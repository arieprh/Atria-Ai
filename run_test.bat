@echo off
title Atria Farm - retest 9Router
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
mode con: cols=90 lines=40

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Python belum terinstall.
    echo     Download: https://python.org/downloads
    pause
    exit /b 1
)

python -c "import httpx" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Menginstall dependensi pertama kali...
    python -m pip install -r requirements.txt
)

echo [*] MODE: re-test koneksi 9Router yang sudah ada
echo.
python atria_farm.py --test-only
pause
