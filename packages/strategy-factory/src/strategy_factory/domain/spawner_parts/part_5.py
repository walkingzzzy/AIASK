
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
        if strategy_type == "event_structure_breakout":
            breakout_window = self._jitter(12 if volatility >= 60 or north_3d > 0 else 14, 10, 20)
            return {
                "breakout_window": breakout_window,
                "breakout_buffer_pct": self._jitter_f(0.002 if north_3d > 0 else 0.004, 0.002, 0.008),
                "contraction_window": self._jitter(5, 3, 8),
                "contraction_max_range_ratio": self._jitter_f(0.06, 0.04, 0.08),
                "volume_window": self._jitter(8, 5, 12),
                "breakout_volume_ratio_min": self._jitter_f(1.0, 0.95, 1.2),
                "structure_window": self._jitter(4, 3, 6),
                "structure_close_location_min": self._jitter_f(0.62, 0.55, 0.7),
                "structure_body_return_min": self._jitter_f(0.003, 0.0015, 0.005),
                "event_impulse_window": self._jitter(5, 3, 8),
                "event_impulse_threshold": self._jitter_f(0.015 if north_3d > 0 else 0.02, 0.01, 0.035),
                "max_hold_bars": self._jitter(8, 5, 12),
                "breakout_failure_close_buffer": self._jitter_f(-0.012, -0.018, -0.008),
                "adverse_volume_ratio_max": self._jitter_f(0.85, 0.75, 0.95),
                "max_active_symbols": 3,
                "universe_selection_profile": "event_structure_breakout_fit_v1",
            }
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
                "fear_threshold": self._jitter(44 if margin_5d < 0 else 40, 34, 50),
                "greed_threshold": self._jitter(62 if margin_5d > 0 else 60, 54, 70),
                "lookback": self._jitter(12, 8, 20),
                "rebound_window": self._jitter(3, 2, 5),
                "repair_drawdown_floor": self._jitter_f(-0.06, -0.09, -0.04),
                "repair_rebound_pct": self._jitter_f(0.012, 0.008, 0.02),
                "dryup_window": 3,
                "dryup_max_ratio": self._jitter_f(0.9, 0.82, 0.98),
                "liquidity_window": 8,
                "entry_volume_floor_ratio": self._jitter_f(1.0, 0.92, 1.1),
                "structure_window": 4,
                "structure_close_location_min": self._jitter_f(0.58, 0.52, 0.68),
                "structure_body_return_min": self._jitter_f(0.002, 0.001, 0.004),
                "max_hold_bars": self._jitter(8, 5, 12),
                "adverse_volume_break_ratio": self._jitter_f(0.72, 0.62, 0.82),
                "adverse_close_break_pct": self._jitter_f(-0.012, -0.02, -0.008),
                "max_active_symbols": 2,
                "universe_selection_profile": "liquidity_divergence_fit_v1",
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
        extras: Optional[dict] = None,
    ) -> dict:
        generation_reason = StrategySpawner._build_generation_reason(
            source=source,
            reason=reason,
            trigger_signal=trigger_signal,
            trigger_thresholds=trigger_thresholds,
            quota_fill=quota_fill,
            kind=kind,
        )
        payload = {
            "strategy_type": strategy_type,
            "params": params,
            "spawn_reason": reason,
            "generation_reason": generation_reason,
            "trigger_signal": generation_reason["trigger_signal"],
            "trigger_thresholds": generation_reason["trigger_thresholds"],
            "quota_fill": quota_fill,
        }
        if extras:
            payload.update(dict(extras))
        return payload
