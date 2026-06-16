from __future__ import annotations

import asyncio
import sqlite3
from datetime import date


def test_factory_persists_decay_measurements_and_pool_updates():
    from akshare_mcp.services.factor_mining_factory.factory import FactorMiningFactory
    from akshare_mcp.services.factor_mining_factory.pool.storage import (
        ensure_factor_pool_tables,
        load_active_pool_from_db,
    )

    class Db:
        def __init__(self):
            self.conn = sqlite3.connect(":memory:")
            self.conn.row_factory = sqlite3.Row

    async def run():
        db = Db()
        await ensure_factor_pool_tables(db)
        factory = FactorMiningFactory()
        measurement = {
            "factor_id": "factor-1",
            "measured_at": "2026-05-19T00:00:00+00:00",
            "rolling_ic_20d": 0.03,
            "rolling_ic_60d": 0.05,
            "admission_ic": 0.08,
            "current_ic": 0.02,
            "decay_rate": 0.75,
            "estimated_half_life_days": 12.0,
        }
        record = {
            "factor_id": "factor-1",
            "name": "momentum",
            "family": "momentum",
            "expression_dsl": "ts_mean(close, 20)",
            "status": "active",
            "fitness": 1.0,
            "current_ic": 0.02,
            "decay_rate": 0.75,
            "last_evaluated_at": "2026-05-19T00:00:00+00:00",
        }
        await factory._persist_decay_report(db, {"measurements": [measurement]})
        await factory._persist_decay_updates(db, {"updated_records": [record]})
        history = db.conn.execute(
            "SELECT * FROM factor_pool_decay_history WHERE factor_id = ?",
            ("factor-1",),
        ).fetchone()
        pool = await load_active_pool_from_db(db)
        return dict(history), pool

    history, pool = asyncio.run(run())

    assert history["decay_rate"] == 0.75
    assert history["alert_triggered"] == 1
    assert pool[0]["factor_id"] == "factor-1"
    assert pool[0]["decay_rate"] == 0.75
    assert pool[0]["current_ic"] == 0.02


def test_forward_verifier_uses_wilson_lcb_and_holding_period_sharpe():
    from akshare_mcp.services.incubation_factory.forward_verifier import ForwardVerifier

    verifier = ForwardVerifier()

    lcb = verifier._compute_skill_lcb([1.0] * 10)
    assert 0.2 < lcb < 0.5

    returns = [0.01, 0.02, -0.005, 0.015, 0.0]
    daily_scaled = verifier._compute_forward_sharpe(returns, horizon_days=1)
    held_scaled = verifier._compute_forward_sharpe(returns, horizon_days=5)
    assert held_scaled < daily_scaled


def test_metrics_recorder_writes_schema_fields_and_nav_rows():
    from akshare_mcp.services.incubation_factory.metrics_recorder import MetricsRecorder

    class Db:
        def __init__(self):
            self.saved = None

        async def get_strategy_incubation_account(self, strategy_id):
            return {"strategy_id": strategy_id, "account_id": "acct-1"}

        async def get_paper_account(self, account_id):
            return {"id": account_id, "initial_capital": 100000.0}

        async def get_paper_nav_rows(self, account_id, limit=60):
            return [
                {"account_id": account_id, "nav_date": "2026-05-19", "total_value": 99000.0, "cash": 5000.0, "market_value": 94000.0, "daily_return": None},
                {"account_id": account_id, "nav_date": "2026-05-18", "total_value": 100000.0, "cash": 6000.0, "market_value": 94000.0, "daily_return": 0.01},
                {"account_id": account_id, "nav_date": "2026-05-17", "total_value": 105000.0, "cash": 7000.0, "market_value": 98000.0, "daily_return": 0.05},
            ]

        async def save_strategy_incubation_metric(self, strategy_id, metric_date, metric):
            self.saved = dict(metric)
            return self.saved

    db = Db()
    metric = asyncio.run(
        MetricsRecorder().record(
            db,
            {"id": "strategy-1", "status": "incubating"},
            {
                "primary_hit_rate": 0.6,
                "recent_primary_hit_rate": 0.55,
                "primary_skill_lcb": 0.03,
                "recent_primary_skill_lcb": 0.02,
                "stability_gap": 0.01,
                "coverage_ratio": 0.8,
                "forward_ic": 0.04,
                "forward_sharpe": 0.7,
                "primary_effective_n": 20,
                "total_signals": 22,
            },
            metric_date=date(2026, 5, 19),
        )
    )

    assert metric["effective_n_5d"] == 20
    assert metric["recent_hit_rate_5d"] == 0.55
    assert metric["stability_gap_5d"] == 0.01
    assert metric["forward_ic_5d"] == 0.04
    assert metric["total_signals"] == 22
    assert metric["daily_return"] == -0.01
    assert metric["max_drawdown"] > 0


def test_feedback_writer_runtime_control_includes_required_fields():
    from akshare_mcp.services.incubation_factory.feedback_writer import FeedbackWriter

    class Db:
        def __init__(self):
            self.controls = []

        async def save_strategy_domain_event(self, payload):
            return payload

        async def save_strategy_closure_snapshot(self, payload):
            return payload

        async def list_strategies(self, status, limit=500):
            return [{"id": "strategy-1", "strategy_type": "momentum"}]

        async def get_strategy_incubation_account(self, strategy_id):
            return {"strategy_id": strategy_id, "account_id": "acct-1"}

        async def save_strategy_runtime_control(self, payload):
            self.controls.append(dict(payload))
            return payload

    db = Db()
    asyncio.run(
        FeedbackWriter().write(
            db,
            {
                "feedback_actions": {"families_to_freeze": ["momentum"]},
                "hit_rate_dashboard": {"by_family": {}},
            },
        )
    )

    control = db.controls[0]
    assert control["account_id"] == "acct-1"
    assert control["status"] == "active"
    assert control["trigger_event_type"] == "incubation_factory.feedback_control"
    assert control["action_summary"]["action"] == "freeze"


def test_evolutionary_optimizer_blends_ic_feedback():
    from akshare_mcp.services.factor_mining_factory.engines.base import FactorCandidate
    from akshare_mcp.services.factor_mining_factory.evolution.optimizer import EvolutionaryOptimizer

    candidate = FactorCandidate(
        name="factor-a",
        hypothesis="structured factor",
        inputs=["close"],
        expression_dsl="ts_mean(close, 20)",
        fitness=1.0,
    )
    optimizer = EvolutionaryOptimizer()

    asyncio.run(
        optimizer._evaluate_fitness(
            [candidate],
            ic_evaluator=lambda _: 0.1,
        )
    )

    assert round(candidate.fitness, 4) == 1.625
    assert candidate.generation_trace["evolution_ic_value"] == 0.1
    assert candidate.generation_trace["evolution_fitness_blend"] == "0.7_structural_0.3_abs_ic_x25"


def test_factor_llm_payload_truncates_overlong_text_fields():
    from akshare_mcp.services.factor_llm_provider_parts.context import (
        validate_factor_generation_payload,
    )

    data = validate_factor_generation_payload(
        {
            "candidates": [
                {
                    "name": "long_text_factor",
                    "hypothesis": "h" * 800,
                    "family": "custom",
                    "inputs": ["close"],
                    "expression_dsl": "ts_mean(close, 20)",
                    "novelty_rationale": "n" * 800,
                }
            ]
        }
    )

    candidate = data["candidates"][0]
    assert len(candidate["hypothesis"]) == 400
    assert len(candidate["novelty_rationale"]) == 400


def test_accelerator_triggers_incubation_pipeline(monkeypatch):
    from akshare_mcp.services.incubation_factory.accelerator import IncubationAccelerator
    from akshare_mcp.services import incubation_pipeline

    class Db:
        async def save_strategy_domain_event(self, payload):
            return payload

    class Pipeline:
        def __init__(self):
            self.calls = []

        async def run_strategy(self, db, strategy, **kwargs):
            self.calls.append((strategy, kwargs))
            return {"ok": True}

    pipeline = Pipeline()
    monkeypatch.setattr(
        incubation_pipeline,
        "get_strategy_incubation_pipeline_service",
        lambda: pipeline,
    )

    asyncio.run(
        IncubationAccelerator()._trigger_acceleration(
            Db(),
            {"id": "strategy-1", "name": "S"},
            {"promote_streak": 10},
        )
    )

    assert pipeline.calls[0][1]["source"] == "incubation_factory_accelerator"
    assert pipeline.calls[0][1]["auto_apply_review"] is True


def test_alpha_blueprints_compile_and_include_economic_metadata():
    from akshare_mcp.services.factor_candidate_compiler import compile_factor_candidate
    from akshare_mcp.services.factor_mining_factory.blueprints import AlphaBlueprintLibrary

    blueprints = AlphaBlueprintLibrary().build_context_blueprints()

    assert blueprints
    for blueprint in blueprints:
        assert blueprint["blueprint_id"]
        assert blueprint["economic_hypothesis"]
        assert blueprint["factor_family"]
        assert blueprint["expected_horizon"] > 0
        assert isinstance(blueprint["risk_exposure_hint"], dict)
        compiled = compile_factor_candidate(
            {
                "name": blueprint["blueprint_id"],
                "hypothesis": blueprint["economic_hypothesis"],
                "family": blueprint["factor_family"],
                "inputs": blueprint["inputs"],
                "expression_dsl": blueprint["expression_dsl"],
            }
        )
        assert compiled["valid"], blueprint["blueprint_id"]
        assert compiled["function_calls"], blueprint["blueprint_id"]


def test_rule_engine_starts_from_alpha_blueprints():
    from akshare_mcp.services.factor_mining_factory.engines.context import MiningContext
    from akshare_mcp.services.factor_mining_factory.engines.rule_engine import RuleSeedEngine
    from akshare_mcp.services.factor_mining_factory.engines.base import SearchBudget

    context = MiningContext(
        alpha_blueprints=[
            {
                "blueprint_id": "test_blueprint",
                "factor_family": "momentum",
                "expression_dsl": "zscore(momentum_20d, 20) - zscore(volatility_20d, 20)",
                "inputs": ["momentum_20d", "volatility_20d"],
                "economic_hypothesis": "Risk-adjusted momentum should persist.",
                "expected_horizon": 10,
                "risk_exposure_hint": {"style": ["momentum"]},
            }
        ]
    )

    candidates = asyncio.run(
        RuleSeedEngine().generate(context, SearchBudget(candidate_count=3))
    )

    assert candidates[0].blueprint_id == "test_blueprint"
    assert candidates[0].economic_hypothesis
    assert candidates[0].risk_exposure_hint["style"] == ["momentum"]


def test_quick_evidence_evaluator_uses_quick_stage_and_thresholds(monkeypatch):
    from akshare_mcp.services import factor_validation_pipeline
    from akshare_mcp.services.factor_mining_factory.engines.base import FactorCandidate
    from akshare_mcp.services.factor_mining_factory.quick_evidence import (
        QuickEvidenceEvaluator,
    )

    captured = {}

    async def fake_validate(db, candidate, **kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "metrics": {
                "rank_ic_mean": 0.03,
                "rank_ic_ir": 0.2,
                "positive_ratio": 0.54,
                "sample_dates": 45,
            },
            "coverage": {"avg_cross_section_n": 100, "eligible_code_count": 120},
            "cross_section": {"summary": {"rank_ic_mean": 0.03, "sample_dates": 45}},
            "lookahead_audit": {"risk_level": "low"},
            "persisted_outputs": {"enabled": False, "ic_history_rows": 0},
        }

    monkeypatch.setattr(
        factor_validation_pipeline,
        "validate_factor_candidate_pipeline",
        fake_validate,
    )

    evaluator = QuickEvidenceEvaluator(object(), codes=[f"000{i:03d}" for i in range(130)])
    candidate = FactorCandidate(
        name="quick_factor",
        hypothesis="quick evidence candidate",
        inputs=["close"],
        expression_dsl="ts_mean(close, 20)",
    )
    evidence = asyncio.run(evaluator.evaluate(candidate))

    assert evidence["passed"] is True
    assert candidate.quick_evidence["stage"] == "quick"
    assert captured["stage"] == "quick"
    assert captured["min_cross_section"] == 80
    assert captured["persist_ic_history"] is False


def test_active_pool_redundancy_uses_replacement_decision_metadata():
    from akshare_mcp.services.factor_mining_factory.engines.base import FactorCandidate
    from akshare_mcp.services.factor_mining_factory.pool.active_pool import ActiveFactorPool

    validation_result = {
        "metrics": {
            "rank_ic_mean": 0.05,
            "rank_ic_ir": 0.35,
            "positive_ratio": 0.56,
            "sample_dates": 60,
        },
        "coverage": {"avg_cross_section_n": 100},
        "lookahead_audit": {"risk_level": "low"},
        "rating": {"grade": "A"},
        "persisted_outputs": {"enabled": True, "ic_history_rows": 60},
    }

    pool = ActiveFactorPool()
    pool.hydrate(
        [
            {
                "factor_id": "existing-1",
                "name": "existing",
                "family": "momentum",
                "inputs": ["close"],
                "hypothesis": "existing factor",
                "expression_dsl": "ts_mean(close, 20)",
                "status": "active",
                "fitness": 95.0,
                "validation_summary": {
                    "quality_status": "promoted",
                    "quality_score": 95.0,
                },
            }
        ]
    )
    rejected = asyncio.run(
        pool.admit(
            FactorCandidate(
                name="redundant_factor",
                hypothesis="same expression",
                inputs=["close"],
                expression_dsl="ts_mean(close, 20)",
                validation_result=validation_result,
            )
        )
    )

    assert rejected["admitted"] is False
    assert rejected["reason"] == "redundant"
    assert rejected["replacement_decision"]["action"] == "reject"
    assert rejected["incremental_quality_score"] < 10.0


def test_factory_quality_summary_includes_quick_funnel_and_blueprints():
    from akshare_mcp.services.factor_mining_factory.engines.base import FactorCandidate
    from akshare_mcp.services.factor_mining_factory.factory import FactorMiningFactory

    raw = [
        FactorCandidate(
            name="raw",
            expression_dsl="ts_mean(close, 20)",
            generation_engine="rule_seed",
            blueprint_id="bp1",
        )
    ]
    evolved = [
        FactorCandidate(
            name="evolved",
            expression_dsl="ts_mean(close, 20)",
            generation_engine="rule_seed",
            blueprint_id="bp1",
            quick_evidence={"passed": False, "fail_reasons": ["rank_ic_ir_below_min"]},
        )
    ]

    class Context:
        validation_universe_health = {"eligible_count": 300}

    summary = FactorMiningFactory()._build_quality_summary(
        raw,
        evolved,
        [],
        [],
        Context(),
    )

    assert summary["quality_funnel"]["generated"] == 1
    assert summary["quality_funnel"]["quick_evaluated"] == 1
    assert summary["reject_reasons"]["rank_ic_ir_below_min"] == 1
    assert summary["by_blueprint"]["bp1"]["raw"] == 1


def test_llm_engine_uses_blueprint_fallback_prompt(monkeypatch):
    from akshare_mcp import storage
    from akshare_mcp.services import factor_llm_provider, factor_prompt_builder
    from akshare_mcp.services.factor_mining_factory.engines.base import SearchBudget
    from akshare_mcp.services.factor_mining_factory.engines.context import MiningContext
    from akshare_mcp.services.factor_mining_factory.engines.llm_engine import LLMSearchEngine

    async def empty_prompt_builder(*args, **kwargs):
        raise ValueError("codes cannot be empty")

    class Provider:
        def __init__(self):
            self.prompt = None

        def is_enabled(self):
            return True

        async def generate_candidates(self, prompt, *, candidate_count):
            self.prompt = prompt
            assert getattr(prompt, "system_prompt", "")
            assert getattr(prompt, "user_prompt", "")
            assert "alpha_blueprints" in prompt.request_payload
            return {
                "provider": "fake",
                "model": "fake-model",
                "candidates": [
                    {
                        "name": "llm_blueprint_factor",
                        "hypothesis": "Mutated blueprint candidate.",
                        "economic_hypothesis": "Risk-adjusted momentum may persist.",
                        "family": "momentum",
                        "factor_family": "vol_adjusted_momentum",
                        "inputs": ["momentum_20d", "volatility_20d"],
                        "expression_dsl": "zscore(momentum_20d, 20) - zscore(volatility_20d, 20)",
                        "expected_holding_period": 10,
                        "expected_horizon": 10,
                        "risk_exposure_hint": {"style": ["momentum"]},
                        "blueprint_id": "bp_mom",
                    }
                ],
            }

    provider = Provider()
    monkeypatch.setattr(factor_prompt_builder, "build_factor_mining_prompt", empty_prompt_builder)
    monkeypatch.setattr(factor_llm_provider, "get_factor_llm_provider", lambda: provider)
    monkeypatch.setattr(storage, "get_db", lambda: object())

    context = MiningContext(
        validation_codes=["000001"],
        alpha_blueprints=[
            {
                "blueprint_id": "bp_mom",
                "factor_family": "vol_adjusted_momentum",
                "expression_dsl": "zscore(momentum_20d, 20) - zscore(volatility_20d, 20)",
                "inputs": ["momentum_20d", "volatility_20d"],
                "economic_hypothesis": "Risk-adjusted momentum may persist.",
                "expected_horizon": 10,
                "risk_exposure_hint": {"style": ["momentum"]},
            }
        ],
    )

    candidates = asyncio.run(
        LLMSearchEngine()._generation_chain(context, SearchBudget(candidate_count=2))
    )

    assert candidates[0].generation_engine == "llm_primary"
    assert candidates[0].blueprint_id == "bp_mom"
    assert provider.prompt.source_chain == ["factor_mining_factory.llm_blueprint_fallback", "factor_mining_factory.alpha_blueprints"]


def test_quality_summary_persists_strict_candidate_validation_result():
    from akshare_mcp.services.factor_mining_factory.engines.base import FactorCandidate
    from akshare_mcp.services.factor_mining_factory.factory import FactorMiningFactory

    candidate = FactorCandidate(
        name="strict_blocked_factor",
        expression_dsl="ts_mean(close, 20)",
        generation_engine="gp_classic",
        quick_evidence={"passed": True},
        generation_trace={"strict_validation_attempted": True},
        validation_result={
            "success": True,
            "stage": "validated",
            "metrics": {
                "rank_ic_mean": 0.05,
                "rank_ic_ir": 0.35,
                "positive_ratio": 0.56,
                "sample_dates": 60,
            },
            "coverage": {"avg_cross_section_n": 100, "diagnostic_counts": {}},
            "lookahead_audit": {"risk_level": "low"},
            "persisted_outputs": {"enabled": True, "ic_history_rows": 60},
            "rating": {"grade": "C", "recommendation": "watch"},
        },
    )

    class Context:
        validation_universe_health = {"eligible_count": 300}

    summary = FactorMiningFactory()._build_quality_summary(
        [candidate],
        [candidate],
        [],
        [],
        Context(),
    )

    strict_rows = summary["strict_candidate_results"]
    assert strict_rows[0]["name"] == "strict_blocked_factor"
    assert strict_rows[0]["validation_result"]["metrics"]["rank_ic_mean"] == 0.05
    assert strict_rows[0]["admission_decision"]["evidence_passed"] is True
    assert "rating_grade_not_admissible:C" in strict_rows[0]["admission_decision"]["blockers"]


# ALPHA-WIRING-V1 (P-B)：放宽 factor_pool 消费门槛的 toggle。
# 已挖出 status=active + 有 DSL 但 quality_status 缺失(null) 的强 IC 因子，
# 默认仍被 promoted 过滤挡住；toggle ON 时放行（quarantine 仍挡）。
def _seed_pool_for_admission():
    from akshare_mcp.services.factor_mining_factory.pool.active_pool import ActiveFactorPool

    pool = ActiveFactorPool()
    pool.hydrate(
        [
            {
                "factor_id": "f_active_null_qs",
                "name": "rl_factor_1",
                "family": "custom",
                "expression_dsl": "ts_rank(open, 5)",
                "status": "active",
                "fitness": 2.0,
                "current_ic": 0.091,
                "validation_summary": {},  # quality_status 缺失
            },
            {
                "factor_id": "f_active_promoted",
                "name": "gp_factor_1",
                "family": "momentum",
                "expression_dsl": "log1p(abs(volume))",
                "status": "active",
                "fitness": 3.0,
                "current_ic": 0.089,
                "validation_summary": {"quality_status": "promoted"},
            },
            {
                "factor_id": "f_active_quarantine",
                "name": "gp_factor_q",
                "family": "momentum",
                "expression_dsl": "ts_mean(close, 5)",
                "status": "active",
                "fitness": 1.0,
                "current_ic": 0.05,
                "validation_summary": {"quality_status": "quarantine"},
            },
        ]
    )
    return pool


def test_factor_pool_admit_default_only_promoted(monkeypatch):
    monkeypatch.delenv("STRATEGY_FACTORY_FACTOR_POOL_ADMIT_ACTIVE_WITHOUT_PROMOTION", raising=False)
    pool = _seed_pool_for_admission()
    factors = asyncio.run(pool.get_active_factors(limit=10))
    names = {item["name"] for item in factors}
    # 默认零变化：只放行 promoted
    assert names == {"gp_factor_1"}


def test_factor_pool_admit_active_without_promotion_toggle(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_POOL_ADMIT_ACTIVE_WITHOUT_PROMOTION", "1")
    pool = _seed_pool_for_admission()
    factors = asyncio.run(pool.get_active_factors(limit=10))
    names = {item["name"] for item in factors}
    # 放行 promoted + active 且 DSL 非空且非 quarantine 的 null-qs 因子
    assert "gp_factor_1" in names
    assert "rl_factor_1" in names
    # quarantine 显式淘汰态仍被挡
    assert "gp_factor_q" not in names
