# Referensi API

Base URL contoh: `http://192.168.1.10:8000`. Swagger interaktif: `/docs`. Semua endpoint `/api/*` memerlukan header `Authorization` berisi token yang diperoleh dari login, kecuali endpoint login. JSON memakai UTF-8. Token dikembalikan oleh login dan masa berlakunya dapat diatur melalui `ACCESS_TOKEN_MINUTES`.

## Autentikasi

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/api/auth/login` | Login: `{ "username": "...", "password": "..." }`; menghasilkan `access_token` |
| GET | `/api/auth/me` | Validasi token dan identitas teknisi |
| GET | `/health` | Pemeriksaan kesehatan server, tanpa token |

## Koneksi dan profil OLT

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/api/olt/test-connection` | Uji Telnet; body `name`, `ip`, `port`, `username`, `password` |
| GET | `/api/olt/profiles` | Daftar profil tanpa password |
| POST | `/api/olt/profiles` | Simpan profil; password dienkripsi di backend |
| POST | `/api/olt/profiles/{id}/select` | Aktifkan profil koneksi |
| POST | `/api/olt/save-config` | Menyimpan konfigurasi; body wajib `{ "confirm": true }` |

Contoh hasil tes: `{ "connected": true, "reason": null }`, atau `connected: false` dengan alasan timeout/auth failed/telnet refused.

## Status, ONT, dan profil

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/api/olt/dashboard` | Jumlah ONT total/online/offline/LOS dan hitungan per PON |
| GET | `/api/olt/pons` | Ringkasan PON |
| GET | `/api/olt/pons/{pon}` | Daftar ONT pada PON, mis. `1/1/1` |
| GET | `/api/onts/search?q=...` | Cari nama, SN, atau username PPPoE dari data tersinkron |
| GET | `/api/onts/unconfigured` | SN yang belum terdaftar dan ONU ID kosong berikutnya per PON |
| GET | `/api/onts/{interface}` | Detail ONT; interface mis. `1/1/1:1` |
| GET | `/api/profiles` | Daftar bandwidth/line/service profile yang tersedia |

## Registrasi dan tindakan

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/api/onts/register` | Registrasi berdasarkan PON dan SN yang terdeteksi |
| POST | `/api/onts/{interface}/actions/{action}` | Aksi pada ONT |

Body registrasi: `pon`, `serial`, `name`, `vlan`, `profile`, `pppoe_user`, `pppoe_password`, `mode` (`pppoe`, `bridge`, `hybrid`). Opsional: `vlan_profile` (nama profile VLAN persis dari `GET /api/vlans`, dipakai pada `wan-ip … vlan-profile`) dan `onu_type` (default env `DEFAULT_ONU_TYPE`, lalu `ZTE-F660`). Pada OLT nyata, ONU ID kosong dibaca langsung dari OLT, konfigurasi dirollback (`no onu`) bila gagal, dan `write` dijalankan otomatis. Username/password PPPoE wajib pada mode PPPoE/Hybrid. Backend menolak SN dan username PPPoE duplikat serta memilih ONU ID kosong.

Aksi yang dikenal: `delete`, `attenuation`, `change-package`, `change-vlan`, `change-pppoe`, `replace`, `remote-on`, `remote-off`, `reboot`. Aksi `delete`, `replace`, dan `reboot` wajib membawa `"confirm": true`. Data tambahan: `profile`, `vlan`, `username`, `password`, atau `serial` sesuai aksi. Nilai diperiksa untuk mencegah karakter CLI berbahaya.

## Sinkronisasi dan audit

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/api/sync?scope=full` | Sinkronisasi penuh ke SQLite |
| POST | `/api/sync?scope=1/1/1` | Sinkronisasi PON tertentu |
| GET | `/api/sync/status` | Status dan riwayat job sync |
| GET | `/api/logs?limit=100` | Log aktivitas teknisi dan hasil aksi |

Semua perubahan melalui endpoint aksi dicatat dengan pengguna, target, status, dan waktu. Backend demo `OLT_MODE=mock` mengembalikan data realistis. Adapter ZTE nyata belum mengaktifkan perintah perubahan konfigurasi sebelum sintaks diverifikasi untuk firmware dan kartu yang dipakai.
