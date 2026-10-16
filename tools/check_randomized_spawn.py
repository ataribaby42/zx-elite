"""Check randomizedspawn=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat randomizedspawn=yes verify=no
    python tools/check_randomized_spawn.py
    python tools/check_randomized_spawn.py --emulator

The option lets a single ship of a random encounter take the calm placement (ahead,
x and y high bytes 0..7) or the hostile one (a diagonal corner, high bytes $32) at
random instead of by its hostility.  The simulator part runs the assembled image
with the supplied 48K ROM in SkoolKit's Z80 simulator against a baseline in which
the five parts are restored from the reference tape:

- only the five declared parts differ, at their original addresses;
- InitialiseShipFromBlueprint without the request, as every caller but the
  encounter path calls it: all blueprint IDs, 1,024 RNG states each, with ID bit 6
  clear and set and a garbage-filled slot.  The instance, every register, the flags
  and the RNG state equal the original's;
- with the request: every byte from z on equals the original's, and x and y follow
  a model of the loader: one extra NextRandomByte whose bit 3 XOR the hostility
  selects the corner, then the original draws of the selected placement;
- SpawnRandomEncounter for all 65,536 RNG states in each of the 8 governments, and
  4,096 states each for the two mission states that force a ship: the same objects
  in the same slots.  Groups, asteroids, the Rock hermit and no encounter are
  identical byte for byte, including the RNG state; a single ship is identical apart
  from x, y and the ECM bit (its ECM byte is drawn later).  The share of corner
  placements per ship type and government is reported and bounded;
- the special Asp encounter and full slots are identical byte for byte.

--emulator loads release/elite-128k.tap through the 48K ROM (tools/emulator_check.py),
launches, jumps to Diso and, after the arrival, pokes the RNG state and the encounter
counter (test-only pokes) so that the next object update creates a predicted
encounter: a calm ship in a corner and a hostile ship ahead, which the original
places the other way round.  Build the option with the default tapfile for this mode.
"""
import argparse
from collections import Counter, defaultdict
import json
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/randomized-spawn-check'
# Part constant prefix in src/options.asm -> original [start, limit).
PARTS = {
    'RandomizedSpawnIdPush': (0xF2FE, 0xF2FF),
    'RandomizedSpawnPlacement': (0xF338, 0xF356),
    'RandomizedSpawnAspEntry': (0xF653, 0xF655),
    'RandomizedSpawnRequest': (0xF6C8, 0xF6DB),
    'RandomizedSpawnHermit': (0xF6FB, 0xF70E),
}
REQUEST = 0x80                      # ID bit 7: ask for the random placement
HOSTILE = 0x04                      # InstanceBehaviour bit 2
CENTRE_HIGH_LIMIT = 8               # calm placement: high bytes 0..7
ECM = 0x01                          # InstanceAiState bit 0
ASTEROID, HERMIT, THARGOID = 6, 7, 15
SINGLE_SHIPS = {8: 'Viper', 9: 'Cobra trader', 10: 'Python trader', 11: 'Python pirate',
                12: 'Cobra pirate', 13: 'Asp Mk II', 14: 'Fer-de-Lance', 15: 'Thargoid'}
LOADER_SEEDS = 1024
MISSION_SEEDS = 4096
# Bounds on the corner share of one ship type in one government.  The RNG is weak
# (each byte depends on the low bits of the two before it), so the bit after the
# type choice is not perfectly even; the Thargoid is exempt, its shape gives it away.
MIN_SAMPLES, LOW, HIGH = 100, 0.30, 0.70


def next_random(seed, carry):
    """NextRandomByte: (new seed, returned byte, carry out)."""
    high, low = seed >> 8, seed & 255
    t = 2 * high + carry
    s = (t & 255) + low + (t >> 8)
    return (s & 255) << 8 | (t & 255), s & 255, s >> 8


def model_position(seed, corner, corner_high):
    """x/y bytes and final seed of a requested placement (the loader's draws after the extra one)."""
    seed, value, _ = next_random(seed, 1)          # the request draw: carry 1 from ADD A,A
    if corner:
        high_x = high_y = corner_high
    else:
        seed, value, _ = next_random(seed, 0)      # AND LoaderHostileMask left carry clear
        high_x = value & 7
        seed, value, _ = next_random(seed, 0)      # AND 7 clears it again
        high_y = value & 7
    seed, low_x, carry = next_random(seed, 0)
    seed, low_y, carry = next_random(seed, carry)
    seed, signs, carry = next_random(seed, carry)
    return [low_x, high_x, (signs & 1) << 7, low_y, high_y, (signs & 2) << 6], seed


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('RANDOMIZED_SPAWN') == 1, 'Build randomizedspawn=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        reference_payload = reference()[1][5].payload
        baseline = bytearray(self.image)
        for start, end in PARTS.values():
            baseline[start - self.base:end - self.base] = reference_payload[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.size = s['InstanceSize']
        self.slots = [s['InitialRuntimeState'] + n * self.size for n in range(s['InstanceSlotCount'])]
        self.corner_high = self.image[s['ShipInstanceTemplate'] + s['InstanceX'] + 1 - self.base]
        self.others = sorted(name for name in cr.OPTION_SYMBOLS if name != 'RANDOMIZED_SPAWN' and s.get(name))
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image), other_options=self.others)

    # ------------------------------------------------------------------ helpers
    def slot_bytes(self, m, slot):
        return bytes(m.memory[self.slots[slot]:self.slots[slot] + self.size])

    def registers(self, m):
        return (m.reg('a'), m.reg('f'), m.pair('bc'), m.pair('de'), m.pair('hl'), m.ix(), m.iy())

    def blueprint_ids(self):
        """Blueprint pointer -> ID and ID -> behaviour, from the loader itself (either ship layout)."""
        m = self.original.machine()
        ids, behaviour = {}, {}
        for ident in range(self.symbols['ShipBlueprintCount']):
            m.call('InitialiseShipFromBlueprint', **dict(cr.ZERO_REGISTERS, a=ident, ix=self.slots[1]))
            ids[m.word(self.slots[1] + cr.INSTANCE_BLUEPRINT)] = ident
            behaviour[ident] = m.byte(self.slots[1] + self.symbols['InstanceBehaviour'])
        assert len(ids) == self.symbols['ShipBlueprintCount']
        return ids, behaviour

    # ------------------------------------------------------------------ checks
    def check_layout(self):
        s = self.symbols
        for prefix, original in PARTS.items():
            assert (s[prefix + 'Start'], s[prefix + 'Limit']) == original, prefix
        for name, address in (('InitialiseShipFromBlueprint', 0xF2FB), ('RandomiseShipLowBytesAndSigns', 0xF366),
                              ('SaveEncounterShipId', 0xF6C7), ('InitialiseEncounterShip', 0xF6C8),
                              ('SelectEncounterTraderType', 0xF6FD), ('L_F70E', 0xF70E)):
            assert s[name] == address, name
        assert self.corner_high == 0x32
        changed = sum(a != b for a, b in zip(self.image, self.baseline))
        assert changed, 'the option changed nothing'
        if not self.others:
            # The baseline differs from the option build only inside the five parts.
            assert self.baseline == reference()[1][5].payload, 'bytes outside the five parts changed'
        self.report['changed_bytes'] = changed
        print(f'PASS: {changed} bytes changed, all inside the five parts; the loader, InitialiseEncounterShip '
              'and the trader choice keep their addresses.', flush=True)

    def check_rng_model(self):
        m = self.fixed.machine()
        for k in range(512):
            seed, carry = (k * 40503 + 7) & 0xFFFF, k & 1
            m.poke_word('RandomSeed', seed)
            m.call('NextRandomByte', a=0, f=carry, bc=0, de=0, hl=0)
            new, value, out = next_random(seed, carry)
            assert (m.word('RandomSeed'), m.reg('a'), m.carry()) == (new, value, out), (seed, carry)
        print('PASS: the NextRandomByte model matches the simulator (512 states).', flush=True)

    def loader_call(self, context, ident, seed, entry_flags, garbage):
        m = context.machine()
        m.poke_word('RandomSeed', seed)
        m.poke(self.slots[1], *garbage)
        m.call('InitialiseShipFromBlueprint', a=ident, f=entry_flags, bc=0x1234 ^ seed, de=0xBEEF,
               hl=seed ^ 0x5A5A, ix=self.slots[1], iy=0x4321)
        return m

    def check_loader(self):
        ids, behaviour = self.blueprint_ids()
        unrequested = requested = 0
        corners = Counter()
        for ident in range(self.symbols['ShipBlueprintCount']):
            for k in range(LOADER_SEEDS):
                seed = (k * 40503 + ident * 977 + 11) & 0xFFFF
                garbage = [(seed * (n + 3) + n * 29) & 255 for n in range(self.size)]
                flags = (k * 37) & 255
                for bit6 in (0, 0x40):
                    fixed = self.loader_call(self.fixed, ident | bit6, seed, flags, garbage)
                    original = self.loader_call(self.original, ident | bit6, seed, flags, garbage)
                    assert self.slot_bytes(fixed, 1) == self.slot_bytes(original, 1), (ident, bit6, seed)
                    assert self.registers(fixed) == self.registers(original), (ident, bit6, seed)
                    assert fixed.word('RandomSeed') == original.word('RandomSeed'), (ident, bit6, seed)
                    unrequested += 1
                fixed = self.loader_call(self.fixed, ident | REQUEST, seed, flags, garbage)
                original = self.loader_call(self.original, ident, seed, flags, garbage)
                got, want = self.slot_bytes(fixed, 1), self.slot_bytes(original, 1)
                assert got[6:] == want[6:], (ident, seed, 'bytes from z on')
                assert self.registers(fixed) == self.registers(original), (ident, seed, 'registers')
                hostile = bool(behaviour[ident] & HOSTILE)
                corner = bool((next_random(seed, 1)[1] >> 3) & 1) != hostile
                position, final_seed = model_position(seed, corner, self.corner_high)
                assert list(got[:6]) == position, (ident, seed, list(got[:6]), position)
                assert fixed.word('RandomSeed') == final_seed, (ident, seed, 'RNG state')
                corners[ident] += corner
                requested += 1
        shares = {ident: corners[ident] / LOADER_SEEDS for ident in corners}
        assert all(0.4 <= share <= 0.6 for share in shares.values()), shares
        self.report['loader'] = dict(unrequested_calls=unrequested, requested_calls=requested,
                                     corner_share_by_id={str(i): round(v, 3) for i, v in shares.items()})
        print(f'PASS: InitialiseShipFromBlueprint: {unrequested:,} calls without the request (19 IDs, ID bit 6 '
              f'clear and set) equal the original in every byte, register and the RNG state; {requested:,} '
              'requested calls follow the model (bit 3 of one extra draw XOR the hostility).', flush=True)

    def encounter_run(self, m, pristine, seed, government, mission_state=3, invasion=0, full=False):
        s = self.symbols
        m.memory[self.slots[0]:self.slots[-1] + self.size] = pristine
        m.poke_word('RandomSeed', seed)
        m.poke('CurrentGovernment', government)
        m.poke('MissionAspEncounterState', mission_state)
        m.poke('InvasionMissionState', invasion)
        m.poke('CommanderFlags', 0x02)
        if full:
            for slot in range(1, 7):
                m.poke(self.slots[slot] + s['InstanceEnergy'], 1)
        draws = [0]
        m.call('SpawnRandomEncounter', hooks={'NextRandomByte': lambda mm: draws.__setitem__(0, draws[0] + 1)},
               **cr.ZERO_REGISTERS)
        return draws[0]

    def created(self, m, ids):
        energy, blueprint = self.symbols['InstanceEnergy'], cr.INSTANCE_BLUEPRINT
        return [(slot, ids[m.word(self.slots[slot] + blueprint)]) for slot in range(1, 7)
                if m.byte(self.slots[slot] + energy)]

    def check_encounters(self):
        ids, behaviour = self.blueprint_ids()
        machines = {'fixed': self.fixed.machine(), 'original': self.original.machine()}
        pristine = {k: list(m.memory[self.slots[0]:self.slots[-1] + self.size]) for k, m in machines.items()}
        clean = {k: list(m.memory) for k, m in machines.items()}
        variables = ('RandomSeed', 'CurrentGovernment', 'MissionAspEncounterState', 'InvasionMissionState',
                     'CommanderFlags')
        stats = defaultdict(lambda: [0, 0])          # (government, ID) -> [ships, corners]
        ecm = Counter()
        outcomes = Counter()
        runs = 0

        def run_both(seed, government, **kwargs):
            nonlocal runs
            results = {}
            for name, m in machines.items():
                draws = self.encounter_run(m, pristine[name], seed, government, **kwargs)
                results[name] = (m, draws)
            runs += 1
            fixed, fixed_draws = results['fixed']
            original, original_draws = results['original']
            region = (self.slots[1], self.slots[-1] + self.size)
            if kwargs.get('full'):
                assert fixed.memory[region[0]:region[1]] == original.memory[region[0]:region[1]], (seed, 'full')
                assert fixed.word('RandomSeed') == original.word('RandomSeed') and fixed_draws == original_draws
                outcomes['full slots'] += 1
                return results
            made = self.created(original, ids)
            assert self.created(fixed, ids) == made, (seed, government, kwargs)
            if len(made) == 1 and made[0][1] in SINGLE_SHIPS:
                slot, ident = made[0]
                got, want = self.slot_bytes(fixed, slot), self.slot_bytes(original, slot)
                ai = self.symbols['InstanceAiState']
                assert got[6:ai] == want[6:ai] and got[ai] & ~ECM == want[ai] & ~ECM \
                    and got[ai + 1:] == want[ai + 1:], (seed, government, ident)
                assert got[2] in (0, 0x80) and got[5] in (0, 0x80)
                high = (got[1], got[4])
                corner = high == (self.corner_high, self.corner_high)
                assert corner or max(high) < CENTRE_HIGH_LIMIT, (seed, government, ident, high)
                original_corner = (want[1], want[4]) == (self.corner_high, self.corner_high)
                assert original_corner == bool(behaviour[ident] & HOSTILE)
                assert fixed_draws == original_draws + 1 + 2 * (not corner) - 2 * (not original_corner), \
                    (seed, government, ident, fixed_draws, original_draws)
                for other in range(1, 7):
                    if other != slot:
                        assert self.slot_bytes(fixed, other) == self.slot_bytes(original, other)
                stats[government, ident][0] += 1
                stats[government, ident][1] += corner
                ecm['fixed'] += bool(got[ai] & ECM)
                ecm['original'] += bool(want[ai] & ECM)
                outcomes[SINGLE_SHIPS[ident]] += 1
            else:
                assert fixed.memory[region[0]:region[1]] == original.memory[region[0]:region[1]], \
                    (seed, government, kwargs, made)
                assert fixed.word('RandomSeed') == original.word('RandomSeed'), (seed, government, kwargs)
                assert fixed_draws == original_draws
                kinds = sorted({ident for _, ident in made})
                key = ('none' if not made else 'Asteroid' if kinds == [ASTEROID] else
                       'Rock hermit' if kinds == [HERMIT] else 'group ' + '/'.join(map(str, kinds)))
                outcomes[key] += 1
            return results

        def check_untouched():
            """Every byte the runs did not restore must still be the clean image."""
            for name, m in machines.items():
                memory = list(m.memory)
                memory[self.slots[0]:self.slots[-1] + self.size] = clean[name][self.slots[0]:self.slots[-1] + self.size]
                for variable in variables:
                    address = self.symbols[variable]
                    width = 2 if variable == 'RandomSeed' else 1
                    memory[address:address + width] = clean[name][address:address + width]
                top = self.fixed.test_stack
                memory[top - 64:top] = clean[name][top - 64:top]
                assert memory == clean[name], (name, 'unexpected write',
                                               [hex(a) for a, (x, y) in enumerate(zip(memory, clean[name]))
                                                if x != y][:8])

        for government in range(8):
            for seed in range(65536):
                run_both(seed, government)
            check_untouched()
            print(f'  government {government}: 65,536 RNG states', flush=True)
        for invasion in (1, 4):
            for k in range(MISSION_SEEDS):
                run_both((k * 16 + 3) & 0xFFFF, k & 7, invasion=invasion)
        special = 0
        for k in range(MISSION_SEEDS):
            results = run_both((k * 16 + 5) & 0xFFFF, k & 7, mission_state=0)
            special += any(ident == 13 for _, ident in self.created(results['original'][0], ids))
        assert special > MISSION_SEEDS // 2, special
        for k in range(MISSION_SEEDS):
            run_both((k * 16 + 9) & 0xFFFF, k & 7, full=True)
        check_untouched()

        shares, violations = {}, []
        for (government, ident), (ships, corners) in sorted(stats.items()):
            share = corners / ships
            shares.setdefault(SINGLE_SHIPS[ident], {})[str(government)] = dict(ships=ships, corner=round(share, 3))
            if ident != THARGOID and ships >= MIN_SAMPLES and not LOW <= share <= HIGH:
                violations.append((government, SINGLE_SHIPS[ident], ships, share))
        assert not violations, violations
        total = sum(v[0] for v in stats.values())
        corner_total = sum(v[1] for v in stats.values())
        assert 0.45 <= corner_total / total <= 0.55, corner_total / total
        by_type = {}
        for (government, ident), (ships, corners) in stats.items():
            entry = by_type.setdefault(SINGLE_SHIPS[ident], [0, 0])
            entry[0] += ships
            entry[1] += corners
        self.report['encounters'] = dict(
            runs_per_image=runs, outcomes=dict(sorted(outcomes.items())), single_ships=total,
            corner_share=round(corner_total / total, 3),
            corner_share_by_type={k: round(c / n, 3) for k, (n, c) in sorted(by_type.items())},
            corner_share_by_type_and_government=shares, special_asp_encounters=special,
            ecm_share=dict(fixed=round(ecm['fixed'] / total, 3), original=round(ecm['original'] / total, 3)))
        worst = max((abs(c / n - 0.5), name) for name, (n, c) in by_type.items() if name != 'Thargoid')
        print(f'PASS: SpawnRandomEncounter, {runs:,} runs per image: the same objects in the same slots; '
              f'no encounter, asteroids, groups, the Rock hermit, the special Asp and full slots identical '
              f'byte for byte with the RNG state; {total:,} single ships differ only in x, y and the ECM bit.',
              flush=True)
        print(f'      corner share {corner_total / total:.3f} overall; by type '
              + ', '.join(f'{k} {c / n:.2f}' for k, (n, c) in sorted(by_type.items()))
              + f' (largest deviation without the Thargoid: {worst[0]:.3f}, {worst[1]}); ECM '
              f'{ecm["fixed"] / total:.3f} (original {ecm["original"] / total:.3f}).', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_rng_model()
        self.check_loader()
        self.check_encounters()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenario')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker)
    checker.write()


ARRIVAL_SECONDS = 36        # Diso reached, arrival tunnel over, no station present
EMULATOR_SECONDS = 37       # ten object updates after the pokes


def single_encounter(checker, context, seed, ids):
    """SpawnRandomEncounter from the RAM of context with RandomSeed = seed:
    (ID, hostile, corner) of a single ship, or None."""
    m = context.machine()
    m.poke_word('RandomSeed', seed)
    m.call('SpawnRandomEncounter', **cr.ZERO_REGISTERS)
    made = checker.created(m, ids)
    if len(made) != 1 or made[0][1] not in SINGLE_SHIPS:
        return None
    slot, ident = made[0]
    data = checker.slot_bytes(m, slot)
    corner = (data[1], data[4]) == (checker.corner_high, checker.corner_high)
    return ident, bool(data[checker.symbols['InstanceBehaviour']] & HOSTILE), corner


def placement_in_flight(data):
    """'corner' or 'centre' from x and y of a ship that has moved for a few updates."""
    highs = [data[1] | (data[2] & 0x7F) << 8, data[4] | (data[5] & 0x7F) << 8]
    if min(highs) >= 0x20:
        return 'corner'
    if max(highs) < 0x10:
        return 'centre'
    return 'unclear'


def emulator(checker):
    """ROM load in ZX Spectrum 48K mode, a jump to Diso, then test-only pokes of the RNG state and the
    encounter counter; the next object update must create the encounter predicted from the RAM."""
    import run_runtime_scenarios as rs
    s = checker.symbols
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == checker.image, \
        'Build the option with the default tapfile first'
    jump = rs.select_planet_and_jump('Diso')

    def scenario(name, seconds, pokes=()):
        args = list(jump)
        args[args.index('--seconds') + 1] = str(seconds)
        for address, data in pokes:
            args += rs.poke(ARRIVAL_SECONDS, f'{address:#06x}', data)
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
        memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        return memory

    memory = scenario('randomized-spawn-arrival', ARRIVAL_SECONDS)
    assert memory[s['JumpTunnelMode']] == 0 and memory[s['StationPresent']] == 0, 'not in open space at Diso'
    assert not any(memory[checker.slots[n] + s['InstanceEnergy']] for n in range(1, 7)), 'slots not empty'
    contexts = {}
    reference_payload = reference()[1][5].payload
    for name, parts in (('fixed', False), ('original', True)):
        ram = bytearray(memory)
        if parts:
            for start, end in PARTS.values():
                ram[start:end] = reference_payload[start - checker.base:end - checker.base]
        context = cr.ImageContext(s, checker.image)
        context.pristine = tuple(ram)
        contexts[name] = context
    ids, _ = checker.blueprint_ids()
    wanted = {'trader in a corner': ((9, 10), True), 'pirate ahead': ((11, 12), False)}
    chosen = {}
    for seed in range(65536):
        outcome = single_encounter(checker, contexts['fixed'], seed, ids)
        if outcome:
            for label, (kinds, corner) in wanted.items():
                if label not in chosen and outcome[0] in kinds and outcome[2] == corner:
                    chosen[label] = seed, outcome
        if len(chosen) == len(wanted):
            break
    assert len(chosen) == len(wanted), chosen
    results = {}
    for label, (seed, (ident, hostile, corner)) in chosen.items():
        original = single_encounter(checker, contexts['original'], seed, ids)
        assert original == (ident, hostile, hostile), (label, original)
        run = 'randomized-spawn-' + label.replace(' ', '-')
        final = scenario(run, EMULATOR_SECONDS, [(s['ObjectUpdateCounter'], '01'),
                                                 (s['RandomSeed'], f'{seed & 255:02x}{seed >> 8:02x}')])
        made = [(n, ids[final[checker.slots[n] + cr.INSTANCE_BLUEPRINT] |
                        final[checker.slots[n] + cr.INSTANCE_BLUEPRINT + 1] << 8])
                for n in range(1, 7) if final[checker.slots[n] + s['InstanceEnergy']]]
        assert len(made) == 1 and made[0][1] == ident, (label, made)
        data = final[checker.slots[made[0][0]]:checker.slots[made[0][0]] + checker.size]
        observed = placement_in_flight(data)
        assert observed == ('corner' if corner else 'centre'), (label, observed, data[:9].hex())
        results[label] = dict(seed=f'${seed:04X}', ship=SINGLE_SHIPS[ident], placement=observed,
                              original_placement='corner' if original[2] else 'centre',
                              position_bytes=data[:9].hex())
    print('PASS: 48K emulator: after a jump to Diso the poked RNG states create '
          + '; '.join(f'{r["ship"]} {r["placement"]} (original: {r["original_placement"]})'
                      for r in results.values()) + ', as predicted from the RAM.', flush=True)
    return results


if __name__ == '__main__':
    main()
