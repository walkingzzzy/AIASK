from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import akshare_mcp.storage as storage_mod
import akshare_mcp.tools.finance as finance_mod
import akshare_mcp.tools.market.kline as kline_mod
import akshare_mcp.tools.market.quote as quote_mod


class _DummyLimiter:
    def acquire(self):
        return True


class _FinanceDB:
    async def get_financials(self, code, limit=1):
        raise RuntimeError("db unavailable")


class _KlineDB:
    async def get_klines(self, code, **kwargs):
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_get_financials_quality_meta_exposes_fallback_chain(monkeypatch):
    today = date.today().isoformat()
    cached_entries = []

    monkeypatch.setattr(finance_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(finance_mod.cache, "get", lambda key, ttl_seconds: None)
    monkeypatch.setattr(finance_mod.cache, "set", lambda key, value: cached_entries.append((key, value)))
    monkeypatch.setattr(storage_mod, "get_db", lambda: _FinanceDB())
    monkeypatch.setattr(
        finance_mod,
        "_get_financials_tushare",
        lambda code: {
            "code": code,
            "reportDate": today,
            "revenue": 100.0,
            "netProfit": 10.0,
            "roe": 12.5,
            "debtRatio": 35.0,
            "source": "tushare_pro",
        },
    )
    monkeypatch.setattr(finance_mod, "_get_financials_akshare", lambda code: None)
    monkeypatch.setattr(finance_mod, "baostock_client", None)

    result = await finance_mod.get_financials.__wrapped__("600519")

    assert result["success"] is True
    assert result["source"] == "tushare_pro"
    assert result["backend_requested"] == "db.get_financials"
    assert result["backend_used"] == "tushare_pro"
    assert result["source_chain"] == ["db.get_financials", "tushare_pro"]
    assert result["fallback_chain"] == ["db.get_financials", "tushare_pro"]
    assert result["fallback_used"] is True
    assert result["quality_flags"] == ["fallback"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["db.get_financials failed: db unavailable"]

    assert cached_entries
    _, cached_payload = cached_entries[0]
    assert cached_payload["source_chain"] == ["db.get_financials", "tushare_pro"]
    assert cached_payload["fallback_reason"] == ["db.get_financials failed: db unavailable"]
    assert cached_payload["payload"]["source"] == "tushare_pro"


@pytest.mark.asyncio
async def test_get_kline_quality_meta_tracks_db_to_datasource_fallback(monkeypatch):
    today = date.today().isoformat()

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod, "get_db", lambda: _KlineDB())
    monkeypatch.setattr(
        kline_mod.data_source,
        "get_kline",
        lambda code, period, limit: [
            {
                "date": today,
                "open": 10.0,
                "close": 10.5,
                "high": 10.8,
                "low": 9.9,
                "volume": 1000,
                "amount": 2000.0,
                "turnover": 1.2,
                "change_pct": 3.1,
                "source": "data_source",
            }
        ],
    )

    async def _noop_save(code, rows):
        return None

    monkeypatch.setattr(kline_mod, "_async_save_klines_to_db", _noop_save)

    result = await kline_mod.get_kline.__wrapped__("600519", "daily", 5)

    assert result["success"] is True
    assert result["source"] == "data_source"
    assert result["backend_requested"] == "db.get_klines"
    assert result["backend_used"] == "data_source"
    assert result["source_chain"] == ["db.get_klines", "data_source.get_kline"]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["db.get_klines failed: db unavailable"]


def test_get_minute_kline_quality_meta_marks_fallback_source_chain(monkeypatch):
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod.data_source, "is_tdx_available", lambda: False)
    monkeypatch.setattr(
        kline_mod,
        "_get_minute_kline_from_akshare",
        lambda code, minutes, limit: [
            {
                "date": now,
                "open": 10.0,
                "close": 10.2,
                "high": 10.3,
                "low": 9.9,
                "volume": 100,
                "amount": 1000.0,
                "turnover": 0.6,
                "change_pct": 1.5,
                "source": "akshare_minute",
            }
        ],
    )
    monkeypatch.setattr(kline_mod, "_get_minute_kline_from_sina", lambda code, minutes, limit: [])

    result = kline_mod.get_minute_kline.__wrapped__("600519", "5m", 10)

    assert result["success"] is True
    assert result["source"] == "akshare_minute"
    assert result["backend_requested"] == "data_source.get_kline"
    assert result["backend_used"] == "akshare_minute"
    assert result["source_chain"] == ["data_source.get_kline", "akshare.stock_zh_a_hist_min_em"]
    assert result["fallback_used"] is True
    assert result["quality_flags"] == ["fallback"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["data_source.get_kline unavailable"]


@pytest.mark.asyncio
async def test_get_kline_data_quality_meta_keeps_full_attempt_chain(monkeypatch):
    today = date.today()
    start_date = (today - timedelta(days=1)).isoformat()
    end_date = today.isoformat()

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod, "get_db", lambda: _KlineDB())

    def _boom_datasource(code, period, limit):
        raise RuntimeError("ds unavailable")

    monkeypatch.setattr(kline_mod.data_source, "get_kline", _boom_datasource)

    class _DummyAk:
        @staticmethod
        def stock_zh_a_hist(symbol, period, start_date=None, end_date=None, adjust="qfq"):
            return pd.DataFrame(
                [
                    {
                        "日期": end_date[:4] + "-" + end_date[4:6] + "-" + end_date[6:8],
                        "开盘": 10.0,
                        "收盘": 10.6,
                        "最高": 10.8,
                        "最低": 9.8,
                        "成交量": 5000,
                        "成交额": 30000.0,
                        "换手率": 1.1,
                        "涨跌幅": 2.3,
                    }
                ]
            )

    async def _noop_save(code, rows):
        return None

    monkeypatch.setattr(kline_mod, "ak", _DummyAk())
    monkeypatch.setattr(kline_mod, "_async_save_klines_to_db", _noop_save)

    result = await kline_mod.get_kline_data(
        "600519",
        period="daily",
        start_date=start_date,
        end_date=end_date,
        limit=30,
    )

    assert result["success"] is True
    assert result["source"] == "akshare"
    assert result["backend_requested"] == "db.get_klines"
    assert result["backend_used"] == "akshare"
    assert result["source_chain"] == [
        "db.get_klines",
        "data_source.get_kline",
        "akshare.stock_zh_a_hist",
    ]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == [
        "db.get_klines failed: db unavailable",
        "data_source.get_kline failed: ds unavailable",
    ]


def test_get_realtime_quote_quality_meta_tracks_fallback_chain(monkeypatch):
    monkeypatch.setattr(quote_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(quote_mod.data_source, "get_realtime_quote", lambda code: (_ for _ in ()).throw(RuntimeError("ds unavailable")))
    monkeypatch.setattr(
        quote_mod,
        "_get_realtime_quote_akshare",
        lambda code: {
            "code": code,
            "name": "贵州茅台",
            "price": 1500.0,
            "change": 10.0,
            "changePercent": 0.67,
            "open": 1490.0,
            "high": 1510.0,
            "low": 1485.0,
            "preClose": 1490.0,
            "volume": 1000,
            "amount": 1500000.0,
            "source": "akshare",
        },
    )
    monkeypatch.setattr(quote_mod, "_get_quote_sina", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_tencent", lambda code: None)
    monkeypatch.setattr(quote_mod, "_save_quote_nonblocking", lambda payload: None)

    result = quote_mod.get_realtime_quote.__wrapped__("600519")

    assert result["success"] is True
    assert result["source"] == "akshare"
    assert result["backend_requested"] == "data_source"
    assert result["backend_used"] == "akshare"
    assert result["source_chain"] == ["data_source", "akshare"]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["data_source失败: ds unavailable"]


def test_get_realtime_quote_quality_meta_marks_failed_chain(monkeypatch):
    monkeypatch.setattr(quote_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(quote_mod.data_source, "get_realtime_quote", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_realtime_quote_akshare", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_sina", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_tencent", lambda code: None)

    result = quote_mod.get_realtime_quote.__wrapped__("600519")

    assert result["success"] is False
    assert result["source"] == "none"
    assert result["backend_requested"] == "data_source"
    assert result["backend_used"] == "none"
    assert result["source_chain"] == ["data_source", "akshare", "sina", "tencent"]
    assert result["fallback_used"] is True
    assert "failed" in result["quality_flags"]
    assert result["fallback_reason"] == ["所有上游源均返回空数据"]
