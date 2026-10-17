# Pemecahan masalah

## HP tidak bisa terhubung ke backend

1. Pastikan service aktif: `sudo systemctl status olt-control` atau `docker compose ps`.
2. Pada server, uji `curl http://127.0.0.1:8000/health`.
3. Di HP, gunakan alamat IP LAN mini PC dan port `8000`, misalnya `http://192.168.1.10:8000` (bukan `/docs`).
4. Pastikan HP dan server berada pada jaringan/VLAN yang saling menjangkau. Periksa firewall UFW/Windows; izinkan port hanya untuk subnet LAN.
5. HTTP lokal membutuhkan Android cleartext yang diaktifkan aplikasi. Hindari Wi-Fi publik; gunakan VPN untuk akses luar.

## Timeout atau koneksi Telnet ditolak

- Dari mini PC, uji `nc -vz IP_OLT 23` atau `telnet IP_OLT 23`.
- `telnet refused`: OLT menolak TCP/23, layanan Telnet mati, atau alamat/port salah.
- `timeout`: periksa routing, VLAN manajemen, ACL, kabel, firewall, dan IP OLT.
- `auth failed`: cek username/password Telnet serta izin akun.
- Tes harus dilakukan dari **mini PC backend**, bukan hanya dari HP.

## Username/password aplikasi gagal

- Pastikan `APP_USERNAME` dan hash `APP_PASSWORD_HASH` di `.env` sesuai.
- Hash dibuat dengan PBKDF2-HMAC-SHA256 seperti pada panduan instalasi; format `salt:digest`.
- Login mock standar `admin` / `admin` hanya jika hash tidak diisi dalam mode mock. Ganti untuk penggunaan nyata.
- Token kedaluwarsa; login kembali. Jangan menghapus/mengubah `JWT_SECRET` ketika service aktif kecuali token lama memang ingin dicabut.

## Data pencarian kosong atau dashboard lama

- Pencarian membaca SQLite, bukan meminta OLT setiap ketikan. Buka menu Sync, jalankan sync penuh/per-PON, dan lihat status job.
- Pastikan backend dapat berkomunikasi dengan OLT. Untuk demo tanpa OLT, aktifkan `OLT_MODE=mock`.
- Periksa database dan izin tulis akun service pada `DATABASE_PATH`.

## Parser tidak cocok dengan firmware

Output CLI ZTE berubah menurut firmware dan konfigurasi. Periksa `backend/app/parsers.py`; kirim sampel yang sudah **disanitasi** untuk memperbaiki regex. Hapus username, password, nomor pelanggan, IP publik, dan data sensitif sebelum berbagi. Sampel yang berguna:

```text
show version-running
show gpon onu uncfg
show gpon onu state
show pon power attenuation gpon-onu_1/1/1:1
```

Kirim keluaran asli apa adanya untuk bagian header/kolom, tetapi ganti nilai identifikasi unik dengan contoh konsisten, misalnya `ZTEG00000001`. Jangan mengirim konfigurasi lengkap atau kata sandi.

Jalankan tes parser setelah mengubah pola:

```bash
cd backend
python -m pytest tests/test_parsers.py -q
```

## Perintah konfigurasi dan keselamatan

Jangan mencoba mengatasi respons “perintah tulis belum diaktifkan” dengan mengirim CLI langsung dari HP. Tinjau template di `app/commands.py`, cocokkan dengan manual/firmware dan uji pada lab. Simpan backup OLT sebelum perubahan. Untuk kegagalan API, lihat `sudo journalctl -u olt-control -f` atau `docker compose logs -f`; redaksi token dan kredensial sebelum membagikan log.
