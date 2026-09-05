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
`$C3`, a little-endian pointer to a 23-byte blueprint header and a dispatch
group byte. The loader at `$F2FB` masks the requested ID to six bits, multiplies
it by four and reads the pointer from bytes 1 and 2 of the selected entry.

| ID | Ship or object | Header | Vertices / edges / faces | Speed | Energy | Bounty | Max. canisters | Group |
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
analysis to fail.

| Offset | Size | Meaning |
|---:|---:|---|
| `+0` | 1 | Canister/commodity flags; low nibble is maximum spawned canisters |
| `+1` | 1 | Target size |
| `+2` | 1 | Agility or rotation limit |
| `+3` | 1 | Vertex count |
| `+4` | 1 | Edge count |
| `+5` | 1 | Face count |
| `+6` | 1 | Maximum speed |
| `+7` | 1 | Energy |
| `+8` | 2 | Bounty in tenths of a credit, little-endian |
| `+10` | 1 | Partially decoded property byte |
| `+11` | 1 | Visibility distance |
| `+12` | 2 | Vertex-table offset relative to this header |
| `+14` | 2 | Edge-table offset relative to this header |
| `+16` | 2 | Face-table offset relative to this header; zero for the alloy plate |
| `+18` | 1 | Behaviour flags |
| `+19` | 1 | Normal-scaling control, read at `$E93A`; see SHIP-COMPARISON.md |
| `+20` | 1 | Gun vertex |
| `+21` | 1 | Low byte of the word read at `$DB53..$DB56`, halved and passed to `$A8EE` |
| `+22` | 1 | High byte of that word; not the normal-scaling exponent |

Vertices use six bytes each; edges and face normals use four bytes each. Their
packed bit fields still need field-by-field naming, but their boundaries and
their relationship to each header are verified.

See [Cross-platform model comparison](SHIP-COMPARISON.md) for every vertex
and the differences from the C64 and BBC sources. Its code evidence corrects
the legacy analyzer's misleading `normal_scale` name for header byte +22;
the normal-scaling field is +19.

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
