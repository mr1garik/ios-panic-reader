# -*- coding: utf-8 -*-
"""Новый интерфейс: данные для каждого экрана и что странице видно только нужное."""
import json
import os
import sys
import tempfile
import unittest

os.environ["IOSPR_LANG"] = "ru"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
SAMPLES = os.path.join(ROOT, "tests", "samples")


class TestBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        os.environ["HOME"] = os.environ["USERPROFILE"] = cls.home
        import webui
        cls.webui = webui
        cls.b = webui.Backend(with_device=False)
        cls.b.load_paths([SAMPLES])

    def test_everything_is_json(self):
        b = self.b
        for res in (b.app_info(), b.phone(), b.parts(), b.logs_list(), b.history_list(), b.kb("mic1"), b.poll()):
            json.dumps(res, ensure_ascii=False)

    def test_phone_screen(self):
        d = self.b.phone()
        self.assertEqual(d["state"], "result")
        self.assertTrue(d["problems"])
        top = d["problems"][0]
        self.assertTrue(top["fix"] and top["board"])
        self.assertTrue(d["probability"])
        self.assertTrue(all(0 < p["pct"] <= 100 for p in d["probability"]))
        self.assertEqual(sum(g["n"] for g in d["groups"]) <= len(self.b.logs), True)

    def test_logs_and_detail(self):
        items = self.b.logs_list(only_panic=True)["items"]
        self.assertTrue(items)
        det = self.b.log_detail(items[0]["id"])
        self.assertTrue(det["parts"] and det["raw"])
        self.assertNotIn(os.path.basename(det.get("suggest", "")), ("",))

    def test_kb_search(self):
        groups = self.b.kb("mic1")
        ids = [i["id"] for g in groups for i in g["items"]]
        self.assertTrue(ids)
        self.assertTrue(self.b.kb_item(ids[0])["parts"])
        prof = self.b.kb("", "Все", "base", "iPhone 13")
        self.assertTrue(prof[0]["items"][0]["id"].startswith("model:"))

    def test_page_sees_only_actions(self):
        api = self.webui.js_api(self.b)
        names = {n for n in dir(api) if not n.startswith("_")}
        self.assertIn("phone", names)
        for hidden in ("window", "history", "watcher", "events", "logs"):
            self.assertNotIn(hidden, names)

    def test_ui_strings_translated(self):
        t = self.b.app_info()["t"]
        self.assertTrue(all(isinstance(v, str) and v for v in t.values()))


if __name__ == "__main__":
    unittest.main()
