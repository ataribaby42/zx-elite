"""Execute station, police and hermit launch regressions in ZX Spectrum 48K RAM.

Uses the current assembled image, and a baseline differing only in the original
38-byte selector. Exhaustive seed sweeps include the preceding launch gate;
testing the isolated final RNG call would miss the original correlation bug.
"""
from collections import Counter
import json
import sys
from tape import ROOT, ANALYSIS_DEPS, reference, sha
from build import symbol_map

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import PC, SP, A, F, C, IXh, IXl, IYh, IYl


def main():
    symbols = symbol_map(ROOT/'build/game.map')
    image = (ROOT/'build/game.bin').read_bytes()
    base = symbols['GameImage']
    start, end = symbols['L_F44A'], symbols['L_F470']
    assert symbols['STATION_RANDOM_LAUNCH_FIX'] == 1, 'Build stationrandomlaunchfix=yes first'
    assert (start, end, end-start) == (0xF44A, 0xF470, 38)
    directory = ROOT/'build/station-random-launch-check'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/f'{"adder" if symbols["SHIP_ADDER"] else "krait"}.json'
    output.unlink(missing_ok=True)
    original = reference()[1][5].payload
    baseline = bytearray(image)
    baseline[start-base:end-base] = original[start-base:end-base]
    rom = (ROOT/'assets/zxspectrum48k.rom').read_bytes()
    assert len(rom) == 0x4000
    seed_address = symbols['L_ED35']
    parent = symbols['InitialRuntimeState']
    stack = 0x5CF0  # Test-only stack below the runtime font.

    def memory(payload):
        ram = [0]*65536
        ram[:len(rom)] = rom
        ram[base:base+len(payload)] = payload
        return ram

    def header(ram, ship_id):
        table = symbols['ShipBlueprintsAndDispatchTables']
        offset = table+ship_id*(2 if symbols['SHIP_ADDER'] else 4)
        if not symbols['SHIP_ADDER']:
            offset += 1
        return ram[offset]+256*ram[offset+1]

    def sweep(payload, entry, hostile=False, special=False, count=0, subtype=0, ship_id=0):
        ram = memory(payload)
        ram[parent+0x26] = 4
        ram[parent+0x21] = 4 if hostile else 0
        ram[parent+0x20] = 6
        ram[symbols['L_DA1B']] = count
        ram[symbols['L_A871']] = 4 if special else 0
        ram[symbols['L_DA16']] = 0
        blueprint = header(ram, ship_id)
        sim = Simulator(ram)
        r = sim.registers
        results = []
        for seed in range(65536):
            ram[seed_address:seed_address+2] = [seed&255, seed>>8]
            ram[stack:stack+2] = [0, 0]
            r[PC], r[SP], r[F], r[C] = symbols[entry], stack, 0, subtype
            r[IXh], r[IXl] = parent>>8, parent&255
            r[IYh], r[IYl] = blueprint>>8, blueprint&255
            calls = 0
            for _ in range(200):
                pc = r[PC]
                if pc == end or pc in (0, symbols['L_F7DF']):
                    results.append((r[A] if pc == end else None,
                                    ram[seed_address]+256*ram[seed_address+1], calls))
                    break
                calls += pc == symbols['L_ED24']
                sim.opcodes[ram[pc]]()
            else:
                raise AssertionError(('Selection did not terminate', entry, seed))
        return results

    def counts(results):
        return dict(Counter('no launch' if row[0] is None else str(row[0]) for row in results))

    checks = {}
    for count in (0, 3, 4):
        before = sweep(baseline, 'L_F846', count=count)
        after = sweep(image, 'L_F846', count=count)
        assert all(b[1:] == a[1:] and (b[0] is None) == (a[0] is None)
                   for b, a in zip(before, after)), 'Station gate or RNG advancement changed'
        expected = {'no launch': 65536} if count == 4 else {'9': 256, '10': 256, 'no launch': 65024}
        assert counts(after) == expected
        assert counts(before) == ({'no launch': 65536} if count == 4 else {'10': 512, 'no launch': 65024})
        checks[f'calm_station_count_{count}'] = dict(before=counts(before), after=counts(after))
    print('PASS: all 65,536 seeds at each calm-station gate; Cobra/Python 256/256; RNG progression unchanged.', flush=True)

    # Includes the hostile gate and special-mode alternate Thargoid branch.
    for special in (False, True):
        for count in (0, 3, 4):
            before = sweep(baseline, 'L_F846', hostile=True, special=special, count=count)
            after = sweep(image, 'L_F846', hostile=True, special=special, count=count)
            assert after == before, ('Police station changed', special, count)
            assert all(row[0] in (None, 15 if special else 8) for row in after)
            if count < 4:
                assert any(row[0] is not None for row in after)
            checks[f'hostile_station_special_{special}_count_{count}'] = counts(after)
    print('PASS: police Viper and special-mode launches match original for every seed and both sides of the AI-count limit.', flush=True)

    for ship_id, name, types in ((7, 'rock_hermit', {16, 17}), (15, 'thargoid', {18})):
        before = sweep(baseline, 'L_F780', ship_id=ship_id)
        after = sweep(image, 'L_F780', ship_id=ship_id)
        assert after == before, name+' launch choice or RNG sequence changed'
        assert {row[0] for row in after} == types | {None}
        checks[name] = counts(after)
    print('PASS: rock hermit Sidewinder/Krait-or-Adder and Thargoid/Thargon gates match original for every seed.', flush=True)

    # Continue through actual allocation, blueprint loading, inherited attitude
    # and parent rotation, including no-free-slot returns. No instructions mocked.
    allocation_cases = 0
    trader_types = set()
    for subtype, ship_id in ((1, 0), (2, 0), (3, 15), (4, 0), (5, 7)):
        for occupied in (0, 5, 6):
            for hostile in (False, True):
                for seed in (0, 1, 255, 256, 257, 0x1234, 0x8000, 0xFFFF):
                    outcomes = []
                    for payload in (baseline, image):
                        ram = memory(payload)
                        p = parent if ship_id == 0 else parent+0x27
                        for slot in range(1, 7):
                            ram[parent+slot*0x27+0x22] = 100 if slot <= occupied else 0
                        ram[p:p+0x1B] = [(i*7+3)&255 for i in range(0x1B)]
                        ram[p+0x22] = 200
                        ram[p+0x21] = 4 if hostile else 0
                        ram[p+0x26] = 4 if ship_id == 0 else 0
                        ram[p+0x23:p+0x25] = header(ram, ship_id).to_bytes(2, 'little')
                        ram[seed_address:seed_address+2] = seed.to_bytes(2, 'little')
                        ram[stack:stack+2] = [0, 0]
                        sim = Simulator(ram, {'PC': symbols['L_F876'], 'SP': stack,
                                               'IX': p, 'IY': header(ram, ship_id),
                                               'A': subtype*16+4, 'F': 0})
                        r = sim.registers
                        selected = None
                        for _ in range(10000):
                            pc = r[PC]
                            if pc == end:
                                selected = r[A]
                            if pc == 0:
                                break
                            sim.opcodes[ram[pc]]()
                        else:
                            raise AssertionError('Full allocation did not return')
                        assert r[SP] == stack+2
                        assert r[IXh]*256+r[IXl] == p, 'Parent IX not restored'
                        assert bool(r[F]&0x40) == (occupied != 6), 'Wrong allocation success flag'
                        if occupied != 6:
                            expected_header = header(ram, selected)
                            children = [parent+n*0x27 for n in range(1, 7)
                                        if parent+n*0x27 != p and ram[parent+n*0x27+0x22] != 0
                                        and ram[parent+n*0x27+0x23:parent+n*0x27+0x25] == list(expected_header.to_bytes(2, 'little'))]
                            assert len(children) == 1, ('Missing or duplicate child', subtype, selected)
                            child = children[0]
                            if hostile:
                                assert ram[child+0x21]&4, 'Parent hostility lost'
                            if subtype == 2:
                                trader_types.add(selected)
                        # Ignore executable differences and popped stack residue.
                        ram[start:end] = [0]*(end-start)
                        ram[0x5C00:0x5D00] = [0]*0x100
                        outcomes.append((bytes(ram), tuple(r[:12]), r[SP]))
                    if subtype != 2:
                        assert outcomes[0] == outcomes[1], ('Allocation state changed', subtype, occupied, hostile, seed)
                    allocation_cases += 1
    assert trader_types == {9, 10}
    checks['full_allocation_cases'] = allocation_cases
    print(f'PASS: {allocation_cases} paired full-allocation cases, including Vipers, hermit fighters, Thargons and full slots.', flush=True)
    output.write_text(json.dumps(dict(passed=True, machine='ZX Spectrum 48K',
        game_sha256=sha(image), replacement_bytes=end-start, added_bytes=0,
        seeds_per_sweep=65536, checks=checks), indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
