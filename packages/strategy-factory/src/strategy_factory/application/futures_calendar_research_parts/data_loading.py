    """Local SC futures calendar adapter with report / candidate outputs."""

    def __init__(
        self,
        *,
        data_path: Path = DEFAULT_SC_DATA_PATH,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        memo_path: Path = DEFAULT_SC_MEMO_PATH,
        notes_path: Path = DEFAULT_SC_NOTES_PATH,
    ) -> None:
        self.data_path = Path(data_path)
        self.output_dir = Path(output_dir)
        self.memo_path = Path(memo_path)
        self.notes_path = Path(notes_path)
        self._memo_text = _load_optional_text(self.memo_path)
        self._notes_text = _load_optional_text(self.notes_path)
        self._contract_lookup_cache: dict[int, tuple[list[dict[str, float]], list[dict[str, int]]]] = {}

    @staticmethod
    def load_curve_frame(data_path: Path) -> pd.DataFrame:
        frame = pd.read_csv(data_path, parse_dates=["trading_date"]).sort_values("trading_date").reset_index(drop=True)
        for month_index in range(2, 13):
            prev_price = "price_01" if month_index == 2 else f"price_{month_index - 1:02d}"
            spread_name = f"spread_{month_index - 1}_{month_index}"
            frame[f"price_{month_index:02d}"] = frame[prev_price] - frame[spread_name]
        for month_index in range(2, 13):
            frame[f"contract_{month_index:02d}"] = [
                _shift_contract_code(contract_code, month_index - 1)
                for contract_code in frame["contract_01"]
            ]
        return frame

    @staticmethod
    def add_features(frame: pd.DataFrame) -> pd.DataFrame:
        enriched = frame.copy()
        enriched["regime"] = np.where(
            enriched["spread_1_2"] > 0,
            "backwardation",
            "contango_or_flat",
        )
        enriched["backwardation_flag"] = (enriched["spread_1_2"] > 0).astype(int)
        enriched["curve_monotone"] = (
            (enriched["spread_1_2"] >= enriched["spread_2_3"])
            & (enriched["spread_2_3"] >= enriched["spread_3_4"])
        )
        enriched["curve_expansion"] = (
            (enriched["spread_1_2"].diff(5) > 0)
            & (enriched["spread_2_3"].diff(5) > 0)
            & (enriched["spread_3_4"].diff(5) > 0)
        )
        enriched["curve_slope_1_4"] = enriched["spread_1_2"] + enriched["spread_2_3"] + enriched["spread_3_4"]
        enriched["spread_1_3"] = enriched["spread_1_2"] + enriched["spread_2_3"]
        enriched["spread_2_4"] = enriched["spread_2_3"] + enriched["spread_3_4"]
        enriched["roll_node"] = (enriched["contract_01"] != enriched["contract_01"].shift(1)).astype(int)
        next_roll = (enriched["contract_01"] != enriched["contract_01"].shift(-1)).astype(int)
        enriched["roll_next_3d"] = next_roll.iloc[::-1].rolling(3, min_periods=1).max().iloc[::-1].fillna(0).astype(int)
        enriched["roll_next_5d"] = next_roll.iloc[::-1].rolling(5, min_periods=1).max().iloc[::-1].fillna(0).astype(int)
        for column in (
            "price_01",
            "price_02",
            "price_03",
            "price_04",
            "spread_1_2",
            "spread_2_3",
            "spread_3_4",
            "spread_1_3",
            "spread_2_4",
        ):
            enriched[f"{column}_ma20"] = enriched[column].rolling(20).mean()
            enriched[f"{column}_ma60"] = enriched[column].rolling(60).mean()
            enriched[f"{column}_std20"] = enriched[column].rolling(20).std()
            enriched[f"{column}_z40"] = (
                (enriched[column] - enriched[column].rolling(40).mean())
                / enriched[column].rolling(40).std().replace(0.0, np.nan)
            )
            enriched[f"{column}_slope10"] = enriched[column].diff(10) / 10.0
        for column in ("price_03", "price_04"):
            price_series = enriched[column].replace(0.0, np.nan)
            enriched[f"{column}_vol20"] = price_series.pct_change().rolling(20).std()
            enriched[f"{column}_price_to_ma60"] = price_series / enriched[f"{column}_ma60"].replace(0.0, np.nan)
        enriched["price_uptrend"] = (
            (enriched["price_01"] > enriched["price_01_ma20"])
            & (enriched["price_01_ma20"] > enriched["price_01_ma60"])
        )
        enriched["price_downtrend"] = (
            (enriched["price_01"] < enriched["price_01_ma20"])
            & (enriched["price_01_ma20"] < enriched["price_01_ma60"])
        )
        return enriched

    @staticmethod
    def _trend_execution_profile(config: TrendConfig) -> ExecutionProfile:
        if config.leg_month == 3:
            return ExecutionProfile(
                commission_rate=0.00005,
                slippage_bps=3.2,
                market_impact_bps=1.6,
                margin_rate=0.15,
                contract_multiplier=1000,
                capacity_participation_rate=0.11,
                liquidity_bucket="far_month_medium",
                max_contracts_per_rebalance=26,
                liquidity_reference_contracts=220,
                far_month_liquidity_haircut=0.82,
                margin_budget_fraction=0.88,
                drawdown_budget_fraction=0.26,
            )
        return ExecutionProfile(
            commission_rate=0.00005,
            slippage_bps=3.5,
            market_impact_bps=1.8,
            margin_rate=0.15,
            contract_multiplier=1000,
            capacity_participation_rate=0.10,
            liquidity_bucket="far_month_light",
            max_contracts_per_rebalance=22,
            liquidity_reference_contracts=180,
            far_month_liquidity_haircut=0.78,
            margin_budget_fraction=0.85,
            drawdown_budget_fraction=0.25,
        )

    @staticmethod
    def _spread_execution_profile(config: SpreadConfig) -> ExecutionProfile:
        if config.leg_name == "1_2":
            return ExecutionProfile(
                commission_rate=0.00005,
                slippage_bps=3.5,
                market_impact_bps=1.8,
                margin_rate=0.15,
                contract_multiplier=1000,
                capacity_participation_rate=0.10,
                liquidity_bucket="near_month_high",
                max_contracts_per_rebalance=24,
                liquidity_reference_contracts=210,
                far_month_liquidity_haircut=0.95,
                margin_budget_fraction=0.70,
                drawdown_budget_fraction=0.18,
            )
        if config.leg_name == "2_3":
            return ExecutionProfile(
                commission_rate=0.00004,
                slippage_bps=2.8,
                market_impact_bps=1.2,
                margin_rate=0.15,
                contract_multiplier=1000,
                capacity_participation_rate=0.11,
                liquidity_bucket="near_mid_high",
                max_contracts_per_rebalance=22,
                liquidity_reference_contracts=220,
                far_month_liquidity_haircut=0.90,
                margin_budget_fraction=0.74,
                drawdown_budget_fraction=0.20,
            )
        if config.leg_name == "3_4":
            return ExecutionProfile(
                commission_rate=0.00004,
                slippage_bps=2.6,
                market_impact_bps=1.1,
                margin_rate=0.15,
                contract_multiplier=1000,
                capacity_participation_rate=0.10,
                liquidity_bucket="mid_far_medium",
                max_contracts_per_rebalance=20,
                liquidity_reference_contracts=180,
                far_month_liquidity_haircut=0.84,
                margin_budget_fraction=0.76,
                drawdown_budget_fraction=0.20,
            )
        if config.leg_name == "1_3":
            return ExecutionProfile(
                commission_rate=0.00005,
                slippage_bps=3.4,
                market_impact_bps=1.5,
                margin_rate=0.15,
                contract_multiplier=1000,
                capacity_participation_rate=0.09,
                liquidity_bucket="synthetic_medium",
                max_contracts_per_rebalance=16,
                liquidity_reference_contracts=150,
                far_month_liquidity_haircut=0.80,
                margin_budget_fraction=0.70,
                drawdown_budget_fraction=0.19,
            )
        return ExecutionProfile(
            commission_rate=0.00004,
            slippage_bps=3.0,
            market_impact_bps=1.3,
            margin_rate=0.15,
            contract_multiplier=1000,
            capacity_participation_rate=0.10,
            liquidity_bucket="synthetic_far_light",
            max_contracts_per_rebalance=16,
            liquidity_reference_contracts=150,
            far_month_liquidity_haircut=0.82,
            margin_budget_fraction=0.72,
            drawdown_budget_fraction=0.19,
        )

    @staticmethod
    def _trend_signal(frame: pd.DataFrame, config: TrendConfig) -> pd.Series:
        price_column = f"price_{config.leg_month:02d}"
        spread_column = f"spread_{config.leg_month - 1}_{config.leg_month}"
        return (
            (frame[spread_column] > config.carry_threshold)
            & frame["curve_monotone"]
            & (frame["curve_slope_1_4"] > 0.0)
            & (frame["spread_1_2"] > config.near_premium_floor)
            & (frame[price_column] > frame[f"{price_column}_ma20"])
            & (frame[f"{price_column}_ma20"] > frame[f"{price_column}_ma60"])
            & (frame[f"{price_column}_price_to_ma60"] < config.price_to_ma60_cap)
            & (frame[f"{price_column}_vol20"] < config.volatility_cap)
            & (frame[f"{price_column}_slope10"] > 0.0)
            & (frame["roll_next_5d"] == 0)
        ).fillna(False)

    @staticmethod
    def _trend_exit_signal(frame: pd.DataFrame, config: TrendConfig) -> pd.Series:
        price_column = f"price_{config.leg_month:02d}"
        spread_column = f"spread_{config.leg_month - 1}_{config.leg_month}"
        return (
            (frame[spread_column] <= 0.0)
            | (frame["spread_1_2"] <= config.exit_premium_floor)
            | (frame[price_column] < frame[f"{price_column}_ma20"])
            | (frame[f"{price_column}_ma20"] < frame[f"{price_column}_ma60"])
            | (frame["roll_next_3d"] == 1)
        ).fillna(False)

    @staticmethod
    def _spread_definition(config: SpreadConfig) -> tuple[pd.Series, str, str]:
        leg_map = {
            "1_2": ("spread_1_2", "price_01", "price_02"),
            "2_3": ("spread_2_3", "price_02", "price_03"),
            "3_4": ("spread_3_4", "price_03", "price_04"),
            "1_3": ("spread_1_3", "price_01", "price_03"),
            "2_4": ("spread_2_4", "price_02", "price_04"),
        }
        spread_column, near_price_column, far_price_column = leg_map[config.leg_name]
        return spread_column, near_price_column, far_price_column

    @classmethod
    def _spread_signal(cls, frame: pd.DataFrame, config: SpreadConfig) -> pd.Series:
        spread_column, _, _ = cls._spread_definition(config)
        zscore_column = f"{spread_column}_z40"
        price_filter = pd.Series(True, index=frame.index)
        if config.require_price_trend:
            price_filter = frame["price_uptrend"]
        return (
            (frame[zscore_column] >= config.entry_z_low)
            & (frame[zscore_column] <= config.entry_z_high)
            & (frame["spread_1_2"] > config.near_premium_floor)
            & frame["curve_monotone"]
            & (frame["curve_slope_1_4"] > config.slope_floor)
            & price_filter
            & (frame["roll_next_5d"] == 0)
        ).fillna(False)

    @classmethod
    def _spread_exit_signal(cls, frame: pd.DataFrame, config: SpreadConfig) -> pd.Series:
        spread_column, _, _ = cls._spread_definition(config)
        zscore_column = f"{spread_column}_z40"
        return (
            (frame[zscore_column] >= config.exit_z)
            | (frame["spread_1_2"] <= config.exit_premium_floor)
            | (frame["curve_slope_1_4"] < min(config.slope_floor, 0.0))
            | frame["price_downtrend"]
            | (frame["roll_next_3d"] == 1)
        ).fillna(False)

    @staticmethod
    def _effective_cost_rate(
        *,
        execution_profile: ExecutionProfile,
        contracts: int,
        participation_cap: int,
        leg_multiplier: int,
    ) -> tuple[float, float]:
        utilization = contracts / max(float(participation_cap or 1), 1.0)
        scale = 1.0 + min(max(utilization, 0.0), 1.0) * 0.5
        commission_rate = execution_profile.commission_rate * leg_multiplier
        bps_cost = (execution_profile.slippage_bps + execution_profile.market_impact_bps) * scale * leg_multiplier
        return commission_rate, bps_cost / 10000.0

    @staticmethod
    def _drawdown_cap(
        *,
        capital: float,
        execution_profile: ExecutionProfile,
        stress_loss_per_contract: float,
    ) -> int:
        if stress_loss_per_contract <= 0:
            return execution_profile.max_contracts_per_rebalance
        cap = math.floor(
            capital * execution_profile.drawdown_budget_fraction / max(stress_loss_per_contract, 1.0)
        )
        return max(cap, 1)

    def _get_contract_lookups(
        self,
        frame: pd.DataFrame,
    ) -> tuple[list[dict[str, float]], list[dict[str, int]]]:
        cache_key = id(frame)
        cached = self._contract_lookup_cache.get(cache_key)
        if cached is not None:
            return cached
        price_maps: list[dict[str, float]] = []
        rank_maps: list[dict[str, int]] = []
        for _, row in frame.iterrows():
            price_map: dict[str, float] = {}
            rank_map: dict[str, int] = {}
            for month_index in range(1, 13):
                code = str(row.get(f"contract_{month_index:02d}") or "").strip().lower()
                price = row.get(f"price_{month_index:02d}")
                if not code or pd.isna(price):
                    continue
                price_map[code] = float(price)
                rank_map[code] = month_index
            price_maps.append(price_map)
            rank_maps.append(rank_map)
        cached = (price_maps, rank_maps)
        self._contract_lookup_cache[cache_key] = cached
        return cached

    @staticmethod
    def _lookup_contract_price(
        lookup: dict[str, float],
        contract_code: str,
    ) -> Optional[float]:
        price = lookup.get(str(contract_code or "").strip().lower())
        if price is None or pd.isna(price):
            return None
        return float(price)

    @staticmethod
    def _regime_summary(
        returns: pd.Series,
        trades: list[dict[str, Any]],
        regime_mask: pd.Series,
    ) -> dict[str, Any]:
        masked_returns = pd.Series(returns).where(regime_mask.fillna(False), 0.0)
        trade_subset = [
            trade for trade in trades
            if str(trade.get("entry_regime") or "").strip()
            == ("backwardation" if bool(regime_mask[trade.get("entry_index", 0)]) else "contango_or_flat")
        ]
        equity = (1.0 + masked_returns.fillna(0.0)).cumprod()
        return {
            "annualized_return": _annualized_return(equity),
            "sharpe_ratio": _sharpe_ratio(masked_returns.fillna(0.0)),
            "max_drawdown": _max_drawdown(equity),
            "trade_count": len([trade for trade in trade_subset if trade.get("status") == "closed"]),
            "win_rate": _trade_win_rate(trade_subset),
        }

    @staticmethod
    def _instrument_profile_from_series(
        *,
        series: pd.Series,
        underlying: str,
        curve_legs: list[dict[str, Any]],
        roll_rule: dict[str, Any],
    ) -> dict[str, Any]:
        close = pd.Series(series).dropna().astype(float)
        returns = close.pct_change().dropna()
        if close.empty or returns.empty:
            return {
                "asset_class": "futures",
                "underlying": underlying,
                "curve_legs": deepcopy(curve_legs),
                "roll_rule": deepcopy(roll_rule),
                "measurement_source": "sc_calendar_research_adapter",
                "measured_profile_complete": False,
                "board_bucket": "futures",
                "symbol": underlying,
            }
        annual_volatility = float(returns.std(ddof=1) * math.sqrt(252))
        abs_returns = returns.abs()
        gap_p95 = float(abs_returns.quantile(0.95))
        atr14_pct = float(abs_returns.rolling(14, min_periods=5).mean().dropna().mean() or abs_returns.mean())
        intraday_range_p90 = float(abs_returns.quantile(0.90))
        direction = close.diff(60).iloc[-1] if len(close) > 61 else close.diff().sum()
        path = close.diff().abs().rolling(60, min_periods=10).sum().iloc[-1] if len(close) > 61 else close.diff().abs().sum()
        path_value = _safe_float(path)
        trend_efficiency = float(abs(direction) / path_value) if path_value > 0 else 0.0
        return {
            "asset_class": "futures",
            "underlying": underlying,
            "curve_legs": deepcopy(curve_legs),
            "roll_rule": deepcopy(roll_rule),
            "annual_volatility_realized_252d": annual_volatility,
            "annual_volatility": annual_volatility,
            "atr14_pct_realized": atr14_pct,
            "atr14_pct": atr14_pct,
            "gap_p95_realized": gap_p95,
            "gap_p95": gap_p95,
            "intraday_range_p90": intraday_range_p90,
            "trend_efficiency_60d_realized": trend_efficiency,
            "trend_efficiency_60d": trend_efficiency,
            "turnover_median": 1.0,
            "volume_ratio_p80": 1.0,
            "volume_ratio_p90": 1.0,
            "turnover_rate_p80": 1.0,
            "turnover_rate_p90": 1.0,
            "measurement_source": "sc_calendar_research_adapter",
            "measurement_sources": {
                "annual_volatility_realized_252d": "research_adapter",
                "atr14_pct_realized": "research_adapter",
                "gap_p95_realized": "research_adapter",
                "intraday_range_p90": "research_adapter",
                "trend_efficiency_60d_realized": "research_adapter",
                "volume_ratio_p80": "research_adapter_proxy",
                "volume_ratio_p90": "research_adapter_proxy",
                "turnover_rate_p80": "research_adapter_proxy",
                "turnover_rate_p90": "research_adapter_proxy",
            },
            "measured_profile_complete": True,
            "board_bucket": "futures",
            "symbol": underlying,
        }

    @staticmethod
    def _compile_strategy_blueprint_safe(candidate: dict[str, Any], market_frame: pd.DataFrame) -> dict[str, Any]:
        from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

        compiled = compile_strategy_blueprint(candidate, market_frame=market_frame, tune_for_factory=True)
        return dict(compiled or {})

    @staticmethod
    def _complete_trade_record(
        *,
        trade: dict[str, Any],
        exit_date: pd.Timestamp,
        exit_value: float,
        net_pnl: float,
        gross_pnl: float,
        exit_reason: str,
        holding_days: int,
    ) -> dict[str, Any]:
        completed = dict(trade)
        completed.update(
            {
                "status": "closed",
                "exit_date": str(exit_date.date()),
                "exit_value": round(exit_value, 6),
                "net_pnl": round(net_pnl, 2),
                "gross_pnl": round(gross_pnl, 2),
                "exit_reason": exit_reason,
                "holding_days": int(holding_days),
            }
        )
        return completed
