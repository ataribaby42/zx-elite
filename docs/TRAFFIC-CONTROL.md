# Station traffic control

`trafficcontrol=no` is the default and preserves the reference game.
`trafficcontrol=yes` suppresses a calm station's random trader launch when
both conditions hold:

- The cockpit S indicator is lit (`StationPresent = 1`).
- The Chebyshev distance to the **centre** of the station is **less than
  1024 units (`$0400`)**: `max(abs(x), abs(y), abs(z)) < 1024`.

The boundary is a cube in the player's coordinate frame, not a sphere.
For example, `(1023, 1023, 1023)` is inside; `(0, 0, 1024)` is outside.
All cockpit views use the same coordinates and decision. Existing ships
are unaffected. Launches resume when either condition ceases to hold.

Police Vipers, the hostile station's special-mode Thargoids, rock-hermit
fighters and Thargons bypass this check. The original four-counted-ship
limit remains. `stationrandomlaunchfix=yes` still independently enables
both Cobra and Python traders; without it, the original selector's Python
bias remains. This option has no dependencies and works together with
`rotationdriftfix` and `dockingrotation`.

```bat
make.bat trafficcontrol=yes verify=no
python tools/check_traffic_control.py --emulator
verify.bat verify=no
```

## Implementation and storage

`src/traffic-control.asm` changes four bounded areas. Their Start/Limit
constants are in `src/options.asm`, with matching source-generator and
build-option checks.

| Original range | Size | Use with the option |
|---|---:|---|
| `$F871..$F875` | 5 B | Original random gate, then branch to distance check |
| `$F882..$F8A1` | 32 B | 17-byte equivalent proximity check for its existing callers, plus 15-byte traffic gate |
| `$7818..$781E` | 7 B | X/Y middle-byte combination; formerly an unreferenced cloak-colour test |
| `$91CC..$91D1` | 6 B | Z middle byte and threshold comparison; formerly two unreferenced vectors |

Only **13 previously unused bytes** are consumed. The TAP and game image
sizes are unchanged; no variable or extra RAM allocation is needed. The
two short helpers use one return address at a time on the existing stack,
and return before ship allocation begins. The rotation/docking padding is
unchanged.

The original `CheckShipProximity` callers use `DE=$0200` and `DE=$0A00`,
with E zero in both cases. Comparing each 16-bit magnitude against these
limits therefore only requires its middle byte. The replacement preserves
carry, D and the original additional `$0200` allowance on Z. Its callers
do not consume A or HL. It is **not a general replacement for calls with
E nonzero**; adding such a caller requires extending the implementation
and regression check.

The new station check uses a separate, symmetric threshold on all three
axes. It does not reuse the asymmetric AI avoidance box. For a power-of-two
threshold, OR of the three middle bytes followed by `CP 4` is exactly
equivalent to the maximum comparison. `StationPresent` is a verified
boolean: subtracting one yields zero for S on, or `$FF` for S off, which
forces the outside result.

The omission of the sign/high bytes relies on the **active-station**
invariant, not on truncating arbitrary 24-bit positions. The initial
station is at `(0,0,$0300)` with speed zero. `UpdateStationDormancy` checks
all three upper magnitude bytes before activation. `MoveObject` removes
an object whose upper magnitude becomes nonzero before the next AI pass.
The station's own movement cannot then extend the range: its speed and
blueprint maximum speed are zero. Dormant stations can have larger
coordinates, but do not run station traffic AI. Signs and negative zero
are immaterial to this magnitude test. Reference evidence is in TAP game
block 5, particularly the original `$779D..$77D3`, `$DB71..$DB8B` and
`$DCE0..$DD08` paths; the checker also executes the range guards.

## Cost and validation

The ordinary random rejection (254 of 256 results) has **zero added
instructions or T-states**. Only a permitted trader attempt reaches the
new comparison, normally on one station AI pass in four object updates.
A blocked attempt adds 151 T-states to the gate itself (about 43 microseconds
at nominal 3.5 MHz), while avoiding the much larger allocation and subsequent
updates/drawing of the new ship. RNG calls and state outside suppression
are unchanged; a blocked attempt naturally skips the trader selector's RNG.

The shortened existing AI proximity test is faster: 68 to 34 T-states
for an X rejection, 130 to 62 for a Y rejection, and 199 to 97 when all
three axes are evaluated. These are instruction timings, not a measured
whole-game FPS or ULA-contention model.

`tools/check_traffic_control.py` writes
`build/traffic-control-check/{krait,adder}.json`. It compares with a copy of
the current image in which only these four areas have been restored from
the structurally validated reference game block. Checks cover:

- 25,433 boundary/sign/S/random-gate cases, including cube corners and negative zero.
- All 65,536 RNG seeds for near, boundary, S-off, police, special-mode and full-count gates.
- All 65,536 magnitudes on every axis for both existing AI proximity limits,
  plus 2,048 decisions through the actual steering caller.
- Real child allocation with free/full slots, unchanged RNG outside suppression,
  and the activation/removal range guards.
- With `--emulator`, actual 48K ROM loading and launch, followed by full object
  updates and real allocations at distances 1000 and 1024, for calm and hostile stations.

The option matrix additionally checks the four regions are disjoint from
other features and that combined images contain exactly the selected patches.

Validated with the standalone Krait option and with Adder, font 48 and all
optional features enabled, including real Cobra/Python and Viper allocations.
The pairwise option check passed 120 builds covering all 756 value pairs.
Default AI regressions and the eight existing relocation fixtures also passed.
The default build still matches the reference TAP byte for byte (SHA-256
`d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6`).
