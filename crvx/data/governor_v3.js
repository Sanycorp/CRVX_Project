// CRVX FPS Booster - AutoGovernor v3 (Script API @@SERVER_API@@ + server-ui @@SERVER_UI_API@@)
// PID (P+I+D, anti-windup) + model termal akumulatif + pembelajaran antar-sesi
// + sampling adaptif + deteksi AFK + culling berjenjang berdaftar-aman
// + menu ActionForm bertema lubang hitam. Semua panggilan API dibungkus try/catch.
import { world, system } from "@minecraft/server";
import { ActionFormData } from "@minecraft/server-ui";

const TAG = "\u00a7d\u00a7l[CRVX]\u00a7r ";
const INTERVAL = @@INTERVAL@@;
const CEPAT = 20;                  // interval saat tidak stabil (1 detik)
const WINDOW = @@WINDOW@@;
const TENANG = 3;
const BATAS_ITEM = 60;
const SAMPAH = @@KINDS@@;
const LABEL = ["SEHAT", "HEMAT", "DINGIN", "MAX"];
// koefisien PID terhadap error = 20 - TPS
const KP = 0.85, KI = 0.10, KD = 0.60, I_MAX = 4.0;
// model termal (skala 0..100)
const PANAS_NAIK = 7.5, PANAS_TURUN = 3.4;
// entity yang TIDAK boleh pernah di-cull
const AMAN_CULL = ["player", "armor_stand", "item_frame", "glow_item_frame", "villager",
  "wandering_trader", "wolf", "cat", "ocelot", "parrot", "horse", "mule", "donkey", "llama",
  "camel", "sniffer", "allay", "bee", "iron_golem", "snow_golem", "tadpole", "axolotl",
  "fox", "turtle", "dolphin", "squid", "glow_squid", "frog", "happy_ghast", "npc"];

const riwayat = [];
let level = 0, tenang = 0, terakhir = Date.now();
let profilSiap = false, dimensiAktif = "", itemTerakhir = 0, tpsTerakhir = 20;
let panas = 0, integral = 0, errSebelum = 0;
let intervalId = null, intervalCur = INTERVAL;
let posSebelum = null, diamTick = 0, afk = false;
// state dibaca LAZY: getDynamicProperty di top-level bisa melempar sebelum
// dunia siap, dan satu lemparan di top-level mematikan SELURUH modul (inilah
// penyebab klasik "!crvx tidak menanggapi apa-apa").
let learned = 0;
let aktif = true;
let hud = true;
let basis = "turbo";
let stateTermuat = false;

function aman(fn) { try { return fn(); } catch (e) { return null; } }

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
function perintah(dim, cmd) { aman(() => dim.runCommand(cmd)); }

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
  perintah(dim, "kill @e[type=item]");
  perintah(dim, "kill @e[type=xp_orb]");
}

function cullAman(dim, pemain) {
  if (!pemain.length) return 0;
  const jauh = aman(() => dim.getEntities({
    location: pemain[0].location, minDistance: 40,
    excludeTypes: AMAN_CULL, excludeFamilies: ["npc"],
  }));
  if (!jauh) return 0;
  let n = 0;
  for (const e of jauh.slice(0, 40)) { aman(() => e.remove()); n++; }
  return n;
}

function terapkan(target) {
  const dim = aman(() => world.getDimension("overworld"));
  const pemain = aman(() => world.getPlayers()) || [];
  if (!dim) return;
  if (target === 0) {
    perintah(dim, "gamerule randomtickspeed " + (basis === "turbo" ? "1" : "0"));
    perintah(dim, "gamerule domobspawning " + (basis === "ganas" ? "false" : "true"));
    perintah(dim, "gamerule dofiretick " + (dimensiAktif.indexOf("nether") >= 0 ? "false" : "true"));
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
    cullAman(dim, pemain);
  }
  level = target;
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

  const dim = aman(() => pemain[0].dimension);
  const namaDim = dim ? String(dim.id) : "";
  if (!profilSiap || namaDim !== dimensiAktif) {
    profilSiap = true; dimensiAktif = namaDim;
    if (dim) {
      terapkan(Math.max(level, learned));
      terapkanProfil(dim, basis);
      if (namaDim.indexOf("nether") >= 0) perintah(dim, "gamerule dofiretick false");
    }
  }

  // --- deteksi AFK: pemain diam ~45 detik -> penghemat baterai ---
  const pos = pemain[0].location;
  if (posSebelum && Math.abs(pos.x - posSebelum.x) < 0.05 &&
      Math.abs(pos.y - posSebelum.y) < 0.05 && Math.abs(pos.z - posSebelum.z) < 0.05) {
    diamTick += intervalCur;
  } else { diamTick = 0; }
  posSebelum = pos;
  const afkBaru = diamTick > 900;
  if (afkBaru !== afk) {
    afk = afkBaru;
    if (afk && dim) {
      perintah(dim, "gamerule randomtickspeed 0");
      aman(() => world.sendMessage(TAG + "kamu terdiam - mode hemat baterai aktif."));
    } else if (dim) {
      perintah(dim, "gamerule randomtickspeed " + (basis === "turbo" ? "1" : "0"));
    }
  }

  itemTerakhir = dim
    ? (aman(() => dim.getEntities({ type: "minecraft:item" })) || []).length : 0;
  if (dim && itemTerakhir > BATAS_ITEM && level < 1) {
    perintah(dim, "kill @e[type=item]");
    perintah(dim, "kill @e[type=xp_orb]");
  }

  // --- PID: error = kekurangan TPS; derivatif menangkap TPS yang sedang jatuh ---
  const err = 20 - rata;
  integral = Math.max(-I_MAX, Math.min(I_MAX, integral + err));
  const jatuh = err - errSebelum;
  errSebelum = err;
  const tekanan = KP * err + KI * integral + KD * Math.max(0, jatuh);

  // --- model termal akumulatif: beban berkelanjutan menaikkan lantai level ---
  const beban = Math.max(0, err / 6) + level * 0.22 + (afk ? -0.6 : 0);
  panas = Math.max(0, Math.min(100,
    panas + (beban > 0.45 ? PANAS_NAIK * beban : -PANAS_TURUN)));
  const lantai = panas > 72 ? 2 : panas > 46 ? 1 : 0;

  const targetPid = tekanan < 0.9 ? 0 : tekanan < 2.4 ? 1 : tekanan < 4.2 ? 2 : 3;
  const target = Math.max(targetPid, lantai);

  if (target > level) {
    tenang = 0;
    terapkan(target);
    aman(() => world.sendMessage(TAG + "PID naik (tekanan " + tekanan.toFixed(1) +
      ", panas " + panas.toFixed(0) + "%) -> " + LABEL[target]));
  } else if (target < level) {
    tenang++;
    if (tenang >= TENANG) {
      tenang = 0;
      const baru = Math.max(target, level - 1);
      terapkan(baru);
      learned = baru;
      aman(() => world.setDynamicProperty("crvx:learn", baru));
      aman(() => world.sendMessage(TAG + "stabil -> turun ke " + LABEL[baru] +
        " (tersimpan utk sesi berikutnya)"));
    }
  } else { tenang = 0; }

  setSampel(Math.abs(err) > 1.5 ? CEPAT : INTERVAL);

  if (hud) {
    const teks = "\u00a7eTPS " + rata.toFixed(1) + "\u00a7r | \u00a7btick " +
      (delta / intervalCur).toFixed(1) + "ms\u00a7r | \u00a7c\u00b0" + panas.toFixed(0) +
      "%\u00a7r | \u00a77item " + itemTerakhir + "\u00a7r | \u00a7a" + LABEL[level] +
      "\u00a7r" + (afk ? " \u00a78zzz\u00a7r" : "");
    for (const p of pemain) aman(() => p.onScreenDisplay.setActionBar(teks));
  }
}

// ------------------- UI lubang hitam -------------------
function bukaMenu(pemain) {
  const form = new ActionFormData()
    .title("\u00a7l\u00a7dCRVX FPS BOOSTER\u00a7r")
    .body("Governor v3 - PID + model termal + pembelajaran sesi\n" +
      "TPS " + tpsTerakhir.toFixed(1) + " | level " + level + " (" + LABEL[level] +
      ") | panas " + panas.toFixed(0) + "%\nprofil dasar: " + basis.toUpperCase() +
      " | HUD " + (hud ? "nyala" : "mati") + "\n\nPilih aksi:")
    .button("TURBO 60 - seimbang", "textures/ui/crvx_turbo")
    .button("HEMAT - baterai & suhu", "textures/ui/crvx_hemat")
    .button("GANAS - FPS maksimum", "textures/ui/crvx_ganas")
    .button("HUD " + (hud ? "MATIKAN" : "NYALAKAN"), "textures/ui/crvx_hud")
    .button("STATUS sistem", "textures/ui/crvx_status")
    .button("PULIHKAN vanilla", "textures/ui/crvx_restore");
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
      " | integral " + integral.toFixed(2) + " | profil " + basis.toUpperCase());
    return;
  } else if (idx === 5) {
    if (dim) {
      perintah(dim, "gamerule randomtickspeed 1");
      perintah(dim, "gamerule doweathercycle true");
      perintah(dim, "gamerule doinsomnia true");
      perintah(dim, "gamerule mobgriefing true");
      perintah(dim, "gamerule dofiretick true");
      perintah(dim, "gamerule domobspawning true");
    }
    panas = 0; integral = 0; learned = 0;
    aman(() => world.setDynamicProperty("crvx:learn", 0));
  }
  if (idx <= 2 && dim) { profilSiap = false; tenang = 0; }
  aman(() => bukaMenu(pemain));   // menu tetap terbuka setelah aksi
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
    if (!arg) { aman(() => bukaMenu(pemain)); return; }
    if (arg === "mati") { aktif = false; aman(() => world.setDynamicProperty("crvx:aktif", 0)); }
    else if (arg === "nyala") { aktif = true; aman(() => world.setDynamicProperty("crvx:aktif", 1)); }
    else if (arg === "hud") { hud = !hud; aman(() => world.setDynamicProperty("crvx:hud", hud ? 1 : 0)); }
    else if (arg === "turbo" || arg === "hemat" || arg === "ganas") {
      basis = arg; aman(() => world.setDynamicProperty("crvx:basis", arg)); profilSiap = false;
    } else if (arg === "reset") { terapkan(0); riwayat.length = 0; panas = 0; integral = 0; }
    else if (arg === "status") { jalankan(pemain, 4); return; }
    else {
      aman(() => world.sendMessage(TAG +
        "perintah: !crvx (menu) | nyala | mati | hud | turbo | hemat | ganas | reset | status"));
      return;
    }
    aman(() => world.sendMessage(TAG + "ok: " + arg + " (basis " + basis.toUpperCase() +
      ", aktif=" + aktif + ", hud=" + hud + ")"));
  });
}));

// pesan ini SELALU dikirim (walau governor nonaktif) supaya kita bisa
// memastikan skrip benar-benar termuat - dan membedakannya dari pack lama.
aman(() => world.afterEvents.worldLoad.subscribe(() => {
  system.runTimeout(() => {
    muatState();
    world.sendMessage(TAG + "\u00a7lv3.1\u00a7r termuat" +
      (aktif ? " & AKTIF" : " (nonaktif - ketik !crvx nyala)") +
      ". Ketik \u00a7d!crvx\u00a7r untuk menu lubang hitam. Level awal: " +
      LABEL[learned] + ".");
  }, 40);
}));
