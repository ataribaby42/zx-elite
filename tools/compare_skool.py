"""Compare an external SkoolKit disassembly of this release with the project.

The external .skool file is only read; nothing from it is copied into the
source.  Usage, after a regeneration (docs/generated/reconstruction.json):

    python tools/compare_skool.py path/to/elite.skool

It compares, for the game image $6048..$FFA8:

- code/data classification byte by byte (ours: code, inline argument bytes,
  typed or verified data, unclassified);
- instruction boundaries inside code that both sides decode;
- which addresses carry descriptive labels on each side.

The machine-readable result is docs/generated/skool-comparison.json.  It also
records the external label and comment text by address, for local review
only; that file is ignored by Git.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from tape import ROOT

BASE, END = 0x6048, 0xFFA9
LINE = re.compile(r'^([bctwsuig\*@ ])\$([0-9A-F]{4}) ?(.*)$')


def read_skool(path):
    kind, label, title, comment = {}, {}, {}, {}
    pending, block, buffer = None, None, []
    for line in path.read_text(encoding='utf-8', errors='replace').split('\n'):
        if line.startswith('@label='):
            pending = line.split('=', 1)[1].strip()
            continue
        if line.startswith(';'):
            buffer.append(line[1:].strip())
            continue
        m = LINE.match(line)
        if not m:
            if not line.strip():
                buffer = []
            continue
        prefix, address, rest = m[1], int(m[2], 16), m[3]
        if prefix in 'bctwsuig':
            block = prefix
            if buffer:
                title[address] = buffer[0]
        buffer = []
        instruction, _, note = rest.partition(';')
        instruction = instruction.strip()
        if note.strip():
            comment[address] = note.strip()
        data = block in 'bwtsuig' or re.match(r'^DEF[BWMS]\b', instruction, re.I)
        kind[address] = 'data' if data else 'code'
        if pending:
            label[address], pending = pending, None
    return kind, label, title, comment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('skool', type=Path)
    args = parser.parse_args()
    kind, ext_label, title, comment = read_skool(args.skool)
    addresses = sorted(a for a in kind if BASE <= a < END)
    ext_byte = {}
    for a, b in zip(addresses, addresses[1:] + [END]):
        for x in range(a, min(b, END)):
            ext_byte[x] = kind[a]
    ext_starts = {a for a in addresses if kind[a] == 'code'}

    reconstruction = json.loads((ROOT / 'docs/generated/reconstruction.json').read_text())
    our_byte = {}
    for r in reconstruction['ranges']:
        k = r['kind'] if r['kind'] in ('code', 'inline', 'unclassified') else 'data'
        for x in range(r['start'], r['end']):
            our_byte[x] = k
    our_starts = set()
    for line in (ROOT / 'src/game.asm').read_text().split('\n'):
        m = re.search(r'; \$([0-9A-F]{4}): ([0-9A-F]{2}(?: [0-9A-F]{2})*)', line)
        if m and not line.lstrip().lower().startswith('defb'):
            our_starts.add(int(m[1], 16))
    labels = {int(a, 16): n for a, n in reconstruction['labels'].items()}

    matrix, differences = Counter(), []
    for x in range(BASE, END):
        e, o = ext_byte.get(x, 'none'), our_byte.get(x, 'none')
        matrix[f'{e}/{o}'] += 1
        if (e == 'code') != (o == 'code'):
            if differences and differences[-1]['end'] == x and differences[-1]['ext'] == e \
                    and differences[-1]['ours'] == o:
                differences[-1]['end'] += 1
            else:
                differences.append(dict(start=x, end=x + 1, ext=e, ours=o))
    both_code = {a for a in ext_starts if our_byte.get(a) == 'code'}
    named = {a for a, n in labels.items() if not n.startswith('L_')}
    ext_named = {a for a in ext_label if BASE <= a < END}
    result = dict(
        skool=str(args.skool), external_instruction_starts=len(ext_starts),
        our_instruction_starts=len(our_starts), byte_matrix=dict(sorted(matrix.items())),
        code_differences=[dict(start=f"{d['start']:04X}", end=f"{d['end'] - 1:04X}",
                               bytes=d['end'] - d['start'], ext=d['ext'], ours=d['ours'])
                          for d in differences],
        external_starts_inside_our_instructions=[f'{a:04X}' for a in sorted(both_code - our_starts)],
        named_by_both=len(ext_named & named), named_only_externally=len(ext_named - named),
        named_only_here=len(named - ext_named),
        labels=[dict(address=f'{a:04X}', external=ext_label.get(a), ours=labels.get(a))
                for a in sorted(ext_named | named)],
        external_titles={f'{a:04X}': t for a, t in title.items() if BASE <= a < END},
        external_comments={f'{a:04X}': t for a, t in comment.items() if BASE <= a < END},
    )
    output = ROOT / 'docs/generated/skool-comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(f"instruction starts: external {len(ext_starts)}, here {len(our_starts)}")
    print('byte classification:', result['byte_matrix'])
    print(f"code/data differences: {len(differences)} runs; boundary differences: "
          f"{len(result['external_starts_inside_our_instructions'])}")
    print(f"labels: both {result['named_by_both']}, external only {result['named_only_externally']}, "
          f"here only {result['named_only_here']}")
    print('Wrote ' + str(output.relative_to(ROOT)))


if __name__ == '__main__':
    main()
