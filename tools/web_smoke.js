// Прокликивает весь новый интерфейс на демо-данных: каждую вкладку, кнопку и окно, смену темы,
// языка и масштаба, поиск по архиву, «после ремонта», вставку паники. Ловит ошибки JavaScript
// и ошибки Python (ответ 500). Выход с кодом 1, если что-то упало.
//   node tools/web_smoke.js
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PORT = 8899;

(async () => {
  const srv = spawn(process.env.PYTHON || "python3", ["-u", path.join(ROOT, "tools", "webui_dev.py"), "--demo", "--port", String(PORT)],
    { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  const pyErr = [];
  srv.stderr.on("data", d => pyErr.push(String(d)));
  await new Promise((res, rej) => { srv.stdout.on("data", d => String(d).includes("http") && res()); setTimeout(() => rej(new Error("сервер не запустился")), 60000); });

  const browser = await chromium.launch();
  const pg = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  pg.on("pageerror", e => errs.push("JS: " + e.message));
  pg.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text()); });
  pg.on("response", r => { if (r.status() >= 500) errs.push("Python 500: " + r.url()); });
  await pg.addInitScript("window.SPLASH_MS = 0");
  await pg.goto(`http://127.0.0.1:${PORT}/index.html`);
  await pg.waitForSelector("#app:not([hidden])");
  const step = async (name, fn) => {
    try { await fn(); await pg.waitForTimeout(250); console.log("✓", name); }
    catch (e) { errs.push(`${name}: ${e.message.split("\n")[0]}`); console.log("✗", name); }
  };
  const closeModal = () => pg.keyboard.press("Escape");
  const api = (m, ...a) => pg.evaluate(([m, a]) => fetch("/api/" + m, { method: "POST", body: JSON.stringify(a) }).then(r => r.json()), [m, a]);

  // Телефон
  await step("вероятность: раскрыть объяснение", () => pg.click(".prob-row"));
  await step("группа ошибок → логи", async () => { await pg.click(".group"); await pg.waitForSelector("#view-logs.on"); });
  await step("назад на телефон", () => pg.click('.nav-item[data-view="phone"]'));
  await step("«Показать логи этой детали»", async () => { await pg.click("[data-part]"); await pg.waitForSelector("#clear-part"); await pg.click("#clear-part"); });
  await step("отметить ремонт: окно", async () => { await pg.click('.nav-item[data-view="phone"]'); await pg.click('[data-a="mark_repair"]'); await pg.fill("#r-note", "тест"); await pg.click("#m-ok"); });
  await step("после ремонта: показать все / только после", async () => { await pg.waitForSelector('[data-a="toggle_after_repair"]'); await pg.click('[data-a="toggle_after_repair"]'); await pg.waitForTimeout(700); await pg.click('[data-a="toggle_after_repair"]'); });
  await step("очистить логи: окно", async () => { await pg.waitForSelector('[data-a="erase"]', { timeout: 3000 }).catch(() => null);
    if (await pg.$('[data-a="erase"]')) { await pg.click('[data-a="erase"]'); await pg.waitForSelector("#m-ok"); await closeModal(); } });
  await step("вставить панику: окно и разбор", async () => { await pg.click('[data-a="paste"]'); await pg.fill("#p-text",
    'panic(cpu 1 caller 0xfffffff0071a3f8c): SEP Panic: :sks /sks : 0x0001a3a1'); await pg.click("#m-ok"); });
  await step("PDF / TXT / папка без окна выбора (тест)", async () => { await api("save_pdf"); await api("save_txt"); });
  // Детали
  await step("вкладка «Детали»", () => pg.click('.nav-item[data-view="parts"]'));
  // Все логи
  await step("логи: поиск", async () => { await pg.click('.nav-item[data-view="logs"]'); await pg.fill("#logs-q", "mic1"); await pg.fill("#logs-q", ""); });
  await step("логи: только паники", () => pg.click("#logs-panic"));
  await step("логи: выбрать второй", () => pg.click("#logs-list .item:nth-child(2)"));
  await step("логи: исходный текст", () => pg.click('.tab[data-t="raw"]'));
  await step("логи: предложить для базы", async () => { await pg.click("#suggest"); await pg.waitForSelector("#s-text"); await closeModal(); });
  await step("логи: назад к разбору", () => pg.click('.tab[data-t="explain"]'));
  // История
  await step("история: список и заметка", async () => { await pg.click('.nav-item[data-view="history"]'); await pg.fill("#note", "заметка"); await pg.click("#note-save"); });
  await step("история: мастерская", async () => { await pg.fill("#workshop", "Lab"); await pg.click("#ws-save"); });
  await step("история: поиск", async () => { await pg.fill("#hist-q", "iPhone"); await pg.fill("#hist-q", ""); });
  await step("история: второй телефон", () => pg.click("#hist-list .item:nth-child(2)"));
  await step("история: открыть логи телефона", async () => { await pg.click("#hist-list .item:nth-child(1)"); await pg.waitForTimeout(300);
    if (await pg.$("#h-open")) { await pg.click("#h-open"); await pg.waitForSelector("#view-phone.on"); } });
  // Поиск ошибок
  await step("поиск: разделы", async () => { await pg.click('.nav-item[data-view="kb"]'); for (const b of await pg.$$("#kb-cats .tab")) await b.click(); await (await pg.$("#kb-cats .tab"))?.click(); });
  await step("поиск: модель", async () => { await pg.selectOption("#kb-model", { index: 3 }); await pg.waitForTimeout(500); await pg.selectOption("#kb-model", { index: 0 }); });
  await step("поиск: «mic1», архив логов", async () => { await pg.fill("#kb-q", "mic1"); await pg.check('input[name=scope][value=all]'); await pg.waitForTimeout(2500); await pg.fill("#kb-q", "mic1 "); await pg.waitForTimeout(800); });
  await step("поиск: открыть найденный лог", async () => { const it = await pg.$('#kb-list .item[data-id^="klog:"]'); if (it) await it.click(); });
  await step("поиск: датчик и шина", async () => { await pg.fill("#kb-q", "i2c"); await pg.waitForTimeout(600); const it = await pg.$$("#kb-list .item"); if (it[1]) await it[1].click(); });
  // Боковая панель
  await step("масштаб + и −", async () => { await pg.click("#zoom-in"); await pg.click("#zoom-out"); await pg.click("#zoom-out"); await pg.keyboard.press("Control+0"); });
  await step("горячие клавиши Ctrl+1..5", async () => { for (const k of "12345") await pg.keyboard.press("Control+" + k); });
  await step("темы: все по очереди", async () => {
    const n = await pg.evaluate(() => Object.keys(INFO.themes).length);
    for (let i = 0; i < n; i++) { await pg.click("#btn-theme"); await pg.click(`#menu button:nth-child(${i + 1})`); await pg.waitForTimeout(250); }
  });
  await step("язык: меню (без перезапуска)", async () => { await pg.click("#btn-lang"); await pg.waitForSelector("#menu:not([hidden])"); await closeModal(); await pg.mouse.click(700, 500); });
  await step("о программе: окно и копирование адреса", async () => { await pg.click("#btn-about"); await pg.click("#a-copy"); await pg.waitForSelector("#a-copied:has-text('')"); await closeModal(); });
  await step("обновление: окно «Доступна новая версия»", async () => {
    await pg.evaluate(() => updateDialog({ version: "9.9.9", notes: "## Новое\n* пункт", can_self: false }));
    await pg.waitForSelector("#u-later"); await pg.click("#u-later"); });

  // Подключение телефона: экраны состояний, как их показывает связь с iPhone
  const ev = (...e) => pg.evaluate(e => fetch("/test/event", { method: "POST", body: JSON.stringify(e) }), e);
  await step("телефон: экраны «Доверять», «Разблокируйте», «Снимаю логи», ошибка", async () => {
    await pg.click('.nav-item[data-view="phone"]');
    await api("again");
    for (const [code, want] of [["trust", ".hero h1"], ["unlock", ".hero h1"], ["denied", ".hero.err"], ["error", ".hero.err"]]) {
      await ev("state", code, code === "error" ? "Тестовая ошибка связи" : ""); await pg.waitForTimeout(900);
      if (!(await pg.$(want))) throw new Error("нет экрана " + code);
    }
    await ev("info", { model: "iPhone 13", ios: "18.6", serial: "F17DEMO0000", udid: "F17DEMO0000" }); await pg.waitForTimeout(900);
    if (!(await pg.$(".spinner"))) throw new Error("нет экрана «Снимаю логи»");
    await ev("pulled"); await pg.waitForTimeout(1200);
    if (!(await pg.$(".result"))) throw new Error("после снятия логов нет результата");
  });

  // Сообщить об ошибке программы
  await step("сообщить об ошибке: окно с журналом", async () => {
    await pg.click("#btn-bug"); await pg.waitForSelector("#b-det");
    const det = await pg.inputValue("#b-det");
    if (!det.includes("Version:")) throw new Error("в отчёте нет версии");
    if (det.includes("/home/") || det.includes("/Users/") || det.includes("C:\\Users")) throw new Error("в отчёте остался путь с именем пользователя");
    await closeModal(); });
  // Своё описание: неизвестная паника → описание → программа её узнаёт → правка → удаление
  const UNKNOWN = "panic(cpu 2 caller 0xfffffff012345678): ZZTestDriver: rail 0x1f stuck at 42 mV";
  await step("своё описание: создать из лога", async () => {
    await pg.click('.nav-item[data-view="phone"]'); await pg.click('[data-a="paste"]'); await pg.fill("#p-text", UNKNOWN); await pg.click("#m-ok");
    await pg.click('.nav-item[data-view="logs"]'); await pg.fill("#logs-q", "ZZTest"); await pg.waitForTimeout(400);
    const items = await pg.$$("#logs-list .item"); if (!items.length) throw new Error("вставленная паника не нашлась в логах");
    await items[0].click(); await pg.click("#add-entry"); await pg.waitForSelector("#e-pattern");
    if (!(await pg.inputValue("#e-pattern")).includes("ZZTestDriver")) throw new Error("текст из лога не подставился");
    await pg.fill("#e-title", "Тестовая поломка ZZ"); await pg.selectOption("#e-part", "charge_flex");
    await pg.fill("#e-fix", "Заменить тестовый шлейф"); await pg.click("#m-ok"); await pg.waitForTimeout(800);
    await pg.fill("#logs-q", ""); await pg.fill("#logs-q", "ZZTest"); await pg.waitForTimeout(500);
    const t = await pg.textContent("#logs-list"); if (!t.includes("Шлейф")) throw new Error("после описания паника не распозналась: " + t.slice(0, 120));
  });
  await step("своё описание: видно в поиске, изменить и удалить", async () => {
    await pg.click('.nav-item[data-view="kb"]'); await pg.fill("#kb-q", "Тестовая поломка"); await pg.waitForTimeout(700);
    await pg.click("#kb-list .item"); await pg.waitForSelector("#kb-del");
    await pg.click("#kb-edit"); await pg.fill("#e-fix", "Заменить шлейф (проверено)"); await pg.click("#m-ok"); await pg.waitForTimeout(700);
    if (!(await pg.textContent("#kb-detail")).includes("проверено")) throw new Error("правка не сохранилась");
    await pg.click("#kb-del"); await pg.click("#m-ok"); await pg.waitForTimeout(600);
    await pg.fill("#kb-q", "Тестовая поломка ZZ"); await pg.waitForTimeout(700);
    if ((await pg.textContent("#kb-list")).includes("Тестовая поломка ZZ")) throw new Error("запись не удалилась");
  });
  await step("ошибки страницы попадают в журнал", async () => {
    await pg.evaluate(() => api.log_error("тестовая ошибка страницы"));
    const r = await api("bug_report"); if (!r.includes("тестовая ошибка страницы")) throw new Error("нет в журнале");
  });

  await browser.close();
  srv.kill();
  const py = pyErr.join("").split("\n").filter(l => /Traceback|Error/.test(l));
  const all = [...new Set([...errs, ...py])];
  console.log(all.length ? "\nОШИБКИ:\n  " + all.join("\n  ") : "\nвсё прошло без ошибок");
  process.exit(all.length ? 1 : 0);
})();
