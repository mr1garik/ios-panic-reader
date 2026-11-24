// Скриншоты и GIF нового интерфейса для README (демо-данные): docs/screenshots/<язык>/.
//   node tools/web_screenshots.js [ru en uk]
// Нужны: Node с Playwright, Python, ImageMagick (convert). Рамку и тень добавляет tools/screenshots.py:frame.
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const ROOT = path.join(__dirname, "..");
const PY = process.env.PYTHON || "python3";
const langs = process.argv.slice(2).length ? process.argv.slice(2) : ["ru", "en", "uk"];
const W = 1440, H = 900;

function server(lang, port) {
  const p = spawn(PY, ["-u", path.join(ROOT, "tools", "webui_dev.py"), "--demo", "--port", String(port), "--lang", lang],
    { stdio: ["ignore", "pipe", "inherit"] });
  return new Promise((res, rej) => {
    p.stdout.on("data", d => { if (String(d).includes("http")) res(p); });
    p.on("exit", c => rej(new Error("webui_dev.py: " + c)));
  });
}
const frame = (src, dst) => execFileSync(PY, ["-c",
  "import sys; sys.path.insert(0, sys.argv[3]); import screenshots as S; S.frame(sys.argv[1], sys.argv[2])",
  src, dst, path.join(ROOT, "tools")]);

(async () => {
  const browser = await chromium.launch();
  let port = 8820;
  for (const lang of langs) {
    const srv = await server(lang, ++port);
    const raw = fs.mkdtempSync(path.join(os.tmpdir(), "iospr-web-"));
    const out = path.join(process.env.SHOTS_OUT || path.join(ROOT, "docs", "screenshots"), lang);   // SHOTS_OUT — для пробы
    fs.mkdirSync(out, { recursive: true });
    const pg = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await pg.addInitScript("window.SPLASH_MS = 0");
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForSelector("#app:not([hidden])"); await pg.waitForTimeout(1200);
    const gif = [];
    const snap = async (name, keep = true) => {
      await pg.waitForTimeout(500);
      const f = path.join(raw, name + ".png");
      await pg.screenshot({ path: f });
      gif.push(f);
      if (keep) frame(f, path.join(out, name + ".png"));
    };
    const go = async v => { await pg.click(`.nav-item[data-view="${v}"]`); await pg.waitForTimeout(400); };
    await snap("4_result");
    await pg.evaluate(() => { document.querySelector(".prob-row")?.classList.add("open"); });
    await pg.evaluate(() => document.querySelector("#view-phone .chart")?.scrollIntoView({ block: "center" }));
    await snap("5_result_chart");
    await pg.evaluate(() => document.querySelector("#view-phone").scrollTo(0, 0));
    await pg.click("[data-part]"); await pg.waitForTimeout(500);
    await snap("6_logs");
    await go("parts"); await snap("7_parts");
    await go("history"); await snap("8_history");
    await go("kb"); await pg.fill("#kb-q", "mic1"); await pg.waitForTimeout(700); await snap("9_search");
    await pg.fill("#kb-q", "4013"); await pg.waitForTimeout(700); await snap("10_search_code", true);
    // после ремонта
    await pg.evaluate(() => fetch("/api/mark_repair", { method: "POST", body: JSON.stringify(["charging flex", false]) }));
    await go("phone"); await pg.waitForTimeout(900); await snap("11_after_repair");
    await pg.close();
    // GIF: каждый кадр ~1.8 с
    const small = gif.map(f => { const s = f.replace(".png", "_s.png"); execFileSync("convert", [f, "-resize", "960x", s]); return s; });
    execFileSync("convert", ["-delay", "180", "-loop", "0", ...small, "-fuzz", "2%", "-layers", "OptimizePlus", "-colors", "180",
      path.join(out, "demo.gif")]);
    fs.rmSync(raw, { recursive: true, force: true });
    srv.kill();
    console.log("готово:", out);
  }
  await browser.close();
})();
