"""P0-1: DCF 驱动项重构测试（WACC + 敏感性 + 兼容性）"""

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
                "revenue": 900.0,
                "net_profit": 180.0,
            },
        ]

    async def get_financials(self, code, limit=4):
        return self._financials[:limit]


@pytest.mark.asyncio
async def test_p0_1_dcf_legacy_call_compatible(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    # 仅传旧参数，验证向后兼容
    result = await mcp.dcf_valuation("600519", discount_rate=0.10, growth_rate=0.05, years=5)
    assert result["success"] is True
    data = result["data"]
    assert data["model"] == "Driver DCF with WACC"
    assert "wacc_breakdown" in data
    assert "sensitivity" in data
    assert data["intrinsic_value"] > 0


@pytest.mark.asyncio
async def test_p0_1_dcf_wacc_breakdown_values(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.11,
        growth_rate=0.05,
        years=3,
        risk_free_rate=0.03,
        beta=1.2,
        market_risk_premium=0.06,
        cost_of_debt=0.05,
        tax_rate=0.25,
        equity_weight=0.7,
        debt_weight=0.3,
        terminal_growth_rate=0.03,
        enable_sensitivity=False,
    )
    assert result["success"] is True
    wb = result["data"]["wacc_breakdown"]

    # CAPM: 0.03 + 1.2*0.06 = 0.102
    assert wb["cost_of_equity"] == pytest.approx(0.102, rel=1e-6)
    # 税后债务成本: 0.05*(1-0.25)=0.0375
    assert wb["cost_of_debt_after_tax"] == pytest.approx(0.0375, rel=1e-6)
    # WACC: 0.7*0.102 + 0.3*0.0375 = 0.08265
    assert wb["wacc"] == pytest.approx(0.08265, rel=1e-6)


@pytest.mark.asyncio
async def test_p0_1_dcf_sensitivity_grid(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.11,
        growth_rate=0.05,
        years=3,
        terminal_growth_rate=0.03,
        enable_sensitivity=True,
    )
    assert result["success"] is True
    sensitivity = result["data"]["sensitivity"]
    # 默认 3*3*3=27 个情景（本参数下全部有效）
    assert len(sensitivity) == 27
    assert all("intrinsic_value" in s for s in sensitivity)


@pytest.mark.asyncio
async def test_p0_1_dcf_terminal_guard(monkeypatch):
    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _FakeDB())

    result = await mcp.dcf_valuation(
        "600519",
        discount_rate=0.04,
        growth_rate=0.05,
        terminal_growth_rate=0.05,
    )
    assert result["success"] is False
    assert "terminal_growth_rate" in result["error"]

