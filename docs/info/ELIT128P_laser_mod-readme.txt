The real laser drawing code is around 0xECD4–0xED21. The original code makes several calls to the line routine at 0xEE10, which creates the double left/right laser beams.

I patched it to one single centered beam:

ECF2: LD HL,$003F
ECF5: LD DE,$0000
ECF8: LD C,$0B
ECFA: JP $EE10

This draws one vertical/center laser from the bottom middle of the front window to the crosshair. TAP checksum is recalculated.

Keep random wiggle at end of laser beam inside crosshair as it was before.

Done — I changed the patch so the laser still starts from the bottom middle, but now it keeps the original random endpoint wiggle near the crosshair.

Patch now uses the original random DE and original random quadrant bits from C:

ECF2: LD HL,$003F      ; bottom-middle start
ECF5: LD A,C           ; keep original random bits
ECF6: OR $03
ECF8: LD C,A
ECF9: JP $EE10         ; draw one beam