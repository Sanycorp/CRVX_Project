#!/data/data/com.termux/files/usr/bin/bash
# CRVX TURBOFRAME - MODE 60 FPS  [MODE ON-DEVICE / TERMUX]
# Tidak butuh PC. Butuh: Termux + Wireless Debugging (Android 11+).
#
# 1) pkg install android-tools
# 2) Settings > Developer options > Wireless debugging > ON
# 3) Buka 'Wireless debugging' > 'Pair device with pairing code'
#    catat IP:PORT dan kode 6 digit, lalu:
#       adb pair 127.0.0.1:<PAIR_PORT>   (masukkan kode)
#       adb connect 127.0.0.1:<CONNECT_PORT>
# 4) bash crvx-termux.sh
set -u
ADB="${ADB:-adb}"
if ! command -v "$ADB" >/dev/null 2>&1; then
  echo "adb belum ada. Jalankan: pkg install android-tools"; exit 1; fi
if ! "$ADB" get-state >/dev/null 2>&1; then
  echo "Belum tersambung. Ikuti langkah pairing di komentar atas."; exit 1; fi

PKG="com.mojang.minecraftpe"
ok() { printf "  \033[38;5;46m[OK]\033[0m %s\n" "$1"; }
no() { printf "  \033[38;5;203m[--]\033[0m %s\n" "$1"; }

echo "== Backup options.txt sebelum disentuh"
"$ADB" shell "cp /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt /data/local/tmp/crvx_options_backup.txt 2>/dev/null || true" >/dev/null 2>&1 && ok "backup options.txt" || no "backup options.txt"
echo "== Matikan Battery Saver & pembatas performa"
"$ADB" shell "settings put global low_power 0" >/dev/null 2>&1 && ok "low_power 0" || no "low_power 0"
"$ADB" shell "settings put global battery_saver_enabled 0" >/dev/null 2>&1 && ok "battery saver off" || no "battery saver off"
"$ADB" shell "settings put global adaptive_battery_enabled 0" >/dev/null 2>&1 && ok "adaptive battery off" || no "adaptive battery off"
echo "== Matikan animasi sistem (skala 0)"
"$ADB" shell "settings put global window_animation_scale 0" >/dev/null 2>&1 && ok "window anim 0" || no "window anim 0"
"$ADB" shell "settings put global transition_animation_scale 0" >/dev/null 2>&1 && ok "transition anim 0" || no "transition anim 0"
"$ADB" shell "settings put global animator_duration_scale 0" >/dev/null 2>&1 && ok "animator 0" || no "animator 0"
echo "== Naikkan peak/min refresh rate sistem ke 60 Hz"
"$ADB" shell "settings put system peak_refresh_rate 60.0" >/dev/null 2>&1 && ok "peak_refresh_rate" || no "peak_refresh_rate"
"$ADB" shell "settings put system min_refresh_rate 60.0" >/dev/null 2>&1 && ok "min_refresh_rate" || no "min_refresh_rate"
"$ADB" shell "settings put system user_refresh_rate 60.0" >/dev/null 2>&1 && ok "user_refresh_rate" || no "user_refresh_rate"
echo "== Kunci refresh rate lewat namespace secure (60 Hz)"
"$ADB" shell "settings put secure min_refresh_rate 60.0" >/dev/null 2>&1 && ok "secure.min_refresh_rate" || no "secure.min_refresh_rate"
"$ADB" shell "settings put secure peak_refresh_rate 60.0" >/dev/null 2>&1 && ok "secure.peak_refresh_rate" || no "secure.peak_refresh_rate"
"$ADB" shell "settings put global user_refresh_rate 60.0" >/dev/null 2>&1 && ok "global.user_refresh_rate" || no "global.user_refresh_rate"
echo "== Matikan blur jendela (kurangi beban GPU kompositor)"
"$ADB" shell "settings put global disable_window_blurs 1" >/dev/null 2>&1 && ok "blur off" || no "blur off"
echo "== Kunci kecerahan (matikan auto-brightness)"
"$ADB" shell "settings put system screen_brightness_mode 0" >/dev/null 2>&1 && ok "auto-brightness off" || no "auto-brightness off"
echo "== Aktifkan Game Mode API: PERFORMANCE"
"$ADB" shell "cmd game mode performance com.mojang.minecraftpe" >/dev/null 2>&1 && ok "game mode = performance" || no "game mode = performance"
echo "== Override FPS Game Mode ke 60 (custom intervention)"
"$ADB" shell "cmd game set --fps 60 com.mojang.minecraftpe" >/dev/null 2>&1 && ok "fps override = 60" || no "fps override = 60"
echo "== Tulis intervensi game_overlay (persisten lintas reboot)"
"$ADB" shell "device_config put game_overlay com.mojang.minecraftpe mode=2,fps=60,downscaleFactor=1.00" >/dev/null 2>&1 && ok "game_overlay config" || no "game_overlay config"
"$ADB" shell "settings put global game_mode_overlay_com.mojang.minecraftpe 1" >/dev/null 2>&1 && ok "penanda overlay" || no "penanda overlay"
echo "== Terapkan preset grafis MODE 60 FPS ke options.txt"
"$ADB" shell "grep -q '^gfx_viewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:112/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_viewdistance:112' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_viewdistance = 112" || no "gfx_viewdistance = 112"
"$ADB" shell "grep -q '^gfx_particleviewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:0.40/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_particleviewdistance:0.40' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_particleviewdistance = 0.40" || no "gfx_particleviewdistance = 0.40"
"$ADB" shell "grep -q '^gfx_smoothlighting:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_smoothlighting:.*/gfx_smoothlighting:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_smoothlighting:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_smoothlighting = 1" || no "gfx_smoothlighting = 1"
"$ADB" shell "grep -q '^gfx_transparentleaves:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_transparentleaves:.*/gfx_transparentleaves:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_transparentleaves = 0" || no "gfx_transparentleaves = 0"
"$ADB" shell "grep -q '^gfx_fancyskies:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_fancyskies:.*/gfx_fancyskies:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_fancyskies = 1" || no "gfx_fancyskies = 1"
"$ADB" shell "grep -q '^gfx_msaa:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_msaa:.*/gfx_msaa:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_msaa = 1" || no "gfx_msaa = 1"
"$ADB" shell "grep -q '^gfx_max_framerate:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:60/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate:60' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_max_framerate = 60" || no "gfx_max_framerate = 60"
"$ADB" shell "grep -q '^gfx_vsync:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_vsync:.*/gfx_vsync:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_vsync:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_vsync = 1" || no "gfx_vsync = 1"
"$ADB" shell "grep -q '^gfx_multithreaded_renderer:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_multithreaded_renderer:.*/gfx_multithreaded_renderer:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_multithreaded_renderer = 1" || no "gfx_multithreaded_renderer = 1"
"$ADB" shell "grep -q '^gfx_field_of_view:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_field_of_view:.*/gfx_field_of_view:66/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_field_of_view = 66" || no "gfx_field_of_view = 66"
"$ADB" shell "grep -q '^gfx_max_framerate_advanced:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >/dev/null 2>&1 && ok "gfx_max_framerate_advanced = 0" || no "gfx_max_framerate_advanced = 0"
echo "== Kompilasi AOT penuh (ART speed) untuk Minecraft"
"$ADB" shell "cmd package compile -m speed -f com.mojang.minecraftpe" >/dev/null 2>&1 && ok "ART compile speed" || no "ART compile speed"
"$ADB" shell "cmd package compile -m speed-profile -f com.mojang.minecraftpe" >/dev/null 2>&1 && ok "profile compile" || no "profile compile"
echo "== Bebaskan Minecraft dari Doze + pembatasan background"
"$ADB" shell "dumpsys deviceidle whitelist +com.mojang.minecraftpe" >/dev/null 2>&1 && ok "doze whitelist" || no "doze whitelist"
"$ADB" shell "cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND allow" >/dev/null 2>&1 && ok "background allow" || no "background allow"
"$ADB" shell "cmd appops set com.mojang.minecraftpe WAKE_LOCK allow" >/dev/null 2>&1 && ok "wake lock allow" || no "wake lock allow"
echo "== Bersihkan memori background sebelum sesi"
"$ADB" shell "am kill-all" >/dev/null 2>&1 && ok "kill cached processes" || no "kill cached processes"
"$ADB" shell "cmd package bg-dexopt-job 2>/dev/null || true" >/dev/null 2>&1 && ok "dexopt job" || no "dexopt job"
echo "== Restart Minecraft agar konfigurasi terbaca"
"$ADB" shell "am force-stop com.mojang.minecraftpe" >/dev/null 2>&1 && ok "tutup Minecraft" || no "tutup Minecraft"
"$ADB" shell "monkey -p com.mojang.minecraftpe -c android.intent.category.LAUNCHER 1" >/dev/null 2>&1 && ok "buka Minecraft" || no "buka Minecraft"

echo
echo "Verifikasi:"
"$ADB" shell "dumpsys display | grep -E \"mActiveRenderFrameRate|peakRefreshRate\""
"$ADB" shell "cmd game list-modes $PKG" 2>/dev/null
"$ADB" shell "grep -E \"gfx_viewdistance|gfx_max_framerate|gfx_vsync\" /sdcard/Android/data/$PKG/files/games/com.mojang/minecraftpe/options.txt" 2>/dev/null
echo
echo "Selesai. Restart Minecraft: $ADB shell am force-stop $PKG; $ADB shell monkey -p $PKG -c android.intent.category.LAUNCHER 1"
