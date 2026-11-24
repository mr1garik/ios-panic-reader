/* iOS Panic Reader — новый интерфейс. Все данные и переводы приходят из Python (webui.Backend). */
"use strict";

// Связь с Python: в программе — pywebview, в тестах — HTTP (tools/webui_dev.py)
const api = new Proxy({}, {
  get: (_, m) => (...a) => window.pywebview && window.pywebview.api
    ? window.pywebview.api[m](...a)
    : fetch("/api/" + m, { method: "POST", body: JSON.stringify(a) }).then(r => r.json()),
});

const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let INFO = null, T = {}, VIEW = "phone", LAST_V = -1, BUSY = false, LAST_STATE = null;
const STATE = { logQ: "", onlyPanic: false, part: null, logSel: null, histQ: "", histSel: null,
  kbQ: "", kbCat: "Все", kbScope: "base_logs", kbModel: "", kbSel: null, logTab: "explain" };

// ---------- значки (свои, простые линии) ----------
const I = {
  phone: '<path d="M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M11 18h2"/>',
  parts: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>',
  logs: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h7M9 8h3"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5M12 7v5l3 2"/>',
  kb: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  theme: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  warn: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  face: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M9 10v1M15 10v1M10 15a3 3 0 0 0 4 0"/>',
  bat: '<rect x="2" y="7" width="18" height="10" rx="2"/><path d="M22 11v2M5 10h8v4H5z"/>',
  file: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/>',
  folder: '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  clip: '<rect x="8" y="3" width="8" height="4" rx="1"/><path d="M8 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-2"/>',
  pdf: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 13h6M9 17h4"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3 17.8V21h3.2l6.3-6.3a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  bug: '<path d="M8 8a4 4 0 0 1 8 0v1H8z"/><rect x="7" y="9" width="10" height="11" rx="5"/><path d="M12 12v8M3 13h4M17 13h4M4 7l3 2M20 7l-3 2M4 20l3-2M20 20l-3-2"/>',
  pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
};
const icon = (k, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${I[k] || ""}</svg>`;

// ---------- запуск ----------
async function boot() {
  INFO = await api.app_info();
  T = INFO.t;
  applyTheme();
  document.documentElement.lang = INFO.lang;
  $("#ver").textContent = "v" + INFO.version;
  $("#btn-theme").innerHTML = icon("theme");
  $("#btn-about").innerHTML = icon("info");
  $("#btn-lang").textContent = INFO.lang.toUpperCase();
  $("#btn-theme").title = T.theme; $("#btn-about").title = T.about; $("#btn-lang").title = T.lang;
  // масштаб, сохранённый на большом экране, на маленьком уменьшается, чтобы всё помещалось
  let z0 = INFO.zoom || 1;
  while (z0 > ZOOMS[0] && window.innerWidth / z0 < 900) z0 = ZOOMS[Math.max(0, ZOOMS.findIndex(x => x >= z0) - 1)];
  setZoom(z0, false);
  const nav = $("#nav");
  nav.innerHTML = ["phone", "parts", "logs", "history", "kb"].map((k, i) =>
    `<button class="nav-item" data-view="${k}" title="${esc(T[k])} (${INFO.mod}+${i + 1})">${icon(k)}<span>${esc(T[k])}</span></button>`).join("");
  nav.onclick = e => { const b = e.target.closest(".nav-item"); if (b) show(b.dataset.view); };
  $("#btn-theme").onclick = e => menu(e.currentTarget, Object.entries(INFO.themes).map(([k, v]) => [v, k === INFO.theme, () => setTheme(k)]));
  $("#btn-lang").onclick = e => menu(e.currentTarget, Object.entries(INFO.langs).map(([k, v]) => [v, k === INFO.lang, () => setLang(k)]));
  $("#btn-about").onclick = about;
  $("#btn-settings").innerHTML = icon("gear"); $("#btn-settings").title = T.settings; $("#btn-settings").onclick = settingsDialog;
  $("#btn-bug").innerHTML = icon("bug"); $("#btn-bug").title = T.bug; $("#btn-bug").onclick = bugDialog;
  $("#zoom-in").onclick = () => zoomStep(1);
  $("#zoom-out").onclick = () => zoomStep(-1);
  document.addEventListener("keydown", keys);
  document.addEventListener("click", e => { if (!e.target.closest("#menu") && !e.target.closest("#btn-theme,#btn-lang")) $("#menu").hidden = true; });
  document.addEventListener("dragover", e => e.preventDefault());
  document.addEventListener("drop", drop);
  show("phone");
  setTimeout(() => { $("#splash").classList.add("hide"); $("#app").hidden = false; }, window.SPLASH_MS ?? 900);
  setTimeout(() => $("#splash").remove(), (window.SPLASH_MS ?? 900) + 600);
  setInterval(poll, 500);
}

function applyTheme() {
  const r = document.documentElement.style;
  for (const [k, v] of Object.entries(INFO.palette)) r.setProperty("--c-" + k, v);
  if (!INFO.palette.accent2) r.setProperty("--c-accent2", INFO.palette.blue);
  document.body.classList.toggle("dark", INFO.dark);
  document.body.classList.toggle("light", !INFO.dark);
}

const ZOOMS = [0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6];
// Высота окна с учётом масштаба: при CSS-zoom «100vh» растягивается в zoom раз и низ уходит за край
// (так в WebKit на Mac и в Chromium на Windows), поэтому высоту считаем сами.
function fitHeight() {
  const z = INFO?.zoom || 1, w = window.innerWidth / z, h = window.innerHeight / z;
  document.documentElement.style.setProperty("--vh", h + "px");
  const b = document.body.classList;
  b.toggle("w-narrow", w <= 1100); b.toggle("w-compact", w <= 980); b.toggle("w-tiny", w <= 560); b.toggle("h-short", h < 820);
}
window.addEventListener("resize", fitHeight);

function setZoom(z, save = true) {
  document.body.style.zoom = z;
  INFO.zoom = z;
  fitHeight();
  $("#zoom-val").textContent = Math.round(z * 100) + "%";
  if (save) api.set_setting("zoom", z);
}
function zoomStep(d) {
  let i = ZOOMS.findIndex(z => Math.abs(z - INFO.zoom) < 0.01); if (i < 0) i = 2;
  const z = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, i + d))];
  // крупнее — только если окно позволяет (ширина страницы с учётом масштаба)
  if (d > 0 && window.innerWidth / z < 900) return toast("info", T.zoom + ": " + Math.round(INFO.zoom * 100) + "%");
  setZoom(z);
}
function keys(e) {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && /^[1-5]$/.test(e.key)) { e.preventDefault(); show(["phone", "parts", "logs", "history", "kb"][+e.key - 1]); }
  else if (mod && (e.key === "=" || e.key === "+")) { e.preventDefault(); zoomStep(1); }
  else if (mod && e.key === "-") { e.preventDefault(); zoomStep(-1); }
  else if (mod && e.key === "0") { e.preventDefault(); setZoom(1); }
  else if (mod && e.key.toLowerCase() === "f") { e.preventDefault(); show("kb"); setTimeout(() => $("#kb-q")?.focus(), 50); }
  else if (e.key === "Escape") { closeModal(); $("#menu").hidden = true; }
}
async function setTheme(k) { await api.set_setting("theme", k); INFO = await api.app_info(); T = INFO.t; applyTheme(); render(); }
async function setLang(k) {
  if (k === INFO.lang) return;
  await api.set_setting("lang", k);
  confirmBox(T.lang, T.restart_q, T.restart, () => api.restart());
}

// ---------- опрос Python ----------
async function poll() {
  if (BUSY) return;
  BUSY = true;
  try {
    const p = await api.poll();
    for (const n of p.notices) toast(n.kind, n.text);
    if (p.update_info && !UPD_SHOWN && !p.update) { UPD_SHOWN = true; updateDialog(p.update_info); }
    if (p.update) updateProgress(p.update);
    // подключили телефон: «Доверять», снятие логов, результат — сразу на экран телефона (как в прежнем окне)
    if (p.state !== LAST_STATE) {
      const prev = LAST_STATE; LAST_STATE = p.state;
      if (prev !== null && ["trust", "unlock", "reading", "result"].includes(p.state) && VIEW !== "phone") show("phone");
    }
    if (p.v !== LAST_V) { LAST_V = p.v; await render(); }
  } catch (e) { /* окно закрывается */ }
  BUSY = false;
}

// ---------- навигация ----------
function show(v) {
  VIEW = v;
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "view-" + v));
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("on", b.dataset.view === v));
  render();
}
async function render() {
  const f = { phone: renderPhone, parts: renderParts, logs: renderLogs, history: renderHistory, kb: renderKb }[VIEW];
  if (f) await f();
}

// ---------- экран «Телефон» ----------
async function renderPhone() {
  const el = $("#view-phone");
  const d = await api.phone();
  if (d.state !== "result") {
    const map = { wait: ["plug", T.wait_t, T.wait_s], start: ["plug", T.wait_t, T.wait_s], trust: ["phone", T.trust_t, T.trust_s],
      unlock: ["lock", T.unlock_t, T.unlock_s], reading: [null, T.reading_t, T.reading_s], denied: ["warn", T.denied_t, T.denied_s],
      error: ["warn", T.error_t, d.error], nodriver: ["warn", T.nodriver_t, T.nodriver_s] };
    const [ic, t, s] = map[d.state] || map.wait;
    const err = ["error", "denied", "nodriver"].includes(d.state);
    el.innerHTML = `<div class="hero ${err ? "err" : ""}"><div>
      ${ic ? `<div class="ic">${icon(ic)}</div>` : `<div class="spinner" style="margin:0 auto 22px"></div>`}
      <h1>${esc(t)}</h1><p>${esc(s || "")}</p>
      <div class="row" style="justify-content:center">
        ${d.state === "error" ? `<button class="btn primary" data-a="again">${esc(T.again)}</button>` : ""}
        <button class="btn" data-a="open_files">${icon("file")}${esc(T.open_file)}</button>
        <button class="btn" data-a="open_folder">${icon("folder")}${esc(T.open_folder)}</button>
        <button class="btn" data-a="paste">${icon("clip")}${esc(T.paste)}</button>
      </div></div></div>`;
    return bindActions(el);
  }
  const chipIc = { model: "phone", ios: "info", port: "bolt", bio: "face", battery: "bat" };
  const stats = d.stats.map(s => `<div class="stat"><div class="k">${esc(T[s.key])}</div><div class="v ${s.level ? "t-" + s.level : ""}">${esc(s.value)}</div></div>`).join("");
  const left = `
    <div class="card glow"><div class="dev-name">${esc(d.dev.model)}</div><div class="muted small">${esc(d.dev.sub)}</div>
      <div class="stats">${stats}</div>${d.dev.imei ? `<div class="muted small" style="margin-top:10px">IMEI ${esc(d.dev.imei)}</div>` : ""}</div>
    ${d.prev ? `<div class="card"><div class="cap" style="margin-top:0">${esc(T.prev)}</div><b>${esc(d.prev.date)}</b>
      <div class="t-${d.prev.level}">${esc(d.prev.text)}</div><div class="muted small">${esc(d.prev.battery)}</div></div>` : ""}
    <div class="side-btns">
      ${d.has_dev ? `<button class="btn" data-a="mark_repair">${icon("wrench")}${esc(T.mark_repair)}</button>` : ""}
      ${INFO.has_device ? `<button class="btn" data-a="again">${icon("plug")}${esc(T.other_phone)}</button>` : ""}
      <button class="btn" data-a="open_files">${icon("file")}${esc(T.open_file)}</button>
      <button class="btn" data-a="paste">${icon("clip")}${esc(T.paste)}</button>
    </div>`;
  let right = `<div class="chips">${d.chips.map(c => `<span class="chip">${icon(chipIc[c.kind] || "info")}${esc(c.text)}</span>`).join("")}</div>`;
  if (d.repair) right += `<div class="card lvl-blue"><div class="section-title"><b>${esc(d.repair.title)}</b>
      <button class="btn small" data-a="toggle_after_repair">${esc(d.repair.after ? T.show_all : T.only_after)}</button></div>
      <div class="t-${d.repair.level}" style="margin-top:6px">${esc(d.repair.text)}</div></div>`;
  if (d.probability.length) {
    right += `<div class="card"><div class="section-title"><h2>${esc(T.probability)}</h2><span class="muted small">${esc(T.probability_hint)}</span></div>
      <div class="prob">${d.probability.map(p => `<div class="prob-row ${p.pct >= 50 ? "hi" : ""}" data-toggle>
        <div class="name">${esc(p.title)}</div><div class="pct">${p.pct}%</div><div class="bar"><i style="width:${p.pct}%"></i></div>
        <div class="why">${esc(p.why)}</div></div>`).join("")}</div></div>`;
  }
  if (!d.problems.length) {
    right += `<div class="card lvl-green"><div class="cap t-green" style="margin-top:0">${esc(T.found_none)}</div>
      <h1>${esc(T.phone_ok)}</h1><div>${esc(d.ok_text)}</div></div>`;
  }
  d.problems.forEach((p, i) => { right += problemCard(p, i + 1, d.problems.length); });
  if (d.groups.length) {
    right += `<div class="card"><h2>${esc(T.groups)}</h2><div class="groups">${d.groups.map(g =>
      `<div class="group" data-group="${esc(g.title)}" title="${esc(T.show_logs)}"><span class="dot ${g.level}"></span><span class="t" title="${esc(g.title)}">${esc(g.title)}</span><span class="n">${g.n}/${g.total}</span></div>`).join("")}</div></div>`;
  }
  if (d.chart) right += chart(d.chart);
  if (d.other.length) right += `<div class="card"><h2>${esc(T.other)}</h2>${d.other.map(([l, t]) => `<div class="row" style="flex-wrap:nowrap;align-items:flex-start;margin:4px 0"><span class="dot ${l}" style="margin-top:7px"></span><span>${esc(t)}</span></div>`).join("")}</div>`;
  right += `<div class="row">
      <button class="btn primary" data-a="save_pdf">${icon("pdf")}${esc(T.pdf)}</button>
      <button class="btn" data-view="logs">${esc(T.show_logs)}</button>
      <button class="btn" data-view="parts">${esc(T.parts)}</button>
      <button class="btn" data-a="save_txt">${esc(T.txt)}</button>
      ${d.dir ? `<button class="btn" data-a="open_dir">${icon("folder")}${esc(T.folder)}</button>` : ""}
    </div>
    ${d.connected ? `<div class="row"><button class="btn danger" data-a="erase">${icon("trash")}${esc(T.erase)}</button><span class="muted small">${esc(T.erase_note)}</span></div>` : ""}`;
  el.innerHTML = `<div class="result"><div class="col">${left}</div><div class="col">${right}</div></div>`;
  el.querySelectorAll("[data-toggle]").forEach(r => r.onclick = () => r.classList.toggle("open"));
  el.querySelectorAll("[data-group]").forEach(g => g.onclick = () => {      // группа → её логи
    STATE.logQ = g.dataset.group; STATE.part = null; STATE.logSel = null; show("logs");
    const q = $("#logs-q"); if (q) q.value = STATE.logQ; });
  bindActions(el);
}

function problemCard(p, num, total) {
  const lvl = p.level === "red" ? T.important : T.not_urgent;
  return `<div class="card lvl-${p.level}">
    <div class="problem-head"><h2>${total > 1 ? num + ". " : ""}${esc(p.title)}</h2><span class="badge-lvl ${p.level}">${esc(lvl)}</span></div>
    <div class="cap">${esc(T.how)}</div><div>${esc(p.how)}</div>
    <div class="cap">${esc(T.why)}</div><div>${esc(p.why)}</div>
    <div class="cap">${esc(T.fix)}</div><ol class="steps">${p.fix.map(f => `<li><span>${esc(f)}</span></li>`).join("")}</ol>
    ${p.board && p.board.zone !== "none" ? board(p.board) : ""}
    <div class="problem-foot"><span class="muted small">${esc(p.note)}</span>
      ${p.count ? `<button class="link" data-part="${esc(p.part)}">${esc(T.part_logs)}</button>` : ""}</div></div>`;
}

// Простая схема телефона: зона, где искать (не схема платы конкретной модели)
function board(b) {
  const zones = {
    top: '<rect class="zone" x="14" y="12" width="64" height="26" rx="6"/>',
    bottom: '<rect class="zone" x="14" y="112" width="64" height="26" rx="6"/>',
    battery: '<rect class="zone" x="40" y="44" width="38" height="62" rx="5"/>',
    board: '<path class="zone" d="M14 40h24v66H14z"/>',
    screen: '<rect class="zone" x="10" y="8" width="72" height="134" rx="12"/>',
  };
  return `<div class="board"><svg viewBox="0 0 92 150">
    <rect x="6" y="4" width="80" height="142" rx="16" fill="none" stroke="var(--c-border)" stroke-width="2"/>
    <rect x="14" y="40" width="24" height="66" rx="4" fill="var(--c-gray_bg)" stroke="var(--c-line)"/>
    <rect x="40" y="44" width="38" height="62" rx="5" fill="var(--c-gray_bg)" stroke="var(--c-line)"/>
    ${zones[b.zone] || ""}</svg>
    <div><div class="cap" style="margin-top:0">${esc(T.where)}</div><b>${esc(b.title)}</b><div class="small">${esc(b.text)}</div>
    <div class="muted small" style="margin-top:4px">${esc(T.board_hint)}</div></div></div>`;
}

function chart(c) {
  const max = Math.max(1, ...c.days.map(d => d[1]));
  return `<div class="card"><h2>${esc(c.title)}</h2><div class="chart">${c.days.map(([day, n]) =>
    `<div class="b ${n ? "" : "z"} ${day === c.repair ? "rep" : ""}" style="height:${n ? Math.max(6, n / max * 100) : 2}%" title="${esc(day)}: ${n}">${n ? `<span>${n}</span>` : ""}</div>`).join("")}</div>
    <div class="chart-axis"><span>${esc(c.days[0][0])}</span><span>${esc(c.days[c.days.length - 1][0])}</span></div></div>`;
}

// ---------- кнопки-действия ----------
function bindActions(el) {
  el.querySelectorAll("[data-a]").forEach(b => b.onclick = () => action(b.dataset.a, b));
  el.querySelectorAll("[data-view]").forEach(b => b.onclick = () => show(b.dataset.view));
  el.querySelectorAll("[data-part]").forEach(b => b.onclick = () => { STATE.part = b.dataset.part; STATE.logSel = null; show("logs"); });
}
async function action(a) {
  if (a === "mark_repair") return repairDialog();
  if (a === "erase") return eraseDialog();
  if (a === "paste") return pasteDialog();
  await api[a]();
  LAST_V = -1;
}

// ---------- экран «Детали» ----------
async function renderParts() {
  const d = await api.parts();
  const st = { green: T.st_green, orange: T.st_orange, red: T.st_red };
  $("#view-parts").innerHTML = `<h1>${esc(d.title)}</h1>
    <div class="counts">${[["green", T.cnt_green], ["orange", T.cnt_orange], ["red", T.cnt_red]].map(([l, t]) =>
      `<div class="card lvl-${l}"><b class="t-${l}">${d.counts[l]}</b>${esc(t)}</div>`).join("")}</div>
    <div class="card lvl-blue" style="margin-bottom:14px"><b>${esc(d.original_t)}</b><div class="small">${esc(d.original)}</div></div>
    <table class="parts"><thead><tr><th>${esc(T.part)}</th><th>${esc(T.data)}</th><th>${esc(T.fails)}</th><th>${esc(T.status)}</th></tr></thead>
    <tbody>${d.rows.map(r => `<tr class="${r.level}"><td>${esc(r.name)}</td><td class="muted">${esc(r.data)}</td>
      <td class="${r.level !== "green" ? "t-" + r.level : ""}">${esc(r.fails)}</td>
      <td class="t-${r.level}"><span class="dot ${r.level}"></span> ${esc(st[r.level])}</td></tr>`).join("")}</tbody></table>`;
}

// ---------- экран «Все логи» ----------
async function renderLogs() {
  const el = $("#view-logs");
  el.classList.add("split");
  if (!$("#logs-q", el)) {
    el.innerHTML = `<div class="toolbar">
        <input type="search" id="logs-q" placeholder="${esc(T.search)}">
        <label class="chk"><input type="checkbox" id="logs-panic"> ${esc(T.only_panics)}</label>
        <span id="logs-chip"></span>
        <span style="flex:1"></span>
        <button class="btn small" data-a="open_folder">${icon("folder")}${esc(T.open_folder)}</button>
        <button class="btn small" data-a="open_files">${icon("file")}${esc(T.open_file)}</button>
      </div>
      <div class="split-body"><div class="card panel" style="padding:8px"><div class="list" id="logs-list"></div></div>
      <div class="card panel" id="logs-detail"></div></div>`;
    $("#logs-q").value = STATE.logQ;
    $("#logs-q").oninput = e => { STATE.logQ = e.target.value; renderLogs(); };
    $("#logs-panic").onchange = e => { STATE.onlyPanic = e.target.checked; renderLogs(); };
    bindActions(el);
  }
  const d = await api.logs_list(STATE.logQ, STATE.onlyPanic, STATE.part);
  $("#logs-chip").innerHTML = d.part_title ? `<button class="btn small primary" id="clear-part">✕ ${esc(d.part_title)}</button>` : "";
  if (d.part_title) $("#clear-part").onclick = () => { STATE.part = null; renderLogs(); };
  const list = $("#logs-list");
  if (!d.items.length) { list.innerHTML = `<div class="empty">${esc(T.no_logs)}</div>`; $("#logs-detail").innerHTML = ""; return; }
  if (STATE.logSel === null || !d.items.some(x => x.id === STATE.logSel)) STATE.logSel = d.items[0].id;
  list.innerHTML = d.items.map(x => `<div class="item ${x.id === STATE.logSel ? "sel" : ""}" data-id="${x.id}">
      <span class="dot ${x.level}"></span><span class="t" title="${esc(x.title)}">${esc(x.title)}</span><span class="s">${esc(x.date)}</span>
      <span class="sub">${esc(x.kind)}</span></div>`).join("");
  list.onclick = e => { const it = e.target.closest(".item"); if (it) { STATE.logSel = +it.dataset.id; renderLogs(); } };
  showLog(STATE.logSel);
}
async function showLog(id) {
  const d = await api.log_detail(id);
  const box = $("#logs-detail");
  box.innerHTML = `<div class="tabs"><button class="tab ${STATE.logTab === "explain" ? "on" : ""}" data-t="explain">${esc(T.fix)}</button>
      <button class="tab ${STATE.logTab === "raw" ? "on" : ""}" data-t="raw">${esc(T.raw)}</button>
      <span style="flex:1"></span><button class="btn small" id="add-entry">${icon("pen")}${esc(T.add_entry)}</button>
      <button class="btn small" id="suggest">${esc(T.suggest)}</button></div>
    <div id="log-body"></div>`;
  box.querySelectorAll(".tab").forEach(t => t.onclick = () => { STATE.logTab = t.dataset.t; showLog(id); });
  $("#suggest").onclick = () => suggestDialog(id, d.suggest);
  $("#add-entry").onclick = () => entryDialog("log:" + id);
  $("#log-body").innerHTML = STATE.logTab === "raw" ? `<pre class="raw">${highlight(d.raw, d.highlights)}</pre>` : rich(d.parts);
}
function rich(parts) {
  return `<div class="rich">${parts.map(([t, k]) => {
    const s = esc(t.replace(/\n$/, ""));
    if (!s.trim()) return "";
    if (k === "cap") return `<div class="cap">${s}</div>`;
    if (k === "h1") return `<div class="h1">${s}</div>`;
    if (k === "mono") return `<div class="mono">${s}</div>`;
    if (k === "small") return `<p class="small muted">${s}</p>`;
    if (k === "red") return `<p class="red">${s}</p>`;
    return `<p>${s}</p>`;
  }).join("")}</div>`;
}
// Подсветка исходного лога: ключи и значения JSON, найденные строки
function highlight(raw, marks) {
  let h = esc(raw);
  h = h.replace(/(&quot;[\w.\-]+&quot;\s*:\s*)(-?\d+(?:\.\d+)?)(?=\s*[,}\n])/g, '$1<span class="n">$2</span>')
       .replace(/(&quot;)([\w.\-]+)(&quot;)(\s*:)/g, '<span class="k">$1$2$3</span>$4');
  for (const m of marks || []) {
    const e = esc(m).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (e.length < 3) continue;
    try { h = h.replace(new RegExp("(" + e + ")(?![^<]*>)", "g"), "<mark>$1</mark>"); } catch (_) { /* пропускаем */ }
  }
  return h;
}

// ---------- экран «История» ----------
async function renderHistory() {
  const el = $("#view-history");
  el.classList.add("split");
  if (!$("#hist-q", el)) {
    el.innerHTML = `<div class="toolbar"><h1 style="margin:0 12px 0 0">${esc(T.phones_seen)}</h1>
        <input type="search" id="hist-q" placeholder="${esc(T.search)}">
        <span style="flex:1"></span>
        <span class="row" style="flex-wrap:nowrap"><label class="muted small" for="workshop">${esc(T.workshop)}</label>
          <input type="text" id="workshop" style="width:180px"><button class="btn small" id="ws-save">${esc(T.save)}</button></span></div>
      <div class="split-body"><div class="card panel" style="padding:8px"><div class="list" id="hist-list"></div></div>
      <div class="card panel" id="hist-detail"></div></div>`;
    $("#hist-q").oninput = e => { STATE.histQ = e.target.value; renderHistory(); };
    $("#workshop").value = INFO.workshop;
    $("#ws-save").onclick = async () => { await api.set_workshop($("#workshop").value); toast("ok", T.save + " ✓"); };
  }
  const rows = await api.history_list(STATE.histQ);
  const list = $("#hist-list");
  if (!rows.length) { list.innerHTML = `<div class="empty">—</div>`; $("#hist-detail").innerHTML = `<div class="empty">${esc(T.pick_phone)}</div>`; return; }
  if (!rows.some(r => r.key === STATE.histSel)) STATE.histSel = rows[0].key;
  list.innerHTML = rows.map(r => `<div class="item ${r.key === STATE.histSel ? "sel" : ""}" data-k="${esc(r.key)}">
      <span class="dot ${r.level}"></span><span class="t">${esc(r.model)} <span class="muted small">${esc(r.serial)}</span></span><span class="s">${esc(r.date)}</span>
      <span class="sub t-${r.level}">${esc(r.result)}</span></div>`).join("");
  list.onclick = e => { const it = e.target.closest(".item"); if (it) { STATE.histSel = it.dataset.k; renderHistory(); } };
  const p = await api.phone_history(STATE.histSel);
  if (!p) return;
  $("#hist-detail").innerHTML = `<h1>${esc(p.model)}</h1><div class="muted small">${esc(p.sub)}</div>
    <div class="cap">${esc(T.note)}</div><textarea id="note" rows="3">${esc(p.note)}</textarea>
    <div class="row" style="margin-top:6px"><button class="btn small" id="note-save">${esc(T.save_note)}</button></div>
    ${p.repairs.length ? `<div class="cap">${esc(T.repairs)}</div>${p.repairs.map(r => `<div>${esc(r.date)} — ${esc(r.note)}</div>`).join("")}` : ""}
    <div class="cap">${esc(T.visits)} (${p.visits.length})</div>
    ${p.visits.map(v => `<div class="row" style="flex-wrap:nowrap;align-items:flex-start;margin:6px 0"><span class="dot ${v.level}" style="margin-top:7px"></span>
      <div><b>${esc(v.date)}</b><div class="muted small">${esc(v.text)}</div></div></div>`).join("")}
    <div class="row" style="margin-top:14px">
      ${p.has_logs ? `<button class="btn small" id="h-open">${esc(T.open_logs)}</button><button class="btn small" id="h-txt">${esc(T.txt)}</button>` : ""}
      <button class="btn small danger" id="h-del">${icon("trash")}${esc(T.delete_phone)}</button></div>`;
  $("#note-save").onclick = async () => { await api.set_note(p.key, $("#note").value); toast("ok", T.save_note + " ✓"); };
  if (p.has_logs) {
    $("#h-open").onclick = async () => { await api.open_history_logs(p.key); show("phone"); };
    $("#h-txt").onclick = () => api.history_report(p.key);
  }
  $("#h-del").onclick = () => confirmBox(T.delete_phone, p.model + " · " + p.sub, T.delete_phone, async () => { await api.delete_phone(p.key); renderHistory(); });
}

// ---------- экран «Поиск ошибок» ----------
let KB_TIMER = null;
async function renderKb() {
  const el = $("#view-kb");
  el.classList.add("split");
  if (!$("#kb-q", el)) {
    el.innerHTML = `<div style="display:grid;gap:10px">
        <div class="toolbar"><input type="search" id="kb-q" placeholder="${esc(T.kb)}" style="max-width:none;font-size:16px;padding:11px 14px">
          <button class="btn" data-a="paste">${icon("clip")}${esc(T.paste)}</button></div>
        <div class="muted small">${esc(T.kb_hint)}</div>
        <div class="toolbar">
          ${[["base", T.scope_base], ["base_logs", T.scope_logs], ["all", T.scope_all]].map(([v, t]) =>
            `<label class="chk"><input type="radio" name="scope" value="${v}" ${v === STATE.kbScope ? "checked" : ""}> ${esc(t)}</label>`).join("")}
          <span style="flex:1"></span><label class="muted small">${esc(T.model)}</label>
          <select id="kb-model"><option value="">${esc(T.all_models)}</option>${INFO.models.map(([n]) => `<option>${esc(n)}</option>`).join("")}</select>
        </div>
        <div class="chipbar" id="kb-cats">${INFO.categories.map(([k, t]) => `<button class="tab ${k === STATE.kbCat ? "on" : ""}" data-c="${esc(k)}">${esc(t)}</button>`).join("")}</div>
      </div>
      <div class="split-body"><div class="card panel" style="padding:8px"><div class="list" id="kb-list"></div></div>
      <div class="card panel" id="kb-detail"></div></div>`;
    $("#kb-q").oninput = e => { STATE.kbQ = e.target.value; clearTimeout(KB_TIMER); KB_TIMER = setTimeout(renderKb, 250); };
    el.querySelectorAll("input[name=scope]").forEach(r => r.onchange = () => { STATE.kbScope = r.value; renderKb(); });
    $("#kb-model").onchange = e => { STATE.kbModel = e.target.value; STATE.kbSel = null; renderKb(); };
    $("#kb-cats").onclick = e => { const b = e.target.closest(".tab"); if (!b) return; STATE.kbCat = b.dataset.c;
      $("#kb-cats").querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x === b)); renderKb(); };
    bindActions(el);
  }
  const groups = await api.kb(STATE.kbQ, STATE.kbCat, STATE.kbScope, STATE.kbModel);
  const ids = groups.flatMap(g => g.items.map(i => i.id));
  if (!ids.includes(STATE.kbSel)) STATE.kbSel = ids[0] || null;
  $("#kb-list").innerHTML = groups.map(g => `<div class="group-title">${esc(g.title)}</div>` + g.items.map(i =>
    `<div class="item ${i.id === STATE.kbSel ? "sel" : ""}" data-id="${esc(i.id)}"><span class="dot ${i.level || "blue"}"></span>
      <span class="t" title="${esc(i.title)}">${esc(i.title)}</span><span class="s">${esc(i.where)}</span></div>`).join("")).join("");
  $("#kb-list").onclick = e => { const it = e.target.closest(".item"); if (it) { STATE.kbSel = it.dataset.id; renderKb(); } };
  if (!STATE.kbSel) { $("#kb-detail").innerHTML = `<div class="empty">${esc(T.nothing)}</div>`; return; }
  const it = await api.kb_item(STATE.kbSel);
  $("#kb-detail").innerHTML = (it.editable ? `<div class="row" style="justify-content:flex-end;margin-bottom:6px">
      <button class="btn small" id="kb-edit">${icon("pen")}${esc(it.user ? T.edit_entry : T.add_entry)}</button>
      ${it.user ? `<button class="btn small danger" id="kb-del">${icon("trash")}${esc(T.delete)}</button>` : ""}</div>` : "") + rich(it.parts);
  if (it.editable) $("#kb-edit").onclick = () => entryDialog(STATE.kbSel);
  if (it.user) $("#kb-del").onclick = () => confirmBox(T.delete, it.entry_id, T.delete, async () => {
    await api.delete_entry(it.entry_id); STATE.kbSel = null; renderKb(); });
}

// ---------- окна ----------
function modal(html, wide = false) {
  const m = $("#modal"), box = $(".modal-box", m);
  box.className = "modal-box" + (wide ? " wide" : "");
  box.innerHTML = html;
  m.hidden = false;
  m.onclick = e => { if (e.target === m && !m.dataset.lock) closeModal(); };
  return box;
}
function closeModal() { const m = $("#modal"); if (!m.dataset.lock) m.hidden = true; }
function confirmBox(title, text, ok, fn) {
  const b = modal(`<h2>${esc(title)}</h2><div class="muted">${esc(text)}</div>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button><button class="btn primary" id="m-ok">${esc(ok)}</button></div>`);
  $("#m-no", b).onclick = closeModal;
  $("#m-ok", b).onclick = () => { closeModal(); fn(); };
}
function repairDialog() {
  const b = modal(`<h2>${esc(T.repair_title)}</h2><div class="muted">${esc(T.repair_desc)}</div>
    <div class="cap">${esc(T.repair_what)}</div><input type="text" id="r-note" style="width:100%">
    ${INFO.has_device ? `<label class="chk" style="margin-top:12px"><input type="checkbox" id="r-erase"> ${esc(T.repair_erase)}</label>` : ""}
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button><button class="btn primary" id="m-ok">${esc(T.mark)}</button></div>`);
  $("#r-note", b).focus();
  $("#m-no", b).onclick = closeModal;
  $("#m-ok", b).onclick = async () => { await api.mark_repair($("#r-note", b).value, !!$("#r-erase", b)?.checked); closeModal(); LAST_V = -1; };
}
async function eraseDialog() {
  const n = await api.connected_count();
  const b = modal(`<h2>${esc(T.erase_title)}</h2><div class="muted">${esc(T.erase_desc)}</div>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button>
    ${n > 1 ? `<button class="btn" id="m-all">${esc(T.erase_all.replace("{0}", n))}</button>` : ""}
    <button class="btn primary" id="m-ok">${esc(T.erase_this)}</button></div>`);
  if (n > 1) $("#m-all", b).onclick = () => { api.erase_phone(true); closeModal(); };
  $("#m-no", b).onclick = closeModal;
  $("#m-ok", b).onclick = () => { api.erase_phone(false); closeModal(); };
}
function pasteDialog() {
  const b = modal(`<h2>${esc(T.paste_title)}</h2><div class="muted">${esc(T.paste_desc)}</div>
    <textarea id="p-text" rows="12" style="margin-top:12px;font-family:var(--mono);font-size:12.5px"></textarea>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button><button class="btn primary" id="m-ok">${esc(T.analyze)}</button></div>`, true);
  const ta = $("#p-text", b);
  ta.focus();
  if (navigator.clipboard && navigator.clipboard.readText) navigator.clipboard.readText().then(t => { if (t && !ta.value) ta.value = t; }).catch(() => {});
  $("#m-no", b).onclick = closeModal;
  $("#m-ok", b).onclick = async () => { if (await api.paste(ta.value)) { closeModal(); show("phone"); } };
}
function suggestDialog(id, body) {
  const b = modal(`<h2>${esc(T.suggest)}</h2><div class="muted small">${esc(T.suggest_desc)}</div>
    <textarea id="s-text" rows="14" style="margin-top:12px;font-family:var(--mono);font-size:12.5px"></textarea>
    <div class="modal-foot"><button class="btn" id="m-copy">${esc(T.copy)}</button><button class="btn primary" id="m-ok">${esc(T.open_github)}</button></div>`, true);
  const ta = $("#s-text", b);
  ta.value = body;
  $("#m-copy", b).onclick = () => copyText(ta.value);
  $("#m-ok", b).onclick = () => { api.suggest_send(id, ta.value); closeModal(); };
}
function about() {
  const b = modal(`<div class="row" style="flex-wrap:nowrap"><img src="icon.png" width="56" height="56" alt=""><div><h1>iOS Panic Reader</h1><div class="muted">v${esc(INFO.version)}</div></div></div>
    <p class="small">${esc(T.data_dir)}<br><button class="link" id="a-dir">${esc(INFO.data_dir)}</button></p>
    <label class="chk"><input type="checkbox" id="a-auto" ${INFO.auto_update ? "checked" : ""}> ${esc(T.auto_update)}</label>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="a-check">${esc(T.check_updates)}</button>
      <button class="btn" id="a-all">${esc(T.all_versions)}</button><button class="btn" id="a-bug">${icon("bug")}${esc(T.bug)}</button></div>
    <hr><div class="cap" style="margin-top:0">${esc(T.other_projects)}</div><b>iActivator</b><div class="muted small">${esc(T.iact_desc)}</div>
    <div class="row" style="margin-top:8px"><button class="btn primary" id="a-iact">${esc(T.iact_dl)}</button><button class="btn" id="a-proj">${esc(T.project)}</button></div>
    <hr><div class="cap" style="margin-top:0">${esc(T.support)}</div>
    <div class="about-qr"><div><div class="muted small">${esc(T.support_desc)}</div><b>${esc(INFO.donate.network)}</b>
      <div class="addr" style="margin:6px 0">${esc(INFO.donate.address)}</div>
      <div class="row"><button class="btn small" id="a-copy">${esc(T.copy_addr)}</button><span id="a-copied" class="t-green small"></span></div>
      <div class="muted small" style="margin-top:6px">${esc(T.usdt_only)}</div></div>
      <img src="donate_qr.png" alt="QR"></div>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.close)}</button></div>`);
  $("#m-no", b).onclick = closeModal;
  $("#a-dir", b).onclick = () => api.open_path(INFO.data_dir);
  $("#a-auto", b).onchange = e => { INFO.auto_update = e.target.checked; api.set_setting("auto_update", e.target.checked); };
  $("#a-check", b).onclick = () => { UPD_SHOWN = false; api.check_updates(true); closeModal(); };
  $("#a-bug", b).onclick = () => { closeModal(); bugDialog(); };
  $("#a-all", b).onclick = () => api.open_url("https://github.com/mr1garik/ios-panic-reader/releases");
  $("#a-iact", b).onclick = () => api.open_url("https://github.com/mr1garik/iActivator/releases/latest");
  $("#a-proj", b).onclick = () => api.open_url("https://github.com/mr1garik/iActivator");
  $("#a-copy", b).onclick = () => { copyText(INFO.donate.address); $("#a-copied", b).textContent = T.copied; };
}

// ---------- настройки и перенос на другой компьютер ----------
function settingsDialog() {
  const opt = (list, cur) => list.map(([k, v]) => `<option value="${esc(k)}" ${k === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
  const b = modal(`<div class="row" style="flex-wrap:nowrap">${icon("gear", "hdr-ic")}<h2 style="margin:0">${esc(T.settings)}</h2></div>
    <div class="cap">${esc(T.s_look)}</div>
    <div class="row" style="gap:12px">
      <label class="small muted" style="flex:1 1 160px">${esc(T.theme)}<select id="st-theme" style="width:100%;margin-top:4px">${opt(Object.entries(INFO.themes), INFO.theme)}</select></label>
      <label class="small muted" style="flex:1 1 160px">${esc(T.lang)}<select id="st-lang" style="width:100%;margin-top:4px">${opt(Object.entries(INFO.langs), INFO.lang)}</select></label>
      <label class="small muted" style="flex:1 1 120px">${esc(T.zoom)}<select id="st-zoom" style="width:100%;margin-top:4px">${opt(ZOOMS.map(z => [String(z), Math.round(z * 100) + "%"]), String(INFO.zoom))}</select></label>
    </div>
    <div class="cap">${esc(T.workshop)}</div>
    <div class="row" style="flex-wrap:nowrap"><input type="text" id="st-ws" style="flex:1" value="${esc(INFO.workshop)}"><button class="btn small" id="st-ws-save">${esc(T.save)}</button></div>
    <div class="cap">${esc(T.s_updates)}</div>
    <label class="chk"><input type="checkbox" id="st-auto" ${INFO.auto_update ? "checked" : ""}> ${esc(T.auto_update)}</label>
    <hr><div class="cap" style="margin-top:0">${esc(T.s_transfer)}</div>
    <div class="muted small">${esc(T.s_transfer_desc)}</div>
    <label class="chk" style="margin-top:10px"><input type="checkbox" id="st-logs"> ${esc(T.s_with_logs)}</label>
    <div class="row" style="margin-top:10px">
      <button class="btn primary" id="st-export">${esc(T.s_export)}</button>
      <button class="btn" id="st-import">${esc(T.s_import)}</button>
      <button class="btn" id="st-dir">${icon("folder")}${esc(T.s_data)}</button></div>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.close)}</button></div>`);
  $("#m-no", b).onclick = closeModal;
  $("#st-theme", b).onchange = e => setTheme(e.target.value);
  $("#st-lang", b).onchange = e => { closeModal(); setLang(e.target.value); };
  $("#st-zoom", b).onchange = e => setZoom(+e.target.value);
  $("#st-ws-save", b).onclick = async () => { await api.set_workshop($("#st-ws", b).value); INFO.workshop = $("#st-ws", b).value; toast("ok", T.save + " ✓"); };
  $("#st-auto", b).onchange = e => { INFO.auto_update = e.target.checked; api.set_setting("auto_update", e.target.checked); };
  $("#st-dir", b).onclick = () => api.open_path(INFO.data_dir);
  $("#st-export", b).onclick = () => api.export_data($("#st-logs", b).checked);
  $("#st-import", b).onclick = async () => {
    const r = await api.import_data();
    if (!r) return;
    INFO = await api.app_info(); T = INFO.t; applyTheme(); setZoom(INFO.zoom || 1, false);
    closeModal(); LAST_V = -1;
    if (r.lang_changed) confirmBox(T.lang, T.restart_q, T.restart, () => api.restart());
  };
}

// ---------- сообщить об ошибке программы ----------
async function bugDialog() {
  const details = await api.bug_report();
  const b = modal(`<h2>${esc(T.bug_title)}</h2><div class="muted small">${esc(T.bug_desc)}</div>
    <div class="cap">${esc(T.bug_what)}</div><textarea id="b-what" rows="4"></textarea>
    <div class="cap">${esc(T.bug_details)}</div>
    <textarea id="b-det" rows="9" style="font-family:var(--mono);font-size:12px"></textarea>
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button><button class="btn" id="m-copy">${esc(T.copy)}</button>
      <button class="btn primary" id="m-ok">${esc(T.open_github)}</button></div>`, true);
  $("#b-det", b).value = details;
  $("#b-what", b).focus();
  $("#m-no", b).onclick = closeModal;
  $("#m-copy", b).onclick = () => { copyText($("#b-what", b).value + "\n\n" + $("#b-det", b).value); toast("ok", T.copy + " ✓"); };
  $("#m-ok", b).onclick = () => { api.bug_send($("#b-what", b).value, $("#b-det", b).value); closeModal(); };
}

// ---------- своё описание паники или ошибки ----------
async function entryDialog(source) {
  const f = await api.entry_form(source);
  const opt = (list, cur, empty) => (empty ? `<option value="">${esc(empty)}</option>` : "") +
    list.map(([k, v]) => `<option value="${esc(k)}" ${k === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
  const field = (id, label, val, rows = 0, hint = "") => `<div class="cap">${esc(label)}</div>` +
    (rows ? `<textarea id="${id}" rows="${rows}">${esc(val)}</textarea>` : `<input type="text" id="${id}" value="${esc(val)}" style="width:100%">`) +
    (hint ? `<div class="muted small">${esc(hint)}</div>` : "");
  const b = modal(`<h2>${esc(f.user ? T.edit_entry : T.entry_title)}</h2><div class="muted small">${esc(T.entry_desc)}</div>
    ${field("e-title", T.f_title, f.title)}
    <div class="row" style="flex-wrap:wrap;gap:12px">
      <div style="flex:1 1 220px"><div class="cap">${esc(T.f_part)}</div><select id="e-part" style="width:100%">${opt(f.parts, f.part, T.no_part)}</select></div>
      <div style="flex:1 1 220px"><div class="cap">${esc(T.f_cat)}</div><select id="e-cat" style="width:100%">${opt(f.cats, f.cat)}</select></div></div>
    ${field("e-pattern", T.f_pattern, f.pattern, 0, T.f_pattern_hint)}
    ${field("e-models", T.f_models, f.models)}
    ${field("e-symptoms", T.f_symptoms, f.symptoms, 2)}
    ${field("e-cause", T.f_cause, f.cause, 2)}
    ${field("e-fix", T.f_fix, f.fix, 3)}
    <div class="modal-foot"><button class="btn" id="m-no">${esc(T.cancel)}</button>
      <button class="btn" id="m-send">${esc(T.send_base)}</button><button class="btn primary" id="m-ok">${esc(T.save_local)}</button></div>`, true);
  $("#e-fix", b).focus();
  const read = () => ({ id: f.id, title: $("#e-title", b).value, part: $("#e-part", b).value, cat: $("#e-cat", b).value,
    pattern: $("#e-pattern", b).value, models: $("#e-models", b).value, symptoms: $("#e-symptoms", b).value,
    cause: $("#e-cause", b).value, fix: $("#e-fix", b).value });
  const save = async send => {
    const form = read();
    const id = await api.save_entry(form);
    if (!id) return;
    if (send) api.send_entry(form);
    closeModal(); LAST_V = -1;
    if (VIEW === "kb") renderKb();
  };
  $("#m-no", b).onclick = closeModal;
  $("#m-ok", b).onclick = () => save(false);
  $("#m-send", b).onclick = () => save(true);
}

// ---------- обновление (как в 3uTools) ----------
let UPD_SHOWN = false;
function updateDialog(u) {
  const notes = (u.notes || "").split("\n").map(l => l.trim()).filter(Boolean).map(l =>
    l.startsWith("#") ? `<div class="cap">${esc(l.replace(/^#+\s*/, ""))}</div>` :
    `<p>${esc(l.replace(/\*\*|`/g, "").replace(/^[*-]\s+/, "• "))}</p>`).join("");
  const b = modal(`<div class="row" style="flex-wrap:nowrap"><img src="icon.png" width="56" height="56" alt="">
      <div><h1>${esc(T.update_t.replace("{0}", u.version))}</h1>
      <div class="muted small">${esc(T.installed.replace("{0}", INFO.version))}</div></div></div>
    <div class="cap">${esc(T.whats_new)}</div>
    <div class="rich" style="max-height:46vh;overflow:auto;margin-top:10px">${notes}</div>
    <label class="chk" style="margin-top:12px"><input type="checkbox" id="u-skip"> ${esc(T.skip)}</label>
    <div class="modal-foot"><button class="btn" id="u-later">${esc(T.later)}</button>
      <button class="btn primary" id="u-go">${esc(u.can_self ? T.update_now : T.download)}</button></div>`);
  $("#u-later", b).onclick = () => { api.dismiss_update($("#u-skip", b).checked); closeModal(); };
  $("#u-go", b).onclick = () => { if (u.can_self) api.start_update(); else { api.open_url("https://github.com/mr1garik/ios-panic-reader/releases/latest"); closeModal(); } };
}
function updateProgress(p) {
  const m = $("#modal");
  if (p.state === "failed") { m.dataset.lock = ""; closeModal(); toast("error", p.error); api.cancel_update(); return; }
  m.dataset.lock = "1";
  let box = $("#u-prog");
  if (!box) {
    const b = modal(`<div id="u-prog"><h2>${esc(T.downloading.replace("{0}", p.version || ""))}</h2>
      <div class="muted small" id="u-text">${esc(T.connecting)}</div><div class="progress"><i id="u-bar" style="width:0"></i></div>
      <div class="modal-foot"><button class="btn" id="u-cancel">${esc(T.cancel)}</button></div></div>`);
    $("#u-cancel", b).onclick = () => { api.cancel_update(); m.dataset.lock = ""; closeModal(); };
    box = $("#u-prog");
  }
  const mb = 1048576;
  if (p.state === "installing") { $("#u-text").textContent = T.installing; $("#u-bar").style.width = "100%"; $("#u-cancel")?.remove(); return; }
  if (p.total) { $("#u-bar").style.width = (p.done * 100 / p.total).toFixed(1) + "%";
    $("#u-text").textContent = `${(p.done / mb).toFixed(1)} / ${(p.total / mb).toFixed(1)} MB · ${Math.floor(p.done * 100 / p.total)}%`; }
}

// ---------- мелочи ----------
function toast(kind, text) {
  const t = document.createElement("div");
  t.className = "toast " + (kind || "");
  t.textContent = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 9000 : 4500);
}
function menu(anchor, items) {
  const m = $("#menu");
  m.innerHTML = "";
  for (const [label, on, fn] of items) {
    const b = document.createElement("button");
    b.textContent = label; if (on) b.className = "on";
    b.onclick = () => { m.hidden = true; fn(); };
    m.appendChild(b);
  }
  m.hidden = false;
  const r = anchor.getBoundingClientRect(), z = INFO.zoom || 1;
  const mh = m.offsetHeight, mw = m.offsetWidth;
  let top = r.bottom / 1 + 6, left = r.left;
  if (top + mh > window.innerHeight / z) top = r.top - mh - 6;
  if (left + mw > window.innerWidth / z) left = window.innerWidth / z - mw - 8;
  m.style.top = Math.max(8, top) + "px"; m.style.left = Math.max(8, left) + "px";
}
function copyText(text) {
  const ta = document.createElement("textarea");
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); } catch (_) { /* нет доступа к буферу */ }
  ta.remove();
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
}
async function drop(e) {
  e.preventDefault();
  const files = [...(e.dataTransfer?.files || [])].map(f => f.path || f.pywebviewFullPath).filter(Boolean);
  if (files.length && await api.load_paths(files)) show("phone");
}

// сбои страницы — в журнал программы (их увидит «Сообщить об ошибке»)
window.addEventListener("error", e => { try { api.log_error(`${e.message} @ ${e.filename}:${e.lineno}`); } catch (_) { /* */ } });
window.addEventListener("unhandledrejection", e => { try { api.log_error("promise: " + (e.reason && (e.reason.stack || e.reason.message) || e.reason)); } catch (_) { /* */ } });

if (window.pywebview) boot();
else window.addEventListener("pywebviewready", boot);
if (location.protocol.startsWith("http")) window.addEventListener("load", boot);
