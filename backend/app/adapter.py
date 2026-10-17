"""ZTE C320 (GPON) command adapter.

ALL device-specific CLI lives in this file. Command syntax and output formats
differ between C320 firmware versions (V1.x vs V2.x); the commands below follow
the commonly documented V2.x syntax and have NOT been verified against a real
device. Places that need confirmation are marked ASSUMPTION / TODO.

ONT reference format: "<rack>/<slot>/<port>:<onu-id>", e.g. "1/2/3:14".
PON reference format: "<rack>/<slot>/<port>", e.g. "1/2/3".
"""
import re

from .telnet_client import OltError

ONT_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{1,2}:\d{1,3}$")
PON_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{1,2}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.@\-]{1,64}$")      # profiles, names, usernames
SN_RE = re.compile(r"^[A-Za-z0-9]{8,16}$")
VLAN_RE = re.compile(r"^\d{1,4}$")
PASS_RE = re.compile(r"^[^\s\"'\\]{1,64}$")
MODES = ("pppoe", "bridge", "hybrid")

# Phase states that mean "connected"; everything else is highlighted as a problem.
OK_PHASES = {"working"}


class ValidationError(ValueError):
    pass


def check(value, regex, label):
    value = "" if value is None else str(value)
    if not regex.match(value):
        raise ValidationError(f"Invalid {label}: {value!r}")
    return value


def split_ont(ont):
    check(ont, ONT_RE, "ONT reference")
    pon, onu_id = ont.split(":")
    return pon, onu_id


def parse_states(text):
    """Parse `show gpon onu state [gpon-olt_x]` output into dicts."""
    rows = []
    for m in re.finditer(r"(?m)^\s*(\d+/\d+/\d+:\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", text):
        ont, admin, omcc, phase, _ = m.groups()
        rows.append({"ont": ont, "pon": ont.split(":")[0], "admin_state": admin,
                     "omcc_state": omcc, "phase": phase})
    return rows


def parse_detail(text):
    def grab(key):
        m = re.search(rf"(?im)^\s*{key}\s*:\s*(.*?)\s*$", text)
        return m.group(1) if m else ""
    return {"name": grab("Name"), "sn": grab("Serial number"), "description": grab("Description")}


def parse_power(text):
    """Parse `show pon power attenuation` output (ASSUMPTION about layout)."""
    result = {"raw": text}
    for key, rx in (("rx_power_dbm", r"(?i)Rx\s*:?\s*(-?\d+(?:\.\d+)?)"),
                    ("tx_power_dbm", r"(?i)Tx\s*:?\s*(-?\d+(?:\.\d+)?)"),
                    ("attenuation_db", r"(?i)Atten\w*\s*:?\s*(-?\d+(?:\.\d+)?)")):
        m = re.search(rx, text)
        result[key] = float(m.group(1)) if m else None
    return result


class ZteC320:
    """Adapter. `session` needs a `run(cmd)` method (TelnetSession or a test fake)."""

    def __init__(self, session):
        self.s = session

    def _cfg(self, commands):
        """Run commands inside configure terminal, always leaving config mode."""
        self.s.run("configure terminal")
        try:
            for c in commands:
                self.s.run(c)
        finally:
            self.s.run("end", check=False)

    # -- read --------------------------------------------------------------
    def list_states(self, pon=None):
        if pon:
            check(pon, PON_RE, "PON")
            return parse_states(self.s.run(f"show gpon onu state gpon-olt_{pon}"))
        return parse_states(self.s.run("show gpon onu state"))

    def ont_detail(self, ont):
        check(ont, ONT_RE, "ONT reference")
        info = parse_detail(self.s.run(f"show gpon onu detail-info gpon-onu_{ont}"))
        # ASSUMPTION: PPPoE username visible in the ONU running config as "username <x>".
        cfg = self.s.run(f"show onu running config gpon-onu_{ont}", check=False)
        m = re.search(r"(?m)\busername\s+(\S+)", cfg)
        info["pppoe_user"] = m.group(1) if m else ""
        return info

    def attenuation(self, ont):
        check(ont, ONT_RE, "ONT reference")
        return parse_power(self.s.run(f"show pon power attenuation gpon-onu_{ont}"))

    # -- write -------------------------------------------------------------
    def register(self, pon, onu_id, sn, onu_type, name, mode, package, vlan,
                 pppoe_user=None, pppoe_pass=None, vlan_profile=None):
        check(pon, PON_RE, "PON"); check(onu_id, VLAN_RE, "ONU id"); check(sn, SN_RE, "serial number")
        check(onu_type, TOKEN_RE, "ONT type"); check(name, TOKEN_RE, "name"); check(package, TOKEN_RE, "package")
        check(vlan, VLAN_RE, "VLAN")
        if mode not in MODES:
            raise ValidationError(f"Invalid mode: {mode!r} (use pppoe, bridge or hybrid)")
        if mode in ("pppoe", "hybrid"):
            check(pppoe_user, TOKEN_RE, "PPPoE username"); check(pppoe_pass, PASS_RE, "PPPoE password")
        ont = f"{pon}:{onu_id}"
        cmds = [f"interface gpon-olt_{pon}", f"onu {onu_id} type {onu_type} sn {sn}", "exit",
                f"interface gpon-onu_{ont}", f"name {name}", f"description {name}",
                f"tcont 1 name T1 profile {package}", "gemport 1 tcont 1",
                f"service-port 1 vport 1 user-vlan {vlan} vlan {vlan}", "exit",
                f"pon-onu-mng gpon-onu_{ont}", f"service 1 gemport 1 vlan {vlan}"]
        # ASSUMPTION: hybrid = PPPoE WAN (host 1) plus a bridged LAN port (eth_0/1).
        if mode in ("pppoe", "hybrid"):
            cmds.append(self._wan_cmd(vlan, pppoe_user, pppoe_pass, vlan_profile))
        if mode in ("bridge", "hybrid"):
            cmds.append(f"vlan port eth_0/{'2' if mode == 'hybrid' else '1'} mode tag vlan {vlan}")
        cmds.append("exit")
        self._cfg(cmds)
        return ont

    @staticmethod
    def _wan_cmd(vlan, user, password, vlan_profile=None):
        prof = f" vlan-profile {check(vlan_profile, TOKEN_RE, 'vlan profile')}" if vlan_profile else ""
        return f"wan-ip 1 mode pppoe username {user} password {password}{prof} host 1"

    def delete(self, ont):
        pon, onu_id = split_ont(ont)
        self._cfg([f"interface gpon-olt_{pon}", f"no onu {onu_id}", "exit"])

    def change_package(self, ont, package):
        split_ont(ont); check(package, TOKEN_RE, "package")
        self._cfg([f"interface gpon-onu_{ont}", f"tcont 1 profile {package}", "exit"])

    def change_vlan(self, ont, vlan):
        split_ont(ont); check(vlan, VLAN_RE, "VLAN")
        self._cfg([f"interface gpon-onu_{ont}", "no service-port 1",
                   f"service-port 1 vport 1 user-vlan {vlan} vlan {vlan}", "exit",
                   f"pon-onu-mng gpon-onu_{ont}", f"service 1 gemport 1 vlan {vlan}", "exit"])

    def change_pppoe(self, ont, user, password, vlan, vlan_profile=None):
        split_ont(ont); check(user, TOKEN_RE, "PPPoE username"); check(password, PASS_RE, "PPPoE password")
        check(vlan, VLAN_RE, "VLAN")
        self._cfg([f"pon-onu-mng gpon-onu_{ont}", self._wan_cmd(vlan, user, password, vlan_profile), "exit"])

    def set_remote(self, ont, enabled):
        split_ont(ont)
        # ASSUMPTION: "remote ONT" = management access (web) from WAN on the ONT.
        state = "enable" if enabled else "disable"
        self._cfg([f"pon-onu-mng gpon-onu_{ont}", f"security-mgmt 1 state {state} mode forward protocol web", "exit"])

    def reboot(self, ont):
        split_ont(ont)
        # ASSUMPTION: V2.x syntax; some firmware uses "onu reboot" under the pon-onu-mng context.
        self._cfg([f"pon-onu-mng gpon-onu_{ont}", "reboot", "exit"])

    def replace(self, ont, new_sn):
        # TODO: expected flow on C320 is: read current `onu <id> type <T> sn <OLD>` from
        # `interface gpon-olt_<pon>`, then `no onu <id>` + `onu <id> type <T> sn <NEW>`
        # (which usually wipes the per-ONU config, so it must be re-applied from a stored
        # profile). Not implemented until confirmed on a real device.
        raise NotImplementedError("Replace ONT requires device-specific confirmation (see TODO in adapter.py)")

    def save(self):
        # ASSUMPTION: `write` in exec mode; older firmware: `copy running-config startup-config`.
        self.s.run("write")
