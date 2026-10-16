# Disassembly conventions and annotation database

`src/game.asm` and the data includes in `src/data/` are generated, reviewable
assembler source. They are produced by `tools/bootstrap_sources.py` from the
immutable reference tape, control-flow analysis, recorded 48K runtime
evidence and the annotation database in `tools/annotations/`. Normal builds
never regenerate source; regeneration is a deliberate step:

```bat
python tools\bootstrap_sources.py --force
make.bat
verify.bat
```

Regeneration overwrites `src/game.asm` and the generated data includes, so
lasting improvements belong in the annotation database, not in the
generated files. The hand-maintained optional modules (`src/options.asm`,
`src/scanner-pixel-fix.asm`, `src/station-random-launch-fix.asm`,
`src/station-slot-fix.asm`, `src/fuel-fix.asm`, `src/ai-courage-fix.asm`,
`src/scanner-blip-fix.asm`, `src/stardust-fix.asm`, `src/text-full-stop-fix.asm`,
`src/iff-unit.asm`, `src/single-laser.asm`, `src/adder-startup.asm`) are never generated.

## Reading the source

Every instruction line ends with a comment that starts with the original
reference address and bytes, followed by an optional explanation:

```asm
    CALL PrintInlineToken                      ; $AF9A: CD 99 BA
    defb $20                                   ; $AF9D: 20  PrintInlineToken argument: " "
    LD A,$09                                   ; $736F: 3E 09  message 9: " GAME OVER"
```

- `VERIFIED:` marks meanings proved by instruction semantics, runtime
  evidence, a test or a verified data format. Only verified labels have
  descriptive names.
- `INFERRED:` marks a hypothesis; its label stays neutral (`L_xxxx`, the
  original address) until the hypothesis is proved.
- `UNCLASSIFIED:` marks bytes that have no proved code or data role yet.
  They remain explicit `defb` source.
- Section banners (`; ====`) group routines into subsystems.
- Bytes that a routine reads through its return address are emitted as
  inline `defb` arguments after the `CALL` (for example
  `PrintInlineToken` and `SetTextColumnInline`). Earlier linear decoding
  had misread several of them as instructions.
- Text codes loaded into `A` before a text routine call, inline text
  arguments, the message table and the token dictionary carry decoded text
  comments. `{name}` denotes a control code and `{a|b|c|d|e}` one of five
  randomly chosen messages. Case conversion is not shown.
- Labels inside an instruction (self-modified operands) are emitted as
  `defc Name = Instruction + offset`, so they move with the code.
- A label that only exists in the original code path of an optional
  modification is defined only when that option is off.
- The end of `game.asm` lists `defc L_xxxx = Name` aliases for every named
  label. Older notes and analysis tools may keep using the neutral names.

## Annotation database

`tools/annotations/__init__.py` documents the schema. Each module covers one
subsystem or address range; the loader rejects a second definition of the
same address. Keys are reference addresses (TAP block 5), never addresses to
copy into source: emitted source always uses labels.

| Dictionary | Purpose |
|---|---|
| `LABELS` | Name (verified only), status and block comment of an address |
| `COMMENTS` | End-of-line comment for one instruction or data line |
| `SECTIONS` | Subsystem banner before an address |
| `DATA` | Typed data in `game.asm`: bytes, words, pointers, text, zeros, stack |
| `INLINE` | Routines followed by inline argument bytes |
| `CONSTANTS` | 16-bit immediates that are numbers although they look like addresses |
| `OPERANDS` | Symbolic operand expressions (structure offsets, table pages) |
| `SEEDS`, `NORETURN`, `STOPS` | Control-flow facts the static decoder cannot see |
| `TEXTCALLS`, `TEXTNAMES` | Text-code arguments and control-code names for comments |
| `FIELDS` | Named structure offsets and format constants |
| `ASSERTS` | Layout constraints, such as page alignment of lookup tables |

`tools/verified_annotations.py` keeps the earlier verified registry used by
`tools/check_bounty_hunters.py`; the generator merges both.

The generator checks the database while it runs: names are unique and
verified, operand expressions evaluate to the original operand, pointer
tables contain image addresses, annotated data is never executed by a
proved code path, and every inline-argument call is unconditional. The
default build then proves byte identity, and the option matrix proves that
modified builds are unchanged by annotation work.

## Evidence tools

| Tool | Output | Use |
|---|---|---|
| `tools/trace_xrefs.py` | `docs/generated/runtime-xrefs.json` | 48K gameplay scenarios with every RAM read and write attributed to the instruction that made it |
| `tools/xref_listing.py` | `build/analysis/game-xref.asm` | Generated source with static and runtime cross-references after each label |
| `tools/text_codec.py` | comments | Decodes the token dictionary and message table |
| `tools/check_core_routines.py` | `build/core-routines-check/` | Exhaustive checks of the shared arithmetic helpers |
| `tools/check_routines.py` | `build/routine-checks/` | Simulator checks behind the verified routine meanings ([list](ROUTINE-CHECKS.md)) |
| `tools/compare_skool.py` | `docs/generated/skool-comparison.json` | Comparison with an external SkoolKit disassembly ([report](COMPARISON-SKOOLKIT.md)) |

`trace_xrefs.py` reuses the scenarios of `tools/run_runtime_scenarios.py`
and adds flight, combat, equipment and menu scenarios. Equipment for those
scenarios is granted by documented test pokes into the active commander
record after normal start-up; game code is never patched. The traces are
regenerated in seconds:

```bat
python tools\trace_xrefs.py
python tools\xref_listing.py
```

`docs/generated/` is ignored by Git and can always be regenerated.

## Relocation rules

Annotated operands keep the code relocatable:

- table pages are expressed from their labels, for example
  `LD H,SquareLookupTables >> 8`, with assertions that the tables stay
  page-aligned;
- the IM 2 vector table and its fixed `$FEFE` entry are asserted;
- pointer tables in data, including the destinations of self-modifying
  patch tables, are emitted as `defw Label`;
- reviewed numeric immediates whose value only happens to lie in the image
  range (bit patterns, coordinates, sizes) are emitted as numbers.

Every 16-bit immediate whose value lies in the image range was reviewed
during the annotation pass. Those still emitted as plain labels are genuine
addresses; `docs/generated/reconstruction.json` lists them under
`label_immediates_list`. New code found later (for example through new
runtime seeds) must have its immediates reviewed in the same way.

## Workflow for further analysis

1. Build the default release and run `tools/trace_xrefs.py` (add a scenario
   to `EXTRA_SCENARIOS` when a game feature is not yet covered), then
   `tools/xref_listing.py`.
2. Read `build/analysis/game-xref.asm` for the routine, its callers, and its
   static and runtime readers and writers.
3. Prove the meaning: by unambiguous instruction semantics, a runtime trace,
   or a simulator test added to `tools/check_routines.py`.
4. Record the result in the module of `tools/annotations/` that covers the
   address. Use a descriptive name only when the status is `verified`.
5. Regenerate, then run `make.bat`, `verify.bat`, the relevant checks and,
   when operands or data types changed, the option matrix
   (`tools/check_build_options.py`).

## Module ownership

| Module | Area |
|---|---|
| `text.py`, `core.py`, `objects.py` | Shared vocabulary: text output, arithmetic, interrupts, object instances |
| `r1_7000.py` | Variables, start-up, main loop, flight and projection `$7000..$7BFF` |
| `r2_7c00.py` | Circle renderer and its patch tables `$7C00..$85FF` |
| `r3_8600.py` | Circle arcs, scanner, compass, screen keys, sound `$8600..$91FF` |
| `r4_9200.py` | Energy bomb, torus jump, stardust, dashboard maths `$9200..$A3FF` |
| `r5_a400.py` | Cockpit indicators, commander record, charts, market `$A400..$AFFF` |
| `r6_b000.py` | Text controls, trading screens, number printing, screen frame `$B000..$BDFF` |
| `r7_be00.py` | Dormant region, status and access menu, tape transfer `$BE00..$D3FF` |
| `r8_d400.py` | Messages, hyperspace, missions, pirates, object update, vectors `$D400..$DFFF` |
| `r9_e000.py` | 3D renderer and arithmetic `$E000..$EBFF` |
| `r10_ec00.py` | Lasers, random numbers, line drawing, object creation `$EC00..$F3FF` |
| `r11_f400.py` | Launches, AI, encounters, input, interrupt handler `$F400..$FFA8` |
| `dormant.py`, `integration.py` | Dormant loader; cross-range operands and comments |
