; Build-time modification switches. The default reconstructs the original tape.
; Fixed machine memory-map boundary, not an address of a relocatable routine.
defc GameLoadAddress = $6048
IFNDEF SHIP_ADDER
    defc SHIP_ADDER = 0
ENDIF
assert SHIP_ADDER = 0 || SHIP_ADDER = 1

IFNDEF LASER_SINGLE
    defc LASER_SINGLE = 0
ENDIF
assert LASER_SINGLE = 0 || LASER_SINGLE = 1

IFNDEF FONT_48
    defc FONT_48 = 0
ENDIF
assert FONT_48 = 0 || FONT_48 = 1

IFNDEF FONT_128FIX
    defc FONT_128FIX = 0
ENDIF
assert FONT_128FIX = 0 || FONT_128FIX = 1
IFNDEF FONT_128FIX_ECM_S
    defc FONT_128FIX_ECM_S = 0
ENDIF
assert FONT_128FIX_ECM_S = 0 || FONT_128FIX_ECM_S = 1
assert FONT_48 + FONT_128FIX + FONT_128FIX_ECM_S <= 1

IFNDEF SCANNER_PIXEL_FIX
    defc SCANNER_PIXEL_FIX = 0
ENDIF
assert SCANNER_PIXEL_FIX = 0 || SCANNER_PIXEL_FIX = 1

IFNDEF STATION_RANDOM_LAUNCH_FIX
    defc STATION_RANDOM_LAUNCH_FIX = 0
ENDIF
assert STATION_RANDOM_LAUNCH_FIX = 0 || STATION_RANDOM_LAUNCH_FIX = 1

; Original fixed boundaries of the shared parent-ship launch selector.
defc ParentLaunchSelectionStart = $F44A
defc ParentLaunchSelectionLimit = $F470

; Original, fixed boundaries of the instrument drawing code being replaced.
defc CockpitIndicatorsStart = $A660
defc CockpitIndicatorsLimit = $A706
defc ScannerEcmOverlap = $50C9
; Fixed screen-cell locations and packed text coordinates, not code pointers.
defc EncounterCircleTop = $5029
defc EncounterCircleBottom = EncounterCircleTop+32
defc EcmIndicatorTop = ScannerEcmOverlap-1
defc StationIndicatorTop = $50D6
defc MissileDisplayCoordinates = (23 << 8) | 2
defc SingleLaserStartCoordinates = $003F

; Startup-only storage, before the $C000 graphics buffer is first reused.
defc VariantStartupStorage = $C600
defc VariantStartupLimit = $C640
