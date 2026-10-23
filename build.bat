@echo off
rem Build a single-file Windows .exe (double-clickable, no console).
rem Run once from this folder. Needs no admin rights, here or on the target.
rem
rem Everything is pure Python wheels (PySide6, pikepdf, Pillow, fontTools,
rem msoffcrypto-tool): no external binaries are bundled.
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed ^
    --name DocUnlock ^
    --icon assets\docunlock.ico ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtPdf ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module tkinter ^
    main.py

echo.
echo Listo: dist\DocUnlock.exe (se instala solo al abrirlo la primera vez)
endlocal
