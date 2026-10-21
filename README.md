# OLT Control

Aplikasi **Android native berbasis Flutter** untuk teknisi yang mengelola ONT pada ZTE C320 GPON OLT. Aplikasi HP berbicara ke backend FastAPI di mini PC; backend yang berkomunikasi ke OLT melalui Telnet dan menyimpan hasil sinkronisasi di SQLite.

```text
Aplikasi Android (Flutter) ── LAN/VPN ──> Backend FastAPI (mini PC) ── Telnet ──> ZTE C320
```

## Fitur MVP

- Login bertoken; beberapa profil koneksi dengan password terenkripsi di server.
- Dashboard status ONT, daftar dan filter PON, pencarian nama/SN/PPPoE, dan detail ONT.
- Registrasi dari daftar ONT yang belum dikonfigurasi, dengan pemilihan ONU ID kosong otomatis.
- Aksi ONT (hapus, redaman, paket, VLAN, PPPoE, ganti ONT, remote, reboot), sinkronisasi SQLite, simpan konfigurasi, dan log.
- Adapter mock agar alur aplikasi bisa dicoba tanpa OLT sungguhan.

## Mulai cepat (demo)

```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
OLT_MODE=mock python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mode mock menyediakan login `admin` / `admin`; hanya untuk uji coba. Buka Swagger di `http://127.0.0.1:8000/docs`. Instalasi server dan aplikasi HP dijelaskan langkah demi langkah di:

- [Instalasi backend di server](docs/INSTALASI_SERVER.md)
- [Instalasi aplikasi Android](docs/INSTALASI_HP.md)
- [Referensi API](docs/API.md)
- [Desain arsitektur dan data](docs/DESAIN.md)
- [Pemecahan masalah](docs/TROUBLESHOOTING.md)

Tes backend: `cd backend && python -m pytest`.

## Peringatan keselamatan

**Uji seluruh alur dengan `OLT_MODE=mock` terlebih dahulu.** Jangan jalankan perintah tulis pada OLT produksi sebelum setiap sintaks diuji dengan cermat di lab/perangkat yang sesuai. Selalu simpan backup konfigurasi OLT. Sintaks CLI dapat berbeda menurut firmware dan kartu; pemilik instalasi wajib memeriksa `show version-running`, termasuk ZTE C320 V2.1.0 dengan kartu GTGOG dan SMXA.

Perubahan paket dan PPPoE (`change-pppoe`, password tidak pernah di-log/dikembalikan) sudah aktif pada OLT nyata; verifikasi sintaks pada lab terlebih dahulu. Tindakan tulis lainnya pada OLT nyata akan ditolak sampai template CLI di `backend/app/commands.py` diverifikasi dan implementasinya disesuaikan untuk firmware setempat.

HTTP cleartext hanya disediakan untuk LAN tepercaya. Jangan membuka backend langsung ke internet; gunakan HTTPS atau VPN seperti Tailscale/WireGuard untuk akses dari luar jaringan.
