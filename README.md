# Atria Farm

*by @arieprh*

Farming API key **Atria-asi.ai** lewat login Google (GSuite), lalu
inject otomatis sebagai connection ke dashboard **9Router**.

```
akun GSuite → login Google → API key Atria → inject 9router → test
```

Anti rate-limit: **sequential** (1 akun pada satu waktu) + jeda acak +
retry backoff. Bukan paralel 10 window.

## Persiapan (sekali saja)

### Windows
1. Install Python 3.10+ dari https://python.org/downloads
   — centang **"Add Python to PATH"**
2. Klik 2x `run.bat`

Script otomatis install dependensi + download browser Camoufox saat
first run. Setelah itu langsung jalan.

### Linux
```bash
sudo apt install python3 python3-pip   # Ubuntu/Debian
# atau: sudo dnf install python3 python3-pip   (Fedora)

chmod +x run.sh
./run.sh
```

Script otomatis install dependensi + download browser Camoufox saat
first run.

> Kalau otomatis gagal, install manual:
> ```
> pip install -r requirements.txt
> python -m camoufox fetch
> ```

## Cara pakai

1. **Edit `config.py`** — isi (WAJIB):
   ```
   ROUTER_URL        → url 9Router kamu, contoh https://9router.kamu.com
   ROUTER_PASSWORD   → password login 9Router kamu
   ```
2. **Isi `akun.txt`** — satu akun GSuite per baris:
   ```
   email1@domain.com:password1
   email2@domain.com:password2
   ```
3. **Jalankan** `run.bat` (Windows) / `./run.sh` (Linux)
4. Tunggu sampai selesai. Laporan akhir menampilkan koneksi yang
   **AKTIF** / **GAGAL**.

## Prasyarat 9Router

Node **Atria** harus sudah ada di dashboard 9Router kamu.
Script auto-detect node dari `/api/provider-nodes` (cocokkan
`baseUrl` / `name` / `prefix` yang mengandung "atria").

Kalau belum ada, buat dulu:
- Type: `anthropic-compatible`
- Base URL: `https://api.atria-asi.ai/v1`
- Prefix: `atr` (atau apa saja yang mengandung "atria")

## Yang terjadi otomatis

- **Per akun:** login Google → bikin key → **inject langsung** ke 9Router
- **Jeda acak** 8–16 detik antar akun (hindari rate-limit Google)
- **Retry** 3x dengan backoff 30/60/90 detik kalau ada yang gagal
- **Skip** otomatis: akun yang sudah punya key (`api.txt`) atau sudah
  ada di 9Router
- **Akhir:** test semua koneksi satu per satu, laporan AKTIF/GAGAL

## File

| File | Keterangan |
|------|-----------|
| `run.bat` / `run.sh` | Launcher (auto-install dependensi) |
| `atria_farm.py` | Script utama |
| `config.py` | Konfigurasi — **EDIT INI** |
| `akun.txt` | INPUT: daftar akun GSuite |
| `api.txt` | OUTPUT: `email;key` (anti-duplikat) |
| `success_akun.txt` | Akun yang berhasil |
| `failed_akun.txt` | Akun yang gagal |
| `farm.log` | Log setiap run |

## config.py — opsi lengkap

| Key | Default | Keterangan |
|-----|---------|------------|
| `ROUTER_URL` | — | **WAJIB** url 9Router |
| `ROUTER_PASSWORD` | — | **WAJIB** password 9Router |
| `DEFAULT_MODEL` | `Atria-Dawn-Preview` | Model default koneksi |
| `MIN_DELAY` | `8` | Jeda min antar akun (detik) |
| `MAX_DELAY` | `16` | Jeda maks antar akun (detik) |
| `MAX_RETRY` | `3` | Retry per akun |
| `BACKOFF` | `30` | Tunggu sebelum retry (× attempt) |
| `LOGIN_TIMEOUT` | `75` | Timeout login Google (detik) |
| `KEY_TIMEOUT` | `60` | Timeout bikin key (detik) |

## Retry akun gagal

Pindah isi `failed_akun.txt` ke `akun.txt`, lalu jalankan lagi.
Akun yang sudah sukses tidak akan diproses ulang.

## Catatan

- Node Atria di 9Router harus sudah dibuat sebelum run.
- Browser Camoufox diunduh otomatis (~100MB) saat first run.
- Login Google dari IP server bisa memicu verifikasi tambahan;
  kalau banyak gagal, naikkan `MIN_DELAY`/`MAX_DELAY` di config.py.
- Gunakan sesuai ketentuan layanan Google & Atria-asi.ai.
