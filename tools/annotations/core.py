"""Shared arithmetic helpers, lookup tables and the interrupt set-up.

Evidence: instruction semantics, the verified square tables at $BE00/$BF00
and the IM 2 initialisation at $FF4C.  The arithmetic routines are checked
against Python models for all inputs by tools/check_core_routines.py.
"""

LABELS = {
    0x7DDF: ('SquareA', 'verified', """
DE = A*A, read from the page-aligned square tables (low byte from
SquareLookupTables, high byte from the following page).  HL is preserved."""),
    0xE45D: ('MultiplyUnsigned', 'verified', """
HL = B*C by quarter squares: s = (B+C) >> 1 (9-bit sum), d = |B-C| >> 1,
HL = s*s - d*d from the square tables.  Exact when B+C is even; when it is
odd the result is B*C - min(B,C).  A, D, E and flags are also changed."""),
    0xE434: ('MultiplyUnsignedHigh', 'verified', """
A = high byte of the quarter-square product of B and C: high(s*s) -
high(d*d) with s and d as in MultiplyUnsigned.  The low-byte borrow is
ignored, so A can be one more than the high byte of MultiplyUnsigned."""),
    0xE424: ('AddSignMagnitude', 'verified', """
Add two sign-magnitude bytes: magnitudes L and E, signs in bit 7 of H and D.
Same signs: A = L+E (sign stays in H); carry is set only when this sum
overflows 255.  Different signs: A = |L-E|, carry clear, and H takes the sign
of the larger magnitude (D's sign when E > L)."""),
    0xFF4C: ('EnableInterruptMode2', 'verified', """
Select interrupt mode 2 with I = high byte of InterruptVectorTable.
Every vector byte is $FE, so any value on the data bus selects $FEFE."""),
    0xFEFE: ('InterruptEntry', 'verified', """
IM 2 entry point at the fixed address $FEFE selected by the vector table."""),
    0xFD00: ('InterruptVectorTable', 'verified', """
IM 2 vector table: 257 bytes of $FE at a page boundary, so that both bytes
of the vector word read at I*256+bus value are $FE."""),
}

DATA = {
    0xFD00: (0xFE01, 'bytes', 16),
}

OPERANDS = {
    0x7DE0: 'SquareLookupTables >> 8',          # LD H,$BE
    0xDC16: 'SquareLookupTables >> 8',          # LD H,$BE
    0xDCA3: '(SquareLookupTables >> 8) + 1',    # LD H,$BF
    0xE43C: '(SquareLookupTables >> 8) + 1',    # LD H,$BF
    0xE465: 'SquareLookupTables >> 8',          # LD H,$BE
    0xFF4C: 'InterruptVectorTable >> 8',        # LD A,$FD
}

# z80asm evaluates assertions before linking, so absolute addresses are
# written as GameLoadAddress plus a label difference.
ASSERTS = {
    'square-table-page': ('((SquareLookupTables-GameImage+GameLoadAddress) & $FF) = 0',
                          'square tables are addressed by page (LD H,page; LD L,n)'),
    'vector-table-page': ('((InterruptVectorTable-GameImage+GameLoadAddress) & $FF) = 0',
                          'IM 2 vector table must start on a page boundary'),
    'interrupt-entry': ('InterruptEntry-GameImage+GameLoadAddress = $FEFE',
                        'IM 2 entry fixed by the $FE vector bytes'),
}
