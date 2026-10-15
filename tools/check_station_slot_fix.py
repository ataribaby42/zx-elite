"""Check stationslotfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat stationslotfix=yes verify=no
    python tools/check_station_slot_fix.py
    python tools/check_station_slot_fix.py --emulator

The simulator part executes the assembled image with the supplied 48K ROM in
SkoolKit's Z80 simulator and compares it with a baseline that differs only in
the four replaced areas, restored from the immutable reference tape.  It
checks the switch-on alignment for 3,000 random and 36 axis geometries, the
following active frames, all 2,048 hyperspace arrivals with turns made while
the station is dormant, and that every path which does not switch the
station on is unchanged.

--emulator also loads release/elite-128k.tap through the 48K ROM
(tools/emulator_check.py), flies Lave -> Diso with a pitch turn and the
galactic jump to LEMAED, then moves sun, planet and station together next to
the player with a test-only poke, so that the real main loop switches the
station on.  Build the option with the default tapfile for this mode.
"""
import argparse
import json
import math
import random
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/station-slot-fix-check'
PARTS = (('StationSwitchOnStoreStart', 'StationSwitchOnStoreLimit'),
         ('StationSlotAlignStart', 'StationSlotAlignLimit'),
         ('StationSlotRoofStart', 'StationSlotRoofLimit'),
         ('StationSlotFinishStart', 'StationSlotFinishLimit'))
AXIS_Z, AXIS_Y, AXIS_X = 0x09, 0x0F, 0x15     # InstanceAxisZ/Y/X
ENERGY, ROLE = 0x22, 0x26                      # InstanceEnergy, InstanceRoleFlags
NEAR = 0x10000                                  # switch-on: every |coordinate| below this
MAX_SLOT_ERROR = 3.0                            # degrees at the switch-on: the planet direction is
                                                # resolved in units of 512, so short distances are coarser
MAX_NOMINAL_ERROR = 1.0                         # from $10000 up (the arrival distance is $18000)
IY_SENTINEL = 0x5A3C


class ImageContext(cr.Context):
    """check_routines.Context for an arbitrary image of the current build."""

    def __init__(self, symbols, image):
        self.symbols = symbols
        self.image = bytes(image)
        self.rom = (ROOT / 'assets/zxspectrum48k.rom').read_bytes()
        assert len(self.rom) == cr.ROM_SIZE
        base = symbols['GameImage']
        memory = list(self.rom) + [0] * (cr.RAM_TOP - cr.ROM_SIZE)
        memory[base:base + len(image)] = image
        self.pristine = tuple(memory)
        self.test_stack = symbols['FontRuntime'] - 0x80
        self.upper_stack = cr.RAM_TOP - 0x10
        self.scratch = self.test_stack + 0x10


def sm8(value):
    return -(value & 0x7F) if value & 0x80 else value


def axis(m, station, offset):
    return [sm8(m.memory[station + offset + 2 * i + 1]) for i in range(3)]


def position(m, base):
    return [cr.get24(m.memory, base + 3 * i) for i in range(3)]


def angle(u, v):
    cosine = sum(a * b for a, b in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def cross(u, v):
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]


def put_axis(m, station, offset, vector):
    for i, value in enumerate(vector):
        m.memory[station + offset + 2 * i] = 0
        m.memory[station + offset + 2 * i + 1] = min(abs(value), 127) | (0x80 if value < 0 else 0)


def random_frame(rng):
    """A right-handed orthonormal frame (Z, Y, X) in the game's 127 scale."""
    while True:
        z = [rng.gauss(0, 1) for _ in range(3)]
        y = [rng.gauss(0, 1) for _ in range(3)]
        nz = math.hypot(*z)
        z = [c / nz for c in z]
        dot = sum(a * b for a, b in zip(y, z))
        y = [a - dot * b for a, b in zip(y, z)]
        ny = math.hypot(*y)
        if ny > 0.2:
            y = [c / ny for c in y]
            x = cross(y, z)
            return [[round(127 * c) for c in v] for v in (z, y, x)]


class Checker:
    def __init__(self):
        self.symbols = symbol_map(ROOT / 'build/game.map')
        s = self.symbols
        assert s.get('STATION_SLOT_FIX') == 1, 'Build stationslotfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        original = reference()[1][5].payload
        self.parts = [(s[a], s[b]) for a, b in PARTS]
        assert [(a, b) for a, b in self.parts] == [(0x77CB, 0x77CE), (0xE88B, 0xE8CF),
                                                    (0xAC56, 0xAC77), (0xFCED, 0xFD00)], self.parts
        assert (s['StationSlotAlign'], s['StationSlotRoof'], s['StationSlotFinish']) == \
            tuple(start for start, _ in self.parts[1:])
        baseline = bytearray(self.image)
        for start, end in self.parts:
            baseline[start - self.base:end - self.base] = original[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = ImageContext(s, self.image)
        self.original = ImageContext(s, self.baseline)
        self.station = s['InitialRuntimeState']
        self.planet = s['PlanetPosition']
        self.sun = s['SunPosition']
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image),
                           replaced_bytes=sum(end - start for start, end in self.parts))

    def outside_parts(self, memory):
        data = bytearray(memory[self.base:self.base + len(self.image)])
        for start, end in self.parts:
            data[start - self.base:end - self.base] = bytes(end - start)
        return bytes(data)

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        assert changed and all(any(start <= a < end for start, end in self.parts) for a in changed)
        assert self.outside_parts(self.fixed.pristine) == self.outside_parts(self.original.pristine)
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside the four replaced areas.', flush=True)

    # -- one switch-on --------------------------------------------------------------
    def prepare(self, m, station_pos, planet_pos, frame):
        m.reset()
        for i in range(3):
            cr.put24(m.memory, self.station + 3 * i, station_pos[i])
            cr.put24(m.memory, self.planet + 3 * i, planet_pos[i])
        for offset, vector in zip((AXIS_Z, AXIS_Y, AXIS_X), frame):
            put_axis(m, self.station, offset, vector)
        m.poke('StationDormantFlag', 0xFF)
        m.poke(self.station + ENERGY, 0)
        m.poke('PlayerRoll', 0)
        m.poke('PlayerPitch', 0)
        m.poke('PlayerSpeed', 0)
        m.poke('ObjectLoopCounter', 8)

    def switch_on(self, m):
        m.call('UpdateStationDormancy', iy=IY_SENTINEL, ix=0, **cr.ZERO_REGISTERS)
        assert m.byte('StationDormantFlag') == 0 and m.byte(self.station + ENERGY) == 0xF0
        assert m.iy() == IY_SENTINEL and m.ix() == self.station
        z = axis(m, self.station, AXIS_Z)
        y = axis(m, self.station, AXIS_Y)
        x = axis(m, self.station, AXIS_X)
        d = [p - q for p, q in zip(position(m, self.planet), position(m, self.station))]
        error = angle(z, d)
        assert error < MAX_SLOT_ERROR, ('slot error', error, z, d)
        assert 120 <= math.hypot(*z) <= 129, z
        # OrthogonaliseYVector assumes |Z| = 128; the per-frame call in UpdateObjects
        # removes the small remainder (checked after the active frames).
        assert math.hypot(*y) >= 95 and abs(angle(y, z) - 90) < 6, (y, z)
        assert abs(angle(x, y) - 90) < 6 and abs(angle(x, z) - 90) < 6, (x, y, z)
        assert sum(a * b for a, b in zip(x, cross(y, z))) > 0, 'left-handed frame'
        return error, z

    def active_frames(self, m, frames):
        for _ in range(frames):
            m.call('MoveSunAndPlanet', **cr.ZERO_REGISTERS)
            m.call('UpdateStationDormancy', **cr.ZERO_REGISTERS)
            m.call('L_DB8B', stop='L_DBA3', ix=self.station, iy=m.word(self.station + 0x23),
                   **cr.ZERO_REGISTERS)

    def check_geometries(self):
        rng = random.Random(0x5107)
        cases, branches, worst, worst_after = [], {'y': 0, 'x': 0, 'z': 0}, 0.0, 0.0
        worst_nominal = worst_nominal_after = 0.0   # |d| of $10000 or more
        for axis_index in range(3):
            for sign in (1, -1):
                for length in (0x6000, 0x18000, 0x60000):
                    d = [0, 0, 0]
                    d[axis_index] = sign * length
                    cases.append(d)
                    tilted = list(d)
                    tilted[(axis_index + 1) % 3] = sign * length // 9
                    cases.append(tilted)
        while len(cases) < 3036:
            length = rng.uniform(0x6000, 0x60000)
            v = [rng.gauss(0, 1) for _ in range(3)]
            n = math.hypot(*v)
            cases.append([round(length * c / n) for c in v])
        m = self.fixed.machine()
        for index, d in enumerate(cases):
            station_pos = [rng.randint(-0xFFE0, 0xFFE0) for _ in range(3)]
            planet_pos = [a + b for a, b in zip(station_pos, d)]
            self.prepare(m, station_pos, planet_pos, random_frame(rng))
            error, z = self.switch_on(m)
            worst = max(worst, error)
            if math.hypot(*d) >= 0x10000:
                worst_nominal = max(worst_nominal, error)
            branches['y' if abs(z[1]) < 0x50 else 'x' if abs(z[0]) < 0x50 else 'z'] += 1
            if index % 12 == 0:
                self.active_frames(m, 8)
                z = axis(m, self.station, AXIS_Z)
                y = axis(m, self.station, AXIS_Y)
                d = [p - q for p, q in zip(position(m, self.planet), position(m, self.station))]
                worst_after = max(worst_after, angle(z, d))
                if math.hypot(*d) >= 0x10000:
                    worst_nominal_after = max(worst_nominal_after, angle(z, d))
                assert all(118 <= math.hypot(*v) <= 134 for v in (z, y)), (z, y)
                assert abs(angle(y, z) - 90) < 3, (y, z)
        assert all(branches.values()), branches
        assert worst_after < MAX_SLOT_ERROR and worst_nominal_after < 1.5, (worst_after, worst_nominal_after)
        assert worst_nominal < MAX_NOMINAL_ERROR, worst_nominal
        self.report['switch_on_geometries'] = dict(cases=len(cases), worst_slot_error_degrees=round(worst, 3),
                                                   worst_for_distance_10000_or_more=round(worst_nominal, 3),
                                                   roof_axis_choices=branches,
                                                   worst_after_8_active_frames=round(worst_after, 3),
                                                   worst_after_8_active_frames_from_10000=round(worst_nominal_after, 3))
        print(f'PASS: {len(cases)} switch-on geometries, worst slot error {worst:.2f} deg '
              f'({worst_nominal:.2f} deg from $10000 up); '
              f'roof axis y/x/z {branches["y"]}/{branches["x"]}/{branches["z"]}; '
              f'8 active frames keep it below {worst_after:.2f} deg.', flush=True)

    # -- all hyperspace arrivals ----------------------------------------------------
    def systems(self):
        gen = self.original.machine()
        seeds = []
        for galaxy in range(8):
            gen.reset()
            cr.load_jameson(gen)
            galaxy_seeds = [gen.memory[self.symbols['GalaxySeeds'] + i] for i in range(6)]
            for _ in range(galaxy):
                galaxy_seeds = [((b << 1) | (b >> 7)) & 0xFF for b in galaxy_seeds]
            gen.poke('GalaxySeeds', *galaxy_seeds)
            gen.call('LoadGalaxySeedsToGenerator', **cr.ZERO_REGISTERS)
            for _ in range(256):
                gen.call('DeriveSelectedSystemData', **cr.ZERO_REGISTERS)
                gen.call('GenerateSystemName', **cr.ZERO_REGISTERS)
                seeds.append((galaxy, [gen.memory[self.symbols['SelectedSystemSeeds'] + i] for i in range(6)]))
        return seeds

    def fly(self, context, galaxy, seeds, turns):
        m = context.machine()
        cr.load_jameson(m)
        m.poke('CurrentGalaxy', galaxy)
        m.poke('SelectedSystemSeeds', *seeds)
        m.call('ArriveInTargetSystem', stop='L_D7B4', limit=500_000, halt=True, **cr.FRESH_REGISTERS)
        arrival = angle(axis(m, self.station, AXIS_Z),
                        [p - q for p, q in zip(position(m, self.planet), position(m, self.station))])
        m.poke('PlayerSpeed', 0)
        m.poke('ObjectLoopCounter', 8)
        for roll, pitch in turns:
            m.poke('PlayerRoll', roll)
            m.poke('PlayerPitch', pitch)
            m.call('MoveSunAndPlanet', **cr.ZERO_REGISTERS)
            m.call('UpdateStationDormancy', **cr.ZERO_REGISTERS)
        assert m.byte('StationDormantFlag') == 0xFF, 'the station must still be dormant'
        # Fly to the station: move sun, planet and station together.
        station_pos = position(m, self.station)
        offset = [t - s for t, s in zip((0x2000, -0x1000, 0x8000), station_pos)]
        for body in (self.station, self.planet, self.sun):
            for i, value in enumerate(position(m, body)):
                cr.put24(m.memory, body + 3 * i, value + offset[i])
        m.poke('PlayerRoll', 0)
        m.poke('PlayerPitch', 0)
        m.call('MoveSunAndPlanet', **cr.ZERO_REGISTERS)
        m.call('UpdateStationDormancy', iy=IY_SENTINEL, **cr.ZERO_REGISTERS)
        assert m.byte('StationDormantFlag') == 0 and m.iy() == IY_SENTINEL
        d = [p - q for p, q in zip(position(m, self.planet), position(m, self.station))]
        return arrival, angle(axis(m, self.station, AXIS_Z), d)

    def check_arrivals(self):
        rng = random.Random(0xA221)
        fixed_worst, original_errors, arrival_away = 0.0, [], 0
        for index, (galaxy, seeds) in enumerate(self.systems()):
            turns = [(rng.choice((0, 1, 4, 8, 15)) | rng.choice((0, 0x80)),
                      rng.choice((0, 1, 3, 8)) | rng.choice((0, 0x80))) for _ in range(12)]
            arrival, fixed = self.fly(self.fixed, galaxy, seeds, turns)
            fixed_worst = max(fixed_worst, fixed)
            arrival_away += arrival > 90
            if index % 4 == 0:
                original_errors.append((arrival, self.fly(self.original, galaxy, seeds, turns)[1]))
        assert arrival_away == 464, arrival_away
        assert fixed_worst < MAX_NOMINAL_ERROR, fixed_worst
        # The original keeps every reversed slot and adds the dormant turns to the others.
        assert all(after > 90 for arrival, after in original_errors if arrival > 90)
        turned = sum(arrival < 1 and after > 10 for arrival, after in original_errors)
        assert turned > 0
        original_errors = [after for _, after in original_errors]
        self.report['arrivals'] = dict(
            systems=2048, reversed_at_arrival=arrival_away, turns_while_dormant=12,
            fixed_worst_slot_error_degrees=round(fixed_worst, 3),
            original_sample=len(original_errors),
            original_slot_error_over_10_degrees=sum(e > 10 for e in original_errors),
            original_turned_away_from_a_correct_arrival=turned,
            original_mean_slot_error_degrees=round(sum(original_errors) / len(original_errors), 1))
        print(f'PASS: all 2048 arrivals (464 reversed by the original arrival code) with 12 turned frames; '
              f'fixed slot error at most {fixed_worst:.2f} deg; original over 10 deg in '
              f'{self.report["arrivals"]["original_slot_error_over_10_degrees"]} of {len(original_errors)} '
              f'sampled systems.', flush=True)

    # -- paths that do not switch the station on ------------------------------------
    def check_unchanged_paths(self):
        rng = random.Random(0x0FF)
        cases = 0
        for kind in ('far', 'blocked', 'active'):
            for _ in range(200):
                station_pos = [rng.randint(-0xFFE0, 0xFFE0) for _ in range(3)]
                if kind == 'far':
                    station_pos[rng.randrange(3)] = rng.choice((1, -1)) * rng.randint(0x10000, 0x7C0000)
                planet_pos = [a + rng.randint(-0x20000, 0x20000) for a in station_pos]
                frame = random_frame(rng)
                turn = (rng.randint(0, 15) | rng.choice((0, 0x80)), rng.randint(0, 15) | rng.choice((0, 0x80)))
                outcomes = []
                for context in (self.fixed, self.original):
                    m = context.machine()
                    self.prepare(m, station_pos, planet_pos, frame)
                    m.poke('PlayerRoll', turn[0])
                    m.poke('PlayerPitch', turn[1])
                    if kind == 'blocked':
                        m.poke(self.station + ROLE, m.byte(self.station + ROLE) | 0x80)
                    if kind == 'active':
                        m.poke('StationDormantFlag', 0)
                        m.poke(self.station + ENERGY, 0xF0)
                    m.call('UpdateStationDormancy', iy=IY_SENTINEL, **cr.ZERO_REGISTERS)
                    outcomes.append((self.outside_parts(m.memory), m.ix(), m.iy()))
                assert outcomes[0] == outcomes[1], (kind, station_pos)
                cases += 1
        self.report['unchanged_paths'] = cases
        print(f'PASS: {cases} far, blocked (+$26 bit 7) and already active cases leave RAM and IX/IY '
              'exactly as the original.', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        report = OUTPUT / 'verification.json'
        report.unlink(missing_ok=True)
        self.check_layout()
        self.check_unchanged_paths()
        self.check_geometries()
        self.check_arrivals()
        report.write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n', encoding='utf-8')


# -- 48K emulator, ROM load and real main loop ------------------------------------------
def emulator(symbols):
    sys.path.insert(0, str(ROOT / 'tools'))
    import run_runtime_scenarios as rs
    image = (ROOT / 'build/game.bin').read_bytes()
    tape_payload = parse(RELEASE_TAP.read_bytes())[5].payload
    assert bytes(tape_payload) == image, 'Build the option with the default tapfile first'
    station, planet, sun = symbols['InitialRuntimeState'], symbols['PlanetPosition'], symbols['SunPosition']

    def drop(args, start, key):
        out, i = [], 0
        while i < len(args):
            spec = args[i + 1] if args[i] == '--key' else ''
            if spec.startswith(f'{start}:') and spec.endswith(f':{key}'):
                i += 2
                continue
            out.append(args[i])
            i += 1
        return out

    def seconds(args, value):
        args = list(args)
        args[args.index('--seconds') + 1] = str(value)
        return args

    diso = seconds(drop(rs.select_planet_and_jump('Diso'), 46, 'L'), 50) + rs.key(47, 1.0, 'S')
    lemaed = seconds(drop(rs.SCENARIOS['galactic-hyperspace-overlap'], 43, 'L'), 80)
    lemaed += [*rs.key(45, 0.3, 'I'), *rs.key(47, 0.3, 'R')]
    second = 48.0
    for character in 'LEMAED':
        lemaed += rs.key(f'{second:.2f}', 0.18, character)
        second += 0.45
    lemaed += [*rs.key(f'{second:.2f}', 0.25, 'ENTER'), *rs.key(53, 0.3, '1'), *rs.key(55, 0.4, 'H')]

    def run(name, args):
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
        assert report['machine'] == 'ZX Spectrum 48K'
        return (ROOT / f'build/emulator/{name}-memory.bin').read_bytes(), report

    def slot(memory):
        z = [sm8(memory[station + AXIS_Z + 2 * i + 1]) for i in range(3)]
        def pos(base):
            out = []
            for i in range(3):
                a = base + 3 * i
                magnitude = memory[a] | memory[a + 1] << 8 | (memory[a + 2] & 0x7F) << 16
                out.append(-magnitude if memory[a + 2] & 0x80 else magnitude)
            return out
        return angle(z, [p - q for p, q in zip(pos(planet), pos(station))]), pos

    def encode(value):
        magnitude = abs(value)
        assert magnitude < 1 << 23
        return bytes([magnitude & 255, magnitude >> 8 & 255, magnitude >> 16 | (0x80 if value < 0 else 0)])

    results = {}
    for name, args, end in (('station-slot-diso', diso, 50), ('station-slot-lemaed', lemaed, 80)):
        memory, _ = run(name + '-before', args)
        before, pos = slot(memory)
        assert memory[symbols['StationDormantFlag']] == 0xFF, name
        offset = [t - s for t, s in zip((0x1000, -0x800, 0x8000), pos(station))]
        pokes = []
        for body in (station, planet, sun):
            data = b''.join(encode(v + o) for v, o in zip(pos(body), offset))
            pokes += ['--poke', f'{end}:{body:#06x}:{data.hex()}']
        memory, report = run(name, seconds(args, end + 4) + pokes)
        assert all(p['applied'] for p in report['test_pokes'])
        after, _ = slot(memory)
        assert memory[symbols['StationDormantFlag']] == 0 and memory[station + ENERGY] != 0, name
        assert after < 2.0, (name, after)
        results[name] = dict(slot_error_before_switch_on=round(before, 1),
                             slot_error_after_switch_on=round(after, 2),
                             final_text=[row['text'].strip() for row in report['final_text'][:3]])
        print(f'PASS: {name}: dormant slot error {before:.1f} deg, after the real switch-on {after:.2f} deg.',
              flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenarios')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker.symbols)
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **checker.report), indent=2) + '\n',
                                                  encoding='utf-8')


if __name__ == '__main__':
    main()
