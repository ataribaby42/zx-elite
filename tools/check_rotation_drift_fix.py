"""Check rotationdriftfix=yes using ZX Spectrum 48K and assets/zxspectrum48k.rom.

Run after make.bat rotationdriftfix=yes verify=no (either ship). --emulator also
loads the actual release through the 48K ROM, launches, selects a side view
and reverses roll repeatedly. Reports are disposable build artifacts.
"""
import argparse
import json
import math
import random
import subprocess
import sys

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

    # Half-coordinate cleanup must retain carry from the signed addition:
    # DoubleSignMagnitude consumes it when preparing the subsequent roll.
    # Compare with the same half product called without the wrapper. Both
    # carry values occur here; an XOR A cleanup silently changes full motion.
    direct = fixed.machine()
    carries = set()
    for u, v, c, half in cases:
        if not half:
            continue
        outputs = []
        for mm, entry in ((m, 'RotationDriftHalfCoordinate'),
                          (direct, 'AddScaledCoordinate')):
            put_vector(mm, p, (u, v, 271))
            mm.poke('RotationDriftHalfScale', int(mm is direct))
            mm.call(entry, ix=p, iy=0x1234, hl=s['InstanceX'],
                    de=s['InstanceY'], c=signed(c))
            outputs.append((bytes(mm.memory[p:p + 9]), mm.pair('hl'), mm.r[cr.F] & 1))
        assert outputs[0] == outputs[1], (u, v, c, outputs)
        carries.add(outputs[0][2])
    assert carries == {0, 1}, carries

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
                  half_wrapper_carry_cases=sum(half for _, _, _, half in cases),
                  drift=drift, save=save)
    if emulate:
        report['emulator'] = emulator(s, image, original)
    report_text = json.dumps(report, indent=2) + '\n'
    report_path.write_text(report_text, encoding='utf-8')
    (OUT / ('verification-' + report['ship'] + '.json')).write_text(report_text, encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


def emulator(s, image, original):
    import run_runtime_scenarios as rs
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == image
    results = {}
    start = (0x080000, 0x010000, 0x030000)
    sun = (0x100000, -0x040000, 0x060000)
    def packed(v):
        data = [0] * 9
        for i, n in enumerate(v):
            cr.put24(data, i * 3, n)
        return bytes(data).hex()
    for name, old in (('fixed', False), ('original', True)):
        args = [*rs.started(90), *rs.key(8, .5, '1'), *rs.key(19, .5, '4'),
                *rs.poke(18, hex(s['PlanetPosition']), packed(start)),
                *rs.poke(18, hex(s['SunPosition']), packed(sun))]
        if old:
            parts = FIX_PARTS['rotationdriftfix'][0] + (('DockingRotationHook',) if s.get('DOCKING_ROTATION') else ())
            for part in parts:
                a, b = s[part+'Start'], s[part+'Limit']
                args += rs.poke(0, hex(a), original[a-s['GameImage']:b-s['GameImage']].hex())
        for i in range(16):
            args += rs.key(22 + i * 4, 4, 'M' if i % 2 == 0 else 'N')
        label = 'rotation-drift-' + ('adder-' if s['SHIP_ADDER'] else 'krait-') + name
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', label],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        result = json.loads((ROOT / f'build/emulator/{label}.json').read_text())
        ram = list((ROOT / f'build/emulator/{label}-memory.bin').read_bytes())
        assert result['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in result['test_pokes'])
        assert s['ApplyPlayerMotion'] in result['execution_map']
        ratios = {}
        for body, v in (('PlanetPosition', start), ('SunPosition', sun)):
            xy = [cr.get24(ram, s[body] + i * 3) for i in range(2)]
            ratios[body] = math.hypot(*xy) / math.hypot(*v[:2])
            if not old:
                assert abs(ratios[body] - 1) < .005, ratios
        results[name] = dict(ratios=ratios, current_view=ram[s['CurrentScreenId']],
                             operations=result['operations'])
    assert results['fixed']['current_view'] == 3, results
    assert results['original']['ratios']['PlanetPosition'] > 1.1, results
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true')
    run(parser.parse_args().emulator)


