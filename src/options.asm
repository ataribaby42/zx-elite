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

IFNDEF STATION_SLOT_FIX
    defc STATION_SLOT_FIX = 0
ENDIF
assert STATION_SLOT_FIX = 0 || STATION_SLOT_FIX = 1

; Original fixed boundaries of the four areas that stationslotfix=yes replaces:
; the flag store at the station switch-on and three free areas of the image.
defc StationSwitchOnStoreStart = $77CB
defc StationSwitchOnStoreLimit = $77CE
defc StationSlotAlignStart = $E88B
defc StationSlotAlignLimit = $E8CF
defc StationSlotRoofStart = $AC56
defc StationSlotRoofLimit = $AC77
defc StationSlotFinishStart = $FCED
defc StationSlotFinishLimit = $FD00
IF STATION_SLOT_FIX
    INCLUDE "station-slot-fix.asm"
ENDIF

IFNDEF FUEL_FIX
    defc FUEL_FIX = 0
ENDIF
assert FUEL_FIX = 0 || FUEL_FIX = 1

; Original fixed boundaries of the five areas that fuelfix=yes replaces: two calls
; and three free areas of the image.
defc FuelLaunchHookStart = $7B85                ; CALL PrepareShipForLaunch in LaunchFromStation
defc FuelLaunchHookLimit = $7B88
defc FuelPriceHookStart = $B53F                 ; CALL BeginTradeScreen in EquipShipScreen
defc FuelPriceHookLimit = $B542
defc FuelPricePartStart = $B31B
defc FuelPricePartLimit = $B32B
defc FuelEconomyPartStart = $A89B
defc FuelEconomyPartLimit = $A8AA
defc FuelStorePartStart = $9A3A
defc FuelStorePartLimit = $9A46
IF FUEL_FIX
    INCLUDE "fuel-fix.asm"
ENDIF

IFNDEF HYPERSPACE_DOCKING_FIX
    defc HYPERSPACE_DOCKING_FIX = 0
ENDIF
assert HYPERSPACE_DOCKING_FIX = 0 || HYPERSPACE_DOCKING_FIX = 1

; Original fixed boundaries of the instruction that hyperspacedockingfix=yes replaces:
; CheckDocking's LD A,(HyperspaceKeyLatch) becomes LD A,(JumpTunnelMode).
defc HyperspaceDockingCheckStart = $70BE
defc HyperspaceDockingCheckLimit = $70C1

IFNDEF AI_COURAGE_FIX
    defc AI_COURAGE_FIX = 0
ENDIF
assert AI_COURAGE_FIX = 0 || AI_COURAGE_FIX = 1

; Original fixed boundaries of the courage update in ApplyPlayerLaserHit that
; aicouragefix=yes replaces in place (src/ai-courage-fix.asm).
defc AiCourageHitStart = $EC6A
defc AiCourageHitLimit = $EC7D

IFNDEF SCANNER_BLIP_FIX
    defc SCANNER_BLIP_FIX = 0
ENDIF
assert SCANNER_BLIP_FIX = 0 || SCANNER_BLIP_FIX = 1

; Original fixed boundaries of the three parts of DrawScannerContacts that
; scannerblipfix=yes replaces in place (src/scanner-blip-fix.asm).
defc ScannerBlipStepStart = $8CE0
defc ScannerBlipStepLimit = $8CF3
defc ScannerBlipCentreStart = $8D0B
defc ScannerBlipCentreLimit = $8D0D
defc ScannerBlipGuardStart = $8DCC
defc ScannerBlipGuardLimit = $8DDE
IF SCANNER_BLIP_FIX
    INCLUDE "scanner-blip-fix.asm"
ENDIF

IFNDEF STARDUST_FIX
    defc STARDUST_FIX = 0
ENDIF
assert STARDUST_FIX = 0 || STARDUST_FIX = 1

; Original fixed boundaries of GetDustPixelAddress, which stardustfix=yes replaces
; in place (src/stardust-fix.asm).
defc StardustPixelStart = $A2EF
defc StardustPixelLimit = $A334
IF STARDUST_FIX
    INCLUDE "stardust-fix.asm"
ENDIF

IFNDEF MISSILE_TARGET_FIX
    defc MISSILE_TARGET_FIX = 0
ENDIF
assert MISSILE_TARGET_FIX = 0 || MISSILE_TARGET_FIX = 1

; Original fixed boundaries of the missile test in ReleaseTargetLocks that
; missiletargetfix=yes replaces: BIT 0,(IX+$26), which tests the removed object,
; becomes BIT 0,(IY+$26), which tests the slot being scanned.
defc MissileTargetCheckStart = $EB82
defc MissileTargetCheckLimit = $EB86

IFNDEF TEXT_FULL_STOP_FIX
    defc TEXT_FULL_STOP_FIX = 0
ENDIF
assert TEXT_FULL_STOP_FIX = 0 || TEXT_FULL_STOP_FIX = 1

; Original fixed boundaries of the two parts that textfullstopfix=yes replaces
; (src/text-full-stop-fix.asm): the start of BufferJustifiedCharacter, and the zero
; padding before the page-aligned square tables.
defc TextFullStopBufferStart = $BCFC
defc TextFullStopBufferLimit = $BD1B
defc TextFullStopHookStart = $BDF5
defc TextFullStopHookLimit = $BE00
IF TEXT_FULL_STOP_FIX
    INCLUDE "text-full-stop-fix.asm"
ENDIF

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
