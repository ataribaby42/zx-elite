# ZX Spectrum Elite 128K-compatible reconstruction

## Project boundary

This directory is the root of the independent ZX Spectrum Elite project.
Run project commands from this directory. Keep project source, documentation,
reports, temporary files and release artifacts in the layout described below.

## Objective and acceptance test

Reconstruct the Torus/Firebird ZX Spectrum Elite release distributed as
`assets/Elite - 128k.tap` as readable, buildable Z80 source.

The first non-negotiable milestone is a clean build whose resulting TAP is
byte-for-byte identical to that reference. The reference currently has:

```text
size:   47,918 bytes
SHA256: d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
```

Do not call the reconstruction complete merely because a TAP wrapper around
the original binary is identical. Every byte of the BASIC loader, loading
screen and `$6048..$FFA8` image must be emitted by assembler source. Temporary
`INCBIN` scaffolding is acceptable only when clearly marked as incomplete and
covered by a check that prevents it being mistaken for the final result.

## Historical target

The filename â€ś128kâ€ť means 128K-*compatible*. The executable is a 48K memory-map
program fixed to work on later 128K Spectrum machines; it does not page or
require 128K RAM. The reference tape contains:

This distinction is permanent project terminology: **Elite 128K is the name
of the compatibility-fixed release of Elite 48K, not a Spectrum 128K port.**
It has no expanded-memory assets, bank switching, 128K-only code path or
128K-specific gameplay. A 48K ROM/memory emulator is the correct functional
environment for its game code. Testing on a physical 128K model would only
verify that the original 48K incompatibility was fixed; it would not exercise
additional functionality.

### Mandatory emulator model

Always run this project in **ZX Spectrum 48K mode**, for both automated and
manual emulator tests. Always use `assets/zxspectrum48k.rom`. Do not select a
Spectrum 128K, +2 or +3 emulation profile because of the release filename.
Every emulator report must identify the model as ZX Spectrum 48K. Keep this
rule even when investigating the historical compatibility fix.

| TAP blocks | Payload | Load/start metadata |
|---|---:|---:|
| BASIC `ELITE` | 130 B | autostart line 10 |
| CODE `a` | 6912 B | `$8000` loading screen |
| CODE `elite` | 40,801 B | `$6048..$FFA8`, entry `$7000` |

The screen header stores `$8000`; the BASIC `LOAD "" SCREEN$` statement
overrides that address and loads it into the screen at `$4000`.

Treat the reference bytes and execution in an emulator as authoritative.
Existing notes may contain errors; mark inferred meanings separately from
verified facts.

## Repository layout

- `assets/` contains immutable reference media and the supplied 48K ROM.
- `docs/` contains project-authored documentation. Put new maintained
  documentation directly in this directory.
- `docs/info/` contains pre-existing research notes and POKE files supplied by
  the project owner. Preserve them verbatim and keep them separate from new
  project documentation.
- Put machine-generated maps/reports in `docs/generated/` and explain how to
  regenerate them. Never overwrite the supplied research notes in `docs/info/`.
- `docs/evidence/` retains small historical reports from one-off investigations
  whose results must survive a build cleanup. Keep these under version control.
- `docs/GRAPHICS.md` documents verified graphics. Retain the user-requested
  font atlases in `docs/images/font-128.png` and `docs/images/font-48.png`
  under version control, not in an ignored build directory. Each shows
  91 active glyphs plus five empty slots for its corresponding font option.
- Retain `docs/images/cockpit-monochrome.png` and
  `docs/images/cockpit-attributes.png`. They are deterministic 3x renders of
  the initial bitmap, respectively without and with its stored attributes;
  regenerate them with `tools/render_cockpit.py`.
- `src/` contains hand-maintained or generated-but-reviewable assembler source.
  Keep top-level assembler files directly here and data includes in `src/data/`.
  Source generators must use this layout too; do not recreate a separate
  generated-source directory. Normal builds never regenerate source files.
- `tools/` contains deterministic extraction, conversion, verification and
  emulator helpers. z88dk is installed separately; no assembler archive is
  bundled. Record the actual assembler version printed by each build.
- `tools/deps/` contains the optional local SkoolKit installation, excluded
  from Git. `tools/install_analysis_tools.bat` installs it; Python helpers
  use `ANALYSIS_DEPS` from `tools/tape.py`. Never install dependencies in `build/`.
- `build/` contains only disposable generated intermediate binaries, maps,
  logs and emulator artifacts. Nothing required for builds or tests may live
  only here. Normal builds recreate their outputs; test/analysis commands
  recreate their respective reports. Keep these separate from the deliverable.
- `release/` contains the final `release/elite-128k.tap` and a short English
  `README.md` with loading instructions. Preserve this README under version
  control; the TAP and all of `build/` remain ignored. Build, verification
  and emulator helpers share the output path defined in `tools/tape.py`.

The `.gitignore` here must work with `zx-elite/` as a standalone repository
root. The local assembler archive has been removed. Its ignore rule prevents an accidental future
download from entering Git; builds use the separately installed assembler.

## Required workflow

1. Run `git status --short --branch` before editing. Preserve unrelated work.
2. Parse TAP structurally: validate each little-endian block length and XOR
   checksum; never search for byte patterns without recording block/load scope.
3. Use z88dk `z80asm.exe` as the assembler. Preserve the owner's simplified
   BAT files and selected settings; do not rewrite them when adding options.
   Run them from the project directory. `make.bat` only forwards its arguments
   to `tools/build.py`; defaults belong in that Python helper, not duplicated
   in `make.bat`. `build.bat` holds the owner's explicit choices (including
   any REM examples). Build failures must propagate and leave no stale release.
   Document allowed values in the project documentation. Run `make.bat`
   directly when passing options on the command line.
4. Package TAP blocks deterministically. Validate Spectrum header fields,
   payload lengths, checksums, total size and SHA-256.
5. When building the default reconstruction, run `verify.bat`. Success requires structural
   validation and exact bytes against `assets/Elite - 128k.tap`. Authorized
   modifications use `make.bat ship=adder verify=no` (or another documented
   option) and `verify.bat verify=no`. Only binary identity may be disabled;
   TAP structure, metadata, XOR checksums and assembler bounds remain mandatory.
6. When semantics change, use targeted emulator checks of the affected behaviour.
   Exact bytes prove a reconstruction build, while emulator tests prove
   modified behaviour. Choose their scope using the rules below.
7. Do not commit or push unless explicitly asked.

## Proportionate validation

Select builds and tests according to the actual feature or fix and its likely
impact. Run the smallest meaningful set that checks the changed behaviour,
relevant edge cases and directly affected callers or options.

Do not automatically rerun every historical test, every gameplay scenario or
the complete build-option matrix. The feature-specific test lists elsewhere
in this file and in the documentation are a catalogue of available checks,
not a mandatory checklist for every edit. This section takes precedence over
any broader wording in those lists.

Expand validation only when the change affects shared code, build machinery
or memory layout in ways that justify broader coverage, when a failure calls
for further investigation, or when the owner explicitly requests it. A full
matrix is not required merely because a build option exists or is mentioned.
Documentation-only changes normally need a content review, not a game build.
Mandatory integrity checks built into any build that is actually performed
(TAP structure, checksums and assembler bounds) must remain enabled.

Briefly report what was actually checked and any material limits. Do not run
unrelated tests just to repeat an earlier report or populate every field of
the completion-report template.

## Reverse-engineering rules

- Disassembly is evidence, not automatically correct source annotation. A
  linear disassembler will decode tables and text as plausible instructions.
- Initially preserve every byte exactly. Split a region into code or data only
  after references, control flow, POKEs, runtime tracing or formats support it.
- Give verified labels descriptive names. Use neutral address-based labels such
  as `L_D065` where meaning is uncertain. Mark hypotheses with `INFERRED:` and
  cite the evidence in nearby comments or a generated map.
- Preserve the verified routine/state names and comments in
  `tools/verified_annotations.py` when regenerating `src/game.asm`. See
  `docs/CODE-NAMES.md` for the named paths. Original `L_xxxx` names remain
  aliases for existing analysis tools, not numeric substitutes for new code.
- Never copy C64/BBC routine layouts, addresses, ship formats or mission state
  into this version. They are distinct ports. General Elite concepts may guide
  investigation, but ZX bytes and runtime behaviour decide the result.
- Known POKE addresses are useful entry points, not blanket proof of a whole
  routine's meaning. Record the original bytes before adding a label/comment.
- Never hard-code a numeric address for relocatable code or data in assembler.
  Always use labels, assembler expressions or addresses calculated from a
  symbolic base and parameters. This applies to jumps/calls, immediate pointer
  loads, memory operands, pointer tables, inline data and self-modifying code.
  Code and data references must remain correct when their targets move.
- Derive offsets, lengths and table entry sizes from labels and expressions
  such as `Item-Table`, `End-Start` and `Table+Index*EntrySize`. Name structure
  field offsets and format constants; do not hand-calculate offsets that depend
  on instruction sizes, text lengths or the current build's layout. Merely
  assigning a hard-coded relocatable address to a named constant is not enough.
- For separately assembled parts, build scripts, patches and emulator tools,
  obtain current addresses from the assembler's symbol map or shared symbolic
  definitions. Never manually copy addresses from a previous build. Source
  generators must emit symbolic references, not reintroduce numeric targets.
- True fixed machine addresses (ROM entry points, hardware ports, video RAM)
  and prescribed memory-map boundaries must use named constants. Original
  reference addresses may identify immutable reference bytes or compatibility
  constraints, but must not replace labels for current relocatable targets.
  Guard required fixed positions and in-place patch boundaries with assembler
  assertions; an incompatible move must fail the build rather than silently
  patch or access the wrong bytes.
- Use assembler assertions for table/index bounds, block lengths and memory
  limits, including image end `$FFA9` (exclusive). After moving code or data,
  verify references from callers, tables, generated files and patch tools.
- Preserve the corrections documented in `docs/ADDRESSING-AUDIT.md`.
  `StartupAfterGraphicsCopy` must identify actual code in either ship variant,
  not an offset into reclaimed startup data. Read PATCH128 font bytes using
  the immutable tape's copy operands, and locate current data using the current
  assembler map. Keep those two address spaces separate in regression tools.
  After changing optional-feature references, run
  `tools/check_variant_relocation.py` as well as the ordinary game tests.
- Do not â€śclean upâ€ť, optimize, reorder or modernize instructions during the
  binary-identical phase. Prefixes, redundant instructions, unused bytes,
  padding, self-modifying code and data placement can all be significant.

## Source documentation priorities

Write all new and updated project documentation in English. This includes
Markdown files, generated reports, explanatory source comments and retained
diagram captions. Preserve the supplied research notes in `docs/info/`
verbatim, as required below, but do not add Czech text to project files.

The first confirmed data regions are now isolated as ASM includes:

- `src/data/font.asm`: `FontBitmap`, `$C000..$C2D7`, 728 bytes;
  91 eight-row glyphs for codes `$20..$7A`. The startup copy lives at
  `$5D70..$6047` and must not overlap the game image at `$6048`.
- `src/data/cockpit-attributes.asm`: `CockpitAttributes`,
  `$C700..$C7FF`, 256 colour cells, copied to `$5B00` then to screen `$5A00`.
- `src/data/cockpit-bitmap.asm`: `CockpitBitmap`,
  `$C800..$CFFF`, 2,048 bytes / 256 x 64 pixels, screen destination `$5000`.

Runtime gameplay tracing also confirms these non-code regions:

- `$6048..$617F`: initial mutable runtime state;
- `$6180..$6FFF`: 19 structured ship/object blueprints and dispatch-pointer
  tables. `docs/SHIPS.md` is the maintained map and
  `tools/analyze_ship_blueprints.py` validates it against the 128K-compatible
  tape plus the supplied 48K Krait/Adder comparison tapes;
- `$92B5..$9965` and `$9A9D..$9E73`: encoded text and its token dictionary;
- `$A816..$A87D`: the mutable 104-byte buffer used directly by ROM tape
  load/save. Its first 102 bytes are persistent commander data; the final two
  tape bytes carry no necessary persistent information, although their RAM
  addresses are reused as transient runtime variables;
- `$A910..$A975`: the initial 102-byte JAMESON template, also reused as a
  mutable working copy by the tape workflow;
- `$BE00..$BFFF`: low- and high-byte tables for `n*n`, `n=0..255`.

`tools/run_runtime_scenarios.py` reproduces docked screens, transactions,
in-flight screens, three normal hyperspace jumps and a galactic jump. Run its
normal and `--accesses` modes before `tools/analyze_runtime.py` when extending
the map. Actual program counters from these 48K runs are persistent source
seeds in `src/runtime-code-seeds.json`.

Do not classify `$C2D8..$C6FF` as a plain graphics buffer. It is reused at
runtime, but the initial image also contains dormant code around
`$C350..$C40C`, likely tape/save support. Keep mixed or unexercised regions
unclassified until control flow or format evidence separates them.

Preserve the verified ship-variant distinction: the 128K-compatible release
and 48K side A use Krait in blueprint slot 17, while 48K side B replaces that
slot with Adder. Keep Krait in the default reconstruction; the owner-authorized
`ship=adder` modification replaces slot 17 explicitly. Do not add a twentieth
slot. See `docs/BUILD-VARIANTS.md` for its source and memory layout. There is no
separate Boulder blueprint in this ZX release; the mining special case creates
two instances of blueprint ID 5, Splinter, directly from an Asteroid.

For ship variants run `tools/check_build_options.py`,
`tools/check_ship_variant.py` and `tools/check_graphics.py`, then gameplay
scenarios with `tools/run_runtime_scenarios.py`, always in 48K mode. The build
option check deliberately leaves an Adder TAP with
`laser=single font=48 scannerpixelfix=yes` for testing.
Rebuild the default Krait version before collecting reference reconstruction/runtime-code seeds.
The Adder test compares 128 actual rendered frames with the original side-B
model, in addition to checking all 19 object loaders and other ship geometry.

Station slot zero in `InitialRuntimeState` is preinitialised and bypasses the
generic object loader. Its word at offset `$23`, `StationBlueprintPointer`,
must be emitted as `defw ShipCoriolisStationBlueprint`, never copied as raw
address bytes. Preserve this in source regeneration. Moving models without
relocating this word previously reduced the visible station to a small dot.
The build validates this pointer; ship tests check it before/after startup,
and full emulator scenarios check the loaded and final runtime values. After
model relocation, also run launch/rear-view and hyperspace regressions.

Preserve both Adder definitions: `src/data/adder.asm` is the selected
299-byte optimized model; `adder-original.asm` is the unmodified 307-byte 48K
side-B model with all 15 normals and original face references. Keep the latter
as an unlinked reference and preserve it in source regeneration. Both use the
same labels; do not include both or substitute the larger model without
addressing the additional eight-byte memory requirement.

Never treat the BASIC loader RAM as free: `$5B00..$5D6F` is reused as a
624-byte screen backup by `$8E5C..$8E94`. The Adder variant instead reuses only
the original one-time startup area for persistent text pointers and executes
its relocated startup at `$C600` before that graphics buffer is used. Do not
call that relocated startup again after drawing begins. Restart/death paths
continue to use the original `$718F` entry. The IM2 table and stacks remain
unchanged.

Preserve the distinction between initial tape content and runtime reuse:
the `$C000..$CFFF` area later serves graphics buffers and a temporary stack.
Do not interpret that whole area as a font or immutable graphics. Keep named
sizes derived from end/start labels. `tools/bootstrap_sources.py` reads data
boundaries from verified original copy operands, and `tools/check_graphics.py`
checks the original copy and glyph routines in a Z80 simulator.

Also preserve the attribute distinction recorded in `docs/GRAPHICS.md`:
the `$C700` table initializes the mutable `$5B00` buffer and cockpit restore
copies that buffer to `$5A00` VRAM. Other routines subsequently colour
instrument cells directly or update the saved buffer. Do not describe the
original table as unused, or as the cockpit's only colour mechanism.

Comment only what the evidence supports, starting with:

- bootstrap and 128K compatibility fix;
- input tables and the documented B/Symbol Shift swap addresses;
- encounter/safety indicator and scanner-pixel fixes;
- legal status and station Viper behaviour;
- mission/pirate triggers around documented `$D0xx`, `$D7xx`, `$DDxx` and
  `$DExx` state/routines;
- laser drawing around `$ECD4..$EE10`;
- commander save/load layout and its 104-byte 128K-compatible record.

The existing save and mission documents are research input. Update generated
documentation when code evidence confirms or contradicts them; do not rewrite
the originals.

The shared line renderer at `$EE10` is `DrawLine`; the player laser routine
at `$ECD4` is `DrawLaser`. `laser=original` is the default. `laser=single`
selects `src/single-laser.asm`, implementing the final ten-byte patch in
`docs/info/ELIT128P_laser_mod-readme.txt`. Keep the original random DE endpoint
and C quadrant bits; do not substitute the earlier no-wiggle patch. Use
assembler labels for the jump target and retain the original layout. Source
regeneration must preserve both the names and conditional laser include.
Run `tools/check_build_options.py` and `tools/check_laser_variant.py` plus a
48K ROM-load/launch/firing smoke test after changing this feature. Keep
`verify=no` explicit for modified builds; structural checks stay enabled.

## Tool safety and generated files

`font=128` is the default and selects the original `src/data/font.asm`.
`font=48` selects `src/data/font-48.asm`, extracted from the validated game
block in `assets/Elite128fixes/PATCH128.TAP`. Both contain exactly 728 bytes
for codes `$20..$7A`, with the same symbols, source address and runtime copy.
Do not copy 768 bytes into the active font: the extra 40 bytes would overlap
the game image. Preserve the conditional include in source regeneration.
The optional font requires explicit `verify=no`; no other PATCH128 changes
are imported. Run the 64-case build matrix, graphics tests and 48K emulator
startup/screen checks after changing this option. Normal builds use ASM data
only and never depend on the patch tape. The owner has requested permanent
previews of both fonts in `docs/images/`; preserve the two named atlases above.

`scannerpixelfix=no` preserves the original indicator code. The optional
`scannerpixelfix=yes` implementation in `src/scanner-pixel-fix.asm` must fit
inside the original `$A660..$A705` block (166 bytes), with no extra RAM.
Preserve bit 0 at screen `$50C9` on the write itself, both for ECM on and off;
do not force the bit on, temporarily erase it or modify shared font bytes.
Keep the shared text renderer unchanged. Preserve the selected font and all
other indicator pixels, including missile counts 0..4 and their return mode.
Run `tools/check_scanner_pixel_fix.py` for both fonts, the build-option matrix
and 48K gameplay regressions. Preserve the conditional source include and
original-layout assertions in source regeneration. Do not rewrite the BATs.

The status bytes at `$D137` are an inline `$11` consumed by `L_BA99`, followed
by `CALL L_D1A6`. Never restore the misleading linear-disassembly form
`LD DE,L_A6CD` / `POP DE`: it creates a false reference into the indicator
tables and corrupts the status routine if those tables move.

`stationrandomlaunchfix=no` preserves the original station launch behaviour.
The optional `yes` include in `src/station-random-launch-fix.asm` must stay
inside the original 38-byte `$F44A..$F46F` selector. Reuse the station gate's
preceding random result via the RNG seed, while retaining both the original
RNG advancement and the rock hermit's fighter choice. Do not simply remove
the selector's RNG call: that biases the shared hermit path to Sidewinders.
Police Viper, Thargon and special-mode Thargoid launches must remain intact.
Run `tools/check_station_random_launch_fix.py` for both ship choices; include
the preceding launch gates, all 65,536 seed states, and actual allocation
with free/full slots. Preserve the include and assertions in regeneration.
Use the 64-case option matrix and 48K ROM-load/launch regression as well.

- Source boundaries, offsets and lengths must be calculated by scripts or
  labels. No tool may silently truncate or pad a block.
- Generated assembler should contain a provenance header naming the input TAP,
  block index, load address and source hash.
- A generator must be deterministic: two runs with unchanged inputs produce
  identical files.
- Keep the original TAP and ROM read-only in practice. Build and analysis
  outputs go under `build/`, `release/`, `src/` or `docs/generated/`.
  The optional package installer writes to `tools/deps/`; preserve historical
  one-off reports in `docs/evidence/` when requested. Retained
  documentation illustrations explicitly requested by the user belong in
  `docs/images/` instead of the ignored generated directories.
- Do not distribute a modified ROM. The supplied ROM is only for local
  disassembly/emulator tests where needed.

## POK patch policy

POK files always target only the unmodified original 128K-compatible release
in `assets/Elite - 128k.tap`. They do not target modified reconstruction builds
or the older 48K releases. Do not create or maintain dedicated POK generation
scripts in `tools/`; the POK file itself is the deliverable. Validate patch
addresses and original values against the structurally validated reference TAP.

## Completion report

Report the changed files, exact commands, z88dk version, block map, output hash,
whether binary identity passed, any emulator tests, remaining unlabelled/data
regions, git status, and that no commit/push occurred. Do not describe a linear
byte-preserving disassembly as fully understood or fully documented.
