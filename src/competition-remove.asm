; competitionremove=yes: skip the post-save security number, keeping the
; record, COMMANDER SAVED message and restart snapshot. Rotation drift repair
; and docking alignment may use these bytes; the remainder stays zero-filled.
MACRO CompetitionSecurityCode
IF ROTATION_DRIFT_FIX
    RotationDriftSecurityCode
ELSE
    JR CopyCommanderToTemplate
IF DOCKING_ROTATION
    DockingRotationAcceptCode
    assert $-GameImage <= DockingRotationLoadStart-GameLoadAddress
    defs (DockingRotationLoadStart-GameLoadAddress)-($-GameImage),0
    DockingRotationLoadCode
ENDIF
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
IF DOCKING_ROTATION
    defs (DockingRotationCompareStart-GameLoadAddress)-($-GameImage),0
    DockingRotationCompareCode
ENDIF
    assert $-GameImage <= CompetitionParityLimit-GameLoadAddress
    defs (CompetitionParityLimit-GameLoadAddress)-($-GameImage),0
ENDIF
ENDM
