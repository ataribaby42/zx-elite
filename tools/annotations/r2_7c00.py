"""Workspace clearing, commander template copy and the circle/disc renderer ($7C00..$85FF).

Evidence: instruction semantics, runtime traces (docs/generated/runtime-xrefs.json) and
simulator checks with the 48K ROM and the reference image:
tools/check_routines.py circles/circle-renderer (outline/filled circles in the 256x128 view
buffer, centre offsets, flags, radius limit, clipping), tools/check_routines.py
circles/screen-circle-patching (the 32 patch pointers, the direct-screen circle at $8461,
the direct-screen discs of $8545 and the restore of every patched byte)
and tools/check_routines.py maths/half-chord-root (integer square root at $80ED, ClearBytes).
Pass 2 checks: missions/p2-hyperspace-key-latch, circles/p2-circle-offset-bit8,
circles/p2-span-end-locators and circles/p2-screen-circle-minimum-radius.
"""

SECTIONS = {
    0x7C09: ('Workspace clearing and commander template copy',
             'Small helpers: zero a byte range, free the ship slots, copy the JAMESON\n'
             'template into the active commander record.'),
    0x7C39: ('Hyperspace key latch and circle renderer workspace',
             'HyperspaceKeyLatch, then the parameters and work bytes of the circle/disc\n'
             'renderer DrawCircle.'),
    0x7C4B: ('Circle and filled-disc renderer',
             'Midpoint circle drawn row by row into the 256x128 view buffer (SET 7,H turns a\n'
             'ROM screen address $40xx..$4Fxx into $C0xx..$CFxx).  CircleOutlineFlag selects\n'
             'the outline code (L_8640, L_866E and the arc routines L_869C, L_8740,\n'
             'L_883C) or the filled spans here.  The view is drawn between x 8 and 247\n'
             '(half width $78) and rows 0..127.'),
    0x8461: ('Direct-screen circle variants (self-modifying code)',
             'DrawScreenCircle patches 32 operand/opcode bytes for a 256x192 screen circle and\n'
             'restores them; DrawFlaggedObjectDiscs/PatchDiscRendererTarget switch the filled\n'
             'path to the screen top 128 lines and back.'),
}

LABELS = {
    # ------------------------------------------------------------------ helpers
    0x7C09: ('ClearLatchedKeys', 'verified', """
Zero the five latched key-state bytes KeyFlagsScreens..KeyFlagsChart (state bytes 0..4
of KeyActionTable) through ClearBytes; the same effect as ClearKeyFlags.
Also reached by falling through from ResetFlightInputs, which first zeroes the roll and
pitch words and the low byte of SpeedControl and sets its high byte to 12.
Out: A = 0, B = 0, HL = KeyFlagsChart + 1.
Evidence: instruction semantics; callers RestoreCockpitIfFullScreen+6 and the jump at $8F1E
after every screen handler call; runtime: executed."""),
    0x7C0E: ('ClearBytes', 'verified', """
Store zero in B bytes from HL upwards (B=0 clears 256 bytes).
In: HL = first byte, B = count.
Out: HL = first byte after the range, A = 0, B = 0.  Flags changed.
Evidence: instruction semantics; tools/check_routines.py maths/half-chord-root."""),
    0x7C14: ('ResetShipSlots', 'verified', """
Free instance slots 1..7 and clear the station's hostility.
Clears bit 2 (hostile) of +$21 in slot 0 and SharedHostilityAlert, and writes 0 to
byte +$22 of slots 1..7 (a zero +$22 marks a free slot, see FindFreeShipSlot).
Slot 0 (the station) keeps its other bytes.
Out: A = 0, IX = slot 7, B = 0, DE = 39.
Callers: the game-over sequence (L_7356+45), hyperspace arrival
(PlayHyperspaceArrival+8), the launch (LaunchFromStation+93) and the Torus jump key
handler (HandleTorusJumpKey+41).
Evidence: instruction semantics; caller code."""),
    0x7C2D: ('CopyCommanderTemplate', 'verified', """
Copy the 102-byte restart snapshot CommanderTemplateBuffer to ActiveCommanderRecord (the
first 102 bytes of the 104-byte tape record).  The snapshot holds JAMESON at power-on and
is replaced by the active record after every successful tape load or save
(CopyCommanderToTemplate), so a new game restarts from the last loaded or saved commander.
Callers: InitialiseCommander+3 (new game) and ReportTapeLoadingError+5 (a failed load
restores the record).
Out: HL and DE advanced past both records, BC = 0.
Evidence: LDIR operands; caller code; writers of CommanderTemplateBuffer ($D3E2)."""),
    # ------------------------------------------------------------------ variables
    0x7C39: ('HyperspaceKeyLatch', 'verified', """
Set to 1 by CheckHyperspaceKeys as soon as it consumes a hyperspace key bit
(KeyFlagsViews bit 4 H or bit 5 G), before it tests anything else: also when the jump is
refused (countdown already running, docked, galactic hyperdrive missing, target out of
range or the current system itself).  While nonzero CheckDocking returns at once, so
neither station contact (L_DA15) nor the docking computer key docks the ship.
Cleared only on arrival (FinishHyperspaceArrival) and by the game-over restart at L_7388.
So a refused hyperspace key press disables docking until the next jump.
Evidence: tools/check_routines.py missions/p2-hyperspace-key-latch; 48K emulator run
(docking computer key ignored after H was pressed with the current system selected,
honoured without the H press)."""),
    0x7C3A: ('CircleOffsetY', 'verified', """
Circle parameter: vertical distance of the centre from the centre row of the area
(row 64 in the view, row 96 for DrawScreenCircle); CircleFlags bit 1 gives the side.
Written by the planet/sun projection (L_7572, L_764C), L_79F5, DrawScreenCircle and
DrawFlaggedObjectDiscs.  Evidence: tools/check_routines.py circles/circle-renderer."""),
    0x7C3B: ('CircleOffsetX', 'verified', """
Circle parameter: horizontal distance of the centre from column 128; CircleFlags bit 0
gives the side.  Evidence: tools/check_routines.py circles/circle-renderer."""),
    0x7C3C: ('CircleFlags', 'verified', """
Circle flags.  Bit 0 set: centre x = 128 + CircleOffsetX, clear: 128 - offset.
Bit 1 set: centre row = centre - CircleOffsetY (above), clear: below.
Bits 2 (x) and 3 (y) are bit 8 of the offset, inverted: set = the offset byte is the whole
distance; clear = the distance is 256 + the byte.  With a clear bit DrawCircle treats the
centre as beyond that side (bit 2) or top/bottom (bit 3) edge and returns at once when the
byte is at least the half size ($78 / $40): a radius <= 255 cannot reach the view then.
ProjectCoordinate sets bits 2/3 when the projection quotient is below 1 (|coord| < z).
DrawScreenCircle and L_E1D4 store $0C + side bits; L_79F5 stores $0F.
Evidence: tools/check_routines.py circles/circle-renderer (bits 0/1, all four sides) and
circles/p2-circle-offset-bit8 (clear bits 2/3: discs and outlines centred 256 + byte away)."""),
    0x7C3D: ('CircleRadius', 'verified', """
Circle radius in pixels.  DrawFilledCircle and DrawCircleOutline draw nothing for a
radius < 9; DrawCircleOutlineAnySize has no limit.
Evidence: tools/check_routines.py circles/circle-renderer."""),
    0x7C3E: ('CircleWorkOffsetY', 'verified', """
Working copy of CircleOffsetY made by DrawCircle (word store with CircleWorkOffsetX).
The clipping cases replace it with the distance beyond the view edge (offset - $40).
Read through BC by StartMidpointAtRadius and StartMidpointAtFarEdge."""),
    0x7C3F: ('CircleWorkOffsetX', 'verified', """
Working copy of CircleOffsetX.  The clipping cases store offset - $78 (distance beyond
the side edge) or restore offset + $78.  Read as B by the span set-ups."""),
    0x7C40: ('CircleCentreY', 'verified', """
Screen row of the circle centre computed by DrawCircle (may lie outside the view).
The case at L_7F5F replaces it with the nearest view edge row (0 or $7F)."""),
    0x7C41: ('CircleCentreX', 'verified', """
Pixel column of the circle centre computed by DrawCircle.
Evidence: tools/check_routines.py circles/circle-renderer."""),
    0x7C42: ('CircleHalfChord', 'verified', """
ComputeHalfChord result saved by the clipping cases: the half chord where the circle
meets a view edge, used as a row count and as the midpoint start value."""),
    0x7C43: ('CircleSavedStackPointer', 'verified', """
Saved SP while SP is repurposed: the span loops fill bytes with PUSH, and the patch
loops of DrawScreenCircle walk CirclePatchTargets with POP.
Also used by the outline span code (L_86B0, L_8758, L_8850)."""),
    0x7C45: ('HalfChordRadicand', 'verified', """
Word D*D - A*A (- carry) stored by ComputeHalfChord and reloaded on every iteration."""),
    0x7C47: ('SavedLeftEndMask', 'verified', """
Temporary copy of B, the left end mask built by LocateSpanLeftEnd: LocateSpanRightEnd
saves it here before the ROM address call and restores it at its end (fill mode) or in
its outline tail at L_862B.  Evidence: instruction semantics;
tools/check_routines.py circles/p2-span-end-locators (B preserved, mask stored here)."""),
    0x7C48: ('CircleRowDirection', 'verified', """
Row step of the span loops: 1 = downwards (INC H), 0 = upwards (DEC H).  Set by the six
DrawCircleRows dispatchers; also selects which buffer limit (top or bottom) is checked."""),
    0x7C49: ('CircleOutlineFlag', 'verified', """
Renderer style: 1 = outline circle (set by DrawCircleOutlineAnySize), 0 = filled disc
(set by DrawFilledCircle).  Every dispatcher jumps to the outline code (L_8640, L_866E,
DrawCircleLeftArc, DrawCirclePairedArcs, DrawCircleRightArc) when nonzero, otherwise
to the fill code in this range.
Evidence: tools/check_routines.py circles/circle-renderer."""),
    0x7C4A: ('CirclePatchCount', 'verified', """
Number of bytes (32) patched by the two loops of DrawScreenCircle: the entry count of
CirclePatchTargets and the length of both value tables (see the assertions)."""),
    # ------------------------------------------------------------------ span dispatchers
    0x7C4B: ('DrawCircleRowsDownRightClipped', 'verified', """
Draw circle rows downwards whose right end is clipped at the right edge.
Saves AF, sets the midpoint state HL' = 0, D' = 0, B' = $FF, CircleRowDirection = 1, then
jumps to L_869C (outline: left end pixel only) or FillDiscRowsRightClipped.
In: HL = address of the start row's right end byte, E = low byte of the left end,
B = left end mask, C = right end mask, C' = -x and E' = y of the midpoint state.
The span code returns to this dispatcher's caller with AF restored (every exit ends with
POP AF; RET), so a CALL Z / CALL NZ pair after a flag test runs exactly one dispatcher.
Main and alternate BC, DE, HL are changed."""),
    0x7C63: ('DrawCircleRowsUpRightClipped', 'verified', """
As DrawCircleRowsDownRightClipped, but CircleRowDirection = 0 (rows upwards)."""),
    0x7C7A: ('DrawCircleRowsDownLeftClipped', 'verified', """
Draw circle rows downwards whose left end is clipped at the left edge.
Same set-up as DrawCircleRowsDownRightClipped, then L_883C (outline: right end pixel
only) or FillDiscRowsLeftClipped."""),
    0x7C92: ('DrawCircleRowsUpLeftClipped', 'verified', """
As DrawCircleRowsDownLeftClipped, but rows upwards."""),
    0x7CA9: ('DrawCircleRowsDown', 'verified', """
Draw circle rows downwards with both ends inside the view.
Same set-up as above, then L_8740 (outline: both end pixels) or FillDiscRows."""),
    0x7CC1: ('DrawCircleRowsUp', 'verified', """
As DrawCircleRowsDown, but rows upwards."""),
    0x7CD8: ('FillCircleRowsUp', 'verified', """
Rows where the circle covers the whole view width, upwards: A = first row, B = count.
Outline mode: L_8640 only moves HL up B rows; fill mode: FillViewRowsUp fills them.
Out: HL = address in the row after the block (column 31).  AF, BC, DE preserved.
When the block reaches the buffer edge, H is left at $BF (up) or $D0 (down); the span
loops called next then return at once."""),
    0x7CE4: ('FillCircleRowsDown', 'verified', """
As FillCircleRowsUp, downwards (L_866E outline, FillViewRowsDown fill)."""),
    # ------------------------------------------------------------------ main entries
    0x7CF0: ('DrawFilledCircle', 'verified', """
Draw a filled disc into the view buffer from CircleOffsetY/X, CircleFlags and
CircleRadius, clipped to x 8..247 and rows 0..127.  Returns at once if radius < 9.
Sets CircleOutlineFlag = 0, runs DrawCircle with interrupts disabled (the fill loops use
SP as a PUSH pointer), then EI.  Pixels are ORed in; the interior bytes are set to $FF.
Callers: DrawSunAndPlanet+26 (the sun, projected from SunPosition) and
DrawFlaggedObjectDiscs.
Evidence: tools/check_routines.py circles/circle-renderer (discs, full-width fill, edge
clipping)."""),
    0x7CFE: ('DrawCircleOutline', 'verified', """
Draw an outline circle from the circle parameters; returns at once if radius < 9.
Falls into DrawCircleOutlineAnySize.  Callers: the jump at L_74E7+16 (the planet,
projected from PlanetPosition) and DrawScreenCircle.
Evidence: tools/check_routines.py circles/circle-renderer; runtime: flight views."""),
    0x7D04: ('DrawCircleOutlineAnySize', 'verified', """
Draw an outline circle without the radius check: CircleOutlineFlag = 1, DrawCircle, EI.
Caller: L_7A09+19 (concentric rings centred in the view, CircleFlags = $0F)."""),
    0x7D09: (None, 'verified', """
Common tail of the circle entries: CALL DrawCircle, EI, RET."""),
    0x7D0E: ('DrawCircle', 'verified', """
Circle renderer.  In: CircleOffsetY/X, CircleFlags, CircleRadius, CircleOutlineFlag.
Computes CircleCentreY = $40 -/+ dy and CircleCentreX = $80 +/- dx (the $40 and $78
limits are patched by DrawScreenCircle), copies the offsets to CircleWorkOffsetY/X and
selects a clipping case from dy < $40, dx < $78 and CircleFlags bits 2/3:
L_7D56 centre inside, L_7D6B beyond a side edge, L_7D7E above/below, L_7DAE diagonal.
A clear bit 2/3 adds 256 to that offset (see CircleFlags).
Cases that cannot reach the view return early.  All registers and alternates change.
Evidence: tools/check_routines.py circles/circle-renderer; runtime: flight views,
launch/hyperspace rings."""),
    0x7D48: (None, 'verified', """
Case selection: bit 3 clear and dy >= $40 -> invisible."""),
    0x7D4B: (None, 'verified', """
Case selection: bit 2 clear and dx >= $78 -> invisible."""),
    0x7D56: (None, 'verified', """
Case: centre inside the view.  dx + r < $78 -> L_7DE8 (no side edge reached);
r - dx < $78 -> L_7EB8 (only the nearer side edge); else L_7E1E (both side edges)."""),
    0x7D6B: (None, 'verified', """
Case: centre beyond a side edge, row inside.  B = dx - $78 (distance beyond the edge);
returns if r <= B; r - B >= $F0 -> L_7E14 (reaches the opposite edge), else L_7EAE."""),
    0x7D7E: (None, 'verified', """
Case: centre above/below the view, column inside.  C = dy - $40; returns if r < C.
Compares r*r - C*C with (120-dx)^2 and (120+dx)^2 to choose L_7F5F (no side edge at
the edge row), L_7EE2 (one side edge) or L_7E6A (both side edges)."""),
    0x7DAE: (None, 'verified', """
Case: centre outside diagonally.  B = dx - $78, C = dy - $40; returns if the nearest
view corner is outside the circle (r*r - C*C < B*B).  L_7E60 when B < 8 and
r*r - C*C >= (B+248)^2 (far side edge reached; 248, not 240), else L_7ED8."""),
    0x7DE8: (None, 'verified', """
No side edge reached: SetUpCentreRowSpan, DrawCircleRowsUp, SetUpCentreRowSpan again,
then jump to DrawCircleRowsDown."""),
    0x7DF4: ('SetUpCentreRowSpan', 'verified', """
Span set-up on the centre row: C' = -radius, E' = 0 (midpoint x and y), left end at
x = CircleCentreX - radius (LocateSpanLeftEnd), right end at CircleCentreX + radius
(LocateSpanRightEnd).  The dispatcher called next sets HL', D' and B'.
Out: B = left end mask, E = left end low byte, HL = right end address, C = right end mask,
D = radius, C' = -radius, E' = 0."""),
    0x7E14: (None, 'verified', """
Restore CircleWorkOffsetX (B + $78) and enter L_7E22 with A' = 0: the clipped spans
never switch to the unclipped loop (the centre lies beyond the side edge)."""),
    0x7E1E: (None, 'verified', """
Both side edges reached: A' = $88 + dx + 1 = dx - $77 ($80 base when patched), the
negative midpoint x at which the spans leave the nearer edge.  The clipped loops
compare C' with A' and then continue in the FillDiscRows loop (L_8191, L_81D1)."""),
    0x7E22: (None, 'verified', """
Both side edges reached: CircleHalfChord = ComputeHalfChord(r, $78 + dx), the height
where the circle meets the far edge.  Those rows are filled up and down from the centre
row (FillCircleRowsUp/Down); the remaining rows are drawn clipped at the nearer edge
(StartMidpointAtFarEdge, SetFullWidthSpanEnds, dispatcher by CircleFlags bit 0)."""),
    0x7E60: (None, 'verified', """
Restore CircleWorkOffsetX and enter L_7E6D with A' = 0 (diagonal case)."""),
    0x7E6A: (None, 'verified', """
Edge row reaches both side edges: A' = dx - $77 (switch point, see L_7E1E)."""),
    0x7E6D: (None, 'verified', """
Edge row inside both side edges: CircleHalfChord = ComputeHalfChord(r, $78 + dx); fill
the rows from the view edge up to that height, then draw the rest clipped at the
nearer edge (direction from CircleFlags bit 1)."""),
    0x7E97: (None, 'verified', """
As L_7E6D for a centre below the view: start at row $7F and fill upwards."""),
    0x7EAE: (None, 'verified', """
Restore CircleWorkOffsetX and enter L_7EBB with A' = 0."""),
    0x7EB8: (None, 'verified', """
Only the nearer side edge reached: A' = dx - $77 (switch point, see L_7E1E)."""),
    0x7EBB: (None, 'verified', """
One side edge reached, centre row inside: draw up and down with spans clipped at the
right edge (CircleFlags bit 0 set, SetUpRightClippedSpan) or the left edge
(SetUpLeftClippedSpan)."""),
    0x7ED8: (None, 'verified', """
Restore CircleWorkOffsetX and enter L_7EE5 with A' = 0."""),
    0x7EE2: (None, 'verified', """
Edge row reaches one side edge: A' = dx - $77 (switch point, see L_7E1E)."""),
    0x7EE5: (None, 'verified', """
Edge row crosses one side edge:
CircleHalfChord = ComputeHalfChord(r, CircleWorkOffsetY); build the edge-row span (row 0
or $7F) and draw away from the edge.  Midpoint state: E' = rows beyond the edge,
C' = -chord."""),
    0x7F5F: (None, 'verified', """
In: B = dx, C = rows beyond the top/bottom edge (CircleWorkOffsetY), D = radius.
Centre above/below, no side edge reached: CircleCentreY := edge row (0 or $7F),
CircleHalfChord = ComputeHalfChord(r, CircleWorkOffsetY); span from centre x - chord
to centre x + chord on that row, then DrawCircleRowsDown or DrawCircleRowsUp.
The midpoint state starts at y = C, x = -chord (E', C')."""),
    0x7FA5: ('SetUpRightClippedSpan', 'verified', """
Right-clipped set-up: StartMidpointAtRadius, left end at x = $80 + dx - r
(LocateSpanLeftEnd).  Fill mode: right end L = column 31 (exclusive), C = 0;
outline mode: L_8616.
Out: B = left end mask, E = left end low byte, HL = right end address, C = right end mask,
C' = -radius, E' = 0 (from StartMidpointAtRadius)."""),
    0x7FC1: ('SetUpLeftClippedSpan', 'verified', """
Left-clipped set-up: StartMidpointAtRadius, right end at x = $80 - dx + r
(LocateSpanRightEnd), left end E = column 1 (patched 0 for the screen).
B = $FF (fill) or $80 (outline).
Out: as SetUpRightClippedSpan (B, E, HL, C; C' = -radius, E' = 0)."""),
    0x7FE3: ('StartMidpointAtRadius', 'verified', """
Midpoint start for the full radius: BC = (CircleWorkOffsetY), DE = (CircleFlags), so
C = working dy, B = working dx, E = CircleFlags, D = CircleRadius; then C' = -radius and
E' = 0 (midpoint x and y)."""),
    0x7FF4: ('LocateSpanLeftEnd', 'verified', """
In: A = x, C = row.  HL = address of the pixel (ROM PIXEL-ADD tail, then SET 7,H for the
view buffer, NOP NOP when patched for the screen); B = mask of the pixels right of x in
that byte (outline mode: L_861F gives the single pixel x); E = L.  Changes A and C.
Evidence: tools/check_routines.py circles/p2-span-end-locators (all 256 x, both modes)."""),
    0x800F: ('LocateSpanRightEnd', 'verified', """
In: A = x, C = row.  HL = address of the pixel (as LocateSpanLeftEnd); C = mask of the
pixels left of x (fill) or the single pixel x (outline, L_8629).  B (through
SavedLeftEndMask), D and E are preserved.  A filled span thus covers the pixels strictly
between the two x values.
Evidence: tools/check_routines.py circles/p2-span-end-locators (all 256 x, both modes)."""),
    0x8036: ('StartMidpointAtFarEdge', 'verified', """
Midpoint start where the circle meets the far side edge: C' = $88 - CircleWorkOffsetX
(= -(dx+$78); $80 base when patched), E' = CircleHalfChord.
Out: BC = (CircleWorkOffsetY)."""),
    0x8045: ('SetFullWidthSpanEnds', 'verified', """
After the full-width rows: left end E = column 1 of the current row with B = $FF, right
end mask C = 0 (HL stays at column 31).  Outline mode: L_8635."""),
    0x8057: ('FillViewRowsUp', 'verified', """
Fill B rows upwards from row A with $FF in columns 1..30 (x 8..247): SP = column 31 and
15 PUSH DE per row.  Stops early at the top limit (L_809C: $C0 buffer, $40 screen).
Out: HL = address in the row above the block.  AF, BC, DE preserved."""),
    0x80A2: ('FillViewRowsDown', 'verified', """
As FillViewRowsUp, downwards; bottom limit at L_80E7 ($D0 buffer, $50 screen)."""),
    0x80ED: ('ComputeHalfChord', 'verified', """
A = isqrt(D*D - A*A - CF): the half chord at distance A from the centre of a circle of
radius D.  The carry on entry is subtracted because POP AF restores it before SBC HL,DE.
Binary search with SquareA; the radicand is kept in HalfChordRadicand.
BC, DE and HL are preserved.
Evidence: tools/check_routines.py maths/half-chord-root (11,051 cases, all match)."""),
    # ------------------------------------------------------------------ fill span loops
    0x8117: ('FillDiscRows', 'verified', """
Filled-disc rows with both ends inside the view.  Per row: OR C into the right end byte
(HL), OR B into the left end byte (E), $FF in between (one byte, then a self-modified JR
into the PUSH AF run with AF = $FFFF from FilledSpanPattern).  Steps rows by
CircleRowDirection with AdjustRowUpAcrossCell/AdjustRowDownAcrossCell and moves the ends
by the midpoint rule (HL' error, DE' = y, BC' = -x).  Ends when E >= L, at the buffer
limit or when the ends meet.  Uses CircleSavedStackPointer; AF from the dispatcher."""),
    0x8153: (None, 'verified', """
Run of 16 PUSH AF entered part-way by the self-modified JR above: n PUSHes write 2n $FF
bytes below the right end of the span.  The code after the run steps to the next row."""),
    0x81AC: ('EndCircleRows', 'verified', """
Common exit of the span loops: restore SP from CircleSavedStackPointer,
POP AF (pushed by the dispatcher) and return to the dispatcher's caller.
Also jumped to from L_8816."""),
    0x81FC: (None, 'verified', """
Second PUSH AF run of FillDiscRows (rows after the octant change at L_81C4)."""),
    0x8228: ('FillDiscRowsLeftClipped', 'verified', """
As FillDiscRows, but only the right end is masked (OR C); the span is filled with $FF up
to and including the left end byte E (the left edge column).  Continues in the
FillDiscRows loop (L_8191, L_81D1) when the spans leave the edge (C' = A')."""),
    0x825B: (None, 'verified', """
PUSH AF run of FillDiscRowsLeftClipped (first octant)."""),
    0x8305: (None, 'verified', """
PUSH AF run of FillDiscRowsLeftClipped (second octant)."""),
    0x8331: ('FillDiscRowsRightClipped', 'verified', """
As FillDiscRows, but only the left end is masked (OR B); bytes up to, not including,
the right end L are filled (L = column 31 at the right edge).  Continues in the
FillDiscRows loop when the spans leave the edge (C' = A')."""),
    0x8366: (None, 'verified', """
PUSH AF run of FillDiscRowsRightClipped (first octant)."""),
    0x8404: (None, 'verified', """
PUSH AF run of FillDiscRowsRightClipped (second octant)."""),
    0x8430: ('AdjustRowUpAcrossCell', 'verified', """
Called after DEC H left a character cell: E -= 32, L -= 32; within the same screen
third H += 8.  On leaving a third, if H is the top limit ($BF buffer, $3F screen) the
span loop ends through AbortCircleRows.  Out: HL and E on the row above."""),
    0x8445: ('AdjustRowDownAcrossCell', 'verified', """
Called after INC H left a character cell: E += 32, L += 32; within the same third
H -= 8.  On entering the next third, if H is the bottom limit ($D0 buffer, $58 for
DrawScreenCircle, $50 for DrawFlaggedObjectDiscs) the loop ends via AbortCircleRows."""),
    0x845A: ('AbortCircleRows', 'verified', """
Drop the helper's return address, restore SP from CircleSavedStackPointer, POP AF and
return to the dispatcher's caller (the span loop stops at the limit)."""),
    # ------------------------------------------------------------------ patched variants
    0x8461: ('DrawScreenCircle', 'verified', """
Draw an outline circle directly on the 256x192 screen: centre x = (L_A813),
row = (L_A814), radius = (L_A815).  Converts them to CircleOffsetX/Y and CircleFlags
($0C + side bits, relative to x 128 and row 96), copies ScreenCirclePatchValues to the 32
bytes listed in CirclePatchTargets (interrupts disabled), calls DrawCircleOutline, then
copies ViewCirclePatchValues back.  A radius below 9 draws nothing (DrawCircleOutline).
Out: A = 0, interrupts enabled; other registers changed.
Callers: the short-range chart L_A9D0+105 (radius = FuelLevel, centred on the current
system at x $61, row $60), DrawGalacticChart+47 (radius = FuelLevel / 4, centred on
the current system) and BuyCargoScreen+37 (a fixed circle at x $B6, row $76, radius $3D
on the message screen it shows while L_A843 is nonzero).
Evidence: tools/check_routines.py circles/screen-circle-patching (four circles, every patched
byte restored) and circles/p2-screen-circle-minimum-radius; caller code."""),
    0x849D: (None, 'verified', """
Patch loop: POP DE takes the next destination from CirclePatchTargets, LDI copies one
value byte; CirclePatchCount iterations.  SP is then restored."""),
    0x84B9: (None, 'verified', """
Restore loop: as L_849D, copying ViewCirclePatchValues."""),
    0x84C5: ('ScreenCirclePatchValues', 'verified', """
32 values for DrawScreenCircle in CirclePatchTargets order: centre row and half height
$60, half width $80 (and -$80, $7F), columns 0/31, NOP NOP instead of SET 7,H, x limit
$FF and screen row limits $28/$58/$57/$3F."""),
    0x84E5: ('ViewCirclePatchValues', 'verified', """
The 32 view-buffer values, identical to the image bytes at the targets: $40/$78/$88/$77,
columns 1/30, SET 7,H ($CB,$FC), x limit $F7 and buffer limits $C0/$D0/$CF/$BF."""),
    0x8505: ('CirclePatchTargets', 'verified', """
32 pointers to the patched operand/opcode bytes, shared by both value tables.  Each
points at the exact byte (checked against ViewCirclePatchValues in
tools/check_routines.py circles/screen-circle-patching).  Line comments: role of the
target, view value / screen value."""),
    0x8545: ('DrawFlaggedObjectDiscs', 'verified', """
Expanding filled discs drawn directly on the screen for destroyed object instances.
Returns if LastActiveObjectEnergy is zero (no slot active).  Switches the fill path to
the screen top 128 lines (L_809D = $40; PatchDiscRendererTarget with NOP NOP, $50, $4F,
$3F).  For every slot 0..7 whose +$20 bits 5:4 are 11: FillViewAttributes with L = $0A
(ink 2, red); CircleOffsetX/Y, CircleFlags and CircleRadius from +$1C..+$1F; 15
DrawFilledCircle calls, radius += 2 each; FillViewAttributes with L = $0F (ink 7,
white); clear +$20 bit 4 (state 10).  Then restores the buffer values by falling into
PatchDiscRendererTarget ($C0, $CF, $BF, SET 7,H, $D0).
+$20 bit 4 is set when an object is destroyed (player laser L_EC8E, energy bomb L_DAD4,
L_EB88).  While such an object lies in the current view, L_E1D4 records its projected x/y
offsets (+$1C/+$1D), $0C + side bits (+$1E) and projected size (+$1F) and sets bit 5.
Called every frame from L_72FD+28, before BlitViewBitmap copies the buffer over these lines.
Evidence: tools/check_routines.py circles/screen-circle-patching (discs on the screen, buffer
untouched, values restored); writers of +$20 bits 4/5; runtime: called every frame."""),
    0x8567: (None, 'verified', """
Per-slot loop of DrawFlaggedObjectDiscs (B = 8 slots, IX += 39)."""),
    0x858B: (None, 'verified', """
Draw 15 discs: DrawFilledCircle, CircleRadius += 2."""),
    0x85C4: ('PatchDiscRendererTarget', 'verified', """
Patch the filled-disc path.  HL = two opcode bytes for the SET 7,H sites in
LocateSpanLeftEnd, LocateSpanRightEnd, FillViewRowsUp and FillViewRowsDown ($CB,$FC =
SET 7,H for the buffer; 0,0 = NOP NOP for the screen); A = bottom limit for
FillViewRowsDown and AdjustRowDownAcrossCell.  The operands at L_85D7 (last row high
byte) and L_85E2 (row above the top) are set by the caller and copied into the three
fill loops (and AdjustRowUpAcrossCell).  The image holds the screen values $4F/$3F
there; after the first restore they hold $CF/$BF."""),
    0x85F0: (None, 'inferred', """
Two bytes ($01,$3D) with no static or runtime reference and no decoded path into them.
Plausibly unused filler before FilledSpanPattern."""),
    0x85F2: ('FilledSpanPattern', 'verified', """
Word $FFFF loaded into AF (LD SP,FilledSpanPattern; POP AF) by the three fill loops;
each PUSH AF then writes two set bytes."""),
    0x85F4: (None, 'verified', """
Outline-mode tail of L_7F0E: right end = column 30 ($1E, not patched), C = 1 (x 247),
then DrawCircleRowsDownRightClipped or DrawCircleRowsUpRightClipped by CircleFlags bit 1."""),
}

COMMENTS = {
    0x7C01: 'roll and pitch words, speed low byte',
    0x7C07: 'speed high byte (SpeedControl+1) = 12',
    0x7C0B: '5 bytes L_FC0E..L_FC12',
    0x7C14: 'IX = slot 0 (the station)',
    0x7C18: 'slot 0 (station): clear hostile bit',
    0x7C1D: 'no shared hostility alert',
    0x7C20: '39 = instance slot size',
    0x7C23: 'slots 1..7',
    0x7C27: '+$22 = 0 marks the slot free',
    0x7C2D: 'restart snapshot (JAMESON until a load/save)',
    0x7C30: 'first 102 bytes of the tape record',
    0x7C33: '102 commander bytes',
    0x7C4B: 'restored by every exit of the span code',
    0x7C4D: "HL' = 0: midpoint error term",
    0x7C50: "D' = 0: DE' = midpoint y (E')",
    0x7C51: "BC' = $FFxx: negative x counter",
    0x7C54: 'rows downwards',
    0x7C5D: 'outline: left end pixel only',
    0x7C60: 'filled: spans clipped at the right edge',
    0x7C6C: 'rows upwards',
    0x7C74: 'outline: left end pixel only',
    0x7C77: 'filled: spans clipped at the right edge',
    0x7C83: 'rows downwards',
    0x7C8C: 'outline: right end pixel only',
    0x7C8F: 'filled: spans clipped at the left edge',
    0x7C9B: 'rows upwards',
    0x7CA3: 'outline: right end pixel only',
    0x7CA6: 'filled: spans clipped at the left edge',
    0x7CB2: 'rows downwards',
    0x7CBB: 'outline: both end pixels',
    0x7CBE: 'filled: both ends masked',
    0x7CCA: 'rows upwards',
    0x7CD2: 'outline: both end pixels',
    0x7CD5: 'filled: both ends masked',
    0x7CD8: 'keep the start row',
    0x7CDE: 'outline: only move HL up B rows',
    0x7CE1: 'filled: $FF over x 8..247 of B rows',
    0x7CE4: 'keep the start row',
    0x7CEA: 'outline: only move HL down B rows',
    0x7CED: 'filled: $FF over x 8..247 of B rows',
    0x7CF3: 'radius < 9: nothing drawn',
    0x7CF6: 'the fill loops use SP as a PUSH pointer',
    0x7CF8: 'CircleOutlineFlag = 0: filled disc',
    0x7D06: 'CircleOutlineFlag = 1: outline',
    0x7D0C: 'interrupts on again',
    0x7D0E: 'C = dy, B = dx',
    0x7D12: 'working copies of the offsets',
    0x7D16: 'E = CircleFlags, D = CircleRadius',
    0x7D1A: 'SMC: centre row $40 (view) / $60 (DrawScreenCircle)',
    0x7D1C: 'bit 1: centre above the centre row',
    0x7D20: 'below: + 2*dy, then - dy',
    0x7D23: 'centre row, 8-bit (may lie outside the view)',
    0x7D26: 'centre column 128',
    0x7D28: 'bit 0: centre right of column 128',
    0x7D2C: 'right: + 2*dx, then - dx',
    0x7D2F: 'centre column, 8-bit',
    0x7D33: 'SMC: half height $40 (view) / $60 (screen)',
    0x7D35: 'bit 3 set: dy is the whole distance',
    0x7D37: "keep the y test in AF'",
    0x7D39: 'SMC: half width $78 (view x 8..247) / $80 (screen)',
    0x7D3B: 'bit 2 set: dx is the whole distance',
    0x7D3D: 'bit 2 clear: x distance 256 + dx',
    0x7D3F: 'dx >= half width: beyond a side edge',
    0x7D41: 'column inside: recall the y test',
    0x7D42: 'bit 3 clear: y distance 256 + dy',
    0x7D44: 'dy >= half height: above/below',
    0x7D46: 'centre inside the view',
    0x7D48: '256 + dy: out of reach if dy >= $40',
    0x7D49: 'above/below the view, column inside',
    0x7D4B: '256 + dx: out of reach if dx >= $78',
    0x7D4C: 'beyond a side edge: recall the y test',
    0x7D4D: 'bit 3 clear: y distance 256 + dy',
    0x7D4F: 'beyond the top/bottom edge too',
    0x7D51: 'row inside',
    0x7D53: '256 + dy: out of reach if dy >= $40',
    0x7D54: 'diagonal',
    0x7D57: 'dx + r',
    0x7D58: 'over 255: reaches the nearer edge',
    0x7D5A: 'SMC: half width $78 / $80',
    0x7D5C: 'dx + r < half width: no side edge',
    0x7D60: 'r - dx',
    0x7D61: 'r < dx: far edge out of reach (carry)',
    0x7D63: 'SMC: half width $78 / $80',
    0x7D65: 'r - dx < half width: nearer edge only',
    0x7D68: 'both side edges reached',
    0x7D6C: 'pixels beyond the side edge',
    0x7D6F: 'CircleWorkOffsetX = that distance',
    0x7D73: 'r - distance',
    0x7D74: 'r < distance: out of reach',
    0x7D75: 'r = distance: only touches the edge',
    0x7D76: '240 = view width',
    0x7D78: 'also reaches the opposite edge',
    0x7D7B: 'nearer edge only',
    0x7D7F: 'rows beyond the top/bottom edge',
    0x7D82: 'CircleWorkOffsetY = that distance',
    0x7D86: 'r - C',
    0x7D87: 'r < C: out of reach',
    0x7D89: 'DE = r*r',
    0x7D8F: 'DE = C*C',
    0x7D92: 'HL = r*r - C*C: half chord^2 on the edge row',
    0x7D94: '$78 - dx: to the nearer side edge',
    0x7D97: 'DE = its square',
    0x7D9C: 'chord inside the nearer edge',
    0x7D9F: 'restore r*r - C*C',
    0x7DA0: '$78 + dx: to the farther side edge',
    0x7DA3: 'DE = its square',
    0x7DA8: 'chord crosses the farther edge too',
    0x7DAB: 'crosses the nearer edge only',
    0x7DAF: 'columns beyond the side edge',
    0x7DB3: 'rows beyond the top/bottom edge',
    0x7DB6: 'both working offsets',
    0x7DBB: 'DE = r*r',
    0x7DC1: 'DE = C*C',
    0x7DC4: 'HL = r*r - C*C',
    0x7DC6: 'r < C: out of reach',
    0x7DC8: 'DE = B*B',
    0x7DCD: 'nearest view corner outside the circle',
    0x7DCE: 'restore r*r - C*C',
    0x7DD0: 'B + 248 (carry: B >= 8)',
    0x7DD2: 'B >= 8: far edge out of reach',
    0x7DD4: 'DE = (B + 248)^2 (far edge: B + 240)',
    0x7DD9: 'far side edge reached',
    0x7DE8: 'centre-row span',
    0x7DEB: 'upper half',
    0x7DEE: 'centre-row span again',
    0x7DF1: 'lower half',
    0x7DF4: 'C = CircleCentreY, B = CircleCentreX',
    0x7DF8: 'D = CircleRadius',
    0x7E00: "C' = -radius: midpoint x",
    0x7E01: "E' = 0: midpoint y",
    0x7E05: 'left end x = centre x - radius',
    0x7E09: 'C = centre row again',
    0x7E10: 'right end x = centre x + radius',
    0x7E15: 'dx again',
    0x7E18: 'CircleWorkOffsetX = dx',
    0x7E1B: "A' = 0: no switch to the unclipped loop",
    0x7E1E: 'SMC: $88 = -$78 (view) / $80 = -$80 (screen)',
    0x7E21: 'switch value $89 + dx (see header)',
    0x7E22: "keep the switch value in A'",
    0x7E23: 'SMC: half width $78 / $80',
    0x7E25: 'centre to the far side edge',
    0x7E26: 'height where the circle crosses it',
    0x7E29: 'full-width rows above and below the centre',
    0x7E2D: 'from the centre row',
    0x7E30: 'full-width rows upwards',
    0x7E33: 'midpoint state at the far edge',
    0x7E36: 'span ends at the view edges',
    0x7E3C: 'bit 0: centre right of column 128',
    0x7E3E: 'centre left: rest clipped at the left edge',
    0x7E41: 'centre right: clipped at the right edge',
    0x7E44: 'row count again',
    0x7E48: 'from the centre row',
    0x7E4B: 'full-width rows downwards',
    0x7E4E: 'midpoint state at the far edge',
    0x7E51: 'span ends at the view edges',
    0x7E57: 'bit 0: centre right of column 128',
    0x7E59: 'centre left: rest clipped at the left edge',
    0x7E5C: 'centre right: clipped at the right edge',
    0x7E61: 'dx again',
    0x7E64: 'CircleWorkOffsetX = dx',
    0x7E67: "A' = 0: no switch to the unclipped loop",
    0x7E6B: 'switch value dx - $77',
    0x7E6D: "keep the switch value in A'",
    0x7E6E: 'E = CircleFlags, D = CircleRadius',
    0x7E72: 'centre to the far side edge',
    0x7E75: 'height where the circle crosses it',
    0x7E7B: 'minus the rows outside the view',
    0x7E7C: 'B = full-width rows inside the view',
    0x7E7D: 'bit 1: centre above the view',
    0x7E81: 'above: from row 0 downwards',
    0x7E82: 'full-width rows',
    0x7E85: 'midpoint state at the far edge',
    0x7E88: 'span ends at the view edges',
    0x7E8E: 'bit 0: centre right of column 128',
    0x7E90: 'centre left: rest clipped at the left edge',
    0x7E93: 'centre right: clipped at the right edge',
    0x7E97: 'below: from row $7F upwards',
    0x7E99: 'full-width rows',
    0x7E9C: 'midpoint state at the far edge',
    0x7E9F: 'span ends at the view edges',
    0x7EA5: 'bit 0: centre right of column 128',
    0x7EA7: 'centre left: rest clipped at the left edge',
    0x7EAA: 'centre right: clipped at the right edge',
    0x7EAF: 'dx again',
    0x7EB1: 'CircleWorkOffsetX = dx',
    0x7EB5: "A' = 0: no switch to the unclipped loop",
    0x7EB9: 'SMC: half width - 1: $77 / $7F',
    0x7EBB: "keep the switch value in A'",
    0x7EBC: 'bit 0: centre right of column 128',
    0x7EBE: 'centre left: clip at the left edge',
    0x7EC0: 'centre-row span, right end at the edge',
    0x7EC3: 'lower half',
    0x7EC6: 'centre-row span again',
    0x7EC9: 'upper half',
    0x7ECC: 'centre-row span, left end at the edge',
    0x7ECF: 'lower half',
    0x7ED2: 'centre-row span again',
    0x7ED5: 'upper half',
    0x7ED9: 'dx again',
    0x7EDB: 'CircleWorkOffsetX = dx',
    0x7EDF: "A' = 0: no switch to the unclipped loop",
    0x7EE3: 'switch value dx - $77',
    0x7EE5: "keep the switch value in A'",
    0x7EE6: 'E = CircleFlags, D = CircleRadius',
    0x7EEA: 'rows beyond the top/bottom edge',
    0x7EEB: 'half chord on the edge row',
    0x7EF3: "E' = rows beyond the edge: midpoint y",
    0x7EF9: "C' = -chord: midpoint x",
    0x7EFB: 'bit 0: centre right of column 128',
    0x7EFD: 'centre left: the right end is inside',
    0x7F03: '$80 - chord ...',
    0x7F05: '... + dx: left end x on the edge row',
    0x7F06: 'row 0 (centre above the view)',
    0x7F08: 'bit 1: centre above the view',
    0x7F0C: 'row $7F (centre below the view)',
    0x7F15: 'outline: L_85F4',
    0x7F1B: 'left end in column 31 (x >= 248)?',
    0x7F1D: 'then nothing is inside the view',
    0x7F1F: 'right end: column 31 (exclusive)',
    0x7F22: 'no right end mask',
    0x7F27: 'bit 1: centre above the view',
    0x7F29: 'above: rows downwards from row 0',
    0x7F2C: 'below: rows upwards from row $7F',
    0x7F33: 'chord + $80 ...',
    0x7F35: '... - dx: right end x on the edge row',
    0x7F36: 'x < 8: all in the left border',
    0x7F39: 'row 0 (centre above the view)',
    0x7F3B: 'bit 1: centre above the view',
    0x7F3F: 'row $7F (centre below the view)',
    0x7F47: 'left end: column 1 (x 8)',
    0x7F4E: 'outline: L_8608',
    0x7F51: 'whole left byte',
    0x7F56: 'bit 1: centre above the view',
    0x7F58: 'above: rows downwards from row 0',
    0x7F5B: 'below: rows upwards from row $7F',
    0x7F5F: 'E = CircleFlags, D = CircleRadius',
    0x7F63: 'rows beyond the top/bottom edge',
    0x7F64: 'half chord on the edge row',
    0x7F6C: "E' = rows beyond the edge: midpoint y",
    0x7F72: "C' = -chord: midpoint x",
    0x7F74: 'row 0 (centre above the view)',
    0x7F75: 'bit 1: centre above the view',
    0x7F79: 'row $7F (centre below the view)',
    0x7F7B: 'the spans start on the edge row',
    0x7F86: 'left end x = centre x - chord',
    0x7F8A: 'C = edge row again',
    0x7F95: 'right end x = centre x + chord',
    0x7F9C: 'bit 1: centre above the view',
    0x7F9E: 'above: rows downwards',
    0x7FA1: 'below: rows upwards',
    0x7FA8: 'C = centre row',
    0x7FAF: 'left end x = $80 + dx - r',
    0x7FB7: 'outline: L_8616',
    0x7FBB: 'right end: column 31 (exclusive)',
    0x7FBE: 'no right end mask',
    0x7FC4: 'C = centre row',
    0x7FCB: 'right end x = $80 - dx + r',
    0x7FD0: 'start of the row',
    0x7FD2: 'SMC: left column 1 (view, x >= 8) / 0 (screen)',
    0x7FD4: 'left end: the edge byte',
    0x7FDD: 'filled: whole left byte',
    0x7FE0: 'outline: its leftmost pixel',
    0x7FE3: 'C = working dy, B = working dx',
    0x7FE7: 'E = CircleFlags, D = CircleRadius',
    0x7FEF: "C' = -radius: midpoint x",
    0x7FF0: "E' = 0: midpoint y",
    0x7FF6: 'B = row, C = x, A = row',
    0x7FF7: 'A = row, C = x -> HL, A = x AND 7',
    0x7FFA: 'SMC: SET 7,H (view buffer) / NOP NOP (screen)',
    0x8002: 'outline: single pixel x (L_861F)',
    0x8005: 'B = $FF >> (1 + x AND 7): pixels right of x',
    0x800D: 'E = low byte of the left end address',
    0x8011: 'keep the left end mask',
    0x8017: 'B = row, C = x, A = row',
    0x8018: 'A = row, C = x -> HL, A = x AND 7',
    0x801B: 'SMC: SET 7,H (view buffer) / NOP NOP (screen)',
    0x801F: 'A = 8 - (x AND 7)',
    0x8027: 'outline: single pixel x (L_8629)',
    0x802A: 'C = $FF << (8 - x AND 7): pixels left of x',
    0x8031: 'left end mask back into B',
    0x8036: 'C = working dy, B = working dx',
    0x803A: 'SMC: $88 = -$78 (view) / $80 (screen)',
    0x803C: '-(half width + dx)',
    0x803E: "C' = midpoint x at the far edge",
    0x8042: "E' = CircleHalfChord: midpoint y",
    0x8049: 'outline: L_8635',
    0x8051: 'left end: column 1 (x 8)',
    0x8052: 'no right end mask (HL at column 31)',
    0x8054: 'whole left byte',
    0x805A: 'B = start row',
    0x805D: 'x = 248: column 31',
    0x8060: 'SMC: SET 7,H / NOP NOP (PatchDiscRendererTarget)',
    0x8062: 'B = row count',
    0x8064: 'fill pattern',
    0x8067: 'SP becomes the fill pointer',
    0x806D: 'no rows',
    0x806F: 'SP = column 31 of the row',
    0x8070: '15 words: columns 1..30',
    0x807F: 'row above; leaving a character cell?',
    0x8087: 'SP back; BC, AF, DE restored',
    0x8090: 'cell row above',
    0x8093: 'crossed into the third above',
    0x8096: 'same third: H + 8',
    0x809B: 'H - 1 is already the right row',
    0x809C: 'SMC: top limit $C0 (buffer) / $40 (screen)',
    0x809E: 'still inside: next row',
    0x80A0: 'left the top: stop',
    0x80A5: 'B = start row',
    0x80A8: 'x = 248: column 31',
    0x80AB: 'SMC: SET 7,H / NOP NOP (PatchDiscRendererTarget)',
    0x80AD: 'B = row count',
    0x80B2: 'SP becomes the fill pointer',
    0x80B8: 'no rows',
    0x80BA: 'SP = column 31 of the row',
    0x80BB: '15 words: columns 1..30',
    0x80CA: 'row below; leaving a character cell?',
    0x80D2: 'SP back; BC, AF, DE restored',
    0x80DB: 'cell row below',
    0x80DE: 'crossed into the next third',
    0x80E1: 'same third: H - 8',
    0x80E6: 'H + 1 is already the right row',
    0x80E7: 'SMC: bottom limit $D0 (buffer) / $50 (screen)',
    0x80E9: 'still inside: next row',
    0x80EB: 'left the bottom: stop',
    0x80F0: 'keep A and the entry carry',
    0x80F2: 'DE = D*D',
    0x80F7: 'A and the carry back',
    0x80F8: 'DE = A*A',
    0x80FB: 'HL = D*D - A*A - carry',
    0x80FD: 'binary search bit',
    0x80FF: 'A = 0: result so far',
    0x8106: 'try the bit (no carry)',
    0x8107: 'DE = trial square',
    0x810C: 'trial square fits: keep the bit',
    0x810E: 'too big: drop the bit',
    0x8111: 'until bit 0 has been tried',
    0x8119: 'left end not left of the right end',
    0x811F: 'downwards: bottom check',
    0x8121: 'SMC: row above the top, $BF buffer / $3F screen',
    0x8124: 'start row inside: draw',
    0x8126: 'start row above the area',
    0x8128: 'SMC: last row high byte, $CF buffer / $4F screen',
    0x812B: 'start row inside: draw',
    0x812D: "dispatcher's AF; nothing drawn",
    0x812F: 'kept for the PUSH fill and the exits',
    0x8134: 'OR the right end mask into its byte',
    0x8136: 'D = right end low byte',
    0x8137: 'HL = left end byte',
    0x8139: 'OR the left end mask',
    0x813D: 'bytes strictly between the ends',
    0x813E: 'words; an odd byte in carry',
    0x8143: 'odd byte right of the left end',
    0x8145: 'HL = right end byte again',
    0x8148: 'A = $10 - words',
    0x8149: 'JR displacement = $10 - word count',
    0x814C: 'AF = $FFFF fill pattern',
    0x8150: 'SP = right end: PUSHes fill leftwards',
    0x8151: 'SMC: displacement written above (into the PUSH AF run)',
    0x8167: 'SP back for the row helpers (flags kept)',
    0x816E: 'row up',
    0x8171: 'cell boundary crossed',
    0x8176: 'row down',
    0x817A: 'cell boundary crossed',
    0x817E: "error += 2y + 1, y += 1 (DE')",
    0x8181: 'error negative?',
    0x8184: 'yes: same x, draw the next row',
    0x8186: 'x in: left end one pixel right',
    0x8188: 'mask was empty: next byte',
    0x818A: 'right end one pixel left',
    0x818C: 'mask was empty: previous byte',
    0x818F: "error += 2x + 1, x += 1 (BC' = x < 0)",
    0x8191: 'second half; entry from the clipped loops',
    0x8192: 'error negative again?',
    0x8195: 'yes: draw the next row',
    0x8198: 'no: x moves more than once per row',
    0x819A: 'left end into the next byte',
    0x819D: 'the ends met: done',
    0x819F: 'pixels right of its first one',
    0x81A3: 'right end into the previous byte',
    0x81A6: 'the ends met: done',
    0x81A8: 'pixels left of its last one',
    0x81AC: 'SP saved by the span loop',
    0x81B0: "the dispatcher's AF",
    0x81B2: 'left end into the next byte',
    0x81B5: 'the ends met: done',
    0x81B7: 'pixels right of its first one',
    0x81BB: 'right end into the previous byte',
    0x81BE: 'the ends met: done',
    0x81C0: 'pixels left of its last one',
    0x81C4: 'x in: left end one pixel right',
    0x81C6: 'mask was empty: next byte',
    0x81C8: 'right end one pixel left',
    0x81CA: 'mask was empty: previous byte',
    0x81CD: 'error += x, x += 1',
    0x81CF: 'x = 0: top of the circle, done',
    0x81D1: 'error += x (entry from the clipped loops)',
    0x81D5: 'error not negative: move x again',
    0x81D8: 'error += 2y + 1, y += 1: next row',
    0x81DD: 'OR the right end mask into its byte',
    0x81E2: 'OR the left end mask',
    0x81E6: 'bytes strictly between the ends',
    0x81EC: 'odd byte right of the left end',
    0x81F2: 'JR displacement = $10 - word count',
    0x81F5: 'AF = $FFFF fill pattern',
    0x81FA: 'SMC: displacement written above (into the PUSH AF run)',
    0x8210: 'SP back for the row helpers (flags kept)',
    0x8217: 'row up',
    0x821A: 'cell boundary crossed',
    0x821D: 'move x for the next row',
    0x821F: 'row down',
    0x8223: 'cell boundary crossed',
    0x8226: 'move x for the next row',
    0x822C: 'downwards: bottom check',
    0x822E: 'SMC: $BF buffer / $3F screen',
    0x8231: 'start row inside: draw',
    0x8233: 'start row above the area',
    0x8235: 'SMC: $CF buffer / $4F screen',
    0x8238: 'start row inside: draw',
    0x823A: "dispatcher's AF; nothing drawn",
    0x823C: 'kept for the PUSH fill and the exits',
    0x8241: 'OR the right end mask into its byte',
    0x8244: 'HL = left edge byte',
    0x8246: 'bytes from the edge byte to the right end',
    0x8247: 'words; an odd byte in carry',
    0x824B: 'odd byte: the edge byte, whole',
    0x8251: 'JR displacement = $10 - word count',
    0x8254: 'AF = $FFFF fill pattern',
    0x8259: 'SMC: displacement written above (into the PUSH AF run)',
    0x826F: 'SP back for the row helpers (flags kept)',
    0x8276: 'row up',
    0x8279: 'cell boundary crossed',
    0x827E: 'row down',
    0x8282: 'cell boundary crossed',
    0x8286: 'error += 2y + 1, y += 1',
    0x828C: 'error negative: same x, next row',
    0x828E: 'x in: right end one pixel left',
    0x8290: 'mask was empty: previous byte',
    0x8293: 'error += x, x += 1',
    0x8296: "x = switch value (A')?",
    0x8297: 'left end leaves the edge',
    0x829A: 'error += x',
    0x829E: 'error negative: draw the next row',
    0x82A1: 'x moves more than once per row',
    0x82A3: 'right end into the previous byte',
    0x82A7: 'right end left of the edge byte: done',
    0x82A9: 'pixels left of its last one',
    0x82B0: 'right end in the edge byte?',
    0x82B2: 'yes: done',
    0x82B4: 'continue in FillDiscRows',
    0x82BA: 'right end in the edge byte?',
    0x82BC: 'yes: done',
    0x82BE: 'continue in FillDiscRows (second half)',
    0x82C1: 'SP saved by the span loop',
    0x82C5: "the dispatcher's AF",
    0x82C7: 'right end into the previous byte',
    0x82CB: 'right end left of the edge byte: done',
    0x82CD: 'pixels left of its last one',
    0x82D1: 'x in: right end one pixel left',
    0x82D3: 'mask was empty: previous byte',
    0x82D6: 'error += x, x += 1',
    0x82D8: 'x = 0: top of the circle, done',
    0x82DB: "x = switch value (A')?",
    0x82DC: 'left end leaves the edge',
    0x82DF: 'error += x',
    0x82E3: 'error not negative: move x again',
    0x82E6: 'error += 2y + 1, y += 1: next row',
    0x82EB: 'OR the right end mask into its byte',
    0x82F0: 'bytes from the edge byte to the right end',
    0x82F5: 'odd byte: the edge byte, whole',
    0x82FB: 'JR displacement = $10 - word count',
    0x82FE: 'AF = $FFFF fill pattern',
    0x8303: 'SMC: displacement written above (into the PUSH AF run)',
    0x8319: 'SP back for the row helpers (flags kept)',
    0x8320: 'row up',
    0x8323: 'cell boundary crossed',
    0x8326: 'move x for the next row',
    0x8328: 'row down',
    0x832C: 'cell boundary crossed',
    0x832F: 'move x for the next row',
    0x8335: 'downwards: bottom check',
    0x8337: 'SMC: $BF buffer / $3F screen',
    0x833A: 'start row inside: draw',
    0x833C: 'start row above the area',
    0x833E: 'SMC: $CF buffer / $4F screen',
    0x8341: 'start row inside: draw',
    0x8343: "dispatcher's AF; nothing drawn",
    0x8345: 'kept for the PUSH fill and the exits',
    0x8349: 'D = right end low byte (edge column)',
    0x834C: 'OR the left end mask',
    0x8350: 'bytes strictly between the ends',
    0x8351: 'words; an odd byte in carry',
    0x8356: 'odd byte right of the left end',
    0x835C: 'JR displacement = $10 - word count',
    0x835F: 'AF = $FFFF fill pattern',
    0x8364: 'SMC: displacement written above (into the PUSH AF run)',
    0x837A: 'SP back for the row helpers (flags kept)',
    0x8381: 'row up',
    0x8384: 'cell boundary crossed',
    0x8389: 'row down',
    0x838D: 'cell boundary crossed',
    0x8391: 'error += 2y + 1, y += 1',
    0x8397: 'error negative: same x, next row',
    0x8399: 'x in: left end one pixel right',
    0x839B: 'mask was empty: next byte',
    0x839E: 'error += x, x += 1',
    0x83A1: "x = switch value (A')?",
    0x83A2: 'right end leaves the edge',
    0x83A5: 'error += x',
    0x83A9: 'error negative: draw the next row',
    0x83AC: 'x moves more than once per row',
    0x83AE: 'left end into the next byte',
    0x83B1: 'reached the right end byte: done',
    0x83B3: 'pixels right of its first one',
    0x83B8: 'continue in FillDiscRows',
    0x83BC: 'continue in FillDiscRows (second half)',
    0x83BF: 'SP saved by the span loop',
    0x83C3: "the dispatcher's AF",
    0x83C5: 'left end into the next byte',
    0x83C8: 'reached the right end byte: done',
    0x83CA: 'pixels right of its first one',
    0x83CE: 'x in: left end one pixel right',
    0x83D0: 'mask was empty: next byte',
    0x83D3: 'error += x, x += 1',
    0x83D5: 'x = 0: top of the circle, done',
    0x83D8: "x = switch value (A')?",
    0x83D9: 'right end leaves the edge',
    0x83DC: 'error += x',
    0x83E0: 'error not negative: move x again',
    0x83E3: 'error += 2y + 1, y += 1: next row',
    0x83EA: 'OR the left end mask',
    0x83EE: 'bytes strictly between the ends',
    0x83F4: 'odd byte right of the left end',
    0x83FA: 'JR displacement = $10 - word count',
    0x83FD: 'AF = $FFFF fill pattern',
    0x8402: 'SMC: displacement written above (into the PUSH AF run)',
    0x8418: 'SP back for the row helpers (flags kept)',
    0x841F: 'row up',
    0x8422: 'cell boundary crossed',
    0x8425: 'move x for the next row',
    0x8427: 'row down',
    0x842B: 'cell boundary crossed',
    0x842E: 'move x for the next row',
    0x8431: 'left end byte: cell row above',
    0x8435: 'right end byte: cell row above',
    0x8438: 'same third: H + 8',
    0x843A: 'SMC: top limit $BF (buffer) / $3F (screen)',
    0x843D: 'above the area: stop the span loop',
    0x843F: 'previous third: H - 1 is right',
    0x8446: 'left end byte: cell row below',
    0x844A: 'right end byte: cell row below',
    0x844D: 'same third: H - 8',
    0x844F: 'SMC: bottom limit $D0 (buffer) / $58 or $50 (screen)',
    0x8452: 'below the area: stop the span loop',
    0x8454: 'next third: H + 1 is right',
    0x845A: 'drop the return into the span loop',
    0x845B: 'SP saved by the span loop',
    0x845F: "the dispatcher's AF",
    0x8461: '$0C: both offsets exact (CircleFlags bits 2/3)',
    0x8463: 'centre x',
    0x8467: 'x - 128',
    0x846B: 'right of column 128',
    0x8471: '128 - x',
    0x8472: 'CircleOffsetX = |x - 128|',
    0x8475: 'centre row',
    0x8479: 'row - 96',
    0x847D: 'above row 96',
    0x8481: '96 - row',
    0x8482: 'CircleOffsetY = |row - 96|',
    0x8486: '$0C + side bits',
    0x8489: 'radius',
    0x848F: 'SP is borrowed by the patch loop',
    0x8494: '32 patch bytes',
    0x8497: 'screen values',
    0x849A: 'SP walks the destination pointers',
    0x849E: 'patch one byte (destination from POP DE)',
    0x84A3: 'SP back',
    0x84A7: 'interrupts on while drawing',
    0x84A8: 'draw with the screen values in place',
    0x84AB: 'restore with interrupts off',
    0x84B3: 'view-buffer values',
    0x84B6: 'the same 32 destinations',
    0x84BA: 'restore one byte',
    0x84C3: 'A = 0 on return',
    0x84C5: 'entries 0..7: centre and half sizes',
    0x84CD: 'entries 8..15: columns, SET 7,H, far edge',
    0x84D5: 'entries 16..23: L_8640 and L_866E',
    0x84DD: 'entries 24..31: arc start rows, cell limits',
    0x84E5: 'entries 0..7: centre and half sizes',
    0x84ED: 'entries 8..15: columns, SET 7,H, far edge',
    0x84F5: 'entries 16..23: L_8640 and L_866E',
    0x84FD: 'entries 24..31: arc start rows, cell limits',
    0x8505: 'DrawCircle centre row: $40 / $60',
    0x8507: 'DrawCircle half height: $40 / $60',
    0x8509: 'DrawCircle half width: $78 / $80',
    0x850B: 'L_7D56 dx + r test: $78 / $80',
    0x850D: 'L_7D56 r - dx test: $78 / $80',
    0x850F: 'L_7E1E -(half width): $88 / $80',
    0x8511: 'L_7E22 half width: $78 / $80',
    0x8513: 'L_7EB8 half width - 1: $77 / $7F',
    0x8515: 'L_8616 right column: $1E / $1F',
    0x8517: 'SetUpLeftClippedSpan left column: $01 / $00',
    0x8519: 'LocateSpanLeftEnd SET 7,H: $CB / NOP',
    0x851B: 'LocateSpanLeftEnd SET 7,H: $FC / NOP',
    0x851D: 'LocateSpanRightEnd SET 7,H: $CB / NOP',
    0x851F: 'LocateSpanRightEnd SET 7,H: $FC / NOP',
    0x8521: 'StartMidpointAtFarEdge: $88 / $80',
    0x8523: 'L_8635 left column: $01 / $00',
    0x8525: 'L_8640 start x: $F7 / $FF',
    0x8527: 'L_8640 SET 7,H: $CB / NOP',
    0x8529: 'L_8640 SET 7,H: $FC / NOP',
    0x852B: 'L_8640 top limit: $C0 / $28 (no limit)',
    0x852D: 'L_866E start x: $F7 / $FF',
    0x852F: 'L_866E SET 7,H: $CB / NOP',
    0x8531: 'L_866E SET 7,H: $FC / NOP',
    0x8533: 'L_866E bottom limit: $D0 / $58',
    0x8535: 'DrawCircleLeftArc last row: $CF / $57',
    0x8537: 'DrawCircleLeftArc row above: $BF / $3F',
    0x8539: 'DrawCirclePairedArcs row above: $BF / $3F',
    0x853B: 'DrawCirclePairedArcs last row: $CF / $57',
    0x853D: 'DrawCircleRightArc last row: $CF / $57',
    0x853F: 'DrawCircleRightArc row above: $BF / $3F',
    0x8541: 'AdjustRowDownAcrossCell limit: $D0 / $58',
    0x8543: 'AdjustRowUpAcrossCell limit: $BF / $3F',
    0x8545: 'nonzero while an instance slot is in use (L_DAA6)',
    0x854C: 'FillViewRowsUp top limit: $40 (screen)',
    0x8551: 'last row high byte for PatchDiscRendererTarget',
    0x8556: 'row above the top for PatchDiscRendererTarget',
    0x8559: 'NOP NOP replaces SET 7,H',
    0x855C: 'bottom limit: screen line 128',
    0x8561: 'slot 0',
    0x8565: '8 slots',
    0x856C: '+$20 bits 4 and 5 both set',
    0x8570: 'bits 5:4 not 11: skip the slot',
    0x8572: 'attribute $0A (ink 2, red) for L_9287',
    0x8577: '+$1C/+$1D -> CircleOffsetX/Y',
    0x8580: '+$1E/+$1F -> CircleFlags/CircleRadius',
    0x8589: '15 discs',
    0x8597: 'radius + 2',
    0x859F: 'attribute $0F (ink 7, white) for L_9287',
    0x85A4: 'done: bits 5:4 = 10',
    0x85A8: '39 = instance slot size',
    0x85B0: 'restore the buffer values',
    0x85BF: '$CB,$FC = SET 7,H opcode bytes',
    0x85C2: 'bottom limit: buffer end $D0',
    0x85C4: 'SET 7,H site in LocateSpanLeftEnd',
    0x85C7: 'SET 7,H site in LocateSpanRightEnd',
    0x85CA: 'SET 7,H site in FillViewRowsUp',
    0x85CD: 'SET 7,H site in FillViewRowsDown',
    0x85D0: 'bottom limit of FillViewRowsDown',
    0x85D3: 'bottom limit of AdjustRowDownAcrossCell',
    0x85D6: 'SMC parameter: $4F (screen) / $CF (buffer), set by the caller',
    0x85D8: 'start check of FillDiscRowsRightClipped',
    0x85DB: 'start check of FillDiscRows',
    0x85DE: 'start check of FillDiscRowsLeftClipped',
    0x85E1: 'SMC parameter: $3F (screen) / $BF (buffer), set by the caller',
    0x85E3: 'start check of FillDiscRowsRightClipped',
    0x85E6: 'start check of FillDiscRows',
    0x85E9: 'start check of FillDiscRowsLeftClipped',
    0x85EC: 'top limit of AdjustRowUpAcrossCell',
    0x85F5: 'start of the row in E',
    0x85F7: 'right end: column 30 (x 240..247)',
    0x85FA: 'its last pixel (x 247)',
    0x85FF: 'bit 1: centre above the view',
}

DATA = {
    0x7C39: (0x7C43, 'bytes', 1),
    0x7C43: (0x7C47, 'words', 1),
    0x7C47: (0x7C4B, 'bytes', 1),
    0x84C5: (0x84E5, 'bytes', 8),
    0x84E5: (0x8505, 'bytes', 8),
    0x8505: (0x8545, 'pointers', 1),
    0x85F0: (0x85F2, 'bytes', 2),
    0x85F2: (0x85F4, 'bytes', 2),
}

SEEDS = {
    0x8153: 'PUSH AF run entered by the self-modified JR at $8151 (displacement from $8149)',
    0x81FC: 'PUSH AF run entered by the self-modified JR at $81FA (displacement from $81F2)',
    0x825B: 'PUSH AF run entered by the self-modified JR at $8259 (displacement from $8251)',
    0x8305: 'PUSH AF run entered by the self-modified JR at $8303 (displacement from $82FB)',
    0x8366: 'PUSH AF run entered by the self-modified JR at $8364 (displacement from $835C)',
    0x8404: 'PUSH AF run entered by the self-modified JR at $8402 (displacement from $83FA)',
}

CONSTANTS = {
    0x85BF: 'opcode bytes $CB,$FC (SET 7,H) written back into four code sites, not an address',
}

FIELDS = {
    'RomPixelAddressTail': (0x22B0, 'ROM PIXEL-ADD after its range check: A = row, C = x'),
}

OPERANDS = {
    0x7C33: 'CommanderTemplateBufferEnd-CommanderTemplateBuffer',
    0x7FF7: 'RomPixelAddressTail',
    0x8018: 'RomPixelAddressTail',
    0x805D: 'RomPixelAddressTail',
    0x80A8: 'RomPixelAddressTail',
}

ASSERTS = {
    'r2-view-buffer-c000': ('FontBitmap-GameImage+GameLoadAddress = $C000',
                            'ViewBitmapBuffer: SET 7,H maps screen $40xx..$4Fxx onto it'),
    'r2-patch-values-screen': ('ViewCirclePatchValues-ScreenCirclePatchValues = 32',
                               'one value per CirclePatchTargets entry'),
    'r2-patch-values-view': ('CirclePatchTargets-ViewCirclePatchValues = 32',
                             'one value per CirclePatchTargets entry'),
    'r2-patch-targets': ('DrawFlaggedObjectDiscs-CirclePatchTargets = 2*32',
                         'CirclePatchCount ($20) pointers'),
}
