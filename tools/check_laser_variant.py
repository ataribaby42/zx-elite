"""Execute the built laser and line renderer in a ZX Spectrum 48K simulator.

Compare the endpoint randomisation with the original routine for 256 RNG
states, count real line calls, check the stack and inspect rendered pixels.
Only test RAM/registers are prepared; game instructions are not patched.
"""
import json
import sys
from tape import ROOT, ANALYSIS_DEPS, RELEASE_TAP, parse, reference, sha
from build import symbol_map

sys.path.insert(0, str(ANALYSIS_DEPS))
from skoolkit.simulator import Simulator
from skoolkit.simutils import C, D, E, H, L, PC, SP

# Immutable reference-image locations, separate from the current symbol map.
REFERENCE_LAYOUT = dict(GameImage=0x6048, GameImageEnd=0xFFA9, ViewBitmapBuffer=0xC000,
                        L_ED35=0xED35, DrawLaser=0xECD4, LaserPatchSite=0xECF2, DrawLine=0xEE10)


def main():
    out = ROOT/'build/laser-variant-check'
    out.mkdir(parents=True, exist_ok=True)
    report_path = out/'verification.json'
    report_path.unlink(missing_ok=True)
    symbols = symbol_map(ROOT/'build/game.map')
    image = (ROOT/'build/game.bin').read_bytes()
    tape = RELEASE_TAP.read_bytes()
    assert parse(tape)[5].payload == image
    original = reference()[1][5].payload
    rom = (ROOT/'assets/zxspectrum48k.rom').read_bytes()
    assert len(rom) == 16384
    single = bool(symbols['LASER_SINGLE'])
    mode = 'single' if single else 'original'

    def draw(payload, seed, layout):
        memory = list(rom)+[0]*(65536-len(rom))
        memory[layout['GameImage']:layout['GameImageEnd']] = payload
        # The initial font/startup storage is a graphics buffer during flight.
        memory[layout['ViewBitmapBuffer']:layout['ViewBitmapBuffer']+4096] = [0]*4096
        rng = layout['L_ED35']
        memory[rng:rng+2] = [seed, seed ^ 0xA5]
        memory[0xFFE0:0xFFE2] = [1, 0]  # return sentinel, emulator only
        sim = Simulator(memory, {'PC': layout['DrawLaser'], 'SP': 0xFFE0, 'F': seed & 1})
        calls = []
        endpoint = None
        for _ in range(50000):
            pc = sim.registers[PC]
            if pc == 1:
                break
            if pc == layout['LaserPatchSite']:
                endpoint = tuple(sim.registers[r] for r in (D, E, C))
            if pc == layout['DrawLine']:
                calls.append(tuple(sim.registers[r] for r in (H, L, D, E, C)))
            sim.run()
        else:
            raise AssertionError(f'Laser failed to return: ${sim.registers[PC]:04X}')
        assert sim.registers[SP] == 0xFFE2, 'Unbalanced laser/line stack'
        buffer = bytes(memory[layout['ViewBitmapBuffer']:layout['ViewBitmapBuffer']+4096])
        return endpoint, calls, buffer

    endpoints = set()
    renderings = set()
    for seed in range(256):
        expected, original_calls, original_pixels = draw(original, seed, REFERENCE_LAYOUT)
        endpoint, calls, pixels = draw(image, seed, symbols)
        assert endpoint == expected, 'Original random endpoint/quadrant changed'
        assert len(original_calls) == 4
        assert len(calls) == (1 if single else 4)
        assert any(pixels), 'Laser did not draw any pixels'
        if single:
            d, e, c = expected
            assert calls == [(0, 63, d, e, c | 3)]
            lit = set()
            for y in range(128):
                for x in range(256):
                    offset = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | (x >> 3)
                    if pixels[offset] & (128 >> (x & 7)):
                        lit.add((x, y))
            assert lit and all(125 <= x <= 129 and 61 <= y <= 126 for x, y in lit), 'Beam outside centre strip'
            # The existing rasterizer omits an endpoint pixel; do not require
            # the mathematical endpoint itself to be lit.
            assert any(x == 127 and y >= 125 for x, y in lit), 'Beam misses bottom centre'
        else:
            assert calls == original_calls and pixels == original_pixels
        endpoints.add(endpoint)
        renderings.add(sha(pixels))
    assert len(endpoints) > 1 and len(renderings) > 1, 'Endpoint wiggle was lost'
    report = dict(passed=True, machine='ZX Spectrum 48K', laser=mode,
                  ship='adder' if symbols['SHIP_ADDER'] else 'krait',
                  tape_sha256=sha(tape), rng_states=256,
                  distinct_endpoints=len(endpoints), distinct_renderings=len(renderings),
                  line_calls_per_shot=1 if single else 4, stack_balanced=True,
                  original_endpoint_preserved=True, actual_pixels_checked=True)
    report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f'PASS: ZX Spectrum 48K, laser={mode}; 256 RNG states, real line rendering, endpoint wiggle and balanced stack.')


if __name__ == '__main__':
    main()
