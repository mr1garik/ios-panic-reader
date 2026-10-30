# -*- coding: utf-8 -*-
"""Разбор логов iOS и общий вывод: что с телефоном и какая деталь виновата."""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

from knowledge_base import BUG_TYPES, FILE_KINDS, KB, PRODUCTS, sensor_info

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
    """Свои записи из user_kb.json рядом с программой."""
    path = os.path.join(app_dir(), "user_kb.json")
    if not os.path.isfile(path):
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
    text = _read_text(path)
    info = {
        "file": path, "raw": text, "header": {}, "body": {}, "product": "", "model": "",
        "os": "", "date": "", "bug_type": "", "panic": "", "process": "", "exception": "",
        "kind": file_kind(path), "missing_sensors": [], "findings": [], "is_panic": False,
    }

    stripped = text.lstrip("﻿").strip()
    first, _, rest = stripped.partition("\n")
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
    if info["kind"] in ("Лог", "Отчёт о сбое") and info["bug_type"] in BUG_TYPES:
        info["kind"] = BUG_TYPES[info["bug_type"]]
    info["is_panic"] = bool(info["panic"]) or info["bug_type"] in ("210", "409") or \
        "panic" in os.path.basename(path).lower()
    analyze(info)
    return info


def analyze(info):
    if info["panic"]:
        hay = info["panic"]
    else:
        hay = " ".join([info["exception"], os.path.basename(info["file"]), info["raw"][:4000]])

    m = re.search(r"Missing sensor\(s\):\s*([^\n\\\"]+)", hay)
    if m:
        info["missing_sensors"] = [s for s in re.split(r"[\s,]+", m.group(1).strip()) if s]

    for e in KB:
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
        return "Нет датчика: " + ", ".join(info["missing_sensors"]) + " (" + "; ".join(dict.fromkeys(names)) + ")"
    for e, _ in info["findings"]:
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
    out.append("Файл:        " + os.path.basename(info["file"]))
    out.append("Вид лога:    " + info["kind"])
    out.append("Устройство:  " + device_label(info))
    out.append("iOS:         " + (info["os"] or "—"))
    out.append("Дата:        " + (str(info["date"]) or "—"))
    bt = info["bug_type"]
    out.append("bug_type:    " + (f"{bt} — {BUG_TYPES.get(bt, 'неизвестно')}" if bt else "—"))
    if info["process"]:
        out.append("Процесс:     " + info["process"])
    if info["exception"]:
        out.append("Исключение:  " + info["exception"])
    out.append("")

    if info["missing_sensors"]:
        out.append("ОТСУТСТВУЮЩИЕ ДАТЧИКИ:")
        for s in info["missing_sensors"]:
            d = sensor_info(s)
            out.append(f"  • {s} — {d['name']}")
            out.append(f"      Где стоит:   {d['where']}")
            if d.get("models"):
                out.append(f"      По моделям:  {d['models']}")
            out.append(f"      Что делать:  {d['fix']}")
        out.append("")

    out.append("РАСШИФРОВКА:")
    if info["findings"]:
        for i, (e, hit) in enumerate(info["findings"], 1):
            out.append(f"  {i}. {e['title']}   [найдено: «{hit}»]")
            out.append(f"     Узел:         {e['node']}")
            out.append(f"     Как ведёт себя: {e['symptoms']}")
            out.append(f"     Почему:       {e['cause']}")
            out.append(f"     Что делать:   {e['fix']}")
            out.append("")
    else:
        out.append("  Известных шаблонов не найдено. Посмотри текст ниже или исходный лог.")
        out.append("")

    if info["panic"]:
        out.append("ТЕКСТ ПАНИКИ (panicString):")
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
    out = ["СВОДКА ПО ТЕЛЕФОНУ", "=" * 72]
    if device_info:
        for k, v in device_info.items():
            out.append(f"{k + ':':16}{v}")
        out.append("")
    if not logs:
        out.append("Логов нет.")
        return "\n".join(out)

    panics = [l for l in logs if l["is_panic"]]
    kinds = Counter(l["kind"] for l in logs)
    out.append(f"Всего логов: {len(logs)}, из них паник ядра: {len(panics)}")
    for k, n in kinds.most_common():
        out.append(f"  {k}: {n}")
    out.append("")

    if panics:
        causes = Counter(main_cause(p) for p in panics)
        out.append("ЧАСТЫЕ ПРИЧИНЫ ПАНИК:")
        for c, n in causes.most_common(8):
            out.append(f"  {n:4} × {c}")
        out.append("")

        sensors = Counter(s for p in panics for s in p["missing_sensors"])
        if sensors:
            out.append("ОТСУТСТВУЮЩИЕ ДАТЧИКИ (по всем паникам):")
            for s, n in sensors.most_common():
                d = sensor_info(s)
                out.append(f"  {n:4} × {s} — {d['name']}: {d['where']}")
            out.append("")

        dates = sorted(d for d in (_parse_date(p["date"]) for p in panics) if d)
        if dates:
            out.append(f"Первая паника: {dates[0]:%Y-%m-%d %H:%M}   последняя: {dates[-1]:%Y-%m-%d %H:%M}")
            if len(dates) >= 3:
                gaps = []
                for a, b in zip(dates, dates[1:]):
                    try:
                        gaps.append((b - a).total_seconds())
                    except TypeError:
                        pass
                short = [g for g in gaps if 0 < g < 600]
                if len(short) >= 2:
                    out.append(f"Паники идут сериями с интервалом ~{int(sorted(short)[len(short)//2])} с "
                               "→ телефон перезагружается по кругу.")
            out.append("")

        osv = Counter(p["os"] for p in panics if p["os"])
        if len(osv) > 1:
            out.append("Паники на разных версиях iOS: " + ", ".join(osv) +
                       " → если причина одна и та же, это железо, а не прошивка.")
            out.append("")

        top, n = causes.most_common(1)[0]
        out.append("ВЫВОД:")
        if n >= 3 and n / len(panics) >= 0.6:
            out.append(f"  Повторяющаяся причина ({n} из {len(panics)}): {top}.")
            out.append("  Одинаковые паники подряд почти всегда означают аппаратную неисправность этого узла.")
        elif len(causes) > 3:
            out.append("  Причины паник разные — подозрение на ПО, питание (аккумулятор), память или процессор.")
        else:
            out.append(f"  Основная причина: {top}. Открой паники в списке для подробностей.")
    else:
        out.append("Паник ядра нет — аппаратных сбоев по логам не видно.")
    crashes = [l for l in logs if not l["is_panic"] and l["exception"]]
    if crashes:
        apps = Counter(l["process"] or "?" for l in crashes)
        out.append("")
        out.append("ВЫЛЕТЫ ПРИЛОЖЕНИЙ:")
        for a, n in apps.most_common(10):
            out.append(f"  {n:4} × {a}")
    return "\n".join(out)


def collect_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
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
    ("battery", "Аккумулятор"),
    ("charge_flex", "Шлейф зарядки (нижний микрофон, барометр)"),
    ("top_flex", "Верхний шлейф (датчики, микрофон)"),
    ("display", "Дисплей и тач"),
    ("camera", "Камеры"),
    ("biometry", "Face ID / Touch ID"),
    ("baseband", "Модем (сеть, IMEI)"),
    ("wifi", "Wi-Fi / Bluetooth / NFC"),
    ("audio", "Звук (кодек, динамики)"),
    ("usb", "Контроллер зарядки / USB"),
    ("board", "Плата (питание, память, процессор)"),
    ("software", "Программное обеспечение"),
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
    for e, _ in info["findings"]:
        if e["id"] in KB_PART:
            return KB_PART[e["id"]]
    return None


def _main_entry(info):
    for e, _ in info["findings"]:
        if e["id"] in KB_PART or e["id"] == "thermalmonitord":
            return e
    return info["findings"][0][0] if info["findings"] else None


def build_verdict(logs, dev=None):
    """Список проблем для главного экрана, от самой важной.
    Проблема: dict(level='red'|'orange', title, how, why, fix=[...], note, part)."""
    problems = []
    panics = [l for l in logs if l["is_panic"]]

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
            why = f"Телефон не видит: {names}. Где стоит: {where['where']}"
            fix = [x.strip() for x in where["fix"].split(". ") if x.strip()]
            how = KB[[k["id"] for k in KB].index("thermalmonitord")]["symptoms"]
        else:
            why = e["cause"] if e else "—"
            fix = [x.strip() for x in (e["fix"] if e else "").split(". ") if x.strip()]
            how = e["symptoms"] if e else "—"
        problems.append(dict(
            level=level, part=part, title=PART_NAMES[part], how=how, why=why, fix=fix,
            note=f"{n} из {len(panics)} {_plural_panic(len(panics))} указывают на эту деталь", count=n))

    unknown = by_part.get(None, [])
    if len(unknown) >= 3:
        problems.append(dict(
            level="orange", part="software", title="Случайные перезагрузки",
            how="Телефон иногда перезагружается сам.",
            why="Паники разные и не указывают на одну деталь — чаще ПО, реже питание или память.",
            fix=["Обновить или восстановить iOS", "Если не помогло — проверить аккумулятор и плату"],
            note=f"{len(unknown)} паник без явной причины", count=len(unknown)))

    if dev:
        h = dev.get("battery_health")
        if h is not None and h < 80 and not any(p["part"] == "battery" for p in problems):
            problems.append(dict(
                level="red", part="battery", title="Аккумулятор изношен",
                how="Быстро садится, может выключаться на 20–30% заряда или на холоде.",
                why=f"Ёмкость {h}% от заводской" +
                    (f", {dev['battery_cycles']} циклов" if dev.get("battery_cycles") else "") +
                    ". Apple считает нормой не ниже 80%.",
                fix=["Заменить аккумулятор"], note="по данным контроллера аккумулятора", count=0))
        if dev.get("is_iphone") and not dev.get("imei") and \
                not any(p["part"] == "baseband" for p in problems):
            problems.append(dict(
                level="orange", part="baseband", title="IMEI не прочитан",
                how="Если в Настройках → Основные → Об этом устройстве IMEI тоже пустой — нет сети.",
                why="Модем не отдал IMEI. Бывает при неисправном модеме или его питании.",
                fix=["Проверить IMEI в настройках телефона", "Если пустой — диагностика модема"],
                note="по данным телефона", count=0))

    problems.sort(key=lambda p: (p["level"] != "red", -p["count"]))
    return problems


def parts_table(logs, dev=None):
    """Строки для экрана «Детали»: (деталь, данные с телефона, сбои в логах, уровень)."""
    panics = [l for l in logs if l["is_panic"]]
    fails = {}
    for p in panics:
        part = panic_part(p)
        if part:
            fails.setdefault(part, Counter())[main_cause(p)] += 1
    dev = dev or {}
    data = {
        "battery": ", ".join(x for x in (
            f"ёмкость {dev['battery_health']}%" if dev.get("battery_health") is not None else "",
            f"{dev['battery_cycles']} циклов" if dev.get("battery_cycles") is not None else "",
            f"серийный {dev['battery_serial']}" if dev.get("battery_serial") else "") if x),
        "baseband": ", ".join(x for x in (
            f"IMEI {dev['imei']}" if dev.get("imei") else ("IMEI не прочитан" if dev else ""),
            f"прошивка модема {dev['baseband']}" if dev.get("baseband") else "") if x),
        "wifi": ", ".join(x for x in (
            f"Wi-Fi {dev['wifi_mac']}" if dev.get("wifi_mac") else "",
            f"BT {dev['bt_mac']}" if dev.get("bt_mac") else "") if x),
        "board": f"плата {dev['hw_model']}" if dev.get("hw_model") else "",
        "software": f"iOS {dev['ios']} ({dev.get('build', '')})" if dev.get("ios") else "",
    }
    rows = []
    for pid, name in PARTS:
        c = fails.get(pid)
        n = sum(c.values()) if c else 0
        fail_text = f"{n} {_plural_panic(n)}: " + "; ".join(k for k, _ in c.most_common(2)) if n else "нет"
        level = "red" if n >= 3 else ("orange" if n else "green")
        if pid == "battery" and dev.get("battery_health") is not None and dev["battery_health"] < 80:
            level = "red"
        if pid == "baseband" and dev and dev.get("is_iphone") and not dev.get("imei") and level == "green":
            level = "orange"
        rows.append((name, data.get(pid, "") or "—", fail_text, level))
    return rows


def _plural_panic(n):
    if n % 10 == 1 and n % 100 != 11:
        return "паника"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "паники"
    return "паник"
