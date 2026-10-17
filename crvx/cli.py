"""CRVX TurboFrame CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional

from . import __codename__, __version__
from .adb import SimTransport, Transport, build_transport
from .bench import Benchmarker, compare
from .detect import describe_device, detect_device, generic_device, parse_options
from .governor import AdaptiveGovernor
from .minecraft import diff as options_diff
from .minecraft import merge as options_merge
from .models import Device, Plan
from .modes import all_modes, get_mode
from .packforge import build_fogcut_pack, verify_pack
from .planner import BACKUP_DIR, CRVX_HOME, Journal, Planner
from . import generators

# --------------------------------------------------------------------------- #
# Terminal helpers
# --------------------------------------------------------------------------- #
class C:
    PINK = "\033[38;5;212m"
    CYAN = "\033[38;5;51m"
    GREEN = "\033[38;5;46m"
    AMBER = "\033[38;5;220m"
    RED = "\033[38;5;203m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    OFF = "\033[0m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


if not _supports_color():
    for _name in ("PINK", "CYAN", "GREEN", "AMBER", "RED", "DIM", "BOLD", "OFF"):
        setattr(C, _name, "")


def head(text: str) -> None:
    print(f"\n{C.PINK}{C.BOLD}{text}{C.OFF}")
    print(f"{C.PINK}{'=' * max(8, len(text))}{C.OFF}")


def ok(text: str) -> None:
    print(f"  {C.GREEN}[OK]{C.OFF} {text}")


def warn(text: str) -> None:
    print(f"  {C.AMBER}[!!]{C.OFF} {text}")


def bad(text: str) -> None:
    print(f"  {C.RED}[XX]{C.OFF} {text}")


def dim(text: str) -> None:
    print(f"  {C.DIM}{text}{C.OFF}")


def banner() -> None:
    print(f"""
{C.PINK}{C.BOLD}  ██████╗██████╗ ██╗   ██╗██╗  ██╗   {C.CYAN}TURBOFRAME{C.PINK}
 ██╔════╝██╔══██╗██║   ██║╚██╗██╔╝   {C.OFF}FPS Boost Engine - Minecraft Bedrock/PE
 ██║     ██████╔╝██║   ██║ ╚███╔╝    {C.DIM}v{__version__} - {__codename__}{C.OFF}
 ██║     ██╔══██╗╚██╗ ██╔╝ ██╔██╗    {C.PINK}60 {C.OFF}|{C.CYAN} 90 {C.OFF}|{C.PINK} 120 {C.OFF}|{C.AMBER} 144 FPS{C.OFF}
 ╚██████╗██║  ██║ ╚████╔╝ ██╔╝ ██╗
  ╚═════╝╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝{C.OFF}""")


# --------------------------------------------------------------------------- #
# Shared plumbing
# --------------------------------------------------------------------------- #
def make_transport(args: argparse.Namespace) -> Transport:
    if getattr(args, "sim", False):
        return SimTransport()
    return build_transport(serial=getattr(args, "serial", "") or "", simulate=False,
                           adb_bin=getattr(args, "adb", "") or "")


def make_device(args: argparse.Namespace, transport: Optional[Transport] = None,
                quiet: bool = False) -> Device:
    transport = transport or make_transport(args)
    if transport.name == "offline":
        warn("Tidak ada perangkat ADB tersambung. Memakai profil GENERIK agar rencana "
             "dan skrip tetap bisa dibuat (pakai --sim untuk simulator penuh).")
        return generic_device()
    if not quiet:
        dim(f"transport: {transport.name}" + (" (simulasi)" if transport.simulated else ""))
    return detect_device(transport)


def save_json(path: str, payload: object) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    ok(f"disimpan: {path}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> int:
    head("DOCTOR - pemeriksaan lingkungan")
    print(f"  Python      : {sys.version.split()[0]}")
    print(f"  CRVX home   : {CRVX_HOME}")
    adb_path = args.adb or "adb"
    from shutil import which
    resolved = which(adb_path)
    if resolved:
        ok(f"adb ditemukan: {resolved}")
    else:
        bad("adb tidak ditemukan. Install platform-tools atau pakai --sim untuk simulasi.")
    transport = build_transport(serial=args.serial or "", adb_bin=args.adb or "")
    if transport.name == "adb":
        devices = transport.devices()
        ok(f"perangkat tersambung: {', '.join(devices) or '-'}")
        dev = detect_device(transport)
        print()
        print(describe_device(dev))
    else:
        warn("tidak ada perangkat. Jalankan `adb devices` atau `crvx detect --sim`.")
    journal = Journal()
    entries = journal.load()
    print()
    print(f"  Jurnal undo : {len(entries)} entri tersimpan")
    print(f"  Backup      : {BACKUP_DIR}")
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    transport = make_transport(args)
    dev = make_device(args, transport)
    if args.json:
        print(json.dumps(dev.to_dict(), indent=2, ensure_ascii=False))
        return 0
    head(f"DETEKSI PERANGKAT - {dev.model}")
    print(describe_device(dev))
    print()
    if dev.minecraft.installed and dev.minecraft.current_options:
        head("options.txt saat ini (kunci grafis)")
        for key in ("gfx_viewdistance", "gfx_msaa", "gfx_vsync", "gfx_max_framerate",
                    "gfx_smoothlighting", "gfx_transparentleaves", "gfx_particleviewdistance",
                    "gfx_fancyskies", "gfx_multithreaded_renderer"):
            value = dev.minecraft.current_options.get(key)
            if value is not None:
                print(f"  {key:<32} {C.CYAN}{value}{C.OFF}")
    return 0


def cmd_modes(args: argparse.Namespace) -> int:
    dev = make_device(args, quiet=True)
    head("MODE YANG TERSEDIA")
    for entry in all_modes(dev):
        feasible = entry.get("feasible", True)
        capped = entry.get("engine_capped", False)
        mark = C.GREEN + "READY" + C.OFF if feasible and not capped else (
            C.AMBER + "TERBATAS ENGINE" + C.OFF if capped else C.RED + "LAYAR TIDAK MENDUKUNG" + C.OFF)
        print(f"\n  {C.PINK}{C.BOLD}{entry['name']}{C.OFF}  [{mark}]")
        print(f"    {entry['tagline']}")
        budget = entry.get("budget") or {}
        print(f"    target efektif : {entry.get('effective_target')} FPS")
        print(f"    render distance: {budget.get('chunks')} chunk ({budget.get('viewdistance')} blok)")
        print(f"    MSAA {budget.get('msaa')}x | V-Sync {'ON' if budget.get('vsync') else 'OFF'} | "
              f"cap {budget.get('max_framerate') or 'unlimited'} | "
              f"render scale {int((budget.get('downscale') or 1) * 100)}%")
        for note in entry.get("notes", []):
            dim(f"- {note}")
    if args.json:
        save_json(args.json, all_modes(dev))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    dev = make_device(args, quiet=True)
    planner = Planner(make_transport(args))
    plan = planner.plan(dev, args.mode, risk=args.risk, with_pack=args.with_pack)
    proj = plan.projection
    head(f"RENCANA {plan.mode_name} - {plan.id}")
    print(f"  Target            : {proj.target_fps} FPS")
    print(f"  Perkiraan tercapai: {C.GREEN}{C.BOLD}{proj.reachable_fps} FPS{C.OFF} "
          f"(batas {proj.ceiling_fps} FPS)")
    print(f"  Frame time        : {proj.frametime_ms} ms")
    print(f"  Stabilitas        : {proj.stability}/100   keyakinan {int(proj.confidence * 100)}%")
    print(f"  Baterai/Panas     : +{proj.battery_pct}% / {proj.heat}")
    print()
    for i, step in enumerate(plan.steps, 1):
        print(f"  {C.CYAN}{i:02d}{C.OFF} [{step.rule.risk.value:<8}] {step.rule.title}")
        if args.verbose:
            for cmd in step.commands:
                dim(f"     $ {cmd.shell}")
    if plan.skipped:
        print()
        head("DILEWATI")
        for item in plan.skipped:
            print(f"  {C.DIM}-{C.OFF} {item['rule']['title']}")
            for reason in item["reasons"]:
                dim(f"     {reason}")
    if proj.notes:
        print()
        head("CATATAN ENGINE")
        for note in proj.notes:
            warn(note)
    if args.json:
        save_json(args.json, plan.to_dict())
    if getattr(args, 'apply', False):
        return _apply(plan, planner, args)
    return 0


def _apply(plan: Plan, planner: Planner, args: argparse.Namespace) -> int:
    head(f"EKSEKUSI {plan.mode_name}" + (" [DRY-RUN]" if args.dry_run else ""))
    if not args.dry_run and not args.yes:
        print(f"\n{C.AMBER}Perubahan akan diterapkan ke perangkat. "
              f"Semua bisa dibatalkan dengan `crvx undo`.{C.OFF}")
        try:
            answer = input("Lanjut? [Y/n] ").strip().lower()
        except EOFError:
            answer = "y"
        if answer.startswith("n"):
            warn("dibatalkan")
            return 1

    def on_step(step, index, total):
        mark = C.GREEN + "OK" + C.OFF if step.ok else C.RED + "GAGAL" + C.OFF
        verify = ""
        if step.verify_passed is True:
            verify = f"  {C.GREEN}terverifikasi{C.OFF}"
        elif step.verify_passed is False:
            verify = f"  {C.AMBER}verifikasi tidak cocok{C.OFF}"
        print(f"  [{index:02d}/{total:02d}] {mark} {step.rule.title}{verify}")
        if step.error and args.verbose:
            for line in step.error.splitlines()[:6]:
                dim(f"     {line}")

    before = None
    if args.bench:
        dim("mengukur FPS sebelum (10 detik)...")
        before = Benchmarker(planner.transport, plan.device.minecraft.package).run(
            duration_s=10, label="before", target_fps=plan.projection.target_fps)
        print(f"  sebelum: {before.fps_avg} FPS | 1% low {before.fps_p1} | jank {before.jank}")

    planner.apply(plan, dry_run=args.dry_run, on_step=on_step)

    if args.bench:
        dim("mengukur FPS sesudah (12 detik)...")
        after = Benchmarker(planner.transport, plan.device.minecraft.package).run(
            duration_s=12, label="after", target_fps=plan.projection.target_fps)
        result = compare(before, after)
        head("HASIL")
        print(f"  FPS  : {result['fps_before']} -> {C.GREEN}{result['fps_after']}{C.OFF} "
              f"({result['fps_gain']:+} FPS / {result['fps_gain_pct']:+}%) [{result['verdict']}]")
        print(f"  1%low: {result['p1_before']} -> {result['p1_after']}")
        print(f"  jank : {result['jank_gain']:+} | stutter {result['stutter_gain']:+} | "
              f"smoothness {result['smoothness_gain']:+}")
        if args.json:
            save_json(args.json.replace(".json", "-result.json"), result)
    print()
    ok(f"selesai. Undo kapan saja: crvx undo --plan {plan.id}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    dev = make_device(args, quiet=True)
    planner = Planner(make_transport(args))
    plan = planner.plan(dev, args.mode, risk=args.risk, with_pack=args.with_pack)
    return _apply(plan, planner, args)


def cmd_undo(args: argparse.Namespace) -> int:
    planner = Planner(make_transport(args))
    head("UNDO - mengembalikan kondisi awal")
    result = planner.undo(args.plan or None)
    print(f"  entri jurnal : {result['entries']}")
    print(f"  dipulihkan   : {C.GREEN}{result['restored']}{C.OFF}")
    for failed in result["failed"]:
        bad(failed)
    if args.verbose:
        for cmd in result["commands"]:
            dim(f"  <- {cmd}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    transport = make_transport(args)
    dev = make_device(args, transport, quiet=True)
    bench = Benchmarker(transport, dev.minecraft.package)
    head(f"BENCHMARK {args.duration:.0f} detik - target {args.target} FPS")
    if not dev.minecraft.installed:
        warn("Minecraft tidak terdeteksi; tetap mencoba mengambil data frame layar aktif.")
    print("  Buka Minecraft dan masuk ke dunia sekarang. Sampling dimulai dalam 3 detik...")
    time.sleep(3)

    def progress(count: int) -> None:
        print(f"\r  sampel #{count}", end="", flush=True)

    result = bench.run(duration_s=args.duration, interval_s=args.interval,
                       label=args.label, target_fps=args.target, progress=progress)
    print("\r" + " " * 30 + "\r", end="")
    if result.frames == 0:
        bad("tidak ada data frame. " + (result.notes[0] if result.notes else ""))
        return 2
    print(f"  sumber      : {result.source}")
    print(f"  frame       : {result.frames} dalam {result.duration_s}s")
    print(f"  FPS rata2   : {C.GREEN}{C.BOLD}{result.fps_avg}{C.OFF}")
    print(f"  1% low      : {result.fps_p1}   | 5% low {result.fps_p5} | max {result.fps_max}")
    print(f"  frame time  : avg {result.frametime_avg_ms} ms | p95 {result.frametime_p95_ms} ms")
    print(f"  jank        : {result.jank} frame | stutter index {result.stutter_index}")
    print(f"  smoothness  : {C.CYAN}{result.smoothness_score}/100{C.OFF}")
    print(f"  termal      : {result.thermal_start} -> {result.thermal_end} "
          f"({result.temp_start}C -> {result.temp_end}C)")
    for note in result.notes:
        warn(note)
    if args.json:
        save_json(args.json, result.to_dict())
    return 0


def cmd_govern(args: argparse.Namespace) -> int:
    transport = make_transport(args)
    dev = make_device(args, transport, quiet=True)
    mode = get_mode(args.mode, dev)
    gov = AdaptiveGovernor(dev, mode, mode.budget_for(dev))
    bench = Benchmarker(transport, dev.minecraft.package)
    head(f"ADAPTIVE FRAME GOVERNOR - {mode.name} (PID {gov.gains})")
    print(f"  target internal : {gov.target:.1f} FPS | batas engine {dev.engine_cap_fps} FPS")
    print(f"  tekan Ctrl+C untuk berhenti\n")
    decisions: List[Dict[str, object]] = []
    try:
        while True:
            sample = bench.quick(target_fps=mode.target_fps)
            thermal, _temp = bench.thermal()
            decision = gov.update(sample.fps_avg or 0.0, thermal)
            decisions.append(decision.to_dict())
            color = C.GREEN if decision.error < 2 else C.AMBER if decision.error < 8 else C.RED
            print(f"  [{time.strftime('%H:%M:%S')}] FPS {color}{decision.measured_fps:5.1f}{C.OFF} "
                  f"/ target {decision.target_fps:.0f} | error {decision.error:+.1f} | "
                  f"PID out {decision.output:+.2f} | termal {decision.thermal_name} | "
                  f"Q {decision.quality_index:.2f}")
            print(f"      {C.DIM}{decision.message}{C.OFF}")
            for action in decision.actions:
                warn(f"    -> {action.lever}: {action.value} ({action.reason})")
                if args.apply and action.command:
                    res = transport.shell(action.command)
                    (ok if res.ok else bad)(action.command)
                    if res.out.strip():
                        dim(f"       {res.out.strip()[:120]}")
            if args.json:
                save_json(args.json, decisions)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        ok(f"governor berhenti setelah {len(decisions)} keputusan")
        if args.json:
            save_json(args.json, decisions)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    dev = make_device(args, quiet=True)
    planner = Planner(make_transport(args))
    plan = planner.plan(dev, args.mode, risk=args.risk, with_pack=args.with_pack)
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    formats = args.format.split(",") if args.format != "all" else \
        ["sh", "undo", "bat", "termux", "ondevice", "md"]
    written: List[str] = []
    for fmt in formats:
        fmt = fmt.strip().lower()
        if fmt == "sh":
            script, undo = generators.posix_script(plan, dev, serial=args.serial or dev.serial)
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps.sh")
            _write(path, script)
            _write(os.path.join(outdir, "crvx-undo.sh"), undo)
            written += [path, os.path.join(outdir, "crvx-undo.sh")]
        elif fmt == "undo":
            continue
        elif fmt == "bat":
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps.bat")
            _write(path, generators.windows_script(plan, dev, serial=args.serial or dev.serial))
            _write(os.path.join(outdir, "crvx-undo.bat"),
                   generators.windows_undo_script(plan, dev, serial=args.serial or dev.serial))
            written += [path, os.path.join(outdir, "crvx-undo.bat")]
        elif fmt == "termux":
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps-termux.sh")
            _write(path, generators.termux_script(plan, dev))
            written.append(path)
        elif fmt == "ondevice":
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps-ondevice.sh")
            _write(path, generators.ondevice_script(plan, dev, root=args.root))
            upath = os.path.join(outdir, f"crvx-undo-{plan.mode_id}fps-ondevice.sh")
            _write(upath, generators.ondevice_undo_script(plan, dev, root=args.root))
            written += [path, upath]
        elif fmt == "md":
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps-report.md")
            _write(path, generators.markdown_report(plan, dev))
            written.append(path)
        elif fmt == "json":
            path = os.path.join(outdir, f"crvx-{plan.mode_id}fps-plan.json")
            _write(path, json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
            written.append(path)
        else:
            bad(f"format tidak dikenal: {fmt}")
    head("EXPORT")
    for path in written:
        ok(path)
    return 0


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if path.endswith(".sh"):
        os.chmod(path, 0o755)


def cmd_pack(args: argparse.Namespace) -> int:
    path = args.out or os.path.join(CRVX_HOME, "packs", "crvx-fogcut.mcpack")
    build_fogcut_pack(path, strength=args.strength)
    result = verify_pack(path)
    head("PACKFORGE")
    if result["ok"]:
        ok(f"{path} ({result['size_bytes']} bytes, {len(result['entries'])} entri)")
        for entry in result["entries"]:
            dim(f"  - {entry}")
    else:
        bad("pack tidak valid:")
        for problem in result["problems"]:
            print(f"     {problem}")
        return 1
    print()
    dim("Pasang: buka file .mcpack di HP (otomatis diimpor Minecraft), atau:")
    dim(f"  adb push {path} /sdcard/Android/data/com.mojang.minecraftpe/files/resource_packs/")
    dim("Lalu aktifkan di Minecraft > Settings > Global Resources > Activate.")
    return 0


def cmd_options(args: argparse.Namespace) -> int:
    transport = make_transport(args)
    dev = make_device(args, transport, quiet=True)
    path = dev.minecraft.options_path
    if not dev.minecraft.installed:
        bad("Minecraft tidak terdeteksi")
        return 1
    if args.show:
        head(f"options.txt - {path}")
        res = transport.shell(f"cat {path}")
        print(res.out or res.err)
        return 0
    current = transport.shell(f"cat {path}").out
    if args.reset:
        backup = transport.shell(f"cat {BACKUP_DIR.replace(os.path.expanduser('~'), '')}"
                                 f"/options.txt 2>/dev/null")
        warn("reset memakai backup lokal di CRVX_HOME/backups/options.txt")
        local = os.path.join(BACKUP_DIR, "options.txt")
        if os.path.exists(local):
            with open(local, "r", encoding="utf-8") as fh:
                restored = fh.read()
            _push_text(transport, path, restored)
            ok("options.txt dipulihkan dari backup")
        else:
            bad("backup tidak ditemukan")
            return 1
        return 0
    updates: Dict[str, str] = {}
    for item in args.set or []:
        if ":" not in item and "=" not in item:
            bad(f"format salah: {item} (pakai key:value)")
            return 1
        key, _, value = item.replace("=", ":").partition(":")
        updates[key.strip()] = value.strip()
    mode = get_mode(args.mode, dev) if args.mode else None
    if mode:
        budget = mode.budget_for(dev)
        updates.update(budget.options())
    if not updates:
        warn("tidak ada perubahan diminta (pakai --set key:value atau --mode)")
        return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(os.path.join(BACKUP_DIR, "options.txt"), "w", encoding="utf-8") as fh:
        fh.write(current)
    new_text = options_merge(current, updates, legacy=args.legacy)
    head("PERUBAHAN options.txt")
    for key, old, new in options_diff(current, new_text):
        print(f"  {key:<34} {C.RED}{old}{C.OFF} -> {C.GREEN}{new}{C.OFF}")
    if args.dry_run:
        warn("dry-run: tidak ditulis")
        return 0
    _push_text(transport, path, new_text)
    ok("options.txt diperbarui")
    dim("restart Minecraft: adb shell am force-stop " + dev.minecraft.package)
    return 0


def _push_text(transport: Transport, remote: str, text: str) -> None:
    """Tulis teks ke perangkat lewat push file lokal (paling andal)."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        tmp = fh.name
    res = transport.push(tmp, remote)
    os.unlink(tmp)
    if not res.ok:
        # fallback: tulis lewat shell
        escaped = text.replace("'", "'\\''")
        transport.shell(f"printf '%s' '{escaped}' > {remote}")


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import run_server
    return run_server(host=args.host, port=args.port, sim=args.sim, serial=args.serial,
                      open_browser=not args.no_browser)


def build_parser() -> argparse.ArgumentParser:
    glob = argparse.ArgumentParser(add_help=False)
    glob.add_argument("--serial", default="", help="serial perangkat ADB")
    glob.add_argument("--adb", default="", help="path binary adb")
    glob.add_argument("--sim", action="store_true", help="pakai simulator perangkat")

    parser = argparse.ArgumentParser(
        prog="crvx", description=f"CRVX TurboFrame v{__version__} - FPS Boost Engine "
                                 "untuk Minecraft Bedrock/PE (Android)", parents=[glob])
    parser.add_argument("--version", action="version", version=f"crvx {__version__} {__codename__}")

    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", default="", help="simpan hasil ke file JSON")
        sp.add_argument("--verbose", "-v", action="store_true")

    p = sub.add_parser("doctor", help="periksa lingkungan", parents=[glob])
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("detect", help="deteksi perangkat & Minecraft", parents=[glob])
    common(p)
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("modes", help="daftar mode 60/90/120/144 untuk perangkat ini", parents=[glob])
    common(p)
    p.set_defaults(func=cmd_modes)

    for name, func, help_text in (
            ("plan", cmd_plan, "buat rencana optimasi"),
            ("apply", cmd_apply, "buat + terapkan rencana")):
        p = sub.add_parser(name, help=help_text, parents=[glob])
        p.add_argument("--mode", default="120", help="60|90|120|144|auto")
        p.add_argument("--risk", default="", help="safe|moderate|advanced|root")
        p.add_argument("--with-pack", action="store_true", help="sertakan .mcpack fog-cut")
        common(p)
        if name == "apply":
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--yes", "-y", action="store_true", help="tanpa konfirmasi")
            p.add_argument("--bench", action="store_true", help="ukur FPS sebelum & sesudah")
        p.set_defaults(func=func)

    p = sub.add_parser("undo", help="kembalikan semua perubahan", parents=[glob])
    p.add_argument("--plan", default="", help="plan id (kosongkan = semua)")
    common(p)
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("bench", help="ukur FPS nyata saat game berjalan", parents=[glob])
    p.add_argument("--duration", type=float, default=15.0)
    p.add_argument("--interval", type=float, default=1.5)
    p.add_argument("--target", type=float, default=60.0)
    p.add_argument("--label", default="run")
    common(p)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("govern", help="Adaptive Frame Governor (loop PID live)", parents=[glob])
    p.add_argument("--mode", default="120")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--apply", action="store_true", help="jalankan tindakan governor")
    common(p)
    p.set_defaults(func=cmd_govern)

    p = sub.add_parser("export", help="hasilkan skrip siap jalan", parents=[glob])
    p.add_argument("--mode", default="120")
    p.add_argument("--risk", default="")
    p.add_argument("--with-pack", action="store_true")
    p.add_argument("--format", default="all", help="sh,bat,termux,ondevice,md,json / all")
    p.add_argument("--outdir", default="./dist")
    p.add_argument("--root", action="store_true")
    common(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("pack", help="bangun .mcpack fog-cut", parents=[glob])
    p.add_argument("--out", default="")
    p.add_argument("--strength", type=float, default=0.85)
    common(p)
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("options", help="baca/tulis options.txt Minecraft", parents=[glob])
    p.add_argument("--show", action="store_true")
    p.add_argument("--set", nargs="*", help="key:value ...")
    p.add_argument("--mode", default="", help="terapkan preset mode")
    p.add_argument("--legacy", action="store_true", help="tulis juga alias kunci versi lama")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    common(p)
    p.set_defaults(func=cmd_options)

    p = sub.add_parser("serve", help="jalankan Control Panel web", parents=[glob])
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8120)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command not in ("serve",):
        banner()
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print()
        warn("dibatalkan")
        return 130
    except Exception as exc:  # pragma: no cover
        bad(f"{type(exc).__name__}: {exc}")
        if getattr(args, "verbose", False):
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
