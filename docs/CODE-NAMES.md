# Verified routine and state names

The names below describe code already investigated through source flow and
the graphics, ship-allocation and station-launch checks. These annotations
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

For these naming changes, compare the default TAP with the immutable original,
and the combined modified build with its pre-annotation TAP. Check that every
legacy alias equals its new label and that the former symbols have not moved.
The small `tools/check_variant_relocation.py` fixture also covers the changed
references from optional includes. No full gameplay or option matrix is needed
when the resulting binaries are identical.
