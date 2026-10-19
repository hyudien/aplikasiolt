# Instalasi backend di mini PC

Backend berjalan di mini PC/server yang dapat menjangkau OLT melalui Telnet. HP dan server harus berada di LAN yang sama, atau terhubung melalui VPN. Langkah ini cocok untuk pemula.

## A. Ubuntu atau Debian Linux (Python)

### 1. Siapkan IP server dan paket

Atur **DHCP reservation/static lease** pada router untuk mini PC supaya alamat server tidak berubah. Catat alamat LAN, misalnya `192.168.1.10`. Hindari mengekspos port API ke internet.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip telnet
python3 --version
```

Gunakan Python 3.11 atau lebih baru. Jika menjalankan Ubuntu lama, pasang Python versi yang didukung distro.

### 2. Ambil kode dan buat virtual environment

```bash
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
cd /opt
git clone https://github.com/hyudien/aplikasiolt.git
cd /opt/aplikasiolt/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### 3. Buat kunci dan hash password aplikasi

Jangan gunakan kunci di bawah ini sebagai nilai literal. Perintah berikut menghasilkan kunci acak dan hash kata sandi yang dipilih. Simpan hasilnya secara privat; jangan kirim file `.env` ke GitHub.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import getpass,hashlib,secrets; p=getpass.getpass('Password login aplikasi: ').encode(); s=secrets.token_hex(16); print(s+':'+hashlib.pbkdf2_hmac('sha256',p,bytes.fromhex(s),240000).hex())"
```

Edit `.env`:

```dotenv
OLT_MODE=mock
APP_USERNAME=teknisi
APP_PASSWORD_HASH=hasil-salt:hasil-hash
JWT_SECRET=hasil-kunci-rahasia-acak
FERNET_KEY=hasil-kunci-fernet
DATABASE_PATH=./data/olt.db
ACCESS_TOKEN_MINUTES=480
OLT_HOST=192.168.1.2
OLT_PORT=23
OLT_USERNAME=username-olt
OLT_PASSWORD=password-olt
OLT_TIMEOUT=8
```

Untuk percobaan, biarkan `OLT_MODE=mock`. Login demo tanpa mengisi hash adalah `admin` / `admin`; jangan gunakan konfigurasi demo ini di jaringan produksi. Untuk mencoba backend nyata, atur `OLT_MODE=zte` dan isi kredensial OLT setelah konektivitas diperiksa. Hash login memakai PBKDF2-HMAC-SHA256; password OLT tersimpan terenkripsi memakai Fernet.

### 4. Jalankan dan uji API

```bash
cd /opt/aplikasiolt/backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

Di terminal lain (ganti alamat jika berbeda):

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"teknisi","password":"PASSWORD_YANG_DIPILIH"}'
```

Buka `http://192.168.1.10:8000/docs` dari browser untuk mencoba endpoint Swagger. Jangan menyalin token ke tiket atau log publik.

### 5. Buka firewall hanya untuk LAN

Sesuaikan subnet `192.168.1.0/24` dengan LAN sendiri:

```bash
sudo ufw allow OpenSSH
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
sudo ufw enable
sudo ufw status
```

Jangan membuat port-forward 8000 dari internet. Untuk akses luar lokasi, gunakan VPN.

### 6. Uji jangkauan Telnet dari mini PC ke OLT

Pertama pastikan IP, port, routing, VLAN, dan ACL manajemen OLT benar. Uji TCP:

```bash
nc -vz 192.168.1.2 23
telnet 192.168.1.2 23
```

Jika `nc` tidak ditemukan, pasang `netcat-openbsd`. Keluar dari sesi Telnet dengan `Ctrl+]`, lalu ketik `quit`. Tes konektivitas tidak membuktikan sintaks CLI aman. Periksa keluaran `show version-running` dan kartu terpasang.

### 7. Jalankan otomatis dengan systemd (opsional)

Buat akun layanan dan pastikan ia dapat membaca `.env` serta menulis database:

```bash
sudo useradd --system --home /opt/aplikasiolt --shell /usr/sbin/nologin oltcontrol
sudo chown -R oltcontrol:oltcontrol /opt/aplikasiolt
sudo cp /opt/aplikasiolt/backend/olt-control.service.example /etc/systemd/system/olt-control.service
sudo systemctl daemon-reload
sudo systemctl enable --now olt-control
sudo systemctl status olt-control
sudo journalctl -u olt-control -f
```

Unit contoh menggunakan WorkingDirectory dan EnvironmentFile `/opt/aplikasiolt/backend`. Pastikan file `.env` hanya dapat dibaca akun layanan dan jangan mengaktifkan `OLT_MODE=zte` sebelum validasi.

### Alternatif: Docker Compose

Pasang Docker Engine dan plugin Compose terlebih dahulu. Dari direktori backend:

```bash
cd /opt/aplikasiolt/backend
cp .env.example .env
# Isi kunci rahasia pada .env, kemudian:
docker compose up -d --build
docker compose logs -f
```

Compose menyimpan SQLite di `backend/data/olt.db` dan memulai ulang container otomatis. Gunakan `.env` yang sama prosedur pengamanan seperti instalasi Python.

## B. Windows 10/11 (alternatif)

1. Pasang Git for Windows dan Python 3.11+ dari python.org, centang **Add Python to PATH**.
2. Buka PowerShell:

```powershell
git clone https://github.com/hyudien/aplikasiolt.git
cd aplikasiolt\backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

3. Jalankan tiga perintah pembuat secret/hash pada bagian Linux (tersedia Python dan paket cryptography setelah pip install), isi `.env`, lalu mulai API:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

4. Izinkan Python/Uvicorn di Windows Defender Firewall hanya pada **Private network**. Uji dari HP dengan `http://IP-WINDOWS:8000/docs`. Untuk uji Telnet, aktifkan Telnet Client di **Turn Windows features on or off**, lalu jalankan `telnet 192.168.1.2 23`.

## Backup, pembaruan, dan mode mock

- Database utama: `backend/data/olt.db` (atau nilai `DATABASE_PATH`). Backup konsisten saat API dihentikan atau pakai SQLite Online Backup API:
  ```bash
  sqlite3 data/olt.db ".backup 'data/olt-backup.db'"
  ```
- Simpan backup konfigurasi OLT secara terpisah sebelum perubahan. Jangan masukkan `.env`, database produksi, atau password ke Git.
- Uji alur aplikasi dengan `OLT_MODE=mock`; mock menyediakan ONT contoh untuk dashboard, cari, aksi, dan registrasi.
- Perbarui kode dengan `git pull`, aktifkan virtual environment, jalankan `pip install -r requirements.txt`, lalu restart service. Backup database dan `.env` sebelum pembaruan.
- Pencarian membaca data SQLite; tekan Sync setelah konfigurasi backend/OLT berubah untuk menyegarkan data.
