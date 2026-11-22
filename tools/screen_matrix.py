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


def child(out, w, h, dpi, zoom, lang):
    """Один вариант (запускается в отдельном процессе на своём экране)."""
    sys.path.insert(0, os.path.join(ROOT, "app"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import screenshots as S
    home, logs = S.make_demo_home()
    hist = os.path.join(home, "Documents", "iOSPanicReader", "history.json")
    with open(hist, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("settings", {})["zoom"] = zoom
    with open(hist, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.environ.update(HOME=home, USERPROFILE=home, IOSPR_LANG=lang)
    import tkinter as tk
    import gui
    root = tk.Tk()
    app = gui.App(root)
    app.watcher = None
    area = (0, 0, w, h - TASKBAR)
    tag = f"{w}x{h}@{dpi}dpi_z{zoom}_{lang}"
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
            snap("1_phone")
            for tab in ("parts", "logs", "history", "kb"):
                app.show(tab)
                settle()
            app.show("history")
            snap("2_history")
            app.show("phone")
            app.show_about()
            settle()
            settle()
            tops = [c for c in root.winfo_children() if isinstance(c, tk.Toplevel)]
            for t in tops:
                inside(t, "О программе")
            snap("3_about")
            for t in tops:
                t.destroy()
            # окно поверх, размер от главного: «Доступна новая версия»
            app.update_info = {"version": "9.9.9", "notes": "## Новое\n* пункт\n" * 8, "url": "", "asset": None}
            app.show_update_dialog()
            settle()
            for t in [c for c in root.winfo_children() if isinstance(c, tk.Toplevel)]:
                inside(t, "Доступна новая версия")
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
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--child", nargs=5)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.child:
        w, h, dpi = map(int, a.child[:3])
        return child(a.out, w, h, dpi, float(a.child[3]), a.child[4])
    bad = 0
    disp = 140
    for w, h, dpi in SCREENS:
        for zoom in map(float, a.zooms.split(",")):
            disp += 1
            xv = subprocess.Popen(["Xvfb", f":{disp}", "-screen", "0", f"{w}x{h}x24", "-dpi", str(dpi)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.2)
            env = dict(os.environ, DISPLAY=f":{disp}", IOSPR_WORKAREA=f"0,0,{w},{h - TASKBAR}")
            try:
                r = subprocess.run([sys.executable, __file__, "--out", a.out, "--child", str(w), str(h), str(dpi),
                                    str(zoom), a.lang], env=env, capture_output=True, text=True, timeout=180)
                line = next((l for l in r.stdout.splitlines() if l.startswith("{")), None)
                res = json.loads(line) if line else {"tag": f"{w}x{h}@{dpi}", "problems": [r.stderr[-800:]]}
            finally:
                xv.terminate()
            ok = not res["problems"]
            bad += not ok
            print(("✓ " if ok else "✗ ") + res["tag"] + ("" if ok else "\n    " + "\n    ".join(res["problems"])))
    print(f"\nс проблемами: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
