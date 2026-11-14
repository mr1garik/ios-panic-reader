# -*- coding: utf-8 -*-
"""Сквозная проверка автообновления на настоящей системе (запускается в сборке на Windows и Mac).

1. Ставит «старую» собранную программу во временную папку, создаёт данные пользователя.
2. Поднимает локальный сервер, который отдаёт «релиз» с версией 9.9.9 и новым файлом.
3. Запускает старую программу с --update: она должна найти версию, скачать, проверить,
   запустить установщик и завершиться.
4. Ждёт замены и проверяет: новая версия на месте, старая — в previous/, данные целы,
   копия истории в backups/.

Режимы:
  --mode cli  (по умолчанию) — обновление командой --update, без перезапуска;
  --mode gui  — настоящее окно программы: проверка при запуске, загрузка с прогрессом, установка
                и перезапуск новой версии (как при нажатии «Обновить сейчас»).
  --installed ПУТЬ — обновлять уже установленную программу (например, установщиком), а не копию.
Версия «новой» программы берётся из неё самой (--version).

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


def running(app):
    """Процессы, запущенные из этой программы."""
    if IS_WIN:
        ps = ("Get-Process -Name iOSPanicReader -ErrorAction SilentlyContinue | "
              f"Where-Object {{ $_.Path -eq '{app}' }} | ForEach-Object {{ $_.Id }}")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    else:
        out = subprocess.run(["pgrep", "-f", binary(app)], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def stop(pids):
    for pid in pids:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            subprocess.run(["kill", str(pid)], capture_output=True)
    time.sleep(2)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def serve_release(tmp, home, new):
    """Локальный «релиз»: файл новой версии и описание, как у GitHub API."""
    srv = os.path.join(tmp, "server")
    os.makedirs(srv)
    if IS_WIN:
        asset_name = "iOSPanicReader.exe"
        shutil.copy2(new, os.path.join(srv, asset_name))
    else:
        asset_name = "iOSPanicReader-macOS.zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", new, os.path.join(srv, asset_name)], check=True)
    asset = os.path.join(srv, asset_name)
    with open(asset, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=srv)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    out = os.path.join(tmp, "ver_new.txt")
    run(new, ["--version", "--out", out], dict(os.environ, HOME=home, USERPROFILE=home))
    new_version_expected = read(out).strip()
    print("новая версия (в релизе):", new_version_expected)
    release = {"tag_name": "v" + new_version_expected, "body": "## Тест", "html_url": "http://127.0.0.1/",
               "assets": [{"name": asset_name, "size": os.path.getsize(asset), "digest": "sha256:" + digest,
                           "browser_download_url": f"http://127.0.0.1:{port}/{asset_name}"}]}
    with open(os.path.join(srv, "release.json"), "w", encoding="utf-8") as f:
        json.dump(release, f)

    return httpd, new_version_expected, f"http://127.0.0.1:{port}/release.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", help="новая сборка (её отдаёт локальный «релиз»)")
    ap.add_argument("--real", metavar="ВЕРСИЯ",
                    help="без локального сервера: обновиться с настоящего релиза на GitHub до этой версии")
    ap.add_argument("--mode", choices=["cli", "gui"], default="cli")
    ap.add_argument("--installed", help="уже установленная программа, которую надо обновить")
    a = ap.parse_args()
    if not a.new and not a.real:
        ap.error("нужен --new или --real")

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
    if a.installed:
        installed = os.path.abspath(a.installed)
    else:
        installed = os.path.join(apps, os.path.basename(a.old))
        if IS_WIN:
            shutil.copy2(a.old, installed)
        else:
            shutil.copytree(a.old, installed, symlinks=True)

    env = dict(os.environ, HOME=home, USERPROFILE=home, IOSPR_LANG="ru")
    httpd = None
    if a.real:
        new_version_expected = a.real
        env.pop("IOSPR_UPDATE_URL", None)
        print("настоящий релиз на GitHub, ожидается версия", new_version_expected)
    else:
        httpd, new_version_expected, url = serve_release(tmp, home, a.new)
        env["IOSPR_UPDATE_URL"] = url

    # версия до обновления
    out = os.path.join(tmp, "ver_before.txt")
    run(installed, ["--version", "--out", out], env)
    old_version = read(out).strip()
    print("версия до:", old_version)
    if old_version == new_version_expected:
        fail(f"старая сборка уже {new_version_expected}")

    # обновление
    if a.mode == "cli":
        out = os.path.join(tmp, "update.txt")
        for attempt in range(4):
            r = run(installed, ["--update", "--out", out], env)
            text = read(out) if os.path.exists(out) else "(нет вывода)"
            print(text)
            not_seen = r.returncode == 0 and "обновление не нужно" in text
            if not a.real:
                if not_seen:
                    fail(f"программа не увидела версию {new_version_expected}")
                break
            if r.returncode == 0 and not not_seen:
                break
            time.sleep(30)   # настоящий GitHub: лимит запросов или релиз ещё не появился
        if r.returncode != 0 or "обновление не нужно" in text:
            fail(f"обновление не прошло (код {r.returncode})")
    else:
        # обычный запуск окна: программа сама находит версию и «нажимает» «Обновить сейчас»
        old_proc = subprocess.Popen([binary(installed)], env=dict(env, IOSPR_TEST_AUTOUPDATE="1"))
        try:
            old_proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            old_proc.kill()
            fail("окно программы не закрылось само после загрузки обновления за 3 минуты")
        print("старая программа закрылась, код", old_proc.returncode)

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
    if new_version != new_version_expected:
        fail(f"после обновления версия {new_version}, ожидалась {new_version_expected}")

    if a.mode == "gui":
        pids = []
        for _ in range(60):
            pids = running(installed)
            if pids:
                break
            time.sleep(1)
        if not pids:
            fail("после обновления новая версия не запустилась сама")
        print("новая версия запущена сама, процессы:", pids)
        stop(pids)

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
    print(f"УСПЕХ ({a.mode}): {old_version} → {new_version}, данные целы, прошлая версия в previous/")
    if httpd:
        httpd.shutdown()


if __name__ == "__main__":
    main()
