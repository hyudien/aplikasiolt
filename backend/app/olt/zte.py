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
        tconts = parsers.parse_tcont_indexes(running)
        if not tconts:
            raise RuntimeError("T-CONT ONU tidak ditemukan di konfigurasi OLT")
        sequence = ["configure terminal", commands.ONU_INTERFACE.format(interface=interface)]
        sequence += [commands.set_tcont_profile(index, profile) for index in tconts]
        if upstream:
            gemports = parsers.parse_gemport_indexes(running)
            if not gemports:
                raise RuntimeError("GEM port ONU tidak ditemukan di konfigurasi OLT")
            sequence += [commands.set_gemport_limit(index, upstream, downstream) for index in gemports]
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
        return parsers.parse_unconfigured(await self.execute(commands.SHOW_UNCONFIGURED))

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
