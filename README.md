# aplikasiolt

MVP aplikasi kontrol **ZTE C320 (GPON)** lewat **Telnet**, dipakai dari HP.
Arsitektur: `HP (browser/PWA)  →  Backend FastAPI (mini PC lokal)  →  OLT (Telnet)`.

- `backend/app/telnet_client.py` – klien Telnet (stdlib), timeout, logging, error jelas
- `backend/app/adapter.py` – **seluruh perintah CLI ZTE C320** + validasi input (anti command-injection)
- `backend/app/db.py` – SQLite (pengaturan OLT + cache ONT hasil sync)
- `backend/app/main.py` – REST API + menyajikan UI
- `backend/static/index.html` – UI mobile (tanpa build step)

## Menjalankan

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt   # test: requirements-dev.txt
cp .env.example .env && set -a && . ./.env && set +a   # opsional
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Buka `http://<ip-mini-pc>:8000/` dari HP (satu jaringan). Isi IP/port/user/pass OLT di tab **Koneksi**,
tekan **Tes koneksi**, lalu **Sync DB** agar pencarian berfungsi. Test: `cd backend && python -m pytest`.

## Fitur → API

| Fitur | Endpoint |
|---|---|
| Pengaturan / tes koneksi | `GET/PUT /api/settings`, `POST /api/connection/test` |
| Status total + per PON | `GET /api/status`, `GET /api/onts?pon=1/1/1` (ONT LOS/offline disorot) |
| Cari nama/SN/PPPoE | `GET /api/search?q=` (dari DB hasil sync) |
| Redaman | `GET /api/ont/attenuation?ont=1/1/1:1` |
| Hapus / paket / VLAN / PPPoE / remote / reboot | `DELETE /api/ont`, `POST /api/ont/{package,vlan,pppoe,remote,reboot}?ont=` |
| Ganti ONT | `POST /api/ont/replace` → **501 (stub)**, lihat TODO di `adapter.py` |
| Registrasi (pppoe/bridge/hybrid) | `POST /api/register` |
| Save config | `POST /api/save` |
| Sync DB | `POST /api/sync` |

## Asumsi & catatan penting

- Perintah CLI mengikuti sintaks umum C320 V2.x dan **belum diuji ke perangkat nyata**. Format output dan
  perintah berbeda antar firmware; sesuaikan di `adapter.py` (ditandai `ASSUMPTION`/`TODO`). Uji dulu di OLT non-produksi.
- Mode *hybrid* diasumsikan = WAN PPPoE + satu port LAN bridge.
- Password OLT disimpan **plaintext** di SQLite lokal (file dibuat dengan mode 600) dan tidak pernah dikembalikan oleh API.
- Telnet tidak terenkripsi; jalankan hanya di jaringan manajemen lokal. Set `OLT_APP_TOKEN` (header `X-API-Token`)
  dan/atau batasi akses ke port 8000 dengan firewall — isi token di kolom "API token" pada tab Koneksi (disimpan di sessionStorage). Jika token kosong, siapa pun di LAN dapat mengubah pengaturan OLT — selalu gunakan firewall/LAN tepercaya.
- Hanya satu sesi Telnet pada satu waktu (lock) agar tidak menghabiskan sesi VTY OLT.
