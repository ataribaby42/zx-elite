"""Cockpit status/energy/missiles, commander record fields, charts, system generator, market.

Range $A400..$AFFF.  Evidence: instruction semantics; tokens and messages printed with
the values (status, data-on-system, market, chart and mission screens); 48K runtime traces
in docs/generated/runtime-xrefs.json; and the simulator checks in tools/check_routines.py
(groups economy, dust, missions and commander, including the p5-* checks).
"""

COMMODITIES = ('FOOD', 'TEXTILES', 'RADIOACTIVES', 'SLAVES', 'LIQUOR/WINES', 'LUXURIES',
               'NARCOTICS', 'COMPUTERS', 'MACHINERY', 'ALLOYS', 'FIREARMS', 'FURS',
               'MINERALS', 'GOLD', 'PLATINUM', 'GEM-STONES', 'ALIEN ITEMS')

ACTIVE = 0xA816      # ActiveCommanderRecord (104-byte tape buffer)
TEMPLATE = 0xA910    # CommanderTemplateBuffer (102-byte JAMESON template)

# Field layout shared by both records: (offset, comment).  Meanings are proved by the
# code cited in the LABELS headers of the active record below.
_FIELDS = [
    (0x00, 'name, 10 characters (this release pads with $00)'),
    (0x0A, 'name terminator'),
    (0x0B, 'legal score (PlayerLegalScore)'),
    (0x0C, 'combat score, fraction byte'),
    (0x0D, 'combat score, low byte'),
    (0x0E, 'combat score, high byte'),
    (0x0F, 'jump counter, word'),
    (0x11, 'galaxy number, zero-based'),
    (0x12, 'cash high word (units of 1000.0 Cr)'),
    (0x14, 'cash low word (0..9999 tenths of a credit)'),
    (0x16, 'market fluctuation byte'),
] + [(0x17 + i, f'cargo {i}: {name}') for i, name in enumerate(COMMODITIES)] + [
    (0x28, 'free cargo space, tons'),
    (0x29, 'front laser (0 none, 1 pulse, 2 beam, 3 military, 4 mining)'),
    (0x2A, 'rear laser'),
    (0x2B, 'left laser'),
    (0x2C, 'right laser'),
    (0x2D, 'nova mission active (NovaMissionActive)'),
    (0x2E, 'fuel, tenths of a light year'),
    (0x2F, 'missiles'),
    (0x30, 'large cargo bay'),
    (0x31, 'E.C.M. system'),
    (0x32, 'two bytes without any code reference'),
    (0x34, 'fuel scoops'),
    (0x35, 'escape pod'),
    (0x36, 'energy bomb'),
    (0x37, 'energy unit'),
    (0x38, 'docking computers'),
    (0x39, 'galactic hyperdrive'),
    (0x3A, 'two bytes without any code reference'),
    (0x3C, 'galaxy seeds s0, s1, s2 (words)'),
    (0x42, 'current system seeds s0, s1, s2 (words)'),
    (0x43, 'current system Y (s0 high)'),
    (0x44, 'current system s1 low'),
    (0x45, 'current system X (s1 high)'),
    (0x46, 'current system s2'),
    (0x48, 'current system tech level'),
    (0x49, 'current system government'),
] + [(0x4A + i, f'station stock {i}: {name}') for i, name in enumerate(COMMODITIES)] + [
    (0x5B, 'invasion mission state (InvasionMissionState)'),
    (0x5C, 'flags: missions 0..3, 5 refugees, 6 cloak, 7 ECM jammer'),
    (0x5D, '9-byte copy of L_7065..L_706D'),
]

COMMENTS = {}
for _offset, _text in _FIELDS:
    COMMENTS[ACTIVE + _offset] = f'+${_offset:02X} {_text}'
    COMMENTS[TEMPLATE + _offset] = f'+${_offset:02X} {_text}'
COMMENTS.update({
    ACTIVE + 0x66: '+$66 tape byte; RAM reused as ExpandingSunActive',
    ACTIVE + 0x67: '+$67 tape byte; RAM reused as ChartCursorX',
})
for _i, _name in enumerate(COMMODITIES):
    COMMENTS[0xAF0E + 2 * _i] = f'price {_i}: {_name}'

COMMENTS.update({
    # Side-view dust respawn (RespawnDustSideView).
    0xA402: 'vertical rate of this view (side views swap the rates in)',
    0xA409: 'Z OR operand 0: Z = 0..127',
    0xA40C: 'C = 1: left view, C = 2: right view',
    0xA40F: 'left view: X = +120, at the edge',
    0xA414: 'right view: X = -120 (sign bit 7 set)',
    0xA418: 'Y: magnitude 0..63 with a random sign',
    0xA41D: 'store Y (record byte 1)',
    0xA41F: 'Z = random 0..127 OR the patched operand',
    0xA424: 'SMC operand: $00 without, $80 with a vertical rate (Z bit 7)',
    0xA426: 'store Z, save the pointer and the random state',
    0xA42A: 'Z OR operand $80: Z = 128..255',
    0xA42D: 'alternate the two patterns: bit 7 into carry',
    0xA434: 'no carry: X at the side edge as above',
    0xA436: 'carry: random X, magnitude bit 3 clear (at most 119)',
    0xA43D: 'pitch sign (DustFlags bit 3) chooses the edge',
    0xA444: 'Y = +63: top edge',
    0xA448: 'Y = -63: bottom edge',
    # SwapDustParticleXY.
    0xA44C: 'B = particles in this pass (16, or 4 in witchspace)',
    0xA450: 'first particle record',
    0xA455: 'DE = byte 1 (Y)',
    0xA459: 'byte 1 = old X',
    0xA45A: 'byte 0 = old Y',
    0xA45C: '5-byte record stride',
    # Condition indicator.
    0xA4C1: 'docked: no condition indicator',
    0xA4C3: 'fore shield empty?',
    0xA4C9: 'aft shield empty?',
    0xA4D0: 'flashing ($63) has priority over red',
    0xA4D4: 'red: a shield is down',
    0xA4D7: '$63: flashing red (EnergyBank4 not full)',
    0xA4DB: 'flash phase counter',
    0xA4DF: 'bit 1: colour 2 for two calls, 0 for two',
    0xA4E8: 'D = colour: 0, 2 red, 4 green or 6 yellow',
    0xA4EC: 'cockpit views 0..3?',
    0xA4F0: 'attribute cells of the encounter circle tiles (rows 17..18, columns 8..9)',
    0xA4F6: 'second row of the circle cells',
    0xA4FC: 'FlightCondition = 4 (green) for the next frame',
    0xA4FF: 'missile status cell paper from MissileState (1 -> 4)',
    0xA506: 'armed and searching: green paper',
    0xA50B: 'attribute = paper * 8 + white ink 7',
    0xA50D: 'missile status cell: row 23, column 7',
    0xA511: 'other screens: indicator in the title row',
    0xA514: 'CharacterBlendOpcode = NOP (overwrite glyphs)',
    0xA516: 'TextColumn 27, row 1: characters land at columns 28..29',
    0xA51C: 'screens 9 and above: codes $23,$24 with the raw colour',
    0xA522: 'dark flash phase: shown as 2, red ink on red paper',
    0xA524: 'red?',
    0xA532: 'red: attribute $17, white ink on red paper',
    0xA538: 'attribute $10 + colour: coloured ink on red paper',
    0xA53C: 'codes $23,$24 with attribute D',
    0xA548: 'attributes of the two indicator cells at row 1, columns 28..29',
    0xA551: 'CharacterBlendOpcode = XOR C (blend glyphs)',
    # Cockpit systems, energy and shields.
    0xA55C: 'cockpit views 0..3 only',
    0xA56F: 'keep fire, E and C (bits 0, 4, 7); drop T, F, U, W, Q',
    0xA577: 'docked: nothing to do',
    0xA57B: 'is the last energy bank full ($A0)?',
    0xA57F: 'no: flashing condition ($63)',
    0xA587: 'fore shield',
    0xA58A: 'fore damage of this update',
    0xA590: 'aft shield',
    0xA593: 'aft damage of this update',
    0xA599: 'cloaking device on: one more unit of drain',
    0xA59D: 'drain units of this update (laser, ECM)',
    0xA5A4: 'drain C four times',
    0xA5A9: 'D = banks left to draw on',
    0xA5AF: 'bank cannot pay C: empty it, its rest is lost',
    0xA5B1: 'next bank',
    0xA5B6: 'all four banks empty',
    0xA5B8: 'the ship is lost: the game ends',
    0xA5BC: 'bank keeps the rest; the same bank pays next time',
    0xA5C2: 'damage this update?',
    0xA5C4: 'none: DamageCounter decays by one',
    0xA5CE: 'damage >= $46: chance of equipment damage',
    0xA5D0: 'heavy hit: random equipment or cargo loss',
    0xA5D5: 'subtract the damage up to five times',
    0xA5DF: 'shield exhausted',
    0xA5E1: 'that was the last repetition: no energy loss',
    0xA5E3: 'remaining repetitions drain the banks',
    0xA5EA: 'DamageCounter += 5; equipment damage from 13',
    0xA5ED: '13 or more: fall into DamageEquipmentOrCargo',
    0xA5F0: 'equipment-destroyed message still pending?',
    0xA5F6: 'random byte (low byte of AuxRandomSeed)',
    0xA5FB: 'n = bits 2..7: 0..63',
    0xA5FD: '0: fuel leak',
    0xA600: '>= $11: nothing',
    0xA604: '7..16: lose cargo',
    0xA608: 'equipment base EcmFitted; offsets 0 and 3..7 follow',
    0xA60E: 'n = 2..6: offsets 3..7 (the two unused bytes are skipped)',
    0xA613: 'fitted?',
    0xA616: 'D = 0 after AddAToHL: the item is destroyed',
    0xA618: 'token $6C+offset: E.C.M.SYSTEM .. DOCKING COMPUTERS',
    0xA61A: 'item token for the " DESTROYED" message',
    0xA61D: 'recolour the instruments (colour shows EscapePodFitted)',
    0xA620: 'raise the " DESTROYED" message',
    0xA626: 'A = 6..15 selects CargoHold+2..CargoHold+11',
    0xA62C: 'carried?',
    0xA62F: 'lose one ton',
    0xA630: 'and gain one ton of free space',
    0xA634: 'token $CC+A = $D0+commodity',
    0xA63A: 'energy unit fitted: recharge twice',
    0xA644: 'four banks, EnergyBank4 first',
    0xA647: 'bank full?',
    0xA64B: 'one unit into that bank',
    0xA64D: 'previous bank',
    0xA651: 'all banks full: fore shield + 1',
    0xA657: 'aft shield + 1',
    # Cockpit indicators (original code path of DrawCockpitIndicators).
    0xA663: 'CharacterBlendOpcode = NOP (overwrite glyphs)',
    0xA665: 'circle top: row 17, column 9',
    0xA670: 'circle bottom: row 18, column 9',
    0xA67B: 'E indicator: rows 22..23, columns 8..9',
    0xA67E: 'ECM active?',
    0xA68F: 'S indicator: rows 22..23, columns 22..23',
    0xA692: 'station present?',
    0xA6A6: 'CharacterBlendOpcode = XOR C (blend glyphs)',
    0xA6B4: 'next tile row',
    0xA6D3: 'row 23, column 2: slots at columns 3..6',
    0xA6DC: 'CharacterBlendOpcode = NOP (overwrite glyphs)',
    0xA6DE: 'one missile character per missile',
    0xA6EE: 'then 4 - MissileCount empty slots',
    0xA6F5: 'four missiles: return in overwrite mode',
    0xA6F6: 'B = empty slots',
    0xA703: 'CharacterBlendOpcode = XOR C (blend glyphs)',
    # Missiles.
    0xA706: 'no missiles: nothing to do',
    0xA70E: 'searching (state 1)?',
    0xA712: 'no target locked yet?',
    0xA719: 'object in the sights (8 - slot), 0 = none',
    0xA71F: 'lock on to it',
    0xA723: 'locked (state 2)',
    0xA725: 'ROM BEEPER pitch value',
    0xA728: 'ROM BEEPER length in cycles',
    0xA72B: 'ROM BEEPER: lock tone',
    0xA72E: 'latched combat keys',
    0xA735: 'key bits into carry, bit 0 first',
    0xA739: 'T (bit 1): arm',
    0xA73D: 'F (bit 2): fire',
    0xA741: 'U (bit 3): disarm',
    0xA744: 'already locked: T changes nothing',
    0xA748: 'armed, searching (unless already locked)',
    0xA74B: 'searching starts without a target',
    0xA74F: 'disarmed',
    0xA752: 'fire only when locked',
    0xA75D: 'event 2 with the target slot in the high nibble',
    0xA764: 'Z: launched',
    0xA766: 'launch failed: raise "MISSILE JAMMED"',
    0xA76C: 'launched: state 0',
    0xA76E: 'sound request bit 1: missile launch',
    0xA776: 'one missile fewer',
    0xA777: 'redraw the missile slots',
    # Escape pod.
    0xA780: 'pod not launched: check the key',
    0xA784: 'timer expired',
    0xA78B: 'bit 6 of KeyFlagsCombat (Q): launch escape pod',
    0xA78E: 'escape pod fitted?',
    0xA793: 'never in witchspace (WitchspaceFlag)',
    0xA798: '24 frames until L_7102',
    0xA79D: 'SpeedControl = $0010: speed 0',
    0xA7A4: 'escape pod clears the legal score',
    0xA7A7: 'and is used up',
    0xA7AA: '17 bytes: fluctuation and CargoHold+0..15 (alien items kept)',
    0xA7B3: 'refugees (bit 5) are lost with the ship',
    0xA7B7: 'clear bit 5 of CommanderFlags',
    0xA7BA: 'free space of an empty hold',
    0xA7C1: 'free space 20 tons, or 35 with the large cargo bay',
    0xA7C5: 'large cargo bay: 35 tons',
    0xA7C8: 'ship event $17',
    0xA7CD: 'chart cursor = current system',
    # Screen function table: functions 0..2 are screens 4..6, 3..8 screens 7..12.
    0xA7DA: 'function 0: buy cargo (screen 4)',
    0xA7DD: 'function 1: sell cargo (screen 5)',
    0xA7E0: 'function 2: equip ship (screen 6, prints EQUIP)',
    0xA7E3: 'function 3: galactic chart (screen 7, key I)',
    0xA7E6: 'function 4: short-range chart (screen 8, key O)',
    0xA7E9: 'function 5: data on the selected system (screen 9, key P)',
    0xA7EC: 'function 6: market prices (screen 10, key K)',
    0xA7EF: 'function 7: commander status (screen 11, key L)',
    0xA7F2: 'function 8: inventory (screen 12, ENTER)',
    0xA7F5: 'function 9: chart cursor left (X-1)',
    0xA7F8: 'function 10: chart cursor right (X+1)',
    0xA7FB: 'function 11: chart cursor down (Y+2)',
    0xA7FE: 'function 12: chart cursor up (Y-2)',
    0xA801: 'function 13: chart cursor to the current system',
    0xA804: 'function 14: snap the cursor to the nearest system',
    0xA807: 'function 15: find a system by name',
    # Dormant vectors.
    0xA897: 'dormant vector: fuel leak',
    0xA89B: 'dormant vector: ScoopCargoItem',
    0xA89E: 'dormant vector: AwardBounty',
    0xA8A1: 'dormant vector: AddCombatScore',
    0xA8A7: 'dormant vector: DamageEquipmentOrCargo',
    # Scooping, combat score, bounty.
    0xA8AD: 'cloaking device (CommanderFlags bit 6)',
    0xA8B2: '+256 combat score',
    0xA8B3: 'token CLOAKING DEVICE',
    0xA8B8: '$FF: the cloaking-device canister',
    0xA8BF: 'one ton less free space',
    0xA8C3: 'CargoHold + commodity',
    0xA8C7: 'one ton more of commodity A',
    0xA8C8: 'commodity name token',
    0xA8CA: 'scooped-cargo message slot',
    0xA8CD: 'raise the scooped-cargo message with token A',
    0xA8D1: 'A = commodity again ($FF: no penalty applies)',
    0xA8D2: 'quantity 1 for the contraband check',
    0xA8D4: 'firearms: 2 per ton',
    0xA8D8: 'slaves: 4 per ton',
    0xA8DC: 'narcotics: 4 per ton',
    0xA8DF: 'x2 again for slaves and narcotics',
    0xA8E1: 'B = 2 * tons',
    0xA8E3: 'legal score + penalty',
    0xA8EA: 'saturate at 255',
    0xA8F2: 'fraction byte + E',
    0xA8F6: 'low byte + D + carry',
    0xA8FA: 'carry out of the low byte: high byte +1',
    0xA8FB: 'raise "RIGHT ON COMMANDER*"',
    0xA903: 'amount printed with the " CR" message',
    0xA907: 'cash += DE tenths of a credit',
    0xA90A: 'raise the " CR" message',
    # New commander.
    0xA976: 'clear all pending messages',
    0xA979: 'copy the 102-byte template to ActiveCommanderRecord',
    0xA97C: 'chart cursor on the current system',
    0xA988: 'select the system under the cursor (the current system)',
    0xA98E: 'patch L_AF01 to NOP: ComputeMarket keeps the saved stock',
    0xA991: 'prices for the saved market',
    0xA995: 'restore LD (HL),A at L_AF01',
    0xA997: 'selected name -> current name (8 characters)',
    0xA9A2: 'template +$5D, 9 bytes -> SunPosition',
    0xA9AE: 'no hyperspace countdown',
    # Short-range chart.
    0xA9CB: '24 text rows',
    0xA9D7: 'token SHORT RANGE CHART',
    0xA9DC: 'colour the prompt row 21',
    0xA9E2: 'window: X-19, 0 on underflow',
    0xA9E7: 'patch window X minimum at L_AA51',
    0xA9ED: 'X+19, $FF on overflow',
    0xA9F2: 'patch window X limit at L_AA55',
    0xA9F8: 'Y-34',
    0xA9FD: 'patch window Y minimum at L_AA5C',
    0xAA03: 'Y+34',
    0xAA08: 'patch window Y limit at L_AA60',
    0xAA0D: 'store to ROM address $00C0: no effect on a 48K Spectrum',
    0xAA10: 'cross-hair vertical clip row $A7',
    0xAA15: 'centre mark arm length 24',
    0xAA1A: 'chart centre: pixel x $61, y $60',
    0xAA24: 'centre mark on the current system',
    0xAA27: 'pass 1: system markers',
    0xAA2D: 'pass 2: system names',
    0xAA33: 'radius in pixels = fuel in tenths (4 pixels per X unit)',
    0xAA3C: 'cursor arm length 16',
    0xAA41: 'draw the chart cursor',
    0xAA44: 'patch the CALL operand at L_AA64 with HL',
    0xAA47: 'generator at system 0',
    0xAA4A: '256 systems',
    0xAA50: 'SMC: X >= window minimum (patched by DrawShortRangeChart)',
    0xAA54: 'SMC: X < window limit (patched by DrawShortRangeChart)',
    0xAA5B: 'SMC: Y >= window minimum (patched by DrawShortRangeChart)',
    0xAA5F: 'SMC: Y < window limit (patched by DrawShortRangeChart)',
    0xAA63: 'SMC: target patched by ForEachChartSystem; it advances the seeds',
    0xAA68: 'outside the window: next system',
    0xAA6F: 'centre column $61',
    0xAA7B: 'C = 4*(X-current X) + $61 - 3',
    0xAA7F: 'centre row $60 (top-down)',
    0xAA8F: 'B = $60 - 2*(Y-current Y) - $0E (ROM y is bottom-up)',
    0xAA91: 'ROM PIXEL-ADD: HL = screen byte, A = pixel within the byte',
    0xAA99: 'patch the shift count at L_AAB6',
    0xAA9C: 'four 8-row marker shapes; s2 high bits 3..4 select one',
    0xAAA2: 'shape offset 0, 8, 16 or 24',
    0xAAA9: '8 pixel rows',
    0xAAB3: 'pixel 0: no shift',
    0xAAB5: 'SMC: B = pixel offset 1..7 (patched by DrawShortRangeSystemMarker)',
    0xAAB7: 'shift the row right, spilling into C',
    0xAABF: 'XOR into the screen byte',
    0xAAC3: 'and the spill into the next byte',
    0xAAC6: 'next pixel line of the screen',
    0xAAD0: 'next character row: L + 32',
    0xAAD6: 'next third: H + 8',
    0xAAE1: 'next system',
    # Names on the short-range chart.
    0xAAEA: 'keep the marker position',
    0xAAEB: 'build the name; advances the seeds',
    0xAAF5: 'find the terminator: C = 8 - length',
    0xAAF8: 'length = (C XOR 7) + 1 for 4..8 letters',
    0xAAFB: 'written but never read',
    0xAAFF: 'x pixel / 8',
    0xAB06: 'text column = x/8 + 1',
    0xAB09: 'ROM y / 8, rounded',
    0xAB15: 'text row = 22 - rounded y/8',
    0xAB1A: 'row free?',
    0xAB23: 'row above, unless it reaches the title rows',
    0xAB31: 'row below',
    0xAB37: 'row flag of TextRow',
    0xAB40: 'mark the row as used',
    0xAB43: 'capital first letter',
    # Galactic chart.
    0xAB53: 'store to ROM address $00C0: no effect on a 48K Spectrum',
    0xAB56: 'cross-hair vertical clip row $98',
    0xAB5B: 'centre mark arm length 16',
    0xAB60: 'cross at the current system (y halved, 24 pixels down)',
    0xAB73: 'fuel range / 4 for DrawScreenCircle',
    0xAB7D: 'fuel range circle',
    0xAB80: 'trim the drawings: clear character rows 0..2',
    0xAB88: 'and character rows 19..23 below the chart',
    0xAB90: 'redraw the screen frame',
    0xAB93: 'cursor arm length 10 (DrawChartCursor: galactic mapping)',
    0xAB9B: 'token GALACTIC CHART',
    0xABA0: 'colour 160 attribute cells from $5A60',
    0xABAA: 'line under the chart: pixel row 152',
    0xABB0: 'generator at system 0',
    0xABB3: '256 systems',
    0xABC1: 'save SP',
    0xABC8: '8 pixel lines',
    0xABCD: 'SP = end of the area in this pixel line',
    0xABD1: '16 pushes = 32 bytes per block',
    0xABD9: 'next pixel line',
    0xABE9: 'Y / 2',
    0xABEB: 'B = ROM y (bottom-up) of 24 + Y/2',
    0xABF0: 'C = x pixel = system X',
    0xABF4: 'ROM PIXEL-ADD',
    0xABF7: 'bit number n = 7 - pixel',
    0xABFC: 'opcode byte of SET n,B with n = 7 - pixel',
    0xAC01: 'patch L_AC05',
    0xAC04: 'SMC: SET n,B (opcode byte patched just above)',
    0xAC07: 'XOR the pixel',
    # Find system by name.
    0xAC7E: 'remember this system\'s seeds',
    0xAC81: 'its name; advances the seeds',
    0xAC8C: 'compare with the typed name',
    0xAC90: 'both ended together: match',
    0xAC9A: 'try all 256 systems',
    0xAC9D: 'carry: not found',
    0xAC9F: 'back to the matching system',
    0xACA2: 'erase cursor, select, redraw cursor',
    # Nearest system.
    0xACB6: 'screens 7 and 8 (the two charts) show the cursor',
    0xACCA: 'best squared distance so far',
    0xACD0: '256 systems',
    0xACDD: 'overflow: too far to compete',
    0xACE4: 'keep the nearest (ties: the later system)',
    0xACEC: 'remember its seeds',
    0xACF9: 'overwritten by UpdateSelectedSystemDistance below',
    0xACFC: 'seeds of the nearest system',
    0xAD02: 'its name',
    0xAD0F: 'from the current system to the cursor',
    0xAD17: 'four twists per system',
    0xAD25: '|cursor X - B|',
    0xAD29: 'dx^2',
    0xAD31: '|cursor Y - A|',
    0xAD34: 'half the Y difference',
    0xAD37: '(dy/2)^2',
    0xAD3B: 'sum; carry on overflow',
    0xAD49: 'overflow: use $FFFF',
    0xAD4E: 'zero distance stays 0',
    0xAD50: 'H = integer part of sqrt(HL) (SquareRootHL gives 256*sqrt)',
    0xAD56: 'distance * 4 = tenths of a light year',
    0xAD67: 'next multiplier bit, most significant first',
    # Name generator.
    0xAD75: 'clear the 8 name bytes',
    0xAD80: 'bit 6 of s0 low: four letter pairs, else three',
    0xAD8E: 'three pairs: only the fourth twist',
    0xAD94: 'pair index from s2 high; 0 adds nothing',
    0xAD99: 'two letters per index',
    0xADA4: 'store the first letter',
    0xADAD: 'a "?" second letter is not stored',
    0xADB3: 'advance the write pointer',
    0xADBD: 's0 + s1',
    0xADCE: 's2 = s0 + s1 + s2; s0 = s1; s1 = s2',
    # Selected-system data.
    0xADE2: 'selected seeds s0',
    0xADE6: 'cursor Y = s0 high',
    0xADE9: 'economy = s0 high AND 7',
    0xADF1: 'selected seeds s1',
    0xADF5: 'cursor X = s1 high',
    0xADFF: 'government = (s1 low >> 3) AND 7',
    0xAE04: 'government 0 or 1?',
    0xAE0B: 'governments 0..1 force economy bit 1',
    0xAE13: 'eco XOR 7, carry clear',
    0xAE18: '+ (s1 high AND 3)',
    0xAE21: '+ gov/2 rounded up (carry = gov bit 0)',
    0xAE22: 'tech = (eco XOR 7) + (s1 high AND 3) + ceil(gov/2)',
    0xAE2F: '4*tech + eco',
    0xAE33: 'population = 4*tech + eco + gov + 1',
    0xAE3B: '(eco XOR 7) + 3',
    0xAE41: 'gov + 4',
    0xAE43: 'HL = (gov+4) * ((eco XOR 7)+3)',
    0xAE4A: '* population',
    0xAE50: 'productivity = ((eco XOR 7)+3)*(gov+4)*population*8',
    0xAE56: 'selected seeds s2',
    0xAE5F: 'zero: only the new line',
    0xAE61: 'token DISTANCE',
    0xAE66: '4-character field',
    0xAE6E: 'carry: print n.n',
    # Market.
    0xAE96: 'low byte of the dust generator state',
    0xAE99: 'fluctuation for this arrival',
    0xAE9C: 'stock destination (kept in the alternate HL)',
    0xAE9F: 'price destination (alternate DE)',
    0xAEA3: '17 commodity records of 4 bytes at CommodityTable',
    0xAEA9: 'E = base price',
    0xAEAD: 'economy factor (bits 0..4 of byte 1)',
    0xAEB2: 'economy 0..7 of the selected system',
    0xAEB7: 'factor * economy',
    0xAEBE: 'B = base quantity',
    0xAEC0: 'C = fluctuation mask',
    0xAEC2: '(fluctuation AND mask) + base quantity',
    0xAECB: 'bit 7 of byte 1 clear: subtract the economy term',
    0xAECF: 'subtract term + 1 (INC before NEG)',
    0xAED7: 'negative: stock 0',
    0xAED8: 'stock quantity 0..63',
    0xAEDB: '(fluctuation AND mask) + base price',
    0xAEE4: 'bit 7 set: subtract the economy term',
    0xAEE8: 'subtract term + 1 (INC before NEG)',
    0xAEEF: 'price * 4 = tenths of a credit',
    0xAEFB: 'store the price word',
    0xAF01: 'SMC: NOP while InitialiseCommander recomputes prices only',
    0xAF07: 'alien items are never stocked',
    0xAF3C: 'sound on (ControlOptions bit 7)?',
    0xAF3F: 'ROM BEEPER pitch value',
    0xAF42: 'ROM BEEPER length in cycles',
    0xAF45: 'ROM BEEPER',
    0xAF51: '$FF: no key yet',
    0xAF57: 'KeyFlagsScreens and the next three latch bytes',
    0xAF66: 'commodity name token',
    0xAF76: 'next price word',
    0xAF82: 'carry: one decimal place',
    0xAF83: '4-character price field',
    0xAF8F: 'next stock byte',
    0xAF98: 'stock zero: print "-"',
    0xAFA3: 'carry: not available here',
    0xAFA5: '2-character stock field',
    0xAFB7: 'carry clear: line printed',
    0xAFBC: 'pre-increment to this commodity',
    0xAFC2: 'none carried: carry set, nothing printed',
    0xAFC7: 'commodity name token',
    0xAFD0: '3-character quantity field',
    0xAFDF: 'carry clear: line printed',
    0xAFEB: "':' after the text",
    0xAFFC: 'capitalise the next letter',
    0xAFFF: 'column 0',
})

SECTIONS = {
    0xA4BD: ('Cockpit status: condition colour, energy, damage, missiles, escape pod',
             'Per-frame flight instrument updates and their state variables.'),
    0xA7DA: ('Screen functions, text and chart state, pending flight messages',
             'Jump table used by L_8F02, shared variables and the 104-byte commander record.'),
    0xA976: ('New commander, charts and the system generator',
             'Short-range and galactic charts, nearest-system selection, name search and the\n'
             'per-system data derived from the three 16-bit seeds.'),
    0xAE96: ('Market prices and trading-screen lines',
             'Price/stock generation from the commodity table and the line printers.'),
}

LABELS = {
    # ------------------------------------------------------------------ $A400..$A4BC
    0xA402: ('RespawnDustSideView', 'verified', """
Respawn the current particle in a side view.  Reached from L_A38D with C =
CurrentScreenId - 1 (1 left, 2 right), DE = record (DustRecordPointer), HL = random state.
Without a vertical rate (DustPitchRate; the side views swap the rates in): X = +120 in
the left view, -120 in the right view (at the edge), Y = random 0..63 with a random
sign, Z = random 0..127.  With a rate Z gets bit 7 ($80..$FF), and AlternatingBits
alternates that pattern with a random X (magnitude bit 3 clear, at most 119) on the top
edge (Y = +63) when DustFlags bit 3 (pitch sign) is set, else the bottom edge (Y = -63).
Record bytes 3..4 (fractions) are kept; StoreRespawnedDust writes Z, advances
DustRecordPointer by 5 and saves the random state.
Evidence: instruction semantics; tools/check_routines.py dust/p5-side-view-respawn."""),
    0xA44C: ('SwapDustParticleXY', 'verified', """
Exchange record bytes 0 and 1 (X and Y, magnitude plus sign bit 7) of the first
DustRemaining particle records at DustParticleRecords; later records are untouched.
Called by MoveAndPlotDust when CurrentScreenId differs from DustLastScreenId.
Clobbers: A, B, C, D, E, H, L.
Evidence: instruction semantics; tools/check_routines.py dust/p5-side-view-respawn."""),
    0xA465: ('AdvanceRandomHL', 'verified', """
Advance the 16-bit generator held in HL with the NextRandomByte recurrence:
t = 2*H + carry, new L = t AND 255, new H = new L + old L + (t >> 8).
Output: A = new H.  B = new L.  Carry is an input and an output.
Evidence: instruction semantics; L_A334 keeps the seed in L_7063 between calls."""),
    0xA46C: ('DustParticleRecords', 'verified', """
16 particle records of 5 bytes: X (bits 0..6 magnitude, bit 7 sign), Y (the same), Z
depth, X fraction, Y fraction (the layout written by StoreAndPlotDust).
MoveAndPlotDust walks them with DustRecordPointer; RespawnDust and RespawnDustSideView
rebuild single records, L_7A88 rebuilds all 16 at launch, SwapDustParticleXY swaps X/Y
when the view changes.  The initial bytes have no meaning.
Evidence: runtime reads and writes cover all 80 bytes; tools/check_routines.py
dust/stardust-update, dust/launch-dust-respawn and dust/p5-side-view-respawn."""),
    0xA4BC: ('ConditionFlashPhase', 'verified', """
Counter of the flashing condition colour: UpdateConditionIndicator increments it on
every call while FlightCondition is $63; its bit 1 selects colour 2 or 0, so the colour
changes every second call."""),
    0xA4BD: ('UpdateConditionIndicator', 'verified', """
Show FlightCondition (the condition colour) and leave it at 4 (green) for the next frame.
0 (docked): return at once.  An empty ForwardShield or AftShield makes it 2 (red) unless
it is $63; $63 (set by UpdateEnergyAndShields while EnergyBank4 is not full) flashes:
colour 2 or 0 from bit 1 of ConditionFlashPhase.
Cockpit views (CurrentScreenId < 4): the colour becomes the attribute (ink on black) of
the four encounter-circle cells, and the missile status cell (row 23, column 7) gets
white ink on paper 0, 4 or 2 for MissileState 0, 1 or 2.
Other screens: two characters at row 1, columns 28..29, in overwrite mode.  Screens 4..8
print codes $21,$22 with attribute $17 for red, otherwise $23,$24 with attribute $10 +
colour (colour 0 shown as 2); screens 9 and above print $23,$24 with the colour itself.
Callers: PrintScreenTitle, ShowCommanderStatus, UpdateFlightMessage.
Evidence: instruction semantics; FlightCondition values (see that variable)."""),
    # ------------------------------------------------------------------ $A559..$A65F
    0xA559: ('UpdateCockpitSystems', 'verified', """
Cockpit-view frame update: return unless CurrentScreenId < 4; draw the
indicators, run UpdateMissileControl, UpdateEscapePod and UseEnergyBomb, clear
the one-shot key bits 1, 2, 3, 5 and 6 (T, F, U, W, Q) of KeyFlagsCombat, then continue
at UpdateEnergyAndShields.  Caller: L_72FD."""),
    0xA572: ('UpdateEnergyAndShields', 'verified', """
Energy and shield update, also called directly by L_72D2 on the non-view screens.
Docked (FlightCondition = 0): return.  EnergyBank4 below $A0 requests the flashing
condition ($63).  Then one RechargeEnergyBanks step, fore damage FrontDamageThisUpdate
applied to ForwardShield and aft damage RearDamageThisUpdate to AftShield
(ApplyShieldDamage), and finally the drain units L_DA17 (+1 while CloakingDeviceActive)
taken four times from the banks (DrainEnergyBanks).
Evidence: instruction semantics; dashboard variables documented in their own entries."""),
    0xA5A6: ('DrainEnergyBanks', 'verified', """
Take C from the energy banks B times, starting with EnergyBank1.  A bank holding less
than C is set to 0 (its rest is lost) and the next bank (2 bytes on) pays C instead;
later repetitions continue with the current bank.  When no bank is left PlayerDeadFlag
= 1 (the game ends) and the routine returns.
Input: B = repetitions, C = amount.  Clobbers: A, B, D, HL."""),
    0xA5C0: ('ApplyShieldDamage', 'verified', """
Apply damage A to the shield at HL (ForwardShield or AftShield).
A = 0: DamageCounter decays by one (not below zero) and return.  A >= $46 first runs
DamageEquipmentOrCargo.  The shield then loses A up to five times; if it cannot pay it
becomes 0, the remaining repetitions (if any) drain A from the energy banks
(DrainEnergyBanks) and DamageCounter grows by 5; at 13 or more DamageEquipmentOrCargo
runs (fall-through).  Clobbers: A, B, C, D, E, HL."""),
    0xA5F0: ('DamageEquipmentOrCargo', 'verified', """
Random damage effect, chosen from bits 2..7 of L_7063 (n = 0..63):
  0      fuel leak (L_D862: fuel = 0, "FUEL LEAK*")
  1..6   destroy E.C.M., fuel scoops, escape pod, energy bomb, energy unit or
         docking computers (if fitted) and raise "<item> DESTROYED"
  7..16  lose one ton of cargo 2..11 (RADIOACTIVES..FURS), if any is carried
  17..63 nothing
Returns at once while a " DESTROYED" message is pending (L_D448 = $FD).
Evidence: tokens $6C+offset and $D0+commodity passed to the message system."""),
    0xA639: ('DamageCounter', 'verified', """
Damage counter: +5 each time damage exhausts L_7046/L_7048 (L_A5C0), -1 per
damage-free call; 13 or more triggers DamageEquipmentOrCargo."""),
    0xA63A: ('RechargeEnergyBanks', 'verified', """
Recharge one step, twice when EnergyUnitFitted is nonzero (CALL NZ then fall-through).
One step (L_A641): increment the first bank below $A0, scanning from L_705A down
to L_7054 in steps of 2; when all four are full, increment L_7046 and L_7048 up to $A0.
Evidence: instruction semantics; the status screen (L_D161) prints ENERGY UNIT for it."""),
    0xA65A: ('IncrementUpToFull', 'verified', """
Increment the byte at HL unless it is already $A0 (full)."""),
    0xA553: ('SetConditionGreen', 'verified', """
Set FlightCondition = 4 (green): the end of UpdateConditionIndicator, also called by it
on the cockpit views."""),
    0xA641: ('RechargeStep', 'verified', """
One recharge step of RechargeEnergyBanks (see there)."""),
    0xA830: ('CargoSlaves', 'verified', """
CargoHold+3 (SLAVES); SpawnRandomEncounter reads it directly."""),
    0xA833: ('CargoNarcotics', 'verified', """
CargoHold+6 (NARCOTICS); SpawnRandomEncounter reads it directly."""),
    0xA837: ('CargoFirearms', 'verified', """
CargoHold+10 (FIREARMS); SpawnRandomEncounter reads it directly."""),
    0xA83C: ('CargoGemStones', 'verified', """
CargoHold+15 (GEM-STONES); the nova reward in SellCargoScreen sets it to 100."""),
    0xAC6D: (None, 'verified', """
Dormant: RLC both bytes of the word at HL (HL ends on the high byte).  Used only by
the dormant L_AC56."""),
    # ------------------------------------------------------------------ indicator tiles
    0xA6A9: ('PrintTileSquare', 'verified', """
Draw a 2x2 tile: four PrintToken codes at DE, top row at column L, row H, then
the next row.  Returns DE advanced by 4 and H + 2."""),
    0xA6AC: ('PrintTileRow', 'verified', """
Set TextColumn/TextRow from HL, print two codes from DE, then H = H + 1."""),
    0xA6B6: ('PrintTwoTileCodes', 'verified', """
Print two PrintToken codes from DE (falls into PrintTileCode)."""),
    0xA6B9: ('PrintTileCode', 'verified', """
Print the PrintToken code at DE, then DE = DE + 1."""),
    0xA6C1: (None, 'verified', """
Two bytes $26,$24: the same codes as the encounter-circle tiles that
DrawCockpitIndicators prints from immediates.  No word in the image points here and
no runtime access was recorded.  INFERRED: an unused copy."""),
    0xA6C3: ('EcmOnIndicatorTiles', 'verified', """
2x2 tile codes for L_A6A9: E indicator with EcmTimer nonzero."""),
    0xA6C7: ('EcmOffIndicatorTiles', 'verified', """
2x2 tile codes: E indicator position with EcmTimer zero."""),
    0xA6CB: ('StationOnIndicatorTiles', 'verified', """
2x2 tile codes: S indicator with StationPresent nonzero."""),
    0xA6CF: ('StationOffIndicatorTiles', 'verified', """
2x2 tile codes: S indicator position with StationPresent zero."""),
    # ------------------------------------------------------------------ missiles
    0xA706: ('UpdateMissileControl', 'verified', """
Missile state machine (MissileState: 0 idle, 1 armed and searching, 2 locked).
No missiles: return.  State 1 with MissileTarget zero and L_DA12 nonzero: lock
(MissileTarget = L_DA12, state 2, ROM BEEPER tone).  Then the one-shot key bits
of L_FC11: bit 1 arms (state 1 unless locked), bit 3 disarms (state 0), bit 2
fires a locked missile: DispatchShipEvent(MissileTarget*16 + 2); on success
state 0, L_707D bit 1 set, MissileCount - 1 and the indicators are redrawn,
otherwise "MISSILE JAMMED" is raised.
Evidence: instruction semantics; DrawMissileIndicators reads MissileCount."""),
    0xA77A: ('EscapePodTimer', 'verified', """
Escape-pod countdown in frames: UpdateEscapePod sets 24 at launch and jumps to
L_7102 when it reaches zero."""),
    0xA77B: ('UpdateEscapePod', 'verified', """
While EscapePodTimer runs, count it down and jump to L_7102 at zero.
Otherwise launch when key bit 6 of L_FC11 is set, EscapePodFitted is nonzero and
L_7061 is zero: timer 24, L_FF0C = $0010, legal score 0, pod used up, 17 bytes
from MarketFluctuation cleared (alien items stay), CommanderFlags bit 5 cleared,
free space 20 or 35 tons, ship event $17, chart cursor = current system.
Evidence: ESCAPE POD token for EscapePodFitted (L_D19C list); runtime escape-pod
scenario; tools/check_routines.py commander/p5-escape-pod."""),
    # ------------------------------------------------------------------ screen table
    0xA7DA: ('ScreenFunctionTable', 'verified', """
16 jump instructions, 3 bytes each.  L_8F02 calls ScreenFunctionTable + 3*A
through a patched CALL, with the stack moved to CockpitBitmap.
Evidence: dispatcher arithmetic; all 16 entries executed in the runtime traces."""),
    # ------------------------------------------------------------------ variables
    0xA80A: ('JumpTunnelMode', 'verified', """
Jump/tunnel mode: 0 none; 1 a normal hyperspace countdown is running (L_D5A6) or the
station tunnel runs (StartStationTunnel, together with TunnelLoopActive); 2 a galactic
hyperspace countdown is running (CheckHyperspaceKeys, galactic hyperdrive fitted).
ExecuteHyperspaceJump takes the galactic path for 2.  Cleared when the arrival tunnel
(FinishHyperspaceTunnel) or the station tunnel (L_7A76) ends.  While nonzero: no
docking-computer docking (L_70CF), cockpit views 1..3 are refused (L_8F30), the chart
keys are ignored (L_713B) and StepTunnelAnimation draws tunnel frames.
Evidence: every static and runtime access; tools/check_routines.py
missions/p5-jump-tunnel-mode."""),
    0xA80B: ('TunnelLoopActive', 'verified', """
1 while the blocking part of a tunnel animation runs: set by StartStationTunnel and by
FinishHyperspaceArrival (arrival rings), cleared by FinishLaunchTunnelLoop,
FinishDockingTunnelLoop and FinishHyperspaceTunnel.  While set PlayHyperspaceArrival
starts the arrival tunnel, L_79E3 runs the ring loop to its end inside one call and
HandleScreenKeys ignores all screen keys.
Evidence: every static and runtime access; tools/check_routines.py
missions/p5-jump-tunnel-mode."""),
    0xA80C: ('CloakingDeviceActive', 'verified', """
Nonzero while the cloaking device is switched on.  L_77D5 toggles it on a key press
only when CommanderFlags bit 6 (cloaking device) is set: 1 -> 0 switches off; from 0
it becomes 1 if bank L_7058 >= $28 (then clears station hostility bit 2 of L_6069
and SharedHostilityAlert), otherwise it is left at $FF.  L_721F, L_7B68 and L_D550
clear it.  Nonzero adds one to the energy drain (L_A584) and stops L_F745.
Evidence: instruction semantics; CLOAKING DEVICE status token for bit 6."""),
    0xA80F: ('MissileState', 'verified', """
Missile state: 0 idle, 1 armed and searching, 2 locked on MissileTarget.
Written by UpdateMissileControl, L_9A46, L_D814 and L_EB8C; its value colours
the missile indicator cell (L_A4E8)."""),
    0xA810: (None, 'verified', """
Three bytes without any code or runtime reference."""),
    0xA813: ('ShapeCentreX', 'verified', """
Centre x for the cross/circle drawers L_D886 and L_8461 (chart centre, current
system, chart cursor).  L_D886 draws from ShapeCentreX - L_D883/2 to + L_D883/2."""),
    0xA814: ('ShapeCentreY', 'verified', """
Centre y (top-down pixel row) for L_D886 and L_8461."""),
    0xA815: ('ShapeSize', 'verified', """
Radius for DrawScreenCircle: FuelLevel on the short-range chart and FuelLevel/4 on the
galactic chart (the fuel range: chart pixels per X unit are 4 and 1), $3D for the
picture of the nova offer (BuyCargoScreen)."""),
    # ------------------------------------------------------------------ commander record
    0xA822: ('CombatScoreFraction', 'verified', """
Combat score, 24 bits: CombatScoreFraction, CombatScoreLow, CombatScoreHigh.
AddCombatScore adds blueprint +$15/+$16 / 2 for each kill (L_DB43).  The status
screen prints RATING from CombatScoreHigh, or from CombatScoreLow when the high
byte is zero (L_D107).  The save path L_D35A also uses it for the security number."""),
    0xA823: ('CombatScoreLow', 'verified', """
Combat score middle byte; a carry out of it raises "RIGHT ON COMMANDER*"."""),
    0xA824: ('CombatScoreHigh', 'verified', """
Combat score high byte; the cloaking-device item adds one (L_A8AA)."""),
    0xA825: ('JumpCounter', 'verified', """
16-bit jump counter incremented by L_D7EE in the hyperspace-arrival checks
(reached only when CurrentGalaxy is nonzero).  The mission-flag tests of
CommanderFlags bits 0..2 follow the increment."""),
    0xA827: ('CurrentGalaxy', 'verified', """
Zero-based galaxy number: L_D62B increments it modulo 8 for a galactic jump and
L_B8DD prints it plus one."""),
    0xA828: ('CashHigh', 'verified', """
Cash, two words: CashHigh counts units of 10000 tenths (1000.0 Cr), CashLow holds
0..9999 tenths.  L_B84D adds with a carry at 10000; L_B877 subtracts; L_B7A8
prints both parts.  The JAMESON template holds 1000 = 100.0 Cr."""),
    0xA82A: ('CashLow', 'verified', """
Cash low word, 0..9999 tenths of a credit (see CashHigh)."""),
    0xA82C: ('MarketFluctuation', 'verified', """
Market fluctuation byte: RandomiseMarket sets it from L_7063 on arrival;
ComputeMarket adds (fluctuation AND mask) to each base price and base quantity."""),
    0xA82D: ('CargoHold', 'verified', """
17 cargo quantities indexed by commodity (token $D0+index names it).
ScoopCargoItem increments CargoHold+A; L_A626 removes damaged cargo; the
inventory lines (PrintCargoLine) and the market code read it."""),
    0xA83E: ('CargoFreeSpace', 'verified', """
Free cargo space in tons: scooping decrements it, cargo lost to damage increments
it, the escape pod resets it to 20 or 35 (LargeCargoBayFitted)."""),
    0xA83F: ('LaserMounts', 'verified', """
Four laser bytes: front, rear, left, right.  0 none, 1 pulse, 2 beam, 3 military,
4 mining: the status screen prints token $60+view then $66+v (v < 3) or $72+v."""),
    0xA843: ('NovaMissionActive', 'verified', """
Nova mission flag (record +$2D).  Set to 1 by the first mission trigger L_D832 (with
CommanderFlags bit 0, red view, fuel leak); cleared, together with ExpandingSunActive,
only by GalacticHyperspaceJump.  While it is set:
- BuyCargoScreen shows "THE SUN IS GOING NOVA* WILL YOU SAVE US (Y/N)?"; 'Y' empties
  the hold, sets free space 0, LargeCargoBayFitted and CommanderFlags bit 5 (refugees);
- every hyperspace jump becomes a galactic jump (NormalHyperspaceJump);
- launching arms the expanding sun (ArmExpandingSun: ExpandingSunActive = 1);
- CheckFlightWarnings broadcasts "MAYDAY * CORIOLIS IN DANGER*" until that launch;
- view attributes keep only the paper and ink bit 1 (L_9291); CockpitRestored paints
  the view red and L_7ACD skips the white reset; the equipment screen does not list
  fuel (L_B56B) and buying item 1 does not fill the tank (L_B5F7);
- SellCargoScreen goes straight to the sell list (no reward yet).
GetEquipmentStatePointer uses this address as the base of the equipment bytes (item n
at +n).  Evidence: message texts; tools/check_routines.py missions/hyperspace-arrival,
missions/p5-nova-mission and missions/p5-nova-offer-and-reward."""),
    0xA844: ('FuelLevel', 'verified', """
Fuel in tenths of a light year (JAMESON: 70).  The status screen prints it after
FUEL with PrintDecimalTenths (L_B8C9); L_D862 empties it for "FUEL LEAK*";
L_D86D stores it after a jump (capped at 70); the charts use it for the range circle."""),
    0xA845: ('MissileCount', 'verified', """
Number of missiles, drawn by DrawMissileIndicators; a launch decrements it."""),
    0xA846: ('LargeCargoBayFitted', 'verified', """
Nonzero: large cargo bay (status token LARGE CARGO BAY; free space 35, not 20)."""),
    0xA847: ('EcmFitted', 'verified', """
Nonzero: E.C.M. system (status token E.C.M.SYSTEM; DamageEquipmentOrCargo offset 0).
The following two bytes have no code reference."""),
    0xA84A: ('FuelScoopsFitted', 'verified', """
Nonzero: fuel scoops (status token FUEL SCOOPS; L_EA71 checks it before scooping)."""),
    0xA84B: ('EscapePodFitted', 'verified', """
Nonzero: escape pod (status token ESCAPE POD; used up by UpdateEscapePod)."""),
    0xA84C: ('EnergyBombFitted', 'verified', """
Nonzero: energy bomb (status token ENERGY BOMB)."""),
    0xA84D: ('EnergyUnitFitted', 'verified', """
Nonzero: energy unit (status token ENERGY UNIT; doubles RechargeEnergyBanks)."""),
    0xA84E: ('DockingComputerFitted', 'verified', """
Nonzero: docking computers (status token DOCKING COMPUTERS)."""),
    0xA84F: ('GalacticHyperdriveFitted', 'verified', """
Nonzero: galactic hyperdrive (status token GALACTIC HYPERSPACE); L_D62B stores A
into it when the galactic jump starts.  The next two bytes have no reference."""),
    0xA852: ('GalaxySeeds', 'verified', """
Three seed words of the current galaxy: L_D62B rotates each byte left for a
galactic jump; LoadGalaxySeedsToGenerator copies them to GeneratorSeeds before
the 256 systems are walked.  JAMESON: $5A4A, $0248, $B753 (system 0 TIBEDIED)."""),
    0xA858: ('CurrentSystemSeeds', 'verified', """
Seeds s0, s1, s2 of the current system, copied from SelectedSystemSeeds on
arrival (L_D6B3).  s0 high is the system Y, s1 high its X (JAMESON: Lave, X 20,
Y 173)."""),
    0xA859: ('CurrentSystemY', 'verified', """
Current system Y (s0 high byte); also written by L_D7B4 and L_D68B."""),
    0xA85B: ('CurrentSystemX', 'verified', """
Current system X (s1 high byte); also written by L_D7B4 and L_D68B."""),
    0xA85E: ('CurrentTechLevel', 'verified', """
Current system tech level, copied from SelectedSystemTechLevel on arrival (L_D6B3);
read by the equipment screen (L_B53F).  The JAMESON template holds 5, while the
generator gives Lave 4 (a simulator check in tools/check_routines.py)."""),
    0xA85F: ('CurrentGovernment', 'verified', """
Current system government, copied from SelectedSystemGovernment on arrival."""),
    0xA860: ('MarketStock', 'verified', """
17 station stock quantities, written by ComputeMarket (alien items always 0) and
printed by PrintMarketLine through StockPointer."""),
    0xA871: ('InvasionMissionState', 'verified', """
Invasion mission state (record +$5B):
  0     none;
  1     set by the third mission trigger L_D853 (CommanderFlags bit 2): CheckFlightWarnings
        broadcasts "MAYDAY * <system> INVADED*", L_F684 may add a Python trader;
  2     after the next arrival.  In states 1 and 2 docking shows the GalCop offer
        (OfferSpecialMission): 'Y' sets CommanderFlags bit 7 (ECM jammer) and state 3,
        anything else state 0;
  3     accepted;
  4     arrival at the galaxy's first system (seeds equal GalaxySeeds; any nonzero state
        there, L_D7B4), 4 -> 3 on other arrivals.  UpdateObjects makes the station
        hostile, L_F684 adds Thargoids, AI ECM stays off against the jammer, and
        docking ends the game with " THARGON" (L_782B);
  $0C   a missile reached the station in state 4 (the hit code after L_F94A: SET 3,
        AddCombatScore $FFFF, station +$26 bit 7, the station explodes);
  5     the next arrival after that (L_D7B4); docking then awards +256 combat score,
        CommanderFlags bit 3 and the HIGHEST HONOUR message, state 0 (AwardHighestHonour).
GalacticHyperspaceJump clears it.  The data screen of that first system reports the
invasion while it is nonzero (DisplaySystemData, message $DE).
Evidence: message texts; tools/check_routines.py missions/hyperspace-arrival and
missions/p5-invasion-mission."""),
    0xA872: ('CommanderFlags', 'verified', """
Flag byte (record +$5C):
  bit 0  nova mission triggered (L_D832, jump counter low byte >= $20 outside galaxy 0)
  bit 1  cloaked-Asp mission triggered (>= $80); SpawnRandomEncounter creates the
         special Asp while bit 6 is still clear
  bit 2  invasion mission triggered (>= $FE, L_D853)
  bit 3  invasion mission completed (AwardHighestHonour); part of the security number
  bit 4  no access found
  bit 5  refugees on board: set when the nova offer is accepted, cleared by the reward
         in SellCargoScreen or by the escape pod; the inventory prints REFUGEES and
         BuyCargoScreen refuses trading
  bit 6  cloaking device: set by scooping the $FF canister (ScoopCloakingDevice);
         status prints CLOAKING DEVICE, ToggleCloak needs it
  bit 7  ECM jammer: set when the invasion mission is accepted; status prints it
L_D7EE tests bits 0..2 (only the first clear one); AccessMenuSave folds bits 3 and 6
into the security number.  Evidence: instruction semantics and message texts;
tools/check_routines.py missions/hyperspace-arrival, missions/special-encounter,
missions/p5-nova-offer-and-reward."""),
    0xA873: ('SavedSunPosition', 'verified', """
Nine bytes: L_D35A copies L_7065..L_706D here before saving; a new commander
copies the template copy back (InitialiseCommander).  Not a stored security code:
the security number is computed and printed after the save (L_D35A)."""),
    0xA87C: ('ExpandingSunActive', 'verified', """
Tape byte +$66, reused at run time as the expanding-sun flag: ArmExpandingSun sets it
at launch while NovaMissionActive is set; UpdateExpandingSun only runs while it is
nonzero (sun radius +2 and CabinTemperature +1 per call; radius 256 ends the game);
CheckFlightWarnings sends "MAYDAY * CORIOLIS IN DANGER*" only while it is zero.
Cleared by StartNewGame and, with NovaMissionActive, by GalacticHyperspaceJump.
Evidence: instruction semantics; tools/check_routines.py missions/p5-nova-mission."""),
    0xA87D: ('ChartCursorX', 'verified', """
Chart cursor X (tape byte +$67 reused).  The cursor functions move it; selecting a
system sets it to the system X; L_D7B4 makes it the current X on arrival."""),
    0xA87E: ('ChartCursorY', 'verified', """
Chart cursor Y, just after the tape record (not saved)."""),
    0xA87F: ('PendingMessageTable', 'verified', """
Nine 2-byte message slots scanned by L_D4A0 and cleared by L_D563.
Byte 0: bit 7 = pending, bits 0..6 = text column; byte 1: PrintToken code.
This first slot is "MISSILE JAMMED" (raised by UpdateMissileControl).
Slot 7 is LeadingZeroFlag/NumberFieldWidth, which never have bit 7 set."""),
    0xA881: ('IncomingMissileMessage', 'verified', """
Message slot "INCOMING MISSILE", raised by L_F79D."""),
    0xA883: ('TargetLostMessage', 'verified', """
Message slot "TARGET LOST", raised by L_EB8C."""),
    0xA885: ('EquipmentDestroyedMessage', 'verified', """
Message slot $FD " DESTROYED": L_D4E5 prints the item token from L_D44B first."""),
    0xA887: ('BountyMessage', 'verified', """
Message slot $E2 " CR": L_D4F7 prints the amount from L_D449 first."""),
    0xA889: ('CargoScoopedMessage', 'verified', """
Message slot whose token ScoopCargoItem stores (commodity or CLOAKING DEVICE)."""),
    0xA88B: ('RightOnCommanderMessage', 'verified', """
Message slot "RIGHT ON COMMANDER*", raised by AddCombatScore."""),
    0xA88D: ('LeadingZeroFlag', 'verified', """
PrintDecimalHL: 1 while leading zero digits are skipped (also message slot 7)."""),
    0xA88E: ('NumberFieldWidth', 'verified', """
PrintDecimalHL field width for space padding; reset to zero after printing."""),
    0xA88F: ('FuelLeakMessage', 'verified', """
Message slot "FUEL LEAK*", raised by L_D862."""),
    0xA891: ('LetterCaseMode', 'verified', """
PrintCharacter letter case: 1 capitals, 2 lower case, other values title case."""),
    0xA892: ('CapitaliseNextFlag', 'verified', """
Title case: 1 capitalises the next letter (set by NewLine and non-letters)."""),
    0xA893: ('CapitaliseOnce', 'verified', """
Nonzero capitalises one letter in case modes 0 and 2, then clears."""),
    0xA894: ('TextRedirectFlag', 'verified', """
1: PrintCharacter passes characters to L_BCFC instead of the screen.
Set by L_BD9D, cleared by L_BDB9.  The next two bytes have no reference."""),
    0xA897: (None, 'verified', """
Dormant jump vectors: JP instructions to TriggerFuelLeak, ScoopCargoItem, AwardBounty,
AddCombatScore and DamageEquipmentOrCargo, with MissileTarget and three unused bytes
between them.  No word in the image points at any of them and none is executed in the
recorded 48K scenarios.  Decoded as code so that the targets stay symbolic.
INFERRED: remains of an earlier vector table."""),
    0xA89A: ('MissileTarget', 'verified', """
Object slot locked by the missile (from L_DA12); 0 = none.  Read by L_EB8C."""),
    0xA8A4: (None, 'verified', """
Three bytes without any code or runtime reference."""),
    # ------------------------------------------------------------------ scooping etc.
    0xA8AA: ('ScoopCloakingDevice', 'verified', """
Scooped item $FF (the canister of the special Asp): set CommanderFlags bit 6 (cloaking
device), add 256 to the combat score and post token CLOAKING DEVICE in the scooped-cargo
message; the contraband check that follows ignores $FF."""),
    0xA8B7: ('ScoopCargoItem', 'verified', """
Entered by JP from L_EAD5 after the fuel-scoop and free-space checks, with A =
commodity 0..16 or $FF.  Commodity: CargoFreeSpace - 1, CargoHold+A + 1, post
the scooped message with token $D0+A, then AddContrabandPenalty for one ton."""),
    0xA8D4: ('AddContrabandPenalty', 'verified', """
Raise PlayerLegalScore for B tons of commodity A: slaves (3) and narcotics (6)
add 4*B, firearms (10) add 2*B, others nothing; saturates at 255.
Callers: ScoopCargoItem, L_B3CE (buying).
Evidence: tools/check_routines.py economy/contraband-penalty."""),
    0xA8EE: ('AddCombatScore', 'verified', """
Add DE to the 24-bit combat score (fraction, low byte with carry); a carry into
CombatScoreHigh increments it and raises "RIGHT ON COMMANDER*".
Callers: L_DB43 (kill), L_F94A."""),
    0xA900: ('AwardBounty', 'verified', """
DE = bounty in tenths of a credit (blueprint +8, L_DB43).  Zero: return.
Otherwise keep it in L_D449, add it to the cash (L_B84D) and raise " CR"."""),
    # ------------------------------------------------------------------ template
    0xA96D: (None, 'verified', """
Template +$5D: nine bytes copied to L_7065..L_706D by InitialiseCommander."""),
    # ------------------------------------------------------------------ new commander
    0xA976: ('InitialiseCommander', 'verified', """
Start a commander from CommanderTemplateBuffer (called by L_721F): clear the
pending messages, copy the 102 template bytes (L_7C2D), put the chart cursor on
the current system and select it, recompute the prices only (L_AF01 patched to
NOP keeps the saved stock), copy the selected name to CurrentSystemName, copy
template +$5D (9 bytes) to L_7065 and clear L_D573."""),
    # ------------------------------------------------------------------ short-range chart
    0xA9B2: ('ShortRangeChartRows', 'verified', """
24 row-used flags for the short-range chart names, cleared by DrawShortRangeChart
and set to $FF by PrintNameInFreeRow.  The initial bytes are stale code."""),
    0xA9CA: ('DrawShortRangeChart', 'verified', """
Short-range chart (screen function 4): clear the row flags and screen, print token
SHORT RANGE CHART, patch the window X-19..X+19 / Y-34..Y+34 around the current
system, draw the centre cross (L_D886), the markers and names of all systems in the
window (ForEachChartSystem), the fuel circle (L_8461) and the cursor (L_B1C0).
Evidence: runtime local-chart scenario."""),
    0xAA44: ('ForEachChartSystem', 'verified', """
Walk the 256 systems of the galaxy: call routine HL (patched into L_AA64) for each
system whose X/Y lie in the patched window; otherwise advance with
NextGeneratorSystem.  The called routine must advance the seeds itself."""),
    0xAA6F: ('GetShortRangeChartPixel', 'verified', """
Screen position of the generator's system on the short-range chart:
C = 4*(X - CurrentSystemX) + $5E, B = $52 - 2*(Y - CurrentSystemY) (ROM y),
then ROM PIXEL-ADD.  Output: HL screen byte, A pixel 0..7, BC kept."""),
    0xAA96: ('DrawShortRangeSystemMarker', 'verified', """
XOR an 8-row marker (one of four 8-byte shapes at L_91D2, chosen by bits 3..4 of
GeneratorSeed2High) at the system position, then NextGeneratorSystem."""),
    0xAAE4: (None, 'verified', """
Two bytes without any code or runtime reference."""),
    0xAAE6: (None, 'verified', """
Name length stored by PrintShortRangeSystemName; never read."""),
    0xAAE7: ('PrintShortRangeSystemName', 'verified', """
Print the generator system's name near its marker: GenerateSystemName (advances
the seeds), column x/8+1, row 22-y/8, else the row above (if >= 3), else below."""),
    0xAB34: ('PrintNameInFreeRow', 'verified', """
If ShortRangeChartRows[TextRow] is zero, mark it and print GeneratedSystemName
with a capital first letter; returns carry set.  Occupied: carry clear."""),
    # ------------------------------------------------------------------ galactic chart
    0xAB4E: ('DrawGalacticChart', 'verified', """
Galactic chart (screen function 3): clear, cross at the current system (x, 24+y/2),
fuel circle (radius FuelLevel/4), clear character rows 0..2 and 19..23 with
ClearScreenLinesWithStack (trimming the cross and the circle to the chart area),
frame, cursor, token GALACTIC CHART, colours, a line at pixel row 152, then plot all
256 systems (PlotGalacticChartSystem).  Evidence: runtime galactic-chart scenario."""),
    0xABC0: ('ClearScreenLinesWithStack', 'verified', """
Clear the A*32 bytes below HL (HL-A*32..HL-1), then the same range in the next seven
pixel lines (H+1..H+7), by pushing zero words with SP.  Interrupts are disabled
meanwhile; SP is saved in StackClearSavedSP.  Clobbers A, B, C, D, E, H."""),
    0xABE3: ('StackClearBlockCount', 'verified', """
Block count A of ClearScreenLinesWithStack."""),
    0xABE4: ('StackClearSavedSP', 'verified', """
Stack pointer saved by ClearScreenLinesWithStack."""),
    0xABE6: ('PlotGalacticChartSystem', 'verified', """
XOR one pixel at (GeneratorSystemX, 24 + GeneratorSystemY/2) using ROM PIXEL-ADD
and a patched SET n,B instruction."""),
    0xAC0A: ('ClampToZero', 'verified', """
Return A = 0 (window bound below zero)."""),
    0xAC0C: ('ClampToFF', 'verified', """
Return A = $FF (window bound above 255)."""),
    # ------------------------------------------------------------------ generator state
    0xAC0F: ('SelectedSystemSeeds', 'verified', """
Seeds s0, s1, s2 of the selected (hyperspace target) system, set by
DeriveSelectedSystemData and copied to CurrentSystemSeeds on arrival (L_D6B3)."""),
    0xAC11: ('SelectedSystemSeed1', 'verified', """
Selected system s1 (word)."""),
    0xAC13: ('SelectedSystemSeed2', 'verified', """
Selected system s2 (word); L_BA8A reads it for the species text."""),
    0xAC15: ('GeneratorSeeds', 'verified', """
Working seeds s0, s1, s2 of the system generator; TwistGeneratorSeeds advances
them, four twists per system."""),
    0xAC16: ('GeneratorSystemY', 'verified', """
Generator s0 high byte: the system Y."""),
    0xAC17: ('GeneratorSeed1', 'verified', """
Generator s1 (word)."""),
    0xAC18: ('GeneratorSystemX', 'verified', """
Generator s1 high byte: the system X."""),
    0xAC19: ('GeneratorSeed2', 'verified', """
Generator s2 (word); its high byte selects name letter pairs."""),
    0xAC1A: ('GeneratorSeed2High', 'verified', """
Generator s2 high byte."""),
    0xAC1B: ('SavedGeneratorSeeds', 'verified', """
Copy of GeneratorSeeds (SaveGeneratorSeeds / RestoreGeneratorSeeds)."""),
    0xAC21: ('DescriptionSeed1', 'verified', """
First word of the planet-description generator (NextDescriptionRandom)."""),
    0xAC23: ('DescriptionSeed2', 'verified', """
Second word of the planet-description generator."""),
    0xAC25: ('NameInputBuffer', 'verified', """
Typed name, zero-terminated: the system name searched by FindSystemByName
(function 15, L_B0E9) and the tape-load name check in L_D326."""),
    0xAC2E: ('GeneratedSystemName', 'verified', """
Name built by GenerateSystemName (8 characters + zero)."""),
    0xAC37: ('CurrentSystemName', 'verified', """
Name of the current system; cleared by the witchspace path L_D68B."""),
    0xAC40: ('SelectedSystemName', 'verified', """
Name of the selected system (CopyGeneratedNameToSelected)."""),
    0xAC49: ('SelectedSystemDistance', 'verified', """
Distance from the current system to the cursor in tenths of a light year,
printed by PrintSelectedSystemDistance; compared with FuelLevel by L_D65A."""),
    0xAC4B: ('SelectedSystemEconomy', 'verified', """
Economy 0..7 of the selected system (data screen: RICH/AVERAGE/POOR/MAINLY +
INDUSTRIAL/AGRICULTURAL); also the market economy term."""),
    0xAC4C: ('SelectedSystemGovernment', 'verified', """
Government 0..7 (data screen token $B1+value: ANARCHY .. CORPORATE STATE)."""),
    0xAC4D: ('SelectedSystemTechLevel', 'verified', """
Tech level (data screen prints value + 1 after TECH.LEVEL)."""),
    0xAC4E: ('SelectedSystemPopulation', 'verified', """
Population in tenths of a billion (data screen)."""),
    0xAC4F: ('SelectedSystemProductivity', 'verified', """
Gross productivity word in M CR (data screen)."""),
    0xAC51: (None, 'verified', """
Two bytes without any code or runtime reference."""),
    0xAC53: ('NameSearchCounter', 'verified', """
System counter of FindSystemByName (256 tries)."""),
    0xAC54: ('NameWritePointer', 'verified', """
Output pointer of GenerateSystemName."""),
    0xAC56: (None, 'verified', """
Dormant code: CurrentGalaxy = (CurrentGalaxy + 1) AND 7, then rotate each byte of the
three GalaxySeeds words left (L_AC6D per word): the same galaxy step as
GalacticHyperspaceJump, without its other effects.  No word in the image points here
and it never runs in the recorded scenarios.  INFERRED: a superseded copy.
stationslotfix=yes replaces these 33 bytes (with L_AC6D) with StationSlotRoof."""),
    # ------------------------------------------------------------------ search/select
    0xAC77: ('FindSystemByName', 'verified', """
Search the galaxy for the system named in NameInputBuffer.  Found: select it
(seeds, data, cursor redrawn, SelectedSystemName, distance) and return carry
clear.  Not found after 256 systems: carry set.
Evidence: tools/check_routines.py economy/find-system-and-distance (LAVE found at X 20,
Y 173; an unknown name returns carry)."""),
    0xACB1: ('NearestSystemDistance', 'verified', """
Smallest squared cursor distance found by SelectNearestSystem."""),
    0xACB3: ('SnapCursorToNearestSystem', 'verified', """
SelectNearestSystem, erasing and redrawing the cursor (DrawChartCursor) when
CurrentScreenId is 7 or 8 (the galactic and the short-range chart: screen keys I and O
reach screen functions 3 and 4).  Callers: DisplaySystemData, L_D5A6, L_D62B,
function 14."""),
    0xACC7: ('SelectNearestSystem', 'verified', """
Select the system nearest to ChartCursorX/Y (dx^2 + (dy/2)^2; ties go to the later
system): its seeds become SelectedSystemSeeds, its data is derived, the cursor
moves onto it, its name goes to SelectedSystemName, then the distance from the
current system is computed (falls into UpdateSelectedSystemDistance)."""),
    0xAD08: ('UpdateSelectedSystemDistance', 'verified', """
SelectedSystemDistance = 4 * isqrt(dx^2 + (dy/2)^2) between the current system
and the cursor.  Returns carry clear.
Evidence: tools/check_routines.py economy/find-system-and-distance (Lave to TIBEDIED
= 176)."""),
    0xAD17: ('NextGeneratorSystem', 'verified', """
Advance GeneratorSeeds to the next system (four twists)."""),
    0xAD21: ('ChartDistanceSquared', 'verified', """
HL = (ChartCursorX - B)^2 + ((ChartCursorY - A)/2)^2 with absolute differences.
Carry set on 16-bit overflow."""),
    0xAD3D: ('AbsoluteDifference', 'verified', """
A = |A - B| (B is changed when A < B)."""),
    0xAD45: ('StoreSystemDistance', 'verified', """
SelectedSystemDistance from the squared distance in HL (carry: overflow, use $FFFF):
0 stays 0, otherwise 4 * (integer part of sqrt(HL)) from SquareRootHL (256*sqrt in HL)."""),
    0xAD5C: ('MultiplyAByD', 'verified', """
HL = A * D (8 x 8 bits, shift and add).  Clobbers A, B (0), D, E."""),
    0xAD6F: ('GenerateSystemName', 'verified', """
Build the generator system's name in GeneratedSystemName: three letter pairs, or
four when bit 6 of s0 low is set, taken from the pair table L_FBC3 by s2 high AND
$1F (0 adds nothing; a '?' second letter is dropped).  Leaves the seeds advanced
to the next system.  Evidence: tools/check_routines.py economy/galaxy-system-names
(systems 0 and 7 are TIBEDIED and LAVE)."""),
    0xAD90: ('AppendNameLetterPair', 'verified', """
Append the pair selected by s2 high AND $1F (if nonzero), then twist the seeds."""),
    0xADB6: ('TwistGeneratorSeeds', 'verified', """
s0, s1, s2 = s1, s2, s0 + s1 + s2 (16-bit words, carry discarded)."""),
    0xADD3: ('CopyGeneratedNameToSelected', 'verified', """
Copy 8 bytes from GeneratedSystemName to SelectedSystemName."""),
    0xADDF: ('DeriveSelectedSystemData', 'verified', """
From GeneratorSeeds: SelectedSystemSeeds, ChartCursorY = s0 high, ChartCursorX =
s1 high, economy, government, tech level, population and productivity.
Evidence: data-screen tokens; tools/check_routines.py economy/find-system-and-distance
gives Lave 5, 3, 4, 25, 7000."""),
    0xAE5A: ('PrintSelectedSystemDistance', 'verified', """
If SelectedSystemDistance is nonzero print DISTANCE: n.n LIGHT YEARS; then
NewLine."""),
    0xAE79: ('LoadGalaxySeedsToGenerator', 'verified', """
Copy GalaxySeeds to GeneratorSeeds (system 0)."""),
    0xAE81: ('SaveGeneratorSeeds', 'verified', """
Copy GeneratorSeeds to SavedGeneratorSeeds."""),
    0xAE89: ('RestoreGeneratorSeeds', 'verified', """
Copy SavedGeneratorSeeds to GeneratorSeeds."""),
    0xAE95: ('MarketEconomyTerm', 'verified', """
Economy factor * SelectedSystemEconomy for the current commodity (ComputeMarket)."""),
    # ------------------------------------------------------------------ market
    0xAE96: ('RandomiseMarket', 'verified', """
MarketFluctuation = low byte of AuxRandomSeed (the dust generator state), then
ComputeMarket.  Called on arrival by ArriveInTargetSystem, so the market changes once
per jump."""),
    0xAE9C: ('ComputeMarket', 'verified', """
For the 17 four-byte commodity records at CommodityTable (base price, byte 1 = bit 7
sign + bits 0..4 economy factor, base quantity, mask), with term = factor *
SelectedSystemEconomy and f = MarketFluctuation AND mask (all 8-bit):
  stock = base quantity + f - (term + 1) if bit 7 is clear, + term if set; 0 when the
          result has bit 7 set, then AND $3F -> MarketStock;
  price = base price + f + term if bit 7 is clear, - (term + 1) if set; 4 * price
          (tenths of a credit) -> MarketPrices.
Alien items (MarketStock+16) are then set to 0.  L_AF01 can be patched to NOP to keep
the stock (InitialiseCommander).
Evidence: tools/check_routines.py economy/market and economy/p5-market-model (model of
all 17 records for every economy and 64 fluctuations)."""),
    0xAF0C: (None, 'verified', """
Two bytes without a direct access.  L_B52E and L_D07D load this address as
MarketPrices - 2 for the pre-incremented PricePointer."""),
    0xAF0E: ('MarketPrices', 'verified', """
17 price words in tenths of a credit (ComputeMarket); the initial bytes are stale."""),
    0xAF30: ('CurrentCommodity', 'verified', """
Commodity index of the printed line: token $D0 + value names it."""),
    0xAF31: ('CargoPointer', 'verified', """
Pre-incremented pointer into CargoHold for PrintCargoLine."""),
    0xAF33: ('PricePointer', 'verified', """
Pointer into MarketPrices, advanced by 2 before each use (PrintMarketLine)."""),
    0xAF35: ('StockPointer', 'verified', """
Pointer into MarketStock, advanced by 1 before each use."""),
    0xAF37: ('SavedTextPosition', 'verified', """
TextColumn/TextRow word saved by L_B0B5 and restored by L_B0DE."""),
    0xAF39: ('BeepIfSoundOn', 'verified', """
If bit 7 of ControlOptions (sound) is set, sound ROM BEEPER with HL = $0080 (pitch),
DE = $0060 (length).  Used after messages, prompts and errors."""),
    0xAF48: ('WaitForKeyPress', 'verified', """
Wait 20 frames (L_B0AB), clear the input flags, then wait until L_FC13 is not $FF.
Output: A = L_FC13 (L_D301 compares it with the digits '1'..'3')."""),
    0xAF56: ('ClearInputFlags', 'verified', """
With interrupts disabled, clear the four bytes L_FC0E..L_FC11."""),
    0xAF63: ('PrintMarketLine', 'verified', """
One market line for CurrentCommodity: name, unit (L_B06F), price from
PricePointer + 2 (n.n), stock from StockPointer + 1 with its unit, or '-' when
zero (then carry set; otherwise carry clear).  Caller: L_D0AB."""),
    0xAFB9: ('PrintCargoLine', 'verified', """
CargoPointer + 1: if that cargo quantity is zero return carry set; otherwise
print the commodity name, the quantity at column 13 and its unit; carry clear."""),
    # ------------------------------------------------------------------ dormant vectors
    0xA89B: (None, 'verified', """
Dormant vector: JP ScoopCargoItem (see L_A897).
fuelfix=yes replaces $A89B..$A8A9 (these vectors and the fragment after them) with
FuelEconomy."""),
    0xA89E: (None, 'verified', """
Dormant vector: JP AwardBounty (see L_A897)."""),
    0xA8A1: (None, 'verified', """
Dormant vector: JP AddCombatScore (see L_A897)."""),
    0xA8A7: (None, 'verified', """
Dormant vector: JP DamageEquipmentOrCargo (see L_A897)."""),
}

DATA = {
    0xA46C: (0xA4BC, 'bytes', 5),
    0xA4BC: (0xA4BD, 'bytes', 1),
    0xA639: (0xA63A, 'bytes', 1),
    0xA6C1: (0xA6C3, 'bytes', 2),
    0xA6C3: (0xA6D3, 'bytes', 4),
    0xA77A: (0xA77B, 'bytes', 1),
    0xA80A: (0xA80F, 'bytes', 1),
    0xA80F: (0xA810, 'bytes', 1),
    0xA810: (0xA813, 'bytes', 3),
    0xA813: (0xA816, 'bytes', 1),
    0xA87E: (0xA87F, 'bytes', 1),
    0xA87F: (0xA891, 'bytes', 2),
    0xA891: (0xA897, 'bytes', 1),
    0xA89A: (0xA89B, 'bytes', 1),
    0xA8A4: (0xA8A7, 'bytes', 3),
    0xA9B2: (0xA9CA, 'bytes', 8),
    0xAAE4: (0xAAE6, 'bytes', 2),
    0xAAE6: (0xAAE7, 'bytes', 1),
    0xABE3: (0xABE4, 'bytes', 1),
    0xABE4: (0xABE6, 'words', 1),
    0xAC0F: (0xAC15, 'words', 1),
    0xAC15: (0xAC1B, 'bytes', 1),
    0xAC1B: (0xAC21, 'words', 3),
    0xAC21: (0xAC25, 'words', 1),
    0xAC25: (0xAC2E, 'text', 9),
    0xAC2E: (0xAC37, 'text', 9),
    0xAC37: (0xAC40, 'text', 9),
    0xAC40: (0xAC49, 'text', 9),
    0xAC49: (0xAC4B, 'words', 1),
    0xAC4B: (0xAC4F, 'bytes', 1),
    0xAC4F: (0xAC51, 'words', 1),
    0xAC51: (0xAC53, 'bytes', 2),
    0xAC53: (0xAC54, 'bytes', 1),
    0xAC54: (0xAC56, 'words', 1),
    0xACB1: (0xACB3, 'words', 1),
    0xAE95: (0xAE96, 'bytes', 1),
    0xAF0C: (0xAF0E, 'bytes', 2),
    0xAF0E: (0xAF30, 'words', 1),
    0xAF30: (0xAF31, 'bytes', 1),
    0xAF31: (0xAF39, 'words', 1),
}

SEEDS = {
    0xA7F5: 'ScreenFunctionTable entry 9: JP executed at run time (runtime-xrefs.json)',
    0xA7F8: 'ScreenFunctionTable entry 10: JP executed at run time',
    0xA7FB: 'ScreenFunctionTable entry 11: JP executed at run time',
    0xA7FE: 'ScreenFunctionTable entry 12: JP executed at run time',
    0xA801: 'ScreenFunctionTable entry 13: JP executed at run time',
    0xA804: 'ScreenFunctionTable entry 14: JP executed at run time',
    0xA897: 'JP opcode to the routine entry L_D862 (dormant vector)',
    0xA89B: 'JP opcode to the routine entry L_A8B7 (dormant vector)',
    0xA89E: 'JP opcode to the routine entry L_A900 (dormant vector)',
    0xA8A1: 'JP opcode to the routine entry L_A8EE (dormant vector)',
    0xA8A7: 'JP opcode to the routine entry L_A5F0 (dormant vector)',
    0xAC56: 'coherent dormant routine ending in RET; duplicates L_D62B/L_D64F',
}

OPERANDS = {
    0xA626: 'CargoHold-4',       # LD HL,$A829: plus A = 6..15 -> CargoHold+2..+11
    0xAF07: 'MarketStock+16',    # LD HL,$A870: alien items stock
    0xAC64: 'GalaxySeeds+2',     # dormant code: second seed word
    0xAC6A: 'GalaxySeeds+4',     # dormant code: third seed word
}

# The commander record is a fixed tape format; named fields must keep their offsets.
ASSERTS = {
    'r5-cmdr-combat-score': ('CombatScoreFraction-ActiveCommanderRecord = $0C',
                             'commander record: combat score at +$0C'),
    'r5-cmdr-galaxy': ('CurrentGalaxy-ActiveCommanderRecord = $11',
                       'commander record: galaxy at +$11'),
    'r5-cmdr-cash': ('CashHigh-ActiveCommanderRecord = $12', 'commander record: cash at +$12'),
    'r5-cmdr-cargo': ('CargoHold-ActiveCommanderRecord = $17', 'commander record: cargo at +$17'),
    'r5-cmdr-fuel': ('FuelLevel-ActiveCommanderRecord = $2E', 'commander record: fuel at +$2E'),
    'r5-cmdr-galaxy-seeds': ('GalaxySeeds-ActiveCommanderRecord = $3C',
                             'commander record: galaxy seeds at +$3C'),
    'r5-cmdr-system-seeds': ('CurrentSystemSeeds-ActiveCommanderRecord = $42',
                             'commander record: current system seeds at +$42'),
    'r5-cmdr-stock': ('MarketStock-ActiveCommanderRecord = $4A',
                      'commander record: station stock at +$4A'),
    'r5-cmdr-flags': ('CommanderFlags-ActiveCommanderRecord = $5C',
                      'commander record: flags at +$5C'),
    'r5-cmdr-cursor-x': ('ChartCursorX-ActiveCommanderRecord = $67',
                         'last tape byte is reused as the chart cursor X'),
    'r5-short-range-rows': ('DrawShortRangeChart-ShortRangeChartRows = 24',
                            'DrawShortRangeChart clears 24 row flags'),
    'r5-market-prices': ('CurrentCommodity-MarketPrices = 17*2',
                         'ComputeMarket stores 17 price words'),
}
