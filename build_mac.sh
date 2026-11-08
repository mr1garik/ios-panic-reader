#!/bin/bash
# Сборка iOSPanicReader.app на Mac
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt pyinstaller
python3 build.py
echo "Готово: dist/iOSPanicReader.app"
