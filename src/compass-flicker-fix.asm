; The scanner saves 13 bytes per line. Its last byte in rows 144..159
; includes five pixels of the moving compass dot (screen x = 171..175).
; The rightmost possible scanner stick is x = 170 and its dash extends left.
; Keep the live dot bits on the restore write, even if the saved panel
; contains a dot from before a chart visit. Save all 624 bytes as usual.
defc ScannerLineBytes = 13
defc ScannerBackupRows = 6              ; character rows, counted down in A
defc CompassSharedRows = 2              ; first two character rows of the copy
defc CompassLiveMask = $1F
defc ScannerBufferPageBit = 3           ; D bit 3: $50..$57 screen, $5B..$5D buffer
assert (ScreenCockpitBitmap & $F800) = $5000
assert (ScannerBackupBuffer & $F800) = $5800
assert ((ScannerBackupBuffer+ScannerBackupRows*8*ScannerLineBytes-1) & $F800) = $5800

    PUSH BC                             ; preserve B, the pixel-line counter
    LD BC,ScannerLineBytes-1
    LDIR
    POP BC
    LD C,A                              ; row count, restored for the outer loop
    CP ScannerBackupRows-CompassSharedRows+1
    LD A,(HL)
    JR C,ScannerStoreLastByte           ; below the compass
    BIT ScannerBufferPageBit,D
    JR NZ,ScannerStoreLastByte          ; screen -> backup: save the full byte
    LD A,(DE)
    XOR (HL)
    AND CompassLiveMask
    XOR (HL)                            ; screen low five bits, backup high three
ScannerStoreLastByte:
    LD (DE),A
    LD A,C
    INC HL
    INC DE
