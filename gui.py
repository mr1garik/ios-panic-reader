# -*- coding: utf-8 -*-
"""Окно программы: Телефон · Детали · Все логи · История · Справочник ошибок."""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkfont

import core
import i18n
from i18n import _, plural
from core import (APP_TITLE, build_report, build_summary, build_verdict, collect_files,
                  logs_root, main_cause, parse_log, parse_pasted, parts_table)
from device import DeviceWatcher, device_support
from history import History, phone_key
import report_pdf
import updater
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
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
F = "Helvetica Neue" if IS_MAC else "Segoe UI"
MONO = "Menlo" if IS_MAC else "Consolas"
MOD = "Command" if IS_MAC else "Control"     # Cmd на Mac, Ctrl на Windows

# Масштаб интерфейса. dpi — плотность экрана (Windows: 125%, 150%… → 1.25, 1.5),
# zoom — масштаб, выбранный пользователем (Ctrl + / Ctrl −).
UI = {"dpi": 1.0, "zoom": 1.0}
ZOOMS = (0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)
_fonts = {}


def px(n):
    """Размер в пикселях с учётом плотности экрана и масштаба."""
    return int(round(n * UI["dpi"] * UI["zoom"]))


def font(size=11, bold=False, family=None):
    """Именованный шрифт: при смене масштаба все виджеты обновляются сами."""
    key = (family or F, size, bold)
    f = _fonts.get(key)
    if f is None:
        f = tkfont.Font(family=key[0], size=max(6, round(size * UI["zoom"])), weight="bold" if bold else "normal")
        _fonts[key] = f
    return f


def apply_zoom(z):
    UI["zoom"] = z
    for (fam, size, bold), f in _fonts.items():
        f.configure(size=max(6, round(size * z)))


def screen_scale(root):
    """Плотность экрана относительно 96 dpi. На Mac система сама работает в «точках»."""
    if IS_MAC:
        return 1.0
    try:
        return max(1.0, min(3.0, root.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        return 1.0


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
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))

    def _bind_wheel(self, on):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            if on:
                self.canvas.bind_all(ev, self._wheel)
            else:
                self.canvas.unbind_all(ev)

    def _wheel(self, e):
        if getattr(e, "num", None) in (4, 5):        # Linux
            step = -1 if e.num == 4 else 1
        elif IS_MAC:                                  # macOS: delta = ±1..n
            step = -e.delta
        else:                                         # Windows: delta = ±120
            step = int(-e.delta / 120)
        self.canvas.yview_scroll(step, "units")

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


class FlatButton(tk.Label):
    """Кнопка из Label: на macOS обычный tk.Button не умеет цветной фон."""

    def __init__(self, parent, command=None, **kw):
        kw.setdefault("cursor", "hand2")
        kw.setdefault("takefocus", 1)
        kw.pop("relief", None)
        kw.setdefault("bd", 0)
        super().__init__(parent, **kw)
        self.command = command
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.bind("<Enter>", lambda e: self.configure(state="active"))
        self.bind("<Leave>", lambda e: self.configure(state="normal"))

    def _click(self, e=None):
        if self.command:
            self.command()


def button(parent, text, cmd, primary=False, size=11):
    if primary:
        return FlatButton(parent, text=text, command=cmd, font=font(size, True), bg=C["blue"], fg="#ffffff",
                          activebackground="#1d4ed8", activeforeground="#ffffff", padx=px(18), pady=px(9),
                          highlightthickness=0)
    return FlatButton(parent, text=text, command=cmd, font=font(size), bg=C["card"], fg=C["text"],
                      activebackground=C["gray_bg"], activeforeground=C["text"], padx=px(16), pady=px(8),
                      highlightthickness=1, highlightbackground="#cfd6df", highlightcolor=C["blue"])


class WrapLabel(tk.Label):
    """Текст, который переносится по ширине доступного места и перестраивается при
    изменении размера окна. По умолчанию растягивается по ширине."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.bind("<Configure>", self._rewrap)

    def _rewrap(self, e):
        pad = 2 * (int(self.cget("bd")) + int(self.cget("padx")) + int(self.cget("highlightthickness")))
        w = max(px(80), e.width - pad)
        if abs(int(self.cget("wraplength")) - w) > 2:
            self.configure(wraplength=w)

    def pack(self, **kw):
        kw.setdefault("fill", "x")
        if kw.get("side") in ("left", "right"):
            kw.setdefault("expand", True)
        return super().pack(**kw)


def label(parent, text, size=11, bold=False, color=None, bg=None, wrap=0, **kw):
    """wrap — ширина переноса по умолчанию; если задана, текст подстраивается под окно."""
    cls = WrapLabel if wrap else tk.Label
    return cls(parent, text=text, font=font(size, bold), fg=color or C["text"],
               bg=bg or parent["bg"], wraplength=px(wrap) if wrap else 0, justify="left", anchor="w", **kw)


def card(parent, border=None, bg=None, thick=1):
    outer = tk.Frame(parent, bg=border or C["line"])
    inner = tk.Frame(outer, bg=bg or C["card"], padx=px(18), pady=px(16))
    inner.pack(fill="both", expand=True, padx=thick, pady=thick)
    return outer, inner


def text_view(parent):
    fr = tk.Frame(parent, bg=C["card"])
    # width/height малые: размер задаёт окно, а не длина текста (иначе панель «отъедает» место у списка)
    t = tk.Text(fr, wrap="word", font=font(11), bd=0, padx=px(16), pady=px(14), fg=C["text"], width=30, height=5,
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
    t.tag_configure("mono", font=font(9, family=MONO), foreground=C["text"], background=C["gray_bg"])
    t.configure(state="disabled")
    return fr, t


def split_panes(paned, frac):
    """Начальное положение разделителя — доля ширины (один раз, когда окно уже показано);
    дальше пользователь двигает его сам."""
    def first(e):
        if e.width > 50:
            paned.unbind("<Configure>")
            paned.after_idle(lambda: paned.sashpos(0, int(e.width * frac)))
    paned.bind("<Configure>", first)


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
        _fonts.clear()   # шрифты привязаны к окну Tk; новое окно — новые шрифты
        self.logs = []
        self.known = set()
        self.dev = None          # сведения о подключённом телефоне
        self.phone_state = "nodriver" if not device_support() else "start"
        self.events = queue.Queue()
        self.current_tab = None
        self.history = History()
        self.prev_visit = None     # прошлый визит этого телефона
        self.after_repair = True   # показывать только сбои после отметки ремонта
        self.part_filter = None    # деталь, по которой отфильтрован список логов
        self.update_info = None    # найденная новая версия
        self.update_file = None    # скачанный файл новой версии
        self.update_busy = False

        root.title(APP_TITLE)
        root.configure(bg=C["bg"])
        UI["dpi"] = screen_scale(root)
        z = self.history.setting("zoom", 1.0)
        apply_zoom(z if z in ZOOMS else 1.0)
        self.style = ttk.Style()
        try:
            self.style.theme_use("vista" if IS_WIN else "clam")
        except tk.TclError:
            pass
        self._style_trees()

        # Навигация
        self.nav = nav = tk.Frame(root, bg=C["card"], padx=px(16), pady=px(10))
        nav.pack(fill="x")
        self.nav_title = label(nav, "iOS Panic Reader", 13, True)
        self.nav_title.pack(side="left", padx=(0, px(20)))
        self.nav_buttons = {}
        self.nav_long = {"kb": (_("Поиск ошибок"), _("Поиск"))}
        for i, (key, title) in enumerate((("phone", _("Телефон")), ("parts", _("Детали")), ("logs", _("Все логи")),
                                          ("history", _("История")), ("kb", _("Поиск ошибок"))), 1):
            b = FlatButton(nav, text=title, font=font(11), padx=px(16), pady=px(7), highlightthickness=1,
                           highlightbackground="#cfd6df", command=lambda k=key: self.show(k))
            b.pack(side="left", padx=px(3))
            self.nav_buttons[key] = b
            root.bind_all(f"<{MOD}-Key-{i}>", lambda e, k=key: self.show(k))
        zoom = tk.Frame(nav, bg=C["card"])
        zoom.pack(side="right")
        FlatButton(nav, text=f"v{updater.current_version()}", font=font(9), fg=C["muted"], bg=C["card"],
                   activebackground=C["gray_bg"], activeforeground=C["text"], padx=px(8), pady=px(3),
                   command=self.show_about).pack(side="right", padx=(0, px(10)))
        sign = "⌘" if IS_MAC else "Ctrl"
        FlatButton(zoom, text="−", font=font(12, True), bg=C["card"], fg=C["text"], activebackground=C["gray_bg"],
                   padx=px(10), pady=px(3), command=lambda: self.zoom_step(-1)).pack(side="left")
        self.zoom_label = tk.Label(zoom, text="", font=font(10), fg=C["muted"], bg=C["card"], width=5)
        self.zoom_label.pack(side="left")
        FlatButton(zoom, text="+", font=font(12, True), bg=C["card"], fg=C["text"], activebackground=C["gray_bg"],
                   padx=px(10), pady=px(3), command=lambda: self.zoom_step(1)).pack(side="left")
        self.zoom_label.configure(text=f"{round(UI['zoom'] * 100)}%")
        lang_btn = FlatButton(nav, text=i18n.LANG.upper() + " ▾", font=font(10, True), fg=C["text"], bg=C["card"],
                              activebackground=C["gray_bg"], activeforeground=C["text"], padx=px(8), pady=px(3),
                              command=lambda: self.lang_menu(lang_btn))
        lang_btn.pack(side="right", padx=(0, px(6)))
        self._tip(self.zoom_label, _("Масштаб: {0} +  /  {1} −  /  {2} 0", sign, sign, sign))
        tk.Frame(root, bg=C["line"], height=1).pack(fill="x")
        self.banner = tk.Frame(root, bg=C["blue_bg"])   # плашка «доступно обновление»

        # Строка состояния пакуется раньше содержимого, чтобы не пропадать в маленьком окне
        self.status = tk.StringVar()
        bar = tk.Frame(root, bg=C["bar"])
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=C["line"], height=1).pack(fill="x")
        tk.Label(bar, textvariable=self.status, font=font(10), fg=C["muted"], bg=C["bar"],
                 anchor="w", padx=px(16), pady=px(6)).pack(fill="x")

        self.content = tk.Frame(root, bg=C["bg"])
        self.content.pack(fill="both", expand=True)

        # Горячие клавиши
        for key in ("plus", "equal", "KP_Add"):
            root.bind_all(f"<{MOD}-{key}>", lambda e: self.zoom_step(1))
        for key in ("minus", "KP_Subtract"):
            root.bind_all(f"<{MOD}-{key}>", lambda e: self.zoom_step(-1))
        root.bind_all(f"<{MOD}-Key-0>", lambda e: self.set_zoom(1.0))
        root.bind_all(f"<{MOD}-o>", lambda e: self.open_files())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self._fit_nav, add="+")

        self.frames = {
            "phone": ScrollFrame(self.content, C["bg"]),
            "parts": ScrollFrame(self.content, C["bg"]),
            "logs": self._build_logs(),
            "history": self._build_history(),
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
        self.restore_window()
        root.after(4000, self.auto_check)
        if initial_paths:
            root.after(200, lambda: self.load(list(initial_paths)))

    # ------------------------------------------------------------- окно и масштаб
    def _style_trees(self):
        rh = font(11).metrics("linespace") + px(12)
        self.style.configure("Treeview", font=font(11), rowheight=rh)
        self.style.configure("Treeview.Heading", font=font(10, True), padding=(px(6), px(4)))

    def _fit_nav(self, e=None):
        """Верхнее меню на узком окне: прячем название программы, сокращаем подписи."""
        if e is not None and e.widget is not self.root:
            return
        width = self.root.winfo_width()
        b = self.nav_buttons["kb"]
        full = sum(w.winfo_reqwidth() for w in self.nav.winfo_children() if w is not self.nav_title) + px(140)
        short = width < full + self.nav_title.winfo_reqwidth()
        if short and self.nav_title.winfo_ismapped():
            self.nav_title.pack_forget()
        elif not short and not self.nav_title.winfo_ismapped():
            self.nav_title.pack(side="left", padx=(0, px(20)), before=self.nav_buttons["phone"])
        b.configure(text=self.nav_long["kb"][1 if width < full else 0])

    def _update_minsize(self):
        self.root.update_idletasks()
        self.root.minsize(min(px(720), self.root.winfo_screenwidth() - 40),
                          min(px(500), self.root.winfo_screenheight() - 80))

    def restore_window(self):
        """Размер и место окна: как в прошлый раз, если помещается на текущий экран,
        иначе 85% экрана по центру."""
        self._update_minsize()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        saved = self.history.setting("window", {}) or {}
        geo = saved.get("geometry", "")
        m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", geo)
        if m:
            w, h, x, y = map(int, m.groups())
            fits = w <= sw and h <= sh and -50 <= x <= sw - 200 and 0 <= y <= sh - 100
        else:
            fits = False
        if not fits:
            w = min(px(1200), int(sw * 0.85))
            h = min(px(820), int(sh * 0.85))
            x, y = (sw - w) // 2, max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        if saved.get("zoomed"):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def on_close(self):
        try:
            zoomed = self.root.state() == "zoomed"
            if zoomed:
                self.root.state("normal")
                self.root.update_idletasks()
            self.history.set_setting("window", {"geometry": self.root.geometry(), "zoomed": zoomed})
        except Exception:
            pass
        if self.update_file and updater.check_writable() is None:
            # скачанное обновление ставится при закрытии, без перезапуска
            try:
                new = updater.prepare(self.update_file, self._data_dir())
                updater.launch_installer(new, self._data_dir(), updater.current_version(), relaunch=False)
            except Exception:
                pass
        self.root.destroy()

    # ------------------------------------------------------------- обновления
    def _data_dir(self):
        return os.path.dirname(logs_root())

    def auto_check(self):
        if not self.history.setting("auto_update", True):
            return
        last = self.history.setting("update_checked", "")
        try:
            if last and (datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < 6 * 3600:
                return
        except ValueError:
            pass
        self.check_updates(manual=False)

    def check_updates(self, manual=True):
        if self.update_busy:
            return
        self.update_busy = True
        skip = self.history.setting("skip_version", "")
        data = self._data_dir()

        def work():
            try:
                info = updater.check_latest()
                self.events.put(("update_checked", None))
                newer = updater.is_newer(info["version"], updater.current_version())
                if not newer or (not manual and info["version"] == skip):
                    self.events.put(("update_none", manual))
                    return
                path = None
                if updater.can_self_update() and info["asset"]:
                    path = updater.downloaded_path(data, info["version"])
                    if not (os.path.isfile(path) and os.path.getsize(path) == info["asset"]["size"]):
                        self.events.put(("update_progress", (0, info["asset"]["size"] or 0)))
                        updater.download(info["asset"], path,
                                         lambda d, t: self.events.put(("update_progress", (d, t))))
                self.events.put(("update_ready", (info, path)))
            except Exception as e:
                self.events.put(("update_failed", (manual, f"{e.__class__.__name__}: {e}")))

        threading.Thread(target=work, daemon=True).start()

    def _update_event(self, kind, data):
        if kind == "update_checked":
            self.history.set_setting("update_checked", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return
        if kind == "update_progress":
            d, t = data
            self.status.set(_("Скачиваю обновление… {0}%", d * 100 // t if t else 0))
            return
        self.update_busy = False
        if kind == "update_none":
            if data:
                messagebox.showinfo(APP_TITLE, _("У вас последняя версия ({0}).", updater.current_version()))
            self.update_status()
        elif kind == "update_failed":
            manual, err = data
            self.update_status()
            if manual:
                messagebox.showwarning(APP_TITLE, _("Не удалось проверить обновления.\nПроверьте интернет.\n\n") + err)
        elif kind == "update_ready":
            self.update_info, self.update_file = data
            self.update_status()
            self.show_update_banner()

    def show_update_banner(self):
        info = self.update_info
        for w in self.banner.winfo_children():
            w.destroy()
        inner = tk.Frame(self.banner, bg=C["blue_bg"], padx=px(16), pady=px(8))
        inner.pack(fill="x")
        ready = bool(self.update_file)
        if ready:
            button(inner, _("Перезапустить и обновить"), self.install_update, True, size=10).pack(side="right")
        else:
            button(inner, _("Скачать"), lambda: open_path(info["url"]), True, size=10).pack(side="right")
        button(inner, _("Позже"), self.hide_update_banner, size=10).pack(side="right", padx=px(6))
        button(inner, _("Что нового"), self.show_release_notes, size=10).pack(side="right")
        FlatButton(inner, text=_("Пропустить версию"), font=font(10), fg=C["muted"], bg=C["blue_bg"],
                   activebackground=C["blue_bg"], activeforeground=C["text"], padx=px(8),
                   command=self.skip_update).pack(side="right", padx=px(6))
        text = _("Доступна версия {0} (у вас {1}).", info['version'], updater.current_version())
        text += _(" Скачана — установится при перезапуске или закрытии программы.") if ready else ""
        label(inner, text, 11, True, bg=C["blue_bg"], wrap=400).pack(side="left")
        self.banner.pack(fill="x", before=self.content)

    def hide_update_banner(self):
        self.banner.pack_forget()

    def skip_update(self):
        if self.update_info:
            self.history.set_setting("skip_version", self.update_info["version"])
        self.update_file = None      # пропущенную версию и при закрытии не ставим
        self.update_info = None
        self.hide_update_banner()

    def show_release_notes(self):
        info = self.update_info
        w = self.popup(_("Что нового в {0}", info['version']), 0.6, 0.7)
        fr, t = text_view(w)
        fr.pack(fill="both", expand=True)
        parts = [(_("Версия {0}\n", info['version']), "h1")]
        for line in info["notes"].splitlines():
            line = line.rstrip()
            if line.startswith("#"):
                parts.append((line.lstrip("# ") + "\n", "cap"))
            elif line:
                parts.append((line.replace("**", "").replace("`", "") + "\n", "body"))
        text_fill(t, parts)

    def install_update(self, relaunch=True):
        if self.phone_state == "reading":
            return messagebox.showinfo(APP_TITLE, _("Сейчас снимаются логи с телефона. Обновите после того, как программа закончит."))
        reason = updater.check_writable()
        if reason:
            return messagebox.showwarning(APP_TITLE, reason)
        try:
            new = updater.prepare(self.update_file, self._data_dir())
            self.history.save()
            updater.launch_installer(new, self._data_dir(), updater.current_version(), relaunch)
        except Exception as e:
            return messagebox.showerror(APP_TITLE, _("Не удалось установить обновление:\n{0}\n\nПрограмма и ваши данные не изменены.", e))
        self.update_file = None
        self.on_close()

    def lang_menu(self, widget):
        m = tk.Menu(self.root, tearoff=0, font=font(10))
        for code, name in i18n.LANGS.items():
            m.add_radiobutton(label=name, value=code, variable=tk.StringVar(value=i18n.LANG),
                              command=lambda c=code: self.set_language(c))
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def set_language(self, code):
        if code == i18n.LANG:
            return
        self.history.set_setting("lang", code)
        i18n.set_lang(code)   # чтобы вопрос ниже был уже на новом языке
        if messagebox.askyesno(APP_TITLE, _("Язык изменится после перезапуска программы. Перезапустить сейчас?")):
            self.restart()

    def restart(self):
        cmd = [sys.executable] if getattr(sys, "frozen", False) else \
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ios_panic_reader.py")]
        try:
            if IS_MAC and getattr(sys, "frozen", False):
                app = updater.install_target()
                subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open "{app}"'], start_new_session=True)
            else:
                subprocess.Popen(cmd, start_new_session=True) if not IS_WIN else \
                    subprocess.Popen(cmd, creationflags=0x00000200)
        except Exception as e:
            messagebox.showwarning(APP_TITLE, _("Перезапустите программу вручную.") + f"\n{e}")
        self.on_close()

    def show_about(self):
        w = self.popup(_("О программе"), w_frac=None)
        w.configure(padx=px(24), pady=px(20))
        label(w, "iOS Panic Reader", 16, True).pack(anchor="w")
        label(w, _("Версия {0}", updater.current_version()), 11, color=C["muted"]).pack(anchor="w", pady=(0, px(12)))
        label(w, _("Ваши данные (история, логи, заметки) хранятся отдельно от программы и при обновлении не удаляются:"), 10, wrap=440).pack(anchor="w")
        FlatButton(w, text=self._data_dir(), font=font(10), fg=C["blue"], bg=C["card"], activebackground=C["card"],
                   activeforeground="#1e3a8a", padx=0, command=lambda: open_path(self._data_dir())).pack(anchor="w",
                                                                                                    pady=(0, px(12)))
        auto = tk.BooleanVar(value=self.history.setting("auto_update", True))
        tk.Checkbutton(w, text=_("Проверять и скачивать обновления автоматически"), variable=auto,
                       bg=C["card"], activebackground=C["card"], font=font(10),
                       command=lambda: self.history.set_setting("auto_update", auto.get())).pack(anchor="w")
        row = tk.Frame(w, bg=C["card"])
        row.pack(anchor="w", pady=(px(14), 0))
        button(row, _("Проверить обновления"), lambda: (w.destroy(), self.check_updates(manual=True)),
               True, size=10).pack(side="left")
        button(row, _("Все версии"), lambda: open_path(updater.RELEASES_PAGE), size=10).pack(side="left", padx=px(8))

    def zoom_step(self, d):
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - UI["zoom"]))
        self.set_zoom(ZOOMS[max(0, min(len(ZOOMS) - 1, i + d))])

    def set_zoom(self, z):
        if z == UI["zoom"]:
            return
        apply_zoom(z)
        self.history.set_setting("zoom", z)
        self.zoom_label.configure(text=f"{round(z * 100)}%")
        self._style_trees()
        self._update_minsize()
        # экраны, которые рисуются заново, подхватят новые отступы
        self.render_phone()
        if self.current_tab == "parts":
            self.render_parts()
        elif self.current_tab == "history":
            self.show_phone_history()
        self.status.set(_("Масштаб {0}%", round(z * 100)))

    def _tip(self, widget, text):
        """Подсказка при наведении."""
        tip = {}

        def show(e):
            t = tk.Toplevel(widget)
            t.wm_overrideredirect(True)
            t.geometry(f"+{e.x_root + 12}+{e.y_root + 16}")
            tk.Label(t, text=text, font=font(9), bg="#111827", fg="#ffffff", padx=px(8), pady=px(4)).pack()
            tip["w"] = t

        def hide(e):
            if tip.get("w"):
                tip.pop("w").destroy()
        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def popup(self, title, w_frac=0.75, h_frac=0.8, modal=False):
        """Дополнительное окно по центру главного, с размером от главного окна."""
        w = tk.Toplevel(self.root, bg=C["card"])
        w.title(title)
        w.transient(self.root)
        self.root.update_idletasks()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        if w_frac:
            ww, wh = max(px(480), int(rw * w_frac)), max(px(320), int(rh * h_frac))
            w.geometry(f"{ww}x{wh}+{rx + (rw - ww) // 2}+{ry + (rh - wh) // 3}")
        else:
            w.withdraw()
            w.after_idle(lambda: self._center(w))
        w.bind("<Escape>", lambda e: w.destroy())
        if modal:
            w.after_idle(lambda: (w.grab_set(), w.focus_force()))
        return w

    def _center(self, w):
        w.update_idletasks()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        w.geometry(f"+{rx + max(0, (rw - ww) // 2)}+{ry + max(0, (rh - wh) // 3)}")
        w.deiconify()

    # ------------------------------------------------------------- навигация
    def show(self, key):
        for k, f in self.frames.items():
            f.pack_forget()
        self.frames[key].pack(fill="both", expand=True, padx=0, pady=0)
        for k, b in self.nav_buttons.items():
            on = k == key
            b.configure(bg=C["nav_on"] if on else C["card"], fg="#ffffff" if on else C["text"],
                        activebackground=C["nav_on"] if on else C["gray_bg"],
                        activeforeground="#ffffff" if on else C["text"], font=font(11, on))
        self.current_tab = key
        if key == "parts":
            self.render_parts()
        elif key == "history":
            self.refresh_history()
        self.update_status()

    def update_status(self):
        panics = sum(l["is_panic"] for l in self.logs)
        s = {
            "nodriver": _("Служба Apple Mobile Device не найдена") if IS_WIN else _("Нет связи с usbmuxd"),
            "wait": _("Ожидание iPhone…"),
            "trust": _("iPhone подключён · ожидание подтверждения «Доверять»"),
            "unlock": _("iPhone подключён · разблокируйте телефон"),
            "reading": _("Снимаю логи…"),
        }.get(self.phone_state, "")
        if self.logs:
            s = (s + " · " if s else "") + f"{len(self.logs)} {plural(len(self.logs), 'лог', 'лога', 'логов')}, " \
                f"{panics} {plural(panics, 'паника', 'паники', 'паник')}"
        if self.dev and self.dev.get("dir"):
            s = (s + " · " if s else "") + _("сохранены в ") + self.dev["dir"]
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
                    self.part_filter = None
                    self.after_repair = True
                    self.archive = None   # архив пополнился — для поиска перечитаем
                    self.load([self.dev["dir"]], quiet=True)
                    self.prev_visit = self.history.add_visit(
                        self.dev, build_verdict(self.view_logs(), self.dev), self.view_logs())
                    self.phone_state = "result"
                    self.render_phone()
                    self.show("phone")
                elif kind == "disconnected":
                    if self.phone_state != "result":
                        self.phone_state = "wait"
                        self.render_phone()
                elif kind == "archive_ready":
                    self.archive, self.archive_busy = ev[1], False
                    self.update_status()
                    if self.current_tab == "kb":
                        self._kb_refresh()
                elif kind.startswith("update_"):
                    self._update_event(kind, ev[1])
                elif kind == "erased":
                    messagebox.showinfo(APP_TITLE, _("Старые логи на телефоне стёрты. Копия осталась в папке с логами на компьютере."))
                elif kind == "erase_failed":
                    messagebox.showerror(APP_TITLE, _("Не удалось стереть логи на телефоне:\n") + ev[1])
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
                messagebox.showinfo(APP_TITLE, _("Новых логов не найдено."))
            else:
                self.phone_state = "result"
                self.render_phone()
                self.show("phone")
        self.update_status()
        return new

    def open_files(self):
        fs = filedialog.askopenfilenames(title=_("Выберите логи"), filetypes=[
            (_("Логи iOS"), "*.ips *.panic *.log *.txt *.synced *.crash"), (_("Все файлы"), "*.*")])
        if fs:
            self.load(fs)

    def open_folder(self):
        d = filedialog.askdirectory(title=_("Папка с логами"), initialdir=logs_root())
        if d:
            self.load([d])

    def again(self):
        if self.watcher:
            self.watcher.manual.put("*")
        self.phone_state = "wait"
        self.dev = None
        self.prev_visit = None
        self.render_phone()

    # ------------------------------------------------------------- ремонт
    def repair_info(self):
        """(datetime, заметка) последней отметки ремонта текущего телефона или None."""
        if not self.dev:
            return None
        return self.history.last_repair(phone_key(self.dev))

    def view_logs(self):
        """Логи, по которым строится вывод: после ремонта (если он отмечен) или все."""
        r = self.repair_info()
        if r and self.after_repair:
            return core.logs_since(self.logs, r[0])
        return self.logs

    def toggle_repair_view(self):
        self.after_repair = not self.after_repair
        self.refresh_logs()
        self.render_phone()

    def mark_repair(self):
        if not self.dev:
            return
        w = self.popup(_("Отметить ремонт"), w_frac=None, modal=True)
        w.configure(padx=px(24), pady=px(20))
        w.resizable(False, False)
        label(w, _("Отметить ремонт"), 16, True).pack(anchor="w")
        label(w, _("С этого момента программа будет показывать только новые сбои — так видно, помог ли ремонт. Подключите телефон после ремонта ещё раз."), 11, color=C["muted"],
              wrap=460).pack(anchor="w", pady=(px(4), px(12)))
        label(w, _("Что сделано"), 10, True, C["muted"]).pack(anchor="w")
        note = tk.StringVar()
        e = ttk.Entry(w, textvariable=note, width=52, font=font(11))
        e.pack(anchor="w", pady=(px(2), px(10)), fill="x")
        e.focus_set()
        erase = tk.BooleanVar(value=False)
        if self.watcher:
            tk.Checkbutton(w, text=_("Стереть старые логи на телефоне (копия останется на компьютере)"),
                           variable=erase, bg=C["card"], activebackground=C["card"],
                           font=font(10)).pack(anchor="w")
        row = tk.Frame(w, bg=C["card"])
        row.pack(anchor="e", pady=(px(16), px(0)))

        def save():
            if erase.get() and not messagebox.askyesno(
                    APP_TITLE, _("Стереть все логи сбоев на телефоне?\n\nКопия уже сохранена в папке с логами на компьютере."), parent=w):
                return
            self.history.add_repair(self.dev, note.get().strip())
            if erase.get() and self.watcher:
                self.watcher.erase.put(self.dev["udid"])
            self.after_repair = True
            w.destroy()
            self.refresh_logs()
            self.render_phone()

        button(row, _("Отмена"), w.destroy).pack(side="left", padx=(px(0), px(8)))
        button(row, _("Отметить"), save, True).pack(side="left")
        w.bind("<Return>", lambda ev: save())

    def open_part_logs(self, part):
        self.part_filter = part
        self.only_panic.set(False)
        self.log_q.set("")
        self.refresh_logs()
        self.show("logs")
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])

    # ------------------------------------------------------------- PDF
    def save_pdf(self):
        if not self.logs and not self.dev:
            return
        if not report_pdf.available():
            messagebox.showwarning(APP_TITLE, _("PDF недоступен (нет модуля reportlab или шрифта). Сохраню текстовый отчёт."))
            return self.save_report()
        ws = self.history.setting("workshop", None)
        if ws is None:
            ws = simpledialog.askstring(APP_TITLE, _("Название мастерской для отчёта\n(можно оставить пустым, изменить — во вкладке «История»):"), parent=self.root) or ""
            self.history.set_setting("workshop", ws)
        name = (self.dev or {}).get("model", _("телефон"))
        f = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                         initialfile=_("Диагностика {0} {1}.pdf", name, f"{datetime.now():%Y-%m-%d}"))
        if not f:
            return
        note = (self.history.get(phone_key(self.dev)) or {}).get("note", "") if self.dev else ""
        rep = self.repair_info() if self.after_repair else None
        try:
            report_pdf.build_pdf(f, self.view_logs(), self.dev, self.device_lines(), ws, rep, note)
        except Exception as e:
            return messagebox.showerror(APP_TITLE, _("Не удалось сохранить PDF:\n{0}", e))
        self.status.set(_("PDF сохранён: ") + f)
        open_path(f)

    def save_report(self):
        if not self.logs and not self.dev:
            return
        name = (self.dev or {}).get("model", _("телефон"))
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[(_("Текст"), "*.txt")],
                                         initialfile=_("Отчёт {0} {1}.txt", name, f"{datetime.now():%Y-%m-%d}"))
        if not f:
            return
        out = []
        logs = self.view_logs()
        problems = build_verdict(logs, self.dev)
        out.append(_("ОТЧЁТ iOS Panic Reader · {0}", f"{datetime.now():%d.%m.%Y %H:%M}"))
        out.append("=" * 72)
        out += [f"{k}: {v}" for k, v in self.device_lines()]
        out.append("")
        if problems:
            out.append(_("НАЙДЕННЫЕ ПРОБЛЕМЫ:"))
            for i, p in enumerate(problems, 1):
                lvl = _("ВАЖНО") if p["level"] == "red" else _("НЕ СРОЧНО")
                out.append(f"{i}. {p['title']} [{lvl}] — {p['note']}")
                out.append(_("   Как ведёт себя: {0}", p['how']))
                out.append(_("   Почему: {0}", p['why']))
                out.append(_("   Что делать: ") + "; ".join(p["fix"]))
        else:
            out.append(_("ПРОБЛЕМ НЕ НАЙДЕНО"))
        out.append("")
        out.append(_("ДЕТАЛИ:"))
        for name_, data, fails, lvl in parts_table(logs, self.dev):
            out.append(_("  {0}: {1} · сбои: {2}", name_, data, fails))
        out.append("")
        out.append(build_summary(logs))
        out.append("")
        for l in logs:
            if l["is_panic"]:
                out.append(build_report(l))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
        self.status.set(_("Отчёт сохранён: ") + f)

    def device_lines(self):
        d = self.dev
        if not d:
            ls = [l for l in self.logs if l["product"]]
            if ls:
                return [(_("Устройство"), core.device_label(ls[0])), ("iOS", ls[0]["os"] or "—"),
                        (_("Источник"), _("файлы логов"))]
            return []
        out = [(_("Модель"), f"{d['model']} ({d['product']})"), ("iOS", f"{d['ios']} ({d['build']})"),
               (_("Серийный номер"), d.get("serial") or "—"), ("IMEI", d.get("imei") or _("не прочитан"))]
        if d.get("battery_health") is not None:
            out.append((_("Аккумулятор"), _("{0}% ({1}), {2} циклов", d['battery_health'], d.get('battery_mah', ''), d.get('battery_cycles', '?'))))
        return out

    # ------------------------------------------------------------- экран «Телефон»
    def render_phone(self):
        sf = self.frames["phone"]
        sf.clear()
        st = self.phone_state
        if st == "result":
            return self._phone_result(sf.body)
        center = tk.Frame(sf.body, bg=C["bg"])
        center.pack(expand=True, pady=px(70), padx=px(24))

        def big(title, text, color=C["blue"], symbol="📱"):
            tk.Label(center, text=symbol, font=(F, 46), fg=color, bg=C["bg"]).pack()
            label(center, title, 22, True, bg=C["bg"]).pack(pady=(px(10), px(6)))
            if text:
                label(center, text, 13, color=C["muted"], bg=C["bg"], wrap=560).pack()

        row = None
        if st == "nodriver":
            if IS_WIN:
                big(_("Компьютер не видит iPhone"), _("Не установлен драйвер Apple. Без него Windows не может подключиться к телефону."), C["orange"], "⚠")
                lines = (_("1. Установите «Apple Devices» из Microsoft Store (или iTunes)"),
                         _("2. Переподключите кабель"),
                         _("3. Программа подхватит телефон сама"))
            else:
                big(_("Нет связи со службой iPhone"), _("Программа не может подключиться к службе usbmuxd, через которую компьютер общается с iPhone."), C["orange"], "⚠")
                lines = (_("1. Переподключите кабель (лучше оригинальный)"),
                         _("2. Проверьте, видит ли телефон Finder"),
                         _("3. Если нет — перезагрузите компьютер"))
            steps = tk.Frame(center, bg=C["card"], padx=px(20), pady=px(16), highlightbackground=C["line"],
                             highlightthickness=1)
            steps.pack(pady=px(18), fill="x")
            for s in lines:
                label(steps, s, 12).pack(anchor="w", pady=px(2))
            if not device_support():
                label(steps, _("Модуль pymobiledevice3 не найден — используйте собранную программу или выполните: pip install pymobiledevice3"), 10, color=C["red_text"],
                      wrap=520).pack(anchor="w", pady=(px(8), px(0)))
            row = tk.Frame(center, bg=C["bg"])
            if IS_WIN:
                button(row, _("Открыть Microsoft Store"),
                       lambda: open_path("ms-windows-store://search/?query=Apple%20Devices"),
                       True).pack(side="left", padx=px(5))
        elif st in ("wait", "start", "denied"):
            if st == "denied":
                big(_("На iPhone нажали «Не доверять»"), _("Отключите и снова подключите кабель, затем нажмите «Доверять»."), C["orange"], "⚠")
            else:
                big(_("Подключите iPhone кабелем"), _("Разблокируйте телефон и нажмите «Доверять». Программа сама снимет логи и покажет, что с телефоном."))
            row = tk.Frame(center, bg=C["bg"])
        elif st in ("trust", "unlock"):
            big(_("Нажмите «Доверять» на телефоне") if st == "trust" else _("Разблокируйте iPhone"),
                "", C["blue"], "🔓")
            steps = tk.Frame(center, bg=C["bg"])
            steps.pack(pady=px(10))
            for s in (_("1. Разблокируйте iPhone"), _("2. На экране появится вопрос — нажмите «Доверять»"),
                      _("3. Введите код-пароль телефона")):
                label(steps, s, 13, bg=C["bg"]).pack(anchor="w", pady=px(2))
            label(center, _("Окна нет? Отключите и снова подключите кабель."), 11, color=C["muted"],
                  bg=C["bg"]).pack(pady=px(8))
        elif st == "reading":
            d = self.dev or {}
            big(_("{0} подключён", d.get('model', 'iPhone')), _("Снимаю логи… Не отключайте кабель."))
            pb = ttk.Progressbar(center, mode="indeterminate", length=440)
            pb.pack(pady=px(20))
            pb.start(12)
        elif st == "error":
            big(_("Не удалось прочитать iPhone"), getattr(self, "error_text", ""), C["red"], "⚠")
            row = tk.Frame(center, bg=C["bg"])
            button(row, _("Попробовать снова"), self.again, True).pack(side="left", padx=px(5))
        if row is not None:
            row.pack(pady=px(16))
            button(row, _("Открыть файл лога…"), self.open_files).pack(side="left", padx=px(5))
            button(row, _("Открыть папку…"), self.open_folder).pack(side="left", padx=px(5))

    def _phone_result(self, body):
        wrap = tk.Frame(body, bg=C["bg"], padx=px(20), pady=px(20))
        wrap.pack(fill="both", expand=True)
        d = self.dev
        logs = self.view_logs()
        panics = [l for l in logs if l["is_panic"]]
        repair = self.repair_info()

        # Левая колонка — карточка телефона
        left = tk.Frame(wrap, bg=C["bg"])
        o, c = card(left)
        o.pack(fill="x")
        if d:
            label(c, d["model"], 17, True).pack(anchor="w")
            label(c, f"iOS {d['ios']} · {d.get('serial', '')}", 10, color=C["muted"]).pack(anchor="w", pady=(px(2), px(10)))
        else:
            first = next((l for l in self.logs if l["product"]), None)
            label(c, first["model"] if first else _("Логи из файлов"), 17, True).pack(anchor="w")
            label(c, (first["os"] if first else "") or _("телефон не подключён"), 10,
                  color=C["muted"]).pack(anchor="w", pady=(px(2), px(10)))
        grid = tk.Frame(c, bg=C["card"])
        grid.pack(fill="x")
        stats = []
        if d and d.get("battery_health") is not None:
            h = d["battery_health"]
            stats.append((_("Аккумулятор"), f"{h}%", "green" if h >= 85 else ("orange" if h >= 80 else "red")))
        if d and d.get("battery_cycles") is not None:
            stats.append((_("Циклы"), str(d["battery_cycles"]), None))
        stats.append((_("Паник"), str(len(panics)), "green" if not panics else ("orange" if len(panics) < 3 else "red")))
        if d and d.get("is_iphone"):
            stats.append((_("Сеть / IMEI"), "OK" if d.get("imei") else _("нет"), "green" if d.get("imei") else "red"))
        for i, (k, v, lvl) in enumerate(stats):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(px(0), px(26)), pady=px(6))
            label(cell, k, 9, color=C["muted"]).pack(anchor="w")
            label(cell, v, 18, True, color=LEVEL[lvl][2] if lvl else C["text"]).pack(anchor="w")
        if d and d.get("imei"):
            label(c, "IMEI " + d["imei"], 10, color=C["muted"]).pack(anchor="w", pady=(px(8), px(0)))

        if self.prev_visit:
            v = self.prev_visit
            o, c = card(left, C["line"], C["gray_bg"])
            o.pack(fill="x", pady=(px(12), px(0)))
            label(c, _("ЭТОТ ТЕЛЕФОН УЖЕ БЫЛ"), 9, True, C["muted"], bg=C["gray_bg"]).pack(anchor="w")
            label(c, datetime.strptime(v["date"], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M"), 12, True,
                  bg=C["gray_bg"]).pack(anchor="w")
            label(c, ", ".join(v["problems"]) or _("проблем не было"), 10, bg=C["gray_bg"], wrap=260,
                  color=LEVEL[v.get("level", "green")][2]).pack(anchor="w", pady=(px(2), px(0)))
            if v.get("battery") is not None:
                label(c, _("Аккумулятор тогда: {0}%", v['battery']), 10, color=C["muted"], bg=C["gray_bg"]).pack(anchor="w")

        btns = tk.Frame(left, bg=C["bg"])
        btns.pack(fill="x", pady=px(12))
        if d:
            button(btns, _("Отметить ремонт"), self.mark_repair).pack(fill="x", pady=px(3))
        if self.watcher:
            button(btns, _("Подключить другой телефон"), self.again).pack(fill="x", pady=px(3))
        button(btns, _("Открыть файл лога…"), self.open_files).pack(fill="x", pady=px(3))

        # Правая колонка — вывод
        right = tk.Frame(wrap, bg=C["bg"])
        self._two_columns(wrap, left, right, px(330), px(900))
        problems = build_verdict(logs, d)
        wl = 640

        if repair:
            when, rnote = repair
            o, c = card(right, C["blue"], C["blue_bg"])
            o.pack(fill="x", pady=(px(0), px(12)))
            head = tk.Frame(c, bg=C["blue_bg"])
            head.pack(fill="x")
            button(head, _("Показать все логи") if self.after_repair else _("Только после ремонта"),
                   self.toggle_repair_view, size=10).pack(side="right", anchor="n")
            label(head, _("Ремонт отмечен {0}", f"{when:%d.%m.%Y %H:%M}") + (f": {rnote}" if rnote else ""), 12, True,
                  bg=C["blue_bg"], wrap=wl - 200).pack(side="left")
            if self.after_repair:
                if panics:
                    txt, col = (_("После ремонта снова {0} {1} — проблема не устранена или есть другая.", len(panics), plural(len(panics), 'паника', 'паники', 'паник'))), C["red_text"]
                else:
                    txt, col = _("После ремонта паник нет ✓  Показаны только новые сбои."), C["green_text"]
            else:
                txt, col = _("Показаны все логи, включая те, что были до ремонта."), C["muted"]
            label(c, txt, 11, color=col, bg=C["blue_bg"], wrap=wl).pack(anchor="w", pady=(px(4), px(0)))

        if not problems:
            o, c = card(right, C["green"], C["green_bg"], 2)
            o.pack(fill="x")
            label(c, _("ПРОБЛЕМ НЕ НАЙДЕНО"), 10, True, C["green_text"]).pack(anchor="w")
            label(c, _("Телефон в порядке"), 22, True, C["head"]).pack(anchor="w", pady=(px(4), px(6)))
            if repair and self.after_repair:
                msg = _("После ремонта не было ни одной паники ядра.") if not panics else \
                    _("После ремонта паники единичные и не указывают на конкретную деталь.")
            else:
                msg = _("В логах нет ни одной паники ядра.") if not panics else \
                    _("Паники единичные и не указывают на конкретную деталь.")
            if d and d.get("battery_health") is not None:
                msg += _(" Аккумулятор: {0}%.", d['battery_health'])
            label(c, msg, 12, color=C["text"], wrap=wl).pack(anchor="w")
        elif len(problems) == 1:
            self._problem_card(right, problems[0], wl, big=True)
        else:
            reds = sum(p["level"] == "red" for p in problems)
            label(right, _("НАЙДЕНО {0} {1} · от самой важной", len(problems), plural(len(problems), 'ПРОБЛЕМА', 'ПРОБЛЕМЫ', 'ПРОБЛЕМ')), 10, True, C["red_text"] if reds else C["orange_text"],
                  bg=C["bg"]).pack(anchor="w", pady=(px(0), px(8)))
            for i, p in enumerate(problems, 1):
                self._problem_card(right, p, wl, num=i)

        if any(l["is_panic"] for l in self.logs):
            self._chart(right, repair[0] if repair else None)

        # Что ещё нашлось в логах
        crashes = [l for l in logs if not l["is_panic"] and l["exception"]]
        jetsam = [l for l in logs if "Jetsam" in l["kind"] or l["bug_type"] == "298"]
        if crashes or jetsam:
            o, c = card(right)
            o.pack(fill="x", pady=(px(14), px(0)))
            label(c, _("Что ещё нашлось в логах"), 12, True).pack(anchor="w", pady=(px(0), px(6)))
            if crashes:
                apps = {}
                for l in crashes:
                    apps[l["process"] or "?"] = apps.get(l["process"] or "?", 0) + 1
                top = ", ".join(f"{a} ({n})" for a, n in sorted(apps.items(), key=lambda x: -x[1])[:4])
                self._dot_line(c, "orange", _("{0} {1} {2}: {3} — ошибки приложений, с железом не связано", len(crashes), plural(len(crashes), 'вылет', 'вылета', 'вылетов'), 'приложения' if len(crashes) == 1 else 'приложений', top), wl)
            if jetsam:
                self._dot_line(c, "gray", _("{0} раз не хватило памяти (Jetsam) — это нормально", len(jetsam)), wl)

        row = tk.Frame(right, bg=C["bg"])
        row.pack(anchor="w", pady=px(16))
        button(row, _("PDF для клиента"), self.save_pdf, True).pack(side="left", padx=(px(0), px(8)))
        button(row, _("Посмотреть логи"), lambda: self.show("logs")).pack(side="left", padx=(px(0), px(8)))
        button(row, _("Детали"), lambda: self.show("parts")).pack(side="left", padx=(px(0), px(8)))
        button(row, _("Отчёт .txt"), self.save_report).pack(side="left", padx=(px(0), px(8)))
        if d and d.get("dir"):
            button(row, _("Папка с логами"), lambda: open_path(d["dir"])).pack(side="left")

    def _chart(self, parent, repair_dt=None, days=30):
        """Столбики: паники по дням за последний месяц (по всем логам)."""
        data = core.panics_by_day(self.logs, days)
        if not any(n for _day, n in data):
            # все паники старше месяца — показываем месяц, заканчивающийся последней паникой
            last = max((core.log_local_dt(l) for l in self.logs if l["is_panic"] and core.log_local_dt(l)),
                       default=None)
            if last is None:
                return
            data = core.panics_by_day(self.logs, days, last)
        o, c = card(parent)
        o.pack(fill="x", pady=(px(14), px(0)))
        total = sum(n for _day, n in data)
        label(c, _("Паники по дням · {0} – {1} · всего {2}", f"{data[0][0]:%d.%m}", f"{data[-1][0]:%d.%m}", total), 12,
              True).pack(anchor="w", pady=(px(0), px(8)))
        H = px(130)
        cv = tk.Canvas(c, height=H + px(24), bg=C["card"], highlightthickness=0)
        cv.pack(fill="x")
        cv.bind("<Configure>", lambda e: self._draw_chart(cv, data, repair_dt, e.width, H))

    def _draw_chart(self, cv, data, repair_dt, W, H):
        cv.delete("all")
        top = max(n for _day, n in data) or 1
        step = W / len(data)
        bw = max(3, step * 0.65)
        cv.create_line(0, H, W, H, fill=C["line"])
        for i, (day, n) in enumerate(data):
            x = i * step + (step - bw) / 2
            if n:
                h = max(3, n / top * (H - px(18)))
                cv.create_rectangle(x, H - h, x + bw, H, fill=C["red"], outline="")
                cv.create_text(x + bw / 2, H - h - px(8), text=str(n), font=font(8), fill=C["muted"])
            if repair_dt and day == repair_dt.date():
                cv.create_line(x + bw / 2, 0, x + bw / 2, H, fill=C["blue"], width=2, dash=(4, 3))
                near_right = x + bw / 2 > W - px(70)     # у правого края подпись ставим слева от линии
                cv.create_text(x + bw / 2 + (-4 if near_right else 4), px(6), text=_("ремонт"),
                               anchor="ne" if near_right else "nw", font=font(8, True), fill=C["blue"])
            if i in (0, len(data) // 2, len(data) - 1):
                cv.create_text(min(max(x + bw / 2, px(18)), W - px(18)), H + px(12), text=f"{day:%d.%m}",
                               font=font(8), fill=C["muted"])

    @staticmethod
    def _two_columns(wrap, left, right, left_w, breakpoint):
        """Две колонки на широком окне, одна под другой — на узком."""
        state = {"mode": None}

        def layout(e=None):
            width = wrap.winfo_width()
            mode = "wide" if width >= breakpoint or width <= 1 else "narrow"
            if mode == state["mode"]:
                return
            state["mode"] = mode
            left.grid_forget()
            right.grid_forget()
            if mode == "wide":
                wrap.columnconfigure(0, weight=0, minsize=left_w)
                wrap.columnconfigure(1, weight=1)
                left.grid(row=0, column=0, sticky="new", padx=(0, px(20)))
                right.grid(row=0, column=1, sticky="nsew")
            else:
                wrap.columnconfigure(0, weight=1, minsize=0)
                wrap.columnconfigure(1, weight=0)
                left.grid(row=0, column=0, sticky="new", pady=(0, px(16)))
                right.grid(row=1, column=0, sticky="nsew")
        layout()
        wrap.bind("<Configure>", layout)

    def _dot_line(self, parent, lvl, text, wl):
        r = tk.Frame(parent, bg=parent["bg"])
        r.pack(anchor="w", pady=px(2), fill="x")
        tk.Label(r, text="●", fg=LEVEL[lvl][0], bg=parent["bg"], font=font(12)).pack(side="left", anchor="n")
        label(r, text, 11, wrap=wl).pack(side="left", padx=px(6))

    def _problem_card(self, parent, p, wl, big=False, num=None):
        border, bg, tcol = LEVEL[p["level"]]
        o, c = card(parent, border, bg, 2)
        o.pack(fill="x", pady=(px(0), px(12)))
        if big:
            label(c, _("НАЙДЕНА ПРОБЛЕМА") if p["level"] == "red" else _("ВОЗМОЖНАЯ ПРОБЛЕМА"), 10, True, tcol).pack(anchor="w")
            label(c, p["title"], 22, True, C["head"], wrap=wl).pack(anchor="w", pady=(px(4), px(8)))
        else:
            head = tk.Frame(c, bg=bg)
            head.pack(fill="x")
            label(head, _("ВАЖНО") if p["level"] == "red" else _("НЕ СРОЧНО"), 9, True, tcol).pack(side="right", anchor="n")
            label(head, f"{num}. {p['title']}", 15, True, C["head"], wrap=wl - 120).pack(side="left")
        for cap, txt in ((_("Как ведёт себя"), p["how"]), (_("Почему"), p["why"])):
            label(c, cap.upper(), 9, True, C["muted"]).pack(anchor="w", pady=(px(6), px(0)))
            label(c, txt, 11, wrap=wl).pack(anchor="w")
        label(c, _("ЧТО ДЕЛАТЬ"), 9, True, C["muted"]).pack(anchor="w", pady=(px(6), px(0)))
        for i, f in enumerate(p["fix"], 1):
            label(c, f"{i}. {f.rstrip('.')}", 11, wrap=wl).pack(anchor="w")
        foot = tk.Frame(c, bg=bg)
        foot.pack(fill="x", pady=(px(8), px(0)))
        # то, что справа, пакуется первым — иначе текст слева займёт всё место
        if p.get("count"):
            FlatButton(foot, text=_("Показать логи этой детали →"), font=font(10, True), fg=C["blue"], bg=bg,
                       activebackground=bg, activeforeground="#1e3a8a", padx=0, pady=0,
                       command=lambda part=p["part"]: self.open_part_logs(part)).pack(side="right", anchor="n")
        label(foot, _("Уверенность: ") + p["note"], 10, color=C["muted"], wrap=300).pack(side="left")

    # ------------------------------------------------------------- экран «Детали»
    def render_parts(self):
        sf = self.frames["parts"]
        sf.clear()
        body = tk.Frame(sf.body, bg=C["bg"], padx=px(20), pady=px(20))
        body.pack(fill="both", expand=True)
        title = (self.dev or {}).get("model") or next((l["model"] for l in self.logs if l["model"]), _("телефона"))
        label(body, _("Детали {0} — состояние и сбои", title), 18, True, bg=C["bg"]).pack(anchor="w")

        rows = parts_table(self.view_logs(), self.dev)
        counts = {k: sum(r[3] == k for r in rows) for k in ("green", "orange", "red")}
        cnt = tk.Frame(body, bg=C["bg"])
        cnt.pack(fill="x", pady=px(14))
        for lvl, txt in (("green", _("без сбоев")), ("orange", _("есть подозрения")), ("red", _("есть проблемы"))):
            o, c = card(cnt, LEVEL[lvl][0], LEVEL[lvl][1])
            o.pack(side="left", padx=(px(0), px(12)))
            label(c, str(counts[lvl]), 20, True, LEVEL[lvl][2]).pack(anchor="w")
            label(c, txt, 10).pack(anchor="w")

        o, c = card(body, C["blue"], C["blue_bg"])
        o.pack(fill="x", pady=(px(0), px(14)))
        label(c, _("Оригинальность деталей"), 11, True).pack(anchor="w")
        label(c, _("Посмотреть, какие детали заменены, можно на самом iPhone: Настройки → Основные → Об этом устройстве → «История деталей и обслуживания» (iOS 15.2+, iPhone XS и новее). Там будет «Оригинальная деталь Apple» или «Неизвестная деталь». Автоматическая проверка в программе появится после тестов на реальных телефонах."), 10, wrap=900).pack(anchor="w")

        o, tbl = card(body)
        o.pack(fill="x")
        heads = (_("Деталь"), _("Данные с телефона"), _("Сбои в логах"), _("Статус"))
        for j, h in enumerate(heads):
            label(tbl, h, 10, True, C["muted"]).grid(row=0, column=j, sticky="w", padx=px(8), pady=(px(0), px(8)))
        tbl.columnconfigure(1, weight=1)
        tbl.columnconfigure(2, weight=1)
        status_txt = {"green": _("в порядке"), "orange": _("подозрение"), "red": _("проблема")}
        for i, (name, data, fails, lvl) in enumerate(rows, 1):
            bgc = LEVEL[lvl][1] if lvl != "green" else C["card"]
            cells = [label(tbl, name, 11, True, bg=bgc, wrap=260),
                     label(tbl, data, 10, color=C["muted"], bg=bgc, wrap=300),
                     label(tbl, fails, 10, lvl != "green", LEVEL[lvl][2] if lvl != "green" else C["green_text"],
                           bg=bgc, wrap=320),
                     label(tbl, "● " + status_txt[lvl], 10, True, LEVEL[lvl][2], bg=bgc)]
            for j, w in enumerate(cells):
                w.grid(row=i, column=j, sticky="nsew", padx=0, pady=px(1), ipadx=px(8), ipady=px(7))

        row = tk.Frame(body, bg=C["bg"])
        row.pack(anchor="w", pady=px(14))
        button(row, _("Сохранить отчёт"), self.save_report, True).pack(side="left", padx=(px(0), px(8)))
        button(row, _("Посмотреть логи"), lambda: self.show("logs")).pack(side="left")

    # ------------------------------------------------------------- экран «Все логи»
    def _build_logs(self):
        root = tk.Frame(self.content, bg=C["bg"], padx=px(16), pady=px(14))
        bar = tk.Frame(root, bg=C["bg"])
        bar.pack(fill="x", pady=(px(0), px(10)))
        label(bar, _("Поиск"), 11, color=C["muted"], bg=C["bg"]).pack(side="left")
        self.log_q = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.log_q, width=22, font=font(11))
        e.pack(side="left", padx=px(8))
        self.only_panic = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text=_("Только паники"), variable=self.only_panic, bg=C["bg"], font=font(11),
                       command=self.refresh_logs, activebackground=C["bg"]).pack(side="left", padx=px(8))
        self.chip_row = tk.Frame(root, bg=C["bg"])
        self.filter_chip = FlatButton(self.chip_row, text="", font=font(10, True), bg=C["blue"], fg="#ffffff",
                                      activebackground="#1d4ed8", activeforeground="#ffffff", padx=px(12), pady=px(4),
                                      command=self._clear_part_filter)
        button(bar, _("Открыть файлы…"), self.open_files, size=10).pack(side="right", padx=px(3))
        button(bar, _("Открыть папку…"), self.open_folder, size=10).pack(side="right", padx=px(3))
        self.log_q.trace_add("write", lambda *_: self.refresh_logs())
        self.filter_chip.pack(side="left")
        label(self.chip_row, _("показаны только паники этой детали — нажмите, чтобы снять фильтр"), 10,
              color=C["muted"], bg=C["bg"]).pack(side="left", padx=px(10))

        paned = ttk.PanedWindow(root, orient="horizontal")
        split_panes(paned, 0.5)
        self.logs_paned = paned
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=C["card"])
        self.tree = ttk.Treeview(left, columns=("what", "date", "kind"), show="headings", selectmode="browse")
        for c_, t, w in (("what", _("Что случилось"), 330), ("date", _("Дата"), 140), ("kind", _("Вид"), 170)):
            self.tree.heading(c_, text=t)
            self.tree.column(c_, width=px(w), minwidth=px(80), anchor="w", stretch=(c_ == "what"))
        for lvl in ("red", "orange", "gray"):
            self.tree.tag_configure(lvl, foreground=LEVEL[lvl][2])
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        paned.add(left, weight=1)

        right = tk.Frame(paned, bg=C["card"])
        fr, self.log_text = text_view(right)
        fr.pack(fill="both", expand=True)
        rb = tk.Frame(right, bg=C["card"], padx=px(12), pady=px(8))
        rb.pack(fill="x")
        button(rb, _("Исходный текст лога"), self.show_raw, size=10).pack(side="left")
        button(rb, _("Полный разбор"), self.show_full, size=10).pack(side="left", padx=px(6))
        paned.add(right, weight=1)
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
            return _("Паника: ") + (core.PART_NAMES[part] if part else main_cause(l))
        if l["exception"]:
            return _("{0} закрылось", l['process'] or 'Приложение')
        if "Jetsam" in l["kind"]:
            return _("Не хватило памяти")
        return core.tkind(l["kind"])

    def _clear_part_filter(self):
        self.part_filter = None
        self.refresh_logs()

    def refresh_logs(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        q = self.log_q.get().lower().strip()
        visible = {id(l) for l in self.view_logs()}
        if self.part_filter:
            self.filter_chip.configure(text=_("Деталь: {0}  ✕", core.PART_NAMES[self.part_filter]))
            self.chip_row.pack(fill="x", pady=(px(0), px(10)), before=self.logs_paned)
        else:
            self.chip_row.pack_forget()
        for i, l in enumerate(self.logs):
            if id(l) not in visible:
                continue
            if self.part_filter and not (l["is_panic"] and core.panic_part(l) == self.part_filter):
                continue
            if self.only_panic.get() and not l["is_panic"]:
                continue
            title = self._log_title(l)
            if q and q not in (title + l["panic"] + l["process"] + os.path.basename(l["file"])).lower():
                continue
            self.tree.insert("", "end", iid=str(i), tags=(self._log_level(l),),
                             values=("● " + title, str(l["date"])[:16], core.tkind(l["kind"])))
        kids = self.tree.get_children()
        if kids and not self.tree.selection():
            self.tree.selection_set(kids[0])

    def _selected_log(self):
        sel = self.tree.selection()
        return self.logs[int(sel[0])] if sel else None

    def show_log(self):
        l = self._selected_log()
        if l:
            text_fill(self.log_text, self._log_parts(l))

    def _log_parts(self, l):
        parts = [(f"{str(l['date'])[:19]} · {core.tkind(l['kind'])}\n", "small"), (self._log_title(l) + "\n", "h1")]
        if l["missing_sensors"]:
            parts.append((_("ТЕЛЕФОН НЕ ВИДИТ ДАТЧИКИ\n"), "cap"))
            for s in l["missing_sensors"]:
                d = core.sensor_info(s)
                parts.append((f"• {s} — {d['name']}. {d['where']}\n", "body"))
        e = l["findings"][0][0] if l["findings"] else None
        if e:
            parts += [(_("КАК ВЕДЁТ СЕБЯ\n"), "cap"), (e["symptoms"] + "\n", "body"),
                      (_("ПОЧЕМУ\n"), "cap"), (e["cause"] + "\n", "body"),
                      (_("ЧТО ДЕЛАТЬ\n"), "cap"), (e["fix"] + "\n", "body")]
            if len(l["findings"]) > 1:
                parts.append((_("ЕЩЁ НАЙДЕНО В ЛОГЕ\n"), "cap"))
                parts += [(f"• {fe['title']}\n", "body") for fe, _hit in l["findings"][1:]]
        else:
            parts.append((_("\nИзвестных ошибок не найдено. Посмотрите исходный текст лога.\n"), "body"))
        if l["exception"]:
            parts += [(_("ИСКЛЮЧЕНИЕ\n"), "cap"), (l["exception"] + "\n", "body")]
        parts += [(_("\nУСТРОЙСТВО\n"), "cap"), (f"{core.device_label(l)} · {l['os'] or '—'}\n", "body"),
                  (_("ФАЙЛ\n"), "cap"), (l["file"] + "\n", "small")]
        if l["panic"]:
            first = next((x.strip() for x in l["panic"].splitlines() if x.strip()), "")
            parts += [(_("\nПЕРВАЯ СТРОКА ПАНИКИ\n"), "cap"), (first[:400] + "\n", "mono")]
        for bus, rows in core.i2c_hints(l):
            parts.append((_("ШИНА {0} У ЭТОЙ МОДЕЛИ\n", bus.upper()), "cap"))
            parts += [(f"• {r['parts']}\n", "body") for r in rows]
        return parts

    def _popup(self, title, content):
        w = self.popup(title)
        t = tk.Text(w, wrap="none", font=font(10, family=MONO), bd=0, padx=px(10), pady=px(8))
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
            self._popup(_("Разбор: ") + os.path.basename(l["file"]), build_report(l))

    # ------------------------------------------------------------- экран «История»
    def _build_history(self):
        root = tk.Frame(self.content, bg=C["bg"], padx=px(16), pady=px(14))
        bar = tk.Frame(root, bg=C["bg"])
        bar.pack(fill="x", pady=(px(0), px(10)))
        label(bar, _("Телефоны, которые подключали"), 14, True, bg=C["bg"]).pack(side="left")
        self.hist_q = tk.StringVar()
        ttk.Entry(bar, textvariable=self.hist_q, width=26, font=font(11)).pack(side="right")
        label(bar, _("Поиск"), 11, color=C["muted"], bg=C["bg"]).pack(side="right", padx=px(8))
        self.hist_q.trace_add("write", lambda *_: self.refresh_history())

        ws = tk.Frame(root, bg=C["bg"])
        ws.pack(fill="x", pady=(px(0), px(10)))
        label(ws, _("Мастерская (для PDF):"), 10, color=C["muted"], bg=C["bg"]).pack(side="left")
        self.ws_var = tk.StringVar(value=self.history.setting("workshop", ""))
        ttk.Entry(ws, textvariable=self.ws_var, width=40, font=font(10)).pack(side="left", padx=px(8))
        button(ws, _("Сохранить"), lambda: (self.history.set_setting("workshop", self.ws_var.get().strip()),
                                         self.status.set(_("Название мастерской сохранено"))), size=10).pack(side="left")

        paned = ttk.PanedWindow(root, orient="horizontal")
        split_panes(paned, 0.55)
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=C["card"])
        self.htree = ttk.Treeview(left, columns=("model", "serial", "last", "result"), show="headings",
                                  selectmode="browse")
        for c_, t, w in (("model", _("Модель"), 140), ("serial", _("Серийный"), 130), ("last", _("Последний визит"), 130),
                         ("result", _("Результат"), 220)):
            self.htree.heading(c_, text=t)
            self.htree.column(c_, width=px(w), anchor="w")
        for lvl in ("red", "orange", "green"):
            self.htree.tag_configure(lvl, foreground=LEVEL[lvl][2])
        sb = ttk.Scrollbar(left, orient="vertical", command=self.htree.yview)
        self.htree.configure(yscrollcommand=sb.set)
        self.htree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        paned.add(left, weight=3)
        self.hdetail = ScrollFrame(paned, C["card"])
        paned.add(self.hdetail, weight=2)
        self.htree.bind("<<TreeviewSelect>>", lambda e: self.show_phone_history())
        return root

    def refresh_history(self):
        sel = self.htree.selection()
        self.htree.delete(*self.htree.get_children())
        q = self.hist_q.get().lower().strip()
        items = sorted(self.history.phones.items(),
                       key=lambda kv: (kv[1]["visits"][-1]["date"] if kv[1]["visits"] else ""), reverse=True)
        for key, p in items:
            v = p["visits"][-1] if p["visits"] else {}
            result = ", ".join(v.get("problems", [])) or _("в порядке")
            row = (p.get("model", "?"), p.get("serial", key), v.get("date", "")[:16], result)
            if q and q not in (" ".join(row) + p.get("note", "") + p.get("imei", "")).lower():
                continue
            self.htree.insert("", "end", iid=key, values=row, tags=(v.get("level", "green"),))
        if sel and self.htree.exists(sel[0]):
            self.htree.selection_set(sel[0])
        elif self.htree.get_children():
            self.htree.selection_set(self.htree.get_children()[0])
        else:
            self.hdetail.clear()
            label(self.hdetail.body, _("Здесь появятся телефоны после первого подключения."), 11,
                  color=C["muted"], wrap=380).pack(anchor="w", padx=px(18), pady=px(18))

    def show_phone_history(self):
        sel = self.htree.selection()
        if not sel:
            return
        key = sel[0]
        p = self.history.get(key)
        sf = self.hdetail
        sf.clear()
        b = tk.Frame(sf.body, bg=C["card"], padx=px(18), pady=px(16))
        b.pack(fill="both", expand=True)
        label(b, p.get("model", "?"), 17, True).pack(anchor="w")
        label(b, _("Серийный {0}", p.get('serial', key)) + (f" · IMEI {p['imei']}" if p.get("imei") else ""), 10,
              color=C["muted"]).pack(anchor="w", pady=(px(2), px(10)))

        label(b, _("ЗАМЕТКА"), 9, True, C["muted"]).pack(anchor="w")
        t = tk.Text(b, height=4, width=40, font=font(11), wrap="word", bd=1, relief="solid",
                    highlightthickness=0)
        t.insert("1.0", p.get("note", ""))
        t.pack(fill="x", pady=(px(2), px(6)))
        button(b, _("Сохранить заметку"), lambda: (self.history.set_note(key, t.get("1.0", "end").strip()),
                                                self.status.set(_("Заметка сохранена"))), size=10).pack(anchor="w")

        if p.get("repairs"):
            label(b, _("РЕМОНТЫ"), 9, True, C["muted"]).pack(anchor="w", pady=(px(14), px(2)))
            for r in reversed(p["repairs"]):
                when = datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
                label(b, f"{when:%d.%m.%Y %H:%M} — {r.get('note') or _("без описания")}", 11, wrap=380).pack(anchor="w")

        label(b, _("ВИЗИТЫ ({0})", len(p['visits'])), 9, True, C["muted"]).pack(anchor="w", pady=(px(14), px(2)))
        for v in reversed(p["visits"]):
            when = datetime.strptime(v["date"], "%Y-%m-%d %H:%M:%S")
            row = tk.Frame(b, bg=C["card"])
            row.pack(fill="x", pady=px(3))
            tk.Label(row, text="●", fg=LEVEL[v.get("level", "green")][0], bg=C["card"],
                     font=font(11)).pack(side="left", anchor="n")
            col = tk.Frame(row, bg=C["card"])
            col.pack(side="left", padx=px(6), fill="x")
            label(col, f"{when:%d.%m.%Y %H:%M} · iOS {v.get('ios', '?')}", 10, True).pack(anchor="w")
            info = ", ".join(v.get("problems", [])) or _("проблем не найдено")
            extra = []
            if v.get("battery") is not None:
                extra.append(_("аккумулятор {0}%", v['battery']))
            extra.append(_("паник {0}", v.get('panics', 0)))
            label(col, info + " · " + ", ".join(extra), 10, color=C["muted"], wrap=360).pack(anchor="w")

        row = tk.Frame(b, bg=C["card"])
        row.pack(anchor="w", pady=(px(16), px(0)))
        folder = next((os.path.join(logs_root(), n) for n in os.listdir(logs_root())
                       if n.endswith("_" + p.get("serial", key))), None)
        if folder:
            button(row, _("Открыть логи"), lambda: self.open_history_logs(folder), size=10).pack(side="left", padx=(px(0), px(8)))

        def delete():
            if messagebox.askyesno(APP_TITLE, _("Удалить этот телефон из истории?\n(логи на диске останутся)")):
                self.history.delete(key)
                self.refresh_history()
        button(row, _("Удалить из истории"), delete, size=10).pack(side="left")

    def open_history_logs(self, folder):
        self.dev = None
        self.prev_visit = None
        self.logs.clear()
        self.known.clear()
        self.part_filter = None
        self.load([folder], quiet=True)
        self.phone_state = "result"
        self.render_phone()
        self.show("phone")

    # ------------------------------------------------------------- экран «Поиск»
    def _build_kb(self):
        root = tk.Frame(self.content, bg=C["bg"], padx=px(16), pady=px(14))
        self.archive = None          # все логи из папки Logs (строится при первом поиске по архиву)
        self.archive_busy = False
        self.search_results = {}     # iid → ("entry"|"sensor"|"i2c"|"log", ключ)

        bar = tk.Frame(root, bg=C["bg"])
        bar.pack(fill="x")
        label(bar, _("Поиск по ошибкам и паникам"), 14, True, bg=C["bg"]).pack(side="left")
        button(bar, _("Разобрать текст паники…"), self.paste_panic, True, size=10).pack(side="right")
        row = tk.Frame(root, bg=C["bg"])
        row.pack(fill="x", pady=(px(8), 0))
        self.kb_q = tk.StringVar()
        ent = ttk.Entry(row, textvariable=self.kb_q, font=font(12))
        ent.pack(side="left", fill="x", expand=True, ipady=px(3))
        self.root.bind_all(f"<{MOD}-f>", lambda e: (self.show("kb"), ent.focus_set()))
        label(root, _("Код ошибки, слово, датчик, процесс или строка из паники. Например: 4013, mic1, перезагружается, SEP, i2c3, SpringBoard"), 10, color=C["muted"], bg=C["bg"],
              wrap=700).pack(anchor="w", pady=(px(4), 0))

        opts = tk.Frame(root, bg=C["bg"])
        opts.pack(fill="x", pady=(px(8), 0))
        self.search_scope = tk.StringVar(value="base_logs")
        for val, txt in (("base", _("Только база")), ("base_logs", _("База + открытые логи")),
                         ("all", _("База + все логи в архиве"))):
            tk.Radiobutton(opts, text=txt, value=val, variable=self.search_scope, bg=C["bg"],
                           activebackground=C["bg"], font=font(10),
                           command=self._kb_refresh).pack(side="left", padx=(0, px(14)))

        chips = tk.Frame(root, bg=C["bg"])
        chips.pack(fill="x", pady=px(8))
        self.kb_cat = "Все"
        self.chip_buttons = {}
        short = {"Паника ядра": _("Паники"), "Датчики (Missing sensor)": _("Датчики"),
                 "Вылет приложения": _("Приложения"), "Ошибка iTunes / восстановления": _("Ошибки iTunes"),
                 "Симптомы телефона": _("Симптомы"), "Логи и версии iOS": _("Логи и iOS"), "Шины I2C": _("Шины I2C")}
        for cat in ["Все", "Симптомы телефона"] + [c_ for c_ in CATEGORIES if c_ != "Симптомы телефона"] + [_("Шины I2C")]:
            b = FlatButton(chips, text=_(short.get(cat, cat)), font=font(10), padx=px(14), pady=px(5),
                           highlightthickness=1, highlightbackground="#cfd6df",
                           command=lambda c_=cat: self._kb_pick(c_))
            b.pack(side="left", padx=px(3))
            self.chip_buttons[cat] = b

        paned = ttk.PanedWindow(root, orient="horizontal")
        split_panes(paned, 0.42)
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=C["card"])
        self.ktree = ttk.Treeview(left, columns=("where",), show="tree headings", selectmode="browse")
        self.ktree.heading("#0", text=_("Найдено"))
        self.ktree.heading("where", text=_("Раздел / телефон"))
        self.ktree.column("#0", width=px(330), stretch=True)
        self.ktree.column("where", width=px(160), stretch=False)
        for lvl in ("red", "orange", "gray"):
            self.ktree.tag_configure(lvl, foreground=LEVEL[lvl][2])
        self.ktree.tag_configure("group", font=font(10, True))
        sb = ttk.Scrollbar(left, orient="vertical", command=self.ktree.yview)
        self.ktree.configure(yscrollcommand=sb.set)
        self.ktree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        paned.add(left, weight=1)
        right = tk.Frame(paned, bg=C["card"])
        fr, self.kb_text = text_view(right)
        fr.pack(fill="both", expand=True)
        rb = tk.Frame(right, bg=C["card"], padx=px(12), pady=px(8))
        rb.pack(fill="x")
        self.kb_raw_btn = button(rb, _("Исходный текст лога"), self._kb_open_raw, size=10)
        paned.add(right, weight=1)
        self.ktree.bind("<<TreeviewSelect>>", lambda e: self._kb_show())
        self._kb_after = None
        self.kb_q.trace_add("write", lambda *_: self._kb_schedule())
        self._kb_pick("Все")
        return root

    def _kb_schedule(self):
        # поиск после паузы в наборе, чтобы не искать на каждую букву
        if self._kb_after:
            self.root.after_cancel(self._kb_after)
        self._kb_after = self.root.after(250, self._kb_refresh)

    def _kb_pick(self, cat):
        self.kb_cat = cat
        for c_, b in self.chip_buttons.items():
            on = c_ == cat
            b.configure(bg=C["blue"] if on else C["card"], fg="#ffffff" if on else C["text"],
                        activebackground=C["blue"] if on else C["gray_bg"],
                        activeforeground="#ffffff" if on else C["text"])
        self._kb_refresh()

    def _archive_logs(self):
        """Все логи из папки архива; первый раз читаются в фоне."""
        if self.archive is not None:
            return self.archive
        if not self.archive_busy:
            self.archive_busy = True
            self.status.set(_("Читаю архив логов для поиска…"))

            def work():
                logs = []
                for f in collect_files([logs_root()]):
                    try:
                        logs.append(parse_log(f))
                    except Exception:
                        pass
                self.events.put(("archive_ready", logs))
            threading.Thread(target=work, daemon=True).start()
        return None

    def _kb_refresh(self):
        self._kb_after = None
        self.ktree.delete(*self.ktree.get_children())
        self.search_results = {}
        q = self.kb_q.get().strip()
        cat = self.kb_cat
        # база
        if q:
            rows = core.search_db(q)
        else:
            rows = [("entry", i, e["title"], e["cat"]) for i, e in enumerate(KB)]
            rows += [("sensor", k, _("Датчик {0} — {1}", k, d['name']), "Датчики (Missing sensor)") for k, d in SENSORS.items()]
            rows += [("i2c", i, _("Шина {0} — ", b['bus']) + ", ".join(dict.fromkeys(PRODUCTS.get(m, m) for m in b["models"])),
                      _("Шины I2C")) for i, b in enumerate(core.I2C_BUSES)]
        rows = [r for r in rows if cat == "Все" or r[3] == cat]
        g_db = self.ktree.insert("", "end", text=_("В базе ошибок ({0})", len(rows)), open=True, tags=("group",))
        for n, (typ, key, title, c_) in enumerate(rows):
            iid = f"{typ}:{key}"
            self.ktree.insert(g_db, "end", iid=iid, text=title, values=(_(c_),))
            self.search_results[iid] = (typ, key)
        # логи
        scope = self.search_scope.get()
        if q and scope != "base":
            pool = self.logs
            if scope == "all":
                arch = self._archive_logs()
                if arch is None:
                    self.ktree.insert("", "end", text=_("В логах: читаю архив…"), tags=("group",))
                    return self._kb_select_first()
                known = {l["file"] for l in pool}
                pool = pool + [l for l in arch if l["file"] not in known]
            found = sorted(core.search_logs(pool, q), key=lambda l: str(l["date"]), reverse=True)
            g_logs = self.ktree.insert("", "end", text=_("В логах ({0})", len(found)), open=True, tags=("group",))
            for n, l in enumerate(found[:500]):
                iid = f"log:{n}"
                phone = os.path.basename(os.path.dirname(l["file"])) if scope == "all" else (l["model"] or "")
                self.ktree.insert(g_logs, "end", iid=iid, tags=(self._log_level(l),),
                                  text=f"{str(l['date'])[:16]}  {self._log_title(l)}", values=(phone,))
                self.search_results[iid] = ("log", l)
        self._kb_select_first()

    def _kb_select_first(self):
        for g in self.ktree.get_children():
            kids = self.ktree.get_children(g)
            if kids:
                self.ktree.selection_set(kids[0])
                self.ktree.see(kids[0])
                return
        text_fill(self.kb_text, [(_("Ничего не найдено. Попробуйте другое слово или код.\n"), "body")])

    def _entry_parts(self, e):
        parts = [(_(e["cat"]) + "\n", "small"), (e["title"] + "\n", "h1"),
                 (_("УЗЕЛ\n"), "cap"), (e["node"] + "\n", "body")]
        if e.get("models"):
            parts += [(_("МОДЕЛИ\n"), "cap"), (e["models"] + "\n", "body")]
        if e.get("ios"):
            parts += [(_("ВЕРСИИ iOS\n"), "cap"), (e["ios"] + "\n", "body")]
        parts += [(_("КАК ВЕДЁТ СЕБЯ ТЕЛЕФОН\n"), "cap"), (e["symptoms"] + "\n", "body"),
                  (_("ПОЧЕМУ\n"), "cap"), (e["cause"] + "\n", "body"),
                  (_("ЧТО ДЕЛАТЬ\n"), "cap"), (e["fix"] + "\n", "body")]
        n = sum(1 for l in self.logs for fe, _hit in l["findings"] if fe is e)
        if n:
            parts.append((_("\nВстречается в открытых логах: {0} раз(а)\n", n), "red"))
        if e.get("patterns"):
            parts += [(_("КАК ВЫГЛЯДИТ В ЛОГЕ\n"), "cap"), ("  ".join(e["patterns"]) + "\n", "mono")]
        if e.get("confidence"):
            parts += [(_("НАДЁЖНОСТЬ\n"), "cap"), (core.CONFIDENCE.get(e["confidence"], e["confidence"]) + "\n", "small")]
        if e.get("sources"):
            parts += [(_("ИСТОЧНИКИ\n"), "cap")] + [(core.source_url(s) + "\n", "small") for s in e["sources"]]
        return parts

    def _kb_show(self):
        sel = self.ktree.selection()
        self.kb_raw_btn.pack_forget()
        if not sel or sel[0] not in self.search_results:
            return
        typ, key = self.search_results[sel[0]]
        if typ == "sensor":
            d = SENSORS[key]
            parts = [(_("Датчики (Missing sensor)\n"), "small"), (_("Датчик {0} — {1}\n", key, d['name']), "h1"),
                     (_("ГДЕ СТОИТ\n"), "cap"), (d["where"] + "\n", "body")]
            if d.get("models"):
                parts += [(_("ПО МОДЕЛЯМ\n"), "cap"), (d["models"] + "\n", "body")]
            parts += [(_("ЧТО ДЕЛАТЬ\n"), "cap"), (d["fix"] + "\n", "body"),
                      (_("КАК ВЕДЁТ СЕБЯ\n"), "cap"),
                      (_("Если датчика нет, телефон перезагружается каждые ~3 минуты (паника thermalmonitord).\n"), "body")]
            if d.get("sources"):
                parts += [(_("ИСТОЧНИКИ\n"), "cap")] + [(core.source_url(s) + "\n", "small") for s in d["sources"]]
        elif typ == "i2c":
            b = core.I2C_BUSES[key]
            names = ", ".join(f"{PRODUCTS.get(m, m)} ({m})" for m in b["models"])
            parts = [(_("Шины I2C\n"), "small"), (_("Шина {0}\n", b['bus']), "h1"), (_("МОДЕЛИ\n"), "cap"), (names + "\n", "body"),
                     (_("ЧТО НА ЭТОЙ ШИНЕ\n"), "cap"), (b["parts"] + "\n", "body"),
                     (_("КАК ПОЛЬЗОВАТЬСЯ\n"), "cap"),
                     (_("Если в панике есть эта шина (например, «i2c3::_checkBusStatus SCL is stuck low»), отключайте по одной детали из списка и смотрите, пропадёт ли паника. У других моделей назначение шин другое.\n"), "body"),
                     (_("ИСТОЧНИК\n"), "cap"), (core.source_url(b["source"]) + "\n", "small")]
        elif typ == "log":
            parts = self._log_parts(key)
            self.kb_raw_btn.pack(side="left")
        else:
            parts = self._entry_parts(KB[key])
        text_fill(self.kb_text, parts)

    def _kb_open_raw(self):
        sel = self.ktree.selection()
        if sel and sel[0] in self.search_results and self.search_results[sel[0]][0] == "log":
            l = self.search_results[sel[0]][1]
            self._popup(os.path.basename(l["file"]), l["raw"])

    def paste_panic(self):
        """Окно: вставить текст паники (например, скопированный с телефона) и сразу получить разбор."""
        w = self.popup(_("Разобрать текст паники"), 0.7, 0.75)
        w.configure(padx=px(18), pady=px(14))
        label(w, _("Вставьте текст паники или лога"), 14, True).pack(anchor="w")
        label(w, _("На iPhone: Настройки → Конфиденциальность и безопасность → Аналитика и улучшения → Данные аналитики → файл panic-full… → кнопка «Поделиться» → скопируйте текст."),
              10, color=C["muted"], wrap=600).pack(anchor="w", pady=(px(2), px(8)))
        top = tk.Frame(w, bg=C["card"])
        top.pack(fill="x")
        label(top, _("Модель (необязательно, для подсказок по шинам I2C):"), 10).pack(side="left")
        models = [""] + [f"{v} ({k})" for k, v in sorted(PRODUCTS.items(), key=lambda kv: kv[1])]
        model = ttk.Combobox(top, values=models, state="readonly", width=34, font=font(10))
        model.pack(side="left", padx=px(8))
        t = tk.Text(w, height=12, font=font(10, family=MONO), wrap="word", bd=1, relief="solid",
                    highlightthickness=0, padx=px(8), pady=px(6))
        t.pack(fill="both", expand=True, pady=px(8))
        t.focus_set()
        row = tk.Frame(w, bg=C["card"])
        row.pack(fill="x")

        def paste():
            try:
                t.insert("insert", self.root.clipboard_get())
            except tk.TclError:
                pass

        def analyze():
            text = t.get("1.0", "end").strip()
            if not text:
                return
            m = re.search(r"\(([^()]+)\)$", model.get())
            info = parse_pasted(text, m.group(1) if m else "")
            w.destroy()
            self._popup(_("Разбор вставленного текста"), build_report(info))

        button(row, _("Вставить из буфера"), paste, size=10).pack(side="left")
        button(row, _("Разобрать"), analyze, True, size=10).pack(side="right")
        button(row, _("Отмена"), w.destroy, size=10).pack(side="right", padx=px(8))


def set_window_icon(root):
    """Иконка окна и панели задач (значок самого файла программы задаётся при сборке)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "assets", "icon_256.png")
    try:
        root._icon = tk.PhotoImage(file=path)    # ссылку держим, иначе картинку удалит сборщик мусора
        root.iconphoto(True, root._icon)
    except (tk.TclError, OSError):
        pass


def run_gui(initial_paths=()):
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # чёткий текст на экранах с масштабом
        except Exception:
            pass
    root = tk.Tk()
    set_window_icon(root)
    App(root, initial_paths)
    root.mainloop()
