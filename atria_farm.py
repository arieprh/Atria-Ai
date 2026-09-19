"""
Atria Farm — @arieprh
====================
Login GSuite -> buat API key -> inject ke 9router, per akun berurutan.
Anti rate-limit: sequential + jeda acak + retry backoff.

Pakai: isi akun.txt, lalu jalankan run.bat
"""
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx
from camoufox import AsyncCamoufox

from config import CONFIG

BASE = Path(__file__).parent
ATRIA = "https://api.atria-asi.ai"
AKUN_FILE = BASE / "akun.txt"
API_FILE = BASE / "api.txt"
SUCCESS_FILE = BASE / "success_akun.txt"
FAILED_FILE = BASE / "failed_akun.txt"

C = CONFIG


# --- util ---
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
    if not API_FILE.exists():
        return set()
    out = set()
    for line in API_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in (";", ":", "|", ","):
            if sep in line:
                out.add(line.split(sep, 1)[0].strip())
                break
    return out


def save_key(email, key):
    with open(API_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email};{key}\n")


def save_list(path, email, pw):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{email}:{pw}\n")


# --- google login ---
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

    # email
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

    # password + gates
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


# --- 9router ---
class Router:
    def __init__(self):
        self.c = httpx.Client(base_url=C["ROUTER_URL"], timeout=120)
        self.node = None
        self.existing = set()

    def login(self):
        r = self.c.post("/api/auth/login", json={"password": C["ROUTER_PASSWORD"]})
        if r.status_code != 200 or not r.json().get("success"):
            raise SystemExit(f"  9router login gagal: {r.text[:120]}")

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
        self.existing = {c.get("name") for c in conns if c.get("provider") == self.node["id"]}
        return len(self.existing)

    def inject(self, email, key):
        if email in self.existing:
            return "sudah ada"
        body = {
            "provider": self.node["id"],
            "apiKey": key,
            "name": email,
            "isActive": True,
            "defaultModel": C["DEFAULT_MODEL"],
        }
        r = self.c.post("/api/providers", json=body)
        if r.status_code in (200, 201):
            self.existing.add(email)
            return "ok"
        return f"fail {r.status_code}: {r.text[:100]}"

    def verify_all(self):
        r = self.c.get("/api/providers")
        conns = r.json().get("connections", [])
        mine = [c for c in conns if c.get("provider") == self.node["id"]]
        results = []
        for c in mine:
            valid = bool(c.get("testStatus") == "active")
            results.append((c.get("name"), valid, c.get("testStatus")))
        return results

    def test_one(self, cid):
        r = self.c.post(f"/api/providers/{cid}/test", timeout=120)
        try:
            return r.json().get("valid", False)
        except Exception:
            return False


# --- satu akun ---
async def process_one(email, password, router):
    for attempt in range(1, C["MAX_RETRY"] + 1):
        try:
            async with AsyncCamoufox(headless=True, humanize=True) as br:
                p = await br.new_page()
                await p.set_viewport_size({"width": 1280, "height": 900})

                ok = await google_login(p, email, password)
                if not ok:
                    log(f"  {email}: login gagal (attempt {attempt}/{C['MAX_RETRY']})")
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
                    log(f"  {email}: key gagal (attempt {attempt}/{C['MAX_RETRY']})")
                    if attempt < C["MAX_RETRY"]:
                        wt = C["BACKOFF"] * attempt
                        log(f"    tunggu {wt}s sebelum retry...")
                        await asyncio.sleep(wt)
                    continue

                save_key(email, key)
                res = router.inject(email, key)
                log(f"  {email}: key ok -> inject: {res}")
                return True
        except Exception as e:
            log(f"  {email}: error {type(e).__name__}: {str(e)[:80]}")
            if attempt < C["MAX_RETRY"]:
                await asyncio.sleep(C["BACKOFF"] * attempt)
    return False


# --- main ---
# --- preflight: cek semua syarat sebelum mulai -------------------------
def preflight():
    """Cek config + 9router + node + akun. Berhenti kalau ada yang belum siap."""
    print("\n  CEK SYARAT:")
    ok_all = True

    # 1. config.py
    url = C.get("ROUTER_URL", "").strip()
    pw = C.get("ROUTER_PASSWORD", "").strip()
    cfg_bad = (not url or "kamu" in url or not pw or "password-kamu" in pw)
    print(f"    [{'v' if not cfg_bad else 'X'}] config.py ROUTER_URL / ROUTER_PASSWORD")
    if cfg_bad:
        ok_all = False
        print("\n  [!] config.py belum diisi.")
        print("      Buka config.py, isi dua baris ini:")
        print('        "ROUTER_URL":       "https://9router.kamu.com",')
        print('        "ROUTER_PASSWORD":  "password-kamu",')
        if sys.stdin.isatty():
            try:
                a = input("\n  Buka config.py sekarang? [Y/n] ").strip().lower()
                if a in ("", "y", "ya"):
                    import webbrowser
                    webbrowser.open(str((BASE / "config.py").as_uri()))
                    print("  >> Isi config.py, save, lalu jalankan run.bat lagi.")
            except EOFError:
                pass
        return False

    # 2. koneksi + login 9router
    router = Router()
    try:
        router.login()
        print(f"    [v] 9Router terhubung: {C['ROUTER_URL']}")
    except SystemExit:
        ok_all = False
        print(f"    [X] 9Router: URL salah atau server tidak merespons")
        print(f"      Cek ROUTER_URL di config.py (sekarang: {C['ROUTER_URL']})")
        return False
    except Exception as e:
        ok_all = False
        ename = type(e).__name__
        hint = ""
        if "Connect" in ename or "Timeout" in ename:
            hint = "\n      Server tidak terjangkau. Cek apakah 9Router sedang jalan."
        elif "Unsupported" in ename or "Protocol" in ename:
            hint = "\n      URL salah format. Contoh yang benar: https://9router.kamu.com"
        print(f"    [X] 9Router tidak bisa dihubungi / password salah")
        print(f"      {ename}: {str(e)[:80]}{hint}")
        print(f"      Cek ROUTER_URL & ROUTER_PASSWORD di config.py")
        return False

    # 3. node Atria
    node = router.find_node()
    print(f"    [{'v' if node else 'X'}] Node 'atria' di 9Router")
    if not node:
        ok_all = False
        print("\n  [!] Node Atria belum dibuat di 9Router.")
        print("      Buka dashboard 9Router -> Providers -> buat node:")
        print("        Type     : anthropic-compatible")
        print("        Base URL : https://api.atria-asi.ai/v1")
        print("        Prefix   : atr   (harus mengandung kata 'atria')")
        print("\n      Setelah node jadi, jalankan run.bat lagi.")
        return False

    # 4. akun.txt ada isinya
    accounts = load_accounts()
    n_real = len([a for a in accounts if not a[0].startswith("#")])
    print(f"    [{'v' if n_real else 'X'}] akun.txt berisi {n_real} akun")
    if not n_real:
        ok_all = False
        print("\n  [!] akun.txt masih kosong (hanya komentar).")
        print("      Buka akun.txt, hapus baris '#', tulis akun GSuite:")
        print("        email1@domain.com:password1")
        print("        email2@domain.com:password2")
        return False

    print("\n  Semua syarat OK. Mulai farm...\n")
    return True


async def main():
    print("=" * 50)
    print("         ATRIA FARM  —  @arieprh")
    print("   GSuite login -> key -> inject 9router")
    print("=" * 50)

    if not preflight():
        return

    accounts = load_accounts()
    if not accounts:
        print("\n  akun.txt kosong! Format: email:password per baris")
        return

    already = done_emails()
    todo = [a for a in accounts if a[0] not in already]
    print(f"\n  {len(accounts)} akun dibaca, {len(already)} sudah ada key (skip)")
    print(f"  Akan diproses: {len(todo)}")
    if not todo:
        print("\n  Semua akun sudah punya key. Lanjut verifikasi 9router.")
    print()

    # preflight sudah pastikan login + node ada; tinggal muat koneksi
    router = Router()
    router.login()
    node = router.find_node()
    n_existing = router.load_existing()
    print(f"  9router: node '{node.get('name')}' prefix '{node.get('prefix')}'")
    print(f"  koneksi Atria sekarang: {n_existing}")
    print()

    ok_count = 0
    failed = []
    start = time.time()

    for i, (email, pw) in enumerate(todo, 1):
        log(f"  [{i}/{len(todo)}] {email}")
        if email in router.existing:
            log(f"  {email}: sudah ada di 9router, skip")
            ok_count += 1
            continue
        ok = await process_one(email, pw, router)
        if ok:
            ok_count += 1
            save_list(SUCCESS_FILE, email, pw)
        else:
            failed.append((email, pw))
            save_list(FAILED_FILE, email, pw)
        if i < len(todo):
            delay = random.randint(C["MIN_DELAY"], C["MAX_DELAY"])
            log(f"  jeda {delay}s (anti rate-limit)...")
            await asyncio.sleep(delay)

    # bersihkan akun.txt
    moved = {a[0] for a in todo}
    remaining = [a for a in accounts if a[0] not in moved]
    with open(AKUN_FILE, "w", encoding="utf-8") as f:
        for email, pw in remaining:
            f.write(f"{email}:{pw}\n")

    elapsed = time.time() - start
    print("\n" + "=" * 50)
    print("                HASIL FARM")
    print("=" * 50)
    print(f"  Diproses : {len(todo)} akun dalam {elapsed:.0f}s")
    print(f"  Sukses   : {ok_count}")
    print(f"  Gagal    : {len(failed)}")
    if failed:
        for email, _ in failed:
            print(f"    - {email}")
    print()

    # ---# verifikasi akhir ##
    print("=" * 50)
    print("            VERIFIKASI 9ROUTER")
    print("=" * 50)
    r = router.c.get("/api/providers")
    conns = r.json().get("connections", [])
    mine = [c for c in conns if c.get("provider") == node["id"]]
    print(f"  Total koneksi Atria: {len(mine)}")
    print(f"  Testing satu per satu...\n")

    active = 0
    inactive = []
    for c in sorted(mine, key=lambda v: v.get("name", "")):
        valid = router.test_one(c["id"])
        status = "AKTIF" if valid else "GAGAL"
        if valid:
            active += 1
        else:
            inactive.append(c.get("name"))
        print(f"  {c.get('name'):<28} {status}")

    print(f"\n  Aktif: {active}/{len(mine)}")
    if inactive:
        print(f"  Perlu cek: {', '.join(inactive)}")
    print("=" * 50)

    with open(BASE / "farm.log", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"processed={len(todo)} ok={ok_count} fail={len(failed)} "
                f"router_active={active}/{len(mine)}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Dihentikan manual.")
    finally:
        try:
            if sys.stdin.isatty():
                input("\n  Tekan Enter untuk keluar...")
        except EOFError:
            pass





