@echo off
title Atria Farm
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

REM cek dependensi, install kalau belum ada
python -c "import httpx, camoufox" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Menginstall dependensi pertama kali...
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Gagal install dependensi. Coba jalankan manual:
        echo     pip install -r requirements.txt
        pause
        exit /b 1
    )
)

REM download browser camoufox kalau belum ada
python -c "from camoufox.pkgman import installed_verstr; installed_verstr()" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Mengunduh browser Camoufox...
    python -m camoufox fetch
)

python atria_farm.py
pause
