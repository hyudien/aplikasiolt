# Registrasi ONT (Android MVP) — berbasis ONT Unconfigured

Arsitektur: Android app → backend mini PC lokal → OLT ZTE C320 (Telnet).
Teknisi tidak lagi mengetik PON dan SN: keduanya diambil dari daftar ONT *unconfigured* yang sudah terdeteksi OLT.

## 1. Alur singkat
1. Buka **Registrasi** → tampil daftar ONT baru (unconfigured).
2. Tap **Refresh** bila perlu; pilih satu ONT.
3. Form terbuka dengan PON, SN, ONU ID terisi otomatis.
4. Isi: VLAN, profil bandwidth, nama pelanggan, username & password PPPoE (sesuai mode).
5. **Registrasi** → hasil sukses/gagal → opsi **Save Config**.

## 2. Wireframe

### 7a. Daftar ONT Baru (Unconfigured)
```
+--------------------------------+
| Registrasi ONT        [Refresh]|
+--------------------------------+
| ONT baru terdeteksi (3)        |
| Diperbarui: 10 dtk lalu        |
+--------------------------------+
| PON 1/1/1                      |
| SN: ZTEGC1234567               |
| Terdeteksi: 2 menit lalu  [>]  |
+--------------------------------+
| PON 1/1/3                      |
| SN: ZTEGC7654321               |
| Terdeteksi: 15 menit lalu [>]  |
+--------------------------------+
```
Empty state (tidak ada ONT):
```
+--------------------------------+
|   (ikon)                       |
|   Tidak ada ONT baru terdeteksi|
|   Pastikan ONT menyala dan     |
|   kabel fiber terpasang.       |
|   [ REFRESH ]                  |
+--------------------------------+
```
State lain: loading (spinner), error koneksi OLT (pesan + [COBA LAGI]).
Kolom "Terdeteksi" ditampilkan hanya jika OLT menyediakan waktu; jika tidak, tampilkan waktu refresh terakhir.

### 7b. Form Registrasi (dipersingkat)
```
+--------------------------------+
| Registrasi ONT                 |
+--------------------------------+
| PON        1/1/1      (terkunci)|
| SN         ZTEGC1234567 (terkunci)|
| ONU ID     12 (otomatis)       |
+--------------------------------+
| Mode                           |
| (•) PPPoE ( ) Bridge ( ) Hybrid|
| VLAN                           |
| [____________]                 |
| Profil Bandwidth               |
| [ pilih dari daftar v ]        |
| Nama Pelanggan                 |
| [____________]                 |
| PPPoE Username                 |
| [____________]                 |
| PPPoE Password                 |
| [____________]                 |
|                                |
| [ REGISTRASI ]                 |
+--------------------------------+
```
Aturan field per mode:

| Mode   | VLAN | Profil BW | Nama | PPPoE user/pass |
|--------|------|-----------|------|-----------------|
| PPPoE  | ya   | ya        | ya   | ya              |
| Bridge | ya   | ya        | ya   | tidak (disembunyikan) |
| Hybrid | ya   | ya        | ya   | ya (untuk bagian PPPoE) |

- PON & SN read-only. ONU ID read-only, terisi slot kosong terkecil; jika backend gagal menghitung, field ONU ID menjadi editable.
- Jika ONT sudah teregistrasi oleh pihak lain saat submit (konflik), tampilkan error dan kembali ke daftar.

## 3. Spesifikasi API backend

### GET `/api/olt/{olt_id}/unconfigured-onts`
Query opsional: `refresh=true` (paksa baca ulang dari OLT, bukan cache).
```json
{
  "fetched_at": "2026-10-17T10:00:00Z",
  "items": [
    {
      "ref": "1-1-1:ZTEGC1234567",
      "pon": "1/1/1",
      "sn": "ZTEGC1234567",
      "detected_at": "2026-10-17T09:58:00Z",
      "next_onu_id": 12
    }
  ]
}
```
- `ref`: ID stabil `<pon>:<sn>` (pon dengan `/` → `-`) untuk dipakai saat registrasi.
- `detected_at` dan `next_onu_id` boleh `null` bila tidak tersedia.
- Daftar kosong → `items: []` (app menampilkan empty state).

### POST `/api/onts/register`
```json
{
  "olt_id": 1,
  "unconfigured_ref": "1-1-1:ZTEGC1234567",
  "mode": "pppoe",
  "vlan": 100,
  "bandwidth_profile": "20M",
  "customer_name": "Budi Santoso",
  "pppoe_username": "budi01",
  "pppoe_password": "secret"
}
```
- `mode`: `pppoe` | `bridge` | `hybrid`. `pppoe_*` wajib untuk `pppoe` dan `hybrid`, diabaikan untuk `bridge`.
- Tidak ada field `pon`, `sn`, `onu_id` dari klien. Backend menyelesaikan `unconfigured_ref` ke PON + SN dengan membaca ulang daftar unconfigured dari OLT, memastikan ONT masih unconfigured, lalu memilih ONU ID kosong berikutnya pada PON tersebut.
- Respons: `201 {onu_id, pon, sn, status}`; `404` ref tidak lagi ada; `409` sudah teregistrasi / PON penuh; `422` validasi; `502` OLT tidak terjangkau.
- Tindakan tercatat di log aktivitas; konfigurasi tidak otomatis disimpan (gunakan `POST /api/olt/save-config`).

## 4. Adapter OLT (asumsi ZTE C320)
Backend memakai antarmuka adapter agar perbedaan firmware terisolasi:
```
OltAdapter.list_unconfigured() -> [UnconfiguredOnt(pon, sn, detected_at?)]
OltAdapter.next_free_onu_id(pon) -> int | None
OltAdapter.register(pon, sn, onu_id, mode, vlan, bw_profile, name, pppoe?) -> Result
```
Asumsi perintah (harus diverifikasi pada OLT nyata; ZTE C320 firmware V1.x vs V2.x berbeda):
- Unconfigured: `show gpon onu uncfg` (V1.x) / `show pon onu uncfg` (V2.x) — output berisi `OnuIndex` (mis. `gpon-onu_1/1/1:1`) dan `SN`. PON diambil dari OnuIndex.
- ONU ID kosong: dari `show gpon onu state gpon-olt_1/1/1`, ambil ID terkecil 1..128 yang belum dipakai.
- Registrasi: `interface gpon-olt_1/1/1` → `onu <id> type <tipe> sn <SN>`, lalu `interface gpon-onu_1/1/1:<id>` (nama, tcont/gemport sesuai profil bandwidth), dan `service-port` + `pon-onu-mng` (VLAN, PPPoE WAN) sesuai mode.
- Parser dan template perintah disimpan per versi firmware (konfigurasi `firmware: v1|v2`), dengan unit test terhadap contoh output.
- Bila waktu deteksi tidak ada di output, `detected_at` = `null`.

## 5. Perubahan pada dokumen sebelumnya
- Layar #7 "Register ONT" diganti oleh 7a + 7b di atas.
- Alur teknisi #3: buka Registrasi → pilih ONT terdeteksi → isi VLAN, profil, nama, PPPoE → registrasi → save config.
- Daftar API: tambah `GET /api/olt/{olt_id}/unconfigured-onts`; `POST /api/onts/register` memakai body di atas.
- Struktur Flutter: tambah `unconfigured_onts_page.dart`; `register_ont_page.dart` menerima objek ONT terpilih.
