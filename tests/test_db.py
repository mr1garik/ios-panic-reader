# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import unittest

os.environ["IOSPR_LANG"] = "ru"   # тесты проверяют русский текст
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core  # noqa: E402
import knowledge_base as kb  # noqa: E402

REQUIRED = ("id", "cat", "title", "patterns", "node", "symptoms", "cause", "fix")


class TestDatabase(unittest.TestCase):
    def test_file_is_valid_json(self):
        with open(os.path.join(ROOT, "errors_db.json"), encoding="utf-8") as f:
            db = json.load(f)
        self.assertGreaterEqual(db["meta"]["version"], 2)

    def test_entries_complete_and_unique(self):
        ids = [e["id"] for e in kb.KB]
        self.assertEqual(len(ids), len(set(ids)), "повторяются id")
        for e in kb.KB:
            for k in REQUIRED:
                self.assertIn(k, e, f"{e.get('id')}: нет поля {k}")
            self.assertIn(e["cat"], kb.CATEGORIES, e["id"])
            for p in e["patterns"]:
                re.compile(p)

    def test_sources_resolve(self):
        for e in kb.KB:
            for s in e.get("sources", []):
                self.assertIn(s, kb.SOURCES, f"{e['id']}: неизвестный источник {s}")
        for b in kb.I2C_BUSES:
            self.assertIn(b["source"], kb.SOURCES)
            for m in b["models"]:
                self.assertIn(m, kb.PRODUCTS)


class TestSearch(unittest.TestCase):
    def titles(self, q):
        return [r[2] for r in core.search_db(q)]

    def test_by_code(self):
        self.assertTrue(any("4013" in t for t in self.titles("4013")))

    def test_by_russian_words(self):
        self.assertTrue(any("3 минут" in t for t in self.titles("перезагружается 3 минуты")))

    def test_sensor(self):
        self.assertIn("sensor", [r[0] for r in core.search_db("mic1")])

    def test_panic_text_finds_entry_first(self):
        r = core.search_db("panic(cpu 0 caller 0x1): SEP Panic: :sks /sks : 0x0001")
        self.assertEqual(kb.KB[r[0][1]]["id"], "sep")

    def test_search_logs(self):
        logs = [core.parse_log(f) for f in core.collect_files([os.path.join(ROOT, "tests", "samples")])]
        self.assertEqual(len(core.search_logs(logs, "mic1")), 3)
        self.assertEqual(len(core.search_logs(logs, "telegram")), 1)


class TestPasted(unittest.TestCase):
    def test_bare_panic_string_with_model(self):
        info = core.parse_pasted("panic(cpu 2 caller 0xfff): i2c3::_checkBusStatus SCL is stuck low", "iPhone12,5")
        self.assertEqual(info["findings"][0][0]["id"], "i2c_stuck")
        self.assertTrue(core.i2c_hints(info))
        self.assertIn("ШИНА I2C3", core.build_report(info))

    def test_full_ips_pasted(self):
        with open(os.path.join(ROOT, "tests", "samples", "panic-full-2026-10-01-120001.ips"), encoding="utf-8") as f:
            info = core.parse_pasted(f.read())
        self.assertEqual(info["missing_sensors"], ["mic1", "prs0"])


class TestModels(unittest.TestCase):
    def test_family(self):
        self.assertEqual(core.model_family("iPhone10,6"), 10)      # X
        self.assertEqual(core.model_family("iPhone12,8"), 8)       # SE 2 — как iPhone 8
        self.assertEqual(core.model_family("iPhone14,5"), 13)

    def test_profile(self):
        p = core.model_profile("iPhone14,5")
        facts = dict(p["facts"])
        self.assertEqual(facts["Биометрия"], "Face ID")
        self.assertEqual(facts["Разъём"], "Lightning")
        self.assertIn("prs0", [k for k, _d in p["sensors"]])
        se = core.model_profile("iPhone12,8")
        self.assertEqual(dict(se["facts"])["Биометрия"], "Touch ID")
        self.assertNotIn("faceid", [e["id"] for e in se["entries"]])
        self.assertTrue(se["buses"])
        self.assertEqual(dict(core.model_profile("iPhone16,1")["facts"])["Разъём"], "USB-C")

    def test_applies(self):
        faceid = next(e for e in kb.KB if e["id"] == "faceid")
        self.assertTrue(core.applies(faceid, "iPhone14,5"))
        self.assertFalse(core.applies(faceid, "iPhone9,1"))
        uwb = next(e for e in kb.KB if e["id"] == "uwb")
        self.assertFalse(core.applies(uwb, "iPhone17,5"))           # у 16e нет U1


class TestAnonymize(unittest.TestCase):
    def test_private_data_removed(self):
        s = core.anonymize("imei 356789012345678 udid 00008110-001A2B3C4D5E801E "
                           "SerialNumber: F17XX12AB a@b.com /Users/ivan/x C:\\Users\\ivan\\y")
        for secret in ("356789012345678", "001A2B3C4D5E801E", "F17XX12AB", "a@b.com", "ivan"):
            self.assertNotIn(secret, s)

    def test_report(self):
        logs = [core.parse_log(f) for f in core.collect_files([os.path.join(ROOT, "tests", "samples")])]
        p = next(l for l in logs if l["missing_sensors"])
        r = core.report_for_database(p)
        self.assertIn("mic1", r)
        self.assertNotIn("panic-full", r)          # имени файла нет


if __name__ == "__main__":
    unittest.main()
