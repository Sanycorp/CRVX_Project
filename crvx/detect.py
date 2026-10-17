"""Deteksi perangkat: probing lengkap lewat ADB -> objek Device yang diperkaya."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .adb import CommandResult, Transport
from . import MC_PACKAGE_CANDIDATES as MC_PACKAGES
from .models import Device, DisplayMode, MinecraftInstall, Vendor
from .soc import classify_soc, enrich, guess_vendor

OPTIONS_PATHS = [
    "/sdcard/Android/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt",
    "/storage/emulated/0/Android/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt",
    "/sdcard/games/com.mojang/minecraftpe/options.txt",
    "/data/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt",
    "/data/user/0/{pkg}/files/games/com.mojang/minecraftpe/options.txt",
]

PROP_KEYS = {
    "model": ["ro.product.model", "ro.vendor.product.model", "ro.product.odm.model"],
    "brand": ["ro.product.brand", "ro.vendor.product.brand", "ro.product.system.brand"],
    "manufacturer": ["ro.product.manufacturer", "ro.vendor.product.manufacturer"],
    "codename": ["ro.product.device", "ro.vendor.product.device", "ro.product.board"],
    "board_platform": ["ro.board.platform", "ro.vendor.board.platform", "ro.hardware"],
    "soc_model": ["ro.soc.model", "ro.hardware.chipname", "ro.board.platform"],
    "soc_manufacturer": ["ro.soc.manufacturer"],
    "android_release": ["ro.build.version.release", "ro.build.version.release_or_codename"],
    "security_patch": ["ro.build.version.security_patch"],
    "abi": ["ro.product.cpu.abi"],
    "build_id": ["ro.build.display.id"],
    "hardware": ["ro.hardware"],
}


def _getprop_all(transport: Transport) -> Dict[str, str]:
    res = transport.shell("getprop")
    props: Dict[str, str] = {}
    if res.ok:
        for line in res.out.splitlines():
            match = re.match(r"\[(.+?)\]:\s*\[(.*?)\]", line.strip())
            if match:
                props[match.group(1)] = match.group(2)
    for key in set(sum(PROP_KEYS.values(), []) + ["ro.build.version.sdk"]):
        if key not in props:
            single = transport.shell(f"getprop {key}")
            if single.ok and single.out.strip():
                props[key] = single.out.strip()
    return props


def _parse_display(transport: Transport) -> Tuple[List[DisplayMode], float, Tuple[int, int]]:
    res = transport.shell("dumpsys display")
    modes: List[DisplayMode] = []
    size = (0, 0)
    if res.ok:
        text = res.out
        for match in re.finditer(r"width=(\d+),\s*height=(\d+),\s*fps=([\d\.]+)", text):
            modes.append(DisplayMode(int(match.group(1)), int(match.group(2)),
                                     float(match.group(3))))
        if not modes:
            for match in re.finditer(r"(\d+) x (\d+) @ ?([\d\.]+)Hz", text):
                modes.append(DisplayMode(int(match.group(1)), int(match.group(2)),
                                         float(match.group(3))))
        if not modes:
            for match in re.finditer(r"fps=([\d\.]+)", text):
                modes.append(DisplayMode(0, 0, float(match.group(1))))
        active_match = re.search(r"mActiveRenderFrameRate=([\d\.]+)", text) or \
            re.search(r"peakRefreshRate=([\d\.]+)", text)
        size_match = re.search(r"real (\d+) x (\d+)", text) or \
            re.search(r"uniqueId=\"[^\"]*\", (\d+) x (\d+)", text)
        if size_match:
            size = (int(size_match.group(1)), int(size_match.group(2)))
        active = float(active_match.group(1)) if active_match else 0.0
    else:
        active = 0.0
    if not modes:
        wm = transport.shell("wm size")
        if wm.ok:
            match = re.search(r"(\d+)x(\d+)", wm.out)
            if match:
                size = (int(match.group(1)), int(match.group(2)))
        modes = [DisplayMode(size[0], size[1], 60.0)]
        active = 60.0
    if size == (0, 0) and modes:
        size = (modes[0].width, modes[0].height)
    if size != (0, 0):
        for mode in modes:
            if mode.width == 0:
                mode.width, mode.height = size
    if active <= 0:
        active = max((m.fps for m in modes), default=60.0)
    return modes, active, size


def _parse_int(text: str, pattern: str, default: int = 0) -> int:
    match = re.search(pattern, text)
    return int(float(match.group(1))) if match else default


def _parse_float(text: str, pattern: str, default: float = 0.0) -> float:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else default


def detect_minecraft(transport: Transport) -> MinecraftInstall:
    install = MinecraftInstall()
    packages: List[str] = []
    for candidate in MC_PACKAGES:
        res = transport.shell(f"pm list packages | grep {candidate.split('.')[-1]}")
        if res.ok and candidate in res.out:
            packages.append(candidate)
    if not packages:
        res = transport.shell("pm list packages")
        if res.ok:
            for line in res.out.splitlines():
                if "mojang" in line.lower():
                    packages.append(line.split(":", 1)[-1].strip())
    if not packages:
        return install

    install.installed = True
    install.package = packages[0]
    info = transport.shell(f"dumpsys package {install.package}")
    if info.ok:
        install.version_name = _parse_str(info.out, r"versionName=([\w\.\-]+)")
        install.version_code = _parse_str(info.out, r"versionCode=(\d+)")

    for template in OPTIONS_PATHS:
        path = template.format(pkg=install.package)
        listed = transport.shell(f"cat {path}")
        if listed.ok and listed.out.strip():
            install.options_path = path
            install.data_root = path.rsplit("/minecraftpe/", 1)[0] + "/minecraftpe"
            install.root_needed = path.startswith("/data/data") or path.startswith("/data/user")
            writable = transport.shell(f'[ -w "{path}" ] && echo WRITABLE || echo READONLY')
            shell_writable = path.startswith(("/sdcard", "/storage/emulated"))
            install.writable = ("WRITABLE" in writable.out or shell_writable
                                or install.root_needed)
            install.current_options = parse_options(listed.out)
            break
    if not install.options_path:
        install.options_path = OPTIONS_PATHS[0].format(pkg=install.package)
        install.data_root = install.options_path.rsplit("/minecraftpe/", 1)[0] + "/minecraftpe"
        install.writable = transport.shell("id").out.strip().startswith("uid=0")
    return install


def _parse_str(text: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else default


def parse_options(text: str) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for line in (text or "").splitlines():
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            key = key.strip()
            if key:
                options[key] = value.strip()
    return options


def detect_device(transport: Transport, quick: bool = False) -> Device:
    """Probing menyeluruh. quick=True melewati bagian yang lambat."""
    dev = Device(serial=getattr(transport, "serial", ""),
                 simulated=getattr(transport, "simulated", False),
                 transport=transport.name)

    props = _getprop_all(transport)
    dev.extras["props"] = {k: props.get(k, "") for k in
                           ("ro.hardware", "ro.build.version.incremental", "ro.build.type")}

    for field_name, keys in PROP_KEYS.items():
        for key in keys:
            if props.get(key):
                setattr(dev, field_name, props[key])
                break

    sdk = _parse_int(props.get("ro.build.version.sdk", "") or
                     transport.shell("getprop ro.build.version.sdk").out, r"(\d+)")
    dev.android_sdk = sdk or 0

    modes, active, size = _parse_display(transport)
    dev.display_modes = modes
    dev.active_fps = active
    dev.panel_max_fps = max((m.fps for m in modes), default=active)
    dev.extras["screen"] = f"{size[0]}x{size[1]}"

    battery = transport.shell("dumpsys battery")
    if battery.ok:
        level = _parse_int(battery.out, r"level:\s*(\d+)")
        temp = _parse_float(battery.out, r"temperature:\s*(\d+)")
        dev.battery_level = level or 100
        dev.battery_temp_c = round(temp / 10.0, 1) if temp else 0.0
        dev.charging = bool(re.search(r"(AC|USB) powered:\s*true", battery.out))

    thermal = transport.shell("dumpsys thermalservice")
    if thermal.ok:
        dev.thermal_status = _parse_int(thermal.out, r"(?:thermal status|status):\s*(\d+)")

    meminfo = transport.shell("cat /proc/meminfo")
    if meminfo.ok:
        kb = _parse_int(meminfo.out, r"MemTotal:\s*(\d+)")
        dev.ram_mb = kb // 1024

    if not quick:
        cpu_ls = transport.shell("ls /sys/devices/system/cpu")
        if cpu_ls.ok:
            dev.cpu_cores = len(re.findall(r"cpu\d+", cpu_ls.out))
        freq = transport.shell("cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        if freq.ok:
            dev.cpu_max_khz = _parse_int(freq.out, r"(\d+)")
        else:
            for core in range(7, -1, -1):
                res = transport.shell(
                    f"cat /sys/devices/system/cpu/cpu{core}/cpufreq/cpuinfo_max_freq")
                if res.ok:
                    dev.cpu_max_khz = max(dev.cpu_max_khz, _parse_int(res.out, r"(\d+)"))

        sf = transport.shell("dumpsys SurfaceFlinger")
        if sf.ok:
            renderer = _parse_str(sf.out, r"renderer=([^,\n]+)")
            if renderer:
                dev.gpu_renderer = renderer.strip()

        uid = transport.shell("id")
        dev.rooted = "uid=0" in uid.out
        if not dev.rooted:
            which_su = transport.shell("which su")
            dev.rooted = which_su.ok and bool(which_su.out.strip())

    dev.vendor = guess_vendor(dev.manufacturer, dev.brand, dev.model)
    dev.minecraft = detect_minecraft(transport)

    if dev.minecraft.installed:
        modes_res = transport.shell(f"cmd game list-modes {dev.minecraft.package}")
        if modes_res.ok and "available game modes" in modes_res.out:
            dev.game_mode_supported = True
            dev.game_mode_current = _parse_str(modes_res.out, r"current mode:\s*(\w+)")
            listed = re.search(r"available game modes:\s*\[(.*?)\]", modes_res.out)
            if listed:
                dev.game_mode_available = [x.strip() for x in listed.group(1).split(",") if x.strip()]

    return enrich(dev)


def generic_device() -> Device:
    """Profil konservatif untuk ekspor skrip tanpa perangkat tersambung.

    Tidak menebak resolusi/SoC, jadi skrip yang dihasilkan tetap aman dijalankan
    di HP mana pun. Jalankan `crvx detect` untuk rencana yang benar-benar
    disesuaikan dengan perangkat Anda.
    """
    dev = Device(
        serial="", simulated=False, transport="generic",
        model="Generic Android", brand="", manufacturer="",
        android_sdk=34, android_release="14", abi="arm64-v8a",
        cpu_cores=8, cpu_max_khz=2_400_000, ram_mb=6144,
        display_modes=[DisplayMode(0, 0, 60.0), DisplayMode(0, 0, 90.0),
                       DisplayMode(0, 0, 120.0)],
        active_fps=60.0, panel_max_fps=120.0,
        game_mode_supported=True, game_mode_current="standard",
        game_modes_available=["standard", "performance", "battery"],
        minecraft=MinecraftInstall(installed=True, package="com.mojang.minecraftpe",
                                   version_name="", writable=True,
                                   options_path=options_path_for("com.mojang.minecraftpe")),
        extras={"tier": 3, "tier_name": "MID", "tier_reason": "profil generik"},
    )
    enrich(dev)
    dev.engine_cap_fps = 120
    dev.engine_cap_reason = ("profil generik: diasumsikan engine bisa 120 FPS. "
                             "Jalankan `crvx detect` untuk angka pasti perangkat Anda")
    return dev


def options_path_for(package: str) -> str:
    return OPTIONS_PATHS[0].format(pkg=package)


def describe_device(dev: Device) -> str:
    tier = dev.extras.get("tier_name", "MID")
    lines = [
        f"{dev.brand or dev.manufacturer} {dev.model}  [{tier}]  {'(SIMULATOR)' if dev.simulated else ''}",
        f"SoC      : {dev.extras.get('soc_name') or dev.soc_model or 'tidak dikenal'}"
        f"  |  GPU: {dev.gpu_renderer or dev.extras.get('gpu_name') or '-'}",
        f"Android  : {dev.android_release} (SDK {dev.android_sdk})  |  RAM {dev.ram_mb // 1024} GB"
        f"  |  {dev.cpu_cores} core @ {dev.cpu_max_khz // 1000} MHz",
        f"Layar    : {dev.extras.get('screen', '-')}  |  refresh tersedia: "
        f"{', '.join(f'{r:g}Hz' for r in dev.refresh_rates) or '-'}  |  aktif {dev.active_fps:g} Hz",
        f"Termal   : status {dev.thermal_status}  |  baterai {dev.battery_temp_c}C ({dev.battery_level}%)"
        f"{'  [charging]' if dev.charging else ''}",
        f"Minecraft: {dev.minecraft.version_name or 'tidak terdeteksi'} ({dev.minecraft.package})"
        f"  |  options.txt {'bisa ditulis' if dev.minecraft.writable else 'terkunci'}",
        f"GameMode : {'didukung (' + dev.game_mode_current + ')' if dev.game_mode_supported else 'tidak didukung'}"
        f"  |  Root: {'ya' if dev.rooted else 'tidak'}  |  Shizuku: {'ya' if dev.shizuku else 'tidak'}",
        f"Cap FPS  : {dev.engine_cap_fps} FPS  ({dev.engine_cap_reason})",
    ]
    return "\n".join(lines)
