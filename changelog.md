# Changelog

ZX Spectrum Elite 128k source reconstruction

## 19.11.2026 V1.4

- compassflickerfix prevents the compass dot from flickering when the scanner redraws contacts, including after returning from a chart.
- competitionremove – removes the competition number after saving; automatically enabled by rotationdriftfix and dockingrotation.
- rotationdriftfix – fixes planet and sun drift during rotation, optimized without additional memory.
- dockingrotation – checks the player’s rotational alignment with the station’s docking slot.
- trafficcontrol – suppresses Cobra/Python launches while S is active and Chebyshev distance from the station’s centre is < 1024; Vipers remain unrestricted.
- Fixed review findings, expanded regression tests and improved build failure handling.

## 16.10.2026 V1.3

- I.F.F. unit option; replaces the energy bomb and its W key, threats blink on the scanner
- Randomized spawn option; a lone encounter ship appears ahead or in a corner at random, so its position no longer reveals a threat

## 15.10.2026 V1.2

- Station slot fix; docking slot faces the planet when the station appears
- Fuel fix; correct fuel price and FU bar after loading a commander
- Hyperspace docking fix; a refused H or G press no longer blocks docking
- AI courage fix; a fleeing ship stays frightened instead of charging back
- Scanner blip fix; no one-pixel hop at dx = 4, sticks stop at the scanner
- Stardust fix; no dust on or outside the view frame
- Missile target fix; a missile explodes when its target disappears
- Text full stop fix; full stop no longer lost at the end of a justified line

## 8.10.2026 V1.1

- Added all font variations
- Added all original laser variations

## 20.9.2026 V1.0

- Single beam laser option.
- Scanner pixel fix
- Station randomlaunch fix; enables trader Python or Cobra Mk. III to be randomly launched from sation 