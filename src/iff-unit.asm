; Optional modification: iffunit=yes replaces the energy bomb with an I.F.F. unit.
;
; The energy bomb (equipment item 9, commander byte EnergyBombFitted, W key) is
; removed: UseEnergyBomb, the bomb test in the UpdateObjects slot loop, the
; clearing of EnergyBombPending and the W entry of KeyActionTable.  Item 9 keeps
; its price, tech level and commander byte, which now means "I.F.F. unit fitted";
; the equipment list, the status screen, "... PRESENT" and "... DESTROYED" use
; token 113, whose text becomes I.F.F. UNIT.  A saved commander keeps its format.
;
; With the unit fitted, DrawScannerContacts hides threats in every other half of
; a blink cycle, so they blink while all other contacts stay lit.  A threat is
;   - a missile whose target code (InstanceAiState) is the player (0); the
;     player's own missiles are always aimed at a locked object (code 1..8);
;   - any other object with the hostile bit of InstanceBehaviour set, unless it
;     is scoopable (canisters, escape capsules, debris, inert Thargons).  The
;     station counts while it is hostile.
; The game sets the hostile bit of every object while the player's missile flies
; (UpdateSharedHostility); the scoopable test keeps cargo from blinking then.
;
; IffBlinkClock counts cockpit-view frames: UpdateCockpitSystems calls IffBlinkTick
; where it called UseEnergyBomb.  Threats are hidden while bit 1 is set: two
; frames lit, two frames dark.  The 48K emulator check measured 5.6 cockpit frames
; per second with a pirate in view (about 1.4 blinks per second) and 9 just after
; launch with nothing near; more objects to draw make the blink slower.
; The clock byte lives in the freed UseEnergyBomb bytes: no extra RAM.
;
; Replaced parts (start and limit constants in src/options.asm):
;   CALL IffScannerContactEnergy  $8C3D..$8C3F  (3 B, first instruction of a scanner slot)
;   JP IffBlinkTick               $91C9..$91CB  (3 B, unreferenced vector to UseEnergyBomb)
;   IffScannerCode                $9260..$927F  (32 B, UseEnergyBomb)
;   IffUnitTokenText              $9D84..$9E73  (token 113 and the dictionary tail)
;   CALL IffBlinkTick             $A568..$A56A  (3 B, CALL UseEnergyBomb)
;   IffShipCode                   $DAC1..$DAD7  (23 B, the energy bomb test)
;   IffObjectsTailCode            $DBC8..$DBD4  (13 B, end of UpdateObjects)
;   defb $00,$00                  $FF72..$FF73  (KeyActionTable: W has no action, as Z and V)
; FlashViewAttributes stays: the unreferenced vector at L_91CC still jumps to it.

defc IffUnitFitted = EnergyBombFitted   ; commander +$36, equipment item 9
defc IffBlinkHiddenPhase = $02          ; IffBlinkClock bit 1 set: threats not drawn
defc IffMissileRoleBit = 0              ; InstanceRoleFlags bit 0: missile
defc IffScoopableRoles = $02            ; InstanceRoleFlags bit 1: scoopable, never a threat
defc IffHostileBit = 2                  ; InstanceBehaviour bit 2: hostile
defc IffTokenUnit = $AE                 ; PrintToken code of dictionary token 14: UNIT

; Called instead of LD A,(IX+InstanceEnergy) at the start of every scanner slot.
; Out: A = the slot's energy, or 0 for a threat in the dark half of the blink, which
; DrawScannerContacts then skips like an empty slot.  IX preserved; F clobbered (the
; caller tests A with AND A).
MACRO IffScannerCode
assert $-GameImage = IffScannerCodeStart-GameLoadAddress
IffScannerContactEnergy:
    LD A,(IffUnitFitted)
    AND A
    JR Z,IffShowContact                 ; no I.F.F. unit: every contact is drawn
    LD A,(IffBlinkClock)
    AND IffBlinkHiddenPhase
    JR Z,IffShowContact                 ; lit half of the blink
    BIT IffMissileRoleBit,(IX+InstanceRoleFlags)
    JP Z,IffShipContact                 ; not a missile: hostile bit test
    LD A,(IX+InstanceAiState)           ; missile target code: 0 = the player
    AND A
    RET Z                               ; aimed at the player: A = 0 hides it
IffShowContact:
    LD A,(IX+InstanceEnergy)
    RET
; Cockpit-view frame counter, advanced by IffBlinkTick.
IffBlinkClock:
    defb $00
IffScannerCodeEnd:
assert IffScannerCodeEnd-GameImage <= IffScannerCodeLimit-GameLoadAddress
    defs (IffScannerCodeLimit-GameLoadAddress)-(IffScannerCodeEnd-GameImage),0 ; unused
ENDM

; The energy bomb test of the UpdateObjects slot loop is gone: the loop continues
; at UpdateSharedHostility.  The rest of the part holds the hostile bit test of
; IffScannerContactEnergy and IffBlinkTick.
MACRO IffShipCode
assert $-GameImage = IffShipCodeStart-GameLoadAddress
    JR UpdateSharedHostility            ; no energy bomb
; IffScannerContactEnergy for an object that is not a missile, in the dark half.
IffShipContact:
    LD A,(IX+InstanceRoleFlags)
    AND IffScoopableRoles
    JR NZ,IffShowShipContact            ; scoopable: never a threat
    BIT IffHostileBit,(IX+InstanceBehaviour)
    RET NZ                              ; hostile: A = 0 hides it
IffShowShipContact:
    LD A,(IX+InstanceEnergy)
    RET
; Called once per cockpit-view frame by UpdateCockpitSystems.  Clobbers: HL, F.
IffBlinkTick:
    LD HL,IffBlinkClock
    INC (HL)
    RET
IffShipCodeEnd:
assert IffShipCodeEnd-GameImage = IffShipCodeLimit-GameLoadAddress ; UpdateSharedHostility follows
ENDM

; End of UpdateObjects without the clearing of EnergyBombPending: as the original,
; clear SharedHostilityAlert when TorusJumpInhibitFlag is zero.
MACRO IffObjectsTailCode
assert $-GameImage = IffObjectsTailStart-GameLoadAddress
    LD A,(TorusJumpInhibitFlag)
    AND A
    RET NZ                              ; ships present: keep the shared alert
    LD (SharedHostilityAlert),A         ; none: clear the shared alert
    RET
IffObjectsTailEnd:
assert IffObjectsTailEnd-GameImage <= IffObjectsTailLimit-GameLoadAddress
    defs (IffObjectsTailLimit-GameLoadAddress)-(IffObjectsTailEnd-GameImage),0 ; unused
ENDM

; Token 113, the name of equipment item 9: I.F.F. UNIT instead of ENERGY BOMB.
; Three bytes longer; the three empty tokens 146..148 at the end of the dictionary,
; which no PrintToken code reaches (codes $0E..$1F end at token 145), are dropped,
; so TextTokenDictionaryEnd keeps its address.
MACRO IffUnitTokenText
    defm "I.F.F. "
    defb IffTokenUnit,$00
ENDM
