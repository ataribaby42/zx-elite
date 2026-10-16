"""Ship events, encounter AI/steering, keyboard/joystick input and the IM 2 handler ($F400..$FFA8).

Evidence: instruction semantics, verified blueprint IDs (docs/SHIPS.md), equipment
tokens, the 48K runtime traces, and the SkoolKit checks in tools/check_routines.py:
controls/update-flight-controls, maths/square-root-and-normalise, maths/rotation-helpers,
missions/special-encounter, input/scan-keyboard (every one of the 40 keys pressed alone
through ScanKeyboard, the four input devices, ghost-key suppression, CAPS+0) and, from
pass 2, ai/p11-apply-steering-vector, ai/p11-missile-guidance, ai/p11-encounter-selection
and ai/p11-ship-tactics-energy.
Existing verified names (SelectParentLaunchType..TryFireAiLaser) are kept unchanged.
"""

SECTIONS = {
    0xF402: ('Ship event handlers',
             'Targets of DispatchShipEvent: event 2 missile, 5..9 debris, canisters,\n'
             'escape capsule, splinters and the display ship.'),
    0xF61D: ('Random space encounters',
             'Event 0: asteroids, traders, single ships and groups, weighted by contraband in the\n'
             'hold and by the government of the system; the special Asp Mk II encounter.'),
    0xF733: ('Ship AI: tactics, missile guidance and steering',
             'Per-ship energy regeneration and launch decisions, missile guidance and the\n'
             'shared steering calculation that turns a vector into roll/pitch/speed commands.'),
    0xFB51: ('Keyboard and joystick input',
             'Called from the IM 2 handler every frame. Keys are latched as bits in eight\n'
             'state bytes (KeyFlagsScreens..JoystickNumberKeys) through KeyActionTable.'),
    0xFE01: ('Interrupt-driven flight controls and IM 2 handler',
             'Roll, pitch and speed accumulators are integrated from the latched direction\n'
             'and speed keys. InterruptEntry at the fixed address $FEFE splits this routine.'),
}

LABELS = {
    # ------------------------------------------------------------------ events
    0xF402: ('LaunchMissile', 'verified', """
Event 2: create a Missile (blueprint ID 1); C = high nibble of the event = target code.
C = 0 (AI launch, event $02 from TryLaunchAiPayload): a child of the parent IX through
CreateShipAtParent (position and orientation copied, not the speed), then speed +$1B +=
PlayerSpeed.  The LDIR in CreateShipAtParent leaves C = 0, so the target stays the player.
C <> 0 (player launch at $A760, event C*16+2): slot 7 (ObjectSlot7), or any free slot 1..6
when slot 7 is busy; L_F3B3 clears the position bytes, then y = -$29 and z = +$6A.
Both: instance +$25 = C, set +$26 bit 0 (missile flag).
Out: Z and IX = the missile on success; NZ if no slot was free."""),
    0xF44A: (None, 'verified', """
C = 0 or C > 5: return NZ without creating a ship.  Every C >= 2 calls NextRandomByte
before the subtype is tested (subtype 5 calls it twice); the Viper path never does."""),
    0xF48A: (None, 'verified', """
Toggle 1 (L_F4A2 three times): exchange the forward axis (InstanceAxisZ) and up axis
(InstanceAxisY) components and reverse the side axis (InstanceAxisX), a half turn.
Toggle 0 (L_F4BB): a quarter turn, new forward = -old up and new up = old forward.
Only the high bytes of the axis words are moved; the fraction bytes stay in place."""),
    0xF4A2: (None, 'verified', """
One component of the toggle-1 turn: exchange the high bytes +$0A (forward axis) and +$10
(up axis), invert the sign bit of +$16 (side axis), then IX += 2 for the next component.
Three calls cover +$0A/+$10/+$16, +$0C/+$12/+$18 and +$0E/+$14/+$1A."""),
    0xF4BB: (None, 'verified', """
Toggle-0 turn: for the component pairs (+$0A,+$10), (+$0C,+$12) and (+$0E,+$14) store
-second into first and first into second, i.e. forward := -up and up := forward."""),
    0xF4E6: (None, 'verified', """
Tilt the forward axis (InstanceAxisZ) by small random x and y components:
high bytes +$0A and +$0C = NextRandomByte AND $87 (random sign, magnitude 0..7 of 127),
giving a slightly randomised heading.
Input: IX = instance.  Clobbers A, flags; advances the RNG twice."""),
    0xF4F7: ('SpawnAlloyPlatePair', 'verified', """
Event 5: create two Alloy plates (blueprint ID 3).  C odd: both near the player through
SpawnObjectNearPlayer; C even: both at the parent IX through L_F5B8.
Callers: event $05 from the laser kill code at $ECC1 (blueprint energy >= 85) and event
$15 from ClearAllShipSlots at GAME OVER (debris around the player's own position).
Out: Z if both were created, NZ as soon as no slot is free."""),
    0xF4FF: (None, 'verified', """
A = 3 (Alloy plate), then SpawnObjectNearPlayer.  Called once and then fallen into, so
SpawnAlloyPlatePair creates two plates (the second only if the first succeeded)."""),
    0xF501: ('SpawnObjectNearPlayer', 'verified', """
Create blueprint A in a free slot (L_F3AD) at a random offset around the origin (the
player): random heading tilt (L_F4E6); x and y magnitudes 16..63, each with the sign
opposite to the heading tilt in that axis; z = +$19; random roll byte +$1D; speed +$1B =
8..39; clear +$20 bit 6 (not counted).  Out: Z on success, NZ if no slot was free."""),
    0xF54B: (None, 'verified', """
SpawnAlloyPlatePair with C even: two Alloy plates (ID 3) at the parent through L_F5B8."""),
    0xF555: ('SpawnCargoCanister', 'verified', """
Event 6: create a Cargo canister (blueprint ID 4).  C even: at the parent through L_F592
(an AI ship dumping cargo, L_F7D4; the laser kill code at $ECB6 when the blueprint canister
nibble is nonzero; L_EC8C for the marked Asp).  C odd: near the player through
SpawnObjectNearPlayer (event $16 from ClearAllShipSlots at GAME OVER)."""),
    0xF55D: ('HandleEscapeCapsuleEvent', 'verified', """
Event 7.  C even (event $07 from L_F7B6): an AI ship launches an Escape capsule
(blueprint ID 2) from its own position through L_F592.
C odd (event $17, sent only by the escape-pod launch at $A7C8): slot 6 is overwritten with
a Cobra Mk III (ID 9): L_F3B3 clears its position bytes, random heading tilt, y = -$1C,
z = +$4C, pitch byte +$1E = $C0, speed += PlayerSpeed, not counted.  Returns Z.
INFERRED: the Cobra shows the ship the player has just abandoned."""),
    0xF592: (None, 'verified', """
Create child blueprint A at parent IX (CreateShipAtParent), then on the child: clear
+$20 bit 6 (not counted), +$26 = $0A (bits 1 and 3: no laser fire, and the object does
not set L_DA0F in the object update), +$1D = $80.  IX is restored to the parent.
Out: Z on success, NZ if no slot.  Used for escape capsules and cargo canisters."""),
    0xF5B0: ('SpawnSplinterPair', 'verified', """
Event 8: create two Splinters (blueprint ID 5) at the parent through L_F5B8.
Evidence: caller $ECCF after a laser hit of damage 50 (the mining laser) destroys an
Asteroid (blueprint energy 60); AGENTS.md: there is no separate Boulder blueprint."""),
    0xF5B8: (None, 'verified', """
Create child blueprint A at parent IX, turn it with AdjustChildLaunchOrientation, set
+$26 = $0A (as L_F592), clear +$20 bit 6 (not counted) and set +$1D bit 7.  IX is restored
to the parent.  Out: Z on success, NZ if no slot."""),
    0xF5D8: ('SetUpDisplayShip', 'verified', """
Event 9: initialise instance slot 7 with blueprint ID C+2, not counted, x = y = 0 (the
random coordinates of InitialiseShipFromBlueprint are overwritten; only a random x/y sign
bit with zero magnitude remains), z = +$0200, speed 0, +$1D = +$1E = $C0, and copy the
nine orientation high bytes from ObjectSlot7OrientationBytes into +$0A,+$0C,..,+$1A.
Evidence: startup event $79 (ID 9, Cobra Mk III) at $718F; title loop at $71DC cycles
event 16*n+9.  INFERRED: this is the rotating title-screen ship."""),
    0xF61D: (None, 'verified', """
C = 2*(SLAVES + NARCOTICS) + FIREARMS (CargoHold+3, +6, +10, 8-bit sum):
contraband makes ship encounters more likely (L_F660).  The special Asp encounter needs
MissionAspEncounterState = 0, NextRandomByte <> $FF and CommanderFlags AND $42 = $02.
Evidence: tools/check_routines.py ai/p11-encounter-selection, missions/special-encounter."""),
    0xF655: (None, 'verified', """
Special-encounter continuation: the RET of InitialiseEncounterShip returns here
(address pushed at $F648).  Set +$26 bit 6 and +$20 bit 2 (payload count 1 -> 5) on the
new Asp Mk II, then add a group of 2..4 Sidewinders/Kraits at L_F70E.
+$26 bit 6 marks the ship that DrawObjectInView hides while MissionAspEncounterState = 1
(L_E0FA) and whose destruction sets state 3 and drops a canister (L_EC8C).
Evidence: missions/special-encounter (free slots): Asp $61CC with +$20=$C5, +$25=$7F,
+$26=$40, then two Sidewinders.  INFERRED: the cloaked Asp of mission 2 (docs/info notes)."""),
    0xF660: (None, 'verified', """
Ordinary encounter selection: r = NextRandomByte - C (C from SpawnRandomEncounter).
No borrow: r >= $5A -> nothing; r = $50..$59 -> an Asteroid (ID 6), not counted, +$1D = $C0;
r < $50 -> L_F684.  Borrow (random byte below C) -> L_F684 with the wrapped r."""),
    0xF684: (None, 'verified', """
B = r, E = r AND 7.  L_A871 = 4 -> one Thargoid (ID 15); L_A871 = 1 -> one Python trader
(ID 10).  Otherwise g = CurrentGovernment AND 7 (0 anarchy .. 7 corporate state): for
g <> 0, E becomes (r AND 7) + 1 and g >= E means no encounter; an anarchy always gets one.
Then r bit 3 set -> SpawnMixedSingleShipEncounter, else L_F6E2 with E.
Evidence: tools/check_routines.py ai/p11-encounter-selection."""),
    0xF6DB: (None, 'verified', """
Allocate a slot and create blueprint C (Thargoid or Python trader, from L_F684) through
the shared InitialiseEncounterShip path."""),
    0xF6E2: (None, 'verified', """
New random byte r2: (r2 AND 7) >= E -> group at L_F70E.  Otherwise allocate one slot and
choose from bits 7..5 of r2 (rotated into C bits 2..0): 0..1 -> L_F706, 2..7 ->
SelectEncounterTraderType (2..4 Cobra trader, 5..7 Python trader)."""),
    0xF706: (None, 'verified', """
Rock hermit (ID 7) or Viper (ID 8), chosen by bit 4 of r2 (bit 7 of the
rotated copy in C), then created through InitialiseEncounterShip."""),
    0xF70E: (None, 'verified', """
Create a group of 2 + ((r AND 3) >> 1) + (r AND 1) ships (2, 3, 3 or 4 for
r AND 3 = 0..3), each a Sidewinder (ID 16) or Krait (ID 17; Adder with ship=adder)
chosen by NextRandomByte bit 0.  Stops early (NZ) when no slot is free.  Also the tail
of the special encounter.
Evidence: tools/check_routines.py ai/p11-encounter-selection (all 256 group bytes)."""),
    0xF72B: ('SteeringVectorX', 'verified', """
Steering vector, x component: sign-magnitude word (bit 15 = sign) at a quarter of the
coordinate scale.  Written by SteerShipAwayFromPlayer (+position/4), SteerShipTowardsPlayer
(-position/4) and UpdateMissileGuidance ((target - missile)/4); NormaliseVector rescales
the three words in place to length $8000 for ApplySteeringVector."""),
    0xF72D: ('SteeringVectorY', 'verified', """
Steering vector, y component; same format as SteeringVectorX."""),
    0xF72F: ('SteeringVectorZ', 'verified', """
Steering vector, z component; same format as SteeringVectorX."""),
    0xF731: ('SteeringVectorLength', 'verified', """
Length of the steering vector before normalisation: DE returned by
NormaliseVector, stored by ApplySteeringVector.  Within about 3.5% for vectors well
above $100 (coarser for short ones).  Its high byte is the range R tested by
ApplySteeringVector ($02..$12) and TryFireAiLaser ($0C, $04); in coordinate units R
is about distance/1024.
Evidence: tools/check_routines.py ai/p11-apply-steering-vector (the stored word equals
NormaliseVector's result) and maths/square-root-and-normalise (accuracy)."""),
    # ------------------------------------------------------------------ AI
    0xF733: ('UpdateShipTactics', 'verified', """
Per-ship AI step (L_DB86 calls it every fourth update per ship; missiles use
UpdateMissileGuidance instead).  IX = instance, IY = blueprint.
1. Energy := min(blueprint energy +$07, energy + 1, or + 4 when the blueprint energy is
   >= $F0).  Nothing (not even the energy) is stored while CloakingDeviceActive is
   nonzero (the player's cloaking device is on).
2. MissionAspEncounterState 1 (marked Asp hidden) costs 2 energy per step, or switches to 2
   below energy $34; state 2 returns to 1 at energy >= $50.  Every ship's step applies this.
3. Energy >= 128 or >= half the blueprint energy: no launch.  Energy >= 32 or >= 1/8:
   TryLaunchAiPayload.  Below both: L_F7B6 (escape capsule or cargo canister).
4. Continue at L_F7DF (orphaned Thargon check) and L_F815 (ECM), then traffic/steering.
Evidence: tools/check_routines.py ai/p11-ship-tactics-energy (steps 1 and 2)."""),
    0xF780: (None, 'verified', """
Event = blueprint +$0A AND $F0 XOR 4: subtype n gives event n*16+4
(SelectParentLaunchType); a zero high nibble gives 6 XOR 4 = event 2, a missile with
target code 0 (the player)."""),
    0xF7B6: (None, 'verified', """
Low-energy branch: nothing unless NextRandomByte >= instance +$25 (a fleeing ship, bit 7
set, rarely passes).  With +$20 bit 7 (from blueprint +$12 bit 7) launch an escape capsule
(event 7, C = 0) and clear +$20 bits 7 and 6: the abandoned ship is no longer counted and
gets no further AI steps (L_DB71 needs bit 6); return without steering.  Otherwise, if the
blueprint canister byte +$00 is nonzero, dump a cargo canister (event 6, C = 0)."""),
    0xF7DF: (None, 'verified', """
Only for blueprint behaviour byte +$12 = 4 (the Thargon, ID 18): look for an active
instance in slots 1..6 with +$21 = $0C (Thargoid; also the $8C pirate blueprints).
Found: steer at once (no ECM step, no station traffic).  None found: clear +$20 bit 6 (not
counted, and L_DB71 skips its AI from now on), set +$26 bit 1 (no laser fire) and halve
the speed +$1B once: the Thargon drifts.  Every other ship continues at L_F815."""),
    0xF815: (None, 'verified', """
ECM decision for ships with instance +$25 bit 0: when the player missile slot is active
(PlayerMissileEnergy, slot 7, <> 0) and ECM is idle, set EcmTimer = $0A - except with
L_A871 = 4 and the ECM jammer (CommanderFlags bit 7).  The CP $A0 after NextRandomByte
at $F83F has no effect: no branch tests it before TryLaunchStationTraffic overwrites the
flags, so every such ship switches ECM on.  Then station traffic."""),
    0xF882: ('CheckShipProximity', 'verified', """
Return carry if |x| < DE, |y| < DE and |z| < DE + $0200 for instance IX (16-bit
magnitudes at +0/+1, +3/+4, +6/+7; the sign/high bytes +2/+5/+8 are ignored).  NC as
soon as one axis is outside.  Clobbers HL, D (+2), flags."""),
    0xF8B3: (None, 'verified', """
Steering choice: inside the $0200 box (or the $0A00 box while +$26 bit 5 avoidance is
set) -> SteerShipAwayFromPlayer, for calm ships too.  Otherwise calm ships (+$21 bit 2
clear) return with their old roll/pitch commands."""),
    0xF8C8: (None, 'verified', """
Hostile ship: with L_A871 <> 4 and a station in slot 0 (energy L_606A <> 0), +$21 bit 3
selects away (set) or towards (clear).  Otherwise L_F8E2."""),
    0xF8E2: (None, 'verified', """
(+$25 AND $7F) >= 8 -> SteerShipTowardsPlayer; else set +$25 bit 7 (fleeing, also makes
ApplySteeringVector request acceleration 2) and steer away.  The low bits start at $7E and
player laser hits lower them (ApplyPlayerLaserHit)."""),
    0xF928: ('UpdateMissileGuidance', 'verified', """
Missile AI (L_DB71 runs it every update for counted instances with +$26 bit 0).
IX = missile.  EcmTimer nonzero: clear +$20 bit 6, set +$20 bit 4 (explosion state 01,
after which the object update removes it) and return.
Target code +$25 = 0: SteerShipTowardsPlayer.  Otherwise IY = slot 8 - code and
SteeringVectorX/Y/Z = (target - missile)/4 (L_F9B2).
Every component below $20 in magnitude (L_F9AA) = hit: +$20 bit 4 on the missile and,
unless the target is a station (+$26 bit 2), on the target.  A station explodes only when
L_A871 = 4: L_A871 bit 3 is set, the byte below it ($A870, station stock of ALIEN ITEMS)
is cleared, AddCombatScore adds $FFFF and the station gets +$26 bit 7 (read at the next
arrival, L_D7C4) and +$20 bit 4.  No hit: steering.
Evidence: tools/check_routines.py ai/p11-missile-guidance."""),
    0xF9AA: (None, 'verified', """
Hit test of one sign-magnitude component HL: Z if its magnitude is below $20 (ADD HL,HL
drops the sign, then H and bits 7..6 of L must be clear), NZ otherwise.  Clobbers A, HL."""),
    0xF9B2: (None, 'verified', """
HL = (target - object)/4 for one axis: the low 16 magnitude bits of each 24-bit sign-
magnitude coordinate (target IY, object IX) are halved with the sign moved into bit 15,
then HalveDifferenceSignMagnitude halves their difference.  Coordinate bits 16..22 are
ignored.  IX and IY += 3.  Clobbers A, BC, DE."""),
    0xF9DB: (None, 'verified', """
As L_F9E2 with the sign inverted: HL = -coordinate/4, the vector towards the origin (the
player).  IX += 3."""),
    0xF9E2: (None, 'verified', """
HL = coordinate/4 as a sign-magnitude word: the low 16 magnitude bits (IX+0, IX+1)
shifted right twice, the sign (bit 7 of IX+2) moved into bit 15; magnitude bits 16..22
are ignored.  IX += 3.  Clobbers A, DE."""),
    0xF9FA: ('ApplySteeringVector', 'verified', """
Shared steering.  IX = ship, IY = blueprint (both kept).  NormaliseVector rescales
SteeringVectorX/Y/Z to length $8000; its length result goes to SteeringVectorLength.
ComputeNegatedDotProduct with the forward (InstanceAxisZ), up (InstanceAxisY) and side
(InstanceAxisX) axes gives H, L and D (about -127 * cosine; H bit 7 set = vector ahead).
Roll +$1D: m = |D|; m = 0 keeps the old byte; else rate min(15, (m + m/8 + bit 2 of m)/4),
direction bit 6 = sign(D) XOR sign(L), bit 7 clear.
Pitch +$1E, skipped when that roll rate is 4 or more: bit 6 = sign(L), rate 15 when the
vector is behind, else (103 - (|H|+80)/2)/8 (7 at a right angle, 0 straight ahead).
Acceleration +$1C: 2 and return while fleeing (+$25 bit 7).  Otherwise, R = range (high
byte of SteeringVectorLength): ahead: 0 below R = $0A ($02 for missiles, +$26 bit 0), else
1 (R >= $10) or 2, and every ahead case continues into TryFireAiLaser; behind (L_FAF9):
0 below $0B ($03), else -1 (R < $12) or -2.
Evidence: tools/check_routines.py ai/p11-apply-steering-vector."""),
    0xFAF9: (None, 'verified', """
Vector behind the ship (H bit 7 clear): range < $0B ($03 for missiles) keeps +$1C = 0;
otherwise +$1C = $FF (range < $12) or $FE."""),
    0xFB10: (None, 'verified', """
One product term for ComputeNegatedDotProduct: A, B sign-magnitude bytes.  H bit 7 =
NOT(sign A XOR sign B) (other H bits undefined), L = A = high byte of (2|A|)*(2|B|) from
MultiplyUnsignedHigh, about |A|*|B|/64."""),
    0xFB1F: ('ComputeNegatedDotProduct', 'verified', """
A = -(IX+1*IY+1 + IX+3*IY+3 + IX+5*IY+5)/128 as a sign-magnitude byte (inputs are the
sign-magnitude high bytes of three words; the magnitude saturates at $7F).
Evidence: tools/check_routines.py maths/rotation-helpers: $60.$60 -> $C8; -$60.$60 -> $48;
three $40.$40 terms -> $E0.
Callers: ApplySteeringVector and L_E791."""),
    # ------------------------------------------------------------------ input
    0xFB51: ('KeyCharacterTable', 'verified', """
40 character codes, indexed by key bit*8 + row, rows ordered $7FFE, $BFFE, $DFFE,
$EFFE, $F7FE, $FBFE, $FDFE, $FEFE.  $00 = CAPS SHIFT, $01 = SYMBOL SHIFT, $0D = ENTER.
RecordKeyPress stores the code of the pressed key in LastKeyCode.
Evidence: tools/check_routines.py input/scan-keyboard pressing each key alone."""),
    0xFB79: ('ScanKeyboard', 'verified', """
Interrupt-time input scan (called by InterruptHandler).  Clear JoystickNumberKeys, set
LastKeyCode = $FF, read the eight keyboard half-rows (BC = $7FFE rotated before each IN,
first port $FEFE) and call RecordKeyPress for each pressed key.  Then (L_FC16) merge the
selected joystick into the direction bits of KeyFlagsFlight.
Key bits are latched (ORed); consumers clear them (ClearInputFlags, ClearKeyFlags,
L_7158, L_FF1D).
Evidence: tools/check_routines.py input/scan-keyboard (all 40 keys, four input devices,
CAPS+0 and ghost-key suppression)."""),
    0xFB97: (None, 'verified', """
Jump over the input tables and state bytes at $FB9A..$FC15 to the scan continuation."""),
    0xFB9A: ('LaserTypeItemTable', 'verified', """
Laser type 1..4 -> equipment item 5 (EXTRA PULSE LASERS), 6 (EXTRA BEAM LASERS),
13 (MILITARY LASER), 14 (MINING LASER).  Read by the laser purchase code at $B6DE as
LaserTypeItemTable-1 + old laser type to refund the replaced laser; $B65A performs the
inverse map.  Item names: token $68 + item number."""),
    0xFB9E: ('StatusScreenAttributeLayout', 'verified', """
Attribute layout list for ColourAttributeStrips, commander status screen
(ShowCommanderStatus, screen $0B).
Each byte: bits 7..3 = number of cells set to colour $05 from the current row start
(the first row starts at $5821), bits 2..0 = rows to advance; 0 ends the list."""),
    0xFBA6: ('InventoryAttributeLayout', 'verified', """
Attribute layout list for ColourAttributeStrips, inventory screen (ShowInventory,
token "INVENTORY").
Format as StatusScreenAttributeLayout."""),
    0xFBA9: ('MessagePairTable', 'verified', """
Two-letter pairs for message codes $D7..$FF (PrintMessagePairToken reads
base + 2*(code-$D7)).  The 41 pairs run to $FBFA and overlap TokenPairTable from $FBC3.
Pair 0 '@@' (code $D7) is not used by any of the 256 messages."""),
    0xFBAB: ('RandomNamePairTable', 'verified', """
Pair 1 of MessagePairTable and the first of the 32 pairs (64 bytes, running on into
TokenPairTable) from which PrintRandomName prints 1..4 pairs at the even offsets
NextDescriptionRandom AND $3E; a '?' second letter is not printed.  L_B91F addresses it
as MessagePairTable+2.  Evidence: PrintRandomName, verified by simulation (r6_b000)."""),
    0xFBC3: ('TokenPairTable', 'verified', """
32 two-letter pairs for token codes $80..$9F (PrintPairToken); a second letter '?' is
not printed.  Also read by L_AD90 (pair index 1..31) and as message pairs $E4..$FF."""),
    0xFC03: ('SystemDataAttributeLayout', 'verified', """
Attribute layout list for ColourAttributeStrips used by the data-on-system screen
(DisplaySystemData, token "DATA ON").  Format as StatusScreenAttributeLayout."""),
    0xFC0B: ('MarketPricesAttributeLayout', 'verified', """
Attribute layout list for ColourAttributeStrips used by the market prices screen
(ShowMarketPrices, token "MARKET PRICES").  Format as StatusScreenAttributeLayout."""),
    0xFC0E: ('KeyFlagsScreens', 'verified', """
Latched key bits (state byte 0 of KeyActionTable): bit 0 ENTER, 1 L, 2 K, 3 P, 4 O, 5 I,
6 '0' (joystick fire, cleared again by the scan), 7 Y.
Bits 5..0 (I, O, P, K, L, ENTER) select screens 7..12 in HandleScreenKeys, highest bit
first: galactic chart, short-range chart, system data, market prices, commander status,
inventory.  Bit 7 (Y) is the ToggleCloak key.
L_AF56 clears KeyFlagsScreens..KeyFlagsCombat; L_8FB6 and L_7C09 clear five bytes."""),
    0xFC0F: ('KeyFlagsFlight', 'verified', """
Latched key bits (state byte 1): bit 0 N / left, 1 M / right, 2 X / down, 3 S / up,
4 SPACE, 5 SYMBOL SHIFT.  Bits 0..3 are replaced by the selected joystick each scan and
swapped by ControlOptions bits 4/5.  UpdateFlightControls consumes and clears the byte
on screens 0..3; when docked, bit 5 opens the access menu (L_72A2)."""),
    0xFC10: ('KeyFlagsViews', 'verified', """
Latched key bits (state byte 2): bit 0 '1', 1 '2', 2 '3', 3 '4', 4 H, 5 G, 6 J,
7 CAPS SHIFT.  Keys 1..4 (HandleScreenKeys): cockpit views in flight; launch, buy, sell
and equipment screens when docked.  H and G: CheckHyperspaceKeys (hyperspace, galactic
with H); J: HandleTorusJumpKey; CAPS SHIFT starts the pause menu at L_8F68."""),
    0xFC11: ('KeyFlagsCombat', 'verified', """
Latched key bits (state byte 3): bit 0 A or joystick fire, 1 T, 2 F, 3 U, 4 E, 5 W, 6 Q,
7 C.  Consumers: A laser (L_EBD8), T/F/U arm, fire and disarm a missile (L_A72E), E ECM
(L_ED90), W energy bomb (UseEnergyBomb), Q escape pod (L_A788), C docking computer
(L_70CF).  With the keyboard selected, bits 2 and 7 (and KeyFlagsViews bit 7) are cleared
while any KeyFlagsFlight bit is set (L_FC8F).  INFERRED: suppression of matrix ghost keys."""),
    0xFC12: ('KeyFlagsChart', 'verified', """
Latched key bits (state byte 4): bit 4 B, 5 D, 6 R; other bits unused.
L_713B reads bits 4..6 with the KeyFlagsFlight direction bits on screens 7..8."""),
    0xFC13: ('LastKeyCode', 'verified', """
Character code (KeyCharacterTable) of the last key found by the current scan; $FF = no
key, $FE = CAPS SHIFT + '0'.  Waited on by L_AF48 and the pause menu at L_8F78."""),
    0xFC14: ('ControlOptions', 'verified', """
Control options, initial $8C.  Bits 0..1 input device: 0 keyboard, 1 Kempston, 2 Cursor
(5..8, 0), 3 Sinclair (6..9, 0); chosen by holding left on the title screen (L_71E5).
Pause-menu keys toggle: bit 2 R (recentring), 3 D (damping), 4 B (reverse both),
5 Y (reverse vertical), 6 F, 7 sound (Q clears, S sets; tested before the ROM BEEPER).
Bit 6 forces the alternative hyperspace arrival at $D68B (INFERRED: mis-jump)."""),
    0xFC15: ('JoystickNumberKeys', 'verified', """
Current (not latched) number keys from state byte 7:
bit 0 '9', 1 '5', 2 '8', 3 '6', 4 '7'.  Cleared at each scan; converted to direction
bits for the Cursor and Sinclair joysticks."""),
    0xFC16: (None, 'verified', """
Scan continuation after the eight rows.  D = KeyFlagsFlight AND $0F (keyboard).
Kempston: IN port $1F; bit 4 fire -> KeyFlagsCombat bit 0; bits 0..3 -> D with both
swap flags inverted.  Cursor: D = JoystickNumberKeys >> 1 (5 left, 8 right, 6 down, 7 up).
Sinclair: bits reordered from 6 left, 7 right, 8 down, 9 up.  Cursor/Sinclair: '0'
(KeyFlagsScreens bit 6) is fire."""),
    0xFC69: (None, 'verified', """
Option swaps on D: ControlOptions bit 4 swaps bits 0<->1 and 2<->3, bit 5 swaps 2<->3."""),
    0xFC8F: (None, 'verified', """
Keyboard only: while any KeyFlagsFlight bit is set, clear KeyFlagsViews bit 7 and
KeyFlagsCombat bits 2 and 7.  Then store D in the low nibble of KeyFlagsFlight, clear
KeyFlagsScreens bit 6 and report CAPS+0 as LastKeyCode $FE."""),
    0xFCC0: ('RecordKeyPress', 'verified', """
Called for one pressed key: E = 5..1 (bit counter), D = 8..1 (row counter).
Index = (5-E)*8 + D-1; LastKeyCode = KeyCharacterTable[index]; then OR the mask from
KeyActionTable[index] into state byte KeyFlagsScreens + offset.  BC and AF preserved."""),
    0xFCED: (None, 'inferred', """
19 zero bytes before the vector table; no static or runtime reader or writer.
The research note proposes them as patch storage; they are kept as zeros.
stationslotfix=yes uses them for StationSlotFinish."""),
    # ------------------------------------------------------------------ IM 2
    0xFE01: ('UpdateFlightControls', 'verified', """
Called by InterruptHandler, on screens 0..3 only (CurrentScreenId < 4; otherwise the
latched KeyFlagsFlight bits are left for the screen code).  B = KeyFlagsFlight,
C = ControlOptions.
RollControl: N (bit 0) from 0 -> $80FF, then +$FF per frame up to $8FF0; M (bit 1)
likewise positive; both keys: unchanged.  Opposite key: 0 with recentring (C bit 2),
else -$FF (floor 0).  No key: -$3C per frame with damping (C bit 3).
PitchControl: X (bit 2) negative, S (bit 3) positive, step $66, damping $24.
SpeedControl: SPACE +$A0 (max $1FE0), SYMBOL SHIFT -$A0 (floor 0).
Finally clear KeyFlagsFlight.
Evidence: tools/check_routines.py controls/update-flight-controls frame sequences."""),
    0xFE7A: (None, 'verified', """
Store RollControl and update PitchControl from bits 2/3 (step $66, damping $24)."""),
    0xFEE8: (None, 'verified', """
Store PitchControl and update SpeedControl: SPACE (bit 4) +$A0 unless SYMBOL SHIFT too
(undone when bit 13 would be set), SYMBOL SHIFT (bit 5) -$A0 with floor 0."""),
    0xFF00: (None, 'verified', """
SPACE path of the speed update (UpdateFlightControls continues around InterruptEntry)."""),
    0xFF08: ('RollControl', 'verified', """
Roll accumulator, 16-bit sign-magnitude (bit 15 sign), maintained by
UpdateFlightControls from N/M (joystick left/right).  ReadFlightControls copies its
high byte (RollControl+1) to PlayerRoll each frame (and 21 +/- that value to
RollIndicator); ResetFlightInputs clears it.
Roll meaning: the manual lists N/M as anticlockwise/clockwise roll."""),
    0xFF0A: ('PitchControl', 'verified', """
Pitch accumulator, 16-bit sign-magnitude, maintained from X/S (joystick down/up).
ReadFlightControls copies its high byte to PlayerPitch."""),
    0xFF0C: ('SpeedControl', 'verified', """
Speed accumulator $0000..$1FE0 from SPACE / SYMBOL SHIFT.  ReadFlightControls
copies the high byte to PlayerSpeed; ResetFlightInputs sets the high byte to $0C, and
the escape-pod launch (L_A788) sets the word to $0010."""),
    0xFF0E: (None, 'verified', """
SYMBOL SHIFT path: the SBC borrow means the speed went below zero -> 0."""),
    0xFF1D: (None, 'verified', """
Store SpeedControl and clear KeyFlagsFlight (the latched flight keys are consumed)."""),
    0xFF25: ('InterruptHandler', 'verified', """
IM 2 service routine (InterruptEntry jumps here).  DI, save SP in InterruptSavedStack,
switch to the private stack below InterruptStackTop ($FFBF, above the game image),
push HL, DE, BC, AF, IX, IY, then ScanKeyboard, UpdateFlightControls and L_9082
(sound effect step, gated by ControlOptions bit 7).  Restore, EI, RET.
Alternate registers are not saved.  Runtime: stack use $FFAB..$FFBE only."""),
    0xFF53: ('UnusedSelectInterruptMode1', 'verified', """
Unused routine: IM 1, RET, the counterpart of EnableInterruptMode2 just before it.
No caller: no word $FF53 in the image, no relative jump to it, and the seven 48K access
traces neither execute nor read it.  The image contains no other IM 1, so the game
never returns to the ROM interrupt mode.  Called, it selects interrupt mode 1 and
returns with all registers and memory unchanged.  The comparison 48K memory images hold
the same bytes $FF4C..$FF55 (EnableInterruptMode2 and this routine), again without a
word $FF53; their start-up selects IM 2 with inline code instead of a CALL.
Evidence: tools/check_routines.py dormant/unused-interrupt-routines; execution, read and
write maps of tools/run_runtime_scenarios.py --accesses."""),
    0xFF56: ('InterruptSavedStack', 'verified', """
SP of the interrupted program, saved and restored by InterruptHandler."""),
    0xFF58: ('KeyActionTable', 'verified', """
40 two-byte entries in KeyCharacterTable order: state-byte offset from KeyFlagsScreens
(0..7) and the bit mask ORed in by RecordKeyPress.  Z and V have mask 0, and
so has W with iffunit=yes, which removes the energy bomb.
The table must not cross a page (L is incremented without carry).
Evidence: tools/check_routines.py input/scan-keyboard (every key); the POKE notes swap the
SYMBOL SHIFT and B entries."""),
    0xFF68: (None, 'verified', """
KeyActionTable entry 8, SYMBOL SHIFT: state offset $01 (KeyFlagsFlight).  The key-swap
POKE writes $04 here (KeyFlagsChart)."""),
    0xFF69: (None, 'verified', """
Mask of the SYMBOL SHIFT entry: $20 (bit 5).  The key-swap POKE writes $10 (B's bit 4).
LastKeyCode still reports the original key characters."""),
    0xFF98: (None, 'verified', """
KeyActionTable entry 32, B: state offset $04 (KeyFlagsChart).  The POKE writes $01."""),
    0xFF99: (None, 'verified', """
Mask of the B entry: $10 (bit 4).  The key-swap POKE writes $20 (SYMBOL SHIFT's bit 5)."""),
    0xFFA8: (None, 'inferred', """
Last image byte, zero, after KeyActionTable; no reader or writer in code or traces."""),
}

COMMENTS = {
    # LaunchMissile
    0xF404: 'C = 0: AI missile from the parent',
    0xF406: 'slot array base',
    0xF40A: 'offset of slot 7, the player missile slot',
    0xF40F: 'slot 7 energy: nonzero = occupied',
    0xF413: 'slot 7 free: use it',
    0xF415: 'slot 7 busy: any free slot 1..6',
    0xF419: 'blueprint 1: Missile',
    0xF41B: 'keep the target code',
    0xF41C: 'create it with zero position bytes',
    0xF420: 'z = +$6A: just ahead of the player',
    0xF425: 'y = -$29 (sign set below)',
    0xF42C: 'y sign: negative',
    0xF42F: 'A = target code',
    0xF432: 'blueprint 1: Missile',
    0xF434: 'copy the parent position/orientation; IX = missile, BC = 0',
    0xF437: 'NZ: no free slot',
    0xF438: 'add the player speed',
    0xF43B: 'to the blueprint cruising speed',
    0xF441: 'target code (0 = the player; C = 0 after the LDIR)',
    0xF444: 'instance +$26 bit 0: missile flag',
    0xF448: 'Z: success',
    # SelectParentLaunchType (original selector; the fix keeps the same structure)
    0xF44A: '$08: Viper',
    0xF44D: 'subtype 1: Viper, no RNG call',
    0xF44F: 'every subtype >= 2 advances the RNG here',
    0xF454: '$09/$0A: Cobra or Python trader',
    0xF457: 'subtype 2: trader',
    0xF459: '$12: Thargon',
    0xF45C: 'subtype 3',
    0xF45E: '$0F: Thargoid',
    0xF461: 'subtype 4',
    0xF464: 'C = 0 or > 5: nothing created (NZ)',
    0xF465: 'subtype 5: second RNG call',
    0xF46A: '$10: Sidewinder',
    0xF46C: 'random bit 0 clear: Sidewinder',
    0xF46E: '$11: Krait (Adder with ship=adder)',
    # LaunchSelectedShip
    0xF470: 'keep the parent',
    0xF472: 'child at the parent position/orientation',
    0xF475: 'IY = parent',
    0xF478: 'parent +$26 bit 2: a station',
    0xF47C: 'turn the child unless a station launched it',
    0xF47F: 'parent hostile?',
    0xF484: 'the child inherits the hostility bit',
    0xF488: 'Z: success',
    # AdjustChildLaunchOrientation
    0xF48D: 'toggle bit 0',
    0xF48F: 'store the new toggle value',
    0xF492: 'new value 0: quarter turn at L_F4BB',
    0xF496: 'x components: +$0A/+$10, +$16',
    0xF499: 'y components: +$0C/+$12, +$18',
    0xF49C: 'z components: +$0E/+$14, +$1A',
    0xF4A2: 'forward axis component',
    0xF4A5: 'up axis component',
    0xF4AE: 'side axis component: invert its sign',
    0xF4B6: 'next component word',
    0xF4BB: 'forward x := -up x',
    0xF4C6: 'up x := old forward x',
    0xF4C9: 'forward y := -up y',
    0xF4D4: 'up y := old forward y',
    0xF4D7: 'forward z := -up z',
    0xF4E2: 'up z := old forward z',
    # L_F4E6
    0xF4E6: 'forward axis x component',
    0xF4E9: 'random sign, magnitude 0..7',
    0xF4EE: 'forward axis y component',
    # SpawnAlloyPlatePair
    0xF4F7: 'C odd: near the player',
    0xF4F9: 'C even: at the parent',
    0xF4FB: 'first plate near the player',
    0xF4FE: 'no slot: stop (NZ)',
    0xF4FF: 'blueprint 3: Alloy plate',
    # SpawnObjectNearPlayer
    0xF501: 'allocate; position bytes cleared',
    0xF504: 'NZ: no free slot',
    0xF505: 'random heading tilt',
    0xF508: 'not counted by EncounterShipCount',
    0xF50C: 'x magnitude 16..63',
    0xF516: 'x sign opposite to the heading x sign',
    0xF520: 'y magnitude 16..63',
    0xF52A: 'y sign opposite to the heading y sign',
    0xF534: 'z = $19',
    0xF539: 'random roll byte',
    0xF53F: 'speed 8..39',
    0xF549: 'Z: success',
    0xF54B: 'blueprint 3: Alloy plate',
    0xF54D: 'first plate at the parent',
    0xF550: 'no slot: stop (NZ)',
    0xF553: 'second plate',
    # SpawnCargoCanister
    0xF557: 'blueprint 4: Cargo canister',
    0xF559: 'C even: at the parent',
    0xF55B: 'C odd: near the player',
    # HandleEscapeCapsuleEvent
    0xF55F: 'blueprint 2: Escape capsule',
    0xF561: 'C even: leaves the parent ship',
    0xF563: 'blueprint 9: Cobra Mk III',
    0xF565: 'slot 6, overwritten whatever it holds',
    0xF569: 'initialise there, position bytes cleared',
    0xF56C: 'random heading tilt',
    0xF56F: 'y sign: negative',
    0xF574: 'y = -$1C',
    0xF579: 'not counted',
    0xF57D: 'z = $4C',
    0xF582: 'pitch byte $C0',
    0xF587: 'add the player speed',
    0xF590: 'Z: done',
    # L_F592
    0xF592: 'keep the parent',
    0xF594: 'child at the parent position/orientation',
    0xF597: 'IX = parent, child on the stack',
    0xF599: 'HL = child',
    0xF59A: 'NZ: no free slot (IX = parent)',
    0xF59C: 'IX = child, parent on the stack',
    0xF59E: 'not counted',
    0xF5A2: '+$26 = $0A: bits 1 and 3',
    0xF5A7: 'roll byte $80',
    0xF5AC: 'Z: success',
    0xF5AD: 'restore the parent',
    # SpawnSplinterPair / L_F5B8
    0xF5B0: 'blueprint 5: Splinter',
    0xF5B2: 'first Splinter',
    0xF5B5: 'no slot: stop (NZ)',
    0xF5B8: 'keep the parent',
    0xF5BA: 'child at the parent position/orientation',
    0xF5C0: 'NZ: no free slot (IX = parent)',
    0xF5C4: 'turn the child',
    0xF5C7: '+$26 = $0A: bits 1 and 3',
    0xF5CC: 'not counted',
    0xF5D0: 'roll byte bit 7',
    0xF5D6: 'Z: success',
    # SetUpDisplayShip
    0xF5D8: 'slot 7',
    0xF5DD: 'blueprint ID = C+2',
    0xF5DF: 'random x/y are overwritten below',
    0xF5E2: 'roll and pitch bytes $C0',
    0xF5EB: 'z low byte',
    0xF5EE: 'x = 0',
    0xF5F4: 'y = 0',
    0xF5FA: 'z sign byte',
    0xF5FD: 'speed 0',
    0xF600: 'not counted',
    0xF606: 'z high byte = 2: z = +$0200',
    0xF60C: 'offset 9 (first axis word) and count 9',
    0xF60F: 'BC = 9 bytes',
    0xF612: 'DE = instance+$09, the low byte of the first word',
    0xF613: 'nine orientation high bytes',
    0xF616: 'DE skips each low byte',
    0xF619: 'until BC = 0',
    # SpawnRandomEncounter and the special encounter
    0xF61D: 'CargoHold+3: SLAVES',
    0xF621: 'CargoHold+6: NARCOTICS',
    0xF625: 'twice (slaves + narcotics)',
    0xF627: 'CargoHold+10: FIREARMS',
    0xF62B: 'C = 2*(slaves+narcotics)+firearms',
    0xF62C: 'special encounter running or done?',
    0xF630: 'yes: ordinary selection',
    0xF635: 'only $FF skips the special test',
    0xF637: 'random $FF: ordinary selection',
    0xF639: 'bit 1 set, bit 6 (cloaking device) clear',
    0xF640: 'otherwise ordinary selection',
    0xF643: 'MissionAspEncounterState = 1',
    0xF646: 'pushed A: ID 15 makes it set +$25 bit 0',
    0xF648: 'return address for InitialiseEncounterShip',
    0xF64D: 'slot for the Asp',
    0xF650: 'BUG: no free slot pops the pushed AF ($0F02) into PC (ROM)',
    0xF651: 'Asp Mk II',
    0xF653: 'create it; its RET goes to L_F655',
    0xF655: '+$26 bit 6 marks this ship',
    0xF659: 'payload count 1 -> 5',
    0xF65D: 'escort of 2..4 Sidewinders/Kraits',
    # L_F660
    0xF663: 'r = random - contraband sum',
    0xF664: 'random below C: ship encounter',
    0xF666: 'r >= $5A: no encounter',
    0xF66B: 'r < $50: ship encounter',
    0xF66D: 'r = $50..$59: an Asteroid',
    0xF671: 'Asteroid',
    0xF676: 'no effect: the template already sets this bit',
    0xF67A: 'not counted',
    0xF67E: 'roll byte $C0',
    # L_F684
    0xF684: 'B = r',
    0xF687: 'E = r AND 7',
    0xF688: 'special state (L_A871)',
    0xF68B: 'L_A871 = 4: Thargoid',
    0xF68E: 'C = 15: Thargoid',
    0xF693: 'L_A871 = 1: Python trader',
    0xF695: 'C = 10: Python trader',
    0xF699: 'government 0..7',
    0xF69E: 'anarchy: always an encounter',
    0xF6A0: 'E = (r AND 7) + 1',
    0xF6A2: 'government >= E: no encounter',
    0xF6A3: 'C = government (not read afterwards)',
    0xF6A4: 'r bit 3: one mixed ship',
    0xF6B0: '0..63',
    0xF6B2: '0: Thargoid (15)',
    0xF6B6: '1..11: Fer-de-Lance (14)',
    0xF6BB: '12..29: Asp Mk II (13)',
    0xF6C0: '30..45: pirate Cobra (12)',
    0xF6C5: '46..63: pirate Python (11)',
    0xF6C7: 'keep the blueprint ID',
    0xF6CC: 'Thargoid: always +$25 bit 0',
    0xF6D3: 'others: 51 of 256',
    0xF6D6: '+$25 bit 0: ECM fitted (L_F815)',
    0xF6DF: 'A = Thargoid or Python trader',
    # L_F6E2
    0xF6E5: 'B = r2',
    0xF6E8: 'compare with E',
    0xF6E9: '(r2 AND 7) >= E: a group',
    0xF6EB: 'rotate r2 left three times',
    0xF6F1: 'C bits 2..0 = r2 bits 7..5; bit 7 = r2 bit 4',
    0xF6F2: 'one slot',
    0xF6F7: 'r2 bits 7..5',
    0xF6FB: '0..1: Rock hermit or Viper',
    0xF702: '2..4: Cobra trader (9), 5..7: Python trader (10)',
    0xF707: 'r2 bit 4 to bit 0',
    0xF70A: '7 Rock hermit, 8 Viper',
    # L_F70E
    0xF713: 'A = (r AND 3) >> 1, carry = r bit 0',
    0xF714: 'count 2..4',
    0xF717: 'next slot',
    0xF71A: 'no slot: stop (NZ)',
    0xF71C: 'type bit for this ship',
    0xF721: 'Sidewinder (16) or Krait/Adder (17)',
    0xF727: 'next ship of the group',
    # UpdateShipTactics
    0xF733: 'blueprint maximum energy',
    0xF736: 'current energy',
    0xF739: '+1',
    0xF73A: 'large energy: regenerate 4 instead of 1',
    0xF73C: 'below $F0: +1 only',
    0xF73E: '+3 more',
    0xF742: 'above the maximum: cap it',
    0xF744: 'otherwise the incremented energy',
    0xF745: 'B = new energy',
    0xF746: 'player cloaked: no AI step at all',
    0xF74B: 'marked-Asp cloak state',
    0xF74F: 'energy >= $50?',
    0xF751: 'A = state (flags kept)',
    0xF752: 'below $50',
    0xF754: 'state 2 ...',
    0xF758: '... -> 1 (A still 2: no cost this step)',
    0xF759: 'state 1: Asp hidden',
    0xF75E: 'energy >= $34: pay for it',
    0xF762: 'too little energy: state 2 (visible)',
    0xF767: 'costs 2 energy',
    0xF76B: 'store the new energy',
    0xF76E: 'B = blueprint energy',
    0xF771: '2 * energy',
    0xF772: 'energy >= 128',
    0xF775: 'energy >= half maximum',
    0xF777: '4 * energy',
    0xF778: 'energy >= 64',
    0xF77A: '8 * energy',
    0xF77B: 'energy >= 32',
    0xF77E: 'energy < 1/8 maximum',
    # TryLaunchAiPayload
    0xF783: 'payload count',
    0xF785: 'none left',
    0xF78C: 'random >= $80: not this time',
    0xF78E: 'any ECM running?',
    0xF792: 'no launch during ECM',
    0xF794: 'blueprint +$0A high nibble: launch subtype',
    0xF79B: 'zero: 6, giving event 2 below',
    0xF79D: 'event n*16+4 (subtype n) or 2 (missile)',
    0xF79F: 'B = event',
    0xF7A1: 'dispatch with IX/IY kept',
    0xF7A5: 'nothing created: payload kept',
    0xF7A7: 'one payload item used',
    0xF7AB: 'event 2: a missile',
    0xF7AF: 'raise INCOMING MISSILE',
    # L_F7B6
    0xF7B9: 'instance +$25 as the threshold',
    0xF7BC: 'random below it: keep going',
    0xF7BE: '+$20 bit 7: escape capsule available',
    0xF7C2: 'no capsule: maybe dump cargo',
    0xF7C4: 'event 7, C=0: escape capsule from this ship',
    0xF7C9: 'no free slot',
    0xF7CB: 'capsule used',
    0xF7CF: 'abandoned: not counted, no more AI steps',
    0xF7D3: 'no steering',
    0xF7D4: 'blueprint canister byte',
    0xF7D8: 'nothing to dump',
    0xF7DA: 'event 6, C=0: canister from this ship',
    # L_F7DF
    0xF7DF: 'blueprint behaviour byte',
    0xF7E2: 'behaviour byte 4: Thargon',
    0xF7E4: 'other ships: ECM decision',
    0xF7E6: 'keep the Thargon',
    0xF7E8: 'slot base; the loop adds a slot first',
    0xF7EF: 'slots 1..6',
    0xF7F3: 'free slot?',
    0xF7F9: 'instance behaviour +$21',
    0xF7FC: 'behaviour $0C (Thargoid)',
    0xF7FE: 'found one',
    0xF802: 'none: A = 1, NZ',
    0xF805: 'Thargoid present: steer (no ECM step)',
    0xF808: 'not counted: no further AI steps',
    0xF80C: 'no laser fire (+$26 bits 0..3)',
    0xF810: 'halve the speed',
    # L_F815
    0xF815: 'instance +$25 bit 0: ECM fitted',
    0xF819: 'no ECM',
    0xF81B: 'special state 4?',
    0xF822: 'CommanderFlags bit 7: ECM jammer',
    0xF827: 'jammer in mode 4: no AI ECM',
    0xF82D: 'ECM already running',
    0xF82F: 'slot 7 energy: player missile in flight?',
    0xF834: 'no missile: no ECM',
    0xF836: 'station: skip the RNG call',
    0xF83C: 'RNG advanced, result ignored',
    0xF83F: 'result unused: no conditional branch follows',
    0xF841: 'switch ECM on',
    0xF843: 'EcmTimer = 10',
    # TryLaunchStationTraffic
    0xF846: 'station traffic flag',
    0xF84A: 'not a station: steering',
    0xF84C: 'counted ships',
    0xF851: 'four or more: no launch',
    0xF852: 'called with carry set',
    0xF855: 'station hostile?',
    0xF859: 'calm: trader gate',
    0xF85B: 'hostile: 36 of 256',
    0xF85E: 'special state',
    0xF863: 'event $14: parent launch subtype 1 (Viper)',
    0xF865: 'not state 4: a Viper',
    0xF867: 'state 4',
    0xF86A: 'random below $88',
    0xF86D: 'event $44: subtype 4 (Thargoid)',
    0xF871: 'only results 0 and 1',
    0xF874: 'event $24: subtype 2 (trader)',
    0xF87A: 'event A; C = its high nibble',
    # CheckShipProximity
    0xF882: '|x| (16-bit magnitude)',
    0xF88B: '|x| >= DE: outside',
    0xF88C: '|y|',
    0xF895: '|y| >= DE: outside',
    0xF896: '|z|',
    0xF89C: 'z limit DE + $0200',
    0xF89F: 'carry: inside the box',
    # UpdateShipHostilityAndSteering and the steering choice
    0xF8A2: 'legal-sensitive ship?',
    0xF8A8: 'player legal score',
    0xF8AB: '40 or more',
    0xF8AF: 'become hostile',
    0xF8B3: 'box half-size $0200',
    0xF8B6: 'x/y within $0200, z within $0400?',
    0xF8B9: 'too close: turn away',
    0xF8BB: 'avoidance flag from an earlier step',
    0xF8C1: '$0A00 while avoiding',
    0xF8C3: 'x/y within $0A00, z within $0C00?',
    0xF8C6: 'still close: keep turning away',
    0xF8CC: 'calm: old roll/pitch kept',
    0xF8CD: 'special state 4?',
    0xF8D2: 'state 4: courage test',
    0xF8D4: 'slot 0 (station) energy, instance +$22',
    0xF8D8: 'no station: courage test',
    0xF8DA: 'behaviour bit 3',
    0xF8DE: 'clear: attack',
    0xF8E0: 'set: keep away',
    0xF8E5: 'courage: lowered by player laser hits',
    0xF8E7: 'below 8: flee',
    0xF8E9: '8 or more: attack',
    0xF8EB: 'fleeing from now on',
    0xF8F1: 'x/4, sign kept',
    0xF8F7: 'y/4',
    0xF8FD: 'z/4',
    0xF905: 'avoidance flag',
    0xF90D: '-x/4',
    0xF913: '-y/4',
    0xF919: '-z/4',
    0xF921: 'avoidance ends',
    # UpdateMissileGuidance
    0xF928: 'any ECM active?',
    0xF92C: 'no: guide the missile',
    0xF92E: 'not counted',
    0xF932: 'explode (state 01)',
    0xF937: 'target code',
    0xF93B: '0: the player',
    0xF93D: 'keep the blueprint pointer',
    0xF93F: 'slot -1: the loop adds one slot per count',
    0xF946: 'code - 10',
    0xF948: 'A = 9 - code',
    0xF949: 'B = loop count',
    0xF94C: 'IY = slot 8 - code',
    0xF952: 'x: (target - missile)/4',
    0xF958: 'y: (target - missile)/4',
    0xF95E: 'z: (target - missile)/4',
    0xF964: 'IY = target, IX = missile',
    0xF968: 'z close?',
    0xF96B: 'no: steer',
    0xF970: 'y close?',
    0xF978: 'x close?',
    0xF97D: 'hit: target a station?',
    0xF981: 'no: destroy the target',
    0xF983: 'station: only in state 4',
    0xF989: 'otherwise only the missile explodes',
    0xF98B: 'L_A871 4 -> $0C',
    0xF98D: 'HL = $A870: station stock of ALIEN ITEMS',
    0xF98F: 'cleared',
    0xF990: 'combat score + $FFFF',
    0xF996: 'station destroyed marker (read at arrival)',
    0xF99A: 'target explodes (state 01)',
    0xF99E: 'restore the blueprint pointer',
    0xF9A0: 'missile explodes (state 01)',
    0xF9A7: 'steer towards the target',
    0xF9AA: 'drop the sign',
    0xF9AD: 'magnitude >= $80',
    0xF9AF: 'magnitude bits 6..5 (doubled)',
    0xF9B2: 'target low 16 bits',
    0xF9B8: 'target sign byte',
    0xF9BB: 'object low 16 bits',
    0xF9C1: 'object sign byte',
    0xF9C4: 'sign to carry',
    0xF9C6: 'target/2, sign in bit 15',
    0xF9CC: 'object/2, sign in bit 15',
    0xF9D0: 'HL = (target/2 - object/2)/2',
    0xF9D3: 'next coordinate',
    0xF9DE: 'invert the sign',
    0xF9E5: 'low 16 magnitude bits',
    0xF9EB: 'halve',
    0xF9EF: 'sign into carry',
    0xF9F0: 'halve again, sign into bit 15',
    0xF9F4: 'next coordinate',
    # ApplySteeringVector
    0xF9FA: 'keep the blueprint pointer',
    0xF9FC: 'IY = vector for the dot products',
    0xFA06: 'scale to length $8000; DE = length',
    0xFA0B: 'SteeringVectorLength',
    0xFA11: 'forward axis offset',
    0xFA14: 'IX = forward axis',
    0xFA16: 'H = -(forward . v)',
    0xFA19: 'up axis is the next axis',
    0xFA1C: 'IX = up axis',
    0xFA20: 'L = -(up . v)',
    0xFA26: 'side axis is the next axis',
    0xFA29: 'IX = side axis',
    0xFA2B: 'D = -(side . v)',
    0xFA34: 'm = |D|',
    0xFA36: 'zero: keep the old roll byte',
    0xFA39: 'C = m/8, carry = bit 2 of m',
    0xFA3F: 'm + m/8 + carry',
    0xFA40: '/4',
    0xFA44: 'cap at 15',
    0xFA4B: 'direction: sign(D) XOR sign(L)',
    0xFA4F: 'into bit 6',
    0xFA51: 'roll command',
    0xFA54: 'roll rate',
    0xFA56: '4 or more: keep the old pitch',
    0xFA5A: 'forward term',
    0xFA5D: 'behind: largest rate',
    0xFA5F: '|H|',
    0xFA61: '+80',
    0xFA63: '/2',
    0xFA66: '103 - (|H|+80)/2',
    0xFA68: '0..31',
    0xFA6A: 'never 64 or more',
    0xFA6E: 'behind: 63',
    0xFA70: 'sign of L to carry',
    0xFA72: 'sign to bit 7',
    0xFA73: 'sign to bit 6, rate/4',
    0xFA75: 'pitch command',
    0xFA79: 'fleeing?',
    0xFA7F: 'fleeing: accelerate',
    0xFA81: 'acceleration',
    0xFA84: 'fleeing: no laser',
    0xFA85: 'SteeringVectorLength',
    0xFA89: 'A = range (high byte)',
    0xFA8A: 'H bit 7 to carry: ahead?',
    0xFA8C: 'behind',
    0xFA8E: 'ships: $0A',
    0xFA90: 'missile: closer approach',
    0xFA96: 'missiles: $02',
    0xFA99: 'close: acceleration 0',
    0xFA9B: '1 at range $10 or more',
    0xFAA1: '2 below $10',
    0xFAA2: 'then the laser test as well',
    # TryFireAiLaser
    0xFAA5: 'hostile?',
    0xFAAA: 'z sign of the ship',
    0xFAAD: 'z sign of its forward axis',
    0xFAB2: 'equal: nose away from the player side',
    0xFAB3: 'blueprint +$02: firing chance',
    0xFAB6: 'combat score high byte',
    0xFABC: 'still zero: half the chance',
    0xFAC2: 'random >= chance: no shot',
    0xFAC3: '+$26 bits 0..3',
    0xFAC8: 'missiles, debris, orphaned Thargons: no laser',
    0xFAC9: 'range',
    0xFACC: 'range $0C or more: no shot',
    0xFACD: 'H bit 6: |H| >= 64',
    0xFACF: 'not aligned: no shot',
    0xFAD0: 'laser beam drawn (+$20 bit 3)',
    0xFAD5: 'range below 4: a hit',
    0xFAD9: 'H bit 5: |H| >= 96 needed',
    0xFADB: 'miss',
    0xFADC: 'a hit',
    0xFADF: 'sound request bit 6',
    0xFAE1: 'ship behind the player (z < 0)?',
    0xFAE7: 'rear shield damage',
    0xFAEA: '+7',
    0xFAF0: 'front shield damage',
    0xFAF3: '+7',
    0xFAF9: 'ships: $0B',
    0xFB01: 'missiles: $03',
    0xFB04: 'close: acceleration stays 0',
    0xFB05: '-1',
    0xFB0B: '-2 at range $12 or more',
    # L_FB10 and ComputeNegatedDotProduct
    0xFB11: 'sign A XOR sign B',
    0xFB12: 'negated product sign',
    0xFB14: '2|B|',
    0xFB16: '2|A|',
    0xFB18: 'save the sign',
    0xFB19: 'A = high byte of 2|A| * 2|B|',
    0xFB1C: 'H bit 7 = sign',
    0xFB1D: 'L = magnitude',
    0xFB1F: 'high bytes of the first words',
    0xFB25: 'term 1',
    0xFB2F: 'term 2',
    0xFB39: 'term 3',
    0xFB3C: 'DE = term 2',
    0xFB3D: 'term 3 + term 2',
    0xFB42: 'saturate',
    0xFB44: 'DE = term 1',
    0xFB46: '+ term 1',
    0xFB4B: 'saturate',
    0xFB4D: 'sign to carry',
    0xFB4F: 'A = sign | sum/2',
    # input
    0xFB51: 'bit 0: SPACE ENTER P 0 1 Q A CAPS',
    0xFB59: 'bit 1: SYM L O 9 2 W S Z',
    0xFB61: 'bit 2: M K I 8 3 E D X',
    0xFB69: 'bit 3: N J U 7 4 R F C',
    0xFB71: 'bit 4: B H Y 6 5 T G V',
    0xFB7A: 'JoystickNumberKeys = 0',
    0xFB7E: 'LastKeyCode = $FF (no key)',
    0xFB81: 'port $7FFE; RLC B gives $FEFE first',
    0xFB84: 'eight half-rows',
    0xFB86: 'next half-row port',
    0xFB88: 'read the row (0 = pressed)',
    0xFB8C: 'pressed keys as 1 bits',
    0xFB8E: 'five keys',
    0xFB90: 'next key bit to carry',
    0xFB91: 'pressed: record it',
    0xFB97: 'skip the tables and state bytes',
    0xFB9A: 'pulse, beam, military, mining',
    0xFBA9: 'code $D7 (unused)',
    0xFC16: 'next half-row',
    0xFC1A: 'keyboard direction bits',
    0xFC1F: 'D = directions',
    0xFC23: 'E = options',
    0xFC24: 'input device',
    0xFC26: 'keyboard',
    0xFC29: 'Cursor or Sinclair',
    0xFC2B: 'Kempston port $1F',
    0xFC2E: '1 bits = active',
    0xFC30: 'Kempston fire',
    0xFC34: 'fire -> KeyFlagsCombat bit 0 (laser)',
    0xFC39: 'right, left, down, up bits',
    0xFC3D: 'invert both swap flags for Kempston bit order',
    0xFC44: "number keys '9' '5' '8' '6' '7' (bits 0..4)",
    0xFC47: "bits 0..3 = '5' '8' '6' '7'",
    0xFC49: 'device 2: Cursor (5 6 7 8)',
    0xFC4B: 'device 3: Sinclair (6 7 8 9)',
    0xFC4D: "rebuild D: '6' left, '7' right, '8' down, '9' up",
    0xFC60: "'0' = fire",
    0xFC64: 'fire -> KeyFlagsCombat bit 0 (laser)',
    0xFC69: 'reverse both?',
    0xFC6E: 'left and down bits ...',
    0xFC74: '... exchanged with right and up',
    0xFC7A: 'reverse vertical?',
    0xFC7F: 'keep left/right',
    0xFC83: 'down/up ...',
    0xFC8B: '... exchanged',
    0xFC92: 'input device',
    0xFC97: 'keyboard only',
    0xFC99: 'any flight key latched?',
    0xFC9D: 'KeyFlagsViews',
    0xFC9E: 'drop CAPS SHIFT (pause)',
    0xFCA0: 'KeyFlagsCombat',
    0xFCA1: 'F (fire missile)',
    0xFCA3: 'C (docking computer)',
    0xFCA5: 'back to KeyFlagsFlight',
    0xFCA8: 'keep SPACE/SYMBOL SHIFT bits',
    0xFCAA: 'new direction bits',
    0xFCAF: "'0' pressed?",
    0xFCB2: "consume '0'",
    0xFCB4: 'with CAPS SHIFT?',
    0xFCBA: 'CAPS SHIFT + 0',
    0xFCBC: 'LastKeyCode = $FE',
    0xFCC4: 'key bit 0..4',
    0xFCC9: 'index = bit*8 + row',
    0xFCCB: 'B = 2*index',
    0xFCCD: 'character code',
    0xFCD6: 'LastKeyCode = character',
    0xFCD9: 'action entry: offset, mask',
    0xFCDD: 'entry 2*index (same page)',
    0xFCDF: 'A = state byte offset',
    0xFCE1: 'B = mask',
    0xFCE5: 'state byte (same page)',
    0xFCE8: 'latch the key bit',
    # flight controls
    0xFE04: 'cockpit views only',
    0xFE0A: 'B = flight keys',
    0xFE0E: 'C = options',
    0xFE0F: 'roll accumulator',
    0xFE12: 'N (left)?',
    0xFE16: 'M (right)?',
    0xFE1A: 'no key: damping option?',
    0xFE1C: 'off: keep the roll',
    0xFE1E: 'roll damping step',
    0xFE24: 'magnitude below zero?',
    0xFE28: 'stop at 0',
    0xFE2E: 'roll zero?',
    0xFE34: 'first M step',
    0xFE3A: 'negative roll?',
    0xFE3C: 'positive: grow',
    0xFE3E: 'negative: reduce (opposite key)',
    0xFE41: 'with M too?',
    0xFE43: 'N and M: no change',
    0xFE4B: 'first N step: sign-magnitude -$FF',
    0xFE53: 'positive roll: reduce (opposite key)',
    0xFE55: 'roll step',
    0xFE59: 'magnitude would reach $1000: undo',
    0xFE63: 'recentring option?',
    0xFE67: 'recentring: cancel at once',
    0xFE6D: 'otherwise reduce by $FF',
    0xFE73: 'magnitude below zero?',
    0xFE77: 'stop at 0',
    0xFE7D: 'pitch accumulator',
    0xFE80: 'X (down)?',
    0xFE84: 'S (up)?',
    0xFE88: 'no key: damping option?',
    0xFE8C: 'pitch damping step',
    0xFE96: 'stop at 0',
    0xFE9C: 'pitch zero?',
    0xFEA2: 'first S step',
    0xFEAF: 'with S too?',
    0xFEB1: 'X and S: no change',
    0xFEB9: 'first X step: sign-magnitude -$66',
    0xFEC3: 'pitch step',
    0xFEC7: 'magnitude would reach $1000: undo',
    0xFED1: 'recentring option?',
    0xFED5: 'recentring: cancel at once',
    0xFEDB: 'otherwise reduce by $66',
    0xFEE5: 'stop at 0',
    0xFEEB: 'speed accumulator',
    0xFEEE: 'speed step',
    0xFEF1: 'SPACE: faster',
    0xFEF5: 'SYMBOL SHIFT: slower',
    0xFEFA: 'reduce',
    0xFF02: 'both keys: no change',
    0xFF04: 'increase',
    0xFF0E: 'no borrow: store',
    0xFF10: 'below zero: 0',
    0xFF16: 'speed would reach $2000: undo',
    0xFF21: 'consume the flight keys',
    0xFF25: 'no nested interrupts',
    0xFF26: 'save the interrupted SP',
    0xFF2A: 'private interrupt stack above the image',
    0xFF35: 'keys and joystick',
    0xFF38: 'roll, pitch and speed',
    0xFF3B: 'sound effect step',
    0xFF46: 'back to the interrupted stack',
    0xFF4E: 'I = vector table page',
    0xFF58: 'SPACE        -> KeyFlagsFlight bit 4',
    0xFF5A: 'ENTER        -> KeyFlagsScreens bit 0',
    0xFF5C: 'P            -> KeyFlagsScreens bit 3',
    0xFF5E: "'0'          -> KeyFlagsScreens bit 6 (fire)",
    0xFF60: "'1'          -> KeyFlagsViews bit 0",
    0xFF62: 'Q            -> KeyFlagsCombat bit 6',
    0xFF64: 'A            -> KeyFlagsCombat bit 0',
    0xFF66: 'CAPS SHIFT   -> KeyFlagsViews bit 7',
    0xFF68: 'SYMBOL SHIFT -> state offset 1 (KeyFlagsFlight)',
    0xFF69: 'mask: bit 5',
    0xFF6A: 'L            -> KeyFlagsScreens bit 1',
    0xFF6C: 'O            -> KeyFlagsScreens bit 4',
    0xFF6E: "'9'          -> JoystickNumberKeys bit 0",
    0xFF70: "'2'          -> KeyFlagsViews bit 1",
    0xFF72: 'W            -> KeyFlagsCombat bit 5',
    0xFF74: 'S            -> KeyFlagsFlight bit 3',
    0xFF76: 'Z            -> no action bit',
    0xFF78: 'M            -> KeyFlagsFlight bit 1',
    0xFF7A: 'K            -> KeyFlagsScreens bit 2',
    0xFF7C: 'I            -> KeyFlagsScreens bit 5',
    0xFF7E: "'8'          -> JoystickNumberKeys bit 2",
    0xFF80: "'3'          -> KeyFlagsViews bit 2",
    0xFF82: 'E            -> KeyFlagsCombat bit 4',
    0xFF84: 'D            -> KeyFlagsChart bit 5',
    0xFF86: 'X            -> KeyFlagsFlight bit 2',
    0xFF88: 'N            -> KeyFlagsFlight bit 0',
    0xFF8A: 'J            -> KeyFlagsViews bit 6',
    0xFF8C: 'U            -> KeyFlagsCombat bit 3',
    0xFF8E: "'7'          -> JoystickNumberKeys bit 4",
    0xFF90: "'4'          -> KeyFlagsViews bit 3",
    0xFF92: 'R            -> KeyFlagsChart bit 6',
    0xFF94: 'F            -> KeyFlagsCombat bit 2',
    0xFF96: 'C            -> KeyFlagsCombat bit 7',
    0xFF98: 'B            -> state offset 4 (KeyFlagsChart)',
    0xFF99: 'mask: bit 4',
    0xFF9A: 'H            -> KeyFlagsViews bit 4',
    0xFF9C: 'Y            -> KeyFlagsScreens bit 7',
    0xFF9E: "'6'          -> JoystickNumberKeys bit 3",
    0xFFA0: "'5'          -> JoystickNumberKeys bit 1",
    0xFFA2: 'T            -> KeyFlagsCombat bit 1',
    0xFFA4: 'G            -> KeyFlagsViews bit 5',
    0xFFA6: 'V            -> no action bit',
}

DATA = {
    0xF72B: (0xF733, 'words', 1),
    0xFB51: (0xFB79, 'text', 8),
    0xFB9A: (0xFB9E, 'bytes', 4),
    0xFB9E: (0xFBA6, 'bytes', 8),
    0xFBA6: (0xFBA9, 'bytes', 3),
    0xFBA9: (0xFBC3, 'text', 8),
    0xFBC3: (0xFC03, 'text', 16),
    0xFC03: (0xFC0B, 'bytes', 8),
    0xFC0B: (0xFC0E, 'bytes', 3),
    0xFC0E: (0xFC16, 'bytes', 1),
    0xFCED: (0xFD00, 'zeros', 19),
    0xFF08: (0xFF0E, 'bytes', 2),
    0xFF56: (0xFF58, 'words', 1),
    0xFF58: (0xFFA8, 'bytes', 2),
    0xFFA8: (0xFFA9, 'zeros', 1),
}

SEEDS = {
    0xF655: 'return address pushed at $F648 and reached by the RET of InitialiseEncounterShip; '
            'executed in the R11 special-encounter test',
    0xFF53: 'complete unreferenced routine IM 1, RET after the RET of EnableInterruptMode2; '
            'simulated by tools/check_routines.py dormant/unused-interrupt-routines',
}

CONSTANTS = {
    0xFB81: 'keyboard half-row port $7FFE (B rotated before each IN), not an address',
    0xFC2B: 'Kempston joystick port $1F with B = $FF, not an address',
    0xFE4B: 'sign-magnitude roll value -$00FF, not an address',
    0xFEB9: 'sign-magnitude pitch value -$0066, not an address',
}

OPERANDS = {
    0xF40A: '7*InstanceSize',                 # LD DE,$0111: offset of slot 7
    0xF565: 'ObjectSlot6',                    # LD IX,$6132: instance slot 6
    0xF5D8: 'ObjectSlot7',                    # LD IX,$6159: instance slot 7
    0xF7EC: 'InstanceSize',                   # LD DE,$0027
    0xF93F: 'InitialRuntimeState-InstanceSize',  # LD IY,$6021: slot -1, loop adds slots
    0xF943: 'InstanceSize',                   # LD DE,$0027
    0xF8D4: 'InitialRuntimeState+InstanceEnergy',        # LD A,($606A): station slot 0 energy
    0xFA11: 'InstanceAxisZ',                  # LD DE,$0009: forward axis
    0xFA19: 'InstanceAxisY-InstanceAxisZ',    # LD DE,$0006: forward -> up axis
    0xFA26: 'InstanceAxisX-InstanceAxisY',    # LD DE,$0006: up -> side axis
    0xFF2A: 'InterruptStackTop',              # LD SP,$FFBF
}

FIELDS = {
    'InterruptStackTop': (0xFFBF, 'interrupt handler stack top above the game image; uses $FFAB..$FFBE'),
}

ASSERTS = {
    'r11-key-action-page': (
        '((KeyActionTable-GameImage+GameLoadAddress) & $FF) + 80 <= 256',
        'RecordKeyPress adds the entry offset to L without carry'),
    'r11-key-state-page': (
        '((KeyFlagsScreens-GameImage+GameLoadAddress) & $FF) + 8 <= 256',
        'RecordKeyPress and L_FC8F address the state bytes by changing L only'),
    'r11-stack-above-image': (
        'InterruptStackTop - 20 >= GameImageEnd-GameImage+GameLoadAddress',
        'observed interrupt stack use ($FFAB..$FFBE) must stay above the game image'),
}
