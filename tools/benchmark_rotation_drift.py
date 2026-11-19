"""Measure rotationdriftfix in ZX Spectrum 48K with assets/zxspectrum48k.rom.

Run after make.bat rotationdriftfix=yes verify=no. Optionally supply a saved
earlier build/game.bin with --previous-image to compare implementations; all
bytes outside this option's seven fixed regions must match the current build.
Writes build/rotation-speed/verification.json. Nominal 3.5 MHz timing includes
real interrupts but does not model ULA contention; this is not hardware FPS.
"""
import argparse
import contextlib
import io
import json
import statistics
from pathlib import Path

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
from check_build_options import FIX_PARTS
import check_routines as cr
from skoolkit import CSimulator, tap2sna
from skoolkit.snapshot import Snapshot
from skoolkit.simutils import PC, T, from_snapshot
from skoolkit.trace import Tracer
from emulator_check import KEYS

OUT = ROOT / 'build/rotation-speed'
CLOCK_HZ = 3500000
CONTROLS = (('straight', 0, 0), ('roll1', 1, 0), ('roll15', 15, 0),
            ('pitch1', 0, 1), ('pitch15', 0, 15), ('both15', 15, 15))
VECTORS = ((196608, 65536, 524288), (-196608, 65536, -524288),
           (3543, -2007, 98219), (4000, 2000, 10000), (-32767, -89991, 3333333))


def boot(s):
    """ROM-load, launch, then stop at MainLoop with a reproducible IRQ phase."""
    rom = ROOT / 'assets/zxspectrum48k.rom'
    tap2sna.ROM48 = str(rom)
    with (OUT / 'boot.log').open('w') as log, contextlib.redirect_stdout(log):
        tap2sna.main(['--start', hex(s['Entry']), RELEASE_TAP.relative_to(ROOT).as_posix(),
                      str(OUT / 'loaded.z80')])
        snapshot = Snapshot.get(str(OUT / 'loaded.z80'))
        sim = from_snapshot(CSimulator, snapshot, rom_file=str(rom))
        trace = Tracer(sim, snapshot.border, 0, 0, [0] * 16, snapshot.outfe, False)
        sim.set_tracer(trace)
        t0 = sim.registers[T]

        def draw(screen, frame, border, keyboard):
            elapsed = (sim.registers[T] - t0) / CLOCK_HZ
            keyboard[:] = [0] * 8
            for start, key in ((3, 'N'), (5, 'SPACE'), (8, '1')):
                if start <= elapsed < start + .5:
                    row, mask = KEYS[key]
                    keyboard[row] |= mask
            return True

        trace.run(s['Entry'], None, 0, 20 * CLOCK_HZ, True, draw,
                  None, None, None, '$', '02X', '04X')
        trace.keyboard = [0] * 8
        sim.run(stop=s['MainLoop'], interrupts=True)
    assert sim.memory[s['FlightCondition']] and not sim.memory[s['PlayerDeadFlag']]
    return list(sim.memory), list(sim.registers)


def clone(memory, registers):
    sim = CSimulator(list(memory))
    for i, value in enumerate(registers):
        sim.registers[i] = value
    trace = Tracer(sim, 0, 0, 0, [0] * 16, 0, False)
    trace.keyboard = [0] * 8
    sim.set_tracer(trace)
    return sim


def main_loop_frame(sim, s, keys=(), executed=None):
    """Run one complete game update with interrupts and a bounded timeout.

    Feature checks inject fixtures only at MainLoop and observe the next
    MainLoop, after contact, drawing and shield updates have all finished.
    The generous bound also allows the docking animation to finish.
    """
    assert sim.registers[PC] == s['MainLoop']
    trace = Tracer(sim, 0, 0, 0, [0] * 16, 0, False)
    trace.keyboard = [0] * 8
    for key in keys:
        row, mask = KEYS[key]
        trace.keyboard[row] |= mask
    sim.set_tracer(trace)
    with contextlib.redirect_stdout(io.StringIO()):
        trace.run(s['MainLoop'], s['MainLoop'], 0, 30 * CLOCK_HZ, True,
                  None, executed, None, None, '$', '02X', '04X')
    assert sim.registers[PC] == s['MainLoop'], ('main-loop timeout', hex(sim.registers[PC]))
    assert not sim.memory[s['PlayerDeadFlag']]
    return trace.operations


def compare_previous(contexts, s):
    """Keep outputs exact across every legal signed roll/pitch combination."""
    machines = {name: contexts[name].machine() for name in ('previous', 'fixed')}
    angles = (*range(16), *range(128, 144))
    points = ((196608, 65536, 524288), (-196608, -65536, -524288),
              (0, 1, -1), (3000000, -2000000, 1000000))
    p, cases = s['PlanetPosition'], 0

    def prepare(m, point, roll, pitch):
        for i, value in enumerate(point):
            cr.put24(m.memory, p + i * 3, value)
        m.poke('PlayerRoll', roll)
        m.poke('PlayerPitch', pitch)
        m.poke('PlayerSpeed', 20)

    for roll in angles:
        for pitch in angles:
            for point in points:
                outputs = []
                for m in machines.values():
                    prepare(m, point, roll, pitch)
                    m.call('ApplyPlayerMotion', ix=p, iy=0x1234, **cr.ZERO_REGISTERS)
                    outputs.append((bytes(m.memory[p:p + 9]), m.pair('hl'), m.ix(), m.iy()))
                assert outputs[0] == outputs[1], (roll, pitch, point, outputs)
                cases += 1

    # Observe SP after every instruction on representative paths. Include the
    # caller's return address, exclude interrupts (their handler is unchanged).
    peaks = {}
    for name, m in machines.items():
        low = m.ctx.test_stack

        def observe(machine):
            nonlocal low
            low = min(low, machine.r[cr.SP])

        for _, roll, pitch in CONTROLS:
            for point in points:
                prepare(m, point, roll, pitch)
                visited = m.call('ApplyPlayerMotion', ix=p, **cr.ZERO_REGISTERS, record=True)
                prepare(m, point, roll, pitch)
                m.call('ApplyPlayerMotion', ix=p, **cr.ZERO_REGISTERS,
                       hooks={pc: observe for pc in visited})
        peaks[name] = m.ctx.test_stack - low
    assert peaks['fixed'] <= peaks['previous'], peaks
    return dict(passed=True, coordinate_byte_cases=cases, peak_stack_bytes=peaks)


def run(previous_path):
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / 'verification.json'
    report_path.unlink(missing_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    assert s['ROTATION_DRIFT_FIX'] == 1, 'Build rotationdriftfix=yes first'
    assert not s.get('DOCKING_ROTATION'), 'Build dockingrotation=no to isolate rotation timing'
    image = (ROOT / 'build/game.bin').read_bytes()
    assert parse(RELEASE_TAP.read_bytes())[5].payload == image
    ref = reference()[1][5].payload  # Validate TAP scope, structure and hash.
    regions = [(s[p + 'Start'], s[p + 'Limit']) for p in FIX_PARTS['rotationdriftfix'][0]]
    original = bytearray(image)
    for a, b in regions:
        a, b = a - s['GameImage'], b - s['GameImage']
        original[a:b] = ref[a:b]
    images = {'original': bytes(original), 'fixed': image}
    if previous_path:
        previous = previous_path.read_bytes()
        assert len(previous) == len(image), 'Previous game image size differs'
        outside = bytearray(previous)
        for a, b in regions:
            a, b = a - s['GameImage'], b - s['GameImage']
            outside[a:b] = image[a:b]
        assert outside == image, 'Previous image differs outside rotationdriftfix regions'
        images['previous'] = previous
    contexts = {name: cr.ImageContext(s, data) for name, data in images.items()}
    report = dict(machine='ZX Spectrum 48K', rom='assets/zxspectrum48k.rom',
                  clock_hz=CLOCK_HZ, ship='adder' if s['SHIP_ADDER'] else 'krait',
                  image_sha256={name: sha(data) for name, data in images.items()},
                  routine={}, frames={})
    if previous_path:
        report['previous_comparison'] = compare_previous(contexts, s)
    for name, roll, pitch in CONTROLS:
        measurements = {}
        for variant, ctx in contexts.items():
            m, times = ctx.machine(), []
            for vector in VECTORS:
                for i, value in enumerate(vector):
                    cr.put24(m.memory, s['PlanetPosition'] + i * 3, value)
                m.poke('PlayerRoll', roll)
                m.poke('PlayerPitch', pitch)
                m.poke('PlayerSpeed', 20)
                t = m.r[T]
                m.call('ApplyPlayerMotion', ix=s['PlanetPosition'], **cr.ZERO_REGISTERS)
                times.append(m.r[T] - t)
            measurements[variant] = dict(mean_tstates=statistics.mean(times),
                                         min_tstates=min(times), max_tstates=max(times))
        report['routine'][name] = measurements
    bootmem, bootregs = boot(s)

    def patch(memory, variant):
        for a, b in regions:
            memory[a:b] = images[variant][a - s['GameImage']:b - s['GameImage']]

    for scene in ('front_after_launch', 'rear_station', 'front_four_ships'):
        scene_mem = list(bootmem)
        scene_mem[s['CurrentScreenId']] = 1 if scene == 'rear_station' else 0
        if scene == 'front_four_ships':
            m = contexts['original'].machine()
            m.memory[:] = scene_mem
            for i, ship_id in enumerate((9, 10, 14, 9)):
                slot = s['InitialRuntimeState'] + (i + 1) * s['InstanceSize']
                m.call('InitialiseShipFromBlueprint', a=ship_id, ix=slot)
                vector = ((-1 if i % 2 else 1) * (1800 + i * 300),
                          (-1 if i < 2 else 1) * 1200, 10000 + i * 2000)
                for axis, value in enumerate(vector):
                    cr.put24(m.memory, slot + axis * 3, value)
            scene_mem = list(m.memory)
        for name, roll, pitch in CONTROLS:
            memory, registers = list(scene_mem), list(bootregs)
            patch(memory, 'original')
            memory[s['ControlsLockedFlag']] = 1
            memory[s['PlayerRoll']], memory[s['PlayerPitch']] = roll, pitch
            memory[s['PlayerSpeed']] = 20
            times = {variant: [] for variant in images}
            for frame in range(32):
                clones = {}
                for variant in images:
                    mem = list(memory)
                    patch(mem, variant)
                    machine = clone(mem, registers)
                    t = machine.registers[T]
                    machine.run(stop=s['MainLoop'], interrupts=True)
                    assert not machine.memory[s['PlayerDeadFlag']]
                    assert machine.memory[s['FlightCondition']]
                    times[variant].append(machine.registers[T] - t)
                    clones[variant] = machine
                # Identical input state and IRQ phase for every variant. Use
                # the original trajectory so its drift cannot bias timings.
                memory = list(clones['original'].memory)
                registers = list(clones['original'].registers)
            result = {'frames': 32}
            for variant, ticks in times.items():
                mean = statistics.mean(ticks)
                result[variant] = dict(mean_tstates=mean, fps=CLOCK_HZ / mean)
            report['frames'][scene + '_' + name] = result
            print(scene, name, json.dumps(result), flush=True)
    report['method'] = ('Matched complete MainLoop-to-MainLoop frames from the same ROM-loaded '
                        '48K state, real interrupts, 32 frames per fixture, nominal 3.5 MHz, '
                        'no ULA contention. Original trajectory supplies each next input state.')
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Report:', report_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-image', type=Path)
    run(parser.parse_args().previous_image)
