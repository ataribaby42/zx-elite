"""Verified names/comments for the immutable reference disassembly.

Keys identify original reference bytes for reconstruction only. Emitted code
uses symbolic labels; legacy L_xxxx aliases remain available to existing tools.
Evidence: source flow, graphics/ship checks and exhaustive station-launch tests.
Do not add inferred identities here as if they were verified facts.
"""

ANNOTATIONS = {
    0x7041: ('CurrentScreenId', (
        'Current screen selector: 0..3 are the four cockpit views; other values select non-flight screens.',)),
    0x7077: ('StationPresent', (
        'Nonzero while the station is present; also selects the cockpit S indicator.',)),
    0x7189: ('ContinueStartup', (
        'Shared startup continuation after font/colour copies and the initial stack save.',
        'Both original Startup and the one-time relocated AdderStartup reach here.',
        'Restart/death enters later at L_718F; do not rerun reclaimed Adder startup storage.',)),
    0xA660: ('DrawCockpitIndicators', (
        'Draw the encounter circle, ECM E and station S indicators, then restore XOR text mode.',
        'The original character-renderer path overwrites the scanner pixel under the E tile.',
        'scannerpixelfix=yes uses the same-size replacement that preserves that background bit.',)),
    0xA6D3: ('DrawMissileIndicators', (
        'Draw the four missile slots from the commander missile count.',
        'Returns in overwrite mode with all four missiles present, otherwise in XOR mode.',
        'Both original and scannerpixelfix implementations preserve this return convention.',)),
    0xA80D: ('TextColumn', (
        'Current character column; TextRow is the adjacent byte, so an HL store can set both.',)),
    0xA80E: ('TextRow', ('Current character row used by the shared character renderer.',)),
    0xBBBF: ('CharacterBlendOpcode', (
        'Self-modified character-blending instruction, not a separate mode variable.',
        '$A9 is XOR C (combine glyph with old pixels); $00 is NOP (overwrite with glyph).',)),
    0xDA16: ('EcmTimer', (
        'ECM activity countdown: nonzero lights the E indicator and inhibits AI payload launch.',
        'Player/AI activation sets this to 10; the ECM update decrements it.',)),
    0xDA1B: ('EncounterShipCount', (
        'Encounter/traffic count across six allocatable slots; station slot zero is excluded.',
        'Count only instances with nonzero energy (+$22) and bit 6 set in byte +$20.',
        'This is not a count of every occupied slot.',
        'The traffic/encounter gates reject new launches at a count of four or more.',)),
    0xED24: ('NextRandomByte', (
        'Advance the two-byte RandomSeed and return the new high seed byte in A.',
        'Incoming carry is an input to the generator; do not clear or set it casually.',
        'For old seed bytes H:L and input carry c: t=2*H+c, new L=t&255,',
        'new H=(new L+old L+(t>>8))&255. The final ADC also sets output carry.',
        'BC and HL are saved/restored; DE is untouched. A and flags are results.',)),
    0xED35: ('RandomSeed', (
        'Little-endian two-byte RNG state; its high byte holds the last returned random value.',)),
    0xF2CA: ('DispatchShipEvent', (
        'Dispatch A: low nibble selects an event, high nibble becomes its count/subtype in C.',
        'Verified cases: 0=random encounter, 1=Thargoid group, 2=missile, 4=parent launch.',
        'The low-nibble AND clears carry; the subsequent DEC chain preserves that carry.',)),
    0xF2FB: ('InitialiseShipFromBlueprint', (
        'A supplies the ship ID in its low six bits; IX points to an already selected instance.',
        'Resolve the blueprint table, return its pointer in IY, and store it at IX+$23/$24.',
        'Copy instance defaults, then set energy, behaviour, payload count and half maximum speed.',
        'Initial coordinates use the RNG. Parent launches overwrite the first 27 bytes afterwards.',
        'ship=adder uses compact two-byte pointers and replaces only blueprint slot 17.',)),
    0xF381: ('CreateShipAtParent', (
        'A=child ship ID, IX=parent. Allocate and initialise a child, then copy parent bytes 0..26.',
        'Those bytes hold position and orientation; the child keeps its own blueprint and energy.',
        'On success IX points to the child and Z is set. NZ means no free slot.',)),
    0xF399: ('FindFreeShipSlot', (
        'Scan six 39-byte instances after persistent station slot zero.',
        'Energy at instance+$22 equal to zero marks a free slot. C is preserved.',
        'Return Z with IX pointing at the free instance, or NZ if all six are occupied.',)),
    0xF44A: ('SelectParentLaunchType', (
        'IX=parent, C=launch subtype: 1 Viper, 2 Cobra/Python trader, 3 Thargon,',
        '4 Thargoid, 5 Sidewinder/Krait (Adder instead of Krait with ship=adder).',
        'Viper selection bypasses the RNG; all valid choices continue at LaunchSelectedShip.',
        'The original subtype-2 RNG is correlated with the preceding station gate and always',
        'chooses Python there. stationrandomlaunchfix=yes repairs the choice in the same 38 bytes.',)),
    0xF470: ('LaunchSelectedShip', (
        'A=selected child type, IX=parent. Create the child at its parent position/orientation.',
        'Adjust launch orientation only for a non-station parent, then inherit parent hostility.',
        'On success IX=child, IY=parent and Z is set; NZ reports allocation failure.',)),
    0xF48A: ('AdjustChildLaunchOrientation', (
        'Alternate between two child-orientation adjustments using the toggle at L_F2C9.',
        'Called for non-station parents only; station launches retain the copied orientation.',)),
    0xF6FD: ('SelectEncounterTraderType', (
        'Ordinary space encounter: A=2..7 selects Cobra trader (9) or Python trader (10).',
        'This path is separate from station launches and is not affected by stationrandomlaunchfix.',)),
    0xF780: ('TryLaunchAiPayload', (
        'AI payload attempt: IX=parent instance, IY=its blueprint. Require remaining payload,',
        'random result below $80 and inactive ECM. Blueprint byte $0A high nibble selects',
        'the launch subtype; rock hermits use 5, Thargoids use 3. Zero selects a missile event.',
        'Dispatch with IX/IY preserved; decrement the payload count only on successful creation.',)),
    0xF846: ('TryLaunchStationTraffic', (
        'Station traffic gate: require instance+$26 bit 2 and EncounterShipCount below four.',
        'The count comparison leaves carry set for the first NextRandomByte call.',
        'A calm station branches to TryLaunchStationTrader. A hostile station admits results',
        'below $24 and normally requests a Viper; mode value 4 uses an extra Thargoid gate.',)),
    0xF871: ('TryLaunchStationTrader', (
        'Continue with the station gate RNG result in A: only values 0 and 1 permit a trader.',
        'Event $24 means parent-launch event 4, subtype 2; it is not a ship ID.',)),
    0xF876: ('DispatchShipEventPreservingParent', (
        'Dispatch the event in A while saving/restoring parent IX and IY.',
        'POP does not change flags, so the event success/failure result reaches the caller.',)),
}
