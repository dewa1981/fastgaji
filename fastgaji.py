#!/usr/bin/env python3
"""
FASTGAJI — Aplikasi Gaji Karyawan (Windows EXE)
Fitur:
- Daftar karyawan + detail (bank, eWallet, Pintu, ETH/BNB)
- Hitung gaji IDR -> USDT (kurs Binance P2P + 2%)
- Bayar gaji via USDT BSC (web3)
- Private key LOKAL terenkripsi (AES + password)
- Histori pembayaran
"""
import os, sys, json, base64, hashlib, threading, queue, sqlite3
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

# ---------- crypto libs (di-load dinamis biar app tetap bisa buka tanpa key) ----------
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

try:
    from web3 import Web3
    HAVE_WEB3 = True
except ImportError:
    HAVE_WEB3 = False

APP_DIR = os.path.dirname(os.path.abspath(__file__)) if getattr(sys, 'frozen', False) else os.getcwd()
# kalau frozen (EXE), data dir = folder EXE (biar bisa nulis DB), DB bundled = _MEIPASS
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.dirname(sys.executable)   # folder EXE (bisa nulis)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', DATA_DIR)  # file bundled (read-only)
else:
    DATA_DIR = os.getcwd()
    BUNDLE_DIR = os.getcwd()
DATA_FILE = os.path.join(DATA_DIR, "fastgaji_data.json")  # legacy (JSON)
DB_FILE = os.path.join(DATA_DIR, "fastgaji.db")           # SQLite (utama, di folder EXE)
KEY_FILE = os.path.join(DATA_DIR, "fastgaji_key.enc")
_BUNDLED_DB = os.path.join(BUNDLE_DIR, "fastgaji.db")     # DB bawaan dari EXE

# ================= SQLITE DATABASE =================
def _db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # pertama kali: copy DB bawaan (dari bundle EXE) ke folder EXE kalau belum ada
    if not os.path.exists(DB_FILE) and os.path.exists(_BUNDLED_DB) and _BUNDLED_DB != DB_FILE:
        try:
            import shutil
            shutil.copy2(_BUNDLED_DB, DB_FILE)
        except Exception:
            pass
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS karyawan (
        kode INTEGER PRIMARY KEY,
        nama TEXT NOT NULL,
        gaji INTEGER DEFAULT 0,
        gaji_x_fee INTEGER DEFAULT 0,
        eth TEXT DEFAULT '',
        pintu TEXT DEFAULT '',
        jatuh_tempo TEXT DEFAULT '',
        komisi TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        bank TEXT DEFAULT '',
        norek TEXT DEFAULT '',
        namarek TEXT DEFAULT '',
        email TEXT DEFAULT '',
        notelp TEXT DEFAULT '',
        status INTEGER DEFAULT 0,
        ewallet TEXT DEFAULT '',
        btc TEXT DEFAULT '',
        ovo TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS histori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kode_karyawan INTEGER,
        nama TEXT,
        gaji_idr INTEGER,
        usdt REAL,
        tanggal TEXT,
        txid TEXT,
        waktu TEXT,
        notes TEXT
    )""")
    conn.commit()
    conn.close()

def db_load_all():
    """Baca semua karyawan + histori dari SQLite."""
    init_db()
    conn = _db()
    rows = conn.execute("SELECT * FROM karyawan ORDER BY kode").fetchall()
    karyawan = []
    for r in rows:
        k = dict(r)
        karyawan.append(k)
    hist = conn.execute("SELECT kode_karyawan, nama, gaji_idr, usdt, tanggal, txid, waktu FROM histori ORDER BY id DESC LIMIT 500").fetchall()
    histori = [dict(h) for h in hist]
    conn.close()
    return karyawan, histori

def db_upsert_karyawan(k):
    """Insert atau update karyawan by kode (PRIMARY KEY)."""
    conn = _db()
    conn.execute("""INSERT INTO karyawan (kode, nama, gaji, gaji_x_fee, eth, pintu, jatuh_tempo, komisi, notes,
                    bank, norek, namarek, email, notelp, status, ewallet, btc, ovo)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(kode) DO UPDATE SET
                        nama=excluded.nama, gaji=excluded.gaji, gaji_x_fee=excluded.gaji_x_fee,
                        eth=excluded.eth, pintu=excluded.pintu, jatuh_tempo=excluded.jatuh_tempo,
                        komisi=excluded.komisi, notes=excluded.notes, bank=excluded.bank, norek=excluded.norek,
                        namarek=excluded.namarek, email=excluded.email, notelp=excluded.notelp,
                        status=excluded.status, ewallet=excluded.ewallet, btc=excluded.btc, ovo=excluded.ovo""",
                 (k.get("kode", 0), k.get("nama",""), k.get("gaji",0), k.get("gaji_x_fee",0),
                  k.get("eth",""), k.get("pintu",""), k.get("jatuh_tempo",""),
                  k.get("komisi",""), k.get("notes",""), k.get("bank",""), k.get("norek",""),
                  k.get("namarek",""), k.get("email",""), k.get("notelp",""), k.get("status",0),
                  k.get("ewallet",""), k.get("btc",""), k.get("ovo","")))
    conn.commit()
    conn.close()

def db_delete_karyawan(kode):
    conn = _db()
    conn.execute("DELETE FROM karyawan WHERE kode=?", (kode,))
    conn.commit()
    conn.close()

def db_add_histori(h):
    conn = _db()
    conn.execute("INSERT INTO histori (kode_karyawan, nama, gaji_idr, usdt, tanggal, txid, waktu) VALUES (?,?,?,?,?,?,?)",
                 (h.get("kode_karyawan",0), h.get("nama",""), h.get("gaji_idr",0), h.get("usdt",0),
                  h.get("tanggal",""), h.get("txid",""), h.get("waktu","")))
    conn.commit()
    conn.close()

def db_histori_by_karyawan(kode, limit=200):
    """Histori gaji per karyawan (dari DB asli)."""
    init_db()
    conn = _db()
    rows = conn.execute("SELECT gaji_idr, tanggal, notes FROM histori WHERE kode_karyawan=? ORDER BY id DESC LIMIT ?",
                        (kode, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_next_kode():
    conn = _db()
    r = conn.execute("SELECT MAX(kode) as m FROM karyawan").fetchone()
    conn.close()
    return (r["m"] or 0) + 1

BSC_RPC = "https://bnb-mainnet.g.alchemy.com/v2/alch_KgymfWpXkADRUuQzAtwcD"
USDT_CA = "0x55d398326f99059fF775485246999027B3197955"
FEE_RATE = 0.002  # fee 0.2% dari kurs P2P
USDT_ABI = [
    {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]

# ================= FORMAT ANGKA (grouping ribuan) =================
def _fmt_idr(n):
    """1234567 -> 1.234.567 (format Indonesia)"""
    try:
        n = int(n)
        s = f"{n:,}".replace(",", ".")
        return s
    except (ValueError, TypeError):
        return str(n)

def _parse_idr(s):
    """1.234.567 -> 1234567"""
    if not s:
        return 0
    try:
        return int(str(s).replace(".", "").replace(",", "").strip())
    except ValueError:
        return 0

def _parse_jatuh_tempo(s):
    """'11-Aug-25' -> (datetime, hari_selisih). Return None kalau gak valid."""
    if not s:
        return None
    try:
        parts = str(s).strip().split("-")
        if len(parts) != 3 or not parts[0].isdigit():
            return None
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"Mei":5,"Jun":6,"Jul":7,"Agu":8,"Sep":9,"Okt":10,"Nov":11,"Des":12,
                  "jan":1,"feb":2,"mar":3,"apr":4,"mei":5,"jun":6,"jul":7,"agu":8,"sep":9,"okt":10,"nov":11,"des":12}
        m = months.get(parts[1])
        if not m:
            return None
        y = int(parts[2])
        if y < 100:
            y += 2000
        d = datetime(y, m, int(parts[0]))
        today = datetime.now()
        # pakai tanggal polos (tanpa jam) biar selisih hari akurat
        t0 = datetime(today.year, today.month, today.day)
        return d, (d - t0).days
    except Exception:
        return None

def _grouping_entry(parent, textvariable):
    """Entry dengan auto-grouping ribuan saat mengetik."""
    from tkinter import Entry
    e = Entry(parent, textvariable=textvariable, bg="#161b22", fg="#e6edf3",
              insertbackground="#e6edf3", relief="flat")
    return e

def _apply_grouping(var):
    """Format ulang angka di StringVar jadi grouping ribuan."""
    raw = "".join(ch for ch in var.get() if ch.isdigit())
    if raw:
        var.set(_fmt_idr(raw))

# ================= DATA DEFAULT (dari DB karyawan) =================
DEFAULT_KARYAWAN = []  # data asli dari DB Access (fastgaji.db)

# ================= CRYPTO KEY (AES-GCM via hashlib fallback) =================
def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000, dklen=32)

def encrypt_key(private_key: str, password: str) -> bytes:
    salt = os.urandom(16)
    if HAVE_CRYPTO:
        key = _derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(private_key.encode())
        return salt + cipher.nonce + tag + ct
    else:
        # fallback sederhana (XOR + salt) — tetap lebih baik dari plaintext
        key = _derive_key(password, salt)
        data = private_key.encode()
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return salt + xored

def decrypt_key(blob: bytes, password: str) -> str:
    salt = blob[:16]
    if HAVE_CRYPTO:
        key = _derive_key(password, salt)
        nonce, tag, ct = blob[16:28], blob[28:44], blob[44:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode()
    else:
        key = _derive_key(password, salt)
        xored = blob[16:]
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(xored)).decode()

def save_key(private_key: str, password: str):
    blob = encrypt_key(private_key, password)
    with open(KEY_FILE, "wb") as f:
        f.write(blob)

def load_key(password: str) -> str:
    with open(KEY_FILE, "rb") as f:
        return decrypt_key(f.read(), password)

# ================= DATA KARYAWAN =================
def load_data():
    """Baca dari SQLite; kalau kosong, seed dari data default."""
    karyawan, histori = db_load_all()
    if not karyawan:
        # seed pertama kali — kode 0 di-assign otomatis unik
        next_k = 1
        used = set()
        for k in DEFAULT_KARYAWAN:
            kd = k.get("kode", 0)
            if not kd or kd in used:
                while next_k in used or next_k == 0:
                    next_k += 1
                kd = next_k
            k["kode"] = kd
            used.add(kd)
            db_upsert_karyawan(k)
        karyawan, histori = db_load_all()
    return {"karyawan": karyawan, "histori": histori}

def save_data(data):
    """Simpan semua karyawan + histori ke SQLite."""
    init_db()
    # upsert semua karyawan (by kode)
    seen = set()
    for k in data["karyawan"]:
        kode = k.get("kode", 0)
        if not kode:
            kode = db_next_kode()
            k["kode"] = kode
        db_upsert_karyawan(k)
        seen.add(kode)
    # hapus karyawan yang gak ada lagi di list
    conn = _db()
    conn.execute("DELETE FROM karyawan WHERE kode NOT IN (%s)" % ",".join("?" * len(seen)) if seen else "DELETE FROM karyawan")
    conn.commit()
    conn.close()
    # histori
    conn = _db()
    conn.execute("DELETE FROM histori")
    conn.commit()
    conn.close()
    for h in data["histori"]:
        db_add_histori(h)

# ================= KURS BINANCE P2P =================
def get_p2p_rate():
    """Ambil kurs USDT/IDR dari Binance P2P (rata-rata penjual terbaik)."""
    import urllib.request
    payload = json.dumps({"page": 1, "rows": 5, "payTypes": [], "asset": "USDT", "tradeType": "BUY", "fiat": "IDR"}).encode()
    req = urllib.request.Request(
        "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
        data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    advs = d.get("data", [])
    if not advs:
        return None
    prices = [float(a["adv"]["price"]) for a in advs[:3]]
    return sum(prices) / len(prices)

# ================= UI =================
class FastGajiApp:
    def __init__(self, root):
        self.root = root
        root.title("FASTGAJI — Gaji Karyawan (by Chokdi 🐷)")
        root.geometry("1100x680")
        root.configure(bg="#0d1117")

        self.data = load_data()
        self.karyawan = self.data["karyawan"]
        self.histori = self.data.get("histori", [])
        self.kurs = None
        self.private_key = None

        # style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#161b22", fieldbackground="#161b22", foreground="#e6edf3", rowheight=24)
        style.configure("Treeview.Heading", background="#0d1117", foreground="#58a6ff", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#1f6feb")])

        self._build_ui()
        self._refresh_kurs_async()

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#0d1117")
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="💰 FASTGAJI", font=("Segoe UI", 18, "bold"), bg="#0d1117", fg="#e6edf3").pack(side="left")
        tk.Label(header, text="Kurs: ambil otomatis dari Binance P2P +2%", font=("Segoe UI", 9), bg="#0d1117", fg="#8b949e").pack(side="left", padx=10)

        # Main paned
        main = tk.PanedWindow(self.root, orient="horizontal", bg="#0d1117", sashwidth=4)
        main.pack(fill="both", expand=True, padx=12, pady=6)

        # LEFT: daftar karyawan
        left = tk.Frame(main, bg="#0d1117")
        main.add(left, width=420)
        tk.Label(left, text="📋 Daftar Karyawan", font=("Segoe UI", 11, "bold"), bg="#0d1117", fg="#e6edf3").pack(anchor="w")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self._refresh_list())
        tk.Entry(left, textvariable=self.filter_var, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat").pack(fill="x", pady=4)

        self.tree = ttk.Treeview(left, columns=("nama", "gaji", "usd"), show="headings", selectmode="browse")
        self.tree.heading("nama", text="Nama Karyawan")
        self.tree.heading("gaji", text="Gaji (IDR)")
        self.tree.heading("usd", text="USDT")
        self.tree.column("nama", width=200)
        self.tree.column("gaji", width=110, anchor="e")
        self.tree.column("usd", width=100, anchor="e")
        # tag: merah = jatuh tempo dekat/telat, kuning = jatuh tempo hari ini
        self.tree.tag_configure("red", background="#7d1a1a", foreground="#ffd7d7")
        self.tree.tag_configure("soon", background="#5a3a00", foreground="#ffe8b3")
        self.tree.tag_configure("today", background="#7d5a00", foreground="#fff2cc")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Total label
        self.total_label = tk.Label(left, text="", font=("Segoe UI", 10, "bold"), bg="#0d1117", fg="#f85149")
        self.total_label.pack(anchor="w", pady=4)

        # Tombol tambah/edit
        btns = tk.Frame(left, bg="#0d1117")
        btns.pack(fill="x", pady=(0, 4))
        tk.Button(btns, text="➕ Tambah", command=self._tambah_karyawan, bg="#238636", fg="white", relief="flat", padx=10).pack(side="left")
        tk.Button(btns, text="✏️ Edit Detail", command=self._edit_karyawan, bg="#1f6feb", fg="white", relief="flat", padx=10).pack(side="left", padx=6)
        tk.Button(btns, text="🗑️ Hapus", command=self._hapus_karyawan, bg="#f85149", fg="white", relief="flat", padx=10).pack(side="left", padx=6)

        # RIGHT: detail + aksi
        right = tk.Frame(main, bg="#0d1117")
        main.add(right, width=620)

        # kurs bar
        self.kurs_label = tk.Label(right, text="🔄 Ambil kurs P2P...", font=("Segoe UI", 10, "bold"), bg="#0d1117", fg="#d29922")
        self.kurs_label.pack(anchor="w", pady=(0, 4))

        # detail frame
        det = tk.LabelFrame(right, text="👤 Detail Karyawan", bg="#0d1117", fg="#58a6ff", font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        det.pack(fill="x", pady=4)
        self.detail_text = tk.Text(det, height=10, bg="#161b22", fg="#e6edf3", relief="flat", font=("Consolas", 9))
        self.detail_text.pack(fill="x", padx=6, pady=6)
        self.detail_text.config(state="disabled")

        # key + password
        keyf = tk.LabelFrame(right, text="🔑 Wallet & Keamanan", bg="#0d1117", fg="#58a6ff", font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        keyf.pack(fill="x", pady=4)
        self.key_status = tk.Label(keyf, text="Private key: BELUM disimpan", font=("Segoe UI", 9), bg="#0d1117", fg="#8b949e")
        self.key_status.pack(anchor="w", padx=6, pady=(6, 2))
        bf = tk.Frame(keyf, bg="#0d1117")
        bf.pack(fill="x", padx=6, pady=(0, 4))
        tk.Button(bf, text="💾 Simpan Key", command=self._save_key_dialog, bg="#1f6feb", fg="white", relief="flat", padx=10).pack(side="left")
        tk.Button(bf, text="🔓 Buka Key", command=self._load_key_dialog, bg="#30363d", fg="white", relief="flat", padx=10).pack(side="left", padx=6)

        # aksi bayar
        act = tk.LabelFrame(right, text="💰 Aksi Pembayaran", bg="#0d1117", fg="#58a6ff", font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        act.pack(fill="x", pady=4)
        self.calc_label = tk.Label(act, text="Pilih karyawan untuk hitung USDT", font=("Segoe UI", 10), bg="#0d1117", fg="#e6edf3")
        self.calc_label.pack(anchor="w", padx=6, pady=4)
        ab = tk.Frame(act, bg="#0d1117")
        ab.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(ab, text="💸 BAYAR GAJI (USDT)", command=self._bayar, bg="#f85149", fg="white", relief="flat", padx=12).pack(side="left")
        tk.Button(ab, text="📤 Export Excel", command=self._export, bg="#30363d", fg="white", relief="flat", padx=12).pack(side="left", padx=6)

        # histori
        hist = tk.LabelFrame(right, text="📜 Histori Pembayaran", bg="#0d1117", fg="#58a6ff", font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        hist.pack(fill="both", expand=True, pady=4)
        self.hist_text = tk.Text(hist, height=8, bg="#161b22", fg="#e6edf3", relief="flat", font=("Consolas", 9))
        self.hist_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.hist_text.config(state="disabled")

        # Footer: balance wallet (pojok kiri bawah)
        footer = tk.Frame(self.root, bg="#0d1117")
        footer.pack(side="bottom", fill="x", padx=12, pady=6)
        self.balance_label = tk.Label(footer, text="💰 Balance: buka key dulu 🔓", font=("Consolas", 10, "bold"),
                                       bg="#0d1117", fg="#3fb950", anchor="w")
        self.balance_label.pack(side="left")
        tk.Button(footer, text="🔄 Refresh Balance", command=self._update_balance, bg="#30363d", fg="white",
                  relief="flat", padx=8).pack(side="right")

        self._refresh_list()

    def _update_balance(self):
        """Cek balance USDT + BNB dari key yang dibuka."""
        if not HAVE_WEB3:
            self.balance_label.config(text="⚠️ web3 belum terinstall")
            return
        if not self.private_key:
            self.balance_label.config(text="💰 Balance: buka key dulu 🔓")
            return
        try:
            w3 = Web3(Web3.HTTPProvider(BSC_RPC))
            acct = w3.eth.account.from_key(self.private_key)
            addr = acct.address
            bnb = w3.eth.get_balance(addr) / 10**18
            contract = w3.eth.contract(address=USDT_CA, abi=USDT_ABI)
            usdt = contract.functions.balanceOf(addr).call() / 10**18
            self.balance_label.config(
                text=f"💰 USDT: {usdt:,.2f}  |  BNB: {bnb:.4f}  |  {w3.to_checksum_address(addr)[:12]}...")
        except Exception as e:
            self.balance_label.config(text=f"⚠️ Balance error: {str(e)[:60]}")

    def _tambah_karyawan(self):
        self._edit_dialog(None)

    def _hapus_karyawan(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Pilih", "Pilih karyawan dulu!")
            return
        nama = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Hapus", f"Hapus {nama}?"):
            self.karyawan = [k for k in self.karyawan if k["nama"] != nama]
            self.data["karyawan"] = self.karyawan
            save_data(self.data)
            self._refresh_list()

    def _test_send(self, address, parent_win):
        """Kirim 1 USDT test ke address — verifikasi address benar."""
        if not HAVE_WEB3:
            messagebox.showwarning("Lib", "web3.py belum terinstall!")
            return
        if not address or len(address) != 42 or not address.startswith("0x"):
            messagebox.showwarning("Alamat", "Address EVM gak valid!\nFormat: 0x... (42 karakter)")
            return
        if not self.private_key:
            messagebox.showwarning("Key", "Buka private key dulu! (tombol 🔓 Buka Key)")
            return
        if not self.kurs and self.kurs != 0:
            # kurs belum penting untuk test — lanjut aja
            pass
        if not messagebox.askyesno("Konfirmasi Test",
            f"Kirim 1.00 USDT (test) ke:\n{address}\n\nIni TRANSAKSI SUNGGAHAN — butuh fee BNB kecil!\nLanjut?"):
            return
        try:
            w3 = Web3(Web3.HTTPProvider(BSC_RPC))
            acct = w3.eth.account.from_key(self.private_key)
            contract = w3.eth.contract(address=USDT_CA, abi=USDT_ABI)
            amount = int(1 * 10**18)  # 1 USDT
            tx = contract.functions.transfer(address, amount).build_transaction({
                "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
                "gas": 100000, "gasPrice": w3.eth.gas_price})
            signed = w3.eth.account.sign_transaction(tx, self.private_key)
            txid = w3.eth.send_raw_transaction(signed.rawTransaction)
            tx_hex = w3.to_hex(txid)
            # simpan ke histori test
            self.histori.append({"nama": "(TEST ADDRESS)", "usdt": 1.0, "txid": tx_hex,
                                  "waktu": datetime.now().strftime("%Y-%m-%d %H:%M")})
            self.data["histori"] = self.histori
            save_data(self.data)
            self._refresh_hist()
            messagebox.showinfo("TEST TERKIRIM! ✅",
                f"1 USDT test terkirim ke:\n{address}\n\nTx: {tx_hex}\n\nKalau masuk = address BENAR!\nKalau gak masuk = salah!")
            try:
                parent_win.lift()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Gagal", str(e)[:200])

    def _calendar_dialog(self, entry):
        """Kalender bulanan: grid klik-tanggal (gampang dipakai!)."""
        import calendar as _cal
        win = tk.Toplevel(self.root)
        win.title("📅 Pilih Tanggal")
        win.configure(bg="#0d1117")
        win.resizable(False, False)

        # state kalender
        today = datetime.now()
        cur_y, cur_m = today.year, today.month
        # ambil tanggal existing kalau ada (format 11-Aug-25)
        sel_d = None
        cur_val = entry.get().strip()
        if cur_val:
            try:
                parts = cur_val.split("-")
                if len(parts) == 3 and parts[0].isdigit():
                    months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"Mei":5,"Jun":6,"Jul":7,"Agu":8,"Sep":9,"Okt":10,"Nov":11,"Des":12}
                    m = months.get(parts[1], today.month)
                    y = 2000 + int(parts[2]) if len(parts[2]) == 2 else int(parts[2])
                    sel_d = int(parts[0])
                    cur_y, cur_m = y, m
            except Exception:
                pass

        # header
        head = tk.Frame(win, bg="#0d1117")
        head.pack(fill="x", padx=8, pady=6)
        tk.Button(head, text="◀", command=lambda: _change(-1), bg="#30363d", fg="white",
                  relief="flat", width=3).pack(side="left")
        month_label = tk.Label(head, text="", bg="#0d1117", fg="#58a6ff",
                               font=("Segoe UI", 12, "bold"), width=16)
        month_label.pack(side="left", expand=True)
        tk.Button(head, text="▶", command=lambda: _change(1), bg="#30363d", fg="white",
                  relief="flat", width=3).pack(side="right")

        # grid hari
        grid = tk.Frame(win, bg="#0d1117")
        grid.pack(padx=8, pady=(0, 6))
        days = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
        for i, d in enumerate(days):
            tk.Label(grid, text=d, bg="#0d1117", fg="#8b949e", width=5,
                     font=("Segoe UI", 9, "bold")).grid(row=0, column=i, padx=1, pady=1)
        cells = {}
        for r in range(1, 7):
            for c in range(7):
                lbl = tk.Label(grid, text="", bg="#161b22", fg="#e6edf3", width=5, height=2,
                               font=("Segoe UI", 9), cursor="hand2")
                lbl.grid(row=r, column=c, padx=1, pady=1)
                cells[(r, c)] = lbl

        def _render():
            month_label.config(text=f"{['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][cur_m-1]} {cur_y}")
            cal = _cal.Calendar(firstweekday=0)  # Senin dulu
            dates = cal.monthdatescalendar(cur_y, cur_m)
            for r in range(6):
                for c in range(7):
                    lbl = cells[(r, c)]
                    if r < len(dates):
                        d = dates[r][c]
                        in_month = d.month == cur_m
                        lbl.config(text=str(d.day),
                                   fg="#e6edf3" if in_month else "#484f58",
                                   bg="#1f6feb" if (in_month and d.day == sel_d and sel_d) else "#161b22")
                        lbl.bind("<Button-1>", lambda e, dd=d: _pick(dd))
                    else:
                        lbl.config(text="", bg="#161b22")

        def _change(delta):
            nonlocal cur_y, cur_m
            cur_m += delta
            if cur_m < 1:
                cur_m, cur_y = 12, cur_y - 1
            elif cur_m > 12:
                cur_m, cur_y = 1, cur_y + 1
            _render()

        def _pick(d):
            months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
            entry.delete(0, "end")
            entry.insert(0, f"{d.day}-{months[d.month-1]}-{str(d.year)[-2:]}")
            win.destroy()

        _render()

    def _edit_dialog(self, existing):
        """Dialog tambah/edit karyawan: grouping, kalender, multiline, kode unik."""
        win = tk.Toplevel(self.root)
        win.title("✏️ Edit Karyawan" if existing else "➕ Tambah Karyawan")
        win.configure(bg="#0d1117")
        win.geometry("600x560")

        # ---- field Entry biasa ----
        row = 0
        tk.Label(win, text="Kode Karyawan (unik):", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        kode_var = tk.StringVar(value=str(existing.get("kode", "")) if existing else "")
        kode_entry = tk.Entry(win, textvariable=kode_var, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat")
        kode_entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        tk.Label(win, text="Nama Karyawan:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        nama_var = tk.StringVar(value=existing.get("nama", "") if existing else "")
        tk.Entry(win, textvariable=nama_var, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat").grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        tk.Label(win, text="Gaji (IDR):", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        gaji_var = tk.StringVar(value=_fmt_idr(existing.get("gaji", "")) if existing else "")
        gaji_entry = _grouping_entry(win, gaji_var)
        gaji_entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        gaji_var.trace_add("write", lambda *a: _apply_grouping(gaji_var))
        row += 1

        tk.Label(win, text="Gaji + Fee (0.2%):", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        fee_var = tk.StringVar(value=_fmt_idr(int(existing.get("gaji", 0) * (1 + FEE_RATE))) if existing else "")
        fee_label = tk.Label(win, textvariable=fee_var, bg="#161b22", fg="#d29922", font=("Consolas", 10, "bold"), anchor="w", width=38, relief="flat")
        fee_label.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        # auto hitung fee dari gaji
        def _auto_fee(*_):
            fee_var.set(_fmt_idr(int(_parse_idr(gaji_var.get()) * (1 + FEE_RATE))))
        gaji_var.trace_add("write", _auto_fee)
        row += 1

        tk.Label(win, text="EVM/ETH Address:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        eth_frame = tk.Frame(win, bg="#0d1117")
        eth_frame.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        eth_var = tk.StringVar(value=existing.get("eth", "") if existing else "")
        eth_entry = tk.Entry(eth_frame, textvariable=eth_var, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat")
        eth_entry.pack(side="left")
        tk.Button(eth_frame, text="🧪 SEND 1 USDT", command=lambda: self._test_send(eth_var.get().strip(), win),
                  bg="#8a5a00", fg="white", relief="flat", padx=8).pack(side="left", padx=6)
        row += 1

        tk.Label(win, text="Pintu:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        pintu_var = tk.StringVar(value=existing.get("pintu", "") if existing else "")
        tk.Entry(win, textvariable=pintu_var, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat").grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        tk.Label(win, text="Jatuh Tempo:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        jt_frame = tk.Frame(win, bg="#0d1117")
        jt_frame.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        jt_var = tk.StringVar(value=existing.get("jatuh_tempo", "") if existing else "")
        jt_entry = tk.Entry(jt_frame, textvariable=jt_var, width=30, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat")
        jt_entry.pack(side="left")
        tk.Button(jt_frame, text="📅", command=lambda: self._calendar_dialog(jt_entry), bg="#30363d", fg="white", relief="flat").pack(side="left", padx=4)
        row += 1

        # ---- Komisi (multiline) ----
        tk.Label(win, text="Komisi:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="ne", padx=8, pady=4)
        komisi_text = tk.Text(win, height=2, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat", font=("Consolas", 9))
        komisi_text.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        if existing and existing.get("komisi"):
            komisi_text.insert("1.0", existing["komisi"])
        row += 1

        # ---- Notes (multiline besar) ----
        tk.Label(win, text="Notes:", bg="#0d1117", fg="#e6edf3", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="ne", padx=8, pady=4)
        notes_text = tk.Text(win, height=6, width=45, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat", font=("Consolas", 9))
        notes_text.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        if existing and existing.get("notes"):
            notes_text.insert("1.0", existing["notes"])
        row += 1

        def save():
            nama = nama_var.get().strip()
            if not nama:
                messagebox.showwarning("Lengkap", "Nama wajib diisi!")
                return
            kode = kode_var.get().strip()
            gaji = _parse_idr(gaji_var.get())
            # kode unik (primary key ala MS Access)
            if kode:
                for x in self.karyawan:
                    if str(x.get("kode", "")) == kode and (not existing or x["nama"] != existing["nama"]):
                        messagebox.showwarning("Kode", f"Kode {kode} sudah dipakai karyawan lain!")
                        return
            else:
                # auto-generate: max+1
                kode = str(max([_parse_idr(str(x.get("kode", 0))) for x in self.karyawan], default=0) + 1)
            k = {
                "kode": int(kode) if kode.isdigit() else kode,
                "nama": nama,
                "gaji": gaji,
                "gaji_x_fee": int(gaji * (1 + FEE_RATE)),
                "eth": eth_var.get().strip(),
                "pintu": pintu_var.get().strip(),
                "jatuh_tempo": jt_var.get().strip(),
                "komisi": komisi_text.get("1.0", "end").strip(),
                "notes": notes_text.get("1.0", "end").strip(),
            }
            if existing:
                for i, x in enumerate(self.karyawan):
                    if x["nama"] == existing["nama"]:
                        self.karyawan[i] = k
                        break
            else:
                self.karyawan.append(k)
            self.data["karyawan"] = self.karyawan
            save_data(self.data)
            self._refresh_list()
            messagebox.showinfo("Sukses", f"Karyawan tersimpan! (Kode: {k['kode']})")
            win.destroy()

        tk.Button(win, text="💾 Simpan", command=save, bg="#1f6feb", fg="white", relief="flat", padx=20, pady=4).grid(row=row, column=1, sticky="w", padx=8, pady=12)

    def _edit_karyawan(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Pilih", "Pilih karyawan dulu!")
            return
        nama = self.tree.item(sel[0])["values"][0]
        k = next((x for x in self.karyawan if x["nama"] == nama), None)
        if k:
            self._edit_dialog(k)

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        filt = self.filter_var.get().lower()

        # hitung jatuh tempo + sort: yang paling dekat gajian di ATAS
        rows = []
        for k in self.karyawan:
            if filt and filt not in k["nama"].lower():
                continue
            jt = _parse_jatuh_tempo(k.get("jatuh_tempo", ""))
            days_left = jt[1] if jt else 99999  # tanpa tanggal = paling bawah
            rows.append((days_left, k))
        rows.sort(key=lambda x: x[0])  # ascending: dekat/telat di atas

        total = 0
        for days_left, k in rows:
            usdt = f"{k['gaji'] * (1 + FEE_RATE) / self.kurs:,.2f}" if self.kurs else "-"
            tag = ""
            if days_left != 99999:
                if days_left < 0:
                    tag = "red"       # TELAT (sudah lewat jatuh tempo)
                elif days_left == 0:
                    tag = "today"     # JATUH TEMPO HARI INI
                elif days_left <= 7:
                    tag = "soon"      # dekat gajian (1-7 hari lagi)
            self.tree.insert("", "end", values=(k["nama"], _fmt_idr(k["gaji"]), usdt), tags=(tag,) if tag else ())
            total += k["gaji"]
        self.total_label.config(text=f"Total Karyawan: {len(rows)}  |  Total Gaji: Rp {total:,.0f}")

    def _on_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        nama = self.tree.item(sel[0])["values"][0]
        k = next((x for x in self.karyawan if x["nama"] == nama), None)
        if not k:
            return
        self._show_detail(k)
        self._update_calc(k)

    def _show_detail(self, k):
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        lines = [
            f"Kode     : {k.get('kode', 0)}",
            f"Nama     : {k['nama']}",
            f"Gaji     : Rp {_fmt_idr(k['gaji'])}",
            f"Gaji+Fee : Rp {_fmt_idr(k.get('gaji_x_fee', k['gaji'] * (1 + FEE_RATE)))}",
            f"Bank     : {k.get('bank','') or '-'} | {k.get('norek','') or ''}",
            f"EVM/ETH  : {k.get('eth','') or '-'}",
            f"Pintu    : {k.get('pintu','') or '-'}",
            f"Jatuh    : {k.get('jatuh_tempo','') or '-'}",
            f"Komisi   : {k.get('komisi','') or '-'}",
            f"Notes    : {k.get('notes','') or '-'}",
        ]
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.config(state="disabled")
        # tampilkan histori gaji per karyawan
        try:
            hist = db_histori_by_karyawan(k.get("kode", 0), limit=50)
            self.hist_text.config(state="normal")
            self.hist_text.delete("1.0", "end")
            if hist:
                total = sum(h.get("gaji_idr", 0) for h in hist)
                self.hist_text.insert("end", f"📜 HISTORI GAJI: {k['nama']} (total tampil {len(hist)})\n")
                self.hist_text.insert("end", f"💰 Total (50 terakhir): Rp {_fmt_idr(total)}\n{'='*45}\n\n")
                for h in hist:
                    tgl = h.get("tanggal", "") or ""
                    gaji = _fmt_idr(h.get("gaji_idr", 0))
                    notes = (h.get("notes", "") or "")[:80]
                    self.hist_text.insert("end", f"{tgl} | Rp {gaji}")
                    if notes:
                        self.hist_text.insert("end", f" | {notes}")
                    self.hist_text.insert("end", "\n")
            else:
                self.hist_text.insert("end", "Belum ada histori gaji.")
            self.hist_text.config(state="disabled")
        except Exception:
            pass

    def _update_calc(self, k):
        if not self.kurs:
            self.calc_label.config(text=f"{k['nama']}: kurs belum ada — tunggu sebentar...")
            return
        usdt = k["gaji"] * (1 + FEE_RATE) / self.kurs
        self.calc_label.config(
            text=f"{k['nama']}: Rp {_fmt_idr(k['gaji'])} +0.2% → {usdt:,.2f} USDT "
                 f"(kurs P2P BUY {self.kurs:,.0f})")

    def _refresh_kurs_async(self):
        def worker():
            try:
                rate = get_p2p_rate()
                self.kurs = rate * (1 + FEE_RATE)
                self.root.after(0, lambda: self.kurs_label.config(
                    text=f"🟢 Kurs P2P: Rp {rate:,.0f} → +0.2% = Rp {self.kurs:,.0f}/USDT (live!)"))
            except Exception as e:
                self.root.after(0, lambda: self.kurs_label.config(
                    text=f"⚠️ Gagal ambil kurs: {e} — pakai manual 17.800"))
                self.kurs = 17800 * (1 + FEE_RATE)
        threading.Thread(target=worker, daemon=True).start()


    def _save_key_dialog(self):
        if not HAVE_CRYPTO:
            messagebox.showwarning("Lib", "pycryptodome belum terinstall — key disimpan dengan enkripsi ringan. Install: pip install pycryptodome")
        win = tk.Toplevel(self.root)
        win.title("💾 Simpan Private Key")
        win.configure(bg="#0d1117")
        tk.Label(win, text="Private Key:", bg="#0d1117", fg="#e6edf3").grid(row=0, column=0, padx=8, pady=6)
        key_entry = tk.Entry(win, width=70, bg="#161b22", fg="#e6edf3", show="*")
        key_entry.grid(row=0, column=1, padx=8)
        tk.Label(win, text="Password (untuk enkripsi):", bg="#0d1117", fg="#e6edf3").grid(row=1, column=0, padx=8)
        pw_entry = tk.Entry(win, width=70, bg="#161b22", fg="#e6edf3", show="*")
        pw_entry.grid(row=1, column=1, padx=8)
        def save():
            pk, pw = key_entry.get().strip(), pw_entry.get()
            if not pk or not pw:
                messagebox.showwarning("Lengkap", "Isi private key + password!")
                return
            try:
                save_key(pk, pw)
                self.key_status.config(text="✅ Private key TERSIMPAN (terenkripsi!)")
                messagebox.showinfo("Sukses", "Private key disimpan terenkripsi di:\n" + KEY_FILE)
                win.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e))
        tk.Button(win, text="Simpan", command=save, bg="#1f6feb", fg="white", relief="flat").grid(row=2, column=1, pady=10)

    def _load_key_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("🔓 Buka Private Key")
        win.configure(bg="#0d1117")
        tk.Label(win, text="Password:", bg="#0d1117", fg="#e6edf3").grid(row=0, column=0, padx=8, pady=6)
        pw = tk.Entry(win, width=50, bg="#161b22", fg="#e6edf3", show="*")
        pw.grid(row=0, column=1, padx=8)
        def load():
            try:
                self.private_key = load_key(pw.get())
                addr = "?"
                if HAVE_WEB3:
                    w3 = Web3(Web3.HTTPProvider(BSC_RPC))
                    addr = w3.to_checksum_address(w3.eth.account.from_key(self.private_key).address)
                self.key_status.config(text=f"✅ Key terbuka! Address: {addr[:12]}...")
                self._update_balance()
                messagebox.showinfo("Sukses", f"Private key terbuka.\nAddress: {addr}")
                win.destroy()
            except Exception:
                messagebox.showerror("Gagal", "Password salah atau file key rusak!")
        tk.Button(win, text="Buka", command=load, bg="#1f6feb", fg="white", relief="flat").grid(row=1, column=1, pady=10)

    def _bayar(self):
        if not HAVE_WEB3:
            messagebox.showwarning("Lib", "web3.py belum terinstall! Jalankan: pip install web3")
            return
        if not self.private_key:
            messagebox.showwarning("Key", "Buka private key dulu! (tombol 🔓 Buka Key)")
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Pilih", "Pilih karyawan dulu!")
            return
        nama = self.tree.item(sel[0])["values"][0]
        k = next(x for x in self.karyawan if x["nama"] == nama)
        if not k.get("eth"):
            messagebox.showwarning("Alamat", f"{nama} tidak punya address EVM!")
            return
        usdt = k["gaji"] * (1 + FEE_RATE) / self.kurs
        if not messagebox.askyesno("Konfirmasi",
            f"Kirim {usdt:,.2f} USDT ke:\n{k['eth']}\n({nama})\n\nLANJUT?"):
            return
        try:
            w3 = Web3(Web3.HTTPProvider(BSC_RPC))
            acct = w3.eth.account.from_key(self.private_key)
            contract = w3.eth.contract(address=USDT_CA, abi=USDT_ABI)
            amount = int(usdt * 10**18)
            tx = contract.functions.transfer(k["eth"], amount).build_transaction({
                "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
                "gas": 100000, "gasPrice": w3.eth.gas_price})
            signed = w3.eth.account.sign_transaction(tx, self.private_key)
            txid = w3.eth.send_raw_transaction(signed.rawTransaction)
            self.histori.append({"nama": nama, "usdt": round(usdt, 2), "txid": w3.to_hex(txid),
                                  "waktu": datetime.now().strftime("%Y-%m-%d %H:%M")})
            self.data["histori"] = self.histori
            save_data(self.data)
            self._refresh_hist()
            messagebox.showinfo("TERKIRIM! 🎉", f"Tx: {w3.to_hex(txid)}")
        except Exception as e:
            messagebox.showerror("Gagal", str(e))

    def _refresh_hist(self):
        self.hist_text.config(state="normal")
        self.hist_text.delete("1.0", "end")
        for h in reversed(self.histori[-50:]):
            self.hist_text.insert("end", f"{h['waktu']} | {h['nama']} | {h['usdt']:,.2f} USDT | {h['txid'][:18]}...\n")
        self.hist_text.config(state="disabled")

    def _export(self):
        try:
            import csv
            path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Kode", "Nama", "Gaji IDR", "Gaji+Fee", "USDT", "EVM/ETH", "Pintu", "Komisi", "Notes"])
                for k in self.karyawan:
                    usdt = k["gaji"] / self.kurs if self.kurs else 0
                    w.writerow([k.get("kode",0), k["nama"], k["gaji"], k.get("gaji_x_fee", k["gaji"]), round(k["gaji"] * (1 + FEE_RATE) / self.kurs, 2) if self.kurs else "", k.get("eth",""), k.get("pintu",""), k.get("komisi",""), k.get("notes","")])
            messagebox.showinfo("Sukses", "CSV tersimpan: " + path)
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = FastGajiApp(root)
    root.mainloop()
