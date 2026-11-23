# -*- coding: utf-8 -*-
"""Что показывать о логе, записи базы, датчике, шине и модели — общее для старого окна (tkinter)
и нового (веб-интерфейс). Текст — список кусков (текст, вид): small, h1, cap, body, mono, red."""

import os

import core
from i18n import _
from knowledge_base import KB, PRODUCTS, SENSORS


def log_level(l):
    if l["is_panic"]:
        return "red"
    if l["exception"]:
        return "orange"
    return "gray"


def log_title(l):
    if l["is_panic"]:
        part = core.panic_part(l)
        return _("Паника: ") + (core.PART_NAMES[part] if part else core.main_cause(l))
    if l["exception"]:
        return _("{0} закрылось", l['process'] or 'Приложение')
    if "Jetsam" in l["kind"]:
        return _("Не хватило памяти")
    return core.tkind(l["kind"])


def log_parts(l):
    parts = [(f"{str(l['date'])[:19]} · {core.tkind(l['kind'])}\n", "small"), (log_title(l) + "\n", "h1")]
    if l["missing_sensors"]:
        parts.append((_("ТЕЛЕФОН НЕ ВИДИТ ДАТЧИКИ\n"), "cap"))
        for s in l["missing_sensors"]:
            d = core.sensor_info(s)
            parts.append((f"• {s} — {d['name']}. {core.sensor_where(d['where'], l.get('product') or '')}\n", "body"))
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


def entry_parts(e, logs=()):
    parts = [(_(e["cat"]) + "\n", "small"), (e["title"] + "\n", "h1"),
             (_("УЗЕЛ\n"), "cap"), (e["node"] + "\n", "body")]
    if e.get("models"):
        parts += [(_("МОДЕЛИ\n"), "cap"), (e["models"] + "\n", "body")]
    if e.get("ios"):
        parts += [(_("ВЕРСИИ iOS\n"), "cap"), (e["ios"] + "\n", "body")]
    parts += [(_("КАК ВЕДЁТ СЕБЯ ТЕЛЕФОН\n"), "cap"), (e["symptoms"] + "\n", "body"),
              (_("ПОЧЕМУ\n"), "cap"), (e["cause"] + "\n", "body"),
              (_("ЧТО ДЕЛАТЬ\n"), "cap"), (e["fix"] + "\n", "body")]
    n = sum(1 for l in logs for fe, _hit in l["findings"] if fe is e)
    if n:
        parts.append((_("\nВстречается в открытых логах: {0} раз(а)\n", n), "red"))
    if e.get("patterns"):
        parts += [(_("КАК ВЫГЛЯДИТ В ЛОГЕ\n"), "cap"), ("  ".join(e["patterns"]) + "\n", "mono")]
    if e.get("confidence"):
        parts += [(_("НАДЁЖНОСТЬ\n"), "cap"), (core.CONFIDENCE.get(e["confidence"], e["confidence"]) + "\n", "small")]
    if e.get("sources"):
        parts += [(_("ИСТОЧНИКИ\n"), "cap")] + [(core.source_url(s) + "\n", "small") for s in e["sources"]]
    return parts


def sensor_parts(key):
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
    return parts


def i2c_parts(key):
    b = core.I2C_BUSES[key]
    names = ", ".join(f"{PRODUCTS.get(m, m)} ({m})" for m in b["models"])
    return [(_("Шины I2C\n"), "small"), (_("Шина {0}\n", b['bus']), "h1"), (_("МОДЕЛИ\n"), "cap"), (names + "\n", "body"),
            (_("ЧТО НА ЭТОЙ ШИНЕ\n"), "cap"), (b["parts"] + "\n", "body"),
            (_("КАК ПОЛЬЗОВАТЬСЯ\n"), "cap"),
            (_("Если в панике есть эта шина (например, «i2c3::_checkBusStatus SCL is stuck low»), отключайте по одной детали из списка и смотрите, пропадёт ли паника. У других моделей назначение шин другое.\n"), "body"),
            (_("ИСТОЧНИК\n"), "cap"), (core.source_url(b["source"]) + "\n", "small")]


def model_parts(product):
    pr = core.model_profile(product)
    parts = [(_("Профиль модели") + "\n", "small"), (f"{pr['name']} ({product})\n", "h1"),
             (_("ОСОБЕННОСТИ\n"), "cap")]
    parts += [(f"• {k}: {v}\n", "body") for k, v in pr["facts"]]
    if pr["sensors"]:
        parts.append((_("ДАТЧИКИ ИЗ «MISSING SENSOR» И ГДЕ ОНИ СТОЯТ\n"), "cap"))
        parts += [(f"• {k} — {d['name']}: {d['where']}\n", "body") for k, d in pr["sensors"]]
    if pr["buses"]:
        parts.append((_("ШИНЫ I2C\n"), "cap"))
        parts += [(f"• {b['bus']}: {b['parts']}\n", "body") for b in pr["buses"]]
    if pr["entries"]:
        parts.append((_("ОШИБКИ, ХАРАКТЕРНЫЕ ДЛЯ ЭТОЙ МОДЕЛИ\n"), "cap"))
        parts += [(f"• {e['title']}\n", "body") for e in pr["entries"]]
    parts += [(_("\nВ списке слева — записи базы, которые относятся к этой модели, и общие для всех.\n"), "small"),
              (_("Для iPhone 15–17 данных о датчиках и шинах пока мало. Если у вас есть паники с них — "
                 "предложите их для базы кнопкой у лога.\n"), "small")]
    return parts


def kb_rows(q, cat="Все", product=None):
    """Строки базы для поиска: (тип, ключ, заголовок, раздел)."""
    if q:
        rows = core.search_db(q)
    else:
        rows = [("entry", i, e["title"], e["cat"]) for i, e in enumerate(KB)]
        rows += [("sensor", k, _("Датчик {0} — {1}", k, d['name']), "Датчики (Missing sensor)") for k, d in SENSORS.items()]
        rows += [("i2c", i, _("Шина {0} — ", b['bus']) + ", ".join(dict.fromkeys(PRODUCTS.get(m, m) for m in b["models"])),
                  _("Шины I2C")) for i, b in enumerate(core.I2C_BUSES)]
    rows = [r for r in rows if cat == "Все" or r[3] == cat]
    if product:
        def fits(r):
            typ, key = r[0], r[1]
            if typ == "entry":
                return core.applies(KB[key], product) is not False
            if typ == "sensor":
                return core.applies(SENSORS[key], product) is not False
            if typ == "i2c":
                return product in core.I2C_BUSES[key]["models"]
            return True
        rows = [r for r in rows if fits(r)]
    return rows


def phone_folder(serial):
    root = core.logs_root()
    return next((os.path.join(root, n) for n in os.listdir(root) if n.endswith("_" + serial)), None)
