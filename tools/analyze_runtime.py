"""Aggregate verified 48K emulator runs into source seeds and a code map."""
import json
import textwrap
from pathlib import Path

from tape import ROOT, REFERENCE_SHA256

MACHINE = 'ZX Spectrum 48K'
REPORTS = {
    'docked-baseline': 'Docked status screen after starting Commander Jameson',
    'docked-market': 'Docked market-prices screen',
    'docked-inventory': 'Docked inventory screen',
    'docked-equipment': 'Docked equipment-purchase screen',
    'docked-system-data': 'Docked system-data screen',
    'docked-local-chart': 'Docked short-range chart',
    'docked-galactic-chart': 'Docked galactic chart',
    'trade-complete': 'Bought 5 t of food, sold 2 t and verified 3 t in inventory',
    'buy-large-cargo': 'Bought a Large Cargo Bay and verified it on the status screen',
    'buy-fuel-scoops': 'Bought Fuel Scoops and verified them on the status screen',
    'equip-tech10': 'Displayed the complete Tech Level 10 equipment list',
    'buy-galactic-hyperdrive': 'Bought a Galactic Hyperdrive and verified it on the status screen',
    'inflight-screens': 'Front/left/right views plus charts, data, market, status and inventory in flight',
    'inflight-back-view': 'Rear view in flight',
    'hyperspace-diso': 'Normal hyperspace from Lave to Diso',
    'hyperspace-reorte': 'Normal hyperspace from Lave to Reorte',
    'hyperspace-zaonce': 'Normal hyperspace from Lave to Zaonce',
    'galactic-hyperspace-overlap': 'Galactic hyperspace from Lave in galaxy 1 to Inoran in galaxy 2',
}
ACCESS_REPORTS = {
    'access-docked-baseline': 'Docked status baseline',
    'access-docked-market': 'Market prices',
    'access-docked-equipment': 'Equipment list',
    'access-trade-complete': 'Complete buy/sell transaction',
    'access-inflight-screens': 'In-flight views and information screens',
    'access-hyperspace-zaonce': 'Normal hyperspace to Zaonce',
    'access-galactic-hyperspace': 'Galactic hyperspace to Inoran',
}
KINDS = ('code', 'inline', 'data', 'unclassified')
# The view buffer starts at FontBitmap (ViewBitmapBuffer) and ends with
# CockpitBitmap (ViewBitmapBufferSecondHalf); these three are its tape sources.
VIEW_BUFFER_SOURCES = ('FontBitmap', 'CockpitAttributes', 'CockpitBitmap')
VIEW_BUFFER_RESIDUE = 'ViewBufferResidueAfterLoader'

def compact(addresses, gap=24):
    """Group sparse instruction starts into descriptive address windows."""
    windows = []
    for address in sorted(addresses):
        if windows and address - windows[-1]['last'] <= gap:
            windows[-1]['last'] = address
            windows[-1]['count'] += 1
        else:
            windows.append(dict(first=address, last=address, count=1))
    return windows

def kind_at(ranges, address):
    for item in ranges:
        if item['start'] <= address < item['end']:
            return item['kind']
    return 'outside'

def range_named(ranges, name):
    matches = [item for item in ranges if item.get('name') == name]
    if len(matches) != 1:
        raise SystemExit(f'reconstruction.json must contain exactly one range named {name}')
    return matches[0]

def range_at_label(reconstruction, name):
    addresses = [int(address, 16) for address, label in reconstruction['labels'].items()
                 if label == name]
    if len(addresses) != 1:
        raise SystemExit(f'reconstruction.json must contain exactly one label {name}')
    matches = [item for item in reconstruction['ranges'] if item['start'] == addresses[0]]
    if len(matches) != 1:
        raise SystemExit(f'No classified range starts at {name}')
    return matches[0]

def window_text(addresses):
    return ', '.join(f"`${item['first']:04X}-${item['last']:04X}`"
                     for item in compact(addresses, 1)) or 'none'

def wrap(text):
    return textwrap.wrap(text, 74, break_on_hyphens=False, break_long_words=False)

def load_report(name):
    path = ROOT / 'build' / 'emulator' / f'{name}.json'
    if not path.exists():
        raise SystemExit(f'Missing emulator report: {path}')
    report = json.loads(path.read_text())
    if report.get('machine') != MACHINE:
        raise SystemExit(f'{name}: expected {MACHINE}, got {report.get("machine")!r}')
    if report.get('tape_sha256') != REFERENCE_SHA256:
        raise SystemExit(f'{name}: report does not use the reference-identical TAP')
    return report

def main():
    reconstruction_path = ROOT / 'docs' / 'generated' / 'reconstruction.json'
    reconstruction = json.loads(reconstruction_path.read_text())
    start = reconstruction['image_start']
    end = reconstruction['image_end_exclusive']
    reports = {name: load_report(name) for name in REPORTS}
    executions = {
        name: {address for address in report['execution_map'] if start <= address < end}
        for name, report in reports.items()
    }
    union = set().union(*executions.values())
    newly_proved = {address for address in union
                    if kind_at(reconstruction['ranges'], address) == 'unclassified'}

    seed_path = ROOT / 'src' / 'runtime-code-seeds.json'
    previous = set()
    if seed_path.exists():
        old = json.loads(seed_path.read_text())
        if old.get('reference_sha256') != REFERENCE_SHA256:
            raise SystemExit('Existing runtime seeds belong to a different reference TAP')
        previous = {int(value, 16) for value in old.get('instruction_addresses', [])}
    seeds = sorted(previous | newly_proved)
    seed_doc = {
        'machine': MACHINE,
        'reference_sha256': REFERENCE_SHA256,
        'evidence': 'Actual instruction PCs recorded by SkoolKit while running the unmodified game',
        'reports': list(REPORTS),
        'instruction_addresses': [f'0x{address:04X}' for address in seeds],
    }
    seed_path.write_text(json.dumps(seed_doc, indent=2) + '\n', encoding='ascii', newline='\n')

    baseline = executions['docked-baseline']
    scenario_rows = []
    for name, description in REPORTS.items():
        report = reports[name]
        game_pcs = executions[name]
        extra = game_pcs - baseline
        scenario_rows.append({
            'name': name,
            'description': description,
            'instructions_executed': report['operations'],
            'distinct_game_pcs': len(game_pcs),
            'additional_pcs_vs_docked_baseline': len(extra),
            'additional_address_windows': compact(extra),
            'test_pokes': report.get('test_pokes', []),
            'final_text': report.get('final_text', []),
        })
    sources = [range_named(reconstruction['ranges'], name) for name in VIEW_BUFFER_SOURCES]
    view_start = sources[0]['start']
    view_end = sources[-1]['end']
    view_sources = {address for item in sources for address in range(item['start'], item['end'])}
    residue = range_at_label(reconstruction, VIEW_BUFFER_RESIDUE)
    residue_addresses = set(range(residue['start'], residue['end']))
    view_code_ranges = [item for item in reconstruction['ranges']
                        if item['kind'] == 'code' and view_start <= item['start'] < view_end]
    view_code = {address for item in view_code_ranges
                 for address in range(item['start'], item['end'])}
    view_code_names = [reconstruction['labels'].get(f"{item['start']:04X}", f"L_{item['start']:04X}")
                       for item in view_code_ranges]
    view_code_executed = union & view_code
    access_rows = []
    union_unclassified_reads = set()
    union_view_read_before_write = set()
    view_matches_in_every_trace = True
    for name, description in ACCESS_REPORTS.items():
        report = load_report(name)
        reads = {address for address in report.get('memory_read_map', []) if start <= address < end}
        writes = {address for address in report.get('memory_write_map', []) if start <= address < end}
        if not reads or not writes or 'memory_read_before_write_map' not in report:
            raise SystemExit(f'{name}: memory-access maps are missing')
        read_counts = {kind: sum(kind_at(reconstruction['ranges'], address) == kind for address in reads)
                       for kind in KINDS}
        write_counts = {kind: sum(kind_at(reconstruction['ranges'], address) == kind for address in writes)
                        for kind in KINDS}
        if sum(read_counts.values()) != len(reads) or sum(write_counts.values()) != len(writes):
            raise SystemExit(f'{name}: an image address lies outside every classified range')
        unclassified_reads = {address for address in reads
                              if kind_at(reconstruction['ranges'], address) == 'unclassified'}
        union_unclassified_reads.update(unclassified_reads)
        view_read_before_write = {address for address in report['memory_read_before_write_map']
                                  if view_start <= address < view_end}
        union_view_read_before_write.update(view_read_before_write)
        view_matches_in_every_trace &= view_read_before_write == view_sources
        code_writes = {address for address in writes
                       if kind_at(reconstruction['ranges'], address) == 'code'}
        access_rows.append({
            'name': name,
            'description': description,
            'read_counts': read_counts,
            'write_counts': write_counts,
            'self_modifying_code_writes': len(code_writes - view_code),
            'view_buffer_code_overwrites': len(code_writes & view_code),
            'view_buffer_read_before_write_count': len(view_read_before_write),
            'largest_unclassified_read_windows': sorted(compact(unclassified_reads, 1),
                                                         key=lambda item: item['count'], reverse=True)[:12],
        })
    result = {
        'machine': MACHINE,
        'reference_sha256': REFERENCE_SHA256,
        'image_start': start,
        'image_end_exclusive': end,
        'scenario_count': len(reports),
        'distinct_runtime_instruction_addresses': len(union),
        'new_runtime_seeds_added_this_run': len(set(seeds) - previous),
        'instruction_addresses_proved_in_originally_unclassified_bytes': len(seeds),
        'persistent_runtime_seed_count': len(seeds),
        'runtime_address_windows': compact(union),
        'scenarios': scenario_rows,
        'memory_access_scenarios': access_rows,
        'largest_unclassified_runtime_read_windows': sorted(compact(union_unclassified_reads, 1),
                                                             key=lambda item: item['count'], reverse=True)[:24],
        'view_buffer_read_before_write': {
            'start': view_start,
            'end_exclusive': view_end,
            'tape_source_ranges': list(VIEW_BUFFER_SOURCES),
            'tape_source_bytes': len(view_sources),
            'matches_tape_sources_in_every_trace': view_matches_in_every_trace,
            'extra_addresses': compact(union_view_read_before_write - view_sources, 1),
            'residue_read_before_write': sorted(union_view_read_before_write & residue_addresses),
            'code_ranges': view_code_names,
            'code_addresses_executed': sorted(view_code_executed),
        },
    }
    generated = ROOT / 'docs' / 'generated' / 'runtime-map.json'
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(json.dumps(result, indent=2) + '\n', encoding='ascii', newline='\n')

    lines = [
        '# Runtime code and state map', '',
        'This map is generated from deterministic emulator runs of the rebuilt,',
        'byte-identical TAP in **ZX Spectrum 48K** mode with the supplied 48K ROM.',
        'No game instruction was patched. Test-only commander changes are listed',
        'explicitly in the JSON reports and were applied after normal startup.', '',
        f'- Scenarios: **{len(reports)}**',
        f'- Distinct executed instruction addresses in `$6048..$FFA8`: **{len(union):,}**',
        f'- Instruction addresses proved inside former `DEFB` regions: **{len(seeds):,}**',
        f'- Persistent runtime seeds used by source reconstruction: **{len(seeds):,}**', '',
        'An executed program counter proves that its address starts an instruction.',
        'It does not by itself explain the instruction semantically. A changed RAM',
        'byte proves mutable state or self-modifying code, so RAM differences must',
        'not be labelled as data without further evidence.', '',
        '## Exercised scenarios', '',
        '| Scenario | Verified action | Distinct game PCs | New vs docked baseline |',
        '|---|---|---:|---:|',
    ]
    for row in scenario_rows:
        lines.append(f"| `{row['name']}` | {row['description']} | {row['distinct_game_pcs']:,} | {row['additional_pcs_vs_docked_baseline']:,} |")
    lines += ['', '## Largest additional execution windows', '',
              'These are compact footprints of instruction starts reached in addition',
              'to the docked baseline. They locate active areas; they are not yet routine',
              'boundaries or semantic names.', '',
              '| Scenario | Four largest additional PC windows |', '|---|---|']
    for row in scenario_rows:
        windows = sorted(row['additional_address_windows'], key=lambda item: item['count'], reverse=True)[:4]
        display = ', '.join(f"`${item['first']:04X}-${item['last']:04X}` ({item['count']})" for item in windows) or '-'
        lines.append(f"| `{row['name']}` | {display} |")
    view_range = f'`${view_start:04X}..${view_end - 1:04X}`'
    if view_matches_in_every_trace:
        view_text = (f'In the view buffer {view_range} these are, in every access trace, '
                     f'exactly the {len(view_sources):,} bytes of the font, cockpit colours '
                     'and cockpit bitmap. All other buffer bytes, including '
                     f'`{VIEW_BUFFER_RESIDUE}`, are written before any read.')
    else:
        view_text = (f'In the view buffer {view_range} the traces do not match the '
                     f'{len(view_sources):,} font, cockpit-colour and cockpit-bitmap bytes. '
                     'Other buffer bytes read before any write: '
                     f'{window_text(union_view_read_before_write - view_sources)}.')
    view_code_text = ', '.join(f'`{name}`' for name in view_code_names) or 'none'
    view_code_status = ('none of it is executed in the traces' if not view_code_executed
                        else f'executed addresses: {window_text(view_code_executed)}')
    lines += ['', '## Memory-access evidence', '',
              *wrap("The access runs use SkoolKit's slower Python Z80 simulator with a "
                             'list-compatible memory recorder. Opcode fetches explain most reads in '
                             'code ranges. Kinds come from `docs/generated/reconstruction.json`; '
                             'inline arguments are bytes consumed by the preceding call. A read from '
                             'an unclassified range would identify a likely table, text, model or '
                             'mutable workspace for further analysis. Writes to code outside the '
                             'view buffer are self-modifying code. Code inside the view buffer '
                             f'({view_code_text}) is counted separately: it is overwritten when '
                             f'the buffer is reused, and {view_code_status}.'), '',
              *wrap('Each report also lists `memory_read_before_write_map`: addresses '
                             'read while they still hold their loaded value, so only there can '
                             f'the tape byte matter. {view_text}'), '',
              '| Scenario | Image reads | Unclassified reads | Image writes | Unclassified writes | Self-modifying code writes | Code overwritten in view buffer |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for row in access_rows:
        reads = row['read_counts']; writes = row['write_counts']
        lines.append(f"| `{row['name']}` | {sum(reads.values()):,} | {reads['unclassified']:,} | {sum(writes.values()):,} | {writes['unclassified']:,} | {row['self_modifying_code_writes']:,} | {row['view_buffer_code_overwrites']:,} |")
    top_reads = sorted(compact(union_unclassified_reads, 1), key=lambda item: item['count'], reverse=True)[:12]
    if top_reads:
        lines += ['', 'Largest contiguous unclassified regions actually read:', '']
        for item in top_reads:
            lines.append(f"- `${item['first']:04X}-${item['last']:04X}`: {item['count']:,} observed byte addresses")
    else:
        lines += ['', 'No unclassified region was read: every image byte is classified as code,',
                  'inline argument or data, so every recorded access falls in one of them.',
                  'A classified range is not necessarily understood; see `src/game.asm`',
                  'for the remaining neutral labels and `INFERRED:` hypotheses.']
    lines += ['', '## Reproduction', '',
              'Build and verify the default reconstruction first. The emulator loads',
              '`release/elite-128k.tap` and compares the loaded image with',
              '`build/game.bin`, so a previously built variant must not remain there.',
              'Then run the scripted text-only scenarios, aggregate and rebuild:', '', '```bat',
              'make.bat', 'verify.bat',
              'python tools\\run_runtime_scenarios.py',
              'python tools\\run_runtime_scenarios.py --accesses',
              'python tools\\analyze_runtime.py',
              'python tools\\bootstrap_sources.py --force',
              'make.bat', 'verify.bat', '```', '',
              'The detailed key timings, RAM test interventions, final text rows and',
              'address windows are retained in `build/emulator/*.json` and the',
              'generated `docs/generated/runtime-map.json`.', '']
    (ROOT / 'docs' / 'RUNTIME-MAP.md').write_text('\n'.join(lines), encoding='ascii', newline='\n')
    print(f'Aggregated {len(reports)} ZX Spectrum 48K scenarios: {len(union)} distinct game PCs.')
    print(f'Added {len(set(seeds)-previous)} new instruction starts; {len(seeds)} persistent runtime seeds.')

if __name__ == '__main__':
    main()
