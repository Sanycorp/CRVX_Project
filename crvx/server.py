"""Control Panel web - HTTP server stdlib (tanpa dependensi) + JSON API."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from . import __codename__, __version__
from .adb import SimTransport, Transport, build_transport
from .bench import Benchmarker, compare
from .detect import detect_device
from .governor import AdaptiveGovernor
from .models import Device, Plan
from .modes import all_modes, get_mode
from .addonforge import build_addon, verify_addon
from .packforge import build_fogcut_pack, verify_pack
from .texforge import build_texture_pack
from .planner import CRVX_HOME, Journal, Planner
from . import generators

PANEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")


class Engine:
    """State mesin yang dipakai bersama oleh API dan panel."""

    def __init__(self, transport: Optional[Transport] = None, serial: str = "", sim: bool = False):
        self.serial = serial
        self.sim = sim
        self.transport: Transport = transport or (SimTransport() if sim else
                                                  build_transport(serial=serial))
        if self.transport.name == "offline":
            self.transport = SimTransport()
        self.device: Device = detect_device(self.transport)
        self.planner = Planner(self.transport)
        self.plan: Optional[Plan] = None
        self.mode_id = "120"
        self.risk = ""
        self.with_pack = False
        self.bench_history: List[Dict[str, Any]] = []
        self.last_before: Optional[Dict[str, Any]] = None
        self.governor: Optional[AdaptiveGovernor] = None
        self.govern_log: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    # -- state ------------------------------------------------------------ #
    def rescan(self) -> Device:
        with self.lock:
            self.device = detect_device(self.transport)
        return self.device

    def state(self) -> Dict[str, Any]:
        journal = Journal().load()
        return {
            "engine": {"version": __version__, "codename": __codename__,
                       "home": CRVX_HOME, "transport": self.transport.name},
            "device": self.device.to_dict(),
            "modes": all_modes(self.device),
            "selection": {"mode": self.mode_id, "risk": self.risk or
                          get_mode(self.mode_id, self.device).risk_ceiling,
                          "with_pack": self.with_pack},
            "plan": self.plan.to_dict() if self.plan else None,
            "journal": {"entries": len(journal),
                        "plans": sorted({str(e.get("plan_id")) for e in journal})},
            "bench_history": self.bench_history[-8:],
            "govern_log": self.govern_log[-20:],
        }

    # -- aksi ------------------------------------------------------------- #
    def make_plan(self, mode: str = "", risk: str = "", with_pack: Optional[bool] = None) -> Plan:
        self.mode_id = mode or self.mode_id
        self.risk = risk or self.risk
        if with_pack is not None:
            self.with_pack = with_pack
        self.plan = self.planner.plan(self.device, self.mode_id, risk=self.risk or None,
                                      with_pack=self.with_pack)
        return self.plan

    def apply(self, dry_run: bool = False) -> Dict[str, Any]:
        if self.plan is None:
            self.make_plan()
        plan = self.plan
        started = time.time()
        self.planner.apply(plan, dry_run=dry_run)
        applied = sum(1 for s in plan.steps if s.applied)
        failed = [s.rule.id for s in plan.steps if s.applied and not s.ok]
        verified = sum(1 for s in plan.steps if s.verify_passed)
        return {"plan_id": plan.id, "applied": applied, "failed": failed,
                "verified": verified, "dry_run": dry_run,
                "seconds": round(time.time() - started, 2),
                "steps": plan.to_dict()["steps"]}

    def undo(self, plan_id: str = "") -> Dict[str, Any]:
        result = self.planner.undo(plan_id or None)
        return result

    def bench(self, duration: float = 8.0, target: float = 0.0, label: str = "run") -> Dict[str, Any]:
        package = self.device.minecraft.package or "com.mojang.minecraftpe"
        marker = Benchmarker(self.transport, package)
        target = target or get_mode(self.mode_id, self.device).effective_target(self.device)
        result = marker.run(duration_s=max(3.0, min(duration, 30.0)), interval_s=1.0,
                            label=label, target_fps=target)
        payload = result.to_dict()
        payload["target_fps"] = target
        self.bench_history.append({"t": time.time(), **payload})
        if label == "before":
            self.last_before = payload
        return payload

    def compare_last(self) -> Optional[Dict[str, Any]]:
        runs = [b for b in self.bench_history if b.get("label") in ("before", "after")]
        if len(runs) >= 2:
            before = [b for b in runs if b["label"] == "before"][-1]
            after = [b for b in runs if b["label"] == "after"][-1]
            from .models import BenchResult
            def _to(d):
                return BenchResult(**{k: v for k, v in d.items()
                                      if k in BenchResult.__dataclass_fields__})
            return compare(_to(before), _to(after))
        return None

    def govern_tick(self, mode: str = "", do_apply: bool = False) -> Dict[str, Any]:
        mode_obj = get_mode(mode or self.mode_id, self.device)
        if self.governor is None or self.governor.mode.id != mode_obj.id:
            budget = mode_obj.budget_for(self.device)
            if self.plan is None:
                self.make_plan(mode_obj.id)
            capacity = self.planner.gpu_capacity(self.device, mode_obj, budget, self.plan)
            self.governor = AdaptiveGovernor(self.device, mode_obj, budget, capacity=capacity)
        marker = Benchmarker(self.transport, self.device.minecraft.package)
        sample = marker.quick(target_fps=mode_obj.target_fps)
        thermal, temp = marker.thermal()
        decision = self.governor.update(sample.fps_avg or 0.0, thermal)
        payload = decision.to_dict()
        payload["fps"] = sample.fps_avg
        payload["source"] = sample.source
        payload["smoothness"] = sample.smoothness_score
        payload["battery_temp"] = temp
        payload["applied"] = []
        if do_apply:
            for action in decision.actions:
                if action.command:
                    res = self.transport.shell(action.command)
                    payload["applied"].append({"lever": action.lever, "ok": res.ok,
                                               "command": action.command})
        self.govern_log.append({"t": time.time(), **payload})
        return payload

    def script(self, fmt: str) -> Dict[str, str]:
        if self.plan is None:
            self.make_plan()
        plan, dev = self.plan, self.device
        if fmt == "sh":
            body, undo = generators.posix_script(plan, dev, serial=self.serial or dev.serial)
            return {"filename": f"crvx-{plan.mode_id}fps.sh", "body": body, "extra": undo}
        if fmt == "bat":
            return {"filename": f"crvx-{plan.mode_id}fps.bat",
                    "body": generators.windows_script(plan, dev, serial=self.serial or dev.serial)}
        if fmt == "termux":
            return {"filename": f"crvx-{plan.mode_id}fps-termux.sh",
                    "body": generators.termux_script(plan, dev)}
        if fmt == "ondevice":
            return {"filename": f"crvx-{plan.mode_id}fps-ondevice.sh",
                    "body": generators.ondevice_script(plan, dev, root=dev.rooted),
                    "extra": generators.ondevice_undo_script(plan, dev, root=dev.rooted)}
        if fmt == "ondevice-undo":
            return {"filename": f"crvx-undo-{plan.mode_id}fps-ondevice.sh",
                    "body": generators.ondevice_undo_script(plan, dev, root=dev.rooted)}
        if fmt == "md":
            return {"filename": f"crvx-{plan.mode_id}fps-report.md",
                    "body": generators.markdown_report(plan, dev)}
        if fmt == "json":
            return {"filename": f"crvx-{plan.mode_id}fps-plan.json", "body": plan.dumps()}
        raise ValueError(f"format tidak dikenal: {fmt}")

    def pack(self) -> str:
        path = os.path.join(CRVX_HOME, "packs", "crvx-fogcut.mcpack")
        return build_fogcut_pack(path)

    def texture(self, res: int = 8) -> str:
        """Bangun .mcpack tekstur cepat (self-authored) lalu validasi."""
        path = os.path.join(CRVX_HOME, "addon", f"CRVX_FastTex_{res}x.mcpack")
        build_texture_pack(path, res=res)
        hasil = verify_pack(path)
        if not hasil["ok"]:
            raise ValueError("pack tekstur gagal validasi: " + "; ".join(hasil["problems"]))
        return path

    def addon(self, strength: float = 0.85) -> str:
        """Bangun .mcaddon lengkap lalu validasi sebelum disajikan."""
        path = os.path.join(CRVX_HOME, "addon", "CRVX_FPS_Booster.mcaddon")
        build_addon(path, fog_strength=strength)
        hasil = verify_addon(path)
        if not hasil["ok"]:
            raise ValueError("addon gagal validasi: " + "; ".join(hasil["problems"]))
        return path


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".mcpack": "application/octet-stream",
    ".sh": "text/x-shellscript; charset=utf-8",
    ".bat": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"CRVXTurboFrame/{__version__}"
        protocol_version = "HTTP/1.1"

        # -- helpers ------------------------------------------------------ #
        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("  " + (fmt % args) + "\n")

        def _send(self, code: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, payload: Any, code: int = 200):
            self._send(code, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length).decode("utf-8", "replace")
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {k: v[0] for k, v in parse_qs(raw).items()}

        # -- routes ------------------------------------------------------- #
        def do_OPTIONS(self):  # noqa: N802
            self._send(204, b"", "text/plain", {"Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                                                 "Access-Control-Allow-Headers": "Content-Type"})

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            path = url.path
            try:
                if path == "/api/state":
                    return self._json(engine.state())
                if path == "/api/modes":
                    return self._json(all_modes(engine.device))
                if path.startswith("/api/export/"):
                    fmt = path.rsplit("/", 1)[-1]
                    result = engine.script(fmt)
                    ctype = MIME.get("." + fmt, "text/plain; charset=utf-8")
                    return self._send(200, result["body"].encode("utf-8"), ctype,
                                      {"Content-Disposition": f'attachment; filename="{result["filename"]}"'})
                if path == "/api/texture":
                    tex_path = engine.texture()
                    with open(tex_path, "rb") as fh:
                        data = fh.read()
                    return self._send(200, data, "application/octet-stream",
                                      {"Content-Disposition":
                                       'attachment; filename="CRVX_FastTex_8x.mcpack"'})
                if path == "/api/addon":
                    addon_path = engine.addon()
                    with open(addon_path, "rb") as fh:
                        data = fh.read()
                    return self._send(200, data, "application/octet-stream",
                                      {"Content-Disposition":
                                       'attachment; filename="CRVX_FPS_Booster.mcaddon"'})
                if path == "/api/pack":
                    pack_path = engine.pack()
                    with open(pack_path, "rb") as fh:
                        data = fh.read()
                    return self._send(200, data, "application/octet-stream",
                                      {"Content-Disposition": 'attachment; filename="crvx-fogcut.mcpack"'})
                if path == "/api/journal":
                    return self._json(Journal().load())
                if path == "/api/health":
                    return self._json({"ok": True, "version": __version__,
                                       "transport": engine.transport.name})
                return self._static(path)
            except Exception as exc:
                return self._json({"error": f"{type(exc).__name__}: {exc}",
                                   "trace": traceback.format_exc()}, 500)

        def do_POST(self):  # noqa: N802
            url = urlparse(self.path)
            path = url.path
            body = self._body()
            try:
                if path == "/api/detect":
                    if body.get("sim"):
                        engine.transport = SimTransport()
                    dev = engine.rescan()
                    return self._json({"device": dev.to_dict()})
                if path == "/api/plan":
                    plan = engine.make_plan(str(body.get("mode", "")),
                                            str(body.get("risk", "")),
                                            body.get("with_pack"))
                    return self._json(plan.to_dict())
                if path == "/api/apply":
                    if body.get("mode"):
                        engine.make_plan(str(body["mode"]), str(body.get("risk", "")),
                                         body.get("with_pack"))
                    return self._json(engine.apply(dry_run=bool(body.get("dry_run"))))
                if path == "/api/undo":
                    return self._json(engine.undo(str(body.get("plan_id", ""))))
                if path == "/api/bench":
                    result = engine.bench(float(body.get("duration", 8)),
                                          float(body.get("target", 0) or 0),
                                          str(body.get("label", "run")))
                    result["compare"] = engine.compare_last()
                    return self._json(result)
                if path == "/api/govern/tick":
                    return self._json(engine.govern_tick(str(body.get("mode", "")),
                                                         bool(body.get("apply"))))
                if path == "/api/govern/reset":
                    engine.governor = None
                    engine.govern_log = []
                    return self._json({"ok": True})
                return self._json({"error": f"route tidak dikenal: {path}"}, 404)
            except Exception as exc:
                return self._json({"error": f"{type(exc).__name__}: {exc}",
                                   "trace": traceback.format_exc()}, 500)

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        # -- static ------------------------------------------------------- #
        def _static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            full = os.path.normpath(os.path.join(PANEL_DIR, rel))
            if not full.startswith(os.path.normpath(PANEL_DIR)):
                return self._send(403, b"forbidden", "text/plain")
            if not os.path.exists(full) and not os.path.splitext(full)[1]:
                full = os.path.join(PANEL_DIR, "index.html")
            if not os.path.isfile(full):
                return self._send(404, b"not found", "text/plain")
            ctype = MIME.get(os.path.splitext(full)[1], "application/octet-stream")
            with open(full, "rb") as fh:
                return self._send(200, fh.read(), ctype)

    return Handler


def _lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def run_server(host: str = "0.0.0.0", port: int = 8120, sim: bool = False,
               serial: str = "", open_browser: bool = False) -> int:
    engine = Engine(serial=serial, sim=sim)
    handler = make_handler(engine)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    shown_host = "localhost" if host in ("0.0.0.0", "") else host
    print(f"\n  CRVX TurboFrame Control Panel  v{__version__}")
    print(f"  transport : {engine.transport.name}"
          f"{' (SIMULATOR)' if engine.transport.simulated else ''}")
    print(f"  device    : {engine.device.brand} {engine.device.model} | "
          f"tier {engine.device.extras.get('tier_name')}")
    print(f"  panel     : http://{shown_host}:{port}  (LAN: http://{_lan_ip()}:{port})")
    print("  tekan Ctrl+C untuk berhenti\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{shown_host}:{port}")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  panel dihentikan")
    finally:
        httpd.server_close()
    return 0
