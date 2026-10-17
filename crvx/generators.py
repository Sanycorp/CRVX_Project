"""Generator skrip siap-jalan: bash (ADB), Windows .bat, Termux, on-device (Shizuku/root)."""

from __future__ import annotations

import shlex
from typing import Dict, List, Optional, Tuple

from .models import Device, Plan, PlanStep

BANNER = "CRVX TURBOFRAME"


def _strip_dquotes(cmd: str) -> str:
    """Buang double-quote agar aman dilewatkan lewat cmd.exe (path sysfs tanpa spasi)."""
    return cmd.replace('"', "")


def _bat_escape(text: str) -> str:
    """Escape karakter spesial cmd.exe di dalam baris echo."""
    text = text.replace("^", "^^").replace("%", "%%")
    for ch in ("&", "|", "<", ">"):
        text = text.replace(ch, "^" + ch)
    return text


def _flatten(plan: Plan) -> List[PlanStep]:
    return [s for s in plan.steps if s.commands]


# --------------------------------------------------------------------------- #
# POSIX / ADB
# --------------------------------------------------------------------------- #
def posix_script(plan: Plan, dev: Device, serial: str = "", with_undo: bool = True
                 ) -> Tuple[str, str]:
    serial = serial or dev.serial or ""
    target = f'-s "{serial}" ' if serial else ""
    lines: List[str] = [
        "#!/usr/bin/env bash",
        f"# {BANNER} - {plan.mode_name}",
        f"# Perangkat : {(dev.brand + ' ' + dev.model).strip() or 'generik'}"
        f" ({dev.soc_model or dev.board_platform or 'profil generik'})",
        f"# Android   : {dev.android_release} (SDK {dev.android_sdk})  |  panel {dev.panel_max_fps:g} Hz",
        f"# Target    : {plan.projection.target_fps if plan.projection else plan.mode_id} FPS  "
        f"(perkiraan tercapai {plan.projection.reachable_fps if plan.projection else '-'} FPS)",
        f"# Plan ID   : {plan.id}",
        "# Jalankan : bash <nama-file>.sh   (batalkan: bash crvx-undo.sh)",
        "set -u",
        "",
        'ADB="${ADB:-adb}"',
        f'SERIAL="{serial}"',
        'if [ -n "$SERIAL" ]; then T=(-s "$SERIAL"); else T=(); fi',
        "",
        'C_GREEN="\\033[38;5;46m"; C_PINK="\\033[38;5;212m"; C_DIM="\\033[2m"; C_RED="\\033[38;5;203m"; C_AMBER="\\033[38;5;220m"; C_OFF="\\033[0m"',
        'step() { printf "%b[%02d/%02d]%b %s\\n" "$C_PINK" "$1" "$2" "$C_OFF" "$3"; }',
        'run()  { if [ "${DRY_RUN:-0}" = "1" ]; then echo "  DRY $1"; return 0; fi;',
        '         out=$("$ADB" "${T[@]}" shell "$1" 2>&1); rc=$?;',
        '         if [ $rc -ne 0 ]; then printf "%b  ! gagal (rc=%s): %s%b\\n" "$C_RED" "$rc" "${out:0:120}" "$C_OFF"; fi;',
        '         [ -n "$out" ] && printf "%b  %s%b\\n" "$C_DIM" "${out:0:160}" "$C_OFF"; return 0; }',
        'runroot() { run "su -c \'$1\'"; }',
        "",
    ]
    if with_undo:
        lines += [
            'trap \'printf "%b\\nDibatalkan. Kembalikan semua perubahan dengan: bash crvx-undo.sh%b\\n" '
            '"$C_RED" "$C_OFF"; exit 130\' INT',
            "",
        ]
    lines += [
        'printf "%b%s%b %s\\n\\n" "$C_GREEN" "==>" "PREFLIGHT"',
        'command -v "$ADB" >/dev/null 2>&1 || { printf "%badb tidak ditemukan. Install platform-tools dulu.%b\\n" "$C_RED" "$C_OFF"; exit 1; }',
        'STATE=$("$ADB" ${T[@]+"${T[@]}"} get-state 2>/dev/null || echo offline)',
        'if [ "$STATE" != "device" ]; then',
        '  printf "%bPerangkat belum tersambung.%b Aktifkan USB Debugging / Wireless Debugging lalu ulangi.\\n" "$C_RED" "$C_OFF"',
        '  "$ADB" devices; exit 1; fi',
        'MAXHZ=$("$ADB" ${T[@]+"${T[@]}"} shell "dumpsys display" 2>/dev/null | grep -oE "fps=[0-9.]+" | cut -d= -f2 | sort -n | tail -1)',
        'MODEL=$("$ADB" ${T[@]+"${T[@]}"} shell getprop ro.product.model 2>/dev/null | tr -d "\\r")',
        f'TARGET_HZ={int(plan.mode_id) if str(plan.mode_id).isdigit() else 120}',
        'printf "  perangkat    : %s\\n" "${MODEL:-tidak diketahui}"',
        'printf "  refresh maks : %s Hz\\n" "${MAXHZ:-?}"',
        'if [ -n "$MAXHZ" ] && [ "$(printf "%s\\n" "$MAXHZ < $TARGET_HZ" | bc 2>/dev/null || echo 0)" = "1" ]; then',
        '  printf "%b  ! panel tidak punya mode %s Hz - FPS akan dibatasi refresh layar.%b\\n" "$C_AMBER" "$TARGET_HZ" "$C_OFF"; fi',
        'MCVER=$("$ADB" ${T[@]+"${T[@]}"} shell dumpsys package com.mojang.minecraftpe 2>/dev/null | grep -m1 versionName | tr -d " \\r")',
        'printf "  minecraft    : %s\\n" "${MCVER:-tidak terdeteksi}"',
        'printf "%b%s%b %s\\n\\n" "$C_GREEN" "==>" "EKSEKUSI"',
    ]

    undo_lines: List[str] = [
        "#!/usr/bin/env bash",
        f"# {BANNER} - UNDO untuk plan {plan.id}",
        "set -u",
        'ADB="${ADB:-adb}"',
        f'SERIAL="{serial}"',
        'if [ -n "$SERIAL" ]; then T=(-s "$SERIAL"); else T=(); fi',
        'undo() { echo "  <- $1"; "$ADB" "${T[@]}" shell "$1" >/dev/null 2>&1 || true; }',
        'undoroot() { undo "su -c \'$1\'"; }',
        "",
    ]

    steps = _flatten(plan)
    total = len(steps)
    for index, step in enumerate(steps, start=1):
        lines.append("")
        lines.append(f'step {index} {total} "{step.rule.title}"')
        lines.append(f'# [{step.rule.category.value} | risiko {step.rule.risk.value}] '
                     f'{step.rule.description}')
        for cmd in step.commands:
            quoted = shlex.quote(cmd.shell)
            runner = "runroot" if cmd.root else "run"
            lines.append(f"{runner} {quoted}")
            if cmd.undo:
                undo_runner = "undoroot" if cmd.root else "undo"
                undo_lines.append(f"{undo_runner} {shlex.quote(cmd.undo)}")

    lines += [
        "",
        'printf "\\n%b==>%b selesai. Buka Minecraft, masuk dunia, lalu ukur dengan: crvx bench\\n" "$C_GREEN" "$C_OFF"',
    ]
    undo_lines += [
        "",
        'echo "Semua perubahan dikembalikan ke kondisi awal."',
    ]
    return "\n".join(lines) + "\n", "\n".join(undo_lines) + "\n"


# --------------------------------------------------------------------------- #
# Windows .bat
# --------------------------------------------------------------------------- #
def windows_script(plan: Plan, dev: Device, serial: str = "") -> str:
    serial = serial or dev.serial or ""
    lines: List[str] = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal enabledelayedexpansion",
        f"REM {BANNER} - {plan.mode_name}  (plan {plan.id})",
        f"REM Perangkat: {dev.brand} {dev.model} | Android {dev.android_release}",
        f'set "ADB=%ADB%"',
        'if "%ADB%"=="" set "ADB=adb"',
        f'set "SERIAL={serial}"',
        'if not "%SERIAL%"=="" (set "T=-s %SERIAL%") else (set "T=")',
        "echo.",
        f"echo  {BANNER} :: {plan.mode_name}",
        "echo  =========================================",
        "echo.",
        "echo  [PREFLIGHT]",
        "%ADB% get-state >nul 2>&1",
        "if errorlevel 1 (",
        "  echo   [XX] Perangkat belum tersambung. Aktifkan USB/Wireless Debugging.",
        "  %ADB% devices",
        "  pause",
        "  exit /b 1",
        ")",
        "for /f \"delims=\" %%a in ('%ADB% %T% shell getprop ro.product.model') do set \"MODEL=%%a\"",
        "for /f \"delims=\" %%a in ('%ADB% %T% shell dumpsys package com.mojang.minecraftpe ^| findstr versionName') do set \"MCVER=%%a\"",
        "  echo   perangkat : %MODEL%",
        "  echo   minecraft : %MCVER%",
        f"  echo   target Hz : {int(plan.mode_id) if str(plan.mode_id).isdigit() else 120}",
        "echo.",
        "echo  [EKSEKUSI]",
    ]
    for step in _flatten(plan):
        lines.append(f'echo {_bat_escape(f"[{step.rule.category.value}] {step.rule.title}")}')
        for cmd in step.commands:
            body = _strip_dquotes(cmd.shell).replace("%", "%%")
            prefix = "su -c " if cmd.root else ""
            if cmd.root:
                body = f"su -c \"{body}\""
            lines.append(f'%ADB% %T% shell "{body}" >nul 2>&1')
    lines += [
        "echo.",
        "echo  Selesai. Buka Minecraft lalu masuk ke dunia untuk merasakan hasilnya.",
        "echo  Untuk membatalkan semua perubahan jalankan crvx-undo.bat",
        "endlocal",
        "pause",
    ]
    return "\n".join(lines) + "\n"


def windows_undo_script(plan: Plan, dev: Device, serial: str = "") -> str:
    serial = serial or dev.serial or ""
    lines: List[str] = [
        "@echo off",
        "chcp 65001 >nul",
        f"REM {BANNER} - UNDO plan {plan.id}",
        'if "%ADB%"=="" set "ADB=adb"',
        f'set "SERIAL={serial}"',
        'if not "%SERIAL%"=="" (set "T=-s %SERIAL%") else (set "T=")',
    ]
    for step in reversed(_flatten(plan)):
        for cmd in reversed(step.commands):
            if not cmd.undo:
                continue
            body = _strip_dquotes(cmd.undo).replace("%", "%%")
            if cmd.root:
                body = f"su -c \"{body}\""
            lines.append(f'%ADB% %T% shell "{body}" >nul 2>&1')
            lines.append(f'echo   ^<- {_bat_escape(step.rule.id)}')
    lines += ["echo.", "echo  Semua perubahan dikembalikan.", "pause"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# On-device (Termux + wireless ADB ke diri sendiri / Shizuku / root)
# --------------------------------------------------------------------------- #
def termux_script(plan: Plan, dev: Device) -> str:
    """Skrip Termux: pairing ADB nirkabel ke HP sendiri lalu jalankan optimasi."""
    pkg = dev.minecraft.package or "com.mojang.minecraftpe"
    lines: List[str] = [
        "#!/data/data/com.termux/files/usr/bin/bash",
        f"# {BANNER} - {plan.mode_name}  [MODE ON-DEVICE / TERMUX]",
        "# Tidak butuh PC. Butuh: Termux + Wireless Debugging (Android 11+).",
        "#",
        "# 1) pkg install android-tools",
        "# 2) Settings > Developer options > Wireless debugging > ON",
        "# 3) Buka 'Wireless debugging' > 'Pair device with pairing code'",
        "#    catat IP:PORT dan kode 6 digit, lalu:",
        "#       adb pair 127.0.0.1:<PAIR_PORT>   (masukkan kode)",
        "#       adb connect 127.0.0.1:<CONNECT_PORT>",
        "# 4) bash crvx-termux.sh",
        "set -u",
        'ADB="${ADB:-adb}"',
        'if ! command -v "$ADB" >/dev/null 2>&1; then',
        '  echo "adb belum ada. Jalankan: pkg install android-tools"; exit 1; fi',
        'if ! "$ADB" get-state >/dev/null 2>&1; then',
        '  echo "Belum tersambung. Ikuti langkah pairing di komentar atas."; exit 1; fi',
        "",
        f'PKG="{pkg}"',
        'ok() { printf "  \\033[38;5;46m[OK]\\033[0m %s\\n" "$1"; }',
        'no() { printf "  \\033[38;5;203m[--]\\033[0m %s\\n" "$1"; }',
        "",
    ]
    for step in _flatten(plan):
        lines.append(f'echo "== {step.rule.title}"')
        for cmd in step.commands:
            shell = cmd.shell.replace('"', '\\"')
            if cmd.root:
                lines.append(f'"$ADB" shell "su -c \\"{shell}\\"" >/dev/null 2>&1 '
                             f'&& ok "{cmd.label or step.rule.id}" || no "{cmd.label or step.rule.id}"')
            else:
                lines.append(f'"$ADB" shell "{shell}" >/dev/null 2>&1 '
                             f'&& ok "{cmd.label or step.rule.id}" || no "{cmd.label or step.rule.id}"')
    lines += [
        "",
        'echo',
        'echo "Verifikasi:"',
        '"$ADB" shell "dumpsys display | grep -E \\"mActiveRenderFrameRate|peakRefreshRate\\""',
        '"$ADB" shell "cmd game list-modes $PKG" 2>/dev/null',
        '"$ADB" shell "grep -E \\"gfx_viewdistance|gfx_max_framerate|gfx_vsync\\" '
        '/sdcard/Android/data/$PKG/files/games/com.mojang/minecraftpe/options.txt" 2>/dev/null',
        'echo',
        'echo "Selesai. Restart Minecraft: $ADB shell am force-stop $PKG; '
        '$ADB shell monkey -p $PKG -c android.intent.category.LAUNCHER 1"',
    ]
    return "\n".join(lines) + "\n"


def ondevice_script(plan: Plan, dev: Device, root: bool = False) -> str:
    """Skrip untuk dijalankan langsung di shell perangkat (Shizuku/LADB/root)."""
    lines: List[str] = [
        "#!/system/bin/sh",
        f"# {BANNER} - {plan.mode_name}  [ON-DEVICE {'ROOT' if root else 'SHELL'}]",
        "# Jalankan lewat Shizuku (adb permission), LADB, atau `su` di Termux.",
        "",
    ]
    for step in _flatten(plan):
        lines.append(f"echo '== {step.rule.title}'")
        for cmd in step.commands:
            body = cmd.shell.replace("'", "'\\''")
            if root or cmd.root:
                lines.append(f"su -c '{body}' || true")
            else:
                lines.append(f"{cmd.shell} || true")
    lines.append("echo 'Selesai.'")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Laporan
# --------------------------------------------------------------------------- #
def markdown_report(plan: Plan, dev: Device, extra: Optional[Dict[str, object]] = None) -> str:
    proj = plan.projection
    lines: List[str] = [
        f"# {BANNER} - {plan.mode_name}",
        "",
        f"- **Plan ID**: `{plan.id}`",
        f"- **Perangkat**: {dev.brand} {dev.manufacturer} {dev.model} "
        f"({'SIMULATOR' if dev.simulated else 'nyata'})",
        f"- **SoC**: {dev.extras.get('soc_name') or dev.soc_model or 'tidak dikenal'} "
        f"| tier **{dev.extras.get('tier_name', 'MID')}**",
        f"- **Android**: {dev.android_release} (SDK {dev.android_sdk}) | RAM {dev.ram_mb // 1024} GB",
        f"- **Layar**: {dev.extras.get('screen', '-')} | refresh "
        f"{', '.join(f'{r:g}Hz' for r in dev.refresh_rates)} | aktif {dev.active_fps:g} Hz",
        f"- **Minecraft**: {dev.minecraft.version_name or '-'} | options.txt "
        f"{'dapat ditulis' if dev.minecraft.writable else 'terkunci'}",
        f"- **Cap engine**: {dev.engine_cap_fps} FPS ({dev.engine_cap_reason})",
        "",
    ]
    if proj:
        lines += [
            "## Proyeksi",
            "",
            f"| Metrik | Nilai |",
            f"| --- | --- |",
            f"| Target FPS | {proj.target_fps} |",
            f"| Perkiraan tercapai | **{proj.reachable_fps} FPS** |",
            f"| Batas atas | {proj.ceiling_fps} FPS |",
            f"| Frame time | {proj.frametime_ms} ms |",
            f"| Stabilitas | {proj.stability}/100 |",
            f"| Keyakinan | {int(proj.confidence * 100)}% |",
            f"| Baterai | +{proj.battery_pct}% lebih boros |",
            f"| Panas | {proj.heat} |",
            "",
        ]
        if proj.notes:
            lines += ["### Catatan jujur dari engine", ""]
            lines += [f"- {n}" for n in proj.notes]
            lines.append("")
    lines += [f"## Langkah yang akan dijalankan ({len(plan.steps)})", ""]
    for i, step in enumerate(plan.steps, 1):
        lines += [
            f"### {i}. {step.rule.title}",
            f"`{step.rule.category.value}` | risiko **{step.rule.risk.value}** | "
            f"gain ~{step.rule.gain.fps:+.1f} FPS (keyakinan {int(step.rule.gain.confidence * 100)}%)",
            "",
            step.rule.description,
            "",
            "```sh",
        ]
        lines += [c.shell for c in step.commands]
        lines += ["```", ""]
    if plan.skipped:
        lines += [f"## Dilewati ({len(plan.skipped)})", ""]
        for item in plan.skipped:
            rule = item["rule"]
            lines.append(f"- **{rule['title']}** - {'; '.join(item['reasons'])}")
        lines.append("")
    if extra:
        lines += ["## Hasil eksekusi", "", "```json",
                  __import__("json").dumps(extra, indent=2, ensure_ascii=False), "```"]
    return "\n".join(lines)
