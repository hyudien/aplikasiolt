import asyncio
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
        await self._read_until_prompt()
        self.writer.write(self.username + "\n")
        await self._read_until_prompt()
        self.writer.write(self.password + "\n")
        response = await self._read_until_prompt()
        if "incorrect" in response.lower() or "failed" in response.lower():
            await self.close()
            raise PermissionError("auth failed")
        self.writer.write("terminal length 0\n")
        await self._read_until_prompt()

    async def _read_until_prompt(self) -> str:
        result = ""
        while len(result) < 128_000:
            chunk = await asyncio.wait_for(self.reader.read(4096), timeout=self.timeout)
            if not chunk:
                break
            if "--More--" in chunk and self.writer is not None:
                self.writer.write(" ")
            result += chunk.replace("--More--", "")
            lines = result.rstrip().splitlines()
            if lines and lines[-1].strip().endswith(("#", ">", ":")):
                break
        return result

    async def execute(self, command: str) -> str:
        async with self.lock:
            await self._connect()
            self.writer.write(command + "\n")
            return await self._read_until_prompt()

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
        output = await self.execute(commands.show_attenuation(interface))
        return {"optical_power": parsers.parse_attenuation(output)}

    async def unconfigured(self) -> list[dict]:
        return parsers.parse_unconfigured(await self.execute(commands.SHOW_UNCONFIGURED))

    async def profiles_list(self) -> list[str]:
        # TODO: command profile harus dicocokkan dengan output V2.1.0.
        return []

    async def close(self):
        if self.writer:
            self.writer.close()
            self.writer = None
            self.reader = None
