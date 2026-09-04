"""Compare original ZX geometry with pinned Mark Moxon 6502 source checkouts.

Read-only with respect to game source and tapes. See docs/SHIP-COMPARISON.md.
Generated reports go in docs/generated; downloaded checkouts stay in build.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from analyze_ship_blueprints import (
    GAME_BASE, FIXED_48K_BASE, IDENTITIES, Identity, fixed_tap_image,
    parse_table, slice_at,
)
from tape import ROOT, reference, sha

NAMES = ["CORIOLIS", "MISSILE", "ESCAPE_POD", "PLATE", "CANISTER",
         "SPLINTER", "ASTEROID", "ROCK_HERMIT", "VIPER", "COBRA_MK_3",
         "PYTHON", "PYTHON_P", "COBRA_MK_3_P", "ASP_MK_2", "FER_DE_LANCE",
         "THARGOID", "SIDEWINDER", "KRAIT", "THARGON", "ADDER"]
REPOS = {"c64": "elite-source-code-commodore-64",
         "bbc-disc": "elite-source-code-bbc-micro-disc",
         "bbc-cassette": "elite-source-code-bbc-micro-cassette"}
REVISIONS = {"c64": "448b7fadf67510c1302676b211c5ba9551a9c66a",
             "bbc-disc": "a18269cfd71a4721fa30ae13ff4cbf97cafd3c1b",
             "bbc-cassette": "019e1ccc315d89db2148e480d10011e2c4180a39"}
ZX_NORMAL_SCALE_OFFSET = 19


def signed(row):
    return [(-n if row[3] & (128 >> i) else n) for i, n in enumerate(row[:3])]


def zx_model(image, base, record):
    result = {"name": record["name"], "id": record["id"],
              "address": record["address"],
              # The old analyzer's normal_scale field names header +22 in error.
              # Original ZX $E93A reads +19 and $EA1C..$EA28 consumes it.
              "normal_scale": record["header"][ZX_NORMAL_SCALE_OFFSET],
              "vertices": [], "edges": [], "faces": []}
    for kind, size in (("vertices", 6), ("edges", 4), ("faces", 4)):
        if not record[kind]:
            continue
        data = slice_at(image, base, record[kind + "_address"], record[kind] * size)
        for start in range(0, len(data), size):
            row = data[start:start + size]
            if kind == "vertices":
                decoded = signed(row) + sorted([row[4] >> 4, row[4] & 15,
                                                row[5] >> 4, row[5] & 15]) + [row[3] & 31]
            elif kind == "edges":
                decoded = sorted(row[1:3]) + sorted([row[3] >> 4, row[3] & 15]) + [row[0]]
            else:
                decoded = signed(row) + [row[3] & 31]
            result[kind].append(decoded)
    return result


def external_models(root, platform):
    """Read literal geometry macros; fail on conditional or nonliteral tables.

    BBC disc banks repeat models; require every occurrence to agree. Header
    edge references resolve shared Escape Pod/Splinter and Canister/Thargon data.
    """
    tables, headers, locations, scales = {}, {}, {}, {}
    for path in sorted((root / "1-source-files/main-sources").glob("*.asm")):
        if platform == "bbc-disc" and not (path.name.startswith("elite-ships-") or path.name == "elite-missile.asm"):
            continue
        if platform == "c64" and path.name != "elite-data.asm":
            continue
        if platform == "bbc-cassette" and path.name != "elite-source.asm":
            continue
        label, rows, header = None, [], []
        missile_branch = None

        def save():
            if not label:
                return
            target, value = (tables, rows) if re.search(r"_(VERTICES|EDGES|FACES)$", label) else (headers, header)
            if target is tables:
                if label in target and target[label] != value:
                    raise ValueError(f"Different repeated geometry: {label} in {path}")
                target[label] = value[:]
            else:
                target.setdefault(label, value[:])

        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            scale = re.match(r"\s*EQUB\s+(\d+)\s+.*Normals are scaled", line)
            if label and scale:
                if label in scales and scales[label] != int(scale[1]):
                    raise ValueError(f"Conflicting normal scales for {label}")
                scales[label] = int(scale[1])
            code = re.split(r"[;\\]", line)[0].strip()
            if label == "SHIP_MISSILE_FACES" and code in (
                    "IF _STH_DISC OR _IB_DISC", "ELIF _SRAM_DISC", "ENDIF"):
                missile_branch = {"IF _STH_DISC OR _IB_DISC": True,
                                  "ELIF _SRAM_DISC": False, "ENDIF": None}[code]
                continue
            if missile_branch is False:
                continue
            if code.startswith("."):
                save()
                label = code[1:] if re.fullmatch(r"\.SHIP_[A-Z0-9_]+", code) else None
                rows, header = [], []
                if label:
                    locations.setdefault(label, {"file": path.relative_to(root).as_posix(), "line": lineno})
            elif label:
                match = re.match(r"(VERTEX|EDGE|FACE)\s+(.+)", code)
                if match:
                    args = [int(v.strip()) for v in match[2].split(",")]
                    assert len(args) == {"VERTEX": 8, "EDGE": 5, "FACE": 4}[match[1]]
                    if match[1] == "VERTEX":
                        args[3:7] = sorted(args[3:7])
                    elif match[1] == "EDGE":
                        args[:2] = sorted(args[:2])
                        args[2:4] = sorted(args[2:4])
                    rows.append(args)
                elif re.match(r"(IF|ELIF|ELSE|ENDIF)\b", code):
                    raise ValueError(f"Conditional ship data requires explicit handling: {path}:{lineno}")
                elif code:
                    header.append(code)
        save()
    result = {}
    for key in sorted(tables):
        if not key.endswith("_VERTICES"):
            continue
        name = key.removesuffix("_VERTICES")
        edge_ref = re.search(r"LO\((SHIP_[A-Z0-9_]+_EDGES)\s*-", "\n".join(headers[name]))
        if not edge_ref:
            raise ValueError(f"No edge reference for {name}")
        result[name.removeprefix("SHIP_")] = {
            "vertices": tables[key], "edges": tables[edge_ref[1]],
            "faces": tables[name + "_FACES"], "source": locations[name],
            "edge_source": locations[edge_ref[1]],
            "normal_scale": scales[name],
            "face_pointer_expression": next(h for h in headers[name] if "LO(" in h and "_FACES" in h),
        }
    return result


def differences(a, b):
    return [{"index": i, "zx": a[i] if i < len(a) else None,
             "other": b[i] if i < len(b) else None}
            for i in range(max(len(a), len(b)))
            if i >= len(a) or i >= len(b) or a[i] != b[i]]


def compare(zx, other):
    return {"coordinates": differences([v[:3] for v in zx["vertices"]], [v[:3] for v in other["vertices"]]),
            "edge_endpoints": differences([e[:2] for e in zx["edges"]], [e[:2] for e in other["edges"]]),
            "vertex_metadata": differences([v[3:] for v in zx["vertices"]], [v[3:] for v in other["vertices"]]),
            "edge_metadata": differences([e[2:] for e in zx["edges"]], [e[2:] for e in other["edges"]]),
            "faces": differences(zx["faces"], other["faces"]),
            "normal_scale": differences([zx["normal_scale"]], [other["normal_scale"]])}


def validate_model(model):
    assert model["vertices"] and model["edges"]
    for v in model["vertices"]:
        assert len(v) == 8 and 0 <= v[7] <= 31
        assert all(f == 15 or 0 <= f < len(model["faces"]) for f in v[3:7])
    for e in model["edges"]:
        assert len(e) == 5 and 0 <= e[4] <= 31
        assert all(0 <= v < len(model["vertices"]) for v in e[:2])
        assert all(f == 15 or 0 <= f < len(model["faces"]) for f in e[2:4])
    for f in model["faces"]:
        assert len(f) == 4 and 0 <= f[3] <= 31


def write_tables(result, directory):
    lines = ["# Generated ZX / C64 / BBC ship geometry comparison", "",
             "Regenerate with `python tools/compare_ship_geometry.py`. Interpretation: [SHIP-COMPARISON.md](../SHIP-COMPARISON.md).", "",
             "Coordinates are signed model units. Indices start at zero. No axis swap, scaling or vertex reordering was applied.", "",
             f"ZX reference SHA-256: `{result['zx_reference_sha256']}`.", "",
             result["zx_scope"] + ".", ""]
    for platform, source in result["sources"].items():
        lines += [f"- {platform}: [{source['revision']}]({source['repository']}/tree/{source['revision']}); {source['variant']}."]
    for item in result["models"]:
        model = item["zx"]
        lines += ["", f"## {item['key']} — {model['name']}", "",
                  f"ZX blueprint ${model['address']:04X}: {len(model['vertices'])} vertices, {len(model['edges'])} edges, {len(model['faces'])} normals. Normal scale field (+19): {model['normal_scale']}.", "",
                  "| Vertex | ZX (x, y, z) | C64 | BBC disc | BBC cassette |",
                  "|---:|---|---|---|---|"]
        for i, vertex in enumerate(model["vertices"]):
            values = []
            for c in item["comparisons"].values():
                values.append("absent" if c is None else ("same" if c["model"]["vertices"][i][:3] == vertex[:3] else str(tuple(c["model"]["vertices"][i][:3]))))
            lines += [f"| {i} | {tuple(vertex[:3])} | " + " | ".join(values) + " |"]
        for platform, c in item["comparisons"].items():
            lines += ["", f"### {platform}", ""]
            if c is None:
                lines += ["No separate matching blueprint declaration in the selected source. For Rock hermit, compare the identical Asteroid shape separately."]
                continue
            source = result["sources"][platform]
            loc = c["model"]["source"]
            lines += [f"[Source declaration]({source['repository']}/blob/{source['revision']}/{loc['file']}#L{loc['line']})."]
            if not any(c["differences"].values()):
                lines += ["Coordinates, undirected edge endpoints, face associations, visibility fields, normal vectors and normal scale field all match."]
            else:
                lines += ["", "| Field | Index | ZX | Comparison |", "|---|---:|---|---|"]
                for field, changes in c["differences"].items():
                    for change in changes:
                        lines += [f"| {field} | {change['index']} | `{change['zx']}` | `{change['other']}` |"]
            if item["key"] == "SPLINTER":
                lines += ["", "**Pointer caveat:** declared normals are compared here. The reference header adds 24 to the low face-table offset; these declarations are not necessarily the normals read at runtime.",
                          f"`{c['model']['face_pointer_expression']}`"]
    lines += ["", "Field formats: coordinates = x/y/z; edge_endpoints = two sorted vertex indices; vertex_metadata = four sorted face indices then visibility; edge_metadata = two sorted face indices then visibility; faces = normal x/y/z then visibility. Sorting removes nibble packing order only. normal_scale is the scalar header field, not vertex scale.", ""]
    (directory / "ship-comparison.md").write_text("\n".join(lines), encoding="utf-8")


def render_gallery(result, directory):
    """Orthographic geometry diagrams, not emulator screenshots or game culling."""
    from PIL import Image, ImageDraw, ImageFont
    models = [m for m in result["models"] if m["key"] not in ("ROCK_HERMIT", "PYTHON_P", "COBRA_MK_3_P")]
    width, tile_w, tile_h, margin = 1280, 640, 245, 116
    height = margin + math.ceil(len(models) / 2) * tile_h
    picture = Image.new("RGB", (width, height), "#101820")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=17)
    heading = ImageFont.load_default(size=25)
    small = ImageFont.load_default(size=14)
    draw.text((24, 16), "ZX Elite / C64 geometry - all distinct shapes", font=heading, fill="#ffffff")
    draw.text((24, 52), "Orthographic: oblique + X/Z plan. All edges shown; no hidden-line removal or distance culling.", font=font, fill="#c0ccd7")
    draw.text((24, 78), "Grey = shared 3D edges   Cyan/orange = changed ZX/C64 edges. Each model is fitted separately.", font=font, fill="#c0ccd7")

    def projected(vertex, view):
        x, y, z = vertex[:3]
        return (x * .83 - z * .56, -y * .85 + (x * .56 + z * .83) * .53) if view == 0 else (x, -z)

    for index, item in enumerate(models):
        model, other = item["zx"], item["comparisons"]["c64"]["model"]
        left, top = index % 2 * tile_w, margin + index // 2 * tile_h
        draw.line((left + 20, top, left + tile_w - 20, top), fill="#384451")
        draw.text((left + 24, top + 12), model["name"], font=font, fill="#ffffff")
        draw.text((left + 24, top + 36), f"{len(model['vertices'])} vertices / {len(model['edges'])} edges", font=small, fill="#a6b4c0")
        for view in range(2):
            all_points = [projected(v, view) for m in (model, other) for v in m["vertices"]]
            min_x, max_x = min(p[0] for p in all_points), max(p[0] for p in all_points)
            min_y, max_y = min(p[1] for p in all_points), max(p[1] for p in all_points)
            scale = min(260 / max(max_x - min_x, 1), 142 / max(max_y - min_y, 1))

            def point(vertex):
                x, y = projected(vertex, view)
                return (left + 165 + view * 310 + (x - (min_x + max_x) / 2) * scale,
                        top + 145 + (y - (min_y + max_y) / 2) * scale)

            for edge in model["edges"]:
                i, j = edge[:2]
                same = model["vertices"][i][:3] == other["vertices"][i][:3] and model["vertices"][j][:3] == other["vertices"][j][:3]
                if not same:
                    draw.line((point(other["vertices"][i]), point(other["vertices"][j])), fill="#ffac66", width=3)
                draw.line((point(model["vertices"][i]), point(model["vertices"][j])), fill="#aebfcd" if same else "#4ce3f0", width=2)
            draw.text((left + 120 + view * 310, top + 220), "Oblique" if view == 0 else "X/Z plan", font=small, fill="#a6b4c0")
    picture.save(directory / "ship-comparison.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "build/ship-comparison")
    parser.add_argument("--render", action="store_true", help="Also create a PNG geometry atlas (requires Pillow)")
    args = parser.parse_args()
    data, blocks = reference()
    image = blocks[5].payload
    assert slice_at(image, GAME_BASE, 0xE93A, 6) == bytes.fromhex("fd7e133219e9")
    assert slice_at(image, GAME_BASE, 0xEA1C, 14) == bytes.fromhex("3a19e9cb25e54704cb3d10fccb15")
    zx = [zx_model(image, GAME_BASE, r) for r in parse_table(image, GAME_BASE)]
    identities = list(IDENTITIES)
    identities[17] = Identity("Adder", "Adder")
    side_b = fixed_tap_image("Elite+48K+fixed+B+-+Adder.tap")
    zx.append(zx_model(side_b, FIXED_48K_BASE, parse_table(side_b, FIXED_48K_BASE, identities)[17]))
    result = {"zx_reference_sha256": sha(data), "zx_scope": "TAP block 5 (zero-based), load $6048; Adder: side-B final data block, load $4000", "sources": {}, "models": []}
    external = {}
    for platform, repo in REPOS.items():
        checkout = args.sources / platform
        revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if revision != REVISIONS[platform]:
            raise ValueError(f"Expected pinned {platform} revision {REVISIONS[platform]}, found {revision}")
        subprocess.run(["git", "-C", str(checkout), "diff", "--exit-code", "HEAD", "--", "1-source-files/main-sources"], check=True, capture_output=True)
        external[platform] = external_models(checkout, platform)
        result["sources"][platform] = {"repository": f"https://github.com/markmoxon/{repo}", "revision": revision,
            "variant": "STH/IB disc (not SRAM)" if platform == "bbc-disc" else "Unconditional geometry declarations"}
    for name, model in zip(NAMES, zx):
        validate_model(model)
        item = {"key": name, "zx": model, "comparisons": {}}
        for platform, models in external.items():
            # BBC cassette has one record per shape, with no pirate header.
            alias = name.removesuffix("_P") if platform == "bbc-cassette" else name
            other = models.get(alias)
            if other:
                validate_model(other)
            item["comparisons"][platform] = None if other is None else {"model": other, "differences": compare(model, other)}
        result["models"].append(item)
    out = ROOT / "docs/generated/ship-comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_tables(result, out.parent)
    if args.render:
        render_gallery(result, out.parent)
    for item in result["models"]:
        print(item["key"], {p: None if c is None else {k: len(v) for k, v in c["differences"].items()} for p,c in item["comparisons"].items()})


if __name__ == "__main__":
    main()
