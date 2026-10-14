"""Record which game instructions read, write or jump to each address.

Runs the deterministic gameplay scenarios from run_runtime_scenarios.py on the
rebuilt default TAP, always as a ZX Spectrum 48K with the supplied 48K ROM.
Unlike emulator_check.py --memory-accesses, every RAM access is attributed to
the program counter of the instruction that performed it. The aggregated
result is the evidence base for naming variables and classifying data:

    python tools/trace_xrefs.py                 # all scenarios
    python tools/trace_xrefs.py inflight-screens hyperspace-diso
    python tools/trace_xrefs.py --merge         # only rebuild the summary

Per-scenario reports go to build/xrefs/; the merged summary is written to
docs/generated/runtime-xrefs.json. No game byte is patched; scenario RAM
changes are the same documented test pokes used by run_runtime_scenarios.py.
"""
import argparse
import json
import sys
import time
from multiprocessing import Pool

from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, sha
from build import symbol_map
from emulator_check import KEYS, ROM48, MACHINE, png, screen_text
from run_runtime_scenarios import SCENARIOS as BASE_SCENARIOS, key, poke, started

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit import tap2sna                               # noqa: E402
from skoolkit.snapshot import Snapshot                     # noqa: E402
from skoolkit.simutils import from_snapshot, PC, T        # noqa: E402
from skoolkit.trace import Tracer                          # noqa: E402
from skoolkit.simulator import Simulator                   # noqa: E402

# Test-only commander pokes (active record $A816 + offset), applied after the
# normal start.  Offsets follow docs/info save notes and are listed in reports.
ACTIVE = 0xA816
def equip(start, offset, value='01'):
    return poke(start, hex(ACTIVE + offset), value)

def launched(seconds, *extra):
    return [*started(seconds), *key(8, 0.4, '1'), *extra]

EXTRA_SCENARIOS = {
    # Fire at the station behind the ship after launch: the station turns
    # hostile and launches Vipers, which exercises combat and AI code.
    'combat-station': launched(60, *key(12, 0.3, '2'), *key(13, 8, 'A'),
                               *key(30, 0.3, '1'), *key(32, 6, 'A'), *key(42, 6, 'A')),
    'missile-target': launched(40, *key(12, 0.3, '2'), *key(13, 0.3, 'T'),
                               *key(15, 0.3, 'F'), *key(20, 0.3, 'T'), *key(22, 0.3, 'U')),
    'ecm-bomb-pod': launched(40, *equip(7, 0x31), *equip(7, 0x36), *equip(7, 0x35),
                             *key(14, 0.3, 'E'), *key(20, 0.3, 'W'), *key(28, 0.3, 'Q')),
    'docking-computer': launched(70, *equip(7, 0x38), *key(14, 0.3, 'C')),
    'pause-options': launched(30, *key(12, 0.3, 'CS'), *key(14, 0.2, 'R'),
                              *key(15, 0.2, 'D'), *key(16, 0.2, 'Q'), *key(17, 0.2, 'S'),
                              *key(18, 0.2, 'Y'), *key(19, 0.2, 'B'), *key(20, 0.2, 'K'),
                              *key(21, 0.2, 'K'), *key(23, 0.3, 'SPACE')),
    'flight-controls': launched(40, *key(12, 2, 'N'), *key(14, 2, 'M'), *key(16, 2, 'S'),
                                *key(18, 2, 'X'), *key(20, 3, 'SPACE'), *key(24, 2, 'SS'),
                                *key(27, 0.3, 'D'), *key(29, 0.3, 'J'), *key(33, 0.3, '3')),
    'chart-cursor': [*started(30), *key(8, 0.3, 'I'), *key(10, 1, 'M'), *key(12, 1, 'X'),
                     *key(14, 0.3, 'D'), *key(16, 0.3, 'B'), *key(18, 0.3, 'O'),
                     *key(20, 1, 'N'), *key(22, 1, 'S'), *key(24, 0.3, 'D')],
    'access-menu': [*started(30), *key(8, 0.3, 'SS'), *key(11, 0.3, '3'), *key(14, 0.3, 'SS'),
                    *key(17, 0.3, '1'), *key(20, 0.3, 'N'), *key(23, 0.3, '3')],
    'title-idle': ['--seconds', '40'],
    'mission-one': [*started(55), *equip(7, 0x11), *equip(7, 0x0F, '1F'),
                    *key(8, 0.3, 'I'), *key(10, 0.3, 'R'), *key(11, 0.18, 'D'), *key(11.45, 0.18, 'I'),
                    *key(11.9, 0.18, 'S'), *key(12.35, 0.18, 'O'), *key(13, 0.25, 'ENTER'),
                    *key(16, 0.3, 'L'), *key(18, 0.4, '1'), *key(24, 0.3, 'H'), *key(46, 0.4, 'L')],
}
SCENARIOS = {**BASE_SCENARIOS, **EXTRA_SCENARIOS}
OUT = ROOT / 'build' / 'xrefs'
SUMMARY = ROOT / 'docs' / 'generated' / 'runtime-xrefs.json'
# Opcodes whose next PC is chosen at runtime from a register.
INDIRECT = {(0xE9,), (0xDD, 0xE9), (0xFD, 0xE9)}


class AttributedMemory(list):
    """List-compatible memory that records (pc, address) for each access."""
    def __init__(self, values):
        super().__init__(values)
        self.pc = 0
        self.reads = set()
        self.writes = set()

    def __getitem__(self, key):
        if key.__class__ is int:
            pc = self.pc
            # Skip opcode/operand fetches of the current instruction.
            if not 0 <= key - pc < 4:
                self.reads.add((pc << 16) | key)
        return list.__getitem__(self, key)

    def __setitem__(self, key, value):
        if key.__class__ is int:
            self.writes.add((self.pc << 16) | (key & 0xFFFF))
        return list.__setitem__(self, key, value)


class AttributedSimulator(Simulator):
    def __init__(self, memory, registers=None, state=None, config=None):
        super().__init__(AttributedMemory(memory), registers, state, config)


def parse_scenario(arguments):
    seconds, keys, pokes = 3.0, [], []
    items = iter(arguments)
    for item in items:
        value = next(items)
        if item == '--seconds':
            seconds = float(value)
        elif item == '--key':
            start, duration, key = value.split(':')
            keys.append((float(start), float(start) + float(duration), key.upper()))
        elif item == '--poke':
            start, address, data = value.split(':')
            pokes.append(dict(start=float(start), address=int(address, 0),
                              data=bytes.fromhex(data), applied=False))
    return seconds, keys, pokes


def run(name):
    seconds, keys, pokes = parse_scenario(SCENARIOS[name])
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = symbol_map(ROOT / 'build' / 'game.map')
    entry = symbols['Entry']
    tap2sna.ROM48 = str(ROM48)
    loaded = OUT / f'{name}-loaded.z80'
    tap2sna.main(['--start', hex(entry), RELEASE_TAP.relative_to(ROOT).as_posix(),
                  loaded.relative_to(ROOT).as_posix()])
    snapshot = Snapshot.get(str(loaded))
    simulator = from_snapshot(AttributedSimulator, snapshot, rom_file=tap2sna.ROM48)
    memory = simulator.memory
    if simulator.registers[PC] != entry:
        raise AssertionError('Loader entry changed')
    tracer = Tracer(simulator, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                    snapshot.ay, snapshot.outfe, False)
    simulator.set_tracer(tracer)
    tracer.keyboard = [0] * 8
    registers = simulator.registers
    opcodes = simulator.opcodes
    start_t = registers[T]
    end_t = start_t + int(seconds * 3500000)
    frame_duration, int_active = simulator.frame_duration, simulator.int_active
    prev_frame = start_t // frame_duration
    executed = set()
    indirect = set()
    pc = entry
    started = time.time()
    while registers[T] < end_t:
        memory.pc = pc
        first = list.__getitem__(memory, pc)
        opcodes[first]()
        executed.add(pc)
        if first == 0xE9 or (first in (0xDD, 0xFD) and list.__getitem__(memory, (pc + 1) & 0xFFFF) == 0xE9):
            indirect.add((pc << 16) | registers[PC])
        tstates = registers[T]
        if registers[26] and tstates % frame_duration < int_active:
            memory.pc = 0x10000
            simulator.accept_interrupt(registers, memory, pc)
        pc = registers[PC]
        frame = registers[T] // frame_duration
        if frame > prev_frame:
            prev_frame = frame
            elapsed = (registers[T] - start_t) / 3500000
            keyboard = tracer.keyboard
            keyboard[:] = [0] * 8
            for begin, end, key in keys:
                if begin <= elapsed < end:
                    row, mask = KEYS[key]
                    keyboard[row] |= mask
            for event in pokes:
                if not event['applied'] and elapsed >= event['start']:
                    a = event['address']
                    for i, byte in enumerate(event['data']):
                        list.__setitem__(memory, a + i, byte)
                    event['applied'] = True
    def group(pairs):
        result = {}
        for value in pairs:
            source, address = value >> 16, value & 0xFFFF
            if address >= 0x4000:
                result.setdefault(address, set()).add(source)
        return {f'{a:04X}': sorted(f'{p:04X}' if p < 0x10000 else 'INT' for p in pcs)
                for a, pcs in sorted(result.items())}
    ram = bytes(list.__getitem__(memory, slice(0, 65536)))
    png(ram[0x4000:0x5B00], OUT / f'{name}-final.png')
    image = (ROOT / 'build' / 'game.bin').read_bytes()
    font = image[symbols['FontBitmap'] - symbols['GameImage']:symbols['FontBitmapEnd'] - symbols['GameImage']]
    report = dict(machine=MACHINE, scenario=name, seconds=seconds,
                  pokes=[dict(start=e['start'], address=f"${e['address']:04X}", data=e['data'].hex())
                         for e in pokes],
                  final_text=screen_text(ram[0x4000:0x5B00], font),
                  tape_sha256=sha(RELEASE_TAP.read_bytes()),
                  wall_seconds=round(time.time() - started, 1),
                  executed=sorted(f'{a:04X}' for a in executed),
                  indirect=sorted(f'{v >> 16:04X}->{v & 0xFFFF:04X}' for v in indirect),
                  reads=group(memory.reads), writes=group(memory.writes))
    (OUT / f'{name}.json').write_text(json.dumps(report) + '\n')
    loaded.unlink(missing_ok=True)
    return name, report['wall_seconds'], len(executed)


def merge():
    reads, writes, indirect, executed, used = {}, {}, set(), set(), []
    for path in sorted(OUT.glob('*.json')):
        report = json.loads(path.read_text())
        if report.get('machine') != MACHINE:
            raise SystemExit(f'{path.name}: not a ZX Spectrum 48K trace')
        used.append(report['scenario'])
        executed.update(report['executed'])
        indirect.update(report['indirect'])
        for target, source in ((reads, report['reads']), (writes, report['writes'])):
            for address, pcs in source.items():
                target.setdefault(address, set()).update(pcs)
    summary = dict(machine=MACHINE, scenarios=used,
                   evidence='PC-attributed RAM accesses from SkoolKit runs of the unmodified default build',
                   executed=sorted(executed), indirect=sorted(indirect),
                   reads={a: sorted(p) for a, p in sorted(reads.items())},
                   writes={a: sorted(p) for a, p in sorted(writes.items())})
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=0) + '\n')
    print(f'Merged {len(used)} scenarios: {len(executed)} PCs, {len(reads)} read and '
          f'{len(writes)} written addresses -> {SUMMARY.relative_to(ROOT)}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', nargs='*', choices=sorted(SCENARIOS))
    parser.add_argument('--merge', action='store_true', help='only merge existing traces')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not args.merge:
        names = args.scenario or list(SCENARIOS)
        with Pool(min(args.jobs, len(names))) as pool:
            for name, wall, count in pool.imap_unordered(run, names):
                print(f'{name}: {count} PCs in {wall}s', flush=True)
    merge()


if __name__ == '__main__':
    main()
