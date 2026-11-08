# -*- coding: utf-8 -*-
"""Автообновление: проверка новой версии на GitHub, загрузка и установка при перезапуске.

Данные пользователя (история, логи, заметки, свои ошибки) лежат в Документы/iOSPanicReader
и при обновлении не трогаются: заменяется только сам файл программы. Перед установкой
делается резервная копия истории, а прошлая версия программы сохраняется в
Документы/iOSPanicReader/previous — к ней можно вернуться.
"""

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime

REPO = "mr1garik/ios-panic-reader"
# Адрес можно подменить переменной окружения — только для автотеста обновления
API_LATEST = os.environ.get("IOSPR_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_WINDOWS = "iOSPanicReader.exe"
ASSET_MAC = "iOSPanicReader-macOS.zip"


# ---------------------------------------------------------------------------
# Версии
# ---------------------------------------------------------------------------
def current_version():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(base, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def parse_version(v):
    v = v.strip().lstrip("vV")
    out = []
    for part in v.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


# ---------------------------------------------------------------------------
# Сеть
# ---------------------------------------------------------------------------
def _ssl_context():
    # В собранной программе на Mac системные сертификаты Python часто не находятся
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"iOSPanicReader/{current_version()}",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*",
    })
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def asset_name():
    if sys.platform == "win32":
        return ASSET_WINDOWS
    if sys.platform == "darwin":
        return ASSET_MAC
    return None


def check_latest():
    """Последний релиз: dict(version, notes, url, asset) или None, если файла для этой системы нет."""
    with _open(API_LATEST) as r:
        rel = json.load(r)
    name = asset_name()
    asset = next((a for a in rel.get("assets", []) if a.get("name") == name), None)
    return {
        "version": rel.get("tag_name", "").lstrip("v"),
        "notes": rel.get("body", "") or "",
        "url": rel.get("html_url", RELEASES_PAGE),
        "asset": asset and {"url": asset["browser_download_url"], "size": asset.get("size"),
                            "digest": asset.get("digest") or ""},
    }


def download(asset, dest, progress=None):
    """Скачивает файл и проверяет размер и контрольную сумму (если GitHub её дал)."""
    tmp = dest + ".part"
    h = hashlib.sha256()
    done = 0
    with _open(asset["url"], timeout=60) as r, open(tmp, "wb") as f:
        total = asset.get("size") or int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if asset.get("size") and done != asset["size"]:
        os.remove(tmp)
        raise IOError(f"файл скачан не полностью ({done} из {asset['size']} байт)")
    digest = asset.get("digest", "")
    if digest.startswith("sha256:") and digest[7:].lower() != h.hexdigest():
        os.remove(tmp)
        raise IOError("контрольная сумма не совпала — файл повреждён")
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------------------
# Установка
# ---------------------------------------------------------------------------
def can_self_update():
    """Обновлять себя умеет только собранная программа (exe или .app), не запуск из исходников."""
    return getattr(sys, "frozen", False) and asset_name() is not None


def install_target():
    """Что заменяем: путь к exe на Windows или к .app на Mac."""
    exe = os.path.abspath(sys.executable)
    if sys.platform == "darwin":
        p = exe
        while p and not p.endswith(".app"):
            p = os.path.dirname(p)
            if p == os.path.dirname(p):
                return None
        return p
    return exe


def check_writable():
    """Причина, по которой обновиться нельзя, или None."""
    if not can_self_update():
        return "Программа запущена из исходников — обновите её через git pull или скачайте новую версию."
    target = install_target()
    if not target:
        return "Не удалось найти, где установлена программа."
    folder = os.path.dirname(target)
    if not os.access(folder, os.W_OK):
        return f"Нет прав на запись в папку «{folder}». Перенесите программу в папку пользователя."
    return None


def backup_user_data(data_dir, version):
    """Резервная копия истории перед обновлением (сами данные не трогаются)."""
    src = os.path.join(data_dir, "history.json")
    if os.path.isfile(src):
        bdir = os.path.join(data_dir, "backups")
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(src, os.path.join(bdir, f"history-{version}-{datetime.now():%Y%m%d-%H%M%S}.json"))


def prepare(downloaded, data_dir):
    """Готовит новую версию к замене. Возвращает путь к новой программе (exe или .app)."""
    if sys.platform == "darwin":
        out = os.path.join(data_dir, "updates", "new")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out, exist_ok=True)
        subprocess.run(["ditto", "-x", "-k", downloaded, out], check=True)
        app = next((os.path.join(out, n) for n in os.listdir(out) if n.endswith(".app")), None)
        if not app:
            raise IOError("в архиве нет программы .app")
        return app
    return downloaded


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def windows_script(pids, target, new, backup, relaunch, log):
    """PowerShell-установщик. Ждёт завершения всех процессов программы (у exe в один файл их два:
    загрузчик и сама программа), затем заменяет файл, повторяя попытки, пока он занят.
    Каждый шаг пишет в журнал log. При ошибке возвращает старую версию."""
    waits = "\n".join(f"try {{ Wait-Process -Id {p} -Timeout 120 -ErrorAction Stop }} catch {{}}" for p in pids)
    return f"""$ErrorActionPreference = 'Stop'
$log = {_ps_quote(log)}
function L($m) {{ try {{ Add-Content -LiteralPath $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m) -Encoding UTF8 }} catch {{}} }}
L 'установщик запущен'
{waits}
L 'программа закрыта'
$old = {_ps_quote(target)}; $new = {_ps_quote(new)}; $bak = {_ps_quote(backup)}
if (Test-Path -LiteralPath $bak) {{ Remove-Item -LiteralPath $bak -Force }}
$moved = $false
for ($i = 0; $i -lt 60 -and -not $moved; $i++) {{
  try {{ Move-Item -LiteralPath $old -Destination $bak -Force; $moved = $true }}
  catch {{ if ($i -eq 0) {{ L ('файл программы занят, жду: ' + $_.Exception.Message) }}; Start-Sleep -Seconds 1 }}
}}
if (-not $moved) {{ L 'не удалось освободить файл программы — обновление отменено, осталась старая версия'; exit 1 }}
try {{
  Move-Item -LiteralPath $new -Destination $old -Force
  L 'новая версия установлена'
}} catch {{
  L ('ошибка установки: ' + $_.Exception.Message + ' — возвращаю старую версию')
  Move-Item -LiteralPath $bak -Destination $old -Force
}}
if (${'true' if relaunch else 'false'}) {{ Start-Process -FilePath $old; L 'программа запущена' }}
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force
"""


def _sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def mac_script(pid, target, new, backup, data_dir, relaunch):
    kb_old = os.path.join(target, "Contents", "MacOS", "user_kb.json")
    kb_keep = os.path.join(data_dir, "user_kb.json")
    log = os.path.join(data_dir, "updates", "update.log")
    return f"""#!/bin/bash
mkdir -p {_sh_quote(os.path.dirname(log))}
exec >>{_sh_quote(log)} 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') установщик запущен"
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
sleep 0.5
APP={_sh_quote(target)}; NEW={_sh_quote(new)}; BAK={_sh_quote(backup)}
# свои ошибки, если лежали внутри программы, переносим к данным
if [ -f {_sh_quote(kb_old)} ] && [ ! -f {_sh_quote(kb_keep)} ]; then cp {_sh_quote(kb_old)} {_sh_quote(kb_keep)}; fi
mkdir -p "$(dirname "$BAK")"
rm -rf "$BAK"
if mv "$APP" "$BAK"; then
  if mv "$NEW" "$APP"; then echo "$(date '+%Y-%m-%d %H:%M:%S') новая версия установлена"
  else mv "$BAK" "$APP"; echo "ошибка установки — возвращена старая версия"; fi
else echo "не удалось убрать старую версию — обновление отменено"; fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
{'open "$APP"' if relaunch else ':'}
rm -f -- "$0"
"""


def launch_installer(new, data_dir, version, relaunch=True):
    """Запускает отдельный скрипт, который дождётся закрытия программы и заменит её.
    После вызова программа должна сразу завершиться."""
    target = install_target()
    prev = os.path.join(data_dir, "previous")
    os.makedirs(prev, exist_ok=True)
    backup_user_data(data_dir, version)
    pid = os.getpid()
    if sys.platform == "win32":
        backup = os.path.join(prev, os.path.basename(target))
        log = os.path.join(data_dir, "updates", "update.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        # exe «в один файл»: родительский процесс — загрузчик, он тоже держит файл программы
        pids = [pid, os.getppid()] if getattr(sys, "_MEIPASS", None) and \
            os.path.dirname(sys._MEIPASS) != os.path.dirname(target) else [pid]
        fd, script = tempfile.mkstemp(suffix=".ps1", prefix="iospr-update-")
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write(windows_script(pids, target, new, backup, relaunch, log))
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script]
        no_window, new_group, breakaway = 0x08000000, 0x00000200, 0x01000000
        try:   # выходим из «задания» родителя, чтобы установщик не закрылся вместе с программой
            subprocess.Popen(cmd, creationflags=no_window | new_group | breakaway, close_fds=True)
        except OSError:
            subprocess.Popen(cmd, creationflags=no_window | new_group, close_fds=True)
    else:
        backup = os.path.join(prev, os.path.basename(target))
        fd, script = tempfile.mkstemp(suffix=".sh", prefix="iospr-update-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(mac_script(pid, target, new, backup, data_dir, relaunch))
        os.chmod(script, 0o755)
        subprocess.Popen(["/bin/bash", script], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def update_now(data_dir, log=print, relaunch=False):
    """Проверить, скачать и поставить обновление без окна (для командной строки и автотеста).
    Возвращает новую версию или None, если обновлять нечего."""
    log(f"текущая версия: {current_version()}")
    info = check_latest()
    log(f"на сервере: {info['version']}")
    if not is_newer(info["version"], current_version()):
        log("обновление не нужно")
        return None
    reason = check_writable()
    if reason:
        raise RuntimeError(reason)
    if not info["asset"]:
        raise RuntimeError(f"в релизе нет файла {asset_name()}")
    path = downloaded_path(data_dir, info["version"])
    download(info["asset"], path)
    log(f"скачано и проверено: {path}")
    new = prepare(path, data_dir)
    launch_installer(new, data_dir, current_version(), relaunch=relaunch)
    log("установщик запущен, программа завершается")
    return info["version"]


def download_dir(data_dir):
    """Куда качать: на Windows — рядом с exe (тот же диск, замена мгновенная)."""
    if sys.platform == "win32" and can_self_update():
        return os.path.dirname(install_target())
    d = os.path.join(data_dir, "updates")
    os.makedirs(d, exist_ok=True)
    return d


def downloaded_path(data_dir, version):
    name = f"iOSPanicReader-{version}.new.exe" if sys.platform == "win32" else f"iOSPanicReader-{version}.zip"
    return os.path.join(download_dir(data_dir), name)
