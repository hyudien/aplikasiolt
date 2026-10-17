from abc import ABC, abstractmethod


class OltAdapter(ABC):
    @abstractmethod
    async def execute(self, command: str) -> str:
        """Jalankan satu perintah CLI."""

    async def test_connection(self) -> dict:
        try:
            await self.execute("show version-running")
            return {"connected": True, "reason": None}
        except TimeoutError:
            return {"connected": False, "reason": "timeout"}
        except PermissionError:
            return {"connected": False, "reason": "auth failed"}
        except ConnectionRefusedError:
            return {"connected": False, "reason": "telnet refused"}
        except Exception as exc:
            return {"connected": False, "reason": str(exc)}

    @abstractmethod
    async def close(self) -> None:
        pass
