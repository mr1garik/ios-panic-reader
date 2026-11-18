@echo off
chcp 65001 >nul
cd /d "%~dp0.."
python -c "import pymobiledevice3" 2>nul || python -m pip install -r requirements.txt
start "" pythonw app\ios_panic_reader.py
