"""Aggregate verified 48K emulator runs into source seeds and a code map."""
import json
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
    access_rows = []
    union_unclassified_reads = set()
    for name, description in ACCESS_REPORTS.items():
        report = load_report(name)
        reads = {address for address in report.get('memory_read_map', []) if start <= address < end}
        writes = {address for address in report.get('memory_write_map', []) if start <= address < end}
        if not reads or not writes:
            raise SystemExit(f'{name}: memory-access maps are missing')
        read_counts = {kind: sum(kind_at(reconstruction['ranges'], address) == kind for address in reads)
                       for kind in ('code', 'data', 'unclassified')}
        write_counts = {kind: sum(kind_at(reconstruction['ranges'], address) == kind for address in writes)
                        for kind in ('code', 'data', 'unclassified')}
        unclassified_reads = {address for address in reads
                              if kind_at(reconstruction['ranges'], address) == 'unclassified'}
        union_unclassified_reads.update(unclassified_reads)
        access_rows.append({
            'name': name,
            'description': description,
            'read_counts': read_counts,
            'write_counts': write_counts,
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
    lines += ['', '## Memory-access evidence', '',
              "The access runs use SkoolKit's slower Python Z80 simulator with a",
              'list-compatible memory recorder. Opcode fetches explain most reads in',
              'candidate-code ranges. Reads from unclassified ranges identify likely',
              'tables, text, models or mutable workspace for further analysis.', '',
              '| Scenario | Image reads | Unclassified reads | Image writes | Unclassified writes | Writes in candidate code |',
              '|---|---:|---:|---:|---:|---:|']
    for row in access_rows:
        reads = row['read_counts']; writes = row['write_counts']
        lines.append(f"| `{row['name']}` | {sum(reads.values()):,} | {reads['unclassified']:,} | {sum(writes.values()):,} | {writes['unclassified']:,} | {writes['code']:,} |")
    top_reads = sorted(compact(union_unclassified_reads, 1), key=lambda item: item['count'], reverse=True)[:12]
    lines += ['', 'Largest contiguous unclassified regions actually read:', '']
    for item in top_reads:
        lines.append(f"- `${item['first']:04X}-${item['last']:04X}`: {item['count']:,} observed byte addresses")
    lines += ['', '## Reproduction', '',
              'Run the scripted text-only scenarios, then aggregate and rebuild:', '', '```bat',
              'python tools\\run_runtime_scenarios.py',
              'python tools\\run_runtime_scenarios.py --accesses',
              'python tools\\analyze_runtime.py',
              'python tools\\bootstrap_sources.py --force',
              'build.bat', 'verify.bat', '```', '',
              'The detailed key timings, RAM test interventions, final text rows and',
              'address windows are retained in `build/emulator/*.json` and the',
              'generated `docs/generated/runtime-map.json`.', '']
    (ROOT / 'docs' / 'RUNTIME-MAP.md').write_text('\n'.join(lines), encoding='ascii', newline='\n')
    print(f'Aggregated {len(reports)} ZX Spectrum 48K scenarios: {len(union)} distinct game PCs.')
    print(f'Added {len(set(seeds)-previous)} new instruction starts; {len(seeds)} persistent runtime seeds.')

if __name__ == '__main__':
    main()
