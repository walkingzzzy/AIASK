from __future__ import annotations

import json

from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider


def _futures_research_context() -> dict:
    return {
        "strategy_context": {
            "adapter_name": "futures_calendar_research_adapter",
            "underlying": "SC",
            "instrument_profile": {
                "asset_class": "futures",
                "underlying": "SC",
                "curve_legs": [
                    {"side": "long", "leg_type": "month_offset", "month": 1},
                    {"side": "short", "leg_type": "month_offset", "month": 3},
                ],
                "roll_rule": {
                    "rule_type": "calendar_spread_roll",
                    "exit_before_front_delivery_days": 3,
                },
            },
            "strategies": [
                {
                    "strategy_code": "spread_1_3_probe",
                    "family": "spread",
                    "summary": {"annualized_return": 0.08, "post_cost_sharpe": 0.7},
                }
            ],
        },
        "backtest_summary": {
            "leaderboard": [
                {
                    "family": "spread",
                    "strategy_code": "spread_1_3_probe",
                    "annualized_return": 0.08,
                    "post_cost_sharpe": 0.7,
                }
            ]
        },
        "regime_panel": {
            "spread_1_3_probe": {
                "backwardation": {"annualized_return": 0.12},
                "contango_or_flat": {"annualized_return": -0.01},
            }
        },
        "capacity_panel": {
            "spread_1_3_probe": [
                {
                    "capital": 1_000_000,
                    "capacity_limit_contracts": 6,
                    "binding_constraint": "participation",
                }
            ]
        },
        "generalization_seed": {
            "logic_abstraction": ["stable backwardation + pullback entry"],
            "failure_modes": ["delivery pressure"],
        },
    }


def test_compact_research_context_preserves_structured_futures_blocks():
    provider = StrategyLLMProvider(StrategyLLMConfig(enabled=False))

    compact = provider._compact_research_context(_futures_research_context(), compact_level=2)

    assert compact["strategy_context"]["instrument_profile"]["asset_class"] == "futures"
    assert compact["strategy_context"]["instrument_profile"]["underlying"] == "SC"
    assert "backtest_summary" in compact
    assert "regime_panel" in compact
    assert "capacity_panel" in compact
    assert "generalization_seed" in compact


def test_build_prompt_emits_futures_contract_requirements():
    provider = StrategyLLMProvider(StrategyLLMConfig(enabled=False))

    system_prompt, user_prompt = provider._build_prompt(
        snapshot={"date": "2026-04-15"},
        market_summary={"market_regime": {"fg_level": "neutral"}},
        research_context=_futures_research_context(),
        parent_strategies=[],
        history_summary=[],
        limit=1,
        research_task=None,
        compact_level=2,
    )
    user_payload = json.loads(user_prompt)

    assert "paired_futures_spread" in system_prompt
    assert "single_futures_directional" in system_prompt
    assert "objective_profile=high_precision" in system_prompt
    assert "entry_selectivity" in system_prompt
    assert "trade_density_preference" in system_prompt
    assert "instrument_profile" in system_prompt
    assert user_payload["research_context"]["strategy_context"]["instrument_profile"]["asset_class"] == "futures"
    assert "capacity_panel" in user_payload["research_context"]
