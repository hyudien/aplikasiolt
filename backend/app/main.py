import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from .olt import create_adapter

DB_PATH = os.getenv("DATABASE_PATH", "./data/olt.db")
DEMO_MODE = os.getenv("OLT_MODE", "mock").lower() == "mock"
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
_password_hash = os.getenv("APP_PASSWORD_HASH", "")
_jwt_secret = os.getenv("JWT_SECRET", "")
_fernet_key = os.getenv("FERNET_KEY", "")
if DEMO_MODE:
    _password_hash = _password_hash or hashlib.pbkdf2_hmac(
        "sha256", b"admin", b"olt-control-mock", 240_000
    ).hex()
    _jwt_secret = _jwt_secret or secrets.token_urlsafe(48)
    _fernet_key = _fernet_key or Fernet.generate_key().decode()
if not DEMO_MODE and (not _password_hash or not _jwt_secret or not _fernet_key):
    raise RuntimeError("APP_PASSWORD_HASH, JWT_SECRET, dan FERNET_KEY wajib diatur di luar mode mock")
TOKEN_SECRET = _jwt_secret.encode()
fernet = Fernet(_fernet_key.encode())
bearer = HTTPBearer(auto_error=False)
adapter = create_adapter()
olt_lock = asyncio.Lock()
active_profile_id: int | None = None


def connect_db():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS olt_connections (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, ip TEXT NOT NULL, port INTEGER NOT NULL,
            username TEXT NOT NULL, password_encrypted TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pons (
            pon TEXT PRIMARY KEY, total INTEGER NOT NULL DEFAULT 0, online INTEGER NOT NULL DEFAULT 0,
            offline INTEGER NOT NULL DEFAULT 0, los INTEGER NOT NULL DEFAULT 0, synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS onts (
            interface TEXT PRIMARY KEY, pon TEXT NOT NULL, onu_id INTEGER, serial TEXT NOT NULL,
            name TEXT DEFAULT '', pppoe_user TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'unknown',
            reason TEXT DEFAULT '', vlan INTEGER, profile TEXT DEFAULT '', mode TEXT DEFAULT '',
            optical_power TEXT, last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
            result TEXT NOT NULL, details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sync_jobs (
            id INTEGER PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL, summary TEXT DEFAULT '',
            started_at TEXT NOT NULL, finished_at TEXT
        );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(olt_connections)")}
        if "active" not in columns:
            db.execute("ALTER TABLE olt_connections ADD COLUMN active INTEGER NOT NULL DEFAULT 0")
        selected = db.execute("SELECT * FROM olt_connections WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if selected is not None:
        global adapter, active_profile_id
        active_profile_id = selected["id"]
        if not DEMO_MODE:
            adapter = create_adapter({
                "OLT_MODE": "zte", "OLT_HOST": selected["ip"], "OLT_PORT": str(selected["port"]),
                "OLT_USERNAME": selected["username"],
                "OLT_PASSWORD": fernet.decrypt(selected["password_encrypted"].encode()).decode(),
            })


@asynccontextmanager
async def lifespan(_app):
    initialize_db()
    yield
    await adapter.close()


app = FastAPI(title="OLT Control API", version="1.0.0", description="API lokal untuk ZTE C320 GPON OLT", lifespan=lifespan)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def issue_token(username: str) -> str:
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({"sub": username, "iat": now, "exp": now + int(os.getenv("ACCESS_TOKEN_MINUTES", "480")) * 60}).encode())
    signing = f"{header}.{payload}".encode()
    return f"{header}.{payload}.{_b64(hmac.new(TOKEN_SECRET, signing, hashlib.sha256).digest())}"


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(401, "Token diperlukan")
    try:
        header, payload, signature = credentials.credentials.split(".")
        signing = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(TOKEN_SECRET, signing, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if claims["exp"] < time.time() or claims["sub"] != APP_USERNAME:
            raise ValueError
        return claims["sub"]
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Token tidak valid atau kedaluwarsa")


def password_matches(candidate: str) -> bool:
    if _password_hash == hashlib.pbkdf2_hmac("sha256", b"admin", b"olt-control-mock", 240_000).hex() and DEMO_MODE:
        return hmac.compare_digest(candidate, "admin")
    try:
        salt, digest = _password_hash.split(":", 1)
        actual = hashlib.pbkdf2_hmac("sha256", candidate.encode(), bytes.fromhex(salt), 240_000).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ip: str = Field(min_length=1, max_length=253)
    port: int = Field(default=23, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("ip")
    @classmethod
    def valid_host(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9.:-]+", value):
            raise ValueError("Alamat host tidak valid")
        return value

    @field_validator("username", "password")
    @classmethod
    def valid_login_text(cls, value):
        if any(char in value for char in "\r\n"):
            raise ValueError("Kredensial tidak boleh berisi baris baru")
        return value


class TestConnectionRequest(ProfileRequest):
    name: str = "Tes koneksi"


class RegisterRequest(BaseModel):
    pon: str = Field(max_length=11, pattern=r"^[0-9]{1,3}/[0-9]{1,3}/[0-9]{1,3}$")
    serial: str = Field(pattern=r"^[A-Za-z0-9]{8,16}$")
    name: str = Field(min_length=1, max_length=64)
    vlan: int = Field(ge=1, le=4094)
    profile: str = Field(min_length=1, max_length=64)
    pppoe_user: str = Field(default="", max_length=64)
    pppoe_password: str = Field(default="", max_length=128)
    mode: Literal["pppoe", "bridge", "hybrid"]

    @field_validator("name", "profile", "pppoe_user", "pppoe_password")
    @classmethod
    def safe_value(cls, value):
        if any(char in value for char in "\r\n;"):
            raise ValueError("Nilai berisi karakter yang tidak diizinkan")
        return value


class ActionRequest(BaseModel):
    confirm: bool = False
    profile: str | None = Field(default=None, max_length=64)
    vlan: int | None = Field(default=None, ge=1, le=4094)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)
    serial: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{8,16}$")
    enabled: bool | None = None


def safe_action_text(value: str | None):
    if value is not None and any(char in value for char in "\r\n;"):
        raise HTTPException(422, "Nilai berisi karakter CLI yang tidak diizinkan")


def log_action(user: str, action: str, target: str, result: str, details: str = ""):
    with connect_db() as db:
        db.execute(
            "INSERT INTO action_logs(username,action,target,result,details,created_at) VALUES(?,?,?,?,?,?)",
            (user, action, target, result, details[:500], datetime.now(timezone.utc).isoformat()),
        )


def load_onts():
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM onts ORDER BY pon,onu_id")]


def get_ont(interface: str):
    ont = next((item for item in load_onts() if item["interface"] == interface), None)
    if ont is None and DEMO_MODE:
        ont = next((item for item in adapter.onts if item["interface"] == interface), None)
    if ont is None:
        raise HTTPException(404, "ONT tidak ditemukan; jalankan sync terlebih dahulu")
    return ont


ENRICH_FIELDS = ("name", "pppoe_user", "vlan", "profile", "mode")


def clean_ont_config(config: dict | None) -> dict:
    """Ambil hanya kolom yang diizinkan dan tidak kosong; password tidak pernah ikut."""
    return {key: config[key] for key in ENRICH_FIELDS if config and config.get(key) not in (None, "")}


def store_ont_config(db, interface: str, config: dict):
    db.execute(
        "UPDATE onts SET name=COALESCE(?,name), pppoe_user=COALESCE(?,pppoe_user), vlan=COALESCE(?,vlan), "
        "profile=COALESCE(?,profile), mode=COALESCE(?,mode) WHERE interface=?",
        (*(config.get(key) for key in ENRICH_FIELDS), interface),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    if not hmac.compare_digest(payload.username, APP_USERNAME) or not password_matches(payload.password):
        raise HTTPException(401, "Username atau password salah")
    return {"access_token": issue_token(payload.username), "token_type": "bearer"}


@app.get("/api/auth/me")
def who_am_i(user: str = Depends(current_user)):
    return {"username": user}


@app.post("/api/olt/test-connection")
async def test_connection(payload: TestConnectionRequest, _user: str = Depends(current_user)):
    if DEMO_MODE:
        return await adapter.test_connection()
    test_adapter = create_adapter({"OLT_MODE": "zte", "OLT_HOST": payload.ip, "OLT_PORT": str(payload.port),
                                   "OLT_USERNAME": payload.username, "OLT_PASSWORD": payload.password})
    try:
        async with olt_lock:
            return await test_adapter.test_connection()
    finally:
        await test_adapter.close()


@app.get("/api/olt/profiles")
def list_profiles(_user: str = Depends(current_user)):
    with connect_db() as db:
        rows = db.execute("SELECT id,name,ip,port,username,active,created_at FROM olt_connections ORDER BY id").fetchall()
        return [{**dict(row), "selected": row["active"] == 1} for row in rows]


@app.post("/api/olt/profiles")
def save_profile(payload: ProfileRequest, user: str = Depends(current_user)):
    encrypted = fernet.encrypt(payload.password.encode()).decode()
    with connect_db() as db:
        cursor = db.execute(
            "INSERT INTO olt_connections(name,ip,port,username,password_encrypted,created_at) VALUES(?,?,?,?,?,?)",
            (payload.name, payload.ip, payload.port, payload.username, encrypted, datetime.now(timezone.utc).isoformat()),
        )
    log_action(user, "save-profile", payload.name, "success")
    return {"id": cursor.lastrowid, "name": payload.name}


@app.post("/api/olt/profiles/{profile_id}/select")
async def select_profile(profile_id: int, user: str = Depends(current_user)):
    global adapter, active_profile_id
    with connect_db() as db:
        row = db.execute("SELECT * FROM olt_connections WHERE id=?", (profile_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Profil OLT tidak ditemukan")
    async with olt_lock:
        if not DEMO_MODE:
            await adapter.close()
            adapter = create_adapter({
                "OLT_MODE": "zte", "OLT_HOST": row["ip"], "OLT_PORT": str(row["port"]),
                "OLT_USERNAME": row["username"],
                "OLT_PASSWORD": fernet.decrypt(row["password_encrypted"].encode()).decode(),
            })
        with connect_db() as db:
            db.execute("UPDATE olt_connections SET active=0")
            db.execute("UPDATE olt_connections SET active=1 WHERE id=?", (profile_id,))
    active_profile_id = profile_id
    log_action(user, "select-profile", row["name"], "success")
    return {"success": True, "id": profile_id, "name": row["name"]}


@app.get("/api/olt/dashboard")
async def dashboard(_user: str = Depends(current_user)):
    onts = await adapter.all_onts() if DEMO_MODE else load_onts()
    counts = {"total": len(onts), "online": 0, "offline": 0, "los": 0}
    pon_counts = {}
    for ont in onts:
        status = ont.get("status", "offline")
        if status == "online":
            counts["online"] += 1
        elif status == "los":
            counts["los"] += 1
        else:
            counts["offline"] += 1
        pon = pon_counts.setdefault(ont["pon"], {"pon": ont["pon"], "total": 0, "online": 0, "offline": 0, "los": 0})
        pon["total"] += 1
        pon[status if status in {"online", "offline", "los"} else "offline"] += 1
    return {**counts, "pons": list(pon_counts.values())}


@app.get("/api/olt/pons")
async def list_pons(_user: str = Depends(current_user)):
    return (await dashboard(_user))["pons"]


@app.get("/api/olt/pons/{pon:path}")
async def pon_detail(pon: str, _user: str = Depends(current_user)):
    if len(pon) > 11 or not re.fullmatch(r"[0-9]{1,3}/[0-9]{1,3}/[0-9]{1,3}", pon):
        raise HTTPException(422, "Format PON tidak valid")
    onts = await adapter.all_onts() if DEMO_MODE else load_onts()
    return {"pon": pon, "onts": [ont for ont in onts if ont["pon"] == pon]}


SEARCH_FIELDS = ("interface", "pon", "onu_id", "serial", "name", "pppoe_user", "status", "reason", "profile", "vlan", "mode")


@app.get("/api/onts/search")
async def search_onts(q: str = Query(min_length=1, max_length=100), _user: str = Depends(current_user)):
    if DEMO_MODE:
        onts = await adapter.all_onts()
        needle = q.casefold()
        return [
            ont for ont in onts
            if needle in " ".join(str(ont.get(k) or "") for k in SEARCH_FIELDS).casefold()
        ][:100]
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = " OR ".join(f"CAST({field} AS TEXT) LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
    with connect_db() as db:
        return [dict(row) for row in db.execute(
            f"SELECT * FROM onts WHERE {where} ORDER BY pon,onu_id LIMIT 100",
            tuple(pattern for _ in SEARCH_FIELDS),
        )]


@app.get("/api/onts/unconfigured")
async def unconfigured(_user: str = Depends(current_user)):
    candidates = await adapter.unconfigured()
    registered = await adapter.all_onts() if DEMO_MODE else load_onts()
    used_ids: dict[str, set[int]] = {}
    for ont in registered:
        used_ids.setdefault(ont["pon"], set()).add(ont.get("onu_id"))
    return [
        {
            **candidate,
            "next_onu_id": next(
                (onu_id for onu_id in range(1, 129) if onu_id not in used_ids.get(candidate["pon"], set())),
                None,
            ),
        }
        for candidate in candidates
    ]


@app.get("/api/onts/{interface:path}")
async def ont_detail(interface: str, _user: str = Depends(current_user)):
    ont = get_ont(interface)
    if not DEMO_MODE and not any(ont.get(key) for key in ("name", "profile", "vlan", "pppoe_user")):
        try:
            async with olt_lock:
                extra = await adapter.ont_config(interface)
            extra = clean_ont_config(extra)
            if extra:
                with connect_db() as db:
                    store_ont_config(db, interface, extra)
                ont = {**ont, **extra}
        except Exception:
            pass
    return ont


@app.post("/api/onts/{interface:path}/refresh")
async def refresh_ont(interface: str, user: str = Depends(current_user)):
    """Perbarui satu ONT dari OLT: status terbaru dan data pelanggan (tanpa password)."""
    get_ont(interface)
    try:
        async with olt_lock:
            states = await adapter.all_onts()
            config = clean_ont_config(await adapter.ont_config(interface))
    except Exception as exc:
        log_action(user, "refresh-ont", interface, "failed", str(exc)[:200])
        raise HTTPException(502, "Gagal membaca data dari OLT") from exc
    state = next((item for item in states if item["interface"] == interface), None)
    with connect_db() as db:
        if state:
            db.execute("UPDATE onts SET status=?,reason=?,last_seen=? WHERE interface=?",
                       (state["status"], state.get("reason", ""), datetime.now(timezone.utc).isoformat(), interface))
        if config:
            store_ont_config(db, interface, config)
    log_action(user, "refresh-ont", interface, "success")
    return get_ont(interface)


@app.get("/api/profiles")
async def olt_profiles(_user: str = Depends(current_user)):
    bandwidth = await adapter.profiles_list()
    if not bandwidth:
        bandwidth = [item.strip() for item in os.getenv("BANDWIDTH_PROFILES", "").split(",") if item.strip()]
    return {"bandwidth": bandwidth, "line": [], "service": []}


@app.post("/api/onts/register")
async def register_ont(payload: RegisterRequest, user: str = Depends(current_user)):
    serial = payload.serial.upper()
    onts = await adapter.all_onts() if DEMO_MODE else load_onts()
    if any(item["serial"].upper() == serial for item in onts):
        raise HTTPException(409, "SN sudah terdaftar")
    if payload.pppoe_user and any(item.get("pppoe_user") == payload.pppoe_user for item in onts):
        raise HTTPException(409, "Username PPPoE sudah digunakan")
    unconfigured = await adapter.unconfigured()
    if not any(item["pon"] == payload.pon and item["serial"].upper() == serial for item in unconfigured):
        raise HTTPException(400, "SN tidak ditemukan pada daftar ONT belum terkonfigurasi")
    if payload.mode in {"pppoe", "hybrid"} and (not payload.pppoe_user or not payload.pppoe_password):
        raise HTTPException(422, "Username dan password PPPoE wajib untuk mode ini")
    pon_onts = [item for item in onts if item["pon"] == payload.pon]
    onu_id = next((number for number in range(1, 129) if number not in {item.get("onu_id") for item in pon_onts}), None)
    if onu_id is None:
        raise HTTPException(409, "PON penuh")
    interface = f"{payload.pon}:{onu_id}"
    created = {"interface": interface, "pon": payload.pon, "onu_id": onu_id, "serial": serial,
               "name": payload.name, "pppoe_user": payload.pppoe_user, "status": "offline",
               "reason": "baru terdaftar", "vlan": payload.vlan, "profile": payload.profile, "mode": payload.mode}
    async with olt_lock:
        if DEMO_MODE:
            adapter.onts.append(created)
            adapter.unconfigured_onts = [item for item in adapter.unconfigured_onts if item["serial"].upper() != serial]
        else:
            # TODO: daftarkan dengan perintah ZTE tervalidasi sebelum mengaktifkan mode produksi.
            raise HTTPException(501, "Registrasi CLI belum diaktifkan: validasi sintaks firmware terlebih dahulu")
    log_action(user, "register", interface, "success", serial)
    return {"success": True, "ont": created, "save_config_required": True}


@app.post("/api/onts/{interface:path}/actions/{action}")
async def ont_action(interface: str, action: str, payload: ActionRequest, user: str = Depends(current_user)):
    supported = {"delete", "attenuation", "change-package", "change-vlan", "change-pppoe",
                 "replace", "remote-on", "remote-off", "reboot"}
    if action not in supported:
        raise HTTPException(404, "Aksi tidak dikenal")
    if action in {"delete", "replace", "reboot"} and not payload.confirm:
        raise HTTPException(422, "Konfirmasi wajib untuk aksi destruktif")
    ont = get_ont(interface)
    safe_action_text(payload.profile)
    safe_action_text(payload.username)
    safe_action_text(payload.password)
    if action == "change-package" and not payload.profile:
        raise HTTPException(422, "Profile wajib diisi")
    if action == "change-vlan" and payload.vlan is None:
        raise HTTPException(422, "VLAN wajib diisi")
    if action == "change-pppoe" and (not payload.username or not payload.password):
        raise HTTPException(422, "Username dan password PPPoE wajib diisi")
    if action == "replace" and not payload.serial:
        raise HTTPException(422, "SN pengganti wajib diisi")
    known_onts = await adapter.all_onts() if DEMO_MODE else load_onts()
    if action == "replace" and any(item["serial"].upper() == payload.serial.upper() for item in known_onts):
        raise HTTPException(409, "SN pengganti sudah terdaftar")
    if action == "change-pppoe" and any(item.get("pppoe_user") == payload.username and item["interface"] != interface for item in known_onts):
        raise HTTPException(409, "Username PPPoE sudah digunakan")
    async with olt_lock:
        if not DEMO_MODE:
            log_action(user, action, interface, "failed", "CLI write belum diimplementasikan")
            raise HTTPException(501, "Aksi tulis CLI belum diaktifkan; validasi perintah pada firmware terlebih dahulu")
        result = await adapter.action(action, ont, payload.model_dump(exclude_none=True))
        if action == "delete":
            with connect_db() as db:
                db.execute("DELETE FROM onts WHERE interface=?", (interface,))
        elif action != "attenuation":
            with connect_db() as db:
                db.execute(
                    """INSERT INTO onts(interface,pon,onu_id,serial,name,pppoe_user,status,reason,vlan,profile,mode,optical_power,last_seen)
                    VALUES(:interface,:pon,:onu_id,:serial,:name,:pppoe_user,:status,:reason,:vlan,:profile,:mode,:optical_power,:last_seen)
                    ON CONFLICT(interface) DO UPDATE SET serial=:serial,name=:name,pppoe_user=:pppoe_user,status=:status,
                    reason=:reason,vlan=:vlan,profile=:profile,mode=:mode,optical_power=:optical_power""",
                    {"name": "", "pppoe_user": "", "reason": "", "vlan": None, "profile": "",
                     "mode": "", "optical_power": None, **ont, "last_seen": datetime.now(timezone.utc).isoformat()},
                )
    log_action(user, action, interface, "success")
    return result


@app.post("/api/olt/save-config")
async def save_config(payload: ActionRequest, user: str = Depends(current_user)):
    if not payload.confirm:
        raise HTTPException(422, "Konfirmasi wajib sebelum menyimpan konfigurasi OLT")
    async with olt_lock:
        if DEMO_MODE:
            await adapter.execute("write")
            result = {"success": True, "message": "Konfigurasi mock disimpan"}
        else:
            result = {"success": False, "message": "Perintah write dinonaktifkan sampai diverifikasi pada firmware"}
    log_action(user, "save-config", "OLT", "success" if result["success"] else "failed")
    if not result["success"]:
        raise HTTPException(501, result["message"])
    return result


@app.post("/api/sync")
async def sync_data(scope: str = "full", user: str = Depends(current_user)):
    if scope != "full" and (
        len(scope) > 11 or not re.fullmatch(r"[0-9]{1,3}/[0-9]{1,3}/[0-9]{1,3}", scope)
    ):
        raise HTTPException(422, "Gunakan scope=full atau nomor PON seperti 1/1/1")
    started = datetime.now(timezone.utc).isoformat()
    with connect_db() as db:
        cursor = db.execute("INSERT INTO sync_jobs(type,status,started_at) VALUES(?,?,?)", (scope, "running", started))
        job_id = cursor.lastrowid
    try:
        async with olt_lock:
            onts = await adapter.all_onts() if DEMO_MODE else await adapter.all_onts()
        if scope != "full":
            onts = [ont for ont in onts if ont["pon"] == scope]
        with connect_db() as db:
            preserved = {
                str(row["serial"]).upper(): clean_ont_config(dict(row))
                for row in db.execute("SELECT serial,name,pppoe_user,vlan,profile,mode FROM onts")
            }
            onts = [
                {**ont, **{k: v for k, v in preserved.get(str(ont["serial"]).upper(), {}).items()
                           if ont.get(k) in (None, "")}}
                for ont in onts
            ]
            if scope == "full":
                db.execute("DELETE FROM onts")
                db.execute("DELETE FROM pons")
            for ont in onts:
                db.execute(
                    """INSERT INTO onts(interface,pon,onu_id,serial,name,pppoe_user,status,reason,vlan,profile,mode,optical_power,last_seen)
                    VALUES(:interface,:pon,:onu_id,:serial,:name,:pppoe_user,:status,:reason,:vlan,:profile,:mode,:optical_power,:last_seen)
                    ON CONFLICT(interface) DO UPDATE SET serial=:serial,name=:name,pppoe_user=:pppoe_user,status=:status,
                    reason=:reason,vlan=:vlan,profile=:profile,mode=:mode,optical_power=:optical_power,last_seen=:last_seen""",
                    {"name": "", "pppoe_user": "", "vlan": None, "profile": "", "mode": "", "optical_power": None,
                     "reason": "", **ont, "last_seen": started},
                )
            for pon in {ont["pon"] for ont in onts}:
                counts = {"online": 0, "offline": 0, "los": 0}
                for ont in onts:
                    if ont["pon"] == pon:
                        counts[ont["status"] if ont["status"] in counts else "offline"] += 1
                db.execute("INSERT OR REPLACE INTO pons(pon,total,online,offline,los,synced_at) VALUES(?,?,?,?,?,?)",
                           (pon, sum(counts.values()), counts["online"], counts["offline"], counts["los"], started))
            summary = json.dumps({"onts": len(onts)})
            db.execute("UPDATE sync_jobs SET status='success',summary=?,finished_at=? WHERE id=?",
                       (summary, datetime.now(timezone.utc).isoformat(), job_id))
        log_action(user, "sync", scope, "success", summary)
        return {"id": job_id, "status": "success", **json.loads(summary)}
    except Exception as exc:
        with connect_db() as db:
            db.execute("UPDATE sync_jobs SET status='failed',summary=?,finished_at=? WHERE id=?",
                       (str(exc)[:500], datetime.now(timezone.utc).isoformat(), job_id))
        log_action(user, "sync", scope, "failed", str(exc))
        raise


enrich_tasks: set[asyncio.Task] = set()
enrich_active: set[str] = set()


async def run_enrich(job_id: int, scope: str, interfaces: list[str]):
    processed = failed = 0
    try:
        for interface in interfaces:
            try:
                async with olt_lock:
                    config = clean_ont_config(await adapter.ont_config(interface))
                if config:
                    with connect_db() as db:
                        store_ont_config(db, interface, config)
                processed += 1
            except Exception:
                failed += 1
            if (processed + failed) % 20 == 0:
                with connect_db() as db:
                    db.execute("UPDATE sync_jobs SET summary=? WHERE id=?",
                               (json.dumps({"total": len(interfaces), "processed": processed, "failed": failed}), job_id))
        status = "success"
    except Exception:
        status = "failed"
    finally:
        enrich_active.discard(scope)
    summary = json.dumps({"total": len(interfaces), "processed": processed, "failed": failed})
    with connect_db() as db:
        db.execute("UPDATE sync_jobs SET status=?,summary=?,finished_at=? WHERE id=?",
                   (status, summary, datetime.now(timezone.utc).isoformat(), job_id))


@app.post("/api/sync/enrich")
async def enrich_data(scope: str = "full", user: str = Depends(current_user)):
    if scope != "full" and not re.fullmatch(r"[0-9]{1,3}/[0-9]{1,3}/[0-9]{1,3}", scope):
        raise HTTPException(422, "Gunakan scope=full atau nomor PON seperti 1/1/1")
    if "full" in enrich_active or scope in enrich_active or (scope == "full" and enrich_active):
        raise HTTPException(409, "Pelengkapan data pelanggan sedang berjalan")
    with connect_db() as db:
        if scope == "full":
            rows = db.execute("SELECT interface FROM onts ORDER BY pon,onu_id").fetchall()
        else:
            rows = db.execute("SELECT interface FROM onts WHERE pon=? ORDER BY onu_id", (scope,)).fetchall()
        interfaces = [row["interface"] for row in rows]
        cursor = db.execute("INSERT INTO sync_jobs(type,status,summary,started_at) VALUES(?,?,?,?)",
                            (f"enrich:{scope}", "running",
                             json.dumps({"total": len(interfaces), "processed": 0, "failed": 0}),
                             datetime.now(timezone.utc).isoformat()))
        job_id = cursor.lastrowid
    enrich_active.add(scope)
    task = asyncio.create_task(run_enrich(job_id, scope, interfaces))
    enrich_tasks.add(task)
    task.add_done_callback(enrich_tasks.discard)
    log_action(user, "enrich", scope, "started", f"{len(interfaces)} ONT")
    return {"id": job_id, "status": "running", "total": len(interfaces)}


@app.get("/api/sync/status")
def sync_status(_user: str = Depends(current_user)):
    with connect_db() as db:
        rows = db.execute("SELECT * FROM sync_jobs ORDER BY id DESC LIMIT 20").fetchall()
        return [dict(row) for row in rows]


@app.get("/api/logs")
def logs(limit: int = Query(default=100, ge=1, le=500), _user: str = Depends(current_user)):
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM action_logs ORDER BY id DESC LIMIT ?", (limit,))]
