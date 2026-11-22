# -*- coding: utf-8 -*-
"""Окна на разных экранах: не под панелью задач, не за краями, на маленьких экранах — меньше."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import screen  # noqa: E402

DECO_WIN = (16, 48)      # рамка и заголовок Windows при 100 %


def inside(area, w, h, x, y, deco):
    ax, ay, aw, ah = area
    return x >= ax and y >= ay and x + w + deco[0] <= ax + aw and y + h + deco[1] <= ay + ah


class TestMainWindow(unittest.TestCase):
    def test_small_laptop_with_taskbar(self):
        # 1366×768 при 125 %: программа хочет 1500×1025, а над панелью задач только 720 по высоте
        area = (0, 0, 1366, 720)
        w, h, x, y = screen.fit_main(area, 1500, 1025, (20, 60))
        self.assertTrue(inside(area, w, h, x, y, (20, 60)))
        self.assertLessEqual(h, 720 - 60)

    def test_taskbar_on_top_or_left(self):
        for area in ((0, 40, 1920, 1040), (60, 0, 1860, 1080)):
            w, h, x, y = screen.fit_main(area, 1200, 820, DECO_WIN)
            self.assertTrue(inside(area, w, h, x, y, DECO_WIN), area)

    def test_saved_window_under_taskbar_is_moved_up(self):
        area = (0, 0, 1920, 1032)
        w, h, x, y = screen.fit_main(area, 1200, 820, DECO_WIN, saved=(1200, 820, 300, 400))
        self.assertEqual((w, h), (1200, 820))           # размер сохранили
        self.assertTrue(inside(area, w, h, x, y, DECO_WIN))

    def test_saved_window_bigger_than_new_screen(self):
        area = (0, 0, 1280, 672)                         # перенесли с большого монитора на ноутбук
        w, h, x, y = screen.fit_main(area, 1200, 820, DECO_WIN, saved=(2400, 1300, 100, 50))
        self.assertTrue(inside(area, w, h, x, y, DECO_WIN))

    def test_second_monitor_coordinates(self):
        area = (1920, 0, 2560, 1400)                     # монитор справа от основного
        w, h, x, y = screen.fit_main(area, 1200, 820, DECO_WIN, saved=(1200, 820, 2100, 100))
        self.assertEqual((x, y), (2100, 100))

    def test_big_screen_keeps_comfortable_size(self):
        w, h, x, y = screen.fit_main((0, 0, 3840, 2112), 2400, 1640, (32, 96))
        self.assertEqual((w, h), (2400, 1640))


class TestPopup(unittest.TestCase):
    def test_tall_popup_is_cut_to_work_area(self):
        area = (0, 0, 1366, 720)
        w, h, x, y = screen.fit_popup(area, (0, 0, 1366, 700), 600, 1100, DECO_WIN)
        self.assertTrue(inside(area, w, h, x, y, DECO_WIN))
        self.assertEqual(h, 720 - 48)

    def test_popup_centered_on_main_window(self):
        w, h, x, y = screen.fit_popup((0, 0, 1920, 1032), (200, 100, 1200, 800), 400, 300, DECO_WIN)
        self.assertEqual(x, 200 + (1200 - 400) // 2)


if __name__ == "__main__":
    unittest.main()
