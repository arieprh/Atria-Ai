#!/usr/bin/env bash
# Atria Farm — re-test koneksi 9Router
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if ! command -v python3 &>/dev/null; then
    echo "[!] python3 belum terinstall."
    exit 1
fi
if ! python3 -c "import httpx" &>/dev/null; then
    echo "[*] Menginstall dependensi..."
    python3 -m pip install -r requirements.txt
fi

echo "[*] MODE: re-test koneksi 9Router"
python3 atria_farm.py --test-only
