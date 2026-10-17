from app.parsers import parse_onu_information, parse_onu_state, parse_pon_id, parse_unconfigured


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
