# aplikasiolt

## Koneksi ke OLT ZTE melalui SSH

Pastikan klien OpenSSH sudah terpasang dan layanan SSH aktif di OLT. Jalankan:

```sh
python3 connect_olt.py <IP-atau-hostname-OLT> <username-SSH>
```

Contoh:

```sh
python3 connect_olt.py 192.168.1.10 admin
```

OpenSSH akan meminta kata sandi jika diperlukan dan memverifikasi host key
menggunakan konfigurasi SSH Anda. Utilitas ini tidak menyimpan kata sandi.
Gunakan `Ctrl+C` atau perintah logout OLT untuk mengakhiri sesi.