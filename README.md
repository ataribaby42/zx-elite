# ZX Spectrum Elite 128k source reconstruction

This project reconstructs the supplied **original ZX Spectrum Elite
128K-compatible release** as an independent, standalone project.

Despite its published name, **Elite 128K is not a 128K game**. It is the
original 48K game with its incompatibility on later 128K Spectrum models
fixed. It still uses only the 48K address space: there is no bank switching,
expanded-memory content or separate 128K code path.

All three tape payloads are assembled from the source files in
`src/`. The **default** TAP is **byte-for-byte identical** to
`assets/Elite - 128k.tap`. No `INCBIN` or external binary payload is used
to construct the output. The original tape is read only for verification
during a normal build.

The source covers every byte, but it is not yet a fully documented
disassembly. See **Reconstruction status** below before changing game logic.

## Build

Run commands from the project root. The default reconstruction is byte-for-byte
identical to the original tape:

```bat
make.bat
verify.bat
```

Combine options to build a modified release with a custom filename:

```bat
make.bat ship=adder laser=single font=128fix_ecm_s scannerpixelfix=yes verify=no tapfile=elite-custom.tap
verify.bat verify=no tapfile=elite-custom.tap
```

For a double-click build, edit the options in `build.bat`'s `make.bat` call.
For command-line options, run `make.bat` directly. It forwards arguments to
`tools/build.py`; defaults are supplied by the Python helpers.

### All build options

| Option | Allowed values | Default | Description |
|---|---|---|---|
| `ship` | `krait`, `adder` | `krait` | Selects the ship in blueprint slot 17. `krait` keeps the original compatibility-release model; `adder` replaces it with the optimized model based on the 48K side-B Adder. The game still has 19 slots. |
| `laser` | `original`, `single` | `original` | Keeps the original laser beams, or draws one centred beam with the original random endpoint wiggle. |
| `font` | `128`, `48`, `128fix`, `128fix_ecm_s` | `128` | Selects the font and instrument glyphs; see the descriptions below. |
| `scannerpixelfix` | `no`, `yes` | `no` | `yes` preserves the scanner pixel overlapped by the ECM indicator, both when ECM is on and when it is off. |
| `stationrandomlaunchfix` | `no`, `yes` | `no` | `yes` allows both Cobra and Python traders to launch from stations while preserving police Viper, rock hermit fighter and Thargon choices and RNG advancement. |
| `verify` | `yes`, `no` | `yes` | `yes` requires byte-for-byte identity with the original TAP. `no` allows modified game bytes; TAP structure, metadata, checksums and assembler memory bounds remain mandatory. |
| `tapfile` | A plain filename ending in `.tap` | `elite-128k.tap` | Names the output file inside `release/`. No directory paths are accepted. Quote an argument containing spaces, such as `"tapfile=My Elite.tap"`. Internal TAP headers are unchanged. |

Font choices:

| Value | Description |
|---|---|
| `128` | Original font from the 128K-compatible release. |
| `48` | Prettier font from the 48K version. |
| `128fix` | Fixes the corrupted Status Indicator in the Elite 128K instrument panel. Uses the original font with codes `$21..$26` copied from the 48K font. |
| `128fix_ecm_s` | Fixes the corrupted Status Indicator in the Elite 128K instrument panel and uses the smaller ECM and S indicators from the 48K version. Replaces codes `$21..$26`, `$3B..$3E` and `$5B..$5E`. |

All four fonts contain 91 glyphs (728 bytes) and use the same startup copy and
character renderer. Normal builds assemble the selected font source without
reading `PATCH128.TAP`. The font, scanner and station fixes require no extra RAM.

Any game modification requires explicit `verify=no`; changing only `tapfile`
still permits exact verification. The build verifies its output automatically.
When running `verify.bat` separately, supply the same `tapfile` and use
`verify=no` for modified builds. Options also accept the Python-style syntax
`--ship adder`, `--font 48`, `--verify no` and `--tapfile elite-custom.tap`.
Use `python tools/build.py --help` for command-line help; `--verify-only`
checks an existing TAP without building (the mode used by `verify.bat`).

See [Build variants](docs/BUILD-VARIANTS.md) for memory layouts and targeted
regression checks.

### Requirements and output

- Python 3.10 or later, available as `python`.
- The **z88dk Z80 assembler**, available as `z80asm.exe` on `PATH`, or selected
  through the `Z80ASM` environment variable containing its executable path.

If the assembler is not on `PATH`, set its executable path first:

```bat
set "Z80ASM=E:\Development\z88dk\bin\z80asm.exe"
build.bat
```

Install z88dk separately; no assembler archive is bundled. Each build records
the actual assembler version in `build/assembler-version.txt`. Optional Python
analysis packages are not required for normal builds.

The output is `release/<tapfile>`. The release directory also contains a
maintained `README.md` with loading instructions. Intermediate binaries, maps,
logs and reports go in `build/`. A failed build removes the selected output
so an old successful TAP cannot remain in its place; other named releases are
left untouched. Failed verification removes the previous PASS report.

Existing emulator and analysis helpers use `release/elite-128k.tap`. Rebuild
that default filename before running them, so the TAP matches the current
binaries and symbol map.

The standalone `.gitignore` excludes generated outputs in `build/` and
`release/`, while retaining `release/README.md`. The entire `build/` directory
is disposable: normal builds recreate their intermediate files, and analysis
tools recreate their own reports and emulator captures. `build/src/` contains
assembler objects, not maintained source. Optional SkoolKit dependencies live
in `tools/deps/`; retained investigation reports live in `docs/evidence/`.
Keep `assets/`, `src/`, `tools/` and maintained documentation. Distribute the
final TAP separately, for example as a GitHub Release attachment.

## Reference tape and memory map

```text
Size:   47,918 bytes
SHA256: d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
```

TAP block numbers below are zero-based. Each pair consists of one Spectrum
header and one data block; payload sizes exclude flag and checksum bytes.

| Blocks | Name | Payload | Header metadata / runtime destination |
|---|---|---:|---|
| 0, 1 | `ELITE` | 130 B | BASIC, autostart line 10 |
| 2, 3 | `a` | 6,912 B | Header says `$8000`; `SCREEN$` loads at `$4000` |
| 4, 5 | `elite` | 40,801 B | `$6048` through `$FFA8`, inclusive |

The BASIC program clears memory, loads the screen and CODE blocks, then
executes `RANDOMIZE USR 28672`. Entry `$7000` jumps to `$716B`. The exclusive
end of the tape's game image is `$FFA9`, not `$10000`.

The â€ś128kâ€ť filename identifies that compatibility-fixed 48K release. The tape
does not contain extra banked 128K assets or code. The other supplied tape
variants are research references; the optional Adder model is extracted from
the supplied 48K side-B reference into reviewable ASM, not loaded from that
tape during a normal build.

The original BASIC bytes and container metadata are retained. The builder
therefore packages TAP blocks itself instead of using a tool that generates
a different BASIC loader. Lengths and checksums are calculated from the
assembled payloads; game origin and entry are checked against the linker map.

## Source layout

| File | Purpose |
|---|---|
| `AGENTS.md` | Scope, verification requirements and rules for future work |
| `src/basic.asm` | Tokenized BASIC, with line lengths derived from labels |
| `src/screen.asm` | Loading bitmap and attribute bytes |
| `src/game.asm` | Z80 instructions, labels and preserved unclassified bytes |
| `src/single-laser.asm` | Optional centred laser with the original endpoint wiggle |
| `src/data/font.asm` | Verified 91-glyph font / graphic character set |
| `src/data/cockpit-bitmap.asm` | Initial 256 x 64 cockpit bitmap |
| `src/data/cockpit-attributes.asm` | Initial 32 x 8 cockpit colour attributes |
| `src/data/initial-runtime-state.asm` | Initial mutable state below the entry point |
| `src/data/ship-blueprints-and-tables.asm` | Structured ship records and dispatch-pointer tables |
| `src/data/encoded-text.asm` | Encoded zero-terminated game text |
| `src/data/text-token-dictionary.asm` | Token dictionary used by the text expander |
| `src/data/active-commander-initial.asm` | Initial 104-byte tape buffer: 102 persistent commander bytes and two transient bytes |
| `src/data/default-commander.asm` | Initial 102-byte JAMESON template and tape working copy |
| `src/data/square-tables.asm` | Verified low/high-byte square lookup tables |
| `tools/build.py` | Assembly, TAP packaging and binary identity checks |
| `tools/tape.py` | TAP parser, header and checksum helpers |
| `tools/bootstrap_sources.py` | Deliberate, one-time source regeneration |
| `tools/emulator_check.py` | Optional Z80 execution, text recognition, memory-access tracing and screenshots |
| `tools/analyze_runtime.py` | Aggregate verified 48K play scenarios into code seeds and a runtime map |
| `tools/run_runtime_scenarios.py` | Reproduce docked, flight, trading and hyperspace traces without screenshots |
| `tools/check_graphics.py` | Targeted execution checks of font and cockpit routines |
| `src/station-random-launch-fix.asm` | Optional station trader fix within the original 38-byte launch selector |
| `tools/check_station_random_launch_fix.py` | Exhaustive station/police/hermit RNG tests and actual child allocation regressions in 48K memory |
| `tools/check_build_options.py` | All 64 ship/laser/font/scanner-fix/station-launch-fix combinations in both verification modes and invalid TAP checks |
| `tools/check_scanner_pixel_fix.py` | Exhaustive pixel preservation, indicator/missile comparison and 48K first-launch test |
| `tools/check_laser_variant.py` | Actual laser/line rendering, endpoint randomisation and stack checks |
| `tools/render_cockpit.py` | Monochrome and initial-attribute cockpit renderings |
| `tools/analyze_ship_blueprints.py` | Validate and name the 128K-compatible ship/object table plus the 48K Krait/Adder variant slot |
| `docs/` | Project-authored documentation |
| `docs/info/` | Supplied research notes and POKEs, preserved unchanged |
| `docs/generated/` | Reproducible machine-generated maps and reports |
| `docs/GRAPHICS.md`, `docs/images/` | Verified graphics documentation and retained font image |
| `docs/COMMANDER-STATE.md` | Verified active record, tape buffer, snapshot and death/restart behaviour |
| `docs/SHIPS.md` | Verified ship/object IDs, blueprint records, shared geometry, 48K Adder comparison and mining chain |

Assembler source lives directly in `src/`, with data includes in `src/data/`.
The extraction tools use the same layout; there is no separate generated-source
directory.

Keep all assembler files, including `src/data/*.asm`, under version
control even though their first version was generated. Normal builds never
regenerate or overwrite them. The build checks included sources too, so a
binary inclusion cannot bypass the source-only reconstruction requirement.
Build outputs and analysis dependencies are ignored by Git.

## Reconstruction status

Control-flow discovery starts at `$7000`, plus two entry candidates identified
by the supplied laser notes. It currently yields:

- **13,390 candidate instructions**, covering **26,168 bytes**;
- **10,470 bytes of verified data**, isolated in named ASM includes;
- **4,163 unclassified bytes**, preserved as explicit `DEFB` source.

The font is 91 glyphs x 8 rows = 728 bytes, not 768 or 2,048 bytes. The
retained [font image and graphics documentation](docs/GRAPHICS.md) show the
91 active slots plus the following five zero-filled slots for comparison.
The cockpit bitmap occupies 2,048 bytes, with 256 separate colour attributes.
Their initial storage is reused at runtime; it must not be treated as ROM.

Unclassified regions can contain graphics, tables, text, padding **or further
code** reached by indirect dispatch. Instruction discovery is not a proof
that every candidate has the intended semantics. Neutral labels retain
original addresses; comments distinguish verified facts from research hints.

Direct in-image branch and call targets use labels. Immediate register-pair
values that look like addresses also have labels, but some may actually be
numeric constants. These inferred references and any overlapping decode
candidates are recorded in `docs/generated/reconstruction.json`. Review them
before relocating code. Undecoded tables may still contain numeric pointers;
this initial reconstruction is deliberately fixed to the original layout.

POKE landmarks have labels and placement assertions, but **none of the
supplied POKE modifications are applied**. Existing docs describe several
different releases; their meanings must be checked against this tape before
use. C64 or BBC offsets must never be substituted.

Exact binary identity is the acceptance condition for this baseline. It does
not mean that all routines, ship models, save fields or mission logic have
already been understood and annotated.

The [ship and object blueprint map](docs/SHIPS.md) now identifies all 19
records in the 128K-compatible release. It also verifies the Krait in slot 17,
extracts the Adder from the supplied 48K side-B comparison TAP and documents
the ZX-specific Asteroid-to-Splinter mining path.

## Optional analysis and emulator checks

The optional tools use [SkoolKit](https://skoolkit.ca/docs/skoolkit/), pinned
to version 10.0. Installation writes only to the ignored `tools/deps/`
directory and needs access to PyPI:

```bat
tools\install_analysis_tools.bat
```

To deliberately reconstruct the three source files again:

```bat
python tools\bootstrap_sources.py --force
```

**This discards later source annotations or edits.** Back them up first.
Without `--force`, the generator refuses to overwrite existing source.
The generator also creates `docs/generated/reconstruction.json` with byte
coverage, inferred references, landmarks and the tape block map.

Verified gameplay traces are documented in [the runtime map](docs/RUNTIME-MAP.md).
`tools/analyze_runtime.py` converts program counters reached through indirect
dispatch into persistent `src/runtime-code-seeds.json` input. This lets the
source generator classify code reached at runtime without guessing that all
remaining bytes are instructions.

Run these after a successful build:

```bat
python tools\emulator_check.py --seconds 3 --name boot
python tools\emulator_check.py --seconds 12 --key 3:0.5:N --key 5:0.5:SPACE --key 8:0.5:1 --name launch
python tools\check_graphics.py
```

The checker loads the rebuilt tape using the supplied Spectrum ROM and a
Z80 simulator, verifies the loaded game bytes and entry point, then executes
the game with interrupts and keyboard input. The key format is
`start-second:duration-seconds:key`. It does not patch game RAM to force a
successful result. Screenshots, final memory and execution reports are in
`build/emulator/`.

Use `--no-screenshots` for text-only exploration. Add `--memory-accesses` to
run the slower Python Z80 simulator and record every integer memory address
read or written. The latter separates executed code from likely tables and
mutable state, while retaining writes into candidate code so self-modifying
instructions are not accidentally labelled as ordinary data.

Initial checks, visually inspected:

- ROM loading reached `$7000`, with all 40,801 game bytes intact;
- title screen showed the rotating ship and commander-loading prompt;
- `N`, Space and `1` advanced through startup into the front view after launch.

The launch run executed 4,388,554 Z80 instructions and visited 4,676 distinct
instruction addresses inside the game image. This is a startup/launch check,
not a complete playthrough. The supplied **48K ROM** is deliberately used
because this is a 48K game. There is no 128K-ROM code path to test. Running it
on physical 128K hardware would be useful only as a compatibility check for
the historical fix, not as a test of expanded-memory behaviour.

`check_graphics.py` separately executes the original Z80 startup copies,
cockpit save/restore and all 91 glyphs' address-selection/drawing loops. It
checks the resulting screen bytes and XOR erasure using controlled RAM and
register setup, without modifying instructions. Its report is saved under
`build/graphics-check/`. This targeted test is distinct from normal startup.

`python tools/render_cockpit.py` renders the initial cockpit both as a
monochrome bitmap and with its stored attributes. The retained images and an
analysis of initial copying versus later procedural colour updates are in
[the graphics documentation](docs/GRAPHICS.md).

## Provenance

The game, screen and ROM retain their original ownership; this reconstruction
does not grant new rights to those assets. The existing owner-supplied media
and research documents have not been modified. Build tooling is original to
this reconstruction; the optional decoder/emulator is an installed tool,
not source copied into the game.

Assembler documentation: [z88dk](https://github.com/z88dk/z88dk).
