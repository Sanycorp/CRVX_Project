"""Telemetri FPS nyata: dumpsys SurfaceFlinger --latency + gfxinfo framestats.

Timestamp frame dikumpulkan lintas sampel lalu di-dedupe, jadi frame yang sama
tidak pernah dihitung dua kali (masalah umum pengukur FPS berbasis dumpsys).
"""

from __future__ import annotations

import math
import re
import statistics
import time
from typing import Dict, List, Optional, Tuple

from .adb import Transport
from .models import BenchResult, BenchSample

SENTINEL = 9223372036854775807


# --------------------------------------------------------------------------- #
# Parsers -> timestamp present/completed (ns)
# --------------------------------------------------------------------------- #
def parse_sf_latency(text: str) -> Tuple[float, List[int]]:
    """(refresh_period_ms, daftar timestamp present ns unik & terurut)."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return 0.0, []
    try:
        refresh_ns = float(lines[0])
    except ValueError:
        return 0.0, []
    stamps: List[int] = []
    for line in lines[1:]:
        parts = re.split(r"[\s,]+", line)
        if len(parts) < 3:
            continue
        try:
            values = [int(float(p)) for p in parts[:3]]
        except ValueError:
            continue
        if any(v <= 0 or v >= SENTINEL for v in values):
            continue
        stamps.append(values[2])          # kolom 3 = present ke hardware
    return refresh_ns / 1e6, sorted(set(stamps))


def parse_framestats(text: str) -> List[int]:
    """Timestamp FrameCompleted (ns) dari blok PROFILEDATA gfxinfo."""
    if not text or "---PROFILEDATA---" not in text:
        return []
    blocks = text.split("---PROFILEDATA---")
    if len(blocks) < 3:
        return []
    rows = [ln for ln in blocks[1].splitlines() if ln.count(",") > 8]
    if len(rows) < 2:
        return []
    header = [h.strip() for h in rows[0].split(",")]
    try:
        idx_flags = header.index("Flags")
        idx_vsync = header.index("IntendedVsync")
        idx_done = header.index("FrameCompleted")
    except ValueError:
        idx_flags, idx_vsync, idx_done = 0, 1, 13
    stamps: List[int] = []
    for row in rows[1:]:
        cols = row.split(",")
        if len(cols) <= max(idx_flags, idx_vsync, idx_done):
            continue
        try:
            flags = int(cols[idx_flags])
            vsync = int(cols[idx_vsync])
            done = int(cols[idx_done])
        except ValueError:
            continue
        if flags != 0 or done <= vsync or done <= 0 or done >= SENTINEL:
            continue
        stamps.append(done)
    return sorted(set(stamps))


def frame_times_ms(stamps_ns: List[int], max_gap_ms: float = 500.0) -> List[float]:
    """Selisih antar timestamp (ms). Gap besar (load/pause) dibuang."""
    stamps = sorted(set(stamps_ns))
    if len(stamps) < 3:
        return []
    out: List[float] = []
    for i in range(1, len(stamps)):
        delta = (stamps[i] - stamps[i - 1]) / 1e6
        if 0 < delta <= max_gap_ms:
            out.append(delta)
    return out


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    low, high = math.floor(k), math.ceil(k)
    if low == high:
        return ordered[int(k)]
    return ordered[low] * (high - k) + ordered[high] * (k - low)


def compute_stats(frame_times: List[float], refresh_ms: float = 0.0,
                  target_fps: float = 60.0) -> Dict[str, float]:
    if not frame_times:
        return {}
    total_ms = sum(frame_times)
    duration_s = total_ms / 1000.0
    fps = len(frame_times) / duration_s if duration_s > 0 else 0.0
    target_ft = 1000.0 / max(target_fps, 1.0)
    ref = refresh_ms or target_ft
    inst_fps = [1000.0 / ft for ft in frame_times]

    jank = sum(1 for ft in frame_times if ft > ref * 1.6)
    stutter = sum(max(0.0, ft - target_ft) for ft in frame_times) / total_ms * 100.0
    ft_avg = statistics.fmean(frame_times)
    deviation = statistics.pstdev(frame_times) if len(frame_times) > 1 else 0.0
    ft_p95, ft_p99 = percentile(frame_times, 0.95), percentile(frame_times, 0.99)

    consistency = max(0.0, 1.0 - (deviation / max(ft_avg, 0.001)))
    ratio = min(1.0, fps / max(target_fps, 1.0))
    low_ratio = (percentile(inst_fps, 0.01) / max(fps, 0.001)) if inst_fps else 1.0
    smoothness = max(0.0, min(100.0, 100 * (0.5 * ratio + 0.32 * consistency
                                             + 0.18 * min(1.0, low_ratio))))
    return {
        "fps": fps,
        "frames": len(frame_times),
        "duration_s": duration_s,
        "ft_avg_ms": ft_avg,
        "ft_p50_ms": percentile(frame_times, 0.50),
        "ft_p95_ms": ft_p95,
        "ft_p99_ms": ft_p99,
        "fps_median": percentile(inst_fps, 0.50),
        "fps_p1": percentile(inst_fps, 0.01),
        "fps_p5": percentile(inst_fps, 0.05),
        "fps_p95": percentile(inst_fps, 0.95),
        "fps_max": max(inst_fps),
        "jank": jank,
        "stutter_index": stutter,
        "smoothness": smoothness,
        "deviation_ms": deviation,
    }


# --------------------------------------------------------------------------- #
# Benchmarker
# --------------------------------------------------------------------------- #
class Benchmarker:
    """Mengambil sampel frame berulang selama game berjalan."""

    LAYER_HINTS = ("SurfaceView", "com.mojang", "MainActivity")

    def __init__(self, transport: Transport, package: str = "com.mojang.minecraftpe"):
        self.transport = transport
        self.package = package or "com.mojang.minecraftpe"
        self._layer: Optional[str] = None

    def find_layer(self) -> Optional[str]:
        res = self.transport.shell("dumpsys SurfaceFlinger --list")
        if not res.ok:
            return None
        candidates = [ln.strip() for ln in res.out.splitlines() if ln.strip()]
        for hint in self.LAYER_HINTS:
            for name in candidates:
                if hint in name:
                    self._layer = name
                    return name
        return None

    def thermal(self) -> Tuple[int, float]:
        res = self.transport.shell("dumpsys thermalservice")
        match = re.search(r"(?:thermal status|status):\s*(\d+)", res.out or "")
        status = int(match.group(1)) if match else 0
        batt = self.transport.shell("dumpsys battery")
        match = re.search(r"temperature:\s*(\d+)", batt.out or "")
        temp = int(match.group(1)) / 10.0 if match else 0.0
        return status, temp

    def sample_once(self) -> Tuple[List[int], float, str]:
        """(timestamp ns, refresh ms, sumber)."""
        layer = self._layer or self.find_layer()
        if layer:
            res = self.transport.shell(f"dumpsys SurfaceFlinger --latency '{layer}'")
            refresh, stamps = parse_sf_latency(res.out)
            if stamps:
                return stamps, refresh, "SurfaceFlinger --latency"
        res = self.transport.shell(f"dumpsys gfxinfo {self.package} framestats")
        stamps = parse_framestats(res.out)
        if stamps:
            return stamps, 0.0, "gfxinfo framestats"
        return [], 0.0, "unavailable"

    def _result(self, stamps: List[int], refresh: float, source: str, label: str,
                duration: float, samples: List[BenchSample], target_fps: float,
                thermal_start: int, temp_start: float) -> BenchResult:
        frame_times = frame_times_ms(stamps)
        stats = compute_stats(frame_times, refresh, target_fps)
        thermal_end, temp_end = self.thermal()
        notes: List[str] = []
        if not stats:
            notes.append("Tidak ada data frame. Pastikan Minecraft berjalan di depan layar "
                         "(bukan di menu utama) lalu ulangi.")
        return BenchResult(
            label=label, source=source, duration_s=round(duration, 1),
            frames=int(stats.get("frames", 0)), samples=samples,
            fps_avg=round(stats.get("fps", 0.0), 1),
            fps_p1=round(stats.get("fps_p1", 0.0), 1),
            fps_p5=round(stats.get("fps_p5", 0.0), 1),
            fps_p50=round(stats.get("fps_median", 0.0), 1),
            fps_p95=round(stats.get("fps_p95", 0.0), 1),
            fps_max=round(stats.get("fps_max", 0.0), 1),
            frametime_avg_ms=round(stats.get("ft_avg_ms", 0.0), 2),
            frametime_p95_ms=round(stats.get("ft_p95_ms", 0.0), 2),
            jank=int(stats.get("jank", 0)),
            stutter_index=round(stats.get("stutter_index", 0.0), 2),
            smoothness_score=round(stats.get("smoothness", 0.0), 1),
            thermal_start=thermal_start, thermal_end=thermal_end,
            temp_start=temp_start, temp_end=temp_end, notes=notes)

    def run(self, duration_s: float = 12.0, interval_s: float = 1.0, label: str = "run",
            target_fps: float = 60.0, progress=None) -> BenchResult:
        stamps: List[int] = []
        seen = set()
        samples: List[BenchSample] = []
        source, refresh = "unavailable", 0.0
        started = time.time()
        thermal_start, temp_start = self.thermal()
        while time.time() - started < duration_s:
            new_stamps, ref, src = self.sample_once()
            fresh = [s for s in new_stamps if s not in seen]
            if fresh:
                seen.update(fresh)
                stamps.extend(fresh)
                source, refresh = src, (ref or refresh)
                times = frame_times_ms(sorted(stamps)[-140:])
                inst = (len(times) / (sum(times) / 1000.0)) if times else 0.0
                thermal_now, temp_now = self.thermal()
                samples.append(BenchSample(
                    t=round(time.time() - started, 2), fps=round(inst, 1),
                    frametime_ms=round(statistics.fmean(times), 2) if times else 0.0,
                    thermal=thermal_now, battery_temp=temp_now))
            if progress is not None:
                progress(len(samples))
            time.sleep(max(0.05, interval_s))
        stamps.sort()
        return self._result(stamps, refresh, source, label, time.time() - started,
                            samples, target_fps, thermal_start, temp_start)

    def quick(self, target_fps: float = 60.0, label: str = "quick") -> BenchResult:
        stamps, refresh, source = self.sample_once()
        return self._result(sorted(stamps), refresh, source, label, 0.0, [],
                            target_fps, *self.thermal())


def compare(before: BenchResult, after: BenchResult) -> Dict[str, object]:
    def delta(a: float, b: float) -> float:
        return round(b - a, 1)

    fps_gain = delta(before.fps_avg, after.fps_avg)
    pct = round((after.fps_avg - before.fps_avg) / before.fps_avg * 100, 1) if before.fps_avg else 0.0
    verdict = "NAIK" if fps_gain > 0.5 else ("TURUN" if fps_gain < -0.5 else "SAMA")
    return {
        "fps_gain": fps_gain,
        "fps_gain_pct": pct,
        "fps_before": before.fps_avg,
        "fps_after": after.fps_avg,
        "p1_before": before.fps_p1,
        "p1_after": after.fps_p1,
        "p5_before": before.fps_p5,
        "p5_after": after.fps_p5,
        "frametime_gain_ms": delta(before.frametime_avg_ms, after.frametime_avg_ms),
        "jank_gain": int(after.jank - before.jank),
        "stutter_gain": delta(before.stutter_index, after.stutter_index),
        "smoothness_gain": delta(before.smoothness_score, after.smoothness_score),
        "thermal_delta": after.thermal_end - before.thermal_end,
        "temp_gain_c": delta(before.temp_end, after.temp_end),
        "verdict": verdict,
        "before": before.to_dict(),
        "after": after.to_dict(),
    }
