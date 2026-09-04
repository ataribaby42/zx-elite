; Extracted from assets/Elite+48K+fixed+B+-+Adder.tap; TAP data block 2, load $4000.
; TAP SHA256: 5f7f213b1bb333543f05abc125ea601f433cc80b445fd0d6c007ff7edd028239
; Slot 17 replacement: original Adder with duplicate face normals shared.
; Original faces 6/7/8 are identical; their references now use face 6.
; Geometry offsets/counts are derived by the assembler.
ShipAdderBlueprint:
    defb 0 ; canister/commodity flags
    defb 50 ; target size
    defb 100 ; agility / rotation limit
    defb (ShipAdderVerticesEnd-ShipAdderVertices)/6
    defb (ShipAdderEdgesEnd-ShipAdderEdges)/4
    defb (ShipAdderFacesEnd-ShipAdderFaces)/4
    defb 24 ; maximum speed
    defb 85 ; energy
    defw 40 ; bounty in tenths of a credit
    defb $01 ; partially decoded property
    defb 20 ; visibility distance
    defw ShipAdderVertices-ShipAdderBlueprint
    defw ShipAdderEdges-ShipAdderBlueprint
    defw ShipAdderFaces-ShipAdderBlueprint
    defb $8C ; behavior flags
    defb $02 ; byte 19
    defb $00 ; gun vertex
    defb $10 ; byte 21
    defb $01 ; normal scale
assert $-ShipAdderBlueprint = 23
ShipAdderVertices:
    defb $12,$00,$28,$9F,$01,$9A
    defb $12,$00,$28,$1F,$01,$23
    defb $1E,$00,$18,$3F,$23,$45
    defb $1E,$00,$28,$3F,$45,$66
    defb $12,$07,$28,$7F,$56,$6C
    defb $12,$07,$28,$FF,$66,$8C
    defb $1E,$00,$28,$BF,$67,$88
    defb $1E,$00,$18,$BF,$78,$9A
    defb $12,$07,$28,$BF,$66,$7B
    defb $12,$07,$28,$3F,$46,$6B
    defb $12,$07,$0D,$9F,$07,$9B
    defb $12,$07,$0D,$1F,$02,$4B
    defb $12,$07,$0D,$DF,$18,$AC
    defb $12,$07,$0D,$5F,$13,$5C
    defb $0B,$03,$1D,$85,$00,$00
    defb $0B,$03,$1D,$05,$00,$00
    defb $0B,$04,$18,$04,$00,$00
    defb $0B,$04,$18,$84,$00,$00
ShipAdderVerticesEnd:
assert (ShipAdderVerticesEnd-ShipAdderVertices) % 6 = 0
ShipAdderEdges:
    defb $1F,$00,$01,$01
    defb $07,$01,$02,$23
    defb $1F,$02,$03,$45
    defb $1F,$03,$04,$56
    defb $1F,$04,$05,$6C
    defb $1F,$05,$06,$68
    defb $1F,$06,$07,$78
    defb $07,$07,$00,$9A
    defb $1F,$03,$09,$46
    defb $1F,$09,$08,$6B
    defb $1F,$08,$06,$67
    defb $1F,$00,$0A,$09
    defb $1F,$07,$0A,$79
    defb $1F,$01,$0B,$02
    defb $1F,$02,$0B,$24
    defb $1F,$00,$0C,$1A
    defb $1F,$07,$0C,$8A
    defb $1F,$01,$0D,$13
    defb $1F,$02,$0D,$35
    defb $1F,$0A,$0B,$0B
    defb $1F,$0C,$0D,$1C
    defb $1F,$08,$0A,$7B
    defb $1F,$09,$0B,$4B
    defb $1F,$05,$0C,$8C
    defb $1F,$04,$0D,$5C
    defb $05,$0E,$0F,$00
    defb $03,$0F,$10,$00
    defb $04,$10,$11,$00
    defb $03,$11,$0E,$00
ShipAdderEdgesEnd:
assert (ShipAdderEdgesEnd-ShipAdderEdges) % 4 = 0
ShipAdderFaces:
    defb $00,$27,$0A,$1F
    defb $00,$27,$0A,$5F
    defb $45,$32,$0D,$1F
    defb $45,$32,$0D,$5F
    defb $1E,$34,$00,$1F
    defb $1E,$34,$00,$5F
    defb $00,$00,$A0,$3F
    defb $1E,$34,$00,$9F
    defb $1E,$34,$00,$DF
    defb $45,$32,$0D,$9F
    defb $45,$32,$0D,$DF
    defb $00,$1C,$00,$1F
    defb $00,$1C,$00,$5F
ShipAdderFacesEnd:
assert (ShipAdderFacesEnd-ShipAdderFaces) % 4 = 0
ShipAdderBlueprintEnd:
assert ShipAdderBlueprintEnd-ShipAdderBlueprint = 299
