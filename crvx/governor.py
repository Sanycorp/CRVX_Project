"""Adaptive Frame Governor (AFG) - kontroler PID closed-loop.

Menahan FPS sedekat mungkin ke target dengan mengorbankan kualitas paling
sedikit mungkin, dan menurunkan target otomatis saat termal memburuk.

Urutan tuas (dari paling murah ke paling mahal secara visual):
  1. refresh rate          2. thermal/CPU governor (root)
  3. particle view         4. downscale Game Mode
  5. smooth lighting       6. render distance (chunk)
  7. resolusi sistem (wm)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Device
from .modes import FpsMode, QualityBudget

THERMAL_NAMES = ["NONE", "LIGHT", "MODERATE", "SEVERE", "CRITICAL", "EMERGENCY", "SHUTDOWN"]


@dataclass
class PidState:
    integral: float = 0.0
    prev_error: float = 0.0

    def step(self, error: float, kp: float, ki: float, kd: float, dt: float,
             i_limit: float = 60.0) -> float:
        self.integral = max(-i_limit, min(i_limit, self.integral + error * dt))
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        self.prev_error = error
        return kp * error + ki * self.integral + kd * derivative


@dataclass
class Action:
    lever: str
    detail: str
    value: str
    severity: int = 1
    command: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {"lever": self.lever, "detail": self.detail, "value": self.value,
                "severity": self.severity, "command": self.command, "reason": self.reason}


@dataclass
class GovernorDecision:
    target_fps: float
    measured_fps: float
    error: float
    output: float
    thermal: int
    thermal_name: str
    actions: List[Action] = field(default_factory=list)
    quality_index: float = 1.0
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "target_fps": round(self.target_fps, 1),
            "measured_fps": round(self.measured_fps, 1),
            "error": round(self.error, 1),
            "output": round(self.output, 2),
            "thermal": self.thermal,
            "thermal_name": self.thermal_name,
            "actions": [a.to_dict() for a in self.actions],
            "quality_index": round(self.quality_index, 2),
            "message": self.message,
        }


class AdaptiveGovernor:
    def __init__(self, dev: Device, mode: FpsMode, budget: QualityBudget,
                 capacity: Optional[float] = None):
        self.dev = dev
        self.mode = mode
        self.budget = QualityBudget(**{k: getattr(budget, k) for k in budget.__dataclass_fields__})
        self.pid = PidState()
        self.gains = mode.governor or {"kp": 0.8, "ki": 0.1, "kd": 0.3, "target_ratio": 0.92}
        self.target_ratio = float(self.gains.get("target_ratio", 0.92))
        self.ceiling = float(min(dev.panel_max_fps, dev.engine_cap_fps, mode.target_fps))
        # jangan mengejar FPS yang GPU-nya memang tidak sanggup hasilkan
        self.capacity = float(capacity) if capacity else self.ceiling
        self.target = min(float(mode.effective_target(dev)), self.capacity) * self.target_ratio
        self.history: List[float] = []
        self.step_index = 0
        self.under_ticks = 0
        self.over_ticks = 0
        self.exhausted = False

    # -- kualitas --------------------------------------------------------- #
    def quality_index(self) -> float:
        """0..1, 1 = kualitas penuh."""
        chunks_score = min(1.0, self.budget.chunks / 10.0)
        return round(0.55 * chunks_score + 0.2 * (1 if self.budget.smooth_lighting else 0.4)
                     + 0.15 * self.budget.particle_view + 0.1 * self.budget.downscale, 3)

    def _apply_quality(self, action: str) -> Optional[Action]:
        pkg = self.dev.minecraft.package or "com.mojang.minecraftpe"
        opts = (f"/sdcard/Android/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt")
        b = self.budget
        if action == "particles":
            if b.particle_view > 0.08:
                b.particle_view = round(max(0.05, b.particle_view - 0.15), 2)
                return Action("particles", "gfx_particleviewdistance", f"{b.particle_view:.2f}", 1,
                              f"sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:{b.particle_view:.2f}/' {opts}",
                              "FPS di bawah target: partikel dikurangi")
        elif action == "smooth_lighting":
            if b.smooth_lighting:
                b.smooth_lighting = False
                return Action("lighting", "gfx_smoothlighting", "0", 2,
                              f"sed -i 's/^gfx_smoothlighting:.*/gfx_smoothlighting:0/' {opts}",
                              "Smooth lighting dimatikan untuk menambah headroom GPU")
        elif action == "leaves":
            if b.transparent_leaves:
                b.transparent_leaves = False
                return Action("leaves", "gfx_transparentleaves", "0", 2,
                              f"sed -i 's/^gfx_transparentleaves:.*/gfx_transparentleaves:0/' {opts}",
                              "Daun solid mengurangi overdraw transparan")
        elif action == "downscale":
            if b.downscale > 0.6:
                b.downscale = round(max(0.6, b.downscale - 0.05), 2)
                return Action("downscale", "Game Mode backbuffer", f"{int(b.downscale * 100)}%", 3,
                              f"cmd game set --downscale {b.downscale} {pkg}",
                              "Resolusi render diturunkan (butuh restart game)")
        elif action == "render_distance":
            if b.chunks > 2:
                b.chunks -= 1
                return Action("render_distance", "gfx_viewdistance", f"{b.chunks} chunk", 4,
                              f"sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:{b.chunks * 16}/' {opts}",
                              "Render distance diturunkan - tuas paling efektif")
        elif action == "resolution":
            b.resolution_scale = round((b.resolution_scale or 1.0) - 0.1, 2)
            if b.resolution_scale < 0.7:
                b.resolution_scale = 0.7
            return Action("resolution", "wm size", f"{int(b.resolution_scale * 100)}%", 5,
                          None, "Resolusi sistem diturunkan (perlu restart game)")
        return None

    def _relax_quality(self) -> Optional[Action]:
        """Kembalikan kualitas kalau FPS sudah aman dan suhu dingin."""
        pkg = self.dev.minecraft.package or "com.mojang.minecraftpe"
        opts = (f"/sdcard/Android/data/{pkg}/files/games/com.mojang/minecraftpe/options.txt")
        b = self.budget
        if b.chunks < 12 and b.particle_view <= 0.1:
            b.chunks += 1
            b.particle_view = round(min(0.6, b.particle_view + 0.1), 2)
            return Action("quality_up", "gfx_viewdistance", f"{b.chunks} chunk", 1,
                          f"sed -i 's/^gfx_viewdistance:.*/gfx_viewdistance:{b.chunks * 16}/' {opts}",
                          "FPS stabil di atas target: kualitas dinaikkan lagi")
        if b.particle_view < 0.5:
            b.particle_view = round(min(0.6, b.particle_view + 0.1), 2)
            return Action("quality_up", "gfx_particleviewdistance", f"{b.particle_view:.2f}", 1,
                          f"sed -i 's/^gfx_particleviewdistance:.*/gfx_particleviewdistance:{b.particle_view:.2f}/' {opts}",
                          "Partikel dinaikkan sedikit karena ada headroom")
        return None

    # -- keputusan -------------------------------------------------------- #
    def update(self, fps: float, thermal: int = 0, dt: float = 2.0) -> GovernorDecision:
        self.step_index += 1
        self.history.append(fps)
        self.history = self.history[-30:]

        # target diturunkan bertahap saat termal memburuk
        thermal_target = self.target
        if thermal >= 3:
            thermal_target = min(thermal_target, 60.0)
        if thermal >= 4:
            thermal_target = min(thermal_target, 45.0)
        if thermal >= 5:
            thermal_target = min(thermal_target, 30.0)

        smoothed = sum(self.history[-3:]) / len(self.history[-3:])
        error = thermal_target - smoothed
        output = self.pid.step(error, float(self.gains.get("kp", 0.8)),
                               float(self.gains.get("ki", 0.1)),
                               float(self.gains.get("kd", 0.3)), dt)

        actions: List[Action] = []
        message = ""
        deadband = max(1.5, thermal_target * 0.04)

        # hysteresis: jangan bereaksi pada satu tick noise
        if error > deadband:
            self.under_ticks += 1
            self.over_ticks = 0
        elif error < -deadband:
            self.over_ticks += 1
            self.under_ticks = 0
        else:
            self.under_ticks = self.over_ticks = 0
        react = self.under_ticks >= 2 or error > thermal_target * 0.3
        relax = self.over_ticks >= 3

        if thermal >= 5:
            actions.append(Action("thermal", "hentikan sesi", "cooldown", 5, None,
                                  "Status termal EMERGENCY/SHUTDOWN - hentikan permainan dan "
                                  "dinginkan perangkat"))
            message = "BAHAYA PANAS: berhenti dulu."
        elif error > deadband and react:
            # butuh lebih banyak FPS -> turunkan kualitas berurutan
            if output > 24 or error > thermal_target * 0.35:
                for lever in ("render_distance", "downscale"):
                    act = self._apply_quality(lever)
                    if act:
                        actions.append(act)
                        break
            elif output > 10:
                for lever in ("smooth_lighting", "leaves", "particles"):
                    act = self._apply_quality(lever)
                    if act:
                        actions.append(act)
                        break
            else:
                act = self._apply_quality("particles")
                if act:
                    actions.append(act)
            if dev_needs_root_boost(self.dev) and not actions:
                actions.append(Action("cpu", "governor performance", "on", 2,
                                      "echo performance > /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor",
                                      "Perlu root: kunci frekuensi CPU"))
            if actions:
                self.exhausted = False
                message = (f"FPS {smoothed:.0f} di bawah target {thermal_target:.0f} - "
                           f"menurunkan beban ({len(actions)} tindakan)")
            else:
                self.exhausted = True
                message = (f"FPS {smoothed:.0f} mentok: semua tuas kualitas sudah minimum. "
                           f"Batas nyata perangkat {self.capacity:.0f} FPS - turunkan mode "
                           f"(mis. {int(min(self.capacity, 60) // 30 * 30)} FPS) untuk frame-time rata")
                actions.append(Action("mode", "turunkan mode FPS",
                                      f"{int(min(self.capacity, 90) // 30 * 30)} FPS", 3, None,
                                      "GPU/engine tidak sanggup mengejar target; lebih baik "
                                      "FPS lebih rendah tapi stabil"))
        elif error < -deadband and relax and thermal <= 1 and smoothed >= thermal_target:
            act = self._relax_quality()
            if act:
                actions.append(act)
            message = (f"FPS {smoothed:.0f} stabil di atas target - kualitas dinaikkan "
                       "kembali secara aman")
        else:
            message = (f"FPS {smoothed:.0f} dalam deadband target {thermal_target:.0f} - "
                       "tidak ada perubahan")

        return GovernorDecision(
            target_fps=thermal_target, measured_fps=smoothed, error=error, output=output,
            thermal=thermal, thermal_name=THERMAL_NAMES[min(max(thermal, 0), 6)],
            actions=actions, quality_index=self.quality_index(), message=message)


def dev_needs_root_boost(dev: Device) -> bool:
    return bool(dev.rooted or dev.shizuku)


def simulate(dev: Device, mode: FpsMode, fps_series: List[float],
             thermals: Optional[List[int]] = None) -> List[GovernorDecision]:
    """Jalankan governor pada deret FPS (untuk uji & visualisasi panel)."""
    gov = AdaptiveGovernor(dev, mode, mode.budget_for(dev))
    thermals = thermals or [0] * len(fps_series)
    decisions = []
    for i, fps in enumerate(fps_series):
        decisions.append(gov.update(fps, thermals[min(i, len(thermals) - 1)]))
    return decisions
