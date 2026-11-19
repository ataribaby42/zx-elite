; competitionremove=yes: skip the post-save security number, keeping the
; record, COMMANDER SAVED message and restart snapshot. Rotation drift repair
; may use these reclaimed bytes; otherwise they remain zero-filled space.
MACRO CompetitionSecurityCode
IF ROTATION_DRIFT_FIX
    RotationDriftSecurityCode
ELSE
    JR CopyCommanderToTemplate
CompetitionSecurityFreeSpace:
    assert $-GameImage <= CompetitionSecurityLimit-GameLoadAddress
    defs (CompetitionSecurityLimit-GameLoadAddress)-($-GameImage),0
ENDIF
ENDM

MACRO CompetitionParitySpace
IF ROTATION_DRIFT_FIX
    RotationDriftParitySpace
ELSE
CompetitionParityFreeSpace:
    defs CompetitionParityLimit-CompetitionParityStart,0
ENDIF
ENDM
