# -*- coding: utf-8 -*-
"""Проверка окна на разных экранах: разрешение × плотность (масштаб Windows) × масштаб в программе.

Для каждого варианта запускается свой виртуальный экран (Xvfb) с «панелью задач» снизу.
Проверяется: главное окно и окна поверх него целиком в рабочей области (не под панелью задач),
навигация помещается, вкладки рисуются без ошибок. Скриншоты — в папку --out.

  python3 tools/screen_matrix.py --out /tmp/screens
Нужны: Linux, Xvfb, ImageMagick (import), Python с tkinter.
"""

import argparse
import json
import re
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKBAR = 48

# (ширина, высота, dpi): 96 = 100 %, 120 = 125 %, 144 = 150 %, 192 = 200 %, 288 = 300 %
SCREENS = [(1280, 720, 96), (1366, 768, 96), (1366, 768, 120), (1536, 864, 96), (1920, 1080, 96),
           (1920, 1080, 120), (1920, 1080, 144), (2560, 1440, 96), (2560, 1440, 144), (2560, 1600, 192),
           (3840, 2160, 192), (3840, 2160, 288)]


def contrast(c1, c2):
    """Контраст по WCAG двух цветов (r, g, b) в 16-битных значениях Tk."""
    def lum(c):
        out = []
        for v in c:
            v = v / 65535
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    a, b = sorted((lum(c1), lum(c2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def child(out, w, h, dpi, zoom, lang, theme="light"):
    """Один вариант (запускается в отдельном процессе на своём экране)."""
    sys.path.insert(0, os.path.join(ROOT, "app"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import screenshots as S
    home, logs = S.make_demo_home()
    hist = os.path.join(home, "Documents", "iOSPanicReader", "history.json")
    with open(hist, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("settings", {})["zoom"] = zoom
    data["settings"]["theme"] = theme
    with open(hist, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.environ.update(HOME=home, USERPROFILE=home, IOSPR_LANG=lang)
    import tkinter as tk
    import tkinter.font as tkfont
    import gui
    root = tk.Tk()
    app = gui.App(root)
    app.watcher = None
    area = (0, 0, w, h - TASKBAR)
    tag = f"{w}x{h}@{dpi}dpi_z{zoom}_{lang}_{theme}"
    problems = []
    dev = dict(udid=S.SERIAL, name="iPhone", product="iPhone14,5", model="iPhone 13", ios="18.6", build="22G86",
               serial=S.SERIAL, imei="356789012345678", is_iphone=True, battery_health=84,
               battery_mah="2700/3227 mAh", battery_cycles=512, dir=logs)

    def settle():
        for _ in range(6):
            root.update()
            time.sleep(0.08)

    def inside(win, name):
        """Окно вместе с рамкой и заголовком (их размер — как считает программа) в рабочей области."""
        win.update_idletasks()
        gw, gh, gx, gy = (int(v) for v in re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", win.geometry()).groups())
        dw, dh = app._deco(win)
        if gx < area[0] or gy < area[1] or gx + gw + dw > area[0] + area[2] or gy + gh + dh > area[1] + area[3]:
            problems.append(f"{name}: окно {gw}x{gh}+{gx}+{gy} (+рамка {dw}x{dh}) выходит за рабочую область {area}")

    def nav_fits():
        rw = root.winfo_width()
        if app.nav.winfo_reqwidth() > rw + 1:
            problems.append(f"навигация: нужно {app.nav.winfo_reqwidth()} px, а окно {rw} px — кнопки налезают")
        for k, b in app.nav_buttons.items():
            if not b.winfo_ismapped() or b.winfo_rootx() - root.winfo_rootx() + b.winfo_width() > rw + 1:
                problems.append(f"навигация: кнопка «{k}» не помещается")

    def audit(top, where):
        """Обрезанный текст, налезающие друг на друга элементы, слабый контраст."""
        seen = set()

        def rect(wd):
            return wd.winfo_rootx(), wd.winfo_rooty(), wd.winfo_width(), wd.winfo_height()

        def visible_box(wd):
            """Видимая область: пересечение с окном и со всеми прокручиваемыми холстами выше."""
            x, y, ww, hh = rect(wd)
            x2, y2 = x + ww, y + hh
            p = wd.master
            while p is not None:
                if isinstance(p, tk.Canvas) or p is top:
                    px_, py_, pw, ph = rect(p)
                    x, y, x2, y2 = max(x, px_), max(y, py_), min(x2, px_ + pw), min(y2, py_ + ph)
                p = p.master
            return x, y, x2, y2

        def walk(wd):
            for c in wd.winfo_children():
                if isinstance(c, tk.Toplevel) or not c.winfo_ismapped():
                    continue
                yield c
                yield from walk(c)

        texts = []
        for c in walk(top):
            cls = c.winfo_class()
            if cls not in ("Label", "Checkbutton", "Button", "Radiobutton"):
                continue
            try:
                text = c.cget("text")
            except tk.TclError:
                continue
            if not text or not text.strip():
                continue
            x, y, x2, y2 = visible_box(c)
            if x2 <= x or y2 <= y:
                continue                                  # прокручено за край — это нормально
            short = text.strip().replace("\n", " ")[:40]
            fx, fy, fw, fh = rect(c)
            # часть текста за краем окна или прокрутки по горизонтали
            if x2 - x < fw - 2 and (fx < x or fx + fw > x2):
                problems.append(f"{where}: «{short}» выходит за край ({fw} px, видно {x2 - x})")
            # сама надпись уже, чем нужно тексту
            wrap = 0
            try:
                wrap = int(str(c.cget("wraplength") or 0))
            except (tk.TclError, ValueError):
                pass
            if fw + 2 < c.winfo_reqwidth() and not wrap:
                problems.append(f"{where}: «{short}» обрезан по ширине ({fw} из {c.winfo_reqwidth()} px)")
            if fh + 2 < c.winfo_reqheight():
                problems.append(f"{where}: «{short}» обрезан по высоте ({fh} из {c.winfo_reqheight()} px)")
            # контраст
            try:
                fg, bg = c.cget("foreground"), c.cget("background")
                f = tkfont.Font(font=c.cget("font"))
                big = f.actual("size") >= 14 or (f.actual("weight") == "bold" and f.actual("size") >= 11)
                ratio = contrast(c.winfo_rgb(fg), c.winfo_rgb(bg))
                need = 3.0 if big or len(text.strip()) <= 2 else 4.5      # значки (●, ✓) — как графика
                if ratio < need and (fg, bg) not in seen:
                    seen.add((fg, bg))
                    problems.append(f"{where}: слабый контраст {ratio:.1f} (нужно {need}) у «{short}» {fg} на {bg}")
            except tk.TclError:
                pass
            texts.append((c, (x, y, x2, y2), short))
        # наложение надписей друг на друга (у разных, не вложенных элементов)
        for i in range(len(texts)):
            a, (ax1, ay1, ax2, ay2), at = texts[i]
            for j in range(i + 1, len(texts)):
                b, (bx1, by1, bx2, by2), bt = texts[j]
                ix, iy = min(ax2, bx2) - max(ax1, bx1), min(ay2, by2) - max(ay1, by1)
                if ix > 2 and iy > 2:
                    problems.append(f"{where}: «{at}» и «{bt}» налезают друг на друга")

    def snap(name):
        settle()
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+0+0", "+repage",
                        os.path.join(out, f"{tag}_{name}.png")], check=True)

    def run():
        try:
            settle()
            inside(root, "главное окно")
            app.events.put(("pulled", dict(dev)))
            settle()
            settle()
            nav_fits()
            audit(root, "Телефон")
            snap("1_phone")
            app.frames["phone"].canvas.yview_moveto(1)
            settle()
            audit(root, "Телефон (низ)")
            for tab in ("parts", "logs", "history", "kb"):
                app.show(tab)
                settle()
                if tab == "history":
                    kids = app.htree.get_children()
                    if kids:
                        app.htree.selection_set(kids[0])
                        app.show_phone_history()
                        settle()
                audit(root, {"parts": "Детали", "logs": "Все логи", "history": "История", "kb": "Поиск"}[tab])
            app.show("history")
            snap("2_history")
            app.show("phone")
            app.show_about()
            settle()
            settle()
            tops = [c for c in root.winfo_children() if isinstance(c, tk.Toplevel)]
            for t in tops:
                inside(t, "О программе")
                audit(t, "О программе")
            snap("3_about")
            for t in tops:
                t.destroy()
            # окно поверх, размер от главного: «Доступна новая версия»
            app.update_info = {"version": "9.9.9", "notes": "## Новое\n* пункт\n" * 8, "url": "", "asset": None}
            app.show_update_dialog()
            settle()
            for t in [c for c in root.winfo_children() if isinstance(c, tk.Toplevel)]:
                inside(t, "Доступна новая версия")
                audit(t, "Доступна новая версия")
            snap("4_update")
        except Exception as e:
            problems.append(f"ошибка: {e.__class__.__name__}: {e}")
        finally:
            print(json.dumps({"tag": tag, "problems": problems}, ensure_ascii=False))
            root.destroy()

    root.after(900, run)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="screens")
    ap.add_argument("--zooms", default="1.0")
    ap.add_argument("--langs", default="ru")
    ap.add_argument("--themes", default="light")
    ap.add_argument("--screens", help="только эти экраны, например 1366x768@120,1920x1080@96")
    ap.add_argument("--child", nargs=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.child:
        w, h, dpi = map(int, a.child[:3])
        return child(a.out, w, h, dpi, float(a.child[3]), a.child[4], a.child[5])
    bad = 0
    disp = 140
    screens = SCREENS
    if a.screens:
        screens = [tuple(int(v) for v in re.match(r"(\d+)x(\d+)@(\d+)", x).groups()) for x in a.screens.split(",")]
    for w, h, dpi in screens:
        for zoom in map(float, a.zooms.split(",")):
            for lang in a.langs.split(","):
                for theme in a.themes.split(","):
                    disp += 1
                    xv = subprocess.Popen(["Xvfb", f":{disp}", "-screen", "0", f"{w}x{h}x24", "-dpi", str(dpi)],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.2)
                    env = dict(os.environ, DISPLAY=f":{disp}", IOSPR_WORKAREA=f"0,0,{w},{h - TASKBAR}")
                    try:
                        r = subprocess.run([sys.executable, __file__, "--out", a.out, "--child", str(w), str(h),
                                            str(dpi), str(zoom), lang, theme], env=env, capture_output=True,
                                           text=True, timeout=240)
                        line = next((l for l in r.stdout.splitlines() if l.startswith("{")), None)
                        res = json.loads(line) if line else {"tag": f"{w}x{h}@{dpi}",
                                                             "problems": [r.stderr[-800:]]}
                    finally:
                        xv.terminate()
                    ok = not res["problems"]
                    bad += not ok
                    print(("✓ " if ok else "✗ ") + res["tag"] +
                          ("" if ok else "\n    " + "\n    ".join(res["problems"])), flush=True)
    print(f"\nс проблемами: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
