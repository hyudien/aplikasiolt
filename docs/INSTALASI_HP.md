# Instalasi aplikasi Android di HP

OLT Control adalah **aplikasi Android native Flutter**, bukan situs web. Aplikasi memerlukan backend FastAPI yang telah berjalan di mini PC. HP dan server harus dapat saling menjangkau.

## Opsi A — Pasang APK dari GitHub Actions

1. Buka repository GitHub `hyudien/aplikasiolt`, pilih tab **Actions**, lalu workflow **Build Android APK** yang berhasil.
2. Pada bagian **Artifacts**, unduh `olt-control-debug-apk` dan ekstrak ZIP.
3. Salin `app-debug.apk` ke HP. Saat diminta, izinkan browser/file manager memasang aplikasi dari sumber ini (**Install unknown apps**). Nyalakan hanya saat memasang APK yang dipercaya, lalu matikan lagi.
4. Buka **OLT Control** dan isi alamat backend, misalnya `http://192.168.1.10:8000`. Jangan tambahkan `/docs`.
5. Login menggunakan username/password backend. Mode mock demo awal: `admin` / `admin`.
6. Buka Setting, masukkan IP, port Telnet, username, dan password OLT; tekan **Tes koneksi** kemudian **Simpan profil**.
7. Tekan Sync penuh dan periksa Dashboard/Cari. Gunakan mock terlebih dahulu sebelum menghubungkan OLT nyata.

APK workflow saat ini adalah debug internal. Untuk berbagi secara rutin, gunakan rilis bertanda tangan dengan keystore yang dijaga privat; jangan simpan keystore/password signing di repository.

## Opsi B — Build APK sendiri

1. Pasang Flutter SDK stable dan Android Studio (termasuk Android SDK, platform tools, dan lisensi SDK). Tambahkan `flutter/bin` ke PATH.
2. Periksa toolchain:

```bash
flutter doctor
```

3. Dari root repository:

```bash
cd mobile
flutter create --platforms=android --org id.hyudien --project-name olt_control .
flutter pub get
flutter analyze
flutter build apk --release
```

4. APK hasil build:
   `mobile/build/app/outputs/flutter-apk/app-release.apk`
5. Dengan USB debugging aktif dan Android Platform Tools terpasang:

```bash
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Atau salin APK ke HP lalu pasang seperti opsi A. Package aplikasi adalah `id.hyudien.olt_control`.

## Mengakses server dari luar LAN

HTTP cleartext hanya untuk jaringan lokal tepercaya, dan kredensial/token berisiko terlihat pada jaringan yang tidak aman. Jangan meneruskan port 8000 ke internet. Untuk pemakaian di luar kantor, sambungkan HP dan mini PC melalui VPN privat seperti WireGuard atau Tailscale. Alternatifnya, pasang HTTPS dengan sertifikat tepercaya pada reverse proxy dan batasi akses memakai firewall.
