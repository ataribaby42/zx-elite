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
`stationrandomlaunchfix`, `stationslotfix`, `fuelfix` and `hyperspacedockingfix` accept `no` (default) or `yes`.
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
| `$BDF5..$BDFF` | 11 | Zero padding before the page-aligned square tables |
| `$91C9..$91D1` | 9 | Three unreferenced `JP` instructions |
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
two bytes in place. With both fixes 53 bytes remain free in 16 areas, the
largest 11 bytes (`$BDF5..$BDFF`).

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

The option check builds all 512 `ship`/`laser`/`font`/`scannerpixelfix`/
`stationrandomlaunchfix`/`stationslotfix`/`fuelfix`/`hyperspacedockingfix` combinations in both
verification modes, expects
strict verification of any modification to fail, checks stale-output
removal and rejects damaged checksums, invalid metadata with a valid XOR, and
truncated TAP data even with identity disabled. It also verifies the exact
ten-byte laser patch, exact font bytes from PATCH128 and absence of unrelated
changes for each ship option. The scanner fix is limited to the original
instrument region and its two missile-call operands; the station launch fix
is limited to its original 38-byte selector, the station slot fix to its
four areas, the fuel fix to its five and the docking fix to its one operand.
It leaves Adder with `laser=single font=48 scannerpixelfix=yes
stationrandomlaunchfix=yes stationslotfix=yes fuelfix=yes
hyperspacedockingfix=yes` built.

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
  `src/station-slot-fix.asm`, `src/fuel-fix.asm`;
- `src/data/font.asm`, `src/data/font-48.asm`, `tools/font_variant.py`;
- `src/game.asm`, `src/data/ship-blueprints-and-tables.asm`;
- `src/data/initial-runtime-state.asm`;
- `src/data/adder.asm`, `adder-original.asm`, `text-dispatch-first.asm`, `text-dispatch-second.asm`;
- `tools/bootstrap_sources.py`, `tools/analyze_ship_blueprints.py`;
- `tools/check_build_options.py`, `tools/check_laser_variant.py`, `tools/check_ship_variant.py`,
  `tools/check_graphics.py`, `tools/check_station_slot_fix.py`, `tools/check_fuel_fix.py`,
  `tools/check_hyperspace_docking_fix.py`, `tools/emulator_check.py`;
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
`tools/check_build_options.py` now covers 128 combinations, including all four
fonts; `tools/check_graphics.py` checks the hybrid bytes and executes all glyphs.

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
