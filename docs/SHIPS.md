# Ship and object blueprints

## Scope and evidence

The 128K-compatible release stores its complete ship and space-object table at
`$6180..$6FFF`. This release is still a 48K program; the addresses below are in
the normal 48K memory map. The data were identified from the bytes in
`assets/Elite - 128k.tap`, their runtime readers and the two supplied
unprotected 48K comparison TAPs.

The following files settle the Krait/Adder variant question:

- `Elite - 48k - Side A.tzx` describes itself as `With Krait ship`;
- `Elite - 48k - Side B.tzx` describes itself as `With Adder ship`;
- `Elite+48K+fixed+A+-+Krait.tap` contains the same Krait header and geometry
  as blueprint ID 17 in the 128K-compatible release;
- `Elite+48K+fixed+B+-+Adder.tap` places the Adder at blueprint ID 17 instead.

As a separate check, both protected original TZX files were loaded through a
simulated ZX Spectrum 48K ROM tape path. In each case, the resulting
`$6180..$6FFF` memory region was byte-for-byte identical to the corresponding
fixed TAP: Krait on side A and Adder on side B.

The 128K-compatible tape therefore contains the **Krait**, and its two cassette
sides use the same game data. The Adder belongs to side B of the original 48K
release. It is absent from the default reconstruction but can now replace
Krait with `make.bat ship=adder verify=no`. The historical addresses and
counts below describe the original reference, not the modified layout.
See [Build variants](BUILD-VARIANTS.md).

`tools/analyze_ship_blueprints.py` performs these checks directly against the
four supplied comparison files and writes the complete machine-readable result
to `docs/generated/ship-blueprints.json`.

## Blueprint index

`ShipBlueprintTable` contains 19 four-byte entries. Each entry consists of
`$C3`, a little-endian pointer to a 23-byte blueprint header and a group
byte. The loader at `$F2FB` masks the requested ID to six bits, multiplies
it by four and reads the pointer from bytes 1 and 2 of the selected entry.
No instruction reads byte 0 (`$C3`, the opcode of `JP`) or the group byte:
the loader is the only code that addresses the table, the 48K runtime traces
never read those bytes, overwriting them does not change what the loader
creates (check `s1-blueprint-instance-initialisation`), and the `ship=adder`
layout omits both. The group values (0 station and missile, 1 debris and
Asteroid, 2 traders, Viper and Rock hermit, 3 pirates, Asp Mk II,
Fer-de-Lance and Thargoid, 4 Sidewinder, Krait and Thargon) are therefore
only a classification left in the data. "Cargo nibble" is the
low nibble of header byte +0; the game only tests it for zero (see below).

| ID | Ship or object | Header | Vertices / edges / faces | Speed | Energy | Bounty | Cargo nibble | Group |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | Coriolis station | `$6A9D` | 16 / 28 / 14 | 0 | 240 | 0.0 Cr | 0 | 0 |
| 1 | Missile | `$67A6` | 17 / 24 / 9 | 44 | 2 | 0.0 Cr | 0 | 0 |
| 2 | Escape capsule | `$6632` | 4 / 6 / 4 | 8 | 17 | 0.0 Cr | 0 | 1 |
| 3 | Alloy plate | `$68A7` | 4 / 4 / 0 | 16 | 16 | 0.0 Cr | 0 | 1 |
| 4 | Cargo canister | `$63E5` | 10 / 15 / 7 | 15 | 17 | 0.0 Cr | 0 | 1 |
| 5 | Splinter | `$6BBC` | 4 / 6 / 4 | 10 | 20 | 0.0 Cr | 0 | 1 |
| 6 | Asteroid | `$630C` | 9 / 21 / 14 | 30 | 60 | 0.5 Cr | 0 | 1 |
| 7 | Rock hermit | `$62F5` | 9 / 21 / 14 | 30 | 180 | 0.0 Cr | 7 | 2 |
| 8 | Viper | `$6E1B` | 15 / 20 / 7 | 32 | 140 | 0.0 Cr | 0 | 2 |
| 9 | Cobra Mk III, trader record | `$6490` | 28 / 38 / 13 | 28 | 150 | 0.0 Cr | 3 | 2 |
| 10 | Python, trader record | `$68E6` | 11 / 26 / 13 | 20 | 250 | 0.0 Cr | 5 | 2 |
| 11 | Python, pirate record | `$68FD` | 11 / 26 / 13 | 20 | 250 | 20.0 Cr | 2 | 3 |
| 12 | Cobra Mk III, pirate record | `$64A7` | 28 / 38 / 13 | 28 | 150 | 17.5 Cr | 1 | 3 |
| 13 | Asp Mk II | `$61CC` | 19 / 28 / 12 | 40 | 150 | 20.0 Cr | 0 | 3 |
| 14 | Fer-de-Lance | `$6689` | 19 / 27 / 10 | 30 | 160 | 0.0 Cr | 0 | 3 |
| 15 | Thargoid | `$6C13` | 20 / 26 / 10 | 39 | 240 | 50.0 Cr | 0 | 3 |
| 16 | Sidewinder | `$69F2` | 10 / 15 / 7 | 37 | 70 | 5.0 Cr | 0 | 4 |
| 17 | Krait | `$6D32` | 17 / 21 / 6 | 30 | 80 | 10.0 Cr | 1 | 4 |
| 18 | Thargon | `$6EF8` | 10 / 15 / 7 | 30 | 20 | 5.0 Cr | 0 | 4 |

There is one Coriolis station and no Dodo station. Some entries are alternate
gameplay records rather than additional shapes. The Rock hermit points to the
Asteroid vertices, edges and faces. The two Cobra Mk III records share one set
of geometry, as do the two Python records.

See [Fer-de-Lance encounters and legal hostility](BOUNTY-HUNTERS.md) for the
bounty-hunter spawn path, the legal-score threshold and retaliation exceptions.

## Persistent station instance

The station is stored in object slot zero at `InitialRuntimeState` (`$6048`).
Unlike ordinary spawned ships, this slot already contains its blueprint
pointer in the initial image. `StationBlueprintPointer` at slot offset `$23`
(`$606B..$606C`) must point to `ShipCoriolisStationBlueprint`.

The source emits `defw ShipCoriolisStationBlueprint`. In the original layout
that resolves to `$6A9D`; in the current Adder layout it resolves to `$6A77`.
Keeping the original raw bytes after compacting the blueprint table made the
renderer read inside the relocated station's geometry as though it were a
header, producing a tiny dot instead of Coriolis. Testing only the generic
blueprint loader did not cover this preinitialised instance.

`tools/check_ship_variant.py` checks this pointer before and after startup.
The build and full emulator scenarios also validate it. With the corrected
Adder pointer, a deterministic 48K ROM load, launch and rear-view trace
matches the original screen pixel for pixel. The correction replaces the
stored word and requires no extra memory.

## Adder in the 48K side-B variant

The fixed 48K side-B tape puts this record in slot 17:

| Ship | Header | Vertices / edges / faces | Speed | Energy | Bounty | Group |
|---|---:|---:|---:|---:|---:|---:|
| Adder | `$61CC` | 18 / 29 / 15 | 24 | 85 | 4.0 Cr | 4 |

The complete Adder header and geometry remain in the side-B TAP. The analyzer
extracts and validates them without treating the comparison tape as a build
input for the 128K-compatible target.

## Record format

Each blueprint starts with a 23-byte header. Counts and offsets are validated
against the actual geometry boundaries, so malformed or shifted data cause the
analysis to fail. Every field below was identified from the instructions that
read it (reference addresses; `IY` or `HL` holds the header address there).
The header is never written at run time. `tools/check_routines.py` group
`structures` runs these readers in the Z80 simulator.

| Offset | Size | Meaning | Readers |
|---:|---:|---|---|
| `+0` | 1 | Cargo flags: high nibble = scooped commodity - 1; low nibble nonzero = drops a canister when killed | `$EAB5`, `$ECB3`, `$F7D4` |
| `+1` | 1 | Radius: near limit, projected target size and collision/scoop box | `$E02D`, `$EA58`, `$DB38` |
| `+2` | 1 | AI laser fire chance out of 256 | `$FAB3` |
| `+3` | 1 | Vertex count | `$E2F5` |
| `+4` | 1 | Edge count | `$E72F` |
| `+5` | 1 | Face count; zero means no face table | `$E940` |
| `+6` | 1 | Maximum speed | `$F33B`, `$DD7E`, `$DACD` |
| `+7` | 1 | Energy: initial value and regeneration limit | `$F320`, `$F733`, `$F76E`, `$ECBE` |
| `+8` | 2 | Bounty in tenths of a credit, little-endian | `$DB4A`/`$DB4D` |
| `+10` | 1 | Launch flags: bits 0..2 payload count, bits 4..7 launch subtype | `$F32F`, `$F794` |
| `+11` | 1 | Dot distance | `$E112` |
| `+12` | 2 | Vertex-table offset relative to this header | `$E2FA`/`$E2FD` |
| `+14` | 2 | Edge-table offset relative to this header | `$E729`/`$E72C` |
| `+16` | 2 | Face-table offset relative to this header; zero for the alloy plate | `$E92F`/`$E932` |
| `+18` | 1 | Behaviour flags | `$F326`, `$F7DF` |
| `+19` | 1 | Normal scale shift | `$E93A` |
| `+20` | 1 | Gun vertex | `$E1A5` |
| `+21` | 2 | Combat-score award, little-endian | `$DB53`/`$DB56` |

Field details:

- **+0 cargo flags.** When a fuel scoop collects a scoopable object, the
  commodity index is the high nibble plus one: Escape capsule Slaves, Alloy
  plate Alloys, Splinter Minerals, Thargon Alien items. A zero high nibble
  (Cargo canister) gives a random commodity 0..7 (Food..Computers), or the
  cloaking device while `MissionAspEncounterState` is 3. When the player's
  laser destroys an object, a nonzero low nibble creates exactly one Cargo
  canister (event 6); the values 1..7 are not used as a count. A ship below
  one eighth of its energy that passes the random test against instance
  `+$25` and has no escape capsule left drops one canister when the whole
  byte is nonzero.
- **+1 radius.** `DrawObjectInView` draws an object only when its depth
  exceeds the radius and uses 256 x radius / depth as the projected size for
  the crosshair target test. The proximity test at `$EA51` treats an object as
  touching the player when |x|, |y| and |z| are all below the radius (plus 256
  for a missile aimed at the player; 180 for scoopable objects). `$DB38`
  compares it with 30, which no blueprint uses.
- **+2 laser fire chance.** A hostile ship pointing at the player fires only when
  a random byte is below this value; the value is halved while
  `CombatScoreHigh` is zero, that is while the kill count is below 256.
  Range and alignment gates follow.
- **+6 maximum speed.** A new ship starts at half of it. Accelerated speed is
  clamped to it (four times it when behaviour bit 0 is set). Under an energy
  bomb, a value of 39 identifies the Thargoid; the test reads the blueprint of
  the previous slot, see `UpdateObjects`.
- **+7 energy.** Initial energy and regeneration limit (one unit per AI step,
  four when the value is at least `$F0`); the launch and escape decisions use
  half and one eighth of it. For debris after a player kill, at least 85
  gives two Alloy plates and exactly 60 (Asteroid) with mining-laser damage 50
  gives two Splinters.
- **+10 launch flags.** Bits 0..2 are copied to instance `+$20` as the
  payload count, which each successful AI launch decrements. The high nibble
  selects the child: 0 a missile (event 2), otherwise event 4 with subtype
  1 Viper, 2 Cobra Mk III or Python trader, 3 Thargon, 4 Thargoid,
  5 Sidewinder or slot 17. The Rock hermit (`$52`) launches up to two
  fighters and the Thargoid (`$36`) up to six Thargons. Bit 3 is clear in
  every record. The station's `$06` is never loaded: slot 0 is not created by
  `InitialiseShipFromBlueprint` and its initial `+$20` holds no payload.
- **+11 dot distance.** The wireframe is drawn while the high byte of the
  depth is below this value; farther away the object is a 2 x 2 dot.
- **+18 behaviour flags.** `+$12 AND $6F` becomes instance `+$21` and bit 7
  becomes instance `+$20` bit 7. Bit 0 quadruples the speed limit (Escape
  capsule, Rock hermit). Bit 1 makes the ship hostile when the legal score is
  at least 40 (Viper, Fer-de-Lance). Bit 2 is hostility. Bit 3 makes a hostile
  ship take the steer-away branch while a station is present (except in
  mission state 4). Bits 5 and 6
  are tested together: killing such a ship sets legal-score bit 6, and a
  hostile one raises the shared alert (bit 5: traders and Rock hermit; bit 6:
  Viper). Bit 4 is masked off and clear in every record. Bit 7 means an
  escape capsule is on board. The exact value 4 (Thargon) selects the test
  that leaves Thargons inert when no Thargoid remains.
- **+19 normal scale shift.** Rotated face normals are multiplied by 2/2^n
  before being added to the object position in the face test.
- **+20 gun vertex.** The vertex from which an AI laser beam is drawn; it is
  below the vertex count in every record.
- **+21 combat-score award.** Half of this word is added to the 24-bit combat
  score, so a kill raises the kill count (`CombatScoreLow`/`CombatScoreHigh`)
  by word / 512: for example 4 for a Thargoid (`$0800`), 1.75 for a pirate
  Python or Cobra Mk III (`$0380`) and 0.5 for a Sidewinder or Krait
  (`$0100`).

Vertices use six bytes each; edges and face normals use four bytes each:

| Record | Byte | Meaning | Readers |
|---|---:|---|---|
| Vertex | 0..2 | Magnitudes of x, y and z | `RotateRow`, `RotateRowPrecise` |
| Vertex | 3 | Bits 7, 6 and 5: signs of x, y and z; bits 0..4: visibility threshold | `$E30F`, `RotateRow` |
| Vertex | 4, 5 | Four face numbers, one per nibble | `$E31F`, `$E327` |
| Edge | 0 | Visibility threshold (whole byte) | `$E739` |
| Edge | 1, 2 | Vertex numbers of the two ends | `$E74F`, `$E759` |
| Edge | 3 | Two face numbers, one per nibble | `$E747` |
| Face | 0..2 | Magnitudes of the normal's x, y and z | `RotateRow` via `ComputeFaceAxis` |
| Face | 3 | Bits 7, 6 and 5: signs; bits 0..4: visibility threshold | `$E950`, `RotateRow` |

The detail level is min(`$1F`, high byte of 2 x depth) - 2. A vertex, edge or
face is used only while the detail level is below its threshold; `$1F` means
always. A vertex is projected and an edge drawn only when at least one of
their faces is visible (an edge also needs both ends in front of the view).
Face number 15 never names a stored face: its entry in `FaceVisibilityFlags`
stays 1, so 15 means "always visible". The alloy plate has no faces;
`ComputeFaceVisibility` then sets only face 0 visible, and all its vertex and
edge face numbers are 15.

See [Cross-platform model comparison](SHIP-COMPARISON.md) for every vertex
and the differences from the C64 and BBC sources. Its code evidence corrected
the old analyzer name `normal_scale` for header byte +22; the analyzer now
names byte +19 `normal_scale_shift` and the word at +21 `combat_score_award`.

## Asteroid mining and the missing Boulder

There is no separate Boulder blueprint in this release. Blueprint ID 5 is a
four-vertex, six-edge, four-face **Splinter**. The special destruction path at
`$ECB3..$ECD3` tests for an energy value of `$3C` (the Asteroid's 60 energy)
and laser value `$32`, dispatches event 8, and reaches `$F5B0`. That routine
creates blueprint ID 5 twice.

The ZX version therefore breaks a mined Asteroid directly into two Splinters.
It does not implement an intermediate, separately modelled Boulder stage.

## Source organization

The buildable definitions are in
`src/data/ship-blueprints-and-tables.asm`. Every table pointer and
every geometry offset is an assembler expression derived from labels. The file
also asserts the table size, each 23-byte header, all vertex/edge/face lengths,
the text-dispatch table sizes and the complete `$6180..$6FFF` region size.

The pointers following ship geometry are **text/control-token handler
pointers**, not ship AI dispatch data. `$B89F` indexes the first 14 entries;
`$B89A` indexes the following 32. They are now isolated in
`text-dispatch-first.asm` and `text-dispatch-second.asm`, with symbolic code
targets. The Adder variant relocates only the first group.

`src/data/adder.asm` contains the optional replacement. It retains
the original Adder's vertices, edges, properties and visibility rules while
sharing its three identical face normals. There are 13 stored normals rather
than 15; all vertex and edge references are remapped. This saves eight bytes
without changing rendering, as checked by the actual Z80 renderer.

`src/data/adder-original.asm` preserves the complete **unmodified
48K side-B model**: 307 bytes, 18 vertices, 29 edges and 15 face normals, with
the original face indices. It is a reference alternative, not included in
the game build. Both files use the same `ShipAdder...` labels, so include only
one at a time. The original needs eight more bytes than the selected compact
model and cannot be substituted into the current full layout without making
room. Both alternatives are reproduced by the source generator.

The original include was assembled independently at origins `$0000` and
`$61CC`. In both cases all 307 bytes matched the side-B TAP and the existing
ROM-loaded original side-B TZX snapshot. Its binary SHA-256 is
`4d34afa22633aafec3d5fb422261e9bd6531e2175b1934dca05e1bc1b3af0317`.
Retaining this unlinked source does not change the release TAP or memory use.

Run:

```bat
python tools\analyze_ship_blueprints.py --write-source
build.bat
verify.bat
```

The analysis does not modify any supplied tape. Regenerating the source must
still produce the byte-identical 128K-compatible TAP.
