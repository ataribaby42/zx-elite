"""3D object renderer, its workspace and arithmetic helpers, $E000..$EBFF.

Evidence: instruction semantics; 48K runtime traces (docs/generated/runtime-xrefs.json);
simulator checks in tools/check_routines.py (arithmetic helpers against Python models,
L_E008 on real blueprints against a float projection model, pixel plotting,
orthogonalisation, object contact, explosion record, AI beams, player laser rate).
Formats: docs/SHIPS.md (23-byte blueprint header).
Instance/vertex conventions used below (verified here by code and tests):
- instance +$00..+$08: x, y, z; each lo, hi, then a byte whose bit 7 is the sign
  (the renderer uses only the 16-bit magnitude and that sign bit);
- instance +$09..+$0E, +$0F..+$14, +$15..+$1A: orientation vectors Z, Y, X; each
  component is a fraction byte followed by a sign-magnitude byte (unit about 127);
  the renderer reads only the sign-magnitude bytes;
- vertex record (6 bytes): |x|,|y|,|z|, signs in bits 7/6/5 of byte 3 plus a
  visibility threshold in bits 0..4, then four face nibbles in bytes 4..5;
- edge record (4 bytes): visibility, vertex index 1, vertex index 2, two face nibbles;
- face record (4 bytes): |nx|,|ny|,|nz|, signs/visibility as for vertices.
"""

SECTIONS = {
    0xE008: ('3D object renderer',
             'Per-object view culling, projection of the object centre, dot or full\n'
             'wireframe drawing (rotation matrix, face visibility, vertex projection,\n'
             'edges), crosshair target detection, explosion position and AI laser beams.'),
    0xE222: ('3D renderer workspace',
             'Projected-vertex buffer, face-visibility flags, rotation matrix, row\n'
             'product cache and per-vertex scratch variables used by L_E008.'),
    0xE8CF: ('Arithmetic helpers',
             'Division, sign-magnitude averaging and face-normal dot products.'),
    0xEA51: ('Object contact and player laser',
             'Collision, fuel scooping and docking when an object reaches the player,\n'
             'release of missile locks on removed objects, ship-slot reset and the\n'
             'per-frame player laser update.'),
}

LABELS = {
    # ---------------------------------------------------------------- renderer
    0xE008: ('DrawObjectInView', 'verified', """
Draw one object instance in the current space view.
IX = instance, IY = its blueprint; the caller's pushed AF (A = ObjectLoopCounter of the
object loop) lies just above the return address and is read by L_E0B5.
Returns at once unless CurrentScreenId is 0..3 (front, rear, left, right views) and the
object lies in front of that view: depth = z (front/rear) or x (left/right), and its
sign must match the view (front z>=0, rear z<0, left x<0, right x>=0).  Depth must
also exceed blueprint +1.  Projects the centre with L_E592 (ProjectedX/ProjectedY =
256*offset/depth, quadrant bits in ProjectedQuadrant) and the size (L_DA0B =
256*(blueprint +1)/depth).  Off-screen objects (offset - size >= 128 across or 64
down) only get their laser beam (L_E206).  Near the centre the object becomes the
crosshair target (L_E0B5) and may drop its avoidance flag (L_E0CB).
(IX+$20) bit 4 (destroyed) records the explosion position (L_E1D4) instead of
drawing; in MissionAspEncounterState 1 the marked ship (+$26 bit 6) is not drawn.
Depth high byte >= blueprint +$0B: 2x2 XOR dot; otherwise full wireframe (L_E175).
Clobbers AF, BC, DE, HL; IX and IY preserved.
Evidence: pipeline check (vertex buffer within 4 units of a float model in 1287 of
1292 vertices) and the p9 explosion, beam and avoidance checks in
tools/check_routines.py; runtime: every flight-view scenario.
NOTE: entered by JP from L_DFDD (title ship), the word above the return address is
not a loop counter; it is only stored when the crosshair test passes."""),
    0xE038: (None, 'verified', """
Centre projection: depth (DE) is beyond blueprint +1.  Front/rear: ProjectedX =
256*|x|/depth, ProjectedY = 256*|y|/depth; left/right: ProjectedX = 256*|z|/depth.
Pushes two copies of the depth above the stacked radius (blueprint +1)."""),
    0xE0B5: (None, 'verified', """
Crosshair target: D = ProjectedX + ProjectedY.  If below the projected size (L_DA0B)
and z high byte (IX+7) < $2C, store the caller's stacked AF high byte in L_DA12
(POP HL/POP AF/PUSH/PUSH reads below the return address).  From the object loop at
$DBA6 that byte is the remaining-slot counter pushed at $DA9A.
NOTE: (IX+7) is the z high byte even in the left/right views."""),
    0xE0CB: ('CancelAvoidanceInSights', 'verified', """
For counted (+$20 bit 6) hostile (+$21 bit 2) ships: if the local z axis component
along the view axis (+$0E in front/rear views, +$0A in left/right views) has magnitude
>= $40 (either sign) and ProjectedX+ProjectedY < $20, clear the avoidance flag
(IX+$26) bit 5, so the steering at L_F8B3 uses only the small $0200 box again.
B and E are loaded but unused.
Evidence: tools/check_routines.py pipeline/p9-avoidance-in-sights (all four gates,
both view axes)."""),
    0xE10E: (None, 'verified', """
Choose the drawing form: depth high byte < blueprint +$0B (visibility distance) ->
full wireframe at L_E175.  Otherwise plot a 2x2 XOR dot at (127 +/- ProjectedX,
63 +/- ProjectedY) when ProjectedX < $7F and ProjectedY < $3F; the rear and right
views mirror the horizontal sign (XOR 2).
Either way the beam test (L_E206) follows."""),
    0xE164: ('ToggleViewPixel', 'verified', """
XOR one pixel into the view bitmap: C = column 0..255, B = row 0..127 from the top.
Enters ROM PIXEL-ADD after its row inversion ($22B1: AND A first), so HL = screen
address of (C,B); SET 7,H moves it from $4000.. to ViewBitmapBuffer ($C000..).
Output: pixel toggled; B, C preserved; A = new byte; D, HL changed.
Caller: the 2x2 dot of distant objects (L_E152).
Evidence: a simulator check in tools/check_routines.py toggled 11008 (x,y) points,
each exactly one expected bit."""),
    0xE175: ('DrawObjectWireframe', 'verified', """
Full wireframe: BuildRotationMatrix; ObjectViewDepth becomes the detail level
min($1F, high byte of 2*depth) - 2 (not below 0); then ComputeFaceVisibility,
ProjectVertices and DrawVisibleEdges.  If (IX+$20) bit 3 is set (the ship fired its
laser this update, see TryFireAiLaser), draw the beam from the gun vertex (blueprint
+$14) through L_E1AC, which clears that bit.
Evidence: pipeline checks in tools/check_routines.py (object-projection, p9-ai-laser-beam)."""),
    0xE1AC: ('DrawAiLaserBeam', 'verified', """
Draw the laser beam of a firing ship: D,E = start (projected magnitudes), C = start
quadrant (bit 1 left, bit 0 below).  The far end is (255-r, r) for a random r in the
diagonally opposite quadrant, always beyond the view edge (255-r >= 128 or r >= 64),
so DrawLine runs from the start to the border.  Then (IX+$20) bit 3 is cleared.
L_F116 (the view-page operand $C0 of the plot address) is saved, given bit 7 and
restored; bit 7 is already set in $C0, so this has no effect in this build.
Clobbers all registers (DrawLine).
Evidence: tools/check_routines.py combat/p9-ai-laser-beam: the buffer equals the plain
drawing OR one DrawLine with these end points (dot, wireframe and off-screen cases)."""),
    0xE1D4: ('RecordExplosionPosition', 'verified', """
Object destroyed ((IX+$20) bit 4) and visible in this view: store its screen disc
parameters for DrawFlaggedObjectDiscs instead of drawing it: (IX+$1C) = ProjectedX
(CircleOffsetX), (IX+$1D) = ProjectedY (CircleOffsetY), (IX+$1F) = projected size
L_DA0B (CircleRadius), (IX+$1E) = $0C + side bits (CircleFlags: bit 0 right of the
centre, bit 1 above; mirrored in rear/right views).  Sets bit 5: state 11, which
DrawFlaggedObjectDiscs draws as 15 growing filled discs and then ends with bit 4
cleared (state 10: removed and credited by L_DB0F).  An object that is behind or off
this view never gets here and the object loop turns state 01 into 10 directly.
Evidence: tools/check_routines.py pipeline/p9-explosion-record (all four views)."""),
    0xE206: ('DrawAiBeamFromCentre', 'verified', """
Object drawn as a dot, off-screen, or the marked ship in MissionAspEncounterState 1:
if (IX+$20) bit 3 is set, draw the AI laser beam from the projected centre
(ProjectedX, ProjectedY, ProjectedQuadrant mirrored in the rear/right views) via
L_E1AC.  Evidence: tools/check_routines.py combat/p9-ai-laser-beam."""),
    # --------------------------------------------------------------- workspace
    0xE222: ('ProjectedVertexBuffer', 'verified', """
Projected vertices, 3 bytes each, indexed by vertex number: ProjectedX, ProjectedY,
then quadrant bits (bit 1 = left of centre, bit 0 = below centre) or $FF when the
vertex is behind the view.  Written at $E6FC, read by L_E778.  138 bytes = room for
46 vertices; the largest blueprint has 28 (runtime writes cover $E222..$E275).
The first 8 initial bytes repeat code bytes $E21A..$E221: stale assembly leftovers,
overwritten before use."""),
    0xE2AC: ('FaceVisibilityFlags', 'verified', """
One byte per face index 0..15: 1 = visible, 0 = hidden.
ComputeFaceVisibility writes entries 0..face count-1 (at most 14); entries 14 and
15 keep their initial 1, so face nibble
15 in vertex/edge records means 'always visible'.  A blueprint without faces (alloy
plate) sets entry 0 to 1.  Read through L_E348."""),
    0xE2BC: ('RotationMatrix', 'verified', """
3 rows of 3 words (row stride 6): row r holds the r-th components of orientation
vectors X, Y, Z (instance +$16/+$10/+$0A + 2r).  Only the high (odd) bytes are
written, by BuildRotationMatrix; the even bytes are unused (initial bytes stale).
Rotated vertex coordinate r = x*row[0] + y*row[1] + z*row[2] (RotateRow)."""),
    0xE2CE: ('RowProductCache', 'verified', """
Per matrix row, three terms (magnitude byte, sign byte) of the last rotated vertex,
written by RotateRow/L_E3B4 at IY+$12..$17.  Reused with sign flips
(ReuseRowProducts, RotateRowPrecise) when the next vertex has the same magnitudes
(RowCacheInvalid = 0).  The initial bytes are stale."""),
    0xE2E0: ('ObjectViewDepth', 'verified', """
Word: depth magnitude of the object centre (z or x, see DrawObjectInView).
After $E18F the low byte is the detail level min($1F, high(2*depth)) - 2, clamped at 0, compared
with vertex/face/edge visibility thresholds (drawn when threshold = $1F or level
< threshold); levels 0..3 select the precise vertex path (L_E5CB)."""),
    0xE2E2: ('VertexBufferOffset', 'verified', """
Byte offset of the current vertex in ProjectedVertexBuffer; set to $FD before the
vertex loop and advanced by 3 per vertex at $E306."""),
    0xE2E3: ('VertexX', 'verified', """
Rotated, then (L_E607) view-relative vertex x as 16-bit sign-magnitude (bit 15 sign).
In left/right views x is the depth axis."""),
    0xE2E5: ('VertexY', 'verified', """
Rotated, then view-relative vertex y (16-bit sign-magnitude)."""),
    0xE2E7: ('VertexZ', 'verified', """
Rotated, then view-relative vertex z (16-bit sign-magnitude)."""),
    0xE2E9: ('ProjectedX', 'verified', """
Horizontal screen offset magnitude from the view centre: min(255, 256*h/depth) with
h = x (front/rear) or z (left/right).  Also used for the object centre."""),
    0xE2EA: ('ProjectedY', 'verified', """
Vertical screen offset magnitude: min(255, 256*|y|/depth)."""),
    0xE2EB: ('ProjectedQuadrant', 'verified', """
Bit 1 = horizontal sign, bit 0 = vertical sign of the projected point.  For vertices
the stored value is masked to 2 bits and already mirrored for the rear/right views;
for the object centre ($E086) the raw sign bits are stored and consumers mirror."""),
    0xE2EC: ('VertexSignX', 'verified', """
Sign byte (bit 7) of the view-relative VertexX from L_E478."""),
    0xE2ED: ('VertexSignY', 'verified', """
Sign byte (bit 7) of the view-relative VertexY."""),
    0xE2EE: ('VertexSignZ', 'verified', """
Sign byte (bit 7) of the view-relative VertexZ."""),
    0xE2EF: ('VertexNormaliseShift', 'verified', """
Precise vertex path: number of leading zero bits of |x| OR |y| OR |z| of the
model vertex (1..7).  Coordinates are shifted left by it before the 8-bit
multiplications (L_E447) and the sums shifted back with fraction bits (L_E40C)."""),
    0xE2F0: ('RowCacheInvalid', 'verified', """
0 = RowProductCache holds the products of the previous vertex; nonzero after a
vertex was skipped ($E330), so the next vertex recomputes its products."""),
    0xE2F1: ('ProjectVertices', 'verified', """
Rotate, translate and project every vertex of the blueprint into
ProjectedVertexBuffer.  IX = instance, IY = blueprint; RotationMatrix,
FaceVisibilityFlags and ObjectViewDepth (detail level) must be prepared.
A vertex is processed when its threshold allows the detail level and one of its four
faces (two nibbles in each of bytes 4 and 5) is visible; other entries keep stale
data (edges test the same faces).  Each processed vertex goes through L_E5CB
(rotation, precise or normal) and L_E607 (translation, projection, buffer entry).
Output: buffer filled, RowCacheInvalid updated; IX, IY restored.  Clobbers AF, BC, DE, HL.
Evidence: pipeline check against a float model; runtime flight scenarios."""),
    0xE306: (None, 'verified', """
Per-vertex loop: A = vertices left (pushed), IX = vertex record, IY = RotationMatrix."""),
    0xE338: ('TestFacePairVisible', 'verified', """
A = byte with two face nibbles.  NZ if FaceVisibilityFlags of either nibble is set
(low nibble tested first, high nibble returned in B and tested second); A = the last
flag read.  Clobbers A, B, HL."""),
    0xE348: ('TestFaceVisible', 'verified', """
A = face index 0..15.  A = FaceVisibilityFlags[index], Z if hidden.  HL = entry."""),
    0xE353: ('RotateRowPrecise', 'verified', """
Precise path, one matrix row (IY = row, IX = vertex record): sum of the three
products of the vertex magnitudes shifted left by VertexNormaliseShift with the row's
sign-magnitude bytes; reuses RowProductCache when RowCacheInvalid = 0 and the
vertex magnitudes equal the previous record's (IX-6..IX-4).  Shifts back in L_E40C:
HL = 16-bit sign-magnitude sum, A = fraction bits.  IY advances by 6."""),
    0xE40C: (None, 'verified', """
Shift HL right by VertexNormaliseShift, collecting the dropped bits in A (fraction),
then restore the sign from the original H bit 7.  The INC HL rounding branch
cannot be taken because the shift count is at most 7."""),
    0xE447: (None, 'verified', """
B = vertex magnitude << VertexNormaliseShift, C = |row entry (IY+1)|;
HL = MultiplyUnsignedHigh(B, C) (H = 0).  DE preserved."""),
    0xE478: ('TranslateVertexAxis', 'verified', """
Add a rotated vertex term to an instance coordinate.  HL = 16-bit magnitude, B = sign
byte (bit 7) of the instance coordinate; DE = rotated value (sign-magnitude), doubled
with the caller's carry (fraction bit 7) as new bit 0.  Output: HL = |sum|, A = sign.
When the coordinate is the larger magnitude of a difference, it subtracts the fraction
too: it negates the fraction in the caller's stacked AF (POP DE/POP AF/NEG/PUSH AF/
PUSH DE) and decrements HL (also when that fraction is 0, one unit low then)."""),
    0xE49C: (None, 'verified', """
Normal-precision path (detail level >= 4, or a vertex whose largest magnitude already
uses bit 7): three RotateRow row products (ReuseRowProducts for a vertex with the
previous record's magnitudes) into VertexX/Y/Z; fraction bytes cleared; continues
at L_E607."""),
    0xE4E9: ('ReuseRowProducts', 'verified', """
Mirrored-vertex shortcut: the vertex at IX has the same magnitudes as the previous
record (IX-6), so flip the signs of the cached RowProductCache terms where the sign
bits differ ((IX+3) XOR (IX-3)) and re-add them.  HL = L magnitude, H sign; IY += 6."""),
    0xE52A: ('RotateRow', 'verified', """
One matrix row times the vector at IX (bytes 0..2 magnitudes, byte 3 bits 7/6/5
signs): HL = sum of MultiplyUnsignedHigh(|v_i|, |row_i|) with signs (L = magnitude,
H bit 7 = sign); the three terms are cached at IY+$12..$17.  IY = row, advanced by 6.
With row entries of about 127 the result is about half the vector component.
Used for vertices and, through L_EA03, for face normals."""),
    0xE592: ('DivideRatioByte', 'verified', """
C = 256 * (DE:C) / (HL:A), saturated to 255.  Both 24-bit values are shifted left
together (at most 8 steps) until the divisor fills HL, then the top 16 dividend bits
are divided by H (L_E5B4).  When the divisor normalises first, a quotient >= 1
returns 255 and smaller ones are exact or 1..3 too high (divisor truncated to H; less
accurate when the divisor is still below $8000 after the 8 shifts).
NOTE: a dividend with more significant bits than the divisor takes the overflow path
($E5A4), whose SCF re-inserts a set top bit into the divisor.  About half of these
inputs still return 255; the others return values below 255 for true ratios >= 1
(for example 144..249 for ratios 1.2..3.6).
Clobbers A, B, DE, HL.
Evidence: tools/check_routines.py (maths group), random cases against a Python model."""),
    0xE5B4: ('DivideByteFraction', 'verified', """
Restoring division loop: A:E / B with A < B; quotient bits are shifted into C until
the 0 bit of the initial C leaves it (C = $FE gives 8 bits).  L_F0CC enters here with
E = 0, C = $FE: C = A*256/B (the line slope of DrawLine).
Evidence: tools/check_routines.py (maths group), exact on all sampled cases."""),
    0xE5C8: ('VertexFractionX', 'verified', """
Fraction byte of VertexX from the precise path (0 in the normal path)."""),
    0xE5C9: ('VertexFractionY', 'verified', """
Fraction byte of VertexY."""),
    0xE5CA: ('VertexFractionZ', 'verified', """
Fraction byte of VertexZ."""),
    0xE5CB: (None, 'verified', """
Transform one visible vertex (IX = vertex record), entered by JP from ProjectVertices
with the vertex counter and the instance on the stack.  Detail level ObjectViewDepth
< 4 and a vertex whose largest magnitude is below $80 use the precise path (L_E353,
coordinates scaled up by VertexNormaliseShift), otherwise L_E49C; both continue at
L_E607.
NOTE: an all-zero vertex at levels 0..3 would loop forever at $E5E0; none of the 19
default blueprints has one."""),
    0xE607: (None, 'verified', """
Translate: VertexX/Y/Z = instance position + 2 * rotated vertex
(TranslateVertexAxis), then project: front/rear ProjectedX = 256*x/z,
ProjectedY = 256*y/z; left/right (L_E6AA) ProjectedX = 256*z/x, ProjectedY =
256*y/x.  Store the entry in ProjectedVertexBuffer ($FF quadrant when the depth
sign is behind the view)."""),
    0xE71A: (None, 'verified', """
Next vertex record (6 bytes).  INC DE has no effect on the result."""),
    0xE729: ('DrawVisibleEdges', 'verified', """
Draw every edge of the blueprint at IY whose visibility threshold allows the
detail level (ObjectViewDepth), one of whose two faces is visible and whose two
vertices are in front of the view.  Calls DrawLine with DE = vertex 1 (D across,
E down), HL = vertex 2, C = quadrant bits (bits 3..2 vertex 1, bits 1..0 vertex 2).
IX preserved.  Evidence: code; runtime flight scenarios."""),
    0xE778: ('GetProjectedVertex', 'verified', """
A = vertex index.  HL = ProjectedVertexBuffer + 3*A (+2 on return), D = ProjectedX,
E = ProjectedY, A = quadrant byte; NZ when bit 7 is set ($FF: behind the view).
B = index."""),
    0xE791: ('OrthogonaliseYVector', 'verified', """
IX = instance.  Remove from orientation vector Y (+$10/+$12/+$14) its component
along vector Z (+$0A/+$0C/+$0E): L_FB1F gives k = -(Z.Y)/128 (sign-magnitude),
then Y_i += k*Z_i/128 for each axis (L_E7B2).  Only the high bytes change.
IX, IY preserved (the per-axis helper advances copies of them).
Evidence: a simulator check in tools/check_routines.py: |cos(Z,Y)| up to 0.5 before,
at most 0.029 after (3000 cases)."""),
    0xE7B2: (None, 'verified', """
One axis of OrthogonaliseYVector: (IY+1) += E*(IX+1)/128 in sign-magnitude,
saturating at 127; IX and IY advance by 2."""),
    0xE7F3: ('BuildRotationMatrix', 'verified', """
IX = instance.  Compute orientation vector X = Y x Z / 128 (high bytes +$16, +$18,
+$1A, via L_E849) and fill RotationMatrix rows with (X_r, Y_r, Z_r): only those
three entries are products; the other six are copies of Y and Z.
Clobbers IY (= RotationMatrix), AF, BC, DE, HL.
Evidence: pipeline check: X within 1 unit of the float cross product."""),
    0xE849: ('ComputeCrossProductTerm', 'verified', """
B, C, D, E = sign-magnitude bytes.  HL = D*E - B*C as 16-bit sign-magnitude, where
the magnitudes are 2|a|*2|b| (MultiplyUnsigned) halved: |HL| = 2*|D*E - B*C|,
saturating at $7FFF.  H is the sign-magnitude high byte used by L_E7F3.
Evidence: tools/check_routines.py (maths group)."""),
    0xE88B: ('UnusedMultiplyWordHigh', 'verified', """
Unreferenced (no static, pointer or runtime reference) but complete routine:
HL = high word of (A:C) * (D:E) built from four MultiplyUnsigned partial products
(the low word accumulates in IX, which is restored).  Inherits the quarter-square
error, so HL can be lower than the exact high word.
Evidence: tools/check_routines.py (maths group) matches the partial-product model exactly.
stationslotfix=yes replaces these 68 bytes with StationSlotAlign."""),
    0xE8CF: ('DivideWordFraction', 'verified', """
BC = (HL*65536 + A*256) / DE, HL = remainder; requires HL < DE (otherwise the
quotient overflows and is wrong).  16 restoring-division steps; the sentinel 0 bit in
BC = $FFFE ends the loop.  Clobbers A, F.
Evidence: tools/check_routines.py (maths group): exact except on the overflow cases."""),
    0xE8F0: ('HalveDifferenceSignMagnitude', 'verified', """
HL = (HL - DE) / 2 for 16-bit sign-magnitude values (bit 15 sign): negates DE's sign
and continues in L_E8F4.
Callers form half the per-axis difference of two positions
(L_712C: sun minus station; L_F9B2: missile target minus missile); bit 15 of the
result is set when the first position is the smaller one."""),
    0xE8F4: ('HalveSumSignMagnitude', 'verified', """
HL = (HL + DE) / 2 for 16-bit sign-magnitude values (bit 15 sign); the result takes
the sign of the larger magnitude (HL's on a tie), B bit 7 = that sign, carry = the
dropped bit.  Evidence: tools/check_routines.py (maths group), both entries."""),
    0xE917: ('FaceInstancePointer', 'verified', """
Instance pointer saved by ComputeFaceVisibility; ComputeFaceAxis walks it
through x, y, z."""),
    0xE919: ('NormalScaleShift', 'verified', """
Blueprint +$13 copied by ComputeFaceVisibility: face normals are scaled by 2/2^n
before being added to the object position (ComputeFaceAxis)."""),
    0xE91A: ('FacePointX', 'verified', """
(object x + 2*normal x / 2^NormalScaleShift) / 2, 16-bit sign-magnitude; read by
L_E9AE through IY."""),
    0xE91C: ('FacePointY', 'verified', """
Same for y."""),
    0xE91E: ('FacePointZ', 'verified', """
Same for z."""),
    0xE920: ('FaceNormalX', 'verified', """
Rotated face normal x (sign-magnitude byte from RotateRow); read by
ComputeFaceDotProduct through IX."""),
    0xE921: ('FaceNormalY', 'verified', """
Rotated face normal y."""),
    0xE922: ('FaceNormalZ', 'verified', """
Rotated face normal z."""),
    0xE923: ('ComputeFaceVisibility', 'verified', """
IX = instance, IY = blueprint, RotationMatrix and the detail level ready.  For each
face: hidden (0) when its threshold excludes the detail level, otherwise rotate the
normal, form FacePoint = (position + scaled normal)/2 and set the flag to 1 when
the dot product with the rotated normal is negative (facing the viewer).
Output: FaceVisibilityFlags; RowProductCache is overwritten by the normal rotations.
IX, IY restored.
Evidence: pipeline check: 1341 of 1353 faces match the float model; the others
have small rotated normals where the 8-bit truncations decide; runtime flight."""),
    0xE9AE: ('ComputeFaceDotProduct', 'verified', """
IX = 3 sign-magnitude bytes (normal), IY = 3 sign-magnitude words (point):
HL = (n_x*p_x + n_y*p_y + n_z*p_z) / 128 / 2 in 16-bit sign-magnitude, via
MultiplyNormalByCoordinate and HalveSumSignMagnitude (the y+z partial sum is
doubled back, so only the final sum is halved).  ComputeFaceVisibility uses only
the sign."""),
    0xE9E4: ('MultiplyNormalByCoordinate', 'verified', """
A = sign-magnitude byte n, E:C = sign-magnitude word p.  HL ~ |n|*|p|/128 (2|n|
times p_hi plus the high byte of 2|n| times p_lo; quarter-square rounding can make
it up to 128 lower) with bit 15 = sign(n) XOR sign(p), bit 15 of the product lost.
Evidence: tools/check_routines.py (maths group) matches this model exactly."""),
    0xEA03: ('ComputeFaceAxis', 'verified', """
One axis of a face: rotate the normal by the current matrix row (L_E52A, IY += 6),
read the next instance coordinate through the pointer below the return address
(advanced by 3), and return A = rotated normal component and HL = (coordinate +
2*normal/2^NormalScaleShift)/2, both sign-magnitude."""),
    0xEA4F: ('LaserBeamQuadrant', 'verified', """
Random quadrant bits (random byte AND $0C = DrawLine bits 3..2 of the first end)
stored by DrawLaser and reused for its later beam lines."""),
    0xEA50: ('LaserTriggerHeld', 'verified', """
1 = the previous UpdatePlayerLaser call accepted a fire request (key, temperature and
a laser on the current view), whether or not the rate test then let it fire; 0 = no
request.  UpdatePlayerLaser reads and clears it on every call.  While it is set,
pulse and mining lasers fire only on frames where ObjectUpdateCounter AND 1 / AND 7
is 0; a fresh press fires at once.
Evidence: tools/check_routines.py combat/p9-player-laser-rate."""),
    # --------------------------------------------------------- object contact
    0xEA51: ('HandleObjectContact', 'verified', """
Contact between the player and the object at IX (blueprint IY), called by the object
loop (L_DBA3) before drawing.  Nothing happens while PlayerDeadFlag is set or unless
|x|, |y| and |z| (16-bit magnitudes; z must also have no higher bits) are all below
the contact radius: blueprint +1; +256 for a missile (+$26 bit 0) whose target code
+$25 is 0 (the player); $B4 for scoopable objects (+$26 bit 1: set with $0A on the
canisters, capsules, splinters and alloy plates launched from a parent by L_F592 and
L_F5B8, and on orphaned Thargons at L_F80C).
Scoopable objects below the player (y < 0) with FuelScoopsFitted are removed
(energy 0, ReleaseTargetLocks) and, if CargoFreeSpace is nonzero, added through
ScoopCargoItem: commodity (blueprint +0 >> 4) + 1 (capsule slaves, alloy plate
alloys, splinter minerals, Thargon alien items); nibble 0 (canister): random 0..7, or
the cloaking device ($FF) when MissionAspEncounterState is 3 (state then 0).
Otherwise: the station (+$26 bit 2) runs TestStationDocking, everything else
CollideWithObject (also a scoopable object above the player, without fuel scoops
or with a full hold).
Evidence: tools/check_routines.py contact/p9-object-contact, contact/p9-scooping and
contact/p9-station-docking; runtime: entry executed in every flight scenario."""),
    0xEAD8: ('TestStationDocking', 'verified', """
Station contact ((IX+$26) bit 2; other objects go to CollideWithObject).
Crash (CrashIntoStation) unless the station's local z axis points at the player
(+$0E sign set), the station is ahead (z sign clear), it is not hostile (+$21 bit 2)
and |Z.x|, |Z.y| < $6E (compared as 2*magnitude with $DC).  Both below $1E: L_DA15 =
1, and CheckDocking docks on its next call.  Otherwise a scrape: SoundEffectRequests
bit 6 and FrontDamageThisUpdate += 12 + 2*PlayerSpeed (again on every update while
in contact).  The contact box, not the slot position, decides; the roll of the
station is not tested.  The station keeps its energy.
Evidence: tools/check_routines.py contact/p9-station-docking."""),
    0xEB23: ('CollideWithObject', 'verified', """
Collision with the object at IX: it is removed (energy 0).  Damage B = $50, plus the
object's energy for a missile (+$26 bit 0).  The marked mission ship (+$26 bit 6)
also ends MissionAspEncounterState.  SoundEffectRequests bit 2 is requested and B is
added to RearDamageThisUpdate (object behind, z negative) or FrontDamageThisUpdate
(L_EB5E); both paths end in ReleaseTargetLocks.
NOTE: the station never comes here; L_EB58 is its crash path.
Evidence: tools/check_routines.py contact/p9-object-contact and contact/p9-scooping."""),
    0xEB58: ('CrashIntoStation', 'verified', """
Failed docking: PlayerDeadFlag = $0F, so the main loop starts RunGameOverSequence.
Evidence: tools/check_routines.py contact/p9-station-docking (bad alignment, station
behind, slot facing away, hostile station)."""),
    0xEB65: ('ReleaseTargetLocks', 'verified', """
An object is being removed (destroyed, scooped, collided or out of range); H =
ObjectLoopCounter, the counter of that object.  If the removed object IX is itself a
missile (+$26 bit 0), every live object in slots 1..7 whose +$25 equals H gets
+$20 bit 4 (explosion).  Then, if MissileState = 2 and MissileTarget = H, the
player's missile lock ends: MissileState = 0 and TargetLostMessage bit 7 raised.
IY preserved; returns DE = InstanceSize, B = 0.
NOTE: the bit 0 test reads the removed object, not the scanned slot.  A missile
locked on a removed ship therefore survives, and a ship whose +$25 AI state happens
to equal the counter of a removed missile explodes.
Evidence: tools/check_routines.py contact/p9-release-target-locks; runtime: executed
in the flight scenarios (callers L_DB43, L_DCF3, L_EAAC and the collision path)."""),
    0xEBA4: ('ClearAllShipSlots', 'verified', """
Set SoundEffectRequests bit 2, select the front view (CurrentScreenId = 0), zero the
energy byte (+$22) of all 8 ship slots (energy 0 = free slot: FindFreeShipSlot,
update loop $DA9F), then DispatchShipEvent $16 (one cargo canister near the player,
SpawnCargoCanister with C odd) and $15 (two alloy plates near the player,
SpawnAlloyPlatePair with C odd): the wreckage shown after the player's death.
Evidence: only caller is the GAME OVER sequence at $7348."""),
    0xEBC7: ('UpdatePlayerLaser', 'verified', """
Per-frame player laser update (continues into ApplyPlayerLaserHit / DrawLaser).
LaserTemperature -= 2, floored at 0.  Fires only when KeyFlagsCombat bit 0 is set
(then cleared), LaserTemperature is then below $90 and the LaserMounts byte for
CurrentScreenId (1 pulse, 2 beam, 3 military, 4 mining) is nonzero.  Then
LaserTriggerHeld = 1.  Pulse lasers set D = 1, mining lasers D = 7: when
LaserTriggerHeld was already set, (ObjectUpdateCounter AND D) must be 0.  Firing
(L_EC11) increments L_DA17, sets SoundEffectRequests bit 4 and raises
LaserTemperature by a type-dependent amount (capped at $A0).
Evidence: tools/check_routines.py combat/p9-player-laser-rate (all types and views,
key release, temperature limits)."""),
}

COMMENTS = {
    # DrawObjectInView
    0xE001: 'IX = slot 7 instance (title/demo object of L_DFDD)',
    0xE008: 'views 0..3 only (front, rear, left, right)',
    0xE00E: 'other screens: nothing to draw',
    0xE012: 'left/right view: depth axis is x (+0), else z (+6)',
    0xE016: 'front/rear views: depth is z',
    0xE01A: 'DE = depth magnitude',
    0xE01E: 'C = depth sign byte',
    0xE01F: 'bit 7 = view bits 0 XOR 1 ...',
    0xE023: '... XOR depth sign: set means behind the view',
    0xE026: 'behind this view: not drawn',
    0xE027: 'ObjectViewDepth = 16-bit depth magnitude',
    0xE02D: 'blueprint +1: object radius',
    0xE030: 'radius kept for the size projection',
    0xE034: 'draw only when depth > radius',
    0xE036: 'too close: drop the radius, return',
    0xE038: 'depth copies for the next two divisions',
    0xE03C: 'left/right views use z across',
    0xE03E: 'HL = depth (divisor)',
    0xE045: 'no fraction bytes (A, C = 0)',
    0xE047: 'ProjectedX = 256*|x|/depth',
    0xE057: 'ProjectedY = 256*|y|/depth',
    0xE05E: 'B = x sign byte (horizontal sign)',
    0xE06C: 'ProjectedX = 256*|z|/depth (left/right views)',
    0xE07C: 'ProjectedY = 256*|y|/depth',
    0xE083: 'B = z sign byte (horizontal sign)',
    0xE086: 'y sign byte; bit 1 = horizontal sign, bit 0 = y sign',
    0xE08D: 'raw signs: not mirrored for rear/right',
    0xE090: 'HL = depth, DE = radius',
    0xE094: 'projected size = 256*radius/depth',
    0xE099: 'L_DA0B = projected size',
    0xE0A2: 'ProjectedY < size: overlaps row 63',
    0xE0A4: 'ProjectedY - size >= 64: off-screen',
    0xE0A6: 'off-screen: only a laser beam',
    0xE0AE: 'ProjectedX < size: overlaps column 127',
    0xE0B0: 'ProjectedX - size >= 128: off-screen',
    0xE0B2: 'off-screen: only a laser beam',
    0xE0B7: 'D = ProjectedX + ProjectedY',
    0xE0B8: 'over 255: far from the crosshair',
    0xE0BA: 'inside the projected size?',
    0xE0C0: 'z high byte < $2C',
    0xE0C4: 'peek at the caller\'s stacked AF (update-loop counter)',
    0xE0C8: 'L_DA12 = counter of the object under the crosshair',
    0xE0CF: 'not counted: skip',
    0xE0D5: 'not hostile: skip',
    0xE0DC: 'front/rear: local z axis, z part',
    0xE0DF: 'E is not used',
    0xE0E4: 'left/right: local z axis, x part',
    0xE0ED: '|component| >= $40: aimed along the view axis',
    0xE0F2: 'near the crosshair (sum < $20)',
    0xE0F6: 'drop the avoidance flag',
    0xE0FA: 'bit 4: destroyed, record its position',
    0xE101: 'state 1 hides the marked mission ship',
    0xE10B: 'marked ship: beam only',
    0xE112: 'blueprint +$0B: wireframe when depth high byte below it',
    0xE11A: 'dot only inside the view',
    0xE11C: 'too far off-centre for a dot: beam only',
    0xE123: 'ProjectedY < $3F',
    0xE12C: 'views 1 (rear) and 3 (right)',
    0xE133: 'rear/right view mirrors the horizontal sign',
    0xE136: 'bit 1: left of the centre',
    0xE13B: 'C = 127 + ProjectedX',
    0xE142: 'C = 127 - ProjectedX',
    0xE144: 'bit 0: below the centre',
    0xE149: 'B = 63 + ProjectedY (row from the top)',
    0xE150: 'B = 63 - ProjectedY',
    0xE152: '2x2 dot: (C,B), (C,B+1), (C+1,B+1), (C+1,B)',
    0xE161: 'then the beam if it fires',
    # ToggleViewPixel
    0xE165: 'HL = screen address of (C,B), A = C AND 7',
    0xE169: 'D = bit number + 1',
    0xE16C: 'A = $80 >> (C AND 7)',
    0xE170: '$4000.. screen address -> $C000.. ViewBitmapBuffer',
    0xE172: 'toggle the pixel',
    # DrawObjectWireframe
    0xE177: 'clobbers IY',
    0xE17F: 'HL = 2*depth; carry: beyond 16 bits',
    0xE180: 'detail level = min($1F, high byte of 2*depth) ...',
    0xE18A: '... minus 2, not below 0',
    0xE18F: 'from here the low byte is the detail level',
    0xE192: 'vertex buffer offset starts at -3',
    0xE1A0: 'bit 3: this ship fires its laser',
    0xE1A5: 'blueprint +$14: gun vertex',
    0xE1A8: 'D,E = gun vertex, A = its quadrant',
    # DrawAiLaserBeam
    0xE1AC: 'r = random byte',
    0xE1AF: 'L = r: far end |y|',
    0xE1B0: 'A = r - 255 ...',
    0xE1B4: '... negated: H = 255 - r, far end |x|',
    0xE1B6: 'far end: opposite quadrant',
    0xE1B9: 'start quadrant to bits 3..2',
    0xE1BF: 'view page operand of the plot address',
    0xE1C3: 'already set in $C0: no effect',
    0xE1C8: 'from the start (DE) to the view edge',
    0xE1CC: 'restore the operand',
    0xE1CF: 'beam drawn: clear the firing flag',
    # RecordExplosionPosition
    0xE1D7: '+$1C: CircleOffsetX for the explosion discs',
    0xE1DD: '+$1D: CircleOffsetY',
    0xE1E3: '+$1F: CircleRadius (projected size)',
    0xE1E9: 'views 1 and 3 mirror horizontally',
    0xE1F6: 'vertical sign into A ...',
    0xE1F9: '... then horizontal: bit 1 vert., bit 0 horiz.',
    0xE1FA: 'invert: bit 0 right, bit 1 above',
    0xE1FC: '$0C + inverted quadrant bits',
    0xE1FE: '+$1E: CircleFlags',
    0xE201: 'bits 5:4 = 11: DrawFlaggedObjectDiscs draws it',
    # DrawAiBeamFromCentre
    0xE20E: 'D = horizontal offset of the centre',
    0xE212: 'E = vertical offset',
    0xE216: 'views 1 and 3 mirror horizontally',
    0xE220: 'beam from the object centre',
    # ProjectVertices
    0xE2F3: 'second copy becomes IX ...',
    0xE2F5: 'blueprint +3: vertex count',
    0xE2F8: '... IX = blueprint, instance saved',
    0xE2FA: 'blueprint +$0C/$0D: vertex table offset',
    0xE300: 'IX = first vertex record',
    0xE302: 'IY = matrix row 0',
    0xE30A: 'three bytes per projected vertex',
    0xE30F: 'vertex visibility threshold (bits 0..4)',
    0xE314: '$1F: visible at any distance',
    0xE31D: 'detail level >= threshold: skip',
    0xE31F: 'face nibbles of the vertex (bytes 4 and 5)',
    0xE32D: 'a face is visible: transform it',
    0xE330: 'skipped: RowCacheInvalid becomes nonzero',
    0xE334: 'A = vertices left',
    # TestFacePairVisible / TestFaceVisible
    0xE339: 'B = high nibble',
    0xE341: 'A = low nibble',
    0xE346: 'first face visible: NZ',
    0xE347: 'then the high-nibble face',
    0xE34B: 'HL = FaceVisibilityFlags + A',
    0xE351: 'Z: hidden',
    # RotateRowPrecise
    0xE353: 'cache valid only after a processed vertex',
    0xE359: 'same magnitudes as the previous vertex?',
    0xE371: 'B = sign differences from the previous vertex',
    0xE378: 'cached x term (magnitude, sign)',
    0xE37E: 'cached y term',
    0xE384: 'flip the x term where the x signs differ',
    0xE38B: 'y sign difference to bit 7',
    0xE395: 'x term + y term',
    0xE399: 'cached z term',
    0xE3A0: 'z sign difference to bit 7',
    0xE3A8: '+ z term',
    0xE3AC: 'next matrix row',
    0xE3B1: 'scale the sum back',
    0xE3B4: 'x magnitude',
    0xE3B7: 'L = (|x| << shift) * |row x| / 256',
    0xE3BA: 'term sign = x sign XOR row sign',
    0xE3C3: 'cache the x term',
    0xE3C9: 'DE = x term',
    0xE3CE: 'y magnitude',
    0xE3D1: 'same for y',
    0xE3D4: 'y sign (bit 6) XOR row sign',
    0xE3E4: 'x term + y term',
    0xE3ED: 'z magnitude',
    0xE3F0: 'same for z',
    0xE3F3: 'z sign (bit 5) XOR row sign',
    0xE404: '+ z term',
    # L_E40C
    0xE40F: 'B = shift count',
    0xE411: 'C = sign byte',
    0xE414: 'shift right, dropped bits into A',
    0xE41B: 'never taken: at most 7 shifts',
    0xE41E: 'restore the sign',
    # AddSignMagnitude (header in core.py)
    0xE426: 'carry = signs differ',
    0xE42A: 'same signs: L + E, carry = overflow',
    0xE42D: 'different signs: L - E',
    0xE42E: 'L >= E: H keeps its sign',
    0xE42F: 'E > L: magnitude E - L ...',
    0xE432: '... with D\'s sign',
    # MultiplyUnsignedHigh (header in core.py)
    0xE438: '|B - C|',
    0xE43A: 'd = |B - C| >> 1',
    0xE43F: 'D = high byte of d*d',
    0xE442: 's = (B + C) >> 1 with the 9th bit',
    0xE445: 'A = high(s*s) - high(d*d)',
    # L_E447
    0xE44A: 'B <<= VertexNormaliseShift',
    0xE44F: 'C = |matrix entry|',
    0xE458: 'HL = product high byte',
    # MultiplyUnsigned (header in core.py)
    0xE463: 'd = |B - C| >> 1',
    0xE468: 'DE = d*d',
    0xE46E: 's = (B + C) >> 1 with the 9th bit',
    0xE470: 'HL = s*s',
    0xE475: 'HL = s*s - d*d',
    # TranslateVertexAxis
    0xE478: 'C = sign of the rotated value',
    0xE479: 'DE = 2*|value| + caller\'s carry',
    0xE47F: 'signs differ?',
    0xE481: 'same signs: add magnitudes',
    0xE484: 'coordinate - value',
    0xE488: 'value larger: value - coordinate ...',
    0xE48D: '... with the value\'s sign',
    0xE48F: 'difference 0: no borrow',
    0xE493: 'borrow from the fraction in the ...',
    0xE495: '... caller\'s stacked A',
    0xE499: 'integer part - 1',
    0xE49A: 'A = coordinate sign',
    # L_E49C
    0xE49C: 'cache usable?',
    0xE4A4: 'compare the three magnitudes',
    0xE4B4: 'same magnitudes: re-sign the cache',
    0xE4CA: 'VertexX = row 0 . v',
    0xE4D0: 'VertexY = row 1 . v',
    0xE4D6: 'VertexZ = row 2 . v',
    0xE4DC: 'normal path: no fraction bits',
    0xE4E6: 'translate and project',
    # ReuseRowProducts
    0xE4E9: 'sign differences from the previous vertex',
    0xE4F0: 'cached x term',
    0xE4F6: 'cached y term',
    0xE4FC: 'flip the x term where the signs differ',
    0xE503: 'y sign difference to bit 7',
    0xE50D: 'x term + y term',
    0xE511: 'cached z term',
    0xE518: 'z sign difference to bit 7',
    0xE520: '+ z term',
    0xE524: 'next matrix row',
    # RotateRow
    0xE52A: 'x magnitude',
    0xE52D: '|row x|',
    0xE532: 'L = |x|*|row x|/256',
    0xE536: 'term sign = x sign XOR row sign',
    0xE53F: 'cache term 1',
    0xE545: 'DE = term 1',
    0xE546: 'y magnitude',
    0xE549: '|row y|',
    0xE554: 'y sign (bit 6) XOR row sign',
    0xE55E: 'cache term 2',
    0xE564: 'term 1 + term 2',
    0xE569: 'z magnitude',
    0xE56C: '|row z|',
    0xE577: 'z sign (bit 5) XOR row sign',
    0xE582: 'cache term 3',
    0xE588: '+ term 3',
    0xE58C: 'next matrix row',
    # DivideRatioByte / DivideByteFraction
    0xE592: 'at most 8 normalising shifts',
    0xE595: 'divisor not normalised after 8',
    0xE597: 'divisor HL:A << 1',
    0xE59A: 'top bit left HL: normalised',
    0xE59C: 'dividend DE:C << 1',
    0xE5A2: 'no dividend overflow: next step',
    0xE5A4: 'dividend overflow: undo its shift ...',
    0xE5A8: '... and set the divisor top bit',
    0xE5A9: 'divisor >> 1 with carry in bit 15',
    0xE5AE: '255 when not below the divisor',
    0xE5B2: 'B = divisor high byte',
    0xE5B3: 'C = $FE: 8 quotient bits',
    0xE5B4: 'next dividend bit into A',
    0xE5B7: 'A overflowed: subtract',
    0xE5B9: 'A >= B: subtract',
    0xE5BC: 'quotient bit 0',
    0xE5BE: 'sentinel left C: done',
    0xE5C1: 'subtract the divisor',
    0xE5C3: 'quotient bit 1',
    # L_E5CB
    0xE5D0: 'detail levels 0..3: precise path',
    0xE5D5: 'leading zero bits of |x| OR |y| OR |z|',
    0xE5E1: 'until the top set bit leaves A',
    0xE5E9: 'bit 7 already used: normal path',
    0xE5EC: 'VertexX = row 0 . v',
    0xE5F5: 'VertexY = row 1 . v',
    0xE5FE: 'VertexZ = row 2 . v',
    # L_E607
    0xE607: 'the next vertex may use the cache',
    0xE60B: 'IY = RotationMatrix again',
    0xE60D: 'HL = vertex counter (AF)',
    0xE60E: 'IX = instance, vertex pointer saved',
    0xE611: 'instance x (16-bit magnitude, sign byte)',
    0xE61A: 'DE = rotated x',
    0xE621: 'carry = fraction bit 7, consumed by L_E478',
    0xE623: 'HL = |x + 2*rotated|, A = sign',
    0xE62C: 'doubled (or borrowed) fraction',
    0xE630: 'instance y',
    0xE64F: 'instance z',
    0xE66E: 'left/right view: depth axis is x',
    0xE67D: 'divisor z: HL from the last L_E478',
    0xE680: 'ProjectedX = 256*x/z',
    0xE695: 'ProjectedY = 256*y/z',
    0xE6A0: 'C bit 0 = x sign (across)',
    0xE6A6: 'B bit 0 = z sign (depth)',
    0xE6AA: 'DE = |z| (across)',
    0xE6B5: 'ProjectedX = 256*z/x',
    0xE6CA: 'ProjectedY = 256*y/x',
    0xE6D5: 'B bit 0 = x sign (depth)',
    0xE6DB: 'C bit 0 = z sign (across)',
    0xE6E1: 'C bit 1 = across sign, bit 0 = y sign',
    0xE6EB: 'rear/right view mirrors the horizontal sign',
    0xE6ED: 'quadrant bits only',
    0xE6F5: 'HL = ProjectedVertexBuffer + VertexBufferOffset',
    0xE700: 'entry +0: ProjectedX',
    0xE705: 'entry +1: ProjectedY',
    0xE70B: 'carry = view bits 0 XOR 1 XOR depth sign',
    0xE714: '$FF: vertex behind the view',
    0xE716: 'entry +2: quadrant or $FF',
    0xE718: 'IX = vertex record, instance saved',
    # L_E71A
    0xE71A: 'vertex records are 6 bytes',
    0xE71F: 'unused',
    0xE724: 'IX = instance',
    # DrawVisibleEdges
    0xE729: 'blueprint +$0E/$0F: edge table offset',
    0xE72F: 'blueprint +4: edge count',
    0xE734: 'IX = blueprint, instance saved',
    0xE736: 'IX = first edge record',
    0xE739: 'edge visibility threshold',
    0xE73C: '$1F: drawn at any distance',
    0xE745: 'detail level >= threshold: skip',
    0xE747: 'face nibbles of the edge',
    0xE74D: 'both faces hidden: skip',
    0xE74F: 'vertex 1',
    0xE755: 'behind the view: skip',
    0xE757: 'C = vertex 1 quadrant',
    0xE759: 'vertex 2',
    0xE75F: 'HL = vertex 2, DE = vertex 1',
    0xE761: 'behind the view: skip',
    0xE763: 'C = quadrants: vertex 1 bits 3..2, vertex 2 bits 1..0',
    0xE76A: 'from vertex 1 to vertex 2',
    0xE76D: 'B = edges left',
    0xE76E: 'edge records are 4 bytes',
    0xE775: 'IX = instance',
    # GetProjectedVertex
    0xE779: 'HL = buffer + 3*index',
    0xE789: 'D = ProjectedX',
    0xE78B: 'E = ProjectedY',
    0xE78D: 'A = quadrant byte',
    0xE78E: 'NZ: $FF, behind the view',
    # OrthogonaliseYVector
    0xE795: 'IY = instance, caller\'s IY saved',
    0xE797: 'IX+1 = vector Z (+$0A)',
    0xE79C: 'IY+1 = vector Y (+$10)',
    0xE7A0: 'A = -(Z.Y)/128, sign-magnitude',
    0xE7A3: 'E = k',
    0xE7A4: 'Y.x += k*Z.x/128',
    0xE7A7: 'Y.y += k*Z.y/128',
    0xE7AA: 'Y.z += k*Z.z/128',
    # L_E7B2
    0xE7B2: 'C = Z component',
    0xE7B6: 'B = 2|k|',
    0xE7B8: 'C = 2|Z component|',
    0xE7BA: 'A = |k*Z|/64',
    0xE7BF: 'sign of k*Z',
    0xE7C3: 'C = k*Z/128, sign-magnitude',
    0xE7C5: 'B = Y component',
    0xE7C9: 'A bit 7 = signs differ',
    0xE7CA: 'C = 2|term|, H bit 0 = term sign',
    0xE7CE: 'B = 2|Y|, H bit 0 = Y sign',
    0xE7D2: 'carry = signs differ',
    0xE7D6: 'same signs: 2|Y| + 2|term| ...',
    0xE7D9: '... saturating',
    0xE7DD: 'different: 2|Y| - 2|term|',
    0xE7E0: 'term larger: negate, term sign',
    0xE7E4: 'carry = result sign',
    0xE7E6: 'halve and attach the sign',
    0xE7E7: 'new Y component (high byte)',
    # BuildRotationMatrix
    0xE7F3: 'rows of 6 bytes; odd bytes used',
    0xE7F7: 'Z.y and Y.z',
    0xE7FD: 'Z.z and Y.y',
    0xE806: 'X.x = Y.y*Z.z - Y.z*Z.y (scaled)',
    0xE809: 'row 0 entry 1: X.x',
    0xE80F: 'row 2 entry 3: Z.z',
    0xE815: 'row 0 entry 2: Y.x',
    0xE81E: 'row 2 entry 2: Y.z',
    0xE824: 'X.y',
    0xE827: 'row 1 entry 1: X.y',
    0xE82D: 'row 0 entry 3: Z.x',
    0xE833: 'row 1 entry 2: Y.y',
    0xE839: 'row 1 entry 3: Z.y',
    0xE842: 'X.z',
    0xE845: 'row 2 entry 1: X.z',
    # ComputeCrossProductTerm
    0xE849: 'B = 2|b|; sign of b ...',
    0xE84C: '... XOR sign of c',
    0xE851: 'H bit 7 = sign of B*C',
    0xE858: 'A bit 7 = sign of D*E',
    0xE85A: 'A bit 7 = signs differ',
    0xE85E: 'bit 7 = sign of -B*C, bit 6 = differ',
    0xE862: 'HL = 2|b| * 2|c|',
    0xE867: 'HL = 2|d| * 2|e|',
    0xE86C: 'signs differ: add magnitudes',
    0xE873: 'saturate',
    0xE878: '|B*C| - |D*E| with -B*C\'s sign',
    0xE87E: 'D*E larger: other order ...',
    0xE883: '... with D*E\'s sign',
    0xE885: 'halve; sign into bit 15',
    # UnusedMultiplyWordHigh
    0xE88D: 'IX accumulates the low word',
    0xE899: 'C*E',
    0xE8A2: 'C*D',
    0xE8B3: 'A*E',
    0xE8C7: 'A*D',
    # DivideWordFraction
    0xE8CF: 'sentinel 0 bit: 16 quotient bits',
    0xE8D2: 'HL:A << 1',
    0xE8D7: 'bit out of HL: subtract anyway',
    0xE8D9: 'remainder - divisor',
    0xE8DB: 'fits: quotient bit 1',
    0xE8DD: 'restore: quotient bit 0',
    0xE8E2: 'sentinel left B: done',
    0xE8E8: 'quotient bit 1',
    # HalveDifferenceSignMagnitude / HalveSumSignMagnitude
    0xE8F1: 'negate DE\'s sign',
    0xE8F5: 'signs differ?',
    0xE8F6: 'B, C = original sign bytes',
    0xE8F8: 'magnitudes only',
    0xE900: 'same signs: add',
    0xE903: 'different: |HL| - |DE|',
    0xE905: 'HL larger: its sign',
    0xE907: 'DE larger: |DE| - |HL| ...',
    0xE90C: '... with DE\'s sign',
    0xE90D: 'halve, carry = dropped bit',
    0xE911: 'attach the sign',
    # ComputeFaceVisibility
    0xE929: 'IX = blueprint, instance on the stack',
    0xE92B: 'HL = instance',
    0xE92C: 'FaceInstancePointer = instance',
    0xE92F: 'blueprint +$10/$11: face table offset',
    0xE935: 'IX = first face record',
    0xE937: 'DE = first output flag',
    0xE93A: 'blueprint +$13: normal scale shift',
    0xE940: 'blueprint +5: face count',
    0xE944: 'IY = matrix row 0',
    0xE94A: 'no faces: face 0 visible',
    0xE94E: 'faces left',
    0xE950: 'face visibility threshold',
    0xE955: '$1F: any distance',
    0xE95E: 'detail level below threshold: test it',
    0xE961: 'hidden at this detail level',
    0xE966: 'instance pointer for ComputeFaceAxis',
    0xE96A: 'rotated normal x, face point x',
    0xE973: 'y',
    0xE97C: 'z',
    0xE985: 'drop the advanced pointer',
    0xE990: 'HL = (normal . point) / 256',
    0xE999: 'negative dot product: visible',
    0xE99E: 'store this face\'s flag',
    0xE9A0: 'face records are 4 bytes',
    # ComputeFaceDotProduct
    0xE9AE: 'E:C = point x',
    0xE9B4: 'A = normal x',
    0xE9B7: 'HL = n_x*p_x/128',
    0xE9C4: 'n_y*p_y/128',
    0xE9D1: 'n_z*p_z/128',
    0xE9D5: 'HL = (z + y)/2, carry = dropped bit',
    0xE9D8: 'undo the halving ...',
    0xE9DA: '... and restore the sign',
    0xE9E0: 'DE = x product',
    0xE9E1: 'HL = (x + y + z)/2',
    # MultiplyNormalByCoordinate
    0xE9E5: 'B = 2|n|',
    0xE9E9: 'E bit 7 = product sign',
    0xE9EB: 'A = 2|n| * p_lo / 256',
    0xE9F0: 'C = |p_hi|',
    0xE9F4: 'HL = 2|n| * |p_hi|',
    0xE9FB: '+ the low partial',
    0xE9FC: 'drop bit 15 ...',
    0xE9FD: '... carry = product sign ...',
    0xE9FE: '... into bit 15',
    # ComputeFaceAxis
    0xEA03: 'L = |rotated normal|, H = sign',
    0xEA06: 'return address; the instance pointer is below it',
    0xEA09: 'DE = |coordinate|',
    0xEA0F: 'A = its sign byte',
    0xEA12: 'pointer to the next coordinate',
    0xEA1B: 'C = coordinate sign',
    0xEA1C: 'NormalScaleShift',
    0xEA1F: 'L = 2|normal|',
    0xEA21: 'kept for the return value',
    0xEA24: 'L >>= shift + 1 ...',
    0xEA28: '... << 1: 2|n| / 2^shift',
    0xEA2B: 'signs differ?',
    0xEA31: 'same signs: add magnitudes',
    0xEA34: 'different: |coordinate| - |n|',
    0xEA3A: 'normal larger: other order, its sign',
    0xEA43: 'halve, sign into bit 15',
    0xEA4A: 'A = rotated normal, sign-magnitude',
    # HandleObjectContact
    0xEA51: 'nonzero: player dying, skip',
    0xEA56: 'D = 0: radius below 256',
    0xEA58: 'blueprint +1: radius',
    0xEA5B: 'missile?',
    0xEA61: 'target code 0: the player',
    0xEA67: 'missile at the player: radius + 256',
    0xEA69: 'scoopable?',
    0xEA6F: 'radius 180 for (IX+$26) bit 1 objects',
    0xEA79: '|x| >= radius: no contact',
    0xEA83: '|y| >= radius: no contact',
    0xEA8D: '|z| >= radius: no contact',
    0xEA8E: 'z sign byte bits 0..6 must be clear',
    0xEA98: 'not scoopable: station or collision',
    0xEA9A: 'y sign: object below the player?',
    0xEA9E: 'above: collision',
    0xEAA5: 'no fuel scoops: collision',
    0xEAA9: 'scooped: object removed',
    0xEAAC: 'release locks on it',
    0xEAB3: 'hold full: collision damage',
    0xEAB5: 'blueprint +0 high nibble',
    0xEAC0: 'commodity = nibble + 1',
    0xEAC3: 'canister: mission ship destroyed?',
    0xEACA: 'state 0 ...',
    0xEACD: '... item $FF: cloaking device',
    0xEAD3: 'random commodity 0..7',
    0xEAD5: 'add one ton (or the special item)',
    # TestStationDocking
    0xEADC: 'not the station: collision',
    0xEADE: 'local z axis must point at the player',
    0xEAE4: 'station must be in front (z positive)',
    0xEAEA: 'hostile station?',
    0xEAF3: '2*|Z.x| (sign shifted out)',
    0xEAF4: '2*|Z.x| < $DC',
    0xEAFD: '2*|Z.y| < $DC',
    0xEB01: '|Z.y| >= $1E: scrape',
    0xEB06: '|Z.x| >= $1E: scrape',
    0xEB0C: 'L_DA15 = 1: CheckDocking docks',
    0xEB13: 'sound request bit 6',
    0xEB1B: 'front damage 12 + 2*PlayerSpeed',
    # CollideWithObject
    0xEB23: 'B = its energy',
    0xEB27: 'object destroyed',
    0xEB2A: 'missile: its energy adds to the damage',
    0xEB31: 'damage $50 (+ energy for bit 0 objects)',
    0xEB34: 'marked mission ship?',
    0xEB3D: 'already 0: nothing to clear',
    0xEB41: 'MissionAspEncounterState = 0',
    0xEB47: 'sound request bit 2',
    0xEB49: 'z sign: object behind the player',
    0xEB53: 'rear damage',
    0xEB56: 'release locks on it',
    # CrashIntoStation
    0xEB5A: 'PlayerDeadFlag = $0F: game over',
    0xEB62: 'front damage, then release locks',
    # ReleaseTargetLocks
    0xEB65: 'H = counter of the removed object',
    0xEB69: 'caller\'s IY kept',
    0xEB6B: 'IY = slot 0; advanced before each test',
    0xEB6F: 'slot size',
    0xEB72: 'slots 1..7',
    0xEB76: 'live slot (energy nonzero)?',
    0xEB7C: 'its +$25 equals the removed counter?',
    0xEB82: 'tests the removed object, not this slot',
    0xEB88: 'start this object\'s explosion',
    0xEB90: 'missile locked (state 2) ...',
    0xEB96: '... on the removed object?',
    0xEB9B: 'MissileState = 0',
    0xEBA1: 'raise TARGET LOST',
    # ClearAllShipSlots
    0xEBA7: 'sound request bit 2',
    0xEBAA: 'front view',
    0xEBAD: 'IX = slot -1; advanced before each store',
    0xEBB1: 'slot size',
    0xEBB8: 'energy 0: slot free',
    0xEBBF: 'event $16: canister near the player',
    0xEBC4: 'event $15: two alloy plates',
    # UpdatePlayerLaser
    0xEBC7: 'flag from the previous frame',
    0xEBCC: 'cleared until a request is accepted',
    0xEBD8: 'LaserTemperature -= 2, not below 0',
    0xEBE0: 'fire request',
    0xEBE3: 'consume the request',
    0xEBE5: 'LaserTemperature >= $90: no fire',
    0xEBE8: 'B = cooled temperature (heat base at L_EC2A)',
    0xEBEC: 'laser byte for this view',
    0xEBF5: 'no laser on this view',
    0xEBF6: 'E = previous flag, C = laser type',
    0xEBFB: 'type 1: D = 1',
}

DATA = {
    0xE222: (0xE2AC, 'bytes', 12),
    0xE2AC: (0xE2BC, 'bytes', 16),
    0xE2BC: (0xE2CE, 'bytes', 6),
    0xE2CE: (0xE2E0, 'bytes', 6),
    0xE2E0: (0xE2E2, 'words', 1),
    0xE2E2: (0xE2E3, 'bytes', 1),
    0xE2E3: (0xE2E9, 'words', 1),
    0xE2E9: (0xE2F1, 'bytes', 1),
    0xE5C8: (0xE5CB, 'bytes', 1),
    0xE917: (0xE919, 'words', 1),
    0xE919: (0xE91A, 'bytes', 1),
    0xE91A: (0xE920, 'words', 1),
    0xE920: (0xE923, 'bytes', 1),
    0xEA4F: (0xEA51, 'bytes', 1),
}

SEEDS = {
    0xE88B: 'complete unreferenced routine: balanced PUSH IX..POP IX and three PUSH BC/DE '
            'pairs, four CALL MultiplyUnsigned, RET at $E8CE immediately before L_E8CF; '
            'simulated by a check in tools/check_routines.py (high word of a 16x16 product)',
}

FIELDS = {
    'RomPixelAddRow': (0x22B1, 'ROM PIXEL-ADD entry after the y inversion: A = B = row from '
                               'the top, C = column -> HL screen address, A = C AND 7'),
}

OPERANDS = {
    0xE001: 'ObjectSlot7',   # LD IX,$6159: slot 7
    0xE165: 'RomPixelAddRow',                        # CALL $22B1
    0xEB6F: 'InstanceSize',                          # LD DE,$0027
    0xEBAD: 'InitialRuntimeState-InstanceSize',      # LD IX,$6021: before slot 0
    0xEBB1: 'InstanceSize',                          # LD DE,$0027
    0xEBEC: 'LaserMounts',             # LD HL,$A83F: per-view laser bytes
}

# ToggleViewPixel (SET 7,H) needs ViewBitmapBuffer = FontBitmap at $C000; the generator
# already asserts FontBitmap-GameImage = $C000-$6048, so no extra assertion is added here.
