# -*- coding: utf-8 -*-
"""История телефонов: визиты, отметки ремонта, заметки, настройки мастерской.
Хранится в Документы/iOSPanicReader/history.json."""

import json
import os
from datetime import datetime

from core import logs_root

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def data_dir():
    return os.path.dirname(logs_root())


def phone_key(dev):
    return dev.get("serial") or dev.get("udid") or ""


class History:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "history.json")
        self.data = {"phones": {}, "settings": {}}
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            self.data["phones"] = loaded.get("phones", {})
            self.data["settings"] = loaded.get("settings", {})
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # --- телефоны
    @property
    def phones(self):
        return self.data["phones"]

    def get(self, key):
        return self.phones.get(key)

    def _phone(self, dev):
        key = phone_key(dev)
        p = self.phones.setdefault(key, {"visits": [], "repairs": [], "note": "",
                                         "first_seen": datetime.now().strftime(DATE_FMT)})
        for k in ("model", "product", "serial", "name", "imei"):
            if dev.get(k):
                p[k] = dev[k]
        return key, p

    def add_visit(self, dev, problems, logs):
        """Записывает визит; возвращает предыдущий визит (или None)."""
        key, p = self._phone(dev)
        prev = p["visits"][-1] if p["visits"] else None
        p["visits"].append({
            "date": datetime.now().strftime(DATE_FMT),
            "ios": dev.get("ios", ""),
            "battery": dev.get("battery_health"),
            "cycles": dev.get("battery_cycles"),
            "panics": sum(l["is_panic"] for l in logs),
            "problems": [x["title"] for x in problems],
            "level": problems[0]["level"] if problems else "green",
        })
        self.save()
        return prev

    def add_repair(self, dev, note):
        key, p = self._phone(dev)
        p["repairs"].append({"date": datetime.now().strftime(DATE_FMT), "note": note})
        self.save()

    def last_repair(self, key):
        p = self.get(key)
        if p and p.get("repairs"):
            r = p["repairs"][-1]
            return datetime.strptime(r["date"], DATE_FMT), r.get("note", "")
        return None

    def set_note(self, key, note):
        if key in self.phones:
            self.phones[key]["note"] = note
            self.save()

    def delete(self, key):
        if self.phones.pop(key, None) is not None:
            self.save()

    # --- настройки
    def setting(self, name, default=""):
        return self.data["settings"].get(name, default)

    def set_setting(self, name, value):
        self.data["settings"][name] = value
        self.save()
