from unittest.mock import AsyncMock, MagicMock

import pytest

import akshare_mcp.services.strategy_factory as legacy_factory_package
import akshare_mcp.services.strategy_factory.submission_gate as legacy_submission_gate
import akshare_mcp.services.strategy_factory.utils as legacy_utils

from strategy_factory.application.submitter import StrategySubmitter


@pytest.mark.asyncio
async def test_submitter_uses_legacy_submission_gate_patch_point(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    gate_mock = AsyncMock(return_value={"passed": False, "reasons": ["bridge"], "reason_codes": ["bridge"]})
    monkeypatch.setattr(legacy_submission_gate, "run_submission_quality_gate", gate_mock)
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "spawn_reason": "compat-bridge",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    gate_mock.assert_awaited_once()
    assert result["submitted"] == 1
    assert result["passed_quality_gate"] == 0


@pytest.mark.asyncio
async def test_submitter_uses_legacy_utils_patch_points(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    gate_mock = AsyncMock(return_value={"passed": False, "reasons": [], "reason_codes": []})
    update_status_mock = AsyncMock()

    monkeypatch.setattr(legacy_submission_gate, "run_submission_quality_gate", gate_mock)
    monkeypatch.setattr(legacy_utils, "_auto_name", lambda *_args, **_kwargs: "legacy-patched-name")
    monkeypatch.setattr(legacy_utils, "_update_strategy_status", update_status_mock)
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "spawn_reason": "compat-utils",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["strategies"][0]["name"] == "legacy-patched-name"
    update_status_mock.assert_awaited()
