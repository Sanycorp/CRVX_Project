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


class TestAddonForge(unittest.TestCase):
    """Add-on dalam game: .mcaddon (RP fog + BP fungsi + AutoGovernor script)."""

    def build(self, tmp):
        from crvx.addonforge import build_addon
        return build_addon(os.path.join(tmp, "CRVX_Turbo60.mcaddon"))

    def test_addon_valid(self):
        from crvx.addonforge import verify_addon
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build(tmp)
            hasil = verify_addon(path)
            self.assertTrue(hasil["ok"], str(hasil["problems"]))
            self.assertEqual(len(hasil["packs"]), 3)
            self.assertGreater(hasil["size_bytes"], 10000)
            folders = {p["folder"] for p in hasil["packs"]}
            self.assertIn("CRVX_Turbo60_RP", folders)
            self.assertIn("CRVX_Turbo60_BP", folders)
            self.assertIn("CRVX_AutoGovernor_BP", folders)

    def test_uuids_stabil_dan_unik(self):
        import json as _json
        import zipfile as _zip
        from crvx.addonforge import _uuid
        with tempfile.TemporaryDirectory() as tmp:
            a = self.build(tmp)
            b = self.build(os.path.join(tmp, "sub"))
            with _zip.ZipFile(a) as za, _zip.ZipFile(b) as zb:
                for folder in ("CRVX_Turbo60_RP", "CRVX_Turbo60_BP"):
                    ua = _json.loads(za.read(f"{folder}/manifest.json"))["header"]["uuid"]
                    ub = _json.loads(zb.read(f"{folder}/manifest.json"))["header"]["uuid"]
                    self.assertEqual(ua, ub, "uuid harus deterministik")
        self.assertNotEqual(_uuid("A", "header"), _uuid("B", "header"))

    def test_fungsi_mcfunction_bersih(self):
        import zipfile as _zip
        from crvx.addonforge import functions
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build(tmp)
            with _zip.ZipFile(path) as zf:
                nama = set()
                for entry in zf.namelist():
                    if not entry.endswith(".mcfunction"):
                        continue
                    if "/functions/gov/" in entry:
                        continue          # fungsi internal governor, diuji terpisah
                    nama.add(entry.rsplit("/", 1)[-1][:-len(".mcfunction")])
                    isi = zf.read(entry).decode("utf-8")
                    for baris in isi.splitlines():
                        baris = baris.strip()
                        if not baris or baris.startswith("#"):
                            continue
                        self.assertFalse(baris.startswith("/"), f"{entry}: ada '/' di depan")
                        if baris.startswith("gamerule"):
                            # 2 token = query (dipakai status), 3 token = setter
                            self.assertIn(len(baris.split()), (2, 3))
                self.assertEqual(nama, set(functions().keys()))
                self.assertIn("pulihkan", nama)

    def test_script_governor(self):
        import zipfile as _zip
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build(tmp)
            with _zip.ZipFile(path) as zf:
                man = _json_load(zf.read("CRVX_AutoGovernor_BP/manifest.json"))
                deps = man["dependencies"]
                self.assertEqual(deps[0]["module_name"], "@minecraft/server")
                self.assertEqual(deps[0]["version"], "2.0.0",
                                 "versi API terbaru membuat skrip gagal muat di "
                                 "klien yang tidak mendukungnya persis")
                self.assertEqual(deps[1]["version"], "2.0.0")
                self.assertEqual(man["modules"][1]["type"], "script")
                js = zf.read("CRVX_AutoGovernor_BP/scripts/main.js").decode("utf-8")
                for wajib in ("import { world, system }", "system.runInterval",
                              "function gov/l", "function gov/profil_",
                              "setActionBar", "itemUse", "isSneaking",
                              "scriptEventReceive", "tanganiArg",
                              "try {", "world.getDimension"):
                    self.assertIn(wajib, js)
                self.assertEqual(js.count("import "), 2, "server + server-ui")
                for wajib2 in ("ActionFormData", "@minecraft/server-ui",
                               "KP = ", "integral", "PANAS_NAIK",
                               "form.show", "setDynamicProperty",
                               "KOOLDAUN", "function gov/l", "naikBeruntun",
                               # v3.3: pengaman anti force-close
                               "ANGGARAN", "sapuBertahap", "TENANG_MUAT",
                               "sekeringPutus", "v3.3"):
                    self.assertIn(wajib2, js)
                self.assertNotIn("@@", js, "token template tidak boleh tersisa")
                # chatSend TIDAK ADA di API stabil 2.x -> boleh disebut hanya
                # sebagai feature-detect, tidak boleh dipakai langsung
                self.assertNotIn("world.beforeEvents.chatSend.subscribe", js)
                self.assertIn("typeof sinyalChat.subscribe", js,
                              "chatSend hanya boleh dipakai lewat feature-detect")

    def test_event_api_cocok_dengan_versi_yang_dideklarasikan(self):
        """Regresi '!crvx mati diam-diam': skrip pernah berlangganan event yang
        tidak ada di API stabil (world.beforeEvents.chatSend), TypeError-nya
        ditelan try/catch, dan governor jadi tak terkendali. Anggota di bawah
        disalin dari deklarasi tipe @minecraft/server 2.0.0 di npm."""
        import re as _re, zipfile as _zip
        API = {
            "world.beforeEvents": {
                "effectAdd", "entityRemove", "explosion", "itemUse",
                "playerBreakBlock", "playerGameModeChange",
                "playerInteractWithBlock", "playerInteractWithEntity",
                "playerLeave", "weatherChange"},
            "world.afterEvents": {
                "blockExplode", "buttonPush", "dataDrivenEntityTrigger",
                "effectAdd", "entityDie", "entityHealthChanged", "entityHitBlock",
                "entityHitEntity", "entityHurt", "entityLoad", "entityRemove",
                "entitySpawn", "explosion", "gameRuleChange", "itemCompleteUse",
                "itemReleaseUse", "itemStartUse", "itemStartUseOn", "itemStopUse",
                "itemStopUseOn", "itemUse", "leverAction", "pistonActivate",
                "playerBreakBlock", "playerButtonInput", "playerDimensionChange",
                "playerEmote", "playerGameModeChange", "playerInputModeChange",
                "playerInputPermissionCategoryChange", "playerInteractWithBlock",
                "playerInteractWithEntity", "playerJoin", "playerLeave",
                "playerPlaceBlock", "playerSpawn", "pressurePlatePop",
                "pressurePlatePush", "projectileHitBlock", "projectileHitEntity",
                "targetBlockHit", "tripWireTrip", "weatherChange", "worldLoad"},
            "system.afterEvents": {"scriptEventReceive"},
        }
        FEATURE_DETECT = {"chatSend"}     # hanya untuk klien 1.x, dijaga runtime
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build(tmp)
            with _zip.ZipFile(path) as zf:
                js = zf.read("CRVX_AutoGovernor_BP/scripts/main.js").decode("utf-8")
        # komentar kepala menyebut API lama sebagai penjelasan -> periksa kodenya saja
        kode = "\n".join(l for l in js.splitlines()
                         if not l.strip().startswith("//"))
        dipakai = _re.findall(r"(world|system)\.(before|after)Events\.(\w+)", kode)
        self.assertTrue(dipakai, "skrip tidak berlangganan event apa pun?")
        for obj, grup, anggota in dipakai:
            kunci = f"{obj}.{grup}Events"
            if anggota in FEATURE_DETECT:
                continue
            self.assertIn(anggota, API[kunci],
                          f"{kunci}.{anggota} tidak ada di API yang dideklarasikan "
                          f"- akan TypeError diam-diam")
        self.assertIn("itemUse", {a for _, _, a in dipakai},
                      "gestur jongkok+pakai item adalah satu-satunya kontrol "
                      "tanpa Cheats")
        # Entity.isPlayer() juga tidak ada di 2.0.0 -> harus pakai typeId
        self.assertNotIn("isPlayer", kode)
        self.assertIn("typeId", kode)

    def test_rp_berisi_fog_skema_benar_dan_awan_transparan(self):
        import zipfile as _zip
        with tempfile.TemporaryDirectory() as tmp:
            path = self.build(tmp)
            with _zip.ZipFile(path) as zf:
                awan = zf.read("CRVX_Turbo60_RP/textures/environment/clouds.png")
                self.assertEqual(awan[:8], b"\x89PNG\r\n\x1a\n")
                self.assertNotIn(255, list(awan[-400:]), "awan harus transparan penuh")
                fogs = [n for n in zf.namelist()
                        if n.startswith("CRVX_Turbo60_RP/fogs/")]
                self.assertEqual(len(fogs), 6,
                                 "73 file = beban parsing saat dunia dimuat, dan "
                                 "sebagian besar tidak menyentuh overworld")
                punya = {n.rsplit("/", 1)[-1].replace("_fog_setting.json", "")
                         for n in fogs}
                for wajib in ("default", "dry", "humid", "semi_humid", "hell",
                              "the_end"):
                    self.assertIn(wajib, punya,
                                  f"fog global '{wajib}' wajib ikut terkirim")
                for f in fogs[:12]:
                    doc = _json_load(zf.read(f))
                    self.assertIn("minecraft:fog_settings", doc,
                                  "skema lama (fog_definitions) tidak dibaca game")
                    fs = doc["minecraft:fog_settings"]
                    self.assertTrue(
                        fs["description"]["identifier"].startswith("minecraft:fog_"))
                    self.assertTrue(fs["distance"], "distance tidak boleh kosong")
                    for kunci, blok in fs["distance"].items():
                        self.assertIn(blok.get("render_distance_type"),
                                      ("render", "fixed"), f"{f}:{kunci}")
                        self.assertLess(blok["fog_start"], blok["fog_end"], f"{f}:{kunci}")
                    nama = f.rsplit("/", 1)[-1]
                    if nama.startswith(("default_", "dry_", "humid_",
                                        "semi_humid_")):
                        # aturan lama melarang blok lava -> seluruh identifier
                        # global dilewati dan fog tak pernah sampai ke overworld
                        self.assertIn("lava", fs["distance"], f"{f}: lava hilang")
                        self.assertIn("lava_resistance", fs["distance"], f)
                        self.assertIn("transition_fog", fs["distance"]["water"],
                                      "transisi air vanilla harus disalin utuh")


class TestAntiBadaiPerintah(unittest.TestCase):
    """Regresi force-close: satu tick tidak boleh memuat lusinan `kill @e[...]`."""

    def test_tidak_ada_fungsi_dengan_lebih_dua_kill(self):
        from crvx.addonforge import functions, gov_functions
        for nama, baris in {**functions(), **{f"gov/{k}": v
                                             for k, v in gov_functions().items()}}.items():
            kill = [b for b in baris if b.startswith("kill ")]
            self.assertLessEqual(len(kill), 2,
                                 f"{nama}: {len(kill)} kill = badai dalam satu tick")
            self.assertLessEqual(len(baris), 14,
                                 f"{nama}: {len(baris)} perintah sekaligus terlalu berat")

    def test_selector_bedrock_valid(self):
        from crvx.addonforge import functions, gov_functions
        for nama, baris in {**functions(), **gov_functions()}.items():
            for baris in baris:
                self.assertNotIn("rm=", baris,
                                 f"{nama}: 'rm=' tidak ada di Bedrock (benar 'r=')")
                self.assertFalse(baris.startswith("/"), nama)

    def test_level_max_tidak_memusnahkan_mob(self):
        from crvx.addonforge import gov_functions
        l3 = " ".join(gov_functions()["l3"])
        self.assertIn("domobspawning false", l3)
        for jenis in ("zombie", "creeper", "skeleton", "piglin", "enderman"):
            self.assertNotIn(jenis, l3,
                             "level MAX mematikan spawning, bukan memusnahkan "
                             "mob dunia pemain")

    def test_verifier_menolak_badai_kill(self):
        import zipfile as _zip
        from crvx.addonforge import build_addon, verify_addon
        with tempfile.TemporaryDirectory() as tmp:
            src = build_addon(os.path.join(tmp, "sumber.mcaddon"))
            rusak = os.path.join(tmp, "rusak.mcaddon")
            with _zip.ZipFile(src) as zin, _zip.ZipFile(rusak, "w") as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.endswith("gov/l3.mcfunction"):
                        data = ("\n".join([f"kill @e[type=item{i}]"
                                            for i in range(12)])).encode("utf-8")
                    if item.filename.endswith("crvx/bersihkan.mcfunction"):
                        data = b"kill @e[type=zombie,rm=40]\n"
                    zout.writestr(item, data)
            hasil = verify_addon(rusak)
            self.assertFalse(hasil["ok"])
            teks = " ".join(hasil["problems"])
            self.assertIn("badai", teks)
            self.assertIn("rm=", teks)


class TestFogForge(unittest.TestCase):
    """Skema fog diverifikasi terhadap Mojang/bedrock-samples (80 identifier)."""

    def test_cakupan_dan_skema(self):
        from crvx import fogforge
        cakup = fogforge.coverage()
        self.assertEqual(cakup["total"], 80)
        self.assertEqual(cakup["ditimpa"], 6)
        self.assertNotIn("minecraft:fog_default", fogforge.skipped(),
                         "fog_default justru yang paling menentukan tampilan "
                         "overworld - wajib ditimpa, bukan dilewati")
        for ident in fogforge.TARGETS:
            doc = fogforge.fog_definition(ident)
            self.assertEqual(set(doc.keys()), {"format_version", "minecraft:fog_settings"})
            self.assertIn(doc["format_version"], ("1.16.100", "1.21.90"))
            fs = doc["minecraft:fog_settings"]
            self.assertEqual(fs["description"]["identifier"], ident)
            self.assertIn("air", fs["distance"], "tanpa blok air fog tidak berguna")
        self.assertEqual(sorted(fogforge.fog_files()), [
            "fogs/default_fog_setting.json", "fogs/dry_fog_setting.json",
            "fogs/hell_fog_setting.json", "fogs/humid_fog_setting.json",
            "fogs/semi_humid_fog_setting.json", "fogs/the_end_fog_setting.json"])
        # format_version harus cocok dengan vanilla per identifier
        self.assertEqual(fogforge.fog_definition("minecraft:fog_default")["format_version"],
                         "1.16.100")
        self.assertEqual(fogforge.fog_definition("minecraft:fog_dry")["format_version"],
                         "1.21.90")
        self.assertEqual(fogforge.fog_definition("minecraft:fog_hell")["format_version"],
                         "1.16.100")
        # nether: air/weather vanilla bertipe fixed (meter), bukan render
        hell = fogforge.fog_definition("minecraft:fog_hell")["minecraft:fog_settings"]
        self.assertEqual(hell["distance"]["air"]["render_distance_type"], "fixed")

    def test_densitas_mengubah_jarak_bukan_warna(self):
        from crvx import fogforge
        ringan = fogforge.fog_definition("minecraft:fog_default", 0.15)
        pekat = fogforge.fog_definition("minecraft:fog_default", 0.85)
        r = ringan["minecraft:fog_settings"]["distance"]
        k = pekat["minecraft:fog_settings"]["distance"]
        self.assertLess(k["air"]["fog_start"], r["air"]["fog_start"],
                        "densitas lebih tinggi -> kabut mulai lebih dekat")
        self.assertEqual(r["air"]["fog_color"], "#ABD2FF",
                         "warna udara vanilla tidak boleh diubah")
        self.assertEqual(r["water"], k["water"], "blok air harus verbatim vanilla")
        self.assertEqual(r["lava"], k["lava"], "blok lava harus verbatim vanilla")
        self.assertEqual(r["lava"]["fog_end"], 0.64)

    def test_identifier_tidak_ditebak_dari_namafile(self):
        from crvx import fogforge
        index = fogforge.load_index()
        self.assertEqual(index["minecraft:fog_mega_spruce_taiga_mutated"]["file"],
                         "mega_spruse_taiga_mutated")
        self.assertEqual(index["minecraft:fog_sulfur_caves"]["file"], "sulfur_cave")


class TestFoliage(unittest.TestCase):
    """Tekstur 16x16 alpha-biner buatan sendiri pada path vanilla terverifikasi."""

    def test_alpha_biner_dan_path(self):
        from crvx import foliage
        ent = foliage.entries()
        self.assertEqual(len(ent), 27)
        for nama in ("leaves_oak_opaque", "glass", "glass_pane_top", "ice",
                     "ice_packed", "frosted_ice_0", "frosted_ice_3", "ladder",
                     "vine", "tallgrass", "deadbush", "waterlily", "sapling_oak",
                     "mushroom_red", "flower_dandelion"):
            self.assertIn(f"textures/blocks/{nama}.png", ent)
        for nama in ("tallgrass", "vine", "deadbush"):
            stat = foliage.alpha_stats(ent[f"textures/blocks/{nama}.png"][2])
            self.assertEqual(stat["blend"], 0,
                             f"{nama} harus alpha biner (0 piksel blend)")
            self.assertGreater(stat["opak"], 20)
        # REGRESI: leaves_*_opaque WAJIB opak penuh. Versi berlubang membuat
        # blok daun jadi cutout -> permukaan daun yang digambar meledak.
        for nama in ("leaves_oak_opaque", "leaves_birch_opaque", "leaves_jungle_opaque"):
            stat = foliage.alpha_stats(ent[f"textures/blocks/{nama}.png"][2])
            self.assertEqual(stat["transparan"], 0, f"{nama} tidak boleh berlubang")
            self.assertEqual(stat["blend"], 0)
            self.assertEqual(stat["opak"], 256)
        stat = foliage.alpha_stats(ent["textures/blocks/glass.png"][2])
        self.assertGreater(stat["blend"], 0, "kaca memang harus translusen")


class TestBlackHole(unittest.TestCase):
    """Seni prosedural lubang hitam untuk ikon pack & tombol UI."""

    def test_horizon_hitam_dan_cincin_terang(self):
        from crvx import blackhole
        size, _, rows = blackhole.pack_icon(64)
        self.assertEqual((size, size), (64, 64))
        tengah = rows[32][32 * 4:32 * 4 + 4]
        self.assertEqual(tengah, b"\x00\x00\x00\xff", "horizon harus hitam mutlak")
        # cincin foton (sekitar 1.13x radius) harus lebih terang dari pojok
        ring = rows[int(64 * 0.515 - 64 * 0.152 * 1.13)][32 * 4:32 * 4 + 3]
        pojok = rows[2][2 * 4:2 * 4 + 3]
        self.assertGreater(sum(ring), sum(pojok) + 60)

    def test_fungsi_gov_satu_perintah_per_level(self):
        from crvx.addonforge import gov_functions
        f = gov_functions()
        for nama in ("l0", "l1", "l2", "l3", "profil_turbo",
                     "profil_hemat", "profil_ganas", "afk"):
            self.assertIn(nama, f)
            self.assertTrue(f[nama], f"{nama} kosong")
        # v3.3: tiap level MANDIRI - menyetel sendiri semua gamerule yang relevan,
        # jadi satu `function gov/l<N>` cukup dan tidak ada sisa state level
        # sebelumnya. Versi lama menumpuk: l3 = l2 + 31 perintah kill.
        def nama_rule(baris):
            return {b.split()[1] for b in baris
                    if b.startswith("gamerule") and len(b.split()) > 2}
        for atas, bawah in (("l1", "l0"), ("l2", "l1"), ("l3", "l2")):
            self.assertTrue(nama_rule(f[bawah]) <= nama_rule(f[atas]),
                            f"{atas} wajib menyetel ulang semua yang disetel {bawah}")
        self.assertIn("gamerule randomtickspeed 0", f["l2"])
        self.assertIn("gamerule domobspawning false", f["l3"])
        for nama, baris in f.items():
            for b in baris:
                self.assertFalse(b.startswith("/"), nama)
                self.assertFalse(b.startswith("kill "),
                                 f"{nama}: sapuan entity harus bertahap lewat JS, "
                                 f"bukan diborong dalam satu tick")

    def test_enam_ikon_tombol(self):
        from crvx import blackhole
        ikon = blackhole.button_icons(32)
        self.assertEqual(sorted(ikon), ["ganas", "hemat", "hud",
                                        "restore", "status", "turbo"])
        for w, h, rows in ikon.values():
            self.assertEqual((w, h), (32, 32))
            self.assertEqual(len(rows), 32)


class TestTexForge(unittest.TestCase):
    """Codec PNG murni + pack tekstur (self-authored & downscale aset user)."""

    def test_png_roundtrip(self):
        from crvx.packforge import write_png
        from crvx.texforge import read_png
        rows = [bytes((x * 16 % 256, y * 16 % 256, (x + y) * 8 % 256,
                       255 if (x + y) % 3 else 0))
                for y in range(8) for x in range(8)]
        rows = [b"".join(rows[y * 8:(y + 1) * 8]) for y in range(8)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.png")
            write_png(path, 8, 8, rows)
            with open(path, "rb") as fh:
                w, h, back = read_png(fh.read())
        self.assertEqual((w, h), (8, 8))
        self.assertEqual(back, rows, "piksel harus identik setelah roundtrip")

    def test_read_png_menolak_bukan_png(self):
        from crvx.texforge import read_png
        with self.assertRaises(ValueError):
            read_png(b"RIFF1234WEBP" + b"\x00" * 40)

    def test_downscale_rata_kotak(self):
        from crvx.texforge import downscale
        merah = bytes((200, 40, 40, 255)) * 4
        rows = [merah for _ in range(4)]
        w, h = downscale(4, 4, rows, 2, 2)[0][0:4], 2
        self.assertEqual(bytes((200, 40, 40, 255)), w)
        # gradasi: kiri gelap, kanan terang -> rata-rata harus di tengah
        grad = [bytes((0, 0, 0, 255) * 2 + (255, 255, 255, 255) * 2) for _ in range(4)]
        out = downscale(4, 4, grad, 2, 2)
        self.assertEqual(out[0][:4], bytes((0, 0, 0, 255)))
        self.assertEqual(out[0][4:8], bytes((255, 255, 255, 255)))

    def test_strip_animasi_dilewati(self):
        from crvx.packforge import write_png
        from crvx.texforge import downscale_png
        rows = [bytes(16 * 4) for _ in range(512)]      # 16x512 = flipbook strip
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "strip.png")
            write_png(path, 16, 512, rows)
            with open(path, "rb") as fh:
                self.assertIsNone(downscale_png(fh.read(), 8))

    def test_texture_entries_path_vanilla(self):
        from crvx.texforge import texture_entries
        ent = texture_entries(8)
        # path harus persis seperti vanilla Bedrock (diverifikasi dari bedrock-samples)
        self.assertIn("textures/environment/clouds.png", ent)
        self.assertIn("textures/environment/weather.png", ent)
        self.assertIn("textures/blocks/glass.png", ent)
        self.assertIn("textures/blocks/leaves_oak_opaque.png", ent)
        self.assertNotIn("textures/environment/rain.png", ent)
        w, h, rows = ent["textures/environment/clouds.png"]
        self.assertEqual((w, h), (256, 256))
        self.assertEqual(set(rows[0]), {0}, "awan harus transparan penuh")
        w, h, rows = ent["textures/environment/weather.png"]
        self.assertEqual((w, h), (32, 32))
        alpha = [rows[y][x * 4 + 3] for y in range(h) for x in range(w)]
        self.assertLess(max(alpha), 60, "cuaca harus nyaris tak terlihat")
        w, h, rows = ent["textures/blocks/leaves_oak_opaque.png"]
        self.assertEqual((w, h), (8, 8))
        alpha = [rows[y][x * 4 + 3] for y in range(h) for x in range(w)]
        self.assertIn(0, alpha, "daun butuh lubang alpha-test")
        self.assertIn(255, alpha)

    def test_build_texture_pack_valid(self):
        from crvx.packforge import verify_pack
        from crvx.texforge import build_texture_pack
        with tempfile.TemporaryDirectory() as tmp:
            path = build_texture_pack(os.path.join(tmp, "fast.mcpack"), res=8)
            hasil = verify_pack(path)
            self.assertTrue(hasil["ok"], str(hasil["problems"]))
            self.assertIn("textures/environment/weather.png", hasil["entries"])
            self.assertIn("textures/blocks/glass.png", hasil["entries"])

    def test_build_downscaled_pack(self):
        from crvx.packforge import write_png
        from crvx.texforge import build_downscaled_pack, read_png
        import zipfile as _zip
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "vanilla")
            for sub in ("textures/blocks", "textures/environment"):
                os.makedirs(os.path.join(src, sub), exist_ok=True)
            big = [bytes((i * 3 % 256, i * 5 % 256, i * 7 % 256, 255)) * 32
                   for i in range(32)]
            write_png(os.path.join(src, "textures/blocks/stone.png"), 32, 32, big)
            write_png(os.path.join(src, "textures/blocks/water_still.png"), 16, 512,
                      [bytes(16 * 4) for _ in range(512)])
            with open(os.path.join(src, "textures/terrain_texture.json"), "w") as fh:
                fh.write("{\"resource_pack_name\": \"vanilla\"}")
            out = os.path.join(tmp, "out.mcpack")
            stats = build_downscaled_pack(src, out, target=8)
            self.assertEqual(stats["converted"], 1)
            self.assertEqual(stats["skipped_animated"], 1)
            self.assertEqual(stats["atlas"], ["textures/terrain_texture.json"])
            with _zip.ZipFile(out) as zf:
                w, h, _ = read_png(zf.read("textures/blocks/stone.png"))
                self.assertEqual((w, h), (8, 8))
                w, h, _ = read_png(zf.read("textures/blocks/water_still.png"))
                self.assertEqual((w, h), (16, 512), "strip animasi tidak boleh diubah")
                self.assertIn("textures/terrain_texture.json", zf.namelist())
                self.assertNotIn("manifest.json", [n for n in zf.namelist()
                                                   if n.startswith("textures/")])



def _json_load(data):
    import json as _json
    return _json.loads(data.decode("utf-8"))



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
