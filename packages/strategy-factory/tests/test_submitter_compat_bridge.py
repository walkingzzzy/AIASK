from unittest.mock import AsyncMock, MagicMock

import pytest

import akshare_mcp.services.strategy_factory as legacy_factory_package
import akshare_mcp.services.strategy_factory.submission_gate as legacy_submission_gate
import akshare_mcp.services.strategy_factory.utils as legacy_utils

from strategy_factory.application.submitter import StrategySubmitter
from strategy_factory.domain.strategy_profile import apply_candidate_strategy_profile


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
    assert result["created"] == 0
    assert result["created_total"] == 1
    assert result["created_strategy_pool"] == 0
    assert result["created_audit_only"] == 1
    assert result["submitted"] == 0
    assert result["passed_quality_gate"] == 0
    assert result["gate_3_input"] == 1
    assert result["gate_report"]["gate_3"]["input_count"] == 1
    assert result["gate_report"]["gate_3"]["failed_count"] == 1


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
    assert result["created"] == 0
    assert result["created_total"] == 1
    assert result["created_audit_only"] == 1
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
async def test_submitter_applies_incubation_budget_tracks(monkeypatch):
    import strategy_factory.application.incubation_budgeter as budgeter_mod

    incubation_gateway = MagicMock()
    incubation_gateway.ensure_account = AsyncMock(return_value={"account": {"id": "acct_formal_1"}})
    incubation_gateway.run_pipeline = AsyncMock(
        return_value={
            "snapshot": {
                "pipeline_stage": "warmup",
                "pipeline_status": "collecting",
                "readiness_score": 0.62,
            },
            "task_run_id": 101,
        }
    )
    submitter = StrategySubmitter(incubation_gateway=incubation_gateway)
    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()

    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.0)
    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(return_value={"passed": True, "reasons": [], "reason_codes": []}),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    result = await submitter.submit(
        [
            {
                "name": "formal_candidate",
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "spawn_reason": "formal-budget",
                "research_task": {"priority": 80, "candidate_family": "momentum"},
                "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.16, "max_drawdown": 0.10, "trades_count": 6},
            },
            {
                "name": "observe_candidate",
                "strategy_type": "value_factor",
                "params": {"lookback": 60},
                "spawn_reason": "observe-budget",
                "research_task": {"priority": 55, "candidate_family": "value_factor"},
                "backtest_metrics": {"sharpe_ratio": 0.45, "total_return": 0.05, "max_drawdown": 0.08, "trades_count": 5},
            },
        ],
        {"date": "2026-04-02", "fg_level": "neutral", "fear_greed_index": 55},
        db,
    )

    strategy_status = {item["name"]: item["status"] for item in result["strategies"]}
    strategy_tracks = {item["name"]: item["incubation_budget_track"] for item in result["strategies"]}

    assert strategy_status["formal_candidate"] == "incubating"
    assert strategy_status["observe_candidate"] == "submitted"
    assert strategy_tracks["formal_candidate"] == "formal_incubation"
    assert strategy_tracks["observe_candidate"] == "observe_incubation"
    assert result["created"] == 2
    assert result["created_total"] == 2
    assert result["created_strategy_pool"] == 2
    assert result["created_audit_only"] == 0
    assert result["incubation_budget_summary"]["track_counts"]["formal_incubation"] == 1
    assert result["incubation_budget_summary"]["track_counts"]["observe_incubation"] == 1
    assert incubation_gateway.ensure_account.await_count == 2
    incubation_gateway.run_pipeline.assert_awaited_once()


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

    assert result["created"] == 0
    assert result["created_total"] == 0
    assert result["created_strategy_pool"] == 0
    assert result["created_audit_only"] == 0
    assert result["submitted"] == 0
    assert result["gate_3_input"] == 1
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
        AsyncMock(
            return_value={
                "passed": False,
                "reasons": ["bridge"],
                "reason_codes": ["bridge"],
                "multiple_testing_registry": {
                    "registry_key": "task|snapshot|family|sentiment|universe|explicit:600519|template|default|revision|baseline",
                    "task_key": "task|snapshot",
                    "family_key": "family|sentiment|dsl_rule",
                    "universe_key": "universe|explicit:600519|600519",
                    "template_key": "template|default|trade_rule_validation|dsl_rule",
                    "revision_key": "revision|snapshot|baseline",
                    "lineage_id": "snapshot",
                    "target_pool_id": "explicit:600519",
                    "candidate_contract_hash": "hash_mt_1",
                    "candidate_identity_signature": "sig_mt_1",
                    "revision_mode": "baseline",
                    "refresh_mode": None,
                    "multiple_testing_mode": "bootstrap_family_proxy",
                },
            }
        ),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    candidate = apply_candidate_strategy_profile(
        {
            "name": "candidate_provenance_case",
            "strategy_type": "dsl_rule",
            "candidate_family": "sentiment",
            "holding_period_bucket": "short",
            "alpha_source": "sentiment",
            "risk_level": "high",
            "regime_fit": "event_sensitive",
            "generator_mode": "external_llm",
            "direction_bias": "long_only",
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
            "spawn_reason": "provenance-test",
            "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
            "research_task": {
                "task_id": "task_candidate_1",
                "task_source": "snapshot",
                "source_candidate_artifact_id": "candidate_001",
                "source_generation_artifact_id": "llm_episode_001",
                "source_validation_artifact_id": "candidate_validation_001",
                "memory_record_id": "memory_001",
                "candidate_family": "sentiment",
                "candidate_registry_stage": "governed",
                "validation_score": 82.0,
                "expected_regime": ["trend"],
                "expected_holding_period": 10,
                "latest_validation_at": "2026-03-20T08:30:00+08:00",
                "latest_validation_age_days": 1,
                "candidate_evidence_status": {
                    "required_audits_complete": True,
                    "lookahead_available": True,
                    "multiple_testing_available": True,
                    "overall_risk_level": "low",
                    "blocked": False,
                },
            },
        }
    )

    result = await submitter.submit(
        [candidate],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    assert result["strategies"][0]["source_candidate_artifact_id"] == "candidate_001"
    assert result["strategies"][0]["source_generation_artifact_id"] == "llm_episode_001"
    assert result["strategies"][0]["source_validation_artifact_id"] == "candidate_validation_001"
    assert result["strategies"][0]["candidate_family"] == "sentiment"
    assert result["strategies"][0]["candidate_registry_stage"] == "governed"
    assert result["strategies"][0]["candidate_validation_score"] == 82.0
    assert result["strategies"][0]["expected_regime"] == ["trend"]
    assert result["strategies"][0]["expected_holding_period"] == 10
    assert result["strategies"][0]["candidate_latest_validation_age_days"] == 1
    assert result["strategies"][0]["holding_period_bucket"] == "short"
    assert result["strategies"][0]["alpha_source"] == "sentiment"
    assert result["strategies"][0]["risk_level"] == "high"
    assert result["strategies"][0]["regime_fit"] == "event_sensitive"
    assert result["strategies"][0]["generator_mode"] == "external_llm"
    assert result["strategies"][0]["direction_bias"] == "long_only"
    assert result["strategies"][0]["target_symbol_count"] == 1
    assert result["strategies"][0]["strategy_profile"]["candidate_family_id"] == "sentiment_short_sentiment_1"
    assert result["strategies"][0]["candidate_contract_hash"]
    assert result["strategies"][0]["candidate_identity_signature"]

    saved_payload = db.save_strategy.await_args.args[0]
    assert saved_payload["params"]["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert saved_payload["params"]["candidate_provenance"]["source_generation_artifact_id"] == "llm_episode_001"
    assert saved_payload["params"]["candidate_provenance"]["candidate_family"] == "sentiment"
    assert saved_payload["params"]["candidate_provenance"]["candidate_registry_stage"] == "governed"
    assert saved_payload["params"]["candidate_provenance"]["expected_holding_period"] == 10
    assert saved_payload["params"]["strategy_profile"]["candidate_family_id"] == "sentiment_short_sentiment_1"
    assert saved_payload["params"]["holding_period_bucket"] == "short"
    assert saved_payload["params"]["alpha_source"] == "sentiment"
    assert saved_payload["params"]["risk_level"] == "high"
    assert saved_payload["params"]["regime_fit"] == "event_sensitive"
    assert saved_payload["params"]["generator_mode"] == "external_llm"
    assert saved_payload["params"]["direction_bias"] == "long_only"
    assert saved_payload["params"]["target_symbol_count"] == 1
    assert saved_payload["params"]["candidate_contract_hash"] == result["strategies"][0]["candidate_contract_hash"]
    assert saved_payload["params"]["candidate_identity_signature"] == result["strategies"][0]["candidate_identity_signature"]
    assert saved_payload["params"]["candidate_contract_snapshot"]["targeting"]["target_pool_id"] == "explicit:600519"

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert quality_report["candidate_provenance"]["candidate_family"] == "sentiment"
    assert quality_report["candidate_provenance"]["latest_validation_age_days"] == 1
    assert quality_report["strategy_profile"]["candidate_family_id"] == "sentiment_short_sentiment_1"
    assert quality_report["summary"]["holding_period_bucket"] == "short"
    assert quality_report["summary"]["alpha_source"] == "sentiment"
    assert quality_report["summary"]["risk_level"] == "high"
    assert quality_report["summary"]["regime_fit"] == "event_sensitive"
    assert quality_report["summary"]["generator_mode"] == "external_llm"
    assert quality_report["candidate_contract_hash"] == result["strategies"][0]["candidate_contract_hash"]
    assert quality_report["candidate_identity_signature"] == result["strategies"][0]["candidate_identity_signature"]
    assert quality_report["summary"]["target_pool_id"] == "explicit:600519"
    assert quality_report["summary"]["multiple_testing_registry"]["task_key"] == "task|snapshot"

    lineage_metadata = db.save_strategy_lineage.await_args.kwargs["metadata"]
    assert lineage_metadata["candidate_contract_hash"] == result["strategies"][0]["candidate_contract_hash"]
    assert lineage_metadata["candidate_identity_signature"] == result["strategies"][0]["candidate_identity_signature"]
    assert lineage_metadata["target_pool_id"] == "explicit:600519"
    assert lineage_metadata["multiple_testing_registry"]["family_key"] == "family|sentiment|dsl_rule"


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

    candidate = apply_candidate_strategy_profile(
        {
            "name": "candidate_experiment_case",
            "experiment_id": "exp_candidate_001",
            "strategy_type": "dsl_rule",
            "candidate_family": "capital_flow",
            "holding_period_bucket": "medium",
            "alpha_source": "capital_flow",
            "risk_level": "medium",
            "regime_fit": "rotation_balanced",
            "generator_mode": "external_llm",
            "direction_bias": "trend_follow_long",
            "target_symbols": ["600519", "000858"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858"]},
            "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
            "spawn_reason": "experiment-provenance-test",
            "backtest_metrics": {"sharpe_ratio": 0.5, "total_return": 0.1, "max_drawdown": 0.12, "trades_count": 4},
            "research_task": {
                "task_id": "task_candidate_2",
                "task_source": "snapshot",
            },
            "source_candidate_artifact_id": "candidate_002",
            "source_generation_artifact_id": "llm_episode_002",
            "source_validation_artifact_id": "candidate_validation_002",
            "memory_record_id": "memory_002",
            "candidate_family": "capital_flow",
            "candidate_registry_stage": "governed",
            "validation_score": 79.0,
            "expected_regime": ["trend", "rotation"],
            "expected_holding_period": 15,
            "latest_validation_at": "2026-03-20T08:30:00+08:00",
            "latest_validation_age_days": 1,
        }
    )

    await submitter.submit(
        [candidate],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    experiment_payload = db.save_strategy_generation_experiment.await_args.args[0]
    assert experiment_payload["strategy_spec"]["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_002"
    assert experiment_payload["strategy_spec"]["candidate_provenance"]["source_generation_artifact_id"] == "llm_episode_002"
    assert experiment_payload["evaluation"]["candidate_provenance"]["candidate_family"] == "capital_flow"
    assert experiment_payload["result"]["candidate_provenance"]["expected_regime"] == ["trend", "rotation"]
    assert experiment_payload["result"]["candidate_provenance"]["expected_holding_period"] == 15
    assert experiment_payload["strategy_spec"]["strategy_profile"]["candidate_family_id"] == "capital_flow_medium_capital_flow_2"
    assert experiment_payload["strategy_spec"]["holding_period_bucket"] == "medium"
    assert experiment_payload["strategy_spec"]["alpha_source"] == "capital_flow"
    assert experiment_payload["evaluation"]["risk_level"] == "medium"
    assert experiment_payload["evaluation"]["regime_fit"] == "rotation_balanced"
    assert experiment_payload["result"]["generator_mode"] == "external_llm"
    assert experiment_payload["result"]["target_symbol_count"] == 2
    assert experiment_payload["strategy_spec"]["candidate_contract_hash"]
    assert experiment_payload["strategy_spec"]["candidate_identity_signature"]
    assert experiment_payload["evaluation"]["candidate_contract_hash"] == experiment_payload["strategy_spec"]["candidate_contract_hash"]
    assert experiment_payload["result"]["candidate_identity_signature"] == experiment_payload["strategy_spec"]["candidate_identity_signature"]


@pytest.mark.asyncio
async def test_submitter_persists_admission_event_window_and_execution_evidence(monkeypatch):
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
        AsyncMock(
            return_value={
                "passed": True,
                "passed_strict": True,
                "provisional_pass": False,
                "admission_stage": "live",
                "incubation_pass_mode": "strict",
                "research_candidate_ready": True,
                "incubation_candidate_ready": True,
                "live_candidate_ready": True,
                "admission_block_reasons": [],
                "admission_evaluations": {
                    "research": {"passed": True},
                    "incubation": {"passed": True},
                    "live": {"passed": True},
                },
                "profile": "event_trade_validation",
                "validation_focus": "event_target_only",
                "primary_validation_layer": "target_layer_metrics",
                "reasons": [],
                "reason_codes": [],
            }
        ),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))

    candidate = apply_candidate_strategy_profile(
        {
            "name": "candidate_execution_evidence",
            "experiment_id": "exp_candidate_evidence_001",
            "strategy_type": "dsl_rule",
            "candidate_family": "event",
            "holding_period_bucket": "short",
            "alpha_source": "event",
            "risk_level": "medium",
            "regime_fit": "event_sensitive",
            "generator_mode": "external_llm",
            "direction_bias": "long_only",
            "target_symbols": ["600519", "000858"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858"]},
            "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
            "spawn_reason": "experiment-evidence-test",
            "incubation_budget": {"track": "observe_incubation", "rank": 2, "priority_score": 0.41},
            "backtest_metrics": {
                "sharpe_ratio": 1.12,
                "total_return": 0.18,
                "max_drawdown": 0.09,
                "trades_count": 7,
                "event_window_config": {"pre_days": 3, "post_days": 5},
                "event_window_metrics": {
                    "abnormal_return": 0.086,
                    "car": 0.081,
                    "bhar": 0.084,
                    "hit_ratio": 0.75,
                },
                "position_assumption": "equal_weight_proxy",
                "cost_assumptions": {
                    "commission_bps": 8,
                    "market_ruleset": "cn_equity",
                    "sell_tax_rate": 0.001,
                    "min_trade_lot": 100,
                    "t_plus_one": True,
                    "arrival_price_policy": "next_open_proxy",
                    "market_impact_bps": 5.0,
                    "implementation_shortfall_proxy": 17.5,
                },
                "backtest_assumptions": {
                    "max_position_pct": 0.2,
                    "target_weight_scheme": "equal_weight",
                    "tradability_filter": True,
                    "market_ruleset": "cn_equity",
                    "sell_tax_rate": 0.001,
                    "min_trade_lot": 100,
                    "t_plus_one": True,
                },
                "constraint_check": {
                    "intersection_ratio": 1.0,
                    "constraint_violation": None,
                    "expansion_applied": False,
                },
            },
            "research_task": {
                "task_id": "task_candidate_evidence",
                "task_source": "event_driven",
                "validation_focus": "event_target_only",
            },
        }
    )

    await submitter.submit(
        [candidate],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["admission_stage"] == "live"
    assert quality_report["event_window_metrics"]["car"] == pytest.approx(0.081)
    assert quality_report["execution_reality"]["market_ruleset"] == "cn_equity"
    assert quality_report["execution_reality"]["min_trade_lot"] == 100
    assert quality_report["summary"]["live_candidate_ready"] is True
    assert quality_report["summary"]["market_ruleset"] == "cn_equity"

    experiment_payload = db.save_strategy_generation_experiment.await_args.args[0]
    assert experiment_payload["evaluation"]["admission_stage"] == "live"
    assert experiment_payload["evaluation"]["event_window_metrics"]["hit_ratio"] == pytest.approx(0.75)
    assert experiment_payload["evaluation"]["execution_reality"]["t_plus_one"] is True
    assert experiment_payload["evaluation"]["backtest_metrics"]["cost_assumptions"]["market_ruleset"] == "cn_equity"
    assert experiment_payload["evaluation"]["quality_summary"]["market_ruleset"] == "cn_equity"
    assert experiment_payload["result"]["event_window_metrics"]["bhar"] == pytest.approx(0.084)
    assert experiment_payload["result"]["execution_reality"]["target_weight_scheme"] == "equal_weight"
    assert experiment_payload["result"]["live_candidate_ready"] is True


@pytest.mark.asyncio
async def test_submitter_routes_live_ready_candidates_into_review_chain(monkeypatch):
    class _DummyIncubationGateway:
        async def ensure_account(self, _db, _strategy, *, source_run_id=None, stage="warmup"):
            assert source_run_id == "2026-03-19"
            assert stage == "candidate"
            return {
                "account": {"id": "paper_live_001"},
                "binding": {"account_id": "paper_live_001"},
            }

    class _DummyRuntimeControlService:
        async def set_control(self, _db, strategy, **kwargs):
            assert strategy["id"]
            assert kwargs["control_mode"] == "monitor"
            assert kwargs["trigger_event_type"] == "factory_live_ready_submission"
            return {
                "strategy_id": strategy["id"],
                "control_mode": "monitor",
                "status": "active",
            }

    class _DummyPromotionPipelineService:
        async def review(self, _db, strategy, **kwargs):
            assert strategy["id"]
            assert kwargs["auto_apply"] is True
            return {
                "review": {
                    "id": "promotion_review_001",
                    "status": "watch",
                    "recommendation": "observe",
                    "score": 0.61,
                }
            }

    submitter = StrategySubmitter(incubation_gateway=_DummyIncubationGateway())
    class _DB:
        def __init__(self):
            self.save_strategy = AsyncMock()
            self.save_strategy_metrics = AsyncMock()
            self.save_strategy_quality_report = AsyncMock()
            self.update_strategy_status = AsyncMock()
            self.update_paper_account_status = AsyncMock(return_value={"id": "paper_live_001", "status": "active"})
            self.save_strategy_lineage = AsyncMock()

    db = _DB()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(
            return_value={
                "passed": True,
                "passed_strict": True,
                "provisional_pass": False,
                "admission_stage": "live",
                "incubation_pass_mode": "strict",
                "research_candidate_ready": True,
                "incubation_candidate_ready": True,
                "live_candidate_ready": True,
                "admission_block_reasons": [],
                "admission_evaluations": {
                    "research": {"passed": True},
                    "incubation": {"passed": True},
                    "live": {"passed": True},
                },
                "reasons": [],
                "reason_codes": [],
                "warnings": [],
            }
        ),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "strategy_factory.application._submitter_actions.get_strategy_runtime_control_service",
        lambda: _DummyRuntimeControlService(),
    )
    monkeypatch.setattr(
        "strategy_factory.application._submitter_actions.get_strategy_promotion_pipeline_service",
        lambda: _DummyPromotionPipelineService(),
    )

    result = await submitter.submit(
        [
            {
                "name": "live_ready_candidate",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "backtest_metrics": {
                    "sharpe_ratio": 1.2,
                    "total_return": 0.14,
                    "max_drawdown": 0.08,
                    "trades_count": 8,
                },
                "spawn_reason": "live-ready-chain",
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    strategy_summary = result["strategies"][0]
    assert strategy_summary["submission_lane"] == "live_ready_review"
    assert strategy_summary["submission_action_type"] == "runtime_review"
    assert strategy_summary["submission_action_trigger"] == "live_candidate_ready"
    assert strategy_summary["submission_action_next_step"] == "pool_admission"
    assert strategy_summary["submission_action_completed"] is True
    assert strategy_summary["live_review_ready"] is True
    assert strategy_summary["paper_account_id"] == "paper_live_001"
    assert strategy_summary["runtime_control_mode"] == "monitor"
    assert strategy_summary["runtime_control_status"] == "active"
    assert strategy_summary["promotion_review_id"] == "promotion_review_001"
    assert strategy_summary["promotion_review_status"] == "watch"
    assert strategy_summary["promotion_review_recommendation"] == "observe"

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["summary"]["submission_lane"] == "live_ready_review"
    assert quality_report["summary"]["submission_action_type"] == "runtime_review"
    assert quality_report["summary"]["submission_action_trigger"] == "live_candidate_ready"
    assert quality_report["summary"]["submission_action_next_step"] == "pool_admission"
    assert quality_report["summary"]["submission_action_completed"] is True
    assert quality_report["summary"]["live_review_ready"] is True
    assert quality_report["summary"]["paper_account_id"] == "paper_live_001"
    assert quality_report["summary"]["runtime_control_mode"] == "monitor"
    assert quality_report["summary"]["promotion_review_status"] == "watch"


@pytest.mark.asyncio
async def test_submitter_applies_pool_admission_for_promoted_live_ready_candidates(monkeypatch):
    class _DummyIncubationGateway:
        async def ensure_account(self, _db, _strategy, *, source_run_id=None, stage="warmup"):
            assert source_run_id == "2026-03-19"
            assert stage == "candidate"
            return {
                "account": {"id": "paper_live_approved_001"},
                "binding": {"account_id": "paper_live_approved_001"},
            }

    class _DummyRuntimeControlService:
        async def set_control(self, _db, strategy, **kwargs):
            assert strategy["id"]
            assert kwargs["control_mode"] == "monitor"
            return {
                "strategy_id": strategy["id"],
                "control_mode": "monitor",
                "status": "active",
            }

    class _DummyPromotionPipelineService:
        async def review(self, _db, strategy, **kwargs):
            assert strategy["id"]
            assert kwargs["auto_apply"] is True
            return {
                "review": {
                    "id": "promotion_review_approved_001",
                    "status": "approved",
                    "recommendation": "promote",
                    "score": 0.93,
                },
                "applied_transition": {
                    "from": "submitted",
                    "to": "listed",
                },
            }

    submitter = StrategySubmitter(incubation_gateway=_DummyIncubationGateway())

    class _DB:
        def __init__(self):
            self.save_strategy = AsyncMock()
            self.save_strategy_metrics = AsyncMock()
            self.save_strategy_quality_report = AsyncMock()
            self.update_strategy_status = AsyncMock()
            self.update_paper_account_status = AsyncMock(return_value={"id": "paper_live_approved_001", "status": "active"})
            self.save_strategy_lineage = AsyncMock()

    db = _DB()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(
            return_value={
                "passed": True,
                "passed_strict": True,
                "provisional_pass": False,
                "admission_stage": "live",
                "incubation_pass_mode": "strict",
                "research_candidate_ready": True,
                "incubation_candidate_ready": True,
                "live_candidate_ready": True,
                "admission_block_reasons": [],
                "admission_evaluations": {
                    "research": {"passed": True},
                    "incubation": {"passed": True},
                    "live": {"passed": True},
                },
                "reasons": [],
                "reason_codes": [],
                "warnings": [],
            }
        ),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "strategy_factory.application._submitter_actions.get_strategy_runtime_control_service",
        lambda: _DummyRuntimeControlService(),
    )
    monkeypatch.setattr(
        "strategy_factory.application._submitter_actions.get_strategy_promotion_pipeline_service",
        lambda: _DummyPromotionPipelineService(),
    )

    result = await submitter.submit(
        [
            {
                "name": "live_ready_promote_candidate",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "backtest_metrics": {
                    "sharpe_ratio": 1.4,
                    "total_return": 0.18,
                    "max_drawdown": 0.07,
                    "trades_count": 9,
                },
                "spawn_reason": "live-ready-promote-chain",
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    strategy_summary = result["strategies"][0]
    assert strategy_summary["status"] == "listed"
    assert strategy_summary["submission_lane"] == "live_ready_review"
    assert strategy_summary["submission_action_type"] == "pool_admission"
    assert strategy_summary["submission_action_trigger"] == "live_candidate_ready_pool_admission"
    assert strategy_summary["submission_action_next_step"] is None
    assert strategy_summary["submission_action_completed"] is True
    assert strategy_summary["pool_admission_applied"] is True
    assert strategy_summary["promotion_applied_transition"] == {"from": "submitted", "to": "listed"}
    assert strategy_summary["promotion_review_status"] == "approved"
    assert strategy_summary["promotion_review_recommendation"] == "promote"

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["summary"]["status_after_review"] == "listed"
    assert quality_report["summary"]["submission_action_type"] == "pool_admission"
    assert quality_report["summary"]["submission_action_next_step"] is None
    assert quality_report["summary"]["pool_admission_applied"] is True
    assert quality_report["pool_admission_applied"] is True
    assert quality_report["promotion_applied_transition"] == {"from": "submitted", "to": "listed"}


@pytest.mark.asyncio
async def test_submitter_routes_observe_candidates_into_paper_lane(monkeypatch):
    import strategy_factory.application.incubation_budgeter as budgeter_mod

    class _DummyIncubationGateway:
        async def ensure_account(self, _db, _strategy, *, source_run_id=None, stage="warmup"):
            assert source_run_id == "2026-03-19"
            assert stage == "paper"
            return {
                "account": {"id": "paper_observe_001"},
                "binding": {"account_id": "paper_observe_001"},
            }

    submitter = StrategySubmitter(incubation_gateway=_DummyIncubationGateway())

    class _DB:
        def __init__(self):
            self.save_strategy = AsyncMock()
            self.save_strategy_metrics = AsyncMock()
            self.save_strategy_quality_report = AsyncMock()
            self.update_strategy_status = AsyncMock()
            self.update_paper_account_status = AsyncMock(return_value={"id": "paper_observe_001", "status": "active"})
            self.save_strategy_lineage = AsyncMock()

    db = _DB()

    monkeypatch.setattr(
        legacy_submission_gate,
        "run_submission_quality_gate",
        AsyncMock(
            return_value={
                "passed": True,
                "passed_strict": True,
                "provisional_pass": False,
                "admission_stage": "incubation",
                "incubation_pass_mode": "strict",
                "research_candidate_ready": True,
                "incubation_candidate_ready": True,
                "live_candidate_ready": False,
                "admission_block_reasons": ["deflated_sharpe 0.120 < 0.300"],
                "admission_evaluations": {
                    "research": {"passed": True},
                    "incubation": {"passed": True},
                    "live": {"passed": False, "reasons": ["deflated_sharpe 0.120 < 0.300"]},
                },
                "reasons": [],
                "reason_codes": [],
                "warnings": [],
            }
        ),
    )
    monkeypatch.setattr(legacy_factory_package, "_run_validation_report", AsyncMock(return_value=None))
    monkeypatch.setattr(legacy_factory_package, "_run_risk_report", AsyncMock(return_value=None))
    monkeypatch.setattr(
        budgeter_mod.IncubationBudgeter,
        "plan",
        staticmethod(
            lambda candidates, _snapshot: {
                "summary": {"track_counts": {"observe_incubation": 1}},
                "plans": {
                    int(id(candidates[0])): {
                        "track": "observe_incubation",
                        "rank": 1,
                        "priority_score": 0.31,
                    }
                },
            }
        ),
    )

    result = await submitter.submit(
        [
            {
                "name": "observe_paper_candidate",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "backtest_metrics": {
                    "sharpe_ratio": 0.92,
                    "total_return": 0.11,
                    "max_drawdown": 0.12,
                    "trades_count": 7,
                },
                "incubation_budget": {"track": "observe_incubation", "rank": 2, "priority_score": 0.31},
                "spawn_reason": "paper-observe-route",
            }
        ],
        {"date": "2026-03-19", "fg_level": "neutral", "fear_greed_index": 50},
        db,
    )

    strategy_summary = result["strategies"][0]
    assert strategy_summary["submission_lane"] == "observe_incubation"
    assert strategy_summary["submission_action_type"] == "paper"
    assert strategy_summary["submission_action_trigger"] == "observe_track_paper_route"
    assert strategy_summary["submission_action_next_step"] == "runtime_review"
    assert strategy_summary["paper_lane_ready"] is True
    assert strategy_summary["paper_account_id"] == "paper_observe_001"
    assert strategy_summary["paper_account_status"] == "active"
    assert strategy_summary["submission_action_completed"] is True

    quality_report = db.save_strategy_quality_report.await_args.args[2]
    assert quality_report["summary"]["submission_lane"] == "observe_incubation"
    assert quality_report["summary"]["submission_action_type"] == "paper"
    assert quality_report["summary"]["paper_lane_ready"] is True
    assert quality_report["summary"]["paper_account_id"] == "paper_observe_001"
