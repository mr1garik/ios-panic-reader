@echo off
chcp 65001 >nul
echo === Установка зависимостей ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
echo.
echo === Сборка iOSPanicReader.exe ===
python -m PyInstaller --noconfirm --onefile --noconsole --name iOSPanicReader --icon assets\icon.ico ^
  --collect-all pymobiledevice3 ^
  --hidden-import gui --hidden-import core --hidden-import device --hidden-import knowledge_base --hidden-import history --hidden-import report_pdf --hidden-import updater --collect-all reportlab --collect-data certifi --add-data VERSION:. --add-data errors_db.json:. --add-data assets/icon_256.png:assets ^
  ios_panic_reader.py
echo.
echo Готово: dist\iOSPanicReader.exe
pause
