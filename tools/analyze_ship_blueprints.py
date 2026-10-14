"""Decode and document the ZX Elite ship blueprint table.

The 128K-compatible release is the authoritative build target.  The two
unprotected 48K TAPs are comparison media: side A confirms the Krait slot,
while side B exposes the Adder that replaces it in that release.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from tape import REFERENCE_SHA256, ROOT, parse, reference, sha


GAME_BASE = 0x6048
FIXED_48K_BASE = 0x4000
TABLE_ADDRESS = 0x6180
BLUEPRINT_COUNT = 19
TABLE_ENTRY_SIZE = 4
HEADER_SIZE = 23
BLUEPRINT_DATA_END = 0x6FA3
REGION_END = 0x7000
EXTERNAL_DATA_LABELS = {
    0x640A: "L_640A",
    0x6FA3: "TokenControlTable",
    0x6FBF: "MessageControlTable",
}


@dataclass(frozen=True)
class Identity:
    name: str
    label: str
    role: str = ""


IDENTITIES = (
    Identity("Coriolis station", "CoriolisStation"),
    Identity("Missile", "Missile"),
    Identity("Escape capsule", "EscapeCapsule"),
    Identity("Alloy plate", "AlloyPlate"),
    Identity("Cargo canister", "CargoCanister"),
    Identity("Splinter", "Splinter"),
    Identity("Asteroid", "Asteroid"),
    Identity("Rock hermit", "RockHermit"),
    Identity("Viper", "Viper"),
    Identity("Cobra Mk III", "CobraMkIIITrader", "trader record"),
    Identity("Python", "PythonTrader", "trader record"),
    Identity("Python", "PythonPirate", "pirate record"),
    Identity("Cobra Mk III", "CobraMkIIIPirate", "pirate record"),
    Identity("Asp Mk II", "AspMkII"),
    Identity("Fer-de-Lance", "FerDeLance"),
    Identity("Thargoid", "Thargoid"),
    Identity("Sidewinder", "Sidewinder"),
    Identity("Krait", "Krait"),
    Identity("Thargon", "Thargon"),
)


# Header layout: (offset, size, JSON key, reading instructions in the reference image).
HEADER_FIELDS = (
    (0x00, 1, "cargo_flags", "$ECB3 low nibble, $F7D4 whole byte, $EAB5 high nibble"),
    (0x01, 1, "radius", "$E02D near limit and projected size, $EA58 proximity box, $DB38"),
    (0x02, 1, "laser_fire_chance", "$FAB3, halved while CombatScoreHigh = 0"),
    (0x03, 1, "vertices", "$E2F5"),
    (0x04, 1, "edges", "$E72F"),
    (0x05, 1, "faces", "$E940; zero marks face 0 visible"),
    (0x06, 1, "maximum_speed", "$F33B half at creation, $DD7E speed limit, $DACD Thargoid test"),
    (0x07, 1, "energy", "$F320 creation, $F733/$F76E regeneration, $ECBE/$ECC5 debris"),
    (0x08, 2, "bounty_tenths_cr", "$DB4A/$DB4D -> AwardBounty"),
    (0x0A, 1, "launch_flags", "$F32F bits 0..2 payload count, $F794 high nibble subtype"),
    (0x0B, 1, "dot_distance", "$E112"),
    (0x0C, 2, "vertices_address", "$E2FA/$E2FD offset from the header"),
    (0x0E, 2, "edges_address", "$E729/$E72C offset from the header"),
    (0x10, 2, "faces_address", "$E92F/$E932 offset from the header"),
    (0x12, 1, "behaviour_flags", "$F326 -> instance +$21/+$20 bit 7, $F7DF value 4"),
    (0x13, 1, "normal_scale_shift", "$E93A -> NormalScaleShift"),
    (0x14, 1, "gun_vertex", "$E1A5"),
    (0x15, 2, "combat_score_award", "$DB53/$DB56, halved -> AddCombatScore"),
)

# Commodity names in CargoHold order (tokens $D0..$E0, printed by ScoopCargoItem).
COMMODITY_NAMES = (
    "Food", "Textiles", "Radioactives", "Slaves", "Liquor/Wines", "Luxuries", "Narcotics",
    "Computers", "Machinery", "Alloys", "Firearms", "Furs", "Minerals", "Gold", "Platinum",
    "Gem-stones", "Alien items",
)
# Header +$0A high nibble: the child chosen by SelectParentLaunchType (0 = missile event).
LAUNCH_SUBTYPES = {0: "missile", 1: "Viper", 2: "Cobra/Python trader", 3: "Thargon",
                   4: "Thargoid", 5: "Sidewinder or slot-17 ship"}
# Header +$12 bits, as used through instance +$21 (bit 7 goes to instance +$20 bit 7).
BEHAVIOUR_BITS = ((0x01, "speed limit x4"), (0x02, "legal-sensitive"), (0x04, "hostile"),
                  (0x08, "steers away near station"), (0x20, "protected"), (0x40, "protected"),
                  (0x80, "escape capsule"))


def word(data: bytes, offset: int) -> int:
    return data[offset] | data[offset + 1] << 8


def scooped_commodity(cargo_flags: int):
    """Commodity index given by a scooped object: high nibble + 1, or None (random 0..7)."""
    return (cargo_flags >> 4) + 1 if cargo_flags >> 4 else None


def cargo_comment(cargo_flags: int) -> str:
    commodity = scooped_commodity(cargo_flags)
    scoop = COMMODITY_NAMES[commodity] if commodity is not None else "random Food..Computers"
    kill = "one canister" if cargo_flags & 0x0F else "no canister"
    return f"+0 cargo: scooped as {scoop}; {kill} when killed"


def launch_comment(flags: int) -> str:
    count, subtype = flags & 0x07, flags >> 4
    if not count:
        return "+$0A launches: none"
    return f"+$0A launches: {count} x {LAUNCH_SUBTYPES.get(subtype, 'nothing')}"


def behaviour_comment(flags: int) -> str:
    names = []
    for bit, name in BEHAVIOUR_BITS:
        if flags & bit and name not in names:
            names.append(name)
    text = ", ".join(names) if names else "passive"
    if flags == 0x04:
        text += " (value 4: Thargon test)"
    return f"+$12 behaviour: {text}"


def slice_at(image: bytes, base: int, address: int, size: int) -> bytes:
    start = address - base
    if start < 0 or start + size > len(image):
        raise ValueError(f"${address:04X}..${address + size - 1:04X} is outside the image")
    return image[start : start + size]


def parse_table(
    image: bytes,
    base: int,
    identities=IDENTITIES,
    blueprint_data_limit: int = REGION_END,
    compact: bool = False,
    table_address: int = TABLE_ADDRESS,
) -> list[dict]:
    entry_size = 2 if compact else TABLE_ENTRY_SIZE
    table = slice_at(image, base, table_address, BLUEPRINT_COUNT * entry_size)
    result = []
    for index, identity in enumerate(identities):
        entry = table[index * entry_size : (index+1)*entry_size]
        if not compact and entry[0] != 0xC3:
            raise ValueError(f"Blueprint table entry {index} does not start with $C3")
        address = word(entry, 0 if compact else 1)
        if not table_address + len(table) <= address < blueprint_data_limit:
            raise ValueError(f"Blueprint {index} pointer ${address:04X} is outside the data region")
        header = slice_at(image, base, address, HEADER_SIZE)
        vertex_offset = word(header, 12)
        edge_offset = word(header, 14)
        face_offset = word(header, 16)
        vertices = address + vertex_offset if vertex_offset else None
        edges = address + edge_offset if edge_offset else None
        faces = address + face_offset if face_offset else None
        if not vertices or not edges:
            raise ValueError(f"Blueprint {index} has no vertex or edge data")
        if vertices + header[3] * 6 != edges:
            raise ValueError(f"Blueprint {index} vertex count does not reach its edge table")
        if faces:
            if edges + header[4] * 4 != faces:
                raise ValueError(f"Blueprint {index} edge count does not reach its face table")
            geometry_end = faces + header[5] * 4
        else:
            if header[5] != 0:
                raise ValueError(f"Blueprint {index} has faces but no face pointer")
            geometry_end = edges + header[4] * 4
        if geometry_end > blueprint_data_limit:
            raise ValueError(f"Blueprint {index} geometry extends beyond ${blueprint_data_limit:04X}")
        result.append(
            {
                "id": index,
                "name": identity.name,
                "role": identity.role or None,
                "label": identity.label,
                # Table byte 3; no code reads it (nor the $C3 byte 0).
                "unused_table_group": None if compact else entry[3],
                "address": address,
                "header": header,
                "cargo_flags": header[0],
                "drops_canister_when_killed": bool(header[0] & 0x0F),
                "scooped_commodity": scooped_commodity(header[0]),
                "radius": header[1],
                "laser_fire_chance": header[2],
                "vertices": header[3],
                "edges": header[4],
                "faces": header[5],
                "maximum_speed": header[6],
                "energy": header[7],
                "bounty_tenths_cr": word(header, 8),
                "launch_flags": header[10],
                "payload_count": header[10] & 0x07,
                "launch_subtype": header[10] >> 4,
                "dot_distance": header[11],
                "vertices_address": vertices,
                "edges_address": edges,
                "faces_address": faces,
                "behaviour_flags": header[18],
                "normal_scale_shift": header[19],
                "gun_vertex": header[20],
                "combat_score_award": word(header, 21),
                "geometry_end": geometry_end,
            }
        )
    return result


def fixed_tap_image(name: str) -> bytes:
    blocks = parse((ROOT / "assets" / name).read_bytes())
    if len(blocks) != 3 or blocks[-1].flag != 0xFF or len(blocks[-1].payload) != 49065:
        raise ValueError(f"Unexpected fixed 48K TAP structure: {name}")
    return blocks[-1].payload


def tzx_description(name: str) -> str:
    """Read the leading TZX text-description block without parsing protected data."""
    data = (ROOT / "assets" / name).read_bytes()
    if data[:8] != b"ZXTape!\x1A" or data[10] != 0x30:
        raise ValueError(f"Expected a leading TZX text-description block: {name}")
    length = data[11]
    return data[12 : 12 + length].decode("ascii")


def record_for_id(records: list[dict], blueprint_id: int) -> dict:
    return next(item for item in records if item["id"] == blueprint_id)


def geometry_bytes(image: bytes, base: int, record: dict) -> bytes:
    start = record["vertices_address"]
    return slice_at(image, base, start, record["geometry_end"] - start)


def validate_reference_code(image: bytes) -> None:
    # Destruction/mining path: the special event at $ECD1 reaches dispatch
    # case 8, which enters $F5B0 and creates blueprint ID 5 twice.
    landmarks = {
        0xECB3: "7ee60f3e062017110700197efe553e05300c7efe3c200a79fe3220053e08cdcaf2",
        0xF2EE: "3dca5df53dcab0f53dcad8f5c9",
        0xF5B0: "3e05cdb8f5c03e05",
    }
    for address, expected_hex in landmarks.items():
        actual = slice_at(image, GAME_BASE, address, len(bytes.fromhex(expected_hex)))
        if actual != bytes.fromhex(expected_hex):
            raise ValueError(f"Mining landmark changed at ${address:04X}")


def serializable_record(record: dict) -> dict:
    return {
        key: (
            f"${value:04X}"
            if value is not None and (key.endswith("_address") or key == "address")
            else value
        )
        for key, value in record.items()
        if key not in {"header", "label", "geometry_end"}
    }


def analysis() -> tuple[dict, bytes, list[dict]]:
    tape_data, blocks = reference()
    image = blocks[5].payload
    records = parse_table(image, GAME_BASE)
    if max(record["geometry_end"] for record in records) != BLUEPRINT_DATA_END:
        raise ValueError("The reference blueprint geometry has an unexpected end address")
    validate_reference_code(image)

    fixed_a = fixed_tap_image("Elite+48K+fixed+A+-+Krait.tap")
    fixed_b = fixed_tap_image("Elite+48K+fixed+B+-+Adder.tap")
    records_a = parse_table(fixed_a, FIXED_48K_BASE)
    side_b_identities = list(IDENTITIES)
    side_b_identities[17] = Identity("Adder", "Adder")
    records_b = parse_table(fixed_b, FIXED_48K_BASE, side_b_identities)
    krait = record_for_id(records, 17)
    krait_a = record_for_id(records_a, 17)
    adder = record_for_id(records_b, 17)

    if krait["header"] != krait_a["header"] or geometry_bytes(image, GAME_BASE, krait) != geometry_bytes(fixed_a, FIXED_48K_BASE, krait_a):
        raise ValueError("The 128K-compatible and fixed 48K side-A Krait records differ")
    if adder["name"] != "Adder" or adder["vertices"] != 18 or adder["edges"] != 29 or adder["faces"] != 15:
        raise ValueError("The expected Adder is not present in fixed 48K side B")

    report = {
        "reference": {
            "file": "assets/Elite - 128k.tap",
            "sha256": sha(tape_data),
            "game_load_address": f"${GAME_BASE:04X}",
            "table_address": f"${TABLE_ADDRESS:04X}",
            "blueprint_count": BLUEPRINT_COUNT,
            "blueprint_data_end_exclusive": f"${BLUEPRINT_DATA_END:04X}",
            "auxiliary_data_end_exclusive": f"${REGION_END:04X}",
        },
        "header_fields": [
            {"offset": f"+${offset:02X}", "size": size, "key": key, "readers": readers}
            for offset, size, key, readers in HEADER_FIELDS
        ],
        "blueprints": [serializable_record(record) for record in records],
        "shared_geometry": [
            {"record": "Rock hermit", "geometry_owner": "Asteroid"},
            {"record": "Cobra Mk III (trader record)", "geometry_owner": "Cobra Mk III (pirate record)"},
            {"record": "Python (trader record)", "geometry_owner": "Python (pirate record)"},
        ],
        "variant_slot_17": {
            "original_side_a_description": tzx_description("Elite - 48k - Side A.tzx"),
            "original_side_b_description": tzx_description("Elite - 48k - Side B.tzx"),
            "compatible_128k": serializable_record(krait),
            "fixed_48k_side_a": serializable_record(krait_a),
            "fixed_48k_side_b": serializable_record(adder),
            "krait_bytes_match_between_compatible_128k_and_fixed_48k_side_a": True,
        },
        "mining": {
            "special_destruction_path": "$ECB3..$ECD3 -> dispatch case 8 -> $F5B0",
            "spawned_blueprint_id": 5,
            "spawned_blueprint": "Splinter",
            "spawn_count": 2,
            "evidence": "The special path requires header energy $3C and laser value $32, then $F5B0 creates blueprint ID 5 twice.",
            "separate_boulder_blueprint_present": False,
        },
    }
    if report["reference"]["sha256"] != REFERENCE_SHA256:
        raise ValueError("Reference hash changed")
    return report, image, records


def defb(data: bytes) -> str:
    return "defb " + ",".join(f"${value:02X}" for value in data)


def emit_data(lines: list[str], image: bytes, start: int, size: int, preferred_size: int) -> None:
    address = start
    end = start + size
    while address < end:
        if address in EXTERNAL_DATA_LABELS:
            lines.append(EXTERNAL_DATA_LABELS[address] + ":")
        next_label = min((item for item in EXTERNAL_DATA_LABELS if address < item < end), default=end)
        count = min(preferred_size, end - address, next_label - address)
        lines.append(f"    {defb(slice_at(image, GAME_BASE, address, count))} ; ${address:04X}")
        address += count


def render_asm(image: bytes, records: list[dict]) -> str:
    lines = [
        "; Reconstructed from assets/Elite - 128k.tap; no original binary is included at build time.",
        f"; TAP SHA256: {REFERENCE_SHA256}",
        f"; Zero-based TAP data block 5; payload SHA256: {sha(image)}",
        "; Generated by tools/analyze_ship_blueprints.py; tools/bootstrap_sources.py uses the same renderer.",
        "",
        "; VERIFIED DATA: 19 four-byte blueprint table entries, structured ship blueprint",
        "; headers and geometry, followed by text/control-token handler pointers.",
        "; Table entry: $C3, pointer to the header, group byte.  InitialiseShipFromBlueprint reads",
        "; only the pointer; no code reads the $C3 or group bytes (ship=adder drops both).",
        "; Header, 23 bytes (readers in docs/SHIPS.md): +0 cargo flags, +1 radius, +2 AI laser fire",
        "; chance, +3/+4/+5 vertex/edge/face counts, +6 maximum speed, +7 energy, +8 bounty word,",
        "; +$0A launch flags, +$0B dot distance, +$0C/+$0E/+$10 vertex/edge/face table offsets from",
        "; the header, +$12 behaviour flags, +$13 normal scale shift, +$14 gun vertex,",
        "; +$15 combat-score award word (halved and added to the score: kill count + word/512).",
        "; Vertex, 6 bytes: |x|, |y|, |z|; +3 bits 7/6/5 = signs of x/y/z, bits 0..4 visibility",
        "; threshold; +4 and +5 = four face numbers, one per nibble.",
        "; Edge, 4 bytes: visibility threshold, first vertex, second vertex, two face nibbles.",
        "; Face, 4 bytes: normal |x|, |y|, |z|; +3 bits 7/6/5 signs, bits 0..4 visibility threshold.",
        "; A part is used while the detail level (depth class) is below its threshold; $1F means",
        "; always.  Face number 15 is always visible; a vertex or edge needs one visible face.",
        "",
        "ShipBlueprintsAndDispatchTables:",
        "ShipBlueprintTable:",
    ]
    for record in records:
        role = f" ({record['role']})" if record["role"] else ""
        lines += [
            'IF !SHIP_ADDER', "    defb $C3 ; not read (JP opcode byte)", 'ENDIF',
            ("IF SHIP_ADDER\n    defw ShipAdderBlueprint\nELSE\n    defw ShipKraitBlueprint\nENDIF"
             if record['id'] == 17 else f"    defw Ship{record['label']}Blueprint"),
            'IF !SHIP_ADDER',
            f"    defb ${record['unused_table_group']:02X} ; ID {record['id']}: {record['name']}{role};"
            " group byte, not read",
            'ENDIF',
        ]
    lines += [
        "ShipBlueprintTableEnd:",
        f"defc ShipBlueprintCount = {BLUEPRINT_COUNT}",
        'IF SHIP_ADDER', 'assert ShipBlueprintTableEnd-ShipBlueprintTable = ShipBlueprintCount*2',
        'ELSE', "assert ShipBlueprintTableEnd-ShipBlueprintTable = ShipBlueprintCount*4", 'ENDIF',
        "",
    ]

    # Records are physically ordered by address, rather than by dispatch ID.
    for record in sorted(records, key=lambda item: item["address"]):
        if record['id'] == 17:
            lines += ['IF SHIP_ADDER', '    INCLUDE "adder.asm"', 'ELSE']
        address = record["address"]
        identity = record["name"] + (f" ({record['role']})" if record["role"] else "")
        owners = [
            candidate
            for candidate in records
            if candidate["address"] + HEADER_SIZE == record["vertices_address"]
            and candidate["vertices_address"] == record["vertices_address"]
            and candidate["edges_address"] == record["edges_address"]
            and candidate["faces_address"] == record["faces_address"]
        ]
        if len(owners) != 1:
            raise ValueError(f"Blueprint {record['id']} has no unique geometry owner")
        owner = owners[0]
        lines += [
            f"; Blueprint ID {record['id']}: {identity}; original address ${address:04X}.",
            f"Ship{record['label']}Blueprint:",
            f"    defb ${record['cargo_flags']:02X} ; {cargo_comment(record['cargo_flags'])}",
            f"    defb {record['radius']} ; +1 radius: near limit, target size, collision box",
            f"    defb ${record['laser_fire_chance']:02X} ; +2 AI laser fire chance in 256, halved below 256 kills",
            f"    defb {record['vertices']} ; +3 vertices",
            f"    defb {record['edges']} ; +4 edges",
            f"    defb {record['faces']} ; +5 faces",
            f"    defb {record['maximum_speed']} ; +6 maximum speed; a new ship starts at half",
            f"    defb {record['energy']} ; +7 energy: initial value and regeneration limit",
            f"    defw {record['bounty_tenths_cr']} ; +8 bounty in tenths of a credit",
            f"    defb ${record['launch_flags']:02X} ; {launch_comment(record['launch_flags'])}",
            f"    defb {record['dot_distance']} ; +$0B dot distance: wireframe while the depth high byte is lower",
            f"    defw Ship{owner['label']}Vertices-Ship{record['label']}Blueprint ; +$0C",
            f"    defw Ship{owner['label']}Edges-Ship{record['label']}Blueprint ; +$0E",
        ]
        if record["faces_address"]:
            lines.append(f"    defw Ship{owner['label']}Faces-Ship{record['label']}Blueprint ; +$10")
        else:
            lines.append("    defw 0 ; +$10 no face normals")
        award = record['combat_score_award']
        lines += [
            f"    defb ${record['behaviour_flags']:02X} ; {behaviour_comment(record['behaviour_flags'])}",
            f"    defb ${record['normal_scale_shift']:02X} ; +$13 normal scale shift n: normals x 2/2^n",
            f"    defb {record['gun_vertex']} ; +$14 gun vertex: start of the AI laser beam",
            f"    defb ${award & 255:02X} ; +$15 combat-score award {award}: kill count +{award >> 1}/256",
            f"    defb {award >> 8} ; +$16 high byte of the award",
            f"assert $-Ship{record['label']}Blueprint = {HEADER_SIZE}",
        ]

        # Shared geometry belongs to the later record and must only be emitted once.
        if owner is not record:
            lines += [
                f"; Geometry is shared with {owner['name']}"
                + (f" ({owner['role']})." if owner["role"] else "."),
                "",
            ]
            continue

        sections = [
            ("Vertices", record["vertices_address"], record["vertices"] * 6, 6),
            ("Edges", record["edges_address"], record["edges"] * 4, 4),
        ]
        if record["faces_address"]:
            sections.append(("Faces", record["faces_address"], record["faces"] * 4, 4))
        for section, start, size, unit in sections:
            label = f"Ship{record['label']}{section}"
            lines.append(f"{label}:")
            emit_data(lines, image, start, size, 4 * unit)
            lines.append(f"assert $-{label} = {size}")
        lines.append("")
        if record['id'] == 17:
            lines.append('ENDIF')

    if max(record["geometry_end"] for record in records) != BLUEPRINT_DATA_END:
        raise ValueError("The named blueprint geometry does not end at the auxiliary table")
    lines += [
        'ShipGeometryEnd:',
        'IF SHIP_ADDER',
        '    INCLUDE "text-dispatch-second.asm"',
        'ELSE',
        '    INCLUDE "text-dispatch-first.asm"',
        '    INCLUDE "text-dispatch-second.asm"',
        'ENDIF',
        "",
        "ShipBlueprintsAndDispatchTablesEnd:",
        "defc ShipBlueprintsAndDispatchTablesSize = ShipBlueprintsAndDispatchTablesEnd - ShipBlueprintsAndDispatchTables",
        f"assert ShipBlueprintsAndDispatchTablesSize = {REGION_END - TABLE_ADDRESS}",
        'IF !SHIP_ADDER',
        "assert L_640A-ShipBlueprintsAndDispatchTables = $640A-$6180",
        "assert TokenControlTable-ShipBlueprintsAndDispatchTables = $6FA3-$6180",
        "assert MessageControlTable-ShipBlueprintsAndDispatchTables = $6FBF-$6180",
        'ENDIF',
        "",
    ]
    return "\n".join(lines)


def text_dispatch_targets(image):
    data = slice_at(image, GAME_BASE, BLUEPRINT_DATA_END, REGION_END-BLUEPRINT_DATA_END)
    assert len(data) == 93 and data[-1] == 0
    return [word(data, i) for i in range(0, len(data)-1, 2)]


def write_variant_sources(image, names=None):
    """Extract reviewable ASM once; normal builds never extract reference binaries.

    names maps handler addresses to their current source labels; without it
    the neutral L_xxxx names are used (resolved through the alias table)."""
    names = names or {}
    directory = ROOT/'src/data'
    prologue = [
        '; Original text control-code handler pointers, read by DispatchMessageControl ($B89A)',
        '; and DispatchTokenControl ($B89F).  Entry n handles control code n.',
        f'; assets/Elite - 128k.tap, block 5, load $6048, SHA256 {REFERENCE_SHA256}',
    ]
    targets = text_dispatch_targets(image)
    for part, label, values in [('first','TokenControlTable',targets[:14]),
                                ('second','MessageControlTable',targets[14:])]:
        lines = prologue + [label+':'] + [f'    defw {names.get(target, f"L_{target:04X}"):<32} ; code {n}'
                                          for n, target in enumerate(values)]
        lines += [f'{label}End:', f'defc {label}Size = {label}End-{label}',
                  f'assert {label}Size = {len(values)*2}']
        if part == 'second':
            lines += ['    defb 0 ; original trailing byte']
        (directory/f'text-dispatch-{part}.asm').write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    filename = 'Elite+48K+fixed+B+-+Adder.tap'
    data = fixed_tap_image(filename)
    for output, optimize in [('adder.asm', True), ('adder-original.asm', False)]:
        (directory/output).write_text(render_adder_source(data, filename, optimize),
                                      encoding='ascii', newline='\n')


def render_adder_source(data, filename, optimize):
    """Keep both the byte-exact side-B model and the optional compact model."""
    identities = list(IDENTITIES)
    identities[17] = Identity('Adder', 'Adder')
    r = parse_table(data, FIXED_48K_BASE, identities)[17]
    # Faces 6, 7 and 8 have exactly the same four-byte normal and visibility.
    # Share that normal, remapping every vertex/edge face reference. Geometry,
    # winding, edge visibility and all ship properties remain equivalent.
    original_faces = slice_at(data,FIXED_48K_BASE,r['faces_address'],r['faces']*4)
    unique, face_map = [], {15:15}
    for i in range(r['faces']):
        face = original_faces[i*4:i*4+4]
        if face not in unique:
            unique.append(face)
        face_map[i] = unique.index(face)
    def remap(value):
        return face_map[value>>4]*16 + face_map[value&15]
    lines = [f'; Extracted from assets/{filename}; TAP data block 2, load $4000.',
             f'; TAP SHA256: {sha((ROOT/"assets"/filename).read_bytes())}']
    if optimize:
        lines += ['; Slot 17 replacement: original Adder with duplicate face normals shared.',
                  '; Original faces 6/7/8 are identical; their references now use face 6.']
    else:
        lines += ['; Original 48K side-B Adder: complete unmodified header and geometry.',
                  '; All 15 face normals and original vertex/edge face indices are retained.',
                  f'; Original record: ${r["address"]:04X}..${r["geometry_end"]-1:04X} (307 bytes).',
                  '; Reference only: ship=adder still selects the optimized adder.asm.',
                  '; Same labels as adder.asm: include only one of these alternatives.',
                  '; This version needs 8 extra bytes; the current game layout cannot fit it unchanged.']
    lines += ['; Geometry offsets/counts are derived by the assembler.', 'ShipAdderBlueprint:']
    fields = [('cargo_flags', cargo_comment(r['cargo_flags'])),
              ('radius', '+1 radius: near limit, target size, collision box'),
              ('laser_fire_chance', '+2 AI laser fire chance in 256, halved below 256 kills')]
    lines += [f'    defb {r[key]} ; {comment}' for key, comment in fields]
    for section, unit, offset in [('Vertices',6,3),('Edges',4,4),('Faces',4,5)]:
        lines.append(f'    defb (ShipAdder{section}End-ShipAdder{section})/{unit} ; +{offset} count')
    award = r['combat_score_award']
    lines += [f'    defb {r["maximum_speed"]} ; +6 maximum speed',
              f'    defb {r["energy"]} ; +7 energy',
              f'    defw {r["bounty_tenths_cr"]} ; +8 bounty in tenths of a credit',
              f'    defb ${r["launch_flags"]:02X} ; {launch_comment(r["launch_flags"])}',
              f'    defb {r["dot_distance"]} ; +$0B dot distance']
    lines += [f'    defw ShipAdder{section}-ShipAdderBlueprint ; +${offset:02X} table offset'
              for section, offset in [('Vertices',0x0C),('Edges',0x0E),('Faces',0x10)]]
    for value, comment in [(r['behaviour_flags'], behaviour_comment(r['behaviour_flags'])),
                           (r['normal_scale_shift'], '+$13 normal scale shift'),
                           (r['gun_vertex'], '+$14 gun vertex'),
                           (award & 255, f'+$15 combat-score award {award}, low byte'),
                           (award >> 8, '+$16 combat-score award, high byte')]:
        lines.append(f'    defb ${value:02X} ; {comment}')
    lines += ['assert $-ShipAdderBlueprint = 23']
    for section, key, unit in [('Vertices','vertices',6),('Edges','edges',4),('Faces','faces',4)]:
        lines.append(f'ShipAdder{section}:')
        raw = bytearray(slice_at(data, FIXED_48K_BASE, r[key+'_address'], r[key]*unit))
        if optimize and section == 'Faces':
            raw = b''.join(unique)
        elif optimize:
            for i in range(0,len(raw),unit):
                for offset in ([4,5] if section == 'Vertices' else [3]):
                    raw[i+offset] = remap(raw[i+offset])
        for i in range(0,len(raw),unit):
            lines.append('    '+defb(raw[i:i+unit]))
        lines += [f'ShipAdder{section}End:', f'assert (ShipAdder{section}End-ShipAdder{section}) % {unit} = 0']
    size = r['geometry_end']-r['address'] - (len(original_faces)-4*len(unique) if optimize else 0)
    lines += ['ShipAdderBlueprintEnd:', f'assert ShipAdderBlueprintEnd-ShipAdderBlueprint = {size}', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-source",
        action="store_true",
        help="regenerate ship/table ASM, both Adder alternatives and both text-dispatch includes",
    )
    args = parser.parse_args()
    report, image, records = analysis()
    output = ROOT / "docs" / "generated" / "ship-blueprints.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.write_source:
        write_variant_sources(image)
        source = ROOT / "src" / "data" / "ship-blueprints-and-tables.asm"
        source.write_text(render_asm(image, records), encoding="ascii", newline="\n")
        print(f"Structured source: {source.relative_to(ROOT)}")
    print(f"Verified {len(records)} blueprint records; report: {output.relative_to(ROOT)}")
    print("Slot 17: Krait in the 128K-compatible and side-A tapes; Adder in side B")
    print("Mining special case: blueprint ID 5 (Splinter) is created twice; no Boulder blueprint is present")


if __name__ == "__main__":
    main()
