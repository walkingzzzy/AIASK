
    def _from_factor_pool(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        factor_research = dict(snapshot.get("factor_research") or {})
        pool_payload = dict(
            factor_research.get("factory_pool_payload")
            or snapshot.get("factory_pool_payload")
            or {}
        )
        factors = [
            dict(item or {})
            for item in list(
                pool_payload.get("factors")
                or factor_research.get("factory_pool_factors")
                or snapshot.get("factory_pool_factors")
                or []
            )
            if isinstance(item, dict)
        ]

        for factor in factors[:8]:
            factor_id = str(factor.get("factor_id") or "").strip()
            factor_name = str(
                factor.get("name")
                or factor.get("factor_name")
                or factor_id
            ).strip()
            factor_dsl = str(
                factor.get("expression_dsl")
                or factor.get("factor_dsl")
                or factor.get("dsl")
                or ""
            ).strip()
            if not factor_id or not factor_name or not factor_dsl:
                continue

            family = str(factor.get("family") or factor_name).strip().lower()
            strategy_types = preferred_strategy_types_for_factor(
                family or factor_name,
                default=["multi_factor"],
            )
            strategy_type = str((strategy_types or ["multi_factor"])[0] or "multi_factor")
            fitness = self._safe_float(factor.get("fitness"))
            decay_rate = self._safe_float(factor.get("decay_rate"))
            current_ic = self._safe_float(factor.get("current_ic"))
            grade = str(factor.get("admission_grade") or factor.get("grade") or "").strip()
            engine = str(factor.get("generation_engine") or "").strip()
            params = {
                "factor_dsl": factor_dsl,
                "factor_name": factor_name,
                "fitness": fitness,
                "grade": grade,
                "engine": engine,
                "factor_pool_factor_id": factor_id,
                "factor_pool_fitness": fitness,
                "factor_pool_grade": grade,
                "factor_pool_engine": engine,
                "factor_pool_current_ic": current_ic,
                "factor_pool_decay_rate": decay_rate,
                "lookback": int(factor.get("expected_holding_period") or 60),
            }
            if strategy_type == "multi_factor":
                params["factor_weights"] = {factor_name: 1.0}
            extras = {
                "candidate_origin": "factor_pool",
                "candidate_family": family or strategy_type,
                "factor_pool_factor_id": factor_id,
                "metadata": {
                    "factor_pool_factor_id": factor_id,
                    "factor_pool_factor_name": factor_name,
                },
                "factor_pool_metadata": {
                    "factor_id": factor_id,
                    "factor_name": factor_name,
                    "family": family,
                    "fitness": fitness,
                    "grade": grade,
                    "engine": engine,
                    "current_ic": current_ic,
                    "decay_rate": decay_rate,
                },
                "tags": ["factor_pool", "active_factor_pool"],
            }
            out.append(
                self._make(
                    strategy_type,
                    params,
                    f"active factor pool: {factor_name}",
                    source="factor_pool",
                    trigger_signal={
                        "field": "factor_pool",
                        "factor_id": factor_id,
                        "factor_name": factor_name,
                        "fitness": fitness,
                        "current_ic": current_ic,
                    },
                    trigger_thresholds=[
                        self._threshold(
                            f"factor_pool.{factor_name}.fitness",
                            ">",
                            0.0,
                            fitness,
                            "active pool factor",
                        )
                    ],
                    extras=extras,
                )
            )
        return out

    def _from_factor_ic(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        factor_ic, trend = self._factor_maps(snapshot)

        for factor_name, ic_value in factor_ic.items():
            trend_value = trend.get(factor_name, "flat")
            if ic_value > 0.03 and trend_value == "rising":
                if factor_name == "momentum":
                    event_prefilter = self._snapshot_event_prefilter(
                        snapshot,
                        source="factor_ic",
                        trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value},
                    )
                    if event_prefilter.get("passed"):
                        out.append(
                            self._make(
                                "event_structure_breakout",
                                self._high_precision_event_structure_breakout_params(),
                                f"momentum IC={ic_value:.3f}上升，事件锚确认后高精度事件结构突破",
                                source="factor_ic",
                                trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value},
                                trigger_thresholds=[
                                    self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"),
                                    self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值"),
                                ],
                                extras=self._high_precision_candidate_fields(
                                    preferred_regime="event_follow_through_with_structure_confirmation",
                                    avoid_regime="false_breakout_or_post_event_mean_reversion",
                                    holding_rationale="只在催化或强势脉冲后经历缩量整理并放量突破时参与，优先结构延续而不是普通趋势追涨。",
                                    failure_mode={
                                        "primary_failure_mode": "false_breakout_after_event_impulse",
                                        "secondary_failure_mode": "late_entry_after_extension",
                                    },
                                    entry_selectivity="strict_event_breakout",
                                    max_position_pct=0.14,
                                    capacity_bucket="mid",
                                    min_days=3,
                                    max_days=12,
                                    entry_bias="event_structure_breakout_confirmation",
                                    exit_bias="breakout_failure_or_time_stop",
                                    event_prefilter=event_prefilter,
                                    candidate_origin="research_signal",
                                    event_anchor=dict(event_prefilter.get("event_anchor") or {}),
                                    target_pool_source=(
                                        "event_anchor"
                                        if self._event_anchor_has_explicit_source(event_prefilter.get("event_anchor"))
                                        else "static_fallback"
                                    ),
                                ),
                            )
                        )
                    for lookback in [5, 10, 20]:
                        out.append(self._make("momentum", {"lookback": lookback, "threshold": 0.02}, f"momentum IC={ic_value:.3f}上升，{lookback}日动量", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "value":
                    out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"value IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "quality":
                    out.append(self._make("quality_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}, f"quality IC={ic_value:.3f}上升", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")]))
                elif factor_name == "reversal":
                    out.append(self._make("margin_divergence", self._high_precision_margin_divergence_params(), f"reversal IC={ic_value:.3f}上升，高精度流动性修复", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", ">", 0.03, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "rising", trend_value, "趋势阈值")], extras=self._high_precision_candidate_fields(preferred_regime="liquidity_repair_with_volume_reexpansion", avoid_regime="volume_vacuum_or_failed_rebound", holding_rationale="只有在中期下跌后出现缩量止跌、放量修复和结构转强时才参与，避免把普通噪声反抽误当成高精度修复。", failure_mode={"primary_failure_mode": "factor_reversal_false_positive", "secondary_failure_mode": "false_reexpansion"}, entry_bias="liquidity_divergence_repair_confirmation", exit_bias="liquidity_break_or_time_stop")))
            elif ic_value < -0.02 and trend_value == "falling" and factor_name == "momentum":
                out.append(self._make("margin_divergence", self._high_precision_margin_divergence_params(), f"momentum IC={ic_value:.3f}下降，转高精度流动性修复", source="factor_ic", trigger_signal={"field": "factor_ic", "factor": factor_name, "value": ic_value, "trend": trend_value}, trigger_thresholds=[self._threshold(f"factor_ic.{factor_name}", "<", -0.02, ic_value, "IC阈值"), self._threshold(f"factor_ic_trend.{factor_name}", "==", "falling", trend_value, "趋势阈值")], extras=self._high_precision_candidate_fields(preferred_regime="liquidity_repair_with_volume_reexpansion", avoid_regime="volume_vacuum_or_failed_rebound", holding_rationale="只有在趋势衰减后出现缩量止跌与放量修复共振时才参与，避免追着噪声做均值回归。", failure_mode={"primary_failure_mode": "trend_break_without_repair", "secondary_failure_mode": "overtrading"}, entry_bias="liquidity_divergence_repair_confirmation", exit_bias="liquidity_break_or_time_stop")))

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
            out.append(self._make("macro_timing", {"fear_threshold": 24, "greed_threshold": 74, "lookback": 36}, f"波动率{volatility}，高精度宏观择时", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, volatility, "波动率阈值")], extras=self._high_precision_candidate_fields(preferred_regime="panic_repair_with_volatility_stabilization", avoid_regime="mid_regime_whipsaw", holding_rationale="只有在高波动后恐慌修复且波动结构开始稳定时才入场，避免宏观噪声来回打脸。", failure_mode={"primary_failure_mode": "regime_whipsaw", "secondary_failure_mode": "late_entry_after_volatility_spike"}, max_position_pct=0.14, capacity_bucket="mid", min_days=6, max_days=24, entry_bias="panic_repair_after_regime_confirmation", exit_bias="greed_extreme_or_regime_break")))
        elif volatility > 65:
            out.append(self._make("ma_cross", {"short_period": 3, "long_period": 15}, f"波动率{volatility}，低波动短周期均线", source="volatility", trigger_signal={"field": "fg_components.volatility", "value": volatility}, trigger_thresholds=[self._threshold("fg_components.volatility", ">", 65, volatility, "波动率阈值")]))
        return out

    def _from_event_driven(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        event_driven = dict(snapshot.get("event_driven") or {})
        events = [dict(item or {}) for item in list(event_driven.get("events") or []) if isinstance(item, dict)]
        for event in events[:4]:
            event_id = str(event.get("event_id") or "").strip()
            event_type = str(event.get("event_type") or "event").strip().lower() or "event"
            event_name = str(event.get("event_name") or event.get("summary") or event_id or "event").strip()
            themes = [dict(item or {}) for item in list(event.get("themes") or []) if isinstance(item, dict)]
            for theme in themes[:3]:
                strategy_preferences = {
                    str(item or "").strip()
                    for item in list(theme.get("preferred_strategy_types") or theme.get("strategy_preferences") or [])
                    if str(item or "").strip()
                }
                if strategy_preferences and "event_structure_breakout" not in strategy_preferences:
                    continue
                target_symbols = _normalize_target_codes(theme.get("target_symbols"), limit=3)
                if not target_symbols:
                    continue
                focus_name = str(theme.get("theme_name") or theme.get("theme_code") or event_name).strip()
                event_anchor = {
                    "source": "announcement" if event_type in {"announcement", "earnings", "filing", "news"} else "sector_catalyst",
                    "id": event_id or str(theme.get("theme_code") or focus_name).strip(),
                    "type": event_type,
                    "strength": round(
                        max(
                            self._safe_float((theme.get("score_summary") or {}).get("avg_final_score") or 0.0),
                            self._safe_float(event.get("confidence") or event.get("intensity") or 0.0),
                        ),
                        4,
                    ),
                    "theme_code": str(theme.get("theme_code") or "").strip() or None,
                    "focus_industries": self._normalize_text_list(focus_name, limit=3),
                    "target_symbols": list(target_symbols),
                }
                observed_sources = ["announcement"] if event_anchor["source"] == "announcement" else ["sector_catalyst"]
                event_prefilter = self._build_event_prefilter(
                    observed_sources=observed_sources,
                    evidence_summary=str(event.get("summary") or event_name or "").strip(),
                    event_id=event_id,
                    theme_code=str(theme.get("theme_code") or "").strip(),
                    focus_industries=self._normalize_text_list(focus_name, limit=3),
                    event_anchor=event_anchor,
                    confirmation_count=len(observed_sources),
                    anchor_strength=event_anchor.get("strength"),
                    required=True,
                )
                research_task = {
                    "task_source": "event_driven",
                    "preferred_strategy_types": ["event_structure_breakout"],
                    "allowed_strategy_types": ["event_structure_breakout"],
                    "strategy_preferences": ["event_structure_breakout"],
                    "candidate_family": "event_structure_breakout",
                    "target_symbols": list(target_symbols),
                    "stock_pool": {"selection_mode": "explicit", "symbols": list(target_symbols)},
                    "target_symbol_policy": "strict_intersection",
                    "universe_expansion_policy": "forbid",
                    "validation_focus": "candidate_target_only",
                    "focus_industries": list(event_anchor.get("focus_industries") or []),
                    "event_id": event_id or None,
                    "event_type": event_type,
                    "theme_code": event_anchor.get("theme_code"),
                    "event_name": event_name,
                    "preference_strength": "strong",
                    "preference_reason": f"event_anchor:{event_anchor.get('source')}:{event_anchor.get('id')}",
                    "gate_1_representative_count": min(3, len(target_symbols)),
                    "synthetic_local_spawn": True,
                    "target_pool_source": "event_anchor",
                }
                extras = {
                    **self._high_precision_candidate_fields(
                        preferred_regime="event_follow_through_with_structure_confirmation",
                        avoid_regime="false_breakout_or_post_event_mean_reversion",
                        holding_rationale="只在明确事件锚存在后，等待缩量整理与放量突破确认再参与，避免把普通板块热度误当成可审计事件延续。",
                        failure_mode={
                            "primary_failure_mode": "false_breakout_after_weak_event_confirmation",
                            "secondary_failure_mode": "event_extension_without_follow_through",
                        },
                        entry_selectivity="strict_event_breakout",
                        max_position_pct=0.14,
                        capacity_bucket="mid",
                        min_days=3,
                        max_days=12,
                        entry_bias="event_structure_breakout_confirmation",
                        exit_bias="breakout_failure_or_time_stop",
                        event_prefilter=event_prefilter,
                        candidate_origin="research_signal",
                        event_anchor=event_anchor,
                        target_pool_source="event_anchor",
                    ),
                    "research_task": research_task,
                    "requested_target_symbols": list(target_symbols),
                    "target_symbols": list(target_symbols),
                    "stock_pool": {"selection_mode": "explicit", "symbols": list(target_symbols)},
                }
                out.append(
                    self._make(
                        "event_structure_breakout",
                        self._high_precision_event_structure_breakout_params(),
                        f"{focus_name or event_name} 事件锚确认后的高精度结构突破",
                        source="event_driven",
                        trigger_signal={
                            "field": "event_driven",
                            "event_id": event_id,
                            "event_type": event_type,
                            "theme_code": event_anchor.get("theme_code"),
                            "target_symbols": list(target_symbols),
                        },
                        trigger_thresholds=[
                            self._threshold("event_id", "!=", "", event_id or None, "事件锚存在"),
                            self._threshold("event_target_symbols", ">=", 1, len(target_symbols), "事件目标池可用"),
                        ],
                        extras=extras,
                    )
                )
        return out

    def _from_fund_flow(self, snapshot: dict) -> List[dict]:
        out: List[dict] = []
        north_3d = snapshot.get("north_fund_3d_net", 0)
        margin_5d = snapshot.get("margin_5d_change_pct", 0)

        if north_3d > 5_000_000_000:
            north_anchor = self._snapshot_event_anchor(
                snapshot,
                source="fund_flow",
                trigger_signal={"field": "north_fund_3d_net", "value": north_3d},
            )
            north_prefilter = self._build_event_prefilter(
                observed_sources=["fund_flow"],
                evidence_summary=f"north_fund_3d_net:{north_3d:.0f}",
                event_anchor=north_anchor,
                confirmation_count=1,
                anchor_strength=north_anchor.get("strength"),
                required=True,
            )
            if self._event_anchor_has_explicit_source(north_anchor):
                out.append(self._make("event_structure_breakout", self._high_precision_event_structure_breakout_params(), f"北向3日净流入{north_3d / 1e8:.0f}亿，高精度事件结构突破", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")], extras=self._high_precision_candidate_fields(preferred_regime="event_follow_through_with_structure_confirmation", avoid_regime="false_breakout_or_post_event_mean_reversion", holding_rationale="只在资金显著回流后等待缩量整理并放量突破再参与，避免把普通脉冲误当成结构延续。", failure_mode={"primary_failure_mode": "false_breakout_after_flow_impulse", "secondary_failure_mode": "cost_drag_after_chasing_extension"}, entry_selectivity="strict_event_breakout", max_position_pct=0.14, capacity_bucket="mid", min_days=3, max_days=12, entry_bias="event_structure_breakout_confirmation", exit_bias="breakout_failure_or_time_stop", event_prefilter=north_prefilter, candidate_origin="research_signal", event_anchor=north_anchor, target_pool_source="event_anchor" if _normalize_target_codes(north_anchor.get("target_symbols"), limit=6) else "static_fallback")))
            out.append(self._make("growth_factor", {"lookback": self._jitter(40, 30, 60), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流入{north_3d / 1e8:.0f}亿，成长加速", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
            out.append(self._make("quality_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.8, "sell_quantile": 0.2}, f"北向3日净流入{north_3d / 1e8:.0f}亿，质量优选", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
        elif north_3d < -5_000_000_000:
            out.append(self._make("value_factor", {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.85, "sell_quantile": 0.15}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，价值防御", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 24, "greed_threshold": 74, "lookback": 36}, f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，高精度宏观择时", source="fund_flow", trigger_signal={"field": "north_fund_3d_net", "value": north_3d}, trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")], extras=self._high_precision_candidate_fields(preferred_regime="panic_repair_with_volatility_stabilization", avoid_regime="mid_regime_whipsaw", holding_rationale="北向明显撤退后只等待风险偏好修复再参与，避免在中性阶段来回切换。", failure_mode={"primary_failure_mode": "regime_whipsaw", "secondary_failure_mode": "false_risk_repair"}, max_position_pct=0.14, capacity_bucket="mid", min_days=6, max_days=24, entry_bias="panic_repair_after_regime_confirmation", exit_bias="greed_extreme_or_regime_break")))

        if margin_5d > 2.0:
            margin_anchor = self._snapshot_event_anchor(
                snapshot,
                source="fund_flow",
                trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d},
            )
            margin_prefilter = self._build_event_prefilter(
                observed_sources=["fund_flow"],
                evidence_summary=f"margin_5d_change_pct:{margin_5d:.2f}",
                event_anchor=margin_anchor,
                confirmation_count=1,
                anchor_strength=margin_anchor.get("strength"),
                required=True,
            )
            if self._event_anchor_has_explicit_source(margin_anchor):
                out.append(self._make("event_structure_breakout", self._high_precision_event_structure_breakout_params(), f"融资5日增速{margin_5d:.1f}%，高精度事件结构突破", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", ">", 2.0, margin_5d, "融资增速阈值")], extras=self._high_precision_candidate_fields(preferred_regime="event_follow_through_with_structure_confirmation", avoid_regime="false_breakout_or_post_event_mean_reversion", holding_rationale="只有在融资脉冲后出现缩量整理并放量突破时才参与，避免在纯脉冲扩张阶段直接追高。", failure_mode={"primary_failure_mode": "breakout_without_follow_through", "secondary_failure_mode": "overtrading"}, entry_selectivity="strict_event_breakout", max_position_pct=0.14, capacity_bucket="mid", min_days=3, max_days=12, entry_bias="event_structure_breakout_confirmation", exit_bias="breakout_failure_or_time_stop", event_prefilter=margin_prefilter, candidate_origin="research_signal", event_anchor=margin_anchor, target_pool_source="event_anchor" if _normalize_target_codes(margin_anchor.get("target_symbols"), limit=6) else "static_fallback")))
            out.append(self._make("momentum", {"lookback": self._jitter(5, 3, 10), "threshold": 0.01}, f"融资5日增速{margin_5d:.1f}%，短周期动量", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", ">", 2.0, margin_5d, "融资增速阈值")]))
        elif margin_5d < -2.0:
            out.append(self._make("margin_divergence", self._high_precision_margin_divergence_params(), f"融资5日降速{abs(margin_5d):.1f}%，高精度流动性修复", source="fund_flow", trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d}, trigger_thresholds=[self._threshold("margin_5d_change_pct", "<", -2.0, margin_5d, "融资降速阈值")], extras=self._high_precision_candidate_fields(preferred_regime="liquidity_repair_with_volume_reexpansion", avoid_regime="volume_vacuum_or_failed_rebound", holding_rationale="融资回落后只等待缩量止跌、放量修复和结构转强共振再参与，优先低频高胜率而不是频繁抄底。", failure_mode={"primary_failure_mode": "failed_rebound_after_liquidity_dryup", "secondary_failure_mode": "cost_fragility"}, entry_bias="liquidity_divergence_repair_confirmation", exit_bias="liquidity_break_or_time_stop")))
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
            event_prefilter = {}
            event_anchor: dict[str, Any] = {}
            if strategy_type == "event_structure_breakout":
                event_prefilter = self._snapshot_event_prefilter(
                    snapshot,
                    source="quota_fill",
                    trigger_signal={"field": "quota_fill", "strategy_type": strategy_type},
                )
                event_anchor = dict(event_prefilter.get("event_anchor") or {})
                if not self._event_anchor_has_explicit_source(event_anchor):
                    return False
                if not event_prefilter.get("passed"):
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
            extras = None
            if strategy_type == "event_structure_breakout":
                extras = self._high_precision_candidate_fields(
                    preferred_regime="event_follow_through_with_structure_confirmation",
                    avoid_regime="false_breakout_or_post_event_mean_reversion",
                    holding_rationale="只在公告/资金/板块催化先行确认后，再等待缩量整理与放量突破的结构延续段参与，避免把无催化噪声突破误判成事件延续。",
                    failure_mode={
                        "primary_failure_mode": "breakout_without_external_catalyst",
                        "secondary_failure_mode": "false_breakout_after_weak_event_confirmation",
                    },
                    entry_selectivity="strict_event_breakout",
                    max_position_pct=0.14,
                    capacity_bucket="mid",
                    min_days=3,
                    max_days=12,
                    entry_bias="event_structure_breakout_confirmation",
                    exit_bias="breakout_failure_or_time_stop",
                    event_prefilter=event_prefilter,
                    candidate_origin="anchored_quota_fill",
                    event_anchor=event_anchor,
                    target_pool_source=(
                        "event_anchor"
                        if _normalize_target_codes(event_anchor.get("target_symbols"), limit=6)
                        else "static_fallback"
                    ),
                )
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
                extras=extras,
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
