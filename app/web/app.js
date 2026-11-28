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
  partSel: null, kbQ: "", kbCat: "Все", kbScope: "base_logs", kbModel: "", kbSel: null, logTab: "explain" };

// ---------- значки: набор Lucide (ISC, лицензия в web/LICENSE-lucide.txt), один стиль и толщина линий ----------
const I = {
  phone: '<rect width="14" height="20" x="5" y="2" rx="2" ry="2" /><path d="M12 18h.01" />',
  parts: '<rect width="16" height="16" x="4" y="4" rx="2" /><rect width="6" height="6" x="9" y="9" rx="1" /><path d="M15 2v2" /><path d="M15 20v2" /><path d="M2 15h2" /><path d="M2 9h2" /><path d="M20 15h2" /><path d="M20 9h2" /><path d="M9 2v2" /><path d="M9 20v2" />',
  logs: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M10 9H8" /><path d="M16 13H8" /><path d="M16 17H8" />',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l4 2" />',
  kb: '<circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />',
  theme: '<path d="M12 8a2.83 2.83 0 0 0 4 4 4 4 0 1 1-4-4" /><path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.9 4.9 1.4 1.4" /><path d="m17.7 17.7 1.4 1.4" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m6.3 17.7-1.4 1.4" /><path d="m19.1 4.9-1.4 1.4" />',
  info: '<circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" />',
  plug: '<path d="M12 22v-5" /><path d="M9 8V2" /><path d="M15 8V2" /><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z" />',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />',
  warn: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" /><path d="M12 9v4" /><path d="M12 17h.01" />',
  chip: '<rect width="16" height="16" x="4" y="4" rx="2" /><rect width="6" height="6" x="9" y="9" rx="1" /><path d="M15 2v2" /><path d="M15 20v2" /><path d="M2 15h2" /><path d="M2 9h2" /><path d="M20 15h2" /><path d="M20 9h2" /><path d="M9 2v2" /><path d="M9 20v2" />',
  bolt: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z" />',
  face: '<path d="M3 7V5a2 2 0 0 1 2-2h2" /><path d="M17 3h2a2 2 0 0 1 2 2v2" /><path d="M21 17v2a2 2 0 0 1-2 2h-2" /><path d="M7 21H5a2 2 0 0 1-2-2v-2" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><path d="M9 9h.01" /><path d="M15 9h.01" />',
  bat: '<rect width="16" height="10" x="2" y="7" rx="2" ry="2" /><line x1="22" x2="22" y1="11" y2="13" /><line x1="6" x2="6" y1="11" y2="13" /><line x1="10" x2="10" y1="11" y2="13" />',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" />',
  folder: '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />',
  clip: '<path d="M15 2H9a1 1 0 0 0-1 1v2c0 .6.4 1 1 1h6c.6 0 1-.4 1-1V3c0-.6-.4-1-1-1Z" /><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2M16 4h2a2 2 0 0 1 2 2v2M11 14h10" /><path d="m17 10 4 4-4 4" />',
  pdf: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M12 18v-6" /><path d="m9 15 3 3 3-3" />',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />',
  gear: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" />',
  bug: '<path d="m8 2 1.88 1.88" /><path d="M14.12 3.88 16 2" /><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1" /><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6" /><path d="M12 20v-9" /><path d="M6.53 9C4.6 8.8 3 7.1 3 5" /><path d="M6 13H2" /><path d="M3 21c0-2.1 1.7-3.9 3.8-4" /><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4" /><path d="M22 13h-4" /><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4" />',
  pen: '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z" />',
  trash: '<path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" /><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" /><line x1="10" x2="10" y1="11" y2="17" /><line x1="14" x2="14" y1="11" y2="17" />',
};
const icon = (k, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${I[k] || ""}</svg>`;

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
      if (prev !== null && p.state === "reading") { STATE.partSel = null; STATE.okOpen = false; }       // новый телефон — сначала главная находка
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
  el.innerHTML = devbar(d) + verdict(d) + (d.repair ? repairBanner(d.repair) : "") +
    `<div class="diag"><div class="card plist">${partList(d.parts)}</div><div class="card pdetail" id="pdetail"></div></div>` +
    `<div class="below">${d.chart ? chart(d.chart) : ""}${notes(d)}</div>`;
  const sel = d.parts.find(r => r.part === STATE.partSel) || d.parts[0];
  STATE.partSel = sel && sel.part;
  const bindList = () => {
    const list = el.querySelector(".plist");
    list.querySelectorAll(".prow").forEach(r => r.onclick = () => {
      STATE.partSel = r.dataset.part;
      list.querySelectorAll(".prow").forEach(x => x.classList.toggle("sel", x === r));
      $("#pdetail").innerHTML = partDetail(d.parts.find(x => x.part === STATE.partSel), d);
      bindActions($("#pdetail"));
    });
    const t = list.querySelector("#ok-toggle");
    if (t) t.onclick = () => { STATE.okOpen = !t.classList.contains("open"); list.innerHTML = partList(d.parts); bindList(); };
  };
  bindList();
  $("#pdetail").innerHTML = sel ? partDetail(sel, d) : "";
  bindActions(el);
}

// Полоса телефона: что за устройство, его состояние и главные действия
function devbar(d) {
  const st = Object.fromEntries(d.stats.map(s => [s.key, s]));
  const prop = (v, label, lvl) => v ? `<div class="prop"><b class="${lvl ? "t-" + lvl : ""}">${esc(v)}</b><span>${esc(label)}</span></div>` : "";
  const sub = d.dev.sub.split(" · ");
  return `<div class="devbar">
    <div class="name">${esc(d.dev.model)}${d.chips[0] ? `<small>${esc(d.chips[0].text.split(" · ").pop())}</small>` : ""}</div>
    ${prop(sub[0], d.has_dev ? T.dev_ios : T.dev_source)}
    ${d.has_dev ? prop(sub[1], T.dev_serial) : ""}
    ${prop(d.dev.imei, "IMEI")}
    ${st.battery ? prop(st.battery.value + (st.cycles ? " · " + st.cycles.value : ""), T.battery + (st.cycles ? " · " + T.cycles.toLowerCase() : ""), st.battery.level) : ""}
    ${d.has_dev ? `<span class="state-pill ${d.connected ? "on" : ""}"><span class="dot ${d.connected ? "green" : "gray"}"></span>${esc(d.connected ? T.dev_connected : T.dev_disconnected)}</span>` : ""}
    <div class="acts">
      ${d.has_dev ? `<button class="btn" data-a="mark_repair">${icon("wrench")}${esc(T.mark_repair)}</button>` : ""}
      <button class="btn primary" data-a="save_pdf">${icon("pdf")}${esc(T.pdf)}</button>
    </div></div>`;
}

// Вывод одной фразой — главное, что нужно мастеру
function verdict(d) {
  const top = d.parts.find(r => r.level === "red") || d.parts.find(r => r.level === "orange");
  if (!top || !d.problems.length) {
    return `<div class="verdict"><div class="lbl t-green">${esc(T.found_none)}</div><h1>${esc(T.phone_ok)}</h1><p>${esc(d.ok_text || "")}</p></div>`;
  }
  const red = top.level === "red";
  const p = top.problem || d.problems[0];
  const evid = top.n ? T.n_of_total.replace("{0}", top.n).replace("{1}", d.stats.find(s => s.key === "panics")?.value || top.n) : (p.note || "");
  return `<div class="verdict"><div class="lbl ${red ? "t-red" : "t-orange"}">${esc(red ? T.likely_fault : T.possible_fault)}</div>
    <h1>${esc(top.name.replace(/\s*\(.*\)$/, ""))}</h1>
    <p>${esc(evid)}</p></div>`;
}

function repairBanner(r) {
  return `<div class="banner"><b>${esc(r.title)}</b><span class="t-${r.level}">${esc(r.text)}</span>
    <button class="btn small" data-a="toggle_after_repair" style="margin-left:auto">${esc(r.after ? T.show_all : T.only_after)}</button></div>`;
}

function partList(rows) {
  // Сначала детали со сбоями; исправные свёрнуты в одну строку, раскрываются по клику
  const bad = rows.filter(r => r.level !== "green"), good = rows.filter(r => r.level === "green");
  const open = STATE.okOpen === true || !bad.length;
  const row = r => `<div class="prow ${r.level} ${r.part === STATE.partSel ? "sel" : ""}" data-part="${esc(r.part)}">
      <span class="dot ${r.level}"></span>
      <div class="nm"><b>${esc(r.name)}</b>${r.data ? `<span>${esc(r.data)}</span>` : ""}</div>
      <span class="n">${r.n || "—"}</span>
      ${r.n ? `<div class="mini"><i style="width:${r.pct}%"></i></div>` : "<span></span>"}</div>`;
  let h = `<div class="head"><span></span><span>${esc(T.part)}</span><span style="text-align:right">${esc(T.panics)}</span><span>${esc(T.share)}</span></div>` +
    bad.map(row).join("");
  if (good.length && bad.length) {
    h += `<button class="pgroup ${open ? "open" : ""}" id="ok-toggle"><span class="dot green"></span>
      <span>${esc(T.ok_parts.replace("{0}", good.length))}</span><span class="chev">${open ? "▾" : "▸"}</span></button>`;
  }
  if (open) h += good.map(row).join("");
  return h;
}

function partDetail(r, d) {
  if (!r) return "";
  const p = r.problem;
  const status = { red: T.st_red, orange: T.st_orange, green: T.st_green }[r.level];
  let h = `<h2>${esc(r.name)}<span class="status ${r.level}">${esc(status)}</span></h2>
    <div class="meta">${r.n ? esc(T.first_last.replace("{0}", r.n).replace("{1}", r.first).replace("{2}", r.last)) : esc(r.data || T.no_faults)}</div>`;
  if (p) {
    h += `<div class="split2"><div><div class="cap">${esc(T.how)}</div><div>${esc(p.how)}</div>
        <div class="cap">${esc(T.why)}</div><div>${esc(p.why)}</div></div>
      ${p.board && p.board.zone !== "none" ? where(p.board) : "<div></div>"}</div>
      <div class="cap">${esc(T.fix)}</div>
      <ul class="checklist">${p.fix.map(f => `<li><input type="checkbox"><span>${esc(f)}</span></li>`).join("")}</ul>`;
  } else if (!r.n) {
    h += `<p class="muted" style="margin:12px 0 0">${esc(T.no_faults)}</p>`;
  }
  if (r.evidence.length) {
    h += `<div class="cap">${esc(T.evidence)} · ${r.n}</div><div class="evidence">${r.evidence.map(e =>
      `<button data-log="${e.id}"><span>${esc(e.date)}</span><span>${esc(e.text)}</span></button>`).join("")}</div>
      <button class="link" data-part="${esc(r.part)}" style="margin-top:6px">${esc(T.all_part_logs.replace("{0}", r.n))} →</button>`;
  }
  return h;
}

// Где искать: простой контур телефона и зона (не схема платы конкретной модели)
function where(b) {
  const zones = { top: '<rect class="zone" x="12" y="10" width="46" height="18" rx="4"/>',
    bottom: '<rect class="zone" x="12" y="86" width="46" height="18" rx="4"/>',
    battery: '<rect class="zone" x="31" y="34" width="27" height="46" rx="3"/>',
    board: '<rect class="zone" x="12" y="34" width="17" height="46" rx="3"/>',
    screen: '<rect class="zone" x="8" y="6" width="54" height="102" rx="9"/>' };
  return `<div class="where"><svg class="where-svg" viewBox="0 0 70 114"><rect x="4" y="2" width="62" height="110" rx="12" fill="none" stroke="var(--c-border)" stroke-width="1.5"/>
    <rect x="12" y="34" width="17" height="46" rx="3" fill="var(--c-gray_bg)"/><rect x="31" y="34" width="27" height="46" rx="3" fill="var(--c-gray_bg)"/>
    ${zones[b.zone] || ""}</svg>${esc(b.title)}</div>`;
}

function chart(c) {
  const max = Math.max(1, ...c.days.map(d => d[1]));
  return `<div class="card"><h2>${esc(c.title)}</h2><div class="chart">${c.days.map(([day, n]) =>
    `<div class="b ${n ? "" : "z"} ${day === c.repair ? "rep" : ""}" style="height:${n ? Math.max(6, n / max * 100) : 2}%" title="${esc(day)}: ${n}">${n ? `<span>${n}</span>` : ""}</div>`).join("")}</div>
    <div class="chart-axis"><span>${esc(c.days[0][0])}</span><span>${esc(c.days[c.days.length - 1][0])}</span></div></div>`;
}

// Прочее: прошлый визит, не связанное с железом, действия с телефоном
function notes(d) {
  let h = `<div class="card notes">`;
  if (d.prev) h += `<div class="cap" style="margin-top:0">${esc(T.prev)}</div><p><span class="dot ${d.prev.level}"></span><span>${esc(d.prev.date)} · ${esc(d.prev.text)}${d.prev.battery ? " · " + esc(d.prev.battery) : ""}</span></p>`;
  if (d.other.length) h += `<div class="cap" ${d.prev ? "" : 'style="margin-top:0"'}>${esc(T.other)}</div>` + d.other.map(([l, t]) => `<p><span class="dot ${l}"></span><span>${esc(t)}</span></p>`).join("");
  h += `<div class="row" style="margin-top:12px">
      <button class="btn small" data-view="logs">${esc(T.show_logs)}</button>
      <button class="btn small" data-a="save_txt">${esc(T.txt)}</button>
      ${d.dir ? `<button class="btn small" data-a="open_dir">${icon("folder")}${esc(T.folder)}</button>` : ""}
      ${d.connected ? `<button class="btn small danger" data-a="erase">${icon("trash")}${esc(T.erase)}</button>` : ""}
      ${INFO.has_device ? `<button class="btn small" data-a="again">${icon("plug")}${esc(T.other_phone)}</button>` : ""}
      <button class="btn small" data-a="open_files">${icon("file")}${esc(T.open_file)}</button>
      <button class="btn small" data-a="paste">${icon("clip")}${esc(T.paste)}</button></div></div>`;
  return h;
}

// ---------- кнопки-действия ----------
function bindActions(el) {
  el.querySelectorAll("[data-a]").forEach(b => b.onclick = () => action(b.dataset.a, b));
  el.querySelectorAll("[data-view]").forEach(b => b.onclick = () => show(b.dataset.view));
  el.querySelectorAll("button[data-part], .link[data-part]").forEach(b => b.onclick = () => { STATE.part = b.dataset.part; STATE.logSel = null; show("logs"); });
  el.querySelectorAll("[data-log]").forEach(b => b.onclick = () => { STATE.part = null; STATE.logQ = ""; STATE.logSel = +b.dataset.log; STATE.logTab = "explain"; show("logs"); });
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
    `<div class="item ${i.id === STATE.kbSel ? "sel" : ""}" data-id="${esc(i.id)}">${i.level ? `<span class="dot ${i.level}"></span>` : "<span></span>"}
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
