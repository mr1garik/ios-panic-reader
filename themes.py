# -*- coding: utf-8 -*-
"""Цветовые темы окна. Тема выбирается до создания окна (смена — после перезапуска).

Ключи палитры:
  bg, card, bar, line, border  — фон окна, карточек, строки состояния, разделители, рамки
  text, head, muted            — текст обычный, заголовки, второстепенный
  blue, accent_hover, blue_bg  — акцент (кнопки, вкладка, ссылки), он же при наведении, светлый фон акцента
  on_accent, link_hover        — текст на акценте, ссылка при наведении
  red/orange/green(_text/_bg)  — уровни: проблема, подозрение, в порядке
  gray, gray_bg, stripe        — нейтральный, фон наведения, полоска через строку в списках
  tip_bg, tip_fg               — подсказка
"""

import subprocess
import sys

_LIGHT = dict(
    bg="#eef1f5", card="#ffffff", bar="#f7f8fa", line="#e3e7ec", border="#cfd6df",
    text="#1f2937", head="#111827", muted="#4b5563",
    blue="#2563eb", accent_hover="#1d4ed8", blue_bg="#eff6ff", on_accent="#ffffff", link_hover="#1e3a8a",
    red="#dc2626", red_text="#b91c1c", red_bg="#fef2f2",
    orange="#ea580c", orange_text="#b45309", orange_bg="#fff7ed",
    green="#16a34a", green_text="#15803d", green_bg="#f0fdf4",
    gray="#9ca3af", gray_bg="#f3f4f6", stripe="#f8fafc", tip_bg="#111827", tip_fg="#ffffff",
)

_DARK = dict(
    bg="#0f1115", card="#171a21", bar="#12151b", line="#262b35", border="#353c49",
    text="#e5e7eb", head="#f9fafb", muted="#9ca3af",
    blue="#3b82f6", accent_hover="#2563eb", blue_bg="#16213a", on_accent="#ffffff", link_hover="#93c5fd",
    red="#ef4444", red_text="#f87171", red_bg="#2a1416",
    orange="#f97316", orange_text="#fbbf24", orange_bg="#2a1d0f",
    green="#22c55e", green_text="#4ade80", green_bg="#0f2418",
    gray="#6b7280", gray_bg="#20242c", stripe="#1b1f27", tip_bg="#f9fafb", tip_fg="#111827",
)

THEMES = {
    "light": dict(_LIGHT),
    "dark": dict(_DARK),
    "night": dict(_DARK, bg="#0b1220", card="#111a2e", bar="#0d1526", line="#1e2a44", border="#2b3a5c",
                  muted="#94a3b8", blue="#60a5fa", accent_hover="#3b82f6", blue_bg="#14244a",
                  on_accent="#0b1220", link_hover="#bfdbfe", gray_bg="#18233b", stripe="#14203a"),
    "mint": dict(_LIGHT, bg="#eef5f3", bar="#f5faf8", line="#dce9e5", border="#c4d8d2",
                 blue="#0d9488", accent_hover="#0f766e", blue_bg="#ecfdf9", link_hover="#115e59",
                 gray_bg="#eef4f2", stripe="#f6fbf9"),
    "graphite": dict(_DARK, bg="#141414", card="#1e1e1e", bar="#181818", line="#2c2c2c", border="#3d3d3d",
                     muted="#a3a3a3", blue="#f59e0b", accent_hover="#d97706", blue_bg="#2a2112",
                     on_accent="#111111", link_hover="#fcd34d", gray_bg="#262626", stripe="#222222"),
}

# Названия по-русски — переводятся через i18n при показе
NAMES = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная", "night": "Синяя ночь",
         "mint": "Мятная", "graphite": "Графит"}
DARK_THEMES = {"dark", "night", "graphite"}


def system_is_dark():
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True,
                                 text=True, timeout=3).stdout
            return "dark" in out.lower()
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        pass
    return False


def resolve(name):
    """Ключ темы → (ключ, палитра). «system» превращается в светлую или тёмную."""
    if name == "system" or name not in THEMES:
        name = "dark" if system_is_dark() else "light"
    return name, THEMES[name]
