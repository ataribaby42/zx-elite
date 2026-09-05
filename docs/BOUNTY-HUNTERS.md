# Fer-de-Lance encounters and legal hostility

The ordinary encounter system can spawn a **Fer-de-Lance (blueprint ID 14)
even when the player is Clean**. It starts without hostility. Its AI sets
hostility when the player's legal score reaches **40 decimal (`$28`)**.
The condition is not simply "not Clean".

Among the 19 original blueprints, only **Viper (8)** and **Fer-de-Lance (14)**
have the initial behaviour bit that enables this legal check. Viper is the
police ship. Thus Fer-de-Lance is the only non-police model with this
legal-sensitive behaviour. Calling that its *bounty-hunter role* is an
interpretation of the verified behaviour; there is no separate named
bounty-hunter event or role enumeration in the reconstructed code.

All addresses below describe the immutable `assets/Elite - 128k.tap`, game
payload in zero-based TAP block 5, loaded at `$6048..$FFA8`. This is the
128K-compatible release of the 48K program. Tests use **ZX Spectrum 48K**
with `assets/zxspectrum48k.rom`.

## Spawn path

The ordinary encounter call at `$DA3F..$DA5C` requires the encounter countdown
to reach zero, no station-presence flag, a zero value at `L_7061`, and fewer
than four counted ships. It calls `DispatchShipEvent` with event zero.
The event dispatcher at `$F2CA` reaches `$F61D`.

Within that event, `$F660..$F6A6` applies encounter and government gates and
selects a branch. The mixed single-ship branch at `$F6A9` first calls
`FindFreeShipSlot`. With a free slot, `$F6AD..$F6C6` selects a blueprint
using `NextRandomByte AND $3F`:

| Masked random value | Blueprint | Initial hostility |
|---|---|---|
| 0 | 15: Thargoid | Hostile |
| 1..11 | 14: Fer-de-Lance | Calm, legal-sensitive |
| 12..29 | 13: Asp Mk II | Hostile |
| 30..45 | 12: Cobra Mk III pirate | Hostile |
| 46..63 | 11: Python pirate | Hostile |

The selection proceeds to `InitialiseShipFromBlueprint` at `$F6C8`.
Neither this choice nor the loader tests the player's legal score.
The 11 Fer-de-Lance outcomes out of 64 describe this selector only; they
are not its probability per frame or per encounter attempt, because earlier
gates and correlated RNG calls also apply.

The Fer-de-Lance blueprint at `$6689` has behaviour byte `$82` at header
offset `+$12`. The loader at `$F326..$F32C` masks it with `$6F` and stores
`$02` at instance offset `+$21`: bit 1 set, hostility bit 2 clear.
The later optional bit-0 update at `$F6D6` writes instance byte `+$25`,
not the hostility byte.

Asp, pirate Cobra and pirate Python share the selector with Fer-de-Lance,
but their initial behaviour is `$0C` after masking. They already have the
hostility bit and do not wait for a legal-status check. Their presence in
this selector does not make them alternative legal-sensitive hunters.

## Attack condition and displayed status

The main AI path reaches `$F8A2` through `$F733`, `$F815` and
`TryLaunchStationTraffic` (a non-station immediately leaves that station gate).
The check at `$F8A2..$F8AF` is equivalent to:

```text
if ship.behaviour has bit 1 and player.legal_score >= 40:
    set ship.behaviour bit 2
```

The score is `PlayerLegalScore` (legacy alias `L_A821`), the byte at
commander-record offset 11.
The status screen's `$D0FB..$D107` path uses zero and **50 decimal (`$32`)**
as its display boundaries:

| Legal score | Displayed status | Initially calm Fer-de-Lance becomes hostile from this check |
|---|---|---|
| 0 | Clean | No |
| 1..39 | Offender | No |
| 40..49 | Offender | Yes |
| 50..255 | Fugitive | Yes |

These are code-derived thresholds. The `$30` and `$60` values in the
supplied save-format notes are not the display boundaries; those historical
notes remain unchanged.

For a distant ship, `$F8C8` returns when hostility is clear. With hostility
set, the Fer-de-Lance reaches `$F90B`, which computes a vector towards the
player by reversing the signs of its player-relative coordinates. The
close-distance paths can instead steer away. Hostility therefore enables
combat AI; it does not mean continuous pursuit or firing in every frame.

The firing code also tests hostility explicitly at `$FAA5..$FAA9`.
Facing, range, alignment and random gates still apply before the damage
accumulators are updated at `$FAE7..$FAF5`.

## Why a Clean player can still be attacked

The legal check is only one way to set hostility:

- A player laser hit sets bit 2 unconditionally at `$EC55`, before applying
  damage. A surviving Fer-de-Lance can retaliate even if the score is zero.
- `$DAD8..$DAF6` spreads a shared alert (`L_DA14`) to ships. An already
  hostile instance with behaviour bits `$20` or `$40` raises that alert;
  trader records and Viper have those bits. Thus provoking another ship
  can also make a calm Fer-de-Lance hostile.
- The same update sets hostility while `L_617B` is nonzero. That address is
  the energy field of slot seven, the dedicated player-missile slot selected
  by the nonzero-subtype path at `$F402..$F42F`.
- The legal check only sets hostility; it does not clear an existing hostile
  ship when the player's score falls below 40. It stays hostile unless some
  other path resets or removes that instance.

The shared alert and missile tests are controlled executions of those
specific update paths. They do not claim that every possible encounter,
mission or way of provoking an alert has been exhaustively exercised.

## Reproduce the evidence

Run from the project root:

```bat
make.bat
verify.bat
python tools\check_bounty_hunters.py
```

The helper requires the optional SkoolKit installation in `tools/deps/`.
It checks the current assembled game and default release against the
structurally validated original before executing any fixture, and resolves
all current code and data addresses through `build/game.map`.
Its disposable report is `build/bounty-hunter-check/verification.json`.

The investigation passed:

- all 256 random-byte values at the mixed single-ship selector;
- 21 complete event-zero spawn cases: legal scores 0, 1, 39, 40, 49, 50 and
  255, with zero, five and six occupied allocatable slots. Seed `$000C`
  produces a Fer-de-Lance in the stated ordinary-event fixture; the full
  instance bytes are identical across legal scores, and full slots prevent
  allocation;
- all 19 blueprint defaults against all 256 legal scores (4,864 cases);
- all 256 inputs through the inline-space consumer, actual token-base load,
  legal-score read and status category branches;
- both steering-vector directions for all eight position-sign octants
  (16 cases);
- seven actual AI-entry executions, followed by controlled firing-gate
  checks with favourable alignment, range and RNG;
- a legal-score reduction, a nonlethal player hit, a trader-generated
  shared alert and an active player-missile slot, including Clean cases.

This is targeted Z80 execution with the supplied **ZX Spectrum 48K** ROM,
not a fresh full ROM tape-load or manual gameplay session. No executable bytes
were changed, and unrelated gameplay regressions were not rerun. Verified
meanings now have English labels/comments in `src/game.asm` and the initial
runtime-state and commander data includes. [Code names](CODE-NAMES.md) lists
them; `tools/verified_annotations.py` preserves them during regeneration.
Legacy aliases remain available. Existing unresolved regions remain unresolved.

The status-screen prefix at `$D0F8..$D0FA` is now written as an inline space
followed by `LD B,$12`, preserving bytes `$20,$06,$12`. The earlier linear
disassembly incorrectly displayed `JR NZ,L_D100` / `LD (DE),A`. The fixture
executes the real text-byte consumer before testing the selected status token.
To regenerate the annotated sources explicitly, run
`python tools\bootstrap_sources.py --force`; normal builds do not regenerate
them. Repeated generation with unchanged inputs produces identical sources.

The default build used z88dk **Z80 Macro Assembler
23854-4d530b6eb7-20251002**. All six TAP blocks passed structure, metadata,
length and XOR checks; the 47,918-byte release passed binary identity:

```text
SHA256: d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
```

| TAP block pair | Header / payload bytes | Metadata |
|---|---:|---|
| 0 / 1: BASIC ELITE | 17 / 130 | Autostart line 10 |
| 2 / 3: CODE a | 17 / 6,912 | Header load `$8000`; BASIC SCREEN$ uses `$4000` |
| 4 / 5: CODE elite | 17 / 40,801 | Load `$6048`, last byte `$FFA8`, entry `$7000` |

The investigation adds this document and `tools/check_bounty_hunters.py`,
and links it from `docs/SHIPS.md`. The follow-up annotates `src/game.asm`,
`src/data/initial-runtime-state.asm` and `src/data/active-commander-initial.asm`,
updates `tools/verified_annotations.py` and `tools/bootstrap_sources.py`, and
documents the names in `docs/CODE-NAMES.md`. The working tree was clean before
the original investigation; its pending changes were preserved during the
follow-up. Changes are left uncommitted locally; no commit or push was made.
