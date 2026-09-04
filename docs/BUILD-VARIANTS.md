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
remain Krait, original laser, 128K-compatible font, both fixes disabled and
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
or `single`. `font` accepts `128` (default), `48`, `128fix` or `128fix_ecm_s`. `scannerpixelfix` and
`stationrandomlaunchfix` accept `no` (default) or `yes`. `verify` accepts `yes`
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

The option check builds all 128 `ship`/`laser`/`font`/`scannerpixelfix`/
`stationrandomlaunchfix` combinations in both verification modes, expects
strict verification of any modification to fail, checks stale-output
removal and rejects damaged checksums, invalid metadata with a valid XOR, and
truncated TAP data even with identity disabled. It also verifies the exact
ten-byte laser patch, exact font bytes from PATCH128 and absence of unrelated
changes for each ship option. The scanner fix is limited to the original
instrument region and its two missile-call operands; the station launch fix
is limited to its original 38-byte selector. It leaves Adder with
`laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes` built.

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
unclassified bytes and partially decoded blueprint properties. Do not infer
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
- `src/options.asm`, `src/adder-startup.asm`, `src/single-laser.asm`;
- `src/data/font.asm`, `src/data/font-48.asm`, `tools/font_variant.py`;
- `src/game.asm`, `src/data/ship-blueprints-and-tables.asm`;
- `src/data/initial-runtime-state.asm`;
- `src/data/adder.asm`, `adder-original.asm`, `text-dispatch-first.asm`, `text-dispatch-second.asm`;
- `tools/bootstrap_sources.py`, `tools/analyze_ship_blueprints.py`;
- `tools/check_build_options.py`, `tools/check_laser_variant.py`, `tools/check_ship_variant.py`,
  `tools/check_graphics.py`, `tools/emulator_check.py`;
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
