// CRVX FPS Booster - AutoGovernor v3.2 (Script API @@SERVER_API@@ + server-ui @@SERVER_UI_API@@)
// PERBAIKAN v3.2 setelah laporan lapangan (spam + panas + stutter):
//  1. ANTI-OSILASI: cooldown 4 sampel setelah tiap perubahan level, kenaikan
//     butuh 2 sampel beruntun, suku derivatif dihaluskan (rata-rata 3 sampel).
//     Sebelumnya level naik-turun terus dan tiap naik mengirim ~10 perintah ->
//     storm perintah = stutter, dan pesan chat = spam.
//  2. SATU perintah per perubahan level: eskalasi kini memanggil
//     `function gov/l<N>` (mcfunction di pack ini), bukan 10 runCommand.
//  3. Pesan chat dibatasi maks 1 per 60 detik; info rutin hanya lewat action bar.
//  4. Menu TIDAK membuka ulang dirinya setelah tombol ditekan.
//  5. Sampling lebih murah: jumlah entity hanya diukur tiap 4 sampel (atau saat
//     level >= 1), dan interval melambat saat pemain AFK.
import { world, system } from "@minecraft/server";
import { ActionFormData } from "@minecraft/server-ui";

const TAG = "\u00a7d\u00a7l[CRVX]\u00a7r ";
const INTERVAL = @@INTERVAL@@;
const CEPAT = 40;                  // saat tidak stabil (2 dtk, dulu 1 dtk - terlalu agresif)
const SANTAI = 200;                // saat AFK (10 dtk) - hemat baterai
const WINDOW = @@WINDOW@@;
const TENANG = 4;                  // sampel sehat beruntun sebelum turun level
const KOOLDAUN = 4;                // sampel terkunci setelah perubahan level
const BATAS_ITEM = 80;
const SAMPAH = @@KINDS@@;
const LABEL = ["SEHAT", "HEMAT", "DINGIN", "MAX"];
const KP = 0.80, KI = 0.08, KD = 0.35, I_MAX = 4.0;   // KD kecil: derivatif = penguat noise
const PANAS_NAIK = 5.0, PANAS_TURUN = 2.6;            // konstanta termal lebih lambat
const AMAN_CULL = ["player", "armor_stand", "item_frame", "glow_item_frame", "villager",
  "wandering_trader", "wolf", "cat", "ocelot", "parrot", "horse", "mule", "donkey", "llama",
  "camel", "sniffer", "allay", "bee", "iron_golem", "snow_golem", "tadpole", "axolotl",
  "fox", "turtle", "dolphin", "squid", "glow_squid", "frog", "happy_ghast", "npc"];

const riwayat = [];
const errRiwayat = [];
let level = 0, tenang = 0, naikBeruntun = 0, kunci = 0, terakhir = Date.now();
let profilSiap = false, dimensiAktif = "", itemTerakhir = 0, tpsTerakhir = 20;
let panas = 0, integral = 0;
let intervalId = null, intervalCur = INTERVAL, sampelKe = 0;
let posSebelum = null, diamTick = 0, afk = false;
let pesanTerakhir = 0;
let learned = 0;
let aktif = true, hud = true, basis = "turbo", stateTermuat = false;

function aman(fn) { try { return fn(); } catch (e) { return null; } }
function perintah(dim, cmd) { aman(() => dim.runCommand(cmd)); }

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
  if (!dim) return;
  // SATU perintah: semua aksi level ada di mcfunction pack ini
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

function sample() {
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
  const namaDim = dim ? String(dim.id) : "";
  if (!profilSiap || namaDim !== dimensiAktif) {
    profilSiap = true; dimensiAktif = namaDim;
    if (dim) {
      perintah(dim, "function gov/profil_" + basis);
      if (namaDim.indexOf("nether") >= 0) perintah(dim, "gamerule dofiretick false");
      kabari("profil " + basis.toUpperCase() + " diterapkan di " + namaDim + ".");
    }
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
    if (dim) perintah(dim, "function gov/" + (afk ? "afk" : "profil_" + basis));
  }

  // ukur entity hanya sesekali - query getEntities tidak gratis di HP lemah
  if (sampelKe % 4 === 0 || level >= 1) {
    itemTerakhir = dim
      ? (aman(() => dim.getEntities({ type: "minecraft:item" })) || []).length : 0;
    if (dim && itemTerakhir > BATAS_ITEM && level < 1) {
      perintah(dim, "kill @e[type=item]");
      perintah(dim, "kill @e[type=xp_orb]");
    }
  }

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
      "\u00a7r" + (afk ? " \u00a78zzz\u00a7r" : "");
    for (const p of pemain) aman(() => p.onScreenDisplay.setActionBar(teks));
  }
}

function bukaMenu(pemain) {
  const form = new ActionFormData()
    .title("\u00a7l\u00a7dCRVX FPS BOOSTER\u00a7r")
    .body("Governor v3.2 - anti-osilasi, 1 perintah per level\n" +
      "TPS " + tpsTerakhir.toFixed(1) + " | level " + level + " (" + LABEL[level] +
      ") | panas " + panas.toFixed(0) + "%\nprofil: " + basis.toUpperCase() +
      " | HUD " + (hud ? "nyala" : "mati") + " | aktif " + (aktif ? "ya" : "tidak") +
      "\n\nMenu ini tidak membuka ulang dirinya lagi.")
    .button("TURBO 60 - seimbang", "textures/ui/crvx_turbo")
    .button("HEMAT - baterai & suhu", "textures/ui/crvx_hemat")
    .button("GANAS - FPS maksimum", "textures/ui/crvx_ganas")
    .button("HUD " + (hud ? "MATIKAN" : "NYALAKAN"), "textures/ui/crvx_hud")
    .button("STATUS sistem", "textures/ui/crvx_status")
    .button("DIAMKAN governor", "textures/ui/crvx_restore");
  aman(() => form.show(pemain).then((hasil) => {
    if (!hasil || hasil.canceled || hasil.selection === undefined) return;
    jalankan(pemain, hasil.selection);
  }));
}

function jalankan(pemain, idx) {
  const dim = aman(() => world.getDimension("overworld"));
  if (idx === 0) { basis = "turbo"; aman(() => world.setDynamicProperty("crvx:basis", "turbo")); }
  else if (idx === 1) { basis = "hemat"; aman(() => world.setDynamicProperty("crvx:basis", "hemat")); }
  else if (idx === 2) { basis = "ganas"; aman(() => world.setDynamicProperty("crvx:basis", "ganas")); }
  else if (idx === 3) { hud = !hud; aman(() => world.setDynamicProperty("crvx:hud", hud ? 1 : 0)); }
  else if (idx === 4) {
    world.sendMessage(TAG + "TPS " + tpsTerakhir.toFixed(1) + " | level " + level +
      " (" + LABEL[level] + ") | panas " + panas.toFixed(0) + "% | item " + itemTerakhir +
      " | integral " + integral.toFixed(2) + " | kunci " + kunci + " | profil " +
      basis.toUpperCase());
    return;
  } else if (idx === 5) {
    aktif = false;
    aman(() => world.setDynamicProperty("crvx:aktif", 0));
    if (dim) perintah(dim, "function gov/l0");
    world.sendMessage(TAG + "governor DIAMKAN. Ketik !crvx nyala untuk menjalankan lagi.");
    return;
  }
  if (idx <= 2 && dim) { perintah(dim, "function gov/profil_" + basis); profilSiap = true; }
  // v3.2: menu TIDAK membuka ulang dirinya - tidak ada lagi popup berulang
}

muatState();
intervalId = system.runInterval(sample, INTERVAL);

aman(() => world.beforeEvents.chatSend.subscribe((ev) => {
  const pesan = (ev.message || "").trim().toLowerCase();
  if (pesan.indexOf("!crvx") !== 0) return;
  const arg = pesan.split(/\s+/)[1] || "";
  ev.cancel = true;
  const pemain = ev.sender;
  system.run(() => {
    pesanTerakhir = 0;                     // perintah manual selalu dijawab
    if (!arg) { aman(() => bukaMenu(pemain)); return; }
    if (arg === "mati") { aktif = false; aman(() => world.setDynamicProperty("crvx:aktif", 0)); }
    else if (arg === "nyala") { aktif = true; aman(() => world.setDynamicProperty("crvx:aktif", 1)); }
    else if (arg === "hud") { hud = !hud; aman(() => world.setDynamicProperty("crvx:hud", hud ? 1 : 0)); }
    else if (arg === "turbo" || arg === "hemat" || arg === "ganas") {
      basis = arg; aman(() => world.setDynamicProperty("crvx:basis", arg));
      const dim = aman(() => world.getDimension("overworld"));
      if (dim) perintah(dim, "function gov/profil_" + basis);
    } else if (arg === "reset") {
      const dim = aman(() => world.getDimension("overworld"));
      if (dim) perintah(dim, "function gov/l0");
      riwayat.length = 0; panas = 0; integral = 0; kunci = 0;
    } else if (arg === "status") { jalankan(pemain, 4); return; }
    else {
      aman(() => world.sendMessage(TAG +
        "perintah: !crvx (menu) | nyala | mati | hud | turbo | hemat | ganas | reset | status"));
      return;
    }
    aman(() => world.sendMessage(TAG + "ok: " + arg + " (basis " + basis.toUpperCase() +
      ", aktif=" + aktif + ", hud=" + hud + ")"));
  });
}));

aman(() => world.afterEvents.worldLoad.subscribe(() => {
  system.runTimeout(() => {
    muatState();
    world.sendMessage(TAG + "\u00a7lv3.2\u00a7r termuat" +
      (aktif ? " & AKTIF" : " (nonaktif - !crvx nyala)") +
      ". Ketik \u00a7d!crvx\u00a7r untuk menu. Pesan chat kini maks 1/menit.");
  }, 40);
}));
