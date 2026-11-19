; trafficcontrol=yes: suppress calm station traders inside the 1024-unit box
; while S is lit. Police and special-mode launches bypass this hook.
; Evidence, reachable-state invariants and tests: docs/TRAFFIC-CONTROL.md.
;
; An active station has zero upper magnitude bytes: UpdateStationDormancy checks
; all three before activation; MoveObject removes out-of-range objects before
; their next AI pass. Station speed is zero. Thus the three middle bytes suffice
; for the exact Chebyshev comparison at this call site (signs do not matter).
defc TrafficControlDistance = $0400
defc TrafficControlCoarseLimit = TrafficControlDistance >> 8
assert TrafficControlCoarseLimit > 0 && TrafficControlCoarseLimit < 256
assert TrafficControlDistance = 256*TrafficControlCoarseLimit
assert (TrafficControlCoarseLimit & (TrafficControlCoarseLimit-1)) = 0

MACRO TrafficControlHookCode
    CP 2
    RET NC                              ; original random gate, no extra cycles
    JR TrafficControlDistanceCheck
ENDM

MACRO TrafficControlXYCode
TrafficControlXY:
    OR (IX+InstanceX+1)
    OR (IX+InstanceY+1)
    RET
ENDM

MACRO TrafficControlZCode
TrafficControlZ:
    OR (IX+InstanceZ+1)
    CP TrafficControlCoarseLimit         ; carry: all three magnitudes < 1024
    RET
ENDM

MACRO TrafficControlProximityCode
    ; Both existing callers set E=0 (DE=$0200 or $0A00). Their 16-bit tests
    ; therefore depend only on the middle bytes. They consume only carry and D;
    ; A/HL are dead at each continuation. Preserve the original z allowance.
    LD A,(IX+InstanceX+1)
    CP D
    RET NC
    LD A,(IX+InstanceY+1)
    CP D
    RET NC
    INC D
    INC D
    LD A,(IX+InstanceZ+1)
    CP D
    RET
TrafficControlProximityEnd:

TrafficControlDistanceCheck:
    LD A,(StationPresent)                ; verified boolean 0/1
    DEC A                               ; S off -> $FF forces the outside path
    CALL TrafficControlXY
    CALL TrafficControlZ
    RET C                               ; S on and inside: suppress this attempt
    LD A,$24                            ; original trader event, subtype 2
    JR DispatchShipEventPreservingParent
ENDM
