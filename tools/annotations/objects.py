"""Object instances: the 8 x 39-byte slot array at $6048 and its field offsets.

Evidence: InitialiseShipFromBlueprint ($F2FB) copies the 31-byte default
template ShipInstanceTemplate ($F2A1) into a new instance and then fills energy, behaviour,
payload, speed and random coordinates from the blueprint; FindFreeShipSlot
scans six 39-byte slots after slot 0; the initial station slot holds the
Coriolis blueprint pointer, 240 energy and an identity orientation; the
player-missile energy is slot 7 offset $22.  Field meanings that are not
proved by these sources are left out of FIELDS.

The Blueprint* constants name the 23-byte header fields, each proved by the
instructions that read it (docs/SHIPS.md lists them).  The tools/check_routines.py
group 'structures' runs those readers, the +$20 explosion states and the
+$1D/+$1E rotation counters in the simulator.  docs/DATA-STRUCTURES.md has the
bit-level instance layout.
"""

FIELDS = {
    'InstanceSize': (39, 'bytes per object instance slot'),
    'InstanceSlotCount': (8, 'slot 0 station, 1..6 allocatable, 7 missile/title'),
    'InstanceX': (0x00, 'x: 24-bit sign-magnitude, sign = bit 7 of +2'),
    'InstanceY': (0x03, 'y: same format'),
    'InstanceZ': (0x06, 'z: same format; depth in the front view'),
    'InstanceAxisZ': (0x09, 'local z (nose) axis: 3 words, $7FFF = 1.0'),
    'InstanceAxisY': (0x0F, 'local y (roof) axis, same format'),
    'InstanceAxisX': (0x15, 'local x (side) axis; renderer rebuilds Y x Z'),
    'InstanceSpeed': (0x1B, 'speed; starts at half the blueprint maximum'),
    'InstanceAcceleration': (0x1C, 'signed speed change per move (AI command)'),
    'InstanceExplosionDisc': (0x1C, 'destroyed: disc x, y, flags, radius (+$1C..+$1F)'),
    'InstanceRoll': (0x1D, 'roll: bits 0..3 steps left, 6 sign, 7 endless'),
    'InstancePitch': (0x1E, 'pitch steps, same format as InstanceRoll'),
    'InstanceFlags': (0x20, 'bits 0..2 payload, 3 fired, 4/5 explosion, 6 AI, 7 pod'),
    'InstanceBehaviour': (0x21, 'blueprint +$12 AND $6F; bit 2 hostile'),
    'InstanceEnergy': (0x22, 'energy; zero marks a free slot'),
    'InstanceAiState': (0x25, 'ship: bit 0 ECM, bits 1..6 courage counter (-14 per hit), 7 fleeing; missile: target'),
    'InstanceRoleFlags': (0x26, 'bit 0 missile, 1 scoopable, 2 station, 3 passive...'),
    'InstanceBlueprint': (0x23, 'pointer to the 23-byte blueprint header'),
    'InstanceTemplateSize': (0x1F, 'bytes +$00..+$1E copied from ShipInstanceTemplate'),
    'BlueprintHeaderSize': (23, 'bytes in a blueprint header'),
    'BlueprintCargo': (0x00, 'scooped commodity - 1 (high), canister (low)'),
    'BlueprintRadius': (0x01, 'near limit, target size and collision box'),
    'BlueprintLaserChance': (0x02, 'AI fire chance in 256, halved below 256 kills'),
    'BlueprintVertexCount': (0x03, 'vertex count'),
    'BlueprintEdgeCount': (0x04, 'edge count'),
    'BlueprintFaceCount': (0x05, 'face count (0: no face table)'),
    'BlueprintMaximumSpeed': (0x06, 'maximum speed'),
    'BlueprintEnergy': (0x07, 'energy: initial value and regeneration limit'),
    'BlueprintBounty': (0x08, 'bounty word in tenths of a credit'),
    'BlueprintPayload': (0x0A, 'bits 0..2 payload count, bits 4..7 launch type'),
    'BlueprintDotDistance': (0x0B, 'wireframe while the depth high byte is lower'),
    'BlueprintVertexTable': (0x0C, 'vertex table offset from the header'),
    'BlueprintEdgeTable': (0x0E, 'edge table offset from the header'),
    'BlueprintFaceTable': (0x10, 'face table offset from the header (0: none)'),
    'BlueprintBehaviour': (0x12, 'behaviour flags; AND $6F gives instance +$21'),
    'BlueprintNormalShift': (0x13, 'normal scale shift n: normals x 2/2^n'),
    'BlueprintGunVertex': (0x14, 'vertex where AI laser beams start'),
    'BlueprintCombatScore': (0x15, 'award word; half is added to the combat score'),
}

LABELS = {
    0x6048 + 1 * 39: ('ObjectSlot1', 'verified', """
Object instance slot 1, the first of six allocatable slots scanned by
FindFreeShipSlot.  Each slot has the InstanceSize layout described by the
Instance* field constants."""),
    0x6048 + 2 * 39: ('ObjectSlot2', 'verified', 'Object instance slot 2.'),
    0x6048 + 3 * 39: ('ObjectSlot3', 'verified', 'Object instance slot 3.'),
    0x6048 + 4 * 39: ('ObjectSlot4', 'verified', 'Object instance slot 4.'),
    0x6048 + 5 * 39: ('ObjectSlot5', 'verified', 'Object instance slot 5.'),
    0x6048 + 6 * 39: ('ObjectSlot6', 'verified', 'Object instance slot 6, the last allocatable slot.'),
    0x6048 + 7 * 39: ('ObjectSlot7', 'verified', """
Object instance slot 7, outside the six allocatable slots.  Used for the
player's missile in flight (PlayerMissileEnergy is its energy byte) and
reused by the title display."""),

}

COMMENTS = {
    0x6048: 'slot 0 (station): x = 0',
    0x6048 + 0x03: 'y = 0',
    0x6048 + 0x06: 'z = +$0300',
    0x6048 + 0x09: 'z axis = (0, 0, +1) ($7FFF = 1.0)',
    0x6048 + 0x0F: 'y axis = (0, +1, 0)',
    0x6048 + 0x15: 'x axis = (+1, 0, 0)',
    0x6048 + 0x1B: 'speed 0, acceleration 0',
    0x6048 + 0x1D: 'roll $C0: endless, negative direction',
    0x6048 + 0x1E: 'pitch 0; +$1F is used only after destruction',
    0x6048 + 0x20: 'flags $40: AI active and counted, no payload',
    0x6048 + 0x21: 'behaviour 0: calm (bit 2 makes the station hostile)',
    0x6048 + 0x22: 'energy 240',
    0x6048 + 0x25: '+$25 = $7F: bit 0 ECM fitted',
    0x6048 + 0x26: '+$26 = $0C: station, passive; bit 7 = destroyed (station mission)',
    0x6048 + 39: 'slots 1..7 start empty (zero energy)',
}


# Instructions that address a field of a fixed slot.
OPERANDS = {
    0x70F0: 'InitialRuntimeState+InstanceBehaviour',      # LD HL,$6069
    0x77FD: 'InitialRuntimeState+InstanceBehaviour',      # LD HL,$6069
    0xDA24: 'InitialRuntimeState+InstanceBehaviour',      # LD HL,$6069
    0xD744: 'InitialRuntimeState+InstanceX+1',
    0xD78B: 'InitialRuntimeState+InstanceX+2',
    0xD73A: 'InitialRuntimeState+InstanceZ+1',
    0xD775: 'InitialRuntimeState+InstanceZ+1',
    0xD7A2: 'InitialRuntimeState+InstanceZ+2',
    0xD769: 'InitialRuntimeState+InstanceAxisZ',
    0xD783: 'InitialRuntimeState+InstanceAxisZ+1',
    0xD79C: 'InitialRuntimeState+InstanceAxisZ+5',
    0xD77B: 'InitialRuntimeState+InstanceAxisY+3',
    0xD799: 'InitialRuntimeState+InstanceAxisX+1',
    0xD780: 'InitialRuntimeState+InstanceAxisX+5',
    0xD7C6: 'InitialRuntimeState+InstanceRoleFlags',
    0x7194: 'InitialRuntimeState+InstanceRoll',
    0x7840: 'InitialRuntimeState+InstanceRoll',
    0xD80F: 'InitialRuntimeState+InstanceRoll',
    0xDFF7: 'ObjectSlot7+InstanceAxisZ',
}

ASSERTS = {
    'object-slot-size': ('ObjectSlot1-InitialRuntimeState = InstanceSize', 'slots are 39 bytes apart'),
    'object-slot-array': ('ObjectSlot7-InitialRuntimeState = 7*InstanceSize', 'eight contiguous slots'),
    'object-array-end': ('InitialRuntimeStateSize = InstanceSlotCount*InstanceSize',
                         'the initial state region is exactly the slot array'),
    'missile-energy': ('PlayerMissileEnergy-ObjectSlot7 = InstanceEnergy', 'slot 7 energy byte'),
}
