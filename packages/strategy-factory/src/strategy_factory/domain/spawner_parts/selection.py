
    @staticmethod
    def _high_precision_candidate_fields(
        *,
        preferred_regime: str,
        avoid_regime: str,
        holding_rationale: str,
        failure_mode: dict,
        entry_selectivity: str = "strict",
        trade_density_preference: str = "low",
        slippage_bps: float = 4.0,
        max_position_pct: float = 0.12,
        capacity_bucket: str = "small",
        min_days: int = 2,
        max_days: int = 8,
        entry_bias: str = "oversold_repair_with_mean_reversion_confirmation",
        exit_bias: str = "mean_reversion_completion_or_rsi_reset",
        event_prefilter: Optional[dict] = None,
        candidate_origin: str = "research_signal",
        event_anchor: Optional[dict[str, Any]] = None,
        target_pool_source: str = "explicit_task",
    ) -> dict:
        event_prefilter_payload = dict(event_prefilter or {})
        resolved_event_anchor = dict(
            event_anchor
            or event_prefilter_payload.get("event_anchor")
            or {}
        )
        cost_grid = {
            "base_case": {
                "commission_rate": 0.00025,
                "slippage_bps": slippage_bps,
                "tradability_filter": True,
                "slippage_model": "fixed",
                "market_impact_bps": 1.0,
            },
            "stress_cases": [
                {
                    "label": "base_plus_50pct_cost",
                    "commission_rate": 0.000375,
                    "slippage_bps": round(slippage_bps * 1.5, 2),
                }
            ],
            "source": "snapshot_local_high_precision",
        }
        validation_profile = {
            "profile": "trade_rule_validation",
            "validation_focus": "candidate_target_only",
            "primary_validation_layer": "target",
            "objective_profile": "high_precision",
            "trade_density_preference": trade_density_preference,
            "regime_required": True,
            "cost_robust_required": True,
            "entry_selectivity": entry_selectivity,
            "preferred_regime": preferred_regime,
            "avoid_regime": avoid_regime,
            "event_prefilter_required": bool(event_prefilter_payload.get("required")),
            "event_prefilter_profile": str(event_prefilter_payload.get("profile") or "").strip() or None,
            "event_prefilter_min_confirmations": (
                int(event_prefilter_payload.get("min_confirmations") or 0)
                if event_prefilter_payload.get("min_confirmations") is not None
                else None
            ),
        }
        hypothesis_artifact = {
            "objective_profile": "high_precision",
            "trade_density_preference": trade_density_preference,
            "entry_selectivity": entry_selectivity,
            "holding_rationale": holding_rationale,
            "failure_mode": dict(failure_mode or {}),
            "cost_sensitivity_grid": dict(cost_grid),
            "capacity_assumption": {
                "max_position_pct": max_position_pct,
                "capacity_bucket": capacity_bucket,
                "symbol_count": 4,
            },
            "market_regime_assumption": {
                "preferred_regime": preferred_regime,
                "avoid_regime": avoid_regime,
            },
            "cost_robust_required": True,
            "event_prefilter": dict(event_prefilter_payload),
            "event_anchor": dict(resolved_event_anchor),
        }
        tags = ["high_precision", "regime_required"]
        if event_prefilter_payload.get("required"):
            tags.append("event_prefilter_required")
        return {
            "validation_profile": validation_profile,
            "holding_horizon": {
                "min_days": min_days,
                "max_days": max_days,
                "expected_turnover_band": trade_density_preference,
            },
            "trade_plan": {
                "entry_bias": entry_bias,
                "exit_bias": exit_bias,
            },
            "holding_rationale": holding_rationale,
            "failure_mode": dict(failure_mode or {}),
            "cost_sensitivity_grid": dict(cost_grid),
            "capacity_assumption": {
                "max_position_pct": max_position_pct,
                "capacity_bucket": capacity_bucket,
                "symbol_count": 4,
            },
            "market_regime_assumption": {
                "summary": holding_rationale,
                "preferred_regime": preferred_regime,
                "avoid_regime": avoid_regime,
            },
            "hypothesis_artifact": hypothesis_artifact,
            "event_prefilter": dict(event_prefilter_payload),
            "candidate_origin": str(candidate_origin or "research_signal").strip() or "research_signal",
            "event_anchor": dict(resolved_event_anchor),
            "target_pool_source": str(target_pool_source or "explicit_task").strip() or "explicit_task",
            "tags": tags,
        }

    @staticmethod
    def _high_precision_margin_divergence_params() -> dict:
        return {
            "fear_threshold": 43,
            "greed_threshold": 60,
            "lookback": 12,
            "rebound_window": 3,
            "repair_drawdown_floor": -0.06,
            "repair_rebound_pct": 0.012,
            "dryup_window": 3,
            "dryup_max_ratio": 0.9,
            "liquidity_window": 8,
            "entry_volume_floor_ratio": 1.0,
            "structure_window": 4,
            "structure_close_location_min": 0.58,
            "structure_body_return_min": 0.002,
            "max_hold_bars": 8,
            "adverse_volume_break_ratio": 0.72,
            "adverse_close_break_pct": -0.012,
            "max_active_symbols": 2,
            "universe_selection_profile": "liquidity_divergence_fit_v1",
        }

    @staticmethod
    def _high_precision_event_structure_breakout_params() -> dict:
        return {
            "breakout_window": 12,
            "breakout_buffer_pct": 0.002,
            "contraction_window": 5,
            "contraction_max_range_ratio": 0.06,
            "volume_window": 8,
            "breakout_volume_ratio_min": 1.0,
            "structure_window": 4,
            "structure_close_location_min": 0.62,
            "structure_body_return_min": 0.003,
            "event_impulse_window": 5,
            "event_impulse_threshold": 0.015,
            "max_hold_bars": 8,
            "breakout_failure_close_buffer": -0.012,
            "adverse_volume_ratio_max": 0.85,
            "max_active_symbols": 3,
            "universe_selection_profile": "event_structure_breakout_fit_v1",
            "event_prefilter_enabled": True,
            "event_prefilter_profile": "announcement_flow_sector_v1",
            "event_prefilter_min_confirmations": 1,
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
        signal_feedback_summary: Optional[dict] = None,
    ) -> dict:
        source_counts: Dict[str, int] = {}
        strategy_type_counts: Dict[str, int] = {}
        quota_fill_count = 0
        signal_trigger_count = 0
        threshold_hit_count = 0
        parameter_source_counts: Dict[str, int] = {}
        quota_fill_mode_counts: Dict[str, int] = {}
        quota_fill_quality_counts: Dict[str, int] = {}
        quota_fill_feedback_limited_count = 0
        quota_fill_feedback_limited_type_counts: Dict[str, int] = {}
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
                if bool(fill_meta.get("feedback_limited")):
                    quota_fill_feedback_limited_count += 1
                    quota_fill_feedback_limited_type_counts[strategy_type] = (
                        quota_fill_feedback_limited_type_counts.get(strategy_type, 0) + 1
                    )
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
        signal_feedback = dict(signal_feedback_summary or {})
        trimmed_count = sum(
            max(0, int(raw_counts.get(source, 0) or 0) - int(source_counts.get(source, 0) or 0))
            for source in raw_counts
        )
        trend_cluster_count = StrategySpawner._trend_cluster_count(candidates)
        diversification_debt = StrategySpawner._diversification_debt(candidates)
        return {
            "summary": {
                "policy_version": get_spawn_policy_version(),
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
                "signal_feedback_limited_count": int(signal_feedback.get("signal_feedback_limited_count") or 0),
                "signal_feedback_limited_type_counts": dict(
                    signal_feedback.get("signal_feedback_limited_type_counts") or {}
                ),
                "signal_feedback_factor_by_type": dict(
                    signal_feedback.get("signal_feedback_factor_by_type") or {}
                ),
                "parameter_source_counts": parameter_source_counts,
                "historical_distribution_count": int(parameter_source_counts.get("historical_distribution") or 0),
                "quota_fill_mode_counts": quota_fill_mode_counts,
                "quota_fill_quality_counts": quota_fill_quality_counts,
                "quota_fill_feedback_limited_count": quota_fill_feedback_limited_count,
                "quota_fill_feedback_limited_type_counts": quota_fill_feedback_limited_type_counts,
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
        except (TypeError, ValueError):
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

    @staticmethod
    def _is_tradable_target_code(code: str) -> bool:
        """PR-U1: 判断股票代码是否适合作为策略目标。

        排除：
        - 北交所（920xxx、8xxxxx）—— 流动性极差
        - B 股（200xxx、900xxx）—— 外币计价
        """
        c = str(code or "").strip()
        if not c or len(c) < 6:
            return False
        if c.startswith("920") or c.startswith("8"):
            return False
        if c.startswith("200") or c.startswith("900"):
            return False
        return True

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

            # PR-U1: 排除不适合做策略目标的股票（北交所、B股、老三板）
            if not cls._is_tradable_target_code(code):
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
