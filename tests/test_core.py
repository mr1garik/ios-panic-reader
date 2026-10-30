# -*- coding: utf-8 -*-
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core  # noqa: E402

SAMPLES = os.path.join(ROOT, "tests", "samples")


def load(*names):
    return [core.parse_log(os.path.join(SAMPLES, n)) for n in names]


class TestParse(unittest.TestCase):
    def test_thermalmonitord_panic(self):
        (p,) = load("panic-full-2026-10-01-120001.ips")
        self.assertTrue(p["is_panic"])
        self.assertEqual(p["model"], "iPhone 13")
        self.assertEqual(p["missing_sensors"], ["mic1", "prs0"])
        self.assertEqual(core.panic_part(p), "charge_flex")

    def test_sep_panic(self):
        (p,) = load("panic-full-old-sep.ips")
        self.assertEqual(p["model"], "iPhone X")
        self.assertEqual(core.panic_part(p), "biometry")

    def test_app_crash(self):
        (p,) = load("Telegram-2026-10-02-101010.ips")
        self.assertFalse(p["is_panic"])
        self.assertIn("EXC_BAD_ACCESS", p["exception"])
        self.assertEqual(p["process"], "Telegram")


class TestVerdict(unittest.TestCase):
    def test_repeated_panics_are_red(self):
        logs = [core.parse_log(f) for f in core.collect_files([SAMPLES])]
        problems = core.build_verdict(logs)
        self.assertEqual(problems[0]["part"], "charge_flex")
        self.assertEqual(problems[0]["level"], "red")

    def test_worn_battery(self):
        problems = core.build_verdict([], {"battery_health": 75, "battery_cycles": 900,
                                           "is_iphone": True, "imei": "1"})
        self.assertEqual([p["part"] for p in problems], ["battery"])

    def test_healthy_phone(self):
        self.assertEqual(core.build_verdict([], {"battery_health": 95, "is_iphone": True, "imei": "1"}), [])

    def test_parts_table(self):
        logs = [core.parse_log(f) for f in core.collect_files([SAMPLES])]
        rows = {r[0]: r for r in core.parts_table(logs)}
        self.assertEqual(rows[core.PART_NAMES["charge_flex"]][3], "red")


class TestTime(unittest.TestCase):
    def test_panics_by_day(self):
        from datetime import datetime
        logs = [core.parse_log(f) for f in core.collect_files([SAMPLES])]
        days = core.panics_by_day(logs, 3, datetime(2026, 10, 2))
        self.assertEqual(len(days), 3)
        self.assertEqual(sum(n for _, n in days), 3)

    def test_logs_since_repair(self):
        from datetime import datetime
        logs = [core.parse_log(f) for f in core.collect_files([SAMPLES])]
        self.assertEqual(core.logs_since(logs, datetime(2030, 1, 1)), [])
        self.assertEqual(len(core.logs_since(logs, datetime(2000, 1, 1))), len(logs))


class TestHistory(unittest.TestCase):
    def test_visits_and_repairs(self):
        import tempfile
        from history import History
        path = os.path.join(tempfile.mkdtemp(), "h.json")
        h = History(path)
        dev = {"serial": "ABC", "model": "iPhone 13", "battery_health": 90}
        self.assertIsNone(h.add_visit(dev, [], []))
        h.add_repair(dev, "шлейф")
        prev = History(path).add_visit(dev, [], [])
        self.assertEqual(prev["battery"], 90)
        self.assertEqual(History(path).last_repair("ABC")[1], "шлейф")


class TestPdf(unittest.TestCase):
    def test_build_pdf(self):
        import tempfile
        import report_pdf
        if not report_pdf.available():
            self.skipTest("нет reportlab или шрифта")
        logs = [core.parse_log(f) for f in core.collect_files([SAMPLES])]
        path = os.path.join(tempfile.mkdtemp(), "r.pdf")
        report_pdf.build_pdf(path, logs, None, [("Устройство", "тест")], "Мастерская")
        with open(path, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")


if __name__ == "__main__":
    unittest.main()
