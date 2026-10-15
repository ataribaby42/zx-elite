"""Check fuelfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat fuelfix=yes verify=no
    python tools/check_fuel_fix.py
    python tools/check_fuel_fix.py --emulator

The simulator part executes the assembled image with the supplied 48K ROM in
SkoolKit's Z80 simulator and compares it with a baseline that differs only in
the five replaced areas, restored from the immutable reference tape:

- only those areas differ;
- FuelPriceUpdate gives the expected price for every fuel level 0..70, every
  government and every s0 high byte (145,408 cases) and continues in
  BeginTradeScreen;
- after a normal hyperspace jump into each of the 2,048 systems it gives the
  price the original jump stores;
- FuelGaugeUpdate leaves the same RAM as StoreFuelLevel followed by the
  original PrepareShipForLaunch, for every fuel byte 0..255.

--emulator loads release/elite-128k.tap through the 48K ROM
(tools/emulator_check.py).  A test-only poke of FuelLevel stands for a loaded
commander with 3.4 light years; the equipment list must then show the fuel
price 4.6, buying fuel must cost 4.6 and fill the tank, and a launch must set
the FU bar value to 76.  Build the option with the default tapfile for this mode.
"""
import argparse
import json
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/fuel-fix-check'
PARTS = ('FuelLaunchHook', 'FuelPriceHook', 'FuelPricePart', 'FuelEconomyPart', 'FuelStorePart')
FULL = 70


def expected_price(fuel, government, s0_high):
    if fuel == FULL:
        return 0
    economy = (s0_high & 7) | (2 if government < 2 else 0)
    return (2 * economy + FULL - fuel) & 0xFF


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('FUEL_FIX') == 1, 'Build fuelfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.parts = [(s[part + 'Start'], s[part + 'Limit']) for part in PARTS]
        assert self.parts == [(0x7B85, 0x7B88), (0xB53F, 0xB542), (0xB31B, 0xB32B),
                              (0xA89B, 0xA8AA), (0x9A3A, 0x9A46)], self.parts
        original = reference()[1][5].payload
        baseline = bytearray(self.image)
        for start, end in self.parts:
            baseline[start - self.base:end - self.base] = original[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
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
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside the five replaced areas.', flush=True)

    def check_formula(self):
        m = self.fixed.machine()
        seeds = self.symbols['CurrentSystemSeeds']
        cases = 0
        for fuel in range(FULL + 1):
            for government in range(8):
                for s0_high in range(256):
                    m.poke('FuelLevel', fuel)
                    m.poke('CurrentGovernment', government)
                    m.poke(seeds + 1, s0_high)
                    m.poke('FuelPrice', 0xA5)
                    m.call('FuelPriceUpdate', stop='BeginTradeScreen', balance=False,
                           a=0, f=0, bc=0, de=0, hl=0)
                    assert m.byte('FuelPrice') == expected_price(fuel, government, s0_high), \
                        (fuel, government, s0_high, m.byte('FuelPrice'))
                    assert (m.byte('FuelLevel'), m.byte('CurrentGovernment'), m.byte(seeds + 1)) == \
                        (fuel, government, s0_high)
                    cases += 1
        self.report['formula_cases'] = cases
        print(f'PASS: {cases} fuel/government/s0 cases: 0 for a full tank, otherwise '
              '2*economy + 70 - fuel; then BeginTradeScreen.', flush=True)

    def check_jumps(self):
        gen = self.original.machine()
        matches = 0
        prices = set()
        for galaxy in range(8):
            gen.reset()
            cr.load_jameson(gen)
            galaxy_seeds = [gen.memory[self.symbols['GalaxySeeds'] + i] for i in range(6)]
            for _ in range(galaxy):
                galaxy_seeds = [((b << 1) | (b >> 7)) & 0xFF for b in galaxy_seeds]
            gen.poke('GalaxySeeds', *galaxy_seeds)
            gen.call('LoadGalaxySeedsToGenerator', **cr.ZERO_REGISTERS)
            for index in range(256):
                gen.call('DeriveSelectedSystemData', **cr.ZERO_REGISTERS)
                gen.call('GenerateSystemName', **cr.ZERO_REGISTERS)
                # Everything DeriveSelectedSystemData sets for the target system.
                selected = {name: gen.memory[self.symbols[name]:self.symbols[name] + size]
                            for name, size in (('SelectedSystemSeeds', 6), ('SelectedSystemEconomy', 1),
                                               ('SelectedSystemGovernment', 1), ('SelectedSystemTechLevel', 1))}
                distance = 1 + (galaxy * 256 + index) % FULL
                results = []
                for context in (self.original, self.fixed):
                    m = context.machine()
                    cr.load_jameson(m)
                    m.poke('CurrentGalaxy', galaxy)
                    for name, values in selected.items():
                        m.poke(name, *values)
                    m.poke('SelectedSystemDistance', distance)
                    m.poke('AuxRandomSeed', 0)          # no mis-jump
                    m.call('NormalHyperspaceJump', stop='L_D7B4', limit=500_000, halt=True,
                           **cr.FRESH_REGISTERS)
                    if context is self.fixed:
                        m.poke('FuelPrice', 0)
                        m.call('FuelPriceUpdate', stop='BeginTradeScreen', balance=False,
                               a=0, f=0, bc=0, de=0, hl=0)
                    results.append((m.byte('FuelLevel'), m.byte('FuelPrice')))
                assert results[0] == results[1], (galaxy, index, results)
                assert results[0][0] == FULL - distance
                prices.add(results[0][1])
                matches += 1
        self.report['jump_matches'] = dict(systems=matches, distinct_prices=len(prices))
        print(f'PASS: after a normal jump into each of the {matches} systems the price equals the '
              'one the original jump stores.', flush=True)

    def check_gauge(self):
        for fuel in range(256):
            states = []
            for context, steps in ((self.fixed, ('FuelGaugeUpdate',)),
                                   (self.original, ('StoreFuelLevel', 'PrepareShipForLaunch'))):
                m = context.machine()
                cr.load_jameson(m)
                m.poke('FuelLevel', fuel)
                for step in steps:
                    m.call(step, halt=True, a=fuel, f=0, bc=0, de=0, hl=0)
                states.append((self.outside_parts(m.memory), m.byte('FuelLevel'), m.byte('FuelGauge')))
            assert states[0] == states[1], fuel
            assert states[0][1] == fuel
        gauge = {fuel: (2 * fuel + (2 * fuel >> 3)) & 0xFF for fuel in (34, 70)}
        self.report['gauge_cases'] = 256
        print(f'PASS: FuelGaugeUpdate equals StoreFuelLevel + PrepareShipForLaunch for all 256 fuel '
              f'bytes and keeps FuelLevel (3.4 LY -> {gauge[34]}, 7.0 LY -> {gauge[70]}).', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_formula()
        self.check_jumps()
        self.check_gauge()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def emulator(symbols):
    import run_runtime_scenarios as rs
    image = (ROOT / 'build/game.bin').read_bytes()
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == image, \
        'Build the option with the default tapfile first'
    fuel = f"{symbols['FuelLevel']:#06x}"
    runs = {
        'fuel-fix-equip': [*rs.started(12), *rs.poke(7, fuel, '22'), *rs.key(9, 0.5, '4')],
        'fuel-fix-buy': [*rs.started(16), *rs.poke(7, fuel, '22'), *rs.key(9, 0.5, '4'),
                         *rs.key(11, 0.25, '1'), *rs.key(12, 0.3, 'ENTER')],
        'fuel-fix-launch': [*rs.started(20), *rs.poke(7, fuel, '22'), *rs.key(9, 0.5, '1')],
    }
    results = {}
    for name, args in runs.items():
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
        memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        text = [row['text'].rstrip(' _') for row in report['final_text']]
        fuel_line = next((line for line in text if line.split()[:2] == ['1', 'Fuel']), None)
        results[name] = dict(fuel_level=memory[symbols['FuelLevel']], fuel_price=memory[symbols['FuelPrice']],
                             fuel_gauge=memory[symbols['FuelGauge']], drawn_gauge=memory[symbols['FuelGauge'] - 1],
                             fuel_line=fuel_line,
                             cash_tenths=int.from_bytes(memory[symbols['CashLow']:symbols['CashLow'] + 2], 'little'))
    equip, buy, launch = results['fuel-fix-equip'], results['fuel-fix-buy'], results['fuel-fix-launch']
    assert equip['fuel_line'].split()[-1] == '4.6' and equip['fuel_level'] == 34, equip
    assert equip['cash_tenths'] - buy['cash_tenths'] == 46, (equip, buy)   # 4.6 Cr paid
    assert buy['fuel_level'] == FULL and buy['fuel_line'].split()[-1] == '0.0', buy
    assert (launch['fuel_level'], launch['fuel_gauge'], launch['drawn_gauge']) == (34, 76, 76), launch
    print(f"PASS: 48K emulator: 3.4 LY lists fuel at {equip['fuel_line'].split()[-1]}, buying costs 4.6, fills "
          f"the tank and lists 0.0, launch sets the FU bar to {launch['fuel_gauge']}.", flush=True)
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
