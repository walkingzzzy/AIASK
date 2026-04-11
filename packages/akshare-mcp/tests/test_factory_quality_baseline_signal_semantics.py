from __future__ import annotations

import pytest

from akshare_mcp.services.strategy_lifecycle_shared import build_incubation_overview
from akshare_mcp.tools.managers.strategy_mgr_helpers import build_factory_quality_baseline

from ._strategy_factory_test_support import _StrategyDB


@pytest.mark.asyncio
async def test_factory_quality_baseline_does_not_treat_missing_forward_returns_as_zero_signal():
    db = _StrategyDB()
    strategy = {
        "id": "factory_raw_only",
        "name": "Raw Signal Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "submitted",
        "tags": ["factory", "auto_generated"],
        "params": {"lookback": 20},
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics("factory_raw_only", "all", {"sharpe_ratio": 0.8, "max_drawdown": 0.12})
    await db.save_strategy_quality_report(
        "factory_raw_only",
        "submission",
        {
            "passed": False,
            "summary": {
                "validation_grade": "C",
                "raw_validation_grade": "C",
                "effective_validation_grade": "C",
                "raw_validation_total_score": 58.0,
                "validation_total_score": 58.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats["factory_raw_only"] = {
        "hit_rate": {},
        "forward_ic": {},
        "forward_sharpe": {},
        "total_signals": 12,
        "raw_signal_count": 12,
        "signals_with_forward_returns_count": 0,
        "observed_forward_return_count": 0,
    }

    overview = await build_incubation_overview(db, strategy)
    baseline = await build_factory_quality_baseline(db)
    cohort = baseline["submitted_strategy_cohort"]

    assert overview["total_signals"] == 12
    assert overview["raw_signal_count"] == 12
    assert overview["signals_with_forward_returns_count"] == 0
    assert overview["observed_forward_return_count"] == 0
    assert overview["missing_forward_days"] == [1, 5, 10, 20]
    assert cohort["zero_signal_count"] == 0
    assert cohort["forward_coverage_count"] == 0
    assert cohort["zero_signal_definition"] == "raw_signal_count <= 0"
