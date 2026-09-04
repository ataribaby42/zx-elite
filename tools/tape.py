"""Strict Spectrum TAP framing. No input file is ever modified."""
from dataclasses import dataclass
from functools import reduce
from operator import xor
from pathlib import Path
import hashlib
import struct

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DEPS = ROOT / 'tools' / 'deps'
DEFAULT_TAPFILE = 'elite-128k.tap'


def release_tap(tapfile=DEFAULT_TAPFILE):
    """Resolve a plain TAP filename inside release; never accept a path."""
    if (not tapfile or tapfile != tapfile.strip() or
            any(ord(c) < 32 or c in '<>:"/\\|?*' for c in tapfile) or
            not tapfile.lower().endswith('.tap') or tapfile.startswith('.') or
            tapfile.split('.')[0].upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1,10)),
             *(f'LPT{i}' for i in range(1,10))}):
        raise ValueError('tapfile must be a plain filename ending in .tap, without a directory')
    return ROOT / 'release' / tapfile


RELEASE_TAP = release_tap()
REFERENCE = ROOT / 'assets' / 'Elite - 128k.tap'
REFERENCE_SHA256 = 'd9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6'

@dataclass
class Block:
    offset: int
    flag: int
    payload: bytes
    checksum: int

def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse(data):
    blocks = []
    offset = 0
    while offset < len(data):
        if offset + 2 > len(data):
            raise ValueError(f'Truncated TAP length at {offset}')
        size = struct.unpack_from('<H', data, offset)[0]
        end = offset + 2 + size
        if size < 2 or end > len(data):
            raise ValueError(f'Invalid TAP block size {size} at {offset}')
        raw = data[offset + 2:end]
        if reduce(xor, raw, 0):
            raise ValueError(f'TAP checksum mismatch at {offset}')
        blocks.append(Block(offset, raw[0], raw[1:-1], raw[-1]))
        offset = end
    return blocks

def reference():
    data = REFERENCE.read_bytes()
    if len(data) != 47918 or sha(data) != REFERENCE_SHA256:
        raise ValueError('Reference TAP is not the original supplied 128K-compatible release')
    blocks = parse(data)
    validate_pairs(blocks)
    if len(blocks) != 6:
        raise ValueError('Expected exactly six reference TAP blocks')
    return data, blocks

def validate_pairs(blocks):
    if len(blocks) % 2:
        raise ValueError('Expected header/data pairs')
    for index in range(0, len(blocks), 2):
        h, d = blocks[index:index + 2]
        if h.flag != 0 or len(h.payload) != 17 or d.flag != 255:
            raise ValueError(f'Invalid header/data pair at block {index}')
        if struct.unpack_from('<H', h.payload, 11)[0] != len(d.payload):
            raise ValueError(f'Header/data length mismatch at block {index}')

def frame(flag, payload):
    raw = bytes([flag]) + payload
    raw += bytes([reduce(xor, raw, 0)])
    if len(raw) > 65535:
        raise ValueError('TAP block exceeds 16-bit length')
    return struct.pack('<H', len(raw)) + raw

def header(kind, name, size, parameter1, parameter2):
    name = name.encode('ascii')
    if len(name) > 10 or not 0 <= kind <= 3:
        raise ValueError('Invalid Spectrum header')
    return bytes([kind]) + name.ljust(10, b' ') + struct.pack('<HHH', size, parameter1, parameter2)

def describe(blocks):
    result = []
    for i, b in enumerate(blocks):
        row = dict(index=i, offset=b.offset, flag=b.flag, payload_length=len(b.payload), checksum=b.checksum, sha256=sha(b.payload))
        if b.flag == 0 and len(b.payload) == 17:
            row.update(type=b.payload[0], name=b.payload[1:11].decode('ascii'),
                       length=struct.unpack_from('<H', b.payload, 11)[0],
                       parameter1=struct.unpack_from('<H', b.payload, 13)[0],
                       parameter2=struct.unpack_from('<H', b.payload, 15)[0])
        result.append(row)
    return result
