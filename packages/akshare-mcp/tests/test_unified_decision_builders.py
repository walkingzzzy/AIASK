"""Focused tests for unified decision builders."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_build_stock_context_degrades_to_market_and_flow_snapshots(monkeypatch):
    from akshare_mcp.services import decision_context_builder as builder

    async def _fake_investment_analysis(code):
        return {"success": False, "error": "analysis_backend_down", "data": None, "cached": False}

    def _fake_stock_info(code):
        return {"success": True, "data": {"code": code, "name": "测试股份", "industry": "白酒", "listDate": "20010101"}}

    def _fake_quote(code):
        return {
            "success": True,
            "cached": False,
            "data": {
                "code": code,
                "name": "测试股份",
                "price": 123.4,
                "changePercent": 1.2,
                "amount": 320000000.0,
                "volume": 560000,
                "open": 121.0,
                "high": 124.0,
                "low": 120.8,
                "preClose": 121.9,
            },
        }

    def _fake_fund_flow(code):
        return {
            "success": True,
            "data": {
                "mainNetInflow": 10000000.0,
                "superLargeNetInflow": 4000000.0,
                "largeNetInflow": 3000000.0,
                "middleNetInflow": -1000000.0,
                "smallNetInflow": -2000000.0,
            },
        }

    def _fake_north(code):
        return {"success": True, "data": {"shares": 1000.0, "ratio": 2.5, "change": 50.0}}

    def _fake_order_book(code):
        return {
            "success": True,
            "data": {
                "bids": [{"price": 123.3, "volume": 12000}],
                "asks": [{"price": 123.5, "volume": 10000}],
            },
        }

    def _fake_industry_chain(keyword=None, chain_id=None):
        return {
            "success": True,
            "data": {
                "chains": [
                    {
                        "id": "liquor",
                        "name": "白酒产业链",
                        "upstream": ["粮食"],
                        "midstream": ["酿造"],
                        "downstream": ["零售"],
                    }
                ]
            },
        }

    monkeypatch.setattr(builder, "get_investment_analysis", _fake_investment_analysis)
    monkeypatch.setattr(builder, "get_stock_info", _fake_stock_info)
    monkeypatch.setattr(builder, "get_realtime_quote", _fake_quote)
    monkeypatch.setattr(builder, "get_stock_fund_flow", _fake_fund_flow)
    monkeypatch.setattr(builder, "get_north_fund_holding", _fake_north)
    monkeypatch.setattr(builder, "get_order_book", _fake_order_book)
    monkeypatch.setattr(builder, "get_industry_chain", _fake_industry_chain)

    payload = await builder.build_stock_context("600519")

    assert payload["market_snapshot"]["price"] == 123.4
    assert payload["fund_flow_snapshot"]["flow_bias"] == "bullish"
    assert payload["industry_chain_snapshot"]["matched"] is True
    assert payload["data_quality"]["degraded"] is True
    assert payload["fallback_reason"]


@pytest.mark.asyncio
async def test_build_stock_context_prefers_latest_realtime_timestamp(monkeypatch):
    from akshare_mcp.services import decision_context_builder as builder
    from akshare_mcp.tools.data_quality import parse_asof_time

    order_book_timestamp = 1775439960000

    async def _fake_investment_analysis(code):
        return {
            "success": True,
            "cached": False,
            "data": {
                "basic_info": {"code": code, "name": "测试股份", "industry": "白酒"},
                "price_context": {"current_price": 123.4, "analysis_date": "2022-03-30"},
                "valuation": {"pe": 18.5},
                "risk": {"volatility_20d": 0.03},
            },
        }

    def _fake_stock_info(code):
        return {"success": True, "data": {"code": code, "name": "测试股份", "industry": "白酒", "listDate": "20010101"}}

    def _fake_quote(code):
        return {
            "success": True,
            "cached": False,
            "asof_time": "2026-04-06T09:45:00+08:00",
            "data": {
                "code": code,
                "name": "测试股份",
                "price": 123.4,
                "changePercent": 1.2,
                "amount": 320000000.0,
                "volume": 560000,
                "open": 121.0,
                "high": 124.0,
                "low": 120.8,
                "preClose": 121.9,
                "data_timestamp": "2026-04-06T09:45:00+08:00",
            },
        }

    def _fake_fund_flow(code):
        return {
            "success": True,
            "data": {
                "mainNetInflow": 10000000.0,
                "superLargeNetInflow": 4000000.0,
                "largeNetInflow": 3000000.0,
                "middleNetInflow": -1000000.0,
                "smallNetInflow": -2000000.0,
                "tradeDate": "2026-04-05",
            },
        }

    def _fake_north(code):
        return {"success": True, "data": {"shares": 1000.0, "ratio": 2.5, "change": 50.0}}

    def _fake_order_book(code):
        return {
            "success": True,
            "data": {
                "bids": [{"price": 123.3, "volume": 12000}],
                "asks": [{"price": 123.5, "volume": 10000}],
                "timestamp": order_book_timestamp,
            },
        }

    def _fake_industry_chain(keyword=None, chain_id=None):
        return {
            "success": True,
            "data": {
                "chains": [
                    {
                        "id": "liquor",
                        "name": "白酒产业链",
                        "upstream": ["粮食"],
                        "midstream": ["酿造"],
                        "downstream": ["零售"],
                    }
                ]
            },
        }

    monkeypatch.setattr(builder, "get_investment_analysis", _fake_investment_analysis)
    monkeypatch.setattr(builder, "get_stock_info", _fake_stock_info)
    monkeypatch.setattr(builder, "get_realtime_quote", _fake_quote)
    monkeypatch.setattr(builder, "get_stock_fund_flow", _fake_fund_flow)
    monkeypatch.setattr(builder, "get_north_fund_holding", _fake_north)
    monkeypatch.setattr(builder, "get_order_book", _fake_order_book)
    monkeypatch.setattr(builder, "get_industry_chain", _fake_industry_chain)
    monkeypatch.setattr(
        builder,
        "_build_evidence",
        lambda _context: ([{"signal": "stub"}], ["实时盘口活跃"], [], "buy", "建议继续跟踪"),
    )

    payload = await builder.build_stock_context("600519")
    expected = parse_asof_time(order_book_timestamp).isoformat()

    assert payload["updated_at"] == expected
    assert payload["analysis_date"] == expected
    assert payload["updated_at"] != "2022-03-30T00:00:00+08:00"


@pytest.mark.asyncio
async def test_build_quant_context_exposes_probability_targets_and_oos(monkeypatch):
    from akshare_mcp.services import decision_quant_builder as builder

    class _DummyDb:
        async def get_klines(self, code, limit=260):
            return [
                {
                    "date": f"2026-01-{day:02d}",
                    "close": 100 + day * 0.6,
                    "volume": 100000 + day * 1000,
                }
                for day in range(1, 180)
            ]

        async def get_stock_info(self, code):
            return {"industry": "白酒"}

    async def _fake_fetch_peer_codes(db, code, industry):
        return (["000858", "002304", "000596"], ["600809", "603589"])

    async def _fake_oos(*args, **kwargs):
        return {
            "success": True,
            "data": {
                "validation_report": {
                    "walk_forward": {"stability_ratio": 0.66, "oos_rank_ic_mean": 0.09},
                    "bootstrap_ci": {"ci_lower": 0.02, "ci_upper": 0.11, "sample_size": 88},
                }
            },
        }

    monkeypatch.setattr(builder, "get_db", lambda: _DummyDb())
    monkeypatch.setattr(builder, "_fetch_peer_codes", _fake_fetch_peer_codes)
    monkeypatch.setattr(builder, "run_factor_oos_validation", _fake_oos)

    payload = await builder.build_quant_context("600519")

    assert "conditional_returns" in payload
    assert "similar_patterns" in payload
    assert "oos_validation" in payload
    assert "probability_targets" in payload and "10d" in payload["probability_targets"]
    assert payload["probability_targets"]["10d"]["prediction_quality"]["method"] == "ensemble_empirical_blend"
    assert payload["probability_targets"]["10d"]["prediction_quality"]["support_samples"] > 0
    assert payload["probability_targets"]["10d"]["prediction_interval"]["horizon_days"] == 10
    assert payload["prediction_quality"]["method"] == "ensemble_empirical_blend"
    assert payload["confidence_meta"]["horizon_quality"]["10d"] == payload["prediction_quality"]["quality"]
    assert payload["confidence_meta"]["quality"] in {"medium", "high"}


def test_parse_asof_time_supports_epoch_seconds_and_milliseconds():
    from akshare_mcp.tools.data_quality import parse_asof_time

    sec_value = 1775439960
    ms_value = 1775439960000

    assert parse_asof_time(sec_value) is not None
    assert parse_asof_time(ms_value) is not None
    assert parse_asof_time(sec_value).isoformat() == parse_asof_time(ms_value).isoformat()


@pytest.mark.asyncio
async def test_build_event_context_extracts_veto_candidates(monkeypatch):
    from akshare_mcp.services import decision_event_builder as builder

    def _fake_news(code, limit):
        return {
            "success": True,
            "data": [
                {"date": "2026-03-18", "title": "公司高管被实施留置", "summary": "被实施留置并接受调查"},
                {"date": "2026-03-17", "title": "公司签约新订单", "summary": "中标重大项目"},
            ],
        }

    def _fake_notices(start_date, end_date, types, stock_code):
        return {
            "success": True,
            "data": {
                "events": [
                    {"date": "2026-03-19", "title": "关于收到监管函的公告", "summary": "涉嫌违规被监管关注"},
                ]
            },
        }

    def _fake_reports(symbol="", stock_code="", limit=10):
        return {
            "success": True,
            "data": {
                "reports": [
                    {"date": "2026-03-16", "title": "维持审慎评级", "institution": "某券商", "rating": "中性"},
                ]
            },
        }

    monkeypatch.setattr(builder, "get_stock_news", _fake_news)
    monkeypatch.setattr(builder, "get_stock_notices", _fake_notices)
    monkeypatch.setattr(builder, "get_research_reports", _fake_reports)

    payload = await builder.build_event_context("600519")

    assert payload["hard_veto_eligible"] is True
    assert payload["event_direction"] == "bearish"
    assert payload["veto_candidates"]
    assert payload["evidence_links"]
