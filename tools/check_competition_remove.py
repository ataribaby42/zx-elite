"""Check competitionremove=yes, alone or implied by rotationdriftfix/dockingrotation.

Uses ZX Spectrum 48K with assets/zxspectrum48k.rom. Run after a modified build:
    make.bat competitionremove=yes verify=no
    python tools/check_competition_remove.py

The real save control flow runs; keyboard, display and ROM cassette transport
are stubs. Success and BREAK compare all 104 tape bytes and the 102-byte restart
snapshot with the original save implementation. No cassette audio is simulated.
"""
import json
from tape import ROOT, reference, sha
from build import symbol_map
from check_build_options import FIX_PARTS
import check_routines as cr


def check_save_paths(s, baseline, fixed):
    """Shared by the standalone removal and rotation-drift regressions."""
    save = []
    for success in (True, False):
        states = []
        for ctx in (baseline, fixed):
            mm = ctx.machine()
            record = bytes((i * 29 + 17) & 255 for i in range(104))
            mm.memory[s['ActiveCommanderRecord']:s['ActiveCommanderRecord'] + 104] = record
            for i, value in enumerate((123456, -67890, 98765)):
                cr.put24(mm.memory, s['SunPosition'] + i * 3, value)
            messages, tapes = [], []
            def write_tape(machine):
                assert machine.ix() == s['ActiveCommanderRecord'] and machine.pair('de') == 104
                tapes.append(bytes(machine.memory[s['ActiveCommanderRecord']:s['ActiveCommanderRecord'] + 104]))
                machine.set(f=1 if success else 0)
            stubs = {'PromptCommanderName': None, 'WaitForKeyPress': None,
                     'RomSaBytesAfterSetup': write_tape,
                     'PrintStatusLineMessage': lambda machine: messages.append(machine.reg('a')),
                     'PrintMessage': lambda machine: messages.append(machine.reg('a')),
                     'PrintDecimalHL': None, 'ClearPromptLines': None}
            mm.call('AccessMenuSave', stop='AccessMenuKeyLoop', stubs=stubs)
            template = bytes(mm.memory[s['CommanderTemplateBuffer']:s['CommanderTemplateBuffer'] + 102])
            states.append((tapes, template, messages))
        assert states[0][:2] == states[1][:2]
        assert states[1][2] == ([2, 0x97] if success else [2, 0xC7]), states
        assert states[0][2] == ([2, 0x97, 4] if success else [2, 0xC7]), states
        if success:
            assert states[1][1] == states[1][0][0][:102]
        save.append(dict(success=success, messages=states[1][2], tape_bytes=104))

    return save


def main():
    output = ROOT / 'build/competition-remove-check'
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / 'verification.json'
    report_path.unlink(missing_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    assert s['COMPETITION_REMOVE'] == 1, 'Build competitionremove=yes first'
    image = (ROOT / 'build/game.bin').read_bytes()
    original = bytearray(image)
    ref = reference()[1][5].payload
    base = s['GameImage']
    for part in FIX_PARTS['competitionremove'][0]:
        start, end = s[part+'Start'], s[part+'Limit']
        original[start-base:end-base] = ref[start-base:end-base]
    if not s['ROTATION_DRIFT_FIX']:
        padding = bytearray(image)
        if s['DOCKING_ROTATION']:
            for part in FIX_PARTS['dockingrotation'][0][1:]:
                start, end = s[part+'Start'], s[part+'Limit']
                padding[start-base:end-base] = bytes(end-start)
        start, end = s['CompetitionSecurityStart'], s['CompetitionSecurityLimit']
        jump = bytes((0x18, s['CopyCommanderToTemplate'] - (start + 2)))
        assert padding[start-base:end-base] == jump + bytes(end-start-2)
        start, end = s['CompetitionParityStart'], s['CompetitionParityLimit']
        assert padding[start-base:end-base] == bytes(end-start)
        start, end = s['ApplyPlayerMotion']-base, s['RotateAndDrawTitleShip']-base
        assert image[start:end] == ref[start:end], 'standalone removal changed motion'
    save = check_save_paths(s, cr.ImageContext(s, original), cr.ImageContext(s, image))
    report = dict(passed=True, machine='ZX Spectrum 48K', rom='assets/zxspectrum48k.rom',
                  rotationdriftfix=bool(s['ROTATION_DRIFT_FIX']), dockingrotation=bool(s['DOCKING_ROTATION']),
                  image_sha256=sha(image), save=save)
    report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS: competition removal: identical tape bytes and restart snapshot; success and BREAK; '
          + ('rotation helpers present.' if s['ROTATION_DRIFT_FIX'] else
             'original motion unchanged; '+('87' if s['DOCKING_ROTATION'] else '105')+' padding bytes remain.'))


if __name__ == '__main__':
    main()
