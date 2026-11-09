# -*- coding: utf-8 -*-
"""Скриншоты и GIF для README на демонстрационных данных (вымышленный телефон и логи).

Нужны: Linux, Xvfb, ImageMagick (import, convert), Python с tkinter.
  Xvfb :99 -screen 0 1600x1000x24 &
  DISPLAY=:99 python3 tools/screenshots.py            # все языки → docs/screenshots/<язык>/
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "screenshots")
W, H = 1280, 820
SERIAL = "F17DEMO0000"

PANIC_3MIN = ("panic(cpu 4 caller 0xfffffff01b2c8a10): userspace watchdog timeout: no successful checkins from "
              "com.apple.thermalmonitord in 180 seconds\\nservice returned not alive with context : "
              "is_alive_func returned unhealthy : current menu: Missing sensor(s): mic1 prs0 \\n"
              "Debugger message: panic\\nOS version: 22G86")
PANIC_SEP = "panic(cpu 1 caller 0xfffffff0071a3f8c): SEP Panic: :sks /sks : 0x0001a3a1 0x0001a1d3"


def make_demo_home():
    home = tempfile.mkdtemp(prefix="iospr-demo-")
    data = os.path.join(home, "Documents", "iOSPanicReader")
    logs = os.path.join(data, "Logs", f"iPhone 13_{SERIAL}")
    os.makedirs(logs)
    now = datetime.now().replace(microsecond=0)

    def ips(name, header, body):
        with open(os.path.join(logs, name), "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n" + body)

    n = 0
    # серия паник «каждые 3 минуты» за последние две недели, чаще ближе к сегодняшнему дню
    for days_ago, count in ((13, 1), (9, 2), (6, 3), (4, 2), (2, 5), (1, 4)):
        for k in range(count):
            t = now - timedelta(days=days_ago, minutes=3 * k)
            stamp = t.strftime("%Y-%m-%d %H:%M:%S.00 +0300")
            n += 1
            ips(f"panic-full-{t:%Y-%m-%d-%H%M%S}.000.ips",
                {"bug_type": "210", "timestamp": stamp, "os_version": "iPhone OS 18.6 (22G86)"},
                '{"build":"iPhone OS 18.6 (22G86)","product":"iPhone14,5","panicString":"%s","date":"%s"}'
                % (PANIC_3MIN, stamp))
    t = now - timedelta(days=20)
    ips(f"panic-full-{t:%Y-%m-%d-%H%M%S}.000.ips",
        {"bug_type": "210", "timestamp": t.strftime("%Y-%m-%d %H:%M:%S.00 +0300"), "os_version": "iPhone OS 18.5 (22F76)"},
        json.dumps({"product": "iPhone14,5", "panicString": PANIC_SEP}))
    for app, days_ago in (("Telegram", 3), ("Instagram", 5), ("Telegram", 8)):
        t = now - timedelta(days=days_ago, hours=2)
        ips(f"{app}-{t:%Y-%m-%d-%H%M%S}.ips",
            {"app_name": app, "bug_type": "309", "timestamp": t.strftime("%Y-%m-%d %H:%M:%S.00 +0300"),
             "os_version": "iPhone OS 18.6 (22G86)", "name": app},
            json.dumps({"procName": app, "modelCode": "iPhone14,5",
                        "exception": {"type": "EXC_BAD_ACCESS", "signal": "SIGSEGV", "codes": "0x1"}}))
    for days_ago in (1, 4, 7, 10):
        t = now - timedelta(days=days_ago, hours=5)
        ips(f"JetsamEvent-{t:%Y-%m-%d-%H%M%S}.ips",
            {"bug_type": "298", "timestamp": t.strftime("%Y-%m-%d %H:%M:%S.00 +0300"),
             "os_version": "iPhone OS 18.6 (22G86)"}, '{"product":"iPhone14,5"}')

    # история: этот телефон уже был, плюс ещё пара телефонов
    def visit(d, problems, level, bat, panics, ios="18.6"):
        return {"date": (now - timedelta(days=d)).strftime("%Y-%m-%d %H:%M:%S"), "ios": ios, "battery": bat,
                "cycles": None, "panics": panics, "problems": problems, "level": level}
    history = {"settings": {"workshop": "Phone Lab", "auto_update": False}, "phones": {
        SERIAL: {"model": "iPhone 13", "product": "iPhone14,5", "serial": SERIAL, "imei": "356789012345678",
                 "note": "", "first_seen": (now - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S"),
                 "repairs": [], "visits": [visit(40, [], "green", 91, 0, "18.5")]},
        "DX3DEMO0001": {"model": "iPhone 11", "product": "iPhone12,1", "serial": "DX3DEMO0001",
                        "note": "", "repairs": [{"date": (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
                                                 "note": "battery"}],
                        "visits": [visit(9, ["Battery"], "red", 71, 4), visit(5, [], "green", 100, 0)]},
        "G6TDEMO0002": {"model": "iPhone 15 Pro", "product": "iPhone16,1", "serial": "G6TDEMO0002",
                        "note": "", "repairs": [], "visits": [visit(2, [], "green", 96, 0, "26.0")]},
    }}
    with open(os.path.join(data, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)
    return home, logs


def frame(src, dst):
    """Скругление углов, тонкая рамка и тень — чтобы скриншот смотрелся как окно."""
    w, h = subprocess.run(["identify", "-format", "%w %h", src], capture_output=True, text=True,
                          check=True).stdout.split()
    mask = f"roundrectangle 0,0,{int(w) - 1},{int(h) - 1},14,14"
    rounded = dst + ".tmp.png"
    subprocess.run(["convert", src, "-alpha", "set",
                    "(", "-size", f"{w}x{h}", "xc:none", "-fill", "white", "-draw", mask, ")",
                    "-compose", "DstIn", "-composite",
                    "-fill", "none", "-stroke", "#d0d7e1", "-strokewidth", "1", "-draw", mask, rounded], check=True)
    subprocess.run(["convert", rounded,
                    "(", "+clone", "-background", "#0f172a", "-shadow", "30x14+0+10", ")",
                    "+swap", "-background", "none", "-layers", "merge", "+repage", dst], check=True)
    os.remove(rounded)


def shoot(lang):
    home, logs = make_demo_home()
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    os.environ["IOSPR_LANG"] = lang
    sys.path.insert(0, ROOT)
    import tkinter as tk
    import gui
    import core

    raw_dir = tempfile.mkdtemp(prefix="iospr-raw-")
    out_dir = os.path.join(OUT, lang)
    os.makedirs(out_dir, exist_ok=True)
    root = tk.Tk()
    gui.set_window_icon(root)
    app = gui.App(root)
    app.watcher = object()          # чтобы показывались кнопки, как с подключённым телефоном
    root.geometry(f"{W}x{H}+0+0")
    dev = dict(udid=SERIAL, name="iPhone", product="iPhone14,5", model="iPhone 13", ios="18.6", build="22G86",
               serial=SERIAL, imei="356789012345678", is_iphone=True, baseband="3.01.02", hw_model="D17AP",
               battery_health=84, battery_mah="2700/3227 mAh", battery_cycles=512, battery_serial="F5D2DEMO",
               dir=logs)
    gif = []

    def snap(name, keep=True, for_gif=True):
        for _i in range(8):
            root.update()
            time.sleep(0.12)
        app.status.set(app.status.get().replace(os.path.join(home, "Documents"), "~/Documents"))
        root.update()
        raw = os.path.join(raw_dir, name + ".png")
        subprocess.run(["import", "-window", "root", "-crop", f"{W}x{H}+0+0", "+repage", raw], check=True)
        if keep:
            frame(raw, os.path.join(out_dir, name + ".png"))
        if for_gif:
            gif.append(raw)

    def phone(state):
        app.phone_state = state
        app.render_phone()
        app.show("phone")

    steps = []
    steps.append(lambda: (phone("wait"), snap("1_wait")))
    steps.append(lambda: (phone("trust"), snap("2_trust", keep=False)))
    steps.append(lambda: (setattr(app, "dev", dict(dev)), phone("reading"), snap("3_reading", keep=False)))
    steps.append(lambda: app.events.put(("pulled", dict(dev))))
    steps.append(lambda: snap("4_result"))
    steps.append(lambda: (app.frames["phone"].canvas.yview_moveto(1), snap("5_result_chart")))
    steps.append(lambda: (app.open_part_logs("charge_flex"), snap("6_logs")))
    steps.append(lambda: (app._clear_part_filter(), app.show("parts"), snap("7_parts")))
    steps.append(lambda: (app.show("history"), snap("8_history")))
    steps.append(lambda: (app.show("kb"), app.search_scope.set("all"), app.kb_q.set("mic1")))
    steps.append(lambda: snap("9_search"))
    steps.append(lambda: (app.kb_q.set("4013")))
    steps.append(lambda: snap("10_search_code", for_gif=False))

    def repair():
        app.history.add_repair(app.dev, "charging flex" if lang == "en" else
                               ("шлейф заряджання" if lang == "uk" else "заменён шлейф зарядки"))
        app.events.put(("pulled", dict(dev)))
    steps.append(repair)
    steps.append(lambda: snap("11_after_repair"))

    def finish():
        root.destroy()

    def run(i=0):
        if i < len(steps):
            steps[i]()
            root.after(900, lambda: run(i + 1))
        else:
            finish()
    root.after(1000, run)
    root.mainloop()

    # PDF-отчёт, первая страница
    import report_pdf
    if report_pdf.available():
        pdf = os.path.join(raw_dir, "report.pdf")
        lg = [core.parse_log(f) for f in core.collect_files([logs])]
        report_pdf.build_pdf(pdf, lg, dev, [("Model", "iPhone 13 (iPhone14,5)"), ("iOS", "18.6 (22G86)"),
                                           ("Serial", SERIAL)], "Phone Lab")
        subprocess.run(["pdftoppm", "-png", "-r", "70", "-f", "1", "-l", "1", "-singlefile", pdf,
                        os.path.join(raw_dir, "pdf")], check=True)
        frame(os.path.join(raw_dir, "pdf.png"), os.path.join(out_dir, "12_pdf.png"))

    # GIF: уменьшаем, держим каждый кадр ~1.8 с
    small = []
    for p in gif:
        s = p.replace(".png", "_s.png")
        subprocess.run(["convert", p, "-resize", "960x", s], check=True)
        small.append(s)
    subprocess.run(["convert", "-delay", "180", "-loop", "0"] + small +
                   ["-fuzz", "2%", "-layers", "OptimizePlus", "-colors", "160",
                    os.path.join(out_dir, "demo.gif")], check=True)
    shutil.rmtree(raw_dir, ignore_errors=True)
    shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    langs = sys.argv[1:] or ["ru", "en", "uk"]
    for lang in langs:
        # каждый язык — отдельный процесс: язык выбирается при загрузке модулей
        if len(langs) > 1:
            subprocess.run([sys.executable, __file__, lang], check=True)
        else:
            shoot(lang)
    print("готово:", OUT)
