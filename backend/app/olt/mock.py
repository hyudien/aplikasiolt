from .base import OltAdapter


class MockOltAdapter(OltAdapter):
    def __init__(self):
        self.onts = [
            {"interface": "1/1/1:1", "pon": "1/1/1", "onu_id": 1, "serial": "ZTEG00000001",
             "name": "Pelanggan Contoh", "pppoe_user": "pelanggan01", "status": "online", "reason": "working",
             "vlan": 100, "profile": "100M", "mode": "pppoe", "optical_power": "-21.4 dBm"},
            {"interface": "1/1/1:2", "pon": "1/1/1", "onu_id": 2, "serial": "ZTEG00000002",
             "name": "Rumah Uji LOS", "pppoe_user": "pelanggan02", "status": "los", "reason": "LOS",
             "vlan": 100, "profile": "50M", "mode": "pppoe", "optical_power": "-35.0 dBm"},
            {"interface": "1/1/2:1", "pon": "1/1/2", "onu_id": 1, "serial": "ZTEG00000003",
             "name": "ONT Offline", "pppoe_user": "pelanggan03", "status": "offline", "reason": "dying gasp",
             "vlan": 200, "profile": "20M", "mode": "bridge", "optical_power": None},
        ]
        self.unconfigured_onts = [{"pon": "1/1/1", "serial": "ZTEG00000004"}]
        self.profiles = ["20M", "50M", "100M"]

    async def execute(self, command: str) -> str:
        if command in {"show version-running", "write"}:
            return "ZTE C320 V2.1.0"
        return ""

    async def close(self) -> None:
        return None

    async def test_connection(self) -> dict:
        return {"connected": True, "reason": None}

    async def all_onts(self) -> list[dict]:
        return [dict(ont) for ont in self.onts]

    async def ont_config(self, interface: str) -> dict:
        ont = next((item for item in self.onts if item["interface"] == interface), None)
        if ont is None:
            return {}
        return {key: ont[key] for key in ("name", "pppoe_user", "vlan", "profile", "mode") if ont.get(key)}

    async def attenuation(self, interface: str) -> dict:
        ont = next((item for item in self.onts if item["interface"] == interface), None)
        return {"optical_power": ont.get("optical_power") if ont else None}

    async def unconfigured(self) -> list[dict]:
        return [dict(ont) for ont in self.unconfigured_onts]

    async def profiles_list(self) -> list[str]:
        return list(self.profiles)

    async def action(self, action: str, ont: dict, data: dict | None = None) -> dict:
        data = data or {}
        if action == "delete":
            self.onts = [item for item in self.onts if item["interface"] != ont["interface"]]
        elif action == "replace":
            ont["serial"] = data["serial"].upper()
        elif action in {"change-package", "change-vlan", "change-pppoe"}:
            fields = {
                "change-package": {"profile": data["profile"]},
                "change-vlan": {"vlan": data["vlan"]},
                "change-pppoe": {"pppoe_user": data["username"]},
            }
            ont.update(fields[action])
        elif action == "reboot":
            ont["status"] = "offline"
            ont["reason"] = "rebooting"
        elif action == "attenuation":
            return {"optical_power": ont.get("optical_power")}
        elif action in {"remote-on", "remote-off"}:
            ont["remote_management"] = action == "remote-on"
        return {"success": True, "message": "Aksi berhasil pada adapter mock"}
