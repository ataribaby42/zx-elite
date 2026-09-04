# Optional-feature addressing audit

Scope: Adder replacement/startup, both fonts, single laser, scanner pixel fix,
their source generators, patch export and emulator checks. This is not a claim
that every unidentified
byte of the reconstructed original game is relocatable or understood.

## Findings and corrections

- Adder blueprint pointers and vertex/edge/face offsets already used labels.
  The preinitialised station pointer also already followed the Coriolis label.
  These did not need a binary change.
- In Adder builds, `StartupAfterGraphicsCopy` previously used a numerical
  offset into the reclaimed original startup area. It now aliases the actual
  `AdderStartupAfterGraphicsCopy` code. The original slot padding remains two
  zero bytes; its size is checked against the relocated startup's labels.
  The relocated startup's upper bounds use the named reserved region and
  the following attribute data label, not an unexplained numerical address.
- The font source and character lookup already used symbolic references.
  PATCH128 font extraction now reads the immutable reference's copy operands;
  it no longer uses current-build addresses to index the old reference tape.
  Tests use the current symbol map to locate the assembled font and runtime
  glyph storage. `FontRuntime` remains a named fixed workspace below the game
  load boundary, protected by a size/end assertion.
- The single-laser jump already used `DrawLine`. Its `$003F` operand is a pair
  of drawing coordinates, not an address; it is now explicitly named
  `SingleLaserStartCoordinates` to avoid that ambiguity.
- The scanner fix already used labels for its routines, tile tables, glyph
  lookup and variables. Its fixed screen destinations and packed missile text
  coordinates are now named constants with assertions for the shared screen
  page. It still preserves the existing bit rather than forcing a pixel on.
- The missile redraw tail jump now has its own `L_A777` label. The build
  matrix reads that label from the current map instead of embedding its
  previous address. At the time of this audit, the POK exporter also used
  that label and checked the layout against the immutable original tape.
  The exporter has since been removed: POK files target only the original
  128K-compatible release and have no maintained generation scripts.
- Text dispatch tables now expose end/size symbols. Emulator protection
  checks use those sizes, not manually copied table lengths.
- Current-model parsing and ship tests now use current table, geometry and
  runtime-state symbols. The first ship and title-ship test locations are
  derived from the runtime-state base and record-format offsets.
- Graphics, laser and scanner tests distinguish immutable-reference locations
  from current assembled locations. The ROM loader checker reads entry,
  image bounds and font bounds from the current map as well.

Fixed machine memory-map locations, test-only scratch stacks, original-media
coordinates and compatibility assertions are intentionally distinct from
relocatable current code/data references. They are not silently rewritten to
follow a different build when their purpose is to check the original release.
Source regeneration preserves all of the symbolic changes above.

## Verification

The before/after option matrices produced identical TAP SHA-256 values for
all 64 combinations. No executable bytes, data bytes, load addresses, payload
sizes or memory consumption changed. The scanner-only POK is also identical.
Default strict verification still reproduces the original tape.

```text
python tools/check_build_options.py
python tools/check_variant_relocation.py
python tools/check_ship_variant.py
python tools/check_graphics.py
python tools/check_laser_variant.py
python tools/check_scanner_pixel_fix.py
python tools/run_runtime_scenarios.py docked-baseline docked-equipment inflight-screens hyperspace-diso
```

`check_variant_relocation.py` assembles the actual optional ASM includes into
four disposable fixtures with two different origins/layouts and both fonts.
It executes the startup copies, observes the laser's relocated target and
parameters, verifies Adder geometry offsets and compares all scanner pixels
in 32 cases. Startup/line-renderer external calls are test stubs here; the
full routines and real rendering are covered by the separate game tests.
The fixture test does not weaken normal game bounds or alter the release.

The game tests cover all 19 object loaders, 128 actual Adder rendered frames,
all 91 glyphs in each font, 256 RNG states in each laser mode, 1,536 indicator
cases per font, all five missile counts and ROM-loaded first launch with
ECM off/on/off. All emulator tests use ZX Spectrum 48K and the supplied 48K ROM.
They are regressions, not a full playthrough or a physical-hardware test.

Assembler: Z80 Macro Assembler 23854-4d530b6eb7-20251002.
The six TAP blocks retain payloads of 130, 6,912 and 40,801 bytes. Game origin
is `$6048`, entry `$7000`, exclusive end `$FFA9`; total TAP size is 47,918 bytes.
Additional memory used by this refactor: **0 bytes**.

Explicit game builds used for the regressions and final delivery:

```bat
make.bat
verify.bat
make.bat ship=krait laser=original font=128 scannerpixelfix=yes stationrandomlaunchfix=no verify=no
make.bat ship=adder laser=single font=48 scannerpixelfix=yes stationrandomlaunchfix=yes verify=no
```

The final combined TAP SHA-256 remains
`7870da8e9ee44bee00a24b06698b0482a676419d893f7a09996f495a92d93893`.
Default strict verification passes; modified builds require explicit
`verify=no` and still pass all structural checks. BAT settings were preserved.
No commit or push was performed.

Detailed before/after hashes, changed-file manifest and temporary relocation
fixtures are recorded under `build/address-audit/`. They are disposable.
