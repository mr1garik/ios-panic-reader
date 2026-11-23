// Проверка нового интерфейса в браузере: размеры окна × масштаб Windows × язык × тема.
// Ищет: обрезанный текст (без многоточия), налезающие надписи, горизонтальную прокрутку,
// ошибки JavaScript. Скриншоты — в папку out.
//   node tools/web_matrix.js out [--quick]
// Нужны: Node с Playwright, Python (tools/webui_dev.py поднимает страницу с демо-данными).
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.join(__dirname, "..");
const out = process.argv[2] || "web-screens";
const quick = process.argv.includes("--quick");
fs.mkdirSync(out, { recursive: true });

// окно программы в CSS-пикселях = экран (без панели задач и рамки) / масштаб Windows
const SCREENS = [[1280, 720, 1], [1366, 768, 1], [1366, 768, 1.25], [1536, 864, 1.25], [1920, 1080, 1],
  [1920, 1080, 1.5], [2560, 1440, 1.5], [3840, 2160, 2], [3840, 2160, 3]];
const LANGS = quick ? ["ru"] : ["ru", "en", "uk"];
const THEMES = quick ? ["neon"] : ["neon", "light", "dark", "night", "mint", "graphite"];

function server(lang, port) {
  const p = spawn(process.env.PYTHON || "python3", [path.join(ROOT, "tools", "webui_dev.py"), "--demo", "--port", String(port), "--lang", lang],
    { stdio: ["ignore", "pipe", "inherit"] });
  return new Promise(res => p.stdout.on("data", d => { if (String(d).includes("http")) res(p); }));
}

// аудит страницы (выполняется в браузере)
function audit() {
  const probs = [];
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1) probs.push(`горизонтальная прокрутка страницы (${document.documentElement.scrollWidth} > ${vw})`);
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && +s.opacity !== 0; };
  const leaves = [];
  const modalOpen = !document.querySelector("#modal").hidden;
  for (const el of document.querySelectorAll(modalOpen ? "#modal *" : "#app *")) {
    if (!vis(el) || el.closest("[hidden]") || el.closest("svg")) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const s = getComputedStyle(el);
    // обрезано без многоточия (кроме прокручиваемых блоков, полей ввода и графика)
    const scrollable = /(auto|scroll)/.test(s.overflowX) || /(auto|scroll)/.test(s.overflowY) || el.matches("input,textarea,select,pre,.chart,.chart *");
    if (own && !scrollable && s.textOverflow !== "ellipsis") {
      if (el.scrollWidth > el.clientWidth + 2 && s.overflowX !== "visible") probs.push(`обрезан по ширине: «${el.textContent.trim().slice(0, 40)}»`);
      if (el.scrollHeight > el.clientHeight + 2 && s.overflowY !== "visible" && s.overflowY !== "clip") probs.push(`обрезан по высоте: «${el.textContent.trim().slice(0, 40)}»`);
    }
    // выходит за край своего прокручиваемого контейнера или окна по горизонтали
    if (own) {
      const r = el.getBoundingClientRect();
      let p = el.parentElement, box = { left: 0, right: vw };
      while (p) { const ps = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(ps.overflowX)) { const pr = p.getBoundingClientRect(); box = { left: Math.max(box.left, pr.left), right: Math.min(box.right, pr.right) }; } p = p.parentElement; }
      if ((r.right > box.right + 2 || r.left < box.left - 2) && s.textOverflow !== "ellipsis") probs.push(`за краем: «${el.textContent.trim().slice(0, 40)}»`);
      leaves.push([el, [...el.getClientRects()]]);      // у перенесённого текста — по прямоугольнику на строку
    }
  }
  // налезающие надписи (не вложенные друг в друга)
  for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
    const [a, ras] = leaves[i], [b, rbs] = leaves[j];
    if (a.contains(b) || b.contains(a)) continue;
    const hit = ras.some(ra => rbs.some(rb => Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left) > 3 &&
                                             Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top) > 3));
    if (hit) probs.push(`налезают: «${a.textContent.trim().slice(0, 25)}» и «${b.textContent.trim().slice(0, 25)}»`);
  }
  return [...new Set(probs)].slice(0, 15);
}

(async () => {
  const browser = await chromium.launch();
  let bad = 0, port = 8790;
  for (const lang of LANGS) {
    const srv = await server(lang, ++port);
    const url = `http://127.0.0.1:${port}/index.html`;
    for (const theme of THEMES) {
      const screens = theme === "neon" ? SCREENS : [[1366, 768, 1.25]];
      for (const [sw, sh, dpr] of screens) {
        const w = Math.round((sw - 16) / dpr), h = Math.round((sh - 48 - 40) / dpr);   // рамка, панель задач, заголовок
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
        const pg = await ctx.newPage();
        const errs = [];
        pg.on("pageerror", e => errs.push("JS: " + e.message));
        pg.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text()); });
        await pg.addInitScript("window.SPLASH_MS = 0");
        await pg.goto(url);
        await pg.waitForSelector("#app:not([hidden])");
        await pg.evaluate(t => fetch("/api/set_setting", { method: "POST", body: JSON.stringify(["theme", t]) }), theme);
        await pg.reload(); await pg.waitForSelector("#app:not([hidden])"); await pg.waitForTimeout(900);
        const tag = `${sw}x${sh}@${dpr * 100}%_${lang}_${theme}`;
        const probs = [];
        for (const v of ["phone", "parts", "logs", "history", "kb"]) {
          await pg.click(`.nav-item[data-view="${v}"]`); await pg.waitForTimeout(450);
          for (const p of await pg.evaluate(audit)) probs.push(`${v}: ${p}`);
          if (v === "phone") {
            await pg.evaluate(() => document.querySelector("#view-phone").scrollTo(0, 1e6)); await pg.waitForTimeout(200);
            for (const p of await pg.evaluate(audit)) probs.push(`phone (низ): ${p}`);
          }
          if (theme === "neon" || v === "phone") await pg.screenshot({ path: `${out}/${tag}_${v}.png` });
        }
        await pg.click(".nav-item[data-view=logs]"); await pg.click('.tab[data-t="raw"]'); await pg.waitForTimeout(300);
        for (const p of await pg.evaluate(audit)) probs.push(`raw: ${p}`);
        await pg.click("#btn-about"); await pg.waitForTimeout(300);
        for (const p of await pg.evaluate(audit)) probs.push(`about: ${p}`);
        await pg.screenshot({ path: `${out}/${tag}_about.png` });
        const all = [...new Set([...errs, ...probs])];
        console.log((all.length ? "✗ " : "✓ ") + tag + (all.length ? "\n    " + all.join("\n    ") : ""));
        bad += !!all.length;
        await ctx.close();
      }
    }
    srv.kill();
  }
  await browser.close();
  console.log(`\nс проблемами: ${bad}`);
  process.exit(bad ? 1 : 0);
})();
