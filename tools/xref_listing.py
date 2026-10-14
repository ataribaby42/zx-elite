"""Write an analysis copy of src/game.asm with cross-references at each label.

Inputs: src/game.asm, docs/generated/reconstruction.json (static references
from tools/bootstrap_sources.py) and, when present,
docs/generated/runtime-xrefs.json (PC-attributed 48K runtime accesses from
tools/trace_xrefs.py).  Output: build/analysis/game-xref.asm, a disposable
review aid.  The source itself is never modified.

Each label gets a comment block listing static callers/jumpers/readers and,
for data, the routines that read or wrote it at runtime.  Program counters
are mapped to the nearest preceding code label so the lists stay readable.
"""
import bisect
import json
import re

from tape import ROOT

OUT = ROOT / 'build' / 'analysis' / 'game-xref.asm'
LIMIT = 12
# Data includes whose labels are worth cross-referencing (not fonts/bitmaps).
INLINED = {'data/initial-runtime-state.asm', 'data/encoded-text.asm',
           'data/text-token-dictionary.asm', 'data/active-commander-initial.asm',
           'data/default-commander.asm', 'data/square-tables.asm'}


def main():
    reconstruction = json.loads((ROOT / 'docs/generated/reconstruction.json').read_text())
    labels = {int(a, 16): n for a, n in reconstruction['labels'].items()}
    static = {int(a, 16): v for a, v in reconstruction['static_xrefs'].items()}
    runtime_path = ROOT / 'docs/generated/runtime-xrefs.json'
    runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
    reads = {int(a, 16): p for a, p in runtime.get('reads', {}).items()}
    writes = {int(a, 16): p for a, p in runtime.get('writes', {}).items()}
    executed = {int(a, 16) for a in runtime.get('executed', [])}
    code_ranges = [r for r in reconstruction['ranges'] if r['kind'] == 'code']
    code_labels = sorted(a for a in labels if any(r['start'] <= a < r['end'] for r in code_ranges))

    def owner(pc):
        if pc == 'INT':
            return 'INT'
        pc = int(pc, 16)
        if pc < 0x6048:
            return f'ROM${pc:04X}'
        i = bisect.bisect_right(code_labels, pc) - 1
        if i < 0:
            return f'${pc:04X}'
        base = code_labels[i]
        return labels[base] + (f'+{pc - base}' if pc != base else '')

    def summarise(items):
        names = []
        for item in items:
            name = owner(item)
            if name not in names:
                names.append(name)
        more = len(names) - LIMIT
        return ', '.join(names[:LIMIT]) + (f' (+{more} more)' if more > 0 else '')

    by_name = {n: a for a, n in labels.items()}
    out = []
    source = []
    for line in (ROOT / 'src/game.asm').read_text().split('\n'):
        m = re.match(r'^\s+INCLUDE "(data/[\w-]+\.asm)"', line)
        if m and m[1] in INLINED:
            source += (ROOT / 'src' / m[1]).read_text().split('\n')
        else:
            source.append(line)
    for line in source:
        out.append(line)
        m = re.match(r'^(\w+):$', line)
        if not m or m[1] not in by_name:
            continue
        address = by_name[m[1]]
        notes = []
        refs = static.get(address, [])
        if refs:
            groups = {}
            for ref in refs:
                kind, pc = ref.split(':')
                groups.setdefault(kind, []).append(pc)
            for kind, pcs in groups.items():
                notes.append(f'{kind}: ' + summarise(pcs))
        span = range(address, address + 1)
        r = sorted({p for a in span for p in reads.get(a, [])})
        w = sorted({p for a in span for p in writes.get(a, [])})
        if r:
            notes.append('runtime reads: ' + summarise(r))
        if w:
            notes.append('runtime writes: ' + summarise(w))
        if address in executed:
            notes.append('executed at runtime')
        out.extend(';; XREF ' + note for note in notes)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(out), encoding='utf-8')
    print(f'Wrote {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
