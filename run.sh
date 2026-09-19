#!/usr/bin/env bash
# Atria Farm — launcher Linux
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

# cek python
if ! command -v python3 &>/dev/null; then
    echo "[!] python3 belum terinstall."
    echo "    Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "    Fedora:        sudo dnf install python3 python3-pip"
    exit 1
fi

# cek dependensi, install kalau belum ada
if ! python3 -c "import httpx, camoufox" &>/dev/null; then
    echo "[*] Menginstall dependensi pertama kali..."
    python3 -m pip install -r requirements.txt
fi

# download browser camoufox kalau belum ada
if ! python3 -c "from camoufox.pkgman import installed_verstr; installed_verstr()" &>/dev/null; then
    echo "[*] Mengunduh browser Camoufox..."
    python3 -m camoufox fetch
fi

python3 atria_farm.py
