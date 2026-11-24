# -*- coding: utf-8 -*-
"""Работа программы «как у мастера» — через тот же Backend, что и новое окно.
Телефон имитируется событиями, которые отдаёт связь с iPhone (device.DeviceWatcher):
state → info → pulled → disconnected → erased.

1. Полный цикл: ожидание → «Доверять» → разблокировка → снятие логов → результат → ремонт →
   очистка логов на телефоне → повторное подключение после ремонта.
2. Плохие файлы: пустые, битые, двоичные, огромные, с кириллицей в имени; 1000 логов на скорость.
3. Отчёты PDF и TXT создаются на самом деле.
4. История переживает перезапуск.
5. На английском и украинском в интерфейсе нет русских слов.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

os.environ["IOSPR_LANG"] = "ru"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
SAMPLES = os.path.join(ROOT, "tests", "samples")
SERIAL = "F17TEST0001"
UDID = "00008110-TEST"
CYR = re.compile("[А-Яа-яЁёІіЇїЄєҐґ]")


def panic_file(folder, when, sensors="mic1 prs0", name=None):
    """Паника «нет датчиков» с нужной датой (как в настоящем panic-full-*.ips)."""
    # пояс — как у этого компьютера: так «до/после ремонта» считается без сдвига
    stamp = when.strftime("%Y-%m-%d %H:%M:%S.00 ") + (datetime.now().astimezone().strftime("%z") or "+0000")
    text = ("panic(cpu 4 caller 0xfffffff01b2c8a10): userspace watchdog timeout: no successful checkins from "
            "com.apple.thermalmonitord in 180 seconds\\nservice returned not alive with context : "
            f"is_alive_func returned unhealthy : current menu: Missing sensor(s): {sensors} \\nDebugger message: panic")
    path = os.path.join(folder, name or f"panic-full-{when:%Y-%m-%d-%H%M%S}.000.ips")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"bug_type": "210", "timestamp": stamp, "os_version": "iPhone OS 18.6 (22G86)"}) + "\n")
        f.write(json.dumps({"product": "iPhone14,5", "panicString": text.replace("\\n", "\n"), "date": stamp}))
    return path


class FakeWatcher:
    """Вместо потока связи с iPhone: очереди, как у DeviceWatcher."""
    def __init__(self):
        self.erase, self.manual = queue.Queue(), queue.Queue()


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="iospr-scn-")
        self._env = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = self.home
        import core
        import webui
        self.core, self.webui = core, webui
        core.KB[:] = [e for e in core.KB if not e.get("user")]
        self.logs_dir = os.path.join(core.logs_root(), f"iPhone 13_{SERIAL}")
        os.makedirs(self.logs_dir)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def backend(self):
        b = self.webui.Backend(with_device=False)
        b.watcher = FakeWatcher()
        b.phone_state = "wait"
        return b

    def dev(self):
        return dict(udid=UDID, name="iPhone", product="iPhone14,5", model="iPhone 13", ios="18.6", build="22G86",
                    serial=SERIAL, imei="356789012345678", is_iphone=True, battery_health=84,
                    battery_mah="2700/3227 mAh", battery_cycles=512, dir=self.logs_dir)


class TestRepairCycle(Base):
    def test_full_day_of_a_repair_shop(self):
        now = datetime.now()
        for i in range(4):
            panic_file(self.logs_dir, now - timedelta(days=3, minutes=3 * i))
        b = self.backend()

        # подключили кабель: ждём «Доверять», разблокировку, снимаются логи
        for code in ("trust", "unlock"):
            b.events.put(("state", code, ""))
            self.assertEqual(b.poll()["state"], code)
            self.assertEqual(b.phone()["state"], code)
        b.events.put(("info", self.dev()))
        self.assertEqual(b.poll()["state"], "reading")

        # логи сняты — результат
        b.events.put(("pulled", self.dev()))
        b.poll()
        d = b.phone()
        self.assertEqual(d["state"], "result")
        self.assertEqual(d["problems"][0]["part"], "charge_flex")
        self.assertEqual(d["probability"][0]["pct"], 100)
        self.assertTrue(d["connected"], "кнопка очистки логов должна быть видна у подключённого телефона")
        self.assertTrue(os.path.isfile(os.path.join(self.logs_dir, self.core.REPORT_FILE)), "нет TXT-отчёта в папке")
        self.assertEqual(len(b.history_list()), 1)

        # отметили ремонт с очисткой логов на телефоне
        self.assertTrue(b.mark_repair("заменён шлейф зарядки", True))
        self.assertEqual(b.watcher.erase.get_nowait(), UDID)
        b.events.put(("erased", [UDID], []))
        notes = b.poll()["notices"]
        self.assertTrue(any(n["kind"] == "ok" for n in notes))
        d = b.phone()
        self.assertEqual(d["problems"], [], "старые паники не должны считаться после ремонта")
        self.assertEqual(d["repair"]["level"], "green")

        # «показать все логи» — старые паники видны снова
        b.toggle_after_repair()
        self.assertTrue(b.phone()["problems"])
        b.toggle_after_repair()

        # отключили, телефон вернулся с новой паникой
        b.events.put(("disconnected", UDID))
        b.poll()
        self.assertFalse(b.phone()["connected"])
        time.sleep(1.1)
        panic_file(self.logs_dir, datetime.now() + timedelta(minutes=1))
        b.events.put(("pulled", self.dev()))
        b.poll()
        d = b.phone()
        self.assertEqual(d["repair"]["level"], "red", "новая паника после ремонта должна быть видна")
        self.assertEqual(len(b.phone_history(SERIAL)["visits"]), 2)
        self.assertIsNotNone(d["prev"], "должно быть «этот телефон уже был»")

    def test_device_errors_go_to_bug_report(self):
        b = self.backend()
        b.events.put(("state", "error", "ConnectionAbortedError: тест связи"))
        b.events.put(("log", "MuxException: тест"))
        b.poll()
        report = b.bug_report()
        self.assertIn("ConnectionAbortedError", report)
        self.assertIn("MuxException", report)
        self.assertEqual(b.phone()["state"], "error")

    def test_erase_refused_for_not_copied_phone(self):
        """Стирать можно только скопированное — Backend просит, а поток устройства проверяет."""
        b = self.backend()
        self.assertFalse(b.erase_phone(), "без телефона стирать нечего")


class TestBadFiles(Base):
    def test_broken_files_do_not_break_anything(self):
        d = self.logs_dir
        with open(os.path.join(d, "panic-full-empty.ips"), "w") as f:
            f.write("")
        with open(os.path.join(d, "panic-full-binary.ips"), "wb") as f:
            f.write(os.urandom(4096))
        with open(os.path.join(d, "panic-full-bplist.ips"), "wb") as f:
            f.write(b"bplist00" + os.urandom(200))
        with open(os.path.join(d, "panic-full-badjson.ips"), "w", encoding="utf-8") as f:
            f.write('{"bug_type":"210", "timestamp": \n{"panicString": "panic(cpu 0): Missing sensor(s): mic1')
        with open(os.path.join(d, "Паника телефона клиента №1.ips"), "w", encoding="utf-8") as f:
            f.write('{"bug_type":"210"}\n{"panicString":"panic(cpu 0): SEP Panic: :sks /sks : 0x1"}')
        with open(os.path.join(d, "panic-full-huge.ips"), "w", encoding="utf-8") as f:
            f.write('{"bug_type":"210"}\n{"panicString":"panic(cpu 0): test ' + "x" * 6_000_000 + '"}')
        b = self.backend()
        b.load_paths([d])
        for res in (b.phone(), b.parts(), b.logs_list(), b.kb("mic1", "Все", "all")):
            json.dumps(res, ensure_ascii=False)
        for item in b.logs_list()["items"]:
            json.dumps(b.log_detail(item["id"]), ensure_ascii=False)
        self.assertTrue(any("SEP" in str(b.log_detail(i["id"])["raw"]) for i in b.logs_list()["items"]))

    def test_thousand_logs_fast_enough(self):
        now = datetime.now()
        for i in range(1000):
            panic_file(self.logs_dir, now - timedelta(minutes=i), name=f"panic-full-{i:04d}.ips")
        b = self.backend()
        t = time.time()
        b.load_paths([self.logs_dir])
        load = time.time() - t
        t = time.time()
        b.phone(), b.logs_list(), b.parts()
        show = time.time() - t
        self.assertEqual(len(b.logs), 1000)
        self.assertLess(load, 60, f"1000 логов читались {load:.1f} с")
        self.assertLess(show, 10, f"экраны строились {show:.1f} с")
        print(f"\n1000 логов: чтение {load:.1f} с, экраны {show:.2f} с", file=sys.stderr)


class TestReports(Base):
    def test_pdf_and_txt_are_really_made(self):
        for i in range(3):
            panic_file(self.logs_dir, datetime.now() - timedelta(days=1, minutes=3 * i))
        b = self.backend()
        b.events.put(("pulled", self.dev()))
        b.poll()
        out = os.path.join(self.home, "отчёты клиента")
        os.makedirs(out)
        txt, pdf = os.path.join(out, "отчёт.txt"), os.path.join(out, "отчёт.pdf")
        b._dialog = lambda kind, **kw: txt
        self.assertEqual(b.save_txt(), txt)
        with open(txt, encoding="utf-8") as f:
            text = f.read()
        for part in ("iPhone 13", SERIAL, "Шлейф зарядки", "mic1"):
            self.assertIn(part, text)
        import report_pdf
        if not report_pdf.available():
            self.skipTest("нет reportlab")
        b._dialog = lambda kind, **kw: pdf
        b.open_path = lambda path: True          # не открывать просмотрщик
        self.assertEqual(b.save_pdf(), pdf)
        with open(pdf, "rb") as f:
            head = f.read(5)
        self.assertEqual(head, b"%PDF-")
        self.assertGreater(os.path.getsize(pdf), 3000)
        if shutil.which("pdftotext"):          # дополнительно: текст внутри PDF (если утилита работает)
            ptxt = subprocess.run(["pdftotext", "-enc", "UTF-8", pdf, "-"], capture_output=True).stdout.decode(
                "utf-8", "replace")
            if ptxt.strip():
                self.assertIn("iPhone 13", ptxt)


class TestHistoryPersists(Base):
    def test_restart_keeps_everything(self):
        panic_file(self.logs_dir, datetime.now())
        b = self.backend()
        b.events.put(("pulled", self.dev()))
        b.poll()
        b.set_note(SERIAL, "клиент Иван, звонить после 18:00")
        b.mark_repair("шлейф", False)
        b.set_workshop("Мастерская на Ленина")
        # «перезапуск»: новый Backend читает то же с диска
        b2 = self.backend()
        p = b2.phone_history(SERIAL)
        self.assertEqual(p["note"], "клиент Иван, звонить после 18:00")
        self.assertEqual(len(p["repairs"]), 1)
        self.assertEqual(b2.app_info()["workshop"], "Мастерская на Ленина")
        self.assertTrue(b2.open_history_logs(SERIAL))
        self.assertTrue(b2.logs_list()["items"])


class TestLanguages(unittest.TestCase):
    """Экран телефона на en/uk: подписи и разбор без русского текста (отдельный процесс — язык при запуске)."""

    def check(self, lang):
        code = f"""
import json, os, sys
sys.path.insert(0, {os.path.join(ROOT, 'app')!r})
import webui
b = webui.Backend(with_device=False)
b.load_paths([{SAMPLES!r}])
d = b.phone()
out = dict(t=b.app_info()["t"], problems=[{{k: p[k] for k in ("title", "how", "why", "fix", "note")}} for p in d["problems"]],
           prob=[p["title"] for p in d["probability"]], groups=[g["title"] for g in d["groups"]],
           parts=[r["name"] + r["fails"] for r in b.parts()["rows"]])
print(json.dumps(out, ensure_ascii=False))
"""
        env = dict(os.environ, IOSPR_LANG=lang, HOME=tempfile.mkdtemp(), USERPROFILE=tempfile.mkdtemp(),
                   PYTHONIOENCODING="utf-8")          # консоль Windows по умолчанию не в UTF-8
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        data = json.loads(r.stdout.strip().splitlines()[-1])
        return data

    def test_english_has_no_russian(self):
        data = self.check("en")
        bad = [s for s in re.findall(r'"([^"]*)"', json.dumps(data, ensure_ascii=False)) if CYR.search(s)]
        self.assertEqual(bad, [], "русский текст в английской версии")

    def test_ukrainian_is_ukrainian(self):
        data = self.check("uk")
        text = json.dumps(data, ensure_ascii=False)
        self.assertIn("Телефон", text)
        # буквы, которых нет в украинском
        russian_only = [s for s in re.findall(r'"([^"]*)"', text) if re.search("[ЫыЭэЁёЪъ]", s)]
        self.assertEqual(russian_only, [], "русские слова в украинской версии")


class TestTransfer(Base):
    """Перенос настроек и данных: компьютер А → файл → компьютер Б."""

    def switch_home(self):
        home = tempfile.mkdtemp(prefix="iospr-scn-b-")
        os.environ["HOME"] = os.environ["USERPROFILE"] = home
        self.core.KB[:] = [e for e in self.core.KB if not e.get("user")]
        return home

    def test_move_to_another_computer(self):
        import zipfile
        # компьютер А: телефон, заметка, ремонт, своё описание, логи, настройки
        panic_file(self.logs_dir, datetime.now() - timedelta(days=1))
        a = self.backend()
        a.events.put(("pulled", self.dev()))
        a.poll()
        a.set_note(SERIAL, "клиент А")
        a.mark_repair("шлейф", False)
        a.set_workshop("Мастерская А")
        a.set_setting("theme", "mint")
        a.save_entry({"title": "Моя поломка", "pattern": "ZZDriver stuck", "part": "board", "fix": "перепайка"})
        out = os.path.join(self.home, "перенос.zip")
        res = a.export_data(True, out)
        self.assertEqual(res["phones"], 1)
        self.assertGreaterEqual(res["logs"], 1)
        self.assertEqual(res["entries"], 1)

        # компьютер Б: свой телефон и та же модель с другой заметкой
        self.switch_home()
        b = self.webui.Backend(with_device=False)
        b.history.phones[SERIAL] = {"model": "iPhone 13", "serial": SERIAL, "note": "клиент Б", "visits": [],
                                    "repairs": []}
        b.history.phones["OTHER1"] = {"model": "iPhone 11", "serial": "OTHER1", "note": "", "visits": [], "repairs": []}
        b.history.save()
        r = b.import_data(out)
        self.assertEqual(r["phones_merged"], 1)
        p = b.phone_history(SERIAL)
        self.assertIn("клиент А", p["note"])
        self.assertIn("клиент Б", p["note"])           # своё не затёрто
        self.assertEqual(len(p["repairs"]), 1)
        self.assertIsNotNone(b.phone_history("OTHER1"))
        self.assertEqual(b.app_info()["workshop"], "Мастерская А")
        self.assertEqual(b.app_info()["theme"], "mint")
        self.assertTrue(b.kb("Моя поломка")[0]["items"])
        self.assertTrue(b.open_history_logs(SERIAL), "логи телефона не перенеслись")
        # повторная загрузка того же файла ничего не удваивает
        r2 = b.import_data(out)
        self.assertEqual((r2["visits"], r2["repairs"], r2["entries"], r2["logs"]), (0, 0, 0, 0))
        self.assertEqual(len(b.phone_history(SERIAL)["repairs"]), 1)
        # перед загрузкой сделана копия истории
        self.assertTrue(os.listdir(os.path.join(os.path.dirname(self.core.logs_root()), "backups")))

    def test_bad_files_are_refused(self):
        import zipfile
        b = self.backend()
        bad = os.path.join(self.home, "чужой.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("readme.txt", "не перенос")
        self.assertIsNone(b.import_data(bad))
        notes = b.poll()["notices"]
        self.assertTrue(any(n["kind"] == "error" for n in notes))
        # файл переноса с опасными путями: ничего не пишется за пределы папки логов
        evil = os.path.join(self.home, "evil.zip")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("manifest.json", json.dumps({"format": "iospr-backup"}))
            z.writestr("Logs/../../escape.txt", "x")
            z.writestr("Logs/a/../../escape2.txt", "x")
            z.writestr("Logs//etc/passwd", "x")
            z.writestr("Logs/ok phone/panic-full-ok.ips", "{}")
        r = b.import_data(evil)
        self.assertEqual(r["logs"], 1)
        data = os.path.dirname(self.core.logs_root())
        self.assertFalse(os.path.exists(os.path.join(data, "escape.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "escape.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.core.logs_root(), "ok phone", "panic-full-ok.ips")))


if __name__ == "__main__":
    unittest.main()
