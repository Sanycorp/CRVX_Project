"""TexForge - codec PNG murni stdlib + pembangun texture pack performa.

Dua jalur, keduanya nyata:

1. ``build_texture_pack()`` - pack berisi tekstur **buatan sendiri** (bukan aset
   Mojang, jadi sah dibagikan): awan transparan, cuaca nyaris tak terlihat, kaca/
   es/daun versi 8x8. Resolusi blok dipotong 16x16 -> 8x8 = texel yang diambil
   GPU tinggal seperempat, dan atlas muat lebih banyak di cache. Di Mali-G57 MC2
   yang bandwidth-nya sempit, ini penghematan nyata.

2. ``build_downscaled_pack()`` - menurunkan resolusi **aset vanilla milik user
   sendiri** (hasil ekstrak APK / folder resource_pack) menjadi pack 8x8 atau 4x8
   yang tetap terlihat seperti Minecraft asli. Tidak ada berkas Mojang yang
   disalin ke repo: semuanya diproses di mesin user.

Dimensi & nama berkas diverifikasi terhadap Mojang/bedrock-samples (Okt 2026):
clouds.png 256x256, weather.png 32x32, sun.png 32x32, moon_phases.png 128x64,
glass.png / ice.png / leaves_*_opaque.png 16x16, water_still.png 16x512 (strip
flipbook - sengaja dilewati supaya animasi tidak rusak).
"""

from __future__ import annotations

import json
import os
import random
import shutil
import struct
import zipfile
import zlib
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .packforge import fog_file, make_icon, write_png

PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


# --------------------------------------------------------------------------- #
# Decoder PNG (8-bit, non-interlaced, color type 0/2/3/4/6)
# --------------------------------------------------------------------------- #
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(data: bytes) -> Tuple[int, int, List[bytes]]:
    """Kembalikan (width, height, baris RGBA 8-bit) dari sebuah PNG."""
    if data[:8] != PNG_SIG:
        raise ValueError("bukan PNG")
    pos = 8
    idat = bytearray()
    width = height = 0
    bitdepth = colortype = interlace = 0
    palette: List[bytes] = []
    trns = b""
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            (width, height, bitdepth, colortype,
             _comp, _filt, interlace) = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"PLTE":
            palette = [chunk[i:i + 3] for i in range(0, len(chunk), 3)]
        elif tag == b"tRNS":
            trns = chunk
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    if interlace:
        raise ValueError("PNG interlaced tidak didukung")
    if bitdepth != 8:
        raise ValueError(f"bit depth {bitdepth} tidak didukung (perlu 8)")
    if colortype not in _CHANNELS:
        raise ValueError(f"color type {colortype} tidak dikenal")
    if colortype == 3 and not palette:
        raise ValueError("PNG palet tanpa PLTE")

    raw = zlib.decompress(bytes(idat))
    ch = _CHANNELS[colortype]
    stride = width * ch
    need = height * (stride + 1)
    if len(raw) < need:
        raise ValueError(f"data piksel kurang: {len(raw)} < {need}")

    buf = bytearray()
    prev = bytearray(stride)
    idx = 0
    for _ in range(height):
        filt = raw[idx]
        idx += 1
        line = bytearray(raw[idx:idx + stride])
        idx += stride
        if filt == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 0xFF
        elif filt == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif filt == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 0xFF
        elif filt == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
        elif filt != 0:
            raise ValueError(f"filter type {filt} tidak dikenal")
        buf += line
        prev = line

    rows: List[bytes] = []
    for y in range(height):
        src = buf[y * stride:(y + 1) * stride]
        row = bytearray()
        for x in range(width):
            o = x * ch
            if colortype == 6:
                row += src[o:o + 4]
            elif colortype == 2:
                row += src[o:o + 3] + b"\xff"
            elif colortype == 0:
                g = src[o]
                row += bytes((g, g, g, 255))
            elif colortype == 4:
                g, a = src[o], src[o + 1]
                row += bytes((g, g, g, a))
            else:
                pi = src[o]
                rgb = palette[pi] if pi < len(palette) else b"\x00\x00\x00"
                alpha = trns[pi] if pi < len(trns) else 255
                row += rgb + bytes((alpha,))
        rows.append(bytes(row))
    return width, height, rows


def downscale(width: int, height: int, rows: Sequence[bytes],
              tw: int, th: int) -> List[bytes]:
    """Box-filter: rata-rata kotak sumber -> 1 piksel target."""
    tw = max(1, int(tw))
    th = max(1, int(th))
    out: List[bytes] = []
    for ty in range(th):
        y0 = ty * height // th
        y1 = max(y0 + 1, (ty + 1) * height // th)
        row = bytearray()
        for tx in range(tw):
            x0 = tx * width // tw
            x1 = max(x0 + 1, (tx + 1) * width // tw)
            r = g = b = a = 0
            n = 0
            for y in range(y0, y1):
                src = rows[y]
                for x in range(x0, x1):
                    o = x * 4
                    r += src[o]
                    g += src[o + 1]
                    b += src[o + 2]
                    a += src[o + 3]
                    n += 1
            row += bytes((r // n, g // n, b // n, a // n))
        out.append(bytes(row))
    return out


def downscale_png(data: bytes, target: int) -> Optional[bytes]:
    """Turunkan resolusi PNG ke ``target`` px sisi terpendek. None bila dilewati."""
    width, height, rows = read_png(data)
    if height > width:
        return None                       # strip flipbook/animasi -> jangan disentuh
    if min(width, height) <= target:
        return None                       # sudah kecil
    if width >= height:
        tw, th = target, max(1, height * target // width)
    else:
        tw, th = max(1, width * target // height), target
    scaled = downscale(width, height, rows, tw, th)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp.png")
    write_png(out, tw, th, scaled)
    with open(out, "rb") as fh:
        blob = fh.read()
    os.remove(out)
    return blob


def _png_bytes(width: int, height: int, rows: Sequence[bytes]) -> bytes:
    raw = b"".join(b"\x00" + row for row in rows)
    return (PNG_SIG
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


# --------------------------------------------------------------------------- #
# Tekstur prosedural (100% piksel buatan sendiri, bukan aset Mojang)
# --------------------------------------------------------------------------- #
def _clamp(v: float) -> int:
    return max(0, min(255, int(v)))


def tex_transparent(size: int, width: Optional[int] = None,
                    height: Optional[int] = None) -> Tuple[int, int, List[bytes]]:
    w = width or size
    h = height or size
    return w, h, [bytes(w * 4) for _ in range(h)]


def tex_weather_faint(size: int = 32, alpha: int = 26) -> Tuple[int, int, List[bytes]]:
    """Cuaca (rain/snow sheet) nyaris transparan: overdraw hujan hilang."""
    rnd = random.Random(9137)
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            streak = 1.0 if (x * 3 + y) % 5 == 0 else 0.25
            jit = 0.6 + 0.8 * rnd.random()
            row += bytes((216, 230, 246, _clamp(alpha * streak * jit)))
        rows.append(bytes(row))
    return size, size, [bytes(r) for r in rows]


def tex_glass(size: int = 8, edge: int = 96) -> Tuple[int, int, List[bytes]]:
    """Kaca 8x8: isi hampir bening, tepi tipis - blend lebih murah."""
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            border = x == 0 or y == 0 or x == size - 1 or y == size - 1
            if border:
                row += bytes((214, 236, 245, edge))
            else:
                row += bytes((200, 228, 240, 14))
        rows.append(bytes(row))
    return size, size, [bytes(r) for r in rows]


def tex_glass_pane_top(size: int = 8) -> Tuple[int, int, List[bytes]]:
    rows = []
    for y in range(size):
        row = bytearray()
        mid = size // 2
        for x in range(size):
            on_line = x in (mid - 1, mid) or y in (mid - 1, mid)
            row += bytes((214, 236, 245, 120 if on_line else 10))
        rows.append(bytes(row))
    return size, size, [bytes(r) for r in rows]


def tex_ice(size: int = 8, packed: bool = False) -> Tuple[int, int, List[bytes]]:
    rnd = random.Random(4421 if packed else 7712)
    base = (176, 206, 232) if packed else (150, 196, 230)
    alpha = 255 if packed else 168
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            v = 0.88 + 0.24 * rnd.random()
            row += bytes((_clamp(base[0] * v), _clamp(base[1] * v),
                          _clamp(base[2] * v), alpha))
        rows.append(bytes(row))
    return size, size, [bytes(r) for r in rows]


LEAF_TONES = {
    "oak": (58, 132, 44),
    "spruce": (44, 96, 46),
    "birch": (96, 148, 60),
    "jungle": (48, 152, 44),
    "acacia": (98, 138, 40),
    "big_oak": (52, 118, 42),
}


def tex_leaves(size: int = 8, tone: Tuple[int, int, int] = (58, 132, 44),
               holes: float = 0.16, seed: int = 1) -> Tuple[int, int, List[bytes]]:
    """Daun alpha-tested: lubang penuh (discard murah) + variasi nada."""
    rnd = random.Random(seed * 7919)
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            n = rnd.random()
            if n < holes:
                row += bytes((0, 0, 0, 0))
                continue
            v = 0.66 + 0.62 * n
            row += bytes((_clamp(tone[0] * v), _clamp(tone[1] * v),
                          _clamp(tone[2] * v), 255))
        rows.append(bytes(row))
    return size, size, [bytes(r) for r in rows]


# --------------------------------------------------------------------------- #
# Pack tekstur jadi (self-authored)
# --------------------------------------------------------------------------- #
def texture_entries(res: int = 8, cloud_size: int = 256,
                    weather_alpha: int = 26) -> Dict[str, Tuple[int, int, List[bytes]]]:
    """Peta path dalam pack -> (w, h, baris RGBA). Path = path vanilla Bedrock."""
    entries: Dict[str, Tuple[int, int, List[bytes]]] = {
        "textures/environment/clouds.png": tex_transparent(cloud_size),
        "textures/environment/weather.png": tex_weather_faint(32, weather_alpha),
        "textures/blocks/glass.png": tex_glass(res),
        "textures/blocks/glass_pane_top.png": tex_glass_pane_top(res),
        "textures/blocks/ice.png": tex_ice(res, packed=False),
        "textures/blocks/ice_packed.png": tex_ice(res, packed=True),
    }
    for index, (name, tone) in enumerate(sorted(LEAF_TONES.items())):
        entries[f"textures/blocks/leaves_{name}_opaque.png"] = tex_leaves(
            res, tone, seed=index + 1)
    return entries


def build_texture_pack(out_path: str, res: int = 8, fog_strength: float = 0.85,
                       name: str = "CRVX Fast Texture 8x",
                       version: Sequence[int] = (1, 0, 0)) -> str:
    """Tulis .mcpack berisi tekstur self-authored + fog cut."""
    from .addonforge import manifest

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = out_path + ".src"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    write_png(os.path.join(staging, "pack_icon.png"), 128, 128,
              make_icon(accent=(52, 211, 153)))
    _put(staging, "manifest.json", json.dumps(
        manifest(name,
                 f"Tekstur {res}x{res} buatan sendiri untuk blok transparan paling "
                 "berat (kaca, es, daun) + awan transparan + cuaca nyaris tak "
                 "terlihat + 16 definisi fog dipangkas. Bukan aset Mojang.",
                 version, "resources"), indent=2, ensure_ascii=False))
    _put(staging, "fogs/crvx_fog_cut.json",
         json.dumps(fog_file(fog_strength), indent=2, ensure_ascii=False))
    for rel, (w, h, rows) in texture_entries(res).items():
        os.makedirs(os.path.dirname(os.path.join(staging, rel)), exist_ok=True)
        write_png(os.path.join(staging, rel), w, h, rows)

    _zip_dir(staging, out_path)
    shutil.rmtree(staging, ignore_errors=True)
    return out_path


def _put(root: str, rel: str, text: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _zip_dir(src: str, out_path: str, prefix: str = "") -> None:
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src):
            for fname in sorted(files):
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                zf.write(full, f"{prefix}{rel}" if prefix else rel)


# --------------------------------------------------------------------------- #
# Downscale aset vanilla milik user sendiri
# --------------------------------------------------------------------------- #
ATLAS_FILES = ("terrain_texture.json", "item_texture.json", "blocks.json",
               "flipbook_textures.json", "biomes_client.json")


def _iter_sources(vanilla: str) -> Iterable[Tuple[str, bytes]]:
    """Hasilkan (path relatif RP, bytes) dari folder atau arsip zip/apk/mcpack."""
    if os.path.isdir(vanilla):
        for root, _dirs, files in os.walk(vanilla):
            for fname in sorted(files):
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, vanilla).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    yield rel, fh.read()
        return
    if os.path.isfile(vanilla):
        with zipfile.ZipFile(vanilla) as zf:
            # APK: aset ada di assets/resource_packs/vanilla/...
            roots = _detect_roots(zf.namelist())
            for rel in sorted(zf.namelist()):
                trimmed = _strip_root(rel, roots)
                if trimmed is None:
                    continue
                yield trimmed, zf.read(rel)
        return
    raise FileNotFoundError(f"tidak ditemukan: {vanilla}")


def _detect_roots(names: Sequence[str]) -> List[str]:
    roots: List[str] = []
    for candidate in ("assets/resource_packs/vanilla/", "resource_pack/"):
        if any(n.startswith(candidate) for n in names):
            roots.append(candidate)
    return roots


def _strip_root(rel: str, roots: Sequence[str]) -> Optional[str]:
    for root in roots:
        if rel.startswith(root):
            return rel[len(root):]
    return rel if not roots else None


def build_downscaled_pack(vanilla: str, out_path: str, target: int = 8,
                          name: Optional[str] = None,
                          version: Sequence[int] = (1, 0, 0)) -> Dict[str, object]:
    """Bangun pack resolusi-rendah dari aset vanilla milik user sendiri.

    ``vanilla`` boleh folder RP, .zip, .mcpack, atau .apk. Berkas Mojang tidak
    pernah masuk ke repo ini: pemrosesan terjadi di mesin pemakai.
    """
    from .addonforge import manifest

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = out_path + ".src"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    stats: Dict[str, object] = {
        "out": out_path, "target": target, "converted": 0, "skipped_animated": 0,
        "skipped_small": 0, "skipped_error": 0, "bytes_before": 0, "bytes_after": 0,
        "atlas": [], "errors": [],
    }
    kept = 0
    for rel, blob in _iter_sources(vanilla):
        low = rel.lower()
        base = os.path.basename(rel)
        if low.endswith(".json") and base in ATLAS_FILES and rel.count("/") <= 1:
            _put(staging, rel, blob.decode("utf-8", "replace"))
            stats["atlas"].append(rel)
            continue
        if not low.endswith(".png"):
            continue                        # .tga / .texture_set.json sengaja dibuang
        if not (low.startswith("textures/blocks/")
                or low.startswith("textures/environment/")
                or low.startswith("textures/items/")
                or low.startswith("textures/entity/")
                or low.startswith("textures/misc/")):
            continue
        stats["bytes_before"] += len(blob)
        try:
            scaled = downscale_png(blob, target)
        except Exception as exc:            # noqa: BLE001 - satu berkas rusak tak boleh mematikan pack
            stats["skipped_error"] += 1
            stats["errors"].append(f"{rel}: {type(exc).__name__}: {exc}")
            scaled = None
            _put_binary(staging, rel, blob)
            kept += 1
            continue
        if scaled is None:
            try:
                w, h, _ = read_png(blob)
                if h > w:
                    stats["skipped_animated"] += 1
                else:
                    stats["skipped_small"] += 1
            except Exception:               # noqa: BLE001
                stats["skipped_small"] += 1
            _put_binary(staging, rel, blob)
            kept += 1
            continue
        _put_binary(staging, rel, scaled)
        stats["bytes_after"] += len(scaled)
        stats["converted"] += 1
        kept += 1

    write_png(os.path.join(staging, "pack_icon.png"), 128, 128,
              make_icon(accent=(56, 189, 248)))
    label = name or f"CRVX {target}x Performance (vanilla-derived)"
    _put(staging, "manifest.json", json.dumps(
        manifest(label,
                 f"Tekstur vanilla yang diturunkan ke {target}px oleh CRVX TexForge. "
                 "Diproses dari aset milik pemakai sendiri; tidak ada berkas Mojang "
                 "yang didistribusikan ulang.",
                 version, "resources"), indent=2, ensure_ascii=False))
    stats["kept"] = kept
    _zip_dir(staging, out_path)
    shutil.rmtree(staging, ignore_errors=True)
    stats["size_bytes"] = os.path.getsize(out_path)
    return stats


def _put_binary(root: str, rel: str, blob: bytes) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(blob)
