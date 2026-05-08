
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
        signal_candidates += self._expand_signal_variants(snapshot, signal_candidates)
        quota_candidates = self._fill_gaps(snapshot, signal_candidates)
        candidates = [
            self._materialize_candidate_identity(self._apply_snapshot_target_alignment(candidate, snapshot), snapshot, idx)
            for idx, candidate in enumerate([*signal_candidates, *quota_candidates])
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

    @classmethod
    def _materialize_candidate_identity(cls, candidate: dict, snapshot: dict, slot_index: int) -> dict:
        item = dict(candidate or {})
        strategy_type = str(item.get("strategy_type") or "").strip().lower()
        if not strategy_type:
            return item
        targets = _normalize_target_codes(
            [
                item.get("target_symbols"),
                item.get("requested_target_symbols"),
                item.get("stock_pool"),
                dict(item.get("research_task") or {}).get("target_symbols"),
                dict(item.get("research_task") or {}).get("stock_pool"),
            ],
            limit=20,
        )
        seed_context = {
            "snapshot_date": dict(snapshot or {}).get("date") or dict(snapshot or {}).get("snapshot_date") or dict(snapshot or {}).get("as_of"),
            "source": dict(item.get("generation_reason") or {}).get("source") or item.get("parameter_source"),
            "spawn_reason": item.get("spawn_reason"),
            "generation_reason": dict(item.get("generation_reason") or {}),
        }
        params = materialize_strategy_params(
            strategy_type,
            dict(item.get("params") or {}),
            seed_context=seed_context,
            slot_index=slot_index,
            targets=targets,
            variant_existing=True,
            refresh_signal_rule=True,
        )
        item["params"] = params
        item["strategy_instance_hash"] = params.get("strategy_instance_hash")
        item["tested_object_hash"] = params.get("tested_object_hash")
        item["candidate_contract_hash"] = params.get("candidate_contract_hash")
        item["parameter_source"] = params.get("parameter_source")
        return item

    def _build_signal_batches(self, snapshot: dict) -> Dict[str, List[dict]]:
        return {
            "event_driven": self._from_event_driven(snapshot),
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

        for source in ("event_driven", "fear_greed", "factor_ic", "volatility", "fund_flow"):
            items = list(source_batches.get(source) or [])
            weight = float(source_weights.get(source, 1.0) or 0.0)
            if source in {"event_driven", "factor_ic"}:
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
        target_coverage = 12 if SPAWNER_TARGET_TOTAL >= 16 else 8
        if completion_ratio < 1.0:
            target_total = min(target_total, max(4, int(round(SPAWNER_TARGET_TOTAL * 0.75))))
        budget = max(0, target_total - max(0, int(signal_candidate_count or 0)))
        if event_ready:
            if signal_candidate_count <= 0 or not StrategySpawner._event_ready_supports_local_fill(snapshot):
                return 0
            return min(budget, SPAWNER_EVENT_FILL_BUDGET_MAX)
        if signal_candidate_count <= 0 and not has_historical_distribution:
            return min(budget, max(1, target_coverage))
        return min(budget, max(SPAWNER_FILL_BUDGET_MAX, target_coverage))

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
            out.append(self._make("volatility_breakout", {"lookback": 20, "threshold": 0.022}, f"恐贪{fear_greed}，中性波动突破", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("quality_factor", {"lookback": 72, "buy_quantile": 0.82, "sell_quantile": 0.18}, f"恐贪{fear_greed}，中性质量精选", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("sector_rotation", {"lookback": 20, "factor_weights": {"momentum": 0.45, "quality": 0.30, "value": 0.25}}, f"恐贪{fear_greed}，中性行业轮动", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
            out.append(self._make("north_capital_track", {"lookback": 15, "threshold": 0.015}, f"恐贪{fear_greed}，中性北向跟踪", source="fear_greed", trigger_signal={"field": "fear_greed_index", "value": fear_greed, "level": "neutral"}, trigger_thresholds=[self._threshold("fear_greed_index", ">=", 30, fear_greed, "恐贪下界"), self._threshold("fear_greed_index", "<=", 70, fear_greed, "恐贪上界")]))
        return out
