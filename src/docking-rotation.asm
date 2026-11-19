; dockingrotation=yes: require the rectangular slot's long axis to be horizontal.
; ZX Coriolis vertices 12..15 have |x|=10, |y|=30, z=160: local Y is the long
; axis. Its x component must have magnitude >=106/127 (about 33 degrees).
; Evidence and tests: docs/DOCKING-ROTATION.md; tools/check_docking_rotation.py.
; The 18-byte helper uses only the optimized rotation fix's three padding gaps.

defc DockingRotationRoofXHigh = InstanceAxisY+1
defc DockingRotationMinimum = 106
assert DockingRotationMinimum > 0 && DockingRotationMinimum < 128

MACRO DockingRotationHookCode
    CALL DockingRotationCheck
    JR C,L_EB10                 ; original station scrape: sound and front damage
    RET                         ; success already set DockingContactFlag to 1
ENDM

MACRO DockingRotationLoadCode
    assert $-GameImage = DockingRotationLoadStart-GameLoadAddress
DockingRotationCheck:
    LD A,(IX+DockingRotationRoofXHigh)
    JR DockingRotationCompare
    assert $-GameImage = DockingRotationLoadLimit-GameLoadAddress
ENDM

MACRO DockingRotationCompareCode
    assert $-GameImage = DockingRotationCompareStart-GameLoadAddress
DockingRotationCompare:
    ADD A,A                     ; discard sign: 0 and 180 degrees both fit
    CP 2*DockingRotationMinimum
    RET C                       ; carry set: caller takes the scrape path
    JP DockingRotationAccept
DockingRotationCompareCodeEnd:
    assert $-GameImage <= DockingRotationCompareLimit-GameLoadAddress
    defs (DockingRotationCompareLimit-GameLoadAddress)-($-GameImage),0
ENDM

MACRO DockingRotationAcceptCode
    assert $-GameImage = DockingRotationAcceptStart-GameLoadAddress
DockingRotationAccept:
    LD A,1
    LD (DockingContactFlag),A
    RET                         ; carry remains clear from the comparison
    assert $-GameImage = DockingRotationAcceptLimit-GameLoadAddress
ENDM
