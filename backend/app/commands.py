"""Template perintah ZTE C320; verifikasi pada firmware dan kartu sebelum produksi."""

import re

SHOW_ONU_STATE = "show gpon onu state"
SHOW_ONU_INFORMATION = "show pon onu information gpon-olt_{pon}"
SHOW_TCONT_PROFILES = ("show gpon profile tcont", "show pon profile tcont")
SHOW_TRAFFIC_PROFILES = ("show gpon profile traffic", "show pon profile traffic")
SET_GEMPORT_LIMIT = "gemport {index} traffic-limit upstream {upstream} downstream {downstream}"
SHOW_VLANS = ("show vlan brief", "show vlan", "show vlan all", "show vlan summary", "show running-config")
SHOW_UNCONFIGURED = "show gpon onu uncfg"
SHOW_ATTENUATION = "show pon power attenuation gpon-onu_{interface}"
SHOW_DETAIL = "show gpon onu detail-info {interface}"
PON_INTERFACE = "interface gpon-olt_{pon}"
REGISTER_ONU = "onu {onu_id} type {onu_type} sn {serial}"
ONU_INTERFACE = "interface gpon-onu_{interface}"
SET_NAME = "name {name}"
SET_TCONT = "tcont {index} profile {profile}"
SET_GEMPORT = "gemport {index} tcont {tcont}"
SET_SERVICE_PORT = "service-port {index} vport {vport} user-vlan {vlan} vlan {vlan}"
SET_PPPoE = "wan-ip {index} mode pppoe username {username} password {password}"
SET_VLAN = "vlan port eth_0/1 mode tag vlan {vlan}"
REMOTE_MANAGEMENT = "pon-onu-mng gpon-onu_{interface}"
REBOOT_ONU = "pon-onu-mng {interface} reboot"
DELETE_ONU = "no onu {onu_id}"
SAVE_CONFIG = "write"
SHOW_ONU_RUNNING = "show running-config interface gpon-onu_{interface}"
SHOW_ONU_MNG = "show onu running config gpon-onu_{interface}"

_INTERFACE_RE = re.compile(r"\d{1,3}/\d{1,3}/\d{1,3}:\d{1,3}")


def validate_interface(interface: str) -> str:
    """Tolak interface yang tidak berbentuk x/y/z:n sebelum dipakai membangun perintah CLI."""
    if not isinstance(interface, str) or not _INTERFACE_RE.fullmatch(interface):
        raise ValueError("Interface ONU tidak valid")
    return interface


def show_onu_running(interface: str) -> str:
    return SHOW_ONU_RUNNING.format(interface=validate_interface(interface))


SHOW_ATTENUATION_ALT = (
    "show pon power onu-rx gpon-onu_{interface}",
    "show pon power attenuation gpon-olt_{pon} {onu_id}",
)


def show_attenuation_commands(interface: str) -> list[str]:
    """Perintah redaman yang dicoba berurutan; firmware ZTE berbeda-beda."""
    validate_interface(interface)
    pon, onu_id = interface.split(":")
    # onu-rx menghasilkan satu nilai Rx yang jelas, jadi dicoba lebih dulu.
    return [alt.format(interface=interface, pon=pon, onu_id=onu_id) for alt in SHOW_ATTENUATION_ALT[:1]] + [
        SHOW_ATTENUATION.format(interface=interface)
    ] + [alt.format(interface=interface, pon=pon, onu_id=onu_id) for alt in SHOW_ATTENUATION_ALT[1:]]


_PROFILE_RE = re.compile(r"[A-Za-z0-9_.\-]{1,64}")


def validate_profile(profile: str) -> str:
    if not isinstance(profile, str) or not _PROFILE_RE.fullmatch(profile):
        raise ValueError("Nama profile hanya boleh huruf, angka, titik, garis bawah, dan strip")
    return profile


def set_tcont_profile(index: int, profile: str) -> str:
    return SET_TCONT.format(index=int(index), profile=validate_profile(profile))


def set_gemport_limit(index: int, upstream: str, downstream: str) -> str:
    return SET_GEMPORT_LIMIT.format(
        index=int(index), upstream=validate_profile(upstream), downstream=validate_profile(downstream))


def show_attenuation(interface: str) -> str:
    return SHOW_ATTENUATION.format(interface=validate_interface(interface))


def show_onu_mng(interface: str) -> str:
    return SHOW_ONU_MNG.format(interface=validate_interface(interface))

_PPPOE_USER_RE = re.compile(r"[A-Za-z0-9_.@\-]{1,64}")
_PPPOE_PASSWORD_RE = re.compile(r"[\x21-\x7e]{1,128}")


def set_pppoe(index: int, username: str, password: str) -> str:
    """Bangun perintah wan-ip PPPoE (dijalankan di mode pon-onu-mng); input divalidasi ketat."""
    if not isinstance(username, str) or not _PPPOE_USER_RE.fullmatch(username):
        raise ValueError("Username PPPoE hanya boleh huruf, angka, titik, garis bawah, strip, dan @")
    if not isinstance(password, str) or not _PPPOE_PASSWORD_RE.fullmatch(password):
        raise ValueError("Password PPPoE hanya boleh karakter ASCII tercetak tanpa spasi")
    return SET_PPPoE.format(index=int(index), username=username, password=password)


def set_service_port_vlan(index: int, vport: int, vlan: int) -> str:
    vlan = int(vlan)
    if not 1 <= vlan <= 4094:
        raise ValueError("VLAN harus 1-4094")
    return SET_SERVICE_PORT.format(index=int(index), vport=int(vport), vlan=vlan)


def set_service_vlan(name: str, gemport: int, vlan: int) -> str:
    vlan = int(vlan)
    if not 1 <= vlan <= 4094:
        raise ValueError("VLAN harus 1-4094")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", name or ""):
        raise ValueError("Nama service tidak valid")
    return f"service {name} gemport {int(gemport)} vlan {vlan}"


# TODO: Format service-port, T-CONT/GEM, VLAN, PPPoE, remote management, and
# reboot commands against the exact C320 V2.1.0 release before enabling writes.
