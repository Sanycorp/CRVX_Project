"""GearForge - armor 3D + pedang Bedrock, dibangun dari skema yang diverifikasi.

Bukan tebakan. Setiap bentuk berkas di modul ini diturunkan dari sumber resmi:

Mojang/bedrock-samples (diambil Okt 2026)
  * ``resource_pack/models/entity/player_armor.json``
      -> nama bone, parent, pivot, origin, size, dan uv kerangka armor pemain:
         waist(neverRender) <- body <- {head <- hat, rightArm <- rightItem,
         leftArm, rightLeg, leftLeg}. Ukuran badan: origin[-4,12,-2] size[8,12,4].
         Armor bikinan WAJIB memakai bone & pivot ini supaya ikut bergerak.
  * ``resource_pack/attachables/diamond_helmet.json`` (+ varian ``.player.json``)
      -> bentuk attachable armor: materials armor/armor_enchanted, geometry,
         render_controllers ["controller.render.armor"], identifier ``<item>.player``
         dengan pemetaan ``item`` + ``query.owner_identifier == 'minecraft:player'``.
  * ``behavior_pack/items/netherite_spear.json`` (format_version 1.21.100)
      -> komponen senjata: minecraft:damage {value}, durability {max_durability,
         damage_chance}, enchantable {slot,value}, repairable {repair_items},
         hand_equipped {value}, fire_resistant {value}, icon {textures:{default}}.
  * ``behavior_pack/recipes/diamond_sword.json`` / ``diamond_chestplate.json``
      -> minecraft:recipe_shaped {description.identifier, tags:["crafting_table"],
         pattern, key, unlock, result}.
  * ``resource_pack/textures/item_texture.json``
      -> texture_name "atlas.items", texture_data {kunci: {textures: path}}.

MicrosoftDocs/minecraft-creator
  * ``content/forms/item/minecraft_wearable.form.json``
      -> slot resmi: slot.armor.head/chest/legs/feet (+body, weapon.mainhand/offhand),
         field ``protection`` (int, default 0).
  * ``content/forms/item/minecraft_enchantable.form.json``
      -> pola slot resmi: none|all|g_armor|armor_head|armor_torso|armor_feet|
         armor_legs|sword|bow|spear|crossbow|melee_spear|g_tool|hoe|shears|
         flintsteel|shield|g_digging|axe|pickaxe|shovel|fishing_rod|carrot_stick|
         elytra|cosmetic_head
  * ``content/forms/item/description.form.json``
      -> description = {identifier (wajib), menu_category{category,group,
         is_hidden_in_commands}}; category sah: construction|equipment|items|
         nature|none.
  * ``creator/Documents/AddCustomItems.md`` (tutorial resmi item 3D dipegang)
      -> attachable senjata: item mapping ``query.is_owner_identifier_any(
         'minecraft:player')``, materials entity/entity_alphatest_glint, animasi
         bawaan ``animation.steve_head.hold_first_person`` & ``hold_third_person``
         yang dipilih lewat ``scripts.animate`` + ``context.is_first_person``,
         render_controllers ["controller.render.item_default"], dan geometry dengan
         ``"binding": "q.item_slot_to_bone_name(context.item_slot)"``.

Catatan jujur soal tampilan: ikon di inventory/hotbar SELALU sprite 2D - itu
batasan mesin Bedrock, bukan kekurangan pack. Yang benar-benar 3D adalah model
yang menempel di tubuh (armor) dan di tangan (pedang), lewat attachable+geometry.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

NS = "crvx"
SERI = "void"

# --------------------------------------------------------------------------- #
# Kerangka pemain - disalin dari vanilla player_armor.json
# --------------------------------------------------------------------------- #
WAIST_PIVOT = [0.0, 12.0, 0.0]
BODY_PIVOT = [0.0, 24.0, 0.0]
ARM_R_PIVOT = [-5.0, 22.0, 0.0]
ARM_L_PIVOT = [5.0, 22.0, 0.0]
LEG_R_PIVOT = [-1.9, 12.0, 0.0]
LEG_L_PIVOT = [1.9, 12.0, 0.0]

# (origin, size, uv) tubuh vanilla; armor kita membungkusnya dengan inflate
BADAN = ([-4.0, 12.0, -2.0], [8, 12, 4])
KEPALA = ([-4.0, 24.0, -4.0], [8, 8, 8])
LENGAN_R = ([-8.0, 12.0, -2.0], [4, 12, 4])
LENGAN_L = ([4.0, 12.0, -2.0], [4, 12, 4])
KAKI_R = ([-3.9, 0.0, -2.0], [4, 12, 4])
KAKI_L = ([-0.1, 0.0, -2.0], [4, 12, 4])

# --------------------------------------------------------------------------- #
# Palet: baja lubang hitam + aksen energi
# --------------------------------------------------------------------------- #
BAJA_GELAP = (22, 25, 34)
BAJA_TENGAH = (48, 54, 70)
BAJA_TERANG = (98, 108, 132)
BAJA_SOROT = (158, 170, 198)
VOID_AKSEN = (86, 224, 255)      # cyan energi
VOID_UNGU = (154, 88, 246)       # ungu lubang hitam
PUTIH_PANAS = (236, 252, 255)

ITEM_FORMAT = "1.21.100"         # sama dengan netherite_spear.json vanilla
RECIPE_FORMAT = "1.20.10"        # sama dengan diamond_sword.json vanilla
ATTACH_ARMOR_FORMAT = "1.10.0"   # sama dengan diamond_helmet.player.json vanilla
ATTACH_ITEM_FORMAT = "1.20.30"   # sama dengan tutorial resmi AddCustomItems
GEO_FORMAT = "1.16.0"            # sama dengan spear.geo.json / wrench.geo.json

PIECE = ("helmet", "chestplate", "leggings", "boots")
SLOT_WEARABLE = {"helmet": "slot.armor.head", "chestplate": "slot.armor.chest",
                 "leggings": "slot.armor.legs", "boots": "slot.armor.feet"}
SLOT_ENCHANT = {"helmet": "armor_head", "chestplate": "armor_torso",
                "leggings": "armor_legs", "boots": "armor_feet",
                "blade": "sword"}
NAMA_ID = {"helmet": "Helm Singularitas", "chestplate": "Zirah Singularitas",
           "leggings": "Tungkai Singularitas", "boots": "Sepatu Singularitas",
           "blade": "Pedang Singularitas"}
# perlindungan: total 20 = plafon armor Bedrock (sama seperti netherite penuh),
# tapi durability & enchantability jauh di atasnya
PROTEKSI = {"helmet": 3, "chestplate": 8, "leggings": 6, "boots": 3}
DURABILITAS = {"helmet": 1620, "chestplate": 2140, "leggings": 1980,
               "boots": 1460, "blade": 2600}
ENCHANT_VALUE = 25               # netherite 15 -> enchantment lebih bagus
DAMAGE_BLADE = 11                # netherite sword 8


def item_id(bagian: str) -> str:
    return f"{NS}:{SERI}_{bagian}"


def ikon_id(bagian: str) -> str:
    return f"{NS}_{SERI}_{bagian}"


# --------------------------------------------------------------------------- #
# Kanvas & atlas UV
# --------------------------------------------------------------------------- #
def kanvas(w: int, h: int) -> List[bytearray]:
    return [bytearray(w * 4) for _ in range(h)]


def isi(kv: List[bytearray], x: int, y: int, w: int, h: int,
        rgba: Tuple[int, int, int, int]) -> None:
    r, g, b, a = rgba
    for yy in range(max(0, y), min(len(kv), y + h)):
        baris = kv[yy]
        for xx in range(max(0, x), min(len(baris) // 4, x + w)):
            o = xx * 4
            baris[o] = r; baris[o + 1] = g; baris[o + 2] = b; baris[o + 3] = a


def campur(a: Tuple[int, ...], b: Tuple[int, ...], t: float) -> Tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * max(0.0, min(1.0, t))))
                 for i in range(3))


def baris_png(kv: List[bytearray]) -> List[bytes]:
    return [bytes(b) for b in kv]


class Atlas:
    """Pengalokasi UV shelf-packing: tiap kotak butuh (2w+2d) x (h+d) piksel.

    Tata letak box-UV Bedrock untuk kubus ukuran (w,h,d) pada uv (u,v):
        atas   : (u+d,     v)   ukuran (w, d)
        bawah  : (u+d+w,   v)   ukuran (w, d)
        kanan  : (u,       v+d) ukuran (d, h)
        depan  : (u+d,     v+d) ukuran (w, h)
        kiri   : (u+d+w,   v+d) ukuran (d, h)
        belakang: (u+d+w+d, v+d) ukuran (w, h)
    """

    def __init__(self, lebar: int = 64, tinggi: int = 64, padding: int = 1):
        self.lebar = lebar
        self.tinggi = tinggi
        self.padding = padding
        self._x = 0
        self._y = 0
        self._rak = 0
        self.terpakai: List[Tuple[int, int, int, int]] = []

    def alokasi(self, bw: int, bh: int) -> Tuple[int, int]:
        pad = self.padding
        if self._x + bw + pad > self.lebar:
            self._x = 0
            self._y += self._rak + pad
            self._rak = 0
        if self._y + bh + pad > self.tinggi:
            raise ValueError(f"atlas {self.lebar}x{self.tinggi} penuh "
                             f"(butuh {bw}x{bh} lagi)")
        u, v = self._x, self._y
        self._x += bw + pad
        self._rak = max(self._rak, bh)
        self.terpakai.append((u, v, bw, bh))
        return u, v

    def tumpang(self) -> List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]]:
        """Pasangan kotak yang saling menimpa (harus kosong)."""
        out = []
        for i, a in enumerate(self.terpakai):
            for b in self.terpakai[i + 1:]:
                if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and
                        a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                    out.append((a, b))
        return out


def lukis_wajah(kv: List[bytearray], x: int, y: int, w: int, h: int,
                dasar: Tuple[int, int, int], arah: str,
                aksen: Optional[Tuple[int, int, int]] = None,
                garis: bool = True) -> None:
    """Lukis satu wajah kotak dengan gradien + tepi, agar terlihat ditempa."""
    if w <= 0 or h <= 0:
        return
    atas, bawah = {
        "atas": (campur(dasar, BAJA_SOROT, 0.55), campur(dasar, BAJA_TERANG, 0.30)),
        "bawah": (campur(dasar, BAJA_GELAP, 0.55), campur(dasar, BAJA_GELAP, 0.75)),
        "depan": (campur(dasar, BAJA_TERANG, 0.30), campur(dasar, BAJA_GELAP, 0.25)),
        "belakang": (campur(dasar, BAJA_TENGAH, 0.10), campur(dasar, BAJA_GELAP, 0.45)),
        "samping": (campur(dasar, BAJA_TENGAH, 0.22), campur(dasar, BAJA_GELAP, 0.35)),
    }[arah]
    for yy in range(h):
        t = yy / max(1, h - 1)
        r, g, b = campur(atas, bawah, t)
        isi(kv, x, y + yy, w, 1, (r, g, b, 255))
    if garis and w >= 3 and h >= 3:
        tepi = campur(dasar, BAJA_SOROT, 0.70)
        isi(kv, x, y, w, 1, (*tepi, 255))
        isi(kv, x, y + h - 1, w, 1, (*campur(dasar, BAJA_GELAP, 0.8), 255))
    if aksen and w >= 2 and h >= 2:
        ay = y + max(0, h // 2 - 1)
        isi(kv, x + 1, ay, max(1, w - 2), min(2, max(1, h - 2)), (*aksen, 255))
        if h >= 4 and w >= 3:
            isi(kv, x + 1, ay, max(1, w - 2), 1, (*PUTIH_PANAS, 255))


def kotak(kv: List[bytearray], atlas: Atlas, origin: Sequence[float],
          size: Sequence[int], warna: Tuple[int, int, int] = BAJA_TENGAH,
          aksen: Optional[Tuple[int, int, int]] = None,
          inflate: float = 0.0) -> Dict[str, object]:
    """Satu kubus geometry + lukisan UV-nya. ``size`` harus bilangan bulat
    supaya kotak UV tidak pecah menjadi piksel sebagian."""
    w, h, d = (int(size[0]), int(size[1]), int(size[2]))
    bw, bh = 2 * (w + d), h + d
    u, v = atlas.alokasi(bw, bh)
    lukis_wajah(kv, u + d, v, w, d, warna, "atas")
    lukis_wajah(kv, u + d + w, v, w, d, warna, "bawah")
    lukis_wajah(kv, u, v + d, d, h, warna, "samping")
    lukis_wajah(kv, u + d, v + d, w, h, warna, "depan", aksen=aksen)
    lukis_wajah(kv, u + d + w, v + d, d, h, warna, "samping")
    lukis_wajah(kv, u + d + w + d, v + d, w, h, warna, "belakang")
    cube: Dict[str, object] = {"origin": [float(origin[0]), float(origin[1]),
                                          float(origin[2])],
                               "size": [w, h, d], "uv": [u, v]}
    if inflate:
        cube["inflate"] = inflate
    return cube


def tulang(nama: str, pivot: Sequence[float], parent: Optional[str] = None,
           cubes: Optional[List[Dict[str, object]]] = None,
           never: bool = False, rotation: Optional[Sequence[float]] = None,
           binding: Optional[str] = None) -> Dict[str, object]:
    b: Dict[str, object] = {"name": nama,
                            "pivot": [float(pivot[0]), float(pivot[1]), float(pivot[2])]}
    if parent:
        b["parent"] = parent
    if never:
        b["neverRender"] = True
    if rotation:
        b["rotation"] = [float(r) for r in rotation]
    if binding:
        b["binding"] = binding
    if cubes:
        b["cubes"] = cubes
    return b


RANTAI = (("waist", WAIST_PIVOT, None), ("body", BODY_PIVOT, "waist"),
          ("head", BODY_PIVOT, "body"),
          ("rightArm", ARM_R_PIVOT, "body"), ("leftArm", ARM_L_PIVOT, "body"),
          ("rightLeg", LEG_R_PIVOT, "body"), ("leftLeg", LEG_L_PIVOT, "body"))


def kerangka(render: Optional[Dict[str, List[Dict[str, object]]]] = None
             ) -> List[Dict[str, object]]:
    """Rantai tulang pemain lengkap. Bone yang ada di ``render`` membawa kubus
    (digambar); sisanya ``neverRender``.

    Meniru warisan ``geometry.player.armor.*`` vanilla: setiap potongan armor
    tetap membawa rantai waist->body->{head,rightArm,leftArm,rightLeg,leftLeg}
    supaya menempel benar saat pemain bergerak, jongkok, atau berenang.
    """
    render = render or {}
    return [tulang(nama, pivot, parent, cubes=render.get(nama),
                   never=(nama not in render))
            for nama, pivot, parent in RANTAI]


def geometry(identifier: str, bones: List[Dict[str, object]],
             tw: int = 64, th: int = 64) -> Dict[str, object]:
    return {"format_version": GEO_FORMAT,
            "minecraft:geometry": [{
                "description": {"identifier": identifier, "texture_width": tw,
                                "texture_height": th, "visible_bounds_width": 3,
                                "visible_bounds_height": 4,
                                "visible_bounds_offset": [0, 1, 0]},
                "bones": bones}]}


# --------------------------------------------------------------------------- #
# Geometry tiap potongan: armor 3D berlapis + pedang
# --------------------------------------------------------------------------- #
def geo_helmet() -> Tuple[Dict[str, object], List[bytes]]:
    kv = kanvas(64, 64); at = Atlas(64, 64)
    bones = kerangka({"head": [
        kotak(kv, at, KEPALA[0], KEPALA[1], BAJA_TENGAH,
              aksen=VOID_AKSEN, inflate=0.55)]})
    # jambul bertingkat ke belakang
    bones.append(tulang("crest", BODY_PIVOT, "head", [
        kotak(kv, at, [-1, 32, -4], [2, 2, 8], BAJA_TERANG, aksen=VOID_UNGU),
        kotak(kv, at, [-1, 34, -2], [2, 2, 5], BAJA_TERANG, aksen=VOID_AKSEN),
        kotak(kv, at, [-1, 36, 1], [2, 3, 2], VOID_AKSEN)]))
    # tanduk menyamping (pivot di sisi kepala agar rotasinya wajar)
    bones.append(tulang("hornRight", [-4.0, 28.0, 0.0], "head", [
        kotak(kv, at, [-7, 29, -2], [3, 2, 4], BAJA_TERANG),
        kotak(kv, at, [-9, 30, -1], [2, 2, 2], VOID_UNGU)], rotation=[0, 0, -22]))
    bones.append(tulang("hornLeft", [4.0, 28.0, 0.0], "head", [
        kotak(kv, at, [4, 29, -2], [3, 2, 4], BAJA_TERANG),
        kotak(kv, at, [7, 30, -1], [2, 2, 2], VOID_UNGU)], rotation=[0, 0, 22]))
    # pelindung wajah + celah energi
    bones.append(tulang("visor", BODY_PIVOT, "head", [
        kotak(kv, at, [-4, 25, -5], [8, 4, 1], BAJA_GELAP),
        kotak(kv, at, [-3, 26, -6], [6, 1, 1], VOID_AKSEN)]))
    return (geometry(f"geometry.{NS}.{SERI}_helmet", bones), baris_png(kv))


def geo_chestplate() -> Tuple[Dict[str, object], List[bytes]]:
    kv = kanvas(64, 64); at = Atlas(64, 64)
    bones = kerangka({
        "body": [kotak(kv, at, BADAN[0], BADAN[1], BAJA_TENGAH,
                       aksen=VOID_UNGU, inflate=0.70)],
        "rightArm": [kotak(kv, at, LENGAN_R[0], LENGAN_R[1], BAJA_TENGAH,
                           inflate=0.60)],
        "leftArm": [kotak(kv, at, LENGAN_L[0], LENGAN_L[1], BAJA_TENGAH,
                          inflate=0.60)]})
    bones.append(tulang("core", BODY_PIVOT, "body", [
        kotak(kv, at, [-2, 18, -4], [4, 4, 2], BAJA_GELAP),
        kotak(kv, at, [-1, 19, -5], [2, 2, 1], VOID_AKSEN)]))
    bones.append(tulang("spine", BODY_PIVOT, "body", [
        kotak(kv, at, [-1, 20, 2], [2, 3, 2], BAJA_TERANG, aksen=VOID_UNGU),
        kotak(kv, at, [-1, 16, 2], [2, 3, 2], BAJA_TERANG),
        kotak(kv, at, [-1, 13, 2], [2, 2, 1], VOID_UNGU)]))
    for sisi, pivot, x0, induk in (("Right", ARM_R_PIVOT, -10, "rightArm"),
                                   ("Left", ARM_L_PIVOT, 4, "leftArm")):
        bones.append(tulang(f"pauldron{sisi}", pivot, induk, [
            kotak(kv, at, [x0, 20, -3], [6, 2, 6], BAJA_TERANG, aksen=VOID_AKSEN),
            kotak(kv, at, [x0 + 1, 22, -2], [4, 2, 4], BAJA_TERANG),
            kotak(kv, at, [x0 + 1, 24, -1], [3, 2, 2], VOID_UNGU)]))
    return (geometry(f"geometry.{NS}.{SERI}_chestplate", bones), baris_png(kv))


def geo_leggings() -> Tuple[Dict[str, object], List[bytes]]:
    kv = kanvas(64, 64); at = Atlas(64, 64)
    bones = kerangka({
        "body": [kotak(kv, at, BADAN[0], BADAN[1], BAJA_TENGAH, inflate=0.35),
                 kotak(kv, at, [-5, 18, -3], [10, 3, 6], BAJA_TERANG,
                       aksen=VOID_AKSEN)],
        "rightLeg": [kotak(kv, at, KAKI_R[0], KAKI_R[1], BAJA_TENGAH, inflate=0.50),
                     kotak(kv, at, [-5, 8, -3], [1, 5, 6], BAJA_TERANG,
                           aksen=VOID_UNGU)],
        "leftLeg": [kotak(kv, at, KAKI_L[0], KAKI_L[1], BAJA_TENGAH, inflate=0.50),
                    kotak(kv, at, [4, 8, -3], [1, 5, 6], BAJA_TERANG,
                          aksen=VOID_UNGU)]})
    bones.append(tulang("kneeRight", LEG_R_PIVOT, "rightLeg", [
        kotak(kv, at, [-4, 6, -4], [4, 3, 2], BAJA_TERANG, aksen=VOID_AKSEN)]))
    bones.append(tulang("kneeLeft", LEG_L_PIVOT, "leftLeg", [
        kotak(kv, at, [0, 6, -4], [4, 3, 2], BAJA_TERANG, aksen=VOID_AKSEN)]))
    return (geometry(f"geometry.{NS}.{SERI}_leggings", bones), baris_png(kv))


def geo_boots() -> Tuple[Dict[str, object], List[bytes]]:
    kv = kanvas(64, 64); at = Atlas(64, 64)
    boots = {}
    for nama, origin, xtoe in (("rightLeg", KAKI_R[0], -5), ("leftLeg", KAKI_L[0], 1)):
        boots[nama] = [
            kotak(kv, at, [origin[0], 0.0, origin[2]], [4, 8, 4],
                  BAJA_TENGAH, inflate=0.55),
            kotak(kv, at, [xtoe, 0, -5], [4, 2, 3], BAJA_TERANG, aksen=VOID_AKSEN),
            kotak(kv, at, [xtoe, 4, -3], [4, 3, 6], BAJA_TERANG, inflate=0.15),
            kotak(kv, at, [xtoe + 1, 0, 2], [2, 2, 1], VOID_UNGU)]
    return (geometry(f"geometry.{NS}.{SERI}_boots", kerangka(boots)), baris_png(kv))


# pivot/rotation/binding mengikuti tutorial resmi AddCustomItems (wrench) supaya
# pedang menempel di tangan dengan cara yang sudah terbukti dirender klien.
BLADE_PIVOT = [0.1, 19.0, -6.0]
BLADE_ROTATION = [125.0, 0.0, 0.0]
BLADE_BINDING = "q.item_slot_to_bone_name(context.item_slot)"


def geo_blade() -> Tuple[Dict[str, object], List[bytes]]:
    kv = kanvas(64, 64); at = Atlas(64, 64)
    cubes = [
        kotak(kv, at, [-2, 8, -9], [3, 2, 3], BAJA_GELAP, aksen=VOID_UNGU),   # pommel
        kotak(kv, at, [-1, 10, -8], [2, 5, 2], (58, 40, 62)),                 # gagang
        kotak(kv, at, [-4, 15, -9], [8, 2, 3], BAJA_TERANG, aksen=VOID_AKSEN),  # guard
        kotak(kv, at, [-5, 16, -9], [1, 3, 2], VOID_UNGU),
        kotak(kv, at, [4, 16, -9], [1, 3, 2], VOID_UNGU),
        kotak(kv, at, [-2, 17, -9], [4, 6, 2], BAJA_SOROT, aksen=VOID_AKSEN),  # bilah
        kotak(kv, at, [-2, 23, -9], [4, 5, 1], BAJA_SOROT),
        kotak(kv, at, [-1, 28, -9], [2, 4, 1], BAJA_TERANG),
        kotak(kv, at, [-1, 32, -9], [1, 3, 1], PUTIH_PANAS),                   # ujung
        kotak(kv, at, [-1, 18, -10], [1, 14, 1], VOID_AKSEN),      # garis energi
        kotak(kv, at, [-4, 21, -9], [1, 2, 1], VOID_UNGU),         # serpihan
        kotak(kv, at, [3, 26, -9], [1, 2, 1], VOID_AKSEN),
    ]
    bones = [tulang("bb_main", BLADE_PIVOT, None, cubes,
                    rotation=BLADE_ROTATION, binding=BLADE_BINDING)]
    return (geometry(f"geometry.{NS}.{SERI}_blade", bones), baris_png(kv))


GEOMETRIES = {
    "helmet": geo_helmet, "chestplate": geo_chestplate,
    "leggings": geo_leggings, "boots": geo_boots, "blade": geo_blade,
}

GEOMETRIES = {
    "helmet": geo_helmet, "chestplate": geo_chestplate,
    "leggings": geo_leggings, "boots": geo_boots, "blade": geo_blade,
}


# --------------------------------------------------------------------------- #
# Ikon item 16x16 (sprite inventory tetap 2D - batasan mesin Bedrock)
# --------------------------------------------------------------------------- #
def px(kv: List[bytearray], x: int, y: int, rgba: Tuple[int, int, int],
       a: int = 255) -> None:
    if 0 <= y < len(kv) and 0 <= x < len(kv[0]) // 4:
        o = x * 4
        kv[y][o] = rgba[0]; kv[y][o + 1] = rgba[1]
        kv[y][o + 2] = rgba[2]; kv[y][o + 3] = a


def kotak_px(kv: List[bytearray], x: int, y: int, w: int, h: int,
             rgba: Tuple[int, int, int]) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            px(kv, xx, yy, rgba)


def ikon_blade(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    # bilah diagonal: tepi terang + badan baja, dari kanan-atas ke kiri-bawah
    for i in range(9):
        x, y = 13 - i, 2 + i
        px(kv, x, y, VOID_AKSEN)
        px(kv, x - 1, y, BAJA_SOROT)
        px(kv, x - 1, y + 1, BAJA_TERANG)
        px(kv, x, y + 1, BAJA_TENGAH)
    px(kv, 14, 1, PUTIH_PANAS)
    px(kv, 13, 1, VOID_AKSEN)
    # pelindung tangan tegak lurus bilah
    for i in range(5):
        px(kv, 2 + i, 8 + i, BAJA_TERANG)
        px(kv, 3 + i, 8 + i, VOID_UNGU)
    px(kv, 1, 7, VOID_AKSEN); px(kv, 7, 13, VOID_AKSEN)
    # gagang + pommel
    for i in range(3):
        px(kv, 4 - i, 11 + i, (74, 50, 82))
        px(kv, 5 - i, 11 + i, (52, 34, 60))
    kotak_px(kv, 1, 13, 2, 2, BAJA_GELAP)
    px(kv, 1, 13, VOID_UNGU)
    return ukuran, ukuran, baris_png(kv)


def ikon_helmet(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    kotak_px(kv, 7, 1, 2, 2, VOID_UNGU); px(kv, 7, 1, VOID_AKSEN)     # jambul
    kotak_px(kv, 4, 3, 8, 1, BAJA_SOROT)        # puncak dome
    kotak_px(kv, 3, 4, 10, 1, BAJA_TERANG)
    kotak_px(kv, 2, 5, 12, 2, BAJA_TERANG)
    kotak_px(kv, 2, 7, 12, 5, BAJA_TENGAH)      # batok
    kotak_px(kv, 2, 7, 1, 5, BAJA_SOROT); kotak_px(kv, 13, 7, 1, 5, BAJA_GELAP)
    kotak_px(kv, 4, 7, 8, 2, BAJA_GELAP)        # visor
    kotak_px(kv, 5, 8, 6, 1, VOID_AKSEN)        # celah energi
    px(kv, 5, 8, PUTIH_PANAS)
    kotak_px(kv, 0, 7, 2, 3, BAJA_TERANG)       # tanduk kiri
    kotak_px(kv, 14, 7, 2, 3, BAJA_TERANG)
    px(kv, 0, 7, VOID_UNGU); px(kv, 15, 7, VOID_UNGU)
    kotak_px(kv, 4, 12, 8, 1, BAJA_GELAP)       # leher
    kotak_px(kv, 5, 13, 6, 1, BAJA_GELAP)
    return ukuran, ukuran, baris_png(kv)


def ikon_chestplate(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    kotak_px(kv, 6, 2, 4, 2, BAJA_TERANG)       # kerah
    kotak_px(kv, 4, 4, 8, 10, BAJA_TENGAH)      # badan
    kotak_px(kv, 4, 4, 1, 10, BAJA_SOROT); kotak_px(kv, 11, 4, 1, 10, BAJA_GELAP)
    kotak_px(kv, 2, 5, 2, 7, BAJA_TENGAH)       # lengan menempel badan
    kotak_px(kv, 12, 5, 2, 7, BAJA_TENGAH)
    kotak_px(kv, 2, 11, 2, 1, BAJA_GELAP); kotak_px(kv, 12, 11, 2, 1, BAJA_GELAP)
    kotak_px(kv, 1, 3, 4, 3, BAJA_TERANG)       # pauldron kiri menindih bahu
    kotak_px(kv, 11, 3, 4, 3, BAJA_TERANG)      # pauldron kanan
    kotak_px(kv, 1, 3, 4, 1, VOID_AKSEN); kotak_px(kv, 11, 3, 4, 1, VOID_AKSEN)
    kotak_px(kv, 1, 5, 1, 1, VOID_UNGU); kotak_px(kv, 14, 5, 1, 1, VOID_UNGU)
    kotak_px(kv, 7, 6, 2, 2, VOID_AKSEN)        # inti energi
    px(kv, 7, 6, PUTIH_PANAS)
    kotak_px(kv, 7, 9, 2, 4, VOID_UNGU)         # alur tengah
    kotak_px(kv, 4, 13, 8, 1, BAJA_GELAP)       # pinggang
    return ukuran, ukuran, baris_png(kv)


def ikon_leggings(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    kotak_px(kv, 4, 2, 8, 3, BAJA_TENGAH)        # sabuk
    kotak_px(kv, 4, 2, 8, 1, BAJA_TERANG)
    kotak_px(kv, 7, 3, 2, 2, VOID_AKSEN)         # gesper
    kotak_px(kv, 4, 5, 3, 9, BAJA_TENGAH)        # kaki kanan
    kotak_px(kv, 9, 5, 3, 9, BAJA_TENGAH)        # kaki kiri
    kotak_px(kv, 4, 5, 1, 9, BAJA_SOROT); kotak_px(kv, 11, 5, 1, 9, BAJA_GELAP)
    kotak_px(kv, 3, 9, 2, 3, BAJA_TERANG)        # pelindung lutut
    kotak_px(kv, 11, 9, 2, 3, BAJA_TERANG)
    px(kv, 3, 10, VOID_AKSEN); px(kv, 12, 10, VOID_AKSEN)
    kotak_px(kv, 4, 13, 3, 1, BAJA_GELAP); kotak_px(kv, 9, 13, 3, 1, BAJA_GELAP)
    return ukuran, ukuran, baris_png(kv)


def ikon_boots(ukuran: int = 16) -> Tuple[int, int, List[bytes]]:
    kv = kanvas(ukuran, ukuran)
    for x0 in (2, 9):
        kotak_px(kv, x0, 5, 4, 6, BAJA_TENGAH)      # betis
        kotak_px(kv, x0, 5, 1, 6, BAJA_SOROT); kotak_px(kv, x0 + 3, 5, 1, 6, BAJA_GELAP)
        kotak_px(kv, x0, 8, 4, 2, VOID_UNGU)        # pergelangan
        px(kv, x0 + 1, 8, VOID_AKSEN); px(kv, x0 + 2, 9, VOID_AKSEN)
        kotak_px(kv, x0, 11, 6 if x0 == 2 else 5, 3, BAJA_TERANG)   # kaki
        kotak_px(kv, x0, 13, 6 if x0 == 2 else 5, 1, BAJA_GELAP)    # sol
    return ukuran, ukuran, baris_png(kv)


IKON = {"helmet": ikon_helmet, "chestplate": ikon_chestplate,
        "leggings": ikon_leggings, "boots": ikon_boots, "blade": ikon_blade}

BAGIAN = ("helmet", "chestplate", "leggings", "boots", "blade")


def textures() -> Dict[str, Tuple[int, int, List[bytes]]]:
    """relpath dalam resource pack -> (w, h, baris RGBA)."""
    out: Dict[str, Tuple[int, int, List[bytes]]] = {}
    for bagian in BAGIAN:
        doc, rows = GEOMETRIES[bagian]()
        if bagian == "blade":
            out[f"textures/models/item/{NS}_{SERI}_{bagian}.png"] = (64, 64, rows)
        else:
            out[f"textures/models/armor/{NS}_{SERI}_{bagian}.png"] = (64, 64, rows)
        w, h, ikon = IKON[bagian]()
        out[f"textures/items/{NS}_{SERI}_{bagian}.png"] = (w, h, ikon)
    return out


def geometries() -> Dict[str, Dict[str, object]]:
    """relpath -> dokumen geometry."""
    out = {}
    for bagian in BAGIAN:
        doc, _ = GEOMETRIES[bagian]()
        out[f"models/entity/{NS}_{SERI}_{bagian}.geo.json"] = doc
    return out


# --------------------------------------------------------------------------- #
# Attachable (RP) - bentuk disalin dari vanilla & tutorial resmi
# --------------------------------------------------------------------------- #
def attachable_armor(bagian: str, varian_player: bool = False) -> Dict[str, object]:
    ident = item_id(bagian)
    desc: Dict[str, object] = {
        "identifier": ident + (".player" if varian_player else ""),
        "materials": {"default": "armor", "enchanted": "armor_enchanted"},
        "textures": {"default": f"textures/models/armor/{NS}_{SERI}_{bagian}",
                     "enchanted": "textures/misc/enchanted_actor_glint"},
        "geometry": {"default": f"geometry.{NS}.{SERI}_{bagian}"},
        "render_controllers": ["controller.render.armor"],
    }
    if varian_player:
        desc["item"] = {ident: "query.is_owner_identifier_any('minecraft:player')"}
    return {"format_version": ATTACH_ARMOR_FORMAT,
            "minecraft:attachable": {"description": desc}}


def attachable_blade() -> Dict[str, object]:
    ident = item_id("blade")
    return {"format_version": ATTACH_ITEM_FORMAT,
            "minecraft:attachable": {"description": {
                "identifier": ident,
                "item": {ident: "query.is_owner_identifier_any('minecraft:player')"},
                "materials": {"default": "entity_alphatest",
                              "enchanted": "entity_alphatest_glint"},
                "textures": {"default": f"textures/models/item/{NS}_{SERI}_blade",
                             "enchanted": "textures/misc/enchanted_item_glint"},
                "geometry": {"default": f"geometry.{NS}.{SERI}_blade"},
                "animations": {
                    "hold_first_person": "animation.steve_head.hold_first_person",
                    "hold_third_person": "animation.steve_head.hold_third_person"},
                "scripts": {"animate": [
                    {"hold_first_person": "context.is_first_person == 1.0"},
                    {"hold_third_person": "context.is_first_person == 0.0"}]},
                "render_controllers": ["controller.render.item_default"]}}}


def attachables() -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for bagian in PIECE:
        out[f"attachables/{NS}_{SERI}_{bagian}.json"] = attachable_armor(bagian)
        out[f"attachables/{NS}_{SERI}_{bagian}.player.json"] = \
            attachable_armor(bagian, varian_player=True)
    out[f"attachables/{NS}_{SERI}_blade.player.json"] = attachable_blade()
    return out


# --------------------------------------------------------------------------- #
# Item (BP) - komponen diverifikasi dari netherite_spear.json + skema resmi
# --------------------------------------------------------------------------- #
def _repair(bagian: str) -> Dict[str, object]:
    return {"repair_items": [
        {"items": [item_id(bagian)],
         "repair_amount": "context.other->query.remaining_durability"},
        {"items": ["minecraft:echo_shard"],
         "repair_amount": "query.max_durability * 0.25"}]}


def item_json(bagian: str) -> Dict[str, object]:
    comp: Dict[str, object] = {
        "minecraft:icon": {"texture": ikon_id(bagian)},
        "minecraft:display_name": {"value": NAMA_ID[bagian]},
        "minecraft:max_stack_size": 1,
        "minecraft:durability": {"max_durability": DURABILITAS[bagian],
                                 "damage_chance": {"min": 0, "max": 100}},
        "minecraft:enchantable": {"slot": SLOT_ENCHANT[bagian],
                                  "value": ENCHANT_VALUE},
        "minecraft:repairable": _repair(bagian),
        "minecraft:fire_resistant": {"value": True},
        "minecraft:glint": True,
    }
    if bagian == "blade":
        comp["minecraft:damage"] = {"value": DAMAGE_BLADE}
        comp["minecraft:hand_equipped"] = {"value": True}
        comp["minecraft:tags"] = {"tags": ["minecraft:is_sword"]}
    else:
        comp["minecraft:wearable"] = {"slot": SLOT_WEARABLE[bagian],
                                      "protection": PROTEKSI[bagian]}
        comp["minecraft:tags"] = {"tags": ["minecraft:is_armor"]}
    return {"format_version": ITEM_FORMAT,
            "minecraft:item": {
                "description": {"identifier": item_id(bagian),
                                "menu_category": {"category": "equipment"}},
                "components": comp}}


def items() -> Dict[str, Dict[str, object]]:
    return {f"items/{NS}_{SERI}_{b}.json": item_json(b) for b in BAGIAN}


# --------------------------------------------------------------------------- #
# Resep crafting (bisa didapat di survival tanpa Cheats)
# --------------------------------------------------------------------------- #
POLA = {
    "helmet": (["XXX", "X#X"], {"X": "minecraft:netherite_ingot",
                                "#": "minecraft:echo_shard"}),
    "chestplate": (["X#X", "XXX", "XXX"], {"X": "minecraft:netherite_ingot",
                                           "#": "minecraft:echo_shard"}),
    "leggings": (["XXX", "X#X", "X X"], {"X": "minecraft:netherite_ingot",
                                         "#": "minecraft:echo_shard"}),
    "boots": (["X X", "X#X"], {"X": "minecraft:netherite_ingot",
                               "#": "minecraft:echo_shard"}),
    "blade": (["E", "N", "R"], {"E": "minecraft:echo_shard",
                                "N": "minecraft:netherite_ingot",
                                "R": "minecraft:blaze_rod"}),
}


def recipe_json(bagian: str) -> Dict[str, object]:
    pola, kunci = POLA[bagian]
    return {"format_version": RECIPE_FORMAT,
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{NS}:{SERI}_{bagian}_craft"},
                "tags": ["crafting_table"],
                "pattern": pola,
                "key": {k: {"item": v} for k, v in kunci.items()},
                "unlock": [{"item": "minecraft:echo_shard"}],
                "result": {"item": item_id(bagian), "count": 1}}}


def recipes() -> Dict[str, Dict[str, object]]:
    return {f"recipes/{NS}_{SERI}_{b}.json": recipe_json(b) for b in BAGIAN}


def item_texture() -> Dict[str, object]:
    return {"resource_pack_name": f"{NS}_{SERI}_arsenal",
            "texture_name": "atlas.items",
            "texture_data": {ikon_id(b): {"textures": f"textures/items/{ikon_id(b)}"}
                             for b in BAGIAN}}


def statistik() -> Dict[str, object]:
    """Ringkasan untuk README/CLI: perbandingan melawan netherite."""
    return {"proteksi_total": sum(PROTEKSI[p] for p in PIECE),
            "proteksi_netherite": 20,
            "durability_rata": round(sum(DURABILITAS[p] for p in PIECE) / 4),
            "durability_netherite_rata": round((407 + 592 + 555 + 481) / 4),
            "damage_pedang": DAMAGE_BLADE, "damage_netherite": 8,
            "enchantability": ENCHANT_VALUE, "enchantability_netherite": 15,
            "jumlah_kubus": sum(
                sum(len(b.get("cubes", []))
                    for b in GEOMETRIES[x]()[0]["minecraft:geometry"][0]["bones"])
                for x in BAGIAN)}
