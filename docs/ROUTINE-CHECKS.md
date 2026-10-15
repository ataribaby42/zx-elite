# Routine checks

`tools/check_routines.py` re-runs the routine-level verification evidence behind
the annotations in `tools/annotations/`. It consolidates the simulator tests
written while the source was annotated. Annotation headers cite it as
`tools/check_routines.py group/check`.

## Running it

Run it from the project directory after a default build:

```text
make.bat
python tools/check_routines.py                  all groups
python tools/check_routines.py --list           groups, checks and routines
python tools/check_routines.py --only maths     one group (repeatable)
```

It prints one `PASS`/`FAIL` line per check and a summary, writes
`build/routine-checks/verification.json` (no timings, so identical runs give an
identical file) and exits with status 1 when any check fails. A failed run
deletes the previous report first. The whole tool runs in about 15 seconds.

## Machine model and conventions

- The supplied **ZX Spectrum 48K** ROM and `build/game.bin` (asserted identical
  to block 5 of `assets/Elite - 128k.tap`; every build option symbol must be 0)
  are loaded into a private 64K memory list and executed by SkoolKit's Z80
  simulator. No 128K model is involved.
- Each check calls original routines with controlled registers and RAM
  fixtures. A call pushes a sentinel return address and runs until the routine
  returns (stack balance is checked) or reaches a named stop address. No
  interrupts are generated: a `HALT` is an error unless the check states that
  it treats it as a completed frame wait (the text handlers).
- Addresses come only from `build/game.map`. Numeric addresses are limited to
  fixed hardware (screen `$4000`, attributes `$5800`, ports, ROM) and harness
  RAM outside the game image (test stack below `FontRuntime`, a scratch area
  above it, and an upper stack above `InterruptStackTop`). Two unlabelled
  entry/stop points inside routines are located by searching for an
  instruction built from symbols (`LD HL,CombatScoreHigh`,
  `LD HL,(CombatScoreLow)`, `CALL PrintDecimalHL`).
- No byte of the build, the release or the reference tape is changed. Where an
  original test did so, a check changes only its private RAM copy and says so:
  emulated `RET` stubs for `FillViewAttributes` (its colour flash HALTs) and
  for `PutCharacter`/`NewLine` (output capture), the launch patch that
  `L_7A88` itself applies to `RespawnDustFront`, and the game's `L_AF01` NOP
  market patch.
- Random samples use `random.Random(<fixed seed>)` and are capped at a few
  thousand cases; small domains are tested exhaustively. Several checks also
  assert values recorded from the original runs (pixel counts, strings,
  frame sequences), so a behavioural change is reported even where no
  closed-form model exists.

## Check groups

### `controls`: Flight controls and gauges (387 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `read-flight-controls` | `ReadFlightControls` | 259 | PlayerRoll/Pitch/Speed copy the high bytes of RollControl/PitchControl/SpeedControl; RollIndicator/PitchIndicator = 21 +/- magnitude; SpeedGauge = speed\*5+5. |
| `draw-gauges` | `DrawGauges`, `DrawBarGauge`, `DrawIndicatorGauge` | 13 | Changed gauges are redrawn at GaugeScreenAddresses: 11 bars of value/4 pixels and two 2-pixel indicator markers at pixels value-2..value-1, five identical rows, right border. |
| `update-flight-controls` | `UpdateFlightControls` | 115 | RollControl/PitchControl/SpeedControl frame sequences: N/M +$FF per frame from $80FF/$00FF up to $8FF0/$0FF0, damping -$3C, recentring, pitch step $66, speed +/-$A0 with max $1FE0; KeyFlagsFlight is consumed on screens 0..3 and kept on screen 4. |

### `screen`: Screen, view buffer and pixel plotting (35,745 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `clear-view-buffer` | `ClearViewBuffer` | 4,096 | The 4 KB view buffer is cleared with the view frame: rows 0 and 127 = $00,$FF x30,$00, other rows $00,$80,0..0,$01,$00; SP is saved in ViewClearSavedSP. |
| `blit-view-bitmap` | `BlitViewBitmap` | 4,096 | Every view-buffer byte lands at the same offset in the top two screen thirds. |
| `restore-cockpit-test` | `RestoreCockpitIfFullScreen` | 1 | RestoreCockpitIfFullScreen returns at once when screen byte $4000 is not $FF. |
| `pixel-screen-address` | `GetPixelScreenAddress`, `AdjustScreenAddressCellRow` | 16,535 | GetPixelScreenAddress returns the bitmap byte of pixel (A, C); AdjustScreenAddressCellRow corrects HL after INC H leaves a character cell. |
| `toggle-view-pixel` | `ToggleViewPixel` | 11,008 | ToggleViewPixel XORs exactly one bit, pixel (C, B), into the view buffer; B and C preserved. |
| `xor-crosshair` | `DrawXorCrosshair` | 9 | DrawXorCrosshair XORs a "+" of CrosshairSize around (ShapeCentreX, ShapeCentreY); the arms are clipped to the screen and CrosshairTopLimit..CrosshairBottomLimit, the centre is left clear and a second call erases the cross. |

### `text`: Text output and screen text helpers (167 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `justified-word-wrap` | `StartJustifiedText`, `PrintCharacter`, `EndJustifiedText` | 82 | The justified printer lays a description out as 30-column lines padded at word gaps; StartJustifiedText also writes $20 to CurrentScreenId (31-byte fill).  PutCharacter and NewLine are stubbed to capture the output. |
| `token-control-handlers` | `PrintToken`, `PrintGalaxyNumber`, `PrintPresentSystemName`, `PrintSelectedSystemName`, `PrintCommanderName`, `PrintFuelLine`, `PrintCashLine`, `PrintGalaxyFirstSystemName`, `SetCapitals`, `SetTitleCase`, `SelectMessageMode` | 12 | Token controls 1..11 print " 1"/" 3", the present and selected system names, "Jameson", "Fuel: 7.0 Light Years", "Cash:   100.0 Cr", "Tibedied" and set the case/mode flags. |
| `message-control-handlers` | `PrintMessageByte`, `SelectTokenMode`, `SetLowerCase`, `SetColumn4Capital`, `CapitaliseNextLetter`, `SetTextRow10`, `SetTextRow6`, `ClearScreenAndFrame`, `DrawTitleUnderline`, `ClearPromptLines`, `PrintSelectedSystemAdjective`, `PrintRandomName` | 22 | Message controls: 6 token mode, 13 lower case, 8 column 4 + capital, 19 capital, 23/29 rows 10/6, 10 new line, 9 clear screen and frame, 11 title underline at $4340, 21 clears the prompt lines (480 bytes from $50A1), 17 adjectives Lavian/Disian/Riedquatian in justified text, 18 random names, 4 commander, 16 first system name. |
| `attribute-strips` | `ColourAttributeStrips`, `ColourPromptRow` | 3 | BuyScreenAttributeStrips colours 60 cells ($5821..$585E) and TradeScreenAttributeStrip 30 ($5821..$583E) with $05, then $5822/$5823 = $07; ColourPromptRow colours $5AA1..$5ABE. |
| `screen-text-helpers` | `PrintEconomy`, `PrintCommodityUnit`, `TestCommodityTonnes` | 44 | PrintEconomy prints "Mainly" for economy 4 and "Rich" otherwise, Industrial for 0..3 and Agricultural for 4..7; units t (0..12, 16), kg (13, 14), g (15), km (17); carry = tonnes. |
| `insert-space` | `InsertSpaceInTextBuffer` | 4 | A space is inserted at JustifyWritePointer; the bytes up to the first zero move up; the pointer is unchanged. |

### `pipeline`: 3D projection pipeline (154 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `project-body-position` | `ProjectBodyPosition`, `ProjectCoordinate` | 34 | Sun/planet projection for the four views: A=1 in front, offsets = 256\*\|h\|/depth and 256\*\|v\|/depth (bits 2/3 set below 256, 255 for a ratio of exactly 1, offset-256 up to 511), bit 0 right, bit 1 above, radius = $A000/depth word (255 up to $A0); A=0 behind the viewer or for an offset of 512 or more. |
| `object-projection` | `DrawObjectInView`, `BuildRotationMatrix`, `ComputeFaceVisibility`, `ProjectVertices` | 120 | DrawObjectInView on real blueprints in all four views (120 random cases, fixed seed): the third orientation vector is B x A / 128 within 1 unit, RotationMatrix rows are (X_r, Y_r, Z_r), ObjectViewDepth is the depth class, 1341 of 1353 face flags match the float model (the rest are near-zero or small-normal cases) and 1287 of 1292 projected vertices lie within 4 units. |

### `maths`: Arithmetic: division, multiplication, roots, vectors (362,214 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `fraction-dividers` | `DivideFractionABToC`, `DivideFractionAB`, `DivideFractionAEB` | 70,280 | C = A\*256/B and D = A\*256/B (E cleared) for every A < B; D = (A\*256+E)/B for A < B. |
| `dust-arithmetic` | `MultiplyByLowBits`, `DivideToFractionD`, `DivideWordToFixed` | 234,250 | HL = A\*(C mod 2^B) for B = 4, 5, 8 and all A, C; D = A\*256/B for all A < B; C:D = (A:L)\*256/B for A:L < $2000 and quotients below $4000, D kept when exact. |
| `line-helpers` | `DivideToFractionC`, `ScaleByFraction`, `DivideByteFraction` | 9,000 | DivideToFractionC: C = A\*256/B for A < B, $FF for A = B, D/E kept; ScaleByFraction: C = (MultiplyUnsigned(A, C) + $80) >> 8, DE/HL kept; DivideByteFraction with C = $FE: C = (A:E)/B for A < B. |
| `word-division` | `DivideWordFraction` | 5,000 | BC = (HL\*65536 + A\*256)/DE, HL = remainder, exact for HL < DE; overflowing inputs (HL >= DE) give wrong quotients. |
| `ratio-division` | `DivideRatioByte` | 6,000 | C = 256\*(DE:C)/(HL:A) by the documented shift/normalise algorithm (bit-exact model): a normalised divisor gives 255 for ratios >= 1 and the exact quotient or 1..3 more for divisors >= $8000; the dividend-overflow path forces the divisor top bit and can return values below 255 for ratios >= 1. |
| `multiply-helpers` | `UnusedMultiplyWordHigh`, `MultiplyNormalByCoordinate`, `ComputeCrossProductTerm` | 9,000 | UnusedMultiplyWordHigh = high word of the four MultiplyUnsigned partial products (IX restored); MultiplyNormalByCoordinate = 2\|n\|\*p_hi + high(2\|n\|\*p_lo) with sign n XOR p; ComputeCrossProductTerm = (D\*E - B\*C) from 2\|a\|\*2\|b\| products, halved, saturating. |
| `sign-magnitude-sums` | `HalveSumSignMagnitude`, `HalveDifferenceSignMagnitude`, `TranslateVertexAxis` | 8,000 | HL = (HL +/- DE)/2 for sign-magnitude words with the sign of the larger magnitude (HL on a tie); TranslateVertexAxis = HL:B + 2\*DE (+ fraction carry) within 1. |
| `half-chord-root` | `ComputeHalfChord`, `ClearBytes` | 11,052 | ComputeHalfChord: A = isqrt(D\*D - A\*A - CF) with BC, DE, HL preserved (11,051 cases); ClearBytes zeroes B bytes from HL and returns HL after them. |
| `vector-magnitude` | `GetVectorMagnitude`, `GetVectorMagnitudeHigh` | 2,552 | GetVectorMagnitude is within 1% of sqrt(x^2+y^2+z^2) when a 16-bit coordinate is >= 256 and returns 0 for \|v\| >= 65536; GetVectorMagnitudeHigh uses the mid/high bytes (($400000,$300000,$50000) -> $5028).  Vectors whose three coordinates are all below 256 are excluded: the routine does not return their magnitude. |
| `square-root-and-normalise` | `SquareRootHL`, `NormaliseVector` | 361 | SquareRootHL ~ 256\*sqrt(HL) within 3.5% for HL >= 16; NormaliseVector scales three sign-magnitude words to length $8000 and returns DE ~ the original length (within 3.5%, signs kept); recorded steering-vector results (300,400,0) -> DE 632 etc. |
| `rotation-helpers` | `AddScaledSignMagnitude`, `AddScaledCoordinate`, `RenormaliseOrientationVector`, `OrthogonaliseYVector`, `ComputeNegatedDotProduct` | 3,719 | AddScaledSignMagnitude = D + s\*\|B\|\*\|C\|/128 saturated (within 1.25); AddScaledCoordinate adds src\*\|C\|/256 with sign(C) XOR sign(src) (within 1% of \|src\|, IX/IY kept); RenormaliseOrientationVector pulls the length towards 127 (IX += 6); OrthogonaliseYVector leaves \|cos(Z,Y)\| <= 0.029; ComputeNegatedDotProduct examples. |
| `sun-relative-to-station` | `MakeSunRelativeToStation` | 3,000 | Each sun word becomes (sun - station) in sign-magnitude form with bit 0 lost; the fraction bytes are kept (3000 cases). |

### `numbers`: Small byte and word helpers (772 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `double-sign-magnitude` | `DoubleSignMagnitude` | 512 | C = (A AND $80) OR ((A << 1) AND $7E) OR carry-in; A bit 0 := A bit 6; carry out = old bit 0 (all 256 values, both carries). |
| `fuel-and-seed-helpers` | `SetFuelLevel`, `RotateSeedWordLeft` | 260 | SetFuelLevel: FuelLevel = min(A, 70), FuelGauge = 2\*fuel + (2\*fuel >> 3) for all A; RotateSeedWordLeft rotates both bytes of the word at HL left by one bit and returns HL + 2. |

### `lines`: Line drawing and clipping (9,010 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `line-delta-and-start` | `ComputeLineDelta`, `SetLinePlotStart` | 6,000 | ComputeLineDelta returns \|dx\|, \|dy\|, the slope and the documented direction/major/overflow flags (DE kept); SetLinePlotStart gives the buffer address, pixel mask and rows to the cell edge of the DE endpoint in the alternate registers. |
| `draw-line` | `DrawLine` | 3,002 | Lines with both ends inside equal a DDA model (start at the DE end, HL end pixel omitted); clipped lines stay within 3 pixels of the ideal segment, visible lines are drawn, nothing is written outside the buffer, stack and workspace (deltas above 255 may clip wrongly and are only counted); H AND E or L AND D = $FF draws nothing. |
| `sights-and-laser-lines` | `DrawLine` | 8 | The four sight lines and the laser beam lines produce the recorded pixels. |

### `circles`: Circles and the patched screen variants (101 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `circle-renderer` | `DrawCircle`, `DrawCircleOutline`, `DrawFilledCircle`, `DrawCircleOutlineAnySize` | 22 | Circles are drawn into the view buffer only, centred at 128 +/- dx, 64 -/+ dy by CircleFlags bits 0/1 (CircleCentreX/Y), radius +/- 1; outline mode leaves the interior empty (CircleOutlineFlag 1), fill mode fills it (flag 0); radius < 9 draws nothing except via DrawCircleOutlineAnySize; filled discs stay within x 8..247 and fill the full width. |
| `outline-arcs` | `DrawCircleLeftArc`, `DrawCirclePairedArcs`, `DrawCircleRightArc`, `L_8640`, `L_866E` | 42 | Outline circles of radius 9..200, centred in, near or beyond the view edges: every pixel lies between r-1.6 and r+2.1 from the centre, in view rows 0..127; the recorded arc routines (paired, left, right, row-address helpers) are used; with CircleFlags bits 2/3 clear an outside centre draws nothing. |
| `screen-circle-patching` | `DrawScreenCircle`, `DrawFlaggedObjectDiscs`, `PatchDiscRendererTarget` | 37 | CirclePatchTargets lists 32 bytes that hold ViewCirclePatchValues in the image; DrawScreenCircle draws chart circles on the 256x192 screen (buffer untouched) and restores every patched byte; DrawFlaggedObjectDiscs draws discs on screen rows 0..127, clears +$20 bit 4 and restores the buffer values ($CF/$BF at L_85D7/L_85E2).  FillViewAttributes (HALT-based colour flash) is stubbed with an emulated RET, as in the original test. |

### `scanner`: Scanner, compass and sun/planet proximity (658 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `scanner-background` | `SaveScannerBackground`, `RestoreScannerBackground`, `CopyScannerBackground` | 628 | Save copies the 624 bytes of character rows 2..7, columns 9..21 of the bottom third to ScannerBackupBuffer in row/line order without touching the screen, with the documented save patches; restore (only when ScannerContactsDrawn = 1) clears 8 x 11 bytes at row 1, column 10, copies the bytes back and restores the original instruction bytes. |
| `scanner-contacts` | `DrawScannerContacts` | 9 | Scanner contact of one object: ScannerDotX = 0.75\*x/256 (x = $1000 -> $0C, -$1000 -> $8C), ScannerStickHeight = 5/16\*y/256 ($05), ScannerDotZ = 5/16\*z/256, recorded dot/stick pixels; a coordinate middle byte of $40 or more is not drawn. |
| `compass` | `DrawCompass`, `DrawCompassBackground` | 9 | DrawCompassBackground copies CompassBackgroundBitmap to columns 21..23, rows 136..159; DrawCompass moves the 4x4 dot right for positive CompassDotX and up for positive CompassDotY (recorded positions) and draws nothing on screen 4. |
| `sun-planet-proximity` | `UpdateProximityAndCompass` | 12 | Sun/planet distance thresholds: d < $C000 destroys the player, the sun sets FuelScoopRangeFlag below $E000 and CabinTemperature = high(2.5\*($10000-d)), the planet sets StationPresent and AltitudeGauge = $A0 - high(2.5\*($10000-d)), FlightCondition follows (recorded outputs). |

### `sound`: Sound effects (42 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `interrupt-sound-player` | `UpdateSoundEffect`, `SoundRequestJumpTable`, `FinishSoundEffect` | 38 | With sound on, each request bit of SoundEffectRequests starts its SoundRequestJumpTable entry (bit 0 -2, bit 1 -28, bit 2 +2 noise sweeps; bit 3 SRL A and bits 6/7 ADD A,$10 ROM pulse bursts; bits 4/5 pulse sweeps $FD/$D3), runs 8, 8, 8, 1, 2, 8, 1, 1 frames and clears its bit; with sound off nothing happens. |
| `synchronous-sound-players` | `PlayLongNoiseSweep`, `PlayRisingNoiseSweep`, `PlayFallingNoiseSweep`, `PlayNoiseBurst`, `WaitSoundFinished` | 4 | Each synchronous player runs its effect to the end (SoundState 0) and clears all requests; last samples-per-step/delay-step operands $A0/+2, $C0/-16, $C0/+16, $A0/(unchanged). |

### `dust`: Stardust and the Torus jump (4,463 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `stardust-update` | `UpdateDust`, `MoveAndPlotDust`, `MoveDustInDepth`, `ApplyDustRoll`, `ApplyDustPitch`, `GetDustPixelAddress`, `RespawnDust` | 2,382 | Front view without roll/pitch: every particle record and every XORed pixel equals the model X += X\*dz/Z, Y += Y\*dz/Z, Z -= dz (dz = speed/2+1), leaving particles respawn inside the masks with their fraction bytes kept; rear view Z += dz with shrinking X/Y; roll keeps the radius within 3%; pitch moves particles vertically (recorded records). |
| `launch-dust-respawn` | `RespawnDustFront` | 64 | With the launch patch of L_7A88 applied (masks $83 at L_A348/L_A34D, RET at DustRespawnExit, made here in the private RAM copy exactly as the game does), each call creates one particle with \|X\|, \|Y\| <= 3 and Z >= $80 and advances DE by 5. |
| `torus-jump` | `HandleTorusJumpKey`, `ApplyJumpShift`, `UpdateDust` | 2,017 | With J latched and the preconditions met, HandleTorusJumpKey sets TorusJumpDustFlag and shifts the z coordinates of SunPosition, PlanetPosition and slot 0 by $2000 ($85AE16 -> $85CE16, $015ADC -> $013ADC); each inhibitor (SunNearFlag 1, PlanetNearFlag 1, L_DA0F set, StationDormantFlag 0) prevents it; ApplyJumpShift follows its sign-magnitude model; the next UpdateDust clears the flag and runs three passes with speeds $1E, $10, $10. |

### `economy`: Galaxy, systems and market (268 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `galaxy-system-names` | `LoadGalaxySeedsToGenerator`, `GenerateSystemName` | 256 | Galaxy 1 starts TIBEDIED, QUBE, LELEER, BIARGE, XEQUERIN, TIRAOR, RABEDIRA, LAVE; the generator walks all 256 systems. |
| `find-system-and-distance` | `FindSystemByName`, `DeriveSelectedSystemData`, `UpdateSelectedSystemDistance` | 3 | FindSystemByName selects LAVE at X 20, Y 173 (the JAMESON current system: same seeds, distance 0) with economy 5, government 3, tech level 4 (template 5), population 25, productivity 7000; TIBEDIED is 176 tenths away at (2, 90); an unknown name returns carry.  The cross-hair settings are those of the galactic chart. |
| `contraband-penalty` | `AddContrabandPenalty` | 7 | Slaves and narcotics add 4 per ton, firearms 2, other goods nothing; saturates at 255. |
| `market` | `ComputeMarket` | 2 | Lave market for fluctuation 46: recorded prices (tenths of a credit), no alien items; with the opcode at L_AF01 patched to NOP (the game's own stock-keeping patch, applied here in the private RAM copy) the stock is not stored. |

### `commander`: Commander rating, security number and seeds (6,528 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `rating-thresholds` | `ShowCommanderStatus`, `RatingKillThresholdsLow`, `RatingKillThresholdsHigh` | 1,528 | Rating token for the 16-bit kill count: 0..8 HARMLESS, ..16, ..32, ..64, ..128, 129..767 COMPETENT, 768..2815 DANGEROUS, 2816..6655 DEADLY, 6656+ ELITE.  Entered at the LD HL,CombatScoreHigh of ShowCommanderStatus, stopped at L_D130. |
| `security-number` | `AccessMenuSave`, `RotateParityIntoD` | 3,000 | The two save "security numbers" (HL, DE) follow the Python model of kill count, galaxy, CommanderFlags bits 3/6 and CashHigh for any carry on entry.  Entered at the LD HL,(CombatScoreLow) of AccessMenuSave, stopped at the first CALL PrintDecimalHL after it. |
| `galaxy-seed-compare` | `CompareWithGalaxySeeds` | 2,000 | Carry clear exactly when the six bytes at HL equal GalaxySeeds. |

### `dormant`: Dormant bytes (14 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `download-loader-relocation` | `L_C350`, `L_C3EE` | 9 | The dormant loader at L_C350 starts with DE = BC + $9E and nine "LD HL,n / ADD HL,BC / LD (HL),E / INC HL / LD (HL),D" relocations; with BC = L_C350 (USR convention) they are exactly the operands of the nine CALLs to L_C3EE, and there are no other such CALLs. |
| `unused-interrupt-routines` | `UnusedEnableInterrupts`, `UnusedSelectInterruptMode1`, `ViewBufferResidueAfterLoader`, `ClearViewBuffer` | 5 | Both routines follow a RET and have no word or JR/DJNZ reference; called with interrupts off in IM 2, `EI`, `RET` sets IFF and `IM 1`, `RET` selects IM 1, with other registers and memory unchanged. Both comparison 48K memory images hold EnableInterruptMode2 and UnusedSelectInterruptMode1 unchanged, no word $FF53, no CALL EnableInterruptMode2 (IM 2 is selected inline) and no RET, EI, RET. ClearViewBuffer replaces the residue bytes $F3,$AF with 0. |

### `missions`: Missions, pirates and encounters (2,082 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `hyperspace-arrival` | `L_D7B4`, `FinishHyperspaceArrival`, `TriggerFuelLeak` | 2,076 | Outside galaxy 0 the arrival tail increments JumpCounter and triggers mission bit 0 at a low byte >= $20 (L_A843 = 1, red view, fuel leak only with fuel), bit 1 at >= $80 and bit 2 at >= $FE (L_A871 = 1), only for the first clear bit; otherwise pirates board when AuxRandomSeed <= 7 - government (station +$1D bit 7 cleared); mission-3 states 1->2, 4->3, station +$26 bit 7 -> 5, 1..4 -> 4 at the galaxy-seed system; galaxy 0 skips all of it.  FillViewAttributes (HALT-based flash) is stubbed with an emulated RET that records its colour, as in the original. |
| `energy-bomb-exemption` | `UpdateObjects` | 4 | With EnergyBombPending the next UpdateObjects explodes active slots unless IY still holds a Thargoid blueprint from the previous slot: the ship after a Thargoid is spared, the Thargoid itself is not. |
| `special-encounter` | `SpawnRandomEncounter`, `L_F655` | 2 | Mission-2 special encounter (CommanderFlags bit 1): with free slots an Asp Mk II with +$20 = $C5, +$25 = $7F, +$26 = $40 and two Sidewinders are created and MissionAspEncounterState = 1; with all six slots occupied the code pops AF and continues in the ROM at $0F02 (documented bug). |

### `input`: Keyboard and joystick input (52 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `scan-keyboard` | `ScanKeyboard`, `RecordKeyPress`, `KeyCharacterTable`, `KeyActionTable` | 52 | Each of the 40 keys alone gives its KeyCharacterTable code in LastKeyCode and its documented KeyFlags bit; no key gives $FF, CAPS+0 gives $FE; Kempston, Cursor and Sinclair directions and fire map to KeyFlagsFlight/KeyFlagsCombat; keyboard ghost keys are suppressed. |

## Checks added in the second annotation pass

The second pass compared the source with an independent disassembly of the
same release and proved additional meanings. These checks back the names
and comments it added (see `docs/COMPARISON-SKOOLKIT.md`).

### `ai` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p11-apply-steering-vector` | `ApplySteeringVector`, `SteeringVectorLength`, `TryFireAiLaser` | 700 | ApplySteeringVector stores the NormaliseVector length of the steering vector in SteeringVectorLength; H/L/D = ComputeNegatedDotProduct with the forward, up and side axes; roll = (D xor L sign in bit 6) \| min(15, (m + m/8 + bit 2 of m)/4) with m = \|D\| (kept when m = 0); pitch skipped for roll rate >= 4, else sign of L in bit 6 and rate 15 (target behind) or (103 - (\|H\|+80)/2)/8; acceleration 2 and return while fleeing; otherwise ahead: 0 below range $0A ($02 missile), else 1 (range >= $10) or 2, always continuing into TryFireAiLaser; behind: 0 below $0B ($03), else -1 (below $12) or -2. |
| `p11-missile-guidance` | `UpdateMissileGuidance`, `SteerShipAwayFromPlayer`, `SteerShipTowardsPlayer`, `L_F9B2`, `L_F9DB`, `L_F9E2`, `L_F9AA` | 419 | Steering vectors are quarter-scale: away = +pos/4, towards = -pos/4 (low 16 magnitude bits, sign in bit 15) with +$26 bit 5 set/cleared; a missile with target code k aims at slot 8-k with (target-missile)/4; it hits when every component magnitude is below $20: +$20 bit 4 on the missile and the target, a station only in L_A871 mode 4 (then L_A871 bit 3, L_A870 = 0, combat score + $FFFF, station +$26 bit 7); active ECM destroys the missile; code 0 steers towards the player. |
| `p11-encounter-selection` | `SpawnRandomEncounter`, `L_F660`, `L_F684`, `L_F6E2`, `L_F706`, `L_F70E`, `SelectEncounterTraderType` | 11,092 | With scripted random bytes r1, r2: r = r1 - C (2\*(slaves+narcotics)+firearms); no borrow and r >= $5A: nothing; $50..$59: Asteroid; otherwise E = r AND 7, government g > E: nothing (anarchy never), E+1 for g <> 0; r bit 3: mixed single ship; else (r2 AND 7) >= E: a group of 2 + ((r3 AND 3) >> 1) + (r3 AND 1) Sidewinders/Kraits; else r2 bits 7..5 = 0..1: Rock hermit/Viper by r2 bit 4, 2..4 Cobra trader, 5..7 Python trader.  L_A871 = 4 / 1 force a Thargoid / Python trader. |
| `p11-ship-tactics-energy` | `UpdateShipTactics` | 2,000 | Energy becomes min(blueprint energy, energy + 1, or + 4 when the blueprint energy >= $F0); nothing is stored while CloakingDeviceActive is nonzero; with MissionAspEncounterState 1 the ship pays 2 energy (state -> 2 below $34 without paying); state 2 returns to 1 at energy >= $50. |

### `circles` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p2-circle-offset-bit8` | `DrawCircle`, `DrawFilledCircle`, `DrawCircleOutline`, `CircleFlags` | 18 | With CircleFlags bit 2 (x) or bit 3 (y) clear the offset is 256 + the stored byte: filled discs light exactly the view pixels of a disc centred that far away (within 1.5 pixels of the edge) and outlines stay on its circle; centres out of reach draw nothing. |
| `p2-span-end-locators` | `LocateSpanLeftEnd`, `LocateSpanRightEnd`, `SavedLeftEndMask` | 8,192 | For every x and sample view rows: HL = view-buffer address of (x, row); fill mode B = pixels right of x, C = pixels left of x; outline mode B or C = pixel x; LocateSpanLeftEnd sets E = L; LocateSpanRightEnd preserves B (kept in SavedLeftEndMask), D and E. |
| `p2-screen-circle-minimum-radius` | `DrawScreenCircle`, `DrawCircleOutline` | 9 | DrawScreenCircle draws nothing for a radius below 9 (DrawCircleOutline limit) and a circle for radius 9; it returns A = 0 with every patched byte restored. |

### `combat` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p9-ai-laser-beam` | `DrawObjectInView`, `DrawAiLaserBeam`, `DrawAiBeamFromCentre` | 7 | With +$20 bit 3 the view buffer equals the drawing without it OR one DrawLine from the gun vertex (wireframe) or the projected centre (dot/off-screen, quadrant mirrored in rear/right views) to (255-r, r) in the opposite quadrant, r = NextRandomByte; bit 3 is cleared and L_F116 keeps its value. |
| `p9-player-laser-rate` | `UpdatePlayerLaser`, `LaserTriggerHeld` | 25 | Each call: LaserTemperature -= 2 (not below 0) and KeyFlagsCombat bit 0 is consumed.  A fire request with temperature < $90 after cooling and a laser on the current view sets LaserTriggerHeld; the first request fires, held requests fire only when ObjectUpdateCounter AND 1 (pulse, type 1) or AND 7 (mining, type 4) is 0, beam and military fire every call; no request clears LaserTriggerHeld.  (L_EC11, where firing continues, is stubbed.) |
| `r10-laser-hit-outcomes` | `UpdatePlayerLaser`, `ApplyPlayerLaserHit` | 2,965 | TargetedObjectCounter t selects slot 8-t (0: beams only).  A hit sets +$21 bit 2 and sound bit 3; the station flag (+$26 bit 2), +$20 bit 5 and energy $FF prevent damage; +$25 drops by 14 (6 or 7 on borrow, bits 0 and 7 kept); a kill sets energy $FF and +$20 bit 4, the marked Asp (state 1/2) gives state 3 and event 6, otherwise the blueprint debris event: 6 canister, 5 alloys (energy >= 85), 8 splinters (Asteroid, damage 50). |
| `r10-sights-and-ecm` | `UpdateSightsLaserAndEcm`, `ClearPitchAndSpeed` | 295 | PlayerDeadFlag clears pitch and speed and skips sights, laser and ECM; screens 4+ change nothing; the ECM countdown skips everything for jammer + L_A871 = 4, consumes key bit 4, starts through ActivatePlayerEcm when idle, clears EcmFitted bit 7 at expiry and while running sets sound bit 5 and drains one L_DA17 unit when an ECM is owned. |

### `commander` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p5-escape-pod` | `UpdateEscapePod`, `EscapePodTimer` | 7 | Q with the escape pod fitted (not in witchspace): EscapePodTimer 24, SpeedControl $0010, legal score 0, pod used up, fluctuation and cargo 0..15 cleared while alien items stay, refugees bit 5 cleared, free space 20 (35 with the large cargo bay), ship event $17, chart cursor on the current system.  The timer then counts down and jumps to L_7102 at zero. |
| `p7-docked-screen-text` | `ShowCommanderStatus`, `PrintInlineTokenIfSet`, `PrintLaserMount`, `PrintColonTokenAtColumn21`, `NewLineAtColumn5`, `ShowInventory` | 7 | Status screen rows 1, 4..9 and 11, equipment from row 12 at column 5 in the documented order; the jammer line replaces E.C.M. System; laser types 1..4 on all four mounts; the inventory puts Large Cargo Bay on row 6 (attributes $05, columns 1..30), Refugees on row 7 and cargo after them. |
| `p7-security-number-print` | `AccessMenuSave`, `PrintDecimalHL` | 302 | After a save the screen shows "SECURITY NUMBER: " followed by HL in decimal without padding and DE as exactly five digits (leading zeros), one digit string; HL and DE from the commander/security-number model.  Entered at the LD HL,$0C01 after "COMMANDER SAVED". |
| `p7-tape-load-paths` | `LoadCommanderRecord`, `CommanderLoadedFlag`, `CopyCommanderToTemplate`, `TapeLoadFailed` | 6 | With ROM LD-BYTES stubbed (IX = ActiveCommanderRecord, DE = 104, A' = $FF, carry set): records are loaded until the name matches (an empty typed name accepts the first), CommanderLoadedFlag is 1 after any record, the accepted record becomes the template; a failed load with key $20 (BREAK) keeps the partial bytes, any other key restores the record from the template. |

### `contact` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p9-object-contact` | `HandleObjectContact`, `CollideWithObject`, `ReleaseTargetLocks` | 24 | HandleObjectContact reacts only when \|x\|, \|y\| and \|z\| are all below the radius (blueprint +1; +256 for a missile whose target code +$25 is 0, the player) and z has no bits above 16; ships then lose all energy, add $50 (+ their energy for missiles) to FrontDamageThisUpdate (z >= 0) or RearDamageThisUpdate (z < 0) and request sound bit 2; the marked mission ship clears MissionAspEncounterState; nothing happens while PlayerDeadFlag is set. |
| `p9-scooping` | `HandleObjectContact`, `ScoopCargoItem` | 50 | Objects with +$26 bit 1 use radius $B4.  Below the player (y < 0) with FuelScoopsFitted and free cargo space they vanish without damage and add one ton: (blueprint +0 >> 4) + 1 (escape capsule slaves, alloy plate alloys, splinter minerals, Thargon alien items) or, for nibble 0 (canister), random AND 7; in MissionAspEncounterState 3 a canister gives the cloaking device (CommanderFlags bit 6, state 0).  Above, without scoops or with a full hold the object is destroyed with collision damage. |
| `p9-station-docking` | `HandleObjectContact`, `TestStationDocking`, `CrashIntoStation` | 13 | Station slot (+$26 bit 2) inside its radius box: L_DA15 = 1 (CheckDocking then docks) when it lies ahead (z >= 0), is not hostile, its local z axis points at the player (+$0E sign set) and \|Z.x\|, \|Z.y\| < $1E; with one of them $1E..$6D sound bit 6 and FrontDamageThisUpdate += 12 + 2\*PlayerSpeed; any other case sets PlayerDeadFlag = $0F.  The station keeps its energy. |
| `p9-release-target-locks` | `ReleaseTargetLocks` | 8 | With ObjectLoopCounter = H: MissileState 2 locked on H becomes 0 and TargetLostMessage bit 7 is raised (other states or targets unchanged).  Only when the removed object IX is a missile (+$26 bit 0) do live slots 1..7 whose +$25 equals H get +$20 bit 4 (explosion); IY is preserved. |

### `controls` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p1-chart-cursor-keys` | `HandleChartCursorKeys` | 3,120 | Only on screens 7 and 8 with L_A80A clear: screen handler 9 + the lowest set bit of (KeyFlagsFlight AND $0F) OR (KeyFlagsChart AND $70) runs through CallScreenHandler and both key bytes are cleared; otherwise nothing is called and the key bytes are kept. |
| `p1-title-ship-cycle` | `L_71C8`, `TitleShipCounter` | 256 | After the key is released the title counter is incremented and event 9 is dispatched with C = (counter AND 7) + 1, plus 10 below 6: ship IDs C+2 cycle 13..17, 8, 9, 10. |
| `p1-cloak-toggle` | `ToggleCloak`, `CloakKeyDelay` | 37 | Acts on every second call when Y (KeyFlagsScreens bit 7) is latched again after one frame and CommanderFlags bit 6 is set: 1 -> 0 with L=7 colours; otherwise on with EnergyBank3 >= $28 (value 1, station hostile bit and SharedHostilityAlert cleared, L=$0F), else the decremented value stays (0 -> $FF) without colours. |
| `p1-gauge-all-lengths` | `DrawBarGauge`, `DrawIndicatorGauge`, `StoreGaugeEndByte` | 80 | Every bar length 0..40 and indicator position 2..40 rewrites exactly the five bytes of all five pixel lines: n leading pixels (bars) or pixels p-2..p-1 (markers), plus the right border pixel; the bytes on either side are untouched. |
| `p4-launch-reset` | `PrepareShipForLaunch`, `ColourInstrumentBlocks`, `FillAttributeBlock` | 8 | PrepareShipForLaunch clears MissileState, LaserTemperature, CabinTemperature and DockingComputerFlag, sets ForwardShield, AftShield, AltitudeGauge and EnergyBank1..4 to $A0 without touching their drawn copies, and ColourInstrumentBlocks writes exactly the 70 cells of columns 3..7 and 24..28, rows 17..23: $17, or $1F with EscapePodFitted, into VRAM for views 0..3 and into the $5B00 save buffer otherwise. |

### `dust` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p5-side-view-respawn` | `RespawnDustSideView`, `RespawnDust`, `SwapDustParticleXY` | 386 | Side views (screen 2 left, 3 right): without a vertical rate a new particle has X = +120 (left) or -120 (right), \|Y\| <= 63 with a random sign and Z < $80; with a rate Z >= $80 and AlternatingBits alternates that pattern with a random X (magnitude bit 3 clear) on the top (Y = +63, DustFlags bit 3 set) or bottom (Y = -63) edge.  Fraction bytes are kept and DustRecordPointer advances by 5.  SwapDustParticleXY exchanges bytes 0 and 1 of the first DustRemaining records only. |
| `p4-torus-jump-effects` | `HandleTorusJumpKey`, `ResetShipSlots` | 8 | A refused or absent J keeps everything except key bit 6 (other KeyFlagsViews bits kept); a jump clears MissionAspEncounterState, frees slots 1..7 (energy 0), clears the station hostile bit and SharedHostilityAlert, rotates AlternatingBits ($55 <-> $AA) and sets ObjectUpdateCounter = 1 only when the old value was $AA. |
| `p4-dust-roll-pitch-side-model` | `ApplyDustRoll`, `ScaleByRate`, `ApplyDustPitch`, `MoveDustSideways`, `StoreAndPlotDust`, `NegateDustX`, `NegateDustY`, `UpdateDust` | 9,004 | Exact particle records for random inputs: roll x' = x -/+ (\|y\|\*r)>>7 (\|X\| grows on odd X/Y/roll sign parity), then y' from the new \|x\| (\|Y\| grows on even parity), negation across zero, respawn at 120; pitch s = hi(2\*($4000 - y\*p)), Z\*s/128, X\*128/s, (y+p)\*128/s with the zero-quotient sign flip and the 0/128/64/63 respawn limits; side view step (dz\*256/Z)/2+1 with direction from bit 5 XOR the X sign and respawn at 119.  UpdateDust leaves IX, IY and the alternate registers unchanged. |

### `economy` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p6-select-system-at-cursor` | `SelectSystemAtCursor`, `PrintSelectedSystemSummary` | 2 | The chart key handler SelectSystemAtCursor selects the system nearest the cursor: (3, 92) -> TIBEDIED at (2, 90), 17.6 light years from LAVE; (21, 171) -> LAVE at (20, 173), distance 0 (no distance line).  The name is printed in capitals on prompt row 21. |
| `p6-nova-cargo-screens` | `BuyCargoScreen`, `SellCargoScreen` | 5 | BuyCargoScreen with L_A843 set: 'Y' empties the hold, sets LargeCargoBayFitted ('Y'), free space 0 and CommanderFlags bit 5 (circle $B6/$76/$3D); another key changes nothing; with bit 5 set the inventory is shown at once.  SellCargoScreen with L_A843 clear and bit 5 set: bit 5 cleared, CombatScoreHigh + 1, 100 g of gem-stones (CargoHold+15), free space 35; with L_A843 set it runs SellCargoList. |
| `p6-equipment-purchase` | `BuyEquipmentItem`, `GetEquipmentPriceEntry`, `SubtractCash` | 4 | BuyEquipmentItem item 1 with fuel price 0.5 Cr: L_A843 clear -> fuel 70, cash -0.5, price cleared; L_A843 set -> fuel unchanged but the 0.5 Cr stays paid.  Item 2 with 4 missiles: "ALL PRESENT", cash restored.  An item beyond EquipmentItemCount goes to the status screen. |
| `p5-market-model` | `ComputeMarket`, `CommodityTable` | 512 | For every economy 0..7 and 64 fluctuations, ComputeMarket matches the model: term = factor \* economy; stock = base quantity + (fluctuation AND mask) - (term + 1) when byte 1 bit 7 is clear, + term when set, 0 when bit 7 of the result is set, AND $3F (alien items 0); price word = 4 \* (base price + (fluctuation AND mask) + term when clear, - (term + 1) when set), 8-bit sums. |
| `p3-commodity-table` | `CommodityTable`, `ComputeMarket` | 40 | CommodityTable holds 17 four-byte records (base price; economy factor in bits 0..4 and direction in bit 7; base stock; fluctuation mask): a model of these fields reproduces every MarketPrices word and MarketStock byte of ComputeMarket for economies 0..7 and five fluctuation values; ALIEN ITEMS (record 16) has no stock. |

### `input` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p3-screen-keys` | `HandleScreenKeys`, `SelectScreen`, `CallScreenHandler`, `ClearViewAndScreenKeys` | 33 | Keys pressed through ScanKeyboard, then HandleScreenKeys: docked, 1 calls StartStationTunnel and 2/3/4 select screens 4..6 with handlers 0..2; in flight 1..4 select cockpit views 0..3 without a handler; I, O, P, K, L, ENTER select screens 7..12 with handlers 3..8 (table entries BuyCargoScreen..ShowInventory); a screen >= 7 that is already shown is not redrawn; L_A80A refuses views 1..3 (front view instead); both key bytes end cleared. |
| `p3-freeze-options` | `HandleFreezeMode`, `ToggleFreezeOptionB`, `ToggleFreezeOptionD`, `ToggleFreezeOptionF`, `ToggleFreezeOptionR`, `ToggleFreezeOptionY`, `SelectSoundOff`, `SelectSoundOn`, `ToggleControlDevice`, `ClearKeyFlags`, `RequestNewGame` | 18 | Freeze loop driven frame by frame through LastKeyCode: B, D, F, R, Y toggle ControlOptions bits 4, 3, 6, 2, 5; Q clears and S sets bit 7 (S also clears SoundEffectRequests); K swaps the keyboard and the SelectedJoystickType device (nothing without one); each option beeps once, other keys do nothing; SPACE returns carry clear and 1 carry set, both with the five key bytes cleared; without the CAPS SHIFT bit it returns at once.  Through ScanKeyboard, bit 4 swaps the roll (N/M) and pitch (X/S) key bits and bit 5 swaps the pitch bits only. |

### `maths` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `r8-motion-helpers` | `ScaleComponentBySpeed`, `AddToCoordinate`, `SquareRootHL`, `ApplyPlayerMotion` | 6,014 | ScaleComponentBySpeed and AddToCoordinate equal their bit-level models (the high-byte test compares all of A with D); SquareRootHL returns A = 0; ApplyPlayerMotion without rotation moves z by 2\*(speed+1) towards negative, flips the sign when crossing zero and turns a negative overflow into +$7FFFxx, returning HL = z high/mid. |
| `roll-reversal-drift` | `ApplyPlayerMotion`, `AddScaledCoordinate` | 2 | Original quirk: a roll is two shear steps in a fixed order (x -= y\*a, then y += x\*a with the new x, a = 2\*roll/256), so a roll to the right is not undone by a roll to the left. M and N held alternately for 32 updates each (roll ramps to 15 and -15) for 20 cycles move the planet 4.98 times further from the view axis at unchanged depth; the same order in exact arithmetic gives 6.2, a true rotation 1.0. The same number of updates in one direction gives 0.83. |

### `missions` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `r8-docking-contact` | `L_EA51`, `CheckDocking`, `CheckHyperspaceKeys`, `DockingContactFlag` | 17 | Touching the station (inside its size, in front, not hostile, nose z < 0) sets DockingContactFlag only when \|Z.x\|, \|Z.y\| < $1E; up to $6D adds 12 + 2\*speed front damage and sound bit 6; worse alignment, a hostile station or z < 0 sets PlayerDeadFlag $0F; out of reach nothing.  CheckDocking clears the flag and docks unless L_7C39 is set; a G press without H sets L_7C39 although no jump starts. |
| `r8-energy-drain` | `L_A584`, `L_EDA9`, `L_EC11`, `UpdateObjects`, `EnergyDrainThisUpdate` | 14 | L_A584 drains 4\*(EnergyDrainThisUpdate + cloak) from energy bank 1; the ECM update (C nonzero) and a laser shot each add one; UpdateObjects clears it. |
| `r8-object-presence-flags` | `UpdateObjects`, `TorusJumpInhibitFlag`, `LastNonStationObjectEnergy` | 3 | After UpdateObjects: station only -> TorusJumpInhibitFlag 0, LastNonStationObjectEnergy 0 and SharedHostilityAlert cleared; plus a cargo canister (+$26 = $0A) -> flag 0, energy 17, alert cleared; plus a Sidewinder (+$26 = 0) -> flag 1, energy 70, alert kept. |
| `p5-nova-mission` | `NovaMissionActive`, `ExpandingSunActive`, `ArmExpandingSun`, `UpdateExpandingSun`, `CheckFlightWarnings`, `GalacticHyperspaceJump`, `NormalHyperspaceJump` | 18 | ArmExpandingSun sets ExpandingSunActive and paints the view red (colour 2) only with NovaMissionActive; UpdateExpandingSun does nothing while ExpandingSunActive is 0, otherwise CabinTemperature + 1 and the sun radius + 2 (from CircleRadius when ExpandingSunRadius is 0), radius 256 sets PlayerDeadFlag.  CheckFlightWarnings sends token $C2 "MAYDAY \* CORIOLIS IN DANGER\*" only with the nova flag and the sun not yet armed, token $0F "... INVADED\*" for InvasionMissionState 1, every 70th call.  The nova flag turns NormalHyperspaceJump into GalacticHyperspaceJump, which clears it with ExpandingSunActive and the invasion state. |
| `p5-nova-offer-and-reward` | `BuyCargoScreen`, `SellCargoScreen`, `NovaMissionActive`, `CommanderFlags` | 7 | With NovaMissionActive the buy key shows message $5B "THE SUN IS GOING NOVA\* ... (Y/N)?" and a circle of radius $3D; Y empties all 17 holds, free space 0, LargeCargoBayFitted nonzero and CommanderFlags bit 5 (refugees); other keys change nothing; bit 5 already set skips trading.  Selling with bit 5 set and the nova flag clear rewards: bit 5 cleared, CombatScoreHigh + 1, 100 gem-stones, free space 35 and message $0F "YOU HAVE SAVED OUR LIVES"; with the nova flag set the normal sell list runs. |
| `p5-invasion-mission` | `InvasionMissionState`, `OfferSpecialMission`, `AwardHighestHonour`, `L_782B` | 10 | Docking acts on InvasionMissionState: 1 and 2 -> OfferSpecialMission, 4 -> EndGameWithMessage with message $D4 " THARGON", 5 -> AwardHighestHonour, 0, 3 and $0C -> nothing.  The offer (message $DF "... SPECIAL MISSION ... (Y/N)?") sets state 3, CommanderFlags bit 7 and shows the briefing $E0 "... TO DESTROY THE SPACE STATION ..." on Y, state 0 otherwise.  The award adds 256 to the combat score, sets CommanderFlags bit 3, clears the state and shows message $0A "... HIGHEST HONOUR". |
| `p5-jump-tunnel-mode` | `JumpTunnelMode`, `TunnelLoopActive`, `CheckHyperspaceKeys`, `ExecuteHyperspaceJump`, `StartStationTunnel` | 11 | CheckHyperspaceKeys sets JumpTunnelMode 2 (galactic, needs the hyperdrive) or 1 (normal, target in fuel range) and starts the countdown; out of range or without the hyperdrive it stays 0.  ExecuteHyperspaceJump takes the galactic path for 2 only.  StartStationTunnel sets both bytes to 1 (not in witchspace); FinishLaunchTunnelLoop clears TunnelLoopActive only, FinishHyperspaceTunnel both.  HandleScreenKeys ignores keys while TunnelLoopActive is set. |
| `p1-mission-state-on-docking` | `CheckMissionStateOnDocking` | 256 | L_A871 = 1 or 2 runs OfferSpecialMission, 5 AwardHighestHonour, 4 EndGameWithMessage with A = $D4 (" THARGON"); every other value returns without action. |
| `p2-hyperspace-key-latch` | `HyperspaceKeyLatch`, `CheckHyperspaceKeys`, `CheckDocking`, `FinishHyperspaceArrival` | 9 | CheckHyperspaceKeys sets HyperspaceKeyLatch whenever it consumes a hyperspace key bit, also for refused jumps (countdown running, zero distance, no galactic drive); while it is set CheckDocking docks neither on station contact nor with the docking computer key; FinishHyperspaceArrival clears it. |
| `p4-energy-bomb-use` | `UseEnergyBomb`, `FlashViewAttributes`, `FillViewAttributes` | 53 | FillViewAttributes fills rows 0..15, columns 1..30 only, with L AND 7 without the cloak, L while CloakingDeviceActive is nonzero, then AND $3A while L_A843 is set, returning A = B = 0 and H = L = the value; the L_9291 entry skips the cloak mask.  UseEnergyBomb acts only with key bit 5 and a nonzero EnergyBombFitted: it clears that byte, sets EnergyBombPending = 1 and SoundEffectRequests bit 0 (other bits kept), leaves the key byte, and fills 48 times (24 x cyan $28, then $0F through the masks). |

### `objects` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `r10-ship-creation` | `InitialiseShipFromBlueprint`, `CreateShipAtParent`, `FindFreeShipSlot`, `L_F3AD`, `L_F3B3`, `SpawnThargoidGroup`, `SetUpDisplayShip` | 147 | The loader sets the documented fields for all 19 IDs (template, energy, +$20/+$21, half speed, +$25 = $7E, +$26 = 0, random x/y low bytes and signs, high bytes 0..7 unless hostile, z kept; 3 or 5 RNG calls; A = 0, Z).  FindFreeShipSlot/CreateShipAtParent outputs including failure; L_F3AD/L_F3B3 give the identity orientation at x = z = 0; Thargoid groups have 3-4 members and the documented fields; the slot-7 orientation bytes form a rotation and land in the axis high bytes. |

### `pipeline` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `r8-projected-object-size` | `DrawObjectInView`, `ProjectedObjectSize` | 120 | ProjectedObjectSize = DivideRatioByte(blueprint +1 size, depth) = min(255, 256\*size/depth) for every view once the depth exceeds the size (otherwise unchanged); an object with +$20 bit 4 has it copied to +$1F with ProjectedX in +$1C and +$20 bit 5 set (L_E1D4). |
| `p9-explosion-record` | `DrawObjectInView`, `RecordExplosionPosition` | 11 | A visible object with +$20 bit 4 is not drawn: +$1C/+$1D = ProjectedX/Y, +$1F = projected size (L_DA0B), +$1E = $0C + CircleFlags side bits (bit 0 right of centre, bit 1 above, rear/right views mirrored) and +$20 bit 5 is set; behind or off the view nothing is recorded. |
| `p9-avoidance-in-sights` | `DrawObjectInView`, `CancelAvoidanceInSights` | 9 | A counted (+$20 bit 6) hostile (+$21 bit 2) ship near the view centre (ProjectedX+ProjectedY < $20) whose local z axis has \|component\| >= $40 along the view axis (z in front/rear views, x in left/right views) loses the avoidance flag +$26 bit 5; otherwise it stays. |
| `p1-projection-offset-paths` | `ProjectBodyPosition`, `ProjectCoordinate` | 4,005 | Offsets below 256 (\|c\| <= depth, bit 2/3 set) are within 2 of min(255, 256\*\|c\|/depth); the 256..511 path (bit clear) matches a bit-level model of L_76D6/L_7746 exactly, including the not-visible case, and is approximate: within 3 of 256\*\|c\|/depth-256 for 99% of coordinates with as many significant bits as the depth (x $1774EC / z $176C2A borrows: 173), -1..+127 too large with more bits (x $180000 / z $0F0000: 206).  Near a body this hides a disc that should fill columns 136..247 (x $80E5 / z $7E00: 131 instead of 6).  Depth 1 (1/256) gives 128. |

### `scanner` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p3-scanner-geometry` | `DrawScannerContacts`, `L_8DBA`, `L_8DCC`, `SetConditionYellowForShips` | 37 | One contact at x = +/-(dx\*256/0.75), y = z = 0: stick column 123 + dx (124 - dx when x is negative) on row 165, dash from that column two pixels to the left; dx = 4 lands one row lower (+) or higher (-) because B = 0 makes the byte loop run 256 times.  Tallest upward stick: in column 15 the climb stops at the top of the bottom third, elsewhere its dash lands on screen row 127; downward sticks stop at the bottom of the screen.  The condition colour becomes 6 when L_DA1A is non-zero unless it is 2 or $63. |

### `structures` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `s1-blueprint-instance-initialisation` | `InitialiseShipFromBlueprint`, `ShipBlueprintTable` | 76 | For every ID (also with bits 6/7 set in A, and with table bytes 0 and 3 overwritten) IY and instance +$23 = the table pointer; +$22 = header +7; +$21 = header +$12 AND $6F; +$20 = $40 \| header +$0A bits 0..2 \| header +$12 bit 7; +$1B = header +6 / 2; +$25 = $7E; +$26 = 0; +$1F is not written (template copies +$00..+$1E). |
| `s1-blueprint-ai-laser-chance` | `TryFireAiLaser` | 5,632 | A hostile ship passes the random firing gate when NextRandomByte < header +2, halved (SRL) while CombatScoreHigh = 0 (kill count below 256); every real header value and 0/1/$FF. |
| `s1-blueprint-debris-events` | `L_ECAD`, `DispatchShipEvent`, `SpawnCargoCanister` | 12,534 | Destroyed by the player: header +0 low nibble nonzero -> event 6, else header +7 >= 85 -> event 5, else +7 = 60 with damage 50 -> event 8, else none.  With the real dispatcher every cargo-carrying blueprint (low nibble 1, 2, 3, 5 or 7) creates exactly one Cargo canister (+$26 = $0A). |
| `s1-blueprint-scoop-and-radius` | `L_EA51`, `ScoopCargoItem` | 412 | Proximity box: every \|x\|,\|y\|,\|z\| must be below header +1 (+256 for a player-targeting missile, 180 for a scoopable +$26 bit 1 object).  Scooped: commodity = header +0 high nibble + 1, or a random 0..7 when it is 0, or $FF (cloaking device) once MissionAspEncounterState = 3; real blueprints give SLAVES, ALLOYS, MINERALS and ALIEN ITEMS. |
| `s1-blueprint-view-distances` | `DrawObjectInView`, `L_E10E` | 82 | DrawObjectInView continues past the near test (L_E038) only when the 16-bit depth exceeds header +1; L_E10E draws the wireframe (L_E175) when the depth high byte is below header +$0B, else a dot. |
| `s1-blueprint-launch-byte` | `TryLaunchAiPayload` | 513 | With a nonzero payload (+$20 bits 0..2) the AI launch event is (header +$0A AND $F0, or 6 when zero) XOR 4: missile event 2, or event 4 with launch subtype = high nibble; success decrements +$20 and a missile raises IncomingMissileMessage.  Rock hermit -> $54, Thargoid -> $34. |
| `s1-blueprint-kill-award` | `L_DAFA`, `L_DB0F`, `L_DB43`, `AwardBounty`, `AddCombatScore` | 19 | State 10 (+$20 bits 5:4) removes the object: energy 0, +$20 bit 5 cleared, +$1D = $C0; AwardBounty gets header word +8 and AddCombatScore header word +$15 / 2; header +$12 AND $60 makes PlayerLegalScore at least $40.  All 19 blueprints. |
| `s1-instance-explosion-states` | `L_DBA3`, `DrawObjectInView`, `L_E1D4`, `DrawFlaggedObjectDiscs` | 4 | +$20 bits 5:4: a destroyed object (01) drawn in view records ProjectedX/ProjectedY, $0C + inverted quadrant bits and the projected size in +$1C/+$1D/+$1E/+$1F and becomes 11; DrawFlaggedObjectDiscs draws 15 discs (radius +2 each) and makes it 10; an object that is not drawn goes 01 -> 10 in L_DBA3. |
| `s1-instance-rotation-counters` | `MoveObject`, `L_DD5D` | 512 | Instance +$1D/+$1E: bit 7 rotates every move without counting; otherwise a nonzero low nibble rotates once and decrements the byte, a zero low nibble stops (bits 4/5 are ignored); the step is 12 for roll and 8 for pitch, bit 6 selects the negative direction (+$80). |
| `s1-blueprint-geometry-format` | `ShipBlueprintTable` | 905 | All 19 default records and the original side-B Adder: edge byte 0 (visibility threshold) is at most $1F; vertex and edge face nibbles are below the face count or 15; edge vertices and the gun vertex (+$14) are below the vertex count; faces follow the edges (offset 0 when there are none); +$0A bit 3 and +$12 bit 4 are clear. |

### `text` (second pass)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `p6-unreachable-byte` | `L_B93F`, `SetLowerCase` | 3 | The $C9 byte at L_B93F is unreachable: no little-endian word in the image equals its address, no JR/DJNZ targets it, and the instruction before it is the unconditional JR of SetLowerCase. |
| `p6-input-quantity` | `InputQuantity`, `L_B32B`, `AcceptQuantity` | 9 | InputQuantity: the handler runs after every digit with EnteredNumber 1..99; a second digit or a delete first undoes the previous attempt (RestoreTradeState); Enter first -> carry, A = 2; a non-digit key -> carry, A = key, without undoing a one-digit attempt; codes below '1' (first) or '0' (second) and an early delete are ignored; a refusing handler -> carry, A = 1. |
| `p6-input-string` | `InputString`, `EraseInputCharacter` | 4 | InputString keeps '0'..'9' and '@'..'Z', ignores other codes and a delete on an empty buffer, deletes the last character, ends on Enter and also on a further character once the maximum length is reached (that character is dropped); the result is zero-terminated. |
| `p7-justify-padding` | `InsertSpaceInTextBuffer`, `FindPreviousSpace` | 4 | In the justified printer each InsertSpaceInTextBuffer call adds one space at an existing word gap: the calls equal the extra spaces inside the printed lines, every printed line is 30 characters wide and the words keep their order.  PutCharacter and NewLine are stubbed. |
| `justified-full-stop-loss` | `PrintCharacter`, `EndJustifiedText` | 1 | Original quirk: a character that arrives as the 31st character of a justified line is stored after the 30 printed characters and lost; here the final full stop disappears. |
| `description-full-stop-loss` | `DeriveSelectedSystemData`, `GenerateSystemName`, `L_BA49` | 1 | The same quirk in real game text: the "DATA ON" description of SOCELAGE (galaxy 1, system 45) is generated with a final full stop, but its second line is exactly 30 characters wide, so the full stop never reaches the screen. A scan of all 2,048 descriptions found 72 such cases, always the final full stop. |

## Checks added in the station-slot investigation

These checks back the station-orientation findings in
[findings](FINDINGS.md#found-in-the-station-slot-investigation). They run on
the default build like every other group. The optional repair has its own
tool, `tools/check_station_slot_fix.py` (see
[build variants](BUILD-VARIANTS.md#station-slot-fix)).

### `station`: Station orientation (3,358 cases)

| Check | Routines | Cases | Claim supported |
|---|---|---:|---|
| `arrival-slot-direction` | `ArriveInTargetSystem` | 2,048 | For all 2,048 systems the station is placed $18000 from the planet, along z in galaxies 1, 3, 5 and 8 and along x in galaxies 2, 4, 6 and 7. Every z placement points the nose (docking slot) at the planet. For x, the raw compare of sign-magnitude bytes reverses the nose for a negative planet x: 464 systems (96, 128, 112 and 128 in galaxies 2, 4, 6 and 7), each exactly 180 degrees away. Entered after `RandomiseMarket`, at the instruction found by its bytes `LD B,$12` / `XOR A` / `LD HL,SunPosition`. |
| `dormant-orientation-frozen` | `UpdateStationDormancy`, `MoveObject` | 2 | After arriving at DISO (galaxy 1, slot facing the planet) the station is dormant. 20 updates of `MoveSunAndPlanet` and `UpdateStationDormancy` at pitch 8 turn the station and planet positions, but the station axes stay byte for byte the same, so the slot error grows from 0 to 38 degrees. Once moved next to the player, the station is switched on and its axes turn. |
| `orientation-pitch-quantisation` | `RotateVectorRollPitch`, `ApplyPlayerMotion` | 8 | Axes get the shear steps of `ApplyPlayerMotion` at the same scale, but with pitch/2 truncated. Over 32 updates, pitch 1 turns a position by 7.2 degrees and a unit axis not at all. Pitch 3 turns the axis by 14.5 degrees like pitch 2, while the position turns by 21.4. Roll 1 turns both alike, by 14.5 and 14.1 degrees. |
| `roll-drift-keeps-slot` | `ApplyPlayerMotion`, `RotateVectorRollPitch`, `MoveObject`, `OrthogonaliseYVector`, `RenormaliseOrientationVector` | 1,300 | The roll-reversal drift does not turn an active station away from the planet. Start from the launch layout: planet $18000 ahead, station just behind with unit axes and active. Then 20 updates at pitch 8 and the 1,280 alternating-roll updates of `maths/roll-reversal-drift` move the planet 2.29 times further from the view axis. The slot error only changes from 3.5 to 8.6 degrees. Each update runs `MoveSunAndPlanet`, `UpdateStationDormancy` and the slot-0 part of `UpdateObjects` from `L_DB8B` to `L_DBA3`. |

## Differences from the former ad-hoc tests

- Random sample sizes are smaller where the former scripts used tens or
  hundreds of thousands of cases: `DivideWordToFixed` 5,000 (was 300,000),
  `DivideFractionAEB` 5,000 (20,000), the `$E000` arithmetic helpers 3,000 to
  6,000 each (20,000 to 30,000), `ComputeLineDelta` 3,000 (6,000). Exhaustive
  domains are unchanged.
- Results that the former scripts only printed are now asserted: the recorded
  values, or the model stated in the annotation where it holds exactly
  (`DivideRatioByte` has a bit-exact model of its shift and overflow paths).
- The forced Torus jump (formerly a scripted 48K gameplay run with test POKEs)
  is a controlled routine test of `HandleTorusJumpKey`, `ApplyJumpShift` and
  the following `UpdateDust`.
- `FindSystemByName` runs with the galactic chart's cross-hair settings. With
  the image value `CrosshairSize = 0`, `DrawChartCursor` XORs a 256-pixel arm
  through the BASIC area and corrupted the former test's stack (it returned
  unbalanced but happened to reach its sentinel).

Not ported, because they were listings, finders or exploratory surveys rather
than verification: disassembly/xref listing helpers, text dumps, the
`$C2D8..$C6FF` comparison with the 48K tapes, line-clipping statistics,
annotation line-length lint, the JAMESON market search (it found no exact
fluctuation), and the scripted 48K gameplay probes (energy bomb, roll/pitch
copies, unforced J key), which `tools/run_runtime_scenarios.py` and
`tools/trace_xrefs.py` cover at runtime.

## Findings recorded while porting

- `GetVectorMagnitude` is accurate (worst 0.86%) when at least one 16-bit
  coordinate is 256 or more; when all three are below 256 it does not return
  the magnitude (for example `(100,0,0)` gives 51200). The check excludes
  those vectors; the annotation's "accurate to < 1% for |v| >= 256" needs that
  condition.
- `DivideRatioByte`: the dividend-overflow path returns 255 for about half of
  its inputs, so it is "not necessarily saturated" rather than "not
  saturated".
- `AddScaledSignMagnitude` deviates up to 1.22 from its real-valued model
  (the annotation says 1.2).
