@echo off
chcp 65001 >nul
echo === Установка зависимостей ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
echo.
echo === Сборка iOSPanicReader.exe ===
python build.py
echo.
echo Готово: dist\iOSPanicReader.exe
pause
