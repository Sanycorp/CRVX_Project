"""Transport ADB: real device (subprocess) + simulator ber-fisika untuk demo.

Simulator mensimulasikan POCO X6 Pro (Dimensity 8300 Ultra, 120 Hz, Android 15)
lengkap dengan state yang berubah saat perintah diterapkan, sehingga benchmark
dan verifikasi benar-benar merespons.
"""

from __future__ import annotations

import math
import os
import random
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class CommandResult:
    code: int = 0
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def text(self) -> str:
        return (self.out or "") + (("\n" + self.err) if self.err else "")


class Transport:
    """Interface transport."""

    name = "abstract"
    simulated = False

    def shell(self, cmd: str, timeout: float = 25.0, root: bool = False) -> CommandResult:
        raise NotImplementedError

    def push(self, local: str, remote: str) -> CommandResult:
        raise NotImplementedError

    def pull(self, remote: str, local: str) -> CommandResult:
        raise NotImplementedError

    def available(self) -> bool:
        return False

    def devices(self) -> List[str]:
        return []


# --------------------------------------------------------------------------- #
# Real ADB
# --------------------------------------------------------------------------- #
class AdbTransport(Transport):
    name = "adb"

    def __init__(self, serial: str = "", adb_bin: str = ""):
        self.serial = serial
        self.adb = adb_bin or shutil.which("adb") or "adb"
        self._has_su: Optional[bool] = None

    def available(self) -> bool:
        res = self._run(["devices"], timeout=10)
        return res.ok and bool(self._parse_devices(res.out))

    def devices(self) -> List[str]:
        return self._parse_devices(self._run(["devices"], timeout=10).out)

    @staticmethod
    def _parse_devices(out: str) -> List[str]:
        found: List[str] = []
        for line in (out or "").splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                found.append(parts[0])
        return found

    def _run(self, args: List[str], timeout: float = 25.0) -> CommandResult:
        try:
            proc = subprocess.run(
                [self.adb] + args, capture_output=True, text=True, timeout=timeout
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)
        except FileNotFoundError:
            return CommandResult(127, "", "adb tidak ditemukan di PATH")
        except subprocess.TimeoutExpired:
            return CommandResult(124, "", f"timeout setelah {timeout}s")
        except Exception as exc:  # pragma: no cover
            return CommandResult(1, "", str(exc))

    def shell(self, cmd: str, timeout: float = 25.0, root: bool = False) -> CommandResult:
        if root:
            if self._has_su is None:
                probe = self._run(["-s", self.serial, "shell", "su -c id"], timeout=8)
                self._has_su = probe.ok and "uid=0" in probe.out
            if self._has_su:
                escaped = cmd.replace("'", "'\\''")
                cmd = f"su -c '{escaped}'"
        args: List[str] = []
        if self.serial:
            args += ["-s", self.serial]
        args += ["shell", cmd]
        res = self._run(args, timeout=timeout)
        if root and res.err and "Permission denied" in res.err:
            res.code = res.code or 1
        return res

    def push(self, local: str, remote: str) -> CommandResult:
        args: List[str] = []
        if self.serial:
            args += ["-s", self.serial]
        return self._run(args + ["push", local, remote], timeout=120)

    def pull(self, remote: str, local: str) -> CommandResult:
        args: List[str] = []
        if self.serial:
            args += ["-s", self.serial]
        return self._run(args + ["pull", remote, local], timeout=120)


class NoTransport(Transport):
    """Dipakai saat tidak ada perangkat: engine tetap bisa membuat rencana."""

    name = "offline"

    def shell(self, cmd: str, timeout: float = 25.0, root: bool = False) -> CommandResult:
        return CommandResult(1, "", "tidak ada perangkat tersambung")


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #
DEFAULT_OPTIONS_TXT = """gfx_viewdistance:256
gfx_particleviewdistance:0.5
gfx_viewbobbing:1
gfx_damagebobbing:1
gfx_transparentleaves:1
gfx_smoothlighting:1
gfx_fancyskies:1
gfx_field_of_view:60
gfx_msaa:4
gfx_gamma:0.5
gfx_multithreaded_renderer:1
gfx_vsync:1
gfx_max_framerate:60
gfx_max_framerate_advanced:0
gfx_guiscale_offset:0
gfx_ui_profile:1
gfx_fullscreen:0
mp_username:Player
dvce_filestoragelocation:2
"""


class SimTransport(Transport):
    """Simulasi perangkat Android + Minecraft Bedrock yang responsif."""

    name = "sim"
    simulated = True

    def __init__(self, profile: str = "poco_x6_pro"):
        self.profile = profile
        self.serial = f"SIMULATOR-{profile.upper()}"
        self.settings: Dict[str, Dict[str, str]] = {
            "system": {"peak_refresh_rate": "60.0", "min_refresh_rate": "60.0",
                       "screen_brightness_mode": "1"},
            "secure": {"user_refresh_rate": "0", "miui_refresh_rate": "0",
                       "show_touches": "0"},
            "global": {"window_animation_scale": "1.0", "transition_animation_scale": "1.0",
                       "animator_duration_scale": "1.0", "low_power": "0",
                       "hwui_renderer": "skiavk", "disable_window_blurs": "0"},
        }
        self.state: Dict[str, object] = {
            "game_mode": "standard",
            "custom_fps": 0,
            "downscale": 1.0,
            "use_angle": False,
            "wm_size": (1220, 2712),
            "wm_density": 440,
            "compiled": False,
            "dnd": False,
            "stayon": False,
            "deviceidle_whitelist": set(),
            "stopped_packages": set(),
            "bloat_disabled": set(),
            "thermal_override": None,
            "refresh_locked": 60.0,
            "fps_history": [],
            "pack_installed": False,
        }
        self.fs: Dict[str, str] = {
            "/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt":
                DEFAULT_OPTIONS_TXT,
        }
        self.writes: List[str] = []

    # -- helpers ---------------------------------------------------------- #
    def available(self) -> bool:
        return True

    def devices(self) -> List[str]:
        return [self.serial]

    def push(self, local: str, remote: str) -> CommandResult:
        try:
            with open(local, "rb") as fh:
                data = fh.read()
            self.fs[remote] = f"<binary {len(data)} bytes>"
            self.state["pack_installed"] = True
            return CommandResult(0, f"{local}: 1 file pushed, 0 skipped.")
        except OSError as exc:
            return CommandResult(1, "", str(exc))

    def pull(self, remote: str, local: str) -> CommandResult:
        if remote not in self.fs:
            return CommandResult(1, "", f"{remote}: does not exist")
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        with open(local, "w", encoding="utf-8") as fh:
            fh.write(self.fs[remote])
        return CommandResult(0, f"{remote}: 1 file pulled")

    # -- fps model -------------------------------------------------------- #
    def options(self) -> Dict[str, str]:
        raw = self.fs.get(
            "/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe/options.txt",
            DEFAULT_OPTIONS_TXT)
        out: Dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                out[key.strip()] = value.strip()
        return out

    def set_option(self, key: str, value: str) -> None:
        path = ("/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/"
                "minecraftpe/options.txt")
        opts = self.options()
        opts[key] = str(value)
        self.fs[path] = "".join(f"{k}:{v}\n" for k, v in opts.items())

    def model_fps(self) -> Tuple[float, float]:
        """Model fisika sederhana: (fps_rata_rata, frametime_p95)."""
        opts = self.options()
        st = self.state
        base_engine = 110.0                    # kemampuan engine tanpa beban
        gpu = base_engine

        chunks = float(opts.get("gfx_viewdistance", "256")) / 16.0
        gpu *= max(0.20, 1.45 - 0.045 * chunks)                      # render distance
        gpu *= 0.90 if opts.get("gfx_smoothlighting") == "1" else 1.0
        gpu *= 0.94 if opts.get("gfx_transparentleaves") == "1" else 1.0
        gpu *= 0.97 if opts.get("gfx_fancyskies") == "1" else 1.0
        msaa = float(opts.get("gfx_msaa", "1") or 1)
        gpu *= {1: 1.0, 2: 0.90, 4: 0.78, 8: 0.62, 16: 0.48}.get(msaa, 0.8)
        gpu *= 0.9 + 0.2 * float(opts.get("gfx_particleviewdistance", "0.5") or 0.5)
        fov = float(opts.get("gfx_field_of_view", "60") or 60)
        gpu *= 1.0 - (fov - 60) * 0.0022

        # resolusi render (wm size / downscale)
        w, h = st["wm_size"]
        pixels = (w * h) * float(st["downscale"])
        gpu *= max(0.35, min(1.35, 2_000_000 / max(pixels, 1)) ** 0.55)

        if st["use_angle"]:
            gpu *= 0.93
        gpu *= 0.88                            # efisiensi driver mobile nyata

        cap_mode = float(opts.get("gfx_max_framerate", "60") or 0)
        vsync = opts.get("gfx_vsync", "1") == "1"

        ceiling = float(st["refresh_locked"])
        panel_cap = 120.0
        engine_cap = 120.0 if st["compiled"] else 96.0
        if vsync:
            ceiling = min(ceiling, panel_cap)
        ceiling = min(ceiling, panel_cap, engine_cap)
        if cap_mode > 0:
            ceiling = min(ceiling, cap_mode)
        if st["custom_fps"]:
            ceiling = min(ceiling, float(st["custom_fps"]))

        fps = min(gpu, ceiling)
        thermal_penalty = 1.0 - 0.035 * max(0, self.thermal_status() - 1)
        fps *= thermal_penalty

        jitter = 1.0 + (0.12 if fps < 45 else 0.05) * math.sin(time.time() / 3.0)
        avg = max(8.0, fps * jitter)
        p95_ft = 1000.0 / max(avg, 1.0) * (1.55 if st["refresh_locked"] <= 60 else 1.28)
        st["fps_history"].append(avg)
        st["fps_history"] = st["fps_history"][-240:]
        return avg, p95_ft

    def thermal_status(self) -> int:
        override = self.state["thermal_override"]
        if override is not None:
            return int(override)
        hist = self.state["fps_history"][-40:]
        load = sum(hist) / max(len(hist), 1) / 120.0
        return min(6, int(load * 4))

    def battery_temp(self) -> float:
        return round(31.0 + self.thermal_status() * 2.4 + random.uniform(-0.3, 0.3), 1)

    # -- command dispatch ------------------------------------------------- #
    def shell(self, cmd: str, timeout: float = 25.0, root: bool = False) -> CommandResult:
        cmd = cmd.strip()
        self.writes.append(cmd)
        handlers: List[Tuple[str, Callable[[re.Match], CommandResult]]] = [
            (r"^getprop\s+(?P<key>[\w\.\-]+)$", self.h_getprop),
            (r"^getprop$", self.h_getprop_all),
            (r"^settings\s+(?P<op>get|put|delete)\s+(?P<ns>system|secure|global)\s+"
             r"(?P<key>[\w\.]+)(\s+(?P<val>.+))?$", self.h_settings),
            (r"^dumpsys\s+display", self.h_dumpsys_display),
            (r"^dumpsys\s+battery", self.h_dumpsys_battery),
            (r"^dumpsys\s+thermalservice", self.h_dumpsys_thermal),
            (r"^dumpsys\s+SurfaceFlinger\s+--list", self.h_sf_list),
            (r"^dumpsys\s+SurfaceFlinger\s+--latency", self.h_sf_latency),
            (r"^dumpsys\s+SurfaceFlinger\b", self.h_sf_gles),
            (r"^dumpsys\s+gfxinfo\s+(?P<pkg>[\w\.]+)\s+framestats", self.h_framestats),
            (r"^dumpsys\s+gfxinfo\s+(?P<pkg>[\w\.]+)\s+reset", self.h_noop),
            (r"^dumpsys\s+package\s+(?P<pkg>[\w\.]+)", self.h_dumpsys_package),
            (r"^dumpsys\s+deviceidle\s+whitelist", self.h_deviceidle),
            (r"^cat\s+/proc/meminfo", self.h_meminfo),
            (r"^cat\s+/proc/cpuinfo", self.h_cpuinfo),
            (r"^ls\s+/sys/devices/system/cpu\b", self.h_cpu_ls),
            (r"^cat\s+/sys/devices/system/cpu/cpu\d+/cpufreq/cpuinfo_max_freq", self.h_cpu_max),
            (r"^cat\s+(?P<path>\S*options\.txt)$", self.h_cat_file),
            (r"^\[\s+-w\s+", self.h_test_writable),
            (r"(?s).+options\.txt", self.h_options_write),
            (r"^ls\s+(-l\s+|-a\s+)*(?P<path>/\S+)$", self.h_ls),
            (r"^pm\s+list\s+packages", self.h_pm_list),
            (r"^pm\s+path\s+(?P<pkg>[\w\.]+)", self.h_noop),
            (r"^pm\s+disable-user.*\s(?P<pkg>[\w\.]+)$", self.h_pm_disable),
            (r"^cmd\s+game\s+list-modes\s+(?P<pkg>[\w\.]+)", self.h_game_list_modes),
            (r"^cmd\s+game\s+list-configs\s+(?P<pkg>[\w\.]+)", self.h_game_list_configs),
            (r"^cmd\s+game\s+mode\s+(?P<mode>standard|performance|battery|custom|[1-4])\s+"
             r"(?P<pkg>[\w\.]+)", self.h_game_mode),
            (r"^cmd\s+game\s+mode\s+--user", self.h_game_mode_user),
            (r"^cmd\s+game\s+set\s+(?P<args>.*)$", self.h_game_set),
            (r"^cmd\s+game\s+reset\s+(?P<pkg>[\w\.]+)", self.h_game_reset),
            (r"^device_config\s+(get|put)\s+game_overlay", self.h_device_config),
            (r"^wm\s+size(\s+(?P<val>[\dx]+|reset))?$", self.h_wm_size),
            (r"^wm\s+density(\s+(?P<val>\d+|reset))?$", self.h_wm_density),
            (r"^cmd\s+display\s+set-user-preferred-display-mode\s+(?P<args>.+)$",
             self.h_preferred_mode),
            (r"^cmd\s+package\s+compile\s+(?P<args>.+)$", self.h_compile),
            (r"^cmd\s+notification\s+set_dnd\s+(?P<val>on|off)", self.h_dnd),
            (r"^cmd\s+thermalservice\s+override-status\s+(?P<val>\d+)", self.h_thermal_override),
            (r"^svc\s+power\s+stayon\s+(?P<val>true|false|usb)", self.h_stayon),
            (r"^am\s+force-stop\s+(?P<pkg>[\w\.]+)", self.h_force_stop),
            (r"^am\s+kill\s+", self.h_noop),
            (r"^monkey\s+-p\s+(?P<pkg>[\w\.]+)", self.h_monkey),
            (r"^input\s+keyevent", self.h_noop),
            (r"^id$", self.h_id),
            (r"^which\s+su$", self.h_which_su),
            (r"^su\s+-c\s+", self.h_denied),
            (r"^echo\s+", self.h_echo),
            (r"^mkdir\s+-p\s+", self.h_noop),
            (r"^rm\s+", self.h_noop),
            (r"^cp\s+\S*options\.txt", self.h_options_backup),
            (r"^cp\s+", self.h_noop),
        ]
        for pattern, handler in handlers:
            match = re.match(pattern, cmd)
            if match:
                try:
                    return handler(match)
                except Exception as exc:  # pragma: no cover
                    return CommandResult(1, "", f"sim error: {exc}")
        return CommandResult(0, "", "")

    # -- handlers --------------------------------------------------------- #
    PROPS = {
        "ro.product.model": "2311DRK48G",
        "ro.product.brand": "POCO",
        "ro.product.manufacturer": "Xiaomi",
        "ro.product.device": "duchamp",
        "ro.product.board": "duchamp",
        "ro.board.platform": "mt6897",
        "ro.soc.model": "Dimensity 8300 Ultra",
        "ro.soc.manufacturer": "Mediatek",
        "ro.build.version.sdk": "35",
        "ro.build.version.release": "15",
        "ro.build.version.security_patch": "2026-09-05",
        "ro.build.version.incremental": "OS2.0.4.0.VNLMIXM",
        "ro.build.display.id": "HyperOS 2.0 (Android 15)",
        "ro.product.cpu.abi": "arm64-v8a",
        "ro.hardware": "mt6897",
        "ro.miui.ui.version.name": "V816",
        "ro.boot.flash.locked": "1",
        "persist.sys.timezone": "Asia/Jakarta",
        "ro.build.type": "user",
    }

    def h_getprop(self, m: re.Match) -> CommandResult:
        return CommandResult(0, self.PROPS.get(m.group("key"), "") + "\n")

    def h_getprop_all(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "".join(f"[{k}]: [{v}]\n" for k, v in self.PROPS.items()))

    def h_settings(self, m: re.Match) -> CommandResult:
        op, ns, key = m.group("op"), m.group("ns"), m.group("key")
        val = (m.group("val") or "").strip().strip("'\"")
        bucket = self.settings.setdefault(ns, {})
        if op == "get":
            return CommandResult(0, bucket.get(key, "null") + "\n")
        if op == "delete":
            bucket.pop(key, None)
            return CommandResult(0, "")
        bucket[key] = val
        self._apply_refresh_policy()
        return CommandResult(0, "")

    def _apply_refresh_policy(self) -> None:
        """Refresh rate aktif = hasil voting semua policy (mirip DisplayManager)."""
        votes: List[float] = []
        s = self.settings
        for ns in ("system", "secure", "global"):
            for key in ("peak_refresh_rate", "min_refresh_rate", "user_refresh_rate",
                        "miui_refresh_rate"):
                raw = s.get(ns, {}).get(key)
                if not raw:
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if value >= 24:     # nilai Hz langsung
                    votes.append(value)
                elif value > 0:     # index mode (Samsung/OnePlus/MIUI lama)
                    votes.append({1: 60.0, 2: 90.0, 3: 120.0, 4: 144.0}.get(int(value), 60.0))
        preferred = self.state.get("preferred_mode_fps")
        if preferred:
            votes.append(float(preferred))
        self.state["refresh_locked"] = max(votes) if votes else 60.0

    def h_dumpsys_display(self, m: re.Match) -> CommandResult:
        w, h = self.state["wm_size"]
        active = self.state["refresh_locked"]
        modes = []
        for i, fps in enumerate((60.0, 90.0, 120.0), start=1):
            modes.append(f"mSupportedModes=[id={i}, width={w}, height={h}, fps={fps:.6f}, "
                         f"supportedAlternativeRefreshRates=[60.0, 90.0, 120.0]]")
        body = "\n".join([
            "DisplayDeviceInfo{\"Built-in Screen\": uniqueId=\"local:0\", "
            f"{w} x {h}, modeId 3, defaultModeId 3, supportedModes={modes}}}",
            f"  mActiveModeId=3",
            f"  mActiveRenderFrameRate={active:.6f}",
            f"  peakRefreshRate={active:.6f}",
            f"  minRefreshRate={min(active, 60.0):.6f}",
            f"  mBaseDisplayInfo=DisplayInfo{{\"Built-in Screen\", displayId 0, "
            f"real {w} x {h}, largest app {w} x {h}, density 440, rotation 0}}",
            "  PRIORITY_MIUI_REFRESH_RATE -> RenderVote{ RefreshRateVote{ "
            f"mMinRefreshRate=0.0, mMaxRefreshRate={active:.1f} }}",
        ])
        return CommandResult(0, body + "\n")

    def h_dumpsys_battery(self, m: re.Match) -> CommandResult:
        return CommandResult(0, (
            "Current Battery Service state:\n  AC powered: false\n  USB powered: true\n"
            f"  status: 2\n  level: 78\n  scale: 100\n  voltage: 4250\n"
            f"  temperature: {int(self.battery_temp() * 10)}\n  health: 2\n"))

    def h_dumpsys_thermal(self, m: re.Match) -> CommandResult:
        st = self.thermal_status()
        names = ["NONE", "LIGHT", "MODERATE", "SEVERE", "CRITICAL", "EMERGENCY", "SHUTDOWN"]
        return CommandResult(0, f"Thermal Service Dump:\n  Current thermal status: {st} "
                                f"({names[min(st, 6)]})\n  mThrottlingStatus: {st}\n")

    def h_sf_list(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "\n".join([
            "SurfaceView[com.mojang.minecraftpe/com.mojang.minecraftpe.MainActivity]#0",
            "com.mojang.minecraftpe/com.mojang.minecraftpe.MainActivity#0",
            "StatusBar#0", "NavigationBar#0",
        ]) + "\n")

    def h_sf_gles(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "GLES: vendor=ARM, renderer=Mali-G615 MC6, "
                                "version=OpenGL ES 3.2 v1.r44p0\n")

    def h_sf_latency(self, m: re.Match) -> CommandResult:
        """Timeline frame persisten: sampel berikutnya overlap persis seperti device nyata."""
        fps, _ = self.model_fps()
        st = self.state
        timeline: List[int] = st.setdefault("sf_timeline", [])
        now_ns = int(time.time() * 1e9)
        period = max(1, int(1e9 / max(fps, 1.0)))
        last = st.get("sf_last_gen")
        if last is None:
            last = now_ns - 128 * period
        index = st.get("sf_index", 0)
        while last < now_ns and len(timeline) < 8192:
            index += 1
            # jitter deterministik dari index supaya frame overlap identik antar sampel
            jitter = ((index * 2654435761) % 2001 - 1000) * period // 22000
            timeline.append(last + jitter)
            last += period
        st["sf_last_gen"] = last
        st["sf_index"] = index
        window = sorted(timeline[-128:])
        lines = [str(max(1, int(1e9 / max(self.state["refresh_locked"], 1.0))))]
        for present in window:
            start = present - period // 2
            vsync = present - period // 3
            lines.append(f"{start}\t{vsync}\t{present}")
        return CommandResult(0, "\n".join(lines) + "\n")

    def h_framestats(self, m: re.Match) -> CommandResult:
        fps, p95 = self.model_fps()
        period = 1e9 / max(fps, 1.0)
        rows = ["---PROFILEDATA---",
                "Flags,IntendedVsync,Vsync,OldestInputEvent,NewestInputEvent,HandleInputStart,"
                "AnimationStart,PerformTraversalsStart,DrawStart,SyncQueued,SyncStart,"
                "IssueDrawCommandsStart,SwapBuffers,FrameCompleted,DequeueBufferDuration,"
                "QueueBufferDuration,GpuCompleted,"]
        base = int(time.time() * 1e9) - int(120 * period)
        for i in range(120):
            vsync = base + int(i * period)
            jitter = random.randint(-int(period * 0.08), int(period * 0.08))
            completed = vsync + int(period * 0.92) + jitter
            values = [0, vsync, vsync + 1000, -9223372036854775808, -9223372036854775808,
                      vsync + 200000, vsync + 300000, vsync + 400000, vsync + 500000,
                      completed - 900000, completed - 800000, completed - 700000,
                      completed - 200000, completed, 120000, 180000, completed]
            rows.append(",".join(str(v) for v in values) + ",")
        rows += ["---PROFILEDATA---", "", f"Total frames rendered: {120 + int(fps)}",
                 f"Janky frames: {max(0, int(120 - fps))} ({max(0, int(100 - fps)):.2f}%)",
                 f"90th percentile: {int(p95 * 0.7)}ms",
                 f"95th percentile: {int(p95)}ms",
                 f"99th percentile: {int(p95 * 1.4)}ms"]
        return CommandResult(0, "\n".join(rows) + "\n")

    def h_dumpsys_package(self, m: re.Match) -> CommandResult:
        pkg = m.group("pkg")
        if pkg.startswith("com.mojang"):
            return CommandResult(0, (
                f"Package [{pkg}]:\n    versionCode=972605020 minSdk=24 targetSdk=35\n"
                "    versionName=26.52.20\n    appCategory=game\n"
                "    primaryCpuAbi=arm64-v8a\n    codePath=/data/app/com.mojang.minecraftpe\n"
                "    dataDir=/data/data/com.mojang.minecraftpe\n"
                "    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ]\n"
                "    pkgFlags=[ HAS_CODE ]\n"))
        return CommandResult(1, "", f"Package {pkg} not found")

    def h_deviceidle(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "  com.mojang.minecraftpe\n  com.android.systemui\n")

    def h_meminfo(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "MemTotal:       12108864 kB\nMemFree:         2451230 kB\n"
                                "MemAvailable:    6921440 kB\nSwapTotal:       6291456 kB\n")

    def h_cpuinfo(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "processor\t: 0\nBogoMIPS\t: 38.40\nFeatures\t: fp asimd evtstrm\n"
                                "CPU implementer\t: 0x41\nCPU part\t: 0xd49\n")

    def h_cpu_ls(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "cpu0\ncpu1\ncpu2\ncpu3\ncpu4\ncpu5\ncpu6\ncpu7\ncpufreq\ncpuidle\n")

    def h_cpu_max(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "3350000\n")

    def h_test_writable(self, m: re.Match) -> CommandResult:
        """`[ -w <path> ] && echo WRITABLE || echo READONLY`"""
        path = re.search(r'\[\s+-w\s+"?(?P<path>[^"\s]+)"?\s+\]', m.group(0))
        if path and (path.group("path").startswith(("/sdcard", "/storage/emulated"))
                     or path.group("path") in self.fs):
            return CommandResult(0, "WRITABLE\n")
        return CommandResult(0, "READONLY\n")

    def h_cat_file(self, m: re.Match) -> CommandResult:
        path = m.group("path")
        for known, content in self.fs.items():
            if known == path or known.endswith(path.lstrip("/")):
                return CommandResult(0, content)
        return CommandResult(1, "", f"cat: {path}: No such file or directory")

    def h_ls(self, m: re.Match) -> CommandResult:
        path = m.group("path").rstrip("/")
        hits = [p for p in self.fs if p.startswith(path)]
        if hits:
            return CommandResult(0, "\n".join(os.path.basename(p) for p in hits) + "\n")
        if path in ("/sdcard", "/sdcard/Android", "/sdcard/Android/data",
                    "/sdcard/Android/data/com.mojang.minecraftpe",
                    "/sdcard/Android/data/com.mojang.minecraftpe/files",
                    "/sdcard/Android/data/com.mojang.minecraftpe/files/games",
                    "/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang",
                    "/sdcard/Android/data/com.mojang.minecraftpe/files/games/com.mojang/minecraftpe",
                    "/sdcard/Android/data/com.mojang.minecraftpe/files/resource_packs"):
            return CommandResult(0, "options.txt\n" if path.endswith("minecraftpe") else ".\n")
        return CommandResult(1, "", f"ls: {path}: No such file or directory")

    def h_pm_list(self, m: re.Match) -> CommandResult:
        packages = ["com.mojang.minecraftpe", "com.android.chrome", "com.spotify.music",
                    "com.whatsapp", "com.instagram.android", "com.tencent.mm",
                    "com.miui.analytics", "com.xiaomi.mipicks", "com.miui.daemon",
                    "com.facebook.katana", "com.shopee.id", "com.google.android.youtube"]
        if "-3" in m.group(0):
            packages = [p for p in packages if not p.startswith("com.android.")
                        and not p.startswith("com.miui") and not p.startswith("com.xiaomi")]
        return CommandResult(0, "\n".join(f"package:{p}" for p in packages) + "\n")

    def h_pm_disable(self, m: re.Match) -> CommandResult:
        self.state["bloat_disabled"].add(m.group("pkg"))
        return CommandResult(0, f"Package {m.group('pkg')} new state: disabled-user\n")

    def h_game_list_modes(self, m: re.Match) -> CommandResult:
        cur = self.state["game_mode"]
        return CommandResult(0, f"{m.group('pkg')} current mode: {cur}, "
                                "available game modes: [standard, performance, battery]\n")

    def h_game_list_configs(self, m: re.Match) -> CommandResult:
        st = self.state
        mode_num = {"standard": 1, "performance": 2, "battery": 3, "custom": 4}.get(
            st["game_mode"], 1)
        return CommandResult(0, f"{m.group('pkg')} interventions: "
                                f"[Game Mode:{mode_num}, Scaling:{st['downscale']:.2f}, "
                                f"Use Angle:{st['use_angle']}, Fps:{st['custom_fps']}]\n")

    def h_game_mode(self, m: re.Match) -> CommandResult:
        mode = m.group("mode")
        mapping = {"1": "standard", "2": "performance", "3": "battery", "4": "custom"}
        self.state["game_mode"] = mapping.get(mode, mode)
        return CommandResult(0, "")

    def h_game_mode_user(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "")

    def h_game_set(self, m: re.Match) -> CommandResult:
        args = m.group("args")
        fps = re.search(r"--fps\s+(\d+|disable)", args)
        down = re.search(r"--downscale\s+([\d\.]+|disable)", args)
        angle = re.search(r"--use-angle\s+(\w+)", args)
        if fps:
            self.state["custom_fps"] = 0 if fps.group(1) == "disable" else int(fps.group(1))
        if down:
            self.state["downscale"] = 1.0 if down.group(1) == "disable" else float(down.group(1))
        if angle:
            self.state["use_angle"] = angle.group(1).lower() in ("true", "1")
        self.state["game_mode"] = "custom"
        return CommandResult(0, "")

    def h_game_reset(self, m: re.Match) -> CommandResult:
        self.state.update(game_mode="standard", custom_fps=0, downscale=1.0, use_angle=False)
        return CommandResult(0, "")

    def h_device_config(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "mode=2,fps=0:mode=3,fps=0\n" if "get" in m.group(0) else "")

    def h_wm_size(self, m: re.Match) -> CommandResult:
        val = (m.group("val") or "").strip()
        if not val:
            w, h = self.state["wm_size"]
            return CommandResult(0, f"Physical size: {w}x{h}\nOverride size: {w}x{h}\n")
        if val == "reset":
            self.state["wm_size"] = (1220, 2712)
            return CommandResult(0, "")
        if "x" in val:
            w, _, h = val.partition("x")
            self.state["wm_size"] = (int(w), int(h))
        return CommandResult(0, "")

    def h_wm_density(self, m: re.Match) -> CommandResult:
        val = (m.group("val") or "").strip()
        if not val:
            return CommandResult(0, f"Physical density: {self.state['wm_density']}\n")
        if val == "reset":
            self.state["wm_density"] = 440
        else:
            self.state["wm_density"] = int(val)
        return CommandResult(0, "")

    def h_preferred_mode(self, m: re.Match) -> CommandResult:
        parts = m.group("args").split()
        if len(parts) >= 3:
            try:
                self.state["preferred_mode_fps"] = float(parts[2])
                self._apply_refresh_policy()
                return CommandResult(0, "")
            except ValueError:
                return CommandResult(1, "", "invalid refresh rate")
        return CommandResult(1, "", "usage: set-user-preferred-display-mode <w> <h> <fps>")

    def h_compile(self, m: re.Match) -> CommandResult:
        self.state["compiled"] = True
        return CommandResult(0, "Success\n")

    def h_dnd(self, m: re.Match) -> CommandResult:
        self.state["dnd"] = m.group("val") == "on"
        return CommandResult(0, "")

    def h_thermal_override(self, m: re.Match) -> CommandResult:
        val = int(m.group("val"))
        self.state["thermal_override"] = None if val < 0 else val
        return CommandResult(0, "")

    def h_stayon(self, m: re.Match) -> CommandResult:
        self.state["stayon"] = m.group("val") in ("true", "usb")
        return CommandResult(0, "")

    def h_force_stop(self, m: re.Match) -> CommandResult:
        self.state["stopped_packages"].add(m.group("pkg"))
        return CommandResult(0, "")

    def h_monkey(self, m: re.Match) -> CommandResult:
        return CommandResult(0, f"// Launching {m.group('pkg')}\nEvents injected: 1\n")

    def h_id(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "uid=2000(shell) gid=2000(shell) groups=2000(shell)\n")

    def h_which_su(self, m: re.Match) -> CommandResult:
        return CommandResult(1, "", "")

    def h_denied(self, m: re.Match) -> CommandResult:
        return CommandResult(1, "", "su: inaccessible or not found")

    def h_echo(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "")

    def h_noop(self, m: re.Match) -> CommandResult:
        return CommandResult(0, "")

    VALID_KEY = re.compile(r'^(gfx|mp|dvce|game|ctrl|audio|dev|store|old)_\w+$')
    VALUE_RE = re.compile(r'^[\w.\-]+$')
    SED_RE = re.compile(r"sed\s+-i\s+'s/\^(\w+):[^/]*/\1:([^/']+)/'")
    ECHO_RE = re.compile(r"echo\s+'(\w+):([\w.\-]+)'\s*>>")
    PRINTF_RE = re.compile(r"printf\s+'(\w+):([\w.\-]+)'")

    def h_options_backup(self, m: re.Match) -> CommandResult:
        parts = m.group(0).split()
        if len(parts) >= 3:
            src, dst = parts[1], parts[2]
            for known, content in list(self.fs.items()):
                if known == src or known.endswith(src.lstrip('/')):
                    self.state['options_backup'] = content
                    self.fs[dst] = content
                    return CommandResult(0, '')
            current = [v for k, v in self.fs.items() if k.endswith('options.txt')]
            if current:
                self.state['options_backup'] = current[0]
        return CommandResult(0, '')

    def h_options_write(self, m: re.Match) -> CommandResult:
        """Simulasikan penulisan options.txt (sed -i, echo >>, printf, cp)."""
        cmd = m.group(0)
        opts = self.options()

        def apply_pair(key: str, value: str) -> bool:
            if not self.VALID_KEY.match(key) or not self.VALUE_RE.match(value or ''):
                return False
            self.set_option(key, value)
            return True

        for sed in self.SED_RE.finditer(cmd):
            apply_pair(sed.group(1), sed.group(2))
        for echo in self.ECHO_RE.finditer(cmd):
            key, value = echo.group(1), echo.group(2)
            guard = 'grep -q' in cmd and key in opts
            if guard:
                continue                      # jalur sed yang dipakai, bukan fallback echo
            apply_pair(key, value)
        for pr in self.PRINTF_RE.finditer(cmd):
            apply_pair(pr.group(1), pr.group(2))
        cp = re.search(r'cp\s+(\S+)\s+(\S*options\.txt)', cmd)
        if cp:
            backup = self.state.get('options_backup')
            if isinstance(backup, str):
                self.fs[cp.group(2)] = backup
        return CommandResult(0, '')


def build_transport(serial: str = "", simulate: bool = False, adb_bin: str = "") -> Transport:
    """Pilih transport: simulator, ADB nyata, atau offline."""
    if simulate:
        return SimTransport()
    adb = AdbTransport(serial=serial, adb_bin=adb_bin)
    if adb.available():
        if not adb.serial:
            devices = adb.devices()
            if devices:
                adb.serial = devices[0]
        return adb
    return NoTransport()
