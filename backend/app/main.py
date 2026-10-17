"""FastAPI backend: exposes the OLT operations as simple JSON endpoints and serves the mobile UI."""
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db
from .adapter import OK_PHASES, ValidationError, ZteC320
from .telnet_client import OltCommandError, OltError, TelnetSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("olt.api")

STATIC = Path(__file__).resolve().parent.parent / "static"
olt_lock = threading.Lock()  # one Telnet session at a time; the OLT has few VTY lines


def require_token(x_api_token: Optional[str] = Header(default=None)):
    token = os.environ.get("OLT_APP_TOKEN")
    if token and x_api_token != token:
        raise HTTPException(401, "Invalid or missing X-API-Token")


app = FastAPI(title="OLT Control MVP", dependencies=[Depends(require_token)])


def default_session_factory(s):
    return TelnetSession(s["host"], s["port"], s["username"], s["password"],
                         float(os.environ.get("OLT_CONNECT_TIMEOUT", 8)),
                         float(os.environ.get("OLT_COMMAND_TIMEOUT", 20)))


app.state.session_factory = default_session_factory


@contextmanager
def olt(settings=None):
    settings = settings or db.get_settings()
    if not settings:
        raise HTTPException(400, "OLT connection settings not configured")
    try:
        with olt_lock, app.state.session_factory(settings) as sess:
            yield ZteC320(sess)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except OltCommandError as e:
        raise HTTPException(409, str(e))
    except OltError as e:
        log.error("OLT error: %s", e)
        raise HTTPException(502, str(e))


# ---- models --------------------------------------------------------------
class Conn(BaseModel):
    host: str
    port: int = 23
    username: str
    password: str


class Register(BaseModel):
    pon: str
    onu_id: int
    sn: str
    onu_type: str = "ZTE-F660"
    name: str
    mode: str = "pppoe"
    package: str
    vlan: int
    pppoe_user: Optional[str] = None
    pppoe_pass: Optional[str] = None
    vlan_profile: Optional[str] = None


class Package(BaseModel):
    package: str


class Vlan(BaseModel):
    vlan: int


class Pppoe(BaseModel):
    username: str
    password: str
    vlan: int
    vlan_profile: Optional[str] = None


class Remote(BaseModel):
    enabled: bool


class Replace(BaseModel):
    new_sn: str


# ---- settings / connection -----------------------------------------------
@app.get("/api/settings")
def get_settings():
    s = db.get_settings()
    return {"configured": False} if not s else {"configured": True, "host": s["host"], "port": s["port"],
                                                "username": s["username"]}


@app.put("/api/settings")
def put_settings(c: Conn):
    db.save_settings(c.host, c.port, c.username, c.password)
    return {"ok": True}


@app.post("/api/connection/test")
def test_connection(c: Optional[Conn] = None):
    """Test the posted settings (or the saved ones). Always 200; `connected` tells the result."""
    settings = c.model_dump() if c else db.get_settings()
    if not settings:
        raise HTTPException(400, "OLT connection settings not configured")
    try:
        with olt_lock, app.state.session_factory(settings):
            return {"connected": True, "message": "Connected to OLT"}
    except OltError as e:
        log.warning("Connection test failed: %s", e)
        return {"connected": False, "message": str(e)}


# ---- status / data -------------------------------------------------------
def _is_problem(phase):
    return phase.lower() not in OK_PHASES


@app.get("/api/status")
def status():
    """Live status from the OLT: total connected ONTs and a per-PON summary."""
    with olt() as a:
        states = a.list_states()
    pons = {}
    for r in states:
        p = pons.setdefault(r["pon"], {"pon": r["pon"], "total": 0, "connected": 0, "problems": 0})
        p["total"] += 1
        if _is_problem(r["phase"]):
            p["problems"] += 1
        else:
            p["connected"] += 1
    return {"total": len(states), "connected": sum(p["connected"] for p in pons.values()),
            "problems": sum(p["problems"] for p in pons.values()), "pons": sorted(pons.values(), key=lambda p: p["pon"])}


@app.get("/api/onts")
def onts(pon: str = Query(...)):
    """Live ONT list of one PON (names merged from the synced DB); problem ONTs flagged."""
    with olt() as a:
        states = a.list_states(pon)
    known = {r["ont"]: r for r in db.list_onts(pon)}
    out = []
    for r in states:
        k = known.get(r["ont"], {})
        out.append({**r, "name": k.get("name", ""), "sn": k.get("sn", ""), "pppoe_user": k.get("pppoe_user", ""),
                    "problem": _is_problem(r["phase"])})
    out.sort(key=lambda r: (not r["problem"], r["ont"]))
    return {"pon": pon, "onts": out}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return {"results": db.search(q.strip())}


@app.post("/api/sync")
def sync():
    """Copy ONT data from the OLT into the local DB so search is fast."""
    with olt() as a:
        rows = []
        for r in a.list_states():
            try:
                d = a.ont_detail(r["ont"])
            except OltError as e:
                log.warning("detail failed for %s: %s", r["ont"], e)
                d = {"name": "", "sn": "", "pppoe_user": ""}
            rows.append({"ont": r["ont"], "pon": r["pon"], "name": d["name"], "sn": d["sn"],
                         "pppoe_user": d["pppoe_user"], "phase": r["phase"], "admin_state": r["admin_state"]})
    db.replace_onts(rows)
    log.info("Synced %d ONTs", len(rows))
    return {"synced": len(rows)}


# ---- ONT actions ---------------------------------------------------------
# ONT references contain "/" and ":", so they are passed as ?ont=1/1/1:1 .
@app.get("/api/ont/attenuation")
def attenuation(ont: str):
    with olt() as a:
        return a.attenuation(ont)


@app.delete("/api/ont")
def delete_ont(ont: str):
    with olt() as a:
        a.delete(ont)
    db.delete_ont(ont)
    return {"ok": True}


@app.post("/api/ont/package")
def change_package(ont: str, body: Package):
    with olt() as a:
        a.change_package(ont, body.package)
    return {"ok": True}


@app.post("/api/ont/vlan")
def change_vlan(ont: str, body: Vlan):
    with olt() as a:
        a.change_vlan(ont, body.vlan)
    return {"ok": True}


@app.post("/api/ont/pppoe")
def change_pppoe(ont: str, body: Pppoe):
    with olt() as a:
        a.change_pppoe(ont, body.username, body.password, body.vlan, body.vlan_profile)
    db.set_pppoe_user(ont, body.username)
    return {"ok": True}


@app.post("/api/ont/replace")
def replace_ont(ont: str, body: Replace):
    with olt() as a:
        a.replace(ont, body.new_sn)
    return {"ok": True}


@app.post("/api/ont/remote")
def remote(ont: str, body: Remote):
    with olt() as a:
        a.set_remote(ont, body.enabled)
    return {"ok": True}


@app.post("/api/ont/reboot")
def reboot(ont: str):
    with olt() as a:
        a.reboot(ont)
    return {"ok": True}


@app.post("/api/register")
def register(r: Register):
    with olt() as a:
        ont = a.register(r.pon, r.onu_id, r.sn, r.onu_type, r.name, r.mode, r.package, r.vlan,
                         r.pppoe_user, r.pppoe_pass, r.vlan_profile)
    db.upsert_ont({"ont": ont, "pon": r.pon, "name": r.name, "sn": r.sn,
                   "pppoe_user": r.pppoe_user or "", "phase": "working", "admin_state": "enable"})
    return {"ok": True, "ont": ont}


@app.post("/api/save")
def save():
    with olt() as a:
        a.save()
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
