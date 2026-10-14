; Original text control-code handler pointers, read by DispatchMessageControl ($B89A)
; and DispatchTokenControl ($B89F).  Entry n handles control code n.
; assets/Elite - 128k.tap, block 5, load $6048, SHA256 d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
MessageControlTable:
    defw IgnoreTextControl                ; code 0
    defw SetCapitals                      ; code 1
    defw SetTitleCase                     ; code 2
    defw PrintSelectedSystemName          ; code 3
    defw PrintCommanderName               ; code 4
    defw SelectMessageMode                ; code 5
    defw SelectTokenMode                  ; code 6
    defw BeepIfSoundOn                    ; code 7
    defw SetColumn4Capital                ; code 8
    defw ClearScreenAndFrame              ; code 9
    defw NextTextRow                      ; code 10
    defw DrawTitleUnderline               ; code 11
    defw NewLine                          ; code 12
    defw SetLowerCase                     ; code 13
    defw StartJustifiedText               ; code 14
    defw EndJustifiedText                 ; code 15
    defw PrintGalaxyFirstSystemName       ; code 16
    defw PrintSelectedSystemAdjective     ; code 17
    defw PrintRandomName                  ; code 18
    defw CapitaliseNextLetter             ; code 19
    defw IgnoreTextControl                ; code 20
    defw ClearPromptLines                 ; code 21
    defw Wait20Frames                     ; code 22
    defw SetTextRow10                     ; code 23
    defw Wait36Frames                     ; code 24
    defw PrintEmptyMessageAndWait         ; code 25
    defw IgnoreTextControl                ; code 26
    defw IgnoreTextControl                ; code 27
    defw IgnoreTextControl                ; code 28
    defw SetTextRow6                      ; code 29
    defw IgnoreTextControl                ; code 30
    defw IgnoreTextControl                ; code 31
MessageControlTableEnd:
defc MessageControlTableSize = MessageControlTableEnd-MessageControlTable
assert MessageControlTableSize = 64
    defb 0 ; original trailing byte
