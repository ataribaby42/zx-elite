; Optional repair of the AI courage counter: aicouragefix=yes.
;
; ApplyPlayerLaserHit lowers the courage in bits 0..6 of InstanceAiState (+$25) by
; 14 per hit, with a floor of 6 that keeps the ECM bit 0, and it keeps the fleeing
; bit 7.  The original subtracts from the whole byte, so the floor only applies
; while bit 7 is clear.  For a fleeing ship a courage below 14 wraps to 114..127:
; the ship turns back towards the player at full acceleration, never fires again
; (ApplySteeringVector returns before TryFireAiLaser while bit 7 is set), and
; seldom bails out, because the escape test compares a random byte with +$25.
;
; This replacement subtracts from bits 0..6 alone, working on the byte shifted
; left so that the fleeing bit drops out, and puts bit 7 back afterwards.  A
; frightened ship therefore stays at courage 6 or 7 and keeps fleeing.  For a
; byte below $80 (ships that do not flee, missile target codes) A, B and +$25
; end exactly as in the original.  It fills the original 19 bytes at $EC6A.

defc AiCourageLossPerHit = 14
defc AiCourageFloor = 6

assert $-GameImage = AiCourageHitStart-GameLoadAddress
    LD A,(IX+InstanceAiState)
    LD B,A
    ADD A,A                     ; courage * 2: the fleeing bit leaves A
    SUB 2*AiCourageLossPerHit
    JR NC,AiCourageLowered
    AND 2                       ; the ECM bit, shifted to bit 1
    ADD A,2*AiCourageFloor
AiCourageLowered:
    SLA B                       ; carry = the old fleeing bit
    RRA                         ; bits 0..6 = new courage, bit 7 = fleeing bit
    LD (IX+InstanceAiState),A
AiCourageHitEnd:
assert AiCourageHitEnd-GameImage = AiCourageHitLimit-GameLoadAddress
