"""Check compassflickerfix=yes against the original scanner copy in ZX Spectrum 48K.

Run after a modified build. --emulator also loads its TAP, launches, and
compares the live compass immediately before and after the in-flight scanner.
"""
import argparse
import contextlib
import io
import json
import random

import check_routines as cr
from build import symbol_map
from tape import ROOT, parse, reference, release_tap, sha

OUT = ROOT / 'build/compass-flicker-check'


def compass(memory):
    return bytes(memory[cr.SCREEN + cr.screen_offset(x, y)]
                 for y in range(136, 160) for x in (168, 176, 184))


def check_copy(ctx):
    """Every destination byte, both directions, including the adjacent scanner bits."""
    m = ctx.machine()
    rng = random.Random(48)
    start = cr.SCREEN
    end = start + cr.SCREEN_SIZE + cr.ATTRIBUTES_SIZE
    screen = [rng.randrange(256) for _ in range(end - start)]
    m.memory[start:end] = screen
    cells = [start + cr.screen_offset(x, y) for y in range(144, 192) for x in range(72, 176, 8)]
    backup = ctx['ScannerBackupBuffer']
    guard = m.byte(backup + len(cells))
    m.poke('ScannerContactsDrawn', 0)
    m.call('SaveScannerBackground', stack=ctx.upper_stack)
    saved = [screen[a - start] for a in cells]
    assert m.memory[start:end] == screen and m.memory[backup:backup + len(cells)] == saved
    assert m.byte(backup + len(cells)) == guard

    live = [b ^ 0xFF for b in screen]
    expected = live.copy()
    for y in range(136, 144):
        for x in range(80, 168, 8):
            expected[cr.screen_offset(x, y)] = 0
    for i, address in enumerate(cells):
        expected[address - start] = saved[i]
    for y in range(144, 160):
        i = cr.screen_offset(168, y)
        expected[i] = (screen[i] & 0xE0) | (live[i] & 0x1F)
    m.memory[start:end] = live
    m.call('RestoreScannerBackground', stack=ctx.upper_stack)
    assert m.memory[start:end] == live, 'inactive restore'
    m.poke('ScannerContactsDrawn', 1)
    m.call('RestoreScannerBackground', stack=ctx.upper_stack)
    assert m.byte('ScannerContactsDrawn') == 0 and m.memory[start:end] == expected
    assert m.memory[backup:backup + len(cells)] == saved and m.byte(backup + len(cells)) == guard


def contact_sequence(ctx, chart):
    m = ctx.machine()

    def call(name):
        m.call(name, stack=ctx.upper_stack)

    def dot(x):
        m.poke('CompassDotX', x)
        m.poke('CompassDotY', 0)
        m.poke('CompassTargetBehind', int(chart))
        call('DrawCompass')

    call('RestoreCockpitBitmap')
    m.poke('CurrentScreenId', 0)
    if chart:
        dot(0x87)
        call('SaveCleanCockpit')        # save a left-pointing dot on leaving the cockpit
        call('RestoreCockpitBitmap')    # its scanner backup now contains that old dot
        dot(0)                          # target has since moved to the centre
    else:
        dot(0x87)                       # clean backup, live dot on the left
    ready = compass(m.memory)
    state = ctx['InitialRuntimeState']
    m.clear(state, ctx['InstanceSlotCount'] * ctx['InstanceSize'])
    slot = state + ctx['InstanceSize']
    m.poke(slot + ctx['InstanceEnergy'], 1)
    m.poke('LastActiveObjectEnergy', 1)
    call('DrawScannerContacts')
    assert compass(m.memory) == ready and m.byte('ScannerContactsDrawn') == 1
    call('DrawScannerContacts')         # prior contact now triggers the restore
    changed = sum((a ^ b).bit_count() for a, b in zip(ready, compass(m.memory)))
    call('DrawCompass')
    assert compass(m.memory) == ready
    m.poke('LastActiveObjectEnergy', 0)
    call('DrawScannerContacts')         # last contact disappears
    assert m.byte('ScannerContactsDrawn') == 0
    assert sum((a ^ b).bit_count() for a, b in zip(ready, compass(m.memory))) == changed
    return changed


def flight(fixed, original, start, limit, tap):
    import benchmark_rotation_drift as bench
    from skoolkit.simutils import PC

    s = fixed.symbols
    assert parse(tap.read_bytes())[5].payload == fixed.image
    bench.OUT, bench.RELEASE_TAP = OUT, tap
    memory, registers = bench.boot(s)
    # Put the station in scanner range on the left. The game computes both
    # displays from its coordinates with the normal movement and interrupts.
    for axis, value in enumerate((-0x1400, 0, -0x800)):
        cr.put24(memory, s['InitialRuntimeState'] + 3 * axis, value)
    results = []
    for ctx in (original, fixed):
        sim = bench.clone(memory, registers)
        sim.memory[start:limit] = bytes(ctx.pristine[start:limit])
        bench.main_loop_frame(sim, s)
        assert sim.memory[s['CompassDotX']] >= 0x84 and sim.memory[s['ScannerContactsDrawn']] == 1

        def until(label):
            with contextlib.redirect_stdout(io.StringIO()):
                sim.tracer.run(sim.registers[PC], s[label], 0, bench.CLOCK_HZ, True,
                               None, None, None, None, '$', '02X', '04X')
            assert sim.registers[PC] == s[label], label

        until('DrawScannerContacts')
        before = compass(sim.memory)
        until('DrawGauges')             # before the end-of-frame compass repaint
        results.append(sum((a ^ b).bit_count() for a, b in zip(before, compass(sim.memory))))
    assert results[0] > 0 and results[1] == 0, results
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / 'verification.json'
    report.unlink(missing_ok=True)
    s = symbol_map(ROOT / 'build/game.map')
    assert s.get('COMPASS_FLICKER_FIX') == 1, 'Build compassflickerfix=yes first'
    image = (ROOT / 'build/game.bin').read_bytes()
    start, limit = s['CompassScannerCopyStart'], s['CompassScannerCopyLimit']
    part = slice(start - s['GameImage'], limit - s['GameImage'])
    baseline = bytearray(image)
    baseline[part] = reference()[1][5].payload[part]
    assert baseline[part] == bytes.fromhex('ED A0') * 13 and baseline != image
    original, fixed = (cr.ImageContext(s, data) for data in (baseline, image))
    check_copy(fixed)
    results = dict(machine='ZX Spectrum 48K', image_sha256=sha(image))
    for chart, name in ((False, 'erased_live_dot'), (True, 'restored_old_dot')):
        counts = [contact_sequence(ctx, chart) for ctx in (original, fixed)]
        assert counts[0] > 0 and counts[1] == 0, (name, counts)
        results[name] = counts
    if args.emulator:
        meta = json.loads((ROOT / 'build/verification.json').read_text())
        results['flight'] = flight(fixed, original, start, limit, release_tap(meta['tapfile']))
    report.write_text(json.dumps(results, indent=2) + '\n', encoding='ascii')
    print('PASS:', results)


if __name__ == '__main__':
    main()
