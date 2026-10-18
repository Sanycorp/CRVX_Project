"""CRVX Sentinel - penjaga terbang pemburu mob add-on (The Locust dkk).

Semua kunci di berkas ini dicocokkan dengan bentuk resmi Mojang/MicrosoftDocs
(per Oktober 2026), bukan dikarang:

Entity behavior pack (``content/forms/entity``, 495 bentuk; yang dipakai di sini
terbukti ADA): ``minecraft:type_family``, ``health``, ``attack``,
``knockback_resistance``, ``fire_immune``, ``physics`` (``has_gravity``,
``has_collision``), ``pushable``, ``collision_box``, ``movement``,
``movement.fly``, ``navigation.fly``, ``jump.static``, ``can_fly``,
``breathable``, ``nameable``, ``persistent``, ``tameable``
(``probability``, ``tame_items``, ``tame_event``), ``is_tamed``,
``behavior.melee_attack``, ``behavior.nearest_attackable_target``,
``behavior.hurt_by_target``, ``behavior.owner_hurt_by_target``,
``behavior.owner_hurt_target``, ``behavior.follow_owner``,
``behavior.move_towards_target``, ``behavior.look_at_player``,
``behavior.random_look_around``.

Dipastikan TIDAK ADA di 495 bentuk resmi (jadi tidak dipakai): ``minecraft:gravity``,
``minecraft:is_summonable``, ``minecraft:behavior.avoid_entity``,
``minecraft:event_receiver``. Melayang dipakai lewat ``physics.has_gravity=false``
+ ``movement.fly`` + ``navigation.fly``, bukan lewat komponen gravity.

Client entity (meniru ``resource_pack/entity/blaze.entity.json`` vanilla):
``format_version`` 1.8.0+, ``description`` berisi ``identifier``,
``min_engine_version``, ``materials``, ``textures``, ``geometry``,
``render_controllers``, ``spawn_egg``.

Item telur spawn: komponen ``minecraft:entity_placer`` (butuh format_version item
>= 1.20.10) dengan field ``entity`` - inilah cara resmi menaruh entity ke dunia
tanpa mengandalkan telur vanilla.

Skrip ``@minecraft/server`` 2.0.0 (d.ts resmi): ``Entity.remove()`` ADA dan
dokumentasinya menyatakan entity dihapus *tanpa* animasi kematian dan *tanpa*
loot; ``Entity.kill()`` TIDAK ADA. ``dimension.getEntities({location,
maxDistance})`` persis contoh resmi d.ts. Itulah sebabnya pembersih di sini
memakai ``remove()``: mob yang kebal damage atau yang respawn saat mati tidak
sempat menjalankan logika kematiannya.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from .gearforge import (Atlas, BAJA_GELAP, BAJA_SOROT, BAJA_TERANG, BAJA_TENGAH,
                        GEO_FORMAT, ITEM_FORMAT, RECIPE_FORMAT, VOID_AKSEN,
                        VOID_UNGU, PUTIH_PANAS, campur, geometry, isi, kanvas,
                        kotak, kotak_px, px, tulang)

NS = "crvx"
SERI = "sentinel"
ENTITAS = f"{NS}:{SERI}"            # crvx:sentinel
TELUR = f"{NS}:{SERI}_egg"          # crvx:sentinel_egg
GEO_ID = f"geometry.{NS}.{SERI}"
TEKS_ENTITAS = f"textures/entity/{NS}_{SERI}"
IKON_TELUR = f"{NS}_{SERI}_egg"
NAMA_ENTITAS = "Sentinel Void"
NAMA_TELUR = "Telur Sentinel Void"

CLIENT_ENTITY_FORMAT = "1.10.0"     # >= 1.8.0 seperti blaze.entity.json vanilla

# --- statistik tempur (pembanding: wither skeleton 20 HP, iron golem 100 HP,
# --- warden 500 HP, netherite sword 8 damage, zombie 3 damage) -------------
NYAWA = 240
NYAWA_JINAK = 300
SERANGAN = 16
KECEPATAN = 0.42
RADIUS_BURU = 28
RADIUS_LINDUNG = 32
KOTAK_LEBAR = 0.9
KOTAK_TINGGI = 1.8

# Keluarga yang diburu. Selain keluarga vanilla, ikut keluarga tebakan yang
# lazim dipakai add-on "Locust"-an; kalau tidak ada yang cocok, filternya hanya
# tidak pernah aktif (tidak merusak apa pun).
KELUARGA_BURU = ("monster", "undead", "arthropod", "illager", "hostile",
                 "locust", "swarm", "insect", "bug", "hive", "plague")
# Keluarga yang TIDAK boleh disentuh - penjaga ini harus tetap "baik".
KELUARGA_AMAN = ("player", "animal", "villager", "npc", "tamed", "pet",
                 "inanimate", "item", "sentinel", "crvx", "boat", "minecart")


def _filter_keluarga(nilai: str, operator: str = "equals") -> Dict[str, object]:
    """Filter molang ``is_family`` sesuai bentuk resmi (test/subject/operator/value)."""
    f: Dict[str, object] = {"test": "is_family", "subject": "other", "value": nilai}
    if operator != "equals":
        f["operator"] = operator
    return f


def _tipe_buruan() -> List[Dict[str, object]]:
    """Daftar ``entity_types`` untuk ``behavior.nearest_attackable_target``.

    Tiap keluarga jadi entri sendiri: lebih tahan versi daripada satu
    ``any_of`` besar, dan radius keluarga tebakan dibuat lebih jauh.
    """
    out: List[Dict[str, object]] = []
    for kel in KELUARGA_BURU:
        jauh = RADIUS_LINDUNG if kel not in ("monster", "undead", "arthropod",
                                             "illager", "hostile") else RADIUS_BURU
        out.append({"filters": _filter_keluarga(kel), "max_dist": jauh})
    return out


# --------------------------------------------------------------------------- #
# Behavior pack: definisi entity
# --------------------------------------------------------------------------- #
def entity_bp() -> Dict[str, object]:
    """BP entity JSON. Hanya komponen yang terbukti ada di bentuk resmi."""
    komponen: Dict[str, object] = {
        "minecraft:type_family": {"family": ["sentinel", "crvx", "guardian", "mob"]},
        "minecraft:nameable": {},
        "minecraft:health": {"value": NYAWA, "max": NYAWA},
        "minecraft:attack": {"damage": SERANGAN},
        "minecraft:knockback_resistance": {"value": 1.0},
        "minecraft:fire_immune": {},                      # bentuk wither.json
        "minecraft:physics": {"has_gravity": False, "has_collision": True},
        "minecraft:pushable": {"is_pushable": True, "is_pushable_by_piston": True},
        "minecraft:collision_box": {"height": KOTAK_TINGGI, "width": KOTAK_LEBAR},
        "minecraft:movement": {"value": KECEPATAN},
        "minecraft:movement.fly": {},                     # bentuk parrot.json
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
        # --- otak penjaga ---
        "minecraft:behavior.hurt_by_target": {"priority": 0},
        "minecraft:behavior.owner_hurt_by_target": {"priority": 0},
        "minecraft:behavior.owner_hurt_target": {"priority": 1},
        "minecraft:behavior.nearest_attackable_target": {
            "priority": 2, "reselect_targets": True, "must_see": False,
            "within_radius": RADIUS_LINDUNG, "attack_interval": 1,
            "entity_types": _tipe_buruan()},
        "minecraft:behavior.melee_attack": {
            "priority": 1, "speed_multiplier": 1.45, "track_target": True,
            "cooldown_time": 0.6},
        "minecraft:behavior.move_towards_target": {
            "priority": 3, "speed_multiplier": 1.2, "within_range": 3},
        "minecraft:behavior.follow_owner": {
            "priority": 4, "speed_multiplier": 1.2, "start_distance": 12,
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
                "crvx:tame": {"add": {"component_groups": ["crvx:jinak"]}},
            },
        },
    }


# --------------------------------------------------------------------------- #
# Resource pack: client entity + geometry + tekstur
# --------------------------------------------------------------------------- #
def client_entity() -> Dict[str, object]:
    """RP client entity, meniru bentuk ``blaze.entity.json`` vanilla."""
    return {
        "format_version": CLIENT_ENTITY_FORMAT,
        "minecraft:client_entity": {
            "description": {
                "identifier": ENTITAS,
                "min_engine_version": CLIENT_ENTITY_FORMAT,
                "materials": {"default": "entity_alphatest"},
                "textures": {"default": TEKS_ENTITAS},
                "geometry": {"default": GEO_ID},
                "render_controllers": ["controller.render.default"],
                "spawn_egg": {"texture": IKON_TELUR},
            }
        },
    }


def geo_sentinel() -> Tuple[Dict[str, object], List[bytes]]:
    """Konstruk melayang: inti, mata, mahkota, halo, dua bilah samping.

    Tidak ada tulang kaki - navigation.fly membuat entity melayang, jadi model
    cukup satu akar ``body`` tanpa animation controller tambahan.
    """
    kv = kanvas(64, 64)
    at = Atlas(64, 64)

    inti = [kotak(kv, at, [-3, 11, -3], [6, 6, 6], BAJA_TENGAH, aksen=VOID_AKSEN),
            kotak(kv, at, [-1, 13, -4], [2, 2, 1], VOID_AKSEN, aksen=PUTIH_PANAS)]
    halo = [kotak(kv, at, [-4, 18, -4], [8, 1, 1], VOID_UNGU),
            kotak(kv, at, [-4, 18, 3], [8, 1, 1], VOID_UNGU),
            kotak(kv, at, [-4, 18, -3], [1, 1, 6], VOID_UNGU),
            kotak(kv, at, [3, 18, -3], [1, 1, 6], VOID_UNGU)]
    mahkota = [kotak(kv, at, [-1, 17, -1], [2, 3, 2], BAJA_TERANG, aksen=VOID_AKSEN),
               kotak(kv, at, [-3, 17, 0], [1, 2, 1], BAJA_TERANG),
               kotak(kv, at, [2, 17, 0], [1, 2, 1], BAJA_TERANG)]
    bilah_r = [kotak(kv, at, [-8, 10, -1], [2, 8, 2], BAJA_SOROT, aksen=VOID_AKSEN)]
    bilah_l = [kotak(kv, at, [6, 10, -1], [2, 8, 2], BAJA_SOROT, aksen=VOID_AKSEN)]
    jantung = [kotak(kv, at, [-2, 12, -2], [4, 4, 4], VOID_AKSEN, aksen=PUTIH_PANAS)]

    bones = [
        tulang("body", [0.0, 14.0, 0.0], None, cubes=inti + jantung),
        tulang("halo", [0.0, 19.0, 0.0], "body", cubes=halo),
        tulang("crown", [0.0, 17.0, 0.0], "body", cubes=mahkota),
        tulang("shardRight", [-6.0, 14.0, 0.0], "body", cubes=bilah_r,
               rotation=[0.0, 0.0, 16.0]),
        tulang("shardLeft", [6.0, 14.0, 0.0], "body", cubes=bilah_l,
               rotation=[0.0, 0.0, -16.0]),
    ]
    return geometry(GEO_ID, bones, 64, 64), [bytes(b) for b in kv]


def ikon_telur(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    """Ikon 16x16 telur spawn: cangkang gelap + urat energi cyan."""
    kv = kanvas(ukuran, ukuran)
    if ukuran != 16:
        return ukuran, ukuran, [bytes(b) for b in kv]
    # siluet telur membulat: sempit di puncak & dasar, lebar di tengah
    lebar = {2: (6, 4), 3: (5, 6), 4: (4, 8), 5: (4, 8), 6: (4, 8), 7: (4, 8),
             8: (4, 8), 9: (4, 8), 10: (4, 8), 11: (5, 6), 12: (5, 6),
             13: (6, 4)}
    for y, (x, w) in lebar.items():
        isi(kv, x, y, w, 1, (*campur(BAJA_TENGAH, BAJA_GELAP,
                                     0.15 + 0.55 * abs(y - 7.5) / 6.0), 255))
    # sorot lengkung kiri-atas (cangkang mengilap)
    for i, (x, y) in enumerate([(6, 2), (5, 3), (4, 4), (4, 5), (5, 6)]):
        px(kv, x, y, campur(BAJA_TENGAH, BAJA_SOROT, 0.85 - i * 0.12))
    for x, y in [(7, 2), (6, 3), (5, 4)]:
        px(kv, x, y, campur(BAJA_TENGAH, BAJA_SOROT, 0.55))
    # bayangan tepi kanan (volume)
    for y in range(4, 12):
        px(kv, 11, y, campur(BAJA_TENGAH, BAJA_GELAP, 0.7))
        px(kv, 4, y + 1, campur(BAJA_TENGAH, BAJA_GELAP, 0.6))
    # urat energi retak membelah cangkang
    for x, y in [(7, 4), (8, 5), (7, 6), (6, 7), (7, 8), (8, 9), (7, 10),
                 (8, 11), (7, 12)]:
        px(kv, x, y, VOID_AKSEN)
    for x, y in [(8, 5), (7, 8), (8, 11)]:
        px(kv, x, y, PUTIH_PANAS)
    for x, y in [(6, 6), (9, 8), (6, 10)]:
        px(kv, x, y, campur(VOID_AKSEN, BAJA_GELAP, 0.35))
    # pendar ungu di dasar (identitas CRVX)
    kotak_px(kv, 6, 13, 4, 1, VOID_UNGU)
    px(kv, 5, 12, campur(VOID_UNGU, BAJA_GELAP, 0.3))
    px(kv, 10, 12, campur(VOID_UNGU, BAJA_GELAP, 0.3))
    return 16, 16, [bytes(b) for b in kv]


def tekstur() -> Dict[str, Tuple[int, int, List[bytes]]]:
    geo_doc, rows = geo_sentinel()
    del geo_doc
    w, h, egg = ikon_telur(16)
    return {f"{TEKS_ENTITAS}.png": (64, 64, rows),
            f"textures/items/{IKON_TELUR}.png": (w, h, egg)}


def geometries() -> Dict[str, Dict[str, object]]:
    doc, _rows = geo_sentinel()
    return {f"models/entity/{NS}_{SERI}.geo.json": doc}


def client_entities() -> Dict[str, Dict[str, object]]:
    return {f"entity/{NS}_{SERI}.entity.json": client_entity()}


def item_texture() -> Dict[str, object]:
    """Registrasi ikon telur di ``textures/item_texture.json`` (bentuk vanilla)."""
    return {"resource_pack_name": f"{NS}_{SERI}",
            "texture_name": "atlas.items",
            "texture_data": {IKON_TELUR: {
                "textures": f"textures/items/{IKON_TELUR}"}}}


def bahasa() -> Dict[str, str]:
    """Teks lang RP: nama entity + nama item (pakai kunci resmi Bedrock)."""
    return {
        "texts/en_US.lang": (
            "pack.name=CRVX Sentinel - Model & Tekstur\n"
            "pack.description=Guardian construct that hunts hostile mobs\n"
            f"entity.{ENTITAS}.name={NAMA_ENTITAS}\n"
            f"item.{TELUR}=Void Sentinel Egg\n"
            f"tile.{NS}:{SERI}.name=Void Sentinel\n"),
        "texts/id_ID.lang": (
            "pack.name=CRVX Sentinel - Model & Tekstur\n"
            "pack.description=Konstruk penjaga pemburu mob musuh\n"
            f"entity.{ENTITAS}.name={NAMA_ENTITAS}\n"
            f"item.{TELUR}={NAMA_TELUR}\n"
            f"tile.{NS}:{SERI}.name={NAMA_ENTITAS}\n"),
    }


# --------------------------------------------------------------------------- #
# Item telur spawn + resep (bisa didapat tanpa Cheats)
# --------------------------------------------------------------------------- #
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
    """Resep shaped 1 kolom x 2 baris: echo shard di atas netherite ingot."""
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
    """Skrip BP ``scripts/sentinel.js`` (dibaca dari crvx/data/sentinel.js)."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "data", "sentinel.js"), encoding="utf-8") as fh:
        return fh.read()


def statistik() -> Dict[str, object]:
    """Ringkasan untuk CLI/README/jawaban pengguna."""
    return {
        "entity": ENTITAS,
        "nama": NAMA_ENTITAS,
        "nyawa": NYAWA,
        "nyawa_jinak": NYAWA_JINAK,
        "serangan": SERANGAN,
        "kecepatan": KECEPATAN,
        "radius_buru": RADIUS_BURU,
        "radius_lindung": RADIUS_LINDUNG,
        "melayang": True,
        "kebal_api": True,
        "kebal_knockback": 1.0,
        "keluarga_buru": list(KELUARGA_BURU),
        "keluarga_aman": list(KELUARGA_AMAN),
        "penjinak": "minecraft:echo_shard",
        "perintah": ["/scriptevent crvx:scan", "/scriptevent crvx:basmi 24",
                     "/scriptevent crvx:bantuan", f"/summon {ENTITAS}"],
        "pembanding": {"iron_golem": {"nyawa": 100, "serangan": 15},
                       "warden": {"nyawa": 500, "serangan": 30},
                       "wither_skeleton": {"nyawa": 20, "serangan": 5}},
    }
