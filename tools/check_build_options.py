"""Exercise the build options; leave Adder/single/48K with every fix built.

Default mode uses single-option builds and a pairwise covering array:

1. The default build must reproduce the reference tape.
2. Every non-default value alone, in both verification modes: the strict build
   fails and leaves no release or PASS report; the relaxed build changes only
   the bytes that option declares.  Laser and font bytes are compared with
   independent sources (the owner's patch note and PATCH128.TAP).
3. Declared areas are disjoint except for the competition -> rotation -> docking
   dependency chain. Docking uses only three padding gaps within rotation.
   Dependent payloads take precedence inside their declared shared regions.
4. Combinations: a covering array in which every pair of values of two
   options is built together at least once (two includes that clash on a
   symbol or an assertion fail there); every option on at once for each ship
   and non-default font; finally Adder/single/48K with every fix.  Each
   relaxed build must equal the reference, or the Adder build, with the
   selected options' bytes overlaid; each strict build must fail.
5. Invalid values of every option, strict verify-only, and corrupt TAPs that
   must fail even with identity checks off.

--full builds the complete product of all values instead of step 4's
selection (1,048,576 requested combinations). Use it after changing the
build machinery itself.
"""
import argparse
from itertools import combinations as pairs_of, product
import json
import subprocess
import sys
from tape import ROOT, RELEASE_TAP, frame, parse, reference, sha
from build import symbol_map, verify
from font_variant import patch_font, fixed_font

# Option name -> values; the first value is the default.
OPTIONS = (
    ('ship', ('krait', 'adder')),
    ('laser', ('original', 'single')),
    ('font', ('128', '48', '128fix', '128fix_ecm_s')),
    ('scannerpixelfix', ('no', 'yes')),
    ('stationrandomlaunchfix', ('no', 'yes')),
    ('stationslotfix', ('no', 'yes')),
    ('fuelfix', ('no', 'yes')),
    ('hyperspacedockingfix', ('no', 'yes')),
    ('aicouragefix', ('no', 'yes')),
    ('scannerblipfix', ('no', 'yes')),
    ('stardustfix', ('no', 'yes')),
    ('missiletargetfix', ('no', 'yes')),
    ('textfullstopfix', ('no', 'yes')),
    ('iffunit', ('no', 'yes')),
    ('randomizedspawn', ('no', 'yes')),
    ('competitionremove', ('no', 'yes')),
    ('rotationdriftfix', ('no', 'yes')),
    ('dockingrotation', ('no', 'yes')),
    ('trafficcontrol', ('no', 'yes')),
)
NAMES = tuple(name for name, _ in OPTIONS)
DEFAULT = tuple(values[0] for _, values in OPTIONS)
FIX_NAMES = tuple(name for name, values in OPTIONS if values == ('no', 'yes'))
ALL_FIXES = ('yes',) * len(FIX_NAMES)
FINAL = ('adder', 'single', '48') + ALL_FIXES
# Areas a fix replaces: Start/Limit constant prefixes in src/options.asm, with the
# original addresses they must keep.
FIX_PARTS = {
    'trafficcontrol': (('TrafficControlHook', 'TrafficControlProximity', 'TrafficControlXY', 'TrafficControlZ'),
                       [(0xF871, 0xF876), (0xF882, 0xF8A2), (0x7818, 0x781F), (0x91CC, 0x91D2)]),
    'competitionremove': (('CompetitionSecurity', 'CompetitionParity'), [(0xD386, 0xD3E2), (0xD3F0, 0xD3FF)]),
    'rotationdriftfix': (('CompetitionSecurity', 'CompetitionParity', 'RotationDriftRotation', 'RotationDriftProduct',
                        'RotationDriftHighMultiply', 'RotationDriftMidMultiply', 'RotationDriftLowMultiply'),
                       [(0xD386, 0xD3E2), (0xD3F0, 0xD3FF), (0xDED1, 0xDF0B), (0xDF80, 0xDF84),
                        (0xDF64, 0xDF67), (0xDF6B, 0xDF6E), (0xDF78, 0xDF7B)]),
    'dockingrotation': (('DockingRotationHook', 'DockingRotationLoad', 'DockingRotationCompare',
                         'DockingRotationAccept'),
                        [(0xEB0A, 0xEB10), (0xD3DD, 0xD3E2), (0xD3F7, 0xD3FF), (0xDF05, 0xDF0B)]),
    'stationrandomlaunchfix': (('ParentLaunchSelection',), [(0xF44A, 0xF470)]),
    'stationslotfix': (('StationSwitchOnStore', 'StationSlotAlign', 'StationSlotRoof', 'StationSlotFinish'),
                       [(0x77CB, 0x77CE), (0xE88B, 0xE8CF), (0xAC56, 0xAC77), (0xFCED, 0xFD00)]),
    'fuelfix': (('FuelLaunchHook', 'FuelPriceHook', 'FuelPricePart', 'FuelEconomyPart', 'FuelStorePart'),
                [(0x7B85, 0x7B88), (0xB53F, 0xB542), (0xB31B, 0xB32B), (0xA89B, 0xA8AA), (0x9A3A, 0x9A46)]),
    'hyperspacedockingfix': (('HyperspaceDockingCheck',), [(0x70BE, 0x70C1)]),
    'aicouragefix': (('AiCourageHit',), [(0xEC6A, 0xEC7D)]),
    'scannerblipfix': (('ScannerBlipStep', 'ScannerBlipCentre', 'ScannerBlipGuard'),
                       [(0x8CE0, 0x8CF3), (0x8D0B, 0x8D0D), (0x8DCC, 0x8DDE)]),
    'stardustfix': (('StardustPixel',), [(0xA2EF, 0xA334)]),
    'missiletargetfix': (('MissileTargetCheck',), [(0xEB82, 0xEB86)]),
    'textfullstopfix': (('TextFullStopBuffer', 'TextFullStopHook'), [(0xBCFC, 0xBD1B), (0xBDF5, 0xBE00)]),
    'iffunit': (('IffScannerHook', 'IffBombVector', 'IffScannerCode', 'IffUnitText', 'IffBlinkHook',
                 'IffShipCode', 'IffObjectsTail', 'IffBombKey'),
                [(0x8C3D, 0x8C40), (0x91C9, 0x91CC), (0x9260, 0x9280), (0x9D84, 0x9E74),
                 (0xA568, 0xA56B), (0xDAC1, 0xDAD8), (0xDBC8, 0xDBD5), (0xFF72, 0xFF74)]),
    'randomizedspawn': (('RandomizedSpawnIdPush', 'RandomizedSpawnPlacement', 'RandomizedSpawnAspEntry',
                         'RandomizedSpawnRequest', 'RandomizedSpawnHermit'),
                        [(0xF2FE, 0xF2FF), (0xF338, 0xF356), (0xF653, 0xF655), (0xF6C8, 0xF6DB),
                         (0xF6FB, 0xF70E)]),
}
LASER_PATCH = bytes.fromhex('21 3f 00 79 f6 03 4f c3')  # + DrawLine, the owner's final ten-byte patch


def effective_values(row):
    """Independent expectation for requested vs effective build settings."""
    values = dict(zip(NAMES, row))
    if values['dockingrotation'] == 'yes':
        values['rotationdriftfix'] = 'yes'
    if values['rotationdriftfix'] == 'yes':
        values['competitionremove'] = 'yes'
    return values


def covering_rows():
    """Deterministic greedy covering array: every pair of values of two options at least once."""
    levels = [len(values) for _, values in OPTIONS]
    uncovered = {(i, a, j, b) for i, j in pairs_of(range(len(levels)), 2)
                 for a in range(levels[i]) for b in range(levels[j])}
    total, rows = len(uncovered), []
    while uncovered:
        i, a, j, b = min(uncovered)
        row = [None] * len(levels)
        row[i], row[j] = a, b
        for k in range(len(levels)):
            if row[k] is None:
                row[k] = max(range(levels[k]), key=lambda v: (sum(
                    (min(k, m), v if k < m else row[m], max(k, m), row[m] if k < m else v) in uncovered
                    for m in range(len(levels)) if row[m] is not None and m != k), -v))
        uncovered -= {(m, row[m], n, row[n]) for m, n in pairs_of(range(len(levels)), 2)}
        rows.append(tuple(OPTIONS[k][1][row[k]] for k in range(len(levels))))
    return rows, total


def selected_rows(full):
    if full:
        rows, pairs = list(product(*(values for _, values in OPTIONS))), None
    else:
        rows, pairs = covering_rows()
        rows += [(ship, 'single', font) + ALL_FIXES for ship in ('krait', 'adder')
                 for font in ('48', '128fix', '128fix_ecm_s')]
        # Exercise every requested state of the three-option dependency chain,
        # including explicit no values overridden by a dependent yes.
        for values in product(('no', 'yes'), repeat=3):
            selected = dict(zip(NAMES, DEFAULT))
            selected.update(zip(('competitionremove', 'rotationdriftfix', 'dockingrotation'), values))
            rows.append(tuple(selected[n] for n in NAMES))
    ordered = []
    for row in rows:
        if row not in ordered and row != FINAL:
            ordered.append(row)
    return ordered + [FINAL], pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--full', action='store_true', help='build the complete product of all option values')
    full = parser.parse_args().full
    directory = ROOT/'build/build-options-check'
    directory.mkdir(parents=True, exist_ok=True)
    report = directory/'verification.json'
    report.unlink(missing_ok=True)
    builds = [0]

    def run(name, *args, success=True):
        result = subprocess.run([sys.executable, str(ROOT/'tools/build.py'), *args], cwd=ROOT,
                                capture_output=True, text=True)
        (directory/f'{name}.log').write_text(result.stdout+result.stderr, encoding='utf-8')
        assert (result.returncode == 0) == success, result.stdout+result.stderr
        builds[0] += 1
        return result

    def label(row):
        """Short log name (Windows paths): changed non-fix values, then one digit per fix."""
        values = dict(zip(NAMES, row))
        parts = [f'{name}{value}' for name, value, default in zip(NAMES, row, DEFAULT)
                 if value != default and name not in FIX_NAMES]
        fixes = ''.join('1' if values[name] == 'yes' else '0' for name in FIX_NAMES)
        if '1' in fixes:
            parts.append('fixes' + fixes)
        return '-'.join(parts) or 'defaults'

    def build_both(row):
        """Strict build (must fail unless row is the default), then the relaxed build."""
        name = label(row)
        exact = row == DEFAULT
        result = run(name+'-exact', *(f'{n}={v}' for n, v in zip(NAMES, row)), 'verify=yes', success=exact)
        if not exact:
            assert 'Binary identity FAILED' in result.stderr
            assert not RELEASE_TAP.exists(), 'Failed build left a stale release'
            assert not (ROOT/'build/verification.json').exists()
        run(name+'-relaxed', *(arg for n, v in zip(NAMES, row) for arg in (f'--{n}', v)), '--verify', 'no')
        metadata = json.loads((ROOT/'build/verification.json').read_text())
        assert {n: metadata[n] for n in NAMES} == effective_values(row), (row, metadata)
        assert metadata['competitionremove_requested'] == dict(zip(NAMES, row))['competitionremove']
        assert metadata['rotationdriftfix_requested'] == dict(zip(NAMES, row))['rotationdriftfix']
        built = symbol_map(ROOT/'build/game.map')
        assert built['COMPETITION_REMOVE'] == int(effective_values(row)['competitionremove'] == 'yes')
        assert built['ROTATION_DRIFT_FIX'] == int(effective_values(row)['rotationdriftfix'] == 'yes')
        assert built['DOCKING_ROTATION'] == int(effective_values(row)['dockingrotation'] == 'yes')
        assert built['TRAFFIC_CONTROL'] == int(effective_values(row)['trafficcontrol'] == 'yes')
        return RELEASE_TAP.read_bytes()

    # 1. Defaults.
    run('defaults')
    reference_tap = reference()[0]
    assert RELEASE_TAP.read_bytes() == reference_tap
    reference_payload = parse(reference_tap)[5].payload
    symbols = symbol_map(ROOT/'build/game.map')
    base = symbols['GameImage']

    def offsets(start, end):
        return range(start-base, end-base)

    # 2. Every non-default value alone.
    single = {}
    for index, (name, values) in enumerate(OPTIONS):
        for value in values[1:]:
            row = DEFAULT[:index] + (value,) + DEFAULT[index+1:]
            single[name, value] = (row, build_both(row), symbol_map(ROOT/'build/game.map'))
    adder_tap = single['ship', 'adder'][1]
    areas = {}
    for name, (prefixes, expected) in FIX_PARTS.items():
        built = single[name, 'yes'][2]
        found = [(built[f'{p}Start'], built[f'{p}Limit']) for p in prefixes]
        assert found == expected, (name, found)
        areas[name] = found
    scanner_symbols = single['scannerpixelfix', 'yes'][2]
    scanner_image = parse(single['scannerpixelfix', 'yes'][1])[5].payload
    areas['scannerpixelfix'] = [(scanner_symbols['L_A660'], scanner_symbols['CockpitIndicatorsLimit'])]
    # Only the instrument region and its two existing call/jump operands may change.
    for address, opcode, target in ((scanner_symbols['L_9A46'], 0xCD, 'L_A6D3'),
                                     (scanner_symbols['L_A777'], 0xC3, 'L_A6D3')):
        assert scanner_image[address-base] == opcode
        assert scanner_image[address-base+1:address-base+3] == scanner_symbols[target].to_bytes(2, 'little')
        areas['scannerpixelfix'].append((address+1, address+3))
    areas['laser'] = [(symbols['LaserPatchSite'], symbols['LaserPatchSite']+len(LASER_PATCH)+2)]
    areas['font'] = [(symbols['FontBitmap'], symbols['FontBitmapEnd'])]
    overlay = {name: parse(single[name, 'yes'][1])[5].payload for name in FIX_PARTS}
    overlay['scannerpixelfix'] = scanner_image

    def expected(row):
        """The reference (or the Adder build) with the selected options' bytes overlaid."""
        values = effective_values(row)
        blocks = parse(adder_tap if values['ship'] == 'adder' else reference_tap)
        payload = bytearray(blocks[5].payload)
        if values['laser'] == 'single':
            patch = LASER_PATCH+symbols['DrawLine'].to_bytes(2, 'little')
            start = symbols['LaserPatchSite']-base
            payload[start:start+len(patch)] = patch
        if values['font'] != '128':
            start, end = symbols['FontBitmap']-base, symbols['FontBitmapEnd']-base
            font = patch_font()[0] if values['font'] == '48' else \
                fixed_font(bytes(payload[start:end]), ecm_s=values['font'] == '128fix_ecm_s')
            assert len(font) == end-start
            payload[start:end] = font
        for name, image in overlay.items():
            # The dependent option supplies the complete shared-region payload;
            # do not let the standalone removal's padding erase its helpers.
            if name == 'competitionremove' and values['rotationdriftfix'] == 'yes':
                continue
            if values[name] == 'yes':
                for start, end in areas[name]:
                    payload[start-base:end-base] = image[start-base:end-base]
        return b''.join(frame(b.flag, bytes(payload) if i == 5 else b.payload) for i, b in enumerate(blocks))

    singles = []
    for (name, value), (row, tap, _) in single.items():
        if name != 'ship':
            assert tap == expected(row), f'{name}={value}: bytes outside its declared areas changed'
        singles.append(dict(option=name, value=value, relaxed_sha256=sha(tap)))

    # 3. Only explicit dependency regions may overlap. The docking helper's
    # three parts are wholly inside the rotation padding, not arbitrary code.
    adder_payload = parse(adder_tap)[5].payload
    claimed = {name: {address for start, end in found for address in range(start, end)}
               for name, found in areas.items()}
    claimed['ship'] = {base+i for i, (a, b) in enumerate(zip(reference_payload, adder_payload)) if a != b}
    docking_gaps = {address for start, end in areas['dockingrotation'][1:] for address in range(start, end)}
    competition_gaps = {address for start, end in areas['dockingrotation'][1:3] for address in range(start, end)}
    shared = {('competitionremove', 'rotationdriftfix'): claimed['competitionremove'],
              ('competitionremove', 'dockingrotation'): competition_gaps,
              ('dockingrotation', 'rotationdriftfix'): docking_gaps}
    rotation_payload = overlay['rotationdriftfix']
    assert all(rotation_payload[a-base] == 0 for a in docking_gaps), 'docking must reuse padding only'
    for first, second in pairs_of(sorted(claimed), 2):
        common = claimed[first] & claimed[second]
        if (first, second) in shared:
            assert common == shared[first, second], ('incorrect dependency overlap', first, second)
            continue
        assert not common, (first, second, sorted(f'${a:04X}' for a in common)[:8])

    # 4. Combinations.
    rows, pairs = selected_rows(full)
    combinations = []
    for row in rows:
        tap = build_both(row)
        assert tap == expected(row), f'{label(row)}: the build is not the sum of its options'
        combinations.append(dict(zip(NAMES, row), competitionremove_effective=effective_values(row)['competitionremove'],
                                 rotationdriftfix_effective=effective_values(row)['rotationdriftfix'],
                                 strict_accepted=row == DEFAULT, relaxed_sha256=sha(tap)))
    assert rows[-1] == FINAL

    # 5. Invalid values, strict verify-only and corrupt TAPs.
    invalid = {'ship': 'cobra', 'laser': 'double', 'font': '47'}
    for name in NAMES:
        run(f'invalid-{name}', f'{name}={invalid.get(name, "maybe")}', success=False)
    good = RELEASE_TAP.read_bytes()
    failed = run('verify-exact-rejected', '--verify-only', success=False)
    assert 'Binary identity FAILED' in failed.stderr
    assert not (ROOT/'build/verification.json').exists()
    # Corrupt the checksum, then a header with a correctly recalculated XOR.
    # Both must fail even when original-byte comparison is switched off.
    checksum = bytearray(good)
    checksum[-1] ^= 1
    blocks = parse(good)
    changed = bytearray(blocks[4].payload)
    changed[13] ^= 1
    bad_header = b''.join(frame(b.flag, bytes(changed) if i == 4 else b.payload) for i, b in enumerate(blocks))
    for name, contents in [('bad-checksum', checksum), ('bad-header', bad_header), ('truncated', good[:-1])]:
        path = directory/f'{name}.tap'
        path.write_bytes(contents)
        try:
            try:
                verify(path, exact=False)
            except ValueError:
                pass
            else:
                raise AssertionError(name+' was accepted with verify=no')
        finally:
            path.unlink()
    run('verify-relaxed', '--verify-only', 'verify=no')
    assert RELEASE_TAP.read_bytes() == good

    report.write_text(json.dumps(dict(
        passed=True, strategy='full product' if full else 'pairwise covering array',
        value_pairs_covered=pairs, builds=builds[0], single_option_builds=singles,
        declared_areas={name: [f'${s:04X}..${e-1:04X}' for s, e in found] for name, found in sorted(areas.items())},
        adder_changed_bytes=len(claimed['ship']), areas_pairwise_disjoint=False,
        independent_areas_disjoint=True,
        declared_dependency=dict(rotationdriftfix='competitionremove', dockingrotation='rotationdriftfix'),
        combinations=combinations, invalid_values_rejected=list(NAMES),
        corrupt_tapes_rejected_without_identity=True,
        final=dict(zip(NAMES, FINAL)), final_tape_sha256=sha(good)), indent=2)+'\n', encoding='utf-8')
    scope = 'the complete product' if full else f'all {pairs} value pairs and every option on at once'
    print(f'PASS: {len(singles)} single-option builds scoped to declared areas (only declared dependencies share); {len(rows)} combinations covering '
          f'{scope}, each the sum of its options; strict rejection, stale-output handling, invalid values and '
          f'corrupt TAP rejection ({builds[0]} builds).')


if __name__ == '__main__':
    main()
