#!/bin/bash
# Запуск из исходников на Mac: двойной клик по этому файлу.
cd "$(dirname "$0")"
python3 -c "import pymobiledevice3" 2>/dev/null || python3 -m pip install --user -r requirements.txt
python3 ios_panic_reader.py
