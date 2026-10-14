; Original text control-code handler pointers, read by DispatchMessageControl ($B89A)
; and DispatchTokenControl ($B89F).  Entry n handles control code n.
; assets/Elite - 128k.tap, block 5, load $6048, SHA256 d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
TokenControlTable:
    defw IgnoreTextControl                ; code 0
    defw PrintGalaxyNumber                ; code 1
    defw PrintPresentSystemName           ; code 2
    defw PrintSelectedSystemName          ; code 3
    defw PrintCommanderName               ; code 4
    defw PrintFuelLine                    ; code 5
    defw SetCapitals                      ; code 6
    defw PrintCashLine                    ; code 7
    defw SetTitleCase                     ; code 8
    defw NewLine                          ; code 9
    defw SelectMessageMode                ; code 10
    defw PrintGalaxyFirstSystemName       ; code 11
    defw IgnoreTextControl                ; code 12
    defw IgnoreTextControl                ; code 13
TokenControlTableEnd:
defc TokenControlTableSize = TokenControlTableEnd-TokenControlTable
assert TokenControlTableSize = 28
