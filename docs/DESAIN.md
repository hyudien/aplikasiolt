# Desain OLT Control

## Arsitektur

```text
Flutter Android ── HTTP pada LAN/VPN ──> FastAPI mini PC ── Telnet ──> ZTE C320
                                                  │
                                                  └── SQLite (cache pencarian, sync, audit)
```

HP tidak terhubung langsung ke Telnet OLT. Backend memegang kredensial OLT, mengatur satu lock per adapter, menjalankan parser yang dapat disesuaikan, dan menyediakan API untuk aplikasi. SQLite mempercepat pencarian ONT setelah data disinkronkan.

## Layar Android

- **Splash/Login**: pulihkan sesi lokal atau login memakai URL server dan akun teknisi; token disimpan dengan `flutter_secure_storage`.
- **Dashboard**: kartu total/online/offline/LOS dan daftar PON.
- **Cari**: pencarian nama, SN, dan PPPoE; buka detail ONT.
- **Registrasi**: pilih SN hasil deteksi `show gpon onu uncfg`, lihat PON dan ONU ID berikutnya, masukkan data layanan, tinjau ringkasan, lalu registrasi.
- **Sync**: sync penuh/per-PON serta status pekerjaan terakhir.
- **Setting**: profil OLT, uji koneksi, simpan konfigurasi; ikon riwayat membuka Logs.
- **Detail PON/ONT**: filter/search status di PON dan tombol aksi ONT dengan konfirmasi untuk perubahan destruktif.

## Backend

- `app/main.py`: API FastAPI, autentikasi bertoken HMAC, validasi, penyimpanan lokal, dan log.
- `app/olt/base.py`, `mock.py`, `zte.py`: antarmuka adapter, data demo, dan transport Telnet.
- `app/commands.py`: template perintah pada satu tempat.
- `app/parsers.py`: parser keluaran CLI dan normalisasi state.
- `tests/`: sampel keluaran CLI dan uji alur API mock.

Password login disimpan sebagai hash PBKDF2-HMAC-SHA256. Password profil OLT dienkripsi memakai Fernet dengan `FERNET_KEY`. Kunci tersebut hanya disimpan di `.env` backend; jangan pernah mengirim password OLT ke aplikasi kecuali untuk tes koneksi atau proses simpan profil.

## Skema database SQLite

- `olt_connections`: nama, host, port, username, dan password terenkripsi (tidak pernah dikembalikan di API).
- `pons`: ringkasan jumlah ONT per PON dan waktu sync.
- `onts`: interface, PON, ONU ID, SN, nama, status/alasan, PPPoE, VLAN, profile, mode, daya optik, dan waktu terakhir terlihat.
- `action_logs`: akun, aksi, target, hasil, keterangan, dan timestamp.
- `sync_jobs`: lingkup, status, ringkasan, waktu mulai/selesai.

Sync penuh mengganti cache ONT dengan hasil terkini. SQLite berada pada path `DATABASE_PATH` (default `backend/data/olt.db`).

## Catatan kompatibilitas dan keamanan

Format keluaran dan perintah CLI dapat berbeda antar versi software, kartu, dan konfigurasi. Parser saat ini perlu dicocokkan dengan sampel lokal. Perintah konfigurasi yang sintaksnya belum dipastikan diberi TODO dan tidak dijalankan pada adapter nyata. Uji semua template terlebih dahulu pada lab; backup konfigurasi; lindungi mini PC dan kredensial. HTTP cleartext hanya untuk LAN tepercaya; gunakan VPN/HTTPS di luar LAN.
