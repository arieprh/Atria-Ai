CONFIG = {
    # -- WAJIB EDIT ---------------------------------------------
    # Isi dengan URL & password 9Router kamu sendiri
    "ROUTER_URL": "https://9router.kamu.com",
    "ROUTER_PASSWORD": "password-kamu",
    # -- OPTIONAL -----------------------------------------------
    "DEFAULT_MODEL": "Atria-Dawn-Preview",
    "MIN_DELAY": 8,        # detik jeda minimum antar akun
    "MAX_DELAY": 16,       # detik jeda maksimum antar akun
    "MAX_RETRY": 3,        # retry per akun kalau gagal
    "BACKOFF": 30,         # detik tunggu sebelum retry (x attempt)
    "LOGIN_TIMEOUT": 75,   # detik timeout login google
    "KEY_TIMEOUT": 60,     # detik timeout pembuatan key
}
