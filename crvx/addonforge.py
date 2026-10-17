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

NAMESPACE = uuid.UUID("6f1c9a2e-4c7b-4d31-9c0a-2b7d5e8f1a40")
SERVER_API = "2.10.0"          # rilis stabil di Bedrock 26.50 "Wilderness Bound"
MIN_ENGINE_RP = [1, 20, 0]
MIN_ENGINE_BP = [1, 20, 0]
MIN_ENGINE_SCRIPT = [1, 21, 0]

RP_NAME = "CRVX Turbo60 - Visual Saver"
BP_NAME = "CRVX Turbo60 - Preset Performa"
GOV_NAME = "CRVX AutoGovernor - Adaptif"

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
    """JavaScript ES module AutoGovernor v2 (entry: scripts/main.js).

    v2: proaktif (menerapkan profil dasar saat dunia dimuat, tanpa perlu
    ``/function``), sadar-dimensi (Nether mematikan fire tick), sensor tekanan
    entity (jumlah dropped item), HUD action bar, dan kendali chat ``!crvx``.
    """
    kinds = json.dumps(ENTITY_SAMPAH)
    return """// CRVX AutoGovernor v2 - governor adaptif Minecraft Bedrock (Script API %s)
// Mengukur tick-time nyata tiap %d tick, bukan menebak. Naik level saat dunia
// berat, turun perlahan setelah %d sampel sehat (hysteresis) agar tidak berosilasi.
// Tidak butuh Cheats -> achievement dunia tetap aman.
import { world, system } from "@minecraft/server";

const TAG = "\u00a7b[CRVX]\u00a7r ";
const INTERVAL = %d;                 // tick per sampel (60 tick = 3 detik @20 TPS)
const WINDOW = %d;                   // jumlah sampel untuk rata-rata
const TENANG = 3;                    // sampel sehat beruntun sebelum turun 1 level
const BATAS_ITEM = 60;               // dropped item di atas ini = tekanan entity
const SAMPAH = %s;
const LABEL = ["SEHAT", "HEMAT", "DINGIN", "MAX"];

const riwayat = [];
let level = 0;
let tenang = 0;
let terakhir = Date.now();
let profilSiap = false;
let dimensiAktif = "";
let itemTerakhir = 0;

let aktif = world.getDynamicProperty("crvx:aktif") !== 0;
let hud = world.getDynamicProperty("crvx:hud") !== 0;
let basis = world.getDynamicProperty("crvx:basis") || "turbo";

function aman(fn) { try { return fn(); } catch (e) { return null; } }
function perintah(dim, cmd) { aman(() => dim.runCommand(cmd)); }

// ---- profil dasar: diterapkan sekali tiap dunia/dimensi, tanpa /function ----
function terapkanProfil(dim, mode) {
  perintah(dim, "gamerule doweathercycle false");
  perintah(dim, "weather clear");
  perintah(dim, "gamerule doinsomnia false");
  perintah(dim, "gamerule mobgriefing false");
  perintah(dim, "gamerule naturalregeneration true");
  if (mode === "turbo") {
    perintah(dim, "gamerule randomtickspeed 1");
    perintah(dim, "gamerule domobspawning true");
  } else if (mode === "hemat") {
    perintah(dim, "gamerule randomtickspeed 0");
    perintah(dim, "gamerule dofiretick false");
    perintah(dim, "gamerule domobspawning true");
  } else if (mode === "ganas") {
    perintah(dim, "gamerule randomtickspeed 0");
    perintah(dim, "gamerule dofiretick false");
    perintah(dim, "gamerule domobspawning false");
  }
  for (const t of ["item", "xp_orb"]) perintah(dim, "kill @e[type=" + t + "]");
}

// ---- eskalasi saat tick-time memburuk ----
function terapkan(target) {
  const dim = aman(() => world.getDimension("overworld"));
  if (!dim) return;
  if (target === 0) {
    perintah(dim, "gamerule randomtickspeed " + (basis === "turbo" ? "1" : "0"));
    perintah(dim, "gamerule domobspawning " + (basis === "ganas" ? "false" : "true"));
    perintah(dim, "gamerule dofiretick " + (dimensiAktif === "nether" ? "false" : "true"));
  }
  if (target >= 1) {
    perintah(dim, "gamerule doweathercycle false");
    perintah(dim, "weather clear");
    perintah(dim, "kill @e[type=item]");
    perintah(dim, "kill @e[type=xp_orb]");
  }
  if (target >= 2) {
    perintah(dim, "gamerule randomtickspeed 0");
    perintah(dim, "gamerule dofiretick false");
    perintah(dim, "gamerule doinsomnia false");
    for (const t of SAMPAH) perintah(dim, "kill @e[type=" + t + "]");
  }
  if (target >= 3) {
    perintah(dim, "gamerule mobgriefing false");
    perintah(dim, "gamerule domobspawning false");
  }
  level = target;
}

function tingkatKe(tps) {
  if (tps >= 19.2) return 0;
  if (tps >= 16.0) return 1;
  if (tps >= 12.0) return 2;
  return 3;
}

function hitungItem(dim) {
  const daftar = aman(() => dim.getEntities({ type: "minecraft:item" }));
  return daftar ? daftar.length : 0;
}

function sample() {
  const pemain = aman(() => world.getPlayers()) || [];
  if (!aktif || pemain.length === 0) { terakhir = Date.now(); return; }

  const sekarang = Date.now();
  const delta = Math.max(1, sekarang - terakhir);
  terakhir = sekarang;
  const tps = Math.min(20, INTERVAL / (delta / 1000));
  riwayat.push(tps);
  while (riwayat.length > WINDOW) riwayat.shift();

  const dim = aman(() => pemain[0].dimension);
  const namaDim = dim ? String(dim.id) : "";
  if (!profilSiap || namaDim !== dimensiAktif) {
    profilSiap = true;
    dimensiAktif = namaDim;
    if (dim) {
      terapkanProfil(dim, basis);
      if (namaDim.indexOf("nether") >= 0) perintah(dim, "gamerule dofiretick false");
    }
  }

  itemTerakhir = dim ? hitungItem(dim) : 0;
  if (dim && itemTerakhir > BATAS_ITEM && level < 1) {
    perintah(dim, "kill @e[type=item]");
    perintah(dim, "kill @e[type=xp_orb]");
  }

  const rata = riwayat.reduce((a, b) => a + b, 0) / riwayat.length;
  const target = tingkatKe(rata);

  if (target > level) {
    tenang = 0;
    terapkan(target);
    aman(() => world.sendMessage(TAG + "beban naik (TPS " + rata.toFixed(1) +
      ", item " + itemTerakhir + ") -> " + LABEL[target] + " diterapkan otomatis"));
  } else if (target < level) {
    tenang++;
    if (tenang >= TENANG) {
      tenang = 0;
      terapkan(level - 1);
      aman(() => world.sendMessage(TAG + "stabil (TPS " + rata.toFixed(1) +
        ") -> turun ke " + LABEL[level]));
    }
  } else {
    tenang = 0;
  }

  if (hud) {
    const ms = (delta / INTERVAL).toFixed(1);
    const teks = "\u00a7eTPS " + rata.toFixed(1) + "\u00a7r | \u00a7btick " + ms +
      " ms\u00a7r | \u00a77item " + itemTerakhir + "\u00a7r | \u00a7a" +
      LABEL[level] + "\u00a7r | \u00a7d" + basis.toUpperCase() + "\u00a7r";
    for (const p of pemain) aman(() => p.onScreenDisplay.setActionBar(teks));
  }
}

system.runInterval(sample, INTERVAL);

// ---- kendali chat, tanpa Cheats: !crvx <perintah> ----
aman(() => world.beforeEvents.chatSend.subscribe((ev) => {
  const pesan = (ev.message || "").trim().toLowerCase();
  if (pesan.indexOf("!crvx") !== 0) return;
  const arg = pesan.split(/\s+/)[1] || "status";
  ev.cancel = true;
  system.run(() => {
    if (arg === "mati") {
      aktif = false; world.setDynamicProperty("crvx:aktif", 0);
      world.sendMessage(TAG + "governor DIMATIKAN. Reset gamerule: /function crvx/pulihkan");
    } else if (arg === "nyala") {
      aktif = true; tenang = 0; world.setDynamicProperty("crvx:aktif", 1);
      world.sendMessage(TAG + "governor NYALA, sampel tiap " +
        (INTERVAL * 50 / 1000).toFixed(0) + " detik.");
    } else if (arg === "hud") {
      hud = !hud; world.setDynamicProperty("crvx:hud", hud ? 1 : 0);
      world.sendMessage(TAG + "HUD action bar " + (hud ? "NYALA" : "MATI"));
    } else if (arg === "turbo" || arg === "hemat" || arg === "ganas") {
      basis = arg; world.setDynamicProperty("crvx:basis", arg);
      profilSiap = false; tenang = 0;
      world.sendMessage(TAG + "profil dasar -> " + arg.toUpperCase() +
        " (diterapkan ulang otomatis)");
    } else if (arg === "reset") {
      terapkan(0); riwayat.length = 0; tenang = 0;
      world.sendMessage(TAG + "level dipaksa kembali ke SEHAT.");
    } else if (arg === "pulihkan") {
      const dim = aman(() => world.getDimension("overworld"));
      if (dim) {
        perintah(dim, "gamerule randomtickspeed 1");
        perintah(dim, "gamerule doweathercycle true");
        perintah(dim, "gamerule doinsomnia true");
        perintah(dim, "gamerule mobgriefing true");
        perintah(dim, "gamerule dofiretick true");
        perintah(dim, "gamerule domobspawning true");
      }
      world.sendMessage(TAG + "semua gamerule dikembalikan ke default vanilla.");
    } else {
      const rata = riwayat.length
        ? (riwayat.reduce((a, b) => a + b, 0) / riwayat.length).toFixed(1) : "-";
      world.sendMessage(TAG + "AutoGovernor v2 " + (aktif ? "AKTIF" : "MATI") +
        " | level " + level + " (" + LABEL[level] + ") | TPS " + rata +
        " | item " + itemTerakhir + " | profil " + basis.toUpperCase() +
        " | HUD " + (hud ? "nyala" : "mati"));
      world.sendMessage(TAG + "perintah: !crvx nyala|mati|hud|reset|turbo|hemat|ganas|pulihkan");
    }
  });
}));

world.afterEvents.worldLoad.subscribe(() => {
  system.runTimeout(() => {
    if (!aktif) return;
    world.sendMessage(TAG + "AutoGovernor v2 siaga (profil " + basis.toUpperCase() +
      "). Ketik \u00a7e!crvx status\u00a7r untuk cek, \u00a7e!crvx hud\u00a7r untuk HUD.");
  }, 40);
});
""" % (SERVER_API, interval, window, interval, window, kinds)


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
    write_png(os.path.join(rp, "pack_icon.png"), 128, 128, make_icon(accent=(56, 189, 248)))
    _tulis(rp, "manifest.json", json.dumps(
        manifest(RP_NAME,
                 f"Tekstur {texture_res}x{texture_res} buatan sendiri untuk permukaan "
                 "transparan terberat (kaca, es, daun) + awan transparan + cuaca "
                 "nyaris tak terlihat + 16 definisi fog dipangkas. Mengurangi "
                 "overdraw & bandwidth tekstur. Bukan aset Mojang.",
                 version, "resources", MIN_ENGINE_RP), indent=2, ensure_ascii=False))
    _tulis(rp, "fogs/crvx_fog_cut.json",
           json.dumps(fog_file(fog_strength), indent=2, ensure_ascii=False))
    for rel, (w, h, rows) in texture_entries(texture_res).items():
        target = os.path.join(rp, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_png(target, w, h, rows)
    _tulis(rp, "texts/en_US.lang",
           "pack.name=%s\npack.description=CRVX fast textures + fog cut\n" % RP_NAME)
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
                                    "version": SERVER_API}]),
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
                    for f in fog:
                        try:
                            doc = json.loads(zf.read(f).decode("utf-8"))
                        except json.JSONDecodeError as exc:
                            problems.append(f"{f}: JSON rusak ({exc})")
                            continue
                        defs = doc.get("fog_definitions", [])
                        if not defs:
                            problems.append(f"{f}: fog_definitions kosong")
                        for d in defs:
                            if not d.get("identifier") or "minecraft:fog_settings" not in d:
                                problems.append(f"{f}: definisi fog tidak lengkap")
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
