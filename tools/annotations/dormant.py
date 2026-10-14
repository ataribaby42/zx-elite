"""Dormant code left in the reference image (never referenced or executed).

The block at $C350..$C40B lies in the area that the game later overwrites as
the view bitmap buffer.  No instruction of the game refers to it and no 48K
trace executes it, but its structure proves that it is code: the prologue
relocates exactly the operands of its nine CALL instructions.  Its operands
are emitted symbolically so that the block stays self-consistent if moved.
"""

SEEDS = {
    0xC350: 'self-relocating loader: its prologue patches exactly the nine CALL operands of this block',
    0xC3EE: 'byte receiver: target of the nine relocated CALLs of DormantPortLoader',
}

# The prologue computes BC + offset for each CALL operand (BC = own address,
# the BASIC USR convention) and stores BC + (receiver - loader) there.
OPERANDS = {
    0xC350: 'DormantPortReceiveByte-DormantPortLoader',
    0xC355: 'L_C3A3+1-DormantPortLoader',
    0xC35C: 'L_C3AB+1-DormantPortLoader',
    0xC363: 'L_C3AF+1-DormantPortLoader',
    0xC36A: 'L_C3B3+1-DormantPortLoader',
    0xC371: 'L_C3B7+1-DormantPortLoader',
    0xC378: 'L_C3BB+1-DormantPortLoader',
    0xC37F: 'L_C3BF+1-DormantPortLoader',
    0xC386: 'L_C3C8+1-DormantPortLoader',
    0xC38D: 'L_C3D5+1-DormantPortLoader',
}

COMMENTS = {
    0xC350: 'DE = own address + receiver offset (BC = own address)',
    0xC355: 'patch the operand of each CALL DormantPortReceiveByte',
    0xC394: 'set up the external interface ports',
    0xC3A3: 'wait for the header sync byte',
    0xC3A7: "'-'",
    0xC3AB: 'destination address -> HL',
    0xC3B3: 'length -> BC',
    0xC3BB: 'execution address -> stack',
    0xC3C6: 'checksum starts at $FF',
    0xC3C8: 'receive the block, adding each byte to D',
    0xC3D5: 'check byte',
    0xC3DA: 'checksum matches: RET to the pushed execution address',
    0xC3DB: 'error: flash the border until a key is pressed',
    0xC3EB: 'discard the execution address and wait for a new header',
    0xC3EE: 'handshake low',
    0xC3F7: 'data byte',
    0xC3FA: 'handshake high',
    0xC404: 'border stripes from the length counter',
}

ASSERTS = {
    'dormant-call-offsets': ('L_C3D5+1-DormantPortLoader = $86',
                             'last patched CALL operand of the dormant loader'),
}
