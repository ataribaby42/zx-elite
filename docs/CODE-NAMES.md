# Verified routine and state names

The names below describe code already investigated through source flow and
the graphics, ship-allocation, station-launch and bounty-hunter checks. These annotations
do not change instructions, data, addresses or memory usage.

`tools/verified_annotations.py` supplies these names and English comments to
`tools/bootstrap_sources.py`. Normal builds assemble `src/game.asm` directly;
they do not run the reconstruction generator. Keep source annotations and
their generator definitions consistent.

The registry keys are positions in the immutable reference tape, not runtime
addresses to copy into code. ASM references use labels. Each renamed target
retains its old `L_xxxx` alias at the same position, so existing analysis tools
and historical documentation remain usable. Current addresses come from the
assembler map; optional implementations may place an entry differently.

## Graphics and startup

| Name | Verified purpose |
|---|---|
| `ContinueStartup` | Shared continuation after the original or relocated Adder startup copies. |
| `CurrentScreenId` | Selects cockpit views 0..3 or a non-flight screen. |
| `StationPresent` | Station-presence state, also used for the cockpit S indicator. |
| `DrawCockpitIndicators` | Encounter circle, ECM E and station S indicators; restores XOR text mode. |
| `DrawMissileIndicators` | Four missile slots, including the optional scanner-fix implementation. |
| `TextColumn`, `TextRow` | Adjacent character-position bytes. |
| `CharacterBlendOpcode` | Self-modified XOR C / NOP opcode selecting glyph blending or overwrite. |
| `EcmTimer` | ECM countdown, used by the indicator and the AI payload gate. |

The existing `DrawLaser`, `DrawLine`, font, cockpit-data and startup labels
remain in use. The scanner fix still preserves the existing background bit
on each write, rather than changing the shared character renderer.

## Ship creation and launches

| Name | Verified purpose |
|---|---|
| `DispatchShipEvent` | Decodes the event in A's low nibble and the count/subtype in its high nibble. |
| `DispatchShipEventPreservingParent` | Saves and restores parent IX/IY around the event dispatcher. |
| `FindFreeShipSlot` | Looks for zero energy in six 39-byte instances after station slot zero. |
| `InitialiseShipFromBlueprint` | Resolves the blueprint and fills an allocated instance's defaults. |
| `CreateShipAtParent` | Allocates a child and copies the parent's position and orientation. |
| `SelectParentLaunchType` | Shared selection of Viper, trader, Thargon, Thargoid or fighter. |
| `LaunchSelectedShip` | Creates the selected child, adjusts non-station launches and inherits hostility. |
| `AdjustChildLaunchOrientation` | Alternates two orientation adjustments for non-station parents. |
| `TryLaunchAiPayload` | Launches a missile, a rock-hermit fighter or a Thargoid's Thargon. |
| `TryLaunchStationTraffic` | Station-only launch gate, with separate calm and hostile paths. |
| `TryLaunchStationTrader` | Calm-station trader gate; accepts the preceding random result 0 or 1. |
| `SelectEncounterTraderType` | Separate Cobra/Python choice for ordinary space encounters. |
| `EncounterShipCount` | Launch/encounter limit count, excluding the station and non-qualifying objects. |

`EncounterShipCount` includes only instances with nonzero energy at offset
`$22` and bit 6 set at offset `$20`. It is not the total number of occupied
slots. Allocation itself checks energy and can therefore run out of slots
independently of this count.

Station traffic and ordinary space encounters use different trader-selection
paths. Rock hermits and Thargoids share the parent-launch selector, but do not
pass through the station-only gate. The comments record register inputs,
allocation results and the distinction between an event code and a ship ID.

## Encounter selection and hostility

The following names come from the Fer-de-Lance investigation and controlled
ZX Spectrum 48K execution in `tools/check_bounty_hunters.py`. See
[Fer-de-Lance encounters and legal hostility](BOUNTY-HUNTERS.md) for the
complete paths, original addresses and test scope.

| Name | Verified purpose |
|---|---|
| `SpawnRandomEncounter` | Event-zero encounter entry, including the paths preceding the mixed ship selector. |
| `SpawnMixedSingleShipEncounter` | Allocate one slot before selecting a mixed encounter ship; return when full. |
| `SelectMixedEncounterShipType` | Select Thargoid, Fer-de-Lance, Asp, pirate Cobra or pirate Python. |
| `InitialiseEncounterShip` | Load the selected blueprint and restore saved AF before the optional byte `+$25` flag. |
| `PlayerLegalScore` | Commander score: Clean at zero, Offender at 1..49, Fugitive at 50 or more. |
| `PrintLegalStatus` | Consume the inline space, load the Clean token index and continue the status-screen row. |
| `SelectLegalStatusToken` | Increment that token index according to the legal-score display boundaries. |
| `UpdateShipHostilityAndSteering` | Viper/Fer-de-Lance legal-hostility threshold at 40, followed by steering decisions. |
| `SharedHostilityAlert` | Alert raised by a hostile ship carrying behaviour bits `$20` or `$40`. |
| `PlayerMissileEnergy` | Slot-seven energy: player missile during flight, also reused by the title display. |
| `UpdateSharedHostility` | Propagate that alert or active player missile into the current instance's hostility. |
| `ApplyPlayerLaserHit` | Provoke the hit instance before damage handling and beam drawing. |
| `SteerShipAwayFromPlayer` | Build the scaled vector away from the player and set the avoidance bit. |
| `SteerShipTowardsPlayer` | Reverse the vector signs to steer towards the player; also used by enemy missiles. |
| `TryFireAiLaser` | Test hostility, facing, RNG, flags, range and alignment before laser damage. |

Several names identify blocks within a larger routine, not separately callable
subroutines. Their comments state the required registers, stack state and
continuation. The hunter role is inferred from the verified legal-sensitive
behaviour; it is not used as the name of a separate spawn event.

The source generator now preserves annotations and legacy aliases inside
verified data includes as well as `game.asm`. It also emits the legal-status
prefix at original `$D0F8..$D0FA` correctly: inline `$20` consumed by `L_BA99`,
then `LD B,$12`. The former linear `JR NZ,L_D100` / `LD (DE),A` spelling was
misleading. Its bytes are unchanged, and the old `L_D100` address alias remains
available for existing analysis tools.

## Random state

`NextRandomByte` updates the two-byte `RandomSeed`. Incoming carry is part of
its input, and the final ADC produces outgoing carry. BC and HL are preserved;
DE is untouched. The exact byte recurrence is documented beside the routine.

That carry dependency explains the original station-trader selection bug.
The optional station fix retains RNG advancement and the rock-hermit fighter
choice while correcting the station trader choice. See
`BUILD-VARIANTS.md` for the investigation and exhaustive checks.

## Scope and validation

Only meanings supported by existing evidence are named. Unresolved code keeps
neutral labels; an executed address alone does not establish a routine's role.
This is a partial map, not a claim that the entire disassembly is understood.

For naming changes, compare the default TAP with the immutable original and
check that legacy aliases equal their new labels and existing symbols have
not moved. Select the relevant behaviour tests for the annotated paths.
If names used by optional includes change, also compare a combined modified
build with its pre-annotation TAP and run `tools/check_variant_relocation.py`.
No full gameplay or option matrix is needed when the resulting binaries are
identical and optional implementations are unchanged.

For the encounter/hostility names, `make.bat`, `verify.bat` and
`python tools/check_bounty_hunters.py` passed. The helper checks every registry
alias, executes all 256 scores through the real inline-space consumer and
legal-token selection, and checks both steering-vector directions in all eight
position-sign octants. A before/after map comparison found no moved or missing
existing symbols. Two consecutive `python tools/bootstrap_sources.py --force`
runs with the final inputs produced identical source files. Optional include
files and their references were unchanged, so their separate regressions were
not rerun.
