; Optional repair of the station orientation: stationslotfix=yes.
;
; The original game keeps the station dormant while it is far away. During that
; time MoveObject turns its position with the player's roll and pitch but not its
; axes, so the docking slot (the local Z axis) stays fixed in the player's frame.
; The hyperspace arrival also reverses the slot for a negative planet x. When the
; station is switched on, this code points the slot at the planet centre.
;
; The station is invisible while it is dormant (no energy: no drawing, no scanner
; contact), so the new orientation appears together with the station. Nothing
; changes while it stays active.
;
; Three macros fill free areas of the original image, which keeps every other
; address unchanged; game.asm expands each one in place of the original bytes:
;   StationSlotAlignCode   $E88B..$E8CE  (68 B, uncalled UnusedMultiplyWordHigh)
;   StationSlotRoofCode    $AC56..$AC76  (33 B, dormant galaxy-step copy)
;   StationSlotFinishCode  $FCED..$FCFF  (19 B, zeros before the IM 2 table)
; The switch-on in UpdateStationDormancy calls StationSlotAlign instead of
; storing StationDormantFlag; StationSlotFinish stores the flag before returning.

; Offsets of the high bytes in a three-word sign-magnitude vector.
defc VectorHighX = 1
defc VectorHighY = 3
; A roof candidate is used when the nose component along its axis is below
; 80/127 (cos 51 degrees), so that the orthogonalised roof keeps at least 77% of
; its length, where the per-frame RenormaliseOrientationVector converges.
defc StationRoofNoseLimit = $50
; Stop scaling the difference vector once a magnitude reaches $2000: from there
; to $3FFF NormaliseVector neither overflows nor loses direction accuracy.
defc StationSlotScaleMask = $60

; In: IX = station slot 0, A = 0 (UpdateStationDormancy's switch-on).
; Out: IX unchanged, IY preserved, StationDormantFlag = 0; AF, BC, DE, HL clobbered.
MACRO StationSlotAlignCode
assert $-GameImage = StationSlotAlignStart-GameLoadAddress
assert InstanceAxisZ = 3*(InstanceY-InstanceX)  ; the difference loop leaves IX here
assert InstanceAxisY = InstanceAxisZ+6
assert InstanceAxisX = InstanceAxisY+6
StationSlotAlign:
    PUSH IY                     ; UpdateStationDormancy preserves IY
    LD IY,PlanetPosition
    LD HL,InitialRuntimeState+InstanceAxisZ
    LD B,3
StationSlotDifference:          ; nose word = (planet - station)/512, per axis
    PUSH BC
    PUSH HL
    CALL HalveCoordinateDifference
    EX DE,HL
    POP HL
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD BC,InstanceY-InstanceX   ; next coordinate
    ADD IX,BC
    ADD IY,BC
    POP BC
    DJNZ StationSlotDifference
                                ; IX = the nose vector now
StationSlotScale:               ; double all three until one reaches $2000
    PUSH IX
    POP HL
    LD BC,3*256                 ; B = three words, C = OR of their new high bytes
StationSlotShift:
    SLA (HL)
    INC HL
    RL (HL)                     ; magnitude bit 14 is clear; the sign goes to carry
    JR NC,StationSlotShifted
    SET 7,(HL)                  ; put the sign back
StationSlotShifted:
    LD A,(HL)
    OR C
    LD C,A
    INC HL
    DJNZ StationSlotShift
    AND StationSlotScaleMask
    JR Z,StationSlotScale
    CALL NormaliseVector        ; nose = unit vector towards the planet
    LD HL,InitialRuntimeState+InstanceAxisY
    JP StationSlotRoof
StationSlotAlignEnd:
assert StationSlotAlignEnd-StationSlotAlign <= StationSlotAlignLimit-StationSlotAlignStart
    defs (StationSlotAlignLimit-StationSlotAlignStart)-(StationSlotAlignEnd-StationSlotAlign),0
ENDM

; In: IX = the nose vector, HL = the roof vector.
; Roof = the unit axis least aligned with the nose: y, else x, else z.
MACRO StationSlotRoofCode
assert $-GameImage = StationSlotRoofStart-GameLoadAddress
StationSlotRoof:
    LD B,InstanceAxisX-InstanceAxisY
    CALL ClearBytes             ; roof = 0, HL = InstanceAxisX
    DEC HL                      ; roof z high byte
    LD A,(IX+VectorHighY)
    ADD A,A
    CP 2*StationRoofNoseLimit
    JR C,StationSlotRoofY       ; |nose y| small: roof = y axis
    LD A,(IX+VectorHighX)
    ADD A,A
    CP 2*StationRoofNoseLimit
    JR NC,StationSlotRoofSet    ; |nose x| large too: roof = z axis
    DEC HL                      ; roof = x axis
    DEC HL
StationSlotRoofY:
    DEC HL
    DEC HL
StationSlotRoofSet:
    LD (HL),$7F                 ; unit component
    JP StationSlotFinish
StationSlotRoofEnd:
assert StationSlotRoofEnd-StationSlotRoof <= StationSlotRoofLimit-StationSlotRoofStart
    defs (StationSlotRoofLimit-StationSlotRoofStart)-(StationSlotRoofEnd-StationSlotRoof),0
ENDM

; Make the roof perpendicular to the nose, rebuild side = roof x nose and switch
; the station on; the caller then gives it energy $F0.
MACRO StationSlotFinishCode
assert $-GameImage = StationSlotFinishStart-GameLoadAddress
StationSlotFinish:
    LD IX,InitialRuntimeState
    CALL OrthogonaliseYVector
    CALL BuildRotationMatrix    ; side axis; clobbers IY
    POP IY
    XOR A
    LD (StationDormantFlag),A   ; the replaced instruction: station active
    RET
StationSlotFinishEnd:
assert StationSlotFinishEnd-StationSlotFinish <= StationSlotFinishLimit-StationSlotFinishStart
    defs (StationSlotFinishLimit-StationSlotFinishStart)-(StationSlotFinishEnd-StationSlotFinish),0
ENDM
