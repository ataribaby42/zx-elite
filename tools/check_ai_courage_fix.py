"""Check aicouragefix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat aicouragefix=yes verify=no
    python tools/check_ai_courage_fix.py
    python tools/check_ai_courage_fix.py --emulator

The simulator part runs the assembled image with the supplied 48K ROM in
SkoolKit's Z80 simulator against a baseline with the original 19 bytes of
ApplyPlayerLaserHit restored from the reference tape:

- only those bytes differ;
- ApplyPlayerLaserHit for every +$25 value, the three laser damages and a
  surviving and a destroyed target: below $80 everything matches the original;
  from $80 up only +$25 differs, by the floor instead of the wrap;
- 27 pulse-laser hits on a hostile Python (with and without ECM), each
  followed by the real UpdateShipHostilityAndSteering in open space: the fixed
  ship keeps fleeing after its first flight and never fires again, while the
  original ship turns back at hits 10 and 19.

--emulator loads release/elite-128k.tap through the 48K ROM.  After a launch,
test-only pokes put a hostile Python straight ahead and move the station far
away (dormant), so that the AI decides by courage; the player then holds fire.
The hit Python must flee at courage 6 with full acceleration.  The original
build in the same run ends at $E4: fleeing, but with courage 100 after the
wrap.  Build the option with the default tapfile for this mode.
"""
import argparse
import json
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/ai-courage-fix-check'
AI_STATE, ENERGY, BEHAVIOUR, STATE, ROLE = 0x25, 0x22, 0x21, 0x20, 0x26
FLEEING = 0x80
PYTHON = 11                     # pirate Python; energy 250
DAMAGES = (15, 23, 50)          # pulse/beam, military, mining


def fixed_value(value):
    courage = value & 0x7F
    courage = courage - 14 if courage >= 14 else 6 + (courage & 1)
    return (value & FLEEING) | courage


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('AI_COURAGE_FIX') == 1, 'Build aicouragefix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.part = (s['AiCourageHitStart'], s['AiCourageHitLimit'])
        assert self.part == (0xEC6A, 0xEC7D) and s['AiCourageHitEnd'] == self.part[1]
        start, end = self.part
        baseline = bytearray(self.image)
        baseline[start - self.base:end - self.base] = reference()[1][5].payload[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.slot = s['InitialRuntimeState'] + s['InstanceSize']
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def outside_part(self, memory):
        start, end = self.part
        data = bytearray(memory[self.base:self.base + len(self.image)])
        data[start - self.base:end - self.base] = bytes(end - start)
        return bytes(data)

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        start, end = self.part
        assert changed and all(start <= a < end for a in changed), changed
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside the original 19 bytes at $EC6A.', flush=True)

    def hit(self, context, value, damage, energy):
        m = context.machine()
        m.poke(self.slot + AI_STATE, value)
        m.poke(self.slot + ENERGY, energy)
        m.poke(self.slot + STATE, 0x40)
        m.poke(self.slot + ROLE, 0)
        m.call('ApplyPlayerLaserHit', stop='DrawLaser', balance=False, ix=self.slot, iy=0,
               a=0, f=0, bc=damage, de=0, hl=0)
        return m, (m.reg('a'), m.reg('b'), m.reg('c'), m.ix())

    def check_arithmetic(self):
        cases = 0
        for value in range(256):
            for damage in DAMAGES:
                for energy in (200, 10):
                    mf, rf = self.hit(self.fixed, value, damage, energy)
                    mo, ro = self.hit(self.original, value, damage, energy)
                    assert rf == ro, (value, damage, energy, rf, ro)
                    assert mf.byte(self.slot + AI_STATE) == fixed_value(value), (value, mf.byte(self.slot + AI_STATE))
                    if value < FLEEING:
                        assert self.outside_part(mf.memory) == self.outside_part(mo.memory), value
                    else:
                        mo.poke(self.slot + AI_STATE, mf.byte(self.slot + AI_STATE))
                        assert self.outside_part(mf.memory) == self.outside_part(mo.memory), value
                    cases += 1
        self.report['arithmetic_cases'] = cases
        print(f'PASS: {cases} hit cases: below $80 RAM and registers match the original; from $80 up only '
              '+$25 differs (floor 6/7 kept instead of the wrap).', flush=True)

    def fight(self, context, ecm):
        """27 pulse hits on a hostile Python in open space, each followed by one AI step."""
        m = context.machine()
        m.poke(self.symbols['InitialRuntimeState'] + ENERGY, 0)      # no active station
        m.poke('InvasionMissionState', 0)
        m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=PYTHON, ix=self.slot))
        m.poke(self.slot + AI_STATE, 0x7E | ecm)
        blueprint = m.word(self.slot + 0x23)
        trace = []
        for _ in range(27):
            m.call('ApplyPlayerLaserHit', stop='DrawLaser', balance=False, ix=self.slot, iy=0,
                   a=0, f=0, bc=15, de=0, hl=0)
            m.poke(self.slot + ENERGY, 250)                            # keep it alive for the trace
            events = []
            m.call('UpdateShipHostilityAndSteering', ix=self.slot, iy=blueprint, **cr.ZERO_REGISTERS,
                   hooks={'SteerShipTowardsPlayer': lambda mm: events.append('towards'),
                          'SteerShipAwayFromPlayer': lambda mm: events.append('away')},
                   stubs={'TryFireAiLaser': lambda mm: events.append('fire')})
            trace.append((m.byte(self.slot + AI_STATE), tuple(events), m.byte(self.slot + 0x1C)))
        return trace

    def check_fight(self):
        results = {}
        for ecm in (0, 1):
            fixed, original = self.fight(self.fixed, ecm), self.fight(self.original, ecm)
            assert fixed[:8] == original[:8], 'identical before the ship flees'
            first = next(i for i, (_, events, _) in enumerate(fixed) if 'away' in events)
            assert first == 8 and first == next(i for i, (_, e, _) in enumerate(original) if 'away' in e)
            assert fixed[first][0] == FLEEING | ecm, fixed[first]       # 126 - 9*14 = 0, plus the ECM bit
            for index, (value, events, acceleration) in enumerate(fixed[first:]):
                assert value & FLEEING and (index == 0 or (value & 0x7F) == 6 + ecm), value
                assert events == ('away',) and acceleration == 2, (events, acceleration)
            turned_back = [i + 1 for i, (_, events, _) in enumerate(original) if i > first and 'towards' in events]
            assert turned_back and turned_back[0] == 10 and not any('fire' in e for _, e, _ in original[first:])
            results[f'ecm_{ecm}'] = dict(first_flight_at_hit=first + 1, fixed_courage_after=6 + ecm,
                                         original_turns_back_at_hits=[h for h in turned_back
                                                                      if 'towards' not in original[h - 2][1]])
        self.report['python_fight'] = results
        print('PASS: Python, 27 pulse hits: both flee at hit 9; the fixed ship keeps fleeing at courage 6/7 '
              f"with full acceleration and no laser, the original turns back at hits "
              f"{results['ecm_0']['original_turns_back_at_hits']}.", flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_arithmetic()
        self.check_fight()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def emulator(symbols):
    """Open-space fight: a hostile Python created by InitialiseShipFromBlueprint is poked into
    slot 1 straight ahead, the station is made dormant and moved far away (test-only pokes,
    so that the AI decides by courage), and the player holds fire for 17 seconds."""
    import run_runtime_scenarios as rs
    image = (ROOT / 'build/game.bin').read_bytes()
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == image,         'Build the option with the default tapfile first'
    station, size = symbols['InitialRuntimeState'], symbols['InstanceSize']
    slot = station + size
    m = cr.ImageContext(symbols, image).machine()
    m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=PYTHON, ix=slot))
    ship = bytearray(m.memory[slot:slot + size])
    ship[0:9] = bytes([0, 0, 0, 0, 0, 0, 0, 0x08, 0])          # x = y = 0, z = $0800 ahead
    ship[BEHAVIOUR] |= 4                                      # hostile
    far = bytes([0, 0, 0, 0, 0, 0, 0, 0, 0x85])               # station at z = -$050000
    args = [*rs.started(34), *rs.key(8, 0.4, '1'),
            *rs.poke(16, f'{slot:#06x}', ship.hex()), *rs.poke(16, f'{station:#06x}', far.hex()),
            *rs.poke(16, f'{station + ENERGY:#06x}', '00'),
            *rs.poke(16, f"{symbols['StationDormantFlag']:#06x}", 'ff'), *rs.key(17, 16.5, 'A')]
    name = 'ai-courage-python'
    subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
    memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
    assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
    assert symbols['AiCourageHitStart'] in set(report['execution_map']), 'no damaging hit'
    value = memory[slot + AI_STATE]
    assert memory[slot + ENERGY] and memory[symbols['StationDormantFlag']] == 0xFF
    assert value == FLEEING | 6 and memory[slot + 0x1C] == 2, f'${value:02X}'
    print(f'PASS: 48K emulator open-space fight: the hit Python flees with +$25 ${value:02X} '
          '(courage held at 6) and full acceleration.', flush=True)
    return dict(ai_state=value, energy=memory[slot + ENERGY], acceleration=memory[slot + 0x1C])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load combat scenario')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker.symbols)
    checker.write()


if __name__ == '__main__':
    main()
