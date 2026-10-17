// CRVX FPS Booster - AutoGovernor v3.3 (Script API @@SERVER_API@@ + server-ui @@SERVER_UI_API@@)
//
// PERBAIKAN v3.3 setelah laporan lapangan (panas + patah-patah + FORCE CLOSE):
//  1. KONTROL BENAR-BENAR HIDUP. Versi lama berlangganan
//     `world.beforeEvents.chatSend`, yang TIDAK ADA di API stabil 2.x.
//     Diperiksa langsung dari deklarasi tipe @minecraft/server 2.0.0:
//     WorldBeforeEvents = effectAdd, entityRemove, explosion, itemUse,
//     playerBreakBlock, playerGameModeChange, playerInteractWithBlock,
//     playerInteractWithEntity, playerLeave, weatherChange. Tidak ada chatSend.
//     TypeError-nya ditelan try/catch, jadi perintah "!crvx" TIDAK PERNAH
//     terdaftar dan governor tidak bisa dikendalikan dari dalam game.
//     Kontrol sekarang: JONGKOK + PAKAI ITEM apa pun -> menu (tanpa Cheats);
//     /scriptevent crvx:<arg> bila dunia mengizinkan perintah; dan !crvx tetap
//     dipasang otomatis hanya bila klien benar-benar menyediakannya.
//  2. ANGGARAN PERINTAH: maks 2 perintah per sampel. Versi lama bisa mengirim
//     43 perintah dalam satu tick (gov/l3 = 31x `kill @e[...]`); tiap `kill`
//     menyapu seluruh daftar entity + memicu simpan-chunk serentak. Di HP RAM
//     4 GB saat chunk masih streaming, lonjakan itu = stutter berat sampai
//     force close. Kini tiap level hanya mengubah gamerule (murah).
//  3. SAPUAN BERTAHAP: pembersihan entity SATU jenis per sampel, jeda min 8 dtk.
//  4. MASA TENANG: 3 sampel pertama setelah dunia dimuat tidak mengirim
//     perintah apa pun - hanya mengukur.
//  5. PEMUTUS SIRKUIT: bila API terus menolak, governor berhenti mengirim
//     perintah dan melambat sendiri, bukan mengulang error tiap tick.
//  6. Tanpa mass-kill mob: level MAX mematikan spawning (sumber beban CPU),
//     tidak memusnahkan mob dunia kamu.
//  7. Anti-osilasi v3.2 dipertahankan: cooldown, konfirmasi 2 sampel, derivatif
//     dihaluskan, chat maks 1/60 detik, menu tidak membuka ulang dirinya.
import { world, system } from "@minecraft/server";
import { ActionFormData } from "@minecraft/server-ui";

const TAG = "\u00a7d\u00a7l[CRVX]\u00a7r ";
const INTERVAL = @@INTERVAL@@;
const CEPAT = 40;                  // saat tidak stabil (2 dtk)
const SANTAI = 200;                // saat AFK (10 dtk) - hemat baterai
const WINDOW = @@WINDOW@@;
const TENANG = 4;                  // sampel sehat beruntun sebelum turun level
const KOOLDAUN = 4;                // sampel terkunci setelah perubahan level
const ANGGARAN = 2;                // v3.3: maks perintah per sampel
const JEDA_SAPU = 8000;            // v3.3: ms minimum antar sapuan entity
const TENANG_MUAT = 3;             // v3.3: sampel tanpa perintah setelah load
const BATAS_GAGAL = 6;             // v3.3: pemutus sirkuit
const JEDA_GESTUR = 1200;          // v3.3: ms antar gestur buka-menu
const BATAS_ITEM = 80;
const SAPU = @@KINDS@@;            // antrean sapuan bertahap (1 jenis per sampel)
const LABEL = ["SEHAT", "HEMAT", "DINGIN", "MAX"];
const KP = 0.80, KI = 0.08, KD = 0.35, I_MAX = 4.0;
const PANAS_NAIK = 5.0, PANAS_TURUN = 2.6;

const riwayat = [];
const errRiwayat = [];
let level = 0, tenang = 0, naikBeruntun = 0, kunci = 0, terakhir = Date.now();
let profilSiap = false, dimensiAktif = "", itemTerakhir = 0, tpsTerakhir = 20;
let panas = 0, integral = 0;
let intervalId = null, intervalCur = INTERVAL, sampelKe = 0;
let posSebelum = null, diamTick = 0, afk = false;
let pesanTerakhir = 0, anggaran = ANGGARAN, sapuIdx = 0, sapuTerakhir = 0;
let gagal = 0, sekeringPutus = false;
let menuTerbuka = false, gesturTerakhir = 0, sudahDihint = false;
let learned = 0;
let aktif = true, hud = true, basis = "turbo", stateTermuat = false;

function aman(fn) {
  try { const h = fn(); gagal = Math.max(0, gagal - 1); return h; }
  catch (e) { gagal++; return null; }
}

// v3.3: setiap perintah lewat sini, dan DITOLAK bila anggaran sampel habis
function perintah(dim, cmd) {
  if (!dim || anggaran <= 0 || sekeringPutus) return false;
  anggaran--;
  return aman(() => dim.runCommand(cmd)) !== null;
}

function muatState() {
  aman(() => {
    const l = world.getDynamicProperty("crvx:learn");
    if (typeof l === "number") learned = l;
    const a = world.getDynamicProperty("crvx:aktif");
    if (a !== undefined) aktif = a !== 0;
    const h = world.getDynamicProperty("crvx:hud");
    if (h !== undefined) hud = h !== 0;
    const b = world.getDynamicProperty("crvx:basis");
    if (typeof b === "string" && b) basis = b;
    stateTermuat = true;
  });
}

// chat maks 1 pesan / 60 detik - tidak ada lagi spam
function kabari(teks) {
  const n = Date.now();
  if (n - pesanTerakhir < 60000) return;
  pesanTerakhir = n;
  aman(() => world.sendMessage(TAG + teks));
}

function terapkan(target) {
  const dim = aman(() => world.getDimension("overworld"));
  // SATU perintah per level; isinya hanya gamerule (murah, tanpa sapuan entity)
  perintah(dim, "function gov/l" + target);
  level = target;
  kunci = KOOLDAUN;
  naikBeruntun = 0;
  tenang = 0;
}

function setSampel(tick) {
  if (tick === intervalCur && intervalId !== null) return;
  if (intervalId !== null) aman(() => system.clearRun(intervalId));
  intervalCur = tick;
  intervalId = system.runInterval(sample, tick);
}

// v3.3: satu jenis entity per sampel, dengan jeda minimum
function sapuBertahap(dim) {
  const n = Date.now();
  if (n - sapuTerakhir < JEDA_SAPU || !SAPU.length) return;
  if (itemTerakhir < BATAS_ITEM && level < 2) return;
  sapuTerakhir = n;
  const jenis = SAPU[sapuIdx % SAPU.length];
  sapuIdx++;
  perintah(dim, "kill @e[type=" + jenis + "]");
}

function contoh() {
  if (!stateTermuat) muatState();
  const pemain = aman(() => world.getPlayers()) || [];
  if (!aktif || pemain.length === 0) { terakhir = Date.now(); return; }

  const sekarang = Date.now();
  const delta = Math.max(1, sekarang - terakhir);
  terakhir = sekarang;
  const tps = Math.min(20, intervalCur / (delta / 1000));
  tpsTerakhir = tps;
  riwayat.push(tps);
  while (riwayat.length > WINDOW) riwayat.shift();
  const rata = riwayat.reduce((a, b) => a + b, 0) / riwayat.length;
  sampelKe++;

  const dim = aman(() => pemain[0].dimension);

  // v3.3: MASA TENANG - chunk masih streaming, jangan kirim perintah apa pun
  if (sampelKe <= TENANG_MUAT) {
    if (hud) {
      const teks = "\u00a77mengukur... \u00a7eTPS " + rata.toFixed(1) +
        "\u00a7r \u00a78(" + (TENANG_MUAT - sampelKe + 1) + " sampel lagi)\u00a7r";
      for (const p of pemain) aman(() => p.onScreenDisplay.setActionBar(teks));
    }
    return;
  }

  const namaDim = dim ? String(dim.id) : "";
  if (!profilSiap || namaDim !== dimensiAktif) {
    profilSiap = true; dimensiAktif = namaDim;
    perintah(dim, "function gov/profil_" + basis);
    if (namaDim.indexOf("nether") >= 0) perintah(dim, "gamerule dofiretick false");
    kabari("profil " + basis.toUpperCase() + " diterapkan di " + namaDim + ".");
  }

  // AFK -> perlambat sampling (hemat baterai), bukan spam perintah
  const pos = pemain[0].location;
  if (posSebelum && Math.abs(pos.x - posSebelum.x) < 0.05 &&
      Math.abs(pos.y - posSebelum.y) < 0.05 && Math.abs(pos.z - posSebelum.z) < 0.05) {
    diamTick += intervalCur;
  } else { diamTick = 0; }
  posSebelum = pos;
  const afkBaru = diamTick > 1200;
  if (afkBaru !== afk) {
    afk = afkBaru;
    perintah(dim, "function gov/" + (afk ? "afk" : "profil_" + basis));
  }

  // ukur entity hanya sesekali - query getEntities tidak gratis di HP lemah
  if (sampelKe % 4 === 0 || level >= 1) {
    itemTerakhir = dim
      ? (aman(() => dim.getEntities({ type: "minecraft:item" })) || []).length : 0;
  }
  sapuBertahap(dim);

  // --- PID dengan derivatif DIHALUSKAN (rata-rata 3 sampel) ---
  const err = 20 - rata;
  integral = Math.max(-I_MAX, Math.min(I_MAX, integral + err));
  errRiwayat.push(err);
  while (errRiwayat.length > 4) errRiwayat.shift();
  const jatuh = errRiwayat.length >= 4 ? (err - errRiwayat[0]) / 3 : 0;
  const tekanan = KP * err + KI * integral + KD * Math.max(0, jatuh);

  const beban = Math.max(0, err / 6) + level * 0.22 + (afk ? -0.6 : 0);
  panas = Math.max(0, Math.min(100,
    panas + (beban > 0.45 ? PANAS_NAIK * beban : -PANAS_TURUN)));
  const lantai = panas > 75 ? 2 : panas > 50 ? 1 : 0;

  const targetPid = tekanan < 1.0 ? 0 : tekanan < 2.6 ? 1 : tekanan < 4.4 ? 2 : 3;
  const target = Math.max(targetPid, lantai);

  if (kunci > 0) {
    kunci--;
  } else if (target > level) {
    naikBeruntun++;
    if (naikBeruntun >= 2) {                 // butuh 2 sampel yakin sebelum naik
      terapkan(target);
      kabari("naik ke " + LABEL[target] + " (tekanan " + tekanan.toFixed(1) +
        ", panas " + panas.toFixed(0) + "%)");
    }
  } else if (target < level) {
    naikBeruntun = 0;
    tenang++;
    if (tenang >= TENANG) {
      const baru = Math.max(target, level - 1);
      terapkan(baru);
      learned = baru;
      aman(() => world.setDynamicProperty("crvx:learn", baru));
      kabari("stabil -> turun ke " + LABEL[baru]);
    }
  } else {
    naikBeruntun = 0;
    tenang = 0;
  }

  setSampel(afk ? SANTAI : (Math.abs(err) > 2.0 ? CEPAT : INTERVAL));

  if (hud) {
    const teks = "\u00a7eTPS " + rata.toFixed(1) + "\u00a7r | \u00a7btick " +
      (delta / intervalCur).toFixed(1) + "ms\u00a7r | \u00a7c\u00b0" + panas.toFixed(0) +
      "%\u00a7r | \u00a77item " + itemTerakhir + "\u00a7r | \u00a7a" + LABEL[level] +
      "\u00a7r" + (afk ? " \u00a78zzz\u00a7r" : "") +
      (sekeringPutus ? " \u00a74AMAN\u00a7r" : "");
    for (const p of pemain) aman(() => p.onScreenDisplay.setActionBar(teks));
  }
}

function sample() {
  anggaran = ANGGARAN;                       // isi ulang tiap sampel
  try { contoh(); } catch (e) { gagal += 2; }
  // v3.3: PEMUTUS SIRKUIT - berhenti mengirim perintah bila API terus menolak
  if (!sekeringPutus && gagal >= BATAS_GAGAL) {
    sekeringPutus = true;
    kabari("pemutus sirkuit AKTIF: governor berhenti mengirim perintah " +
      "(API menolak " + gagal + "x). Buka menu (jongkok + pakai item) -> DIAMKAN.");
    setSampel(SANTAI);
  } else if (sekeringPutus && gagal === 0) {
    sekeringPutus = false;
  }
}

function bukaMenu(pemain) {
  if (menuTerbuka || !pemain) return;
  menuTerbuka = true;
  const form = new ActionFormData()
    .title("\u00a7l\u00a7dCRVX FPS BOOSTER\u00a7r")
    .body("Governor v3.3 - anggaran " + ANGGARAN + " perintah/sampel, tanpa badai kill\n" +
      "TPS " + tpsTerakhir.toFixed(1) + " | level " + level + " (" + LABEL[level] +
      ") | panas " + panas.toFixed(0) + "%\nprofil: " + basis.toUpperCase() +
      " | HUD " + (hud ? "nyala" : "mati") + " | aktif " + (aktif ? "ya" : "tidak") +
      (sekeringPutus ? "\n\u00a74pemutus sirkuit aktif\u00a7r" : ""))
    .button("TURBO 60 - seimbang", "textures/ui/crvx_turbo")
    .button("HEMAT - baterai & suhu", "textures/ui/crvx_hemat")
    .button("GANAS - FPS maksimum", "textures/ui/crvx_ganas")
    .button("HUD " + (hud ? "MATIKAN" : "NYALAKAN"), "textures/ui/crvx_hud")
    .button("STATUS sistem", "textures/ui/crvx_status")
    .button("DIAMKAN governor", "textures/ui/crvx_restore");
  const janji = aman(() => form.show(pemain));
  if (!janji || typeof janji.then !== "function") { menuTerbuka = false; return; }
  janji.then((hasil) => {
    menuTerbuka = false;
    if (!hasil || hasil.canceled || hasil.selection === undefined) return;
    terapkanTombol(pemain, hasil.selection);
  }, () => { menuTerbuka = false; });
}

function terapkanTombol(pemain, idx) {
  const dim = aman(() => world.getDimension("overworld"));
  if (idx === 0) { basis = "turbo"; aman(() => world.setDynamicProperty("crvx:basis", "turbo")); }
  else if (idx === 1) { basis = "hemat"; aman(() => world.setDynamicProperty("crvx:basis", "hemat")); }
  else if (idx === 2) { basis = "ganas"; aman(() => world.setDynamicProperty("crvx:basis", "ganas")); }
  else if (idx === 3) { hud = !hud; aman(() => world.setDynamicProperty("crvx:hud", hud ? 1 : 0)); }
  else if (idx === 4) {
    aman(() => world.sendMessage(TAG + "TPS " + tpsTerakhir.toFixed(1) + " | level " +
      level + " (" + LABEL[level] + ") | panas " + panas.toFixed(0) + "% | item " +
      itemTerakhir + " | integral " + integral.toFixed(2) + " | kunci " + kunci +
      " | cmd/sampel " + ANGGARAN + " | profil " + basis.toUpperCase()));
    return;
  } else if (idx === 5) {
    aktif = false;
    aman(() => world.setDynamicProperty("crvx:aktif", 0));
    perintah(dim, "function gov/l0");
    aman(() => world.sendMessage(TAG +
      "governor DIAMKAN. Nyalakan lagi dari menu (jongkok + pakai item)."));
    return;
  }
  if (idx <= 2 && dim) { perintah(dim, "function gov/profil_" + basis); profilSiap = true; }
  // v3.2+: menu TIDAK membuka ulang dirinya - tidak ada lagi popup berulang
}

// satu jalur untuk semua masukan: gestur, /scriptevent, dan chat (bila ada)
function tanganiArg(arg, pemain) {
  const p = pemain || (aman(() => world.getPlayers()) || [])[0] || null;
  const dim = aman(() => world.getDimension("overworld"));
  if (!arg || arg === "menu") { bukaMenu(p); return; }
  if (arg === "mati") { aktif = false; aman(() => world.setDynamicProperty("crvx:aktif", 0)); }
  else if (arg === "nyala") {
    aktif = true; gagal = 0; sekeringPutus = false; kunci = 0;
    aman(() => world.setDynamicProperty("crvx:aktif", 1));
  } else if (arg === "hud") { hud = !hud; aman(() => world.setDynamicProperty("crvx:hud", hud ? 1 : 0)); }
  else if (arg === "turbo" || arg === "hemat" || arg === "ganas") {
    basis = arg; aman(() => world.setDynamicProperty("crvx:basis", arg));
    perintah(dim, "function gov/profil_" + basis);
    profilSiap = true;
  } else if (arg === "reset") {
    perintah(dim, "function gov/l0");
    riwayat.length = 0; panas = 0; integral = 0; kunci = 0; level = 0;
    gagal = 0; sekeringPutus = false; sampelKe = 0;
  } else if (arg === "status") { terapkanTombol(p, 4); return; }
  else if (arg === "bantuan") {
    aman(() => world.sendMessage(TAG + "JONGKOK + PAKAI ITEM = menu | /scriptevent " +
      "crvx:mati|nyala|hud|turbo|hemat|ganas|reset|status"));
    return;
  } else {
    aman(() => world.sendMessage(TAG + "argumen tidak dikenal: " + arg +
      " (mati|nyala|hud|turbo|hemat|ganas|reset|status|bantuan)"));
    return;
  }
  aman(() => world.sendMessage(TAG + "ok: " + arg + " (basis " + basis.toUpperCase() +
    ", aktif=" + aktif + ", hud=" + hud + ")"));
}

muatState();
intervalId = system.runInterval(sample, INTERVAL);

// --- KONTROL UTAMA: jongkok + pakai item apa pun (tanpa Cheats, tanpa chat) ---
aman(() => world.beforeEvents.itemUse.subscribe((ev) => {
  const p = ev.source;
  if (!p || menuTerbuka) return;
  if (!aman(() => p.isSneaking)) return;         // hanya saat jongkok
  const n = Date.now();
  if (n - gesturTerakhir < JEDA_GESTUR) return;
  gesturTerakhir = n;
  system.run(() => { pesanTerakhir = 0; bukaMenu(p); });
}));

// --- kontrol lewat perintah (hanya bila dunia mengizinkan /scriptevent) ---
aman(() => system.afterEvents.scriptEventReceive.subscribe((ev) => {
  if (!ev || String(ev.id || "").indexOf("crvx:") !== 0) return;
  const dariId = String(ev.id).slice(5).trim().toLowerCase();
  const arg = dariId || String(ev.message || "").split(/\s+/)[0].toLowerCase();
  const sumber = aman(() => ev.sourceEntity) || aman(() => ev.initiator);
  // Entity.isPlayer() tidak ada di API stabil 2.0.0 -> pakai typeId (terverifikasi)
  const pemain = sumber && aman(() => sumber.typeId) === "minecraft:player" ? sumber : null;
  system.run(() => { pesanTerakhir = 0; tanganiArg(arg, pemain); });
}));

// --- chat "!crvx" HANYA bila klien ini benar-benar punya chatSend (1.x) ---
const sinyalChat = aman(() => world.beforeEvents.chatSend);
if (sinyalChat && typeof sinyalChat.subscribe === "function") {
  aman(() => sinyalChat.subscribe((ev) => {
    const pesan = (ev.message || "").trim().toLowerCase();
    if (pesan.indexOf("!crvx") !== 0) return;
    const arg = pesan.split(/\s+/)[1] || "";
    ev.cancel = true;
    const pemain = ev.sender;
    system.run(() => { pesanTerakhir = 0; tanganiArg(arg, pemain); });
  }));
}

// --- petunjuk sekali per dunia, supaya gesturnya ketemu ---
aman(() => world.afterEvents.playerSpawn.subscribe((ev) => {
  if (!ev || !ev.initialSpawn || sudahDihint) return;
  sudahDihint = true;
  system.runTimeout(() => {
    aman(() => world.sendMessage(TAG + "\u00a7lv3.3\u00a7r aktif. Menu: " +
      "\u00a7dJONGKOK + PAKAI ITEM\u00a7r apa pun. Perintah (bila diizinkan): " +
      "\u00a7d/scriptevent crvx:status\u00a7r"));
  }, 60);
}));

aman(() => world.afterEvents.worldLoad.subscribe(() => {
  system.runTimeout(() => {
    muatState();
    aman(() => world.sendMessage(TAG + "\u00a7lv3.3\u00a7r termuat" +
      (aktif ? " & AKTIF" : " (nonaktif - /scriptevent crvx:nyala)") +
      ". Maks " + ANGGARAN + " perintah/sampel; " + TENANG_MUAT +
      " sampel pertama hanya mengukur. Menu: \u00a7dJONGKOK + PAKAI ITEM\u00a7r."));
  }, 40);
}));
