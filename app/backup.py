# -*- coding: utf-8 -*-
"""Перенос настроек и данных между компьютерами: один файл .zip.

В файле: manifest.json, settings.json (тема, язык, масштаб, мастерская…), history.json (телефоны,
визиты, ремонты, заметки), user_kb.json (свои описания ошибок) и по желанию Logs/ (логи телефонов).
Загрузка ДОБАВЛЯЕТ данные к уже имеющимся и ничего не затирает; перед ней сохраняется копия истории.
"""

import json
import os
import shutil
import zipfile
from datetime import datetime

import core
from history import History, data_dir

FORMAT = "iospr-backup"
PORTABLE_SETTINGS = ("theme", "lang", "zoom", "auto_update", "workshop")   # без размера окна и служебного


def export_backup(path, include_logs=False, version=""):
    """Сохранить настройки и данные в path (.zip). Возвращает сводку: сколько чего сохранено."""
    h = History()
    settings = {k: v for k, v in h.data["settings"].items() if k in PORTABLE_SETTINGS}
    user_kb = core._user_entries()
    n_logs = 0
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"format": FORMAT, "version": version,
                                                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                "logs": include_logs}, ensure_ascii=False, indent=1))
        z.writestr("settings.json", json.dumps(settings, ensure_ascii=False, indent=1))
        z.writestr("history.json", json.dumps({"phones": h.phones}, ensure_ascii=False, indent=1))
        z.writestr("user_kb.json", json.dumps(user_kb, ensure_ascii=False, indent=1))
        if include_logs:
            root = core.logs_root()
            for folder, _dirs, files in os.walk(root):
                for fn in files:
                    full = os.path.join(folder, fn)
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                    z.write(full, "Logs/" + rel)
                    n_logs += 1
    os.replace(tmp, path)
    return {"phones": len(h.phones), "entries": len(user_kb), "logs": n_logs, "settings": len(settings)}


def _safe_log_path(name):
    """Logs/<папка>/<файл> → путь внутри папки логов; всё подозрительное (.., абсолютные пути) — None."""
    if not name.startswith("Logs/") or name.endswith("/"):
        return None
    parts = name[5:].split("/")
    if not parts or any(p in ("", ".", "..") or ":" in p or "\\" in p for p in parts):
        return None
    root = os.path.abspath(core.logs_root())
    full = os.path.abspath(os.path.join(root, *parts))
    return full if full.startswith(root + os.sep) else None


def _merge_list(local, incoming, key="date"):
    seen = {x.get(key) for x in local}
    added = [x for x in incoming if x.get(key) not in seen]
    return sorted(local + added, key=lambda x: x.get(key) or ""), len(added)


def import_backup(path):
    """Загрузить файл переноса. Возвращает сводку; ValueError — если это не файл переноса."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError(str(e))
    with z:
        names = set(z.namelist())
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError):
            raise ValueError("manifest.json")
        if manifest.get("format") != FORMAT:
            raise ValueError("format")

        def read(name, default):
            if name not in names:
                return default
            try:
                return json.loads(z.read(name))
            except ValueError:
                return default

        # копия текущей истории — на всякий случай
        h = History()
        if os.path.isfile(h.path):
            bdir = os.path.join(data_dir(), "backups")
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(h.path, os.path.join(bdir, f"history-before-import-{datetime.now():%Y%m%d-%H%M%S}.json"))

        summary = {"phones_new": 0, "phones_merged": 0, "visits": 0, "repairs": 0, "entries": 0, "logs": 0,
                   "settings": 0}
        # настройки
        for k, v in read("settings.json", {}).items():
            if k in PORTABLE_SETTINGS:
                h.data["settings"][k] = v
                summary["settings"] += 1
        # телефоны
        for key, p in (read("history.json", {}).get("phones") or {}).items():
            if not isinstance(p, dict):
                continue
            mine = h.phones.get(key)
            if not mine:
                h.phones[key] = p
                summary["phones_new"] += 1
                continue
            mine["visits"], nv = _merge_list(mine.get("visits", []), p.get("visits", []))
            mine["repairs"], nr = _merge_list(mine.get("repairs", []), p.get("repairs", []))
            summary["visits"] += nv
            summary["repairs"] += nr
            note_in = (p.get("note") or "").strip()
            note_my = (mine.get("note") or "").strip()
            if note_in and note_in not in note_my:
                mine["note"] = (note_my + "\n" + note_in).strip()
            for k in ("model", "product", "serial", "name", "imei", "first_seen"):
                if p.get(k) and not mine.get(k):
                    mine[k] = p[k]
            summary["phones_merged"] += 1
        h.save()
        # свои описания ошибок: новые добавляются, свои с тем же id остаются
        have = {e.get("id") for e in core._user_entries()}
        for e in read("user_kb.json", []):
            if isinstance(e, dict) and e.get("title") and e.get("id") not in have:
                core.save_user_entry(e)
                summary["entries"] += 1
        # логи: только новые файлы, только внутрь папки логов
        for name in names:
            dst = _safe_log_path(name)
            if dst and not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(name) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
                summary["logs"] += 1
    return summary
