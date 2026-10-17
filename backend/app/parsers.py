"""Parser keluaran CLI ZTE C320 (sesuaikan dengan sampel firmware lapangan)."""

import re


_STATE_ROW = re.compile(
    r"^\s*(?P<interface>\d+/\d+/\d+:\d+)\s+"
    r"(?P<serial>[A-Za-z0-9]{8,16})\s+"
    r"(?P<state>working|online|offline|los|dying\s+gasp|"
    r"auth\s+fail|unknown)\b(?P<tail>.*)$",
    re.IGNORECASE,
)
_UNCFIG_ROW = re.compile(
    r"^\s*(?P<interface>\d+/\d+/\d+)\s+(?P<serial>[A-Za-z0-9]{8,16})\s*$",
    re.IGNORECASE,
)
_ONU_ID = re.compile(r"(?P<pon>\d+/\d+/\d+):(?P<onu_id>\d+)")


def normalize_state(state: str, reason: str = "") -> tuple[str, str]:
    value = state.strip().lower()
    if value in {"working", "online"}:
        return "online", "working"
    if "los" in value:
        return "los", "LOS"
    if "dying" in value:
        return "offline", "dying gasp"
    if "auth" in value:
        return "offline", "auth failed"
    return "offline", reason.strip() or value or "offline"


def parse_onu_state(output: str) -> list[dict]:
    onts = []
    for line in output.splitlines():
        match = _STATE_ROW.match(line)
        if not match:
            continue
        interface = match.group("interface")
        pon, onu_id = interface.split(":")
        state, reason = normalize_state(match.group("state"), match.group("tail"))
        onts.append({
            "interface": interface,
            "pon": pon,
            "onu_id": int(onu_id),
            "serial": match.group("serial"),
            "status": state,
            "reason": reason,
        })
    return onts


def parse_unconfigured(output: str) -> list[dict]:
    result = []
    for line in output.splitlines():
        match = _UNCFIG_ROW.match(line)
        if match:
            result.append({"pon": match.group("interface"), "serial": match.group("serial").upper()})
    return result


def parse_profiles(output: str) -> list[str]:
    return [
        match.group(1)
        for line in output.splitlines()
        if (match := re.match(r"^\s*(?:\d+\s+)?([A-Za-z][A-Za-z0-9_-]{0,63})\s*$", line))
        and match.group(1).lower() not in {"profile", "name", "index"}
    ]


def parse_pon_id(interface: str) -> tuple[str, int]:
    match = _ONU_ID.fullmatch(interface)
    if not match:
        raise ValueError("Format interface ONT tidak valid")
    return match.group("pon"), int(match.group("onu_id"))
