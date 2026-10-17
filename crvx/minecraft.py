"""Utilitas options.txt Bedrock: penulisan, alias versi lama, diff."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .modes import QualityBudget

# Nama kunci modern (Bedrock 26.x / 1.21+) -> alias lama (1.16 - 1.20)
LEGACY_KEYS: Dict[str, Tuple[str, str]] = {
    "gfx_viewdistance": ("gfx_render_distance", "chunks"),
    "gfx_particleviewdistance": ("gfx_particle_view_distance", "same"),
    "gfx_smoothlighting": ("gfx_smooth_lighting", "same"),
    "gfx_transparentleaves": ("gfx_transparent_leaves", "same"),
    "gfx_viewbobbing": ("gfx_view_bobbing", "same"),
    "gfx_fancyskies": ("gfx_fancyskies", "same"),
    "gfx_field_of_view": ("gfx_field_of_view", "same"),
    "gfx_damagebobbing": ("gfx_damage_bobbing", "same"),
}


def parse(text: str) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        options[key.strip()] = value.strip()
    return options


def render(options: Dict[str, str], original_order: List[str] | None = None) -> str:
    order = original_order or list(options.keys())
    lines = [f"{key}:{options[key]}" for key in order if key in options]
    for key, value in options.items():
        if key not in order:
            lines.append(f"{key}:{value}")
    return "\n".join(lines) + "\n"


def merge(current_text: str, updates: Dict[str, str], legacy: bool = True) -> str:
    """Terapkan pembaruan ke isi options.txt, pertahankan urutan & kunci lain."""
    options = parse(current_text)
    order = list(options.keys())
    for key, value in updates.items():
        options[key] = str(value)
    if legacy:
        for key, (alias, mode) in LEGACY_KEYS.items():
            if key not in updates:
                continue
            value = updates[key]
            if mode == "chunks":
                try:
                    value = str(max(5, min(96, int(float(value)) // 16)))
                except ValueError:
                    continue
            options[alias] = str(value)
    return render(options, order)


def apply_budget(current_text: str, budget: QualityBudget, legacy: bool = True) -> str:
    return merge(current_text, budget.options(), legacy=legacy)


def diff(old_text: str, new_text: str) -> List[Tuple[str, str, str]]:
    before, after = parse(old_text), parse(new_text)
    changes: List[Tuple[str, str, str]] = []
    for key in sorted(set(before) | set(after)):
        old_value = before.get(key, "<tidak ada>")
        new_value = after.get(key, "<dihapus>")
        if old_value != new_value:
            changes.append((key, old_value, new_value))
    return changes


def shell_apply_commands(path: str, updates: Dict[str, str]) -> List[str]:
    """Perintah shell yang aman & idempoten untuk tiap kunci."""
    cmds: List[str] = []
    for key, value in updates.items():
        safe_key = key.replace("/", "\\/")
        safe_value = str(value).replace("/", "\\/").replace("&", "\\&")
        cmds.append(
            f"grep -q '^{safe_key}:' '{path}' && "
            f"sed -i 's/^{safe_key}:.*/{safe_key}:{safe_value}/' '{path}' || "
            f"echo '{key}:{value}' >> '{path}'")
    return cmds


def options_path_for(package: str) -> str:
    return (f"/sdcard/Android/data/{package}/files/games/com.mojang/minecraftpe/options.txt")
