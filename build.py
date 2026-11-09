# -*- coding: utf-8 -*-
"""Сборка программы PyInstaller'ом — одна команда для Windows (exe) и Mac (.app).

  python build.py                         → dist/iOSPanicReader.exe или dist/iOSPanicReader.app
  python build.py --dist dist-next --version 9.9.9   → тестовая сборка с другим номером версии
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ["gui", "core", "device", "knowledge_base", "history", "report_pdf", "updater", "i18n"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default="dist")
    ap.add_argument("--version", help="подменить номер версии в сборке (для тестов обновления)")
    a = ap.parse_args()

    work = tempfile.mkdtemp(prefix="iospr-build-")
    version_file = os.path.join(HERE, "VERSION")
    if a.version:
        version_file = os.path.join(work, "VERSION")
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(a.version)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--name", "iOSPanicReader",
           "--distpath", a.dist, "--workpath", os.path.join(work, "build"), "--specpath", work,
           "--collect-all", "pymobiledevice3", "--collect-all", "reportlab", "--collect-data", "certifi",
           "--add-data", f"{version_file}{os.pathsep}.",
           "--add-data", f"{os.path.join(HERE, 'errors_db.json')}{os.pathsep}.",
           "--add-data", f"{os.path.join(HERE, 'translations.json')}{os.pathsep}.",
           "--add-data", f"{os.path.join(HERE, 'assets', 'icon_256.png')}{os.pathsep}assets"]
    for m in MODULES:
        cmd += ["--hidden-import", m]
    if sys.platform == "win32":
        cmd += ["--onefile", "--noconsole", "--icon", os.path.join(HERE, "assets", "icon.ico")]
    elif sys.platform == "darwin":
        cmd += ["--windowed", "--icon", os.path.join(HERE, "assets", "icon.icns"),
                "--osx-bundle-identifier", "com.mr1garik.iospanicreader"]
    cmd.append(os.path.join(HERE, "ios_panic_reader.py"))
    print(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=HERE)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
