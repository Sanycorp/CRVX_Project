"""Definisi mode FPS: 60 / 90 / 120 / 144 + AUTO.

Setiap mode membawa "quality budget" yang diskalakan menurut tier perangkat,
jadi mode 120 di chipset entry tidak akan dipaksakan sama seperti di flagship.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Device


@dataclass
class QualityBudget:
    chunks: int                      # render distance (chunk) -> gfx_viewdistance = chunks*16
    particle_view: float             # gfx_particleviewdistance 0..1
    smooth_lighting: bool
    transparent_leaves: bool
    fancy_skies: bool
    msaa: int                        # 1 = off
    max_framerate: int               # 0 = unlimited
    vsync: bool
    downscale: float                 # WindowManager backbuffer scale (Game Mode API)
    resolution_scale: Optional[float] = None   # opsional: ubah wm size
    fog_cut: bool = False
    fov: int = 66

    @property
    def viewdistance_blocks(self) -> int:
        return max(80, min(1536, self.chunks * 16))

    def options(self) -> Dict[str, str]:
        return {
            "gfx_viewdistance": str(self.viewdistance_blocks),
            "gfx_particleviewdistance": f"{self.particle_view:.2f}",
            "gfx_smoothlighting": "1" if self.smooth_lighting else "0",
            "gfx_transparentleaves": "1" if self.transparent_leaves else "0",
            "gfx_fancyskies": "1" if self.fancy_skies else "0",
            "gfx_msaa": str(self.msaa),
            "gfx_max_framerate": str(self.max_framerate),
            "gfx_vsync": "1" if self.vsync else "0",
            "gfx_multithreaded_renderer": "1",
            "gfx_field_of_view": str(self.fov),
            "gfx_max_framerate_advanced": "0",
        }


@dataclass
class FpsMode:
    id: str
    name: str
    tagline: str
    target_fps: int
    refresh_target: float
    accent: str
    budgets: Dict[int, QualityBudget]      # tier 1..5
    risk_ceiling: str = "moderate"         # safe | moderate | advanced | root
    thermal_policy: str = "balanced"       # balanced | aggressive | max
    governor: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def budget_for(self, dev: Device) -> QualityBudget:
        tier = int(dev.extras.get("tier", 3))
        budget = self.budgets.get(tier) or self.budgets.get(3) or list(self.budgets.values())[0]
        # jangan minta lebih dari yang layar/engine sanggup tampilkan
        ceiling = min(dev.panel_max_fps, dev.engine_cap_fps)
        if self.target_fps > ceiling:
            budget.chunks = max(2, budget.chunks - 1)
            budget.downscale = min(0.85, budget.downscale or 0.85)
        tier = int(dev.extras.get("tier", 3))
        if tier <= 2 and self.target_fps >= 120 and budget.resolution_scale is None:
            budget.resolution_scale = 0.85 if tier == 2 else 0.8
        return budget

    def effective_target(self, dev: Device) -> int:
        ceiling = min(int(dev.panel_max_fps), dev.engine_cap_fps)
        return max(30, min(self.target_fps, ceiling))

    def to_dict(self, dev: Optional[Device] = None) -> Dict[str, object]:
        data: Dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "target_fps": self.target_fps,
            "refresh_target": self.refresh_target,
            "accent": self.accent,
            "risk_ceiling": self.risk_ceiling,
            "thermal_policy": self.thermal_policy,
            "notes": self.notes,
        }
        if dev is not None:
            budget = self.budget_for(dev)
            data["effective_target"] = self.effective_target(dev)
            data["budget"] = {
                "chunks": budget.chunks,
                "viewdistance": budget.viewdistance_blocks,
                "particle_view": budget.particle_view,
                "smooth_lighting": budget.smooth_lighting,
                "transparent_leaves": budget.transparent_leaves,
                "fancy_skies": budget.fancy_skies,
                "msaa": budget.msaa,
                "max_framerate": budget.max_framerate,
                "vsync": budget.vsync,
                "downscale": budget.downscale,
                "resolution_scale": budget.resolution_scale,
                "options": budget.options(),
            }
            data["feasible"] = dev.panel_max_fps + 0.6 >= self.target_fps
            data["engine_capped"] = self.target_fps > dev.engine_cap_fps
        return data


def _budgets(spec: Dict[int, tuple]) -> Dict[int, QualityBudget]:
    out: Dict[int, QualityBudget] = {}
    for tier, values in spec.items():
        chunks, particle, smooth, leaves, skies, msaa, maxfps, vsync, downscale = values
        out[tier] = QualityBudget(
            chunks=chunks, particle_view=particle, smooth_lighting=smooth,
            transparent_leaves=leaves, fancy_skies=skies, msaa=msaa,
            max_framerate=maxfps, vsync=vsync, downscale=downscale)
    return out


MODES: Dict[str, FpsMode] = {
    "60": FpsMode(
        id="60", name="MODE 60 FPS", tagline="STABIL · Hemat baterai · frame-time paling rata",
        target_fps=60, refresh_target=60.0, accent="#38bdf8",
        budgets=_budgets({
            1: (4, 0.15, False, False, False, 1, 60, True, 0.75),
            2: (5, 0.25, False, False, True, 1, 60, True, 0.85),
            3: (7, 0.40, True, False, True, 1, 60, True, 1.0),
            4: (9, 0.55, True, True, True, 2, 60, True, 1.0),
            5: (11, 0.70, True, True, True, 4, 60, True, 1.0),
        }),
        risk_ceiling="safe", thermal_policy="balanced",
        governor={"kp": 0.6, "ki": 0.08, "kd": 0.25, "target_ratio": 0.95},
        notes=[
            "V-Sync aktif = frame pacing paling mulus, tanpa tearing.",
            "Paling dingin & paling irit: cocok untuk main lama.",
        ],),

    "90": FpsMode(
        id="90", name="MODE 90 FPS", tagline="SMOOTH · keseimbangan FPS, suhu, dan visual",
        target_fps=90, refresh_target=90.0, accent="#a78bfa",
        budgets=_budgets({
            1: (3, 0.10, False, False, False, 1, 90, False, 0.70),
            2: (4, 0.20, False, False, True, 1, 90, False, 0.80),
            3: (6, 0.35, False, False, True, 1, 90, False, 0.90),
            4: (7, 0.45, True, False, True, 1, 90, False, 1.0),
            5: (9, 0.60, True, True, True, 2, 90, False, 1.0),
        }),
        risk_ceiling="moderate", thermal_policy="aggressive",
        governor={"kp": 0.75, "ki": 0.10, "kd": 0.30, "target_ratio": 0.93},
        notes=[
            "Butuh layar 90 Hz ke atas. Kalau panel hanya 60 Hz, engine turun ke mode 60.",
            "V-Sync mati + cap 90 = input latency lebih rendah.",
        ],),

    "120": FpsMode(
        id="120", name="MODE 120 FPS", tagline="ULTRA · kompetitif · latency sentuh minimum",
        target_fps=120, refresh_target=120.0, accent="#f472b6",
        budgets=_budgets({
            1: (2, 0.05, False, False, False, 1, 120, False, 0.60),
            2: (3, 0.15, False, False, False, 1, 120, False, 0.70),
            3: (5, 0.25, False, False, True, 1, 120, False, 0.85),
            4: (6, 0.35, False, False, True, 1, 120, False, 0.90),
            5: (8, 0.45, True, False, True, 1, 120, False, 1.0),
        }),
        risk_ceiling="advanced", thermal_policy="aggressive",
        governor={"kp": 0.9, "ki": 0.12, "kd": 0.35, "target_ratio": 0.90},
        notes=[
            "Bedrock Android masih dikunci 60 FPS di banyak perangkat walau layar 120 Hz.",
            "Engine membuka kunci 90/120 hanya pada kombinasi SoC + build yang didukung.",
            "Semua tuas dibuka: refresh rate, Game Mode API, resolusi render, termal.",
        ],),

    "144": FpsMode(
        id="144", name="MODE 144/165 FPS", tagline="EXTREME · gaming phone · semua batas dilepas",
        target_fps=144, refresh_target=144.0, accent="#fbbf24",
        budgets=_budgets({
            1: (2, 0.05, False, False, False, 1, 144, False, 0.55),
            2: (3, 0.10, False, False, False, 1, 144, False, 0.60),
            3: (4, 0.15, False, False, False, 1, 144, False, 0.75),
            4: (5, 0.25, False, False, True, 1, 144, False, 0.85),
            5: (7, 0.35, False, False, True, 1, 0, False, 0.90),
        }),
        risk_ceiling="root", thermal_policy="max",
        governor={"kp": 1.1, "ki": 0.15, "kd": 0.4, "target_ratio": 0.88},
        notes=[
            "Hanya masuk akal di ROG Phone / RedMagic / iQOO panel 144-165 Hz.",
            "Frame rate tak terbatas + resolusi render diturunkan = GPU lega.",
            "Suhu naik cepat; governor akan menurunkan target otomatis.",
        ],),
}


def auto_mode(dev: Device) -> FpsMode:
    """Pilih mode terbaik menurut kemampuan nyata perangkat."""
    ceiling = min(int(dev.panel_max_fps), dev.engine_cap_fps)
    tier = int(dev.extras.get("tier", 3))
    if ceiling >= 144 and tier >= 4:
        return MODES["144"]
    if ceiling >= 120 and tier >= 3:
        return MODES["120"]
    if ceiling >= 90 and tier >= 2:
        return MODES["90"]
    return MODES["60"]


def get_mode(mode_id: str, dev: Optional[Device] = None) -> FpsMode:
    key = (mode_id or "auto").strip().lower()
    if key in ("auto", "", "adaptive"):
        if dev is None:
            return MODES["120"]
        return auto_mode(dev)
    for fps in ("144", "120", "90", "60"):
        if key.startswith(fps):
            return MODES[fps]
    return MODES.get(key, MODES["120"])


def all_modes(dev: Optional[Device] = None) -> List[Dict[str, object]]:
    return [MODES[key].to_dict(dev) for key in ("60", "90", "120", "144")]
