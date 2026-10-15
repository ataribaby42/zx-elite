# Runtime code and state map

This map is generated from deterministic emulator runs of the rebuilt,
byte-identical TAP in **ZX Spectrum 48K** mode with the supplied 48K ROM.
No game instruction was patched. Test-only commander changes are listed
explicitly in the JSON reports and were applied after normal startup.

- Scenarios: **18**
- Distinct executed instruction addresses in `$6048..$FFA8`: **9,169**
- Instruction addresses proved inside former `DEFB` regions: **1,359**
- Persistent runtime seeds used by source reconstruction: **1,359**

An executed program counter proves that its address starts an instruction.
It does not by itself explain the instruction semantically. A changed RAM
byte proves mutable state or self-modifying code, so RAM differences must
not be labelled as data without further evidence.

## Exercised scenarios

| Scenario | Verified action | Distinct game PCs | New vs docked baseline |
|---|---|---:|---:|
| `docked-baseline` | Docked status screen after starting Commander Jameson | 3,196 | 0 |
| `docked-market` | Docked market-prices screen | 3,342 | 146 |
| `docked-inventory` | Docked inventory screen | 3,293 | 97 |
| `docked-equipment` | Docked equipment-purchase screen | 3,383 | 187 |
| `docked-system-data` | Docked system-data screen | 3,563 | 367 |
| `docked-local-chart` | Docked short-range chart | 3,976 | 780 |
| `docked-galactic-chart` | Docked galactic chart | 3,818 | 622 |
| `trade-complete` | Bought 5 t of food, sold 2 t and verified 3 t in inventory | 3,701 | 505 |
| `buy-large-cargo` | Bought a Large Cargo Bay and verified it on the status screen | 3,513 | 317 |
| `buy-fuel-scoops` | Bought Fuel Scoops and verified them on the status screen | 3,515 | 319 |
| `equip-tech10` | Displayed the complete Tech Level 10 equipment list | 3,384 | 188 |
| `buy-galactic-hyperdrive` | Bought a Galactic Hyperdrive and verified it on the status screen | 3,555 | 359 |
| `inflight-screens` | Front/left/right views plus charts, data, market, status and inventory in flight | 7,624 | 4,428 |
| `inflight-back-view` | Rear view in flight | 6,600 | 3,404 |
| `hyperspace-diso` | Normal hyperspace from Lave to Diso | 7,264 | 4,068 |
| `hyperspace-reorte` | Normal hyperspace from Lave to Reorte | 7,266 | 4,070 |
| `hyperspace-zaonce` | Normal hyperspace from Lave to Zaonce | 7,389 | 4,193 |
| `galactic-hyperspace-overlap` | Galactic hyperspace from Lave in galaxy 1 to Inoran in galaxy 2 | 7,182 | 3,986 |

## Largest additional execution windows

These are compact footprints of instruction starts reached in addition
to the docked baseline. They locate active areas; they are not yet routine
boundaries or semantic names.

| Scenario | Four largest additional PC windows |
|---|---|
| `docked-baseline` | - |
| `docked-market` | `$8EE2-$8F3E` (46), `$AF63-$AFB8` (39), `$B049-$B09A` (27), `$D07D-$D0B7` (25) |
| `docked-inventory` | `$8EE2-$8F3E` (46), `$D279-$D2D9` (32), `$B049-$B05F` (10), `$AFB9-$AFC2` (6) |
| `docked-equipment` | `$B53F-$B5C6` (57), `$8F02-$8F3E` (24), `$B0AB-$B0DD` (24), `$8EA1-$8EC1` (19) |
| `docked-system-data` | `$BCFC-$BDE2` (114), `$B93B-$BA2F` (86), `$8EE2-$8F3E` (41), `$BC2B-$BC6B` (34) |
| `docked-local-chart` | `$A9CA-$AB4B` (190), `$8740-$8816` (124), `$D96D-$DA0A` (93), `$8430-$84C4` (71) |
| `docked-galactic-chart` | `$8740-$8816` (119), `$D96D-$DA0A` (93), `$AB4E-$AC09` (84), `$8430-$84C4` (63) |
| `trade-complete` | `$AF39-$AFE2` (79), `$B49F-$B53E` (67), `$B049-$B0E4` (61), `$8EE2-$8F3E` (46) |
| `buy-large-cargo` | `$B53F-$B657` (100), `$8EE2-$8F3E` (42), `$B0AB-$B0DD` (25), `$B333-$B364` (23) |
| `buy-fuel-scoops` | `$B53F-$B657` (102), `$8EE2-$8F3E` (42), `$B0AB-$B0DD` (25), `$B333-$B364` (23) |
| `equip-tech10` | `$B53F-$B5C6` (58), `$8F02-$8F3E` (24), `$B0AB-$B0DD` (24), `$8EA1-$8EC1` (19) |
| `buy-galactic-hyperdrive` | `$B53F-$B657` (103), `$B333-$B3A0` (55), `$8EE2-$8F3E` (42), `$B3F8-$B443` (31) |
| `inflight-screens` | `$A13D-$A36C` (301), `$A9CA-$AC09` (274), `$D96D-$DB08` (178), `$9E74-$9FFE` (171) |
| `inflight-back-view` | `$9E74-$9FFE` (180), `$DB71-$DCA2` (144), `$861F-$86F5` (131), `$DED1-$DFDC` (131) |
| `hyperspace-diso` | `$D96D-$DB08` (178), `$9E74-$9FFE` (171), `$7975-$7ADA` (163), `$DB71-$DCA2` (144) |
| `hyperspace-reorte` | `$D96D-$DB08` (178), `$9E74-$9FFE` (171), `$7975-$7ADA` (163), `$DB71-$DCA2` (144) |
| `hyperspace-zaonce` | `$78C0-$7ADA` (273), `$D96D-$DB08` (178), `$8A3A-$8BAD` (177), `$9E74-$9FFE` (171) |
| `galactic-hyperspace-overlap` | `$85A8-$871A` (197), `$9E74-$9FFE` (171), `$7975-$7ADA` (163), `$DB71-$DCA2` (144) |

## Memory-access evidence

The access runs use SkoolKit's slower Python Z80 simulator with a
list-compatible memory recorder. Opcode fetches explain most reads in code
ranges. Kinds come from `docs/generated/reconstruction.json`; inline
arguments are bytes consumed by the preceding call. A read from an
unclassified range would identify a likely table, text, model or mutable
workspace for further analysis. Writes to code outside the view buffer are
self-modifying code. Code inside the view buffer (`DormantPortLoader`) is
counted separately: it is overwritten when the buffer is reused, and none
of it is executed in the traces.

Each report also lists `memory_read_before_write_map`: addresses read
while they still hold their loaded value, so only there can the tape byte
matter. In the view buffer `$C000..$CFFF` these are, in every access
trace, exactly the 3,032 bytes of the font, cockpit colours and cockpit
bitmap. All other buffer bytes, including `ViewBufferResidueAfterLoader`,
are written before any read.

| Scenario | Image reads | Unclassified reads | Image writes | Unclassified writes | Self-modifying code writes | Code overwritten in view buffer |
|---|---:|---:|---:|---:|---:|---:|
| `access-docked-baseline` | 14,118 | 0 | 4,576 | 0 | 21 | 188 |
| `access-docked-market` | 14,518 | 0 | 4,585 | 0 | 23 | 188 |
| `access-docked-equipment` | 14,568 | 0 | 4,594 | 0 | 23 | 188 |
| `access-trade-complete` | 15,325 | 0 | 4,599 | 0 | 23 | 188 |
| `access-inflight-screens` | 23,739 | 0 | 5,113 | 0 | 99 | 188 |
| `access-hyperspace-zaonce` | 23,011 | 0 | 5,040 | 0 | 92 | 188 |
| `access-galactic-hyperspace` | 22,500 | 0 | 5,003 | 0 | 64 | 188 |

No unclassified region was read: every image byte is classified as code,
inline argument or data, so every recorded access falls in one of them.
A classified range is not necessarily understood; see `src/game.asm`
for the remaining neutral labels and `INFERRED:` hypotheses.

## Reproduction

Build and verify the default reconstruction first. The emulator loads
`release/elite-128k.tap` and compares the loaded image with
`build/game.bin`, so a previously built variant must not remain there.
Then run the scripted text-only scenarios, aggregate and rebuild:

```bat
make.bat
verify.bat
python tools\run_runtime_scenarios.py
python tools\run_runtime_scenarios.py --accesses
python tools\analyze_runtime.py
python tools\bootstrap_sources.py --force
make.bat
verify.bat
```

The detailed key timings, RAM test interventions, final text rows and
address windows are retained in `build/emulator/*.json` and the
generated `docs/generated/runtime-map.json`.
