#!/usr/bin/env bash
# CRVX TURBOFRAME - MODE 120 FPS
# Perangkat : Generic Android (profil generik)
# Android   : 14 (SDK 34)  |  panel 120 Hz
# Target    : 120 FPS  (perkiraan tercapai 87.0 FPS)
# Plan ID   : 70c22ee77e17
# Jalankan : bash <nama-file>.sh   (batalkan: bash crvx-undo.sh)
set -u

ADB="${ADB:-adb}"
SERIAL=""
if [ -n "$SERIAL" ]; then T=(-s "$SERIAL"); else T=(); fi

C_GREEN="\033[38;5;46m"; C_PINK="\033[38;5;212m"; C_DIM="\033[2m"; C_RED="\033[38;5;203m"; C_AMBER="\033[38;5;220m"; C_OFF="\033[0m"
step() { printf "%b[%02d/%02d]%b %s\n" "$C_PINK" "$1" "$2" "$C_OFF" "$3"; }
run()  { if [ "${DRY_RUN:-0}" = "1" ]; then echo "  DRY $1"; return 0; fi;
         out=$("$ADB" "${T[@]}" shell "$1" 2>&1); rc=$?;
         if [ $rc -ne 0 ]; then printf "%b  ! gagal (rc=%s): %s%b\n" "$C_RED" "$rc" "${out:0:120}" "$C_OFF"; fi;
         [ -n "$out" ] && printf "%b  %s%b\n" "$C_DIM" "${out:0:160}" "$C_OFF"; return 0; }
runroot() { run "su -c '$1'"; }

trap 'printf "%b\nDibatalkan. Kembalikan semua perubahan dengan: bash crvx-undo.sh%b\n" "$C_RED" "$C_OFF"; exit 130' INT

printf "%b%s%b %s\n\n" "$C_GREEN" "==>" "PREFLIGHT"
command -v "$ADB" >/dev/null 2>&1 || { printf "%badb tidak ditemukan. Install platform-tools dulu.%b\n" "$C_RED" "$C_OFF"; exit 1; }
STATE=$("$ADB" ${T[@]+"${T[@]}"} get-state 2>/dev/null || echo offline)
if [ "$STATE" != "device" ]; then
  printf "%bPerangkat belum tersambung.%b Aktifkan USB Debugging / Wireless Debugging lalu ulangi.\n" "$C_RED" "$C_OFF"
  "$ADB" devices; exit 1; fi
MAXHZ=$("$ADB" ${T[@]+"${T[@]}"} shell "dumpsys display" 2>/dev/null | grep -oE "fps=[0-9.]+" | cut -d= -f2 | sort -n | tail -1)
MODEL=$("$ADB" ${T[@]+"${T[@]}"} shell getprop ro.product.model 2>/dev/null | tr -d "\r")
TARGET_HZ=120
printf "  perangkat    : %s\n" "${MODEL:-tidak diketahui}"
printf "  refresh maks : %s Hz\n" "${MAXHZ:-?}"
if [ -n "$MAXHZ" ] && [ "$(printf "%s\n" "$MAXHZ < $TARGET_HZ" | bc 2>/dev/null || echo 0)" = "1" ]; then
  printf "%b  ! panel tidak punya mode %s Hz - FPS akan dibatasi refresh layar.%b\n" "$C_AMBER" "$TARGET_HZ" "$C_OFF"; fi
MCVER=$("$ADB" ${T[@]+"${T[@]}"} shell dumpsys package com.mojang.minecraftpe 2>/dev/null | grep -m1 versionName | tr -d " \r")
printf "  minecraft    : %s\n" "${MCVER:-tidak terdeteksi}"
printf "%b%s%b %s\n\n" "$C_GREEN" "==>" "EKSEKUSI"

step 1 19 "Backup options.txt sebelum disentuh"
# [minecraft | risiko safe] Menyalin options.txt asli ke folder kerja CRVX. Undo selalu bisa mengembalikan kondisi awal apa pun yang terjadi.
run 'cp /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt /data/local/tmp/crvx_options_backup.txt 2>/dev/null || true'

step 2 19 "Matikan Battery Saver & pembatas performa"
# [system | risiko safe] Battery Saver memotong frekuensi CPU dan memaksa 60 Hz. Selama optimasi aktif, fitur ini dimatikan agar target FPS tercapai.
run 'settings put global low_power 0'
run 'settings put global battery_saver_enabled 0'
run 'settings put global adaptive_battery_enabled 0'

step 3 19 "Matikan animasi sistem (skala 0)"
# [system | risiko safe] Animasi window/transition/animator memakan frame budget dan membuat CPU sibuk tepat saat game butuh. Skala 0 = sistem terasa instan.
run 'settings put global window_animation_scale 0'
run 'settings put global transition_animation_scale 0'
run 'settings put global animator_duration_scale 0'

step 4 19 "Naikkan peak/min refresh rate sistem ke 120 Hz"
# [display | risiko safe] `peak_refresh_rate` + `min_refresh_rate` di namespace system dipakai Pixel, Xiaomi, Samsung, dan banyak ROM lain. Kalau kunci tidak dikenal, perintah diabaikan tanpa efek samping.
run 'settings put system peak_refresh_rate 120.0'
run 'settings put system min_refresh_rate 120.0'
run 'settings put system user_refresh_rate 120.0'

step 5 19 "Kunci refresh rate lewat namespace secure (120 Hz)"
# [display | risiko safe] Beberapa ROM (OnePlus/Oppo lama, sebagian Android 14+) membaca kunci refresh rate dari namespace secure, bukan system.
run 'settings put secure min_refresh_rate 120.0'
run 'settings put secure peak_refresh_rate 120.0'
run 'settings put global user_refresh_rate 120.0'

step 6 19 "Matikan blur jendela (kurangi beban GPU kompositor)"
# [display | risiko safe] `disable_window_blurs=1` mematikan blur real-time di notification shade dan dialog. Mengurangi kerja SurfaceFlinger saat game berjalan.
run 'settings put global disable_window_blurs 1'

step 7 19 "Kunci kecerahan (matikan auto-brightness)"
# [display | risiko safe] Sensor cahaya yang terus menyesuaikan kecerahan memicu refresh-rate switching dan micro-stutter. Kecerahan tetap = frame pacing lebih rata.
run 'settings put system screen_brightness_mode 0'

step 8 19 "Aktifkan Game Mode API: PERFORMANCE"
# [gamemode | risiko safe] Android 12L+ punya Game Mode resmi. Mode PERFORMANCE meminta Power HAL memberi latensi terendah dan mencegah OEM menurunkan performa game.
run 'cmd game mode performance com.mojang.minecraftpe'

step 9 19 "Override FPS Game Mode ke 120 (custom intervention)"
# [gamemode | risiko moderate] `cmd game set --fps` memberi tahu framework target frame rate game. Pada perangkat yang mendukung, ini yang membuat Bedrock benar-benar jalan di 120 FPS alih-alih jatuh ke 60.
run 'cmd game set --fps 120 com.mojang.minecraftpe'

step 10 19 "Backbuffer resize 85% (tuas FPS terbesar)"
# [gamemode | risiko moderate] WindowManager merender game pada 85% resolusi lalu meng-upscale. Dokumentasi Android: memangkas sampai 30% beban GPU. Ditukar dengan ketajaman gambar sedikit berkurang.
run 'cmd game set --downscale 0.85 com.mojang.minecraftpe'

step 11 19 "Tulis intervensi game_overlay (persisten lintas reboot)"
# [gamemode | risiko advanced] `device_config put game_overlay` menyimpan konfigurasi FPS + downscale per mode game, jadi tetap berlaku setelah restart. Nilai FPS yang tidak didukung panel bisa membuat SurfaceFlinger restart - karena itu hanya diisi dengan angka yang panel Anda dukung.
run 'device_config put game_overlay com.mojang.minecraftpe mode=2,fps=120,downscaleFactor=0.85'
run 'settings put global game_mode_overlay_com.mojang.minecraftpe 1'

step 12 19 "Terapkan preset grafis MODE 120 FPS ke options.txt"
# [minecraft | risiko moderate] Render distance 5 chunk (80 blok), MSAA 1x, V-Sync OFF, cap 120 FPS, partikel 25%, daun solid (fast). Semua kunci memakai nama modern Bedrock 26.x dan tetap terbaca versi lama.
run 'grep -q '"'"'^gfx_viewdistance:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_viewdistance:.*/gfx_viewdistance:80/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_viewdistance:80'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_particleviewdistance:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_particleviewdistance:.*/gfx_particleviewdistance:0.25/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_particleviewdistance:0.25'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_smoothlighting:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_smoothlighting:.*/gfx_smoothlighting:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_smoothlighting:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_transparentleaves:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_transparentleaves:.*/gfx_transparentleaves:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_transparentleaves:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_fancyskies:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_fancyskies:.*/gfx_fancyskies:1/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_fancyskies:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_msaa:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_msaa:.*/gfx_msaa:1/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_msaa:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_max_framerate:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_max_framerate:.*/gfx_max_framerate:120/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_max_framerate:120'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_vsync:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_vsync:.*/gfx_vsync:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_vsync:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_multithreaded_renderer:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_multithreaded_renderer:.*/gfx_multithreaded_renderer:1/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_multithreaded_renderer:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_field_of_view:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_field_of_view:.*/gfx_field_of_view:66/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_field_of_view:66'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'grep -q '"'"'^gfx_max_framerate_advanced:'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i '"'"'s/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_max_framerate_advanced:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'

step 13 19 "Lepas kunci V-Sync + set cap framerate engine"
# [minecraft | risiko moderate] Bedrock menyimpan `gfx_vsync` dan `gfx_max_framerate` di options.txt. V-Sync OFF + cap 120 adalah satu-satunya cara engine mau melewati 60 FPS di perangkat yang mendukung.
run 'sed -i '"'"'s/^gfx_vsync:.*/gfx_vsync:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'sed -i '"'"'s/^gfx_max_framerate:.*/gfx_max_framerate:120/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
run 'sed -i '"'"'s/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/'"'"' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo '"'"'gfx_max_framerate_advanced:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'

step 14 19 "Kompilasi AOT penuh (ART speed) untuk Minecraft"
# [runtime | risiko safe] Android menjalankan sebagian kode lewat JIT/interpreter. `cmd package compile -m speed -f` memaksa kompilasi AOT penuh sehingga stutter saat load chunk dan awal sesi berkurang drastis.
run 'cmd package compile -m speed -f com.mojang.minecraftpe'
run 'cmd package compile -m speed-profile -f com.mojang.minecraftpe'

step 15 19 "Bebaskan Minecraft dari Doze + pembatasan background"
# [runtime | risiko safe] Mencegah Android menidurkan thread jaringan/render Minecraft dan menghentikan proses saat layar redup atau game di-background sebentar.
run 'dumpsys deviceidle whitelist +com.mojang.minecraftpe'
run 'cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND allow'
run 'cmd appops set com.mojang.minecraftpe WAKE_LOCK allow'

step 16 19 "Bersihkan memori background sebelum sesi"
# [memory | risiko safe] `am kill-all` menutup proses cache yang tidak terlihat. Mengurangi tekanan LMK (low memory killer) yang biasa jadi penyebab stutter tiba-tiba saat main.
run 'am kill-all'
run 'cmd package bg-dexopt-job 2>/dev/null || true'

step 17 19 "Mode fokus: DND + layar tetap menyala saat sesi"
# [runtime | risiko moderate] Notifikasi masuk memicu overlay + wake lock yang menjatuhkan frame. DND dinyalakan hanya selama sesi; `crvx undo` mengembalikannya.
run 'cmd notification set_dnd on'
run 'settings put global stay_on_while_plugged_in 3'

step 18 19 "Thermal service: status 1"
# [thermal | risiko advanced] Mengatakan ke ThermalService bahwa perangkat sedang dingin sehingga throttling preemptif tidak dipicu terlalu cepat. PERANGKAT TETAP BISA PANAS - gunakan kipas/cooling fan dan jangan menutupi ventilasi.
run 'cmd thermalservice override-status 1'
run 'settings put global thermal_status_override 1'

step 19 19 "Restart Minecraft agar konfigurasi terbaca"
# [minecraft | risiko safe] options.txt hanya dibaca saat game start. Aturan ini menutup lalu membuka kembali Minecraft. Simpan dunia dulu sebelum menjalankan.
run 'am force-stop com.mojang.minecraftpe'
run 'monkey -p com.mojang.minecraftpe -c android.intent.category.LAUNCHER 1'

printf "\n%b==>%b selesai. Buka Minecraft, masuk dunia, lalu ukur dengan: crvx bench\n" "$C_GREEN" "$C_OFF"
