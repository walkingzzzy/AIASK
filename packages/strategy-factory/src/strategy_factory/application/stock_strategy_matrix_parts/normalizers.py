    """Plan per-stock strategy-family tasks for bulk autonomy generation."""

    _MIN_HISTORY_BARS = 250
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

    @classmethod
    def _runtime_flags_for_snapshot(cls, snapshot: dict[str, Any] | None) -> dict[str, bool]:
        payload = dict(snapshot or {})
        execution_mode = str(
            payload.get("factory_execution_mode")
            or payload.get("execution_mode")
            or ""
        ).strip()
        if not execution_mode:
            return {}
        try:
            return dict(resolve_runtime_mode_flags(execution_mode) or {})
        except Exception:
            return {}

    @classmethod
    def _effective_stock_matrix_enabled(cls, snapshot: dict[str, Any] | None) -> bool:
        flags = cls._runtime_flags_for_snapshot(snapshot)
        return bool(STOCK_STRATEGY_MATRIX_ENABLED or flags.get("stock_first_observe_mode"))

    @classmethod
    def _effective_router_enabled(cls, snapshot: dict[str, Any] | None) -> bool:
        flags = cls._runtime_flags_for_snapshot(snapshot)
        return bool(STOCK_FIRST_ROUTER_ENABLED or flags.get("router_enabled"))

    @classmethod
    def _effective_router_strict(cls, snapshot: dict[str, Any] | None) -> bool:
        flags = cls._runtime_flags_for_snapshot(snapshot)
        return bool(STOCK_FIRST_ROUTER_STRICT or flags.get("router_strict"))

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

    @staticmethod
    def _industry_key(value: Any) -> str:
        token = str(value or "").strip()
        return token or "__unknown__"

    @classmethod
    def _normalize_sector_labels(
        cls,
        values: Any,
        *,
        limit: int | None = None,
    ) -> list[str]:
        return normalize_sector_labels(values, limit=limit)

    @classmethod
    def _sector_match_strength(
        cls,
        industry: Any,
        sector_labels: Any,
    ) -> float:
        return sector_match_strength(industry, sector_labels)

    @classmethod
    def _sector_family_biases(
        cls,
        industry: Any,
        *,
        mode: str = "intrinsic",
    ) -> list[str]:
        return sector_family_biases(industry, mode=mode)

    @classmethod
    def _build_sector_label_coverage(
        cls,
        rows: list[dict[str, Any]],
        *,
        sector_labels: set[str],
    ) -> dict[str, dict[str, float]]:
        normalized_labels = [
            str(item or "").strip()
            for item in list(sector_labels or set())
            if str(item or "").strip()
        ]
        if not normalized_labels:
            return {}
        universe_size = max(1, len(list(rows or [])))
        coverage: dict[str, dict[str, float]] = {}
        for label in normalized_labels:
            matched_count = 0
            matched_profile_keys: set[str] = set()
            for row in list(rows or []):
                industry = str(dict(row or {}).get("industry") or dict(row or {}).get("sector") or "").strip()
                if cls._sector_match_strength(industry, [label]) <= 0.0:
                    continue
                matched_count += 1
                for profile in sector_profiles_for_label(industry):
                    profile_key = str(profile.get("key") or "").strip()
                    if profile_key:
                        matched_profile_keys.add(profile_key)
            coverage_ratio = matched_count / float(universe_size)
            profile_breadth = max(1, len(matched_profile_keys))
            breadth_penalty = 1.0 / math.sqrt(float(profile_breadth))
            coverage_penalty = max(0.45, 1.0 - min(coverage_ratio, 0.35) * 1.4)
            coverage[label] = {
                "matched_count": float(matched_count),
                "coverage_ratio": round(coverage_ratio, 4),
                "matched_profile_count": float(profile_breadth),
                "breadth_penalty": round(breadth_penalty, 4),
                "coverage_penalty": round(coverage_penalty, 4),
                "effective_penalty": round(min(1.0, breadth_penalty * coverage_penalty), 4),
            }
        return coverage

    @classmethod
    def _sector_regime_component_score(
        cls,
        industry: Any,
        *,
        sector_labels: set[str],
        label_coverage: dict[str, dict[str, float]] | None,
        base_points: float,
    ) -> float:
        normalized_labels = [
            str(item or "").strip()
            for item in list(sector_labels or set())
            if str(item or "").strip()
        ]
        best_score = 0.0
        for label in normalized_labels:
            match_strength = cls._sector_match_strength(industry, [label])
            if match_strength <= 0.0:
                continue
            penalty_payload = dict((label_coverage or {}).get(label) or {})
            breadth_penalty = cls._safe_float(penalty_payload.get("breadth_penalty") or 1.0)
            coverage_penalty = cls._safe_float(penalty_payload.get("coverage_penalty") or 1.0)
            effective_penalty = max(0.35, min(1.0, breadth_penalty * coverage_penalty))
            best_score = max(best_score, base_points * match_strength * effective_penalty)
        return round(best_score, 4)

    @staticmethod
    def _percentile_from_sorted(
        sorted_values: list[float],
        value: float,
        *,
        higher_is_better: bool,
    ) -> float:
        values = [float(item) for item in list(sorted_values or [])]
        if not values:
            return 0.5
        if len(values) == 1:
            return 1.0
        target = float(value)
        left = max(0, min(bisect_left(values, target), len(values) - 1))
        right = max(0, min(bisect_right(values, target) - 1, len(values) - 1))
        average_position = (left + right) / 2.0
        if higher_is_better:
            return max(0.0, min(average_position / (len(values) - 1), 1.0))
        return max(0.0, min(1.0 - (average_position / (len(values) - 1)), 1.0))

    @staticmethod
    def _factor_signal_enabled(active_factors: list[str], token: str) -> bool:
        normalized_token = str(token or "").strip().lower()
        if not normalized_token:
            return False
        for factor_name in list(active_factors or []):
            normalized_factor = str(factor_name or "").strip().lower()
            if not normalized_factor:
                continue
            if normalized_factor == normalized_token:
                return True
            if normalized_token in normalized_factor:
                return True
        return False

    @classmethod
    def _build_priority_scoring_context(
        cls,
        rows: list[dict[str, Any]],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
        stock_family_allocation: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        allocation = {
            str(code or "").strip(): dict(item or {})
            for code, item in dict(stock_family_allocation or {}).items()
            if str(code or "").strip()
        }
        normalized_hot_sectors = set(cls._normalize_sector_labels(hot_sectors, limit=20))
        normalized_cold_sectors = set(cls._normalize_sector_labels(cold_sectors, limit=20))
        normalized_active_factors = [
            str(item or "").strip().lower()
            for item in list(active_factors or [])
            if str(item or "").strip()
        ]
        preferred_families: list[str] = []
        for factor_name in normalized_active_factors:
            for family in preferred_strategy_types_for_factor(factor_name, default=[]):
                normalized_family = str(family or "").strip().lower()
                if normalized_family and normalized_family not in preferred_families:
                    preferred_families.append(normalized_family)

        size_logs: list[float] = []
        valuation_pe_global: list[float] = []
        valuation_pb_global: list[float] = []
        valuation_pe_by_industry: dict[str, list[float]] = {}
        valuation_pb_by_industry: dict[str, list[float]] = {}
        allocation_priorities: list[float] = []
        allocation_source_modes: list[str] = []
        for row in list(rows or []):
            payload = dict(row or {})
            market_cap = cls._safe_float(payload.get("market_cap"))
            if market_cap > 0:
                size_logs.append(math.log(max(market_cap, 1.0)))
            industry_key = cls._industry_key(payload.get("industry") or payload.get("sector"))
            pe_ratio = cls._safe_float(payload.get("pe_ratio"))
            pb_ratio = cls._safe_float(payload.get("pb_ratio"))
            if pe_ratio > 0:
                valuation_pe_global.append(pe_ratio)
                valuation_pe_by_industry.setdefault(industry_key, []).append(pe_ratio)
            if pb_ratio > 0:
                valuation_pb_global.append(pb_ratio)
                valuation_pb_by_industry.setdefault(industry_key, []).append(pb_ratio)
            code = str(payload.get("code") or "").strip()
            allocation_item = dict(allocation.get(code) or {})
            allocation_priority = max(0.0, min(cls._safe_float(allocation_item.get("priority")), 1.0))
            if allocation_priority > 0.0:
                allocation_priorities.append(allocation_priority)
            source_mode = str(allocation_item.get("source_mode") or "").strip()
            if source_mode:
                allocation_source_modes.append(source_mode)

        for bucket in valuation_pe_by_industry.values():
            bucket.sort()
        for bucket in valuation_pb_by_industry.values():
            bucket.sort()
        size_logs.sort()
        valuation_pe_global.sort()
        valuation_pb_global.sort()
        allocation_priorities.sort()

        source_mode = None
        if allocation_source_modes:
            distinct_source_modes = list(dict.fromkeys(allocation_source_modes))
            source_mode = distinct_source_modes[0] if len(distinct_source_modes) == 1 else "mixed"

        hot_sector_coverage = cls._build_sector_label_coverage(
            rows,
            sector_labels=normalized_hot_sectors,
        )
        cold_sector_coverage = cls._build_sector_label_coverage(
            rows,
            sector_labels=normalized_cold_sectors,
        )

        return {
            "score_contract_version": "strategy_factory.full_market_topn.v2",
            "preferred_families": preferred_families,
            "normalized_active_factors": normalized_active_factors,
            "hot_sectors": normalized_hot_sectors,
            "cold_sectors": normalized_cold_sectors,
            "hot_sector_coverage": hot_sector_coverage,
            "cold_sector_coverage": cold_sector_coverage,
            "size_logs": size_logs,
            "valuation_pe_global": valuation_pe_global,
            "valuation_pb_global": valuation_pb_global,
            "valuation_pe_by_industry": valuation_pe_by_industry,
            "valuation_pb_by_industry": valuation_pb_by_industry,
            "allocation_priorities": allocation_priorities,
            "allocation_source_mode": source_mode,
            "allocation_avg_priority": round(
                sum(allocation_priorities) / len(allocation_priorities),
                4,
            ) if allocation_priorities else 0.0,
            "active_factors": list(active_factors or []),
            "snapshot_date": str(snapshot.get("date") or snapshot.get("snapshot_date") or "").strip() or None,
        }

    # ------------------------------------------------------------------
    # PR-S19 (策略工厂跑偏修复方案 P2)：消费 row["stock_profile"] 画像
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_profile_summary(row: dict[str, Any]) -> dict[str, Any]:
        """从 row 上的 stock_profile（来自 PR-S17）提取 profile_summary。

        路径：row["stock_profile"]["metadata"]["profile_summary"]，
        兼容老结构 row["stock_profile"]["profile_summary"]。
        若画像缺失，返回 {}。
        """

        profile = dict(row.get("stock_profile") or {})
        if not profile:
            return {}
        metadata = profile.get("metadata")
        if isinstance(metadata, str):
            # SQLite 存储有时返回 JSON 字符串
            try:
                import json as _json

                metadata = _json.loads(metadata or "{}")
            except Exception:
                metadata = {}
        metadata = dict(metadata or {})
        summary = dict(metadata.get("profile_summary") or profile.get("profile_summary") or {})
        return summary

    @classmethod
    def _build_lightweight_profile_summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        """Build a local, no-IO profile so strict Stock-First runs never use legacy family fallback silently."""

        pe_ratio = cls._safe_float(row.get("pe_ratio"))
        pb_ratio = cls._safe_float(row.get("pb_ratio"))
        market_cap = cls._safe_float(row.get("market_cap"))
        valuation_score = 0.0
        if 0 < pe_ratio <= 30:
            valuation_score = max(valuation_score, (30.0 - pe_ratio) / 30.0)
        if 0 < pb_ratio <= 3:
            valuation_score = max(valuation_score, (3.0 - pb_ratio) / 3.0)
        quality_score = 0.0
        if market_cap > 0:
            try:
                quality_score = max(0.0, min(math.log10(market_cap / 1e8 + 1.0) / 3.0, 1.0))
            except Exception:
                quality_score = 0.0
        recommended = ["multi_factor"]
        if valuation_score >= 0.35 and quality_score >= 0.25:
            recommended = ["value_factor", "quality_factor", "multi_factor"]
        elif quality_score >= 0.55:
            recommended = ["quality_factor", "multi_factor"]
        return {
            "profile_quality": "partial",
            "profile_source": "lightweight_row_fallback",
            "primary_archetype": "lightweight_unknown",
            "secondary_archetypes": [],
            "regime": {
                "trend_regime": "unknown",
                "vol_regime": "unknown",
                "sentiment_regime": "unknown",
            },
            "factor_dimension_scores": {
                "trend": 0.0,
                "reversal": 0.0,
                "valuation": round(max(0.0, min(valuation_score, 1.0)), 4),
                "quality": round(max(0.0, min(quality_score, 1.0)), 4),
                "growth": 0.0,
            },
            "feature_coverage": {
                "technical_price_volume": "missing",
                "valuation_financial": "partial" if valuation_score > 0.0 or quality_score > 0.0 else "missing",
                "alternative_sentiment_capital_flow": "missing",
                "event_news_notice_research_theme": "missing",
            },
            "recommended_families": recommended,
            "candidate_factor_families": recommended,
        }

    @classmethod
    def _ensure_lightweight_profile_summary(cls, row: dict[str, Any]) -> bool:
        if cls._extract_profile_summary(row):
            return False
        profile = dict(row.get("stock_profile") or {})
        metadata = profile.get("metadata")
        if isinstance(metadata, str):
            try:
                import json as _json

                metadata = _json.loads(metadata or "{}")
            except Exception:
                metadata = {}
        metadata = dict(metadata or {})
        metadata["profile_summary"] = cls._build_lightweight_profile_summary(row)
        profile["metadata"] = metadata
        profile.setdefault("stock_code", row.get("code"))
        profile.setdefault("source", "lightweight_row_fallback")
        row["stock_profile"] = profile
        row["_stock_first_router_lightweight_profile_generated"] = True
        return True

    @staticmethod
    def _set_router_status(
        row: dict[str, Any],
        *,
        status: str,
        enabled: bool | None = None,
        strict: bool | None = None,
        reason: str | None = None,
        families: list[str] | None = None,
        holding_bucket: str | None = None,
        confidence: float | None = None,
        exclusions: list[str] | None = None,
        error_type: str | None = None,
    ) -> None:
        payload = {
            "enabled": bool(STOCK_FIRST_ROUTER_ENABLED if enabled is None else enabled),
            "strict": bool(STOCK_FIRST_ROUTER_STRICT if strict is None else strict),
            "status": str(status or "unknown").strip().lower() or "unknown",
            "reason": str(reason or "").strip() or None,
            "families": list(families or []),
            "holding_bucket": str(holding_bucket or "").strip() or None,
            "confidence": confidence,
            "exclusions": list(exclusions or []),
            "error_type": str(error_type or "").strip() or None,
            "lightweight_profile_generated": bool(row.get("_stock_first_router_lightweight_profile_generated")),
        }
        row["_stock_first_router"] = {key: value for key, value in payload.items() if value not in (None, "", [])}

    @classmethod
    def _router_telemetry_for_rows(
        cls,
        rows: list[dict[str, Any]],
        *,
        selected_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        router_rows = [row for row in list(rows or []) if str((row or {}).get("code") or "").strip()]
        status_counts: dict[str, int] = {}
        fallback_reason_counts: dict[str, int] = {}
        family_counts: dict[str, int] = {}
        bucket_counts: dict[str, int] = {}
        applied_count = 0
        present_count = 0
        generated_count = 0
        enabled_seen: list[bool] = []
        strict_seen: list[bool] = []
        for row in router_rows:
            if cls._extract_profile_summary(row):
                present_count += 1
            if bool(row.get("_stock_first_router_lightweight_profile_generated")):
                generated_count += 1
            status = dict(row.get("_stock_first_router") or {})
            if "enabled" in status:
                enabled_seen.append(bool(status.get("enabled")))
            if "strict" in status:
                strict_seen.append(bool(status.get("strict")))
            state = str(status.get("status") or "not_evaluated").strip().lower() or "not_evaluated"
            status_counts[state] = status_counts.get(state, 0) + 1
            if state == "applied":
                applied_count += 1
                for family in list(status.get("families") or []):
                    token = str(family or "").strip().lower()
                    if token:
                        family_counts[token] = family_counts.get(token, 0) + 1
                bucket = str(status.get("holding_bucket") or "").strip().lower()
                if bucket:
                    bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            elif state in {"fallback", "blocked"}:
                reason = str(status.get("reason") or "unknown").strip().lower() or "unknown"
                fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1

        selected_router_applied_count = 0
        selected_profile_missing_count = 0
        selected_task_count = 0
        for task in list(selected_tasks or []):
            selected_task_count += 1
            router = dict(task.get("stock_first_router") or {})
            if str(router.get("status") or "").strip().lower() == "applied":
                selected_router_applied_count += 1
            if not task.get("stock_profile_summary"):
                selected_profile_missing_count += 1

        missing_count = max(0, len(router_rows) - present_count)
        return {
            "router_enabled": bool(STOCK_FIRST_ROUTER_ENABLED or any(enabled_seen)),
            "router_strict": bool(STOCK_FIRST_ROUTER_STRICT or any(strict_seen)),
            "router_telemetry_enabled": bool(STOCK_FIRST_ROUTER_TELEMETRY_ENABLED),
            "router_candidate_stock_count": len(router_rows),
            "router_applied_count": applied_count,
            "router_status_counts": status_counts,
            "router_fallback_reason_counts": fallback_reason_counts,
            "router_family_counts": family_counts,
            "router_holding_bucket_counts": bucket_counts,
            "profile_summary_present_count": present_count,
            "profile_summary_missing_count": missing_count,
            "profile_summary_generated_count": generated_count,
            "selected_task_count": selected_task_count,
            "selected_router_applied_count": selected_router_applied_count,
            "selected_profile_summary_missing_count": selected_profile_missing_count,
        }

    @staticmethod
    def _profile_dimension_scores(profile_summary: dict[str, Any]) -> dict[str, float]:
        scores = dict(profile_summary.get("factor_dimension_scores") or {})
        out: dict[str, float] = {}
        for key, value in scores.items():
            try:
                out[str(key).strip().lower()] = max(0.0, min(float(value), 1.0))
            except (TypeError, ValueError):
                continue
        return out

    @classmethod
    def _intrinsic_families_for_row(
        cls,
        row: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
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

        # PR-S19：优先消费 stock_profile 推荐 family，让画像真正影响 family 选择
        profile_summary = cls._extract_profile_summary(row)
        profile_quality = str(profile_summary.get("profile_quality") or "").strip().lower()
        coverage = dict(profile_summary.get("feature_coverage") or {})
        router_enabled = cls._effective_router_enabled(snapshot)
        router_strict = cls._effective_router_strict(snapshot)

        # SR-1 (P1-2)：toggle ON 且画像可用时，由 StockStrategyRouter 依 regime+周期+排除项决定 family。
        # 严守同步边界：只读已挂在 row 上的 profile_summary，不做任何异步/网络调用。
        if router_enabled and not profile_summary:
            cls._set_router_status(
                row,
                status="blocked" if router_strict else "fallback",
                enabled=router_enabled,
                strict=router_strict,
                reason="missing_profile_summary",
            )
            if router_strict:
                return []
        if router_enabled and profile_summary and profile_quality in {"failed", ""}:
            reason = "profile_failed" if profile_quality == "failed" else "profile_quality_missing"
            cls._set_router_status(
                row,
                status="blocked" if router_strict else "fallback",
                enabled=router_enabled,
                strict=router_strict,
                reason=reason,
            )
            if router_strict:
                return []
        if router_enabled and profile_summary and profile_quality not in {"failed", ""}:
            try:
                regime = dict(profile_summary.get("regime") or {})
                extras = {
                    "rsi": ((profile_summary.get("factor_dimension_scores") or {}) or {}).get("rsi"),
                    "volume_ratio": cls._safe_float(row.get("volume_ratio_5_20")) or 1.0,
                    "event_catalyst": str(coverage.get("event_news_notice_research_theme") or "").lower()
                    in {"ok", "partial"},
                    "liquidity_low": (cls._safe_float(row.get("amount")) or 0.0) > 0
                    and (cls._safe_float(row.get("amount")) or 0.0) < 1e7,
                }
                profile = StockRegimeProfile.from_profile_summary(
                    str(row.get("code") or ""), profile_summary, regime, extras
                )
                routed = route_strategies(profile, max_families=STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)
                if routed.families:
                    families = routed.families[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]
                    cls._set_router_status(
                        row,
                        status="applied",
                        enabled=router_enabled,
                        strict=router_strict,
                        families=families,
                        holding_bucket=routed.holding_period_bucket,
                        confidence=float(routed.confidence or 0.0),
                        exclusions=list(routed.exclusions or []),
                    )
                    return families
                cls._set_router_status(
                    row,
                    status="blocked" if router_strict else "fallback",
                    enabled=router_enabled,
                    strict=router_strict,
                    reason="empty_routed_families",
                )
                if router_strict:
                    return []
            except Exception as exc:
                cls._set_router_status(
                    row,
                    status="blocked" if router_strict else "fallback",
                    enabled=router_enabled,
                    strict=router_strict,
                    reason="router_exception",
                    error_type=type(exc).__name__,
                )
                if router_strict:
                    return []

        if profile_summary and profile_quality not in {"failed", ""}:
            recommended = [
                str(item or "").strip().lower()
                for item in list(profile_summary.get("recommended_families") or [])
                if str(item or "").strip()
            ]
            candidate_families = [
                str(item or "").strip().lower()
                for item in list(profile_summary.get("candidate_factor_families") or [])
                if str(item or "").strip()
            ]
            # alternative_sentiment 与 event 维度 coverage 缺失时，剔除强情绪/事件 family
            alt_cov = str(coverage.get("alternative_sentiment_capital_flow") or "").lower()
            event_cov = str(coverage.get("event_news_notice_research_theme") or "").lower()

            def _allowed(fam: str) -> bool:
                if fam == "event_structure_breakout":
                    return event_cov in {"ok", "partial"}
                if fam == "sentiment" or fam == "sentiment_factor":
                    return alt_cov in {"ok", "partial"}
                return True

            for fam in recommended:
                if _allowed(fam):
                    add(fam)
            for fam in candidate_families:
                if _allowed(fam):
                    add(fam)

        if router_enabled:
            current = dict(row.get("_stock_first_router") or {})
            if str(current.get("status") or "").strip().lower() != "applied":
                cls._set_router_status(
                    row,
                    status="fallback",
                    enabled=router_enabled,
                    strict=router_strict,
                    reason=str(current.get("reason") or "legacy_family_fallback"),
                )

        # 旧逻辑（hot/cold sector + 估值 + base family 序列）作为 fallback / 补充
        hot_match = cls._sector_match_strength(industry, hot_sectors)
        cold_match = cls._sector_match_strength(industry, cold_sectors)
        add(*cls._sector_family_biases(industry, mode="intrinsic"))
        if hot_match > 0.0:
            add(*cls._sector_family_biases(industry, mode="hot") or ["momentum", "growth_factor"])
        if cold_match > 0.0:
            add(*cls._sector_family_biases(industry, mode="cold") or ["rsi", "value_factor", "quality_factor"])
        value_candidate = 0 < pe_ratio <= 18 or 0 < pb_ratio <= 1.8
        reversal_enabled = cls._factor_signal_enabled(active_factors, "reversal")
        if value_candidate:
            add("value_factor")
            if reversal_enabled:
                add("mean_reversion_short")
            add("quality_factor")
        add(*cls._base_family_order(snapshot))
        for factor_name in active_factors:
            add(*preferred_strategy_types_for_factor(factor_name, default=[]))

        return families[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]

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
        scoring_context: dict[str, Any] | None = None,
    ) -> float:
        components = cls._row_priority_components(
            row,
            snapshot=snapshot,
            hot_sectors=hot_sectors,
            cold_sectors=cold_sectors,
            active_factors=active_factors,
            allocation_item=allocation_item,
            scoring_context=scoring_context,
        )
        return round(sum(cls._safe_float(value) for value in components.values()), 4)

    @classmethod
    def _row_priority_components(
        cls,
        row: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        hot_sectors: set[str],
        cold_sectors: set[str],
        active_factors: list[str],
        allocation_item: dict[str, Any] | None = None,
        scoring_context: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        market_cap = cls._safe_float(row.get("market_cap"))
        industry = str(row.get("industry") or row.get("sector") or "").strip()
        resolved_context = dict(scoring_context or {})
        normalized_active_factors = [
            str(item or "").strip().lower()
            for item in list(
                resolved_context.get("normalized_active_factors")
                or active_factors
                or []
            )
            if str(item or "").strip()
        ]
        preferred_families = [
            str(item or "").strip().lower()
            for item in list(resolved_context.get("preferred_families") or [])
            if str(item or "").strip()
        ]
        components: dict[str, float] = {
            "size_score": 0.0,
            "valuation_score": 0.0,
            "sector_regime_score": 0.0,
            "factor_alignment_score": 0.0,
            "allocation_score": 0.0,
            # PR-S19：画像驱动维度
            "stock_profile_score": 0.0,
            "profile_quality_score": 0.0,
        }
        size_logs = list(resolved_context.get("size_logs") or [])
        if market_cap > 0:
            if size_logs:
                size_pct = cls._percentile_from_sorted(
                    size_logs,
                    math.log(max(market_cap, 1.0)),
                    higher_is_better=True,
                )
            else:
                normalized_log = math.log10(market_cap / 1e8 + 1.0)
                size_pct = max(0.0, min(normalized_log / 2.5, 1.0))
            components["size_score"] = round(size_pct * 12.0, 4)

        hot_sector_set = set(resolved_context.get("hot_sectors") or hot_sectors or set())
        cold_sector_set = set(resolved_context.get("cold_sectors") or cold_sectors or set())
        hot_sector_coverage = dict(resolved_context.get("hot_sector_coverage") or {})
        cold_sector_coverage = dict(resolved_context.get("cold_sector_coverage") or {})
        hot_score = cls._sector_regime_component_score(
            industry,
            sector_labels=hot_sector_set,
            label_coverage=hot_sector_coverage,
            base_points=6.0,
        )
        cold_score = cls._sector_regime_component_score(
            industry,
            sector_labels=cold_sector_set,
            label_coverage=cold_sector_coverage,
            base_points=4.0,
        )
        if hot_score > 0.0:
            components["sector_regime_score"] += hot_score
        if cold_score > 0.0:
            components["sector_regime_score"] -= cold_score

        pe_ratio = cls._safe_float(row.get("pe_ratio"))
        pb_ratio = cls._safe_float(row.get("pb_ratio"))
        if cls._factor_signal_enabled(normalized_active_factors, "value") or cls._factor_signal_enabled(
            normalized_active_factors,
            "reversal",
        ):
            industry_key = cls._industry_key(industry)
            pe_values = list(
                dict(resolved_context).get("valuation_pe_by_industry", {}).get(industry_key)
                or []
            )
            pb_values = list(
                dict(resolved_context).get("valuation_pb_by_industry", {}).get(industry_key)
                or []
            )
            if len(pe_values) < 20:
                pe_values = list(resolved_context.get("valuation_pe_global") or [])
            if len(pb_values) < 20:
                pb_values = list(resolved_context.get("valuation_pb_global") or [])
            valuation_percentiles: list[float] = []
            if pe_ratio > 0:
                valuation_percentiles.append(
                    cls._percentile_from_sorted(
                        pe_values,
                        pe_ratio,
                        higher_is_better=False,
                    )
                )
            if pb_ratio > 0:
                valuation_percentiles.append(
                    cls._percentile_from_sorted(
                        pb_values,
                        pb_ratio,
                        higher_is_better=False,
                    )
                )
            if valuation_percentiles:
                components["valuation_score"] = round(
                    (sum(valuation_percentiles) / len(valuation_percentiles)) * 10.0,
                    4,
                )

        if not preferred_families:
            for factor_name in normalized_active_factors:
                for family in preferred_strategy_types_for_factor(factor_name, default=[]):
                    normalized_family = str(family or "").strip().lower()
                    if normalized_family and normalized_family not in preferred_families:
                        preferred_families.append(normalized_family)
        projected_families = cls._families_for_row(
            row,
            snapshot=snapshot,
            hot_sectors=hot_sector_set,
            cold_sectors=cold_sector_set,
            active_factors=normalized_active_factors,
            allocation_item=None,
        )
        if preferred_families and projected_families:
            preferred_rank = {
                family: index + 1
                for index, family in enumerate(preferred_families)
                if family
            }
            projected_weight_total = sum(1.0 / (index + 1) for index in range(len(projected_families)))
            weighted_overlap = 0.0
            for projected_index, family in enumerate(projected_families, 1):
                preferred_index = preferred_rank.get(family)
                if not preferred_index:
                    continue
                weighted_overlap += (1.0 / projected_index) * (1.0 / preferred_index)
            overlap_ratio = weighted_overlap / max(projected_weight_total, 1e-9)
            components["factor_alignment_score"] = round(max(0.0, min(overlap_ratio, 1.0)) * 8.0, 4)

        allocation_priority = max(0.0, min(cls._safe_float((allocation_item or {}).get("priority")), 1.0))
        allocation_priorities = list(resolved_context.get("allocation_priorities") or [])
        if allocation_priority > 0.0 and allocation_priorities:
            allocation_pct = cls._percentile_from_sorted(
                allocation_priorities,
                allocation_priority,
                higher_is_better=True,
            )
        else:
            allocation_pct = 0.5
        components["allocation_score"] = round((allocation_pct - 0.5) * 8.0, 4)

        # PR-S19：画像分量 - 让 stock_profile 维度真正参与排序
        # 使用 dimension_scores 的关键维度按权重叠加，与现有几个 component 保持同量级。
        profile_summary = cls._extract_profile_summary(row)
        profile_score = 0.0
        profile_quality_score = 0.0
        if profile_summary:
            scores = cls._profile_dimension_scores(profile_summary)
            quality = str(profile_summary.get("profile_quality") or "").lower()
            quality_factor = {"good": 1.0, "partial": 0.7, "low_confidence": 0.4, "failed": 0.0}.get(
                quality, 0.5
            )
            # 与维度对应的权重，覆盖率缺失的维度自动 0
            weighted = (
                scores.get("quality", 0.0) * 1.6
                + scores.get("valuation", 0.0) * 1.4
                + scores.get("trend", 0.0) * 1.2
                + scores.get("growth", 0.0) * 1.0
                + scores.get("volume", 0.0) * 0.6
                + scores.get("reversal", 0.0) * 0.4
                - scores.get("risk", 0.0) * 0.4
            )
            profile_score = round(weighted * quality_factor, 4)
            profile_quality_score = round(quality_factor * 2.0, 4)
        components["stock_profile_score"] = profile_score
        components["profile_quality_score"] = profile_quality_score

        return {key: round(cls._safe_float(value), 4) for key, value in components.items()}

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

        def add(*items: str) -> None:
            for item in items:
                lowered = str(item or "").strip().lower()
                if lowered and lowered not in families:
                    families.append(lowered)

        intrinsic_families = cls._intrinsic_families_for_row(
            row,
            snapshot=snapshot,
            hot_sectors=hot_sectors,
            cold_sectors=cold_sectors,
            active_factors=active_factors,
        )

        router_enabled = cls._effective_router_enabled(snapshot)
        router_strict = cls._effective_router_strict(snapshot)
        if allocation_item and not (router_enabled and router_strict):
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
                source_mode = str(allocation_item.get("source_mode") or "").strip().lower()
                if source_mode.startswith("stock_universe_projection") and intrinsic_families:
                    sector_anchor = next(
                        (
                            family
                            for family in cls._sector_family_biases(
                                row.get("industry") or row.get("sector"),
                                mode="intrinsic",
                            )
                            if str(family or "").strip()
                        ),
                        intrinsic_families[0],
                    )
                    # Keep one industry-driven anchor so projection-covered leaders do not all collapse
                    # into the same allocation trio.
                    add(sector_anchor)
                    add(*allocation_families)
                    add(*intrinsic_families[1:])
                else:
                    add(*allocation_families)
                    add(*intrinsic_families)
                return families[: max(1, STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK)]
        add(*intrinsic_families)

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
        router_enabled = cls._effective_router_enabled(snapshot)
        router_strict = cls._effective_router_strict(snapshot)
        if allocation_plans and not (router_enabled and router_strict):
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

    # ------------------------------------------------------------------
    # PR-S19：画像驱动的 holding_window / risk_level / 参数 band
    # ------------------------------------------------------------------

    @classmethod
    def _holding_window_with_profile(
        cls,
        family: str,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = dict(cls._holding_window_for_family(family))
        if not profile_summary:
            return base
        scores = cls._profile_dimension_scores(profile_summary)
        risk = scores.get("risk", 0.0)
        trend = scores.get("trend", 0.0)
        # 高波动 / 高换手：缩短持仓上限；低波动 / 趋势稳健：放宽上限
        min_days = max(2, int(base.get("min_days") or 5))
        max_days = max(min_days + 1, int(base.get("max_days") or 20))
        if risk >= 0.6:
            max_days = max(min_days + 1, int(max_days * 0.7))
        elif risk <= 0.25 and trend >= 0.4:
            max_days = int(max_days * 1.25)
        return {"min_days": min_days, "max_days": max_days}

    @classmethod
    def _risk_level_with_profile(
        cls,
        family: str,
        profile_summary: dict[str, Any] | None,
    ) -> str:
        base = cls._risk_level_for_family(family)
        if not profile_summary:
            return base
        scores = cls._profile_dimension_scores(profile_summary)
        risk = scores.get("risk", 0.0)
        if risk >= 0.7:
            return "high"
        if risk <= 0.2 and scores.get("quality", 0.0) >= 0.5:
            return "low"
        return base

    @classmethod
    def _alpha_source_with_profile(
        cls,
        family: str,
        profile_summary: dict[str, Any] | None,
    ) -> str:
        base = cls._alpha_source_for_family(family)
        if not profile_summary:
            return base
        coverage = dict(profile_summary.get("feature_coverage") or {})
        # 如果事件 coverage missing，但 family 想用 event：降级到 multi_factor
        if base == "event" or family == "event_structure_breakout":
            event_cov = str(coverage.get("event_news_notice_research_theme") or "").lower()
            if event_cov not in {"ok", "partial"}:
                return "multi_factor"
        return base

    @classmethod
    def _param_band_for_profile(
        cls,
        family: str,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """根据画像维度分数给出 family 的参数微调 band。

        返回结构示例：
            {
              "lookback_days": {"min": 14, "max": 36, "preferred": 24},
              "risk_budget": {"min": 0.02, "max": 0.05, "preferred": 0.035},
              "rsi_overbought": {...},
              "_profile_quality": "partial",
            }

        下游 `_expand_bulk_rule_specs` / `param_search_space` 消费时
        以 `preferred` 为种子点，`min/max` 为采样区间。
        """

        normalized_family = str(family or "").strip().lower()
        if not profile_summary:
            return {}

        scores = cls._profile_dimension_scores(profile_summary)
        quality = str(profile_summary.get("profile_quality") or "").lower()
        quality_factor = {"good": 1.0, "partial": 0.75, "low_confidence": 0.5, "failed": 0.3}.get(
            quality, 0.6
        )

        risk = scores.get("risk", 0.0)
        trend = scores.get("trend", 0.0)
        reversal = scores.get("reversal", 0.0)
        volume = scores.get("volume", 0.0)

        # 通用 lookback：高波动/高反转→更短 lookback；低波动/强趋势→更长 lookback
        base_min, base_max = 14, 36
        if normalized_family in {"rsi", "mean_reversion_short", "gap_fill"}:
            base_min, base_max = 4, 14
        elif normalized_family in {"value_factor", "quality_factor", "growth_factor", "multi_factor"}:
            base_min, base_max = 20, 60
        elif normalized_family in {"momentum", "ma_cross"}:
            base_min, base_max = 12, 36

        skew = (trend - reversal) * 0.3 - risk * 0.25
        center_shift = round((base_max - base_min) * skew, 1)
        lo = max(2, int(base_min + center_shift * 0.4))
        hi = max(lo + 2, int(base_max + center_shift * 0.6))
        preferred = (lo + hi) // 2

        # risk_budget：高波动/低质量 → 收紧
        rb_min, rb_max = 0.015, 0.06
        rb_preferred = 0.035
        if risk >= 0.6:
            rb_preferred = 0.020
            rb_max = 0.040
        elif risk <= 0.25:
            rb_preferred = 0.045
            rb_max = 0.070
        rb_min = round(rb_min * quality_factor, 4)
        rb_preferred = round(rb_preferred * quality_factor, 4)

        band: dict[str, Any] = {
            "lookback_days": {"min": lo, "max": hi, "preferred": preferred},
            "risk_budget": {
                "min": max(0.005, rb_min),
                "max": rb_max,
                "preferred": rb_preferred,
            },
            "_profile_quality": quality or "unknown",
            "_dimension_scores": dict(scores),
        }

        # family 特异参数 band
        if normalized_family in {"rsi", "mean_reversion_short"}:
            # 反转家族：reversal 高时拉宽 oversold/overbought
            ext = 5 + int(reversal * 10)
            band["rsi_overbought"] = {
                "min": 65 + ext // 2,
                "max": 80 + ext,
                "preferred": 70 + ext // 2,
            }
            band["rsi_oversold"] = {
                "min": 20 - ext // 2,
                "max": 35 - ext // 2,
                "preferred": 30 - ext // 2,
            }
        if normalized_family in {"momentum", "ma_cross"}:
            # 动量/均线：volume 强时偏短均线
            fast = max(5, int(10 - volume * 3))
            slow = max(fast + 3, int(30 - trend * 5))
            band["fast_window"] = {"min": fast - 1, "max": fast + 3, "preferred": fast}
            band["slow_window"] = {"min": slow - 3, "max": slow + 5, "preferred": slow}

        return band

    @staticmethod
    def _merge_param_search_space(
        family_default: dict[str, Any] | None,
        profile_band: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """合并 family 默认参数空间与 profile 提供的 band。

        合并规则：profile_band 中 ``_`` 开头的元数据键（如 _profile_quality）
        会原样保留；其他参数键如果同时出现在两边，profile_band 的 min/max/preferred 覆盖 default。
        """

        merged: dict[str, Any] = {}
        for source in (family_default or {}, profile_band or {}):
            if not isinstance(source, Mapping):
                continue
            for key, value in source.items():
                if key.startswith("_"):
                    merged[key] = value
                    continue
                if isinstance(value, Mapping):
                    existing = dict(merged.get(key) or {})
                    existing.update(dict(value))
                    merged[key] = existing
                else:
                    merged[key] = value
        return merged

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
