from __future__ import annotations

from akshare_mcp.tools.market import helpers as helpers_mod


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_name_map_merges_stock_and_fund_records(monkeypatch):
    helpers_mod._list_cache["data"] = None
    helpers_mod._list_cache["ts"] = 0.0

    payloads = {
        "stock_basic": {
            "code": 0,
            "data": {
                "fields": ["ts_code", "name"],
                "items": [["600519.SH", "贵州茅台"]],
            },
        },
        "fund_basic": {
            "code": 0,
            "data": {
                "fields": ["ts_code", "name"],
                "items": [["511380.SH", "城投债ETF"]],
            },
        },
    }

    def _fake_post(_url, json=None, timeout=15):
        api_name = (json or {}).get("api_name")
        return _FakeResp(payloads[api_name])

    monkeypatch.setattr(helpers_mod.requests, "post", _fake_post)
    monkeypatch.setattr(helpers_mod, "ak", None)

    from akshare_mcp.data_source import data_source

    monkeypatch.setattr(data_source, "get_tushare_http_url", lambda: "https://mock-tushare.local")
    monkeypatch.setattr(data_source, "tushare_token", "test-token")

    name_map = helpers_mod.get_name_map()

    assert name_map["600519"] == "贵州茅台"
    assert name_map["511380"] == "城投债ETF"

