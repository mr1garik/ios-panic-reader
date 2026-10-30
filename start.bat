@echo off
chcp 65001 >nul
python -c "import pymobiledevice3" 2>nul || python -m pip install -r requirements.txt
start "" pythonw ios_panic_reader.py
