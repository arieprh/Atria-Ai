"""
Atria Farm — @arieprh
====================
Login GSuite -> buat API key -> (opsional) inject + test ke 9router,
per akun berurutan. Anti rate-limit: sequential + jeda acak + retry.

Pilih launcher:
  run.bat          farm saja, simpan key ke hasil.txt (tanpa 9Router)
  run_9router.bat  farm + inject + test langsung ke 9Router
  run_test.bat     re-test koneksi 9Router yang sudah ada (tanpa farm)

File:
  daftar_akun.txt  INPUT  : email:password per baris
  hasil.txt        OUTPUT : email;apikey (akun sukses)
  akun_gagal.txt   OUTPUT : email:password (akun gagal)
"""
import argparse
import asyncio
import json
import random
import re
import sys
import time
import webbrowser
from pathlib import Path

import httpx
from camoufox import AsyncCamoufox

from config import CONFIG

BASE = Path(__file__).parent
ATRIA = "https://api.atria-asi.ai"
AKUN_FILE = BASE / "daftar_akun.txt"
HASIL_FILE = BASE / "hasil.txt"
GAGAL_FILE = BASE / "akun_gagal.txt"
LOG_FILE = BASE / "catatan.log"

C = CONFIG


# --- util -------------------------------------------------------------
def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def load_accounts():
    if not AKUN_FILE.exists():
        return []
    out, seen = [], set()
    for line in AKUN_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in (":", ";", "|", ","):
            if sep in line:
                email, pw = line.split(sep, 1)
                email, pw = email.strip(), pw.strip()
                if email and email not in seen:
                    seen.add(email)
                    out.append((email, pw))
                break
    return out


def done_emails():
    if not HASIL_FILE.exists():
        return set()
    out = set()
    for line in HASIL_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in (";", ":", "|", ","):
            if sep in line:
                out.add(line.split(sep, 1)[0].strip())
                break
    return out


def save_hasil(email, key):
    with open(HASIL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email};{key}\n")


def save_gagal(email, pw):
    with open(GAGAL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email}:{pw}\n")


def write_log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


# --- google login -----------------------------------------------------
async def _snapshot(p):
    try:
        return await p.evaluate("""() => ({
            url: location.href,
            body: document.body.innerText.slice(0, 180),
            btns: [...document.querySelectorAll('button')]
                .map(b => (b.innerText || '').trim()).filter(Boolean).slice(0, 10)
        })""")
    except Exception:
        return {"url": "?", "body": "", "btns": []}


async def google_login(p, email, password):
    try:
        await p.goto(f"{ATRIA}/sign-in", wait_until="networkidle", timeout=45000)
    except Exception:
        return False
    await asyncio.sleep(3)

    try:
        await p.click('button:has-text("Continue with Google")', timeout=15000)
    except Exception:
        return False

    deadline = time.time() + C["LOGIN_TIMEOUT"]

    warned = False
    while time.time() < deadline:
        await asyncio.sleep(1)
        if "accounts.google.com" not in p.url:
            break
        try:
            inp = await p.query_selector('input[name="identifier"]')
            if inp and await inp.is_visible():
                await inp.fill(email)
                await asyncio.sleep(0.4)
                await p.click('button:has-text("Next")')
                await asyncio.sleep(3)
                break
            if not warned and time.time() > deadline - 25:
                s = await _snapshot(p)
                log(f"    [email macet] {s['url'][:60]} | {s['body'][:60]}")
                warned = True
        except Exception:
            pass
    else:
        return False

    warned = False
    while time.time() < deadline:
        await asyncio.sleep(1)
        if "atria-asi.ai" in p.url and "accounts.google.com" not in p.url:
            break
        try:
            inp = await p.query_selector('input[type="password"]')
            if inp and await inp.is_visible():
                await inp.fill(password)
                await asyncio.sleep(0.4)
                await p.click('button:has-text("Next")')
                await asyncio.sleep(3)
                continue
        except Exception:
            pass
        try:
            for label in ("I understand", "Saya mengerti", "Allow", "Izinkan",
                          "Continue", "Lanjutkan", "Accept", "Terima",
                          "Agree", "Setuju"):
                b = await p.query_selector(f'button:has-text("{label}")')
                if b and await b.is_visible():
                    await b.click()
                    await asyncio.sleep(3)
                    break
        except Exception:
            pass
        try:
            inp = await p.query_selector('input[name="identifier"]')
            if inp and await inp.is_visible():
                if not (await inp.input_value() or "").strip():
                    await inp.fill(email)
                    await asyncio.sleep(0.3)
                await p.click('button:has-text("Next")')
                await asyncio.sleep(3)
        except Exception:
            pass
        if not warned and time.time() > deadline - 25:
            s = await _snapshot(p)
            log(f"    [pw macet] {s['url'][:60]} | {s['body'][:60]}")
            warned = True

    if "accounts.google.com" in p.url:
        return False

    for _ in range(30):
        if "console" in p.url:
            break
        await asyncio.sleep(2)
    return "atria" in p.url


async def create_api_key(p):
    deadline = time.time() + C["KEY_TIMEOUT"]
    while time.time() < deadline:
        try:
            r = await p.evaluate("""async () => {
                const res = await fetch('/api/keys', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: 'default'})
                });
                return {status: res.status, body: await res.text()};
            }""")
        except Exception:
            await asyncio.sleep(2)
            continue
        st = r.get("status")
        if st in (200, 201):
            try:
                data = json.loads(r["body"])
            except Exception:
                await asyncio.sleep(2)
                continue
            key = data.get("key") or data.get("apiKey") or ""
            if not key:
                m = re.search(r'"?(atr_\w+)"?', r["body"])
                if m:
                    key = m.group(1)
            if key:
                return key
        elif st == 401:
            return None
        await asyncio.sleep(2)
    return None


# --- 9router ----------------------------------------------------------
class Router:
    def __init__(self):
        self.c = httpx.Client(base_url=C["ROUTER_URL"], timeout=120)
        self.node = None
        self.existing = {}

    def login(self):
        r = self.c.post("/api/auth/login", json={"password": C["ROUTER_PASSWORD"]})
        if r.status_code != 200 or not r.json().get("success"):
            raise SystemExit("login gagal")

    def find_node(self):
        r = self.c.get("/api/provider-nodes")
        for n in r.json().get("nodes", []):
            blob = " ".join(str(n.get(k, "")).lower() for k in ("baseUrl", "name", "prefix"))
            if "atria" in blob:
                self.node = n
                return n
        return None

    def load_existing(self):
        r = self.c.get("/api/providers")
        conns = r.json().get("connections", [])
        self.existing = {c.get("name"): c for c in conns
                         if c.get("provider") == self.node["id"]}
        return len(self.existing)

    def inject(self, email, key):
        body = {
            "provider": self.node["id"],
            "apiKey": key,
            "name": email,
            "isActive": True,
            "defaultModel": C["DEFAULT_MODEL"],
        }
        r = self.c.post("/api/providers", json=body)
        if r.status_code not in (200, 201):
            return None
        try:
            return (r.json().get("connection") or {}).get("id")
        except Exception:
            return None

    def test_conn(self, cid):
        try:
            r = self.c.post(f"/api/providers/{cid}/test", timeout=120)
            d = r.json()
            return bool(d.get("valid")), d
        except Exception as e:
            return False, {"error": str(e)[:80]}


# --- preflight --------------------------------------------------------
def preflight(use_router):
    """Cek syarat. use_router=False -> skip cek 9Router."""
    print("\n  CEK SYARAT:")

    if use_router:
        url = C.get("ROUTER_URL", "").strip()
        pw = C.get("ROUTER_PASSWORD", "").strip()
        cfg_bad = (not url or "kamu" in url or not pw or "password-kamu" in pw)
        print(f"    [{'v' if not cfg_bad else 'X'}] config.py ROUTER_URL / ROUTER_PASSWORD")
        if cfg_bad:
            print("\n  [!] config.py belum diisi.")
            print("      Buka config.py, isi dua baris ini:")
            print('        "ROUTER_URL":       "https://9router.kamu.com",')
            print('        "ROUTER_PASSWORD":  "password-kamu",')
            if sys.stdin.isatty():
                try:
                    a = input("\n  Buka config.py sekarang? [Y/n] ").strip().lower()
                    if a in ("", "y", "ya"):
                        webbrowser.open(str((BASE / "config.py").as_uri()))
                        print("  >> Isi config.py, save, lalu jalankan lagi.")
                except EOFError:
                    pass
            return False

        router = Router()
        try:
            router.login()
            print(f"    [v] 9Router terhubung: {C['ROUTER_URL']}")
        except SystemExit:
            print(f"    [X] 9Router: URL salah atau server tidak merespons")
            print(f"      Cek ROUTER_URL di config.py (sekarang: {C['ROUTER_URL']})")
            return False
        except Exception as e:
            ename = type(e).__name__
            hint = ""
            if "Connect" in ename or "Timeout" in ename:
                hint = "\n      Server tidak terjangkau. Cek apakah 9Router sedang jalan."
            elif "Unsupported" in ename or "Protocol" in ename:
                hint = "\n      URL salah format. Contoh: https://9router.kamu.com"
            print(f"    [X] 9Router tidak bisa dihubungi / password salah")
            print(f"      {ename}: {str(e)[:80]}{hint}")
            return False

        node = router.find_node()
        print(f"    [{'v' if node else 'X'}] Node 'atria' di 9Router")
        if not node:
            print("\n  [!] Node Atria belum dibuat di 9Router.")
            print("      Buka dashboard 9Router -> Providers -> buat node:")
            print("        Type     : anthropic-compatible")
            print("        Base URL : https://api.atria-asi.ai/v1")
            print("        Prefix   : atr   (harus mengandung kata 'atria')")
            print("\n      Setelah node jadi, jalankan lagi.")
            return False

    accounts = load_accounts()
    print(f"    [{'v' if accounts else 'X'}] daftar_akun.txt berisi {len(accounts)} akun")
    if not accounts:
        print("\n  [!] daftar_akun.txt masih kosong (hanya komentar).")
        print("      Buka daftar_akun.txt, hapus baris '#', tulis akun GSuite:")
        print("        email1@domain.com:password1")
        print("        email2@domain.com:password2")
        return False

    print("\n  Semua syarat OK. Mulai farm...\n")
    return True


# --- satu akun --------------------------------------------------------
async def process_one(email, password, router):
    """Login -> key -> (inject + test kalau router aktif).
    Return key jika sukses, None kalau gagal."""
    for attempt in range(1, C["MAX_RETRY"] + 1):
        try:
            async with AsyncCamoufox(headless=True, humanize=True) as br:
                p = await br.new_page()
                await p.set_viewport_size({"width": 1280, "height": 900})

                ok = await google_login(p, email, password)
                if not ok:
                    log(f"    login gagal (attempt {attempt}/{C['MAX_RETRY']})")
                    if attempt < C["MAX_RETRY"]:
                        wt = C["BACKOFF"] * attempt
                        log(f"    tunggu {wt}s sebelum retry...")
                        await asyncio.sleep(wt)
                    continue

                await asyncio.sleep(3)
                try:
                    await p.goto(f"{ATRIA}/console", wait_until="networkidle", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(2)

                key = await create_api_key(p)
                if not key:
                    log(f"    key gagal (attempt {attempt}/{C['MAX_RETRY']})")
                    if attempt < C["MAX_RETRY"]:
                        wt = C["BACKOFF"] * attempt
                        log(f"    tunggu {wt}s sebelum retry...")
                        await asyncio.sleep(wt)
                    continue

                if router is not None:
                    if email in router.existing:
                        log(f"    sudah ada di 9router, skip inject")
                    else:
                        cid = router.inject(email, key)
                        if not cid:
                            log(f"    inject gagal (key tetap disimpan)")
                        else:
                            valid, raw = router.test_conn(cid)
                            if valid:
                                log(f"    inject OK, test: AKTIF")
                            else:
                                err = str(raw.get("error", ""))[:60] if isinstance(raw, dict) else ""
                                log(f"    inject OK, test: GAGAL {err}")
                                await asyncio.sleep(3)
                                valid, raw = router.test_conn(cid)
                                log(f"    test ulang: {'AKTIF' if valid else 'GAGAL'}")
                return key
        except Exception as e:
            log(f"    error {type(e).__name__}: {str(e)[:80]}")
            if attempt < C["MAX_RETRY"]:
                await asyncio.sleep(C["BACKOFF"] * attempt)
    return None


# --- mode: retest saja ------------------------------------------------
def run_retest():
    """Re-test semua koneksi Atria di 9Router, GAGAL di-retry."""
    print("\n  MODE: re-test koneksi 9Router (tanpa farm)\n")
    router = Router()
    try:
        router.login()
    except Exception:
        print("  [!] 9Router tidak terhubung. Cek config.py.")
        return
    node = router.find_node()
    if not node:
        print("  [!] Node 'atria' belum dibuat di 9Router.")
        return

    n = router.load_existing()
    print(f"  Node '{node.get('name')}' — {n} koneksi Atria\n")
    print("  Testing satu per satu...\n")

    active, still_bad = 0, []
    for name, c in sorted(router.existing.items()):
        valid, _ = router.test_conn(c["id"])
        if valid:
            active += 1
            print(f"  {name:<30} AKTIF")
            continue
        print(f"  {name:<30} GAGAL -> retry...")
        time.sleep(4)
        valid, _ = router.test_conn(c["id"])
        if valid:
            active += 1
            print(f"  {name:<30} AKTIF (setelah retry)")
        else:
            still_bad.append(name)
            print(f"  {name:<30} GAGAL")

    print("\n" + "=" * 50)
    print(f"  Aktif: {active}/{n}")
    if still_bad:
        print(f"  Masih gagal: {', '.join(still_bad)}")
        print("  Key ini kemungkinan expired/banned. Farm ulang akunnya.")
    print("=" * 50)
    write_log(f"retest: active={active}/{n} bad={len(still_bad)}")


# --- main -------------------------------------------------------------
async def main(use_router=True, test_only=False):
    print("=" * 50)
    print("         ATRIA FARM  —  @arieprh")
    if test_only:
        print("   Re-test koneksi 9Router")
    elif use_router:
        print("   GSuite login -> key -> inject + test 9Router")
    else:
        print("   GSuite login -> key (simpan ke hasil.txt)")
    print("=" * 50)

    if test_only:
        run_retest()
        return

    if not preflight(use_router):
        return

    accounts = load_accounts()
    already = done_emails()
    todo = [a for a in accounts if a[0] not in already]
    print(f"  {len(accounts)} akun dibaca, {len(already)} sudah ada key (skip)")
    print(f"  Akan diproses: {len(todo)}\n")

    router = None
    if use_router:
        router = Router()
        router.login()
        node = router.find_node()
        n_existing = router.load_existing()
        print(f"  9router: node '{node.get('name')}' prefix '{node.get('prefix')}'")
        print(f"  koneksi Atria sekarang: {n_existing}\n")

    ok_count = 0
    failed = []
    start = time.time()

    for i, (email, pw) in enumerate(todo, 1):
        log(f"  [{i}/{len(todo)}] {email}")
        key = await process_one(email, pw, router)
        if key:
            ok_count += 1
            save_hasil(email, key)
        else:
            failed.append((email, pw))
            save_gagal(email, pw)
        if i < len(todo):
            delay = random.randint(C["MIN_DELAY"], C["MAX_DELAY"])
            log(f"  jeda {delay}s (anti rate-limit)...\n")
            await asyncio.sleep(delay)

    moved = {a[0] for a in todo}
    remaining = [a for a in accounts if a[0] not in moved]
    with open(AKUN_FILE, "w", encoding="utf-8") as f:
        for email, pw in remaining:
            f.write(f"{email}:{pw}\n")

    elapsed = time.time() - start
    print("\n" + "=" * 50)
    print("                   HASIL FARM")
    print("=" * 50)
    print(f"  Diproses : {len(todo)} akun dalam {elapsed:.0f}s")
    print(f"  Sukses   : {ok_count}")
    print(f"  Gagal    : {len(failed)}")
    if failed:
        for email, _ in failed:
            print(f"    - {email}")
    print(f"\n  Key tersimpan   : {HASIL_FILE.name}")
    if failed:
        print(f"  Akun gagal      : {GAGAL_FILE.name}")
    print("=" * 50)

    write_log(f"mode={'router' if use_router else 'farm'} "
              f"processed={len(todo)} ok={ok_count} fail={len(failed)} "
              f"time={elapsed:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Atria Farm — @arieprh")
    ap.add_argument("--no-router", action="store_true",
                    help="farm saja, tanpa inject 9Router")
    ap.add_argument("--test-only", action="store_true",
                    help="re-test koneksi 9Router yang sudah ada")
    args = ap.parse_args()
    try:
        asyncio.run(main(use_router=not args.no_router, test_only=args.test_only))
    except KeyboardInterrupt:
        print("\n  Dihentikan manual.")
    finally:
        try:
            if sys.stdin.isatty():
                input("\n  Tekan Enter untuk keluar...")
        except EOFError:
            pass
