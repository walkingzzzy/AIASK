"""P0-2: IC 双口径 + 中性化测试（quant + multi_factor）"""

import pytest

import akshare_mcp.tools.quant as quant_mod
from akshare_mcp.services.multi_factor import FactorAnalyzer as MultiFactorAnalyzer


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDB:
    def __init__(self, with_style: bool = True):
        self.with_style = with_style

    async def get_klines(self, code, limit=100):
        # 构造长度足够的递增价格，避免样本不足
        base = 10 + int(code[-2:]) * 0.1
        closes = [base + i * 0.1 for i in range(max(limit, 60))]
        return [{"close": c} for c in closes]

    async def get_financials(self, code, limit=1):
        # momentum 因子不强制财务数据，此处返回空不影响
        return []

    async def get_stock_info(self, code):
        if not self.with_style:
            return {}
        idx = int(code[-2:])
        return {
            "industry": "A" if idx % 2 == 0 else "B",
            "market_cap": 1_000_000_000 + idx * 10_000_000,
            "beta": 0.8 + idx * 0.01,
        }


@pytest.mark.asyncio
async def test_p0_2_quant_dual_ic_and_backward_compat(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeDB(with_style=True))

    codes = [f"600{100 + i:03d}" for i in range(12)]
    result = await mcp.calculate_factor_ic(codes=codes, factor="momentum", period=20)
    assert result["success"] is True
    data = result["data"]

    # 新增双口径字段
    for k in ("normal_ic", "rank_ic", "normal_p_value", "rank_p_value", "neutralization"):
        assert k in data

    # 向后兼容字段：ic/p_value 继续可用，且 ic 映射 rank_ic
    assert data["ic"] == pytest.approx(data["rank_ic"])
    assert data["p_value"] == pytest.approx(data["rank_p_value"])
    assert data["sample_size"] >= 10


@pytest.mark.asyncio
async def test_p0_2_quant_disable_neutralization(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeDB(with_style=True))

    codes = [f"600{200 + i:03d}" for i in range(12)]
    result = await mcp.calculate_factor_ic(
        codes=codes,
        factor="momentum",
        period=20,
        enable_neutralization=False,
    )
    assert result["success"] is True
    neutral = result["data"].get("neutralization", {})
    assert neutral.get("enabled") is False


@pytest.mark.asyncio
async def test_p0_2_quant_no_style_data_degrade(monkeypatch):
    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, "get_db", lambda: _FakeDB(with_style=False))

    codes = [f"600{300 + i:03d}" for i in range(12)]
    result = await mcp.calculate_factor_ic(codes=codes, factor="momentum", period=20)
    assert result["success"] is True
    neutral = result["data"].get("neutralization", {})
    # 无风格暴露时应可降级，不阻断主流程
    assert neutral.get("reason") in ("no_style_data", "neutralization_disabled_or_small_sample", None)


def test_p0_2_multi_factor_dual_ic_wrapper():
    factor = [1.0, 2.0, 3.0, 4.0, 5.0]
    rets = [0.01, 0.02, 0.03, 0.05, 0.06]
    result = MultiFactorAnalyzer.calculate_ic_dual(
        factor_values=factor,
        returns=rets,
        industry=["A", "A", "B", "B", "A"],
        market_cap=[1e9, 1.1e9, 1.2e9, 1.3e9, 1.4e9],
        beta=[0.9, 1.0, 1.1, 1.0, 0.95],
        enable_neutralization=True,
    )
    assert "normal_ic" in result and "rank_ic" in result
    assert "neutralization" in result

