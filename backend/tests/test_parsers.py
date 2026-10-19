from app.parsers import parse_attenuation, parse_tcont_profiles, parse_onu_information, parse_onu_state, parse_pon_id, parse_unconfigured


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
                return "interface gpon-onu_1/1/1:5\n  name X\n  tcont 1 name PPP profile UPto-100M\n  tcont 2 name BRG profile UPto-10M\n  gemport 1 name PPP tcont 1\n  gemport 1 traffic-limit upstream Upto-100M downstream Upto-100M\n  gemport 2 name BRG tcont 2\n  gemport 2 traffic-limit upstream Upto-10M downstream Upto-10M\n"
            return "ZXAN(config-if)#"

    result = asyncio.run(Fake("h", 23, "u", "p").change_package("1/1/1:5", "50Mbps"))
    assert result["profile"] == "50Mbps"
    assert sent[1:] == ["configure terminal", "interface gpon-onu_1/1/1:5", "tcont 1 profile 50Mbps", "exit", "exit", "write"]
    sent.clear()
    asyncio.run(Fake("h", 23, "u", "p").change_package("1/1/1:5", "50Mbps", "UP-50M", "DOWN-50M"))
    assert "gemport 1 traffic-limit upstream UP-50M downstream DOWN-50M" in sent
    assert not any(c.startswith(("tcont 2", "gemport 2")) for c in sent)
    with pytest.raises(ValueError):
        asyncio.run(Fake("h", 23, "u", "p").change_package("1/1/1:5", "x;reload"))


def test_parse_attenuation_rejects_implausible_values():
    assert parse_attenuation("down    Tx :6.100(dbm)   Rx:6.000(dbm)   6.0(dB)") is None
    assert parse_attenuation("up      Rx :-29.1(dbm)   Tx:6.0(dbm)    6.0(dB)") is None
    assert parse_attenuation("gpon-onu_1/1/1:5    6.000(dbm)") is None


def test_parse_tcont_profiles_table_and_prompt():
    out = """show gpon profile tcont
Profile name      Type  FBW    ABW    MBW
--------------------------------------------
default           4     0      0      1000000
20Mbps            4     0      0      20480
50Mbps            4     0      0      51200
ZXAN#"""
    assert parse_tcont_profiles(out) == ["default", "20Mbps", "50Mbps"]
    assert parse_tcont_profiles("Profile name: UP-10M\nType: 4\n") == ["UP-10M"]
    assert parse_tcont_profiles("% Invalid input detected\nZXAN#") == []


def test_parse_profiles_real_olt_format():
    traffic = """ZXAN#show gpon profile traffic
Profile name  :default
  SIR(kbps)            PIR(kbps)            CBS(kbytes)         PBS(kbytes)

 9953280              9953280              default             default


Profile name  :D-50M
  SIR(kbps)            PIR(kbps)

 51200                51200                default             default
"""
    assert parse_tcont_profiles(traffic) == ["default", "D-50M"]
    tcont = "Profile name :default\n Type  FBW(kbps)\n 1     10000   0   0   N/A  N/A\n\nProfile name :10Mbps\n Type FBW\n 1  10240  0  0  N/A  N/A\n"
    assert parse_tcont_profiles(tcont) == ["default", "10Mbps"]


def test_parse_onu_information_wrapped_sn_format():
    output = """ZXAN#show pon onu information gpon-olt_1/1/1
            MAC            LLID                                         Offline
ONU         SN report      ONU ID Auth configuration State              times
-------------------------------------------------------------------------------
1/1/1:1     SN(HWTC070D11F 30     SN(HWTC070D11FF)   LOS                16
            F)
1/1/1:2     SN(ZTEGD4A45D7 35     SN(ZTEGD4A45D7D)   working            0
            D)
1/1/1:7     SN(ZTEGD16500C 1      SN(ZTEGD16500C0)   working            1
"""
    result = parse_onu_information(output)
    assert [o["serial"] for o in result] == ["HWTC070D11FF", "ZTEGD4A45D7D", "ZTEGD16500C0"]
    assert [o["status"] for o in result] == ["los", "online", "online"]


def test_set_pppoe_validation():
    import pytest
    from app import commands
    assert commands.set_pppoe(1, "user@isp", "p4ss") == "wan-ip 1 mode pppoe username user@isp password p4ss"
    for user, pw in (("bad user", "x"), ("u", "has space"), ("u", ""), ("", "x")):
        with pytest.raises(ValueError):
            commands.set_pppoe(1, user, pw)


def test_zte_change_pppoe_sequence_and_redaction():
    import asyncio
    import pytest
    from app.olt.zte import ZteC320Adapter

    class Fake(ZteC320Adapter):
        def __init__(self, reject=False):
            super().__init__("h", 23, "u", "p")
            self.sent, self.reject = [], reject

        async def execute(self, command):
            self.sent.append(command)
            if command.startswith("show onu running"):
                return "wan-ip 2 mode pppoe username old\nZXAN#"
            if self.reject and command.startswith("wan-ip"):
                return command + "\n%Error 20201: Invalid input secretpw\nZXAN#"
            return "ok\nZXAN#"

    fake = Fake()
    asyncio.run(fake.change_pppoe("1/1/1:2", "new", "secretpw"))
    assert "wan-ip 2 mode pppoe username new password secretpw" in fake.sent
    assert fake.sent[-1] == "write"
    fake = Fake(reject=True)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(fake.change_pppoe("1/1/1:2", "new", "secretpw"))
    assert "secretpw" not in str(exc.value)
    assert "write" not in fake.sent


def test_zte_change_vlan_sequence():
    import asyncio
    import pytest
    from app.olt.zte import ZteC320Adapter

    class Fake(ZteC320Adapter):
        def __init__(self, reject=False):
            super().__init__("h", 23, "u", "p")
            self.sent, self.reject = [], reject

        async def execute(self, command):
            self.sent.append(command)
            if command.startswith("show running"):
                return RUNNING_SAMPLE
            if command.startswith("show onu running"):
                return MNG_SAMPLE
            if self.reject and command.startswith("service-port"):
                return "%Error: Invalid input\nZXAN#"
            return "ok\nZXAN#"

    fake = Fake()
    result = asyncio.run(fake.change_vlan("1/1/1:1", 200))
    assert result["vlan"] == 200
    assert "service-port 1 vport 1 user-vlan 200 vlan 200" in fake.sent
    assert "service ServiceName gemport 1 vlan 200" in fake.sent
    assert fake.sent[-1] == "write"
    fake = Fake(reject=True)
    with pytest.raises(RuntimeError):
        asyncio.run(fake.change_vlan("1/1/1:1", 200))
    assert "write" not in fake.sent


def test_parse_vlan_list():
    from app.parsers import parse_vlan_list
    out = "VLAN Name Status\n1 default active\n177 TEST_177 active\nVlan list: 200-202,300\nZXAN#"
    out = out.replace("\\\\n", "\\n")
    assert parse_vlan_list(out) == [1, 177, 200, 201, 202, 300]
    assert parse_vlan_list("no vlan") == []
