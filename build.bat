@echo off
rem Build a single-file Windows .exe (double-clickable, no console).
rem Run once from this folder. Needs the venv set up (see README).
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
    --collect-submodules PySide6 ^
    main.py

echo.
echo Listo: dist\DocUnlock.exe
endlocal
