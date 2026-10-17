"""Core data model of the TurboFrame engine."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Risk(str, Enum):
    SAFE = "safe"            # reversible, no visual change, no stability risk
    MODERATE = "moderate"    # visual change or battery/heat cost
    ADVANCED = "advanced"    # resolution/governor changes, needs care
    ROOT = "root"            # needs root/Shizuku, touches kernel state

    @property
    def order(self) -> int:
        return {"safe": 0, "moderate": 1, "advanced": 2, "root": 3}[self.value]


class Category(str, Enum):
    DISPLAY = "display"
    GAMEMODE = "gamemode"
    MINECRAFT = "minecraft"
    RESOLUTION = "resolution"
    RUNTIME = "runtime"
    SYSTEM = "system"
    THERMAL = "thermal"
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    PACK = "pack"


class Vendor(str, Enum):
    XIAOMI = "xiaomi"
    SAMSUNG = "samsung"
    ONEPLUS = "oneplus"
    OPPO = "oppo"
    REALME = "realme"
    VIVO = "vivo"
    IQOO = "iqoo"
    ASUS = "asus"
    GOOGLE = "google"
    MOTOROLA = "motorola"
    HONOR = "honor"
    HUAWEI = "huawei"
    NUBIA = "nubia"
    TECNO = "tecno"
    INFINIX = "infinix"
    POCO = "poco"
    REDMI = "redmi"
    NOTHING = "nothing"
    SONY = "sony"
    GENERIC = "generic"


VENDOR_ALIASES: Dict[str, Vendor] = {
    "xiaomi": Vendor.XIAOMI, "redmi": Vendor.REDMI, "poco": Vendor.POCO,
    "blackshark": Vendor.XIAOMI, "black shark": Vendor.XIAOMI,
    "samsung": Vendor.SAMSUNG, "oneplus": Vendor.ONEPLUS, "oppo": Vendor.OPPO,
    "realme": Vendor.REALME, "vivo": Vendor.VIVO, "iqoo": Vendor.IQOO,
    "asus": Vendor.ASUS, "rog": Vendor.ASUS, "google": Vendor.GOOGLE,
    "motorola": Vendor.MOTOROLA, "honor": Vendor.HONOR, "huawei": Vendor.HUAWEI,
    "nubia": Vendor.NUBIA, "redmagic": Vendor.NUBIA, "tecno": Vendor.TECNO,
    "infinix": Vendor.INFINIX, "nothing": Vendor.NOTHING, "sony": Vendor.SONY,
}


# --------------------------------------------------------------------------- #
# Device
# --------------------------------------------------------------------------- #
@dataclass
class DisplayMode:
    width: int
    height: int
    fps: float

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class MinecraftInstall:
    installed: bool = False
    package: str = "com.mojang.minecraftpe"
    version_name: str = ""
    version_code: str = ""
    data_root: str = ""
    options_path: str = ""
    writable: bool = False
    root_needed: bool = False
    current_options: Dict[str, str] = field(default_factory=dict)

    @property
    def major(self) -> Tuple[int, ...]:
        parts: List[int] = []
        for chunk in self.version_name.split(".")[:4]:
            digits = "".join(c for c in chunk if c.isdigit())
            if digits:
                parts.append(int(digits))
        return tuple(parts) or (0,)

    @property
    def is_2026_numbering(self) -> bool:
        """Bedrock switched to year.drop numbering (26.x) in 2026."""
        return bool(self.major) and self.major[0] >= 20


@dataclass
class Device:
    serial: str = ""
    simulated: bool = False
    transport: str = "adb"          # adb | sim | offline
    model: str = "unknown"
    manufacturer: str = ""
    brand: str = ""
    codename: str = ""
    board_platform: str = ""
    soc_model: str = ""
    soc_manufacturer: str = ""
    android_sdk: int = 0
    android_release: str = ""
    security_patch: str = ""
    abi: str = ""
    cpu_cores: int = 0
    cpu_max_khz: int = 0
    ram_mb: int = 0
    gpu_renderer: str = ""
    vendor: Vendor = Vendor.GENERIC
    rooted: bool = False
    shizuku: bool = False
    thermal_status: int = 0         # 0 none .. 6 shutdown
    battery_temp_c: float = 0.0
    battery_level: int = 100
    charging: bool = False
    display_modes: List[DisplayMode] = field(default_factory=list)
    active_fps: float = 60.0
    panel_max_fps: float = 60.0
    game_mode_supported: bool = False
    game_mode_current: str = ""
    game_modes_available: List[str] = field(default_factory=list)
    engine_cap_fps: int = 60        # honest Bedrock-Android ceiling for this device
    engine_cap_reason: str = ""
    minecraft: MinecraftInstall = field(default_factory=MinecraftInstall)
    extras: Dict[str, Any] = field(default_factory=dict)

    # -- derived ---------------------------------------------------------- #
    @property
    def refresh_rates(self) -> List[float]:
        seen: List[float] = []
        for mode in self.display_modes:
            if mode.fps not in seen:
                seen.append(round(mode.fps, 2))
        return sorted(seen, reverse=True)

    def supports_refresh(self, fps: float) -> bool:
        return any(abs(r - fps) < 0.6 for r in self.refresh_rates)

    def native_mode_for(self, fps: float) -> Optional[DisplayMode]:
        best: Optional[DisplayMode] = None
        for mode in self.display_modes:
            if abs(mode.fps - fps) < 0.6:
                if best is None or mode.pixels > best.pixels:
                    best = mode
        return best

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["vendor"] = self.vendor.value
        data["refresh_rates"] = self.refresh_rates
        data["minecraft"]["major"] = list(self.minecraft.major)
        return data


# --------------------------------------------------------------------------- #
# Commands / rules
# --------------------------------------------------------------------------- #
@dataclass
class Command:
    shell: str
    root: bool = False
    undo: Optional[str] = None
    label: str = ""
    capture: bool = False       # keep stdout for verification
    optional: bool = True       # failure is tolerated (vendor-specific keys)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Requirements:
    min_sdk: Optional[int] = None
    max_sdk: Optional[int] = None
    root: bool = False
    shizuku: bool = False
    game_mode: bool = False
    display_fps: Optional[float] = None
    vendors: Sequence[Vendor] = ()
    exclude_vendors: Sequence[Vendor] = ()
    minecraft: bool = False
    minecraft_writable: bool = False
    custom: Optional[Any] = None      # Callable[[Device], bool]

    def unmet(self, dev: Device) -> List[str]:
        why: List[str] = []
        if self.min_sdk and dev.android_sdk < self.min_sdk:
            why.append(f"butuh Android SDK >= {self.min_sdk} (punya {dev.android_sdk})")
        if self.max_sdk and dev.android_sdk > self.max_sdk:
            why.append(f"hanya untuk SDK <= {self.max_sdk}")
        if self.root and not dev.rooted:
            why.append("butuh ROOT")
        if self.shizuku and not (dev.shizuku or dev.rooted):
            why.append("butuh Shizuku/ROOT")
        if self.game_mode and not dev.game_mode_supported:
            why.append("Game Mode API tidak didukung")
        if self.display_fps and not dev.supports_refresh(self.display_fps):
            why.append(f"layar tidak mendukung {self.display_fps:g} Hz")
        if self.vendors and dev.vendor not in self.vendors:
            why.append(f"khusus vendor {[v.value for v in self.vendors]}")
        if self.exclude_vendors and dev.vendor in self.exclude_vendors:
            why.append(f"tidak untuk vendor {dev.vendor.value}")
        if self.minecraft and not dev.minecraft.installed:
            why.append("Minecraft tidak terdeteksi")
        if self.minecraft_writable and not dev.minecraft.writable:
            why.append("options.txt tidak bisa ditulis")
        if self.custom is not None and not self.custom(dev):
            why.append("kondisi perangkat tidak terpenuhi")
        return why


@dataclass
class Gain:
    """Expected effect. fps/stability in absolute points, others in percent."""
    fps: float = 0.0
    stability: float = 0.0
    frametime_ms: float = 0.0
    gpu_load: float = 0.0
    battery: float = 0.0
    heat: float = 0.0
    input_latency_ms: float = 0.0
    confidence: float = 0.6

    def scaled(self, factor: float) -> "Gain":
        return Gain(
            fps=self.fps * factor,
            stability=self.stability * factor,
            frametime_ms=self.frametime_ms * factor,
            gpu_load=self.gpu_load * factor,
            battery=self.battery * factor,
            heat=self.heat * factor,
            input_latency_ms=self.input_latency_ms * factor,
            confidence=self.confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Verify:
    command: str
    expect: str = ""
    mode: str = "contains"      # contains | equals | number_gte | nonempty


@dataclass
class Rule:
    id: str
    title: str
    category: Category
    risk: Risk
    description: str
    commands: List[Command] = field(default_factory=list)
    requirements: Requirements = field(default_factory=Requirements)
    gain: Gain = field(default_factory=Gain)
    verify: Optional[Verify] = None
    tags: List[str] = field(default_factory=list)
    dynamic: Optional[Any] = None       # Callable[[Device, FpsMode], Optional[Rule]]

    def unmet(self, dev: Device) -> List[str]:
        return self.requirements.unmet(dev)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "risk": self.risk.value,
            "description": self.description,
            "commands": [c.to_dict() for c in self.commands],
            "gain": self.gain.to_dict(),
            "tags": self.tags,
            "verify": asdict(self.verify) if self.verify else None,
        }


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #
@dataclass
class PlanStep:
    rule: Rule
    commands: List[Command]
    applied: bool = False
    ok: bool = False
    output: str = ""
    error: str = ""
    verify_result: str = ""
    verify_passed: Optional[bool] = None
    skipped_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule.to_dict(),
            "commands": [c.to_dict() for c in self.commands],
            "applied": self.applied,
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "verify_result": self.verify_result,
            "verify_passed": self.verify_passed,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class Projection:
    target_fps: int
    reachable_fps: float
    ceiling_fps: float
    ceiling_reason: str
    frametime_ms: float
    stability: float
    confidence: float
    battery_pct: float
    heat: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: float = field(default_factory=time.time)
    mode_id: str = ""
    mode_name: str = ""
    device: Optional[Device] = None
    steps: List[PlanStep] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    projection: Optional[Projection] = None
    risk_ceiling: Risk = Risk.SAFE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created": self.created,
            "mode_id": self.mode_id,
            "mode_name": self.mode_name,
            "device": self.device.to_dict() if self.device else None,
            "steps": [s.to_dict() for s in self.steps],
            "skipped": self.skipped,
            "projection": self.projection.to_dict() if self.projection else None,
            "risk_ceiling": self.risk_ceiling.value,
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Journal (undo safety net)
# --------------------------------------------------------------------------- #
@dataclass
class JournalEntry:
    ts: float
    plan_id: str
    rule_id: str
    command: str
    undo: Optional[str]
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Benchmark
# --------------------------------------------------------------------------- #
@dataclass
class BenchSample:
    t: float
    fps: float
    frametime_ms: float
    thermal: int = 0
    cpu_pct: float = 0.0
    battery_temp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchResult:
    label: str
    source: str
    duration_s: float
    frames: int
    samples: List[BenchSample] = field(default_factory=list)
    fps_avg: float = 0.0
    fps_p1: float = 0.0
    fps_p5: float = 0.0
    fps_p50: float = 0.0
    fps_p95: float = 0.0
    fps_max: float = 0.0
    frametime_avg_ms: float = 0.0
    frametime_p95_ms: float = 0.0
    jank: int = 0
    stutter_index: float = 0.0
    smoothness_score: float = 0.0
    thermal_start: int = 0
    thermal_end: int = 0
    temp_start: float = 0.0
    temp_end: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
