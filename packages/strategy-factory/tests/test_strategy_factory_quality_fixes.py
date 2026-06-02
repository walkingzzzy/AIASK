from __future__ import annotations

import asyncio
from types import MethodType


def _semantic_ready_strategy(strategy_type: str = "ma_cross") -> dict:
    return {
        "id": "candidate_quality_fix",
        "name": "quality fix candidate",
        "strategy_type": strategy_type,
        "params": {
            "evidence_chain": {"evidences": [{"id": "ev1", "source": "test"}]},
            "prediction_contract": {"claims": [{"id": "cl1", "evidence_ids": ["ev1"]}]},
            "confidence_contract": {"probability": 0.62, "support_samples": 24},
        },
    }


def test_admission_uses_authoritative_backtest_expectancy():
    from strategy_factory.application.submission_gate import runner

    result = runner._attach_admission_evaluations(
        _semantic_ready_strategy("ma_cross"),
        {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
        {
            "passed": True,
            "profile": "trade_rule_validation",
            "validation_focus": "target_plus_representative",
            "post_cost_sharpe": 1.1,
        },
        backtest_metrics={
            "event_window_metrics": {
                "post_cost_sharpe": 1.1,
                "sharpe_ratio": 1.1,
                "total_return": 0.24,
                "target_layer_oos_return": 0.18,
                "max_drawdown": 0.08,
                "trade_count": 24,
                "trades_count": 24,
                "avg_holding_days": 12,
                "trade_density": 0.4,
                "win_rate": 0.62,
                "profit_factor": 2.1,
                "expectancy": 123.45,
                "expectancy_return": 0.031,
            }
        },
    )

    all_reasons = [
        reason
        for evaluation in result["admission_evaluations"].values()
        for reason in evaluation.get("reasons", [])
    ]
    assert not any("expectancy" in reason and "<= 0" in reason for reason in all_reasons)
    assert result["metric_source_audit"]["expectancy"] == "event_window_metrics"


def test_statistical_admission_distinguishes_missing_from_zero():
    """P1 update (R5.1, audit P1-prep): explicit 0.0 is now classified
    as ``missing`` rather than ``weak``. The audit observed that
    ``factor_validation_bootstrap`` writes 0.0 as a placeholder when an
    empty walk-forward / bootstrap run happens, so 0.0 should not be
    treated as "weak signal" — it's "no signal at all".

    The old assertion (``walk_forward_ic_ir 0.000 < ...``) is preserved
    here as a regression guard, but flipped: we now assert it is *not*
    emitted, and instead the per-metric ``missing_<m>`` codes are.
    """
    from strategy_factory.application.submission_gate import runner

    missing = runner._evaluate_statistical_admission(
        _semantic_ready_strategy("value_factor"),
        {"profile": "factor_rank_validation"},
        {},
    )

    assert "missing_statistical_metrics:wf_ic_ir,pkf_ic,bootstrap_ci_lower,param_sensitivity" in missing["reasons"]
    assert not any(reason.startswith("walk_forward_ic_ir 0.000") for reason in missing["reasons"])
    assert missing["statistical_metric_missing_counts"]["wf_ic_ir"] == 1

    explicit_zero = runner._evaluate_statistical_admission(
        _semantic_ready_strategy("value_factor"),
        {"profile": "factor_rank_validation"},
        {
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": 0.0,
            "param_sensitivity": 0.0,
        },
    )

    # Post-P1: explicit 0.0 -> missing (placeholder semantics).
    assert any(reason.startswith("missing_statistical_metrics") for reason in explicit_zero["reasons"])
    # And the per-metric structured codes appear:
    for m in ("wf_ic_ir", "pkf_ic", "bootstrap_ci_lower", "param_sensitivity"):
        assert f"missing_{m}" in explicit_zero["reasons"]
    # Threshold-comparison messages should NOT appear, because the value is
    # now classified as missing not present-real.
    assert not any(reason.startswith("walk_forward_ic_ir 0.000")
                   for reason in explicit_zero["reasons"])
    assert not any(reason.startswith("purged_kfold_ic 0.000")
                   for reason in explicit_zero["reasons"])


def test_statistical_gate_uses_validation_and_backtest_metrics():
    from strategy_factory.application.submission_gate import runner

    result = asyncio.run(
        runner._run_statistical_gate(
            None,
            _semantic_ready_strategy("value_factor"),
            profile={"profile": "factor_rank_validation"},
            validation_report={
                "walk_forward": {"oos_rank_ic_ir": 0.35},
                "purged_kfold": {"oos_rank_ic_mean": 0.03},
                "bootstrap_ci": {"ci_lower": 0.02},
            },
            backtest_metrics={"parameter_perturbation_trade_stability": 0.85},
        )
    )

    assert result["passed"] is True
    assert result["wf_ic_ir"] == 0.35
    assert result["pkf_ic"] == 0.03
    assert result["bootstrap_ci_lower"] == 0.02
    assert result["param_sensitivity"] == 0.15
    assert not any(reason.startswith("missing_statistical_metrics") for reason in result["reasons"])
    assert result["metric_source_audit"]["wf_ic_ir"] == "validation_report.walk_forward"


def test_research_task_timeout_skips_without_local_fallback(monkeypatch):
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

    class SlowGateway:
        async def generate_factory_candidates(self, *args, **kwargs):
            await asyncio.sleep(0.05)
            return {"generation": {"candidates": [{"id": "late_local_candidate"}]}}

    scheduler = StrategyFactoryScheduler(db_provider=lambda: object())
    scheduler._resolve_research_task_timeout_sec = MethodType(lambda self: 0.001, scheduler)

    cycle = asyncio.run(
        scheduler._generate_for_research_task(
            SlowGateway(),
            object(),
            {"date": "2026-05-22"},
            {"task_id": "timeout_task", "task_source": "snapshot", "generation_limit": 1},
        )
    )

    llm_generation = cycle["llm_generation"]
    assert cycle["generated_count"] == 0
    assert cycle["generation"]["candidates"] == []
    assert llm_generation["task_timeout_skip"] is True
    assert llm_generation["task_timeout_policy"] == "skip_without_local_fallback"
    assert llm_generation["external_provider"]["status"] == "skipped_timeout"


def test_bulk_research_tasks_get_longer_timeout(monkeypatch):
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

    scheduler = StrategyFactoryScheduler()
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_RESEARCH_TASK_TIMEOUT_SEC", "360")

    timeout_sec = scheduler._resolve_effective_research_task_timeout_sec(
        object(),
        {"task_id": "bulk_matrix_2026-05-22_600000_value_factor", "task_source": "bulk_stock_matrix"},
        base_timeout=180.0,
    )

    assert timeout_sec == 360.0


def test_success_summary_exposes_quality_diagnostics():
    from strategy_factory.application._cycle_success_summary import build_success_run_summary

    summary = build_success_run_summary(
        trace_id="trace_quality",
        snapshot={},
        candidates=[],
        passed=[],
        unique=[],
        eliminated=[],
        spawn_report={},
        submit_result={
            "created_strategy_pool": 0,
            "created_audit_only": 1,
            "gate_3_failure_reason_topn": [{"reason_code": "missing_statistical_metrics:wf_ic_ir", "count": 1}],
            "strategies": [
                {
                    "validation_grade": "D",
                    "metric_source_audit": {"expectancy": "event_window_metrics"},
                    "gate_b": {
                        "statistical_metric_missing_counts": {"wf_ic_ir": 1},
                    },
                }
            ],
        },
        quality_gate_report={},
        backtest_report={},
        autonomy_summary={
            "external_llm_status_counts": {"skipped_timeout": 1},
            "pipeline_fallback_counts": {"empty_confirmations": 1},
            "task_timeout_skip_count": 1,
            "task_timeout_policy": "skip_without_local_fallback",
        },
        task_scan_summary={},
        task_source_counts={},
        bulk_stock_matrix_family_counts={},
        bulk_stock_matrix_allocation_pass_counts={},
        factor_research_summary={},
        factor_refresh_summary={},
        readiness_summary={},
        warmup_summary={},
        backtest_audit_summary={},
        submission_audit_summary={},
        vector_summary={},
        elapsed=1.0,
    )

    assert summary["llm_status_counts"] == {"skipped_timeout": 1}
    assert summary["pipeline_fallback_counts"] == {"empty_confirmations": 1}
    assert summary["gate_3_failure_topn"] == [{"reason_code": "missing_statistical_metrics:wf_ic_ir", "count": 1}]
    assert summary["validation_grade_counts"] == {"D": 1}
    assert summary["statistical_metric_missing_counts"]["wf_ic_ir"] == 1
    assert summary["metric_source_audit"]["expectancy"]["event_window_metrics"] == 1


def test_success_summary_maps_llm_provider_diagnostics_into_status_counts():
    from strategy_factory.application._cycle_success_summary import build_success_run_summary

    summary = build_success_run_summary(
        trace_id="trace_llm_mapping",
        snapshot={},
        candidates=[],
        passed=[],
        unique=[],
        eliminated=[],
        spawn_report={},
        submit_result={},
        quality_gate_report={},
        backtest_report={},
        autonomy_summary={
            "external_llm_status_counts": {"non_executable": 2},
            "pipeline_fallback_counts": {
                "cooldown_skip": 3,
                "local_fallback_preferred_or_skip": 10,
                "target_context_blocked": 1,
                "502 Bad Gateway": 4,
            },
            "external_llm_request_status_counts": {"cooldown_skip": 2, "failed": 4},
            "external_llm_last_error": "Server error '502 Bad Gateway'",
        },
        task_scan_summary={},
        task_source_counts={},
        bulk_stock_matrix_family_counts={},
        bulk_stock_matrix_allocation_pass_counts={},
        factor_research_summary={},
        factor_refresh_summary={},
        readiness_summary={},
        warmup_summary={},
        backtest_audit_summary={},
        submission_audit_summary={},
        vector_summary={},
        elapsed=1.0,
    )

    counts = summary["llm_status_counts"]
    assert counts["non_executable"] == 2
    assert counts["provider_cooldown_skip"] == 2
    assert counts["provider_http_502"] == 4
    assert summary["pipeline_fallback_counts"]["cooldown_skip"] == 3
    assert "local_fallback_preferred_or_skip" not in counts
    assert "target_context_blocked" not in counts


def test_scheduler_feedback_uses_gate3_failure_results():
    from strategy_factory.application._factory_scheduler_loop import (
        update_scheduler_family_gate_feedback,
    )

    results = {
        "stages": {
            "submit": {
                "gate_3_input": 3,
                "gate_3_passed": 0,
                "gate_3_failed": 3,
                "submitted": 0,
                "created_audit_only": 3,
                "gate_3_failure_reason_topn": [
                    {"reason_code": "weak_wf_ic_ir", "count": 3}
                ],
                "incubation_budget_summary": {
                    "family_counts": {"ma_cross": 3},
                },
            },
        },
        "summary": {},
    }

    feedback, update = update_scheduler_family_gate_feedback({}, results, cycle_count=1)

    ma_cross = feedback["ma_cross"]
    assert ma_cross["ema_submit_count"] == 0.0
    assert ma_cross["gate_3_input_count"] == 3
    assert ma_cross["gate_3_passed_count"] == 0
    assert ma_cross["gate_failure_rate"] == 1.0
    assert ma_cross["cooldown_active"] is True
    assert ma_cross["suppressed"] is True
    assert update["control_counts"]["suppress"] == 1


def test_scheduler_feedback_exploration_reset_skips_cycle_zero():
    from strategy_factory.application._factory_scheduler_loop import (
        update_scheduler_family_gate_feedback,
    )

    feedback, update = update_scheduler_family_gate_feedback(
        {"ma_cross": {"ema_submit_count": 0.0}},
        {"stages": {"submit": {"gate_3_input": 0}}},
        cycle_count=0,
        ema_floor=0.15,
        exploration_reset_interval=20,
    )

    assert feedback["ma_cross"]["ema_submit_count"] == 0.15
    assert feedback["ma_cross"]["ema_submit_count"] != 0.5
    assert update["control_counts"]["normal"] == 1


def test_budget_feedback_controls_gate3_failure_rate():
    from strategy_factory.application._budget_feedback import resolve_feedback_metrics

    cooldown = resolve_feedback_metrics(
        {
            "ma_cross": {
                "strategy_count": 2,
                "gate_failure_rate": 0.75,
                "gate_3_input_count": 2,
            }
        },
        family="ma_cross",
    )
    suppressed = resolve_feedback_metrics(
        {
            "ma_cross": {
                "strategy_count": 3,
                "gate_failure_rate": 1.0,
                "gate_3_input_count": 3,
            }
        },
        family="ma_cross",
    )

    assert cooldown["family_control_mode"] == "cooldown"
    assert "family_gate_failure_rate_cooldown" in cooldown["control_reasons"]
    assert suppressed["family_control_mode"] == "suppress"
    assert suppressed["control_mode"] == "suppress"
    assert "family_gate_failure_rate_suppress" in suppressed["control_reasons"]


def test_spawner_feedback_blocks_failed_family_signal_variants():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    signal_candidates = [
        {
            "strategy_type": "ma_cross",
            "params": {"fast": 5},
            "trigger_thresholds": [{}, {}, {}],
        },
        {
            "strategy_type": "ma_cross",
            "params": {"fast": 10},
            "trigger_thresholds": [{}, {}, {}],
        },
    ]
    base_snapshot = {
        "fear_greed_index": 70,
        "north_fund_3d_net": 6_000_000_000,
    }

    expanded_without_feedback = spawner._expand_signal_variants(
        {**base_snapshot, "family_gate_feedback": {"ma_cross": {"ema_submit_count": 2.0}}},
        signal_candidates,
    )
    expanded_with_failed_feedback = spawner._expand_signal_variants(
        {
            **base_snapshot,
            "family_gate_feedback": {
                "ma_cross": {
                    "ema_submit_count": 2.0,
                    "gate_failure_rate": 1.0,
                    "cooldown_active": True,
                }
            },
        },
        signal_candidates,
    )

    assert len(expanded_without_feedback) > 0
    assert expanded_with_failed_feedback == []


def test_spawner_feedback_blocks_failed_family_quota_fill():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    current_candidates = [
        {
            "strategy_type": "quality_factor",
            "params": {},
            "trigger_thresholds": [{}],
        }
    ]
    base_snapshot = {
        "fear_greed_index": 50,
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "completeness": {"completion_ratio": 1.0},
    }

    fill_without_feedback = spawner._fill_gaps(base_snapshot, current_candidates)
    assert "ma_cross" in {candidate["strategy_type"] for candidate in fill_without_feedback}
    assert any(
        candidate["strategy_type"] == "ma_cross"
        and candidate.get("quota_fill", {}).get("parameter_source") == "fixed_defaults"
        for candidate in fill_without_feedback
    )

    fill_with_failed_feedback = spawner._fill_gaps(
        {
            **base_snapshot,
            "family_gate_feedback": {
                "ma_cross": {
                    "ema_submit_count": 2.0,
                    "gate_failure_rate": 1.0,
                    "cooldown_active": True,
                }
            },
        },
        current_candidates,
    )

    filled_types = {candidate["strategy_type"] for candidate in fill_with_failed_feedback}
    assert "ma_cross" not in filled_types
    assert "gap_fill" in filled_types


def test_spawner_feedback_filters_failed_family_from_raw_signals():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()

    candidates = spawner.spawn(
        {
            "fear_greed_index": 50,
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "completeness": {"completion_ratio": 1.0},
            "family_gate_feedback": {
                "ma_cross": {
                    "ema_submit_count": 2.0,
                    "gate_failure_rate": 1.0,
                    "cooldown_active": True,
                }
            },
        }
    )

    report_summary = spawner.get_last_report()["summary"]
    candidate_types = {candidate["strategy_type"] for candidate in candidates}
    assert "ma_cross" not in candidate_types
    assert report_summary["source_raw_counts"]["fear_greed"] >= 1
    assert report_summary["signal_feedback_limited_count"] >= 1
    assert report_summary["signal_feedback_limited_type_counts"]["ma_cross"] >= 1
    assert report_summary["signal_feedback_factor_by_type"]["ma_cross"] < 1.0


def test_spawner_missing_feedback_keeps_normal_quota_fill_budget():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    assert spawner._family_negative_feedback_factor("ma_cross", {}) == 1.0
    assert spawner._family_negative_feedback_factor(
        "ma_cross",
        {"family_gate_feedback": {}},
    ) == 1.0


def test_strategy_factory_run_summary_compaction_preserves_feedback_diagnostics():
    import json

    from aiask_quant_core.storage.sqlite.strategy_factory_json_budget import bounded_json_text

    summary = {
        "trace_id": "trace_quality_compaction",
        "gate_3_input": 3,
        "gate_3_passed": 0,
        "gate_3_failed": 3,
        "scheduler_cycle_count": 2,
        "family_gate_feedback_control_counts": {"suppress": 2, "cooldown": 1},
        "family_gate_feedback_updated_family_count": 3,
        "family_gate_feedback_active_families": ["momentum", "ma_cross", "value_factor"],
        "family_gate_feedback_gate_3_input": 3,
        "family_gate_feedback_gate_3_passed": 0,
        "family_gate_feedback_gate_3_failed": 3,
        "family_gate_feedback_failure_reason_topn": [
            {"reason_code": "weak_wf_ic_ir", "count": 3}
        ],
        "raw_results": [{"candidate_id": f"candidate_{index}", "payload": "x" * 256} for index in range(80)],
    }

    stored = json.loads(
        bounded_json_text("strategy_factory_runs.summary", summary, max_bytes=4096)
    )

    assert stored["storage_mode"] == "compact_json"
    assert stored["trace_id"] == "trace_quality_compaction"
    assert stored["gate_3_input"] == 3
    assert stored["gate_3_failed"] == 3
    assert stored["scheduler_cycle_count"] == 2
    assert stored["family_gate_feedback_control_counts"] == {"suppress": 2, "cooldown": 1}
    assert stored["family_gate_feedback_updated_family_count"] == 3
    assert stored["family_gate_feedback_active_families"] == ["momentum", "ma_cross", "value_factor"]
    assert stored["family_gate_feedback_failure_reason_topn"] == [
        {"reason_code": "weak_wf_ic_ir", "count": 3}
    ]
    assert "raw_results" not in stored
