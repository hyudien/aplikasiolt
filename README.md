# OLT Control — Registrasi ONT

Aplikasi web ringan berbahasa Indonesia untuk mengirim permintaan registrasi ONT ke API provisioning OLT, termasuk pilihan provisioning OMCI. Tidak memerlukan proses build atau dependensi frontend.

## Menjalankan antarmuka

Sajikan direktori ini dengan web server statis, misalnya:

```sh
python3 -m http.server 8080
```

Buka `http://localhost:8080`. Masukkan endpoint API registrasi yang dapat dijangkau browser (default `/api/onts`), lalu isi nama OLT, port PON, serial number, ONT ID, serta line dan service profile.

## Kontrak adapter OLT

Antarmuka mengirim `POST` JSON ke endpoint yang dipilih. Adapter harus memvalidasi input dan menerjemahkan permintaan ke API/CLI OLT yang sesuai dengan vendor dan model perangkat:

```json
{
  "olt": "OLT-Jakarta-01",
  "pon": "0/1/1",
  "ontId": 1,
  "serial": "ALCLB1234567",
  "lineProfile": "residential-line",
  "serviceProfile": "internet-100m",
  "omciEnabled": true
}
```

Respons HTTP `2xx` berarti adapter menerima permintaan; respons error sebaiknya JSON dengan properti `message`, misalnya `{"message":"Serial number sudah terdaftar"}`. Adapter perlu melaporkan sukses hanya setelah provisioning pada OLT selesai, termasuk status OMCI bila diaktifkan. Antarmuka mencatat permintaan yang diterima API pada browser ini, bukan status operasional ONT yang diverifikasi langsung.

OMCI merupakan mekanisme manajemen antara OLT dan ONT. Karena protokol provisioning dan API berbeda antar-vendor, aplikasi ini tidak mengirim OMCI langsung dan belum menyertakan driver OLT. Integrasi operasional memerlukan adapter untuk vendor/model OLT yang digunakan; tempatkan autentikasi dan otorisasi pada adapter/API sebelum digunakan di jaringan produksi. Endpoint dan riwayat disimpan di `localStorage` browser.