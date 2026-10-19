import os

from .mock import MockOltAdapter
from .zte import ZteC320Adapter


def create_adapter(overrides: dict | None = None):
    values = {**os.environ, **(overrides or {})}
    if values.get("OLT_MODE", "mock").lower() == "mock":
        return MockOltAdapter()
    return ZteC320Adapter(
        values.get("OLT_HOST", "127.0.0.1"),
        int(values.get("OLT_PORT", "23")),
        values.get("OLT_USERNAME", ""),
        values.get("OLT_PASSWORD", ""),
        float(values.get("OLT_TIMEOUT", "8")),
    )
