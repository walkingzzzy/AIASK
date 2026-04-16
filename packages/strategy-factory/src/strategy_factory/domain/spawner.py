"""策略工厂候选生成。"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from .constants import (
    CATEGORY_MINIMUMS,
    SPAWNER_EVENT_SOURCE_BASE_CAP,
    SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS,
    SPAWNER_EVENT_FILL_BUDGET_MAX,
    SPAWNER_FILL_BUDGET_MAX,
    SPAWNER_TARGET_TOTAL,
    preferred_strategy_types_for_factor,
)
from .parameter_distribution_registry import ParameterDistributionRegistry
from .targets import _normalize_target_codes


class StrategySpawner:
    """根据每日数据快照生成候选策略。"""
    _TREND_CLUSTER_TYPES = frozenset({"momentum", "ma_cross", "volatility_breakout", "sector_rotation"})
    _LOCAL_GENERATION_CAPS = {
        "mean_reversion_short": 1,
    }
    _DIVERSIFICATION_GROUPS = {
        "quality_defensive": frozenset({"quality_factor", "value_factor", "macro_timing"}),
        "mean_reversion": frozenset({"rsi", "gap_fill", "mean_reversion_short"}),
        "flow_rotation": frozenset({"north_capital_track", "sector_rotation", "margin_divergence"}),
    }
    _POOL_PROFILE_BY_TYPE = {
        "momentum": "high_vol_growth",
        "volatility_breakout": "high_vol_growth",
        "growth_factor": "high_vol_growth",
        "gap_fill": "high_vol_growth",
        "mean_reversion_short": "high_vol_growth",
        "rsi": "high_vol_growth",
        "quality_factor": "low_vol_defensive",
        "value_factor": "low_vol_defensive",
        "macro_timing": "low_vol_defensive",
        "north_capital_track": "cycle_resource",
        "sector_rotation": "cycle_resource",
        "margin_divergence": "cycle_resource",
        "ma_cross": "cycle_resource",
    }
    _SNAPSHOT_TARGET_SYMBOL_BUDGET_BY_TYPE = {
        "momentum": 3,
        "ma_cross": 3,
        "rsi": 3,
        "volatility_breakout": 3,
        "gap_fill": 2,
        "mean_reversion_short": 2,
        "value_factor": 4,
        "quality_factor": 4,
        "growth_factor": 4,
        "multi_factor": 4,
        "macro_timing": 4,
        "sector_rotation": 4,
        "north_capital_track": 3,
        "margin_divergence": 3,
    }
    _SNAPSHOT_TARGET_FAMILY_ALIASES = {
        "momentum": ("momentum", "ma_cross", "growth_factor"),
        "ma_cross": ("ma_cross", "momentum", "quality_factor"),
        "rsi": ("rsi", "gap_fill", "mean_reversion_short", "value_factor"),
        "volatility_breakout": ("volatility_breakout", "momentum", "ma_cross"),
        "gap_fill": ("gap_fill", "rsi", "mean_reversion_short"),
        "mean_reversion_short": ("mean_reversion_short", "rsi", "gap_fill", "value_factor"),
        "value_factor": ("value_factor", "quality_factor", "multi_factor"),
        "quality_factor": ("quality_factor", "value_factor", "multi_factor"),
        "growth_factor": ("growth_factor", "momentum", "quality_factor"),
        "multi_factor": ("multi_factor", "quality_factor", "value_factor", "growth_factor"),
        "macro_timing": ("macro_timing", "quality_factor", "value_factor", "ma_cross"),
        "sector_rotation": ("sector_rotation", "north_capital_track", "quality_factor", "ma_cross"),
        "north_capital_track": ("north_capital_track", "sector_rotation", "quality_factor", "growth_factor"),
        "margin_divergence": ("margin_divergence", "sector_rotation", "value_factor", "quality_factor"),
    }

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "candidate_count": 0,
                "source_counts": {},
                "strategy_type_counts": {},
                "quota_fill_count": 0,
                "signal_trigger_count": 0,
                "threshold_hit_count": 0,
                "parameter_source_counts": {},
                "quota_fill_mode_counts": {},
                "quota_fill_quality_counts": {},
                "historical_distribution_count": 0,
                "historical_guided_quota_fill_count": 0,
                "signal_aligned_quota_fill_count": 0,
                "no_signal_quota_fill_count": 0,
                "effective_quota_fill_count": 0,
            }
        }

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _threshold(field: str, operator: str, threshold: Any, actual: Any, label: Optional[str] = None) -> dict:
        item = {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "matched": True,
        }
        if label:
            item["label"] = label
        return item

    @staticmethod
    def _build_generation_reason(
        source: str,
        reason: str,
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        return {
            "kind": kind,
            "source": source,
            "summary": reason,
            "trigger_signal": trigger_signal or {},
            "trigger_thresholds": list(trigger_thresholds or []),
            "quota_fill": quota_fill,
        }

    @classmethod
    def _trend_cluster_count(cls, candidates: Optional[List[dict]]) -> int:
        return sum(
            1
            for item in list(candidates or [])
            if str((item or {}).get("strategy_type") or "").strip() in cls._TREND_CLUSTER_TYPES
        )

    @classmethod
    def _diversification_debt(cls, candidates: Optional[List[dict]]) -> List[str]:
        present = {
            str((item or {}).get("strategy_type") or "").strip()
            for item in list(candidates or [])
            if str((item or {}).get("strategy_type") or "").strip()
        }
        debt: List[str] = []
        for group_name, members in cls._DIVERSIFICATION_GROUPS.items():
            if not any(strategy_type in present for strategy_type in members):
                debt.append(group_name)
        return debt

    @classmethod
    def _pool_profile_distribution(cls, candidates: Optional[List[dict]]) -> Dict[str, int]:
        distribution: Dict[str, int] = {}
        for item in list(candidates or []):
            strategy_type = str((item or {}).get("strategy_type") or "").strip()
            profile = cls._POOL_PROFILE_BY_TYPE.get(strategy_type, "unknown")
            distribution[profile] = distribution.get(profile, 0) + 1
        return distribution

    @classmethod
    def _local_generation_cap(cls, strategy_type: str) -> Optional[int]:
        normalized = str(strategy_type or "").strip().lower()
        if not normalized:
            return None
        cap = cls._LOCAL_GENERATION_CAPS.get(normalized)
        return int(cap) if cap is not None else None

    @staticmethod
    def _build_spawn_report(
        candidates: List[dict],
        *,
        event_ready: bool = False,
        event_ready_supplemental: bool = False,
        source_raw_counts: Optional[Dict[str, int]] = None,
        source_budget_caps: Optional[Dict[str, Optional[int]]] = None,
        source_budget_weights: Optional[Dict[str, Optional[float]]] = None,
    ) -> dict:
        source_counts: Dict[str, int] = {}
        strategy_type_counts: Dict[str, int] = {}
        quota_fill_count = 0
        signal_trigger_count = 0
        threshold_hit_count = 0
        parameter_source_counts: Dict[str, int] = {}
        quota_fill_mode_counts: Dict[str, int] = {}
        quota_fill_quality_counts: Dict[str, int] = {}
        historical_quota_fill_count = 0
        signal_aligned_quota_fill_count = 0
        no_signal_quota_fill_count = 0
        for candidate in candidates:
            generation_reason = candidate.get("generation_reason") or {}
            source = str(generation_reason.get("source") or "unknown")
            strategy_type = str(candidate.get("strategy_type") or "unknown")
            parameter_source = str(candidate.get("parameter_source") or "").strip()
            source_counts[source] = source_counts.get(source, 0) + 1
            strategy_type_counts[strategy_type] = strategy_type_counts.get(strategy_type, 0) + 1
            if parameter_source:
                parameter_source_counts[parameter_source] = parameter_source_counts.get(parameter_source, 0) + 1
            threshold_hit_count += len(candidate.get("trigger_thresholds") or [])
            if candidate.get("quota_fill"):
                quota_fill_count += 1
                fill_meta = dict(candidate.get("quota_fill") or {})
                fill_mode = str(fill_meta.get("fill_source_mode") or "unknown").strip()
                fill_quality = str(fill_meta.get("fill_quality_tier") or "unknown").strip()
                if fill_mode:
                    quota_fill_mode_counts[fill_mode] = quota_fill_mode_counts.get(fill_mode, 0) + 1
                if fill_quality:
                    quota_fill_quality_counts[fill_quality] = quota_fill_quality_counts.get(fill_quality, 0) + 1
                if fill_mode == "historical_guided":
                    historical_quota_fill_count += 1
                elif fill_mode == "signal_aligned":
                    signal_aligned_quota_fill_count += 1
                elif fill_mode == "no_signal_fallback":
                    no_signal_quota_fill_count += 1
            else:
                signal_trigger_count += 1
        raw_counts = dict(source_raw_counts or {})
        budget_caps = dict(source_budget_caps or {})
        budget_weights = dict(source_budget_weights or {})
        trimmed_count = sum(
            max(0, int(raw_counts.get(source, 0) or 0) - int(source_counts.get(source, 0) or 0))
            for source in raw_counts
        )
        trend_cluster_count = StrategySpawner._trend_cluster_count(candidates)
        diversification_debt = StrategySpawner._diversification_debt(candidates)
        return {
            "summary": {
                "candidate_count": len(candidates),
                "source_counts": source_counts,
                "strategy_type_counts": strategy_type_counts,
                "quota_fill_count": quota_fill_count,
                "signal_trigger_count": signal_trigger_count,
                "threshold_hit_count": threshold_hit_count,
                "event_ready": bool(event_ready),
                "event_ready_supplemental": bool(event_ready_supplemental),
                "source_raw_counts": raw_counts,
                "source_budget_caps": budget_caps,
                "source_budget_weights": budget_weights,
                "source_trimmed_count": trimmed_count,
                "parameter_source_counts": parameter_source_counts,
                "historical_distribution_count": int(parameter_source_counts.get("historical_distribution") or 0),
                "quota_fill_mode_counts": quota_fill_mode_counts,
                "quota_fill_quality_counts": quota_fill_quality_counts,
                "historical_guided_quota_fill_count": historical_quota_fill_count,
                "signal_aligned_quota_fill_count": signal_aligned_quota_fill_count,
                "no_signal_quota_fill_count": no_signal_quota_fill_count,
                "effective_quota_fill_count": max(quota_fill_count - no_signal_quota_fill_count, 0),
                "trend_cluster_ratio": round(trend_cluster_count / len(candidates), 4) if candidates else 0.0,
                "diversification_debt": diversification_debt,
                "pool_profile_distribution": StrategySpawner._pool_profile_distribution(candidates),
            }
        }

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _factor_research(snapshot: dict) -> dict:
        return dict(snapshot.get("factor_research") or {})

    @classmethod
    def _factor_maps(cls, snapshot: dict) -> tuple[Dict[str, float], Dict[str, str]]:
        artifact = cls._factor_research(snapshot)
        ranked_factors = list(artifact.get("ranked_factors") or [])
        factor_ic: Dict[str, float] = {}
        factor_trend: Dict[str, str] = {}
        for item in ranked_factors:
            name = str((item or {}).get("factor_name") or "").strip()
            if not name:
                continue
            factor_ic[name] = cls._safe_float((item or {}).get("ic_value"))
            factor_trend[name] = str((item or {}).get("trend") or "flat").strip().lower() or "flat"
        if factor_ic or factor_trend:
            return factor_ic, factor_trend
        active_candidate_pool = dict(artifact.get("active_candidate_pool") or {})
        top_candidates = list(active_candidate_pool.get("top_candidates") or [])
        for item in top_candidates:
            family = str((item or {}).get("family") or "").strip().lower()
            if not family:
                continue
            factor_ic[family] = max(
                factor_ic.get(family, 0.0),
                cls._safe_float((item or {}).get("total_score")) / 100.0,
            )
            factor_trend[family] = "rising"
        if factor_ic or factor_trend:
            return factor_ic, factor_trend
        return dict(snapshot.get("factor_ic") or {}), dict(snapshot.get("factor_ic_trend") or {})

    @classmethod
    def _strong_rising_factor_names(cls, snapshot: dict, minimum_ic: float = 0.04) -> List[str]:
        factor_ic, factor_trend = cls._factor_maps(snapshot)
        return [
            name
            for name, ic_value in factor_ic.items()
            if cls._safe_float(ic_value) >= minimum_ic and str(factor_trend.get(name) or "").strip().lower() == "rising"
        ]

    @classmethod
    def _factor_preferred_strategy_types(cls, snapshot: dict) -> List[str]:
        artifact = cls._factor_research(snapshot)
        preferred = [
            str(item).strip()
            for item in list(artifact.get("preferred_strategy_types") or [])
            if str(item).strip() in CATEGORY_MINIMUMS
        ]
        if preferred:
            return preferred

        factor_ic, factor_trend = cls._factor_maps(snapshot)
        derived: List[str] = []
        for factor_name in ("momentum", "value", "quality", "growth"):
            trend = str(factor_trend.get(factor_name) or "").strip().lower()
            ic_value = cls._safe_float(factor_ic.get(factor_name))
            if trend == "rising" and ic_value > 0.0:
                mapped = tuple(preferred_strategy_types_for_factor(factor_name, default=[]))
                for strategy_type in mapped:
                    if strategy_type in CATEGORY_MINIMUMS and strategy_type not in derived:
                        derived.append(strategy_type)
        return derived

    @classmethod
    def _snapshot_target_symbol_budget(cls, strategy_type: str) -> int:
        normalized = str(strategy_type or "").strip().lower()
        return max(0, int(cls._SNAPSHOT_TARGET_SYMBOL_BUDGET_BY_TYPE.get(normalized, 0) or 0))

    @classmethod
    def _snapshot_target_family_aliases(cls, strategy_type: str) -> tuple[str, ...]:
        normalized = str(strategy_type or "").strip().lower()
        aliases = cls._SNAPSHOT_TARGET_FAMILY_ALIASES.get(normalized)
        if aliases:
            return tuple(str(item).strip().lower() for item in aliases if str(item).strip())
        return (normalized,) if normalized else tuple()

    @classmethod
    def _snapshot_target_symbols(cls, strategy_type: str, snapshot: dict) -> List[str]:
        budget = cls._snapshot_target_symbol_budget(strategy_type)
        aliases = cls._snapshot_target_family_aliases(strategy_type)
        if budget <= 0 or not aliases:
            return []

        allocation = dict(cls._factor_research(snapshot).get("stock_family_allocation") or {})
        ranked_matches: list[tuple[float, str]] = []
        for raw_code, raw_item in allocation.items():
            code = str(raw_code or "").strip()
            payload = dict(raw_item or {})
            if not code:
                continue
            plans = [
                dict(plan or {})
                for plan in list(payload.get("family_plans") or [])
                if isinstance(plan, dict)
            ]
            families = [
                str(item or "").strip().lower()
                for item in list(payload.get("families") or [])
                if str(item or "").strip()
            ]

            matched_alias_index: Optional[int] = None
            matched_rank: Optional[int] = None
            matched_budget = 0.0
            matched_penalty = 0.0
            for alias_index, alias in enumerate(aliases):
                if plans:
                    for fallback_rank, plan in enumerate(plans, 1):
                        family = str(plan.get("family") or "").strip().lower()
                        if family != alias:
                            continue
                        matched_alias_index = alias_index
                        matched_rank = max(1, int(plan.get("family_rank") or fallback_rank))
                        matched_budget = max(
                            0.0,
                            min(
                                cls._safe_float(plan.get("budget_weight") or plan.get("budget")),
                                1.0,
                            ),
                        )
                        matched_penalty = max(
                            0.0,
                            min(cls._safe_float(plan.get("failure_penalty")), 1.0),
                        )
                        break
                    if matched_alias_index is not None:
                        break
                elif alias in families:
                    matched_alias_index = alias_index
                    matched_rank = max(1, families.index(alias) + 1)
                    break
            if matched_alias_index is None:
                continue

            priority = max(0.0, min(cls._safe_float(payload.get("priority")), 1.0))
            top_family = str(payload.get("top_family") or "").strip().lower()
            source_bonus = 1.5 if str(payload.get("source_mode") or "").strip().lower() == "stock_universe_projection" else 0.0
            alias_bonus = max(0.0, 8.0 - matched_alias_index * 2.0)
            rank_bonus = max(0.0, 16.0 - (max(1, int(matched_rank or 1)) - 1) * 4.0)
            exact_bonus = 4.0 if top_family == str(strategy_type or "").strip().lower() else 0.0
            score = (
                priority * 100.0
                + alias_bonus
                + rank_bonus
                + matched_budget * 10.0
                - matched_penalty * 12.0
                + source_bonus
                + exact_bonus
            )
            ranked_matches.append((round(score, 4), code))

        ranked_matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return _normalize_target_codes([code for _score, code in ranked_matches], limit=budget)

    @classmethod
    def _apply_snapshot_target_alignment(cls, candidate: dict, snapshot: dict) -> dict:
        item = dict(candidate or {})
        if not item:
            return {}
        strategy_type = str(item.get("strategy_type") or "").strip().lower()
        if not strategy_type:
            return item
        existing_targets = _normalize_target_codes(
            [
                item.get("requested_target_symbols"),
                item.get("target_symbols"),
                item.get("stock_pool"),
                dict(item.get("research_task") or {}).get("target_symbols"),
                dict(item.get("research_task") or {}).get("stock_pool"),
            ],
            limit=12,
        )
        if existing_targets:
            return item

        target_symbols = cls._snapshot_target_symbols(strategy_type, snapshot)
        if not target_symbols:
            return item

        candidate_family = str(item.get("candidate_family") or strategy_type).strip().lower() or strategy_type
        research_task = {
            **dict(item.get("research_task") or {}),
            "task_source": "snapshot",
            "preferred_strategy_types": [strategy_type],
            "allowed_strategy_types": [strategy_type],
            "strategy_preferences": [strategy_type],
            "candidate_family": candidate_family,
            "target_symbols": list(target_symbols),
            "stock_pool": {"selection_mode": "explicit", "symbols": list(target_symbols)},
            "target_symbol_policy": "strict_intersection",
            "universe_expansion_policy": "forbid",
            "validation_focus": "candidate_target_only",
            "preference_strength": "soft",
            "preference_reason": f"snapshot_local_spawn:{strategy_type}",
            "gate_1_representative_count": min(3, len(target_symbols)),
            "synthetic_local_spawn": True,
        }
        tags = list(item.get("tags") or [])
        for tag in ("targeted_universe", "synthetic_local_spawn"):
            if tag not in tags:
                tags.append(tag)

        return {
            **item,
            "candidate_family": candidate_family,
            "research_task": research_task,
            "requested_target_symbols": list(target_symbols),
            "target_symbols": list(target_symbols),
            "stock_pool": {"selection_mode": "explicit", "symbols": list(target_symbols)},
            "tags": tags,
        }

    def spawn(self, snapshot: dict) -> List[dict]:
        event_ready = self._event_research_ready(snapshot)
        event_ready_supplemental = self._event_ready_supports_local_fill(snapshot)
        source_batches = self._build_signal_batches(snapshot)
        signal_candidates, source_raw_counts, source_budget_caps, source_budget_weights = self._merge_signal_batches(
            source_batches,
            event_ready=event_ready,
            event_ready_supplemental=event_ready_supplemental,
        )
        signal_candidates += self._expand_signal_variants(snapshot, signal_candidates)
        quota_candidates = self._fill_gaps(snapshot, signal_candidates)
        candidates = [
            self._apply_snapshot_target_alignment(candidate, snapshot)
            for candidate in [*signal_candidates, *quota_candidates]
        ]
        self.last_report = self._build_spawn_report(
            candidates,
            event_ready=event_ready,
            event_ready_supplemental=event_ready_supplemental,
            source_raw_counts=source_raw_counts,
            source_budget_caps=source_budget_caps,
            source_budget_weights=source_budget_weights,
        )
        return candidates

    def _build_signal_batches(self, snapshot: dict) -> Dict[str, List[dict]]:
        return {
            "fear_greed": self._from_fear_greed(snapshot),
            "factor_ic": self._from_factor_ic(snapshot),
            "volatility": self._from_volatility(snapshot),
            "fund_flow": self._from_fund_flow(snapshot),
        }

    @staticmethod
    def _event_ready_source_cap(*, event_ready_supplemental: bool) -> int:
        return max(0, SPAWNER_EVENT_SOURCE_BASE_CAP + (SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS if event_ready_supplemental else 0))

    @staticmethod
    def _event_ready_source_weights(*, event_ready_supplemental: bool) -> Dict[str, float]:
        if event_ready_supplemental:
            return {
                "fear_greed": 0.75,
                "factor_ic": 1.0,
                "volatility": 0.70,
                "fund_flow": 0.80,
            }
        return {
            "fear_greed": 0.45,
            "factor_ic": 1.0,
            "volatility": 0.40,
            "fund_flow": 0.50,
        }

    @staticmethod
    def _weighted_source_cap(raw_count: int, *, weight: float, minimum_floor: int) -> int:
        if raw_count <= 0:
            return 0
        scaled = int(round(raw_count * max(0.0, weight)))
        return max(1, min(raw_count, max(minimum_floor, scaled)))

    @classmethod
    def _merge_signal_batches(
        cls,
        source_batches: Dict[str, List[dict]],
        *,
        event_ready: bool,
        event_ready_supplemental: bool,
    ) -> tuple[List[dict], Dict[str, int], Dict[str, Optional[int]], Dict[str, Optional[float]]]:
        source_raw_counts = {source: len(list(items or [])) for source, items in dict(source_batches or {}).items()}
        if not event_ready:
            ordered = [
                *list(source_batches.get("fear_greed") or []),
                *list(source_batches.get("factor_ic") or []),
                *list(source_batches.get("volatility") or []),
                *list(source_batches.get("fund_flow") or []),
            ]
            return (
                ordered,
                source_raw_counts,
                {source: None for source in source_raw_counts},
                {source: None for source in source_raw_counts},
            )

        local_source_floor = cls._event_ready_source_cap(event_ready_supplemental=event_ready_supplemental)
        source_weights = cls._event_ready_source_weights(event_ready_supplemental=event_ready_supplemental)
        capped_batches: Dict[str, List[dict]] = {}
        source_budget_caps: Dict[str, Optional[int]] = {}
        source_budget_weights: Dict[str, Optional[float]] = {}

        for source in ("fear_greed", "factor_ic", "volatility", "fund_flow"):
            items = list(source_batches.get(source) or [])
            weight = float(source_weights.get(source, 1.0) or 0.0)
            if source == "factor_ic":
                capped_batches[source] = items
                source_budget_caps[source] = None
                source_budget_weights[source] = weight
                continue
            cap = cls._weighted_source_cap(
                len(items),
                weight=weight,
                minimum_floor=local_source_floor,
            )
            capped_batches[source] = items[:cap]
            source_budget_caps[source] = cap
            source_budget_weights[source] = weight

        ordered = [
            *capped_batches["fear_greed"],
            *capped_batches["factor_ic"],
            *capped_batches["volatility"],
            *capped_batches["fund_flow"],
        ]
        return ordered, source_raw_counts, source_budget_caps, source_budget_weights

    @staticmethod
    def _event_research_ready(snapshot: dict) -> bool:
        event_driven = dict(snapshot.get("event_driven") or {})
        return bool(int(event_driven.get("event_count") or 0) or int(event_driven.get("tasks_ready_count") or 0))

    @staticmethod
    def _event_ready_supports_local_fill(snapshot: dict) -> bool:
        strong_factor_count = len(StrategySpawner._strong_rising_factor_names(snapshot, minimum_ic=0.04))
        fear_greed = float(snapshot.get("fear_greed_index") or 50.0)
        volatility = float(dict(snapshot.get("fg_components") or {}).get("volatility") or 50.0)
        north_3d = abs(float(snapshot.get("north_fund_3d_net") or 0.0)) >= 5_000_000_000
        margin_5d = abs(float(snapshot.get("margin_5d_change_pct") or 0.0)) >= 2.0
        extreme_fg = abs(fear_greed - 50.0) >= 18.0
        extreme_volatility = volatility <= 35.0 or volatility >= 65.0
        return bool(strong_factor_count or extreme_fg or extreme_volatility or north_3d or margin_5d)

    @staticmethod
    def _generated_type_counts(candidates: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in list(candidates or []):
            strategy_type = str(item.get("strategy_type") or "").strip()
            if not strategy_type:
                continue
            counts[strategy_type] = counts.get(strategy_type, 0) + 1
        return counts

    @classmethod
    def _preferred_fill_types(cls, snapshot: dict, current_counts: Optional[Dict[str, int]] = None) -> List[str]:
        preferred: List[str] = []

        def add(*types: str) -> None:
            for strategy_type in types:
                if strategy_type in CATEGORY_MINIMUMS and strategy_type not in preferred:
                    preferred.append(strategy_type)

        fear_greed = int(snapshot.get("fear_greed_index") or 50)
        if fear_greed <= 35:
            add("rsi", "gap_fill", "mean_reversion_short", "quality_factor", "macro_timing")
        elif fear_greed >= 65:
            add("growth_factor", "quality_factor", "north_capital_track", "sector_rotation", "volatility_breakout")
        else:
            add("quality_factor", "north_capital_track", "sector_rotation", "gap_fill", "ma_cross")

        north_3d = float(snapshot.get("north_fund_3d_net") or 0.0)
        if north_3d >= 5_000_000_000:
            add("north_capital_track", "quality_factor", "growth_factor", "sector_rotation")
        elif north_3d <= -5_000_000_000:
            add("value_factor", "macro_timing", "rsi", "quality_factor")

        margin_5d = float(snapshot.get("margin_5d_change_pct") or 0.0)
        if margin_5d >= 2.0:
            add("volatility_breakout", "sector_rotation", "north_capital_track")
        elif margin_5d <= -2.0:
            add("rsi", "gap_fill", "value_factor")

        add(*cls._factor_preferred_strategy_types(snapshot))

        event_driven = dict(snapshot.get("event_driven") or {})
        if int(event_driven.get("event_count") or 0) > 0 or int(event_driven.get("tasks_ready_count") or 0) > 0:
            add("quality_factor", "north_capital_track", "sector_rotation", "gap_fill")

        if not preferred:
            add("quality_factor", "north_capital_track", "gap_fill", "ma_cross")

        counts = current_counts or {}
        return sorted(preferred, key=lambda strategy_type: (int(counts.get(strategy_type) or 0), preferred.index(strategy_type)))

    @staticmethod
    def _quota_fill_budget(snapshot: dict, signal_candidate_count: int) -> int:
        completeness = dict(snapshot.get("completeness") or {})
        completion_ratio = float(completeness.get("completion_ratio") or 1.0)
        event_ready = StrategySpawner._event_research_ready(snapshot)
        has_historical_distribution = ParameterDistributionRegistry.from_snapshot(snapshot).has_any_distribution()
        target_total = SPAWNER_TARGET_TOTAL
        if completion_ratio < 1.0:
            target_total = min(target_total, max(4, int(round(SPAWNER_TARGET_TOTAL * 0.75))))
        budget = max(0, target_total - max(0, int(signal_candidate_count or 0)))
        if event_ready:
            if signal_candidate_count <= 0 or not StrategySpawner._event_ready_supports_local_fill(snapshot):
                return 0
            return min(budget, SPAWNER_EVENT_FILL_BUDGET_MAX)
        if signal_candidate_count <= 0 and not has_historical_distribution:
            return min(budget, 1)
        return min(budget, SPAWNER_FILL_BUDGET_MAX)

    @staticmethod
    def _signal_expansion_budget(snapshot: dict, signal_candidate_count: int) -> int:
        if signal_candidate_count <= 0:
            return 0
        remaining = max(0, SPAWNER_TARGET_TOTAL - max(0, int(signal_candidate_count or 0)))
        if remaining <= 0:
            return 0
        strong_factor_count = len(StrategySpawner._strong_rising_factor_names(snapshot, minimum_ic=0.04))
        extreme_fg = abs(float(snapshot.get("fear_greed_index") or 50.0) - 50.0) >= 18.0
        north_3d = abs(float(snapshot.get("north_fund_3d_net") or 0.0)) >= 5_000_000_000
        margin_5d = abs(float(snapshot.get("margin_5d_change_pct") or 0.0)) >= 2.0
        signal_strength = strong_factor_count + int(extreme_fg) + int(north_3d) + int(margin_5d)
        if signal_strength <= 0:
            return 0
        return min(remaining, SPAWNER_FILL_BUDGET_MAX, max(1, signal_strength + 1))

    def _expand_signal_variants(self, snapshot: dict, signal_candidates: List[dict]) -> List[dict]:
        expansion_budget = self._signal_expansion_budget(snapshot, len(signal_candidates))
        if expansion_budget <= 0:
            return []
        parameter_registry = ParameterDistributionRegistry.from_snapshot(snapshot)

        current_counts = self._generated_type_counts(signal_candidates)
        threshold_hits: Dict[str, int] = {}
        preferred_types = self._preferred_fill_types(snapshot, current_counts)
        for item in list(signal_candidates or []):
            strategy_type = str(item.get("strategy_type") or "").strip()
            if not strategy_type:
                continue
            threshold_hits[strategy_type] = threshold_hits.get(strategy_type, 0) + len(item.get("trigger_thresholds") or [])

        ranked_types = sorted(
            current_counts.keys(),
            key=lambda strategy_type: (
                int(current_counts.get(strategy_type) or 0),
                int(threshold_hits.get(strategy_type) or 0),
                -(preferred_types.index(strategy_type) if strategy_type in preferred_types else len(preferred_types)),
            ),
            reverse=True,
        )
        if not ranked_types:
            return []

        existing_keys = {
            (
                str(item.get("strategy_type") or ""),
                json.dumps(item.get("params") or {}, sort_keys=True, ensure_ascii=False, default=str),
            )
            for item in list(signal_candidates or [])
        }
        out: List[dict] = []
        variation_counts: Dict[str, int] = {}

        for strategy_type in ranked_types:
            if len(out) >= expansion_budget:
                break
            generation_cap = self._local_generation_cap(strategy_type)
            existing_total_for_type = int(current_counts.get(strategy_type) or 0) + int(variation_counts.get(strategy_type) or 0)
            if generation_cap is not None and existing_total_for_type >= generation_cap:
                continue
            desired_variants = min(
                3,
                max(
                    1,
                    int(current_counts.get(strategy_type) or 0) - 1 + (1 if int(threshold_hits.get(strategy_type) or 0) >= 3 else 0),
                ),
            )
            if generation_cap is not None:
                desired_variants = min(desired_variants, max(0, generation_cap - existing_total_for_type))
            for _ in range(desired_variants):
                if len(out) >= expansion_budget:
                    break
                slot_index = int(current_counts.get(strategy_type) or 0) + int(variation_counts.get(strategy_type) or 0)
                params, parameter_source, parameter_sample_count = self._resolved_varied_defaults(
                    strategy_type,
                    slot_index,
                    snapshot=snapshot,
                    registry=parameter_registry,
                )
                key = (strategy_type, json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str))
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                variation_counts[strategy_type] = int(variation_counts.get(strategy_type) or 0) + 1
                candidate = self._make(
                    strategy_type,
                    params,
                    f"{strategy_type} 强信号延展参数变体#{variation_counts[strategy_type]}",
                    source="signal_variation",
                    trigger_signal={
                        "field": f"signal_type_counts.{strategy_type}",
                        "value": int(current_counts.get(strategy_type) or 0),
                        "threshold_hits": int(threshold_hits.get(strategy_type) or 0),
                        "parameter_source": parameter_source,
                    },
                    trigger_thresholds=[
                        self._threshold(
                            f"signal_type_counts.{strategy_type}",
                            ">=",
                            1,
                            int(current_counts.get(strategy_type) or 0),
                            "强信号变体扩容",
                        )
                    ],
                )
                candidate["parameter_source"] = parameter_source
                candidate["parameter_sample_count"] = parameter_sample_count
                out.append(candidate)
        return out

    def _from_fear_greed(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        fear_greed = snapshot.get("fear_greed_index", 50)
        if fear_greed < 30:
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 25, "overbought": 75}, f"恐贪{fear_greed}，恐惧区RSI抄底", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 6, "oversold": 20, "overbought": 80}, f"恐贪{fear_greed}，短周期RSI超跌", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
            out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，恐惧期精选价值", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
        elif fear_greed > 70:
            out.append(self._make("momentum", {"lookback": 5, "threshold": 0.01}, f"恐贪{fear_greed}，贪婪期短周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("momentum", {"lookback": 10, "threshold": 0.02}, f"恐贪{fear_greed}，贪婪期中周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("growth_factor", {"lookback": 40, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，贪婪期成长加速", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 35, "overbought": 65}, f"恐贪{fear_greed}，贪婪期RSI逃顶", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
        else:
            out.append(self._make("ma_cross", {"short_period": 5, "long_period": 20}, f"恐贪{fear_greed}，中性标准均线", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("momentum", {"lookback": 20, "threshold": 0.02}, f"恐贪{fear_greed}，中性标准动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
        return out

    def _from_factor_ic(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        factor_ic, trend = self._factor_maps(snapshot)

        for factor_name, ic_value in factor_ic.items():
            trend_value = trend.get(factor_name, "flat")
            if ic_value > 0.03 and trend_value == "rising":
                if factor_name == "momentum":
                    for lookback in [5, 10, 20]:
                        out.append(self._make("momentum", {"lookback": lookback, "threshold": 0.02}, f"momentum IC={ic_value:.3f}上升，{lookback}日动量", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "value":
                    out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"value IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "quality":
                    out.append(self._make("quality_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"quality IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "reversal":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70}, f"reversal IC={ic_value:.3f}上升，反转有效", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
            elif ic_value < -0.02 and trend_value == "falling" and factor_name == "momentum":
                out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70}, f"momentum IC={ic_value:.3f}下降，转反转", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", "<", -0.02, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "falling", trend_value, "趋势阈值")]))

        weights: Dict[str, float] = {}
        factor_signal_count = 0
        for factor_name in ["value", "quality", "growth"]:
            ic_value = factor_ic.get(factor_name, 0)
            trend_value = trend.get(factor_name, "flat")
            if trend_value == "rising":
                weights[factor_name] = max(0.1, 0.33 + ic_value * 2)
                if float(ic_value or 0.0) > 0.0:
                    factor_signal_count += 1
            elif trend_value == "falling":
                weights[factor_name] = max(0.05, 0.33 - abs(ic_value) * 2)
                if float(ic_value or 0.0) < 0.0:
                    factor_signal_count += 1
            else:
                weights[factor_name] = 0.33
        total = sum(weights.values()) or 1.0
        weights = {key: round(value / total, 2) for key, value in weights.items()}
        if factor_signal_count > 0:
            out.append(self._make("multi_factor", {"factor_weights": weights, "lookback": 60}, f"IC驱动多因子权重: {weights}", source="factor_ic", trigger_signal={"field": "factor_ic_weights", "value": weights}, trigger_thresholds=[self._threshold("factor_ic_weights", "derived_from", {"positive_ic": 0.0, "trend_preference": "rising"}, {"factor_ic": factor_ic, "factor_ic_trend": trend, "weights": weights}, "权重派生规则")]))
        return out

    def _from_volatility(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        volatility = snapshot.get("fg_components", {}).get("volatility", 50)
        if volatility < 35:
            out.append(self._make("ma_cross", {"short_period": 10, "long_period": 60}, f"波动率{volatility}，高波动长周期均线", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, volatility, "波动率阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 70, "lookback": 30}, f"波动率{volatility}，高波动宏观择时", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, volatility, "波动率阈值")]))
        elif volatility > 65:
            out.append(self._make("ma_cross", {"short_period": 3, "long_period": 15}, f"波动率{volatility}，低波动短周期均线", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", ">", 65, volatility, "波动率阈值")]))
        return out

    def _from_fund_flow(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        north_3d = snapshot.get("north_fund_3d_net", 0)
        margin_5d = snapshot.get("margin_5d_change_pct", 0)

        if north_3d > 5_000_000_000:
            out.append(self._make("growth_factor", {"lookback": self._jitter(40, 30, 60), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流入{north_3d / 1e8:.0f}亿，成长加速", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
            out.append(self._make("quality_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.8, "sell_quantile": 0.2}, f"北向3日净流入{north_3d / 1e8:.0f}亿，质量优选", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
        elif north_3d < -5_000_000_000:
            out.append(self._make("value_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，价值防御", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 60, "lookback": self._jitter(25, 15, 35)}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，宏观择时", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))

        if margin_5d > 2.0:
            out.append(self._make("momentum", {"lookback": self._jitter(5, 3, 10), "threshold": 0.01}, f"融资5日增速{margin_5d:.1f}%，短周期动量", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", ">", 2.0, margin_5d, "融资增速阈值")]))
        elif margin_5d < -2.0:
            out.append(self._make("rsi", {"rsi_period": self._jitter(6, 4, 10), "oversold": 20, "overbought": 80}, f"融资5日降速{abs(margin_5d):.1f}%，RSI超跌", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", "<", -2.0, margin_5d, "融资降速阈值")]))
        return out

    @classmethod
    def _coverage_fill_priority(cls, current_candidates: Optional[List[dict]]) -> List[str]:
        debt = cls._diversification_debt(current_candidates)
        preferred: List[str] = []

        def add(*types: str) -> None:
            for strategy_type in types:
                if strategy_type in CATEGORY_MINIMUMS and strategy_type not in preferred:
                    preferred.append(strategy_type)

        for item in debt:
            if item == "quality_defensive":
                add("quality_factor", "value_factor")
            elif item == "mean_reversion":
                add("gap_fill", "mean_reversion_short", "rsi")
            elif item == "flow_rotation":
                add("north_capital_track", "sector_rotation")
        return preferred

    def _fill_gaps(self, snapshot: dict, current_candidates: Optional[List[dict]] = None) -> List[dict]:
        current_candidates = list(current_candidates or [])
        current_counts = self._generated_type_counts(current_candidates)
        fill_budget = self._quota_fill_budget(snapshot, len(current_candidates))
        if fill_budget <= 0:
            return []
        parameter_registry = ParameterDistributionRegistry.from_snapshot(snapshot)

        preferred_types = list(
            dict.fromkeys(
                [
                    *self._coverage_fill_priority(current_candidates),
                    *self._preferred_fill_types(snapshot, current_counts),
                ]
            )
        )
        preferred_types = sorted(
            preferred_types,
            key=lambda strategy_type: (
                -int(parameter_registry.sample_count(strategy_type) or 0),
                preferred_types.index(strategy_type),
            ),
        )
        out: List[dict] = []
        fill_counts: Dict[str, int] = {}

        def maybe_add(strategy_type: str, preferred_rank: int) -> bool:
            if strategy_type == "momentum":
                return False
            current = int(current_counts.get(strategy_type) or 0) + int(fill_counts.get(strategy_type) or 0)
            desired_generated_count = 1 if preferred_rank > 2 else 2
            generation_cap = self._local_generation_cap(strategy_type)
            if generation_cap is not None:
                desired_generated_count = min(desired_generated_count, generation_cap)
                if current >= generation_cap:
                    return False
            if current >= desired_generated_count:
                return False
            existing_total = len(current_candidates) + len(out)
            existing_trend = self._trend_cluster_count(current_candidates) + self._trend_cluster_count(out)
            if strategy_type in self._TREND_CLUSTER_TYPES and existing_total > 0 and existing_trend / existing_total >= 0.5:
                return False
            projected_total = len(current_candidates) + len(out) + 1
            projected_trend = (
                self._trend_cluster_count(current_candidates)
                + self._trend_cluster_count(out)
                + (1 if strategy_type in self._TREND_CLUSTER_TYPES else 0)
            )
            if strategy_type in self._TREND_CLUSTER_TYPES and projected_total > 0 and projected_trend / projected_total > 0.5:
                return False
            slot_index = int(fill_counts.get(strategy_type) or 0) + 1
            params, parameter_source, parameter_sample_count = self._resolved_varied_defaults(
                strategy_type,
                slot_index - 1,
                snapshot=snapshot,
                registry=parameter_registry,
            )
            fill_source_mode = self._quota_fill_source_mode(
                strategy_type,
                snapshot=snapshot,
                current_candidates=current_candidates,
                parameter_source=parameter_source,
                parameter_sample_count=parameter_sample_count,
            )
            fill_quality_tier = self._quota_fill_quality_tier(fill_source_mode)
            quota_fill = {
                "strategy_type": strategy_type,
                "current_count": int(current_counts.get(strategy_type) or 0),
                "minimum_required": CATEGORY_MINIMUMS.get(strategy_type, 0),
                "desired_generated_count": desired_generated_count,
                "fill_budget": fill_budget,
                "preferred_rank": preferred_rank,
                "slot_index": slot_index,
                "parameter_source": parameter_source,
                "parameter_sample_count": parameter_sample_count,
                "fill_source_mode": fill_source_mode,
                "fill_quality_tier": fill_quality_tier,
            }
            candidate = self._make(
                strategy_type,
                params,
                f"{strategy_type}研究信号不足，按市场状态补位#{slot_index}",
                source="quota_fill",
                trigger_signal={
                    "field": f"generated_type_counts.{strategy_type}",
                    "value": int(current_counts.get(strategy_type) or 0),
                    "parameter_source": parameter_source,
                    "fill_source_mode": fill_source_mode,
                },
                trigger_thresholds=[
                    self._threshold(
                        f"generated_type_counts.{strategy_type}",
                        "<",
                        desired_generated_count,
                        int(current_counts.get(strategy_type) or 0),
                        "研究候选补位阈值",
                    )
                ],
                quota_fill=quota_fill,
                kind="quota_fill",
            )
            candidate["parameter_source"] = parameter_source
            candidate["parameter_sample_count"] = parameter_sample_count
            out.append(candidate)
            fill_counts[strategy_type] = slot_index
            return True

        for pass_index in range(2):
            for preferred_rank, strategy_type in enumerate(preferred_types, 1):
                if len(out) >= fill_budget:
                    break
                if pass_index == 0 and int(current_counts.get(strategy_type) or 0) > 0:
                    continue
                maybe_add(strategy_type, preferred_rank)
            if len(out) >= fill_budget:
                break

        return out[:fill_budget]

    @staticmethod
    def _jitter(base: int, lo: int, hi: int) -> int:
        delta = max(1, int(base * 0.2))
        return max(lo, min(hi, base + random.randint(-delta, delta)))

    @staticmethod
    def _jitter_f(base: float, lo: float, hi: float) -> float:
        delta = max(0.01, base * 0.15)
        return round(max(lo, min(hi, base + random.uniform(-delta, delta))), 2)

    @staticmethod
    def _snapshot_regime_inputs(snapshot: Optional[dict] = None) -> dict[str, float]:
        payload = dict(snapshot or {})
        return {
            "fear_greed": StrategySpawner._safe_float(payload.get("fear_greed_index") or 50.0),
            "volatility": StrategySpawner._safe_float(dict(payload.get("fg_components") or {}).get("volatility") or 50.0),
            "north_3d": StrategySpawner._safe_float(payload.get("north_fund_3d_net") or 0.0),
            "margin_5d": StrategySpawner._safe_float(payload.get("margin_5d_change_pct") or 0.0),
        }

    def _legacy_varied_defaults(self, strategy_type: str, idx: int, snapshot: Optional[dict] = None) -> dict:
        regime = self._snapshot_regime_inputs(snapshot)
        fear_greed = regime["fear_greed"]
        volatility = regime["volatility"]
        north_3d = regime["north_3d"]
        margin_5d = regime["margin_5d"]

        if strategy_type == "momentum":
            if fear_greed >= 68 and north_3d > 0 and margin_5d > 0:
                lookbacks = [5, 10, 20]
                threshold_base = 0.016
            elif fear_greed <= 42 or north_3d < 0 or volatility >= 65:
                lookbacks = [20, 30, 45]
                threshold_base = 0.028
            else:
                lookbacks = [10, 20, 30]
                threshold_base = 0.022
            lookback = lookbacks[idx % len(lookbacks)]
            return {
                "lookback": self._jitter(lookback, 5, 50),
                "threshold": self._jitter_f(threshold_base, 0.008, 0.05),
            }
        if strategy_type == "ma_cross":
            if volatility >= 65 or fear_greed <= 45:
                pairs = [(8, 34), (10, 55), (13, 89)]
            elif fear_greed >= 68 and north_3d > 0:
                pairs = [(5, 21), (8, 34), (13, 55)]
            else:
                pairs = [(5, 20), (8, 34), (13, 55)]
            short_period, long_period = pairs[idx % len(pairs)]
            short_period = self._jitter(short_period, 3, 15)
            long_period = self._jitter(long_period, max(short_period + 8, 18), 120)
            return {"short_period": short_period, "long_period": long_period}
        if strategy_type == "rsi":
            if fear_greed <= 40 or north_3d < 0:
                periods = [6, 10, 14]
                oversold_base = 22
                overbought_base = 76
            else:
                periods = [10, 14, 21]
                oversold_base = 24
                overbought_base = 72
            period = periods[idx % len(periods)]
            return {
                "rsi_period": self._jitter(period, 4, 28),
                "oversold": self._jitter(oversold_base, 18, 34),
                "overbought": self._jitter(overbought_base, 64, 82),
            }
        if strategy_type == "volatility_breakout":
            lookbacks = [8, 13, 21] if volatility >= 60 else [10, 15, 20]
            lookback = lookbacks[idx % len(lookbacks)]
            threshold_base = 0.03 if volatility >= 60 else 0.025
            return {"lookback": self._jitter(lookback, 5, 30), "threshold": self._jitter_f(threshold_base, 0.01, 0.06)}
        if strategy_type == "gap_fill":
            oversold_base = 22 if fear_greed <= 45 else 20
            overbought_base = 66 if volatility >= 60 else 62
            return {
                "rsi_period": self._jitter(5 if fear_greed <= 45 else 7, 3, 12),
                "oversold": self._jitter(oversold_base, 16, 30),
                "overbought": self._jitter(overbought_base, 56, 74),
            }
        if strategy_type == "mean_reversion_short":
            oversold_base = 20 if fear_greed <= 38 or north_3d < 0 else 18
            overbought_base = 76 if volatility >= 55 else 72
            base_period = 8 if fear_greed <= 38 or volatility <= 40 else 10
            return {
                "rsi_period": self._jitter(base_period, 4, 14),
                "oversold": self._jitter(oversold_base, 16, 26),
                "overbought": self._jitter(overbought_base, 68, 82),
            }
        if strategy_type == "value_factor":
            lookback_base = 72 if north_3d < 0 or fear_greed <= 45 else 60
            return {
                "lookback": self._jitter(lookback_base, 30, 100),
                "buy_quantile": self._jitter_f(0.82, 0.72, 0.9),
                "sell_quantile": self._jitter_f(0.18, 0.1, 0.28),
            }
        if strategy_type == "quality_factor":
            lookback_base = 72 if volatility >= 60 or north_3d < 0 else 60
            return {
                "lookback": self._jitter(lookback_base, 30, 100),
                "buy_quantile": self._jitter_f(0.8, 0.72, 0.9),
                "sell_quantile": self._jitter_f(0.2, 0.1, 0.28),
            }
        if strategy_type == "growth_factor":
            lookback_base = 36 if north_3d > 0 and fear_greed >= 60 else 48
            return {
                "lookback": self._jitter(lookback_base, 25, 80),
                "buy_quantile": self._jitter_f(0.82, 0.72, 0.92),
                "sell_quantile": self._jitter_f(0.18, 0.08, 0.28),
            }
        if strategy_type == "multi_factor":
            weights = {
                "value": random.uniform(0.2, 0.5),
                "quality": random.uniform(0.2, 0.5),
                "growth": random.uniform(0.2, 0.5),
            }
            total = sum(weights.values())
            weights = {key: round(value / total, 2) for key, value in weights.items()}
            lookback_base = 72 if north_3d < 0 else 60
            return {"factor_weights": weights, "lookback": self._jitter(lookback_base, 30, 100)}
        if strategy_type == "macro_timing":
            return {
                "fear_threshold": self._jitter(35 if north_3d < 0 else 32, 24, 45),
                "greed_threshold": self._jitter(68 if north_3d > 0 else 64, 55, 78),
                "lookback": self._jitter(24 if volatility >= 60 else 20, 10, 40),
            }
        if strategy_type == "sector_rotation":
            weights = {"momentum": 0.45, "quality": 0.3, "value": 0.25}
            return {"factor_weights": weights, "lookback": self._jitter(24 if volatility >= 60 else 20, 10, 45)}
        if strategy_type == "north_capital_track":
            threshold_base = 0.012 if north_3d > 0 else 0.018
            return {"lookback": self._jitter(15, 5, 30), "threshold": self._jitter_f(threshold_base, 0.005, 0.04)}
        if strategy_type == "margin_divergence":
            return {
                "fear_threshold": self._jitter(42 if margin_5d < 0 else 38, 30, 50),
                "greed_threshold": self._jitter(62 if margin_5d > 0 else 58, 50, 72),
                "lookback": self._jitter(15, 8, 28),
            }
        return {}

    def _resolved_varied_defaults(
        self,
        strategy_type: str,
        idx: int,
        *,
        snapshot: Optional[dict] = None,
        registry: Optional[ParameterDistributionRegistry] = None,
    ) -> tuple[dict, str, int]:
        parameter_registry = registry or ParameterDistributionRegistry.from_snapshot(snapshot)
        sampled = parameter_registry.sample(strategy_type, idx)
        if sampled:
            return (
                dict(sampled.get("params") or {}),
                str(sampled.get("source") or "historical_distribution"),
                int(sampled.get("sample_count") or 0),
            )
        return self._legacy_varied_defaults(strategy_type, idx, snapshot=snapshot), "fixed_defaults", 0

    def _varied_defaults(self, strategy_type: str, idx: int, snapshot: Optional[dict] = None) -> dict:
        params, _, _ = self._resolved_varied_defaults(strategy_type, idx, snapshot=snapshot)
        return params

    def _quota_fill_source_mode(
        self,
        strategy_type: str,
        *,
        snapshot: Optional[dict] = None,
        current_candidates: Optional[list[dict]] = None,
        parameter_source: str,
        parameter_sample_count: int,
    ) -> str:
        if parameter_source == "historical_distribution" and parameter_sample_count >= 3:
            return "historical_guided"
        if current_candidates:
            return "signal_aligned"
        return "no_signal_fallback"

    @staticmethod
    def _quota_fill_quality_tier(fill_source_mode: str) -> str:
        if fill_source_mode == "historical_guided":
            return "oos_validated_history"
        if fill_source_mode == "signal_aligned":
            return "market_signal_aligned"
        return "fallback_only"


    @staticmethod
    def _make(
        strategy_type: str,
        params: dict,
        reason: str = "",
        *,
        source: str = "unknown",
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        generation_reason = StrategySpawner._build_generation_reason(
            source=source,
            reason=reason,
            trigger_signal=trigger_signal,
            trigger_thresholds=trigger_thresholds,
            quota_fill=quota_fill,
            kind=kind,
        )
        return {
            "strategy_type": strategy_type,
            "params": params,
            "spawn_reason": reason,
            "generation_reason": generation_reason,
            "trigger_signal": generation_reason["trigger_signal"],
            "trigger_thresholds": generation_reason["trigger_thresholds"],
            "quota_fill": quota_fill,
        }
