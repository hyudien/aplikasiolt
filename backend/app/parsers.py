"""Parser keluaran CLI ZTE C320 (sesuaikan dengan sampel firmware lapangan)."""

import re


_STATE_ROW = re.compile(
    r"^\s*(?P<interface>\d+/\d+/\d+:\d+)\s+"
    r"(?P<serial>[A-Za-z0-9]{8,16})\s+"
    r"(?P<state>working|online|offline|los|dying\s+gasp|"
    r"auth\s+fail|unknown)\b(?P<tail>.*)$",
    re.IGNORECASE,
)
_INFO_ROW = re.compile(r"^\s*(?P<interface>\d+/\d+/\d+:\d+)\s+(?P<rest>.+?)\s*$")
_INFO_STATE = re.compile(
    r"\b(?P<state>working|online|offline|los|dying\s*gasp|dyinggasp|"
    r"auth\s*fail(?:ed)?|unknown)\b",
    re.IGNORECASE,
)
_SERIAL = re.compile(r"^(?:SN:)?(?P<serial>[A-Za-z0-9]{8,16})(?:\(.*\))?$")
_FULL_SN = re.compile(r"\bSN\(([A-Za-z0-9]{8,16})\)")
_UNCFIG_ROW = re.compile(
    r"^\s*(?:gpon[-_](?:onu|olt)_)?(?P<interface>\d+/\d+/\d+)(?::\d+)?\s+"
    r"(?:\S+\s+)??(?:SN:?\s*)?(?P<serial>[A-Za-z0-9]{8,16})(?:\s+\S+)*\s*$",
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


def parse_onu_information(output: str) -> list[dict]:
    """Parse `show pon onu information gpon-olt_x/x/x` (tabel ONU, SN, ID, Auth, State)."""
    onts = []
    for line in output.splitlines():
        match = _INFO_ROW.match(line)
        if not match:
            continue
        rest = match.group("rest")
        state_match = _INFO_STATE.search(rest)
        if not state_match:
            continue
        interface = match.group("interface")
        pon, onu_id = interface.split(":")
        # Kolom "SN report" bisa terpotong ke baris berikutnya; kolom Auth configuration memuat SN(...) utuh.
        if full_sn := _FULL_SN.search(rest):
            serial = full_sn.group(1).upper()
        else:
            serial_match = _SERIAL.match(rest.split()[0])
            serial = serial_match.group("serial") if serial_match and not _INFO_STATE.fullmatch(rest.split()[0]) else ""
        state, reason = normalize_state(re.sub(r"\s+", " ", state_match.group("state")))
        onts.append({
            "interface": interface,
            "pon": pon,
            "onu_id": int(onu_id),
            "serial": serial,
            "status": state,
            "reason": reason,
        })
    return onts


def parse_unconfigured(output: str) -> list[dict]:
    result = []
    for line in clean_cli(output).splitlines():
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


def parse_onu_running_config(output: str) -> dict:
    """Parse `show running-config interface gpon-onu_x/x/x:y` -> name, profile, vlan."""
    result: dict = {}
    if m := re.search(r"^[ \t]*name[ \t]+(\S.*?)\s*$", output, re.MULTILINE):
        result["name"] = m.group(1)
    if m := re.search(r"^[ \t]*tcont[ \t]+\d+[ \t]+(?:name[ \t]+\S+[ \t]+)?profile[ \t]+(\S+)", output, re.MULTILINE):
        result["profile"] = m.group(1)
    if m := re.search(r"\buser-vlan[ \t]+(\d+)", output):
        result["vlan"] = int(m.group(1))
    return result


_PROMPT = re.compile(r"^\S*[#>]\s*$|^\S+#\s*show\b", re.IGNORECASE)
_HEADER_WORDS = {"profile", "name", "index", "type", "fbw", "abw", "mbw", "id", "total", "show"}


def parse_tcont_profiles(output: str) -> list[str]:
    """Nama profile dari `show gpon profile tcont|traffic` (format `Profile name :X` per blok)."""
    names: list[str] = []
    for m in re.finditer(r"^[ \t]*(?:tcont[ \t]+)?profile[ \t]+name[ \t]*:[ \t]*(\S+)", output, re.IGNORECASE | re.MULTILINE):
        if m.group(1) not in names and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}", m.group(1)):
            names.append(m.group(1))
    if names:
        return names
    # Fallback tabel satu baris per profile: `20Mbps  4  0  0  20480`
    for raw in output.splitlines():
        tokens = raw.split()
        if (len(tokens) > 2 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}", tokens[0]) and not tokens[0].isdigit()
                and tokens[0].lower() not in _HEADER_WORDS and not tokens[0].endswith("#")
                and all(re.fullmatch(r"\d+(?:\.\d+)?", t) for t in tokens[2:]) and tokens[0] not in names):
            names.append(tokens[0])
    return names


def parse_onu_services(output: str) -> list[dict]:
    """T-CONT ONU beserta nama, profile, dan GEM port yang terikat (`gemport N name X tcont M`)."""
    tconts: dict[int, dict] = {}
    for m in re.finditer(r"^[ \t]*tcont[ \t]+(\d+)\b(.*)$", output, re.MULTILINE):
        rest = m.group(2)
        name = re.search(r"\bname[ \t]+(\S+)", rest)
        profile = re.search(r"\bprofile[ \t]+(\S+)", rest)
        if profile:
            tconts[int(m.group(1))] = {"tcont": int(m.group(1)), "name": name.group(1) if name else "",
                                       "profile": profile.group(1), "gemports": []}
    for m in re.finditer(r"^[ \t]*gemport[ \t]+(\d+)\b.*?\btcont[ \t]+(\d+)\b", output, re.MULTILINE):
        entry = tconts.get(int(m.group(2)))
        if entry and int(m.group(1)) not in entry["gemports"]:
            entry["gemports"].append(int(m.group(1)))
    return [tconts[k] for k in sorted(tconts)]


def pick_primary_service(services: list[dict]) -> dict | None:
    """Layanan internet: abaikan T-CONT bridge (nama BRG/BRIDGE), ambil nomor terkecil."""
    internet = [item for item in services if not re.search(r"brg|bridge", item["name"], re.IGNORECASE)]
    candidates = internet or services
    return candidates[0] if candidates else None


def parse_gemport_indexes(output: str) -> list[int]:
    """Nomor GEM port dari running-config ONU (`gemport 1 name G1 tcont 1`), tanpa duplikat."""
    found: list[int] = []
    for m in re.finditer(r"^[ \t]*gemport[ \t]+(\d+)\b", output, re.MULTILINE):
        if int(m.group(1)) not in found:
            found.append(int(m.group(1)))
    return found


def parse_tcont_indexes(output: str) -> list[int]:
    """Ambil nomor T-CONT dari running-config ONU (`tcont 1 name T1 profile 20M`)."""
    return [int(m.group(1)) for m in re.finditer(r"^[ \t]*tcont[ \t]+(\d+)\b.*\bprofile\b", output, re.MULTILINE)]


CLI_ERROR = re.compile(r"%\s*error|invalid|incomplete|unknown command|not exist|fail", re.IGNORECASE)


def _plausible_rx(value: str) -> str | None:
    """Daya terima GPON ONU selalu negatif (sekitar -8 s.d. -40 dBm); nilai lain = salah baca (mis. Tx/dB)."""
    try:
        number = float(value)
    except ValueError:
        return None
    return f"{value} dBm" if -50.0 <= number < 0 else None


def parse_attenuation(output: str) -> str | None:
    """Daya terima di ONU (dBm) dari `show pon power onu-rx` atau `show pon power attenuation`.

    Hanya nilai Rx sisi ONU (baris down) yang dipakai; nilai Tx, dB redaman, dan nilai positif ditolak.
    """
    num = r"(-?\d+(?:\.\d+)?)"
    if m := re.search(r"^[ \t]*gpon-onu_\S+[ \t]+" + num + r"[ \t]*\(?dbm", output, re.IGNORECASE | re.MULTILINE):
        return _plausible_rx(m.group(1))
    for line in output.splitlines():
        if line.strip().lower().startswith("down"):
            # Kolom ONU ada setelah Tx OLT: "down Tx :7.5(dbm) Rx:-25.2(dbm) 32.7(dB)"
            if m := re.search(r"\bRx[ \t]*:[ \t]*" + num + r"[ \t]*\(?dbm", line, re.IGNORECASE):
                return _plausible_rx(m.group(1))
    if m := re.search(r"\bRx[ \t]*power[ \t]*:?[ \t]*" + num + r"[ \t]*\(?dbm", output, re.IGNORECASE):
        return _plausible_rx(m.group(1))
    return None


def parse_onu_mng_config(output: str) -> dict:
    """Parse `show onu running config gpon-onu_x/x/x:y` -> pppoe_user, mode, vlan.

    Password PPPoE sengaja tidak pernah diparse maupun dikembalikan.
    """
    result: dict = {}
    if m := re.search(r"\bwan-ip[ \t]+\d+[ \t]+mode[ \t]+(\w+)", output):
        result["mode"] = m.group(1).lower()
        if result["mode"] == "pppoe" and (u := re.search(
                r"\bwan-ip[ \t]+\d+[ \t]+mode[ \t]+pppoe[ \t]+username[ \t]+(\S+)", output)):
            result["pppoe_user"] = u.group(1)
    if m := re.search(r"\bservice[ \t]+\S+[ \t]+gemport[ \t]+\d+[ \t]+vlan[ \t]+(\d+)", output):
        result["vlan"] = int(m.group(1))
    return result


def parse_vlan_list(output: str) -> list[int]:
    """VLAN terdaftar dari `show vlan brief`: baris `100 name ...` atau daftar `1,100-105`."""
    found: set[int] = set()
    for raw in clean_cli(output).splitlines():
        line = raw.strip()
        if m := re.fullmatch(r"CVLAN[ \t]*:[ \t]*(\d{1,4})", line, re.IGNORECASE):
            if 1 <= int(m.group(1)) <= 4094:
                found.add(int(m.group(1)))
        elif re.fullmatch(r"(?:vlan[ \t]*(?:list)?[ \t]*:?[ \t]*)?\d+(?:-\d+)?(?:[ \t]*,[ \t]*\d+(?:-\d+)?)*", line, re.IGNORECASE) \
                or re.match(r"vlan[ \t]*(?:list)?[ \t]*:", line, re.IGNORECASE):
            for a, b in re.findall(r"(\d+)(?:-(\d+))?", line.split(":", 1)[-1] if ":" in line else line):
                lo, hi = int(a), int(b or a)
                if 1 <= lo <= hi <= 4094 and hi - lo < 4094:
                    found.update(range(lo, hi + 1))
        elif (m := re.match(r"(\d{1,4})[ \t]+\S", line)) and 1 <= int(m.group(1)) <= 4094:
            found.add(int(m.group(1)))
    return sorted(found)


def parse_vlan_profiles(output: str) -> list[dict]:
    """Blok `show gpon onu profile vlan`: nama profile persis seperti di OLT (mis. `vlan-KWL(150)`, `TEST_177`) + CVLAN."""
    profiles: list[dict] = []
    name = None
    for raw in clean_cli(output).splitlines():
        line = raw.strip()
        if m := re.match(r"Profile[ \t]+name[ \t]*:[ \t]*(\S.*?)\s*$", line, re.IGNORECASE):
            name = m.group(1)
        elif name and (m := re.match(r"CVLAN[ \t]*:[ \t]*(\d{1,4})\s*$", line, re.IGNORECASE)):
            if 1 <= int(m.group(1)) <= 4094 and all(p["name"] != name for p in profiles):
                profiles.append({"name": name, "vlan": int(m.group(1))})
            name = None
    return profiles


_CONTROL_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|[\x00-\x08\x0b-\x1f\x7f]")


def clean_cli(output: str) -> str:
    """Buang escape ANSI, backspace, dan karakter kontrol sisa paginasi `--More--`."""
    return _CONTROL_RE.sub("", output.replace("\r\n", "\n").replace("\r", "\n"))
