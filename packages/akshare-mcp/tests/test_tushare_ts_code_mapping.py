from akshare_mcp.data_source.quotes import _to_tushare_ts_code


def test_to_tushare_ts_code_market_suffixes():
    assert _to_tushare_ts_code("688981") == "688981.SH"
    assert _to_tushare_ts_code("300308") == "300308.SZ"
    assert _to_tushare_ts_code("920000") == "920000.BJ"
