; Optional repair of the original station trader selection.
; Fits the same 38 bytes, preserves RNG advancement and all other launch types.
; TryLaunchStationTraffic calls the RNG with carry set. A calm station only launches if its
; result is 0 or 1. The next RNG result is then always odd, so the original
; AND 1 / ADD 9 always selected Python (10), never Cobra trader (9).

    LD A,$08
    DEC C
    JR Z,LaunchSelectedShip ; C=1: police Viper, unchanged, no RNG call
    CALL NextRandomByte     ; Keep the original RNG call and state progression.
    LD A,(RandomSeed)       ; New seed low byte = previous result * 2 (carry=0).
    RRCA                    ; Recover bit 0 of the previous result from bit 1.
    AND $01
    ADD A,$09               ; C=2: 0 -> Cobra trader, 1 -> Python trader
    DEC C
    JR Z,LaunchSelectedShip
    LD A,$12
    DEC C
    JR Z,LaunchSelectedShip ; C=3: Thargon
    LD A,$0F
    DEC C
    JR Z,LaunchSelectedShip ; C=4: Thargoid
    DEC C
    RET NZ
    CALL NextRandomByte     ; C=5: retain the second RNG call for hermit fighters
    AND $01
    ADD A,$10               ; Same Sidewinder/Krait choice, four bytes shorter
StationRandomLaunchFixEnd:
    assert StationRandomLaunchFixEnd-SelectParentLaunchType = ParentLaunchSelectionLimit-ParentLaunchSelectionStart
