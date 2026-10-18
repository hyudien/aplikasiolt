"""Template perintah ZTE C320; verifikasi pada firmware dan kartu sebelum produksi."""

import re

SHOW_ONU_STATE = "show gpon onu state"
SHOW_ONU_INFORMATION = "show pon onu information gpon-olt_{pon}"
SHOW_UNCONFIGURED = "show gpon onu uncfg"
SHOW_ATTENUATION = "show pon power attenuation {interface}"
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
REMOTE_MANAGEMENT = "pon-onu-mng {interface}"
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


def show_onu_mng(interface: str) -> str:
    return SHOW_ONU_MNG.format(interface=validate_interface(interface))

# TODO: Format service-port, T-CONT/GEM, VLAN, PPPoE, remote management, and
# reboot commands against the exact C320 V2.1.0 release before enabling writes.
