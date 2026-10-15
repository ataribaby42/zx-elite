"""Check scannerblipfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat scannerblipfix=yes verify=no
    python tools/check_scanner_blip_fix.py
    python tools/check_scanner_blip_fix.py --emulator

The simulator part runs DrawScannerContacts of the assembled image with the
supplied 48K ROM in SkoolKit's Z80 simulator and compares it with a baseline
whose three replaced parts are restored from the reference tape.  A model of
the contact geometry (column 123 + dx or 124 - dx, base row 165 -/+ dz, stick,
three-pixel dash, the two stick stops and the final clearing of rows
128..134) must reproduce:

- the original exactly, with its two quirks: dx = 4 shifts the contact one
  row, and an upward stick leaves the scanner except in character column 15;
- the fixed image exactly, without them;

for a grid of about 8,000 object positions, including every dx and the
tallest sticks.  Only the three parts may differ between the images.

--emulator loads release/elite-128k.tap through the 48K ROM, launches and
puts a cargo canister at dx = 4 next to the player with a test-only poke, so
that the real main loop draws it with the replaced code.  Build the option
with the default tapfile for this mode.
"""
import argparse
import json
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/scanner-blip-fix-check'
PARTS = ('ScannerBlipStep', 'ScannerBlipCentre', 'ScannerBlipGuard')
CENTRE_ROW = 165            # base row of a contact with dz = 0
SCANNER_TOP = 128           # first row of the bottom third
SCREEN_BOTTOM = 191
CLEARED_ROWS = range(128, 135)      # 7 rows at $5009 cleared after the contacts
CLEARED_COLUMNS = range(72, 176)    # bytes 9..21


def model(dot_x, stick, dot_z, original):
    """Pixels (x, y) lit by one contact, from the values DrawScannerContacts stores."""
    dx, negative = dot_x & 0x7F, dot_x & 0x80
    column = 124 - dx if negative else 123 + dx
    row = CENTRE_ROW + (dot_z & 0x7F if dot_z & 0x80 else -(dot_z & 0x7F))
    if original and dx == 4:
        row += -1 if negative else 1            # the 256-step DJNZ loop
    pixels, dash = set(), True
    height = stick & 0x7F
    for _ in range(height):
        pixels.add((column, row))
        if stick & 0x80:
            if row == SCREEN_BOTTOM:
                dash = False
                break
            row += 1
        else:
            if row == SCANNER_TOP and (not original or column // 8 == 15):
                dash = False
                break
            row -= 1
    if dash:
        pixels |= {(column - 2, row), (column - 1, row), (column, row)}
    return {(x, y) for x, y in pixels if not (y in CLEARED_ROWS and x in CLEARED_COLUMNS)}


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('SCANNER_BLIP_FIX') == 1, 'Build scannerblipfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.parts = [(s[part + 'Start'], s[part + 'Limit']) for part in PARTS]
        assert self.parts == [(0x8CE0, 0x8CF3), (0x8D0B, 0x8D0D), (0x8DCC, 0x8DDE)], self.parts
        original = reference()[1][5].payload
        baseline = bytearray(self.image)
        for start, end in self.parts:
            baseline[start - self.base:end - self.base] = original[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        assert changed and all(any(start <= a < end for start, end in self.parts) for a in changed)
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside the three replaced parts.', flush=True)

    def draw(self, context, x, y, z):
        m = context.machine()
        size, state = self.symbols['InstanceSize'], self.symbols['InitialRuntimeState']
        m.clear(cr.SCREEN, cr.SCREEN_SIZE)
        m.poke('LastActiveObjectEnergy', 1)
        m.poke('ScannerContactsDrawn', 0)
        for slot in range(self.symbols['InstanceSlotCount']):
            m.poke(state + slot * size + self.symbols['InstanceEnergy'], 0)
        for axis, value in enumerate((x, y, z)):
            cr.put24(m.memory, state + size + 3 * axis, value)
        m.poke(state + size + self.symbols['InstanceEnergy'], 0x40)
        m.call('DrawScannerContacts', stack=self.fixed.upper_stack)
        drawn = m.byte('ScannerContactsDrawn')
        values = (m.byte('ScannerDotX'), m.byte('ScannerStickHeight'), m.byte('ScannerDotZ'))
        return drawn, values, cr.bitmap_pixels(m.memory, cr.SCREEN, 192)

    def check_grid(self):
        xs = list(range(-0x3F80, 0x3F81, 0x100)) + [1367, -1367, 1366, -1366, 1368, -1368]
        ys = (-0x3FFF, -0x2800, -0x1000, -0x400, 0, 0x400, 0x1000, 0x2800, 0x3FFF)
        zs = (-0x3FFF, -0x2000, -0x800, 0, 0x800, 0x2000, 0x3FFF)
        cases = drawn_cases = dx4 = leaving = 0
        for x in xs:
            for y in ys:
                for z in zs:
                    fixed = self.draw(self.fixed, x, y, z)
                    original = self.draw(self.original, x, y, z)
                    assert fixed[:2] == original[:2], (x, y, z)
                    cases += 1
                    if not fixed[0]:
                        assert not fixed[2] and not original[2], (x, y, z)
                        continue
                    drawn_cases += 1
                    values = fixed[1]
                    assert fixed[2] == model(*values, original=False), (x, y, z, values, sorted(fixed[2]))
                    assert original[2] == model(*values, original=True), (x, y, z, values, sorted(original[2]))
                    assert all(row >= SCANNER_TOP for _, row in fixed[2]), (x, y, z)
                    dx4 += (values[0] & 0x7F) == 4
                    extra = {p for p in original[2] if p[1] < SCANNER_TOP}
                    if extra:
                        leaving += 1
                        assert all(row == 127 for _, row in extra), (x, y, z, sorted(extra))
        assert dx4 and leaving
        self.report['grid'] = dict(cases=cases, contacts=drawn_cases, dx_4_contacts=dx4,
                                   original_sticks_into_the_view=leaving)
        print(f'PASS: {cases} object positions ({drawn_cases} contacts): the fixed image matches the '
              f'intended geometry, the original matches it with its quirks ({dx4} contacts at dx = 4, '
              f'{leaving} sticks reaching row 127, only that row).', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_grid()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def emulator(symbols):
    import run_runtime_scenarios as rs
    image = (ROOT / 'build/game.bin').read_bytes()
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == image, \
        'Build the option with the default tapfile first'
    station, size = symbols['InitialRuntimeState'], symbols['InstanceSize']
    slot = station + size
    m = cr.ImageContext(symbols, image).machine()
    m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=4, ix=slot))   # cargo canister
    canister = bytearray(m.memory[slot:slot + size])
    position = bytearray(9)
    for axis, value in enumerate((1367, 0x0800, 0x0800)):
        cr.put24(position, 3 * axis, value)
    canister[0:9] = position
    name = 'scanner-blip-dx4'
    args = [*rs.started(14), *rs.key(8, 0.4, '1'), *rs.poke(12, f'{slot:#06x}', canister.hex())]
    subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
    executed = set(report['execution_map'])
    assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
    assert symbols['ScannerBlipStepStart'] in executed and symbols['DrawScannerContacts'] in executed
    memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
    dot_x = memory[symbols['ScannerDotX']]
    assert dot_x == 4 and memory[slot + 0x22], 'the canister (last slot drawn) is at dx = 4'
    print('PASS: 48K emulator: ROM load, launch and a canister at dx = 4 drawn on the scanner by the '
          'replaced code.', flush=True)
    return dict(scanner_dot_x=dot_x, final_text=[row['text'].rstrip(' _') for row in report['final_text'][:2]])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenario')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker.symbols)
    checker.write()


if __name__ == '__main__':
    main()
