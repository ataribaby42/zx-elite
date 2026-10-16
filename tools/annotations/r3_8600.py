"""Outline circles, sun/planet proximity, compass, scanner, screen keys and sound ($8600..$91FF).

Evidence: instruction semantics; 48K runtime traces (docs/generated/runtime-xrefs.json); Z80
simulator checks in tools/check_routines.py that run the unmodified reference image with
controlled RAM: circles/outline-arcs, maths/vector-magnitude, scanner/sun-planet-proximity,
scanner/compass, scanner/scanner-contacts, scanner/scanner-background,
scanner/p3-scanner-geometry, input/p3-screen-keys, input/p3-freeze-options,
economy/p3-commodity-table, sound/interrupt-sound-player and sound/synchronous-sound-players."""

SECTIONS = {
    0x8608: ('Outline circle plotting',
             'Outline branches of the circle renderer at L_7D0E (L_7C49 = 1): planet outline in\n'
             'the view buffer, chart circles directly on the screen (limits patched by L_8461).'),
    0x88DC: ('Sun and planet proximity, compass',
             'Distance checks against the sun (L_7065) and planet (L_706E) vectors, collision,\n'
             'temperature/altitude gauges, condition colour and the cockpit compass.'),
    0x8C10: ('3D scanner contacts',
             'Projects every live object slot onto the cockpit scanner, with a saved copy of the\n'
             'clean scanner background in the 624-byte buffer at $5B00.'),
    0x8E95: ('Screen selection keys and freeze-mode options', ''),
    0x902B: ('Sound effects',
             'Beeper effects: an interrupt-driven player for the request bits in L_707D and\n'
             'synchronous players that run a whole effect with interrupts disabled.'),
}

LABELS = {
    # ------------------------------------------------------------------ circles
    0x8608: (None, 'verified', """
Tail of the circle code at L_7F41 (reached by JP) for a circle cut by the left edge
of the view: E is already column 1 of the start row; B = $80 is the pixel at the left
edge (x 8), used once the left side of the outline comes into view.  Then draw the
right-hand arc downwards (L_7C7A) when bit 1 of L_7C3C is set, otherwise upwards (L_7C92).
The arc routines restore AF, so exactly one of the two conditional calls runs.
Evidence: instruction semantics; runtime: executed in flight scenarios;
tools/check_routines.py circles/outline-arcs (circles beyond the left edge)."""),
    0x8616: (None, 'verified', """
Tail of L_7FA5: L = (E AND $E0) OR $1E (column 30 of the row in E: the right clip
column of the view), C = 1 (its rightmost pixel, x 247).  The OR operand is patched by
L_8461 (see the comment there).
Evidence: instruction semantics; exercised by tools/check_routines.py circles/outline-arcs
(circle cut by the right edge)."""),
    0x861F: (None, 'verified', """
Tail of L_8000: B = pixel mask $80 >> A (A = 0..7, bit position from the left), E
= L.
Evidence: instruction semantics (B = $01 rotated right A+1 times)."""),
    0x8629: (None, 'verified', """
Tail of L_801B: C = pixel mask $01 << (A-1) for A = 1..8, B = (L_7C47).
Evidence: instruction semantics (C = $80 rotated left A times)."""),
    0x8635: (None, 'verified', """
Tail of L_8045: E = (L AND $E0) OR $01 (column 1 of the row in L: the left clip
column of the view), C = 1, B = $80.  The OR operand is patched by L_8461.
Evidence: instruction semantics; exercised by tools/check_routines.py circles/outline-arcs
(large circles)."""),
    0x8640: (None, 'verified', """
Circle start address above a row: HL = address of pixel (x = 247, y = A) from the
ROM routine PIXEL-ADD ($22B0, y counted from the bottom, so screen row 175-A), mapped into
the view buffer by SET 7,H, then moved up B rows (stops early when it would leave the top
of the buffer).  This is the outline-mode partner of FillViewRowsUp: FillCircleRowsUp jumps
here when L_7C49 = 1, so the rows that a filled disc would cover are skipped without
drawing anything.
Input: A = y, B = rows.  Output: HL.  AF and BC preserved.
SMC: the x operand ($F7), SET 7,H and the CP $C0 limit are patched by L_8461 for drawing
directly to the screen (x 255, two NOPs, no top limit).
Evidence: instruction semantics; exercised by tools/check_routines.py circles/outline-arcs
(large circle cases)."""),
    0x866E: (None, 'verified', """
As L_8640, but moves down B rows (INC H) and stops at the end of the view buffer
($D0xx).  Outline-mode partner of FillViewRowsDown (entered from FillCircleRowsDown).
Input: A = y, B = rows.  Output: HL.  AF and BC preserved.  SMC operands as in L_8640.
Evidence: instruction semantics; exercised by tools/check_routines.py circles/outline-arcs
(centre far below the view)."""),
    0x869C: ('DrawCircleLeftArc', 'verified', """
Plot one vertical half of the LEFT side of a circle outline (used when the right
side is off the view): one pixel per step at column byte E with mask B, moving outwards
with RRC B/INC E, row by row up (L_7C48 = 0, DEC H) or down (L_7C48 = 1, INC H).  The
midpoint error term and counters are in the alternate registers (HL', DE', BC'); when C'
reaches A' the arc continues in the two-sided loop (L_878F/L_87D1).  Character-row
crossing and clipping go through L_8430/L_8445; exits restore SP from L_7C43 (abort path)
and finish with POP AF/RET, so AF of the caller entry (L_7C4B, L_7C63) is restored.
Alternate registers: HL' = error term (negative: stay in this column), E' = y (D' = 0),
C' = -x (B' = $FF, so BC' is -x as a word), A' = the C' value at which the other side of
the circle enters the view.  A row step adds 2y+1 to HL'; an x step adds -(2x-1).
While HL' is negative after a row step the arc is steep (one pixel per row, L_86B4);
once an x step leaves it non-negative the arc is shallow (L_8709: one pixel per x step,
a row step only when HL' turns negative).
Entered by JP from L_7C4B/L_7C63 when L_7C49 = 1 (outline mode).
SMC: the start-row limits LD A,$BF/$CF are patched by L_8461.
Evidence: tools/check_routines.py circles/outline-arcs draws circles of radius 9..200 with the
centre near the right edge: all plotted pixels lie within 1-2 pixels of the requested
circle, clipped to view rows 0..127."""),
    0x8740: ('DrawCirclePairedArcs', 'verified', """
Plot one vertical half of a circle outline with both sides visible: left point at
byte E with mask B (moves out with RRC B/INC E), right point at byte L with mask C (RLC
C/DEC L), row by row up (L_7C48 = 0) or down (L_7C48 = 1).  Returns at once when E >= L.
Same alternate-register midpoint error as DrawCircleLeftArc; the arc ends when the two
sides meet (L_87F4/L_8808/L_8819 fill the last byte) or are clipped.
In the steep part the arc simply ends when both points reach the same byte; in the shallow
part (L_87BB) the shared byte is filled between the two points, and when x reaches 0 the
two neighbouring bytes are filled up to the lit pixels, so the outline is closed by a short
horizontal run.
Entered by JP from L_7CA9/L_7CC1 (L_7C49 = 1).
SMC: LD A,$BF/$CF start-row limits patched by L_8461.
Evidence: tools/check_routines.py circles/outline-arcs (centred and vertically clipped
circles use this routine)."""),
    0x878F: (None, 'verified', """
Two-sided midpoint loop continuation; also entered from DrawCircleLeftArc (L_86F4)
and DrawCircleRightArc (L_8892) when the second side comes into view.
Evidence: control flow."""),
    0x87D1: (None, 'verified', """
Two-sided loop, horizontal-step part; also entered from L_86F8 and L_8896.
Evidence: control flow."""),
    0x8816: (None, 'verified', """
Common exit of the arc fill paths: JP L_81AC (restore SP from L_7C43, POP AF,
RET).
Evidence: control flow."""),
    0x883C: ('DrawCircleRightArc', 'verified', """
Mirror of DrawCircleLeftArc for the RIGHT side of a circle outline (used when the
left side is off the view): pixel at byte L with mask C, moving outwards with RLC C/DEC L,
rows up or down by L_7C48.  Same alternate registers; the arc ends when the point passes
the left end byte E or x reaches 0, and switches to the two-sided loop when C' reaches A'.
Entered by JP from L_7C7A/L_7C92 when L_7C49 = 1.
SMC: LD A,$BF/$CF start-row limits patched by L_8461.
Evidence: tools/check_routines.py circles/outline-arcs (circles with the centre near or
beyond the left edge)."""),
    # ------------------------------------------------- sun/planet and compass
    0x88DC: ('SunNearFlag', 'verified', """
1 when the last proximity check found the sun (L_7065) with all three high
coordinate bytes zero (within 65535 on every axis), else 0.  Written by
UpdateProximityAndCompass; read by L_9966 (the J key handler), which refuses to act while
this flag is 1.
Evidence: writes at $88E2/$8907, read at $9973; tools/check_routines.py
maths/vector-magnitude, scanner/sun-planet-proximity."""),
    0x88DD: ('PlanetNearFlag', 'verified', """
1 when every high coordinate byte of the planet vector (L_706E, sign masked) is
below 2, else 0.  The same condition sets StationPresent.  Read by L_9966 like
SunNearFlag.
Evidence: writes at $8930/$8958, read at $9978; tools/check_routines.py
maths/vector-magnitude, scanner/sun-planet-proximity."""),
    0x88DE: ('CompassDotX', 'verified', """
Compass dot horizontal offset, sign-magnitude (bit 7 = negative/left, bits 0..2 =
0..7 pixels): 8 * (x / |v|) of the compass target.  Written at $899A/$89C7, read by
DrawCompass.
Evidence: instruction semantics; tools/check_routines.py scanner/compass (positive moves the
dot right)."""),
    0x88DF: ('CompassDotY', 'verified', """
Compass dot vertical offset, sign-magnitude like CompassDotX; positive moves the
dot up.
Evidence: write at $89D4, read by DrawCompass at $8AE4; tools/check_routines.py
scanner/compass."""),
    0x88E0: ('CompassTargetBehind', 'verified', """
1 when the compass target's z coordinate is negative (behind), else 0; DrawCompass
then uses the hollow sprite CompassDotBehindSprite instead of the filled
CompassDotFrontSprite.
Evidence: write at $89E2 from bit 7 of the z sign byte, read at $8AD0."""),
    0x88E1: ('UpdateProximityAndCompass', 'verified', """
Per-frame proximity work for the main loop (called from L_732B):
1. Sun vector L_7065: when all high bytes are zero, SunNearFlag = 1 and d = |v|.
   d < $C000 -> L_8A09 (player destroyed flag L_707A = 1, return).  Otherwise L_7079 =
   (d < $E000) and L_704C = high byte of 2.5*($10000-d) via L_8A0F (which also updates the
   condition colour L_7062).
2. Planet vector L_706E: when every high byte (sign masked) is below 2, PlanetNearFlag = 1
   and StationPresent = 1; if they are all zero, d = |v|, d < $C000 -> L_8A09, else
   L_7050 = $A0 - high(2.5*($10000-d)).  Otherwise StationPresent = 0.
3. Compass target: the station slot (InitialRuntimeState) when StationPresent, else the
   planet; L_7078 = $FF selects the coarse (mid/high byte) form for the station.  The
   unit-vector offsets go to CompassDotX/CompassDotY/CompassTargetBehind, then DrawCompass.
   The compass is only drawn on cockpit views; the flags and gauges are updated on every
   screen.
Clobbers: AF, BC, DE, HL, IX.
Evidence: tools/check_routines.py maths/vector-magnitude, scanner/sun-planet-proximity drives
the thresholds (sun/planet at d = $BF00, $C100, $DF00, $E100, $F000, $FF00, $18000, $28000)
and checks every output; runtime: flight scenarios.
INFERRED: L_704C is the cabin temperature gauge, L_7050 the altitude gauge, L_7079 allows
fuel scooping (read at $D507); names belong to the owner of $7000..$70FF."""),
    0x89A9: ('CompassOffsetFine', 'verified', """
Compass offset from a 16-bit coordinate: dividend (IX+1):(IX+0):$00, divisor DE =
|v| (L_E8CF), A = top 3 quotient bits (0..7) OR $80 when bit 7 of (IX+2) (sign) is set.
The quotient is 65536 * coordinate / |v|, so A = 8 * coordinate / |v| (one axis of the unit
vector in 1/8 steps).
Evidence: instruction semantics; tools/check_routines.py scanner/compass,
maths/vector-magnitude."""),
    0x89B2: (None, 'verified', """
Planet not near (some high coordinate byte of L_706E is 2 or more): StationPresent = 0,
then fall into the coarse compass form (L_89B6) with IX still at the planet vector, so the
compass points at the planet.
Evidence: control flow (JR NC from the three axis tests at $893E/$8948/$8953); runtime:
executed in flight scenarios."""),
    0x89B6: (None, 'verified', """
Coarse compass target (planet, or station when L_7078 = $FF): magnitude from the
mid/high bytes (L_8A4D), offsets from the 24-bit coordinates (L_89E8).
Evidence: control flow."""),
    0x89E8: ('CompassOffsetCoarse', 'verified', """
Compass offset from a 24-bit coordinate: dividend (IX+2 AND $7F):(IX+1):(IX+0),
divisor DE (magnitude from L_8A4D), result as L_89A9 (falls into L_89F3).  The dividend is
256 * coordinate and DE is about |v|/256, so the scaling matches the fine form.  Used for
the planet and for a dormant station (StationDormantFlag = $FF).
Evidence: instruction semantics."""),
    0x8A09: ('CollideWithSunOrPlanet', 'verified', """
Collision with the sun or planet: L_707A = 1 and return.  The main loop (L_732B+3)
then runs the destruction sequence ($7335: explosion sounds L_9051/L_9030).
Reached by JP from UpdateProximityAndCompass when |sun| or |planet| is below $C000.
Evidence: instruction semantics; caller code at $732E."""),
    0x8A0F: ('ScaleProximityAndCondition', 'verified', """
HL = 2.5*HL (HL*2 + HL/2) and condition update from H: H >= $78 -> L_7062 = $63; H
>= $50 -> L_7062 = 2 unless it is $63; H < $50 -> L_7062 = 6 only when it was 4.  Returns
HL.  The caller passes $10000 - |v|, so H grows as the sun or planet gets closer.
Evidence: instruction semantics; tools/check_routines.py maths/vector-magnitude,
scanner/sun-planet-proximity (sun at $C100: H = $9D, L_7062 = $63).
The L_7062 values are the condition colours documented there (4 green, 6 yellow, 2 red,
$63 flashing)."""),
    0x8A3A: ('LoadVectorWords', 'verified', """
Load the three coordinate words of the vector at IX: DE = (IX+0,1), BC = (IX+3,4),
HL = (IX+6,7).
Evidence: instruction semantics."""),
    0x8A4D: ('GetVectorMagnitudeHigh', 'verified', """
HL ~= |v| of the vector at IX taking the 16-bit coordinates from (IX+0,1),
(IX+3,4), (IX+6,7) with bit 7 of each high byte cleared.  Called with IX = start of a
3-byte-per-axis vector plus 1, this is the magnitude of the mid/high bytes (|v|/256).
Continues in GetVectorMagnitude.
Evidence: tools/check_routines.py maths/vector-magnitude, scanner/sun-planet-proximity
(e.g. ($400000,$300000,$50000) -> $5028, exact $5027)."""),
    0x8A5A: ('GetVectorMagnitude', 'verified', """
HL ~= sqrt(x*x + y*y + z*z) of the 16-bit coordinates (IX+0,1), (IX+3,4),
(IX+6,7): normalise all three by doubling until one overflows, square the top bytes
(SquareA), take the square root (L_DC53) and shift back.  Accurate to < 1% when some
coordinate is >= 256; returns 0 when |v| >= 65536.  When all three coordinates are below
256 the result is not the magnitude (for example (100,0,0) gives 51200).  A zero vector
never terminates the normalising loop.
Clobbers AF, BC, DE.
Evidence: tools/check_routines.py maths/vector-magnitude, scanner/sun-planet-proximity
compares 3000 random vectors with the exact magnitude."""),
    0x8AC7: ('DrawCompass', 'verified', """
Draw the cockpit compass when CurrentScreenId < 4: copy the 8-byte dot sprite
(filled CompassDotFrontSprite, or hollow CompassDotBehindSprite when CompassTargetBehind)
to CompassDotShiftBuffer, move the screen address $5156 vertically by CompassDotY rows,
redraw the background (DrawCompassBackground), shift the sprite horizontally by
CompassDotX bits and OR its 4 rows x 2 bytes into the screen.  A right shift spills into
the byte to the right of the address, a left shift into the byte to its left.
Evidence: tools/check_routines.py scanner/compass renders the background (a 24x24 circle at
x 168..191, y 136..159) and checks the dot position for +/-x, +/-y; runtime: flight
scenarios."""),
    0x8B7C: ('FixScreenRowDown', 'verified', """
Screen-address correction after INC H crossed a character row: L += $20; if no
carry, H -= 8.
Evidence: instruction semantics (standard Spectrum display layout)."""),
    0x8B86: ('FixScreenRowUp', 'verified', """
Screen-address correction after DEC H crossed a character row: L -= $20; if no
borrow, H += 8.
Evidence: instruction semantics."""),
    0x8B90: ('DrawCompassBackground', 'verified', """
Copy CompassBackgroundBitmap (24 rows x 3 bytes) to the screen at $5035 (character
columns 21..23, pixel rows 136..159).  This erases the previous dot as well.
Evidence: instruction semantics; tools/check_routines.py scanner/compass."""),
    0x8BAE: ('CompassDotScreenAddress', 'verified', """
Screen address of the compass dot's top row, computed by DrawCompass ($8B07) and
read when the sprite is ORed in ($8B2C/$8B5C).  Initial value zero.
Evidence: static and runtime accesses."""),
    0x8BB0: ('CompassDotShiftBuffer', 'verified', """
8-byte work copy of the selected dot sprite (4 rows x 2 bytes), shifted in place
by DrawCompass.
Evidence: written by the LDIR at $8ADF and the shifts at $8B21/$8B51."""),
    0x8BB8: ('CompassDotBehindSprite', 'verified', """
Hollow 4x4 square dot, 4 rows x 2 bytes: shown when the target is behind.
Evidence: selected at $8AD6 when CompassTargetBehind is non-zero."""),
    0x8BC0: ('CompassDotFrontSprite', 'verified', """
Filled 4x4 round dot, 4 rows x 2 bytes: shown when the target is in front.
Evidence: default sprite at $8ACD."""),
    0x8BC8: ('CompassBackgroundBitmap', 'verified', """
Compass background, 24 rows x 3 bytes (a circle plus the panel edge at the right).
Evidence: copied by DrawCompassBackground; rendered by tools/check_routines.py
scanner/compass."""),
    # ---------------------------------------------------------------- scanner
    0x8C10: ('ScannerDotX', 'verified', """
Scanner x offset of the current contact, sign-magnitude: 0.75 * (x/256), bit 7 =
left. Written at $8C95, read at $8CDB/$8CF3/$8D0E.
Evidence: tools/check_routines.py scanner/scanner-contacts (x = $1000 -> $0C, x = -$1000 ->
$8C)."""),
    0x8C11: ('ScannerStickHeight', 'verified', """
Scanner stick length of the current contact, sign-magnitude: 5/16 * (y/256), bit 7
= down.
Evidence: write at $8CB5, read at $8D49; tools/check_routines.py scanner/scanner-contacts
(y = $1000 -> $05)."""),
    0x8C12: ('ScannerDotZ', 'verified', """
Scanner vertical position of the current contact, sign-magnitude: 5/16 * (z/256);
positive moves the stick base up the screen.
Evidence: write at $8CD5, read at $8D27; tools/check_routines.py scanner/scanner-contacts."""),
    0x8C13: ('ScannerSlotCounter', 'verified', """
Remaining object slots in the DrawScannerContacts loop (set to 8, decremented per
slot).
Evidence: accesses at $8C36/$8D7E/$8D84."""),
    0x8C14: ('ScannerContactsDrawn', 'verified', """
1 when contacts have been drawn over the scanner since the background was saved;
the next RestoreScannerBackground (which runs only when it is exactly 1) then repaints the
background and clears it to 0.
Evidence: write at $8C72, read/cleared at $8E1D; tools/check_routines.py
scanner/scanner-background."""),
    0x8C15: ('ShiftBCRight4', 'verified', """
BC >>= 4 (logical).  Entry points +4/+8/+12 shift by 3/2/1.
Evidence: instruction semantics."""),
    0x8C19: ('ShiftBCRight3', 'verified', 'BC >>= 3 (logical).'),
    0x8C1D: ('ShiftBCRight2', 'verified', 'BC >>= 2 (logical).'),
    0x8C21: ('ShiftBCRight1', 'verified', 'BC >>= 1 (logical).'),
    0x8C26: (None, 'verified', """
JP L_8D7E: next slot of DrawScannerContacts (in reach of the JRs above).
Evidence: control flow."""),
    0x8C29: ('DrawScannerContacts', 'verified', """
Repaint the scanner: restore the saved background (RestoreScannerBackground); return
at once when L_DA11 is zero (no active slot); otherwise call L_8DDE (condition colour),
then for each of the 8 object slots (39 bytes from InitialRuntimeState) with non-zero
energy (+$22), coordinate middle bytes (+1, +4, +7) below $40 and x_mid^2 + z_mid^2 <
$1600: set ScannerContactsDrawn and plot a contact around the scanner centre ($558F):
base offset by ScannerDotX (horizontal) and ScannerDotZ (vertical), a vertical stick of
ScannerStickHeight pixels and a 3-pixel dash at its end.
Finally clears 7 pixel rows x 13 bytes at $5009 (stick overflow above the panel).
Geometry (dx = ScannerDotX AND $7F): the stick is in pixel column 123 + dx, or 124 - dx when
x is negative, base row 165 moved up (z > 0) or down by ScannerDotZ; the dash covers the
stick column and the two pixels to its left.  Quirk: dx = 4 leaves the byte count B = 0,
so the byte-step loop runs 256 times and the contact lands one pixel row lower (x > 0) or
higher (x < 0) than intended.  An upward stick is stopped at the top of the bottom third
only in column 15 (L_8DCC); in other columns the dash can land on screen row 127.  That
row holds the bottom line of the view frame, so the extra pixels are rarely visible.  A
downward stick stops at the bottom of the screen (L_8DBA).
scannerblipfix=yes (src/scanner-blip-fix.asm) replaces $8CE0..$8CF2, the operand at
$8D0C and L_8DCC: dx = 4 stays in the centre byte, and every column stops the stick.
Clobbers: all main registers, IX.
Evidence: tools/check_routines.py scanner/scanner-contacts (objects at +/-x, +/-y, +/-z and
out of range), scanner/p3-scanner-geometry (dx 0..13 both signs, tallest sticks);
runtime: flight."""),
    0x8C3D: (None, 'verified', """
Per-slot body of DrawScannerContacts (IX = slot).
iffunit=yes calls IffScannerContactEnergy instead of loading the energy: with the
I.F.F. unit fitted it returns 0 for a threat in the dark half of the blink, so the
slot is skipped like an empty one (src/iff-unit.asm).
Evidence: control flow."""),
    0x8D0B: ('ScannerDotInCentreByte', 'verified', """
dx 0..3 (dx - 4 borrowed): C = dx + 4, the pixel of the stick within the centre byte
$558F; continue with the positive (L_8CFD) or negative (L_8D1A) mask.
Evidence: tools/check_routines.py scanner/p3-scanner-geometry (dx 0..3, both signs)."""),
    0x8D7E: ('NextScannerContact', 'verified', """
Advance DrawScannerContacts to the next 39-byte slot, or finish at L_8D8F.
Evidence: instruction semantics."""),
    0x8DBA: (None, 'verified', """
Stick moving down: FixScreenRowDown, but when the address passes the bottom of the
bitmap (H = $58) drop the return address and continue with the next slot (L_8D7E), so
the contact gets no dash.
Evidence: instruction semantics; tools/check_routines.py scanner/p3-scanner-geometry."""),
    0x8DCC: (None, 'verified', """
Stick moving up: when L = $0F (character row 0, column 15) drop the return address
and continue with the next slot; otherwise FixScreenRowUp.  Only column 15 is guarded:
in any other column the stick continues into the middle third.
Evidence: instruction semantics; tools/check_routines.py scanner/p3-scanner-geometry."""),
    0x8DDE: ('SetConditionYellowForShips', 'verified', """
If L_DA1A is non-zero and L_7062 is neither $63 nor 2, set L_7062 = 6 (yellow).
L_DA1A is set by UpdateObjects when an active slot has bit 2 of its role byte (+$26)
clear; the station slot ($0C there) never sets it, so the colour turns yellow while any
other object is present and red/flashing red are kept.
Called from L_72D2+19 and DrawScannerContacts.
Evidence: instruction semantics; L_DA9A ($DAA9); tools/check_routines.py
scanner/p3-scanner-geometry (condition cases)."""),
    0x8DF2: ('SaveScannerBackground', 'verified', """
Restore any drawn contacts first (RestoreScannerBackground), then patch
CopyScannerBackground for the screen -> buffer direction and run it: the 624 bytes of
character rows 2..7, columns 9..21 of the bottom third ($5049..) are stored at
ScannerBackupBuffer ($5B00..$5D6F). Entered by JP from L_745C.
Evidence: tools/check_routines.py scanner/scanner-background (byte order and exact extent;
the screen is not modified)."""),
    0x8E1D: ('RestoreScannerBackground', 'verified', """
Only when ScannerContactsDrawn = 1: clear it, clear 8 pixel rows x 11 bytes at
$502A (character row 1, columns 10..20), patch CopyScannerBackground back to the buffer ->
screen direction (the original image bytes) and copy the saved 624 bytes back.
Evidence: tools/check_routines.py scanner/scanner-background (no effect for flag values 0,
2, $FF; exact restore otherwise)."""),
    0x8E5C: ('CopyScannerBackground', 'verified', """
Copy 6 character rows x 8 pixel rows x 13 bytes between the screen ($5049) and
ScannerBackupBuffer ($5B00).  Self-modified by
SaveScannerBackground/RestoreScannerBackground:
                save (screen -> buffer)        restore (buffer -> screen, image bytes)
  $8E62         EX DE,HL                       NOP
  $8E65/$8E6A   PUSH HL                        PUSH DE
  $8E85/$8E86   POP HL / INC H                 POP DE / INC D
  $8E89         EX DE,HL                       NOP
  $8E90         NOP                            EX DE,HL
C = $FF keeps the 104 LDI decrements per row group from borrowing into the DJNZ counter B.
Evidence: tools/check_routines.py scanner/scanner-background; smc.txt (runtime writes from
$8DFD..$8E5B)."""),
    0x8E62: ('ScannerCopySwapStart', 'verified',
             'SMC: NOP (restore) or EX DE,HL (save); see CopyScannerBackground.'),
    0x8E65: ('ScannerCopyPushRow', 'verified',
             'SMC: PUSH DE (restore) or PUSH HL (save): keeps the screen row start.'),
    0x8E6A: ('ScannerCopyPushLine', 'verified',
             'SMC: PUSH DE (restore) or PUSH HL (save): keeps the pixel-line start.'),
    0x8E85: ('ScannerCopyNextLine', 'verified',
             'SMC: POP DE / INC D (restore) or POP HL / INC H (save): next pixel line.'),
    0x8E89: ('ScannerCopySwapEnd', 'verified',
             'SMC: NOP (restore) or EX DE,HL (save) before the row pointer is popped.'),
    0x8E90: ('ScannerCopyRowSwap', 'verified',
             'SMC: EX DE,HL (restore) or NOP (save) after the +$20 row step.'),
    # ------------------------------------------------------- screens and keys
    0x8E95: ('HandleScreenKeys', 'verified', """
Screen/view keys (called from the main loop at L_7290), ignored while L_A80B is
set:
- L_FC10 bits 0..3 = keys 1..4 (lowest set bit n): docked (L_7062 = 0) key 1 calls
  L_7AF8 (launch), keys 2..4 select screens 4..6 and call handlers 0..2 (buy cargo, sell
  cargo, equip ship) through CallScreenHandler; in flight keys 1..4 select cockpit views
  0..3 (SelectScreen only, no handler).
- otherwise L_FC0E bits 5..0 = keys I, O, P, K, L, ENTER select screens 7..12 and call
  handlers 3..8 (galactic chart, short-range chart, system data, market prices, commander
  status, inventory), docked or in flight.
Both bytes are cleared afterwards (L_8EF8).
Evidence: instruction semantics; key bits from KeyActionTable (input/scan-keyboard);
tools/check_routines.py input/p3-screen-keys presses every key through ScanKeyboard and
checks the screen and handler; runtime: docked and flight screen scenarios."""),
    0x8EF8: ('ClearViewAndScreenKeys', 'verified', """
Clear the key bytes L_FC10 and L_FC0E and return.
Evidence: instruction semantics; tools/check_routines.py input/p3-screen-keys."""),
    0x8F00: ('ScreenHandlerSavedSP', 'verified', """
Caller SP saved by CallScreenHandler while the handler runs on the temporary
stack.
Evidence: write at $8F02, read at $8F1A."""),
    0x8F02: ('CallScreenHandler', 'verified', """
Run screen handler A (0..8) from the JP table L_A7DA (3 bytes per entry) on a
temporary stack that ends at CockpitBitmap: saves SP in ScreenHandlerSavedSP, patches the
CALL operand at ScreenHandlerCall with L_A7DA + 3*A, calls it, restores SP and jumps to
L_7C09 (clears the 5 key bytes from L_FC0E).
Handlers: 0 L_B27B, 1 L_B474 ("SELL"), 2 L_B53F ("EQUIP SHIP"), 3 L_AB4E, 4 L_A9CA, 5
L_B991 (system data), 6 L_D07D (market), 7 L_D0B9 (status), 8 L_D279 (inventory).
Other callers: L_7158 (index 9 + the number of the lowest set bit of A) and L_7B43 (7).
Evidence: instruction semantics; smc.txt ($8F17 written by $8F14); runtime: docked
screens; tools/check_routines.py input/p3-screen-keys (table entries 0..8)."""),
    0x8F17: ('ScreenHandlerCall', 'verified',
             'SMC: CALL operand replaced by CallScreenHandler with L_A7DA + 3*index.'),
    0x8F21: ('SelectScreen', 'verified', """
Make C the current screen (CurrentScreenId).  Pressing the key of the screen
already shown does nothing for C >= 7 (drops the caller's return address and clears the
keys).  While L_A80A is non-zero cockpit views 1..3 are refused (CurrentScreenId = 0, A =
0).  When the change is from a cockpit view (0..3) to a full screen (>= 4), the clean
cockpit is saved (SaveCleanCockpit).  Output: A = C (0 in the refused case).
Screens 4..6 are redrawn when selected again.
Evidence: instruction semantics; runtime: screen-change scenarios;
tools/check_routines.py input/p3-screen-keys."""),
    0x8F42: ('SaveCleanCockpit', 'verified', """
Restore the scanner background (RestoreScannerBackground), then fall into
SaveCockpitBitmap and SaveCockpitAttributes.  AF preserved.
Evidence: instruction semantics; callers L_71A2, L_721F, L_7B43, SelectScreen."""),
    0x8F5E: (None, 'verified', """
L_A80A set: allow screens >= 4, otherwise force CurrentScreenId = 0 and return A =
0.
Evidence: instruction semantics; tools/check_routines.py input/p3-screen-keys."""),
    0x8F67: ('SelectedJoystickType', 'verified', """
Control type chosen on the title screen ($7219: 1, 2 or 3 when a joystick
direction was held; not written when SPACE selects the keyboard); its low two bits are the
joystick value of the options byte L_FC14 bits 0..1.  ToggleControlDevice XORs it into
L_FC14 to swap between keyboard (0) and that joystick.
Evidence: write at $7219, reads at $8FFA/$9002."""),
    0x8F68: ('HandleFreezeMode', 'verified', """
Freeze loop, entered when L_FC10 bit 7 (CAPS SHIFT) is set: wait for no key
(L_FC13 = $FF), then for each key code: B, D, F, K, Q, R, S, Y run the option handlers
below (each returns A = 0, which plays PlayOptionBeep); SPACE returns with carry clear
(continue), 1 returns with carry set (the caller at $7296 restarts the game).  Both clear
the key bytes (ClearKeyFlags).  Any other key is ignored.  One HALT per poll.
Evidence: instruction semantics (key codes $42, $44, $46, $4B, $51, $52, $53, $59, $31,
$20); caller at $7293; CAPS SHIFT -> L_FC10 bit 7 in KeyActionTable;
tools/check_routines.py input/p3-freeze-options."""),
    0x8FB6: ('ClearKeyFlags', 'verified', """
Zero the five key bytes L_FC0E..L_FC12 (A = 0, carry clear).
Evidence: instruction semantics."""),
    0x8FC4: ('RequestNewGame', 'verified', """
Freeze-mode key 1: ClearKeyFlags, return with carry set (start a new game).
Evidence: instruction semantics; caller at $7296 jumps to L_718F on carry."""),
    0x8FC9: ('ToggleFreezeOptionB', 'verified', """
Freeze-mode key B: toggle bit 4 of L_FC14.  While it is set the input scan (L_FC69)
swaps the two roll key bits and the two pitch key bits, reversing both control axes
(the Kempston path inverts the sense of both swap bits).
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options (N/M and
X/S swapped through ScanKeyboard)."""),
    0x8FCF: ('ToggleFreezeOptionD', 'verified', """
Freeze-mode key D: toggle bit 3 of L_FC14.  While it is set UpdateFlightControls lets
roll and pitch decay towards zero when no direction key is held; clear, they keep their
value.
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options,
controls/update-flight-controls."""),
    0x8FD5: ('ToggleFreezeOptionF', 'verified', """
Freeze-mode key F: toggle bit 6 of L_FC14.  NormalHyperspaceJump tests it at $D680:
while it is set every normal jump takes the mis-jump path (EnterHyperspaceMisjump).
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options."""),
    0x8FDB: ('SelectSoundOff', 'verified', """
Freeze-mode key Q: clear bit 7 of L_FC14 (sound effects off; every player checks
this bit).  Pending requests stay in L_707D.
Evidence: all players (PlayLongNoiseSweep, PlayRisingNoiseSweep, PlayFallingNoiseSweep,
PlayNoiseBurst, UpdateSoundEffect) return at once when bit 7 is clear;
tools/check_routines.py input/p3-freeze-options."""),
    0x8FE1: ('ToggleFreezeOptionR', 'verified', """
Freeze-mode key R: toggle bit 2 of L_FC14.  While it is set UpdateFlightControls
resets roll or pitch to zero at once when the opposite direction key is pressed;
clear, the control moves back one step per frame.
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options,
controls/update-flight-controls."""),
    0x8FE7: ('SelectSoundOn', 'verified', """
Freeze-mode key S: set bit 7 of L_FC14 (sound on) and clear the pending sound
requests L_707D.
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options."""),
    0x8FF0: ('ToggleFreezeOptionY', 'verified', """
Freeze-mode key Y: toggle bit 5 of L_FC14.  While it is set the input scan (L_FC7A)
swaps the two pitch key bits only (vertical control reversed).
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options (X/S
swapped through ScanKeyboard)."""),
    0x8FF6: ('ToggleControlDevice', 'verified', """
Freeze-mode key K: L_FC14 ^= SelectedJoystickType when L_FC14 bits 0..1 are
non-zero (joystick -> keyboard) or when SelectedJoystickType is non-zero (keyboard ->
joystick).  With no joystick chosen nothing changes, but the beep still sounds.
Evidence: instruction semantics; tools/check_routines.py input/p3-freeze-options."""),
    0x9009: ('PlayOptionBeep', 'verified', """
Confirmation beep: 6 frames (HALT), each with 4 speaker pulses (OUT $FE = $30 then
0) whose length E = 2*E + 5 grows from pulse to pulse.  Clobbers AF, BC, E.
Evidence: instruction semantics."""),
    # ----------------------------------------------------------------- sound
    0x902B: ('SoundState', 'verified', """
Current sound player: 0 idle, 1 pulse sweep, 2 ROM pulse burst, 3 or $83 noise
sweep (bit 7 has no reader).  Players: PlayPulseSweepStep, PlayRomPulseBurst,
PlayNoiseSweepStep.
Evidence: dispatch in UpdateSoundEffect; writers in the set-up code; tools/check_routines.py
sound/interrupt-sound-player, sound/synchronous-sound-players."""),
    0x902C: ('SoundCounters', 'verified', """
Sound counters, E = low byte, D = high byte.  Noise sweep: E = steps left, D =
delay per sample.  Pulse sweep: E = pulse width, D = frames left.  ROM pulse burst: D =
frames left.
Evidence: loaded/stored as DE by the players; tools/check_routines.py
sound/interrupt-sound-player, sound/synchronous-sound-players."""),
    0x902E: ('SoundDataPointer', 'verified', """
Current read address of the noise players (a ROM address: $0127, $031A or $1A1A);
the sample bytes come from ROM, so the effects are pseudo-random noise.
Evidence: loaded/stored as HL by L_90AF/L_90F0; tools/check_routines.py
sound/interrupt-sound-player, sound/synchronous-sound-players."""),
    0x9030: ('PlayLongNoiseSweep', 'verified', """
If sound is on (L_FC14 bit 7): DI, noise sweep with $50 samples per step, delay
$40 rising by 2 for 32 steps (L_91A4), then the $A0-sample burst (StartNoiseBurst), played
to the end by WaitSoundFinished.  Callers: launch (L_7B68), docking (L_7B43), destruction
($734E).
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players; instruction semantics."""),
    0x903B: ('PlayRisingNoiseSweep', 'verified', """
If sound is on: DI, noise sweep with $C0 samples per step, delay $C0 falling by 16
for 12 steps (pitch rises), played to the end.  Entered by JP from L_7ACD at the end of
the hyperspace tunnel.
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x9046: ('PlayFallingNoiseSweep', 'verified', """
If sound is on: DI, noise sweep with $C0 samples per step, delay $40 rising by 16
for 12 steps (pitch falls), played to the end.  Called from L_79C0 when the hyperspace
tunnel starts.
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x9051: ('PlayNoiseBurst', 'verified', """
If sound is on: StartNoiseBurst ($A0 samples, delay $40, 2 steps, step size left
from the previous sweep) and play it to the end.  Interrupts are not disabled here. Called
from the destruction sequence ($734B).
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x905A: ('WaitSoundFinished', 'verified', """
Call PlayNoiseSweepStep until SoundState is 0, then clear all pending requests
(L_707D = 0) and enable interrupts.
Evidence: instruction semantics."""),
    0x906A: ('SoundRequestJumpTable', 'verified', """
Eight JP instructions, one per request bit of L_707D, entered by JP (HL) from
UpdateSoundEffect with HL = SoundRequestJumpTable + 3*bit.
bit 0 -> noise sweep, step -2      bit 4 -> pulse sweep 2 frames, step $FD
bit 1 -> noise sweep, step -28     bit 5 -> pulse sweep 8 frames, step $D3
bit 2 -> noise sweep, step +2      bits 6, 7 -> ROM pulse burst (ADD A,$10 variant)
bit 3 -> ROM pulse burst (SRL A variant)
Request setters (SET n on L_707D): bit 0 UseEnergyBomb ($9275); bit 1 UpdateMissileControl
when a missile is launched ($A771); bit 2 object removal L_DB0F ($DB24), collision L_EB44
($EB47) and ClearAllShipSlots ($EBA7); bit 3 ApplyPlayerLaserHit ($EC5C); bit 4
UpdatePlayerLaser when the player fires ($EC1B); bit 5 the ECM update while it runs
($EDAC); bit 6 player damage: L_EB10 ($EB13) and the AI laser hit at $FADF.  No code
sets bit 7.
Evidence: runtime indirect jumps $90A7 -> $906A/$9070/$9076/$9079; tools/check_routines.py
sound/interrupt-sound-player, sound/synchronous-sound-players reaches all 8; static and
runtime writers of L_707D."""),
    0x9082: ('UpdateSoundEffect', 'verified', """
Called from the IM 2 interrupt handler (L_FF25) every frame.  With sound on: if a
player is active (SoundState 1, 2 or other), run one step of it; otherwise take the lowest
set request bit of L_707D, store its number in SoundRequestIndex and start it via
SoundRequestJumpTable.  FinishSoundEffect clears the request bit when the effect ends.
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players (bits 0..7: 8, 8, 8, 1, 2, 8, 1, 1 frames); runtime:
flight scenarios."""),
    0x90AF: ('PlayNoiseSweepStep', 'verified', """
One step of the ROM noise sweep: C samples (operand NoiseSamplesPerStep), each OUT
$FE with (HL) AND $18 (speaker and MIC bits of a ROM byte) followed by a delay of D; then
D += step (operand NoiseDelayStep), E -= 1 and the counters are saved.  At E = 0: if the
new D has bit 7 set the burst StartNoiseBurst follows, else FinishSoundEffect.
Evidence: instruction semantics; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x90B6: (None, 'verified', 'First step of a new noise sweep (JP from StartNoiseSweep).'),
    0x90B7: ('NoiseSamplesPerStep', 'verified',
             'SMC: operand of LD C,n (samples per step); patched at $9195 and $90DF.'),
    0x90C6: ('NoiseDelayStep', 'verified',
             'SMC: operand of ADD A,n (delay change per step); patched at $9191.'),
    0x9134: ('PulseSweepStep', 'verified',
             'SMC: operand of ADD A,n (pulse width step); patched at $9156 ($FD or $D3).'),
    0x8F18: ('ScreenHandlerCallTarget', 'verified',
             'SMC: CALL operand, set by CallScreenHandler to L_A7DA + 3*index.'),
    0x90D8: ('StartNoiseBurst', 'verified', """
SoundState = 3, $A0 samples per step, SoundDataPointer = $0127, D = $40, E = 2.
The delay step operand keeps its previous value.  Called by PlayNoiseBurst; also reached
from PlayNoiseSweepStep when a sweep ends with D >= $80.
Evidence: instruction semantics; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x90F0: ('PlayRomPulseBurst', 'verified', """
State 2: 100 speaker pulses whose high and low lengths are both f(ROM byte), with
f = byte/4 (SRL A; SRL A) or (byte+$10)/2 (ADD A,$10; SRL A) selected by the 2-byte patch
at RomPulseScale; the pointer advances with INC L only.  Then D -= 1 (L_9110); at 0 the
effect ends.
Evidence: instruction semantics; set-up at L_9160/L_9167."""),
    0x90F7: (None, 'verified', 'Entry of the burst loop used by the set-up code at L_9160/L_9167.'),
    0x90FB: ('RomPulseScale', 'verified',
             'SMC: two bytes patched by $916F with CB 3F (SRL A) or C6 10 (ADD A,$10).'),
    0x9110: (None, 'verified', """
Shared end of a pulse frame: D -= 1, save the counters and pointer, finish when D
reaches 0."""),
    0x9119: ('FinishSoundEffect', 'verified', """
SoundState = 0 and toggle request bit SoundRequestIndex of L_707D (clears the bit
that started the effect).  The synchronous players reach this too; WaitSoundFinished then
clears L_707D.  Because the bit is toggled with XOR, a request that was cancelled while
its effect played (SelectSoundOn) is set again.
Evidence: instruction semantics; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x912D: ('PlayPulseSweepStep', 'verified', """
State 1: E = 2*E + k (k = operand PulseSweepStep), then 15 speaker pulses of E
high and E low, then the frame end at L_9110.
Evidence: instruction semantics; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players (requests 4 and 5)."""),
    0x9131: (None, 'verified', 'Pulse sweep entry with DE already loaded (from L_914A/L_9151).'),
    0x914A: (None, 'verified', """
Request bit 4: pulse sweep with k = $FD for D = 2 frames (E = 0): patch
PulseSweepStep, SoundState = 1, first frame at L_9131.
Evidence: runtime executed; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x9151: (None, 'verified', """
Request bit 5: pulse sweep with k = $D3 for D = 8 frames.
Evidence: runtime executed; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x9160: (None, 'verified', """
Request bits 6 and 7: ROM pulse burst with RomPulseScale = ADD A,$10, data at
$1A1A, 1 frame.
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x9167: (None, 'verified', """
Request bit 3: ROM pulse burst with RomPulseScale = SRL A, data at $031A, 1 frame
(SoundState = 2, JP L_90F7).
Evidence: tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x917D: (None, 'verified', 'Request bit 1: noise sweep with step $E4 (-28) (C = $E4).'),
    0x9181: (None, 'verified', """
Request bit 0: noise sweep with step $FE (-2): SoundState = 3, B = $40 samples per
step, D = $40, E = 8 steps, continue at StartNoiseSweep.
Evidence: runtime executed; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x918D: ('StartNoiseSweep', 'verified', """
Start a noise sweep: SoundDataPointer source HL = $0127, delay step operand = C,
samples per step operand = B, then the first step at L_90B6 with D = initial delay, E =
steps.
Evidence: instruction semantics; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x919B: (None, 'verified', """
Request bit 2: noise sweep with step +2, SoundState = $83 (bit 7 set; no reader
tests it).
Evidence: runtime executed; tools/check_routines.py sound/interrupt-sound-player,
sound/synchronous-sound-players."""),
    0x91A4: (None, 'verified', """
Set-up for PlayLongNoiseSweep: SoundState = 3, DI, B = $50, C = $02, D = $40, E =
$20."""),
    0x91B2: (None, 'verified', """
Set-up for PlayRisingNoiseSweep: B = $C0 samples, C = $F0 (step -16), D = $C0, E =
12."""),
    0x91B8: (None, 'verified', 'DI, SoundState = 3, StartNoiseSweep.'),
    0x91C0: (None, 'verified', """
Set-up for PlayFallingNoiseSweep: B = $C0 samples, C = $10 (step +16), D = $40, E
= 12."""),
    0x91C8: ('SoundRequestIndex', 'verified', """
Bit number (0..7) of the L_707D request being played; FinishSoundEffect clears
that bit.
Evidence: write at $909A, read at $911D."""),
    0x91C9: (None, 'inferred', """
Three JP instructions to L_9260, L_9280 and L_9287 (all executed routines).  No
static reference, pointer or runtime access to this block was found; kept as code so that
the targets relocate.  Possibly an unused vector block.  iffunit=yes points the
first entry at IffBlinkTick, since UseEnergyBomb no longer exists."""),
    0x91D2: ('ChartDiscGlyphs', 'verified', """
Four 8x8 glyphs (32 bytes): small disc, large disc, small disc, large disc.
L_AA96 selects one with DE = this + (L_AC1A AND $18) and XORs it into the screen with a
bit shift.
Evidence: read by L_AAAB at runtime (docked-local-chart).
INFERRED: chart system markers whose size depends on L_AC1A."""),
    0x91F2: ('CommodityTable', 'verified', """
17 four-byte market records ($91F2..$9235), one per commodity in the cargo order
(FOOD .. ALIEN ITEMS, tokens $D0..$E0), read in sequence by ComputeMarket (B = $11):
  byte 0  base price (price unit: 0.4 Cr after ComputeMarket's x4 into tenths)
  byte 1  bits 0..4 economy factor f; bit 7 set: stock + f*economy, price -
          (f*economy + 1); clear: stock - (f*economy + 1), price + f*economy
  byte 2  base stock quantity (stock is ANDed with $3F; a negative result gives 0)
  byte 3  mask applied to MarketFluctuation before it is added to price and stock
Bit 5 (GOLD, PLATINUM) and bit 6 (GEM-STONES) of byte 1 mark the kg/g goods but have no
reader: ComputeMarket masks them out and the units come from PrintCommodityUnit by index.
ALIEN ITEMS always gets stock 0.  Line comments: base price, signed price change per
economy level, base stock, mask.
Evidence: instruction semantics of ComputeMarket; tools/check_routines.py
economy/p3-commodity-table (a model of these fields reproduces all prices and stock for
economies 0..7), economy/market (Lave prices)."""),
}

COMMENTS = {
    # circles: SMC limits patched by the stack-copy loops at $849E/$84BA (L_8461)
    0x8601: 'L_7C3C bit 1 set: rows downwards',
    0x8604: 'bit 1 clear: rows upwards (AF comes back intact, so only one call runs)',
    0x8608: 'B = $80: pixel at the left view edge (byte E = column 1)',
    0x860F: 'L_7C3C bit 1 set: right arc downwards',
    0x8612: 'bit 1 clear: right arc upwards',
    0x8619: 'SMC: $1E view (column 30) / $1F direct screen, written by $849E/$84BA',
    0x861C: 'C = $01: rightmost pixel of the end byte',
    0x8630: 'B as saved by L_800F',
    0x8638: 'SMC: $01 view (column 1) / $00 direct screen, written by $849E/$84BA',
    0x863D: 'B = $80: leftmost pixel of the start byte',
    0x8643: 'SMC: x = $F7 view / $FF direct screen, written by $849E/$84BA',
    0x8645: 'ROM PIXEL-ADD: HL = screen address of (C, B)',
    0x8648: 'SMC: SET 7,H maps $40xx->$C0xx (view buffer); two NOPs for the screen',
    0x864E: 'B = 0: no rows to skip',
    0x8651: 'one pixel row up',
    0x8654: 'left the character cell',
    0x865C: 'previous character row',
    0x865F: 'borrow: moved into the third above',
    0x8662: 'same third: undo the DEC H overflow',
    0x8668: 'SMC: top of buffer $C0 / $28 direct screen (no limit)',
    0x866A: 'still inside: continue',
    0x866C: 'left the top of the buffer: stop here',
    0x8671: 'SMC: x = $F7 view / $FF direct screen, written by $849E/$84BA',
    0x8676: 'SMC: SET 7,H (view buffer) / two NOPs (screen)',
    0x867C: 'B = 0: no rows to skip',
    0x867E: 'one pixel row down',
    0x868A: 'next character row',
    0x868D: 'carry: moved into the next third',
    0x8690: 'same third: undo the INC H overflow',
    0x8696: 'SMC: end of buffer $D0 / $58 direct screen',
    0x8698: 'still inside: continue',
    0x869A: 'reached the end of the buffer: stop here',
    # DrawCircleLeftArc
    0x869C: 'L_7C48: 0 = draw upwards, 1 = downwards',
    0x86A2: 'SMC: $BF view / $3F screen: last row above the area',
    0x86A5: 'start row inside the area: draw',
    0x86A9: 'SMC: $CF view / $57 screen: last row of the area',
    0x86AC: 'start row inside the area: draw',
    0x86AE: 'start row outside: nothing to draw (AF pushed by the dispatcher)',
    0x86B0: 'save SP for the clipping exits (L_81AC)',
    0x86B4: 'keep L (right end byte) in D',
    0x86B8: 'plot the left-side pixel',
    0x86BA: 'row direction',
    0x86C4: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x86CD: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    0x86D0: "row step: HL' += 2y+1, y += 1",
    0x86D7: 'error still negative: same column, next row',
    0x86D9: 'x step: left point one pixel inwards',
    0x86DB: 'mask wrapped to bit 7: next byte',
    0x86DD: "HL' -= x, x -= 1 (C' = -x)",
    0x86E1: "x at the value (A') where the right side enters the view?",
    0x86E2: 'yes: continue with both sides',
    0x86E5: "HL' -= new x: 2x-1 in all",
    0x86E9: 'error negative: plot the next row',
    0x86EB: 'error still >= 0: shallow part, horizontal steps',
    0x86F0: 'moved past the right end byte L: done',
    0x86FC: 'end of the arc: restore SP, POP AF, return',
    0x8705: 'moved past the right end byte L: done',
    0x8709: 'shallow part: plot the left point',
    0x870F: 'one pixel inwards; carry: next byte',
    0x8713: "x step: HL' -= x, x -= 1",
    0x8716: 'x reached 0: done',
    0x871A: 'right side enters the view: two-sided loop',
    0x8721: 'error >= 0: next pixel on the same row',
    0x8723: "error negative: row step, HL' += 2y+1",
    0x8728: 'row direction',
    0x8732: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x873B: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    # DrawCirclePairedArcs
    0x8742: 'left end at or right of the right end: nothing to draw',
    0x8744: 'row direction',
    0x874A: 'SMC: $BF view / $3F screen',
    0x874D: 'start row inside the area: draw',
    0x8751: 'SMC: $CF view / $57 screen',
    0x8754: 'start row inside the area: draw',
    0x8756: 'start row outside: nothing to draw',
    0x875E: 'plot the right-side pixel (mask C at L)',
    0x8763: 'plot the left-side pixel (mask B at E)',
    0x8765: 'row direction',
    0x876F: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x8778: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    0x877B: "row step: HL' += 2y+1, y += 1",
    0x8782: 'error negative: same columns, next row',
    0x8784: 'x step: left point one pixel inwards',
    0x8788: 'right point one pixel inwards',
    0x878C: "HL' -= 2x-1, x -= 1",
    0x8793: 'error negative: plot the next row',
    0x8796: 'error >= 0: shallow part',
    0x8799: 'left point into the next byte',
    0x879C: 'meets the right point: the arc ends',
    0x87A0: 'right point into the previous byte',
    0x87A3: 'meets the left point: the arc ends',
    0x87A7: 'end of the arc: restore SP, POP AF, return',
    0x87AD: 'left point into the next byte',
    0x87B0: "same byte as the right point: fill between them",
    0x87B4: 'right point into the previous byte',
    0x87B7: 'same byte as the left point: fill between them',
    0x87BB: 'shallow part: plot both points',
    0x87C4: 'left point inwards',
    0x87C8: 'right point inwards',
    0x87CC: "x step: HL' -= x, x -= 1",
    0x87CF: 'x reached 0: close the outline in both bytes',
    0x87D5: 'error >= 0: next pixels on the same row',
    0x87D7: "error negative: row step, HL' += 2y+1",
    0x87DC: 'row direction',
    0x87E6: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x87EF: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    0x87F4: "left point entered the right point's byte",
    0x87F9: 'nothing lit: fill the whole byte',
    0x87FE: 'A = $FF << (index of the lowest lit pixel)',
    0x8805: 'fill from bit 7 down to the lowest lit pixel',
    0x8808: "right point entered the left point's byte",
    0x880C: 'nothing lit: fill the whole byte',
    0x880E: 'B = $FF >> (number of unlit pixels on the left)',
    0x8815: 'fill from the highest lit pixel down to bit 0',
    0x8819: 'x = 0: right byte first',
    0x8821: 'A = $FF << (index of the lowest lit pixel)',
    0x882A: 'right byte: bit 7 down to its lit pixel',
    0x882B: 'left byte',
    0x8832: 'B = $FF >> (number of unlit pixels on the left)',
    0x8839: 'left byte: its lit pixel down to bit 0',
    # DrawCircleRightArc
    0x883C: 'L_7C48: 0 = draw upwards, 1 = downwards',
    0x8842: 'SMC: $BF view / $3F screen',
    0x8845: 'start row inside the area: draw',
    0x8849: 'SMC: $CF view / $57 screen',
    0x884C: 'start row inside the area: draw',
    0x884E: 'start row outside: nothing to draw',
    0x8856: 'plot the right-side pixel',
    0x8857: 'row direction',
    0x8861: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x886A: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    0x886D: "row step: HL' += 2y+1, y += 1",
    0x8874: 'error still negative: same column, next row',
    0x8876: 'x step: right point one pixel inwards',
    0x8878: 'mask wrapped to bit 0: previous byte',
    0x887A: "HL' -= x, x -= 1",
    0x887E: "x at the value (A') where the left side enters the view?",
    0x887F: 'yes: continue with both sides',
    0x8886: 'error negative: plot the next row',
    0x8888: 'error still >= 0: shallow part, horizontal steps',
    0x888E: 'moved past the left end byte E: done',
    0x889A: 'end of the arc: restore SP, POP AF, return',
    0x88A4: 'moved past the left end byte E: done',
    0x88A8: 'shallow part: plot the right point',
    0x88AB: 'one pixel inwards; carry: previous byte',
    0x88AF: "x step: HL' -= x, x -= 1",
    0x88B2: 'x reached 0: done',
    0x88B6: 'left side enters the view: two-sided loop',
    0x88BD: 'error >= 0: next pixel on the same row',
    0x88BF: "error negative: row step, HL' += 2y+1",
    0x88C4: 'row direction',
    0x88CE: 'cell crossed: fix HL and E; ends the arc at the top limit',
    0x88D7: 'cell crossed: fix HL and E; ends the arc at the bottom limit',
    # proximity / compass
    0x88E2: 'SunNearFlag = 0 unless the sun passes the test',
    0x88E5: 'sun position vector (3 bytes per axis)',
    0x88E9: 'x high byte (sign masked)',
    0x88EE: 'non-zero high byte: sun too far, skip it',
    0x88FE: 'HL = |sun|',
    0x8903: '0: |v| >= 65536, treat as far',
    0x8907: 'SunNearFlag = 1: the J key is refused',
    0x890E: 'DE = $10000 - |v| (carry is clear after OR L)',
    0x8915: 'borrow when |v| < $C000: collision',
    0x891E: 'borrow when |v| < $E000',
    0x8924: 'L_7079 = 1 when |sun| < $E000',
    0x8928: 'HL = 2.5*($10000-|v|); condition colour from H',
    0x892C: 'L_704C = high byte of 2.5*($10000-|v|)',
    0x8930: 'PlanetNearFlag = 0 unless the planet passes the test',
    0x8933: 'planet position vector',
    0x893C: 'within 2*65536 on this axis?',
    0x894A: 'collect the high bytes (0 or 1 each)',
    0x8955: 'Z only when all three high bytes are 0',
    0x8958: 'PlanetNearFlag = 1',
    0x895B: 'a high byte is 1: no altitude update',
    0x895D: 'HL = |planet|',
    0x8962: '|v| >= 65536: no altitude update',
    0x8971: 'within $C000: collision with the planet',
    0x8975: 'HL = 2.5*($10000-|v|); condition colour from H',
    0x897B: 'L_7050 = $A0 - high byte of 2.5*($10000-|v|)',
    0x8980: 'StationPresent = 1 (planet near)',
    0x8983: '$FF selects the coarse station form',
    0x8987: 'compass target: station slot 0',
    0x898B: 'station dormant: 24-bit form',
    0x898D: 'HL = |station| from the 16-bit coordinates',
    0x8994: 'avoid a zero divisor',
    0x8996: 'keep |v| for the y axis',
    0x8997: 'A = 8*x/|v|, bit 7 = sign',
    0x899A: 'x offset',
    0x899D: 'IX += 3: y coordinate',
    0x89A4: 'A = 8*y/|v|',
    0x89A9: 'A = 0: dividend = coordinate * 256',
    0x89B3: 'StationPresent = 0: compass shows the planet',
    0x89B6: 'IX+1: middle and high bytes',
    0x89B8: 'HL = |v|/256',
    0x89BF: 'avoid a zero divisor',
    0x89C1: 'IX back to the vector start',
    0x89C4: 'A = 8*x/|v|, bit 7 = sign',
    0x89C7: 'x offset',
    0x89CA: 'IX += 3: y coordinate',
    0x89D1: 'A = 8*y/|v|',
    0x89D4: 'y offset',
    0x89D7: 'z sign byte (IX was advanced by 3)',
    0x89E2: 'CompassTargetBehind = 1 when z is negative',
    0x89E5: 'draw it (cockpit views only)',
    0x89E8: 'dividend = 24-bit coordinate, sign cleared',
    0x89F3: 'BC = 65536 * coordinate / DE',
    0x89F6: 'A = top 3 bits of the quotient: 8*coordinate/|v|',
    0x89FF: 'sign from bit 7 of the high coordinate byte',
    0x8A0B: 'PlayerDeadFlag = 1',
    0x8A16: 'HL = 2.5 * HL',
    0x8A17: 'previous condition colour',
    0x8A1C: 'H >= $50 ?',
    0x8A20: 'H >= $78 ?',
    0x8A27: 'flashing red is kept',
    0x8A28: 'L_7062 = 2 (red)',
    0x8A2C: 'L_7062 = $63 (flashing red)',
    0x8A33: 'only green (4) changes',
    0x8A34: 'L_7062 = 6 (yellow)',
    0x8A50: 'clear the sign bits',
    0x8A56: 'A = 1: no doubling yet',
    0x8A5F: 'double x, y and z until one overflows; A = 2^doublings',
    0x8A62: 'x overflowed: restore its top bit, this round undone',
    0x8A68: 'y overflowed: restore y, undo the x doubling',
    0x8A6B: 'z overflowed: restore z, undo y and x',
    0x8A6D: 'all three doubled: the scale A doubles',
    0x8A80: 'C = x high byte',
    0x8A83: 'DE = z^2',
    0x8A8A: 'DE = y^2',
    0x8A8D: 'HL = y^2 + z^2, carry into B',
    0x8A92: 'DE = x^2',
    0x8A95: 'B:HL = x^2 + y^2 + z^2',
    0x8A9B: 'sum < 65536: root directly',
    0x8A9D: 'sum >= 65536: divide B:HL by 4',
    0x8AAA: 'and halve the scale',
    0x8AAC: 'scale was 1: special case at L_8ABD',
    0x8AAF: 'L_DC53: HL = 256*sqrt(HL)',
    0x8AB3: 'divide the root by the scale A',
    0x8ABD: 'sqrt of the quartered sum',
    0x8AC0: 'times 2; carry: |v| >= 65536',
    0x8AC3: 'out of range: 0',
    0x8ACA: 'cockpit views 0..3 only',
    0x8ACD: 'filled dot: target in front',
    0x8AD6: 'target behind: hollow dot',
    0x8ADF: 'copy the dot sprite to CompassDotShiftBuffer',
    0x8AE1: 'screen address of the dot at offset (0,0)',
    0x8AE8: 'number of rows',
    0x8AEF: 'bit 7 set: move down',
    0x8AF2: 'move up one pixel row per unit',
    0x8AF5: 'fix the address at a character-cell boundary',
    0x8AFE: 'move down one pixel row per unit',
    0x8B02: 'fix the address at a character-cell boundary',
    0x8B07: 'dot address after the vertical move',
    0x8B0A: 'redraw the empty compass (erases the old dot)',
    0x8B0D: 'horizontal offset, bit 7 = left',
    0x8B1A: 'bit 7 set: shift left',
    0x8B21: 'shift all 4 rows right by one pixel',
    0x8B2A: 'once per pixel of the offset',
    0x8B33: 'B = 4 sprite rows',
    0x8B36: 'OR the first byte into the screen',
    0x8B3B: 'and the spill byte to its right',
    0x8B43: 'next pixel row',
    0x8B51: 'shift all 4 rows left by one pixel',
    0x8B5A: 'once per pixel of the offset',
    0x8B66: 'OR the first byte into the screen',
    0x8B6B: 'and the spill byte to its left',
    0x8B73: 'next pixel row',
    0x8B90: 'screen: character row 1, column 21 of the bottom third',
    0x8B96: 'B = 24 rows of 3 bytes; C = $FF keeps the LDIs from borrowing into B',
    0x8B9F: 'back to the first column',
    0x8BA7: 'next pixel row',
    # scanner
    0x8C2C: 'no active slot: background restored, no contacts',
    0x8C31: 'condition yellow while ships are present',
    0x8C34: '8 object slots',
    0x8C39: 'slot 0 (the station) first',
    0x8C3D: 'energy 0: empty slot',
    0x8C41: 'next slot',
    0x8C46: 'x middle byte must be < $40',
    0x8C4D: 'y middle byte must be < $40',
    0x8C54: 'z middle byte must be < $40',
    0x8C5B: 'x_mid^2',
    0x8C62: 'z_mid^2',
    0x8C66: 'overflow: out of range',
    0x8C68: 'x^2 + z^2 limit (scanner ellipse)',
    0x8C6E: 'outside the ellipse: no contact',
    0x8C72: 'ScannerContactsDrawn = 1',
    0x8C75: 'divisor $4000: BC = 4*coordinate',
    0x8C82: 'BC = x/2',
    0x8C87: 'BC = x/4',
    0x8C8A: 'HL = 0.75 * x (high byte used)',
    0x8C8B: 'sign of x',
    0x8CA2: 'BC = y/4',
    0x8CA7: 'BC = y/16',
    0x8CAA: 'HL = 5/16 * y',
    0x8CAB: 'sign of y',
    0x8CC2: 'BC = z/4',
    0x8CC7: 'BC = z/16',
    0x8CCA: 'HL = 5/16 * z',
    0x8CCB: 'sign of z',
    0x8CD8: 'scanner centre on screen',
    0x8CDE: 'dx = horizontal offset in pixels',
    0x8CE0: 'dx - 4',
    0x8CE3: 'dx < 4: stays in the centre byte',
    0x8CE6: 'whole bytes: (dx-4)/8',
    0x8CF2: 'partial byte: one more',
    0x8CF8: 'negative x: step left',
    0x8CFA: 'B bytes right (B = 0 for dx = 4: 256 steps = one row down)',
    0x8CFD: 'mask $80 >> (C-1), or $01 when C = 0',
    0x8D0B: 'C = dx + 4: pixel stays in the centre byte',
    0x8D17: 'B bytes left (B = 0 for dx = 4: 256 steps = one row up)',
    0x8D1A: 'mask $01 << (C-1), or $80 when C = 0',
    0x8D27: 'vertical position from z',
    0x8D33: 'bit 7 set: below the centre',
    0x8D35: 'move up one pixel row per unit',
    0x8D40: 'move down one pixel row per unit',
    0x8D49: 'stick length from ScannerStickHeight',
    0x8D55: 'bit 7 set: stick goes down',
    0x8D57: 'stick upwards: one pixel per row',
    0x8D5E: 'cell crossed (column 15 stops at the top of the third)',
    0x8D65: 'stick downwards',
    0x8D6C: 'cell crossed (stops at the bottom of the screen)',
    0x8D71: '3-pixel dash at the end of the stick',
    0x8D73: 'pixel in bit 7: dash spans two bytes',
    0x8D77: 'pixel in bit 6: dash spans two bytes',
    0x8D79: 'the pixel and the two to its left',
    0x8D84: 'one slot fewer',
    0x8D87: '39-byte object slot',
    0x8D90: 'clear 7 pixel rows x 13 bytes above the scanner',
    0x8D92: 'character row 0, column 9 of the bottom third',
    0x8DA2: 'left byte bits 1..0 plus bit 7 here',
    0x8DAE: 'left byte bit 0 plus bits 7..6 here',
    0x8DBB: 'next character row',
    0x8DC0: 'past the bottom of the screen?',
    0x8DC4: 'drop the return address: next slot',
    0x8DCD: 'character row 0, column 15 only',
    0x8DD1: 'drop the return address: next slot',
    0x8DD5: 'previous character row',
    0x8DE2: 'no ships present',
    0x8DE8: 'flashing red kept',
    0x8DEB: 'red kept',
    0x8DEC: '6 = yellow',
    # scanner background save/restore SMC
    0x8DF8: 'EX DE,HL',
    0x8DFD: 'patch ScannerCopySwapStart',
    0x8DFE: 'PUSH HL',
    0x8E03: 'patch ScannerCopyPushRow',
    0x8E05: 'patch ScannerCopyPushLine',
    0x8E06: 'POP HL',
    0x8E0B: 'patch ScannerCopyNextLine',
    0x8E0D: 'INC H',
    0x8E0F: 'patch the INC after the POP',
    0x8E10: 'A = 0: NOP opcode',
    0x8E14: 'patch ScannerCopyRowSwap = NOP',
    0x8E15: 'EX DE,HL',
    0x8E1A: 'patch ScannerCopySwapEnd',
    0x8E21: 'runs only when the flag is exactly 1',
    0x8E22: 'A = 0: flag cleared',
    0x8E25: 'clear the stick area above the scanner',
    0x8E26: '8 pixel rows x 11 bytes',
    0x8E28: 'character row 1, column 10 of the bottom third',
    0x8E3A: 'A = 0: NOP opcode',
    0x8E3E: 'patch ScannerCopySwapStart = NOP',
    0x8E3F: 'PUSH DE',
    0x8E44: 'patch ScannerCopyPushRow',
    0x8E46: 'patch ScannerCopyPushLine',
    0x8E47: 'POP DE',
    0x8E4C: 'patch ScannerCopyNextLine',
    0x8E4E: 'INC D',
    0x8E50: 'patch the INC after the POP',
    0x8E51: 'EX DE,HL',
    0x8E56: 'patch ScannerCopyRowSwap',
    0x8E57: 'A = 0: NOP opcode',
    0x8E5B: 'patch ScannerCopySwapEnd = NOP',
    0x8E5C: 'screen: character row 2, column 9 of the bottom third',
    0x8E5F: 'saved background (624 bytes)',
    0x8E63: '6 character rows',
    0x8E66: '8 pixel rows',
    0x8E68: 'C = $FF: the 13 LDIs never borrow into B',
    0x8E6B: '13 bytes of one pixel line',
    0x8E8A: 'row start',
    0x8E8C: 'next character row',
    # screens
    0x8E95: 'non-zero: screen keys ignored',
    0x8E9A: 'keys 1..4 (bits 0..3)',
    0x8E9F: 'none: try the screen keys',
    0x8EA1: 'C = key number - 1',
    0x8EA5: 'key 1',
    0x8EAA: 'key 2',
    0x8EAF: 'key 3; otherwise key 4',
    0x8EB2: '0 = docked',
    0x8EB6: 'in flight: cockpit view C',
    0x8EB8: 'docked: screens 4..6',
    0x8EBC: 'screen 4..6; A = C',
    0x8EBF: 'handler index 0..2: buy, sell, equip',
    0x8ECF: 'in flight: front view',
    0x8ED1: 'docked key 1: launch',
    0x8EDB: 'screen keys, bits 5..0 -> screens 7..12',
    0x8EDE: 'I, O, P, K, L, ENTER',
    0x8EE1: 'none pressed',
    0x8EE3: 'B = 6 keys, C = 7 for I',
    0x8EE6: 'highest key bit first: I 7, O 8, P 9, K 10, L 11, ENTER 12',
    0x8EEF: 'A < 7 would mean refused (not possible for 7..12)',
    0x8EF3: 'handler index 3..8',
    0x8F06: 'temporary stack ends where the saved cockpit bitmap starts',
    0x8F0A: 'A*3: JP table entry size',
    0x8F0F: 'HL = L_A7DA + 3*A',
    0x8F14: 'patch the CALL operand below',
    0x8F1A: "back to the caller's stack",
    0x8F1E: 'clear the key bytes and return',
    0x8F24: 'B = old screen',
    0x8F26: 'different screen: change it',
    0x8F29: 'static screens are not redrawn',
    0x8F2D: 'drop the caller, clear the keys',
    0x8F30: 'non-zero: cockpit views 1..3 refused',
    0x8F37: 'new current screen',
    0x8F3B: 'old screen a full screen?',
    0x8F3E: 'old screen is a full screen: no cockpit to save',
    0x8F3F: 'new screen a cockpit view?',
    0x8F43: 'remove the contacts before saving',
    0x8F63: 'refused: front view, A = 0',
    # freeze mode
    0x8F68: 'bit 7: CAPS SHIFT freeze key',
    0x8F6E: 'HL = options byte for the handlers',
    0x8F72: 'wait until no key is pressed',
    0x8F7E: 'wait for a key',
    0x8F80: "'B'",
    0x8F82: 'reverse roll and pitch keys',
    0x8F85: "'D'",
    0x8F87: 'control damping',
    0x8F8A: "'F'",
    0x8F8C: 'forced mis-jump',
    0x8F8F: "'K'",
    0x8F91: 'keyboard <-> joystick',
    0x8F94: "'Q'",
    0x8F96: 'sound off',
    0x8F99: "'R'",
    0x8F9B: 'recentring',
    0x8F9E: "'S'",
    0x8FA0: 'sound on',
    0x8FA3: "'Y'",
    0x8FA5: 'reverse the pitch keys',
    0x8FA8: "'1': new game",
    0x8FAC: "SPACE: continue",
    0x8FB0: 'A = 0 after an option handler: beep',
    0x8FB6: 'KeyFlagsScreens and the four bytes after it',
    0x8FC7: 'carry set: new game',
    0x8FCD: 'A = 0: the freeze loop beeps',
    0x8FF8: 'joystick selected?',
    0x8FFD: 'yes: back to the keyboard',
    0x9000: 'keyboard and no joystick chosen: no change',
    0x9005: 'toggle the device bits',
    0x900E: 'one frame per group of pulses',
    0x9013: 'E = 2*E + 5: longer pulses',
    0x9017: 'speaker bit on',
    0x901B: 'high time',
    0x9020: 'speaker off',
    0x9022: 'low time',
    # sound
    0x9033: 'sound effects on?',
    0x9035: 'sound off: no effect',
    0x9036: 'DI and set up the sweep',
    0x9039: 'play it to the end',
    0x9057: 'set up the burst',
    0x905E: 'finished',
    0x9065: 'cancel all pending requests',
    0x906A: 'bit 0: energy bomb',
    0x906D: 'bit 1: missile launched',
    0x9070: 'bit 2: object destroyed or collision',
    0x9073: "bit 3: player's laser hit",
    0x9076: 'bit 4: player fires the laser',
    0x9079: 'bit 5: ECM running',
    0x907C: 'bit 6: player damaged',
    0x907F: 'bit 7: no setter in the code',
    0x9088: 'player active?',
    0x908E: 'pending requests',
    0x9095: 'B = number of the lowest set bit',
    0x909D: 'A = 3*B',
    0x90A7: 'JP into SoundRequestJumpTable',
    0x90A9: 'state 1',
    0x90AD: 'state 2; 3 or $83 fall through',
    0x90B9: 'speaker (bit 4) and MIC (bit 3) from the ROM byte',
    0x90BE: 'delay D',
    0x90C8: 'one step fewer',
    0x90D1: 'not used by either continuation',
    0x90D4: 'delay wrapped past $7F: add the burst',
    0x90E2: 'ROM address used as noise data',
    0x90E5: 'D = $40 delay, E = 2 steps',
    0x90F7: '100 pulses',
    0x90FA: 'INC L only: stays in one 256-byte page',
    0x9101: 'speaker bit on',
    0x9105: 'high time',
    0x910B: 'low time',
    0x9110: 'one frame fewer',
    0x9122: 'A = bit SoundRequestIndex',
    0x912A: 'clear that request bit',
    0x9133: 'SMC: operand patched by $9156 ($FD or $D3)',
    0x9136: '15 pulses',
    0x9138: 'speaker bit on',
    0x913D: 'high time E',
    0x9143: 'low time E',
    0x914C: 'D = 2 frames, E = 0',
    0x9153: 'D = 8 frames, E = 0',
    0x9156: 'patch the ADD operand at $9134',
    0x9162: 'C6 10 = ADD A,$10 (opcode bytes, not an address)',
    0x9169: 'CB 3F = SRL A (opcode bytes, not an address)',
    0x916C: 'D = 1 frame',
    0x916F: 'patch RomPulseScale',
    0x9172: 'HL = ROM data address A*256 + $1A',
    0x918A: 'D = $40 initial delay, E = 8 steps',
    0x9188: 'B = $40 samples per step',
    0x918D: 'ROM address used as noise data',
    0x9191: 'patch NoiseDelayStep',
    0x9195: 'patch NoiseSamplesPerStep',
    0x91AA: 'B = $50 samples, C = step +2',
    0x91AD: 'D = $40 initial delay, E = 32 steps',
    0x91B2: 'B = $C0 samples, C = $F0 (step -16)',
    0x91B5: 'D = $C0 initial delay, E = 12 steps',
    0x91C0: 'B = $C0 samples, C = $10 (step +16)',
    0x91C3: 'D = $40 initial delay, E = 12 steps',
    # commodity records: price, flags/factor, stock, mask (CommodityTable header)
    0x91F2: 'FOOD: price 19, -2 per economy level, stock 6, mask $01',
    0x91F6: 'TEXTILES: price 20, -1, stock 10, mask $03',
    0x91FA: 'RADIOACTIVES: price 65, -3, stock 2, mask $07',
    0x91FE: 'SLAVES: price 40, -5, stock 226, mask $1F',
    0x9202: 'LIQUOR/WINES: price 83, -5, stock 251, mask $0F',
    0x9206: 'LUXURIES: price 196, +8, stock 54, mask $03',
    0x920A: 'NARCOTICS: price 235, +29, stock 8, mask $78',
    0x920E: 'COMPUTERS: price 154, +14, stock 56, mask $03',
    0x9212: 'MACHINERY: price 117, +6, stock 40, mask $07',
    0x9216: 'ALLOYS: price 78, +1, stock 17, mask $1F',
    0x921A: 'FIREARMS: price 124, +13, stock 29, mask $07',
    0x921E: 'FURS: price 176, -9, stock 220, mask $3F',
    0x9222: 'MINERALS: price 32, -1, stock 53, mask $03',
    0x9226: 'GOLD: price 97, -1, stock 66, mask $07 (byte 1 bit 5)',
    0x922A: 'PLATINUM: price 171, -2, stock 55, mask $1F (byte 1 bit 5)',
    0x922E: 'GEM-STONES: price 45, -1, stock 250, mask $0F (byte 1 bit 6)',
    0x9232: 'ALIEN ITEMS: price 53, +15, stock 192 (never stocked), mask $07',
}

DATA = {
    0x88DC: (0x88E1, 'bytes', 1),
    0x8BAE: (0x8BB0, 'words', 1),
    0x8BB0: (0x8BB8, 'bytes', 2),
    0x8BB8: (0x8BC0, 'bytes', 2),
    0x8BC0: (0x8BC8, 'bytes', 2),
    0x8BC8: (0x8C10, 'bytes', 3),
    0x8C10: (0x8C15, 'bytes', 1),
    0x8F00: (0x8F02, 'words', 1),
    0x8F67: (0x8F68, 'bytes', 1),
    0x902B: (0x902C, 'bytes', 1),
    0x902C: (0x902E, 'words', 1),
    0x902E: (0x9030, 'words', 1),
    0x91C8: (0x91C9, 'bytes', 1),
    0x91D2: (0x91F2, 'bytes', 8),
    0x91F2: (0x9236, 'bytes', 4),
}

CONSTANTS = {
    0x91B2: 'B = $C0 samples per step, C = $F0 delay step: two byte parameters, not an address',
    0x91B5: 'D = $C0 initial delay, E = $0C steps: two byte parameters, not an address',
    0x91C0: 'B = $C0 samples per step, C = $10 delay step: two byte parameters, not an address',
}

OPERANDS = {
    0x8DF5: 'ScannerCopyPushLine-ScannerCopyPushRow',   # LD BC,$0005: distance of the
    0x8E37: 'ScannerCopyPushLine-ScannerCopyPushRow',   # two patched PUSH instructions
    0x8E5C: 'ScannerBackupScreen',
    0x8E5F: 'ScannerBackupBuffer',
}

FIELDS = {
    'ScannerBackupBuffer': (0x5B00, '624-byte saved scanner background (also the runtime '
                                    'cockpit attribute buffer when the cockpit is saved)'),
    'ScannerBackupScreen': (0x5049, 'screen address of the scanner background area: '
                                    'character rows 2..7, columns 9..21 of the bottom third'),
}

SEEDS = {
    0x906A: 'SoundRequestJumpTable entry 0: runtime indirect jump $90A7 -> $906A',
    0x906D: 'SoundRequestJumpTable entry 1: tools/check_routines.py sound/interrupt-sound-player '
            '(request bit 1)',
    0x9070: 'SoundRequestJumpTable entry 2: runtime indirect jump $90A7 -> $9070',
    0x9073: 'SoundRequestJumpTable entry 3: tools/check_routines.py sound/interrupt-sound-player '
            '(request bit 3)',
    0x9076: 'SoundRequestJumpTable entry 4: runtime indirect jump $90A7 -> $9076',
    0x9079: 'SoundRequestJumpTable entry 5: runtime indirect jump $90A7 -> $9079',
    0x907C: 'SoundRequestJumpTable entry 6: tools/check_routines.py sound/interrupt-sound-player '
            '(request bit 6)',
    0x907F: 'SoundRequestJumpTable entry 7: tools/check_routines.py sound/interrupt-sound-player '
            '(request bit 7)',
    0x914A: 'runtime executed; target of JP at $9076',
    0x9151: 'runtime executed; target of JP at $9079',
    0x9160: 'target of JP at $907C/$907F; tools/check_routines.py sound/interrupt-sound-player',
    0x9167: 'target of JP at $9073; tools/check_routines.py sound/interrupt-sound-player',
    0x917D: 'target of JP at $906D; tools/check_routines.py sound/interrupt-sound-player',
    0x9181: 'runtime executed; target of JP at $906A',
    0x919B: 'runtime executed; target of JP at $9070',
    0x91C9: 'well-formed JP to the executed routine L_9260 (unreferenced vector block)',
    0x91CC: 'well-formed JP to the executed routine L_9280 (unreferenced vector block)',
    0x91CF: 'well-formed JP to the executed routine L_9287 (unreferenced vector block)',
}

ASSERTS = {
    'r3-scanner-backup-size': ('ScannerBackupBuffer+6*8*13 <= FontRuntime',
                               'the 624-byte scanner backup must end before the runtime font copy'),
}
