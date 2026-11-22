# -*- coding: utf-8 -*-
"""Рабочая область экрана и размещение окон так, чтобы они не залезали под панель задач Windows,
строку меню и Dock на Mac, и помещались на маленьких экранах.

Рабочая область — прямоугольник (x, y, ширина, высота) без панели задач / Dock.
Функции fit_* — чистые (без Tk), их проверяют тесты.
"""

import os
import subprocess
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

_mac_cache = None


def _win_area(point=None, hwnd=None):
    """Windows: рабочая область монитора, где точка/окно (без панели задач). None — монитор не найден."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    mon = None
    if hwnd:
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)            # ближайший
    elif point is not None:
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        mon = user32.MonitorFromPoint(wintypes.POINT(int(point[0]), int(point[1])), 0)   # 0 — нет монитора
        if not mon:
            return None
    if not mon:
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        mon = user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)            # основной
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    r = info.rcWork
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _mac_area():
    """Mac: видимая часть главного экрана (без строки меню и Dock) через Cocoa из osascript."""
    global _mac_cache
    if _mac_cache is None:
        js = ("ObjC.import('AppKit'); var s = $.NSScreen.mainScreen; var f = s.frame; var v = s.visibleFrame;"
              "[f.size.height, v.origin.x, v.origin.y, v.size.width, v.size.height].join(' ')")
        try:
            out = subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True,
                                 text=True, timeout=4).stdout.split()
            fh, vx, vy, vw, vh = (float(x) for x in out)
            _mac_cache = (int(vx), int(fh - (vy + vh)), int(vw), int(vh))   # Cocoa считает y снизу
        except Exception:
            _mac_cache = False
    return _mac_cache or None


def work_area(root, point=None, window=None):
    """Рабочая область для окна (или точки, например сохранённого места окна).
    point на несуществующем мониторе → None (окно надо ставить на основной экран)."""
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    test = os.environ.get("IOSPR_WORKAREA")        # только для тестов: «x,y,ширина,высота»
    if test:
        area = tuple(int(v) for v in test.split(","))
        if point is not None and not (area[0] <= point[0] < area[0] + area[2] and
                                      area[1] <= point[1] < area[1] + area[3]):
            return None
        return area
    try:
        if IS_WIN:
            hwnd = None
            if window is not None and window.winfo_ismapped():
                hwnd = int(window.wm_frame(), 16)
            area = _win_area(point, hwnd)
            if area is None and point is not None:
                return None
            if area:
                return area
        elif IS_MAC:
            area = _mac_area()
            if area:
                return area
            return 0, 25, sw, sh - 25 - 80        # строка меню и Dock по умолчанию
    except Exception:
        pass
    if point is not None and not (0 <= point[0] < sw and 0 <= point[1] < sh):
        return None
    return 0, 0, sw, sh


def fit_main(area, want_w, want_h, deco, saved=None, min_w=0, min_h=0):
    """Главное окно: (ширина, высота, x, y) внутренней области. deco = (рамка слева+справа, заголовок+рамка снизу).
    saved — прошлое место (w, h, x, y), если оно на этом экране; если не влезает — подгоняется."""
    ax, ay, aw, ah = area
    dw, dh = deco
    max_w, max_h = aw - dw, ah - dh
    if saved:
        w, h, x, y = saved
    else:
        # на больших экранах — с полями вокруг, на маленьких — во всю рабочую область
        w = min(want_w, int(aw * 0.9) if aw >= 1600 else max_w)
        h = min(want_h, int(ah * 0.9) if ah >= 1000 else max_h)
        x = y = None
    w = max(min(w, max_w), min(min_w, max_w))
    h = max(min(h, max_h), min(min_h, max_h))
    if x is None:
        x = ax + (aw - (w + dw)) // 2
        y = ay + max(0, (ah - (h + dh)) // 3)
    # целиком внутри рабочей области: правый и нижний край не под панелью задач
    x = min(max(x, ax), ax + aw - (w + dw))
    y = min(max(y, ay), ay + ah - (h + dh))
    return w, h, x, y


def fit_popup(area, parent, want_w, want_h, deco):
    """Дополнительное окно: по центру главного, но не больше и не за краями рабочей области."""
    ax, ay, aw, ah = area
    px_, py_, pw, ph = parent
    dw, dh = deco
    w, h = min(want_w, aw - dw), min(want_h, ah - dh)
    x = px_ + (pw - w) // 2
    y = py_ + max(0, (ph - h) // 3)
    x = min(max(x, ax), ax + aw - (w + dw))
    y = min(max(y, ay), ay + ah - (h + dh))
    return w, h, x, y
