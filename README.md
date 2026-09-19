# Atria Farm

*by @arieprh*

Farming API key **Atria-asi.ai** lewat login Google (GSuite), lalu
inject otomatis sebagai connection ke dashboard **9Router**.

```
akun GSuite → login Google → API key Atria → inject 9router → test
```

Anti rate-limit: **sequential** (1 akun pada satu waktu) + jeda acak +
retry backoff. Bukan paralel 10 window.

## Pilih launcher

| Launcher | Fungsi |
|----------|--------|
| `run.bat` / `run.sh` | **Farm saja** — login + key, simpan ke `hasil.txt`. Tidak butuh 9Router. |
| `run_9router.bat` / `run_9router.sh` | **Farm + inject + test** — setiap key langsung dipush ke 9Router dan ditest. |
| `run_test.bat` / `run_test.sh` | **Re-test saja** — test ulang koneksi 9Router yang sudah ada, GAGAL di-retry otomatis. Tanpa farm. |

> Tidak pakai 9Router? Klik `run.bat` saja, `config.py` tidak perlu diisi.

## Persiapan (sekali saja)

### Windows
1. Install Python 3.10+ dari https://python.org/downloads
   — centang **"Add Python to PATH"**
2. Klik 2x salah satu launcher (lihat tabel di atas)

Script otomatis install dependensi + download browser Camoufox saat
first run. Setelah itu langsung jalan.

### Linux
```bash
sudo apt install python3 python3-pip   # Ubuntu/Debian
# atau: sudo dnf install python3 python3-pip   (Fedora)

chmod +x run.sh   # (atau run_9router.sh / run_test.sh)
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

### Mode farm saja (tidak pakai 9Router)
1. Isi `daftar_akun.txt` — satu akun GSuite per baris:
   ```
   email1@domain.com:password1
   email2@domain.com:password2
   ```
2. Klik `run.bat`
3. Key tersimpan di `hasil.txt` dengan format `email;apikey`

### Mode farm + 9Router
1. **Edit `config.py`** — isi (WAJIB):
   ```
   ROUTER_URL        → url 9Router kamu, contoh https://9router.kamu.com
   ROUTER_PASSWORD   → password login 9Router kamu
   ```
2. Isi `daftar_akun.txt` (sama seperti di atas)
3. Klik `run_9router.bat`
4. Setiap akun: login → key → **inject + test langsung** ke 9Router

### Mode re-test 9Router
1. Pastikan `config.py` sudah diisi
2. Klik `run_test.bat`
3. Semua koneksi Atria di-test; yang GAGAL di-retry otomatis sekali
   lagi. Kalau masih GAGAL → key expired/banned, farm ulang akunnya.

## Prasyarat 9Router

Node **Atria** harus sudah ada di dashboard 9Router kamu.
Script auto-detect node dari `/api/provider-nodes` (cocokkan
`baseUrl` / `name` / `prefix` yang mengandung "atria").

Kalau belum ada, buat dulu:
- Type: `anthropic-compatible`
- Base URL: `https://api.atria-asi.ai/v1`
- Prefix: `atr` (atau apa saja yang mengandung "atria")

## Yang terjadi otomatis

- **Per akun:** login Google → bikin key → (mode 9Router) **inject +
  test langsung** ke 9Router
- **Jeda acak** 8–16 detik antar akun (hindari rate-limit Google)
- **Retry** 3x dengan backoff 30/60/90 detik kalau ada yang gagal
- **Skip** otomatis: akun yang sudah ada key (`hasil.txt`) atau sudah
  ada di 9Router
- **Test GAGAL?** Jalan `run_test.bat` untuk re-test. Kalau masih
  GAGAL, key expired — farm ulang akunnya.

## File

| File | Keterangan |
|------|-----------|
| `run*.bat` / `run*.sh` | Launcher (auto-install dependensi) |
| `atria_farm.py` | Script utama |
| `config.py` | Konfigurasi — **EDIT INI** (mode 9Router saja) |
| `daftar_akun.txt` | INPUT: daftar akun GSuite |
| `hasil.txt` | OUTPUT: `email;apikey` (akun sukses) |
| `akun_gagal.txt` | OUTPUT: `email:password` (akun gagal) |
| `catatan.log` | Log setiap run |

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

Pindah isi `akun_gagal.txt` ke `daftar_akun.txt`, lalu jalankan lagi.
Akun yang sudah sukses tidak akan diproses ulang.

## Catatan

- Node Atria di 9Router harus sudah dibuat sebelum run.
- Browser Camoufox diunduh otomatis (~100MB) saat first run.
- Login Google dari IP server bisa memicu verifikasi tambahan;
  kalau banyak gagal, naikkan `MIN_DELAY`/`MAX_DELAY` di config.py.
- Gunakan sesuai ketentuan layanan Google & Atria-asi.ai.
