; Optional repair of stardust pixels drawn on the view frame or outside it:
; stardustfix=yes.
;
; ClearViewBuffer draws the view frame into the buffer every frame: rows 0 and 127
; and the side pixels in columns 8 and 247.  GetDustPixelAddress maps a particle to
; column $80 +/- X and row $3F -/+ Y, and XorPlotDustList XORs that pixel into the
; buffer, so a particle on the frame erases a frame pixel.  The original reaches the
; frame or the area outside it in two ways:
;
; - It selects the lower half of the buffer from the Y sign alone.  A particle with
;   Y = 0 and the sign bit set (negative zero) therefore lands on row 127, the bottom
;   frame line, instead of row 63.  SeedLaunchDust gives about one launch particle in
;   eight this value, and with Y = 0 the particle keeps it while it moves outward.
;   Respawns and the pitch step also produce it in flight.
; - StoreAndPlotDust plots every particle with |Y| < 63 but does not limit X.  The
;   depth motion keeps |X| <= 119, so X = +119 lands on column 247, the right frame
;   line.  The pitch step keeps |X| <= 127, which also reaches column 8 and columns
;   1..7 and 248..255 outside the frame.
;
; StardustPixelCode replaces GetDustPixelAddress ($A2EF..$A333, 69 bytes) in place.
; It selects the half from the row, so negative zero is drawn on row 63 like
; positive zero, and returns the pixel mask 0 for a column outside the frame, so
; that XorPlotDustList leaves the frame and the area outside it unchanged.  Every
; other particle gets the same DE, C and A as before; the particle records and their
; motion do not change.  Output: DE = buffer address, C = A = pixel mask, B = 0,
; L = column, H = row - 64 (the original returns the row; StoreAndPlotDust, the only
; caller, uses only DE and C).

defc DustCentreColumn = $80             ; column of X = 0
defc DustViewFirstColumn = 9            ; ClearViewBuffer: side frame pixels in columns 8 and 247
defc DustViewLastColumn = 246
defc ViewLowerHalfBit = 3               ; D bit 3: rows 64..127 of the view buffer

MACRO StardustPixelCode
assert $-GameImage = StardustPixelStart-GameLoadAddress
    LD D,ViewBitmapBuffer >> 8
    LD A,(DustFlags)
    LD B,A                              ; B = sign flags
    LD A,(DustX)
    BIT 7,B
    JR Z,StardustColumn
    NEG                                 ; X negative: left of the centre
StardustColumn:
    ADD A,DustCentreColumn
    LD L,A                              ; L = column = $80 +/- X
    LD A,(DustY)
    BIT 6,B
    JR Z,StardustRow                    ; Y positive: upper half
    NEG                                 ; carry: Y is not zero
    JR NC,StardustRow                   ; negative zero: upper half, like positive zero
    SET ViewLowerHalfBit,D              ; Y negative: lower half
StardustRow:
    CPL                                 ; A = row - 64 = -1 - signed Y, row = $3F - signed Y
    LD H,A
    AND $07                             ; pixel line within the character row (same as the row's)
    OR D
    LD D,A
    LD A,H
    AND $38                             ; character row bits into E (same as the row's)
    ADD A,A
    ADD A,A
    LD E,A
    LD A,L
    RRA                                 ; column / 8
    RRA
    RRA
    AND $1F
    OR E
    LD E,A
    LD A,L
    AND $07                             ; bit position in the byte
    INC A
    LD B,A
    LD A,L
    SUB DustViewFirstColumn
    CP DustViewLastColumn-DustViewFirstColumn+1    ; carry: inside the frame
    LD A,0                              ; keeps the carry
StardustMask:
    RRA                                 ; first step: carry into bit 7; then $80 >> (column AND 7)
    DJNZ StardustMask
    LD C,A                              ; C = A = pixel mask, 0 outside the frame
    RET
StardustPixelEnd:
assert StardustPixelEnd-GameImage <= StardustPixelLimit-GameLoadAddress
    defs (StardustPixelLimit-GameLoadAddress)-(StardustPixelEnd-GameImage),0 ; unreachable padding
ENDM
