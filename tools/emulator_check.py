"""Local-only Z80 smoke test using optional SkoolKit 10.0, no game patches.

Loads the freshly built TAP through a simulated Spectrum ROM LOAD, then runs
the actual Z80 code with frame interrupts and optional Spectrum matrix keys.
"""
import argparse
import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, sha
from build import symbol_map

MACHINE = 'ZX Spectrum 48K'
ROM48 = ROOT/'assets/zxspectrum48k.rom'

sys.path.insert(0,str(ANALYSIS_DEPS))
try:
    from skoolkit import tap2sna, CSimulator
    from skoolkit.snapshot import Snapshot
    from skoolkit.simutils import from_snapshot, PC, T
    from skoolkit.trace import Tracer
    from skoolkit.simulator import Simulator
except ImportError:
    raise SystemExit('Run tools\\install_analysis_tools.bat first.')

KEY_ROWS = ['CS Z X C V','A S D F G','Q W E R T','1 2 3 4 5',
            '0 9 8 7 6','P O I U Y','ENTER L K J H','SPACE SS M N B']
KEYS = {key:(row,1<<bit) for row,line in enumerate(KEY_ROWS) for bit,key in enumerate(line.split())}

class TrackedMemory(list):
    """List-compatible Spectrum memory with optional integer access logging."""
    def __init__(self, values):
        super().__init__(values)
        self.tracking = False
        self.read_addresses = set()
        self.write_addresses = set()

    def __getitem__(self, key):
        if self.tracking and isinstance(key, int):
            self.read_addresses.add(key & 0xFFFF)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        if self.tracking and isinstance(key, int):
            self.write_addresses.add(key & 0xFFFF)
        return super().__setitem__(key, value)

class AccessSimulator(Simulator):
    def __init__(self, memory, registers=None, state=None, config=None):
        super().__init__(TrackedMemory(memory), registers, state, config)

def screen_text(screen, font):
    """Return text rows whose 8x8 cells exactly match the Elite font.

    This deliberately ignores cells used by the 3D view and instruments.  It
    is useful for proving which menu or status screen a scripted run reached
    without creating or visually interpreting a screenshot.
    """
    glyphs = {}
    for offset in range(0, len(font), 8):
        glyphs.setdefault(bytes(font[offset:offset + 8]), chr(0x20 + offset // 8))
    rows = []
    for cell_y in range(24):
        chars = []
        for cell_x in range(32):
            bitmap = bytes(
                screen[((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | cell_x]
                for y in range(cell_y * 8, cell_y * 8 + 8)
            )
            chars.append(glyphs.get(bitmap, ' '))
        row = ''.join(chars).strip()
        if re.search(r'[A-Za-z]{2}', row):
            rows.append(dict(row=cell_y, text=row))
    return rows

def changed_ranges(before, after, start=0x4000):
    """Compact a RAM byte diff into half-open address ranges."""
    changed = [address for address in range(start, min(len(before), len(after)))
               if before[address] != after[address]]
    ranges = []
    for address in changed:
        if ranges and ranges[-1][1] == address:
            ranges[-1][1] += 1
        else:
            ranges.append([address, address + 1])
    return changed, ranges

def png(screen,path):
    # Decode the physical Spectrum bitmap/attribute layout without changing it.
    lines=[]
    for y in range(192):
        row=bytearray()
        for x in range(256):
            a=screen[6144+(y//8)*32+x//8]
            bits=screen[((y&0xC0)<<5)|((y&7)<<8)|((y&0x38)<<2)|(x//8)]
            c=(a&7) if bits & (128>>(x&7)) else (a>>3)&7
            level=255 if a&64 else 205
            pixel=bytes([level if c&2 else 0,level if c&4 else 0,level if c&1 else 0])
            row.extend(pixel*2)
        lines.extend([b'\0'+row,b'\0'+row])
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xFFFFFFFF)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',512,384,8,2,0,0,0))
    data+=chunk(b'IDAT',zlib.compress(b''.join(lines)))+chunk(b'IEND',b'')
    path.write_bytes(data)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seconds',type=float,default=3)
    p.add_argument('--key',action='append',default=[],metavar='START:DURATION:KEY')
    p.add_argument('--poke',action='append',default=[],metavar='START:ADDRESS:HEXBYTES',
                   help='test-only timed RAM change, e.g. 7:0xA828:98008096')
    p.add_argument('--name',default='boot')
    p.add_argument('--no-screenshots',action='store_true',
                   help='record execution, RAM and recognised text without writing PNG files')
    p.add_argument('--memory-accesses',action='store_true',
                   help='use the slower Python simulator and record RAM reads and writes')
    args=p.parse_args()
    if args.seconds<=0 or args.seconds>120:
        raise SystemExit('Duration must be 0..120 seconds.')
    if not args.name.replace('-','').replace('_','').isalnum():
        raise SystemExit('Name must be a simple artifact basename.')
    events=[]
    for spec in args.key:
        start,duration,key=spec.split(':')
        if key.upper() not in KEYS: raise SystemExit('Unknown key: '+key)
        events.append((float(start),float(start)+float(duration),key.upper()))
    pokes=[]
    for spec in args.poke:
        start,address,data=spec.split(':')
        try:
            payload=bytes.fromhex(data)
            address=int(address,0)
        except ValueError as error:
            raise SystemExit('Invalid poke: '+spec) from error
        if not payload or not 0x4000<=address or address+len(payload)>0x10000:
            raise SystemExit('Poke must contain RAM bytes within $4000..$FFFF: '+spec)
        pokes.append(dict(start=float(start),address=address,data=payload,applied=False))
    out=ROOT/'build/emulator';out.mkdir(parents=True,exist_ok=True)
    os.chdir(ROOT)
    rom=ROM48.read_bytes()
    symbols=symbol_map(ROOT/'build/game.map')
    entry=symbols['Entry']
    image_start,image_end=symbols['GameImage'],symbols['GameImageEnd']
    if len(rom)!=16384:
        raise AssertionError('ZX Spectrum 48K ROM must be exactly 16 KiB')
    tap2sna.ROM48=str(ROM48)
    # Relative tape path avoids interpreting a Windows drive letter as a URL.
    tap2sna.main(['--start',hex(entry),RELEASE_TAP.relative_to(ROOT).as_posix(),'build/emulator/loaded.z80'])
    snapshot=Snapshot.get('build/emulator/loaded.z80')
    simulator_class=AccessSimulator if args.memory_accesses else (CSimulator or Simulator)
    simulator=from_snapshot(simulator_class,snapshot,rom_file=tap2sna.ROM48)
    if simulator.registers[PC]!=entry: raise AssertionError('Loader entry changed')
    original_image=(ROOT/'build/game.bin').read_bytes()
    if bytes(simulator.memory[image_start:image_end])!=original_image:
        raise AssertionError('ROM LOAD changed the initial game image')
    initial_ram=bytes(simulator.memory)
    font=original_image[symbols['FontBitmap']-image_start:symbols['FontBitmapEnd']-image_start]
    trace=Tracer(simulator,snapshot.border,snapshot.out7ffd,snapshot.outfffd,snapshot.ay,snapshot.outfe,False)
    simulator.set_tracer(trace)
    if args.memory_accesses:
        simulator.memory.tracking=True
    executed=set();start_t=simulator.registers[T]
    captures={}; text_captures={}; next_second=1
    def draw(screen,frame,border,keyboard):
        nonlocal next_second
        elapsed=(simulator.registers[T]-start_t)/3500000
        keyboard[:]=[0]*8
        for begin,end,key in events:
            if begin<=elapsed<end:
                row,mask=KEYS[key];keyboard[row]|=mask
        for poke_event in pokes:
            if not poke_event['applied'] and elapsed>=poke_event['start']:
                address=poke_event['address'];data=poke_event['data']
                simulator.memory[address:address+len(data)]=data
                poke_event['applied']=True
        if elapsed>=next_second:
            if not args.no_screenshots:
                png(screen,out/f'{args.name}-{next_second:02}.png')
            captures[str(next_second)]=sha(bytes(screen));next_second+=1
            text_captures[str(next_second-1)]=screen_text(screen,font)
        return True
    trace.run(entry,None,0,int(args.seconds*3500000),True,draw,executed,None,None,'$','02X','04X')
    ram=bytes(simulator.memory)
    # Unlike ordinary ships, station slot zero starts with a stored blueprint
    # pointer. Check it before and after every complete gameplay scenario.
    station_pointer=symbols['StationBlueprintPointer']
    station_blueprint=symbols['ShipCoriolisStationBlueprint'].to_bytes(2,'little')
    for label,memory in [('loaded',initial_ram),('final',ram)]:
        if memory[station_pointer:station_pointer+2] != station_blueprint:
            raise AssertionError(f'{label}: station blueprint pointer does not match Coriolis')
    # A reset into ROM can otherwise finish a timed trace with exit status 0.
    # Both text tables must survive every gameplay scenario unchanged.
    for address,size in [(symbols['Entry'],3),(symbols['L_6FA3'],symbols['L_6FA3Size']),
                         (symbols['L_6FBF'],symbols['L_6FBFSize'])]:
        if ram[address:address+size] != initial_ram[address:address+size]:
            raise AssertionError(f'Persistent code/text table was overwritten at ${address:04X}')
    if symbols['SHIP_ADDER'] and any(symbols['Startup']<=pc<symbols['L_7189'] for pc in executed):
        raise AssertionError('Execution entered the reclaimed startup text table')
    if not args.no_screenshots:
        png(ram[0x4000:0x5B00],out/f'{args.name}-final.png')
    (out/f'{args.name}-memory.bin').write_bytes(ram)
    changed, ranges=changed_ranges(initial_ram,ram)
    game_changed, game_ranges=changed_ranges(initial_ram,ram,image_start)
    game_changed=[address for address in game_changed if address<image_end]
    game_ranges=[]
    for address in game_changed:
        if game_ranges and game_ranges[-1][1]==address:
            game_ranges[-1][1]+=1
        else:
            game_ranges.append([address,address+1])
    final_text=screen_text(ram[0x4000:0x5B00],font)
    report=dict(machine=MACHINE,tape_sha256=sha(RELEASE_TAP.read_bytes()),
                rom_sha256=sha(Path(tap2sna.ROM48).read_bytes()),entry=entry,
                pc=simulator.registers[PC],tstates=simulator.registers[T]-start_t,
                operations=trace.operations,executed_addresses=len(executed),
                game_executed_addresses=len([a for a in executed if image_start<=a<image_end]),
                keys=events,
                station_blueprint_pointer_valid=True,
                test_pokes=[dict(start=e['start'],address=e['address'],
                                 data=e['data'].hex(),applied=e['applied']) for e in pokes],
                screen_sha256=sha(ram[0x4000:0x5B00]),captures=captures,
                text_captures=text_captures,final_text=final_text,
                changed_ram_bytes=len(changed),changed_ram_ranges=ranges,
                changed_game_image_bytes=len(game_changed),changed_game_image_ranges=game_ranges,
                execution_map=sorted(executed))
    if args.memory_accesses:
        report['memory_read_map']=sorted(simulator.memory.read_addresses)
        report['memory_write_map']=sorted(simulator.memory.write_addresses)
    (out/f'{args.name}.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Machine: '+MACHINE)
    print(f"Executed {trace.operations:,} actual Z80 instructions; {report['game_executed_addresses']} distinct PCs in the game image.")
    for row in final_text:
        print(f"Text row {row['row']:02}: {row['text']}")
    if not args.no_screenshots:
        print('Final screen: '+str(out/f'{args.name}-final.png'))

if __name__=='__main__': main()
