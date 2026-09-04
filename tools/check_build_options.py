"""Exercise all build options; leave Adder/single/48K and both fixes built."""
from itertools import product
import json
import subprocess
import sys
from tape import ROOT, RELEASE_TAP, frame, parse, reference, sha
from build import symbol_map, verify
from font_variant import patch_font, fixed_font


def main():
    directory=ROOT/'build/build-options-check';directory.mkdir(parents=True,exist_ok=True)
    report=directory/'verification.json';report.unlink(missing_ok=True)
    def run(name,*args,success=True):
        result=subprocess.run([sys.executable,str(ROOT/'tools/build.py'),*args],cwd=ROOT,
                              capture_output=True,text=True)
        (directory/f'{name}.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        assert (result.returncode==0)==success, result.stdout+result.stderr
        return result
    run('defaults')
    assert RELEASE_TAP.read_bytes()==reference()[0]
    run('adder-relaxed','ship=adder','verify=no')
    baseline = {'krait': reference()[0], 'adder': RELEASE_TAP.read_bytes()}
    run('scanner-fix-baseline', 'scannerpixelfix=yes', 'verify=no')
    scanner_image = parse(RELEASE_TAP.read_bytes())[5].payload
    scanner_symbols = symbol_map(ROOT/'build/game.map')
    run('station-launch-fix-baseline', 'stationrandomlaunchfix=yes', 'verify=no')
    station_image = parse(RELEASE_TAP.read_bytes())[5].payload
    station_symbols = symbol_map(ROOT/'build/game.map')
    station_range = (station_symbols['L_F44A'], station_symbols['L_F470'])
    assert station_range == (0xF44A, 0xF470)
    # Only the instrument region and its two existing call/jump references
    # may move. These are original-image landmarks, not hand-linked targets.
    scanner_base = scanner_symbols['GameImage']
    scanner_changes = [(scanner_symbols['L_A660'], scanner_symbols['CockpitIndicatorsLimit'])]
    for address, opcode, target in ((scanner_symbols['L_9A46'], 0xCD, 'L_A6D3'),
                                     (scanner_symbols['L_A777'], 0xC3, 'L_A6D3')):
        offset = address-scanner_base
        assert scanner_image[offset] == opcode
        assert scanner_image[offset+1:offset+3] == scanner_symbols[target].to_bytes(2, 'little')
        scanner_changes.append((address+1, address+3))
    combinations=[]
    for ship, laser, font, scanner, station in product(('krait','adder'), ('original','single'), ('128fix_ecm_s','128fix','128','48'), ('no','yes'), ('no','yes')):
        name=f'{ship}-{laser}-font{font}-scanner{scanner}-station{station}'
        exact=(ship,laser,font,scanner,station)==('krait','original','128','no','no')
        result=run(name+'-exact',f'ship={ship}',f'laser={laser}',f'font={font}',
                   f'scannerpixelfix={scanner}', f'stationrandomlaunchfix={station}', 'verify=yes',success=exact)
        if not exact:
            assert 'Binary identity FAILED' in result.stderr
            assert not RELEASE_TAP.exists(), 'Failed build left a stale release'
            assert not (ROOT/'build/verification.json').exists()
        run(name+'-relaxed','--ship',ship,'--laser',laser,'--font',font,
            '--scannerpixelfix',scanner,'--stationrandomlaunchfix',station,'--verify','no')
        symbols=symbol_map(ROOT/'build/game.map')
        # Independently reproduce only the selected changes in each ship's
        # baseline. Font bytes must match the supplied TAP, not an ASM fixture.
        blocks=parse(baseline[ship])
        payload=bytearray(blocks[5].payload)
        if laser=='single':
            offset=symbols['LaserPatchSite']-symbols['GameImage']
            patch=bytes.fromhex('21 3f 00 79 f6 03 4f c3')+symbols['DrawLine'].to_bytes(2,'little')
            payload[offset:offset+len(patch)]=patch
        if font!='128':
            start,end=symbols['FontBitmap'],symbols['FontBitmapEnd']
            font_bytes=patch_font()[0] if font=='48' else fixed_font(bytes(payload[start-symbols['GameImage']:end-symbols['GameImage']]), ecm_s=font=='128fix_ecm_s')
            assert len(font_bytes)==end-start
            payload[start-symbols['GameImage']:end-symbols['GameImage']]=font_bytes
        if scanner=='yes':
            for start, end in scanner_changes:
                payload[start-symbols['GameImage']:end-symbols['GameImage']] = scanner_image[start-scanner_base:end-scanner_base]
        if station=='yes':
            start, end = station_range
            payload[start-symbols['GameImage']:end-symbols['GameImage']] = station_image[start-station_symbols['GameImage']:end-station_symbols['GameImage']]
        expected=b''.join(frame(b.flag,bytes(payload) if i==5 else b.payload) for i,b in enumerate(blocks))
        assert RELEASE_TAP.read_bytes()==expected, f'{name}: unrelated bytes changed'
        metadata=json.loads((ROOT/'build/verification.json').read_text())
        assert (metadata['ship'],metadata['laser'],metadata['font'],metadata['scannerpixelfix'],metadata['stationrandomlaunchfix'])==(ship,laser,font,scanner,station)
        combinations.append(dict(ship=ship,laser=laser,font=font,scannerpixelfix=scanner,stationrandomlaunchfix=station,strict_accepted=exact,
                                 relaxed_sha256=sha(expected)))
    run('invalid-font','font=47',success=False)
    run('invalid-scanner-fix','scannerpixelfix=maybe',success=False)
    run('invalid-station-launch-fix','stationrandomlaunchfix=maybe',success=False)
    good=RELEASE_TAP.read_bytes()
    failed=run('verify-exact-rejected','--verify-only',success=False)
    assert 'Binary identity FAILED' in failed.stderr
    assert not (ROOT/'build/verification.json').exists()
    # Corrupt the checksum, then a header with a correctly recalculated XOR.
    # Both must fail even when original-byte comparison is switched off.
    checksum=bytearray(good);checksum[-1]^=1
    blocks=parse(good)
    changed=bytearray(blocks[4].payload);changed[13]^=1
    bad_header=b''.join(frame(b.flag,bytes(changed) if i==4 else b.payload) for i,b in enumerate(blocks))
    for name,contents in [('bad-checksum',checksum),('bad-header',bad_header),('truncated',good[:-1])]:
        path=directory/f'{name}.tap';path.write_bytes(contents)
        try:
            try:
                verify(path,exact=False)
            except ValueError:
                pass
            else:
                raise AssertionError(name+' was accepted with verify=no')
        finally:
            path.unlink()
    run('verify-relaxed','--verify-only','verify=no')
    assert RELEASE_TAP.read_bytes()==good
    report.write_text(json.dumps(dict(passed=True,all_128_combinations=True,combinations=combinations,
        strict_adder_rejected=True,corrupt_tapes_rejected_without_identity=True,
        single_laser_exact_patch=True,strict_single_laser_rejected=True,
        patch_font_matches_source_tape=True,strict_font48_rejected=True,
        scanner_fix_changes_scoped=True,final_scannerpixelfix='yes',
        station_launch_fix_changes_scoped=True,final_stationrandomlaunchfix='yes',
        final_ship='adder',final_laser='single',final_font='48',final_tape_sha256=sha(good)),indent=2)+'\n',encoding='utf-8')
    print('PASS: all 128 ship/laser/font/scannerpixelfix/stationrandomlaunchfix combinations in both verification modes, scoped patches, stale-output handling, corrupt TAP rejection.')


if __name__=='__main__':
    main()
