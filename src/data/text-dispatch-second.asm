; Original text/control-token handler pointers, read by $B89A/$B89F.
; assets/Elite - 128k.tap, block 5, load $6048, SHA256 d9013872555f448308e0b8a69b624600335384cd38911165bde74a9d11de84d6
L_6FBF:
    defw L_B916
    defw L_B940
    defw L_B8C5
    defw L_B904
    defw L_B8C0
    defw L_B977
    defw L_B97B
    defw L_AF39
    defw L_B90D
    defw L_BC9E
    defw L_B002
    defw L_BBD3
    defw L_AFFA
    defw L_B93B
    defw L_BD9D
    defw L_BDB9
    defw L_B8E9
    defw L_B946
    defw L_B917
    defw L_B911
    defw L_B916
    defw L_B0BC
    defw L_B0AB
    defw L_B985
    defw L_B0AF
    defw L_B8AC
    defw L_B916
    defw L_B916
    defw L_B916
    defw L_B981
    defw L_B916
    defw L_B916
L_6FBFEnd:
defc L_6FBFSize = L_6FBFEnd-L_6FBF
assert L_6FBFSize = 64
    defb 0 ; original trailing byte
