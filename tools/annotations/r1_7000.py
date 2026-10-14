"""$7000..$7BFF: state variables, title/main loop, view buffer, sun/planet, gauges, tunnels.

Evidence: instruction semantics, 48K runtime traces (docs/generated/runtime-xrefs.json),
decoded game text (tools/text_codec.py), the cockpit bitmap labels (docs/images) and the
simulator checks in tools/check_routines.py (controls, screen, pipeline, maths and text
groups): ReadFlightControls/DrawGauges, ClearViewBuffer,
BlitViewBitmap, ProjectBodyPosition, the fractional dividers, MakeSunRelativeToStation and the
justified word-wrap printer that uses the buffer at $7003.
"""

SECTIONS = {
    0x7003: ('Game state variables',
             'Word-wrap line buffer, flight controls, cockpit gauge values, sun and planet\n'
             'positions and flight-state flags.'),
    0x718F: ('Title screen and main game loop',
             'Title ship display, new-game start, the per-frame main loop and the death\n'
             'sequence.'),
    0x7398: ('View buffer and cockpit display',
             'Blit and clear of the 4 KB view buffer at ViewBitmapBuffer, cockpit restore.'),
    0x74BE: ('Sun and planet',
             'Projection and drawing of the two large bodies, the expanding-sun effect,\n'
             'station dormancy and the cloak key.'),
    0x7859: ('Cockpit gauges',
             'Bar and indicator gauges in the bottom screen third.'),
    0x7999: ('Tunnel animations',
             'Hyperspace arrival rings and the station launch/docking tunnel.'),
}

LABELS = {
    # ------------------------------------------------------------------
    # Word-wrap buffer $7003..$7040
    0x7003: ('WrapSentinelSpace', 'verified', """
Constant space ($20) in front of WrapLineBuffer.  The backward word search
at L_BDCB stops here, and L_BCFA/L_BCF6 count write positions from this byte
(the write pointer is pre-incremented, so the first character goes to $7004).
Evidence: L_BCFC..L_BDE2 semantics; tools/check_routines.py text/justified-word-wrap."""),
    0x7004: ('WrapLineBuffer', 'verified', """
30-character output line of the justified word-wrap printer (PrintCharacter
passes characters to L_BCFC while L_A894 = 1; message control L_BD9D enters
the mode, L_BDB9 flushes).  L_BD5D prints these 30 bytes through L_BB58.
On overflow the last word moves to WrapCarryBuffer and L_D000 inserts spaces
at word gaps to fill the line (justification).
Evidence: tools/check_routines.py text/justified-word-wrap prints a planet description
as justified 30-column lines; runtime: docked-system-data."""),
    0x7022: ('WrapOverflowChar', 'verified', """
31st character position: receives the character that does not fit; a space
here simply flushes the line, otherwise the word ending here is carried over.
L_BDDC also restarts the backward space search from this byte."""),
    0x7023: ('WrapCarryBuffer', 'verified', """
Carry-over buffer: the word moved off a full line is copied here, then
L_BD75 moves 30 bytes from here to WrapLineBuffer and refills this buffer
with spaces.
NOTE: L_BD9D fills 31 bytes from here, so it also writes $20 to
CurrentScreenId ($7041).  Runtime confirms the write (PC $BDA9) and
tools/check_routines.py text/justified-word-wrap reproduces it; the original code relies
on later screen selection to overwrite it."""),
    # ------------------------------------------------------------------
    # Flight controls
    0x7042: ('PlayerRoll', 'verified', """
Current roll rate, sign-magnitude byte (bit 7 = direction).  Copied each
frame by ReadFlightControls from L_FF09, which the interrupt code updates.
Shown by the RL indicator (RollIndicator) and applied by L_DED1, which
rotates body/object positions by the player's roll and pitch."""),
    0x7043: ('PlayerPitch', 'verified', """
Current pitch rate, sign-magnitude byte, copied from L_FF0B by
ReadFlightControls.  Shown by the DC indicator (PitchIndicator); used by
L_DED1.  Cleared when docking starts (DockIntoStation) and by L_ED37."""),
    0x7044: ('PlayerSpeed', 'verified', """
Current speed 0..31, copied from the high byte of SpeedControl by ReadFlightControls
and shown on the SP gauge (SpeedGauge = speed*5+5).  L_DED1 moves bodies along z by
2*(speed+1) per update.  Set to 7 for the stardust of the remaining launch-tunnel
frames (L_7A88), 12 by DockIntoStation and 0 on death."""),
    # ------------------------------------------------------------------
    # Gauges
    0x7045: ('GaugeDisplayTable', 'verified', """
Thirteen (last drawn value, current value) byte pairs for the cockpit
gauges, walked by DrawGauges from ForwardShield in steps of two.  A gauge
is redrawn only when its current value differs from the last drawn copy
stored in the byte before it.  This first byte is the drawn copy of
ForwardShield.  Pairs 0..10 are bars (value/4 pixels, 160 = full 40-pixel
bar), pairs 11..12 the RL/DC indicators.  Screen addresses: GaugeScreenAddresses.
Evidence: tools/check_routines.py controls/read-flight-controls, controls/draw-gauges;
cockpit labels FS AS FU CT LT AL SP 1..4 RL DC."""),
    0x7046: ('ForwardShield', 'verified', """
Fore shield strength, 0..160, drawn as the FS bar.  L_A584 subtracts fore
damage (L_DA18), L_A65A recharges it; L_9A46 fills it ($A0) at launch."""),
    0x7048: ('AftShield', 'verified', """
Aft shield strength, 0..160, drawn as the AS bar (damage from L_DA19)."""),
    0x704A: ('FuelGauge', 'verified', """
FU bar value, written by L_D873 from the commander's fuel (L_A844)."""),
    0x704C: ('CabinTemperature', 'verified', """
CT bar value.  L_88E1 sets it from the distance to the sun when close to it;
UpdateExpandingSun increments it every frame; cleared at launch and after
hyperspace."""),
    0x704E: ('LaserTemperature', 'verified', """
LT bar value, raised and checked by the laser-firing code (L_EBC7..L_EC39);
cleared at launch."""),
    0x7050: ('AltitudeGauge', 'verified', """
AL bar value: $A0 minus the distance-derived value to the planet (L_892F),
$A0 (full) when far from it."""),
    0x7052: ('SpeedGauge', 'verified', """
SP bar value, PlayerSpeed*5+5, computed by ReadFlightControls."""),
    0x7054: ('EnergyBank1', 'verified', """
Energy bank 1 of 4 (gauge "1"), 0..160.  Damage drains bank 1 first
(L_A5A6); recharge (L_A641) fills bank 4 first.  When all four are empty
L_A5AB sets PlayerDeadFlag."""),
    0x7056: ('EnergyBank2', 'verified', """
Energy bank 2 of 4 (gauge "2"); accessed only through the bank loops."""),
    0x7058: ('EnergyBank3', 'verified', """
Energy bank 3 of 4 (gauge "3").  ToggleCloak requires at least $28 here."""),
    0x705A: ('EnergyBank4', 'verified', """
Energy bank 4 of 4 (gauge "4").  Below $A0 L_A572 sets FlightCondition $63;
below $9F L_D500 shows "ENERGY LOW" and switches the cloak off."""),
    0x705C: ('RollIndicator', 'verified', """
RL indicator position: 21 + roll magnitude for a positive roll, 21 -
magnitude for a negative one (ReadFlightControls).  Drawn as a two-pixel
marker at pixels value-2..value-1 of the gauge."""),
    0x705E: ('PitchIndicator', 'verified', """
DC indicator position, computed from PlayerPitch like RollIndicator."""),
    0x705F: (None, 'verified', """
Two bytes after the gauge table; no static or runtime access was found (no
instruction or pointer operand $705F/$7060 in the image; no traced read or write)."""),
    # ------------------------------------------------------------------
    # Flight state
    0x7061: ('WitchspaceFlag', 'verified', """
Nonzero after a hyperspace jump that ended between systems: L_D68B sets it
when bit 6 of the option byte L_FC14 is set or AuxRandomSeed's low byte is
$F9, places the current coordinates midway to the target, clears
StationPresent, and PlayHyperspaceArrival then launches a Thargoid group
(DispatchShipEvent 1).  While set, the sun/planet are not drawn or moved,
no station tunnel starts and ordinary encounters are suppressed.
Cleared on a normal arrival (L_D6B3) and at game start."""),
    0x7062: ('FlightCondition', 'verified', """
0 while docked; in flight the colour of the cockpit condition cells
(L_A4E8 stores it as an attribute): 4 green (launch, L_A553), 6 yellow
(L_8DDE, L_8A30), 2 red (L_A4BD when a shield is empty, L_8A28), $63
flashing red (L_A572 when EnergyBank4 is below $A0, L_8A2C); L_A4D6
alternates attributes 0 and 2 for $63.
The main loop takes the docked path for 0 and the flight path otherwise."""),
    0x7063: ('AuxRandomSeed', 'verified', """
Word state of the small generator L_A465 used by L_A334 (particle
coordinates); saved back at L_A3EA.  Its low byte is also read as a random
value: $F9 forces witchspace at hyperspace arrival (L_D684) and the
pirate check at $D80C compares it.  L_7A88 seeds launch particles from it."""),
    0x7065: ('SunPosition', 'verified', """
Sun position: x, y, z, each three bytes (fraction, then a 16-bit word whose
bit 15 is the sign).  Evidence: L_88E1 derives CabinTemperature and the
fuel-scoop range from it; DrawSunAndPlanet draws it with circle mode 0.
L_D6E2 places it at hyperspace arrival; L_DED1 moves it with the player."""),
    # Component labels of the 9-byte records are documented by the data comments.
    0x7066: ('SunXWord', 'verified', ''),
    0x7067: ('SunXHigh', 'verified', ''),
    0x7068: ('SunY', 'verified', ''),
    0x7069: ('SunYWord', 'verified', ''),
    0x706A: ('SunYHigh', 'verified', ''),
    0x706B: ('SunZ', 'verified', ''),
    0x706C: ('SunZWord', 'verified', ''),
    0x706D: ('SunZHigh', 'verified', """
High byte and sign of the sun z word; LaunchFromStation flips its sign."""),
    0x706E: ('PlanetPosition', 'verified', """
Planet position, same 9-byte format as SunPosition.  L_892F derives
AltitudeGauge and StationPresent from it; L_D72B copies it into station
slot 0 before offsetting the station; drawn with circle mode 1."""),
    0x706F: ('PlanetXWord', 'verified', ''),
    0x7070: ('PlanetXHigh', 'verified', ''),
    0x7071: ('PlanetY', 'verified', ''),
    0x7072: ('PlanetYWord', 'verified', ''),
    0x7073: ('PlanetYHigh', 'verified', ''),
    0x7074: ('PlanetZ', 'verified', ''),
    0x7075: ('PlanetZWord', 'verified', """
Low byte of the planet z word (LaunchFromStation sets z to $0180)."""),
    0x7076: ('PlanetZHigh', 'verified', ''),
    0x7078: ('StationDormantFlag', 'verified', """
Nonzero ($FF) while station slot 0 is inactive: UpdateStationDormancy sets it
when the station's energy is zero and clears it (restoring energy $F0) once
all three station coordinate words are below 256.  Set at hyperspace
arrival, cleared at launch.  The in-system jump (L_9966) requires it
nonzero.  While it is $FF the compass keeps using the station slot, but L_897E
switches to the coarse 24-bit form (CompassOffsetCoarse)."""),
    0x7079: ('FuelScoopRangeFlag', 'verified', """
1 while the sun closeness value of L_88E1 (negated L_8A5A result) exceeds
$2000; above $4000 L_8A09 is taken instead.  With fuel scoops fitted
(L_A84A) L_D500 then shows token $A0 "FUEL SCOOPS ON" and adds fuel."""),
    0x707A: ('PlayerDeadFlag', 'verified', """
Nonzero ends the game: the main loop runs RunGameOverSequence.  Set when all
energy banks are empty (L_A5AB), by a collision/crash path (L_8A09, L_EB58)
and by UpdateExpandingSun; ReadFlightControls input and L_ED3F laser
handling stop while it is set."""),
    0x707B: ('LargeSunFlag', 'verified', """
1 when the sun is visible with a projected radius of 40 or more
(DrawSunAndPlanet).  L_DA29 then patches the four line-plot sites
(L_F203, L_F231, L_F252, L_F27E) to XOR C instead of OR C, so lines stay
visible over the large sun."""),
    0x707C: ('ControlsLockedFlag', 'verified', """
Nonzero suspends ReadFlightControls in the main loop.  Only four stores exist:
DockIntoStation sets it and it stays set while docked until LaunchFromStation
clears it after the launch tunnel; RunGameOverSequence sets it for the death
sequence and clears it before the restart.  After a game-ending message on docking
(EndGameWithMessage) it therefore stays set into the next game until its first launch."""),
    0x707D: ('SoundEffectRequests', 'verified', """
Bit mask of pending sound effects.  L_9082 (sound enabled: bit 7 of L_FC14)
selects the lowest set bit and jumps through the 8-entry JP table at L_906A
to a beeper routine (OUT ($FE)).  Bits are set by game events, e.g. bit 0
energy bomb (L_9275), bit 2 (L_EB44), bit 4 (L_EC18), bit 6 (L_EB10)."""),
    0x707E: ('DockingComputerFlag', 'verified', """
Set when the docking-computer key docks the ship (L_70CF); cleared by L_9A46
at launch.  While set L_D500 shows token $7B "DOCKING COMPUTERS ON"."""),
    # ------------------------------------------------------------------
    # Flight controls and docking
    0x707F: ('ReadFlightControls', 'verified', """
Copy the high bytes of the interrupt-maintained accumulators RollControl,
PitchControl and SpeedControl (L_FF09, L_FF0B, L_FF0D) into PlayerRoll, PlayerPitch
and PlayerSpeed, and compute RollIndicator/PitchIndicator (21 +/- magnitude) and
SpeedGauge (speed*5+5).  Called by MainLoop unless ControlsLockedFlag is set.
Clobbers A, B, C, HL.
Evidence: tools/check_routines.py controls/read-flight-controls, controls/draw-gauges;
runtime writers of $FF09/$FF0B/$FF0D are $FE7A/$FEE8/$FF1D in the interrupt code."""),
    0x70BE: ('CheckDocking', 'verified', """
Per-frame docking check in flight.  Return if L_7C39 (set by the hyperspace
key handler L_D574) is set.  If L_DA15 (station slot contact, set at L_EB0C)
is set, clear it and dock (DockWithStation).  Otherwise read and clear key
bit 7 of L_FC11 and dock with the docking computer if the station is
present, docking computers are fitted (L_A84E), the ship is in flight,
L_A80A is clear (no hyperspace countdown: L_D574 sets 1 or 2 for normal or
galactic hyperspace) and the station is not hostile (byte +$21 bit 2)."""),
    0x70CF: ('CheckDockingComputerKey', 'verified', """
Docking-computer key path of CheckDocking: read and clear bit 7 of KeyFlagsCombat
(key C).  Docking needs StationPresent, DockingComputerFitted, FlightCondition
nonzero, L_A80A clear and the station's hostile bit (+$21 bit 2) clear; then
DockingComputerFlag = 1 and fall into DockWithStation.  Every refusal just returns."""),
    0x70FB: ('DockWithStation', 'verified', """
Dock: select the front view, restore the cockpit, make SunPosition
relative to the station (MakeSunRelativeToStation) and run the docking
tunnel through StartStationTunnel."""),
    0x7102: ('StartDockingSequence', 'verified', """
Common docking path: MakeSunRelativeToStation, then StartStationTunnel (which runs
the docking tunnel because FlightCondition is nonzero).  Reached by falling through
DockWithStation and by the JP in UpdateEscapePod when its EscapePodTimer countdown
(24 frames after the escape pod is launched) reaches zero, so the escape pod also
ends docked at the station.  Evidence: instruction semantics; runtime: executed, and
the countdown test at $A784 is executed too."""),
    0x7108: ('MakeSunRelativeToStation', 'verified', """
For x, y and z: sun word = sun word - station word (slot 0 at
InitialRuntimeState), using L_E8F0 (halved signed difference) and doubling
the result again, so bit 0 of each word is lost.  Fraction bytes are kept.
IX and IY advance by 3 per axis.  Used on every docking (StartDockingSequence): the
sun position becomes relative to the station, which is the docked ship's position;
that is the position a tape save stores (SavedSunPosition) and that
LaunchFromStation later mirrors in z.
Evidence: tools/check_routines.py maths/sun-relative-to-station (3000 cases)."""),
    0x7116: (None, 'verified', """
One axis of MakeSunRelativeToStation: difference, double, keep the sign."""),
    0x712C: (None, 'verified', """
HL = word at IY+1 (sun), DE = word at IX+1 (station); continue in L_E8F0,
which returns (HL - DE)/2 in sign-magnitude form."""),
    0x713B: ('HandleChartCursorKeys', 'verified', """
Chart keys.  Only on screens 7 (galactic chart, handler 3) and 8 (short-range chart,
handler 4) and only while L_A80A is clear (no hyperspace countdown or tunnel): take
the lowest set bit n of (L_FC0F AND $0F) OR (L_FC12 AND $70) and run screen handler
9 + n through L_8F02, then clear both key bytes.  Handlers: 9 cursor left (bit 0),
10 right (1), 11 down (2), 12 up (3), 13 cursor to the current system (bit 4),
14 snap to the nearest system (5), 15 find a system by name (6).
Called by MainLoop when docked and by the non-view flight frame (L_72D2).
Evidence: HandleScreenKeys maps screen keys to screens 7..12 = handlers 3..8; the JP table
ScreenFunctionTable; tools/check_routines.py controls/p1-chart-cursor-keys."""),
    0x7169: ('UnusedEnableInterrupts', 'verified', """
Unused routine: EI, RET.  It follows the unconditional RET of L_713B
and precedes Startup, so only a call or jump could enter it, and there is none: no
word $7169 in the image, no relative jump to it, and the seven 48K access traces
neither execute nor read it.  Called, it enables interrupts and returns with every other register and
all memory unchanged.  The comparison 48K memory images contain no RET, EI, RET
sequence, so it is not a leftover of their layout.
Evidence: tools/check_routines.py dormant/unused-interrupt-routines; execution, read and
write maps of tools/run_runtime_scenarios.py --accesses."""),
    0x716B: (None, 'verified', """
One-time start-up (default ship variant): copy the font (FontBitmapSize = 728 bytes,
glyphs $20..$7A) to FontRuntime and the initial cockpit colours to the mutable buffer
CockpitAttributesRuntime, because their tape areas at $C000/$C700 are reused as view
buffer and work space.  Then install IM 2, enable interrupts, save SP in
StartupStackPointer, reset the inputs and draw the first cockpit screen."""),
    # ------------------------------------------------------------------
    # Title screen and main loop
    0x718F: ('RunTitleScreen', 'verified', """
Title sequence; also the restart point after death or a game-ending message
(the stack is reset by EndGameWithMessage).  Show title ship ID 9 (Cobra Mk III)
in slot 7 (DispatchShipEvent event 9 creates ship C+2, C = high nibble), set bit 7 of
station byte +$1D, paint the top two thirds' attributes white
on black, then loop showing "LOAD NEW COMMANDER (Y/N)?" with a rotating ship.
'Y' opens the tape/access menu (L_D2E4); any other key continues to the
"PRESS SPACE, COMMANDER" loop with a new title ship."""),
    0x71A2: (None, 'verified', """
Load-prompt loop: one animated frame per pass until a key is pressed
(L_FC13 holds $FF while none is)."""),
    0x71BE: (None, 'verified', """
Return from the access menu (also from the docked main loop when L_D2E4
returns NZ): front view, clear screen, restore cockpit, then the start
prompt."""),
    0x71C8: (None, 'verified', """
Wait for key release, then pick the next title ship from TitleShipCounter:
C = (counter AND 7) + 1, plus 10 when below 6 (11..15, 6, 7, 8); event 9
then shows ship ID C+2: 13..17 (Asp Mk II, Fer-de-Lance, Thargoid, Sidewinder,
blueprint slot 17), then 8, 9, 10 (Viper, Cobra Mk III, Python).
Evidence: tools/check_routines.py controls/p1-title-ship-cycle; docs/SHIPS.md IDs."""),
    0x71E5: (None, 'verified', """
Start-prompt loop.  Each pass waits one frame (HALT; the interrupt rescans the keys)
and then picks the control method from a joystick held left: Kempston port $1F bit 1
(only if bit 5 reads 0, taken as an interface being present) selects 1, key '5'
(Cursor left, L_FC15 bit 1) selects 2 and key '6' (Sinclair left, bit 3) selects 3;
SPACE (L_FC13 = $20) selects 0 (keyboard)."""),
    0x7219: (None, 'verified', """
Joystick start: remember the method (1..3) in L_8F67 for the freeze-menu
keyboard/joystick toggle; B = method."""),
    0x721F: ('StartNewGame', 'verified', """
Store control method B in bits 0-1 of L_FC14, restore the commander
(L_A976), clear WitchspaceFlag, FlightCondition (docked), L_A87C,
FuelScoopRangeFlag, L_A80C (cloak) and ExpandingSunRadius, show the status
screen (L_D0B9), reset inputs and enter MainLoop."""),
    0x7248: ('DrawTitleLoadPrompt', 'verified', """
Print the title banner and message 6 "LOAD NEW COMMANDER (Y/N)?" at
column 1, row 14 into the view buffer."""),
    0x7252: ('DrawTitleStartPrompt', 'verified', """
Print the title banner and message 7 "PRESS SPACE, COMMANDER" at column 4,
row 14 into the view buffer."""),
    0x725A: (None, 'verified', """
HL = row/column, A = message: print the message into the view buffer."""),
    0x7267: ('PrintTitleBanner', 'verified', """
Print token $1D "---- E L I T E ----" at column 5, row 1 into the view
buffer: setting bit 7 of L_BB81 (high byte of the LD HL,$4000 at L_BB7F)
redirects the character renderer from screen $4000 to $C000."""),
    0x7277: (None, 'verified', """
Restore the character renderer to the screen (clear bit 7 of L_BB81)."""),
    0x727D: ('FillAttributePageWhite', 'verified', """
Fill 256 bytes from HL with $07 (white ink on black paper): eight attribute rows.
Output: HL advanced by 256, A = 7, B = 0.  RunTitleScreen calls it twice from $5800
for attribute rows 0..15 (the view area)."""),
    0x7286: ('TitleShipCounter', 'verified', """
Incremented for each new title ship; see L_71C8."""),
    0x7287: ('MainLoop', 'verified', """
One game frame.  Unless ControlsLockedFlag is set read the flight controls;
handle view keys (L_8E95) and L_8F68 (carry: abandon the game, return to
the title); hyperspace keys (L_D574).  Docked (FlightCondition 0): chart
keys, SYMBOL SHIFT (bit 5 of L_FC0F) for the access menu (L_D2E4; back to the
start prompt if a commander was loaded) or the status page.  In flight: docking
check, jump drive (L_9966), sun/planet motion
and station dormancy (outside witchspace), then either a cockpit-view frame
(L_72FD) or a non-view screen frame (L_72D2), and finally L_732B."""),
    0x72C0: (None, 'verified', 'In-flight part of MainLoop.'),
    0x72D2: (None, 'verified', """
Non-view screen while flying (CurrentScreenId 4 or more): update ships and
lasers without drawing; unless CheckDocking docked in this frame (FlightCondition
0) also the condition colour (L_8DDE) and the energy/shield update L_A572, which
L_A559 runs on cockpit views.  Then keep the expanding sun growing, print the
message line and wait 8 frames, polling the chart keys."""),
    0x72FD: (None, 'verified', """
Cockpit-view frame: clear the view buffer, draw sun/planet (not in
witchspace), particles (L_9E74), view name (L_D44C), ships, lasers, the
hyperspace arrival tunnel, blit, scanner (L_8C29), gauges, cloak key and
indicators (L_A559)."""),
    0x732B: (None, 'verified', """
End of frame: L_88E1 (altitude, cabin temperature, station presence), then
loop unless PlayerDeadFlag is set."""),
    0x7335: ('RunGameOverSequence', 'verified', """
Death: stop, lock controls, normal colours (L_9287 with L=7), remove the scanner
contacts (L_8E1D), empty every slot and release the wreck (L_EBA4: a cargo canister
and two alloy plates), explosion noise (L_9051, L_9030), then 30 frames of stardust
and moving objects with message 9 " GAME OVER" at column 10, row 7 of the view,
blank the view, free slots 1..7, wait 50 frames, unlock the controls, clear
PlayerDeadFlag and L_7C39 and restart at RunTitleScreen.
Not reached in the recorded runtime scenarios."""),
    # ------------------------------------------------------------------
    # View buffer and cockpit
    0x7398: ('BlitViewBitmap', 'verified', """
Copy the 4 KB view buffer (screen layout of $4000..$4FFF, at $C000) to the
top two screen thirds: even pixel lines of both thirds first, then odd lines.
The bottom third (cockpit) is never written.
Evidence: tools/check_routines.py screen/clear-view-buffer, screen/blit-view-bitmap,
screen/restore-cockpit-test (every byte lands at buffer address - $8000)."""),
    0x73BD: ('BlitAlternateLines', 'verified', """
DE = screen line address, HL = DE + $8000: copy four pixel lines two apart
(32 bytes each) for each of the 8 character rows of one screen third.
The LDIs count down in C (reset to $FF per row), so B stays the row counter.
Output (for the third-aligned entries used): B = 0, DE back at its entry value
(E wraps after 8 rows), HL = DE + $8000.  Clobbers A, C."""),
    0x741C: ('RestoreCockpitIfFullScreen', 'verified', """
Return at once unless screen byte $4000 is $FF.  L_BC9E (full-screen page
clear) draws a top line, so $FF there means a full-screen page is shown;
cockpit views leave $00 (ClearViewBuffer).  Then clear key state (L_7C09)
and fall into ClearScreenAndDrawCockpit."""),
    0x7425: ('ClearScreenAndDrawCockpit', 'verified', """
Clear the screen (L_BC9E), black out attribute columns 0 and 31 of all 24
rows, copy the cockpit bitmap and colours to the bottom third, then
CockpitRestored."""),
    0x7451: ('CockpitRestored', 'verified', """
If commander byte L_A843 is set, L_9287 recolours the view red (L=2).
L_A843 is NovaMissionActive (missions/p5-nova-mission).
Then L_8DF2 (SaveScannerBackground) stores the clean scanner area of the freshly
drawn cockpit in the backup buffer, which the contact plotter restores each frame."""),
    0x745F: ('ClearViewBuffer', 'verified', """
Clear the 4 KB view buffer with the stack (interrupts off, SP saved in
ViewClearSavedSP) and draw the view frame: the first and last 32 bytes become
$00,$FF x30,$00 (top and bottom lines, rows y=0 and y=127) and all other
rows $00,$80,0...,0,$01,$00 (side pixels at x=8 and x=247).  The frame is thus
redrawn by every clear.  Interrupts are enabled again on return.
Clobbers A, BC, DE, HL, IX.  Evidence: tools/check_routines.py screen/clear-view-buffer,
screen/blit-view-bitmap, screen/restore-cockpit-test."""),
    0x74B0: ('ViewClearSavedSP', 'verified', 'Stack pointer saved by ClearViewBuffer.'),
    0x74B2: ('StartupStackPointer', 'verified', """
Stack pointer saved at startup (StartupAfterGraphicsCopy, also AdderStartup);
EndGameWithMessage reloads it before restarting the title."""),
    # ------------------------------------------------------------------
    # Sun and planet
    0x74B4: ('ProjectionX', 'verified', """
9-byte work copy of the body being projected (x, y, z; same format as
SunPosition), filled by DrawSunAndPlanet for ProjectBodyPosition."""),
    0x74B5: ('ProjectionXWord', 'verified', ''),   # documented by the data comments
    0x74B6: ('ProjectionXHigh', 'verified', ''),
    0x74B7: ('ProjectionY', 'verified', ''),
    0x74B8: ('ProjectionYWord', 'verified', ''),
    0x74B9: ('ProjectionYHigh', 'verified', ''),
    0x74BA: ('ProjectionZ', 'verified', ''),
    0x74BB: ('ProjectionZWord', 'verified', ''),
    0x74BC: ('ProjectionZHigh', 'verified', ''),
    0x74BD: ('ExpandingSunRadius', 'verified', """
Sun radius while the expanding-sun effect runs (UpdateExpandingSun); 0 when
inactive.  Cleared at game start and at the end of the hyperspace tunnel."""),
    0x74BE: ('DrawSunAndPlanet', 'verified', """
Clear LargeSunFlag, copy SunPosition to ProjectionX and project it
(ProjectBodyPosition); run UpdateExpandingSun; if the sun is in view draw it as a
filled disc (L_7CF0, nothing below radius 9) and set LargeSunFlag for a radius of 40
or more, so the following UpdateObjects XOR-plots lines over it.  Then copy and project
PlanetPosition and draw the planet as an outline circle (L_7CFE, radius 9 or more).
Called by the cockpit-view frame (not in witchspace) and by the last 11 launch frames.
Evidence: tools/check_routines.py pipeline/project-body-position, circles/circle-renderer."""),
    0x74E7: (None, 'verified', 'Planet half of DrawSunAndPlanet.'),
    0x74FA: ('UpdateExpandingSun', 'verified', """
Only while L_A87C is set: CabinTemperature += 1 and the sun radius grows by 2
per call (starting from the radius just projected in L_7C3D); the result is
stored in L_7C3D and ExpandingSunRadius.  Reaching 256 sets PlayerDeadFlag and
leaves radius 0.  Called by DrawSunAndPlanet (even when the sun is out of view) and
by the non-view flight frame, so the growth continues on every screen; L_7ACD
clears ExpandingSunRadius after a hyperspace jump, restarting from the new sun.
This is the supernova of the nova mission: L_A87C (ExpandingSunActive) is armed by
ArmExpandingSun (missions/p5-nova-mission)."""),
    0x751F: ('ProjectBodyPosition', 'verified', """
Perspective projection of ProjectionX..ProjectionZ for the current view
(CurrentScreenId 0 front: depth +z; 1 rear: -z; 2 left: -x; 3 right: +x).
Returns A=1 when in front of the viewer, with
  L_7C3B = low byte of 256*|horizontal|/depth, L_7C3A = same for vertical;
  L_7C3C bit 0 = right of centre, bit 1 = above centre, bit 2/bit 3 =
  horizontal/vertical offset below 256 (clear: offset 256..511);
  L_7C3D = radius $A000/depth word, 255 when the depth word is $00A0 or less.
Returns A=0 when behind the viewer, when the depth word exceeds $A000 or when an
offset reaches 512.  The depth coordinate's sign is cleared in place in ProjectionX..
Offsets below 256 are within 2 of the exact quotient; for the 256..511 range see the
NOTE at L_7746.
Evidence: tools/check_routines.py pipeline/project-body-position,
pipeline/p1-projection-offset-paths."""),
    0x7550: (None, 'verified', 'Front/rear views: horizontal and vertical offsets, then radius.'),
    0x75D3: (None, 'verified', 'Rear view: depth must be negative; horizontal sign is mirrored.'),
    0x7601: (None, 'verified', 'Left view: depth is -x, horizontal is z.'),
    0x762A: (None, 'verified', 'Left/right views: offsets and radius as in L_7550.'),
    0x76AD: (None, 'verified', 'Right view: depth is +x, horizontal is mirrored z.'),
    0x76D0: ('ProjectionVisible', 'verified', """
Store the radius A in L_7C3D and return A=1 (visible)."""),
    0x76D6: (None, 'verified', """
Part of ProjectCoordinate, coordinate larger than the depth: a coordinate word below
256 (so the depth word is below 256 too) is moved up one byte (H:L = coordinate
low:fraction, D:E = depth low:fraction) and the first 8-step shift loop is skipped.
B keeps the depth fraction, which L_7746 later shifts in again.
Evidence: instruction semantics; tools/check_routines.py pipeline/p1-projection-offset-paths."""),
    0x76DC: ('ProjectCoordinate', 'verified', """
HL = coordinate word (sign masked), C = its fraction byte; DE = depth word,
B = depth fraction.  Return D = low byte of 256*|coordinate|/depth, setting
bit 2 (first call) or bit 3 (second call, counted in C') of B' when
|coordinate| <= depth (offset 0..255; equality gives 255).  For a larger coordinate
both values are shifted left until the coordinate's top bit falls out (L_7746).
An offset of 512 or more discards the caller's return address and returns A=0 from
ProjectBodyPosition (L_7764/L_7766).  The <= depth path (L_7729) shifts both values
until the depth's top bit falls out and divides the top bytes (DivideFractionAB):
results are within 2 of the exact quotient (depth 2/256 or more).
Evidence: tools/check_routines.py pipeline/project-body-position,
pipeline/p1-projection-offset-paths."""),
    0x7746: (None, 'verified', """
Offset 256..511 path: coordinate and depth shifted together, the coordinate's top
bit restored; a coordinate of twice the depth or more leaves via L_7764 (not
visible), otherwise D = 256*(coordinate - depth)/depth from the top bytes.
NOTE: the result is approximate.  The depth is shifted once more than the
coordinate and SCF / RR D at L_775C only restores its high byte (E stays shifted).
With as many significant bits as the depth the offset is within 3 of
256*|c|/depth - 256, except for a rare borrow when the coordinate barely exceeds the
depth (x $1774EC, z $176C2A: 173 instead of 0).  With more significant bits than the
depth (most ratios between 1 and 2) the divisor D is the depth's high byte with bit 7
forced on instead of a normalised depth, and the offset is up to 127 too large
(x $180000, z $0F0000: 206 instead of 153).  Close to the sun or planet this can
hide a large disc just beyond an edge of the view: x $80E5, z $7E00 gives 131 instead of 6, so
DrawCircle draws nothing where the disc should fill columns 136..247.
Evidence: tools/check_routines.py pipeline/p1-projection-offset-paths (bit-level model
of this path, random cases of both kinds, the hidden disc)."""),
    0x7766: ('ProjectionNotVisible', 'verified', 'Return A=0 (body not visible).'),
    0x7777: ('DivideFractionAB', 'verified', """
D = A*256/B (requires A < B); E is cleared.  Falls into DivideFractionAEB.
Evidence: tools/check_routines.py maths/fraction-dividers (all A < B)."""),
    0x7779: ('DivideFractionAEB', 'verified', """
D = (A*256+E)/B for A < B (8 restoring-division steps; the initial D=$FE
terminates the loop).  Evidence: tools/check_routines.py maths/fraction-dividers."""),
    0x778F: ('MoveSunAndPlanet', 'verified', """
Apply the player's motion to SunPosition and PlanetPosition (L_DED1 with
IX = each body)."""),
    0x779D: ('UpdateStationDormancy', 'verified', """
IX = station slot 0.  If StationDormantFlag is clear and the station has
energy, return; if it has none, set the flag ($FF).  While dormant, move the
station (L_DCE0); when the high bytes of x, y and z are all zero and bit 7
of byte +$26 is clear, clear the flag and give the station energy $F0.
So once the station slot has lost its energy (L_DCE0 frees far objects; energy 0
means a free slot), it is kept off but still moved here, and it is switched on again
when every coordinate word is below 256; HandleTorusJumpKey only jumps while the
flag is set.
Called by the in-flight main loop outside witchspace."""),
    0x77D4: ('CloakKeyDelay', 'verified', """
Call counter of ToggleCloak: the key is examined on every second call."""),
    0x77D5: ('ToggleCloak', 'verified', """
Clear key latch bit 7 of L_FC0E on every call; on every second call wait one
frame (HALT) and test whether the interrupt set it again.  If so and commander
bit 6 of L_A872 is set: DEC L_A80C; reaching 0 switches off (white view,
L=7).  Otherwise EnergyBank3 must be >= $28: set L_A80C = 1, clear the
station's hostility bit and SharedHostilityAlert and colour the view blue
(L_9287, L=$0F).  L_A599 drains extra energy while L_A80C is nonzero.
NOTE: with too little energy the DEC leaves L_A80C at $FF (nonzero) without
the blue colours; the next key press then switches it on properly.
The device is the cloaking device: the key is Y (L_FC0E bit 7) and the required
L_A872 bit 6 is the one the status page lists as CLOAKING DEVICE.
Evidence: tools/check_routines.py controls/p1-cloak-toggle."""),
    0x780F: (None, 'inferred', """
Unreferenced code: LD A,(L_A843) / AND A falls into L_7813 (red view colours
when set).  No static, pointer or runtime reference was found; decoded
because it ends exactly at the verified instruction L_7813."""),
    0x7818: (None, 'inferred', """
Unreferenced code: if L_A80C is set jump to L_7806 (blue view colours).
No static, pointer or runtime reference was found; decoded because its JR
lands on a verified instruction and it ends exactly at ArmExpandingSun."""),
    0x781F: ('ArmExpandingSun', 'verified', """
Called at launch.  If commander byte L_A843 is set: L_A87C = 1, which
enables UpdateExpandingSun, and the view is coloured red (L_9287, L=2)."""),
    0x782B: ('CheckMissionStateOnDocking', 'verified', """
Docking: act on commander byte L_A871: 1 or 2 -> L_D219 (Y/N mission offer;
'Y' stores 3), 4 -> EndGameWithMessage with message 212 " THARGON" (boarded),
5 -> L_D243 (reward: adds 1 to L_A824, sets bit 3 of L_A872, clears L_A871);
0, 3 and 6..255 do nothing.  Called by DockIntoStation before CheckPirateGameOver.
Evidence: tools/check_routines.py missions/p1-mission-state-on-docking.
L_A871 is InvasionMissionState (missions/p5-invasion-mission)."""),
    0x7840: ('CheckPirateGameOver', 'verified', """
Docking: if bit 7 of station byte +$1D was cleared (L_D812 does this),
end the game with message 13 " PIRATE"."""),
    0x7848: ('EndGameWithMessage', 'verified', """
A = message: L_D1EC prints it, then "S" and "THEY SHOW NO MERCY...".
Then front view, restore the cockpit, reload StartupStackPointer and
restart at RunTitleScreen."""),
    # ------------------------------------------------------------------
    # Gauges
    0x7859: ('DrawGauges', 'verified', """
Redraw each changed gauge: 11 bars (DrawBarGauge, value/4 pixels) and the
RL/DC indicators (DrawIndicatorGauge), using GaugeDisplayTable and
GaugeScreenAddresses.  Called every cockpit-view frame and once by LaunchFromStation.
Evidence: tools/check_routines.py controls/read-flight-controls, controls/draw-gauges,
controls/p1-gauge-all-lengths."""),
    0x78A3: ('GaugeIndicatorMode', 'verified', """
1 while DrawGauges draws the two indicator gauges, 0 for bars."""),
    0x78A4: ('GaugeScreenAddresses', 'verified', """
Screen address of pixel line 1 of each gauge (bottom third, five lines
high, 40 pixels wide), in GaugeDisplayTable order.  The 14th entry ($51E3,
the row of the missile icons) is never read."""),
    0x78C0: ('DrawIndicatorGauge', 'verified', """
A = position, DE = the gauge's GaugeScreenAddresses entry: patch the shared drawer
for a two-pixel marker at pixels A-2..A-1 (empty fill, end mask $03) and draw it.
DrawGauges sets GaugeIndicatorMode around the calls."""),
    0x78CF: ('DrawBarGauge', 'verified', """
A = length in pixels (0..40), DE = the gauge's GaugeScreenAddresses entry: patch
the shared drawer for a solid bar (fill $FF, end mask $FF) and draw it."""),
    0x78DB: (None, 'verified', """
Shared gauge drawer: HL = screen address from (DE); B = length/position.
Writes five identical pixel lines of five bytes; the last byte always keeps
the right border pixel (bit 0)."""),
    0x78ED: ('GaugeEndMask', 'verified', """
Operand of LD C,n: end byte used when the length is a multiple of 8.
DrawBarGauge stores $FF, DrawIndicatorGauge $03."""),
    0x7917: ('GaugeFillByte', 'verified', """
Operand of LD A,n: fill byte before the end byte ($FF bars, $00 indicators)."""),
    0x7939: ('GaugeFillByteFull', 'verified', """
Same as GaugeFillByte for a gauge whose end byte is the fifth byte."""),
    0x794C: (None, 'verified', """
Length 1..8 (only the first of the five bytes is used): on each of the five pixel
lines store end byte C in byte 1, clear bytes 2..4 and write $01 (border pixel)
into byte 5.  StoreGaugeEndByte is not used here.
Evidence: tools/check_routines.py controls/p1-gauge-all-lengths."""),
    0x7961: (None, 'verified', """
Zero length (empty gauge, HL = its screen address): on all five pixel lines clear
bytes 1..4 and write $01 into byte 5, keeping the right border pixel."""),
    0x7975: (None, 'verified', """
Indicator with position mod 8 = r (1..7, in B): marker byte $80 for r = 1 (the
other pixel is bit 0 of the previous byte, see StoreGaugeEndByte), otherwise $C0
shifted right r-2 times, i.e. pixels r-2 and r-1 of the end byte.  A multiple of 8
does not come here: it uses GaugeEndMask $03 (pixels 6 and 7)."""),
    0x7986: ('StoreGaugeEndByte', 'verified', """
Store end byte C.  In indicator mode a marker byte of $80/$81 also sets bit 0
of the previous byte, so the two-pixel marker can straddle two bytes."""),
    # ------------------------------------------------------------------
    # Tunnels
    0x7999: ('StepTunnelAnimation', 'verified', """
Print the view name/messages (L_D44C), then if a tunnel animation is active
(L_A80A) run one step: while L_A80B is set, the whole first part runs inside
this call; afterwards each call draws one frame and counts it down.
The tunnel is a set of concentric outline circles centred in the view (rings of
radius 256/distance).  Callers: DockIntoStation, LaunchFromStation."""),
    0x79A3: ('PlayHyperspaceArrival', 'verified', """
Cockpit-view frame after a hyperspace jump (L_A80B set by L_D814): reset
inputs, clear all ship slots, in witchspace remove the station and launch a
Thargoid group (DispatchShipEvent 1), then run the 66-frame ring tunnel
with 16 rings (HyperspaceRingDistances) and finish at FinishHyperspaceTunnel.
With TunnelFrameLimit = 1 all 66 frames run inside this one call."""),
    0x79E3: (None, 'verified', """
Select the ring-loop exit: L_A80B set -> blit and count frames inside this
call (L_7A2B); clear -> one frame per call (L_7A44).  Centre the rings
(L_7C3A/L_7C3B = 0, L_7C3C = $0F)."""),
    0x7A06: (None, 'verified', """
Frame start: HL = ring distance table (patched operand)."""),
    0x7A07: ('TunnelRingTablePointer', 'verified', """
Operand of LD HL,nn: HyperspaceRingDistances (PlayHyperspaceArrival) or
StationTunnelRingDistances (StartStationTunnel)."""),
    0x7A09: (None, 'verified', """
Ring loop: decrement each distance d and draw a ring of radius 256/d
(DivideFractionABToC) with L_7D04 when the radius is 4 or more."""),
    0x7A25: ('TunnelRingsDoneOffset', 'verified', """
Displacement of JR Z: L_7A2B (5) while L_A80B is set, L_7A44 ($1E) otherwise."""),
    0x7A2B: (None, 'verified', """
In-call frame end: blit, count TunnelFrameCounter down and leave through
the patched JR C when it falls below TunnelFrameLimit."""),
    0x7A33: ('TunnelFrameLimit', 'verified', """
Operand of CP n: 1 for hyperspace, $30 for the station tunnel."""),
    0x7A38: ('TunnelExitOffset', 'verified', """
Displacement of JR C: FinishHyperspaceTunnel ($15), FinishLaunchTunnelLoop
($32, the on-tape value) or FinishDockingTunnelLoop ($38)."""),
    0x7A44: ('CountTunnelFrame', 'verified', """
Per-call frame end: decrement TunnelFrameCounter; at zero finish the
station tunnel (L_7A76)."""),
    0x7A4E: ('FinishHyperspaceTunnel', 'verified', """
Clear L_A80B and L_A80A, add 66 back to all 16 ring distances (SUB $BE),
clear and blit the view, then L_7ACD."""),
    0x7A6B: ('FinishLaunchTunnelLoop', 'verified', """
Launch: clear L_A80B and continue with L_7A88."""),
    0x7A71: ('FinishDockingTunnelLoop', 'verified', """
Docking: clear L_A80B and return.  Reached only through the patched JR C
(displacement $38 stored by DockIntoStation); executed in the runtime traces
(write to L_A80B from $7A72)."""),
    0x7A76: (None, 'verified', """
Station tunnel finished: clear L_A80A and add 64 back to the 8 station ring
distances (SUB $C0)."""),
    0x7A88: ('SeedLaunchDust', 'verified', """
After the first 17 launch-tunnel frames: PlayerSpeed = 7 for the remaining tunnel
frames; temporarily patch L_A347 (masks $83, RET at L_A3ED) and create all 16
stardust particles of L_A46C (the records MoveAndPlotDust moves and plots) from
AuxRandomSeed, each within 3 units of the centre and deep ahead (z >= $80), then
restore the original bytes.
Evidence: tools/check_routines.py dust/launch-dust-respawn, dust/stardust-update."""),
    0x7AB9: ('DivideFractionABToC', 'verified', """
C = A*256/B for A < B.  Evidence: tools/check_routines.py maths/fraction-dividers (all A < B)."""),
    0x7ACD: (None, 'verified', """
End of the hyperspace tunnel: white view colours unless L_A843 is set (then the
red view stays), clear ExpandingSunRadius (an armed expansion restarts from the new
sun's projected radius) and continue in L_903B (sound), which returns to the
caller of PlayHyperspaceArrival."""),
    0x7ADD: ('TunnelRingCount', 'verified', 'Rings per frame: 16 hyperspace, 8 station tunnel.'),
    0x7ADE: ('TunnelRingsLeft', 'verified', 'Rings left to draw in the current frame.'),
    0x7ADF: ('TunnelFrameCounter', 'verified', """
Frames left: $42 for hyperspace, $40 for the station tunnel (17 frames in
the first call, then 47 calls)."""),
    0x7AE0: ('HyperspaceRingDistances', 'verified', """
16 ring distances, decremented once per frame and restored afterwards."""),
    0x7AF0: ('StationTunnelRingDistances', 'verified', """
8 ring distances of the launch/docking tunnel, restored afterwards."""),
    0x7AF8: ('StartStationTunnel', 'verified', """
Not in witchspace: set up the 8-ring station tunnel and L_A80A = L_A80B = 1,
then launch (LaunchFromStation) when docked, otherwise dock (DockIntoStation).
Called from L_8ED1 (docked, launch key) and reached from DockWithStation."""),
    0x7B1E: ('DockIntoStation', 'verified', """
Docking tunnel: speed 12, no roll/pitch, ECM off, controls locked, then the
64-frame tunnel (17 frames in the first StepTunnelAnimation call, 47 calls).
Afterwards FlightCondition = 0 (docked), run the docking checks (L_782B,
CheckPirateGameOver) and show screen 7 (status) via L_8F02."""),
    0x7B68: ('LaunchFromStation', 'verified', """
FlightCondition = 4 (green), front view, station active, cloak off; reset
shields/energy (L_9A46), ArmExpandingSun; planet ahead at z = $0180, sun z
mirrored, station slot 0 just behind the ship (z fraction $F0, negative,
unit orientation, energy $F0); clear other slots; draw gauges; then the
64-frame tunnel (17 in the first call, then 36 + 11 calls, the last 11 also
moving and drawing sun and planet).  Falls into ResetFlightInputs."""),
    0x7BFF: ('ResetFlightInputs', 'verified', """
Clear the interrupt input bytes L_FF08..L_FF0C and set L_FF0D (high byte of
SpeedControl) to 12, so the next ReadFlightControls gives speed 12 with no roll or
pitch; then clear the key state L_FC0E..L_FC12 (L_7C09).
Output (from L_7C09/ClearBytes): A = 0, B = 0, HL = L_FC13."""),
}

COMMENTS = {
    # GaugeDisplayTable
    0x7045: 'drawn copy of ForwardShield',
    0x7047: 'drawn copy of AftShield',
    0x7049: 'drawn copy of FuelGauge',
    0x704B: 'drawn copy of CabinTemperature',
    0x704D: 'drawn copy of LaserTemperature',
    0x704F: 'drawn copy of AltitudeGauge',
    0x7051: 'drawn copy of SpeedGauge',
    0x7053: 'drawn copy of EnergyBank1',
    0x7055: 'drawn copy of EnergyBank2',
    0x7057: 'drawn copy of EnergyBank3',
    0x7059: 'drawn copy of EnergyBank4',
    0x705B: 'drawn copy of RollIndicator',
    0x705D: 'drawn copy of PitchIndicator',
    # SunPosition
    0x7065: 'sun x fraction',
    0x7066: 'sun x word low',
    0x7067: 'sun x word high, bit 7 sign',
    0x7068: 'sun y fraction',
    0x7069: 'sun y word low',
    0x706A: 'sun y word high, bit 7 sign',
    0x706B: 'sun z fraction',
    0x706C: 'sun z word low',
    0x706D: 'sun z word high, bit 7 sign',
    # PlanetPosition
    0x706E: 'planet x fraction',
    0x706F: 'planet x word low',
    0x7070: 'planet x word high, bit 7 sign',
    0x7071: 'planet y fraction',
    0x7072: 'planet y word low',
    0x7073: 'planet y word high, bit 7 sign',
    0x7074: 'planet z fraction',
    0x7075: 'planet z word low',
    0x7076: 'planet z word high, bit 7 sign',
    # ReadFlightControls
    0x707F: 'interrupt-maintained roll input',
    0x7083: 'sign-magnitude roll rate',
    0x7086: 'bit 7: roll direction',
    0x708A: 'positive: indicator 21 + value',
    0x708E: 'roll magnitude',
    0x7091: 'negative: indicator 21 - magnitude',
    0x7094: 'RL marker position',
    0x7097: 'HL = high byte of PitchControl',
    0x709A: 'sign-magnitude pitch rate',
    0x70A1: 'positive: 21 + value',
    0x70A8: 'negative: 21 - magnitude',
    0x70AB: 'DC marker position',
    0x70AE: 'HL = high byte of SpeedControl',
    0x70B1: 'speed 0..31',
    0x70B4: 'SpeedGauge = 5*speed + 5',
    # CheckDocking
    0x70BE: 'any hyperspace key press since the last arrival: no docking',
    0x70C3: 'station slot contact (L_EB0C)',
    0x70C7: 'no contact: docking-computer key',
    0x70CA: 'contact consumed',
    # CheckDockingComputerKey
    0x70CF: 'key bit 7: docking computer',
    0x70D3: 'Z if not pressed',
    0x70D5: 'key bit consumed',
    0x70DB: 'C not pressed',
    0x70DC: 'station must be in range',
    0x70E1: 'docking computers fitted',
    0x70E6: 'not when docked',
    0x70EB: 'not during a jump countdown or tunnel',
    0x70F0: 'station behaviour byte',
    0x70F3: 'station hostile: refuse',
    0x70F6: 'remember the automatic docking',
    # DockWithStation
    0x70FC: 'front view',
    0x70FF: 'cockpit back if a page is shown',
    # StartDockingSequence
    0x7105: 'in flight: docking tunnel',
    # MakeSunRelativeToStation
    0x710C: 'IX = station position (slot 0)',
    0x7110: 'x',
    0x7113: 'y; z by falling through',
    # L_7116
    0x7119: 'restore the halved difference',
    0x711A: 'carry = sign of the halved value',
    0x711C: 'negative: set the sign again',
    0x7124: 'next coordinate, 3 bytes on',
    # HandleChartCursorKeys
    0x713E: 'charts: screens 7 and 8',
    0x7140: 'below 7: no chart',
    0x7143: '9 or more: no chart',
    0x7144: 'jump countdown or tunnel: no cursor',
    0x714C: 'bits 0..3: left, right, down, up',
    0x7152: 'bits 4..6 of KeyFlagsChart',
    0x7155: 'no chart key',
    0x7156: 'handler = 9 + lowest set bit',
    0x715E: 'chart handlers 9..15',
    0x7161: 'keys consumed',
    # Startup
    0x716B: 'font, 91 glyphs',
    0x7176: 'initial colours to the mutable copy',
    0x7185: 'restart stack for EndGameWithMessage',
    0x7189: 'controls neutral, speed input 12',
    0x718C: 'first screen: frame and cockpit',
    # RunTitleScreen
    0x718F: 'event 9, C=7: ID 9 (Cobra Mk III)',
    0x7194: 'station byte +$1D',
    0x7197: 'cleared by L_D812; tested by CheckPirateGameOver',
    0x7199: 'attributes of the top two thirds',
    0x719C: 'attribute rows 0..7 = $07',
    0x719F: 'attribute rows 8..15 = $07',
    # L_71A2
    0x71AE: '$FF: no key',
    0x71B1: '$FF + 1 = 0: still no key',
    0x71B4: "'Y' (code + 1 = $5A)",
    0x71B6: 'other key: start prompt',
    0x71B8: 'save the cockpit before the menu',
    0x71BB: "'Y': tape access menu",
    # L_71BE
    0x71BF: 'front view',
    # L_71C8
    0x71CC: 'wait until the key is released',
    0x71D6: '1..5 -> 11..15; 6..8 stay',
    0x71DC: 'C to the high nibble',
    0x71E0: 'event 9: ship ID C+2',
    # L_71E5
    0x71F1: 'B=$FF, C=Kempston port $1F',
    0x71F4: "keys '5' (bit 1) and '6' (bit 3)",
    0x71F7: 'next frame: keys rescanned',
    0x71FA: 'bit 5 set: no Kempston interface',
    0x71FE: 'Kempston bit 1: joystick left',
    0x7200: 'method 1: Kempston',
    0x7204: "method 2: Cursor, '5' = left",
    0x720A: "method 3: Sinclair, '6' = left",
    0x720F: 'SPACE starts with the keyboard',
    0x7214: 'not SPACE: keep waiting',
    0x7216: 'B = 0: keyboard',
    # L_7219
    0x721C: 'B = method 1..3',
    # StartNewGame
    0x7223: 'bits 0-1: control method',
    0x722E: 'docked',
    0x7231: 'expanding sun disarmed',
    0x7237: 'cloak off',
    0x723D: 'save the cockpit before the page',
    0x7240: 'docked: status page',
    0x7243: 'controls neutral, speed input 12',
    # DrawTitleLoadPrompt
    0x724B: 'row 14, column 1',
    0x724E: 'message 6: "LOAD NEW COMMANDER (Y/N)?"',
    # DrawTitleStartPrompt
    0x7255: 'row 14, column 4',
    0x7258: 'message 7: "PRESS SPACE, COMMANDER"',
    # L_725A
    0x7260: 'print into the view buffer ($C000)',
    0x7265: 'renderer back to the screen',
    # PrintTitleBanner
    0x7267: 'row 1, column 5',
    0x726D: 'token $1D: "---- E L I T E ----"',
    0x7272: 'print into the view buffer ($C000)',
    # L_7277
    0x727A: 'printing back to the screen ($4000)',
    # FillAttributePageWhite
    0x727D: '256 bytes',
    0x727F: 'white ink, black paper',
    # MainLoop
    0x7287: 'set from docking until launch end',
    0x728D: 'roll/pitch/speed from the interrupt inputs',
    0x7290: 'view keys 1..4 and page keys',
    0x7293: 'carry: quit to the title',
    0x7298: 'game abandoned from the freeze menu',
    0x72A2: 'H and G: hyperspace requests',
    0x72A9: 'nonzero: in flight',
    0x72AB: 'docked: chart keys',
    0x72B1: 'SYMBOL SHIFT: access menu',
    0x72B5: 'access menu; on Z the docked game continues with whatever record it left',
    0x72B8: 'commander loaded: start prompt',
    0x72BB: 'otherwise redraw the status page',
    # L_72C0
    0x72C4: 'witchspace: no sun, planet or station',
    0x72C6: 'dock on contact or key C',
    0x72C9: 'J: in-system jump',
    0x72CC: "bodies follow the ship's motion",
    0x72CF: 'station slot off/on by distance',
    # L_72D2
    0x72D5: 'cockpit views are 0..3',
    0x72D9: 'objects move, nothing is shown',
    0x72E3: 'docked in this frame: skip',
    0x72E5: 'yellow condition with ships near',
    0x72E8: 'energy, shields and damage',
    0x72EB: 'expanding sun also grows here',
    0x72EE: 'message line on the page',
    0x72F1: '8 frames per pass',
    0x72F4: 'chart keys',
    # L_72FD
    0x72FD: 'cockpit back after a page',
    0x7307: 'no sun or planet in witchspace',
    0x730A: 'stardust',
    0x730D: 'view name and messages',
    0x7316: 'hyperspace arrival tunnel',
    0x7319: 'flagged discs straight on screen',
    0x731C: 'show the view',
    0x731F: 'scanner contacts',
    0x7322: 'redraw changed gauges',
    0x7325: 'cloak key',
    0x7328: 'indicators, missiles, pod, bomb',
    # L_732B
    0x732B: 'altitude, temperature, compass',
    0x7332: 'PlayerDeadFlag clear: next frame',
    # RunGameOverSequence
    0x7336: 'ship stops',
    0x7339: 'lines OR-plotted again',
    0x733D: 'controls locked',
    0x7340: 'normal view colours',
    0x7345: 'remove scanner contacts',
    0x7348: 'canister and two alloy plates',
    0x734B: 'explosion noise',
    0x7354: '30 frames',
    0x7357: 'one frame of the drifting wreck',
    0x7363: 'print into the view buffer',
    0x7369: 'row 7, column 10',
    0x7375: 'renderer back to the screen',
    0x737D: 'blank view',
    0x7383: 'free slots 1..7',
    0x7386: 'wait 50 frames',
    0x738C: 'controls unlocked',
    0x738F: 'alive again',
    0x7392: 'jump latch cleared',
    # BlitViewBitmap
    0x739E: 'top third, lines 0, 2, 4, 6',
    0x73A7: 'middle third, lines 0, 2, 4, 6',
    0x73B0: 'top third, lines 1, 3, 5, 7',
    0x73B9: 'middle third, lines 1, 3, 5, 7',
    # BlitAlternateLines
    0x73BD: '8 character rows',
    0x73C0: 'LDI count in C; B stays the row count',
    0x73C2: '4 lines per row (every second)',
    0x73C5: '32 LDIs: one pixel line',
    0x7406: 'two pixel lines down',
    0x7409: 'buffer address = screen address + $8000',
    0x7412: 'next character row: +32',
    # RestoreCockpitIfFullScreen
    0x741F: 'L_BC9E draws $FF here; views leave $00',
    0x7422: 'clear the latched key bytes',
    # ClearScreenAndDrawCockpit
    0x7428: 'column 0 -> column 31',
    0x742B: '23 row steps',
    0x742D: 'black on black',
    0x7439: 'column 31 of row 23',
    0x743E: 'tape image or saved copy',
    0x7449: 'mutable cockpit colours',
    # CockpitRestored
    0x7451: 'mission flag',
    0x745C: 'save the clean scanner area',
    # ClearViewBuffer
    0x7464: 'stack fills the buffer downwards',
    0x7467: 'row interior: zero words',
    0x746A: 'pattern $00FF: right end of a line',
    0x746D: 'pattern $FF00',
    0x7471: 'pattern $FFFF',
    0x7474: 'row 127, bytes 30..31',
    0x7475: 'bottom row first: DE, 14 x BC, IX = 32 bytes',
    0x7477: 'bytes 2..29 = $FF',
    0x747B: 'bytes 0..1 = $00,$FF',
    0x747D: 'pattern $00/$01: right side pixel',
    0x747F: 'pattern $8000: left side pixel',
    0x7483: '126 middle rows',
    0x7485: 'one middle row, right end first',
    0x749D: 'top row ($C000): frame line',
    0x74A1: 'row 0, built like row 127',
    0x74AA: "back to the caller's stack",
    # ProjectionX
    0x74B4: 'x fraction',
    0x74B5: 'x word low',
    0x74B6: 'x word high, bit 7 sign (cleared in place when x is the depth)',
    0x74B7: 'y fraction',
    0x74B8: 'y word low',
    0x74B9: 'y word high, bit 7 sign',
    0x74BA: 'z fraction',
    0x74BB: 'z word low',
    0x74BC: 'z word high, bit 7 sign (cleared in place when z is the depth)',
    # DrawSunAndPlanet
    0x74BF: 'OR-plot lines unless the sun is large',
    0x74C2: 'project the sun',
    0x74C8: '9 bytes: x, y, z',
    0x74D0: 'keep A over UpdateExpandingSun',
    0x74D6: 'sun not in view',
    0x74D8: 'sun: filled disc',
    0x74DE: 'radius 40 or more',
    0x74E4: 'XOR-plot lines over the sun',
    # L_74E7
    0x74E7: 'project the planet',
    0x74F6: 'planet not in view',
    0x74F7: 'planet: outline circle',
    # UpdateExpandingSun
    0x74FA: 'expanding sun armed?',
    0x7503: 'already expanding',
    0x7505: 'start from the projected radius',
    0x750B: 'CabinTemperature += 1',
    0x750C: 'radius += 2; 256 or more ends the game',
    0x750E: 'exactly 256: dead',
    0x7510: 'below 256: store',
    0x7512: 'the sun engulfs the ship',
    0x7517: 'radius 0',
    0x751B: 'grown radius for the next call',
    # ProjectBodyPosition
    0x7520: "B' = flags, C' = 3: call counter",
    0x7524: 'view 0: front',
    0x752E: 'z negative: behind',
    0x7535: 'depth made positive in place',
    0x7538: 'DE = depth word (z)',
    0x753C: 'HL = horizontal word (x)',
    0x753F: 'B = depth fraction',
    0x7543: 'C = horizontal fraction',
    0x754A: 'x negative: left of centre',
    0x754D: 'bit 0: right of centre',
    # L_7550
    0x7550: 'magnitude',
    0x7557: 'horizontal offset',
    0x755E: 'HL = vertical word (y)',
    0x756C: 'y negative: below centre',
    0x756F: 'bit 1: above centre',
    0x7579: 'vertical offset',
    0x757F: 'side and range bits',
    0x7582: 'depth 65536 or more?',
    0x7588: 'radius = $A000/depth',
    0x758B: 'DE = depth low word and fraction',
    0x7591: 'above $A000: divide',
    0x7593: 'very close: radius 255',
    0x75A1: 'depth word above $A000: too far',
    0x75AA: 'B:C = depth word',
    0x75AF: 'A:E = $00A0',
    0x75B2: 'normalise B:C, shift A:E alike',
    0x75BD: 'B = top 8 bits of the depth word',
    0x75C0: 'radius = (A*256+E)/B',
    0x75C6: 'depth word below 256',
    0x75CC: 'radius = $A000/depth word',
    0x75D0: 'store radius, A = 1',
    # L_75D3
    0x75D4: 'not the rear view',
    0x75D6: 'view 1: rear, z must be negative',
    0x75E0: 'depth = |z|',
    0x75F5: 'x positive: left in the rear view',
    0x75FB: 'x negative: right of centre',
    # L_7601
    0x7602: 'not the left view',
    0x7605: 'view 2: left, x must be negative',
    0x760F: 'depth = |x|',
    0x7612: 'DE = depth word (x)',
    0x7616: 'HL = horizontal word (z)',
    0x7624: 'z negative: left of centre',
    0x7627: 'z positive: right of centre',
    # L_762A
    0x7631: 'horizontal offset',
    0x7638: 'HL = vertical word (y)',
    0x7646: 'y negative: below centre',
    0x7649: 'bit 1: above centre',
    0x7653: 'vertical offset',
    0x7659: 'side and range bits',
    0x7665: 'DE = depth low word and fraction',
    0x766D: 'very close: radius 255',
    0x767B: 'depth word above $A000: too far',
    0x76A6: 'radius = $A000/depth word',
    # L_76AD
    0x76AD: 'view 3: right, x must be positive',
    0x76B5: 'DE = depth word (x)',
    0x76B9: 'HL = horizontal word (z)',
    0x76C7: 'z positive: left in the right view',
    0x76CA: 'z negative: right of centre',
    0x76CD: 'offsets and radius as the left view',
    # L_76D6
    0x76D6: 'H:L = coordinate low byte and fraction',
    0x76D8: 'D:E = depth low byte and fraction',
    0x76DA: 'skip the first shift loop',
    # ProjectCoordinate
    0x76DC: 'keep the coordinate word',
    0x76DE: "count this call in C'",
    0x76E1: 'coordinate word - depth word',
    0x76E3: 'smaller: offset below 256',
    0x76E6: 'equal words: compare fractions',
    0x76EB: 'coordinate word below 256?',
    0x76EE: 'shift both left (24 bits)',
    0x76F4: "coordinate's top bit out",
    0x7700: 'then 16 bits',
    0x770C: 'then the high bytes',
    0x7718: 'not reached for a nonzero value',
    0x771B: 'coordinate fraction - depth fraction',
    0x771D: 'not greater: offset below 256',
    0x7724: 'first call: horizontal below 256',
    0x772D: 'second call: vertical below 256',
    0x772F: 'undo the extra count',
    0x7732: 'up to 23 shifts of both values',
    0x773F: "depth's top bit out",
    0x7745: 'depth 0 or 1/256: D = shifted depth',
    # L_7746
    0x774D: "coordinate's top bit back in",
    0x7753: 'depth normalised too',
    0x7757: 'coordinate >= 2 * depth?',
    0x7759: 'yes: offset 512 or more',
    0x775D: "depth's top bit (see L_7746 NOTE)",
    0x7760: 'coordinate - depth',
    0x7764: 'drop HL and the return address',
    # ProjectionNotVisible
    0x7768: "coordinate's top bit was 1",
    0x776D: "coordinate's shift carry",
    0x7770: "coordinate's top bit was 0",
    0x7772: "depth's top bit back in",
    0x7775: 'offset = 256*A/B',
    # DivideFractionAEB
    0x7779: 'sentinel: stop after 8 bits',
    0x777E: 'dividend overflow: subtract',
    0x7783: 'quotient bit 0',
    0x7788: 'quotient bit 1',
    # UpdateStationDormancy
    0x77A1: 'IX = station slot 0',
    0x77A5: 'inactive: keep moving it',
    0x77A7: 'station energy',
    0x77AB: 'active: nothing to do',
    0x77AC: 'energy 0: inactive ($FF)',
    0x77B0: 'move it with the ship',
    0x77B3: 'x, y, z high bytes, sign masked',
    0x77B8: 'still far: stay inactive',
    0x77C5: 'byte +$26 bit 7',
    0x77CB: 'station active again',
    0x77CE: 'station energy $F0',
    # ToggleCloak
    0x77D8: 'act on every second call',
    0x77D9: 'key latch',
    0x77DE: 'not this call',
    0x77DF: 'next test two calls later',
    0x77E4: 'wait for the next key scan',
    0x77E7: 'Y no longer held',
    0x77E8: 'commander bit 6: cloak owned',
    0x77F1: '1 -> 0: switch off',
    0x77F2: 'off: normal colours',
    0x77F4: 'needs EnergyBank3 >= $28',
    0x77F9: 'too little energy: left nonzero',
    0x77FC: 'cloak on',
    0x7800: 'station no longer hostile',
    0x7803: 'shared alert cleared',
    0x7806: 'blue paper, white ink',
    0x780A: 'white ink on black',
    # L_780F
    0x7813: 'red view colours',
    # ArmExpandingSun
    0x7823: 'no mission flag: nothing',
    0x7826: 'arm UpdateExpandingSun',
    0x7829: 'red view, return',
    # CheckMissionStateOnDocking
    0x782E: 'state 1?',
    0x7831: 'state 2?',
    0x7832: 'offer the mission (Y/N)',
    0x7835: 'state 5?',
    0x7837: 'reward',
    0x783A: 'state 4?',
    0x783B: 'message 212: " THARGON"',
    0x783D: 'boarded by Thargons',
    0x783F: 'other states: nothing',
    # CheckPirateGameOver
    0x7845: 'still set: no boarding',
    0x7846: 'message 13: " PIRATE"',
    # EndGameWithMessage
    0x784C: 'front view',
    0x7852: 'discard all callers',
    0x7856: 'title, then a new game',
    # DrawGauges
    0x7859: 'screen address per gauge',
    0x785D: '11 bars',
    0x7860: 'value; its drawn copy is before it',
    0x7866: 'unchanged: skip',
    0x7868: 'remember the drawn value',
    0x7869: 'bar length = value/4 pixels',
    0x7874: 'next screen address',
    0x7876: 'next value (HL was decremented)',
    0x787E: 'indicator mode',
    0x7884: '2 indicators',
    0x789E: 'bar mode again',
    # GaugeScreenAddresses
    0x78A4: 'FS bar, row 17 column 3',
    0x78A6: 'AS bar, row 18 column 3',
    0x78A8: 'FU bar, row 19 column 3',
    0x78AA: 'CT bar, row 20 column 3',
    0x78AC: 'LT bar, row 21 column 3',
    0x78AE: 'AL bar, row 22 column 3',
    0x78B0: 'SP bar, row 17 column 24',
    0x78B2: 'energy bank 1, row 20 column 24',
    0x78B4: 'energy bank 2, row 21 column 24',
    0x78B6: 'energy bank 3, row 22 column 24',
    0x78B8: 'energy bank 4, row 23 column 24',
    0x78BA: 'RL indicator, row 18 column 24',
    0x78BC: 'DC indicator, row 19 column 24',
    0x78BE: 'row 23 column 3 (missile icon row); never read',
    # DrawIndicatorGauge
    0x78C2: 'GaugeFillByte = $00',
    0x78C5: 'GaugeFillByteFull = $00',
    0x78CA: 'GaugeEndMask = $03',
    # DrawBarGauge
    0x78D2: 'GaugeEndMask = $FF',
    0x78D5: 'GaugeFillByte = $FF',
    0x78D8: 'GaugeFillByteFull = $FF',
    # L_78DB
    0x78DB: 'HL = screen address',
    0x78E1: 'five pixel lines',
    0x78E6: 'zero: empty gauge',
    0x78E9: 'D = length',
    0x78EA: 'pixels in the end byte',
    0x78EC: 'patched: $FF bars, $03 indicators',
    # GaugeEndMask
    0x78F0: 'multiple of 8: end byte = mask',
    0x78F6: 'indicator: marker byte',
    0x78F9: 'bar: n leading pixels',
    0x78FE: 'C = end byte',
    0x7900: 'round up to whole bytes',
    0x790A: 'B = bytes used (1..5)',
    0x790E: 'D = 5 - bytes used',
    0x790F: 'end byte is the fifth',
    0x7912: 'only the first byte used',
    0x7914: 'E = full bytes before the end byte',
    0x7916: 'patched: $FF bars, $00 indicators',
    # GaugeFillByte
    0x791C: 'end byte',
    0x7920: 'bytes after the end byte',
    0x7924: 'are cleared',
    0x7929: 'right border pixel',
    0x7931: 'next pixel line',
    0x7938: 'patched: $FF bars, $00 indicators',
    # GaugeFillByteFull
    0x793E: 'border pixel in the end byte',
    0x7948: 'next pixel line',
    # L_794C
    0x794E: 'end byte in byte 1',
    0x7952: 'bytes 2..4 clear',
    0x7959: 'byte 5: border pixel',
    0x795D: 'next pixel line',
    # L_7961
    0x7963: 'bytes 1..4 clear',
    0x796D: 'byte 5: border pixel',
    0x7971: 'next pixel line',
    # L_7975
    0x7975: 'r = 1: bit 7 only',
    0x797A: 'r = 2: $C0',
    0x797F: 'r > 2: shift into place',
    # StoreGaugeEndByte
    0x798B: 'bars: done',
    0x798D: 'marker $80/$81: pixel before it',
    0x7994: 'previous byte, bit 0',
    # StepTunnelAnimation
    0x79A0: 'no tunnel running',
    # PlayHyperspaceArrival
    0x79A3: 'set by FinishHyperspaceArrival',
    0x79A8: 'reset inputs',
    0x79AB: 'clear all ship slots',
    0x79B9: 'station removed (energy 0)',
    0x79BD: 'event 1: Thargoid group',
    0x79C0: 'blank view',
    0x79C6: '66 frames',
    0x79CB: 'hyperspace noise',
    0x79CE: 'TunnelRingTablePointer = hyperspace rings',
    0x79D4: '16 rings',
    0x79D9: 'TunnelFrameLimit = 1',
    0x79DE: 'TunnelExitOffset -> FinishHyperspaceTunnel',
    # L_79E3
    0x79E3: 'first part inside this call?',
    0x79E9: 'TunnelRingsDoneOffset -> CountTunnelFrame',
    0x79F0: 'TunnelRingsDoneOffset -> L_7A2B',
    0x79F5: 'ring centre: both offsets positive, < 256',
    0x79FD: 'both centre offsets 0',
    0x7A03: 'rings to draw this frame',
    # L_7A06
    0x7A06: 'patched: ring distance table',
    # L_7A09
    0x7A0A: 'ring moves closer',
    0x7A0E: 'radius = 256/distance',
    0x7A14: 'draw rings of radius 4 or more',
    0x7A18: 'ring radius',
    0x7A1C: 'centred outline ring',
    0x7A24: 'patched displacement',
    # L_7A2B
    0x7A2B: 'show the frame',
    0x7A32: 'patched: TunnelFrameLimit',
    # TunnelFrameLimit
    0x7A37: 'patched displacement: TunnelExitOffset',
    # TunnelExitOffset
    0x7A3F: 'next frame',
    # FinishHyperspaceTunnel
    0x7A4F: 'tunnel over',
    0x7A55: '16 distances',
    0x7A5C: 'restore: +66',
    0x7A62: 'blank view',
    # FinishLaunchTunnelLoop
    0x7A6C: 'one frame per call from now',
    0x7A6F: 'seed the stardust, return',
    # FinishDockingTunnelLoop
    0x7A72: 'one frame per call from now',
    # L_7A76
    0x7A77: 'station tunnel over',
    0x7A7A: '8 distances',
    0x7A81: 'restore: +64',
    # SeedLaunchDust
    0x7A88: 'patch L_A347 operands: masks $83',
    0x7A90: 'RET instead of JP L_A193',
    0x7A95: 'stardust speed for the rest',
    0x7A9D: 'stardust table, 5 bytes per particle',
    0x7AA0: '16 particles',
    0x7AA3: 'one particle near the centre',
    0x7AA9: 'restore the original operands',
    0x7AB3: 'restore JP L_A193',
    # DivideFractionABToC
    0x7AB9: 'sentinel: stop after 8 bits',
    # L_7ACD
    0x7AD1: 'white on black',
    0x7AD3: 'mission flag set: colours kept',
    0x7AD7: 'expansion restarts at the new sun',
    0x7ADA: 'arrival noise',
    # StartStationTunnel
    0x7AFC: 'witchspace: no station',
    0x7AFD: 'TunnelRingTablePointer = station rings',
    0x7B03: '8 rings',
    0x7B08: 'TunnelFrameLimit = $30',
    0x7B0D: '$40 frames in total',
    0x7B12: 'L_A80A = L_A80B = 1',
    0x7B1C: 'docked: launch',
    # DockIntoStation
    0x7B1E: 'TunnelExitOffset -> FinishDockingTunnelLoop',
    0x7B23: 'docking speed',
    0x7B2F: 'ECM countdown stopped',
    0x7B33: 'ControlsLockedFlag = 1',
    0x7B39: 'player ECM inactive (bit 7)',
    0x7B3E: 'first 17 frames in one call',
    0x7B41: '47 more frames',
    0x7B47: 'one frame',
    0x7B50: 'docking noise',
    0x7B54: 'docked',
    0x7B57: 'save the cockpit before the page',
    0x7B5A: 'controls neutral, speed input 12',
    0x7B5D: 'mission state',
    0x7B60: 'boarded by pirates?',
    0x7B63: 'screen 7: status (L_D0B9)',
    # LaunchFromStation
    0x7B68: 'FlightCondition: green',
    0x7B6D: 'launch noise',
    0x7B71: 'no pending station contact',
    0x7B74: 'front view',
    0x7B77: 'station active',
    0x7B7A: 'cloak off',
    0x7B7D: 'TunnelExitOffset -> FinishLaunchTunnelLoop',
    0x7B85: 'shields, energy, gauge values',
    0x7B90: 'planet x, y and z fraction = 0',
    0x7B93: 'planet z = $0180',
    0x7B9B: 'sun z sign flipped',
    0x7BA5: 'station position and orientation = 0',
    0x7BAC: 'station z fraction $F0',
    0x7BB1: 'z sign: behind the ship',
    0x7BB6: '$7F: unit orientation',
    0x7BC0: 'station energy',
    0x7BC5: 'free slots 1..7',
    0x7BC8: 'show the reset gauges',
    0x7BCE: 'first 17 frames, then SeedLaunchDust',
    0x7BD1: '36 frames',
    0x7BD7: 'stardust at speed 7',
    0x7BE3: '11 frames with sun and planet',
    0x7BE9: 'sun and planet move',
    0x7BF2: 'and are drawn',
    0x7BFC: 'controls unlocked',
}

DATA = {
    0x7003: (0x7004, 'bytes', 1),
    0x7004: (0x7022, 'zeros', 30),
    0x7022: (0x7023, 'zeros', 1),
    0x7023: (0x7041, 'zeros', 30),
    0x7041: (0x7045, 'bytes', 1),
    0x7045: (0x705F, 'bytes', 1),
    0x705F: (0x7063, 'bytes', 2),
    0x7063: (0x7065, 'words', 1),
    0x7065: (0x7077, 'bytes', 1),
    0x7077: (0x707F, 'bytes', 1),
    0x7286: (0x7287, 'bytes', 1),
    0x74B0: (0x74B4, 'words', 1),
    0x74B4: (0x74BE, 'bytes', 1),
    0x77D4: (0x77D5, 'bytes', 1),
    0x78A3: (0x78A4, 'bytes', 1),
    0x78A4: (0x78C0, 'words', 1),
    0x7ADD: (0x7AE0, 'bytes', 1),
    0x7AE0: (0x7AF0, 'bytes', 8),
    0x7AF0: (0x7AF8, 'bytes', 8),
}

SEEDS = {
    0x7A71: 'target of the JR C at $7A37 after DockIntoStation patches displacement $38; '
            'runtime write to L_A80B from $7A72',
    0x780F: 'unreferenced fragment ending exactly at the verified instruction L_7813',
    0x7818: 'unreferenced fragment: JR NZ to verified L_7806, RET, then ArmExpandingSun',
    0x7169: 'complete unreferenced routine EI, RET between two RET-terminated routines; '
            'simulated by tools/check_routines.py dormant/unused-interrupt-routines',
}

CONSTANTS = {
    0x71F1: 'BC = $FF1F: B=$FF and Kempston joystick port $1F for IN A,(C), not an address',
    0x746D: 'pattern word $FF00 pushed into the view buffer (frame line ends), not an address',
    0x747F: 'pattern word $8000 pushed into the view buffer (left side pixel), not an address',
    0x749D: 'pattern word $FF00 pushed into the view buffer (frame line ends), not an address',
    0x7588: 'projection scale: radius = $A000/depth, not an address',
    0x7597: 'projection scale: radius = $A000/depth, not an address',
    0x7662: 'projection scale: radius = $A000/depth, not an address',
    0x7671: 'projection scale: radius = $A000/depth, not an address',
}

OPERANDS = {
    0x7464: 'ViewBitmapBuffer+$1000',            # LD SP,$D000: end of the view buffer
    0x73AD: 'ViewBitmapBuffer+$100',             # LD HL,$C100: odd pixel lines, top third
    0x73B6: 'ViewBitmapBufferSecondHalf+$100',   # LD HL,$C900: odd pixel lines, middle third
    # Patched JR displacements: target - (displacement byte + 1).
    0x79DE: 'FinishHyperspaceTunnel-(TunnelExitOffset+1)',
    0x7B1E: 'FinishDockingTunnelLoop-(TunnelExitOffset+1)',
    0x7B7D: 'FinishLaunchTunnelLoop-(TunnelExitOffset+1)',
    0x79E9: 'CountTunnelFrame-(TunnelRingsDoneOffset+1)',
    0x79F0: 'L_7A2B-(TunnelRingsDoneOffset+1)',
}

# z80asm cannot evaluate the defc operand labels in assertions; use the
# instruction labels (JR at L_7A37 / L_7A24, two bytes long) instead.
ASSERTS = {
    'r1-tunnel-exit-hyperspace': ('FinishHyperspaceTunnel-(L_7A37+2) < 128',
                                  'patched JR C displacement must stay in range'),
    'r1-tunnel-exit-docking': ('FinishDockingTunnelLoop-(L_7A37+2) < 128',
                               'patched JR C displacement must stay in range'),
    'r1-tunnel-exit-launch': ('FinishLaunchTunnelLoop-(L_7A37+2) < 128',
                              'patched JR C displacement must stay in range'),
    'r1-tunnel-rings-done': ('CountTunnelFrame-(L_7A24+2) < 128',
                             'patched JR Z displacement must stay in range'),
    'r1-gauge-table': ('ForwardShield-GaugeDisplayTable = 1',
                       'DrawGauges compares each value with the byte before it'),
}
