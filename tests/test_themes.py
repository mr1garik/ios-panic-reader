# -*- coding: utf-8 -*-
"""Читаемость во всех темах: контраст текста к фону по WCAG (4.5 для текста, 3 для значков)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import themes  # noqa: E402


def lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


class TestContrast(unittest.TestCase):
    def test_text_on_backgrounds(self):
        for name, p in themes.THEMES.items():
            for fg in ("text", "head", "muted", "blue", "red_text", "orange_text", "green_text"):
                for bg in ("bg", "card", "bar", "gray_bg", "stripe"):
                    with self.subTest(theme=name, fg=fg, bg=bg):
                        self.assertGreaterEqual(contrast(p[fg], p[bg]), 4.5)

    def test_level_cards_and_buttons(self):
        for name, p in themes.THEMES.items():
            for lvl in ("red", "orange", "green"):
                with self.subTest(theme=name, level=lvl):
                    self.assertGreaterEqual(contrast(p[lvl + "_text"], p[lvl + "_bg"]), 4.5)
            with self.subTest(theme=name, what="кнопка"):
                self.assertGreaterEqual(contrast(p["on_accent"], p["blue"]), 4.5)
                self.assertGreaterEqual(contrast(p["tip_fg"], p["tip_bg"]), 4.5)

    def test_icons(self):
        for name, p in themes.THEMES.items():
            for fg in ("gray", "red", "orange", "green"):
                with self.subTest(theme=name, fg=fg):
                    self.assertGreaterEqual(contrast(p[fg], p["card"]), 3.0)


if __name__ == "__main__":
    unittest.main()
