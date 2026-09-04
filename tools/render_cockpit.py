"""Render the initial cockpit bitmap, alone and with its stored colour cells.

Reads assembled data using the current linker symbols. Standard library only;
no emulator state, procedural instrument updates or image interpolation.
"""
from collections import Counter
import json
import struct
import zlib
from tape import ROOT, RELEASE_TAP, parse, sha
from build import symbol_map


def save_png(path,width,height,rgb):
    def chunk(kind,data):
        return (struct.pack('>I',len(data))+kind+data+
                struct.pack('>I',zlib.crc32(kind+data)&0xFFFFFFFF))
    rows=b''.join(b'\0'+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    encoded=(b'\x89PNG\r\n\x1a\n'+
             chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
             chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))
    path.write_bytes(encoded)


def render(bitmap,attributes,scale=3):
    rows=[]
    for y in range(64):
        row=bytearray()
        for x in range(256):
            offset=((y&7)<<8)|((y&0x38)<<2)|(x>>3)
            ink_pixel=bool(bitmap[offset]&(0x80>>(x&7)))
            attr=attributes[(y//8)*32+x//8] if attributes is not None else 0x07
            # FLASH is displayed in its first phase. The supplied table has none.
            colour=(attr&7) if ink_pixel else ((attr>>3)&7)
            level=255 if attr&0x40 else 205
            pixel=bytes((level if colour&2 else 0,level if colour&4 else 0,level if colour&1 else 0))
            row.extend(pixel*scale)
        rows.extend([row]*scale)
    return b''.join(rows)


def main():
    symbols=symbol_map(ROOT/'build/game.map')
    image=(ROOT/'build/game.bin').read_bytes()
    tape_bytes=RELEASE_TAP.read_bytes()
    assert parse(tape_bytes)[5].payload==image, 'Build image differs from release TAP'
    def data(name):
        return image[symbols[name]-symbols['GameImage']:symbols[name+'End']-symbols['GameImage']]
    bitmap=data('CockpitBitmap');attributes=data('CockpitAttributes')
    assert len(bitmap)==32*64 and len(attributes)==32*8
    output=ROOT/'docs/images';output.mkdir(parents=True,exist_ok=True)
    for name,colours in [('cockpit-monochrome.png',None),('cockpit-attributes.png',attributes)]:
        path=output/name
        save_png(path,768,192,render(bitmap,colours))
        print(path)
    report=dict(tape_sha256=sha(tape_bytes),bitmap_sha256=sha(bitmap),
                attributes_sha256=sha(attributes),
                bitmap_address=symbols['CockpitBitmap'],attribute_address=symbols['CockpitAttributes'],
                native_width=256,native_height=64,scale=3,
                attribute_values={f'${value:02X}':count for value,count in sorted(Counter(attributes).items())},
                runtime_colouring_applied=False)
    report_dir=ROOT/'build/graphics-check';report_dir.mkdir(parents=True,exist_ok=True)
    (report_dir/'cockpit-render.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Stored attribute values:',report['attribute_values'])


if __name__=='__main__': main()
