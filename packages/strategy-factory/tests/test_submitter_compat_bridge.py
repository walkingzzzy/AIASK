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


@pytest.mark.asyncio
async def test_submitter_runs_gate_before_persisting_new_strategy(monkeypatch):
    submitter = StrategySubmitter()
    order: list[str] = []
    db = MagicMock()
    db.save_strategy = AsyncMock(side_effect=lambda *_args, **_kwargs: order.append("save_strategy"))
    db.save_strategy_metrics = AsyncMock(side_effect=lambda *_args, **_kwargs: order.append("save_metrics"))
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock(side_effect=lambda *_args, **_kwargs: order.append("update_status"))
    db.save_strategy_lineage = AsyncMock()

    async def _gate(*_args, **_kwargs):
        order.append("gate")
        return {"passed": False, "reasons": ["bridge"], "reason_codes": ["bridge"]}

    monkeypatch.setattr(legacy_submission_gate, "run_submission_quality_gate", _gate)
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    await submitter.submit(
        [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "spawn_reason": "gate-before-persist",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert order[0] == "gate"
    assert "save_strategy" in order
    assert order.index("gate") < order.index("save_strategy")


@pytest.mark.asyncio
async def test_submitter_does_not_overwrite_existing_strategy_when_refresh_candidate_fails_gate(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.get_strategy = AsyncMock(
        return_value={
            "id": "sid_existing_1",
            "name": "既有策略",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "incubating",
            "params": {"lookback": 12, "threshold": 0.01},
            "factor_weights": {},
            "tags": ["factory", "momentum"],
        }
    )
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_generation_experiment = AsyncMock()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": False, "reasons": ["refresh rejected"], "reason_codes": ["refresh_rejected"]}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "spawn_reason": "refresh-failed",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
                "dedup_result": {"refresh_existing": True, "matched_strategy_id": "sid_existing_1", "matched_status": "incubating"},
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["submitted"] == 1
    db.save_strategy.assert_not_awaited()
    db.save_strategy_metrics.assert_not_awaited()


@pytest.mark.asyncio
async def test_submitter_blocks_provisional_only_pass_on_medium_preference_mismatch(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": True, "passed_strict": False, "provisional_pass": True, "reasons": [], "warnings": []}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "name": "event_dsl_candidate",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "research_task": {
                    "task_source": "snapshot",
                    "preferred_strategy_types": ["momentum"],
                    "preference_strength": "medium",
                },
                "backtest_metrics": {"sharpe_ratio": 0.08, "total_return": 0.0, "max_drawdown": 0.08, "trades_count": 6},
                "spawn_reason": "medium-preference-mismatch",
                "tags": ["factory", "external_llm", "ai_generated"],
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["passed_quality_gate"] == 0
    assert result["strategies"][0]["passed"] is False
    assert result["strategies"][0]["provisional_pass"] is False
    assert any("provisional_only_blocked_by_medium_preference" in reason for reason in result["strategies"][0]["reasons"])


@pytest.mark.asyncio
async def test_submitter_allows_evidence_override_with_preference_reason(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": True, "passed_strict": True, "reasons": [], "warnings": []}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "name": "event_dsl_evidence_override",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "research_task": {
                    "task_source": "snapshot",
                    "preferred_strategy_types": ["momentum"],
                    "preference_strength": "hard",
                    "preference_reason": "snapshot_regime_bias:momentum",
                },
                "backtest_metrics": {
                    "sharpe_ratio": 0.35,
                    "post_cost_sharpe": 0.35,
                    "target_layer_oos_return": 0.06,
                    "event_window_hit_ratio": 0.7,
                    "total_return": 0.06,
                    "max_drawdown": 0.08,
                    "trades_count": 6,
                },
                "spawn_reason": "evidence-override",
                "tags": ["factory", "external_llm", "ai_generated"],
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["passed_quality_gate"] == 1
    assert result["strategies"][0]["passed"] is True
    assert result["strategies"][0]["task_preference"]["override_applied"] is True
    assert any("overridden by stronger target evidence" in warning for warning in result["strategies"][0]["gate_3"]["warnings"])


@pytest.mark.asyncio
async def test_submitter_persists_candidate_provenance_into_summary_and_quality_report(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": False, "reasons": ["bridge"], "reason_codes": ["bridge"]}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "name": "candidate_provenance_case",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "spawn_reason": "provenance-test",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
                "research_task": {
                    "task_id": "task_candidate_1",
                    "task_source": "snapshot",
                    "source_candidate_artifact_id": "candidate_001",
                    "candidate_family": "sentiment",
                    "validation_score": 82.0,
                    "expected_regime": ["trend"],
                },
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["strategies"][0]["source_candidate_artifact_id"] == "candidate_001"
    assert result["strategies"][0]["candidate_family"] == "sentiment"
    assert result["strategies"][0]["candidate_validation_score"] == 82.0
    assert result["strategies"][0]["expected_regime"] == ["trend"]

    saved_payload = db.save_strategy.await_args.args[0]
    assert saved_payload["params"]["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert saved_payload["params"]["candidate_provenance"]["candidate_family"] == "sentiment"

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert quality_report["candidate_provenance"]["candidate_family"] == "sentiment"


@pytest.mark.asyncio
async def test_submitter_records_candidate_provenance_into_generation_experiment(monkeypatch):
    submitter = StrategySubmitter()
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()
    db.get_strategy_generation_experiment = AsyncMock(return_value={})
    db.save_strategy_generation_experiment = AsyncMock()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": False, "reasons": ["bridge"], "reason_codes": ["bridge"]}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    await submitter.submit(
        [
            {
                "name": "candidate_experiment_case",
                "experiment_id": "exp_candidate_001",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "spawn_reason": "experiment-provenance-test",
                "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
                "research_task": {
                    "task_id": "task_candidate_2",
                    "task_source": "snapshot",
                },
                "source_candidate_artifact_id": "candidate_002",
                "candidate_family": "capital_flow",
                "validation_score": 79.0,
                "expected_regime": ["trend", "rotation"],
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    experiment_payload = db.save_strategy_generation_experiment.await_args.args[0]
    assert experiment_payload["strategy_spec"]["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_002"
    assert experiment_payload["evaluation"]["candidate_provenance"]["candidate_family"] == "capital_flow"
    assert experiment_payload["result"]["candidate_provenance"]["expected_regime"] == ["trend", "rotation"]
