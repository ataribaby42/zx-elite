"""Assemble a reference or modified image; always validate the TAP container."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tape import ROOT, RELEASE_TAP, DEFAULT_TAPFILE, release_tap, frame, header, parse, reference, validate_pairs, describe, sha

BUILD = ROOT / 'build'
OUTPUT = RELEASE_TAP

def symbol_map(path):
    return {m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9A-Fa-f]+)',path.read_text(),re.M)}

def check_source_includes(source, active=None):
    """Apply the no-binary-inclusion rule to the complete ASM include tree."""
    source=source.resolve()
    active=set() if active is None else active
    if not source.is_relative_to(ROOT/'src') or source in active:
        raise ValueError('Unsafe or cyclic source include: '+str(source))
    active.add(source)
    text=source.read_text()
    if re.search(r'^\s*(?:INCBIN|BINARY)\b',text,re.I|re.M):
        raise ValueError(f'{source.name}: external binary inclusion is not permitted in the reconstruction')
    for included in re.findall(r'^\s*INCLUDE\s+"([^"]+)"',text,re.I|re.M):
        check_source_includes(source.parent/included,active)
    active.remove(source)

def verify(output=OUTPUT, exact=True):
    # A failed verification must not leave a previous PASS report behind.
    (BUILD/'verification.json').unlink(missing_ok=True)
    rebuilt = output.read_bytes()
    blocks = parse(rebuilt)
    validate_pairs(blocks)
    if len(blocks) != 6:
        raise ValueError('TAP block count changed')
    # Verification=no disables identity only. Metadata and fixed memory-map
    # limits are constraints even for deliberately modified game payloads.
    for index, (name,kind,size,p1,p2) in enumerate([
        ('ELITE',0,130,10,130), ('a',3,6912,0x8000,0x8000),
        ('elite',3,40801,0x6048,0x8000),
    ]):
        if blocks[2*index].payload != header(kind,name,size,p1,p2):
            raise ValueError(f'TAP header metadata changed for {name}')
        if len(blocks[2*index+1].payload) != size:
            raise ValueError(f'TAP payload size changed for {name}')
    original = reference()[0] if exact else None
    if exact and rebuilt != original:
        first = next((i for i,(a,b) in enumerate(zip(original,rebuilt)) if a!=b), min(len(original),len(rebuilt)))
        raise ValueError(f'Binary identity FAILED: first difference at TAP offset {first}; lengths {len(original)} / {len(rebuilt)}')
    report = dict(structural_validation=True,identity_check='passed' if exact else 'disabled',
                  binary_identical=True if exact else None,size=len(rebuilt),sha256=sha(rebuilt),blocks=describe(blocks))
    BUILD.mkdir(parents=True,exist_ok=True)
    (BUILD/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: all {len(blocks)} TAP blocks, metadata, lengths and checksums; {len(rebuilt):,} bytes.')
    print('Binary identity: '+('PASS (exact original bytes).' if exact else 'DISABLED (modified builds allowed).'))
    print('SHA256: '+sha(rebuilt))
    return report

def assemble(ship='krait', exact=True, laser='original', font='128', scannerpixelfix='no', stationrandomlaunchfix='no', tapfile=DEFAULT_TAPFILE):
    output = release_tap(tapfile)
    BUILD.mkdir(parents=True,exist_ok=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Delete only named generated success artifacts, never source/reference data.
    output.unlink(missing_ok=True)
    (BUILD/'verification.json').unlink(missing_ok=True)
    assembler = os.environ.get('Z80ASM') or shutil.which('z80asm.exe') or shutil.which('z88dk-z80asm') or shutil.which('z80asm')
    if not assembler:
        raise ValueError('z88dk z80asm.exe not found; add z88dk/bin to PATH or set Z80ASM to the executable path')
    version = subprocess.run([assembler],text=True,capture_output=True,check=True).stdout.strip()
    (BUILD/'assembler-version.txt').write_text(version+'\n',encoding='utf-8')
    print(version)
    for name in ['basic','screen','game']:
        source=ROOT/'src'/f'{name}.asm'
        check_source_includes(source)
        binary=BUILD/f'{name}.bin';binary.unlink(missing_ok=True)
        command=[assembler,'-b','-m',f'-DSHIP_ADDER={int(ship=="adder")}',
                 f'-DLASER_SINGLE={int(laser=="single")}',f'-DFONT_48={int(font=="48")}', f'-DFONT_128FIX={int(font=="128fix")}', f'-DFONT_128FIX_ECM_S={int(font=="128fix_ecm_s")}',
                 f'-DSCANNER_PIXEL_FIX={int(scannerpixelfix=="yes")}',
                 f'-DSTATION_RANDOM_LAUNCH_FIX={int(stationrandomlaunchfix=="yes")}',
                 '-I=src','-I=src/data','-O=build',f'-o={name}.bin',f'src/{name}.asm']
        run=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
        (BUILD/f'{name}-assemble.log').write_text(run.stdout+run.stderr,encoding='utf-8')
        if run.returncode:
            raise ValueError(f'Assembly failed ({name}):\n{run.stdout}{run.stderr}')
        if not binary.is_file():
            raise ValueError(f'Assembler did not create {binary}')
        print(f'Assembled {source.relative_to(ROOT)}: {binary.stat().st_size:,} bytes')
    symbols=symbol_map(BUILD/'game.map')
    if (symbols['GameImage'],symbols['Entry'],symbols['GameImageEnd']) != (0x6048,0x7000,0xFFA9):
        raise ValueError('Linked game origin, entry or end address changed')
    if symbols['FontRuntimeEnd'] != symbols['GameImage']:
        raise ValueError('Relocated font must end immediately before the game image')
    game=(BUILD/'game.bin').read_bytes()
    station_pointer=symbols['StationBlueprintPointer']-symbols['GameImage']
    if game[station_pointer:station_pointer+2] != symbols['ShipCoriolisStationBlueprint'].to_bytes(2,'little'):
        raise ValueError('Initial station blueprint pointer does not match the assembled Coriolis')
    if len(game) != symbols['GameImageEnd']-symbols['GameImage']:
        raise ValueError('Linked game length does not match the symbol map')
    basic=(BUILD/'basic.bin').read_bytes(); screen=(BUILD/'screen.bin').read_bytes()
    if (len(basic),len(screen),len(game)) != (130,6912,40801):
        raise ValueError('One of the source payload sizes changed')
    # Original container metadata. Payload lengths are always derived from the
    # assembled images. +zx/appmake would create a different BASIC loader.
    pieces=[]
    for name,kind,payload,p1,p2 in [
        ('ELITE',0,basic,10,len(basic)),
        ('a',3,screen,0x8000,0x8000),
        ('elite',3,game,symbols['GameImage'],0x8000),
    ]:
        pieces.extend([frame(0,header(kind,name,len(payload),p1,p2)),frame(255,payload)])
    candidate=BUILD/'elite-128k.candidate.tap'
    candidate.write_bytes(b''.join(pieces))
    try:
        report=verify(candidate, exact)
        report['ship']=ship
        report['laser']=laser
        report['font']=font
        report['scannerpixelfix']=scannerpixelfix
        report['stationrandomlaunchfix']=stationrandomlaunchfix
        report['tapfile']=tapfile
        candidate.replace(output)
        (BUILD/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    finally:
        candidate.unlink(missing_ok=True)
    print('Ready: '+str(output))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tapfile', default=DEFAULT_TAPFILE, help='output filename in release/ (default: %(default)s)')
    p.add_argument('--verify-only',action='store_true')
    p.add_argument('--ship',choices=['krait','adder'],default='krait',help='blueprint in slot 17 (default: krait)')
    p.add_argument('--laser',choices=['original','single'],default='original',help='original beams or one centred beam with endpoint wiggle (default: original)')
    p.add_argument('--font',choices=['128','48','128fix','128fix_ecm_s'],default='128',help='original font, prettier font from the 48K version (48), or fix the corrupted compass in the Elite 128K instrument panel (128fix); 128fix_ecm_s also uses the smaller ECM and S indicators from the 48K version (default: 128)')
    p.add_argument('--scannerpixelfix',choices=['no','yes'],default='no',help='preserve the scanner pixel overlapped by the ECM indicator (default: no)')
    p.add_argument('--stationrandomlaunchfix',choices=['no','yes'],default='no',help='allow both Cobra and Python station traders without changing police launches (default: no)')
    p.add_argument('--verify',choices=['yes','no'],default='yes',help='exact original-byte comparison (default: yes); structural checks always run')
    # Also accept make.bat ship=adder laser=single verify=no.
    arguments=[]
    for value in sys.argv[1:]:
        if value.startswith(('ship=','laser=','font=','scannerpixelfix=','stationrandomlaunchfix=','verify=','tapfile=')):
            key,setting=value.split('=',1)
            arguments += ['--'+key,setting]
        else:
            arguments.append(value)
    args=p.parse_args(arguments)
    try:
        if args.verify_only: verify(output=release_tap(args.tapfile),exact=args.verify=='yes')
        else: assemble(args.ship,args.verify=='yes',args.laser,args.font,args.scannerpixelfix,args.stationrandomlaunchfix,args.tapfile)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as ex:
        (BUILD/'verification.json').unlink(missing_ok=True)
        print('ERROR: '+str(ex),file=sys.stderr);return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
