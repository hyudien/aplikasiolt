from app.parsers import parse_onu_state, parse_pon_id, parse_unconfigured


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
