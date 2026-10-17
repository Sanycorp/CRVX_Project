"""Uji inti engine: parsing telemetri, planner, pack, governor, generator."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile

from crvx import generators
from crvx.adb import SimTransport
from crvx.bench import (Benchmarker, compute_stats, frame_times_ms, parse_framestats,
                        parse_sf_latency)
from crvx.detect import detect_device
from crvx.governor import AdaptiveGovernor, simulate
from crvx.minecraft import diff, merge
from crvx.modes import MODES, all_modes, auto_mode, get_mode
from crvx.packforge import build_fogcut_pack, verify_pack
from crvx.planner import Journal, Planner
from crvx.rules import build_catalog


def make_device(**kw):
    sim = SimTransport()
    dev = detect_device(sim)
    for key, value in kw.items():
        setattr(dev, key, value)
    return sim, dev


class TestDetection(unittest.TestCase):
    def test_sim_device_enriched(self):
        _sim, dev = make_device()
        self.assertEqual(dev.android_sdk, 35)
        self.assertTrue(dev.refresh_rates)
        self.assertEqual(max(dev.refresh_rates), 120.0)
        self.assertTrue(dev.minecraft.installed)
        self.assertEqual(dev.minecraft.version_name, "26.52.20")
        self.assertTrue(dev.minecraft.writable)
        self.assertTrue(dev.game_mode_supported)
        self.assertGreaterEqual(dev.engine_cap_fps, 60)
        self.assertIn(dev.extras["tier_name"], ("FLAGSHIP", "UPPER", "MID", "ENTRY", "LOW"))

    def test_options_parsed(self):
        _sim, dev = make_device()
        self.assertEqual(dev.minecraft.current_options["gfx_max_framerate"], "60")
        self.assertEqual(dev.minecraft.current_options["gfx_vsync"], "1")

    def test_engine_cap_respects_panel(self):
        _sim, dev = make_device()
        dev.panel_max_fps = 60.0
        dev.display_modes = [m for m in dev.display_modes if m.fps <= 60.01]
        from crvx.soc import enrich
        enrich(dev)
        self.assertLessEqual(dev.engine_cap_fps, 60)


class TestModes(unittest.TestCase):
    def test_all_modes_present(self):
        self.assertEqual(list(MODES), ["60", "90", "120", "144"])

    def test_mode_budget_scales_with_tier(self):
        _sim, dev = make_device()
        for tier_low, tier_high in ((1, 5), (2, 4)):
            dev.extras["tier"] = tier_low
            low = MODES["120"].budget_for(dev).chunks
            dev.extras["tier"] = tier_high
            high = MODES["120"].budget_for(dev).chunks
            self.assertLess(low, high, "tier lemah harus dapat render distance lebih kecil")

    def test_effective_target_clamped(self):
        _sim, dev = make_device()
        dev.panel_max_fps = 60.0
        dev.engine_cap_fps = 60
        self.assertEqual(MODES["120"].effective_target(dev), 60)

    def test_auto_mode(self):
        _sim, dev = make_device()
        self.assertIn(auto_mode(dev).id, MODES)
        dev.panel_max_fps = 60.0
        dev.engine_cap_fps = 60
        self.assertEqual(auto_mode(dev).id, "60")

    def test_options_dict_valid_ranges(self):
        _sim, dev = make_device()
        for mode in MODES.values():
            opts = mode.budget_for(dev).options()
            self.assertTrue(80 <= int(opts["gfx_viewdistance"]) <= 1536)
            self.assertIn(int(opts["gfx_msaa"]), (1, 2, 4, 8, 16))
            self.assertTrue(0 <= float(opts["gfx_particleviewdistance"]) <= 1)


class TestRulesAndPlanner(unittest.TestCase):
    def test_catalog_not_empty_and_unique(self):
        _sim, dev = make_device()
        rules = build_catalog(dev, MODES["120"])
        ids = [r.id for r in rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("minecraft.options", ids)
        self.assertIn("display.refresh.system", ids)

    def test_every_rule_has_undo_or_is_harmless(self):
        _sim, dev = make_device()
        for rule in build_catalog(dev, MODES["120"]):
            for cmd in rule.commands:
                if cmd.shell.startswith(("settings put", "wm ", "cmd game", "device_config")):
                    self.assertTrue(cmd.undo or cmd.optional,
                                    f"{rule.id}: perintah sistem tanpa jalur undo")

    def test_plan_respects_risk_ceiling(self):
        _sim, dev = make_device()
        dev.rooted = True
        planner = Planner(SimTransport())
        safe = planner.plan(dev, "120", risk="safe")
        rooted = planner.plan(dev, "144", risk="root")
        self.assertTrue(all(s.rule.risk.value == "safe" for s in safe.steps))
        self.assertTrue(any(s.rule.risk.value == "root" for s in rooted.steps))

    def test_plan_skips_unmet(self):
        _sim, dev = make_device()
        dev.game_mode_supported = False
        plan = Planner(SimTransport()).plan(dev, "120")
        skipped_ids = {s["rule"]["id"] for s in plan.skipped}
        self.assertIn("gamemode.performance", skipped_ids)
        self.assertNotIn("gamemode.performance", [s.rule.id for s in plan.steps])

    def test_projection_is_honest(self):
        _sim, dev = make_device()
        dev.panel_max_fps = 60.0
        dev.engine_cap_fps = 60
        plan = Planner(SimTransport()).plan(dev, "120")
        self.assertLessEqual(plan.projection.reachable_fps, 60.0)
        self.assertTrue(plan.projection.notes)

    def test_apply_and_undo_roundtrip(self):
        sim, dev = make_device()
        journal_path = os.path.join(tempfile.mkdtemp(), "journal.json")
        planner = Planner(sim, Journal(journal_path))
        plan = planner.plan(dev, "120")
        planner.apply(plan)
        self.assertTrue(all(s.applied for s in plan.steps))
        self.assertGreater(len(planner.journal.load()), 10)

        # refresh rate benar-benar naik di simulator
        self.assertEqual(sim.settings["system"]["peak_refresh_rate"], "120.0")
        self.assertGreaterEqual(sim.state["refresh_locked"], 120.0)

        # options.txt mengikuti preset
        opts = sim.options()
        self.assertEqual(opts["gfx_vsync"], "0")
        self.assertEqual(opts["gfx_max_framerate"], "120")

        result = planner.undo(plan.id)
        self.assertGreater(result["restored"], 10)
        self.assertEqual(planner.journal.load(), [])
        self.assertEqual(sim.options()["gfx_vsync"], "1")

    def test_gpu_capacity_monotonic(self):
        sim, dev = make_device()
        planner = Planner(sim)
        high = MODES["60"].budget_for(dev)
        low = MODES["144"].budget_for(dev)
        cap_high = planner.gpu_capacity(dev, MODES["60"], high, planner.plan(dev, "60"))
        cap_low = planner.gpu_capacity(dev, MODES["144"], low, planner.plan(dev, "144"))
        self.assertGreater(cap_low, cap_high, "preset lebih ringan harus memberi kapasitas lebih besar")


class TestOptionsMerge(unittest.TestCase):
    ORIGINAL = "gfx_viewdistance:256\ngfx_vsync:1\ngfx_msaa:4\nmp_username:Player\n"

    def test_merge_keeps_unknown_keys(self):
        out = merge(self.ORIGINAL, {"gfx_viewdistance": "96", "gfx_vsync": "0"})
        self.assertIn("gfx_viewdistance:96", out)
        self.assertIn("gfx_vsync:0", out)
        self.assertIn("mp_username:Player", out)
        self.assertIn("gfx_msaa:4", out)

    def test_merge_appends_missing(self):
        out = merge(self.ORIGINAL, {"gfx_max_framerate": "120"})
        self.assertIn("gfx_max_framerate:120", out)

    def test_legacy_aliases(self):
        out = merge(self.ORIGINAL, {"gfx_viewdistance": "96"}, legacy=True)
        self.assertIn("gfx_render_distance:6", out)

    def test_diff(self):
        out = merge(self.ORIGINAL, {"gfx_vsync": "0"})
        changes = dict((k, (o, n)) for k, o, n in diff(self.ORIGINAL, out))
        self.assertEqual(changes["gfx_vsync"], ("1", "0"))


class TestTelemetry(unittest.TestCase):
    LATENCY = "8333333\n" + "\n".join(
        f"{1000000000 + i * 11111111}\t{1000000000 + i * 11111111 + 3000000}\t"
        f"{1000000000 + i * 11111111 + 6000000}" for i in range(60)) + "\n"

    def test_parse_sf_latency(self):
        refresh, stamps = parse_sf_latency(self.LATENCY)
        self.assertAlmostEqual(refresh, 8.333333, places=3)
        self.assertEqual(len(stamps), 60)
        self.assertEqual(stamps, sorted(set(stamps)))

    def test_parse_sf_latency_rejects_sentinels(self):
        text = "16666666\n0\t0\t0\n5\t5\t9223372036854775807\n7\t7\t1000\n9\t9\t2000\n"
        _refresh, stamps = parse_sf_latency(text)
        self.assertEqual(stamps, [1000, 2000])

    def test_dedupe_prevents_double_count(self):
        _refresh, stamps = parse_sf_latency(self.LATENCY)
        once = frame_times_ms(stamps)
        twice = frame_times_ms(sorted(set(stamps + stamps)))
        self.assertEqual(len(once), len(twice))

    def test_framestats(self):
        header = ("Flags,IntendedVsync,Vsync,OldestInputEvent,NewestInputEvent,HandleInputStart,"
                  "AnimationStart,PerformTraversalsStart,DrawStart,SyncQueued,SyncStart,"
                  "IssueDrawCommandsStart,SwapBuffers,FrameCompleted,DequeueBufferDuration,"
                  "QueueBufferDuration,GpuCompleted,")
        rows = [header]
        for i in range(40):
            vsync = 1_000_000_000 + i * 16_000_000
            done = vsync + 15_000_000
            rows.append(",".join(str(v) for v in [0, vsync, vsync, 0, 0, vsync, vsync, vsync,
                                                  vsync, done, done, done, done, done, 1, 1, done]) + ",")
        text = "---PROFILEDATA---\n" + "\n".join(rows) + "\n---PROFILEDATA---\n"
        stamps = parse_framestats(text)
        self.assertEqual(len(stamps), 40)
        times = frame_times_ms(stamps)
        stats = compute_stats(times, 16.6, 60)
        self.assertAlmostEqual(stats["fps"], 62.5, delta=1.0)
        self.assertGreater(stats["smoothness"], 50)

    def test_stats_percentiles(self):
        times = [16.6] * 90 + [50.0] * 10
        stats = compute_stats(times, 16.6, 60)
        self.assertGreater(stats["ft_p99_ms"], stats["ft_p50_ms"])
        self.assertEqual(stats["jank"], 10)
        self.assertGreater(stats["stutter_index"], 0)

    def test_benchmarker_against_sim(self):
        sim, dev = make_device()
        bench = Benchmarker(sim, dev.minecraft.package)
        result = bench.run(duration_s=2.0, interval_s=0.4, label="test", target_fps=60)
        self.assertGreater(result.frames, 10)
        self.assertEqual(result.source, "SurfaceFlinger --latency")
        self.assertGreater(result.fps_avg, 0)


class TestGovernor(unittest.TestCase):
    def test_reduces_quality_when_below_target(self):
        _sim, dev = make_device()
        gov = AdaptiveGovernor(dev, MODES["120"], MODES["120"].budget_for(dev), capacity=120)
        start = gov.budget.chunks
        for _ in range(6):
            gov.update(35.0, thermal=0)
        self.assertLess(gov.budget.chunks, start)

    def test_thermal_emergency_stops(self):
        _sim, dev = make_device()
        gov = AdaptiveGovernor(dev, MODES["144"], MODES["144"].budget_for(dev), capacity=144)
        decision = gov.update(120.0, thermal=5)
        self.assertEqual(decision.thermal_name, "EMERGENCY")
        self.assertTrue(any(a.lever == "thermal" for a in decision.actions))

    def test_relaxes_when_headroom(self):
        _sim, dev = make_device()
        gov = AdaptiveGovernor(dev, MODES["60"], MODES["60"].budget_for(dev), capacity=60)
        gov.budget.chunks = 3
        gov.budget.particle_view = 0.05
        for _ in range(5):
            decision = gov.update(59.5, thermal=0)
        self.assertGreater(gov.budget.chunks, 3)
        self.assertTrue(decision.actions)

    def test_simulate_series(self):
        _sim, dev = make_device()
        decisions = simulate(dev, MODES["120"], [40, 42, 45, 50, 55, 58, 60])
        self.assertEqual(len(decisions), 7)
        self.assertTrue(all(d.to_dict()["measured_fps"] >= 0 for d in decisions))

    def test_target_never_exceeds_capacity(self):
        _sim, dev = make_device()
        gov = AdaptiveGovernor(dev, MODES["144"], MODES["144"].budget_for(dev), capacity=70)
        self.assertLessEqual(gov.target, 70)


class TestPackForge(unittest.TestCase):
    def test_pack_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pack.mcpack")
            build_fogcut_pack(path)
            result = verify_pack(path)
            self.assertTrue(result["ok"], result["problems"])
            with zipfile.ZipFile(path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                self.assertEqual(manifest["format_version"], 2)
                self.assertEqual(manifest["modules"][0]["type"], "resources")
                self.assertNotEqual(manifest["header"]["uuid"], manifest["modules"][0]["uuid"])
                fog = json.loads(zf.read("fogs/crvx_fog_cut.json"))
                self.assertTrue(fog["fog_definitions"])
                icon = zf.read("pack_icon.png")
                self.assertTrue(icon.startswith(b"\x89PNG\r\n\x1a\n"))


class TestGenerators(unittest.TestCase):
    def test_scripts_are_valid_bash(self):
        sim, dev = make_device()
        plan = Planner(sim).plan(dev, "120", risk="root")
        script, undo = generators.posix_script(plan, dev)
        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn("trap ", script)
        self.assertTrue(script.count("run '") > 10)
        self.assertIn("#!/usr/bin/env bash", undo)
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in (("a.sh", script), ("b.sh", undo),
                               ("c.sh", generators.termux_script(plan, dev)),
                               ("d.sh", generators.ondevice_script(plan, dev, root=True)),
                               ("e.sh", generators.ondevice_undo_script(plan, dev))):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
                self.assertEqual(os.system(f"bash -n {path}"), 0, f"{name} tidak valid")

    def test_bat_has_no_raw_ampersand_in_echo(self):
        sim, dev = make_device()
        plan = Planner(sim).plan(dev, "120")
        bat = generators.windows_script(plan, dev)
        for line in bat.splitlines():
            if line.startswith("echo ["):
                self.assertNotIn(" & ", line)

    def test_markdown_report(self):
        sim, dev = make_device()
        plan = Planner(sim).plan(dev, "120")
        report = generators.markdown_report(plan, dev)
        self.assertIn("# CRVX TURBOFRAME", report)
        self.assertIn("## Proyeksi", report)
        self.assertIn("gfx_viewdistance", report)

    def test_ondevice_undo_runs_inside_device_shell(self):
        """Undo on-device ditempel ke LADB/Shizuku: tidak boleh ada prefiks adb."""
        sim, dev = make_device()
        plan = Planner(sim).plan(dev, "120", risk="root")
        undo = generators.ondevice_undo_script(plan, dev, root=False)
        self.assertIn("#!/system/bin/sh", undo)
        self.assertNotIn("adb ", undo)
        self.assertIn("settings delete", undo)
        self.assertIn("device_config delete", undo)
        self.assertIn("optbisa()", undo)
        restores = [l for l in undo.splitlines()
                    if l.strip() and not l.startswith("#") and not l.startswith("echo")]
        self.assertTrue(len(restores) > 5, "terlalu sedikit perintah pemulihan")

    def test_ondevice_guards_unwritable_options_txt(self):
        """Android 11+: options.txt tak terbaca dari shell -> skrip harus sadar & memberi nilai manual."""
        sim, dev = make_device()
        plan = Planner(sim).plan(dev, "120")
        script = generators.ondevice_script(plan, dev, root=False)
        self.assertIn("optbisa()", script)
        self.assertIn("[LEWAT]", script)
        self.assertIn("gfx_viewdistance = ", script)
        self.assertIn(dev.minecraft.options_path, script)


class TestServerApi(unittest.TestCase):
    def setUp(self):
        from crvx.server import make_handler, Engine
        from http.server import ThreadingHTTPServer
        import threading
        self.engine = Engine(sim=True)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _get(self, path):
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as res:
            return res.status, res.read()

    def _post(self, path, payload=None):
        import urllib.request
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read())

    def test_state_and_flow(self):
        status, body = self._get("/api/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertIn("device", state)
        self.assertEqual([m["id"] for m in state["modes"]], ["60", "90", "120", "144"])

        plan = self._post("/api/plan", {"mode": "120", "risk": "advanced"})
        self.assertGreater(len(plan["steps"]), 5)

        applied = self._post("/api/apply", {})
        self.assertEqual(applied["failed"], [])

        result = self._post("/api/bench", {"duration": 3, "label": "after"})
        self.assertGreater(result["frames"], 0)

        decision = self._post("/api/govern/tick", {"mode": "120"})
        self.assertIn("measured_fps", decision)

        undo = self._post("/api/undo", {})
        self.assertGreater(undo["restored"], 0)

        for fmt in ("sh", "bat", "termux", "ondevice", "md", "json"):
            status, body = self._get(f"/api/export/{fmt}")
            self.assertEqual(status, 200, fmt)
            self.assertGreater(len(body), 200, fmt)

        status, body = self._get("/api/pack")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"PK"))

        status, _ = self._get("/")
        self.assertEqual(status, 200)

    def test_static_traversal_blocked(self):
        import urllib.error
        try:
            status, body = self._get("/../../etc/passwd")
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read()
        self.assertIn(status, (403, 404))
        self.assertNotIn(b"root:x:0:0", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
