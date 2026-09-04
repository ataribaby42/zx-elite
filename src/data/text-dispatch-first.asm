; Original text/control-token handler pointers, read by $B89A/$B89F.
; assets/Elite - 128k.tap, block 5, load $6048, SHA256 d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
L_6FA3:
    defw L_B916
    defw L_B8DD
    defw L_B8FC
    defw L_B904
    defw L_B8C0
    defw L_B8C9
    defw L_B940
    defw L_B8B4
    defw L_B8C5
    defw L_AFFA
    defw L_B977
    defw L_B8E9
    defw L_B916
    defw L_B916
L_6FA3End:
defc L_6FA3Size = L_6FA3End-L_6FA3
assert L_6FA3Size = 28
