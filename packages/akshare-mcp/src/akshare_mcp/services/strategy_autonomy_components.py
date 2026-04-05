"""Supporting services for strategy autonomy orchestration."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from typing import Any, Optional
from uuid import uuid4

def _extract_event_context(*args, **kwargs):
    from strategy_factory import extract_event_context
    return extract_event_context(*args, **kwargs)

from .artifact_registry import register_experiment
from .strategy_generators import LLMProxyStrategyGenerator, RuleStrategyGenerator
from .strategy_optimizer import BanditParameterOptimizer
from .strategy_reviewer import MultiAgentStrategyReviewer
from .strategy_spec import StrategySpec

logger = logging.getLogger(__name__)


def _env_bool(*names: str, default: bool) -> bool:
    for name in names:
        raw = os.getenv(str(name or "").strip())
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
    return bool(default)


class CandidateGenerationService:
    def __init__(
        self,
        *,
        rule_generator: Optional[RuleStrategyGenerator] = None,
        llm_generator: Optional[LLMProxyStrategyGenerator] = None,
        optimizer: Optional[BanditParameterOptimizer] = None,
    ):
        self.rule_generator = rule_generator or RuleStrategyGenerator()
        self.llm_generator = llm_generator or LLMProxyStrategyGenerator()
        self.optimizer = optimizer or BanditParameterOptimizer()

    @staticmethod
    def _task_source(research_task: Optional[dict[str, Any]]) -> str:
        return str((research_task or {}).get("task_source") or "").strip().lower()

    @classmethod
    def _bulk_llm_enabled(cls) -> bool:
        return _env_bool(
            "STRATEGY_FACTORY_BULK_LLM_ENABLED",
            "STRATEGY_FACTORY_BULK_STOCK_MATRIX_LLM_ENABLED",
            default=False,
        )

    @classmethod
    def _bulk_optimizer_enabled(cls) -> bool:
        return _env_bool(
            "STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED",
            "STRATEGY_FACTORY_BULK_STOCK_MATRIX_OPTIMIZER_ENABLED",
            default=False,
        )

    @classmethod
    def _skipped_llm_report(
        cls,
        *,
        task_source: str,
        requested_limit: int,
        reason: str,
        optimizer_enabled: bool,
    ) -> dict[str, Any]:
        mode = "rule_only" if not optimizer_enabled else "rule_plus_optimizer"
        return {
            "mode": mode,
            "external_provider": {
                "status": "skipped",
                "skip_reason": reason,
                "task_source": task_source,
                "requested_limit": int(requested_limit or 0),
                "selected_count": 0,
                "elapsed_seconds": 0.0,
                "requests": [],
            },
            "optimizer": {
                "status": "enabled" if optimizer_enabled else "skipped",
                "skip_reason": None if optimizer_enabled else reason,
            },
        }

    @staticmethod
    def _bulk_primary_family(research_task: Optional[dict[str, Any]]) -> Optional[str]:
        task = dict(research_task or {})
        preferred = [
            str(item or "").strip()
            for item in list(task.get("strategy_preferences") or task.get("preferred_strategy_types") or [])
            if str(item or "").strip()
        ]
        if preferred:
            return preferred[0]
        family = str(task.get("candidate_family") or "").strip()
        return family or None

    @classmethod
    def _bulk_rule_variant_params(
        cls,
        strategy_type: str,
        *,
        base_params: dict[str, Any],
        variant_index: int,
    ) -> dict[str, Any]:
        variants: dict[str, list[dict[str, Any]]] = {
            "momentum": [
                {"lookback": 8, "threshold": 0.008},
                {"lookback": 15, "threshold": 0.015},
                {"lookback": 22, "threshold": 0.022},
            ],
            "ma_cross": [
                {"short_period": 5, "long_period": 20},
                {"short_period": 8, "long_period": 30},
                {"short_period": 10, "long_period": 40},
            ],
            "rsi": [
                {"rsi_period": 6, "oversold": 24, "overbought": 68},
                {"rsi_period": 10, "oversold": 28, "overbought": 72},
                {"rsi_period": 14, "oversold": 32, "overbought": 76},
            ],
            "value_factor": [
                {"lookback": 40, "buy_quantile": 0.75, "sell_quantile": 0.25},
                {"lookback": 60, "buy_quantile": 0.80, "sell_quantile": 0.20},
                {"lookback": 90, "buy_quantile": 0.85, "sell_quantile": 0.15},
            ],
            "quality_factor": [
                {"lookback": 30, "buy_quantile": 0.70, "sell_quantile": 0.30},
                {"lookback": 50, "buy_quantile": 0.75, "sell_quantile": 0.25},
                {"lookback": 70, "buy_quantile": 0.82, "sell_quantile": 0.18},
            ],
            "growth_factor": [
                {"lookback": 24, "buy_quantile": 0.72, "sell_quantile": 0.28},
                {"lookback": 40, "buy_quantile": 0.78, "sell_quantile": 0.22},
                {"lookback": 60, "buy_quantile": 0.84, "sell_quantile": 0.16},
            ],
            "multi_factor": [
                {"lookback": 24, "factor_weights": {"value": 0.45, "quality": 0.35, "momentum": 0.20}},
                {"lookback": 36, "factor_weights": {"value": 0.35, "quality": 0.35, "momentum": 0.30}},
                {"lookback": 48, "factor_weights": {"value": 0.25, "quality": 0.35, "momentum": 0.40}},
            ],
            "macro_timing": [
                {"risk_on_threshold": 0.50, "rebalance_days": 5},
                {"risk_on_threshold": 0.55, "rebalance_days": 10},
                {"risk_on_threshold": 0.60, "rebalance_days": 15},
            ],
            "volatility_breakout": [
                {"lookback": 10, "threshold": 0.012},
                {"lookback": 16, "threshold": 0.018},
                {"lookback": 24, "threshold": 0.024},
            ],
            "gap_fill": [
                {"gap_threshold": 0.015, "rsi_period": 4, "oversold": 22, "overbought": 56},
                {"gap_threshold": 0.020, "rsi_period": 6, "oversold": 24, "overbought": 60},
                {"gap_threshold": 0.030, "rsi_period": 8, "oversold": 28, "overbought": 64},
            ],
            "mean_reversion_short": [
                {"rsi_period": 4, "oversold": 22, "overbought": 58},
                {"rsi_period": 6, "oversold": 26, "overbought": 62},
                {"rsi_period": 8, "oversold": 30, "overbought": 66},
            ],
            "sector_rotation": [
                {"lookback": 15, "factor_weights": {"momentum": 0.50, "quality": 0.30, "value": 0.20}},
                {"lookback": 20, "factor_weights": {"momentum": 0.45, "quality": 0.30, "value": 0.25}},
                {"lookback": 30, "factor_weights": {"momentum": 0.35, "quality": 0.35, "value": 0.30}},
            ],
            "north_capital_track": [
                {"lookback": 10, "threshold": 0.010},
                {"lookback": 15, "threshold": 0.015},
                {"lookback": 20, "threshold": 0.020},
            ],
            "margin_divergence": [
                {"fear_threshold": 35, "greed_threshold": 55, "lookback": 10},
                {"fear_threshold": 40, "greed_threshold": 60, "lookback": 15},
                {"fear_threshold": 45, "greed_threshold": 65, "lookback": 20},
            ],
        }
        options = list(variants.get(strategy_type) or [])
        if not options:
            return dict(base_params or {})
        selected = dict(options[variant_index % len(options)])
        return {**dict(base_params or {}), **selected}

    @classmethod
    def _expand_bulk_rule_specs(
        cls,
        rule_specs: list[StrategySpec],
        *,
        research_task: Optional[dict[str, Any]],
        limit: int,
    ) -> list[StrategySpec]:
        requested_limit = max(1, int(limit or 1))
        if not rule_specs:
            return []
        primary_family = cls._bulk_primary_family(research_task)
        base_spec = None
        if primary_family:
            for item in rule_specs:
                if str(item.strategy_type or "").strip().lower() == primary_family:
                    base_spec = item
                    break
        if base_spec is None:
            base_spec = rule_specs[0]

        expanded: list[StrategySpec] = []
        seen: set[str] = set()
        for variant_index in range(requested_limit):
            params = cls._bulk_rule_variant_params(
                str(base_spec.strategy_type or "").strip().lower(),
                base_params=dict(base_spec.params or {}),
                variant_index=variant_index,
            )
            key = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
            if key in seen:
                continue
            seen.add(key)
            metadata = {
                **dict(base_spec.metadata or {}),
                "bulk_rule_variant": {
                    "variant_index": variant_index + 1,
                    "variant_count": requested_limit,
                    "task_source": cls._task_source(research_task),
                },
            }
            expanded.append(
                StrategySpec(
                    strategy_type=base_spec.strategy_type,
                    params=params,
                    name=f"{base_spec.name} V{variant_index + 1}",
                    description=base_spec.description,
                    tags=list(base_spec.tags or []),
                    metadata=metadata,
                )
            )
        return expanded or [base_spec]

    async def select_parents(self, db, parent_strategy_id: Optional[str] = None) -> list[dict]:
        if parent_strategy_id:
            try:
                strategy = await db.get_strategy(parent_strategy_id)
            except Exception as exc:
                logger.warning(
                    "CandidateGenerationService: failed to load parent strategy %s, continuing without parents: %s",
                    parent_strategy_id,
                    exc,
                )
                return []
            return [strategy] if strategy else []
        parents = []
        for status in ("incubating", "listed"):
            try:
                parents.extend(await db.list_strategies(status, limit=5))
            except Exception as exc:
                logger.warning(
                    "CandidateGenerationService: failed to load %s parents, continuing with partial context: %s",
                    status,
                    exc,
                )
        return parents[:3]

    async def build_shared_generation_context(
        self,
        db,
        *,
        snapshot: dict,
        parent_strategy_id: Optional[str] = None,
    ) -> dict[str, Any]:
        parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        history_summary = await self.llm_generator._recent_experiments(db, parent_strategies=parents)
        research_context = await self.llm_generator.build_shared_research_context(
            db,
            snapshot=snapshot,
            parent_strategies=parents,
            history_summary=history_summary,
        )
        return {
            "parent_strategies": parents,
            "history_summary": history_summary,
            "research_context": research_context,
        }

    async def generate(
        self,
        db,
        *,
        snapshot: dict,
        limit: int,
        research_task: dict[str, Any],
        parent_strategy_id: Optional[str] = None,
    ) -> dict:
        shared_generation_context = dict(snapshot.get("_shared_generation_context") or {})
        task_source = self._task_source(research_task)
        bulk_stock_matrix_task = task_source == "bulk_stock_matrix"
        bulk_llm_enabled = self._bulk_llm_enabled() if bulk_stock_matrix_task else True
        bulk_optimizer_enabled = self._bulk_optimizer_enabled() if bulk_stock_matrix_task else True
        needs_parent_context = bool(parent_strategy_id or bulk_llm_enabled or bulk_optimizer_enabled or not bulk_stock_matrix_task)
        parents = (
            [dict(item or {}) for item in list(shared_generation_context.get("parent_strategies") or [])]
            if needs_parent_context
            else []
        )
        if parent_strategy_id:
            parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        elif needs_parent_context and not parents:
            parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        task_preferences = list(research_task.get("strategy_preferences") or [])
        effective_limit = max(1, min(int(limit or 3), 10))
        if bulk_stock_matrix_task:
            primary_family = self._bulk_primary_family(research_task)
            base_rule_specs = self.rule_generator.generate(
                snapshot,
                limit=1,
                preferred_types=[primary_family] if primary_family else (task_preferences or None),
            )
            if not base_rule_specs:
                base_rule_specs = self.rule_generator.generate(
                    snapshot,
                    limit=1,
                    preferred_types=task_preferences or None,
                )
            bulk_rule_limit = (
                effective_limit
                if not bulk_llm_enabled and not bulk_optimizer_enabled
                else 1
            )
            rule_specs = self._expand_bulk_rule_specs(
                list(base_rule_specs or []),
                research_task=research_task,
                limit=bulk_rule_limit,
            )
        else:
            rule_limit = max(0, limit // 3) if research_task else max(1, limit // 2 or 1)
            rule_specs = (
                self.rule_generator.generate(
                    snapshot,
                    limit=rule_limit,
                    preferred_types=task_preferences or None,
                )
                if rule_limit > 0
                else []
            )
        llm_specs: list[StrategySpec] = []
        if bulk_stock_matrix_task and not bulk_llm_enabled:
            llm_report = self._skipped_llm_report(
                task_source=task_source,
                requested_limit=effective_limit,
                reason="bulk_stock_matrix_llm_disabled",
                optimizer_enabled=bulk_optimizer_enabled,
            )
        else:
            llm_specs = await self.llm_generator.generate(
                db,
                limit=max(1, limit),
                snapshot=snapshot,
                parent_strategies=parents,
                research_task=research_task,
            )
            llm_report = self.llm_generator.get_last_report() if hasattr(self.llm_generator, "get_last_report") else {}
            if bulk_stock_matrix_task and not bulk_optimizer_enabled:
                llm_report = {
                    **dict(llm_report or {}),
                    "optimizer": {
                        "status": "skipped",
                        "skip_reason": "bulk_stock_matrix_optimizer_disabled",
                    },
                }
        evolved_specs: list[StrategySpec] = []
        if bulk_stock_matrix_task and not bulk_optimizer_enabled:
            logger.info(
                "CandidateGenerationService: bulk_stock_matrix task %s using rule-first generation without optimizer",
                research_task.get("task_id") or research_task.get("task_key") or "unknown",
            )
        else:
            for parent in parents[:2]:
                evolved_specs.extend(await self.optimizer.evolve(db, parent, limit=2))

        merged_specs: list[StrategySpec] = []
        seen = set()
        for spec in [*rule_specs, *llm_specs, *evolved_specs]:
            if research_task and not dict(spec.metadata or {}).get("research_task"):
                spec.metadata = {**dict(spec.metadata or {}), "research_task": research_task}
            key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
            if key in seen:
                continue
            seen.add(key)
            merged_specs.append(spec)
            if len(merged_specs) >= effective_limit:
                break

        return {
            "parents": parents,
            "rule_specs": rule_specs,
            "llm_specs": llm_specs,
            "evolved_specs": evolved_specs,
            "merged_specs": merged_specs,
            "llm_report": llm_report,
        }


class CommitteeReviewService:
    def __init__(self, *, reviewer: Optional[MultiAgentStrategyReviewer] = None):
        self.reviewer = reviewer or MultiAgentStrategyReviewer()

    @staticmethod
    def attach_lineage(
        spec: StrategySpec,
        *,
        parent_strategy_id: Optional[str],
        task_run_id: Optional[int],
        review_rank: Optional[int] = None,
        is_champion: bool = False,
    ) -> StrategySpec:
        metadata = dict(spec.metadata or {})
        if parent_strategy_id and not metadata.get("parent_strategy_id"):
            metadata["parent_strategy_id"] = parent_strategy_id
        if task_run_id is not None:
            metadata["task_run_id"] = task_run_id
        committee_review = dict(metadata.get("committee_review") or {})
        if review_rank is not None:
            committee_review["rank"] = int(review_rank)
        if is_champion:
            committee_review["is_champion"] = True
        elif review_rank is not None:
            committee_review.setdefault("is_champion", False)
        if committee_review:
            metadata["committee_review"] = committee_review
        spec.metadata = metadata
        return spec

    @staticmethod
    def review_score(spec: StrategySpec) -> float:
        review = dict((spec.metadata or {}).get("committee_review") or {})
        value = review.get("final_score")
        try:
            return float(value)
        except Exception:
            return 0.0

    def review_candidates(
        self,
        specs: list[StrategySpec],
        *,
        snapshot: dict,
        parent_strategy_id: Optional[str],
        task_run_id: Optional[int],
    ) -> dict:
        reviewed_specs: list[StrategySpec] = []
        committee_reviews: list[dict[str, Any]] = []
        rejected_count = 0
        for spec in list(specs or []):
            reviewed_spec, review = self.reviewer.review(spec, snapshot)
            committee_reviews.append({
                "strategy_type": spec.strategy_type,
                "name": spec.name,
                **review,
            })
            if reviewed_spec is None:
                rejected_count += 1
                continue
            reviewed_specs.append(
                self.attach_lineage(
                    reviewed_spec,
                    parent_strategy_id=parent_strategy_id,
                    task_run_id=task_run_id,
                )
            )

        reviewed_specs.sort(key=self.review_score, reverse=True)
        for rank, spec in enumerate(reviewed_specs, 1):
            self.attach_lineage(
                spec,
                parent_strategy_id=parent_strategy_id,
                task_run_id=task_run_id,
                review_rank=rank,
                is_champion=rank == 1,
            )
        return {
            "reviewed_specs": reviewed_specs,
            "committee_reviews": committee_reviews,
            "rejected_count": rejected_count,
        }


class ExperimentRecorder:
    async def record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        experiment_id = f"exp_{int(time.time())}_{uuid4().hex[:8]}"
        hypothesis = spec.description or f"{source}:{spec.strategy_type}"
        artifact = register_experiment({
            "experiment_id": experiment_id,
            "hypothesis": hypothesis,
            "method": spec.metadata.get("generator_type") or source,
            "parameters": spec.params,
            "status": "running",
            "tags": spec.tags,
            "conclusion": "",
        })
        parent_strategy_id = spec.metadata.get("parent_strategy_id")
        prompt_payload = spec.metadata.get("llm_prompt")
        research_task = dict(spec.metadata.get("research_task") or {})
        event_context = dict(spec.metadata.get("event_context") or {}) or _extract_event_context(research_task)
        payload = {
            "experiment_id": experiment_id,
            "strategy_id": parent_strategy_id,
            "parent_strategy_id": parent_strategy_id,
            "generated_strategy_id": spec.metadata.get("generated_strategy_id"),
            "task_run_id": task_run.get("id"),
            "source": source,
            "generator_type": spec.metadata.get("generator_type") or source,
            "optimizer_type": spec.metadata.get("optimizer_type"),
            "status": "generated",
            "hypothesis": hypothesis,
            "prompt": (str(prompt_payload) if prompt_payload is not None else str(snapshot.get("date") or date.today())),
            "parameters": spec.params,
            "strategy_spec": {
                "strategy_type": spec.strategy_type,
                "name": spec.name,
                "description": spec.description,
                "tags": spec.tags,
                "params": spec.params,
                "target_symbols": spec.metadata.get("target_symbols") or [],
                "stock_pool": spec.metadata.get("stock_pool") or {},
                "selection_logic": spec.metadata.get("selection_logic") or [],
                "research_task": research_task,
                "event_context": event_context,
            },
            "evaluation": {
                "source": source,
                "task_run_id": task_run.get("id"),
                "generation_reason": spec.metadata.get("generation_reason") or {},
                "committee_review": spec.metadata.get("committee_review") or {},
                "llm_analysis": spec.metadata.get("llm_analysis") or {},
                "llm_research_context": spec.metadata.get("llm_research_context") or {},
                "llm_response": spec.metadata.get("llm_response") or {},
                "target_symbols": spec.metadata.get("target_symbols") or [],
                "stock_pool": spec.metadata.get("stock_pool") or {},
                "selection_logic": spec.metadata.get("selection_logic") or [],
                "research_scope": spec.metadata.get("research_scope") or {},
                "research_task": research_task,
                "event_context": event_context,
            },
            "result": {},
            "parent_experiment_id": None,
            "artifact_id": artifact.get("artifact_id"),
        }
        try:
            return await db.save_strategy_generation_experiment(payload)
        except Exception as exc:
            logger.warning(
                "ExperimentRecorder: save experiment failed, continuing without persistence: %s",
                exc,
            )
            return {
                **payload,
                "persistence_error": str(exc),
            }

    async def record_candidates(self, db, specs: list[StrategySpec], *, source: str, snapshot: dict, task_run: dict) -> dict:
        experiments = []
        candidates = []
        champion = None
        for spec in list(specs or []):
            experiment = await self.record_experiment(db, spec, source, snapshot, task_run)
            experiments.append(experiment)
            candidate = spec.to_candidate(source, experiment["experiment_id"])
            candidates.append(candidate)
            if champion is None:
                committee_review = dict((experiment.get("evaluation") or {}).get("committee_review") or {})
                champion = {
                    "experiment_id": experiment.get("experiment_id"),
                    "strategy_type": spec.strategy_type,
                    "name": spec.name,
                    "final_score": committee_review.get("final_score"),
                    "decision": committee_review.get("decision"),
                    "parent_strategy_id": experiment.get("parent_strategy_id") or experiment.get("strategy_id"),
                }
        return {
            "experiments": experiments,
            "candidates": candidates,
            "champion": champion,
        }

    async def apply_submission_results(self, db, experiments: list[dict], submit_result: Optional[dict]) -> dict:
        payload = dict(submit_result or {})
        submission_items = list(payload.get("items") or payload.get("strategies") or [])
        by_experiment = {item.get("experiment_id"): item for item in submission_items}
        updated_experiments = []
        for experiment in list(experiments or []):
            item = by_experiment.get(experiment.get("experiment_id")) or {}
            evaluation = dict(experiment.get("evaluation") or {})
            evaluation["submission_result"] = item
            updated = await db.save_strategy_generation_experiment({
                **experiment,
                "strategy_id": experiment.get("parent_strategy_id") or experiment.get("strategy_id"),
                "generated_strategy_id": item.get("strategy_id") or experiment.get("generated_strategy_id"),
                "status": "accepted" if item.get("passed") else "rejected",
                "evaluation": evaluation,
                "result": item,
            })
            updated_experiments.append(updated)
        return {
            "experiments": updated_experiments,
            "items_by_experiment": by_experiment,
        }
