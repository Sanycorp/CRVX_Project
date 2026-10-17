/* CRVX TurboFrame - Control Panel */
(() => {
"use strict";

const $ = (id) => document.getElementById(id);
const S = { state: null, plan: null, bench: null, compare: null, govTimer: null, expanded: new Set(), planOpen: true };
const ACCENTS = { "60": "#38bdf8", "90": "#a78bfa", "120": "#f472b6", "144": "#fbbf24" };

/* ------------------------------------------------------------------ utils */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 1) => (n === null || n === undefined || isNaN(n) ? "—" : Number(n).toFixed(d));

function log(msg, kind = "") {
  const el = $("log");
  const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
  el.innerHTML += `<span class="t">[${time}]</span> <span class="${kind}">${esc(msg)}</span>\n`;
  el.scrollTop = el.scrollHeight;
}

function toast(msg, kind = "ok") {
  const wrap = $("toasts");
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = msg;
  wrap.appendChild(node);
  setTimeout(() => { node.style.opacity = "0"; node.style.transition = ".3s"; }, 3200);
  setTimeout(() => node.remove(), 3600);
}

async function api(path, body = null) {
  const opt = body === null ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({ error: "respons bukan JSON" }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function busy(btn, on, label = "") {
  if (!btn) return;
  if (on) { btn.dataset.old = btn.innerHTML; btn.classList.add("busy"); btn.disabled = true; }
  else { btn.classList.remove("busy"); btn.disabled = false; if (label) btn.innerHTML = label; else if (btn.dataset.old) btn.innerHTML = btn.dataset.old; }
}

/* ------------------------------------------------------------------ canvas */
function fit(canvas, cssHeight) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || canvas.width;
  canvas.width = Math.max(160, Math.round(w * dpr));
  canvas.height = Math.max(80, Math.round(cssHeight * dpr));
  canvas.style.height = cssHeight + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h: cssHeight };
}

function drawGauge() {
  const canvas = $("gauge");
  if (!canvas) return;
  const { ctx, w, h } = fit(canvas, 190);
  ctx.clearRect(0, 0, w, h);
  const p = S.plan && S.plan.projection;
  const cx = w / 2, cy = h * 0.72, r = Math.min(w * 0.38, h * 0.6);
  const start = Math.PI * 0.78, end = Math.PI * 2.22;
  const target = p ? Math.max(p.target_fps, 60) : 120;
  const value = p ? p.reachable_fps : 0;
  const ratio = Math.max(0, Math.min(1, value / target));

  ctx.lineCap = "round";
  ctx.lineWidth = 13;
  ctx.strokeStyle = "rgba(255,255,255,.07)";
  ctx.beginPath(); ctx.arc(cx, cy, r, start, end); ctx.stroke();

  if (ratio > 0) {
    const grad = ctx.createLinearGradient(cx - r, cy, cx + r, cy);
    grad.addColorStop(0, "#38bdf8"); grad.addColorStop(.55, "#a78bfa"); grad.addColorStop(1, "#f472b6");
    ctx.strokeStyle = grad;
    ctx.shadowColor = "rgba(244,114,182,.55)"; ctx.shadowBlur = 18;
    ctx.beginPath(); ctx.arc(cx, cy, r, start, start + (end - start) * ratio); ctx.stroke();
    ctx.shadowBlur = 0;
  }

  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255,255,255,.25)";
  for (let i = 0; i <= 4; i++) {
    const a = start + (end - start) * (i / 4);
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * (r + 11), cy + Math.sin(a) * (r + 11));
    ctx.lineTo(cx + Math.cos(a) * (r + 17), cy + Math.sin(a) * (r + 17));
    ctx.stroke();
  }

  ctx.textAlign = "center";
  ctx.fillStyle = "#e7ecf5";
  ctx.font = "700 34px ui-monospace, monospace";
  ctx.fillText(value ? value.toFixed(1) : "—", cx, cy - 2);
  ctx.fillStyle = "#5d6880";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText("FPS PERKIRAAN", cx, cy + 16);
  ctx.fillStyle = "#8b96ad";
  ctx.font = "600 11px ui-monospace, monospace";
  ctx.fillText(`target ${target} FPS`, cx, cy + 34);
}

function drawChart() {
  const canvas = $("fps-chart");
  if (!canvas) return;
  const { ctx, w, h } = fit(canvas, 180);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 34, r: 12, t: 12, b: 20 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

  const series = (S.bench && S.bench.samples) || [];
  const target = (S.bench && S.bench.target_fps) || (S.plan && S.plan.projection
    ? S.plan.projection.target_fps : 60);
  const maxFps = Math.max(target * 1.15, ...series.map((s) => s.fps), 30);

  ctx.strokeStyle = "rgba(255,255,255,.06)"; ctx.lineWidth = 1;
  ctx.font = "9px ui-monospace, monospace"; ctx.fillStyle = "#5d6880"; ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (ih * i) / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
    ctx.fillText(Math.round(maxFps * (1 - i / 4)), pad.l - 6, y + 3);
  }

  const ty = pad.t + ih * (1 - target / maxFps);
  ctx.strokeStyle = "rgba(244,114,182,.55)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.moveTo(pad.l, ty); ctx.lineTo(w - pad.r, ty); ctx.stroke();
  ctx.setLineDash([]);
  ctx.textAlign = "left"; ctx.fillStyle = "#f472b6";
  ctx.fillText(`target ${target}`, pad.l + 4, ty - 4);

  if (series.length < 2) {
    ctx.textAlign = "center"; ctx.fillStyle = "#5d6880"; ctx.font = "11px Inter, sans-serif";
    ctx.fillText("belum ada sampel — jalankan pengukuran saat Minecraft berjalan", w / 2, h / 2);
    return;
  }
  const x = (i) => pad.l + (iw * i) / (series.length - 1);
  const y = (v) => pad.t + ih * (1 - Math.max(0, v) / maxFps);

  ctx.beginPath(); ctx.moveTo(x(0), y(series[0].fps));
  series.forEach((s, i) => ctx.lineTo(x(i), y(s.fps)));
  const grad = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
  grad.addColorStop(0, "rgba(56,189,248,.35)"); grad.addColorStop(1, "rgba(56,189,248,0)");
  ctx.lineTo(x(series.length - 1), h - pad.b); ctx.lineTo(x(0), h - pad.b); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  ctx.beginPath(); ctx.moveTo(x(0), y(series[0].fps));
  series.forEach((s, i) => ctx.lineTo(x(i), y(s.fps)));
  ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2;
  ctx.shadowColor = "rgba(56,189,248,.6)"; ctx.shadowBlur = 10; ctx.stroke(); ctx.shadowBlur = 0;

  series.forEach((s, i) => {
    ctx.beginPath(); ctx.arc(x(i), y(s.fps), 2.4, 0, Math.PI * 2);
    ctx.fillStyle = s.thermal >= 3 ? "#fb7185" : "#e7ecf5"; ctx.fill();
  });

  if (series.some((s) => s.thermal >= 3)) {
    ctx.textAlign = "right"; ctx.fillStyle = "#fb7185"; ctx.font = "9px ui-monospace, monospace";
    ctx.fillText("● titik merah = thermal throttling", w - pad.r, h - 6);
  }
}

/* ------------------------------------------------------------------ render */
function renderTopbar(dev, engine) {
  $("engine-version").textContent = `v${engine.version} · ${engine.codename}`;
  $("footer-rev").textContent = engine.version;
  const sim = dev.simulated;
  $("chip-transport").innerHTML =
    `<i class="dot"></i>${esc(engine.transport.toUpperCase())}${sim ? " · SIM" : ""}`;
  $("chip-transport").className = "chip" + (sim ? " warn" : "");
  $("chip-device").innerHTML = `<b>${esc(dev.brand || dev.manufacturer || "?")} ${esc(dev.model)}</b>`;
  $("chip-tier").innerHTML = `tier <b>${esc(dev.extras.tier_name || "?")}</b>`;
  const th = dev.thermal_status;
  $("chip-thermal").innerHTML = `termal <b>${th}</b> · ${fmt(dev.battery_temp_c, 1)}°C`;
  $("chip-thermal").className = "chip" + (th >= 4 ? " bad" : th >= 2 ? " warn" : "");
  $("device-sim-badge").hidden = !sim;
}

function capRow(label, value, max, color) {
  const pct = max > 0 ? Math.max(2, Math.min(100, (value / max) * 100)) : 0;
  return `<div class="cap-row"><span>${label}</span>
    <div class="cap-bar"><i style="width:${pct}%;background:${color}"></i></div>
    <b>${value ? fmt(value, 0) : "—"}</b></div>`;
}

function renderDevice(dev) {
  const mc = dev.minecraft || {};
  const tier = dev.extras.tier_name || "MID";
  const rates = dev.refresh_rates || [];
  const maxRate = Math.max(165, ...rates);
  $("device-body").innerHTML = `
    <div class="device-title">
      <strong>${esc(dev.brand || dev.manufacturer)} ${esc(dev.model)}</strong>
      <span class="tier-badge tier-${tier}">${tier}</span>
      <em>${esc(dev.codename || "")}</em>
    </div>
    <dl class="kv">
      <dt>SoC</dt><dd>${esc(dev.extras.soc_name || dev.soc_model || dev.board_platform || "tidak dikenal")}</dd>
      <dt>GPU</dt><dd>${esc(dev.gpu_renderer || dev.extras.gpu_name || "—")}</dd>
      <dt>Android</dt><dd>${esc(dev.android_release)} <b>SDK ${dev.android_sdk}</b></dd>
      <dt>RAM / Core</dt><dd>${Math.round((dev.ram_mb || 0) / 1024)} GB · ${dev.cpu_cores} @ ${Math.round((dev.cpu_max_khz || 0) / 1000)} MHz</dd>
      <dt>Layar</dt><dd>${esc(dev.extras.screen || "—")} · aktif <b>${fmt(dev.active_fps, 0)} Hz</b></dd>
      <dt>Game Mode</dt><dd>${dev.game_mode_supported ? "didukung · <b>" + esc(dev.game_mode_current) + "</b>" : "tidak didukung"}</dd>
      <dt>Root/Shizuku</dt><dd>${dev.rooted ? "<b>root</b>" : "tidak"} · ${dev.shizuku ? "shizuku" : "—"}</dd>
      <dt>Minecraft</dt><dd><b>${esc(mc.version_name || "tidak ada")}</b> ${esc(mc.version_code || "")}</dd>
      <dt>options.txt</dt><dd>${mc.writable ? "<b>bisa ditulis</b>" : "terkunci"}</dd>
      <dt>Baterai</dt><dd>${dev.battery_level}% · ${fmt(dev.battery_temp_c, 1)}°C ${dev.charging ? "· charging" : ""}</dd>
    </dl>
    <div class="hz-chips">${rates.map((r) =>
      `<span class="hz ${Math.abs(r - dev.active_fps) < 0.6 ? "active" : ""}">${fmt(r, 0)} Hz</span>`).join("")
      || '<span class="hz">tidak terbaca</span>'}</div>`;

  $("capability").innerHTML =
    capRow("Panel", dev.panel_max_fps, maxRate, "linear-gradient(90deg,#38bdf8,#7dd3fc)") +
    capRow("Cap engine", dev.engine_cap_fps, maxRate, "linear-gradient(90deg,#a78bfa,#f472b6)") +
    capRow("Target mode", (S.plan && S.plan.projection ? S.plan.projection.target_fps : 120), maxRate,
      "linear-gradient(90deg,#f472b6,#fbbf24)") +
    `<p class="hint" style="margin-top:2px">Cap engine: ${esc(dev.engine_cap_reason || "—")}</p>`;

  const opts = mc.current_options || {};
  const interesting = ["gfx_viewdistance", "gfx_msaa", "gfx_vsync", "gfx_max_framerate",
    "gfx_smoothlighting", "gfx_transparentleaves", "gfx_fancyskies", "gfx_particleviewdistance",
    "gfx_multithreaded_renderer", "gfx_field_of_view", "gfx_max_framerate_advanced"];
  const planOpts = (S.plan && S.plan.steps || []).flatMap((s) => s.commands)
    .map((c) => (c.shell.match(/s\/\^(gfx_\w+):\.\*\/\1:([^/']+)/) || []));
  const changed = new Set(planOpts.filter((m) => m.length).map((m) => m[1]));
  $("options-path").textContent = (mc.options_path || "—").replace(/^\/sdcard\/Android\/data\//, "…/");
  $("options-grid").innerHTML = interesting
    .filter((k) => k in opts)
    .map((k) => `<div class="opt ${changed.has(k) ? "changed" : ""}"><span>${k}</span><b>${esc(opts[k])}</b></div>`)
    .join("") || '<p class="muted">options.txt belum terbaca — jalankan deteksi ulang dengan perangkat tersambung.</p>';
}

function renderModes(modes, selection, dev) {
  $("mode-grid").innerHTML = modes.map((m) => {
    const accent = ACCENTS[m.id] || "#f472b6";
    const sel = String(selection.mode) === String(m.id);
    let stateCls = "ok", stateTxt = "READY";
    if (!m.feasible) { stateCls = "no"; stateTxt = "LAYAR TIDAK MENDUKUNG"; }
    else if (m.engine_capped) { stateCls = "cap"; stateTxt = "TERBATAS ENGINE"; }
    const b = m.budget || {};
    return `<div class="mode ${sel ? "sel" : ""}" data-mode="${m.id}" style="--accent:${accent}">
      <span class="state ${stateCls}">${stateTxt}</span>
      <div class="fps">${m.id}<small>FPS</small></div>
      <div class="name">${esc(m.name.replace("MODE ", ""))}</div>
      <div class="tagline">${esc(m.tagline)}</div>
      <div class="budget">
        <span>${b.chunks ?? "?"} chunk</span>
        <span>MSAA ${b.msaa ?? "?"}x</span>
        <span>vsync ${b.vsync ? "on" : "off"}</span>
        <span>scale ${Math.round((b.downscale ?? 1) * 100)}%</span>
        <span>target ${m.effective_target ?? m.target_fps}</span>
      </div>
    </div>`;
  }).join("");

  document.querySelectorAll(".mode").forEach((node) => {
    node.onclick = () => { S.mode = node.dataset.mode; renderModes(modes, { mode: S.mode }, dev); refreshSummary(); };
  });
  const chosen = modes.find((m) => String(m.id) === String(selection.mode)) || modes[2];
  S.mode = chosen.id;
  refreshSummary(chosen);
}

function refreshSummary(mode) {
  const dev = S.state && S.state.device;
  if (!dev) return;
  const m = mode || (S.state.modes || []).find((x) => String(x.id) === String(S.mode));
  if (!m) return;
  const cap = Math.min(dev.panel_max_fps, dev.engine_cap_fps);
  const eff = Math.min(m.target_fps, cap);
  $("apply-summary").innerHTML =
    `Mode <b style="color:${ACCENTS[m.id]}">${m.target_fps} FPS</b> → target efektif ` +
    `<b>${eff} FPS</b> (batas perangkat ${fmt(cap, 0)} FPS)`;
  $("apply-risknote").textContent =
    `risiko maks ${m.risk_ceiling} · ${m.notes.length} catatan engine · ` +
    `${(S.plan && S.plan.steps || []).length} langkah siap`;
}

function renderProjection(plan) {
  if (!plan) {
    $("proj-numbers").innerHTML = '<p class="muted">Susun rencana untuk melihat proyeksi.</p>';
    $("proj-notes").innerHTML = "";
    drawGauge();
    return;
  }
  const p = plan.projection;
  $("proj-mode").textContent = plan.mode_name;
  const confCls = p.confidence >= 0.7 ? "good" : p.confidence >= 0.5 ? "warn" : "bad";
  $("proj-numbers").innerHTML = `
    <div class="pnum good"><b>${fmt(p.reachable_fps)}</b><small>FPS tercapai</small></div>
    <div class="pnum"><b>${fmt(p.ceiling_fps, 0)}</b><small>batas atas</small></div>
    <div class="pnum"><b>${fmt(p.frametime_ms, 2)}</b><small>ms / frame</small></div>
    <div class="pnum"><b>${fmt(p.stability, 0)}</b><small>stabilitas</small></div>
    <div class="pnum ${confCls}"><b>${Math.round(p.confidence * 100)}%</b><small>keyakinan</small></div>
    <div class="pnum ${p.battery_pct > 25 ? "bad" : p.battery_pct > 12 ? "warn" : "good"}">
      <b>+${fmt(p.battery_pct, 0)}%</b><small>baterai</small></div>`;
  $("proj-notes").innerHTML = (p.notes || []).map((n, i) =>
    `<li class="${i % 2 ? "info" : ""}">${esc(n)}</li>`).join("");
  drawGauge();
}

function stepState(s) {
  if (!s.applied) return { cls: "", txt: "siap" };
  if (!s.ok) return { cls: "fail", txt: "GAGAL" };
  if (s.verify_passed === true) return { cls: "verif", txt: "✓ TERVERIFIKASI" };
  if (s.verify_passed === false) return { cls: "warn", txt: "⚠ belum cocok" };
  return { cls: "ok", txt: "OK" };
}

function renderPlan(plan) {
  if (!plan) return;
  $("plan-id").textContent = plan.id;
  $("plan-count").textContent = `${plan.steps.length} langkah · risiko ≤ ${plan.risk_ceiling}`;
  $("plan-body").innerHTML = plan.steps.map((s, i) => {
    const r = s.rule, st = stepState(s);
    const open = S.expanded.has(r.id);
    const gain = r.gain || {};
    return `<div class="step ${open ? "open" : ""}" data-id="${esc(r.id)}">
      <div class="step-head">
        <span class="step-idx">${String(i + 1).padStart(2, "0")}</span>
        <span class="step-title">${esc(r.title)}</span>
        <span class="step-cat">${esc(r.category)}</span>
        <span class="risk risk-${r.risk}">${esc(r.risk)}</span>
        <span class="step-gain">${gain.fps ? (gain.fps > 0 ? "+" : "") + fmt(gain.fps, 1) + " fps" : ""}</span>
        <span class="step-state ${st.cls}">${st.txt}</span>
      </div>
      <div class="step-detail">
        <p class="step-desc">${esc(r.description)}</p>
        ${s.commands.map((c) => `<div class="cmd ${c.root ? "root" : ""}">
            <span class="lbl">${esc(c.label || "perangkat")}${c.root ? " · ROOT" : ""}${c.optional ? " · opsional" : ""}</span>${esc(c.shell)}</div>`).join("")}
        ${s.commands.filter((c) => c.undo).map((c) =>
          `<div class="cmd cmd-undo"><span class="lbl">undo</span>${esc(c.undo)}</div>`).join("")}
        ${s.verify_result ? `<div class="verify"><b>verifikasi:</b>\n${esc(s.verify_result.slice(0, 900))}</div>` : ""}
        ${s.error ? `<div class="verify" style="color:#fb7185"><b>error:</b>\n${esc(s.error.slice(0, 900))}</div>` : ""}
      </div>
    </div>`;
  }).join("") || '<p class="muted">Tidak ada langkah yang lolos filter.</p>';

  document.querySelectorAll(".step-head").forEach((h) => {
    h.onclick = () => {
      const node = h.parentElement, id = node.dataset.id;
      node.classList.toggle("open");
      node.classList.contains("open") ? S.expanded.add(id) : S.expanded.delete(id);
    };
  });

  const skipped = plan.skipped || [];
  $("skipped-wrap").hidden = skipped.length === 0;
  $("skipped-summary").textContent = `Aturan yang dilewati (${skipped.length})`;
  $("skipped-body").innerHTML = skipped.map((it) =>
    `<div class="skip-item"><b>${esc(it.rule.title)}</b> — ${esc((it.reasons || []).join("; "))}</div>`).join("");
}

function statCard(label, value, cls = "") {
  return `<div class="stat ${cls}"><b>${value}</b><small>${label}</small></div>`;
}

function renderBench(res, cmp) {
  if (!res) return;
  $("bench-stats").innerHTML = [
    statCard("FPS rata-rata", fmt(res.fps_avg), res.fps_avg >= 55 ? "hi" : ""),
    statCard("1% low", fmt(res.fps_p1), res.fps_p1 < 25 ? "lo" : ""),
    statCard("5% low", fmt(res.fps_p5)),
    statCard("median", fmt(res.fps_p50)),
    statCard("maks", fmt(res.fps_max)),
    statCard("frame avg", fmt(res.frametime_avg_ms, 2) + " ms"),
    statCard("frame p95", fmt(res.frametime_p95_ms, 2) + " ms"),
    statCard("jank", res.jank, res.jank > 20 ? "lo" : "hi"),
    statCard("stutter", fmt(res.stutter_index) + "%"),
    statCard("smoothness", fmt(res.smoothness_score, 0) + "/100", res.smoothness_score >= 70 ? "hi" : ""),
    statCard("termal", `${res.thermal_start}→${res.thermal_end}`),
    statCard("suhu", `${fmt(res.temp_start)}→${fmt(res.temp_end)}°C`),
  ].join("");

  const box = $("bench-compare");
  if (cmp) {
    const down = cmp.fps_gain < 0;
    box.hidden = false;
    box.className = "compare" + (down ? " down" : "");
    box.innerHTML = `
      <div><div class="big">${down ? "" : "+"}${fmt(cmp.fps_gain)} FPS</div>
        <div class="row">${esc(cmp.verdict)} · ${fmt(cmp.fps_gain_pct)}%</div></div>
      <div class="row">1% low: ${fmt(cmp.p1_before)} → <b>${fmt(cmp.p1_after)}</b></div>
      <div class="row">frame: ${fmt(cmp.frametime_gain_ms, 2)} ms</div>
      <div class="row">jank: ${cmp.jank_gain > 0 ? "+" : ""}${cmp.jank_gain}</div>
      <div class="row">stutter: ${fmt(cmp.stutter_gain, 2)}%</div>
      <div class="row">smoothness: ${cmp.smoothness_gain > 0 ? "+" : ""}${fmt(cmp.smoothness_gain, 1)}</div>
      <div class="row">suhu: ${cmp.temp_gain_c > 0 ? "+" : ""}${fmt(cmp.temp_gain_c, 1)}°C</div>`;
  } else box.hidden = true;
  drawChart();
}

function renderGovernor(d) {
  if (!d) return;
  $("gov-fps").textContent = fmt(d.measured_fps, 0);
  $("gov-fps").style.color = d.error > 12 ? "#fb7185" : d.error > 4 ? "#fbbf24" : "#34d399";
  $("gov-meta").innerHTML = `
    <span>target <b>${fmt(d.target_fps, 0)}</b> fps · error <b>${fmt(d.error, 1)}</b></span>
    <span>PID out <b>${fmt(d.output, 2)}</b> · sumber <b>${esc(d.source || "—")}</b></span>
    <span>termal <b>${esc(d.thermal_name)}</b> (${d.thermal}) · ${fmt(d.battery_temp, 1)}°C</span>
    <span>smoothness <b>${fmt(d.smoothness, 0)}</b>/100</span>`;
  const q = Math.round((d.quality_index || 0) * 100);
  $("quality-fill").style.width = q + "%";
  $("quality-label").textContent = `indeks kualitas ${q}%`;

  const entry = document.createElement("div");
  entry.className = "gov-entry" + (d.actions && d.actions.length ? " act" : "");
  entry.innerHTML = `<time>${new Date().toLocaleTimeString("id-ID", { hour12: false })}</time>
    <p>${esc(d.message)}</p>
    ${(d.actions || []).map((a) => `<p><b>→ ${esc(a.lever)}</b>: ${esc(a.value)} — ${esc(a.reason)}</p>`).join("")}
    ${(d.applied || []).map((a) => `<p>${a.ok ? "✓" : "✗"} <code>${esc(a.command || "")}</code></p>`).join("")}`;
  const box = $("gov-log");
  box.prepend(entry);
  while (box.children.length > 40) box.lastChild.remove();
}

function renderAll(state) {
  S.state = state;
  S.plan = state.plan;
  renderTopbar(state.device, state.engine);
  renderDevice(state.device);
  renderModes(state.modes, state.selection, state.device);
  renderProjection(state.plan);
  renderPlan(state.plan);
  $("journal-count").textContent = `${state.journal.entries} entri undo tersimpan`;
  $("opt-risk").value = state.selection.risk || "";
  $("opt-pack").checked = !!state.selection.with_pack;
  refreshSummary();
}

/* ------------------------------------------------------------------ actions */
async function load(silent = false) {
  try {
    const state = await api("/api/state");
    renderAll(state);
    if (!silent) log("state dimuat: " + state.device.model, "info");
  } catch (err) {
    log("gagal memuat state: " + err.message, "err");
    toast("Gagal memuat state: " + err.message, "err");
  }
}

async function act(btn, fn) {
  busy(btn, true);
  try { await fn(); }
  catch (err) { log("ERROR: " + err.message, "err"); toast(err.message, "err"); }
  finally { busy(btn, false); }
}

async function makePlan(thenApply = false) {
  const risk = $("opt-risk").value;
  const withPack = $("opt-pack").checked;
  const mode = S.mode || "120";
  log(`menyusun rencana mode ${mode} FPS (risiko ${risk || "ikut mode"}, pack ${withPack ? "on" : "off"})…`, "info");
  const plan = await api("/api/plan", { mode, risk, with_pack: withPack });
  S.plan = plan;
  renderPlan(plan);
  renderProjection(plan);
  renderDevice(S.state.device);
  refreshSummary();
  log(`rencana ${plan.id}: ${plan.steps.length} langkah, proyeksi ${plan.projection.reachable_fps} FPS`, "ok");
  if (thenApply) await applyPlan();
  return plan;
}

async function applyPlan() {
  const dry = $("opt-dryrun").checked;
  log(dry ? "DRY RUN — perintah hanya dicetak" : "menerapkan rencana ke perangkat…", dry ? "warn" : "hi");
  const res = await api("/api/apply", { dry_run: dry });
  const plan = Object.assign({}, S.plan, { steps: res.steps });
  S.plan = plan;
  renderPlan(plan);
  const failed = (res.failed || []).length;
  log(`eksekusi selesai: ${res.applied} langkah diterapkan, ${res.verified} terverifikasi, ` +
      `${failed} bermasalah, ${res.seconds}s`, failed ? "warn" : "ok");
  $("journal-count").textContent = "jurnal diperbarui";
  toast(failed ? `Selesai dengan ${failed} langkah bermasalah` : "Optimasi diterapkan", failed ? "warn" : "ok");
  await load(true);
}

async function undo() {
  log("mengembalikan semua perubahan (undo)…", "warn");
  const res = await api("/api/undo", {});
  log(`undo: ${res.restored} perintah dipulihkan dari ${res.entries} entri jurnal`, "ok");
  (res.failed || []).forEach((f) => log("gagal: " + f, "err"));
  toast(`${res.restored} perubahan dikembalikan`, "ok");
  await load(true);
}

async function bench(label) {
  const duration = Number($("bench-duration").value);
  log(`mengukur FPS (${label}, ${duration} detik) — pastikan Minecraft berjalan di dunia…`, "info");
  const res = await api("/api/bench", { duration, label, target: S.plan ? S.plan.projection.target_fps : 0 });
  S.bench = res;
  renderBench(res, res.compare);
  log(`${label}: ${res.fps_avg} FPS · 1% low ${res.fps_p1} · jank ${res.jank} · ` +
      `smoothness ${res.smoothness_score} · sumber ${res.source}`, res.frames ? "ok" : "warn");
  (res.notes || []).forEach((n) => log(n, "warn"));
  if (res.compare) {
    S.compare = res.compare;
    log(`perbandingan: ${res.compare.fps_before} → ${res.compare.fps_after} FPS ` +
        `(${res.compare.fps_gain > 0 ? "+" : ""}${res.compare.fps_gain} / ${res.compare.fps_gain_pct}%) ` +
        `[${res.compare.verdict}]`, res.compare.fps_gain >= 0 ? "ok" : "err");
  }
}

async function govTick() {
  const d = await api("/api/govern/tick", { mode: S.mode || "120", apply: $("gov-apply").checked });
  renderGovernor(d);
  log(`governor: FPS ${d.measured_fps} / target ${d.target_fps} · ${d.message}`,
      d.actions.length ? "warn" : "info");
  d.actions.forEach((a) => log(`  → ${a.lever} = ${a.value} (${a.reason})`, "hi"));
}

/* ------------------------------------------------------------------ wiring */
function wire() {
  $("btn-rescan").onclick = (e) => act(e.currentTarget, async () => {
    log("deteksi ulang perangkat…", "info");
    const res = await api("/api/detect", {});
    await load(true);
    log(`perangkat: ${res.device.brand} ${res.device.model} · tier ${res.device.extras.tier_name} · ` +
        `cap ${res.device.engine_cap_fps} FPS`, "ok");
    toast("Deteksi selesai", "ok");
  });

  $("btn-plan").onclick = (e) => act(e.currentTarget, () => makePlan(false));
  $("btn-apply").onclick = (e) => act(e.currentTarget, async () => {
    if (!S.plan || String(S.plan.mode_id) !== String(S.mode)) await makePlan(false);
    await applyPlan();
  });
  $("btn-undo").onclick = (e) => act(e.currentTarget, undo);
  $("btn-bench-before").onclick = (e) => act(e.currentTarget, () => bench("before"));
  $("btn-bench-after").onclick = (e) => act(e.currentTarget, () => bench("after"));
  $("btn-gov-tick").onclick = (e) => act(e.currentTarget, govTick);
  $("btn-gov-auto").onclick = (e) => {
    const btn = e.currentTarget;
    if (S.govTimer) {
      clearInterval(S.govTimer); S.govTimer = null;
      btn.textContent = "Auto Loop"; btn.classList.remove("danger"); btn.classList.add("primary");
      log("governor auto-loop dihentikan", "warn");
      return;
    }
    btn.textContent = "Hentikan Loop"; btn.classList.remove("primary"); btn.classList.add("danger");
    log("governor auto-loop aktif (tiap 4 detik)", "hi");
    govTick().catch((err) => log(err.message, "err"));
    S.govTimer = setInterval(() => govTick().catch((err) => log(err.message, "err")), 4000);
  };
  $("btn-plan-toggle").onclick = () => {
    S.planOpen = !S.planOpen;
    document.querySelectorAll(".step").forEach((n) => {
      n.classList.toggle("open", S.planOpen);
      S.planOpen ? S.expanded.add(n.dataset.id) : S.expanded.delete(n.dataset.id);
    });
    $("btn-plan-toggle").textContent = S.planOpen ? "Lipat semua" : "Buka semua";
  };
  $("btn-clear-log").onclick = () => { $("log").innerHTML = ""; };
  $("opt-risk").onchange = () => { if (S.plan) makePlan(false).catch((e) => log(e.message, "err")); };
  $("opt-pack").onchange = () => { if (S.plan) makePlan(false).catch((e) => log(e.message, "err")); };
  window.addEventListener("resize", () => { drawGauge(); drawChart(); });
}

/* ------------------------------------------------------------------ boot */
(async function boot() {
  wire();
  drawGauge(); drawChart();
  log("CRVX TurboFrame Control Panel siap", "hi");
  await load(true);
  log("engine tersambung. Pilih mode FPS lalu tekan TERAPKAN.", "info");
})();
})();
