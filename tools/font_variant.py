"""Validated font provenance for extraction and tests, never for normal builds."""
from tape import ROOT, parse, reference, sha, validate_pairs

PATCH_SOURCE = 'assets/Elite128fixes/PATCH128.TAP'
PATCH_SHA256 = 'fac185ce4248e1dccc99f93a7cb7d2791e220543c24016a3a77a1dfff4cbec47'
REFERENCE_FONT_COPY = 0x716B  # Immutable reference instruction, not a current-build address.


def patch_font():
    """Extract using the immutable tape's copy operands, never current addresses."""
    data = (ROOT / PATCH_SOURCE).read_bytes()
    if sha(data) != PATCH_SHA256:
        raise ValueError('PATCH128.TAP differs from the supplied reference')
    blocks = parse(data)
    validate_pairs(blocks)
    original = reference()[1]
    if len(blocks) != len(original) or any(a != b for a, b in zip(blocks[:5], original[:5])):
        raise ValueError('PATCH128.TAP container or non-game payload changed')
    base = int.from_bytes(blocks[4].payload[13:15], 'little')
    payload = blocks[5].payload
    copy = REFERENCE_FONT_COPY-base
    code = original[5].payload
    if (code[copy], code[copy+3], code[copy+6], code[copy+9:copy+11]) != (0x21,0x11,0x01,b'\xED\xB0'):
        raise ValueError('Original font-copy instructions changed')
    start = int.from_bytes(code[copy+1:copy+3], 'little')
    end = start+int.from_bytes(code[copy+7:copy+9], 'little')
    first, last = start - base, end - base
    if not 0 <= first < last <= len(payload):
        raise ValueError('Font region is outside the PATCH128.TAP game block')
    if (payload[:first], payload[last:]) != (original[5].payload[:first], original[5].payload[last:]):
        raise ValueError('PATCH128.TAP has unexpected changes outside the font region')
    return payload[first:last], payload


def fixed_font(original, ecm_s=False):
    """Replace the compass glyphs, optionally also the smaller ECM/S glyphs."""
    alternate = patch_font()[0]
    if len(original) != len(alternate):
        raise ValueError('Font sizes differ')
    result = bytearray(original)
    ranges = [(0x21, 0x27)] + ([(0x3B, 0x3F), (0x5B, 0x5F)] if ecm_s else [])
    for first_code, end_code in ranges:
        first, end = (first_code-0x20)*8, (end_code-0x20)*8
        result[first:end] = alternate[first:end]
    return bytes(result)


def selected_font(symbols):
    if symbols.get('FONT_128FIX_ECM_S', 0):
        return '128fix_ecm_s'
    return '48' if symbols['FONT_48'] else '128fix' if symbols.get('FONT_128FIX', 0) else '128'
