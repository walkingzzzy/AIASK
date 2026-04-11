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
from .strategy_spec import StrategySpec, _safe_normalize_research_task

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


def _normalized_research_task_payload(research_task: Optional[dict[str, Any]]) -> dict[str, Any]:
    normalized = _safe_normalize_research_task(research_task)
    return dict(normalized or research_task or {})


def _preferred_strategy_types(
    research_task: Optional[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[str]:
    task = _normalized_research_task_payload(research_task)
    preferred: list[str] = []
    for item in list(task.get("preferred_strategy_types") or task.get("strategy_preferences") or []):
        token = str(item or "").strip()
        if token and token not in preferred:
            preferred.append(token)
        if len(preferred) >= max(1, int(limit or 8)):
            break
    return preferred


def _allowed_strategy_types(
    research_task: Optional[dict[str, Any]],
    *,
    limit: int = 12,
) -> list[str]:
    task = _normalized_research_task_payload(research_task)
    allowed: list[str] = []
    for item in list(task.get("allowed_strategy_types") or []):
        token = str(item or "").strip()
        if token and token not in allowed:
            allowed.append(token)
        if len(allowed) >= max(1, int(limit or 12)):
            break
    return allowed


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

    @staticmethod
    def _has_generation_task_constraints(research_task: Optional[dict[str, Any]]) -> bool:
        task = dict(research_task or {})
        for key in (
            "task_id",
            "task_key",
            "task_source",
            "opportunity_type",
            "event_id",
            "theme_code",
            "target_symbols",
            "stock_pool",
            "strategy_preferences",
            "preferred_strategy_types",
            "allowed_strategy_types",
            "candidate_family",
            "factor_name",
        ):
            if task.get(key) not in (None, "", [], {}):
                return True
        return False

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
    def _l2_hypothesis_enabled(cls) -> bool:
        return _env_bool(
            "STRATEGY_FACTORY_L2_HYPOTHESIS_ENABLED",
            "STRATEGY_FACTORY_L2_ENABLED",
            default=True,
        )

    @classmethod
    def _l2_hypothesis_replay_enabled(cls) -> bool:
        return _env_bool(
            "STRATEGY_FACTORY_L2_HYPOTHESIS_REPLAY_ENABLED",
            "STRATEGY_FACTORY_L2_REPLAY_ENABLED",
            default=True,
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
        task = _normalized_research_task_payload(research_task)
        preferred = _preferred_strategy_types(task)
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
        normalized_research_task = _normalized_research_task_payload(research_task)
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
        task_preferences = _preferred_strategy_types(normalized_research_task)
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
            has_generation_task_constraints = self._has_generation_task_constraints(research_task)
            rule_limit = (
                max(0, limit // 3)
                if has_generation_task_constraints
                else max(1, limit // 2 or 1)
            )
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
        replay_specs: list[StrategySpec] = []
        llm_disabled_by_scheduler = bool(research_task.get("disable_external_llm"))
        llm_skip_reason = str(research_task.get("external_llm_skip_reason") or "provider_health_blocked").strip()
        optimizer_disabled_by_scheduler = bool(research_task.get("disable_optimizer"))
        optimizer_skip_reason = str(research_task.get("optimizer_skip_reason") or "generator_mode_cooldown").strip()
        if llm_disabled_by_scheduler:
            llm_report = self._skipped_llm_report(
                task_source=task_source,
                requested_limit=effective_limit,
                reason=llm_skip_reason or "provider_health_blocked",
                optimizer_enabled=bulk_optimizer_enabled if bulk_stock_matrix_task else True,
            )
        elif bulk_stock_matrix_task and not bulk_llm_enabled:
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
            elif optimizer_disabled_by_scheduler:
                llm_report = {
                    **dict(llm_report or {}),
                    "optimizer": {
                        "status": "skipped",
                        "skip_reason": optimizer_skip_reason or "generator_mode_cooldown",
                    },
                }
        replay_report: dict[str, Any] = {
            "status": "disabled" if not self._l2_hypothesis_replay_enabled() else "not_needed",
            "selected_count": 0,
        }
        replay_trigger_reason: Optional[str] = None
        if self._l2_hypothesis_enabled() and self._l2_hypothesis_replay_enabled() and hasattr(
            self.llm_generator,
            "replay_persisted_specs",
        ):
            provider_status = str(
                dict(dict(llm_report or {}).get("external_provider") or {}).get("status") or ""
            ).strip().lower()
            if llm_disabled_by_scheduler:
                replay_trigger_reason = llm_skip_reason or "provider_health_blocked"
            elif bulk_stock_matrix_task and not bulk_llm_enabled:
                replay_trigger_reason = "bulk_stock_matrix_llm_disabled"
            elif not llm_specs:
                replay_trigger_reason = provider_status or "empty_external_selection"
        if replay_trigger_reason:
            try:
                replay_result = await self.llm_generator.replay_persisted_specs(
                    db,
                    limit=max(1, effective_limit),
                    snapshot=snapshot,
                    parent_strategies=parents,
                    research_task=research_task,
                    trigger_reason=replay_trigger_reason,
                )
                replay_specs = list(dict(replay_result or {}).get("specs") or [])
                replay_report = {
                    "status": "succeeded" if replay_specs else "empty",
                    "trigger_reason": replay_trigger_reason,
                    **dict(dict(replay_result or {}).get("report") or {}),
                }
            except Exception as exc:
                logger.warning(
                    "CandidateGenerationService: replay_persisted_specs failed, continuing without replay: %s",
                    exc,
                )
                replay_report = {
                    "status": "failed",
                    "trigger_reason": replay_trigger_reason,
                    "error": str(exc),
                    "selected_count": 0,
                }
        llm_report = {
            **dict(llm_report or {}),
            "replay_provider": dict(replay_report or {}),
        }
        evolved_specs: list[StrategySpec] = []
        if optimizer_disabled_by_scheduler:
            llm_report = {
                **dict(llm_report or {}),
                "optimizer": {
                    "status": "skipped",
                    "skip_reason": optimizer_skip_reason or "generator_mode_cooldown",
                },
            }
        if optimizer_disabled_by_scheduler:
            logger.info(
                "CandidateGenerationService: scheduler disabled optimizer for task %s (%s)",
                research_task.get("task_id") or research_task.get("task_key") or "unknown",
                optimizer_skip_reason or "generator_mode_cooldown",
            )
        elif bulk_stock_matrix_task and not bulk_optimizer_enabled:
            logger.info(
                "CandidateGenerationService: bulk_stock_matrix task %s using rule-first generation without optimizer",
                research_task.get("task_id") or research_task.get("task_key") or "unknown",
            )
        else:
            for parent in parents[:2]:
                evolved_specs.extend(await self.optimizer.evolve(db, parent, limit=2))

        merged_specs: list[StrategySpec] = []
        seen = set()
        prioritized_specs = (
            [*llm_specs, *replay_specs, *evolved_specs, *rule_specs]
            if (llm_specs or replay_specs or evolved_specs)
            else [*rule_specs, *llm_specs, *replay_specs, *evolved_specs]
        )
        for spec in prioritized_specs:
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
            "replay_specs": replay_specs,
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
    _PREVIEW_LIMIT = 3

    @staticmethod
    def _compact_dict(payload: Optional[dict[str, Any]], *, keys: tuple[str, ...]) -> dict[str, Any]:
        source = dict(payload or {})
        return {
            key: source.get(key)
            for key in keys
            if source.get(key) not in (None, "", [], {})
        }

    @classmethod
    def _summarize_research_task(cls, research_task: Optional[dict[str, Any]]) -> dict[str, Any]:
        task = _normalized_research_task_payload(research_task)
        summary = cls._compact_dict(
            task,
            keys=(
                "task_id",
                "task_key",
                "task_source",
                "opportunity_type",
                "theme_code",
                "event_id",
                "candidate_family",
                "factor_name",
                "generation_limit",
                "source_candidate_artifact_id",
                "evidence_count",
                "preference_strength",
                "validation_focus",
            ),
        )
        target_symbols = list(task.get("target_symbols") or [])
        if target_symbols:
            summary["target_symbols"] = target_symbols[:12]
        preferred_strategy_types = _preferred_strategy_types(task, limit=6)
        if preferred_strategy_types:
            summary["preferred_strategy_types"] = preferred_strategy_types
            summary["strategy_preferences"] = list(preferred_strategy_types)
        allowed_strategy_types = _allowed_strategy_types(task, limit=6)
        if allowed_strategy_types:
            summary["allowed_strategy_types"] = allowed_strategy_types
        return summary

    @classmethod
    def _summarize_event_context(cls, event_context: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(event_context or {})
        summary = cls._compact_dict(
            payload,
            keys=(
                "task_source",
                "event_id",
                "theme_code",
                "event_type",
                "opportunity_type",
                "candidate_family",
                "factor_name",
            ),
        )
        target_symbols = list(payload.get("target_symbols") or payload.get("symbols") or [])
        if target_symbols:
            summary["target_symbols"] = target_symbols[:12]
        return summary

    @classmethod
    def _summarize_stock_pool(cls, stock_pool: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(stock_pool or {})
        summary = cls._compact_dict(
            payload,
            keys=("selection_mode", "universe_scope", "source", "reason"),
        )
        symbols = list(payload.get("symbols") or payload.get("target_symbols") or [])
        if symbols:
            summary["symbol_count"] = len(symbols)
            summary["symbols"] = symbols[:12]
        return summary

    @classmethod
    def _summarize_selection_logic(cls, selection_logic: Optional[list[Any]]) -> dict[str, Any]:
        items = list(selection_logic or [])
        preview: list[Any] = []
        for item in items[: cls._PREVIEW_LIMIT]:
            if isinstance(item, dict):
                preview.append({key: item.get(key) for key in list(item.keys())[:6]})
            else:
                preview.append(str(item))
        return {
            "count": len(items),
            "preview": preview,
        }

    @classmethod
    def _summarize_parameters(cls, spec: StrategySpec) -> dict[str, Any]:
        params = dict(spec.params or {})
        summary: dict[str, Any] = {}
        for key, value in params.items():
            if key in {"research_task", "event_context"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
            elif isinstance(value, list) and len(value) <= 12 and all(
                isinstance(item, (str, int, float, bool)) or item is None for item in value
            ):
                summary[key] = value
            elif key == "dsl" and isinstance(value, dict):
                dsl_summary = cls._compact_dict(
                    value,
                    keys=("version", "timeframe", "entry", "exit", "risk_rules"),
                )
                metadata = dict(value.get("metadata") or {})
                if metadata:
                    dsl_summary["metadata"] = {
                        meta_key: metadata.get(meta_key)
                        for meta_key in (
                            "target_symbols",
                            "stock_pool",
                            "portfolio_spec",
                            "execution_assumptions",
                            "validation_profile",
                            "targeting_policy",
                            "constraint_check",
                        )
                        if metadata.get(meta_key) not in (None, "", [], {})
                    }
                if dsl_summary:
                    summary[key] = dsl_summary
            elif key == "stock_pool" and isinstance(value, dict):
                summary[key] = cls._summarize_stock_pool(value)
        dsl_activity = dict(spec.metadata.get("dsl_activity") or {})
        if dsl_activity:
            summary["dsl_activity"] = dsl_activity
        elif params.get("dsl") not in (None, {}, []):
            summary["dsl_present"] = True
        target_symbols = list(spec.metadata.get("target_symbols") or [])
        if target_symbols:
            summary["target_symbols"] = target_symbols[:12]
        return summary

    @classmethod
    def _summarize_llm_research_context(cls, context: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(context or {})
        summary = cls._compact_dict(
            payload,
            keys=(
                "snapshot_date",
                "fear_greed_index",
                "task_source",
                "candidate_family",
                "factor_name",
            ),
        )
        for key in ("target_symbols", "candidate_universe", "preferred_strategy_types", "top_factor_names"):
            items = list(payload.get(key) or [])
            if items:
                summary[key] = items[:12]
                summary[f"{key}_count"] = len(items)
        for key in ("symbol_frames", "symbol_details", "parents", "history_summary"):
            value = payload.get(key)
            if isinstance(value, dict):
                summary[f"{key}_count"] = len(value)
            elif isinstance(value, list):
                summary[f"{key}_count"] = len(value)
        return summary

    @classmethod
    def _summarize_llm_response(cls, response: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(response or {})
        request_metrics = dict(payload.get("request_metrics") or {})
        summary = cls._compact_dict(
            payload,
            keys=("provider", "model"),
        )
        candidates = list(payload.get("candidates") or [])
        if candidates:
            summary["candidate_count"] = len(candidates)
            summary["candidate_names"] = [
                str((item or {}).get("name") or "")
                for item in candidates[: cls._PREVIEW_LIMIT]
            ]
        analysis = dict(payload.get("analysis") or {})
        if analysis:
            summary["analysis"] = cls._compact_dict(
                analysis,
                keys=("style_bias", "market_regime", "theme", "direction", "confidence"),
            )
        if request_metrics:
            summary["request_metrics"] = cls._compact_dict(
                request_metrics,
                keys=(
                    "status",
                    "requested_limit",
                    "attempt_count",
                    "prompt_profile",
                    "prompt_chars",
                    "response_chars",
                    "selected_candidate_count",
                    "elapsed_seconds",
                    "last_error_type",
                    "last_error",
                ),
            )
        return summary

    @classmethod
    def _summarize_hypothesis_artifact(cls, artifact: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(artifact or {})
        if not payload:
            return {}
        summary = cls._compact_dict(
            payload,
            keys=(
                "artifact_id",
                "version",
                "provider",
                "model",
                "family_hint",
                "holding_rationale",
                "alpha_half_life",
                "position_model",
                "validation_focus",
            ),
        )
        if payload.get("alpha_hypothesis") not in (None, "", [], {}):
            summary["alpha_hypothesis"] = payload.get("alpha_hypothesis")
        if payload.get("failure_mode") not in (None, "", [], {}):
            summary["failure_mode"] = payload.get("failure_mode")
        if payload.get("target_universe_hypothesis") not in (None, "", [], {}):
            summary["target_universe_hypothesis"] = payload.get("target_universe_hypothesis")
        if payload.get("capacity_assumption") not in (None, "", [], {}):
            summary["capacity_assumption"] = payload.get("capacity_assumption")
        if payload.get("cost_sensitivity_grid") not in (None, "", [], {}):
            summary["cost_sensitivity_grid"] = payload.get("cost_sensitivity_grid")
        return summary

    @classmethod
    def _build_replay_strategy_contract(
        cls,
        *,
        spec: StrategySpec,
        research_task: Optional[dict[str, Any]],
        event_context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = dict(spec.metadata or {})
        return {
            "strategy_type": spec.strategy_type,
            "name": spec.name,
            "description": spec.description,
            "tags": list(spec.tags or []),
            "params": dict(spec.params or {}),
            "target_symbols": list(metadata.get("target_symbols") or [])[:12],
            "stock_pool": dict(metadata.get("stock_pool") or {}),
            "selection_logic": list(metadata.get("selection_logic") or []),
            "research_task": dict(research_task or {}),
            "event_context": dict(event_context or {}),
            "hypothesis_artifact": dict(metadata.get("hypothesis_artifact") or {}),
            "hypothesis_lowering_audit": dict(metadata.get("hypothesis_lowering_audit") or {}),
            "holding_horizon": dict(metadata.get("holding_horizon") or {}),
            "trade_plan": dict(metadata.get("trade_plan") or {}),
            "risk_rules": dict(metadata.get("risk_rules") or {}),
            "position_sizing": dict(metadata.get("position_sizing") or {}),
            "execution_notes": metadata.get("execution_notes"),
            "rebalance_rule": dict(metadata.get("rebalance_rule") or {}),
            "portfolio_spec": dict(metadata.get("portfolio_spec") or {}),
            "execution_assumptions": dict(metadata.get("execution_assumptions") or {}),
            "validation_profile": dict(metadata.get("validation_profile") or {}),
            "targeting_policy": dict(metadata.get("targeting_policy") or {}),
            "constraint_check": dict(metadata.get("constraint_check") or {}),
        }

    @classmethod
    def _build_persisted_experiment_payload(
        cls,
        *,
        spec: StrategySpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        research_task = dict((payload.get("strategy_spec") or {}).get("research_task") or {})
        event_context = dict((payload.get("strategy_spec") or {}).get("event_context") or {})
        replay_contract = cls._build_replay_strategy_contract(
            spec=spec,
            research_task=research_task,
            event_context=event_context,
        )
        strategy_spec = {
            "strategy_type": spec.strategy_type,
            "name": spec.name,
            "description": spec.description,
            "tags": list(spec.tags or []),
            "params": cls._summarize_parameters(spec),
            "target_symbols": list(spec.metadata.get("target_symbols") or [])[:12],
            "stock_pool": cls._summarize_stock_pool(spec.metadata.get("stock_pool") or {}),
            "selection_logic": cls._summarize_selection_logic(spec.metadata.get("selection_logic") or []),
            "research_task": cls._summarize_research_task(research_task),
            "event_context": cls._summarize_event_context(event_context),
            "hypothesis_artifact": cls._summarize_hypothesis_artifact(spec.metadata.get("hypothesis_artifact") or {}),
            "holding_horizon": dict(spec.metadata.get("holding_horizon") or {}),
            "trade_plan": dict(spec.metadata.get("trade_plan") or {}),
            "risk_rules": dict(spec.metadata.get("risk_rules") or {}),
            "position_sizing": dict(spec.metadata.get("position_sizing") or {}),
            "execution_notes": spec.metadata.get("execution_notes"),
            "rebalance_rule": dict(spec.metadata.get("rebalance_rule") or {}),
            "portfolio_spec": dict(spec.metadata.get("portfolio_spec") or {}),
            "execution_assumptions": dict(spec.metadata.get("execution_assumptions") or {}),
            "validation_profile": dict(spec.metadata.get("validation_profile") or {}),
            "replay_contract": replay_contract,
        }
        evaluation = {
            "source": payload.get("source"),
            "task_run_id": payload.get("task_run_id"),
            "generation_reason": dict(spec.metadata.get("generation_reason") or {}),
            "committee_review": dict(spec.metadata.get("committee_review") or {}),
            "llm_analysis": dict(spec.metadata.get("llm_analysis") or {}),
            "llm_research_context": cls._summarize_llm_research_context(spec.metadata.get("llm_research_context") or {}),
            "llm_response": cls._summarize_llm_response(spec.metadata.get("llm_response") or {}),
            "target_symbols": list(spec.metadata.get("target_symbols") or [])[:12],
            "stock_pool": cls._summarize_stock_pool(spec.metadata.get("stock_pool") or {}),
            "selection_logic": cls._summarize_selection_logic(spec.metadata.get("selection_logic") or []),
            "research_scope": cls._compact_dict(
                spec.metadata.get("research_scope") or {},
                keys=("scope", "symbol_count", "candidate_count", "source"),
            ),
            "hypothesis_artifact": cls._summarize_hypothesis_artifact(spec.metadata.get("hypothesis_artifact") or {}),
            "hypothesis_lowering_audit": cls._compact_dict(
                spec.metadata.get("hypothesis_lowering_audit") or {},
                keys=("source", "target_symbols"),
            ),
            "research_task": cls._summarize_research_task(research_task),
            "event_context": cls._summarize_event_context(event_context),
        }
        return {
            **payload,
            "parameters": cls._summarize_parameters(spec),
            "strategy_spec": strategy_spec,
            "evaluation": evaluation,
            "result": dict(payload.get("result") or {}),
        }

    async def record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        experiment_id = f"exp_{int(time.time())}_{uuid4().hex[:8]}"
        hypothesis_artifact = dict(spec.metadata.get("hypothesis_artifact") or {})
        hypothesis = (
            str(hypothesis_artifact.get("alpha_hypothesis") or "").strip()
            or spec.description
            or f"{source}:{spec.strategy_type}"
        )
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
                "hypothesis_artifact": hypothesis_artifact,
                "holding_horizon": spec.metadata.get("holding_horizon") or {},
                "trade_plan": spec.metadata.get("trade_plan") or {},
                "risk_rules": spec.metadata.get("risk_rules") or {},
                "position_sizing": spec.metadata.get("position_sizing") or {},
                "execution_notes": spec.metadata.get("execution_notes"),
                "rebalance_rule": spec.metadata.get("rebalance_rule") or {},
                "portfolio_spec": spec.metadata.get("portfolio_spec") or {},
                "execution_assumptions": spec.metadata.get("execution_assumptions") or {},
                "validation_profile": spec.metadata.get("validation_profile") or {},
                "hypothesis_lowering_audit": spec.metadata.get("hypothesis_lowering_audit") or {},
                "replay_contract": self._build_replay_strategy_contract(
                    spec=spec,
                    research_task=research_task,
                    event_context=event_context,
                ),
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
                "hypothesis_artifact": hypothesis_artifact,
                "hypothesis_lowering_audit": spec.metadata.get("hypothesis_lowering_audit") or {},
                "research_task": research_task,
                "event_context": event_context,
            },
            "result": {},
            "parent_experiment_id": None,
            "artifact_id": artifact.get("artifact_id"),
        }
        persisted_payload = self._build_persisted_experiment_payload(
            spec=spec,
            payload=payload,
        )
        try:
            return await db.save_strategy_generation_experiment(persisted_payload)
        except Exception as exc:
            logger.warning(
                "ExperimentRecorder: save experiment failed, continuing without persistence: %s",
                exc,
            )
            return {
                **persisted_payload,
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
