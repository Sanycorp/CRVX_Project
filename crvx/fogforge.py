"""FogForge v3.3 - enam definisi fog yang benar-benar dipakai biome.

SEJARAH (kenapa file ini ditulis ulang setelah laporan force-close):

Versi lama mengirim 73 file fog. Audit menemukan dua cacat sekaligus:

1. **Salah sasaran.** Empat identifier global yang dipakai mayoritas biome
   overworld - ``minecraft:fog_default``, ``fog_dry``, ``fog_humid``,
   ``fog_semi_humid`` - justru TIDAK terkirim, karena versi lama memakai
   aturan "lewati identifier yang punya blok lava" agar fog lava tidak rusak.
   Yang terkirim malah nether/end/goa. Jadi biaya parsing 73 JSON saat dunia
   dimuat itu nyata, sementara manfaat visualnya di overworld nyaris nol.

2. **Boros saat muat dunia.** 73 dokumen fog dibaca dan diregistrasi setiap
   kali dunia dimuat. Di perangkat RAM 4 GB itu beban yang tidak perlu untuk
   fitur yang murni kosmetik.

Perbaikan v3.3: hanya enam identifier yang menentukan tampilan sebagian besar
dunia (empat global overworld + nether + end), dan **setiap blok vanilla
disalin verbatim** - termasuk ``lava``, ``lava_resistance``, ``transition_fog``,
dan ``fog_color`` - sehingga tidak ada satu pun tampilan vanilla yang hilang.
Yang disetel hanya jarak ``air``/``weather``.

Bentuk dokumen diverifikasi langsung dari Mojang/bedrock-samples (Okt 2026):
SATU definisi per file, ``minecraft:fog_settings`` di level atas, tanpa array
``fog_definitions`` (format itu tidak dibaca game). ``render_distance_type``
hanya boleh ``"render"`` (kelipatan render distance) atau ``"fixed"`` (blok).

Catatan jujur: fog TIDAK mengurangi beban GPU secara berarti - fog hanyalah
lerp murah per fragmen, geometri tetap digambar. Nilainya adalah **menyamarkan
batas chunk** supaya Render Distance bisa diturunkan (tuas performa yang
sesungguhnya) tanpa dunia terlihat terpotong.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "fog_index.json")

# Enam identifier yang menentukan tampilan sebagian besar dunia. Nilai blok
# air/lava/lava_resistance/warna disalin verbatim dari vanilla; hanya jarak
# air/weather yang disetel oleh ``density``.
VERBATIM = {
    "minecraft:fog_default": {
        "file": "default", "format_version": "1.16.100",
        "air": {"fog_color": "#ABD2FF", "render_distance_type": "render",
                "vanilla": (0.92, 1.0)},
        "weather": {"fog_color": "#666666", "render_distance_type": "render",
                    "vanilla": (0.23, 0.7)},
        "water": {"fog_start": 0.0, "fog_end": 60.0, "fog_color": "#44AFF5",
                  "render_distance_type": "fixed", "transition_fog": True},
        "lava": {"fog_start": 0.0, "fog_end": 0.64, "fog_color": "#991A00",
                 "render_distance_type": "fixed"},
        "lava_resistance": {"fog_start": 2.0, "fog_end": 4.0,
                            "fog_color": "#991A00",
                            "render_distance_type": "fixed"},
    },
    "minecraft:fog_dry": {
        "file": "dry", "format_version": "1.21.90",
        "air": {"fog_color": "#ABD2FF", "render_distance_type": "render",
                "vanilla": (0.92, 1.0)},
        "weather": {"fog_color": "#666666", "render_distance_type": "render",
                    "vanilla": (0.23, 0.7)},
        "water": {"fog_start": 0.0, "fog_end": 60.0, "fog_color": "#44AFF5",
                  "render_distance_type": "fixed", "transition_fog": True},
        "lava": {"fog_start": 0.0, "fog_end": 0.64, "fog_color": "#991A00",
                 "render_distance_type": "fixed"},
        "lava_resistance": {"fog_start": 2.0, "fog_end": 4.0,
                            "fog_color": "#991A00",
                            "render_distance_type": "fixed"},
    },
    "minecraft:fog_humid": {
        "file": "humid", "format_version": "1.21.90",
        "air": {"fog_color": "#ABD2FF", "render_distance_type": "render",
                "vanilla": (0.92, 1.0)},
        "weather": {"fog_color": "#666666", "render_distance_type": "render",
                    "vanilla": (0.23, 0.7)},
        "water": {"fog_start": 0.0, "fog_end": 60.0, "fog_color": "#44AFF5",
                  "render_distance_type": "fixed", "transition_fog": True},
        "lava": {"fog_start": 0.0, "fog_end": 0.64, "fog_color": "#991A00",
                 "render_distance_type": "fixed"},
        "lava_resistance": {"fog_start": 2.0, "fog_end": 4.0,
                            "fog_color": "#991A00",
                            "render_distance_type": "fixed"},
    },
    "minecraft:fog_semi_humid": {
        "file": "semi_humid", "format_version": "1.21.90",
        "air": {"fog_color": "#ABD2FF", "render_distance_type": "render",
                "vanilla": (0.92, 1.0)},
        "weather": {"fog_color": "#666666", "render_distance_type": "render",
                    "vanilla": (0.23, 0.7)},
        "water": {"fog_start": 0.0, "fog_end": 60.0, "fog_color": "#44AFF5",
                  "render_distance_type": "fixed", "transition_fog": True},
        "lava": {"fog_start": 0.0, "fog_end": 0.64, "fog_color": "#991A00",
                 "render_distance_type": "fixed"},
        "lava_resistance": {"fog_start": 2.0, "fog_end": 4.0,
                            "fog_color": "#991A00",
                            "render_distance_type": "fixed"},
    },
    # nether: air & weather vanilla bertipe "fixed" (meter, bukan render distance)
    "minecraft:fog_hell": {
        "file": "hell", "format_version": "1.16.100",
        "air": {"fog_color": "#330808", "render_distance_type": "fixed",
                "vanilla": (10.0, 96.0)},
        "weather": {"fog_color": "#330808", "render_distance_type": "fixed",
                    "vanilla": (10.0, 96.0)},
        "water": {"fog_start": 0.0, "fog_end": 15.0, "fog_color": "#905957",
                  "render_distance_type": "fixed", "transition_fog": True},
    },
    "minecraft:fog_the_end": {
        "file": "the_end", "format_version": "1.21.90",
        "air": {"fog_color": "#0B080C", "render_distance_type": "render",
                "vanilla": (0.92, 1.0)},
        "water": {"fog_start": 0.0, "fog_end": 15.0, "fog_color": "#62529e",
                  "render_distance_type": "fixed", "transition_fog": True},
    },
}

# transisi masuk-keluar air, identik di semua file vanilla yang memakainya
_TRANSITION_PCT = {"min_percent": 0.25, "mid_seconds": 5,
                   "mid_percent": 0.6, "max_seconds": 30}

TARGETS: List[str] = [
    "minecraft:fog_default", "minecraft:fog_dry", "minecraft:fog_humid",
    "minecraft:fog_semi_humid", "minecraft:fog_hell", "minecraft:fog_the_end",
]


def load_index() -> Dict[str, Dict[str, object]]:
    """identifier -> {file, format_version, distance[]} dari data otoritatif."""
    with open(INDEX_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _transition(warna: str, end: float) -> Dict[str, object]:
    return {"init_fog": {"fog_start": 0.0, "fog_end": 0.01,
                         "fog_color": warna, "render_distance_type": "fixed"},
            **_TRANSITION_PCT}


def tuned(blok: Dict[str, object], density: float) -> Dict[str, object]:
    """Jarak air/weather yang disetel, warna & tipe tetap verbatim vanilla."""
    density = max(0.0, min(1.0, density))
    warna = blok["fog_color"]
    tipe = blok["render_distance_type"]
    v_start, v_end = blok["vanilla"]
    if tipe == "render":
        # udara: kabut mulai lebih dekat -> batas chunk tersamar
        start = round(v_start - 0.30 * density, 3)
        end = round(max(start + 0.05, v_end - 0.12 * density), 3)
    else:
        # nether: satuan blok, diperpendek sebanding density
        start = v_start
        end = round(max(start + 4.0, v_end - 36.0 * density), 1)
    return {"fog_start": start, "fog_end": end, "fog_color": warna,
            "render_distance_type": tipe}


def water_fog(identifier: str) -> Dict[str, object]:
    """Blok air verbatim vanilla (tidak disetel - murni kosmetik)."""
    src = dict(VERBATIM[identifier]["water"])
    pakai_transisi = src.pop("transition_fog", False)
    if pakai_transisi:
        src["transition_fog"] = _transition(src["fog_color"], src["fog_end"])
    return src


def fog_definition(identifier: str,
                   density: float = 0.35) -> Optional[Dict[str, object]]:
    """Satu dokumen fog, atau ``None`` bila identifier bukan target."""
    spec = VERBATIM.get(identifier)
    if spec is None:
        return None
    distance: Dict[str, object] = {}
    for key in ("air", "weather"):
        if key in spec:
            distance[key] = tuned(spec[key], density)
    if "water" in spec:
        distance["water"] = water_fog(identifier)
    for key in ("lava", "lava_resistance"):
        if key in spec:
            distance[key] = dict(spec[key])
    return {"format_version": spec["format_version"],
            "minecraft:fog_settings": {
                "description": {"identifier": identifier},
                "distance": distance}}


def fog_files(density: float = 0.35) -> Dict[str, Dict[str, object]]:
    """relpath dalam resource pack -> dokumen fog (enam identifier target)."""
    out: Dict[str, Dict[str, object]] = {}
    for identifier in TARGETS:
        doc = fog_definition(identifier, density)
        if doc is None:
            continue
        out[f"fogs/{VERBATIM[identifier]['file']}_fog_setting.json"] = doc
    return out


def skipped() -> List[str]:
    """Identifier vanilla yang tidak ditimpa di luar enam target."""
    return sorted(set(load_index()) - set(VERBATIM))


def coverage() -> Dict[str, int]:
    index = load_index()
    return {"total": len(index), "ditimpa": len(fog_files()),
            "dilewati": len(skipped())}
