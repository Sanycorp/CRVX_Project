@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM CRVX TURBOFRAME - MODE 60 FPS  (plan 6c18c98927ce)
REM Perangkat:  Generic Android | Android 14
set "ADB=%ADB%"
if "%ADB%"=="" set "ADB=adb"
set "SERIAL="
if not "%SERIAL%"=="" (set "T=-s %SERIAL%") else (set "T=")
echo.
echo  CRVX TURBOFRAME :: MODE 60 FPS
echo  =========================================
echo.
echo  [PREFLIGHT]
%ADB% get-state >nul 2>&1
if errorlevel 1 (
  echo   [XX] Perangkat belum tersambung. Aktifkan USB/Wireless Debugging.
  %ADB% devices
  pause
  exit /b 1
)
for /f "delims=" %%a in ('%ADB% %T% shell getprop ro.product.model') do set "MODEL=%%a"
for /f "delims=" %%a in ('%ADB% %T% shell dumpsys package com.mojang.minecraftpe ^| findstr versionName') do set "MCVER=%%a"
  echo   perangkat : %MODEL%
  echo   minecraft : %MCVER%
  echo   target Hz : 60
echo.
echo  [EKSEKUSI]
echo [minecraft] Backup options.txt sebelum disentuh
%ADB% %T% shell "cp /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt /data/local/tmp/crvx_options_backup.txt 2>/dev/null || true" >nul 2>&1
echo [system] Matikan Battery Saver ^& pembatas performa
%ADB% %T% shell "settings put global low_power 0" >nul 2>&1
%ADB% %T% shell "settings put global battery_saver_enabled 0" >nul 2>&1
%ADB% %T% shell "settings put global adaptive_battery_enabled 0" >nul 2>&1
echo [system] Matikan animasi sistem (skala 0)
%ADB% %T% shell "settings put global window_animation_scale 0" >nul 2>&1
%ADB% %T% shell "settings put global transition_animation_scale 0" >nul 2>&1
%ADB% %T% shell "settings put global animator_duration_scale 0" >nul 2>&1
echo [display] Naikkan peak/min refresh rate sistem ke 60 Hz
%ADB% %T% shell "settings put system peak_refresh_rate 60.0" >nul 2>&1
%ADB% %T% shell "settings put system min_refresh_rate 60.0" >nul 2>&1
%ADB% %T% shell "settings put system user_refresh_rate 60.0" >nul 2>&1
echo [display] Kunci refresh rate lewat namespace secure (60 Hz)
%ADB% %T% shell "settings put secure min_refresh_rate 60.0" >nul 2>&1
%ADB% %T% shell "settings put secure peak_refresh_rate 60.0" >nul 2>&1
%ADB% %T% shell "settings put global user_refresh_rate 60.0" >nul 2>&1
echo [display] Matikan blur jendela (kurangi beban GPU kompositor)
%ADB% %T% shell "settings put global disable_window_blurs 1" >nul 2>&1
echo [display] Kunci kecerahan (matikan auto-brightness)
%ADB% %T% shell "settings put system screen_brightness_mode 0" >nul 2>&1
echo [gamemode] Aktifkan Game Mode API: PERFORMANCE
%ADB% %T% shell "cmd game mode performance com.mojang.minecraftpe" >nul 2>&1
echo [gamemode] Override FPS Game Mode ke 60 (custom intervention)
%ADB% %T% shell "cmd game set --fps 60 com.mojang.minecraftpe" >nul 2>&1
echo [gamemode] Tulis intervensi game_overlay (persisten lintas reboot)
%ADB% %T% shell "device_config put game_overlay com.mojang.minecraftpe mode=2,fps=60,downscaleFactor=1.00" >nul 2>&1
%ADB% %T% shell "settings put global game_mode_overlay_com.mojang.minecraftpe 1" >nul 2>&1
echo [minecraft] Terapkan preset grafis MODE 60 FPS ke options.txt
%ADB% %T% shell "grep -q '^gfx_viewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:112/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_viewdistance:112' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_particleviewdistance:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:0.40/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_particleviewdistance:0.40' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_smoothlighting:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_smoothlighting:.*/gfx_smoothlighting:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_smoothlighting:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_transparentleaves:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_transparentleaves:.*/gfx_transparentleaves:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_fancyskies:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_fancyskies:.*/gfx_fancyskies:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_msaa:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_msaa:.*/gfx_msaa:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_max_framerate:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:60/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate:60' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_vsync:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_vsync:.*/gfx_vsync:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_vsync:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_multithreaded_renderer:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_multithreaded_renderer:.*/gfx_multithreaded_renderer:1/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_field_of_view:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_field_of_view:.*/gfx_field_of_view:66/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
%ADB% %T% shell "grep -q '^gfx_max_framerate_advanced:' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt && sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt || echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo [runtime] Kompilasi AOT penuh (ART speed) untuk Minecraft
%ADB% %T% shell "cmd package compile -m speed -f com.mojang.minecraftpe" >nul 2>&1
%ADB% %T% shell "cmd package compile -m speed-profile -f com.mojang.minecraftpe" >nul 2>&1
echo [runtime] Bebaskan Minecraft dari Doze + pembatasan background
%ADB% %T% shell "dumpsys deviceidle whitelist +com.mojang.minecraftpe" >nul 2>&1
%ADB% %T% shell "cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND allow" >nul 2>&1
%ADB% %T% shell "cmd appops set com.mojang.minecraftpe WAKE_LOCK allow" >nul 2>&1
echo [memory] Bersihkan memori background sebelum sesi
%ADB% %T% shell "am kill-all" >nul 2>&1
%ADB% %T% shell "cmd package bg-dexopt-job 2>/dev/null || true" >nul 2>&1
echo [minecraft] Restart Minecraft agar konfigurasi terbaca
%ADB% %T% shell "am force-stop com.mojang.minecraftpe" >nul 2>&1
%ADB% %T% shell "monkey -p com.mojang.minecraftpe -c android.intent.category.LAUNCHER 1" >nul 2>&1
echo.
echo  Selesai. Buka Minecraft lalu masuk ke dunia untuk merasakan hasilnya.
echo  Untuk membatalkan semua perubahan jalankan crvx-undo.bat
endlocal
pause
