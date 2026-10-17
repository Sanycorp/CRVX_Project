"""Engine inti: rencana (plan), eksekusi (apply), pembatalan (undo), jurnal."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional

from .adb import Transport
from .models import (Category, Command, Device, JournalEntry, Plan, PlanStep,
                     Projection, Risk, Rule)
from .modes import FpsMode, QualityBudget, get_mode
from .rules import build_catalog

CRVX_HOME = os.environ.get("CRVX_HOME") or os.path.expanduser("~/.crvx")
JOURNAL_PATH = os.path.join(CRVX_HOME, "journal.json")
PLANS_DIR = os.path.join(CRVX_HOME, "plans")
BACKUP_DIR = os.path.join(CRVX_HOME, "backups")

CATEGORY_ORDER = [
    Category.MINECRAFT, Category.SYSTEM, Category.DISPLAY, Category.GAMEMODE,
    Category.RESOLUTION, Category.RUNTIME, Category.MEMORY, Category.THERMAL,
    Category.CPU, Category.GPU, Category.PACK,
]

RULE_ORDER = {
    "minecraft.backup": 0,
    "system.power_saver_off": 10,
    "system.animations": 11,
    "display.preferred_mode": 20,
    "display.refresh.system": 21,
    "display.refresh.secure": 22,
    "display.refresh.miui": 23,
    "display.refresh.oneui": 23,
    "display.refresh.oplus": 23,
    "samsung.game_launcher": 24,
    "display.blurs_off": 25,
    "display.brightness_fixed": 26,
    "gamemode.performance": 30,
    "gamemode.custom_fps": 31,
    "gamemode.downscale": 32,
    "gamemode.overlay_config": 33,
    "resolution.wm_scale": 40,
    "minecraft.options": 50,
    "minecraft.vsync_unlock": 51,
    "runtime.art_compile": 60,
    "runtime.doze_whitelist": 61,
    "memory.trim": 62,
    "runtime.focus": 63,
    "thermal.override": 70,
    "cpu.governor": 71,
    "gpu.governor": 72,
    "cpu.core_ctl": 73,
    "memory.kernel": 74,
    "thermal.kernel": 75,
    "pack.fog_cut": 80,
    "minecraft.reload": 99,
}

BASELINE_BY_TIER = {1: 21.0, 2: 29.0, 3: 42.0, 4: 55.0, 5: 60.0}


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #
class Journal:
    """Catatan setiap perubahan + perintah pembaliknya."""

    def __init__(self, path: str = JOURNAL_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def load(self) -> List[Dict[str, object]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, entries: List[Dict[str, object]]) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2, ensure_ascii=False)

    def append(self, entries: List[JournalEntry]) -> None:
        data = self.load()
        data.extend(e.to_dict() for e in entries)
        self.save(data)

    def take(self, plan_id: Optional[str] = None) -> List[Dict[str, object]]:
        data = self.load()
        if plan_id is None:
            self.save([])
            return data
        keep = [e for e in data if e.get("plan_id") != plan_id]
        self.save(keep)
        return [e for e in data if e.get("plan_id") == plan_id]


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #
class Planner:
    def __init__(self, transport: Transport, journal: Optional[Journal] = None):
        self.transport = transport
        self.journal = journal or Journal()

    # -- perencanaan ------------------------------------------------------ #
    def plan(self, dev: Device, mode_id: str = "120",
             risk: Optional[str] = None, with_pack: bool = False) -> Plan:
        mode = get_mode(mode_id, dev)
        budget = mode.budget_for(dev)
        if with_pack:
            budget = QualityBudget(**{**budget.__dict__, "fog_cut": True})

        ceiling_name = risk or mode.risk_ceiling
        ceiling = Risk(ceiling_name) if ceiling_name in Risk.__members__.values() else Risk.MODERATE
        ceiling_order = ceiling.order

        catalog = build_catalog(dev, mode, budget)
        steps: List[PlanStep] = []
        skipped: List[Dict[str, object]] = []

        for rule in catalog:
            reasons = rule.unmet(dev)
            if rule.category == Category.RESOLUTION and budget.resolution_scale is None:
                reasons = reasons or ["resolusi sistem tidak diturunkan pada mode ini"]
            if reasons:
                skipped.append({"rule": rule.to_dict(), "reasons": reasons})
                continue
            if rule.risk.order > ceiling_order:
                skipped.append({"rule": rule.to_dict(),
                                "reasons": [f"risiko {rule.risk.value} di atas batas "
                                            f"{ceiling.value} (pakai --risk {rule.risk.value})"]})
                continue
            steps.append(PlanStep(rule=rule, commands=list(rule.commands)))

        steps.sort(key=lambda s: (RULE_ORDER.get(s.rule.id, 500), s.rule.id))
        plan = Plan(mode_id=mode.id, mode_name=mode.name, device=dev, steps=steps,
                    skipped=skipped, risk_ceiling=ceiling)
        plan.projection = self.project(dev, mode, budget, plan)
        os.makedirs(PLANS_DIR, exist_ok=True)
        with open(os.path.join(PLANS_DIR, f"{plan.id}.json"), "w", encoding="utf-8") as fh:
            json.dump(plan.to_dict(), fh, indent=2, ensure_ascii=False)
        return plan

    # -- proyeksi --------------------------------------------------------- #
    def project(self, dev: Device, mode: FpsMode, budget: QualityBudget,
                plan: Plan) -> Projection:
        tier = int(dev.extras.get("tier", 3))
        baseline = BASELINE_BY_TIER.get(tier, 42.0)
        opts = dev.minecraft.current_options
        if opts:
            chunks = float(opts.get("gfx_viewdistance", "256") or 256) / 16.0
            baseline *= max(0.6, min(1.25, 1.25 - 0.03 * chunks))
            if opts.get("gfx_msaa", "1") in ("4", "8", "16"):
                baseline *= 0.9
        baseline = max(12.0, baseline)

        ceiling = float(min(dev.panel_max_fps or 60, dev.engine_cap_fps, mode.target_fps))
        fps_gain = 0.0
        stability_gain = 0.0
        latency_gain = 0.0
        battery_cost = 0.0
        heat_cost = 0.0
        confidence_total = 0.0
        confidence_weight = 0.0
        tier_factor = {1: 1.25, 2: 1.15, 3: 1.0, 4: 0.9, 5: 0.8}.get(tier, 1.0)

        for step in plan.steps:
            g = step.rule.gain
            fps_gain += max(0.0, g.fps) * g.confidence * tier_factor
            stability_gain += max(0.0, g.stability) * g.confidence
            latency_gain += min(0.0, g.input_latency_ms) * g.confidence
            battery_cost += abs(min(0.0, g.battery)) * g.confidence
            heat_cost += max(0.0, g.heat) * g.confidence
            confidence_total += g.confidence
            confidence_weight += 1

        decay = 0.52                     # gain antar-tuas saling tumpang tindih
        gpu_capacity = self.gpu_capacity(dev, mode, budget, plan)
        reachable = min(ceiling, gpu_capacity, baseline + fps_gain * decay)
        if dev.engine_cap_fps < mode.target_fps:
            reachable = min(reachable, dev.engine_cap_fps)
        stability = min(99.0, 55.0 + stability_gain * 0.55)
        confidence = (confidence_total / confidence_weight) if confidence_weight else 0.5

        notes: List[str] = []
        if dev.engine_cap_fps < mode.target_fps:
            notes.append(
                f"Engine Bedrock di perangkat ini diperkirakan menahan di "
                f"{dev.engine_cap_fps} FPS ({dev.engine_cap_reason}). Mode "
                f"{mode.target_fps} FPS tetap diterapkan - sistem akan memaksimalkan "
                f"stabilitas frame-time pada batas itu.")
        if not dev.supports_refresh(mode.refresh_target):
            rates = ", ".join(f"{r:g}" for r in dev.refresh_rates) or "60"
            notes.append(f"Layar tidak punya mode {mode.refresh_target:g} Hz "
                         f"(tersedia: {rates} Hz). Target diturunkan ke yang didukung.")
        if dev.thermal_status >= 3:
            notes.append(f"Perangkat sedang thermal status {dev.thermal_status} - "
                         "FPS akan turun otomatis sampai suhu normal.")
        if dev.battery_temp_c and dev.battery_temp_c >= 40:
            notes.append(f"Suhu baterai {dev.battery_temp_c}C sudah tinggi. "
                         "Pakai cooling fan untuk mode ini.")
        if battery_cost > 12:
            notes.append(f"Perkiraan konsumsi baterai +{int(battery_cost)}% lebih boros "
                         "dibanding kondisi awal.")
        if not dev.game_mode_supported:
            notes.append("Game Mode API tidak tersedia di perangkat/versi Android ini - "
                         "tuas backbuffer resize & FPS override dilewati.")
        if not dev.minecraft.writable:
            notes.append("options.txt tidak bisa ditulis lewat ADB. Jalankan lewat Termux/root "
                         "atau ubah manual dari file manager.")
        applied_scale = budget.downscale
        for step in plan.steps:
            if step.rule.id == "gamemode.downscale":
                for cmd in step.commands:
                    if cmd.label.startswith("render scale"):
                        try:
                            applied_scale = int(cmd.label.split()[2].rstrip("%")) / 100.0
                        except (IndexError, ValueError):
                            pass
        if applied_scale < 1.0:
            notes.append(f"Render scale {int(applied_scale * 100)}% - gambar sedikit "
                         "kurang tajam, ditukar FPS yang jauh lebih lega.")
        if reachable < mode.target_fps * 0.9:
            notes.append(f"GPU perangkat ini diperkirakan mentok di {reachable:.0f} FPS pada "
                         f"preset ini. Turunkan render distance atau pakai mode lebih rendah "
                         f"untuk frame-time yang rata.")

        return Projection(
            target_fps=mode.target_fps,
            reachable_fps=round(reachable, 1),
            ceiling_fps=round(ceiling, 1),
            ceiling_reason=dev.engine_cap_reason,
            frametime_ms=round(1000.0 / max(reachable, 1.0), 2),
            stability=round(stability, 1),
            confidence=round(min(0.95, max(0.25, confidence)), 2),
            battery_pct=round(battery_cost, 1),
            heat=("tinggi" if heat_cost > 25 else "sedang" if heat_cost > 10 else "normal"),
            notes=notes,
        )

    # -- model kapasitas GPU ---------------------------------------------- #
    GPU_CAPACITY_BY_TIER = {1: 34.0, 2: 46.0, 3: 68.0, 4: 98.0, 5: 138.0}

    def gpu_capacity(self, dev: Device, mode: FpsMode, budget: QualityBudget,
                     plan: Plan) -> float:
        """Perkiraan FPS maksimum yang sanggup dihasilkan GPU pada preset ini."""
        tier = int(dev.extras.get("tier", 3))
        capacity = self.GPU_CAPACITY_BY_TIER.get(tier, 68.0)

        ram_factor = 1.0
        if dev.ram_mb and dev.ram_mb < 3800:
            ram_factor = 0.82
        elif dev.ram_mb and dev.ram_mb < 6000:
            ram_factor = 0.92
        capacity *= ram_factor

        # render distance adalah beban terbesar
        chunks = budget.chunks
        capacity *= max(0.35, 1.28 - 0.052 * chunks)
        if budget.smooth_lighting:
            capacity *= 0.93
        if budget.transparent_leaves:
            capacity *= 0.96
        if not budget.fancy_skies:
            capacity *= 1.02
        msaa_factor = {1: 1.0, 2: 0.93, 4: 0.84, 8: 0.7, 16: 0.55}
        capacity *= msaa_factor.get(budget.msaa, 0.9)
        capacity *= 0.94 + 0.14 * budget.particle_view

        # resolusi render efektif (backbuffer resize + resolusi layar)
        scale = budget.downscale if budget.downscale < 1.0 else 1.0
        if budget.resolution_scale:
            scale *= budget.resolution_scale
        capacity /= max(0.4, scale ** 1.55)

        pixels = 0
        if dev.extras.get("screen"):
            try:
                w, h = (int(x) for x in dev.extras["screen"].split("x"))
                pixels = w * h
            except ValueError:
                pixels = 0
        if pixels:
            # normalisasi ke 1080p; panel lebih besar = lebih berat
            capacity *= (2_073_600 / pixels) ** 0.35

        # perangkat yang sudah panas kehilangan kapasitas
        capacity *= 1.0 - 0.06 * max(0, dev.thermal_status - 1)
        return round(capacity, 1)

    # -- eksekusi --------------------------------------------------------- #
    def apply(self, plan: Plan, dry_run: bool = False,
              on_step: Optional[Callable[[PlanStep, int, int], None]] = None) -> Plan:
        entries: List[JournalEntry] = []
        total = len(plan.steps)
        for index, step in enumerate(plan.steps, start=1):
            if dry_run:
                step.applied = False
                step.ok = True
                step.output = "[dry-run] " + " && ".join(c.shell for c in step.commands)
            else:
                outputs: List[str] = []
                errors: List[str] = []
                step.applied = True
                for cmd in step.commands:
                    res = self.transport.shell(cmd.shell, root=cmd.root)
                    text = (res.out or "").strip()
                    if res.ok or cmd.optional:
                        outputs.append(f"$ {cmd.shell}\n{text}".strip())
                        if cmd.undo:
                            entries.append(JournalEntry(
                                ts=time.time(), plan_id=plan.id, rule_id=step.rule.id,
                                command=cmd.shell, undo=cmd.undo,
                                output=text[:400]))
                    else:
                        errors.append(f"$ {cmd.shell}\n! {(res.err or res.out).strip()}")
                step.output = "\n".join(outputs)[:6000]
                step.error = "\n".join(errors)[:2000]
                step.ok = not errors or bool(outputs)

                if step.rule.verify and step.rule.verify.command:
                    vres = self.transport.shell(step.rule.verify.command)
                    step.verify_result = (vres.out or vres.err or "").strip()[:4000]
                    step.verify_passed = self._check(step.verify_result, step.rule.verify.expect,
                                                     step.rule.verify.mode)
            if on_step:
                on_step(step, index, total)
        if entries and not dry_run:
            self.journal.append(entries)
        return plan

    @staticmethod
    def _check(output: str, expect: str, mode: str) -> bool:
        if mode == "nonempty":
            return bool(output) and output.strip().lower() not in ("null", "none", "")
        if mode == "equals":
            return output.strip() == expect.strip()
        if mode == "number_gte":
            try:
                return float(re.search(r"[\d\.]+", output).group(0)) >= float(expect)
            except (AttributeError, ValueError):
                return False
        return expect.lower() in output.lower() if expect else bool(output)

    # -- pembatalan ------------------------------------------------------- #
    def undo(self, plan_id: Optional[str] = None,
             on_entry: Optional[Callable[[Dict[str, object]], None]] = None) -> Dict[str, object]:
        entries = self.journal.take(plan_id or None)
        done: List[str] = []
        failed: List[str] = []
        for entry in reversed(entries):
            undo_cmd = entry.get("undo")
            if not undo_cmd:
                continue
            res = self.transport.shell(str(undo_cmd))
            if res.ok:
                done.append(str(undo_cmd))
            else:
                failed.append(f"{undo_cmd} -> {(res.err or res.out).strip()}")
            if on_entry:
                on_entry(entry)
        return {"restored": len(done), "failed": failed, "commands": done,
                "entries": len(entries)}

