#!/bin/bash
# Сборка iOSPanicReader.app на Mac
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --windowed --name iOSPanicReader --icon assets/icon.icns \
  --osx-bundle-identifier com.mr1garik.iospanicreader \
  --collect-all pymobiledevice3 \
  --hidden-import gui --hidden-import core --hidden-import device --hidden-import knowledge_base --hidden-import history --hidden-import report_pdf --hidden-import updater --collect-all reportlab --collect-data certifi --add-data VERSION:. --add-data errors_db.json:. --add-data assets/icon_256.png:assets \
  ios_panic_reader.py
echo "Готово: dist/iOSPanicReader.app"
