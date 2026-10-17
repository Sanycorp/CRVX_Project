# CRVX TURBOFRAME - MODE 60 FPS

- **Plan ID**: `6c18c98927ce`
- **Perangkat**:   Generic Android (nyata)
- **SoC**: tidak dikenal | tier **MID**
- **Android**: 14 (SDK 34) | RAM 6 GB
- **Layar**: - | refresh 120Hz, 90Hz, 60Hz | aktif 60 Hz
- **Minecraft**: - | options.txt dapat ditulis
- **Cap engine**: 120 FPS (profil generik: diasumsikan engine bisa 120 FPS. Jalankan `crvx detect` untuk angka pasti perangkat Anda)

## Proyeksi

| Metrik | Nilai |
| --- | --- |
| Target FPS | 60 |
| Perkiraan tercapai | **55.0 FPS** |
| Batas atas | 60.0 FPS |
| Frame time | 18.18 ms |
| Stabilitas | 79.8/100 |
| Keyakinan | 70% |
| Baterai | +20.1% lebih boros |
| Panas | normal |

### Catatan jujur dari engine

- Perkiraan konsumsi baterai +20% lebih boros dibanding kondisi awal.

## Langkah yang akan dijalankan (15)

### 1. Backup options.txt sebelum disentuh
`minecraft` | risiko **safe** | gain ~+0.0 FPS (keyakinan 100%)

Menyalin options.txt asli ke folder kerja CRVX. Undo selalu bisa mengembalikan kondisi awal apa pun yang terjadi.

```sh
cp /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt /data/local/tmp/crvx_options_backup.txt 2>/dev/null || true
```

### 2. Matikan Battery Saver & pembatas performa
`system` | risiko **safe** | gain ~+5.0 FPS (keyakinan 70%)

Battery Saver memotong frekuensi CPU dan memaksa 60 Hz. Selama optimasi aktif, fitur ini dimatikan agar target FPS tercapai.

```sh
settings put global low_power 0
settings put global battery_saver_enabled 0
settings put global adaptive_battery_enabled 0
```

### 3. Matikan animasi sistem (skala 0)
`system` | risiko **safe** | gain ~+0.0 FPS (keyakinan 80%)

Animasi window/transition/animator memakan frame budget dan membuat CPU sibuk tepat saat game butuh. Skala 0 = sistem terasa instan.

```sh
settings put global window_animation_scale 0
settings put global transition_animation_scale 0
settings put global animator_duration_scale 0
```

### 4. Naikkan peak/min refresh rate sistem ke 60 Hz
`display` | risiko **safe** | gain ~+0.0 FPS (keyakinan 70%)

`peak_refresh_rate` + `min_refresh_rate` di namespace system dipakai Pixel, Xiaomi, Samsung, dan banyak ROM lain. Kalau kunci tidak dikenal, perintah diabaikan tanpa efek samping.

```sh
settings put system peak_refresh_rate 60.0
settings put system min_refresh_rate 60.0
settings put system user_refresh_rate 60.0
```

### 5. Kunci refresh rate lewat namespace secure (60 Hz)
`display` | risiko **safe** | gain ~+0.0 FPS (keyakinan 45%)

Beberapa ROM (OnePlus/Oppo lama, sebagian Android 14+) membaca kunci refresh rate dari namespace secure, bukan system.

```sh
settings put secure min_refresh_rate 60.0
settings put secure peak_refresh_rate 60.0
settings put global user_refresh_rate 60.0
```

### 6. Matikan blur jendela (kurangi beban GPU kompositor)
`display` | risiko **safe** | gain ~+0.0 FPS (keyakinan 50%)

`disable_window_blurs=1` mematikan blur real-time di notification shade dan dialog. Mengurangi kerja SurfaceFlinger saat game berjalan.

```sh
settings put global disable_window_blurs 1
```

### 7. Kunci kecerahan (matikan auto-brightness)
`display` | risiko **safe** | gain ~+0.0 FPS (keyakinan 55%)

Sensor cahaya yang terus menyesuaikan kecerahan memicu refresh-rate switching dan micro-stutter. Kecerahan tetap = frame pacing lebih rata.

```sh
settings put system screen_brightness_mode 0
```

### 8. Aktifkan Game Mode API: PERFORMANCE
`gamemode` | risiko **safe** | gain ~+4.0 FPS (keyakinan 75%)

Android 12L+ punya Game Mode resmi. Mode PERFORMANCE meminta Power HAL memberi latensi terendah dan mencegah OEM menurunkan performa game.

```sh
cmd game mode performance com.mojang.minecraftpe
```

### 9. Override FPS Game Mode ke 60 (custom intervention)
`gamemode` | risiko **moderate** | gain ~+2.0 FPS (keyakinan 60%)

`cmd game set --fps` memberi tahu framework target frame rate game. Pada perangkat yang mendukung, ini yang membuat Bedrock benar-benar jalan di 60 FPS alih-alih jatuh ke 60.

```sh
cmd game set --fps 60 com.mojang.minecraftpe
```

### 10. Tulis intervensi game_overlay (persisten lintas reboot)
`gamemode` | risiko **advanced** | gain ~+2.0 FPS (keyakinan 50%)

`device_config put game_overlay` menyimpan konfigurasi FPS + downscale per mode game, jadi tetap berlaku setelah restart. Nilai FPS yang tidak didukung panel bisa membuat SurfaceFlinger restart - karena itu hanya diisi dengan angka yang panel Anda dukung.

```sh
device_config put game_overlay com.mojang.minecraftpe mode=2,fps=60,downscaleFactor=1.00
settings put global game_mode_overlay_com.mojang.minecraftpe 1
```

### 11. Terapkan preset grafis MODE 60 FPS ke options.txt
`minecraft` | risiko **moderate** | gain ~+15.8 FPS (keyakinan 90%)

Render distance 7 chunk (112 blok), MSAA 1x, V-Sync ON, cap 60 FPS, partikel 40%, daun solid (fast). Semua kunci memakai nama modern Bedrock 26.x dan tetap terbaca versi lama.

```sh
grep -q '^gfx_viewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:112/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_viewdistance:112' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_particleviewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:0.40/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_particleviewdistance:0.40' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_smoothlighting:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_smoothlighting:.*/gfx_smoothlighting:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_smoothlighting:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_transparentleaves:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_transparentleaves:.*/gfx_transparentleaves:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_fancyskies:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_fancyskies:.*/gfx_fancyskies:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_msaa:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_msaa:.*/gfx_msaa:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_max_framerate:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:60/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate:60' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_vsync:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_vsync:.*/gfx_vsync:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_vsync:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_multithreaded_renderer:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_multithreaded_renderer:.*/gfx_multithreaded_renderer:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_field_of_view:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_field_of_view:.*/gfx_field_of_view:66/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
grep -q '^gfx_max_framerate_advanced:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt
```

### 12. Kompilasi AOT penuh (ART speed) untuk Minecraft
`runtime` | risiko **safe** | gain ~+3.0 FPS (keyakinan 70%)

Android menjalankan sebagian kode lewat JIT/interpreter. `cmd package compile -m speed -f` memaksa kompilasi AOT penuh sehingga stutter saat load chunk dan awal sesi berkurang drastis.

```sh
cmd package compile -m speed -f com.mojang.minecraftpe
cmd package compile -m speed-profile -f com.mojang.minecraftpe
```

### 13. Bebaskan Minecraft dari Doze + pembatasan background
`runtime` | risiko **safe** | gain ~+0.0 FPS (keyakinan 70%)

Mencegah Android menidurkan thread jaringan/render Minecraft dan menghentikan proses saat layar redup atau game di-background sebentar.

```sh
dumpsys deviceidle whitelist +com.mojang.minecraftpe
cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND allow
cmd appops set com.mojang.minecraftpe WAKE_LOCK allow
```

### 14. Bersihkan memori background sebelum sesi
`memory` | risiko **safe** | gain ~+0.0 FPS (keyakinan 60%)

`am kill-all` menutup proses cache yang tidak terlihat. Mengurangi tekanan LMK (low memory killer) yang biasa jadi penyebab stutter tiba-tiba saat main.

```sh
am kill-all
cmd package bg-dexopt-job 2>/dev/null || true
```

### 15. Restart Minecraft agar konfigurasi terbaca
`minecraft` | risiko **safe** | gain ~+0.0 FPS (keyakinan 100%)

options.txt hanya dibaca saat game start. Aturan ini menutup lalu membuka kembali Minecraft. Simpan dunia dulu sebelum menjalankan.

```sh
am force-stop com.mojang.minecraftpe
monkey -p com.mojang.minecraftpe -c android.intent.category.LAUNCHER 1
```
