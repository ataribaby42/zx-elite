"""Reproduce the deterministic gameplay traces used by RUNTIME-MAP.md."""
import argparse
import subprocess
import sys
from pathlib import Path

from tape import ROOT

CHECKER = ROOT / 'tools' / 'emulator_check.py'

def key(start, duration, name):
    return ['--key', f'{start}:{duration}:{name}']

def poke(start, address, data):
    return ['--poke', f'{start}:{address}:{data}']

def started(seconds):
    return ['--seconds', str(seconds), *key(3, 0.5, 'N'), *key(5, 0.5, 'SPACE')]

def trade():
    args = [*started(54), *key(8, 0.4, 'K'), *key(10, 0.25, '2'),
            *key(11, 0.25, '5'), *key(12, 0.25, 'ENTER')]
    for second in range(13, 29):
        args += key(second, 0.22, 'ENTER')
    args += [*key(30, 0.25, '3'), *key(31, 0.25, '2'), *key(32, 0.25, 'ENTER')]
    for second in range(33, 49):
        args += key(second, 0.22, 'ENTER')
    return [*args, *key(51, 0.3, 'ENTER')]

def select_planet_and_jump(name):
    args = [*started(50), *key(8, 0.3, 'I'), *key(10, 0.3, 'R')]
    second = 11.0
    for character in name.upper():
        args += key(f'{second:.2f}', 0.18, character)
        second += 0.45
    return [*args, *key(f'{second:.2f}', 0.25, 'ENTER'), *key(16, 0.3, 'L'),
            *key(18, 0.4, '1'), *key(24, 0.3, 'H'), *key(46, 0.4, 'L')]

RICH_MONEY = [
    *poke(7, '0xA828', '98008096'), *poke(7, '0xA922', '98008096'),
]
RICH_TECH10 = [
    *RICH_MONEY,
    *poke(7, '0xA85E', '0A'), *poke(7, '0xA958', '0A'),
]

SCENARIOS = {
    'docked-baseline': started(8),
    'docked-market': [*started(10), *key(8, 0.5, 'K')],
    'docked-inventory': [*started(10), *key(8, 0.5, 'ENTER')],
    'docked-equipment': [*started(10), *key(8, 0.5, '4')],
    'docked-system-data': [*started(10), *key(8, 0.5, 'P')],
    'docked-local-chart': [*started(10), *key(8, 0.5, 'O')],
    'docked-galactic-chart': [*started(10), *key(8, 0.5, 'I')],
    'trade-complete': trade(),
    'buy-large-cargo': [*started(17), *RICH_MONEY, *key(8, 0.4, '4'),
                        *key(10, 0.25, '3'), *key(11, 0.3, 'ENTER'), *key(15, 0.4, 'L')],
    'buy-fuel-scoops': [*started(17), *RICH_MONEY, *key(8, 0.4, '4'),
                        *key(10, 0.25, '7'), *key(11, 0.3, 'ENTER'), *key(15, 0.4, 'L')],
    'equip-tech10': [*started(11), *RICH_TECH10, *key(8, 0.4, '4')],
    'buy-galactic-hyperdrive': [*started(18), *RICH_TECH10, *key(8, 0.4, '4'),
                                *key(10, 0.2, '1'), *key(10.5, 0.2, '2'),
                                *key(11, 0.3, 'ENTER'), *key(15, 0.4, 'L')],
    'inflight-screens': [*started(38), *key(8, 0.4, '1'), *key(13, 0.3, '2'),
                         *key(15, 0.3, '3'), *key(17, 0.3, '4'), *key(19, 0.3, 'I'),
                         *key(21, 0.3, 'O'), *key(23, 0.3, 'P'), *key(25, 0.3, 'K'),
                         *key(27, 0.3, 'L'), *key(29, 0.3, 'ENTER'), *key(31, 0.3, '1'),
                         *key(33, 0.4, 'SPACE'), *key(35, 0.4, 'SS')],
    'inflight-back-view': [*started(20), *key(8, 0.5, '1'), *key(14, 0.8, '2')],
    'hyperspace-diso': select_planet_and_jump('Diso'),
    'hyperspace-reorte': select_planet_and_jump('Reorte'),
    'hyperspace-zaonce': select_planet_and_jump('Zaonce'),
    'galactic-hyperspace-overlap': [
        *started(48), *RICH_TECH10, *key(8, 0.4, '4'), *key(10, 0.2, '1'),
        *key(10.5, 0.2, '2'), *key(11, 0.3, 'ENTER'), *key(15, 0.4, 'L'),
        *key(17, 0.4, '1'), *key(23, 1.0, 'G'), *key(23.25, 0.4, 'H'),
        *key(43, 0.4, 'L'),
    ],
}

ACCESS_NAMES = {
    'docked-baseline': 'access-docked-baseline',
    'docked-market': 'access-docked-market',
    'docked-equipment': 'access-docked-equipment',
    'trade-complete': 'access-trade-complete',
    'inflight-screens': 'access-inflight-screens',
    'hyperspace-zaonce': 'access-hyperspace-zaonce',
    'galactic-hyperspace-overlap': 'access-galactic-hyperspace',
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', nargs='*', choices=sorted(SCENARIOS))
    parser.add_argument('--accesses', action='store_true',
                        help='run the seven representative memory-access traces')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.list:
        print('\n'.join(SCENARIOS))
        return
    selected = args.scenario or list(ACCESS_NAMES if args.accesses else SCENARIOS)
    for name in selected:
        if args.accesses and name not in ACCESS_NAMES:
            raise SystemExit(f'No memory-access profile is defined for {name}')
        output_name = ACCESS_NAMES[name] if args.accesses else name
        command = [sys.executable, str(CHECKER), *SCENARIOS[name],
                   '--name', output_name, '--no-screenshots']
        if args.accesses:
            command.append('--memory-accesses')
        print(f'\n=== {output_name} ===', flush=True)
        subprocess.run(command, cwd=ROOT, check=True)

if __name__ == '__main__':
    main()
