from fastapi.testclient import TestClient

from app import main


def test_mock_auth_dashboard_search_registration_and_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(main.app) as client:
        assert client.get("/api/olt/dashboard").status_code == 401
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]

        dashboard = client.get("/api/olt/dashboard").json()
        assert dashboard["total"] == 3
        assert dashboard["online"] == 1
        assert dashboard["los"] == 1
        assert client.get("/api/olt/pons/1/1/1").status_code == 200
        assert client.get("/api/onts/search?q=pelanggan01").json()[0]["serial"] == "ZTEG00000001"
        assert client.post(
            "/api/onts/1/1/1:2/actions/change-pppoe",
            json={"username": "pelanggan01", "password": "baru"},
        ).status_code == 409
        candidate = client.get("/api/onts/unconfigured").json()[0]
        assert candidate["next_onu_id"] == 3
        profile = client.post("/api/olt/profiles", json={
            "name": "OLT Uji", "ip": "192.168.1.2", "port": 23, "username": "teknisi", "password": "sandi-uji",
        }).json()
        assert "password" not in client.get("/api/olt/profiles").json()[0]
        assert client.post(f"/api/olt/profiles/{profile['id']}/select").json()["success"] is True
        assert client.get("/api/olt/profiles").json()[0]["selected"] is True

        payload = {
            "pon": "1/1/1", "serial": "ZTEG00000004", "name": "Uji Registrasi", "vlan": 100,
            "profile": "100M", "pppoe_user": "uji04", "pppoe_password": "rahasia", "mode": "pppoe",
        }
        registered = client.post("/api/onts/register", json=payload)
        assert registered.status_code == 200
        assert registered.json()["ont"]["onu_id"] == 3
        assert client.post("/api/onts/register", json=payload).status_code == 409

        interface = registered.json()["ont"]["interface"]
        assert client.post(f"/api/onts/{interface}/actions/reboot", json={}).status_code == 422
        assert client.post(f"/api/onts/{interface}/actions/reboot", json={"confirm": True}).status_code == 200
        assert client.post(f"/api/onts/{interface}/actions/delete", json={"confirm": True}).status_code == 200
        assert client.get(f"/api/onts/{interface}").status_code == 404
        logs = client.get("/api/logs").json()
        assert [entry["action"] for entry in logs][:3] == ["delete", "reboot", "register"]


def test_search_enrich_and_sync_preserve(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test2.db"))
    with TestClient(main.app) as client:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        monkeypatch.setattr(main, "DEMO_MODE", False)
        assert client.post("/api/sync/enrich?scope=bad").status_code == 422
        assert client.post("/api/sync").status_code == 200
        client.post("/api/sync")
        with main.connect_db() as db:
            db.execute("UPDATE onts SET name='',pppoe_user='',vlan=NULL,profile='',mode=''")
        assert client.get("/api/onts/search?q=pelanggan01").json() == []
        job = client.post("/api/sync/enrich?scope=full").json()
        assert job["status"] == "running"
        for _ in range(50):
            status = client.get("/api/sync/status").json()
            if status[0]["status"] != "running":
                break
            time.sleep(0.1)
        assert status[0]["type"] == "enrich:full" and status[0]["status"] == "success"
        assert client.get("/api/onts/search?q=pelanggan01").json()[0]["serial"] == "ZTEG00000001"
        assert client.get("/api/onts/search?q=50m").json()[0]["profile"] == "50M"
        assert client.get("/api/onts/search?q=200").json()[0]["vlan"] == 200
        assert client.get("/api/onts/search?q=ROSE").json() == []
        assert client.get("/api/onts/search?q=rumah uji").json()[0]["interface"] == "1/1/1:2"
        # full sync tidak menghapus data hasil enrich
        mock_ont = main.adapter.onts[0]
        saved = dict(mock_ont)
        for key in ("name", "pppoe_user", "profile", "mode"):
            mock_ont[key] = ""
        mock_ont["vlan"] = None
        client.post("/api/sync")
        mock_ont.update(saved)
        row = client.get("/api/onts/1/1/1:1").json()
        assert row["name"] == "Pelanggan Contoh" and row["vlan"] == 100 and row["profile"] == "100M"
