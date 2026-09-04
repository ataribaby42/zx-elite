# ZX Elite model geometry compared with C64 and BBC sources

## Result

All 17 distinct shapes covered here have the same vertex count and undirected
edge endpoints as their C64 counterparts. Of 231 vertex triples, 230 are
identical without rotation, axis swapping, rescaling or reindexing. The only
coordinate change is Thargon vertex 3: ZX `(-9,25,-32)` versus C64/BBC
`(-9,24,-32)`. The default ZX release has 16 distinct shapes; the seventeenth
is the original side-B Adder.

Some face normals, visibility fields, a face association and one normal-scaling
field differ. Thus equal coordinates do not prove equal hidden-line behaviour.
The comparison covers all 19 default ZX records and the original Adder with
18 vertices, 29 edges and 15 normals. The optional compact Adder is not used.
Rock hermit shares Asteroid geometry; trader/pirate Python and trader/pirate
Cobra records also share their respective geometry.

## Sources and evidence

ZX data come from structurally validated `assets/Elite - 128k.tap`, zero-based
data block 5, load `$6048`, with blueprints scoped to `$6180..$6FFF`. The file
is 47,918 bytes, SHA-256
`d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6`.
The six payload lengths are 17, 130, 17, 6912, 17 and 40801 bytes. Adder comes
from the validated final data block of `assets/Elite+48K+fixed+B+-+Adder.tap`,
load `$4000`.

The external references are Mark Moxon's documented source/disassembly
repositories, pinned as follows:

| Platform | Revision | Source scope |
|---|---|---|
| [C64](https://github.com/markmoxon/elite-source-code-commodore-64) | `448b7fadf67510c1302676b211c5ba9551a9c66a` | `1-source-files/main-sources/elite-data.asm`; unconditional geometry |
| [BBC Micro disc](https://github.com/markmoxon/elite-source-code-bbc-micro-disc) | `a18269cfd71a4721fa30ae13ff4cbf97cafd3c1b` | `elite-ships-a.asm` through `elite-ships-p.asm` and `elite-missile.asm`; STH / Ian Bell disc branch |
| [BBC Micro cassette](https://github.com/markmoxon/elite-source-code-bbc-micro-cassette) | `019e1ccc315d89db2148e480d10011e2c4180a39` | `elite-source.asm`; unconditional geometry |

BBC Master, 6502 Second Processor, Electron, NES and the unreleased BBC SRAM
variant are not conflated with these versions. Repeated geometry in the BBC
disc ship banks is checked for agreement. The separate docked-screen
demonstration model is outside this flight-model comparison.

- [Every vertex and every field difference](generated/ship-comparison.md)
- [Coordinates, edges, normals and source locations as JSON](generated/ship-comparison.json)
- [Atlas of all 17 shapes](generated/ship-comparison.png)

The atlas overlays ZX and C64 at the same scale for each pair, with each model
fitted independently. It shows oblique and X/Z plan views with all edges,
including back edges. These are orthographic diagrams, not game screenshots;
they demonstrate shape equality, not normal-based hiding or distance culling.

## Every model

"Same" covers coordinates, undirected edge endpoints, face associations,
visibility fields, declared normals and normal-scaling control. All matching
references have identical edge endpoints. Counts are vertices/edges/normals.

| ZX ID | Model | Counts | C64 | BBC disc | BBC cassette |
|---:|---|---|---|---|---|
| 0 | Coriolis station | 16/28/14 | Same | Same | Same |
| 1 | Missile | 17/24/9 | Same | Same shape; two normal records differ | Same |
| 2 | Escape capsule | 4/6/4 | Same | Same | Same shape; normal magnitudes and scale differ |
| 3 | Alloy plate | 4/4/0 | Same shape; ZX omits dummy zero normal | Same as C64 | Absent |
| 4 | Cargo canister | 10/15/7 | Same | Same | Same |
| 5 | Splinter | 4/6/4 | Same shape; four declared normals differ; pointer caveat below | Same as C64 | Absent |
| 6 | Asteroid | 9/21/14 | Same | Same | Same |
| 7 | Rock hermit | 9/21/14 | Same | No separate declaration; Asteroid shape matches | No separate declaration; Asteroid shape matches |
| 8 | Viper | 15/20/7 | Same | Same | Same |
| 9 | Cobra Mk III, trader | 28/38/13 | Same | Same | Same |
| 10 | Python, trader | 11/26/13 | Same shape; four edge visibility values differ | Same as C64 | Same shape; more visibility differences |
| 11 | Python, pirate | 11/26/13 | Same shape; four edge visibility values differ | Same as C64 | Single Python used for comparison; more visibility differences |
| 12 | Cobra Mk III, pirate | 28/38/13 | Same shape; ZX normal scale 10 instead of 1 | Same as C64 | Single Cobra used for comparison; scale differs |
| 13 | Asp Mk II | 19/28/12 | Same | Same | Absent |
| 14 | Fer-de-Lance | 19/27/10 | Same shape; one normal component differs | Same as C64 | Absent |
| 15 | Thargoid | 20/26/10 | Same | Same | Same |
| 16 | Sidewinder | 10/15/7 | Same | Same | Same |
| 17 | Krait | 17/21/6 | Same | Same | Absent |
| 18 | Thargon | 10/15/7 | One coordinate and one edge-face association differ | Same as C64 | Same as C64 |
| 17, side B | Adder | 18/29/15 | Same | Same | Absent |

"No separate declaration" for Rock hermit is not a claim about all BBC game
logic; its shape is compared separately through Asteroid. BBC cassette has
only one corresponding Python and Cobra blueprint, not two role records.

## Exact differences and their visual implications

### Thargon

Vertex numbering starts at zero. Vertex 3 is `(-9,25,-32)` on ZX and
`(-9,24,-32)` in all three references. Its incident edges are 2, 3 and 13.
Vertex 2 still has Y=-24, so the one-unit change introduces a slight asymmetry.
The total Y extent remains -38 to +38. No other vertex changes.

Edge 11 still joins vertices 1 and 6, but its adjacent faces are `{1,6}`
on ZX versus `{2,6}` in all three references. Normals are identical.
The 6502 version shares Canister edges; ZX stores a dedicated edge table.

INFERRED: a very small contour change at sufficiently large screen size,
plus a possible change in when edge 11 is hidden. The hiding change is
separate from the vertex displacement.

### Python, both records

Against C64/BBC disc, edges 12, 13, 14 and 15 have visibility 9 on ZX versus 7.
These are surface detail lines with identical adjacent face indices, rather
than boundaries between different faces. BBC cassette uses 5 for them and
also has lower thresholds for five vertices, another sixteen edges, and all
thirteen faces. All coordinates, edge connections and normal directions match.

INFERRED: the same hull and proportions, with detail disappearing at different
distances. These numeric fields are not converted into equal cross-platform
world distances; that also depends on each renderer and projection.

### Cobra Mk III pirate

ZX pirate header `$64A7` has 10 (`$0A`) at +19, versus 1 in the trader header
and in the C64/BBC references. All 28 vertices, 38 edges, 13 normals and their
visibility/association fields match. This is not a larger hull.

Verified ZX code at `$E93A` reads header +19 into `$E919`; `$EA1C..$EA28`
uses it in normal-based visibility calculations. The comparison asserts the
original instruction bytes before decoding the field.

INFERRED: the near-field hidden-face calculation can differ. No measured
screen difference or historical intent is claimed here.

### Fer-de-Lance

Face 8 is `(12,46,-22)` on ZX versus `(12,46,-19)` on C64/BBC disc.
Visibility remains 28. All vertices, edges and other normals match.
INFERRED: a small change to the viewing-angle boundary at which associated
edges are hidden, without a change to the hull itself.

### Splinter

All four vertices and six edges match. The declared normals are:

| Face | ZX | C64 / BBC disc declaration |
|---:|---|---|
| 0 | `(177,12,-148)` | `(35,0,4)` |
| 1 | `(100,-25,213)` | `(3,4,8)` |
| 2 | `(-202,104,-34)` | `(1,8,12)` |
| 3 | `(-2,-51,-74)` | `(18,12,0)` |

These are not positive rescalings of the same vectors. Both reference sources
also encode the low face pointer as
`LO(SHIP_SPLINTER_FACES - SHIP_SPLINTER) + 24`, with no such addition to
the high part. The nominal `_FACES` declarations must therefore not be
presented as proof of the normals actually read by the C64/BBC renderer.
The low-byte-only offset also introduces an address-carry caveat. This
comparison records the expression without silently correcting it.

INFERRED: unchanged tetrahedron shape but potentially substantial differences
in hidden-edge behaviour. Exact runtime effects of the reference pointer
need separate execution checks; the atlas shows all edges deliberately.

### Missile

ZX matches C64 and BBC cassette. In the STH/Ian Bell BBC disc branch,
face 7 is `(0,160,110)` rather than ZX `(0,32,0)`, and face 8 is `(0,64,4)`
with visibility 0 rather than `(0,0,-176)` with visibility 31. The unreleased
SRAM branch has the ZX/C64 normal records instead. The hull is unchanged.

### Escape capsule

C64/BBC disc match ZX. BBC cassette normals are `(26,0,-61)`, `(19,51,15)`,
`(19,-51,15)`, `(-56,0,0)` at scale 3. ZX has `(52,0,-122)`, `(39,103,30)`,
`(39,-103,30)`, `(-112,0,0)` at scale 4. Two are exact doubles and two are
approximately doubled, with rounding differences. This is normal precision
and representation, not a bigger capsule. All vertices and edges match.

### Alloy plate

C64/BBC disc declare one zero normal with visibility 0; ZX has no normals
and a null face pointer. The vertices and edges use face sentinel 15.
The four-point geometry is identical. ZX explicitly handles zero faces at
`$E940..$E94C`.

## Correction to the legacy ZX field annotation

The old `analyze_ship_blueprints.py` JSON key `normal_scale` and generated
ASM comment at header +22 are misleading: they expose byte 22. The renderer
uses **byte 19** for normal scaling. This comparator reads byte 19 directly.
The maintained SHIPS.md format table is corrected. Renaming legacy generator
fields and regenerating ASM comments are outside this geometry investigation;
no game source/data were modified.

Header +21/+22 is read as a word at `$DB53..$DB56`, shifted right and passed
to `$A8EE` at `$DB5D`. It must not be interpreted as a geometry scale.
This evidence comes from ZX instructions, not the 6502 layout.

## Regeneration and checks

Run from the project root. Create these disposable checkouts if missing:

```powershell
git clone https://github.com/markmoxon/elite-source-code-commodore-64.git build/ship-comparison/c64
git clone https://github.com/markmoxon/elite-source-code-bbc-micro-disc.git build/ship-comparison/bbc-disc
git clone https://github.com/markmoxon/elite-source-code-bbc-micro-cassette.git build/ship-comparison/bbc-cassette
git -C build/ship-comparison/c64 checkout --detach 448b7fadf67510c1302676b211c5ba9551a9c66a
git -C build/ship-comparison/bbc-disc checkout --detach a18269cfd71a4721fa30ae13ff4cbf97cafd3c1b
git -C build/ship-comparison/bbc-cassette checkout --detach 019e1ccc315d89db2148e480d10011e2c4180a39
python tools/compare_ship_geometry.py
python tools/compare_ship_geometry.py --render
```

Only `--render` needs Pillow. The script checks pinned revisions, repeated
geometry, unexpected geometry conditionals, all edge/face indices and TAP
framing/checksums. It retains all compared data and exact source locations.

The investigation cloned these revisions using `--depth 1`. Actual render
command, using the bundled Python with Pillow:

```powershell
& 'C:/Users/atari/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/compare_ship_geometry.py --render
git diff --check
git status --short --branch
```

The reports and atlas were regenerated twice and hashes compared for
determinism; the atlas was visually reviewed. No assembler or emulator was
run, and no release TAP was rebuilt. Thus there is no new z88dk version,
release hash or emulator pixel-identity result. Original reference SHA and
TAP structure were verified during extraction. No source classification or
remaining unlabelled regions changed. No commit or push was performed.
