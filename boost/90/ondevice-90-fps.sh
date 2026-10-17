#!/system/bin/sh
# CRVX TURBOFRAME - MODE 90 FPS  [ON-DEVICE SHELL]
# Jalankan lewat Shizuku (adb permission), LADB, atau `su` di Termux.

echo '== Backup options.txt sebelum disentuh'
cp /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt /data/local/tmp/crvx_options_backup.txt 2>/dev/null || true || true
echo '== Matikan Battery Saver & pembatas performa'
settings put global low_power 0 || true
settings put global battery_saver_enabled 0 || true
settings put global adaptive_battery_enabled 0 || true
echo '== Matikan animasi sistem (skala 0)'
settings put global window_animation_scale 0 || true
settings put global transition_animation_scale 0 || true
settings put global animator_duration_scale 0 || true
echo '== Naikkan peak/min refresh rate sistem ke 90 Hz'
settings put system peak_refresh_rate 90.0 || true
settings put system min_refresh_rate 90.0 || true
settings put system user_refresh_rate 90.0 || true
echo '== Kunci refresh rate lewat namespace secure (90 Hz)'
settings put secure min_refresh_rate 90.0 || true
settings put secure peak_refresh_rate 90.0 || true
settings put global user_refresh_rate 90.0 || true
echo '== Matikan blur jendela (kurangi beban GPU kompositor)'
settings put global disable_window_blurs 1 || true
echo '== Kunci kecerahan (matikan auto-brightness)'
settings put system screen_brightness_mode 0 || true
echo '== Aktifkan Game Mode API: PERFORMANCE'
cmd game mode performance com.mojang.minecraftpe || true
echo '== Override FPS Game Mode ke 90 (custom intervention)'
cmd game set --fps 90 com.mojang.minecraftpe || true
echo '== Backbuffer resize 90% (tuas FPS terbesar)'
cmd game set --downscale 0.9 com.mojang.minecraftpe || true
echo '== Tulis intervensi game_overlay (persisten lintas reboot)'
device_config put game_overlay com.mojang.minecraftpe mode=2,fps=90,downscaleFactor=0.90 || true
settings put global game_mode_overlay_com.mojang.minecraftpe 1 || true
echo '== Terapkan preset grafis MODE 90 FPS ke options.txt'
grep -q '^gfx_viewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:96/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_viewdistance:96' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_particleviewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:0.35/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_particleviewdistance:0.35' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_smoothlighting:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_smoothlighting:.*/gfx_smoothlighting:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_smoothlighting:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_transparentleaves:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_transparentleaves:.*/gfx_transparentleaves:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_fancyskies:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_fancyskies:.*/gfx_fancyskies:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_msaa:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_msaa:.*/gfx_msaa:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_max_framerate:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:90/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate:90' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_vsync:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_vsync:.*/gfx_vsync:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_vsync:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_multithreaded_renderer:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_multithreaded_renderer:.*/gfx_multithreaded_renderer:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_field_of_view:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_field_of_view:.*/gfx_field_of_view:66/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
grep -q '^gfx_max_framerate_advanced:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
echo '== Lepas kunci V-Sync + set cap framerate engine'
sed -i 's/^gfx_vsync:.*/gfx_vsync:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:90/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || true
echo '== Kompilasi AOT penuh (ART speed) untuk Minecraft'
cmd package compile -m speed -f com.mojang.minecraftpe || true
cmd package compile -m speed-profile -f com.mojang.minecraftpe || true
echo '== Bebaskan Minecraft dari Doze + pembatasan background'
dumpsys deviceidle whitelist +com.mojang.minecraftpe || true
cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND allow || true
cmd appops set com.mojang.minecraftpe WAKE_LOCK allow || true
echo '== Bersihkan memori background sebelum sesi'
am kill-all || true
cmd package bg-dexopt-job 2>/dev/null || true || true
echo '== Mode fokus: DND + layar tetap menyala saat sesi'
cmd notification set_dnd on || true
settings put global stay_on_while_plugged_in 3 || true
echo '== Thermal service: status 1'
cmd thermalservice override-status 1 || true
settings put global thermal_status_override 1 || true
echo '== Restart Minecraft agar konfigurasi terbaca'
am force-stop com.mojang.minecraftpe || true
monkey -p com.mojang.minecraftpe -c android.intent.category.LAUNCHER 1 || true
echo 'Selesai.'
