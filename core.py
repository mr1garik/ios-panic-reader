# -*- coding: utf-8 -*-
"""Разбор логов iOS и общий вывод: что с телефоном и какая деталь виновата."""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

from i18n import _

from knowledge_base import (BUG_TYPES, CONFIDENCE, FILE_KINDS, I2C_BUSES, KB, PRODUCTS, SENSORS,
                            i2c_parts, sensor_info, source_url)

APP_TITLE = "iOS Panic Reader"
LOG_EXTENSIONS = (".ips", ".panic", ".log", ".txt", ".synced", ".beta", ".crash", ".diag")


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def logs_root():
    d = os.path.join(os.path.expanduser("~"), "Documents", "iOSPanicReader", "Logs")
    os.makedirs(d, exist_ok=True)
    return d


def load_user_kb():
    """Свои записи из user_kb.json: в папке данных (Документы/iOSPanicReader — переживает
    обновления) или, по-старому, рядом с программой."""
    path = next((p for p in (os.path.join(os.path.dirname(logs_root()), "user_kb.json"),
                             os.path.join(app_dir(), "user_kb.json")) if os.path.isfile(p)), None)
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as f:
            extra = json.load(f)
        for e in extra:
            e.setdefault("patterns", [])
            e.setdefault("cat", "Паника ядра")
            for k in ("node", "symptoms", "cause", "fix"):
                e.setdefault(k, "")
            KB.insert(0, e)
    except Exception as ex:
        print("user_kb.json:", ex)


# ---------------------------------------------------------------------------
# Разбор файла
# ---------------------------------------------------------------------------
def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"bplist"):
        return ""
    for enc in ("utf-8", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _try_json(s):
    try:
        return json.loads(s)
    except Exception:
        return None


def file_kind(path):
    name = os.path.basename(path)
    for pat, kind in FILE_KINDS:
        if re.search(pat, name, re.I):
            return kind
    return "Лог"


def parse_log(path):
    return parse_text(_read_text(path), path)


def parse_pasted(text, product=""):
    """Разбор текста паники, вставленного вручную (например, скопированного с телефона)."""
    text = text.strip()
    if text and not text.startswith("{") and "panic(" in text:
        # голый panicString без JSON — оборачиваем, чтобы разбор пошёл обычным путём
        text = json.dumps({"bug_type": "210"}) + "\n" + json.dumps({"panicString": text, "product": product})
    info = parse_text(text, _("вставленный текст"))
    if product and not info["product"]:
        info["product"] = product
        info["model"] = PRODUCTS.get(product, product)
    if text and not info["panic"] and not info["exception"]:
        # просто кусок текста: ищем в нём всё, что знает база
        info["panic"] = text
        info["is_panic"] = True
        info["findings"] = []
        analyze(info)
    return info


def parse_text(text, path):
    info = {
        "file": path, "raw": text, "header": {}, "body": {}, "product": "", "model": "",
        "os": "", "date": "", "bug_type": "", "panic": "", "process": "", "exception": "",
        "kind": file_kind(path), "missing_sensors": [], "findings": [], "is_panic": False,
    }

    stripped = text.lstrip("﻿").strip()
    first, _sep, rest = stripped.partition("\n")
    header = _try_json(first)
    body = None
    if isinstance(header, dict):
        body = _try_json(rest.strip()) if rest.strip() else None
    else:
        whole = _try_json(stripped)
        header = body = whole if isinstance(whole, dict) else None

    h = info["header"] = header if isinstance(header, dict) else {}
    b = info["body"] = body if isinstance(body, dict) else {}

    info["bug_type"] = str(h.get("bug_type") or b.get("bug_type") or "")
    info["product"] = b.get("product") or b.get("modelCode") or h.get("product") or ""
    os_ver = b.get("osVersion") if isinstance(b.get("osVersion"), dict) else {}
    info["os"] = h.get("os_version") or b.get("build") or \
        (" ".join(x for x in (os_ver.get("train"), os_ver.get("build")) if x))
    info["date"] = h.get("timestamp") or b.get("date") or b.get("captureTime") or ""
    info["panic"] = b.get("panicString") or ""
    info["process"] = b.get("procName") or h.get("app_name") or h.get("name") or ""

    exc = b.get("exception")
    if isinstance(exc, dict):
        parts = [exc.get("type"), exc.get("signal"), exc.get("codes"), exc.get("subtype")]
        info["exception"] = " ".join(str(p) for p in parts if p)
    term = b.get("termination")
    if isinstance(term, dict):
        info["exception"] += " termination: " + " ".join(
            str(term.get(k)) for k in ("namespace", "code", "indicator", "reasons") if term.get(k))

    # Старые форматы / паника внутри текста
    if not info["panic"]:
        m = re.search(r'"panicString"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        if m:
            info["panic"] = _try_json('"' + m.group(1) + '"') or m.group(1)
        elif re.search(r"panic\(cpu", text):
            info["panic"] = text[text.find("panic(cpu"):]
    if not info["exception"]:
        m = re.search(r"Exception Type:\s*(.+)", text)
        if m:
            info["exception"] = m.group(1).strip()
            m2 = re.search(r"Exception Codes?:\s*(.+)", text)
            if m2:
                info["exception"] += " " + m2.group(1).strip()
    if not info["process"]:
        m = re.search(r"^Process:\s*(\S+)", text, re.M)
        if m:
            info["process"] = m.group(1)
    if not info["product"]:
        m = re.search(r"(iPhone\d+,\d+|iPad\d+,\d+|iPod\d+,\d+)", text)
        if m:
            info["product"] = m.group(1)
    if not info["os"]:
        m = re.search(r"(iPhone OS|iOS|iPadOS)\s+([\d.]+)\s*\((\w+)\)", text)
        if m:
            info["os"] = m.group(0)
    if not info["date"]:
        m = re.search(r'(?:"date"|Date/Time:)\s*:?\s*"?(\d{4}-\d{2}-\d{2}[ T][\d:.]+[^",\n]*)', text)
        if m:
            info["date"] = m.group(1).strip()
    if not info["bug_type"]:
        m = re.search(r'"bug_type"\s*:\s*"?(\d+)', text)
        if m:
            info["bug_type"] = m.group(1)

    info["model"] = PRODUCTS.get(info["product"], info["product"])
    info["from_watch"] = info["product"].startswith("Watch") or "ProxiedDevice" in path or \
        bool(re.search(r"\bNano[A-Z]\w*|WatchApp\b|WatchKit", info["process"] or ""))
    if info["kind"] in ("Лог", "Отчёт о сбое") and info["bug_type"] in BUG_TYPES:
        info["kind"] = BUG_TYPES[info["bug_type"]]
    if info["from_watch"]:
        info["kind"] += " · Apple Watch"
    info["is_panic"] = bool(info["panic"]) or info["bug_type"] in ("210", "409") or \
        "panic" in os.path.basename(path).lower()
    analyze(info)
    return info


APP_CATS = ("Вылет приложения",)


def tkind(kind):
    """Вид лога на языке интерфейса (внутри программы он хранится по-русски)."""
    return " · ".join(_(p) for p in kind.split(" · "))


def phone_panics(logs):
    """Паники самого iPhone: логи с часов Apple Watch, которые телефон хранит у себя, не считаются."""
    return [l for l in logs if l["is_panic"] and not l.get("from_watch")]


def analyze(info):
    if info["panic"]:
        hay = info["panic"]
        entries = KB
        m = re.search(r"Missing sensor\(s\):\s*([^\n\\\"]+)", hay)
        if m:
            info["missing_sensors"] = [s for s in re.split(r"[\s,]+", m.group(1).strip()) if s]
    else:
        # Не паника: признаки поломок железа здесь не ищем — в аналитике и отчётах о сбоях
        # слова вроде «baseband» или «WLAN» встречаются всегда и дают ложные тревоги.
        hay = " ".join([info["exception"], os.path.basename(info["file"]), info["raw"][:4000]])
        entries = [e for e in KB if e["cat"] in APP_CATS]

    for e in entries:
        if e["id"] in ("wd_generic", "wdt_generic") and info["findings"]:
            continue  # общий шаблон — только если ничего конкретнее нет
        for pat in e.get("patterns", []):
            mm = re.search(pat, hay)
            if mm:
                info["findings"].append((e, mm.group(0)))
                break


def main_cause(info):
    if info["missing_sensors"]:
        names = [sensor_info(s)["name"] for s in info["missing_sensors"]]
        return _("Нет датчика: ") + ", ".join(info["missing_sensors"]) + " (" + "; ".join(dict.fromkeys(names)) + ")"
    for e, _hit in info["findings"]:
        if e["id"] not in ("wd_generic", "missing_sensor"):
            return e["node"]
    if info["findings"]:
        return info["findings"][0][0]["node"]
    return "—"


def device_label(info):
    if info["product"] and info["model"] != info["product"]:
        return f'{info["model"]} ({info["product"]})'
    return info["product"] or "—"


def build_report(info):
    out = []
    out.append("=" * 72)
    out.append(_("Файл:        ") + os.path.basename(info["file"]))
    out.append(_("Вид лога:    ") + tkind(info["kind"]))
    out.append(_("Устройство:  ") + device_label(info))
    out.append("iOS:         " + (info["os"] or "—"))
    out.append(_("Дата:        ") + (str(info["date"]) or "—"))
    bt = info["bug_type"]
    out.append("bug_type:    " + (f"{bt} — {_(BUG_TYPES.get(bt, 'неизвестно'))}" if bt else "—"))
    if info["process"]:
        out.append(_("Процесс:     ") + info["process"])
    if info["exception"]:
        out.append(_("Исключение:  ") + info["exception"])
    out.append("")

    if info["missing_sensors"]:
        out.append(_("ОТСУТСТВУЮЩИЕ ДАТЧИКИ:"))
        for s in info["missing_sensors"]:
            d = sensor_info(s)
            out.append(f"  • {s} — {d['name']}")
            out.append(_("      Где стоит:   {0}", d['where']))
            if d.get("models"):
                out.append(_("      По моделям:  {0}", d['models']))
            out.append(_("      Что делать:  {0}", d['fix']))
        out.append("")

    out.append(_("РАСШИФРОВКА:"))
    if info["findings"]:
        for i, (e, hit) in enumerate(info["findings"], 1):
            out.append(_("  {0}. {1}   [найдено: «{2}»]", i, e['title'], hit))
            out.append(_("     Узел:         {0}", e['node']))
            out.append(_("     Как ведёт себя: {0}", e['symptoms']))
            out.append(_("     Почему:       {0}", e['cause']))
            out.append(_("     Что делать:   {0}", e['fix']))
            out.append("")
    else:
        out.append(_("  Известных шаблонов не найдено. Посмотри текст ниже или исходный лог."))
        out.append("")

    for bus, rows in i2c_hints(info):
        out.append(_("ШИНА {0} У ЭТОЙ МОДЕЛИ:", bus.upper()))
        for r in rows:
            out.append(_("  • {0}  (источник: {1})", r['parts'], source_url(r['source'])))
        out.append("")

    if info["panic"]:
        out.append(_("ТЕКСТ ПАНИКИ (panicString):"))
        out.append(info["panic"].strip()[:6000])
    out.append("")
    return "\n".join(out)


def _parse_date(s):
    s = str(s)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.strip()[:32], fmt)
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", s)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return None


def build_summary(logs, device_info=None):
    """Общий вывод по всем логам — что с телефоном."""
    out = [_("СВОДКА ПО ТЕЛЕФОНУ"), "=" * 72]
    if device_info:
        for k, v in device_info.items():
            out.append(f"{k + ':':16}{v}")
        out.append("")
    if not logs:
        out.append(_("Логов нет."))
        return "\n".join(out)

    panics = phone_panics(logs)
    kinds = Counter(l["kind"] for l in logs)
    out.append(_("Всего логов: {0}, из них паник ядра: {1}", len(logs), len(panics)))
    kinds = Counter(tkind(k) for k in kinds.elements())
    for k, n in kinds.most_common():
        out.append(f"  {k}: {n}")
    out.append("")

    if panics:
        causes = Counter(main_cause(p) for p in panics)
        out.append(_("ЧАСТЫЕ ПРИЧИНЫ ПАНИК:"))
        for c, n in causes.most_common(8):
            out.append(f"  {n:4} × {c}")
        out.append("")

        sensors = Counter(s for p in panics for s in p["missing_sensors"])
        if sensors:
            out.append(_("ОТСУТСТВУЮЩИЕ ДАТЧИКИ (по всем паникам):"))
            for s, n in sensors.most_common():
                d = sensor_info(s)
                out.append(f"  {n:4} × {s} — {d['name']}: {d['where']}")
            out.append("")

        dates = sorted(d for d in (_parse_date(p["date"]) for p in panics) if d)
        if dates:
            out.append(_("Первая паника: {0}   последняя: {1}", f"{dates[0]:%Y-%m-%d %H:%M}", f"{dates[-1]:%Y-%m-%d %H:%M}"))
            if len(dates) >= 3:
                gaps = []
                for a, b in zip(dates, dates[1:]):
                    try:
                        gaps.append((b - a).total_seconds())
                    except TypeError:
                        pass
                short = [g for g in gaps if 0 < g < 600]
                if len(short) >= 2:
                    out.append(_("Паники идут сериями с интервалом ~{0} с → телефон перезагружается по кругу.", int(sorted(short)[len(short)//2])))
            out.append("")

        osv = Counter(p["os"] for p in panics if p["os"])
        if len(osv) > 1:
            out.append(_("Паники на разных версиях iOS: ") + ", ".join(osv) +
                       _(" → если причина одна и та же, это железо, а не прошивка."))
            out.append("")

        top, n = causes.most_common(1)[0]
        out.append(_("ВЫВОД:"))
        if n >= 3 and n / len(panics) >= 0.6:
            out.append(_("  Повторяющаяся причина ({0} из {1}): {2}.", n, len(panics), top))
            out.append(_("  Одинаковые паники подряд почти всегда означают аппаратную неисправность этого узла."))
        elif len(causes) > 3:
            out.append(_("  Причины паник разные — подозрение на ПО, питание (аккумулятор), память или процессор."))
        else:
            out.append(_("  Основная причина: {0}. Открой паники в списке для подробностей.", top))
    else:
        out.append(_("Паник ядра нет — аппаратных сбоев по логам не видно."))
    crashes = [l for l in logs if not l["is_panic"] and l["exception"]]
    if crashes:
        apps = Counter(l["process"] or "?" for l in crashes)
        out.append("")
        out.append(_("ВЫЛЕТЫ ПРИЛОЖЕНИЙ:"))
        for a, n in apps.most_common(10):
            out.append(f"  {n:4} × {a}")
    return "\n".join(out)


def collect_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for fn in files:
                    if fn.lower().endswith(LOG_EXTENSIONS) or "panic" in fn.lower():
                        out.append(os.path.join(root, fn))
        elif os.path.isfile(p):
            out.append(p)
    return out




# ---------------------------------------------------------------------------
# Детали телефона и общий вывод для главного экрана
# ---------------------------------------------------------------------------
PARTS = [
    ("battery", _("Аккумулятор")),
    ("charge_flex", _("Шлейф зарядки (нижний микрофон, барометр)")),
    ("top_flex", _("Верхний шлейф (датчики, микрофон)")),
    ("display", _("Дисплей и тач")),
    ("camera", _("Камеры")),
    ("biometry", "Face ID / Touch ID"),
    ("baseband", _("Модем (сеть, IMEI)")),
    ("wifi", "Wi-Fi / Bluetooth / NFC"),
    ("audio", _("Звук (кодек, динамики)")),
    ("usb", _("Контроллер зарядки / USB")),
    ("board", _("Плата (питание, память, процессор)")),
    ("software", _("Программное обеспечение")),
]
PART_NAMES = dict(PARTS)

KB_PART = {
    "battery": "battery", "brownout": "battery",
    "charger": "usb", "tristar": "usb",
    "touch": "display", "display": "display", "wd_springboard": "software",
    "camera": "camera",
    "sep": "biometry", "faceid": "biometry", "touchid": "biometry",
    "baseband": "baseband", "wd_commcenter": "baseband", "pcie": "wifi",
    "wlan": "wifi", "wd_wifid": "wifi", "nfc": "wifi", "uwb": "wifi",
    "audio": "audio", "wd_mediaserverd": "audio", "taptic": "audio",
    "aop": "top_flex", "sensors_motion": "top_flex", "wd_locationd": "top_flex",
    "nand": "board", "smc": "board", "pmu": "board", "soc_wdt": "board", "i2c": "board",
    "thermal": "board", "dart": "board", "gpu": "board",
    "initproc": "software", "zone": "software", "data_abort": "software",
    "fetch_abort": "software", "jailbreak": "software",
}


def sensor_part(name):
    k = name.lower()
    if k in ("mic1", "prs0") or k.startswith("prs"):
        return "charge_flex"
    if k.startswith("tg"):
        return "battery"
    if k in ("mic2", "mic4"):
        return "top_flex"
    if k == "mic3":
        return "camera"
    return "board"


def panic_part(info):
    """Какая деталь виновата в этой панике (или None)."""
    if info["missing_sensors"]:
        return sensor_part(info["missing_sensors"][0])
    for e, _hit in info["findings"]:
        if e["id"] in KB_PART:
            return KB_PART[e["id"]]
    return None


def _main_entry(info):
    for e, _hit in info["findings"]:
        if e["id"] in KB_PART or e["id"] == "thermalmonitord":
            return e
    return info["findings"][0][0] if info["findings"] else None


def build_verdict(logs, dev=None):
    """Список проблем для главного экрана, от самой важной.
    Проблема: dict(level='red'|'orange', title, how, why, fix=[...], note, part)."""
    problems = []
    panics = phone_panics(logs)

    by_part = {}
    for p in panics:
        by_part.setdefault(panic_part(p), []).append(p)

    for part, items in by_part.items():
        if part is None:
            continue
        n = len(items)
        level = "red" if n >= 3 or (n >= 2 and n / len(panics) >= 0.5) else "orange"
        sensors = Counter(s for p in items for s in p["missing_sensors"])
        e = _main_entry(items[0])
        if sensors:
            names = ", ".join(f"{sensor_info(s)['name'].lower()} ({s})" for s in sensors)
            where = sensor_info(sensors.most_common(1)[0][0])
            why = _("Телефон не видит: {0}. Где стоит: {1}", names, where['where'])
            fix = [x.strip() for x in where["fix"].split(". ") if x.strip()]
            how = KB[[k["id"] for k in KB].index("thermalmonitord")]["symptoms"]
        else:
            why = e["cause"] if e else "—"
            fix = [x.strip() for x in (e["fix"] if e else "").split(". ") if x.strip()]
            how = e["symptoms"] if e else "—"
        problems.append(dict(
            level=level, part=part, title=PART_NAMES[part], how=how, why=why, fix=fix,
            note=_("{0} из {1} {2} указывают на эту деталь", n, len(panics), _plural_panic(len(panics))), count=n))

    unknown = by_part.get(None, [])
    if len(unknown) >= 3:
        problems.append(dict(
            level="orange", part="software", title=_("Случайные перезагрузки"),
            how=_("Телефон иногда перезагружается сам."),
            why=_("Паники разные и не указывают на одну деталь — чаще ПО, реже питание или память."),
            fix=[_("Обновить или восстановить iOS"), _("Если не помогло — проверить аккумулятор и плату")],
            note=_("{0} паник без явной причины", len(unknown)), count=len(unknown)))

    if dev:
        h = dev.get("battery_health")
        if h is not None and h < 80 and not any(p["part"] == "battery" for p in problems):
            problems.append(dict(
                level="red", part="battery", title=_("Аккумулятор изношен"),
                how=_("Быстро садится, может выключаться на 20–30% заряда или на холоде."),
                why=_("Ёмкость {0}% от заводской", h) +
                    (_(", {0} циклов", dev['battery_cycles']) if dev.get("battery_cycles") else "") +
                    _(". Apple считает нормой не ниже 80%."),
                fix=[_("Заменить аккумулятор")], note=_("по данным контроллера аккумулятора"), count=0))
        if dev.get("is_iphone") and not dev.get("imei") and \
                not any(p["part"] == "baseband" for p in problems):
            problems.append(dict(
                level="orange", part="baseband", title=_("IMEI не прочитан"),
                how=_("Если в Настройках → Основные → Об этом устройстве IMEI тоже пустой — нет сети."),
                why=_("Модем не отдал IMEI. Бывает при неисправном модеме или его питании."),
                fix=[_("Проверить IMEI в настройках телефона"), _("Если пустой — диагностика модема")],
                note=_("по данным телефона"), count=0))

    problems.sort(key=lambda p: (p["level"] != "red", -p["count"]))
    return problems


def parts_table(logs, dev=None):
    """Строки для экрана «Детали»: (деталь, данные с телефона, сбои в логах, уровень)."""
    panics = phone_panics(logs)
    fails = {}
    for p in panics:
        part = panic_part(p)
        if part:
            fails.setdefault(part, Counter())[main_cause(p)] += 1
    dev = dev or {}
    data = {
        "battery": ", ".join(x for x in (
            _("ёмкость {0}%", dev['battery_health']) if dev.get("battery_health") is not None else "",
            _("{0} циклов", dev['battery_cycles']) if dev.get("battery_cycles") is not None else "",
            _("серийный {0}", dev['battery_serial']) if dev.get("battery_serial") else "") if x),
        "baseband": ", ".join(x for x in (
            f"IMEI {dev['imei']}" if dev.get("imei") else (_("IMEI не прочитан") if dev else ""),
            _("прошивка модема {0}", dev['baseband']) if dev.get("baseband") else "") if x),
        "wifi": ", ".join(x for x in (
            f"Wi-Fi {dev['wifi_mac']}" if dev.get("wifi_mac") else "",
            f"BT {dev['bt_mac']}" if dev.get("bt_mac") else "") if x),
        "board": _("плата {0}", dev['hw_model']) if dev.get("hw_model") else "",
        "software": f"iOS {dev['ios']} ({dev.get('build', '')})" if dev.get("ios") else "",
    }
    rows = []
    for pid, name in PARTS:
        c = fails.get(pid)
        n = sum(c.values()) if c else 0
        fail_text = f"{n} {_plural_panic(n)}: " + "; ".join(k for k, _hit in c.most_common(2)) if n else _("нет")
        level = "red" if n >= 3 else ("orange" if n else "green")
        if pid == "battery" and dev.get("battery_health") is not None and dev["battery_health"] < 80:
            level = "red"
        if pid == "baseband" and dev and dev.get("is_iphone") and not dev.get("imei") and level == "green":
            level = "orange"
        rows.append((name, data.get(pid, "") or "—", fail_text, level))
    return rows


def _plural_panic(n):
    if n % 10 == 1 and n % 100 != 11:
        return _("паника")
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return _("паники")
    return _("паник")


# ---------------------------------------------------------------------------
# Время логов: до/после ремонта, паники по дням
# ---------------------------------------------------------------------------
def log_local_dt(info):
    """Дата лога в местном времени компьютера (без часового пояса) или None."""
    d = _parse_date(info.get("date", ""))
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def logs_since(logs, since):
    """Логи, записанные после момента since (логи без даты отбрасываются)."""
    out = []
    for l in logs:
        d = log_local_dt(l)
        if d is not None and d >= since:
            out.append(l)
    return out


def panics_by_day(logs, days=30, end=None):
    """[(дата, число паник)] за последние days дней, заканчивая днём end."""
    from datetime import timedelta
    end = (end or datetime.now()).date()
    counts = Counter()
    for l in logs:
        if l["is_panic"]:
            d = log_local_dt(l)
            if d is not None:
                counts[d.date()] += 1
    return [(end - timedelta(days=i), counts.get(end - timedelta(days=i), 0))
            for i in range(days - 1, -1, -1)]


# ---------------------------------------------------------------------------
# Шины I2C и поиск по базе
# ---------------------------------------------------------------------------
def i2c_hints(info):
    """[(шина, [строки таблицы])] для шин, упомянутых в панике, если модель есть в таблице."""
    if not info.get("panic") or not info.get("product"):
        return []
    out = []
    for bus in dict.fromkeys(m.lower() for m in re.findall(r"\b(i2c\d+)", info["panic"], re.I)):
        rows = i2c_parts(bus, info["product"])
        if rows:
            out.append((bus, rows))
    return out


def _words(q):
    return [w for w in re.split(r"\s+", q.lower().strip()) if w]


def _entry_text(e):
    return " ".join(str(e.get(k, "")) for k in ("id", "title", "node", "symptoms", "cause", "fix", "models",
                                                 "ios", "keywords", "_ru")) + " " + " ".join(e.get("patterns", []))


def search_db(query):
    """Поиск по базе: все слова запроса должны встретиться. Возвращает [(тип, ключ, заголовок, раздел)]:
    тип — entry (ключ — индекс в KB), sensor (ключ — имя датчика), i2c (ключ — индекс в I2C_BUSES).
    Если запрос похож на текст паники — сначала то, что база находит в нём по шаблонам."""
    words = _words(query)
    if not words:
        return []
    res, seen = [], set()
    if len(query) > 40 or "panic" in query.lower():
        for e, _hit in parse_pasted(query)["findings"]:
            i = KB.index(e)
            res.append(("entry", i, e["title"], e["cat"]))
            seen.add(i)
    scored = []
    for i, e in enumerate(KB):
        if i in seen:
            continue
        hay = _entry_text(e).lower()
        if all(w in hay for w in words):
            scored.append((0 if all(w in e["title"].lower() for w in words) else 1, i, e))
    for _rank, i, e in sorted(scored, key=lambda x: x[:2]):
        res.append(("entry", i, e["title"], e["cat"]))
    for k, d in SENSORS.items():
        hay = (k + " " + " ".join(str(v) for v in d.values() if isinstance(v, str))).lower()
        if all(w in hay for w in words):
            res.append(("sensor", k, _("Датчик {0} — {1}", k, d['name']), "Датчики (Missing sensor)"))
    for i, b in enumerate(I2C_BUSES):
        models = " ".join(PRODUCTS.get(m, m) + " " + m for m in b["models"])
        hay = _("{0} i2c шина {1} {2}", b['bus'], b['parts'], models).lower()
        if all(w in hay for w in words):
            names = ", ".join(dict.fromkeys(PRODUCTS.get(m, m) for m in b["models"]))
            res.append(("i2c", i, _("Шина {0} — {1}", b['bus'], names), _("Шины I2C")))
    return res


def search_logs(logs, query):
    """Логи, в тексте которых есть все слова запроса (по паникам, процессам, исключениям)."""
    words = _words(query)
    if not words:
        return []
    out = []
    for l in logs:
        hay = " ".join([l["panic"], l["process"], l["exception"], l["kind"], tkind(l["kind"]), l["model"], l["os"],
                        os.path.basename(l["file"]), " ".join(e["title"] for e, _hit in l["findings"]),
                        " ".join(l["missing_sensors"])]).lower()
        if all(w in hay for w in words):
            out.append(l)
    return out


# ---------------------------------------------------------------------------
# Модели: поколение, что относится к модели, профиль модели
# ---------------------------------------------------------------------------
# Поколение как число, чтобы сравнивать: X = 10, XS/XR = 10.5, SE 2/3 — как iPhone 8 (тот же корпус)
_FAMILY_SPECIAL = {"iPhone8,4": 6.5, "iPhone10,3": 10, "iPhone10,6": 10, "iPhone12,8": 8, "iPhone14,6": 8,
                   "iPhone17,5": 16}


def model_family(product):
    if product in _FAMILY_SPECIAL:
        return _FAMILY_SPECIAL[product]
    name = PRODUCTS.get(product, "")
    m = re.match(r"iPhone (\d+)(s)?", name)
    if m:
        return int(m.group(1)) + (0.5 if m.group(2) else 0)
    if name.startswith("iPhone X"):
        return 10.5
    if name.startswith("iPhone Air"):
        return 17
    return None


def applies(item, product):
    """True — запись относится к модели, False — нет, None — общая для всех моделей."""
    rng = item.get("fam")
    if not rng:
        return None
    if product in item.get("except", []):
        return False
    f = model_family(product)
    return None if f is None else rng[0] <= f <= rng[1]


def model_choices():
    """[(название, код)] — по одной модели на название, от новых к старым."""
    seen = {}
    for code, name in PRODUCTS.items():
        if code.startswith("iPhone") and name not in seen:
            seen[name] = code
    return sorted(seen.items(), key=lambda kv: (-(model_family(kv[1]) or 0), kv[0]))


def model_profile(product):
    """Что известно о модели: особенности, датчики, шины I2C, записи базы именно для неё."""
    f = model_family(product) or 0
    name = PRODUCTS.get(product, product)
    facts = [
        (_("Разъём"), "USB-C" if f >= 15 else "Lightning"),
        (_("Биометрия"), "Face ID" if f >= 10 else "Touch ID"),
    ]
    if product == "iPhone18,4":
        sim = _("только eSIM, SIM-лотка нет")
    elif f >= 17:
        sim = _("в ряде стран только eSIM — проверьте, есть ли SIM-лоток")
    elif f >= 14:
        sim = _("у моделей для США только eSIM, у остальных есть SIM-лоток")
    else:
        sim = _("SIM-лоток (и eSIM с iPhone XS)") if f >= 10.5 else _("SIM-лоток")
    facts.append((_("SIM"), sim))
    ser = [x for x, lo in ((_("аккумулятор"), 10.5), (_("дисплей"), 11), (_("камера"), 12)) if f >= lo]
    facts.append((_("«Неизвестная деталь» при замене"), ", ".join(ser) if ser else _("нет")))
    facts.append((_("Чип U1 (UWB)"), _("есть") if f >= 11 and product != "iPhone17,5" and f != 8 else _("нет")))
    facts.append(("MagSafe", _("есть") if f >= 12 and product != "iPhone17,5" and f != 8 else _("нет")))
    sensors = [(k, d) for k, d in SENSORS.items() if applies(d, product)]
    sensors_other = [(k, d) for k, d in SENSORS.items() if applies(d, product) is None]
    buses = [b for b in I2C_BUSES if product in b["models"]]
    entries = [e for e in KB if applies(e, product)]
    return {"name": name, "product": product, "facts": facts, "sensors": sensors,
            "sensors_other": sensors_other, "buses": buses, "entries": entries}


# ---------------------------------------------------------------------------
# Лог для пополнения базы: без личных данных
# ---------------------------------------------------------------------------
_PRIVATE = [
    (re.compile(r"\b\d{15}\b"), "<IMEI>"),                                      # IMEI
    (re.compile(r"\b[0-9a-fA-F]{40}\b"), "<UDID>"),                             # старый UDID
    (re.compile(r"\b[0-9A-F]{8}-[0-9A-F]{16}\b"), "<UDID>"),                    # новый UDID
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"(?i)(serial(?:number)?|sn|imei|meid|ecid|udid)[\"']?\s*[:=]\s*[\"']?[\w-]+"), r"\1: <скрыто>"),
    (re.compile(r"(/Users/|/home/|C:\\\\Users\\\\|C:\\Users\\)[^/\\\s\"]+"), r"\1<user>"),
]


def anonymize(text):
    for rx, repl in _PRIVATE:
        text = rx.sub(repl, text)
    return text


def report_for_database(info, limit=3500):
    """Текст заявки «добавьте в базу»: модель, iOS, вид лога, что распознано и начало паники.
    Без имени файла, серийного номера, IMEI, UDID и путей."""
    lines = [f"Model: {info['model'] or '?'} ({info['product'] or '?'})",
             f"iOS: {info['os'] or '?'}",
             f"bug_type: {info['bug_type'] or '?'}",
             "Recognized: " + (", ".join(e["id"] for e, _hit in info["findings"]) or "nothing"),
             f"Missing sensors: {', '.join(info['missing_sensors']) or '—'}", "", "```"]
    body = info["panic"] or info["exception"] or ""
    body = anonymize(body.strip())
    if len(body) > limit:
        body = body[:limit] + "\n…"
    lines += [body, "```"]
    return "\n".join(lines)
