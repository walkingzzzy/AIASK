"""Tests for rule gate and fusion logic in unified decision."""

from __future__ import annotations


def test_rule_gate_blocks_st_and_liquidity():
    from akshare_mcp.services.decision_rule_gate import build_rule_gates

    gate = build_rule_gates(
        code="600519",
        investment_style="balanced",
        stock_context={
            "current_price": 123.0,
            "volatility_20d": 0.02,
            "market_snapshot": {"liquidity_score": 0.12, "spread_pct": 1.8, "suspended": False, "extreme_volatility": False},
            "security_status": {"is_st": True, "suspended": False},
        },
        quant_context={"confidence_meta": {"stability_ratio": 0.8}},
        event_context={"event_direction": "neutral", "event_intensity": "low", "hard_veto_eligible": False},
        user_context={"risk_bucket": "moderate", "risk_level": "moderate"},
    )

    assert gate["blocked"] is True
    assert gate["veto_reason"] in {"market_gate_st", "market_gate_liquidity"}
    assert any(flag["blocking"] for flag in gate["flags"])


def test_fusion_uses_dynamic_weights_and_raw_ai_output():
    from akshare_mcp.services.decision_fusion import fuse_unified_decision

    aggressive = fuse_unified_decision(
        stock_context={"recommendation": "buy", "score": 70.0, "highlights": ["估值偏低"], "risks": []},
        quant_context={
            "score": 82.0,
            "reasons": ["20 日动量为正"],
            "risks": [],
            "confidence_meta": {"quality": "high"},
            "data_quality": {"degraded": False},
        },
        event_context={
            "score": 58.0,
            "reasons": ["正向催化存在"],
            "risks": [],
            "event_direction": "bullish",
            "event_intensity": "medium",
            "data_quality": {"degraded": False},
        },
        user_context={"risk_level": "aggressive"},
        gate={
            "blocked": False,
            "veto_reason": None,
            "flags": [],
            "warning_flags": [],
            "position_cap_pct": 0.35,
            "requested_style": "aggressive",
            "user_risk_level": "aggressive",
            "gate_adjustment": 0.0,
        },
    )

    conservative = fuse_unified_decision(
        stock_context={"recommendation": "buy", "score": 70.0, "highlights": ["估值偏低"], "risks": [], "data_quality": {"degraded": False}},
        quant_context={
            "score": 82.0,
            "reasons": ["20 日动量为正"],
            "risks": [],
            "confidence_meta": {"quality": "high"},
            "data_quality": {"degraded": False},
        },
        event_context={
            "score": 58.0,
            "reasons": ["正向催化存在"],
            "risks": [],
            "event_direction": "bullish",
            "event_intensity": "medium",
            "data_quality": {"degraded": False},
        },
        user_context={"risk_level": "conservative"},
        gate={
            "blocked": False,
            "veto_reason": None,
            "flags": [],
            "warning_flags": [],
            "position_cap_pct": 0.10,
            "requested_style": "conservative",
            "user_risk_level": "conservative",
            "gate_adjustment": 0.0,
        },
    )

    assert aggressive["weights"]["quant"] > conservative["weights"]["quant"]
    assert aggressive["raw_ai_output"]["raw_action"] in {"buy", "hold"}
    assert conservative["recommended_horizon"] in {"short", "mid"}
