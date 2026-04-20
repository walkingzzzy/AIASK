    """Plan per-stock strategy-family tasks for bulk autonomy generation."""

    _MIN_HISTORY_BARS = 100
    _HISTORY_COUNT_CHUNK_SIZE = 400
    _HIGH_CONFLICT_FAMILY_SHARE_CAP = 0.2
    _HIGH_CONFLICT_FAMILY_ABS_CAP = 4

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
        elif normalized_family == "quality_factor" and normalized_focus == "candidate_target_only":
            profile = "trade_rule_validation"
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
        if str(family or "").strip().lower() == "quality_factor" and validation_focus == "candidate_target_only":
            normalized_profile = "trade_rule_validation"
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
        if normalized_family == "mean_reversion_short":
            base_penalty = 0.28
        elif normalized_family in {"momentum", "growth_factor", "volatility_breakout", "gap_fill"}:
            base_penalty = 0.22
        elif normalized_family in {"quality_factor", "value_factor"}:
            base_penalty = 0.08
        else:
            base_penalty = 0.14
        return round(min(base_penalty + max(family_rank - 1, 0) * 0.03, 0.45), 4)

    @classmethod
    def _family_task_cap(cls, family: str, *, effective_task_budget: int) -> int | None:
        normalized_family = str(family or "").strip().lower()
        if normalized_family != "mean_reversion_short":
            return None
        dynamic_cap = int(math.ceil(max(1, int(effective_task_budget or 1)) * cls._HIGH_CONFLICT_FAMILY_SHARE_CAP))
        return max(1, min(cls._HIGH_CONFLICT_FAMILY_ABS_CAP, dynamic_cap))

    @classmethod
    def _apply_family_pressure_caps(
        cls,
        tasks: list[dict[str, Any]],
        *,
        effective_task_budget: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if not tasks:
            return [], {}

        kept: list[dict[str, Any]] = []
        family_counts: dict[str, int] = {}
        family_caps: dict[str, int] = {}
        for raw_task in tasks:
            task = dict(raw_task or {})
            family = str(task.get("candidate_family") or "").strip().lower()
            cap = cls._family_task_cap(family, effective_task_budget=effective_task_budget)
            if cap is not None:
                family_caps[family] = cap
                if int(family_counts.get(family) or 0) >= cap:
                    continue
            kept.append(task)
            if family:
                family_counts[family] = family_counts.get(family, 0) + 1
        return kept, family_caps

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
    def _research_family_preference_order(cls, snapshot: dict[str, Any]) -> list[str]:
        factor_research = dict(snapshot.get("factor_research") or {})
        summary = dict(factor_research.get("summary") or {})
        ordered: list[str] = []
        for source in (
            factor_research.get("family_preference_order"),
            summary.get("family_preference_order"),
        ):
            for item in list(source or []):
                family = str(item or "").strip().lower()
                if family and family not in ordered:
                    ordered.append(family)
        return ordered

    @classmethod
    def _family_preference_source(cls, snapshot: dict[str, Any]) -> str:
        factor_research = dict(snapshot.get("factor_research") or {})
        summary = dict(factor_research.get("summary") or {})
        if cls._research_family_preference_order(snapshot):
            return (
                str(
                    factor_research.get("family_preference_source_mode")
                    or summary.get("family_preference_source_mode")
                    or "factor_research"
                ).strip()
                or "factor_research"
            )
        return "fear_greed_base_order"

    @classmethod
    def _base_family_order(cls, snapshot: dict[str, Any]) -> list[str]:
        research_order = cls._research_family_preference_order(snapshot)
        if research_order:
            return research_order
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
        if family in {"rsi"}:
            return "short"
        if family in {"momentum"}:
            return "medium"
        if family in {"value_factor"}:
            return "long"
        return "medium"

    @staticmethod
    def _holding_window_for_family(family: str) -> dict[str, Any]:
        normalized_family = str(family or "").strip().lower()
        if normalized_family == "quality_factor":
            return {"min_days": 24, "max_days": 72}
        if normalized_family == "ma_cross":
            return {"min_days": 14, "max_days": 48}
        if normalized_family == "momentum":
            return {"min_days": 14, "max_days": 42}
        if normalized_family in {"value_factor", "growth_factor", "multi_factor"}:
            return {"min_days": 18, "max_days": 60}
        if normalized_family in {"rsi", "gap_fill", "mean_reversion_short"}:
            return {"min_days": 3, "max_days": 12}
        return {"min_days": 5, "max_days": 20}

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
