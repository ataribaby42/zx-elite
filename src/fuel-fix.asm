; Optional repair of the fuel price and the FU gauge: fuelfix=yes.
;
; The original keeps the fuel price (FuelPrice, entry 0 of EquipmentPriceTable)
; and the FU bar value (FuelGauge) outside the saved commander record. Only a
; hyperspace jump, fuel scooping or a fuel purchase rewrite them. After a tape load
; the price and the FU bar keep their previous values: following a reset and
; reload, fuel costs 0.0 and the FU bar is full whatever the loaded fuel. A new
; commander and fuel scooping leave them stale in the same way.
;
; This code recomputes the price from FuelLevel whenever the equipment list is
; shown, with the formula of the original normal jump: 2*economy + (70 - fuel)
; tenths of a credit for the system the ship is docked at, and 0 for a full tank.
; It recomputes the FU bar value from FuelLevel at every launch.
;
; Three macros fill free areas of the original image, which keeps every other
; address unchanged; game.asm expands each one in place of the original bytes:
;   FuelPriceCode    $B31B..$B32A  (16 B, dormant attribute fill)
;   FuelEconomyCode  $A89B..$A8A9  (15 B, dormant JP vectors)
;   FuelStoreCode    $9A3A..$9A45  (12 B, unused bytes before PrepareShipForLaunch)
; EquipShipScreen calls FuelPriceUpdate instead of BeginTradeScreen, and
; LaunchFromStation calls FuelGaugeUpdate instead of PrepareShipForLaunch.

defc FuelTankFull = 70                  ; 7.0 light years, SetFuelLevel's limit
; DeriveSelectedSystemData: economy = s0 high AND 7, with bit 1 forced for
; governments 0 and 1 (anarchy and feudal).
defc EconomyMask = 7
defc EconomyForcedBit = 2
defc EconomyForcedBelowGovernment = 2

; In: nothing.  Out: FuelPrice updated, then BeginTradeScreen.  A, B, HL clobbered.
MACRO FuelPriceCode
assert $-GameImage = FuelPricePartStart-GameLoadAddress
; L alone switches between these three bytes of the commander record.
assert ((FuelLevel-GameImage+GameLoadAddress) >> 8) = ((CurrentGovernment-GameImage+GameLoadAddress) >> 8)
assert ((FuelLevel-GameImage+GameLoadAddress) >> 8) = ((CurrentSystemSeeds+1-GameImage+GameLoadAddress) >> 8)
assert FuelStoreCodeEnd = PrepareShipForLaunch           ; FuelGaugeUpdate falls into it
assert FuelPrice = EquipmentPriceTable+1                 ; entry 0 (fuel), low byte
FuelPriceUpdate:
    LD HL,FuelLevel
    LD A,FuelTankFull
    SUB (HL)                    ; tenths of a light year missing
    JP Z,FuelPriceStore         ; full tank: price 0
    LD B,A
    LD L,CurrentGovernment & $FF
    LD A,(HL)
    JP FuelEconomy
FuelPriceCodeEnd:
assert FuelPriceCodeEnd-FuelPriceUpdate <= FuelPricePartLimit-FuelPricePartStart
    defs (FuelPricePartLimit-FuelPricePartStart)-(FuelPriceCodeEnd-FuelPriceUpdate),0
ENDM

; In: A = CurrentGovernment, B = tenths missing, H = page of the commander record.
MACRO FuelEconomyCode
assert $-GameImage = FuelEconomyPartStart-GameLoadAddress
FuelEconomy:
    CP EconomyForcedBelowGovernment
    SBC A,A
    AND EconomyForcedBit        ; anarchy and feudal force economy bit 1
    LD L,(CurrentSystemSeeds+1) & $FF ; s0 high byte of the current system
    OR (HL)
    AND EconomyMask             ; the economy, as DeriveSelectedSystemData forms it
    ADD A,A
    ADD A,B                     ; 2*economy + tenths missing, as NormalHyperspaceJump
    JP FuelPriceStore
FuelEconomyCodeEnd:
assert FuelEconomyCodeEnd-FuelEconomy <= FuelEconomyPartLimit-FuelEconomyPartStart
    defs (FuelEconomyPartLimit-FuelEconomyPartStart)-(FuelEconomyCodeEnd-FuelEconomy),0
ENDM

; FuelPriceStore ends FuelPriceUpdate.  FuelGaugeUpdate (launch) sets the FU bar
; value from FuelLevel through StoreFuelLevel, which leaves FuelLevel unchanged, and
; falls into PrepareShipForLaunch; A, B and the flags are clobbered.
MACRO FuelStoreCode
assert $-GameImage = FuelStorePartStart-GameLoadAddress
FuelPriceStore:
    LD (FuelPrice),A
    JP BeginTradeScreen
FuelGaugeUpdate:
    LD A,(FuelLevel)
    CALL StoreFuelLevel
FuelStoreCodeEnd:
assert FuelStoreCodeEnd-FuelPriceStore = FuelStorePartLimit-FuelStorePartStart
ENDM
