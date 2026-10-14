# Findings from the disassembly

This note collects results of the complete annotation pass that matter
beyond individual source comments. They fall into three groups:

- behaviour of the original game that is very probably unintended;
- corrections to the supplied research notes in `docs/info/`;
- facts about the image layout that earlier project notes described differently.

Addresses refer to the immutable reference image (TAP block 5). The source
uses the label names shown. "Verified" means the instructions fully determine
the behaviour. Most items were also reproduced by running the original code
in a ZX Spectrum 48K simulator, as described in
[routine checks](ROUTINE-CHECKS.md). None of these defects is fixed by the
default build. That build must stay byte-identical to the original.

## Original behaviour that looks unintended

| Address | Routine | Finding |
|---|---|---|
| `$BA65` | `PrintEconomy` | The economy adjective is computed in A, but the following `CALL PrintInlineToken` reloads A. Economies 0..3 and 5..7 therefore all print "Rich", and only economy 4 prints "Mainly". All eight values were executed. |
| `$DAC1` | `UpdateObjects` | The energy bomb's Thargoid exemption reads `(IY+6)` before IY is reloaded for the current slot at `$DAFA`, so it tests the previously processed ship. A Thargoid explodes and the ship processed after it is spared. |
| `$F650` | `SpawnRandomEncounter` | Special Asp encounter: if all six object slots are occupied, `RET NZ` pops the pushed AF word and execution continues in ROM at `$0F02`. |
| `$F83F` | AI ECM decision | The result of `CP $A0` is never used. Any AI ship with ECM switches it on as soon as the player's missile is in flight. |
| `$A7AA` | `UpdateEscapePod` | The cargo is cleared from `MarketFluctuation` (`$A82C`) for 17 bytes rather than from `CargoHold` (`$A82D`). Alien items survive and the price fluctuation byte is cleared, while the free space is reset as if the hold were empty. |
| `$BD9D` | `StartJustifiedText` | The justified-text buffer is filled up to and including `$7041`, overwriting `CurrentScreenId` with `$20`. The runtime traces show the write after every planet description. |
| `$E592` | `DivideRatioByte` | The division does not reliably saturate when the dividend has more significant bits than the divisor (the `SCF` at `$E5A8`). About half of those inputs still return 255; others return values below 255 for true ratios of 1 or more, for example 144 to 249 for ratios of 1.2 to 3.6. |
| `$E0C4` | `DrawObjectInView` | The crosshair test reads a caller's stacked value. Through `RotateAndDrawTitleShip` (the title object) that word is unrelated stack data. |
| `$EE10` | `DrawLine` | Lines whose deltas exceed 255 use halved 9-bit deltas. A small fraction of such lines is clipped wrongly. |
| `$8A5A` | `GetVectorMagnitude` | Accurate only when some coordinate is 256 or more. With all three coordinates below 256 it does not return the magnitude: (100, 0, 0) gives 51200. |
| `$77D5` | `ToggleCloak` | With too little energy the toggle leaves `$A80C` at `$FF` (non-zero) without changing the view colour. |

### Found in the second annotation pass

Each item below was reproduced by the named check in `tools/check_routines.py`,
or, where marked, follows from the instructions alone.

| Address | Routine | Finding |
|---|---|---|
| `$7C39` | `HyperspaceKeyLatch` | `CheckHyperspaceKeys` sets the latch before it tests anything else, so even a refused H or G press sets it. Until the next hyperspace arrival or game over, neither station contact nor the docking computer can dock the ship. Confirmed by `missions/p2-hyperspace-key-latch` and by a 48K emulator run. |
| `$BCFC` | `BufferJustifiedCharacter` | A non-space character arriving as the 31st character of a justified line is stored after the 30 printed characters and lost, for example a line-ending full stop (`text/justified-full-stop-loss`). |
| `$BDC6` | `FindPreviousSpace` | A justified line without any space would loop forever (follows from the instructions). |
| `$B5B4` | `BuyEquipmentItem` | Buying fuel while the nova mission is active takes the price and gives no fuel (`economy/p6-equipment-purchase`). |
| `$B333` | `InputQuantity` | A non-digit key after the first digit leaves the prompt with the one-digit trade already applied (`text/p6-input-quantity`). |
| `$B11D` | `InputString` | Typing into a full buffer ends the input as Enter would (`text/p6-input-string`). |
| `$D411` | `ReportTapeLoadingError` | A tape error while docked restores the commander from the snapshot taken at the last load, save or game start. The game then continues docked with that older commander. A BREAK keeps the bytes already loaded (`commander/p7-tape-load-paths`). |
| `$76DC` | `ProjectCoordinate` | For an off-screen sun or planet whose coordinate is between one and two times the depth, the projected offset can be up to 127 too large (`pipeline/p1-projection-offset-paths`). |
| `$EB65` | `ReleaseTargetLocks` | The test reads the removed object instead of the slot being scanned. Missiles locked on a removed ship keep their lock, and a ship whose `+$25` equals a removed missile's counter explodes (`contact/p9-release-target-locks`). |
| `$EC55` | `ApplyPlayerLaserHit` | Each hit lowers the AI courage counter in `+$25` by 14. On a fleeing ship a low value wraps upwards instead of stopping at the floor, which lifts it back above the flee threshold (`combat/r10-laser-hit-outcomes`). |
| `$8C29` | `DrawScannerContacts` | A contact with dx = 4 is drawn one pixel row off. The upward-stick guard covers only column 15, so in other columns a stick can reach screen row 127 inside the view (`scanner/p3-scanner-geometry`). |
| `$9119` | `FinishSoundEffect` | The request bit is cleared with XOR. If `SelectSoundOn` cancelled the requests while the effect played, the bit is set again (follows from the instructions). |
| `$F882` | `CheckShipProximity` | The coordinate high bytes are ignored, so a very distant object with small low bits would test as near (follows from the instructions; not seen in traces). |
| `$DB38` | `UpdateSharedHostility` block | The radius comparison with 30 can never be true: no blueprint has that radius (`structures/s1-blueprint-scoop-and-radius`). |
| `$6180` | blueprint table | The station's launch byte (`$06`) is never loaded, and nothing reads the `$C3` and group bytes of the table entries (`structures/s1-blueprint-launch-byte`). |

The second pass also fixed several of this project's own first-pass
statements; the corrected texts are in the source:

- blueprint header byte +2 is the AI laser-fire chance, halved while the
  combat score high byte is zero, not "agility";
- roll and pitch are 4-bit step counters with fixed angles;
- the AI steering vector is the position divided by 4;
- `CommanderFlags` bits 0..2 are set when missions 1..3 are triggered, not
  when they are completed.

## Corrections to the research notes

The save-format note in `docs/info/` remains unchanged as supplied research.
The active commander record (`ActiveCommanderRecord`, `$A816`) differs from
it as follows:

| Offset | Note | Code evidence |
|---|---|---|
| `+$28` | cargo bay size | `CargoFreeSpace`: free space. Buying subtracts, selling adds, and the large cargo bay adds 15. |
| `+$5D..+$65` | security code | A copy of the nine bytes at `$7065` (`SunPosition`), written before each save (`AccessMenuSave`) and copied back from the template when a new game starts. The security number printed after saving is calculated from the record and is not stored. |
| `+$66..+$67` | always `$00`, `$14` | Runtime variables in this 128K-compatible release; `+$67` holds `ChartCursorX`. |
| `+$0B` | legal status `$00/$30/$60` | Unsigned score: Clean at 0, Offender at 1..49, Fugitive at 50 or more. |
| `+$2D`, `+$5B`, `+$66` | mission events | `NovaMissionActive`, `InvasionMissionState` (states 0..5, plus `$0C` after the station is destroyed) and, at run time, `ExpandingSunActive`; proved by the messages each state shows and by the `missions` checks. |

Other research notes:

- **Missions** (`ArriveInTargetSystem`, `$D6B3`): in galaxy 1 (internal value 0) the hyperspace jump counter (`JumpCounter`, `+$0F`) is not incremented, and neither missions nor pirates are tested. Elsewhere only the counter's low byte is compared. The first clear bit of `CommanderFlags` is triggered: mission 1 at `$20` jumps, mission 2 at `$80` and mission 3 at `$FE`, strictly in that order. `MissionGalaxyGateOperand` (`$D7C5`) is the offset of that galaxy test.
- **Pirate boarding** (`$D802`): the station is boarded when the byte at `$7063` is less than or equal to 7 minus the government type. This is twice the probability quoted in the forum notes for a uniformly distributed byte. Boarding clears bit 7 of the station's `InstanceRoll`, so the station stops rotating. `CheckPirateGameOver` ends the game at docking.
- **Key-swap POKE**: the entry at `$FF68/$FF69` belongs to SYMBOL SHIFT and the entry at `$FF98/$FF99` belongs to B. The landmark labels are now named after these keys (`KeySymbolShiftActionByte`, `KeyBActionByte` and their masks).
- **Lave's tech level**: the JAMESON template stores 5 at `$A958`, but the system generator computes 4 for Lave and replaces the value at the first arrival.

## Image layout corrections

- `$92B5..$92B6` is a saved stack pointer used by `$9287`. The message table runs from `$92B7` to `$9964`. `$9965` is `TorusJumpDustFlag`, which is not text.
- `$C350..$C40B` is dormant code: a self-relocating loader for an external parallel interface (ports `$1F` and `$9F`). It is not the game's tape support, which is `RunAccessMenu` at `$D2E4`. The code is never referenced or executed, but its prologue relocates exactly its nine `CALL` operands. It is now disassembled as `DormantPortLoader`, with symbolic relocation offsets.
- The four large blocks at `$8153..$842F`, previously unclassified, are code. They are reached only through a self-modified `JR` in the disc-fill loops.
- `$84C5..$8544` holds patch values and destination pointers for self-modifying code. `DrawScreenCircle` uses them to switch the circle renderer between the `$C000` view buffer and the screen. The destinations are now emitted as `defw` labels, so they follow the patched code if it moves.
- `$E88B` is a complete but unused 16x16 multiply (`UnusedMultiplyWordHigh`).

Only seven bytes remain unclassified. Each is an unreferenced fragment with
an `INFERRED` comment explaining what it would decode to:

- `$7169..$716A`: `EI`/`RET`;
- `$C40C..$C40D`: the two bytes after the dormant receiver;
- `$FF53..$FF55`: `IM 1`/`RET`.

The `RET` byte at `$B93F` between two text handlers is now typed data: a
check proves that no path reaches it (`text/p6-unreachable-byte`).
