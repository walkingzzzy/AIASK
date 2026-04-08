"""Bulk stock-strategy matrix planning for P0 factory expansion."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Dict, List

from ..domain.constants import (
    STOCK_STRATEGY_MATRIX_ENABLED,
    STOCK_STRATEGY_MATRIX_BATCH_SIZE,
    STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
    STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
    STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
    preferred_strategy_types_for_factor,
)
from ._opportunity_utils import _MarketOpportunityScannerUtilityMixin
from ._stock_universe_loader import load_stock_universe_rows
from .research_plane_contract import build_task_artifact


class StockStrategyMatrixPlanner(_MarketOpportunityScannerUtilityMixin):
    """Plan per-stock strategy-family tasks for bulk autonomy generation."""

    _MIN_HISTORY_BARS = 100
    _HISTORY_COUNT_CHUNK_SIZE = 400

    def __init__(self) -> None:
        self.last_report: dict[str, Any] = {
            "summary": {
                "enabled": bool(STOCK_STRATEGY_MATRIX_ENABLED),
                "task_count": 0,
                "stock_count": 0,
                "eligible_stock_count": 0,
                "loaded_stock_count": 0,
                "pages_loaded": 0,
                "analysis_complete": False,
                "analysis_stock_coverage_ratio": 0.0,
                "family_counts": {},
                "planned_family_counts": {},
                "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                "requested_universe_offset": 0,
                "effective_universe_offset": 0,
                "universe_offset_fallback": False,
                "next_universe_offset": 0,
                "cursor_wrapped": False,
                "cursor_mode": "task_offset",
                "requested_task_offset": 0,
                "effective_task_offset": 0,
                "task_offset_fallback": False,
                "next_task_offset": 0,
                "task_cursor_wrapped": False,
                "max_tasks_per_run": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
                "max_candidates_per_run": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
                "generation_limit_per_task": STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
                "effective_task_budget": 0,
                "estimated_candidate_count": 0,
                "planned_task_count": 0,
                "planned_candidate_count": 0,
                "batch_size": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
                "batch_count": 0,
                "selected_batch_count": 0,
                "batch_task_counts": {},
                "tasks_per_shard": STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
                "shard_count": 0,
                "selected_shard_count": 0,
                "selected_shard_ids": [],
                "stock_coverage_ratio": 0.0,
                "allocation_mode": "stock_round_robin_by_family_rank",
                "allocation_pass_counts": {},
                "planned_allocation_pass_counts": {},
                "overflow_task_count": 0,
                "stock_family_allocation_count": 0,
                "stock_family_allocation_applied_count": 0,
                "stock_family_allocation_coverage_ratio": 0.0,
                "min_history_bars": self._MIN_HISTORY_BARS,
                "history_prefilter_applied": False,
                "insufficient_history_filtered_count": 0,
            },
            "tasks": [],
        }

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    @staticmethod
    def _normalize_factor_names(snapshot: dict[str, Any]) -> list[str]:
        factor_research = dict(snapshot.get("factor_research") or {})
        summary = dict(factor_research.get("summary") or {})
        names = [
            str(item).strip()
            for item in list(
                factor_research.get("active_factors")
                or summary.get("active_factors")
                or summary.get("top_factor_names")
                or []
            )
            if str(item).strip()
        ]
        return list(dict.fromkeys(names))[:6]

    @classmethod
    def _default_validation_profile_for_family(
        cls,
        family: str,
        *,
        validation_focus: str = "candidate_target_only",
    ) -> dict[str, Any]:
        normalized_family = str(family or "").strip().lower()
        normalized_focus = str(validation_focus or "candidate_target_only").strip().lower() or "candidate_target_only"
        if normalized_family == "macro_timing":
            profile = "macro_regime_validation"
        elif normalized_focus == "event_target_only" or normalized_family in {"north_capital_track", "margin_divergence"}:
            profile = "event_trade_validation"
            normalized_focus = "event_target_only"
        elif normalized_family in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sentiment", "sentiment_factor"}:
            profile = "factor_rank_validation"
        else:
            profile = "trade_rule_validation"
        return {
            "profile": profile,
            "validation_focus": normalized_focus,
            "primary_validation_layer": "target" if normalized_focus in {"candidate_target_only", "event_target_only"} else "combined",
        }

    @classmethod
    def _normalize_validation_profile(
        cls,
        family: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = dict(payload or {})
        default_profile = cls._default_validation_profile_for_family(
            family,
            validation_focus=str(profile.get("validation_focus") or "candidate_target_only"),
        )
        normalized_profile = str(profile.get("profile") or default_profile.get("profile") or "").strip().lower()
        validation_focus = str(
            profile.get("validation_focus")
            or default_profile.get("validation_focus")
            or "candidate_target_only"
        ).strip().lower() or "candidate_target_only"
        if not normalized_profile:
            normalized_profile = str(
                cls._default_validation_profile_for_family(
                    family,
                    validation_focus=validation_focus,
                ).get("profile")
                or "trade_rule_validation"
            )
        primary_layer = str(
            profile.get("primary_validation_layer")
            or default_profile.get("primary_validation_layer")
            or ("target" if validation_focus in {"candidate_target_only", "event_target_only"} else "combined")
        ).strip().lower() or "target"
        return {
            "profile": normalized_profile,
            "validation_focus": validation_focus,
            "primary_validation_layer": primary_layer,
        }

    @staticmethod
    def _default_failure_penalty_for_family(family: str, *, family_rank: int) -> float:
        normalized_family = str(family or "").strip().lower()
        if normalized_family in {"momentum", "growth_factor", "volatility_breakout", "gap_fill"}:
            base_penalty = 0.22
        elif normalized_family in {"quality_factor", "value_factor"}:
            base_penalty = 0.08
        else:
            base_penalty = 0.14
        return round(min(base_penalty + max(family_rank - 1, 0) * 0.03, 0.45), 4)

    @classmethod
    def _default_family_plans(
        cls,
        families: list[str],
        *,
        priority: float,
    ) -> list[dict[str, Any]]:
        selected = [
            str(item or "").strip().lower()
            for item in list(families or [])
            if str(item or "").strip()
        ][: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]
        if not selected:
            return []
        raw_weights: list[float] = []
        for family_rank, _family in enumerate(selected, 1):
            rank_multiplier = max(0.4, 1.0 - (family_rank - 1) * 0.2)
            raw_weights.append(max(0.05, max(priority, 0.35) * rank_multiplier))
        total = sum(raw_weights) or float(len(selected))
        plans: list[dict[str, Any]] = []
        allocated = 0.0
        for family_rank, family in enumerate(selected, 1):
            if family_rank == len(selected):
                budget_weight = round(max(0.0, 1.0 - allocated), 4)
            else:
                budget_weight = round(raw_weights[family_rank - 1] / total, 4)
                allocated += budget_weight
            plans.append(
                {
                    "family": family,
                    "family_rank": family_rank,
                    "budget": budget_weight,
                    "budget_weight": budget_weight,
                    "failure_penalty": cls._default_failure_penalty_for_family(family, family_rank=family_rank),
                    "validation_profile": cls._normalize_validation_profile(family),
                }
            )
        return plans

    @classmethod
    def _normalize_stock_family_allocation(cls, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        factor_research = dict(snapshot.get("factor_research") or {})
        allocation = dict(factor_research.get("stock_family_allocation") or {})
        normalized: dict[str, dict[str, Any]] = {}
        for code, item in allocation.items():
            normalized_code = str(code or "").strip()
            payload = dict(item or {})
            priority = max(0.0, min(cls._safe_float(payload.get("priority")), 1.0))
            families = [
                str(family or "").strip().lower()
                for family in list(payload.get("families") or [])
                if str(family or "").strip()
            ]
            normalized_family_plans: list[dict[str, Any]] = []
            for index, raw_plan in enumerate(list(payload.get("family_plans") or []), 1):
                plan_payload = dict(raw_plan or {})
                family = str(plan_payload.get("family") or "").strip().lower()
                if not family:
                    continue
                family_rank = max(1, cls._safe_int(plan_payload.get("family_rank")) or index)
                normalized_family_plans.append(
                    {
                        "family": family,
                        "family_rank": family_rank,
                        "budget": max(
                            0.0,
                            min(
                                cls._safe_float(plan_payload.get("budget") or plan_payload.get("budget_weight")),
                                1.0,
                            ),
                        ),
                        "budget_weight": max(
                            0.0,
                            min(
                                cls._safe_float(plan_payload.get("budget_weight") or plan_payload.get("budget")),
                                1.0,
                            ),
                        ),
                        "failure_penalty": max(
                            0.0,
                            min(
                                cls._safe_float(plan_payload.get("failure_penalty")),
                                1.0,
                            ),
                        ),
                        "validation_profile": cls._normalize_validation_profile(
                            family,
                            dict(plan_payload.get("validation_profile") or {}),
                        ),
                    }
                )
            normalized_family_plans.sort(
                key=lambda plan: (
                    int(plan.get("family_rank") or 0),
                    str(plan.get("family") or ""),
                )
            )
            if normalized_family_plans:
                families = [
                    str(plan.get("family") or "").strip().lower()
                    for plan in normalized_family_plans
                    if str(plan.get("family") or "").strip()
                ]
            if not normalized_code or not families:
                continue
            default_family_plans = cls._default_family_plans(families, priority=priority or 0.5)
            default_plan_lookup = {
                str(plan.get("family") or "").strip().lower(): dict(plan or {})
                for plan in default_family_plans
                if str(plan.get("family") or "").strip()
            }
            if not normalized_family_plans:
                normalized_family_plans = default_family_plans
            else:
                resolved_plans: list[dict[str, Any]] = []
                seen_families: set[str] = set()
                for plan in normalized_family_plans:
                    family = str(plan.get("family") or "").strip().lower()
                    if not family or family in seen_families:
                        continue
                    seen_families.add(family)
                    fallback = dict(default_plan_lookup.get(family) or {})
                    budget_weight = cls._safe_float(plan.get("budget_weight") or plan.get("budget"))
                    if budget_weight <= 0.0:
                        budget_weight = cls._safe_float(fallback.get("budget_weight") or fallback.get("budget"))
                    failure_penalty = cls._safe_float(plan.get("failure_penalty"))
                    if failure_penalty <= 0.0:
                        failure_penalty = cls._safe_float(fallback.get("failure_penalty"))
                    resolved_plans.append(
                        {
                            "family": family,
                            "family_rank": max(1, cls._safe_int(plan.get("family_rank")) or len(resolved_plans) + 1),
                            "budget": max(0.0, min(budget_weight, 1.0)),
                            "budget_weight": max(0.0, min(budget_weight, 1.0)),
                            "failure_penalty": max(0.0, min(failure_penalty, 1.0)),
                            "validation_profile": cls._normalize_validation_profile(
                                family,
                                dict(plan.get("validation_profile") or fallback.get("validation_profile") or {}),
                            ),
                        }
                    )
                normalized_family_plans = resolved_plans
            normalized_family_plans = normalized_family_plans[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]
            families = [
                str(plan.get("family") or "").strip().lower()
                for plan in normalized_family_plans
                if str(plan.get("family") or "").strip()
            ]
            normalized[normalized_code] = {
                "families": list(dict.fromkeys(families))[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)],
                "family_plans": normalized_family_plans,
                "priority": priority,
                "source_mode": str(payload.get("source_mode") or "").strip() or None,
            }
            industry = str(payload.get("industry") or "").strip()
            if industry:
                normalized[normalized_code]["industry"] = industry
            if normalized_family_plans:
                normalized[normalized_code]["top_family"] = normalized_family_plans[0]["family"]
                normalized[normalized_code]["top_validation_profile"] = (
                    dict(normalized_family_plans[0].get("validation_profile") or {}).get("profile")
                )
        return normalized

    @classmethod
    def _base_family_order(cls, snapshot: dict[str, Any]) -> list[str]:
        fg = cls._safe_float(snapshot.get("fear_greed_index") or 50.0)
        if fg >= 60:
            return ["momentum", "growth_factor", "ma_cross", "quality_factor"]
        if fg <= 40:
            return ["rsi", "value_factor", "quality_factor", "ma_cross"]
        return ["ma_cross", "quality_factor", "multi_factor", "value_factor"]

    @classmethod
    def _row_priority_score(
        cls,
        row: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
        allocation_item: dict[str, Any] | None = None,
    ) -> float:
        market_cap = cls._safe_float(row.get("market_cap"))
        industry = str(row.get("industry") or row.get("sector") or "").strip()
        score = 30.0
        if market_cap > 0:
            score += min(math.log10(market_cap / 1e8 + 1.0) * 8.0, 20.0)
        if industry and industry in hot_sectors:
            score += 10.0
        if industry and industry in cold_sectors:
            score -= 4.0
        pe_ratio = cls._safe_float(row.get("pe_ratio"))
        pb_ratio = cls._safe_float(row.get("pb_ratio"))
        if "value" in active_factors or "reversal" in active_factors:
            if 0 < pe_ratio <= 18:
                score += 6.0
            if 0 < pb_ratio <= 1.8:
                score += 4.0
        if "growth" in active_factors and industry in hot_sectors:
            score += 4.0
        if "quality" in active_factors and market_cap >= 30_000_000_000:
            score += 3.0
        if allocation_item:
            allocation_priority = max(0.0, min(cls._safe_float(allocation_item.get("priority")), 1.0))
            if allocation_priority > 0.0:
                score = score * 0.55 + allocation_priority * 45.0
        return round(score, 4)

    @classmethod
    def _families_for_row(
        cls,
        row: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
        allocation_item: dict[str, Any] | None = None,
    ) -> list[str]:
        families: list[str] = []
        industry = str(row.get("industry") or row.get("sector") or "").strip()
        pe_ratio = cls._safe_float(row.get("pe_ratio"))
        pb_ratio = cls._safe_float(row.get("pb_ratio"))

        def add(*items: str) -> None:
            for item in items:
                lowered = str(item or "").strip().lower()
                if lowered and lowered not in families:
                    families.append(lowered)

        if allocation_item:
            allocation_families = [
                str(plan.get("family") or "").strip().lower()
                for plan in list(allocation_item.get("family_plans") or [])
                if str(plan.get("family") or "").strip()
            ]
            if not allocation_families:
                allocation_families = [
                    str(item or "").strip().lower()
                    for item in list(allocation_item.get("families") or [])
                    if str(item or "").strip()
                ]
            if allocation_families:
                add(*allocation_families)
                return families[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]
        if industry and industry in hot_sectors:
            add("momentum", "growth_factor")
        if industry and industry in cold_sectors:
            add("rsi", "value_factor", "quality_factor")
        if 0 < pe_ratio <= 18 or 0 < pb_ratio <= 1.8:
            add("value_factor", "quality_factor")
        add(*cls._base_family_order(snapshot))
        for factor_name in active_factors:
            add(*preferred_strategy_types_for_factor(factor_name, default=[]))

        return families[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]

    @classmethod
    def _family_plans_for_row(
        cls,
        row: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
        allocation_item: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        allocation_plans = [
            dict(plan or {})
            for plan in list((allocation_item or {}).get("family_plans") or [])
            if isinstance(plan, dict)
        ]
        if allocation_plans:
            normalized_plans: list[dict[str, Any]] = []
            for index, plan in enumerate(allocation_plans, 1):
                family = str(plan.get("family") or "").strip().lower()
                if not family:
                    continue
                family_rank = max(1, cls._safe_int(plan.get("family_rank")) or index)
                normalized_plans.append(
                    {
                        "family": family,
                        "family_rank": family_rank,
                        "budget": max(
                            0.0,
                            min(
                                cls._safe_float(plan.get("budget") or plan.get("budget_weight")),
                                1.0,
                            ),
                        ),
                        "budget_weight": max(
                            0.0,
                            min(
                                cls._safe_float(plan.get("budget_weight") or plan.get("budget")),
                                1.0,
                            ),
                        ),
                        "failure_penalty": max(
                            0.0,
                            min(
                                cls._safe_float(plan.get("failure_penalty")),
                                1.0,
                            ),
                        ),
                        "validation_profile": cls._normalize_validation_profile(
                            family,
                            dict(plan.get("validation_profile") or {}),
                        ),
                    }
                )
            normalized_plans.sort(
                key=lambda plan: (
                    int(plan.get("family_rank") or 0),
                    str(plan.get("family") or ""),
                )
            )
            if normalized_plans:
                return normalized_plans[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]

        families = cls._families_for_row(
            row,
            snapshot=snapshot,
            hot_sectors=hot_sectors,
            cold_sectors=cold_sectors,
            active_factors=active_factors,
            allocation_item=allocation_item,
        )
        return cls._default_family_plans(
            families,
            priority=max(0.0, min(cls._safe_float((allocation_item or {}).get("priority")), 1.0)),
        )

    @staticmethod
    def _holding_bucket_for_family(family: str) -> str:
        if family in {"momentum", "rsi"}:
            return "short"
        if family in {"value_factor"}:
            return "long"
        return "medium"

    @staticmethod
    def _alpha_source_for_family(family: str) -> str:
        if family in {"momentum", "ma_cross", "rsi"}:
            return "technical"
        if family in {"value_factor", "quality_factor", "growth_factor"}:
            return "fundamental"
        if family == "macro_timing":
            return "macro"
        return "multi_factor"

    @staticmethod
    def _risk_level_for_family(family: str) -> str:
        if family in {"momentum", "growth_factor"}:
            return "high"
        if family in {"quality_factor"}:
            return "low"
        return "medium"

    @staticmethod
    def _effective_generation_limit() -> int:
        candidate_budget = max(1, int(STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN))
        return max(1, min(int(STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK), candidate_budget))

    @classmethod
    def _effective_task_budget(cls) -> int:
        generation_limit = cls._effective_generation_limit()
        candidate_budget = max(1, int(STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN))
        candidate_limited_budget = max(1, candidate_budget // generation_limit)
        return max(1, min(int(STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN), candidate_limited_budget))

    @classmethod
    async def _fetch_history_bar_counts(
        cls,
        db,
        codes: Sequence[str],
        *,
        min_history_bars: int,
    ) -> tuple[dict[str, int], bool]:
        normalized_codes = [
            str(code or "").strip()
            for code in list(codes or [])
            if str(code or "").strip()
        ]
        if not normalized_codes:
            return {}, False

        deduped_codes = list(dict.fromkeys(normalized_codes))
        acquire = getattr(db, "acquire", None)
        if callable(acquire):
            history_counts: dict[str, int] = {}
            try:
                async with db.acquire() as conn:
                    for start in range(0, len(deduped_codes), cls._HISTORY_COUNT_CHUNK_SIZE):
                        chunk = deduped_codes[start : start + cls._HISTORY_COUNT_CHUNK_SIZE]
                        rows = await conn.fetch(
                            """
                            SELECT code, COUNT(*) AS bar_count
                            FROM kline_1d
                            WHERE code = ANY($1::text[])
                            GROUP BY code
                            """,
                            chunk,
                        )
                        for row in rows or []:
                            payload = dict(row or {})
                            code = str(payload.get("code") or "").strip()
                            if not code:
                                continue
                            history_counts[code] = max(0, int(payload.get("bar_count") or 0))
                return history_counts, True
            except Exception:
                pass

        get_klines = getattr(db, "get_klines", None)
        if not callable(get_klines) or len(deduped_codes) > 256:
            return {}, False

        history_counts = {}
        query_limit = max(int(min_history_bars or 0), cls._MIN_HISTORY_BARS)
        for code in deduped_codes:
            try:
                klines = await get_klines(code, limit=query_limit)
            except Exception:
                history_counts[code] = 0
                continue
            history_counts[code] = len(list(klines or []))
        return history_counts, True

    @staticmethod
    def _resolve_task_cursor(
        *,
        planned_task_count: int,
        requested_task_offset: int,
        effective_task_budget: int,
    ) -> tuple[int, int, bool, bool]:
        if planned_task_count <= 0:
            return 0, 0, False, False

        requested = max(0, int(requested_task_offset or 0))
        effective_offset = requested
        task_offset_fallback = False
        if effective_offset >= planned_task_count:
            effective_offset = effective_offset % planned_task_count
            task_offset_fallback = requested > 0

        actual_budget = max(1, min(int(effective_task_budget or 1), planned_task_count))
        next_task_offset = (effective_offset + actual_budget) % planned_task_count
        cursor_wrapped = bool(task_offset_fallback or effective_offset + actual_budget >= planned_task_count)
        return effective_offset, next_task_offset, cursor_wrapped, task_offset_fallback

    @staticmethod
    def _task_target_code(task: dict[str, Any]) -> str:
        return str(((task or {}).get("target_symbols") or [None])[0] or "").strip()

    @classmethod
    def _pop_family_interleaved_task(
        cls,
        bucket: list[dict[str, Any]],
        *,
        used_codes: set[str],
    ) -> dict[str, Any] | None:
        if not bucket:
            return None
        scan_limit = min(len(bucket), max(6, len(used_codes) + 2))
        for index in range(scan_limit):
            code = cls._task_target_code(bucket[index] or {})
            if not code or code not in used_codes:
                return bucket.pop(index)
        return bucket.pop(0)

    @classmethod
    def _interleave_tasks_by_family(
        cls,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(tasks) <= 1:
            return [dict(item or {}) for item in tasks]

        family_buckets: dict[str, list[dict[str, Any]]] = {}
        for item in tasks:
            task = dict(item or {})
            family = str(task.get("candidate_family") or "").strip().lower() or "unknown"
            family_buckets.setdefault(family, []).append(task)

        family_order = sorted(
            family_buckets.keys(),
            key=lambda family: (
                int((family_buckets[family][0] or {}).get("matrix_family_rank") or 0),
                int((family_buckets[family][0] or {}).get("matrix_stock_rank") or 0),
                family,
            ),
        )

        interleaved: list[dict[str, Any]] = []
        remaining = sum(len(bucket) for bucket in family_buckets.values())
        while remaining > 0:
            used_codes: set[str] = set()
            wave_progress = False
            for family in family_order:
                bucket = family_buckets.get(family) or []
                task = cls._pop_family_interleaved_task(bucket, used_codes=used_codes)
                if task is None:
                    continue
                interleaved.append(task)
                remaining -= 1
                wave_progress = True
                code = cls._task_target_code(task)
                if code:
                    used_codes.add(code)
            if not wave_progress:
                break

        if remaining > 0:
            for family in family_order:
                bucket = family_buckets.get(family) or []
                while bucket:
                    interleaved.append(bucket.pop(0))
        return interleaved

    @classmethod
    def _build_task(
        cls,
        row: dict[str, Any],
        *,
        family: str,
        rank: int,
        stock_rank: int,
        priority_score: float,
        snapshot: dict[str, Any],
        generation_limit: int,
        family_plan: dict[str, Any] | None = None,
        allocation_item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or code).strip() or code
        holding_bucket = cls._holding_bucket_for_family(family)
        alpha_source = cls._alpha_source_for_family(family)
        risk_level = cls._risk_level_for_family(family)
        resolved_family_plan = dict(family_plan or {})
        resolved_rank = max(1, int(resolved_family_plan.get("family_rank") or rank))
        validation_profile = cls._normalize_validation_profile(
            family,
            dict(resolved_family_plan.get("validation_profile") or {}),
        )
        budget_weight = max(
            0.0,
            min(
                cls._safe_float(resolved_family_plan.get("budget_weight") or resolved_family_plan.get("budget")),
                1.0,
            ),
        )
        failure_penalty = max(
            0.0,
            min(
                cls._safe_float(resolved_family_plan.get("failure_penalty"))
                or cls._default_failure_penalty_for_family(family, family_rank=resolved_rank),
                1.0,
            ),
        )
        priority = max(45, min(98, int(round(priority_score - (resolved_rank - 1) * 1.5))))
        task = {
            "task_id": f"bulk_matrix_{snapshot.get('date')}_{code}_{family}",
            "task_key": f"bulk_matrix:{snapshot.get('date')}:{code}:{family}",
            "task_source": "bulk_stock_matrix",
            "theme": f"stock_strategy_matrix_{family}",
            "title": f"逐股策略矩阵·{name}·{family}",
            "opportunity_type": "stock_strategy_matrix",
            "rationale": f"为 {name}({code}) 生成 {family} 家族候选，优先验证单股可执行策略。",
            "preferred_strategy_types": [family],
            "allowed_strategy_types": [family],
            "strategy_preferences": [family],
            "candidate_family": family,
            "candidate_family_id": f"{code}_{family}_{holding_bucket}",
            "holding_period_bucket": holding_bucket,
            "alpha_source": alpha_source,
            "risk_level": risk_level,
            "regime_fit": "trend_expansion" if family in {"momentum", "growth_factor"} else ("mean_reversion" if family in {"rsi", "value_factor"} else "rotation_balanced"),
            "direction_bias": "long_only",
            "generator_mode": "bulk_stock_matrix",
            "target_symbol_policy": "strict_intersection",
            "universe_expansion_policy": "forbid",
            "preference_strength": "hard",
            "preference_reason": f"stock_matrix:{code}:{family}",
            "validation_focus": str(validation_profile.get("validation_focus") or "candidate_target_only"),
            "validation_profile": validation_profile,
            "target_symbols": [code],
            "stock_pool": {"selection_mode": "explicit", "symbols": [code]},
            "focus_industries": [str(row.get("industry") or row.get("sector") or "").strip()] if str(row.get("industry") or row.get("sector") or "").strip() else [],
            "priority": priority,
            "generation_limit": generation_limit,
            "matrix_rank": resolved_rank,
            "matrix_stock_rank": stock_rank,
            "matrix_family_rank": resolved_rank,
            "matrix_priority_score": priority_score,
            "stock_family_budget": budget_weight,
            "stock_family_budget_weight": budget_weight,
            "stock_family_failure_penalty": failure_penalty,
            "source_symbol_summary": cls._summarize_symbol(row),
            "source_snapshot": {
                "fear_greed_index": cls._safe_float(snapshot.get("fear_greed_index") or 50.0),
                "fg_level": snapshot.get("fg_level"),
            },
        }
        if allocation_item:
            task["stock_family_priority"] = max(0.0, min(cls._safe_float(allocation_item.get("priority")), 1.0))
            task["stock_family_allocation_source"] = allocation_item.get("source_mode") or "factor_research_stock_family_allocation"
        return cls._finalize_task(task)

    async def plan(self, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not STOCK_STRATEGY_MATRIX_ENABLED:
            task_artifact = build_task_artifact()
            self.last_report = {
                "summary": {
                    "enabled": False,
                    "task_count": 0,
                    "stock_count": 0,
                    "eligible_stock_count": 0,
                    "loaded_stock_count": 0,
                    "pages_loaded": 0,
                    "analysis_complete": False,
                    "analysis_stock_coverage_ratio": 0.0,
                    "family_counts": {},
                    "planned_family_counts": {},
                    "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                    "requested_universe_offset": 0,
                    "effective_universe_offset": 0,
                    "universe_offset_fallback": False,
                    "next_universe_offset": 0,
                    "cursor_wrapped": False,
                    "cursor_mode": "task_offset",
                    "requested_task_offset": 0,
                    "effective_task_offset": 0,
                    "task_offset_fallback": False,
                    "next_task_offset": 0,
                    "task_cursor_wrapped": False,
                    "max_tasks_per_run": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
                    "max_candidates_per_run": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
                    "generation_limit_per_task": STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
                    "effective_task_budget": 0,
                    "estimated_candidate_count": 0,
                    "planned_task_count": 0,
                    "planned_candidate_count": 0,
                    "batch_size": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
                    "batch_count": 0,
                    "selected_batch_count": 0,
                    "batch_task_counts": {},
                    "tasks_per_shard": STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
                    "shard_count": 0,
                    "selected_shard_count": 0,
                    "selected_shard_ids": [],
                    "stock_coverage_ratio": 0.0,
                    "allocation_mode": "stock_round_robin_by_family_rank",
                    "allocation_pass_counts": {},
                    "planned_allocation_pass_counts": {},
                    "overflow_task_count": 0,
                    "stock_family_allocation_count": 0,
                    "stock_family_allocation_applied_count": 0,
                    "stock_family_allocation_coverage_ratio": 0.0,
                    "min_history_bars": self._MIN_HISTORY_BARS,
                    "history_prefilter_applied": False,
                    "insufficient_history_filtered_count": 0,
                    "task_artifact_contract_version": task_artifact.get("contract_version"),
                    "task_artifact_available": bool(task_artifact.get("available")),
                },
                "tasks": [],
                "task_artifact": task_artifact,
            }
            return self.last_report

        universe_page_size = max(100, min(int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT), 1000))
        try:
            rows, universe_meta = await load_stock_universe_rows(
                db,
                limit=STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                page_size=universe_page_size,
                start_offset=0,
            )
        except Exception:
            rows, universe_meta = [], {
                "pages_loaded": 0,
                "loaded_count": 0,
                "complete": False,
                "truncated": False,
                "page_size": universe_page_size,
            }

        hot_sectors = {
            str(item).strip()
            for item in list(snapshot.get("hot_sectors") or [])
            if str(item).strip()
        }
        cold_sectors = {
            str(item).strip()
            for item in list(snapshot.get("cold_sectors") or [])
            if str(item).strip()
        }
        active_factors = self._normalize_factor_names(snapshot)
        stock_family_allocation = self._normalize_stock_family_allocation(snapshot)
        candidate_rows = [row for row in rows if str(row.get("code") or "").strip()]
        min_history_bars = self._MIN_HISTORY_BARS
        history_counts, history_prefilter_applied = await self._fetch_history_bar_counts(
            db,
            [str(row.get("code") or "").strip() for row in candidate_rows],
            min_history_bars=min_history_bars,
        )
        filtered_rows = candidate_rows
        insufficient_history_filtered_count = 0
        if history_prefilter_applied:
            filtered_rows = [
                row
                for row in candidate_rows
                if int(history_counts.get(str(row.get("code") or "").strip()) or 0) >= min_history_bars
            ]
            insufficient_history_filtered_count = max(0, len(candidate_rows) - len(filtered_rows))

        ranked_rows = sorted(
            filtered_rows,
            key=lambda row: self._row_priority_score(
                row,
                snapshot=snapshot,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
                active_factors=active_factors,
                allocation_item=stock_family_allocation.get(str(row.get("code") or "").strip()),
            ),
            reverse=True,
        )

        effective_generation_limit = self._effective_generation_limit()
        effective_task_budget = self._effective_task_budget()
        row_plans: list[dict[str, Any]] = []
        max_family_depth = 0
        allocation_applied_count = 0
        for stock_rank, row in enumerate(ranked_rows, 1):
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            allocation_item = dict(stock_family_allocation.get(code) or {})
            row_score = self._row_priority_score(
                row,
                snapshot=snapshot,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
                active_factors=active_factors,
                allocation_item=allocation_item,
            )
            row_tasks: list[dict[str, Any]] = []
            for family_plan in self._family_plans_for_row(
                row,
                snapshot=snapshot,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
                active_factors=active_factors,
                allocation_item=allocation_item,
            ):
                family = str(family_plan.get("family") or "").strip().lower()
                if not family:
                    continue
                row_tasks.append(
                    self._build_task(
                        row,
                        family=family,
                        rank=max(1, self._safe_int(family_plan.get("family_rank")) or len(row_tasks) + 1),
                        stock_rank=stock_rank,
                        priority_score=row_score,
                        snapshot=snapshot,
                        generation_limit=effective_generation_limit,
                        family_plan=family_plan,
                        allocation_item=allocation_item,
                    )
                )
            if not row_tasks:
                continue
            if allocation_item:
                allocation_applied_count += 1
            max_family_depth = max(max_family_depth, len(row_tasks))
            row_plans.append(
                {
                    "code": code,
                    "stock_rank": stock_rank,
                    "priority_score": row_score,
                    "tasks": row_tasks,
                }
            )

        batch_size = max(1, int(STOCK_STRATEGY_MATRIX_BATCH_SIZE))
        row_plan_batches: list[list[dict[str, Any]]] = [
            row_plans[start : start + batch_size]
            for start in range(0, len(row_plans), batch_size)
        ]
        for batch_id, batch_rows in enumerate(row_plan_batches, 1):
            batch_stock_count = len(batch_rows)
            for batch_stock_index, row_plan in enumerate(batch_rows, 1):
                row_plan["matrix_batch_id"] = batch_id
                row_plan["matrix_batch_stock_index"] = batch_stock_index
                row_plan["matrix_batch_stock_count"] = batch_stock_count

        planned_tasks: list[dict[str, Any]] = []
        planned_family_counts: dict[str, int] = {}
        planned_codes: list[str] = []
        planned_allocation_pass_counts: dict[str, int] = {}
        for allocation_pass in range(max_family_depth):
            pass_key = str(allocation_pass + 1)
            pass_count = 0
            for batch_rows in row_plan_batches:
                for row_plan in batch_rows:
                    row_tasks = list(row_plan.get("tasks") or [])
                    if allocation_pass >= len(row_tasks):
                        continue
                    task = dict(row_tasks[allocation_pass] or {})
                    task["matrix_allocation_pass"] = allocation_pass + 1
                    task["matrix_batch_id"] = int(row_plan.get("matrix_batch_id") or 1)
                    task["matrix_batch_stock_index"] = int(row_plan.get("matrix_batch_stock_index") or 1)
                    task["matrix_batch_stock_count"] = int(row_plan.get("matrix_batch_stock_count") or len(batch_rows) or 1)
                    planned_tasks.append(task)
                    family = str(task.get("candidate_family") or "").strip().lower()
                    if family:
                        planned_family_counts[family] = planned_family_counts.get(family, 0) + 1
                    code = str(row_plan.get("code") or "").strip()
                    if code and code not in planned_codes:
                        planned_codes.append(code)
                    pass_count += 1
            if pass_count > 0:
                planned_allocation_pass_counts[pass_key] = pass_count

        planned_tasks = self._interleave_tasks_by_family(planned_tasks)
        for plan_slot, task in enumerate(planned_tasks, 1):
            task["matrix_plan_slot"] = plan_slot

        tasks_per_shard = max(1, int(STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD))
        shard_count = int(math.ceil(len(planned_tasks) / tasks_per_shard)) if planned_tasks else 0
        planned_batch_task_counts: dict[str, int] = {}
        for task in planned_tasks:
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            planned_batch_task_counts[batch_key] = planned_batch_task_counts.get(batch_key, 0) + 1
        planned_batch_task_indexes: dict[str, int] = {}
        for index, task in enumerate(planned_tasks, 1):
            task["matrix_shard_id"] = int(math.ceil(index / tasks_per_shard))
            task["matrix_shard_task_index"] = ((index - 1) % tasks_per_shard) + 1
            task["matrix_shard_count"] = shard_count
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            planned_batch_task_indexes[batch_key] = planned_batch_task_indexes.get(batch_key, 0) + 1
            task["matrix_batch_count"] = len(row_plan_batches)
            task["matrix_batch_task_index"] = planned_batch_task_indexes[batch_key]
            task["matrix_batch_task_count"] = int(planned_batch_task_counts.get(batch_key) or 0)

        planned_task_count = len(planned_tasks)
        requested_task_offset = max(
            0,
            int(
                snapshot.get("bulk_stock_matrix_task_offset")
                or snapshot.get("bulk_stock_matrix_universe_offset")
                or 0
            ),
        )
        effective_task_offset, next_task_offset, task_cursor_wrapped, task_offset_fallback = self._resolve_task_cursor(
            planned_task_count=planned_task_count,
            requested_task_offset=requested_task_offset,
            effective_task_budget=effective_task_budget,
        )

        tasks: list[dict[str, Any]] = []
        if planned_task_count > 0:
            actual_budget = max(1, min(effective_task_budget, planned_task_count))
            window_end = effective_task_offset + actual_budget
            if window_end <= planned_task_count:
                tasks = [dict(item or {}) for item in planned_tasks[effective_task_offset:window_end]]
            else:
                tasks = [
                    *[dict(item or {}) for item in planned_tasks[effective_task_offset:]],
                    *[dict(item or {}) for item in planned_tasks[: window_end % planned_task_count]],
                ]

        family_counts: dict[str, int] = {}
        selected_codes: list[str] = []
        allocation_pass_counts: dict[str, int] = {}
        batch_task_counts: dict[str, int] = {}
        batch_task_indexes: dict[str, int] = {}
        for index, task in enumerate(tasks, 1):
            task["matrix_budget_slot"] = index
            family = str(task.get("candidate_family") or "").strip().lower()
            if family:
                family_counts[family] = family_counts.get(family, 0) + 1
            code = str((task.get("target_symbols") or [None])[0] or "").strip()
            if code and code not in selected_codes:
                selected_codes.append(code)
            pass_key = str(int(task.get("matrix_allocation_pass") or 0))
            if pass_key and pass_key != "0":
                allocation_pass_counts[pass_key] = allocation_pass_counts.get(pass_key, 0) + 1
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            batch_task_counts[batch_key] = batch_task_counts.get(batch_key, 0) + 1
        for task in tasks:
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            batch_task_indexes[batch_key] = batch_task_indexes.get(batch_key, 0) + 1
            task["matrix_batch_task_index"] = batch_task_indexes[batch_key]
            task["matrix_batch_task_count"] = int(batch_task_counts.get(batch_key) or 0)

        selected_shard_ids = sorted(
            {
                int(task.get("matrix_shard_id") or 0)
                for task in tasks
                if int(task.get("matrix_shard_id") or 0) > 0
            }
        )

        eligible_stock_count = len(row_plans)
        stock_coverage_ratio = round(len(selected_codes) / eligible_stock_count, 4) if eligible_stock_count else 0.0
        analysis_stock_coverage_ratio = round(eligible_stock_count / len(rows), 4) if rows else 0.0
        overflow_task_count = max(planned_task_count - len(tasks), 0)
        stock_family_allocation_coverage_ratio = (
            round(allocation_applied_count / eligible_stock_count, 4)
            if eligible_stock_count
            else 0.0
        )

        report = {
            "summary": {
                "enabled": True,
                "task_count": len(tasks),
                "stock_count": len(selected_codes),
                "eligible_stock_count": eligible_stock_count,
                "loaded_stock_count": len(rows),
                "pages_loaded": int(universe_meta.get("pages_loaded") or 0),
                "analysis_complete": bool(universe_meta.get("complete")) and not bool(universe_meta.get("truncated")),
                "analysis_stock_coverage_ratio": analysis_stock_coverage_ratio,
                "family_counts": family_counts,
                "planned_family_counts": planned_family_counts,
                "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                "requested_universe_offset": requested_task_offset,
                "effective_universe_offset": effective_task_offset,
                "universe_offset_fallback": task_offset_fallback,
                "next_universe_offset": next_task_offset,
                "cursor_wrapped": task_cursor_wrapped,
                "cursor_mode": "task_offset",
                "requested_task_offset": requested_task_offset,
                "effective_task_offset": effective_task_offset,
                "task_offset_fallback": task_offset_fallback,
                "next_task_offset": next_task_offset,
                "task_cursor_wrapped": task_cursor_wrapped,
                "max_tasks_per_run": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
                "max_candidates_per_run": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
                "families_per_stock": STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
                "generation_limit_per_task": effective_generation_limit,
                "effective_task_budget": effective_task_budget,
                "estimated_candidate_count": len(tasks) * effective_generation_limit,
                "planned_task_count": planned_task_count,
                "planned_candidate_count": planned_task_count * effective_generation_limit,
                "batch_size": batch_size,
                "batch_count": len(row_plan_batches),
                "selected_batch_count": len(batch_task_counts),
                "batch_task_counts": batch_task_counts,
                "tasks_per_shard": tasks_per_shard,
                "shard_count": shard_count,
                "selected_shard_count": len(selected_shard_ids),
                "selected_shard_ids": selected_shard_ids,
                "stock_coverage_ratio": stock_coverage_ratio,
                "allocation_mode": (
                    "factor_research_stock_family_allocation"
                    if allocation_applied_count > 0
                    else "stock_round_robin_by_family_rank"
                ),
                "allocation_pass_counts": allocation_pass_counts,
                "planned_allocation_pass_counts": planned_allocation_pass_counts,
                "overflow_task_count": overflow_task_count,
                "stock_family_allocation_count": len(stock_family_allocation),
                "stock_family_allocation_applied_count": allocation_applied_count,
                "stock_family_allocation_coverage_ratio": stock_family_allocation_coverage_ratio,
                "min_history_bars": min_history_bars,
                "history_prefilter_applied": history_prefilter_applied,
                "insufficient_history_filtered_count": insufficient_history_filtered_count,
            },
            "tasks": tasks,
        }
        task_artifact = build_task_artifact(
            {
                "task_scan": report,
                "task_source_counts": {"bulk_stock_matrix": len(tasks)},
                "event_task_count": 0,
                "snapshot_task_count": 0,
                "bulk_stock_task_count": len(tasks),
            }
        )
        report["task_artifact"] = task_artifact
        report["summary"] = {
            **dict(report.get("summary") or {}),
            "task_artifact_contract_version": task_artifact.get("contract_version"),
            "task_artifact_available": bool(task_artifact.get("available")),
        }
        self.last_report = report
        return self.last_report

    def get_last_report(self) -> dict[str, Any]:
        return dict(self.last_report)


__all__ = ["StockStrategyMatrixPlanner"]
