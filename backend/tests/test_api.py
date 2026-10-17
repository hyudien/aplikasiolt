import os
import re

import pytest
from fastapi.testclient import TestClient

from app import adapter


class FakeSession:
    log = []

    def __init__(self, settings=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def run(self, cmd, check=True):
        FakeSession.log.append(cmd)
        if cmd == "show gpon onu state":
            return ("OnuIndex Admin State OMCC State Phase State Channel\n"
                    "1/1/1:1 enable enable working ch\n1/1/1:2 enable disable LOS ch\n1/1/2:1 enable enable working ch")
        if cmd.startswith("show gpon onu state gpon-olt_1/1/1"):
            return "1/1/1:1 enable enable working ch\n1/1/1:2 enable disable LOS ch"
        if cmd.startswith("show gpon onu detail-info"):
            n = cmd.split("_")[1]
            return f"Name: Budi{n[-1]}\nSerial number: ZTEG0000000{n[-1]}\n"
        if cmd.startswith("show onu running config"):
            return "wan-ip 1 mode pppoe username user@isp password x"
        if cmd.startswith("show pon power"):
            return "Rx: -21.5 dBm\nTx: 2.1 dBm\nAttenuation: 23.6 dB"
        return ""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OLT_APP_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("OLT_APP_TOKEN", raising=False)
    from app.main import app
    FakeSession.log = []
    app.state.session_factory = lambda s: FakeSession(s)
    c = TestClient(app)
    c.put("/api/settings", json={"host": "10.0.0.1", "port": 23, "username": "u", "password": "p"})
    return c


def test_settings_hide_password(client):
    r = client.get("/api/settings").json()
    assert r["host"] == "10.0.0.1" and "password" not in r


def test_connection_and_failure(client):
    assert client.post("/api/connection/test").json()["connected"] is True
    from app.main import app
    from app.telnet_client import OltConnectionError

    def boom(s):
        raise OltConnectionError("nope")
    app.state.session_factory = boom
    r = client.post("/api/connection/test").json()
    assert r == {"connected": False, "message": "nope"}


def test_status_and_pon(client):
    s = client.get("/api/status").json()
    assert s["total"] == 3 and s["connected"] == 2 and s["problems"] == 1
    r = client.get("/api/onts", params={"pon": "1/1/1"}).json()["onts"]
    assert r[0]["phase"] == "LOS" and r[0]["problem"]


def test_sync_and_search(client):
    assert client.post("/api/sync").json()["synced"] == 3
    r = client.get("/api/search", params={"q": "budi1"}).json()["results"]
    assert len(r) == 2
    assert client.get("/api/search", params={"q": "user@isp"}).json()["results"]
    assert client.get("/api/search", params={"q": "%"}).json()["results"] == []


def test_register_modes_and_commands(client):
    body = {"pon": "1/1/3", "onu_id": 5, "sn": "ZTEG12345678", "name": "Ani", "package": "10M", "vlan": 100,
            "pppoe_user": "ani", "pppoe_pass": "secret"}
    for mode in ("pppoe", "bridge", "hybrid"):
        FakeSession.log = []
        assert client.post("/api/register", json={**body, "mode": mode}).status_code == 200
        joined = "\n".join(FakeSession.log)
        assert "onu 5 type ZTE-F660 sn ZTEG12345678" in joined
        assert ("wan-ip 1 mode pppoe" in joined) == (mode != "bridge")
    assert client.post("/api/register", json={**body, "mode": "x"}).status_code == 422


def test_injection_rejected(client):
    assert client.delete("/api/ont", params={"ont": "1/1/1:1\nreload"}).status_code == 422
    assert client.post("/api/ont/package", params={"ont": "1/1/1:1"}, json={"package": "a\nb"}).status_code == 422


def test_actions_and_save(client):
    o = {"ont": "1/1/1:1"}
    assert client.get("/api/ont/attenuation", params=o).json()["rx_power_dbm"] == -21.5
    assert client.post("/api/ont/vlan", params=o, json={"vlan": 200}).status_code == 200
    assert client.post("/api/ont/reboot", params=o).status_code == 200
    assert client.post("/api/ont/remote", params=o, json={"enabled": False}).status_code == 200
    assert client.post("/api/ont/pppoe", params=o, json={"username": "z", "password": "p", "vlan": 10}).status_code == 200
    assert client.delete("/api/ont", params=o).status_code == 200
    assert client.post("/api/save").status_code == 200 and "write" in FakeSession.log
    assert client.post("/api/ont/replace", params=o, json={"new_sn": "ZTEG00000000"}).status_code == 501


def test_token(client, monkeypatch):
    monkeypatch.setenv("OLT_APP_TOKEN", "t")
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", headers={"X-API-Token": "t"}).status_code == 200
