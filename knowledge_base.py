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


DB = load_db()
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
    key = name.lower().rstrip(",")
    if key in SENSORS:
        return SENSORS[key]
    for prefix, d in (("mic", dict(SENSORS["mic1"], name="Микрофон",
                                   where="Один из шлейфов с микрофоном (зависит от модели).")),
                      ("tg", SENSORS["tg0b"]), ("prs", SENSORS["prs0"])):
        if key.startswith(prefix):
            return d
    if key.startswith(("tp", "ts", "tc", "tf", "pmu")):
        return {"name": "Термодатчик", "where": "Плата / контроллер питания.", "models": "",
                "fix": "Диагностика платы."}
    return {"name": "Неизвестный датчик", "where": "Определяется по модели.", "models": "",
            "fix": "Поищите название датчика для своей модели."}


def i2c_parts(bus, product):
    """Что висит на шине bus (например «i2c3») у модели product, если это известно."""
    bus = bus.lower()
    return [b for b in I2C_BUSES if b["bus"] == bus and product in b["models"]]


def kb_by_id():
    return {e["id"]: e for e in KB}
