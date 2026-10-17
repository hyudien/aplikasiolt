"""Template perintah ZTE C320; verifikasi pada firmware dan kartu sebelum produksi."""

SHOW_ONU_STATE = "show gpon onu state"
SHOW_UNCONFIGURED = "show gpon onu uncfg"
SHOW_ATTENUATION = "show pon power attenuation {interface}"
SHOW_DETAIL = "show gpon onu detail-info {interface}"
PON_INTERFACE = "interface gpon-olt_{pon}"
REGISTER_ONU = "onu {onu_id} type {onu_type} sn {serial}"
ONU_INTERFACE = "interface gpon-onu_{interface}"
DELETE_ONU = "no onu {onu_id}"
SAVE_CONFIG = "write"

# TODO: Format service-port, T-CONT/GEM, VLAN, PPPoE, remote management, and
# reboot commands against the exact C320 V2.1.0 release before enabling writes.
