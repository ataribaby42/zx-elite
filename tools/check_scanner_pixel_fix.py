"""Execute both indicator implementations in ZX Spectrum 48K memory.

Compare every screen byte against the original routines. Watch every write,
not just the final frame, so a clear-then-restore workaround cannot pass.
The exhaustive input byte check includes an absent scanner pixel too.
"""
from itertools import product
import json
import sys
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, reference, sha
from build import symbol_map
from font_variant import selected_font

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import PC, SP, T, from_snapshot
from skoolkit import tap2sna
from skoolkit.snapshot import Snapshot
from skoolkit.trace import Tracer
from emulator_check import KEYS, png

# Locations in the immutable reference payload only. The modified image always
# uses its own symbol map; never run reference bytes at current relocated labels.
REFERENCE_LAYOUT = dict(GameImage=0x6048, GameImageEnd=0xFFA9, FontRuntime=0x5D70,
    L_A660=0xA660, L_A6D3=0xA6D3, L_DA16=0xDA16, L_7077=0x7077,
    L_A894=0xA894, L_BBBF=0xBBBF, L_A845=0xA845,
    L_A80D=0xA80D, L_A80E=0xA80E, L_A892=0xA892)


class WatchedMemory(list):
    def __init__(self, data, pixel_address):
        super().__init__(data)
        self.pixel_writes = []
        self.pixel_address = pixel_address

    def __setitem__(self, address, value):
        if address == self.pixel_address:
            self.pixel_writes.append(value)
        super().__setitem__(address, value)


def call(memory, entry):
    # Test stack is below the font; a zero return address terminates the call.
    memory[0x5CF0:0x5CF2] = [0, 0]
    sim = Simulator(memory, {'PC': entry, 'SP': 0x5CF0})
    for _ in range(10000):
        if sim.registers[PC] == 0:
            assert sim.registers[SP] == 0x5CF2, 'Unbalanced stack'
            return sim
        sim.run()
    raise AssertionError(f'Routine at {entry:04X} did not return')


def launch_check(symbols, directory):
    """ROM load, first launch, and ECM off/on/off, watching actual writes."""
    writes = [0, 0]

    class Memory(list):
        registers = None

        def __setitem__(self, address, value):
            if (address == symbols['ScannerEcmOverlap'] and self.registers is not None
                    and self.registers[PC] == symbols['StoreIndicatorRow']):
                assert (self[address]&1) == (value&1), 'ECM erased a live scanner pixel'
                writes[int(self[symbols['L_DA16']] != 0)] += 1
            super().__setitem__(address, value)

    class WatchedSimulator(Simulator):
        def __init__(self, memory, registers=None, state=None, config=None):
            super().__init__(Memory(memory), registers, state, config)
            self.memory.registers = self.registers

    rom = ROOT/'assets/zxspectrum48k.rom'
    tap2sna.ROM48 = str(rom)
    snapshot_path = directory/'loaded.z80'
    tap2sna.main(['--start', hex(symbols['Entry']), RELEASE_TAP.relative_to(ROOT).as_posix(),
                 snapshot_path.relative_to(ROOT).as_posix()])
    snapshot = Snapshot.get(str(snapshot_path))
    sim = from_snapshot(WatchedSimulator, snapshot, rom_file=str(rom))
    trace = Tracer(sim, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                   snapshot.ay, snapshot.outfe, False)
    sim.set_tracer(trace)
    start = sim.registers[T]
    events = [(3, 3.5, 'N'), (5, 5.5, 'SPACE'), (8, 8.5, '1')]
    captured = set()

    def draw(screen, frame, border, keyboard):
        elapsed = (sim.registers[T]-start)/3500000
        keyboard[:] = [0]*8
        for begin, end, key in events:
            if begin <= elapsed < end:
                row, mask = KEYS[key]
                keyboard[row] |= mask
        # Only the ECM timer in emulated RAM is forced; no code/TAP changes.
        if 18 <= elapsed < 20:
            sim.memory[symbols['L_DA16']] = 10
        for second in (17, 19, 27):
            if elapsed >= second and second not in captured:
                png(screen, directory/f'font-{selected_font(symbols)}-{second}.png')
                captured.add(second)
        return True

    trace.run(symbols['Entry'], None, 0, 28*3500000, True, draw, set(), None, None, '$', '02X', '04X')
    assert min(writes) > 0, 'Both ECM states must execute after first launch'
    assert sim.memory[symbols['L_7041']] == 0, 'Expected front cockpit view'
    return dict(seconds=28, ecm_off_writes=writes[0], ecm_on_writes=writes[1],
                first_launch_passed=True, test_only_ecm_timer_override_seconds=[18, 20])


def main():
    symbols = symbol_map(ROOT/'build/game.map')
    image = (ROOT/'build/game.bin').read_bytes()
    original = reference()[1][5].payload
    font = image[symbols['FontBitmap']-symbols['GameImage']:symbols['FontBitmapEnd']-symbols['GameImage']]
    pixel = symbols['ScannerEcmOverlap']  # Fixed video RAM location.
    report_path = ROOT/'build/scanner-pixel-check'/f'font-{selected_font(symbols)}.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    assert symbols['SCANNER_PIXEL_FIX'] == 1, 'Build scannerpixelfix=yes first'
    assert symbols['CockpitIndicatorsEnd'] <= symbols['CockpitIndicatorsLimit']

    def memory(payload, layout):
        result = [0]*65536
        result[:0x4000] = (ROOT/'assets/zxspectrum48k.rom').read_bytes()
        result[layout['GameImage']:layout['GameImageEnd']] = payload
        result[layout['FontRuntime']:layout['FontRuntime']+len(font)] = font
        # Nonuniform old pixels expose missing writes or unwanted OR blending.
        result[0x4000:0x5B00] = [(i*37+19)&255 for i in range(0x1B00)]
        result[layout['L_A894']] = 0       # Normal screen output, not text measurement
        return result

    cases = 0
    for ecm, station, old in product((0, 1, 255), (0, 1), range(256)):
        baseline, fixed = memory(original, REFERENCE_LAYOUT), memory(image, symbols)
        for ram, layout in ((baseline, REFERENCE_LAYOUT), (fixed, symbols)):
            ram[layout['L_DA16']], ram[layout['L_7077']], ram[pixel] = ecm, station, old
        fixed = WatchedMemory(fixed, pixel)
        call(baseline, REFERENCE_LAYOUT['L_A660'])
        call(fixed, symbols['L_A660'])
        baseline[pixel] = (baseline[pixel]&0xFE) | (old&1)
        assert fixed[0x4000:0x5B00] == baseline[0x4000:0x5B00], (ecm, station, old)
        assert fixed.pixel_writes == [baseline[pixel]], 'Pixel was transiently erased'
        assert fixed[symbols['L_BBBF']] == baseline[REFERENCE_LAYOUT['L_BBBF']] == 0xA9
        assert fixed[symbols['FontRuntime']:symbols['FontRuntimeEnd']] == list(font), 'Runtime font changed'
        cases += 1

    for count in range(5):
        baseline, fixed = memory(original, REFERENCE_LAYOUT), memory(image, symbols)
        baseline[REFERENCE_LAYOUT['L_A845']] = fixed[symbols['L_A845']] = count
        call(baseline, REFERENCE_LAYOUT['L_A6D3'])
        call(fixed, symbols['L_A6D3'])
        assert fixed[0x4000:0x5B00] == baseline[0x4000:0x5B00], count
        for label in ('L_BBBF', 'L_A80D', 'L_A80E', 'L_A892'):
            assert fixed[symbols[label]] == baseline[REFERENCE_LAYOUT[label]], (count, label)

    report = dict(passed=True, machine='ZX Spectrum 48K', game_sha256=sha(image),
                  font=selected_font(symbols),
                  exhaustive_indicator_cases=cases, missile_counts=list(range(5)),
                  every_pixel_write_checked=True, other_screen_bytes_match_original=True,
                  added_image_bytes=0, replacement_bytes=symbols['CockpitIndicatorsEnd']-symbols['L_A660'])
    report['rom_load_and_launch'] = launch_check(symbols, report_path.parent)
    report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f'PASS: {cases} indicator cases, all five missile counts; every pixel write preserves bit 0.')


if __name__ == '__main__':
    main()
