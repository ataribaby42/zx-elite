"""Check iffunit=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat iffunit=yes verify=no
    python tools/check_iff_unit.py
    python tools/check_iff_unit.py --emulator

iffunit=yes removes the energy bomb and puts an I.F.F. unit in its place
(src/iff-unit.asm).  The simulator part runs the assembled image and a
baseline whose eight replaced parts are restored from the reference tape (with
no other option selected the baseline must equal the reference image) with the
supplied 48K ROM in SkoolKit's Z80 simulator:

- layout: every changed byte lies inside the eight parts;
- text: PrintToken renders every dictionary code ($0E..$1F, $60..$7F,
  $A0..$FF, tokens 0..145) as the original, except code $71 (token 113),
  which reads I.F.F. UNIT instead of ENERGY BOMB;
- IffScannerContactEnergy against a model for every role byte, hostile and
  other behaviour bits, missile targets, blink phases and fitted values;
- DrawScannerContacts with a hostile station, a pirate, a trader, a missile
  aimed at the player, a player-style missile, a hostile canister and a
  Fer-de-Lance, calm and hostile: the screen equals the original drawing of all
  objects, or in the dark half of the blink with the unit fitted the original
  drawing of the non-threats only;
- the bomb is gone: W sets no key bit, UpdateCockpitSystems with W and the
  unit fitted only advances the blink clock, and UpdateObjects ignores a
  nonzero EnergyBombPending byte.

--emulator loads release/elite-128k.tap through the 48K ROM (build the option
with the default tapfile).  A docked run buys item 9 and shows I.F.F. UNIT in
the equipment list and on the status screen.  Flight runs put a pirate or a
trader near the player with test-only pokes and sample ScannerContactsDrawn at
every frame interrupt: with the unit fitted the pirate's contact blinks, the
trader's does not, and without the unit nothing blinks.  W then leaves the
pirate alive, while the reference tape's energy bomb destroys it.  The
reference tape run uses the option build's symbol addresses, which the layout
check proves to be identical outside the replaced parts; it is skipped when
another option (such as ship=adder) is built as well.

Mission situations then start from the RAM of a launch run, taken at the start
of MainLoop: the baseline (an unused energy bomb) and the option image (the
I.F.F. unit fitted) run up to 300 main loops each in the simulator after the
same set-up.  After every loop their RAM must be identical except the scanner
columns of the screen, the scanner work bytes, the replaced parts and the test
stack:
- mission 2: the real special encounter, a cloaked Asp and two Sidewinders;
- a Thargoid and a Thargon;
- witchspace with three Thargoids and no station;
- mission 3, state 4: the hostile station (it launches Thargoids);
- the player's missile at a trader, which makes every object hostile.
"""
import argparse
import json
import os
import random
import subprocess
import sys

from tape import ROOT, REFERENCE, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr
from text_codec import TextCodec

OUTPUT = ROOT / 'build/iff-unit-check'
PARTS = ('IffScannerHook', 'IffBombVector', 'IffScannerCode', 'IffUnitText', 'IffBlinkHook',
         'IffShipCode', 'IffObjectsTail', 'IffBombKey')
ORIGINAL_PARTS = [(0x8C3D, 0x8C40), (0x91C9, 0x91CC), (0x9260, 0x9280), (0x9D84, 0x9E74),
                  (0xA568, 0xA56B), (0xDAC1, 0xDAD8), (0xDBC8, 0xDBD5), (0xFF72, 0xFF74)]
# Object fields (docs/DATA-STRUCTURES.md), independent of the option's own constants.
MISSILE_ROLE, SCOOPABLE_ROLE = 0x01, 0x02      # InstanceRoleFlags bits 0 and 1
HOSTILE = 0x04                                 # InstanceBehaviour bit 2
PLAYER_TARGET = 0                              # missile InstanceAiState aimed at the player
EXPLOSION_BITS = 0x30                          # InstanceFlags bits 4/5
SPEED = 0x1B                                   # InstanceSpeed (not every field reaches the symbol map)
FRAME_LOOP_LIMIT = 2 * 3500000                 # T-states allowed to reach a stop address
MISSION_SAMPLES_NEVER = 1e9                    # sample_from of a run that records no samples
FITTED = 0xFF                                  # BuyEquipmentItem stores $FF
CANISTER_ROLES = 0x0A                          # +$26 of a released cargo canister
BOMB_KEY_BIT = 0x20                            # KeyFlagsCombat bit 5: W, the energy bomb key
KEY_STATE_BYTES = 8                            # KeyFlagsScreens + 0..7 (RecordKeyPress offsets)
# Blueprint IDs (docs/SHIPS.md).
MISSILE, CANISTER, COBRA_TRADER, COBRA_PIRATE, FER_DE_LANCE = 1, 4, 9, 12, 14
DICTIONARY_CODES = [*range(0x0E, 0x20), *range(0x60, 0x80), *range(0xA0, 0x100)]
ENERGY_BOMB_CODE = 0x71                        # token 113, equipment item 9


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('IFF_UNIT') == 1, 'Build iffunit=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.parts = [(s[part + 'Start'], s[part + 'Limit']) for part in PARTS]
        assert self.parts == ORIGINAL_PARTS, self.parts
        self.reference = bytes(reference()[1][5].payload)
        baseline = bytearray(self.image)
        for start, end in self.parts:
            baseline[start - self.base:end - self.base] = self.reference[start - self.base:end - self.base]
        self.baseline = bytes(baseline)
        # Only iffunit=yes selected: outside its parts the image must be the reference itself.
        self.others = [name for name in cr.OPTION_SYMBOLS if name != 'IFF_UNIT' and s.get(name, 0)]
        self.iff = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        assert (s['IffMissileRoleBit'], s['IffScoopableRoles'], s['IffHostileBit']) == (0, SCOOPABLE_ROLE, 2)
        self.hidden_phase = s['IffBlinkHiddenPhase']
        assert bin(self.hidden_phase).count('1') == 1
        self.size, self.state = s['InstanceSize'], s['InitialRuntimeState']
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def slot(self, index):
        return self.state + index * self.size

    def in_parts(self, address):
        return any(start <= address < end for start, end in self.parts)

    # ------------------------------------------------------------------ layout and text
    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        assert changed and all(self.in_parts(a) for a in changed)
        self.report['changed_bytes'] = len(changed)
        self.report['other_options'] = self.others
        if self.others:
            print(f'PASS: {len(changed)} bytes differ from the original in the eight replaced parts; with '
                  f'{", ".join(self.others)} also built, the rest is not compared with the reference.', flush=True)
            return
        assert self.baseline == self.reference, 'bytes outside the replaced parts differ from the reference'
        print(f'PASS: {len(changed)} changed bytes, all inside the eight replaced parts; restoring them '
              f'gives the reference image.', flush=True)

    def printed(self, context, code):
        """What PrintToken does with one code: characters and control codes, in order."""
        m = context.machine()
        out = []
        m.call('PrintToken', a=code, stubs={'PrintCharacter': lambda mm: out.append(chr(mm.reg('a'))),
                                            'DispatchTokenControl': lambda mm: out.append(f'{{{mm.reg("a")}}}')})
        return ''.join(out)

    def check_text(self):
        changed = {}
        for code in DICTIONARY_CODES:
            original, iff = self.printed(self.original, code), self.printed(self.iff, code)
            if original != iff:
                changed[code] = (original, iff)
        assert changed == {ENERGY_BOMB_CODE: ('ENERGY BOMB', 'I.F.F. UNIT')}, changed
        # The documentation codec reads the same tables: it must agree with the simulator.
        assert TextCodec(self.image).dictionary(ENERGY_BOMB_CODE) == 'I.F.F. UNIT'
        self.report['text'] = dict(codes=len(DICTIONARY_CODES), token_113=changed[ENERGY_BOMB_CODE])
        print(f'PASS: PrintToken renders all {len(DICTIONARY_CODES)} dictionary codes as the original '
              f'except $71: "ENERGY BOMB" becomes "I.F.F. UNIT".', flush=True)

    # ------------------------------------------------------------------ scanner
    def threat(self, roles, behaviour, target):
        if roles & MISSILE_ROLE:
            return target == PLAYER_TARGET
        return not roles & SCOOPABLE_ROLE and bool(behaviour & HOSTILE)

    def check_contact_energy(self):
        s = self.symbols
        m = self.iff.machine()
        inst = self.slot(1)
        rng = random.Random(1)
        cases = hidden = 0
        for fitted in (0, 1, FITTED):
            for clock in (0, 1, 2, 3, 0xFD, 0xFE):
                for roles in range(256):
                    for behaviour in (0, HOSTILE, 0xFF & ~HOSTILE, 0xFF):
                        for target in (PLAYER_TARGET, 1, 7, 0x7E, 0x80):
                            energy = rng.randrange(1, 256)
                            m.poke('IffUnitFitted', fitted)
                            m.poke('IffBlinkClock', clock)
                            m.poke(inst + s['InstanceRoleFlags'], roles)
                            m.poke(inst + s['InstanceBehaviour'], behaviour)
                            m.poke(inst + s['InstanceAiState'], target)
                            m.poke(inst + s['InstanceEnergy'], energy)
                            check_memory = cases % 251 == 0
                            before = list(m.memory) if check_memory else None
                            m.call('IffScannerContactEnergy', ix=inst, iy=0x5A5A)
                            hide = bool(fitted and clock & self.hidden_phase and
                                        self.threat(roles, behaviour, target))
                            assert m.reg('a') == (0 if hide else energy), (fitted, clock, roles, behaviour, target)
                            assert m.ix() == inst and m.iy() == 0x5A5A
                            if check_memory:
                                top = self.iff.test_stack
                                differ = [a for a in range(0x4000, 0x10000)
                                          if m.memory[a] != before[a] and not top - 2 <= a < top]
                                assert not differ, [hex(a) for a in differ]
                            cases += 1
                            hidden += hide
        self.report['contact_energy'] = dict(cases=cases, hidden=hidden)
        print(f'PASS: IffScannerContactEnergy for {cases} slot states: energy, or 0 for a missile aimed '
              f'at the player and a hostile non-scoopable object in the dark half with the unit fitted '
              f'({hidden} hidden); IX and IY kept, no memory written.', flush=True)

    def scene(self):
        """Slot records: (slot, blueprint or None for the station, position, field changes)."""
        s = self.symbols
        return [
            (0, None, (0x0000, 0x0400, -0x2000), {s['InstanceBehaviour']: HOSTILE}),    # hostile station
            (1, COBRA_PIRATE, (0x1800, 0x0800, 0x1000), {}),
            (2, COBRA_TRADER, (-0x1800, -0x0400, 0x0800), {}),
            (3, MISSILE, (0x0800, 0x0000, 0x2400), {'missile': PLAYER_TARGET}),
            (4, MISSILE, (-0x0800, 0x0200, 0x2800), {'missile': 3, s['InstanceBehaviour']: HOSTILE}),
            (5, CANISTER, (0x2000, -0x0800, -0x1000), {s['InstanceRoleFlags']: CANISTER_ROLES,
                                                       s['InstanceBehaviour']: HOSTILE}),
            (6, FER_DE_LANCE, (-0x2400, 0x0600, -0x0800), {}),
        ]

    def records(self, hostile_fer_de_lance):
        s = self.symbols
        m = self.iff.machine()
        records = {}
        for index, blueprint, position, changes in self.scene():
            inst = self.slot(index)
            if blueprint is not None:
                m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=blueprint, ix=inst))
            record = bytearray(m.memory[inst:inst + self.size])
            for axis, value in enumerate(position):
                cr.put24(record, 3 * axis, value)
            for field, value in changes.items():
                if field == 'missile':
                    record[s['InstanceRoleFlags']] |= MISSILE_ROLE
                    record[s['InstanceAiState']] = value
                elif field == s['InstanceBehaviour']:
                    record[field] |= value
                else:
                    record[field] = value
            if index == 6 and hostile_fer_de_lance:
                record[s['InstanceBehaviour']] |= HOSTILE            # as a player laser hit leaves it
            assert record[s['InstanceEnergy']]
            records[index] = record
        return records

    def draw(self, context, records, fitted, clock, without=()):
        s = self.symbols
        m = context.machine()
        m.clear(cr.SCREEN, cr.SCREEN_SIZE)
        m.poke('LastActiveObjectEnergy', 1)
        m.poke('ScannerContactsDrawn', 0)
        m.poke('EnergyBombFitted', fitted)
        if 'IffBlinkClock' in s and context is self.iff:
            m.poke('IffBlinkClock', clock)
        for index in range(s['InstanceSlotCount']):
            m.poke(self.slot(index) + s['InstanceEnergy'], 0)
        for index, record in records.items():
            m.poke(self.slot(index), *record)
            if index in without:
                m.poke(self.slot(index) + s['InstanceEnergy'], 0)
        m.call('DrawScannerContacts', stack=context.upper_stack)
        return m.byte('ScannerContactsDrawn'), cr.bitmap_pixels(m.memory, cr.SCREEN, 192)

    def check_scanner(self):
        s = self.symbols
        cases = 0
        for hostile_fer_de_lance in (False, True):
            records = self.records(hostile_fer_de_lance)
            threats = {index for index, record in records.items()
                       if self.threat(record[s['InstanceRoleFlags']], record[s['InstanceBehaviour']],
                                      record[s['InstanceAiState']])}
            assert threats == ({0, 1, 3, 6} if hostile_fer_de_lance else {0, 1, 3}), threats
            everything = self.draw(self.original, records, 0, 0)
            others = self.draw(self.original, records, 0, 0, without=threats)
            alone = {index: self.draw(self.original, {index: records[index]}, 0, 0)[1] for index in records}
            assert everything[0] == 1 and all(alone.values()) and everything[1] != others[1]
            assert all(pixels <= everything[1] for pixels in alone.values())
            for fitted in (0, FITTED):
                for clock in (0, 1, 2, 3, 0xFF):
                    want = others if fitted and clock & self.hidden_phase else everything
                    got = self.draw(self.iff, records, fitted, clock)
                    assert got == want, (hostile_fer_de_lance, fitted, clock)
                    cases += 1
        self.report['scanner'] = dict(cases=cases, objects=len(self.scene()))
        print(f'PASS: DrawScannerContacts in {cases} cases with {len(self.scene())} objects: the original '
              f'drawing of all objects, and in the dark half with the unit fitted exactly the drawing of the '
              f'non-threats (calm trader, player missile, hostile canister, calm Fer-de-Lance).', flush=True)

    # ------------------------------------------------------------------ the energy bomb is gone
    def check_bomb_key(self):
        s = self.symbols
        index = (s['IffBombKeyStart'] - s['KeyActionTable']) // 2
        assert self.image[s['KeyCharacterTable'] - self.base + index] == ord('W')
        row, bit = index % 8 + 1, index // 8                       # RecordKeyPress: D = 8..1, E = 5..1
        results = {}
        for name, context in (('original', self.original), ('iff', self.iff)):
            m = context.machine()
            m.call('RecordKeyPress', d=row, e=5 - bit, a=0x55, bc=0x1234)
            results[name] = (m.byte('LastKeyCode'), [m.byte(s['KeyFlagsScreens'] + i) for i in range(KEY_STATE_BYTES)],
                             m.pair('bc'), m.reg('a'))
        # The state bytes include LastKeyCode, which both images set to the character.
        before = [self.image[s['KeyFlagsScreens'] - self.base + i] for i in range(KEY_STATE_BYTES)]
        before[s['LastKeyCode'] - s['KeyFlagsScreens']] = ord('W')
        want = list(before)
        want[s['KeyFlagsCombat'] - s['KeyFlagsScreens']] |= BOMB_KEY_BIT
        assert results['original'] == (ord('W'), want, 0x1234, 0x55), results
        assert results['iff'] == (ord('W'), before, 0x1234, 0x55), results
        print('PASS: RecordKeyPress for W reports the character W in both images; the original latches '
              'KeyFlagsCombat bit 5, the option image no key bit.', flush=True)

    def cockpit_frame(self, context, clock):
        s = self.symbols
        m = context.machine()
        m.poke('CurrentScreenId', 0)
        m.poke('FlightCondition', 0)                     # UpdateEnergyAndShields returns at once
        m.poke('KeyFlagsCombat', BOMB_KEY_BIT | 0x91)
        m.poke('EnergyBombFitted', FITTED)
        m.poke('EnergyBombPending', 0)
        m.poke('SoundEffectRequests', 0x40)
        if context is self.iff:
            m.poke('IffBlinkClock', clock)
        m.clear(cr.ATTRIBUTES, cr.ATTRIBUTES_SIZE, 0x55)
        before = list(m.memory)
        stubs = {name: None for name in ('DrawCockpitIndicators', 'UpdateMissileControl', 'UpdateEscapePod')}
        m.call('UpdateCockpitSystems', halt=True, stubs=stubs, limit=5_000_000)
        top = context.test_stack
        changed = {a for a in range(0x4000, 0x10000) if m.memory[a] != before[a] and not top - 0x40 <= a < top}
        return m, changed

    def check_cockpit_frame(self):
        s = self.symbols
        m, changed = self.cockpit_frame(self.original, 0)
        assert m.byte('EnergyBombFitted') == 0 and m.byte('EnergyBombPending') == 1
        assert any(cr.ATTRIBUTES <= a < cr.ATTRIBUTES + cr.ATTRIBUTES_SIZE for a in changed), 'original flash'
        for clock in (0, 1, 0xFF):
            m, changed = self.cockpit_frame(self.iff, clock)
            assert m.byte('EnergyBombFitted') == FITTED and m.byte('EnergyBombPending') == 0
            assert m.byte('SoundEffectRequests') == 0x40 and m.byte('KeyFlagsCombat') == 0x91
            assert m.byte('IffBlinkClock') == (clock + 1) & 0xFF
            assert changed == {s['KeyFlagsCombat'], s['IffBlinkClock']}, sorted(hex(a) for a in changed)
        print('PASS: UpdateCockpitSystems with W and the item fitted: the original uses the energy bomb '
              '(byte cleared, EnergyBombPending = 1, view flash); the option image keeps the I.F.F. unit, '
              'changes only the blink clock (+1, wrapping) and the consumed key bit.', flush=True)

    def update_objects(self, context, pending):
        s = self.symbols
        m = context.machine()
        cr.load_jameson(m)
        for index, ship in enumerate((cr.SIDEWINDER, COBRA_PIRATE, cr.THARGOID), start=1):
            m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=ship, ix=self.slot(index)))
        m.poke('EnergyBombPending', pending)
        m.poke('ObjectUpdateCounter', 9)                # keep the random-encounter dispatch away
        m.poke('CurrentScreenId', 0x0B)                 # non-flight screen: no drawing
        m.call('UpdateObjects', limit=5_000_000, **cr.FRESH_REGISTERS)
        exploding = [bool(m.byte(self.slot(i) + cr.INSTANCE_STATE) & EXPLOSION_BITS) for i in (1, 2, 3)]
        return m, exploding

    def check_update_objects(self):
        s = self.symbols
        original_bomb, exploded = self.update_objects(self.original, 1)
        assert exploded == [True, True, True], exploded
        original_calm, calm = self.update_objects(self.original, 0)
        assert calm == [False, False, False]
        iff_bomb, iff_exploded = self.update_objects(self.iff, 1)
        iff_calm, _ = self.update_objects(self.iff, 0)
        assert iff_exploded == [False, False, False] and iff_bomb.byte('EnergyBombPending') == 1
        pending = s['EnergyBombPending']
        for a in range(0x4000, 0x10000):
            if self.in_parts(a):
                continue
            assert iff_bomb.memory[a] == iff_calm.memory[a] or a == pending, hex(a)
            assert iff_calm.memory[a] == original_calm.memory[a], hex(a)
        print('PASS: UpdateObjects with EnergyBombPending = 1: the original explodes the Sidewinder, the '
              'pirate and the Thargoid; the option image ignores and keeps the byte, and its RAM equals the '
              'original update without a bomb.', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_text()
        self.check_contact_energy()
        self.check_scanner()
        self.check_bomb_key()
        self.check_cockpit_frame()
        self.check_update_objects()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


# ---------------------------------------------------------------------- 48K emulator
def commander_pokes(s, label, data, second):
    """Test-only pokes of a commander field in the active record and in the template."""
    import run_runtime_scenarios as rs
    template = s['CommanderTemplateBuffer'] + s[label] - s['ActiveCommanderRecord']
    return [*rs.poke(second, f'{s[label]:#06x}', data), *rs.poke(second, f'{template:#06x}', data)]


def emulator_purchase(checker):
    """Docked: buy item 9 and show the equipment list and the status screen."""
    import run_runtime_scenarios as rs
    s = checker.symbols
    name = 'iff-unit-purchase'
    args = [*rs.started(17), *commander_pokes(s, 'CashHigh', '98008096', 7),
            *commander_pokes(s, 'CurrentTechLevel', '0a', 7),
            *rs.key(8, 0.4, '4'), *rs.key(10, 0.25, '9'), *rs.key(11, 0.3, 'ENTER'), *rs.key(15, 0.4, 'L')]
    subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', name, '--no-screenshots'],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads((ROOT / f'build/emulator/{name}.json').read_text())
    assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
    memory = (ROOT / f'build/emulator/{name}-memory.bin').read_bytes()
    assert memory[s['IffUnitFitted']] == FITTED, 'item 9 was not bought'
    listed = [row['text'] for second in ('9', '12', '14') for row in report['text_captures'][second]]
    status = [row['text'] for row in report['final_text']]
    item = [row for row in listed if 'I.F.F. UNIT' in row.upper()]
    shown = [row for row in status if 'I.F.F. UNIT' in row.upper()]
    assert item and shown and not any('BOMB' in row.upper() for row in listed + status), (listed, status)
    print(f'PASS: 48K emulator: docked, item 9 listed as "{item[0]}", bought (IffUnitFitted = $FF) and '
          f'shown on the status screen as "{shown[0]}".', flush=True)
    return dict(equipment_row=item[0], status_row=shown[0])


def flight_pokes(checker, blueprint, fitted):
    """A ship in slot 1 ahead of the player, the station moved off the scanner, the item byte."""
    s = checker.symbols
    m = checker.iff.machine()
    inst = checker.slot(1)
    m.call('InitialiseShipFromBlueprint', **dict(cr.FRESH_REGISTERS, a=blueprint, ix=inst))
    record = bytearray(m.memory[inst:inst + checker.size])
    for axis, value in enumerate((0x0600, 0x0200, 0x2400)):
        cr.put24(record, 3 * axis, value)
    record[SPEED] = 0
    far = bytearray(3)
    cr.put24(far, 0, 0xF000)                       # middle byte >= $40: no scanner contact
    return [(s['EnergyBombFitted'], bytes([fitted])), (checker.slot(0), bytes(far)), (inst, bytes(record))]


def run_flight(checker, tap, name, pokes, keys, seconds, sample_from, stop_at=None):
    """ROM load of tap in ZX Spectrum 48K mode, launch, pokes at 12 s; sample every frame interrupt.

    Contacts appear only after the launch sequence, so samples start later (sample_from).
    With stop_at the run continues after `seconds` until the PC reaches that address."""
    import emulator_check as ec
    from skoolkit import tap2sna, CSimulator
    from skoolkit.snapshot import Snapshot
    from skoolkit.simutils import from_snapshot, PC, T
    from skoolkit.trace import Tracer
    from skoolkit.simulator import Simulator
    s = checker.symbols
    events = [(3, 3.5, 'N'), (5, 5.5, 'SPACE'), (8, 8.4, '1'), *keys]
    tap2sna.ROM48 = str(ec.ROM48)
    snapshot_path = OUTPUT / f'{name}.z80'
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        tap2sna.main(['--start', hex(s['Entry']), tap.relative_to(ROOT).as_posix(),
                      snapshot_path.relative_to(ROOT).as_posix()])
    finally:
        os.chdir(cwd)
    snapshot = Snapshot.get(str(snapshot_path))
    sim = from_snapshot(CSimulator or Simulator, snapshot, rom_file=tap2sna.ROM48)
    assert sim.registers[PC] == s['Entry']
    trace = Tracer(sim, snapshot.border, snapshot.out7ffd, snapshot.outfffd, snapshot.ay, snapshot.outfe, False)
    sim.set_tracer(trace)
    start, applied, samples, shots = sim.registers[T], [False], [], {}
    scanner = range(0x5000 + 2 * 0x20, 0x5800)        # character rows 2..7 of the bottom third

    def frame(screen, _frame, _border, keyboard):
        elapsed = (sim.registers[T] - start) / 3500000
        keyboard[:] = [0] * 8
        for begin, end, key in events:
            if begin <= elapsed < end:
                row, mask = ec.KEYS[key]
                keyboard[row] |= mask
        if not applied[0] and elapsed >= 12:
            for address, data in pokes:
                sim.memory[address:address + len(data)] = data
            applied[0] = True
        if elapsed >= sample_from:
            drawn = sim.memory[s['ScannerContactsDrawn']]
            samples.append((drawn, sim.memory[s['IffBlinkClock']] if 'IffBlinkClock' in s else 0,
                            sum(bin(sim.memory[a]).count('1') for a in scanner)))
            if drawn not in shots:
                shots[drawn] = bytes(sim.memory[0x4000:0x5B00])
        return True

    trace.run(s['Entry'], None, 0, int(seconds * 3500000), True, frame, set(), None, None, '$', '02X', '04X')
    if stop_at is not None:
        trace.run(sim.registers[PC], stop_at, 0, FRAME_LOOP_LIMIT, True, frame, set(), None, None,
                  '$', '02X', '04X')
        assert sim.registers[PC] == stop_at, hex(sim.registers[PC])
    assert applied[0]
    for drawn, screen in shots.items():
        ec.png(screen, OUTPUT / f'{name}-{"lit" if drawn else "dark"}.png')
    return samples, bytes(sim.memory)


def blink_summary(samples):
    lit = [drawn for drawn, _, _ in samples]
    changes = sum(1 for a, b in zip(lit, lit[1:]) if a != b)
    return dict(samples=len(lit), dark=lit.count(0), changes=changes,
                clock_ticks=(samples[-1][1] - samples[0][1]) & 0xFF)


def emulator_flight(checker):
    s = checker.symbols
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == checker.image, \
        'Build the option with the default tapfile first'
    results = {}
    for name, blueprint, fitted in (('pirate-iff', COBRA_PIRATE, FITTED), ('pirate-no-iff', COBRA_PIRATE, 0),
                                    ('trader-iff', COBRA_TRADER, FITTED)):
        samples, _ = run_flight(checker, RELEASE_TAP, f'iff-unit-{name}', flight_pokes(checker, blueprint, fitted),
                                [], 19.5, 14.5)
        results[name] = blink_summary(samples)
    blink, plain, trader = results['pirate-iff'], results['pirate-no-iff'], results['trader-iff']
    assert 0.3 <= blink['dark'] / blink['samples'] <= 0.7 and blink['changes'] >= 10, blink
    assert blink['clock_ticks'] >= 20, blink
    for other in (plain, trader):
        assert other['dark'] <= other['samples'] // 20, other
    print(f'PASS: 48K emulator flight: with the I.F.F. unit the pirate\'s scanner contact is dark in '
          f'{blink["dark"]} of {blink["samples"]} frame samples ({blink["changes"]} changes, '
          f'{blink["clock_ticks"]} cockpit frames); without the unit {plain["dark"]} and for a trader '
          f'{trader["dark"]} dark samples.', flush=True)

    # W: the option build keeps the pirate, the reference tape's energy bomb destroys it.  The
    # reference run needs the option build's addresses to be the reference's (no other option).
    inst = checker.slot(1)
    runs = (('w-iff', RELEASE_TAP),) + (() if checker.others else (('w-reference', REFERENCE),))
    for name, tap in runs:
        _, memory = run_flight(checker, tap, f'iff-unit-{name}', flight_pokes(checker, COBRA_PIRATE, FITTED),
                               [(15, 15.4, 'W')], 17.5, 17)
        alive = bool(memory[inst + s['InstanceEnergy']]) and not memory[inst + cr.INSTANCE_STATE] & EXPLOSION_BITS
        results[name] = dict(pirate_alive=alive, item_byte=memory[s['EnergyBombFitted']],
                             energy_bomb_pending=memory[s['EnergyBombPending']])
    assert results['w-iff'] == dict(pirate_alive=True, item_byte=FITTED, energy_bomb_pending=0), results
    if checker.others:
        print('PASS: 48K emulator: W in flight leaves the pirate and the I.F.F. unit in place (reference '
              'tape run skipped: other options change the layout).', flush=True)
        return results
    assert not results['w-reference']['pirate_alive'] and results['w-reference']['item_byte'] == 0, results
    print('PASS: 48K emulator: W in flight leaves the pirate and the I.F.F. unit in place; on the reference '
          'tape the same W uses the energy bomb and destroys the pirate.', flush=True)
    return results


# ---------------------------------------------------------------------- mission situations
# Both images start from the RAM of a real 48K ROM-load and launch, taken at the start of
# MainLoop, and get the same mission set-up and the same unit byte ($FF: an unused energy
# bomb in the baseline, the I.F.F. unit in the option image).  Then MainLoop runs loop by loop
# in the Python simulator (no interrupts: no key, control or sound changes).  After every loop
# the RAM must be identical except the scanner columns of the screen, the scanner work bytes,
# the replaced parts and the test stack.
MISSION_LOOPS = 300
CALL_SIZE = 3                                   # CALL nn
SCANNER_WORK = ('ScannerDotX', 'ScannerStickHeight', 'ScannerDotZ', 'ScannerSlotCounter',
                'ScannerContactsDrawn')
BOTTOM_THIRD = (0x5000, 0x5800)                 # screen bitmap of the scanner and the gauges
SCANNER_COLUMNS = range(9, 23)                  # byte columns the contacts can reach (scanner/p3 checks)
TEST_STACK_BYTES = 0x200
MISSION_2_FLAG = 0x02                           # CommanderFlags bit 1: mission 2 triggered
CLOAK_FLAG = 0x40                               # bit 6, cloaking device: the special Asp needs AND $42 = $02
INVASION_HOSTILE_STATION = 4                    # InvasionMissionState that makes the station hostile
ASP_MARK = 0x40                                 # InstanceRoleFlags bit 6: the mission Asp
ASP_CLOAKED = 1                                 # MissionAspEncounterState: the marked Asp is hidden
THARGOID, THARGON = 15, 18                      # blueprint IDs (docs/SHIPS.md)


def place(checker, m, ctx, index, blueprint, position):
    inst = checker.slot(index)
    m.call('InitialiseShipFromBlueprint', stack=ctx.upper_stack,
           **dict(cr.FRESH_REGISTERS, a=blueprint, ix=inst))
    for axis, value in enumerate(position):
        cr.put24(m.memory, inst + 3 * axis, value)


def setup_cloaked_asp(checker, m, ctx):
    """Mission 2: the real special encounter, a marked Asp and two Sidewinders, moved near."""
    s = checker.symbols
    m.poke('CommanderFlags', (m.byte('CommanderFlags') | MISSION_2_FLAG) & ~CLOAK_FLAG & 0xFF)
    m.poke('MissionAspEncounterState', 0)
    for index in range(1, s['InstanceSlotCount'] - 1):
        m.poke(checker.slot(index) + s['InstanceEnergy'], 0)
    m.call('SpawnRandomEncounter', stack=ctx.upper_stack, limit=500_000, **cr.FRESH_REGISTERS)
    assert m.byte('MissionAspEncounterState') == ASP_CLOAKED
    assert m.byte(checker.slot(1) + s['InstanceRoleFlags']) & ASP_MARK
    for index, position in zip((1, 2, 3), ((0x0600, 0x0200, 0x1C00), (-0x0900, 0x0100, 0x2000),
                                           (0x0C00, -0x0200, 0x2400))):
        for axis, value in enumerate(position):
            cr.put24(m.memory, checker.slot(index) + 3 * axis, value)


def setup_thargoids(checker, m, ctx):
    place(checker, m, ctx, 1, THARGOID, (0x0800, 0x0200, 0x1800))
    place(checker, m, ctx, 2, THARGON, (-0x0600, 0x0100, 0x1400))


def setup_witchspace(checker, m, ctx):
    """Witchspace (mis-jump) with three Thargoids and no station."""
    m.poke('WitchspaceFlag', 1)
    m.poke(checker.slot(0) + checker.symbols['InstanceEnergy'], 0)
    for index, position in zip((1, 2, 3), ((0x0800, 0x0200, 0x1800), (-0x0A00, -0x0200, 0x2000),
                                           (0x0200, 0x0400, 0x2800))):
        place(checker, m, ctx, index, THARGOID, position)


def setup_hostile_station(checker, m, ctx):
    """Mission 3, state 4: UpdateObjects makes the station hostile; a calm trader nearby."""
    m.poke('InvasionMissionState', INVASION_HOSTILE_STATION)
    place(checker, m, ctx, 1, COBRA_TRADER, (0x0600, 0x0100, 0x1C00))


def setup_missile_alert(checker, m, ctx):
    """The player's missile at a trader: the game marks every object hostile while it flies."""
    place(checker, m, ctx, 1, COBRA_TRADER, (0x0400, 0x0100, 0x1400))
    place(checker, m, ctx, 2, CANISTER, (-0x0800, 0x0000, 0x1000))
    counter = checker.symbols['InstanceSlotCount'] - 1                  # ObjectLoopCounter of slot 1
    m.call('LaunchMissile', stack=ctx.upper_stack, **dict(cr.FRESH_REGISTERS, c=counter))


MISSIONS = (('cloaked-asp', setup_cloaked_asp), ('thargoids', setup_thargoids),
            ('witchspace-thargoids', setup_witchspace), ('hostile-station', setup_hostile_station),
            ('missile-alert', setup_missile_alert))


def mission_machines(checker, ram):
    """Baseline and option machine with the launch RAM and each image's own replaced parts."""
    machines = []
    for image in (checker.baseline, checker.image):
        ctx = cr.ImageContext(checker.symbols, image)
        memory = list(ctx.pristine[:0x4000]) + list(ram[0x4000:])
        for start, end in checker.parts:
            memory[start:end] = image[start - checker.base:end - checker.base]
        ctx.pristine = tuple(memory)
        machines.append((ctx, ctx.machine()))
    return machines


def emulator_missions(checker):
    s = checker.symbols
    _, ram = run_flight(checker, RELEASE_TAP, 'iff-unit-launch', [], [], 15, MISSION_SAMPLES_NEVER,
                        stop_at=s['MainLoop'])
    loop_end = s['L_732B'] + CALL_SIZE           # after CALL UpdateProximityAndCompass: one loop done
    call = checker.image[s['L_732B'] - checker.base:loop_end - checker.base]
    assert call[0] == 0xCD and int.from_bytes(call[1:], 'little') == s['UpdateProximityAndCompass']
    work = {s[name] for name in SCANNER_WORK}
    results = {}
    for name, setup in MISSIONS:
        (octx, om), (ictx, im) = mission_machines(checker, ram)
        skip = work | {a for start, end in checker.parts for a in range(start, end)}
        skip |= set(range(octx.upper_stack - TEST_STACK_BYTES, octx.upper_stack))
        strict = [a for a in range(0x4000, 0x10000)
                  if a not in skip and not BOTTOM_THIRD[0] <= a < BOTTOM_THIRD[1]]
        for m, ctx in ((om, octx), (im, ictx)):
            m.poke('EnergyBombFitted', FITTED)
            setup(checker, m, ctx)
        assert all(om.memory[a] == im.memory[a] for a in strict), name
        scanner_loops, asp_states, station_hostile = 0, set(), False
        for loop in range(MISSION_LOOPS):
            for m, ctx in ((om, octx), (im, ictx)):
                m.call('MainLoop', stop=loop_end, stack=ctx.upper_stack, halt=True, limit=30_000_000)
            differ = [a for a in strict if om.memory[a] != im.memory[a]]
            assert not differ, (name, loop, [f'${a:04X}' for a in differ[:8]])
            screen = [a for a in range(*BOTTOM_THIRD) if om.memory[a] != im.memory[a]]
            assert all((a & 0x1F) in SCANNER_COLUMNS for a in screen), (name, loop)
            scanner_loops += bool(screen)
            asp_states.add(om.byte('MissionAspEncounterState'))
            station_hostile |= bool(om.byte(checker.slot(0) + s['InstanceBehaviour']) & HOSTILE)
            if om.byte('PlayerDeadFlag'):
                break
        assert scanner_loops, (name, 'no threat blinked')
        results[name] = dict(loops=loop + 1, scanner_loops=scanner_loops,
                             player_dead=bool(om.byte('PlayerDeadFlag')),
                             asp_states=sorted(asp_states), station_hostile=station_hostile)
    assert ASP_CLOAKED in results['cloaked-asp']['asp_states']
    assert results['hostile-station']['station_hostile'] and results['missile-alert']['station_hostile']
    assert not results['thargoids']['station_hostile']
    for name, result in results.items():
        print(f'PASS: mission {name}: {result["loops"]} main loops from a 48K launch, RAM identical to the '
              f'original outside the scanner; the scanner differs in {result["scanner_loops"]} loops'
              + (', the player is killed' if result['player_dead'] else '') + '.', flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenarios')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = dict(purchase=emulator_purchase(checker), flight=emulator_flight(checker),
                                          missions=emulator_missions(checker))
    checker.write()


if __name__ == '__main__':
    main()
