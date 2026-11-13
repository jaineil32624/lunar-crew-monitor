@echo off
title SELENE - Lunar Habitat AI
cd /d "%~dp0"
echo.
echo   ===========================================
echo     SELENE  -  Lunar Habitat AI Dashboard
echo   ===========================================
echo.

rem ---- find Python (prefer 3.12) ----
set "PY="
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto nopython

rem ---- first run: create a private Python environment and install ----
if not exist ".venv\Scripts\python.exe" (
    echo First start: setting things up. This takes a few minutes, only once.
    %PY% -m venv .venv || goto fail
)
if not exist ".venv\setup_core.ok" (
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements-core.txt || goto fail
    echo ok> ".venv\setup_core.ok"
)
if not exist ".venv\setup_full.ok" (
    echo Installing camera scan and Claude features (optional^)...
    ".venv\Scripts\python.exe" -m pip install opencv-python mediapipe anthropic && (
        ".venv\Scripts\python.exe" -m crew_monitor setup-models && echo ok> ".venv\setup_full.ok"
    ) || echo   Optional features could not be installed. The dashboard still works.
)

rem ---- pick the data file: your own in data\ first, else the example ----
set "DATA=examples\data_format_example.csv"
for %%F in (data\*.csv data\*.json data\*.jsonl) do set "DATA=%%F"
echo Opening SELENE with data file: %DATA%
".venv\Scripts\python.exe" -m crew_monitor dashboard --data "%DATA%" || goto fail
exit /b 0

:nopython
echo Python is not installed on this computer.
echo.
echo  1. The Python download page will open now.
echo  2. Install Python 3.12 and TICK "Add python.exe to PATH".
echo     (No admin rights? Install "Python 3.12" from the Microsoft Store instead.)
echo  3. Double-click this file again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:fail
echo.
echo Something went wrong (see the message above). Copy it and ask for help.
pause
exit /b 1
