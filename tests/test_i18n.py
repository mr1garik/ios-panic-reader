# -*- coding: utf-8 -*-
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tools_i18n_keys  # noqa: E402

PH = re.compile(r"\{\d+\}")


class TestTranslations(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "translations.json"), encoding="utf-8") as f:
            self.tr = json.load(f)

    def test_every_phrase_translated(self):
        missing = [k for k in tools_i18n_keys.all_keys()
                   if not (self.tr.get(k, {}).get("en") and self.tr.get(k, {}).get("uk"))]
        self.assertEqual(missing, [], "нет перевода")

    def test_placeholders_and_newlines_kept(self):
        for k, v in self.tr.items():
            for lang in ("en", "uk"):
                self.assertEqual(sorted(PH.findall(k)), sorted(PH.findall(v[lang])), f"{lang}: {k!r}")
                self.assertEqual(k.endswith("\n"), v[lang].endswith("\n"), f"{lang}: {k!r}")
                v[lang].format(*range(10))   # шаблон должен форматироваться

    def test_database_translated(self):
        with open(os.path.join(ROOT, "errors_db.json"), encoding="utf-8") as f:
            db = json.load(f)
        items = db["entries"] + list(db["sensors"].values()) + db["i2c_buses"]
        for it in items:
            for lang in ("en", "uk"):
                self.assertIn(lang, it.get("i18n", {}), it.get("id") or it.get("name") or it.get("bus"))


class TestLanguageSwitch(unittest.TestCase):
    def run_cli(self, lang):
        env = dict(os.environ, IOSPR_LANG=lang, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "ios_panic_reader.py"), "--cli",
                            os.path.join(ROOT, "tests", "samples")], env=env, capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_english(self):
        out = self.run_cli("en")
        self.assertIn("PHONE SUMMARY", out)
        self.assertIn("Charging flex", out)
        self.assertNotIn("СВОДКА", out)

    def test_ukrainian(self):
        out = self.run_cli("uk")
        self.assertIn("ЗВЕДЕННЯ ПО ТЕЛЕФОНУ", out)
        self.assertIn("Шлейф заряджання", out)

    def test_russian(self):
        self.assertIn("СВОДКА ПО ТЕЛЕФОНУ", self.run_cli("ru"))


if __name__ == "__main__":
    unittest.main()
