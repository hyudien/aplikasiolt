from app.parsers import parse_attenuation, parse_onu_information, parse_onu_state, parse_pon_id, parse_unconfigured


def test_parse_onu_state_recognizes_statuses_and_ignores_headers():
    output = """
      Onu Interface       Serial Number    State
      1/1/1:1              ZTEG00000001    working
      1/1/1:2              ZTEG00000002    LOS
      1/1/2:4              ZTEG00000003    dying gasp
    """
    result = parse_onu_state(output)
    assert [ont["status"] for ont in result] == ["online", "los", "offline"]
    assert result[2]["reason"] == "dying gasp"
    assert result[0]["pon"] == "1/1/1"


def test_parse_unconfigured_ignores_headers_and_normalizes_serial():
    result = parse_unconfigured("PON                SN\n1/1/1 ZTEG0000000a\ninvalid row")
    assert result == [{"pon": "1/1/1", "serial": "ZTEG0000000A"}]


def test_parse_pon_id_rejects_invalid_interface():
    assert parse_pon_id("1/1/2:7") == ("1/1/2", 7)
    try:
        parse_pon_id("bad:1")
    except ValueError as error:
        assert "tidak valid" in str(error)
    else:
        raise AssertionError("interface tidak valid harus ditolak")


def test_parse_onu_information_table():
    output = """
ONU        SN report        LLID  ONU ID  Auth  configuration  State    Offline times
1/1/1:1    ZTEGC0000001     1     1       enable  success      LOS      2
1/1/1:2    ZTEGC0000002     2     2       enable  success      working  0
"""
    result = parse_onu_information(output)
    assert [o["interface"] for o in result] == ["1/1/1:1", "1/1/1:2"]
    assert [o["status"] for o in result] == ["los", "online"]
    assert result[0]["serial"] == "ZTEGC0000001"
    assert result[1]["onu_id"] == 2 and result[1]["pon"] == "1/1/1"
    assert parse_onu_information("ONU  SN report  State\nno rows") == []


RUNNING_SAMPLE = """interface gpon-onu_1/1/1:1\r
  name PUTRI KUS -24\r
  tcont 1 name PPP profile UPto-6M\r
  gemport 1 name PPP tcont 1\r
  gemport 1 traffic-limit upstream Upto-6M downstream Upto-6M\r
  encrypt 1 enable downstream\r
  service-port 1 vport 1 user-vlan 177 vlan 177\r
!\r
end\r
"""

MNG_SAMPLE = """pon-onu-mng gpon-onu_1/1/1:1
  service ServiceName gemport 1 vlan 177
  wan-ip 1 mode pppoe username putri@nombes.net password <REDACTED> vlan-profile TEST_177 host 1
  wan-ip 1 ping-response enable traceroute-response enable
  security-mgmt 1 state enable mode forward
!
"""


def test_parse_onu_running_config():
    from app.parsers import parse_onu_running_config
    assert parse_onu_running_config(RUNNING_SAMPLE) == {"name": "PUTRI KUS -24", "profile": "UPto-6M", "vlan": 177}
    assert parse_onu_running_config("") == {}
    assert parse_onu_running_config("  name   Budi  \n") == {"name": "Budi"}


def test_parse_onu_mng_config_never_returns_password():
    from app.parsers import parse_onu_mng_config
    result = parse_onu_mng_config(MNG_SAMPLE)
    assert result == {"pppoe_user": "putri@nombes.net", "mode": "pppoe", "vlan": 177}
    assert "REDACTED" not in str(result)
    assert parse_onu_mng_config("garbage") == {}


def test_interface_validation_rejects_bad_input():
    import pytest
    from app import commands
    assert commands.show_onu_running("1/1/1:1") == "show running-config interface gpon-onu_1/1/1:1"
    assert commands.show_onu_mng("1/1/1:1") == "show onu running config gpon-onu_1/1/1:1"
    for bad in ("1/1/1", "1/1/1:1; reload", "1/1/1:1\nwrite", "", "a/b/c:d", "1/1/1:1 "):
        with pytest.raises(ValueError):
            commands.show_onu_running(bad)
        with pytest.raises(ValueError):
            commands.show_onu_mng(bad)


def test_parse_attenuation():
    out = "OLT                  ONU                  Attenuation\nup      Rx :-21.397(dbm)   Tx:2.456(dbm)    22.2(dB)\ndown    Tx :4.1(dbm)       Rx:-22.3(dbm)    26.4(dB)\n"
    assert parse_attenuation(out) == "-22.3 dBm"
    assert parse_attenuation("") is None


def test_parse_attenuation_onu_rx_table():
    out = "Onu                  Rx power\n------------------------\ngpon-onu_1/1/1:2    -25.230(dbm)\nZXAN#"
    assert parse_attenuation(out) == "-25.230 dBm"


def test_change_package_zte_sequence():
    import asyncio

    import pytest

    from app.olt.zte import ZteC320Adapter

    sent = []

    class Fake(ZteC320Adapter):
        async def execute(self, command):
            sent.append(command)
            if command.startswith("show running-config"):
                return "interface gpon-onu_1/1/1:5\n  name X\n  tcont 1 name T1 profile 20Mbps\n"
            return "ZXAN(config-if)#"

    result = asyncio.run(Fake("h", 23, "u", "p").change_package("1/1/1:5", "50Mbps"))
    assert result["profile"] == "50Mbps"
    assert sent[1:] == ["configure terminal", "interface gpon-onu_1/1/1:5", "tcont 1 profile 50Mbps", "exit", "exit", "write"]
    with pytest.raises(ValueError):
        asyncio.run(Fake("h", 23, "u", "p").change_package("1/1/1:5", "x;reload"))


def test_parse_attenuation_rejects_implausible_values():
    assert parse_attenuation("down    Tx :6.100(dbm)   Rx:6.000(dbm)   6.0(dB)") is None
    assert parse_attenuation("up      Rx :-29.1(dbm)   Tx:6.0(dbm)    6.0(dB)") is None
    assert parse_attenuation("gpon-onu_1/1/1:5    6.000(dbm)") is None
