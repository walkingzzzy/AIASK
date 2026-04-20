
    def _simulate_trend(
        self,
        frame: pd.DataFrame,
        config: TrendConfig,
        *,
        capital: float,
        execution_profile: ExecutionProfile,
    ) -> dict[str, Any]:
        entry_signal = self._trend_signal(frame, config)
        exit_signal = self._trend_exit_signal(frame, config)
        price_column = f"price_{config.leg_month:02d}"
        price_series = frame[price_column].astype(float)
        gross_equity = float(capital)
        net_equity = float(capital)
        position_contracts = 0
        entry_price = 0.0
        entry_index = -1
        entry_date: Optional[pd.Timestamp] = None
        entry_regime = ""
        gross_returns: list[float] = []
        net_returns: list[float] = []
        equity_path: list[float] = []
        trades: list[dict[str, Any]] = []
        gross_pnl_running = 0.0
        net_pnl_running = 0.0
        stress_move = max(
            _safe_float(price_series.pct_change().abs().quantile(0.95), 0.02) * float(price_series.median()) * 2.2,
            0.02 * float(price_series.median()),
        )

        for index, row in frame.iterrows():
            current_price = float(row[price_column])
            previous_price = float(price_series.iloc[index - 1]) if index > 0 else current_price
            gross_pnl = position_contracts * execution_profile.contract_multiplier * (current_price - previous_price)
            gross_equity += gross_pnl
            net_equity += gross_pnl
            gross_cost = 0.0
            net_cost = 0.0
            if position_contracts > 0 and int(row["roll_node"] or 0):
                notional = abs(position_contracts) * current_price * execution_profile.contract_multiplier
                _, roll_cost_rate = self._effective_cost_rate(
                    execution_profile=execution_profile,
                    contracts=abs(position_contracts),
                    participation_cap=max(
                        1,
                        math.floor(
                            execution_profile.liquidity_reference_contracts
                            * execution_profile.capacity_participation_rate
                            * execution_profile.far_month_liquidity_haircut
                        ),
                    ),
                    leg_multiplier=1,
                )
                roll_cost = notional * (roll_cost_rate * 0.35)
                net_equity -= roll_cost
                net_cost += roll_cost
            if position_contracts > 0:
                trade_return = (current_price - entry_price) / max(entry_price, 1e-9)
                should_exit = bool(exit_signal.iloc[index]) or trade_return <= -config.stop_loss_pct
                if should_exit:
                    participation_cap = max(
                        1,
                        math.floor(
                            execution_profile.liquidity_reference_contracts
                            * execution_profile.capacity_participation_rate
                            * execution_profile.far_month_liquidity_haircut
                        ),
                    )
                    commission_rate, cost_rate = self._effective_cost_rate(
                        execution_profile=execution_profile,
                        contracts=abs(position_contracts),
                        participation_cap=participation_cap,
                        leg_multiplier=1,
                    )
                    notional = abs(position_contracts) * current_price * execution_profile.contract_multiplier
                    trade_cost = notional * (commission_rate + cost_rate)
                    net_equity -= trade_cost
                    net_cost += trade_cost
                    last_trade = trades[-1]
                    trades[-1] = self._complete_trade_record(
                        trade=last_trade,
                        exit_date=row["trading_date"],
                        exit_value=current_price,
                        gross_pnl=last_trade.get("gross_pnl", 0.0) + gross_pnl_running + gross_pnl,
                        net_pnl=last_trade.get("net_pnl", 0.0) + net_pnl_running + gross_pnl - net_cost,
                        exit_reason="trend_decay_or_delivery" if bool(exit_signal.iloc[index]) else "stop_loss",
                        holding_days=index - entry_index,
                    )
                    gross_pnl_running = 0.0
                    net_pnl_running = 0.0
                    position_contracts = 0
                    entry_price = 0.0
                    entry_index = -1
                    entry_date = None
                    entry_regime = ""
            if position_contracts == 0 and bool(entry_signal.iloc[index]):
                participation_cap = max(
                    1,
                    math.floor(
                        execution_profile.liquidity_reference_contracts
                        * execution_profile.capacity_participation_rate
                        * execution_profile.far_month_liquidity_haircut
                    ),
                )
                margin_per_contract = current_price * execution_profile.contract_multiplier * execution_profile.margin_rate
                margin_cap = math.floor(net_equity * execution_profile.margin_budget_fraction / max(margin_per_contract, 1.0))
                drawdown_cap = self._drawdown_cap(
                    capital=net_equity,
                    execution_profile=execution_profile,
                    stress_loss_per_contract=stress_move * execution_profile.contract_multiplier,
                )
                capacity_limit = max(
                    1,
                    min(
                        margin_cap,
                        participation_cap,
                        execution_profile.max_contracts_per_rebalance,
                        drawdown_cap,
                    ),
                )
                if capacity_limit > 0:
                    commission_rate, cost_rate = self._effective_cost_rate(
                        execution_profile=execution_profile,
                        contracts=capacity_limit,
                        participation_cap=participation_cap,
                        leg_multiplier=1,
                    )
                    notional = capacity_limit * current_price * execution_profile.contract_multiplier
                    entry_cost = notional * (commission_rate + cost_rate)
                    net_equity -= entry_cost
                    net_cost += entry_cost
                    position_contracts = capacity_limit
                    entry_price = current_price
                    entry_index = index
                    entry_date = row["trading_date"]
                    entry_regime = str(row["regime"])
                    trades.append(
                        {
                            "status": "open",
                            "family": "trend",
                            "entry_index": index,
                            "entry_date": str(entry_date.date()),
                            "entry_value": round(current_price, 6),
                            "entry_regime": entry_regime,
                            "contracts": int(capacity_limit),
                            "gross_pnl": 0.0,
                            "net_pnl": -round(entry_cost, 2),
                        }
                    )
                    gross_pnl_running = 0.0
                    net_pnl_running = -entry_cost
            if position_contracts > 0:
                gross_pnl_running += gross_pnl
                net_pnl_running += gross_pnl - net_cost
            gross_returns.append(gross_pnl / max(gross_equity - gross_pnl, 1.0))
            net_returns.append((gross_pnl - net_cost) / max(net_equity - gross_pnl + net_cost, 1.0))
            equity_path.append(net_equity)

        if position_contracts > 0 and trades:
            last_trade = trades[-1]
            trades[-1] = self._complete_trade_record(
                trade=last_trade,
                exit_date=frame["trading_date"].iloc[-1],
                exit_value=float(price_series.iloc[-1]),
                gross_pnl=last_trade.get("gross_pnl", 0.0) + gross_pnl_running,
                net_pnl=last_trade.get("net_pnl", 0.0) + net_pnl_running,
                exit_reason="final_mark",
                holding_days=max(len(frame) - 1 - last_trade.get("entry_index", 0), 1),
            )

        gross_returns_series = pd.Series(gross_returns, index=frame.index).fillna(0.0)
        net_returns_series = pd.Series(net_returns, index=frame.index).fillna(0.0)
        equity_series = pd.Series(equity_path, index=frame.index)
        entry_forward_returns = price_series.shift(-5).div(price_series).sub(1.0).where(entry_signal, np.nan)
        trade_count = len([trade for trade in trades if trade.get("status") == "closed"])
        summary = {
            "annualized_return": _annualized_return(equity_series),
            "total_return": _safe_float(equity_series.iloc[-1] / max(capital, 1.0) - 1.0),
            "sharpe_ratio": _sharpe_ratio(gross_returns_series),
            "post_cost_sharpe": _sharpe_ratio(net_returns_series),
            "max_drawdown": _max_drawdown(equity_series),
            "win_rate": _trade_win_rate(trades),
            "trade_count": trade_count,
            "trade_density": trade_count / max(len(frame) / 252.0, 1e-9),
            "forward_sharpe_5d": _forward_sharpe_5d(entry_forward_returns),
            "alpha_decay": max(
                0.0,
                _sharpe_ratio(gross_returns_series) - max(_forward_sharpe_5d(entry_forward_returns), 0.0),
            ),
            "ending_equity": _safe_float(equity_series.iloc[-1]),
        }
        regime_panel = {
            "overall": {
                key: summary[key]
                for key in ("annualized_return", "sharpe_ratio", "post_cost_sharpe", "max_drawdown", "win_rate", "trade_count")
            },
            "backwardation": self._regime_summary(net_returns_series, trades, frame["regime"].eq("backwardation")),
            "contango_or_flat": self._regime_summary(net_returns_series, trades, frame["regime"].eq("contango_or_flat")),
        }
        return {
            "family": "trend",
            "entry_signal": entry_signal,
            "summary": summary,
            "regime_panel": regime_panel,
            "trades": trades,
            "equity_series": equity_series,
            "returns_pre_cost": gross_returns_series,
            "returns_post_cost": net_returns_series,
            "signal_series": price_series,
        }

    def _simulate_spread(
        self,
        frame: pd.DataFrame,
        config: SpreadConfig,
        *,
        capital: float,
        execution_profile: ExecutionProfile,
    ) -> dict[str, Any]:
        spread_column, near_price_column, far_price_column = self._spread_definition(config)
        entry_signal = self._spread_signal(frame, config)
        exit_signal = self._spread_exit_signal(frame, config)
        spread_series = frame[spread_column].astype(float)
        near_prices = frame[near_price_column].astype(float)
        far_prices = frame[far_price_column].astype(float)
        near_month = _safe_int(near_price_column.split("_")[1], 1)
        far_month = _safe_int(far_price_column.split("_")[1], near_month + 1)
        price_lookups, rank_lookups = self._get_contract_lookups(frame)
        gross_equity = float(capital)
        net_equity = float(capital)
        position_contracts = 0
        entry_spread = 0.0
        entry_index = -1
        entry_date: Optional[pd.Timestamp] = None
        entry_regime = ""
        entry_long_code = ""
        entry_short_code = ""
        gross_returns: list[float] = []
        net_returns: list[float] = []
        equity_path: list[float] = []
        trades: list[dict[str, Any]] = []
        gross_pnl_running = 0.0
        net_pnl_running = 0.0
        stress_move = max(float(spread_series.diff().abs().quantile(0.95) or 0.0) * 2.0, 3.0)

        for index, row in frame.iterrows():
            current_spread = float(spread_series.iloc[index])
            current_long_price = None
            current_short_price = None
            gross_pnl = 0.0
            if position_contracts > 0:
                current_lookup = price_lookups[index]
                previous_lookup = price_lookups[index - 1] if index > 0 else current_lookup
                current_long_price = self._lookup_contract_price(current_lookup, entry_long_code)
                current_short_price = self._lookup_contract_price(current_lookup, entry_short_code)
                previous_long_price = self._lookup_contract_price(previous_lookup, entry_long_code) or current_long_price
                previous_short_price = self._lookup_contract_price(previous_lookup, entry_short_code) or current_short_price
                if (
                    current_long_price is not None
                    and current_short_price is not None
                    and previous_long_price is not None
                    and previous_short_price is not None
                ):
                    gross_pnl = position_contracts * execution_profile.contract_multiplier * (
                        (current_long_price - previous_long_price)
                        - (current_short_price - previous_short_price)
                    )
                    current_spread = current_long_price - current_short_price
            gross_equity += gross_pnl
            net_equity += gross_pnl
            net_cost = 0.0
            if position_contracts > 0:
                long_rank = rank_lookups[index].get(entry_long_code, 99)
                should_exit = (
                    bool(exit_signal.iloc[index])
                    or (current_spread - entry_spread) <= config.stop_move
                    or (index - entry_index) >= int(config.max_holding_days)
                    or (long_rank <= 2 and int(row["roll_next_3d"] or 0) == 1)
                    or current_long_price is None
                    or current_short_price is None
                )
                if should_exit:
                    participation_cap = max(
                        1,
                        math.floor(
                            execution_profile.liquidity_reference_contracts
                            * execution_profile.capacity_participation_rate
                            * execution_profile.far_month_liquidity_haircut
                        ),
                    )
                    commission_rate, cost_rate = self._effective_cost_rate(
                        execution_profile=execution_profile,
                        contracts=abs(position_contracts),
                        participation_cap=participation_cap,
                        leg_multiplier=2,
                    )
                    gross_notional = abs(position_contracts) * execution_profile.contract_multiplier * max(
                        (current_long_price or float(row[near_price_column])) + (current_short_price or float(row[far_price_column])),
                        1.0,
                    )
                    trade_cost = gross_notional * (commission_rate + cost_rate)
                    net_equity -= trade_cost
                    net_cost += trade_cost
                    last_trade = trades[-1]
                    trades[-1] = self._complete_trade_record(
                        trade=last_trade,
                        exit_date=row["trading_date"],
                        exit_value=current_spread,
                        gross_pnl=last_trade.get("gross_pnl", 0.0) + gross_pnl_running + gross_pnl,
                        net_pnl=last_trade.get("net_pnl", 0.0) + net_pnl_running + gross_pnl - net_cost,
                        exit_reason=(
                            "mean_reversion_or_delivery"
                            if bool(exit_signal.iloc[index]) or (long_rank <= 2 and int(row["roll_next_3d"] or 0) == 1)
                            else "stop_loss_or_time_stop"
                        ),
                        holding_days=index - entry_index,
                    )
                    gross_pnl_running = 0.0
                    net_pnl_running = 0.0
                    position_contracts = 0
                    entry_spread = 0.0
                    entry_index = -1
                    entry_date = None
                    entry_regime = ""
                    entry_long_code = ""
                    entry_short_code = ""
            if position_contracts == 0 and bool(entry_signal.iloc[index]):
                participation_cap = max(
                    1,
                    math.floor(
                        execution_profile.liquidity_reference_contracts
                        * execution_profile.capacity_participation_rate
                        * execution_profile.far_month_liquidity_haircut
                    ),
                )
                gross_margin_per_contract = execution_profile.contract_multiplier * execution_profile.margin_rate * (
                    float(row[near_price_column]) + float(row[far_price_column])
                )
                margin_cap = math.floor(net_equity * execution_profile.margin_budget_fraction / max(gross_margin_per_contract, 1.0))
                drawdown_cap = self._drawdown_cap(
                    capital=net_equity,
                    execution_profile=execution_profile,
                    stress_loss_per_contract=stress_move * execution_profile.contract_multiplier,
                )
                capacity_limit = max(
                    1,
                    min(
                        margin_cap,
                        participation_cap,
                        execution_profile.max_contracts_per_rebalance,
                        drawdown_cap,
                    ),
                )
                if capacity_limit > 0:
                    long_code = str(row.get(f"contract_{near_month:02d}") or "").strip().lower()
                    short_code = str(row.get(f"contract_{far_month:02d}") or "").strip().lower()
                    commission_rate, cost_rate = self._effective_cost_rate(
                        execution_profile=execution_profile,
                        contracts=capacity_limit,
                        participation_cap=participation_cap,
                        leg_multiplier=2,
                    )
                    gross_notional = capacity_limit * execution_profile.contract_multiplier * (
                        float(row[near_price_column]) + float(row[far_price_column])
                    )
                    entry_cost = gross_notional * (commission_rate + cost_rate)
                    net_equity -= entry_cost
                    net_cost += entry_cost
                    position_contracts = capacity_limit
                    entry_spread = current_spread
                    entry_index = index
                    entry_date = row["trading_date"]
                    entry_regime = str(row["regime"])
                    entry_long_code = long_code
                    entry_short_code = short_code
                    trades.append(
                        {
                            "status": "open",
                            "family": "spread",
                            "entry_index": index,
                            "entry_date": str(entry_date.date()),
                            "entry_value": round(current_spread, 6),
                            "entry_regime": entry_regime,
                            "contracts": int(capacity_limit),
                            "long_contract": entry_long_code,
                            "short_contract": entry_short_code,
                            "gross_pnl": 0.0,
                            "net_pnl": -round(entry_cost, 2),
                        }
                    )
                    gross_pnl_running = 0.0
                    net_pnl_running = -entry_cost
            if position_contracts > 0:
                gross_pnl_running += gross_pnl
                net_pnl_running += gross_pnl - net_cost
            gross_returns.append(gross_pnl / max(gross_equity - gross_pnl, 1.0))
            net_returns.append((gross_pnl - net_cost) / max(net_equity - gross_pnl + net_cost, 1.0))
            equity_path.append(net_equity)

        if position_contracts > 0 and trades:
            terminal_long_price = self._lookup_contract_price(price_lookups[-1], entry_long_code)
            terminal_short_price = self._lookup_contract_price(price_lookups[-1], entry_short_code)
            terminal_spread = (
                terminal_long_price - terminal_short_price
                if terminal_long_price is not None and terminal_short_price is not None
                else float(spread_series.iloc[-1])
            )
            last_trade = trades[-1]
            trades[-1] = self._complete_trade_record(
                trade=last_trade,
                exit_date=frame["trading_date"].iloc[-1],
                exit_value=terminal_spread,
                gross_pnl=last_trade.get("gross_pnl", 0.0) + gross_pnl_running,
                net_pnl=last_trade.get("net_pnl", 0.0) + net_pnl_running,
                exit_reason="final_mark",
                holding_days=max(len(frame) - 1 - last_trade.get("entry_index", 0), 1),
            )

        gross_returns_series = pd.Series(gross_returns, index=frame.index).fillna(0.0)
        net_returns_series = pd.Series(net_returns, index=frame.index).fillna(0.0)
        equity_series = pd.Series(equity_path, index=frame.index)
        spread_notional = near_prices.abs().add(far_prices.abs()).replace(0.0, np.nan)
        entry_forward_returns = (
            spread_series.shift(-5).sub(spread_series).div(spread_notional)
        ).where(entry_signal, np.nan)
        trade_count = len([trade for trade in trades if trade.get("status") == "closed"])
        summary = {
            "annualized_return": _annualized_return(equity_series),
            "total_return": _safe_float(equity_series.iloc[-1] / max(capital, 1.0) - 1.0),
            "sharpe_ratio": _sharpe_ratio(gross_returns_series),
            "post_cost_sharpe": _sharpe_ratio(net_returns_series),
            "max_drawdown": _max_drawdown(equity_series),
            "win_rate": _trade_win_rate(trades),
            "trade_count": trade_count,
            "trade_density": trade_count / max(len(frame) / 252.0, 1e-9),
            "forward_sharpe_5d": _forward_sharpe_5d(entry_forward_returns),
            "alpha_decay": max(
                0.0,
                _sharpe_ratio(gross_returns_series) - max(_forward_sharpe_5d(entry_forward_returns), 0.0),
            ),
            "ending_equity": _safe_float(equity_series.iloc[-1]),
        }
        regime_panel = {
            "overall": {
                key: summary[key]
                for key in ("annualized_return", "sharpe_ratio", "post_cost_sharpe", "max_drawdown", "win_rate", "trade_count")
            },
            "backwardation": self._regime_summary(net_returns_series, trades, frame["regime"].eq("backwardation")),
            "contango_or_flat": self._regime_summary(net_returns_series, trades, frame["regime"].eq("contango_or_flat")),
        }
        return {
            "family": "spread",
            "entry_signal": entry_signal,
            "summary": summary,
            "regime_panel": regime_panel,
            "trades": trades,
            "equity_series": equity_series,
            "returns_pre_cost": gross_returns_series,
            "returns_post_cost": net_returns_series,
            "signal_series": spread_series,
        }

    def _run_trend_grid(self, frame: pd.DataFrame, *, capital: float) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for leg_month in (3, 4):
            for carry_threshold in (0.0, 0.5, 1.0):
                for volatility_cap in (0.03, 0.04, 0.05, 0.06):
                    for price_to_ma60_cap in (1.08, 1.12, 1.20):
                        for stop_loss_pct in (0.05, 0.07):
                            config = TrendConfig(
                                leg_month=leg_month,
                                carry_threshold=carry_threshold,
                                volatility_cap=volatility_cap,
                                price_to_ma60_cap=price_to_ma60_cap,
                                stop_loss_pct=stop_loss_pct,
                            )
                            execution_profile = self._trend_execution_profile(config)
                            backtest = self._simulate_trend(
                                frame,
                                config,
                                capital=capital,
                                execution_profile=execution_profile,
                            )
                            results.append(
                                {
                                    "config": config,
                                    "execution_profile": execution_profile,
                                    "backtest": backtest,
                                }
                            )
        return results
