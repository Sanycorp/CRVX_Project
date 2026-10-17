# CRVX TURBOFRAME

**FPS Boost Engine untuk Minecraft Bedrock / MCPE (Android)** — versi engine `2026.10.1`,
disesuaikan untuk Bedrock **26.52** (rilis Okt 2026) dan Preview **26.70**.

Mode **60 / 90 / 120 / 144 FPS**. Python murni (stdlib saja, tanpa `pip install` apa pun),
CLI + Control Panel web, dan semuanya punya jalur **undo**.

```
60 FPS   STABIL    frame-time paling rata, paling dingin, paling irit
90 FPS   SMOOTH    keseimbangan FPS / suhu / visual
120 FPS  ULTRA     kompetitif, input latency minimum
144 FPS  EXTREME   gaming phone (ROG / RedMagic / iQOO), semua batas dilepas
```

---

## Jalan tercepat

```bash
python3 -m crvx serve --port 8120      # Control Panel web (auto-detect perangkat)
```

atau lewat CLI:

```bash
python3 -m crvx doctor                 # cek adb + perangkat
python3 -m crvx detect                 # deteksi SoC, layar, termal, versi Minecraft
python3 -m crvx modes                  # apa yang realistis untuk HP ini
python3 -m crvx plan  --mode 120       # lihat rencana + proyeksi (tidak mengubah apa pun)
python3 -m crvx apply --mode 120 --bench -y   # terapkan + ukur FPS sebelum/sesudah
python3 -m crvx undo                   # kembalikan semuanya
```

Tanpa PC? Skrip siap jalan sudah ada di **`boost/`**:

| File | Fungsi |
| --- | --- |
| `boost/120/boost-120-fps.sh` | Linux/macOS + adb (ada preflight & verifikasi) |
| `boost/120/boost-120-fps.bat` | Windows + adb |
| `boost/120/termux-120-fps.sh` | **tanpa PC**: Termux pairing ke HP sendiri |
| `boost/120/ondevice-120-fps.sh` | Shizuku / LADB / root shell di HP |
| `boost/120/undo-120-fps.sh` | batalkan semua |

Folder `boost/60/` dan `boost/90/` isinya sama untuk mode lain.
Skrip ini dibuat dari profil generik — jalankan `python3 -m crvx export --mode 120 --outdir boost`
dengan HP tersambung supaya nilainya (resolusi, refresh rate, versi Minecraft) persis perangkatmu.

---

## Apa yang benar-benar dilakukan engine

| Lapis | Tuas |
| --- | --- |
| **Tampilan** | `cmd display set-user-preferred-display-mode`, `peak/min_refresh_rate`, kunci vendor (`miui_refresh_rate`, One UI `refresh_rate_mode`, `oplus_customize_*`) |
| **Game Mode API** | `cmd game mode performance`, `cmd game set --fps/--downscale`, `device_config game_overlay` (persisten) |
| **Minecraft** | `options.txt`: `gfx_viewdistance`, `gfx_msaa`, `gfx_vsync`, `gfx_max_framerate`, `gfx_smoothlighting`, `gfx_transparentleaves`, `gfx_particleviewdistance`, `gfx_fancyskies` — nama kunci modern **+ alias versi lama** |
| **Runtime** | ART AOT `cmd package compile -m speed`, doze whitelist, appops, `am kill-all`, animasi sistem 0 |
| **Termal / CPU / GPU** (root) | `cmd thermalservice override-status`, governor `performance`, `core_ctl` off, GPU devfreq, swappiness/read-ahead |
| **Pack** | `.mcpack` fog-cut yang dibuat sendiri (manifest + PNG valid, bukan mod APK) |

Ditambah dua hal yang biasanya tidak ada di "FPS booster":

* **Telemetri FPS nyata** — `dumpsys SurfaceFlinger --latency` → fallback `gfxinfo framestats`,
  timestamp di-dedupe (tidak ada frame yang dihitung dua kali), lalu dihitung FPS avg / 1% low /
  5% low / median / frame-time p95 / jank / stutter index / skor smoothness 0–100.
* **Adaptive Frame Governor** — kontroler PID closed-loop yang menahan FPS sedekat target dengan
  mengorbankan kualitas sesedikit mungkin, dan **menurunkan target otomatis saat termal memburuk**.

---

## Baca ini (jujur)

Bedrock Android **masih dikunci 60 FPS di banyak perangkat** walau layarnya 120 Hz — itu keputusan
engine Mojang, bukan sesuatu yang bisa dipaksa aplikasi pihak ketiga. Yang bisa dilakukan:

1. memastikan panel benar-benar berjalan di 90/120 Hz,
2. memastikan Android/OEM tidak menahan game di 60 Hz (Game Mode, MIUI Smart FPS, One UI),
3. membuat game **mencapai** cap-nya dan **bertahan** di sana (frame-time rata, tanpa throttling),
4. kalau cap-nya memang 60 — membuat 60 FPS itu mulus tanpa jank.

Engine selalu melaporkan **cap engine** dan **proyeksi realistis** untuk perangkatmu, termasuk saat
target tidak tercapai. Samsung: aktifkan juga *Game Launcher → Frame rate 120 FPS* (aturan
`samsung.game_launcher` membukakan panelnya).

Tidak ada modifikasi APK/binary game, tidak ada cheat, tidak ada injeksi. Yang disentuh: setelan
Android, setelan grafis Minecraft milikmu sendiri (`options.txt`), dan resource pack sah.
Semua tercatat di jurnal dan bisa dibalik dengan `crvx undo`.

---

## Uji

```bash
python3 -m unittest discover -s tests -t .      # 36 uji, tanpa dependensi
```

Tanpa HP, tambahkan `--sim` di perintah apa pun: simulator perangkat (POCO X6 Pro ·
Dimensity 8300 Ultra · 120 Hz · Android 15) merespons perintah dan model FPS-nya berubah
saat preset diterapkan, jadi seluruh alur bisa diuji dari ujung ke ujung.
