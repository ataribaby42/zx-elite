"""Check stardustfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat stardustfix=yes verify=no
    python tools/check_stardust_fix.py
    python tools/check_stardust_fix.py --emulator

The simulator part runs the assembled image and a baseline whose
GetDustPixelAddress is restored from the reference tape, with the supplied 48K
ROM in SkoolKit's Z80 simulator:

- ClearViewBuffer draws the view frame in rows 0 and 127 and columns 8 and 247,
  so the interior is DustViewFirstColumn..DustViewLastColumn (9..246);
- GetDustPixelAddress for every X 0..127 and Y 0..62 (the range that
  StoreAndPlotDust plots) with all four sign combinations matches a pixel model:
  the original selects the buffer half from the Y sign, so negative zero lands
  on row 127; the fixed routine puts it on row 63 and returns the mask 0 for a
  column outside the interior; DE, C and A are otherwise the original ones;
- whole dust passes, after SeedLaunchDust at the launch speed and in flight with
  random particles, speeds, roll and pitch in all four views: both images get
  the same particle records, random state and GetDustPixelAddress inputs, every
  plotted pixel matches the model, and each pass XORed into a freshly cleared
  view leaves the frame and the area outside it unchanged in the fixed image,
  while the original damages them.

--emulator loads release/elite-128k.tap through the 48K ROM and launches.  A
test-only poke then turns all 16 particles into negative-zero particles; a
second run also restores the original routine with a test-only poke.  The final
screen of the original has holes in the bottom frame line, the fixed one none.
Build the option with the default tapfile for this mode.
"""
import argparse
import json
import random
import subprocess
import sys

from tape import ROOT, RELEASE_TAP, parse, reference, sha
from build import symbol_map
import check_routines as cr

OUTPUT = ROOT / 'build/stardust-fix-check'
FRAME_ROWS = (0, cr.VIEW_ROWS - 1)
RECORD, COUNT = cr.DUST_RECORD, cr.DUST_COUNT
PLOTTED_Y = range(0x3F)                 # StoreAndPlotDust plots only |Y| < 63
X_SIGN, Y_SIGN = 0x80, 0x40             # DustFlags bits 7 and 6


def view_pixel(column, row, buffer):
    """Buffer address and mask of a view pixel (Spectrum layout, 128 rows)."""
    return buffer + cr.screen_offset(column, row), 0x80 >> (column & 7)


def model(x, y, flags, buffer, first, last, fixed):
    """(address, mask) that GetDustPixelAddress returns for DustX, DustY, DustFlags."""
    column = (0x80 - x if flags & X_SIGN else 0x80 + x) & 0xFF
    row = 0x3F + y if flags & Y_SIGN else 0x3F - y
    if fixed:
        address, mask = view_pixel(column, row, buffer)
        return address, mask if first <= column <= last else 0
    lower = bool(flags & Y_SIGN)                 # the half follows the sign alone
    return view_pixel(column, (row & 0x3F) | (0x40 if lower else 0), buffer)


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('STARDUST_FIX') == 1, 'Build stardustfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.part = (s['StardustPixelStart'], s['StardustPixelLimit'])
        assert self.part == (s['GetDustPixelAddress'], s['RespawnDust']) == (0xA2EF, 0xA334), self.part
        start, end = self.part
        self.original_bytes = bytes(reference()[1][5].payload[start - self.base:end - self.base])
        baseline = bytearray(self.image)
        baseline[start - self.base:end - self.base] = self.original_bytes
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.buffer = s['ViewBitmapBuffer']
        self.first, self.last = s['DustViewFirstColumn'], s['DustViewLastColumn']
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        start, end = self.part
        assert changed and all(start <= a < end for a in changed)
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside GetDustPixelAddress '
              f'(${start:04X}..${end - 1:04X}).', flush=True)

    def check_frame(self):
        m = self.fixed.machine()
        m.call('ClearViewBuffer')
        lit = cr.bitmap_pixels(m.memory, self.buffer, cr.VIEW_ROWS)
        left, right = self.first - 1, self.last + 1
        frame = ({(x, y) for x in range(left, right + 1) for y in FRAME_ROWS} |
                 {(x, y) for x in (left, right) for y in range(cr.VIEW_ROWS)})
        assert lit == frame, sorted(lit ^ frame)[:10]
        self.frame = frame
        print(f'PASS: ClearViewBuffer draws the frame in rows {FRAME_ROWS} and columns {left} and {right}; '
              f'dust may use columns {self.first}..{self.last}.', flush=True)

    def pixel(self, m, x, y, flags):
        m.poke('DustX', x)
        m.poke('DustY', y)
        m.poke('DustFlags', flags)
        m.call('GetDustPixelAddress')
        return m.pair('de'), m.reg('c'), m.reg('a'), m.reg('b'), m.reg('l')

    def check_routine(self):
        fixed, original = self.fixed.machine(), self.original.machine()
        cases = negative_zero = outside = 0
        for x in range(0x80):
            for y in PLOTTED_Y:
                for signs in (0, X_SIGN, Y_SIGN, X_SIGN | Y_SIGN):
                    flags = signs | (x + y) & 0x38                  # vary the unused flag bits
                    f, o = self.pixel(fixed, x, y, flags), self.pixel(original, x, y, flags)
                    want_f = model(x, y, flags, self.buffer, self.first, self.last, True)
                    want_o = model(x, y, flags, self.buffer, self.first, self.last, False)
                    assert (o[0], o[1]) == want_o and o[2] == o[1] and o[3] == 0, (x, y, flags, o, want_o)
                    assert (f[0], f[1]) == want_f and f[2] == f[1] and f[3:] == o[3:], (x, y, flags, f, want_f)
                    if (f[0], f[1]) != (o[0], o[1]):
                        zero = y == 0 and flags & Y_SIGN
                        assert zero or not want_f[1], (x, y, flags)
                        negative_zero += bool(zero)
                        outside += not want_f[1]
                    cases += 1
        self.report['routine'] = dict(cases=cases, changed=dict(negative_zero=negative_zero, outside_frame=outside))
        print(f'PASS: GetDustPixelAddress for {cases} inputs: the original matches the model with negative '
              f'zero on row 127; the fixed routine puts it on row 63 ({negative_zero} inputs), masks '
              f'{outside} inputs outside columns {self.first}..{self.last} and returns the original DE, C, A, '
              f'B and L for all others.', flush=True)

    def dust_pass(self, m, fixed):
        """One MoveAndPlotDust pass into a cleared view; returns the calls and the view."""
        calls, entries = [], []
        m.call('ClearViewBuffer')
        m.call('MoveAndPlotDust', hooks={
            'GetDustPixelAddress': lambda mm: calls.append((mm.byte('DustX'), mm.byte('DustY'),
                                                            mm.byte('DustFlags') & (X_SIGN | Y_SIGN))),
            'XorPlotDustList': lambda mm: entries.extend(
                (mm.word(mm['DustPlotList'] + 3 * i), mm.byte(mm['DustPlotList'] + 3 * i + 2))
                for i in range(mm.byte('DustPlotCount')))})
        assert len(calls) == len(entries)
        plotted = bytearray(cr.VIEW_SIZE)
        for (x, y, flags), entry in zip(calls, entries):
            assert y in PLOTTED_Y, (x, y)
            assert entry == model(x, y, flags, self.buffer, self.first, self.last, fixed), (x, y, flags, entry)
            address, mask = entry
            plotted[address - self.buffer] ^= mask
        lit = cr.bitmap_pixels(m.memory, self.buffer, cr.VIEW_ROWS)
        assert lit == self.frame ^ cr.bitmap_pixels(plotted, 0, cr.VIEW_ROWS), 'view is not frame XOR dust'
        return calls, lit

    def state(self, m):
        records = m['DustParticleRecords']
        return (tuple(m.memory[records:records + RECORD * COUNT]), m.word('AuxRandomSeed'),
                m.byte('AlternatingBits'))

    def run_passes(self, setups, passes, stats):
        fixed, original = self.fixed.machine(), self.original.machine()
        interior = set(range(self.first, self.last + 1))
        for setup in setups:
            for m in (fixed, original):
                m.reset()
                setup(m)
            for _ in range(passes):
                f_calls, f_lit = self.dust_pass(fixed, True)
                o_calls, o_lit = self.dust_pass(original, False)
                assert f_calls == o_calls and self.state(fixed) == self.state(original)
                stats['passes'] += 1
                stats['plotted'] += len(f_calls)
                stats['negative_zero'] += sum(1 for _, y, flags in f_calls if y == 0 and flags & Y_SIGN)
                stats['outside'] += sum(1 for x, _, flags in f_calls
                                        if (0x80 - x if flags & X_SIGN else 0x80 + x) & 0xFF not in interior)
                assert self.frame <= f_lit, 'fixed: frame pixel erased'
                assert all(x in interior for x, y in f_lit - self.frame), 'fixed: pixel outside the frame'
                if not self.frame <= o_lit or any(x not in interior for x, y in o_lit - self.frame):
                    stats['original_damaged_passes'] += 1

    def check_launch(self, seeds=96, passes=12):
        def seeded(seed):
            def setup(m):
                m.poke_word('AuxRandomSeed', seed)
                m.call('SeedLaunchDust')                 # also sets the launch speed 7
                for name in ('CurrentScreenId', 'DustLastScreenId', 'PlayerRoll', 'PlayerPitch',
                             'WitchspaceFlag', 'TorusJumpDustFlag'):
                    m.poke(name, 0)
            return setup
        rng = random.Random(1)
        stats = dict(passes=0, plotted=0, negative_zero=0, outside=0, original_damaged_passes=0)
        self.run_passes([seeded(rng.randrange(0x10000)) for _ in range(seeds)], passes, stats)
        assert stats['negative_zero'] and stats['original_damaged_passes']
        self.report['launch'] = dict(seeds=seeds, **stats)
        print(f'PASS: launch dust, {seeds} seeds x {passes} passes: {stats["plotted"]} plotted particles, '
              f'{stats["negative_zero"]} at negative zero; the original damages the frame in '
              f'{stats["original_damaged_passes"]} passes, the fixed image in none; records identical.',
              flush=True)

    def check_flight(self, sequences=80, passes=8):
        rng = random.Random(2)

        def rate():
            return rng.choice((0, rng.randrange(1, 16) | rng.choice((0, 0x80))))

        setups = []                              # roll and pitch drawn once per sequence
        for _ in range(sequences):
            seed, roll, pitch = rng.randrange(1 << 30), rate(), rate()

            def setup(m, seed=seed, roll=roll, pitch=pitch):
                local = random.Random(seed)
                screen = local.randrange(4)
                m.poke('CurrentScreenId', screen)
                m.poke('DustLastScreenId', screen)
                m.poke('PlayerRoll', roll, pitch, local.randrange(0, 41))
                m.poke('WitchspaceFlag', 0)
                m.poke('TorusJumpDustFlag', 0)
                m.poke_word('AuxRandomSeed', local.randrange(0x10000))
                records = m['DustParticleRecords']
                for i in range(COUNT):
                    m.poke(records + RECORD * i, local.randrange(0x78) | local.choice((0, 0x80)),
                           local.choice((0, local.randrange(0x3F))) | local.choice((0, 0x80)),
                           local.randrange(0x10, 0x100), local.randrange(256), local.randrange(256))
            setups.append(setup)
        stats = dict(passes=0, plotted=0, negative_zero=0, outside=0, original_damaged_passes=0)
        self.run_passes(setups, passes, stats)
        assert stats['negative_zero'] and stats['outside'] and stats['original_damaged_passes']
        self.report['flight'] = dict(sequences=sequences, **stats)
        print(f'PASS: flight dust, {sequences} sequences x {passes} passes in all four views with random '
              f'speed, roll and pitch: {stats["plotted"]} plotted particles, {stats["negative_zero"]} at '
              f'negative zero, {stats["outside"]} outside the interior; the original damages the frame in '
              f'{stats["original_damaged_passes"]} passes, the fixed image in none; records identical.',
              flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_frame()
        self.check_routine()
        self.check_launch()
        self.check_flight()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def bottom_line_holes(memory, first, last):
    """Columns of the bottom frame line (screen row 127) that are not lit."""
    row = cr.VIEW_ROWS - 1
    return [x for x in range(first - 1, last + 2)
            if not memory[cr.SCREEN + cr.screen_offset(x, row)] & 0x80 >> (x & 7)]


def emulator(checker):
    import run_runtime_scenarios as rs
    symbols = checker.symbols
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == checker.image, \
        'Build the option with the default tapfile first'
    records = symbols['DustParticleRecords']
    particles = bytearray()
    for i in range(COUNT):                       # columns 17..239, all at Y = -0 (record byte 1 = $80)
        particles += bytes((6 + 7 * i | (0x80 if i & 1 else 0), 0x80, 0xF0, 0, 0))
    results = {}
    for name, extra in (('fixed', []),
                        ('original', rs.poke(11, f'{checker.part[0]:#06x}', checker.original_bytes.hex()))):
        run = f'stardust-{name}'
        args = [*rs.started(14), *rs.key(8, 0.4, '1'), *extra, *rs.poke(12, f'{records:#06x}', particles.hex())]
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', run, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{run}.json').read_text())
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        assert symbols['GetDustPixelAddress'] in set(report['execution_map'])
        memory = (ROOT / f'build/emulator/{run}-memory.bin').read_bytes()
        negative_zero = sum(memory[records + RECORD * i + 1] == 0x80 for i in range(COUNT))
        holes = bottom_line_holes(memory, checker.first, checker.last)
        results[name] = dict(negative_zero_particles=negative_zero, bottom_line_holes=holes)
    assert results['fixed']['negative_zero_particles'] and not results['fixed']['bottom_line_holes'], results
    assert results['original']['bottom_line_holes'], results
    print(f'PASS: 48K emulator: ROM load, launch and 16 negative-zero particles. With the original routine '
          f'restored the bottom frame line has holes in columns {results["original"]["bottom_line_holes"]}; '
          f'the fixed image keeps it intact ({results["fixed"]["negative_zero_particles"]} particles still at '
          f'negative zero).', flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emulator', action='store_true', help='also run the 48K ROM-load scenarios')
    args = parser.parse_args()
    checker = Checker()
    checker.run()
    if args.emulator:
        checker.report['emulator'] = emulator(checker)
    checker.write()


if __name__ == '__main__':
    main()
