#!/usr/bin/env bash
# Atria Farm — farm + inject + test ke 9Router
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if ! command -v python3 &>/dev/null; then
    echo "[!] python3 belum terinstall."
    echo "    Ubuntu/Debian: sudo apt install python3 python3-pip"
    exit 1
fi

if ! python3 -c "import httpx, camoufox" &>/dev/null; then
    echo "[*] Menginstall dependensi..."
    python3 -m pip install -r requirements.txt
fi
if ! python3 -c "from camoufox.pkgman import installed_verstr; installed_verstr()" &>/dev/null; then
    echo "[*] Mengunduh browser Camoufox..."
    python3 -m camoufox fetch
fi

echo "[*] MODE: farm + inject + test ke 9Router"
echo "[*] Pastikan config.py sudah diisi (ROUTER_URL + ROUTER_PASSWORD)"
python3 atria_farm.py
