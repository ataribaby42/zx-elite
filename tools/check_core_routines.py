"""Verify the shared arithmetic helpers named in tools/annotations/core.py.

Run after a default build (make.bat).  Each routine of the assembled default
image is executed in SkoolKit's Z80 simulator with controlled registers and
compared with a Python model for every input combination:

    SquareA               256 values of A
    MultiplyUnsigned      65,536 pairs (B, C)
    MultiplyUnsignedHigh  65,536 pairs (B, C)
    AddSignMagnitude      65,536 magnitude pairs x 4 sign combinations

The image is loaded with the 48K ROM into a 64K memory model; no game byte is
changed.  Addresses come from build/game.map.  The report is written to
build/core-routines-check/verification.json.
"""
import json
import sys

from tape import ROOT, ANALYSIS_DEPS
from build import symbol_map

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator                                 # noqa: E402
from skoolkit.simutils import A, B, C, D, E, F, H, L, PC, SP           # noqa: E402

STACK = 0x5CF0
SENTINEL = 0x0000


def main():
    symbols = symbol_map(ROOT / 'build/game.map')
    image = (ROOT / 'build/game.bin').read_bytes()
    rom = (ROOT / 'assets/zxspectrum48k.rom').read_bytes()
    memory = list(rom) + [0] * (0x10000 - len(rom))
    base = symbols['GameImage']
    memory[base:base + len(image)] = image
    sim = Simulator(memory)
    r = sim.registers

    def call(name, **registers):
        for key, value in registers.items():
            r[{'a': A, 'b': B, 'c': C, 'd': D, 'e': E, 'h': H, 'l': L, 'f': F}[key]] = value
        r[SP] = STACK - 2
        memory[STACK - 2] = SENTINEL & 0xFF
        memory[STACK - 1] = SENTINEL >> 8
        r[PC] = symbols[name]
        sim.run(stop=SENTINEL)

    report = {}
    # SquareA: DE = A*A, HL preserved.
    for a in range(256):
        call('SquareA', a=a, h=0x12, l=0x34)
        assert r[D] * 256 + r[E] == a * a, ('SquareA', a)
        assert (r[H], r[L]) == (0x12, 0x34), ('SquareA HL', a)
    report['SquareA'] = 256

    def quarter_square(b, c):
        s, d = (b + c) >> 1, abs(b - c) >> 1
        return s * s - d * d

    for b in range(256):
        for c in range(256):
            call('MultiplyUnsigned', b=b, c=c)
            hl = r[H] * 256 + r[L]
            expected = quarter_square(b, c)
            assert hl == expected, ('MultiplyUnsigned', b, c, hl, expected)
            assert hl == b * c - (min(b, c) if (b + c) & 1 else 0), ('documented form', b, c)
            call('MultiplyUnsignedHigh', b=b, c=c)
            s, d = (b + c) >> 1, abs(b - c) >> 1
            assert r[A] == ((s * s >> 8) - (d * d >> 8)) & 0xFF, ('MultiplyUnsignedHigh', b, c)
            assert r[A] - (hl >> 8) in (0, 1), ('MultiplyUnsignedHigh bound', b, c)
    report['MultiplyUnsigned'] = report['MultiplyUnsignedHigh'] = 65536

    cases = 0
    for sign_h in (0x00, 0x80):
        for sign_d in (0x00, 0x80):
            for l in range(256):
                for e in range(256):
                    call('AddSignMagnitude', h=sign_h, l=l, d=sign_d, e=e)
                    carry = r[F] & 1
                    if sign_h == sign_d:
                        assert r[A] == (l + e) & 0xFF and r[H] & 0x80 == sign_h, ('same', l, e)
                        assert carry == (l + e > 255), ('carry same', l, e)
                    else:
                        assert r[A] == abs(l - e), ('different', l, e)
                        assert carry == 0, ('carry different', l, e)
                        expected_sign = sign_d if e > l else sign_h
                        assert r[H] & 0x80 == expected_sign, ('sign', l, e)
                    cases += 1
    report['AddSignMagnitude'] = cases

    output = ROOT / 'build/core-routines-check/verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(machine='ZX Spectrum 48K memory model', cases=report), indent=2) + '\n')
    print('PASS: ' + ', '.join(f'{name} {count:,}' for name, count in report.items()))


if __name__ == '__main__':
    main()
