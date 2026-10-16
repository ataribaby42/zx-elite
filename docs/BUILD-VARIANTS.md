# Build variants and verification

## Commands

See [Optional-feature addressing audit](ADDRESSING-AUDIT.md) for the symbolic
reference rules, retrospective corrections and relocation regression.

`build.bat` is the simple double-click entry point. Edit its explicit options:

```bat
make.bat ship=krait laser=original font=128 verify=yes
```

`make.bat` only forwards its arguments to `tools/build.py` and contains no
option settings. Preserve the owner's simplified BAT files and their selected
options, including REM examples. Run the BAT files from the project directory;
run `make.bat` directly for command-line options. The Python helper's defaults
remain Krait, original laser, 128K-compatible font, all fixes disabled and
strict verification.

Build the byte-identical Krait reconstruction independently of `build.bat` settings:

```bat
make.bat
verify.bat
```

Optional Adder replacement in slot 17:

```bat
make.bat ship=adder verify=no
verify.bat verify=no
```

Equivalent Python syntax:

```text
python tools/build.py --ship adder --verify no
python tools/build.py --verify-only --verify no
```

`ship` accepts `krait` (default) or `adder`; `laser` accepts `original` (default)
or `single`. `font` accepts `128` (default), `48`, `128fix` or `128fix_ecm_s`. `scannerpixelfix`,
`stationrandomlaunchfix`, `stationslotfix`, `fuelfix`, `hyperspacedockingfix`, `aicouragefix`,
`scannerblipfix`, `stardustfix`, `missiletargetfix`, `textfullstopfix`, `iffunit` and `randomizedspawn`
accept `no` (default) or `yes`.
`verify` accepts `yes`
(default) or `no`. A build does not change the saved BAT settings or remember
its command-line overrides. No modification silently weakens verification: select
`verify=no` explicitly. Modified builds with `verify=yes` correctly fail the
original-byte comparison and leave no release TAP.

Single centred laser, alone or combined with Adder:

```bat
make.bat laser=single verify=no
make.bat ship=adder laser=single verify=no
verify.bat verify=no
```

The equivalent Python option is `--laser single`.

The output is always **`release/elite-128k.tap`**, containing only the chosen
variant. It is still a ZX Spectrum 48K program. No banked RAM, extra ship slot
or save-format change is introduced.

## Scanner pixel fix

```bat
make.bat scannerpixelfix=yes verify=no
make.bat ship=adder laser=single font=48 scannerpixelfix=yes verify=no
python tools/check_scanner_pixel_fix.py
```

The equivalent Python option is `--scannerpixelfix yes`. With the default
`scannerpixelfix=no`, the original bytes and behaviour are preserved.

The ECM indicator overlaps bit 0 of screen byte `$50C9`, at pixel (79,176).
`src/scanner-pixel-fix.asm` preserves that bit on the very first write to the
top-right E tile: `(glyph & $FE) | (old_screen & 1)`. The other seven bits
are overwritten normally. An absent pixel remains absent; this does not
force a permanent dot or briefly clear and subsequently restore the pixel.

The replacement occupies exactly the original **166 bytes** at
`$A660..$A705`. It draws the ten existing circle/E/S tiles from the selected
runtime font and compacts the adjacent four-slot missile display loop.
Both existing callers of the missile routine use assembler labels. Nothing
after this region moves. No additional image bytes, persistent RAM, spare
padding, graphics-buffer storage or font modifications are required.
The shared text renderer remains unchanged. The missile loop retains the
original display and return mode for each valid missile count (0 through 4).

The regression compares all screen bytes with the original routines for
1,536 combinations per font, watches every overlapping write, checks all
five missile counts and executes a ROM-loaded first launch in 48K mode with
ECM off/on/off. Only the ECM timer in emulated RAM is temporarily forced for
the active-state test. Reports and diagnostic frames are disposable files in
`build/scanner-pixel-check/`. Run the test after building each font.

Source reconstruction also correctly represents the unchanged bytes at
`$D137..$D13A` as an inline character `$11` followed by `CALL L_D1A6`.
`L_BA99` consumes the character before returning to that call. Linear
decoding had incorrectly represented them as `LD DE,L_A6CD` / `POP DE`,
which would falsely relocate an unrelated status-screen instruction when
the indicator tables moved. This source correction emits identical bytes.

## Station random launch fix

```bat
make.bat stationrandomlaunchfix=yes verify=no
make.bat ship=adder laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no
python tools/check_station_random_launch_fix.py
```

The equivalent Python option is `--stationrandomlaunchfix yes`. The default
`no` retains the original bytes, including the station's Python-only behaviour.
The replacement is `src/station-random-launch-fix.asm`, conditionally included
in `src/game.asm`. It occupies exactly **38 bytes at $F44A..$F46F**, requires
no additional RAM, and leaves the shared allocator at `$F470` unchanged.
Assembler assertions protect both boundaries. No other code or data moves.

The calm-station gate at `L_F846` permits only RNG results 0 and 1. That
preceding RNG call uses carry=1, leaving an odd low seed byte. The original
selector then calls the RNG with carry=0; doubling 0 or 1 and adding the odd
byte always produces an odd result. Consequently its `AND 1 / ADD 9` always
selects Python (ID 10), never Cobra trader (ID 9).

The repair retains that second RNG call so later random choices keep the
same seed progression. Its new low seed byte contains twice the preceding
result; loading it from `L_ED35`, rotating right and masking bit 0 recovers
the earlier result's low bit. This selects Cobra for 0 and Python for 1.

The four bytes needed for `LD A,(L_ED35)` and `RRCA` come from shortening the
rock hermit's final fighter selector to `AND 1 / ADD $10`. It still uses
the same RNG call, chooses the same Sidewinder/Krait ID for every seed and
keeps the same subsequent RNG state. With `ship=adder`, ID 17 resolves to
Adder as usual. The Viper branch bypasses the changed selection instructions;
Thargon and special-mode Thargoid launch types remain unchanged. Ordinary
in-flight trader encounters use a separate, unchanged path via `L_F6E2`.

The regression runs actual Z80 instructions in a ZX Spectrum 48K memory map
with the supplied 48K ROM. For both ship options it checks all 65,536 seed
states through each calm/hostile station gate, the four-AI launch limit, the
special-mode Thargoid branch, and the rock hermit/Thargoid AI launch gates.
Calm stations produce 256 Cobra and 256 Python selections instead of 512
Pythons, with the same 65,024 rejected states. These counts enumerate seed
states, not a guarantee of equal observed traffic in every play session.
Police and hermit results are compared seed by seed with the original,
including RNG call counts and final seed values. An additional 240 paired
full-allocation cases cover actual blueprints, inherited hostility, parent
restoration and full-slot failure; non-trader resulting game state matches
the baseline. Reports are in `build/station-random-launch-check/`.

## Station slot fix

```bat
make.bat stationslotfix=yes verify=no
python tools/check_station_slot_fix.py
python tools/check_station_slot_fix.py --emulator
```

The equivalent Python option is `--stationslotfix yes`. The default `no`
keeps the original bytes and behaviour.

In the original game the docking slot of the Coriolis station often does not
face the planet when the station appears after a hyperspace jump. There are
two causes; see [findings](FINDINGS.md#found-in-the-station-slot-investigation).
While the station is dormant and far away, `MoveObject` turns its position
with the player's roll and pitch but not its axes. In galaxies 2, 4, 6 and 7
the arrival code also reverses the slot for a negative planet x (464
systems). The roll-reversal drift is not a cause.

The fix acts when `UpdateStationDormancy` switches the station on: every
coordinate below $10000, flag cleared, energy $F0. A dormant station has no
energy, so it is neither drawn nor shown on the scanner, and its stale
orientation is never visible. At the switch-on `StationSlotAlign` does the
following:

1. It forms planet minus station per axis with the existing
   `HalveCoordinateDifference`, in units of 512.
2. It doubles the three words until one reaches $2000, then scales the
   vector to unit length with `NormaliseVector`. The result is the new nose,
   which is the slot axis.
3. It sets the roof to the unit axis least aligned with the nose (y, else x,
   else z), makes it perpendicular with `OrthogonaliseYVector` and rebuilds
   the side axis with `BuildRotationMatrix`.
4. It clears `StationDormantFlag`, the instruction that the call replaces.

From then on the station is updated exactly as in the original, including its
own roll about the nose and the per-frame orthogonalisation and
renormalisation. Nothing changes while the station stays active, for example
after a launch, when the original already points the slot at the planet.

The only in-place change is the three-byte flag store at `$77CB`, which
becomes `CALL StationSlotAlign`. The 114 bytes of new code occupy three areas
listed as [persistently free](#persistently-free-bytes-in-the-image):

| Area | Original contents | New contents |
|---|---|---|
| `$E88B..$E8CE` (68 B) | `UnusedMultiplyWordHigh` | `StationSlotAlign`, 66 B |
| `$AC56..$AC76` (33 B) | Dormant galaxy-step copy (`L_AC56`, `L_AC6D`) | `StationSlotRoof`, 31 B |
| `$FCED..$FCFF` (19 B) | Zeros before the IM 2 vector table | `StationSlotFinish`, 17 B |

`src/station-slot-fix.asm` defines the three parts as macros, and
`src/game.asm` expands each one in place of the original bytes. Each part is
padded to its original length. Assembler assertions protect both boundaries
of all four areas, using the original limits in `src/options.asm`. No other
byte changes, 118 bytes in total, and no RAM is added. `StationSlotAlign`
preserves IY, as the original routine does, and returns with IX unchanged.
The source generator re-creates the four conditional blocks.

The planet direction is resolved in units of 512 and the axes in steps of
1/127. In the check, the slot error at the switch-on is at most 0.79 degrees
for station-to-planet distances from $10000; the arrival places the station
$18000 from the planet. The shortest tested distance, $6000, gives at most
1.90 degrees.

The fix leaves the arrival code and the pitch rounding of
`RotateVectorRollPitch` unchanged. After the station has appeared, slow
pitching can still turn the slot a few degrees off the planet, as it does for
every object in the original.

`tools/check_station_slot_fix.py` runs the assembled image with the supplied
48K ROM in SkoolKit's simulator. It compares it with a baseline whose four
areas are restored from the reference tape, and checks the following:

- only the four areas differ;
- 600 far, blocked (`+$26` bit 7) and already active cases leave RAM, IX and
  IY exactly as the original does;
- 3,036 switch-on geometries: 36 axis and near-axis cases and 3,000 random
  ones, at distances from $6000 to $60000, with random previous frames. Each
  case checks the slot error, unit lengths, a perpendicular roof and side
  axis, a right-handed frame and the preserved IY. Eight further active
  frames keep the slot within 1.64 degrees and the roof perpendicular;
- all 2,048 hyperspace arrivals, each followed by 12 turned dormant updates
  and a move next to the station. The slot error is at most 0.90 degrees. In
  a sample of 512 the original keeps every reversed slot and is more than
  10 degrees off in 186.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM with
`tools/emulator_check.py`. It runs Lave to Diso with one second of pitch, and
the galactic jump to Inoran followed by a jump to LEMAED. A test-only poke then
moves sun, planet and station together next to the player, so that the real
main loop switches the station on. In the default Krait build the slot error
changed from 59.5 to 0.52 degrees at Diso, and from 180.0 to 0.02 degrees at
LEMAED. The combined Adder, single-laser, `font=48` build with all three fixes
gave 64.3 to 0.84 and 180.0 to 0.00 degrees. Build the option with the default
tapfile for this mode. Reports are in `build/station-slot-fix-check/`.

## Fuel fix

```bat
make.bat fuelfix=yes verify=no
python tools/check_fuel_fix.py
python tools/check_fuel_fix.py --emulator
```

The equivalent Python option is `--fuelfix yes`. The default `no` keeps the
original bytes and behaviour.

In the original game the fuel price (`FuelPrice`, entry 0 of
`EquipmentPriceTable`) and the FU bar value (`FuelGauge`) are not part of the
saved commander record, and nothing recomputes them when a record is loaded.
After saving with 3.4 light years, resetting, reloading the game and loading
the commander, the equipment screen offers fuel at 0.0 and the FU bar shows a
full tank. See [findings](FINDINGS.md#found-in-the-fuel-price-investigation).

The fix recomputes both from `FuelLevel` at the moments they are used:

- `EquipShipScreen` calls `FuelPriceUpdate` instead of `BeginTradeScreen`. It
  stores 0 for a full tank, otherwise 2 x economy + (70 - fuel) tenths of a
  credit, and continues in `BeginTradeScreen`. This is the formula of the
  original normal jump. The economy is that of the system the ship is docked
  at, formed as `DeriveSelectedSystemData` does it: s0 high byte AND 7, with
  bit 1 set for governments 0 and 1.
- `LaunchFromStation` calls `FuelGaugeUpdate` instead of
  `PrepareShipForLaunch`. It sets the FU bar value through `StoreFuelLevel`,
  the end of `SetFuelLevel`, which leaves `FuelLevel` unchanged, and falls
  into `PrepareShipForLaunch`.

In the normal case, docked after a jump without scooping, the price is the
one the original shows. The fix also corrects the other stale cases:
- a load without a reset;
- a new commander after the game is over;
- fuel scooped after a jump;
- the galactic jump, which originally stores the old galaxy number + 1 as the
  price.

A full tank always costs 0.0. A record with more than 7.0 light years, which
the game itself never creates, gets a meaningless price; the original shows
whatever price is left over in that case.

The two hooked calls keep their three bytes. The 43 bytes of new code fill
three areas listed as [persistently free](#persistently-free-bytes-in-the-image),
none of them used by another option:

| Area | Original contents | New contents |
|---|---|---|
| `$B31B..$B32A` (16 B) | Dormant attribute-fill routine | `FuelPriceUpdate`, 16 B |
| `$A89B..$A8A9` (15 B) | Dormant `JP` vectors and a fragment | `FuelEconomy`, 15 B |
| `$9A3A..$9A45` (12 B) | Unused bytes after `DustPlotList` | `FuelPriceStore` and `FuelGaugeUpdate`, 12 B, falling into `PrepareShipForLaunch` |

`src/fuel-fix.asm` defines the three parts as macros, and `src/game.asm`
expands each one in place of the original bytes. Assembler assertions protect
both boundaries of all five areas, using the original limits in
`src/options.asm`. Further assertions check the fall-through into
`PrepareShipForLaunch` and that `FuelLevel`, `CurrentGovernment` and the
current system's s0 high byte share one page. No other byte changes, 44 bytes
in total, and no RAM is added.

`tools/check_fuel_fix.py` runs the assembled image with the supplied 48K ROM
in SkoolKit's simulator. It compares it with a baseline whose five areas are
restored from the reference tape, and checks the following:

- only the five areas differ;
- the price for every fuel level 0..70, government 0..7 and s0 high byte, a
  total of 145,408 cases;
- after a normal jump into each of the 2,048 systems, the same fuel and price
  as the original jump;
- for every fuel byte 0..255, the same RAM after `FuelGaugeUpdate` as after
  `StoreFuelLevel` and the original `PrepareShipForLaunch`. `FuelLevel` is
  kept, so it is not capped at 70.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM. A test-only
poke of `FuelLevel` stands for a loaded commander with 3.4 light years:

- the equipment screen lists fuel at 4.6;
- buying it costs 4.6, fills the tank and lists 0.0;
- after a launch the FU bar value is 76 instead of 160.

The original under the same poke lists 0.0 and keeps 160. Build the option
with the default tapfile for this mode. Reports are in `build/fuel-fix-check/`.

## Hyperspace docking fix

```bat
make.bat hyperspacedockingfix=yes verify=no
python tools/check_hyperspace_docking_fix.py
python tools/check_hyperspace_docking_fix.py --emulator
```

The equivalent Python option is `--hyperspacedockingfix yes`. The default
`no` keeps the original bytes and behaviour.

In the original game `CheckHyperspaceKeys` sets `HyperspaceKeyLatch` as soon
as it consumes an H or G press, before it tests anything else. While the latch
is set, `CheckDocking` returns at once, so neither station contact nor the
docking computer docks the ship. Only a hyperspace arrival or the game-over
restart clears it. A press that the game refuses therefore disables docking
until the next jump. Refused presses include:

- H or G while docked;
- G alone;
- G and H without a galactic hyperdrive;
- H with the current system selected;
- H with a target out of range.

See [findings](FINDINGS.md#found-in-the-second-annotation-pass).

The fix changes the operand of the first instruction of `CheckDocking`, so
that it reads `JumpTunnelMode` instead of the latch. Only an accepted jump sets
`JumpTunnelMode`, at the same moment as the latch: 1 for a normal jump and 2
for a galactic one. The end of the arrival tunnel (`FinishHyperspaceTunnel`)
clears it. An accepted jump therefore still prevents docking from its
countdown onwards, while a refused press no longer does.

The window now lasts until the end of the arrival tunnel, not until the
arrival itself. In that interval the docking computer is refused anyway,
because `CheckDockingComputerKey` also tests `JumpTunnelMode`. The station is
far away and dormant, so no new contact can occur, and witchspace never calls
`CheckDocking`. The only difference concerns a contact flag left over from
touching the station during a countdown. The original docks with it at the
arrival, the fix after the arrival tunnel. The latch is still written but no
longer read.

Only the two operand bytes at `$70BF..$70C0` change. Assembler assertions
protect the boundaries of the instruction (`HyperspaceDockingCheckStart` and
`HyperspaceDockingCheckLimit` in `src/options.asm`). The source generator
emits the alternative instruction itself, so no extra source file is needed.
No memory is used.

`tools/check_hyperspace_docking_fix.py` runs the assembled image with the
supplied 48K ROM in SkoolKit's simulator. It compares it with a baseline that
has the original instruction restored from the reference tape, and checks
the following:

- only the operand differs;
- `CheckDocking` for each latch value, `JumpTunnelMode` value and docking
  path (contact or docking computer);
- each of six refused presses followed by station contact. The fixed image
  docks and the original does not. A press during a running countdown still
  blocks docking in both;
- an accepted jump blocks docking from the acceptance until its arrival
  tunnel ends.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM. Docking
computers are fitted by a test-only poke, and the runs check the following:

- H pressed while docked, a launch and the key C dock the ship; the
  original stays in flight;
- the same without H docks in both;
- C pressed during an accepted countdown to Diso does not dock, and the jump
  arrives at Diso.

Build the option with the default tapfile for this mode. Reports are in
`build/hyperspace-docking-fix-check/`.

## AI courage fix

```bat
make.bat aicouragefix=yes verify=no
python tools/check_ai_courage_fix.py
python tools/check_ai_courage_fix.py --emulator
```

The equivalent Python option is `--aicouragefix yes`. The default `no` keeps
the original bytes and behaviour.

`InstanceAiState` (`+$25`) of an AI ship holds an ECM bit (bit 0), a courage
counter in bits 1..6 and a fleeing bit (bit 7). The courage starts at 126
($7E). Each damaging laser hit (`ApplyPlayerLaserHit`) is meant to lower it
by 14, down to a floor of 6 that keeps the ECM bit, and to leave bit 7
alone. In open space, without an active station, a hostile ship whose courage
is below 8 flees: it sets bit 7, turns away and accelerates. While bit 7 is
set, `ApplySteeringVector` returns before `TryFireAiLaser`, so the ship never
fires.

The original subtracts 14 from the whole byte. The floor therefore applies
only while bit 7 is clear: a fleeing ship's byte is at least $80 and never
borrows. A courage below 14 then wraps to 114..127. At its next AI step
the ship turns back and charges the player at full acceleration, still
without firing, and about nine hits later it flees again. A Python under
pulse-laser fire flees at hit 9 and turns back at hits 10, 19, 28 and so on.

The abandon-ship test also compares a random byte with the whole of `+$25`.
A fleeing ship at the floor ($86) passes it about 48% of the time; after the
wrap ($F2) it passes only about 5% of the time. The effect needs a ship that
survives at least ten hits in open space:

| Laser | Damage per hit | Ships that can show the effect |
|---|---:|---|
| pulse, beam | 15 | Python, Thargoid, rock hermit, Fer-de-Lance; Cobra Mk III and Asp Mk II only marginally |
| military | 23 | Python and Thargoid |
| mining | 50 | none |

The fix replaces the 19 bytes `$EC6A..$EC7C` in place
(`src/ai-courage-fix.asm`). It shifts the byte left, so that the fleeing bit
drops out, subtracts 2 x 14, applies the floor 2 x 6 with the ECM bit and
shifts back with the old bit 7. For bytes below $80, which covers every ship
that is not fleeing and every missile target code, A, B and `+$25` end exactly
as in the original. A frightened ship stays at courage 6 or 7 and keeps
fleeing. Assembler assertions protect both boundaries
(`AiCourageHitStart` and `AiCourageHitLimit` in `src/options.asm`). Nine bytes
change and no memory is used.

`tools/check_ai_courage_fix.py` runs the assembled image with the supplied
48K ROM in SkoolKit's simulator. It compares it with a baseline that has the
original 19 bytes restored from the reference tape, and checks the following:

- only those bytes differ;
- every `+$25` value with damage 15, 23 and 50, for a surviving and a
  destroyed target, 1,536 cases. Below $80 RAM and registers match the
  original; from $80 up only `+$25` differs;
- 27 pulse hits on a hostile Python, with and without ECM, each followed by
  the real `UpdateShipHostilityAndSteering` in open space. Both builds flee
  at hit 9. The fixed ship then stays at courage 6 or 7, steers away with
  acceleration 2 and never fires. The original turns back at hits 10 and 19.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM. After a
launch, test-only pokes put a hostile Python, created by
`InitialiseShipFromBlueprint`, straight ahead. They also make the station
dormant far away, so that the AI decides by courage. The player then holds
fire for 17 seconds. The fixed build ends with the Python fleeing at `$86`
(courage 6) with full acceleration. The original build in the same run ends
at `$E4`: fleeing, but with courage 100 after the wrap, and its course departs
from the fixed one as it turns back. Build the option with the default
tapfile for this mode. Reports are in `build/ai-courage-fix-check/`.

## Scanner contact fix

```bat
make.bat scannerblipfix=yes verify=no
python tools/check_scanner_blip_fix.py
python tools/check_scanner_blip_fix.py --emulator
```

The equivalent Python option is `--scannerblipfix yes`. The default `no`
keeps the original bytes and behaviour.

`DrawScannerContacts` draws each ship or the station as a contact on the
scanner. A contact has a vertical stick in pixel column 123 + dx when x is
positive, or 124 - dx when it is negative, where dx = `ScannerDotX` AND $7F.
The stick starts at base row 165, which `ScannerDotZ` moves up or down, and
ends in a three-pixel dash. The original has two quirks:

- From dx = 4 on, the code first steps ceil((dx - 4) / 8) screen bytes with
  a `DJNZ` loop. For dx = 4 that count is 0, so the loop runs 256 times and
  the whole contact lands one pixel row lower (x > 0) or higher (x < 0). A
  contact therefore hops by one row while it crosses that column. This is
  plainly visible.
- An upward stick that leaves character row 0 of the bottom third would
  enter the 3D view. `L_8DCC` stops it there, without its dash, only when
  `L = $0F`, character column 15. In the other columns it reaches screen row
  127, which is the bottom line of the view frame (all pixels set in the 48K
  flight runs). The extra stick pixel and dash are therefore mostly hidden.

The fix replaces three parts of `DrawScannerContacts` in place
(`src/scanner-blip-fix.asm`):

| Area | Original | Fixed |
|---|---|---|
| `$8CE0..$8CF2` (19 B) | dx - 4; dx < 4 stays in the centre byte; byte count with a conditional `INC B` | dx - 5; dx < 5 stays in the centre byte; byte count (dx - 5) / 8 + 1, the same as before for dx >= 5; two `NOP`s pad the area |
| `$8D0B..$8D0C` (2 B) | `ADD A,8`: pixel dx + 4 | `ADD A,9` on dx - 5: the same pixel dx + 4 |
| `$8DCC..$8DDD` (18 B) | stop the upward stick only at `L = $0F` | stop it whenever the previous character row would be outside the bottom third; three unreachable padding bytes |

`ScannerDotInCentreByte` (`$8D0B`) and `NextScannerContact` (`$8D7E`) are
the verified names the fix refers to. Assembler assertions protect the
boundaries of all three parts (`ScannerBlip...Start` and `...Limit` in
`src/options.asm`). The changes touch 32 bytes and use no memory.

`tools/check_scanner_blip_fix.py` runs `DrawScannerContacts` with the
supplied 48K ROM in SkoolKit's simulator, for the assembled image and for a
baseline whose three parts are restored from the reference tape. A model of
the contact geometry covers the column, base row, stick, dash, both stick
stops and the final clearing of rows 128..134. The model checks the
following for 8,442 object positions (7,614 contacts), which include every dx
and the tallest sticks:

- the original matches the model exactly with its two quirks: 630 contacts at
  dx = 4, and 68 upward sticks that reach row 127 and only that row;
- the fixed image matches it exactly without them, and never draws above row
  128;
- the values `DrawScannerContacts` stores (`ScannerDotX`, `ScannerStickHeight`,
  `ScannerDotZ`) and whether a contact is drawn are the same in both images.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM. After a
launch, a test-only poke places a cargo canister at dx = 4, and the real main
loop draws it with the replaced code. Build the option with the default
tapfile for this mode. Reports are in `build/scanner-blip-fix-check/`.

## Stardust fix

```bat
make.bat stardustfix=yes verify=no
python tools/check_stardust_fix.py
python tools/check_stardust_fix.py --emulator
```

The equivalent Python option is `--stardustfix yes`. The default `no` keeps
the original bytes and behaviour.

`ClearViewBuffer` draws the view frame into the view buffer every frame: rows
0 and 127 and the side pixels in columns 8 and 247. `GetDustPixelAddress`
maps a stardust particle to column $80 +/- X and row $3F -/+ Y, and
`XorPlotDustList` XORs the pixel into the buffer. A particle on the frame
therefore erases a frame pixel. The original reaches the frame, or the area
outside it, in two ways:

- It selects the lower half of the buffer from the Y sign alone. A particle
  with Y = 0 and the sign bit set (negative zero) lands on row 127, the
  bottom frame line, instead of row 63. `SeedLaunchDust` creates the launch
  particles with |X|, |Y| <= 3 and a random sign, so about one in eight starts
  at negative zero, about two per launch. With Y = 0 the depth motion keeps
  the row, and the particle slides along the bottom line until it leaves the
  view. Respawns and the pitch step also produce negative zero in flight.
- `StoreAndPlotDust` plots every particle with |Y| < 63 but does not limit X.
  The depth motion keeps |X| <= 119, so X = +119 lands on column 247, the
  right frame pixel. The pitch step keeps |X| <= 127, which also reaches
  column 8 and the columns outside the frame (1..7 and 248..255).

A 48K snapshot reported by the owner (not kept in the repository) shows
both: a particle at X = +49, Y = -0 has erased the bottom frame line in column
177. Running it on in the simulator for 300 frames with its roll and pitch
drew particles on the side frame lines or outside the frame in 24 frames.

The fix replaces `GetDustPixelAddress` (`$A2EF..$A333`, 69 bytes) in place
with the macro in `src/stardust-fix.asm`:

- It computes row - 64 as -1 - Y (signed Y), which has the same line and
  character-row bits as the row. The lower half is selected only for a
  negative Y that is not zero. Negative zero is therefore drawn on row 63,
  like positive zero.
- It returns the pixel mask 0 for a column outside 9..246
  (`DustViewFirstColumn`..`DustViewLastColumn`), so `XorPlotDustList` leaves
  the frame and the area outside it unchanged.

Every other particle gets the same address and mask as before. The particle
records, their motion and the random numbers do not change. The routine
returns row - 64 in H instead of the row; `StoreAndPlotDust`, its only caller,
uses only DE and C. The new code is 68 bytes, followed by one unreachable
padding byte. Assembler assertions protect both boundaries
(`StardustPixelStart` and `StardustPixelLimit` in `src/options.asm`).

`tools/check_stardust_fix.py` compares the assembled image with a baseline
whose routine is restored from the reference tape, using the supplied 48K ROM
in SkoolKit's simulator:

- `ClearViewBuffer` draws exactly the frame described above, so the interior
  is columns 9..246;
- `GetDustPixelAddress` for every X 0..127 and Y 0..62 (the range that
  `StoreAndPlotDust` plots) with all four sign combinations, 32,256 inputs: the
  original matches a pixel model with negative zero on row 127, and the fixed
  routine matches it with negative zero on row 63 and mask 0 outside the
  interior. DE, C, A, B and L are otherwise the original ones;
- 96 launches (`SeedLaunchDust` at the launch speed) and 80 random flight
  sequences in all four views with random speed, roll and pitch, 1,792 dust
  passes in total: both images get the same records, random state and
  routine inputs, every plotted pixel matches the model, and each pass XORed
  into a freshly cleared view leaves the frame and the area outside it
  unchanged in the fixed image. The original damages them in 969 of the
  1,152 launch passes and 251 of the 640 flight passes.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM and launches.
A test-only poke then sets all 16 particles to negative zero. A second run
also restores the original routine with a test-only poke. The original's
final screen has holes in the bottom frame line, the fixed one none, while
particles at negative zero remain. Build the option with the default tapfile
for this mode. Reports are in `build/stardust-fix-check/`.

## Missile target fix

```bat
make.bat missiletargetfix=yes verify=no
python tools/check_missile_target_fix.py
python tools/check_missile_target_fix.py --emulator
```

The equivalent Python option is `--missiletargetfix yes`. The default `no`
keeps the original bytes and behaviour.

A missile keeps its target in `+$25` as the counter of the target's slot (8
for slot 0 down to 1 for slot 7). `UpdateMissileGuidance` steers towards that
slot without checking that it is still occupied. Whenever an object is
removed (destroyed, scooped, collided or out of range), `ReleaseTargetLocks`
gets H = `ObjectLoopCounter`, the counter of the removed slot, and IX = the
removed object. It ends the player's own lock (`MissileState` 2, TARGET LOST)
correctly. It then scans slots 1..7 to explode every live missile aimed at H,
but tests the missile flag (`+$26` bit 0) with `BIT 0,(IX+$26)`, on the
removed object instead of the scanned slot (IY). As a result:

- a missile whose target is removed is not exploded. It keeps steering
  towards the target's slot: the last coordinates of the removed object, or
  whatever is created in that slot next;
- when a missile is removed, every live object whose `+$25` equals the
  missile's counter explodes. For a ship `+$25` is the AI courage byte.

The fix changes the index prefix of that one instruction at `$EB82` from
`$DD` to `$FD`, giving `BIT 0,(IY+$26)`. Its boundaries are asserted
(`MissileTargetCheckStart` and `MissileTargetCheckLimit` in
`src/options.asm`). Missiles aimed at a removed object now explode, as after
an ECM, and removing a missile no longer affects other objects. The player's
lock is handled as before.

`tools/check_missile_target_fix.py` runs `ReleaseTargetLocks` of the
assembled image and of a baseline with the original byte, using the supplied
48K ROM in SkoolKit's simulator. For every counter, both kinds of removed
object and 4,064 cases of random slot contents, each image matches its
model, the player's lock is released identically, and only the explosion
flags differ.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM and launches.
A test-only poke then adds:

- a player missile in slot 7, aimed at a cargo canister in slot 1;
- an enemy missile in slot 2;
- a canister in slot 3 whose `+$25` equals the counter of slot 2.

The objects in slots 1 and 2 lie beyond the removal distance, so the first
object update removes them. The poke also clears the station's ECM bit;
otherwise the station may fire its ECM at the player's missile and destroy
every missile. A second run also restores the original byte with a test-only
poke. In the original the player's missile flies on after its target is
removed. In the recorded run a police Viper then launched from the station
into the freed slot 1, and the missile turned towards it. The canister in
slot 3 explodes when the enemy missile is removed. In the fixed image the
player's missile explodes and the canister survives. Build the option with
the default tapfile for this mode. Reports are in
`build/missile-target-fix-check/`.

## Text full stop fix

```bat
make.bat textfullstopfix=yes verify=no
python tools/check_text_full_stop_fix.py
python tools/check_text_full_stop_fix.py --emulator
```

The equivalent Python option is `--textfullstopfix yes`. The default `no`
keeps the original bytes and behaviour.

Justified text (message control 14, used for the planet descriptions on the
DATA ON screen) is laid out by `BufferJustifiedCharacter` in lines of 30
characters. A full stop prints the line at once. The original tests for the
full stop before it counts the character. A full stop that arrives as the
31st character is therefore stored after the 30 printed characters
(`WrapOverflowChar`) and lost, while any other character in that position
is wrapped to the next line with its word. In the game this removes the
final full stop of 72 of the 2,048 planet descriptions, those whose last
line is exactly 30 characters wide. SOCELAGE (galaxy 1) ends with "noted for
Its Exotic Goat Meat".

The fix has two parts (`src/text-full-stop-fix.asm`):

| Area | Original | Fixed |
|---|---|---|
| `$BCFC..$BD1A` (31 B, start of `BufferJustifiedCharacter`) | full stop test, then the count | count first; up to the 30th character a full stop prints the line at once, as before; as the 31st it goes to `JustifyWrapFullStop` |
| `$BDF5..$BDFF` (11 B, zero padding before the square tables) | zeros | `JustifyWrapFullStop` wraps the word with the original code from `JustifyWrapWord` (`$BD1B`) and then prints the next line at once; `JustifyCharacterInLine` returns for other characters |

The last word then moves to a new line with its full stop, and the line
before it is justified like any other. In mid-text the next sentence starts
on a new line, as after every full stop. Characters other than a full stop
are handled as before. The routine returns with the character in A and the
line-length address in HL instead of the length and the write pointer; all
descriptions and the random texts below print identically otherwise.
Assertions protect both parts (`TextFullStopBuffer...` and
`TextFullStopHook...` in `src/options.asm`), and the square tables keep
their page-aligned address. The longest fixed description has five lines,
screen rows 19 to 23 of the DATA ON screen; the original already has two
descriptions of six lines.

`tools/check_text_full_stop_fix.py` compares the assembled image with a
baseline whose two parts are restored from the reference tape, using the
supplied 48K ROM in SkoolKit's simulator. It takes about a minute:

- all 2,048 planet descriptions: both images receive the same characters,
  every fixed description ends with its full stop, the original loses it in
  exactly 72, and all others are printed identically. In the 72, the last
  word moves to a new line with its full stop, and the line before it is
  justified to 30 characters;
- a full stop as the 31st character in mid-text prints its word on a line of
  its own, and the next sentence starts a new line;
- 600 random texts lose no character in the fixed image and are otherwise
  printed as by the original.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM, finds
SOCELAGE with the galactic chart search and opens its DATA ON screen with
real key presses. A second run restores the original bytes with a test-only
poke. The original ends the description with "Goat Meat" and no full stop;
the fixed image prints "Meat." on the next line. Build the option with the
default tapfile for this mode. Reports are in
`build/text-full-stop-fix-check/`.

## I.F.F. unit

```bat
make.bat iffunit=yes verify=no
python tools/check_iff_unit.py
python tools/check_iff_unit.py --emulator
```

The equivalent Python option is `--iffunit yes`. The default `no` keeps the
original bytes and behaviour.

This option is a modification, not a fix. It removes the energy bomb and puts
an I.F.F. (identification friend or foe) unit in its place
(`src/iff-unit.asm`). With the unit fitted, threats blink on the scanner while
every other contact stays lit.

### Equipment item

Item 9 keeps the energy bomb's price (900.0 Cr), its tech level and its
commander byte (`+$36`, `EnergyBombFitted`, used as `IffUnitFitted`). Buying
it, "... PRESENT", the status screen and the " DESTROYED" damage message all
print the item's token 113. Its text becomes I.F.F. UNIT: the characters
"I.F.F. " followed by the UNIT token that ENERGY UNIT already uses. The screens
print it in title case as "I.F.F. Unit". The saved commander format does not
change. A commander saved with an energy bomb loads with the unit, and one
saved with the unit loads into the original with an energy bomb.

The new text is three bytes longer than ENERGY BOMB. The dictionary ends with
three empty tokens, 146..148 (`$9E71..$9E73`). `PrintToken` reaches only tokens
0..145 (codes `$A0..$FF`, `$60..$7F`, and `$0E..$1F` as tokens `$80..$91`), and
nothing else reads the dictionary, so no code ever reads these three bytes. The
option drops them: tokens 114..145 move up by three bytes and
`TextTokenDictionaryEnd` keeps its address. Tokens are found by counting
terminators, never by address.

### Removed energy bomb

- `UseEnergyBomb` (`$9260..$927F`) and its call in `UpdateCockpitSystems`
  (`$A568`);
- the bomb test in the `UpdateObjects` slot loop (`$DAC1..$DAD7`) and the
  clearing of `EnergyBombPending` after the loop (`$DBC8`). Nothing reads or
  writes `EnergyBombPending` (`$DA10`) any more;
- the W entry of `KeyActionTable` (`$FF72..$FF73`), now `$00,$00` like Z and
  V. W still types the letter (commander name, chart search); in flight it does
  nothing.

`FlashViewAttributes` stays, because the unreferenced vector at `L_91CC` jumps
to it. The vector at `L_91C9` jumped to `UseEnergyBomb` and now jumps to
`IffBlinkTick`. Sound request bit 0 has no setter any more.

### Threats

`DrawScannerContacts` calls `IffScannerContactEnergy` instead of loading the
energy of each slot (`$8C3D`). With the unit fitted, in the dark half of the
blink it returns 0 for a threat, and the slot is skipped like an empty one.
Otherwise it returns the energy, and the contact is drawn exactly as in the
original. A threat is:

- a missile (`+$26` bit 0) whose target code (`+$25`) is 0, the player. The
  player's own missiles always carry a locked target: F fires only in missile
  state 2, which needs a nonzero target, and a laser hit changes a missile's
  code to 6 or more, never 0;
- any other object with the hostile bit (`+$21` bit 2), unless it is
  scoopable (`+$26` bit 1: cargo canisters, escape capsules, debris, inert
  Thargons). The station counts while it is hostile.

The game sets the hostile bit (see [BOUNTY-HUNTERS.md](BOUNTY-HUNTERS.md)):

- from the blueprint: the pirate Python and Cobra Mk III records, Asp Mk II,
  Sidewinder, Krait or Adder, Thargoid and Thargon;
- for the Viper and the Fer-de-Lance once the legal score reaches 40;
- for any ship hit by the player's laser;
- for the station in mission-3 state 4;
- for every object while the player's missile flies, or after a hostile
  trader or Viper raises the shared alert.

Only the station's bit is ever cleared again. After a missile launch or a
shared alert, traders and the station therefore blink too; the scoopable test
keeps cargo from blinking.

### Blink

`IffBlinkClock`, one byte inside the replaced `UseEnergyBomb` bytes, counts
cockpit-view frames: `UpdateCockpitSystems` calls `IffBlinkTick` where it
called `UseEnergyBomb`. Threats are hidden while bit 1
(`IffBlinkHiddenPhase`) is set: two frames lit, two frames dark. The frame
rate depends on what is drawn. The emulator check measured 5.6 cockpit frames
per second with a pirate in view, about 1.4 blinks per second. Just after
launch, with nothing near, the game runs 9 frames per second.

### Memory layout

| Area | Original | With `iffunit=yes` |
|---|---|---|
| `$8C3D..$8C3F` | `LD A,(IX+$22)` | `CALL IffScannerContactEnergy` |
| `$91C9..$91CB` | `JP UseEnergyBomb` | `JP IffBlinkTick` |
| `$9260..$927F` (32 B) | `UseEnergyBomb` | `IffScannerContactEnergy`, `IffBlinkClock`, 2 unused bytes |
| `$9D84..$9E73` (240 B) | token 113 ENERGY BOMB, tokens 114..145, empty tokens 146..148 | token 113 I.F.F. UNIT, tokens 114..145 three bytes later |
| `$A568..$A56A` | `CALL UseEnergyBomb` | `CALL IffBlinkTick` |
| `$DAC1..$DAD7` (23 B) | the energy bomb test | `JR UpdateSharedHostility`, `IffShipContact`, `IffBlinkTick` |
| `$DBC8..$DBD4` (13 B) | clear `EnergyBombPending`, then the shared alert | the shared alert only, 4 unused bytes |
| `$FF72..$FF73` | W: `KeyFlagsCombat` bit 5 | W: no action bit |

The start and limit constants of every part are in `src/options.asm`
(`IffScannerHook`, `IffBombVector`, `IffScannerCode`, `IffUnitText`,
`IffBlinkHook`, `IffShipCode`, `IffObjectsTail`, `IffBombKey`), and the build
asserts them. No other address changes, and no extra RAM is needed.
`tools/bootstrap_sources.py` regenerates the eight conditional parts,
including the two inside the token dictionary; `UseEnergyBomb` is defined only
without the option.

### Checks

`tools/check_iff_unit.py` compares the assembled image with a baseline whose
eight parts are restored from the reference tape, using the supplied 48K ROM
in SkoolKit's simulator. The baseline must equal the reference image.

- All 306 changed bytes lie inside the eight parts.
- `PrintToken`, run for all 146 dictionary codes, prints every token as the
  original except code `$71`: "ENERGY BOMB" becomes "I.F.F. UNIT".
- `IffScannerContactEnergy` is checked against a model for 92,160 slot states:
  every role byte, hostile and other behaviour bits, five missile targets, six
  clock values and three item values. IX and IY are kept and no memory is
  written.
- `DrawScannerContacts` draws seven objects: a hostile station, a pirate, a
  trader, a missile aimed at the player, a player-style missile with the
  hostile bit, a hostile canister and a Fer-de-Lance, calm or hostile. The
  screen equals the original drawing of all objects. In the dark half with the
  unit fitted, it equals the original drawing of the non-threats only.
- W latches no key bit (`RecordKeyPress`).
- `UpdateCockpitSystems` with W and the item fitted changes only the blink
  clock and the consumed key bit, while the original uses the bomb.
- `UpdateObjects` ignores a nonzero `EnergyBombPending`; its RAM then equals
  the original update without a bomb.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM:

- docked, it buys item 9 ("9 I.F.F. Unit 900.0") and shows I.F.F. Unit on the
  status screen;
- in flight, test-only pokes put a pirate ahead and move the station off the
  scanner, and `ScannerContactsDrawn` is sampled at every frame interrupt. The
  pirate's contact was dark in 125 of 251 samples with 14 changes. Without the
  unit 4 samples were dark (the moment between restoring the scanner
  background and redrawing it), and with a trader instead 0;
- W in flight leaves the pirate and the unit in place; on the reference tape
  the same W uses the energy bomb and destroys the pirate. That run uses the
  option build's addresses, which the layout check proves identical outside
  the parts. It is skipped when another option, such as `ship=adder`, is
  built as well.

Mission situations start from the RAM of a launch run, taken at the start of
`MainLoop`. The baseline gets an unused energy bomb and the option image the
I.F.F. unit, then both receive the same set-up. Each runs up to 300 main loops
in the simulator, without interrupts. After every loop their RAM must be
identical except the scanner columns of the screen, the scanner work bytes, the
replaced parts and the test stack. Results for Krait and Adder:

| Situation | Loops | Loops with a different scanner |
|---|---:|---:|
| Mission 2: the real special encounter, a cloaked Asp and two Sidewinders | 300 | 150 |
| A Thargoid and a Thargon | 300 | 150 |
| Witchspace with three Thargoids and no station | 75 (player killed) | 37 |
| Mission 3, state 4: the hostile station, which launches Thargoids | 245 (player killed) | 122 |
| The player's missile at a trader, which makes every object hostile | 235 (player killed) | 117 |

The cloaked Asp stays hidden in the 3D view exactly as in the original. The
original draws it on the scanner, so with the unit it blinks there.

Build the option with the default tapfile for this mode. Reports and
screenshots of a lit and a dark frame are in `build/iff-unit-check/`.

## Randomized spawn

```bat
make.bat randomizedspawn=yes verify=no
python tools/check_randomized_spawn.py
python tools/check_randomized_spawn.py --emulator
```

The equivalent Python option is `--randomizedspawn yes`. The default `no`
keeps the original bytes and behaviour.

### Original placement

Every object that `InitialiseShipFromBlueprint` creates starts as a copy of
`ShipInstanceTemplate`: x = y = z = +$3200, with the forward axis pointing back
at the player. The loader keeps z = +$3200, 12,800 units ahead, and randomises
the low bytes and signs of x and y. It also draws new high bytes 0..7 for x
and y, but only when bit 2 of the blueprint behaviour (`InstanceBehaviour`,
hostile) is clear:

| At creation | x and y | In the front view |
|---|---|---|
| calm: Cobra and Python traders, Viper, Fer-de-Lance, Rock hermit, Asteroid | random sign, magnitude 0..$07FF | almost straight ahead, within about 9 degrees in x and y |
| hostile: pirate Cobra and Python, Asp Mk II, Thargoid, Sidewinder, Krait | random sign, magnitude $3200..$32FF | about 45 degrees out in x and y, towards one of the four corners |

The Fer-de-Lance starts calm and turns hostile later through its AI (see
[Fer-de-Lance encounters](BOUNTY-HUNTERS.md)), so it also appears ahead.
Station and parent launches, debris, missiles, the title ship and Thargoid
groups overwrite the loader's coordinates; only random space encounters keep
them. The starting point therefore tells the player at once whether a newly
arrived ship is a threat.

### Change

With `yes` a single ship of a random encounter takes either placement with
about even odds, whatever its hostility: the Cobra and Python traders and
pirates, the Viper, the Asp Mk II, the Fer-de-Lance, a lone Thargoid, and the
Python trader or Thargoid that the invasion mission states 1 and 4 force. Its
type, hostility, energy, speed, payload, AI and ECM chance are created as
before. Unchanged are the groups of 2..4 Sidewinders and Kraits, asteroids,
the Rock hermit, the special Asp of mission 2 with its escort, and every other
caller of the loader. The Rock hermit keeps the placement of an asteroid: a
rock towards a corner would give it away.

Five parts replace original bytes in place, asserted with the
`RandomizedSpawn...Start`/`Limit` constants in `src/options.asm`. No free area
and no RAM are used; 59 of the 71 bytes change.

| Part | Original | Replacement |
|---|---|---|
| `$F2FE` (1 B) | `LD B,A` in `InitialiseShipFromBlueprint`; `LD BC` reloads B before any read | `PUSH AF`: keep the caller's A |
| `$F338..$F355` (30 B) | the last fields (`+$20` with bit 6, speed, `+$25`, `+$26`), then `BIT 2,(IX+$21)` and `JR NZ` | the same fields in 19 bytes, then the placement test |
| `$F653..$F654` (2 B) | the special Asp's `JR InitialiseEncounterShip` | `JR InitialiseEncounterShipByHostility` |
| `$F6C8..$F6DA` (19 B) | `InitialiseEncounterShip` | `OR $80`, the request, then the loader call and the same ECM test in two bytes fewer |
| `$F6FB..$F70D` (19 B) | the trader choice and the Rock hermit/Viper choice | the trader choice in two bytes fewer; the Viper takes the request path, the Rock hermit pushes its ID itself and enters after the request |

The loader masks the ID with `AND $3F`, and every other caller passes an ID
below $40, so bit 7 is free for the request. The fields keep their values:
bit 6 of `+$20` is ORed in before the store instead of set afterwards, the
speed is halved with `RRA` while the carry is known clear, and `+$26` is
stored from B, which the template `LDIR` leaves at 0. The test then pops the
caller's A. Without the request it tests the hostility alone, draws nothing
and leaves the carry clear for the next `NextRandomByte`, exactly as the
original. With the request it draws one byte and takes the corner when bit 3
of that byte differs from the hostility. Then the loader continues with the
original draws of the selected placement.

`InitialiseEncounterShip` computes the ECM decision with `ADD A,$CD` and
`RET C` instead of `CP $33` and `RET NC`. A Thargoid ID ($0F, which the
special Asp also pushes to get its ECM) draws no byte and returns with the
carry clear, as after the original `CP $0F`. That carry matters: the special
Asp's continuation passes it to the `NextRandomByte` that sizes its escort.
The ordinary encounter caller clears every register it uses afterwards.

### Randomness

`NextRandomByte` is weak. Each byte depends mostly on the low bits of the two
bytes before it, and the request byte directly follows the bytes that chose
the encounter and the ship type. In a model over all 65,536 states and eight
governments, bit 3 is among the bits least correlated with the type: the
largest deviation from even odds for one type in one government was 0.10. The
generator's carry output, the obvious alternative in the same bytes, gave
0.02 for the Viper and 0.89 for the Thargoid and was rejected. Measured with
the real code over all 65,536 states in every government (74,960 single
ships):

| Ship | Corner share |
|---|---:|
| Asp Mk II | 0.52 |
| Cobra pirate | 0.50 |
| Python pirate | 0.49 |
| Fer-de-Lance | 0.49 |
| Cobra trader | 0.48 |
| Python trader | 0.48 |
| Viper | 0.48 |
| Thargoid | 0.41 |
| All | 0.490 |

For one ship type in one government, counting at least 100 ships, the share
lies between 0.40 (Cobra trader, government 5) and 0.54 (Asp Mk II,
government 4); the check bounds it to 0.30..0.70. The Thargoid is exempt
from that bound; its shape gives it away anyway. The ECM share of these ships
is 0.234, against 0.229 in the original, because their ECM byte is drawn one
or three bytes later.

### Checks

`tools/check_randomized_spawn.py` compares the assembled image with a
baseline whose five parts are restored from the reference tape, using the
supplied 48K ROM in SkoolKit's simulator. Without other options the baseline
must equal the reference image.

- A Python model of `NextRandomByte` matches the simulator in 512 states.
- `InitialiseShipFromBlueprint` without the request, the way every other
  caller uses it: all 19 IDs, 1,024 RNG states each, ID bit 6 clear and set,
  varied entry flags and a garbage-filled slot (38,912 calls). The slot,
  every register, the flags and the RNG state equal the original's.
- With the request (19,456 calls): every byte from z on and every register
  equal the original's, and x, y and the final RNG state equal a model of the
  loader: the request byte, then the original draws of the selected
  placement.
- `SpawnRandomEncounter` for all 65,536 RNG states in each of the eight
  governments, then 4,096 states each for invasion mission states 1 and 4,
  the special Asp encounter and full slots (540,672 runs per image). Both
  images create the same objects in the same slots. No encounter, asteroids,
  groups, the Rock hermit, the special Asp with its escort and full slots
  are identical byte for byte, including the RNG state and its number of
  draws. A single ship differs only in x, y and the ECM bit; it has the
  centre or the corner form, and the option image draws one byte more, plus
  two for the centre form, minus two when the original took the centre.
  Bytes outside the slots and the variables the test sets stay unchanged.
  The corner shares are bounded as above.

`--emulator` loads `release/elite-128k.tap` through the 48K ROM, launches and
jumps to Diso. At 36 seconds the arrival tunnel is over and no station is
present. The RAM of that moment is loaded into the simulator, which searches
for RNG states that make the next encounter a trader towards a corner and a
pirate ahead; the original places both the other way round. Each state is
then poked into a second ROM-load run, with `ObjectUpdateCounter` = 1 so that
the next object update dispatches the encounter. One second later the
predicted ship is in its predicted placement: a Cobra trader at
x = +$3206, y = +$3285, z = +$2FE4 (RNG state $000B) and a pirate Cobra at
x = +$05B3, y = +$047F, z = +$3080 (state $0007), for Krait and Adder. Build
the option with the default tapfile for this mode. Reports are in
`build/randomized-spawn-check/`.

## What verification means

Always checked, including `verify=no`:

- six TAP blocks forming the original three header/data pairs;
- little-endian lengths, XOR checksums, header names/types and load metadata;
- assembled payload lengths of 130, 6,912 and 40,801 bytes;
- game origin `$6048`, entry `$7000` and exclusive image end `$FFA9`;
- source include safety, no external binary inclusion, table/geometry lengths
  and assembler memory-bound assertions.

`verify=yes` additionally reads the immutable reference, checks its known
hash and requires the complete output to match byte for byte. `verify=no`
does not read the reference during a normal build. Its report records
`identity_check: disabled` and `binary_identical: null`, never a false claim
that modified bytes passed identity verification.

Builds delete the previous release before assembling. A failed comparison
does not publish the candidate TAP. Standalone failed verification removes
the success report but preserves the file being inspected.

## Font selection

```bat
make.bat font=48 verify=no
make.bat ship=adder laser=single font=48 verify=no
```

The equivalent Python option is `--font 48`. `font=128` selects the original
`src/data/font.asm`; `font=48` selects the prettier font from the 48K version
in `src/data/font-48.asm`. The latter is
extracted from zero-based data block 5 of `assets/Elite128fixes/PATCH128.TAP`,
whose game payload loads at `$6048`. Both fonts occupy `$C000..$C2D7`: 728
bytes for codes `$20..$7A`, copied to `$5D70..$6047` at startup.

237 bytes differ between the fonts. No byte outside that region differs
between PATCH128 and the original tape. No rendering routine, cockpit bitmap,
loading screen, memory boundary or save format changes with this option.
The additional memory cost is **0 bytes**. All original interior labels and
end/start assertions are retained in both ASM definitions.

`tools/font_variant.py` validates the patch tape's hash, headers, XOR checksums,
load scope and unchanged bytes outside the font for extraction and tests.
Normal builds need neither that helper nor the patch tape. Source regeneration
preserves both font definitions and the conditional include.

The default Krait/original-laser build with `font=48 verify=no` reproduces
`PATCH128.TAP` exactly (SHA-256
`fac185ce4248e1dccc99f93a7cb7d2791e220543c24016a3a77a1dfff4cbec47`).
This is distinct from `verify=yes`, which always compares against the original
128K-compatible release and must reject the modified font.

## Single laser and identified drawing routines

`src/single-laser.asm` implements the **last** version in the owner's
`docs/info/ELIT128P_laser_mod-readme.txt`. The earlier variant that clears DE
and fixes C is not used. The original note and POKE file remain unmodified.

| Label | Original address | Verified purpose |
|---|---|---|
| `DrawLaser` | `$ECD4` | Generate the original random endpoint, then draw the player's laser beams |
| `LaserPatchSite` / `SingleLaser` | `$ECF2` | Optional centred-beam dispatch |
| `LaserOriginalContinuation` | `$ECFE` | Original first-beam continuation, not reached by the single beam |
| `DrawLine` | `$EE10` | Shared clipped line renderer using endpoint magnitudes in HL/DE and quadrant bits in C |

The replacement sets HL to `$003F` (bottom centre), preserves the random DE
endpoint and C's endpoint quadrant bits, sets the start quadrant with `OR $03`,
then jumps to `DrawLine`. There is one line-renderer invocation instead of the
original four. `DrawLine` returns directly to `DrawLaser`'s caller, so no extra
stack entry is left behind. Existing line calls elsewhere are unchanged.

Only the ten bytes at `$ECF2..$ECFB` are replaced. The original CALL operand
bytes at `$ECFC..$ECFD` remain as unreachable data, followed by the untouched
original continuation. Addresses are derived from assembler labels and the
patch boundary is asserted. **No extra code or persistent RAM is required**;
the patch does not create extra space in the ship-model block. It changes no
damage, firing-rate, heat or equipment settings.

`tools/check_laser_variant.py` runs the real laser and line routines in ZX
Spectrum 48K mode with the supplied 48K ROM. For 256 RNG states it compares the
endpoint with the original, checks real line-call counts and stack balance,
and verifies pixels remain in the narrow centre strip with the expected
wiggle. The original mode is checked against the original rendered pixels.
The existing rasterizer may omit an endpoint pixel; the test preserves that
behaviour. Normal ROM load, launch and firing are also exercised with
`tools/emulator_check.py`.

## Adder definition and memory layout

The separate source is **`src/data/adder.asm`**, extracted from
`assets/Elite+48K+fixed+B+-+Adder.tap`. It is assembled directly; no reference
binary is included at build time. Header properties and 18 vertices / 29
edges retain the original Adder behaviour. Its original normals 6, 7 and 8
are identical, including sign and visibility. They share one stored normal,
with all vertex and edge face references remapped. There are therefore 13
stored normals and 299 total bytes instead of 15 normals / 307 bytes.

The original, byte-exact 307-byte record is also retained as
**`src/data/adder-original.asm`**. It preserves all 15 normals and
the original vertex/edge face references. It is not included by `ship=adder`;
the current build still uses `adder.asm`. Both files use the same labels and
are mutually exclusive includes. Selecting the original later will require
eight additional bytes of space. `tools/analyze_ship_blueprints.py
--write-source` and the bootstrap generator reproduce both alternatives.

Krait uses 233 bytes. The extra 66 bytes are recovered without moving game
routines after `$7000`:

| Change enabled only for Adder | Recovered space |
|---|---:|
| Nineteen two-byte blueprint pointers instead of four-byte entries | 38 B |
| Move the first fourteen text-handler pointers into old startup code | 28 B |

The original table's `$C3` prefix and fourth byte are not used by its live
reader at `$F2FB`. The Adder variant retains the pointers, indexes them by
two, and omits the prefix skip. Two original instructions become NOPs, so
the reader and subsequent code retain their addresses. Spawn IDs and header
behaviour flags remain unchanged. All 19 live object-loader paths are tested.

The preinitialised station is a separate path: its blueprint pointer at
`StationBlueprintPointer` in `src/data/initial-runtime-state.asm` is emitted
symbolically as `ShipCoriolisStationBlueprint`. It must follow the same model
relocation even though the station bypasses the generic loader. The build
rejects a mismatch. An earlier raw `$6A9D` pointer caused a dot-sized station
in Adder builds; the corrected current value is `$6A77`, computed by the
assembler without increasing data size. See [Ship blueprints](SHIPS.md#persistent-station-instance).

The original `$716B..$7188` instructions execute once at startup. In the
Adder variant their equivalent code runs at `$C600..$C620`, then jumps back
to the original continuation `$7189`. It copies the font, copies cockpit
attributes, initializes IM2 and saves SP before returning. These operations
do not overwrite `$C600`; drawing and clearing begin only after the jump.
The startup code's initial storage may then be reused by the renderer.

The former startup range holds 28 permanent text-handler pointer bytes and
two zero bytes. The second 32-entry text table remains at `$6FBF`. Restart,
death and return-to-title paths enter `$718F`, not the relocated startup.
The original IM2 vector table, interrupt routine and stack locations are
unchanged. `$5B00..$5D6F` is **not spare RAM**: it is a 624-byte screen-backup
buffer used by `$8E5C..$8E94`.

Verified Adder build landmarks:

| Region | Address / size |
|---|---|
| Blueprint pointer index | `$6180..$61A5`, 38 B |
| Adder header and geometry | `$6D0C..$6E36`, 299 B |
| End of all ship geometry | `$6FBF` exclusive |
| Second text-pointer group plus original trailing zero | `$6FBF..$6FFF`, 65 B |
| Relocated first text-pointer group | `$716B..$7186`, 28 B |
| One-time startup | `$C600..$C620`, 33 B |
| Game image | `$6048..$FFA8`, unchanged 40,801 B |

The ship/table region is full: **0 bytes of additional capacity** before
`$7000`. The two startup padding bytes and the existing 19-byte zero area
at `$FCED..$FCFF` are unchanged available candidates, not a general promise
that larger modifications will fit. Initial zeros in graphics buffers are
not persistent free memory. Bounds remain enforced even with `verify=no`.

`LD BC,$640A` at `$D55E` is a pair of numeric display parameters, not a ship
pointer. Its accidental autogenerated geometry label has been replaced with
the original numeric value so compacting the ship table cannot change it.

See [Free memory in the default build](#free-memory-in-the-default-build)
for every byte that a further modification could reuse.

## Free memory in the default build

The default build has almost no spare memory. Only **216 bytes inside the
game image** are persistently free, spread over 22 small areas; the largest
contiguous block is 68 bytes. Above the stacks there are another **22 bytes**.
About **238 bytes** in total can hold persistent code or data. A larger
modification must first recover space, as the Adder variant does by
compacting the blueprint table, or use the start-up-only area described below.

### 48K memory map at run time

| Range | Use |
|---|---|
| `$4000..$5AFF` | Screen bitmap and attributes |
| `$5B00..$5D6F` | Cockpit attribute buffer and scanner background backup (624 B); the BASIC system area is overwritten |
| `$5D70..$6047` | Runtime copy of the font (`FontRuntime`, 728 B) |
| `$6048..$FFA8` | Game image (40,801 B) |
| `$FFA9..$FFAA` | Unused margin below the interrupt stack |
| `$FFAB..$FFBE` | Interrupt stack (`InterruptStackTop` = `$FFBF`; 20 B measured) |
| `$FFBF..$FFC5` | Unused margin between the two stacks |
| `$FFC6..$FFE9` | Main stack, deepest measured use |
| `$FFEA..$FFFF` | BASIC's stack contents at the `USR` call; never used after start-up (**22 B free**) |

The stack depths are measured, not proved. Untraced paths may be deeper, so
the two margins are kept as safety space rather than counted as free.

### Persistently free bytes in the image

Every area below is free for three independent reasons:

- the annotation analysis classifies it as unused, unreferenced or dormant;
- `docs/generated/reconstruction.json` lists no reference into it from
  outside the area;
- none of the 28 ZX Spectrum 48K scenarios of `tools/trace_xrefs.py`
  executes, reads or writes any of its bytes.

| Range | Bytes | Contents |
|---|---:|---|
| `$E88B..$E8CE` | 68 | `UnusedMultiplyWordHigh`, a complete but uncalled routine |
| `$AC56..$AC76` | 33 | Dormant older copy of the galactic-jump seed rotation |
| `$FCED..$FCFF` | 19 | Zeros before the IM 2 vector table (the POKE notes use them for patches) |
| `$A89B..$A8A9` | 15 | Dormant `JP` vectors and a three-byte fragment |
| `$B31B..$B32A` | 16 | Dormant attribute-fill routine |
| `$9A3A..$9A45` | 12 | Bytes after `DustPlotList` |
| `$BDF5..$BDFF` | 11 | Zero padding before the page-aligned square tables (used by `textfullstopfix=yes`) |
| `$91C9..$91D1` | 9 | Three unreferenced `JP` instructions (`iffunit=yes` retargets the first) |
| `$7818..$781E` | 7 | Unreferenced cloak-colour test |
| `$780F..$7812` | 4 | Unreferenced code that falls into the used `L_7813` |
| `$A897..$A899` | 3 | Dormant `JP` vector (`$A89A` is the live `MissileTarget`) |
| `$FF53..$FF55` | 3 | `UnusedSelectInterruptMode1` (`IM 1`, `RET`), never called |
| `$705F..$7060` | 2 | Bytes after the gauge table |
| `$7169..$716A` | 2 | `UnusedEnableInterrupts` (`EI`, `RET`), never called |
| `$85F0..$85F1` | 2 | Filler before `FilledSpanPattern` |
| `$A6C1..$A6C2` | 2 | Unused indicator tile codes (inside the region that `scannerpixelfix=yes` replaces) |
| `$A895..$A896` | 2 | Bytes after `TextRedirectFlag` |
| `$D2DA..$D2DB` | 2 | Zero padding |
| `$B93F` | 1 | Unreachable `RET` (`text/p6-unreachable-byte`) |
| `$DA0D` | 1 | Unused byte |
| `$DA13` | 1 | Unused byte |
| `$FFA8` | 1 | Last image byte |
| **Total** | **216** | |

Using the `$BDF5..$BDFF` padding requires keeping `SquareLookupTables`
page-aligned. The layout assertions in `src/game.asm` reject a misaligned
table.

### Space that is not free

- **`$C2D8..$C6FF` (1,064 B).** It holds initial zeros, `DormantPortLoader`
  and the reserved `$C600..$C63F` area, but at run time it is part of the
  view bitmap buffer `$C000..$CFFF`. It can only hold code or data used before
  the first drawing operation. The Adder variant uses `$C600..$C620` this way
  for its one-time start-up.
- **Commander record bytes `$A848..$A849` and `$A850..$A851`.** No code reads
  them, but they belong to the 104-byte tape record. Reusing them would change
  saved commander files.
- **The stack margins** listed in the memory map.
- **Bytes only absent from the traces.** About 11,000 image bytes are never
  touched in the recorded scenarios: other object slots, ship models,
  messages and untraced code paths. That is missing coverage, not free memory.

### Effect of the build options

`scannerpixelfix`, `stationrandomlaunchfix`, `laser=single` and every `font`
choice reuse only their own original regions and need no extra memory. With
`ship=adder` the blueprint table and the old start-up code are compacted. The
ship and table region before `$7000` then has no spare capacity, and the
one-time start-up runs in the start-up-only area above. `stationslotfix=yes`
uses three of the free areas listed above: `$E88B..$E8CE`, `$AC56..$AC76` and
`$FCED..$FCFF`, 114 of their 120 bytes. `fuelfix=yes` fills three others
completely: `$B31B..$B32A`, `$A89B..$A8A9` and `$9A3A..$9A45`, 43 bytes. Every
other option leaves the free areas unchanged; `hyperspacedockingfix` changes
two bytes in place, `aicouragefix` nine within its original 19 and
`scannerblipfix` 32 within three parts of the scanner routine and
`stardustfix` 57 within the 69 bytes of the dust pixel routine and
`missiletargetfix` one byte in place. `textfullstopfix=yes` rewrites 31 bytes
in place and fills `$BDF5..$BDFF`. With the station slot, fuel and text full
stop fixes 42 bytes remain free in 15 areas, the largest 9 bytes
(`$91C9..$91D1`). `iffunit=yes` reuses the energy bomb's own bytes and the
three unreachable bytes at the end of the token dictionary, and claims the
first unreferenced `JP` at `$91C9..$91CB`. Its parts keep 6 bytes unused
(`$927E..$927F`, `$DBD1..$DBD4`), and `EnergyBombPending` becomes unused.
With the I.F.F. unit as well, 39 bytes remain free in 15 areas, the largest 7
bytes (`$7818..$781E`). `randomizedspawn=yes` uses no free area: it rewrites
71 bytes of the ship loader and the encounter code in place, in five parts.

### Rules for using free space

Address new code and data through labels, and add `assert` lines for any
fixed position or capacity, as the optional modules do. A modified build needs
`verify=no` and must still pass the structural checks. Re-check a candidate
area with `tools/trace_xrefs.py` and `docs/generated/reconstruction.json`
after any annotation change that reclassifies it.

## Reproduction and tests

Assembler used: `Z80 Macro Assembler 23854-4d530b6eb7-20251002`.

```text
python tools/check_build_options.py
python tools/check_laser_variant.py
python tools/check_ship_variant.py
python tools/check_graphics.py
python tools/run_runtime_scenarios.py docked-baseline docked-market docked-equipment docked-system-data trade-complete buy-large-cargo inflight-screens hyperspace-diso galactic-hyperspace-overlap
```

For the font option, both the default and `font=48` glyph tests pass. ROM-load,
launch and rear-view checks also pass with the 48K font for Krait and Adder:

```text
python tools/emulator_check.py --seconds 20 --key 3:0.5:N --key 5:0.5:SPACE --key 8:0.5:1 --key 14:0.8:2 --name font48-adder-launch --no-screenshots
python tools/run_runtime_scenarios.py docked-baseline docked-market docked-equipment inflight-screens
```

Use `make.bat ship=krait font=48 verify=no` for the Krait check and
`make.bat ship=adder laser=single font=48 verify=no` for the combined check.
The inherited broader gameplay scenarios above remain available; they are
not all required for a font-only data substitution.

The option check (`tools/check_build_options.py`) runs in about 25 seconds
(92 builds). It checks the following:

- The default build reproduces the reference tape.
- Every non-default value alone builds in both verification modes. The strict
  build must fail and leave no release or PASS report. The relaxed build may
  change only the areas its option declares:
  - the laser's ten bytes, compared with the owner's patch note;
  - the font, compared with the bytes of `PATCH128.TAP`;
  - the scanner fix: the instrument region and its two missile-call operands;
  - the station launch fix: its 38-byte selector;
  - the station slot fix: its four areas;
  - the fuel fix: its five areas;
  - the docking fix: its one operand;
  - the AI courage fix: its 19 bytes;
  - the scanner contact fix: its three parts;
  - the stardust fix: its 69 bytes;
  - the missile target fix: its one instruction;
  - the text full stop fix: its two parts;
  - the I.F.F. unit: its eight parts;
  - the randomized spawn: its five parts.
- These areas, together with every byte `ship=adder` changes, are pairwise
  disjoint. That is what makes the options composable.
- Combinations are built in both modes:
  - a greedy covering array in which every pair of values of two options is
    built together at least once (476 pairs in 20 combinations), so two includes
    that clash on a symbol or an assertion fail there;
  - every option on at once for each ship and non-default font.

  Each relaxed build must equal the reference, or the Adder build, with the
  selected options' bytes overlaid.
- Invalid values of every option are rejected, as is strict `--verify-only`.
  Damaged checksums, invalid metadata with a valid XOR and truncated TAP data
  are rejected even with identity disabled.

`python tools/check_build_options.py --full` builds the complete product of
all values instead of the selected combinations: 65,536 combinations, several
hours. Use it after changing the build machinery itself. Either mode leaves
Adder with `laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes
stationslotfix=yes fuelfix=yes hyperspacedockingfix=yes aicouragefix=yes
scannerblipfix=yes stardustfix=yes missiletargetfix=yes textfullstopfix=yes
iffunit=yes randomizedspawn=yes` built. A new option must be added to `OPTIONS`, and a new
fix's areas to `FIX_PARTS`, in that tool.

The ship check compares all other models with the original bytes, resolves
every Adder vertex/edge face reference to the original normal, and executes
all 19 object loaders. It also compares **128 real Z80-rendered Adder frames**
against the original uncompressed side-B model across changing orientations
and four distances. The compared pixels are identical.

The graphics check exercises both startup copies, cockpit backup/restore,
and drawing/XOR-erasing all 91 font glyphs. Gameplay scenarios load the TAP
through the supplied 48K ROM and exercise screens, buying/selling cargo,
equipment purchase, flight views, normal hyperspace and galactic hyperspace.
The emulator checker also rejects overwritten permanent text tables,
incorrect station blueprint pointers or execution through the reclaimed
startup area. Launch/rear-view renders were compared with the original and
match pixel for pixel after the station-pointer correction. The ship check
covers this preinitialised pointer before invoking the generic object loader.

These are automated ZX Spectrum **48K** emulator regressions, not a complete
playthrough or a physical-machine test. The reconstruction still contains
dormant code of unknown purpose and partially decoded blueprint properties. Do not infer
that the entire game is now understood.

All TAPs are 47,918 bytes. The following historical hashes use
`scannerpixelfix=no`. Recorded SHA-256 values with `font=128` after the station-pointer fix:

```text
Krait / original laser: d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
Krait / single laser:   1c18d1de6f3651413d61f944e0d284fcfc9e7e719a32cb9890d439e2c2937a28
Adder / original laser: 361b6a1b1b27f90d4c123d21effd4799ed5f5836da2eb6f834e6102b50d2aaec
Adder / single laser:   8282ee2f28564319fa3ec144ac6e49aee830c4beb7c7c2a3d6cc26672df9a171
```

With `font=48`:

```text
Krait / original laser: fac185ce4248e1dccc99f93a7cb7d2791e220543c24016a3a77a1dfff4cbec47
Krait / single laser:   4518d1c10c5cf72edc4e3be6208065ec87eb9df4e728e11b937beb4a9d089cb7
Adder / original laser: ad647f1fd39aa944fac5de89b43352a9aa4f3e50627520e5bb43ebe061620d4a
Adder / single laser:   cb1a948f3ae591777a7d783c443313f41663275fe7c11282460e2738b373fe56
```

No commit or push is made by any build or test command.

Maintained files for this feature:

- `build.bat`, `make.bat`, `verify.bat`, `tools/build.py`;
- `src/options.asm`, `src/adder-startup.asm`, `src/single-laser.asm`,
  `src/station-slot-fix.asm`, `src/fuel-fix.asm`, `src/ai-courage-fix.asm`,
  `src/scanner-blip-fix.asm`, `src/stardust-fix.asm`, `src/text-full-stop-fix.asm`,
  `src/iff-unit.asm`, `src/randomized-spawn.asm`;
- `src/data/font.asm`, `src/data/font-48.asm`, `tools/font_variant.py`;
- `src/game.asm`, `src/data/ship-blueprints-and-tables.asm`;
- `src/data/initial-runtime-state.asm`;
- `src/data/adder.asm`, `adder-original.asm`, `text-dispatch-first.asm`, `text-dispatch-second.asm`;
- `tools/bootstrap_sources.py`, `tools/analyze_ship_blueprints.py`;
- `tools/check_build_options.py`, `tools/check_laser_variant.py`, `tools/check_ship_variant.py`,
  `tools/check_graphics.py`, `tools/check_station_slot_fix.py`, `tools/check_fuel_fix.py`,
  `tools/check_hyperspace_docking_fix.py`, `tools/check_ai_courage_fix.py`,
  `tools/check_scanner_blip_fix.py`, `tools/check_stardust_fix.py`,
  `tools/check_missile_target_fix.py`, `tools/check_text_full_stop_fix.py`,
  `tools/check_iff_unit.py`, `tools/check_randomized_spawn.py`, `tools/emulator_check.py`;
- `AGENTS.md`, `README.md`, `docs/SHIPS.md`, `docs/GRAPHICS.md`, this document.

The bootstrap generator preserves these conditional hooks and regenerates
the symbolic text targets. `--force` deliberately replaces generated source
annotations/model edits; it is not part of normal builds. Rebuild the default
Krait variant before collecting reference-only runtime analysis or code seeds.

### Status Indicator font fix (`font=128fix`)

This option fixes the corrupted Status Indicator in the Elite 128K instrument panel.

Run `make.bat font=128fix verify=no`, then `verify.bat verify=no`.
The equivalent Python option is `--font 128fix`. This selects
`src/data/font-128fix.asm`: the original `font.asm` with only character codes
`$21..$26` (the six graphic glyphs selected by the owner) copied from
`font-48.asm`. All other glyphs, labels, the 728-byte size and startup copy
remain unchanged. Normal builds need only assembler source. Source regeneration
preserves this variant. The default remains `font=128` and byte-identical.
`tools/check_build_options.py` covers all four fonts alone and in combination;
`tools/check_graphics.py` checks the hybrid bytes and executes all glyphs.

### Status Indicator and smaller ECM/S font (`font=128fix_ecm_s`)

Fixes the corrupted Status Indicator in the Elite 128K instrument panel and uses the smaller ECM and S indicators from the 48K version.

Run `make.bat font=128fix_ecm_s verify=no`, then `verify.bat verify=no`.
The equivalent Python option is `--font 128fix_ecm_s`. This selects
`src/data/font-128fix_ecm_s.asm`, based on `font.asm` with only codes
`$21..$26`, `$3B..$3E` and `$5B..$5E` copied from `font-48.asm`.
The other 77 glyphs, labels, 728-byte size and startup copy remain unchanged.
Normal builds use assembler source only; source regeneration preserves this variant.

### Output TAP filename

`tapfile=elite-128k.tap` is the default. Edit `tapfile=` in `build.bat` to
choose the output name while retaining its selected game options. The file
is written to `release/`; use a plain filename ending in `.tap`, not a path.
Names with spaces must be quoted as one argument, for example
`"tapfile=My Elite.tap"`. The Python equivalent is `--tapfile "My Elite.tap"`.

```text
make.bat tapfile=elite-custom.tap
verify.bat tapfile=elite-custom.tap
```

For modified game options, keep `verify=no` explicit in both commands.
The filename does not change the internal TAP headers or game bytes.
A failed assembly or identity check removes the selected output, leaving other
named releases untouched. Verification and emulator/analysis helpers retain
the default filename unless explicitly configured; `verify.bat` accepts
`tapfile=`, while existing emulator helpers use `release/elite-128k.tap`.
Rebuild that default filename before running those emulator helpers.
