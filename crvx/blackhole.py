"""BlackHole - seni prosedural bertema lubang hitam untuk CRVX FPS Booster.

Semua piksel digambar dari nol dengan matematika (gradien akresi, cincin foton,
lensa gravitasi, medan bintang) - tidak memakai aset Mojang, tidak memakai
library gambar. Output PNG lewat encoder murni di packforge.

Dipakai untuk: pack_icon (128px), ikon tombol ActionForm (32px), dan banner UI.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

# nada piringan akresi per aksi (panas -> dingin)
RAMP: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = {
    "turbo":   ((255, 248, 225), (120, 220, 255), (24, 60, 130)),
    "hemat":   ((240, 255, 235), (120, 255, 180), (18, 90, 66)),
    "ganas":   ((255, 240, 235), (255, 120, 150), (110, 16, 60)),
    "hud":     ((255, 250, 225), (255, 196, 90), (110, 60, 10)),
    "status":  ((245, 235, 255), (186, 140, 255), (60, 24, 110)),
    "restore": ((235, 245, 255), (150, 190, 235), (30, 50, 90)),
    "inti":    ((255, 250, 235), (255, 170, 70), (120, 30, 20)),
}
DEFAULT_RAMP = RAMP["inti"]


def _ramp(t: float, ramp: Sequence[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """t=0 panas/putih, t=1 dingin/gelap."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        a, b, k = ramp[0], ramp[1], t * 2.0
    else:
        a, b, k = ramp[1], ramp[2], (t - 0.5) * 2.0
    return (int(a[0] + (b[0] - a[0]) * k),
            int(a[1] + (b[1] - a[1]) * k),
            int(a[2] + (b[2] - a[2]) * k))


def _noise(x: float, y: float, seed: int) -> float:
    """Noise deterministik murah (sin-hash), cukup untuk nebula halus."""
    v = math.sin(x * 12.9898 + y * 78.233 + seed * 3.17) * 43758.5453
    return v - math.floor(v)


def render(size: int = 128, seed: int = 20261017,
           ramp: Sequence[Tuple[int, int, int]] = DEFAULT_RAMP,
           tilt: float = 0.26, glow: float = 1.0,
           stars: bool = True) -> Tuple[int, int, List[bytes]]:
    """Gambar lubang hitam. Kembalikan (w, h, baris RGBA)."""
    size = max(16, int(size))
    cx, cy = size * 0.5, size * 0.515
    rh = size * 0.152                       # radius horizon peristiwa
    ring = rh * 1.13                        # cincin foton
    a = size * 0.455                        # semi-mayor piringan
    b = a * max(0.10, tilt)                 # semi-minor (kemiringan pandang)
    e_in = (rh * 1.30) / a                  # tepi dalam piringan (ternormalisasi)
    rnd = random.Random(seed)

    star_pts = []
    if stars:
        for _ in range(max(24, size * size // 110)):
            star_pts.append((rnd.random() * size, rnd.random() * size,
                             0.25 + 0.75 * rnd.random(), rnd.random()))

    rows: List[bytes] = []
    for y in range(size):
        row = bytearray()
        dy = y - cy
        for x in range(size):
            dx = x - cx
            r = math.sqrt(dx * dx + dy * dy)

            # --- latar: nebula sangat gelap + vignette ---
            n = _noise(x / size * 3.1, y / size * 3.1, seed)
            n2 = _noise(x / size * 7.7, y / size * 7.7, seed + 11)
            base = 5 + 11 * n * n2
            vig = 1.0 - 0.55 * min(1.0, r / (size * 0.72))
            cr, cg, cb = base * vig, base * vig * 1.06, base * vig * 1.28

            # --- medan bintang (diredam di dekat lubang karena lensing) ---
            for sx, sy, br, hue in star_pts:
                ddx, ddy = x - sx, y - sy
                if abs(ddx) > 1.2 or abs(ddy) > 1.2:
                    continue
                d2 = ddx * ddx + ddy * ddy
                if d2 > 1.5:
                    continue
                falloff = max(0.0, 1.0 - d2)
                redam = 0.12 + 0.88 * min(1.0, max(0.0, (r - rh * 1.6) / (size * 0.3)))
                inten = br * falloff * redam * 235
                cr += inten * (0.85 + 0.3 * hue)
                cg += inten * (0.9 + 0.2 * hue)
                cb += inten * 1.12

            # --- piringan akresi (bagian depan & belakang) ---
            ex = dx / a
            ey = dy / b
            e = math.sqrt(ex * ex + ey * ey)
            if e_in < e < 1.05:
                t = (e - e_in) / max(1e-6, 1.05 - e_in)
                ang = math.atan2(ey, ex)
                # Doppler beaming: sisi yang mendekat jauh lebih terang
                dop = 1.0 + 0.62 * math.cos(ang - math.pi * 0.92)
                # tepi luar memudar, tepi dalam panas
                inten = ((1.0 - t) ** 1.55) * max(0.15, dop) * glow
                # piringan belakang (atas) lebih redup - tertutup lensing
                if dy < 0:
                    inten *= 0.55
                turb = 0.82 + 0.36 * _noise(x / size * 22.0 + t * 6.0,
                                            y / size * 9.0, seed + 5)
                inten *= turb
                rr, gg, bb = _ramp(min(1.0, t * 0.92 + (1.0 - min(1.4, inten)) * 0.22), ramp)
                k = min(1.6, inten)
                cr = cr * (1 - min(1.0, k)) + rr * k
                cg = cg * (1 - min(1.0, k)) + gg * k
                cb = cb * (1 - min(1.0, k)) + bb * k

            # --- busur lensing: cahaya piringan belakang melengkung di atas ---
            if dy < 0 and rh * 1.02 < r < rh * 2.35 and abs(dx) < a * 0.98:
                k = 1.0 - abs(r - rh * 1.62) / (rh * 0.75)
                if k > 0:
                    k = (k ** 1.7) * (1.0 - abs(dx) / (a * 1.05)) * 0.95 * glow
                    rr, gg, bb = _ramp(0.30, ramp)
                    cr += rr * k * 0.95
                    cg += gg * k * 0.95
                    cb += bb * k * 0.95

            # --- cincin foton ---
            dr = abs(r - ring)
            if dr < rh * 0.30:
                k = (1.0 - dr / (rh * 0.30)) ** 2.2 * 1.15 * glow
                rr, gg, bb = _ramp(0.02, ramp)
                cr += rr * k
                cg += gg * k
                cb += bb * k

            # --- halo luar lembut ---
            if rh < r < rh * 3.4:
                k = (1.0 - (r - rh) / (rh * 2.4)) ** 3.0 * 0.30 * glow
                rr, gg, bb = _ramp(0.45, ramp)
                cr += rr * k
                cg += gg * k
                cb += bb * k

            # --- horizon peristiwa: hitam mutlak ---
            if r < rh:
                cr = cg = cb = 0.0
            elif r < rh * 1.06:
                k = (r - rh) / (rh * 0.06)
                cr, cg, cb = cr * k, cg * k, cb * k

            row += bytes((max(0, min(255, int(cr))),
                          max(0, min(255, int(cg))),
                          max(0, min(255, int(cb))), 255))
        rows.append(bytes(row))
    return size, size, rows


def pack_icon(size: int = 128, kind: str = "inti") -> Tuple[int, int, List[bytes]]:
    return render(size, seed=hash(kind) % 9999 + 7, ramp=RAMP.get(kind, DEFAULT_RAMP),
                  tilt=0.27, glow=1.0)


def button_icons(size: int = 32) -> Dict[str, Tuple[int, int, List[bytes]]]:
    """Ikon tombol ActionForm. Path dalam pack: textures/ui/crvx_<kind>.png"""
    out: Dict[str, Tuple[int, int, List[bytes]]] = {}
    for index, kind in enumerate(("turbo", "hemat", "ganas", "hud", "status", "restore")):
        out[kind] = render(size, seed=1000 + index * 37, ramp=RAMP[kind],
                           tilt=0.30, glow=1.05, stars=False)
    return out


def banner(width: int = 256, height: int = 96) -> Tuple[int, int, List[bytes]]:
    """Banner lebar untuk laporan/preview: lubang hitam + pita gradien."""
    size, _, square = render(96, seed=4242, ramp=RAMP["status"], tilt=0.24)
    rows: List[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            t = x / max(1, width - 1)
            base = (int(8 + 26 * t), int(6 + 12 * (1 - t)), int(16 + 34 * (1 - t)))
            if x < size and y < size:
                o = x * 4
                px = square[y][o:o + 4]
                k = 1.0 - 0.35 * t
                row += bytes((int(px[0] * k), int(px[1] * k), int(px[2] * k), 255))
            else:
                row += bytes(base + (255,))
        rows.append(bytes(row))
    return width, height, rows
