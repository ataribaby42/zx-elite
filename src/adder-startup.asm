; Relocated original $716B..$7188, used ONLY on the initial entry from BASIC.
; Font/attribute source reads do not touch this code. Jump back before any
; drawing or clearing can reuse the $C000..$CFFF graphics buffers.
AdderStartup:
    LD HL,FontBitmap
    LD DE,FontRuntime
    LD BC,FontBitmapSize
    LDIR
    LD HL,CockpitAttributes
    LD DE,CockpitAttributesRuntime
    LD BC,CockpitAttributesSize
    LDIR
AdderStartupAfterGraphicsCopy:
    CALL L_FF4C
    EI
    LD (L_74B2),SP
AdderStartupResumeJump:
    JP ContinueStartup
AdderStartupEnd:
assert AdderStartup-GameImage = VariantStartupStorage-GameLoadAddress
assert AdderStartupEnd-GameImage <= VariantStartupLimit-GameLoadAddress
