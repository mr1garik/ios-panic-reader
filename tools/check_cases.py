# -*- coding: utf-8 -*-
"""Проверка точности диагноза на реальных случаях с известной поломкой.

Случай — папка в tests/cases/<имя>/ с логами телефона и файлом case.json:
  {"model": "iPhone 11", "replaced": "шлейф зарядки", "expect": "charge_flex",
   "note": "перезагрузки каждые 3 минуты, после замены шлейфа прошло"}
  expect — деталь, которую программа должна назвать первой (ключи из core.PARTS), или "none",
  если телефон исправен и программа не должна ничего находить.

Добавить случай из папки с логами (серийный номер, IMEI, UDID и пути убираются):
  python tools/check_cases.py --add ПАПКА_С_ЛОГАМИ --name iphone11-flex --expect charge_flex --replaced "шлейф зарядки"
Проверить все случаи:
  python tools/check_cases.py
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("IOSPR_LANG", "ru")
import core  # noqa: E402

CASES = os.path.join(ROOT, "tests", "cases")


def add_case(src, name, expect, replaced, note, model):
    if expect != "none" and expect not in core.PART_NAMES:
        sys.exit(f"неизвестная деталь {expect!r}; можно: none, " + ", ".join(core.PART_NAMES))
    dst = os.path.join(CASES, re.sub(r"[^\w.-]+", "-", name))
    if os.path.exists(dst):
        sys.exit(f"случай {dst} уже есть")
    os.makedirs(dst)
    n = 0
    for f in core.collect_files([src]):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = core.anonymize(fh.read())
        except OSError:
            continue
        n += 1
        ext = os.path.splitext(f)[1] or ".ips"
        with open(os.path.join(dst, f"log{n:03d}{ext}"), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(dst, "case.json"), "w", encoding="utf-8") as fh:
        json.dump({"model": model, "replaced": replaced, "expect": expect, "note": note}, fh,
                  ensure_ascii=False, indent=1)
    print(f"добавлен {dst}: {n} логов (без серийного номера, IMEI, UDID и путей)")


def check_case(folder):
    """(ожидалось, что выдала программа первым, совпало ли, все найденные проблемы)."""
    with open(os.path.join(folder, "case.json"), encoding="utf-8") as fh:
        case = json.load(fh)
    logs = [core.parse_log(f) for f in core.collect_files([folder]) if not f.endswith("case.json")]
    problems = core.build_verdict(logs)
    top = problems[0]["part"] if problems else "none"
    return case, top, top == case["expect"], [p["part"] for p in problems]


def all_cases():
    if not os.path.isdir(CASES):
        return []
    return sorted(os.path.join(CASES, d) for d in os.listdir(CASES)
                  if os.path.isfile(os.path.join(CASES, d, "case.json")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", metavar="ПАПКА")
    ap.add_argument("--name")
    ap.add_argument("--expect", help="деталь: " + ", ".join(core.PART_NAMES) + " или none")
    ap.add_argument("--replaced", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--model", default="")
    a = ap.parse_args()
    if a.add:
        if not (a.name and a.expect):
            ap.error("для --add нужны --name и --expect")
        return add_case(a.add, a.name, a.expect, a.replaced, a.note, a.model)

    cases = all_cases()
    if not cases:
        print("случаев нет — добавьте: python tools/check_cases.py --add ПАПКА --name ... --expect ...")
        return
    ok = 0
    for c in cases:
        case, top, good, found = check_case(c)
        ok += good
        mark = "✓" if good else "✗"
        print(f"{mark} {os.path.basename(c):30} ждали {case['expect']:12} получили {top:12} "
              f"(все: {', '.join(found) or '—'}) {case.get('replaced', '')}")
    print(f"\nверно {ok} из {len(cases)} ({ok * 100 // len(cases)}%)")
    sys.exit(0 if ok == len(cases) else 1)


if __name__ == "__main__":
    main()
