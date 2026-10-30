# -*- coding: utf-8 -*-
"""Окно программы: Телефон · Детали · Все логи · Справочник ошибок."""

import os
import queue
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

import core
from core import (APP_TITLE, build_report, build_summary, build_verdict, collect_files,
                  logs_root, main_cause, parse_log, parts_table)
from device import DeviceWatcher, device_support
from knowledge_base import CATEGORIES, KB, PRODUCTS, SENSORS

# ---------------------------------------------------------------------------
# Цвета и шрифты
# ---------------------------------------------------------------------------
C = dict(
    bg="#eef1f5", card="#ffffff", line="#e3e7ec", text="#1f2937", muted="#4b5563",
    head="#111827", blue="#2563eb", blue_bg="#eff6ff", nav_on="#1f2937",
    red="#dc2626", red_text="#b91c1c", red_bg="#fef2f2",
    orange="#ea580c", orange_text="#b45309", orange_bg="#fff7ed",
    green="#16a34a", green_text="#15803d", green_bg="#f0fdf4",
    gray="#9ca3af", gray_bg="#f3f4f6", bar="#f7f8fa",
)
LEVEL = {
    "red": (C["red"], C["red_bg"], C["red_text"]),
    "orange": (C["orange"], C["orange_bg"], C["orange_text"]),
    "green": (C["green"], C["green_bg"], C["green_text"]),
    "gray": (C["gray"], C["gray_bg"], C["muted"]),
}
F = "Segoe UI"


def font(size=11, bold=False):
    return (F, size, "bold") if bold else (F, size)


def plural(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def open_path(path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        messagebox.showinfo(APP_TITLE, path)


# ---------------------------------------------------------------------------
# Простые виджеты
# ---------------------------------------------------------------------------
class ScrollFrame(tk.Frame):
    """Фрейм с вертикальной прокруткой: содержимое кладётся в self.body."""

    def __init__(self, master, bg):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


def button(parent, text, cmd, primary=False, size=11):
    if primary:
        b = tk.Button(parent, text=text, command=cmd, font=font(size, True), bg=C["blue"], fg="#ffffff",
                      activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat",
                      bd=0, padx=18, pady=9, cursor="hand2")
    else:
        b = tk.Button(parent, text=text, command=cmd, font=font(size), bg=C["card"], fg=C["text"],
                      activebackground=C["gray_bg"], relief="solid", bd=1, padx=16, pady=8,
                      cursor="hand2", highlightbackground=C["line"])
    return b


def label(parent, text, size=11, bold=False, color=None, bg=None, wrap=0, **kw):
    return tk.Label(parent, text=text, font=font(size, bold), fg=color or C["text"],
                    bg=bg or parent["bg"], wraplength=wrap, justify="left", anchor="w", **kw)


def card(parent, border=None, bg=None, thick=1):
    outer = tk.Frame(parent, bg=border or C["line"])
    inner = tk.Frame(outer, bg=bg or C["card"], padx=18, pady=16)
    inner.pack(fill="both", expand=True, padx=thick, pady=thick)
    return outer, inner


def text_view(parent):
    fr = tk.Frame(parent, bg=C["card"])
    t = tk.Text(fr, wrap="word", font=font(11), bd=0, padx=16, pady=14, fg=C["text"],
                bg=C["card"], highlightthickness=0)
    sb = ttk.Scrollbar(fr, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    t.tag_configure("h1", font=font(16, True), foreground=C["head"], spacing3=6)
    t.tag_configure("small", font=font(10), foreground=C["muted"])
    t.tag_configure("cap", font=font(9, True), foreground=C["muted"], spacing1=10)
    t.tag_configure("body", font=font(11), spacing3=4, lmargin1=0)
    t.tag_configure("red", font=font(11, True), foreground=C["red_text"])
    t.tag_configure("mono", font=("Consolas", 9), foreground=C["text"], background=C["gray_bg"])
    t.configure(state="disabled")
    return fr, t


def text_fill(t, parts):
    """parts — список (текст, тег)."""
    t.configure(state="normal")
    t.delete("1.0", "end")
    for s, tag in parts:
        t.insert("end", s, tag)
    t.configure(state="disabled")
    t.yview_moveto(0)


# ---------------------------------------------------------------------------
# Приложение
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root, initial_paths=()):
        self.root = root
        self.logs = []
        self.known = set()
        self.dev = None          # сведения о подключённом телефоне
        self.phone_state = "nodriver" if not device_support() else "start"
        self.events = queue.Queue()
        self.current_tab = None

        root.title(APP_TITLE)
        root.geometry("1200x800")
        root.minsize(900, 600)
        root.configure(bg=C["bg"])
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        style.configure("Treeview", font=font(11), rowheight=30)
        style.configure("Treeview.Heading", font=font(10, True))

        # Навигация
        nav = tk.Frame(root, bg=C["card"], padx=16, pady=10)
        nav.pack(fill="x")
        label(nav, "iOS Panic Reader", 13, True).pack(side="left", padx=(0, 20))
        self.nav_buttons = {}
        for key, title in (("phone", "Телефон"), ("parts", "Детали"), ("logs", "Все логи"),
                           ("kb", "Справочник ошибок")):
            b = tk.Button(nav, text=title, font=font(11), relief="flat", bd=0, padx=16, pady=7,
                          cursor="hand2", command=lambda k=key: self.show(k))
            b.pack(side="left", padx=3)
            self.nav_buttons[key] = b
        tk.Frame(root, bg=C["line"], height=1).pack(fill="x")

        self.content = tk.Frame(root, bg=C["bg"])
        self.content.pack(fill="both", expand=True)

        self.status = tk.StringVar()
        bar = tk.Frame(root, bg=C["bar"])
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=C["line"], height=1).pack(fill="x")
        tk.Label(bar, textvariable=self.status, font=font(10), fg=C["muted"], bg=C["bar"],
                 anchor="w", padx=16, pady=6).pack(fill="x")

        self.frames = {
            "phone": ScrollFrame(self.content, C["bg"]),
            "parts": ScrollFrame(self.content, C["bg"]),
            "logs": self._build_logs(),
            "kb": self._build_kb(),
        }
        self.show("phone")
        self.render_phone()

        if device_support():
            self.watcher = DeviceWatcher(self.events)
            self.watcher.start()
        else:
            self.watcher = None
        root.after(300, self.poll)
        if initial_paths:
            root.after(200, lambda: self.load(list(initial_paths)))

    # ------------------------------------------------------------- навигация
    def show(self, key):
        for k, f in self.frames.items():
            f.pack_forget()
        self.frames[key].pack(fill="both", expand=True, padx=0, pady=0)
        for k, b in self.nav_buttons.items():
            on = k == key
            b.configure(bg=C["nav_on"] if on else C["card"], fg="#ffffff" if on else C["text"],
                        activebackground=C["nav_on"] if on else C["gray_bg"],
                        font=font(11, on))
        self.current_tab = key
        if key == "parts":
            self.render_parts()
        self.update_status()

    def update_status(self):
        panics = sum(l["is_panic"] for l in self.logs)
        s = {
            "nodriver": "Служба Apple Mobile Device не найдена",
            "wait": "Ожидание iPhone…",
            "trust": "iPhone подключён · ожидание подтверждения «Доверять»",
            "unlock": "iPhone подключён · разблокируйте телефон",
            "reading": "Снимаю логи…",
        }.get(self.phone_state, "")
        if self.logs:
            s = (s + " · " if s else "") + f"{len(self.logs)} {plural(len(self.logs), 'лог', 'лога', 'логов')}, " \
                f"{panics} {plural(panics, 'паника', 'паники', 'паник')}"
        if self.dev and self.dev.get("dir"):
            s = (s + " · " if s else "") + "сохранены в " + self.dev["dir"]
        self.status.set(s)

    # ------------------------------------------------------------- события
    def poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "state":
                    code = ev[1]
                    if code == "wait" and self.phone_state == "result":
                        pass  # результат остаётся на экране, пока не подключат другой
                    else:
                        self.phone_state = code
                        self.error_text = ev[2]
                        self.render_phone()
                elif kind == "info":
                    self.dev = ev[1]
                    self.phone_state = "reading"
                    self.render_phone()
                elif kind == "pulled":
                    self.dev = ev[1]
                    self.logs.clear()
                    self.known.clear()
                    self.load([self.dev["dir"]], quiet=True)
                    self.phone_state = "result"
                    self.render_phone()
                    self.show("phone")
                elif kind == "disconnected":
                    if self.phone_state != "result":
                        self.phone_state = "wait"
                        self.render_phone()
                elif kind == "log":
                    print(ev[1])
                self.update_status()
        except queue.Empty:
            pass
        self.root.after(300, self.poll)

    # ------------------------------------------------------------- загрузка
    def load(self, paths, quiet=False):
        new = []
        for f in collect_files(paths):
            if f in self.known:
                continue
            self.known.add(f)
            try:
                new.append(parse_log(f))
            except Exception:
                pass
        self.logs.extend(new)
        self.logs.sort(key=lambda l: str(l["date"]), reverse=True)
        self.refresh_logs()
        if not quiet:
            if not new:
                messagebox.showinfo(APP_TITLE, "Новых логов не найдено.")
            else:
                self.phone_state = "result"
                self.render_phone()
                self.show("phone")
        self.update_status()
        return new

    def open_files(self):
        fs = filedialog.askopenfilenames(title="Выберите логи", filetypes=[
            ("Логи iOS", "*.ips *.panic *.log *.txt *.synced *.crash"), ("Все файлы", "*.*")])
        if fs:
            self.load(fs)

    def open_folder(self):
        d = filedialog.askdirectory(title="Папка с логами", initialdir=logs_root())
        if d:
            self.load([d])

    def again(self):
        if self.watcher:
            self.watcher.manual.put("*")
        self.phone_state = "wait"
        self.dev = None
        self.render_phone()

    def save_report(self):
        if not self.logs and not self.dev:
            return
        name = (self.dev or {}).get("model", "телефон")
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Текст", "*.txt")],
                                         initialfile=f"Отчёт {name} {datetime.now():%Y-%m-%d}.txt")
        if not f:
            return
        out = []
        problems = build_verdict(self.logs, self.dev)
        out.append(f"ОТЧЁТ iOS Panic Reader · {datetime.now():%d.%m.%Y %H:%M}")
        out.append("=" * 72)
        out += [f"{k}: {v}" for k, v in self.device_lines()]
        out.append("")
        if problems:
            out.append("НАЙДЕННЫЕ ПРОБЛЕМЫ:")
            for i, p in enumerate(problems, 1):
                lvl = "ВАЖНО" if p["level"] == "red" else "НЕ СРОЧНО"
                out.append(f"{i}. {p['title']} [{lvl}] — {p['note']}")
                out.append(f"   Как ведёт себя: {p['how']}")
                out.append(f"   Почему: {p['why']}")
                out.append("   Что делать: " + "; ".join(p["fix"]))
        else:
            out.append("ПРОБЛЕМ НЕ НАЙДЕНО")
        out.append("")
        out.append("ДЕТАЛИ:")
        for name_, data, fails, lvl in parts_table(self.logs, self.dev):
            out.append(f"  {name_}: {data} · сбои: {fails}")
        out.append("")
        out.append(build_summary(self.logs))
        out.append("")
        for l in self.logs:
            if l["is_panic"]:
                out.append(build_report(l))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
        self.status.set("Отчёт сохранён: " + f)

    def device_lines(self):
        d = self.dev
        if not d:
            ls = [l for l in self.logs if l["product"]]
            if ls:
                return [("Устройство", core.device_label(ls[0])), ("iOS", ls[0]["os"] or "—"),
                        ("Источник", "файлы логов")]
            return []
        out = [("Модель", f"{d['model']} ({d['product']})"), ("iOS", f"{d['ios']} ({d['build']})"),
               ("Серийный номер", d.get("serial") or "—"), ("IMEI", d.get("imei") or "не прочитан")]
        if d.get("battery_health") is not None:
            out.append(("Аккумулятор", f"{d['battery_health']}% ({d.get('battery_mah', '')}), "
                                       f"{d.get('battery_cycles', '?')} циклов"))
        return out

    # ------------------------------------------------------------- экран «Телефон»
    def render_phone(self):
        sf = self.frames["phone"]
        sf.clear()
        st = self.phone_state
        if st == "result":
            return self._phone_result(sf.body)
        center = tk.Frame(sf.body, bg=C["bg"])
        center.pack(expand=True, pady=70, padx=24)

        def big(title, text, color=C["blue"], symbol="📱"):
            tk.Label(center, text=symbol, font=(F, 46), fg=color, bg=C["bg"]).pack()
            label(center, title, 22, True, bg=C["bg"]).pack(pady=(10, 6))
            if text:
                label(center, text, 13, color=C["muted"], bg=C["bg"], wrap=560).pack()

        row = None
        if st == "nodriver":
            big("Компьютер не видит iPhone", "Не установлен драйвер Apple. Без него Windows не может "
                "подключиться к телефону.", C["orange"], "⚠")
            steps = tk.Frame(center, bg=C["card"], padx=20, pady=16, highlightbackground=C["line"],
                             highlightthickness=1)
            steps.pack(pady=18, fill="x")
            for s in ("1. Установите «Apple Devices» из Microsoft Store (или iTunes)",
                      "2. Переподключите кабель",
                      "3. Программа подхватит телефон сама"):
                label(steps, s, 12).pack(anchor="w", pady=2)
            if not device_support():
                label(steps, "Модуль pymobiledevice3 не найден — используйте собранный .exe "
                             "или выполните: pip install pymobiledevice3", 10, color=C["red_text"],
                      wrap=520).pack(anchor="w", pady=(8, 0))
            row = tk.Frame(center, bg=C["bg"])
            button(row, "Открыть Microsoft Store",
                   lambda: open_path("ms-windows-store://search/?query=Apple%20Devices"), True).pack(side="left", padx=5)
        elif st in ("wait", "start", "denied"):
            if st == "denied":
                big("На iPhone нажали «Не доверять»", "Отключите и снова подключите кабель, затем нажмите "
                    "«Доверять».", C["orange"], "⚠")
            else:
                big("Подключите iPhone кабелем", "Разблокируйте телефон и нажмите «Доверять». Программа "
                    "сама снимет логи и покажет, что с телефоном.")
            row = tk.Frame(center, bg=C["bg"])
        elif st in ("trust", "unlock"):
            big("Нажмите «Доверять» на телефоне" if st == "trust" else "Разблокируйте iPhone",
                "", C["blue"], "🔓")
            steps = tk.Frame(center, bg=C["bg"])
            steps.pack(pady=10)
            for s in ("1. Разблокируйте iPhone", "2. На экране появится вопрос — нажмите «Доверять»",
                      "3. Введите код-пароль телефона"):
                label(steps, s, 13, bg=C["bg"]).pack(anchor="w", pady=2)
            label(center, "Окна нет? Отключите и снова подключите кабель.", 11, color=C["muted"],
                  bg=C["bg"]).pack(pady=8)
        elif st == "reading":
            d = self.dev or {}
            big(f"{d.get('model', 'iPhone')} подключён", "Снимаю логи… Не отключайте кабель.")
            pb = ttk.Progressbar(center, mode="indeterminate", length=440)
            pb.pack(pady=20)
            pb.start(12)
        elif st == "error":
            big("Не удалось прочитать iPhone", getattr(self, "error_text", ""), C["red"], "⚠")
            row = tk.Frame(center, bg=C["bg"])
            button(row, "Попробовать снова", self.again, True).pack(side="left", padx=5)
        if row is not None:
            row.pack(pady=16)
            button(row, "Открыть файл лога…", self.open_files).pack(side="left", padx=5)
            button(row, "Открыть папку…", self.open_folder).pack(side="left", padx=5)

    def _phone_result(self, body):
        wrap = tk.Frame(body, bg=C["bg"], padx=20, pady=20)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(1, weight=1)

        # Левая колонка — карточка телефона
        left = tk.Frame(wrap, bg=C["bg"], width=320)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 20))
        o, c = card(left)
        o.pack(fill="x")
        d = self.dev
        panics = [l for l in self.logs if l["is_panic"]]
        if d:
            label(c, d["model"], 17, True).pack(anchor="w")
            label(c, f"iOS {d['ios']} · {d.get('serial', '')}", 10, color=C["muted"]).pack(anchor="w", pady=(2, 10))
        else:
            first = next((l for l in self.logs if l["product"]), None)
            label(c, first["model"] if first else "Логи из файлов", 17, True).pack(anchor="w")
            label(c, (first["os"] if first else "") or "телефон не подключён", 10,
                  color=C["muted"]).pack(anchor="w", pady=(2, 10))
        grid = tk.Frame(c, bg=C["card"])
        grid.pack(fill="x")
        stats = []
        if d and d.get("battery_health") is not None:
            h = d["battery_health"]
            stats.append(("Аккумулятор", f"{h}%", "green" if h >= 85 else ("orange" if h >= 80 else "red")))
        if d and d.get("battery_cycles") is not None:
            stats.append(("Циклы", str(d["battery_cycles"]), None))
        stats.append(("Паник", str(len(panics)), "green" if not panics else ("orange" if len(panics) < 3 else "red")))
        if d and d.get("is_iphone"):
            stats.append(("Сеть / IMEI", "OK" if d.get("imei") else "нет", "green" if d.get("imei") else "red"))
        for i, (k, v, lvl) in enumerate(stats):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 26), pady=6)
            label(cell, k, 9, color=C["muted"]).pack(anchor="w")
            label(cell, v, 18, True, color=LEVEL[lvl][2] if lvl else C["text"]).pack(anchor="w")
        if d and d.get("imei"):
            label(c, "IMEI " + d["imei"], 10, color=C["muted"]).pack(anchor="w", pady=(8, 0))

        btns = tk.Frame(left, bg=C["bg"])
        btns.pack(fill="x", pady=12)
        if self.watcher:
            button(btns, "Подключить другой телефон", self.again).pack(fill="x", pady=3)
        button(btns, "Открыть файл лога…", self.open_files).pack(fill="x", pady=3)

        # Правая колонка — вывод
        right = tk.Frame(wrap, bg=C["bg"])
        right.grid(row=0, column=1, sticky="nsew")
        problems = build_verdict(self.logs, d)
        wl = 640

        if not problems:
            o, c = card(right, C["green"], C["green_bg"], 2)
            o.pack(fill="x")
            label(c, "ПРОБЛЕМ НЕ НАЙДЕНО", 10, True, C["green_text"]).pack(anchor="w")
            label(c, "Телефон в порядке", 22, True, C["head"]).pack(anchor="w", pady=(4, 6))
            msg = "В логах нет ни одной паники ядра." if not panics else \
                "Паники единичные и не указывают на конкретную деталь."
            if d and d.get("battery_health") is not None:
                msg += f" Аккумулятор: {d['battery_health']}%."
            label(c, msg, 12, color=C["text"], wrap=wl).pack(anchor="w")
        elif len(problems) == 1:
            p = problems[0]
            self._problem_card(right, p, wl, big=True)
        else:
            reds = sum(p["level"] == "red" for p in problems)
            label(right, f"НАЙДЕНО {len(problems)} {plural(len(problems), 'ПРОБЛЕМА', 'ПРОБЛЕМЫ', 'ПРОБЛЕМ')} · "
                         "от самой важной", 10, True, C["red_text"] if reds else C["orange_text"],
                  bg=C["bg"]).pack(anchor="w", pady=(0, 8))
            for i, p in enumerate(problems, 1):
                self._problem_card(right, p, wl, num=i)

        # Что ещё нашлось в логах
        crashes = [l for l in self.logs if not l["is_panic"] and l["exception"]]
        jetsam = [l for l in self.logs if "Jetsam" in l["kind"] or l["bug_type"] == "298"]
        if crashes or jetsam:
            o, c = card(right)
            o.pack(fill="x", pady=(14, 0))
            label(c, "Что ещё нашлось в логах", 12, True).pack(anchor="w", pady=(0, 6))
            if crashes:
                apps = {}
                for l in crashes:
                    apps[l["process"] or "?"] = apps.get(l["process"] or "?", 0) + 1
                top = ", ".join(f"{a} ({n})" for a, n in sorted(apps.items(), key=lambda x: -x[1])[:4])
                self._dot_line(c, "orange", f"{len(crashes)} {plural(len(crashes), 'вылет', 'вылета', 'вылетов')} "
                                            f"{'приложения' if len(crashes) == 1 else 'приложений'}: {top} — ошибки приложений, с железом не связано", wl)
            if jetsam:
                self._dot_line(c, "gray", f"{len(jetsam)} раз не хватило памяти (Jetsam) — это нормально", wl)

        row = tk.Frame(right, bg=C["bg"])
        row.pack(anchor="w", pady=16)
        button(row, "Посмотреть логи", lambda: self.show("logs"), True).pack(side="left", padx=(0, 8))
        button(row, "Детали", lambda: self.show("parts")).pack(side="left", padx=(0, 8))
        button(row, "Сохранить отчёт", self.save_report).pack(side="left", padx=(0, 8))
        if d and d.get("dir"):
            button(row, "Открыть папку с логами", lambda: open_path(d["dir"])).pack(side="left")

    def _dot_line(self, parent, lvl, text, wl):
        r = tk.Frame(parent, bg=parent["bg"])
        r.pack(anchor="w", pady=2, fill="x")
        tk.Label(r, text="●", fg=LEVEL[lvl][0], bg=parent["bg"], font=font(12)).pack(side="left", anchor="n")
        label(r, text, 11, wrap=wl).pack(side="left", padx=6)

    def _problem_card(self, parent, p, wl, big=False, num=None):
        border, bg, tcol = LEVEL[p["level"]]
        o, c = card(parent, border, bg, 2)
        o.pack(fill="x", pady=(0, 12))
        if big:
            label(c, "НАЙДЕНА ПРОБЛЕМА" if p["level"] == "red" else "ВОЗМОЖНАЯ ПРОБЛЕМА", 10, True, tcol).pack(anchor="w")
            label(c, p["title"], 22, True, C["head"], wrap=wl).pack(anchor="w", pady=(4, 8))
        else:
            head = tk.Frame(c, bg=bg)
            head.pack(fill="x")
            label(head, f"{num}. {p['title']}", 15, True, C["head"], wrap=wl - 120).pack(side="left")
            label(head, "ВАЖНО" if p["level"] == "red" else "НЕ СРОЧНО", 9, True, tcol).pack(side="right")
        for cap, txt in (("Как ведёт себя", p["how"]), ("Почему", p["why"])):
            label(c, cap.upper(), 9, True, C["muted"]).pack(anchor="w", pady=(6, 0))
            label(c, txt, 11, wrap=wl).pack(anchor="w")
        label(c, "ЧТО ДЕЛАТЬ", 9, True, C["muted"]).pack(anchor="w", pady=(6, 0))
        for i, f in enumerate(p["fix"], 1):
            label(c, f"{i}. {f.rstrip('.')}", 11, wrap=wl).pack(anchor="w")
        label(c, "Уверенность: " + p["note"], 10, color=C["muted"]).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------- экран «Детали»
    def render_parts(self):
        sf = self.frames["parts"]
        sf.clear()
        body = tk.Frame(sf.body, bg=C["bg"], padx=20, pady=20)
        body.pack(fill="both", expand=True)
        title = (self.dev or {}).get("model") or next((l["model"] for l in self.logs if l["model"]), "телефона")
        label(body, f"Детали {title} — состояние и сбои", 18, True, bg=C["bg"]).pack(anchor="w")

        rows = parts_table(self.logs, self.dev)
        counts = {k: sum(r[3] == k for r in rows) for k in ("green", "orange", "red")}
        cnt = tk.Frame(body, bg=C["bg"])
        cnt.pack(fill="x", pady=14)
        for lvl, txt in (("green", "без сбоев"), ("orange", "есть подозрения"), ("red", "есть проблемы")):
            o, c = card(cnt, LEVEL[lvl][0], LEVEL[lvl][1])
            o.pack(side="left", padx=(0, 12))
            label(c, str(counts[lvl]), 20, True, LEVEL[lvl][2]).pack(anchor="w")
            label(c, txt, 10).pack(anchor="w")

        o, c = card(body, C["blue"], C["blue_bg"])
        o.pack(fill="x", pady=(0, 14))
        label(c, "Оригинальность деталей", 11, True).pack(anchor="w")
        label(c, "Посмотреть, какие детали заменены, можно на самом iPhone: Настройки → Основные → "
                 "Об этом устройстве → «История деталей и обслуживания» (iOS 15.2+, iPhone XS и новее). "
                 "Там будет «Оригинальная деталь Apple» или «Неизвестная деталь». Автоматическая проверка "
                 "в программе появится после тестов на реальных телефонах.", 10, wrap=900).pack(anchor="w")

        o, tbl = card(body)
        o.pack(fill="x")
        heads = ("Деталь", "Данные с телефона", "Сбои в логах", "Статус")
        for j, h in enumerate(heads):
            label(tbl, h, 10, True, C["muted"]).grid(row=0, column=j, sticky="w", padx=8, pady=(0, 8))
        tbl.columnconfigure(1, weight=1)
        tbl.columnconfigure(2, weight=1)
        status_txt = {"green": "в порядке", "orange": "подозрение", "red": "проблема"}
        for i, (name, data, fails, lvl) in enumerate(rows, 1):
            bgc = LEVEL[lvl][1] if lvl != "green" else C["card"]
            cells = [label(tbl, name, 11, True, bg=bgc, wrap=260),
                     label(tbl, data, 10, color=C["muted"], bg=bgc, wrap=300),
                     label(tbl, fails, 10, lvl != "green", LEVEL[lvl][2] if lvl != "green" else C["green_text"],
                           bg=bgc, wrap=320),
                     label(tbl, "● " + status_txt[lvl], 10, True, LEVEL[lvl][2], bg=bgc)]
            for j, w in enumerate(cells):
                w.grid(row=i, column=j, sticky="nsew", padx=0, pady=1, ipadx=8, ipady=7)

        row = tk.Frame(body, bg=C["bg"])
        row.pack(anchor="w", pady=14)
        button(row, "Сохранить отчёт", self.save_report, True).pack(side="left", padx=(0, 8))
        button(row, "Посмотреть логи", lambda: self.show("logs")).pack(side="left")

    # ------------------------------------------------------------- экран «Все логи»
    def _build_logs(self):
        root = tk.Frame(self.content, bg=C["bg"], padx=16, pady=14)
        bar = tk.Frame(root, bg=C["bg"])
        bar.pack(fill="x", pady=(0, 10))
        label(bar, "Поиск", 11, color=C["muted"], bg=C["bg"]).pack(side="left")
        self.log_q = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.log_q, width=30, font=font(11))
        e.pack(side="left", padx=8)
        self.only_panic = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Только паники", variable=self.only_panic, bg=C["bg"], font=font(11),
                       command=self.refresh_logs, activebackground=C["bg"]).pack(side="left", padx=8)
        button(bar, "Открыть файлы…", self.open_files, size=10).pack(side="right", padx=3)
        button(bar, "Открыть папку…", self.open_folder, size=10).pack(side="right", padx=3)
        self.log_q.trace_add("write", lambda *_: self.refresh_logs())

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=C["card"])
        self.tree = ttk.Treeview(left, columns=("what", "date", "kind"), show="headings", selectmode="browse")
        for c_, t, w in (("what", "Что случилось", 330), ("date", "Дата", 140), ("kind", "Вид", 170)):
            self.tree.heading(c_, text=t)
            self.tree.column(c_, width=w, anchor="w")
        for lvl in ("red", "orange", "gray"):
            self.tree.tag_configure(lvl, foreground=LEVEL[lvl][2])
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        paned.add(left, weight=2)

        right = tk.Frame(paned, bg=C["card"])
        fr, self.log_text = text_view(right)
        fr.pack(fill="both", expand=True)
        rb = tk.Frame(right, bg=C["card"], padx=12, pady=8)
        rb.pack(fill="x")
        button(rb, "Исходный текст лога", self.show_raw, size=10).pack(side="left")
        button(rb, "Полный разбор", self.show_full, size=10).pack(side="left", padx=6)
        paned.add(right, weight=3)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_log())
        return root

    def _log_level(self, l):
        if l["is_panic"]:
            return "red"
        if l["exception"]:
            return "orange"
        return "gray"

    def _log_title(self, l):
        if l["is_panic"]:
            part = core.panic_part(l)
            return "Паника: " + (core.PART_NAMES[part] if part else main_cause(l))
        if l["exception"]:
            return f"{l['process'] or 'Приложение'} закрылось"
        if "Jetsam" in l["kind"]:
            return "Не хватило памяти"
        return l["kind"]

    def refresh_logs(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        q = self.log_q.get().lower().strip()
        for i, l in enumerate(self.logs):
            if self.only_panic.get() and not l["is_panic"]:
                continue
            title = self._log_title(l)
            if q and q not in (title + l["panic"] + l["process"] + os.path.basename(l["file"])).lower():
                continue
            self.tree.insert("", "end", iid=str(i), tags=(self._log_level(l),),
                             values=("● " + title, str(l["date"])[:16], l["kind"]))

    def _selected_log(self):
        sel = self.tree.selection()
        return self.logs[int(sel[0])] if sel else None

    def show_log(self):
        l = self._selected_log()
        if not l:
            return
        parts = [(f"{str(l['date'])[:19]} · {l['kind']}\n", "small"), (self._log_title(l) + "\n", "h1")]
        if l["missing_sensors"]:
            parts.append(("ТЕЛЕФОН НЕ ВИДИТ ДАТЧИКИ\n", "cap"))
            for s in l["missing_sensors"]:
                d = core.sensor_info(s)
                parts.append((f"• {s} — {d['name']}. {d['where']}\n", "body"))
        e = l["findings"][0][0] if l["findings"] else None
        if e:
            parts += [("КАК ВЕДЁТ СЕБЯ\n", "cap"), (e["symptoms"] + "\n", "body"),
                      ("ПОЧЕМУ\n", "cap"), (e["cause"] + "\n", "body"),
                      ("ЧТО ДЕЛАТЬ\n", "cap"), (e["fix"] + "\n", "body")]
            if len(l["findings"]) > 1:
                parts.append(("ЕЩЁ НАЙДЕНО В ЛОГЕ\n", "cap"))
                parts += [(f"• {fe['title']}\n", "body") for fe, _ in l["findings"][1:]]
        else:
            parts.append(("\nИзвестных ошибок не найдено. Посмотрите исходный текст лога.\n", "body"))
        if l["exception"]:
            parts += [("ИСКЛЮЧЕНИЕ\n", "cap"), (l["exception"] + "\n", "body")]
        parts += [("\nУСТРОЙСТВО\n", "cap"), (f"{core.device_label(l)} · {l['os'] or '—'}\n", "body"),
                  ("ФАЙЛ\n", "cap"), (l["file"] + "\n", "small")]
        if l["panic"]:
            first = next((x.strip() for x in l["panic"].splitlines() if x.strip()), "")
            parts += [("\nПЕРВАЯ СТРОКА ПАНИКИ\n", "cap"), (first[:400] + "\n", "mono")]
        text_fill(self.log_text, parts)

    def _popup(self, title, content):
        w = tk.Toplevel(self.root)
        w.title(title)
        w.geometry("1000x700")
        t = tk.Text(w, wrap="none", font=("Consolas", 10))
        ys = ttk.Scrollbar(w, orient="vertical", command=t.yview)
        xs = ttk.Scrollbar(w, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        t.pack(fill="both", expand=True)
        t.insert("1.0", content)

    def show_raw(self):
        l = self._selected_log()
        if l:
            self._popup(os.path.basename(l["file"]), l["raw"])

    def show_full(self):
        l = self._selected_log()
        if l:
            self._popup("Разбор: " + os.path.basename(l["file"]), build_report(l))

    # ------------------------------------------------------------- экран «Справочник»
    def _build_kb(self):
        root = tk.Frame(self.content, bg=C["bg"], padx=16, pady=14)
        bar = tk.Frame(root, bg=C["bg"])
        bar.pack(fill="x")
        label(bar, "Что случилось с телефоном?", 12, True, bg=C["bg"]).pack(side="left")
        self.kb_q = tk.StringVar()
        ttk.Entry(bar, textvariable=self.kb_q, width=40, font=font(11)).pack(side="left", padx=10)
        label(bar, "например: перезагружается, 4013, mic1, нет сети", 10, color=C["muted"],
              bg=C["bg"]).pack(side="left")

        chips = tk.Frame(root, bg=C["bg"])
        chips.pack(fill="x", pady=10)
        self.kb_cat = "Все"
        self.chip_buttons = {}
        short = {"Паника ядра": "Паники", "Датчики (Missing sensor)": "Датчики",
                 "Вылет приложения": "Приложения", "Ошибка iTunes / восстановления": "Ошибки iTunes",
                 "Симптомы телефона": "Симптомы", "Логи и версии iOS": "Логи и iOS"}
        for cat in ["Все", "Симптомы телефона"] + [c_ for c_ in CATEGORIES if c_ != "Симптомы телефона"]:
            b = tk.Button(chips, text=short.get(cat, cat), font=font(10), relief="flat", bd=0, padx=14,
                          pady=5, cursor="hand2", command=lambda c_=cat: self._kb_pick(c_))
            b.pack(side="left", padx=3)
            self.chip_buttons[cat] = b

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=C["card"])
        self.ktree = ttk.Treeview(left, columns=("title",), show="headings", selectmode="browse")
        self.ktree.heading("title", text="Ошибка / симптом")
        self.ktree.column("title", width=360)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.ktree.yview)
        self.ktree.configure(yscrollcommand=sb.set)
        self.ktree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        paned.add(left, weight=2)
        fr, self.kb_text = text_view(paned)
        paned.add(fr, weight=3)
        self.ktree.bind("<<TreeviewSelect>>", lambda e: self._kb_show())
        self.kb_q.trace_add("write", lambda *_: self._kb_refresh())
        self._kb_pick("Все")
        return root

    def _kb_pick(self, cat):
        self.kb_cat = cat
        for c_, b in self.chip_buttons.items():
            on = c_ == cat
            b.configure(bg=C["blue"] if on else C["card"], fg="#ffffff" if on else C["text"],
                        activebackground=C["blue"] if on else C["gray_bg"])
        self._kb_refresh()

    def _kb_refresh(self):
        self.ktree.delete(*self.ktree.get_children())
        q = self.kb_q.get().lower().strip()
        cat = self.kb_cat
        for i, e in enumerate(KB):
            if cat != "Все" and e["cat"] != cat:
                continue
            hay = " ".join(str(e.get(k, "")) for k in ("title", "node", "symptoms", "cause", "fix",
                                                        "models", "ios")) + " " + " ".join(e.get("patterns", []))
            if q and q not in hay.lower():
                continue
            self.ktree.insert("", "end", iid=f"kb:{i}", values=(e["title"],))
        if cat in ("Все", "Датчики (Missing sensor)"):
            for k, d in SENSORS.items():
                if q and q not in (k + " " + " ".join(d.values())).lower():
                    continue
                self.ktree.insert("", "end", iid=f"s:{k}", values=(f"Датчик {k} — {d['name']}",))
        kids = self.ktree.get_children()
        if kids:
            self.ktree.selection_set(kids[0])

    def _kb_show(self):
        sel = self.ktree.selection()
        if not sel:
            return
        typ, key = sel[0].split(":", 1)
        if typ == "s":
            d = SENSORS[key]
            parts = [("Датчики (Missing sensor)\n", "small"), (f"Датчик {key} — {d['name']}\n", "h1"),
                     ("ГДЕ СТОИТ\n", "cap"), (d["where"] + "\n", "body")]
            if d.get("models"):
                parts += [("ПО МОДЕЛЯМ\n", "cap"), (d["models"] + "\n", "body")]
            parts += [("ЧТО ДЕЛАТЬ\n", "cap"), (d["fix"] + "\n", "body"),
                      ("КАК ВЕДЁТ СЕБЯ\n", "cap"),
                      ("Если датчика нет, телефон перезагружается каждые ~3 минуты "
                       "(паника thermalmonitord).\n", "body")]
        else:
            e = KB[int(key)]
            parts = [(e["cat"] + "\n", "small"), (e["title"] + "\n", "h1"),
                     ("УЗЕЛ\n", "cap"), (e["node"] + "\n", "body")]
            if e.get("models"):
                parts += [("МОДЕЛИ\n", "cap"), (e["models"] + "\n", "body")]
            if e.get("ios"):
                parts += [("ВЕРСИИ iOS\n", "cap"), (e["ios"] + "\n", "body")]
            parts += [("КАК ВЕДЁТ СЕБЯ ТЕЛЕФОН\n", "cap"), (e["symptoms"] + "\n", "body"),
                      ("ПОЧЕМУ\n", "cap"), (e["cause"] + "\n", "body"),
                      ("ЧТО ДЕЛАТЬ\n", "cap"), (e["fix"] + "\n", "body")]
            n = sum(1 for l in self.logs for fe, _ in l["findings"] if fe is e)
            if n:
                parts.append((f"\nВстречается в загруженных логах: {n} раз(а)\n", "red"))
            if e.get("patterns"):
                parts += [("КАК ВЫГЛЯДИТ В ЛОГЕ\n", "cap"), ("  ".join(e["patterns"]) + "\n", "mono")]
        text_fill(self.kb_text, parts)


def run_gui(initial_paths=()):
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    App(root, initial_paths)
    root.mainloop()
