; Optional laser=single: final patch in docs/info/ELIT128P_laser_mod-readme.txt.
; DrawLaser has already generated the original endpoint magnitudes in DE
; and endpoint quadrant bits in C. Preserve both, including the random wiggle.
SingleLaser:
    LD HL,SingleLaserStartCoordinates ; packed coordinates, not a memory address
    LD A,C
    OR $03                     ; set only the start-point quadrant bits
    LD C,A
    JP DrawLine                ; one beam; DrawLine returns to DrawLaser's caller
SingleLaserEnd:
defc SingleLaserSize = SingleLaserEnd-SingleLaser
