# Comparison with the SkoolKit disassembly by nzeemin

This page compares this project's annotated source with an independent
disassembly of the same release:
[nzeemin/skoolkit-game-revs](https://github.com/nzeemin/skoolkit-game-revs),
directory `elite128-zx`, commit `be2aee67909433c724c79129f2e845deab9e3f08`
(2026-09-24). Its README credits earlier work by LW.

That repository has no licence file. Its text is therefore not copied into
this project. It was used only as a cross-check, and every change made after
the comparison rests on this project's own evidence. To reproduce the
comparison, regenerate the source, then run:

```bat
python tools\compare_skool.py path\to\skoolkit-game-revs\elite128-zx\elite.skool
```

The tool writes `docs/generated/skool-comparison.json`.

## Same release

The external disassembly targets the same memory layout. For example:

- the 19-entry blueprint table is at `$6180`, with the Coriolis blueprint at `$6A9D`;
- the dispatch tables are at `$6FA3` and `$6FBF`;
- the commander record is at `$A816`;
- the IM 2 code is at `$FEFE`.

Its instruction boundaries and data blocks line up with this project's
reference image throughout. The differences below therefore concern
interpretation, not bytes.

## Code and data classification

Byte classification of the game image `$6048..$FFA8` (40,801 bytes):

| External / this project | Bytes |
|---|---:|
| code / code | 27,184 |
| data / data | 13,356 |
| data / inline argument | 57 |
| code / inline argument | 4 |
| data / code | 199 |
| code / data | 1 |

The two disassemblies agree on 99.4% of the bytes. Each remaining difference
has a reason:

| Address | External | Here | Resolution |
|---|---|---|---|
| `$B708..$B709` | data | code | Both instructions are executed in the 48K runtime traces, so they are code. |
| `$B3EC`, `$B697`, `$B72F`, `$B8D1` | instructions | inline arguments | These bytes follow `CALL SetTextColumnInline` or `CALL PrintInlineToken`. Those routines pop the return address, read the byte and return after it. The traces execute `$B8D2`, not `$B8D3`, which confirms the boundary. The external decoding at `$B72F` and `$B8D1` shifts the following instruction boundaries (`$B731/$B732`, `$B8D3/$B8D4`). The other 57 argument bytes are data on both sides. |
| `$C350..$C40B` | data | code | `DormantPortLoader`: its prologue relocates exactly the operands of its nine `CALL` instructions, which proves the block is code. It is never executed and is documented as dormant. |
| `$91C9..$91D1` | data | code | Three `JP` instructions to `UseEnergyBomb`, `$9280` and `$9287`. There is no reference to them; the header marks the role as INFERRED. As code, their targets are symbolic. |
| `$B93F` | code | data | A `RET` byte between two text handlers. A check proves that no path reaches it (`text/p6-unreachable-byte`), so it is typed as a data byte. |

The source here contains 14,099 instruction starts, against 13,982 in the
external `.skool`. The extra instructions are mainly the dormant loader.

## Labels

| | Addresses |
|---|---:|
| Descriptive label in both | 344 |
| Only in the external disassembly | 23 |
| Only here | 658 |

The shared addresses describe the same concepts in different words. Examples:

- `ShieldFront` / `ForwardShield`;
- `CompasPointerCrdX` / `CompassDotX`;
- `TablQuadrant` / `LineClipRegionTable`;
- `MatrixRotate` / `RotationMatrix`.

The 23 addresses named only externally are covered here in other ways:

- the 19 ship blueprint headers are named by the ship renderer (`Ship...Blueprint`);
- the cargo-slot and seed sub-addresses are operand expressions such as
  `CargoHold+3` or `GalaxySeeds+2`;
- the remaining two are unreferenced bytes kept with an INFERRED comment.

## Second pass: filling the gaps

After the first comparison, a gap analysis listed every place where the
external `elite.ctl` says something and this project's database did not. That
covered block titles, mid-routine notes, line comments and register notes. It
also listed every INFERRED meaning here for which the external text offers a
claim. Each range of the image was then examined again.

The external text served only as a pointer: each statement was checked
against the instructions, runtime traces or a new simulator check, and
written up in this project's own words. Results:

| Gap | Before | After |
|---|---:|---:|
| Instruction lines with an external comment and none here | 2,993 | 1,658 |
| Blocks with an external title and no header here | 44 | 19 |
| Addresses named only externally | 52 | 23 |
| INFERRED headers here | 43 | 15 |

Line comments in the database rose from 1,978 to 5,745. The remaining 1,658
lines were examined and left without a comment, because a comment would only
restate the instruction or repeat the label next to it. The remaining 19
"blocks" are steps inside routines; they have line comments instead of
separate headers.

`tools/check_routines.py` gained 66 checks (124 in total, 493,754 cases),
which back the upgraded meanings. Among them:

- docking, collision and scooping;
- the explosion state machine;
- the nova and invasion missions;
- the AI laser beam and laser-hit outcomes;
- input, scanner and screen keys;
- the blueprint header fields.

The second pass also found where the external interpretation differs from
the code. For example:

- blueprint byte +2 is the AI laser-fire chance, halved while the combat
  score is below 256, not "unless Elite";
- the special buy screen is the nova refugee offer, not a contraband mission;
- `$DA1A` is set for every object except the station, not "station near";
- `CircleFlags` bits 2/3 are the inverted top bit of a 9-bit offset, not
  "needs clipping";
- a launched ship does not inherit its parent's speed;
- vertex culling tests four faces, not two;
- several screen and sound names are shifted relative to the code that sets
  the requests.

Each analysis kept a list of these disagreements together with the deciding
code.

New original-game behaviour found in this pass is listed in
[findings](FINDINGS.md), for example:

- after any hyperspace key press, docking stays disabled until the next
  arrival;
- the missile-lock release quirk;
- a character lost at the end of a justified line;
- the AI courage counter wrapping on fleeing ships.

## Differences in approach

- **Relocatable source.** This project emits operands as labels and
  expressions. That includes self-modifying patch tables (`CirclePatchTargets`),
  table pages (`SquareLookupTables >> 8`), the dormant loader's relocation
  offsets, and structure fields (`InitialRuntimeState+InstanceBehaviour`).
  Assertions protect fixed layouts. The build options use this to move code
  and data safely.
- **Inline arguments.** Bytes read through the return address are emitted as
  data after their `CALL`, which avoids the boundary errors noted above.
- **Evidence status.** Every header states whether its meaning is verified
  or inferred. Simulator checks in `tools/check_core_routines.py` and
  `tools/check_routines.py` back the verified arithmetic, drawing, text,
  input and mission claims.
- **Comment density.** After the second pass this project has 5,745 line
  comments, plus generated text comments, against about 4,200 external ones.
  It has 1,160 routine and data headers, against 657 external block titles.
