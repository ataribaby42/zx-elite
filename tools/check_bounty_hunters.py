"""Reproduce encounter selection and legal-hostility evidence in ZX Spectrum 48K.

Run after make.bat and verify.bat. Execute the unchanged reference reconstruction
with the supplied 48K ROM; controlled RAM fixtures do not modify the release.
Addresses come from the current assembler map. See docs/BOUNTY-HUNTERS.md.
"""
from collections import Counter
import json
import sys

from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, reference, sha, describe
from build import symbol_map
from verified_annotations import ANNOTATIONS

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import A, B, C, D, E, F, H, L, PC, SP, IXh, IXl, IYh, IYl

INSTANCE_SIZE = 39
BEHAVIOUR = 0x21
ENERGY = 0x22
BLUEPRINT = 0x23
HOSTILE = 4
LEGAL_SENSITIVE = 2
TEST_STACK = 0x5CF0
RETURN_SENTINEL = 0


def main():
    output = ROOT / 'build/bounty-hunter-check/verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    symbols = symbol_map(ROOT / 'build/game.map')
    for address, (name, _) in ANNOTATIONS.items():
        assert symbols[name] == symbols[f'L_{address:04X}'], ('Annotation alias differs', name)
    original, blocks = reference()  # Checks framing, headers, lengths, XOR and hash.
    image = (ROOT / 'build/game.bin').read_bytes()
    assert RELEASE_TAP.read_bytes() == original
    assert image == blocks[5].payload
    assert symbols['SHIP_ADDER'] == 0
    rom = (ROOT / 'assets/zxspectrum48k.rom').read_bytes()
    assert len(rom) == 0x4000
    ram = list(rom) + [0] * (65536 - len(rom))
    base = symbols['GameImage']
    ram[base:base + len(image)] = image
    sim = Simulator(ram)
    r = sim.registers
    station = symbols['InitialRuntimeState']
    ship = station + INSTANCE_SIZE
    legal = symbols['PlayerLegalScore']
    seed_address = symbols['RandomSeed']
    table = symbols['ShipBlueprintTable']
    headers = [ram[table + n * 4 + 1] + 256 * ram[table + n * 4 + 2]
               for n in range(19)]

    def seed(value):
        ram[seed_address:seed_address + 2] = value.to_bytes(2, 'little')

    def run(entry, stop=None, a=0, b=0, c=0, d=0, h=0, f=0, ix=ship, iy=0):
        r[PC], r[SP], r[F] = symbols[entry], TEST_STACK, f
        r[A], r[B], r[C], r[D], r[E], r[H], r[L] = a, b, c, d, 0, h, 0
        r[IXh], r[IXl], r[IYh], r[IYl] = ix >> 8, ix & 255, iy >> 8, iy & 255
        ram[TEST_STACK:TEST_STACK + 2] = [RETURN_SENTINEL, 0]
        target = symbols[stop] if stop else RETURN_SENTINEL
        visited = set()
        for _ in range(20000):
            pc = r[PC]
            if pc == target:
                return visited
            assert pc != RETURN_SENTINEL, (entry, stop, 'unexpected return')
            visited.add(pc)
            sim.opcodes[ram[pc]]()
        raise AssertionError((entry, 'instruction limit', hex(r[PC])))

    defaults = []
    for ship_id in range(19):
        seed(0)
        run('InitialiseShipFromBlueprint', a=ship_id)
        defaults.append(bytes(ram[ship:ship + INSTANCE_SIZE]))
    sensitive_ids = [i for i, data in enumerate(defaults) if data[BEHAVIOUR] & LEGAL_SENSITIVE]
    assert sensitive_ids == [8, 14]
    assert defaults[14][BEHAVIOUR] == 2
    assert all(defaults[i][BEHAVIOUR] & HOSTILE for i in (11, 12, 13, 15, 16, 17, 18))

    # Every possible RNG byte at the actual mixed-encounter selection branch.
    # Low-byte seeds 0..255, high byte zero yield all 256 RNG outputs here.
    selection = Counter()
    for value in range(256):
        for slot in range(1, 7):
            ram[station + slot * INSTANCE_SIZE + ENERGY] = 0
        seed(value)
        run('L_F6A3', stop='InitialiseEncounterShip', a=0, b=8)
        n = value & 63
        expected = 15 if n == 0 else 14 if n < 12 else 13 if n < 30 else 12 if n < 46 else 11
        assert r[A] == expected, (value, r[A], expected)
        selection[r[A]] += 1

    # Find a real event-0 seed that produces a Fer-de-Lance, without mocking RNG.
    for label in ('L_A830', 'L_A833', 'L_A837', 'L_A871', 'L_A872', 'L_A85F', 'L_DA0C'):
        ram[symbols[label]] = 0

    def encounter(value, score, occupied=0):
        for slot in range(1, 7):
            ram[station + slot * INSTANCE_SIZE + ENERGY] = 100 if slot <= occupied else 0
        ram[legal] = score
        seed(value)
        visited = run('DispatchShipEvent', a=0)
        slot = station + (occupied + 1) * INSTANCE_SIZE
        data = bytes(ram[slot:slot + INSTANCE_SIZE]) if occupied < 6 else None
        return visited, data

    for witness in range(65536):
        _, data = encounter(witness, 0)
        if data[ENERGY] and int.from_bytes(data[BLUEPRINT:BLUEPRINT + 2], 'little') == headers[14]:
            break
    else:
        raise AssertionError('No Fer-de-Lance found in event-0 seed space')
    spawn_cases = 0
    for occupied in (0, 5, 6):
        baseline = None
        for score in (0, 1, 39, 40, 49, 50, 255):
            visited, data = encounter(witness, score, occupied)
            if occupied < 6:
                assert int.from_bytes(data[BLUEPRINT:BLUEPRINT + 2], 'little') == headers[14]
                assert data[BEHAVIOUR] == 2
                if baseline is None:
                    baseline = data
                assert data == baseline, 'Legal score changed spawn state'
            else:
                assert symbols['InitialiseShipFromBlueprint'] not in visited
            spawn_cases += 1

    # All legal byte values against all initial blueprint attitudes.
    threshold_cases = 0
    for ship_id, data in enumerate(defaults):
        for score in range(256):
            ram[ship:ship + INSTANCE_SIZE] = data
            ram[legal] = score
            run('UpdateShipHostilityAndSteering', stop='L_F8B3')
            expected = data[BEHAVIOUR] | (HOSTILE if data[BEHAVIOUR] & LEGAL_SENSITIVE and score >= 40 else 0)
            assert ram[ship + BEHAVIOUR] == expected
            threshold_cases += 1

    # Execute the inline space consumer, real LD B,$12 and score read/branches.
    # Stop just before the selected status word is printed.
    for score in range(256):
        ram[legal] = score
        visited = run('PrintLegalStatus', stop='L_D107')
        assert symbols['SelectLegalStatusToken'] in visited
        assert r[B] == 0x12 + (0 if score == 0 else 1 if score < 50 else 2)

    # Confirm both named steering vector paths for every position-sign octant.
    steering_cases = 0
    for signs in range(8):
        for towards, entry in ((False, 'SteerShipAwayFromPlayer'), (True, 'SteerShipTowardsPlayer')):
            ram[ship:ship + INSTANCE_SIZE] = defaults[14]
            for axis, magnitude in enumerate((0x4005, 0x200A, 0x100F)):
                offset = ship + axis * 3
                sign = (signs >> axis) & 1
                ram[offset:offset + 3] = [magnitude & 255, magnitude >> 8, sign * 128]
            run(entry, stop='L_F9FA')
            for axis, (label, magnitude) in enumerate(zip(('L_F72B', 'L_F72D', 'L_F72F'), (0x4005, 0x200A, 0x100F))):
                offset = symbols[label]
                word = ram[offset] + 256 * ram[offset + 1]
                assert word == magnitude // 4 + ((((signs >> axis) & 1) ^ towards) << 15)
            assert bool(ram[ship + 0x26] & 32) == (not towards)
            steering_cases += 1

    # Real AI entry: distant ship either returns peacefully or computes pursuit.
    # Then exercise the firing gate with favourable range, alignment and RNG.
    combat = []
    for score in (0, 1, 39, 40, 49, 50, 255):
        ram[ship:ship + INSTANCE_SIZE] = defaults[14]
        ram[legal] = score
        ram[symbols['L_A80C']] = 0
        ram[symbols['L_A871']] = 0
        ram[ship:ship + 9] = [0, 0, 0, 0, 0, 0, 0, 16, 0]
        visited = run('L_F733', iy=headers[14])
        hostile = score >= 40
        assert (symbols['SteerShipTowardsPlayer'] in visited) == hostile
        assert bool(ram[ship + BEHAVIOUR] & HOSTILE) == hostile
        ram[ship + 8], ram[ship + 14], ram[ship + 0x26] = 0, 0x80, 0
        ram[symbols['L_DA18']] = 0
        seed(0)
        run('TryFireAiLaser', d=1, h=0xE0, iy=headers[14])
        assert ram[symbols['L_DA18']] == (7 if hostile else 0)
        combat.append(dict(legal=score, pursuit=hostile, favourable_firing_damage=7 if hostile else 0))

    # Hostility is latched: lowering legal status alone does not clear it.
    ram[ship:ship + INSTANCE_SIZE] = defaults[14]
    for score in (40, 0):
        ram[legal] = score
        run('UpdateShipHostilityAndSteering', stop='L_F8B3')
        assert ram[ship + BEHAVIOUR] == 6

    # A nonlethal player laser hit provokes the ship even with legal=0.
    ram[ship:ship + INSTANCE_SIZE] = defaults[14]
    ram[legal] = 0
    run('ApplyPlayerLaserHit', stop='DrawLaser', c=1)
    assert ram[ship + BEHAVIOUR] == 6 and ram[ship + ENERGY] == 159
    assert ram[legal] == 0

    # Shared hostility: an angry trader raises the alert; a calm FdL inherits it.
    alert = symbols['SharedHostilityAlert']
    missile_energy = symbols['PlayerMissileEnergy']
    assert missile_energy == station + 7 * INSTANCE_SIZE + ENERGY
    ram[alert] = ram[missile_energy] = 0
    ram[ship:ship + INSTANCE_SIZE] = defaults[9]
    ram[ship + BEHAVIOUR] |= HOSTILE
    run('UpdateSharedHostility', stop='L_DAFA')
    assert ram[alert] == 1
    ram[ship:ship + INSTANCE_SIZE] = defaults[14]
    run('UpdateSharedHostility', stop='L_DAFA')
    assert ram[ship + BEHAVIOUR] == 6 and ram[legal] == 0
    ram[alert] = 0
    ram[ship:ship + INSTANCE_SIZE] = defaults[14]
    ram[missile_energy] = 2
    run('UpdateSharedHostility', stop='L_DAFA')
    assert ram[ship + BEHAVIOUR] == 6 and ram[legal] == 0

    report = dict(passed=True, machine='ZX Spectrum 48K', rom_sha256=sha(rom),
        tape_sha256=sha(original), binary_identity=True,
        assembler_version=(ROOT / 'build/assembler-version.txt').read_text().strip(),
        blocks=describe(blocks), legal_sensitive_blueprint_ids=sensitive_ids,
        mixed_selector_counts=dict(sorted(selection.items())),
        event_zero_fer_de_lance_seed=witness, full_spawn_cases=spawn_cases,
        threshold_cases=threshold_cases, status_category_cases=256, combat=combat,
        annotation_aliases_checked=len(ANNOTATIONS), steering_vector_cases=steering_cases,
        hostility_persists_after_legal_reduction=True, clean_player_laser_retaliation=True,
        clean_player_shared_alert=True, clean_player_missile_alert=True,
        scope='Controlled Z80 routine tests; no full ROM tape-load or manual gameplay session.')
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: ZX Spectrum 48K; selector 256 bytes, {spawn_cases} full spawn cases, '
          f'{threshold_cases} attitude cases, 256 status cases, {steering_cases} steering vectors, '
          '7 AI/firing cases and hostility exceptions.')
    print(f'Event-0 Fer-de-Lance seed: ${witness:04X}; legal-sensitive IDs: {sensitive_ids}.')
    print(output.relative_to(ROOT))


if __name__ == '__main__':
    main()
