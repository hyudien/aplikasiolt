import asyncio
import re
import os

import telnetlib3

from .. import commands, parsers
from .base import OltAdapter


class ZteC320Adapter(OltAdapter):
    """Adapter Telnet sederhana; perintah konfigurasi destruktif tetap perlu uji firmware."""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: float = 8):
        self.host, self.port, self.username, self.password = host, port, username, password
        self.timeout = timeout
        self.reader = self.writer = None
        self.lock = asyncio.Lock()

    async def _connect(self):
        if self.reader is not None:
            return
        last_error = None
        for attempt in range(2):
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    telnetlib3.open_connection(host=self.host, port=self.port, connect_minwait=0.1, connect_maxwait=1),
                    timeout=self.timeout,
                )
                break
            except (TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                await self.close()
                if attempt == 1:
                    raise
        if self.reader is None or self.writer is None:
            raise last_error or ConnectionError("Koneksi Telnet gagal")
        await self._read_until_prompt(login=True)
        self.writer.write(self.username + "\n")
        await self._read_until_prompt(login=True)
        self.writer.write(self.password + "\n")
        response = await self._read_until_prompt(login=True)
        if "incorrect" in response.lower() or "failed" in response.lower():
            await self.close()
            raise PermissionError("auth failed")
        self.writer.write("terminal length 0\n")
        await self._read_until_prompt(login=True)

    async def _read_until_prompt(self, login: bool = False) -> str:
        result = ""
        while len(result) < 128_000:
            chunk = await asyncio.wait_for(self.reader.read(4096), timeout=self.timeout)
            if not chunk:
                break
            if "--More--" in chunk and self.writer is not None:
                self.writer.write(" ")
            result += chunk.replace("--More--", "")
            lines = result.rstrip().splitlines()
            # Setelah login hanya "#"/">" yang prompt; ":" bisa ujung echo perintah (mis. gpon-onu_1/1/1:)
            if lines and lines[-1].strip().endswith(("#", ">", ":") if login else ("#", ">")):
                break
        return result

    async def execute(self, command: str) -> str:
        async with self.lock:
            for attempt in range(2):
                try:
                    if self.writer is not None and (self.writer.is_closing() or self.reader.at_eof()):
                        await self.close()
                    await self._connect()
                    self.writer.write(command + "\n")
                    return await self._read_until_prompt()
                except PermissionError:
                    raise
                except Exception:
                    # Koneksi lama kemungkinan sudah ditutup OLT (idle); sambung ulang sekali.
                    await self.close()
                    if attempt == 1:
                        raise

    async def all_onts(self) -> list[dict]:
        onts = parsers.parse_onu_state(await self.execute(commands.SHOW_ONU_STATE))
        if onts:
            return onts
        # Fallback firmware C320: daftar ONU per port PON (slot 1, port 1-16).
        for port in range(1, 17):
            output = await self.execute(commands.SHOW_ONU_INFORMATION.format(pon=f"1/1/{port}"))
            onts.extend(parsers.parse_onu_information(output))
        return onts

    async def ont_config(self, interface: str) -> dict:
        """Baca nama, paket, VLAN, user PPPoE (tanpa password) lewat perintah show read-only."""
        running = parsers.parse_onu_running_config(await self.execute(commands.show_onu_running(interface)))
        mng = parsers.parse_onu_mng_config(await self.execute(commands.show_onu_mng(interface)))
        if "vlan" in running:
            mng.pop("vlan", None)
        return {**running, **mng}

    async def ont_configs_for_pon(self, pon: str, interfaces: list[str]) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for interface in interfaces:
            try:
                results[interface] = await self.ont_config(interface)
            except Exception:
                continue
        return results

    async def attenuation(self, interface: str) -> dict:
        last = ""
        for command in commands.show_attenuation_commands(interface):
            output = await self.execute(command)
            if power := parsers.parse_attenuation(output):
                return {"optical_power": power}
            last = output.strip()
        if re.search(r"invalid|error|unknown|incomplete", last, re.IGNORECASE):
            raise RuntimeError("Perintah redaman ditolak OLT: " + last.splitlines()[-2 if len(last.splitlines()) > 1 else -1][:120])
        return {"optical_power": None}

    async def change_package(self, interface: str, profile: str,
                             upstream: str | None = None, downstream: str | None = None) -> dict:
        """Ganti T-CONT profile dan (opsional) traffic-limit upstream/downstream pada GEM port ONU."""
        commands.validate_interface(interface)
        if bool(upstream) != bool(downstream):
            raise ValueError("Profile upstream dan downstream harus diisi bersamaan")
        running = await self.execute(commands.show_onu_running(interface))
        target = parsers.pick_primary_service(parsers.parse_onu_services(running))
        if target is None:
            raise RuntimeError("T-CONT ONU tidak ditemukan di konfigurasi OLT")
        sequence = ["configure terminal", commands.ONU_INTERFACE.format(interface=interface),
                    commands.set_tcont_profile(target["tcont"], profile)]
        if upstream:
            if not target["gemports"]:
                raise RuntimeError("GEM port untuk T-CONT layanan internet tidak ditemukan")
            sequence += [commands.set_gemport_limit(index, upstream, downstream) for index in target["gemports"]]
        failure = None
        try:
            for command in sequence:
                output = await self.execute(command)
                if parsers.CLI_ERROR.search(output.replace(command, "")):
                    failure = output.strip().splitlines()[-2:-1] or [output.strip()]
                    break
        finally:
            for command in ("exit", "exit"):
                try:
                    await self.execute(command)
                except Exception:
                    break
        if failure is not None:
            raise RuntimeError("OLT menolak perintah paket: " + failure[0][:120])
        await self.execute(commands.SAVE_CONFIG)
        return {"success": True, "message": f"Paket diubah ke {profile}", "profile": profile,
                "upstream": upstream, "downstream": downstream}

    async def change_pppoe(self, interface: str, username: str, password: str) -> dict:
        """Ubah username/password PPPoE pada wan-ip yang sudah ada (indeks diambil dari konfigurasi ONU)."""
        commands.validate_interface(interface)
        mng = await self.execute(commands.show_onu_mng(interface))
        match = re.search(r"\bwan-ip[ \t]+(\d+)[ \t]+mode[ \t]+pppoe\b", mng)
        index = int(match.group(1)) if match else 1
        command = commands.set_pppoe(index, username, password)
        sequence = ["configure terminal", commands.REMOTE_MANAGEMENT.format(interface=interface), command]
        failure = None
        try:
            for item in sequence:
                output = await self.execute(item)
                if parsers.CLI_ERROR.search(output.replace(item, "")):
                    failure = (output.replace(password, "***").strip().splitlines()[-2:-1]
                               or [output.replace(password, "***").strip()])
                    break
        finally:
            for item in ("exit", "exit"):
                try:
                    await self.execute(item)
                except Exception:
                    break
        if failure is not None:
            raise RuntimeError("OLT menolak perintah PPPoE: " + failure[0][:120])
        await self.execute(commands.SAVE_CONFIG)
        return {"success": True, "message": f"PPPoE diubah ke {username}", "pppoe_user": username}

    async def change_vlan(self, interface: str, vlan: int) -> dict:
        """Ubah VLAN pada service-port (interface ONU) dan service (pon-onu-mng) yang sudah ada."""
        commands.validate_interface(interface)
        running = await self.execute(commands.show_onu_running(interface))
        mng = await self.execute(commands.show_onu_mng(interface))
        ports = [commands.set_service_port_vlan(int(m[0]), int(m[1]), vlan) for m in re.findall(
            r"^[ \t]*service-port[ \t]+(\d+)[ \t]+vport[ \t]+(\d+)\b", running, re.MULTILINE)]
        services = [commands.set_service_vlan(m[0], int(m[1]), vlan) for m in re.findall(
            r"^[ \t]*service[ \t]+(\S+)[ \t]+gemport[ \t]+(\d+)[ \t]+vlan[ \t]+\d+", mng, re.MULTILINE)]
        if not ports and not services:
            raise RuntimeError("Service-port/service ONU tidak ditemukan di konfigurasi OLT")
        sequence = ["configure terminal"]
        if ports:
            sequence += [commands.ONU_INTERFACE.format(interface=interface), *ports, "exit"]
        if services:
            sequence += [commands.REMOTE_MANAGEMENT.format(interface=interface), *services, "exit"]
        failure = None
        try:
            for command in sequence:
                output = await self.execute(command)
                if parsers.CLI_ERROR.search(output.replace(command, "")):
                    failure = output.strip().splitlines()[-2:-1] or [output.strip()]
                    break
        finally:
            for command in ("exit",):
                try:
                    await self.execute(command)
                except Exception:
                    break
        if failure is not None:
            raise RuntimeError("OLT menolak perintah VLAN: " + failure[0][:120])
        await self.execute(commands.SAVE_CONFIG)
        return {"success": True, "message": f"VLAN diubah ke {vlan}", "vlan": vlan}

    async def register_ont(self, pon: str, serial: str, name: str, vlan: int, profile: str, mode: str,
                           pppoe_user: str = "", pppoe_password: str = "", vlan_profile: str = "",
                           onu_type: str = "ZTE-F660") -> dict:
        """Daftarkan ONU baru: ONU ID kosong dibaca langsung dari OLT, rollback (`no onu`) bila konfigurasi gagal."""
        output = await self.execute(commands.SHOW_ONU_INFORMATION.format(pon=pon))
        used = {item["onu_id"] for item in parsers.parse_onu_information(output)}
        onu_id = next((n for n in range(1, 129) if n not in used), None)
        if onu_id is None:
            raise RuntimeError("PON penuh")
        interface = f"{pon}:{onu_id}"
        register = commands.register_onu(pon, onu_id, onu_type, serial)
        provision = commands.provision_onu(interface, name, profile, vlan, mode, pppoe_user,
                                           pppoe_password, vlan_profile)
        secrets = [pppoe_password] if pppoe_password else []

        def redact(text: str) -> str:
            for secret in secrets:
                text = text.replace(secret, "***")
            return text

        async def run(sequence: list[str]) -> str | None:
            for command in sequence:
                result = await self.execute(command)
                if parsers.CLI_ERROR.search(result.replace(command, "")):
                    lines = redact(result).strip().splitlines()
                    return (lines[-2:-1] or lines or [""])[0][:120]
            return None

        failure = None
        try:
            failure = await run(register)
            if failure is None:
                failure = await run(provision)
        finally:
            for command in ("exit", "exit"):
                try:
                    await self.execute(command)
                except Exception:
                    break
        if failure is not None:
            try:
                await run(commands.delete_onu(pon, onu_id))
                for command in ("exit", "exit"):
                    await self.execute(command)
            except Exception:
                pass
            raise RuntimeError("OLT menolak perintah registrasi: " + failure)
        await self.execute(commands.SAVE_CONFIG)
        return {"onu_id": onu_id, "interface": interface}

    async def vlan_profiles_list(self) -> list[dict]:
        """Profile VLAN (nama persis + CVLAN) dari OLT; kosong bila tidak terbaca."""
        try:
            return parsers.parse_vlan_profiles(await self.execute(commands.SHOW_VLANS[0]))
        except Exception:
            return []

    async def vlans_list(self) -> list[int]:
        """Daftar VLAN yang terdaftar di OLT (kosong bila tidak terbaca)."""
        for command in commands.SHOW_VLANS:
            try:
                vlans = parsers.parse_vlan_list(await self.execute(command))
            except Exception:
                continue
            if vlans:
                return vlans
        return []

    async def traffic_profiles_list(self) -> list[str]:
        """Daftar traffic profile (untuk gemport upstream/downstream) yang ada di OLT."""
        for command in commands.SHOW_TRAFFIC_PROFILES:
            try:
                names = parsers.parse_tcont_profiles(await self.execute(command))
            except Exception:
                continue
            if names:
                return names
        return []

    async def unconfigured(self) -> list[dict]:
        found = parsers.parse_unconfigured(await self.execute(commands.SHOW_UNCONFIGURED))
        if found:
            return found
        try:
            found = parsers.parse_unconfigured(await self.execute(commands.SHOW_UNCONFIGURED_ALT[0]))
        except Exception:
            found = []
        return found

    async def profiles_list(self) -> list[str]:
        """Daftar T-CONT profile yang ada di OLT (tidak gagal bila perintah tidak didukung)."""
        for command in commands.SHOW_TCONT_PROFILES:
            try:
                names = parsers.parse_tcont_profiles(await self.execute(command))
            except Exception:
                continue
            if names:
                return names
        return []

    async def close(self):
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
            self.writer = None
            self.reader = None
