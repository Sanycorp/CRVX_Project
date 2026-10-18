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

## Add-on dari dalam game (tanpa ADB, tanpa PC)

`python3 -m crvx addon --out addon/CRVX_Turbo60.mcaddon` menghasilkan satu file
**`addon/CRVX_Turbo60.mcaddon`** (39 KB) berisi tiga pack:

| Pack | Isi | Efek |
| --- | --- | --- |
| `CRVX Turbo60 - Visual Saver` (RP) | 16 definisi fog dipangkas + `clouds.png` transparan + `rain.png` 88% transparan | fragmen alpha-blended turun → GPU lega, HP lebih dingin |
| `CRVX Turbo60 - Preset Performa` (BP) | `/function crvx/turbo60` · `hemat` · `ganas` · `bersihkan` · `status` · `pulihkan` | gamerule + pembersihan entity → beban CPU & block-update turun |
| `CRVX AutoGovernor - Adaptif` v2 (BP + Script API `@minecraft/server` 2.10.0) |ukur tick-time tiap 3 detik, 4 level hemat, hysteresis, HUD action bar, kontrol chat `!crvx status|mati|nyala|hud|reset` | menyesuaikan diri otomatis saat dunia berat — **tanpa Cheats, achievement tidak terkunci** |

### Tekstur

| Perintah | Hasil |
| --- | --- |
| `python3 -m crvx texture --res 8` | `addon/CRVX_FastTex_8x.mcpack` - tekstur **buatan sendiri** 8x8 (kaca, es, daun alpha-test) + awan transparan + `weather.png` nyaris tak terlihat + fog cut. Sah dibagikan karena tidak memakai aset Mojang. |
| `python3 -m crvx texforge --vanilla <folder/zip/apk> --res 8` | pack 8x8 dari **aset vanilla milikmu sendiri** (hasil ekstrak APK). Tampilan tetap seperti Minecraft asli, bandwidth tekstur tinggal seperempat. Strip animasi (mis. `water_still.png` 16x512) otomatis dilewati supaya animasi tidak rusak. |

`crvx/texforge.py` berisi decoder PNG murni stdlib (color type 0/2/3/4/6, filter 0-4)
+ box-filter downscale + encoder PNG. Tidak ada dependensi eksternal.

Nama berkas & dimensi tekstur diverifikasi terhadap `Mojang/bedrock-samples` (Okt 2026):
`clouds.png` 256x256, `weather.png` 32x32 (bukan `rain.png`), `glass.png` / `ice.png` /
`leaves_*_opaque.png` 16x16, `water_still.png` 16x512.

Pasang: kirim `.mcaddon` ke HP → buka → Minecraft mengimpornya otomatis →
**Play → ✏️ dunia → Resource Packs & Behavior Packs → Activate** (aktifkan ketiganya).
Jalur `/function` butuh Cheats ON di dunia itu; AutoGovernor tidak butuh.

Tanpa PC? Skrip siap jalan sudah ada di **`boost/`**:

| File | Fungsi |
| --- | --- |
| `boost/120/boost-120-fps.sh` | Linux/macOS + adb (ada preflight & verifikasi) |
| `boost/120/boost-120-fps.bat` | Windows + adb |
| `boost/120/termux-120-fps.sh` | **tanpa PC**: Termux pairing ke HP sendiri |
| `boost/120/ondevice-120-fps.sh` | Shizuku / LADB / root shell di HP |
| `boost/120/undo-120-ondevice.sh` | **batalkan** dari dalam shell HP (tanpa prefiks `adb`) |
| `boost/120/undo-120.sh` / `undo-120.bat` | batalkan semua dari PC |
| `boost/poco-m3-pro-5g/` | skrip device-exact POCO M3 Pro 5G (Dimensity 700, panel 90 Hz, engine cap 60 FPS) |

Folder `boost/60/` dan `boost/90/` isinya sama untuk mode lain.
Skrip di `boost/60|90|120/` dibuat dari profil generik — jalankan
`python3 -m crvx export --mode 120 --outdir boost` dengan HP tersambung supaya nilainya
(resolusi, refresh rate, versi Minecraft) persis perangkatmu.

Skrip on-device sadar bahwa Android 11+ memblokir akses shell ke `/sdcard/Android/data/`:
kalau `options.txt` tidak bisa ditulis, skrip melewati bagian itu dan mencetak nilai yang
harus kamu atur manual lewat **Minecraft → Settings → Video** (atau lewat file manager
ber-Shizuku seperti Material Files / MT Manager).

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
python3 -m unittest discover -s tests -t .      # 88 uji, tanpa dependensi
```

Tanpa HP, tambahkan `--sim` di perintah apa pun: simulator perangkat (POCO X6 Pro ·
Dimensity 8300 Ultra · 120 Hz · Android 15) merespons perintah dan model FPS-nya berubah
saat preset diterapkan, jadi seluruh alur bisa diuji dari ujung ke ujung.

---

## Add-on (impor langsung di HP, tanpa PC/ADB)

| Berkas | Isi |
|---|---|
| `addon/CRVX_FPS_Booster.mcaddon` | RP fog/awan hemat + BP preset gamerule + AutoGovernor v3 (skrip `@minecraft/server` 2.0.0, HUD & pemutus arus). Kontrol: jongkok + pakai item, atau `/scriptevent crvx:…` |
| `addon/CRVX_Void_Arsenal.mcaddon` | 4 armor 3D + pedang 3D (model & tekstur buatan sendiri di kerangka pemain vanilla), resep survival netherite + echo shard |
| `addon/CRVX_Sentinel.mcaddon` | Sentinel Void: penjaga melayang (240 HP / damage 16) yang memburu keluarga monster/undead/arthropod/illager (+keluarga add-on), membalas apa pun yang melukai pemiliknya, tidak menyentuh player/hewan/villager; plus skrip `crvx:scan` & `crvx:basmi` yang menghapus mob kebal `/kill` lewat `Entity.remove()` |

Bangun ulang: `python3 -m crvx.cli addon|arsenal|sentinel`. Pasang: kirim berkas ke HP, buka, lalu aktifkan RP+BP di pengaturan dunia.
