# -*- coding: utf-8 -*-
"""Сквозная проверка автообновления на настоящей системе (запускается в сборке на Windows и Mac).

1. Ставит «старую» собранную программу во временную папку, создаёт данные пользователя.
2. Поднимает локальный сервер, который отдаёт «релиз» с версией 9.9.9 и новым файлом.
3. Запускает старую программу с --update: она должна найти версию, скачать, проверить,
   запустить установщик и завершиться.
4. Ждёт замены и проверяет: новая версия на месте, старая — в previous/, данные целы,
   копия истории в backups/.

Запуск:
  Windows: python tests/e2e_update.py --old dist/iOSPanicReader.exe --new dist-next/iOSPanicReader.exe
  Mac:     python tests/e2e_update.py --old dist/iOSPanicReader.app --new dist-next/iOSPanicReader.app
"""

import argparse
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

NEW_VERSION = "9.9.9"
for _s in (sys.stdout, sys.stderr):       # консоль Windows по умолчанию не в UTF-8
    _s.reconfigure(encoding="utf-8", errors="replace")
IS_WIN = sys.platform == "win32"


def fail(msg):
    print("ПРОВАЛ:", msg)
    sys.exit(1)


def binary(app):
    return app if IS_WIN else os.path.join(app, "Contents", "MacOS", "iOSPanicReader")


def run(app, args, env, timeout=180):
    return subprocess.run([binary(app)] + args, env=env, timeout=timeout)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="iospr-e2e-")
    home = os.path.join(tmp, "home Пользователь")          # пробел и кириллица — как у живых людей
    data = os.path.join(home, "Documents", "iOSPanicReader")
    os.makedirs(os.path.join(data, "Logs", "iPhone 13_TEST"))
    history = '{"phones": {"TEST": {"model": "iPhone 13", "note": "заметка мастера", "visits": [], "repairs": []}}, "settings": {"workshop": "Мастерская"}}'
    files = {
        "history.json": history,
        "user_kb.json": "[]",
        os.path.join("Logs", "iPhone 13_TEST", "panic-full-test.ips"): '{"bug_type":"210"}\n{"panicString":"panic(cpu 0): test"}',
    }
    for rel, content in files.items():
        with open(os.path.join(data, rel), "w", encoding="utf-8") as f:
            f.write(content)

    # «установленная» старая версия
    apps = os.path.join(tmp, "Программы")
    os.makedirs(apps)
    installed = os.path.join(apps, os.path.basename(a.old))
    if IS_WIN:
        shutil.copy2(a.old, installed)
    else:
        shutil.copytree(a.old, installed, symlinks=True)

    # файл новой версии и «релиз»
    srv = os.path.join(tmp, "server")
    os.makedirs(srv)
    if IS_WIN:
        asset_name = "iOSPanicReader.exe"
        shutil.copy2(a.new, os.path.join(srv, asset_name))
    else:
        asset_name = "iOSPanicReader-macOS.zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", a.new, os.path.join(srv, asset_name)], check=True)
    asset = os.path.join(srv, asset_name)
    with open(asset, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=srv)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    release = {"tag_name": "v" + NEW_VERSION, "body": "## Тест", "html_url": "http://127.0.0.1/",
               "assets": [{"name": asset_name, "size": os.path.getsize(asset), "digest": "sha256:" + digest,
                           "browser_download_url": f"http://127.0.0.1:{port}/{asset_name}"}]}
    with open(os.path.join(srv, "release.json"), "w", encoding="utf-8") as f:
        json.dump(release, f)

    env = dict(os.environ, HOME=home, USERPROFILE=home, IOSPR_LANG="ru",
               IOSPR_UPDATE_URL=f"http://127.0.0.1:{port}/release.json")

    # версия до обновления
    out = os.path.join(tmp, "ver_before.txt")
    run(installed, ["--version", "--out", out], env)
    old_version = read(out).strip()
    print("версия до:", old_version)
    if old_version == NEW_VERSION:
        fail("старая сборка уже 9.9.9")

    # обновление
    out = os.path.join(tmp, "update.txt")
    r = run(installed, ["--update", "--out", out], env)
    print(read(out) if os.path.exists(out) else "(нет вывода)")
    if r.returncode != 0:
        fail(f"--update вернул код {r.returncode}")

    # ждём, пока установщик заменит программу (запускать её раньше нельзя: на Windows занятый файл не заменить)
    backup = os.path.join(data, "previous", os.path.basename(installed))
    deadline = time.time() + 120
    while time.time() < deadline:
        if os.path.exists(backup) and os.path.exists(installed):
            break
        time.sleep(1)
    else:
        log = os.path.join(data, "updates", "update.log")
        print("журнал установщика:\n" + (read(log) if os.path.exists(log) else "(нет журнала)"))
        fail("установщик не заменил программу за 2 минуты")
    time.sleep(3)

    out = os.path.join(tmp, "ver_after.txt")
    run(installed, ["--version", "--out", out], env)
    new_version = read(out).strip()
    print("версия после:", new_version)
    if new_version != NEW_VERSION:
        fail(f"после обновления версия {new_version}, ожидалась {NEW_VERSION}")

    # данные целы
    for rel, content in files.items():
        p = os.path.join(data, rel)
        if not os.path.exists(p) or read(p) != content:
            fail(f"данные изменились или пропали: {rel}")
    backups = os.listdir(os.path.join(data, "backups"))
    if not backups:
        fail("нет резервной копии истории")
    if read(os.path.join(data, "backups", backups[0])) != history:
        fail("резервная копия истории не совпадает")

    # прошлая версия сохранена и рабочая
    out = os.path.join(tmp, "ver_prev.txt")
    run(backup, ["--version", "--out", out], env)
    if read(out).strip() != old_version:
        fail("в previous/ не прошлая версия")

    # повторная проверка: обновлять уже нечего
    out = os.path.join(tmp, "update2.txt")
    r = run(installed, ["--update", "--out", out], env)
    print(read(out))
    if r.returncode != 0 or "обновление не нужно" not in read(out):
        fail("повторная проверка должна сказать, что обновление не нужно")

    log = os.path.join(data, "updates", "update.log")
    print("журнал установщика:\n" + (read(log) if os.path.exists(log) else "(нет журнала)"))
    print(f"УСПЕХ: {old_version} → {new_version}, данные целы, прошлая версия в previous/")
    httpd.shutdown()


if __name__ == "__main__":
    main()
