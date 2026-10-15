"""Check missiletargetfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat missiletargetfix=yes verify=no
    python tools/check_missile_target_fix.py
    python tools/check_missile_target_fix.py --emulator

ReleaseTargetLocks runs whenever an object is removed (destroyed, scooped,
collided or out of range), with H = ObjectLoopCounter, the counter of the
removed slot (8 for slot 0 down to 1 for slot 7), and IX = the removed object.
It should explode every live missile in slots 1..7 whose target code (+$25)
is H.  The original tests the missile flag (+$26 bit 0) of the removed object
instead of the scanned slot, so a missile whose target is removed keeps
homing on that slot, and removing a missile explodes every live object whose
+$25 (for ships the AI courage byte) equals its counter.

The simulator part runs ReleaseTargetLocks of the assembled image and of a
baseline whose replaced instruction is restored from the reference tape, with
the supplied 48K ROM in SkoolKit's simulator, for every counter, both kinds of
removed object and random slot contents.  Each image must match its model;
the missile lock of the player (MissileState 2) and every other byte must be
handled identically.

--emulator loads release/elite-128k.tap through the 48K ROM and launches.  A
test-only poke then adds a player missile aimed at a cargo canister that is
removed at once (out of range), and an enemy missile that is removed at once
next to a canister whose +$25 equals that missile's counter.  A second run
also restores the original instruction with a test-only poke.  Build the
option with the default tapfile for this mode.
"""
import argparse
import json
import random
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/missile-target-fix-check'
FIRST_SCANNED_SLOT = 1
EXPLODING = 0x10                        # +$20 bit 4: explosion state set by ReleaseTargetLocks
EXPLOSION_BITS = 0x30                   # +$20 bits 4/5: exploding
MISSILE = 0x01                          # +$26 bit 0
LOCKED = 2                              # MissileState: the player's missile is locked on a target
TARGET_LOST = 0x80                      # TargetLostMessage bit 7
# Instance fields (src/game.asm defc Instance...; not all of them reach the symbol map)
AI_STATE, ROLE_FLAGS, FLAGS = cr.INSTANCE_FLAGS25, cr.INSTANCE_FLAGS26, cr.INSTANCE_STATE
SPEED = 0x1B                            # InstanceSpeed
STATION_WITHOUT_ECM = 0x7E              # station +$25 with bit 0 (ECM fitted) clear


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('MISSILE_TARGET_FIX') == 1, 'Build missiletargetfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.part = (s['MissileTargetCheckStart'], s['MissileTargetCheckLimit'])
        assert self.part == (0xEB82, 0xEB86), self.part
        start, end = self.part
        self.original_bytes = bytes(reference()[1][5].payload[start - self.base:end - self.base])
        baseline = bytearray(self.image)
        baseline[start - self.base:end - self.base] = self.original_bytes
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.slots = s['InstanceSlotCount']
        self.size = s['InstanceSize']
        self.state = s['InitialRuntimeState']
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def slot(self, index):
        return self.state + index * self.size

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        start, end = self.part
        assert len(changed) == 1 and start <= changed[0] < end, changed
        assert self.original_bytes[0] == 0xDD and self.image[changed[0] - self.base] == 0xFD
        self.report['changed_bytes'] = changed
        print(f'PASS: one changed byte at ${changed[0]:04X}: the index prefix of BIT 0,(IX+$26) '
              f'becomes that of BIT 0,(IY+$26).', flush=True)

    def release(self, context, case):
        counter, removed_missile, contents, lock_state, lock_target = case
        s = self.symbols
        m = context.machine()
        removed = self.slot(self.slots - counter)
        for index, (energy, target, flags26, flags20) in contents.items():
            inst = self.slot(index)
            m.poke(inst + s['InstanceEnergy'], energy)
            m.poke(inst + AI_STATE, target)
            m.poke(inst + ROLE_FLAGS, flags26)
            m.poke(inst + FLAGS, flags20)
        m.poke(removed + s['InstanceEnergy'], 0)         # every caller frees the slot first
        m.poke(removed + ROLE_FLAGS, MISSILE if removed_missile else 0)
        m.poke('ObjectLoopCounter', counter)
        m.poke('MissileState', lock_state)
        m.poke('MissileTarget', lock_target)
        m.poke('TargetLostMessage', m.byte('TargetLostMessage') & ~TARGET_LOST & 0xFF)
        m.call('ReleaseTargetLocks', ix=removed, iy=0x5A5A, a=0, f=0, bc=0, de=0, hl=0)
        assert m.iy() == 0x5A5A and m.pair('de') == self.size and m.reg('b') == 0
        return m

    def check_release(self, cases=4000):
        s = self.symbols
        rng = random.Random(1)
        changed_cases = 0
        stats = dict(cases=0, original_explosions=0, fixed_explosions=0, locks_released=0)
        targets = (0, 6, 7, 0x7E, 0x86)
        all_cases = []
        for counter in range(1, self.slots + 1):
            for removed_missile in (False, True):
                for lock_state, lock_target in ((LOCKED, counter), (LOCKED, counter % 8 + 1), (1, counter), (0, 0)):
                    all_cases.append((counter, removed_missile, lock_state, lock_target))
        for _ in range(cases):
            all_cases.append((rng.randrange(1, self.slots + 1), rng.random() < 0.5,
                              rng.choice((0, 1, LOCKED)), rng.randrange(1, self.slots + 1)))
        for counter, removed_missile, lock_state, lock_target in all_cases:
            contents = {}
            for index in range(FIRST_SCANNED_SLOT, self.slots):
                contents[index] = (rng.choice((0, rng.randrange(1, 256))),
                                   rng.choice((counter, counter, rng.choice(targets), counter | 0x80)),
                                   rng.randrange(256), rng.randrange(256) & ~EXPLODING & 0xFF)
            case = (counter, removed_missile, contents, lock_state, lock_target)
            fixed, original = self.release(self.fixed, case), self.release(self.original, case)
            removed = self.slots - counter
            for name, m, model in (('original', original, lambda i: removed_missile),
                                   ('fixed', fixed, lambda i: contents[i][2] & MISSILE)):
                exploded = {i for i in range(FIRST_SCANNED_SLOT, self.slots)
                            if m.byte(self.slot(i) + FLAGS) & EXPLODING}
                want = {i for i, (energy, target, _, _) in contents.items()
                        if i != removed and energy and target == counter and model(i)}
                assert exploded == want, (name, case, exploded, want)
                stats[f'{name}_explosions'] += len(exploded)
            released = lock_state == LOCKED and lock_target == counter
            for m in (fixed, original):
                assert m.byte('MissileState') == (0 if released else lock_state)
                assert bool(m.byte('TargetLostMessage') & TARGET_LOST) == released
            stats['locks_released'] += released
            flags = {self.slot(i) + FLAGS for i in range(self.slots)}
            differ = [a for a in range(0x4000, 0x10000) if fixed.memory[a] != original.memory[a]
                      and not self.part[0] <= a < self.part[1]]
            assert all(a in flags for a in differ), [hex(a) for a in differ]
            changed_cases += bool(differ)
            stats['cases'] += 1
        stats['cases_with_different_results'] = changed_cases
        assert stats['original_explosions'] and stats['fixed_explosions'] and changed_cases
        self.report['release'] = stats
        print(f'PASS: ReleaseTargetLocks for {stats["cases"]} cases (every counter, removed missile or '
              f'not, random slots): the original explodes live objects whose +$25 equals the counter '
              f'when the removed object is a missile ({stats["original_explosions"]} explosions), the '
              f'fixed image explodes live missiles aimed at the removed object '
              f'({stats["fixed_explosions"]}); the player\'s lock is released identically '
              f'({stats["locks_released"]} cases) and only +$20 bytes differ.', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_release()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def put_position(record, x, y, z):
    for axis, value in enumerate((x, y, z)):
        cr.put24(record, 3 * axis, value)


def emulator(checker):
    """Player missile in slot 7 aimed at a canister in slot 1 that is out of range, so the first
    object update removes it; an enemy missile in slot 2, also out of range, next to a canister
    in slot 3 whose +$25 equals the counter of slot 2.  The station's ECM (+$25 bit 0) is
    switched off: with a player missile in slot 7 it may fire and destroy every missile."""
    import run_runtime_scenarios as rs
    s = checker.symbols
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == checker.image, \
        'Build the option with the default tapfile first'
    m = checker.fixed.machine()
    for index in range(1, checker.slots):
        m.poke(checker.slot(index) + s['InstanceEnergy'], 0)
    far = 0x010000                                     # nonzero z high byte: removed by MoveObject
    records = {}
    for index, (blueprint, position, ai_state) in {1: (4, (0, 0, far), None),
                                                   2: (1, (0x400, 0, far), 0),
                                                   3: (4, (0x300, 0x100, 0x900), 6)}.items():
        inst = checker.slot(index)
        m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=blueprint, ix=inst))
        record = bytearray(m.memory[inst:inst + checker.size])
        put_position(record, *position)
        record[SPEED] = 0
        if ai_state is not None:
            record[AI_STATE] = ai_state
        if blueprint == 1:
            record[ROLE_FLAGS] |= MISSILE    # as LaunchMissile sets it
        records[index] = record
    counter_of = {index: checker.slots - index for index in range(checker.slots)}
    assert records[3][AI_STATE] == counter_of[2]
    m.call('LaunchMissile', **dict(cr.FRESH_REGISTERS, c=counter_of[1]))   # player launch: slot 7
    missile = checker.slot(checker.slots - 1)
    records[checker.slots - 1] = bytearray(m.memory[missile:missile + checker.size])
    assert records[checker.slots - 1][AI_STATE] == counter_of[1]
    assert records[checker.slots - 1][ROLE_FLAGS] & MISSILE
    station_ai = checker.slot(0) + AI_STATE
    pokes = [*rs.poke(12.5, f'{station_ai:#06x}', f'{STATION_WITHOUT_ECM:02x}')]
    pokes += [arg for index, record in records.items()
              for arg in rs.poke(12.5, f'{checker.slot(index):#06x}', record.hex())]
    results = {}
    for name, extra in (('fixed', []),
                        ('original', rs.poke(11, f'{checker.part[0]:#06x}', checker.original_bytes.hex()))):
        run = f'missile-target-{name}'
        args = [*rs.started(16), *rs.key(8, 0.4, '1'), *extra, *pokes]
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', run, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{run}.json').read_text())
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        assert s['ReleaseTargetLocks'] in set(report['execution_map'])
        memory = (ROOT / f'build/emulator/{run}-memory.bin').read_bytes()

        def alive(index):
            inst = checker.slot(index)
            return bool(memory[inst + s['InstanceEnergy']]) and not memory[inst + FLAGS] & EXPLOSION_BITS
        missile_bytes = memory[missile:missile + checker.size]
        results[name] = dict(player_missile_alive=alive(checker.slots - 1),
                             player_missile_target=missile_bytes[AI_STATE],
                             canister_alive=alive(3),
                             canister_ai_state=memory[checker.slot(3) + AI_STATE])
    fixed, original = results['fixed'], results['original']
    assert not fixed['player_missile_alive'] and fixed['canister_alive'] and fixed['canister_ai_state'] == 6, results
    assert original['player_missile_alive'] and original['player_missile_target'] == counter_of[1], results
    assert not original['canister_alive'], results
    print('PASS: 48K emulator: ROM load and launch.  With the original instruction restored, the player '
          'missile keeps flying after its target canister is removed, and removing an enemy missile '
          'explodes a canister whose +$25 equals its counter; the fixed image explodes the missile and '
          'keeps the canister.', flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenarios')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker)
    checker.write()


if __name__ == '__main__':
    main()
