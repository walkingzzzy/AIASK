from __future__ import annotations

import asyncio

from strategy_factory.application.research.factor_research_builder import FactorResearchBuilder


class _FeedbackDb:
    async def list_strategies(self, status, *_args):
        if status != "submitted":
            return []
        return [
            {
                "id": "s-1",
                "status": "submitted",
                "strategy_type": "momentum",
                "params": {
                    "incubation_budget": {"track": "observe_incubation"},
                    "candidate_provenance": {"candidate_family": "momentum"},
                },
            }
        ]

    async def list_strategy_incubation_metrics(self, strategy_id, limit=1):
        assert strategy_id == "s-1"
        assert limit == 30
        return [
            {
                "metric_date": "2026-05-06",
                "daily_return": 0.01,
                "nav": 1.02,
                "hit_rate_5d": 0.62,
                "hit_rate_lcb_5d": 0.56,
                "skill_lcb_5d": 0.06,
                "effective_n_5d": 12,
                "recent_hit_rate_5d": 0.6,
                "recent_skill_lcb_5d": 0.04,
                "forward_ic_5d": 0.08,
                "forward_sharpe_5d": 0.7,
                "total_signals": 12,
                "total_orders": 3,
                "total_trades": 2,
            },
            {
                "metric_date": "2026-05-05",
                "daily_return": 0.0,
                "nav": 1.01,
                "total_signals": 10,
                "total_orders": 2,
                "total_trades": 1,
            },
        ]

    async def get_signal_stats(self, strategy_id):
        return {}

    async def get_latest_strategy_quality_report(self, strategy_id):
        return {
            "summary": {
                "raw_validation_grade": "B",
                "raw_validation_total_score": 68,
                "strict_incubation_ready": True,
                "validation_evidence_mode": "backtest_derived_fallback",
            },
            "validation_report": {
                "evidence_mode": "backtest_derived_fallback",
                "diagnostic_only": True,
            },
        }

    async def list_strategy_runtime_risk_events(self, **_kwargs):
        return []

    async def list_strategy_runtime_alerts(self, **_kwargs):
        return []

    async def get_latest_strategy_promotion_review(self, strategy_id):
        return None


class _PendingSubmittedFeedbackDb(_FeedbackDb):
    async def list_strategies(self, status, *_args):
        if status != "submitted":
            return []
        return [
            {
                "id": "pending-formal",
                "status": "submitted",
                "strategy_type": "multi_factor",
                "params": {
                    "incubation_budget": {"track": "formal_incubation"},
                    "candidate_provenance": {"candidate_family": "multi_factor"},
                },
            }
        ]

    async def list_strategy_incubation_metrics(self, strategy_id, limit=1):
        assert strategy_id == "pending-formal"
        return []

    async def get_latest_strategy_quality_report(self, strategy_id):
        return None


class _BrokenLifecycleRuntime:
    async def build_incubation_overview(self, db, strategy):
        return {
            "total_signals": 0,
            "observed_forward_days": [],
            "missing_forward_days": [1, 5, 10, 20],
            "promotion_ready": False,
            "signal_quality": {},
        }


def test_budget_feedback_uses_incubation_metric_proxy_when_signal_stats_are_empty(monkeypatch):
    monkeypatch.setattr(
        "strategy_factory.application.research.factor_research_builder.get_strategy_lifecycle_shared_runtime",
        lambda: _BrokenLifecycleRuntime(),
    )

    feedback = asyncio.run(FactorResearchBuilder._load_budget_feedback(_FeedbackDb(), {}))
    summary = feedback["summary"]

    assert summary["strategy_count"] == 1
    assert summary["signal_count_total"] == 12
    assert summary["zero_signal_strategy_count"] == 0
    assert summary["observed_forward_window_count"] >= 2
    assert summary["forward_window_coverage_ratio"] > 0
    assert summary["promotion_ready_count"] == 1
    assert summary["fallback_evidence_strategy_count"] == 1
    assert summary["fallback_evidence_mode_counts"]["incubation_metric_proxy"] == 1


def test_budget_feedback_separates_new_submitted_without_runtime_evidence(monkeypatch):
    monkeypatch.setattr(
        "strategy_factory.application.research.factor_research_builder.get_strategy_lifecycle_shared_runtime",
        lambda: _BrokenLifecycleRuntime(),
    )

    feedback = asyncio.run(FactorResearchBuilder._load_budget_feedback(_PendingSubmittedFeedbackDb(), {}))
    summary = feedback["summary"]

    assert summary["source_strategy_count"] == 1
    assert summary["strategy_count"] == 0
    assert summary["pending_evidence_refresh_count"] == 1
    assert summary["pending_evidence_refresh_strategy_ids"] == ["pending-formal"]
    assert summary["pending_evidence_refresh_reason_counts"] == {
        "submitted_runtime_evidence_pending": 1
    }
    assert summary["zero_signal_strategy_count"] == 0
    assert summary["zero_signal_ratio"] == 0.0
    assert summary["evidence_debt_ratio"] == 0.0
