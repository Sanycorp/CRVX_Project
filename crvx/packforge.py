"""PackForge - membangun .mcpack Bedrock yang valid tanpa dependensi eksternal.

Termasuk encoder PNG murni (zlib + struct) untuk ikon pack dan definisi fog
yang dipangkas untuk mengurangi fragmen alpha-blended.
"""

from __future__ import annotations

import json
import os
import struct
import uuid
import zipfile
import zlib
from typing import Dict, List, Tuple

NAMESPACE = uuid.UUID("6f1c9a2e-4c7b-4d31-9c0a-2b7d5e8f1a40")
MIN_ENGINE = [1, 20, 0]

FOG_IDENTIFIERS = [
    ("default", "minecraft:fog_default", "#ABD2FF"),
    ("the_end", "minecraft:fog_the_end", "#0B0824"),
    ("hell", "minecraft:fog_hell", "#330303"),
    ("water", "minecraft:fog_water", "#1A3A6B"),
    ("lava", "minecraft:fog_lava", "#4A0A00"),
    ("ice_plains", "minecraft:fog_ice_plains", "#D8ECF5"),
    ("desert", "minecraft:fog_desert", "#E4D6A8"),
    ("jungle", "minecraft:fog_jungle", "#B8E0A8"),
    ("forest", "minecraft:fog_forest", "#C8E6B0"),
    ("swamp", "minecraft:fog_swamp", "#B6C7A1"),
    ("mushroom_island", "minecraft:fog_mushroom_island", "#D9C2E0"),
    ("ocean", "minecraft:fog_ocean", "#A9CBEC"),
    ("river", "minecraft:fog_river", "#BFD8EE"),
    ("roofed_forest", "minecraft:fog_roofed_forest", "#A8C89A"),
    ("savanna", "minecraft:fog_savanna", "#E0D8A8"),
    ("taiga", "minecraft:fog_taiga", "#C6D8E4"),
]


# --------------------------------------------------------------------------- #
# PNG encoder minimal (RGBA 8-bit, non-interlaced)
# --------------------------------------------------------------------------- #
def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: str, width: int, height: int, pixels: List[bytes]) -> None:
    raw = b"".join(b"\x00" + row for row in pixels)
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def make_icon(size: int = 128, accent: Tuple[int, int, int] = (244, 114, 182)) -> List[bytes]:
    """Ikon prosedural: gradien gelap + kilau aksen + garis FPS."""
    rows: List[bytes] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            nx, ny = x / size, y / size
            diagonal = (nx + ny) / 2.0
            glow = max(0.0, 1.0 - abs(ny - 0.62 - 0.16 * (0.5 - nx)) * 7.0)
            base = int(14 + 26 * diagonal)
            r = min(255, int(base + accent[0] * glow * 0.85))
            g = min(255, int(base + accent[1] * glow * 0.85))
            b = min(255, int(base + 10 + accent[2] * glow * 0.85))
            border = 1 if (x < 3 or y < 3 or x >= size - 3 or y >= size - 3) else 0
            if border:
                r, g, b = accent
            row += bytes((r, g, b, 255))
        rows.append(bytes(row))
    return rows


# --------------------------------------------------------------------------- #
# Fog definitions
# --------------------------------------------------------------------------- #
def fog_definition(identifier: str, color: str, start: float, end: float) -> Dict[str, object]:
    water = identifier.endswith("water") or identifier.endswith("lava")
    distance: Dict[str, object] = {}
    if water:
        distance["water"] = {
            "fog_start": round(start * 0.5, 3), "fog_end": round(end * 0.6, 3),
            "fog_color": color, "render_distance_type": "fixed",
            "max_density": {"max_density": 0.9, "max_density_height": 8,
                            "uniform": True, "zero_density_height": 40},
        }
    else:
        distance["air"] = {
            "fog_start": round(start, 3), "fog_end": round(end, 3),
            "fog_color": color, "render_distance_type": "render",
        }
        distance["weather"] = {
            "fog_start": round(min(0.95, start + 0.1), 3),
            "fog_end": round(min(1.0, end + 0.05), 3),
            "fog_color": color, "render_distance_type": "render",
        }
    return {
        "identifier": identifier,
        "minecraft:fog_settings": {
            "description": {"identifier": f"crvx:fog_cut_{identifier}"},
            "distance": distance,
        },
    }


def fog_file(strength: float = 0.85) -> Dict[str, object]:
    definitions = []
    for name, identifier, color in FOG_IDENTIFIERS:
        start = round(min(0.92, 0.55 + 0.35 * strength), 3)
        end = round(min(1.0, start + 0.12), 3)
        definitions.append(fog_definition(identifier, color, start, end))
    return {"format_version": "1.16.100", "fog_definitions": definitions}


def manifest(name: str, description: str, version: List[int]) -> Dict[str, object]:
    header_uuid = str(uuid.uuid5(NAMESPACE, f"{name}-header"))
    module_uuid = str(uuid.uuid5(NAMESPACE, f"{name}-module"))
    return {
        "format_version": 2,
        "header": {
            "name": name,
            "description": description,
            "uuid": header_uuid,
            "version": version,
            "min_engine_version": MIN_ENGINE,
        },
        "modules": [{
            "type": "resources",
            "uuid": module_uuid,
            "version": version,
        }],
        "metadata": {
            "product_type": "addon",
            "url": "https://github.com/Sanycorp/CRVX_Project",
            "generated_by": "CRVX TurboFrame PackForge",
        },
    }


def build_fogcut_pack(out_path: str, strength: float = 0.85,
                      version: List[int] | None = None) -> str:
    """Tulis crvx-fogcut.mcpack. Kembalikan path-nya."""
    version = version or [1, 1, 0]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    tmp_dir = out_path + ".src"
    os.makedirs(os.path.join(tmp_dir, "fogs"), exist_ok=True)
    icon_path = os.path.join(tmp_dir, "pack_icon.png")
    write_png(icon_path, 128, 128, make_icon())

    with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest("CRVX Fog-Cut Performance",
                           "Pangkas jarak fog per bioma untuk mengurangi overdraw "
                           "transparan. Dibuat oleh CRVX TurboFrame.", version),
                  fh, indent=2, ensure_ascii=False)
    with open(os.path.join(tmp_dir, "fogs", "crvx_fog_cut.json"), "w", encoding="utf-8") as fh:
        json.dump(fog_file(strength), fh, indent=2, ensure_ascii=False)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(tmp_dir):
            for fname in sorted(files):
                full = os.path.join(root, fname)
                zf.write(full, os.path.relpath(full, tmp_dir))
    for root, _dirs, files in os.walk(tmp_dir, topdown=False):
        for fname in files:
            os.remove(os.path.join(root, fname))
        os.rmdir(root)
    return out_path


def verify_pack(path: str) -> Dict[str, object]:
    """Validasi struktur pack supaya tidak gagal import di Bedrock."""
    result: Dict[str, object] = {"path": path, "ok": False, "problems": []}
    problems: List[str] = []
    if not os.path.exists(path):
        problems.append("file tidak ada")
        result["problems"] = problems
        return result
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                problems.append("manifest.json tidak ada di root zip")
            else:
                data = json.loads(zf.read("manifest.json").decode("utf-8"))
                header = data.get("header", {})
                modules = data.get("modules", [])
                if not header.get("uuid"):
                    problems.append("header.uuid kosong")
                if not modules or modules[0].get("type") != "resources":
                    problems.append("modules[0].type harus 'resources'")
                if header.get("uuid") and modules and modules[0].get("uuid") == header.get("uuid"):
                    problems.append("uuid header dan module tidak boleh sama")
                if not header.get("min_engine_version"):
                    problems.append("min_engine_version tidak ada")
            if "pack_icon.png" not in names:
                problems.append("pack_icon.png tidak ada (opsional tapi disarankan)")
            result["entries"] = names
            result["size_bytes"] = os.path.getsize(path)
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
        problems.append(f"arsip rusak: {exc}")
    result["problems"] = problems
    result["ok"] = not problems
    return result
