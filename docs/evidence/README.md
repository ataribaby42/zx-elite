# Historical investigation evidence

These small reports are retained from one-off ZX Spectrum 48K investigations.
They are historical evidence, not claims about the latest build and not
automatically regenerated test results. Keep them when cleaning `build/`.

- `attribute-runtime.json`: controlled execution of the original attribute
  writers, showing direct screen updates and updates to the saved cockpit
  colour buffer. See [Graphics](../GRAPHICS.md).
- `station-fix-verification.json`: the Adder station-pointer correction,
  including the historical before/after TAP hashes, changed address and
  rear-view pixel comparison. The current station-pointer checks are maintained
  in `tools/check_ship_variant.py` and `tools/emulator_check.py`.

Repeatable build, graphics, ship, laser and emulator results remain disposable
outputs in `build/`. Maintained source, data definitions and documentation
live outside that directory.
