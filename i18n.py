# -*- coding: utf-8 -*-
"""Языки интерфейса: русский (исходный), английский, украинский.

Тексты в коде пишутся по-русски и оборачиваются в _(): _("Найдено {0} паник", n).
Переводы — в translations.json: {"русский текст": {"en": "...", "uk": "..."}}.
Язык выбирается до загрузки остальных модулей (они переводят строки при импорте),
поэтому смена языка вступает в силу после перезапуска программы.
"""

import json
import locale
import os
import sys

LANGS = {"ru": "Русский", "en": "English", "uk": "Українська"}
_tr = {}
LANG = "ru"


def _base():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _settings_path():
    return os.path.join(os.path.expanduser("~"), "Documents", "iOSPanicReader", "history.json")


def system_lang():
    try:
        code = (locale.getlocale()[0] or os.environ.get("LANG", "") or "").lower()
    except ValueError:
        code = ""
    if sys.platform == "darwin":
        try:   # программа с окном на Mac не получает LANG — спрашиваем систему
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                                 text=True, timeout=3).stdout
            first = out.replace("(", "").replace('"', "").split(",")[0].strip().lower()
            code = first or code
        except Exception:
            pass
    if sys.platform == "win32" and not code:
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            code = {0x19: "ru", 0x22: "uk"}.get(lcid, "en")
        except Exception:
            pass
    for key, lang in (("uk", "uk"), ("ukrain", "uk"), ("ru", "ru"), ("russian", "ru")):
        if code.startswith(key):
            return lang
    return "en"


def saved_lang():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f).get("settings", {}).get("lang")
    except (OSError, ValueError):
        return None


def set_lang(lang):
    global LANG, _tr
    LANG = lang if lang in LANGS else "ru"
    _tr = {}
    if LANG != "ru":
        try:
            with open(os.path.join(_base(), "translations.json"), encoding="utf-8") as f:
                data = json.load(f)
            _tr = {k: v[LANG] for k, v in data.items() if isinstance(v, dict) and v.get(LANG)}
        except (OSError, ValueError):
            _tr = {}


def init():
    set_lang(os.environ.get("IOSPR_LANG") or saved_lang() or system_lang())


def _(text, *args):
    s = _tr.get(text, text)
    return s.format(*args) if args else s


# Множественное число: формы для числа n
_FORMS = {
    "ru": lambda n: 0 if n % 10 == 1 and n % 100 != 11 else (1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2),
    "uk": lambda n: 0 if n % 10 == 1 and n % 100 != 11 else (1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2),
    "en": lambda n: 0 if n == 1 else 2,
}


def plural(n, one, few, many):
    """Русские формы на входе; для другого языка берутся переводы каждой формы."""
    form = (one, few, many)[_FORMS.get(LANG, _FORMS["ru"])(abs(int(n)))]
    return _(form)


init()
