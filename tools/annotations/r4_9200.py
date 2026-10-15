"""$9200..$A3FF: equipment prices, energy bomb flash, Torus jump, dashboard colours, stardust.

Evidence summary:
- instruction semantics of every routine below;
- 48K runtime traces (docs/generated/runtime-xrefs.json): energy bomb in the
  ecm-bomb-pod scenario (W key), view ids 0..3 from keys 1..4, roll/pitch copies
  L_7042/L_7043 changing with N/M and S/X, the J key reaching $9973;
- simulator checks in tools/check_routines.py (dust and maths groups): checks of the dust
  multiply/divide helpers, a Python model of one front-view dust pass that
  matches the original code byte for byte (particle records and view-buffer
  pixels), rear-view, roll, pitch and respawn checks, the $7A88-style patched
  single respawn, and a forced Torus jump showing the coordinate shift;
- pass-2 checks (p4-* in tools/check_routines.py): energy-bomb use and the
  view-attribute masks, the launch reset and instrument colours, the Torus jump
  side effects, and exact models of the roll, pitch and side-view dust motion;
- the equipment price table matches the manual prices in docs/info/Elite.txt
  and is printed beside tokens $69..$76 (FUEL .. MINING LASER).
"""

SECTIONS = {
    0x9260: ('Energy bomb and view-window attributes',
             'Energy bomb use, the cyan flash and the stack-based colour fill of\n'
             'the 3D view attributes (rows 0..15, columns 1..30).'),
    0x9966: ('Torus jump drive',
             'J key handler: when nothing is near, moves the sun, the planet and the\n'
             'station $2000 units along z (the player jumps forward).'),
    0x99F7: ('Stardust workspace',
             'Per-pass copies of one particle record, flags and the plot list used\n'
             'by UpdateDust ($9E74..$A44B).'),
    0x9A46: ('Launch reset and instrument block colours',
             'Gauge and state reset at launch, and the attribute colour of the two\n'
             'instrument blocks (red paper, magenta with an escape pod).'),
    0x9E74: ('Stardust (space dust particles)',
             'Up to 16 particle records of 5 bytes at L_A46C are moved with the\n'
             'speed and the roll/pitch copies, re-created when they leave the view,\n'
             'and XOR-plotted as single pixels into the view bitmap buffer.'),
}

LABELS = {
    # ---------------------------------------------------------------- prices
    0x9236: ('EquipmentPriceTable', 'verified', """
Equipment prices: 14 entries of 3 bytes, in the order of tokens $69..$76
(FUEL, MISSILE, LARGE CARGO BAY, E.C.M.SYSTEM, PULSE, BEAM, FUEL SCOOPS,
ESCAPE POD, ENERGY BOMB, ENERGY UNIT, DOCKING COMPUTERS, GALACTIC HYPERSPACE,
MILITARY LASER, MINING LASER).  Byte 0 = price DIV 1000 Cr (printed by
L_B7AF as the high part), bytes 1..2 = remaining price in tenths of a credit
(little-endian word); e.g. MISSILE = $00,$012C = 30.0 Cr, BEAM = $01,$0000 =
1000.0 Cr.  All 13 fixed prices equal the manual's equipment list.
Evidence: L_B53F loads HL with this table and prints one entry per item
(L_B597..L_B5A3); L_B70A also indexes it; runtime: docked-equipment."""),
    0x9237: ('FuelPrice', 'verified', """
Low byte of the FUEL price word (entry 0, tenths of a credit).  The only
runtime-written price byte: cleared at $B608 after buying fuel, set to
2*economy + (70 - fuel) by a normal jump ($D675) and to the old galaxy number + 1
by a galactic jump ($D632).  The high byte $9238 is never written.
NOTE: the byte is not part of the saved commander record and nothing recomputes it
from FuelLevel.  A tape load keeps the previous price, so after a reset and reload
fuel costs 0.0 whatever the loaded fuel; scooping fuel or a new commander leaves it
stale as well.
Evidence: tools/check_routines.py commander/fuel-price-not-restored.
fuelfix=yes recomputes it whenever the equipment list is shown (FuelPriceUpdate)."""),

    # ---------------------------------------------------------- energy bomb
    0x9260: ('UseEnergyBomb', 'verified', """
Use the energy bomb: when key flag bit 5 of L_FC11 (W) is set and the
energy-bomb byte L_A84C (commander +$36, listed as ENERGY BOMB at $D161) is nonzero,
clear that byte, set L_DA10 = 1 and sound request bit 0 of L_707D, then
flash the view 24 times through FlashViewAttributes (48 frame waits, about one
second).  L_DA10 makes the next UpdateObjects mark the active objects for
explosion (exemptions: see L_DA10); request bit 0 plays the noise sweep with
step -2.  The key bit is left set here; the caller L_A559, which runs only for
the cockpit views (screen id < 4), afterwards keeps only bits 0, 4 and 7 of L_FC11.
Input: none.  Output: none.  Clobbers: AF, BC, HL.
Evidence: called once per cockpit-view flight frame from L_A559; runtime:
ecm-bomb-pod scenario (bomb fitted by test poke, W key as in the manual)
executes $926C; tools/check_routines.py missions/p4-energy-bomb-use."""),
    0x9280: ('FlashViewAttributes', 'verified', """
One flash step: colour the view window with attribute $28 (cyan paper, black
ink) through the L_9291 entry, so only the L_A843 mask applies, then with $0F
through FillViewAttributes, whose masks turn it into the colour of the current
mode: $07 (white ink on black) normally, $0F (blue paper) while the cloak is
on, $02 (red ink) while L_A843 is set.  Each fill waits for one frame
interrupt (HALT).  Clobbers: AF, B, HL.
Evidence: tools/check_routines.py missions/p4-energy-bomb-use."""),
    0x9287: ('FillViewAttributes', 'verified', """
Set the attributes of the 3D view window (attribute rows 0..15, columns
1..30 of $5800..$59FF) to L.  While the cloak flag L_A80C is zero only the ink bits
0..2 of L are kept (black paper); when L_A843 is nonzero L is also ANDed with
$3A (paper and ink bit 1 kept: red or black ink).  Callers pass $07 for the
normal view, $0F when the cloak switches on (blue paper survives only then) and
$02 for the L_A843 colours.
The fill PUSHes HL with SP pointing into attribute RAM (16 rows of 15 words,
skipping two bytes per row = columns 31 and 0).  HALT first synchronises
with the frame interrupt, so no interrupt can push onto the attributes.
Input: L = attribute.  Output: A = 0, B = 0, H = L = the attribute written.
Clobbers: AF, B, HL.  SP is saved in L_92B5 and restored.
Evidence: instruction semantics; tools/check_routines.py missions/p4-energy-bomb-use
(all mask combinations, columns 0/31 and rows 16..23 untouched); callers restore
the view colour after screen changes (L_7ACD, L_D550, CockpitRestored, ...)."""),
    0x9291: (None, 'verified', """
FillViewAttributes entry that skips the L_A80C ink-only mask (still
applies the L_A843 mask).  FlashViewAttributes uses it so that the cyan paper of the
energy-bomb flash shows without the cloak.  Input: L = attribute."""),

    # ------------------------------------------------------- Torus jump drive
    0x9965: ('TorusJumpDustFlag', 'verified', """
Not message text: a flag byte at the end of the message table.  Set to 1 by
HandleTorusJumpKey ($99A0) after a jump; UpdateDust clears it and then runs
three dust passes with speed values $1E, $10 and $10 (a dust streak).
Evidence: only $99A0 and $9E7A write it, only $9E74 reads it; forced-jump
test (tools/check_routines.py dust/torus-jump) sees it at 1 on the next UpdateDust."""),
    0x9966: ('HandleTorusJumpKey', 'verified', """
Torus jump drive (J key): test and clear key flag bit 6 of L_FC10 (cleared
even when the jump is refused; the other key bits are kept).  The jump is
refused near the sun (L_88DC = 1) or the planet (L_88DD = 1), while L_DA0F is
set (UpdateObjects found an active slot without +$26 bit 3) and while the
station is active (L_7078 = 0).  Otherwise: cancel the mission Asp
encounter (L_DA0C = 0), free slots 1..7 and clear the station's
hostility (L_7C14; the LD IX before it is redundant), rotate
AlternatingBits right and, when its old value was $AA, set L_DA0E = 1
so that the next UpdateObjects starts a random encounter; set
TorusJumpDustFlag = 1 and move the sun (L_7065), the planet (L_706E)
and station slot 0 by $2000 units along z with ApplyJumpShift.
AlternatingBits only ever holds $55 or $AA, and the rear/side-view dust
respawns rotate it too, so roughly every second jump requests an encounter.
Input: none.  Output: none.  Clobbers: AF, BC, DE, HL, IX.
Evidence: manual (docs/info/Elite.txt) lists J = Torus jump drive; runtime:
pressing J during flight reaches $9973 (bit 6 set) exactly while J is held;
tools/check_routines.py dust/torus-jump (shift, e.g. L_706E +8..+6 $015ADC ->
$013ADC, L_7065 $85AE16 -> $85CE16; each inhibitor; jump streak) and
dust/p4-torus-jump-effects (key byte, freed slots, Asp state, encounter request)."""),
    0x99B5: ('ApplyJumpShift', 'verified', """
Move the sign-magnitude 24-bit z coordinate at IX+6 (low), IX+7, IX+8 (bit 7 =
sign) by $2000 towards negative, as if the player moved $2000 units forward:
a positive value loses $2000 and becomes negative ($2000 - value) when it
would cross zero; a negative value gains $2000 in magnitude and saturates to
+$7FFFFF (sign clear) on overflow.
Input: IX = object slot or L_7065/L_706E (both formats keep z at +6..+8,
InstanceZ).  Clobbers: AF, BC, DE, HL.
Evidence: tools/check_routines.py dust/torus-jump (2000 random values and the
edge cases against this model)."""),

    # ------------------------------------------------------- dust workspace
    0x99F7: ('DustRollRate', 'verified', """
Dust copy of the roll value L_7042 (bit 7 = sign, magnitude 0..15) for the
current pass; UpdateDust strips the sign into DustFlags bit 4.  For the left
and right views it is swapped with DustPitchRate.  Nonzero rotates every
particle about the view centre (ApplyDustRoll).
Evidence: L_7042 changes with the N/M keys in 48K runs; roll test."""),
    0x99F8: ('DustPitchRate', 'verified', """
Dust copy of the pitch value L_7043 (bit 7 = sign, magnitude 0..15); sign
moved to DustFlags bit 3; swapped with DustRollRate in the side views.
Nonzero moves particles vertically (ApplyDustPitch) and selects the edge
respawn patterns.  Evidence: L_7043 changes with S/X; pitch test."""),
    0x99F9: ('DustPitchScale', 'verified', """
Pitch perspective factor ($80 = 1.0): high byte of 2*($4000 +/- Y*pitch)
computed by ApplyDustPitch; Z is multiplied and X, Y are divided by it."""),
    0x99FA: ('DustSideViewFlag', 'verified', """
1 while the current pass is for the left or right view (set by L_A1EA),
0 for front/rear; NextDustParticle then goes to MoveDustSideways."""),
    0x99FB: ('DustRecordPointer', 'verified', """
Address of the particle record being processed (starts at L_A46C, advanced
by 5 per particle by the store and respawn paths)."""),
    0x99FD: ('DustStep', 'verified', """
Depth step per pass: speed L_7044 / 2 + 1."""),
    0x99FE: ('DustXFraction', 'verified', """
Low (fraction) byte of the current particle's X, record byte 3.  Read as the
word DustXFraction/DustX (8.8 fixed point)."""),
    0x99FF: ('DustX', 'verified', """
Current particle's X magnitude (record byte 0 bits 0..6; sign in DustFlags
bit 7).  The particle leaves the view at 120 ($78)."""),
    0x9A00: ('DustYFraction', 'verified', """
Low (fraction) byte of the current particle's Y, record byte 4."""),
    0x9A01: ('DustY', 'verified', """
Current particle's Y magnitude (record byte 1 bits 0..6; sign in DustFlags
bit 6).  Plotted only below 63 ($3F); positive Y is above the centre."""),
    0x9A02: ('DustZ', 'verified', """
Current particle's depth, record byte 2 (unsigned)."""),
    0x9A03: ('DustLastScreenId', 'verified', """
CurrentScreenId of the previous dust pass; a change calls L_A44C, which
swaps record bytes 0 and 1 (X and Y) of every particle."""),
    0x9A04: ('DustRemaining', 'verified', """
Particles left in this pass: 16, or 4 while L_7061 is nonzero (the
hyperspace jump ended in witchspace, between systems)."""),
    0x9A05: ('DustPlotPointer', 'verified', """
Next free entry of DustPlotList (3 bytes per plotted particle)."""),
    0x9A07: ('DustFlags', 'verified', """
Dust sign/direction flags: bit 7 = X negative, bit 6 = Y negative,
bit 5 = reverse depth motion (rear view; also toggled for the right view),
bit 4 = roll sign, bit 3 = pitch sign.  Bits 7/6 are taken from each record,
bits 5..3 are set once per pass (L_A1DC/L_A1EA flip and swap them)."""),
    0x9A08: ('DustPlotCount', 'verified', """
Number of entries written to DustPlotList in this pass."""),
    0x9A09: ('AlternatingBits', 'verified', """
Rotating bit pattern, initially $55 (alternate 0/1 bits), so it only ever
holds $55 or $AA.  RLCA at L_A3C4 and L_A428 alternates the two edge-respawn
patterns; RRCA in HandleTorusJumpKey makes a jump set L_DA0E when the old
value was $AA.  The three rotations share the byte, so neither sequence is
strictly alternating.
Evidence: tools/check_routines.py dust/p4-torus-jump-effects."""),
    0x9A0A: ('DustPlotList', 'verified', """
Plot list: up to 16 entries of (view-buffer address low, high, pixel mask),
filled by StoreAndPlotDust and XORed into the buffer by XorPlotDustList.
Only entries written in the same pass are read, so the initial bytes (text
fragments, apparently left over from a dictionary build) are never used."""),
    0x9A3A: (None, 'inferred', """
12 bytes after DustPlotList ($9A3A..$9A45) with no static or runtime access
in any recorded 48K scenario.  Their text-like content continues the leftover
dictionary fragment of the plot list's initial bytes.  Plausibly unused.
fuelfix=yes uses them for FuelPriceStore and FuelGaugeUpdate, which falls into
PrepareShipForLaunch."""),

    # ------------------------------------------------- launch / gauges
    0x9A46: ('PrepareShipForLaunch', 'verified', """
Reset the ship systems for a launch: DrawMissileIndicators,
L_D563 (drop queued flight messages), clear L_A80F (missile
disarmed), L_704E, L_704C and L_707E, set the gauge values
L_7046, L_7048, L_7050 and the four energy banks
L_7054..L_705A to $A0 (160, the full scale of these bars), then fall
into ColourInstrumentBlocks.  Only the value bytes are written; the drawn copy that
precedes each gauge value is left, so L_7859 redraws the changed bars.
Input: none.  Clobbers: AF, BC, DE, HL and what DrawMissileIndicators uses.
Evidence: called by the launch sequence L_7B68 after it sets view 0;
tools/check_routines.py controls/p4-launch-reset."""),
    0x9A6E: ('ColourInstrumentBlocks', 'verified', """
Colour the two instrument blocks (attribute columns 3..7 and 24..28 of rows
17..23, 70 cells) with $17 (white ink on red paper), or $1F (white on magenta)
when L_A84B (escape pod, commander +$35) is nonzero.  Writes VRAM $5A23..
for the cockpit views (CurrentScreenId < 4), otherwise the saved cockpit
attribute buffer $5B23.., which the cockpit restore copies back later.  Also
called by L_A61A when a fitted item is destroyed, so the colour follows
L_A84B again.  Clobbers: AF, BC, DE, HL.
Evidence: docs/GRAPHICS.md and docs/evidence/attribute-runtime.json;
tools/check_routines.py controls/p4-launch-reset (both colours, both targets,
exactly 70 cells)."""),
    0x9A8F: ('FillAttributeBlock', 'verified', """
Fill 7 rows of 5 attribute cells with C, starting at HL; DE must be 27 (the
row stride 32 minus 5).  Output: HL after the block.  Clobbers: B, HL."""),

    # --------------------------------------------------------- stardust
    0x9E74: ('UpdateDust', 'verified', """
Per-frame stardust update for the cockpit views.  Normally one pass
(MoveAndPlotDust).  When TorusJumpDustFlag is 1 it is cleared and three
passes run with L_7044 = $1E, then $10, then $10 again (L_707F reloads the
real speed in the next frame).
Input: CurrentScreenId 0..3 (front/rear/left/right), L_7042/L_7043/L_7044.
Clobbers: AF, BC, DE, HL (and L_7044 after a jump); IX, IY and the alternate
registers are not used.
Callers: the flight frame L_72FD after the view buffer is cleared and before
BlitViewBitmap, the game-over loop L_7356 and the launch tunnel loops
L_7BD3/L_7BE5.
Evidence: dust model test (tools/check_routines.py dust/stardust-update,
dust/launch-dust-respawn); register use in dust/p4-dust-roll-pitch-side-model."""),
    0x9E8D: ('MoveAndPlotDust', 'verified', """
One dust pass over all particle records at L_A46C: copy speed and roll/pitch
(DustStep, DustRollRate, DustPitchRate, sign bits to DustFlags), set the
count (16, or 4 when L_7061 <> 0), call L_A44C if the view changed, then for
each record move it (front/rear: MoveDustInDepth; sides: MoveDustSideways),
apply roll and pitch, store it, collect visible pixels in DustPlotList and
finally XOR them into the view bitmap buffer.  Particles that leave the
view are re-created by RespawnDust and not plotted in that pass.
Verified for the front view against a Python model: X += X*dz/Z,
Y += Y*dz/Z (8.8 fixed point, dz = DustStep), Z -= dz, exact record bytes
and pixels.  Rear view: Z += dz, X/Y shrink."""),
    0x9F1F: ('MoveDustInDepth', 'verified', """
Front/rear motion of the current particle: delta = (X:Xfrac * dz / 256) *
256 / Z via MultiplyByLowBits (5-bit dz) and DivideToFractionD or
DivideWordToFixed; X:Xfrac += delta (front) or -= delta (DustFlags bit 5);
the same for Y; then Z -= dz (front) or += dz.  Leaving the view (X >= 120,
Y >= 120, crossing zero, Z carry/zero) goes to RespawnDust.
Quirks kept from the original: the low byte of each product is accumulated
into the fraction byte, and the Y path always adds 1 to the product high
byte (the X path adds the carry)."""),
    0x9FFA: ('ApplyDustRoll', 'verified', """
Roll the current particle about the view centre when DustRollRate <> 0
(r = rate 1..15, sign in DustFlags bit 4): X moves by the step
(|Y| * r) >> 7, then Y by the step (|new X| * r) >> 7.  In signed terms
x' = x - y*r/128 and y' = y + x'*r/128 (truncated steps), a pair of shears
that keeps the radius within about 3% (roll test).  |X| grows when the X, Y
and roll sign bits have odd parity and |Y| grows when they have even parity;
a shrinking magnitude that crosses zero is negated with its sign flipped
(NegateDustX/Y), and a growing X or Y that reaches 120 respawns.  A zero step
leaves that coordinate unchanged.  Continues with ApplyDustPitch.
Evidence: tools/check_routines.py dust/p4-dust-roll-pitch-side-model (exact
records for random particles and rates); dust/stardust-update (radius)."""),
    0xA085: ('ScaleByRate', 'verified', """
A = (A * (C AND 15)) >> 7, i.e. bits 7..14 of the product; Z set if zero,
carry clear.  Input: A = magnitude, C = rate.  Output: B = 0.
Clobbers: C, D, E, HL.  Computes the steps of the roll shears in ApplyDustRoll."""),
    0xA090: (None, 'verified', """
ApplyDustRoll continued (reached only by jumps from L_A048..L_A078): |Y| grows
by the roll step in L and respawns at 120 or more; L_A099 stores the new Y and
falls into ApplyDustPitch."""),
    0xA09C: ('ApplyDustPitch', 'verified', """
Pitch the current particle when DustPitchRate <> 0 (p = rate, sign in
DustFlags bit 3; y = signed Y): DustPitchScale s = high byte of
2*($4000 - y*p), i.e. 128 - y*p/128 ($80 = 1.0).  Then Z = Z*s/128 (respawn
when 2*Z*s overflows 16 bits or is zero); X = (X/2)*256/s, respawning when it
becomes 0 or >= 128; Y = (|y + p|/2)*256/s, the Y sign flipping when y + p
crosses zero and again when this quotient is 0; Y >= 64 respawns.  So a
pitch shifts particles vertically by p and scales them by 128/s.  Without
roll StoreAndPlotDust then also respawns Y >= 63.
Evidence: tools/check_routines.py dust/p4-dust-roll-pitch-side-model (exact
records); pitch cases of dust/stardust-update."""),
    0xA13D: ('StoreAndPlotDust', 'verified', """
Without roll a particle with Y >= 63 respawns; with roll it is kept (it may
turn back into the view) but not plotted.  If Y < 63 its pixel (address and
mask from GetDustPixelAddress) is appended to DustPlotList.  Then the record
(X|sign, Y|sign, Z, Xfrac, Yfrac) is written back at DustRecordPointer,
which advances by 5, and NextDustParticle follows."""),
    0xA193: ('NextDustParticle', 'verified', """
Decrement DustRemaining; at zero XOR-plot the list (XorPlotDustList, which
returns to the caller of MoveAndPlotDust).  Otherwise load the next record
into DustX/DustY/DustZ/fractions, set DustFlags bits 7/6 from its signs
(bits 5..3 kept) and continue at MoveDustSideways (side views) or
MoveDustInDepth."""),
    0xA1DC: (None, 'verified', """
Non-front views (A = CurrentScreenId, nonzero).  Rear (1): flip DustFlags
bits 5..3 (reverse depth motion and both rotation signs), then
MoveDustInDepth.  Left (2) / right (3): see L_A1EA."""),
    0xA1EA: (None, 'verified', """
Side views: DustSideViewFlag = 1; left flips the roll sign, right flips the
pitch sign; then bits 4 and 3 of DustFlags are exchanged and DustRollRate /
DustPitchRate swapped; the right view also flips bit 5 (direction).  The
exchange fits the geometry: looking sideways, the forward (roll) axis lies
across the screen and the pitch axis along the line of sight."""),
    0xA235: ('MoveDustSideways', 'verified', """
Side-view motion: respawn if DustStep >= Z; otherwise
step = (DustStep*256/Z)/2 + 1 (nearer particles move faster) and X moves by
it: |X| grows when DustFlags bit 5 XOR the X sign is 1, otherwise it shrinks
and crossing zero flips the X sign; a growing X >= 119 respawns.  In signed
terms x' = x - step with bit 5 clear (left view) and x + step with bit 5 set
(right view).  Z is not changed in the side views.  Continues with
ApplyDustRoll.
Evidence: tools/check_routines.py dust/p4-dust-roll-pitch-side-model."""),
    0xA272: ('XorPlotDustList', 'verified', """
XOR every DustPlotList entry (address, mask) into memory, DustPlotCount
entries.  Output: B = 0, HL after the last entry; with no entries it returns
at once with A = 0.  Clobbers: AF, B, C, DE, HL."""),
    0xA287: ('NegateDustY', 'verified', """
A = -A and toggle DustFlags bit 6 (Y sign).  Called when a magnitude
subtraction borrowed: the result is the new magnitude on the other side of
zero.  Clobbers: B."""),
    0xA294: ('NegateDustX', 'verified', """
A = -A and toggle DustFlags bit 7 (X sign), like NegateDustY.  Clobbers: B."""),
    0xA2A1: ('MultiplyByLowBits', 'verified', """
HL = A * (C mod 2^B): shift-and-add over the low B bits of C.
Input: A, C, B = bit count (4, 5 or 8 here).  Output: HL.  Clobbers: A, B,
C (rotated), D = 0 on entry then high bits of the shifted A, E, flags.
Evidence: tools/check_routines.py maths/dust-arithmetic checks B = 4, 5, 8 for all A, C."""),
    0xA2B5: ('DivideWordToFixed', 'verified', """
C:D = (A:L) * 256 / B (integer part in C, fraction in D) for A:L < $2000
and a quotient below $4000; larger quotients are not exact.  When the
division leaves no remainder D is NOT written (it keeps the caller's D; the
fraction 0 is then only in A).  MoveDustInDepth enters with D = the dividend's
high byte, so an exact quotient there gets that byte as its fraction.
Falls into DivideToFractionD for the fraction.  Clobbers: A, L, flags.
Evidence: random cases in tools/check_routines.py maths/dust-arithmetic."""),
    0xA2DB: ('DivideToFractionD', 'verified', """
D = A * 256 / B (8 quotient bits, $FE sentinel) for A < B.  Clobbers: A.
Evidence: all A < B checked (tools/check_routines.py maths/dust-arithmetic).
L_7AB9 is the same algorithm with the result in C."""),
    0xA2EF: ('GetDustPixelAddress', 'verified', """
View-buffer address and pixel mask of the current particle: column
$80 +/- DustX, row $3F -/+ DustY (positive Y up).  Output: DE = address
in the 256x128 view bitmap buffer (Spectrum screen layout, lower half
selected by the Y sign), C = A = pixel mask.  Clobbers: B (0), H = row,
L = column.
Quirk: a negative zero Y maps to row 127 instead of 63.
Evidence: dust model test compares every plotted pixel."""),
    0xA334: ('RespawnDust', 'verified', """
Re-create the current particle with the dust random generator L_A465 (state
in HL, saved in L_7063), writing bytes 0..2 of the record at
DustRecordPointer (the fraction bytes keep their old values):
  front, no pitch: X = rnd AND $BF, Y = rnd AND $9F, Z = $80 + rnd AND $7F;
  front, pitching: X = rnd AND $F8, Y = rnd AND $3F with sign opposite to
    the pitch sign bit;
  rear and side views: edge positions (L_A38D).
Then NextDustParticle; the respawned particle is not plotted this pass."""),
    0xA347: ('RespawnDustFront', 'verified', """
Front-view respawn entry, also CALLed by L_7AA2 for each of the 16 records
(DE = record, HL = random state) after L_7A88 has patched the two mask
operands below to $83 and the JP at DustRespawnExit to RET: every particle
then starts within 3 units of the centre with Z >= $80 (test confirmed).
Output (patched call): DE advanced by 5, HL = new random state."""),
    0xA38D: (None, 'verified', """
Respawn for the rear view (id 1) and the side views (L_A402).  Rear: alternating with
AlternatingBits, either X at the left/right edge (|X| = $77, random sign) or
Y at the top/bottom edge (from the patched AND/OR at L_A3FA/L_A3FC), with
Z = rnd OR (L_A3E1 operand: $80 when pitching)."""),
    0xA3E2: ('StoreRespawnedDust', 'verified', """
Store the new Z byte, step DE past the two fraction bytes, save
DustRecordPointer and the random state L_7063, then exit (DustRespawnExit).
Also entered from the side-view respawn at $A426."""),
    0xA3ED: ('DustRespawnExit', 'verified', """
SELF-MODIFIED OPCODE: normally JP NextDustParticle ($C3).  L_7A88 writes $C9
(RET) here at $7A92 before calling RespawnDustFront 16 times and restores
$C3 at $7AB5."""),
}

COMMENTS = {
    # CommodityTable records 4..16 (the table starts at $91F2; record i is commodity i,
    # whose name is token $D0+i, see ComputeMarket and the market printers)
    # equipment prices / bomb / attributes
    0x9263: 'key flag bit 5 (W key: energy bomb)',
    0x9266: 'energy bomb fitted? (commander +$36)',
    0x926B: 'no bomb: nothing happens',
    0x926D: 'use the bomb up',
    0x926F: 'bomb request for UpdateObjects',
    0x9272: 'pending sound effects',
    0x9275: 'request bit 0: noise sweep, step -2',
    0x9277: '24 flashes (48 frame waits)',
    0x9279: 'cyan frame, then view colour frame',
    0x9280: '$28: cyan paper, black ink',
    0x9282: 'skip the cloak ink-only mask',
    0x9285: '$0F ends as $07, $0F (cloak) or $02 (L_A843)',
    0x9287: 'paper kept only while cloaked',
    0x928B: 'L_A80C nonzero: keep the whole attribute',
    0x928E: 'otherwise ink bits only (black paper)',
    0x9291: 'L_A843 set: mission colour mask',
    0x9298: 'keep paper and ink bit 1: red or black ink',
    0x929B: 'wait for the frame interrupt before moving SP',
    0x929C: 'restored at the end',
    0x92A0: 'HL = attribute in both bytes for PUSH',
    0x92A1: 'SP = $59FF: end of attribute rows 0..15',
    0x92A4: '16 attribute rows',
    0x92A6: '15 words = columns 1..30',
    0x92A8: 'two cells per PUSH, downwards',
    0x92AB: 'skip column 0 here, column 31 of the row above',
    0x92B0: 'restore SP',
    # Torus jump
    0x9969: 'key flag bit 6 = J (Torus jump drive)',
    0x996C: 'consume the key',
    0x996E: 'cleared even when the jump is refused',
    0x9972: 'J not pressed',
    0x9973: 'refused near the sun',
    0x9978: 'refused near the planet',
    0x997D: 'refused while L_DA0F is set',
    0x9982: 'station active: refused',
    0x9988: 'cancel the mission Asp encounter',
    0x998B: 'redundant: ResetShipSlots sets IX',
    0x998F: 'free slots 1..7, clear station hostility',
    0x9992: 'always $55 or $AA',
    0x9995: 'carry = old bit 0',
    0x9996: 'dust respawns rotate it too',
    0x9999: 'A = 1 for both stores below',
    0x999B: 'was $55: no encounter request',
    0x999D: 'was $AA: request an encounter',
    0x99A0: 'UpdateDust runs the three-pass jump streak',
    0x99A3: 'sun position (x, y, z triples)',
    0x99A7: 'sun z -= $2000',
    0x99AA: 'planet position, same format',
    0x99AE: 'planet z -= $2000',
    0x99B1: 'station slot 0 (fall-through call)',
    0x99B5: 'BC = $20 in the middle byte = $2000',
    0x99B8: 'H = z high byte with sign (+8)',
    0x99BB: 'L = z middle byte (+7)',
    0x99BE: 'D = old middle byte for the crossing case',
    0x99BF: 'sign bit',
    0x99C1: 'negative: the magnitude grows',
    0x99C4: 'positive: magnitude - $2000',
    0x99C6: 'positive value would cross zero',
    0x99CA: 'magnitude + $2000, sign kept in bit 15',
    0x99CB: 'negative magnitude overflow',
    0x99CD: 'store high byte and sign',
    0x99D4: 'new magnitude = $2000 - old value, sign set',
    0x99D7: 'DE = old value (its high byte was 0)',
    0x99DD: 'negative, high magnitude byte 0',
    0x99E9: '+$7FFFFF: sign becomes positive',
    # launch reset and gauge colours
    0x9A46: 'missile indicators from MissileCount',
    0x9A49: 'drop queued flight messages',
    0x9A4D: 'missile disarmed',
    0x9A50: 'laser cooled down',
    0x9A53: 'cabin temperature zero',
    0x9A56: 'docking computer off',
    0x9A59: '$A0 = 160: full scale of the gauge bars',
    0x9A5B: 'full fore shield',
    0x9A5E: 'full aft shield',
    0x9A61: 'altitude bar full (far from the planet)',
    0x9A64: 'energy banks 1..4: every second byte',
    0x9A67: '4 banks',
    0x9A69: 'fill one bank (its drawn copy is kept)',
    0x9A6E: 'attribute row 17, column 3 (VRAM)',
    0x9A71: 'views 0..3 show these cells',
    0x9A74: 'view id >= 4: write the $5B00 save buffer instead',
    0x9A78: 'H = $5B: saved cockpit attributes',
    0x9A79: '$17: white ink on red paper',
    0x9A7B: 'escape pod fitted? (commander +$35)',
    0x9A81: '$1F: white ink on magenta paper',
    0x9A83: 'row stride 32 - 5',
    0x9A86: 'keep the block start',
    0x9A87: 'left block: columns 3..7, rows 17..23',
    0x9A8C: '+21: column 24 (right block)',
    0x9A8F: '7 attribute rows',
    0x9A92: '5 cells per row',
    0x9A99: 'next row',
    # stardust: entry / pass setup
    0x9E74: 'set after a Torus jump',
    0x9E77: 'zero only when the flag was 1',
    0x9E78: 'normal frame: one pass',
    0x9E7A: 'A = 0: clear the flag',
    0x9E7D: 'jump streak: fast pass',
    0x9E7F: 'until ReadFlightControls restores it',
    0x9E82: 'first streak pass',
    0x9E85: 'second pass, then the normal one',
    0x9E8A: 'then fall into the third pass',
    0x9E8E: 'no pixels collected yet',
    0x9E91: 'front/rear until L_A1EA sets it',
    0x9E94: 'speed',
    0x9E9A: 'DustStep = speed/2 + 1',
    0x9E9D: 'roll and pitch copies (L_7042, L_7043)',
    0x9EA0: 'DustRollRate and DustPitchRate',
    0x9EA3: '16 particles',
    0x9EA8: 'witchspace (between systems)?',
    0x9EAE: 'only 4 particles',
    0x9EB3: 'view id of the previous pass',
    0x9EB7: 'view id of this pass',
    0x9EBB: 'remember the current view',
    0x9EBE: 'view changed: swap X/Y bytes of every record',
    0x9EC1: 'empty plot list',
    0x9EC4: 'plot pointer to the list start',
    0x9EC7: 'B collects the DustFlags bits',
    0x9EC9: 'first particle record',
    0x9ECC: 'later records: NextDustParticle',
    0x9ED0: 'byte 0: X, bit 7 = sign',
    0x9ED5: 'magnitude only',
    0x9ED7: 'X sign',
    0x9EDD: 'byte 1: Y, bit 7 = sign',
    0x9EE4: 'Y sign',
    0x9EEA: 'byte 2: depth Z',
    0x9EEF: 'byte 3: X fraction',
    0x9EF4: 'byte 4: Y fraction',
    0x9EF8: 'roll: magnitude, sign to bit 4',
    0x9F01: 'roll sign',
    0x9F03: 'keep the magnitude only',
    0x9F06: 'pitch: magnitude, sign to bit 3',
    0x9F0F: 'pitch sign',
    0x9F11: 'keep the magnitude only',
    0x9F15: 'bit 5 = 0 here: forward depth motion',
    0x9F18: 'front view continues below; others at L_A1DC',
    0x9F1C: 'rear/side: flags adjusted first',
    # MoveDustInDepth
    0x9F1F: 'C = dz',
    0x9F23: 'A = X integer part',
    0x9F26: '5-bit dz multiply',
    0x9F28: 'HL = X * dz',
    0x9F30: 'X fraction * dz',
    0x9F38: 'DE = X * dz',
    0x9F3D: 'low product byte accumulated into the fraction',
    0x9F40: 'fraction product high byte + carry',
    0x9F45: 'DE = X:Xfrac * dz / 256',
    0x9F49: 'Z is the divisor',
    0x9F4F: 'dividend >= 256: full division',
    0x9F53: 'dividend >= Z: full division',
    0x9F55: 'small: fraction only',
    0x9F58: 'integer part 0',
    0x9F5E: 'C:D = DE*256/Z; exact: D unchanged',
    0x9F61: 'B = integer part',
    0x9F62: 'BC = delta X (8.8) = X * dz / Z',
    0x9F66: 'bit 5: rear view moves inwards',
    0x9F68: 'HL = X:Xfrac (8.8)',
    0x9F6D: 'front: X moves outwards',
    0x9F6F: 'X >= 120: left the view',
    0x9F76: 'rear: X moves towards the centre',
    0x9F78: 'crossed zero: respawn',
    0x9F7A: 'reached the centre: respawn',
    0x9F7C: 'store the new X:Xfrac',
    0x9F7F: 'the same for Y',
    0x9F88: 'HL = Y * dz',
    0x9F95: 'Y fraction * dz',
    0x9F9D: 'low product byte accumulated into the fraction',
    0x9FA1: 'Y path always adds 1 (no carry test)',
    0x9FA3: 'DE = Y:Yfrac * dz / 256 (+1)',
    0x9FA7: 'Z is the divisor',
    0x9FB3: 'small: fraction only',
    0x9FBC: 'C:D = DE*256/Z; exact: D unchanged',
    0x9FC0: 'BC = delta Y (8.8) = Y * dz / Z',
    0x9FC4: 'bit 5: rear view moves inwards',
    0x9FC6: 'HL = Y:Yfrac (8.8)',
    0x9FCB: 'front: Y moves outwards',
    0x9FCD: 'Y >= 120: left the view',
    0x9FD3: 'left the view: create a new particle',
    0x9FD7: 'rear: Y moves towards the centre',
    0x9FD9: 'crossed zero: respawn',
    0x9FDB: 'store the new Y:Yfrac',
    0x9FE5: 'rear view: Z grows',
    0x9FE9: 'front: Z -= dz',
    0x9FF2: 'rear: Z += dz',
    0x9FF3: 'Z crossed zero or 256: respawn',
    0x9FF7: 'new depth',
    # roll / pitch
    0x9FFE: 'no roll: pitch only',
    0xA002: 'X step from |Y| * roll',
    0xA005: 'B is reloaded by ScaleByRate',
    0xA007: 'L = |Y| * rate / 128',
    0xA00A: 'zero step: X unchanged',
    0xA00D: 'choose add/subtract from X, Y and roll signs',
    0xA034: '|X| grows (sign parity odd)',
    0xA038: 'X >= 120: respawn',
    0xA03E: '|X| shrinks (sign parity even)',
    0xA042: 'crossed zero: negate, flip X sign',
    0xA045: 'x = x - y*roll/128 (signed)',
    0xA048: 'second shear: Y from the new X',
    0xA04C: 'Y step from the new |X|',
    0xA051: 'L = |X| * rate / 128',
    0xA054: 'zero step: Y unchanged',
    0xA057: 'add/subtract from the sign bits',
    0xA07C: '|Y| shrinks (sign parity odd)',
    0xA080: 'crossed zero: negate, flip Y sign',
    0xA085: 'low 4 bits of the rate',
    0xA087: 'HL = A * rate',
    0xA08A: 'A = HL >> 7',
    0xA08E: 'Z when zero, carry clear',
    0xA090: '|Y| grows (sign parity even)',
    0xA094: 'Y >= 120: respawn',
    0xA099: 'y = y + x*roll/128 (signed)',
    0xA0A0: 'no pitch: store the particle',
    0xA0A3: 'C = pitch rate',
    0xA0A4: 'A = |Y|',
    0xA0A7: 'overwritten by the product below',
    0xA0AA: 'HL = |Y| * rate',
    0xA0AE: '$4000 = 1.0 in this fixed-point product (number, not screen)',
    0xA0B1: 'Y sign = pitch sign: subtract',
    0xA0C2: 'signs differ: $4000 + |Y|*rate',
    0xA0C6: 'signs equal: $4000 - |Y|*rate',
    0xA0C8: 'scale = 128 - y*pitch/128 (signed)',
    0xA0CA: 'DustPitchScale',
    0xA0D1: '8-bit multiplier',
    0xA0D4: 'Z * scale',
    0xA0D8: 'HL = 2 * Z * scale',
    0xA0DA: 'Z overflow: respawn',
    0xA0DC: 'Z zero: respawn',
    0xA0DF: 'Z = Z * scale / 128',
    0xA0E2: 'divisor: the scale',
    0xA0E9: 'X/2 * 256 / scale',
    0xA0F0: 'X became zero: respawn',
    0xA0F4: 'X >= 128: respawn',
    0xA0F6: 'X = X * 128 / scale',
    0xA0F9: 'B = pitch rate',
    0xA101: 'Y sign = pitch sign: add',
    0xA112: 'signs differ: |Y| - rate',
    0xA114: 'crossed zero: negate, flip Y sign',
    0xA119: 'shared respawn exit',
    0xA11C: 'signs equal: |Y| + rate',
    0xA11E: 'halve, then * 256 / scale',
    0xA121: 'divisor: the scale',
    0xA126: 'D = (y + pitch) * 128 / scale',
    0xA130: 'quotient zero: flip the Y sign',
    0xA136: 'Y >= 64: respawn',
    0xA13A: 'new Y magnitude',
    0xA13D: 'roll active?',
    0xA141: 'LD keeps the Z flag of the roll test',
    0xA144: 'rolling: keep off-view particles',
    0xA146: 'no roll: Y >= 63 respawns',
    0xA14A: 'Y >= 63: keep the record but do not plot',
    0xA14E: 'DE = buffer address, C = mask',
    0xA151: 'next free plot list entry',
    0xA154: 'plot list entry: address low, high, mask',
    0xA15A: 'advance the plot list',
    0xA161: 'count the entry',
    0xA164: 'write the record back',
    0xA16A: 'B = sign bits',
    # store / next
    0xA172: 'X sign into record byte 0',
    0xA17D: 'Y sign into record byte 1',
    0xA181: 'byte 2: Z',
    0xA186: 'byte 3: X fraction',
    0xA18B: 'byte 4: Y fraction',
    0xA190: 'next record',
    0xA196: 'last particle done?',
    0xA197: 'yes: plot the list and return',
    0xA1A0: 'keep direction and rotation sign bits',
    0xA1A3: 'record of the next particle',
    0xA1AE: 'X sign',
    0xA1BB: 'Y sign',
    0xA1C1: 'byte 2: Z',
    0xA1C6: 'byte 3: X fraction',
    0xA1CB: 'byte 4: Y fraction',
    0xA1D0: 'new X/Y signs, pass bits kept',
    0xA1D3: 'side views continue at MoveDustSideways',
    0xA1DA: 'front and rear views',
    0xA1DD: 'views 2 and 3: side views',
    0xA1E2: 'rear: reverse depth motion and rotation signs',
    0xA1EB: 'side view: horizontal motion',
    0xA1F1: 'view 3: right',
    0xA1F6: 'left: flip the roll sign',
    0xA1FB: 'old bit 4 to bit 3',
    0xA201: 'old bit 3 to bit 4',
    0xA205: 'exchange bits 4 and 3',
    0xA210: 'right: flip the pitch sign',
    0xA222: 'right: reverse the sideways direction',
    0xA227: 'side views exchange roll and pitch',
    0xA22E: 'swap the roll and pitch rates',
    0xA23C: 'carry when dz < Z',
    0xA23D: 'also the exit for X >= 119 below (carry clear)',
    0xA240: 'D = dz*256/Z',
    0xA243: 'step = D/2 + 1',
    0xA246: 'bit 5 XOR X sign selects the direction',
    0xA25B: '|X| shrinks',
    0xA25F: 'crossed zero: negate, flip X sign',
    0xA264: '|X| grows',
    0xA268: 'X >= 119: respawn',
    0xA26C: 'new X magnitude',
    0xA26F: 'then roll, pitch and store',
    0xA275: 'entries collected in this pass',
    0xA279: 'nothing to plot',
    0xA27B: 'DE = buffer address',
    0xA27F: 'C = pixel mask',
    0xA281: 'toggle the particle pixel',
    0xA287: 'new magnitude after crossing zero',
    0xA28D: 'flip the Y sign',
    0xA294: 'new magnitude after crossing zero',
    0xA29A: 'flip the X sign',
    # helpers
    0xA2A1: 'D:A = multiplicand',
    0xA2A3: 'product',
    0xA2A7: 'first bit without shifting',
    0xA2A9: 'D:A *= 2',
    0xA2AC: 'next multiplier bit, lowest first',
    0xA2B1: 'HL += D:A',
    0xA2B2: 'B bits',
    0xA2B5: 'A:L <<= 3: dividend bits 12..5 in A',
    0xA2BE: 'quotient sentinel: 6 integer bits',
    0xA2C0: 'first quotient bit',
    0xA2C5: 'next dividend bit into A',
    0xA2C8: 'overflow: subtract',
    0xA2CF: 'sentinel out: integer part done',
    0xA2D3: 'quotient bit 1',
    0xA2D9: 'no remainder: return without writing D',
    0xA2DA: 'exact: C = integer part, A = fraction 0',
    0xA2DB: 'sentinel bit: 8 quotient bits',
    0xA2DD: 'remainder * 2',
    0xA2DE: 'overflow: subtract',
    0xA2E3: 'quotient bit 0',
    0xA2E5: 'sentinel out: 8 bits done',
    0xA2E8: 'quotient bit 1',
    0xA2EF: 'high byte of the view bitmap buffer',
    0xA2F4: 'B = sign flags',
    0xA2FD: 'column = $80 +/- X',
    0xA303: 'X positive: right of the centre',
    0xA306: 'X negative: left',
    0xA308: 'row = $3F -/+ Y',
    0xA30E: 'Y positive: above the centre row',
    0xA311: 'Y negative: below',
    0xA312: 'Y negative: lower half of the buffer',
    0xA315: 'pixel line within the character row',
    0xA31A: 'character row bits into E',
    0xA320: 'column / 8',
    0xA328: 'bit position in the byte',
    0xA32D: 'mask = $80 >> (column AND 7)',
    # respawn and self-modifying code
    0xA334: 'dust random state',
    0xA337: 'record to overwrite',
    0xA33B: 'rear and side views at L_A38D',
    0xA341: 'pitching front view at L_A36E',
    0xA347: 'SMC operand: X mask; $83 by $7A8A, $BF again by $7AAB',
    0xA349: 'SMC: X mask into the AND at L_A358',
    0xA34C: 'SMC operand: Y mask; $83 by $7A8D, $9F again by $7AB0',
    0xA34E: 'SMC: Y mask into the AND at L_A35F',
    0xA352: 'SMC: Y sign OR value 0 (random sign kept)',
    0xA355: 'A = next random byte (state in HL)',
    0xA358: 'SMC operand: $BF, $83 (L_7A88), $F8 pitching ($A375)',
    0xA35A: 'byte 0: X',
    0xA35C: 'random Y byte',
    0xA35F: 'SMC operand: $9F, $83 (L_7A88), $3F pitching ($A370)',
    0xA361: 'SMC operand: 0 ($A352/$A387) or $80 ($A381): Y sign',
    0xA363: 'byte 1: Y',
    0xA365: 'random Z byte',
    0xA368: 'Z = $80..$FF',
    0xA36C: 'store Z, skip the fractions',
    0xA370: 'SMC: Y mask $3F into the AND at L_A35F',
    0xA375: 'SMC: X mask $F8 into the AND at L_A358',
    0xA37B: 'pitch sign selects the half for new particles',
    0xA381: 'SMC: Y forced negative (OR $80 at L_A361)',
    0xA387: 'SMC: Y positive (OR 0 at L_A361)',
    0xA38A: 'generate with the pitching masks',
    0xA38E: 'C = view id - 1: zero for the rear view',
    0xA38F: 'views 2/3: side-view respawn',
    0xA392: 'rear view: pitching?',
    0xA39A: 'SMC: Z OR value $80 at L_A3E0',
    0xA39D: 'pitch sign selects the edge',
    0xA3A5: 'SMC: Y AND mask 0 at L_A3FA',
    0xA3AA: 'SMC: Y OR value $3F at L_A3FC (top edge)',
    0xA3B1: 'SMC: Y OR value $BF at L_A3FC (bottom edge)',
    0xA3B8: 'SMC: Y AND mask $80 at L_A3FA (random sign)',
    0xA3BD: 'SMC: Y OR value $3F at L_A3FC (edge)',
    0xA3C1: 'SMC: Z OR value 0 at L_A3E0',
    0xA3C4: 'alternate the two edge patterns',
    0xA3C7: '$55 <-> $AA; carry = old bit 7',
    0xA3CB: 'top/bottom edge pattern',
    0xA3CD: 'random X sign',
    0xA3D0: '|X| = $77: left/right edge, random sign',
    0xA3D9: 'random Y: sign random, |Y| <= 63',
    0xA3DD: 'random Z',
    0xA3E0: 'SMC operand: $80 ($A39A) or 0 ($A3C1)',
    0xA3E3: 'skip the two fraction bytes',
    0xA3E6: 'next record for NextDustParticle',
    0xA3EA: 'save the dust random state',
    0xA3F3: 'random X',
    0xA3F7: 'Y from the patched AND/OR below',
    0xA3FA: 'SMC operand: $80 ($A3B8) or 0 ($A3A5)',
    0xA3FC: 'SMC operand: $3F ($A3AA/$A3BD) or $BF ($A3B1): Y edge',
}

DATA = {
    # 14 equipment prices x 3 bytes, see EquipmentPriceTable.
    0x9236: (0x9239, 'bytes', 3),       # entry 0 (FUEL), split by the L_9237 label
    0x9239: (0x9260, 'bytes', 3),
    # Dust workspace variables (single bytes and two pointer-valued words,
    # initially zero; 'words' keeps them numeric).
    0x99F7: (0x99FB, 'bytes', 1),
    0x99FB: (0x99FD, 'words', 1),
    0x99FD: (0x9A05, 'bytes', 1),
    0x9A05: (0x9A07, 'words', 1),
    0x9A07: (0x9A0A, 'bytes', 1),
    # Plot list (16 x 3 bytes); initial content is never read.
    0x9A0A: (0x9A3A, 'bytes', 3),
    # Unreferenced bytes after the plot list.
    0x9A3A: (0x9A46, 'bytes', 12),
}

OPERANDS = {
    0xA2EF: 'ViewBitmapBuffer >> 8',      # LD D,$C0: high byte of the view buffer
}

ASSERTS = {
    'r4-view-buffer-4k-aligned': (
        '((FontBitmap-GameImage+GameLoadAddress) & $0FFF) = 0',
        'ViewBitmapBuffer (= FontBitmap): GetDustPixelAddress ORs row bits into its high byte'),
    'r4-dust-plot-list-size': (
        'L_9A3A-DustPlotList = 16*3',
        'DustPlotList holds 16 entries of 3 bytes'),
}
