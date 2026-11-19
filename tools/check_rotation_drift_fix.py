"""Check rotationdriftfix=yes using ZX Spectrum 48K and assets/zxspectrum48k.rom.

Run after make.bat rotationdriftfix=yes verify=no (either ship). --emulator also
loads the actual release through the 48K ROM, launches, selects a side view
and reverses roll repeatedly. Reports are disposable build artifacts.
"""
import argparse
import json
import math
import random

from tape import ROOT, RELEASE_TAP, reference, parse, sha
from build import symbol_map
from check_build_options import FIX_PARTS
import check_routines as cr
from check_competition_remove import check_save_paths

OUT = ROOT / 'build/rotation-drift-fix-check'


def vector(m, p):
    return tuple(cr.get24(m.memory, p + i * 3) for i in range(3))


def put_vector(m, p, v):
    for i, n in enumerate(v):
        cr.put24(m.memory, p + i * 3, n)


def signed(n):
    return abs(n) | (128 if n < 0 else 0)


def rotation_model(point, roll, pitch):
    """Independent integer three-shear model, truncating products toward zero."""
    def product(value, coefficient, divisor):
        n = value * coefficient
        return (1 if n >= 0 else -1) * (abs(n) // divisor)

    def plane(u, v, coefficient):
        u -= product(v, coefficient, 512)
        v += product(u, coefficient, 256)
        u -= product(v, coefficient, 512)
        return u, v

    x, y, z = point
    z, y = plane(z, y, cr.sm8(pitch))
    x, y = plane(x, y, 2 * cr.sm8(roll))
    return x, y, z


def check_full_rotation(ctx):
    """Check control conversion and both planes together, including pitch carry."""
    m, s = ctx.machine(), ctx.symbols
    p = s['PlanetPosition']
    points = ((10000, -65536, 65300), (-10000, 65536, -65300),
              (196608, 65536, 524288), (-196608, -65536, -524288),
              (0, 1, -1), (3000000, -2000000, 1000000))
    angles = (*range(16), *range(128, 144))
    cases = 0
    for roll in angles:
        for pitch in angles:
            for point in points:
                expected = rotation_model(point, roll, pitch)
                for carry in (0, 1):
                    put_vector(m, p, point)
                    m.poke('PlayerRoll', roll)
                    m.poke('PlayerPitch', pitch)
                    m.call('ApplyPlayerMotion', ix=p, iy=0x1234, f=carry,
                           stop='TranslatePlayerPosition', balance=False)
                    actual = vector(m, p)
                    assert actual == expected, (point, roll, pitch, carry, actual, expected)
                    assert m.ix() == p and m.iy() == 0x1234
                    assert m.byte('RotationDriftHalfScale') == 0
                    cases += 1
    return cases


def run(emulate):
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / 'verification.json'
    report_path.unlink(missing_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    assert s['ROTATION_DRIFT_FIX'] == 1, 'Build rotationdriftfix=yes first'
    image = (ROOT / 'build/game.bin').read_bytes()
    ref = reference()[1][5].payload  # framing, checksums and immutable hash checked
    original = bytearray(image)
    parts = FIX_PARTS['rotationdriftfix'][0]
    for part in parts:
        a, b = s[part + 'Start'] - s['GameImage'], s[part + 'Limit'] - s['GameImage']
        original[a:b] = ref[a:b]
    # A dependent docking hook cannot call helpers after their parent regions
    # have been restored to original bytes in the comparison image.
    if s.get('DOCKING_ROTATION'):
        a, b = s['DockingRotationHookStart']-s['GameImage'], s['DockingRotationHookLimit']-s['GameImage']
        original[a:b] = ref[a:b]
    fixed = cr.ImageContext(s, image)
    baseline = cr.ImageContext(s, original)
    m = fixed.machine()
    p = s['PlanetPosition']
    rng = random.Random(728)

    # Exhaust all byte products used by the 24-bit coordinate multiplier.
    for b in range(256):
        for c in range(128):
            m.call('RotationDriftMultiply', b=b, c=c)
            assert m.pair('hl') == b * c
            assert m.pair('bc') == (b << 8) | c
    # Independent integer model, including both signs, half products, odd
    # pitch, small fractions, zero crossing and large representable inputs.
    cases = [(u, v, c, half) for u in (-1, 0, 1) for v in (-513, -1, 0, 1, 513)
             for c in (-30, -15, -1, 0, 1, 15, 30) for half in (False, True)]
    cases += [(rng.randrange(-3000000, 3000001), rng.randrange(-3000000, 3000001),
               rng.randrange(-30, 31), bool(rng.randrange(2))) for _ in range(1500)]
    for u, v, c, half in cases:
        put_vector(m, p, (u, v, 271))
        m.call('RotationDriftHalfCoordinate' if half else 'AddScaledCoordinate',
               ix=p, iy=0x1234, hl=s['InstanceX'], de=s['InstanceY'], c=signed(c))
        delta = abs(v * c) // (512 if half else 256)
        assert vector(m, p) == (u + (delta if v * c >= 0 else -delta), v, 271)
        assert m.ix() == p and m.iy() == 0x1234
        assert m.byte('RotationDriftHalfScale') == 0

    # The roll coefficient must not inherit carry from the pitch plane. Test
    # the full dispatcher against mathematics, not against its old wrapper.
    full_rotation_cases = check_full_rotation(fixed)

    # Each plane transform must be inverted exactly by its opposite rate
    # (numeric coordinates; positive and negative zero are equivalent).
    for rate in range(-30, 31):
        for start in ((1, -1, 0), (0, 0, 0), (196608, 65536, -524288),
                      (-2000000, 1000000, 3000000)):
            for axis in ('InstanceX', 'InstanceZ'):
                put_vector(m, p, start)
                for c in (rate, -rate):
                    m.call('RotationDriftRotatePlane', ix=p, a=signed(c),
                           de=s['InstanceY'], hl=s[axis])
                assert vector(m, p) == start, (rate, axis, start, vector(m, p))

    # Translation must keep the original's zero crossing, overflow and HL
    # return. With zero angles the entire ApplyPlayerMotion result is equal.
    o = baseline.machine()
    for speed in (0, 1, 20, 40):
        for z in (-8388607, -65536, -1, 0, 1, 255, 256, 65536, 8388607):
            outputs = []
            for mm in (m, o):
                put_vector(mm, p, (1234, -5678, z))
                mm.poke('PlayerSpeed', speed)
                mm.poke('PlayerRoll', 0)
                mm.poke('PlayerPitch', 0)
                mm.call('ApplyPlayerMotion', ix=p)
                outputs.append((vector(mm, p), mm.pair('hl')))
            assert outputs[0] == outputs[1], (speed, z, outputs)

    # The reported defect with the real control ramp; repeat ten times longer
    # too. Stop before translation to isolate rotation for pitch/mixed cases.
    drift = {}
    for name, ctx in (('original', baseline), ('fixed', fixed)):
        for control in ('roll', 'pitch', 'mixed', 'one_way'):
            mm = ctx.machine()
            start = (196608, 65536, 524288)
            put_vector(mm, p, start)
            rolls = cr.alternating_roll_bytes(32, 200 if name == 'fixed' else 20)
            for r in rolls:
                mm.poke('PlayerRoll', 15 if control == 'one_way' else r if control != 'pitch' else 0)
                mm.poke('PlayerPitch', r if control in ('pitch', 'mixed') else 0)
                mm.call('ApplyPlayerMotion', ix=p, stop='TranslatePlayerPosition', balance=False)
            ratio = math.dist(vector(mm, p), (0, 0, 0)) / math.dist(start, (0, 0, 0))
            radial = math.hypot(*vector(mm, p)[:2]) / math.hypot(*start[:2])
            drift[name + '_' + control] = dict(updates=len(rolls), radius_ratio=ratio, xy_ratio=radial)
            if name == 'fixed':
                assert abs(ratio - 1) < 0.005, (control, ratio)
                if control == 'roll':
                    assert abs(radial - 1) < 0.005, radial
            elif control == 'roll':
                assert round(radial, 2) == 4.98, radial

    # Exercise both actual callers with identical vectors and all four view
    # selections: motion is independent of which projection is displayed.
    for view in range(4):
        mm = fixed.machine()
        mm.poke('CurrentScreenId', view)
        start = (196608, -65536, 524288)
        for body in ('SunPosition', 'PlanetPosition'):
            put_vector(mm, s[body], start)
        mm.poke('PlayerRoll', 15)
        mm.poke('PlayerPitch', 7)
        mm.poke('PlayerSpeed', 20)
        mm.call('MoveSunAndPlanet')
        assert vector(mm, s['SunPosition']) == vector(mm, p)
        put_vector(mm, s['InitialRuntimeState'], start)
        mm.call('ApplyPlayerMotion', ix=s['InitialRuntimeState'])
        assert vector(mm, s['InitialRuntimeState']) == vector(mm, p)
        assert mm.byte('RotationDriftHalfScale') == 0

    save = check_save_paths(s, baseline, fixed)

    report = dict(passed=True, machine='ZX Spectrum 48K', rom='assets/zxspectrum48k.rom',
                  image_sha256=sha(image), ship='adder' if s['SHIP_ADDER'] else 'krait',
                  products=32768, coordinate_cases=len(cases), inverse_plane_cases=488,
                  full_rotation_cases=full_rotation_cases,
                  drift=drift, save=save)
    if emulate:
        report['emulator'] = emulator(s, image, original)
    report_text = json.dumps(report, indent=2) + '\n'
    report_path.write_text(report_text, encoding='utf-8')
    (OUT / ('verification-' + report['ship'] + '.json')).write_text(report_text, encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


def emulator(s, image, original):
    import benchmark_rotation_drift as bench
    from emulator_check import png
    from skoolkit.simutils import T

    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == image
    bench.OUT = OUT
    memory, registers = bench.boot(s)
    results = {}
    start = (0x080000, 0x010000, 0x030000)
    sun = (0x100000, -0x040000, 0x060000)
    rolls = cr.alternating_roll_bytes(32, 20)
    ship = 'adder' if s['SHIP_ADDER'] else 'krait'
    for name, old in (('fixed', False), ('original', True)):
        sim = bench.clone(memory, registers)
        ram = sim.memory
        if old:
            parts = FIX_PARTS['rotationdriftfix'][0] + (('DockingRotationHook',) if s.get('DOCKING_ROTATION') else ())
            for part in parts:
                a, b = s[part+'Start'], s[part+'Limit']
                ram[a:b] = original[a-s['GameImage']:b-s['GameImage']]
        for body, point in (('PlanetPosition', start), ('SunPosition', sun)):
            for axis, value in enumerate(point):
                cr.put24(ram, s[body] + axis * 3, value)
        # Same control ramp and update count for every option combination.
        # Interrupts still run; locking the copied controls avoids time-based
        # key repeats changing the number of turns between slow/fast builds.
        for key, value in (('ControlsLockedFlag', 1), ('CurrentScreenId', 3),
                           ('PlayerPitch', 0), ('PlayerSpeed', 0)):
            ram[s[key]] = value
        executed, operations = set(), 0
        for roll in rolls:
            ram[s['PlayerRoll']] = roll
            operations += bench.main_loop_frame(sim, s, executed=executed)
            assert ram[s['FlightCondition']] and s['RunGameOverSequence'] not in executed
        assert s['ApplyPlayerMotion'] in executed and s['DrawSunAndPlanet'] in executed
        ratios = {}
        for body, v in (('PlanetPosition', start), ('SunPosition', sun)):
            xy = [cr.get24(ram, s[body] + i * 3) for i in range(2)]
            ratios[body] = math.hypot(*xy) / math.hypot(*v[:2])
            if not old:
                assert abs(ratios[body] - 1) < .005, ratios
        results[name] = dict(ratios=ratios, current_view=ram[s['CurrentScreenId']],
                             updates=len(rolls), operations=operations,
                             tstates=sim.registers[T]-registers[T])
        label = 'rotation-drift-' + ship + '-' + name
        (OUT / (label+'-memory.bin')).write_bytes(bytes(ram))
        png(ram[0x4000:0x5B00], OUT / (label+'.png'))
    assert results['fixed']['current_view'] == 3, results
    assert results['original']['ratios']['PlanetPosition'] > 1.1, results

    # Carry regression through the real callers in an interrupt-driven frame.
    # With no roll, pitch must leave X exactly unchanged for both bodies.
    sim = bench.clone(memory, registers)
    point = (10000, -65536, 65300)
    for body in ('PlanetPosition', 'SunPosition'):
        for axis, value in enumerate(point):
            cr.put24(sim.memory, s[body] + axis * 3, value)
    for key, value in (('ControlsLockedFlag', 1), ('CurrentScreenId', 3),
                       ('PlayerPitch', 1), ('PlayerRoll', 0), ('PlayerSpeed', 0)):
        sim.memory[s[key]] = value
    bench.main_loop_frame(sim, s)
    x, y, z = rotation_model(point, 0, 1)
    expected = (x, y, z-2)  # original translation with PlayerSpeed=0
    results['pitch_only'] = {}
    for body in ('PlanetPosition', 'SunPosition'):
        actual = tuple(cr.get24(sim.memory, s[body] + i * 3) for i in range(3))
        assert actual == expected, (body, actual, expected)
        results['pitch_only'][body] = actual
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true')
    run(parser.parse_args().emulator)


