# Emulator patches

POK files target only the unmodified original 128K-compatible release in
`assets/Elite - 128k.tap`. Dedicated generation scripts in `tools/` are not
created or maintained; the POK files themselves are the deliverables.

## Elite128-scanner-pixel-fix.pok

Target: the unmodified `assets/Elite - 128k.tap` reference, SHA-256
`d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6`.
This is the 128K-compatible release of the 48K program. Run it in **ZX
Spectrum 48K mode**. This patch is not verified for the older 48K release.

1. Load the original game completely and remain docked on the status screen.
2. Pause emulation and import this POK file using the emulator's POKE/trainer
   facility. Enable the single entry, `Scanner pixel fix (Elite128)`.
3. Resume and launch. The ECM indicator now preserves the scanner pixel,
   whether ECM is active or inactive.

Apply the complete patch once while paused and docked, never partway through
drawing an in-flight frame. Do not apply it during tape loading: the loader
would overwrite it. If the pixel was already erased in an earlier flight,
redraw the cockpit before checking it; the fix preserves the current bit
rather than forcing it on. Reload the original tape to return to original
code. The POK also includes original values for emulator undo support.

Only the scanner fix is included: no Adder replacement, single laser, font
change, commander edits or one-off screen POKE. It uses the existing 166-byte
instrument region and updates its two missile-display callers. No extra RAM.
Do not combine it with other patches that replace the same code.

Verification: all 159 original values were checked against the reference and
against the live, ROM-loaded game while docked. After applying the exported
POK, a 28-second 48K emulator run completed the first launch and ECM off/on/off
states. All 95 inactive and 21 active ECM writes preserved the scanner bit.
The resulting game bytes also match the independently assembled scanner-only
build exactly. This is not a test of any particular emulator's POK import UI.

The ASCII file uses bank 8 (unpaged 48K addressing), decimal values and the
standard N/M/Z/Y records described in the
[POK format specification](https://worldofspectrum.org/faq/reference/formats.htm).
The format cannot distinguish a literal original zero from an unspecified
undo byte, so reloading the original tape is the reliable way to undo it if
the emulator has not retained the pre-patch memory.
