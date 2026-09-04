"""Check the built ship selection, all 19 loaders and original Adder rendering.

Controlled emulator-only state is used for the renderer comparison; no source
or release payload is patched. Requires the optional SkoolKit installation.
"""
import json
import sys
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, parse, reference, sha
from build import symbol_map
from analyze_ship_blueprints import (GAME_BASE, FIXED_48K_BASE, IDENTITIES,
    Identity, parse_table, fixed_tap_image, geometry_bytes, slice_at)

sys.path.insert(0,str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import A, C, PC, SP, IXh, IXl

SHIP_INSTANCE_SIZE = 39
SHIP_ENERGY_OFFSET = 0x22
SHIP_BLUEPRINT_OFFSET = 0x23
TITLE_SHIP_SLOT = 7
SHIP_Z_HIGH_OFFSET = 7


def canonical_geometry(image, base, record):
    """Resolve every face reference to its normal/visibility, ignoring numbering."""
    def face(index):
        if index == 15:
            return None
        assert index < record['faces']
        return slice_at(image,base,record['faces_address']+4*index,4)
    result=[]
    for key,unit,plain in [('vertices',6,4),('edges',4,3)]:
        raw=slice_at(image,base,record[key+'_address'],record[key]*unit)
        rows=[]
        for start in range(0,len(raw),unit):
            row=raw[start:start+unit]
            normals=tuple(face(index) for v in row[plain:] for index in (v>>4,v&15))
            rows.append((row[:plain],normals))
        result.append(rows)
    return result


def main():
    out=ROOT/'build/ship-variant-check';out.mkdir(parents=True,exist_ok=True)
    report_path=out/'verification.json';report_path.unlink(missing_ok=True)
    symbols=symbol_map(ROOT/'build/game.map')
    image=(ROOT/'build/game.bin').read_bytes()
    tape=RELEASE_TAP.read_bytes()
    assert parse(tape)[5].payload==image
    original=reference()[1][5].payload
    original_records=parse_table(original,GAME_BASE)
    identities=list(IDENTITIES)
    adder=bool(symbols['SHIP_ADDER'])
    if adder:
        identities[17]=Identity('Adder','Adder')
    image_base=symbols['GameImage']
    records=parse_table(image,image_base,identities,compact=adder,
                        table_address=symbols['ShipBlueprintTable'],
                        blueprint_data_limit=symbols['ShipGeometryEnd'])
    # Slot zero is the persistent station, not created by the generic loader.
    # Its initial blueprint pointer must follow model relocation as well.
    station_pointer=symbols['StationBlueprintPointer']
    expected_station=records[0]['address'].to_bytes(2,'little')
    assert image[station_pointer-image_base:station_pointer-image_base+2]==expected_station, \
        'Initial station blueprint pointer does not match the relocated Coriolis'
    comparison=fixed_tap_image('Elite+48K+fixed+B+-+Adder.tap')
    comparison_records=parse_table(comparison,FIXED_48K_BASE,identities)
    for index,record in enumerate(records):
        expected=comparison_records[17] if adder and index==17 else original_records[index]
        source,base=(comparison,FIXED_48K_BASE) if adder and index==17 else (original,GAME_BASE)
        # Relative geometry pointers and the optional face count may change.
        assert record['header'][:5]==expected['header'][:5], record['name']
        assert record['header'][6:12]==expected['header'][6:12], record['name']
        assert record['header'][18:]==expected['header'][18:], record['name']
        if adder and index==17:
            assert canonical_geometry(image,image_base,record)==canonical_geometry(source,base,expected)
        else:
            assert record['faces']==expected['faces']
            assert geometry_bytes(image,image_base,record)==geometry_bytes(source,base,expected)

    rom=(ROOT/'assets/zxspectrum48k.rom').read_bytes()
    assert len(rom)==16384
    def new_sim():
        memory=list(rom)+[0]*(65536-len(rom))
        memory[image_base:image_base+len(image)]=image
        return Simulator(memory,{'PC':symbols['Entry'],'SP':0xFFE8})
    def until(sim, address, limit=200000):
        for _ in range(limit):
            if sim.registers[PC]==address:
                return
            sim.run()
        raise AssertionError(f'Routine did not return; PC=${sim.registers[PC]:04X}')
    def call(sim,label):
        sim.registers[SP]=0xFFE0
        sim.memory[0xFFE0:0xFFE2]=[1,0]  # test-only return sentinel
        sim.registers[PC]=symbols[label]
        until(sim,1)

    sim=new_sim()
    until(sim,symbols['L_718F'])
    assert bytes(sim.memory[station_pointer:station_pointer+2])==expected_station
    # Execute the actual ID lookup and object initialization for EVERY slot.
    first_ship=symbols['InitialRuntimeState']+SHIP_INSTANCE_SIZE
    for index,record in enumerate(records):
        sim.registers[A]=index
        sim.registers[IXh],sim.registers[IXl]=first_ship>>8,first_ship&255
        call(sim,'L_F2FB')
        address=first_ship+SHIP_BLUEPRINT_OFFSET
        assert bytes(sim.memory[address:address+2])==record['address'].to_bytes(2,'little')
        assert sim.memory[first_ship+SHIP_ENERGY_OFFSET]==record['energy']

    rendered=0
    if adder:
        # Compare the real renderer with the 15-normal original Adder. Place
        # that larger test record over the selected model in this private RAM
        # only; the adjacent Viper is not spawned during this isolated test.
        left,right=new_sim(),new_sim()
        for s in (left,right):
            until(s,symbols['L_718F'])
        r=comparison_records[17]
        raw=slice_at(comparison,FIXED_48K_BASE,r['address'],r['geometry_end']-r['address'])
        address=records[17]['address']
        right.memory[address:address+len(raw)]=raw
        for s in (left,right):
            s.registers[C]=15  # the title model helper adds 2 -> ID 17
            call(s,'L_F5D8')
        frames=set()
        for distance in (1,2,4,8):
            for s in (left,right):
                s.memory[symbols['InitialRuntimeState']+TITLE_SHIP_SLOT*SHIP_INSTANCE_SIZE+SHIP_Z_HIGH_OFFSET]=distance
            for _ in range(32):
                for s in (left,right):
                    call(s,'L_745F')
                    call(s,'L_DFDD')
                    call(s,'BlitViewBitmap')
                a=bytes(left.memory[0x4000:0x5B00]);b=bytes(right.memory[0x4000:0x5B00])
                assert a==b, f'Adder rendering differs at frame {rendered}, distance {distance}'
                assert any(a[:4096]), 'Empty render cannot prove geometry equivalence'
                frames.add(sha(a));rendered+=1
        assert len(frames)>20, 'Renderer did not exercise different orientations'
    report=dict(passed=True,machine='ZX Spectrum 48K',rom_sha256=sha(rom),tape_sha256=sha(tape),
                ship='adder' if adder else 'krait',all_ship_loaders=19,
                initial_station_pointer=True,station_pointer_after_startup=True,
                unchanged_other_models=True,canonical_adder_geometry=True if adder else None,
                identical_original_adder_frames=rendered)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
