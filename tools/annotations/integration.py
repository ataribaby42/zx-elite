"""Cross-range operand and constant decisions taken during integration.

Each entry was proposed by the analysis of a neighbouring range and checked
against the instruction and the label it now uses.  Byte identity proves the
value; these expressions keep the code correct when data moves.
"""

OPERANDS = {
    0x7C20: 'InstanceSize',                     # LD DE,$0027: step between object slots
    0x85A8: 'InstanceSize',                     # LD DE,$0027: step between object slots
    0xB6DE: 'LaserTypeItemTable-1',             # LD HL,$FB99: table indexed by laser type 1..4
    0xD3E8: 'CommanderTemplateBufferSize',      # LD BC,$0066: 102 persistent commander bytes
    0x707F: 'RollControl+1',                    # LD HL,$FF09: high byte of the roll accumulator
    0xB48A: 'CargoHold+15',                     # LD ($A83C),A: gem-stones
    0xF61D: 'CargoHold+3',                      # LD A,($A830): slaves
    0xF621: 'CargoHold+6',                      # LD A,($A833): narcotics
    0xF627: 'CargoHold+10',                     # LD A,($A837): firearms
    0xB925: 'RandomNamePairTable',              # LD HL,$FBAB: pair table without the first ('@@') pair
}

# Equipment price table entries (EquipmentPriceTable): byte 0 = thousands of
# credits, bytes 1..2 = tenths of a credit; item names from tokens $6A..$76.
COMMENTS = {
    0x9239: 'MISSILE: 30.0 Cr',
    0x923C: 'LARGE CARGO BAY: 400.0 Cr',
    0x923F: 'E.C.M.SYSTEM: 600.0 Cr',
    0x9242: 'EXTRA PULSE LASERS: 400.0 Cr',
    0x9245: 'EXTRA BEAM LASERS: 1000.0 Cr',
    0x9248: 'FUEL SCOOPS: 525.0 Cr',
    0x924B: 'ESCAPE POD: 1000.0 Cr',
    0x924E: 'ENERGY BOMB: 900.0 Cr',
    0x9251: 'ENERGY UNIT: 1500.0 Cr',
    0x9254: 'DOCKING COMPUTERS: 1500.0 Cr',
    0x9257: 'GALACTIC HYPERSPACE: 5000.0 Cr',
    0x925A: 'MILITARY LASER: 6000.0 Cr',
    0x925D: 'MINING LASER: 800.0 Cr',
}
