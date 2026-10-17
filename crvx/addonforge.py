"""AddonForge - membangun .mcaddon Bedrock yang bekerja sepenuhnya dari dalam game.

Tanpa ADB, tanpa root, tanpa PC. Tiga pack:

1. ``CRVX_Turbo60_RP``  (resources) - definisi fog dipangkas + awan transparan
   -> mengurangi fragmen alpha-blended yang harus digambar GPU Mali-G57.
2. ``CRVX_Turbo60_BP``  (data)      - fungsi ``/function crvx/*`` berisi preset
   gamerule + pembersihan entity -> beban CPU & block-update turun.
3. ``CRVX_AutoGovernor_BP`` (data + script) - governor adaptif memakai
   ``@minecraft/server`` 2.10.0 (stabil sejak Bedrock 26.50): mengukur tick-time
   tiap 3 detik, menaikkan/menurunkan level hemat secara otomatis, dan
   menampilkan HUD di action bar. Tidak butuh Cheats, tidak mengunci achievement.

Semua UUID deterministik (uuid5) supaya import ulang tidak menduplikasi pack.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from typing import Dict, List, Optional, Sequence, Tuple

from .packforge import make_icon, write_png
from .texforge import texture_entries
from . import blackhole, fogforge, foliage

NAMESPACE = uuid.UUID("6f1c9a2e-4c7b-4d31-9c0a-2b7d5e8f1a40")
SERVER_API = "2.10.0"          # rilis stabil di Bedrock 26.50 "Wilderness Bound"
SERVER_UI_API = "2.2.0"        # rilis stabil 15 Sep 2026, bareng 26.50
MIN_ENGINE_RP = [1, 20, 0]
MIN_ENGINE_BP = [1, 20, 0]
MIN_ENGINE_SCRIPT = [1, 21, 0]

RP_NAME = "CRVX FPS Booster - Visual"
BP_NAME = "CRVX FPS Booster - Preset Performa"
GOV_NAME = "CRVX FPS Booster - AutoGovernor v3"

# --------------------------------------------------------------------------- #
# Fungsi mcfunction (dipanggil dari chat: /function crvx/<nama>)
# --------------------------------------------------------------------------- #
ENTITY_SAMPAH = [
    "item", "xp_orb", "arrow", "snowball", "egg", "ender_pearl",
    "splash_potion", "lingering_potion", "fishing_hook", "trident",
]

FOOTER = ("# Nilai default Bedrock: randomtickspeed 1, sisanya true. "
          "Kembalikan kapan pun dengan /function crvx/pulihkan")


def _tell(text: str, color: str = "green") -> str:
    payload = {"rawtext": [
        {"text": "[CRVX] ", "color": "aqua", "bold": True},
        {"text": text, "color": color},
    ]}
    return "tellraw @a " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _bersihkan_lines(agresif: bool = False) -> List[str]:
    kinds = list(ENTITY_SAMPAH)
    if agresif:
        kinds += ["fireball", "small_fireball", "wither_skull", "llama_spit", "shulker_bullet"]
    return [f"kill @e[type={kind}]" for kind in kinds]


def functions() -> Dict[str, List[str]]:
    """Peta nama fungsi -> baris perintah. Nama dipanggil ``/function crvx/<nama>``."""
    turbo = [
        "# CRVX TURBO60 - preset SEIMBANG: 60 FPS stabil, gameplay tetap normal",
        "gamerule randomtickspeed 1",
        "gamerule doweathercycle false",
        "weather clear",
        "gamerule doinsomnia false",
        "gamerule mobgriefing false",
        "gamerule dofiretick true",
        "gamerule naturalregeneration true",
        "gamerule domobspawning true",
        "function crvx/bersihkan",
        _tell("TURBO60 aktif. Cuaca dikunci cerah, phantom & mob-griefing mati, "
              "entity sampah dibersihkan. Random tick tetap 1 (tanaman masih tumbuh)."),
        _tell("Lanjut di Settings > Video: Render Distance 5 chunk, Smooth Lighting OFF, "
              "MSAA OFF, V-Sync ON, Max Frame Rate 60.", "yellow"),
    ]
    hemat = [
        "# CRVX HEMAT - baterai paling awet & suhu paling dingin",
        "gamerule randomtickspeed 0",
        "gamerule doweathercycle false",
        "weather clear",
        "gamerule doinsomnia false",
        "gamerule mobgriefing false",
        "gamerule dofiretick false",
        "gamerule naturalregeneration true",
        "gamerule domobspawning true",
        "function crvx/bersihkan",
        _tell("MODE HEMAT aktif: random tick 0 + fire tick mati = beban CPU terendah. "
              "Konsekuensi: tanaman tidak tumbuh, daun tidak gugur, es tidak mencair, "
              "api tidak menyebar & tidak padam sendiri.", "yellow"),
    ]
    ganas = [
        "# CRVX GANAS - FPS maksimal, konsekuensi gameplay terbesar",
        "function crvx/hemat",
        "gamerule domobspawning false",
        "gamerule doentitydrops true",
        "gamerule dotiledrops true",
    ] + _bersihkan_lines(agresif=True) + [
        _tell("MODE GANAS aktif: spawning mob MATI total + semua proyektil dibersihkan. "
              "Mob yang sudah ada tetap hidup. Kembali normal: /function crvx/pulihkan", "red"),
    ]
    pulihkan = [
        "# CRVX PULIHKAN - kembali persis ke default vanilla Bedrock",
        "gamerule randomtickspeed 1",
        "gamerule doweathercycle true",
        "gamerule doinsomnia true",
        "gamerule mobgriefing true",
        "gamerule dofiretick true",
        "gamerule domobspawning true",
        "gamerule naturalregeneration true",
        "gamerule doentitydrops true",
        "gamerule dotiledrops true",
        "gamerule domobloot true",
        "gamerule keepinventory false",
        _tell("Semua gamerule dikembalikan ke default vanilla. Cuaca berjalan normal lagi.", "aqua"),
    ]
    bersihkan = (["# CRVX BERSIHKAN - hapus entity sampah yang memakan tick"]
                 + _bersihkan_lines() + [_tell("Entity sampah dibersihkan.", "aqua")])
    status = [
        "# CRVX STATUS - cetak nilai gamerule yang sedang aktif",
        "gamerule randomtickspeed",
        "gamerule doweathercycle",
        "gamerule doinsomnia",
        "gamerule mobgriefing",
        "gamerule dofiretick",
        "gamerule domobspawning",
        "gamerule naturalregeneration",
        _tell("Nilai di atas adalah kondisi dunia ini sekarang. "
              "Preset: crvx/turbo60 | crvx/hemat | crvx/ganas | crvx/pulihkan", "aqua"),
    ]
    return {
        "turbo60": turbo, "hemat": hemat, "ganas": ganas,
        "pulihkan": pulihkan, "bersihkan": bersihkan, "status": status,
    }


# --------------------------------------------------------------------------- #
# Script API: governor adaptif
# --------------------------------------------------------------------------- #
def governor_script(interval: int = 60, window: int = 6) -> str:
    """Muat AutoGovernor v3 dari template ``data/governor_v3.js``.

    Template JS disimpan terpisah supaya mudah dibaca & di-lint dengan
    ``node --check``. Token ``@@...@@`` disubstitusi di sini.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "governor_v3.js")
    with open(path, "r", encoding="utf-8") as fh:
        js = fh.read()
    for token, nilai in (("@@SERVER_API@@", SERVER_API),
                         ("@@SERVER_UI_API@@", SERVER_UI_API),
                         ("@@INTERVAL@@", str(int(interval))),
                         ("@@WINDOW@@", str(int(window))),
                         ("@@KINDS@@", json.dumps(ENTITY_SAMPAH))):
        js = js.replace(token, nilai)
    return js


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(parts)))


def manifest(name: str, description: str, version: Sequence[int],
             kind: str = "resources", min_engine: Sequence[int] = MIN_ENGINE_RP,
             script_entry: Optional[str] = None,
             dependencies: Optional[List[Dict[str, object]]] = None) -> Dict[str, object]:
    """manifest.json Bedrock. ``kind``: ``resources`` (RP) atau ``data`` (BP)."""
    modules: List[Dict[str, object]] = [{
        "type": kind,
        "uuid": _uuid(name, "module", kind),
        "version": list(version),
    }]
    if script_entry:
        modules.append({
            "type": "script",
            "language": "javascript",
            "entry": script_entry,
            "uuid": _uuid(name, "module", "script"),
            "version": list(version),
        })
    return {
        "format_version": 2,
        "header": {
            "name": name,
            "description": description,
            "uuid": _uuid(name, "header"),
            "version": list(version),
            "min_engine_version": list(min_engine),
        },
        "modules": modules,
        "dependencies": dependencies or [],
        "metadata": {
            "product_type": "addon",
            "url": "https://github.com/Sanycorp/CRVX_Project",
            "generated_by": "CRVX TurboFrame AddonForge",
        },
    }


# --------------------------------------------------------------------------- #
# Penulisan berkas
# --------------------------------------------------------------------------- #
def _tulis(root: str, rel: str, isi: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(isi)


def build_addon(out_path: str, version: Sequence[int] = (1, 0, 0),
                fog_strength: float = 0.85, governor: bool = True,
                interval: int = 60, window: int = 6,
                texture_res: int = 8) -> str:
    """Bangun ``.mcaddon`` lengkap. Kembalikan path-nya."""
    from .packforge import fog_file

    version = list(version)
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = out_path + ".src"
    if os.path.exists(staging):
        shutil.rmtree(staging)

    # ---- 1. Resource pack -------------------------------------------------- #
    rp = os.path.join(staging, "CRVX_Turbo60_RP")
    os.makedirs(os.path.join(rp, "fogs"), exist_ok=True)
    os.makedirs(os.path.join(rp, "textures", "ui"), exist_ok=True)
    write_png(os.path.join(rp, "pack_icon.png"), 128, 128,
              blackhole.pack_icon(128, "status")[2])
    _tulis(rp, "manifest.json", json.dumps(
        manifest(RP_NAME,
                 f"CRVX FPS Booster: tekstur 16x16 alpha-biner buatan sendiri "
                 f"(27 permukaan transparan terberat) + awan transparan + cuaca "
                 f"nyaris tak terlihat + {len(fogforge.fog_files(fog_strength))} definisi "
                 f"fog skema benar + ikon UI lubang hitam. Bukan aset Mojang.",
                 version, "resources", MIN_ENGINE_RP), indent=2, ensure_ascii=False))
    for rel, doc in fogforge.fog_files(fog_strength).items():
        _tulis(rp, rel, json.dumps(doc, indent=2, ensure_ascii=False))
    for rel, (w, h, rows) in foliage.entries().items():
        target = os.path.join(rp, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_png(target, w, h, rows)
    for rel, (w, h, rows) in texture_entries(texture_res, only_environment=True).items():
        target = os.path.join(rp, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_png(target, w, h, rows)
    for kind, (w, h, rows) in blackhole.button_icons(32).items():
        write_png(os.path.join(rp, "textures", "ui", f"crvx_{kind}.png"), w, h, rows)
    _tulis(rp, "texts/en_US.lang",
           "pack.name=%s\npack.description=CRVX fast textures + fog + UI black hole\n" % RP_NAME)
    _tulis(rp, "texts/languages.json", json.dumps(["en_US"], indent=2))

    # ---- 2. Behavior pack fungsi ------------------------------------------ #
    bp = os.path.join(staging, "CRVX_Turbo60_BP")
    os.makedirs(os.path.join(bp, "functions", "crvx"), exist_ok=True)
    write_png(os.path.join(bp, "pack_icon.png"), 128, 128, make_icon(accent=(244, 114, 182)))
    _tulis(bp, "manifest.json", json.dumps(
        manifest(BP_NAME,
                 "Preset performa siap panggil: /function crvx/turbo60 (seimbang), "
                 "crvx/hemat (baterai & suhu), crvx/ganas (FPS maks), crvx/pulihkan.",
                 version, "data", MIN_ENGINE_BP,
                 dependencies=[{"uuid": _uuid(RP_NAME, "header"), "version": version}]),
        indent=2, ensure_ascii=False))
    for nama, baris in functions().items():
        isi = "\n".join(baris) + "\n\n" + FOOTER + "\n"
        _tulis(bp, f"functions/crvx/{nama}.mcfunction", isi)

    # ---- 3. Behavior pack governor (script API) --------------------------- #
    packs = [rp, bp]
    if governor:
        gov = os.path.join(staging, "CRVX_AutoGovernor_BP")
        os.makedirs(os.path.join(gov, "scripts"), exist_ok=True)
        write_png(os.path.join(gov, "pack_icon.png"), 128, 128,
                  make_icon(accent=(251, 191, 36)))
        _tulis(gov, "manifest.json", json.dumps(
            manifest(GOV_NAME,
                     "Governor adaptif: mengukur tick-time tiap 3 detik, otomatis "
                     "membersihkan entity & menyesuaikan gamerule saat dunia berat. "
                     "Tanpa Cheats. Kontrol chat: !crvx status|mati|nyala|hud|reset",
                     version, "data", MIN_ENGINE_SCRIPT, script_entry="scripts/main.js",
                     dependencies=[{"module_name": "@minecraft/server",
                                    "version": SERVER_API},
                                   {"module_name": "@minecraft/server-ui",
                                    "version": SERVER_UI_API}]),
            indent=2, ensure_ascii=False))
        _tulis(gov, "scripts/main.js", governor_script(interval, window))
        packs.append(gov)

    # ---- 4. Zip jadi .mcaddon --------------------------------------------- #
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pack in packs:
            base = os.path.basename(pack)
            for root, _dirs, files in os.walk(pack):
                for fname in sorted(files):
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, pack).replace(os.sep, "/")
                    zf.write(full, f"{base}/{rel}")
    shutil.rmtree(staging, ignore_errors=True)
    return out_path


# --------------------------------------------------------------------------- #
# Verifikasi
# --------------------------------------------------------------------------- #
def verify_addon(path: str) -> Dict[str, object]:
    """Validasi .mcaddon supaya tidak ditolak Minecraft saat import."""
    problems: List[str] = []
    result: Dict[str, object] = {"path": path, "ok": False, "problems": problems,
                                  "packs": [], "entries": [], "size_bytes": 0}
    if not os.path.exists(path):
        problems.append("file tidak ada")
        return result

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            result["entries"] = names
            result["size_bytes"] = os.path.getsize(path)
            folders = sorted({n.split("/")[0] for n in names if "/" in n})
            if not folders:
                problems.append(".mcaddon harus berisi folder pack di root zip")
            # pra-lintasan: kumpulkan semua uuid supaya dependency antar-pack
            # bisa divalidasi tanpa bergantung urutan folder
            uuids: Dict[str, str] = {}
            for folder in folders:
                man = f"{folder}/manifest.json"
                if man not in names:
                    continue
                try:
                    data = json.loads(zf.read(man).decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                kandidat = [data.get("header", {}).get("uuid")] + \
                    [m.get("uuid") for m in data.get("modules", [])]
                for uid in kandidat:
                    if not uid:
                        continue
                    if uid in uuids:
                        problems.append(f"{folder}: uuid {uid} bentrok dengan "
                                        f"{uuids[uid]}")
                    uuids[uid] = folder
            for folder in folders:
                man = f"{folder}/manifest.json"
                if man not in names:
                    problems.append(f"{folder}: manifest.json tidak ada")
                    continue
                try:
                    data = json.loads(zf.read(man).decode("utf-8"))
                except json.JSONDecodeError as exc:
                    problems.append(f"{folder}: manifest.json rusak ({exc})")
                    continue
                header = data.get("header", {})
                modules = data.get("modules", [])
                types = [m.get("type") for m in modules]
                if not header.get("name") or not header.get("version"):
                    problems.append(f"{folder}: header.name/version kosong")
                if not header.get("min_engine_version"):
                    problems.append(f"{folder}: min_engine_version tidak ada")
                if not types or types[0] not in ("resources", "data"):
                    problems.append(f"{folder}: modules[0].type harus resources/data")
                if f"{folder}/pack_icon.png" not in names:
                    problems.append(f"{folder}: pack_icon.png tidak ada")
                else:
                    sig = zf.read(f"{folder}/pack_icon.png")[:8]
                    if sig != b"\x89PNG\r\n\x1a\n":
                        problems.append(f"{folder}: pack_icon.png bukan PNG valid")
                for dep in data.get("dependencies", []):
                    if dep.get("module_name") == "@minecraft/server":
                        if dep.get("version") != SERVER_API:
                            problems.append(f"{folder}: @minecraft/server harus {SERVER_API}")
                    if dep.get("module_name") == "@minecraft/server-ui":
                        if dep.get("version") != SERVER_UI_API:
                            problems.append(f"{folder}: @minecraft/server-ui harus "
                                            f"{SERVER_UI_API}")
                    elif dep.get("uuid") and dep["uuid"] not in uuids:
                        problems.append(f"{folder}: dependency uuid tak dikenal "
                                        f"{dep['uuid']}")
                for mod in modules:
                    if mod.get("type") == "script":
                        entry = mod.get("entry", "")
                        if not entry:
                            problems.append(f"{folder}: modul script tanpa entry")
                        elif f"{folder}/{entry}" not in names:
                            problems.append(f"{folder}: entry script {entry} tidak ada")
                if types[0] == "resources":
                    wajib = [f"{folder}/textures/environment/weather.png",
                             f"{folder}/textures/environment/clouds.png"]
                    for w in wajib:
                        if w not in names:
                            problems.append(f"{folder}: tekstur wajib tidak ada ({w})")
                    if f"{folder}/textures/environment/rain.png" in names:
                        problems.append(f"{folder}: 'rain.png' bukan path Bedrock "
                                        f"(yang benar weather.png)")
                    fog = [n for n in names if n.startswith(folder) and "/fogs/" in n]
                    if not fog:
                        problems.append(f"{folder}: resource pack tanpa definisi fog")
                    if len(fog) < 60:
                        problems.append(f"{folder}: hanya {len(fog)} file fog "
                                        f"(vanilla punya 80 identifier)")
                    for f in fog:
                        try:
                            doc = json.loads(zf.read(f).decode("utf-8"))
                        except json.JSONDecodeError as exc:
                            problems.append(f"{f}: JSON rusak ({exc})")
                            continue
                        if not doc.get("format_version"):
                            problems.append(f"{f}: format_version tidak ada")
                        fs = doc.get("minecraft:fog_settings")
                        if not isinstance(fs, dict):
                            problems.append(f"{f}: skema salah - butuh "
                                            f"'minecraft:fog_settings' di level atas")
                            continue
                        ident = (fs.get("description") or {}).get("identifier", "")
                        if not ident.startswith("minecraft:fog_"):
                            problems.append(f"{f}: identifier tidak valid ({ident})")
                        dist = fs.get("distance") or {}
                        if not dist:
                            problems.append(f"{f}: distance kosong")
                        for bahaya in ("lava", "lava_resistance", "powder_snow"):
                            if bahaya in dist:
                                problems.append(f"{f}: kunci {bahaya} tidak boleh "
                                                f"ditimpa (merusak gameplay)")
                if types[0] == "data":
                    funcs = [n for n in names if n.startswith(folder)
                             and n.endswith(".mcfunction")]
                    scripts = [n for n in names if n.startswith(folder)
                               and n.endswith(".js")]
                    if not funcs and not scripts:
                        problems.append(f"{folder}: behavior pack tanpa fungsi/skrip")
                    for f in funcs:
                        isi = zf.read(f).decode("utf-8")
                        perintah = [l for l in isi.splitlines()
                                    if l.strip() and not l.strip().startswith("#")]
                        if not perintah:
                            problems.append(f"{f}: tidak ada perintah")
                        for baris in perintah:
                            if baris.startswith("/"):
                                problems.append(f"{f}: mcfunction tidak boleh diawali '/'")
                result["packs"].append({"folder": folder, "name": header.get("name"),
                                        "types": types, "uuid": header.get("uuid")})
            if len(uuids) < 2:
                problems.append("uuid pack tidak unik")
    except (zipfile.BadZipFile, OSError) as exc:
        problems.append(f"arsip rusak: {exc}")

    result["ok"] = not problems
    return result
