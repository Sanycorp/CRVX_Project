// CRVX Sentinel - pengidentifikasi & pembersih entity add-on (v1.0)
// Tujuan: The Locust (atau mob add-on mana pun) sering tidak bisa /kill karena
// kebal damage atau punya logika respawn saat mati. Entity.remove() tidak memakai
// jalur kematian sama sekali (tanpa animasi mati, tanpa loot), jadi logika itu
// tidak pernah sempat jalan. /scriptevent hanya butuh "Cheats: On" di pengaturan
// dunia - tidak perlu operator server.
import { world, system } from "@minecraft/server";

const TAG = "\u00a7b\u00a7l[CRVX]\u00a7r ";
const BATAS = 64;
const AKU = ["minecraft:", "crvx:"];

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

function ringkas(hitung, n) {
  const kunci = Object.keys(hitung).sort();
  const baris = [];
  for (let i = 0; i < Math.min(kunci.length, n); i++) baris.push(kunci[i] + " x" + hitung[kunci[i]]);
  if (kunci.length > n) baris.push("+" + (kunci.length - n) + " tipe lain");
  return baris.join(", ");
}

function pindai(p) {
  const pos = aman(function () { return p.location; });
  const dim = aman(function () { return p.dimension; });
  if (!pos || !dim) { aman(function () { return world.sendMessage(TAG + "lokasi pemain tidak terbaca."); }); return; }
  const semua = aman(function () { return dim.getEntities({ location: pos, maxDistance: 32 }); }) || [];
  const hitung = {};
  let nasing = 0;
  for (let i = 0; i < semua.length; i++) {
    const t = aman(function () { return semua[i].typeId; }) || "?";
    hitung[t] = (hitung[t] || 0) + 1;
    if (asing(t)) nasing++;
  }
  aman(function () { return world.sendMessage(TAG + "scan: " + semua.length + " entity dalam 32 blok (" + nasing + " dari add-on)"); });
  aman(function () { return world.sendMessage(TAG + "  " + (semua.length ? ringkas(hitung, 12) : "(kosong)")); });
  if (nasing > 0) aman(function () { return world.sendMessage(TAG + "entity add-on di atas inilah The Locust dkk. Pakai: /scriptevent crvx:basmi 24"); });
}

function basmi(p, teks) {
  const r = Math.max(4, Math.min(BATAS, parseInt(teks, 10) || 24));
  const pos = aman(function () { return p.location; });
  const dim = aman(function () { return p.dimension; });
  if (!pos || !dim) { aman(function () { return world.sendMessage(TAG + "lokasi pemain tidak terbaca."); }); return; }
  const semua = aman(function () { return dim.getEntities({ location: pos, maxDistance: r }); }) || [];
  const mati = {};
  let n = 0;
  for (let i = 0; i < semua.length; i++) {
    const t = aman(function () { return semua[i].typeId; }) || "?";
    if (!asing(t)) continue; // entity vanilla & entity CRVX (sentinel) tidak disentuh
    aman(function () { return semua[i].remove(); });
    mati[t] = (mati[t] || 0) + 1;
    n++;
  }
  aman(function () { return world.sendMessage(TAG + (n ? "dibasmi " + n + " entity add-on <= " + r + " blok: " + ringkas(mati, 8) : "bersih - tidak ada entity add-on <= " + r + " blok")); });
  if (!n) return;
  system.runTimeout(function () {
    const sisa = (aman(function () { return dim.getEntities({ location: pos, maxDistance: r }); }) || []).filter(function (e) {
      return asing(aman(function () { return e.typeId; }) || "?");
    }).length;
    aman(function () { return world.sendMessage(TAG + "sisa setelah 3 detik: " + sisa + " entity add-on" + (sisa ? " -> ada spawner/skrip pemanggil; basmi lagi atau hancurkan blok pemanggilnya" : " (habis)")); });
  }, 60);
}

function bantuan() {
  aman(function () { return world.sendMessage(TAG + "Perintah CRVX Sentinel (Cheats: On di dunia ini):"); });
  aman(function () { return world.sendMessage(TAG + "  /scriptevent crvx:scan          -> cetak typeId semua entity <= 32 blok"); });
  aman(function () { return world.sendMessage(TAG + "  /scriptevent crvx:basmi 24      -> remove() entity add-on <= 24 blok"); });
  aman(function () { return world.sendMessage(TAG + "  /scriptevent crvx:bantuan       -> teks ini"); });
  aman(function () { return world.sendMessage(TAG + "  /summon crvx:sentinel           -> panggil penjaga (atau buat Telur Sentinel di crafting table)"); });
}

system.run(function () {
  aman(function () { return world.sendMessage(TAG + "Sentinel v1.0 aktif. Ketik /scriptevent crvx:bantuan"); });
});

aman(function () {
  world.afterEvents.scriptEventReceive.subscribe(function (ev) {
    const id = aman(function () { return ev.id; }) || "";
    const p = sumber(ev);
    if (id === "crvx:scan" && p) return system.run(function () { pindai(p); });
    if (id === "crvx:basmi" && p) {
      const teks = aman(function () { return ev.message; }) || "24";
      return system.run(function () { basmi(p, teks); });
    }
    if (id === "crvx:bantuan") return system.run(function () { bantuan(); });
  });
});
