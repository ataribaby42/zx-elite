"""Check dockingrotation=yes in ZX Spectrum 48K with assets/zxspectrum48k.rom.

Run after make.bat dockingrotation=yes verify=no. --emulator also ROM-loads
the release for aligned/inverted/misaligned approaches and the docking computer.
"""
import argparse
import json
import math

from tape import ROOT, RELEASE_TAP, reference, parse, sha
from build import symbol_map
import check_routines as cr

OUT = ROOT / 'build/docking-rotation-check'
OUTPUTS = ('DockingContactFlag', 'PlayerDeadFlag', 'FrontDamageThisUpdate',
           'RearDamageThisUpdate', 'SoundEffectRequests')


def word(value):
    return (abs(value) | (0x8000 if value < 0 else 0)).to_bytes(2, 'little')


def axes(degrees):
    angle = math.radians(degrees)
    x, y = round(32767 * math.cos(angle)), round(32767 * math.sin(angle))
    # Nose points towards the player; local Y is the slot's long axis.
    return b''.join(word(v) for v in (0, 0, -32767, x, y, 0, -y, x, 0))


def prepare(m, roof=127, low=0, speed=10, view=0, position=(0, 0, 100),
            nose=(0, 0, 255), hostile=0):
    m.reset()
    cr.load_jameson(m)
    s, station = m.ctx.symbols, m['InitialRuntimeState']
    for i, value in enumerate(position):
        cr.put24(m.memory, station + i * 3, value)
    m.memory[station+s['InstanceAxisZ']:station+s['InstanceAxisX']+6] = axes(0)
    m.poke(station + s['DockingRotationRoofXHigh'] - 1, low, roof)
    for i, value in enumerate(nose):
        m.poke(station + s['InstanceAxisZ'] + 1 + i * 2, value)
    m.poke(station + s['InstanceBehaviour'], hostile)
    for name in OUTPUTS:
        m.poke(name, 0)
    m.poke('PlayerSpeed', speed)
    m.poke('CurrentScreenId', view)
    m.poke('HyperspaceKeyLatch', 0)
    m.poke('JumpTunnelMode', 0)
    return station


def contact(m):
    station = m['InitialRuntimeState']
    m.call('HandleObjectContact', ix=station, iy=m['ShipCoriolisStationBlueprint'], **cr.ZERO_REGISTERS)
    assert m.ix() == station and m.iy() == m['ShipCoriolisStationBlueprint']
    return tuple(m.byte(n) for n in OUTPUTS)


def run(emulate):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'verification.json'
    path.unlink(missing_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    assert s['DOCKING_ROTATION'] == s['COMPETITION_REMOVE'] == 1
    image = (ROOT / 'build/game.bin').read_bytes()
    ref = reference()[1][5].payload
    if not s['ROTATION_DRIFT_FIX']:
        start, end = s['ApplyPlayerMotion']-s['GameImage'], s['RotateAndDrawTitleShip']-s['GameImage']
        assert image[start:end] == ref[start:end], 'docking without rotation repair changed motion'
    baseline = bytearray(image)
    a, b = s['DockingRotationHookStart']-s['GameImage'], s['DockingRotationHookLimit']-s['GameImage']
    baseline[a:b] = ref[a:b]  # Only restore the original six-byte success tail.
    fixed, original = cr.ImageContext(s, image), cr.ImageContext(s, baseline)
    m, old = fixed.machine(), original.machine()

    # Confirm the axis from this port's actual model, not the BBC/C64 layout.
    vertices = s['ShipCoriolisStationVertices']-s['GameImage']
    slot = [image[vertices+6*i:vertices+6*(i+1)] for i in range(12, 16)]
    assert all(v[:3] == bytes((10, 30, 160)) for v in slot), slot
    assert s['DockingRotationRoofXHigh'] == s['InstanceAxisY'] + 1
    assert s['DockingRotationMinimum'] == 106

    cases = 0
    for roof in range(256):
        for low in (0, 255):
            for speed in (0, 40):
                station = prepare(m, roof=roof, low=low, speed=speed)
                before = bytes(m.memory[station:station+s['InstanceSize']])
                result = contact(m)
                aligned = (roof & 127) >= 106
                assert result == ((1, 0, 0, 0, 0) if aligned else
                                  (0, 0, 12+2*speed, 0, 0x40)), (roof, low, speed, result)
                assert bytes(m.memory[station:station+s['InstanceSize']]) == before
                if aligned:
                    hits = []
                    m.call('CheckDocking', stubs={'DockWithStation': lambda mm: hits.append(1)})
                    assert hits == [1] and m.byte('DockingContactFlag') == 0
                cases += 1

    # All 360 integer rolls, both signs, and every selected cockpit view.
    for view in range(4):
        for degree in range(360):
            station = prepare(m, view=view)
            rotation = axes(degree)
            m.memory[station+s['InstanceAxisZ']:station+s['InstanceAxisX']+6] = rotation
            roof = m.byte(station+s['DockingRotationRoofXHigh']) & 127
            assert bool(contact(m)[0]) == (roof >= 106), (view, degree, roof)

    # Every pre-existing rejection must keep its exact effect. New checking
    # only runs after the old approach tests succeed; it never weakens them.
    unchanged = [dict(nose=v) for v in ((30, 0, 255), (0, 158, 255), (109, 0, 255),
                                      (0, 237, 255), (110, 0, 255), (0, 238, 255), (0, 0, 127))]
    unchanged += [dict(hostile=4), dict(position=(0, 0, -100)),
                  dict(position=(160, 0, 100)), dict(position=(0, 160, 100)),
                  dict(position=(0, 0, 160))]
    for values in unchanged:
        for roof in (0, 127, 255):
            prepare(m, roof=roof, **values)
            prepare(old, roof=roof, **values)
            assert contact(m) == contact(old), (values, roof)
    # Other ships share the outer contact routine. Read each radius through
    # the actual loader's pointer: Adder compacts the blueprint dispatch table.
    contacts = (cr.P9Contact(fixed), cr.P9Contact(original))
    object_cases = 0
    for ship in range(1, s['ShipBlueprintCount']):
        probe = contacts[0].run(ship, (0, 0, 0x10000))
        radius = contacts[0].m.byte(probe['blueprint'] + cr.P9_BLUEPRINT_RADIUS)
        for distance in (radius-1, radius, radius+1):
            for sign in (-1, 1):
                outputs = [c.run(ship, (distance, 1, sign*7)) for c in contacts]
                assert outputs[0] == outputs[1], (ship, distance, sign, outputs)
                object_cases += 1
    scoop_cases = cr.check_p9_scooping(fixed)

    # The C-key docking computer intentionally bypasses manual slot contact.
    for roof in (0, 127, 255):
        prepare(m, roof=roof)
        for name, value in (('StationPresent', 1), ('DockingComputerFitted', 1),
                            ('FlightCondition', 255), ('KeyFlagsCombat', 128)):
            m.poke(name, value)
        hits = []
        m.call('CheckDocking', stubs={'DockWithStation': lambda mm: hits.append(1)})
        assert hits == [1] and m.byte('DockingComputerFlag') == 1

    report = dict(passed=True, machine='ZX Spectrum 48K', rom='assets/zxspectrum48k.rom',
                  ship='adder' if s['SHIP_ADDER'] else 'krait', image_sha256=sha(image),
                  high_byte_cases=cases, angle_view_cases=1440, unchanged_cases=36,
                  other_object_cases=object_cases, scooping_cases=scoop_cases,
                  docking_computer_cases=3, helper_bytes=18,
                  rotationdriftfix=bool(s['ROTATION_DRIFT_FIX']),
                  remaining_rotation_padding=1 if s['ROTATION_DRIFT_FIX'] else None,
                  remaining_competition_padding=1 if s['ROTATION_DRIFT_FIX'] else 87)
    if emulate:
        report['emulator'] = emulator(s, image, ref[a:b])
    data = json.dumps(report, indent=2)+'\n'
    path.write_text(data, encoding='utf-8')
    (OUT / ('verification-'+report['ship']+'.json')).write_text(data, encoding='utf-8')
    print(data, flush=True)


def emulator(s, image, original_hook):
    import benchmark_rotation_drift as bench
    from emulator_check import png

    assert parse(RELEASE_TAP.read_bytes())[5].payload == image, 'Build the default TAP filename first'
    bench.OUT = OUT
    memory, registers = bench.boot(s)
    results = {}
    for name, degree, original, computer in (('aligned', 0, False, False),
            ('inverted', 180, False, False), ('vertical', 90, False, False),
            ('vertical-original', 90, True, False), ('vertical-computer', 90, False, True)):
        station = s['InitialRuntimeState']
        sim = bench.clone(memory, registers)
        ram = sim.memory
        # Inject at MainLoop, then observe completed game updates: contact and
        # shield damage happen in different parts of the same update.
        for axis, value in enumerate((0, 0, 150)):
            cr.put24(ram, station+axis*3, value)
        ram[station+s['InstanceAxisZ']:station+s['InstanceAxisX']+6] = axes(degree)
        # Retain this build's normal station roll, including bit 7 (also the
        # pirate-mission survival marker). Pitch immediately follows roll.
        station_roll = image[station+s['InstanceRoll']-s['GameImage']]
        for address, value in ((station+s['InstanceRoll'], station_roll), (station+s['InstanceRoll']+1, 0),
                (station+s['InstanceBehaviour'], 0), (station+s['InstanceEnergy'], 240),
                (s['StationDormantFlag'], 0), (s['StationPresent'], 1),
                (s['PlayerSpeed'], 0), (s['PlayerRoll'], 0), (s['PlayerPitch'], 0),
                (s['ControlsLockedFlag'], 1), (s['DockingContactFlag'], 0),
                (s['DockingComputerFitted'], 1)):
            ram[address] = value
        if original:
            ram[s['DockingRotationHookStart']:s['DockingRotationHookLimit']] = original_hook
        shield_before = ram[s['ForwardShield']]
        assert shield_before > 0
        executed, operations = set(), 0
        for updates in range(1, 33):
            operations += bench.main_loop_frame(sim, s, keys=('C',) if computer else (),
                                               executed=executed)
            assert s['RunGameOverSequence'] not in executed, name
            if not ram[s['FlightCondition']] or (name == 'vertical' and ram[s['ForwardShield']] < shield_before):
                break
        else:
            raise AssertionError((name, 'no docking/contact outcome after 32 updates'))
        docked = ram[s['FlightCondition']] == 0
        assert docked == (name != 'vertical'), (name, docked, ram[s['PlayerDeadFlag']])
        assert not ram[s['PlayerDeadFlag']], name
        if not original and not computer:
            assert s['DockingRotationCheck'] in executed, name
        if computer:
            assert ram[s['DockingComputerFlag']] == 1, name
        results[name] = dict(docked=docked, player_dead=ram[s['PlayerDeadFlag']],
                             front_shield_before=shield_before, front_shield=ram[s['ForwardShield']],
                             updates=updates, operations=operations)
        if name == 'vertical':
            assert ram[s['ForwardShield']] < shield_before, 'misalignment must damage the front shield'
            assert s['UpdateEnergyAndShields'] in executed
            assert ram[s['DockingContactFlag']] == 0
        label = 'docking-rotation-'+('adder-' if s['SHIP_ADDER'] else 'krait-')+name
        (OUT / (label+'-memory.bin')).write_bytes(bytes(ram))
        png(ram[0x4000:0x5B00], OUT / (label+'.png'))
        print('PASS: 48K ROM-load:', name, 'docked' if docked else 'scraped, stayed in flight', flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator', action='store_true')
    run(parser.parse_args().emulator)
