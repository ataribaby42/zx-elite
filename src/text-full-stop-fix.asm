; Optional repair of a full stop lost at the end of a justified line:
; textfullstopfix=yes.
;
; Justified text (message control 14; the planet descriptions of DATA ON) goes
; through BufferJustifiedCharacter into lines of 30 characters.  A full stop prints
; the line at once.  The original tests for it before it counts the character, so a
; full stop that arrives as the 31st character is stored after the 30 printed ones
; (WrapOverflowChar) and lost.  This removes the final full stop of 72 of the 2,048
; planet descriptions, those whose last line is exactly 30 characters wide.
;
; TextFullStopBufferCode replaces the first 31 bytes of BufferJustifiedCharacter
; ($BCFC..$BD1A) in place and counts every character first.  Up to the 30th
; character a full stop prints the line at once, as before.  As the 31st character
; it is wrapped like any other character: the original code from JustifyWrapWord on
; moves its word to the next line and justifies and prints the current line.
; TextFullStopHookCode then prints the line with the word and the full stop at once.
; Spaces and other characters are handled exactly as in the original.  The hook
; uses the 11 zero bytes before the page-aligned square tables ($BDF5..$BDFF).

defc JustifyLineWidth = 30              ; characters per justified line

MACRO TextFullStopBufferCode
assert $-GameImage = TextFullStopBufferStart-GameLoadAddress
    LD HL,(JustifyWritePointer)         ; advance to the next free position
    INC HL
    LD (JustifyWritePointer),HL
    POP AF                              ; character left on the stack by PrintCharacter
    LD (HL),A
    LD B,A
    LD HL,JustifyLineLength             ; count every character first, a full stop too
    INC (HL)
    LD A,(HL)
    CP JustifyLineWidth+1
    LD A,B
    JP C,JustifyCharacterInLine         ; up to the 30th character
    CP '.'
    JP Z,JustifyWrapFullStop            ; a full stop as the 31st character
    CP ' '
    JR Z,PrintJustifiedLine             ; a space as the 31st character just ends the line
    NOP
JustifyWrapWord:                        ; original code: wrap the cut word, justify and print
assert JustifyWrapWord-GameImage = TextFullStopBufferLimit-GameLoadAddress
ENDM

MACRO TextFullStopHookCode
assert $-GameImage = TextFullStopHookStart-GameLoadAddress
JustifyWrapFullStop:
    CALL JustifyWrapWord                ; move its word to the next line, justify and print this one
    LD A,'.'                            ; then print the next line at once, as for any full stop
JustifyCharacterInLine:
    CP '.'
    RET NZ                              ; other characters wait for the line to fill
    JP PrintJustifiedLine               ; a full stop prints the line at once
TextFullStopHookEnd:
assert TextFullStopHookEnd-GameImage = TextFullStopHookLimit-GameLoadAddress
ENDM
