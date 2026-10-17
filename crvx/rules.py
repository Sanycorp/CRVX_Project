"""Katalog aturan optimasi.

Setiap aturan dibangun dinamis dari (perangkat, mode) sehingga perintahnya
spesifik: nilai refresh rate, ukuran layar, target FPS, dan path options.txt
diisi dari hasil deteksi nyata - bukan template generik.

Semua perintah punya jalur UNDO. Yang tidak bisa dibalik secara eksplisit
dibuat idempoten dan tidak merusak (mis. `settings delete` mengembalikan
ke default pabrik).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .models import (Category, Command, Device, Gain, Requirements, Risk, Rule,
                     Vendor, Verify)
from .modes import FpsMode, QualityBudget

PKG = "{pkg}"
TMP = "/data/local/tmp"


def _refresh_candidates(dev: Device, target: float) -> List[float]:
    """Pilih refresh rate yang benar-benar didukung panel."""
    rates = dev.refresh_rates or [60.0]
    if any(abs(r - target) < 0.6 for r in rates):
        return [target]
    lower = [r for r in rates if r <= target]
    return [max(lower) if lower else min(rates)]


def _hz(value: float) -> str:
    return f"{value:.1f}"


# --------------------------------------------------------------------------- #
# DISPLAY
# --------------------------------------------------------------------------- #
def display_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    rules: List[Rule] = []
    targets = _refresh_candidates(dev, mode.refresh_target)
    fps = targets[0]
    native = dev.native_mode_for(fps) or (dev.display_modes[-1] if dev.display_modes else None)
    width = native.width if native else 0
    height = native.height if native else 0
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"

    if width and height and dev.android_sdk >= 33:
        rules.append(Rule(
            id="display.preferred_mode",
            title=f"Kunci mode tampilan {fps:g} Hz (DisplayManager)",
            category=Category.DISPLAY, risk=Risk.SAFE,
            description=("Memakai API resmi Android `cmd display` untuk memilih mode panel "
                         f"{width}x{height}@{fps:g}. Ini jalur paling bersih dan paling sering "
                         "berhasil karena tidak menebak kunci settings vendor."),
            requirements=Requirements(min_sdk=33, display_fps=fps),
            commands=[
                Command(shell=f"cmd display set-user-preferred-display-mode {width} {height} {fps:g} 0",
                        undo="cmd display set-user-preferred-display-mode 0 0 0 0",
                        label=f"display mode {width}x{height}@{fps:g}"),
            ],
            gain=Gain(fps=fps - dev.active_fps, stability=4, input_latency_ms=-1.5, confidence=0.85),
            verify=Verify(command="dumpsys display", expect=_hz(fps), mode="contains"),
            tags=["refresh", "aosp"],
        ))

    rules.append(Rule(
        id="display.refresh.system",
        title=f"Naikkan peak/min refresh rate sistem ke {fps:g} Hz",
        category=Category.DISPLAY, risk=Risk.SAFE,
        description=("`peak_refresh_rate` + `min_refresh_rate` di namespace system dipakai "
                     "Pixel, Xiaomi, Samsung, dan banyak ROM lain. Kalau kunci tidak dikenal, "
                     "perintah diabaikan tanpa efek samping."),
        requirements=Requirements(display_fps=fps),
        commands=[
            Command(shell=f"settings put system peak_refresh_rate {_hz(fps)}",
                    undo="settings delete system peak_refresh_rate", label="peak_refresh_rate"),
            Command(shell=f"settings put system min_refresh_rate {_hz(fps)}",
                    undo="settings delete system min_refresh_rate", label="min_refresh_rate"),
            Command(shell=f"settings put system user_refresh_rate {_hz(fps)}",
                    undo="settings delete system user_refresh_rate", label="user_refresh_rate"),
        ],
        gain=Gain(fps=fps - dev.active_fps, stability=3, battery=-6, confidence=0.7),
        verify=Verify(command="settings get system peak_refresh_rate", expect="", mode="nonempty"),
        tags=["refresh"],
    ))

    rules.append(Rule(
        id="display.refresh.secure",
        title=f"Kunci refresh rate lewat namespace secure ({fps:g} Hz)",
        category=Category.DISPLAY, risk=Risk.SAFE,
        description=("Beberapa ROM (OnePlus/Oppo lama, sebagian Android 14+) membaca kunci "
                     "refresh rate dari namespace secure, bukan system."),
        requirements=Requirements(display_fps=fps),
        commands=[
            Command(shell=f"settings put secure min_refresh_rate {_hz(fps)}",
                    undo="settings delete secure min_refresh_rate", label="secure.min_refresh_rate"),
            Command(shell=f"settings put secure peak_refresh_rate {_hz(fps)}",
                    undo="settings delete secure peak_refresh_rate", label="secure.peak_refresh_rate"),
            Command(shell=f"settings put global user_refresh_rate {_hz(fps)}",
                    undo="settings delete global user_refresh_rate", label="global.user_refresh_rate"),
        ],
        gain=Gain(fps=0, stability=2, confidence=0.45),
        verify=Verify(command="settings get secure min_refresh_rate", expect="", mode="nonempty"),
            tags=["refresh", "fallback"],
    ))

    if dev.vendor in (Vendor.XIAOMI, Vendor.POCO, Vendor.REDMI):
        rules.append(Rule(
            id="display.refresh.miui",
            title=f"HyperOS/MIUI: paksa {fps:g} Hz + matikan Smart FPS",
            category=Category.DISPLAY, risk=Risk.MODERATE,
            description=("MIUI/HyperOS punya policy `PRIORITY_MIUI_REFRESH_RATE` yang bisa "
                         "membatasi game ke 60 Hz. Kunci `miui_refresh_rate` dan "
                         "`is_smart_fps=0` membuka batas itu."),
            requirements=Requirements(display_fps=fps),
            commands=[
                Command(shell=f"settings put secure miui_refresh_rate {int(fps)}",
                        undo="settings delete secure miui_refresh_rate", label="miui_refresh_rate"),
                Command(shell="settings put system is_smart_fps 0",
                        undo="settings put system is_smart_fps 1", label="is_smart_fps=0"),
                Command(shell="settings put system power_center_5g_save_mode 0",
                        undo="settings put system power_center_5g_save_mode 1",
                        label="matikan 5G power save", optional=True),
            ],
            gain=Gain(fps=6, stability=5, battery=-8, confidence=0.7),
            verify=Verify(command="dumpsys display", expect="PRIORITY_MIUI_REFRESH_RATE"),
            tags=["refresh", "vendor"],
        ))

    if dev.vendor == Vendor.SAMSUNG:
        rules.append(Rule(
            id="display.refresh.oneui",
            title="One UI: refresh_rate_mode = High + matikan motion smoothness adaptif",
            category=Category.DISPLAY, risk=Risk.MODERATE,
            description=("One UI menyimpan mode refresh di `secure refresh_rate_mode` "
                         "(2 = High). Tanpa ini, Game Launcher tetap menahan 60 Hz."),
            requirements=Requirements(display_fps=fps),
            commands=[
                Command(shell="settings put secure refresh_rate_mode 2",
                        undo="settings delete secure refresh_rate_mode", label="refresh_rate_mode=2"),
                Command(shell=f"settings put system peak_refresh_rate {_hz(fps)}",
                        undo="settings delete system peak_refresh_rate", label="peak_refresh_rate"),
                Command(shell=f"settings put system min_refresh_rate {_hz(fps)}",
                        undo="settings delete system min_refresh_rate", label="min_refresh_rate"),
            ],
            gain=Gain(fps=8, stability=5, battery=-10, confidence=0.75),
            tags=["refresh", "vendor"],
        ))
        rules.append(Rule(
            id="samsung.game_launcher",
            title="Buka Game Launcher: izinkan FPS tinggi untuk Minecraft",
            category=Category.DISPLAY, risk=Risk.SAFE,
            description=("Samsung menahan Minecraft di 60 FPS lewat Game Plugins/Game Launcher. "
                         "Perintah ini membuka panel yang benar supaya Anda tinggal menekan "
                         "'Frame rate 120 FPS' sekali."),
            requirements=Requirements(display_fps=120),
            commands=[
                Command(shell="monkey -p com.samsung.android.game.gls -c "
                              "android.intent.category.LAUNCHER 1",
                        label="buka Game Launcher", optional=True),
            ],
            gain=Gain(fps=0, confidence=0.5),
            tags=["vendor", "manual"],
        ))

    if dev.vendor in (Vendor.ONEPLUS, Vendor.OPPO, Vendor.REALME, Vendor.NOTHING):
        rules.append(Rule(
            id="display.refresh.oplus",
            title=f"OxygenOS/ColorOS: oplus_customize_screen_refresh_rate = {int(fps)}",
            category=Category.DISPLAY, risk=Risk.MODERATE,
            description=("Oppo/OnePlus/Realme memakai kunci `oplus_*` tersendiri. Nilai 3 "
                         "memaksa refresh tertinggi; perlu 'Disable permission monitoring' "
                         "di Developer options pada sebagian build."),
            requirements=Requirements(display_fps=fps),
            commands=[
                Command(shell="settings put secure oplus_customize_screen_refresh_rate 3",
                        undo="settings put secure oplus_customize_screen_refresh_rate 0",
                        label="oplus refresh = high"),
                Command(shell="settings put secure oplus_customize_peak_refresh_rate 1",
                        undo="settings delete secure oplus_customize_peak_refresh_rate",
                        label="oplus peak", optional=True),
                Command(shell="settings put secure oplus_customize_min_refresh_rate 1",
                        undo="settings delete secure oplus_customize_min_refresh_rate",
                        label="oplus min", optional=True),
            ],
            gain=Gain(fps=6, stability=4, battery=-8, confidence=0.65),
            tags=["refresh", "vendor"],
        ))

    rules.append(Rule(
        id="display.blurs_off",
        title="Matikan blur jendela (kurangi beban GPU kompositor)",
        category=Category.DISPLAY, risk=Risk.SAFE,
        description=("`disable_window_blurs=1` mematikan blur real-time di notification shade "
                     "dan dialog. Mengurangi kerja SurfaceFlinger saat game berjalan."),
        requirements=Requirements(min_sdk=31),
        commands=[
            Command(shell="settings put global disable_window_blurs 1",
                    undo="settings put global disable_window_blurs 0", label="blur off"),
        ],
        gain=Gain(gpu_load=2, stability=1, confidence=0.5),
        tags=["gpu"],
    ))

    rules.append(Rule(
        id="display.brightness_fixed",
        title="Kunci kecerahan (matikan auto-brightness)",
        category=Category.DISPLAY, risk=Risk.SAFE,
        description=("Sensor cahaya yang terus menyesuaikan kecerahan memicu refresh-rate "
                     "switching dan micro-stutter. Kecerahan tetap = frame pacing lebih rata."),
        commands=[
            Command(shell="settings put system screen_brightness_mode 0",
                    undo="settings put system screen_brightness_mode 1", label="auto-brightness off"),
        ],
        gain=Gain(stability=2, frametime_ms=-0.4, confidence=0.55),
        tags=["stability"],
    ))

    return rules


# --------------------------------------------------------------------------- #
# GAME MODE API
# --------------------------------------------------------------------------- #
def gamemode_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    rules: List[Rule] = []
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"
    target = mode.effective_target(dev)
    fps_choices = [30, 45, 60, 90, 120]
    nearest = min(fps_choices, key=lambda x: abs(x - target)) if target < 144 else 120

    rules.append(Rule(
        id="gamemode.performance",
        title="Aktifkan Game Mode API: PERFORMANCE",
        category=Category.GAMEMODE, risk=Risk.SAFE,
        description=("Android 12L+ punya Game Mode resmi. Mode PERFORMANCE meminta Power HAL "
                     "memberi latensi terendah dan mencegah OEM menurunkan performa game."),
        requirements=Requirements(game_mode=True),
        commands=[
            Command(shell=f"cmd game mode performance {pkg}",
                    undo=f"cmd game mode standard {pkg}", label="game mode = performance"),
        ],
        gain=Gain(fps=4, stability=6, input_latency_ms=-2, confidence=0.75),
        verify=Verify(command=f"cmd game list-modes {pkg}", expect="performance"),
        tags=["gamemode", "aosp"],
    ))

    if dev.android_sdk >= 33:
        rules.append(Rule(
            id="gamemode.custom_fps",
            title=f"Override FPS Game Mode ke {nearest} (custom intervention)",
            category=Category.GAMEMODE, risk=Risk.MODERATE,
            description=("`cmd game set --fps` memberi tahu framework target frame rate game. "
                         "Pada perangkat yang mendukung, ini yang membuat Bedrock benar-benar "
                         f"jalan di {nearest} FPS alih-alih jatuh ke 60."),
            requirements=Requirements(game_mode=True, min_sdk=33, display_fps=float(nearest)),
            commands=[
                Command(shell=f"cmd game set --fps {nearest} {pkg}",
                        undo=f"cmd game set --fps 0 {pkg}", label=f"fps override = {nearest}"),
            ],
            gain=Gain(fps=nearest - 60 if nearest > 60 else 2, stability=5, confidence=0.6),
            verify=Verify(command=f"cmd game list-configs {pkg}", expect=str(nearest)),
            tags=["gamemode", "fps"],
        ))

    if budget.downscale < 1.0 and dev.android_sdk >= 33:
        allowed = [0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.3]
        ratio = min(allowed, key=lambda x: abs(x - budget.downscale))
        rules.append(Rule(
            id="gamemode.downscale",
            title=f"Backbuffer resize {int(ratio * 100)}% (tuas FPS terbesar)",
            category=Category.GAMEMODE, risk=Risk.MODERATE,
            description=("WindowManager merender game pada {p}% resolusi lalu meng-upscale. "
                         "Dokumentasi Android: memangkas sampai 30% beban GPU. Ditukar dengan "
                         "ketajaman gambar sedikit berkurang.".format(p=int(ratio * 100))),
            requirements=Requirements(game_mode=True, min_sdk=33),
            commands=[
                Command(shell=f"cmd game set --downscale {ratio} {pkg}",
                        undo=f"cmd game set --downscale disable {pkg}",
                        label=f"render scale {int(ratio * 100)}%"),
            ],
            gain=Gain(fps=14 * (1 - ratio) * 2.4, gpu_load=-30 * (1 - ratio),
                      frametime_ms=-2.2, stability=8, battery=-4, confidence=0.8),
            verify=Verify(command=f"cmd game list-configs {pkg}", expect="Scaling:"),
            tags=["gamemode", "gpu", "visual"],
        ))

    rules.append(Rule(
        id="gamemode.overlay_config",
        title="Tulis intervensi game_overlay (persisten lintas reboot)",
        category=Category.GAMEMODE, risk=Risk.ADVANCED,
        description=("`device_config put game_overlay` menyimpan konfigurasi FPS + downscale "
                     "per mode game, jadi tetap berlaku setelah restart. Nilai FPS yang tidak "
                     "didukung panel bisa membuat SurfaceFlinger restart - karena itu hanya "
                     "diisi dengan angka yang panel Anda dukung."),
        requirements=Requirements(game_mode=True, min_sdk=33),
        commands=[
            Command(shell=f"device_config put game_overlay {pkg} "
                          f"mode=2,fps={nearest},downscaleFactor={budget.downscale:.2f}",
                    undo=f"device_config delete game_overlay {pkg}",
                    label="game_overlay config"),
            Command(shell=f"settings put global game_mode_overlay_{pkg} 1",
                    undo=f"settings delete global game_mode_overlay_{pkg}",
                    label="penanda overlay", optional=True),
        ],
        gain=Gain(stability=6, fps=2, confidence=0.5),
        verify=Verify(command=f"device_config get game_overlay {pkg}", expect="fps="),
        tags=["gamemode", "persistent", "experimental"],
    ))

    return rules


# --------------------------------------------------------------------------- #
# MINECRAFT
# --------------------------------------------------------------------------- #
def minecraft_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    rules: List[Rule] = []
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"
    options_path = dev.minecraft.options_path
    if not options_path:
        options_path = (f"/sdcard/Android/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt")
    current = dev.minecraft.current_options or {}

    rules.append(Rule(
        id="minecraft.backup",
        title="Backup options.txt sebelum disentuh",
        category=Category.MINECRAFT, risk=Risk.SAFE,
        description=("Menyalin options.txt asli ke folder kerja CRVX. Undo selalu bisa "
                     "mengembalikan kondisi awal apa pun yang terjadi."),
        requirements=Requirements(minecraft=True),
        commands=[
            Command(shell=f"cp {options_path} {TMP}/crvx_options_backup.txt 2>/dev/null || true",
                    undo="", label="backup options.txt"),
        ],
        gain=Gain(confidence=1.0),
        tags=["safety"],
    ))

    option_cmds: List[Command] = []
    for key, value in budget.options().items():
        old = current.get(key)
        undo = (f"sed -i 's/^{key}:.*/{key}:{old}/' {options_path}" if old is not None
                else f"echo '{key}:{value}' >> {options_path}")
        option_cmds.append(Command(
            shell=(f"grep -q '^{key}:' {options_path} && "
                   f"sed -i 's/^{key}:.*/{key}:{value}/' {options_path} || "
                   f"echo '{key}:{value}' >> {options_path}"),
            undo=undo, label=f"{key} = {value}"))

    rules.append(Rule(
        id="minecraft.options",
        title=f"Terapkan preset grafis {mode.name} ke options.txt",
        category=Category.MINECRAFT, risk=Risk.MODERATE,
        description=(f"Render distance {budget.chunks} chunk ({budget.viewdistance_blocks} blok), "
                     f"MSAA {budget.msaa}x, V-Sync {'ON' if budget.vsync else 'OFF'}, "
                     f"cap {budget.max_framerate or 'tak terbatas'} FPS, partikel "
                     f"{int(budget.particle_view * 100)}%, daun "
                     f"{'transparan' if budget.transparent_leaves else 'solid (fast)'}. "
                     "Semua kunci memakai nama modern Bedrock 26.x dan tetap terbaca "
                     "versi lama."),
        requirements=Requirements(minecraft=True, minecraft_writable=True),
        commands=option_cmds,
        gain=Gain(fps=18 + (6 - budget.chunks) * 2.2, gpu_load=-24, frametime_ms=-3.4,
                  stability=10, battery=-6, confidence=0.9),
        verify=Verify(command=f"cat {options_path}",
                      expect=f"gfx_max_framerate:{budget.max_framerate}"),
        tags=["minecraft", "options"],
    ))

    if mode.target_fps >= 90:
        rules.append(Rule(
            id="minecraft.vsync_unlock",
            title="Lepas kunci V-Sync + set cap framerate engine",
            category=Category.MINECRAFT, risk=Risk.MODERATE,
            description=("Bedrock menyimpan `gfx_vsync` dan `gfx_max_framerate` di options.txt. "
                         f"V-Sync OFF + cap {budget.max_framerate or 0} adalah satu-satunya cara "
                         "engine mau melewati 60 FPS di perangkat yang mendukung."),
            requirements=Requirements(minecraft=True, minecraft_writable=True),
            commands=[
                Command(shell=f"sed -i 's/^gfx_vsync:.*/gfx_vsync:0/' {options_path}",
                        undo=f"sed -i 's/^gfx_vsync:.*/gfx_vsync:{current.get('gfx_vsync', '1')}/' {options_path}",
                        label="gfx_vsync = 0"),
                Command(shell=f"sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:{budget.max_framerate}/' {options_path}",
                        undo=f"sed -i 's/^gfx_max_framerate:.*/gfx_max_framerate:{current.get('gfx_max_framerate', '60')}/' {options_path}",
                        label=f"gfx_max_framerate = {budget.max_framerate}"),
                Command(shell=f"sed -i 's/^gfx_max_framerate_advanced:.*/gfx_max_framerate_advanced:0/' {options_path} "
                              f"|| echo 'gfx_max_framerate_advanced:0' >> {options_path}",
                        undo="", label="gfx_max_framerate_advanced = 0", optional=True),
            ],
            gain=Gain(fps=10, stability=4, input_latency_ms=-4, confidence=0.8),
            verify=Verify(command=f"cat {options_path}", expect="gfx_vsync:0"),
            tags=["minecraft", "fps"],
        ))

    rules.append(Rule(
        id="minecraft.reload",
        title="Restart Minecraft agar konfigurasi terbaca",
        category=Category.MINECRAFT, risk=Risk.SAFE,
        description=("options.txt hanya dibaca saat game start. Aturan ini menutup lalu membuka "
                     "kembali Minecraft. Simpan dunia dulu sebelum menjalankan."),
        requirements=Requirements(minecraft=True),
        commands=[
            Command(shell=f"am force-stop {pkg}", undo="", label="tutup Minecraft"),
            Command(shell=f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1",
                    undo="", label="buka Minecraft"),
        ],
        gain=Gain(confidence=1.0),
        tags=["minecraft", "lifecycle"],
    ))

    return rules


# --------------------------------------------------------------------------- #
# RESOLUTION
# --------------------------------------------------------------------------- #
def resolution_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    scale = budget.resolution_scale
    if not scale or scale >= 1.0:
        return []
    if not dev.extras.get("screen"):
        return []
    try:
        width, height = (int(x) for x in dev.extras["screen"].split("x"))
    except ValueError:
        return []
    new_w, new_h = int(width * scale) // 2 * 2, int(height * scale) // 2 * 2
    if new_w < 720:
        return []
    density = int(dev.extras.get("density", 0) or 0)
    cmds = [
        Command(shell=f"wm size {new_w}x{new_h}", undo="wm size reset",
                label=f"render {new_w}x{new_h} ({int(scale * 100)}%)"),
    ]
    if density:
        cmds.append(Command(shell=f"wm density {int(density * scale)}", undo="wm density reset",
                            label=f"density {int(density * scale)}"))
    return [Rule(
        id="resolution.wm_scale",
        title=f"Turunkan resolusi render sistem ke {int(scale * 100)}%",
        category=Category.RESOLUTION, risk=Risk.ADVANCED,
        description=("Memaksa seluruh pipeline render (termasuk game) bekerja pada resolusi lebih "
                     "rendah. Dampak FPS besar pada perangkat GPU-bound. UI jadi lebih besar; "
                     "kalau tidak nyaman, jalankan `crvx undo` untuk kembali normal."),
        requirements=Requirements(),
        commands=cmds,
        gain=Gain(fps=16 * (1 - scale) * 2, gpu_load=-38 * (1 - scale), stability=6,
                  battery=-9, confidence=0.75),
        verify=Verify(command="wm size", expect=f"{new_w}x{new_h}"),
        tags=["gpu", "visual", "advanced"],
    )]


# --------------------------------------------------------------------------- #
# RUNTIME / SYSTEM
# --------------------------------------------------------------------------- #
def runtime_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"
    rules = [
        Rule(
            id="runtime.art_compile",
            title="Kompilasi AOT penuh (ART speed) untuk Minecraft",
            category=Category.RUNTIME, risk=Risk.SAFE,
            description=("Android menjalankan sebagian kode lewat JIT/interpreter. "
                         "`cmd package compile -m speed -f` memaksa kompilasi AOT penuh sehingga "
                         "stutter saat load chunk dan awal sesi berkurang drastis."),
            requirements=Requirements(minecraft=True, min_sdk=24),
            commands=[
                Command(shell=f"cmd package compile -m speed -f {pkg}",
                        undo=f"cmd package compile --reset -f {pkg}",
                        label="ART compile speed", optional=True),
                Command(shell=f"cmd package compile -m speed-profile -f {pkg}",
                        undo="", label="profile compile", optional=True),
            ],
            gain=Gain(fps=3, stability=9, frametime_ms=-1.1, confidence=0.7),
            verify=Verify(command=f"dumpsys package {pkg}", expect="versionName", mode="contains"),
            tags=["runtime", "stutter"],
        ),
        Rule(
            id="runtime.doze_whitelist",
            title="Bebaskan Minecraft dari Doze + pembatasan background",
            category=Category.RUNTIME, risk=Risk.SAFE,
            description=("Mencegah Android menidurkan thread jaringan/render Minecraft dan "
                         "menghentikan proses saat layar redup atau game di-background sebentar."),
            requirements=Requirements(minecraft=True),
            commands=[
                Command(shell=f"dumpsys deviceidle whitelist +{pkg}",
                        undo=f"dumpsys deviceidle whitelist -{pkg}", label="doze whitelist"),
                Command(shell=f"cmd appops set {pkg} RUN_ANY_IN_BACKGROUND allow",
                        undo=f"cmd appops set {pkg} RUN_ANY_IN_BACKGROUND default",
                        label="background allow", optional=True),
                Command(shell=f"cmd appops set {pkg} WAKE_LOCK allow",
                        undo=f"cmd appops set {pkg} WAKE_LOCK default",
                        label="wake lock allow", optional=True),
            ],
            gain=Gain(stability=7, frametime_ms=-0.8, battery=-3, confidence=0.7),
            verify=Verify(command="dumpsys deviceidle whitelist", expect="mojang"),
            tags=["runtime"],
        ),
        Rule(
            id="system.animations",
            title="Matikan animasi sistem (skala 0)",
            category=Category.SYSTEM, risk=Risk.SAFE,
            description=("Animasi window/transition/animator memakan frame budget dan membuat "
                         "CPU sibuk tepat saat game butuh. Skala 0 = sistem terasa instan."),
            commands=[
                Command(shell="settings put global window_animation_scale 0",
                        undo="settings put global window_animation_scale 1", label="window anim 0"),
                Command(shell="settings put global transition_animation_scale 0",
                        undo="settings put global transition_animation_scale 1", label="transition anim 0"),
                Command(shell="settings put global animator_duration_scale 0",
                        undo="settings put global animator_duration_scale 1", label="animator 0"),
            ],
            gain=Gain(stability=4, input_latency_ms=-6, frametime_ms=-0.5, confidence=0.8),
            verify=Verify(command="settings get global window_animation_scale", expect="0"),
            tags=["system", "latency"],
        ),
        Rule(
            id="system.power_saver_off",
            title="Matikan Battery Saver & pembatas performa",
            category=Category.SYSTEM, risk=Risk.SAFE,
            description=("Battery Saver memotong frekuensi CPU dan memaksa 60 Hz. Selama "
                         "optimasi aktif, fitur ini dimatikan agar target FPS tercapai."),
            commands=[
                Command(shell="settings put global low_power 0",
                        undo="settings delete global low_power", label="low_power 0"),
                Command(shell="settings put global battery_saver_enabled 0",
                        undo="settings delete global battery_saver_enabled",
                        label="battery saver off", optional=True),
                Command(shell="settings put global adaptive_battery_enabled 0",
                        undo="settings put global adaptive_battery_enabled 1",
                        label="adaptive battery off", optional=True),
            ],
            gain=Gain(fps=5, stability=5, battery=-12, confidence=0.7),
            verify=Verify(command="settings get global low_power", expect="0"),
            tags=["system", "power"],
        ),
        Rule(
            id="memory.trim",
            title="Bersihkan memori background sebelum sesi",
            category=Category.MEMORY, risk=Risk.SAFE,
            description=("`am kill-all` menutup proses cache yang tidak terlihat. Mengurangi "
                         "tekanan LMK (low memory killer) yang biasa jadi penyebab stutter "
                         "tiba-tiba saat main."),
            commands=[
                Command(shell="am kill-all", undo="", label="kill cached processes"),
                Command(shell="cmd package bg-dexopt-job 2>/dev/null || true",
                        undo="", label="dexopt job", optional=True),
            ],
            gain=Gain(stability=5, frametime_ms=-0.7, confidence=0.6),
            tags=["memory"],
        ),
    ]

    if mode.target_fps >= 90:
        rules.append(Rule(
            id="runtime.focus",
            title="Mode fokus: DND + layar tetap menyala saat sesi",
            category=Category.RUNTIME, risk=Risk.MODERATE,
            description=("Notifikasi masuk memicu overlay + wake lock yang menjatuhkan frame. "
                         "DND dinyalakan hanya selama sesi; `crvx undo` mengembalikannya."),
            commands=[
                Command(shell="cmd notification set_dnd on", undo="cmd notification set_dnd off",
                        label="DND on"),
                Command(shell="settings put global stay_on_while_plugged_in 3",
                        undo="settings put global stay_on_while_plugged_in 0",
                        label="stay on while charging", optional=True),
            ],
            gain=Gain(stability=6, frametime_ms=-0.6, confidence=0.6),
            tags=["focus"],
        ))

    if mode.thermal_policy in ("aggressive", "max"):
        rules.append(Rule(
            id="thermal.override",
            title=f"Thermal service: status {0 if mode.thermal_policy == 'max' else 1}",
            category=Category.THERMAL, risk=Risk.ADVANCED,
            description=("Mengatakan ke ThermalService bahwa perangkat sedang dingin sehingga "
                         "throttling preemptif tidak dipicu terlalu cepat. PERANGKAT TETAP BISA "
                         "PANAS - gunakan kipas/cooling fan dan jangan menutupi ventilasi."),
            commands=[
                Command(shell=f"cmd thermalservice override-status {0 if mode.thermal_policy == 'max' else 1}",
                        undo="cmd thermalservice override-status -1", label="thermal override"),
                Command(shell="settings put global thermal_status_override 1",
                        undo="settings delete global thermal_status_override",
                        label="penanda thermal", optional=True),
            ],
            gain=Gain(fps=6, stability=8, heat=18, battery=-8, confidence=0.6),
            verify=Verify(command="dumpsys thermalservice", expect="status"),
            tags=["thermal", "risk"],
        ))

    return rules


# --------------------------------------------------------------------------- #
# ROOT / SHIZUKU (kernel level)
# --------------------------------------------------------------------------- #
def root_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    rules: List[Rule] = []
    gov_backup = f"{TMP}/crvx_gov_paths.txt"
    val_backup = f"{TMP}/crvx_gov_values.txt"
    gpu_backup = f"{TMP}/crvx_gpu_gov.txt"

    if not (dev.rooted or dev.shizuku):
        return rules

    rules.append(Rule(
        id="cpu.governor",
        title="CPU governor -> performance (semua core)",
        category=Category.CPU, risk=Risk.ROOT,
        description=("Mengganti scaling_governor ke `performance` agar CPU tidak turun frekuensi "
                     "di tengah frame. Nilai asli disimpan dulu supaya bisa dikembalikan persis."),
        requirements=Requirements(root=True),
        commands=[
            Command(shell=f"rm -f {gov_backup} {val_backup}; "
                          "for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do "
                          f"[ -f \"$f\" ] || continue; echo \"$f\" >> {gov_backup}; "
                          f"cat \"$f\" >> {val_backup}; echo performance > \"$f\" 2>/dev/null || true; done",
                    undo=f"paste -d'|' {gov_backup} {val_backup} | while IFS='|' read -r p v; do "
                         f"echo \"$v\" > \"$p\" 2>/dev/null || true; done",
                    label="scaling_governor = performance", root=True),
            Command(shell="echo 1 > /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || true",
                    undo="echo 1 > /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || true",
                    label="cpu boost on", root=True, optional=True),
        ],
        gain=Gain(fps=7, stability=9, frametime_ms=-1.6, heat=14, battery=-14, confidence=0.7),
        tags=["cpu", "root"],
    ))

    rules.append(Rule(
        id="gpu.governor",
        title="GPU devfreq governor -> performance (Adreno/Mali)",
        category=Category.GPU, risk=Risk.ROOT,
        description=("Menyetel governor devfreq GPU (kgsl untuk Adreno, mali untuk ARM) agar "
                     "frekuensi GPU bertahan tinggi. Ini tuas paling berdampak untuk Bedrock "
                     "yang GPU-bound."),
        requirements=Requirements(root=True),
        commands=[
            Command(shell=f"rm -f {gpu_backup}; for g in /sys/class/kgsl/kgsl-3d0/devfreq/governor "
                          "/sys/devices/platform/*.mali/devfreq/*.governor "
                          "/sys/class/devfreq/*.mali/governor; do "
                          f"[ -f \"$g\" ] || continue; echo \"$g|$(cat $g)\" >> {gpu_backup}; "
                          "echo performance > \"$g\" 2>/dev/null || echo always_on > \"$g\" 2>/dev/null || true; done",
                    undo=f"[ -f {gpu_backup} ] && cat {gpu_backup} | while IFS='|' read -r p v; do "
                         "echo \"$v\" > \"$p\" 2>/dev/null || true; done",
                    label="gpu governor = performance", root=True),
            Command(shell="echo 0 > /sys/class/kgsl/kgsl-3d0/pwrctrl/pwr_level 2>/dev/null || true",
                    undo="", label="kgsl pwr level", root=True, optional=True),
        ],
        gain=Gain(fps=9, stability=7, gpu_load=-10, heat=16, battery=-12, confidence=0.65),
        tags=["gpu", "root"],
    ))

    rules.append(Rule(
        id="cpu.core_ctl",
        title="Matikan core_ctl / dynamic hotplug",
        category=Category.CPU, risk=Risk.ROOT,
        description=("Beberapa SoC menonaktifkan core saat load dianggap ringan, lalu "
                     "menyalakannya lagi - inilah sumber stutter 1% low. Core dikunci aktif."),
        requirements=Requirements(root=True),
        commands=[
            Command(shell="for c in /sys/devices/system/cpu/cpu*/core_ctl/enable; do "
                          "[ -f \"$c\" ] && echo 0 > \"$c\" 2>/dev/null || true; done",
                    undo="for c in /sys/devices/system/cpu/cpu*/core_ctl/enable; do "
                         "[ -f \"$c\" ] && echo 1 > \"$c\" 2>/dev/null || true; done",
                    label="core_ctl off", root=True),
            Command(shell="for c in /sys/devices/system/cpu/cpu*/online; do "
                          "[ -f \"$c\" ] && echo 1 > \"$c\" 2>/dev/null || true; done",
                    undo="", label="semua core online", root=True, optional=True),
        ],
        gain=Gain(stability=12, frametime_ms=-1.2, fps=2, heat=8, battery=-9, confidence=0.6),
        tags=["cpu", "root", "stutter"],
    ))

    rules.append(Rule(
        id="memory.kernel",
        title="Tuning kernel: swappiness + read-ahead",
        category=Category.MEMORY, risk=Risk.ROOT,
        description=("Menurunkan kecenderungan swap dan menaikkan read-ahead storage agar "
                     "streaming chunk dari UFS/eMMC tidak menjatuhkan frame."),
        requirements=Requirements(root=True),
        commands=[
            Command(shell="echo 20 > /proc/sys/vm/swappiness 2>/dev/null || true",
                    undo="echo 100 > /proc/sys/vm/swappiness 2>/dev/null || true",
                    label="swappiness 20", root=True),
            Command(shell="for d in /sys/block/*/queue/read_ahead_kb; do echo 2048 > \"$d\" 2>/dev/null || true; done",
                    undo="for d in /sys/block/*/queue/read_ahead_kb; do echo 512 > \"$d\" 2>/dev/null || true; done",
                    label="read_ahead 2048 KB", root=True),
            Command(shell="echo 0 > /proc/sys/vm/compact_memory 2>/dev/null; "
                          "echo 1 > /proc/sys/vm/drop_caches 2>/dev/null || true",
                    undo="", label="cache trim", root=True, optional=True),
        ],
        gain=Gain(stability=6, frametime_ms=-0.9, confidence=0.55),
        tags=["memory", "root"],
    ))

    if mode.thermal_policy == "max":
        rules.append(Rule(
            id="thermal.kernel",
            title="Bypass thermal engine (kernel) - hanya sesi pendek",
            category=Category.THERMAL, risk=Risk.ROOT,
            description=("Menghentikan daemon thermal vendor supaya tidak ada penurunan "
                         "frekuensi paksa. RISIKO NYATA: perangkat bisa overheat. Gunakan "
                         "cooling fan dan hentikan setelah 30-45 menit."),
            requirements=Requirements(root=True),
            commands=[
                Command(shell="for t in /sys/class/thermal/thermal_zone*/mode; do "
                              "[ -f \"$t\" ] && echo disabled > \"$t\" 2>/dev/null || true; done",
                        undo="for t in /sys/class/thermal/thermal_zone*/mode; do "
                             "[ -f \"$t\" ] && echo enabled > \"$t\" 2>/dev/null || true; done",
                        label="thermal zone disabled", root=True),
                Command(shell="stop vendor.thermal-engine 2>/dev/null; stop thermalservice 2>/dev/null || true",
                        undo="start vendor.thermal-engine 2>/dev/null; start thermalservice 2>/dev/null || true",
                        label="thermal daemon stop", root=True, optional=True),
            ],
            gain=Gain(fps=10, stability=10, heat=35, battery=-18, confidence=0.5),
            tags=["thermal", "root", "danger"],
        ))

    return rules


# --------------------------------------------------------------------------- #
# PACK
# --------------------------------------------------------------------------- #
def pack_rules(dev: Device, mode: FpsMode, budget: QualityBudget) -> List[Rule]:
    if not budget.fog_cut:
        return []
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"
    remote_dir = f"/sdcard/Android/data/{pkg}/files/resource_packs"
    return [Rule(
        id="pack.fog_cut",
        title="Pasang CRVX Fog-Cut .mcpack (kurangi overdraw transparan)",
        category=Category.PACK, risk=Risk.MODERATE,
        description=("Resource pack sah (bukan modifikasi APK/game binary) yang memotong jarak "
                     "fog per bioma. Mengurangi jumlah fragmen alpha-blended yang digambar GPU. "
                     "Efek visual: kabut lebih tipis. Bisa dilepas kapan saja dari "
                     "Settings > Global Resources."),
        requirements=Requirements(minecraft=True),
        commands=[
            Command(shell=f"mkdir -p {remote_dir} 2>/dev/null || true", undo="", label="siapkan folder"),
            Command(shell=f"# push file: crvx-pack-fogcut.mcpack -> {remote_dir}/",
                    undo=f"rm -f {remote_dir}/crvx-pack-fogcut.mcpack", label="push .mcpack"),
        ],
        gain=Gain(fps=1.5, gpu_load=-3, confidence=0.4),
        tags=["pack", "visual"],
    )]


# --------------------------------------------------------------------------- #
BUILDERS: List[Callable[[Device, FpsMode, QualityBudget], List[Rule]]] = [
    display_rules,
    gamemode_rules,
    resolution_rules,
    minecraft_rules,
    runtime_rules,
    root_rules,
    pack_rules,
]


def build_catalog(dev: Device, mode: FpsMode, budget: Optional[QualityBudget] = None) -> List[Rule]:
    budget = budget or mode.budget_for(dev)
    catalog: List[Rule] = []
    seen = set()
    for builder in BUILDERS:
        for rule in builder(dev, mode, budget):
            if rule.id in seen:
                continue
            seen.add(rule.id)
            catalog.append(rule)
    return catalog
