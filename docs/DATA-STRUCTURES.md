# Data structures

This page summarises the main data layouts that the annotated source uses.
Field constants such as `InstanceEnergy` are defined at the top of
`src/game.asm` from `tools/annotations/objects.py`. The source comments at
each field give the evidence. Meanings marked INFERRED are hypotheses; the
rest are proved by code, tests or runtime traces.

## Object instances

There are eight 39-byte slots at `InitialRuntimeState` (`$6048`):

- slot 0 is the space station;
- slots 1..6 (`ObjectSlot1`..`ObjectSlot6`) are allocated by `FindFreeShipSlot`;
- slot 7 (`ObjectSlot7`) holds the player's missile in flight and the title ship.

`InitialiseShipFromBlueprint` copies bytes `+$00..+$1E` from
`ShipInstanceTemplate`, stores the blueprint pointer and fills `+$1B` and
`+$20..+$26` from the blueprint header described in [SHIPS.md](SHIPS.md);
`+$1F` keeps whatever the slot held before. The station in slot 0 is never
created this way: its bytes come from the initial image (see the comments in
`src/data/initial-runtime-state.asm`), so its header launch flags are never
loaded. The `structures` group of `tools/check_routines.py` checks the
creation values, the explosion states and the rotation counters below.

| Offset | Constant | Contents |
|---|---|---|
| `+$00` | `InstanceX` | x: 24-bit sign-magnitude (low, high, then bits 16..22 with the sign in bit 7) |
| `+$03` | `InstanceY` | y, same format |
| `+$06` | `InstanceZ` | z (depth in the front view), same format |
| `+$09` | `InstanceAxisZ` | local z (nose) axis: three words, low fraction byte and sign-magnitude high byte, `$7FFF` = 1.0; ships move along it |
| `+$0F` | `InstanceAxisY` | local y (roof) axis; renormalised against the z axis |
| `+$15` | `InstanceAxisX` | local x (side) axis; recomputed as Y x Z / 128 when the object is drawn |
| `+$1B` | `InstanceSpeed` | speed; half the blueprint maximum when the object is created |
| `+$1C` | `InstanceAcceleration` | signed speed change added by every move (AI: 1, 2, -1 or -2); the sum is clamped to 0..maximum speed |
| `+$1C` | `InstanceExplosionDisc` | after destruction, `+$1C..+$1F` hold the projected x and y offsets, `$0C` + inverted quadrant bits, and the starting disc radius |
| `+$1D` | `InstanceRoll` | roll steps: bits 0..3 count down one per move (zero stops the roll; bits 4 and 5 are ignored), bit 6 negative direction, bit 7 endless; each step is a fixed angle of 12 |
| `+$1E` | `InstancePitch` | pitch steps, same format, fixed angle 8 |
| `+$20` | `InstanceFlags` | see below |
| `+$21` | `InstanceBehaviour` | blueprint `+$12 AND $6F`: bit 0 speed limit x4, 1 legal-sensitive, 2 hostile, 3 steers away (not towards the player) while a station is active, 5/6 protected (killing it raises the legal score) |
| `+$22` | `InstanceEnergy` | energy; zero marks a free slot, `$FF` a ship already destroyed by the laser |
| `+$23` | `InstanceBlueprint` | pointer to the 23-byte blueprint header |
| `+$25` | `InstanceAiState` | see below |
| `+$26` | `InstanceRoleFlags` | see below |

`InstanceFlags` (`+$20`):

| Bits | Meaning |
|---|---|
| 0..2 | payload count from blueprint `+$0A`; each successful AI launch decrements it |
| 3 | the ship fired its laser this update; the beam is drawn from the gun vertex and the bit cleared |
| 5:4 | 00 alive; 01 destroyed (laser, missile, energy bomb or ECM); 11 explosion position recorded by `DrawObjectInView`; 10 discs drawn, removed and credited on the next update |
| 6 | AI active and counted in `EncounterShipCount`; clear for canisters, capsules, debris and inert Thargons |
| 7 | escape capsule on board (blueprint `+$12` bit 7); cleared when it is launched |

A destroyed object (01) that is drawn records its screen position and size
(state 11); `DrawFlaggedObjectDiscs` then draws 15 discs with the radius
growing by 2 and clears bit 4 (state 10). An object that is not drawn goes
straight from 01 to 10. State 10 frees the slot and pays the blueprint bounty
and combat-score award.

`InstanceAiState` (`+$25`): for ships, bit 0 marks an ECM; the byte starts at
`$7E` and each player laser hit subtracts 14 (on underflow it becomes 6 plus
bit 0). When no station is active (or in mission state 4), a hostile ship
whose bits 0..6 are below 8 flees and sets bit 7. A ship below one eighth of
its energy bails out or drops cargo only when a random byte is at least the
whole byte. For missiles it is the target code:
0 = the player, otherwise 8 - slot (the `ObjectLoopCounter` value of the
target).

`InstanceRoleFlags` (`+$26`):

| Bit | Meaning |
|---|---|
| 0 | missile: guidance AI, collision damage includes its energy, closer approach |
| 1 | scoopable (canisters, capsules, debris, an inert Thargon): proximity box 180, fuel-scoop path |
| 2 | space station (slot 0 only): docking test, launches traffic, immune to laser damage |
| 3 | passive (station, canisters, capsules, debris): does not keep `SharedHostilityAlert` alive |
| 4 | not used |
| 5 | avoidance: steering away from the player; widens the near box to `$0A00` |
| 6 | the special Asp of `MissionAspEncounterState` |
| 7 | station destroyed by the player's missile in mission state 4; keeps it dormant until the next arrival |

Any of bits 0..3 also stops `TryFireAiLaser`.

## Active commander record

`ActiveCommanderRecord` (`$A816`) is the 104-byte buffer passed to the ROM
tape routines. `CommanderTemplateBuffer` (`$A910`) has the same layout for its
first 102 bytes. See [COMMANDER-STATE.md](COMMANDER-STATE.md) for how the two
copies are used.

| Offset | Label | Contents |
|---|---|---|
| `+$00` | | commander name, 10 characters and a terminator (padded with `$00`) |
| `+$0B` | `PlayerLegalScore` | legal score: 0 Clean, 1..49 Offender, 50+ Fugitive |
| `+$0C` | `CombatScoreFraction` .. `CombatScoreHigh` | 24-bit combat score (rating) |
| `+$0F` | `JumpCounter` | hyperspace jumps outside galaxy 1 (mission triggers) |
| `+$11` | `CurrentGalaxy` | zero-based galaxy number |
| `+$12` | `CashHigh`, `CashLow` | cash: units of 1000.0 Cr, then 0..9999 tenths |
| `+$16` | `MarketFluctuation` | price fluctuation of the current market |
| `+$17` | `CargoHold` | 17 cargo quantities in commodity order |
| `+$28` | `CargoFreeSpace` | free cargo space in tons |
| `+$29` | `LaserMounts` | front, rear, left, right: 0 none, 1 pulse, 2 beam, 3 military, 4 mining |
| `+$2D` | | mission-1 state (INFERRED: nova mission active) |
| `+$2E` | `FuelLevel` | fuel in tenths of a light year |
| `+$2F` | `MissileCount` | missiles fitted |
| `+$30..+$39` | `LargeCargoBayFitted` .. `GalacticHyperdriveFitted` | equipment flags; `+$32/+$33` and `+$3A/+$3B` unused |
| `+$3C` | `GalaxySeeds` | three seed words of the current galaxy |
| `+$42` | `CurrentSystemSeeds` | seeds of the current system (`CurrentSystemY` `+$43`, `CurrentSystemX` `+$45`) |
| `+$48` | `CurrentTechLevel`, `CurrentGovernment` | current system properties |
| `+$4A` | `MarketStock` | 17 station stock quantities |
| `+$5B` | | mission state (INFERRED: mission 3 events) |
| `+$5C` | `CommanderFlags` | bit 7 ECM jammer, bit 6 cloaking device, bit 5 refugees, bits 0..2 missions triggered |
| `+$5D` | | copy of the nine bytes at `SunPosition` (`$7065`) |
| `+$66` | | tape byte reused at run time |
| `+$67` | `ChartCursorX` | chart cursor x; `ChartCursorY` follows the record at `$A87E` |

## Input

`ScanKeyboard` runs in the IM 2 handler. It reads the eight keyboard half-rows
and, through `KeyCharacterTable` and `KeyActionTable`, latches key bits into
five state bytes:

| Label | Bits |
|---|---|
| `KeyFlagsScreens` | ENTER, L, K, P, O, I, joystick fire, Y |
| `KeyFlagsFlight` | N/left, M/right, X/down, S/up, SPACE, SYMBOL SHIFT |
| `KeyFlagsViews` | 1, 2, 3, 4, H, G, J, CAPS SHIFT |
| `KeyFlagsCombat` | A/fire, T, F, U, E, W, Q, C |
| `KeyFlagsChart` | chart cursor keys and B |

The scan also updates three other bytes:

- `LastKeyCode`: the character of the last key, or `$FF` for none;
- `ControlOptions`: the input device and the pause-menu toggles;
- `JoystickNumberKeys`.

`RollControl`, `PitchControl` and `SpeedControl` are integrated from the latched
direction and speed keys in `UpdateFlightControls`.

## Screens and buffers

| Area | Use |
|---|---|
| `$C000..$CFFF` | View bitmap buffer (256 x 128 pixels, Spectrum screen order). It is cleared by `ClearViewBuffer` and copied by `BlitViewBitmap`. Its initial tape content is the font, dormant code and cockpit data, all overwritten at runtime. |
| `$5B00..$5D6F` | Cockpit attribute buffer, also used as the scanner background backup (`ScannerBackupBuffer`) |
| `$5D70..$6047` | Runtime copy of the font (`FontRuntime`) |
| `$FD00..$FE00` | IM 2 vector table; entry `InterruptEntry` at `$FEFE` |

Self-modifying code switches several drawing routines between the view
buffer and the screen. The patch tables and their destination pointers are
annotated where they are defined (`DrawScreenCircle`,
`PatchDiscRendererTarget`, `GetCharacterBitmap`).

## Text

Text uses two interpreters, documented in `tools/annotations/text.py` and
decoded for comments by `tools/text_codec.py`:

- `PrintToken`: control codes `$00..$0D` through `TokenControlTable`,
  characters `$20..$5F`, two-letter tokens `$80..$9F`, and dictionary tokens
  `$0E..$1F`, `$60..$7F` and `$A0..$FF` from `TextTokenDictionary`;
- `PrintMessage`: numbered messages in `EncodedTextData`, using control codes
  `$00..$1F` (`MessageControlTable`), random choices `$5B..$80`, nested
  messages `$81..$D6` and two-letter tokens `$D7..$FF`.
