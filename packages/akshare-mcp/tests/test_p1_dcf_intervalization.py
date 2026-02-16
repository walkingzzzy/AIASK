"""P1-1: DCF intervalization tests (Monte Carlo distribution output)."""

import pytest

import akshare_mcp.tools.valuation as valuation_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDB:
    def __init__(self):
        self._financials = [
            {
                "code": "600519",
                "report_date": "2024-12-31",
                "revenue": 1000.0,
                "net_profit": 200.0,
            },
            {
                "code": "600519",
                "report_date": "2023-12-31",
                "revenue": 920.0,
                "net_profit": 170.0,
            },
        ]

    async def get_financials(self, code, limit=8):
        return self._financials[:limit]


@pytest.mark.asyncio
async def test_p1_1_dcf_distribution_interval_output(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.10,
        growth_rate=0.05,
        years=5,
        enable_sensitivity=False,
        enable_distribution=True,
        distribution_samples=300,
        distribution_seed=7,
    )
    assert result["success"] is True
    data = result["data"]
    assert "valuation_interval" in data

    interval = data["valuation_interval"]
    assert interval["requested_samples"] == 300
    assert interval["sample_size"] > 0
    assert interval["p10"] <= interval["p50"] <= interval["p90"]
    assert interval["min"] <= interval["p10"]
    assert interval["p90"] <= interval["max"]


@pytest.mark.asyncio
async def test_p1_1_dcf_distribution_samples_are_sanitized(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.10,
        growth_rate=0.05,
        years=5,
        enable_sensitivity=False,
        enable_distribution=True,
        distribution_samples=3,
        distribution_seed=11,
    )
    assert result["success"] is True
    interval = result["data"]["valuation_interval"]
    assert interval["requested_samples"] == 100
    assert interval["sample_size"] > 0


@pytest.mark.asyncio
async def test_p1_1_dcf_distribution_disabled_keeps_legacy_shape(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.10,
        growth_rate=0.05,
        years=5,
        enable_sensitivity=False,
    )
    assert result["success"] is True
    data = result["data"]
    assert "intrinsic_value" in data
    assert "valuation_interval" not in data
