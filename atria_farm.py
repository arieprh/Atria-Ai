"""
Atria Farm — @arieprh
====================
Login GSuite -> buat API key via HTTP -> validasi /v1/models ->
(opsional) inject + test ke 9Router. Per akun berurutan.

Pilih launcher:
  run.bat          farm saja, simpan key ke hasil.txt (tanpa 9Router)
  run_9router.bat  farm + inject + test langsung ke 9Router
  run_test.bat     re-test koneksi 9Router yang sudah ada (tanpa farm)

File:
  daftar_akun.txt  INPUT  : email:password per baris
  hasil.txt        OUTPUT : email;apikey;quota (akun sukses)
  akun_gagal.txt   OUTPUT : email:alasan (akun gagal)
"""
import argparse
import asyncio
import json
import random
import re
import sys
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from camoufox import AsyncCamoufox

from config import CONFIG

BASE_DIR = Path(__file__).parent
ATRIA = "https://api.atria-asi.ai"
MODELS = ATRIA + "/v1/models"
AKUN_FILE = BASE_DIR / "daftar_akun.txt"
HASIL_FILE = BASE_DIR / "hasil.txt"
GAGAL_FILE = BASE_DIR / "akun_gagal.txt"
LOG_FILE = BASE_DIR / "catatan.log"
SYNC_FILE = BASE_DIR / ".router_sync.json"

C = CONFIG


# --- util -------------------------------------------------------------
def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def write_log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


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


def load_existing():
    """Baca hasil.txt -> {email: key}."""
    if not HASIL_FILE.exists():
        return {}
    out = {}
    for line in HASIL_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[;|,]", line)
        if len(parts) >= 2 and parts[0] and parts[1]:
            out[parts[0].strip()] = parts[1].strip()
    return out


def save_hasil(email, key, quota=0):
    with open(HASIL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email};{key};{quota}\n")


def save_gagal(email, reason):
    with open(GAGAL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email}:{reason}\n")


def load_sync():
    """Catatan key yang sudah dipush ke 9router: {email: key}."""
    if not SYNC_FILE.exists():
        return {}
    try:
        return json.loads(SYNC_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sync(sync):
    SYNC_FILE.write_text(json.dumps(sync, indent=0), encoding="utf-8")


# --- validasi key via HTTP (murni, tanpa browser) ---------------------
def key_is_valid(key):
    try:
        req = urllib.request.Request(MODELS, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def purge_dead_keys():
    """Cek semua key di hasil.txt, buang yang sudah invalid."""
    existing = load_existing()
    if not existing:
        return 0, 0
    with ThreadPoolExecutor(max_workers=C["PURGE_WORKERS"]) as ex:
        futs = {ex.submit(key_is_valid, k): e for e, k in existing.items()}
        valid = set()
        for fut in as_completed(futs):
            try:
                if fut.result():
                    valid.add(futs[fut])
            except Exception:
                pass
    dead = set(existing) - valid
    if dead:
        kept = []
        for line in HASIL_FILE.read_text(encoding="utf-8-sig").splitlines():
            parts = re.split(r"[;|,]", line.strip())
            if parts and parts[0].strip() not in dead:
                kept.append(line)
        with open(HASIL_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
    return len(valid), len(dead)


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


# --- key via HTTP (lewat context browser, cookie sudah ada) -----------
async def read_quota_rsc(p):
    """Baca token_quota / token_used dari RSC payload /console."""
    try:
        r = await p.request.get(ATRIA + "/console?_rsc=farm", timeout=15000)
        txt = await r.text()
        mq = re.search(r'token_quota[\\"]*:\s*[\\"]*(\d+)', txt)
        mu = re.search(r'token_used[\\"]*:\s*[\\"]*(\d+)', txt)
        if mq:
            q = int(mq.group(1))
            used = int(mu.group(1)) if mu else 0
            return max(0, q - used)
    except Exception:
        pass
    return 0


async def create_key_http(p):
    """POST /api/keys via HTTP request context. Return key."""
    r = await p.request.post(ATRIA + "/api/keys",
                             data={"name": "atria"},
                             timeout=C["KEY_TIMEOUT"] * 1000)
    if r.status not in (200, 201):
        raise RuntimeError(f"create-key-http-{r.status}")
    try:
        j = json.loads(await r.text())
    except Exception:
        raise RuntimeError("create-key-bad-json")
    if isinstance(j, dict) and j.get("key"):
        return j["key"]
    if isinstance(j, list):
        for it in j:
            if isinstance(it, dict) and it.get("key"):
                return it["key"]
    raise RuntimeError("create-key-no-key-field")


async def validate_key_async(key):
    """Validasi via GET /v1/models. Loop sebanyak VALIDATE_RETRY."""
    for _ in range(C["VALIDATE_RETRY"]):
        if key_is_valid(key):
            return True
        await asyncio.sleep(1.0)
    return False


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

    def delete_conn(self, cid):
        try:
            return self.c.delete(f"/api/providers/{cid}").status_code in (200, 204)
        except Exception:
            return False

    def replace_key(self, email, key):
        """Sync: hapus connection lama, buat ulang pakai key baru.
        Return connection id baru, atau None."""
        old = self.existing.get(email)
        if old:
            self.delete_conn(old["id"])
        cid = self.inject(email, key)
        if cid:
            self.existing[email] = {"id": cid, "name": email}
        return cid

    def test_conn(self, cid):
        try:
            r = self.c.post(f"/api/providers/{cid}/test", timeout=120)
            d = r.json()
            return bool(d.get("valid")), d
        except Exception as e:
            return False, {"error": str(e)[:80]}


# --- preflight --------------------------------------------------------
def preflight(use_router):
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
                        webbrowser.open(str((BASE_DIR / "config.py").as_uri()))
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
async def process_one(email, password, router, sync):
    """Login -> key via HTTP -> validasi -> (sync + test kalau router).
    Return (key, quota) jika sukses, (None, reason) kalau gagal."""
    last_err = "unknown"
    for attempt in range(1, C["MAX_RETRY"] + 1):
        try:
            async with AsyncCamoufox(headless=True, humanize=True) as br:
                ctx = await br.new_context()
                p = await ctx.new_page()
                await p.set_viewport_size({"width": 1280, "height": 800})

                ok = await google_login(p, email, password)
                if not ok:
                    last_err = "login-gagal"
                    if attempt < C["MAX_RETRY"]:
                        log(f"    login gagal (attempt {attempt}/{C['MAX_RETRY']})")
                        await asyncio.sleep(C["RETRY_DELAY"])
                    continue

                quota = await read_quota_rsc(p)
                key = await create_key_http(p)
                if not key:
                    last_err = "key-kosong"
                    continue

                if not await validate_key_async(key):
                    last_err = "key-invalid-401"
                    log(f"    key dibuat tapi tidak valid")
                    continue

                if router is not None:
                    pushed = sync.get(email)
                    if pushed == key:
                        log(f"    9router sudah pakai key ini, skip")
                    else:
                        if email in router.existing:
                            log(f"    update koneksi 9router (hapus + buat ulang)...")
                            cid = router.replace_key(email, key)
                        else:
                            cid = router.inject(email, key)
                        if not cid:
                            log(f"    inject/update gagal (key tetap disimpan)")
                        else:
                            if pushed:
                                log(f"    key lama diganti key baru (sync)")
                            valid, raw = router.test_conn(cid)
                            if valid:
                                log(f"    test: AKTIF")
                            else:
                                await asyncio.sleep(3)
                                valid, raw = router.test_conn(cid)
                                log(f"    test: {'AKTIF' if valid else 'GAGAL'}")
                            sync[email] = key
                            save_sync(sync)

                return key, quota
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:60]}"
            if attempt < C["MAX_RETRY"]:
                await asyncio.sleep(C["RETRY_DELAY"])
    return None, last_err


# --- sync koneksi lama dgn key terbaru --------------------------------
def sync_connections(router, sync):
    """Bandingkan hasil.txt vs 9router, update yang key-nya beda."""
    pairs = load_existing()
    if not pairs:
        return 0, 0
    upd, skip = 0, 0
    print(f"\n  Sync {len(pairs)} key dari {HASIL_FILE.name} ke 9router...")
    for email, key in pairs.items():
        conn = router.existing.get(email)
        if conn is None:
            skip += 1
            continue
        if sync.get(email) == key:
            skip += 1
            continue
        cid = router.replace_key(email, key)
        if cid:
            valid, _ = router.test_conn(cid)
            if not valid:
                time.sleep(3)
                valid, _ = router.test_conn(cid)
            sync[email] = key
            save_sync(sync)
            upd += 1
            print(f"    {email:<30} {'AKTIF' if valid else 'GAGAL'} (key diupdate)")
        else:
            print(f"    {email:<30} gagal update")
    print(f"  Sync selesai: {upd} diupdate, {skip} sudah sama\n")
    return upd, skip


# --- mode: retest saja ------------------------------------------------
def run_retest():
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

    # purge key mati dulu
    existing = load_existing()
    if existing:
        log(f"  Cek {len(existing)} key lama (validasi /v1/models)...")
        valid_n, dead_n = purge_dead_keys()
        if dead_n:
            log(f"  {dead_n} key invalid dibuang, {valid_n} masih aktif")
        else:
            log(f"  Semua {valid_n} key masih valid")

    accounts = load_accounts()
    already = set(load_existing())
    todo = [a for a in accounts if a[0] not in already]
    print(f"\n  {len(accounts)} akun dibaca, {len(already)} sudah ada key (skip)")
    print(f"  Akan diproses: {len(todo)}\n")

    router = None
    sync = {}
    if use_router:
        router = Router()
        router.login()
        node = router.find_node()
        n_existing = router.load_existing()
        sync = load_sync()
        print(f"  9router: node '{node.get('name')}' prefix '{node.get('prefix')}'")
        print(f"  koneksi Atria sekarang: {n_existing}")
        sync_connections(router, sync)

    if not todo:
        print("  Semua akun sudah punya key valid. Selesai.")
        return

    ok_count = 0
    failed = []
    total_tokens = 0
    start = time.time()

    for i, (email, pw) in enumerate(todo, 1):
        log(f"  [{i}/{len(todo)}] {email}")
        key, info = await process_one(email, pw, router, sync)
        if key:
            ok_count += 1
            quota = info if isinstance(info, int) else 0
            total_tokens += quota
            save_hasil(email, key, quota)
            log(f"    OK  quota={quota:,}")
        else:
            failed.append((email, info))
            save_gagal(email, str(info))
            log(f"    GAGAL  {info}")
        if i < len(todo):
            delay = random.uniform(C["MIN_DELAY"], C["MAX_DELAY"])
            await asyncio.sleep(delay)

    # konsumsi daftar_akun.txt
    moved = {a[0] for a in todo}
    remaining = [a for a in accounts if a[0] not in moved]
    with open(AKUN_FILE, "w", encoding="utf-8") as f:
        for email, pw in remaining:
            f.write(f"{email}:{pw}\n")

    elapsed = time.time() - start
    avg = elapsed / len(todo) if todo else 0
    print("\n" + "=" * 50)
    print("                   HASIL FARM")
    print("=" * 50)
    print(f"  Diproses     : {len(todo)} akun dalam {elapsed:.0f}s ({avg:.1f}s/akun)")
    print(f"  Sukses       : {ok_count}")
    print(f"  Gagal        : {len(failed)}")
    print(f"  Total token  : {total_tokens:,}")
    if failed:
        for email, reason in failed:
            print(f"    - {email} ({reason})")
    print(f"\n  Key tersimpan : {HASIL_FILE.name}")
    if failed:
        print(f"  Akun gagal    : {GAGAL_FILE.name}")
    print("=" * 50)

    write_log(f"mode={'router' if use_router else 'farm'} "
              f"processed={len(todo)} ok={ok_count} fail={len(failed)} "
              f"tokens={total_tokens} time={elapsed:.0f}s")


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
