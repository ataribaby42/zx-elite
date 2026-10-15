; Optional repair of two scanner contact quirks: scannerblipfix=yes.
;
; DrawScannerContacts puts a contact's stick in pixel column 123 + dx (x > 0) or
; 124 - dx (x < 0), dx = ScannerDotX AND $7F.  For dx >= 4 it first steps
; ceil((dx - 4) / 8) screen bytes with a DJNZ loop.  For dx = 4 that count is 0, so
; the loop runs 256 times and the whole contact lands one pixel row lower (x > 0) or
; higher (x < 0).  ScannerBlipStepCode lets dx = 4 take the centre-byte path as well
; (ScannerBlipCentreCode keeps its pixel numbering) and counts the bytes for dx >= 5
; as (dx - 5) / 8 + 1, which equals the original count.
;
; An upward stick that leaves character row 0 of the bottom third enters the 3D
; view.  The original stops it there, without its dash, only in character column 15
; (L = $0F).  ScannerBlipGuardCode stops it in every column.  Screen row 127, where
; the original's extra stick pixel and dash land, holds the bottom line of the view
; frame, so that part of the change is rarely visible.
;
; Three macros replace original bytes in place; game.asm expands each one:
;   ScannerBlipStepCode    $8CE0..$8CF2  (19 B, the byte count)
;   ScannerBlipCentreCode  $8D0B..$8D0C  (2 B, the centre-byte pixel)
;   ScannerBlipGuardCode   $8DCC..$8DDD  (18 B, the upward stick guard)

defc ScannerCentreFirstPixel = 4        ; dx = 0 is pixel 4 (from the left) of the centre byte
defc ScannerCentreLastDx = 4            ; dx 0..4 stay in the centre byte (pixels 4..8)
defc ScreenCharacterRowStep = $20       ; L step of one character row within a third
defc ScreenThirdStep = $08              ; H step of one third

MACRO ScannerBlipStepCode
assert $-GameImage = ScannerBlipStepStart-GameLoadAddress
    SUB ScannerCentreLastDx+1           ; A = dx - 5; carry for dx 0..4
    LD C,A
    JR C,ScannerDotInCentreByte
    RRA
    RRA
    RRA
    AND $1F                             ; (dx - 5) / 8
    LD B,A
    INC B                               ; whole bytes: (dx - 5) / 8 + 1 = ceil((dx - 4) / 8)
    LD A,C
    INC A                               ; (dx - 4) AND 7: pixel in the last byte
    AND $07
    LD C,A
ScannerBlipStepEnd:
assert ScannerBlipStepEnd-GameImage <= ScannerBlipStepLimit-GameLoadAddress
    defs (ScannerBlipStepLimit-GameLoadAddress)-(ScannerBlipStepEnd-GameImage),0 ; NOPs, executed
ENDM

; In: A = dx - 5 for dx 0..4.  C = dx + 4, the pixel numbering of the original path.
MACRO ScannerBlipCentreCode
assert $-GameImage = ScannerBlipCentreStart-GameLoadAddress
    ADD A,ScannerCentreLastDx+1+ScannerCentreFirstPixel
ScannerBlipCentreEnd:
assert ScannerBlipCentreEnd-GameImage = ScannerBlipCentreLimit-GameLoadAddress
ENDM

; Called when an upward stick crosses into the character row above (H already
; decremented).  From character row 0 of the bottom third it would enter the view:
; stop there in every column, as the original does in column 15.
MACRO ScannerBlipGuardCode
assert $-GameImage = ScannerBlipGuardStart-GameLoadAddress
    LD A,L
    SUB ScreenCharacterRowStep          ; previous character row
    JR C,ScannerBlipStickStop           ; from character row 0: stop
    LD L,A
    LD A,H
    ADD A,ScreenThirdStep               ; back into this third
    LD H,A
    RET
ScannerBlipStickStop:
    POP AF                              ; drop the return address: next slot, no dash
    JP NextScannerContact
ScannerBlipGuardEnd:
assert ScannerBlipGuardEnd-GameImage <= ScannerBlipGuardLimit-GameLoadAddress
    defs (ScannerBlipGuardLimit-GameLoadAddress)-(ScannerBlipGuardEnd-GameImage),0 ; unreachable
ENDM
