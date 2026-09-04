; In-place replacement of the original $A660..$A705 instrument routines.
; Draw the same ten graphic tiles directly from the selected runtime font.
; Only bit 0 at ScannerEcmOverlap belongs to the scanner, not to the E tile.
; No font bytes are modified. The shared renderer keeps its original code;
; its usual XOR mode is restored on return, just as in the original routine.
assert $-GameImage = CockpitIndicatorsStart-GameLoadAddress
assert FontGlyphHeight = 8
assert (EncounterCircleTop >> 8) = (ScannerEcmOverlap >> 8)
assert (EncounterCircleBottom >> 8) = (ScannerEcmOverlap >> 8)
assert (EcmIndicatorTop >> 8) = (ScannerEcmOverlap >> 8)
assert (StationIndicatorTop >> 8) = (ScannerEcmOverlap >> 8)

    LD HL,EncounterCircleTop    ; Encounter circle: column 9, rows 17 and 18
    LD DE,EncounterCircleTiles
    CALL DrawIndicatorTile
    LD L,EncounterCircleBottom & $FF
    CALL DrawIndicatorTile
    LD L,EcmIndicatorTop & $FF   ; ECM: columns 8/9, rows 22/23
    LD A,(EcmTimer)
    OR A
    LD DE,EcmOffTiles
    JR Z,DrawEcmTiles
    LD DE,EcmOnTiles
DrawEcmTiles:
    CALL DrawIndicatorSquare
    LD L,StationIndicatorTop & $FF ; Station S: columns 22/23, rows 22/23
    LD A,(StationPresent)
    OR A
    LD DE,StationOffTiles
    JR Z,DrawStationTiles
    LD DE,StationOnTiles
DrawStationTiles:
    CALL DrawIndicatorSquare
    LD A,$A9                    ; Preserve original return to XOR text mode
    LD (CharacterBlendOpcode),A
    RET

DrawIndicatorSquare:
    CALL DrawIndicatorPair
    LD A,L
    ADD A,31                    ; Right cell -> left cell of the next row
    LD L,A
DrawIndicatorPair:
    CALL DrawIndicatorTile
    INC L
    JP DrawIndicatorTile

; HL = first screen row ($50xx); DE = next character code in the tile table.
; Return with HL unchanged, DE advanced. Other registers are scratch.
DrawIndicatorTile:
    LD A,(DE)
    INC DE
    PUSH DE
    PUSH HL
    LD L,A
    LD H,0
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    LD BC,FontRuntime-FontFirstCode*FontGlyphHeight
    ADD HL,BC
    EX DE,HL
    POP HL
    LD B,FontGlyphHeight
    LD A,L
    CP ScannerEcmOverlap & $FF
    JR NZ,DrawIndicatorRows
    LD A,(DE)
    XOR (HL)
    AND $FE
    XOR (HL)                    ; (glyph & $FE) | (old screen & 1)
    JR StoreIndicatorRow
DrawIndicatorRows:
    LD A,(DE)
StoreIndicatorRow:
    LD (HL),A
    INC H
    INC DE
    DJNZ DrawIndicatorRows
    LD H,ScannerEcmOverlap >> 8
    POP DE
    RET

EncounterCircleTiles:
    defb $26,$24
EcmOnTiles:
    defb $3B,$3C,$3D,$3E
EcmOffTiles:
    defb $20,$20,$40,$40
StationOnTiles:
    defb $5B,$5C
    defb $5D,$5E
StationOffTiles:
    defb $20,$5F,$40,$2B

; Compact the adjacent missile-count drawing loop to recover the space used
; above. Still draw exactly four slots, keeping the original mode on return:
; NOP for four missiles, XOR otherwise. Valid commander count is 0..4.
DrawMissileIndicators:
L_A6D3: ; legacy analysis alias
    LD HL,MissileDisplayCoordinates
    LD (TextColumn),HL
    XOR A
    LD (CharacterBlendOpcode),A
    LD A,(L_A845)
    LD C,A
    LD B,4
DrawMissileSlots:
    DEC C
    LD A,$25
    JP P,DrawMissileSlot
    LD A,$40
DrawMissileSlot:
    PUSH BC
    CALL L_BA9D
    POP BC
    DJNZ DrawMissileSlots
    LD A,C
    OR A
    RET Z
    LD HL,CharacterBlendOpcode
    LD (HL),$A9
    RET

CockpitIndicatorsEnd:
assert CockpitIndicatorsEnd-L_A660 <= CockpitIndicatorsLimit-CockpitIndicatorsStart
    defs (CockpitIndicatorsLimit-CockpitIndicatorsStart)-(CockpitIndicatorsEnd-L_A660),0
