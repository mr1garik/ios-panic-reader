#!/bin/bash
# Сборка iOSPanicReader.app на Mac
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --windowed --name iOSPanicReader \
  --osx-bundle-identifier com.mr1garik.iospanicreader \
  --collect-all pymobiledevice3 \
  --hidden-import gui --hidden-import core --hidden-import device --hidden-import knowledge_base --hidden-import history --hidden-import report_pdf --collect-all reportlab \
  ios_panic_reader.py
echo "Готово: dist/iOSPanicReader.app"
