"""Verify identified font/cockpit data by executing the original Z80 routines.

Uses controlled RAM/register setup for isolated copy and glyph tests; no game
instructions are patched. Normal ROM loading/launch is tested separately by
emulator_check.py. Requires the optional local SkoolKit analysis dependency.
"""
import json
import sys
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, parse, sha
from build import symbol_map
from font_variant import patch_font, fixed_font, selected_font
from tape import reference

MACHINE = 'ZX Spectrum 48K'

sys.path.insert(0,str(ANALYSIS_DEPS))
try:
    from skoolkit.simulator import Simulator
    from skoolkit.simutils import A, D, E, PC, SP
except ImportError:
    raise SystemExit('Run tools\\install_analysis_tools.bat first.')


def main():
    output=ROOT/'build/graphics-check';output.mkdir(parents=True,exist_ok=True)
    (output/'verification.json').unlink(missing_ok=True)
    symbols=symbol_map(ROOT/'build/game.map')
    image=(ROOT/'build/game.bin').read_bytes()
    tape_bytes=RELEASE_TAP.read_bytes()
    assert parse(tape_bytes)[5].payload==image, 'Build image differs from release TAP'
    memory=[0]*65536
    rom=(ROOT/'assets/zxspectrum48k.rom').read_bytes()
    assert len(rom)==16384, 'ZX Spectrum 48K ROM must be exactly 16 KiB'
    memory[:0x4000]=rom
    memory[symbols['GameImage']:symbols['GameImageEnd']]=image
    simulator=Simulator(memory,{'PC':symbols['Entry'],'SP':0x5CF0})
    operations=0

    def until(label,limit=20000):
        nonlocal operations
        for _ in range(limit):
            if simulator.registers[PC]==symbols[label]: return
            simulator.run();operations+=1
        raise AssertionError('Did not reach '+label)

    def region(label):
        return bytes(memory[symbols[label]:symbols[label+'End']])

    def equal_at(address,expected):
        assert bytes(memory[address:address+len(expected)])==expected, hex(address)

    font=region('FontBitmap')
    if symbols['FONT_48']:
        assert font==patch_font()[0]
    if selected_font(symbols) in ('128fix', '128fix_ecm_s'):
        original = reference()[1][5].payload
        start = symbols['FontBitmap']-symbols['GameImage']
        assert font == fixed_font(original[start:start+len(font)], ecm_s=selected_font(symbols)=='128fix_ecm_s')
    bitmap=region('CockpitBitmap')
    attributes=region('CockpitAttributes')
    # Execute actual startup instructions through both LDIR operations.
    until('StartupAfterGraphicsCopy')
    equal_at(symbols['FontRuntime'],font)
    equal_at(symbols['CockpitAttributesRuntime'],attributes)

    simulator.registers[PC]=symbols['RestoreCockpitBitmap']
    until('CockpitRestored')
    equal_at(symbols['ScreenCockpitBitmap'],bitmap)
    equal_at(symbols['ScreenCockpitAttributes'],attributes)

    # Exercise the opposite direction too: this memory is a mutable backup.
    test_bitmap=bytes((i*37+19)&255 for i in range(len(bitmap)))
    test_attributes=bytes((i*11+3)&255 for i in range(len(attributes)))
    memory[symbols['ScreenCockpitBitmap']:symbols['ScreenCockpitBitmap']+len(bitmap)]=test_bitmap
    memory[symbols['ScreenCockpitAttributes']:symbols['ScreenCockpitAttributes']+len(attributes)]=test_attributes
    simulator.registers[PC]=symbols['SaveCockpitBitmap']
    until('CockpitSaved')
    equal_at(symbols['CockpitBitmap'],test_bitmap)
    equal_at(symbols['CockpitAttributesRuntime'],test_attributes)
    memory[0x4000:0x5B00]=[0]*0x1B00
    simulator.registers[PC]=symbols['RestoreCockpitBitmap']
    until('CockpitRestored')
    equal_at(symbols['ScreenCockpitBitmap'],test_bitmap)
    equal_at(symbols['ScreenCockpitAttributes'],test_attributes)

    # Run the real address selection and eight-row XOR loop for every glyph.
    first=symbols['FontFirstCode'];height=symbols['FontGlyphHeight']
    count=symbols['FontGlyphCount']
    for glyph in range(count):
        memory[0x4000:0x5800]=[0]*0x1800
        memory[symbols['L_A80D']]=0  # current character column
        memory[symbols['L_A80E']]=0  # current character row
        simulator.registers[A]=first+glyph
        simulator.registers[SP]=0x5CF0
        simulator.registers[PC]=symbols['GetCharacterBitmap']
        reads=[]
        for _ in range(256):
            if simulator.registers[PC]==symbols['CharacterDrawn']: break
            if simulator.registers[PC]==symbols['DrawCharacterRow']:
                reads.append(simulator.registers[D]*256+simulator.registers[E])
            simulator.run();operations+=1
        else:
            raise AssertionError('Character loop failed for '+hex(first+glyph))
        assert reads==list(range(symbols['FontRuntime']+glyph*height,
                                 symbols['FontRuntime']+(glyph+1)*height))
        expected=bytearray(0x1800)
        for row,value in enumerate(font[glyph*height:(glyph+1)*height]):
            expected[row*256]=value
        equal_at(0x4000,expected)
        # Drawing the same glyph twice with XOR must erase it again.
        simulator.registers[A]=first+glyph
        simulator.registers[PC]=symbols['GetCharacterBitmap']
        until('CharacterDrawn')
        equal_at(0x4000,bytes(0x1800))

    report=dict(passed=True,machine=MACHINE,tape_sha256=sha(tape_bytes),
                font=selected_font(symbols),
                font_address=symbols['FontBitmap'],font_bytes=len(font),
                glyph_count=count,first_code=first,last_code=first+count-1,
                font_runtime=symbols['FontRuntime'],
                cockpit_address=symbols['CockpitBitmap'],cockpit_bytes=len(bitmap),
                attribute_address=symbols['CockpitAttributes'],attribute_bytes=len(attributes),
                startup_copy=True,cockpit_restore=True,cockpit_backup_roundtrip=True,
                all_glyphs_drawn_and_erased=True,instructions_executed=operations)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Machine: '+MACHINE)
    print(f'PASS: startup font/colour copies, cockpit save/restore, all {count} glyphs drawn and XOR-erased.')
    print(f'Executed {operations:,} original Z80 instructions with controlled RAM/register setup.')


if __name__=='__main__': main()
