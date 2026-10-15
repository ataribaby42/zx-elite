"""Re-run the routine-level verification evidence of the disassembly (ZX Spectrum 48K).

Run from the project directory after a default build (make.bat, which runs
tools/build.py; the image must be byte-identical to the reference):

    python tools/check_routines.py                   all groups
    python tools/check_routines.py --list            groups, checks and routines
    python tools/check_routines.py --only maths      one group (repeatable)

What it checks: the claims recorded in tools/annotations (routine semantics,
formats and recorded outputs) for text and controls, numbers, division,
multiplication, square roots and vectors, the view buffer and screen
addressing, line drawing and clipping, circles and the patched screen
variants, the 3D projection pipeline, scanner/compass/proximity, keyboard and
joystick input, missions and pirates, economy/market/galaxy generation, the
commander rating and security number, stardust and the Torus jump, sound and
the dormant loader.  It consolidates the throwaway simulator tests written
while the source was annotated (their names survive only as the 'replaces'
metadata of each check); docs/ROUTINE-CHECKS.md lists every group, the
routines, case counts and the claims they support.

Machine model: the supplied ZX Spectrum 48K ROM plus build/game.bin at
GameImage in a private 64K memory list, executed by SkoolKit's Z80
simulator (never a 128K model).  Routines are called with controlled
registers and RAM fixtures and return to a sentinel address; no interrupts
are generated, so a HALT is an error unless a check documents that it treats
it as a completed frame wait.  Addresses come only from build/game.map;
numeric addresses are limited to fixed hardware (screen $4000, attributes
$5800, ports, ROM) and to harness RAM outside the game image.

Release safety: no byte of build/, release/ or the reference tape is written
except the report.  A few checks change their private RAM copy exactly as the
original tests did and say so in their docstrings: emulated RET stubs
(FillViewAttributes, PutCharacter/NewLine) and the game's own self-modifying
patches (RespawnDustFront masks, the L_AF01 market NOP).

Determinism: random samples use random.Random(<fixed seed>) and are capped at
a few thousand; the report build/routine-checks/verification.json contains no
timings, so two runs produce the same file.  The exit status is 1 when any
check fails (a failed run leaves no previous PASS report behind).
"""
import argparse
import json
import math
import random
import sys
import time
from collections import Counter

from tape import ROOT, ANALYSIS_DEPS, reference, sha
from build import symbol_map

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator                                     # noqa: E402
from skoolkit.simutils import (A, F, B, C, D, E, H, L, IXh, IXl, IYh, IYl,  # noqa: E402
                               SP, PC, xB, xC, xE, xH, xL)

# ---------------------------------------------------------------------------
# Fixed ZX Spectrum 48K machine constants (hardware, not relocatable game data)
ROM_SIZE = 0x4000
RAM_TOP = 0x10000
SCREEN = 0x4000                      # bitmap, 256 x 192 pixels
SCREEN_SIZE = 0x1800
SCREEN_THIRD = 0x0800
ATTRIBUTES = 0x5800
ATTRIBUTES_SIZE = 0x0300
ROW_BYTES = 32                       # bytes per pixel row (screen and view buffer)
VIEW_ROWS = 128                      # the 3D view buffer covers the top two thirds
VIEW_SIZE = VIEW_ROWS * ROW_BYTES
HALT = 0x76
RET = 0xC9
RETURN_SENTINEL = 0x0000             # return address pushed for every routine call
ROM_IY = 0x5C3A                      # ROM system-variable pointer (SkoolKit's default IY)
FRESH_REGISTERS = dict(a=0, f=0, bc=0, de=0, hl=0, ix=0, iy=ROM_IY)   # a new Simulator's registers

OPTION_SYMBOLS = ('SHIP_ADDER', 'LASER_SINGLE', 'FONT_48', 'FONT_128FIX', 'FONT_128FIX_ECM_S',
                  'SCANNER_PIXEL_FIX', 'STATION_RANDOM_LAUNCH_FIX', 'STATION_SLOT_FIX',
                  'FUEL_FIX', 'HYPERSPACE_DOCKING_FIX', 'AI_COURAGE_FIX',
                  'SCANNER_BLIP_FIX', 'STARDUST_FIX')
OUTPUT = ROOT / 'build/routine-checks/verification.json'

# Object instance fields (offsets inside a 39-byte slot; tools/annotations, docs/SHIPS.md)
INSTANCE_DISC = 0x1C          # +$1C..+$1F: disc offsets, flags and radius (DrawFlaggedObjectDiscs)
INSTANCE_ROLL = 0x1D          # roll counter; bit 7 = continuous roll
INSTANCE_STATE = 0x20         # explosion/state bits
INSTANCE_BLUEPRINT = 0x23     # blueprint pointer word
INSTANCE_FLAGS25 = 0x25
INSTANCE_FLAGS26 = 0x26
# Blueprint header fields (docs/SHIPS.md)
BLUEPRINT_VERTEX_COUNT, BLUEPRINT_FACE_COUNT = 3, 5
BLUEPRINT_VERTEX_TABLE, BLUEPRINT_FACE_TABLE = 12, 16
BLUEPRINT_NORMAL_SHIFT = 0x13


def screen_offset(x, y):
    """Offset of pixel (x, y) from the start of a Spectrum-layout bitmap."""
    return ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | (x >> 3)


def bitmap_pixels(memory, base, rows):
    """Set of lit (x, y) pixels of a Spectrum-layout bitmap with the given row count."""
    lit = set()
    for offset in range(rows * ROW_BYTES):
        value = memory[base + offset]
        if value:
            x0 = (offset & 31) * 8
            y = ((offset >> 8) & 7) | (((offset >> 5) & 7) << 3) | (((offset >> 11) & 3) << 6)
            for bit in range(8):
                if value & (0x80 >> bit):
                    lit.add((x0 + bit, y))
    return lit


def put24(memory, address, value):
    """Store a 24-bit sign-magnitude coordinate (low, mid, high | sign)."""
    magnitude = abs(value)
    assert magnitude < 1 << 23
    memory[address:address + 3] = [magnitude & 255, (magnitude >> 8) & 255,
                                   ((magnitude >> 16) & 0x7F) | (0x80 if value < 0 else 0)]


def get24(memory, address):
    magnitude = memory[address] | memory[address + 1] << 8 | (memory[address + 2] & 0x7F) << 16
    return -magnitude if memory[address + 2] & 0x80 else magnitude


def sm8(value):
    """Value of a sign-magnitude byte."""
    return -(value & 0x7F) if value & 0x80 else value & 0x7F


def sm16(value):
    """Value of a sign-magnitude word (bit 15 = sign)."""
    return -(value & 0x7FFF) if value & 0x8000 else value & 0x7FFF


def qmul(b, c):
    """MultiplyUnsigned model (quarter squares; tools/check_core_routines.py)."""
    return (((b + c) >> 1) ** 2 - (abs(b - c) >> 1) ** 2) & 0xFFFF


def qmul_high(b, c):
    """MultiplyUnsignedHigh model."""
    return ((((b + c) >> 1) ** 2 >> 8) - ((abs(b - c) >> 1) ** 2 >> 8)) & 0xFF


# ---------------------------------------------------------------------------
# Shared harness


class Context:
    """Symbols, the pristine 64K memory image and helpers shared by every check."""

    def __init__(self):
        self.symbols = symbol_map(ROOT / 'build/game.map')
        for name in OPTION_SYMBOLS:
            assert self.symbols.get(name, 0) == 0, ('run after a default build', name)
        self.tape, blocks = reference()       # validates framing, lengths, checksums, hash
        self.image = (ROOT / 'build/game.bin').read_bytes()
        assert self.image == bytes(blocks[5].payload), 'build/game.bin is not the default image'
        self.rom = (ROOT / 'assets/zxspectrum48k.rom').read_bytes()
        assert len(self.rom) == ROM_SIZE
        base = self.symbols['GameImage']
        memory = list(self.rom) + [0] * (RAM_TOP - ROM_SIZE)
        memory[base:base + len(self.image)] = self.image
        self.pristine = tuple(memory)
        # Harness RAM outside the game image (never part of a release):
        # the test stack sits 128 bytes below the runtime font copy, inside the
        # BASIC/scanner-backup area; checks that use that area run on upper_stack.
        self.test_stack = self['FontRuntime'] - 0x80
        self.upper_stack = RAM_TOP - 0x10
        assert self.upper_stack - 0x30 > self["InterruptStackTop"] >= self["GameImageEnd"]
        self.scratch = self.test_stack + 0x10               # free RAM for vectors/records
        assert self.scratch + 0x40 <= self['FontRuntime']

    def __getitem__(self, name):
        return self.symbols[name]

    def find(self, start, end, pattern, first=False):
        """Address of a byte pattern inside [start, end) of the pristine image: the unique
        match, or the first one when first=True.

        Used to enter or stop inside a routine at an instruction that has no label;
        the pattern is built from symbols, so it follows the code if it moves.
        """
        start, end = self.addr(start), self.addr(end)
        hits = [a for a in range(start, end - len(pattern) + 1)
                if list(self.pristine[a:a + len(pattern)]) == list(pattern)]
        assert hits and (first or len(hits) == 1), ('instruction pattern not unique', pattern, hits)
        return hits[0]

    def addr(self, target):
        return self.symbols[target] if isinstance(target, str) else target

    def machine(self):
        return Machine(self)



class ImageContext(Context):
    """Context for any image of the current build, used by the checks of optional fixes.

    It skips Context's default-build assertions; those checks compare the image with
    their own baselines instead."""

    def __init__(self, symbols, image):
        self.symbols = symbols
        self.image = bytes(image)
        self.rom = (ROOT / 'assets/zxspectrum48k.rom').read_bytes()
        assert len(self.rom) == ROM_SIZE
        base = symbols['GameImage']
        memory = list(self.rom) + [0] * (RAM_TOP - ROM_SIZE)
        memory[base:base + len(image)] = image
        self.pristine = tuple(memory)
        self.test_stack = symbols['FontRuntime'] - 0x80
        self.upper_stack = RAM_TOP - 0x10
        self.scratch = self.test_stack + 0x10

REGISTER_INDEX = dict(a=A, f=F, b=B, c=C, d=D, e=E, h=H, l=L)


class Machine:
    """ROM + default game image in a private 64K list, executed by SkoolKit's Simulator.

    No interrupts are generated.  call() pushes RETURN_SENTINEL and runs until the
    routine returns there (or reaches `stop`).  A HALT is an error unless halt=True,
    which treats it as a completed frame wait (the next instruction follows).
    `stubs` maps an address to a callback (or None); when PC reaches it the callback
    runs and a RET is emulated, so the routine at that address is not executed and
    no memory byte is changed.  `hooks` callbacks run before the instruction at
    their address executes.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.memory = list(ctx.pristine)
        self.sim = Simulator(self.memory)
        self.r = self.sim.registers

    def reset(self):
        self.memory[:] = self.ctx.pristine

    def __getitem__(self, name):
        return self.ctx[name]

    def set(self, **registers):
        r = self.r
        for name, value in registers.items():
            if name in REGISTER_INDEX:
                r[REGISTER_INDEX[name]] = value
            elif name in ('bc', 'de', 'hl'):
                r[REGISTER_INDEX[name[0]]], r[REGISTER_INDEX[name[1]]] = value >> 8, value & 255
            elif name == 'ix':
                r[IXh], r[IXl] = value >> 8, value & 255
            elif name == 'iy':
                r[IYh], r[IYl] = value >> 8, value & 255
            else:
                raise KeyError(name)

    def call(self, entry, stop=None, limit=2_000_000, stack=None, halt=False, stubs=None,
             hooks=None, record=False, rom_exit=False, balance=True, **registers):
        ctx, memory, r, opcodes = self.ctx, self.memory, self.r, self.sim.opcodes
        start = ctx.addr(entry)
        top = ctx.test_stack if stack is None else stack
        memory[top - 2] = RETURN_SENTINEL & 255
        memory[top - 1] = RETURN_SENTINEL >> 8
        r[SP], r[PC] = top - 2, start
        self.set(**registers)
        target = RETURN_SENTINEL if stop is None else ctx.addr(stop)
        special = {}
        for address, callback in (stubs or {}).items():
            special[ctx.addr(address)] = ('stub', callback)
        for address, callback in (hooks or {}).items():
            special[ctx.addr(address)] = ('hook', callback)
        visited = set() if record else None
        for _ in range(limit):
            pc = r[PC]
            if pc == target:
                if stop is None and balance:
                    assert r[SP] == top, ('stack imbalance', entry, hex(r[SP]))
                return visited
            if pc == RETURN_SENTINEL:
                raise AssertionError(('unexpected return before the stop address', entry, stop))
            if pc < ROM_SIZE and rom_exit:
                return visited
            if pc in special:
                kind, callback = special[pc]
                if callback:
                    callback(self)
                if kind == 'stub':
                    sp = r[SP]
                    r[PC] = memory[sp] | memory[sp + 1] << 8
                    r[SP] = (sp + 2) & 0xFFFF
                    continue
            if record:
                visited.add(pc)
            op = memory[pc]
            if op == HALT:
                assert halt, ('HALT reached without interrupts', entry, hex(pc))
                r[PC] = pc + 1
                continue
            opcodes[op]()
        raise AssertionError(('instruction limit', entry, hex(r[PC])))

    # register and memory accessors
    def reg(self, name):
        return self.r[REGISTER_INDEX[name]]

    def pair(self, name):
        hi, lo = name
        return self.r[REGISTER_INDEX[hi]] << 8 | self.r[REGISTER_INDEX[lo]]

    def ix(self):
        return self.r[IXh] << 8 | self.r[IXl]

    def iy(self):
        return self.r[IYh] << 8 | self.r[IYl]

    def carry(self):
        return self.r[F] & 1

    def word(self, address):
        address = self.ctx.addr(address)
        return self.memory[address] | self.memory[address + 1] << 8

    def poke_word(self, address, value):
        address = self.ctx.addr(address)
        self.memory[address], self.memory[address + 1] = value & 255, value >> 8

    def byte(self, address):
        return self.memory[self.ctx.addr(address)]

    def poke(self, address, *values):
        address = self.ctx.addr(address)
        self.memory[address:address + len(values)] = list(values)

    def text(self, address, length=9):
        out = ''
        for value in self.memory[self.ctx.addr(address):self.ctx.addr(address) + length]:
            if not value:
                break
            out += chr(value)
        return out

    def clear(self, start, size, value=0):
        start = self.ctx.addr(start)
        self.memory[start:start + size] = [value] * size


# ---------------------------------------------------------------------------
# Check registry

CHECKS = []
GROUPS = {}


def check(group, name, routines, replaces, claim):
    """Register a check: it receives the Context and returns its case count, or
    (count, details) where details is a small dict of recorded measurements."""
    def register(function):
        CHECKS.append(dict(group=group, name=name, routines=list(routines), replaces=replaces,
                           claim=claim, function=function))
        GROUPS.setdefault(group, []).append(name)
        return function
    return register


def expect(condition, *details):
    if not condition:
        raise AssertionError(details)


# ===========================================================================
# controls: flight-control copies, cockpit gauges, interrupt-time integration


@check('controls', 'read-flight-controls', ['ReadFlightControls'], 'R1-tests/test_controls_gauges.py',
       'PlayerRoll/Pitch/Speed copy the high bytes of RollControl/PitchControl/SpeedControl; '
       'RollIndicator/PitchIndicator = 21 +/- magnitude; SpeedGauge = speed*5+5.')
def check_read_flight_controls(ctx):
    m = ctx.machine()
    cases = [(0x85, 0x03, 0x0C), (0x00, 0x8A, 0x00), (0x13, 0x93, 0x1F)]
    cases += [(v, v ^ 0x80, v) for v in range(256)]
    for roll, pitch, speed in cases:
        m.poke(ctx['RollControl'] + 1, roll)
        m.poke(ctx['PitchControl'] + 1, pitch)
        m.poke(ctx['SpeedControl'] + 1, speed)
        m.call('ReadFlightControls')
        indicator = [(0x15 + v if v < 0x80 else 0x15 - (v & 0x7F)) & 255 for v in (roll, pitch)]
        expect((m.byte('PlayerRoll'), m.byte('PlayerPitch'), m.byte('PlayerSpeed')) == (roll, pitch, speed),
               roll, pitch, speed)
        expect([m.byte('RollIndicator'), m.byte('PitchIndicator')] == indicator, roll, pitch)
        expect(m.byte('SpeedGauge') == (speed * 5 + 5) & 255, speed)
    return len(cases)


GAUGES = ('ForwardShield', 'AftShield', 'FuelGauge', 'CabinTemperature', 'LaserTemperature',
          'AltitudeGauge', 'SpeedGauge', 'EnergyBank1', 'EnergyBank2', 'EnergyBank3', 'EnergyBank4',
          'RollIndicator', 'PitchIndicator')


@check('controls', 'draw-gauges', ['DrawGauges', 'DrawBarGauge', 'DrawIndicatorGauge'],
       'R1-tests/test_controls_gauges.py',
       'Changed gauges are redrawn at GaugeScreenAddresses: 11 bars of value/4 pixels and two '
       '2-pixel indicator markers at pixels value-2..value-1, five identical rows, right border.')
def check_draw_gauges(ctx):
    m = ctx.machine()
    values = (0xA0, 0x50, 0x24, 0x04, 0x00, 0x9F, 0x41, 0x08, 0x10, 0x7C, 0xA0, 0x15, 0x0A)
    table = [m.word(ctx['GaugeScreenAddresses'] + 2 * i) for i in range(len(GAUGES))]
    for name, value in zip(GAUGES, values):
        m.poke(name, value)
        m.poke(ctx[name] - 1, value ^ 0xFF)          # drawn copy differs: force a redraw
    m.clear(ctx['ScreenCockpitBitmap'], SCREEN_THIRD)
    m.call('DrawGauges')
    for index, (name, value) in enumerate(zip(GAUGES, values)):
        rows = [''.join(f'{m.memory[table[index] + 256 * row + i]:08b}' for i in range(5))
                for row in range(5)]
        expect(m.byte(ctx[name] - 1) == value, name, 'drawn copy not updated')
        expect(len(set(rows)) == 1, name, rows)
        bits = rows[0]
        if index < 11:
            n = value >> 2
            expected = '1' * n + '0' * (39 - n) + '1' if n < 40 else '1' * 40
        else:
            expected = '0' * (value - 2) + '11' + '0' * (39 - value) + '1'
        expect(bits == expected, name, value, bits)
    return len(GAUGES)


@check('controls', 'update-flight-controls', ['UpdateFlightControls'], 'R11-tests/check_input.py',
       'RollControl/PitchControl/SpeedControl frame sequences: N/M +$FF per frame from $80FF/$00FF up '
       'to $8FF0/$0FF0, damping -$3C, recentring, pitch step $66, speed +/-$A0 with max $1FE0; '
       'KeyFlagsFlight is consumed on screens 0..3 and kept on screen 4.')
def check_update_flight_controls(ctx):
    m = ctx.machine()
    flags = ctx['KeyFlagsFlight']
    roll, pitch, speed = ctx['RollControl'], ctx['PitchControl'], ctx['SpeedControl']
    m.poke('CurrentScreenId', 0)
    frames = 0

    def frame(keys, options=0x8C):
        nonlocal frames
        m.poke(flags, keys)
        m.poke('ControlOptions', options)
        m.call('UpdateFlightControls')
        frames += 1
        return m.word(roll), m.word(pitch), m.word(speed)

    def zero():
        m.clear(roll, 6)

    zero()
    held = [frame(0x01)[0] for _ in range(20)]
    expect(held[:3] == [0x80FF, 0x81FE, 0x82FD] and held[-1] == 0x8FF0, 'N held', held)
    expect([frame(0)[0] for _ in range(3)] == [0x8FB4, 0x8F78, 0x8F3C], 'damping')
    expect(frame(0x02)[0] == 0, 'M once with recentring')
    zero()
    held = [frame(0x02)[0] for _ in range(20)]
    expect(held[:3] == [0x00FF, 0x01FE, 0x02FD] and held[-1] == 0x0FF0, 'M held', held)
    expect(frame(0x01, 0x88)[0] == 0x0EF1, 'N once without recentring')
    zero()
    expect([frame(0x04)[1] for _ in range(3)] == [0x8066, 0x80CC, 0x8132], 'X held')
    zero()
    expect([frame(0x08)[1] for _ in range(3)] == [0x0066, 0x00CC, 0x0132], 'S held')
    zero()
    held = [frame(0x10)[2] for _ in range(60)]
    expect(held[:3] == [0x00A0, 0x0140, 0x01E0] and max(held) == 0x1FE0, 'SPACE held')
    expect([frame(0x20)[2] for _ in range(3)] == [0x1F40, 0x1EA0, 0x1E00], 'SYMBOL SHIFT held')
    expect(m.byte(flags) == 0, 'KeyFlagsFlight consumed')
    m.poke('CurrentScreenId', 4)
    m.poke(flags, 0x01)
    m.call('UpdateFlightControls')
    expect(m.byte(flags) == 0x01, 'KeyFlagsFlight kept on screen 4')
    return frames + 1


# ===========================================================================
# screen: view buffer, screen addressing, pixel and crosshair plotting


@check('screen', 'clear-view-buffer', ['ClearViewBuffer'], 'R1-tests/test_view_buffer.py',
       'The 4 KB view buffer is cleared with the view frame: rows 0 and 127 = $00,$FF x30,$00, '
       'other rows $00,$80,0..0,$01,$00; SP is saved in ViewClearSavedSP.')
def check_clear_view_buffer(ctx):
    m = ctx.machine()
    m.clear('ViewBitmapBuffer', VIEW_SIZE, 0x5A)
    m.call('ClearViewBuffer')
    expect(m.word('ViewClearSavedSP') == ctx.test_stack - 2, 'saved SP')
    base = ctx['ViewBitmapBuffer']
    rows = [bytes(m.memory[base + ROW_BYTES * i:base + ROW_BYTES * (i + 1)]) for i in range(VIEW_ROWS)]
    top = bytes([0] + [0xFF] * 30 + [0])
    middle = bytes([0, 0x80] + [0] * 28 + [1, 0])
    expect(rows[0] == top and rows[-1] == top, 'frame lines')
    expect(all(row == middle for row in rows[1:-1]), 'side pixels')
    return VIEW_SIZE


@check('screen', 'blit-view-bitmap', ['BlitViewBitmap'], 'R1-tests/test_view_buffer.py',
       'Every view-buffer byte lands at the same offset in the top two screen thirds.')
def check_blit_view_bitmap(ctx):
    m = ctx.machine()
    rng = random.Random(1)
    base = ctx['ViewBitmapBuffer']
    m.memory[base:base + VIEW_SIZE] = [rng.randrange(256) for _ in range(VIEW_SIZE)]
    m.clear(SCREEN, VIEW_SIZE)
    m.call('BlitViewBitmap')
    expect(m.memory[SCREEN:SCREEN + VIEW_SIZE] == m.memory[base:base + VIEW_SIZE], 'copy')
    return VIEW_SIZE


@check('screen', 'restore-cockpit-test', ['RestoreCockpitIfFullScreen'], 'R1-tests/test_view_buffer.py',
       'RestoreCockpitIfFullScreen returns at once when screen byte $4000 is not $FF.')
def check_restore_cockpit_test(ctx):
    m = ctx.machine()
    m.poke(SCREEN, 0)
    visited = m.call('RestoreCockpitIfFullScreen', record=True)
    expect(ctx['ClearScreenAndDrawCockpit'] not in visited and len(visited) <= 4, sorted(visited))
    return 1


@check('screen', 'pixel-screen-address', ['GetPixelScreenAddress', 'AdjustScreenAddressCellRow'],
       'R8-tests/test_math.py',
       'GetPixelScreenAddress returns the bitmap byte of pixel (A, C); AdjustScreenAddressCellRow '
       'corrects HL after INC H leaves a character cell.')
def check_pixel_screen_address(ctx):
    m = ctx.machine()
    cases = 0
    for y in range(192):
        for x in range(0, 256, 3):
            m.call('GetPixelScreenAddress', a=x, c=y)
            expect(m.pair('hl') == SCREEN + screen_offset(x, y), x, y)
            cases += 1
    for y in range(7, 191, 8):
        hl = SCREEN + screen_offset(0, y) + 0x100
        m.call('AdjustScreenAddressCellRow', hl=hl)
        expect(m.pair('hl') == SCREEN + screen_offset(0, y + 1), y)
        cases += 1
    return cases


@check('screen', 'toggle-view-pixel', ['ToggleViewPixel'], 'R9-tests/test_plot.py',
       'ToggleViewPixel XORs exactly one bit, pixel (C, B), into the view buffer; B and C preserved.')
def check_toggle_view_pixel(ctx):
    m = ctx.machine()
    base = ctx['ViewBitmapBuffer']
    cases = 0
    for y in range(VIEW_ROWS):
        for x in range(0, 256, 3):
            before = m.memory[base:base + VIEW_SIZE]
            m.call('ToggleViewPixel', b=y, c=x, f=0)
            offset = screen_offset(x, y)
            expect(m.memory[base + offset] == before[offset] ^ (0x80 >> (x & 7)), x, y)
            m.memory[base + offset] = before[offset]
            expect(m.memory[base:base + VIEW_SIZE] == before, 'other bytes changed', x, y)
            m.memory[base + offset] ^= 0x80 >> (x & 7)
            expect((m.reg('b'), m.reg('c')) == (y, x), x, y)
            cases += 1
    return cases


@check('screen', 'xor-crosshair', ['DrawXorCrosshair'], 'R8-tests/test_cross.py',
       'DrawXorCrosshair XORs a "+" of CrosshairSize around (ShapeCentreX, ShapeCentreY); the arms '
       'are clipped to the screen and CrosshairTopLimit..CrosshairBottomLimit, the centre is left '
       'clear and a second call erases the cross.')
def check_xor_crosshair(ctx):
    m = ctx.machine()

    def cross(x, y, size, top=0, bottom=0xA7):
        m.reset()
        m.clear(SCREEN, SCREEN_SIZE)
        m.poke('ShapeCentreX', x, y)
        m.poke('CrosshairSize', size, top, bottom)
        m.call('DrawXorCrosshair')
        return bitmap_pixels(m.memory, SCREEN, 192)

    def arms(lit, x, y):
        row = sorted(p[0] for p in lit if p[1] == y)
        column = sorted(p[1] for p in lit if p[0] == x)
        other = [p for p in lit if p[0] != x and p[1] != y]
        return (len(lit), row[0], row[-1], len(row), column[0], column[-1], len(column), len(other))

    golden = {(100, 80, 16, 0, 0xA7): (30, 92, 107, 15, 72, 87, 15, 0),
              (0x61, 0x60, 0x18, 0, 0xA7): (46, 85, 108, 23, 84, 107, 23, 0),
              (4, 10, 16, 0, 0x98): (25, 1, 11, 10, 2, 17, 15, 0),
              (250, 160, 16, 0, 0x98): (51, 242, 254, 12, 152, 191, 39, 0)}
    columns = {(100, 145, 16, 0, 0x98): (137, 151, 14), (100, 3, 16, 0, 0x98): (0, 10, 10),
               (100, 40, 16, 0x24, 0x98): (36, 47, 11), (100, 0x98, 16, 0, 0x98): (144, 152, 9)}
    for args, expected in golden.items():
        lit = cross(*args)
        expect(arms(lit, args[0], args[1]) == expected, args, arms(lit, args[0], args[1]))
        expect((args[0], args[1]) not in lit, 'centre pixel left clear', args)
    for args, expected in columns.items():
        result = arms(cross(*args), args[0], args[1])
        expect(result[4:7] == expected and result[1:3] == (92, 107), args, result)
    cross(100, 80, 16)
    m.call('DrawXorCrosshair')
    expect(not any(m.memory[SCREEN:SCREEN + SCREEN_SIZE]), 'second call erases')
    return len(golden) + len(columns) + 1


# ===========================================================================
# text: justified printer, token/message controls, screen text helpers


@check('text', 'justified-word-wrap', ['StartJustifiedText', 'PrintCharacter', 'EndJustifiedText'],
       'R1-tests/test_wrap.py',
       'The justified printer lays a description out as 30-column lines padded at word gaps; '
       'StartJustifiedText also writes $20 to CurrentScreenId (31-byte fill).  PutCharacter and '
       'NewLine are stubbed to capture the output.')
def check_justified_word_wrap(ctx):
    """Stubs (as in the original annotation test): PutCharacter and NewLine are not executed; an
    emulated RET follows after recording the character or line break.  No byte is changed."""
    m = ctx.machine()
    out = []
    stubs = {'PutCharacter': lambda mm: out.append(chr(mm.reg('a'))),
             'NewLine': lambda mm: out.append('\n')}
    m.poke('CurrentScreenId', 0x07)
    m.call('StartJustifiedText', stubs=stubs, a=0)
    expect(m.byte('CurrentScreenId') == 0x20, 'CurrentScreenId overwritten by the fill')
    text = 'THE PLANET LAVE IS MOST FAMOUS FOR ITS VAST RAIN FORESTS AND THE LAVIAN TREE GRUB.'
    for character in text:
        m.call('PrintCharacter', stubs=stubs, a=ord(character))
    m.call('EndJustifiedText', stubs=stubs, a=0)
    lines = ''.join(out).split('\n')
    expected = ['The Planet Lave Is Most Famous', 'for Its Vast Rain Forests  And',
                'The Lavian Tree Grub.         ', '']
    expect(lines == expected, lines)
    expect(' '.join(' '.join(lines).split()).upper() == text, 'word order')
    return len(text)


# ===========================================================================
# pipeline: perspective projection of bodies and objects


def body_projection_model(x, y, z, view):
    """Claim model of ProjectBodyPosition (A, |h| byte, |v| byte, flags, radius) or None."""
    depth = {0: z, 1: -z, 2: -x, 3: x}[view]          # front +z, rear -z, left -x, right +x
    horizontal = x if view < 2 else z
    if depth <= 0:
        return None
    flags = 0
    if (horizontal >= 0) != (view in (1, 3)):         # rear and right views mirror the side
        flags |= 1
    if y >= 0:
        flags |= 2
    offsets = []
    for value, bit in ((horizontal, 4), (y, 8)):
        magnitude = abs(value)
        if magnitude >= 2 * depth:
            return None
        if magnitude <= depth:
            offsets.append(min(255, magnitude * 256 // depth))
            flags |= bit
        else:
            offsets.append(magnitude * 256 // depth - 256)
    depth_word = depth >> 8
    radius = 255 if depth_word <= 0xA0 else 0xA000 // depth_word
    return 1, offsets[0], offsets[1], flags, radius


@check('pipeline', 'project-body-position', ['ProjectBodyPosition', 'ProjectCoordinate'],
       'R1-tests/test_projection.py',
       'Sun/planet projection for the four views: A=1 in front, offsets = 256*|h|/depth and '
       '256*|v|/depth (bits 2/3 set below 256, 255 for a ratio of exactly 1, offset-256 up to '
       '511), bit 0 right, bit 1 above, radius = $A000/depth word (255 up to $A0); A=0 behind '
       'the viewer or for an offset of 512 or more.')
def check_project_body_position(ctx):
    m = ctx.machine()
    sweep = [(r, 0x8000, 0x100000, 0) for r in (0x100000, 0x110000, 0x140000, 0x180000, 0x1C0000,
                                                 0x1F0000, 0x200000, 0x210000, 0x300000)]
    cases = [(0, 0, 0x100000, 0), (0x80000, 0, 0x100000, 0), (-0x80000, 0x40000, 0x100000, 0),
             (0x40000, -0x20000, 0x200000, 0), (0, 0, -0x100000, 0), (0, 0, 0x40000, 0),
             (0, 0, 0x3F0000, 0), (0, 0, 0xA000, 0), (0, 0, 0xA100, 0), (0x200000, 0, 0x100000, 0),
             (0, 0, 0x7FFFFF, 0), (0x100, 0, 0x100, 0), (0x100000, 0x100000, 0x100000, 0)]
    for view in (1, 2, 3):
        cases += [(x, y, z, view) for x, y, z in ((0, 0, -0x100000), (0, 0, 0x100000),
                                                  (-0x100000, 0x20000, 0), (0x100000, 0x20000, 0))]
    golden = {  # recorded outputs (A, |x|, |y|, flags, radius) for the visible cases
        0: (1, 0, 0, 0x0F, 10), 1: (1, 128, 0, 0x0F, 10), 2: (1, 128, 64, 0x0E, 10),
        3: (1, 32, 16, 0x0D, 5), 5: (1, 0, 0, 0x0F, 40), 6: (1, 0, 0, 0x0F, 2),
        7: (1, 0, 0, 0x0F, 255), 8: (1, 0, 0, 0x0F, 254), 10: (1, 0, 0, 0x0F, 1),
        11: (1, 255, 0, 0x0F, 255), 12: (1, 255, 255, 0x0F, 10), 13: (1, 0, 0, 0x0E, 10),
        19: (1, 0, 32, 0x0F, 10), 24: (1, 0, 32, 0x0E, 10)}
    sweep_golden = [(1, 255, 8), (1, 16, 8), (1, 64, 8), (1, 128, 8), (1, 192, 8), (1, 240, 8)]
    sweep_flags = [0x0F, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B]
    out = ctx['CircleOffsetY']
    for index, (x, y, z, view) in enumerate(cases + sweep):
        for axis, value in enumerate((x, y, z)):
            put24(m.memory, ctx['ProjectionX'] + 3 * axis, value)
        m.poke('CurrentScreenId', view)
        m.clear(out, 4, 0xEE)
        m.call('ProjectBodyPosition')
        got = (m.reg('a'), m.byte('CircleOffsetX'), m.byte('CircleOffsetY'), m.byte('CircleFlags'),
               m.byte('CircleRadius'))
        model = body_projection_model(x, y, z, view)
        if model is None:
            expect(got[0] == 0, 'should be invisible', x, y, z, view, got)
            continue
        expect(got == model, 'model', x, y, z, view, got, model)
        if index in golden:
            expect(got == golden[index], 'recorded', index, got)
        if index >= len(cases):
            k = index - len(cases)
            expect(got[:3] == sweep_golden[k] and got[3] == sweep_flags[k], 'ratio sweep', k, got)
    return len(cases) + len(sweep)


# ===========================================================================
# maths: division, multiplication, square roots, vectors, sign-magnitude helpers


def restoring_fraction(a, b):
    """Model of the $FE-sentinel restoring division used by DivideToFractionC."""
    c = 0xFE
    while True:
        carry = a >> 7
        a = (a << 1) & 0xFF
        if carry or a >= b:
            a = (a - b) & 0xFF
            out = c >> 7
            c = ((c << 1) | 1) & 0xFF
        else:
            out = c >> 7
            c = (c << 1) & 0xFF
        if not out:
            return c


def divide_ratio_model(dividend, divisor):
    """Bit-level model of DivideRatioByte (entry carry clear), from its annotation:
    shift both 24-bit values left (at most 8 steps) until the divisor normalises; a
    dividend overflow restores the dividend and forces the divisor's top bit (SCF);
    then 255 if D >= H, else the 8-bit quotient (D:E)/H."""
    d, e, c = dividend >> 16, (dividend >> 8) & 255, dividend & 255
    hl, a = divisor >> 8, divisor & 255
    carry = 0
    for _ in range(8):
        a, carry = ((a << 1) | carry) & 255, a >> 7           # RLA
        hl = hl * 2 + carry                                    # ADC HL,HL
        carry, hl = hl >> 16, hl & 0xFFFF
        if carry:                                              # divisor normalised first
            hl = 0x8000 | (hl >> 1)
            break
        value = ((d << 16) | (e << 8) | c) << 1                # RL C / RL E / RL D
        carry = value >> 24
        d, e, c = (value >> 16) & 255, (value >> 8) & 255, value & 255
        if carry:                                              # dividend overflow path
            out = d & 1
            d, e = 0x80 | (d >> 1), (out << 7) | (e >> 1)
            hl = 0x8000 | (hl >> 1)
            return ('overflow', 255 if d >= hl >> 8 else ((d << 8) | e) // (hl >> 8))
    h = hl >> 8
    return ('normal', 255 if d >= h else ((d << 8) | e) // h)


@check('maths', 'fraction-dividers', ['DivideFractionABToC', 'DivideFractionAB', 'DivideFractionAEB'],
       'R1-tests/test_divide.py',
       'C = A*256/B and D = A*256/B (E cleared) for every A < B; D = (A*256+E)/B for A < B.')
def check_fraction_dividers(ctx):
    m = ctx.machine()
    cases = 0
    for b in range(1, 256):
        for a in range(b):
            m.call('DivideFractionABToC', a=a, b=b)
            expect(m.reg('c') == a * 256 // b, 'ABToC', a, b)
            m.call('DivideFractionAB', a=a, b=b, e=0x55)
            expect(m.reg('d') == a * 256 // b and m.reg('e') == 0, 'AB', a, b)
            cases += 2
    rng = random.Random(2)
    for _ in range(5000):
        b = rng.randrange(1, 256)
        a, e = rng.randrange(0, b), rng.randrange(256)
        m.call('DivideFractionAEB', a=a, b=b, e=e)
        expect(m.reg('d') == (a * 256 + e) // b, 'AEB', a, e, b)
        cases += 1
    return cases


@check('maths', 'dust-arithmetic', ['MultiplyByLowBits', 'DivideToFractionD', 'DivideWordToFixed'],
       'R4-tests/explore_math.py, R4-tests/explore_div.py',
       'HL = A*(C mod 2^B) for B = 4, 5, 8 and all A, C; D = A*256/B for all A < B; '
       'C:D = (A:L)*256/B for A:L < $2000 and quotients below $4000, D kept when exact.')
def check_dust_arithmetic(ctx):
    m = ctx.machine()
    cases = 0
    for bits in (4, 5, 8):
        mask = (1 << bits) - 1
        for a in range(256):
            for c in range(256):
                m.call('MultiplyByLowBits', a=a, b=bits, c=c)
                expect(m.pair('hl') == a * (c & mask), bits, a, c)
                cases += 1
    for b in range(1, 256):
        for a in range(b):
            m.call('DivideToFractionD', a=a, b=b)
            expect(m.reg('d') == a * 256 // b, a, b)
            cases += 1
    for d_in in (0x00, 0x5A):              # 716 = 4*179: no remainder, D keeps its value
        m.call('DivideWordToFixed', a=0x02, l=0xCC, b=179, d=d_in)
        expect(m.reg('c') << 8 | m.reg('d') == 0x400 | d_in, '716/179', d_in)
    rng = random.Random(2)
    for _ in range(5000):
        b = rng.randrange(1, 256)
        de = rng.randrange(b, 0x2000)
        d_in = rng.randrange(256)
        m.call('DivideWordToFixed', a=de >> 8, l=de & 0xFF, b=b, d=d_in)
        exact = de * 256 // b if de % b else (de // b) << 8 | d_in
        if exact < 0x4000:
            expect(m.reg('c') << 8 | m.reg('d') == exact, de, b, d_in)
        cases += 1
    return cases + 2


@check('maths', 'line-helpers', ['DivideToFractionC', 'ScaleByFraction', 'DivideByteFraction'],
       'R10-tests/test_drawline.py, R9-tests/test_arith.py',
       'DivideToFractionC: C = A*256/B for A < B, $FF for A = B, D/E kept; ScaleByFraction: '
       'C = (MultiplyUnsigned(A, C) + $80) >> 8, DE/HL kept; DivideByteFraction with C = $FE: '
       'C = (A:E)/B for A < B.')
def check_line_helpers(ctx):
    m = ctx.machine()
    rng = random.Random(10)
    for _ in range(3000):
        b = rng.randrange(1, 256)
        a = rng.randrange(0, b + 1)
        m.call('DivideToFractionC', a=a, b=b, d=0x12, e=0x34)
        expect(m.reg('c') == restoring_fraction(a, b), 'model', a, b)
        expect(m.reg('c') == (a * 256 // b if a < b else 0xFF), 'value', a, b)
        expect((m.reg('d'), m.reg('e')) == (0x12, 0x34), 'DE', a, b)
    for _ in range(3000):
        a, c = rng.randrange(256), rng.randrange(256)
        m.call('ScaleByFraction', a=a, c=c, d=0x12, e=0x34, h=0x56, l=0x78)
        product = a * c - (min(a, c) if (a + c) & 1 else 0)
        expect(m.reg('c') == ((product + 0x80) >> 8) & 0xFF, a, c)
        expect((m.reg('d'), m.reg('e'), m.reg('h'), m.reg('l')) == (0x12, 0x34, 0x56, 0x78), a, c)
    rng = random.Random(1984)
    for _ in range(3000):
        b = rng.randint(1, 255)
        a, e = rng.randint(0, b - 1), rng.randint(0, 255)
        m.call('DivideByteFraction', a=a, b=b, c=0xFE, e=e)
        expect(m.reg('c') == ((a << 8) | e) // b, a, e, b)
    return 9000


@check('maths', 'word-division', ['DivideWordFraction'], 'R9-tests/test_arith.py',
       'BC = (HL*65536 + A*256)/DE, HL = remainder, exact for HL < DE; overflowing inputs '
       '(HL >= DE) give wrong quotients.')
def check_word_division(ctx):
    m = ctx.machine()
    rng = random.Random(1984)
    for i in range(4000):
        de = rng.randint(1, 0xFF) if i % 4 == 0 else rng.randint(1, 0xFFFF)
        hl, a = rng.randint(0, de - 1), rng.randint(0, 255)
        m.call('DivideWordFraction', a=a, hl=hl, de=de, f=0)
        expect((m.pair('bc'), m.pair('hl')) == divmod((hl << 16) | (a << 8), de), hl, a, de)
    wrong = 0
    for _ in range(1000):
        de = rng.randint(1, 0xFFFF)
        hl, a = rng.randint(de, 0xFFFF), rng.randint(0, 255)
        m.call('DivideWordFraction', a=a, hl=hl, de=de, f=0)
        wrong += m.pair('bc') != (((hl << 16) | (a << 8)) // de) & 0xFFFF
    expect(wrong == 1000, 'overflow cases', wrong)
    return 5000


@check('maths', 'ratio-division', ['DivideRatioByte'], 'R9-tests/test_arith.py, R9-tests/probe592.py',
       'C = 256*(DE:C)/(HL:A) by the documented shift/normalise algorithm (bit-exact model): a '
       'normalised divisor gives 255 for ratios >= 1 and the exact quotient or 1..3 more for '
       'divisors >= $8000; the dividend-overflow path forces the divisor top bit and can return '
       'values below 255 for ratios >= 1.')
def check_ratio_division(ctx):
    m = ctx.machine()
    rng = random.Random(1984)
    paths = Counter()
    for i in range(6000):
        de, hl = rng.randint(0, 0xFFFF), rng.randint(1, 0xFFFF)
        c = rng.randint(0, 255) if i % 2 else 0
        a = rng.randint(0, 255) if i % 2 else 0
        if i % 3 == 0:
            de = rng.randint(0, hl)
        m.call('DivideRatioByte', a=a, c=c, de=de, hl=hl, f=0)
        got = m.reg('c')
        dividend, divisor = (de << 8) | c, (hl << 8) | a
        path, model = divide_ratio_model(dividend, divisor)
        expect(got == model, 'model', hex(dividend), hex(divisor), got, model)
        exact = 256 * dividend // divisor
        if path == 'normal' and exact >= 256:
            expect(got == 255, 'saturation', hex(dividend), hex(divisor))
        elif path == 'normal' and divisor >= 0x8000:
            expect(0 <= got - exact <= 3, 'accuracy', hex(dividend), hex(divisor), got, exact)
        paths[(path, got == 255)] += 1
    expect(paths[('overflow', False)] > 0, 'overflow path below 255 not exercised')
    return 6000


@check('maths', 'multiply-helpers', ['UnusedMultiplyWordHigh', 'MultiplyNormalByCoordinate',
                                     'ComputeCrossProductTerm'], 'R9-tests/test_arith.py',
       'UnusedMultiplyWordHigh = high word of the four MultiplyUnsigned partial products (IX '
       'restored); MultiplyNormalByCoordinate = 2|n|*p_hi + high(2|n|*p_lo) with sign n XOR p; '
       'ComputeCrossProductTerm = (D*E - B*C) from 2|a|*2|b| products, halved, saturating.')
def check_multiply_helpers(ctx):
    m = ctx.machine()
    rng = random.Random(1984)
    for _ in range(3000):
        x, y = rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF)
        a, c, d, e = x >> 8, x & 255, y >> 8, y & 255
        m.call('UnusedMultiplyWordHigh', a=a, c=c, d=d, e=e, ix=0)
        product = qmul(e, c) + ((qmul(d, c) + qmul(a, e)) << 8) + (qmul(a, d) << 16)
        expect(m.pair('hl') == (product >> 16) & 0xFFFF and m.ix() == 0, x, y)
    for _ in range(3000):
        a, c, e = rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)
        m.call('MultiplyNormalByCoordinate', a=a, c=c, e=e)
        doubled = (a << 1) & 255
        magnitude = qmul(doubled, e & 0x7F) + qmul_high(doubled, c)
        expect(m.pair('hl') == ((a ^ e) & 0x80) << 8 | (magnitude & 0x7FFF), a, c, e)
    for _ in range(3000):
        b, c, d, e = (rng.randint(0, 255) for _ in range(4))
        m.call('ComputeCrossProductTerm', b=b, c=c, d=d, e=e)
        got = m.pair('hl')
        bc = qmul((b << 1) & 255, (c << 1) & 255)
        de = qmul((d << 1) & 255, (e << 1) & 255)
        difference = (-de if (d ^ e) & 0x80 else de) - (-bc if (b ^ c) & 0x80 else bc)
        expect((got & 0x7FFF) == min(abs(difference), 0xFFFF) >> 1, b, c, d, e)
        if difference:
            expect((got & 0x8000) == (0x8000 if difference < 0 else 0), 'sign', b, c, d, e)
    return 9000


@check('maths', 'sign-magnitude-sums', ['HalveSumSignMagnitude', 'HalveDifferenceSignMagnitude',
                                        'TranslateVertexAxis'], 'R9-tests/test_arith.py',
       'HL = (HL +/- DE)/2 for sign-magnitude words with the sign of the larger magnitude (HL on a '
       'tie); TranslateVertexAxis = HL:B + 2*DE (+ fraction carry) within 1.')
def check_sign_magnitude_sums(ctx):
    m = ctx.machine()
    rng = random.Random(1984)
    for i in range(4000):
        hl, de = rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF)
        entry = 'HalveSumSignMagnitude' if i % 2 else 'HalveDifferenceSignMagnitude'
        m.call(entry, hl=hl, de=de)
        operand = de if i % 2 else de ^ 0x8000
        magnitude = abs(sm16(hl) + sm16(operand)) // 2
        if (hl ^ operand) & 0x8000 and (operand & 0x7FFF) > (hl & 0x7FFF):
            sign = operand & 0x8000
        else:
            sign = hl & 0x8000
        expect(m.pair('hl') == sign | magnitude, entry, hl, de)
    for _ in range(4000):
        hl, b = rng.randint(0, 0x7FFF), rng.choice((0, 0x80))
        e, d, fraction = rng.randint(0, 255), rng.choice((0, 0x80)), rng.randint(0, 255)
        m.call('TranslateVertexAxis', b=b, d=d, e=e, hl=hl, a=0, f=1 if fraction & 0x80 else 0)
        add = 2 * e + (1 if fraction & 0x80 else 0)
        value = (-hl if b else hl) + (-add if d else add)
        expect(abs(abs(value) - m.pair('hl')) <= 1, hl, b, e, d, fraction)
        if value:
            expect(m.reg('a') & 0x80 == (0x80 if value < 0 else 0), 'sign', hl, b, e, d)
    return 8000


# ===========================================================================
# numbers: small byte/word helpers


@check('numbers', 'double-sign-magnitude', ['DoubleSignMagnitude'], 'R6-tests/economy.py',
       'C = (A AND $80) OR ((A << 1) AND $7E) OR carry-in; A bit 0 := A bit 6; carry out = old bit 0 '
       '(all 256 values, both carries).')
def check_double_sign_magnitude(ctx):
    m = ctx.machine()
    for a in range(256):
        for carry in (0, 1):
            m.reset()
            m.call('DoubleSignMagnitude', **dict(FRESH_REGISTERS, a=a, f=carry))
            expect((m.reg('c'), m.reg('a'), m.carry()) ==
                   ((a & 0x80) | ((a << 1) & 0x7E) | carry, (a & 0xFE) | ((a >> 6) & 1), a & 1), a, carry)
    return 512


@check('numbers', 'fuel-and-seed-helpers', ['SetFuelLevel', 'RotateSeedWordLeft'], 'R8-tests/test_math.py',
       'SetFuelLevel: FuelLevel = min(A, 70), FuelGauge = 2*fuel + (2*fuel >> 3) for all A; '
       'RotateSeedWordLeft rotates both bytes of the word at HL left by one bit and returns HL + 2.')
def check_fuel_and_seed_helpers(ctx):
    m = ctx.machine()
    for a in range(256):
        m.reset()
        m.call('SetFuelLevel', a=a)
        fuel = min(a, 70)
        expect(m.byte('FuelLevel') == fuel and m.byte('FuelGauge') == (2 * fuel + (2 * fuel >> 3)) & 255, a)
    area = ctx.scratch
    for word in (0x0001, 0x8080, 0x5A3C, 0xFFFE):
        m.poke_word(area, word)
        m.call('RotateSeedWordLeft', hl=area)
        rotated = [((b << 1) | (b >> 7)) & 255 for b in (word & 255, word >> 8)]
        expect([m.byte(area), m.byte(area + 1)] == rotated and m.pair('hl') == area + 2, hex(word))
    return 256 + 4


@check('maths', 'half-chord-root', ['ComputeHalfChord', 'ClearBytes'], 'R2-tests/test_halfchord.py',
       'ComputeHalfChord: A = isqrt(D*D - A*A - CF) with BC, DE, HL preserved (11,051 cases); '
       'ClearBytes zeroes B bytes from HL and returns HL after them.')
def check_half_chord_root(ctx):
    m = ctx.machine()
    cases = 0
    for radius in range(0, 256, 3):
        for a in range(0, radius + 1, 2):
            for carry in (0, 1):
                if radius * radius - a * a - carry < 0:
                    continue
                m.call('ComputeHalfChord', a=a, d=radius, f=carry, b=0x12, c=0x34, e=0x56, h=0x78, l=0x9A)
                expect(m.reg('a') == math.isqrt(radius * radius - a * a - carry), radius, a, carry)
                expect((m.reg('b'), m.reg('c'), m.reg('d'), m.reg('e'), m.reg('h'), m.reg('l')) ==
                       (0x12, 0x34, radius, 0x56, 0x78, 0x9A), 'registers', radius, a)
                cases += 1
    expect(cases == 11051, cases)
    area = ctx.scratch
    m.clear(area, 16, 0xAA)
    m.call('ClearBytes', b=5, hl=area + 2)
    expect(m.memory[area:area + 16] == [0xAA] * 2 + [0] * 5 + [0xAA] * 9 and m.pair('hl') == area + 7)
    return cases + 1


@check('maths', 'vector-magnitude', ['GetVectorMagnitude', 'GetVectorMagnitudeHigh'],
       'R3-tests/test_magnitude.py',
       'GetVectorMagnitude is within 1% of sqrt(x^2+y^2+z^2) when a 16-bit coordinate is >= 256 '
       'and returns 0 for |v| >= 65536; GetVectorMagnitudeHigh uses the mid/high bytes '
       '(($400000,$300000,$50000) -> $5028).  Vectors whose three coordinates are all below 256 '
       'are excluded: the routine does not return their magnitude.')
def check_vector_magnitude(ctx):
    m = ctx.machine()
    vector = ctx['SunPosition']

    def setv(x, y, z):
        for axis, value in enumerate((x, y, z)):
            put24(m.memory, vector + 3 * axis, value)

    rng = random.Random(2)
    worst, measured, overflow = 0.0, 0, 0
    for _ in range(3000):
        x, y, z = (rng.randrange(-0xFFFF, 0x10000) >> rng.randrange(0, 15) for _ in range(3))
        if x == y == z == 0:
            continue                                  # documented: never terminates
        setv(x, y, z)
        m.call('GetVectorMagnitude', ix=vector, stack=ctx.upper_stack)
        exact = math.sqrt(x * x + y * y + z * z)
        if exact >= 65536:
            expect(m.pair('hl') == 0, 'overflow', x, y, z)
            overflow += 1
        elif max(abs(x), abs(y), abs(z)) >= 256:
            worst = max(worst, abs(m.pair('hl') - exact) / exact)
            measured += 1
    expect(worst < 0.01, worst)
    for v in ((0xFFFF, 0xFFFF, 0), (0xC000, 0x8000, 0x8000)):
        setv(*v)
        m.call('GetVectorMagnitude', ix=vector, stack=ctx.upper_stack)
        expect(m.pair('hl') == 0, v)
    for v, expected in (((0x123456, 0x10000, 0), 0x1227), ((0x400000, 0x300000, 0x50000), 0x5028)):
        setv(*v)
        m.call('GetVectorMagnitudeHigh', ix=vector + 1, stack=ctx.upper_stack)
        expect(m.pair('hl') == expected, v, hex(m.pair('hl')))
    return measured + overflow + 4


@check('maths', 'square-root-and-normalise', ['SquareRootHL', 'NormaliseVector'],
       'R8-tests/test_math.py, R11-tests/check_input.py',
       'SquareRootHL ~ 256*sqrt(HL) within 3.5% for HL >= 16; NormaliseVector scales three '
       'sign-magnitude words to length $8000 and returns DE ~ the original length (within 3.5%, '
       'signs kept); recorded steering-vector results (300,400,0) -> DE 632 etc.')
def check_square_root_and_normalise(ctx):
    m = ctx.machine()
    samples = [1, 2, 4, 9, 16, 100, 255, 256, 1000, 0x0FFF, 0x1000, 0x4000, 0x8000, 0xC000, 0xFFFF]
    samples += random.Random(1).sample(range(1, 65536), 300)
    worst = 0.0
    for n in samples:
        m.call('SquareRootHL', hl=n)
        if n >= 16:
            exact = math.sqrt(n) * 256
            worst = max(worst, abs(m.pair('hl') - exact) / exact)
    expect(worst < 0.035, 'SquareRootHL', worst)
    rng = random.Random(2)
    base = ctx.scratch
    worst_unit = worst_length = 0.0
    cases = len(samples)
    for _ in range(60):
        v = [rng.randint(-0x3000, 0x3000) for _ in range(3)]
        length = math.sqrt(sum(c * c for c in v))
        if max(map(abs, v)) > 0.85 * length or max(map(abs, v)) < 0x100:
            continue
        m.reset()
        for i, c in enumerate(v):
            m.poke_word(base + 2 * i, abs(c) | (0x8000 if c < 0 else 0))
        m.call('NormaliseVector', ix=base)
        out = [sm16(m.word(base + 2 * i)) for i in range(3)]
        expect(all((c < 0) == (o < 0) or o == 0 for c, o in zip(v, out)), 'signs', v, out)
        worst_unit = max(worst_unit, abs(math.sqrt(sum(o * o for o in out)) - 0x8000) / 0x8000)
        worst_length = max(worst_length, abs(m.pair('de') - length) / length)
        cases += 1
    expect(worst_unit < 0.035 and worst_length < 0.035, worst_unit, worst_length)
    vector = ctx['SteeringVectorX']
    recorded = {(300, 400, 0): (632, [0x3CC2, 0x5103, 0]),
                (0x3000, 0x4000, 0): (20713, [0x4BEF, 0x653F, 0]),
                (0x8000 | 1200, 500, 0x8000): (1270, [0xF8F1, 0x3264, 0x8000])}
    for words, (length, components) in recorded.items():
        m.reset()
        for i, word in enumerate(words):
            m.poke_word(vector + 2 * i, word)
        m.call('NormaliseVector', ix=vector, iy=vector)
        expect(m.pair('de') == length and [m.word(vector + 2 * i) for i in range(3)] == components,
               words, m.pair('de'))
        cases += 1
    return cases


@check('maths', 'rotation-helpers', ['AddScaledSignMagnitude', 'AddScaledCoordinate',
                                     'RenormaliseOrientationVector', 'OrthogonaliseYVector',
                                     'ComputeNegatedDotProduct'],
       'R8-tests/test_de5d.py, R8-tests/test_df46.py, R8-tests/test_renorm.py, '
       'R9-tests/test_ortho.py, R11-tests/check_input.py',
       'AddScaledSignMagnitude = D + s*|B|*|C|/128 saturated (within 1.25); AddScaledCoordinate '
       'adds src*|C|/256 with sign(C) XOR sign(src) (within 1% of |src|, IX/IY kept); '
       'RenormaliseOrientationVector pulls the length towards 127 (IX += 6); '
       'OrthogonaliseYVector leaves |cos(Z,Y)| <= 0.029; ComputeNegatedDotProduct examples.')
def check_rotation_helpers(ctx):
    m = ctx.machine()
    cases = 0
    rng = random.Random(5)
    worst = 0.0
    for _ in range(400):
        a, b, c, d = (rng.randrange(256) for _ in range(4))
        m.call('AddScaledSignMagnitude', a=a, b=b, c=c, d=d)
        sign = -1 if (a ^ b) & 0x80 else 1
        want = max(-127, min(127, sm8(d) + sign * (b & 0x7F) * (c & 0x7F) / 128))
        worst = max(worst, abs(sm8(m.reg('a')) - want))
        cases += 1
    expect(worst <= 1.25, 'AddScaledSignMagnitude', worst)
    base = ctx.scratch
    rng = random.Random(3)
    for _ in range(300):
        src, dst = rng.randint(-0x7FFF, 0x7FFF), rng.randint(-0x7FFF, 0x7FFF)
        c = rng.randrange(256)
        m.reset()
        put24(m.memory, base + 3, src)
        put24(m.memory, base + 6, dst)
        m.call('AddScaledCoordinate', ix=base, iy=0x1234, de=3, hl=6, c=c)
        want = dst + (-1 if c & 0x80 else 1) * src * (c & 0x7F) / 256
        expect(abs(get24(m.memory, base + 6) - want) <= abs(src) / 100 + 1, src, dst, c)
        expect(get24(m.memory, base + 3) == src and m.ix() == base and m.iy() == 0x1234, src, c)
        cases += 1
    recorded = [(0x1000, 0, 0x10, 0x100), (0x1000, 0, 0x90, -0x100), (-0x1000, 0, 0x10, -0x100),
                (0x1000, 0x500, 0x90, 0x400), (0x100, 0, 0x7F, 0x7F), (0x7FFF, 0, 1, 0x80),
                (0x12345, 0, 0x40, 0x47AE)]
    for src, dst, c, result in recorded:
        m.reset()
        put24(m.memory, base + 3, src)
        put24(m.memory, base + 6, dst)
        m.call('AddScaledCoordinate', ix=base, iy=0x1234, de=3, hl=6, c=c)
        expect(get24(m.memory, base + 6) == result, hex(src), hex(c))
        cases += 1
    renorm = {(0x7F, 0, 0): ([127.0] * 4, (0x7F, 0, 0)),
              (0x70, 0, 0): ([124.0, 127.0, 127.0, 127.0], (0x7F, 0, 0)),
              (0x60, 0, 0): ([117.0, 126.0, 127.0, 127.0], (0x7F, 0, 0)),
              (0x5A, 0x5A, 0): ([127.3] * 4, (0x5A, 0x5A, 0)),
              (0x50, 0x50, 0): ([124.5, 127.3, 127.3, 127.3], (0x5A, 0x5A, 0)),
              (0x40, 0xC0, 0x40): ([124.7, 128.2, 128.2, 128.2], (0x4A, 0xCA, 0x4A)),
              (0x60, 0x40, 0xA0): ([127.2] * 4, (0x66, 0x44, 0xA2))}
    for vector, (lengths, final) in renorm.items():
        m.reset()
        for i, high in enumerate(vector):
            m.poke(base + 2 * i, 0, high)
        got = []
        for _ in range(4):
            m.call('RenormaliseOrientationVector', ix=base)
            expect(m.ix() == base + 6, 'IX += 6')
            got.append(round(math.sqrt(sum(sm8(m.byte(base + 2 * i + 1)) ** 2 for i in range(3))), 1))
        expect(got == lengths and tuple(m.byte(base + 2 * i + 1) for i in range(3)) == final, vector, got)
        cases += 1
    m.reset()
    instance = ctx['InitialRuntimeState'] + ctx['InstanceSize']
    rng = random.Random(3)

    def smb(v):
        return min(127, int(round(abs(v)))) | (0x80 if v < 0 else 0)

    worst_after = 0.0
    for _ in range(3000):
        a = [rng.uniform(-1, 1) for _ in range(3)]
        n = math.sqrt(sum(x * x for x in a))
        a = [127 * x / n for x in a]
        b = [rng.uniform(-1, 1) for _ in range(3)]
        dot = sum(x * y for x, y in zip(a, b)) / (127 * 127)
        b = [x - dot * y for x, y in zip(b, a)]
        n = math.sqrt(sum(x * x for x in b))
        b = [127 * x / n for x in b]
        tilt = rng.uniform(-0.5, 0.5)
        b = [x * math.sqrt(1 - tilt * tilt) + tilt * y for x, y in zip(b, a)]
        for i in range(3):
            m.poke(instance + ctx['InstanceAxisZ'] + 1 + 2 * i, smb(a[i]))
            m.poke(instance + ctx['InstanceAxisY'] + 1 + 2 * i, smb(b[i]))
        z = [sm8(m.byte(instance + ctx['InstanceAxisZ'] + 1 + 2 * i)) for i in range(3)]
        m.call('OrthogonaliseYVector', ix=instance, a=0, f=0, bc=0, de=0, hl=0, iy=0)
        y = [sm8(m.byte(instance + ctx['InstanceAxisY'] + 1 + 2 * i)) for i in range(3)]
        expect([sm8(m.byte(instance + ctx['InstanceAxisZ'] + 1 + 2 * i)) for i in range(3)] == z, 'Z kept')
        cosine = sum(p * q for p, q in zip(z, y)) / (
            math.sqrt(sum(p * p for p in z)) * max(1e-9, math.sqrt(sum(q * q for q in y))))
        worst_after = max(worst_after, abs(cosine))
        cases += 1
    expect(worst_after <= 0.029, 'OrthogonaliseYVector', worst_after)
    dot_cases = {((0x60, 0, 0), (0x60, 0, 0)): 0xC8, ((0xE0, 0, 0), (0x60, 0, 0)): 0x48,
                 ((0x60, 0x60, 0), (0x60, 0xE0, 0)): 0x00, ((0x40, 0x40, 0x40), (0x40, 0x40, 0x40)): 0xE0,
                 ((0x7F, 0, 0), (0x7F, 0, 0)): 0xFE}
    va, vb = base, base + 0x10
    for (a, b), result in dot_cases.items():
        for i in range(3):
            m.poke(va + 1 + 2 * i, a[i])
            m.poke(vb + 1 + 2 * i, b[i])
        m.call('ComputeNegatedDotProduct', ix=va, iy=vb)
        expect(m.reg('a') == result, a, b, hex(m.reg('a')))
        cases += 1
    return cases


@check('maths', 'sun-relative-to-station', ['MakeSunRelativeToStation'], 'R1-tests/test_rebase.py',
       'Each sun word becomes (sun - station) in sign-magnitude form with bit 0 lost; the '
       'fraction bytes are kept (3000 cases).')
def check_sun_relative_to_station(ctx):
    m = ctx.machine()
    rng = random.Random(3)
    sun, station = ctx['SunPosition'], ctx['InitialRuntimeState']
    for _ in range(3000):
        suns = [rng.randrange(65536) for _ in range(3)]
        stations = [rng.randrange(65536) for _ in range(3)]
        lows = [rng.randrange(256) for _ in range(3)]
        for i in range(3):
            m.poke(sun + 3 * i, lows[i])
            m.poke_word(sun + 3 * i + 1, suns[i])
            m.poke_word(station + 3 * i + 1, stations[i])
        m.call('MakeSunRelativeToStation')
        for i in range(3):
            word = m.word(sun + 3 * i + 1)
            difference = sm16(suns[i]) - sm16(stations[i])
            expect(m.byte(sun + 3 * i) == lows[i], 'fraction kept')
            if abs(difference) > 0x7FFF:
                continue
            magnitude = abs(difference) & 0x7FFE
            expect((word & 0x7FFF) == magnitude and (not magnitude or (word >> 15) == (difference < 0)),
                   suns[i], stations[i], hex(word))
    return 3000


# ===========================================================================
# lines: DrawLine, its clipping and set-up helpers


def line_signed(mx, my, quadrant):
    """Endpoint offsets from the view centre: quadrant bit 0 = below, bit 1 = left."""
    return (-mx if quadrant & 2 else mx), (my if quadrant & 1 else -my)


def dda_model(x1, y1, x2, y2):
    """Pixels of an unclipped DrawLine: start at endpoint 2, endpoint 1 itself omitted."""
    dx, dy = abs(x2 - x1), abs(y2 - y1)
    xmajor = (dx >> 1) >= (dy >> 1)
    major, minor = (dx, dy) if xmajor else (dy, dx)
    slope = restoring_fraction(minor, major)
    sx, sy = (1 if x1 > x2 else -1), (1 if y1 > y2 else -1)
    x, y, acc, out = x2, y2, 0x80, []
    for _ in range(max(major + 1, 2) - 1):
        out.append((x, y))
        acc += slope
        carry, acc = acc > 255, acc & 255
        if xmajor:
            y += sy if carry else 0
            x += sx
        else:
            x += sx if carry else 0
            y += sy
    return out


def segment_distance(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = 0 if vx == vy == 0 else max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(ax + t * vx - px, ay + t * vy - py)


def visible_length(ax, ay, bx, by, xmin=0, xmax=254, ymin=0, ymax=126):
    """Liang-Barsky: major-axis length of the visible part of a segment (0 if none)."""
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for p, q in ((-dx, ax - xmin), (dx, xmax - ax), (-dy, ay - ymin), (dy, ymax - ay)):
        if p == 0:
            if q < 0:
                return 0
        elif p < 0:
            t0 = max(t0, q / p)
        else:
            t1 = min(t1, q / p)
    return 0 if t0 > t1 else (t1 - t0) * max(abs(dx), abs(dy))


class LineMachine:
    """DrawLine runner that also proves no byte outside the buffer/workspace is written."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.m = ctx.machine()
        buffer = ctx['ViewBitmapBuffer']
        allowed = [(buffer, buffer + VIEW_SIZE), (ctx.test_stack - 64, ctx.test_stack),
                   (ctx['LineClipEndpointRegions'], ctx['DrawLine'])]
        allowed += [(ctx[n], ctx[n] + 1) for n in (
            'L_F209', 'L_F20E', 'L_F224', 'L_F228', 'L_F22D', 'L_F237', 'L_F258', 'L_F25D',
            'L_F275', 'L_F27A', 'L_F284', 'L_F29D')]          # self-modified plot operands
        edges, start = [], 0
        for low, high in sorted(allowed):
            if low > start:
                edges.append((start, low))
            start = max(start, high)
        edges.append((start, RAM_TOP))
        self.checked = edges

    def clear(self):
        self.m.reset()
        self.m.clear('ViewBitmapBuffer', VIEW_SIZE)       # the image holds the font there

    def draw(self, h, l, d, e, c, reset=True):
        m = self.m
        if reset:
            self.clear()
        before = bytes(m.memory)
        m.call('DrawLine', h=h, l=l, d=d, e=e, c=c)
        after = bytes(m.memory)
        for low, high in self.checked:
            expect(before[low:high] == after[low:high], 'write outside the buffer', h, l, d, e, c)
        return bitmap_pixels(m.memory, self.ctx['ViewBitmapBuffer'], VIEW_ROWS)


@check('lines', 'line-delta-and-start', ['ComputeLineDelta', 'SetLinePlotStart'],
       'R10-tests/test_drawline.py',
       'ComputeLineDelta returns |dx|, |dy|, the slope and the documented direction/major/'
       'overflow flags (DE kept); SetLinePlotStart gives the buffer address, pixel mask and rows '
       'to the cell edge of the DE endpoint in the alternate registers.')
def check_line_delta_and_start(ctx):
    m = ctx.machine()
    rng = random.Random(11)
    for _ in range(3000):
        h, l, d, e = (rng.randrange(256) for _ in range(4))
        q = rng.randrange(16)
        m.call('ComputeLineDelta', b=q, h=h, l=l, d=d, e=e)
        x1, y1 = line_signed(h, l, q & 3)
        x2, y2 = line_signed(d, e, q >> 2)
        adx, ady = abs(x2 - x1), abs(y2 - y1)
        flags = m.reg('b')
        expect(m.reg('h') == adx & 0xFF and m.reg('l') == ady & 0xFF and (m.reg('d'), m.reg('e')) == (d, e),
               'deltas', q, h, l, d, e)
        expect(flags & 1 == (q >> 2) & 1 and (flags >> 1) & 1 == (q >> 3) & 1
               and (flags >> 5) & 1 == (q >> 3) & 1, 'quadrant bits', q, hex(flags))
        expect((flags >> 7) & 1 == (adx > 255) and (flags >> 6) & 1 == (ady > 255), 'overflow bits')
        if y2 != y1:
            expect((flags >> 2) & 1 == (y2 > y1), 'y direction', q, h, l, d, e)
        if x2 != x1:
            expect((flags >> 3) & 1 == (x2 < x1), 'x direction', q, h, l, d, e)
        xmajor = (adx >> 1) >= (ady >> 1)
        expect((flags >> 4) & 1 == xmajor, 'major axis')
        if xmajor:
            slope = restoring_fraction(ady >> 1, adx >> 1) if adx > 255 else restoring_fraction(ady & 255, adx & 255)
        else:
            slope = restoring_fraction(adx >> 1, ady >> 1) if ady > 255 else restoring_fraction(adx & 255, ady & 255)
        expect(m.reg('c') == slope, 'slope', q, h, l, d, e)
    buffer = ctx['ViewBitmapBuffer']
    for _ in range(3000):
        d, e, flags = rng.randrange(128), rng.randrange(64), rng.randrange(256)
        m.call('SetLinePlotStart', b=flags, c=0x55, d=d, e=e)
        x = 127 - d if flags & 2 else 127 + d
        y = 63 + e if flags & 1 else 63 - e
        r = m.r
        expect((r[xH] << 8 | r[xL]) == buffer + screen_offset(x, y) and r[xC] == 0x80 >> (x & 7),
               'address/mask', d, e, flags)
        expect(r[xB] == ((y & 7) + 1 if flags & 4 else 8 - (y & 7)) and r[xE] == 0x55, 'rows/slope')
    return 6000


@check('lines', 'draw-line', ['DrawLine'], 'R10-tests/test_drawline.py',
       'Lines with both ends inside equal a DDA model (start at the DE end, HL end pixel '
       'omitted); clipped lines stay within 3 pixels of the ideal segment, visible lines are '
       'drawn, nothing is written outside the buffer, stack and workspace (deltas above 255 '
       'may clip wrongly and are only counted); H AND E or L AND D = $FF draws nothing.')
def check_draw_line(ctx):
    lines = LineMachine(ctx)
    for h, l, d, e in ((0xFF, 10, 10, 0xFF), (10, 0xFF, 0xFF, 10)):
        expect(not lines.draw(h, l, d, e, 0), 'sentinel draws nothing', h, l, d, e)
    rng = random.Random(10)
    inside = 0
    while inside < 1500:
        h, l, d, e = rng.randrange(128), rng.randrange(64), rng.randrange(128), rng.randrange(64)
        q = rng.randrange(16)
        if (h & e) == 0xFF or (l & d) == 0xFF:
            continue
        x1, y1 = line_signed(h, l, q & 3)
        x2, y2 = line_signed(d, e, q >> 2)
        expect(lines.draw(h, l, d, e, q) == set(dda_model(127 + x1, 63 + y1, 127 + x2, 63 + y2)),
               'DDA model', h, l, d, e, q)
        inside += 1
    clipped = drawn = anomalies = 0
    for i in range(1500):
        h, l, d, e = (rng.randrange(256) for _ in range(4))
        if i % 3 == 0:
            d, e = rng.randrange(128), rng.randrange(64)
        q = rng.randrange(16)
        if (h & e) == 0xFF or (l & d) == 0xFF:
            continue
        lit = lines.draw(h, l, d, e, q)
        x1, y1 = line_signed(h, l, q & 3)
        x2, y2 = line_signed(d, e, q >> 2)
        ax, ay, bx, by = 127 + x1, 63 + y1, 127 + x2, 63 + y2
        visible = visible_length(ax, ay, bx, by)
        far = max((segment_distance(px, py, ax, ay, bx, by) for px, py in lit), default=0)
        clipped += 1
        if (abs(bx - ax) > 255 or abs(by - ay) > 255) and (
                far >= 3.0 or (visible >= 4 and len(lit) < visible * 0.75 - 2)):
            anomalies += 1
            continue
        expect(far < 3.0, 'far pixel', h, l, d, e, q, far)
        if visible >= 4:
            expect(lit and len(lit) >= visible * 0.75 - 2, 'visible line', h, l, d, e, q)
            drawn += 1
    expect(anomalies <= 2 and drawn > 900, anomalies, drawn)
    return 2 + inside + clipped


@check('lines', 'sights-and-laser-lines', ['DrawLine'], 'R10-tests/test_drawline.py',
       'The four sight lines and the laser beam lines produce the recorded pixels.')
def check_sights_and_laser_lines(ctx):
    lines = LineMachine(ctx)
    lines.clear()
    lit = set()
    for h, l, d, e, c in ((8, 0, 16, 0, 0x0A), (8, 0, 16, 0, 0x00), (0, 16, 0, 8, 0x00), (0, 16, 0, 8, 0x05)):
        lit = lines.draw(h, l, d, e, c, reset=False)
    expected = ({(x, 63) for x in range(111, 119)} | {(x, 63) for x in range(136, 144)} |
                {(127, y) for y in range(48, 56)} | {(127, y) for y in range(71, 79)})
    expect(lit == expected, sorted(lit ^ expected))
    recorded = {(0x543F, 3): ((45, 125), 84), (0x403F, 3): ((64, 125), 64),
                (0x543F, 1): ((210, 125), 84), (0x403F, 1): ((190, 125), 64)}
    for (hl, c), (start, count) in recorded.items():
        lit = lines.draw(hl >> 8, hl & 255, 0, 0, c)
        expect(max(lit, key=lambda p: p[1]) == start and min(lit, key=lambda p: p[1]) == (127, 63)
               and len(lit) == count, hex(hl), c)
    return 4 + len(recorded)


# ===========================================================================
# circles: outline/filled circles in the view buffer and the patched screen variants


def set_circle(m, dy, dx, flags, radius):
    m.poke('CircleOffsetY', dy)
    m.poke('CircleOffsetX', dx)
    m.poke('CircleFlags', flags)
    m.poke('CircleRadius', radius)


@check('circles', 'circle-renderer', ['DrawCircle', 'DrawCircleOutline', 'DrawFilledCircle',
                                      'DrawCircleOutlineAnySize'], 'R2-tests/test_circles.py',
       'Circles are drawn into the view buffer only, centred at 128 +/- dx, 64 -/+ dy by CircleFlags '
       'bits 0/1 (CircleCentreX/Y), radius +/- 1; outline mode leaves the interior empty '
       '(CircleOutlineFlag 1), fill mode fills it (flag 0); radius < 9 draws nothing except via '
       'DrawCircleOutlineAnySize; filled discs stay within x 8..247 and fill the full width.')
def check_circle_renderer(ctx):
    m = ctx.machine()
    buffer = ctx['ViewBitmapBuffer']

    def draw(entry, dy, dx, flags, radius):
        m.reset()
        m.clear(buffer, VIEW_SIZE)
        m.clear(SCREEN, SCREEN_SIZE)
        set_circle(m, dy, dx, flags, radius)
        m.call(entry)
        expect(not any(m.memory[SCREEN:SCREEN + SCREEN_SIZE]), 'drew to the screen', entry)
        return bitmap_pixels(m.memory, buffer, VIEW_ROWS)

    cases = 0
    for entry, outline in (('DrawCircleOutline', True), ('DrawFilledCircle', False)):
        for dy, dx, flags in ((10, 20, 0x0F), (10, 20, 0x0C), (0, 0, 0x0F), (30, 50, 0x0D), (30, 50, 0x0E)):
            lit = draw(entry, dy, dx, flags, 25)
            xs, ys = [p[0] for p in lit], [p[1] for p in lit]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            ex = 128 + dx if flags & 1 else 128 - dx
            ey = 64 - dy if flags & 2 else 64 + dy
            expect(abs(cx - ex) <= 1 and abs(cy - ey) <= 1, 'centre', entry, dy, dx, flags)
            expect(abs((max(xs) - min(xs)) / 2 - 25) <= 1 and abs((max(ys) - min(ys)) / 2 - 25) <= 1, 'radius')
            expect((m.byte('CircleCentreY'), m.byte('CircleCentreX')) == (ey, ex), 'centre bytes')
            interior = sum(1 for x, y in lit if math.hypot(x - ex, y - ey) < 22)
            if outline:
                expect(interior == 0 and m.byte('CircleOutlineFlag') == 1, 'outline', dy, dx, flags)
            else:
                expect(interior > 1500 and m.byte('CircleOutlineFlag') == 0, 'filled', dy, dx, flags)
            cases += 1
    for entry in ('DrawCircleOutline', 'DrawFilledCircle'):
        expect(not draw(entry, 0, 0, 0x0F, 8), 'radius 8', entry)
    expect(draw('DrawCircleOutlineAnySize', 0, 0, 0x0F, 8), 'radius 8 any size')
    cases += 3
    for dy, dx, flags, radius in ((40, 60, 0x0F, 60), (0, 0, 0x0F, 200), (80, 0, 0x0F, 100), (20, 150, 0x0B, 60)):
        for entry in ('DrawFilledCircle', 'DrawCircleOutline'):
            lit = draw(entry, dy, dx, flags, radius)
            if entry == 'DrawFilledCircle':
                expect(all(8 <= x <= 247 for x, _ in lit), 'fill clipped to x 8..247', dy, dx, radius)
            cases += 1
    expect(len(draw('DrawFilledCircle', 0, 0, 0x0F, 200)) == 240 * VIEW_ROWS, 'full-width fill')
    return cases + 1


@check('circles', 'outline-arcs', ['DrawCircleLeftArc', 'DrawCirclePairedArcs', 'DrawCircleRightArc',
                                   'L_8640', 'L_866E'], 'R3-tests/test_circle.py',
       'Outline circles of radius 9..200, centred in, near or beyond the view edges: every pixel '
       'lies between r-1.6 and r+2.1 from the centre, in view rows 0..127; the recorded arc routines '
       '(paired, left, right, row-address helpers) are used; with CircleFlags bits 2/3 clear an '
       'outside centre draws nothing.')
def check_outline_arcs(ctx):
    m = ctx.machine()
    buffer = ctx['ViewBitmapBuffer']
    names = ('L_8640', 'L_866E', 'DrawCircleLeftArc', 'DrawCirclePairedArcs', 'DrawCircleRightArc',
             'L_8608', 'L_8616', 'L_861F', 'L_8629', 'L_8635')
    P, LT, RT = ('DrawCirclePairedArcs', 'L_861F', 'L_8629'), ('DrawCircleLeftArc', 'L_8616', 'L_861F'), \
        ('DrawCircleRightArc', 'L_8629')
    UP = ('L_8640', 'DrawCircleLeftArc', 'L_8635')
    golden = {  # (cx, cy, r): (pixels or None, routines) with CircleFlags bits 2 and 3 set
        (128, 64, 30): (168, P), (128, 64, 60): (336, None), (100, 50, 20): (112, None),
        (200, 30, 50): (174, None), (20, 100, 40): (96, None), (128, 64, 9): (48, None),
        (250, 120, 30): (47, LT), (5, 5, 100): (144, RT), (128, 64, 120): (255, None),
        (5, 64, 30): (None, RT), (250, 64, 30): (None, LT), (128, 5, 30): (None, P),
        (128, 120, 30): (None, P), (10, 64, 40): (None, RT),
        (128, -10, 40): (91, P), (128, 140, 40): (89, P), (-10, 64, 40): (77, RT),
        (270, 64, 40): (67, LT), (-10, -10, 60): (57, ('DrawCircleRightArc', 'L_8608', 'L_8629')),
        (128, -100, 150): (223, P), (128, 200, 150): (244, UP),
        (128, 64, 200): (0, ('L_8640', 'L_866E', 'DrawCircleLeftArc', 'L_8635')),
        (-60, 64, 100): (128, RT), (300, 64, 100): (128, LT), (128, -60, 100): (161, P),
        (60, 180, 130): (184, ('DrawCircleRightArc', 'L_8608', 'L_8629')), (128, 190, 200): (109, UP)}

    def circle(cx, cy, radius, flags):
        m.reset()
        m.clear(buffer, VIEW_SIZE)
        dx, dy = cx - 128, cy - 64
        flags |= (1 if dx >= 0 else 0) | (2 if dy < 0 else 0)
        set_circle(m, abs(dy), abs(dx), flags, radius)
        visited = m.call('DrawCircleOutlineAnySize', stack=ctx.upper_stack, record=True)
        return bitmap_pixels(m.memory, buffer, VIEW_ROWS), visited

    for (cx, cy, radius), (count, routines) in golden.items():
        lit, visited = circle(cx, cy, radius, 0x0C)
        if count is not None:
            expect(len(lit) == count, 'pixel count', cx, cy, radius, len(lit))
        if routines is not None:
            used = tuple(n for n in names if ctx[n] in visited)
            expect(used == routines, 'arc routines', cx, cy, radius, used)
        for x, y in lit:
            distance = math.hypot(x - cx, y - cy)
            expect(radius - 1.6 <= distance <= radius + 2.1 and 0 <= y < VIEW_ROWS,
                   'pixel off the circle', cx, cy, radius, x, y)
    outside = ((128, -10, 40), (128, 140, 40), (-10, 64, 40), (270, 64, 40), (-10, -10, 60))
    for flags in (0x04, 0x08, 0x00):
        for cx, cy, radius in outside:
            lit, visited = circle(cx, cy, radius, flags)
            expect(not lit and not any(ctx[n] in visited for n in names), 'flags', flags, cx, cy)
    return len(golden) + 3 * len(outside)


@check('circles', 'screen-circle-patching', ['DrawScreenCircle', 'DrawFlaggedObjectDiscs',
                                             'PatchDiscRendererTarget'], 'R2-tests/test_patching.py',
       'CirclePatchTargets lists 32 bytes that hold ViewCirclePatchValues in the image; '
       'DrawScreenCircle draws chart circles on the 256x192 screen (buffer untouched) and restores '
       'every patched byte; DrawFlaggedObjectDiscs draws discs on screen rows 0..127, clears +$20 '
       'bit 4 and restores the buffer values ($CF/$BF at L_85D7/L_85E2).  FillViewAttributes '
       '(HALT-based colour flash) is stubbed with an emulated RET, as in the original test.')
def check_screen_circle_patching(ctx):
    """Stub (as the original annotation test did, which wrote RET over it in its RAM copy):
    FillViewAttributes is skipped with an emulated RET because its colour flash HALTs."""
    m = ctx.machine()
    image = ctx.pristine
    count = image[ctx['CirclePatchCount']]
    targets = [image[ctx['CirclePatchTargets'] + 2 * i] | image[ctx['CirclePatchTargets'] + 2 * i + 1] << 8
               for i in range(count)]
    view_values = [image[ctx['ViewCirclePatchValues'] + i] for i in range(count)]
    expect(count == 32 and ctx['CirclePatchTargets'] + 2 * count == ctx['DrawFlaggedObjectDiscs'], count)
    expect(all(image[t] == v for t, v in zip(targets, view_values)), 'view values in the image')
    buffer = ctx['ViewBitmapBuffer']
    for x, y, radius in ((100, 50, 20), (128, 96, 40), (200, 150, 30), (30, 20, 25)):
        m.reset()
        m.clear(SCREEN, SCREEN_SIZE)
        m.clear(buffer, VIEW_SIZE)
        m.poke('ShapeCentreX', x, y, radius)
        m.call('DrawScreenCircle')
        lit = bitmap_pixels(m.memory, SCREEN, 192)
        expect(lit and not bitmap_pixels(m.memory, buffer, VIEW_ROWS), 'screen only', x, y, radius)
        expect(all(abs(math.hypot(px - x, py - y) - radius) < 1.5 for px, py in lit), 'on circle', x, y)
        expect(all(m.memory[t] == image[t] for t in targets), 'patches restored', x, y)
        expect((m.byte('CircleOffsetX'), m.byte('CircleOffsetY'), m.byte('CircleRadius')) ==
               (abs(x - 128), abs(y - 96), radius), 'parameters', x, y)
        expect(m.byte('CircleFlags') == 0x0C | (1 if x >= 128 else 0) | (2 if y < 96 else 0), 'flags', x, y)
    m.reset()
    m.clear(SCREEN, SCREEN_SIZE + ATTRIBUTES_SIZE)
    m.clear(buffer, VIEW_SIZE)
    m.poke('LastActiveObjectEnergy', 1)
    size = ctx['InstanceSize']
    for slot in range(ctx['InstanceSlotCount']):
        m.poke(ctx['InitialRuntimeState'] + slot * size + INSTANCE_STATE, 0)
    instance = ctx['InitialRuntimeState'] + 3 * size
    m.poke(instance + INSTANCE_DISC, 10, 20, 0x0F, 10)     # offsets, flags, radius
    m.poke(instance + INSTANCE_STATE, 0x30)
    patched = [ctx[n] for n in ('L_7FFA', 'L_801B', 'L_8060', 'L_80AB')]
    patched += [a + 1 for a in patched]
    patched += [ctx[n] for n in ('L_80E8', 'L_8450', 'L_809D', 'L_833F', 'L_8129', 'L_8236', 'L_8338',
                                 'L_8122', 'L_822F', 'L_843B')]
    m.call('DrawFlaggedObjectDiscs', limit=50_000_000, stubs={'FillViewAttributes': None})
    lit = bitmap_pixels(m.memory, SCREEN, 192)
    expect(len(lit) == 4361 and all(y < VIEW_ROWS for _, y in lit), 'discs on screen rows 0..127')
    expect(not bitmap_pixels(m.memory, buffer, VIEW_ROWS), 'buffer untouched')
    expect(all(m.memory[a] == image[a] for a in patched), 'renderer restored',
           [hex(a) for a in patched if m.memory[a] != image[a]])
    expect(m.byte(instance + INSTANCE_STATE) == 0x20 and m.byte('CircleRadius') == 10 + 2 * 15, 'state')
    expect((image[ctx['L_85D7']], image[ctx['L_85E2']]) == (0x4F, 0x3F) and
           (m.byte('L_85D7'), m.byte('L_85E2')) == (0xCF, 0xBF), 'restore operands')
    return count + 4 + 1


# ===========================================================================
# scanner: scanner background, contacts, compass and sun/planet proximity


def third_pixels(memory, before=None):
    """Lit pixels of the bottom screen third as (x, y) with y = 128..191 (new ones if before)."""
    out = set()
    base = SCREEN + 2 * SCREEN_THIRD
    for offset in range(SCREEN_THIRD):
        value = memory[base + offset]
        if before is not None:
            value &= ~before[offset]
        for bit in range(8):
            if value & (0x80 >> bit):
                out.add(((offset & 31) * 8 + bit, 128 + ((offset >> 5) & 7) * 8 + ((offset >> 8) & 7)))
    return out


@check('scanner', 'scanner-background', ['SaveScannerBackground', 'RestoreScannerBackground',
                                         'CopyScannerBackground'], 'R3-tests/test_backup.py',
       'Save copies the 624 bytes of character rows 2..7, columns 9..21 of the bottom third to '
       'ScannerBackupBuffer in row/line order without touching the screen, with the documented '
       'save patches; restore (only when ScannerContactsDrawn = 1) clears 8 x 11 bytes at row 1, '
       'column 10, copies the bytes back and restores the original instruction bytes.')
def check_scanner_background(ctx):
    m = ctx.machine()
    stack = ctx.upper_stack
    rng = random.Random(1)
    screen = [rng.randrange(256) for _ in range(SCREEN_SIZE)]
    m.memory[SCREEN:SCREEN + SCREEN_SIZE] = screen
    code = ctx['CopyScannerBackground']
    original = m.memory[code:ctx['HandleScreenKeys']]
    backup = ctx['ScannerBackupBuffer']
    cells = [ctx['ScannerBackupScreen'] + row * ROW_BYTES + line * 0x100 + i
             for row in range(6) for line in range(8) for i in range(13)]
    expect(len(cells) == len(set(cells)) == 624)
    m.poke('ScannerContactsDrawn', 0)
    m.clear(backup, len(cells))
    m.call('SaveScannerBackground', stack=stack)
    expect(m.memory[backup:backup + len(cells)] == [screen[a - SCREEN] for a in cells], 'save order')
    expect(m.byte(backup + len(cells)) == ctx.pristine[backup + len(cells)], 'save extent')
    expect(m.memory[SCREEN:SCREEN + SCREEN_SIZE] == screen, 'save must not modify the screen')
    patches = {'ScannerCopySwapStart': 0xEB, 'ScannerCopyPushRow': 0xE5, 'ScannerCopyPushLine': 0xE5,
               'ScannerCopyNextLine': 0xE1, 'ScannerCopySwapEnd': 0xEB, 'ScannerCopyRowSwap': 0x00}
    expect(all(m.byte(n) == v for n, v in patches.items()) and m.byte(ctx['ScannerCopyNextLine'] + 1) == 0x24,
           'save patches')
    saved = m.memory[backup:backup + len(cells)]
    m.clear(SCREEN, SCREEN_SIZE, 0x55)
    m.poke('ScannerContactsDrawn', 1)
    m.call('RestoreScannerBackground', stack=stack)
    expect(m.byte('ScannerContactsDrawn') == 0, 'flag cleared')
    cleared = {ctx['ScreenCockpitBitmap'] + ROW_BYTES + 10 + line * 0x100 + i for line in range(8) for i in range(11)}
    where = dict(zip(cells, saved))
    for address in range(SCREEN, SCREEN + SCREEN_SIZE):
        wanted = where.get(address, 0 if address in cleared else 0x55)
        expect(m.memory[address] == wanted, 'restore', hex(address))
    expect(m.memory[code:ctx['HandleScreenKeys']] == original, 'original instruction bytes restored')
    for flag in (0, 2, 0xFF):
        m.clear(SCREEN, SCREEN_SIZE, 0x55)
        m.poke('ScannerContactsDrawn', flag)
        m.call('RestoreScannerBackground', stack=stack)
        expect(m.byte('ScannerContactsDrawn') == flag and set(m.memory[SCREEN:SCREEN + SCREEN_SIZE]) == {0x55},
               'no effect', flag)
    return len(cells) + 4


@check('scanner', 'scanner-contacts', ['DrawScannerContacts'], 'R3-tests/test_scanner.py',
       'Scanner contact of one object: ScannerDotX = 0.75*x/256 (x = $1000 -> $0C, -$1000 -> $8C), '
       'ScannerStickHeight = 5/16*y/256 ($05), ScannerDotZ = 5/16*z/256, recorded dot/stick pixels; '
       'a coordinate middle byte of $40 or more is not drawn.')
def check_scanner_contacts(ctx):
    m = ctx.machine()
    golden = {(0, 0, 0): (0x00, 0x00, 0x00, (121, 123), (165, 165), 3),
              (0x1000, 0, 0): (0x0C, 0x00, 0x00, (133, 135), (165, 165), 3),
              (-0x1000, 0, 0): (0x8C, 0x00, 0x00, (110, 112), (165, 165), 3),
              (0, 0, 0x1000): (0x00, 0x00, 0x05, (121, 123), (160, 160), 3),
              (0, 0, -0x1000): (0x00, 0x00, 0x85, (121, 123), (170, 170), 3),
              (0, 0x1000, 0): (0x00, 0x05, 0x00, (121, 123), (160, 165), 8),
              (0, -0x1000, 0): (0x00, 0x85, 0x00, (121, 123), (165, 170), 8),
              (0x3000, 0, 0x3000): (0x24, 0x00, 0x0F, (157, 159), (150, 150), 3),
              (0x4000, 0, 0): None}
    size, state = ctx['InstanceSize'], ctx['InitialRuntimeState']
    for position, expected in golden.items():
        m.reset()
        m.clear(SCREEN, SCREEN_SIZE)
        m.poke('LastActiveObjectEnergy', 1)
        m.poke('ScannerContactsDrawn', 0)
        for slot in range(ctx['InstanceSlotCount']):
            m.poke(state + slot * size + ctx['InstanceEnergy'], 0)
        instance = state + size
        for axis, value in enumerate(position):
            put24(m.memory, instance + 3 * axis, value)
        m.poke(instance + ctx['InstanceEnergy'], 0x40)
        before = m.memory[SCREEN + 2 * SCREEN_THIRD:SCREEN + SCREEN_SIZE]
        m.call('DrawScannerContacts', stack=ctx.upper_stack)
        lit = third_pixels(m.memory, before)
        if expected is None:
            expect(not lit and m.byte('ScannerContactsDrawn') == 0, 'out of range drawn', position)
            continue
        xs, ys = [p[0] for p in lit], [p[1] for p in lit]
        got = (m.byte('ScannerDotX'), m.byte('ScannerStickHeight'), m.byte('ScannerDotZ'),
               (min(xs), max(xs)), (min(ys), max(ys)), len(lit))
        expect(got == expected and m.byte('ScannerContactsDrawn') == 1, position, got)
    return len(golden)


@check('scanner', 'compass', ['DrawCompass', 'DrawCompassBackground'], 'R3-tests/test_compass.py',
       'DrawCompassBackground copies CompassBackgroundBitmap to columns 21..23, rows 136..159; '
       'DrawCompass moves the 4x4 dot right for positive CompassDotX and up for positive '
       'CompassDotY (recorded positions) and draws nothing on screen 4.')
def check_compass(ctx):
    m = ctx.machine()
    bitmap = ctx['CompassBackgroundBitmap']

    def draw(dx, dy, behind, screen=0):
        m.reset()
        m.clear(SCREEN, SCREEN_SIZE)
        m.poke('CurrentScreenId', screen)
        m.poke('CompassDotX', dx, dy, behind)
        m.call('DrawCompass', stack=ctx.upper_stack)
        return third_pixels(m.memory)

    m.clear(SCREEN, SCREEN_SIZE)
    m.call('DrawCompassBackground', stack=ctx.upper_stack)
    for row in range(24):
        for column in range(3):
            expect(m.memory[SCREEN + screen_offset(168 + 8 * column, 136 + row)] == m.memory[bitmap + 3 * row + column],
                   'background', row, column)
    expect(len(third_pixels(m.memory)) == sum(bin(m.memory[bitmap + i]).count('1') for i in range(72)), 'extent')
    base = draw(0, 0, 0)
    expect(min(p[0] for p in base) >= 168 and max(p[0] for p in base) <= 191 and
           min(p[1] for p in base) == 136 and max(p[1] for p in base) == 159, 'compass extent')
    ring = draw(0x7F, 0x7F, 0) & draw(0x81, 0x81, 0) & base
    golden = {(0, 0, 0): (range(178, 182), range(145, 149)), (0, 0, 1): (range(178, 182), range(145, 149)),
              (5, 0, 0): (range(183, 187), range(145, 149)), (0x85, 0, 0): (range(173, 177), range(145, 149)),
              (0, 5, 0): (range(178, 182), range(140, 144)), (0, 0x85, 0): (range(178, 182), range(150, 154))}
    for args, (columns, rows) in golden.items():
        dot = draw(*args) - ring
        expect(sorted({p[0] for p in dot}) == list(columns) and sorted({p[1] for p in dot}) == list(rows),
               args, sorted(dot))
    expect(not draw(0, 0, 0, 4), 'screen 4 draws nothing')
    return 2 + len(golden) + 1


@check('scanner', 'sun-planet-proximity', ['UpdateProximityAndCompass'], 'R3-tests/test_magnitude.py',
       'Sun/planet distance thresholds: d < $C000 destroys the player, the sun sets FuelScoopRangeFlag '
       'below $E000 and CabinTemperature = high(2.5*($10000-d)), the planet sets StationPresent and '
       'AltitudeGauge = $A0 - high(2.5*($10000-d)), FlightCondition follows (recorded outputs).')
def check_sun_planet_proximity(ctx):
    m = ctx.machine()
    far = (0, 0, 0x30000)
    names = ('SunNearFlag', 'PlanetNearFlag', 'PlayerDeadFlag', 'FuelScoopRangeFlag', 'CabinTemperature',
             'AltitudeGauge', 'FlightCondition', 'StationPresent')
    golden = {
        ('sun', 0xBF00): (1, 0, 1, 9, 238, 238, 4, 9), ('sun', 0xC100): (1, 0, 0, 1, 157, 238, 99, 0),
        ('sun', 0xDF00): (1, 0, 0, 1, 82, 238, 2, 0), ('sun', 0xE100): (1, 0, 0, 0, 77, 238, 6, 0),
        ('sun', 0xF000): (1, 0, 0, 0, 40, 238, 6, 0), ('sun', 0xFF00): (1, 0, 0, 0, 2, 238, 6, 0),
        ('planet', 0xBF00): (0, 1, 1, 9, 238, 238, 4, 9), ('planet', 0xC100): (0, 1, 0, 9, 238, 3, 99, 1),
        ('planet', 0xF000): (0, 1, 0, 9, 238, 120, 6, 1), ('planet', 0xFF00): (0, 1, 0, 9, 238, 158, 6, 1),
        ('planet', 0x18000): (0, 1, 0, 9, 238, 238, 4, 1), ('planet', 0x28000): (0, 0, 0, 9, 238, 238, 4, 0)}
    for (body, distance), expected in golden.items():
        m.reset()
        m.poke('CurrentScreenId', 5)                       # full screen: compass not drawn
        sun = (0, 0, distance) if body == 'sun' else far
        planet = (0, 0, distance) if body == 'planet' else far
        for name, vector in (('SunPosition', sun), ('PlanetPosition', planet)):
            for axis, value in enumerate(vector):
                put24(m.memory, ctx[name] + 3 * axis, value)
        m.poke('PlayerDeadFlag', 0)
        m.poke('FuelScoopRangeFlag', 9)
        m.poke('CabinTemperature', 0xEE)
        m.poke('AltitudeGauge', 0xEE)
        m.poke('FlightCondition', 4)
        m.poke('StationPresent', 9)
        m.call('UpdateProximityAndCompass', stack=ctx.upper_stack)
        got = tuple(m.byte(n) for n in names)
        expect(got == expected, body, hex(distance), got)
    return len(golden)


# ===========================================================================
# sound: interrupt-driven effect player and synchronous noise players


@check('sound', 'interrupt-sound-player', ['UpdateSoundEffect', 'SoundRequestJumpTable',
                                           'FinishSoundEffect'], 'R3-tests/test_sound.py',
       'With sound on, each request bit of SoundEffectRequests starts its SoundRequestJumpTable '
       'entry (bit 0 -2, bit 1 -28, bit 2 +2 noise sweeps; bit 3 SRL A and bits 6/7 ADD A,$10 ROM '
       'pulse bursts; bits 4/5 pulse sweeps $FD/$D3), runs 8, 8, 8, 1, 2, 8, 1, 1 frames and clears '
       'its bit; with sound off nothing happens.')
def check_interrupt_sound_player(ctx):
    m = ctx.machine()
    stack = ctx.upper_stack
    table = ctx['SoundRequestJumpTable']
    targets = ['L_9181', 'L_917D', 'L_919B', 'L_9167', 'L_914A', 'L_9151', 'L_9160', 'L_9160']
    golden = [  # SoundState, NoiseDelayStep, PulseSweepStep, RomPulseScale, counters, pointer after frame 1
        (0x03, 0xFE, 0x05, 0x3FCB, 0x3E07, 0x0167), (0x03, 0xE4, 0x05, 0x3FCB, 0x2407, 0x0167),
        (0x83, 0x02, 0x05, 0x3FCB, 0x4207, 0x0167), (0x00, 0x00, 0x05, 0x3FCB, 0x0001, 0x037E),
        (0x01, 0x00, 0xFD, 0x3FCB, 0x01FD, None), (0x01, 0x00, 0xD3, 0x3FCB, 0x07D3, None),
        (0x00, 0x00, 0x05, 0x10C6, 0x000B, 0x1A7E), (0x00, 0x00, 0x05, 0x10C6, 0x000B, 0x1A7E)]
    frames_needed = [8, 8, 8, 1, 2, 8, 1, 1]
    for bit in range(8):
        m.reset()
        m.poke('ControlOptions', 0x80)
        m.poke('SoundEffectRequests', 1 << bit)
        m.poke('SoundState', 0)
        for frame in range(400):
            visited = m.call('UpdateSoundEffect', stack=stack, record=True)
            if frame == 0:
                entries = [pc for pc in visited if table <= pc < table + 24]
                expect(entries == [table + 3 * bit], 'dispatch entry', bit, entries)
                expect(m.word(table + 3 * bit + 1) == ctx[targets[bit]] and ctx[targets[bit]] in visited,
                       'jump target', bit)
                state, delay, pulse, scale, counters, pointer = golden[bit]
                expect((m.byte('SoundState'), m.byte('NoiseDelayStep'), m.byte('PulseSweepStep'),
                        m.word('RomPulseScale'), m.word('SoundCounters')) == (state, delay, pulse, scale, counters)
                       and m.byte('NoiseSamplesPerStep') == 0x40 and m.byte('SoundRequestIndex') == bit,
                       'first frame', bit)
                if pointer is not None:
                    expect(m.word('SoundDataPointer') == pointer, 'pointer', bit)
            if not m.byte('SoundEffectRequests') & (1 << bit):
                break
        expect(frame + 1 == frames_needed[bit] and m.byte('SoundEffectRequests') == 0 and
               m.byte('SoundState') == 0, 'frames', bit, frame + 1)
    m.reset()
    m.poke('ControlOptions', 0)
    m.poke('SoundEffectRequests', 1)
    m.call('UpdateSoundEffect', stack=stack)
    expect(m.byte('SoundState') == 0 and m.byte('SoundEffectRequests') == 1, 'sound off')
    return sum(frames_needed) + 1


@check('sound', 'synchronous-sound-players', ['PlayLongNoiseSweep', 'PlayRisingNoiseSweep',
                                              'PlayFallingNoiseSweep', 'PlayNoiseBurst', 'WaitSoundFinished'],
       'R3-tests/test_sound.py',
       'Each synchronous player runs its effect to the end (SoundState 0) and clears all requests; '
       'last samples-per-step/delay-step operands $A0/+2, $C0/-16, $C0/+16, $A0/(unchanged).')
def check_synchronous_sound_players(ctx):
    m = ctx.machine()
    golden = {'PlayLongNoiseSweep': (0xA0, 0x02, 0x4400), 'PlayRisingNoiseSweep': (0xC0, 0xF0, 0x0000),
              'PlayFallingNoiseSweep': (0xC0, 0x10, 0x0000),
              'PlayNoiseBurst': (0xA0, ctx.pristine[ctx['NoiseDelayStep']], 0x4000)}
    for entry, expected in golden.items():
        m.reset()
        m.poke('ControlOptions', 0x80)
        m.poke('SoundEffectRequests', 0x55)
        m.call(entry, stack=ctx.upper_stack, limit=50_000_000)
        expect(m.byte('SoundState') == 0 and m.byte('SoundEffectRequests') == 0, entry)
        expect((m.byte('NoiseSamplesPerStep'), m.byte('NoiseDelayStep'), m.word('SoundCounters')) == expected,
               entry)
    return len(golden)


# ===========================================================================
# dust: stardust particles and the Torus jump streak

DUST_RECORD = 5
DUST_COUNT = 16


def dust_pixel(buffer, x, sx, y, sy):
    column = (0x80 - x if sx else 0x80 + x) & 0xFF
    row = (0x3F + y if sy else 0x3F - y) & 0xFF
    high = (buffer >> 8) | (row & 7) | (8 if sy else 0)
    low = ((row & 0x38) << 2 | (column >> 3) & 0x1F) & 0xFF
    return high << 8 | low, 0x80 >> (column & 7)


def dust_front_model(buffer, entry, speed):
    """One front-view particle step without roll/pitch: (new record, pixel) or None (respawn)."""
    b0, b1, z, xlo, ylo = entry
    dz = (speed >> 1) + 1
    out = {}
    for axis, (magnitude, low) in (('x', (b0 & 0x7F, xlo)), ('y', (b1 & 0x7F, ylo))):
        h1, h2 = magnitude * (dz & 31), low * (dz & 31)
        total = low + (h2 & 0xFF)
        new_low = total & 0xFF
        word = h1 + (h2 >> 8) + ((total >> 8) if axis == 'x' else 1)
        if word < z:
            delta = word * 256 // z
        else:
            delta = word * 256 // z if word % z else (word // z) << 8 | word >> 8
            if delta >= 0x4000:
                raise OverflowError          # quotient outside DivideWordToFixed's exact range
        value = (magnitude << 8 | new_low) + delta
        if value >> 8 >= 0x78:
            return None
        out[axis] = value
    new_z = z - dz
    if new_z <= 0:
        return None
    x, y = out['x'] >> 8, out['y'] >> 8
    if y >= 0x3F:
        return None
    sx, sy = b0 >> 7, b1 >> 7
    return ((x | sx << 7, y | sy << 7, new_z, out['x'] & 0xFF, out['y'] & 0xFF),
            dust_pixel(buffer, x, sx, y, sy))


@check('dust', 'stardust-update', ['UpdateDust', 'MoveAndPlotDust', 'MoveDustInDepth', 'ApplyDustRoll',
                                   'ApplyDustPitch', 'GetDustPixelAddress', 'RespawnDust'],
       'R4-tests/check_dust.py',
       'Front view without roll/pitch: every particle record and every XORed pixel equals the model '
       'X += X*dz/Z, Y += Y*dz/Z, Z -= dz (dz = speed/2+1), leaving particles respawn inside the masks '
       'with their fraction bytes kept; rear view Z += dz with shrinking X/Y; roll keeps the radius '
       'within 3%; pitch moves particles vertically (recorded records).')
def check_stardust_update(ctx):
    m = ctx.machine()
    table, buffer = ctx['L_A46C'], ctx['ViewBitmapBuffer']
    expect(buffer & 0xFF == 0)

    def setup(entries, speed, screen=0, roll=0, pitch=0):
        m.reset()
        m.poke('CurrentScreenId', screen)
        m.poke('DustLastScreenId', screen)
        m.poke('PlayerRoll', roll, pitch, speed)
        m.poke('WitchspaceFlag', 0)
        m.poke('TorusJumpDustFlag', 0)
        m.poke('AuxRandomSeed', 0x34, 0x12)
        m.clear(buffer, VIEW_SIZE)
        for i, entry in enumerate(entries):
            m.poke(table + DUST_RECORD * i, *entry)

    def records():
        return [tuple(m.memory[table + DUST_RECORD * i:table + DUST_RECORD * (i + 1)]) for i in range(DUST_COUNT)]

    rng = random.Random(1)
    checked = respawned = skipped = 0
    for _ in range(600):
        speed = rng.randrange(0, 32)
        entries = [(rng.randrange(0, 0x40) | rng.choice((0, 0x80)), rng.randrange(0, 0x30) | rng.choice((0, 0x80)),
                    rng.choice((rng.randrange(0x40, 0x100), rng.randrange(1, 0x12))),
                    rng.randrange(256), rng.randrange(256)) for _ in range(DUST_COUNT)]
        try:
            models = [dust_front_model(buffer, e, speed) for e in entries]
        except OverflowError:
            skipped += 1
            continue
        setup(entries, speed)
        m.call('UpdateDust')
        got = records()
        pixels = {}
        for i, (entry, model) in enumerate(zip(entries, models)):
            if model is None:
                new = got[i]
                expect(new[0] & 0x7F <= 0x3F and new[1] & 0x7F <= 0x1F and new[2] >= 0x80 and new[3:] == entry[3:],
                       'respawn', entry, new)
                respawned += 1
                continue
            record, (address, mask) = model
            expect(got[i] == record, 'record', entry, got[i], record, speed)
            pixels[address] = pixels.get(address, 0) ^ mask
            checked += 1
        view = {a: m.memory[a] for a in range(buffer, buffer + VIEW_SIZE) if m.memory[a]}
        expect(view == {a: v for a, v in pixels.items() if v}, 'plotted pixels')
    entries = [(0x20 + i, 0x90 + i, 0x80, 0, 0) for i in range(DUST_COUNT)]
    setup(entries, 20, screen=1)
    m.call('UpdateDust')
    for entry, new in zip(entries, records()):
        expect(new[2] == entry[2] + 11 and new[0] & 0x7F <= entry[0] & 0x7F and new[1] & 0x7F <= entry[1] & 0x7F,
               'rear view', entry, new)
    worst, moved = 0.0, 0
    for roll in (0x05, 0x0F, 0x85, 0x8F):
        entries = [(rng.randrange(8, 0x30) | rng.choice((0, 0x80)), rng.randrange(8, 0x30) | rng.choice((0, 0x80)),
                    0xF0, 0, 0) for _ in range(DUST_COUNT)]
        setup(entries, 0, roll=roll)
        m.call('UpdateDust')
        for entry, new in zip(entries, records()):
            if new[2] != 0xEF:
                continue                                     # respawned
            r0 = math.hypot(entry[0] & 0x7F, entry[1] & 0x7F)
            worst = max(worst, abs(math.hypot(new[0] & 0x7F, new[1] & 0x7F) - r0) / r0)
            moved += (entry[0], entry[1]) != (new[0], new[1])
    expect(worst < 0.03 and moved > 40, 'roll', worst, moved)
    for pitch, expected in ((0x0F, (16, 30, 125)), (0x8F, (15, 128, 127))):
        setup([(0x10, 0x10, 0x80, 0, 0)] * DUST_COUNT, 0, pitch=pitch)
        m.call('UpdateDust')
        expect(records()[0][:3] == expected, 'pitch', hex(pitch), records()[0])
    return checked + respawned + DUST_COUNT + moved + 2, dict(
        front_view_particles_matched=checked, respawned=respawned, trials_skipped_quotient_4000=skipped,
        worst_roll_radius_change=round(worst, 4))


@check('dust', 'launch-dust-respawn', ['RespawnDustFront'], 'R4-tests/check_dust.py',
       'With the launch patch of L_7A88 applied (masks $83 at L_A348/L_A34D, RET at DustRespawnExit, '
       'made here in the private RAM copy exactly as the game does), each call creates one particle '
       'with |X|, |Y| <= 3 and Z >= $80 and advances DE by 5.')
def check_launch_dust_respawn(ctx):
    """Private RAM patch (as in the original annotation test): the three bytes that L_7A88 patches
    before its launch loop (L_A348, L_A34D = $83, DustRespawnExit = RET) are set the same way."""
    m = ctx.machine()
    m.poke('L_A348', 0x83)
    m.poke('L_A34D', 0x83)
    m.poke('DustRespawnExit', RET)
    rng = random.Random(64)
    target = ctx.scratch
    for _ in range(64):
        m.poke('DustPitchRate', 0)
        m.poke('CurrentScreenId', 0)
        m.call('RespawnDustFront', h=rng.randrange(256), l=rng.randrange(256), de=target)
        record = m.memory[target:target + 3]
        expect(record[0] & 0x7F <= 3 and record[1] & 0x7F <= 3 and record[2] >= 0x80, record)
        expect(m.pair('de') == target + DUST_RECORD, hex(m.pair('de')))
    return 64


def jump_shift_model(value):
    if value >= 0:
        return value - 0x2000 if value >= 0x2000 else -(0x2000 - value)
    magnitude = -value + 0x2000
    return 0x7FFFFF if magnitude > 0x7FFFFF else -magnitude


@check('dust', 'torus-jump', ['HandleTorusJumpKey', 'ApplyJumpShift', 'UpdateDust'],
       'R4-tests/probe_jump2.py (ported to a controlled routine test)',
       'With J latched and the preconditions met, HandleTorusJumpKey sets TorusJumpDustFlag and '
       'shifts the z coordinates of SunPosition, PlanetPosition and slot 0 by $2000 ($85AE16 -> '
       '$85CE16, $015ADC -> $013ADC); each inhibitor (SunNearFlag 1, PlanetNearFlag 1, L_DA0F set, '
       'StationDormantFlag 0) prevents it; ApplyJumpShift follows its sign-magnitude model; the next '
       'UpdateDust clears the flag and runs three passes with speeds $1E, $10, $10.')
def check_torus_jump(ctx):
    m = ctx.machine()
    z = ctx['InstanceZ']

    def prepare(**override):
        m.reset()
        values = dict(SunNearFlag=0, PlanetNearFlag=0, L_DA0F=0, StationDormantFlag=1)
        values.update(override)
        for name, value in values.items():
            m.poke(name, value)
        m.poke('KeyFlagsViews', 0x40)
        m.poke('TorusJumpDustFlag', 0)
        put24(m.memory, ctx['SunPosition'] + z, sm24(0x85AE16))
        put24(m.memory, ctx['PlanetPosition'] + z, sm24(0x015ADC))
        put24(m.memory, ctx['InitialRuntimeState'] + z, 0x001000)

    prepare()
    m.call('HandleTorusJumpKey')
    expect(m.byte('TorusJumpDustFlag') == 1 and m.byte('KeyFlagsViews') == 0, 'jump made')
    expect(get24(m.memory, ctx['SunPosition'] + z) == sm24(0x85CE16) and
           get24(m.memory, ctx['PlanetPosition'] + z) == sm24(0x013ADC) and
           get24(m.memory, ctx['InitialRuntimeState'] + z) == -0x1000, 'shifted coordinates')
    cases = 1
    for override in (dict(SunNearFlag=1), dict(PlanetNearFlag=1), dict(L_DA0F=1), dict(StationDormantFlag=0)):
        prepare(**override)
        m.call('HandleTorusJumpKey')
        expect(m.byte('TorusJumpDustFlag') == 0 and m.byte('KeyFlagsViews') == 0 and
               get24(m.memory, ctx['SunPosition'] + z) == sm24(0x85AE16), 'inhibited', override)
        cases += 1
    rng = random.Random(9)
    values = [0, 1, 0x1FFF, 0x2000, 0x2001, 0x7FFFFF, -1, -0x1FFF, -0x7FDFFF, -0x7FE000, -0x7FFFFF]
    values += [rng.randint(-0x7FFFFF, 0x7FFFFF) for _ in range(2000)]
    record = ctx.scratch
    for value in values:
        put24(m.memory, record + z, value)
        m.call('ApplyJumpShift', ix=record)
        expect(get24(m.memory, record + z) == jump_shift_model(value), 'ApplyJumpShift', hex(value))
        cases += 1
    prepare()
    m.call('HandleTorusJumpKey')
    m.poke('CurrentScreenId', 0)
    m.poke('DustLastScreenId', 0)
    m.poke('PlayerRoll', 0, 0, 5)
    m.poke('WitchspaceFlag', 0)
    m.clear('ViewBitmapBuffer', VIEW_SIZE)
    speeds = []
    m.call('UpdateDust', hooks={'MoveAndPlotDust': lambda mm: speeds.append(mm.byte('PlayerSpeed'))})
    expect(speeds == [0x1E, 0x10, 0x10] and m.byte('TorusJumpDustFlag') == 0, 'jump streak', speeds)
    return cases + 1


def sm24(raw):
    """Signed value of a raw 24-bit sign-magnitude number written as $SSMMLL."""
    return -(raw & 0x7FFFFF) if raw & 0x800000 else raw


# ===========================================================================
# economy: galaxy generator, system search and distance, legal penalty, market


def load_jameson(m):
    """Copy the JAMESON template into the active commander record (as CopyCommanderTemplate)."""
    template, size = m['CommanderTemplateBuffer'], m['CommanderTemplateBufferSize']
    m.poke('ActiveCommanderRecord', *m.memory[template:template + size])


def galactic_chart_state(m):
    """Cross-hair settings left by the galactic chart (L_AB4E), where systems are searched.

    With the image value CrosshairSize = 0, DrawChartCursor would XOR a 256-pixel arm
    through the attribute and BASIC area, including the test stack.
    """
    m.poke('CrosshairBottomLimit', 0x98)
    m.poke('CrosshairSize', 0x0A)


ZERO_REGISTERS = dict(a=0, f=0, bc=0, de=0, hl=0)


@check('economy', 'galaxy-system-names', ['LoadGalaxySeedsToGenerator', 'GenerateSystemName'],
       'R5-tests/test_r5.py',
       'Galaxy 1 starts TIBEDIED, QUBE, LELEER, BIARGE, XEQUERIN, TIRAOR, RABEDIRA, LAVE; the '
       'generator walks all 256 systems.')
def check_galaxy_system_names(ctx):
    m = ctx.machine()
    load_jameson(m)
    m.call('LoadGalaxySeedsToGenerator', **ZERO_REGISTERS)
    names = []
    for _ in range(256):
        m.call('GenerateSystemName', **ZERO_REGISTERS)
        names.append(m.text('GeneratedSystemName'))
    expect(names[:8] == ['TIBEDIED', 'QUBE', 'LELEER', 'BIARGE', 'XEQUERIN', 'TIRAOR', 'RABEDIRA', 'LAVE'],
           names[:8])
    expect(all(names), 'empty name')
    return len(names)


@check('economy', 'find-system-and-distance', ['FindSystemByName', 'DeriveSelectedSystemData',
                                               'UpdateSelectedSystemDistance'], 'R5-tests/test_r5.py',
       'FindSystemByName selects LAVE at X 20, Y 173 (the JAMESON current system: same seeds, '
       'distance 0) with economy 5, government 3, tech level 4 (template 5), population 25, '
       'productivity 7000; TIBEDIED is 176 tenths away at (2, 90); an unknown name returns carry.  '
       'The cross-hair settings are those of the galactic chart.')
def check_find_system_and_distance(ctx):
    """Fixture: galactic-chart cross-hair settings (see galactic_chart_state)."""
    m = ctx.machine()
    load_jameson(m)
    galactic_chart_state(m)

    def find(name):
        m.poke('NameInputBuffer', *(name.encode() + bytes(9 - len(name))))
        m.call('FindSystemByName', **ZERO_REGISTERS)
        return not m.carry()

    m.poke('ChartCursorX', 0, 0)
    expect(find('LAVE') and m.text('SelectedSystemName') == 'LAVE', 'LAVE')
    expect((m.byte('ChartCursorX'), m.byte('ChartCursorY')) == (m.byte('CurrentSystemX'), m.byte('CurrentSystemY'))
           == (20, 173), 'cursor')
    expect((m.byte('SelectedSystemEconomy'), m.byte('SelectedSystemGovernment'), m.byte('SelectedSystemTechLevel'),
            m.byte('SelectedSystemPopulation'), m.word('SelectedSystemProductivity')) == (5, 3, 4, 25, 7000), 'data')
    expect(m.byte('SelectedSystemGovernment') == m.byte('CurrentGovernment') and m.byte('CurrentTechLevel') == 5,
           'template government / tech level')
    seeds = ctx['SelectedSystemSeeds']
    expect(m.memory[seeds:seeds + 6] == m.memory[ctx['CurrentSystemSeeds']:ctx['CurrentSystemSeeds'] + 6], 'seeds')
    expect(m.word('SelectedSystemDistance') == 0, 'distance to itself')
    expect(not find('NOWHERE'), 'unknown name')
    expect(find('TIBEDIED') and m.word('SelectedSystemDistance') == 176 and
           (m.byte('ChartCursorX'), m.byte('ChartCursorY')) == (2, 90), 'TIBEDIED')
    return 3


@check('economy', 'contraband-penalty', ['AddContrabandPenalty'], 'R5-tests/test_r5.py',
       'Slaves and narcotics add 4 per ton, firearms 2, other goods nothing; saturates at 255.')
def check_contraband_penalty(ctx):
    m = ctx.machine()
    cases = 0
    for commodity, factor in ((3, 4), (6, 4), (10, 2), (0, 0), (2, 0), (16, 0)):
        m.poke('PlayerLegalScore', 0)
        m.call('AddContrabandPenalty', a=commodity, b=5, f=0, c=0, de=0, hl=0)
        expect(m.byte('PlayerLegalScore') == 5 * factor, commodity)
        cases += 1
    m.poke('PlayerLegalScore', 250)
    m.call('AddContrabandPenalty', a=3, b=5, f=0, c=0, de=0, hl=0)
    expect(m.byte('PlayerLegalScore') == 255, 'saturation')
    return cases + 1


@check('economy', 'market', ['ComputeMarket'], 'R5-tests/test_r5.py',
       'Lave market for fluctuation 46: recorded prices (tenths of a credit), no alien items; with '
       'the opcode at L_AF01 patched to NOP (the game\'s own stock-keeping patch, applied here in the '
       'private RAM copy) the stock is not stored.')
def check_market(ctx):
    """Private RAM patch (as in the original annotation test): the opcode at L_AF01 is set to NOP for the
    second ComputeMarket call, as the game's stock-keeping patch does."""
    m = ctx.machine()
    load_jameson(m)
    galactic_chart_state(m)
    m.poke('NameInputBuffer', *b'LAVE\0\0\0\0\0')
    m.call('FindSystemByName', **ZERO_REGISTERS)
    m.poke('MarketFluctuation', 46)
    m.call('ComputeMarket', **ZERO_REGISTERS)
    prices = [m.word(ctx['MarketPrices'] + 2 * i) for i in range(17)]
    expect(prices == [32, 64, 220, 112, 284, 952, 656, 904, 612, 388, 780, 704, 112, 388, 696, 212, 536], prices)
    stock = ctx['MarketStock']
    expect(m.byte(stock + 16) == 0, 'alien items stock')
    m.clear(stock, 17, 0x55)
    m.poke('L_AF01', 0)
    m.call('ComputeMarket', **ZERO_REGISTERS)
    expect(m.memory[stock:stock + 16] == [0x55] * 16 and m.byte(stock + 16) == 0, 'NOP patch keeps the stock')
    return 2


# ===========================================================================
# text: token and message control handlers, screen text helpers

class TextMachine:
    """Text harness of the R6 tests: runtime font copy, JAMESON record, row 5, column 0.

    Characters are captured with a hook at PutCharacter (the routine still runs); a HALT
    inside a handler is treated as a completed frame wait (no interrupts).
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.m = ctx.machine()

    def fresh(self, row=5, column=0, mode=None):
        m = self.m
        m.reset()
        font, size = self.ctx['FontBitmap'], self.ctx['FontBitmapSize']
        m.poke('FontRuntime', *m.memory[font:font + size])
        load_jameson(m)
        m.poke('TextColumn', column, row)
        if mode is not None:
            m.poke('L_BA98', mode)
        return m

    def run(self, entry, a=0, **registers):
        out = []
        values = dict(f=0, bc=0, de=0, hl=0, ix=0, iy=ROM_IY)
        values.update(registers)
        self.m.call(entry, a=a, halt=True, limit=400_000,
                    hooks={'PutCharacter': lambda mm: out.append(chr(mm.reg('a')))}, **values)
        return ''.join(out)


@check('text', 'token-control-handlers', ['PrintToken', 'PrintGalaxyNumber', 'PrintPresentSystemName',
                                          'PrintSelectedSystemName', 'PrintCommanderName', 'PrintFuelLine',
                                          'PrintCashLine', 'PrintGalaxyFirstSystemName', 'SetCapitals',
                                          'SetTitleCase', 'SelectMessageMode'], 'R6-tests/text_handlers.py',
       'Token controls 1..11 print " 1"/" 3", the present and selected system names, "Jameson", '
       '"Fuel: 7.0 Light Years", "Cash:   100.0 Cr", "Tibedied" and set the case/mode flags.')
def check_token_control_handlers(ctx):
    t = TextMachine(ctx)

    def token(code, **pokes):
        m = t.fresh()
        for name, value in pokes.items():
            m.poke(name, *(value if isinstance(value, (bytes, list)) else [value]))
        return t.run('PrintToken', a=code)

    golden = [(1, {}, ' 1'), (1, dict(CurrentGalaxy=2), ' 3'), (2, dict(CurrentSystemName=b'LAVE\0'), 'Lave'),
              (3, dict(SelectedSystemName=b'DISO\0'), 'Diso'), (4, {}, 'Jameson'), (5, {}, 'Fuel: 7.0 Light Years'),
              (7, {}, 'Cash:   100.0 Cr'), (11, {}, 'Tibedied')]
    for code, pokes, text in golden:
        expect(token(code, **pokes) == text, code, pokes, token(code, **pokes))
    m = t.m
    token(6)
    expect(m.byte('LetterCaseMode') == 1, 'token 6')
    token(8, LetterCaseMode=1)
    expect(m.byte('LetterCaseMode') == 0, 'token 8')
    t.fresh(row=5, column=7)
    t.run('PrintToken', a=9)
    expect((m.byte('TextRow'), m.byte('TextColumn'), m.byte('CapitaliseNextFlag')) == (6, 0, 1), 'token 9')
    token(10, L_BA98=0)
    expect(m.byte('L_BA98') == 1, 'token 10')
    return len(golden) + 4


@check('text', 'message-control-handlers', ['PrintMessageByte', 'SelectTokenMode', 'SetLowerCase',
                                            'SetColumn4Capital', 'CapitaliseNextLetter', 'SetTextRow10',
                                            'SetTextRow6', 'ClearScreenAndFrame', 'DrawTitleUnderline',
                                            'ClearPromptLines', 'PrintSelectedSystemAdjective',
                                            'PrintRandomName'], 'R6-tests/text_handlers.py',
       'Message controls: 6 token mode, 13 lower case, 8 column 4 + capital, 19 capital, 23/29 rows '
       '10/6, 10 new line, 9 clear screen and frame, 11 title underline at $4340, 21 clears the prompt '
       'lines (480 bytes from $50A1), 17 adjectives Lavian/Disian/Riedquatian in justified text, 18 '
       'random names, 4 commander, 16 first system name.')
def check_message_control_handlers(ctx):
    t = TextMachine(ctx)
    m = t.m

    def message(code, row=5, column=0, **pokes):
        t.fresh(row, column, mode=1)
        for name, value in pokes.items():
            m.poke(name, *(value if isinstance(value, (bytes, list)) else [value]))
        return t.run('PrintMessageByte', a=code)

    message(6)
    expect(m.byte('L_BA98') == 0, 'message 6')
    message(13)
    expect(m.byte('LetterCaseMode') == 2, 'message 13')
    message(8, column=9)
    expect((m.byte('TextColumn'), m.byte('CapitaliseOnce')) == (4, 1), 'message 8')
    message(19)
    expect(m.byte('CapitaliseOnce') == 1, 'message 19')
    for code, row in ((23, 10), (29, 6), (10, 6)):
        message(code, column=9)
        expect(m.byte('TextRow') == row, 'message row', code)
    t.fresh(9, 9, mode=1)
    m.clear(SCREEN, SCREEN_SIZE + ATTRIBUTES_SIZE, 0x55)
    t.run('PrintMessageByte', a=9)
    bitmap = m.memory[SCREEN:SCREEN + SCREEN_SIZE]
    edges = {a for a in range(SCREEN_SIZE)
             if a % ROW_BYTES in (0, ROW_BYTES - 1) or a < ROW_BYTES or a >= SCREEN_SIZE - ROW_BYTES}
    expect(set(m.memory[ATTRIBUTES:ATTRIBUTES + ATTRIBUTES_SIZE]) == {7} and set(bitmap[:ROW_BYTES]) == {0xFF}
           and set(bitmap[-ROW_BYTES:]) == {0xFF}, 'message 9 frame lines and colours')
    expect(all(bitmap[ROW_BYTES * k] & 0x80 and bitmap[ROW_BYTES * k + ROW_BYTES - 1] & 1 for k in range(192)),
           'message 9 side lines')
    expect(not any(bitmap[a] for a in range(SCREEN_SIZE) if a not in edges), 'message 9 interior')
    expect((m.byte('TextRow'), m.byte('TextColumn')) == (1, 0), 'message 9 cursor')
    message(11)
    lit = [a for a in range(SCREEN, SCREEN + SCREEN_SIZE) if m.memory[a]]
    expect(lit == list(range(SCREEN + screen_offset(0, 19), SCREEN + screen_offset(0, 19) + ROW_BYTES)) and
           set(m.memory[a] for a in lit) == {0xFF}, 'message 11 underline')
    t.fresh(3, 5, mode=1)
    m.clear(SCREEN, SCREEN_SIZE, 0xFF)
    t.run('PrintMessageByte', a=21)
    cleared = [a for a in range(SCREEN, SCREEN + SCREEN_SIZE) if m.memory[a] == 0]
    expect((m.byte('TextRow'), m.byte('TextColumn'), len(cleared), cleared[0], cleared[-1]) ==
           (21, 0, 480, SCREEN + screen_offset(8, 168), SCREEN + screen_offset(240, 183)), 'message 21')
    for name, adjective in (('LAVE', 'Lavian'), ('DISO', 'Disian'), ('RIEDQUAT', 'Riedquatian')):
        t.fresh(mode=1)
        m.poke('SelectedSystemName', *(name.encode() + b'\0'))
        out = ''.join(t.run('PrintMessageByte', a=code) for code in (14, 13, 17, 15))
        expect(out.strip() == adjective and m.byte('TextRedirectFlag') == 0, name, out)
    names = []
    for seed in (0x1234, 0xBEEF, 0x0F0F, 0x7777, 0xA5A5):
        t.fresh(mode=1)
        m.poke('DescriptionSeed1', seed & 255, seed >> 8)
        m.poke('DescriptionSeed2', (seed * 7) & 255, (seed * 3 >> 8) & 255)
        names.append(t.run('PrintMessageByte', a=18))
    expect(names == ['Le', 'Atainso', 'Et', 'Noreet', 'Atlo'], names)
    expect(message(4) == 'Jameson' and message(16) == 'Tibedied', 'messages 4 and 16')
    return 22


@check('text', 'attribute-strips', ['ColourAttributeStrips', 'ColourPromptRow'], 'R6-tests/text_handlers.py',
       'BuyScreenAttributeStrips colours 60 cells ($5821..$585E) and TradeScreenAttributeStrip 30 '
       '($5821..$583E) with $05, then $5822/$5823 = $07; ColourPromptRow colours $5AA1..$5ABE.')
def check_attribute_strips(ctx):
    m = ctx.machine()

    def coloured():
        return [a for a in range(ATTRIBUTES, ATTRIBUTES + ATTRIBUTES_SIZE) if m.memory[a]]

    row1 = ATTRIBUTES + ROW_BYTES + 1
    m.call('ColourAttributeStrips', de=ctx['BuyScreenAttributeStrips'], a=0)
    cells = coloured()
    expect(len(cells) == 60 and cells[0] == row1 and cells[-1] == row1 + ROW_BYTES + 29, 'buy strips')
    expect([m.byte(row1 + i) for i in range(3)] == [5, 7, 7] and m.byte(row1 + 63) == 0 and m.byte(row1 + 64) == 0)
    m.reset()
    m.call('ColourAttributeStrips', de=ctx['TradeScreenAttributeStrip'], a=0)
    cells = coloured()
    expect(len(cells) == 30 and cells[0] == row1 and cells[-1] == row1 + 29, 'trade strip')
    m.reset()
    m.call('ColourPromptRow', a=0)
    cells = coloured()
    expect(cells == list(range(ATTRIBUTES + 21 * ROW_BYTES + 1, ATTRIBUTES + 21 * ROW_BYTES + 31)) and
           {m.memory[a] for a in cells} == {5}, 'prompt row')
    return 3


@check('text', 'screen-text-helpers', ['PrintEconomy', 'PrintCommodityUnit', 'TestCommodityTonnes'],
       'R6-tests/economy.py',
       'PrintEconomy prints "Mainly" for economy 4 and "Rich" otherwise, Industrial for 0..3 and '
       'Agricultural for 4..7; units t (0..12, 16), kg (13, 14), g (15), km (17); carry = tonnes.')
def check_screen_text_helpers(ctx):
    t = TextMachine(ctx)
    for economy in range(8):
        t.fresh().poke('SelectedSystemEconomy', economy)
        text = t.run('PrintEconomy')
        expected = ('Economy:' + ('Mainly' if economy == 4 else 'Rich') +
                    (' Industrial' if economy < 4 else ' Agricultural'))
        expect(text == expected, economy, text)
    units = ['t'] * 13 + ['kg', 'kg', 'g', 't', 'km']
    for index in range(18):
        t.fresh().poke('CurrentCommodity', index)
        expect(t.run('PrintCommodityUnit') == units[index], 'unit', index)
        t.fresh().poke('CurrentCommodity', index)
        t.run('TestCommodityTonnes')
        expect(t.m.carry() == (1 if units[index] == 't' else 0), 'tonnes', index)
    return 8 + 36


@check('text', 'insert-space', ['InsertSpaceInTextBuffer'], 'R7-tests/check_r7_routines.py',
       'A space is inserted at JustifyWritePointer; the bytes up to the first zero move up; the '
       'pointer is unchanged.')
def check_insert_space(ctx):
    m = ctx.machine()
    buffer = ctx['WrapLineBuffer']
    for text in (b'AB', b'HELLO', b'', b'X'):
        m.poke(buffer, *(list(text) + [0] * (40 - len(text))))
        m.poke_word('JustifyWritePointer', buffer)
        m.call('InsertSpaceInTextBuffer')
        expect(bytes(m.memory[buffer:buffer + len(text) + 2]) == b' ' + text + b'\0', text)
        expect(m.word('JustifyWritePointer') == buffer, 'pointer')
    return 4


# ===========================================================================
# commander: rating, security number, galaxy-seed comparison


def rating_model(kills):
    low, high = kills & 255, kills >> 8
    if high == 0:
        token = 0x15
        for threshold in (0x08, 0x10, 0x20, 0x40, 0x80, 0xFF):
            if threshold >= low:
                return token
            token += 1
    token = 0x1A
    for threshold in (0x02, 0x0A, 0x19, 0xFF):
        if threshold >= high:
            return token
        token += 1


def security_model(kills, galaxy, flags, money):
    def parity(value):
        return bin(value).count('1') & 1

    e = ((kills >> 8) << 1 | (kills >> 7) & 1) & 255
    a = galaxy | (0x08 if flags & 0x08 else 0) | (0x10 if flags & 0x40 else 0)
    d = ((a << 3) | (a >> 5)) & 255
    h, l = money >> 8, money & 255
    for value in (e, h, l):
        d = (d >> 1) | (parity(value) << 7)
    d = ((l ^ d) + 0x3D) & 255
    e = ((d ^ e) + 0x66) & 255
    h = ((e ^ h) + 0x8F) & 255
    l = ((h ^ l) + 0xC7) & 255
    return h << 8 | l, d << 8 | e


@check('commander', 'rating-thresholds', ['ShowCommanderStatus', 'RatingKillThresholdsLow',
                                          'RatingKillThresholdsHigh'], 'R7-tests/check_r7_routines.py',
       'Rating token for the 16-bit kill count: 0..8 HARMLESS, ..16, ..32, ..64, ..128, 129..767 '
       'COMPETENT, 768..2815 DANGEROUS, 2816..6655 DEADLY, 6656+ ELITE.  Entered at the '
       'LD HL,CombatScoreHigh of ShowCommanderStatus, stopped at L_D130.')
def check_rating_thresholds(ctx):
    m = ctx.machine()
    high = ctx['CombatScoreHigh']
    entry = ctx.find('ShowCommanderStatus', 'L_D130', [0x21, high & 255, high >> 8])
    kills_list = list(range(1024)) + [hi << 8 | lo for hi in range(4, 256) for lo in (0, 255)]
    for kills in kills_list:
        m.poke_word('CombatScoreLow', kills)
        m.call(entry, stop='L_D130')
        expect(m.reg('b') == rating_model(kills), kills, m.reg('b'))
    return len(kills_list)


@check('commander', 'security-number', ['AccessMenuSave', 'RotateParityIntoD'], 'R7-tests/check_r7_routines.py',
       'The two save "security numbers" (HL, DE) follow the Python model of kill count, galaxy, '
       'CommanderFlags bits 3/6 and CashHigh for any carry on entry.  Entered at the '
       'LD HL,(CombatScoreLow) of AccessMenuSave, stopped at the first CALL PrintDecimalHL after it.')
def check_security_number(ctx):
    m = ctx.machine()
    low, printer = ctx['CombatScoreLow'], ctx['PrintDecimalHL']
    entry = ctx.find('AccessMenuSave', 'CopyCommanderToTemplate', [0x2A, low & 255, low >> 8])
    stop = ctx.find(entry, 'CopyCommanderToTemplate', [0xCD, printer & 255, printer >> 8], first=True)
    rng = random.Random(7)
    for _ in range(3000):
        kills, money = rng.randrange(65536), rng.randrange(65536)
        galaxy, flags = rng.randrange(8), rng.randrange(256)
        m.poke_word('CombatScoreLow', kills)
        m.poke('CurrentGalaxy', galaxy)
        m.poke('CommanderFlags', flags)
        m.poke_word('CashHigh', money)
        m.call(entry, stop=stop, f=rng.randrange(256))
        expect((m.pair('hl'), m.pair('de')) == security_model(kills, galaxy, flags, money), kills, galaxy, flags, money)
    return 3000


@check('commander', 'galaxy-seed-compare', ['CompareWithGalaxySeeds'], 'R7-tests/check_r7_routines.py',
       'Carry clear exactly when the six bytes at HL equal GalaxySeeds.')
def check_galaxy_seed_compare(ctx):
    m = ctx.machine()
    rng = random.Random(7)
    area = ctx.scratch
    for trial in range(2000):
        seeds = [rng.randrange(256) for _ in range(6)]
        other = list(seeds)
        if trial % 2:
            other[rng.randrange(6)] ^= 1 << rng.randrange(8)
        m.poke('GalaxySeeds', *seeds)
        m.poke(area, *other)
        m.call('CompareWithGalaxySeeds', hl=area, f=0xFF if trial % 3 else 0)
        expect(bool(m.carry()) == (other != seeds), trial)
    return 2000


# ===========================================================================
# dormant: unexecuted bytes kept in the image


@check('dormant', 'download-loader-relocation', ['L_C350', 'L_C3EE'], 'R7-tests/check_dormant_stub.py',
       'The dormant loader at L_C350 starts with DE = BC + $9E and nine "LD HL,n / ADD HL,BC / '
       'LD (HL),E / INC HL / LD (HL),D" relocations; with BC = L_C350 (USR convention) they are '
       'exactly the operands of the nine CALLs to L_C3EE, and there are no other such CALLs.')
def check_download_loader_relocation(ctx):
    image = ctx.pristine
    start, receiver, end = ctx['L_C350'], ctx['L_C3EE'], ctx['L_C40C']

    def word(address):
        return image[address] | image[address + 1] << 8

    expect(list(image[start:start + 5]) == [0x21, 0x9E, 0x00, 0x09, 0xEB] and start + 0x9E == receiver, 'prologue')
    offsets, address = [], start + 5
    while image[address] == 0x21 and list(image[address + 3:address + 7]) == [0x09, 0x73, 0x23, 0x72]:
        offsets.append(word(address + 1))
        address += 7
    expect(len(offsets) == 9, offsets)
    for offset in offsets:
        expect(image[start + offset - 1] == 0xCD and word(start + offset) == receiver, hex(offset))
    calls = [a for a in range(start, end) if image[a] == 0xCD and word(a + 1) == receiver]
    expect([a + 1 - start for a in calls] == offsets, calls)
    return len(offsets)


@check('dormant', 'unused-interrupt-routines',
       ['UnusedEnableInterrupts', 'UnusedSelectInterruptMode1', 'ViewBufferResidueAfterLoader', 'ClearViewBuffer'],
       'integration',
       'UnusedEnableInterrupts (EI, RET) and UnusedSelectInterruptMode1 (IM 1, RET) each follow a RET and '
       'have no reference: no word in the image equals their address and no JR/DJNZ byte pair reaches '
       'them.  Called with interrupts off in IM 2, the first sets IFF and the second selects IM 1; the '
       'other registers and all memory stay unchanged.  Both comparison 48K memory images hold the bytes '
       'from EnableInterruptMode2 to the RET of UnusedSelectInterruptMode1 unchanged, no word $FF53, no '
       'CALL EnableInterruptMode2 (their start-up selects IM 2 inline) and no RET, EI, RET.  '
       'ClearViewBuffer replaces the residue bytes $F3,$AF of ViewBufferResidueAfterLoader with 0.')
def check_unused_interrupt_routines(ctx):
    from skoolkit.simutils import IFF, IM
    from tape import parse
    image, start, end = ctx.pristine, ctx['GameImage'], ctx['GameImageEnd']
    kept = (A, F, B, C, D, E, H, L, IXh, IXl, IYh, IYl)
    cases = 0
    for name, code, state in (('UnusedEnableInterrupts', [0xFB, 0xC9], (1, 2)),
                              ('UnusedSelectInterruptMode1', [0xED, 0x56, 0xC9], (0, 1))):
        address = ctx[name]
        expect(list(image[address - 1:address + len(code)]) == [0xC9] + code, name, 'bytes')
        words = [a for a in range(start, end - 1) if image[a] | image[a + 1] << 8 == address]
        relative = [a for a in range(start, end - 1) if image[a] in (0x10, 0x18, 0x20, 0x28, 0x30, 0x38)
                    and a + 2 + ((image[a + 1] ^ 0x80) - 0x80) == address]
        expect(not words and not relative, name, words, relative)
        m = ctx.machine()
        m.r[IFF], m.r[IM] = 0, 2
        m.set(a=0x12, f=0x34, bc=0x5678, de=0x9ABC, hl=0xDEF0, ix=0x1357, iy=0x2468)
        registers, memory = [m.r[i] for i in kept], list(m.memory)
        m.call(name)
        stack = range(ctx.test_stack - 2, ctx.test_stack)
        expect([m.r[i] for i in kept] == registers and (m.r[IFF], m.r[IM]) == state, name, 'effect')
        expect(all(m.memory[a] == memory[a] for a in range(0x4000, 0x10000) if a not in stack), name, 'memory')
        cases += 1
    here, unused = ctx['EnableInterruptMode2'], ctx['UnusedSelectInterruptMode1']
    select_im2 = bytes(image[here:here + 6])                       # LD A,$FD / LD I,A / IM 2
    for name in ('Elite+48K+fixed+A+-+Krait.tap', 'Elite+48K+fixed+B+-+Adder.tap'):
        old = bytes(0x4000) + parse((ROOT / 'assets' / name).read_bytes())[2].payload
        expect(old[here:unused + 3] == bytes(image[here:unused + 3]), name, 'interrupt helpers')
        expect(bytes([unused & 255, unused >> 8]) not in old[0x4000:], name, 'word $FF53')
        expect(bytes([0xCD, here & 255, here >> 8]) not in old, name, 'CALL EnableInterruptMode2')
        inline = [a for a in range(0x4000, len(old) - 6) if old[a:a + 6] == select_im2 and a != here]
        expect(len(inline) == 1 and old[inline[0] + 6] == 0xC3, name, 'inline IM 2', inline)
        expect(b'\xC9\xFB\xC9' not in old, name, 'RET, EI, RET')
        cases += 1
    residue = ctx['ViewBufferResidueAfterLoader']
    m = ctx.machine()
    expect(list(m.memory[residue:residue + 2]) == [0xF3, 0xAF], 'residue bytes')
    m.call('ClearViewBuffer')
    expect(list(m.memory[residue:residue + 2]) == [0, 0], 'residue cleared')
    return cases + 1


# ===========================================================================
# missions: hyperspace arrival tail, energy bomb exemption, special encounter

THARGOID, SIDEWINDER, ASP_MK_II = 15, 16, 13                            # blueprint IDs (docs/SHIPS.md)


def blueprint_headers(ctx):
    table = ctx['ShipBlueprintTable']
    return [ctx.pristine[table + 4 * n + 1] | ctx.pristine[table + 4 * n + 2] << 8
            for n in range(ctx['ShipBlueprintCount'])]


@check('missions', 'hyperspace-arrival', ['L_D7B4', 'FinishHyperspaceArrival', 'TriggerFuelLeak'],
       'R8-tests/test_arrival.py',
       'Outside galaxy 0 the arrival tail increments JumpCounter and triggers mission bit 0 at a low '
       'byte >= $20 (L_A843 = 1, red view, fuel leak only with fuel), bit 1 at >= $80 and bit 2 at '
       '>= $FE (L_A871 = 1), only for the first clear bit; otherwise pirates board when AuxRandomSeed '
       '<= 7 - government (station +$1D bit 7 cleared); mission-3 states 1->2, 4->3, station +$26 bit 7 '
       '-> 5, 1..4 -> 4 at the galaxy-seed system; galaxy 0 skips all of it.  FillViewAttributes '
       '(HALT-based flash) is stubbed with an emulated RET that records its colour, as in the original.')
def check_hyperspace_arrival(ctx):
    """Stub (as in the original annotation test): FillViewAttributes is skipped with an emulated
    RET that records its colour argument L, because the flash HALTs."""
    m = ctx.machine()
    station = ctx['InitialRuntimeState']
    roll, flags26 = station + INSTANCE_ROLL, station + INSTANCE_FLAGS26

    def arrive(galaxy=1, jumps=0, flags=0, m3=0, rnd=0xFF, gov=0, fuel=70, roll_byte=0xC0, st26=0x0C):
        m.reset()
        load_jameson(m)
        m.poke('CurrentGalaxy', galaxy)
        m.poke_word('JumpCounter', jumps)
        m.poke('CommanderFlags', flags)
        m.poke('L_A871', m3)
        m.poke('AuxRandomSeed', rnd)
        m.poke('CurrentGovernment', gov)
        m.poke('FuelLevel', fuel)
        m.poke(roll, roll_byte)
        m.poke(flags26, st26)
        flashes = []
        m.call('L_D7B4', limit=200_000, stubs={'FillViewAttributes': lambda mm: flashes.append(mm.reg('l'))},
               **FRESH_REGISTERS)
        return dict(jumps=m.word('JumpCounter'), flags=m.byte('CommanderFlags'), m3=m.byte('L_A871'),
                    m1=m.byte('L_A843'), fuel=m.byte('FuelLevel'), roll=m.byte(roll), leak=m.byte('FuelLeakMessage'),
                    screen=m.byte('CurrentScreenId'), asp=m.byte('MissionAspEncounterState'), flashes=flashes,
                    st26=m.byte(flags26))

    cases = 0
    for jumps in (0x1F, 0x7F, 0xFD, 0x00):
        out = arrive(galaxy=0, jumps=jumps, rnd=0)
        expect(out['jumps'] == jumps and out['flags'] == 0 and out['roll'] == 0xC0, 'galaxy 0 gate', out)
        cases += 1
    out = arrive(jumps=0x1E)
    expect(out['jumps'] == 0x1F and out['flags'] == 0 and out['m1'] == 0, out)
    out = arrive(jumps=0x1F)
    expect(out['jumps'] == 0x20 and out['flags'] == 1 and out['m1'] == 1 and out['fuel'] == 0 and
           out['leak'] & 0x80 and out['flashes'] == [2], 'mission 1', out)
    out = arrive(jumps=0x1F, fuel=0)
    expect(out['flags'] == 1 and not out['leak'] & 0x80, 'no fuel leak without fuel', out)
    expect(arrive(jumps=0x7E, flags=1)['flags'] == 1, 'bit 1 early')
    out = arrive(jumps=0x7F, flags=1)
    expect(out['flags'] == 3 and out['m3'] == 0, 'mission 2', out)
    expect(arrive(jumps=0xFC, flags=3)['flags'] == 3, 'bit 2 early')
    out = arrive(jumps=0xFD, flags=3)
    expect(out['flags'] == 7 and out['m3'] == 1, 'mission 3', out)
    expect(arrive(jumps=0x7F, flags=0)['flags'] == 1, 'first clear bit only')
    out = arrive(jumps=0x11F)
    expect(out['jumps'] == 0x120 and out['flags'] == 1, '16-bit counter, low byte compared', out)
    cases += 9
    for gov in range(8):
        hits = [rnd for rnd in range(256) if arrive(jumps=0x10, rnd=rnd, gov=gov)['roll'] == 0x40]
        expect(hits == list(range(0, 8 - gov)), 'boarding', gov, hits)
        cases += 256
    expect(arrive(jumps=0x1F, rnd=0, gov=0)['roll'] == 0xC0, 'mission trigger skips boarding')
    expect(arrive(jumps=0x10, flags=7, rnd=0, gov=0)['roll'] == 0x40, 'boarding after all missions')
    for before, after in ((1, 2), (2, 2), (3, 3), (4, 3), (0, 0)):
        expect(arrive(m3=before)['m3'] == after, 'mission 3 state', before)
    out = arrive(m3=0, st26=0x8C)
    expect(out['m3'] == 5 and out['st26'] == 0x0C, 'station +$26 bit 7', out)
    cases += 8

    def arrive_home(m3):
        m.reset()
        load_jameson(m)
        m.poke('CurrentGalaxy', 1)
        m.poke('L_A871', m3)
        m.poke('AuxRandomSeed', 0xFF)
        seeds = ctx['GalaxySeeds']
        m.poke('CurrentSystemSeeds', *m.memory[seeds:seeds + 6])
        m.poke('ChartCursorX', m.byte(seeds + 3), m.byte(seeds + 1))   # copied to the current x/y first
        m.call('L_D7B4', **FRESH_REGISTERS)
        return m.byte('L_A871')

    expect([arrive_home(state) for state in range(6)] == [0, 4, 4, 4, 4, 4], 'galaxy-seed system')
    out = arrive(galaxy=0)
    expect(out['screen'] == 0 and out['asp'] == 0, 'common exit')
    return cases + 7


@check('missions', 'energy-bomb-exemption', ['UpdateObjects'], 'R8-tests/test_bomb.py',
       'With EnergyBombPending the next UpdateObjects explodes active slots unless IY still holds a '
       'Thargoid blueprint from the previous slot: the ship after a Thargoid is spared, the Thargoid '
       'itself is not.')
def check_energy_bomb_exemption(ctx):
    m = ctx.machine()
    state, size = ctx['InitialRuntimeState'], ctx['InstanceSize']

    def frame(order, iy_id):
        m.reset()
        load_jameson(m)
        for slot, ship in enumerate(order, start=1):
            m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=ship, ix=state + size * slot))
        m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=iy_id, ix=state + size * 6))
        iy = m.iy()
        m.poke(state + size * 6 + ctx['InstanceEnergy'], 0)               # slot 6 free again
        m.poke('EnergyBombPending', 1)
        m.poke('ObjectUpdateCounter', 9)          # keep the random-encounter dispatch away
        m.poke('CurrentScreenId', 0x0B)           # non-flight screen: no drawing
        m.call('UpdateObjects', limit=5_000_000, **dict(FRESH_REGISTERS, iy=iy))
        return [m.byte(state + size * slot + INSTANCE_STATE) & 0x30 for slot in range(1, len(order) + 1)]

    golden = {((THARGOID, SIDEWINDER), SIDEWINDER): [0x20, 0x00], ((THARGOID, SIDEWINDER), THARGOID): [0x20, 0x00],
              ((SIDEWINDER, THARGOID), SIDEWINDER): [0x20, 0x20], ((SIDEWINDER, THARGOID), THARGOID): [0x20, 0x20]}
    for (order, iy_id), expected in golden.items():
        expect(frame(order, iy_id) == expected, order, iy_id, frame(order, iy_id))
    return len(golden)


@check('missions', 'special-encounter', ['SpawnRandomEncounter', 'L_F655'], 'R11-tests/check_input.py',
       'Mission-2 special encounter (CommanderFlags bit 1): with free slots an Asp Mk II with +$20 = '
       '$C5, +$25 = $7F, +$26 = $40 and two Sidewinders are created and MissionAspEncounterState = 1; '
       'with all six slots occupied the code pops AF and continues in the ROM at $0F02 (documented bug).')
def check_special_encounter(ctx):
    m = ctx.machine()
    state, size = ctx['InitialRuntimeState'], ctx['InstanceSize']
    headers = blueprint_headers(ctx)
    created = None
    for occupied in (False, True):
        m.reset()
        for name in ('L_A830', 'L_A833', 'L_A837', 'MissionAspEncounterState'):
            m.poke(name, 0)
        m.poke('CommanderFlags', 0x02)
        for slot in range(1, 7):
            m.poke(state + slot * size + ctx['InstanceEnergy'], 0x50 if occupied else 0)
        m.poke('RandomSeed', 1, 0)
        visited = m.call('SpawnRandomEncounter', record=True, rom_exit=True, limit=200_000, **FRESH_REGISTERS)
        expect(m.byte('MissionAspEncounterState') == 1, 'state', occupied)
        if occupied:
            expect(m.r[PC] == 0x0F02 and ctx['L_F655'] not in visited, 'full slots', hex(m.r[PC]))
        else:
            expect(m.r[PC] == RETURN_SENTINEL and ctx['L_F655'] in visited, 'free slots', hex(m.r[PC]))
            created = []
            for slot in range(1, 7):
                instance = state + slot * size
                if m.byte(instance + ctx['InstanceEnergy']):
                    created.append((slot, m.word(instance + INSTANCE_BLUEPRINT), m.byte(instance + INSTANCE_STATE),
                                    m.byte(instance + INSTANCE_FLAGS25), m.byte(instance + INSTANCE_FLAGS26)))
            expect(created == [(1, headers[ASP_MK_II], 0xC5, 0x7F, 0x40), (2, headers[SIDEWINDER], 0x41, 0x7E, 0),
                               (3, headers[SIDEWINDER], 0x41, 0x7E, 0)], created)
    return 2


# ===========================================================================
# input: keyboard and joystick scanning

KEY_ROWS = {  # half-row port high byte -> keys for bits 0..4
    0xFE: ['CAPS', 'Z', 'X', 'C', 'V'], 0xFD: ['A', 'S', 'D', 'F', 'G'],
    0xFB: ['Q', 'W', 'E', 'R', 'T'], 0xF7: ['1', '2', '3', '4', '5'],
    0xEF: ['0', '9', '8', '7', '6'], 0xDF: ['P', 'O', 'I', 'U', 'Y'],
    0xBF: ['ENTER', 'L', 'K', 'J', 'H'], 0x7F: ['SPACE', 'SYM', 'M', 'N', 'B']}
KEYBOARD_PORT, KEMPSTON_PORT = 0xFE, 0x1F


class InputPorts:
    """SkoolKit tracer answering IN from the keyboard half-rows and the Kempston port."""

    def __init__(self):
        self.keys, self.kempston = set(), 0xFF

    def read_port(self, registers, port):
        if port & 0xFF == KEMPSTON_PORT:
            return self.kempston
        if port & 0xFF != KEYBOARD_PORT:
            return 0xFF
        value = 0xFF
        for row, names in KEY_ROWS.items():
            if not (port >> 8) & ~row & 0xFF:
                for bit, name in enumerate(names):
                    if name in self.keys:
                        value &= ~(1 << bit)
        return value


@check('input', 'scan-keyboard', ['ScanKeyboard', 'RecordKeyPress', 'KeyCharacterTable', 'KeyActionTable'],
       'R11-tests/check_input.py',
       'Each of the 40 keys alone gives its KeyCharacterTable code in LastKeyCode and its documented '
       'KeyFlags bit; no key gives $FF, CAPS+0 gives $FE; Kempston, Cursor and Sinclair directions '
       'and fire map to KeyFlagsFlight/KeyFlagsCombat; keyboard ghost keys are suppressed.')
def check_scan_keyboard(ctx):
    m = ctx.machine()
    ports = InputPorts()
    m.sim.set_tracer(ports)
    state = ctx['KeyFlagsScreens']
    options, last = ctx['ControlOptions'] - state, ctx['LastKeyCode'] - state
    codes = {'CAPS': 0, 'SYM': 1, 'ENTER': 13, 'SPACE': 32}
    flags = {'CAPS': {2: 0x80}, 'X': {1: 0x04}, 'C': {3: 0x80}, 'A': {3: 0x01}, 'S': {1: 0x08}, 'D': {4: 0x20},
             'F': {3: 0x04}, 'G': {2: 0x20}, 'Q': {3: 0x40}, 'W': {3: 0x20}, 'E': {3: 0x10}, 'R': {4: 0x40},
             'T': {3: 0x02}, '1': {2: 0x01}, '2': {2: 0x02}, '3': {2: 0x04}, '4': {2: 0x08}, '5': {7: 0x02},
             '9': {7: 0x01}, '8': {7: 0x04}, '7': {7: 0x10}, '6': {7: 0x08}, 'P': {0: 0x08}, 'O': {0: 0x10},
             'I': {0: 0x20}, 'U': {3: 0x08}, 'Y': {0: 0x80}, 'ENTER': {0: 0x01}, 'L': {0: 0x02},
             'K': {0: 0x04}, 'J': {2: 0x40}, 'H': {2: 0x10}, 'SPACE': {1: 0x10}, 'SYM': {1: 0x20},
             'M': {1: 0x02}, 'N': {1: 0x01}, 'B': {4: 0x10}}

    def scan(keys, device=0, kempston=0xFF):
        m.clear(state, 8)
        m.poke(state + options, 0x8C & 0xFC | device)
        m.poke(state + last, 0x55)
        ports.keys, ports.kempston = set(keys), kempston
        m.call('ScanKeyboard')
        return {i: m.byte(state + i) for i in range(8) if m.byte(state + i) and i not in (options, last)}

    cases = 0
    for names in KEY_ROWS.values():
        for name in names:
            got = scan({name})
            expect(m.byte('LastKeyCode') == codes.get(name, ord(name[0])), 'code', name)
            expect(got == flags.get(name, {}), 'flags', name, got)
            cases += 1
    scan({'CAPS', '0'})
    expect(m.byte('LastKeyCode') == 0xFE and m.byte('KeyFlagsScreens') == 0, 'CAPS+0')
    scan(set())
    expect(m.byte('LastKeyCode') == 0xFF, 'no key')
    devices = [((1, (), 0x02), (0x01, 0x00)), ((1, (), 0x10), (0x00, 0x01)), ((2, ('5',), 0xFF), (0x01, 0x00)),
               ((2, ('0',), 0xFF), (0x00, 0x01)), ((3, ('6',), 0xFF), (0x01, 0x00)), ((3, ('9',), 0xFF), (0x08, 0x00)),
               ((2, ('7',), 0xFF), (0x08, 0x00)), ((1, (), 0x01), (0x02, 0x00)), ((1, (), 0x08), (0x08, 0x00))]
    for (device, keys, kempston), expected in devices:
        scan(keys, device, kempston)
        expect((m.byte('KeyFlagsFlight'), m.byte('KeyFlagsCombat')) == expected, device, keys, hex(kempston))
    scan({'N', 'CAPS', 'F', 'C'})
    expect((m.byte('KeyFlagsFlight'), m.byte('KeyFlagsViews'), m.byte('KeyFlagsCombat')) == (0x01, 0x00, 0x00),
           'ghost-key suppression')
    return cases + 2 + len(devices) + 1


# ===========================================================================
# pipeline (continued): object projection against a float model


def sm_byte_unit(value):
    """Float in [-1, 1] -> sign-magnitude byte with unit 127."""
    return min(127, int(round(abs(value) * 127))) | (0x80 if value < 0 else 0)


@check('pipeline', 'object-projection', ['DrawObjectInView', 'BuildRotationMatrix', 'ComputeFaceVisibility',
                                         'ProjectVertices'], 'R9-tests/test_pipeline.py',
       'DrawObjectInView on real blueprints in all four views (120 random cases, fixed seed): the third '
       'orientation vector is B x A / 128 within 1 unit, RotationMatrix rows are (X_r, Y_r, Z_r), '
       'ObjectViewDepth is the depth class, 1341 of 1353 face flags match the float model (the rest '
       'are near-zero or small-normal cases) and 1287 of 1292 projected vertices lie within 4 units.')
def check_object_projection(ctx):
    m = ctx.machine()
    ram = m.memory
    instance = ctx['InitialRuntimeState'] + ctx['InstanceSize']
    vbuf, faces_flags, matrix = ctx['ProjectedVertexBuffer'], ctx['FaceVisibilityFlags'], ctx['RotationMatrix']
    vsize = faces_flags - vbuf                                     # 46 three-byte entries
    expect(vsize == 138, vsize)
    headers = blueprint_headers(ctx)
    rng = random.Random(7)

    def random_frame():
        while True:
            a = [rng.uniform(-1, 1) for _ in range(3)]
            n = math.sqrt(sum(x * x for x in a))
            if n > 0.2:
                break
        a = [x / n for x in a]
        while True:
            r = [rng.uniform(-1, 1) for _ in range(3)]
            dot = sum(x * y for x, y in zip(r, a))
            r = [x - dot * y for x, y in zip(r, a)]
            n = math.sqrt(sum(x * x for x in r))
            if n > 0.2:
                break
        return a, [x / n for x in r]

    def records(bp, kind):
        count = ram[bp + {'v': BLUEPRINT_VERTEX_COUNT, 'f': BLUEPRINT_FACE_COUNT}[kind]]
        table = bp + {'v': BLUEPRINT_VERTEX_TABLE, 'f': BLUEPRINT_FACE_TABLE}[kind]
        offset = ram[table] + 256 * ram[table + 1]
        size = 6 if kind == 'v' else 4
        out = []
        for k in range(count):
            row = ram[bp + offset + size * k:bp + offset + size * (k + 1)]
            out.append(([(-row[i] if row[3] & (0x80 >> i) else row[i]) for i in range(3)], row))
        return out

    def run_case(ship, pos, screen):
        a, b = random_frame()
        bp = headers[ship]
        inst = [0] * ctx['InstanceSize']
        for i, v in enumerate(pos):
            inst[3 * i], inst[3 * i + 1], inst[3 * i + 2] = abs(v) & 255, abs(v) >> 8, 0x80 if v < 0 else 0
        for i in range(3):
            inst[ctx['InstanceAxisZ'] + 1 + 2 * i] = sm_byte_unit(a[i])
            inst[ctx['InstanceAxisY'] + 1 + 2 * i] = sm_byte_unit(b[i])
        inst[ctx['InstanceEnergy']] = 100
        inst[INSTANCE_BLUEPRINT], inst[INSTANCE_BLUEPRINT + 1] = bp & 255, bp >> 8
        ram[instance:instance + len(inst)] = inst
        ram[ctx['CurrentScreenId']] = screen
        ram[ctx['ViewBitmapBuffer']:ctx['ViewBitmapBuffer'] + VIEW_SIZE] = [0] * VIEW_SIZE
        ram[vbuf:vbuf + vsize] = [0xEE] * vsize                  # poison: untouched entries stay $EE
        m.call('DrawObjectInView', limit=3_000_000, ix=instance, iy=bp, a=0, f=0, bc=0, de=0, hl=0)
        inst = ram[instance:instance + ctx['InstanceSize']]
        A = [sm8(inst[ctx['InstanceAxisZ'] + 1 + 2 * i]) for i in range(3)]
        B = [sm8(inst[ctx['InstanceAxisY'] + 1 + 2 * i]) for i in range(3)]
        X = [sm8(inst[ctx['InstanceAxisX'] + 1 + 2 * i]) for i in range(3)]
        cross = [(B[1] * A[2] - B[2] * A[1]) / 128, (B[2] * A[0] - B[0] * A[2]) / 128,
                 (B[0] * A[1] - B[1] * A[0]) / 128]
        cross_error = max(abs(x - y) for x, y in zip(X, cross))
        matrix_ok = all(ram[matrix + 6 * r + 1] == inst[ctx['InstanceAxisX'] + 1 + 2 * r] and
                        ram[matrix + 6 * r + 3] == inst[ctx['InstanceAxisY'] + 1 + 2 * r] and
                        ram[matrix + 6 * r + 5] == inst[ctx['InstanceAxisZ'] + 1 + 2 * r] for r in range(3))
        scale = ram[bp + BLUEPRINT_NORMAL_SHIFT]
        depth16 = abs(pos[2] if screen in (0, 1) else pos[0])
        doubled = depth16 * 2
        depth_class = max(0, (0x1F if doubled > 0xFFFF or (doubled >> 8) >= 0x1F else doubled >> 8) - 2)
        if ram[matrix + 1] != inst[ctx['InstanceAxisX'] + 1] or all(ram[vbuf + i] == 0xEE for i in range(vsize)):
            return None
        expect(ram[ctx['ObjectViewDepth']] == depth_class, 'ObjectViewDepth', ram[ctx['ObjectViewDepth']], depth_class)
        face_result = Counter()
        P = list(pos)
        for f, (normal, row) in enumerate(records(bp, 'f')):
            if (row[3] & 0x1F) != 0x1F and depth_class >= (row[3] & 0x1F):
                face_result['distance-hidden' if ram[faces_flags + f] == 0 else 'MISMATCH-dist'] += 1
                continue
            n = [sum(normal[k] * [X, B, A][k][axis] for k in range(3)) / 256 for axis in range(3)]
            q = [P[i] + 2 * n[i] / (2 ** scale) for i in range(3)]
            dot = sum(n[i] * q[i] for i in range(3))
            tolerance = 0.02 * sum(abs(n[i] * q[i]) for i in range(3)) + 64
            if ram[faces_flags + f] == (1 if dot < 0 else 0):
                face_result['match'] += 1
            else:
                face_result['near-zero' if abs(dot) <= tolerance else 'MISMATCH'] += 1
        vertex_result, errors = Counter(), []
        for k, (vector, row) in enumerate(records(bp, 'v')):
            entry = ram[vbuf + 3 * k:vbuf + 3 * k + 3]
            if entry == [0xEE] * 3:
                vertex_result['skipped'] += 1
                continue
            w = [P[i] + 2 * sum(vector[j] * [X, B, A][j][i] for j in range(3)) / 256 for i in range(3)]
            hz, vz, depth = (w[0], w[1], w[2]) if screen in (0, 1) else (w[2], w[1], w[0])
            if (depth < 0) != (screen in (1, 2)):
                vertex_result['behind-ok' if entry[2] == 0xFF else 'BEHIND-MISMATCH'] += 1
                continue
            h, v = min(255, 256 * abs(hz) / abs(depth)), min(255, 256 * abs(vz) / abs(depth))
            quadrant = ((1 if hz < 0 else 0) ^ (1 if screen in (1, 3) else 0)) << 1 | (1 if vz < 0 else 0)
            dh, dv = entry[0] - h, entry[1] - v
            errors.append(max(abs(dh), abs(dv)))
            quadrant_ok = entry[2] == quadrant or (abs(hz) < 3 and (entry[2] & 1) == (quadrant & 1)) or \
                (abs(vz) < 3 and (entry[2] & 2) == (quadrant & 2))
            vertex_result['ok' if abs(dh) <= 4 and abs(dv) <= 4 and quadrant_ok else 'MISMATCH'] += 1
        return cross_error, matrix_ok, face_result, vertex_result, errors

    totals, faces = Counter(), Counter()
    worst_cross, matrix_bad = 0.0, 0
    for case in range(120):
        ship = rng.choice((9, 13, 0, 6, 14, 15))
        screen = rng.choice((0, 0, 1, 2, 3))
        depth = rng.randint(0x0500, 0x1400) if case % 2 else rng.randint(0x0100, 0x0280)
        side = [rng.randint(-depth // 3, depth // 3) for _ in range(2)]
        pos = {0: (side[0], side[1], depth), 1: (side[0], side[1], -depth),
               2: (-depth, side[1], side[0]), 3: (depth, side[1], side[0])}[screen]
        out = run_case(ship, pos, screen)
        if out is None:
            totals['not-wireframe'] += 1
            continue
        cross_error, matrix_ok, face_result, vertex_result, _ = out
        worst_cross = max(worst_cross, cross_error)
        matrix_bad += not matrix_ok
        totals.update(vertex_result)
        faces.update(face_result)
    expect(worst_cross <= 1 and matrix_bad == 0, 'cross product / matrix', worst_cross, matrix_bad)
    expect(dict(faces) == {'match': 1341, 'MISMATCH': 9, 'distance-hidden': 19, 'near-zero': 3}, 'faces', dict(faces))
    expect(dict(totals) == {'ok': 1287, 'skipped': 805, 'not-wireframe': 7, 'MISMATCH': 5}, 'vertices', dict(totals))
    return 120, dict(faces=dict(sorted(faces.items())), vertices=dict(sorted(totals.items())),
                     worst_cross_error=worst_cross)


# --- BEGIN P6 CHECKS ---
# Pass-2 checks of the docked-screen helpers in $B000..$BDFF (tools/annotations/r6_b000.py).
# Key input is scripted by stubbing WaitForKeyPress; screens/messages the routines hand over
# to are stubbed and recorded, so each check observes only the routine's own decisions.

P6_ENTER, P6_DELETE = 0x0D, 0xFE


def p6_keys(sequence):
    """WaitForKeyPress stub that returns the scripted key codes in order."""
    keys = [ord(k) if isinstance(k, str) else k for k in sequence]

    def press(mm):
        assert keys, 'key script exhausted'
        mm.r[A] = keys.pop(0)
    return press, keys


def p6_sound_off(m):
    m.poke('ControlOptions', m.byte('ControlOptions') & 0x7F)    # bit 7 clear: no ROM BEEPER


@check('economy', 'p6-select-system-at-cursor', ['SelectSystemAtCursor', 'PrintSelectedSystemSummary'],
       'pass2',
       'The chart key handler SelectSystemAtCursor selects the system nearest the cursor: (3, 92) -> '
       'TIBEDIED at (2, 90), 17.6 light years from LAVE; (21, 171) -> LAVE at (20, 173), distance 0 '
       '(no distance line).  The name is printed in capitals on prompt row 21.')
def check_p6_select_system_at_cursor(ctx):
    t = TextMachine(ctx)
    m = t.m
    cases = 0
    for cursor, name, position, distance in (((3, 92), 'TIBEDIED', (2, 90), 176),
                                             ((21, 171), 'LAVE', (20, 173), 0)):
        t.fresh(row=5)
        galactic_chart_state(m)
        p6_sound_off(m)
        m.poke('CurrentScreenId', 0)                 # not a chart screen: no cross-hair drawing
        m.poke('ChartCursorX', *cursor)
        out = []
        m.call('SelectSystemAtCursor', halt=True, limit=5_000_000,
               hooks={'PutCharacter': lambda mm: out.append(chr(mm.reg('a')))},
               a=0, f=0, bc=0, de=0, hl=0, ix=0, iy=ROM_IY)
        text = ''.join(out)
        expect(m.text('SelectedSystemName') == name, name, m.text('SelectedSystemName'))
        expect((m.byte('ChartCursorX'), m.byte('ChartCursorY')) == position, name, 'cursor')
        expect(m.word('SelectedSystemDistance') == distance, name, m.word('SelectedSystemDistance'))
        expect(text.startswith(name), name, text)
        expect(('17.6' in text) == (distance == 176), name, text)
        cases += 1
    return cases


@check('text', 'p6-unreachable-byte', ['L_B93F', 'SetLowerCase'], 'pass2',
       'The $C9 byte at L_B93F is unreachable: no little-endian word in the image equals its '
       'address, no JR/DJNZ targets it, and the instruction before it is the unconditional JR '
       'of SetLowerCase.')
def check_p6_unreachable_byte(ctx):
    image, base, target = ctx.image, ctx['GameImage'], ctx['L_B93F']
    expect(ctx.pristine[target] == RET, 'not a RET opcode')
    words = [base + i for i in range(len(image) - 1) if image[i] | image[i + 1] << 8 == target]
    expect(not words, 'word references', words)
    relative = [base + i for i in range(len(image) - 1)
                if image[i] in (0x10, 0x18, 0x20, 0x28, 0x30, 0x38)
                and base + i + 2 + ((image[i + 1] ^ 0x80) - 0x80) == target]
    expect(not relative, 'relative branches', relative)
    jr = target - 2
    expect(ctx.pristine[jr] == 0x18 and ctx['SetLowerCase'] < jr and ctx['SetCapitals'] == target + 1,
           'preceding unconditional JR')
    return 3


@check('text', 'p6-input-quantity', ['InputQuantity', 'L_B32B', 'AcceptQuantity'], 'pass2',
       'InputQuantity: the handler runs after every digit with EnteredNumber 1..99; a second digit '
       'or a delete first undoes the previous attempt (RestoreTradeState); Enter first -> carry, '
       'A = 2; a non-digit key -> carry, A = key, without undoing a one-digit attempt; codes below '
       "'1' (first) or '0' (second) and an early delete are ignored; a refusing handler -> carry, A = 1.")
def check_p6_input_quantity(ctx):
    m = ctx.machine()
    refuse = ctx.scratch                              # harness handler: SCF; LD A,1; RET
    cases = [(['5', P6_ENTER], 'AcceptQuantity', (0, None, 5), [5], 0),
             (['1', '2'], 'AcceptQuantity', (0, None, 12), [1, 12], 1),
             ([P6_ENTER], 'AcceptQuantity', (1, 2, 0), [], 0),
             (['0', P6_DELETE, ' ', '7', P6_ENTER], 'AcceptQuantity', (0, None, 7), [7], 0),
             (['3', 'X'], 'AcceptQuantity', (1, ord('X'), 3), [3], 0),
             (['4', P6_DELETE, '6', '0'], 'AcceptQuantity', (0, None, 60), [4, 6, 60], 2),
             (['9', '/', '8'], 'AcceptQuantity', (0, None, 98), [9, 98], 1),
             (['A'], 'AcceptQuantity', (1, ord('A'), 0), [], 0),
             (['9'], refuse, (1, 1, 9), [9], 0)]
    for keys, handler, (carry, a, number), calls, restores in cases:
        m.reset()
        m.poke(refuse, 0x37, 0x3E, 0x01, RET)
        press, left = p6_keys(keys)
        seen, undo = [], []
        entry = ctx.addr(handler)
        m.call('InputQuantity', limit=200_000,
               stubs={'WaitForKeyPress': press, 'PrintToken': None, 'EraseInputCharacter': None,
                      'RestoreTradeState': lambda mm: undo.append(1)},
               hooks={entry: lambda mm: seen.append(mm.byte('EnteredNumber'))},
               a=0, f=0, bc=0, de=0, hl=entry)
        expect(not left, keys, 'unused keys', left)
        expect(m.carry() == carry and (a is None or m.reg('a') == a), keys, m.carry(), m.reg('a'))
        expect(m.byte('EnteredNumber') == number and seen == calls and len(undo) == restores,
               keys, m.byte('EnteredNumber'), seen, undo)
    return len(cases)


@check('text', 'p6-input-string', ['InputString', 'EraseInputCharacter'], 'pass2',
       "InputString keeps '0'..'9' and '@'..'Z', ignores other codes and a delete on an empty "
       'buffer, deletes the last character, ends on Enter and also on a further character once '
       'the maximum length is reached (that character is dropped); the result is zero-terminated.')
def check_p6_input_string(ctx):
    m = ctx.machine()
    buffer = ctx.scratch
    cases = [(3, ['A', 'B', 'C', 'D'], 'ABC'),
             (8, [P6_DELETE, '$', 'L', 'A', P6_DELETE, 'V', P6_ENTER], 'LV'),
             (8, ['1', '@', '[', ':', 'Z', 'a', P6_ENTER], '1@Z'),
             (8, [P6_ENTER], '')]
    for limit, keys, expected in cases:
        m.reset()
        m.clear(buffer, 16, 0x55)
        m.poke('LastKeyCode', 0xFF)
        press, left = p6_keys(keys)
        m.call('InputString', halt=True, limit=500_000,
               stubs={'WaitForKeyPress': press, 'PrintMessage': None, 'PrintToken': None},
               a=14, f=0, b=limit, c=0, de=0, hl=buffer)
        expect(not left, keys, 'unused keys', left)
        expect(m.text(buffer, 16) == expected and m.byte(buffer + len(expected)) == 0 and
               m.byte('InputLength') == len(expected), keys, m.text(buffer, 16))
    return len(cases)


@check('economy', 'p6-nova-cargo-screens', ['BuyCargoScreen', 'SellCargoScreen'], 'pass2',
       "BuyCargoScreen with L_A843 set: 'Y' empties the hold, sets LargeCargoBayFitted ('Y'), free "
       'space 0 and CommanderFlags bit 5 (circle $B6/$76/$3D); another key changes nothing; with bit 5 '
       'set the inventory is shown at once.  SellCargoScreen with L_A843 clear and bit 5 set: bit 5 '
       'cleared, CombatScoreHigh + 1, 100 g of gem-stones (CargoHold+15), free space 35; with L_A843 '
       'set it runs SellCargoList.')
def check_p6_nova_cargo_screens(ctx):
    m = ctx.machine()
    hold = ctx['CargoHold']
    cases = 0
    for key, flags in (('Y', 0x00), ('N', 0x00), ('Y', 0x20)):
        m.reset()
        load_jameson(m)
        m.poke('L_A843', 1)
        m.poke('CommanderFlags', flags)
        m.poke(hold, *range(1, 18))
        m.poke('CargoFreeSpace', 7)
        press, left = p6_keys([key])
        shown = []
        m.call('BuyCargoScreen', limit=200_000,
               stubs={'WaitForKeyPress': press, 'ShowColouredMessageScreen': lambda mm: shown.append(mm.reg('d')),
                      'DrawScreenCircle': lambda mm: shown.append((mm.byte('ShapeCentreX'), mm.byte('ShapeCentreY'),
                                                                   mm.byte('ShapeSize'))),
                      'Wait36Frames': None, 'ShowInventory': lambda mm: shown.append('inventory')},
               a=0, f=0, bc=0, de=0, hl=0)
        if flags:
            expect(shown == ['inventory'] and left == [ord('Y')], 'refugees aboard', shown, left)
        else:
            expect(shown == [91, (0xB6, 0x76, 0x3D), 'inventory'], key, shown)
        accepted = key == 'Y' and not flags
        expect((m.memory[hold:hold + 17] == [0] * 17) == accepted and
               (m.byte('CargoFreeSpace') == 0) == accepted and
               (m.byte('LargeCargoBayFitted') == ord('Y')) == accepted and
               bool(m.byte('CommanderFlags') & 0x20) == (accepted or bool(flags)), key, flags)
        cases += 1
    for mission in (0, 1):
        m.reset()
        load_jameson(m)
        m.poke('L_A843', mission)
        m.poke('CommanderFlags', 0x21)
        m.poke('CombatScoreHigh', 5)
        m.poke('CargoFreeSpace', 0)
        visited = []
        m.call('SellCargoScreen', limit=200_000,
               stubs={'ShowMessageScreenAndWait': lambda mm: visited.append(mm.reg('d')),
                      'ShowInventory': lambda mm: visited.append('inventory'),
                      'SellCargoList': lambda mm: visited.append('sell list')},
               a=0, f=0, bc=0, de=0, hl=0)
        if mission:
            expect(visited == ['sell list'] and m.byte('CommanderFlags') == 0x21, visited)
        else:
            expect(visited == [15, 'inventory'] and m.byte('CommanderFlags') == 0x01 and
                   m.byte('CombatScoreHigh') == 6 and m.byte(hold + 15) == 100 and
                   m.byte('CargoFreeSpace') == 35, visited)
        cases += 1
    return cases


@check('economy', 'p6-equipment-purchase', ['BuyEquipmentItem', 'GetEquipmentPriceEntry', 'SubtractCash'],
       'pass2',
       'BuyEquipmentItem item 1 with fuel price 0.5 Cr: L_A843 clear -> fuel 70, cash -0.5, price '
       'cleared; L_A843 set -> fuel unchanged but the 0.5 Cr stays paid.  Item 2 with 4 missiles: '
       '"ALL PRESENT", cash restored.  An item beyond EquipmentItemCount goes to the status screen.')
def check_p6_equipment_purchase(ctx):
    m = ctx.machine()
    cases = 0
    for mission, keys, fuel, cash, after in ((0, ['1', P6_ENTER], 70, 995, 'list'),
                                             (1, ['1', P6_ENTER, 'X'], 30, 995, 'status'),
                                             (0, ['2', P6_ENTER], 30, 1000, 'status'),
                                             (0, ['6', P6_ENTER], 30, 1000, 'status')):
        m.reset()
        load_jameson(m)
        p6_sound_off(m)
        m.poke('L_A843', mission)
        m.poke('FuelLevel', 30)
        m.poke('MissileCount', 4)
        m.poke('L_9237', 5)
        m.poke('EquipmentItemCount', 5)
        m.poke_word('CashHigh', 0)
        m.poke_word('CashLow', 1000)
        m.poke_word('StockPointer', ctx.scratch)
        m.poke_word('CargoPointer', ctx.scratch + 1)
        press, left = p6_keys(keys)
        exits = []
        m.call('BuyEquipmentItem', halt=True, limit=500_000,
               stubs={'WaitForKeyPress': press, 'ShowCashAfterTrade': None,
                      'ShowCommanderStatus': lambda mm: exits.append('status'),
                      'EquipShipScreen': lambda mm: exits.append('list')},
               a=0, f=0, bc=0, de=0, hl=0)
        expect(not left and exits == [after], mission, keys, exits, left)
        expect(m.byte('FuelLevel') == fuel and m.word('CashLow') == cash and m.word('CashHigh') == 0 and
               m.byte('MissileCount') == 4, mission, keys, m.byte('FuelLevel'), m.word('CashLow'))
        if keys[0] == '1' and not mission:
            expect(m.byte('L_9237') == 0, 'fuel price cleared')
        cases += 1
    return cases
# --- END P6 CHECKS ---

# --- BEGIN S1 CHECKS ---
# structures: blueprint header fields and object instance state, proved by their readers


S1_HEADER_SIZE = 23                   # blueprint header bytes (docs/SHIPS.md)
S1_COMMODITY_COUNT = 17               # CargoHold entries; ScoopCargoItem indexes them


class S1Reached(Exception):
    """Raised by a hook when execution reaches the instruction under test."""


def s1_reaches(m, entry, target, hooks=None, **arguments):
    """True when execution of `entry` reaches `target` before returning."""
    def reached(_machine):
        raise S1Reached()
    hooks = dict(hooks or {})
    hooks[target] = reached
    try:
        m.call(entry, hooks=hooks, **arguments)
    except S1Reached:
        return True
    return False


def s1_headers(ctx):
    """(address, 23 header bytes) of every blueprint in the default image."""
    return [(address, list(ctx.pristine[address:address + S1_HEADER_SIZE]))
            for address in blueprint_headers(ctx)]


def s1_fake_blueprint(m, values):
    """A 23-byte blueprint header in harness RAM with the given {offset: byte} entries."""
    address = m.ctx.scratch
    m.clear(address, S1_HEADER_SIZE)
    for offset, value in values.items():
        m.poke(address + offset, value)
    return address


def s1_instance(m, slot=1):
    return m['InitialRuntimeState'] + slot * m['InstanceSize']


def s1_set_flags(m, zero):
    m.r[F] = (m.r[F] | 0x40) if zero else (m.r[F] & ~0x40)


@check('structures', 's1-blueprint-instance-initialisation', ['InitialiseShipFromBlueprint', 'ShipBlueprintTable'],
       'pass2',
       'For every ID (also with bits 6/7 set in A, and with table bytes 0 and 3 overwritten) IY and '
       'instance +$23 = the table pointer; +$22 = header '
       '+7; +$21 = header +$12 AND $6F; +$20 = $40 | header +$0A bits 0..2 | header +$12 bit 7; +$1B = '
       'header +6 / 2; +$25 = $7E; +$26 = 0; +$1F is not written (template copies +$00..+$1E).')
def check_s1_blueprint_instance_initialisation(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    table, entries = ctx['ShipBlueprintTable'], ctx['ShipBlueprintCount']
    cases = 0
    for blueprint_id, (address, h) in enumerate(s1_headers(ctx)):
        for high_bits in (0x00, 0x40, 0x80, 0xC0):
            m.reset()
            for entry in range(entries):              # bytes 0 ($C3) and 3 (group) are never read
                m.poke(table + 4 * entry, high_bits ^ 0xA5)
                m.poke(table + 4 * entry + 3, high_bits ^ 0x5A)
            m.poke(instance + 0x1F, 0x5A)
            m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=blueprint_id | high_bits, ix=instance))
            expect(m.iy() == address and m.word(instance + INSTANCE_BLUEPRINT) == address, blueprint_id)
            expect(m.byte(instance + 0x22) == h[7], blueprint_id, 'energy')
            expect(m.byte(instance + 0x21) == h[18] & 0x6F, blueprint_id, 'behaviour')
            expect(m.byte(instance + INSTANCE_STATE) == 0x40 | (h[10] & 7) | (h[18] & 0x80), blueprint_id, 'flags')
            expect(m.byte(instance + 0x1B) == h[6] >> 1, blueprint_id, 'speed')
            expect((m.byte(instance + INSTANCE_FLAGS25), m.byte(instance + INSTANCE_FLAGS26)) == (0x7E, 0),
                   blueprint_id)
            expect(m.byte(instance + 0x1F) == 0x5A, blueprint_id, '+$1F written')
            cases += 1
    return cases


@check('structures', 's1-blueprint-ai-laser-chance', ['TryFireAiLaser'], 'pass2',
       'A hostile ship passes the random firing gate when NextRandomByte < header +2, halved (SRL) '
       'while CombatScoreHigh = 0 (kill count below 256); every real header value and 0/1/$FF.')
def check_s1_blueprint_ai_laser_chance(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    after_gate = ctx.find('TryFireAiLaser', ctx['TryFireAiLaser'] + 0x30,
                          [0xDD, 0x7E, INSTANCE_FLAGS26, 0xE6, 0x0F])    # LD A,(IX+$26) / AND $0F
    values = sorted({h[2] for _, h in s1_headers(ctx)} | {0x00, 0x01, 0xFF})
    random_value = [0]
    cases = 0
    for chance in values:
        for high in (0, 1):
            m.reset()
            blueprint = s1_fake_blueprint(m, {2: chance})
            m.poke(instance + 0x21, 0x04)                     # hostile
            m.poke(instance + 0x08, 0x00)
            m.poke(instance + 0x0E, 0x80)                     # facing test passes
            m.poke(instance + INSTANCE_FLAGS26, 0x01)         # returns right after the gate
            m.poke('CombatScoreHigh', high)
            limit = chance if high else chance >> 1
            for value in range(256):
                random_value[0] = value
                passed = s1_reaches(m, 'TryFireAiLaser', after_gate, ix=instance, iy=blueprint,
                                    stubs={'NextRandomByte': lambda mm: mm.set(a=random_value[0])})
                expect(passed == (value < limit), chance, high, value)
                cases += 1
    return cases


@check('structures', 's1-blueprint-debris-events', ['L_ECAD', 'DispatchShipEvent', 'SpawnCargoCanister'],
       'pass2',
       'Destroyed by the player: header +0 low nibble nonzero -> event 6, else header +7 >= 85 -> event 5, '
       'else +7 = 60 with damage 50 -> event 8, else none.  With the real dispatcher every cargo-carrying '
       'blueprint (low nibble 1, 2, 3, 5 or 7) creates exactly one Cargo canister (+$26 = $0A).')
def check_s1_blueprint_debris_events(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    events = []
    cases = 0
    for cargo in range(256):
        for energy in ((100,) if cargo & 0x0F else range(256)):
            for damage in ((15,) if cargo & 0x0F else (15, 23, 50)):
                m.reset()
                blueprint = s1_fake_blueprint(m, {0: cargo, 7: energy})
                m.poke_word(instance + INSTANCE_BLUEPRINT, blueprint)
                events.clear()
                m.call('L_ECAD', stop='DrawLaser', ix=instance, c=damage,
                       stubs={'DispatchShipEvent': lambda mm: events.append(mm.reg('a'))})
                if cargo & 0x0F:
                    expected = [6]
                elif energy >= 85:
                    expected = [5]
                elif energy == 60 and damage == 50:
                    expected = [8]
                else:
                    expected = []
                expect(events == expected, cargo, energy, damage, events)
                cases += 1
    headers = s1_headers(ctx)
    canister = headers[4][0]
    size, state = ctx['InstanceSize'], ctx['InitialRuntimeState']
    carriers = [n for n, (_, h) in enumerate(headers) if h[0] & 0x0F]
    expect(sorted({headers[n][1][0] & 0x0F for n in carriers}) == [1, 2, 3, 5, 7], carriers)
    for blueprint_id in carriers:
        m.reset()
        load_jameson(m)
        m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=blueprint_id, ix=instance))
        m.call('L_ECAD', stop='DrawLaser', **dict(FRESH_REGISTERS, ix=instance, c=15))
        created = [slot for slot in range(2, 7) if m.byte(state + slot * size + 0x22)]
        expect(len(created) == 1, blueprint_id, created)
        child = state + created[0] * size
        expect(m.word(child + INSTANCE_BLUEPRINT) == canister and m.byte(child + INSTANCE_FLAGS26) == 0x0A,
               blueprint_id)
        cases += 1
    return cases


@check('structures', 's1-blueprint-scoop-and-radius', ['L_EA51', 'ScoopCargoItem'], 'pass2',
       'Proximity box: every |x|,|y|,|z| must be below header +1 (+256 for a player-targeting missile, 180 '
       'for a scoopable +$26 bit 1 object).  Scooped: commodity = header +0 high nibble + 1, or a random '
       '0..7 when it is 0, or $FF (cloaking device) once MissionAspEncounterState = 3; real blueprints '
       'give SLAVES, ALLOYS, MINERALS and ALIEN ITEMS.')
def check_s1_blueprint_scoop_and_radius(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    outcome = []
    stubs = {'L_EB23': lambda mm: outcome.append('collision'), 'L_EAD8': lambda mm: outcome.append('dock'),
             'L_EB65': None, 'ScoopCargoItem': lambda mm: outcome.append(mm.reg('a'))}
    random_value = [0]
    stubs['NextRandomByte'] = lambda mm: mm.set(a=random_value[0])

    def place(magnitudes, flags26, flags25=0x7E, y_negative=False):
        m.clear(instance, 9)
        for axis, value in enumerate(magnitudes):
            m.poke(instance + 3 * axis, value & 255, value >> 8, 0)
        if y_negative:
            m.poke(instance + 5, 0x80)
        m.poke(instance + INSTANCE_FLAGS26, flags26)
        m.poke(instance + INSTANCE_FLAGS25, flags25)

    cases = 0
    radii = sorted({h[1] for _, h in s1_headers(ctx)} | {1, 255})
    for radius in radii:
        m.reset()
        blueprint = s1_fake_blueprint(m, {1: radius})
        for limit, flags26, flags25 in ((radius, 0x00, 0x7E), (radius + 256, 0x01, 0x00), (radius, 0x01, 0x03),
                                        (180, 0x02, 0x7E)):
            for axis in range(3):
                for value in (limit - 1, limit):
                    magnitudes = [0, 0, 0]
                    magnitudes[axis] = value
                    place(magnitudes, flags26, flags25)
                    outcome.clear()
                    m.call('L_EA51', ix=instance, iy=blueprint, stubs=stubs)
                    near = value < limit
                    expect(bool(outcome) == near, radius, limit, axis, value, outcome)
                    cases += 1
    names = {}
    for nibble in range(16):
        for state in (0, 3):
            for value in (0x00, 0x05, 0xFF):
                m.reset()
                blueprint = s1_fake_blueprint(m, {0: nibble << 4, 1: 20})
                m.poke('FuelScoopsFitted', 1)
                m.poke('CargoFreeSpace', 5)
                m.poke('MissionAspEncounterState', state)
                place([4, 4, 4], 0x0A, y_negative=True)
                m.poke(instance + 0x22, 0x11)
                random_value[0] = value
                outcome.clear()
                m.call('L_EA51', ix=instance, iy=blueprint, stubs=stubs)
                if nibble:
                    expected = nibble + 1
                else:
                    expected = 0xFF if state == 3 else value & 7
                expect(outcome == [expected] and m.byte(instance + 0x22) == 0, nibble, state, value, outcome)
                cases += 1
    for blueprint_id, (_, h) in enumerate(s1_headers(ctx)):
        if h[0] >> 4:
            names[blueprint_id] = h[0] >> 4
    tokens = {2: 3, 3: 9, 5: 12, 18: 16}                 # escape capsule, alloy plate, splinter, Thargon
    expect({n: v + 1 for n, v in names.items()} == tokens, names)
    expect(all(v < S1_COMMODITY_COUNT for v in tokens.values()))
    return cases + len(tokens)


@check('structures', 's1-blueprint-view-distances', ['DrawObjectInView', 'L_E10E'], 'pass2',
       'DrawObjectInView continues past the near test (L_E038) only when the 16-bit depth exceeds header '
       '+1; L_E10E draws the wireframe (L_E175) when the depth high byte is below header +$0B, else a dot.')
def check_s1_blueprint_view_distances(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    cases = 0
    headers = s1_headers(ctx)
    for radius in sorted({h[1] for _, h in headers} | {0, 255}):
        for depth in (radius, radius + 1, radius + 0x100):
            m.reset()
            blueprint = s1_fake_blueprint(m, {1: radius, 11: 0x40})
            m.poke('CurrentScreenId', 0)
            m.clear(instance, 9)
            m.poke(instance + 6, depth & 255, depth >> 8, 0)
            beyond = s1_reaches(m, 'DrawObjectInView', 'L_E038', ix=instance, iy=blueprint)
            expect(beyond == (depth > radius), radius, depth)
            cases += 1
    for distance in sorted({h[11] for _, h in headers} | {0, 1, 255}):
        for high in {max(distance - 1, 0), distance, min(distance + 1, 255)}:
            m.reset()
            blueprint = s1_fake_blueprint(m, {11: distance})
            m.poke_word('ObjectViewDepth', high << 8 | 0x80)
            m.poke('ProjectedX', 0x10)
            m.poke('ProjectedY', 0x10)
            m.poke('ProjectedQuadrant', 0)
            m.poke(instance + INSTANCE_STATE, 0x40)
            wireframe = s1_reaches(m, 'L_E10E', 'L_E175', ix=instance, iy=blueprint)
            expect(wireframe == (high < distance), distance, high)
            cases += 1
    return cases


@check('structures', 's1-blueprint-launch-byte', ['TryLaunchAiPayload'], 'pass2',
       'With a nonzero payload (+$20 bits 0..2) the AI launch event is (header +$0A AND $F0, or 6 when '
       'zero) XOR 4: missile event 2, or event 4 with launch subtype = high nibble; success decrements '
       '+$20 and a missile raises IncomingMissileMessage.  Rock hermit -> $54, Thargoid -> $34.')
def check_s1_blueprint_launch_byte(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    events = []
    cases = 0

    def dispatch(success):
        def stub(mm):
            events.append(mm.reg('a'))
            s1_set_flags(mm, success)
        return stub

    for value in range(256):
        for success in (True, False):
            for payload in (0, 3):
                m.reset()
                blueprint = s1_fake_blueprint(m, {10: value})
                m.poke(instance + INSTANCE_STATE, 0x40 | payload)
                m.poke('EcmTimer', 0)
                m.poke('IncomingMissileMessage', 0)
                events.clear()
                reached = s1_reaches(m, 'TryLaunchAiPayload', 'L_F7DF', ix=instance, iy=blueprint,
                                     stubs={'NextRandomByte': lambda mm: mm.set(a=0x10),
                                            'DispatchShipEventPreservingParent': dispatch(success)})
                expect(reached, value)
                expected = ((value & 0xF0) or 0x06) ^ 0x04
                if not payload:
                    expect(events == [], value)
                    continue
                expect(events == [expected], value, events)
                left = m.byte(instance + INSTANCE_STATE) & 7
                expect(left == (payload - 1 if success else payload), value, success, left)
                warned = m.byte('IncomingMissileMessage') & 0x80
                expect(bool(warned) == (success and expected == 0x02), value, success)
                cases += 1
    headers = s1_headers(ctx)
    mapped = {n: ((h[10] & 0xF0) or 0x06) ^ 0x04 for n, (_, h) in enumerate(headers)}
    expect(mapped[7] == 0x54 and mapped[15] == 0x34, mapped)
    expect({v for n, v in mapped.items() if n not in (7, 15)} == {0x02}, mapped)
    return cases + 1


@check('structures', 's1-blueprint-kill-award', ['L_DAFA', 'L_DB0F', 'L_DB43', 'AwardBounty', 'AddCombatScore'],
       'pass2',
       'State 10 (+$20 bits 5:4) removes the object: energy 0, +$20 bit 5 cleared, +$1D = $C0; '
       'AwardBounty gets header word +8 and AddCombatScore header word +$15 / 2; header +$12 AND $60 '
       'makes PlayerLegalScore at least $40.  All 19 blueprints.')
def check_s1_blueprint_kill_award(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    award = {}
    stubs = {'L_EB65': None,
             'AwardBounty': lambda mm: award.__setitem__('bounty', mm.pair('de')),
             'AddCombatScore': lambda mm: award.__setitem__('score', mm.pair('de'))}
    cases = 0
    for blueprint_id, (address, h) in enumerate(s1_headers(ctx)):
        m.reset()
        load_jameson(m)
        m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=blueprint_id, ix=instance))
        m.poke(instance + INSTANCE_STATE, (m.byte(instance + INSTANCE_STATE) & 0xCF) | 0x20)
        m.poke('PlayerLegalScore', 0)
        m.poke('MissionAspEncounterState', 0)
        award.clear()
        m.call('L_DAFA', stop='L_DBBE', **dict(FRESH_REGISTERS, ix=instance), stubs=stubs)
        expect(m.iy() == address, blueprint_id)
        expect(award == dict(bounty=h[8] | h[9] << 8, score=(h[21] | h[22] << 8) >> 1), blueprint_id, award)
        expect(m.byte(instance + 0x22) == 0 and m.byte(instance + INSTANCE_STATE) & 0x30 == 0, blueprint_id)
        expect(m.byte(instance + INSTANCE_ROLL) == 0xC0, blueprint_id)
        expect(m.byte('PlayerLegalScore') == (0x40 if h[18] & 0x60 else 0), blueprint_id)
        cases += 1
    return cases


@check('structures', 's1-instance-explosion-states', ['L_DBA3', 'DrawObjectInView', 'L_E1D4',
                                                      'DrawFlaggedObjectDiscs'], 'pass2',
       '+$20 bits 5:4: a destroyed object (01) drawn in view records ProjectedX/ProjectedY, $0C + '
       'inverted quadrant bits and the projected size in +$1C/+$1D/+$1E/+$1F and becomes 11; '
       'DrawFlaggedObjectDiscs draws 15 discs (radius +2 each) and makes it 10; an object that is not '
       'drawn goes 01 -> 10 in L_DBA3.')
def check_s1_instance_explosion_states(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    cases = 0
    for screen in (0x0B, 0x04):                       # no space view: not drawn
        m.reset()
        load_jameson(m)
        m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=16, ix=instance))
        iy = m.iy()
        m.clear(instance, 9)
        m.poke(instance + 7, 0x10)                    # z = $1000: far, ahead
        m.poke(instance + INSTANCE_STATE, 0x50)
        m.poke('CurrentScreenId', screen)
        m.call('L_DBA3', stop='L_DBBE', **dict(FRESH_REGISTERS, ix=instance, iy=iy))
        expect(m.byte(instance + INSTANCE_STATE) & 0x30 == 0x20, screen)
        cases += 1
    m.reset()
    load_jameson(m)
    m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=16, ix=instance))
    iy = m.iy()
    m.clear(instance, 9)
    m.poke(instance + 0, 0x00, 0x01, 0x00)            # x = +$0100
    m.poke(instance + 3, 0x80, 0x00, 0x80)            # y = -$0080
    m.poke(instance + 6, 0x00, 0x08, 0x00)            # z = +$0800
    m.poke(instance + INSTANCE_STATE, 0x50)
    m.poke('CurrentScreenId', 0)
    m.call('DrawObjectInView', **dict(FRESH_REGISTERS, ix=instance, iy=iy))
    recorded = [m.byte(instance + INSTANCE_DISC + n) for n in range(4)]
    quadrant = m.byte('ProjectedQuadrant')
    inverted = ((quadrant & 1) << 1 | (quadrant >> 1) & 1) ^ 3
    expect(m.byte(instance + INSTANCE_STATE) & 0x30 == 0x30, 'state 11')
    expect(recorded == [m.byte('ProjectedX'), m.byte('ProjectedY'), 0x0C + inverted, m.byte('L_DA0B')],
           recorded, quadrant)
    expect(recorded[0] == 0x20 and recorded[1] == 0x10, recorded)       # 256*$100/$800, 256*$80/$800
    cases += 1
    radii = []
    m.poke('LastActiveObjectEnergy', 1)
    m.call('DrawFlaggedObjectDiscs', stubs={'DrawFilledCircle': lambda mm: radii.append(mm.byte('CircleRadius')),
                                            'FillViewAttributes': None})
    expect(radii == [recorded[3] + 2 * n for n in range(15)], radii)
    expect(m.byte(instance + INSTANCE_STATE) & 0x30 == 0x20, 'state 10')
    return cases + 1


@check('structures', 's1-instance-rotation-counters', ['MoveObject', 'L_DD5D'], 'pass2',
       'Instance +$1D/+$1E: bit 7 rotates every move without counting; otherwise a nonzero low nibble '
       'rotates once and decrements the byte, a zero low nibble stops (bits 4/5 are ignored); the step '
       'is 12 for roll and 8 for pitch, bit 6 selects the negative direction (+$80).')
def check_s1_instance_rotation_counters(ctx):
    m = ctx.machine()
    instance = s1_instance(m)
    entry = ctx.find('MoveObject', 'L_DD5D', [0xDD, 0x7E, INSTANCE_ROLL, 0x47, 0xCB, 0x7F])

    def model(value, step):
        if value & 0x80:
            return value, step | (value & 0x40) << 1
        if not value & 0x0F:
            return value, 0
        return value - 1, step | (value & 0x40) << 1

    cases = 0
    for value in range(256):
        for other in (value, value ^ 0xC5):
            m.reset()
            m.poke(instance + INSTANCE_ROLL, value, other)
            m.call(entry, stop='L_DD5D', ix=instance)
            roll, roll_angle = model(value, 12)
            pitch, pitch_angle = model(other, 8)
            expect((m.byte(instance + INSTANCE_ROLL), m.byte('RollRotationAngle')) == (roll, roll_angle), value)
            expect((m.byte(instance + INSTANCE_ROLL + 1), m.reg('a')) == (pitch, pitch_angle), other)
            cases += 1
    return cases


@check('structures', 's1-blueprint-geometry-format', ['ShipBlueprintTable'], 'pass2',
       'All 19 default records and the original side-B Adder: edge byte 0 (visibility threshold) is at '
       'most $1F; vertex and edge face nibbles are below the face count or 15; edge vertices and the gun '
       'vertex (+$14) are below the vertex count; faces follow the edges (offset 0 when there are none); '
       '+$0A bit 3 and +$12 bit 4 are clear.')
def check_s1_blueprint_geometry_format(ctx):
    table = ctx['ShipBlueprintTable']
    cases = 0
    records = [(address, ctx.pristine) for address in blueprint_headers(ctx)]
    from analyze_ship_blueprints import fixed_tap_image                 # comparison tape reader
    side_b = fixed_tap_image('Elite+48K+fixed+B+-+Adder.tap')        # 48K side B, load $4000
    memory = [0] * SCREEN + list(side_b)
    adder = memory[table + 4 * 17 + 1] | memory[table + 4 * 17 + 2] << 8
    expect(memory[adder + 3:adder + 6] == [18, 29, 15], 'side-B Adder')
    records.append((adder, memory))
    for address, memory in records:
        h = memory[address:address + S1_HEADER_SIZE]
        vertices, edges, faces = h[3], h[4], h[5]
        word = lambda offset: h[offset] | h[offset + 1] << 8      # noqa: E731
        vertex_table, edge_table = address + word(12), address + word(14)
        expect(h[20] < vertices and not h[10] & 0x08 and not h[18] & 0x10, hex(address))
        allowed = set(range(faces)) | {15}
        for n in range(vertices):
            v = memory[vertex_table + 6 * n:vertex_table + 6 * n + 6]
            nibbles = {v[4] & 15, v[4] >> 4, v[5] & 15, v[5] >> 4}
            expect(nibbles <= allowed, hex(address), n, v)
            cases += 1
        for n in range(edges):
            e = memory[edge_table + 4 * n:edge_table + 4 * n + 4]
            expect(e[0] <= 0x1F and e[1] < vertices and e[2] < vertices, hex(address), n, e)
            expect({e[3] & 15, e[3] >> 4} <= allowed, hex(address), n, e)
            cases += 1
        if faces:
            expect(address + word(16) == edge_table + 4 * edges, hex(address))
            cases += faces
        else:
            expect(word(16) == 0, hex(address))
    return cases
# --- END S1 CHECKS ---

# --- BEGIN P8 CHECKS ---
# Object update loop and motion helpers of $D400..$DFFF (pass 2).


@check('pipeline', 'r8-projected-object-size', ['DrawObjectInView', 'ProjectedObjectSize'], 'pass2',
       'ProjectedObjectSize = DivideRatioByte(blueprint +1 size, depth) = min(255, 256*size/depth) '
       'for every view once the depth exceeds the size (otherwise unchanged); an object with +$20 '
       'bit 4 has it copied to +$1F with ProjectedX in +$1C and +$20 bit 5 set (L_E1D4).')
def check_r8_projected_object_size(ctx):
    m = ctx.machine()
    slot = ctx['InitialRuntimeState'] + ctx['InstanceSize']
    marker, cases = 0xEE, 0
    for ship in (0, 4, 9, 13, SIDEWINDER):
        for screen in range(4):
            for depth in (0x0060, 0x0100, 0x0180, 0x0300, 0x0800, 0x2000):
                m.reset()
                load_jameson(m)
                m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=ship, ix=slot))
                iy = m.iy()
                size = m.byte(iy + 1)
                side = depth // 8
                position = {0: (side, side, depth), 1: (side, -side, -depth),
                            2: (-depth, side, side), 3: (depth, side, -side)}[screen]
                for axis, value in enumerate(position):
                    put24(m.memory, slot + 3 * axis, value)
                m.poke(slot + INSTANCE_STATE, 0x50)          # counted + bit 4: record the position
                m.poke('CurrentScreenId', screen)
                m.poke('ProjectedObjectSize', marker)
                m.poke(slot + 0x1F, marker)
                m.call('DrawObjectInView', limit=500_000, **dict(FRESH_REGISTERS, ix=slot, iy=iy))
                got = m.byte('ProjectedObjectSize')
                if depth > size:
                    want = divide_ratio_model(size << 8, depth << 8)[1]
                    expect(got == want, 'size', ship, screen, hex(depth), got, want)
                    expect(m.byte(slot + 0x1F) == got and m.byte(slot + INSTANCE_DISC) == m.byte('ProjectedX')
                           and m.byte(slot + INSTANCE_STATE) & 0x20, 'copied to +$1F', ship, screen, hex(depth))
                else:
                    expect(got == marker and m.byte(slot + 0x1F) == marker, 'not drawn', ship, hex(depth))
                cases += 1
    return cases


@check('missions', 'r8-docking-contact', ['L_EA51', 'CheckDocking', 'CheckHyperspaceKeys',
                                          'DockingContactFlag'], 'pass2',
       'Touching the station (inside its size, in front, not hostile, nose z < 0) sets '
       'DockingContactFlag only when |Z.x|, |Z.y| < $1E; up to $6D adds 12 + 2*speed front damage '
       'and sound bit 6; worse alignment, a hostile station or z < 0 sets PlayerDeadFlag $0F; out of '
       'reach nothing.  CheckDocking clears the flag and docks unless L_7C39 is set; a G press '
       'without H sets L_7C39 although no jump starts.')
def check_r8_docking_contact(ctx):
    m = ctx.machine()
    station = ctx['InitialRuntimeState']
    nose = station + ctx['InstanceAxisZ']

    def touch(zx=0, zy=0, zz=0xFF, z=0x40, hostile=False, speed=3):
        m.reset()
        load_jameson(m)
        iy = m.word(station + INSTANCE_BLUEPRINT)
        for axis, value in enumerate((0x10, -0x10, z)):
            put24(m.memory, station + 3 * axis, value)
        m.poke(nose + 1, zx)
        m.poke(nose + 3, zy)
        m.poke(nose + 5, zz)
        if hostile:
            m.poke(station + ctx['InstanceBehaviour'], m.byte(station + ctx['InstanceBehaviour']) | 4)
        m.poke('PlayerSpeed', speed)
        m.poke('FrontDamageThisUpdate', 0)
        m.poke('SoundEffectRequests', 0)
        m.poke('PlayerDeadFlag', 0)
        m.poke('DockingContactFlag', 0)
        m.call('L_EA51', **dict(FRESH_REGISTERS, ix=station, iy=iy))
        return (m.byte('DockingContactFlag'), m.byte('PlayerDeadFlag'), m.byte('FrontDamageThisUpdate'),
                m.byte('SoundEffectRequests'), m.byte(station + ctx['InstanceEnergy']))

    docked, crashed, nothing = (1, 0, 0, 0, 240), (0, 0x0F, 0, 0, 240), (0, 0, 0, 0, 240)
    cases = {(): docked, (('zx', 0x1D),): docked, (('zx', 0x9D), ('zy', 0x1D)): docked,
             (('zx', 0x1E),): (0, 0, 12 + 6, 0x40, 240), (('zy', 0x9E), ('speed', 5)): (0, 0, 12 + 10, 0x40, 240),
             (('zx', 0x6D),): (0, 0, 18, 0x40, 240), (('zx', 0x6E),): crashed, (('zy', 0xEE),): crashed,
             (('zz', 0x7F),): crashed, (('hostile', True),): crashed, (('z', -0x40),): crashed,
             (('z', 0x8040),): nothing, (('z', 0x0100),): nothing}
    for args, want in cases.items():
        got = touch(**dict(args))
        expect(got == want, args, got, want)
    count = len(cases)

    def check_docking(flag, latch):
        m.reset()
        m.poke('DockingContactFlag', flag)
        m.poke('L_7C39', latch)
        m.poke('KeyFlagsCombat', 0)
        hits = []
        m.call('CheckDocking', stubs={'DockWithStation': lambda mm: hits.append(1)}, **FRESH_REGISTERS)
        return len(hits), m.byte('DockingContactFlag')

    expect(check_docking(1, 0) == (1, 0), 'contact docks and is cleared')
    expect(check_docking(1, 1) == (0, 1), 'latch set: no dock, flag kept')
    expect(check_docking(0, 0) == (0, 0), 'no contact, no key')
    m.reset()
    m.poke('KeyFlagsViews', 0x20)
    m.poke('L_7C39', 0)
    m.poke('FlightCondition', 4)                      # in flight (green)
    m.call('CheckHyperspaceKeys', **FRESH_REGISTERS)
    expect(m.byte('L_7C39') == 1 and m.byte('KeyFlagsViews') & 0x30 == 0 and m.byte('HyperspaceCountdown') == 0,
           'G alone sets the latch without a jump')
    return count + 4


@check('missions', 'r8-energy-drain', ['L_A584', 'L_EDA9', 'L_EC11', 'UpdateObjects', 'EnergyDrainThisUpdate'],
       'pass2',
       'L_A584 drains 4*(EnergyDrainThisUpdate + cloak) from energy bank 1; the ECM update (C nonzero) '
       'and a laser shot each add one; UpdateObjects clears it.')
def check_r8_energy_drain(ctx):
    m = ctx.machine()
    banks = ctx['EnergyBank1']
    cases = 0
    for units in range(5):
        for cloak in (0, 1):
            m.reset()
            for bank in range(4):
                m.poke(banks + 2 * bank, 0xA0)
            m.poke('EnergyDrainThisUpdate', units)
            m.poke('CloakingDeviceActive', cloak)
            m.poke('FrontDamageThisUpdate', 0)
            m.poke('RearDamageThisUpdate', 0)
            m.call('L_A584', stubs={'RechargeEnergyBanks': None}, **FRESH_REGISTERS)
            got = [m.byte(banks + 2 * bank) for bank in range(4)]
            expect(got == [0xA0 - 4 * (units + cloak)] + [0xA0] * 3, units, cloak, got)
            cases += 1
    m.reset()
    m.poke('EnergyDrainThisUpdate', 2)
    m.call('L_EDA9', **dict(FRESH_REGISTERS, c=0x81))
    expect(m.byte('EnergyDrainThisUpdate') == 3 and m.byte('EcmFitted') == 0x81, 'ECM running')
    m.call('L_EDA9', **dict(FRESH_REGISTERS, c=0))
    expect(m.byte('EnergyDrainThisUpdate') == 3, 'ECM bit gone: no drain')
    sound = ctx['SoundEffectRequests']
    stop = ctx.find('L_EC11', 'L_EC2A', [0x21, sound & 255, sound >> 8])
    m.call('L_EC11', stop=stop, **FRESH_REGISTERS)
    expect(m.byte('EnergyDrainThisUpdate') == 4, 'laser shot')
    m.reset()
    load_jameson(m)
    m.poke('EnergyDrainThisUpdate', 7)
    m.poke('ObjectUpdateCounter', 9)
    m.poke('CurrentScreenId', 0x0B)
    station_blueprint = m.word(ctx['InitialRuntimeState'] + INSTANCE_BLUEPRINT)
    m.call('UpdateObjects', limit=5_000_000, **dict(FRESH_REGISTERS, iy=station_blueprint))
    expect(m.byte('EnergyDrainThisUpdate') == 0, 'cleared by UpdateObjects')
    return cases + 4


@check('missions', 'r8-object-presence-flags', ['UpdateObjects', 'TorusJumpInhibitFlag',
                                                'LastNonStationObjectEnergy'], 'pass2',
       'After UpdateObjects: station only -> TorusJumpInhibitFlag 0, LastNonStationObjectEnergy 0 and '
       'SharedHostilityAlert cleared; plus a cargo canister (+$26 = $0A) -> flag 0, energy 17, alert '
       'cleared; plus a Sidewinder (+$26 = 0) -> flag 1, energy 70, alert kept.')
def check_r8_object_presence_flags(ctx):
    m = ctx.machine()
    state, size = ctx['InitialRuntimeState'], ctx['InstanceSize']
    slot = state + size
    results = {}
    for kind, ship in (('station', None), ('canister', 4), ('ship', SIDEWINDER)):
        m.reset()
        load_jameson(m)
        if ship is not None:
            m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=ship, ix=slot))
            for axis, value in enumerate((0x200, 0x100, 0x800)):
                put24(m.memory, slot + 3 * axis, value)
            if kind == 'canister':                   # as L_F592/L_F5B8 leave a child object
                m.poke(slot + INSTANCE_FLAGS26, 0x0A)
                m.poke(slot + INSTANCE_STATE, m.byte(slot + INSTANCE_STATE) & 0xBF)
        m.poke('SharedHostilityAlert', 1)
        m.poke('ObjectUpdateCounter', 9)
        m.poke('CurrentScreenId', 0x0B)
        m.call('UpdateObjects', limit=5_000_000, **dict(FRESH_REGISTERS, iy=m.word(state + INSTANCE_BLUEPRINT)))
        results[kind] = (m.byte('TorusJumpInhibitFlag'), m.byte('LastNonStationObjectEnergy'),
                         m.byte('LastActiveObjectEnergy'), m.byte('SharedHostilityAlert'))
    expect(results == {'station': (0, 0, 240, 0), 'canister': (0, 17, 17, 0), 'ship': (1, 70, 70, 1)}, results)
    return len(results)


def r8_scale_model(de, speed):
    """ScaleComponentBySpeed: E = (sum of |DE| >> (6-k) for set speed bits k=5..0, + $FF) >> 8."""
    magnitude, sign = de & 0x7FFF, de >> 15
    total = sum(magnitude >> k for k in range(1, 7) if speed & (1 << (6 - k)))
    return ((total + 0xFF) >> 8) & 0xFF, sign << 7


def r8_add_model(a, hl, de):
    """AddToCoordinate: (B, HL) for sign/high byte A, low word HL and step DE."""
    if a == de >> 8:
        return a, (hl + (de & 0x7FFF)) & 0xFFFF
    step = de & 0x7FFF
    return (a, hl - step) if hl >= step else (de >> 8, step - hl)


@check('maths', 'r8-motion-helpers', ['ScaleComponentBySpeed', 'AddToCoordinate', 'SquareRootHL',
                                      'ApplyPlayerMotion'], 'pass2',
       'ScaleComponentBySpeed and AddToCoordinate equal their bit-level models (the high-byte test '
       'compares all of A with D); SquareRootHL returns A = 0; ApplyPlayerMotion without rotation '
       'moves z by 2*(speed+1) towards negative, flips the sign when crossing zero and turns a '
       'negative overflow into +$7FFFxx, returning HL = z high/mid.')
def check_r8_motion_helpers(ctx):
    m = ctx.machine()
    rng = random.Random(8)
    cases = 0
    for _ in range(3000):
        de, speed = rng.randrange(65536), rng.randrange(256)
        m.call('ScaleComponentBySpeed', de=de, c=speed, hl=0x1234, b=0x55)
        expect((m.reg('e'), m.reg('d')) == r8_scale_model(de, speed), hex(de), hex(speed))
        cases += 1
    for i in range(3000):
        a = rng.choice((0, 0x80, rng.randrange(256)))
        hl, de = rng.randrange(65536), rng.randrange(256) | rng.choice((0, 0x8000))
        if i % 4 == 0:
            de = rng.randrange(65536)
        m.call('AddToCoordinate', a=a, hl=hl, de=de)
        expect((m.reg('b'), m.pair('hl')) == r8_add_model(a, hl, de), hex(a), hex(hl), hex(de))
        cases += 1
    for n in (1, 15, 16, 255, 256, 0x0FFF, 0x1000, 0x8000, 0xFFFF):
        m.call('SquareRootHL', hl=n, a=0x5A)
        expect(m.reg('a') == 0, 'SquareRootHL A', n)
        cases += 1
    base = ctx.scratch
    for z, speed, want in ((0x000500, 3, 0x0004F8), (0x000005, 3, -3), (-0x000005, 3, -13),
                           (-0x7FFFFE, 3, 0x7FFFFA), (0x123456, 0, 0x123454)):
        m.reset()
        m.poke('PlayerRoll', 0)
        m.poke('PlayerPitch', 0)
        m.poke('PlayerSpeed', speed)
        put24(m.memory, base, 0x1234)
        put24(m.memory, base + 3, -0x0567)
        put24(m.memory, base + 6, z)
        m.call('ApplyPlayerMotion', ix=base)
        expect(get24(m.memory, base + 6) == want and get24(m.memory, base) == 0x1234 and
               get24(m.memory, base + 3) == -0x0567, hex(z), get24(m.memory, base + 6))
        expect(m.pair('hl') == m.byte(base + 8) << 8 | m.byte(base + 7), 'HL = z high/mid', hex(z))
        cases += 1
    return cases
# --- END P8 CHECKS ---

# --- BEGIN P5 CHECKS ---
# Pass-2 checks of the $A400..$AFFF annotations: side-view dust respawn, the mission
# bytes of the commander record, the jump/tunnel mode bytes, the escape pod and a model
# of the market formula.


def p5_texts(ctx):
    """Decoded message/token texts of the reference image (tools/text_codec.py)."""
    from text_codec import TextCodec
    return TextCodec(ctx.image)


@check('dust', 'p5-side-view-respawn', ['RespawnDustSideView', 'RespawnDust', 'SwapDustParticleXY'],
       'pass2',
       'Side views (screen 2 left, 3 right): without a vertical rate a new particle has X = +120 '
       '(left) or -120 (right), |Y| <= 63 with a random sign and Z < $80; with a rate Z >= $80 '
       'and AlternatingBits alternates that pattern with a random X (magnitude bit 3 clear) on '
       'the top (Y = +63, DustFlags bit 3 set) or bottom (Y = -63) edge.  Fraction bytes are '
       'kept and DustRecordPointer advances by 5.  SwapDustParticleXY exchanges bytes 0 and 1 '
       'of the first DustRemaining records only.')
def check_p5_side_view_respawn(ctx):
    m = ctx.machine()
    record = ctx.scratch
    rng = random.Random(0x5A5)
    seeds = [rng.randrange(0x10000) for _ in range(24)]
    cases, values = 0, Counter()
    for screen in (2, 3):
        for rate in (0, 5):
            for alternating in (0x00, 0x80):
                for flags in (0x00, 0x08):
                    for seed in seeds:
                        m.reset()
                        m.poke(record, 0x11, 0x22, 0x33, 0x44, 0x55)
                        m.poke_word('DustRecordPointer', record)
                        m.poke_word('AuxRandomSeed', seed)
                        m.poke('CurrentScreenId', screen)
                        m.poke('DustPitchRate', rate)
                        m.poke('AlternatingBits', alternating)
                        m.poke('DustFlags', flags)
                        m.call('RespawnDust', stop='DustRespawnExit', **FRESH_REGISTERS)
                        x, y, z, xf, yf = m.memory[record:record + 5]
                        expect((xf, yf) == (0x44, 0x55) and m.word('DustRecordPointer') == record + 5,
                               'fractions / pointer', screen, rate, seed)
                        edge_x = 0x78 if screen == 2 else 0xF8
                        if rate == 0:
                            expect(m.byte('L_A425') == 0 and m.byte('AlternatingBits') == alternating,
                                   'no rate: Z operand 0, pattern bits untouched')
                            expect(x == edge_x and not y & 0x40 and z < 0x80, 'edge X', screen, x, y, z)
                        else:
                            expect(m.byte('L_A425') == 0x80 and z >= 0x80, 'rate: Z bit 7', z)
                            expect(m.byte('AlternatingBits') == (alternating << 1 | alternating >> 7) & 255,
                                   'pattern bits rotated')
                            if alternating & 0x80:
                                expect(not x & 0x08 and y == (0x3F if flags else 0xBF), 'edge Y', x, y)
                            else:
                                expect(x == edge_x and not y & 0x40, 'edge X with rate', x, y)
                        values[(screen, rate, alternating, flags)] += 1
                        values[('z', z & 0x7F)] += 1
                        cases += 1
    expect(len([k for k in values if k[0] == 'z']) > 32, 'Z varies with the random state')
    records = ctx['DustParticleRecords']
    for count in (4, 16):
        m.reset()
        pattern = [(7 * i + 3) & 255 for i in range(80)]
        m.poke(records, *pattern)
        m.poke('DustRemaining', count)
        m.call('SwapDustParticleXY', **FRESH_REGISTERS)
        out = m.memory[records:records + 80]
        for n in range(16):
            a, b, rest = pattern[5 * n], pattern[5 * n + 1], pattern[5 * n + 2:5 * n + 5]
            want = [b, a] + rest if n < count else [a, b] + rest
            expect(out[5 * n:5 * n + 5] == want, 'swap', count, n)
        cases += 1
    return cases


@check('missions', 'p5-nova-mission', ['NovaMissionActive', 'ExpandingSunActive', 'ArmExpandingSun',
                                       'UpdateExpandingSun', 'CheckFlightWarnings',
                                       'GalacticHyperspaceJump', 'NormalHyperspaceJump'], 'pass2',
       'ArmExpandingSun sets ExpandingSunActive and paints the view red (colour 2) only with '
       'NovaMissionActive; UpdateExpandingSun does nothing while ExpandingSunActive is 0, otherwise '
       'CabinTemperature + 1 and the sun radius + 2 (from CircleRadius when ExpandingSunRadius is 0), '
       'radius 256 sets PlayerDeadFlag.  CheckFlightWarnings sends token $C2 "MAYDAY * CORIOLIS IN '
       'DANGER*" only with the nova flag and the sun not yet armed, token $0F "... INVADED*" for '
       'InvasionMissionState 1, every 70th call.  The nova flag turns NormalHyperspaceJump into '
       'GalacticHyperspaceJump, which clears it with ExpandingSunActive and the invasion state.')
def check_p5_nova_mission(ctx):
    texts = p5_texts(ctx)
    expect('CORIOLIS IN DANGER' in texts.token(0xC2) and 'INVADED' in texts.token(0x0F), 'tokens')
    m = ctx.machine()
    cases = 0
    for nova in (0, 1):
        m.reset()
        m.poke('NovaMissionActive', nova)
        m.poke('ExpandingSunActive', 0)
        fills = []
        m.call('ArmExpandingSun', stubs={'FillViewAttributes': lambda mm: fills.append(mm.reg('l'))},
               **FRESH_REGISTERS)
        expect((m.byte('ExpandingSunActive'), fills) == ((1, [2]) if nova else (0, [])), 'arm', nova, fills)
        cases += 1

    def grow(active, sun, circle):
        m.reset()
        m.poke('ExpandingSunActive', active)
        m.poke('ExpandingSunRadius', sun)
        m.poke('CircleRadius', circle)
        m.poke('CabinTemperature', 10)
        m.poke('PlayerDeadFlag', 0)
        m.call('UpdateExpandingSun', **FRESH_REGISTERS)
        return (m.byte('CabinTemperature'), m.byte('ExpandingSunRadius'), m.byte('CircleRadius'),
                m.byte('PlayerDeadFlag'))

    expect(grow(0, 0, 40) == (10, 0, 40, 0), 'inactive')
    expect(grow(1, 0, 40) == (11, 42, 42, 0), 'starts from the projected radius')
    expect(grow(1, 0x80, 40) == (11, 0x82, 0x82, 0), 'keeps growing')
    expect(grow(1, 0xFD, 40) == (11, 0xFF, 0xFF, 0), 'below 256')
    expect(grow(1, 0xFE, 40) == (11, 0, 0, 1), '256 ends the game')
    cases += 5

    def warning(nova, sun, invasion, delay=0):
        m.reset()
        m.poke('EnergyBank4', 0xA0)
        m.poke('FuelScoopRangeFlag', 0)
        m.poke('DockingComputerFlag', 0)
        m.poke('MissionMessageDelay', delay)
        m.poke('NovaMissionActive', nova)
        m.poke('ExpandingSunActive', sun)
        m.poke('InvasionMissionState', invasion)
        shown = []
        m.call('CheckFlightWarnings', stubs={'ShowFlightMessage': lambda mm: shown.append((mm.reg('b'), mm.reg('c')))},
               **FRESH_REGISTERS)
        return shown, m.byte('MissionMessageDelay')

    expect(warning(1, 0, 0) == ([(0xC2, 2)], 0x46), 'nova mayday')
    expect(warning(1, 1, 0) == ([], 0x46), 'no mayday once the sun expands')
    expect(warning(0, 0, 1) == ([(0x0F, 3)], 0x46), 'invasion mayday')
    expect(warning(1, 0, 1) == ([(0x0F, 3)], 0x46), 'invasion message first')
    expect(warning(0, 0, 2) == ([], 0x46) and warning(0, 0, 4) == ([], 0x46), 'later invasion states')
    expect(warning(1, 0, 0, delay=5) == ([], 4), 'only every 70th call')
    cases += 7

    def galactic(nova, sun):
        m.reset()
        load_jameson(m)
        m.poke('CurrentScreenId', 0)
        m.poke('NovaMissionActive', nova)
        m.poke('ExpandingSunActive', sun)
        m.poke('InvasionMissionState', 4)
        m.poke('GalacticHyperdriveFitted', 1)
        m.call('GalacticHyperspaceJump', stop='ArriveInTargetSystem', **FRESH_REGISTERS)
        return (m.byte('NovaMissionActive'), m.byte('ExpandingSunActive'), m.byte('InvasionMissionState'),
                m.byte('GalacticHyperdriveFitted'), m.byte('CurrentGalaxy'))

    expect(galactic(1, 1) == (0, 0, 0, 0, 1), 'galactic jump ends the nova mission')
    expect(galactic(0, 1) == (0, 1, 0, 0, 1), 'sun flag cleared only with the nova flag')
    cases += 2
    m.reset()
    load_jameson(m)
    m.poke('NovaMissionActive', 1)
    m.call('NormalHyperspaceJump', stop='GalacticHyperspaceJump', **FRESH_REGISTERS)
    m.reset()
    load_jameson(m)
    m.poke('NovaMissionActive', 0)
    m.call('NormalHyperspaceJump', stop='SetFuelLevel',
           hooks={'GalacticHyperspaceJump': lambda mm: expect(False, 'normal jump turned galactic')},
           **FRESH_REGISTERS)
    return cases + 2


@check('missions', 'p5-nova-offer-and-reward', ['BuyCargoScreen', 'SellCargoScreen', 'NovaMissionActive',
                                                'CommanderFlags'], 'pass2',
       'With NovaMissionActive the buy key shows message $5B "THE SUN IS GOING NOVA* ... (Y/N)?" and a '
       'circle of radius $3D; Y empties all 17 holds, free space 0, LargeCargoBayFitted nonzero and '
       'CommanderFlags bit 5 (refugees); other keys change nothing; bit 5 already set skips trading.  '
       'Selling with bit 5 set and the nova flag clear rewards: bit 5 cleared, CombatScoreHigh + 1, '
       '100 gem-stones, free space 35 and message $0F "YOU HAVE SAVED OUR LIVES"; with the nova flag '
       'set the normal sell list runs.')
def check_p5_nova_offer_and_reward(ctx):
    texts = p5_texts(ctx)
    expect('THE SUN IS GOING NOVA' in texts.message(0x5B) and 'YOU HAVE SAVED OUR LIVES' in texts.message(0x0F),
           'messages')
    m = ctx.machine()
    hold = ctx['CargoHold']

    def buy(nova, key, flags=0):
        m.reset()
        load_jameson(m)
        m.poke(hold, *range(1, 18))
        m.poke('CargoFreeSpace', 3)
        m.poke('LargeCargoBayFitted', 0)
        m.poke('CommanderFlags', flags)
        m.poke('NovaMissionActive', nova)
        seen = []

        def press(mm):
            mm.r[A] = key
        m.call('BuyCargoScreen', stubs={
            'ShowColouredMessageScreen': lambda mm: seen.append(('message', mm.reg('d'))),
            'DrawScreenCircle': lambda mm: seen.append(('circle', mm.byte('ShapeSize'))),
            'WaitForKeyPress': press, 'Wait36Frames': None,
            'ShowInventory': lambda mm: seen.append('inventory'),
            'BuyCargoList': lambda mm: seen.append('buy list')}, **FRESH_REGISTERS)
        return (seen, m.memory[hold:hold + 17], m.byte('CargoFreeSpace'), m.byte('LargeCargoBayFitted'),
                m.byte('CommanderFlags'))

    offer = [('message', 0x5B), ('circle', 0x3D), 'inventory']
    expect(buy(1, ord('Y')) == (offer, [0] * 17, 0, ord('Y'), 0x20), 'accepted')
    expect(buy(1, ord('N')) == (offer, list(range(1, 18)), 3, 0, 0), 'declined')
    expect(buy(0, ord('Y'))[0] == ['buy list'], 'no mission: normal buy list')
    expect(buy(1, ord('Y'), flags=0x20)[0] == ['inventory'], 'refugees on board: no trading')

    def sell(nova, flags):
        m.reset()
        load_jameson(m)
        m.poke('NovaMissionActive', nova)
        m.poke('CommanderFlags', flags)
        m.poke('CombatScoreHigh', 2)
        seen = []
        m.call('SellCargoScreen', stubs={
            'ShowMessageScreenAndWait': lambda mm: seen.append(('message', mm.reg('d'))),
            'ShowInventory': lambda mm: seen.append('inventory'),
            'SellCargoList': lambda mm: seen.append('sell list')}, **FRESH_REGISTERS)
        return (seen, m.byte('CommanderFlags'), m.byte('CombatScoreHigh'), m.byte('CargoGemStones'),
                m.byte('CargoFreeSpace'))

    expect(sell(0, 0x60) == ([('message', 0x0F), 'inventory'], 0x40, 3, 100, 35), 'reward')
    expect(sell(1, 0x20)[:3] == (['sell list'], 0x20, 2), 'nova still active: no reward')
    expect(sell(0, 0x00)[:3] == (['sell list'], 0x00, 2), 'no refugees: no reward')
    return 7


@check('missions', 'p5-invasion-mission', ['InvasionMissionState', 'OfferSpecialMission', 'AwardHighestHonour',
                                           'L_782B'], 'pass2',
       'Docking acts on InvasionMissionState: 1 and 2 -> OfferSpecialMission, 4 -> EndGameWithMessage '
       'with message $D4 " THARGON", 5 -> AwardHighestHonour, 0, 3 and $0C -> nothing.  The offer '
       '(message $DF "... SPECIAL MISSION ... (Y/N)?") sets state 3, CommanderFlags bit 7 and shows '
       'the briefing $E0 "... TO DESTROY THE SPACE STATION ..." on Y, state 0 otherwise.  The award '
       'adds 256 to the combat score, sets CommanderFlags bit 3, clears the state and shows message '
       '$0A "... HIGHEST HONOUR".')
def check_p5_invasion_mission(ctx):
    texts = p5_texts(ctx)
    expect('SPECIAL MISSION' in texts.message(0xDF) and 'DESTROY THE SPACE STATION' in texts.message(0xE0)
           and 'HIGHEST HONOUR' in texts.message(0x0A) and 'THARGON' in texts.message(0xD4)
           and 'THARGON INVASION' in texts.message(0xDE), 'messages')
    m = ctx.machine()

    def dock(state):
        m.reset()
        m.poke('InvasionMissionState', state)
        seen = []
        m.call('L_782B', stubs={
            'OfferSpecialMission': lambda mm: seen.append('offer'),
            'AwardHighestHonour': lambda mm: seen.append('award'),
            'EndGameWithMessage': lambda mm: seen.append(('end', mm.reg('a')))}, **FRESH_REGISTERS)
        return seen

    golden = {0: [], 1: ['offer'], 2: ['offer'], 3: [], 4: [('end', 0xD4)], 5: ['award'], 0x0C: []}
    for state, want in golden.items():
        expect(dock(state) == want, 'docking', state, dock(state))

    def offer(key):
        m.reset()
        m.poke('InvasionMissionState', 1)
        m.poke('CommanderFlags', 0x07)
        seen = []

        def press(mm):
            mm.r[A] = key
        m.call('OfferSpecialMission', stubs={
            'ShowColouredMessageScreen': lambda mm: seen.append(mm.reg('d')),
            'WaitForKeyPress': press, 'L_D20A': lambda mm: seen.append('wait')}, **FRESH_REGISTERS)
        return seen, m.byte('InvasionMissionState'), m.byte('CommanderFlags')

    expect(offer(ord('Y')) == ([0xDF, 0xE0, 'wait'], 3, 0x87), 'accepted')
    expect(offer(ord('N')) == ([0xDF], 0, 0x07), 'declined')
    m.reset()
    m.poke('InvasionMissionState', 5)
    m.poke('CommanderFlags', 0x87)
    m.poke('CombatScoreHigh', 1)
    seen = []
    m.call('AwardHighestHonour', stubs={'ShowColouredMessageScreen': lambda mm: seen.append(mm.reg('d')),
                                        'L_D20A': lambda mm: seen.append('wait')}, **FRESH_REGISTERS)
    expect((seen, m.byte('InvasionMissionState'), m.byte('CommanderFlags'), m.byte('CombatScoreHigh'))
           == ([0x0A, 'wait'], 0, 0x8F, 2), 'award')
    return len(golden) + 3


@check('missions', 'p5-jump-tunnel-mode', ['JumpTunnelMode', 'TunnelLoopActive', 'CheckHyperspaceKeys',
                                           'ExecuteHyperspaceJump', 'StartStationTunnel'], 'pass2',
       'CheckHyperspaceKeys sets JumpTunnelMode 2 (galactic, needs the hyperdrive) or 1 (normal, target '
       'in fuel range) and starts the countdown; out of range or without the hyperdrive it stays 0.  '
       'ExecuteHyperspaceJump takes the galactic path for 2 only.  StartStationTunnel sets both bytes '
       'to 1 (not in witchspace); FinishLaunchTunnelLoop clears TunnelLoopActive only, '
       'FinishHyperspaceTunnel both.  HandleScreenKeys ignores keys while TunnelLoopActive is set.')
def check_p5_jump_tunnel_mode(ctx):
    m = ctx.machine()

    def keys(views, hyperdrive=1, target=None):
        m.reset()
        load_jameson(m)
        galactic_chart_state(m)
        m.poke('CurrentScreenId', 0)
        if target:
            m.poke('NameInputBuffer', *(target.encode() + bytes(9 - len(target))))
            m.call('FindSystemByName', **ZERO_REGISTERS)
            expect(not m.carry(), target)
        m.poke('FlightCondition', 4)
        m.poke('HyperspaceCountdown', 0)
        m.poke('KeyFlagsViews', views)
        m.poke('GalacticHyperdriveFitted', hyperdrive)
        m.poke('JumpTunnelMode', 0)
        shown = []
        m.call('CheckHyperspaceKeys', stubs={
            'SetFlightMessageText': lambda mm: shown.append(mm.reg('b')), 'BeepIfSoundOn': None,
            'BeepAndShowFlightMessage': lambda mm: shown.append(mm.reg('b'))}, **FRESH_REGISTERS)
        return m.byte('JumpTunnelMode'), m.byte('HyperspaceCountdown'), shown, m.byte('KeyFlagsViews') & 0x30

    expect(keys(0x30) == (2, 0x15, [0x74], 0), 'galactic')
    expect(keys(0x30, hyperdrive=0) == (0, 0, [], 0), 'no hyperdrive')
    near = keys(0x10, target='DISO')
    expect(near == (1, 0x15, [0xC0], 0) and 0 < m.word('SelectedSystemDistance') <= m.byte('FuelLevel'),
           'normal jump', near, m.word('SelectedSystemDistance'))
    expect(keys(0x10, target='TIBEDIED') == (0, 0, [0xC1], 0), 'out of range')
    cases = 4
    for mode, target in ((2, 'GalacticHyperspaceJump'), (1, 'NormalHyperspaceJump')):
        m.reset()
        m.poke('JumpTunnelMode', mode)
        m.call('ExecuteHyperspaceJump', stop=target, **FRESH_REGISTERS)
        cases += 1
    for witchspace in (0, 1):
        m.reset()
        m.poke_word('JumpTunnelMode', 0)
        m.poke('FlightCondition', 0)
        m.poke('WitchspaceFlag', witchspace)
        if witchspace:
            m.call('StartStationTunnel', **FRESH_REGISTERS)
            expect(m.word('JumpTunnelMode') == 0, 'no tunnel in witchspace')
        else:
            m.call('StartStationTunnel', stop='LaunchFromStation', **FRESH_REGISTERS)
            expect((m.byte('JumpTunnelMode'), m.byte('TunnelLoopActive')) == (1, 1), 'station tunnel')
        cases += 1
    m.reset()
    m.poke('JumpTunnelMode', 1)
    m.poke('TunnelLoopActive', 1)
    m.call('FinishLaunchTunnelLoop', stop='L_7A88', **FRESH_REGISTERS)
    expect((m.byte('JumpTunnelMode'), m.byte('TunnelLoopActive')) == (1, 0), 'launch loop end')
    m.reset()
    m.poke('JumpTunnelMode', 2)
    m.poke('TunnelLoopActive', 1)
    m.call('FinishHyperspaceTunnel', stop='L_7ACD', stubs={'ClearViewBuffer': None, 'BlitViewBitmap': None},
           **FRESH_REGISTERS)
    expect((m.byte('JumpTunnelMode'), m.byte('TunnelLoopActive')) == (0, 0), 'arrival tunnel end')
    m.reset()
    m.poke('TunnelLoopActive', 1)
    m.poke('KeyFlagsViews', 0x01)
    m.call('HandleScreenKeys', **FRESH_REGISTERS)
    expect(m.byte('KeyFlagsViews') == 0x01, 'keys ignored during the tunnel loop')
    return cases + 3


@check('commander', 'p5-escape-pod', ['UpdateEscapePod', 'EscapePodTimer'], 'pass2',
       'Q with the escape pod fitted (not in witchspace): EscapePodTimer 24, SpeedControl $0010, legal '
       'score 0, pod used up, fluctuation and cargo 0..15 cleared while alien items stay, refugees bit 5 '
       'cleared, free space 20 (35 with the large cargo bay), ship event $17, chart cursor on the current '
       'system.  The timer then counts down and jumps to L_7102 at zero.')
def check_p5_escape_pod(ctx):
    m = ctx.machine()
    hold = ctx['CargoHold']

    def launch(bay=0, fitted=1, witchspace=0, key=0x40):
        m.reset()
        load_jameson(m)
        m.poke('EscapePodTimer', 0)
        m.poke('KeyFlagsCombat', key)
        m.poke('EscapePodFitted', fitted)
        m.poke('WitchspaceFlag', witchspace)
        m.poke('LargeCargoBayFitted', bay)
        m.poke('PlayerLegalScore', 50)
        m.poke('MarketFluctuation', 9)
        m.poke(hold, *([5] * 17))
        m.poke('CargoFreeSpace', 1)
        m.poke('CommanderFlags', 0x61)
        m.poke('ChartCursorX', 1, 2)
        events = []
        m.call('UpdateEscapePod', stubs={'DispatchShipEvent': lambda mm: events.append(mm.reg('a'))},
               **FRESH_REGISTERS)
        return dict(timer=m.byte('EscapePodTimer'), speed=m.word('SpeedControl'), legal=m.byte('PlayerLegalScore'),
                    pod=m.byte('EscapePodFitted'), fluct=m.byte('MarketFluctuation'),
                    hold=m.memory[hold:hold + 17], free=m.byte('CargoFreeSpace'), flags=m.byte('CommanderFlags'),
                    events=events, cursor=(m.byte('ChartCursorX'), m.byte('ChartCursorY')),
                    current=(m.byte('CurrentSystemX'), m.byte('CurrentSystemY')))

    out = launch()
    expect(out['timer'] == 24 and out['speed'] == 0x0010 and out['legal'] == 0 and out['pod'] == 0 and
           out['fluct'] == 0 and out['hold'] == [0] * 16 + [5] and out['free'] == 20 and out['flags'] == 0x41
           and out['events'] == [0x17] and out['cursor'] == out['current'], 'launch', out)
    expect(launch(bay=1)['free'] == 35, 'large cargo bay')
    for blocked in (dict(fitted=0), dict(witchspace=1), dict(key=0x00)):
        out = launch(**blocked)
        expect(out['timer'] == 0 and out['pod'] == blocked.get('fitted', 1) and out['events'] == [], blocked)
    m.reset()
    m.poke('EscapePodTimer', 2)
    m.call('UpdateEscapePod', **FRESH_REGISTERS)
    expect(m.byte('EscapePodTimer') == 1, 'countdown')
    m.call('UpdateEscapePod', stop='L_7102', **FRESH_REGISTERS)
    expect(m.byte('EscapePodTimer') == 0, 'expired')
    return 7


@check('economy', 'p5-market-model', ['ComputeMarket', 'CommodityTable'], 'pass2',
       'For every economy 0..7 and 64 fluctuations, ComputeMarket matches the model: term = factor * '
       'economy; stock = base quantity + (fluctuation AND mask) - (term + 1) when byte 1 bit 7 is clear, '
       '+ term when set, 0 when bit 7 of the result is set, AND $3F (alien items 0); price word = 4 * '
       '(base price + (fluctuation AND mask) + term when clear, - (term + 1) when set), 8-bit sums.')
def check_p5_market_model(ctx):
    m = ctx.machine()
    table = ctx['CommodityTable']
    records = [ctx.pristine[table + 4 * n:table + 4 * n + 4] for n in range(17)]
    stock, prices = ctx['MarketStock'], ctx['MarketPrices']
    cases = 0
    for economy in range(8):
        for fluctuation in range(0, 256, 4):
            m.poke('SelectedSystemEconomy', economy)
            m.poke('MarketFluctuation', fluctuation)
            m.call('ComputeMarket', **ZERO_REGISTERS)
            for n, (base_price, factor, base_quantity, mask) in enumerate(records):
                term = (factor & 0x1F) * economy & 255
                quantity = base_quantity + (fluctuation & mask)
                quantity = quantity + term if factor & 0x80 else quantity - term - 1
                quantity &= 255
                quantity = 0 if quantity & 0x80 else quantity & 0x3F
                price = base_price + (fluctuation & mask)
                price = (price - term - 1 if factor & 0x80 else price + term) & 255
                want_stock = 0 if n == 16 else quantity & 255
                expect(m.byte(stock + n) == want_stock and m.word(prices + 2 * n) == 4 * price,
                       'market', economy, fluctuation, n, m.byte(stock + n), want_stock,
                       m.word(prices + 2 * n), 4 * price)
            cases += 1
    return cases
# --- END P5 CHECKS ---

# --- BEGIN P9 CHECKS ---
# contact/combat: object contact (collision, scooping, docking), target release,
# explosion record, AI laser beams, avoidance release and the player laser rate

P9_CORIOLIS, P9_MISSILE, P9_CAPSULE, P9_ALLOY, P9_CANISTER, P9_SPLINTER = 0, 1, 2, 3, 4, 5
P9_COBRA_PIRATE, P9_THARGON = 12, 18                       # blueprint IDs (docs/SHIPS.md)
P9_SLAVES, P9_ALLOYS, P9_MINERALS, P9_ALIEN_ITEMS = 3, 9, 12, 16   # commodity order (CargoHold)
P9_COMMODITIES = 17
P9_BLUEPRINT_CARGO, P9_BLUEPRINT_RADIUS, P9_BLUEPRINT_ENERGY, P9_BLUEPRINT_GUN = 0x00, 0x01, 0x07, 0x14
P9_COLLISION_DAMAGE = 0x50
P9_OUTPUTS = ('PlayerDeadFlag', 'FrontDamageThisUpdate', 'RearDamageThisUpdate', 'SoundEffectRequests',
              'L_DA15', 'CargoFreeSpace', 'MissionAspEncounterState', 'PlayerLegalScore', 'CommanderFlags')


def p9_random_stub(value):
    """Emulated NextRandomByte returning a fixed value in A."""
    def stub(machine):
        machine.r[A] = value
    return stub


class P9Contact:
    """One instance placed in a slot with a chosen position, then HandleObjectContact."""

    def __init__(self, ctx):
        self.ctx, self.m = ctx, ctx.machine()
        self.state, self.size = ctx['InitialRuntimeState'], ctx['InstanceSize']

    def run(self, ship, pos, slot=1, roles=None, target=None, behaviour=0, axis=None, random_value=None,
            **pokes):
        ctx, m = self.ctx, self.m
        m.reset()
        load_jameson(m)
        inst = self.state + slot * self.size
        if slot:
            m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=ship, ix=inst))
        blueprint = m.word(inst + INSTANCE_BLUEPRINT)
        for axis_index, value in enumerate(pos):
            put24(m.memory, inst + ctx['InstanceX'] + 3 * axis_index, value)
        if roles is not None:
            m.poke(inst + INSTANCE_FLAGS26, roles)
        if target is not None:
            m.poke(inst + INSTANCE_FLAGS25, target)
        m.poke(inst + ctx['InstanceBehaviour'], m.byte(inst + ctx['InstanceBehaviour']) | behaviour)
        for component, value in (axis or {}).items():            # sign-magnitude high bytes
            m.poke(inst + ctx['InstanceAxisZ'] + 1 + 2 * component, value)
        for name, value in pokes.items():
            m.poke(name, value)
        m.poke('ObjectLoopCounter', ctx['InstanceSlotCount'] - slot)
        hold = ctx['CargoHold']
        cargo = list(m.memory[hold:hold + P9_COMMODITIES])
        stubs = None if random_value is None else {'NextRandomByte': p9_random_stub(random_value)}
        m.call('HandleObjectContact', stubs=stubs, ix=inst, iy=blueprint, a=0, f=0, bc=0, de=0, hl=0)
        out = {name: m.byte(name) for name in P9_OUTPUTS}
        out['energy'] = m.byte(inst + ctx['InstanceEnergy'])
        out['cargo'] = {i: b - a for i, (a, b) in
                        enumerate(zip(cargo, m.memory[hold:hold + P9_COMMODITIES])) if a != b}
        out['blueprint'] = blueprint
        return out


@check('contact', 'p9-object-contact', ['HandleObjectContact', 'CollideWithObject', 'ReleaseTargetLocks'],
       'pass2',
       'HandleObjectContact reacts only when |x|, |y| and |z| are all below the radius (blueprint +1; '
       '+256 for a missile whose target code +$25 is 0, the player) and z has no bits above 16; '
       'ships then lose all energy, add $50 (+ their energy for missiles) to FrontDamageThisUpdate '
       '(z >= 0) or RearDamageThisUpdate (z < 0) and request sound bit 2; the marked mission ship '
       'clears MissionAspEncounterState; nothing happens while PlayerDeadFlag is set.')
def check_p9_object_contact(ctx):
    contact = P9Contact(ctx)
    cases = 0
    radius = contact.m.byte(blueprint_headers(ctx)[SIDEWINDER] + P9_BLUEPRINT_RADIUS)
    for axis_index in range(3):
        for offset, hit in ((-1, True), (0, False)):
            for sign in (1, -1):
                pos = [5, 5, 5]
                pos[axis_index] = sign * (radius + offset)
                out = contact.run(SIDEWINDER, pos)
                front = P9_COLLISION_DAMAGE if hit and pos[2] >= 0 else 0
                rear = P9_COLLISION_DAMAGE if hit and pos[2] < 0 else 0
                expect((out['energy'] == 0) == hit and out['FrontDamageThisUpdate'] == front and
                       out['RearDamageThisUpdate'] == rear and out['SoundEffectRequests'] == (4 if hit else 0),
                       'ship radius', pos, out)
                cases += 1
    out = contact.run(SIDEWINDER, [5, 5, 0x10005])                # z beyond 16 bits: no contact
    expect(out['energy'] and not out['FrontDamageThisUpdate'], 'z high byte', out)
    out = contact.run(SIDEWINDER, [5, 5, 5], PlayerDeadFlag=1)
    expect(out['energy'] and not out['FrontDamageThisUpdate'], 'player dead', out)
    cases += 2
    missile = blueprint_headers(ctx)[P9_MISSILE]
    missile_radius = contact.m.byte(missile + P9_BLUEPRINT_RADIUS)
    missile_energy = contact.m.byte(missile + P9_BLUEPRINT_ENERGY)
    for target, distance, hit in ((0, 0x100 + missile_radius - 1, True), (0, 0x100 + missile_radius, False),
                                  (3, missile_radius - 1, True), (3, missile_radius, False)):
        out = contact.run(P9_MISSILE, [distance, 0, 7], roles=0x01, target=target)
        expect((out['energy'] == 0) == hit and
               out['FrontDamageThisUpdate'] == (P9_COLLISION_DAMAGE + missile_energy if hit else 0),
               'missile', target, distance, out)
        cases += 1
    for state in (1, 2, 3):
        out = contact.run(ASP_MK_II, [5, 5, 5], roles=0x40, MissionAspEncounterState=state)
        expect(out['MissionAspEncounterState'] == 0 and out['energy'] == 0, 'marked ship', state, out)
        out = contact.run(ASP_MK_II, [5, 5, 5], roles=0x00, MissionAspEncounterState=state)
        expect(out['MissionAspEncounterState'] == state, 'unmarked ship', state, out)
        cases += 2
    return cases


@check('contact', 'p9-scooping', ['HandleObjectContact', 'ScoopCargoItem'], 'pass2',
       'Objects with +$26 bit 1 use radius $B4.  Below the player (y < 0) with FuelScoopsFitted and '
       'free cargo space they vanish without damage and add one ton: (blueprint +0 >> 4) + 1 '
       '(escape capsule slaves, alloy plate alloys, splinter minerals, Thargon alien items) or, for '
       'nibble 0 (canister), random AND 7; in MissionAspEncounterState 3 a canister gives the '
       'cloaking device (CommanderFlags bit 6, state 0).  Above, without scoops or with a full '
       'hold the object is destroyed with collision damage.')
def check_p9_scooping(ctx):
    contact = P9Contact(ctx)
    cases = 0
    for ship, roles, commodity in ((P9_CAPSULE, 0x0A, P9_SLAVES), (P9_ALLOY, 0x0A, P9_ALLOYS),
                                   (P9_SPLINTER, 0x0A, P9_MINERALS), (P9_THARGON, 0x02, P9_ALIEN_ITEMS)):
        for distance, hit in ((0xB3, True), (0xB4, False)):
            out = contact.run(ship, [0, -distance, 9], roles=roles, FuelScoopsFitted=1)
            nibble = contact.m.byte(out['blueprint'] + P9_BLUEPRINT_CARGO) >> 4
            expect(nibble + 1 == commodity, 'cargo nibble', ship, nibble)
            expect(out['cargo'] == ({commodity: 1} if hit else {}) and (out['energy'] == 0) == hit and
                   out['CargoFreeSpace'] == (19 if hit else 20) and not out['FrontDamageThisUpdate'],
                   'scoop', ship, distance, out)
            cases += 1
    for value in range(0, 256, 7):
        out = contact.run(P9_CANISTER, [0, -50, 9], roles=0x0A, random_value=value, FuelScoopsFitted=1)
        expect(out['cargo'] == {value & 7: 1}, 'canister commodity', value, out)
        cases += 1
    out = contact.run(P9_CANISTER, [0, -50, 9], roles=0x0A, FuelScoopsFitted=1, MissionAspEncounterState=3)
    expect(out['CommanderFlags'] == 0x40 and out['MissionAspEncounterState'] == 0 and not out['cargo']
           and out['CargoFreeSpace'] == 20, 'cloaking device', out)
    cases += 1
    for pos, pokes in (([0, 50, 9], dict(FuelScoopsFitted=1)), ([0, -50, 9], {}),
                       ([0, -50, 9], dict(FuelScoopsFitted=1, CargoFreeSpace=0)),
                       ([0, -50, -9], dict(FuelScoopsFitted=1, CargoFreeSpace=0))):
        out = contact.run(P9_CANISTER, pos, roles=0x0A, **pokes)
        front, rear = (P9_COLLISION_DAMAGE, 0) if pos[2] >= 0 else (0, P9_COLLISION_DAMAGE)
        expect(out['energy'] == 0 and not out['cargo'] and out['FrontDamageThisUpdate'] == front
               and out['RearDamageThisUpdate'] == rear and out['SoundEffectRequests'] == 4,
               'failed scoop', pos, out)
        cases += 1
    return cases


@check('contact', 'p9-station-docking', ['HandleObjectContact', 'TestStationDocking', 'CrashIntoStation'],
       'pass2',
       'Station slot (+$26 bit 2) inside its radius box: L_DA15 = 1 (CheckDocking then docks) when '
       'it lies ahead (z >= 0), is not hostile, its local z axis points at the player (+$0E sign set) '
       'and |Z.x|, |Z.y| < $1E; with one of them $1E..$6D sound bit 6 and FrontDamageThisUpdate '
       '+= 12 + 2*PlayerSpeed; any other case sets PlayerDeadFlag = $0F.  The station keeps its energy.')
def check_p9_station_docking(ctx):
    contact = P9Contact(ctx)
    station_energy = ctx.pristine[ctx['InitialRuntimeState'] + ctx['InstanceEnergy']]
    cases = 0
    for zx, zy, zz, z, hostile, speed, outcome in (
            (0x00, 0x00, 0xFF, 100, 0, 10, 'dock'), (0x1D, 0x9D, 0xF0, 100, 0, 10, 'dock'),
            (0x1E, 0x00, 0xF0, 100, 0, 10, 'scrape'), (0x00, 0x9E, 0xF0, 50, 0, 3, 'scrape'),
            (0xED, 0x00, 0xC0, 100, 0, 31, 'scrape'), (0x00, 0x6D, 0xC0, 100, 0, 0, 'scrape'),
            (0x6E, 0x00, 0xC0, 100, 0, 10, 'crash'), (0x00, 0xEE, 0xC0, 100, 0, 10, 'crash'),
            (0x00, 0x00, 0x7F, 100, 0, 10, 'crash'), (0x00, 0x00, 0xFF, -100, 0, 10, 'crash'),
            (0x00, 0x00, 0xFF, 100, 4, 10, 'crash')):
        out = contact.run(P9_CORIOLIS, [17, -30, z], slot=0, behaviour=hostile, axis={0: zx, 1: zy, 2: zz},
                          PlayerSpeed=speed)
        expected = dict(dock=(0, 0, 0, 1), scrape=(0, 12 + 2 * speed, 0x40, 0), crash=(0x0F, 0, 0, 0))[outcome]
        got = (out['PlayerDeadFlag'], out['FrontDamageThisUpdate'], out['SoundEffectRequests'], out['L_DA15'])
        expect(got == expected and out['energy'] == station_energy, 'docking', hex(zx), hex(zy), hex(zz), z,
               outcome, got)
        cases += 1
    radius = contact.m.byte(blueprint_headers(ctx)[P9_CORIOLIS] + P9_BLUEPRINT_RADIUS)
    for distance, docked in ((radius - 1, 1), (radius, 0)):
        out = contact.run(P9_CORIOLIS, [distance, 0, 100], slot=0, axis={0: 0, 1: 0, 2: 0xFF})
        expect(out['L_DA15'] == docked, 'station box', distance, out)
        cases += 1
    return cases


@check('contact', 'p9-release-target-locks', ['ReleaseTargetLocks'], 'pass2',
       'With ObjectLoopCounter = H: MissileState 2 locked on H becomes 0 and TargetLostMessage bit 7 '
       'is raised (other states or targets unchanged).  Only when the removed object IX is a missile '
       '(+$26 bit 0) do live slots 1..7 whose +$25 equals H get +$20 bit 4 (explosion); IY is '
       'preserved.')
def check_p9_release_target_locks(ctx):
    m = ctx.machine()
    state, size = ctx['InitialRuntimeState'], ctx['InstanceSize']
    counter = 6                                     # removed object in slot 2
    removed = state + (ctx['InstanceSlotCount'] - counter) * size
    cases = 0
    for missile in (True, False):
        for lock_state, lock_target in ((2, counter), (2, counter - 1), (1, counter), (0, counter)):
            m.reset()
            slots = {0: (240, counter), 1: (5, counter), 3: (5, counter), 4: (0, counter), 5: (9, counter + 1),
                     7: (2, counter)}
            for slot, (energy, target) in slots.items():
                inst = state + slot * size
                m.poke(inst + ctx['InstanceEnergy'], energy)
                m.poke(inst + INSTANCE_FLAGS25, target)
                m.poke(inst + INSTANCE_STATE, 0x40)
            m.poke(removed + INSTANCE_FLAGS26, 1 if missile else 0)
            m.poke('ObjectLoopCounter', counter)
            m.poke('MissileState', lock_state)
            m.poke('MissileTarget', lock_target)
            message = m.byte('TargetLostMessage') & 0x7F
            m.poke('TargetLostMessage', message)
            m.call('ReleaseTargetLocks', ix=removed, iy=0x5A5A, a=0, f=0, bc=0, de=0, hl=0)
            exploded = {slot for slot in range(ctx['InstanceSlotCount'])
                        if m.byte(state + slot * size + INSTANCE_STATE) & 0x10}
            expect(exploded == ({1, 3, 7} if missile else set()) and m.iy() == 0x5A5A, 'explode', missile, exploded)
            released = lock_state == 2 and lock_target == counter
            expect(m.byte('MissileState') == (0 if released else lock_state) and
                   m.byte('TargetLostMessage') == (message | 0x80 if released else message),
                   'missile lock', lock_state, lock_target)
            cases += 1
    return cases


class P9View:
    """Slot-1 instance drawn by DrawObjectInView with an optional fixed random byte."""

    def __init__(self, ctx):
        self.ctx, self.m = ctx, ctx.machine()
        self.inst = ctx['InitialRuntimeState'] + ctx['InstanceSize']

    def setup(self, ship, pos, screen, flags, behaviour=None, roles=0, axis=None):
        ctx, m, inst = self.ctx, self.m, self.inst
        m.reset()
        load_jameson(m)
        m.call('InitialiseShipFromBlueprint', **dict(FRESH_REGISTERS, a=ship, ix=inst))
        for axis_index, value in enumerate(pos):
            put24(m.memory, inst + ctx['InstanceX'] + 3 * axis_index, value)
        m.poke(inst + INSTANCE_STATE, flags)
        m.poke(inst + INSTANCE_FLAGS26, roles)
        if behaviour is not None:
            m.poke(inst + ctx['InstanceBehaviour'], behaviour)
        for component, value in (axis or {}).items():
            m.poke(inst + ctx['InstanceAxisZ'] + 1 + 2 * component, value)
        m.poke('CurrentScreenId', screen)
        m.clear('ViewBitmapBuffer', VIEW_SIZE)
        return m.word(inst + INSTANCE_BLUEPRINT)

    def draw(self, blueprint, random_value=None):
        stubs = None if random_value is None else {'NextRandomByte': p9_random_stub(random_value)}
        self.m.call('DrawObjectInView', limit=3_000_000, stubs=stubs, ix=self.inst, iy=blueprint,
                    a=0, f=0, bc=0, de=0, hl=0)
        return bitmap_pixels(self.m.memory, self.ctx['ViewBitmapBuffer'], VIEW_ROWS)


@check('pipeline', 'p9-explosion-record', ['DrawObjectInView', 'RecordExplosionPosition'], 'pass2',
       'A visible object with +$20 bit 4 is not drawn: +$1C/+$1D = ProjectedX/Y, +$1F = projected size '
       '(L_DA0B), +$1E = $0C + CircleFlags side bits (bit 0 right of centre, bit 1 above, rear/right '
       'views mirrored) and +$20 bit 5 is set; behind or off the view nothing is recorded.')
def check_p9_explosion_record(ctx):
    view = P9View(ctx)
    m, inst = view.m, view.inst
    cases = 0
    for screen, pos, right, above in ((0, (300, -200, 2000), 1, 0), (0, (-300, 200, 2000), 0, 1),
                                      (1, (300, 200, -2000), 0, 1), (1, (-300, -200, -2000), 1, 0),
                                      (2, (-2000, 100, 300), 1, 1), (2, (-2000, -100, -300), 0, 0),
                                      (3, (2000, -100, -300), 1, 0), (3, (2000, 100, 300), 0, 1)):
        blueprint = view.setup(SIDEWINDER, pos, screen, 0x50)
        lit = view.draw(blueprint)
        record = m.memory[inst + INSTANCE_DISC:inst + INSTANCE_DISC + 4]
        expect(not lit and m.byte(inst + INSTANCE_STATE) == 0x70, 'state', screen, pos, lit)
        expect(record == [m.byte('ProjectedX'), m.byte('ProjectedY'), 0x0C | right | above << 1, m.byte('L_DA0B')],
               'record', screen, pos, record)
        cases += 1
    for screen, pos in ((0, (5000, 0, 2000)), (0, (0, 0, -2000)), (2, (2000, 0, 0))):
        blueprint = view.setup(SIDEWINDER, pos, screen, 0x50)
        view.draw(blueprint)
        expect(m.byte(inst + INSTANCE_STATE) == 0x50, 'not recorded', screen, pos)
        cases += 1
    return cases


@check('combat', 'p9-ai-laser-beam', ['DrawObjectInView', 'DrawAiLaserBeam', 'DrawAiBeamFromCentre'], 'pass2',
       'With +$20 bit 3 the view buffer equals the drawing without it OR one DrawLine from the gun '
       'vertex (wireframe) or the projected centre (dot/off-screen, quadrant mirrored in rear/right '
       'views) to (255-r, r) in the opposite quadrant, r = NextRandomByte; bit 3 is cleared and '
       'L_F116 keeps its value.')
def check_p9_ai_laser_beam(ctx):
    view = P9View(ctx)
    m = view.m
    lines = LineMachine(ctx)
    vertex_buffer = ctx['ProjectedVertexBuffer']
    cases = 0
    for ship, pos, screen, value, form in (
            (SIDEWINDER, (300, -200, 0x1500), 0, 40, 'dot'), (SIDEWINDER, (-300, 200, -0x1500), 1, 100, 'dot'),
            (SIDEWINDER, (300, -200, 0x0800), 0, 77, 'wire'), (P9_COBRA_PIRATE, (-200, 300, 0x0600), 0, 200, 'wire'),
            (P9_COBRA_PIRATE, (-0x0600, 300, 200), 2, 10, 'wire'),
            (P9_COBRA_PIRATE, (0x0600, -300, 200), 3, 250, 'wire'),
            (P9_COBRA_PIRATE, (0x3000, 300, 0x0500), 0, 66, 'off')):
        blueprint = view.setup(ship, pos, screen, 0x40)
        plain = view.draw(blueprint, value)
        blueprint = view.setup(ship, pos, screen, 0x48)
        page = m.byte('L_F116')
        beam = view.draw(blueprint, value)
        expect(m.byte(view.inst + INSTANCE_STATE) == 0x40 and m.byte('L_F116') == page, 'bit 3 / page')
        if form == 'wire':
            gun = m.byte(blueprint + P9_BLUEPRINT_GUN)
            d, e, quadrant = m.memory[vertex_buffer + 3 * gun:vertex_buffer + 3 * gun + 3]
        else:
            d, e = m.byte('ProjectedX'), m.byte('ProjectedY')
            quadrant = m.byte('ProjectedQuadrant') ^ (2 if screen & 1 else 0)
        quadrant &= 3
        expected = lines.draw(255 - value, value, d, e, (~quadrant & 3) | quadrant << 2)
        expect(beam == plain | expected and len(beam - plain) > 20, 'beam', ship, pos, screen, form)
        cases += 1
    return cases


@check('pipeline', 'p9-avoidance-in-sights', ['DrawObjectInView', 'CancelAvoidanceInSights'], 'pass2',
       'A counted (+$20 bit 6) hostile (+$21 bit 2) ship near the view centre (ProjectedX+ProjectedY '
       '< $20) whose local z axis has |component| >= $40 along the view axis (z in front/rear '
       'views, x in left/right views) loses the avoidance flag +$26 bit 5; otherwise it stays.')
def check_p9_avoidance_in_sights(ctx):
    view = P9View(ctx)
    m = view.m
    cases = 0
    for pos, screen, flags, behaviour, axis, cleared in (
            ((100, 50, 0x0800), 0, 0x40, 0x04, {2: 0x40}, True),
            ((100, 50, 0x0800), 0, 0x40, 0x04, {2: 0xC0}, True),
            ((100, 50, -0x0800), 1, 0x40, 0x04, {2: 0x7F}, True),
            ((100, 50, 0x0800), 0, 0x40, 0x04, {2: 0x3F}, False),
            ((600, 400, 0x0800), 0, 0x40, 0x04, {2: 0x7F}, False),
            ((100, 50, 0x0800), 0, 0x40, 0x00, {2: 0x7F}, False),
            ((100, 50, 0x0800), 0, 0x00, 0x04, {2: 0x7F}, False),
            ((-0x0800, 50, 100), 2, 0x40, 0x04, {0: 0x7F, 2: 0}, True),
            ((-0x0800, 50, 100), 2, 0x40, 0x04, {0: 0x10, 2: 0x7F}, False)):
        blueprint = view.setup(SIDEWINDER, pos, screen, flags, behaviour=behaviour, roles=0x20, axis=axis)
        view.draw(blueprint)
        expect((m.byte(view.inst + INSTANCE_FLAGS26) & 0x20 == 0) == cleared, 'avoidance', pos, screen, axis)
        cases += 1
    return cases


@check('combat', 'p9-player-laser-rate', ['UpdatePlayerLaser', 'LaserTriggerHeld'], 'pass2',
       'Each call: LaserTemperature -= 2 (not below 0) and KeyFlagsCombat bit 0 is consumed.  A fire '
       'request with temperature < $90 after cooling and a laser on the current view sets '
       'LaserTriggerHeld; the first request fires, held requests fire only when ObjectUpdateCounter '
       'AND 1 (pulse, type 1) or AND 7 (mining, type 4) is 0, beam and military fire every call; '
       'no request clears LaserTriggerHeld.  (L_EC11, where firing continues, is stubbed.)')
def check_p9_player_laser_rate(ctx):
    m = ctx.machine()
    fired = []

    def record_shot(machine):
        fired.append(1)

    def frames(laser, count, temperature=0, keys=None, counter=20, screen=0):
        m.reset()
        load_jameson(m)
        m.poke('CurrentScreenId', screen)
        m.poke(ctx['LaserMounts'] + screen, laser)
        m.poke('LaserTemperature', temperature)
        m.poke('LaserTriggerHeld', 0)
        out = []
        for frame in range(count):
            m.poke('ObjectUpdateCounter', (counter - frame) & 255)
            key = 1 if keys is None else keys[frame]
            m.poke('KeyFlagsCombat', 0x80 | key)
            fired.clear()
            m.call('UpdatePlayerLaser', stubs={'L_EC11': record_shot}, a=0, f=0, bc=0, de=0, hl=0)
            out.append((1 if fired else 0, m.byte('LaserTriggerHeld'), m.byte('LaserTemperature'),
                        m.byte('KeyFlagsCombat')))
        return out

    cases = 0
    for screen in range(4):
        for laser, mask in ((0, None), (1, 1), (2, 0), (3, 0), (4, 7)):
            out = frames(laser, 16, screen=screen)
            expected = [0] * 16 if mask is None else [1 if f == 0 or ((20 - f) & mask) == 0 else 0
                                                       for f in range(16)]
            expect([o[0] for o in out] == expected, 'rate', screen, laser, out)
            expect(all(o[1] == (1 if laser else 0) and o[3] == 0x80 for o in out), 'flag/key', laser)
            cases += 1
    out = frames(1, 6, keys=[1, 1, 0, 1, 1, 1], counter=21)
    expect([o[0] for o in out] == [1, 1, 0, 1, 0, 1] and [o[1] for o in out] == [1, 1, 0, 1, 1, 1], 'release', out)
    cases += 1
    for temperature, fires, after in ((0x91, 1, 0x8F), (0x92, 0, 0x90), (0x01, 1, 0x00), (0x00, 1, 0x00)):
        out = frames(2, 1, temperature=temperature)
        expect(out[0][0] == fires and out[0][2] == after and out[0][1] == fires, 'temperature', temperature, out)
        cases += 1
    return cases
# --- END P9 CHECKS ---

# --- BEGIN P1 CHECKS ---
# Pass-2 checks for $7000..$7BFF (tools/annotations/r1_7000.py).


@check('controls', 'p1-chart-cursor-keys', ['HandleChartCursorKeys'], 'pass2',
       'Only on screens 7 and 8 with L_A80A clear: screen handler 9 + the lowest set bit of '
       '(KeyFlagsFlight AND $0F) OR (KeyFlagsChart AND $70) runs through CallScreenHandler and both '
       'key bytes are cleared; otherwise nothing is called and the key bytes are kept.')
def check_p1_chart_cursor_keys(ctx):
    m = ctx.machine()
    calls = []
    cases = 0
    for screen in range(13):
        for busy in (0, 1, 2):
            for flight in (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0xF0, 0x0C, 0x3A):
                for chart in (0x00, 0x10, 0x20, 0x40, 0x80, 0x0F, 0x70, 0x8F):
                    m.poke('CurrentScreenId', screen)
                    m.poke('L_A80A', busy)
                    m.poke('KeyFlagsFlight', flight)
                    m.poke('KeyFlagsChart', chart)
                    calls.clear()
                    m.call('HandleChartCursorKeys',
                           stubs={'CallScreenHandler': lambda mm: calls.append(mm.reg('a'))})
                    bits = (flight & 0x0F) | (chart & 0x70)
                    if screen in (7, 8) and not busy and bits:
                        handler = 9 + (bits & -bits).bit_length() - 1
                        expect(calls == [handler], screen, busy, flight, chart, calls)
                        expect(m.byte('KeyFlagsFlight') == 0 and m.byte('KeyFlagsChart') == 0,
                               'keys consumed', screen, flight, chart)
                    else:
                        expect(calls == [], 'no handler', screen, busy, flight, chart, calls)
                        expect((m.byte('KeyFlagsFlight'), m.byte('KeyFlagsChart')) == (flight, chart),
                               'keys kept', screen, busy, flight, chart)
                    cases += 1
    return cases


@check('controls', 'p1-title-ship-cycle', ['L_71C8', 'TitleShipCounter'], 'pass2',
       'After the key is released the title counter is incremented and event 9 is dispatched with '
       'C = (counter AND 7) + 1, plus 10 below 6: ship IDs C+2 cycle 13..17, 8, 9, 10.')
def check_p1_title_ship_cycle(ctx):
    m = ctx.machine()
    events = []
    ids = []
    for value in range(256):
        m.poke('LastKeyCode', 0xFF)
        m.poke('TitleShipCounter', value)
        events.clear()
        m.call('L_71C8', stop='L_71E5',
               stubs={'DispatchShipEvent': lambda mm: events.append(mm.reg('a'))})
        counter = (value + 1) & 255
        c = (counter & 7) + 1
        c += 10 if c < 6 else 0
        expect(m.byte('TitleShipCounter') == counter, value)
        expect(events == [(c << 4 | 9) & 255], value, events)
        ids.append(c + 2)
    expect(sorted(set(ids)) == [8, 9, 10, 13, 14, 15, 16, 17], sorted(set(ids)))
    start = ctx.pristine[ctx['TitleShipCounter']]
    sequence = [ids[(start + i) & 255] for i in range(8)]
    return 256, dict(ship_ids_from_tape_counter=sequence)


@check('controls', 'p1-cloak-toggle', ['ToggleCloak', 'CloakKeyDelay'], 'pass2',
       'Acts on every second call when Y (KeyFlagsScreens bit 7) is latched again after one frame '
       'and CommanderFlags bit 6 is set: 1 -> 0 with L=7 colours; otherwise on with EnergyBank3 >= '
       '$28 (value 1, station hostile bit and SharedHostilityAlert cleared, L=$0F), else the '
       'decremented value stays (0 -> $FF) without colours.')
def check_p1_cloak_toggle(ctx):
    m = ctx.machine()
    after_halt = ctx.find('ToggleCloak', 'ArmExpandingSun', [HALT, 0xCB, 0x7E]) + 1
    behaviour = ctx['InitialRuntimeState'] + ctx['InstanceBehaviour']
    colours = []
    cases = 0
    for owned in (0, 1):
        for held in (0, 1):
            for active in (0, 1, 0xFF):
                for energy in (0x27, 0x28, 0xA0):
                    m.reset()
                    m.poke('CloakKeyDelay', 1)
                    m.poke('CommanderFlags', 0x40 * owned)
                    m.poke('CloakingDeviceActive', active)
                    m.poke('EnergyBank3', energy)
                    m.poke(behaviour, 0xFF)
                    m.poke('SharedHostilityAlert', 0x55)
                    m.poke('KeyFlagsScreens', 0x80)
                    colours.clear()

                    def rescan(mm, held=held):
                        if held:
                            mm.poke('KeyFlagsScreens', mm.byte('KeyFlagsScreens') | 0x80)
                    m.call('ToggleCloak', halt=True, hooks={after_halt: rescan},
                           stubs={'FillViewAttributes': lambda mm: colours.append(mm.reg('l'))})
                    expect(m.byte('CloakKeyDelay') == 2, 'delay reloaded')
                    new, colour, cleared = active, [], False
                    if owned and held:
                        new = (active - 1) & 255
                        if new == 0:
                            colour = [0x07]
                        elif energy >= 0x28:
                            new, colour, cleared = 1, [0x0F], True
                    expect(m.byte('CloakingDeviceActive') == new and colours == colour,
                           owned, held, active, energy, m.byte('CloakingDeviceActive'), colours)
                    hostility = (m.byte(behaviour), m.byte('SharedHostilityAlert'))
                    expect(hostility == ((0xFB, 0) if cleared else (0xFF, 0x55)),
                           'hostility', owned, held, active, energy, hostility)
                    cases += 1
    m.reset()
    m.poke('CloakKeyDelay', 2)
    m.poke('KeyFlagsScreens', 0x80)
    m.poke('CommanderFlags', 0x40)
    m.call('ToggleCloak')
    expect(m.byte('CloakKeyDelay') == 1 and m.byte('KeyFlagsScreens') == 0
           and m.byte('CloakingDeviceActive') == ctx.pristine[ctx['CloakingDeviceActive']], 'odd call')
    return cases + 1


@check('controls', 'p1-gauge-all-lengths', ['DrawBarGauge', 'DrawIndicatorGauge', 'StoreGaugeEndByte'],
       'pass2',
       'Every bar length 0..40 and indicator position 2..40 rewrites exactly the five bytes of all '
       'five pixel lines: n leading pixels (bars) or pixels p-2..p-1 (markers), plus the right '
       'border pixel; the bytes on either side are untouched.')
def check_p1_gauge_all_lengths(ctx):
    m = ctx.machine()
    address = m.word('GaugeScreenAddresses')
    rng = random.Random(71)
    cases = 0
    for mode, values in ((0, range(41)), (1, range(2, 41))):
        for value in values:
            for row in range(5):
                for i in range(-1, 6):
                    m.memory[address + 256 * row + i] = rng.randrange(256)
            before = [[m.memory[address + 256 * row + i] for i in (-1, 5)] for row in range(5)]
            m.poke('GaugeIndicatorMode', mode)
            m.call('DrawIndicatorGauge' if mode else 'DrawBarGauge', a=value,
                   de=ctx['GaugeScreenAddresses'])
            if mode:
                bits = ['0'] * 40
                bits[value - 2] = bits[value - 1] = bits[39] = '1'
                expected = ''.join(bits)
            else:
                expected = '1' * value + '0' * (39 - value) + '1' if value < 40 else '1' * 40
            for row in range(5):
                line = ''.join(f'{m.memory[address + 256 * row + i]:08b}' for i in range(5))
                expect(line == expected, mode, value, row, line)
                expect([m.memory[address + 256 * row + i] for i in (-1, 5)] == before[row],
                       'outside bytes', mode, value, row)
            cases += 1
    return cases


def p1_coordinate_overflow_model(coordinate, depth):
    """Bit-level model of ProjectCoordinate for |coordinate| > depth (24-bit magnitudes),
    from its annotation: shift both left until the coordinate's top bit falls out
    (L_76D6 first moves a coordinate word below 256 up one byte), shift the depth once
    more (L_7746) and put the coordinate's top bit back.  Without a depth carry a
    coordinate >= that depth means an offset of 512 or more (None).  Otherwise the
    divisor is $80 OR (depth high byte >> 1) and the dividend the high byte of
    coordinate - (divisor:E).  Returns (divisor, dividend) for DivideFractionAB."""
    h, l, c = coordinate >> 16, (coordinate >> 8) & 255, coordinate & 255
    d, e, b = depth >> 16, (depth >> 8) & 255, depth & 255
    hl, de = h << 8 | l, d << 8 | e
    if h == 0:
        hl, de, stages = l << 8 | c, e << 8 | b, ('word', 'high')
    else:
        stages = ('long', 'word', 'high')
    overflow = 0
    for stage in stages:
        for _ in range(8):
            if stage == 'long':
                value = (hl << 8 | c) << 1
                overflow, hl, c = value >> 24, (value >> 8) & 0xFFFF, value & 255
                if overflow:
                    break
                value = (de << 8 | b) << 1
                de, b = (value >> 8) & 0xFFFF, value & 255
            elif stage == 'word':
                overflow, hl = hl >> 15, (hl << 1) & 0xFFFF
                if overflow:
                    break
                de = (de << 1) & 0xFFFF
            else:
                overflow, hl = hl >> 15, ((hl << 1) & 0xFF00) | (hl & 255)
                if overflow:
                    break
                de = ((de << 1) & 0xFF00) | (de & 255)
        if overflow:
            break
    expect(overflow, 'model: no overflow', coordinate, depth)
    value = (de << 8 | b) << 1
    depth_carry, de = value >> 24, (value >> 8) & 0xFFFF
    hl = 0x8000 | hl >> 1
    if not depth_carry and hl >= de:
        return None
    divisor = 0x80 | (de >> 9)
    return divisor, ((hl - (divisor << 8 | (de & 255))) & 0xFFFF) >> 8


@check('pipeline', 'p1-projection-offset-paths', ['ProjectBodyPosition', 'ProjectCoordinate'], 'pass2',
       'Offsets below 256 (|c| <= depth, bit 2/3 set) are within 2 of min(255, 256*|c|/depth); the '
       '256..511 path (bit clear) matches a bit-level model of L_76D6/L_7746 exactly, including '
       'the not-visible case, and is approximate: within 3 of 256*|c|/depth-256 for 99% of '
       'coordinates with as many significant bits as the depth (x $1774EC / z $176C2A borrows: 173), '
       '-1..+127 too large with more bits (x $180000 / z $0F0000: 206).  Near a body this hides '
       'a disc that should fill columns 136..247 (x $80E5 / z $7E00: 131 instead of 6).  '
       'Depth 1 (1/256) gives 128.')
def check_p1_projection_offset_paths(ctx):
    m = ctx.machine()
    rng = random.Random(72)

    def project(horizontal, vertical, depth):
        for axis, value in enumerate((horizontal, vertical, depth)):
            put24(m.memory, ctx['ProjectionX'] + 3 * axis, value)
        m.poke('CurrentScreenId', 0)
        m.call('ProjectBodyPosition')
        return m.reg('a'), m.byte('CircleOffsetX'), m.byte('CircleOffsetY'), m.byte('CircleFlags')

    worst_fraction, hidden = 0, 0
    errors = {True: Counter(), False: Counter()}   # same number of significant bits?
    for index in range(4000):
        depth = rng.randrange(2, 1 << rng.randrange(2, 23))
        vertical = index & 1                       # odd cases test the second (vertical) call
        if index % 4 < 2:
            value = rng.randrange(0, depth + 1)
        else:
            value = rng.randrange(depth + 1, min(3 * depth + 2, 0x7FFFFF) + 1)
        a, ox, oy, flags = project(0 if vertical else value, value if vertical else 0, depth)
        offset, bit = (oy, 8) if vertical else (ox, 4)
        if value <= depth:
            expect(a == 1 and flags & bit, 'fraction path', value, depth)
            worst_fraction = max(worst_fraction, abs(offset - min(255, value * 256 // depth)))
            continue
        model = p1_coordinate_overflow_model(value, depth)
        if model is None:
            expect(a == 0, 'should be invisible', value, depth)
            hidden += 1
            continue
        expect(a == 1 and not flags & bit and offset == restoring_fraction(model[1], model[0]),
               'overflow path', value, depth, a, offset, model)
        errors[value.bit_length() == depth.bit_length()][offset - (value * 256 // depth - 256)] += 1
    expect(worst_fraction <= 2, 'fraction error', worst_fraction)
    same_close = sum(n for error, n in errors[True].items() if abs(error) <= 3)
    expect(same_close >= 0.99 * sum(errors[True].values()), 'same-length accuracy', errors[True])
    expect(min(errors[False]) >= -1 and max(errors[False]) <= 127, 'longer-coordinate error range')
    golden = [project(0x180000, 0, 0x0F0000)[1], project(0x1774EC, 0, 0x176C2A)[1]]
    expect(golden == [206, 173], golden)
    # Near a body the error can hide a large disc: depth word $7E (radius 255), x = 1.023 * depth.
    # The exact centre is 262 px right of column 128 (offset byte 6, bit 2 clear), and the renderer
    # would fill columns 136..247; the computed 256 + 131 makes DrawCircle return at once.
    near = project(0x80E5, 0, 0x7E00)
    expect(near == (1, 131, 0, 0x0B) and m.byte('CircleRadius') == 255, near)
    lit_columns = []
    for dx in (131, round(0x80E5 * 256 / 0x7E00) - 256):
        m.reset()
        m.clear(ctx['ViewBitmapBuffer'], VIEW_SIZE)
        set_circle(m, 0, dx, 0x0B, 255)
        m.call('DrawFilledCircle', stack=ctx.upper_stack)
        lit_columns.append(len({x for x, _ in bitmap_pixels(m.memory, ctx['ViewBitmapBuffer'], VIEW_ROWS)}))
    expect(lit_columns == [0, 112], lit_columns)
    # Depth 1 (1/256): 23 shifts never move the depth's top bit out; D is the shifted depth.
    edge = [project(value, value, 1)[1:3] for value in (0, 1)]
    expect(edge == [(128, 128), (128, 128)], edge)
    return 4005, dict(worst_fraction_error=worst_fraction, not_visible=hidden,
                      same_length_cases=sum(errors[True].values()), same_length_within_3=same_close,
                      longer_coordinate_cases=sum(errors[False].values()),
                      longer_coordinate_error_range=[min(errors[False]), max(errors[False])])


@check('missions', 'p1-mission-state-on-docking', ['CheckMissionStateOnDocking'], 'pass2',
       'L_A871 = 1 or 2 runs OfferSpecialMission, 5 AwardHighestHonour, 4 EndGameWithMessage with '
       'A = $D4 (" THARGON"); every other value returns without action.')
def check_p1_mission_state_on_docking(ctx):
    m = ctx.machine()
    seen = []
    stubs = {name: (lambda mm, name=name: seen.append((name, mm.reg('a'))))
             for name in ('OfferSpecialMission', 'AwardHighestHonour', 'EndGameWithMessage')}
    for state in range(256):
        m.poke('L_A871', state)
        seen.clear()
        m.call('CheckMissionStateOnDocking', stubs=stubs)
        names = [name for name, _ in seen]
        if state in (1, 2):
            expect(names == ['OfferSpecialMission'], state, seen)
        elif state == 5:
            expect(names == ['AwardHighestHonour'], state, seen)
        elif state == 4:
            expect(seen == [('EndGameWithMessage', 0xD4)], state, seen)
        else:
            expect(seen == [], state, seen)
    return 256


# --- END P1 CHECKS ---

# --- BEGIN P7 CHECKS ---
# Pass 2 (range $BE00..$D3FF): justified padding, docked screen text, security number
# output and the commander tape-load paths.

from skoolkit.simutils import xA, xF                                           # noqa: E402

P7_JUSTIFY_TEXTS = (
    'THE PLANET LAVE IS MOST FAMOUS FOR ITS VAST RAIN FORESTS AND THE LAVIAN TREE GRUB.',
    'THIS PLANET IS PLAGUED BY OCCASIONAL SOLAR ACTIVITY AND DEADLY EDIBLE ARTS GRAPHICS DISCOS.',
    'AAAA BBBBBBBBB CCCCCCCCCCCCCCC DDDDDDDDDDDDDDDDDDDD E FFF.',
    'A BB CCC DDDD EEEEE FFFFFF GGGGGGG HHHHHHHH IIIIIIIII JJJJJJJJJJ K LL MMM NNNN OOOOO PPP QQ.',
)


@check('text', 'p7-justify-padding', ['InsertSpaceInTextBuffer', 'FindPreviousSpace'], 'pass2',
       'In the justified printer each InsertSpaceInTextBuffer call adds one space at an existing '
       'word gap: the calls equal the extra spaces inside the printed lines, every printed line is '
       '30 characters wide and the words keep their order.  PutCharacter and NewLine are stubbed.')
def check_p7_justify_padding(ctx):
    """Stubs as in text/justified-word-wrap: PutCharacter and NewLine only record their output."""
    m = ctx.machine()
    cases = 0
    for text in P7_JUSTIFY_TEXTS:
        m.reset()
        out, gaps = [], []
        stubs = {'PutCharacter': lambda mm: out.append(chr(mm.reg('a'))),
                 'NewLine': lambda mm: out.append('\n')}
        hooks = {'InsertSpaceInTextBuffer': lambda mm: gaps.append(mm.byte(mm.word('JustifyWritePointer')))}
        m.call('StartJustifiedText', stubs=stubs, a=0)
        for character in text:
            m.call('PrintCharacter', stubs=stubs, hooks=hooks, a=ord(character))
        m.call('EndJustifiedText', stubs=stubs, hooks=hooks, a=0)
        lines = ''.join(out).split('\n')
        expect(lines[-1] == '' and all(len(line) == 30 for line in lines[:-1]), text, lines)
        extra = sum(len(line.strip()) - len(' '.join(line.split())) for line in lines[:-1])
        expect(len(gaps) == extra and set(gaps) <= {0x20}, text, len(gaps), extra, gaps)
        expect(' '.join(' '.join(lines).split()).upper() == text, 'word order', text)
        cases += 1
    expect(cases == len(P7_JUSTIFY_TEXTS))
    return cases


def p7_screen_rows(t, entry, **pokes):
    """Run a docked screen; return {row: (first column, text)} from the PutCharacter calls."""
    m = t.fresh()
    for name, value in pokes.items():
        m.poke(name, *(value if isinstance(value, list) else [value]))
    rows = {}

    def put(mm):
        row = rows.setdefault(mm.byte('TextRow'), [mm.byte('TextColumn'), ''])
        row[1] += chr(mm.reg('a'))
    m.call(entry, limit=3_000_000, halt=True, hooks={'PutCharacter': put})
    return m, {row: tuple(value) for row, value in rows.items()}


P7_STATUS_HEAD = {1: 'COMMANDER JAMESON', 4: 'Present System:Lave', 5: 'Hyperspace System:Lave',
                  6: 'Fuel: 7.0 Light Years', 7: 'Cash:   100.0 Cr', 8: 'Legal Status: Clean',
                  9: 'Rating: Harmless', 11: 'EQUIPMENT:'}


@check('commander', 'p7-docked-screen-text', ['ShowCommanderStatus', 'PrintInlineTokenIfSet', 'PrintLaserMount',
                                              'PrintColonTokenAtColumn21', 'NewLineAtColumn5', 'ShowInventory'],
       'pass2',
       'Status screen rows 1, 4..9 and 11, equipment from row 12 at column 5 in the documented order; '
       'the jammer line replaces E.C.M. System; laser types 1..4 on all four mounts; the inventory puts '
       'Large Cargo Bay on row 6 (attributes $05, columns 1..30), Refugees on row 7 and cargo after them.')
def check_p7_docked_screen_text(ctx):
    t = TextMachine(ctx)
    items = {'LargeCargoBayFitted': 'Large Cargo Bay', 'FuelScoopsFitted': 'Fuel Scoops',
             'EnergyBombFitted': 'Energy Bomb', 'EnergyUnitFitted': 'Energy Unit',
             'DockingComputerFitted': 'Docking Computers', 'GalacticHyperdriveFitted': 'Galactic Hyperspace'}
    lasers = ['Pulse Laser', 'Beam Laser', 'Military Laser', 'Mining Laser']
    mounts = ['Front', 'Rear', 'Left', 'Right']
    cases = [
        (dict(), ['Front Pulse Laser']),
        (dict(EcmFitted=1, CommanderFlags=0x40, LaserMounts=[1, 2, 0, 0]),
         ['E.C.M.System', 'Front Pulse Laser', 'Rear Beam Laser', 'Cloaking Device']),
        (dict({name: 0xFF for name in items}, EcmFitted=1, CommanderFlags=0xC0, LaserMounts=[1, 2, 3, 4]),
         ['Large Cargo Bay', 'Fuel Scoops', 'E.C.M.System Jammer', 'Energy Bomb', 'Energy Unit',
          'Docking Computers', 'Galactic Hyperspace'] +
         [f'{mount} {laser}' for mount, laser in zip(mounts, lasers)] + ['Cloaking Device']),
        (dict(EcmFitted=0, CommanderFlags=0x80, LaserMounts=[0, 4, 0, 3]),
         ['E.C.M.System Jammer', 'Rear Mining Laser', 'Right Military Laser']),
        (dict(LaserMounts=[3, 4, 1, 2]), [f'{mount} {lasers[t_ - 1]}' for mount, t_ in zip(mounts, [3, 4, 1, 2])]),
    ]
    for pokes, equipment in cases:
        _, rows = p7_screen_rows(t, 'ShowCommanderStatus', **pokes)
        expected = dict(P7_STATUS_HEAD)
        expected.update({12 + i: text for i, text in enumerate(equipment)})
        expect({row: text for row, (_, text) in rows.items()} == expected, pokes, rows)
        expect(all(rows[12 + i][0] == 5 for i in range(len(equipment))), 'column 5', rows)
    inventory = [
        (dict(LargeCargoBayFitted=1, CommanderFlags=0x20, CargoHold=[5, 0, 3]),
         {6: 'Large Cargo Bay', 7: 'Refugees', 8: 'Food  5t', 9: 'Radioactives  3t'}),
        (dict(LargeCargoBayFitted=0, CommanderFlags=0x00, CargoHold=[0, 2]), {7: 'Textiles  2t'}),
    ]
    attributes_row6 = ATTRIBUTES + 6 * ROW_BYTES
    for pokes, body in inventory:
        m, rows = p7_screen_rows(t, 'ShowInventory', **pokes)
        expected = {1: 'INVENTORY', 3: 'Fuel: 7.0 Light Years', 4: 'Cash:   100.0 Cr'}
        expected.update(body)
        expect({row: text for row, (_, text) in rows.items()} == expected, pokes, rows)
        bar = [m.byte(attributes_row6 + column) for column in range(1, 31)]
        expect((set(bar) == {5}) == bool(pokes['LargeCargoBayFitted']), 'cargo bay attributes', bar)
    return len(cases) + len(inventory)


@check('commander', 'p7-security-number-print', ['AccessMenuSave', 'PrintDecimalHL'], 'pass2',
       'After a save the screen shows "SECURITY NUMBER: " followed by HL in decimal without padding '
       'and DE as exactly five digits (leading zeros), one digit string; HL and DE from the '
       'commander/security-number model.  Entered at the LD HL,$0C01 after "COMMANDER SAVED".')
def check_p7_security_number_print(ctx):
    t = TextMachine(ctx)
    text_column = ctx['TextColumn']
    entry = ctx.find('AccessMenuSave', 'CopyCommanderToTemplate', [0x21, 0x01, 0x0C, 0x22,
                                                                    text_column & 255, text_column >> 8])
    rng = random.Random(77)
    samples = [(0, 0, 0, 0), (65535, 7, 0xFF, 65535)]
    samples += [(rng.randrange(65536), rng.randrange(8), rng.randrange(256), rng.randrange(65536))
                for _ in range(300)]
    for kills, galaxy, flags, money in samples:
        m = t.fresh()
        m.poke_word('CombatScoreLow', kills)
        m.poke('CurrentGalaxy', galaxy)
        m.poke('CommanderFlags', flags)
        m.poke_word('CashHigh', money)
        out = []
        m.call(entry, stop='CopyCommanderToTemplate', hooks={'PutCharacter': lambda mm: out.append(chr(mm.reg('a')))})
        hl, de = security_model(kills, galaxy, flags, money)
        expect(''.join(out).upper() == f'SECURITY NUMBER: {hl}{de:05d}', kills, galaxy, flags, money, out)
        expect((m.byte('TextRow'), m.byte('NumberFieldWidth'), m.byte('LeadingZeroFlag')) == (12, 0, 1), 'state')
    return len(samples)


@check('commander', 'p7-tape-load-paths', ['LoadCommanderRecord', 'CommanderLoadedFlag', 'CopyCommanderToTemplate',
                                           'TapeLoadFailed'], 'pass2',
       'With ROM LD-BYTES stubbed (IX = ActiveCommanderRecord, DE = 104, A\' = $FF, carry set): records are '
       'loaded until the name matches (an empty typed name accepts the first), CommanderLoadedFlag is 1 '
       'after any record, the accepted record becomes the template; a failed load with key $20 (BREAK) '
       'keeps the partial bytes, any other key restores the record from the template.')
def check_p7_tape_load_paths(ctx):
    t = TextMachine(ctx)
    record, size = ctx['ActiveCommanderRecord'], ctx['ActiveCommanderRecordSize']
    template, persistent = ctx['CommanderTemplateBuffer'], ctx['CommanderTemplateBufferSize']
    name_field = 11                                     # 10 characters and the terminator

    def tape_record(name, fill):
        return list(name.encode()) + [0] * (name_field - len(name)) + [fill] * (size - name_field)

    def run(typed, tape, key=0xFF, partial=()):
        m = t.fresh()
        m.poke('ControlOptions', m.byte('ControlOptions') & 0x7F)      # no ROM BEEPER
        m.poke('NameInputBuffer', *(list(typed.encode()) + [0]))
        m.poke('LastKeyCode', key)
        queue, loads = list(tape), []

        def ld_bytes(mm):
            expect((mm.ix(), mm.pair('de'), mm.r[xA], mm.r[xF] & 1) == (record, size, 0xFF, 1), 'LD-BYTES registers')
            loads.append(1)
            if queue:
                mm.poke(record, *queue.pop(0))
                mm.r[F] |= 1
            else:
                mm.poke(record, *partial)
                mm.r[F] &= 0xFE
        m.call('LoadCommanderRecord', stop='L_D3ED', halt=True, stubs={'RomLdBytesAfterSetup': ld_bytes})
        return m, len(loads)

    jameson = t.fresh().memory[template:template + persistent]
    alice, bob = tape_record('ALICE', 1), tape_record('BOB', 2)
    m, loads = run('BOB', [alice, bob])
    expect(loads == 2 and m.byte('CommanderLoadedFlag') == 1 and m.memory[template:template + persistent] ==
           bob[:persistent], 'second record matches', loads)
    m, loads = run('', [alice])
    expect(loads == 1 and m.memory[template:template + persistent] == alice[:persistent], 'empty name')
    m, loads = run('ABCDEFGHIJ', [tape_record('ABCDEFGHIK', 3), tape_record('ABCDEFGHIJ', 4)])
    expect(loads == 2 and m.memory[template + name_field] == 4, 'ten-character names')
    partial = [0x55] * 20
    m, loads = run('BOB', [], key=0x41, partial=partial)
    expect(loads == 1 and m.memory[record:record + persistent] == jameson and m.byte('CommanderLoadedFlag') == 0,
           'tape error restores the template')
    m, loads = run('BOB', [], key=0x20, partial=partial)
    expect(m.memory[record:record + len(partial)] == partial and m.memory[template:template + persistent] ==
           jameson and m.byte('CommanderLoadedFlag') == 0, 'BREAK keeps the partial record')
    m, loads = run('BOB', [alice], key=0x20)
    expect(loads == 2 and m.text(record, name_field) == 'ALICE' and m.memory[template:template + persistent] ==
           jameson and m.byte('CommanderLoadedFlag') == 1, 'rejected record, then BREAK')
    return 6


# --- END P7 CHECKS ---

# --- BEGIN P2 CHECKS ---
# Pass 2 checks for $7C00..$85FF (tools/annotations/r2_7c00.py).


@check('missions', 'p2-hyperspace-key-latch', ['HyperspaceKeyLatch', 'CheckHyperspaceKeys', 'CheckDocking',
                                               'FinishHyperspaceArrival'], 'pass2',
       'CheckHyperspaceKeys sets HyperspaceKeyLatch whenever it consumes a hyperspace key bit, also '
       'for refused jumps (countdown running, zero distance, no galactic drive); while it is set '
       'CheckDocking docks neither on station contact nor with the docking computer key; '
       'FinishHyperspaceArrival clears it.')
def check_p2_hyperspace_key_latch(ctx):
    """DockWithStation and SnapCursorToNearestSystem are emulated RET stubs (no byte changed)."""
    m = ctx.machine()
    latch = 'HyperspaceKeyLatch'
    refused = (  # (key bits, countdown, galactic drive, distance)
        (0x10, 5, 0, 3), (0x30, 5, 1, 3),     # countdown already running
        (0x10, 0, 0, 0),                      # target is the current system
        (0x30, 0, 0, 3))                      # galactic jump without the hyperdrive
    for keys, countdown, drive, distance in refused:
        m.reset()
        m.poke(latch, 0)
        m.poke('KeyFlagsViews', keys | 0x01)
        m.poke('HyperspaceCountdown', countdown)
        m.poke('FlightCondition', 1)
        m.poke('GalacticHyperdriveFitted', drive)
        m.poke('L_A80A', 0)
        m.poke_word('SelectedSystemDistance', distance)
        m.call('CheckHyperspaceKeys', stubs={'SnapCursorToNearestSystem': None})
        expect(m.byte(latch) == 1 and m.byte('KeyFlagsViews') == 0x01, 'latch set', keys, countdown)
        expect(m.byte('HyperspaceCountdown') == countdown and m.byte('L_A80A') == 0, 'refused', keys)
    cases = len(refused)
    for value in (1, 0):
        docked = []
        m.reset()
        m.poke(latch, value)
        m.poke('L_DA15', 1)                   # station contact
        m.call('CheckDocking', stubs={'DockWithStation': lambda mm: docked.append(1)})
        expect(bool(docked) == (value == 0) and m.byte('L_DA15') == value, 'contact', value)
        docked = []
        m.reset()
        m.poke(latch, value)
        m.poke('L_DA15', 0)
        m.poke('KeyFlagsCombat', 0x80)        # docking computer key C
        m.poke('StationPresent', 1)
        m.poke('DockingComputerFitted', 1)
        m.poke('FlightCondition', 1)
        m.poke('L_A80A', 0)
        m.poke(ctx['InitialRuntimeState'] + ctx['InstanceBehaviour'], 0)
        m.call('CheckDocking', stubs={'DockWithStation': lambda mm: docked.append(1)})
        expect(bool(docked) == (value == 0) and m.byte('KeyFlagsCombat') == (0x80 if value else 0),
               'docking computer', value)
        cases += 2
    m.reset()
    m.poke(latch, 1)
    m.call('FinishHyperspaceArrival')
    expect(m.byte(latch) == 0, 'cleared on arrival')
    return cases + 1


@check('circles', 'p2-circle-offset-bit8', ['DrawCircle', 'DrawFilledCircle', 'DrawCircleOutline', 'CircleFlags'],
       'pass2',
       'With CircleFlags bit 2 (x) or bit 3 (y) clear the offset is 256 + the stored byte: filled '
       'discs light exactly the view pixels of a disc centred that far away (within 1.5 pixels of '
       'the edge) and outlines stay on its circle; centres out of reach draw nothing.')
def check_p2_circle_offset_bit8(ctx):
    m = ctx.machine()
    buffer = ctx['ViewBitmapBuffer']
    cases = 0
    for dy, dx, flags, radius in ((10, 16, 0x0B, 200), (10, 16, 0x0A, 200), (0, 0x30, 0x09, 230),
                                  (20, 0x50, 0x08, 250), (0x10, 30, 0x07, 220), (0x10, 30, 0x05, 220),
                                  (0x20, 0, 0x04, 240), (5, 5, 0x00, 255), (0x30, 0x70, 0x01, 255)):
        tx = dx + (0 if flags & 4 else 256)
        ty = dy + (0 if flags & 8 else 256)
        cx = 128 + tx if flags & 1 else 128 - tx
        cy = 64 - ty if flags & 2 else 64 + ty
        inner = {(x, y) for x in range(8, 248) for y in range(VIEW_ROWS)
                 if math.hypot(x - cx, y - cy) <= radius - 1.5}
        for entry in ('DrawFilledCircle', 'DrawCircleOutline'):
            m.reset()
            m.clear(buffer, VIEW_SIZE)
            set_circle(m, dy, dx, flags, radius)
            m.call(entry, stack=ctx.upper_stack)
            lit = bitmap_pixels(m.memory, buffer, VIEW_ROWS)
            if entry == 'DrawFilledCircle':
                expect(inner <= lit and all(math.hypot(x - cx, y - cy) <= radius + 1.5 for x, y in lit),
                       'disc', dy, dx, flags, radius)
            else:
                expect(all(radius - 1.6 <= math.hypot(x - cx, y - cy) <= radius + 2.1 for x, y in lit),
                       'outline', dy, dx, flags, radius)
            expect(bool(lit) == bool(inner), 'visibility', entry, dy, dx, flags)
            cases += 1
    return cases


@check('circles', 'p2-span-end-locators', ['LocateSpanLeftEnd', 'LocateSpanRightEnd', 'SavedLeftEndMask'],
       'pass2',
       'For every x and sample view rows: HL = view-buffer address of (x, row); fill mode B = pixels '
       'right of x, C = pixels left of x; outline mode B or C = pixel x; LocateSpanLeftEnd sets E = L; '
       'LocateSpanRightEnd preserves B (kept in SavedLeftEndMask), D and E.')
def check_p2_span_end_locators(ctx):
    m = ctx.machine()
    buffer = ctx['ViewBitmapBuffer']
    cases = 0
    for outline in (0, 1):
        m.poke('CircleOutlineFlag', outline)
        for row in (0, 1, 7, 8, 63, 64, 100, 127):
            for x in range(256):
                k = x & 7
                address = buffer + screen_offset(x, row)
                m.call('LocateSpanLeftEnd', a=x, c=row, d=0x5A, e=0)
                left = (0x80 >> k) if outline else (0xFF >> (k + 1))
                expect((m.pair('hl'), m.reg('b'), m.reg('e'), m.reg('d')) ==
                       (address, left, address & 255, 0x5A), 'left end', outline, row, x)
                m.call('LocateSpanRightEnd', a=x, c=row, b=0xA5, d=0x5A, e=0x3C)
                right = (0x80 >> k) if outline else ((0xFF << (8 - k)) & 0xFF)
                expect((m.pair('hl'), m.reg('c'), m.reg('b'), m.reg('d'), m.reg('e')) ==
                       (address, right, 0xA5, 0x5A, 0x3C) and m.byte('SavedLeftEndMask') == 0xA5,
                       'right end', outline, row, x)
                cases += 2
    return cases


@check('circles', 'p2-screen-circle-minimum-radius', ['DrawScreenCircle', 'DrawCircleOutline'], 'pass2',
       'DrawScreenCircle draws nothing for a radius below 9 (DrawCircleOutline limit) and a circle '
       'for radius 9; it returns A = 0 with every patched byte restored.')
def check_p2_screen_circle_minimum_radius(ctx):
    m = ctx.machine()
    image = ctx.pristine
    count = image[ctx['CirclePatchCount']]
    targets = [image[ctx['CirclePatchTargets'] + 2 * i] | image[ctx['CirclePatchTargets'] + 2 * i + 1] << 8
               for i in range(count)]
    cases = 0
    for x, y in ((97, 96), (128, 96), (40, 150)):
        for radius in (0, 8, 9):
            m.reset()
            m.clear(SCREEN, SCREEN_SIZE)
            m.poke('ShapeCentreX', x, y, radius)
            m.call('DrawScreenCircle', a=0x77)
            lit = bitmap_pixels(m.memory, SCREEN, 192)
            expect(bool(lit) == (radius >= 9) and m.reg('a') == 0, 'radius limit', x, y, radius)
            expect(all(m.memory[t] == image[t] for t in targets), 'patches restored', x, y, radius)
            cases += 1
    return cases


# --- END P2 CHECKS ---

# --- BEGIN INTEGRATION CHECKS ---
@check('text', 'justified-full-stop-loss', ['PrintCharacter', 'EndJustifiedText'], 'integration',
       'Original quirk: a character that arrives as the 31st character of a justified line is '
       'stored after the 30 printed characters and lost; here the final full stop disappears.')
def check_justified_full_stop_loss(ctx):
    """Stubs as in text/justified-word-wrap: PutCharacter and NewLine only record output."""
    m = ctx.machine()
    out = []
    stubs = {'PutCharacter': lambda mm: out.append(chr(mm.reg('a'))),
             'NewLine': lambda mm: out.append('\n')}
    m.call('StartJustifiedText', stubs=stubs, a=0)
    text = 'A BB CCC DDDD EEEEE FFFFFF GGGGGGG HHHHHHHH IIIIIIIII JJJJJJJJJJ K LL MMM NNNN OOOOO.'
    for character in text:
        m.call('PrintCharacter', stubs=stubs, a=ord(character))
    m.call('EndJustifiedText', stubs=stubs, a=0)
    lines = ''.join(out).split('\n')
    expect(lines[2] == 'Jjjjjjjjjj K Ll Mmm Nnnn Ooooo', lines)
    expect('.' not in ''.join(out), 'the full stop is printed after all', lines)
    return 1


@check('text', 'description-full-stop-loss', ['DeriveSelectedSystemData', 'GenerateSystemName',
                                               'L_BA49'], 'integration',
       'The same quirk in real game text: the "DATA ON" description of SOCELAGE (galaxy 1, '
       'system 45) is generated with a final full stop, but its second line is exactly 30 '
       'characters wide, so the full stop never reaches the screen.  A scan of all 2048 '
       'descriptions found 72 such cases, always the final full stop.')
def check_description_full_stop_loss(ctx):
    """Stubs as in text/justified-word-wrap: PutCharacter and NewLine only record output."""
    m = ctx.machine()
    load_jameson(m)
    m.call('LoadGalaxySeedsToGenerator', **ZERO_REGISTERS)
    for _ in range(46):                                  # systems 0..45
        m.call('DeriveSelectedSystemData', **ZERO_REGISTERS)
        m.call('GenerateSystemName', **ZERO_REGISTERS)
    name = m.text('GeneratedSystemName')
    expect(name == 'SOCELAGE', name)
    m.poke('SelectedSystemName', *(name.encode() + bytes(9 - len(name))))
    fed, out = [], []
    hooks = {'PrintCharacter': lambda mm: fed.append(chr(mm.reg('a')))
             if mm.byte('TextRedirectFlag') == 1 else None}
    stubs = {'PutCharacter': lambda mm: out.append(chr(mm.reg('a'))),
             'NewLine': lambda mm: out.append('\n')}
    m.call('L_BA49', hooks=hooks, stubs=stubs, limit=3_000_000, halt=True, **ZERO_REGISTERS)
    lines = ''.join(out).split('\n')
    expect(''.join(fed).endswith('GOAT MEAT.'), ''.join(fed))
    expect(lines[:2] == ['This  planet  is    reasonably', 'noted for Its Exotic Goat Meat'], lines)
    expect('.' not in ''.join(out), lines)
    return 1


def alternating_roll_bytes(hold, cycles):
    """PlayerRoll bytes while M and N are held alternately for `hold` updates each, following
    UpdateFlightControls without the damping and recentring options: steps of $FF on the
    sign-magnitude accumulator, high byte 0..15."""
    negative, magnitude, rolls = False, 0, []
    for _ in range(cycles):
        for left in (False, True):
            for _ in range(hold):
                if magnitude == 0:
                    negative, magnitude = left, 0xFF
                elif negative == left:
                    magnitude += 0xFF if magnitude + 0xFF < 0x1000 else 0
                else:
                    magnitude -= 0xFF
                    if magnitude < 0:
                        negative, magnitude = False, 0
                rolls.append(magnitude >> 8 | (0x80 if negative else 0))
    return rolls


@check('maths', 'roll-reversal-drift', ['ApplyPlayerMotion', 'AddScaledCoordinate'], 'integration',
       'Original quirk: ApplyPlayerMotion rolls a position with two shear steps in a fixed order '
       '(x -= y*a, then y += x*a with the new x, a = 2*roll/256).  A roll to the right is not '
       'undone by a roll to the left.  M and N held alternately for 32 updates each (roll ramps '
       'to 15 and to -15) for 20 cycles move the planet 4.98 times further from the view axis '
       'at unchanged depth; the same order in exact arithmetic gives 6.2 and a true rotation '
       '1.0.  The same number of updates in one direction does not push it outward.')
def check_roll_reversal_drift(ctx):
    planet, start = ctx['PlanetPosition'], (0x030000, 0x010000, 0x080000)

    def run(rolls):
        m = ctx.machine()
        for axis, value in enumerate(start):
            put24(m.memory, planet + 3 * axis, value)
        m.poke('PlayerPitch', 0)
        m.poke('PlayerSpeed', 0)
        for roll in rolls:
            m.poke('PlayerRoll', roll)
            m.call('ApplyPlayerMotion', ix=planet, **ZERO_REGISTERS)
        x, y, z = (get24(m.memory, planet + 3 * axis) for axis in range(3))
        expect(z == start[2] - 2 * len(rolls), 'depth moves only by the speed step', z)
        return math.hypot(x, y) / math.hypot(*start[:2])

    def model(rolls, rotation):
        x, y = start[:2]
        for roll in rolls:
            a = (roll & 0x7F) * (-2 if roll & 0x80 else 2) / 256
            if rotation:
                x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            else:
                x -= y * a
                y += x * a
        return math.hypot(x, y) / math.hypot(*start[:2])

    rolls = alternating_roll_bytes(32, 20)
    expect(rolls[:16] == list(range(16)) and rolls[63] == 0x8F
           and set(rolls) == set(range(16)) | set(range(0x80, 0x90)), 'roll ramp', rolls[:64])
    game, shear, rotation = run(rolls), model(rolls, False), model(rolls, True)
    one_way = run([0x0F] * len(rolls))
    expect(round(game, 2) == 4.98 and round(shear, 1) == 6.2 and abs(rotation - 1) < 1e-9,
           game, shear, rotation)
    expect(one_way < 1, 'one direction does not push outward', one_way)
    return 2, dict(alternating_game=round(game, 3), alternating_exact_shear=round(shear, 3),
                   alternating_true_rotation=round(rotation, 3), one_direction_game=round(one_way, 3))
# --- END INTEGRATION CHECKS ---

# --- BEGIN P3 CHECKS ---
# Pass-2 checks of the $8600..$91FF annotations: screen keys, freeze-mode options, scanner
# contact geometry, condition colour and the commodity table format.


@check('input', 'p3-screen-keys', ['HandleScreenKeys', 'SelectScreen', 'CallScreenHandler',
                                   'ClearViewAndScreenKeys'], 'pass2',
       'Keys pressed through ScanKeyboard, then HandleScreenKeys: docked, 1 calls StartStationTunnel '
       'and 2/3/4 select screens 4..6 with handlers 0..2; in flight 1..4 select cockpit views 0..3 '
       'without a handler; I, O, P, K, L, ENTER select screens 7..12 with handlers 3..8 (table '
       'entries BuyCargoScreen..ShowInventory); a screen >= 7 that is already shown is not redrawn; '
       'L_A80A refuses views 1..3 (front view instead); both key bytes end cleared.')
def check_p3_screen_keys(ctx):
    m = ctx.machine()
    ports = InputPorts()
    m.sim.set_tracer(ports)
    handlers = ('BuyCargoScreen', 'SellCargoScreen', 'EquipShipScreen', 'DrawGalacticChart',
                'DrawShortRangeChart', 'DisplaySystemData', 'ShowMarketPrices', 'ShowCommanderStatus',
                'ShowInventory')
    table = ctx['ScreenFunctionTable']
    image = ctx.pristine
    for index, name in enumerate(handlers):
        entry = table + 3 * index
        expect(image[entry] == 0xC3 and image[entry + 1] | image[entry + 2] << 8 == ctx[name],
               'ScreenFunctionTable entry', index, name)
    calls = []
    stubs = {'CallScreenHandler': lambda mm: calls.append(mm.reg('a')),
             'StartStationTunnel': lambda mm: calls.append('launch')}

    def press(key, condition, screen=2, mode=0):
        m.reset()
        m.poke('FlightCondition', condition)
        m.poke('CurrentScreenId', screen)
        m.poke('L_A80A', mode)
        m.poke('L_A80B', 0)
        m.poke('ControlOptions', 0x8C)
        m.clear('KeyFlagsScreens', 5)
        ports.keys = {key}
        m.call('ScanKeyboard')
        ports.keys = set()
        del calls[:]
        m.call('HandleScreenKeys', stack=ctx.upper_stack, stubs=stubs)
        expect(m.byte('KeyFlagsViews') == 0 and m.byte('KeyFlagsScreens') == 0, 'keys cleared', key)
        return m.byte('CurrentScreenId'), list(calls)

    golden = {('1', 0): (2, ['launch']), ('2', 0): (4, [0]), ('3', 0): (5, [1]), ('4', 0): (6, [2]),
              ('1', 4): (0, []), ('2', 4): (1, []), ('3', 4): (2, []), ('4', 4): (3, [])}
    for index, key in enumerate(('I', 'O', 'P', 'K', 'L', 'ENTER')):
        for condition in (0, 4):
            golden[(key, condition)] = (7 + index, [3 + index])
    for (key, condition), expected in golden.items():
        got = press(key, condition)
        expect(got == expected, key, condition, got)
    expect(press('I', 4, screen=7) == (7, []), 'shown screen >= 7 is not redrawn')
    expect(press('2', 0, screen=4) == (4, [0]), 'docked screens are redrawn')
    expect(press('3', 4, mode=1) == (0, []), 'L_A80A refuses view 2')
    expect(press('P', 4, mode=1) == (9, [5]), 'L_A80A allows full screens')
    return len(handlers) + len(golden) + 4


@check('input', 'p3-freeze-options', ['HandleFreezeMode', 'ToggleFreezeOptionB', 'ToggleFreezeOptionD',
                                      'ToggleFreezeOptionF', 'ToggleFreezeOptionR', 'ToggleFreezeOptionY',
                                      'SelectSoundOff', 'SelectSoundOn', 'ToggleControlDevice',
                                      'ClearKeyFlags', 'RequestNewGame'], 'pass2',
       'Freeze loop driven frame by frame through LastKeyCode: B, D, F, R, Y toggle ControlOptions bits '
       '4, 3, 6, 2, 5; Q clears and S sets bit 7 (S also clears SoundEffectRequests); K swaps the '
       'keyboard and the SelectedJoystickType device (nothing without one); each option beeps once, '
       'other keys do nothing; SPACE returns carry clear and 1 carry set, both with the five key bytes '
       'cleared; without the CAPS SHIFT bit it returns at once.  Through ScanKeyboard, bit 4 swaps '
       'the roll (N/M) and pitch (X/S) key bits and bit 5 swaps the pitch bits only.')
def check_p3_freeze_options(ctx):
    m = ctx.machine()
    script, snapshots, beeps = [], [], []
    keys = ctx['KeyFlagsScreens']

    def released(mm):
        snapshots.append(mm.byte('ControlOptions'))
        mm.poke('LastKeyCode', 0xFF)

    def next_key(mm):
        mm.poke('LastKeyCode', script.pop(0))

    def freeze(sequence, options=0x8C, joystick=2, views=0x80):
        m.reset()
        m.poke('ControlOptions', options)
        m.poke('SelectedJoystickType', joystick)
        m.poke('SoundEffectRequests', 0x55)
        m.poke(keys, 0x11, 0x22, views, 0x44, 0x55)
        script[:] = [ord(k) for k in sequence]
        del snapshots[:], beeps[:]
        m.call('HandleFreezeMode', stack=ctx.upper_stack, halt=True,
               hooks={'L_8F71': released, 'L_8F78': next_key},
               stubs={'PlayOptionBeep': lambda mm: beeps.append(1)})
        expect(not script, 'unused keys', script)
        return m.carry(), m.byte('ControlOptions'), list(snapshots), len(beeps)

    carry, options, seen, played = freeze('BDFRYQSKKX ')
    expect(seen == [0x8C, 0x9C, 0x94, 0xD4, 0xD0, 0xF0, 0x70, 0xF0, 0xF2, 0xF0, 0xF0], [hex(v) for v in seen])
    expect(carry == 0 and options == 0xF0 and played == 9, 'SPACE', carry, hex(options), played)
    expect(m.memory[keys:keys + 5] == [0] * 5, 'keys cleared by SPACE')
    freeze('S ')
    expect(m.byte('SoundEffectRequests') == 0, 'S clears the requests')
    freeze('Q ')
    expect(m.byte('SoundEffectRequests') == 0x55, 'Q keeps the requests')
    carry, options, seen, played = freeze('K ', joystick=0)
    expect(options == 0x8C and played == 1, 'K without a joystick', hex(options), played)
    carry, options, seen, played = freeze('1')
    expect(carry == 1 and options == 0x8C and played == 0, '1: new game', carry, played)
    expect(m.memory[keys:keys + 5] == [0] * 5, 'keys cleared by 1')
    carry, options, seen, played = freeze('', views=0x7F)
    expect(not seen and carry == 0 and m.byte('KeyFlagsViews') == 0x7F, 'no freeze key')
    ports = InputPorts()
    m.sim.set_tracer(ports)
    swaps = {0x8C: {'N': 1, 'M': 2, 'X': 4, 'S': 8}, 0x9C: {'N': 2, 'M': 1, 'X': 8, 'S': 4},
             0xAC: {'N': 1, 'M': 2, 'X': 8, 'S': 4}}
    for options, mapping in swaps.items():
        for key, bit in mapping.items():
            m.reset()
            m.clear(keys, 8)
            m.poke('ControlOptions', options)
            ports.keys = {key}
            m.call('ScanKeyboard')
            expect(m.byte('KeyFlagsFlight') & 0x0F == bit, 'swap', hex(options), key)
    return 6 + sum(len(mapping) for mapping in swaps.values())


@check('scanner', 'p3-scanner-geometry', ['DrawScannerContacts', 'L_8DBA', 'L_8DCC',
                                         'SetConditionYellowForShips'], 'pass2',
       'One contact at x = +/-(dx*256/0.75), y = z = 0: stick column 123 + dx (124 - dx when x is '
       'negative) on row 165, dash from that column two pixels to the left; dx = 4 lands one row '
       'lower (+) or higher (-) because B = 0 makes the byte loop run 256 times.  Tallest upward '
       'stick: in column 15 the climb stops at the top of the bottom third, elsewhere its dash lands '
       'on screen row 127; downward sticks stop at the bottom of the screen.  The condition colour '
       'becomes 6 when L_DA1A is non-zero unless it is 2 or $63.')
def check_p3_scanner_geometry(ctx):
    m = ctx.machine()
    size, state = ctx['InstanceSize'], ctx['InitialRuntimeState']

    def contact(x, y, z):
        m.reset()
        m.clear(SCREEN, SCREEN_SIZE)
        m.poke('LastActiveObjectEnergy', 1)
        m.poke('L_DA1A', 0)
        m.poke('ScannerContactsDrawn', 0)
        for slot in range(ctx['InstanceSlotCount']):
            m.poke(state + slot * size + ctx['InstanceEnergy'], 0)
        for axis, value in enumerate((x, y, z)):
            put24(m.memory, state + size + 3 * axis, value)
        m.poke(state + size + ctx['InstanceEnergy'], 0x40)
        m.call('DrawScannerContacts', stack=ctx.upper_stack)
        return bitmap_pixels(m.memory, SCREEN, 192)

    cases = 0
    for dx in range(14):
        for sign in (1, -1):
            lit = contact(sign * ((dx * 1024 + 2) // 3 + 1), 0, 0)
            expect(m.byte('ScannerDotX') == dx | (0x80 if sign < 0 else 0), 'dx', dx, sign)
            column = 123 + dx if sign > 0 else 124 - dx
            row = 165 + (sign if dx == 4 else 0)
            expect(lit == {(column - 2, row), (column - 1, row), (column, row)}, dx, sign, sorted(lit))
            cases += 1
    top = 0x3FFF
    lit = contact(0, top, top)
    expect(min(y for _, y in lit) == 135 and {x for x, _ in lit} == {123}, 'column 15 stops', sorted(lit))
    lit = contact(0x1000, top, top)
    expect({(133, 127), (134, 127), (135, 127)} <= lit and min(y for _, y in lit) == 127, 'dash on row 127')
    lit = contact(0x1000, -top, -top)
    expect(lit == {(135, y) for y in range(184, 192)}, 'downward stick stops at the bottom', sorted(lit))
    cases += 3
    golden = {(1, 4): 6, (1, 0): 6, (1, 6): 6, (1, 2): 2, (1, 0x63): 0x63, (0, 4): 4}
    for (ships, condition), expected in golden.items():
        m.reset()
        m.poke('L_DA1A', ships)
        m.poke('FlightCondition', condition)
        m.call('SetConditionYellowForShips')
        expect(m.byte('FlightCondition') == expected, 'condition', ships, condition)
    return cases + len(golden)


def commodity_model(record, economy, fluctuation):
    """Stock byte and price word of one CommodityTable record (ComputeMarket arithmetic)."""
    price, flags, quantity, mask = record
    term = (flags & 0x1F) * economy & 0xFF
    lowered = (-(term + 1)) & 0xFF
    stock = ((fluctuation & mask) + quantity + (term if flags & 0x80 else lowered)) & 0xFF
    stock = 0 if stock & 0x80 else stock & 0x3F
    value = ((fluctuation & mask) + price + (lowered if flags & 0x80 else term)) & 0xFF
    return stock, value * 4


@check('economy', 'p3-commodity-table', ['CommodityTable', 'ComputeMarket'], 'pass2',
       'CommodityTable holds 17 four-byte records (base price; economy factor in bits 0..4 and '
       'direction in bit 7; base stock; fluctuation mask): a model of these fields reproduces every '
       'MarketPrices word and MarketStock byte of ComputeMarket for economies 0..7 and five '
       'fluctuation values; ALIEN ITEMS (record 16) has no stock.')
def check_p3_commodity_table(ctx):
    m = ctx.machine()
    base = ctx['CommodityTable']
    records = [tuple(ctx.pristine[base + 4 * i:base + 4 * i + 4]) for i in range(17)]
    expect(base + 17 * 4 == ctx['EquipmentPriceTable'], 'table length')
    cases = 0
    for economy in range(8):
        for fluctuation in (0x00, 0x2E, 0x55, 0xAA, 0xFF):
            m.reset()
            m.poke('SelectedSystemEconomy', economy)
            m.poke('MarketFluctuation', fluctuation)
            m.call('ComputeMarket', **ZERO_REGISTERS)
            for i, record in enumerate(records):
                stock, price = commodity_model(record, economy, fluctuation)
                stock = 0 if i == 16 else stock
                got = (m.byte(ctx['MarketStock'] + i), m.word(ctx['MarketPrices'] + 2 * i))
                expect(got == (stock, price), economy, fluctuation, i, got, (stock, price))
            cases += 1
    return cases
# --- END P3 CHECKS ---

# --- BEGIN P4 CHECKS ---
# Pass-2 checks for $9200..$A3FF: energy bomb and view attributes, launch reset and
# instrument colours, Torus jump side effects, roll/pitch/side-view dust models.

P4_VIEW_CELLS = [ATTRIBUTES + row * ROW_BYTES + column for row in range(16) for column in range(1, 31)]


def p4_divide_fraction(a, b):
    """Model of DivideToFractionD: 8 quotient bits of a*256/b with the $FE sentinel."""
    d = 0xFE
    while True:
        a *= 2
        carry, a = a >> 8, a & 0xFF
        if carry or a >= b:
            a = (a - b) & 0xFF
            out, d = d >> 7, ((d << 1) | 1) & 0xFF
        else:
            out, d = d >> 7, (d << 1) & 0xFF
        if not out:
            return d


@check('missions', 'p4-energy-bomb-use', ['UseEnergyBomb', 'FlashViewAttributes', 'FillViewAttributes'],
       'pass2',
       'FillViewAttributes fills rows 0..15, columns 1..30 only, with L AND 7 without the cloak, L '
       'while CloakingDeviceActive is nonzero, then AND $3A while L_A843 is set, returning A = B = 0 '
       'and H = L = the value; the L_9291 entry skips the cloak mask.  UseEnergyBomb acts only with '
       'key bit 5 and a nonzero EnergyBombFitted: it clears that byte, sets EnergyBombPending = 1 and '
       'SoundEffectRequests bit 0 (other bits kept), leaves the key byte, and fills 48 times '
       '(24 x cyan $28, then $0F through the masks).')
def check_p4_energy_bomb_use(ctx):
    """HALT is treated as a completed frame wait (halt=True)."""
    m = ctx.machine()
    cases = 0
    outside = [a for a in range(ATTRIBUTES, ATTRIBUTES + ATTRIBUTES_SIZE) if a not in set(P4_VIEW_CELLS)]
    for cloak in (0, 1, 0xFF):
        for mission in (0, 1):
            for value in (0x07, 0x0F, 0x28, 0xFF):
                for entry in ('FillViewAttributes', 'L_9291'):
                    m.reset()
                    m.poke('CloakingDeviceActive', cloak)
                    m.poke('L_A843', mission)
                    m.clear(ATTRIBUTES, ATTRIBUTES_SIZE, 0x55)
                    m.call(entry, halt=True, l=value, b=0x99, a=0x77)
                    want = value if (cloak or entry == 'L_9291') else value & 0x07
                    if mission:
                        want &= 0x3A
                    expect({m.memory[a] for a in P4_VIEW_CELLS} == {want}, entry, cloak, mission, value)
                    expect(all(m.memory[a] == 0x55 for a in outside), 'outside the view', entry)
                    expect((m.reg('a'), m.reg('b'), m.reg('h'), m.reg('l')) == (0, 0, want, want), 'registers')
                    cases += 1
    for key, fitted, cloak, mission in ((0x20, 1, 0, 0), (0xFF, 7, 1, 0), (0x20, 1, 0, 1),
                                        (0xDF, 1, 0, 0), (0x20, 0, 0, 0)):
        m.reset()
        m.poke('KeyFlagsCombat', key)
        m.poke('EnergyBombFitted', fitted)
        m.poke('EnergyBombPending', 0)
        m.poke('SoundEffectRequests', 0x40)
        m.poke('CloakingDeviceActive', cloak)
        m.poke('L_A843', mission)
        m.clear(ATTRIBUTES, ATTRIBUTES_SIZE, 0x55)
        fills = []
        m.call('UseEnergyBomb', halt=True, hooks={'L_929B': lambda mm: fills.append(mm.reg('l'))})
        used = bool(key & 0x20) and fitted != 0
        expect(m.byte('KeyFlagsCombat') == key, 'key byte untouched')
        if not used:
            expect(m.byte('EnergyBombFitted') == fitted and m.byte('EnergyBombPending') == 0 and
                   m.byte('SoundEffectRequests') == 0x40 and not fills, 'no bomb use', key, fitted)
        else:
            final = 0x0F if cloak else 0x07
            if mission:
                final &= 0x3A
            expect(m.byte('EnergyBombFitted') == 0 and m.byte('EnergyBombPending') == 1 and
                   m.byte('SoundEffectRequests') == 0x41, 'bomb used', key, fitted)
            expect(fills == [0x28, final] * 24, 'flash sequence', fills[:4], len(fills))
            expect({m.memory[a] for a in P4_VIEW_CELLS} == {final}, 'final view colour')
        cases += 1
    return cases


@check('controls', 'p4-launch-reset', ['PrepareShipForLaunch', 'ColourInstrumentBlocks', 'FillAttributeBlock'],
       'pass2',
       'PrepareShipForLaunch clears MissileState, LaserTemperature, CabinTemperature and '
       'DockingComputerFlag, sets ForwardShield, AftShield, AltitudeGauge and EnergyBank1..4 to $A0 '
       'without touching their drawn copies, and ColourInstrumentBlocks writes exactly the 70 cells '
       'of columns 3..7 and 24..28, rows 17..23: $17, or $1F with EscapePodFitted, into VRAM for '
       'views 0..3 and into the $5B00 save buffer otherwise.')
def check_p4_launch_reset(ctx):
    m = ctx.machine()
    gauges = ('ForwardShield', 'AftShield', 'AltitudeGauge', 'EnergyBank1', 'EnergyBank2',
              'EnergyBank3', 'EnergyBank4')
    cleared = ('MissileState', 'LaserTemperature', 'CabinTemperature', 'DockingComputerFlag')
    block = {row * ROW_BYTES + column for row in range(17, 24) for column in list(range(3, 8)) + list(range(24, 29))}
    vram, saved = ATTRIBUTES + 0x200, ATTRIBUTES + ATTRIBUTES_SIZE      # rows 16..23 and their $5B00 copy
    cases = 0
    for screen in (0, 3, 4, 7):
        for pod in (0, 1):
            m.reset()
            m.poke('CurrentScreenId', screen)
            m.poke('EscapePodFitted', pod)
            for name in cleared:
                m.poke(name, 0x33)
            for name in gauges:
                m.poke(ctx[name] - 1, 0x11, 0x22)            # drawn copy, value
            m.clear(vram, 0x100, 0x44)
            m.clear(saved, 0x100, 0x44)
            m.call('PrepareShipForLaunch', limit=5_000_000)
            expect(all(m.byte(name) == 0 for name in cleared), 'cleared', screen)
            expect(all(m.byte(name) == 0xA0 and m.memory[ctx[name] - 1] == 0x11 for name in gauges), 'gauges')
            target, other = (vram, saved) if screen < 4 else (saved, vram)
            colour = 0x1F if pod else 0x17
            expect(all(m.memory[target + i] == (colour if 0x200 + i in block else 0x44)
                       for i in range(0x100)), 'instrument cells', screen, pod)
            expect(all(m.memory[other + i] == 0x44 for i in range(0x100)), 'other area untouched')
            cases += 1
    return cases


@check('dust', 'p4-torus-jump-effects', ['HandleTorusJumpKey', 'ResetShipSlots'], 'pass2',
       'A refused or absent J keeps everything except key bit 6 (other KeyFlagsViews bits kept); a '
       'jump clears MissionAspEncounterState, frees slots 1..7 (energy 0), clears the station hostile '
       'bit and SharedHostilityAlert, rotates AlternatingBits ($55 <-> $AA) and sets '
       'ObjectUpdateCounter = 1 only when the old value was $AA.')
def check_p4_torus_jump_effects(ctx):
    m = ctx.machine()
    size, base = ctx['InstanceSize'], ctx['InitialRuntimeState']
    energy, behaviour = 0x22, 0x21
    cases = 0
    for alternating in (0x55, 0xAA):
        for keys, blocked in ((0x40, False), (0x7F, False), (0xBF, False), (0xFF, True)):
            m.reset()
            for name, value in dict(SunNearFlag=1 if blocked else 0, PlanetNearFlag=0, L_DA0F=0,
                                    StationDormantFlag=0xFF).items():
                m.poke(name, value)
            m.poke('KeyFlagsViews', keys)
            m.poke('AlternatingBits', alternating)
            m.poke('ObjectUpdateCounter', 9)
            m.poke('MissionAspEncounterState', 2)
            m.poke('SharedHostilityAlert', 1)
            m.poke('TorusJumpDustFlag', 0)
            m.memory[base + behaviour] |= 0x04
            for slot in range(1, 8):
                m.memory[base + slot * size + energy] = 0x30 + slot
            m.call('HandleTorusJumpKey')
            jumped = bool(keys & 0x40) and not blocked
            expect(m.byte('KeyFlagsViews') == keys & 0xBF, 'key bit 6 consumed only', hex(keys))
            slots = [m.memory[base + slot * size + energy] for slot in range(1, 8)]
            if jumped:
                expect(slots == [0] * 7 and m.byte('MissionAspEncounterState') == 0 and
                       m.byte('SharedHostilityAlert') == 0 and not m.memory[base + behaviour] & 0x04 and
                       m.byte('TorusJumpDustFlag') == 1, 'jump effects', hex(keys))
                expect(m.byte('AlternatingBits') == alternating ^ 0xFF, 'rotated')
                expect(m.byte('ObjectUpdateCounter') == (1 if alternating == 0xAA else 9), 'encounter request')
            else:
                expect(slots == [0x31 + i for i in range(7)] and m.byte('MissionAspEncounterState') == 2 and
                       m.byte('AlternatingBits') == alternating and m.byte('ObjectUpdateCounter') == 9 and
                       m.byte('TorusJumpDustFlag') == 0, 'no jump', hex(keys), blocked)
            cases += 1
    return cases


@check('dust', 'p4-dust-roll-pitch-side-model',
       ['ApplyDustRoll', 'ScaleByRate', 'ApplyDustPitch', 'MoveDustSideways', 'StoreAndPlotDust',
        'NegateDustX', 'NegateDustY', 'UpdateDust'],
       'pass2',
       'Exact particle records for random inputs: roll x\' = x -/+ (|y|*r)>>7 (|X| grows on odd X/Y/roll '
       'sign parity), then y\' from the new |x| (|Y| grows on even parity), negation across zero, '
       'respawn at 120; pitch s = hi(2*($4000 - y*p)), Z*s/128, X*128/s, (y+p)*128/s with the zero-'
       'quotient sign flip and the 0/128/64/63 respawn limits; side view step (dz*256/Z)/2+1 with '
       'direction from bit 5 XOR the X sign and respawn at 119.  UpdateDust leaves IX, IY and the '
       'alternate registers unchanged.')
def check_p4_dust_roll_pitch_side_model(ctx):
    from skoolkit.simutils import xA, xB, xC, xD, xE, xF, xH, xL
    m = ctx.machine()
    record = ctx.scratch

    def scale(value, rate):
        return ((value * (rate & 15)) >> 7) & 0xFF

    def roll_model(x, sx, y, sy, r, sr):
        step = scale(y, r)
        if step:
            if sx ^ sy ^ sr:
                x += step
                if x >= 120:
                    return None
            else:
                x -= step
                if x < 0:
                    x, sx = -x, sx ^ 1
        step = scale(x, r)
        if step:
            if not sx ^ sy ^ sr:
                y += step
                if y >= 120:
                    return None
            else:
                y -= step
                if y < 0:
                    y, sy = -y, sy ^ 1
        return x | sx << 7, y | sy << 7

    def pitch_model(x, sx, y, sy, z, p, sp):
        product = y * (p & 15)
        s = (2 * (0x4000 - product if sy == sp else 0x4000 + product) >> 8) & 0xFF
        depth = 2 * z * s
        if depth > 0xFFFF or depth == 0:
            return None
        x = p4_divide_fraction(x >> 1, s)
        if x == 0 or x >= 128:
            return None
        if sy == sp:
            y += p
        else:
            y -= p
            if y < 0:
                y, sy = -y, sy ^ 1
        y = p4_divide_fraction(y >> 1, s)
        if y == 0:
            sy ^= 1
        if y >= 63:                     # >= 64 in ApplyDustPitch, >= 63 in StoreAndPlotDust
            return None
        return x | sx << 7, y | sy << 7, depth >> 8

    def side_model(x, sx, z, dz, reverse):
        if dz >= z:
            return None
        step = (p4_divide_fraction(dz, z) >> 1) + 1
        if reverse ^ sx:
            x += step
            if x >= 119:
                return None
        else:
            x -= step
            if x < 0:
                x, sx = -x, sx ^ 1
        return x | sx << 7

    def run(entry, x, sx, y, sy, z, roll, pitch, extra=0, step=0):
        m.reset()
        m.poke('CurrentScreenId', 0)
        m.poke('DustRollRate', roll & 0x7F, pitch & 0x7F)
        m.poke('DustX', x)
        m.poke('DustY', y)
        m.poke('DustZ', z)
        m.poke('DustXFraction', 0x11)
        m.poke('DustYFraction', 0x22)
        m.poke('DustStep', step)
        m.poke('DustFlags', sx << 7 | sy << 6 | (roll >> 7) << 4 | (pitch >> 7) << 3 | extra)
        m.poke('DustRemaining', 1)
        m.poke('DustPlotCount', 0)
        m.poke_word('DustPlotPointer', ctx['DustPlotList'])
        m.poke_word('DustRecordPointer', record)
        respawned = []
        m.call(entry, hooks={'RespawnDust': lambda mm: respawned.append(1)})
        return None if respawned else m.memory[record:record + 5]

    rng = random.Random(4)
    counts = Counter()
    for _ in range(3000):
        x, y, r = rng.randrange(120), rng.randrange(120), rng.randrange(1, 16)
        sx, sy, sr = rng.randrange(2), rng.randrange(2), rng.randrange(2)
        got = run('ApplyDustRoll', x, sx, y, sy, 0x80, r | sr << 7, 0)
        want = roll_model(x, sx, y, sy, r, sr)
        expect((got is None) == (want is None) and (want is None or (tuple(got[:2]), got[2]) == (want, 0x80)),
               'roll', x, sx, y, sy, r, sr, got, want)
        counts['roll-respawn' if want is None else 'roll'] += 1
    for _ in range(3000):
        x, y, z, p = rng.randrange(128), rng.randrange(64), rng.randrange(1, 256), rng.randrange(1, 16)
        sx, sy, sp = rng.randrange(2), rng.randrange(2), rng.randrange(2)
        got = run('ApplyDustPitch', x, sx, y, sy, z, 0, p | sp << 7)
        want = pitch_model(x, sx, y, sy, z, p, sp)
        expect((got is None) == (want is None) and (want is None or tuple(got[:3]) == want),
               'pitch', x, sx, y, sy, z, p, sp, got, want)
        counts['pitch-respawn' if want is None else 'pitch'] += 1
    for _ in range(3000):
        x, y, z, dz = rng.randrange(120), rng.randrange(63), rng.randrange(1, 256), rng.randrange(1, 18)
        sx, sy, reverse = rng.randrange(2), rng.randrange(2), rng.randrange(2)
        got = run('MoveDustSideways', x, sx, y, sy, z, 0, 0, reverse << 5, dz)
        want = side_model(x, sx, z, dz, reverse)
        expect((got is None) == (want is None) and
               (want is None or tuple(got[:3]) == (want, y | sy << 7, z)), 'side', x, sx, z, dz, reverse, got, want)
        counts['side-respawn' if want is None else 'side'] += 1
    preserved = (xA, xF, xB, xC, xD, xE, xH, xL)
    for screen in range(4):
        m.reset()
        m.poke('CurrentScreenId', screen)
        m.poke('PlayerRoll', 0x85, 0x03, 12)
        m.poke('WitchspaceFlag', 0)
        m.poke('TorusJumpDustFlag', 1)
        for index, register in enumerate(preserved):
            m.r[register] = 0x11 * (index + 1)
        m.call('UpdateDust', ix=0x1234, iy=0x5678)
        expect(m.ix() == 0x1234 and m.iy() == 0x5678 and
               [m.r[register] for register in preserved] == [0x11 * (i + 1) for i in range(len(preserved))],
               'registers preserved', screen)
        counts['update-dust-registers'] += 1
    return sum(counts.values()), dict(sorted(counts.items()))
# --- END P4 CHECKS ---

# --- BEGIN P10 CHECKS ---
# Instance field offsets (InstanceX..InstanceRoleFlags in tools/annotations/objects.py)
R10_FLAGS, R10_BEHAVIOUR, R10_ENERGY, R10_AI, R10_ROLE = 0x20, 0x21, 0x22, 0x25, 0x26
R10_BLUEPRINT, R10_SPEED = 0x23, 0x1B
R10_BP_SPEED, R10_BP_ENERGY, R10_BP_PAYLOAD, R10_BP_BEHAVIOUR = 6, 7, 0x0A, 0x12
R10_SHIP_IDS = 19                    # blueprint IDs 0..18 (docs/SHIPS.md)
R10_THARGOID, R10_ASP = 15, 13
R10_Z_FLAG = 0x40


def r10_blueprint(ctx, m, ship_id):
    """Blueprint header address of ship_id: 4-byte ID table entries, pointer in bytes 1..2."""
    return m.word(ctx['ShipBlueprintsAndDispatchTables'] + 4 * ship_id + 1)


def r10_hit_model(ai, flags, behaviour, energy, role, damage, bp, asp):
    """ApplyPlayerLaserHit model: (flags, behaviour, energy, ai, asp state, events)."""
    behaviour |= 0x04
    if role & 0x04 or flags & 0x20:
        return flags, behaviour, energy, ai, asp, []
    low = ai - 14 if ai >= 14 else 6 + (ai & 1)
    ai = (low & 0x7F) | (ai & 0x80)
    if energy == 0xFF or energy > damage:
        return flags, behaviour, energy if energy == 0xFF else energy - damage, ai, asp, []
    flags |= 0x10
    if role & 0x40 and asp in (1, 2):
        return flags, behaviour, 0xFF, ai, 3, [6]
    if bp[0] & 0x0F:
        events = [6]
    elif bp[R10_BP_ENERGY] >= 0x55:
        events = [5]
    elif bp[R10_BP_ENERGY] == 0x3C and damage == 0x32:
        events = [8]
    else:
        events = []
    return flags, behaviour, 0xFF, ai, asp, events


@check('combat', 'r10-laser-hit-outcomes', ['UpdatePlayerLaser', 'ApplyPlayerLaserHit'], 'pass2',
       'TargetedObjectCounter t selects slot 8-t (0: beams only).  A hit sets +$21 bit 2 and '
       'sound bit 3; the station flag (+$26 bit 2), +$20 bit 5 and energy $FF prevent damage; '
       '+$25 drops by 14 (6 or 7 on borrow, bits 0 and 7 kept); a kill sets energy $FF and +$20 '
       'bit 4, the marked Asp (state 1/2) gives state 3 and event 6, otherwise the blueprint '
       'debris event: 6 canister, 5 alloys (energy >= 85), 8 splinters (Asteroid, damage 50).')
def check_r10_laser_hit_outcomes(ctx):
    m = ctx.machine()
    size, slots, slot = ctx['InstanceSize'], ctx['InitialRuntimeState'], ctx['ObjectSlot1']
    record = []
    stubs = {'ApplyPlayerLaserHit': lambda mm: record.append(('hit', mm.ix())),
             'DrawLaser': lambda mm: record.append(('beam', None))}
    for t in range(9):
        m.reset()
        record.clear()
        m.poke('TargetedObjectCounter', t)
        m.call('L_EC39', a=0x20, stubs=stubs)
        expect(record == [('beam', None) if t == 0 else ('hit', slots + (8 - t) * size)], t, record)
    blueprints = [r10_blueprint(ctx, m, i) for i in range(R10_SHIP_IDS)]
    headers = [list(ctx.pristine[b:b + 0x13]) for b in blueprints]
    events = []
    stubs = {'DispatchShipEvent': lambda mm: events.append((mm.reg('a'), mm.reg('c'), mm.ix())),
             'DrawLaser': None}

    def run(ai, flags, behaviour, energy, role, damage, ship, asp):
        m.reset()
        events.clear()
        m.poke(slot + R10_FLAGS, flags, behaviour, energy)
        m.poke_word(slot + R10_BLUEPRINT, blueprints[ship])
        m.poke(slot + R10_AI, ai, role)
        m.poke('SoundEffectRequests', 0)
        m.poke('MissionAspEncounterState', asp)
        m.call('ApplyPlayerLaserHit', ix=slot, c=damage, stubs=stubs)
        expect(m.byte('SoundEffectRequests') == 0x08 and m.byte(slot + R10_ROLE) == role,
               'sound bit 3 / role flags', ai, flags, energy, role)
        expect(all(ix == slot for _, _, ix in events), 'event parent IX', events)
        got = (m.byte(slot + R10_FLAGS), m.byte(slot + R10_BEHAVIOUR), m.byte(slot + R10_ENERGY),
               m.byte(slot + R10_AI), m.byte('MissionAspEncounterState'), [a for a, _, _ in events])
        want = r10_hit_model(ai, flags, behaviour, energy, role, damage, headers[ship], asp)
        expect(got == want, ai, flags, behaviour, energy, role, damage, ship, asp, got, want)

    cases = 9
    for ai in range(256):                                    # AI threshold arithmetic
        for damage in (15, 23, 50):
            run(ai, 0x40, 0x00, 200, 0x00, damage, R10_ASP, 0)
            cases += 1
    for role, flags, energy in ((0x0C, 0x40, 10), (0x00, 0x60, 10), (0x00, 0x40, 0xFF)):
        for ai in (0x00, 0x7E, 0x85):                        # immune / already destroyed
            run(ai, flags, 0x02, energy, role, 50, R10_ASP, 1)
            cases += 1
    debris = {}
    for ship in range(R10_SHIP_IDS):                         # kills: exact zero and borrow
        for damage in (15, 23, 50):
            for energy in (damage, damage - 1, 1):
                run(0x7E, 0x41, 0x00, energy, 0x00, damage, ship, 0)
                cases += 1
            debris[(ship, damage)] = r10_hit_model(0x7E, 0x41, 0, damage, 0, damage, headers[ship], 0)[5]
    for asp in range(4):                                     # marked Asp in each state
        for role in (0x00, 0x40):
            run(0x7E, 0x40, 0x04, 15, role, 15, R10_ASP, asp)
            cases += 1
    rng = random.Random(1010)
    for _ in range(2000):
        run(rng.randrange(256), rng.choice((0x00, 0x40, 0x60, 0xC7)), rng.randrange(256),
            rng.choice((rng.randrange(1, 60), rng.randrange(256), 0xFF)),
            rng.choice((0x00, 0x04, 0x40, 0x0A, 0x0C)), rng.choice((15, 23, 50)),
            rng.randrange(R10_SHIP_IDS), rng.randrange(4))
        cases += 1
    canister = {s for s in range(R10_SHIP_IDS) if debris[(s, 50)] == [6]}
    alloys = {s for s in range(R10_SHIP_IDS) if debris[(s, 50)] == [5]}
    splinters = {s for s in range(R10_SHIP_IDS) if debris[(s, 50)] == [8]}
    expect(canister == {7, 9, 10, 11, 12, 17} and alloys == {0, 8, 13, 14, 15} and splinters == {6}
           and debris[(6, 23)] == [], 'debris by blueprint', canister, alloys, splinters)
    return cases, dict(canister=sorted(canister), alloys=sorted(alloys), splinters=sorted(splinters))


@check('combat', 'r10-sights-and-ecm', ['UpdateSightsLaserAndEcm', 'ClearPitchAndSpeed'], 'pass2',
       'PlayerDeadFlag clears pitch and speed and skips sights, laser and ECM; screens 4+ change '
       'nothing; the ECM countdown skips everything for jammer + L_A871 = 4, consumes key bit 4, '
       'starts through ActivatePlayerEcm when idle, clears EcmFitted bit 7 at expiry and while '
       'running sets sound bit 5 and drains one L_DA17 unit when an ECM is owned.')
def check_r10_sights_and_ecm(ctx):
    m = ctx.machine()
    harness = range(ctx.test_stack - 64, ctx.test_stack)
    cases = 0
    for dead, screen in ((1, 0), (1, 3), (0, 4), (0, 7)):
        m.reset()
        m.poke('PlayerDeadFlag', dead)
        m.poke('CurrentScreenId', screen)
        m.poke('PlayerPitch', 5)
        m.poke('PlayerSpeed', 9)
        m.poke('EcmTimer', 5)
        m.poke('LaserMounts', 1, 1, 1, 1)
        before = list(m.memory)
        m.call('UpdateSightsLaserAndEcm')
        changed = {a for a in range(RAM_TOP) if m.memory[a] != before[a] and a not in harness}
        want = {ctx['PlayerPitch'], ctx['PlayerSpeed']} if dead else set()
        expect(changed == want and m.byte('PlayerPitch') == (0 if dead else 5),
               'dead/non-flight', dead, screen, sorted(changed))
        cases += 1
    started = []
    stubs = {'ActivatePlayerEcm': lambda mm: started.append((mm.reg('b'), mm.reg('c')))}
    for jammer in (0x00, 0x80):
        for mission in (0, 3, 4, 5):
            for timer in (0, 1, 2, 10):
                for ecm in (0x00, 0x01, 0x81):
                    for keys in (0x00, 0x10, 0xFF):
                        m.reset()
                        started.clear()
                        m.poke('CommanderFlags', jammer | 0x05)
                        m.poke('L_A871', mission)
                        m.poke('EcmTimer', timer)
                        m.poke('EcmFitted', ecm)
                        m.poke('KeyFlagsCombat', keys)
                        m.poke('SoundEffectRequests', 0)
                        m.poke('L_DA17', 3)
                        m.call('L_ED83', stubs=stubs)
                        got = (m.byte('KeyFlagsCombat'), m.byte('EcmTimer'), m.byte('EcmFitted'),
                               m.byte('SoundEffectRequests'), m.byte('L_DA17'), list(started))
                        if jammer and mission == 4:
                            want = (keys, timer, ecm, 0, 3, [])
                        elif timer == 0:
                            want = (keys & 0xEF, 0, ecm, 0, 3, [(keys, ecm)])
                        else:
                            c = ecm & 0x7F if timer == 1 else ecm
                            want = (keys & 0xEF, timer - 1, c if c else ecm, 0x20,
                                    4 if c else 3, [])
                        expect(got == want, jammer, mission, timer, ecm, keys, got, want)
                        cases += 1
    for ecm, keys, result in ((0x01, 0x10, (0x81, 10)), (0x01, 0x00, (0x01, 0)),
                              (0x00, 0x10, (0x00, 0))):
        m.reset()
        m.poke('CommanderFlags', 0)
        m.poke('EcmTimer', 0)
        m.poke('EcmFitted', ecm)
        m.poke('KeyFlagsCombat', keys)
        m.call('L_ED83')
        expect((m.byte('EcmFitted'), m.byte('EcmTimer')) == result, 'activation', ecm, keys)
        cases += 1
    return cases


@check('objects', 'r10-ship-creation', ['InitialiseShipFromBlueprint', 'CreateShipAtParent',
       'FindFreeShipSlot', 'L_F3AD', 'L_F3B3', 'SpawnThargoidGroup', 'SetUpDisplayShip'], 'pass2',
       'The loader sets the documented fields for all 19 IDs (template, energy, +$20/+$21, half '
       'speed, +$25 = $7E, +$26 = 0, random x/y low bytes and signs, high bytes 0..7 unless '
       'hostile, z kept; 3 or 5 RNG calls; A = 0, Z).  FindFreeShipSlot/CreateShipAtParent '
       'outputs including failure; L_F3AD/L_F3B3 give the identity orientation at x = z = 0; '
       'Thargoid groups have 3-4 members and the documented fields; the slot-7 orientation bytes '
       'form a rotation and land in the axis high bytes.')
def check_r10_ship_creation(ctx):
    m = ctx.machine()
    size, slots = ctx['InstanceSize'], ctx['InitialRuntimeState']
    slot1, slot6, slot7 = ctx['ObjectSlot1'], ctx['ObjectSlot6'], ctx['ObjectSlot7']
    template = list(ctx.pristine[ctx['ShipInstanceTemplate']:ctx['ObjectSlot7OrientationBytes']])
    expect(len(template) == 31, 'template size')
    blueprints = [r10_blueprint(ctx, m, i) for i in range(R10_SHIP_IDS)]
    calls = []
    hooks = {'NextRandomByte': lambda mm: calls.append(1)}
    cases = 0
    for ship in range(R10_SHIP_IDS):
        bp = list(ctx.pristine[blueprints[ship]:blueprints[ship] + 0x13])
        for seed in (0x0001, 0xF562, 0x8000, 0x3C5A):
            m.reset()
            calls.clear()
            m.poke_word('RandomSeed', seed)
            m.call('InitialiseShipFromBlueprint', a=ship, ix=slot1, hooks=hooks)
            got = m.memory[slot1:slot1 + size]
            hostile = bp[R10_BP_BEHAVIOUR] & 0x04
            expect(m.reg('a') == 0 and m.reg('f') & R10_Z_FLAG and m.ix() == slot1
                   and m.iy() == blueprints[ship], 'registers', ship)
            expect(got[R10_BLUEPRINT] | got[R10_BLUEPRINT + 1] << 8 == blueprints[ship]
                   and got[6:0x1B] == template[6:0x1B] and got[0x1C:0x1F] == template[0x1C:0x1F]
                   and got[R10_ENERGY] == bp[R10_BP_ENERGY]
                   and got[R10_BEHAVIOUR] == bp[R10_BP_BEHAVIOUR] & 0x6F
                   and got[R10_FLAGS] == (bp[R10_BP_PAYLOAD] & 7) | (bp[R10_BP_BEHAVIOUR] & 0x80) | 0x40
                   and got[R10_SPEED] == bp[R10_BP_SPEED] >> 1
                   and got[R10_AI] == 0x7E and got[R10_ROLE] == 0, 'fields', ship, seed)
            highs = (got[1], got[4])
            expect(got[2] in (0, 0x80) and got[5] in (0, 0x80)
                   and (highs == (0x32, 0x32) if hostile else max(highs) <= 7)
                   and len(calls) == (3 if hostile else 5), 'position', ship, seed, got[:9], len(calls))
            cases += 1
    # FindFreeShipSlot: first free slot k, or none
    for k in range(1, 8):
        m.reset()
        for s in range(1, 7):
            m.poke(slots + s * size + R10_ENERGY, 0 if s >= k else 0x55 + s)
        m.call('FindFreeShipSlot', c=0x5A, hl=0x1234, iy=0x4321)
        if k <= 6:
            expect(m.reg('f') & R10_Z_FLAG and m.ix() == slots + k * size and m.reg('a') == 0
                   and m.reg('b') == 7 - k, 'free slot', k)
        else:
            expect(not m.reg('f') & R10_Z_FLAG and m.ix() == slot6 and m.reg('b') == 1
                   and m.reg('a') == 0x55 + 6, 'no free slot')
        expect(m.pair('de') == size and m.reg('c') == 0x5A and m.pair('hl') == 0x1234
               and m.iy() == 0x4321, 'preserved', k)
        cases += 1
    # CreateShipAtParent from a parent in slot 0
    rng = random.Random(1011)
    for child in (2, 3, 4, 5, 9):
        bp = list(ctx.pristine[blueprints[child]:blueprints[child] + 0x13])
        m.reset()
        parent = [rng.randrange(256) for _ in range(0x1B)]
        m.poke(slots, *parent)
        m.call('CreateShipAtParent', a=child, ix=slots)
        got = m.memory[slot1:slot1 + size]
        expect(m.reg('f') & R10_Z_FLAG and m.ix() == slot1 and m.pair('bc') == 0 and m.reg('a') == 0
               and got[:0x1B] == parent and got[R10_SPEED] == bp[R10_BP_SPEED] >> 1
               and got[R10_ENERGY] == bp[R10_BP_ENERGY], 'child', child)
        for s in range(1, 7):
            m.poke(slots + s * size + R10_ENERGY, 1)
        before = list(m.memory)
        m.call('CreateShipAtParent', a=child, ix=slots)
        expect(not m.reg('f') & R10_Z_FLAG and m.ix() == slot6 and m.pair('hl') == slots
               and m.memory[slots:slot7] == before[slots:slot7], 'no slot', child)
        cases += 2
    # L_F3AD / L_F3B3: identity orientation at x = z = 0
    identity = [0, 0, 0, 0, 0xFF, 0x7F, 0, 0, 0xFF, 0x7F, 0, 0, 0xFF, 0x7F, 0, 0, 0, 0]
    for ship in range(R10_SHIP_IDS):
        m.reset()
        m.poke(slot1 + R10_ENERGY, 1)
        m.call('L_F3AD', a=ship)
        got = m.memory[slots + 2 * size:slots + 3 * size]
        expect(m.reg('f') & R10_Z_FLAG and m.ix() == slots + 2 * size, 'slot', ship)
        expect(got[0] == got[1] == got[4] == got[6] == got[7] == got[8] == 0
               and got[2] in (0, 0x80) and got[5] in (0, 0x80) and got[9:0x1B] == identity,
               'position/orientation', ship, got[:0x1B])
        cases += 1
    m.reset()
    for s in range(1, 7):
        m.poke(slots + s * size + R10_ENERGY, 1)
    m.call('L_F3AD', a=3)
    expect(not m.reg('f') & R10_Z_FLAG, 'L_F3AD without a free slot')
    # SpawnThargoidGroup (event 1)
    first = ctx.find('SpawnThargoidGroup', 'L_F3D6', [0xE6, 0x01, 0xC6, 0x03])
    rolled = []
    seen = set()
    for seed in range(0x1000, 0x1000 + 16 * 97, 97):
        for free in (6, 2):
            m.reset()
            rolled.clear()
            m.poke_word('RandomSeed', seed)
            for s in range(1, 7):
                m.poke(slots + s * size + R10_ENERGY, 0 if s <= free else 1)
            m.call('DispatchShipEvent', a=1, hooks={first: lambda mm: rolled.append(mm.reg('a'))})
            count = 3 + (rolled[0] & 1)
            made = [slots + s * size for s in range(1, 7)
                    if m.word(slots + s * size + R10_BLUEPRINT) == blueprints[R10_THARGOID]
                    and m.byte(slots + s * size + R10_ENERGY)]
            expect(len(made) == min(count, free), 'group size', seed, free, count, len(made))
            if free >= count:
                expect(m.reg('f') & R10_Z_FLAG, 'Z when complete', seed)
                seen.add(count)
            else:
                expect(not m.reg('f') & R10_Z_FLAG and m.reg('c') == count - free, 'NZ, C', seed)
            for a in made:
                z = m.byte(a + 7)
                expect(m.byte(a + R10_AI) & 1 and z & 0x04 and z <= 15 and m.byte(a + 1) == (z >> 3) & 1
                       and m.byte(a + 4) == 0 and not m.byte(a + 0x0A) & 0x78
                       and not m.byte(a + 0x0C) & 0x78, 'Thargoid fields', seed, a)
            cases += 1
    expect(seen == {3, 4}, 'both group sizes', seen)
    # slot-7 display orientation: a rotation, copied into the axis high bytes
    rows = [list(ctx.pristine[ctx['ObjectSlot7OrientationBytes'] + 3 * r:
                              ctx['ObjectSlot7OrientationBytes'] + 3 * r + 3]) for r in range(3)]
    z, y, x = ([(-(b & 0x7F) if b & 0x80 else b) / 0x7F for b in row] for row in rows)

    def dot(u, v):
        return sum(p * q for p, q in zip(u, v))

    cross = [y[1] * z[2] - y[2] * z[1], y[2] * z[0] - y[0] * z[2], y[0] * z[1] - y[1] * z[0]]
    expect(all(abs(math.sqrt(dot(v, v)) - 1) < 0.02 for v in (x, y, z))
           and max(abs(dot(z, y)), abs(dot(z, x)), abs(dot(y, x))) < 0.012
           and max(abs(p - q) for p, q in zip(cross, x)) < 0.03, 'rotation', x, y, z)
    m.reset()
    m.call('DispatchShipEvent', a=0x79)
    expect(m.word(slot7 + R10_BLUEPRINT) == blueprints[9]
           and [m.byte(slot7 + 0x0A + 2 * i) for i in range(9)] == sum(rows, []), 'slot 7 copy')
    return cases + 3
# --- END P10 CHECKS ---

# --- BEGIN P11 CHECKS ---
# Pass-2 checks of the ship AI and encounter selection in $F400..$FFA8
# (tools/annotations/r11_f400.py).  NextRandomByte is replaced by a scripted stub where a
# check needs exact random values; ApplySteeringVector is stubbed where only the raw
# steering vector is observed.  Both stubs emulate a RET and change no memory byte.

P11_PITCH, P11_ACCELERATION = 0x1E, 0x1C     # instance pitch and acceleration commands
P11_BLUEPRINT_ENERGY = 0x07                  # blueprint header: energy (docs/SHIPS.md)


def p11_random_script(values, rest=0):
    """NextRandomByte stub: return the scripted values in order, then `rest`."""
    queue = list(values)

    def next_random(mm):
        mm.r[A] = queue.pop(0) if queue else rest
    return next_random


def p11_low16_quarter(value):
    """Coordinate -> steering word: low 16 magnitude bits / 4, sign to bit 15 (L_F9E2)."""
    magnitude = abs(value) & 0xFFFF
    return (magnitude >> 2) | (0x8000 if value < 0 else 0)


def p11_steer_model(h, l, d, length, flags25, flags26, roll, pitch):
    """Roll, pitch and acceleration commands and whether TryFireAiLaser is reached."""
    magnitude = d & 0x7F
    skip_pitch = False
    if magnitude:
        rate = min(0x0F, (magnitude + (magnitude >> 3) + ((magnitude >> 2) & 1)) >> 2)
        roll = (((d ^ l) & 0x80) >> 1) | rate
        skip_pitch = rate >= 4
    if not skip_pitch:
        if h & 0x80:
            t = ((h & 0x7F) + 0x50) >> 1
            rate = (((t ^ 0xFF) + 0x68) & 0xFF) >> 1
            rate = min(rate, 0x3F)
        else:
            rate = 0x3F
        pitch = ((l & 0x80) >> 1) | (rate >> 2)
    if flags25 & 0x80:
        return roll, pitch, 2, False
    distance = length >> 8
    missile = flags26 & 1
    if h & 0x80:
        if distance < (2 if missile else 0x0A):
            return roll, pitch, 0, True
        return roll, pitch, 1 if distance >= 0x10 else 2, True
    if distance < (3 if missile else 0x0B):
        return roll, pitch, 0, False
    return roll, pitch, 0xFF if distance < 0x12 else 0xFE, False


@check('ai', 'p11-apply-steering-vector', ['ApplySteeringVector', 'SteeringVectorLength', 'TryFireAiLaser'],
       'pass2',
       'ApplySteeringVector stores the NormaliseVector length of the steering vector in '
       'SteeringVectorLength; H/L/D = ComputeNegatedDotProduct with the forward, up and side axes; '
       'roll = (D xor L sign in bit 6) | min(15, (m + m/8 + bit 2 of m)/4) with m = |D| (kept when '
       'm = 0); pitch skipped for roll rate >= 4, else sign of L in bit 6 and rate 15 (target '
       'behind) or (103 - (|H|+80)/2)/8; acceleration 2 and return while fleeing; otherwise '
       'ahead: 0 below range $0A ($02 missile), else 1 (range >= $10) or 2, always continuing into '
       'TryFireAiLaser; behind: 0 below $0B ($03), else -1 (below $12) or -2.')
def check_p11_apply_steering_vector(ctx):
    m = ctx.machine()
    rng = random.Random(1101)
    instance, vector, scratch = ctx['ObjectSlot1'], ctx['SteeringVectorX'], ctx.scratch
    axes = (ctx['InstanceAxisZ'], ctx['InstanceAxisY'], ctx['InstanceAxisX'])
    kinds = Counter()

    def dot(axis):
        m.call('ComputeNegatedDotProduct', ix=axis, iy=vector)
        return m.reg('a')

    for case in range(700):
        m.reset()
        scale = rng.choice((0x240, 0x500, 0x900, 0x1400, 0x3FFF))
        words = [rng.randrange(scale) | (0x8000 if rng.random() < 0.5 else 0) for _ in range(3)]
        j = rng.randrange(3)
        words[j] = max(0x200, words[j] & 0x7FFF) | (words[j] & 0x8000)
        for i, word in enumerate(words):
            m.poke_word(vector + 2 * i, word)
            m.poke_word(scratch + 2 * i, word)
        for axis in axes:
            for i in range(3):
                m.poke(instance + axis + 2 * i, rng.randrange(256), rng.randrange(256))
        if case % 5 == 0:
            for i in range(3):
                m.poke(instance + ctx['InstanceAxisX'] + 1 + 2 * i, rng.choice((0, 0x80)))
        flags25, flags26 = rng.randrange(256), rng.randrange(2)
        roll, pitch = rng.randrange(256), rng.randrange(256)
        m.poke(instance + INSTANCE_FLAGS25, flags25)
        m.poke(instance + ctx['InstanceRoleFlags'], flags26)
        m.poke(instance + ctx['InstanceBehaviour'], 0)          # calm: TryFireAiLaser returns at once
        m.poke(instance + INSTANCE_ROLL, roll)
        m.poke(instance + P11_PITCH, pitch)
        visited = m.call('ApplySteeringVector', record=True, ix=instance, iy=0x1234)
        expect(m.ix() == instance and m.iy() == 0x1234, 'IX/IY preserved')
        normalised = [m.word(vector + 2 * i) for i in range(3)]
        length = m.word('SteeringVectorLength')
        m.call('NormaliseVector', ix=scratch)
        expect(m.pair('de') == length and [m.word(scratch + 2 * i) for i in range(3)] == normalised,
               'length word', words, length)
        h, l, d = [dot(instance + axis) for axis in axes]
        want = p11_steer_model(h, l, d, length, flags25, flags26, roll, pitch)
        got = (m.byte(instance + INSTANCE_ROLL), m.byte(instance + P11_PITCH),
               m.byte(instance + P11_ACCELERATION), ctx['TryFireAiLaser'] in visited)
        expect(got == want, words, hex(h), hex(l), hex(d), hex(length), flags25, flags26, got, want)
        kinds['flee' if flags25 & 0x80 else ('ahead' if h & 0x80 else 'behind')] += 1
        kinds['roll kept' if not d & 0x7F else 'roll set'] += 1
        kinds[f'acceleration {want[2]}'] += 1
    expect(min(kinds.values()) >= 10, dict(kinds))
    return sum(kinds[k] for k in ('flee', 'ahead', 'behind')), dict(sorted(kinds.items()))


@check('ai', 'p11-missile-guidance', ['UpdateMissileGuidance', 'SteerShipAwayFromPlayer', 'SteerShipTowardsPlayer',
                                      'L_F9B2', 'L_F9DB', 'L_F9E2', 'L_F9AA'],
       'pass2',
       'Steering vectors are quarter-scale: away = +pos/4, towards = -pos/4 (low 16 magnitude bits, '
       'sign in bit 15) with +$26 bit 5 set/cleared; a missile with target code k aims at slot 8-k with '
       '(target-missile)/4; it hits when every component magnitude is below $20: +$20 bit 4 on the '
       'missile and the target, a station only in L_A871 mode 4 (then L_A871 bit 3, L_A870 = 0, '
       'combat score + $FFFF, station +$26 bit 7); active ECM destroys the missile; code 0 steers '
       'towards the player.')
def check_p11_missile_guidance(ctx):
    m = ctx.machine()
    rng = random.Random(1102)
    vector, size = ctx['SteeringVectorX'], ctx['InstanceSize']
    state = ctx['InitialRuntimeState']
    stub = {'ApplySteeringVector': None}
    cases = 0

    def steering():
        return [m.word(vector + 2 * i) for i in range(3)]

    def place(address, position):
        for i, value in enumerate(position):
            put24(m.memory, address + 3 * i, value)

    for _ in range(200):
        m.reset()
        ship = ctx['ObjectSlot2']
        position = [rng.randint(-0x2FFFF, 0x2FFFF) for _ in range(3)]
        place(ship, position)
        for entry, sign, bit in (('SteerShipAwayFromPlayer', 1, 0x20), ('SteerShipTowardsPlayer', -1, 0)):
            m.poke(ship + ctx['InstanceRoleFlags'], 0x20 ^ bit)
            m.call(entry, stubs=stub, ix=ship)
            expect(steering() == [p11_low16_quarter(sign * v) for v in position], entry, position)
            expect(m.byte(ship + ctx['InstanceRoleFlags']) == bit and m.ix() == ship, entry, 'flags/IX')
            cases += 1
    missile = ctx['ObjectSlot7']
    for code in range(2, 9):
        target = state + (8 - code) * size
        for near in (False, True):
            m.reset()
            m.poke('EcmTimer', 0)
            place(missile, [rng.randint(-0x7FFF, 0x7FFF) for _ in range(3)])
            spot = [get24(m.memory, missile + 3 * i) for i in range(3)]
            offset = [rng.randint(-0x78, 0x78) if near else rng.choice((-1, 1)) * rng.randint(0x90, 0x7FFF)
                      for _ in range(3)]
            place(target, [s + o for s, o in zip(spot, offset)])
            m.poke(missile + INSTANCE_FLAGS25, code)
            m.poke(missile + INSTANCE_STATE, 0x40)
            m.poke(target + INSTANCE_STATE, 0x40)
            m.poke(target + ctx['InstanceRoleFlags'], 0)
            m.call('UpdateMissileGuidance', stubs=stub, ix=missile, iy=0x1234)
            expect(m.iy() == 0x1234, 'IY preserved')
            words = steering()
            for i in range(3):
                t, s = get24(m.memory, target + 3 * i), get24(m.memory, missile + 3 * i)
                expect(abs(sm16(words[i]) - (t - s) / 4) <= 1.5, code, i, t, s, hex(words[i]))
            hit = all(abs(sm16(w)) < 0x20 for w in words)
            expect(hit == near, code, words)
            expect((m.byte(missile + INSTANCE_STATE) & 0x10 != 0) == hit
                   and (m.byte(target + INSTANCE_STATE) & 0x10 != 0) == hit, code, near)
            cases += 1
    # A station target: immune, except in L_A871 mode 4.
    stock16 = ctx['L_A871'] - 1                  # the byte that DEC L reaches (L_A870)
    for mode in (0, 3, 4):
        m.reset()
        m.poke('EcmTimer', 0)
        place(missile, [0x100, 0x200, 0x300])
        place(state, [0x110, 0x1F0, 0x310])
        m.poke(missile + INSTANCE_FLAGS25, 8)
        m.poke(missile + INSTANCE_STATE, 0x40)
        m.poke(state + INSTANCE_STATE, 0x40)
        m.poke(state + ctx['InstanceRoleFlags'], 0x04)
        m.poke('L_A871', mode)
        m.poke(stock16, 0x33)
        m.poke('CombatScoreFraction', 0x10, 0x20, 0x05)
        m.call('UpdateMissileGuidance', stubs=stub, ix=missile, iy=0x1234)
        expect(m.byte(missile + INSTANCE_STATE) & 0x10, 'missile spent', mode)
        destroyed = mode == 4
        expect(bool(m.byte(state + INSTANCE_STATE) & 0x10) == destroyed
               and bool(m.byte(state + ctx['InstanceRoleFlags']) & 0x80) == destroyed, 'station', mode)
        expect(m.byte('L_A871') == (0x0C if destroyed else mode)
               and m.byte(stock16) == (0 if destroyed else 0x33), 'mode bytes', mode)
        score = [m.byte(ctx['CombatScoreFraction'] + i) for i in range(3)]
        expect(score == ([0x0F, 0x20, 0x06] if destroyed else [0x10, 0x20, 0x05]), 'score', mode, score)
        cases += 1
    # ECM active: the missile is destroyed and no longer counted; code 0 steers towards the player.
    m.reset()
    m.poke('EcmTimer', 5)
    m.poke(missile + INSTANCE_STATE, 0x40)
    m.call('UpdateMissileGuidance', stubs=stub, ix=missile)
    expect(m.byte(missile + INSTANCE_STATE) == 0x10, 'ECM')
    m.reset()
    m.poke('EcmTimer', 0)
    place(missile, [0x1234, -0x4321, 0x777])
    m.poke(missile + INSTANCE_FLAGS25, 0)
    m.call('UpdateMissileGuidance', stubs=stub, ix=missile)
    expect(steering() == [p11_low16_quarter(-v) for v in (0x1234, -0x4321, 0x777)], 'code 0')
    return cases + 2


@check('ai', 'p11-encounter-selection', ['SpawnRandomEncounter', 'L_F660', 'L_F684', 'L_F6E2', 'L_F706',
                                         'L_F70E', 'SelectEncounterTraderType'],
       'pass2',
       'With scripted random bytes r1, r2: r = r1 - C (2*(slaves+narcotics)+firearms); no borrow and '
       'r >= $5A: nothing; $50..$59: Asteroid; otherwise E = r AND 7, government g > E: nothing '
       '(anarchy never), E+1 for g <> 0; r bit 3: mixed single ship; else (r2 AND 7) >= E: a group '
       'of 2 + ((r3 AND 3) >> 1) + (r3 AND 1) Sidewinders/Kraits; else r2 bits 7..5 = 0..1: Rock hermit/Viper by r2 bit 4, 2..4 '
       'Cobra trader, 5..7 Python trader.  L_A871 = 4 / 1 force a Thargoid / Python trader.')
def check_p11_encounter_selection(ctx):
    m = ctx.machine()
    state, size = ctx['InitialRuntimeState'], ctx['InstanceSize']
    headers = blueprint_headers(ctx)
    mixed = [THARGOID] + [14] * 11 + [13] * 18 + [12] * 16 + [11] * 18

    def expected(r1, r2, cargo, government, mode):
        r = (r1 - cargo) & 0xFF
        if r1 >= cargo:
            if r >= 0x5A:
                return []
            if r >= 0x50:
                return [6]
        if mode == 4:
            return [THARGOID]
        if mode == 1:
            return [10]
        e = r & 7
        if government:
            e += 1
            if government >= e:
                return []
        if r & 8:
            return [mixed[r2 & 0x3F]]
        if (r2 & 7) >= e:
            return [SIDEWINDER, SIDEWINDER]
        high = r2 >> 5
        if high < 2:
            return [7 + ((r2 >> 4) & 1)]
        return [9 + ((high - 1) >> 2)]

    outcomes = Counter()
    cases = 0
    for government in (0, 2, 7):
        for slaves, narcotics, firearms in ((0, 0, 0), (5, 4, 11)):
            cargo = 2 * (slaves + narcotics) + firearms
            for mode in (0, 1, 4):
                for r1 in range(0, 256, 1 if mode == 0 else 37):
                    for r2 in ((0x00, 0x13, 0x2A, 0x45, 0x5D, 0x9F, 0xF4) if mode == 0 else (0x00,)):
                        m.reset()
                        m.poke(ctx['CargoHold'] + 3, slaves)
                        m.poke(ctx['CargoHold'] + 6, narcotics)
                        m.poke(ctx['CargoHold'] + 10, firearms)
                        m.poke('MissionAspEncounterState', 3)
                        m.poke('CurrentGovernment', government)
                        m.poke('L_A871', mode)
                        m.call('SpawnRandomEncounter', stubs={'NextRandomByte': p11_random_script((r1, r2))})
                        created = [m.word(state + slot * size + INSTANCE_BLUEPRINT) for slot in range(1, 7)
                                   if m.byte(state + slot * size + ctx['InstanceEnergy'])]
                        want = expected(r1, r2, cargo, government, mode)
                        expect(created == [headers[n] for n in want], r1, r2, cargo, government, mode,
                               [hex(a) for a in created], want)
                        outcomes[','.join(map(str, want)) or 'none'] += 1
                        cases += 1
    expect(len(outcomes) >= 10, dict(outcomes))
    for r in range(256):                      # group size and type bit (L_F70E)
        kind = r >> 7
        m.reset()
        m.call('L_F70E', stubs={'NextRandomByte': p11_random_script((r,), rest=kind)})
        created = [m.word(state + slot * size + INSTANCE_BLUEPRINT) for slot in range(1, 7)
                   if m.byte(state + slot * size + ctx['InstanceEnergy'])]
        count = 2 + ((r & 3) >> 1) + (r & 1)
        expect(created == [headers[SIDEWINDER + kind]] * count, r, [hex(a) for a in created])
        cases += 1
    return cases, dict(sorted(outcomes.items()))


@check('ai', 'p11-ship-tactics-energy', ['UpdateShipTactics'], 'pass2',
       'Energy becomes min(blueprint energy, energy + 1, or + 4 when the blueprint energy >= $F0); '
       'nothing is stored while CloakingDeviceActive is nonzero; with MissionAspEncounterState 1 the '
       'ship pays 2 energy (state -> 2 below $34 without paying); state 2 returns to 1 at energy >= $50.')
def check_p11_ship_tactics_energy(ctx):
    m = ctx.machine()
    ship = ctx['ObjectSlot3']
    blueprint = ctx.scratch
    stop = ctx.find('L_F76A', 'TryLaunchAiPayload', [0xFD, 0x46, P11_BLUEPRINT_ENERGY])
    cases = 0
    for cloak in (0, 1):
        for mission in (0, 1, 2, 3):
            for maximum in (0x14, 0x50, 0x96, 0xF0, 0xFA):
                for energy in range(0, maximum + 1, 3):
                    m.reset()
                    m.poke(blueprint + P11_BLUEPRINT_ENERGY, maximum)
                    m.poke(ship + ctx['InstanceEnergy'], energy)
                    m.poke('CloakingDeviceActive', cloak)
                    m.poke('MissionAspEncounterState', mission)
                    m.call('UpdateShipTactics', stop=None if cloak else stop, ix=ship, iy=blueprint)
                    value = min(maximum, energy + (4 if maximum >= 0xF0 else 1))
                    new_state = mission
                    if cloak:
                        value = energy
                    elif mission == 2 and value >= 0x50:
                        new_state = 1
                    elif mission == 1:
                        if value >= 0x34:
                            value -= 2
                        else:
                            new_state = 2
                    expect((m.byte(ship + ctx['InstanceEnergy']), m.byte('MissionAspEncounterState'))
                           == (value, new_state), cloak, mission, maximum, energy)
                    cases += 1
    return cases
# --- END P11 CHECKS ---

# --- BEGIN STATION CHECKS ---
# Orientation of the persistent station: where the docking slot (local Z axis) points.


def station_vectors(m):
    """Station nose (high bytes, -127..127), station position and planet position."""
    ctx, station = m.ctx, m['InitialRuntimeState']
    nose = [sm8(m.memory[station + ctx['InstanceAxisZ'] + 2 * i + 1]) for i in range(3)]
    return (nose, [get24(m.memory, station + 3 * i) for i in range(3)],
            [get24(m.memory, m['PlanetPosition'] + 3 * i) for i in range(3)])


def vector_angle(u, v):
    cosine = sum(a * b for a, b in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def slot_error(m):
    nose, station, planet = station_vectors(m)
    return vector_angle(nose, [p - s for p, s in zip(planet, station)])


def galaxy_selected_seeds(ctx, galaxy):
    """SelectedSystemSeeds of the 256 systems of a galaxy (0..7), from the game's generator;
    the galaxy seeds are rotated left once per galaxy as GalacticHyperspaceJump does."""
    m = ctx.machine()
    load_jameson(m)
    seeds = [m.memory[ctx['GalaxySeeds'] + i] for i in range(6)]
    for _ in range(galaxy):
        seeds = [(b << 1 | b >> 7) & 255 for b in seeds]
    m.poke('GalaxySeeds', *seeds)
    m.call('LoadGalaxySeedsToGenerator', **ZERO_REGISTERS)
    out = []
    for _ in range(256):
        m.call('DeriveSelectedSystemData', **ZERO_REGISTERS)
        m.call('GenerateSystemName', **ZERO_REGISTERS)
        out.append((m.text('GeneratedSystemName'), [m.memory[ctx['SelectedSystemSeeds'] + i] for i in range(6)]))
    return out


def arrival_positions_entry(ctx):
    """The instruction after RandomiseMarket in ArriveInTargetSystem: LD B,$12 / XOR A /
    LD HL,SunPosition, which clears the sun and planet and places the station."""
    sun = ctx['SunPosition']
    return ctx.find('ArriveInTargetSystem', 'L_D7B4', [0x06, 0x12, 0xAF, 0x21, sun & 255, sun >> 8])


@check('station', 'arrival-slot-direction', ['ArriveInTargetSystem'], 'station-slot investigation',
       'For all 2048 systems: the station is placed $18000 from the planet along z in galaxies 1, 3, 5 '
       'and 8 and along x in galaxies 2, 4, 6 and 7.  Every z placement points the nose (docking slot) '
       'at the planet.  For x the raw compare of sign-magnitude bytes reverses it for a negative planet '
       'x: 464 systems (96, 128, 112 and 128 in galaxies 2, 4, 6 and 7), each exactly 180 degrees away.')
def check_arrival_slot_direction(ctx):
    entry = arrival_positions_entry(ctx)
    m = ctx.machine()
    away = {}
    for galaxy in range(8):
        for name, seeds in galaxy_selected_seeds(ctx, galaxy):
            m.reset()
            m.poke('SelectedSystemSeeds', *seeds)
            m.call(entry, stop='L_D7B4', **ZERO_REGISTERS)
            nose, station, planet = station_vectors(m)
            offset = [p - s for p, s in zip(planet, station)]
            expect(sorted(map(abs, offset)) == [0, 0, 0x18000], name, offset)
            expect(offset[0 if galaxy in (1, 3, 5, 6) else 2] != 0, 'offset axis', galaxy, name)
            error = slot_error(m)
            expect(error < 1e-6 or abs(error - 180) < 1e-6, name, error)
            if error > 90:
                expect(offset[0] != 0 and planet[0] < 0, 'reversal needs a negative planet x', name)
                away[galaxy + 1] = away.get(galaxy + 1, 0) + 1
    expect(away == {2: 96, 4: 128, 6: 112, 7: 128}, away)
    return 2048, dict(reversed_slots_by_galaxy=away)


@check('station', 'dormant-orientation-frozen', ['UpdateStationDormancy', 'MoveObject'],
       'station-slot investigation',
       'After the arrival at DISO (galaxy 1, slot facing the planet) the station is dormant: '
       '20 updates of MoveSunAndPlanet and UpdateStationDormancy at pitch 8 turn the station and '
       'planet positions, but the station axes stay byte for byte the same, so the slot error grows '
       'from 0 to 38 degrees.  Moved next to the player (all high bytes zero), the same pitch turns '
       'the station axes as well.')
def check_dormant_orientation_frozen(ctx):
    station = ctx['InitialRuntimeState']
    axes = slice(station + ctx['InstanceAxisZ'], station + ctx['InstanceAxisX'] + 6)
    seeds = next(seeds for name, seeds in galaxy_selected_seeds(ctx, 0) if name == 'DISO')
    m = ctx.machine()
    m.poke('SelectedSystemSeeds', *seeds)
    m.call(arrival_positions_entry(ctx), stop='L_D7B4', **ZERO_REGISTERS)
    expect(m.byte('StationDormantFlag') == 0xFF and slot_error(m) < 1e-6, 'arrival')
    before, frozen = station_vectors(m), m.memory[axes]
    m.poke('PlayerSpeed', 0)
    m.poke('PlayerPitch', 8)
    m.poke('ObjectLoopCounter', 8)
    for _ in range(20):
        m.call('MoveSunAndPlanet', **ZERO_REGISTERS)
        m.call('UpdateStationDormancy', **ZERO_REGISTERS)
    after = station_vectors(m)
    expect(m.byte('StationDormantFlag') == 0xFF and m.memory[axes] == frozen, 'axes frozen')
    expect(after[1] != before[1] and after[2] != before[2], 'positions moved')
    error = slot_error(m)
    expect(round(error) == 38, error)
    # Near the player MoveObject reaches its orientation step.
    for i, value in enumerate((0x1000, -0x800, 0x6000)):
        put24(m.memory, station + 3 * i, value)
    m.call('UpdateStationDormancy', **ZERO_REGISTERS)
    expect(m.memory[axes] != frozen and m.byte('StationDormantFlag') == 0, 'near: axes turn, switched on')
    return 2, dict(slot_error_after_20_pitch_updates=round(error, 1))


@check('station', 'orientation-pitch-quantisation', ['RotateVectorRollPitch', 'ApplyPlayerMotion'],
       'station-slot investigation',
       'RotateVectorRollPitch uses the shear steps of ApplyPlayerMotion at the same scale, but '
       'truncates pitch/2.  For 32 updates: pitch 1 turns a position by 7.2 degrees and a unit axis '
       'not at all; pitch 3 turns the axis by 14.5 degrees like pitch 2 while the position turns by '
       '21.4; roll 1 turns both alike (14.5 and 14.1 degrees).')
def check_orientation_pitch_quantisation(ctx):
    vector, body = ctx.scratch, ctx['PlanetPosition']

    def turn_axis(start, roll, pitch):
        m = ctx.machine()
        for i, value in enumerate(start):
            m.poke(vector + 2 * i, 0, abs(value) | (0x80 if value < 0 else 0))
        m.poke('RollRotationAngle', roll)
        m.poke('PitchRotationAngle', pitch)
        for _ in range(32):
            m.call('RotateVectorRollPitch', ix=vector, **ZERO_REGISTERS)
        return vector_angle(start, [sm8(m.byte(vector + 2 * i + 1)) for i in range(3)])

    def turn_position(start, roll, pitch):
        m = ctx.machine()
        for i, value in enumerate(start):
            put24(m.memory, body + 3 * i, value)
        m.poke('PlayerRoll', roll)
        m.poke('PlayerPitch', pitch)
        m.poke('PlayerSpeed', 0)
        for _ in range(32):
            m.call('ApplyPlayerMotion', ix=body, **ZERO_REGISTERS)
        return vector_angle(start, [get24(m.memory, body + 3 * i) for i in range(3)])

    measured = {}
    for name, roll, pitch, axis_start, body_start in (
            ('pitch1', 0, 1, (0, 0, 127), (0, 0, 0x10000)), ('pitch2', 0, 2, (0, 0, 127), (0, 0, 0x10000)),
            ('pitch3', 0, 3, (0, 0, 127), (0, 0, 0x10000)), ('roll1', 1, 0, (127, 0, 0), (0x10000, 0, 0))):
        measured[name] = (round(turn_axis(axis_start, roll, pitch), 1),
                          round(turn_position(body_start, roll, pitch), 1))
    expect(measured == {'pitch1': (0.0, 7.2), 'pitch2': (14.5, 14.1), 'pitch3': (14.5, 21.4),
                        'roll1': (14.5, 14.1)}, measured)
    return 8, {name: dict(axis_degrees=a, position_degrees=p) for name, (a, p) in measured.items()}


@check('station', 'roll-drift-keeps-slot', ['ApplyPlayerMotion', 'RotateVectorRollPitch', 'MoveObject',
                                            'OrthogonaliseYVector', 'RenormaliseOrientationVector'],
       'station-slot investigation',
       'The roll-reversal drift does not turn an active station away from the planet: positions and '
       'axes get the same shear steps.  From the launch layout (planet $18000 ahead, station just '
       'behind with unit axes, active), 20 updates at pitch 8 and then the 1280 updates of '
       'maths/roll-reversal-drift move the planet 2.29 times further from the view axis, while the '
       'slot error only changes from 3.5 to 8.6 degrees (rounding of the 8-bit axes).')
def check_roll_drift_keeps_slot(ctx):
    """Each update is MoveSunAndPlanet, UpdateStationDormancy and the slot-0 part of UpdateObjects
    from L_DB8B (MoveObject, OrthogonaliseYVector, RenormaliseOrientationVector x3) to L_DBA3."""
    station, planet = ctx['InitialRuntimeState'], ctx['PlanetPosition']
    m = ctx.machine()
    m.clear(station, ctx['InstanceAxisX'] + 6)
    m.poke(station + ctx['InstanceZ'], 0xF0)
    m.poke(station + ctx['InstanceZ'] + 2, 0x80)
    for axis_name, component in (('InstanceAxisZ', 2), ('InstanceAxisY', 1), ('InstanceAxisX', 0)):
        m.poke(station + ctx[axis_name] + 2 * component + 1, 0x7F)
    m.poke(station + ctx['InstanceEnergy'], 0xF0)
    m.poke('StationDormantFlag', 0)
    for i, value in enumerate((0, 0, 0x18000)):
        put24(m.memory, planet + 3 * i, value)
    m.poke('PlayerSpeed', 0)
    m.poke('PlayerPitch', 0)
    m.poke('ObjectLoopCounter', 8)
    blueprint = m.word(station + INSTANCE_BLUEPRINT)

    def update(roll=0, pitch=0):
        m.poke('PlayerRoll', roll)
        m.poke('PlayerPitch', pitch)
        m.call('MoveSunAndPlanet', **ZERO_REGISTERS)
        m.call('UpdateStationDormancy', **ZERO_REGISTERS)
        m.call('L_DB8B', stop='L_DBA3', ix=station, iy=blueprint, **ZERO_REGISTERS)

    for _ in range(20):
        update(pitch=8)
    before = slot_error(m)
    off0 = math.hypot(*(get24(m.memory, planet + 3 * i) for i in range(2)))
    for roll in alternating_roll_bytes(32, 20):
        update(roll=roll)
    after = slot_error(m)
    off1 = math.hypot(*(get24(m.memory, planet + 3 * i) for i in range(2)))
    expect(m.byte('StationDormantFlag') == 0, 'the station stays active')
    measured = (round(before, 1), round(after, 1), round(off1 / off0, 2))
    expect(measured == (3.5, 8.6, 2.29), measured)
    return 1300, dict(slot_error_before=measured[0], slot_error_after=measured[1],
                      planet_off_axis_growth=measured[2])
# --- END STATION CHECKS ---

# --- BEGIN FUEL CHECKS ---
# Fuel-derived values outside the saved commander record.


@check('commander', 'fuel-price-not-restored', ['EquipShipScreen', 'GetEquipmentPriceEntry',
                                                'NormalHyperspaceJump', 'GalacticHyperspaceJump'],
       'fuel-price investigation',
       'FuelPrice (entry 0 of EquipmentPriceTable) lies in the game image, not in the commander '
       'record.  After loading the game its tape value is 0, so a loaded record with 3.4 light years '
       'still gets fuel entry 0.0.  Only NormalHyperspaceJump (2*economy + 70 - fuel: 4.6 Cr for '
       'economy 5 and 3.4 light years left), GalacticHyperspaceJump (old galaxy + 1 for galaxies '
       '0..7, fuel unchanged) and the fuel purchase (0) write it.')
def check_fuel_price_not_restored(ctx):
    m = ctx.machine()
    load_jameson(m)
    m.poke('FuelLevel', 34)                         # a loaded record: 3.4 light years
    expect(m.byte('FuelPrice') == 0, 'tape value')
    m.call('GetEquipmentPriceEntry', a=1, f=0, bc=0, de=0, hl=0)
    entry = m.pair('hl')
    expect(entry == ctx['EquipmentPriceTable'] and m.memory[entry:entry + 3] == [0, 0, 0], 'fuel entry 0.0')
    cases = 1
    m.reset()
    load_jameson(m)
    m.poke('SelectedSystemDistance', 36)
    m.poke('SelectedSystemEconomy', 5)
    m.poke('AuxRandomSeed', 0)                      # no mis-jump
    m.call('NormalHyperspaceJump', stop='ArriveInTargetSystem', **ZERO_REGISTERS)
    expect((m.byte('FuelLevel'), m.byte('FuelPrice')) == (34, 46), 'normal jump',
           m.byte('FuelLevel'), m.byte('FuelPrice'))
    cases += 1
    for galaxy in range(8):
        m.reset()
        load_jameson(m)
        m.poke('FuelLevel', 34)
        m.poke('CurrentGalaxy', galaxy)
        m.call('GalacticHyperspaceJump', stop='SnapCursorToNearestSystem', **ZERO_REGISTERS)
        expect((m.byte('FuelLevel'), m.byte('FuelPrice')) == (34, galaxy + 1), 'galactic jump', galaxy)
        cases += 1
    return cases


@check('commander', 'fuel-gauge-not-restored', ['FuelGauge', 'PrepareShipForLaunch', 'StoreFuelLevel'],
       'fuel-price investigation',
       'FuelGauge (the FU bar value) is not in the commander record either.  Its tape value 160 '
       '(full) stays when a loaded record holds 3.4 light years, also through PrepareShipForLaunch at '
       'the launch.  StoreFuelLevel, the end of SetFuelLevel, gives 76 and leaves FuelLevel as it is.')
def check_fuel_gauge_not_restored(ctx):
    m = ctx.machine()
    load_jameson(m)
    m.poke('FuelLevel', 34)
    expect(m.byte('FuelGauge') == 160, 'tape value')
    m.call('PrepareShipForLaunch', halt=True, **ZERO_REGISTERS)
    expect(m.byte('FuelGauge') == 160 and m.byte('FuelLevel') == 34, 'launch keeps it')
    m.call('StoreFuelLevel', a=34, f=0, bc=0, de=0, hl=0)
    expect((m.byte('FuelGauge'), m.byte('FuelLevel')) == (76, 34), m.byte('FuelGauge'))
    return 2
# --- END FUEL CHECKS ---

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--list', action='store_true', help='list the check groups and checks')
    parser.add_argument('--only', action='append', metavar='GROUP',
                        help='run only this group (repeatable)')
    args = parser.parse_args()
    if args.list:
        for group, names in GROUPS.items():
            print(group)
            for item in CHECKS:
                if item['group'] == group:
                    print(f"  {item['name']:32} {', '.join(item['routines'])}")
        return 0
    selected = args.only or list(GROUPS)
    unknown = [group for group in selected if group not in GROUPS]
    if unknown:
        parser.error('unknown group(s): ' + ', '.join(unknown) + '; use --list')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.unlink(missing_ok=True)
    ctx = Context()
    results, failures, started = {}, [], time.perf_counter()
    ordered = [item for group in GROUPS for item in CHECKS if item['group'] == group]
    for item in ordered:
        if item['group'] not in selected:
            continue
        label = f"{item['group']}/{item['name']}"
        begin = time.perf_counter()
        try:
            outcome = item['function'](ctx)
        except AssertionError as error:
            failures.append(label)
            print(f'FAIL {label}: {error!r}'[:2000])
            results.setdefault(item['group'], {})[item['name']] = dict(passed=False, error=repr(error)[:2000])
            continue
        cases, details = outcome if isinstance(outcome, tuple) else (outcome, None)
        entry = dict(passed=True, cases=cases, routines=item['routines'], claim=item['claim'],
                     replaces=item['replaces'])
        if details:
            entry['details'] = details
        results.setdefault(item['group'], {})[item['name']] = entry
        print(f'PASS {label}: {cases:,} cases ({time.perf_counter() - begin:.1f} s)')
    report = dict(passed=not failures, machine='ZX Spectrum 48K (48K ROM, 64K memory model)',
                  rom_sha256=sha(ctx.rom), image_sha256=sha(ctx.image), tape_sha256=sha(ctx.tape),
                  groups=[group for group in GROUPS if group in selected], failures=failures, results=results,
                  scope='Controlled Z80 routine tests in SkoolKit; no interrupts, no tape load.')
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    total = sum(r.get('cases', 0) for g in results.values() for r in g.values())
    checks = sum(len(g) for g in results.values())
    status = 'FAIL' if failures else 'PASS'
    print(f'{status}: {checks - len(failures)}/{checks} checks, {total:,} cases, '
          f'{time.perf_counter() - started:.1f} s; {OUTPUT.relative_to(ROOT).as_posix()}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
