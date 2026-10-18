// CRVX Sentinel v3.0 - Ksatria Void tak bisa mati + tangga pembunuh mob kebal
//
// Kenapa /kill @e gagal pada The Locust (dan kenapa skrip ini tidak):
//  1. /kill memakai jalur damage "override" biasa -> komponen kebal add-on
//     (damage_sensor deals_damage:false / health dikunci) menolaknya.
//  2. Mob yang mati lewat jalur kematian sering memanggil event on-death
//     milik add-on sendiri -> respawn / memanggil ulang kawanan.
// Skrip ini memakai TANGGA tiga anak tangga per entity:
//   1) applyDamage(1e9, cause "override")  - sebab damage paling absolut di
//      enum EntityDamageCause resmi; kalau HP-nya raksasa, ini tetap menembus.
//   2) teleport ke y=-80 (void)            - untuk yang kebal damage; void
//      memberi damage tiap tick dari dalam engine, bukan dari perintah.
//   3) Entity.remove()                     - dokumen resmi: tanpa animasi mati
//      dan tanpa loot, jadi event on-death add-on TIDAK pernah dijalankan ->
//      respawn-nya tidak sempat terjadi.
// Pelatuk otomatis: tiap pukulan Sentinel yang dinolkan (entityHurt dengan
// damage 0) atau mengenai entity add-on langsung menaiki tangga ini, jadi
// Sentinel benar-benar "yang membunuh The Locust" tanpa perlu perintah chat.
import { world, system } from "@minecraft/server";

const TAG = "\u00a7b\u00a7l[CRVX]\u00a7r ";
const BATAS = 64;
const AKU = ["minecraft:", "crvx:"];
const PROBE = 1000000000;          // 1e9: menembus HP raksasa sekalipun
const VOID_Y = -80;                // di bawah dunia -> void damage engine
const TUNGGU = 40;                 // tick sebelum anak tangga ke-3
const MUSUH_VANILLA = ["zombie", "skeleton", "creeper", "spider", "cave_spider",
  "witch", "blaze", "ghast", "husk", "drowned", "stray", "phantom", "pillager",
  "vindicator", "evoker", "ravager", "vex", "warden", "wither", "ender_dragon",
  "elder_guardian", "wither_skeleton", "hoglin", "piglin_brute", "zombified_piglin"];

let autoId = null;
const pantau = [];                 // {e, label} menunggu cek void

function aman(fn) {
  try { return fn(); } catch (e) { return null; }
}

function sumber(ev) {
  const s = aman(function () { return ev.sourceEntity; });
  if (s && aman(function () { return s.typeId; }) === "minecraft:player") return s;
  const semua = aman(function () { return world.getPlayers(); }) || [];
  return semua[0] || null;
}

function asing(typeId) {
  for (let i = 0; i < AKU.length; i++) {
    if (typeId.indexOf(AKU[i]) === 0) return false;
  }
  return true;
}

function musuhVanilla(typeId) {
  const ekor = typeId.split(":")[1] || "";
  return MUSUH_VANILLA.indexOf(ekor) >= 0;
}

function hp(e) {
  const c = aman(function () { return e.getComponent("minecraft:health"); });
  if (!c) return null;
  const v = aman(function () { return c.currentValue; });
  return typeof v === "number" ? v : null;
}

function lokasi(e) {
  return aman(function () { return e.location; });
}

function lapor(teks) {
  aman(function () { return world.sendMessage(TAG + teks); });
}

function ringkas(hitung, n) {
  const kunci = Object.keys(hitung).sort();
  const baris = [];
  for (let i = 0; i < Math.min(kunci.length, n); i++) baris.push(kunci[i] + " x" + hitung[kunci[i]]);
  if (kunci.length > n) baris.push("+" + (kunci.length - n) + " tipe lain");
  return baris.join(", ");
}

// ---- anak tangga 3: remove() untuk yang lolos damage DAN void ------------- //
function cekPantau() {
  for (let i = pantau.length - 1; i >= 0; i--) {
    const p = pantau[i];
    p.sisa = (p.sisa || TUNGGU) - 20;
    if (p.sisa > 0) continue;
    pantau.splice(i, 1);
    if (!lokasi(p.e)) continue;                       // void sudah menghabisinya
    aman(function () { return p.e.remove(); });
    lapor("anak tangga 3: " + p.label + " kebal damage & void -> remove() " +
          "(tanpa animasi mati, event on-death add-on tidak jalan)");
  }
}

// ---- anak tangga 2: buang ke void (void damage datang dari engine) --------- //
function tanggaVoid(e, label) {
  aman(function () {
    const p = e.location;
    return e.teleport({ x: p.x, y: VOID_Y, z: p.z });
  });
  pantau.push({ e: e, label: label, sisa: TUNGGU });
}

// ---- tangga pembunuh: damage absolut -> void -> remove() ------------------ //
function tangga(e, label) {
  if (!lokasi(e)) return "hilang";
  const h0 = hp(e);
  if (h0 === null) { tanggaVoid(e, label); return "void"; }  // tanpa health comp
  const kena = aman(function () {
    return e.applyDamage(PROBE, { cause: "override" });
  });
  const h1 = hp(e);
  if (h1 === null || !lokasi(e)) return "damage";     // mati oleh damage absolut
  if (kena === false || h1 >= h0) {                   // kebal damage -> void
    tanggaVoid(e, label);
    return "void";
  }
  return "damage";                                    // HP turun -> pasti mati
}

function sapu(p, radius, semua) {
  const r = Math.max(4, Math.min(BATAS, radius || 24));
  const pos = lokasi(p);
  const dim = aman(function () { return p.dimension; });
  if (!pos || !dim) { lapor("lokasi pemain tidak terbaca."); return; }
  const daftar = aman(function () {
    return dim.getEntities({ location: pos, maxDistance: r });
  }) || [];
  const cara = {};
  let n = 0;
  for (let i = 0; i < daftar.length; i++) {
    const e = daftar[i];
    const t = aman(function () { return e.typeId; }) || "?";
    const target = asing(t) || (semua && musuhVanilla(t) && tanggaKebal(e));
    if (!target) continue;                            // vanilla & CRVX aman
    const cara_i = tangga(e, t);
    cara[cara_i] = (cara[cara_i] || 0) + 1;
    n++;
  }
  if (!n) { lapor("bersih - tidak ada entity add-on <= " + r + " blok" +
                  (semua ? " (mode semua: tiada musuh vanilla kebal)" : "")); return; }
  lapor("tangga pembunuh pada " + n + " entity <= " + r + " blok: " +
        Object.keys(cara).sort().map(function (k) { return k + " x" + cara[k]; }).join(", "));
  system.runTimeout(function () {
    const sisa = (aman(function () {
      return dim.getEntities({ location: pos, maxDistance: r });
    }) || []).filter(function (e) {
      const t = aman(function () { return e.typeId; }) || "?";
      return asing(t);
    }).length;
    if (sisa) lapor("sisa " + sisa + " entity add-on -> ada pemanggil ulang; " +
                    "jalankan lagi atau /scriptevent crvx:auto on");
  }, 60);
}

function tanggaKebal(e) {
  const h0 = hp(e);
  if (h0 === null) return false;
  const kena = aman(function () { return e.applyDamage(1, { cause: "override" }); });
  const h1 = hp(e);
  if (h1 === null) return false;                      // mati = tidak kebal
  return kena === false || h1 >= h0;                  // HP tidak turun = kebal
}

// ---- pelatuk: pukulan Sentinel yang dinolkan / mengenai entity add-on ----- //
aman(function () {
  world.afterEvents.entityHurt.subscribe(function (ev) {
    const pen = aman(function () { return ev.damageSource.damagingEntity; });
    if (!pen || aman(function () { return pen.typeId; }) !== "crvx:sentinel") return;
    const v = aman(function () { return ev.hurtEntity; });
    if (!v) return;
    const t = aman(function () { return v.typeId; }) || "?";
    const dinolkan = (aman(function () { return ev.damage; }) || 0) === 0;
    if (!asing(t) && !(dinolkan && musuhVanilla(t))) return;
    system.run(function () {
      const cara = tangga(v, t);
      const hilang = !lokasi(v);
      if (hilang || cara !== "damage") {
        lapor("Sentinel vs " + t + ": anak tangga '" + cara + "'" +
              (hilang ? " - MATI" : " - menunggu void/remove"));
      }
    });
  });
});

// interval permanen murah: hanya bekerja bila ada entity di anak tangga void
system.runInterval(function () {
  if (pantau.length) cekPantau();
}, 20);

// ---- zirah lapis 2: HP dipulihkan SKETIKA setelah tiap pukulan ------------- //
// damage_sensor sudah menolak cause override/fall/void/magic/wither/ledakan;
// sisa damage (mis. entity_attack The Locust) disembuhkan lewat
// EntityHealthComponent.resetToMaxValue() - contoh resmi d.ts 2.0.0. Hasilnya:
// Sentinel tidak pernah kehilangan 1 HP pun permanen = tak terkalahkan.
aman(function () {
  world.afterEvents.entityHurt.subscribe(function (ev) {
    const v = aman(function () { return ev.hurtEntity; });
    if (!v || aman(function () { return v.typeId; }) !== "crvx:sentinel") return;
    system.run(function () {
      const h = aman(function () { return v.getComponent("minecraft:health"); });
      if (h) aman(function () { return h.resetToMaxValue(); });
    });
  });
});

// ---- daemon pembasmi (opt-in): sapu otomatis tiap 4 detik ------------------ //
function autoHidup() {
  if (autoId !== null) return false;
  autoId = system.runInterval(function () {
    const ps = aman(function () { return world.getPlayers(); }) || [];
    for (let i = 0; i < ps.length; i++) {
      const pos = lokasi(ps[i]);
      const dim = aman(function () { return ps[i].dimension; });
      if (!pos || !dim) continue;
      const daftar = aman(function () {
        return dim.getEntities({ location: pos, maxDistance: 48 });
      }) || [];
      let n = 0;
      const cara = {};
      for (let j = 0; j < daftar.length; j++) {
        const t = aman(function () { return daftar[j].typeId; }) || "?";
        if (!asing(t)) continue;
        const cara_i = tangga(daftar[j], t);
        cara[cara_i] = (cara[cara_i] || 0) + 1;
        n++;
      }
      if (n) lapor("auto-basmi " + n + " entity add-on: " +
                   Object.keys(cara).sort().map(function (k) { return k + " x" + cara[k]; }).join(", "));
    }
  }, 80);
  return true;
}

function autoMati() {
  if (autoId === null) return false;
  aman(function () { return system.clearRun(autoId); });
  autoId = null;
  return true;
}

// ---- lepas: panggil pulang Sentinel milik sendiri (remove(), bukan kill) --- //
function lepas(p, radius) {
  const r = Math.max(4, Math.min(BATAS, radius || 16));
  const pos = lokasi(p);
  const dim = aman(function () { return p.dimension; });
  if (!pos || !dim) { lapor("lokasi pemain tidak terbaca."); return; }
  const daftar = aman(function () {
    return dim.getEntities({ location: pos, maxDistance: r });
  }) || [];
  let n = 0;
  for (let i = 0; i < daftar.length; i++) {
    if ((aman(function () { return daftar[i].typeId; }) || "") !== "crvx:sentinel") continue;
    aman(function () { return daftar[i].remove(); });
    n++;
  }
  lapor(n ? "dilepas " + n + " Sentinel <= " + r + " blok (remove(), hormat)."
          : "tidak ada Sentinel <= " + r + " blok.");
}

// ---- scan forensik: typeId + HP, biar ketahuan kenapa /kill gagal ---------- //
function pindai(p) {
  const pos = lokasi(p);
  const dim = aman(function () { return p.dimension; });
  if (!pos || !dim) { lapor("lokasi pemain tidak terbaca."); return; }
  const daftar = aman(function () {
    return dim.getEntities({ location: pos, maxDistance: 32 });
  }) || [];
  const hitung = {};
  let nasing = 0;
  for (let i = 0; i < daftar.length; i++) {
    const t = aman(function () { return daftar[i].typeId; }) || "?";
    const h = hp(daftar[i]);
    const kunci = t + (h === null ? "" : " hp" + Math.round(h));
    hitung[kunci] = (hitung[kunci] || 0) + 1;
    if (asing(t)) nasing++;
  }
  lapor("scan: " + daftar.length + " entity dalam 32 blok (" + nasing + " add-on)");
  lapor("  " + (daftar.length ? ringkas(hitung, 10) : "(kosong)"));
  if (nasing) lapor("entity add-on di atas = The Locust dkk. Bunuh: " +
                    "/scriptevent crvx:basmi 24  atau  /scriptevent crvx:auto on");
}

function bantuan() {
  lapor("CRVX Sentinel v3.0 - Ksatria Void tak bisa mati (Cheats: On):");
  lapor("  /scriptevent crvx:scan          -> typeId + HP entity <= 32 blok");
  lapor("  /scriptevent crvx:basmi 24      -> tangga: damage 1e9 -> void -> remove()");
  lapor("  /scriptevent crvx:basmi 24 semua-> + musuh vanilla yang dibuat kebal");
  lapor("  /scriptevent crvx:auto on|off   -> daemon sapu otomatis tiap 4 detik");
  lapor("  /scriptevent crvx:lepas 16      -> panggil pulang Sentinel-mu sendiri");
  lapor("  /scriptevent crvx:bantuan       -> teks ini");
  lapor("Pukulan Sentinel yang dinolkan mob kebal otomatis menaiki tangga ini.");
}

system.run(function () {
  lapor("Sentinel v3.0 aktif: Ksatria Void tak bisa mati. /scriptevent crvx:bantuan");
});

aman(function () {
  world.afterEvents.scriptEventReceive.subscribe(function (ev) {
    const id = aman(function () { return ev.id; }) || "";
    const p = sumber(ev);
    if (id === "crvx:scan" && p) return system.run(function () { pindai(p); });
    if (id === "crvx:basmi" && p) {
      const teks = (aman(function () { return ev.message; }) || "24").split(" ");
      const r = parseInt(teks[0], 10) || 24;
      const semua = teks.indexOf("semua") >= 0;
      return system.run(function () { sapu(p, r, semua); });
    }
    if (id === "crvx:auto") {
      const mau = (aman(function () { return ev.message; }) || "").trim();
      return system.run(function () {
        if (mau === "on") laporanAuto(autoHidup(), true);
        else if (mau === "off") laporanAuto(autoMati(), false);
        else lapor("auto: " + (autoId !== null ? "NYALA" : "mati") +
                   " - pakai: /scriptevent crvx:auto on|off");
      });
    }
    if (id === "crvx:lepas" && p) {
      const r = parseInt(aman(function () { return ev.message; }) || "16", 10) || 16;
      return system.run(function () { lepas(p, r); });
    }
    if (id === "crvx:bantuan") return system.run(function () { bantuan(); });
  });
});

function laporanAuto(berhasil, hidup) {
  if (!berhasil) { lapor("auto sudah " + (hidup ? "nyala" : "mati") + "."); return; }
  lapor(hidup ? "auto-basmi NYALA: entity add-on dalam 48 blok disapu tiap 4 detik."
              : "auto-basmi mati.");
}
