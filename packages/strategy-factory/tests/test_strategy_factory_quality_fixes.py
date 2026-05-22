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

    assert not any(reason.startswith("missing_statistical_metrics") for reason in explicit_zero["reasons"])
    assert any(reason.startswith("walk_forward_ic_ir 0.000") for reason in explicit_zero["reasons"])
    assert any(reason.startswith("purged_kfold_ic 0.000") for reason in explicit_zero["reasons"])


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
