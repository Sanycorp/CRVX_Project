"""Foliage - penggambar tekstur 16x16 asli (bukan aset Mojang) untuk CRVX.

Prinsip performa yang dipakai: **alpha biner**. Permukaan tanaman/daun di vanilla
sering memakai alpha setengah-transparan, yang pada GPU tile-based (Mali-G57)
memaksa blending read-modify-write per fragmen. Dengan alpha murni 0 atau 255,
fragmen yang transparan bisa dibuang lewat alpha-test lebih awal - beban
fill-rate turun drastis sementara bentuk siluet tanaman tetap terbaca, jadi
tampilan tetap bagus.

Kaca & es tetap memakai alpha nyata (memang harus tembus pandang), tapi dengan
frekuensi detail rendah supaya jumlah texel unik kecil (atlas lebih ramah cache).

Semua nama berkas di sini diverifikasi ada di Mojang/bedrock-samples (Okt 2026).
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

Rows = List[bytes]
SIZE = 16


def _baru() -> List[List[Tuple[int, int, int, int]]]:
    return [[(0, 0, 0, 0) for _ in range(SIZE)] for _ in range(SIZE)]


def _jadi(sel: Sequence[Sequence[Tuple[int, int, int, int]]]) -> Rows:
    return [bytes(b for px in row for b in px) for row in sel]


def _clamp(v: float) -> int:
    return max(0, min(255, int(v)))


def _warna(base: Tuple[int, int, int], v: float) -> Tuple[int, int, int, int]:
    return (_clamp(base[0] * v), _clamp(base[1] * v), _clamp(base[2] * v), 255)


# --------------------------------------------------------------------------- #
# Daun (alpha biner, pola bergerombol seperti vanilla)
# --------------------------------------------------------------------------- #
def daun(tone: Tuple[int, int, int] = (58, 132, 44), seed: int = 1,
         lubang: float = 0.0) -> Tuple[int, int, Rows]:
    """Varian ``*_opaque`` WAJIB opak penuh (alpha 255 di semua piksel).

    Vanilla sengaja membuat leaves_*_opaque tanpa lubang supaya blok daun
    dirender sebagai kubus padat: permukaan di belakangnya tidak perlu
    digambar. Melubanginya (seperti versi sebelumnya) mengubah setiap blok
    daun menjadi cutout tembus-pandang -> jumlah permukaan daun yang harus
    digambar meledak -> hutan jadi JAUH lebih berat. Parameter ``lubang``
    dibiarkan ada (default 0) hanya untuk kompatibilitas pemanggil lama.
    """
    rnd = random.Random(seed * 6151)
    sel = _baru()
    for y in range(SIZE):
        for x in range(SIZE):
            n = rnd.random()
            if n < lubang and 2 <= x <= 13 and 2 <= y <= 13:
                sel[y][x] = _warna(tone, 0.55)   # bayangan dalam, tetap opak
                continue
            gumpal = 0.62 + 0.55 * (0.5 + 0.5 * math.sin(x * 1.7 + seed) *
                                    math.cos(y * 1.9 - seed))
            sel[y][x] = _warna(tone, gumpal * (0.82 + 0.36 * rnd.random()))
    # urat daun lebih gelap supaya tetap terbaca sebagai dedaunan
    for y in range(SIZE):
        for x in range(SIZE):
            if sel[y][x][3] and (x + y * 2) % 7 == 0:
                r, g, b, a = sel[y][x]
                sel[y][x] = (_clamp(r * 0.68), _clamp(g * 0.72), _clamp(b * 0.66), a)
    return SIZE, SIZE, _jadi(sel)


# --------------------------------------------------------------------------- #
# Kaca & es (alpha nyata, detail rendah)
# --------------------------------------------------------------------------- #
def kaca(tepi: int = 200) -> Tuple[int, int, Rows]:
    sel = _baru()
    for y in range(SIZE):
        for x in range(SIZE):
            border = x in (0, 15) or y in (0, 15)
            if border:
                sel[y][x] = (206, 232, 244, tepi)
            elif (x, y) in ((3, 3), (4, 4), (5, 5), (10, 9), (11, 10)):
                sel[y][x] = (235, 248, 255, 92)     # kilau diagonal
            else:
                sel[y][x] = (210, 235, 246, 10)
    return SIZE, SIZE, _jadi(sel)


def kaca_pane_top() -> Tuple[int, int, Rows]:
    sel = _baru()
    for y in range(SIZE):
        for x in range(SIZE):
            if 6 <= y <= 9:
                edge = y in (6, 9) or x in (0, 15)
                sel[y][x] = (206, 232, 244, 210 if edge else 26)
    return SIZE, SIZE, _jadi(sel)


def es(alpha: int = 200, retak: int = 3, seed: int = 7) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for y in range(SIZE):
        for x in range(SIZE):
            v = 0.90 + 0.16 * rnd.random()
            sel[y][x] = (_clamp(168 * v), _clamp(208 * v), _clamp(238 * v), alpha)
    for i in range(retak):
        x, y = rnd.randrange(SIZE), rnd.randrange(SIZE)
        for step in range(6):
            sel[y][x] = (120, 160, 196, alpha)
            x = (x + rnd.choice((-1, 0, 1))) % SIZE
            y = (y + rnd.choice((-1, 1))) % SIZE
    return SIZE, SIZE, _jadi(sel)


def es_packed(seed: int = 3) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for y in range(SIZE):
        for x in range(SIZE):
            v = 0.86 + 0.20 * rnd.random()
            sel[y][x] = (_clamp(196 * v), _clamp(224 * v), _clamp(244 * v), 255)
    for i in range(4):
        x, y = rnd.randrange(SIZE), rnd.randrange(SIZE)
        for _ in range(5):
            sel[y][x] = (160, 196, 224, 255)
            x = (x + 1) % SIZE
            y = (y + rnd.choice((-1, 1))) % SIZE
    return SIZE, SIZE, _jadi(sel)


# --------------------------------------------------------------------------- #
# Tanaman silang (alpha biner)
# --------------------------------------------------------------------------- #
def rumput(hue: Tuple[int, int, int] = (96, 158, 66), seed: int = 5,
           batang: int = 6) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for i in range(batang):
        x = rnd.randrange(2, 14)
        tinggi = rnd.randrange(7, 14)
        lekuk = rnd.choice((-1, 1))
        for j in range(tinggi):
            y = SIZE - 1 - j
            xx = x + (lekuk if j > tinggi // 2 else 0)
            if 0 <= xx < SIZE:
                v = 0.70 + 0.50 * (j / tinggi)
                sel[y][xx] = _warna(hue, v)
            if j == tinggi - 1 and 0 <= xx + 1 < SIZE:
                sel[y][xx + 1] = _warna(hue, 0.62)   # ujung daun
    return SIZE, SIZE, _jadi(sel)


def semak_kering() -> Tuple[int, int, Rows]:
    sel = _baru()
    rnd = random.Random(81)
    cabang = [(8, 15, -1), (8, 15, 1), (5, 12, -1), (11, 12, 1)]
    for x0, y0, arah in cabang:
        x, y = x0, y0
        for j in range(10):
            sel[y][x] = _warna((138, 106, 62), 0.72 + 0.4 * (j / 10))
            y -= 1
            if j % 3 == 2:
                x = max(0, min(15, x + arah))
            if y < 0:
                break
        for j in range(3):
            if 0 <= x + arah * j < 15:
                sel[max(0, y)][x + arah * j] = _warna((138, 106, 62), 0.6)
    _ = rnd
    return SIZE, SIZE, _jadi(sel)


def sulur(tone: Tuple[int, int, int] = (52, 116, 46), seed: int = 9) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for kolom in (2, 6, 10, 14):
        for y in range(SIZE):
            xx = kolom + (1 if (y // 3) % 2 else 0)
            if xx < SIZE and rnd.random() > 0.18:
                sel[y][xx] = _warna(tone, 0.72 + 0.4 * rnd.random())
            if y % 4 == 1 and xx + 1 < SIZE and rnd.random() > 0.4:
                sel[y][xx + 1] = _warna(tone, 0.6)
    return SIZE, SIZE, _jadi(sel)


def teratai() -> Tuple[int, int, Rows]:
    sel = _baru()
    cx, cy = 8.0, 8.0
    for y in range(SIZE):
        for x in range(SIZE):
            dx, dy = x - cx + 0.5, y - cy + 0.5
            r = math.sqrt(dx * dx + dy * dy)
            ang = math.atan2(dy, dx)
            # takik khas daun teratai
            if r < 7.2 and not (-0.35 < ang < 0.35 and r > 2.0):
                v = 0.72 + 0.30 * (1 - r / 7.2)
                if int(ang * 3) % 2 == 0:
                    v *= 0.88
                sel[y][x] = _warna((74, 158, 78), v)
    return SIZE, SIZE, _jadi(sel)


def anakan(hue: Tuple[int, int, int] = (74, 148, 56), seed: int = 4) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for y in range(10, 16):
        sel[y][8] = _warna((96, 128, 60), 0.8)          # batang
    for y in range(3, 11):
        for x in range(4, 13):
            dx, dy = x - 8, y - 7
            if dx * dx + dy * dy * 1.6 < 13 and rnd.random() > 0.12:
                sel[y][x] = _warna(hue, 0.72 + 0.44 * rnd.random())
    return SIZE, SIZE, _jadi(sel)


def jamur(cap: Tuple[int, int, int] = (186, 62, 52),
          bintik: bool = True, seed: int = 6) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for y in range(9, 16):
        for x in (7, 8):
            sel[y][x] = _warna((226, 220, 200), 0.85 + 0.2 * rnd.random())
    for y in range(3, 10):
        lebar = 2 + int((y - 2) * 1.6)
        for x in range(8 - lebar, 8 + lebar + 1):
            if 0 <= x < SIZE:
                v = 0.78 + 0.30 * (y / 10)
                sel[y][x] = _warna(cap, v)
    if bintik:
        for sx, sy in ((6, 5), (9, 4), (11, 7), (5, 8)):
            sel[sy][sx] = (240, 236, 226, 255)
    return SIZE, SIZE, _jadi(sel)


def bunga(kelopak: Tuple[int, int, int], pusat: Tuple[int, int, int],
          seed: int = 2) -> Tuple[int, int, Rows]:
    rnd = random.Random(seed)
    sel = _baru()
    for y in range(8, 16):
        sel[y][8] = _warna((86, 142, 62), 0.85)
    sel[11][6] = _warna((86, 142, 62), 0.7)
    sel[12][10] = _warna((86, 142, 62), 0.7)
    cx, cy = 8.0, 5.0
    for y in range(0, 10):
        for x in range(3, 13):
            dx, dy = x - cx, y - cy
            r = math.sqrt(dx * dx + dy * dy)
            if r < 3.4:
                sel[y][x] = _warna(pusat, 0.9 + 0.2 * rnd.random())
            elif r < 4.6 and (int(math.degrees(math.atan2(dy, dx)) // 60) % 2 == 0):
                sel[y][x] = _warna(kelopak, 0.8 + 0.3 * rnd.random())
    return SIZE, SIZE, _jadi(sel)


def tangga() -> Tuple[int, int, Rows]:
    sel = _baru()
    kayu = (146, 108, 62)
    for y in range(SIZE):
        for x in (2, 3, 12, 13):
            sel[y][x] = _warna(kayu, 0.82 + 0.18 * ((x + y) % 2))
    for y in (2, 3, 7, 8, 12, 13):
        for x in range(2, 14):
            sel[y][x] = _warna(kayu, 0.94 if y % 5 == 2 else 0.80)
    return SIZE, SIZE, _jadi(sel)


# --------------------------------------------------------------------------- #
# Katalog lengkap dengan path vanilla terverifikasi
# --------------------------------------------------------------------------- #
LEAF_TONES = {
    "oak": (58, 132, 44), "spruce": (44, 96, 46), "birch": (96, 148, 60),
    "jungle": (48, 152, 44), "acacia": (98, 138, 40), "big_oak": (52, 118, 42),
}


def entries() -> Dict[str, Tuple[int, int, Rows]]:
    out: Dict[str, Tuple[int, int, Rows]] = {}
    for i, (nama, tone) in enumerate(sorted(LEAF_TONES.items())):
        out[f"textures/blocks/leaves_{nama}_opaque.png"] = daun(tone, seed=i + 1)
    out["textures/blocks/glass.png"] = kaca()
    out["textures/blocks/glass_pane_top.png"] = kaca_pane_top()
    out["textures/blocks/ice.png"] = es(alpha=200, retak=3, seed=7)
    out["textures/blocks/ice_packed.png"] = es_packed()
    for tahap in range(4):
        out[f"textures/blocks/frosted_ice_{tahap}.png"] = es(
            alpha=214 - tahap * 22, retak=2 + tahap, seed=20 + tahap)
    out["textures/blocks/ladder.png"] = tangga()
    out["textures/blocks/vine.png"] = sulur()
    out["textures/blocks/tallgrass.png"] = rumput(seed=5)
    out["textures/blocks/deadbush.png"] = semak_kering()
    out["textures/blocks/waterlily.png"] = teratai()
    out["textures/blocks/sapling_oak.png"] = anakan()
    out["textures/blocks/mushroom_brown.png"] = jamur(cap=(168, 132, 92), bintik=False, seed=11)
    out["textures/blocks/mushroom_red.png"] = jamur(cap=(186, 62, 52), bintik=True, seed=6)
    out["textures/blocks/flower_dandelion.png"] = bunga((246, 206, 66), (250, 232, 120), seed=2)
    out["textures/blocks/flower_rose.png"] = bunga((196, 52, 52), (120, 26, 26), seed=3)
    out["textures/blocks/flower_blue_orchid.png"] = bunga((86, 122, 226), (210, 226, 250), seed=4)
    out["textures/blocks/flower_tulip_red.png"] = bunga((212, 62, 62), (240, 210, 90), seed=5)
    out["textures/blocks/flower_oxeye_daisy.png"] = bunga((238, 238, 232), (238, 210, 84), seed=6)
    return out


def alpha_stats(rows: Rows) -> Dict[str, int]:
    """Hitung distribusi alpha: 0, 255 (biner) vs tengah (blend mahal)."""
    nol = penuh = tengah = 0
    for row in rows:
        for x in range(0, len(row), 4):
            a = row[x + 3]
            if a == 0:
                nol += 1
            elif a == 255:
                penuh += 1
            else:
                tengah += 1
    return {"transparan": nol, "opak": penuh, "blend": tengah}
