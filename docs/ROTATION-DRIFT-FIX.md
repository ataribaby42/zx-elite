# Position rotation fix

`rotationdriftfix=no` is the default. With it, `competitionremove=no` and
`dockingrotation=no`,
the reference bytes and post-save security number are preserved.
`rotationdriftfix=yes` automatically enables `competitionremove=yes` (even if
`competitionremove=no` was requested) and reuses the reclaimed space for
position arithmetic. [Competition removal](COMPETITION-REMOVE.md) can also be
selected alone without changing motion. Build it
with `make.bat rotationdriftfix=yes verify=no`.
The independent [docking roll check](DOCKING-ROTATION.md) also requires
competition removal, but does not enable this rotation fix.

## Cause and scope

The reference is the structurally validated game payload in zero-based TAP
block 5 of `assets/Elite - 128k.tap`, loaded at `$6048..$FFA8`. All execution
checks use **ZX Spectrum 48K** with `assets/zxspectrum48k.rom`.

`ApplyPlayerMotion` originally applies two shears per axis, using each updated
coordinate immediately. For roll, `x -= y*a; y += x*a`, with `a = roll/128`.
Changing the sign of `a` does not invert that sequence. Repeated reversals can
increase the radial distance substantially. This is a coordinate defect, not
a side-view projection defect. Pitch has the same problem. Furthermore, the
original quarter-square multiplication is inexact when the input sum is odd;
its high-byte variant also ignores a low-byte borrow.

The fix changes the shared position routine for sun, planet, ships, missiles
and station. Keeping the station and planet on the same transformation is
necessary for consistent relative geometry. It does not change the separate
orientation-vector routines, object AI, view projection, stardust, player
controls or forward translation. `stationslotfix` remains a separate option.

## Arithmetic

Each plane now uses three shears, with the full updated coordinates:

```text
u -= v*a/2
v += u*a
u -= v*a/2
```

Pitch uses `(u,v)=(z,y)` and `a=pitch/256`; roll then uses `(x,y)` and
`a=roll/128`. Negating the coefficient gives the inverse sequence. All products
are exact before integer truncation. Half-products are divided by 512 after
multiplication, preserving odd and minimum pitch rates. Coordinates stay in
their original 24-bit sign-magnitude representation. Zero rotation skips the
plane. `TranslatePlayerPosition` then executes the original speed step,
including its zero-crossing and overflow behaviour and returned HL.

This is still a small-angle approximation, not an exact sine/cosine rotation.
For constant `a` in real arithmetic it preserves
`u*u + (1-a*a/4)*v*v`; it has a small bounded ellipticity. Integer rounding and
changing rates also remain. The regression limits radius error to 0.5% in
the tested long runs; this is not a guarantee for unlimited arbitrary input.
One plane followed by the same opposite rate restores the tested integer
coordinates exactly. Simultaneous opposite roll and pitch are not claimed to
invert a whole update: rotations about different axes do not commute.

The optimized exact multiply reuses the existing square tables. For even
`B+C`, `MultiplyUnsigned` already returns `B*C`; for odd sums it returns
`B*C-min(B,C)`, so the helper adds back that missing term. Zero multiplicands
and coefficients 0, 1 and 2 use direct short paths. No new table is allocated,
and the shared graphics multipliers remain unchanged.

The half-product wrapper tail-calls `AddScaledCoordinate`. Product packing
clears the half-scale flag before signed addition. The dispatcher explicitly
clears carry before `DoubleSignMagnitude`: its input carry must not come from
the pitch plane. Otherwise an overflow of the low coordinate word can turn
zero roll into coefficient 1, or increase a nonzero roll coefficient by 1.
For example, pitch 1 and roll 0 at `(10000,-65536,65300)` must keep X=10000;
before this correction X became 10254 in one update.
The packing hook also omits saving BC: its caller immediately replaces BC
with the stacked product sign. The carry correction fits in the same bytes:
after loading DE=InstanceY, two one-byte loads copy its zero high byte into
HL=InstanceX, replacing the three-byte immediate load. Assertions guard those
field-offset assumptions. It adds two T-states to the dispatcher, no storage
or stack use. Six shears still replace four when both
axes turn; frame timing is not identical to the unmodified game.

## Speed

The optimization measurements below predate the carry correction described
above; the retained evidence identifies those historical binaries.
The optimized routine took **9,270.4 T-states** on average for simultaneous
maximum roll and pitch in the five-vector fixture, down from **11,626.2**
(**20.3% less CPU time**). That optimization kept straight-flight timing
unchanged; the subsequent carry correction adds the two dispatcher T-states.

Complete-frame measurements with both controls at 15:

| Scene | Fix off, FPS | Previous fix, FPS | Optimized fix, FPS |
|---|---:|---:|---:|
| Front after launch | 8.057 | 7.685 | 7.810 |
| Rear, station visible | 7.369 | 7.044 | 7.117 |
| Front, four ships | 6.205 | 5.761 | 5.963 |

The measured FPS penalty relative to the unmodified game falls from
4.4-7.2% to 3.1-3.9%. This is a 1.0-3.5% FPS improvement over the previous
fix, depending on the scene; the routine's 20.3% saving applies only to
position arithmetic, not to a whole frame.

`tools/benchmark_rotation_drift.py` ROM-loads the current release and times
32 complete `MainLoop` iterations for each of six control settings in three
scenes. Each variant starts each iteration with identical RAM, registers and
interrupt phase. The unmodified trajectory supplies the next input state so
its drift cannot bias the comparison. Timing uses a nominal 3.5 MHz ZX
Spectrum 48K with actual interrupts, without ULA contention modelling; these
are emulator estimates, not measurements on physical hardware.

Run `python tools/benchmark_rotation_drift.py` after a rotation-enabled build
with `dockingrotation=no`, so the comparison isolates position arithmetic.
The optional `--previous-image PATH` accepts a saved earlier `build/game.bin`
whose bytes outside the seven patch regions match. It additionally compares
4,096 coordinate-byte/returned-HL/IX/IY cases across every legal signed
roll/pitch pair and observes stack depth on representative paths. The report
is `build/rotation-speed/verification.json`. The optimization's before/after
report is retained in [evidence](evidence/rotation-drift-optimization.json);
its previous image was saved before editing and is identified by its hash.
The equality comparison is intended for optimizations that preserve behaviour;
an image with the pitch-carry defect is expected to fail against the corrected
implementation.

## Memory and saving

Seven fixed regions (including the two owned by `competitionremove`) are guarded by Start/Limit assertions in `src/options.asm`
and declared in both the source generator and build-option overlap check.
The rotation payload takes precedence over standalone zero padding. The
docking check, when selected together with rotation repair, uses only the three padding gaps:

| Original range (inclusive) | Bytes | Use with the fix |
|---|---:|---|
| `$D386..$D3E1` | 92 | Save bypass, plane rotation, half-product wrapper, product packing and corrected table multiplication |
| `$D3F0..$D3FE` | 15 | Exact product high-byte wrapper; remaining padding |
| `$DED1..$DF0A` | 58 | Rotation dispatcher and direct small-product paths |
| `$DF64..$DF66` | 3 | High-coordinate-byte multiply call |
| `$DF6B..$DF6D` | 3 | Middle-coordinate-byte multiply call |
| `$DF78..$DF7A` | 3 | Low-coordinate-byte multiply call |
| `$DF80..$DF83` | 4 | Product packing/optional halving hook |

One scratch byte, `RotationDriftHalfScale`, is inside the reclaimed security
code. It is zero outside the half-product call. No extra RAM, persistent
commander field, ROM change or image expansion is needed. The interrupt
handler does not call coordinate arithmetic. All helper calls use labels.
The three larger regions use 87/92, 7/15 and 52/58 bytes respectively,
leaving 19 bytes of padding in three separate gaps. The optimization uses
16 bytes of existing padding, keeps the same one-byte scratch state and
does not increase the reserved stack or image size.
Observed peak stack use in the before/after routine fixture is 28 bytes in
both versions, including the caller's return address and excluding interrupts.
These 19 free bytes apply with `dockingrotation=no`. With `dockingrotation=yes`,
its 18-byte helper leaves only the single byte at `$D3FE`.

Saving still prompts for the name, copies the nine sun-position bytes,
writes the same 104-byte tape record, displays `COMMANDER SAVED`, and copies
102 persistent bytes into the restart snapshot. BREAK and load handling are
unchanged. The obsolete number is neither calculated nor displayed when the
option is on. Its unused text-table entry remains to preserve message numbers
and the text layout. The nine stored sun bytes are not a security code.

## Reproduction and evidence

```bat
python tools\bootstrap_sources.py --force
make.bat
verify.bat
python tools\check_core_routines.py
python tools\check_routines.py --only maths --only commander --only station
python tools\check_build_options.py
make.bat rotationdriftfix=yes verify=no
python tools\check_rotation_drift_fix.py --emulator
make.bat ship=adder rotationdriftfix=yes verify=no
python tools\check_rotation_drift_fix.py --emulator
python tools\check_variant_relocation.py
verify.bat verify=no
```

`build/rotation-drift-fix-check/verification.json` records 32,768 exact byte
products (including preservation of B/C), 1,710 signed coordinate cases,
12,288 complete rotation cases against an independent integer model, 488
inverse-plane cases, unchanged translation edge cases, both body callers in
four view selections, and actual
save control flow on success and BREAK. The save test stubs keyboard, display
and ROM transport; it compares all 104 bytes handed to ROM and the restart
snapshot. It does not simulate cassette audio saving.

The original control-ramp fixture grows the roll-plane radius to **4.9750x**
after 1,280 updates. With the fix, after **12,800** updates it is **0.999216x**.
Pitch, combined axes and continuous roll also stay within 0.5% of the initial
3D radius in those long tests.

The optional emulator check ROM-loads the release, launches and stops at
`MainLoop` before placing controlled sun/planet vectors and selecting the right
view. Both versions execute exactly 1,280 complete game updates with the same
alternating roll ramp. Interrupts remain active; copied player controls are
locked so elapsed time cannot change the ramp. Every update has a bounded
timeout. A private comparison image restores only the seven original regions
and, when enabled, the docking hook that calls those regions. For the corrected Krait build
with docking, traffic control and both station fixes, roll-plane radius ratios
were:

| Body | Original | Fixed |
|---|---:|---:|
| Planet | 3.95864 | 0.99966 |
| Sun | 3.35916 | 1.00053 |

The former timed negative control could fail with other options because its
final planet drift depended on the number and phase of updates. The fixed
update count makes that comparison reproducible without weakening the 0.5%
limit on the corrected variant. An additional real game update checks the
pitch-only carry regression for both bodies, including the original translation.
The complete rotation cases include all signed control bytes in the legal
0..15 range (both zero encodings), both input carries, word-boundary fixtures
and large coordinates. They replace the old wrapper comparison that wrongly
treated consumption of pitch carry as required behaviour.
Reports, memory dumps and final screenshots are regenerated under
`build/rotation-drift-fix-check/`.

The optimization was checked with the default exact build and verification,
targeted arithmetic/save checks for Krait and Adder, the Krait 48K ROM-load
regression, the before/after comparison and benchmark above, and the eight
existing relocation fixtures. Patch boundaries and build machinery did not
change, so the full option matrix was not repeated for this optimization.

Before extracting the standalone removal option, both Krait and Adder passed
the routine and 48K ROM-load checks; their measured radius ratios were identical.
The rotation-enabled TAP was byte-identical across that split. The earlier
option matrix passed 95 builds, including
18 individual non-default option values, 20 combinations covering all 540
value pairs, byte-area disjointness and strict-verification rejection. The current
`build/build-options-check/verification.json` additionally records the explicit
competition-removal dependency and checks its shared-area precedence.

Builds used z88dk `Z80 Macro Assembler 23854-4d530b6eb7-20251002`. The default
TAP retained SHA256
`d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6`.
With only `rotationdriftfix=yes`, the corrected Krait TAP has SHA256
`0ff9edae4718445cc65a52250fd25f405ac69e1fffe07754d22a896e1b60c703`.
All builds keep six TAP blocks (three header/data pairs), payloads 130, 6912
and 40801 bytes, total size 47918 bytes, and image end `$FFA9` exclusive.
Modified builds disable only binary identity; structure, checksums, metadata
and assembler bounds remain checked.

### Station-slot combination

The combination with `stationslotfix=yes` also exercises 3,036 switch-on
geometries, 600 unchanged paths and all 2,048 hyperspace arrivals with turns.
The new rotations produce different directions at switch-on. One direction,
`[3543,-2007,98219]`, gave a full 16-bit nose `[1023,-511,32754]` only 0.391
degrees off the planet. The high-byte nose `[3,-1,127]` used by the historical
check is 1.012 degrees off. This exceeded that fixture's historical 1-degree
threshold because of high-byte truncation, not a reversed or drifting slot.
For this combination the arrival regression checks full-axis error below
1 degree and the additional high-byte truncation separately against
`asin(sqrt(3)/127)` (less than 0.782 degrees). The original option alone keeps
its original 1-degree high-byte limit. No station alignment code was changed.
