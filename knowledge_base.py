# -*- coding: utf-8 -*-
"""
База ошибок iOS Panic Reader — загрузка из одного файла errors_db.json.

В errors_db.json:
  meta        — версия базы, дата обновления, источники (sources), уровни надёжности
  categories  — разделы
  products    — коды моделей (iPhone14,5 → iPhone 13)
  bug_types   — типы логов
  file_kinds  — вид лога по имени файла: [regex, описание]
  sensors     — датчики из строки «Missing sensor(s)»
  i2c_buses   — что висит на шинах I2C у конкретных моделей
  entries     — ошибки: id, cat, title, patterns (regex для поиска в логе), node, symptoms,
                cause, fix, models, ios, keywords (слова для поиска), sources, confidence

Более новую базу можно положить в Документы/iOSPanicReader/errors_db.json — она будет
использована, если её версия не ниже встроенной. Свои записи — в user_kb.json (см. core).
Все подсказки — ориентир для диагностики, а не окончательный диагноз.
"""

import json
import os
import sys

import i18n

DB_FILE = "errors_db.json"


def _bundled_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, DB_FILE)


def _user_path():
    return os.path.join(os.path.expanduser("~"), "Documents", "iOSPanicReader", DB_FILE)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_db():
    db = _read(_bundled_path())
    if db is None:
        raise RuntimeError(f"Не найдена база ошибок {DB_FILE}")
    user = _read(_user_path())
    if user and user.get("meta", {}).get("version", 0) >= db["meta"].get("version", 0) and user.get("entries"):
        db = user
    return db


TEXT_FIELDS = ("title", "node", "symptoms", "cause", "fix", "models", "ios", "keywords",
               "name", "where", "parts")


def localize(db, lang):
    """Подставляет переводы из поля i18n записей. Русский текст сохраняется в _ru — по нему
    тоже ищем, чтобы находилось и по-русски, и на языке интерфейса."""
    items = list(db["entries"]) + list(db["sensors"].values()) + list(db.get("i2c_buses", []))
    for item in items:
        tr = (item.get("i18n") or {}).get(lang) or {}
        item["_ru"] = " ".join(str(item.get(k, "")) for k in TEXT_FIELDS)
        for k, v in tr.items():
            if k in TEXT_FIELDS and v:
                item[k] = v
    return db


DB = localize(load_db(), i18n.LANG)
META = DB["meta"]
SOURCES = META.get("sources", {})
CATEGORIES = DB["categories"]
PRODUCTS = DB["products"]
BUG_TYPES = DB["bug_types"]
FILE_KINDS = [tuple(x) for x in DB["file_kinds"]]
SENSORS = DB["sensors"]
I2C_BUSES = DB.get("i2c_buses", [])
KB = DB["entries"]
CONFIDENCE = META.get("confidence_levels", {})


def source_url(key):
    return SOURCES.get(key, key)


def sensor_info(name):
    _ = i18n._
    key = name.lower().rstrip(",")
    if key in SENSORS:
        return SENSORS[key]
    for prefix, d in (("mic", dict(SENSORS["mic1"], name=_("Микрофон"),
                                   where=_("Один из шлейфов с микрофоном (зависит от модели)."))),
                      ("tg", SENSORS["tg0b"]), ("prs", SENSORS["prs0"])):
        if key.startswith(prefix):
            return d
    if key.startswith(("tp", "ts", "tc", "tf", "pmu")):
        return {"name": _("Термодатчик"), "where": _("Плата / контроллер питания."), "models": "",
                "fix": _("Диагностика платы.")}
    return {"name": _("Неизвестный датчик"), "where": _("Определяется по модели."), "models": "",
            "fix": _("Поищите название датчика для своей модели.")}


def i2c_parts(bus, product):
    """Что висит на шине bus (например «i2c3») у модели product, если это известно."""
    bus = bus.lower()
    return [b for b in I2C_BUSES if b["bus"] == bus and product in b["models"]]


def kb_by_id():
    return {e["id"]: e for e in KB}
