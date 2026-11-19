# Docking roll alignment

`dockingrotation=no` is the default. With `yes`, manual docking also requires
the long side of the slot to be approximately horizontal. Both upright and
upside-down approaches fit; a quarter-turn does not. A failed roll check
uses the original scrape path: sound request bit 6 and front damage
`12 + 2*PlayerSpeed` on every contact update. Repeated scraping can destroy
the ship. The existing position, nose-direction, hostility and approach-angle
checks remain in force. This option adds roll alignment only; it does not
replace the ZX collision box with a detailed geometric slot collision model.

The C-key docking computer and escape-pod docking bypass the manual contact
path and remain unchanged. Selecting another cockpit view does not change
the decision. The test runs only when the original code would have granted
manual docking, adding no work to ordinary flight without eligible contact.

## Why this axis and threshold

The authoritative ZX Coriolis model has slot vertices 12..15 at
`(x,y,z)=(+/-10,+/-30,160)`, so local Y is the slot's long axis. Its horizontal
component is the high byte of `InstanceAxisY`'s x component, with bit 7
holding the sign. Acceptance is `(roof_x_high & 127) >= 106`.
For a unit vector of magnitude `$7FFF` this accepts roughly 34 degrees from
horizontal; byte quantization and an oblique approach affect the angular
boundary. The threshold is deliberately generous, in the spirit of the
[BBC docking roll check](https://elite.bbcelite.com/master/main/subroutine/main_flight_loop_part_9_of_16.html).
That version checks its own roof-vector horizontal component against 80;
its orientation scale and collision rules differ. No BBC/C64 addresses,
structure layouts or routines are copied into the ZX source.

## Storage and dependency

The option automatically enables only `competitionremove=yes`, even if
removal was explicitly requested as `no`. Both `rotationdriftfix` and
`stationslotfix` remain independent. Build metadata records requested and
effective settings. Direct assembly uses the same implied defaults and
rejects an explicit `COMPETITION_REMOVE=0` conflict.

With rotation repair off, the 18-byte helper fits entirely in reclaimed
competition code and leaves **87 bytes** free. The original position arithmetic
is unchanged. When both options are enabled, the six-byte success tail moves
into rotation padding, retaining the existing combined build byte for byte.

| Fixed range, inclusive | Capacity | Docking use |
|---|---:|---|
| `$EB0A..$EB0F` | 6 B | Replace the original success tail with a call, conditional scrape and return |
| `$D3DD..$D3E1` | 5 B | Load the station roof's horizontal component and jump to the comparison |
| `$D3F7..$D3FE` | 8 B | Sign removal, threshold, failure return and success jump; 1 B remains |
| `$D388..$D38D` without rotation repair, or `$DF05..$DF0A` with it | 6 B | Set `DockingContactFlag=1` and return |

Only **one byte at `$D3FE` remains free** in these rotation-fix gaps when both
options are enabled. No new data variable, table, persistent record or image
space is allocated. The helper uses one two-byte return address on the
existing stack during contact; it adds no nested calls. Original register
requirements are preserved; AF changes, and the following `DrawObjectInView`
overwrites A and flags before using them. All targets and field references
are symbolic, and every region is bounded by assembler assertions.

The generator owns the six-byte conditional hook. The three helper macros
are nested in competition-removal padding or rotation padding, according to
the selected layout. The option checker permits only these exact overlaps
and proves that the active parent build contains zeros there.
It also verifies all eight requested competition/rotation/docking states.

## Build and checks

```bat
make.bat dockingrotation=yes rotationdriftfix=no competitionremove=no verify=no
python tools\check_docking_rotation.py --emulator
python tools\check_competition_remove.py
make.bat ship=adder dockingrotation=yes verify=no
python tools\check_docking_rotation.py --emulator
make.bat dockingrotation=yes rotationdriftfix=yes verify=no
python tools\check_docking_rotation.py --emulator
python tools\check_rotation_drift_fix.py
```

`tools/check_docking_rotation.py` uses **ZX Spectrum 48K** and
`assets/zxspectrum48k.rom`. The routine checks cover 1,024 combinations of
all signed component bytes, fractional extremes and speed extremes; 360
roll angles in each of four views; 36 unchanged earlier rejection cases;
108 other-object contacts; 50 scooping cases; and three docking-computer cases.
It verifies the slot axis against the current blueprint and the sign-magnitude
threshold against an independent integer model. Only the original six-byte
success tail is restored for the comparison image, preserving all other options.
With rotation repair off, the check also compares the complete position-motion
code against the reference bytes.

The ROM-load scenarios launch and place a controlled station in contact with
the player, retaining its natural rotation and survival flag. Horizontal and
inverted approaches dock; a vertical approach scrapes and loses front shield;
the same vertical approach docks with the old success tail; and C docks
despite the misalignment. Fixtures are injected at `MainLoop` after the actual
48K ROM load and launch. Each observation follows a whole game update, with
interrupts active. The test stops at the first completed update that reduces
the shield or docks, with a maximum of 32 updates and a timeout on each update.
This avoids both repeated fatal scrapes and the former 0.15-second observation
window, which could stop after damage was queued but before it reached the
shield. The vertical test requires a shield reduction and a clear docking flag;
the computer test requires the actual C-key path. Reports, memory dumps and
final screenshots are regenerated under `build/docking-rotation-check/`.

## Validation of independent options

The dependency split passed `python tools/check_build_options.py`: 130 builds,
all 756 pairs of option values, both docking layouts and all eight requested
competition/rotation/docking states. The complete Cartesian product was not run.
Direct z88dk probes also checked implied defaults, explicit rotation-off,
combined options and rejection of explicit competition-removal conflicts.

The docking ROM-load and save checks passed for Krait and Adder with rotation
repair off, and for Adder with every option enabled. The latter also passed
`python tools/check_rotation_drift_fix.py`. The eight fixtures in
`python tools/check_variant_relocation.py` passed. All emulator checks used
ZX Spectrum 48K with `assets/zxspectrum48k.rom`.

`make.bat` and `verify.bat` still reproduce the reference exactly. Enabling
both docking and rotation repair preserves the previous combined image.
Krait with only docking requested now has TAP SHA256
`074d30b8fd8dbd21656202b3e2af713090b6299e80670b4d3bd862c98022d44f`.
Assembler: z88dk `23854-4d530b6eb7-20251002`; TAP size and all image bounds
remain unchanged. Detailed results from this check are in
`build/docking-dependency-review/`; the maintained commands above regenerate
the feature reports.

## Validation of the initial implementation

The default build passed `make.bat` and `verify.bat` with the reference SHA256
`d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6`.
The targeted default checks were `python tools/check_core_routines.py` and
`python tools/check_routines.py --only contact` (95 contact cases).

`python tools/check_build_options.py` passed 117 builds: 20 individual
non-default selections and 28 combinations covering all 680 value pairs,
all eight dependency states, and all options together. It also checked strict
rejection, stale-release handling, invalid values and corrupt TAPs. This was
the pairwise suite, not the full Cartesian product. Direct assembler probes
matched the Python builder's implied defaults and rejected both explicit
parent conflicts.

`python tools/check_docking_rotation.py --emulator` passed for Krait with
only this option requested and for the matrix's Adder/single/48 build with
every option enabled. Both docked at 0 and 180 degrees, refused 90 degrees
with a front-shield reduction from 160 to 100 in the short contact fixture,
and docked with C. Rotation arithmetic and save regressions also passed in
both builds. `python tools/check_variant_relocation.py` passed its eight
existing isolated fixtures; those cover the older optional modules, while
the new helper's fixed-region bounds are checked during every assembly.

At the initial implementation, the Krait build from
`make.bat dockingrotation=yes verify=no` had TAP SHA256
`0aef4f27c1349c4e74a47e5c904e844210be0fa2ce03d7a3159286945a43a026`.
Assembler: z88dk `23854-4d530b6eb7-20251002`. All builds retain six TAP
blocks (three header/data pairs), payloads 130/6912/40801 bytes, total
47,918 bytes, game origin `$6048` and exclusive end `$FFA9`. Only identity
is disabled for modified builds; metadata, lengths, checksums and bounds
remain mandatory. Source regeneration still reports zero unclassified bytes.
