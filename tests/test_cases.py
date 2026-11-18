# -*- coding: utf-8 -*-
"""Реальные случаи с известной поломкой (tests/cases): программа должна назвать нужную деталь первой."""
import os
import sys
import unittest

os.environ["IOSPR_LANG"] = "ru"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_cases  # noqa: E402
import core  # noqa: E402


class TestRealCases(unittest.TestCase):
    def test_cases(self):
        for folder in check_cases.all_cases():
            with self.subTest(case=os.path.basename(folder)):
                case, top, good, found = check_cases.check_case(folder)
                self.assertTrue(good, f"ждали {case['expect']}, получили {top} (все: {found})")


class TestSensorWhere(unittest.TestCase):
    def test_connector_by_model(self):
        w = "Шлейф зарядки (Lightning / USB-C) с нижним микрофоном."
        self.assertIn("(Lightning)", core.sensor_where(w, "iPhone12,1"))      # iPhone 11
        self.assertIn("(USB-C)", core.sensor_where(w, "iPhone16,1"))          # iPhone 15 Pro
        self.assertEqual(core.sensor_where(w, ""), w)

    def test_ipad_gets_warning(self):
        w = core.sensor_where("Шлейф зарядки.", "iPad6,7")
        self.assertIn("iPad Pro 12.9", w)
        self.assertIn("сверяйтесь со схемой", w)


if __name__ == "__main__":
    unittest.main()
