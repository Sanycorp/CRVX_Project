#!/usr/bin/env bash
# CRVX TURBOFRAME - UNDO untuk plan 6c18c98927ce
set -u
ADB="${ADB:-adb}"
SERIAL=""
if [ -n "$SERIAL" ]; then T=(-s "$SERIAL"); else T=(); fi
undo() { echo "  <- $1"; "$ADB" "${T[@]}" shell "$1" >/dev/null 2>&1 || true; }
undoroot() { undo "su -c '$1'"; }

undo 'settings delete global low_power'
undo 'settings delete global battery_saver_enabled'
undo 'settings put global adaptive_battery_enabled 1'
undo 'settings put global window_animation_scale 1'
undo 'settings put global transition_animation_scale 1'
undo 'settings put global animator_duration_scale 1'
undo 'settings delete system peak_refresh_rate'
undo 'settings delete system min_refresh_rate'
undo 'settings delete system user_refresh_rate'
undo 'settings delete secure min_refresh_rate'
undo 'settings delete secure peak_refresh_rate'
undo 'settings delete global user_refresh_rate'
undo 'settings put global disable_window_blurs 0'
undo 'settings put system screen_brightness_mode 1'
undo 'cmd game mode standard com.mojang.minecraftpe'
undo 'cmd game set --fps 0 com.mojang.minecraftpe'
undo 'device_config delete game_overlay com.mojang.minecraftpe'
undo 'settings delete global game_mode_overlay_com.mojang.minecraftpe'
undo 'echo '"'"'gfx_viewdistance:112'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_particleviewdistance:0.40'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_smoothlighting:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_transparentleaves:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_fancyskies:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_msaa:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_max_framerate:60'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_vsync:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_multithreaded_renderer:1'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_field_of_view:66'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'echo '"'"'gfx_max_framerate_advanced:0'"'"' >> /sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt'
undo 'cmd package compile --reset -f com.mojang.minecraftpe'
undo 'dumpsys deviceidle whitelist -com.mojang.minecraftpe'
undo 'cmd appops set com.mojang.minecraftpe RUN_ANY_IN_BACKGROUND default'
undo 'cmd appops set com.mojang.minecraftpe WAKE_LOCK default'

echo "Semua perubahan dikembalikan ke kondisi awal."
