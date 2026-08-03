# FASTGAJI 💰

Aplikasi Gaji Karyawan Windows — dibuat oleh **Chokdi** 🐷 untuk **Bang Ano-CR448**.

## Fitur
- 📋 Daftar karyawan + detail (bank, eWallet, Pintu, ETH/BNB)
- 💰 Hitung gaji IDR → USDT (kurs Binance P2P **+2%** otomatis!)
- 💸 Bayar gaji via USDT BSC (web3)
- 🔑 Private key LOKAL terenkripsi (AES-256 + password!)
- 📤 Export CSV
- 📜 Histori pembayaran

## Build
```bash
pip install pyinstaller pycryptodome web3 requests
pyinstaller --onefile --windowed --name FastGaji fastgaji.py
```

## Keamanan
- Private key **TIDAK pernah** keluar dari PC!
- Disimpan terenkripsi (AES-GCM + PBKDF2) di `fastgaji_key.enc`
- Butuh password untuk membuka

---
*by Chokdi 🐷 · Bang Ano-CR448 · 2026*
