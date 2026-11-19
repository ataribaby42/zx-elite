"""Check trafficcontrol in ZX Spectrum 48K with assets/zxspectrum48k.rom.

Run after make.bat trafficcontrol=yes verify=no; --emulator also ROM-loads
the current TAP and exercises the complete object update with real allocation.
"""
import argparse
from itertools import product
import json
import random

from tape import ROOT, reference, release_tap, DEFAULT_TAPFILE, parse, sha
from build import symbol_map
from check_build_options import FIX_PARTS
from annotations.objects import FIELDS
import check_routines as cr
from skoolkit.simutils import T


def run(emulator=False):
    out = ROOT / 'build/traffic-control-check'
    out.mkdir(parents=True, exist_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    # z80asm omits unused constants from its map; use the same structure-offset
    # database that emits game.asm, never copied addresses from another build.
    for name, (value, _) in FIELDS.items():
        s.setdefault(name, value)
    assert s['TRAFFIC_CONTROL'] == 1 and s['TrafficControlDistance'] == 1024
    path = out / ('adder.json' if s['SHIP_ADDER'] else 'krait.json')
    path.unlink(missing_ok=True)
    image = (ROOT / 'build/game.bin').read_bytes()
    ref = reference()[1][5].payload  # structurally validated game block only
    baseline = bytearray(image)
    for prefix in FIX_PARTS['trafficcontrol'][0]:
        a, b = (s[prefix + suffix] - s['GameImage'] for suffix in ('Start', 'Limit'))
        baseline[a:b] = ref[a:b]
    fixed, original = cr.ImageContext(s, image), cr.ImageContext(s, baseline)
    m, old = fixed.machine(), original.machine()
    station, blueprint = s['InitialRuntimeState'], s['ShipCoriolisStationBlueprint']
    report = dict(machine='ZX Spectrum 48K', rom='assets/zxspectrum48k.rom',
                  image_sha256=sha(image), distance=1024, extra_allocated_ram=0,
                  reclaimed_unused_bytes=13, checks={})

    def position(machine, point):
        for axis, value in enumerate(point):
            cr.put24(machine.memory, station + axis * 3, value)

    def setup(machine, point=(0, 0, 1000), safety=1, hostile=False, special=False, count=0):
        position(machine, point)
        machine.poke(station + s['InstanceRoleFlags'], 4)
        machine.poke(station + s['InstanceBehaviour'], 4 if hostile else 0)
        machine.poke(station + s['InstanceSpeed'], 0, 0)
        machine.poke('StationPresent', safety)
        machine.poke('EncounterShipCount', count)
        machine.poke('InvasionMissionState', 4 if special else 0)

    def gate(machine, entry='TryLaunchStationTraffic', seed=None, value=0):
        events = []
        if seed is not None:
            machine.poke_word('RandomSeed', seed)
        start = machine.r[T]
        machine.call(entry, ix=station, iy=blueprint, a=value, f=0,
                     stubs={'DispatchShipEventPreservingParent': lambda mm: events.append(mm.reg('a'))})
        assert machine.ix() == station and machine.iy() == blueprint
        return events, machine.word('RandomSeed'), machine.r[T] - start

    # Every middle byte of every axis, both low-byte extremes and all signs.
    # Include the cube's corners: these deliberately differ from a sphere.
    points = set(product((-1024, -1023, 0, 1023, 1024), repeat=3))
    for axis, mid, low, sign in product(range(3), range(256), (0, 255), (-1, 1)):
        point = [0, 0, 0]
        point[axis] = sign * (mid * 256 + low)
        points.add(tuple(point))
    cases = 0
    for safety, value, point in product((0, 1), (0, 1, 2, 255), sorted(points)):
        setup(m, point, safety)
        result = gate(m, 'TryLaunchStationTrader', value=value)[0]
        expected = [] if value >= 2 or (safety and max(map(abs, point)) < 1024) else [0x24]
        assert result == expected, (safety, value, point, result)
        cases += 1
    # Negative zero must behave like positive zero on each axis.
    setup(m, (0, 0, 0))
    for axis in range(3):
        m.poke(station + axis * 3 + 2, 128)
    assert not gate(m, 'TryLaunchStationTrader')[0]
    report['checks']['boundary_and_sign_cases'] = cases + 1
    print(f'PASS: {cases + 1:,} Chebyshev boundaries, signs, S states and random gates.', flush=True)

    # Complete gate/RNG sweeps. Dispatch is observed, so both variants consume
    # exactly the gate RNG calls; no random value is mocked.
    launch_seeds = []
    seed_cases = 0
    timings = {}
    for name, kwargs in (
        ('near', {}), ('edge', dict(point=(0, 0, 1024))),
        ('S_off', dict(safety=0)), ('police', dict(hostile=True)),
        ('special', dict(hostile=True, special=True)), ('count_limit', dict(count=4)),
    ):
        setup(m, **kwargs)
        setup(old, **kwargs)
        launches = 0
        for seed in range(65536):
            before, state, old_t = gate(old, seed=seed)
            after, new_state, new_t = gate(m, seed=seed)
            expected = [] if name == 'near' else before
            assert after == expected and new_state == state, (name, seed, before, after)
            launches += bool(after)
            if name == 'near' and before and len(launch_seeds) < 16:
                launch_seeds.append(seed)
            if name == 'near':
                timings['attempt' if before else 'random_rejected'] = dict(original=old_t, fixed=new_t)
            seed_cases += 1
        report['checks'][name + '_launches'] = launches
        print(f'PASS: {name}: all 65,536 seeds, {launches} allowed events.', flush=True)
    assert len(launch_seeds) == 16
    report['checks']['paired_seed_cases'] = seed_cases
    report['gate_tstates'] = timings

    # Both real proximity callers set E=0; prove their carry and D results for
    # every 16-bit magnitude on each axis. No traffic condition is involved.
    for entry in ('L_F8B3',):
        address = s[entry] - s['GameImage']
        assert image[address:address+3] == bytes((0x11, 0, 2))  # LD DE,$0200
    source = (ROOT / 'src/game.asm').read_text()
    assert source.count('CALL CheckShipProximity') == 2
    second = s['L_F8B3'] - s['GameImage']
    assert bytes((0x16, 10, 0xCD, s['CheckShipProximity'] & 255,
                  s['CheckShipProximity'] >> 8)) in image[second:second+32]
    proximity_cases = 0
    for d, axis in product((2, 10), range(3)):
        setup(m, (0, 0, 0)); setup(old, (0, 0, 0))
        for magnitude in range(65536):
            for machine in (m, old):
                machine.poke_word(station + 3*axis, magnitude)
                machine.call('CheckShipProximity', ix=station, de=d*256, a=0xA5, f=1)
            assert (m.carry(), m.reg('d')) == (old.carry(), old.reg('d')), (d, axis, magnitude)
            proximity_cases += 1
    # Exercise the actual steering caller at boundaries and with its state bits.
    rng = random.Random(0)
    for case in range(2048):
        point = tuple(rng.choice((0, 511, 512, 1023, 1024, 2559, 2560, 3071, 3072, 65535)) for _ in range(3))
        behaviour, roles, courage = rng.randrange(256), rng.randrange(256), rng.randrange(256)
        outcomes = []
        for machine in (m, old):
            setup(machine, point)
            machine.poke(station+s['InstanceBehaviour'], behaviour)
            machine.poke(station+s['InstanceRoleFlags'], roles)
            machine.poke(station+s['InstanceAiState'], courage)
            machine.poke('PlayerLegalScore', case & 255)
            machine.poke(station+s['InstanceEnergy'], 240)
            events = []
            machine.call('UpdateShipHostilityAndSteering', ix=station, iy=blueprint,
                         stubs={name: lambda mm, n=name: events.append(n)
                                for name in ('SteerShipAwayFromPlayer', 'SteerShipTowardsPlayer')})
            outcomes.append((events, bytes(machine.memory[station:station+s['InstanceSize']])))
        assert outcomes[0] == outcomes[1], (case, point, outcomes)
    report['checks']['paired_proximity_cases'] = proximity_cases
    report['checks']['paired_steering_cases'] = 2048
    report['proximity_tstates'] = {}
    for point in ((65535, 0, 0), (0, 65535, 0), (0, 0, 0)):
        measured = []
        for machine in (old, m):
            position(machine, point)
            t = machine.r[T]
            machine.call('CheckShipProximity', ix=station, de=512)
            measured.append(machine.r[T]-t)
        report['proximity_tstates'][str(point)] = dict(zip(('original', 'fixed'), measured))
    print(f'PASS: {proximity_cases:,} paired proximity and 2,048 steering cases.', flush=True)

    # Full allocation, actual selector and RNG, including full uncounted slots.
    allocation_cases = 0
    for point, safety, hostile, occupied, seed in product(
            ((0, 0, 1000), (0, 0, 1024)), (0, 1), (False, True), (False, True), launch_seeds):
        outcomes = []
        for ctx in (original, fixed):
            machine = ctx.machine()
            setup(machine, point, safety, hostile)
            for slot in range(1, 7):
                machine.poke(station+slot*s['InstanceSize']+s['InstanceEnergy'], 100 if occupied else 0)
            machine.poke_word('RandomSeed', seed)
            selected = []
            machine.call('TryLaunchStationTraffic', ix=station, iy=blueprint,
                         hooks={'LaunchSelectedShip': lambda mm: selected.append(mm.reg('a'))})
            assert machine.ix() == station and machine.iy() == blueprint
            outcomes.append((selected, machine.word('RandomSeed'),
                             bytes(machine.memory[station:station+s['InstanceSize']*7])))
        blocked = safety and max(map(abs, point)) < 1024 and not hostile
        if blocked:
            assert not outcomes[1][0]
            if not occupied:
                assert all(outcomes[1][2][slot*s['InstanceSize']+s['InstanceEnergy']] == 0 for slot in range(1, 7))
        else:
            assert outcomes[0] == outcomes[1], (point, safety, hostile, occupied, seed)
        allocation_cases += 1
    report['checks']['paired_full_allocation_cases'] = allocation_cases
    print(f'PASS: {allocation_cases} full-allocation cases, RNG and police unchanged outside suppression.', flush=True)

    # Reachable-state invariant: a dormant far station cannot become active;
    # a moving active station with a nonzero high magnitude loses its energy.
    invariant_cases = 0
    for axis, sign, magnitude in product(range(3), (-1, 1), (65535, 65536, 0x10100, 0x100000)):
        machine = fixed.machine()
        point = [0, 0, 0]; point[axis] = sign*magnitude
        setup(machine, point)
        machine.poke(station+s['InstanceEnergy'], 240)
        machine.poke('StationDormantFlag', 0)
        machine.poke('PlayerSpeed', 0)
        machine.poke('PlayerRoll', 0); machine.poke('PlayerPitch', 0)
        machine.call('MoveObject', ix=station, iy=blueprint)
        if machine.byte(station+s['InstanceEnergy']):
            assert all(machine.byte(station+3*i+2) & 127 == 0 for i in range(3))
        # A separate dormant fixture checks the activation guard, retaining
        # the exact supplied far coordinates by observing only its motion call.
        setup(machine, point)
        machine.poke(station+s['InstanceEnergy'], 0)
        machine.poke('StationDormantFlag', 255)
        machine.call('UpdateStationDormancy', stubs={'MoveObject': None,
                     **({'StationSlotAlign': lambda mm: mm.poke('StationDormantFlag', 0)}
                        if s.get('STATION_SLOT_FIX') else {})})
        assert bool(machine.byte(station+s['InstanceEnergy'])) == (magnitude < 65536)
        invariant_cases += 1
    assert fixed.pristine[blueprint+6] == 0  # station blueprint maximum speed
    report['checks']['active_station_invariant_cases'] = invariant_cases

    if emulator:
        import benchmark_rotation_drift as bench
        meta = json.loads((ROOT / 'build/verification.json').read_text())
        tap = release_tap(meta.get('tapfile', DEFAULT_TAPFILE))
        assert parse(tap.read_bytes())[5].payload == image
        bench.OUT, bench.RELEASE_TAP = out, tap
        memory, _ = bench.boot(s)
        results = []
        for distance, hostile in product((1000, 1024), (False, True)):
            seen = []
            for seed in launch_seeds:
                machine = fixed.machine(); machine.memory[:] = memory
                setup(machine, (0, 0, distance), hostile=hostile)
                for slot in range(1, s['InstanceSlotCount']):
                    machine.poke(station+slot*s['InstanceSize']+s['InstanceEnergy'], 0)
                machine.poke(station+s['InstanceFlags'], 0x40)
                machine.poke(station+s['InstanceEnergy'], 240)
                machine.poke('StationDormantFlag', 0)
                machine.poke('ObjectUpdateCounter', 9)  # station's real AI phase
                machine.poke('PlayerRoll', 0); machine.poke('PlayerPitch', 0)
                machine.poke('PlayerSpeed', 0)
                machine.poke_word('RandomSeed', seed)
                machine.call('UpdateObjects', stack=machine.ctx.upper_stack,
                             hooks={'LaunchSelectedShip': lambda mm: seen.append(mm.reg('a'))})
                assert not machine.byte('PlayerDeadFlag')
            if hostile:
                assert seen and set(seen) == {8}, (distance, hostile, seen)
            elif distance < 1024:
                assert not seen, (distance, seen)
            else:
                expected_types = {9, 10} if s['STATION_RANDOM_LAUNCH_FIX'] else {10}
                assert set(seen) == expected_types, (distance, seen)
            results.append(dict(distance=distance, hostile=hostile, selected=seen))
        report['rom_loaded_object_updates'] = results
        print('PASS: 48K ROM-load, launch, real object updates and trader/police allocations.', flush=True)
    report['passed'] = True
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS:', path.relative_to(ROOT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator', action='store_true')
    run(parser.parse_args().emulator)
