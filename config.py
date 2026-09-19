CONFIG = {
    # -- WAJIB EDIT (mode 9Router saja) --------------------------
    # Tidak perlu diisi kalau pakai run.bat (mode farm saja)
    "ROUTER_URL": "https://9router.kamu.com",
    "ROUTER_PASSWORD": "password-kamu",
    # -- KECEPATAN ------------------------------------------------
    "MIN_DELAY": 2.5,      # detik jeda minimum antar akun
    "MAX_DELAY": 5.0,      # detik jeda maksimum antar akun
    "MAX_RETRY": 3,        # retry per akun kalau gagal
    "RETRY_DELAY": 2,      # detik tunggu sebelum retry login
    # -- TIMEOUT --------------------------------------------------
    "LOGIN_TIMEOUT": 75,   # detik timeout login google
    "KEY_TIMEOUT": 20,     # detik timeout bikin key (HTTP)
    "VALIDATE_RETRY": 5,   # retry validasi key
    # -- LAINNYA --------------------------------------------------
    "DEFAULT_MODEL": "Atria-Dawn-Preview",
    "PURGE_WORKERS": 8,    # paralel cek key lama saat purge
}
