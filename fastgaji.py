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
import os, sys, json, base64, hashlib, threading, queue
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
DATA_FILE = os.path.join(APP_DIR, "fastgaji_data.json")
KEY_FILE = os.path.join(APP_DIR, "fastgaji_key.enc")

BSC_RPC = "https://bnb-mainnet.g.alchemy.com/v2/alch_KgymfWpXkADRUuQzAtwcD"
USDT_CA = "0x55d398326f99059fF775485246999027B3197955"
FEE_RATE = 0.002  # fee 0.2% dari kurs P2P
USDT_ABI = [
    {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]

# ================= DATA DEFAULT (dari DB karyawan) =================
DEFAULT_KARYAWAN = [
    {"nama": "HARTONI", "kode": 249, "gaji": 15000852, "gaji_x_fee": 15030854, "eth": "0x91043400624D998eF3cE5A6772176918d9E05046", "pintu": "@hartoni729", "jatuh_tempo": "11-Aug-25", "komisi": "100/120/130/150/200", "notes": "1may2026=15jt/14 @sep2025//13jt @jan202512jt @july2024gaji masuk 30-oct-2019lsg 2 bln 6jt"},
    {"nama": "BOBI FIRMANSYAH", "kode": 181, "gaji": 20000777, "gaji_x_fee": 20040779, "eth": "0x18d5e7965c3d2c579d0025d5a39891fdb6820c82", "pintu": "@bobbyfirmansyah", "jatuh_tempo": "11-Oct-24", "komisi": "85/145/200/270/350/450", "notes": "3-april-2026=20jt / 9july2025=11jt kerja mulai 11 oct 2024"},
    {"nama": "NURHADI GUSNAIN", "kode": 324, "gaji": 11000101, "gaji_x_fee": 11022101, "eth": "0x031F52Aa40aB6e8925dB0823626eF7C15f4310f2", "pintu": "@nurhadi.gusnain916", "jatuh_tempo": "19-Jun-25", "komisi": "2thn=7k usd", "notes": "10jan2026=11jt//start-19june2025~spv malam"},
    {"nama": "HERIY HARYADI", "kode": 0, "gaji": 12000000, "gaji_x_fee": 12024000, "eth": "0x8FFf385A30c91548C519Be4eC92E576872a0c650", "pintu": "@hery65664597", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "YOGI ANDIKA", "kode": 0, "gaji": 12000000, "gaji_x_fee": 12024000, "eth": "0x12AD8a8c3aA7c1F902B2Cb2BbB2b21c5F5b5D34a", "pintu": "@ya5666913602", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "ACEN", "kode": 0, "gaji": 30123789, "gaji_x_fee": 30159789, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "CELVIN APRIO", "kode": 0, "gaji": 5000333, "gaji_x_fee": 5005333, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "TENGKU REZA ERIANDA", "kode": 0, "gaji": 5123789, "gaji_x_fee": 5128789, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "WIVIANY ELLEN", "kode": 0, "gaji": 4500564, "gaji_x_fee": 4505564, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "M RIZKY PRATAMA", "kode": 0, "gaji": 5000000, "gaji_x_fee": 5005000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "SHEREN", "kode": 0, "gaji": 4000000, "gaji_x_fee": 4004000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "JOURDAN", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "MUHAMMAD SAFIUDIN", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "TEGAR", "kode": 0, "gaji": 4000000, "gaji_x_fee": 4004000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "ERICK", "kode": 0, "gaji": 3800000, "gaji_x_fee": 3803800, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "HENDY HALIM", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "JIU CHING", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "STEVEN ZEBUA", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "JUSTIN LIMORGEN", "kode": 0, "gaji": 3500000, "gaji_x_fee": 3503500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "RIDUAN HAMID", "kode": 0, "gaji": 3000000, "gaji_x_fee": 3003000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "M RAFLY AL RISYA", "kode": 0, "gaji": 3000000, "gaji_x_fee": 3003000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "KELVIN ADINATA", "kode": 0, "gaji": 3000000, "gaji_x_fee": 3003000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "M FARIZ RAMADHAN", "kode": 0, "gaji": 3000000, "gaji_x_fee": 3003000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "JIMMY CHANG", "kode": 0, "gaji": 3000000, "gaji_x_fee": 3003000, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "SANDY YULPIANDA", "kode": 0, "gaji": 2500000, "gaji_x_fee": 2502500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
    {"nama": "MUHAMMAD VADRIZAL", "kode": 0, "gaji": 2500000, "gaji_x_fee": 2502500, "eth": "", "pintu": "", "jatuh_tempo": "", "komisi": "", "notes": ""},
]

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
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"karyawan": DEFAULT_KARYAWAN, "histori": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= KURS BINANCE P2P =================
def get_p2p_rate():
    """Ambil kurs USDT/IDR dari Binance P2P (rata-rata penjual terbaik)."""
    import urllib.request
    payload = json.dumps({"page": 1, "rows": 5, "payTypes": [], "asset": "USDT", "tradeType": "SELL", "fiat": "IDR"}).encode()
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
        self.tree.heading("usd", text="USD")
        self.tree.column("nama", width=200)
        self.tree.column("gaji", width=110, anchor="e")
        self.tree.column("usd", width=90, anchor="e")
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
        tk.Button(ab, text="🧮 Hitung USDT", command=self._hitung, bg="#238636", fg="white", relief="flat", padx=12).pack(side="left")
        tk.Button(ab, text="💸 BAYAR GAJI (USDT)", command=self._bayar, bg="#f85149", fg="white", relief="flat", padx=12).pack(side="left", padx=6)
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

    def _edit_dialog(self, existing):
        """Dialog tambah/edit karyawan."""
        win = tk.Toplevel(self.root)
        win.title("✏️ Edit Karyawan" if existing else "➕ Tambah Karyawan")
        win.configure(bg="#0d1117")
        win.geometry("560x480")

        fields = [
            ("nama", "Nama Karyawan"), ("kode", "Kode"), ("gaji", "Gaji (IDR)"),
            ("gaji_x_fee", "Gaji + Fee (0.2%)"), ("eth", "EVM/ETH Address"),
            ("pintu", "Pintu"), ("jatuh_tempo", "Jatuh Tempo"),
            ("komisi", "Komisi"), ("notes", "Notes"),
        ]
        vals = existing or {}
        entries = {}
        for i, (key, label) in enumerate(fields):
            tk.Label(win, text=label + ":", bg="#0d1117", fg="#e6edf3",
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="e", padx=8, pady=3)
            e = tk.Entry(win, width=55, bg="#161b22", fg="#e6edf3", insertbackground="#e6edf3", relief="flat")
            e.grid(row=i, column=1, sticky="w", padx=8, pady=3)
            e.insert(0, str(vals.get(key, "")))
            entries[key] = e

        # Auto-fill gaji_x_fee dari gaji
        def auto_fee(*_):
            try:
                gaji = int(entries["gaji"].get().replace(",", "").replace(".", ""))
                entries["gaji_x_fee"].delete(0, "end")
                entries["gaji_x_fee"].insert(0, str(int(gaji * (1 + FEE_RATE))))
            except ValueError:
                pass
        entries["gaji"].bind("<KeyRelease>", auto_fee)

        def save():
            k = {}
            for key, label in fields:
                v = entries[key].get().strip()
                if key in ("gaji", "gaji_x_fee"):
                    try:
                        k[key] = int(v.replace(",", "").replace(".", ""))
                    except ValueError:
                        k[key] = 0
                else:
                    k[key] = v
            if not k.get("nama"):
                messagebox.showwarning("Lengkap", "Nama wajib diisi!")
                return
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
            messagebox.showinfo("Sukses", "Karyawan tersimpan!")
            win.destroy()

        tk.Button(win, text="💾 Simpan", command=save, bg="#1f6feb", fg="white",
                  relief="flat", padx=16, pady=4).grid(row=len(fields), column=1, sticky="w", padx=8, pady=12)

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
        total = 0
        for k in self.karyawan:
            if filt and filt not in k["nama"].lower():
                continue
            usd = f"{k['gaji'] / self.kurs:,.2f}" if self.kurs else "-"
            self.tree.insert("", "end", values=(k["nama"], f"{k['gaji']:,.0f}", usd))
            total += k["gaji"]
        self.total_label.config(text=f"Total Karyawan: {len(self.karyawan)}  |  Total Gaji: Rp {total:,.0f}")

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
            f"Gaji     : Rp {k['gaji']:,.0f}",
            f"Gaji+Fee : Rp {k.get('gaji_x_fee', k['gaji']):,.0f}",
            f"EVM/ETH  : {k.get('eth','') or '-'}",
            f"Pintu    : {k.get('pintu','') or '-'}",
            f"Jatuh    : {k.get('jatuh_tempo','') or '-'}",
            f"Komisi   : {k.get('komisi','') or '-'}",
            f"Notes    : {k.get('notes','') or '-'}",
        ]
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.config(state="disabled")

    def _update_calc(self, k):
        if not self.kurs:
            self.calc_label.config(text=f"{k['nama']}: kurs belum ada — tunggu sebentar...")
            return
        usdt = k["gaji"] / self.kurs
        self.calc_label.config(
            text=f"{k['nama']}: Rp {k['gaji']:,.0f} ÷ {self.kurs:,.0f} = {usdt:,.2f} USDT "
                 f"(kurs P2P +0.2%)")

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

    def _hitung(self):
        if not self.kurs:
            messagebox.showwarning("Kurs", "Kurs belum siap. Coba lagi.")
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Pilih", "Pilih karyawan dulu!")
            return
        nama = self.tree.item(sel[0])["values"][0]
        k = next(x for x in self.karyawan if x["nama"] == nama)
        usdt = k["gaji"] / self.kurs
        messagebox.showinfo("Hitung USDT",
            f"{k['nama']}\nGaji: Rp {k['gaji']:,.0f}\nKurs (+2%): Rp {self.kurs:,.0f}\n\n= {usdt:,.2f} USDT")

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
        usdt = k["gaji"] / self.kurs
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
                    w.writerow([k.get("kode",0), k["nama"], k["gaji"], k.get("gaji_x_fee", k["gaji"]), round(usdt, 2), k.get("eth",""), k.get("pintu",""), k.get("komisi",""), k.get("notes","")])
            messagebox.showinfo("Sukses", "CSV tersimpan: " + path)
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = FastGajiApp(root)
    root.mainloop()
