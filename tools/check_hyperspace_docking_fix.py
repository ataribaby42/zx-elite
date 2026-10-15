"""Check hyperspacedockingfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat hyperspacedockingfix=yes verify=no
    python tools/check_hyperspace_docking_fix.py
    python tools/check_hyperspace_docking_fix.py --emulator

The fix changes one operand: CheckDocking tests JumpTunnelMode, which only an
accepted jump sets, instead of HyperspaceKeyLatch, which every H or G press
sets.  The simulator part runs the assembled image with the supplied 48K ROM in
SkoolKit's Z80 simulator against a baseline with the original instruction
restored from the reference tape:

- only the operand differs;
- CheckDocking for every latch / JumpTunnelMode / docking-path combination;
- every refused H or G press (docked, G alone, no galactic hyperdrive, the
  current system, out of range, countdown already running) followed by station
  contact: the fixed image docks, the original does not;
- an accepted jump blocks docking from the acceptance until the arrival tunnel
  ends.

--emulator loads release/elite-128k.tap through the 48K ROM
(tools/emulator_check.py): H pressed while docked, launch and the docking
computer key C must dock; the same without H must dock; C during an accepted
countdown to Diso must not dock, and the jump must arrive at Diso.  Docking
computers are fitted by a test-only poke.  Build the option with the default
tapfile for this mode.
"""
import argparse
import json
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/hyperspace-docking-fix-check'


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('HYPERSPACE_DOCKING_FIX') == 1, 'Build hyperspacedockingfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.part = (s['HyperspaceDockingCheckStart'], s['HyperspaceDockingCheckLimit'])
        assert self.part == (0x70BE, 0x70C1) == (s['CheckDocking'], s['CheckDocking'] + 3)
        start, end = self.part
        baseline = bytearray(self.image)
        baseline[start - self.base:end - self.base] = reference()[1][5].payload[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        start, end = self.part
        assert changed == [start + 1, start + 2], changed
        tunnel = self.symbols['JumpTunnelMode']
        assert self.image[start - self.base:end - self.base] == bytes([0x3A, tunnel & 255, tunnel >> 8])
        self.report['changed_bytes'] = len(changed)
        print('PASS: only the operand of CheckDocking changed: LD A,(JumpTunnelMode).', flush=True)

    def docking_state(self, m, contact):
        """Everything else allows docking: in flight, station present and calm, docking
        computers fitted; either station contact or the docking-computer key C."""
        m.poke('FlightCondition', 1)
        m.poke('StationPresent', 1)
        m.poke('DockingComputerFitted', 1)
        m.poke(self.symbols['InitialRuntimeState'] + self.symbols['InstanceBehaviour'], 0)
        m.poke('DockingContactFlag', 1 if contact else 0)
        m.poke('KeyFlagsCombat', 0 if contact else 0x80)

    def docks(self, m):
        docked = []
        m.call('CheckDocking', stubs={'DockWithStation': lambda mm: docked.append(1)}, **cr.ZERO_REGISTERS)
        return bool(docked)

    def check_matrix(self):
        cases = 0
        for latch in (0, 1):
            for tunnel in (0, 1, 2):
                for contact in (True, False):
                    outcome = {}
                    for name, context in (('fixed', self.fixed), ('original', self.original)):
                        m = context.machine()
                        self.docking_state(m, contact)
                        m.poke('HyperspaceKeyLatch', latch)
                        m.poke('JumpTunnelMode', tunnel)
                        outcome[name] = self.docks(m)
                    assert outcome['fixed'] == (tunnel == 0), (latch, tunnel, contact, outcome)
                    assert outcome['original'] == (latch == 0 and (contact or tunnel == 0)), \
                        (latch, tunnel, contact, outcome)
                    cases += 1
        self.report['check_docking_cases'] = cases
        print(f'PASS: {cases} CheckDocking cases: the fixed image docks exactly when JumpTunnelMode is 0, '
              'whatever HyperspaceKeyLatch holds.', flush=True)

    def press(self, m, keys, docked=False, countdown=0, drive=0, distance=3, fuel=70, tunnel=0):
        m.poke('HyperspaceKeyLatch', 0)
        m.poke('KeyFlagsViews', keys | 0x01)
        m.poke('HyperspaceCountdown', countdown)
        m.poke('FlightCondition', 0 if docked else 1)
        m.poke('GalacticHyperdriveFitted', drive)
        m.poke('JumpTunnelMode', tunnel)
        m.poke('FuelLevel', fuel)
        m.poke_word('SelectedSystemDistance', distance)
        m.call('CheckHyperspaceKeys', halt=True, stubs={'SnapCursorToNearestSystem': None,
                                                        'ShowCommanderStatus': None},
               **cr.ZERO_REGISTERS)
        assert m.byte('HyperspaceKeyLatch') == 1 and m.byte('KeyFlagsViews') & 0x30 == 0, 'latch set, keys consumed'

    def check_presses(self):
        refused = {  # name: (keys, keyword arguments)
            'H while docked': (0x10, dict(docked=True)),
            'G alone': (0x20, dict(drive=1)),
            'G+H without galactic hyperdrive': (0x30, dict(drive=0)),
            'H to the current system': (0x10, dict(distance=0)),
            'H out of range (fuel)': (0x10, dict(distance=40, fuel=30)),
            'H out of range (25.6 LY or more)': (0x10, dict(distance=0x100)),
        }
        for name, (keys, kwargs) in refused.items():
            outcome = {}
            for label, context in (('fixed', self.fixed), ('original', self.original)):
                m = context.machine()
                self.press(m, keys, **kwargs)
                assert m.byte('JumpTunnelMode') == 0 and m.byte('HyperspaceCountdown') == 0, (name, 'refused')
                self.docking_state(m, contact=True)
                outcome[label] = self.docks(m)
            assert outcome == {'fixed': True, 'original': False}, (name, outcome)
        # A press while a countdown runs: the accepted jump keeps docking off in both.
        for context in (self.fixed, self.original):
            m = context.machine()
            self.press(m, 0x10, countdown=5, tunnel=1)
            self.docking_state(m, contact=True)
            assert not self.docks(m), 'countdown running'
        self.report['refused_presses'] = len(refused) + 1
        print(f'PASS: {len(refused)} refused H/G presses no longer block docking (the original never '
              'docks afterwards); a press during a running countdown still does.', flush=True)

    def check_accepted_jump(self):
        timeline = {}
        for label, context in (('fixed', self.fixed), ('original', self.original)):
            m = context.machine()
            self.press(m, 0x10, distance=3)
            assert (m.byte('JumpTunnelMode'), m.byte('HyperspaceCountdown')) == (1, 21), 'accepted'
            steps = []
            self.docking_state(m, contact=True)
            steps.append(self.docks(m))                         # during the countdown
            m.call('FinishHyperspaceArrival', **cr.ZERO_REGISTERS)
            self.docking_state(m, contact=True)
            steps.append(self.docks(m))                         # arrival tunnel running
            m.poke('JumpTunnelMode', 0)                         # as FinishHyperspaceTunnel does
            self.docking_state(m, contact=True)
            steps.append(self.docks(m))                         # after the arrival tunnel
            timeline[label] = steps
        assert timeline == {'fixed': [False, False, True], 'original': [False, True, True]}, timeline
        self.report['accepted_jump'] = timeline
        print('PASS: an accepted jump blocks docking from the acceptance until its arrival tunnel ends '
              '(the original until the arrival itself).', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_matrix()
        self.check_presses()
        self.check_accepted_jump()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def emulator(symbols):
    import run_runtime_scenarios as rs
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == (ROOT / 'build/game.bin').read_bytes(), \
        'Build the option with the default tapfile first'
    fitted = rs.poke(7, f"{symbols['DockingComputerFitted']:#06x}", '01')
    jump = [a for a in rs.select_planet_and_jump('Diso')]
    runs = {
        'hyperspace-docking-refused-h': [*rs.started(26), *fitted, *rs.key(8, 0.4, 'H'),
                                         *rs.key(12, 0.5, '1'), *rs.key(20, 0.4, 'C')],
        'hyperspace-docking-control': [*rs.started(26), *fitted, *rs.key(12, 0.5, '1'), *rs.key(20, 0.4, 'C')],
        'hyperspace-docking-countdown': [*jump, *fitted, *rs.key(27, 0.4, 'C')],
    }
    results = {}
    for name, args in runs.items():
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
        memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        results[name] = dict(flight_condition=memory[symbols['FlightCondition']],
                             text=[row['text'].rstrip(' _') for row in report['final_text'][:3]])
    assert results['hyperspace-docking-refused-h']['flight_condition'] == 0, results
    assert results['hyperspace-docking-control']['flight_condition'] == 0, results
    countdown = results['hyperspace-docking-countdown']
    assert countdown['flight_condition'] != 0 and any('Diso' in line for line in countdown['text']), countdown
    print('PASS: 48K emulator: after a refused H in the dock the docking computer docks; without H it docks; '
          'during an accepted countdown it does not, and the jump arrives at Diso.', flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenarios')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker.symbols)
    checker.write()


if __name__ == '__main__':
    main()
