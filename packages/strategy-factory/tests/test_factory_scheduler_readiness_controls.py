from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from strategy_factory.application.cycle_runner import (
    FactoryCycleOutcome,
    FactoryCycleRunner,
    FactoryRunContext,
)
from strategy_factory.application.candidate_contract import (
    build_candidate_contract_hash,
    build_portfolio_candidate_contract,
)
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
from strategy_factory.application.research_plane_contract import (
    RESEARCH_PLANE_CONTRACT_VERSION,
)
from strategy_factory.domain.targets import _extract_target_codes_from_payload


class _RefreshingFactorResearchGateway:
    def __init__(self):
        self.build_calls = 0
        self.refresh_calls = 0

    async def build_artifact(self, db, snapshot):
        self.build_calls += 1
        if self.refresh_calls == 0:
            return {
                "degraded": True,
                "lifecycle_feedback_input": {
                    "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                    "available": True,
                },
                "summary": {
                    "active_factor_count": 1,
                    "top_factor_names": ["value"],
                    "preferred_strategy_types": ["value_factor"],
                    "degraded": True,
                    "stale": True,
                    "freshness_days": 5,
                    "lifecycle_feedback_input_contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                    "lifecycle_feedback_input_available": True,
                    "budget_feedback_available": True,
                    "budget_feedback_family_count": 2,
                    "budget_feedback_strategy_count": 2,
                    "budget_feedback_target_pool_scope_count": 2,
                    "budget_feedback_generator_mode_scope_count": 2,
                    "budget_feedback_runtime_alert_count": 2,
                    "budget_feedback_runtime_risk_event_count": 2,
                },
            }
        return {
            "degraded": False,
            "lifecycle_feedback_input": {
                "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                "available": True,
            },
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "governed_source_candidate_count": 2,
                "top_factor_names": ["value"],
                "preferred_strategy_types": ["value_factor"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
                "governed_freshness_days": 0,
                "active_family_names": ["value"],
                "active_regime_names": ["bull"],
                "lifecycle_feedback_input_contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                "lifecycle_feedback_input_available": True,
                "budget_feedback_available": True,
                "budget_feedback_family_count": 2,
                "budget_feedback_strategy_count": 2,
                "budget_feedback_target_pool_scope_count": 2,
                "budget_feedback_generator_mode_scope_count": 2,
                "budget_feedback_runtime_alert_count": 2,
                "budget_feedback_runtime_risk_event_count": 2,
            },
        }

    def status(self):
        return {"running": False}

    async def refresh(self):
        self.refresh_calls += 1
        return {"computed": 8, "errors": 0, "quality_flags": []}


class _SeedFallbackRefreshGateway:
    def __init__(self):
        self.build_calls = 0
        self.refresh_calls = 0

    async def build_artifact(self, db, snapshot):
        self.build_calls += 1
        if self.refresh_calls == 0:
            return {
                "degraded": False,
                "summary": {
                    "active_factor_count": 1,
                    "active_candidate_count": 0,
                    "governed_source_candidate_count": 0,
                    "governed_blocked_candidate_count": 0,
                    "ranked_factor_count": 1,
                    "top_factor_names": ["value"],
                    "preferred_strategy_types": ["value_factor"],
                    "factor_source_mode": "seed_fallback",
                    "degraded": False,
                    "stale": False,
                    "freshness_days": 0,
                    "scheduler_last_run": None,
                    "scheduler_recent_success": False,
                },
            }
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "governed_source_candidate_count": 2,
                "governed_blocked_candidate_count": 0,
                "ranked_factor_count": 1,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
                "scheduler_last_run": "2026-04-05T10:00:00+08:00",
                "scheduler_recent_success": True,
                "scheduler_llm_validation_status": "success",
            },
            "active_candidate_pool": {
                "count": 2,
                "top_candidates": [
                    {
                        "artifact_id": "factor_validation_001",
                        "name": "sentiment_breakout_factor",
                        "family": "sentiment",
                        "expected_regime": ["trend"],
                    }
                ],
            },
        }

    def status(self):
        return {"running": False}

    async def refresh(self):
        self.refresh_calls += 1
        return {"computed": 12, "errors": 0, "quality_flags": []}


class _StaleFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": True,
            "summary": {
                "active_factor_count": 0,
                "top_factor_names": [],
                "preferred_strategy_types": [],
                "degraded": True,
                "stale": True,
                "freshness_days": 6,
            },
        }

    def status(self):
        return {"running": False}

    async def refresh(self):
        return {"computed": 0, "errors": 1, "quality_flags": ["failed"]}


class _GovernedPoolStaleFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "ranked_factor_count": 0,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum", "ma_cross"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": True,
                "freshness_days": 7,
            },
        }

    def status(self):
        return {"running": False}


class _GovernedPoolSnapshotFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "source_chain": ["quant_manager.factor_candidate_registry(active_pool)", "artifact_v2"],
            "active_candidate_pool": {
                "active_pool_mode": "strict_governed",
                "count": 2,
                "strict_count": 2,
                "provisional_count": 0,
                "family_summary": [
                    {
                        "family": "sentiment",
                        "count": 2,
                        "promote_count": 1,
                        "review_count": 1,
                        "avg_total_score": 82.5,
                        "max_total_score": 84.0,
                    }
                ],
                "regime_summary": [{"regime": "trend", "count": 2}],
                "top_candidates": [
                    {
                        "artifact_id": "factor_validation_001",
                        "name": "sentiment_breakout_factor",
                        "family": "sentiment",
                        "expected_regime": ["trend"],
                        "grade": "A",
                        "recommendation": "promote",
                        "pool_entry_mode": "strict_governed",
                        "total_score": 84.0,
                    }
                ],
            },
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "ranked_factor_count": 0,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum"],
                "factor_source_mode": "governed_candidate_pool",
                "governed_candidate_pool_mode": "strict_governed",
                "governed_candidate_pool_provisional": False,
                "governed_candidate_pool_strict_count": 2,
                "governed_candidate_pool_provisional_count": 0,
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
                "latest_factor_date": "2026-03-23",
                "quality_flags": ["governed_candidate_pool_active"],
            },
        }

    def status(self):
        return {"running": False}


class _ProvisionalGovernedPoolGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "active_candidate_pool": {
                "active_pool_mode": "provisional_validated_watch",
                "count": 1,
                "strict_count": 0,
                "provisional_count": 1,
                "source_count": 4,
                "top_candidates": [
                    {
                        "artifact_id": "factor_validation_watch_001",
                        "name": "watch_factor",
                        "family": "momentum",
                        "expected_regime": ["trend"],
                        "grade": "C",
                        "recommendation": "watch",
                        "registry_stage": "validated",
                        "pool_entry_mode": "provisional_validated_watch",
                        "total_score": 49.5,
                    }
                ],
                "family_summary": [
                    {
                        "family": "momentum",
                        "count": 1,
                        "promote_count": 0,
                        "review_count": 0,
                        "avg_total_score": 49.5,
                        "max_total_score": 49.5,
                    }
                ],
                "regime_summary": [{"regime": "trend", "count": 1}],
            },
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 1,
                "governed_source_candidate_count": 4,
                "governed_blocked_candidate_count": 2,
                "governed_blocked_ratio": 0.5,
                "governed_freshness_days": 0,
                "ranked_factor_count": 0,
                "top_factor_names": ["momentum"],
                "top_candidate_names": ["watch_factor"],
                "active_family_names": ["momentum"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum"],
                "factor_source_mode": "governed_candidate_pool",
                "governed_candidate_pool_mode": "provisional_validated_watch",
                "governed_candidate_pool_provisional": True,
                "governed_candidate_pool_strict_count": 0,
                "governed_candidate_pool_provisional_count": 1,
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
            },
        }

    def status(self):
        return {"running": False}


class _SchedulerRecentSuccessNoPoolGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 0,
                "active_candidate_count": 0,
                "governed_source_candidate_count": 0,
                "governed_blocked_candidate_count": 0,
                "governed_blocked_ratio": 0.0,
                "ranked_factor_count": 1,
                "top_factor_names": ["value"],
                "top_candidate_names": [],
                "active_family_names": [],
                "active_regime_names": [],
                "preferred_strategy_types": ["value_factor"],
                "factor_source_mode": "seed_fallback",
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
                "scheduler_recent_success": True,
                "scheduler_llm_validation_status": "success",
            },
        }

    def status(self):
        return {"running": False}


class _GovernedPoolHighBlockedRatioGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "governed_source_candidate_count": 8,
                "governed_blocked_candidate_count": 6,
                "governed_blocked_ratio": 0.75,
                "governed_freshness_days": 0,
                "ranked_factor_count": 0,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
            },
        }

    def status(self):
        return {"running": False}


class _DummyCollector:
    def __init__(self, *, degraded=False, completion_ratio=1.0):
        self._degraded = degraded
        self._completion_ratio = completion_ratio

    async def collect(self, _db):
        return {
            "date": "2026-03-20",
            "fear_greed_index": 58,
            "fg_level": "neutral",
            "listed_count": 1,
            "incubating_count": 0,
            "degraded": self._degraded,
            "completeness": {
                "completion_ratio": self._completion_ratio,
                "missing_sources": [] if not self._degraded else ["factor_ic"],
            },
            "failure_reasons": [] if not self._degraded else [{"source": "factor_ic"}],
            "sources": {
                "event_driven": {"status": "success"},
            },
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [],
            },
        }


class _DummySpawner:
    def spawn(self, _snapshot):
        return []

    def get_last_report(self):
        return {"summary": {"candidate_count": 0, "quota_fill_count": 0, "signal_trigger_count": 0}}


class _DummyFilter:
    async def filter(self, candidates, _db):
        return candidates

    def get_last_report(self):
        return {
            "summary": {
                "input_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }


class _DummyDedup:
    async def deduplicate(self, candidates, _db):
        return candidates

    def get_last_report(self):
        return {"summary": {"input_count": 0, "kept_count": 0, "dropped_count": 0}, "kept": [], "dropped": []}


class _DummySubmitter:
    async def submit(self, candidates, _snapshot, _db):
        return {
            "submitted": len(candidates),
            "passed_quality_gate": len(candidates),
            "gate_3_passed": len(candidates),
            "gate_3_failed": 0,
            "gate_3_provisional_passed": 0,
            "gate_3_failure_reason_topn": [],
            "strategies": list(candidates),
        }


class _DummyEliminator:
    async def check(self, _db, _fg_level):
        return []


class _AuditSpawner:
    def spawn(self, _snapshot):
        return [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519"],
                "dedup_result": {"refresh_mode": "refresh_metrics_only"},
            },
            {
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["601398"],
                "dedup_result": {"refresh_mode": "spawn_revision_from_existing"},
            },
            {
                "strategy_type": "mean_reversion",
                "params": {"lookback": 5, "threshold": 0.03},
                "target_symbols": ["600036"],
            },
        ]

    def get_last_report(self):
        return {"summary": {"candidate_count": 3, "quota_fill_count": 0, "signal_trigger_count": 3}}


class _AuditFilter:
    def __init__(self):
        self._last_report = {"summary": {}, "passed": [], "failed": []}

    async def filter(self, candidates, _db):
        candidates[0]["backtest_result"] = {
            "passed": True,
            "reason_code": "passed",
            "validation_focus": "event_target_only",
            "contamination_summary": {"representative_included": True, "mixed_layer_used": True},
            "cost_assumptions": {},
            "position_assumption": None,
        }
        candidates[0]["backtest_metrics"] = {}
        candidates[1]["backtest_result"] = {
            "passed": True,
            "reason_code": "passed",
            "validation_focus": "target_plus_representative",
            "contamination_summary": {"representative_included": False, "mixed_layer_used": False},
            "cost_assumptions": {"commission_bps": 8},
            "position_assumption": "equal_weight_proxy",
        }
        candidates[1]["backtest_metrics"] = {"cost_assumptions": {"commission_bps": 8}}
        candidates[2]["backtest_result"] = {
            "passed": True,
            "reason_code": "passed",
            "validation_focus": "target_plus_representative",
            "contamination_summary": {"representative_included": False, "mixed_layer_used": False},
            "cost_assumptions": {"commission_bps": 6},
            "position_assumption": "equal_weight_proxy",
        }
        candidates[2]["backtest_metrics"] = {"cost_assumptions": {"commission_bps": 6}}
        self._last_report = {
            "summary": {
                "input_count": 3,
                "passed_count": 3,
                "failed_count": 0,
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [
                {"strategy_type": item["strategy_type"], "backtest_result": dict(item.get("backtest_result") or {})}
                for item in candidates
            ],
            "failed": [],
        }
        return candidates

    def get_last_report(self):
        return self._last_report


class _AuditSubmitter:
    async def submit(self, candidates, _snapshot, _db):
        return {
            "created": 1,
            "created_total": 2,
            "created_strategy_pool": 1,
            "created_audit_only": 1,
            "gate_3_input": len(candidates),
            "submitted": 1,
            "passed_quality_gate": 1,
            "gate_3_passed": 1,
            "gate_3_failed": 2,
            "gate_3_provisional_passed": 0,
            "gate_3_failure_reason_topn": [],
            "strategies": [
                {
                    "strategy_id": "sid_1",
                    "strategy_type": "mean_reversion_short",
                    "candidate_family": "mean_reversion_short",
                    "generator_type": "rule",
                    "research_task": {"task_source": "snapshot"},
                    "created_total": False,
                    "created_strategy_pool": False,
                    "created_audit_only": False,
                    "refresh_mode": "refresh_metrics_only",
                    "refresh_decision_basis": "same_tested_object_and_identity",
                    "tested_object_hash_changed": False,
                    "existing_identity_available": True,
                    "existing_tested_object_available": True,
                    "revision_trigger_reason": None,
                    "constraint_check": {
                        "constraint_violation": "strict_intersection_empty",
                        "expansion_applied": True,
                        "intersection_ratio": 0.5,
                        "alignment_contract_violation": "coverage_ratio_below_contract",
                    },
                    "target_alignment_violation": "coverage_ratio_below_contract",
                    "generator_precompile_reject_reason": "missing_validation_profile",
                    "contract_reject_reasons": ["missing_validation_profile"],
                    "feedback_control_mode": "cooldown",
                    "feedback_target_pool_control_mode": "freeze",
                    "feedback_generator_mode_control_mode": "normal",
                    "warning_codes": ["preference_mismatch_warning"],
                    "gate_3": {
                        "passed": False,
                        "attempt_adjustment": {"penalty": 0.03},
                        "deflated_sharpe_proxy": -0.12,
                        "pbo_proxy": 0.71,
                        "multiple_testing_mode": "formal_runtime",
                        "deflated_sharpe_ratio": 0.12,
                        "pbo": 0.68,
                        "white_reality_check_pvalue": 0.24,
                        "hansen_spa_pvalue": 0.31,
                    },
                    "incubation_budget": {
                        "feedback_metrics": {
                            "control_mode": "cooldown",
                            "target_pool_control_mode": "freeze",
                            "generator_mode_control_mode": "normal",
                            "target_pool_freeze_active": True,
                            "generator_mode_freeze_active": False,
                        }
                    },
                    "submission_action_type": "research_only",
                },
                {
                    "strategy_id": "sid_2",
                    "strategy_type": "volatility_breakout",
                    "candidate_family": "volatility_breakout",
                    "generator_type": "external_llm",
                    "research_task": {"task_source": "event_driven"},
                    "created_total": True,
                    "created_strategy_pool": True,
                    "created_audit_only": False,
                    "status": "submitted",
                    "submission_lane": "live_ready_review",
                    "submission_action_type": "runtime_review",
                    "live_candidate_ready": True,
                    "live_review_ready": True,
                    "direct_trade_candidate": True,
                    "paper_account_id": "paper_sid_2",
                    "runtime_control_mode": "monitor",
                    "runtime_control_status": "active",
                    "promotion_review_id": "promotion_review_sid_2",
                    "promotion_review_status": "watch",
                    "promotion_review_recommendation": "observe",
                    "refresh_mode": "spawn_revision_from_existing",
                    "refresh_decision_basis": "tested_object_changed",
                    "tested_object_hash_changed": True,
                    "existing_identity_available": True,
                    "existing_tested_object_available": True,
                    "revision_trigger_reason": "tested_object_changed",
                    "constraint_check": {
                        "constraint_violation": None,
                        "expansion_applied": False,
                        "intersection_ratio": 1.0,
                    },
                    "feedback_control_mode": "normal",
                    "feedback_target_pool_control_mode": "normal",
                    "feedback_generator_mode_control_mode": "freeze",
                    "warning_codes": [],
                    "gate_3": {
                        "passed": True,
                        "attempt_adjustment": {"penalty": 0.05},
                        "deflated_sharpe_proxy": 0.18,
                        "pbo_proxy": 0.24,
                        "multiple_testing_mode": "formal_runtime",
                        "deflated_sharpe_ratio": 0.84,
                        "pbo": 0.19,
                        "white_reality_check_pvalue": 0.07,
                        "hansen_spa_pvalue": 0.05,
                    },
                    "incubation_budget": {
                        "feedback_metrics": {
                            "control_mode": "normal",
                            "target_pool_control_mode": "normal",
                            "generator_mode_control_mode": "freeze",
                            "target_pool_freeze_active": False,
                            "generator_mode_freeze_active": True,
                        }
                    },
                },
                {
                    "strategy_id": "sid_3",
                    "strategy_type": "sector_rotation",
                    "candidate_family": "sector_rotation",
                    "generator_type": "rule",
                    "research_task": {"task_source": "bulk_stock_matrix"},
                    "created_total": True,
                    "created_strategy_pool": False,
                    "created_audit_only": True,
                    "submission_action_type": "research_only",
                    "refresh_mode": None,
                    "refresh_decision_basis": "no_refresh_basis",
                    "tested_object_hash_changed": False,
                    "existing_identity_available": False,
                    "existing_tested_object_available": False,
                    "revision_trigger_reason": None,
                    "constraint_check": {
                        "constraint_violation": None,
                        "expansion_applied": False,
                        "intersection_ratio": None,
                    },
                    "feedback_control_mode": "normal",
                    "feedback_target_pool_control_mode": "normal",
                    "feedback_generator_mode_control_mode": "normal",
                    "warning_codes": [],
                    "gate_3": {
                        "passed": False,
                    },
                    "incubation_budget": {
                        "feedback_metrics": {
                            "control_mode": "normal",
                            "target_pool_control_mode": "normal",
                            "generator_mode_control_mode": "normal",
                            "target_pool_freeze_active": False,
                            "generator_mode_freeze_active": False,
                        }
                    },
                },
            ],
        }


async def _empty_scan(_self, _db, _snapshot):
    return {"summary": {"task_count": 0, "task_sources": {}, "task_types": {}}, "tasks": []}


def _patch_factory(monkeypatch, db, collector):
    async def _noop_warmup_runner(**kwargs):
        return {
            "ok": True,
            "status": "skipped",
            "task_type": kwargs.get("task_type"),
            "force": bool(kwargs.get("force")),
            "matched": 0,
            "executed": 0,
            "failed": 0,
            "executed_task_ids": [],
            "failed_schedule_ids": [],
            "schedules": [],
        }

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", collector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _empty_scan)
    monkeypatch.setattr("strategy_factory.application.factory_scheduler.get_runtime_warmup_runner", lambda: _noop_warmup_runner)


def test_extract_target_codes_from_payload_reads_research_task_context():
    payload = {
        "research_task": {
            "target_symbols": ["601398", "601288"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600036"]},
            "event_context": {"target_symbols": ["601166"]},
        }
    }

    assert _extract_target_codes_from_payload(payload, limit=6) == ["601398", "601288", "600036", "601166"]


def test_scheduler_enriches_candidate_targeting_from_research_task():
    candidate = {
        "strategy_type": "dsl_rule",
        "params": {"dsl": {"entry": {"all": []}, "metadata": {}}},
        "tags": ["ai_generated"],
    }
    task = {
        "task_id": "event_hot_banks",
        "task_source": "event_driven",
        "target_symbols": ["601398", "601288", "600036"],
        "event_context": {
            "event_id": "evt_hot_banks",
            "theme_code": "high_dividend_banks",
            "target_symbols": ["601398", "601288", "600036"],
        },
    }

    enriched = StrategyFactoryScheduler._enrich_candidate_targeting(candidate, task)

    assert enriched["target_symbols"] == ["601398", "601288", "600036"]
    assert enriched["stock_pool"]["symbols"] == ["601398", "601288", "600036"]
    assert enriched["research_task"]["task_id"] == "event_hot_banks"
    assert enriched["event_context"]["event_id"] == "evt_hot_banks"
    assert enriched["params"]["target_symbols"] == ["601398", "601288", "600036"]
    assert enriched["params"]["stock_pool"]["symbols"] == ["601398", "601288", "600036"]
    assert enriched["params"]["dsl"]["metadata"]["target_symbols"] == ["601398", "601288", "600036"]
    assert "targeted_universe" in enriched["tags"]


@pytest.mark.asyncio
async def test_scheduler_refreshes_stale_factor_research_before_continuing(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    gateway = _RefreshingFactorResearchGateway()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=gateway)

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert gateway.refresh_calls == 1
    assert gateway.build_calls == 2
    assert result["stages"]["factor_research"]["refresh_attempted"] is True
    assert result["stages"]["factor_research"]["refresh_status"] == "success"
    assert result["summary"]["factor_research_stale"] is False
    assert result["summary"]["factor_research_refresh_status"] == "success"
    assert result["summary"]["factory_readiness_can_proceed"] is True


@pytest.mark.asyncio
async def test_scheduler_refreshes_seed_fallback_when_governed_pool_is_missing(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    gateway = _SeedFallbackRefreshGateway()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=gateway)

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert gateway.refresh_calls == 1
    assert gateway.build_calls == 2
    assert result["stages"]["factor_research"]["refresh_attempted"] is True
    assert result["stages"]["factor_research"]["refresh_trigger"] == "scheduler_warmup_missing_governed_pool"
    assert result["stages"]["factor_research"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["summary"]["factor_research_refresh_status"] == "success"
    assert result["summary"]["factor_research_refresh_trigger"] == "scheduler_warmup_missing_governed_pool"
    assert result["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["summary"]["governed_candidate_pool_active"] is True


@pytest.mark.asyncio
async def test_scheduler_summary_surfaces_bulk_stock_matrix_counts(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    async def _fake_run_autonomy_batches(_db, _snapshot):
        return {
            "stage": {
                "generated_count": 0,
                "task_count": 3,
                "completed_task_count": 3,
                "failed_task_count": 0,
                "event_task_count": 0,
                "snapshot_task_count": 1,
                "bulk_stock_task_count": 2,
                "task_source_counts": {"snapshot": 1, "bulk_stock_matrix": 2},
                "task_scan": {
                    "summary": {
                        "bulk_stock_matrix_enabled": True,
                        "bulk_stock_matrix_stock_count": 2,
                        "bulk_stock_matrix_eligible_stock_count": 3,
                        "bulk_stock_matrix_family_counts": {"momentum": 1, "mean_reversion": 1},
                        "bulk_stock_matrix_universe_limit": 500,
                        "bulk_stock_matrix_requested_universe_offset": 500,
                        "bulk_stock_matrix_effective_universe_offset": 0,
                        "bulk_stock_matrix_universe_offset_fallback": True,
                        "bulk_stock_matrix_next_universe_offset": 500,
                        "bulk_stock_matrix_cursor_wrapped": True,
                        "bulk_stock_matrix_cursor_source": "persisted_run",
                        "bulk_stock_matrix_cursor_resume_from_run_id": "factory_run_hist_1",
                        "bulk_stock_matrix_effective_task_budget": 6,
                        "bulk_stock_matrix_max_candidates_per_run": 6,
                        "bulk_stock_matrix_estimated_candidate_count": 2,
                        "bulk_stock_matrix_tasks_per_shard": 2,
                        "bulk_stock_matrix_shard_count": 1,
                        "bulk_stock_matrix_stock_coverage_ratio": 0.6667,
                        "bulk_stock_matrix_allocation_mode": "stock_round_robin_by_family_rank",
                        "bulk_stock_matrix_allocation_pass_counts": {"1": 2},
                        "bulk_stock_matrix_overflow_task_count": 4,
                        "task_sources": {"snapshot": 1, "bulk_stock_matrix": 2},
                        "task_types": {"snapshot": 1, "bulk_stock_matrix": 2},
                    }
                },
            },
            "candidates": [],
            "experiments": [],
        }

    monkeypatch.setattr(scheduler, "_run_autonomy_batches", _fake_run_autonomy_batches)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert result["summary"]["bulk_stock_task_count"] == 2
    assert result["summary"]["bulk_stock_matrix_enabled"] is True
    assert result["summary"]["bulk_stock_matrix_stock_count"] == 2
    assert result["summary"]["bulk_stock_matrix_eligible_stock_count"] == 3
    assert result["summary"]["bulk_stock_matrix_family_counts"] == {"momentum": 1, "mean_reversion": 1}
    assert result["summary"]["bulk_stock_matrix_universe_limit"] == 500
    assert result["summary"]["bulk_stock_matrix_requested_universe_offset"] == 500
    assert result["summary"]["bulk_stock_matrix_effective_universe_offset"] == 0
    assert result["summary"]["bulk_stock_matrix_universe_offset_fallback"] is True
    assert result["summary"]["bulk_stock_matrix_next_universe_offset"] == 500
    assert result["summary"]["bulk_stock_matrix_cursor_wrapped"] is True
    assert result["summary"]["bulk_stock_matrix_cursor_source"] == "persisted_run"
    assert result["summary"]["bulk_stock_matrix_cursor_resume_from_run_id"] == "factory_run_hist_1"
    assert result["summary"]["bulk_stock_matrix_effective_task_budget"] == 6
    assert result["summary"]["bulk_stock_matrix_max_candidates_per_run"] == 6
    assert result["summary"]["bulk_stock_matrix_estimated_candidate_count"] == 2
    assert result["summary"]["bulk_stock_matrix_tasks_per_shard"] == 2
    assert result["summary"]["bulk_stock_matrix_shard_count"] == 1
    assert result["summary"]["bulk_stock_matrix_stock_coverage_ratio"] == 0.6667
    assert result["summary"]["bulk_stock_matrix_allocation_mode"] == "stock_round_robin_by_family_rank"
    assert result["summary"]["bulk_stock_matrix_allocation_pass_counts"] == {"1": 2}
    assert result["summary"]["bulk_stock_matrix_overflow_task_count"] == 4


@pytest.mark.asyncio
async def test_scheduler_resumes_bulk_stock_matrix_cursor_from_persisted_run(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    db.get_latest_strategy_factory_run = AsyncMock(
        return_value={
            "run_id": "factory_run_hist_cursor",
            "summary": {
                "bulk_stock_matrix_enabled": True,
                "bulk_stock_matrix_universe_limit": 500,
                "bulk_stock_matrix_requested_universe_offset": 500,
                "bulk_stock_matrix_effective_universe_offset": 500,
                "bulk_stock_matrix_universe_offset_fallback": False,
                "bulk_stock_matrix_eligible_stock_count": 500,
                "bulk_stock_matrix_next_universe_offset": 1000,
                "bulk_stock_matrix_cursor_wrapped": False,
            },
        }
    )
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())
    captured_snapshot = {}

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    async def _fake_bulk_plan(_self, _db, snapshot):
        captured_snapshot.update(snapshot)
        requested_offset = int(snapshot.get("bulk_stock_matrix_universe_offset") or 0)
        return {
            "summary": {
                "enabled": True,
                "task_count": 0,
                "stock_count": 0,
                "eligible_stock_count": 500,
                "family_counts": {},
                "universe_limit": 500,
                "requested_universe_offset": requested_offset,
                "effective_universe_offset": requested_offset,
                "universe_offset_fallback": False,
                "next_universe_offset": requested_offset + 500,
                "cursor_wrapped": False,
                "effective_task_budget": 0,
                "max_candidates_per_run": 0,
                "estimated_candidate_count": 0,
                "tasks_per_shard": 0,
                "shard_count": 0,
                "stock_coverage_ratio": 0.0,
                "allocation_mode": "stock_round_robin_by_family_rank",
                "allocation_pass_counts": {},
                "overflow_task_count": 0,
            },
            "tasks": [],
        }

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        _fake_bulk_plan,
    )

    result = await scheduler.run_once()

    assert captured_snapshot["bulk_stock_matrix_universe_offset"] == 1000
    assert captured_snapshot["bulk_stock_matrix_cursor_source"] == "persisted_run"
    assert captured_snapshot["bulk_stock_matrix_cursor_resume_from_run_id"] == "factory_run_hist_cursor"
    assert result["summary"]["bulk_stock_matrix_requested_universe_offset"] == 1000
    assert result["summary"]["bulk_stock_matrix_next_universe_offset"] == 1500
    assert result["summary"]["bulk_stock_matrix_cursor_source"] == "persisted_run"
    assert result["summary"]["bulk_stock_matrix_cursor_resume_from_run_id"] == "factory_run_hist_cursor"


@pytest.mark.asyncio
async def test_scheduler_falls_back_to_default_bulk_cursor_when_persisted_run_lookup_fails():
    db = MagicMock()
    db.get_latest_strategy_factory_run = AsyncMock(side_effect=ConnectionRefusedError("db offline"))
    scheduler = StrategyFactoryScheduler()

    cursor = await scheduler._resolve_bulk_stock_matrix_cursor(db)

    assert cursor["source"] == "default"
    assert cursor["available"] is False
    assert cursor["next_universe_offset"] == 0
    assert cursor["resume_from_run_id"] is None


@pytest.mark.asyncio
async def test_scheduler_skips_bulk_lane_outside_configured_run_window(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    db.get_latest_strategy_factory_run = AsyncMock(return_value=None)
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.STOCK_STRATEGY_MATRIX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.STOCK_STRATEGY_MATRIX_RUN_WINDOW",
        "off_hours",
    )
    monkeypatch.setattr(
        scheduler,
        "_now",
        lambda: datetime(2026, 4, 3, 10, 5, 0, tzinfo=scheduler._market_timezone),
    )

    async def _unexpected_bulk_plan(_self, _db, _snapshot):
        raise AssertionError("bulk planner should be skipped outside configured run window")

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        _unexpected_bulk_plan,
    )

    result = await scheduler.run_once()
    status = scheduler.status()

    assert result["summary"]["bulk_stock_matrix_enabled"] is False
    assert result["summary"]["bulk_stock_matrix_configured_enabled"] is True
    assert result["summary"]["bulk_stock_matrix_run_window"] == "off_hours"
    assert result["summary"]["bulk_stock_matrix_run_window_active"] is False
    assert result["summary"]["bulk_stock_matrix_run_window_current_period"] == "market_hours"
    assert result["summary"]["bulk_stock_matrix_skip_reason"] == "outside_run_window"
    assert status["bulk_stock_matrix_config"]["run_window"] == "off_hours"
    assert status["bulk_stock_matrix_config"]["run_window_active"] is False
    assert status["bulk_stock_matrix_config"]["run_window_current_period"] == "market_hours"


@pytest.mark.asyncio
async def test_scheduler_runs_startup_warmup_before_collect(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    gateway = _RefreshingFactorResearchGateway()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=gateway)
    warmup_calls = []

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    async def _fake_warmup_runner(**kwargs):
        warmup_calls.append(dict(kwargs))
        return {
            "ok": True,
            "status": "completed",
            "task_type": kwargs.get("task_type"),
            "force": bool(kwargs.get("force")),
            "matched": 1,
            "executed": 1,
            "failed": 0,
            "executed_task_ids": ["sync_core_market_1"],
            "failed_schedule_ids": [],
            "schedules": [],
        }

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setattr("strategy_factory.application.factory_scheduler.get_runtime_warmup_runner", lambda: _fake_warmup_runner)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert len(warmup_calls) == 1
    assert warmup_calls[0]["task_type"] == "core_market,factor_context"
    assert result["stages"]["warmup"]["status"] == "completed"
    assert result["stages"]["warmup"]["executed"] == 1
    assert result["summary"]["warmup_status"] == "completed"
    assert result["summary"]["warmup_executed"] == 1


@pytest.mark.asyncio
async def test_scheduler_can_hard_block_on_factory_readiness(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_StaleFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=True, completion_ratio=0.4)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    result = await scheduler.run_once()

    assert result["status"] == "skipped"
    assert result["summary"]["skip_reason"] == "readiness_blocked"
    assert result["summary"]["factory_readiness_can_proceed"] is False
    assert result["summary"]["factory_readiness_blocker_count"] >= 1
    assert result["summary"]["factory_readiness_decision"] == "blocked"
    assert result["summary"]["factory_readiness_blocking_stage"] == "readiness"
    assert "snapshot_completion_too_low" in result["summary"]["factory_readiness_blocking_reason_codes"]
    assert "snapshot_completion_too_low" in result["stages"]["readiness"]["blockers"]
    assert result["stages"]["readiness"]["decision"] == "blocked"
    assert result["stages"]["readiness"]["skip_reason"] == "readiness_blocked"
    assert result["research_plane"]["contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
    assert result["research_plane"]["research_artifact"]["available"] is True
    assert result["research_plane"]["task_artifact"]["available"] is False
    assert result["summary"]["research_plane_contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
    assert result["summary"]["research_task_count"] == 0


@pytest.mark.asyncio
async def test_scheduler_governed_candidate_pool_can_bypass_legacy_factor_stale_block(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_GovernedPoolStaleFactorResearchGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    result = await scheduler.run_once()

    assert result["status"] == "partial"
    assert result["stages"]["readiness"]["can_proceed"] is True
    assert result["stages"]["readiness"]["status"] == "partial"
    assert result["stages"]["readiness"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["stages"]["readiness"]["governed_candidate_pool_active"] is True
    assert result["stages"]["readiness"]["active_candidate_count"] == 2
    assert "factor_research_history_stale_governed_pool_active" in result["stages"]["readiness"]["warnings"]
    assert result["stages"]["factor_research"]["active_family_count"] == 1
    assert result["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["summary"]["active_candidate_count"] == 2
    assert result["summary"]["governed_candidate_pool_active"] is True


@pytest.mark.asyncio
async def test_scheduler_readiness_allows_provisional_governed_candidate_pool(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_ProvisionalGovernedPoolGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    result = await scheduler.run_once()

    assert result["status"] in {"partial", "success"}
    assert result["stages"]["readiness"]["can_proceed"] is True
    assert result["stages"]["readiness"]["governed_candidate_pool_active"] is True
    assert result["stages"]["readiness"]["governed_candidate_pool_mode"] == "provisional_validated_watch"
    assert result["stages"]["readiness"]["governed_candidate_pool_provisional"] is True
    assert "governed_candidate_pool_provisional" in result["stages"]["readiness"]["warnings"]
    assert result["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["summary"]["governed_candidate_pool_mode"] == "provisional_validated_watch"
    assert result["summary"]["governed_candidate_pool_provisional"] is True
    assert result["summary"]["governed_candidate_pool_active"] is True


@pytest.mark.asyncio
async def test_scheduler_readiness_surfaces_recent_scheduler_success_without_governed_pool(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_SchedulerRecentSuccessNoPoolGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "skipped"
    assert result["summary"]["skip_reason"] == "readiness_blocked"
    assert "factor_scheduler_recent_success_without_governed_pool" in result["stages"]["readiness"]["warnings"]
    assert "governed_candidate_pool_missing_after_scheduler_success" in result["stages"]["readiness"]["blockers"]
    assert result["stages"]["readiness"]["governed_pool_missing_after_scheduler_success"] is True
    assert result["stages"]["readiness"]["can_proceed"] is False
    assert result["summary"]["scheduler_recent_success"] is True
    assert result["summary"]["scheduler_llm_validation_status"] == "success"


@pytest.mark.asyncio
async def test_scheduler_readiness_penalizes_high_governed_blocked_ratio(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_GovernedPoolHighBlockedRatioGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] in {"partial", "success"}
    assert "governed_candidate_pool_blocked_ratio_high" in result["stages"]["readiness"]["warnings"]
    assert result["stages"]["readiness"]["governed_blocked_ratio"] == pytest.approx(0.75)
    assert result["summary"]["governed_blocked_ratio"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_scheduler_snapshot_summary_persists_compact_active_pool(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_GovernedPoolSnapshotFactorResearchGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    persisted = db.save_strategy_factory_run.await_args.args[0]
    compact_pool = result["snapshot_summary"]["factor_research"]["active_candidate_pool"]

    assert result["status"] == "success"
    assert compact_pool["count"] == 2
    assert compact_pool["active_pool_mode"] == "strict_governed"
    assert compact_pool["strict_count"] == 2
    assert compact_pool["top_candidates"][0]["artifact_id"] == "factor_validation_001"
    assert compact_pool["top_candidates"][0]["recommendation"] == "promote"
    assert compact_pool["top_candidates"][0]["pool_entry_mode"] == "strict_governed"
    assert compact_pool["family_summary"][0]["family"] == "sentiment"
    assert persisted["snapshot_summary"]["factor_research"]["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert persisted["snapshot_summary"]["factor_research"]["summary"]["governed_candidate_pool_mode"] == "strict_governed"
    assert persisted["snapshot_summary"]["factor_research"]["active_candidate_pool"]["top_candidates"][0]["name"] == "sentiment_breakout_factor"


@pytest.mark.asyncio
async def test_scheduler_summary_exposes_run_level_audit_metrics(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _AuditSpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _AuditFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _AuditSubmitter)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert result["summary"]["created"] == 1
    assert result["summary"]["created_total"] == 2
    assert result["summary"]["created_strategy_pool"] == 1
    assert result["summary"]["created_audit_only"] == 1
    assert result["summary"]["attempt_adjusted_gate_failed"] == 1
    assert result["summary"]["attempt_adjusted_score_avg"] == pytest.approx(0.04)
    assert result["summary"]["constraint_violation_count"] == 1
    assert result["summary"]["target_symbol_intersection_ratio_avg"] == pytest.approx(0.75)
    assert result["summary"]["universe_expansion_count"] == 1
    assert result["summary"]["preference_mismatch_warning_count"] == 1
    assert result["summary"]["event_window_contamination_warning_count"] == 1
    assert result["summary"]["cost_audit_missing_count"] == 1
    assert result["summary"]["deflated_sharpe_proxy_avg"] == pytest.approx(0.03)
    assert result["summary"]["deflated_sharpe_ratio_avg"] == pytest.approx(0.48)
    assert result["summary"]["high_pbo_proxy_count"] == 1
    assert result["summary"]["high_pbo_count"] == 1
    assert result["summary"]["formal_multiple_testing_count"] == 2
    assert result["summary"]["weak_white_reality_check_count"] == 1
    assert result["summary"]["weak_hansen_spa_count"] == 1
    assert result["summary"]["live_ready_review_count"] == 1
    assert result["summary"]["direct_trade_candidate_count"] == 1
    assert result["summary"]["paper_account_bound_count"] == 1
    assert result["summary"]["runtime_review_count"] == 1
    assert result["summary"]["promotion_review_count"] == 1
    assert result["summary"]["promotion_review_status_counts"] == {"watch": 1}
    assert result["summary"]["refresh_metrics_only_count"] == 1
    assert result["summary"]["spawn_revision_from_existing_count"] == 1
    assert result["summary"]["refresh_decision_basis_counts"] == {
        "same_tested_object_and_identity": 1,
        "tested_object_changed": 1,
        "no_refresh_basis": 1,
    }
    assert result["summary"]["revision_trigger_reason_counts"] == {"tested_object_changed": 1}
    assert result["summary"]["tested_object_hash_changed_count"] == 1
    assert result["summary"]["existing_identity_available_count"] == 2
    assert result["summary"]["existing_tested_object_available_count"] == 2
    assert result["summary"]["target_alignment_violation_counts"] == {"coverage_ratio_below_contract": 1}
    assert result["summary"]["generator_precompile_reject_reason_counts"] == {"missing_validation_profile": 1}
    assert result["summary"]["contract_reject_reason_counts"] == {"missing_validation_profile": 1}
    assert result["summary"]["feedback_control_mode_counts"] == {"cooldown": 1, "normal": 2}
    assert result["summary"]["feedback_target_pool_control_mode_counts"] == {"freeze": 1, "normal": 2}
    assert result["summary"]["feedback_generator_mode_control_mode_counts"] == {"normal": 2, "freeze": 1}
    assert result["research_plane"]["contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
    assert result["research_plane"]["task_artifact"]["available"] is True
    assert result["research_plane"]["candidate_artifact"]["available"] is True
    assert result["summary"]["research_plane_contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
    assert (
        result["summary"]["research_candidate_count"]
        == result["research_plane"]["candidate_artifact"]["candidate_count"]
    )
    assert (
        result["summary"]["research_experiment_count"]
        == result["research_plane"]["evidence_artifact"]["experiment_count"]
    )
    assert (
        result["summary"]["research_task_evidence_count"]
        == result["research_plane"]["evidence_artifact"]["task_evidence_count"]
    )
    assert (
        result["summary"]["research_summary"]["research_plane_contract_version"]
        == RESEARCH_PLANE_CONTRACT_VERSION
    )
    assert result["summary"]["research_summary"]["task_contract_observed"] is True
    assert result["summary"]["research_summary"]["gate_2_passed"] == 3
    assert result["summary"]["research_summary"]["source_mix"]["generator_type_counts"] == {"rule": 2, "external_llm": 1}
    assert result["summary"]["research_summary"]["source_mix"]["task_source_counts"] == {
        "snapshot": 1,
        "event_driven": 1,
        "bulk_stock_matrix": 1,
    }
    assert result["summary"]["research_summary"]["family_mix"] == {
        "mean_reversion_short": 1,
        "volatility_breakout": 1,
        "sector_rotation": 1,
    }
    assert result["summary"]["research_summary"]["gate_hit"]["gate_2_passed"] == 3
    assert result["summary"]["research_summary"]["refresh_ratio"]["ratio"] == pytest.approx(0.6667, abs=1e-4)
    assert result["summary"]["research_summary"]["promotion_ratio"]["ratio"] == pytest.approx(0.3333, abs=1e-4)
    assert result["summary"]["incubation_summary"]["gate_3_failed"] == 2
    assert result["summary"]["incubation_summary"]["submission_lane_counts"]["live_ready_review"] == 1
    assert result["summary"]["incubation_summary"]["submission_action_type_counts"]["runtime_review"] == 1
    assert result["summary"]["incubation_summary"]["submission_action_type_counts"]["research_only"] == 2
    assert result["summary"]["incubation_summary"]["refresh_decision_basis_counts"]["tested_object_changed"] == 1
    assert result["summary"]["incubation_summary"]["revision_trigger_reason_counts"] == {"tested_object_changed": 1}
    assert result["summary"]["incubation_summary"]["tested_object_hash_changed_count"] == 1
    assert result["summary"]["incubation_summary"]["target_alignment_violation_counts"] == {
        "coverage_ratio_below_contract": 1
    }
    assert result["summary"]["incubation_summary"]["generator_precompile_reject_reason_counts"] == {
        "missing_validation_profile": 1
    }
    assert result["summary"]["incubation_summary"]["contract_reject_reason_counts"] == {
        "missing_validation_profile": 1
    }
    assert result["summary"]["incubation_summary"]["feedback_control_mode_counts"] == {"cooldown": 1, "normal": 2}
    assert result["summary"]["incubation_summary"]["feedback_target_pool_control_mode_counts"] == {
        "freeze": 1,
        "normal": 2,
    }
    assert result["summary"]["incubation_summary"]["feedback_generator_mode_control_mode_counts"] == {
        "normal": 2,
        "freeze": 1,
    }
    assert result["summary"]["incubation_summary"]["family_mix"]["volatility_breakout"] == 1
    assert result["summary"]["incubation_summary"]["gate_hit"]["gate_3_passed"] == 1
    assert result["summary"]["incubation_summary"]["refresh_ratio"]["mode_counts"] == {
        "refresh_metrics_only": 1,
        "spawn_revision_from_existing": 1,
    }
    assert result["summary"]["incubation_summary"]["promotion_ratio"]["ratio"] == pytest.approx(0.3333, abs=1e-4)
    assert result["summary"]["live_ready_summary"]["live_candidate_ready_count"] == 1
    assert result["summary"]["live_ready_summary"]["live_review_ready_count"] == 1
    assert result["summary"]["live_ready_summary"]["submission_action_type_counts"]["runtime_review"] == 1
    assert result["summary"]["live_ready_summary"]["promotion_review_status_counts"] == {"watch": 1}
    assert result["summary"]["live_ready_summary"]["source_mix"]["submission_lane_counts"] == {"live_ready_review": 1}
    assert result["summary"]["live_ready_summary"]["family_mix"] == {"volatility_breakout": 1}
    assert result["summary"]["live_ready_summary"]["gate_hit"]["promotion_review_count"] == 1
    assert result["summary"]["live_ready_summary"]["refresh_ratio"]["ratio"] == pytest.approx(1.0)
    assert result["summary"]["live_ready_summary"]["promotion_ratio"]["ratio"] == pytest.approx(1.0)
    assert result["summary"]["feedback_summary"]["lifecycle_feedback_input_observed"] is True
    assert (
        result["summary"]["feedback_summary"]["lifecycle_feedback_input_contract_version"]
        == "strategy_factory.lifecycle_feedback_input.v1"
    )
    assert result["summary"]["feedback_summary"]["family_count"] == 2
    assert result["summary"]["feedback_summary"]["strategy_count"] == 2
    assert result["summary"]["feedback_summary"]["target_pool_scope_count"] == 2
    assert result["summary"]["feedback_summary"]["generator_mode_scope_count"] == 2
    assert result["summary"]["feedback_summary"]["runtime_alert_count"] == 2
    assert result["summary"]["feedback_summary"]["runtime_risk_event_count"] == 2
    assert result["summary"]["feedback_summary"]["submission_control_mode_counts"] == {"cooldown": 1, "normal": 2}
    assert result["summary"]["feedback_summary"]["submission_target_pool_control_mode_counts"] == {
        "freeze": 1,
        "normal": 2,
    }
    assert result["summary"]["feedback_summary"]["submission_generator_mode_control_mode_counts"] == {
        "normal": 2,
        "freeze": 1,
    }


@pytest.mark.asyncio
async def test_scheduler_marks_run_partial_when_run_persistence_fails(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock(side_effect=RuntimeError("run persistence unavailable"))
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "partial"
    assert result["summary"]["persistence_failure_count"] == 1
    assert result["summary"]["persistence_failures"][0]["operation"] == "save_strategy_factory_run"


def test_build_layered_run_summary_exposes_feedback_summary_contract():
    summary = {
        "lifecycle_feedback_input_contract_version": "strategy_factory.lifecycle_feedback_input.v1",
        "lifecycle_feedback_input_available": True,
        "budget_feedback_available": True,
        "budget_feedback_family_count": 3,
        "budget_feedback_strategy_count": 9,
        "budget_feedback_target_pool_scope_count": 4,
        "budget_feedback_generator_mode_scope_count": 2,
        "budget_feedback_runtime_alert_count": 5,
        "budget_feedback_runtime_risk_event_count": 6,
        "blocked_feedback_task_count": 2,
        "planned_feedback_cooldown_task_count": 1,
        "planned_feedback_control_mode_counts": {"cooldown": 2, "normal": 1},
        "planned_feedback_target_pool_control_mode_counts": {"freeze": 1},
        "planned_feedback_generator_mode_control_mode_counts": {"suppress": 1},
        "selected_feedback_control_mode_counts": {"cooldown": 1},
        "selected_feedback_target_pool_control_mode_counts": {"freeze": 1},
        "selected_feedback_generator_mode_control_mode_counts": {"normal": 1},
        "feedback_control_mode_counts": {"cooldown": 1, "normal": 2},
        "feedback_target_pool_control_mode_counts": {"freeze": 1, "normal": 2},
        "feedback_generator_mode_control_mode_counts": {"freeze": 1, "normal": 2},
        "suppressed_families": ["family_a"],
        "suppressed_target_pools": ["pool_a"],
        "suppressed_generator_modes": ["external_llm"],
    }

    layered = StrategyFactoryScheduler._build_layered_run_summary(summary, None)
    feedback_summary = layered["feedback_summary"]

    assert (
        feedback_summary["lifecycle_feedback_input_contract_version"]
        == "strategy_factory.lifecycle_feedback_input.v1"
    )
    assert feedback_summary["lifecycle_feedback_input_observed"] is True
    assert feedback_summary["feedback_available"] is True
    assert feedback_summary["family_count"] == 3
    assert feedback_summary["strategy_count"] == 9
    assert feedback_summary["target_pool_scope_count"] == 4
    assert feedback_summary["generator_mode_scope_count"] == 2
    assert feedback_summary["runtime_alert_count"] == 5
    assert feedback_summary["runtime_risk_event_count"] == 6
    assert feedback_summary["blocked_task_count"] == 2
    assert feedback_summary["planned_cooldown_task_count"] == 1
    assert feedback_summary["planned_control_mode_counts"] == {"cooldown": 2, "normal": 1}
    assert feedback_summary["planned_target_pool_control_mode_counts"] == {"freeze": 1}
    assert feedback_summary["planned_generator_mode_control_mode_counts"] == {"suppress": 1}
    assert feedback_summary["selected_control_mode_counts"] == {"cooldown": 1}
    assert feedback_summary["selected_target_pool_control_mode_counts"] == {"freeze": 1}
    assert feedback_summary["selected_generator_mode_control_mode_counts"] == {"normal": 1}
    assert feedback_summary["submission_control_mode_counts"] == {"cooldown": 1, "normal": 2}
    assert feedback_summary["submission_target_pool_control_mode_counts"] == {"freeze": 1, "normal": 2}
    assert feedback_summary["submission_generator_mode_control_mode_counts"] == {"freeze": 1, "normal": 2}
    assert feedback_summary["suppressed_families"] == ["family_a"]
    assert feedback_summary["suppressed_target_pools"] == ["pool_a"]
    assert feedback_summary["suppressed_generator_modes"] == ["external_llm"]


@pytest.mark.asyncio
async def test_cycle_runner_can_be_executed_without_scheduler_loop(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    context = FactoryRunContext(
        db=object(),
        factory_pkg=object(),
        runtime_adapters=None,
        start=scheduler._now(),
        trace_id="strategy_factory:test_runner",
        run_id="factory_run_test_runner",
    )

    monkeypatch.setattr("strategy_factory.application.cycle_runner.is_factory_runtime_enabled", lambda: False)
    monkeypatch.setattr("strategy_factory.application.cycle_runner.resolve_event_runtime_mode", lambda: "disabled")
    monkeypatch.setattr(
        "strategy_factory.application.cycle_runner.is_factory_readiness_hard_block_enabled",
        lambda: True,
    )

    outcome = await FactoryCycleRunner(scheduler, context).run()

    assert isinstance(outcome, FactoryCycleOutcome)
    assert outcome.result["run_id"] == "factory_run_test_runner"
    assert outcome.result["status"] == "skipped"
    assert outcome.result["summary"]["skip_reason"] == "runtime_disabled"
    assert outcome.result["stages"]["readiness"]["status"] == "skipped"
    assert outcome.result["stages"]["readiness"]["decision"] == "blocked"
    assert outcome.result["stages"]["readiness"]["blocking_reason_codes"] == ["runtime_disabled"]
    assert outcome.result["summary"]["factory_readiness_decision"] == "blocked"
    assert outcome.result["summary"]["factory_readiness_blocking_reason_codes"] == ["runtime_disabled"]


@pytest.mark.asyncio
async def test_scheduler_summary_surfaces_factor_llm_provider_health(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()

    class _ProviderHealthGateway:
        async def build_artifact(self, db, snapshot):
            return {
                "degraded": False,
                "summary": {
                    "active_factor_count": 1,
                    "active_candidate_count": 1,
                    "governed_source_candidate_count": 1,
                    "top_factor_names": ["value"],
                    "top_candidate_names": ["value_pool_factor"],
                    "active_family_names": ["value"],
                    "active_regime_names": ["neutral"],
                    "preferred_strategy_types": ["value_factor"],
                    "factor_source_mode": "governed_candidate_pool",
                    "governed_candidate_pool_mode": "strict_governed",
                    "governed_candidate_pool_provisional": False,
                    "governed_candidate_pool_strict_count": 1,
                    "governed_candidate_pool_provisional_count": 0,
                    "degraded": False,
                    "stale": False,
                    "freshness_days": 0,
                    "scheduler_recent_success": True,
                    "scheduler_llm_validation_status": "success",
                    "factor_llm_provider_enabled": True,
                    "factor_llm_provider_ready": False,
                    "factor_llm_provider_health_status": "degraded",
                    "factor_llm_provider_rebuild_count": 2,
                    "factor_llm_provider_last_error_type": "ReadTimeout",
                },
            }

        def status(self):
            return {"running": False}

    scheduler = StrategyFactoryScheduler(factor_research_gateway=_ProviderHealthGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert result["summary"]["factor_llm_provider_enabled"] is True
    assert result["summary"]["factor_llm_provider_ready"] is False
    assert result["summary"]["factor_llm_provider_health_status"] == "degraded"
    assert result["summary"]["factor_llm_provider_rebuild_count"] == 2
    assert result["summary"]["factor_llm_provider_last_error_type"] == "ReadTimeout"
    assert result["summary"]["research_summary"]["factor_llm_provider_health_status"] == "degraded"
    assert result["summary"]["research_summary"]["factor_llm_provider_ready"] is False


@pytest.mark.asyncio
async def test_scheduler_run_once_attaches_governance_slo_and_architecture_review(monkeypatch):
    db = object()
    scheduler = StrategyFactoryScheduler(db_provider=lambda: db)
    scheduler._persist_run_result = AsyncMock()
    scheduler._now = lambda: datetime(2026, 4, 6, 9, 30, 0, tzinfo=scheduler._market_timezone)
    expected_review_week = f"{scheduler._now().isocalendar().year}-W{scheduler._now().isocalendar().week:02d}"
    scheduler.last_result = {
        "summary": {
            "gate_0_passed": 5,
            "candidates_spawned": 6,
            "pre_gate_passed": 4,
            "gate_1_passed": 4,
            "gate_2_input": 4,
            "gate_2_passed": 3,
            "gate_3_input": 3,
            "gate_3_passed": 2,
            "refresh_metrics_only_count": 0,
            "candidates_after_dedup": 3,
            "incubation_summary": {"refresh_ratio": {"ratio": 0.05}},
            "architecture_review": {"review_week": "2026-W14"},
        }
    }

    good_contract = build_portfolio_candidate_contract(
        {
            "strategy_type": "momentum",
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "portfolio_spec": {"position_assumption": "single_name_full_notional", "target_weight_scheme": "single_name"},
            "execution_assumptions": {"slippage_bps": 5, "commission_rate": 0.00025, "tradability_filter": True},
            "validation_profile": {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
            "research_task": {"task_source": "snapshot", "target_symbols": ["600519"]},
        }
    )
    good_hash = build_candidate_contract_hash(contract=good_contract)
    mismatched_contract = build_portfolio_candidate_contract(
        {
            "strategy_type": "mean_reversion",
            "target_symbols": ["000858"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["000858"]},
            "portfolio_spec": {"position_assumption": "single_name_full_notional", "target_weight_scheme": "single_name"},
            "execution_assumptions": {"slippage_bps": 5, "commission_rate": 0.00025, "tradability_filter": True},
            "validation_profile": {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
            "research_task": {"task_source": "snapshot", "target_symbols": ["000858"]},
        }
    )

    class _DummyRunner:
        def __init__(self, owner, context):
            del owner, context

        async def run(self):
            return FactoryCycleOutcome(
                {
                    "run_id": "factory_run_governance",
                    "trace_id": "strategy_factory:governance",
                    "started_at": "2026-04-06T09:30:00+08:00",
                    "completed_at": "2026-04-06T09:31:00+08:00",
                    "status": "partial",
                    "summary": {
                        "warmup_status": "failed",
                        "warmup_failed": 1,
                        "factor_source_mode": "seed_fallback",
                        "governed_candidate_pool_active": False,
                        "governed_blocked_ratio": 0.76,
                        "factor_research_stale": True,
                        "factor_research_freshness_days": 7,
                        "factor_llm_provider_enabled": True,
                        "factor_llm_provider_ready": False,
                        "factor_llm_provider_health_status": "degraded",
                        "external_llm_status": "failed",
                        "candidates_spawned": 6,
                        "gate_0_passed": 1,
                        "pre_gate_passed": 1,
                        "gate_1_passed": 1,
                        "gate_2_input": 4,
                        "gate_2_passed": 1,
                        "gate_3_input": 2,
                        "gate_3_passed": 0,
                        "planned_bulk_task_count": 5,
                        "selected_bulk_task_count": 1,
                        "bulk_stock_matrix_batch_count": 4,
                        "bulk_stock_matrix_selected_batch_count": 1,
                        "factor_research_refresh_attempted": True,
                        "factor_research_refresh_status": "failed",
                        "refresh_metrics_only_count": 1,
                        "candidates_after_dedup": 2,
                        "incubation_summary": {"refresh_ratio": {"ratio": 0.5}},
                    },
                    "stages": {
                        "autonomy": {
                            "external_llm_status_counts": {
                                "fallback_only": 2,
                                "failed": 1,
                            }
                        },
                        "backtest": {
                            "passed": [
                                {
                                    "backtest_result": {
                                        "candidate_contract_hash": good_hash,
                                        "tested_object_hash": "mismatch_tested_hash",
                                    }
                                }
                            ],
                            "failed": [],
                        },
                        "submit": {
                            "strategies": [
                                {
                                    "strategy_id": "sid_mismatch",
                                    "candidate_contract_hash": "wrong_contract_hash",
                                    "candidate_contract_snapshot": mismatched_contract,
                                    "passed": True,
                                    "live_candidate_ready": False,
                                    "live_review_ready": False,
                                    "direct_trade_candidate": False,
                                    "pool_admission_applied": True,
                                    "submission_action_type": "runtime_review",
                                    "submission_lane": "live_ready_review",
                                    "admission_stage": "incubation",
                                    "admission_block_reasons": ["formal_runtime_required"],
                                },
                                {
                                    "strategy_id": "sid_ok",
                                    "candidate_contract_hash": good_hash,
                                    "candidate_contract_snapshot": good_contract,
                                    "passed": True,
                                    "live_candidate_ready": True,
                                    "live_review_ready": True,
                                    "direct_trade_candidate": True,
                                    "pool_admission_applied": False,
                                    "submission_action_type": "runtime_review",
                                    "submission_lane": "live_ready_review",
                                    "admission_stage": "live",
                                    "admission_block_reasons": [],
                                },
                            ]
                        },
                    },
                },
                [],
            )

    monkeypatch.setattr("strategy_factory.application.factory_scheduler.FactoryCycleRunner", _DummyRunner)

    result = await scheduler.run_once()
    status = scheduler.status()
    scheduler_slo = result["summary"]["scheduler_slo"]
    architecture_review = result["summary"]["architecture_review"]

    assert scheduler_slo["status"] == "critical"
    assert "scheduler_warmup_failed" in scheduler_slo["alert_codes"]
    assert "factor_provider_degraded" in scheduler_slo["alert_codes"]
    assert "governed_pool_blocked" in scheduler_slo["alert_codes"]
    assert "bulk_queue_imbalance" in scheduler_slo["alert_codes"]
    assert architecture_review["review_week"] == expected_review_week
    assert architecture_review["previous_review_week"] == "2026-W14"
    assert architecture_review["cadence_due"] is True
    assert architecture_review["status"] == "attention_required"
    assert architecture_review["categories"]["contract_consistency"]["mismatch_count"] == 1
    assert architecture_review["categories"]["validation_object_consistency"]["mismatch_count"] == 0
    assert architecture_review["categories"]["admission_consistency"]["mismatch_count"] == 1
    assert status["scheduler_slo"]["status"] == "critical"
    assert status["architecture_review"]["review_week"] == expected_review_week


@pytest.mark.asyncio
async def test_scheduler_run_once_delegates_to_cycle_runner(monkeypatch):
    db = object()
    scheduler = StrategyFactoryScheduler(db_provider=lambda: db)
    scheduler._persist_run_result = AsyncMock()
    captured: dict[str, object] = {}

    class _DummyRunner:
        def __init__(self, owner, context):
            captured["owner"] = owner
            captured["context"] = context

        async def run(self):
            return FactoryCycleOutcome(
                {
                    "run_id": "factory_run_delegate",
                    "trace_id": "strategy_factory:delegate",
                    "started_at": scheduler._now().isoformat(),
                    "completed_at": scheduler._now().isoformat(),
                    "status": "success",
                    "summary": {},
                    "stages": {},
                },
                [],
            )

    monkeypatch.setattr("strategy_factory.application.factory_scheduler.FactoryCycleRunner", _DummyRunner)

    result = await scheduler.run_once()

    assert captured["owner"] is scheduler
    assert isinstance(captured["context"], FactoryRunContext)
    assert captured["context"].db is db
    assert captured["context"].runtime_adapters is None
    assert result["run_id"] == "factory_run_delegate"
    assert scheduler.last_result is result
    scheduler._persist_run_result.assert_awaited_once()
