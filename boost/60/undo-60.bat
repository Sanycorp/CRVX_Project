@echo off
chcp 65001 >nul
REM CRVX TURBOFRAME - UNDO plan 7d1b58670fa7
if "%ADB%"=="" set "ADB=adb"
set "SERIAL="
if not "%SERIAL%"=="" (set "T=-s %SERIAL%") else (set "T=")
%ADB% %T% shell "cmd appops set com.mojang.minecraftpe WAKE_LOCK default" >nul 2>&1
echo   ^<- runtime.doze_whitelist
%ADB% %T% shell "cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND default" >nul 2>&1
echo   ^<- runtime.doze_whitelist
%ADB% %T% shell "dumpsys deviceidle whitelist -com.mojang.minecraftpe" >nul 2>&1
echo   ^<- runtime.doze_whitelist
%ADB% %T% shell "cmd package compile --reset -f com.mojang.minecraftpe" >nul 2>&1
echo   ^<- runtime.art_compile
%ADB% %T% shell "echo 'gfx_max_framerate_advanced:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_field_of_view:66' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_multithreaded_renderer:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_vsync:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_max_framerate:60' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_msaa:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_fancyskies:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_transparentleaves:0' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_smoothlighting:1' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_particleviewdistance:0.40' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "echo 'gfx_viewdistance:112' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt" >nul 2>&1
echo   ^<- minecraft.options
%ADB% %T% shell "settings delete global game_mode_overlay_com.mojang.minecraftpe" >nul 2>&1
echo   ^<- gamemode.overlay_config
%ADB% %T% shell "device_config delete game_overlay com.mojang.minecraftpe" >nul 2>&1
echo   ^<- gamemode.overlay_config
%ADB% %T% shell "cmd game set --fps 0 com.mojang.minecraftpe" >nul 2>&1
echo   ^<- gamemode.custom_fps
%ADB% %T% shell "cmd game mode standard com.mojang.minecraftpe" >nul 2>&1
echo   ^<- gamemode.performance
%ADB% %T% shell "settings put system screen_brightness_mode 1" >nul 2>&1
echo   ^<- display.brightness_fixed
%ADB% %T% shell "settings put global disable_window_blurs 0" >nul 2>&1
echo   ^<- display.blurs_off
%ADB% %T% shell "settings delete global user_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.secure
%ADB% %T% shell "settings delete secure peak_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.secure
%ADB% %T% shell "settings delete secure min_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.secure
%ADB% %T% shell "settings delete system user_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.system
%ADB% %T% shell "settings delete system min_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.system
%ADB% %T% shell "settings delete system peak_refresh_rate" >nul 2>&1
echo   ^<- display.refresh.system
%ADB% %T% shell "settings put global animator_duration_scale 1" >nul 2>&1
echo   ^<- system.animations
%ADB% %T% shell "settings put global transition_animation_scale 1" >nul 2>&1
echo   ^<- system.animations
%ADB% %T% shell "settings put global window_animation_scale 1" >nul 2>&1
echo   ^<- system.animations
%ADB% %T% shell "settings put global adaptive_battery_enabled 1" >nul 2>&1
echo   ^<- system.power_saver_off
%ADB% %T% shell "settings delete global battery_saver_enabled" >nul 2>&1
echo   ^<- system.power_saver_off
%ADB% %T% shell "settings delete global low_power" >nul 2>&1
echo   ^<- system.power_saver_off
echo.
echo  Semua perubahan dikembalikan.
pause
