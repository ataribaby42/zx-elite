"""Text output: token and message interpreters, cursor and number printing.

Evidence: instruction semantics of the routines below, the decoded tables in
tools/text_codec.py (all 146 dictionary tokens and the message table render
as readable game text) and runtime traces of every docked/flight screen.
"""

INLINE = {
    0xBA99: (1, 'text'),     # POP HL / LD A,(HL) / INC HL / PUSH HL, then PrintToken
    0xB00D: (1, 'column'),   # POP HL / LD A,(HL) / INC HL / PUSH HL, then SetTextColumn
    0xD19C: (1, 'text'),     # POP HL / LD B,(HL) / INC HL / PUSH HL; token printed if A<>0
}

TEXTCALLS = {
    0xBA9D: 'token',
    0xBAD7: 'message',
    0xAFF7: 'token',
    0xAFE8: 'token',
    0xAFEF: 'token',
    0xAFE3: 'message',
}

DATA = {
    # LD (nn),SP at $929C and LD SP,(nn) at $92B0; the message table starts
    # after this word (PrintMessage loads HL with $92B7).
    0x92B5: (0x92B7, 'words', 1),
    # The last message ends at $9964; the following byte is a flag of the
    # torus-jump/dust code (see TorusJumpDustFlag), not message text.
    0x9965: (0x9966, 'bytes', 1),
}

LABELS = {
    # Emitted by the ship/dispatch-table renderer (tools/analyze_ship_blueprints.py).
    0x6FA3: ('TokenControlTable', 'verified', """
Fourteen handler pointers for PrintToken control codes $00..$0D."""),
    0x6FBF: ('MessageControlTable', 'verified', """
Thirty-two handler pointers for PrintMessageByte control codes $00..$1F."""),
    0x92B5: ('AttributeFillSavedSP', 'verified', """
Saved stack pointer, written by LD ($92B5),SP at $929C and restored at $92B0.
Not part of the message table, which PrintMessage starts at $92B7."""),
    0xBA99: ('PrintInlineToken', 'verified', """
Print the byte that follows the CALL as a PrintToken code, then return
after that byte.  The caller's return address is used as the data pointer:
    CALL PrintInlineToken
    defb code
Every CALL site in the source is followed by its inline argument byte."""),
    0xBA9D: ('PrintToken', 'verified', """
Print text code A (recursive token interpreter):
  $00..$0D  control code: jump through TokenControlTable
  $0E..$1F  dictionary token A+$72
  $20..$5F  character, via PrintCharacter
  $60..$7F  dictionary token A
  $80..$9F  two-letter token A-$80, via PrintPairToken
  $A0..$FF  dictionary token A-$A0
Dictionary tokens are themselves strings of PrintToken codes."""),
    0xBAB9: (None, 'verified', """
PrintToken codes $0E..$1F select dictionary tokens $80..$91."""),
    0xBABB: ('PrintDictionaryToken', 'verified', """
Print dictionary token A: skip A zero-terminated strings of
TextTokenDictionary with CPIR, then print each byte through PrintToken."""),
    0xBAD7: ('PrintMessage', 'verified', """
Print message A (1-based) from the message table that starts at $92B7.
Skip A-1 zero-terminated strings, then print each byte through
PrintMessageByte.  Messages may nest: bytes $81..$D6 print another message.
PrintMessage itself does not change MessageDecodeMode."""),
    0xBB05: (None, 'verified', """
Message loop of PrintMessage: print each byte at HL through PrintMessageByte up to
the zero terminator.  Nested messages re-enter PrintMessage and return here."""),
    0xBAE7: ('PrintMessageByte', 'verified', """
Print one message byte in A.  While L_BA98 is zero the byte is passed to
PrintToken instead.  Otherwise:
  $00..$1F  control code: jump through MessageControlTable
  $20..$5A  character, via PrintCharacter
  $5B..$80  random choice of five messages, via PrintRandomMessage
  $81..$D6  nested message A, via PrintMessage
  $D7..$FF  two-letter token from the $FBA9 table, via PrintMessagePairToken"""),
    0xBA98: ('MessageDecodeMode', 'verified', """
Message interpretation mode: nonzero (initially 1) makes PrintMessageByte
decode message bytes itself; zero hands every byte to PrintToken.
Message control 5 sets it to 1 (L_B977); message control 6 clears it (L_B97B)."""),
    0xB89A: ('DispatchMessageControl', 'verified', """
Jump to message control handler A (0..31) from the word table at L_6FBF."""),
    0xB89F: ('DispatchTokenControl', 'verified', """
Jump to token control handler A (0..13) from the word table at L_6FA3."""),
    0xBB10: ('PrintCharacter', 'verified', """
Print character A ($20..$5F) with case conversion of the letters A..Z:
  L_A891 = 1   letters are printed unchanged (capitals);
  L_A891 = 2   letters are printed in lower case (+$20);
  otherwise    title case: a letter is capitalised when L_A892 = 1,
               which every non-letter sets, and lower case otherwise.
L_A893 nonzero capitalises one letter in modes 0 and 2, then clears.
If L_A894 = 1 the character goes to the justified-text buffer (L_BCFC);
otherwise the screen path continues in L_BB58 (column advance and glyph)."""),
    0xBC13: ('PrintPairToken', 'verified', """
Print two-letter token A ($80..$9F) from the pair table at L_FBC3.
A second character of '?' is not printed."""),
    0xBC0C: ('PrintMessagePairToken', 'verified', """
Print two-letter message token A ($D7..$FF) from the pair table at L_FBA9.
Shares the pair printer with PrintPairToken."""),
    0xBC2B: ('PrintRandomMessage', 'verified', """
Message codes $5B..$80: read a base message number from the table at
L_BC76, add 0..4 chosen by NextDescriptionRandom (thresholds $33, $66,
$99, $CC) and print that message.  Used by the planet descriptions."""),
    0xBC58: ('NextDescriptionRandom', 'verified', """
Advance the four-byte description generator and return its new high byte
in A.  With w1 = word at L_AC21 and w2 = word at L_AC23: shift the low byte
of w1 left (carry c), then w1' = w2 + w1 + c and w2' = w1 (shifted).
L_BA49 seeds both words from the selected system seeds (L_AC11/L_AC13)
before a planet description is printed."""),
    0xB00D: ('SetTextColumnInline', 'verified', """
Set TextColumn from the byte that follows the CALL (inline argument) and
return after it.  Falls into SetTextColumn."""),
    0xB011: ('SetTextColumn', 'verified', """
Set TextColumn to A.  A column of 32 or more starts a new line instead."""),
    0xB019: ('SetTextRow', 'verified', """
Set TextRow to A.  A row of 24 or more wraps to row 1 and resets the
column (via ResetTextColumn)."""),
    0xB008: ('ResetTextColumn', 'verified', """
Set TextColumn to zero."""),
    0xB002: ('NextTextRow', 'verified', """
Move to the next text row (TextRow+1, wrapping through SetTextRow)."""),
    0xAFFA: ('NewLine', 'verified', """
Start a new text line: request a capital for the next letter (L_A892=1),
set column zero and advance the row."""),
    0xAFF7: ('PrintTokenNewLine', 'verified', """
Print token A, then fall into NewLine."""),
    0xAFE8: ('PrintTokenColon', 'verified', """
Print token A followed by ':'."""),
    0xAFE3: ('PrintMessageColon', 'verified', """
Print message A followed by ':'."""),
    0xAFEF: ('PrintTokenSpace', 'verified', """
Print token A followed by a space."""),
    0xB062: ('PrintTokenString', 'verified', """
Print the zero-terminated string of PrintToken codes at HL.
Returns with carry set, A = 0 and HL pointing at the terminating zero."""),
    0xB759: ('PrintDecimalTenths', 'verified', """
Print A as an unsigned decimal number with one decimal place (A/10),
for example 70 prints as 7.0.  Sets carry and joins PrintDecimalHL."""),
    0xB75C: ('PrintDecimalA', 'verified', """
Print A as an unsigned decimal number without a decimal point."""),
    0xB760: ('PrintDecimalHL', 'verified', """
Print HL as an unsigned decimal number using the divisors 10000, 1000,
100 and 10.  L_B7F7 first pads to the field width in L_A88E: with spaces
while L_A88D (suppress leading zeros) is set, with zeros when it is clear
(used for money).  Leading zero digits are skipped while L_A88D is set.
With carry set on entry a decimal point is printed before the last digit, so a
value below 10 prints as 0.n.
On exit L_A88E = 0 and L_A88D = 1."""),
}
