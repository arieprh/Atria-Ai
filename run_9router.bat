@echo off
title Atria Farm - farm + inject 9Router
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
mode con: cols=90 lines=40

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Python belum terinstall.
    echo     Download: https://python.org/downloads
    echo     Saat install, centang "Add Python to PATH"
    pause
    exit /b 1
)

python -c "import httpx, camoufox" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Menginstall dependensi pertama kali...
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Gagal install dependensi.
        pause
        exit /b 1
    )
)

python -c "from camoufox.pkgman import installed_verstr; installed_verstr()" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Mengunduh browser Camoufox...
    python -m camoufox fetch
)

echo [*] MODE: farm + inject + test ke 9Router
echo [*] Pastikan config.py sudah diisi (ROUTER_URL + ROUTER_PASSWORD)
echo.
python atria_farm.py
pause
