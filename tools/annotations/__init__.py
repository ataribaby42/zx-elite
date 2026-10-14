"""Disassembly annotation database for src/game.asm and its data includes.

tools/bootstrap_sources.py combines these entries with its control-flow
analysis when it regenerates the source.  Every key is an address in the
immutable reference image (TAP block 5, $6048..$FFA8); emitted source uses
the corresponding labels, never those numbers.

Each module in this package covers one subsystem or address range and may
define any of the dictionaries below.  The loader merges them and rejects a
second definition of the same address, so ownership stays unambiguous.

LABELS     {address: (name, status, header)}
    name    descriptive label, or None to keep the neutral L_xxxx label.
    status  'verified' or 'inferred'.  Only verified entries may carry a
            descriptive name (see docs/DISASSEMBLY.md for the evidence rule).
    header  block comment text emitted above the label; lines are separated
            by newlines.  The status tag is prefixed to the first line unless
            that line already starts with VERIFIED:, INFERRED: or NOTE:.
COMMENTS   {address: text}            end-of-line comment for one line.
SECTIONS   {address: (title, text)}   banner emitted before the address.
DATA       {start: (end, kind, unit)} typed data in game.asm:
    kind    'bytes', 'words', 'pointers' (defw Label), 'text' (defm/defb),
            'zeros' (defs), 'stack' (zero-filled stack/workspace).
    unit    preferred number of items on one source line.
INLINE     {routine: (count, kind)}   unconditional CALLs to this routine are
            followed by count inline argument bytes, consumed through the
            return address.  kind selects the comment decoder
            ('text', 'column', 'row').
CONSTANTS  {instruction: reason}      16-bit immediate that is a number,
            although its value lies inside the image; emit it numerically.
OPERANDS   {instruction: expression}  emit this operand expression instead of
            the default label; the build proves it with byte identity.
SEEDS      {address: evidence}        additional proven instruction starts.
FIELDS     {name: (value, text)}      named constants (structure offsets,
            fixed workspaces) emitted near the top of game.asm.
NORETURN   {routine: evidence}        unconditional CALLs to it never return.
STOPS      {instruction: evidence}    execution never falls through it.
TEXTCALLS  {routine: 'token'|'message'} A on entry is a text code; a preceding
            LD A,n gets the decoded text as its comment.
TEXTNAMES  {('token'|'message', code): name} names of text control codes.
ASSERTS    {key: (expression, reason)} assembler assertions for fixed layout
            constraints, such as page alignment of lookup tables.
"""
from importlib import import_module
from pathlib import Path
import re

KINDS = ('LABELS', 'COMMENTS', 'SECTIONS', 'DATA', 'INLINE', 'CONSTANTS',
         'OPERANDS', 'SEEDS', 'FIELDS', 'NORETURN', 'STOPS', 'TEXTCALLS', 'TEXTNAMES',
         'ASSERTS')
STATUSES = ('verified', 'inferred')
TAGS = ('VERIFIED:', 'INFERRED:', 'NOTE:', 'UNCLASSIFIED:')
DATA_KINDS = ('bytes', 'words', 'pointers', 'text', 'zeros', 'stack')
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
LEGACY = re.compile(r'^L_[0-9A-F]{4}$')


def _load():
    merged = {kind: {} for kind in KINDS}
    owner = {kind: {} for kind in KINDS}
    directory = Path(__file__).parent
    for path in sorted(directory.glob('*.py')):
        if path.stem.startswith('_'):
            continue
        module = import_module(f'{__name__}.{path.stem}')
        for kind in KINDS:
            for key, value in getattr(module, kind, {}).items():
                if key in merged[kind]:
                    raise ValueError(f'{kind} entry {key!r} defined in both '
                                     f'{owner[kind][key]} and {path.stem}')
                merged[kind][key] = value
                owner[kind][key] = path.stem
    _validate(merged)
    return merged


def _validate(db):
    names = {}
    for address, entry in db['LABELS'].items():
        if len(entry) != 3:
            raise ValueError(f'LABELS ${address:04X}: expected (name, status, header)')
        name, status, header = entry
        if status not in STATUSES:
            raise ValueError(f'LABELS ${address:04X}: unknown status {status!r}')
        if name is not None:
            if not NAME.match(name) or LEGACY.match(name):
                raise ValueError(f'LABELS ${address:04X}: invalid name {name!r}')
            if status != 'verified':
                raise ValueError(f'LABELS ${address:04X}: only verified entries may be named ({name})')
            if name in names:
                raise ValueError(f'Label {name} used at ${names[name]:04X} and ${address:04X}')
            names[name] = address
        if not isinstance(header, str):
            raise ValueError(f'LABELS ${address:04X}: header must be a string')
    for start, entry in db['DATA'].items():
        end, kind, unit = entry
        if not start < end or kind not in DATA_KINDS or unit < 1:
            raise ValueError(f'DATA ${start:04X}: invalid entry {entry!r}')
    ranges = sorted((start, entry[0]) for start, entry in db['DATA'].items())
    for (a, b), (c, d) in zip(ranges, ranges[1:]):
        if c < b:
            raise ValueError(f'DATA ranges overlap at ${a:04X} and ${c:04X}')
    for routine, kind in db['TEXTCALLS'].items():
        if kind not in ('token', 'message'):
            raise ValueError(f'TEXTCALLS ${routine:04X}: unknown kind {kind!r}')
    for routine, (count, kind) in db['INLINE'].items():
        if count < 1 or kind not in ('text', 'message', 'column', 'row', 'bytes'):
            raise ValueError(f'INLINE ${routine:04X}: invalid entry')
    for name in db['FIELDS']:
        if not NAME.match(name):
            raise ValueError(f'FIELDS: invalid name {name!r}')


DB = _load()
LABELS = DB['LABELS']
COMMENTS = DB['COMMENTS']
SECTIONS = DB['SECTIONS']
DATA = DB['DATA']
INLINE = DB['INLINE']
CONSTANTS = DB['CONSTANTS']
OPERANDS = DB['OPERANDS']
SEEDS = DB['SEEDS']
FIELDS = DB['FIELDS']
NORETURN = DB['NORETURN']
STOPS = DB['STOPS']
TEXT_CALLS = DB['TEXTCALLS']
TEXT_NAMES = DB['TEXTNAMES']
ASSERTS = DB['ASSERTS']


def header_lines(status, text):
    """Return comment lines for a header, with the status tag on line one."""
    lines = [line.rstrip() for line in text.strip('\n').split('\n')] if text.strip() else []
    if lines and not lines[0].lstrip().startswith(TAGS):
        lines[0] = ('VERIFIED: ' if status == 'verified' else 'INFERRED: ') + lines[0]
    return lines
