; Optional random placement of single encounter ships: randomizedspawn=yes.
;
; InitialiseShipFromBlueprint places every new ship 12,800 units ahead (z = +$3200)
; and chooses x and y by the hostility bit of its blueprint.  A calm ship draws high
; bytes 0..7, which puts it within about 9 degrees of the view axis in x and in y.  A
; hostile ship keeps the template high bytes $32, about 45 degrees out in x and in y:
; one of the four diagonal corners.  Traders, the police Viper and the Fer-de-Lance
; therefore always appear straight ahead and pirates in a corner, so the player knows
; at once whether a newly arrived ship is a threat.
;
; With this option a single ship of a random encounter takes either placement with
; even odds, whatever its hostility: the Cobra and Python traders and pirates, the
; Viper, the Asp, the Fer-de-Lance, a lone Thargoid and the mission Python trader.
; Its type, hostility, energy, speed and AI are created as before; its ECM byte is
; drawn one or three bytes later, with the same chance.  Groups of
; Sidewinders and Kraits, Thargoid groups, asteroids, the Rock hermit (which keeps the
; placement of an asteroid), the special mission Asp with its escort, station and
; parent launches and all other objects keep the original placement, and their
; creation uses the RNG exactly as before.
;
; InitialiseEncounterShip sets bit 7 of the ID it passes on.  The loader masks the ID
; to six bits, and every other caller passes it with bit 7 clear.  The loader keeps
; the caller's A on the stack in place of an unread LD B,A and, after the fields that
; the original sets in the same bytes, tests hostility XOR bit 3 of one extra
; NextRandomByte instead of the hostility alone.  Without the request no byte is
; drawn and the test is the original one.
;
; Five parts replace original bytes in place; game.asm expands each one:
;   PUSH AF                                  $F2FE         (1 B, the unread LD B,A)
;   RandomizedSpawnPlacementCode             $F338..$F355  (30 B, last fields and test)
;   JR InitialiseEncounterShipByHostility    $F653..$F654  (2 B, the special Asp)
;   RandomizedSpawnRequestCode               $F6C8..$F6DA  (19 B, InitialiseEncounterShip)
;   RandomizedSpawnHermitCode                $F6FB..$F70D  (19 B, trader and hermit/Viper choice)

defc RandomizedPlacementRequest = $80           ; ID bit 7: random placement for this ship
defc BehaviourHostileBit = 2                    ; InstanceBehaviour bit 2: hostile
; The loader's RL C shifts the blueprint behaviour left by one before the test.
defc LoaderHostileMask = 1 << (BehaviourHostileBit+1)
defc InstanceFlagCounted = $40                  ; InstanceFlags bit 6: counted by EncounterShipCount
defc InitialAiState = $7E                       ; InstanceAiState of a new ship: no ECM, not fleeing
defc ShipIdRockHermit = 7
defc ShipIdViper = 8
defc ShipIdCobraTrader = 9
defc ShipIdPythonTrader = 10
defc ShipIdThargoid = 15
defc PythonTraderFirstChoice = 5                ; trader choice 2..4: Cobra, 5..7: Python
defc EncounterEcmChance = $33                   ; ECM fitted below this random byte
assert RandomizedPlacementRequest = $80         ; ADD A,A moves it into the carry
assert ShipIdViper = ShipIdRockHermit+1
assert ShipIdCobraTrader = ShipIdPythonTrader-1
assert ShipIdThargoid < EncounterEcmChance      ; a Thargoid passes the ECM test without a draw

; In InitialiseShipFromBlueprint after the payload count: A = the InstanceFlags value
; without bit 6, C = blueprint behaviour << 1, B = 0 (left by the template LDIR), the
; caller's AF on the stack.  The fields are those that the original sets here, in a
; different order and fewer bytes.
; Out: carry clear, as the original leaves it for the next NextRandomByte; the jump to
; RandomiseShipLowBytesAndSigns keeps the corner high bytes $32.
MACRO RandomizedSpawnPlacementCode
assert $-GameImage = RandomizedSpawnPlacementStart-GameLoadAddress
    OR InstanceFlagCounted              ; the original SET 6 of InstanceFlags
    LD (IX+InstanceFlags),A
    LD A,(IY+BlueprintMaximumSpeed)
    RRA                                 ; maximum / 2: the OR cleared the carry
    LD (IX+InstanceSpeed),A
    LD (IX+InstanceAiState),InitialAiState
    LD (IX+InstanceRoleFlags),B         ; 0: no role flags
    POP AF                              ; the caller's A
    ADD A,A                             ; carry = RandomizedPlacementRequest
    SBC A,A                             ; $FF when requested, otherwise 0 with Z
    CALL NZ,NextRandomByte              ; requested: one random byte
    XOR C                               ; bit 3: hostile XOR random bit, or hostile alone
    AND LoaderHostileMask               ; clears the carry
    JR NZ,RandomiseShipLowBytesAndSigns ; corner placement
RandomizedSpawnPlacementEnd:
assert RandomizedSpawnPlacementEnd-GameImage = RandomizedSpawnPlacementLimit-GameLoadAddress
ENDM

; InitialiseEncounterShip: A = blueprint ID, IX = a free slot, a saved AF on the stack
; (SaveEncounterShipId's ID, or $0F pushed by the special Asp for a fitted ECM).
; The same ECM test as the original in two bytes fewer.  The special Asp's
; continuation passes the returned carry to the NextRandomByte of its escort, so a
; Thargoid ID returns with the carry clear, as after the original CP $0F; the
; ordinary encounter caller ignores the flags.
MACRO RandomizedSpawnRequestCode
assert $-GameImage = RandomizedSpawnRequestStart-GameLoadAddress
    OR RandomizedPlacementRequest       ; ask for a random placement
InitialiseEncounterShipByHostility:     ; the Rock hermit and the special Asp enter here
    CALL InitialiseShipFromBlueprint
    POP AF                              ; the saved ID
    CP ShipIdThargoid
    CALL NZ,NextRandomByte              ; a Thargoid draws nothing and stays below the chance
    ADD A,256-EncounterEcmChance        ; carry: byte >= EncounterEcmChance, no ECM
    RET C
    SET 0,(IX+InstanceAiState)          ; ECM fitted; carry clear
    RET
RandomizedSpawnRequestEnd:
assert RandomizedSpawnRequestEnd-GameImage = RandomizedSpawnRequestLimit-GameLoadAddress
ENDM

; Entered with the carry of CP 2 on A = bits 7..5 of the encounter byte r2, and with
; C = r2 rotated left three times (bit 7 = r2 bit 4).  The original's trader choice
; takes two bytes more; the Rock hermit needs them to bypass the request.
MACRO RandomizedSpawnHermitCode
assert $-GameImage = RandomizedSpawnHermitStart-GameLoadAddress
    JR C,RandomizedSpawnHermitOrViper   ; 0..1: Rock hermit or Viper
SelectEncounterTraderType:              ; A = 2..7
    CP PythonTraderFirstChoice
    SBC A,A                             ; -1 for a Cobra trader
    ADD A,ShipIdPythonTrader
    JR SaveEncounterShipId
RandomizedSpawnHermitOrViper:
    LD A,C
    RLCA                                ; carry = r2 bit 4: Viper
    LD A,ShipIdViper
    JR C,SaveEncounterShipId            ; Viper: random placement like the other single ships
    DEC A                               ; Rock hermit: the placement of an asteroid
    PUSH AF
    JR InitialiseEncounterShipByHostility
RandomizedSpawnHermitEnd:
assert RandomizedSpawnHermitEnd-GameImage = RandomizedSpawnHermitLimit-GameLoadAddress
ENDM
