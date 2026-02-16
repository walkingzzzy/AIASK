import pytest

import akshare_mcp.tools.managers.risk_manager as rm


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeRiskDB:
    async def get_stock_info(self, code):
        if str(code).endswith("1"):
            return {"industry": "银行"}
        return {"industry": "消费"}

    async def get_klines(self, code, limit=1):
        return [{"close": 10.0}]


@pytest.mark.asyncio
async def test_stress_test_supports_global_override_and_unified_output(monkeypatch):
    mcp = _DummyMCP()
    rm.register_risk_manager(mcp)
    monkeypatch.setattr(rm, "get_db", lambda: _FakeRiskDB())

    result = await mcp.risk_manager(
        action="stress_test",
        kwargs={
            "codes": ["600001", "600002"],
            "weights": [0.5, 0.5],
            "portfolio_value": 1_000_000,
            "scenario": "market_crash",
            "scenario_overrides": {
                "market": -0.25,
                "volatility": 2.2,
                "liquidity_penalty_pct": 0.01,
            },
        },
    )
    assert result["success"] is True
    data = result["data"]
    assert data["input_mode"] == "codes_weights"
    assert "scenario_results" in data and len(data["scenario_results"]) == 1
    assert "summary" in data and data["summary"]["count"] == 1
    assert data["assumptions"]["market_shock"] == pytest.approx(-0.25)
    assert data["assumptions"]["volatility_multiplier"] == pytest.approx(2.2)
    assert data["assumptions"]["liquidity_penalty_pct"] == pytest.approx(0.01)
    assert data["layer_losses"]["total_loss"] == pytest.approx(data["loss"])


@pytest.mark.asyncio
async def test_stress_test_supports_custom_scenarios_and_batch_summary(monkeypatch):
    mcp = _DummyMCP()
    rm.register_risk_manager(mcp)
    monkeypatch.setattr(rm, "get_db", lambda: _FakeRiskDB())

    result = await mcp.risk_manager(
        action="stress_test",
        kwargs={
            "codes": ["600001", "600002", "600003"],
            "weights": [0.4, 0.3, 0.3],
            "portfolio_value": 2_000_000,
            "scenarios": ["market_crash", "custom_alpha"],
            "custom_scenarios": [
                {
                    "name": "custom_alpha",
                    "market": -0.12,
                    "volatility": 1.8,
                    "liquidity_penalty_pct": 0.005,
                    "description": "custom macro stress",
                }
            ],
            "scenario_overrides": {"market_crash": {"market": -0.22}},
        },
    )
    assert result["success"] is True
    data = result["data"]
    assert data["count"] == 2
    assert "scenario_results" in data and len(data["scenario_results"]) == 2
    assert "scenarios" in data and "market_crash" in data["scenarios"] and "custom_alpha" in data["scenarios"]
    assert data["scenarios"]["market_crash"]["assumptions"]["market_shock"] == pytest.approx(-0.22)
    assert data["scenarios"]["custom_alpha"]["description"] == "custom macro stress"
    assert data["summary"]["count"] == 2
    assert data["summary"]["worst_scenario"] in {"market_crash", "custom_alpha"}
