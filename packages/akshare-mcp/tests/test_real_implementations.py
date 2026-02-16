import pandas as pd

from akshare_mcp.services.llm_alpha import LLMAlphaMiner
from akshare_mcp.tools.managers.performance_manager import _compute_timing_component


def test_timing_component_is_real_and_non_placeholder():
    price_matrix = pd.DataFrame(
        [
            [100.0, 120.0, 90.0],   # +20%, -25%
            [100.0, 90.0, 121.0],   # -10%, +34.44%
        ]
    ).to_numpy()
    start_values = pd.Series([1000.0, 1000.0]).to_numpy()

    result = _compute_timing_component(price_matrix, start_values)

    assert result["aligned_days"] == 3
    assert result["assets_used"] == 2
    assert len(result["daily_returns"]) == 2

    # timing = realized_total_return - static_total_return
    lhs = float(result["realized_total_return"] - result["static_total_return"])
    rhs = float(result["timing_return"])
    assert abs(lhs - rhs) < 1e-12
    assert abs(rhs) > 1e-6


def test_llm_alpha_uses_local_rule_engine_without_api():
    miner = LLMAlphaMiner()
    market_data = pd.DataFrame(
        {
            "close": [10.0, 10.1, 10.4, 10.2, 10.6, 10.8, 10.5, 10.9],
            "open": [9.9, 10.0, 10.2, 10.1, 10.4, 10.7, 10.6, 10.8],
            "high": [10.1, 10.2, 10.5, 10.3, 10.7, 10.9, 10.7, 11.0],
            "low": [9.8, 9.9, 10.1, 10.0, 10.2, 10.5, 10.4, 10.7],
            "volume": [1000, 900, 1500, 1200, 1800, 2000, 1600, 1900],
            "amount": [10000, 9200, 15600, 12200, 19000, 22000, 17600, 21000],
            "market_cap": [200000, 200500, 201000, 201500, 202000, 202500, 203000, 203500],
        }
    )

    candidates = miner.generate_factor_candidates(
        market_data=market_data,
        news_data=[{"title": "业绩超预期"}, {"headline": "行业景气回升"}],
        num_candidates=5,
    )

    assert len(candidates) == 5
    assert all(c["engine"] == "local_rule_v1" for c in candidates)
    assert all(c["factor_id"].startswith("ALPHA_FACTOR_") for c in candidates)
    assert all(c.get("formula") for c in candidates)
    assert all(c.get("category") for c in candidates)


def test_llm_alpha_local_generation_deduplicates_names():
    miner = LLMAlphaMiner()
    raw = [
        {"name": "Momentum Spread", "description": "A", "formula": "close.pct_change(20)", "category": "momentum"},
        {"name": "Momentum Spread", "description": "B", "formula": "close.pct_change(10)", "category": "unknown"},
        {"name": "  ", "description": "bad", "formula": "close.pct_change(5)", "category": "value"},
    ]
    normalized = miner._normalize_candidates(raw, num_candidates=10)

    assert len(normalized) == 2
    assert normalized[0]["name"] == "Momentum_Spread"
    assert normalized[1]["name"].startswith("Momentum_Spread_")
    assert normalized[1]["category"] == "custom"
