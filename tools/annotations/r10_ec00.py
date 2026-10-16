"""Laser hits/beams, RNG, sights/ECM update, clipped line renderer, ship creation ($EC00..$F3FF).

Evidence: instruction semantics; runtime traces in docs/generated/runtime-xrefs.json; SkoolKit
48K simulator tests of the reference image (tools/check_routines.py maths/line-helpers,
lines/line-delta-and-start, lines/draw-line, lines/sights-and-laser-lines,
combat/r10-laser-hit-outcomes, combat/r10-sights-and-ecm, objects/r10-ship-creation): DrawLine
pixels for 1500 inside lines equal a DDA model, 1500 clipped lines stay within 3 px of the
ideal segment and inside ViewBitmapBuffer, and the helpers $F0BE/$F0CC/$F0D6/$F175 match
Python models.  Ship-event outcomes follow the verified DispatchShipEvent and docs/SHIPS.md.
"""

SECTIONS = {
    0xEC55: ('Player laser hits, beam drawing, RNG and sights', """
Laser damage and debris events, the four-line beam (DrawLaser), the shared random number
generator and the per-frame sights/laser/ECM update."""),
    0xEDBC: ('Clipped line renderer', """
DrawLine draws into ViewBitmapBuffer (256x128). Endpoints are magnitudes about the view
centre (127,63) plus quadrant bits; region tables and slope comparisons clip lines to the
view, then one of four self-modified plotting loops steps along the major axis."""),
    0xF2A1: ('Ship instance template, event dispatch and slot allocation', """
Default instance bytes, DispatchShipEvent, blueprint initialisation and free-slot search."""),
}

LABELS = {
    # ------------------------------------------------------------------ laser hit
    0xEC55: (None, 'verified', """
Entered from UpdatePlayerLaser with damage C = 15 (laser 1/2), 23 (3) or 50 (4).
Requests the laser-hit sound (SoundEffectRequests bit 3, set only here).
No damage to the station (+$26 bit 2, set only in slot 0), to an object whose explosion
stage has begun (+$20 bit 5, set at $DBB6/$E201) or once energy +$22 is $FF (destroyed).
Each damaging hit lowers the AI threshold +$25 by 14; on borrow it becomes 6 or 7
(bit 0, ECM fitted, survives) and bit 7 (fleeing) is kept.  L_F8E2 makes a hostile ship
flee when +$25 AND $7F < 8, and L_F7B6 compares +$25 with a random byte before
abandoning ship.  Energy reaching zero (or borrowing) continues at L_EC8C (destruction
and debris events).  All paths end in DrawLaser.
NOTE: a fleeing ship (bit 7 set) never borrows, so a value below 14 wraps to $72+value.
The courage is then 114..127: the ship turns back towards the player at full
acceleration, still without firing (ApplySteeringVector returns before TryFireAiLaser
while bit 7 is set), and the abandon-ship test at L_F7B6 seldom passes.  A Python under
pulse fire flees at hit 9 and turns back at hits 10, 19, 28 ...
Evidence: combat/r10-laser-hit-outcomes in tools/check_routines.py (every +$25 value,
flags, energies, all 19 blueprints); tools/check_ai_courage_fix.py (Python fight with
the real steering, and a 48K emulator fight).
aicouragefix=yes replaces $EC6A..$EC7C (src/ai-courage-fix.asm): the subtraction and
floor act on bits 0..6 only, so a fleeing ship keeps courage 6 or 7."""),
    0xEC8C: (None, 'verified', """
Target destroyed: energy +$22 := $FF (later hits are ignored), set +$20 bit 4.
The Asp marked with +$26 bit 6 by L_F62C, destroyed while MissionAspEncounterState is 1
or 2, sets that state to 3 and drops one cargo canister (event 6) instead of the usual
debris; in state 3 the next object scooped through L_EAC3 yields item $FF, which
ScoopCargoItem turns into the cloaking device (CommanderFlags bit 6).
State 0 or 3, or an unmarked ship: debris choice at L_ECAD.
Evidence: combat/r10-laser-hit-outcomes; scoop code at L_EAC3."""),
    0xECAD: (None, 'verified', """
Debris selection from the blueprint at instance +$23/+$24:
blueprint +0 low nibble nonzero -> event 6 (one Cargo canister at the parent, SpawnCargoCanister);
else blueprint energy +7 >= 85 -> event 5 (two Alloy plates, SpawnAlloyPlatePair);
else energy 60 (Asteroid) hit with damage 50 -> event 8 (two Splinters, SpawnSplinterPair, see
docs/SHIPS.md); otherwise no debris. The event high nibble is 0, so C = 0 in the handlers
and the debris appears at the destroyed ship.  With the default blueprints: rock hermit,
traders, pirates and Krait drop a canister; Viper, Asp, Fer-de-Lance and Thargoid drop
alloys; an Asteroid splits only under the mining laser; the rest drop nothing.
Evidence: combat/r10-laser-hit-outcomes (all 19 blueprint IDs)."""),
    0xECD4: (None, 'verified', """
Four DrawLine calls from the bottom view edge to a random point at the centre.
Start magnitudes (84,63) and (64,63): screen x 43/211 and 63/191 at y 126. End magnitudes
D,E in {0,2} with random quadrant bits (RNG AND $0C), kept in L_EA4F for the later beams.
The start (HL) pixel at y 126 is not plotted, so the beams begin at y 125.
Evidence: tools/check_laser_variant.py and lines/sights-and-laser-lines."""),
    # ------------------------------------------------------------------ RNG
    0xED24: (None, 'verified', """
RandomSeed is written only here (static and runtime cross-references); it starts from
the tape value $F562 and nothing reseeds it from a clock, the R register or input.  It
is separate from AuxRandomSeed (stardust and damage effects).  31 call sites draw from
it: ship creation and positions, encounter, launch and AI decisions, debris placement,
the player's laser beam end point and AI laser beams.  The sequence advances only
through these calls, so it depends on what happened before (for example how often the
laser fired)."""),
    # ------------------------------------------------------------------ sights / ECM
    0xED37: ('ClearPitchAndSpeed', 'verified', """
PlayerDeadFlag path of UpdateSightsLaserAndEcm: clear PlayerPitch and PlayerSpeed and
return, so no sights, laser or ECM update runs after death.
Evidence: combat/r10-sights-and-ecm."""),
    0xED3F: ('UpdateSightsLaserAndEcm', 'verified', """
Per-frame weapon update, called by L_72D2, L_72FD and L_7356.  No register inputs;
clobbers A, BC, DE, HL, IX and the alternate set (DrawLine).
PlayerDeadFlag nonzero: ClearPitchAndSpeed.  Other screens than views 0..3
(CurrentScreenId) return at once, without the ECM update.
If LaserMounts+view (front, rear, left, right) holds a laser: draw four 8-pixel sight
marks around (127,63) (x 111..118 and 136..143 at y 63; y 48..55 and 71..78 at x 127),
then run UpdatePlayerLaser (temperature, firing, ApplyPlayerLaserHit or DrawLaser).
Then, with or without a laser, the ECM countdown at L_ED83.
Evidence: lines/sights-and-laser-lines (sight pixels), combat/r10-sights-and-ecm;
runtime: all flight scenarios."""),
    0xED83: (None, 'verified', """
ECM countdown.  Skipped (RET) with the ECM jammer (CommanderFlags bit 7) while
L_A871 = 4; the AI ECM decision at L_F815 tests the same condition.
B = old KeyFlagsCombat (its bit 4, the E key, is cleared in memory), C = EcmFitted.
EcmTimer zero: ActivatePlayerEcm (E with an ECM fitted sets EcmFitted bit 7 and
EcmTimer = 10).  Otherwise decrement EcmTimer and at zero clear bit 7 of C (the
player's pulse is over).  While the timer runs: request the ECM sound
(SoundEffectRequests bit 5, set only here) and, if the player owns an ECM (C nonzero),
store C back and add one energy drain unit (L_DA17, subtracted by L_A572).
NOTE: the drain also applies while an AI ship's ECM pulse (L_F815) runs.
Evidence: combat/r10-sights-and-ecm."""),
    # ------------------------------------------------------------------ line renderer
    0xEDBC: ('LineClipRegionTable', 'verified', """
Region number of an outside endpoint, indexed by the 4-bit outcode built by DrawLine:
bit 0 = |x| >= 128, bit 1 = |y| >= 64 (outside), bit 2 = below centre, bit 3 = left.
Regions clockwise from top-left: 1 TL, 2 T, 3 TR, 4 R, 5 BR, 6 B, 7 BL, 8 L (odd = corner).
The values are ordinal numbers (they select a row/column of LineClipRegionPairTable),
not direction bit sets.  Entries for inside outcodes (bits 0..1 clear) are 0 and are
never read.
Evidence: index code at L_EE41..L_EE5E; runtime readers $EE4F/$EE5E; lines/draw-line."""),
    0xEDCC: ('LineClipRegionPairTable', 'verified', """
Symmetric 8x8 table for two outside endpoints: row = DE-end region, column = HL-end
region (both 1..8, columns TL,T,TR,R,BR,B,BL,L), read at L_EE6D as
LineClipRegionTable+8*row+column+7.
0 = both on the same outer side: nothing visible, DrawLine returns.
1 = opposite regions (L_EF58). 2 = regions whose line may cut one view corner (L_EFA5)."""),
    0xEE0C: ('LineClipEndpointRegions', 'verified', """
Both-outside clipping workspace: low byte = HL-end region, high byte = DE-end region.
Written at L_EFA5 (re-written swapped when the endpoints are exchanged), read at L_F021."""),
    0xEE0E: ('LineClipCornerVector', 'verified', """
Low byte = slope, high byte = ComputeLineDelta flags of the vector from a view corner
(magnitudes 128,64) to the DE endpoint. Saved at $EF70/$F00B, compared with the line
slope at $EF7A/$F015 to decide which view edge the line crosses."""),
    0xEE10: (None, 'verified', """
Inputs: H,L = |x|,|y| of endpoint 1; D,E = |x|,|y| of endpoint 2; C bits 0/1 =
endpoint 1 below/left of centre, bits 2/3 = endpoint 2 below/left.
Screen x = 127+-|x|, y = 63+-|y|; an endpoint with |x| >= 128 or |y| >= 64 is clipped.
Pixels are ORed (XOR mode: see L_DA29) into ViewBitmapBuffer, starting at the DE end or
its clipped point; the HL end pixel itself is not plotted.
Nothing is drawn when x1 = y2 = $FF or y1 = x2 = $FF (H AND E or L AND D = $FF): the
test pairs coordinates of different endpoints, so one endpoint at ($FF,$FF) alone is
still drawn.  Projected coordinates saturate at 255 (DivideRatioByte).
All registers are clobbered; a drawn line returns from a plotting loop in the
alternate register set (odd EXX count), so callers save what they need.
Callers (static and runtime, the only ones): DrawVisibleEdges (ship edges), L_E1AC (AI
laser beam), DrawLaser and the sight marks of UpdateSightsLaserAndEcm.
Paths: both inside L_EE99; one outside L_EE8F/L_F130; both outside via the region tables.
Evidence: a simulator check in tools/check_routines.py: 1500 inside lines equal a DDA
model exactly; 1500 clipped lines stay within 3 px of the ideal segment and never
write outside the buffer.  Deltas above 255 use halved 9-bit values; one of about 350
such random lines was clipped visibly wrong."""),
    0xEE77: (None, 'verified', """
DE end outside, HL end inside: swap the endpoints and the quadrant pairs in C,
so that HL is the outside end and drawing starts from the inside end."""),
    0xEE87: (None, 'verified', """
DE end inside: both inside -> L_EE99; HL outside -> keep the order and clip (L_EE8F)."""),
    0xEE8F: (None, 'verified', """
One end outside (HL), DE inside: delta and slope, plot start at DE, then L_F130
limits the pixel count to the distance from DE to the view edge."""),
    0xEE99: (None, 'verified', """
Both ends inside: plot from DE for max(|dx|,|dy|) pixels; the HL end pixel is omitted."""),
    0xEEAC: (None, 'verified', """
Common plot set-up. A = pixel count along the major axis; alternate HL/C/B/E come from
SetLinePlotStart. Alternate D := max(A,2)-1 pixels, alternate E := $80 (error accumulator),
and the slope becomes the ADD A,n operand of the selected loop. Flags AND $1C (bit 2 draw
up, bit 3 draw right, bit 4 x-major) select the loop and patch its x step:
RRC C ($CB $09) with INC L ($2C) steps right; RLC C ($CB $01) with DEC L ($2D) steps left.
0/8: PlotSteepLineDown, 4/$0C: PlotSteepLineUp, $10/$18: PlotShallowLineDown,
$14/$1C: PlotShallowLineUp (the +8 values step right)."""),
    0xEF58: ('ClipLineBothEndsOutside', 'verified', """
Both ends outside; A = pair value 1 or 2, L = saved quadrant bits.
Value 1 (opposite regions): corner pairs compare the line slope with the vector from DE
to the corner of its own quadrant; edge pairs (L_EF96) clip DE on its own edge.
Value 2 continues at L_EFA5."""),
    0xEF96: (None, 'verified', """
Opposite edge regions: |y2| >= 64 (top/bottom pair) clips DE at the horizontal edge
(L_F042); otherwise (left/right pair) at the vertical edge (L_F080)."""),
    0xEFA5: (None, 'verified', """
Pair value 2: save both region numbers in LineClipEndpointRegions and exchange the
endpoints when the DE end lies in a corner region, so that DE is in an edge region.
Then choose the view corner between the two regions as quadrant bits in H:
0 top-right, 1 bottom-right, 2 top-left, 3 bottom-left (sum and XOR tests at L_EFCC)."""),
    0xF000: (None, 'verified', """
Build the corner-to-DE vector (LineClipCornerVector) and the line delta, then compare
their slopes: a line passing outside the chosen corner is dropped (L_F040, nothing drawn);
otherwise DE is clipped to its own edge (L_F042 or L_F080)."""),
    0xF042: (None, 'verified', """
Clip DE to the horizontal edge: move |x| by the y excess (|y|-64) times the slope
(ScaleByFraction) or divided by it (DivideToFractionC), flipping the x quadrant bit
when it crosses the centre; then |y| := 63 and |x| is clamped to 127.
Plot from there; L_F130 sets the count."""),
    0xF080: (None, 'verified', """
Clip DE to the vertical edge: move |y| by the x excess (|x|-128) as in L_F042,
flipping the y quadrant bit on crossing; then |x| := 127 and |y| is clamped to 63."""),
    0xF0BE: ('ScaleByFraction', 'verified', """
C = (MultiplyUnsigned(A,C) + $80) >> 8: A times the 8-bit fraction C, rounded.
MultiplyUnsigned is exact when A+C is even. DE and HL preserved; A, B and flags changed.
Used by the edge clipping (L_F042, L_F080) to move a coordinate by excess * slope.
Evidence: a simulator check in tools/check_routines.py, 3000 random pairs."""),
    0xF0CC: ('DivideToFractionC', 'verified', """
C = A*256/B (an 8-bit fraction) for A < B; $FF when A = B. Restoring division in
L_E5B4 with E = 0 and C = $FE as an 8-step sentinel. B and DE preserved.
Used for the line slope (minor delta over major delta, ComputeLineDelta) and to convert
a distance by a slope (L_F042, L_F080, L_F130).
Evidence: a simulator check in tools/check_routines.py, 3000 random pairs with A <= B."""),
    0xF0D6: ('SetLinePlotStart', 'verified', """
Convert the DE endpoint to its plot position in the alternate registers:
x = 127+-D, y = 63+-E (left/below from B bits 1/0). HL' = ViewBitmapBuffer address,
C' = pixel mask, E' = slope from C, B' = rows to the character-cell edge in the drawing
direction (B bit 2 set, drawing up: (y AND 7)+1; clear: 8-(y AND 7)).  D' also holds
the mask until L_EEAC replaces it with the pixel count.
Returns in the main set with BC, DE and HL unchanged and A = B.
Evidence: a simulator check in tools/check_routines.py, 3000 points."""),
    0xF130: (None, 'verified', """
Pixel count for a line that leaves the view.  Entered by JP after SetLinePlotStart has
set the alternate registers for the start point; B/C = line flags/slope, DE = start.
Take the view corner ahead in the drawing direction (magnitudes 128,64) and its delta
and slope from the start (ComputeLineDelta). If the line is not steeper than that
vector on its major axis (or the vector has the other major axis), count = major
distance to the edge; otherwise count = (minor distance - 1) / slope (DivideToFractionC).
Continue at L_EEAC with D/E = line flags/slope."""),
    0xF175: ('ComputeLineDelta', 'verified', """
Endpoint 1 = H,L and endpoint 2 = D,E magnitudes; B bits 0/1 = endpoint 1 below/left,
bits 2/3 = endpoint 2 below/left. Returns H = |dx|, L = |dy| (low 8 bits),
C = slope = minor*256/major (DivideToFractionC) and flags in B:
bit 0/1 = endpoint 2 below/left, bit 2 = endpoint 2 lower than endpoint 1 (draw up),
bit 3 = endpoint 2 left of endpoint 1 (draw right), bit 4 = x-major
((|dx|>>1) >= (|dy|>>1)), bit 5 = copy of bit 1, bits 6/7 = |dy|/|dx| above 255
(the slope then uses halved deltas). DE preserved.
The flags are built two bits higher and rotated into place at $F1D4/$F1D9.
Evidence: a simulator check in tools/check_routines.py, 6000 random endpoint pairs."""),
    # ------------------------------------------------------------------ plotting loops
    0xF201: ('SteepUpNextRow', 'verified', """
One pixel row up inside the character cell (DEC H), then plot (PlotSteepLineUp)."""),
    0xF202: ('PlotSteepLineUp', 'verified', """
Y-major plotting loop drawing upwards, in the alternate registers:
HL = buffer address, C = pixel mask, D = pixels left, E = error accumulator,
B = rows left in the character cell. Plot (SteepUpPlotOp), return (RET Z) when D reaches
zero, add the slope (SteepUpSlope) to E; on carry rotate the mask one pixel along x
(SteepUpMaskRotate) and step a byte when it wraps (SteepUpByteStep); then one row up
(SteepUpNextRow, or the cell change at L_F211).
The plot op is patched by L_DA33, the other three bytes by the octant code at L_EEAC."""),
    0xF203: ('SteepUpPlotOp', 'verified', ''),
    0xF209: ('SteepUpSlope', 'verified', ''),
    0xF20E: ('SteepUpMaskRotate', 'verified', ''),
    0xF211: (None, 'verified', """
Count the row just plotted.  At the top of the character cell (B = 0) move to the bottom
row of the character row above: H+7, L-32, and H-8 more when L borrows (third boundary)."""),
    0xF224: ('SteepUpByteStep', 'verified', ''),
    0xF228: ('ShallowUpByteStep', 'verified', """
The pixel mask wrapped past a byte edge: step the buffer address one byte along x
(patched INC L / DEC L), then plot (PlotShallowLineUp)."""),
    0xF22C: ('ShallowUpStepX', 'verified', """
Next pixel of PlotShallowLineUp: rotate the mask one pixel along x (patched RRC C /
RLC C); carry means a byte edge (ShallowUpByteStep)."""),
    0xF22D: ('ShallowUpMaskRotate', 'verified', ''),
    0xF230: ('PlotShallowLineUp', 'verified', """
X-major plotting loop: one x step per pixel (ShallowUpStepX), one row up (DEC H) on
accumulator carry. Registers as in PlotSteepLineUp.
Self-modified: ShallowUpPlotOp, ShallowUpSlope, ShallowUpMaskRotate, ShallowUpByteStep."""),
    0xF231: ('ShallowUpPlotOp', 'verified', ''),
    0xF237: ('ShallowUpSlope', 'verified', ''),
    0xF250: ('SteepDownNextRow', 'verified', """
One pixel row down inside the character cell (INC H), then plot (PlotSteepLineDown)."""),
    0xF251: ('PlotSteepLineDown', 'verified', """
Y-major plotting loop drawing downwards (SteepDownNextRow). Registers as in
PlotSteepLineUp.  Self-modified: SteepDownPlotOp, SteepDownSlope, SteepDownMaskRotate,
SteepDownByteStep."""),
    0xF252: ('SteepDownPlotOp', 'verified', ''),
    0xF258: ('SteepDownSlope', 'verified', ''),
    0xF25D: ('SteepDownMaskRotate', 'verified', ''),
    0xF260: (None, 'verified', """
Count the row just plotted.  At the bottom of the character cell (B = 0) move to the top
row of the next character row: H-7, L+32, and H+8 more when L carries (third boundary)."""),
    0xF275: ('SteepDownByteStep', 'verified', ''),
    0xF279: ('ShallowDownStepX', 'verified', """
Next pixel of PlotShallowLineDown: rotate the mask one pixel along x (patched RRC C /
RLC C); carry means a byte edge (ShallowDownByteStep)."""),
    0xF27A: ('ShallowDownMaskRotate', 'verified', ''),
    0xF27D: ('PlotShallowLineDown', 'verified', """
X-major plotting loop: one x step per pixel (ShallowDownStepX), one row down (INC H) on
accumulator carry.  Self-modified: ShallowDownPlotOp, ShallowDownSlope,
ShallowDownMaskRotate, ShallowDownByteStep."""),
    0xF27E: ('ShallowDownPlotOp', 'verified', ''),
    0xF284: ('ShallowDownSlope', 'verified', ''),
    0xF29D: ('ShallowDownByteStep', 'verified', ''),
    # ------------------------------------------------------------------ ship creation
    0xF2A1: ('ShipInstanceTemplate', 'verified', """
31-byte default instance image (InstanceTemplateSize), copied by
InitialiseShipFromBlueprint (LDIR at $F31E) over instance bytes +$00..+$1E before the
blueprint fields are set.
InstanceX/Y/Z = +$3200 each; the loader then randomises x and y, z stays +$3200
unless the caller moves it.
Axes in sign-magnitude words ($7FFF = +1, $FFFF = -1): InstanceAxisZ = (0,0,-1),
InstanceAxisY = (0,+1,0), InstanceAxisX = (-1,0,0), so a new ship's forward axis points
back at the player.  +$1B..+$1E are zero (the speed is set later).
L_F3B3 clears bit 7 of +$0E/+$16 to turn the two -1 entries into +1.
Evidence: Instance* field formats (objects); objects/r10-ship-creation."""),
    0xF2C0: ('ObjectSlot7OrientationBytes', 'verified', """
Nine bytes copied by L_F616 (event 9, SetUpDisplayShip) to instance +$0A,+$0C,...,+$1A
of slot 7: the sign-magnitude high bytes of InstanceAxisZ, InstanceAxisY and
InstanceAxisX (the low bytes stay from the template).
The rows have length 1.00..1.02 ($7F = 1), are orthogonal within 0.012 and X = Y x Z:
a proper rotation, the fixed tilt of the slot-7 display ship (RunTitleScreen
dispatches event $79, ship ID 9).
Evidence: objects/r10-ship-creation."""),
    0xF2C9: ('ChildLaunchOrientationToggle', 'verified', """
Bit 0 toggled by AdjustChildLaunchOrientation on every non-station child launch; the
new value selects the three-swap path (1) or the single swap at L_F4BB (0)."""),
    0xF2CA: (None, 'verified', """
C (the event high nibble) per handler: 0 unused (SpawnRandomEncounter overwrites it),
1 unused (SpawnThargoidGroup sets its count), 2 missile target code (0 = AI missile at
IX), 4 launch subtype, 5/6 even = at the parent IX, odd = near the player, 7 even =
escape capsule from IX, odd = the player's abandoned Cobra, 8 unused, 9 ship ID - 2 for
slot 7.  Events 3 and 10..15 return at once.  Laser-kill debris (L_ECD1) uses C = 0."""),
    0xF2FB: (None, 'verified', """
Details: +$20 = blueprint +$0A bits 0..2 (payload count) + blueprint +$12 bit 7 + bit 6
(counted); +$25 = $7E (AI threshold, no ECM, not fleeing); +$26 = 0.  Position: x and y
low bytes and both signs are random; their high bytes are random 0..7 for a calm ship
and keep the template $32 when +$21 bit 2 (hostile) is set; z stays +$3200.  Uses three
or five NextRandomByte values.  Returns A = 0 with Z set; IX unchanged, BC/DE/HL changed.
Evidence: objects/r10-ship-creation (all 19 blueprint IDs).
randomizedspawn=yes (src/randomized-spawn.asm) keeps the caller's A on the stack in place
of the unread LD B,A and stores the last fields in fewer bytes ($F338..$F355).  Bit 7 of
A then asks for a random placement: the test becomes hostility XOR bit 3 of one extra
NextRandomByte.  Every caller but InitialiseEncounterShip passes A below $80 and gets the
original placement and RNG use."""),
    0xF366: ('RandomiseShipLowBytesAndSigns', 'verified', """
Last part of InitialiseShipFromBlueprint, shared by both placements: random x and y low
bytes and random x/y signs, then A = 0 with Z.  A hostile ship arrives here with the
template high bytes $32 (a diagonal corner), a calm one after drawing high bytes 0..7.
Evidence: objects/r10-ship-creation (all 19 blueprint IDs)."""),
    0xF381: (None, 'verified', """
The 27 copied bytes are InstanceX/Y/Z and the three axes; speed +$1B is not copied, so
the child starts at half its own maximum speed (callers adjust it).
Success: BC = 0, A = 0.  Failure (NZ): HL = the parent, but IX is left at slot 6 by
FindFreeShipSlot.
Evidence: objects/r10-ship-creation."""),
    0xF399: (None, 'verified', """
Outputs: Z with IX = the first free slot (1..6) and A = 0; NZ with IX = slot 6, B = 1
and A = its energy.  DE = InstanceSize in both cases; HL and IY are preserved as well.
Evidence: objects/r10-ship-creation."""),
    0xF3AD: (None, 'verified', """
A = ship ID: allocate a slot (FindFreeShipSlot; NZ: none free, IX = slot 6), then
L_F3B3.  Called by SpawnObjectNearPlayer, which then moves the object to a random
nearby offset."""),
    0xF3B3: (None, 'verified', """
Initialise ship A in slot IX (InitialiseShipFromBlueprint), clear bit 7 of +$0E and
+$16, then zero +$00, +$01, +$04, +$06 and +$07 (A = 0 from the loader; returns Z).
Result: identity orientation (all three axes +1, like the player's ship) at the player's
position x = z = 0, except a random y low byte (0..255) and random x/y signs.  Callers
then set the final position: the player missile (slot 7, L_F419), the abandoned Cobra
(HandleEscapeCapsuleEvent) and debris near the player (SpawnObjectNearPlayer).
Evidence: objects/r10-ship-creation."""),
    0xF3CE: ('SpawnThargoidGroup', 'verified', """
Event 1: create 3 or 4 Thargoids (ID 15; count = 3 + one random bit), stopping early
when no slot is free.  Each gets +$25 bit 0 (ECM fitted), z high byte +$07 = random 0..15
with bit 2 forced (4..7 or 12..15), x high byte +$01 = bit 3 of that value and y high
byte +$04 = 0 (low bytes and signs random from the loader); then L_F4E6 randomises the
high bytes +$0A/+$0C.  Returns Z when all were created, NZ when the slots ran out (C =
Thargoids still missing).  Evidence: objects/r10-ship-creation."""),
}

COMMENTS = {
    # tail of L_EBC7 (laser heat and firing)
    0xEC01: 'laser 4: D = 7 (laser 1: D = 1)',
    0xEC03: 'E = previous fire state',
    0xEC07: 'firing in this call',
    0xEC0C: 'held fire repeats when L_DA0E AND D = 0',
    0xEC11: 'one energy drain unit per shot',
    0xEC18: 'laser-fire sound request:',
    0xEC1B: 'bit 4 (set only here)',
    0xEC1D: 'damage: laser 1/2 15, 3 23, 4 50',
    0xEC22: 'laser 1/2: 15',
    0xEC24: 'laser 3: 15+8 = 23',
    0xEC26: 'laser 4: 15+27+8 = 50',
    0xEC2A: 'C = damage per hit',
    0xEC2B: 'heat +10 (D = 0) or +8 (D = 1/7)',
    0xEC33: 'cap heat at $A0',
    0xEC39: 'new temperature',
    0xEC3C: '8 - slot index of the target, 0 = none',
    0xEC40: 'no target: beams only',
    0xEC46: 'A = 9 - L_DA12 -> slot 8 - L_DA12',
    0xEC47: 'slot 0, then 8 - L_DA12 steps',
    0xEC4B: 'instance size',
    0xEC4F: 'IX = targeted instance',
    # ApplyPlayerLaserHit
    0xEC55: 'the target turns hostile',
    0xEC59: 'laser-hit sound request (bit 3)',
    0xEC5E: 'the station (slot 0): no damage',
    0xEC64: 'explosion stage: no damage',
    0xEC6A: 'AI threshold -14 (floor 6 + bit 0)',
    0xEC76: 'bits 0..6 new, bit 7 old',
    0xEC7D: 'energy $FF: already destroyed',
    0xEC84: 'subtract the damage',
    0xEC88: 'zero (or borrow): destroyed',
    0xEC8A: 'still alive: beams only',
    0xEC95: 'Asp marked by L_F62C?',
    0xEC9B: 'only in state 1 or 2',
    0xECA7: 'L_DA0C := 3',
    0xECAA: 'event 6: one canister',
    0xECB0: 'HL = blueprint',
    0xECB4: 'canister nibble -> event 6',
    0xECBF: 'energy >= 85 -> event 5',
    0xECC6: 'energy 60: Asteroid',
    0xECCB: 'damage 50 -> event 8 (Splinters)',
    0xECD1: 'event 5, 6 or 8; C = 0: at this ship',
    # DrawLaser
    0xECD7: 'B = random byte',
    0xECDB: 'centre-end quadrant bits',
    0xECE5: 'D = 0 or 2',
    0xECF1: 'E = 0 or 2',
    0xECF7: 'start (84,63): screen (43,126)',
    0xED05: 'screen (211,126)',
    0xED07: 'beam 2',
    0xED0B: 'start (64,63): (63,126), (191,126)',
    0xED16: 'beam 3',
    0xED21: 'beam 4',
    # NextRandomByte
    0xED2A: 'A = 2*H + incoming carry',
    0xED2C: 'A = new L + old L + carry',
    0xED2D: 'new high byte, returned in A',
    0xED2E: 'new low byte',
    0xED35: 'initial seed from the tape',
    # UpdateSightsLaserAndEcm
    0xED3F: 'nonzero: no weapons this frame',
    0xED48: 'flight views only',
    0xED4B: 'laser of the current view',
    0xED56: 'left mark: x 111..118, y 63',
    0xED61: 'right mark: x 136..143, y 63',
    0xED6B: 'upper mark: x 127, y 48..55',
    0xED75: 'lower mark: x 127, y 71..78',
    0xED80: 'heat, firing and beams',
    # ECM countdown
    0xED83: 'bit 7: ECM jammer',
    0xED8A: 'and L_A871 = 4: no ECM update',
    0xED90: 'bit 4 = the E key',
    0xED93: 'B = key bits before clearing',
    0xED94: 'consume the E (ECM) key',
    0xED96: 'C = ECM fitted, bit 7 player pulse',
    0xED9A: 'ECM pulse countdown',
    0xED9E: 'idle: start on the E key',
    0xEDA7: 'pulse over: clear bit 7',
    0xEDAC: 'ECM sound request (set only here)',
    0xEDB0: 'no ECM owned: no cost',
    0xEDB1: 'write back (bit 7 cleared at the end)',
    0xEDB8: 'one energy drain unit per update',
    # LineClipRegionTable rows (4 outcodes per quadrant)
    0xEDBC: 'up/right: -, R, T, TR',
    0xEDC0: 'down/right: -, R, B, BR',
    0xEDC4: 'up/left: -, L, T, TL',
    0xEDC8: 'down/left: -, L, B, BL',
    # LineClipRegionPairTable rows (DE region)
    0xEDCC: 'DE TL',
    0xEDD4: 'DE T',
    0xEDDC: 'DE TR',
    0xEDE4: 'DE R',
    0xEDEC: 'DE BR',
    0xEDF4: 'DE B',
    0xEDFC: 'DE BL',
    0xEE04: 'DE L',
    # DrawLine
    0xEE10: 'x1 = y2 = $FF: nothing',
    0xEE14: 'y1 = x2 = $FF: nothing',
    0xEE1C: 'B = DE outcode',
    0xEE20: '|x2| >= 128',
    0xEE27: '|y2| >= 64',
    0xEE2E: 'C = HL outcode',
    0xEE32: 'HL quadrant in bits 3/2',
    0xEE34: '|x1| >= 128',
    0xEE3B: '|y1| >= 64',
    0xEE45: 'DE end inside?',
    0xEE4F: 'DE region 1..8',
    0xEE54: 'HL end inside?',
    0xEE56: 'HL inside, DE outside: swap',
    0xEE5E: 'HL region 1..8',
    0xEE63: '8*B + C',
    0xEE67: 'row B-1, column C-1',
    0xEE6E: 'pair value; 0 = invisible',
    0xEE70: 'the line may cross the view',
    0xEE73: 'drop saved BC, HL, DE',
    0xEE7A: 'swap the quadrant pairs',
    0xEE85: 'one end (now HL) outside',
    0xEE8A: 'both ends inside',
    0xEE90: 'H,L = |dx|,|dy|; B flags; C slope',
    0xEE93: 'start address/mask at DE',
    0xEE96: 'count up to the view edge',
    0xEEA3: 'pixel counts |dx|+1, |dy|+1',
    0xEEA6: 'x-major: count along x',
    0xEEAD: 'at least one pixel',
    0xEEB4: 'pixels to plot',
    0xEEB6: 'error accumulator = 1/2',
    0xEEBC: 'bit 2 up, 3 right, 4 x-major',
    0xEEBE: 'x-major: $10..$1C',
    0xEEC2: 'cases 8 and $0C',
    0xEEC6: 'case 4 or 0',
    0xEECD: 'case 0: RLC C (left)',
    0xEED2: 'DEC L',
    0xEED9: 'case 4: RLC C (left)',
    0xEEDE: 'DEC L',
    0xEEE3: 'case $0C or 8',
    0xEEE9: 'case 8: RRC C (right)',
    0xEEEE: 'INC L',
    0xEEF4: 'slope',
    0xEEFA: 'cases $18 and $1C',
    0xEEFE: 'case $14 or $10',
    0xEF04: 'case $10: RLC C (left)',
    0xEF09: 'DEC L',
    0xEF10: 'case $14: RLC C (left)',
    0xEF15: 'DEC L',
    0xEF1A: 'case $1C or $18',
    0xEF21: 'case $18: RRC C (right)',
    0xEF26: 'INC L',
    0xEF2C: 'slope',
    0xEF34: 'case $0C: RRC C (right)',
    0xEF39: 'INC L',
    0xEF3F: 'slope',
    0xEF47: 'case $1C: RRC C (right)',
    0xEF4C: 'INC L',
    0xEF52: 'slope',
    0xEF58: 'L = saved quadrant bits',
    0xEF5D: 'odd DE region: corner pair',
    0xEF68: 'DE quadrant for both ends',
    0xEF6A: 'corner of the DE quadrant',
    0xEF70: 'corner-to-DE flags/slope',
    0xEF77: 'delta and slope of the line',
    0xEF84: 'other major axis: slope $FF',
    0xEF90: 'slope test picks the edge',
    0xEF9D: 'top/bottom pair?',
    0xEFA5: 'C = HL region, B = DE region',
    0xEFA9: 'DE in a corner: swap ends',
    0xEFC8: 'swapped regions',
    0xEFCE: 'sum < 7: top-right',
    0xEFD4: 'sum >= 12: bottom-left',
    0xEFDD: 'XOR >= 8: top-left',
    0xEFE2: 'XOR < 4: bottom-right',
    0xEFE6: 'XOR 5: by DE region',
    0xEFEB: 'bottom-left or top-right',
    0xF001: 'corner quadrant in bits 0/1',
    0xF005: 'selected view corner',
    0xF00B: 'corner-to-DE flags/slope',
    0xF012: 'delta and slope of the line',
    0xF01F: 'other major axis: slope $FF',
    0xF021: 'H = DE region, L = HL region',
    0xF028: 'DE on the top/bottom edge?',
    0xF040: 'misses the view: return',
    0xF045: 'y excess beyond the edge',
    0xF04D: 'y-major: excess * slope',
    0xF053: 'x-major: excess / slope',
    0xF05A: 'towards the centre?',
    0xF068: 'crossed: flip x quadrant',
    0xF06B: '|y| := 63',
    0xF072: 'clamp |x| to 127',
    0xF074: 'plot start: the clipped DE',
    0xF077: 'pixel count from there',
    0xF083: 'x excess beyond the edge',
    0xF08B: 'x-major: excess * slope',
    0xF091: 'y-major: excess / slope',
    0xF098: 'towards the centre?',
    0xF0A6: 'crossed: flip y quadrant',
    0xF0A9: '|x| := 127',
    0xF0B0: 'clamp |y| to 63',
    0xF0B2: 'plot start: the clipped DE',
    0xF0B5: 'pixel count from there',
    0xF0C1: 'HL = A*C (exact for even A+C)',
    0xF0C4: 'round',
    0xF0D9: "B',C' = |x|,|y|; D',E' = flags, slope",
    0xF0E0: 'right: x = 127+|x|',
    0xF0E5: 'left: x = 127-|x|',
    0xF0ED: 'below: y = 63+|y|',
    0xF0F2: 'above: y = 63-|y|',
    0xF0FD: 'mask $80 >> (x AND 7)',
    0xF10E: 'y bits 6..7 and 0..2',
    0xF115: 'buffer page (see L_E1AC)',
    0xF119: 'y bits 3..5',
    0xF120: 'up: (y AND 7)+1 rows',
    0xF12A: 'down: 8-(y AND 7) rows',
    0xF131: 'view corner',
    0xF13E: 'corner ahead',
    0xF143: 'H,L = distances to the corner',
    0xF14D: 'other major axis: slope $FF',
    0xF156: 'count = x distance',
    0xF162: 'count = y distance',
    0xF169: 'count = (distance-1)/slope',
    0xF172: 'A = pixel count',
    # ComputeLineDelta (flags two bits higher until the rotation at $F1D4/$F1D9)
    0xF17B: 'sign differences, ep2 signs',
    0xF183: 'draw right: bit 5 (ends as bit 3)',
    0xF185: 'x signs differ?',
    0xF18E: 'draw right',
    0xF190: '|dx| = |x1|+|x2|, carry kept',
    0xF195: 'same x sign',
    0xF19C: 'draw right',
    0xF1A6: 'draw right',
    0xF1A8: 'no |dx| overflow (bit 1, ends as 7)',
    0xF1AB: 'y signs differ?',
    0xF1AE: 'draw up: bit 4 (ends as bit 2)',
    0xF1B6: 'draw up',
    0xF1B8: '|dy| = |y1|+|y2|, carry kept',
    0xF1BD: 'same y sign',
    0xF1C4: 'draw up',
    0xF1CE: 'draw up',
    0xF1D0: 'no |dy| overflow (bit 0, ends as 6)',
    0xF1D4: 'C = 9-bit |dy| / 2',
    0xF1D9: 'A = 9-bit |dx| / 2',
    0xF1DF: 'x-major',
    0xF1E2: '|dx| above 255?',
    0xF1E6: 'halved deltas: dy/dx',
    0xF1EA: 'y-major',
    0xF1ED: '|dy| above 255?',
    0xF1F1: 'halved deltas: dx/dy',
    0xF1F4: 'dy/dx',
    0xF1F8: 'dx/dy',
    0xF1FA: 'slope = minor*256/major',
    # plotting loops
    0xF201: 'next row up',
    0xF203: 'patched: OR C, or XOR C (L_DA33)',
    0xF208: 'patched slope',
    0xF20B: 'no carry: same column',
    0xF20D: 'patched: RRC C right / RLC C left',
    0xF20F: 'mask wrapped: next byte',
    0xF211: 'rows left in the cell',
    0xF216: 'bottom row of the cell above',
    0xF21A: 'previous character row',
    0xF21D: 'same third',
    0xF21F: 'crossed a third: H-8',
    0xF224: 'patched: INC L right / DEC L left',
    0xF228: 'patched: INC L right / DEC L left',
    0xF22C: 'patched: RRC C right / RLC C left',
    0xF22E: 'mask wrapped: next byte',
    0xF231: 'patched: OR C, or XOR C (L_DA33)',
    0xF236: 'patched slope',
    0xF239: 'no carry: same row',
    0xF23B: 'carry: one row up',
    0xF23C: 'still inside the cell',
    0xF241: 'undo the borrow of DEC H: H+8',
    0xF244: 'previous character row',
    0xF247: 'same third',
    0xF24A: 'crossed a third: H-8',
    0xF250: 'next row down',
    0xF252: 'patched: OR C, or XOR C (L_DA33)',
    0xF257: 'patched slope',
    0xF25C: 'patched: RRC C right / RLC C left',
    0xF25A: 'no carry: same column',
    0xF25E: 'mask wrapped: next byte',
    0xF260: 'rows left in the cell',
    0xF262: 'next character row:',
    0xF265: 'H-7: its top row',
    0xF269: 'L+32',
    0xF26C: 'same third',
    0xF26F: 'crossed a third: H+8',
    0xF275: 'patched: INC L right / DEC L left',
    0xF279: 'patched: RRC C right / RLC C left',
    0xF27B: 'mask wrapped: next byte',
    0xF27E: 'patched: OR C, or XOR C (L_DA33)',
    0xF283: 'patched slope',
    0xF286: 'no carry: same row',
    0xF288: 'carry: one row down',
    0xF289: 'still inside the cell',
    0xF28E: 'undo the carry of INC H: H-8',
    0xF291: 'next character row',
    0xF294: 'same third',
    0xF297: 'crossed a third: H+8',
    0xF29D: 'patched: INC L right / DEC L left',
    # ShipInstanceTemplate lines
    0xF2A1: '+$00: x = +$3200 (low, high, sign)',
    0xF2A4: '+$03: y = +$3200',
    0xF2A7: '+$06: z = +$3200',
    0xF2AA: '+$09: z axis = (0, 0, -1), $7FFF = 1.0',
    0xF2B0: '+$0F: y axis = (0, +1, 0)',
    0xF2B6: '+$15: x axis = (-1, 0, 0)',
    0xF2BC: '+$1B..+$1E',
    0xF2C0: '+$0A,+$0C,...,+$1A',
    # DispatchShipEvent
    0xF2CA: 'C = high nibble',
    0xF2D5: 'event 0',
    0xF2D9: 'event 1',
    0xF2DD: 'event 2: missile',
    0xF2E1: 'event 3: none',
    0xF2E3: 'event 4',
    0xF2E7: 'event 5: two Alloy plates',
    0xF2EB: 'event 6: Cargo canister',
    0xF2EF: 'event 7: capsule (C even)',
    0xF2F3: 'event 8: two Splinters',
    0xF2F7: 'event 9: slot-7 ship C+2',
    0xF2FA: 'events 10..15: none',
    # InitialiseShipFromBlueprint
    0xF2FE: 'B is not read: LD BC reloads it below',
    0xF2FF: 'six-bit blueprint ID',
    0xF30C: 'IY = blueprint',
    0xF318: 'template size',
    0xF320: 'energy',
    0xF326: 'behaviour = +$12 AND $6F',
    0xF32F: 'payload count, +$12 bit 7',
    0xF33B: 'speed = maximum / 2',
    0xF343: '+$25 = $7E: AI threshold',
    0xF349: '+$26 = 0: no role flags',
    0xF34C: 'counted by EncounterShipCount',
    0xF350: 'hostile: keep high bytes $32',
    0xF356: 'calm: high bytes 0..7',
    0xF35B: 'x high byte',
    0xF363: 'y high byte',
    0xF366: 'random low bytes',
    0xF369: 'x low byte',
    0xF36F: 'y low byte',
    0xF372: 'random signs',
    0xF376: 'x sign',
    0xF37B: 'y sign',
    0xF37F: 'A = 0, Z set',
    # CreateShipAtParent / FindFreeShipSlot
    0xF387: 'HL = parent',
    0xF388: 'no slot: IX = slot 6',
    0xF392: 'parent +$00..+$1A',
    0xF397: 'Z, A = 0 (BC = 0)',
    0xF399: 'first ADD selects slot 1',
    0xF39D: 'instance size',
    0xF3A0: 'six allocatable slots',
    0xF3A4: 'zero energy: free',
    0xF3AB: 'NZ: no free slot',
    # L_F3B3 / SpawnThargoidGroup
    0xF3B6: 'z and x axes: -1 -> +1',
    0xF3BE: 'A = 0',
    0xF3D3: '3 or 4 Thargoids',
    0xF3DA: 'Thargoid',
    0xF3E0: '+$25 bit 0: ECM fitted',
    0xF3E9: '+$07 = 4..7 or 12..15',
    0xF3F1: '+$01 = bit 3',
    0xF3F7: '+$04 = 0',
    0xF3FA: 'random +$0A/+$0C high bytes',
    0xF3FE: 'next Thargoid',
}

DATA = {
    0xED35: (0xED37, 'words', 1),     # RandomSeed
    0xEDBC: (0xEDCC, 'bytes', 4),     # LineClipRegionTable
    0xEDCC: (0xEE0C, 'bytes', 8),     # LineClipRegionPairTable
    0xEE0C: (0xEE0E, 'bytes', 2),     # LineClipEndpointRegions
    0xEE0E: (0xEE10, 'bytes', 2),     # LineClipCornerVector
    0xF2A1: (0xF2C0, 'bytes', 6),     # ShipInstanceTemplate (lines split at comments)
    0xF2C0: (0xF2C9, 'bytes', 9),     # slot-7 orientation high bytes
    0xF2C9: (0xF2CA, 'bytes', 1),     # ChildLaunchOrientationToggle
}

CONSTANTS = {
    0xEF6A: 'view corner magnitudes |x| = 128, |y| = 64 for ComputeLineDelta, not an address',
    0xF005: 'view corner magnitudes |x| = 128, |y| = 64 for ComputeLineDelta, not an address',
    0xF131: 'view corner magnitudes |x| = 128, |y| = 64 for ComputeLineDelta, not an address',
}

OPERANDS = {
    0xEE67: 'LineClipRegionPairTable-LineClipRegionTable-9',   # ADD A,$07: 8*B+C+7
    0xF115: 'ViewBitmapBuffer >> 8',                            # OR $C0
    0xF318: 'L_F2C0-ShipInstanceTemplate',                      # LD BC,$001F
}

ASSERTS = {
    'r10-view-buffer-4k': ('((FontBitmap-GameImage+GameLoadAddress) & $0FFF) = 0',
                           'ViewBitmapBuffer = FontBitmap; SetLinePlotStart ORs y bits '
                           'into its page'),
    'r10-instance-template': ('L_F2C0-ShipInstanceTemplate = $1F',
                              'InitialiseShipFromBlueprint copies the template over +$00..+$1E'),
    'r10-clip-region-table': ('LineClipRegionPairTable-LineClipRegionTable = 16',
                              'DrawLine indexes both region tables from LineClipRegionTable'),
}
