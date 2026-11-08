# -*- coding: utf-8 -*-
"""Собирает все фразы для перевода: _("…") и plural(…) в коде + названия разделов,
видов логов и типов логов из базы. Используется тестом и при добавлении переводов."""
import ast
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["gui.py", "core.py", "knowledge_base.py", "report_pdf.py", "updater.py", "ios_panic_reader.py", "history.py", "device.py"]
CYR = re.compile("[А-Яа-яЁё]")


def code_keys():
    keys = set()
    for f in FILES:
        with open(os.path.join(HERE, f), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and (getattr(n.func, "id", "") in ("_", "plural") or
                                            getattr(n.func, "attr", "") == "_"):
                args = n.args if getattr(n.func, "id", "") == "plural" else n.args[:1]
                for a in args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and CYR.search(a.value):
                        keys.add(a.value)
    return keys


def db_keys():
    with open(os.path.join(HERE, "errors_db.json"), encoding="utf-8") as f:
        db = json.load(f)
    keys = set(db["categories"]) | set(db["bug_types"].values()) | {k for _r, k in db["file_kinds"]}
    keys |= {"Лог", "Отчёт о сбое", "Шины I2C", "неизвестно"}
    return keys


def all_keys():
    return sorted(code_keys() | db_keys())


if __name__ == "__main__":
    print(json.dumps(all_keys(), ensure_ascii=False, indent=0))
