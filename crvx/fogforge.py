"""FogForge - 80 definisi fog Bedrock dengan skema yang BENAR.

Skema diverifikasi langsung dari Mojang/bedrock-samples (Okt 2026). Setiap file
fog vanilla berbentuk:

    {
      "format_version": "1.21.90",
      "minecraft:fog_settings": {
        "description": {"identifier": "minecraft:fog_forest"},
        "distance": {"water": {...}}
      }
    }

SATU definisi per file, ``minecraft:fog_settings`` di level atas. Tidak ada
array ``fog_definitions`` di mana pun dalam vanilla - format itu tidak dibaca
game, jadi pack yang memakainya tidak melakukan apa-apa.

Fakta yang dikumpulkan dari 80 file vanilla (tersimpan di data/fog_index.json):
    65x distance = [water]
     7x distance = [air, water, weather]
     6x distance = [air, lava, lava_resistance, water, weather]
     1x distance = [air, water]
     1x distance = [powder_snow]
     format_version: 50x 1.21.90, 30x 1.16.100
     2 identifier tidak sama dengan nama file (mega_spruce_taiga_mutated,
       sulfur_caves) - karena itu identifier tidak boleh ditebak dari nama file.

Keputusan keselamatan: identifier yang punya kunci ``lava``, ``lava_resistance``,
atau ``powder_snow`` TIDAK ditimpa. Menimpa tanpa kunci itu akan menghapus fog
lava/salju-bubuk vanilla dan merusak pengalaman bermain. 73 dari 80 ditimpa.

Catatan jujur: fog TIDAK mengurangi beban GPU secara berarti - fog hanyalah
lerp murah per fragmen, geometri tetap digambar. Nilai fog di sini adalah
**menyamarkan render distance rendah** supaya batas chunk tidak terlihat, yang
memungkinkan kamu menurunkan Render Distance (tuas performa yang sesungguhnya)
tanpa mengorbankan tampilan.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "fog_index.json")

# kunci yang tidak boleh disentuh - nilainya spesifik gameplay
SKIP_KEYS = {"lava", "lava_resistance", "powder_snow"}

# palet warna air karangan sendiri per keluarga bioma (bukan data Mojang)
WATER_PALETTE: Tuple[Tuple[str, Tuple[str, str]], ...] = (
    ("ocean", ("#1B6FA8", "#0E4C7A")),
    ("river", ("#2A7FB8", "#155C8A")),
    ("swamp", ("#4A5D32", "#2E3D1F")),
    ("mangrove", ("#4A5D32", "#2E3D1F")),
    ("mesa", ("#8A6A4A", "#5E4630")),
    ("desert", ("#4FA3C7", "#2E7A9C")),
    ("ice", ("#7FB6D8", "#4E87AC")),
    ("frozen", ("#7FB6D8", "#4E87AC")),
    ("cold", ("#3E7FA8", "#255C7E")),
    ("jungle", ("#2E8B6A", "#1A5E45")),
    ("bamboo", ("#2E8B6A", "#1A5E45")),
    ("forest", ("#2C7FA0", "#18556F")),
    ("taiga", ("#2F6E86", "#1B4A5C")),
    ("savanna", ("#4E9AA8", "#2E6C79")),
    ("plains", ("#3D8FB8", "#246486")),
    ("beach", ("#37A0C4", "#1F7391")),
    ("mushroom", ("#7A5FA8", "#4E3A72")),
    ("hell", ("#8A2A1A", "#54150C")),
    ("crimson", ("#8A2A3A", "#54151F")),
    ("warped", ("#1E6E7A", "#0F454E")),
    ("soulsand", ("#4A4038", "#2C2620")),
    ("basalt", ("#4A4A52", "#2C2C33")),
    ("end", ("#2A1E4A", "#170F2C")),
    ("cave", ("#2E4A5A", "#1A2E3A")),
    ("cherry", ("#4E86B8", "#2E5C86")),
    ("pale", ("#5A6A78", "#38444E")),
)
WATER_DEFAULT = ("#2A7FA8", "#155C7E")


def load_index() -> Dict[str, Dict[str, object]]:
    """identifier -> {file, format_version, distance[]} dari data otoritatif."""
    with open(INDEX_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def water_color(identifier: str) -> Tuple[str, str]:
    name = identifier.replace("minecraft:fog_", "")
    for kunci, warna in WATER_PALETTE:
        if kunci in name:
            return warna
    return WATER_DEFAULT


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    out = [int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)]
    return "#" + "".join(f"{max(0, min(255, v)):02X}" for v in out)


def air_fog(density: float, tint: str) -> Dict[str, object]:
    """Fog udara sebagai penyamar batas chunk. ``density`` 0..1."""
    density = max(0.0, min(1.0, density))
    start = round(0.92 - 0.58 * density, 3)
    end = round(min(1.0, start + 0.42 + 0.10 * density), 3)
    return {"fog_start": start, "fog_end": end, "fog_color": tint,
            "render_distance_type": "render"}


def weather_fog(density: float, tint: str) -> Dict[str, object]:
    density = max(0.0, min(1.0, density))
    start = round(0.80 - 0.55 * density, 3)
    end = round(min(1.0, start + 0.35 + 0.10 * density), 3)
    return {"fog_start": start, "fog_end": end, "fog_color": tint,
            "render_distance_type": "render"}


def water_fog(density: float, identifier: str) -> Dict[str, object]:
    dekat, jauh = water_color(identifier)
    end = round(max(12.0, 60.0 - 34.0 * density), 2)
    return {"fog_start": 0.0, "fog_end": end,
            "fog_color": _mix(dekat, jauh, density),
            "render_distance_type": "fixed"}


def fog_definition(identifier: str, distance_keys: List[str],
                   density: float = 0.55) -> Optional[Dict[str, object]]:
    """Satu dokumen fog. ``None`` bila identifier sengaja tidak ditimpa."""
    if SKIP_KEYS.intersection(distance_keys):
        return None
    tint_far, tint_near = water_color(identifier)
    tint = _mix(tint_far, "#0B1220", 0.35 + 0.3 * density)
    distance: Dict[str, object] = {}
    for key in distance_keys:
        if key == "air":
            distance["air"] = air_fog(density, tint)
        elif key == "weather":
            distance["weather"] = weather_fog(density, tint)
        elif key == "water":
            distance["water"] = water_fog(density, identifier)
    if not distance:
        # bioma yang vanilla-nya cuma punya air/water: tambahkan air supaya
        # penyamaran batas chunk berlaku juga di bioma itu
        distance["air"] = air_fog(density, tint)
        if "water" in distance_keys:
            distance["water"] = water_fog(density, identifier)
    return {
        "format_version": "1.21.90",
        "minecraft:fog_settings": {
            "description": {"identifier": identifier},
            "distance": distance,
        },
    }


def fog_files(density: float = 0.55) -> Dict[str, Dict[str, object]]:
    """relpath dalam resource pack -> dokumen fog, untuk seluruh identifier."""
    out: Dict[str, Dict[str, object]] = {}
    for identifier, meta in sorted(load_index().items()):
        doc = fog_definition(identifier, list(meta.get("distance", [])), density)
        if doc is None:
            continue
        out[f"fogs/{meta['file']}_fog_setting.json"] = doc
    return out


def skipped() -> List[str]:
    """Identifier yang sengaja tidak ditimpa (punya lava/powder_snow)."""
    return sorted(i for i, m in load_index().items()
                  if SKIP_KEYS.intersection(set(m.get("distance", []))))


def coverage() -> Dict[str, int]:
    index = load_index()
    return {"total": len(index), "ditimpa": len(fog_files()),
            "dilewati": len(skipped())}
