"""CRVX Sentinel v3 - Ksatria Void: penjaga BERWUJUD MANUSIA yang tak bisa mati.

Lahir dari laporan lapangan: Sentinel v1 (konstruk melayang 240 HP) MATI
SEKETIKA melawan The Locust, dan The Locust kebal ``/kill``. v3 menjawab keduanya:

1. Tak bisa mati. ``minecraft:damage_sensor`` (bentuk iron_golem.json:
   ``{"triggers": [{"cause": ..., "deals_damage": "no"}]}``) menolak cause
   ``override`` - sebab damage yang dipakai ``/kill`` - plus fall/void/magic/
   wither/lava/explosion. Sisa damage yang masuk disembuhkan SKETIKA itu juga
   oleh skrip lewat ``EntityHealthComponent.resetToMaxValue()`` (contoh resmi
   d.ts @minecraft/server 2.0.0) pada ``world.afterEvents.entityHurt``.
   Jadi 1 HP pun tidak pernah hilang permanen.
2. Bisa membunuh yang kebal /kill. Tangga pembunuh di ``data/sentinel.js``:
   ``applyDamage(1e9, cause "override")`` -> teleport void y=-80 ->
   ``Entity.remove()`` (tanpa animasi mati & loot, sehingga event on-death
   add-on tidak pernah dijalankan -> respawn-nya mati kutu).
3. Berwujud manusia. Kerangka bone humanoid (body, head, armRight, armLeft,
   legRight, legLeft, cape, shard) dengan 23 kubus zirah ksatria.
4. Mutakhir kelihatan: tekstur HD 1024x1024 (UV skala 8x, pelukis gradien +
   rune + bintik deterministik), animasi melayang/jubah/orbit bilah meniru
   bentuk ``resource_pack/animations/vex.animation.json`` dan
   ``animation_controllers/vex.animation_controllers.json`` vanilla.

Semua komponen entity diambil dari 495 bentuk resmi ``content/forms/entity``
(29 komponen + ``minecraft:damage_sensor``); yang terbukti TIDAK ADA
(``minecraft:gravity``, ``minecraft:is_summonable``,
``minecraft:behavior.avoid_entity``, ``minecraft:event_receiver``) tetap
dilarang oleh ``verify_sentinel``.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from .gearforge import (Atlas, BAJA_GELAP, BAJA_SOROT, BAJA_TERANG, BAJA_TENGAH,
                        GEO_FORMAT, ITEM_FORMAT, RECIPE_FORMAT, VOID_AKSEN,
                        VOID_UNGU, PUTIH_PANAS, campur, geometry, isi, kanvas,
                        kotak_px, px, tulang)

NS = "crvx"
SERI = "sentinel"
ENTITAS = f"{NS}:{SERI}"
TELUR = f"{NS}:{SERI}_egg"
GEO_ID = f"geometry.{NS}.{SERI}"
TEKS_ENTITAS = f"textures/entity/{NS}_{SERI}"
IKON_TELUR = f"{NS}_{SERI}_egg"
NAMA_ENTITAS = "Ksatria Void (Sentinel)"
NAMA_TELUR = "Telur Ksatria Void"

CLIENT_ENTITY_FORMAT = "1.10.0"
ANIM_FORMAT = "1.8.0"          # sama dengan vex.animation.json vanilla
CTRL_FORMAT = "1.10.0"         # sama dengan vex.animation_controllers.json

# Tekstur HD: UV diskalakan 8x supaya tiap wajah zirah punya ruang detail
# (gradien tempa, baris rune, bintik logam) - bukan tekstur 64x64 yang buram
# saat didekati kamera.
TEKS_SIZE = 2048
SKALA = 16

# --- statistik tempur v3: laporan lapangan bilang v1 (240 HP) mati seketika -- #
NYAWA = 1000
NYAWA_JINAK = 1200
SERANGAN = 40                  # + efek wither IV 6 detik (bentuk wither_skeleton)
EFEK_SERANG = "wither"
EFEK_DETIK = 6
EFEK_AMPLIFIER = 3
KECEPATAN = 0.5
RADIUS_BURU = 28
RADIUS_LINDUNG = 32
KOTAK_LEBAR = 0.8
KOTAK_TINGGI = 1.95
SUARA_PANGGIL = "crvx.sentinel.summon"
SUARA_JINAK = "crvx.sentinel.jinak"
CAUSE_DITOLAK = ("override", "fall", "void", "magic", "wither", "lightning",
                 "fire_tick", "lava", "freezing", "entity_explosion",
                 "block_explosion", "sonic_boom")

KELUARGA_BURU = ("monster", "undead", "arthropod", "illager", "hostile",
                 "locust", "swarm", "insect", "bug", "hive", "plague")
KELUARGA_AMAN = ("player", "animal", "villager", "npc", "tamed", "pet",
                 "inanimate", "item", "sentinel", "crvx", "boat", "minecart")

# Bone wajib wujud manusia - verifier menolak model tanpa ini.
BONE_MANUSIA = ("body", "head", "armRight", "armLeft", "legRight", "legLeft")


def _filter_keluarga(nilai: str) -> Dict[str, object]:
    return {"test": "is_family", "subject": "other", "value": nilai}


def _tipe_buruan() -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for kel in KELUARGA_BURU:
        jauh = RADIUS_LINDUNG if kel not in ("monster", "undead", "arthropod",
                                             "illager", "hostile") else RADIUS_BURU
        out.append({"filters": _filter_keluarga(kel), "max_dist": jauh})
    return out


# --------------------------------------------------------------------------- #
# Pelukis HD (1024x1024, UV skala 8)
# --------------------------------------------------------------------------- #
def _bintik(x: int, y: int) -> float:
    """Noise deterministik 0..1 - logam tempa, bukan acak antar-build."""
    return ((x * 73856093) ^ (y * 19349663)) % 97 / 97.0


def lukis_hd(kv: List[bytearray], x: int, y: int, w: int, h: int,
             warna: Tuple[int, int, int], arah: str,
             aksen: Optional[Tuple[int, int, int]] = None) -> None:
    """Satu wajah kubus pada resolusi HD: gradien + rune + bintik + tepi."""
    if w <= 0 or h <= 0:
        return
    pasangan = {
        "atas": (campur(warna, BAJA_SOROT, 0.55), campur(warna, BAJA_TERANG, 0.30)),
        "bawah": (campur(warna, BAJA_GELAP, 0.55), campur(warna, BAJA_GELAP, 0.75)),
        "depan": (campur(warna, BAJA_TERANG, 0.35), campur(warna, BAJA_GELAP, 0.30)),
        "belakang": (campur(warna, BAJA_TENGAH, 0.10), campur(warna, BAJA_GELAP, 0.45)),
        "samping": (campur(warna, BAJA_TENGAH, 0.25), campur(warna, BAJA_GELAP, 0.35)),
    }[arah]
    for yy in range(h):
        t = yy / max(1, h - 1)
        dasar = campur(pasangan[0], pasangan[1], t)
        garis = (yy % 3 == 0)                 # garis kuas tempa horizontal
        for xx in range(w):
            n = _bintik(x + xx, y + yy)
            m = _bintik(x + xx // 2, y + yy * 3)
            r, g, b = dasar
            if n > 0.72:                      # kilau butir logam
                r, g, b = campur(dasar, BAJA_SOROT, 0.50)
            elif n < 0.22:                    # lekukan tempa
                r, g, b = campur(dasar, BAJA_GELAP, 0.42)
            if garis:
                r, g, b = campur((r, g, b), BAJA_GELAP, 0.16)
            if m > 0.93:                      # bintik mikro acak
                r, g, b = campur((r, g, b), PUTIH_PANAS, 0.30)
            if arah in ("depan", "samping"):
                if (xx + yy) % 41 == 0:       # goresan ukiran diagonal
                    r, g, b = campur((r, g, b), BAJA_GELAP, 0.55)
                elif (xx - yy) % 61 == 0:
                    r, g, b = campur((r, g, b), BAJA_SOROT, 0.45)
                g2 = _bintik(xx * 5 + yy, yy * 7 + xx)
                if g2 > 0.885:                # glif rune terukir
                    r, g, b = campur((r, g, b), VOID_UNGU, 0.35)
            isi(kv, x + xx, y + yy, 1, 1, (r, g, b, 255))
    tepi = max(2, min(w, h) // 12)
    isi(kv, x, y, w, tepi, (*campur(warna, BAJA_SOROT, 0.65), 255))
    isi(kv, x, y + h - tepi, w, tepi, (*campur(warna, BAJA_GELAP, 0.80), 255))
    isi(kv, x, y, tepi, h, (*campur(warna, BAJA_SOROT, 0.40), 255))
    isi(kv, x + w - tepi, y, tepi, h, (*campur(warna, BAJA_GELAP, 0.55), 255))
    if aksen and w > 24 and h > 24:           # baris rune energi
        step = max(6, h // 8)
        for yy in range(y + h // 3, y + h - tepi, step):
            for xx in range(x + tepi * 2, x + w - tepi * 2, 4):
                if _bintik(xx, yy) > 0.45:
                    isi(kv, xx, yy, 3, 2, (*aksen, 255))
        tengah = y + h // 2 - 2
        isi(kv, x + tepi * 2, tengah, w - tepi * 4, 3, (*aksen, 255))
        isi(kv, x + tepi * 2, tengah + 1, w - tepi * 4, 1, (*PUTIH_PANAS, 255))


def kotak_hd(kv: List[bytearray], atlas: Atlas, origin: Sequence[float],
             size: Sequence[int], warna: Tuple[int, int, int] = BAJA_TENGAH,
             aksen: Optional[Tuple[int, int, int]] = None) -> Dict[str, object]:
    """Kubus geometry dengan UV skala ``SKALA`` di tekstur HD."""
    w, h, d = (int(size[0]), int(size[1]), int(size[2]))
    s = SKALA
    bw, bh = 2 * (w + d) * s, (h + d) * s
    u, v = atlas.alokasi(bw, bh)
    lukis_hd(kv, u + d * s, v, w * s, d * s, warna, "atas")
    lukis_hd(kv, u + d * s + w * s, v, w * s, d * s, warna, "bawah")
    lukis_hd(kv, u, v + d * s, d * s, h * s, warna, "samping")
    lukis_hd(kv, u + d * s, v + d * s, w * s, h * s, warna, "depan", aksen=aksen)
    lukis_hd(kv, u + d * s + w * s, v + d * s, d * s, h * s, warna, "samping")
    lukis_hd(kv, u + d * s + w * s + d * s, v + d * s, w * s, h * s, warna,
             "belakang")
    return {"origin": [float(origin[0]), float(origin[1]), float(origin[2])],
            "size": [w, h, d], "uv": [u, v]}


# --------------------------------------------------------------------------- #
# Model ksatria humanoid (23 kubus)
# --------------------------------------------------------------------------- #
_GEO_CACHE: Dict[str, object] = {}


def geo_ksatria() -> Tuple[Dict[str, object], List[bytes]]:
    """Zirah ksatria void berwujud manusia: helm berpuncak, visor menyala,
    pauldron, jubah, greaves, sepatu besi, dua bilah melayang di sisi tubuh."""
    if "geo" in _GEO_CACHE:
        return _GEO_CACHE["geo"], _GEO_CACHE["rows"]  # type: ignore[return-value]
    kv = kanvas(TEKS_SIZE, TEKS_SIZE)
    at = Atlas(TEKS_SIZE, TEKS_SIZE)

    badan = [kotak_hd(kv, at, [-4, 13, -2], [8, 9, 4], BAJA_TENGAH, aksen=VOID_AKSEN),
             kotak_hd(kv, at, [-4, 11, -2], [8, 2, 4], BAJA_GELAP),
             kotak_hd(kv, at, [-1, 16, -3], [2, 2, 1], VOID_AKSEN, aksen=PUTIH_PANAS),
             kotak_hd(kv, at, [-7, 20, -2], [3, 3, 4], BAJA_TERANG, aksen=VOID_UNGU),
             kotak_hd(kv, at, [4, 20, -2], [3, 3, 4], BAJA_TERANG, aksen=VOID_UNGU)]
    kepala = [kotak_hd(kv, at, [-4, 22, -4], [8, 8, 8], BAJA_TENGAH),
              kotak_hd(kv, at, [-3, 25, -5], [6, 2, 1], VOID_AKSEN, aksen=PUTIH_PANAS),
              kotak_hd(kv, at, [-1, 30, -1], [2, 4, 2], VOID_UNGU, aksen=VOID_AKSEN)]
    lengan_r = [kotak_hd(kv, at, [-8, 12, -2], [4, 10, 4], BAJA_TENGAH),
                kotak_hd(kv, at, [-9, 12, -3], [5, 4, 5], BAJA_TERANG,
                         aksen=VOID_AKSEN)]
    lengan_l = [kotak_hd(kv, at, [4, 12, -2], [4, 10, 4], BAJA_TENGAH),
                kotak_hd(kv, at, [4, 12, -3], [5, 4, 5], BAJA_TERANG,
                         aksen=VOID_AKSEN)]
    kaki_r = [kotak_hd(kv, at, [-4, 2, -2], [4, 10, 4], BAJA_TENGAH),
              kotak_hd(kv, at, [-4, 0, -2], [4, 3, 4], BAJA_GELAP, aksen=VOID_UNGU),
              kotak_hd(kv, at, [-4, 0, -4], [4, 2, 2], BAJA_GELAP),
              kotak_hd(kv, at, [-4, 6, -3], [4, 3, 1], BAJA_TERANG)]
    kaki_l = [kotak_hd(kv, at, [0, 2, -2], [4, 10, 4], BAJA_TENGAH),
              kotak_hd(kv, at, [0, 0, -2], [4, 3, 4], BAJA_GELAP, aksen=VOID_UNGU),
              kotak_hd(kv, at, [0, 0, -4], [4, 2, 2], BAJA_GELAP),
              kotak_hd(kv, at, [0, 6, -3], [4, 3, 1], BAJA_TERANG)]
    pelat = [kotak_hd(kv, at, [-5, 10, -1], [1, 4, 3], BAJA_TERANG),
             kotak_hd(kv, at, [4, 10, -1], [1, 4, 3], BAJA_TERANG),
             kotak_hd(kv, at, [-4, 5, -3], [2, 3, 1], BAJA_TERANG, aksen=VOID_AKSEN),
             kotak_hd(kv, at, [2, 5, -3], [2, 3, 1], BAJA_TERANG, aksen=VOID_AKSEN),
             kotak_hd(kv, at, [-9, 16, -1], [1, 3, 3], BAJA_TERANG),
             kotak_hd(kv, at, [8, 16, -1], [1, 3, 3], BAJA_TERANG),
             kotak_hd(kv, at, [-3, 14, 2], [6, 7, 1], BAJA_GELAP, aksen=VOID_UNGU),
             kotak_hd(kv, at, [-5, 28, -2], [1, 4, 1], VOID_UNGU, aksen=VOID_AKSEN),
             kotak_hd(kv, at, [4, 28, -2], [1, 4, 1], VOID_UNGU, aksen=VOID_AKSEN)]
    jubah = [kotak_hd(kv, at, [-4, 9, 3], [8, 13, 1], VOID_UNGU, aksen=VOID_AKSEN)]
    bilah_r = [kotak_hd(kv, at, [-11, 13, -1], [2, 7, 2], BAJA_SOROT, aksen=VOID_AKSEN)]
    bilah_l = [kotak_hd(kv, at, [9, 13, -1], [2, 7, 2], BAJA_SOROT, aksen=VOID_AKSEN)]

    bones = [
        tulang("body", [0.0, 12.0, 0.0], None, cubes=badan + pelat),
        tulang("head", [0.0, 22.0, 0.0], "body", cubes=kepala),
        tulang("armRight", [-6.0, 21.0, 0.0], "body", cubes=lengan_r,
               rotation=[0.0, 0.0, -6.0]),
        tulang("armLeft", [6.0, 21.0, 0.0], "body", cubes=lengan_l,
               rotation=[0.0, 0.0, 6.0]),
        tulang("legRight", [-2.0, 12.0, 0.0], "body", cubes=kaki_r,
               rotation=[0.0, 0.0, 3.0]),
        tulang("legLeft", [2.0, 12.0, 0.0], "body", cubes=kaki_l,
               rotation=[0.0, 0.0, -3.0]),
        tulang("cape", [0.0, 21.0, 3.0], "body", cubes=jubah,
               rotation=[8.0, 0.0, 0.0]),
        tulang("shardRight", [-10.0, 16.0, 0.0], "body", cubes=bilah_r),
        tulang("shardLeft", [10.0, 16.0, 0.0], "body", cubes=bilah_l),
    ]
    doc = geometry(GEO_ID, bones, TEKS_SIZE, TEKS_SIZE)
    rows = [bytes(b) for b in kv]
    _GEO_CACHE["geo"], _GEO_CACHE["rows"] = doc, rows
    return doc, rows


def animasi() -> Dict[str, object]:
    """Bentuk ``resource_pack/animations/vex.animation.json`` (keyframe waktu)."""
    return {
        "format_version": ANIM_FORMAT,
        "animations": {
            "animation.crvx.sentinel.hover": {
                "loop": True,
                "bones": {"body": {"position": {
                    "0.0": [0.0, 0.0, 0.0],
                    "1.0": [0.0, 1.6, 0.0],
                    "2.0": [0.0, 0.0, 0.0]}}},
            },
            "animation.crvx.sentinel.cape": {
                "loop": True,
                "bones": {"cape": {"rotation": {
                    "0.0": [6.0, 0.0, 0.0],
                    "1.0": [13.0, 0.0, 0.0],
                    "2.0": [6.0, 0.0, 0.0]}}},
            },
            "animation.crvx.sentinel.orbit": {
                "loop": True,
                "bones": {
                    "shardRight": {"rotation": {"0.0": [0.0, 0.0, 0.0],
                                                "2.0": [0.0, 360.0, 0.0]}},
                    "shardLeft": {"rotation": {"0.0": [0.0, 0.0, 0.0],
                                               "2.0": [0.0, -360.0, 0.0]}},
                },
            },
        },
    }


def controllers() -> Dict[str, object]:
    """Bentuk ``animation_controllers/vex.animation_controllers.json``."""
    return {
        "format_version": CTRL_FORMAT,
        "animation_controllers": {
            "controller.animation.crvx.sentinel": {
                "initial_state": "default",
                "states": {"default": {"animations": ["hover", "cape", "orbit"]}},
            }
        },
    }


def client_entity() -> Dict[str, object]:
    return {
        "format_version": CLIENT_ENTITY_FORMAT,
        "minecraft:client_entity": {
            "description": {
                "identifier": ENTITAS,
                "min_engine_version": CLIENT_ENTITY_FORMAT,
                "materials": {"default": "entity_alphatest"},
                "textures": {"default": TEKS_ENTITAS},
                "geometry": {"default": GEO_ID},
                "animations": {
                    "hover": "animation.crvx.sentinel.hover",
                    "cape": "animation.crvx.sentinel.cape",
                    "orbit": "animation.crvx.sentinel.orbit",
                },
                "animation_controllers": [
                    {"move": "controller.animation.crvx.sentinel"}],
                "render_controllers": ["controller.render.default"],
                "spawn_egg": {"texture": IKON_TELUR},
            }
        },
    }


# --------------------------------------------------------------------------- #
# Behavior pack: entity tak bisa mati
# --------------------------------------------------------------------------- #
def entity_bp() -> Dict[str, object]:
    komponen: Dict[str, object] = {
        "minecraft:type_family": {"family": ["sentinel", "crvx", "guardian", "mob"]},
        "minecraft:nameable": {},
        "minecraft:health": {"value": NYAWA, "max": NYAWA},
        "minecraft:attack": {"damage": SERANGAN, "effect_name": EFEK_SERANG,
                             "effect_duration": EFEK_DETIK,
                             "effect_amplifier": EFEK_AMPLIFIER},
        "minecraft:knockback_resistance": {"value": 1.0},
        "minecraft:fire_immune": {},
        # Perisai utama: /kill memakai cause "override" - ditolak mentah-mentah.
        "minecraft:damage_sensor": {
            "triggers": [{"cause": c, "deals_damage": "no"}
                         for c in CAUSE_DITOLAK]},
        "minecraft:physics": {"has_gravity": False, "has_collision": True},
        "minecraft:pushable": {"is_pushable": True, "is_pushable_by_piston": True},
        "minecraft:collision_box": {"height": KOTAK_TINGGI, "width": KOTAK_LEBAR},
        "minecraft:movement": {"value": KECEPATAN},
        "minecraft:movement.fly": {},
        "minecraft:navigation.fly": {"can_path_from_air": True,
                                     "can_path_over_water": True},
        "minecraft:jump.static": {},
        "minecraft:can_fly": {},
        "minecraft:breathable": {"total_supply": 15, "suffocate_time": 0,
                                 "breathes_air": True, "breathes_water": True},
        "minecraft:persistent": {},
        "minecraft:tameable": {"probability": 1.0,
                               "tame_items": ["minecraft:echo_shard"],
                               "tame_event": {"event": "crvx:tame", "target": "self"}},
        "minecraft:behavior.hurt_by_target": {"priority": 0},
        "minecraft:behavior.owner_hurt_by_target": {"priority": 0},
        "minecraft:behavior.owner_hurt_target": {"priority": 1},
        "minecraft:behavior.nearest_attackable_target": {
            "priority": 2, "reselect_targets": True, "must_see": False,
            "within_radius": RADIUS_LINDUNG, "attack_interval": 1,
            "entity_types": _tipe_buruan()},
        "minecraft:behavior.melee_attack": {
            "priority": 1, "speed_multiplier": 1.6, "track_target": True,
            "cooldown_time": 0.4},
        "minecraft:behavior.move_towards_target": {
            "priority": 3, "speed_multiplier": 1.3, "within_range": 3},
        "minecraft:behavior.follow_owner": {
            "priority": 4, "speed_multiplier": 1.3, "start_distance": 12,
            "min_distance": 3, "max_distance": 24, "can_teleport": True},
        "minecraft:behavior.look_at_player": {"priority": 8, "look_distance": 8},
        "minecraft:behavior.random_look_around": {"priority": 9},
    }
    return {
        "format_version": "1.21.0",
        "minecraft:entity": {
            "description": {
                "identifier": ENTITAS,
                "is_spawnable": True,
                "is_summonable": True,
                "is_experimental": False,
            },
            "component_groups": {
                "crvx:jinak": {
                    "minecraft:is_tamed": {},
                    "minecraft:health": {"value": NYAWA_JINAK, "max": NYAWA_JINAK},
                }
            },
            "components": komponen,
            "events": {
                "crvx:tame": {"sequence": [
                    {"add": {"component_groups": ["crvx:jinak"]}},
                    {"play_sound": {"sound": SUARA_JINAK}},
                ]},
                "minecraft:entity_spawned": {"sequence": [
                    {"play_sound": {"sound": SUARA_PANGGIL}},
                ]},
            },
        },
    }


# --------------------------------------------------------------------------- #
# Tekstur, ikon, lang, item, resep
# --------------------------------------------------------------------------- #
def ikon_telur(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    lebar = {2: (6, 4), 3: (5, 6), 4: (4, 8), 5: (4, 8), 6: (4, 8), 7: (4, 8),
             8: (4, 8), 9: (4, 8), 10: (4, 8), 11: (5, 6), 12: (5, 6),
             13: (6, 4)}
    for y, (x, w) in lebar.items():
        isi(kv, x, y, w, 1, (*campur(BAJA_TENGAH, BAJA_GELAP,
                                     0.15 + 0.55 * abs(y - 7.5) / 6.0), 255))
    for i, (x, y) in enumerate([(6, 2), (5, 3), (4, 4), (4, 5), (5, 6)]):
        px(kv, x, y, campur(BAJA_TENGAH, BAJA_SOROT, 0.85 - i * 0.12))
    for x, y in [(7, 2), (6, 3), (5, 4)]:
        px(kv, x, y, campur(BAJA_TENGAH, BAJA_SOROT, 0.55))
    for y in range(4, 12):
        px(kv, 11, y, campur(BAJA_TENGAH, BAJA_GELAP, 0.7))
        px(kv, 4, y + 1, campur(BAJA_TENGAH, BAJA_GELAP, 0.6))
    for x, y in [(7, 4), (8, 5), (7, 6), (6, 7), (7, 8), (8, 9), (7, 10),
                 (8, 11), (7, 12)]:
        px(kv, x, y, VOID_AKSEN)
    for x, y in [(8, 5), (7, 8), (8, 11)]:
        px(kv, x, y, PUTIH_PANAS)
    for x, y in [(6, 6), (9, 8), (6, 10)]:
        px(kv, x, y, campur(VOID_AKSEN, BAJA_GELAP, 0.35))
    kotak_px(kv, 6, 13, 4, 1, VOID_UNGU)
    px(kv, 5, 12, campur(VOID_UNGU, BAJA_GELAP, 0.3))
    px(kv, 10, 12, campur(VOID_UNGU, BAJA_GELAP, 0.3))
    return 16, 16, [bytes(b) for b in kv]


def tekstur() -> Dict[str, Tuple[int, int, List[bytes]]]:
    _doc, rows = geo_ksatria()
    _w, _h, egg = ikon_telur(16)
    return {f"{TEKS_ENTITAS}.png": (TEKS_SIZE, TEKS_SIZE, rows),
            f"textures/items/{IKON_TELUR}.png": (16, 16, egg)}


def geometries() -> Dict[str, Dict[str, object]]:
    doc, _rows = geo_ksatria()
    return {f"models/entity/{NS}_{SERI}.geo.json": doc}


def animations_files() -> Dict[str, Dict[str, object]]:
    return {f"animations/{NS}_{SERI}.animation.json": animasi(),
            f"animation_controllers/{NS}_{SERI}.animation_controllers.json":
                controllers()}


def client_entities() -> Dict[str, Dict[str, object]]:
    return {f"entity/{NS}_{SERI}.entity.json": client_entity()}


def item_texture() -> Dict[str, object]:
    return {"resource_pack_name": f"{NS}_{SERI}",
            "texture_name": "atlas.items",
            "texture_data": {IKON_TELUR: {
                "textures": f"textures/items/{IKON_TELUR}"}}}


def bahasa() -> Dict[str, str]:
    return {
        "texts/en_US.lang": (
            "pack.name=CRVX Sentinel - Model & Tekstur\n"
            "pack.description=Unkillable void knight that hunts hostile mobs\n"
            f"entity.{ENTITAS}.name={NAMA_ENTITAS}\n"
            f"item.{TELUR}=Void Knight Egg\n"),
        "texts/id_ID.lang": (
            "pack.name=CRVX Sentinel - Model & Tekstur\n"
            "pack.description=Ksatria void tak bisa mati, pemburu mob musuh\n"
            f"entity.{ENTITAS}.name={NAMA_ENTITAS}\n"
            f"item.{TELUR}={NAMA_TELUR}\n"),
    }


def item_telur() -> Dict[str, object]:
    return {
        "format_version": ITEM_FORMAT,
        "minecraft:item": {
            "description": {"identifier": TELUR,
                            "menu_category": {"category": "nature"}},
            "components": {
                "minecraft:icon": {"texture": IKON_TELUR},
                "minecraft:display_name": {"value": NAMA_TELUR},
                "minecraft:max_stack_size": 16,
                "minecraft:entity_placer": {"entity": ENTITAS},
                "minecraft:tags": {"tags": ["minecraft:spawn_egg"]},
            },
        },
    }


def resep_telur() -> Dict[str, object]:
    return {
        "format_version": RECIPE_FORMAT,
        "minecraft:recipe_shaped": {
            "description": {"identifier": f"{NS}:{SERI}_egg_craft"},
            "tags": ["crafting_table"],
            "pattern": ["E", "N"],
            "key": {"E": {"item": "minecraft:echo_shard"},
                    "N": {"item": "minecraft:netherite_ingot"}},
            "unlock": [{"item": "minecraft:echo_shard"}],
            "result": {"item": TELUR, "count": 1},
        },
    }


def items() -> Dict[str, Dict[str, object]]:
    return {f"items/{NS}_{SERI}_egg.json": item_telur()}


def recipes() -> Dict[str, Dict[str, object]]:
    return {f"recipes/{NS}_{SERI}_egg.json": resep_telur()}


def entities() -> Dict[str, Dict[str, object]]:
    return {f"entities/{NS}_{SERI}.json": entity_bp()}


def skrip() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "data", "sentinel.js"), encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# Suara: disintesis deterministik (stdlib wave) - tanpa aset pihak ketiga
# --------------------------------------------------------------------------- #
import math
import wave
import io as _io

RATE = 48000


def _wav(samples: List[float]) -> bytes:
    buf = _io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        data = bytearray()
        for smp in samples:
            v = max(-1.0, min(1.0, smp))
            data += int(v * 32767).to_bytes(2, "little", signed=True)
        w.writeframes(bytes(data))
    return buf.getvalue()


def _suara_panggil(durasi: float = 2.6) -> bytes:
    """Raungan void: sapuan 70->190 Hz + cincin logam + desis energi."""
    n = int(RATE * durasi)
    out = []
    for i in range(n):
        t = i / RATE
        sapu = 70.0 + 120.0 * min(1.0, t / 1.1)
        inti = math.sin(2 * math.pi * sapu * t) * 0.55
        cincin = (math.sin(2 * math.pi * 618 * t) * 0.16 *
                  math.exp(-2.2 * t) +
                  math.sin(2 * math.pi * 927 * t) * 0.10 * math.exp(-3.1 * t))
        desis = (_bintik(i, 7) - 0.5) * 0.16 * min(1.0, t * 6) * \
            math.exp(-0.9 * t)
        amp = min(1.0, t * 9) * math.exp(-0.85 * max(0.0, t - 1.1))
        out.append((inti + cincin + desis) * amp)
    return _wav(out)


def _suara_jinak(durasi: float = 1.6) -> bytes:
    """Lonceng penjinakan: nada naik 440->880 Hz dengan kemilau harmonik."""
    n = int(RATE * durasi)
    out = []
    for i in range(n):
        t = i / RATE
        f = 440.0 * (2 ** min(1.0, t / 0.7))
        nada = math.sin(2 * math.pi * f * t) * 0.5
        kilau = math.sin(2 * math.pi * f * 2.02 * t) * 0.18 * math.exp(-2.5 * t)
        amp = min(1.0, t * 20) * math.exp(-1.6 * max(0.0, t - 0.5))
        out.append((nada + kilau) * amp)
    return _wav(out)


_SUARA_CACHE: Dict[str, bytes] = {}


def suara() -> Dict[str, bytes]:
    if not _SUARA_CACHE:
        _SUARA_CACHE[f"sounds/{NS}_{SERI}_summon.wav"] = _suara_panggil()
        _SUARA_CACHE[f"sounds/{NS}_{SERI}_jinak.wav"] = _suara_jinak()
    return dict(_SUARA_CACHE)


def sound_definitions() -> Dict[str, object]:
    return {
        "format_version": "1.26.50",
        "sound_definitions": {
            SUARA_PANGGIL: {"category": "hostile",
                            "sounds": [{"name": f"sounds/{NS}_{SERI}_summon",
                                        "volume": 0.9, "is3D": True}]},
            SUARA_JINAK: {"category": "neutral",
                          "sounds": [{"name": f"sounds/{NS}_{SERI}_jinak",
                                      "volume": 0.8, "is3D": True}]},
        },
    }


def statistik() -> Dict[str, object]:
    return {
        "entity": ENTITAS,
        "nama": NAMA_ENTITAS,
        "wujud": "manusia (ksatria zirah void, 9 bone, 32 kubus)",
        "tekstur": f"{TEKS_SIZE}x{TEKS_SIZE} (UV skala {SKALA}x)",
        "suara": ["summon (raungan void 2.6 d, 48 kHz)", "jinak (lonceng 1.6 d)"],
        "nyawa": NYAWA,
        "nyawa_jinak": NYAWA_JINAK,
        "serangan": SERANGAN,
        "efek_serang": f"{EFEK_SERANG} {EFEK_AMPLIFIER + 1} / {EFEK_DETIK} detik",
        "kecepatan": KECEPATAN,
        "radius_buru": RADIUS_BURU,
        "radius_lindung": RADIUS_LINDUNG,
        "melayang": True,
        "kebal_api": True,
        "kebal_knockback": 1.0,
        "tolak_cause": list(CAUSE_DITOLAK),
        "sembuh_instan": "resetToMaxValue() tiap entityHurt",
        "keluarga_buru": list(KELUARGA_BURU),
        "keluarga_aman": list(KELUARGA_AMAN),
        "penjinak": "minecraft:echo_shard",
        "perintah": ["/scriptevent crvx:scan", "/scriptevent crvx:basmi 24",
                     "/scriptevent crvx:auto on", "/scriptevent crvx:lepas 16",
                     "/scriptevent crvx:bantuan", f"/summon {ENTITAS}"],
        "pembanding": {"iron_golem": {"nyawa": 100, "serangan": 15},
                       "warden": {"nyawa": 500, "serangan": 30},
                       "wither_skeleton": {"nyawa": 20, "serangan": 5}},
    }
