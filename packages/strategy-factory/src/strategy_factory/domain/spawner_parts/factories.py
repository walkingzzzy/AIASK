
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

        target_pool_source = str(item.get("target_pool_source") or "").strip().lower() or None
        target_symbols = cls._event_anchor_target_symbols(
            strategy_type,
            item,
            snapshot,
            limit=max(1, cls._snapshot_target_symbol_budget(strategy_type)),
        )
        if target_symbols:
            target_pool_source = "event_anchor"
        if not target_symbols and strategy_type != "event_structure_breakout":
            target_symbols = cls._snapshot_target_symbols(strategy_type, snapshot)
            if target_symbols:
                target_pool_source = "explicit_task"
        if not target_symbols:
            target_symbols = cls._focus_industry_target_symbols(
                strategy_type,
                item,
                snapshot,
                limit=max(1, cls._snapshot_target_symbol_budget(strategy_type)),
            )
            if target_symbols:
                target_pool_source = "static_fallback"
        if not target_symbols:
            return item

        candidate_family = str(item.get("candidate_family") or strategy_type).strip().lower() or strategy_type
        focus_industries = cls._normalize_text_list(
            dict(item.get("event_prefilter") or {}).get("focus_industries"),
            dict(item.get("research_task") or {}).get("focus_industries"),
            dict(snapshot or {}).get("hot_sectors"),
            limit=3,
        )
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
            "focus_industries": list(focus_industries),
            "preference_strength": "soft",
            "preference_reason": f"snapshot_local_spawn:{strategy_type}",
            "gate_1_representative_count": min(3, len(target_symbols)),
            "synthetic_local_spawn": True,
            "target_pool_source": target_pool_source or "explicit_task",
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
            "target_pool_source": target_pool_source or "explicit_task",
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
        signal_candidates, signal_feedback_summary = self._apply_family_feedback_to_signal_candidates(
            snapshot,
            signal_candidates,
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
            signal_feedback_summary=signal_feedback_summary,
        )
        return candidates

    def _build_signal_batches(self, snapshot: dict) -> Dict[str, List[dict]]:
        return {
            "event_driven": self._from_event_driven(snapshot),
            "fear_greed": self._from_fear_greed(snapshot),
            "factor_ic": self._from_factor_ic(snapshot),
            "factor_pool": self._from_factor_pool(snapshot),
            "volatility": self._from_volatility(snapshot),
            "fund_flow": self._from_fund_flow(snapshot),
        }

    def _apply_family_feedback_to_signal_candidates(
        self,
        snapshot: dict,
        signal_candidates: List[dict],
    ) -> tuple[List[dict], dict]:
        candidates = [dict(item or {}) for item in list(signal_candidates or []) if isinstance(item, dict)]
        if not candidates:
            return [], {
                "signal_feedback_limited_count": 0,
                "signal_feedback_limited_type_counts": {},
                "signal_feedback_factor_by_type": {},
            }

        type_counts: Dict[str, int] = {}
        type_labels: Dict[str, str] = {}
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "").strip()
            if not strategy_type:
                continue
            normalized = strategy_type.lower()
            type_counts[normalized] = type_counts.get(normalized, 0) + 1
            type_labels.setdefault(normalized, strategy_type)

        allowed_by_type: Dict[str, int] = {}
        factor_by_type: Dict[str, float] = {}
        for normalized, count in type_counts.items():
            label = type_labels.get(normalized, normalized)
            factor = self._family_negative_feedback_factor(label, snapshot)
            factor_by_type[normalized] = factor
            if factor >= 1.0:
                allowed_by_type[normalized] = count
            elif factor <= 0:
                allowed_by_type[normalized] = 0
            else:
                allowed_by_type[normalized] = max(0, int(round(count * factor)))

        kept: List[dict] = []
        kept_counts: Dict[str, int] = {}
        filtered_counts: Dict[str, int] = {}
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "").strip()
            normalized = strategy_type.lower()
            if not normalized:
                kept.append(item)
                continue
            allowed = allowed_by_type.get(normalized, type_counts.get(normalized, 0))
            current = kept_counts.get(normalized, 0)
            if current < allowed:
                kept.append(item)
                kept_counts[normalized] = current + 1
                continue
            filtered_counts[strategy_type] = filtered_counts.get(strategy_type, 0) + 1

        limited_factors = {
            type_labels.get(normalized, normalized): round(float(factor), 4)
            for normalized, factor in factor_by_type.items()
            if factor < 1.0
        }
        return kept, {
            "signal_feedback_limited_count": sum(filtered_counts.values()),
            "signal_feedback_limited_type_counts": filtered_counts,
            "signal_feedback_factor_by_type": limited_factors,
        }

    @staticmethod
    def _event_ready_source_cap(*, event_ready_supplemental: bool) -> int:
        return max(0, SPAWNER_EVENT_SOURCE_BASE_CAP + (SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS if event_ready_supplemental else 0))

    @staticmethod
    def _event_ready_source_weights(*, event_ready_supplemental: bool) -> Dict[str, float]:
        return get_event_ready_source_weights(
            event_ready_supplemental=event_ready_supplemental
        )

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
                *list(source_batches.get("event_driven") or []),
                *list(source_batches.get("fear_greed") or []),
                *list(source_batches.get("factor_ic") or []),
                *list(source_batches.get("factor_pool") or []),
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

        for source in ("event_driven", "fear_greed", "factor_ic", "factor_pool", "volatility", "fund_flow"):
            items = list(source_batches.get(source) or [])
            weight = float(source_weights.get(source, 1.0) or 0.0)
            if source in {"event_driven", "factor_ic", "factor_pool"}:
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
            *capped_batches["event_driven"],
            *capped_batches["fear_greed"],
            *capped_batches["factor_ic"],
            *capped_batches["factor_pool"],
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
            add("event_structure_breakout", "growth_factor", "quality_factor", "north_capital_track", "sector_rotation", "volatility_breakout")
        else:
            add("event_structure_breakout", "quality_factor", "north_capital_track", "sector_rotation", "gap_fill", "ma_cross")

        north_3d = float(snapshot.get("north_fund_3d_net") or 0.0)
        if north_3d >= 5_000_000_000:
            add("north_capital_track", "quality_factor", "growth_factor", "sector_rotation")
        elif north_3d <= -5_000_000_000:
            add("value_factor", "macro_timing", "rsi", "quality_factor")

        margin_5d = float(snapshot.get("margin_5d_change_pct") or 0.0)
        if margin_5d >= 2.0:
            add("event_structure_breakout", "volatility_breakout", "sector_rotation", "north_capital_track")
        elif margin_5d <= -2.0:
            add("rsi", "gap_fill", "value_factor")

        add(*cls._factor_preferred_strategy_types(snapshot))

        event_driven = dict(snapshot.get("event_driven") or {})
        if int(event_driven.get("event_count") or 0) > 0 or int(event_driven.get("tasks_ready_count") or 0) > 0:
            add("event_structure_breakout", "quality_factor", "north_capital_track", "sector_rotation", "gap_fill")

        if not preferred:
            add("event_structure_breakout", "quality_factor", "north_capital_track", "gap_fill", "ma_cross")

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

    @staticmethod
    def _family_negative_feedback_factor(strategy_type: str, snapshot: dict) -> float:
        family_feedback = dict((snapshot or {}).get("family_gate_feedback") or {})
        normalized_type = str(strategy_type or "").strip().lower()
        if not normalized_type:
            return 1.0
        entry = dict(
            family_feedback.get(normalized_type)
            or family_feedback.get(str(strategy_type or "").strip())
            or {}
        )
        if not entry:
            return 1.0
        try:
            ema = float(entry.get("ema_submit_count") or 0.0)
        except (TypeError, ValueError):
            ema = 1.0
        try:
            raw_failure_rate = entry.get("gate_failure_rate")
            if raw_failure_rate is None:
                raw_failure_rate = entry.get("submission_gate_failure_rate")
            gate_failure_rate = float(raw_failure_rate or 0.0)
        except (TypeError, ValueError):
            gate_failure_rate = 0.0
        if bool(entry.get("freeze_active")):
            return 0.0
        if bool(entry.get("suppressed")) or bool(entry.get("suppress_active")):
            return 0.15
        if bool(entry.get("cooldown_active")) or gate_failure_rate >= 0.95:
            return 0.25
        if gate_failure_rate >= 0.75:
            return 0.5
        if ema >= 1.0:
            return 1.0
        if ema >= 0.3:
            return 0.6
        return 0.25

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
            # PR-S12: 按负反馈系数缩减（最少 0，跳过该 type）
            feedback_factor = self._family_negative_feedback_factor(strategy_type, snapshot)
            desired_variants = max(0, int(round(desired_variants * feedback_factor)))
            if generation_cap is not None:
                desired_variants = min(desired_variants, max(0, generation_cap - existing_total_for_type))
            if desired_variants <= 0:
                continue
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
            out.append(
                self._make(
                    "margin_divergence",
                    self._high_precision_margin_divergence_params(),
                    f"恐贪{fear_greed}，高精度流动性背离修复",
                    source="fear_greed",
                    trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"},
                    trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")],
                    extras=self._high_precision_candidate_fields(
                        preferred_regime="liquidity_repair_with_volume_reexpansion",
                        avoid_regime="volume_vacuum_or_failed_rebound",
                        holding_rationale="只在恐慌释放后出现缩量止跌、放量修复和结构转强共振时参与，避免把普通反抽误当成修复。",
                        failure_mode={
                            "primary_failure_mode": "failed_rebound_after_liquidity_dryup",
                            "secondary_failure_mode": "false_reexpansion",
                        },
                        entry_bias="liquidity_divergence_repair_confirmation",
                        exit_bias="liquidity_break_or_time_stop",
                    ),
                )
            )
            out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，恐惧期精选价值", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "fear"}, trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fear_greed, "恐贪阈值")]))
        elif fear_greed > 70:
            out.append(self._make("momentum", {"lookback": 5, "threshold": 0.01}, f"恐贪{fear_greed}，贪婪期短周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("momentum", {"lookback": 10, "threshold": 0.02}, f"恐贪{fear_greed}，贪婪期中周期动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
            out.append(self._make("growth_factor", {"lookback": 40, "buy_quantile": 0.85, "sell_quantile": 0.15}, f"恐贪{fear_greed}，贪婪期成长加速", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "greed"}, trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fear_greed, "恐贪阈值")]))
        else:
            out.append(self._make("ma_cross", {"short_period": 5, "long_period": 20}, f"恐贪{fear_greed}，中性标准均线", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("momentum", {"lookback": 20, "threshold": 0.02}, f"恐贪{fear_greed}，中性标准动量", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
        return out
