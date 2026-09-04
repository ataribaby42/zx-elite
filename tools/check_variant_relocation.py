"""Relocate actual optional ASM includes in isolated ZX Spectrum 48K fixtures.

Normal game layout assertions remain intact. These fixtures deliberately move
code, font sources, glyph storage and Adder geometry without editing the release.
External startup/line-renderer calls are observed stubs; their full game routines
are exercised separately by the graphics, laser and ROM-load regressions.
"""
import json
import os
import shutil
import subprocess
import sys
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, sha
from build import symbol_map

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import PC, SP, H, L, D, E, C


def main():
    directory = ROOT/'build/address-audit/relocation'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/'verification.json'
    output.unlink(missing_ok=True)
    release = RELEASE_TAP.read_bytes()
    assembler = os.environ.get('Z80ASM') or shutil.which('z80asm.exe') or shutil.which('z88dk-z80asm') or shutil.which('z80asm')
    if not assembler:
        raise SystemExit('z88dk assembler not found')
    current = symbol_map(ROOT/'build/game.map')
    hardware = ('ScannerEcmOverlap', 'EncounterCircleTop', 'EncounterCircleBottom',
                'EcmIndicatorTop', 'StationIndicatorTop', 'MissileDisplayCoordinates',
                'SingleLaserStartCoordinates')
    reports = []
    for origin, padding in ((0x7000, 7), (0x8000, 31)):
        for font in ('128', '48', '128fix', '128fix_ecm_s'):
            name = f'{origin:04x}-font{font}'
            fixture = directory/f'{name}.asm'
            directives = '\n'.join(f'defc {key} = {current[key]}' for key in hardware)
            font_file = 'font.asm' if font == '128' else f'font-{font}.asm'
            fixture.write_text(f'''{directives}
defc GameLoadAddress = ${origin:04X}
defc FontFirstCode = 32
defc FontGlyphHeight = 8
defc FontRuntime = GameLoadAddress-{current['FontBitmapSize']}
defc CockpitAttributesRuntime = FontRuntime-256
defc VariantStartupStorage = GameLoadAddress+{padding}
defc VariantStartupLimit = VariantStartupStorage+64
defc CockpitIndicatorsStart = GameLoadAddress+$100
defc CockpitIndicatorsLimit = CockpitIndicatorsStart+166
org GameLoadAddress
GameImage:
    defs {padding},0
    INCLUDE "adder-startup.asm"
    defs {padding},0
    INCLUDE "single-laser.asm"
    defs (CockpitIndicatorsStart-GameLoadAddress)-($-GameImage),0
L_A660:
    INCLUDE "scanner-pixel-fix.asm"
L_FF4C:
    LD A,1
    LD (BootstrapCalled),A
    RET
ContinueStartup:
L_7189:
    RET
DrawLine:
    RET
L_BA9D:
    RET
BootstrapCalled:
    defb 0
L_74B2:
    defw 0
EcmTimer:
L_DA16:
    defb 0
StationPresent:
L_7077:
    defb 0
CharacterBlendOpcode:
L_BBBF:
    defb 0
TextColumn:
L_A80D:
    defw 0
L_A845:
    defb 0
    defs {padding},0
    INCLUDE "data/{font_file}"
CockpitAttributes:
    defs 256,$47
defc CockpitAttributesSize = $-CockpitAttributes
    defs {padding},0
    INCLUDE "data/adder.asm"
GameImageEnd:
''', encoding='ascii')
            command = [assembler, '-b', '-m', '-I=src', '-I=src/data',
                       '-O='+directory.relative_to(ROOT).as_posix(), '-o='+name+'.bin',
                       fixture.relative_to(ROOT).as_posix()]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            (directory/f'{name}.log').write_text(result.stdout+result.stderr)
            assert result.returncode == 0, result.stdout+result.stderr
            symbols = symbol_map(directory/f'{name}.map')
            data = (directory/f'{name}.bin').read_bytes()
            ram = [0]*65536
            ram[:0x4000] = (ROOT/'assets/zxspectrum48k.rom').read_bytes()
            ram[origin:origin+len(data)] = data
            stack = 0xFF00  # Test-only stack, outside this fixture.

            def run(label, stop=0):
                ram[stack:stack+2] = [0, 0]
                sim = Simulator(ram, {'PC': symbols[label], 'SP': stack, 'DE': 0x1234, 'C': 0x80})
                for _ in range(20000):
                    if sim.registers[PC] == stop:
                        return sim
                    sim.run()
                raise AssertionError((name, label, 'did not return'))

            sim = run('AdderStartup')
            assert sim.registers[SP] == stack+2
            glyphs = bytes(ram[symbols['FontBitmap']:symbols['FontBitmapEnd']])
            assert bytes(ram[symbols['FontRuntime']:symbols['FontRuntimeEnd']]) == glyphs
            assert ram[symbols['CockpitAttributesRuntime']:symbols['CockpitAttributesRuntime']+256] == [0x47]*256
            assert ram[symbols['BootstrapCalled']] == 1
            assert ram[symbols['L_74B2']:symbols['L_74B2']+2] == list(stack.to_bytes(2,'little'))
            sim = run('SingleLaser', symbols['DrawLine'])
            assert tuple(sim.registers[r] for r in (H,L,D,E,C)) == (0,63,0x12,0x34,0x83)
            sim.run()
            assert sim.registers[PC] == 0 and sim.registers[SP] == stack+2

            header = symbols['ShipAdderBlueprint']
            for offset, label in ((12,'ShipAdderVertices'), (14,'ShipAdderEdges'), (16,'ShipAdderFaces')):
                assert int.from_bytes(bytes(ram[header+offset:header+offset+2]),'little') == symbols[label]-header
            for ecm in (0, 1):
                for station in (0, 1):
                    for old in (0, 255):
                        ram[0x4000:0x5B00] = [old]*0x1B00
                        expected = ram[0x4000:0x5B00].copy()
                        tiles = [(0x5029,0x26), (0x5049,0x24)]
                        tiles += list(zip((0x50C8,0x50C9,0x50E8,0x50E9),
                                          (0x3B,0x3C,0x3D,0x3E) if ecm else (0x20,0x20,0x40,0x40)))
                        tiles += list(zip((0x50D6,0x50D7,0x50F6,0x50F7),
                                          (0x5B,0x5C,0x5D,0x5E) if station else (0x20,0x5F,0x40,0x2B)))
                        for address, code in tiles:
                            for row in range(8):
                                value = glyphs[(code-32)*8+row]
                                if address == symbols['ScannerEcmOverlap'] and row == 0:
                                    value = (value&254)|(old&1)
                                expected[address+row*256-0x4000] = value
                        ram[symbols['L_DA16']], ram[symbols['L_7077']] = ecm, station
                        sim = run('L_A660')
                        assert sim.registers[SP] == stack+2
                        assert ram[0x4000:0x5B00] == expected, (name, ecm, station, old)
            reports.append(dict(font=font, origin=origin, startup=symbols['AdderStartup'],
                font_source=symbols['FontBitmap'], font_runtime=symbols['FontRuntime'],
                laser=symbols['SingleLaser'], line_target=symbols['DrawLine'],
                indicator=symbols['L_A660'], adder_blueprint=header, indicator_cases=8))
    assert RELEASE_TAP.read_bytes() == release
    output.write_text(json.dumps(dict(passed=True, machine='ZX Spectrum 48K',
        release_unchanged=True, release_sha256=sha(release), fixtures=reports),indent=2)+'\n')
    print('PASS: eight relocated ASM fixtures; startup copies, laser target/parameters, 64 indicator cases and Adder geometry pointers; release unchanged.')


if __name__ == '__main__':
    main()
