# -*- coding: utf-8 -*-
"""
iOS Panic Reader — программа для Windows: снимает логи с iPhone по USB и простыми словами
объясняет, что с телефоном, какая деталь виновата и что делать.

Запуск:            python ios_panic_reader.py [файлы или папки с логами]
Без окна (отчёт):  python ios_panic_reader.py --cli <файлы или папки>
"""

import os
import sys

# В exe без консоли stdout = None — некоторые библиотеки пытаются туда писать
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
# Консоль Windows по умолчанию не в UTF-8 — без этого русский текст в --cli падает
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import core  # noqa: E402


def _out(args):
    """--out ФАЙЛ: куда писать результат (у программы без консоли нет вывода на экран)."""
    if "--out" in args:
        path = args[args.index("--out") + 1]
        f = open(path, "w", encoding="utf-8")
        return lambda msg: (f.write(msg + "\n"), f.flush())
    return print


def main():
    args = sys.argv[1:]
    if args and args[0] == "--version":
        import updater
        _out(args)(updater.current_version())
        return
    if args and args[0] == "--update":
        import updater
        log = _out(args)
        try:
            updater.update_now(os.path.dirname(core.logs_root()), log)
        except Exception as e:
            log(f"ОШИБКА: {e.__class__.__name__}: {e}")
            sys.exit(1)
        return
    core.load_user_kb()
    if args and args[0] == "--cli":
        parsed = [core.parse_log(f) for f in core.collect_files(args[1:])]
        print(core.build_summary(parsed))
        print()
        for p in core.build_verdict(parsed):
            print(f"[{'ВАЖНО' if p['level'] == 'red' else 'НЕ СРОЧНО'}] {p['title']} — {p['note']}")
            print("  Почему:", p["why"])
            print("  Что делать:", "; ".join(p["fix"]))
        print()
        for info in parsed:
            print(core.build_report(info))
        return
    from gui import run_gui
    run_gui(args)


if __name__ == "__main__":
    main()
