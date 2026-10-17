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
        assert client.get("/api/onts/search?q=pelanggan01").json()[0]["serial"] == "ZTEG00000001"

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
        logs = client.get("/api/logs").json()
        assert [entry["action"] for entry in logs][:2] == ["reboot", "register"]
