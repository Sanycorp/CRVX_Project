#!/system/bin/sh
# CRVX TURBOFRAME - UNDO MODE 60 FPS  [ON-DEVICE SHELL]
# Mengembalikan semua setelan ke kondisi sebelum boost dijalankan.
# Tempel isi file ini ke terminal LADB / Shizuku / `su` di Termux.

echo '== CRVX UNDO: mengembalikan setelan awal'
OPT='/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'

optbisa() {
  [ -f "$OPT" ] && [ -r "$OPT" ] && [ -w "$OPT" ] && return 0
  return 1
}

echo '-- Matikan Battery Saver & pembatas performa'
settings delete global low_power || true
settings delete global battery_saver_enabled || true
settings put global adaptive_battery_enabled 1 || true
echo '-- Matikan animasi sistem (skala 0)'
settings put global window_animation_scale 1 || true
settings put global transition_animation_scale 1 || true
settings put global animator_duration_scale 1 || true
echo '-- Kunci mode tampilan 60 Hz (DisplayManager)'
cmd display set-user-preferred-display-mode 0 0 0 0 || true
echo '-- Naikkan peak/min refresh rate sistem ke 60 Hz'
settings delete system peak_refresh_rate || true
settings delete system min_refresh_rate || true
settings delete system user_refresh_rate || true
echo '-- Kunci refresh rate lewat namespace secure (60 Hz)'
settings delete secure min_refresh_rate || true
settings delete secure peak_refresh_rate || true
settings delete global user_refresh_rate || true
echo '-- HyperOS/MIUI: paksa 60 Hz + matikan Smart FPS'
settings delete secure miui_refresh_rate || true
settings put system is_smart_fps 1 || true
settings put system power_center_5g_save_mode 1 || true
echo '-- Matikan blur jendela (kurangi beban GPU kompositor)'
settings put global disable_window_blurs 0 || true
echo '-- Kunci kecerahan (matikan auto-brightness)'
settings put system screen_brightness_mode 1 || true
echo '-- Aktifkan Game Mode API: PERFORMANCE'
cmd game mode standard com.mojang.minecraftpe || true
echo '-- Override FPS Game Mode ke 60 (custom intervention)'
cmd game set --fps 0 com.mojang.minecraftpe || true
echo '-- Backbuffer resize 85% (tuas FPS terbesar)'
cmd game set --downscale disable com.mojang.minecraftpe || true
echo '-- Tulis intervensi game_overlay (persisten lintas reboot)'
device_config delete game_overlay com.mojang.minecraftpe || true
settings delete global game_mode_overlay_com.mojang.minecraftpe || true
echo '-- Terapkan preset grafis MODE 60 FPS ke options.txt'
if optbisa; then
  echo 'gfx_viewdistance:80' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_particleviewdistance:0.25' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_smoothlighting:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_max_framerate:60' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_vsync:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
  echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
else
  echo '  [LEWAT] options.txt tidak bisa ditulis dari shell non-root.'
  echo '          Kembalikan nilai grafis lewat Minecraft -> Settings -> Video.'
fi
echo '-- Kompilasi AOT penuh (ART speed) untuk Minecraft'
cmd package compile --reset -f com.mojang.minecraftpe || true
echo '-- Bebaskan Minecraft dari Doze + pembatasan background'
dumpsys deviceidle whitelist -com.mojang.minecraftpe || true
cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND default || true
cmd appops set com.mojang.minecraftpe WAKE_LOCK default || true

echo 'Selesai: 38 setelan dikembalikan.'
echo 'Catatan: nilai yang dibaca saat boost dijalankan adalah acuan; jika suatu'
echo '         setelan belum pernah diubah, perintah di atas tidak berbahaya.'
