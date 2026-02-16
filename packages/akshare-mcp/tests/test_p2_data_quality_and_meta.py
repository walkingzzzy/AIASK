import re

import pytest

import akshare_mcp.tools.market.quote as quote_mod
import akshare_mcp.tools.managers.decision_manager as dm
import akshare_mcp.tools.managers.quant_manager as qm


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _QuoteModel:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self):
        return dict(self._payload)


class _DecisionDB:
    async def get_klines(self, code, limit=100):
        return [
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "close": 10.0 + i * 0.1,
                "volume": 100000 + i,
            }
            for i in range(100)
        ]

    async def save_klines(self, code, klines):
        return None

    async def get_financials(self, code, limit=1):
        # 故意返回缺失字段，验证 P2-2 data_quality 与 penalty 逻辑
        return [{}]


def test_p2_realtime_quote_trace_fields(monkeypatch):
    payload = {
        "code": "000777",
        "name": "测试股",
        "price": 12.3,
        "change": 0.1,
        "changePercent": 0.8,
        "open": 12.0,
        "high": 12.5,
        "low": 11.9,
        "preClose": 12.2,
        "volume": 1000,
        "amount": 12300.0,
        "source": "tdx",
    }

    monkeypatch.setattr(quote_mod.data_source, "get_realtime_quote", lambda _c: payload)
    monkeypatch.setattr(quote_mod, "validate_quote", lambda d: _QuoteModel(d))

    r = quote_mod.get_realtime_quote("000777")
    assert r["success"] is True

    d = r["data"]
    assert d["attempted_sources"] == ["data_source"]
    assert d["source_chain"] == ["data_source"]
    assert d["fallback_used"] is False
    assert "data_timestamp" in d and re.match(r"^\d{4}-\d{2}-\d{2}$", d["data_timestamp"])


@pytest.mark.asyncio
async def test_p2_decision_manager_data_quality(monkeypatch):
    mcp = _DummyMCP()
    dm.register_decision_manager(mcp)
    monkeypatch.setattr(dm, "get_db", lambda: _DecisionDB())

    r = await mcp.decision_manager(action="analyze", code="600519", explain=True)
    assert r["success"] is True

    data = r["data"]
    assert "data_quality" in data
    assert "raw_total_score" in data
    assert data["total_score"] <= data["raw_total_score"]
    assert data["data_quality"]["score_penalty"] > 0
    assert len(data["data_quality"]["missing_fields"]) >= 1


@pytest.mark.asyncio
async def test_p2_quant_manager_meta_defaults(monkeypatch):
    mcp = _DummyMCP()
    qm.register_quant_manager(mcp)

    monkeypatch.setattr(qm, "get_db", lambda: object())

    r = await mcp.quant_manager(action="help")
    assert r["success"] is True
    assert "meta" in r
    assert r["meta"]["source_chain"] == ["quant_manager"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", r["meta"]["data_timestamp"])

