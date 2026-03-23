from __future__ import annotations

import os
from unittest.mock import MagicMock

import pandas as pd
import pytest

import akshare_mcp.data_source as data_source_mod
from akshare_mcp.tools.market import kline as kline_mod


def test_get_tushare_pro_lazy_loads_env(monkeypatch):
    manager = data_source_mod.data_source
    fake_pro = MagicMock()
    captured: dict[str, str] = {}

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_HTTP_URL", raising=False)
    monkeypatch.setattr(manager, "tushare_token", "", raising=False)
    monkeypatch.setattr(manager, "tushare_http_url", "", raising=False)
    monkeypatch.setattr(manager, "ts_pro", None, raising=False)

    def fake_load_mcp_env(*, override=False, only_prefixes=None, **_kwargs):
        assert override is False
        assert only_prefixes == ("TUSHARE_",)
        os.environ["TUSHARE_TOKEN"] = "lazy-token"
        os.environ["TUSHARE_HTTP_URL"] = "http://tushare-proxy.test"
        return None

    def fake_set_token(token: str):
        captured["set_token"] = token

    def fake_pro_api(token: str):
        captured["pro_api"] = token
        return fake_pro

    monkeypatch.setattr(data_source_mod, "load_mcp_env", fake_load_mcp_env)
    monkeypatch.setattr(data_source_mod.ts, "set_token", fake_set_token)
    monkeypatch.setattr(data_source_mod.ts, "pro_api", fake_pro_api)

    resolved = manager.get_tushare_pro()

    assert resolved is fake_pro
    assert captured == {"set_token": "lazy-token", "pro_api": "lazy-token"}
    assert manager.get_tushare_http_url() == "http://tushare-proxy.test"


@pytest.mark.asyncio
async def test_get_index_kline_prefers_tushare_before_akshare(monkeypatch):
    class _FakeDB:
        async def get_klines(self, code: str, limit: int = 60):
            assert code == "sh000001"
            assert limit == 2
            return []

    class _FakePro:
        def __init__(self):
            self.calls: list[tuple[str, str, str]] = []

        def index_daily(self, *, ts_code: str, start_date: str, end_date: str):
            self.calls.append((ts_code, start_date, end_date))
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260321",
                        "open": 3401.0,
                        "close": 3412.0,
                        "high": 3415.0,
                        "low": 3398.0,
                        "vol": 123456.0,
                        "amount": 654321.0,
                    },
                    {
                        "trade_date": "20260320",
                        "open": 3388.0,
                        "close": 3400.0,
                        "high": 3405.0,
                        "low": 3380.0,
                        "vol": 120000.0,
                        "amount": 640000.0,
                    },
                ]
            )

    fake_pro = _FakePro()

    monkeypatch.setattr(kline_mod, "get_db", lambda: _FakeDB())
    monkeypatch.setattr(kline_mod.data_source, "get_tushare_pro", lambda: fake_pro)
    monkeypatch.setattr(
        kline_mod,
        "_run_with_retry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("AkShare should not be called")),
    )

    response = await kline_mod.get_index_kline("000001", limit=2)

    assert response["success"] is True
    assert fake_pro.calls
    assert [item["date"] for item in response["data"]] == ["2026-03-20", "2026-03-21"]
    assert all(item["source"] == "tushare_index" for item in response["data"])
