"""$D400..$DFFF: tape glue, flight messages, hyperspace/arrival/missions, crosshair, object update.

Evidence: instruction semantics; decoded tokens/messages (tools/text_codec.py); 48K runtime
traces (hyperspace, galactic hyperspace, mission-one, combat, docking, ECM/bomb scenarios);
SkoolKit Simulator tests of the unchanged image in tools/check_routines.py: missions/
hyperspace-arrival (galaxy gate, mission triggers, pirate boarding, mission-3 states),
missions/energy-bomb-exemption, screen/xor-crosshair, screen/pixel-screen-address,
numbers/fuel-and-seed-helpers, maths/square-root-and-normalise, maths/rotation-helpers and
the pass-2 checks pipeline/r8-projected-object-size, missions/r8-docking-contact,
missions/r8-energy-drain, missions/r8-object-presence-flags and maths/r8-motion-helpers.
"""

SECTIONS = {
    0xD44C: ('Flight view title and message line',
             'View name overlay, timed in-flight messages, warnings and mission MAYDAY calls.'),
    0xD574: ('Hyperspace: keys, countdown, jump and arrival',
             'Normal and galactic jumps, mis-jump, new-system set-up, jump counter,\n'
             'mission triggers and the pirate boarding test.'),
    0xD883: ('Chart crosshair',
             'XOR crosshair with screen-edge and vertical clipping, drawn by the chart screens.'),
    0xDA0B: ('Object update loop',
             'Per-update variables, the eight-slot object loop, removal/explosion handling.'),
    0xDBD5: ('Vector and object-motion arithmetic',
             'Vector normalisation, square root, orientation rotation and position updates.'),
}

LABELS = {
    # ------------------------------------------------------------------ tape glue
    0xD407: ('ReportTapeBreak', 'verified', """
Stop a tape operation: clear the status lines (ClearPromptLines), print message $C7
"BREAK" on the status line and return to the access-menu loop at L_D3ED.
Reached by JP NC after a failed ROM save ($D37E) and after a failed load when the key
code in LastKeyCode is $20.  The active record is not restored: after a BREAK during a
load the bytes already read stay in ActiveCommanderRecord.
Evidence: decoded message $C7; tools/check_routines.py commander/p7-tape-load-paths."""),
    0xD411: ('ReportTapeLoadingError', 'verified', """
Failed load: print message 3 "TAPE LOADING ERROR", copy the commander snapshot back into
ActiveCommanderRecord (L_7C2D) and return to the access-menu loop at L_D3ED.
Evidence: decoded message 3; docs/COMMANDER-STATE.md for L_7C2D."""),
    0xD41B: ('SetCommanderTapeParameters', 'verified', """
IX = ActiveCommanderRecord, DE = ActiveCommanderRecordSize (104 bytes), A = $FF (data
block flag): the register set of the ROM LD-BYTES ($0562) and SA-BYTES ($04C6) entries.
Changes only A, DE and IX.
Evidence: both callers (L_D326, $D373) enter the ROM directly after this call."""),
    0xD425: ('PromptCommanderName', 'verified', """
Read a commander name: A = message 8 "COMMANDER'S NAME? ", B = 10 characters maximum,
HL = destination supplied by the caller; tail-jump to the line-input routine InputString
(stores the typed characters at HL followed by a zero byte).
Callers: AccessMenuLoad (search name in NameInputBuffer before a load),
AccessMenuSave (ActiveCommanderRecord)."""),
    0xD42C: ('PrintStatusLineMessage', 'verified', """
Print message A on the bottom status line: LetterCaseMode = 0 (title case),
TextColumn = 0, TextRow = $16, clear that text line (FillPromptRow22 with A = 0),
print the message, NewLine, then L_AF39 (ROM beep when bit 7 of ControlOptions is set).
Used for the tape messages FOUND COMMANDER, START TAPE..., COMMANDER SAVED, BREAK and
TAPE LOADING ERROR.  Clobbers AF, BC, DE, HL."""),
    # ------------------------------------------------------- flight message line
    0xD444: ('MissionMessageDelay', 'verified', """
Delay between mission MAYDAY broadcasts.
When zero, CheckFlightWarnings reloads it with 70 and tests the mission states;
otherwise each idle warning check only decrements it."""),
    0xD445: ('FlightMessageTimer', 'verified', """
Updates remaining for the current flight message.
14 for ordinary messages (ShowFlightMessage), 21 for the hyperspace messages (L_D5C2).
The text is printed only while the value before the decrement is 4 or more, so the
last three updates leave the line empty."""),
    0xD446: ('FlightMessageAlternator', 'verified', """
Incremented whenever no message is shown; bit 0 alternates between the status-warning
check (L_D500, odd) and the scan of the pending-message table L_A87F (even)."""),
    0xD447: ('FlightMessageColumn', 'verified', """
Text column of the current flight message (row 14)."""),
    0xD448: ('FlightMessageToken', 'verified', """
Token of the current flight message.
$FD (" DESTROYED") follows the item token in DestroyedItemToken; $E2 (" CR") follows
LastBountyAmount.  L_A5F0 suppresses a new equipment loss while $FD is shown;
ClearPendingFlightMessages zeroes it."""),
    0xD449: ('LastBountyAmount', 'verified', """
Bounty word in tenths of a credit for the " CR" message, stored by L_A900 when nonzero.
L_DB43 passes blueprint bytes +8/+9 (bounty, docs/SHIPS.md) to L_A900."""),
    0xD44B: ('DestroyedItemToken', 'verified', """
Token printed before " DESTROYED": L_A61A stores $6C+item for a lost equipment item
($73 = "DOCKING COMPUTERS", printed without the 3-column indent)."""),
    0xD44C: ('PrintViewTitleAndMessages', 'verified', """
Text overlay for the current screen.
Flight views (CurrentScreenId 0..3): set bit 7 of the character renderer's screen-base
high byte (L_BB81, operand of LD HL,$4000 at LoadCharacterScreenBase) so text goes to
ViewBitmapBuffer, print token $60+view ("FRONT".."RIGHT") and " VIEW " at column 10
row 1, update the message line (UpdateFlightMessage), then restore the $40 screen base.
Other screens: patch CharacterBlendOpcode to NOP (overwrite), run UpdateFlightMessage and
restore XOR C ($A9).  Also sets LetterCaseMode = 0 (title case).
Runtime: every flight-view trace."""),
    0xD486: ('UpdateFlightMessage', 'verified', """
Once per main-loop pass: UpdateHyperspaceCountdown and L_A4BD, then the message line.
While FlightMessageTimer is nonzero, decrement it and redraw the message.
Otherwise toggle FlightMessageAlternator: odd -> CheckFlightWarnings; even -> take the
first pending entry of the 9-entry table L_A87F (bit 7 of the column byte = pending,
next byte = token), clear its bit 7 and show it with a beep.  At most one pending
message is taken per call; nothing pending: return."""),
    0xD4AE: ('BeepAndShowFlightMessage', 'verified', """
Beep (L_AF39), then show token B at column C (falls into ShowFlightMessage)."""),
    0xD4B3: ('ShowFlightMessage', 'verified', """
FlightMessageTimer = 14, then fall into SetFlightMessageText."""),
    0xD4B8: ('SetFlightMessageText', 'verified', """
FlightMessageColumn = C, FlightMessageToken = B."""),
    0xD4C1: (None, 'verified', """
Message shown: decrement FlightMessageTimer.
Print only if the old value >= 4 and a flight view is shown: row 14, column
FlightMessageColumn; tokens $FD and $E2 as described at FlightMessageToken."""),
    0xD500: ('CheckFlightWarnings', 'verified', """
Status warnings, in priority order (B = token, C = column):
- EnergyBank4 < $9F: switch the cloak off (CloakingDeviceActive = 0), set the view
  window attributes to L = 7 with FillViewAttributes on a flight view, "ENERGY LOW" at
  column 10.
- FuelScoopRangeFlag nonzero (sun within fuel-scoop range) and FuelScoopsFitted:
  fuel + 1 tenth (SetFuelLevel, capped at 70), "FUEL SCOOPS ON".  Without scoops: nothing.
- DockingComputerFlag nonzero: "DOCKING COMPUTERS ON".
- Otherwise every 70th check (MissionMessageDelay): mission-3 state L_A871 = 1 ->
  "MAYDAY * <name> INVADED*"; mission 1 active (L_A843) and L_A87C zero (not yet set
  by ArmExpandingSun) -> "MAYDAY * CORIOLIS IN DANGER*".
Runtime: energy/fuel-scoop paths not traced."""),
    0xD563: ('ClearPendingFlightMessages', 'verified', """
Clear the pending bit 7 of all 9 entries of PendingMessageTable and zero
FlightMessageToken (the timer is not changed).  Exit: A = 0, B = 0, HL = end of the
table.  Callers: L_9A46, InitialiseCommander (new game), ExecuteHyperspaceJump."""),
    # --------------------------------------------------------------- hyperspace
    0xD573: ('HyperspaceCountdown', 'verified', """
Hyperspace countdown in message-line updates: 21 when a jump is accepted, 0 when idle.
UpdateHyperspaceCountdown prints value/2 (10..1) and jumps when it reaches zero.
Also written by $A9AE."""),
    0xD574: ('CheckHyperspaceKeys', 'verified', """
Main-loop key check (L_72A2).  If KeyFlagsViews bit 4 (H) or bit 5 (G) is set, both
are cleared and L_7C39 = 1, before any other test, so a request that is then ignored
also sets it (CheckDocking returns while it is set; only an arrival or the game-over
path clears it).  Ignored while HyperspaceCountdown runs.  Docked (FlightCondition = 0):
print "DOCKED" and show the status screen.  G needs H as well (G alone is consumed
without effect) and GalacticHyperdriveFitted: L_A80A = 2, "GALACTIC HYPERSPACE".
H alone: SnapCursorToNearestSystem selects the target; SelectedSystemDistance 0 is
ignored silently, >= 256 or above FuelLevel gives "HYPERSPACE RANGE ?"; otherwise
L_A80A = 1 and "HYPERSPACE -- <name>".
An accepted jump sets HyperspaceCountdown = FlightMessageTimer = 21 and beeps.
Evidence: hyperspace traces press H (bit 4 path); the galactic trace holds G with H;
tools/check_routines.py missions/r8-docking-contact (G alone sets L_7C39)."""),
    0xD5D0: (None, 'verified', """
Target out of range: beep and show "HYPERSPACE RANGE ?" at column 6."""),
    0xD5D6: (None, 'verified', """
Hyperspace key while docked: print message $CD "DOCKED" at column 11 row 7, beep and
continue at the status screen L_D0B9."""),
    0xD5F5: ('UpdateHyperspaceCountdown', 'verified', """
If HyperspaceCountdown is nonzero, decrement it; at zero continue with
ExecuteHyperspaceJump, otherwise print the old value / 2 in a 2-digit field (L_A88E) at
column 1 row 1."""),
    0xD610: ('ExecuteHyperspaceJump', 'verified', """
Countdown expired: ClearPendingFlightMessages.
L_A80A = 2 -> GalacticHyperspaceJump, any other value -> NormalHyperspaceJump.
Runtime: hyperspace and galactic traces."""),
    0xD61A: ('GalacticHyperspaceJump', 'verified', """
Clear the mission-3 state (L_A871); if mission 1 is active (L_A843) clear L_A843
and L_A87C; clear GalacticHyperdriveFitted (always, also when forced by mission 1).
L_9237 = old galaxy + 1, CurrentGalaxy = (galaxy + 1) AND 7, rotate every byte of the
three galaxy seed words at GalaxySeeds left by one bit, clear PlayerLegalScore, select
the system nearest the chart cursor in the new galaxy (SnapCursorToNearestSystem), then
ArriveInTargetSystem.  No fuel is used."""),
    0xD64F: ('RotateSeedWordLeft', 'verified', """
RLC both bytes of the word at HL; HL += 2.  Clobbers DE.
Evidence: tools/check_routines.py numbers/fuel-and-seed-helpers."""),
    0xD65A: ('NormalHyperspaceJump', 'verified', """
While mission 1 is active (L_A843) every jump is a galactic jump.  Otherwise
fuel = fuel - distance (low byte of SelectedSystemDistance) via SetFuelLevel,
L_9237 = 2*SelectedSystemEconomy + (70 - new fuel), PlayerLegalScore halved.
Bit 6 of ControlOptions, or a byte of $F9 at AuxRandomSeed, selects
EnterHyperspaceMisjump; otherwise ArriveInTargetSystem."""),
    0xD68B: ('EnterHyperspaceMisjump', 'verified', """
Mis-jump: WitchspaceFlag = A+1 ($FA, or the option byte + 1 when forced by
ControlOptions bit 6).  The galactic x/y bytes CurrentSystemX/ChartCursorX and
CurrentSystemY/ChartCursorY are both set to the 9-bit average of current and target;
StationPresent = CurrentSystemName = SelectedSystemName = 0; then
FinishHyperspaceArrival (no new system, no mission or pirate test).
INFERRED: witchspace; WitchspaceFlag nonzero suppresses the ordinary encounter event
in UpdateObjects."""),
    0xD6B3: ('ArriveInTargetSystem', 'verified', """
WitchspaceFlag = 0; the target seeds SelectedSystemSeeds (6 bytes) become
CurrentSystemSeeds; copy the 8-byte name SelectedSystemName -> CurrentSystemName;
CurrentTechLevel = SelectedSystemTechLevel, CurrentGovernment =
SelectedSystemGovernment; new market (RandomiseMarket).
Clear SunPosition and PlanetPosition (9 bytes each), StationDormantFlag = $FF (station
dormant), then set only their sign/high bytes from the target seeds s0, s1, s2:
sun x = s2.hi, y = s2.lo (AND $83, OR 1), z = -(((s1.hi OR s1.lo) AND 7) + 4, OR 1);
planet x = s0.lo, y = s1.lo (AND $83, OR 1), z = +(((s0.hi OR s0.lo) AND 7) + 3).
The station (slot 0) is placed at the planet position offset by $18000 along z (s2
bit 0 set) or x, away from the origin when s2 bit 1 is set, otherwise towards it
(crossing zero for a high magnitude of 1).  Its orientation becomes Y = (0, 1, 0), the
Z (nose) axis along the offset axis and X along the other horizontal axis; the nose
points to + when the station's high byte is below the planet's (raw byte compare, sign
bit included), else to -.  For positive coordinates (always for z) that is towards the
planet.  For a negative planet x the raw compare is reversed, and so is the
nose: the docking slot then faces directly away from the planet.
Over all 2048 systems the offset is along z in galaxies 1, 3, 5 and 8 (all slots face
the planet) and along x in galaxies 2, 4, 6 and 7, where 464 systems get the reversed
slot.  Then L_D7B4.
Evidence: tools/check_routines.py station/arrival-slot-direction."""),
    0xD7B4: (None, 'verified', """
Arrival tail.
Copy the galactic x/y bytes ChartCursorX -> CurrentSystemX and ChartCursorY ->
CurrentSystemY, then the galaxy gate.  In galaxy 0 skip directly to
FinishHyperspaceArrival.  Otherwise:
- station +$26 bit 7 set -> clear it, mission-3 state L_A871 = 5;
- L_A871 1 -> 2, 4 -> 3; then any nonzero state becomes 4 at the system whose seeds
  equal the galaxy seeds (CompareWithGalaxySeeds), where UpdateObjects makes the
  station hostile.
Evidence: tools/check_routines.py missions/hyperspace-arrival."""),
    0xD7C4: (None, 'verified', """
Galaxy gate.
CurrentGalaxy = 0 branches to FinishHyperspaceArrival, skipping the jump counter,
mission triggers and pirate test.  The POKE that changes MissionGalaxyGateOperand
from $4E to 0 makes this JR fall through, enabling them in galaxy 0.
Evidence: tools/check_routines.py missions/hyperspace-arrival."""),
    0xD7EE: (None, 'verified', """
Increment the 16-bit jump counter L_A825 (counted only outside galaxy 0) and test the
first clear mission flag of L_A872 against the counter's low byte:
bit 0 at >= $20 (mission 1), bit 1 at >= $80, bit 2 at >= $FE.  A trigger skips the
pirate test; otherwise (or with all three bits set) the pirate test follows."""),
    0xD802: (None, 'verified', """
Pirate boarding test: board when the byte at AuxRandomSeed <= 7 - government
(CurrentGovernment), i.e. (8 - government) of 256 values.  Boarding clears bit 7
(continuous roll) of the station's +$1D roll byte, so the station stops rotating;
CheckPirateGameOver ends the game at docking with the "PIRATES" message when that bit
is clear.  AuxRandomSeed is the low byte of the dust generator state (AdvanceRandomHL),
used here as a random byte.
Evidence: tools/check_routines.py missions/hyperspace-arrival."""),
    0xD80D: (None, 'verified', """
Boarding chance branch.
PirateChanceOperand ($05) skips the boarding store; the POKE value 0 makes every
non-mission jump outside galaxy 0 board the station."""),
    0xD812: (None, 'verified', """
Boarding store RES 7,(HL); PirateBoardingCompare is its second opcode byte.  The POKE
$BE -> $FE turns it into SET 7,(HL), so boarding never takes effect."""),
    0xD814: ('FinishHyperspaceArrival', 'verified', """
Common exit of every jump path.
L_A80B = 1, CurrentScreenId = 0 (front view); clear CabinTemperature,
FuelScoopRangeFlag, MissileState, MissionAspEncounterState and the jump-request latch
L_7C39; AltitudeGauge = $A0."""),
    0xD832: (None, 'verified', """
Mission 1 trigger (low byte of the jump counter >= $20): set CommanderFlags bit 0,
L_A843 = 1, fill the view attributes with colour 2 (FillViewAttributes, L=2) and
TriggerFuelLeak."""),
    0xD849: (None, 'verified', """
Mission 2 trigger (>= $80): set CommanderFlags bit 1.  This bit (with bit 6 clear)
enables the Asp Mk II encounter at $F62C, tracked by MissionAspEncounterState."""),
    0xD853: (None, 'verified', """
Mission 3 trigger (>= $FE): set L_A872 bit 2 and mission-3 state L_A871 = 1."""),
    0xD862: ('TriggerFuelLeak', 'verified', """
If fuel (FuelLevel) is nonzero: mark the pending "FUEL LEAK*" message (bit 7 of
FuelLeakMessage) and set fuel to 0 through SetFuelLevel.
Callers: mission 1 trigger, damage path DamageEquipmentOrCargo."""),
    0xD86D: ('SetFuelLevel', 'verified', """
FuelLevel = min(A, 70) in tenths of a light year; FU bar FuelGauge =
2*fuel + (2*fuel >> 3) (70 -> 157).  Clobbers A, B, F.
Evidence: tools/check_routines.py numbers/fuel-and-seed-helpers (all A)."""),
    0xD873: ('StoreFuelLevel', 'verified', """
SetFuelLevel after its limit: FuelLevel = A, any value, and the FU bar value
FuelGauge = 2*A + (2*A >> 3).  Clobbers A, B, F.
Evidence: tools/check_routines.py numbers/fuel-and-seed-helpers (A up to 70 reaches it
through the JR C)."""),
    # ------------------------------------------------------------------ crosshair
    0xD883: ('CrosshairSize', 'verified', """
Arm length of the XOR crosshair in pixels: $18 for the short-range chart centre mark,
$10 for the cursor (callers L_A9D0, L_AB4E); L_B1C0 compares it with $0A."""),
    0xD884: ('CrosshairTopLimit', 'verified', """
First screen row the vertical arm may use.  Only read (stays 0 in the reference)."""),
    0xD885: ('CrosshairBottomLimit', 'verified', """
Vertical-arm clip row: $A7 (short-range chart), $98 (galactic chart)."""),
    0xD886: ('DrawXorCrosshair', 'verified', """
XOR a "+" of size CrosshairSize centred on pixel (ShapeCentreX, ShapeCentreY) of the
screen at $4000.  The horizontal arm runs from x - size/2; it is clipped at the screen
edges, and a clipped arm leaves column 0 (left) or 255 (right) untouched.  The vertical
arm is clipped to CrosshairTopLimit..CrosshairBottomLimit; the centre pixel is toggled
twice (left clear).  Calling it again erases it.  Clobbers AF, BC, DE, HL.
Evidence: tools/check_routines.py screen/xor-crosshair.  Callers: chart screens L_A9D0,
DrawGalacticChart and L_B221."""),
    0xD96D: ('MakeLeftPixelMask', 'verified', """
E = byte with its E leftmost bits set (E = 1..8).  A is also the mask."""),
    0xD975: ('MakeRightPixelMask', 'verified', """
D = byte with its D rightmost bits set (D = 1..8).  A is also the mask."""),
    0xD97D: ('GetPixelScreenAddress', 'verified', """
HL = screen bitmap address of the byte holding pixel x = A, y = C.
Evidence: tools/check_routines.py screen/pixel-screen-address."""),
    0xD9A5: (None, 'verified', """
Vertical arm of DrawXorCrosshair, clipped to CrosshairTopLimit/CrosshairBottomLimit."""),
    0xDA01: ('AdjustScreenAddressCellRow', 'verified', """
After INC H stepped HL out of a character cell: L += $20, and H -= 8 unless that carried
into the next screen third.  Evidence: tools/check_routines.py screen/pixel-screen-address."""),
    # ----------------------------------------------------------- object update
    0xDA0B: ('ProjectedObjectSize', 'verified', """
Projected size of the object being drawn: min(255, 256 * blueprint +1 (size) / depth),
computed by DivideRatioByte at $E094 once the depth exceeds the size (otherwise the
object is not drawn and the byte keeps its old value).  L_E0B5 compares the projected
centre with it (crosshair test); L_E1D4 copies it to instance +$1F when an object with
+$20 bit 4 set has its screen position recorded.
Evidence: tools/check_routines.py pipeline/r8-projected-object-size (5 blueprints, 4 views,
6 depths: equal to the DivideRatioByte model, copied to +$1F)."""),
    0xDA0C: ('MissionAspEncounterState', 'verified', """
Mission Asp encounter state.
0 none; 1 set by $F62C when it spawns an Asp Mk II (blueprint 13) marked with
+$26 bit 6, only if L_A872 AND $42 = $02 (mission-2 flag set, bit 6 clear);
L_F745 switches 1 <-> 2;
3 after the marked ship is destroyed ($EC9B).  Cleared on arrival and when the marked
ship is removed in states 1/2.  INFERRED: the cloaked-Asp mission encounter."""),
    0xDA0D: (None, 'inferred', """
Unused byte: no static reference and no access in any runtime trace."""),
    0xDA0E: ('ObjectUpdateCounter', 'verified', """
Decremented by every UpdateObjects call, so it wraps every 256 updates.
Reaching 0 dispatches event 0 (random encounter) when allowed.
Also schedules AI per slot (L_DB71) and gates laser firing ($EC0C).
L_9966 (Torus jump) sets it to 1, so that the next update dispatches an encounter,
but only when AlternatingBits was $AA (dust respawns rotate the same byte)."""),
    0xDA0F: ('TorusJumpInhibitFlag', 'verified', """
Set to 1 during UpdateObjects when an active slot has +$26 bit 3 clear: any object
except the station (initial +$26 = $0C) and the children made by L_F592/L_F5B8 with
+$26 = $0A (escape capsules, cargo canisters, splinters); ordinary ships, asteroids and
missiles count (InitialiseShipFromBlueprint clears +$26).  Cleared at the start of
every update.  Nonzero makes HandleTorusJumpKey refuse the Torus jump; zero after the
slot loop clears SharedHostilityAlert.
Evidence: tools/check_routines.py missions/r8-object-presence-flags, dust/torus-jump."""),
    0xDA10: ('EnergyBombPending', 'verified', """
Energy bomb request.
Set by UseEnergyBomb (key bit 5 of KeyFlagsCombat with EnergyBombFitted, which is used
up).  The next UpdateObjects sets the explosion bit 4 of +$20 in every active slot
without +$26 bit 2, unless the blueprint in IY has maximum speed 39 (Thargoid), then
clears this byte.
NOTE: IY still holds the previously processed slot's blueprint at that test, so the
slot after a Thargoid is spared and the Thargoid is not.
Evidence: tools/check_routines.py missions/energy-bomb-exemption."""),
    0xDA11: ('LastActiveObjectEnergy', 'verified', """
Cleared by UpdateObjects, then set to the energy of each active slot: nonzero when at
least one slot is active (the station counts).
Read by DrawFlaggedObjectDiscs and DrawScannerContacts."""),
    0xDA12: ('TargetedObjectCounter', 'verified', """
Slot-loop counter (8 - slot index) of the object found by the projection test at $E0C8,
0 = none; cleared every update.  The laser hit at $EC3C converts it back to an instance
(ApplyPlayerLaserHit) and missile targeting ($A719) locks it into L_A89A."""),
    0xDA13: (None, 'inferred', """
Unused byte: no static reference and no access in any runtime trace."""),
    0xDA15: ('DockingContactFlag', 'verified', """
Manual docking accepted.  Set to 1 only at $EB0C: the player touched the station (an
object with +$26 bit 2, within its size on all axes) while it is in front, not hostile,
its nose (Z axis z component) points at the player and |Z.x|, |Z.y| (high bytes) are
both below $1E.  CheckDocking clears it and docks (DockWithStation), unless the
jump-request latch L_7C39 is set: then it returns first and the flag stays set.
LaunchFromStation clears it.  Wider misalignment below $6E costs front damage
(12 + 2*speed) instead; worse alignment, a hostile station or approach from behind
sets L_707A = $0F.
Evidence: tools/check_routines.py missions/r8-docking-contact."""),
    0xDA17: ('EnergyDrainThisUpdate', 'verified', """
Energy drain units collected during one update.
Cleared by UpdateObjects; +1 for each player laser shot (L_EC11) and for each update with
the player's ECM running (L_EDA9).  $A59D adds 1 while the cloaking device is on and
subtracts the total four times from the energy banks (L_A5A6), bank 1 first.
Evidence: tools/check_routines.py missions/r8-energy-drain."""),
    0xDA18: ('FrontDamageThisUpdate', 'verified', """
Damage collected this update from objects with z >= 0.
Sources: collisions (L_EB10/L_EB5E) and AI lasers (L_FAF0).  L_A584 subtracts it from
L_7046; overflow drains the energy banks."""),
    0xDA19: ('RearDamageThisUpdate', 'verified', """
As FrontDamageThisUpdate for objects with negative z (+8 bit 7); applied to L_7048."""),
    0xDA1A: ('LastNonStationObjectEnergy', 'verified', """
Cleared by UpdateObjects, then set to the energy of each active slot without +$26 bit 2
(every object except the station): nonzero when such an object is present.  L_8DDE then
sets the yellow condition (L_7062 = 6) unless it is red (2) or flashing ($63).
Evidence: tools/check_routines.py missions/r8-object-presence-flags."""),
    0xDA1C: ('ObjectLoopCounter', 'verified', """
Counter of the slot being updated: 8 for slot 0 down to 1 for slot 7.  L_EB65 compares
it with +$25 of the other instances and with the locked missile target L_A89A."""),
    0xDA1D: ('UpdateObjects', 'verified', """
Per-frame object update, called from the flight loops.
- Mission-3 state 4: set the station's hostile bit (+$21 bit 2).
- Patch the four pixel-combine opcodes of the line renderer (L_F203, L_F231, L_F252,
  L_F27E): OR C ($B1) when L_707B is zero, XOR C ($A9) otherwise.
- Decrement ObjectUpdateCounter; at 0 (every 256th update) dispatch event 0 (random
  encounter) unless the station is present, L_7061 is set or EncounterShipCount >= 4.
- Clear the per-update variables, recount EncounterShipCount, then update all 8 slots
  (L_DA9A); afterwards clear EnergyBombPending and maybe SharedHostilityAlert.
Clobbers all registers including IX and IY."""),
    0xDA9A: (None, 'verified', """
Slot loop: A = ObjectLoopCounter (8..1) is kept on the stack; IX = instance.  Skip slots
with zero energy.  Record LastActiveObjectEnergy / LastNonStationObjectEnergy /
TorusJumpInhibitFlag, apply the energy bomb, then UpdateSharedHostility and the state
dispatch at L_DAFA.  B = counter and C = ObjectUpdateCounter stay set for the AI phase."""),
    0xDAFA: (None, 'verified', """
IY = blueprint (+$23/+$24).  +$20 bits 5:4 select: 00 alive (L_DB71), 10 remove and
credit (L_DB0F), 01/11 exploding: only L_DBA3."""),
    0xDB0F: (None, 'verified', """
Remove a destroyed object: clear +$20 bit 5, +$1E = 0, +$1D = $C0.  Unless +$26 bit 0:
set L_707D bit 2 and end MissionAspEncounterState when the marked ship (+$26 bit 6) goes
in state 1/2, or in state 3 when blueprint +1 is $1E (no reference blueprint has $1E).
Always continues at L_DB43, which frees the slot."""),
    0xDB43: (None, 'verified', """
Free the slot (energy 0), release references (L_EB65), add the blueprint bounty (+8/+9)
via L_A900 and half the word at +$15/+$16 via L_A8EE.  Behaviour +$21 AND $60 nonzero
(trader records, rock hermit, Viper): PlayerLegalScore OR $40."""),
    0xDB71: (None, 'verified', """
Alive object: if +$20 bit 6, run AI - UpdateMissileGuidance every update when +$26
bit 0 is set (INFERRED: missile), otherwise UpdateShipTactics when
(counter XOR ObjectUpdateCounter) AND 3 = 0, so the ships take turns, each on one
update in four.  Then MoveObject, OrthogonaliseYVector and RenormaliseOrientationVector
for the three vectors at +9."""),
    0xDBA3: (None, 'verified', """
L_EA51 (collision, scooping, docking contact), draw/project (DrawObjectInView), clear
+$20 bit 3; an explosion state 01 advances to 10."""),
    0xDBBE: (None, 'verified', """
Next slot (IX += InstanceSize).  After slot 7 clear EnergyBombPending; clear
SharedHostilityAlert when TorusJumpInhibitFlag is zero."""),
    # ---------------------------------------------------------- vector maths
    0xDBD5: ('NormaliseVector', 'verified', """
IX -> three sign-magnitude words (bit 15 = sign).  Scale the vector to length $8000
(about 3% error): each component becomes |c| * 32768 / length with its sign kept.
Return DE = the original length (SquareRootHL of the summed squares / 65536).
A component not smaller than the computed length overflows the division
(DivideWordFraction needs HL < DE).  IX preserved; A = 0; clobbers BC, HL.
Evidence: tools/check_routines.py maths/square-root-and-normalise.  Caller L_F9FA."""),
    0xDBFA: ('SquareVectorComponent', 'verified', """
HL = (|word at IX|)^2 >> 16 using MultiplyUnsigned and the square tables; IX += 2.
The square is assembled as B^2*65536 + 2*B*C*256 + C^2 for the word B:C."""),
    0xDC31: ('DivideVectorComponent', 'verified', """
Word at IX = sign-preserving (|word| / DE) via L_E8CF, halved; IX += 2.
With A = 0 (as in NormaliseVector) the new magnitude is |word| * 32768 / DE; BC returns
the new word."""),
    0xDC53: ('SquareRootHL', 'verified', """
HL = 256 * sqrt(HL), approximately; A = 0 on return, BC and DE clobbered.
Within 3.5% for HL >= 16, coarser below.  HL < $1000 is pre-scaled by 16 (result / 4),
HL < $100 by 256 (result / 16) before L_DC7A.
Evidence: tools/check_routines.py maths/square-root-and-normalise, maths/r8-motion-helpers
(A = 0 on return)."""),
    0xDC7A: (None, 'verified', """
Square-root core for N = HL: three Newton steps x' = (x + 16384*N/x) / 2 towards
x = 128*sqrt(N), starting from x = $8000 (L_DC97/L_DC8D, using L_E8CF).  Each step
returns HL = 2*x', so the result is HL ~ 256*sqrt(N)."""),
    0xDC8D: (None, 'verified', """
One Newton step of the square-root core (second and third iterations): halve the previous
HL (17 bits with the carry) to get x, then L_DC97 with N from DE."""),
    0xDC97: (None, 'verified', """
Newton step: HL = DE + (quotient from DivideWordFraction) / 2, with DE = x and
HL.A = N/2 on entry, i.e. HL = x + 16384*N/x; A = 0 on return."""),
    0xDCA3: ('RenormaliseOrientationVector', 'verified', """
IX -> three words (high bytes, bit 7 = sign).  Scale the high bytes by B/128 with
B = $80 - S/4, where S is the 8-bit sum of the squared doubled magnitudes / 256
(= |v|^2/64) taken as a signed value: S wraps to 0 at length 128, so lengths just below
grow and lengths above shrink (the check measures 127.0..128.2 after four calls).
Signs are kept; IX += 6.  Evidence: tools/check_routines.py maths/rotation-helpers."""),
    0xDCC6: (None, 'verified', """
Scale one high byte by B/128 (MultiplyUnsigned of B and twice the magnitude), keep its
sign; IX += 2."""),
    0xDCDE: ('RollRotationAngle', 'verified', """
Angle for rotation in the x-y plane (z is the view depth): first the player's L_7042,
then the object's own roll from +$1D ($0C, sign $80).
Read by RotateVectorRollPitch and RotateOrientationComponent."""),
    0xDCDF: ('PitchRotationAngle', 'verified', """
Angle for rotation in the y-z plane: the player's L_7043, then the object's +$1E ($08)."""),
    0xDCE0: ('MoveObject', 'verified', """
Move one object: IX = instance, IY = blueprint.
ApplyPlayerMotion; remove (energy 0, L_EB65) objects with nonzero x/y/z high
magnitude, or z mid byte >= $60 without +$26 bit 2.  Otherwise rotate the orientation
by the player's roll/pitch, then by the object's own +$1D/+$1E counters (bit 7 =
continuous, bit 6 = sign, low nibble = remaining steps), update the speed and move the
position along the vector at +9 (L_DD92).
On removal L_EB65 releases the references to the slot given by ObjectLoopCounter, so
callers outside the slot loop (L_77B0) depend on its current value.
A removed object skips the orientation step.  For the dormant station, which
UpdateStationDormancy moves while it is far away, the position therefore follows the
player's motion but the axes do not.
Evidence: tools/check_routines.py station/dormant-orientation-frozen."""),
    0xDCF3: (None, 'verified', """
Remove the object: energy +$22 = 0, then tail-jump to L_EB65."""),
    0xDD5D: (None, 'verified', """
Entry with PitchRotationAngle = A.
Rotate the orientation by the object's angles (RotateOrientationComponent x3).
Add +$1C (acceleration) to +$1B (speed), clamped to 0..blueprint +6 (x4 when +$21
bit 0), then move along the vector at +9 by the speed."""),
    0xDD92: (None, 'verified', """
Move: C = speed (+$1B); MoveCoordinateAlongNose for x, y and z (IY = instance).
Each coordinate changes by about Z-axis component * speed / 64 / 256 (rounded up).
IX and IY preserved."""),
    0xDDAB: ('MoveCoordinateAlongNose', 'verified', """
24-bit coordinate at IY += ScaleComponentBySpeed(word at IX+9, C) via AddToCoordinate;
IY += 3, IX += 2.  BC preserved."""),
    0xDDD6: ('ScaleComponentBySpeed', 'verified', """
DE = sign-magnitude word (bit 15 = sign), C = speed (bits 0..5 used).
E = (sum over speed bits k = 5..0 of (|DE| >> (6 - k)) + $FF) >> 8, i.e. about
|DE| * speed / 64 / 256 rounded up; D = sign bit only; B = 0.
Evidence: tools/check_routines.py maths/r8-motion-helpers (exact model)."""),
    0xDDF8: ('AddToCoordinate', 'verified', """
Add signed DE (bit 15 = sign) to a 24-bit coordinate.
A = sign/high byte, HL = low 16 bits of the magnitude.  If A equals D (same sign and a
zero high magnitude): HL += DE, without carry into the high byte.  Otherwise HL -= DE;
when that borrows, HL = DE - HL and the result takes D (sign of DE, high magnitude 0).
Returns B (sign/high byte) and HL; C = old D.  MoveObject removes objects with a
nonzero high magnitude first, so the comparison acts as a sign test there.
Evidence: tools/check_routines.py maths/r8-motion-helpers (exact model)."""),
    0xDE0B: ('RotateVectorRollPitch', 'verified', """
Rotate one orientation vector by the roll and pitch angles.
High bytes at IX+1/+3/+5 (x, y, z): z += y*(-pitch/2)/128, x += y*(-roll)/128,
y += x*roll/128, y += z*(pitch/2)/128 (AddScaledSignMagnitude, updated values used at
once); IX += 6, DE = 6.
NOTE: these are the shear steps of ApplyPlayerMotion at the same scale, but pitch/2 is
truncated.  At pitch 1 positions turn and the axes do not; an odd pitch turns the
axes like the next lower even one.
Evidence: tools/check_routines.py station/orientation-pitch-quantisation."""),
    0xDE5D: ('AddScaledSignMagnitude', 'verified', """
A = D + s*|B|*|C|/128 for sign-magnitude bytes, s = sign of (A XOR B), saturated at 127.
Evidence: tools/check_routines.py maths/rotation-helpers (within 1.25 of the model)."""),
    0xDE88: ('RotateOrientationComponent', 'verified', """
Rotate one component of the three orientation vectors (IX+$0A, +$10, +$16) by the
object's angles: pitch couples +$0A/+$10, roll couples +$10/+$16; IX += 2.
Applied to all three components this rotates the object about its own axes: pitch mixes
its Z (nose) and Y (roof) vectors, roll mixes its X (side) and Y vectors."""),
    0xDED1: ('ApplyPlayerMotion', 'verified', """
Rotate the 24-bit position at IX+0..8 by the player's pitch (L_7043, y-z) and roll
(L_7042, x-y) with AddScaledCoordinate, then move z by 2*(L_7044+1): positive z decreases,
negative z grows.  Returns HL = z sign/high and mid bytes.  Also used for L_7065/L_706E
(L_778F).  Crossing zero flips the sign; a negative magnitude overflowing $FFFF becomes
+$7FFF.. (sign cleared).
NOTE: each rotation is two shear steps in a fixed order (z, then y from the new z; x,
then y from the new x).  One step is close to a rotation, but a roll or pitch in one
direction is not undone by the same rate in the other.  Rolling alternately left and right
pushes positions away from the view axis at unchanged depth (planet 4.98 times further
after 20 cycles of 32 updates each way); one direction alone does not.
Evidence: tools/check_routines.py maths/r8-motion-helpers (z step, zero crossing,
overflow, returned HL), maths/roll-reversal-drift."""),
    0xDF46: ('AddScaledCoordinate', 'verified', """
Coordinate at IX+HL += coordinate at IX+DE * |C| / 256, sign = sign(C) XOR source sign
(24-bit sign-magnitude, approximate products).  IX/IY preserved.
Evidence: tools/check_routines.py maths/rotation-helpers."""),
    0xDFDD: ('RotateAndDrawTitleShip', 'verified', """
Title-screen ship update (callers L_71A2, L_71E5).
IX = slot 7, IY = its blueprint, roll $94 / pitch $8C: rotate and move (L_DD5D),
L_E791, renormalise two orientation vectors (Z and Y), then draw (L_E008).
Clobbers all registers."""),
}

COMMENTS = {
    # tape glue
    0xD400: 'key code after a failed load ($FF = none)',
    0xD403: 'key code $20 -> BREAK, otherwise TAPE LOADING ERROR',
    0xD40F: 'back to the access-menu loop',
    0xD416: 'restore ActiveCommanderRecord from the snapshot',
    0xD41F: 'tape block length: 104 bytes',
    0xD422: 'flag byte $FF: data block',
    0xD425: 'at most 10 characters',
    0xD427: 'message 8 "COMMANDER\'S NAME? "',
    0xD429: 'tail call: prompt, read and zero-terminate the name',
    0xD42E: 'LetterCaseMode 0: title case',
    0xD431: 'column 0, row $16',
    0xD437: 'clear the status text line (A = 0)',
    0xD43B: 'message A',
    0xD441: 'tail call: beep if sound is on',
    # view title and message line
    0xD44D: 'LetterCaseMode 0: title case',
    0xD453: 'flight views are 0..3',
    0xD455: 'flight view: title and message into the view buffer',
    0xD45A: 'SMC: CharacterBlendOpcode = NOP, characters overwrite',
    0xD45C: 'message line in overwrite mode',
    0xD462: 'SMC: restore XOR C ($A9)',
    0xD465: 'flight views: title into the view buffer',
    0xD468: 'SMC: screen base $40xx -> $C0xx, text into ViewBitmapBuffer',
    0xD46A: 'column 10, row 1',
    0xD473: 'tokens $60..$63: FRONT, REAR, LEFT, RIGHT',
    0xD47D: 'message line into the view buffer too',
    0xD483: 'SMC: restore screen base $40xx',
    0xD486: 'countdown digits; may start the jump',
    0xD489: 'condition colour and missile cell',
    0xD48F: 'A = remaining updates of the current message',
    0xD491: 'a message is being shown',
    0xD496: 'count idle updates',
    0xD497: 'odd: status warnings',
    0xD49B: '9 entries of (column+pending bit 7, token)',
    0xD4A0: 'bit 7 = pending',
    0xD4A4: 'next 2-byte entry',
    0xD4A8: 'nothing pending',
    0xD4A9: 'take this message',
    0xD4AB: 'C = text column',
    0xD4AD: 'B = token',
    0xD4AF: 'beep (if sound is on)',
    0xD4B3: 'show for 14 updates',
    0xD4C1: 'one update less; A still holds the old value',
    0xD4C2: 'old timer value < 4: leave the line empty',
    0xD4C8: 'only on the four flight views',
    0xD4CF: 'row 14',
    0xD4D7: '" DESTROYED": print the item first',
    0xD4DB: '" CR": print the bounty first',
    0xD4DF: 'the message token itself',
    0xD4E2: 'tail call: token and newline',
    0xD4E5: 'lost equipment item',
    0xD4E8: '"DOCKING COMPUTERS" is printed without the indent',
    0xD4EC: 'indent by three columns',
    0xD4F2: 'print the item name',
    0xD4F7: 'bounty in tenths of a credit',
    0xD4FA: 'carry: one decimal place',
    # warnings
    0xD4FB: 'print the bounty',
    0xD500: 'last energy bank',
    0xD503: 'below $9F: ENERGY LOW',
    0xD507: 'set within fuel-scoop range of the sun',
    0xD50D: 'docking computer active',
    0xD511: 'active: show "DOCKING COMPUTERS ON"',
    0xD518: 'not due yet: count down',
    0xD51A: 'next mission broadcast after 70 checks',
    0xD51D: 'mission-3 state 1?',
    0xD521: 'state 1: INVADED broadcast',
    0xD523: 'mission 1 active?',
    0xD528: 'set by ArmExpandingSun: broadcasts end',
    0xD52D: 'token $C2 "MAYDAY * CORIOLIS IN DANGER*", column 2',
    0xD534: 'token $0F "MAYDAY * <name> INVADED*", column 3',
    0xD539: 'token $7B "DOCKING COMPUTERS ON", column 5',
    0xD53E: 'fuel scoops fitted?',
    0xD543: 'tenths of a light year',
    0xD547: 'fuel + 1 tenth, capped at 70',
    0xD54A: 'token $A0 "FUEL SCOOPS ON ", column 8',
    0xD551: 'low energy switches the cloak off',
    0xD554: 'attribute colour 7',
    0xD55B: 'flight view only: view window attributes = L',
    0xD55E: 'token $64 "ENERGY LOW", column 10',
    0xD563: '9 message entries',
    0xD565: 'pending-message table',
    0xD568: 'clear the pending bit',
    0xD56F: 'no current flight message',
    # hyperspace keys
    0xD578: 'bits 4/5: H and G keys',
    0xD57B: 'B = requested key bits',
    0xD57D: 'consume both key bits',
    0xD582: 'jump-request latch: CheckDocking now returns at once',
    0xD585: 'countdown already running',
    0xD58A: 'zero while docked',
    0xD58E: 'docked: DOCKED message',
    0xD590: 'G (bit 5) pressed?',
    0xD592: 'H alone: normal hyperspace',
    0xD596: 'G without H: ignored',
    0xD597: 'galactic hyperdrive fitted?',
    0xD59B: 'none fitted: ignored',
    0xD59C: 'L_A80A = 2: galactic jump',
    0xD5A1: 'token $74 "GALACTIC HYPERSPACE", column 6',
    0xD5A6: 'select the system nearest the chart cursor',
    0xD5A9: 'distance to the target in tenths of a light year',
    0xD5AE: '25.6 light years or more: out of range',
    0xD5B2: 'distance 0 (current system): no jump, no message',
    0xD5B4: 'fuel',
    0xD5B8: 'not enough fuel: out of range',
    0xD5BA: 'L_A80A = 1: normal jump',
    0xD5BF: 'token $C0 "HYPERSPACE -- <name>", column 5',
    0xD5C2: '21 updates: countdown 10..1',
    0xD5C7: 'message stays for the whole countdown',
    0xD5CA: 'B = token, C = column',
    0xD5CD: 'tail call: beep',
    0xD5D6: 'clear the screen and draw the frame',
    0xD5D9: 'column 11, row 7',
    0xD5E1: 'LetterCaseMode 1: capitals',
    0xD5E9: 'beep',
    0xD5EC: 'pause',
    0xD5EF: 'drop the key state',
    0xD5F2: 'continue with the status screen',
    0xD5FC: 'reached zero: jump now',
    0xD5FE: 'B = old value',
    0xD5FF: 'two-digit field',
    0xD604: 'column 1, row 1',
    0xD60B: 'display 10..1',
    0xD60D: 'tail call: print without a decimal point',
    0xD613: 'jump type: 1 normal, 2 galactic',
    0xD618: 'not 2: normal jump',
    # galactic jump
    0xD61B: 'clear mission-3 state',
    0xD61E: 'mission 1 active?',
    0xD625: 'mission 1 ends with the forced galactic jump',
    0xD62B: 'galactic hyperdrive used up (A = 0)',
    0xD632: 'fuel price byte = old galaxy + 1',
    0xD635: 'eight galaxies',
    0xD63A: 'three galaxy seed words',
    0xD63D: 'seed word 0',
    0xD640: 'seed word 1',
    0xD643: 'seed word 2',
    0xD647: 'Clean after a galactic jump',
    0xD64A: 'target: system nearest the cursor in the new galaxy',
    # normal jump
    0xD64D: 'arrive there',
    0xD65A: 'mission 1 forces a galactic jump',
    0xD660: 'distance (low byte)',
    0xD668: 'C = remaining fuel',
    0xD669: 'fuel = fuel - distance',
    0xD66C: '70 = full tank',
    0xD66F: 'B = 70 - remaining fuel',
    0xD670: 'target economy',
    0xD675: 'fuel price byte = 2*economy + 70 - fuel',
    0xD67B: 'legal score halved by every normal jump',
    0xD680: 'forced mis-jump option bit',
    0xD684: 'random byte',
    0xD687: 'mis-jump when the byte is $F9',
    # mis-jump
    0xD689: 'normal arrival',
    0xD68B: '$FA, or the option byte + 1',
    0xD68C: 'nonzero: mis-jump state',
    0xD68F: 'x: average of current and target',
    0xD697: 'RRA keeps the carry: 9-bit average',
    0xD698: 'both become the midpoint',
    0xD69A: 'y: average of current and target',
    0xD6A7: 'no station',
    0xD6AA: 'no current system name',
    0xD6AD: 'no selected system name',
    0xD6B0: 'no new system, no missions or pirates',
    # arrival
    0xD6B4: 'leave the mis-jump state',
    0xD6B7: 'target seeds -> current seeds',
    0xD6C2: '8-byte name: selected -> current',
    0xD6CD: 'tech level',
    0xD6D3: 'government',
    0xD6D9: 'new market, fluctuation from L_7063',
    0xD6DC: 'sun and planet positions, 9 bytes each',
    0xD6E6: 'station dormant until the player is near it',
    0xD6EB: 'HL = seed s0',
    0xD6EE: 'DE = seed s1',
    0xD6F2: 'BC = seed s2',
    0xD6F6: 'sun x from s2 high byte',
    0xD6F7: 'keep sign bit and two magnitude bits, at least 1',
    0xD6FE: 'sun y from s2 low byte',
    0xD706: 'sun z from s1',
    0xD70A: 'magnitude 4..11',
    0xD70C: 'sign set (behind the player), odd: 5..11',
    0xD711: 'planet x from s0 low byte',
    0xD719: 'planet y from s1 low byte',
    0xD721: 'planet z from s0',
    0xD725: '3..10, positive (ahead)',
    0xD72A: 'keep s2 low byte (C) for the station offset',
    0xD72B: 'station position = planet position',
    0xD737: 'A = planet z high byte',
    0xD73A: 'HL = station z mid byte',
    0xD73D: 's2 bit 0 set: offset along z, else along x',
    0xD741: 'offset along x instead',
    0xD747: 'mid byte $80: $8000 of the offset',
    0xD749: 'B = high byte with sign',
    0xD74A: 'A = high magnitude',
    0xD74C: 's2 bit 1 set: away from the origin',
    0xD750: 'magnitude 1: the station crosses zero',
    0xD756: 'flip the sign',
    0xD75D: 'magnitude - 2: $18000 nearer the origin',
    0xD760: 'magnitude + 1: $18000 farther out',
    0xD761: 'put the sign back into bit 7',
    0xD767: 'station high byte on the offset axis',
    0xD769: 'clear the station orientation',
    0xD772: 'did the offset change the z mid byte?',
    0xD779: '$7F: unit vector component',
    0xD77B: 'Y axis = (0, 1, 0)',
    0xD77E: 'z offset',
    0xD780: 'x offset: X axis z and Z axis x components',
    0xD786: 'X = (0, 0, 1), Z = (1, 0, 0)',
    0xD78E: 'x high bytes compared raw (sign included): wrong for negative x',
    0xD791: 'station below: X axis z = -1',
    0xD793: 'otherwise Z axis x = -1',
    0xD799: 'z offset: X axis x and Z axis z components',
    0xD7A5: 'station and planet z high bytes',
    0xD7A6: 'station below: both +1',
    0xD7A8: 'otherwise both -1',
    0xD7AC: 'station +$26 bit 7 was set: mission-3 state 5',
    # arrival tail and missions
    0xD7B4: 'galactic x/y of the arrival position',
    0xD7C0: 'galaxy 0: no missions or pirates',
    0xD7C9: 'station +$26 bit 7 at arrival',
    0xD7CB: 'clear it',
    0xD7CF: 'mission-3 state',
    0xD7D4: 'state 0: nothing to step',
    0xD7D9: 'state 1 -> 2',
    0xD7DC: 'state 4?',
    0xD7E0: 'state 4 -> 3',
    0xD7E1: 'current seeds equal to the galaxy seeds?',
    0xD7E4: 'carry clear when all six are equal',
    0xD7E7: 'another system: keep the state',
    0xD7E9: 'state 4: station hostile (UpdateObjects)',
    0xD7EB: 'store the new mission-3 state',
    0xD7EE: 'jump counter (outside galaxy 0 only)',
    0xD7F5: 'mission flags',
    0xD7FA: 'bit 0 clear: mission 1 test',
    0xD7FD: 'bit 1 clear: mission 2 test',
    0xD800: 'bit 2 clear: mission 3 test',
    0xD805: 'government 0..7',
    0xD808: '7 - government',
    0xD80C: 'compare with the pseudo-random byte',
    0xD80F: 'station roll byte +$1D',
    0xD814: 'L_A80B = 1',
    0xD81A: 'front view',
    0xD81D: 'cabin temperature 0',
    0xD820: 'not within fuel-scoop range',
    0xD823: 'missile state',
    0xD826: 'end any mission Asp encounter',
    0xD829: 'release the jump-request latch',
    0xD82E: 'altitude bar full',
    0xD833: 'mission 1 at 32 jumps',
    0xD835: 'not yet: pirate test',
    0xD837: 'HL = mission flags',
    0xD838: 'mission 1 flag',
    0xD83C: 'mission 1 active: every jump becomes galactic',
    0xD83F: 'attribute colour 2',
    0xD841: 'view attributes red',
    0xD844: 'lose all fuel',
    0xD84A: 'mission 2 at 128 jumps',
    0xD84F: 'mission 2 flag',
    0xD854: 'mission 3 at 254 jumps',
    0xD859: 'mission 3 flag',
    0xD85B: 'mission-3 state 1: MAYDAY INVADED broadcasts',
    0xD866: 'no fuel: no message',
    0xD867: 'pending "FUEL LEAK*" message',
    0xD86C: 'fuel 0 (falls into SetFuelLevel)',
    0xD86D: '70 = 7.0 light years',
    0xD871: 'cap at 70',
    0xD877: 'B = 2*fuel',
    0xD87E: '2*fuel + 2*fuel/8',
    0xD87F: 'FU bar value: 70 -> 157',
    # crosshair
    0xD889: 'half arm length',
    0xD88F: 'left end x = centre - size/2',
    0xD892: 'left end at or beyond the left edge',
    0xD894: 'D = left end x',
    0xD89A: 'HL = byte holding the left end',
    0xD8A0: 'right end x = centre + size/2',
    0xD8A1: 'beyond the right edge',
    0xD8A3: 'E = pixels in the right end byte (0 counts as 8)',
    0xD8AD: 'C = size - E: pixels before the right end byte',
    0xD8AF: 'D = pixels in the left end byte (0 counts as 8)',
    0xD8BB: 'full bytes in between',
    0xD8BD: 'none: two adjacent partial bytes',
    0xD8C3: 'A = number of full bytes',
    0xD8C8: 'clipped at the left edge: start at x = 0',
    0xD8CD: 'HL = byte at x = 0',
    0xD8E3: 'right end in the first byte',
    0xD8EE: 'clipped at the right edge',
    0xD8F4: 'pixels from the left end to the right edge',
    0xD90F: 'masks for the two partial bytes',
    0xD915: 'first byte: rightmost D pixels',
    0xD91B: 'left-clipped arm within one byte',
    0xD91E: 'pixel x = 0 left untouched',
    0xD922: 'right-clipped arm within one byte',
    0xD925: 'pixel x = 255 left untouched',
    0xD92A: 'B = full bytes',
    0xD931: 'first byte: rightmost D pixels',
    0xD936: 'full byte: all eight pixels',
    0xD93C: 'last byte, then the vertical arm',
    0xD944: 'first byte without pixel x = 0',
    0xD967: 'last byte without pixel x = 255',
    0xD96A: 'then the vertical arm',
    0xD96E: 'shift a set bit in from the left',
    0xD976: 'shift a set bit in from the right',
    0xD981: 'L = column (x / 8)',
    0xD985: 'y bits 3..5 -> L bits 5..7',
    0xD98C: 'y bits 0..2 -> H bits 0..2',
    0xD98E: 'screen at $4000',
    0xD992: 'y bits 6..7 -> H bits 3..4 (screen third)',
    0xD99E: 'last byte: leftmost E pixels',
    0xD9A3: 'first byte: rightmost D pixels',
    0xD9A8: 'half arm length',
    0xD9B2: 'top end y = centre - size/2',
    0xD9B3: 'above row 0: clip',
    0xD9B6: 'above the top limit: clip',
    0xD9BC: 'HL = top end',
    0xD9C7: 'rows beyond the bottom limit',
    0xD9CC: 'none: the whole arm',
    0xD9CE: 'shorten by the overhang',
    0xD9D4: 'overhang above the top limit',
    0xD9D9: 'size - overhang',
    0xD9DE: 'start at the top limit row (C)',
    0xD9E4: 'single-pixel mask for x AND 7',
    0xD9EA: 'bit 7 set, shifted right x AND 7 times',
    0xD9F5: 'toggle one pixel per row',
    0xD9F7: 'next pixel row',
    0xD9FB: 'crossed a character cell boundary',
    0xDA02: 'next character row',
    0xDA05: 'carry: next screen third, H already right',
    0xDA07: 'back to the top pixel line of the cell',
    # object update loop
    0xDA1D: 'mission-3 state',
    0xDA20: 'mission-3 state 4?',
    0xDA27: 'station hostile (+$21 bit 2)',
    0xDA29: 'large sun on screen?',
    0xDA2D: '$B1 = OR C',
    0xDA2F: 'no large sun: OR C',
    0xDA31: '$A9 = XOR C',
    0xDA33: 'SMC: pixel-combine opcode in the line renderer',
    0xDA36: 'SMC: same opcode, second plot loop',
    0xDA39: 'SMC: same opcode, third plot loop',
    0xDA3C: 'SMC: same opcode, fourth plot loop',
    0xDA46: 'B = counter: zero once every 256 updates',
    0xDA47: 'no encounter while the station is present',
    0xDA4D: 'or in the mis-jump state',
    0xDA56: 'or with four or more ships',
    0xDA5C: 'A = 0: random encounter event',
    0xDA5F: 'clear the per-update totals and flags',
    0xDA75: 'C = ship count',
    0xDA76: 'slot 0; counting starts at slot 1',
    0xDA7D: 'six allocatable slots',
    0xDA85: 'free slot',
    0xDA87: '+$20 bit 6: counted',
    0xDA94: 'slot 0 again',
    0xDA98: 'all eight slots',
    0xDA9A: 'counter kept for the next slot',
    0xDA9B: 'B = counter (AI phase)',
    0xDAA3: 'energy 0: free slot',
    0xDAA9: 'not the station: LastNonStationObjectEnergy',
    0xDAB5: 'C = ObjectUpdateCounter (AI phase)',
    0xDAB6: 'not station or debris: TorusJumpInhibitFlag',
    0xDAC1: 'energy bomb pending?',
    0xDAC7: 'the station is not affected',
    0xDACD: 'NOTE: IY is still the previous slot\'s blueprint',
    0xDAD0: 'maximum speed 39: Thargoid',
    0xDAD4: 'start the explosion',
    0xDAD8: 'hostile?',
    0xDAE1: 'behaviour bits $20/$40',
    0xDAE5: 'raise the shared alert',
    0xDAEA: 'player missile in flight?',
    0xDAF0: 'or the shared alert raised?',
    0xDAF6: 'make this object hostile',
    0xDB01: 'IY = blueprint',
    0xDB06: 'state bits 5:4',
    0xDB08: '00: alive',
    0xDB0C: '01 or 11: exploding',
    0xDB13: 'pitch counter 0 (A = 0)',
    0xDB16: '$C0: continuous roll',
    0xDB1B: 'missile: no sound, no mission check',
    0xDB24: 'L_707D bit 2',
    0xDB26: 'mission Asp state',
    0xDB2A: 'state 0: just free the slot',
    0xDB2C: 'state 3?',
    0xDB30: 'states 1/2: only the marked Asp ends it',
    0xDB34: 'not the marked Asp',
    0xDB3B: 'blueprint size $1E: none in the reference',
    0xDB40: 'end the Asp encounter',
    0xDB44: 'free the slot',
    0xDB47: 'release missiles and the lock aimed at it',
    0xDB4A: 'blueprint bounty',
    0xDB50: 'credit it (zero: nothing)',
    0xDB53: 'blueprint word +$15/+$16, halved',
    0xDB5D: 'add to the combat score',
    0xDB63: 'trader/police behaviour bits',
    0xDB65: 'no legal consequence',
    0xDB6A: 'at least 64: Fugitive',
    0xDB73: 'AI phase of this slot',
    0xDB79: 'not counted: no AI',
    0xDB7F: 'not a missile',
    0xDB81: 'missile guidance every update',
    0xDB88: 'AI every fourth update',
    0xDB8B: 'move and rotate',
    0xDB8E: 'keep Y orthogonal to Z',
    0xDB93: 'orientation vectors at +9',
    0xDB98: 'Z axis',
    0xDB9B: 'Y axis',
    0xDB9E: 'X axis',
    0xDBA3: 'collision, scooping, docking contact',
    0xDBA6: 'draw, or record the screen position',
    0xDBA9: 'AI laser-fired flag consumed',
    0xDBB2: 'explosion state 01 -> 10',
    0xDBBE: 'A = counter of this slot',
    0xDBC5: 'more slots',
    0xDBC9: 'bomb applied to every slot',
    0xDBD0: 'ships present: keep the shared alert',
    0xDBD1: 'none: clear the shared alert',
    # vector maths
    0xDBD7: 'x^2 / 65536',
    0xDBDB: 'y^2 / 65536',
    0xDBDF: 'z^2 / 65536',
    0xDBE5: 'HL = sum of squares / 65536',
    0xDBE8: 'HL = 256*sqrt: the length',
    0xDBEB: 'DE = length',
    0xDBEE: 'each component * 32768 / length',
    0xDBF1: 'y component',
    0xDBF4: 'z component',
    0xDC00: 'B = high magnitude, C = low byte',
    0xDC04: 'IX accumulates the high word',
    0xDC08: 'HL = B*C',
    0xDC11: 'high word += 2*B*C >> 8',
    0xDC14: 'HL = low byte of 2*B*C, times 256',
    0xDC1D: 'high word += B^2',
    0xDC24: 'HL += C^2',
    0xDC27: 'carry into the high word',
    0xDC29: 'restore IX, high word to the stack',
    0xDC2B: 'HL = word^2 >> 16',
    0xDC38: 'HL = magnitude',
    0xDC3A: 'BC = magnitude * 65536 / DE (A = 0)',
    0xDC3F: 'halved',
    0xDC46: 'copy the sign',
    0xDC56: 'HL >= $1000: direct',
    0xDC59: 'HL < $100',
    0xDC5D: 'HL < $1000: scale by 16',
    0xDC63: 'result / 4',
    0xDC6C: 'HL < $100: scale by 256',
    0xDC73: 'result / 16',
    0xDC7C: 'keep N for the second and third steps',
    0xDC81: 'HL.A = N/2',
    0xDC82: 'initial square-root guess',
    0xDC85: 'first step: HL = 2*x1',
    0xDC89: 'second step',
    0xDC8C: 'N for the third step (falls through)',
    0xDC8F: 'x = HL/2 (17 bits with the carry)',
    0xDC91: 'DE = x, HL = N',
    0xDC96: 'HL.A = N/2',
    0xDC98: 'BC = N * 32768 / x',
    0xDC9D: 'halved',
    0xDC9F: 'A = 0 on return',
    0xDCA1: 'HL = x + 16384*N/x = 2 * next x',
    0xDCA5: 'H selects the square table high bytes',
    0xDCAA: '(2*|x|)^2 / 256',
    0xDCB6: '+ the y and z terms: |v|^2/64 (8-bit, wraps)',
    0xDCB9: 'signed sum / 4',
    0xDCBD: 'B = $80 - sum/4',
    0xDCC9: 'C = 2*magnitude, sign shifted out',
    0xDCCB: 'HL = B * 2*magnitude',
    0xDCD4: 'old sign into bit 7',
    0xDCD6: 'new high byte: magnitude * B / 128',
    # MoveObject
    0xDCE0: 'HL = z sign/high and mid bytes afterwards',
    0xDCE3: 'the station has no z distance limit',
    0xDCE9: 'z mid byte',
    0xDCEA: 'too far away',
    0xDCF1: 'z high magnitude zero?',
    0xDCF7: 'release references to this slot',
    0xDCFD: 'x high magnitude must be zero',
    0xDD04: 'y high magnitude must be zero',
    0xDD08: 'player roll and pitch',
    0xDD0B: 'roll and pitch angles of this pass',
    0xDD10: 'three orientation vectors',
    0xDD15: 'Z, Y and X axes',
    0xDD20: 'own roll counter +$1D',
    0xDD24: 'bit 7: keep rolling',
    0xDD28: 'remaining steps (low nibble)',
    0xDD2C: 'none: angle 0',
    0xDD2F: 'one step used',
    0xDD33: 'roll angle 12',
    0xDD35: 'bit 6: direction',
    0xDD3B: 'sign bit',
    0xDD3D: 'object roll angle for this pass',
    0xDD40: 'own pitch counter +$1E',
    0xDD44: 'bit 7: keep pitching',
    0xDD48: 'remaining steps (low nibble)',
    0xDD4C: 'none: angle 0',
    0xDD4F: 'one step used',
    0xDD53: 'pitch angle 8',
    0xDD55: 'bit 6: direction',
    0xDD5B: 'sign bit',
    0xDD62: 'rotate about the object\'s own axes',
    0xDD6D: 'acceleration',
    0xDD71: 'none: keep the speed',
    0xDD76: 'speed + acceleration',
    0xDD77: 'negative: stop',
    0xDD7E: 'blueprint maximum speed',
    0xDD87: 'x4 when +$21 bit 0',
    0xDD8C: 'cap at the maximum',
    0xDD8F: 'new speed',
    0xDD96: 'C = speed',
    0xDD9B: 'IY = instance coordinates',
    0xDD9D: 'x += nose x * speed',
    0xDDA0: 'y += nose y * speed',
    0xDDA3: 'z += nose z * speed',
    0xDDAF: 'DE = Z axis (nose) component',
    0xDDB2: 'E = step magnitude, D = sign',
    0xDDBB: 'A = sign/high byte, HL = low 16 bits',
    0xDDBE: 'add the signed step',
    0xDDC1: 'store the new coordinate',
    0xDDD6: 'sign into carry',
    0xDDDA: 'C << 2: speed bits 5..0 at the top',
    0xDDDC: 'D = magnitude high byte',
    0xDDE1: 'six speed bits',
    0xDDE5: 'DE = magnitude >> k',
    0xDDE7: 'next speed bit (bit 5 first)',
    0xDDEB: 'add the scaled magnitude',
    0xDDEE: 'round up',
    0xDDF2: 'E = high byte of the sum',
    0xDDF5: 'D = sign bit only',
    0xDDFA: 'zero only when A equals D',
    0xDDFB: 'D = step magnitude',
    0xDDFF: 'same sign: add (no carry into the high byte)',
    0xDE01: 'different: subtract',
    0xDE03: 'no borrow: keep the sign',
    0xDE07: 'crossed zero: HL = step - old',
    0xDE09: 'sign of the step',
    # rotations
    0xDE12: 'C = -pitch/2 (sign-magnitude)',
    0xDE1B: 'z += y * (-pitch/2) / 128',
    0xDE24: 'C = -roll',
    0xDE2D: 'x += y * (-roll) / 128',
    0xDE3D: 'y += x * roll / 128 (new x)',
    0xDE48: 'C = pitch/2',
    0xDE51: 'y += z * (pitch/2) / 128 (new z)',
    0xDE57: 'next vector',
    0xDE5E: 'bit 7: sign of the product',
    0xDE61: 'C = |angle|',
    0xDE64: 'A = |B|*|C|/128',
    0xDE67: 'B = D (value)',
    0xDE6A: 'product sign XOR value sign',
    0xDE72: 'A = 2*|value|',
    0xDE73: 'signs differ: subtract',
    0xDE75: 'same signs: add',
    0xDE79: 'saturate',
    0xDE7D: 'subtract',
    0xDE80: 'product larger: result takes its sign',
    0xDE86: 'sign into bit 7, magnitude halved back',
    0xDE8D: 'C = -pitch',
    0xDE94: 'Z += Y * (-pitch) / 128',
    0xDE9F: 'C = -roll',
    0xDEA6: 'X += Y * (-roll) / 128',
    0xDEB6: 'Y += X * roll / 128 (new X)',
    0xDEC6: 'Y += Z * pitch / 128 (new Z)',
    0xDECC: 'next component',
    0xDED4: 'C = -pitch',
    0xDEDA: 'source y (+3), destination z (+6)',
    0xDEDD: 'z += y * (-pitch) / 256',
    0xDEE5: 'C = 2*(-roll)',
    0xDEED: 'x += y * 2*(-roll) / 256',
    0xDEF3: 'C = 2*roll',
    0xDEFB: 'y += x * 2*roll / 256 (new x)',
    0xDF08: 'y += z * pitch / 256 (new z)',
    0xDF0B: 'player speed',
    0xDF10: 'B = 2*(speed + 1)',
    0xDF17: 'HL = z sign/high and mid, A = low',
    0xDF1A: 'negative z: magnitude grows',
    0xDF22: 'no carry: done',
    0xDF23: 'carry into the upper bytes',
    0xDF26: 'still within range',
    0xDF28: 'overflow: largest magnitude, sign cleared',
    0xDF2D: 'positive z: magnitude shrinks',
    0xDF31: 'no borrow: done',
    0xDF32: 'borrow from the upper bytes',
    0xDF35: 'still positive',
    0xDF37: 'crossed zero: sign set, upper magnitude 0',
    0xDF3A: 'low byte negated: distance past zero',
    0xDF4A: 'IY = IX (both restored at exit)',
    0xDF4C: 'IX = source coordinate',
    0xDF4F: 'IY = destination coordinate',
    0xDF5C: 'product sign = source sign XOR angle sign',
    0xDF61: 'magnitudes only',
    0xDF64: 'high byte * |C|',
    0xDF6B: 'mid byte * |C|',
    0xDF78: 'low byte * |C| (high part)',
    0xDF8C: 'destination coordinate',
    0xDFA1: 'signs differ: subtract',
    0xDFA8: 'same sign: add',
    0xDFAE: 'subtract',
    0xDFB9: 'no borrow: keep the sign',
    0xDFBE: 'crossed zero: flip the sign',
    0xDFC6: 'and negate the magnitude',
    0xDFCF: 'store the destination',
    0xDFE8: 'IY = its blueprint',
    0xDFEA: 'fixed title roll',
    0xDFEF: 'fixed title pitch',
    0xDFF1: 'own rotation, speed and move',
    0xDFF4: 'keep Y orthogonal to Z',
    0xDFF7: 'renormalise the Z and Y axes',
}

DATA = {
    0xD444: (0xD449, 'bytes', 1),
    0xD449: (0xD44B, 'words', 1),
    0xD44B: (0xD44C, 'bytes', 1),
    0xD573: (0xD574, 'bytes', 1),
    0xD883: (0xD886, 'bytes', 1),
    0xDA0B: (0xDA1D, 'bytes', 1),
    0xDCDE: (0xDCE0, 'bytes', 1),
}

CONSTANTS = {
    0xD52D: 'B = token $C2, C = column 2',
    0xD539: 'B = token $7B, C = column 5',
    0xD54A: 'B = token $A0, C = column 8',
    0xD5A1: 'B = token $74, C = column 6',
    0xD5BF: 'B = token $C0, C = column 5',
    0xD5D0: 'B = token $C1, C = column 6',
    0xDC82: 'initial Newton guess $8000, not an address',
    0xDF28: 'largest 15-bit magnitude, not an address',
    0xDF37: 'magnitude 0 with sign bit set, not an address',
}

FIELDS = {
}

OPERANDS = {
    0xD41F: 'ActiveCommanderRecordSize',                 # LD DE,$0068
    0xDA7A: 'InstanceSize',
    0xDBBF: 'InstanceSize',
    0xDFDD: 'ObjectSlot7',      # slot 7
}

TEXTCALLS = {
    0xD42C: 'message',
}

ASSERTS = {
    'r8-rotation-angles-adjacent': ('PitchRotationAngle-RollRotationAngle = 1',
                                    'LD (RollRotationAngle),HL at $DD0B stores both angles'),
}
