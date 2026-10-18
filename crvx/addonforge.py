"""AddonForge - membangun .mcaddon Bedrock yang bekerja sepenuhnya dari dalam game.

Tanpa ADB, tanpa root, tanpa PC. Tiga pack:

1. ``CRVX_Turbo60_RP``  (resources) - enam definisi fog global yang benar-benar
   dipakai biome (bukan 73 file yang sebagian besar tidak berpengaruh) + awan
   transparan -> mengurangi fragmen alpha-blended yang digambar GPU Mali-G57.
2. ``CRVX_Turbo60_BP``  (data)      - fungsi ``/function crvx/*`` berisi preset
   gamerule + pembersihan entity -> beban CPU & block-update turun.
3. ``CRVX_AutoGovernor_BP`` (data + script) - governor adaptif memakai
   ``@minecraft/server`` 2.0.0: mengukur tick-time
   tiap 3 detik, menaikkan/menurunkan level hemat secara otomatis, dan
   menampilkan HUD di action bar. Tidak butuh Cheats, tidak mengunci achievement.

Semua UUID deterministik (uuid5) supaya import ulang tidak menduplikasi pack.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import uuid
import zipfile
from typing import Dict, List, Optional, Sequence, Tuple

from .packforge import make_icon, write_png
from .texforge import texture_entries
from . import blackhole, fogforge, foliage, gearforge

NAMESPACE = uuid.UUID("6f1c9a2e-4c7b-4d31-9c0a-2b7d5e8f1a40")
# v3.3: mendeklarasikan versi API TERBARU (2.10.0 / 2.2.0) membuat seluruh
# skrip GAGAL MUAT di klien yang tidak punya versi persis itu di daftar
# dukungannya - governor lalu mati total tanpa pesan apa pun. 2.0.0 adalah versi
# stabil pertama yang didukung semua klien era 1.21+/26.x, dan seluruh API yang
# dipakai pack ini (world, system, Dimension.runCommand, getEntities,
# setActionBar, dynamic property, ActionFormData berbasis Promise) sudah ada
# di sana. Jadi 2.0.0 = kompatibilitas maksimum tanpa kehilangan fitur.
SERVER_API = "2.0.0"
SERVER_UI_API = "2.0.0"
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

# v3.3: mcfunction hanya boleh menyapu DUA jenis. Versi lama menaruh 10-31
# perintah ``kill @e[...]`` dalam satu fungsi; tiap ``kill`` menyapu seluruh
# daftar entity dan memicu simpan-chunk serentak, sehingga satu tick bisa
# memuat 43 perintah berat - pada HP RAM 4 GB itu stutter berat sampai force
# close. ENTITY_SAMPAH tetap ada, tapi dipakai JS sebagai ANTREAN sapuan
# bertahap (1 jenis per sampel, jeda 8 detik), bukan diborong dalam satu tick.
BERSIHKAN_INTI = ["item", "xp_orb"]

FOOTER = ("# Nilai default Bedrock: randomtickspeed 1, sisanya true. "
          "Kembalikan kapan pun dengan /function crvx/pulihkan")


def _tell(text: str, color: str = "green") -> str:
    payload = {"rawtext": [
        {"text": "[CRVX] ", "color": "aqua", "bold": True},
        {"text": text, "color": color},
    ]}
    return "tellraw @a " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _bersihkan_lines(agresif: bool = False) -> List[str]:
    """Dua sapuan saja - proyektil (panah, telur, dsb) lenyap sendiri ~60 dtk
    dan jarang jadi sumber beban, jadi menyapunya hanya menambah spike tick."""
    return [f"kill @e[type={kind}]" for kind in BERSIHKAN_INTI]


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
    # v3.3: tidak lagi memanggil crvx/hemat (yang sudah menyapu) lalu menyapu
    # lagi 15x - total kill dalam satu tick dibatasi dua.
    ganas = [
        "# CRVX GANAS - FPS maksimal, konsekuensi gameplay terbesar",
        "gamerule randomtickspeed 0",
        "gamerule doweathercycle false",
        "weather clear",
        "gamerule doinsomnia false",
        "gamerule mobgriefing false",
        "gamerule dofiretick false",
        "gamerule naturalregeneration true",
        "gamerule domobspawning false",
        "gamerule doentitydrops true",
        "gamerule dotiledrops true",
        "function crvx/bersihkan",
        _tell("MODE GANAS aktif: spawning mob MATI total + random tick 0. Mob yang "
              "sudah ada tetap hidup. Kembali normal: /function crvx/pulihkan", "red"),
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


def gov_functions() -> Dict[str, List[str]]:
    """mcfunction milik pack governor: SATU perintah per perubahan level.

    v3.3: isinya HANYA gamerule. Versi lama menaruh 31 perintah ``kill @e[...]``
    di ``gov/l3`` (43 perintah total dalam satu tick) dan 12 di ``gov/l2``.
    Pembersihan entity kini dilakukan JS secara bertahap.

    Tidak ada mass-kill mob: level MAX mematikan ``domobspawning`` (sumber beban
    CPU yang sesungguhnya) tanpa memusnahkan isi dunia pemain.

    Catatan selector Bedrock: ``rm=`` (radius minimum) TIDAK ADA; yang tersedia
    hanya ``r=`` (radius maksimum). Jadi "bunuh mob yang jauh saja" tidak bisa
    ditulis dengan selector - versi lama memakai ``rm=40`` dan 19 barisnya gagal
    tanpa efek apa pun.
    """
    l0 = ["gamerule randomtickspeed 1", "gamerule domobspawning true",
          "gamerule dofiretick true", "gamerule mobgriefing true",
          "gamerule doinsomnia true", "gamerule doweathercycle true",
          "gamerule naturalregeneration true"]
    l1 = ["gamerule randomtickspeed 1", "gamerule domobspawning true",
          "gamerule dofiretick true", "gamerule mobgriefing true",
          "gamerule doinsomnia false", "gamerule doweathercycle false",
          "weather clear", "gamerule naturalregeneration true"]
    l2 = ["gamerule randomtickspeed 0", "gamerule domobspawning true",
          "gamerule dofiretick false", "gamerule mobgriefing false",
          "gamerule doinsomnia false", "gamerule doweathercycle false",
          "weather clear", "gamerule naturalregeneration true"]
    l3 = ["gamerule randomtickspeed 0", "gamerule domobspawning false",
          "gamerule dofiretick false", "gamerule mobgriefing false",
          "gamerule doinsomnia false", "gamerule doweathercycle false",
          "weather clear", "gamerule naturalregeneration true"]
    dasar = ["gamerule doweathercycle false", "weather clear",
             "gamerule doinsomnia false", "gamerule mobgriefing false",
             "gamerule naturalregeneration true"]
    return {
        "l0": l0, "l1": l1, "l2": l2, "l3": l3,
        "profil_turbo": dasar + ["gamerule randomtickspeed 1",
                                 "gamerule dofiretick true",
                                 "gamerule domobspawning true"],
        "profil_hemat": dasar + ["gamerule randomtickspeed 0",
                                 "gamerule dofiretick false",
                                 "gamerule domobspawning true"],
        "profil_ganas": dasar + ["gamerule randomtickspeed 0",
                                 "gamerule dofiretick false",
                                 "gamerule domobspawning false"],
        "afk": ["gamerule randomtickspeed 0"],
    }


def build_addon(out_path: str, version: Sequence[int] = (1, 3, 0),
                fog_strength: float = 0.35, governor: bool = True,
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
        os.makedirs(os.path.join(gov, "functions", "gov"), exist_ok=True)
        for nama, baris in gov_functions().items():
            _tulis(gov, f"functions/gov/{nama}.mcfunction",
                   "\n".join(baris) + "\n")
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
                    # v3.3: yang penting BUKAN jumlahnya, tapi identifier global
                    # yang benar-benar dipakai biome overworld ikut terkirim.
                    global_wajib = {"default", "dry", "humid", "semi_humid"}
                    punya = {os.path.basename(f).replace("_fog_setting.json", "")
                             for f in fog}
                    hilang = sorted(global_wajib - punya)
                    if hilang:
                        problems.append(f"{folder}: definisi fog global hilang: "
                                        f"{', '.join(hilang)} (biome overworld tidak "
                                        f"terpengaruh tanpa ini)")
                    if len(fog) > 12:
                        problems.append(f"{folder}: {len(fog)} file fog terlalu banyak "
                                        f"(beban parsing saat dunia dimuat; cukup 6)")
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
                        # v3.3 dibalik: blok lava HARUS ada (disalin verbatim
                        # vanilla). Aturan lama "jangan ada lava" membuat seluruh
                        # identifier global dilewati, sehingga fog tidak pernah
                        # sampai ke overworld.
                        if os.path.basename(f).startswith(("default_", "dry_",
                                                          "humid_", "semi_humid_")):
                            for wajib_lava in ("lava", "lava_resistance"):
                                if wajib_lava not in dist:
                                    problems.append(f"{f}: blok {wajib_lava} hilang - "
                                                    f"fog lava vanilla ikut terhapus")
                        for kunci, blok in dist.items():
                            rdt = blok.get("render_distance_type")
                            if rdt not in ("render", "fixed"):
                                problems.append(f"{f}: {kunci}.render_distance_type "
                                                f"'{rdt}' bukan 'render'/'fixed'")
                            if not (0 <= blok.get("fog_start", -1) <
                                    blok.get("fog_end", -1)):
                                problems.append(f"{f}: {kunci} fog_start harus < "
                                                f"fog_end dan >= 0")
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
                        kill = [b for b in perintah if b.startswith("kill ")]
                        if len(kill) > 2:
                            problems.append(f"{f}: {len(kill)} perintah kill dalam satu "
                                            f"fungsi = badai entity dalam satu tick "
                                            f"(maks 2)")
                        for baris in perintah:
                            if baris.startswith("/"):
                                problems.append(f"{f}: mcfunction tidak boleh diawali '/'")
                            if re.search(r"\brm=", baris):
                                problems.append(f"{f}: selector 'rm=' tidak ada di "
                                                f"Bedrock (yang benar 'r='): {baris}")
                result["packs"].append({"folder": folder, "name": header.get("name"),
                                        "types": types, "uuid": header.get("uuid")})
            if len(uuids) < 2:
                problems.append("uuid pack tidak unik")
    except (zipfile.BadZipFile, OSError) as exc:
        problems.append(f"arsip rusak: {exc}")

    result["ok"] = not problems
    return result


# --------------------------------------------------------------------------- #
# Arsenal: armor 3D + pedang (CRVX Void Arsenal)
# --------------------------------------------------------------------------- #
ARSENAL_RP_NAME = "CRVX Void Arsenal - Model & Tekstur"
ARSENAL_BP_NAME = "CRVX Void Arsenal - Item & Resep"
ARSENAL_RP = "CRVX_VoidArsenal_RP"
ARSENAL_BP = "CRVX_VoidArsenal_BP"

SLOT_WEARABLE_RESMI = {"slot.armor.head", "slot.armor.chest", "slot.armor.legs",
                       "slot.armor.feet", "slot.armor.body",
                       "slot.weapon.mainhand", "slot.weapon.offhand"}
SLOT_ENCHANT_RESMI = ("none|all|g_armor|armor_head|armor_torso|armor_feet|"
                      "armor_legs|sword|bow|spear|crossbow|melee_spear|g_tool|hoe|"
                      "shears|flintsteel|shield|g_digging|axe|pickaxe|shovel|"
                      "fishing_rod|carrot_stick|elytra|cosmetic_head")
TULANG_PEMAIN = {"waist", "body", "head", "rightArm", "leftArm",
                 "rightLeg", "leftLeg"}


def build_arsenal(out_path: str, version: Sequence[int] = (1, 0, 0)) -> str:
    """Bangun ``.mcaddon`` armor 3D + pedang. Kembalikan path-nya."""
    version = list(version)
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = out_path + ".src"
    if os.path.exists(staging):
        shutil.rmtree(staging)

    stat = gearforge.statistik()
    rp = os.path.join(staging, ARSENAL_RP)
    os.makedirs(os.path.join(rp, "attachables"), exist_ok=True)
    os.makedirs(os.path.join(rp, "models", "entity"), exist_ok=True)
    os.makedirs(os.path.join(rp, "texts"), exist_ok=True)
    write_png(os.path.join(rp, "pack_icon.png"), 128, 128,
              blackhole.pack_icon(128, "ganas")[2])
    _tulis(rp, "manifest.json", json.dumps(
        manifest(ARSENAL_RP_NAME,
                 f"Model 3D armor Singularitas ({stat['jumlah_kubus']} kubus pada "
                 f"kerangka pemain vanilla) + pedang 3D yang menempel di tangan. "
                 f"Tekstur & geometry buatan sendiri, bukan aset Mojang.",
                 version, "resources", MIN_ENGINE_RP), indent=2, ensure_ascii=False))
    for rel, doc in gearforge.attachables().items():
        _tulis(rp, rel, json.dumps(doc, indent=2, ensure_ascii=False))
    for rel, doc in gearforge.geometries().items():
        _tulis(rp, rel, json.dumps(doc, indent=2, ensure_ascii=False))
    for rel, (w, h, rows) in gearforge.textures().items():
        target = os.path.join(rp, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_png(target, w, h, rows)
    _tulis(rp, "textures/item_texture.json",
           json.dumps(gearforge.item_texture(), indent=2, ensure_ascii=False))
    _tulis(rp, "texts/en_US.lang",
           f"pack.name={ARSENAL_RP_NAME}\npack.description=CRVX Void Arsenal 3D\n")
    _tulis(rp, "texts/id_ID.lang",
           f"pack.name={ARSENAL_RP_NAME}\n"
           f"pack.description=Armor & pedang 3D CRVX Void Arsenal\n")
    _tulis(rp, "texts/languages.json", json.dumps(["en_US", "id_ID"], indent=2))

    bp = os.path.join(staging, ARSENAL_BP)
    os.makedirs(os.path.join(bp, "items"), exist_ok=True)
    os.makedirs(os.path.join(bp, "recipes"), exist_ok=True)
    write_png(os.path.join(bp, "pack_icon.png"), 128, 128,
              blackhole.pack_icon(128, "inti")[2])
    _tulis(bp, "manifest.json", json.dumps(
        manifest(ARSENAL_BP_NAME,
                 f"4 potong armor Singularitas (proteksi total {stat['proteksi_total']}, "
                 f"durability ~{stat['durability_rata']}) + Pedang Singularitas "
                 f"(damage {stat['damage_pedang']}). Bisa dibuat di crafting table "
                 f"dengan netherite ingot + echo shard - tanpa Cheats.",
                 version, "data", MIN_ENGINE_BP,
                 dependencies=[{"uuid": _uuid(ARSENAL_RP_NAME, "header"),
                                "version": version}]),
        indent=2, ensure_ascii=False))
    for rel, doc in gearforge.items().items():
        _tulis(bp, rel, json.dumps(doc, indent=2, ensure_ascii=False))
    for rel, doc in gearforge.recipes().items():
        _tulis(bp, rel, json.dumps(doc, indent=2, ensure_ascii=False))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pack in (rp, bp):
            base = os.path.basename(pack)
            for root, _dirs, files in os.walk(pack):
                for fname in sorted(files):
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, pack).replace(os.sep, "/")
                    zf.write(full, f"{base}/{rel}")
    shutil.rmtree(staging, ignore_errors=True)
    return out_path


def _kotak_uv(cube: Dict[str, object]) -> Tuple[int, int, int, int]:
    w, h, d = cube["size"]                       # type: ignore[index]
    u, v = cube["uv"]                            # type: ignore[index]
    return (int(u), int(v), 2 * (int(w) + int(d)), int(h) + int(d))


def verify_arsenal(path: str) -> Dict[str, object]:
    """Validasi .mcaddon arsenal: geometry, attachable, item, resep, tekstur."""
    problems: List[str] = []
    result: Dict[str, object] = {"ok": False, "problems": problems, "packs": [],
                                 "size_bytes": 0, "entries": [],
                                 "geometries": [], "items": [], "recipes": []}
    if not os.path.exists(path):
        problems.append(f"file tidak ada: {path}")
        return result
    result["size_bytes"] = os.path.getsize(path)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            result["entries"] = names
            for wajib in (f"{ARSENAL_RP}/manifest.json", f"{ARSENAL_BP}/manifest.json"):
                if wajib not in names:
                    problems.append(f"{wajib} tidak ada")
            uuids = set()
            for folder in (ARSENAL_RP, ARSENAL_BP):
                man = f"{folder}/manifest.json"
                if man not in names:
                    continue
                data = json.loads(zf.read(man).decode("utf-8"))
                uuids.add(data["header"]["uuid"])
                result["packs"].append({"folder": folder,
                                        "name": data["header"].get("name"),
                                        "types": [m.get("type")
                                                  for m in data.get("modules", [])]})
            if len(uuids) < 2:
                problems.append("uuid pack tidak unik")

            def baca(n):
                return json.loads(zf.read(n).decode("utf-8"))

            # ---- 1. geometry ------------------------------------------------ #
            geo_ids = set()
            for n in [x for x in names if x.endswith(".geo.json")]:
                doc = baca(n)
                if doc.get("format_version") != "1.16.0":
                    problems.append(f"{n}: format_version harus 1.16.0")
                for blok in doc.get("minecraft:geometry", []):
                    desc = blok.get("description", {})
                    ident = desc.get("identifier", "")
                    if not ident.startswith("geometry."):
                        problems.append(f"{n}: identifier harus geometry.* ({ident})")
                    if ident in geo_ids:
                        problems.append(f"{n}: identifier geometry duplikat {ident}")
                    geo_ids.add(ident)
                    result["geometries"].append(ident)
                    tw, th = desc.get("texture_width"), desc.get("texture_height")
                    if not isinstance(tw, int) or not isinstance(th, int):
                        problems.append(f"{n}: texture_width/height harus int")
                        continue
                    bones = blok.get("bones", [])
                    nama_bone = [b.get("name") for b in bones]
                    if len(set(nama_bone)) != len(nama_bone):
                        problems.append(f"{n}: nama bone duplikat")
                    for b in bones:
                        par = b.get("parent")
                        if par and par not in nama_bone:
                            problems.append(f"{n}: bone {b.get('name')} punya parent "
                                            f"tak dikenal ({par})")
                        if "pivot" not in b:
                            problems.append(f"{n}: bone {b.get('name')} tanpa pivot")
                    kotak = []
                    for b in bones:
                        for c in b.get("cubes", []):
                            if any(not isinstance(x, int) or x <= 0 for x in c["size"]):
                                problems.append(f"{n}: ukuran kubus harus int > 0 "
                                                f"({c['size']})")
                            kotak.append(_kotak_uv(c))
                            u, v, bw, bh = kotak[-1]
                            if u < 0 or v < 0 or u + bw > tw or v + bh > th:
                                problems.append(f"{n}: uv {(u, v)} kotak {(bw, bh)} "
                                                f"keluar tekstur {tw}x{th}")
                    for i, a in enumerate(kotak):
                        for bb in kotak[i + 1:]:
                            if (a[0] < bb[0] + bb[2] and bb[0] < a[0] + a[2] and
                                    a[1] < bb[1] + bb[3] and bb[1] < a[1] + a[3]):
                                problems.append(f"{n}: kotak UV tumpang tindih "
                                                f"{a} vs {bb} (tekstur akan bocor)")
                    if "blade" in n:
                        utama = [b for b in bones if b.get("name") == "bb_main"]
                        if not utama:
                            problems.append(f"{n}: pedang butuh bone bb_main")
                        else:
                            if utama[0].get("binding") != \
                                    "q.item_slot_to_bone_name(context.item_slot)":
                                problems.append(f"{n}: binding salah - item tidak "
                                                f"akan menempel di tangan")
                            if not utama[0].get("rotation"):
                                problems.append(f"{n}: pedang butuh rotation")
                    else:
                        hilang = TULANG_PEMAIN - set(nama_bone)
                        if hilang:
                            problems.append(f"{n}: tulang pemain hilang {sorted(hilang)}"
                                            f" - armor tidak ikut bergerak")

            # ---- 2. attachable --------------------------------------------- #
            item_ids = set()
            ikon_keys = set()
            for n in [x for x in names if "/items/" in x and x.endswith(".json")]:
                doc = baca(n)
                ident = doc["minecraft:item"]["description"]["identifier"]
                item_ids.add(ident)
                result["items"].append(ident)
            itex = f"{ARSENAL_RP}/textures/item_texture.json"
            if itex not in names:
                problems.append("textures/item_texture.json tidak ada")
            else:
                t = baca(itex)
                if t.get("texture_name") != "atlas.items":
                    problems.append("item_texture.json: texture_name harus atlas.items")
                for kunci, val in t.get("texture_data", {}).items():
                    ikon_keys.add(kunci)
                    png = val["textures"] + ".png"
                    if f"{ARSENAL_RP}/{png}" not in names:
                        problems.append(f"item_texture.json: {kunci} -> {png} tidak ada")
            attach_ids = set()
            for n in [x for x in names if "/attachables/" in x]:
                doc = baca(n)
                if doc.get("format_version") not in ("1.10.0", "1.20.30"):
                    problems.append(f"{n}: format_version attachable tak dikenal")
                desc = doc.get("minecraft:attachable", {}).get("description", {})
                ident = desc.get("identifier", "")
                if ident in attach_ids:
                    problems.append(f"{n}: identifier attachable duplikat {ident}")
                attach_ids.add(ident)
                for slot in ("default", "enchanted"):
                    if slot not in desc.get("materials", {}):
                        problems.append(f"{n}: materials.{slot} tidak ada")
                    if slot not in desc.get("textures", {}):
                        problems.append(f"{n}: textures.{slot} tidak ada")
                tex = desc.get("textures", {}).get("default", "")
                if tex and f"{ARSENAL_RP}/{tex}.png" not in names:
                    problems.append(f"{n}: tekstur model {tex}.png tidak ada")
                geo = desc.get("geometry", {}).get("default", "")
                if geo and geo not in geo_ids:
                    problems.append(f"{n}: geometry {geo} tidak didefinisikan")
                if not desc.get("render_controllers"):
                    problems.append(f"{n}: render_controllers kosong")
                for item_key in desc.get("item", {}):
                    if item_key not in item_ids:
                        problems.append(f"{n}: pemetaan item {item_key} bukan item "
                                        f"yang didefinisikan pack ini")
            for ident in sorted(item_ids):
                if ident not in attach_ids:
                    problems.append(f"item {ident} tidak punya attachable")

            # ---- 3. komponen item ------------------------------------------- #
            for n in [x for x in names if "/items/" in x and x.endswith(".json")]:
                doc = baca(n)
                if doc.get("format_version") != gearforge.ITEM_FORMAT:
                    problems.append(f"{n}: format_version harus "
                                    f"{gearforge.ITEM_FORMAT}")
                item = doc["minecraft:item"]
                comp = item.get("components", {})
                ikon = comp.get("minecraft:icon", {}).get("texture")
                if ikon not in ikon_keys:
                    problems.append(f"{n}: icon '{ikon}' tidak terdaftar di "
                                    f"item_texture.json")
                if not comp.get("minecraft:display_name", {}).get("value"):
                    problems.append(f"{n}: display_name kosong")
                dur = comp.get("minecraft:durability", {}).get("max_durability", 0)
                if not isinstance(dur, int) or dur <= 0:
                    problems.append(f"{n}: durability tidak valid")
                ench = comp.get("minecraft:enchantable", {})
                if not re.fullmatch(SLOT_ENCHANT_RESMI, str(ench.get("slot", ""))):
                    problems.append(f"{n}: enchantable.slot '{ench.get('slot')}' "
                                    f"bukan nilai resmi")
                wear = comp.get("minecraft:wearable")
                if wear is not None:
                    if wear.get("slot") not in SLOT_WEARABLE_RESMI:
                        problems.append(f"{n}: wearable.slot '{wear.get('slot')}' "
                                        f"bukan slot resmi")
                    if not isinstance(wear.get("protection"), int):
                        problems.append(f"{n}: wearable.protection harus int")
                if "blade" in n:
                    dmg = comp.get("minecraft:damage", {}).get("value", 0)
                    if not isinstance(dmg, int) or dmg <= 0:
                        problems.append(f"{n}: damage pedang tidak valid")
                    if not comp.get("minecraft:hand_equipped"):
                        problems.append(f"{n}: pedang tanpa hand_equipped")

            # ---- 4. resep ---------------------------------------------------- #
            for n in [x for x in names if "/recipes/" in x]:
                doc = baca(n)
                rec = doc.get("minecraft:recipe_shaped", {})
                result["recipes"].append(rec["description"]["identifier"])
                if "crafting_table" not in rec.get("tags", []):
                    problems.append(f"{n}: tags harus memuat crafting_table")
                pola = rec.get("pattern", [])
                if not 1 <= len(pola) <= 3:
                    problems.append(f"{n}: pattern harus 1-3 baris")
                kunci = rec.get("key", {})
                for baris in pola:
                    if len(baris) > 3:
                        problems.append(f"{n}: baris pattern > 3 kolom")
                    for ch in baris:
                        if ch != " " and ch not in kunci:
                            problems.append(f"{n}: karakter '{ch}' tidak ada di key")
                hasil = rec.get("result", {}).get("item")
                if hasil not in item_ids:
                    problems.append(f"{n}: result {hasil} bukan item pack ini")
                if not rec.get("unlock"):
                    problems.append(f"{n}: resep tanpa unlock tidak muncul di buku resep")

            # ---- 5. tekstur PNG ---------------------------------------------- #
            for n in [x for x in names if x.endswith(".png")]:
                data = zf.read(n)
                if data[:8] != b"\x89PNG\r\n\x1a\n":
                    problems.append(f"{n}: bukan PNG valid")
                    continue
                w, h = struct.unpack(">II", data[16:24])
                if "/textures/items/" in n and (w, h) != (16, 16):
                    problems.append(f"{n}: ikon item harus 16x16 (dapat {w}x{h})")
                if "/textures/models/" in n and (w, h) != (64, 64):
                    problems.append(f"{n}: tekstur model harus 64x64 (dapat {w}x{h})")
    except (zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
        problems.append(f"gagal memeriksa: {exc}")
    result["ok"] = not problems
    return result
