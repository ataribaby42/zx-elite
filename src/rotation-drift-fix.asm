; rotationdriftfix=yes: reversible three-shear position rotations.
; Evidence and limits: docs/ROTATION-DRIFT-FIX.md; tools/check_rotation_drift_fix.py.
; All coordinates retain the original 24-bit sign-magnitude format. The
; coordinate multiplier gets exact byte products; signed addition is unchanged.

MACRO RotationDriftRotationCode
    LD A,(PlayerPitch)
    LD DE,InstanceY
    LD HL,InstanceZ
    CALL RotationDriftRotatePlane
    LD A,(PlayerRoll)
    CALL DoubleSignMagnitude
    LD A,C
    LD DE,InstanceY
    LD HL,InstanceX
    CALL RotationDriftRotatePlane
    JP TranslatePlayerPosition
; Exact B*C. Handle C=0/1/2 directly so slow turns do not pay for table lookups.
; ADD HL,HL preserves S/Z from DEC A: C=2 returns positive, C=0 falls through.
RotationDriftMultiply:
    LD A,B
    AND A
    JR Z,RotationDriftZeroProduct
    LD A,C
    CP 3
    JP NC,RotationDriftMultiplyTable
    LD H,0
    LD L,B
    DEC A
    RET Z
    ADD HL,HL
    RET P
RotationDriftZeroProduct:
    LD H,0
    LD L,H
    RET
RotationDriftRotationCodeEnd:
IF DOCKING_ROTATION
    DockingRotationAcceptCode
ENDIF
    assert RotationDriftRotationCodeEnd-GameImage <= RotationDriftRotationLimit-GameLoadAddress
    defs (RotationDriftRotationLimit-GameLoadAddress)-($-GameImage),0
ENDM

MACRO RotationDriftSecurityCode
    ; Successful saves still print COMMANDER SAVED and update the snapshot.
    JR CopyCommanderToTemplate

; A = signed coefficient, DE = source, HL = destination coordinate offset.
; u -= v*a/2; v += u*a; u -= v*a/2 (a = coefficient/256).
; The reverse coefficient gives the inverse sequence. Half-products are
; shifted AFTER multiplication, so odd pitch rates are not rounded to zero.
RotationDriftRotatePlane:
    LD C,A
    AND $7F
    RET Z
    LD A,C
    PUSH AF
    PUSH DE
    PUSH HL
    XOR $80
    LD C,A
    CALL RotationDriftHalfCoordinate
    POP DE
    POP HL
    POP AF
    PUSH AF
    PUSH DE
    PUSH HL
    LD C,A
    CALL AddScaledCoordinate
    POP DE
    POP HL
    POP AF
    XOR $80
    LD C,A
    JP RotationDriftHalfCoordinate

RotationDriftHalfCoordinate:
    LD A,1
    LD (RotationDriftHalfScale),A
    ; Product packing consumes the flag before the signed addition. Tail-call
    ; to retain its carry (used by DoubleSignMagnitude) and save stack depth.
    JP AddScaledCoordinate
RotationDriftHalfScale:
    defb 0

; Replace the four original product-repacking LD instructions, preserving
; their A:HL result for every ordinary AddScaledCoordinate call.
RotationDriftPackProduct:
    LD B,A
    LD A,H
    LD H,L
    LD L,B
    ; BC is immediately replaced by POP BC at the only call site.
    LD B,A
    LD A,(RotationDriftHalfScale)
    AND A
    LD A,B
    RET Z
    LD A,0
    LD (RotationDriftHalfScale),A
    LD A,B
    SRL A
    RR H
    RR L
    RET

; Exact B*C: quarter squares give B*C-min(B,C) for odd B+C.
; B/C survive MultiplyUnsigned. Correct the omitted term in that case only.
; Shared graphics multiplication remains unchanged.
RotationDriftMultiplyTable:
    LD A,B
    XOR C
    RRA
    JP NC,MultiplyUnsigned
    CALL MultiplyUnsigned
    LD A,B
    CP C
    JR C,RotationDriftMultiplyCorrection
    LD A,C
RotationDriftMultiplyCorrection:
    ADD A,L
    LD L,A
    RET NC
    INC H
    RET
RotationDriftSecurityCodeEnd:
IF DOCKING_ROTATION
    DockingRotationLoadCode
ENDIF
    assert RotationDriftSecurityCodeEnd-GameImage <= CompetitionSecurityLimit-GameLoadAddress
    defs (CompetitionSecurityLimit-GameLoadAddress)-($-GameImage),0
ENDM

MACRO RotationDriftParitySpace
RotationDriftMultiplyHigh:
    PUSH DE
    CALL RotationDriftMultiply
    LD A,H
    POP DE
    RET
RotationDriftFreeSpace:
IF DOCKING_ROTATION
    DockingRotationCompareCode
ENDIF
    assert RotationDriftFreeSpace-GameImage <= CompetitionParityLimit-GameLoadAddress
    defs (CompetitionParityLimit-GameLoadAddress)-($-GameImage),0
RotationDriftFreeSpaceEnd:
ENDM

MACRO RotationDriftProductHook
    CALL RotationDriftPackProduct
    NOP
ENDM
