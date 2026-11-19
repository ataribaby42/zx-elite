# Competition number removal

`competitionremove=yes` removes calculation and display of the competition
security number after a successful commander save. Its default is `no`.
It changes neither motion nor the 104-byte save format. `COMMANDER SAVED`,
the 102-byte restart snapshot, name entry, load handling and BREAK remain.
The unused `SECURITY NUMBER:` message entry stays to preserve text numbering.

`rotationdriftfix=yes` needs the reclaimed code space and therefore forces
`competitionremove=yes`, including when the command explicitly requests `no`.
The builder prints that resolution. `build/verification.json` records the
effective `competitionremove` and the original `competitionremove_requested`.
`dockingrotation=yes` enables `rotationdriftfix=yes`, so it also enables
competition removal through that dependency.

| Requested competitionremove | Requested rotationdriftfix | Effective behaviour |
|---|---|---|
| `no` | `no` | Original save number and motion |
| `yes` | `no` | Remove the number; original motion |
| `no` | `yes` | Enable removal automatically; repair rotation drift |
| `yes` | `yes` | Remove the number; repair rotation drift |

```bat
make.bat competitionremove=yes verify=no
python tools\check_competition_remove.py
verify.bat verify=no

make.bat rotationdriftfix=yes verify=no
python tools\check_competition_remove.py
python tools\check_rotation_drift_fix.py
```

Only the original block-5 regions `$D386..$D3E1` (92 bytes) and
`$D3F0..$D3FE` (15 bytes) are removed. A two-byte `JR` keeps the successful
save connected to `CopyCommanderToTemplate`, leaving 90 + 15 = **105 bytes**
of zero-filled space when rotation repair is off. When rotation repair is on,
its helpers occupy these regions. The later [rotation optimization](ROTATION-DRIFT-FIX.md)
also stays within these boundaries. No extra memory or shorter TAP is implied.

The regions belong to `CompetitionSecurityStart/Limit` and
`CompetitionParityStart/Limit` in `src/options.asm`. The source generator
guards them with `COMPETITION_REMOVE`; their macros in
`src/competition-remove.asm` select padding or rotation helpers. Direct
assembly defaults the dependency to the rotation setting and rejects an
explicit conflicting assembler configuration. Normal Python/BAT builds
resolve the dependency automatically before assembly.

`tools/check_build_options.py` checks all requested value pairs, effective
settings, assembler flags, strict rejection and the exact shared-region
payload. Only the declared competition/rotation/docking dependencies may
overlap; every independent option's regions must remain disjoint. Full Cartesian
coverage is not necessary for this dependency; the pairwise suite plus
targeted save and byte-identity checks cover its four states.

`tools/check_competition_remove.py` runs in **ZX Spectrum 48K** RAM with
`assets/zxspectrum48k.rom`. It executes save success and BREAK, stubbing
keyboard, display and ROM tape transport, and compares all tape bytes and
the restart snapshot with the original. It also checks the bypass, padding
and unchanged motion for standalone removal. Results are regenerated at
`build/competition-remove-check/verification.json`. It does not simulate
cassette audio. The same save checks are used by the rotation test.

Validation of the split passed the default byte-identical build and verify,
standalone save checks, combined rotation/save checks, and 98 option builds
covering all 608 requested value pairs. Direct assembler probes verified the
implied default and rejection of an explicit conflicting pair. No new ROM-load
flight run was needed for that split: its rotation-enabled TAP was byte-identical
to the then-current implementation (historical SHA256
`5e8b7ef8db00cd7be32a81448c2437d50f6dd23a054cf06ffd40bd8c875767db`).
Standalone removal with default Krait has SHA256
`1440a146881174a528e2d0250c64072c1563a3aa4702a79468fd7f793aa7cb9e`.
Builds used z88dk `23854-4d530b6eb7-20251002` and retained all six TAP blocks,
payload lengths 130/6912/40801 and total length 47918, with structural checks
and checksums enabled. The default reference hash is unchanged.
