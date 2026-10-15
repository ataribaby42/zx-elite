"""Check textfullstopfix=yes in ZX Spectrum 48K RAM.

Run from the project directory after a build with the option, for example

    make.bat textfullstopfix=yes verify=no
    python tools/check_text_full_stop_fix.py
    python tools/check_text_full_stop_fix.py --emulator

Justified text is laid out by BufferJustifiedCharacter in lines of 30
characters.  The original tests for a full stop before it counts the
character, so a full stop arriving as the 31st character is stored after the
printed line and lost.

The simulator part runs the assembled image and a baseline whose two
replaced parts are restored from the reference tape, with the supplied 48K ROM
in SkoolKit's simulator.  PutCharacter and NewLine only record the output.

- All 2,048 planet descriptions (L_BA49, as on the DATA ON screen): both images
  receive the same characters, and every fixed description ends with its full
  stop.  The original loses it in exactly 72 of them.  Every other description is
  printed identically.  In the 72, the last word moves to a new line with its
  full stop, and the line before it is justified to 30 characters.
- Synthetic texts: a full stop as the 31st character in the middle of a text
  prints its word at once, and the next sentence starts on a new line, as after
  any other full stop; random texts lose no character in the fixed image and
  are otherwise printed as by the original.

--emulator loads release/elite-128k.tap through the 48K ROM, finds SOCELAGE
with the galactic chart search and opens its DATA ON screen with real key
presses.  A second run restores the original bytes with a test-only poke.
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

OUTPUT = ROOT / 'build/text-full-stop-fix-check'
PARTS = ('TextFullStopBuffer', 'TextFullStopHook')
LINE_WIDTH = 30
LOST_DESCRIPTIONS = 72                  # docs/FINDINGS.md, text/description-full-stop-loss
EXAMPLE = 'SOCELAGE'                        # galaxy 1, system 45


class Checker:
    def __init__(self):
        s = self.symbols = symbol_map(ROOT / 'build/game.map')
        assert s.get('TEXT_FULL_STOP_FIX') == 1, 'Build textfullstopfix=yes first'
        self.image = (ROOT / 'build/game.bin').read_bytes()
        self.base = s['GameImage']
        self.parts = [(s[part + 'Start'], s[part + 'Limit']) for part in PARTS]
        assert self.parts == [(0xBCFC, 0xBD1B), (0xBDF5, 0xBE00)], self.parts
        assert self.parts[0][0] == s['BufferJustifiedCharacter'] and self.parts[1][1] == s['SquareLookupTables']
        original = reference()[1][5].payload
        self.original_parts = [bytes(original[a - self.base:b - self.base]) for a, b in self.parts]
        baseline = bytearray(self.image)
        for (start, end), data in zip(self.parts, self.original_parts):
            baseline[start - self.base:end - self.base] = data
        self.baseline = bytes(baseline)
        self.fixed = cr.ImageContext(s, self.image)
        self.original = cr.ImageContext(s, self.baseline)
        self.report = dict(machine='ZX Spectrum 48K', game_sha256=sha(self.image))

    def check_layout(self):
        changed = [self.base + i for i, (a, b) in enumerate(zip(self.image, self.baseline)) if a != b]
        assert changed and all(any(a <= x < b for a, b in self.parts) for x in changed)
        assert not any(self.original_parts[1]), 'the hook area must be the original zero padding'
        self.report['changed_bytes'] = len(changed)
        print(f'PASS: {len(changed)} changed bytes, all inside the start of BufferJustifiedCharacter '
              f'and the zero padding before the square tables.', flush=True)

    @staticmethod
    def recorder():
        out = []
        stubs = {'PutCharacter': lambda mm: out.append(chr(mm.reg('a'))),
                 'NewLine': lambda mm: out.append('\n')}
        return out, stubs

    def feed(self, context, text):
        m = context.machine()
        out, stubs = self.recorder()
        m.call('StartJustifiedText', stubs=stubs, a=0)
        for character in text:
            m.call('PrintCharacter', stubs=stubs, a=ord(character))
        m.call('EndJustifiedText', stubs=stubs, a=0)
        return lines(out)

    def descriptions(self, context):
        """Characters fed to the justified printer and printed lines for all 2,048 systems."""
        s, results = self.symbols, []
        m = context.machine()
        for galaxy in range(8):
            m.reset()
            cr.load_jameson(m)
            seeds = [m.memory[s['GalaxySeeds'] + i] for i in range(6)]
            for _ in range(galaxy):
                seeds = [((b << 1) | (b >> 7)) & 0xFF for b in seeds]
            m.poke('GalaxySeeds', *seeds)
            m.call('LoadGalaxySeedsToGenerator', **cr.ZERO_REGISTERS)
            for system in range(256):
                m.call('DeriveSelectedSystemData', **cr.ZERO_REGISTERS)
                m.call('GenerateSystemName', **cr.ZERO_REGISTERS)
                saved = list(m.memory)
                name = m.text('GeneratedSystemName')
                m.poke('SelectedSystemName', *(name.encode() + bytes(9 - len(name))))
                fed, (out, stubs) = [], self.recorder()
                hooks = {'PrintCharacter': lambda mm: fed.append(chr(mm.reg('a')))
                         if mm.byte('TextRedirectFlag') == 1 else None}
                m.call('L_BA49', hooks=hooks, stubs=stubs, limit=3_000_000, halt=True, **cr.ZERO_REGISTERS)
                results.append((galaxy, system, name, ''.join(fed), lines(out)))
                m.memory[:] = saved
        return results

    def check_descriptions(self):
        fixed, original = self.descriptions(self.fixed), self.descriptions(self.original)
        lost, example = [], None
        for f, o in zip(fixed, original):
            galaxy, system, name, fed, f_lines = f
            assert o[:4] == f[:4] and fed.endswith('.'), (f[:4], o[:4])
            o_lines = o[4]
            assert all(len(line) == LINE_WIDTH for line in f_lines + o_lines), (name, f_lines, o_lines)
            # The printed text can differ from the characters fed: an adjective drops a
            # final letter of the name (BIARGE: "Biargian").  Compare the two images instead.
            assert printed(f_lines).endswith('.'), (name, f_lines)
            if printed(f_lines) == printed(o_lines):
                assert f_lines == o_lines, (name, f_lines, o_lines)
                continue
            assert printed(f_lines) == printed(o_lines) + '.', (name, f_lines, o_lines)
            assert_wrapped(o_lines, f_lines)
            lost.append(f'{galaxy + 1}/{system} {name}')
            if name == EXAMPLE and galaxy == 0:
                example = dict(original=o_lines, fixed=f_lines)
        assert len(lost) == LOST_DESCRIPTIONS and example, (len(lost), example)
        self.report['descriptions'] = dict(checked=len(fixed), original_lost_full_stops=len(lost),
                                           systems=lost, example=example)
        print(f'PASS: all {len(fixed)} planet descriptions: the original loses the final full stop in '
              f'{len(lost)}, the fixed image in none; there the last word moves to a new line with its '
              f'full stop, every other description is printed identically.', flush=True)
        print('      ' + EXAMPLE + ': ' + ' / '.join(line.rstrip() for line in example['fixed']), flush=True)

    def check_synthetic(self, texts=600):
        sentence = 'A BB CCC DDDD EEEEE FFFFFF GGGGGGG HHHHHHHH IIIIIIIII JJJJJJJJJJ K LL MMM NNNN OOOOO.'
        o_lines = self.feed(self.original, sentence + ' PP QQQ.')
        f_lines = self.feed(self.fixed, sentence + ' PP QQQ.')
        row = next(i for i, line in enumerate(o_lines) if line.startswith('Jjjjjjjjjj'))
        assert o_lines[row] == 'Jjjjjjjjjj K Ll Mmm Nnnn Ooooo', o_lines
        assert f_lines[:row] == o_lines[:row] and f_lines[row + 2:] == o_lines[row + 1:], (o_lines, f_lines)
        assert f_lines[row].split() == o_lines[row].split()[:-1] and f_lines[row + 1].rstrip() == 'Ooooo.'
        assert o_lines[row + 1].rstrip() == ' Pp Qqq.', o_lines
        rng = random.Random(3)
        lost = 0
        for _ in range(texts):
            words = []
            for _ in range(rng.randrange(5, 40)):
                word = ''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(rng.randrange(1, 12)))
                words.append(word + ('.' if rng.random() < 0.2 else ''))
            text = ' '.join(words) + '.'
            o_lines, f_lines = self.feed(self.original, text), self.feed(self.fixed, text)
            assert printed(f_lines) == significant(text), (text, f_lines)
            if printed(o_lines) == significant(text):
                assert f_lines == o_lines, (text, o_lines, f_lines)
            else:
                lost += 1
        assert lost
        self.report['synthetic'] = dict(random_texts=texts, original_lost_characters_in=lost)
        print(f'PASS: synthetic texts: a full stop as the 31st character in mid-text prints its word on a '
              f'line of its own and the next sentence starts a new line; {texts} random texts lose no '
              f'character in the fixed image ({lost} lose one in the original) and are otherwise printed '
              f'identically.', flush=True)

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'verification.json').unlink(missing_ok=True)
        self.check_layout()
        self.check_descriptions()
        self.check_synthetic()

    def write(self):
        (OUTPUT / 'verification.json').write_text(json.dumps(dict(passed=True, **self.report), indent=2) + '\n',
                                                  encoding='utf-8')


def lines(out):
    return [line for line in ''.join(out).split('\n') if line]


def significant(text):
    return ''.join(text.split()).upper()


def printed(text_lines):
    return significant(''.join(text_lines))


def assert_wrapped(o_lines, f_lines):
    """The fixed layout of a description whose final full stop the original lost."""
    *head, last = o_lines
    words = last.split()
    assert len(f_lines) == len(o_lines) + 1 and f_lines[:-2] == head, (o_lines, f_lines)
    assert f_lines[-2].split() == words[:-1] and f_lines[-2][0] != ' ' and f_lines[-2][-1] != ' ', f_lines
    assert f_lines[-1].rstrip() == words[-1] + '.', f_lines


def emulator(checker):
    import run_runtime_scenarios as rs
    assert bytes(parse(RELEASE_TAP.read_bytes())[5].payload) == checker.image, \
        'Build the option with the default tapfile first'
    second, keys = 11.0, [*rs.key(8, 0.3, 'I'), *rs.key(10, 0.3, 'R')]
    for character in EXAMPLE:
        keys += rs.key(f'{second:.2f}', 0.18, character)
        second += 0.45
    keys += [*rs.key(f'{second:.2f}', 0.25, 'ENTER'), *rs.key(f'{second + 1.5:.2f}', 0.4, 'P')]
    restore = [arg for (start, _), data in zip(checker.parts, checker.original_parts)
               for arg in rs.poke(7, f'{start:#06x}', data.hex())]
    results = {}
    for name, extra in (('fixed', []), ('original', restore)):
        run = f'text-full-stop-{name}'
        args = [*rs.started(second + 4), *keys, *extra]
        subprocess.run([sys.executable, str(rs.CHECKER), *args, '--name', run, '--no-screenshots'],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads((ROOT / f'build/emulator/{run}.json').read_text())
        assert report['machine'] == 'ZX Spectrum 48K' and all(p['applied'] for p in report['test_pokes'])
        text = [row['text'].rstrip(' _') for row in report['final_text']]
        assert any(EXAMPLE.title() in row or EXAMPLE in row.upper() for row in text), text
        results[name] = text
    assert any(row.endswith('Meat.') for row in results['fixed']), results['fixed']
    assert any(row.endswith('Goat Meat') for row in results['original']), results['original']
    assert not any('Meat.' in row for row in results['original']), results['original']
    print('PASS: 48K emulator: ROM load, galactic chart search for SOCELAGE and its DATA ON screen. The '
          'original ends the description with "Goat Meat" and no full stop; the fixed image prints '
          '"Meat." on the next line.', flush=True)
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
