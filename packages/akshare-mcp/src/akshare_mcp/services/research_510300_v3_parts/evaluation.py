

def simulate_monthly_rotation_family(
    *,
    name: str,
    base_calendar: pd.DataFrame,
    instrument_frames: dict[str, pd.DataFrame],
    lookback_months: int,
    trend_window: int,
    assumptions: FactoryBacktestAssumptions,
) -> StrategyArtifact:
    if base_calendar.empty or not instrument_frames:
        return _empty_artifact(name, extra={"lookback_months": lookback_months, "trend_window": trend_window})
    calendar = base_calendar["date"].drop_duplicates().sort_values().reset_index(drop=True)
    execution_dates = set(_build_monthly_execution_dates(calendar))
    signal_dates = set(pd.to_datetime(base_calendar.groupby(base_calendar["date"].dt.to_period("M"))["date"].max().tolist()))
    next_trade_map = {
        pd.Timestamp(calendar.iloc[idx]): pd.Timestamp(calendar.iloc[idx + 1]) if idx + 1 < len(calendar) else pd.Timestamp(calendar.iloc[idx])
        for idx in range(len(calendar))
    }
    target_by_exec: dict[pd.Timestamp, str | None] = {}
    for signal_date in sorted(signal_dates):
        scored: list[tuple[float, str]] = []
        for code, frame in instrument_frames.items():
            score = _monthly_score(
                frame,
                signal_date,
                lookback_months=lookback_months,
                trend_window=trend_window,
            )
            if score is None:
                continue
            scored.append((score, code))
        scored.sort(key=lambda item: (-item[0], item[1]))
        target = scored[0][1] if scored else None
        target_by_exec[next_trade_map[pd.Timestamp(signal_date)]] = target

    cash = 0.0
    current_code: str | None = None
    current_shares = 0
    prev_total_asset: float | None = None
    tw_nav = 1.0
    equity_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    for trade_date in calendar:
        trade_date = pd.Timestamp(trade_date)
        external_flow = 0.0
        if trade_date in execution_dates:
            cash += MONTHLY_CONTRIBUTION
            external_flow += MONTHLY_CONTRIBUTION
        target_code = target_by_exec.get(trade_date, current_code)
        if target_code != current_code:
            if current_code and current_shares > 0:
                current_frame = instrument_frames[current_code]
                sell_open = _trade_price(current_frame, trade_date, "open") or _trade_price(current_frame, trade_date, "close")
                if sell_open:
                    revenue = current_shares * sell_open * (1.0 - assumptions.commission_rate - assumptions.slippage_bps / 10000.0)
                    cash += revenue
                    trade_rows.append(
                        {
                            "date": trade_date,
                            "side": "sell",
                            "asset_code": current_code,
                            "shares": current_shares,
                            "price": sell_open,
                            "cash_amount": revenue,
                            "reason": "monthly_rotation",
                        }
                    )
                    current_shares = 0
                    current_code = None
            if target_code:
                target_frame = instrument_frames[target_code]
                buy_open = _trade_price(target_frame, trade_date, "open")
                if buy_open:
                    cost_per_share = buy_open * (1.0 + assumptions.commission_rate + assumptions.slippage_bps / 10000.0)
                    shares = _round_down_lot(cash / cost_per_share, assumptions.min_trade_lot)
                    if shares > 0:
                        total_cost = shares * buy_open * (1.0 + assumptions.commission_rate + assumptions.slippage_bps / 10000.0)
                        cash -= total_cost
                        current_code = target_code
                        current_shares = shares
                        trade_rows.append(
                            {
                                "date": trade_date,
                                "side": "buy",
                                "asset_code": target_code,
                                "shares": shares,
                                "price": buy_open,
                                "cash_amount": total_cost,
                                "reason": "monthly_rotation",
                            }
                        )
        market_value = 0.0
        if current_code and current_shares > 0:
            current_frame = instrument_frames[current_code]
            close_price = _trade_price(current_frame, trade_date, "close")
            if close_price:
                market_value = current_shares * close_price
        total_asset = cash + market_value
        exposure = market_value / total_asset if total_asset > 0 else 0.0
        if prev_total_asset and prev_total_asset > 0:
            tw_nav *= max((total_asset - external_flow) / prev_total_asset, 0.0)
        prev_total_asset = total_asset
        equity_rows.append(
            {
                "date": trade_date,
                "total_asset": total_asset,
                "market_value": market_value,
                "cash_pool": cash,
                "external_flow": external_flow,
                "exposure": exposure,
                "tw_nav": tw_nav,
                "selected_asset": current_code or "",
            }
        )
    return _build_strategy_artifact_from_rows(
        name=name,
        equity_rows=equity_rows,
        trade_rows=trade_rows,
        extra={"lookback_months": lookback_months, "trend_window": trend_window},
    )


def simulate_leveraged_family(
    *,
    name: str,
    price_df: pd.DataFrame,
    strong_exposure: float,
    weak_exposure: float,
    assumptions: FactoryBacktestAssumptions,
    financing_rate_daily: float = 0.04 / 252.0,
) -> StrategyArtifact:
    if price_df.empty or len(price_df) < 160:
        return _empty_artifact(name, extra={"strong_exposure": strong_exposure, "weak_exposure": weak_exposure})
    frame = price_df.copy().reset_index(drop=True)
    frame["ma150"] = frame["close"].rolling(150).mean()
    frame["ma150_slope"] = frame["ma150"].diff(20)
    execution_dates = set(_build_monthly_execution_dates(frame["date"]))
    cash = 0.0
    equity_value = 0.0
    exposure = 0.0
    prev_total_asset: float | None = None
    tw_nav = 1.0
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(frame.itertuples(index=False)):
        trade_date = pd.Timestamp(row.date)
        external_flow = 0.0
        if trade_date in execution_dates:
            cash += MONTHLY_CONTRIBUTION
            equity_value += MONTHLY_CONTRIBUTION
            external_flow += MONTHLY_CONTRIBUTION
        prior_signal = weak_exposure
        if idx > 0:
            prev = frame.iloc[idx - 1]
            if np.isfinite(prev["ma150"]) and np.isfinite(prev["ma150_slope"]) and prev["close"] > prev["ma150"] and prev["ma150_slope"] > 0:
                prior_signal = strong_exposure
        if abs(prior_signal - exposure) > 1e-9:
            turnover = abs(prior_signal - exposure)
            trade_cost = turnover * max(equity_value, 0.0) * (assumptions.commission_rate + assumptions.slippage_bps / 10000.0)
            equity_value = max(equity_value - trade_cost, 0.0)
            trade_rows.append(
                {
                    "date": trade_date,
                    "side": "rebalance",
                    "price": float(row.open),
                    "cash_amount": trade_cost,
                    "reason": "signal_shift",
                    "target_exposure": prior_signal,
                }
            )
            exposure = prior_signal
        open_price = _safe_float(row.open)
        close_price = _safe_float(row.close)
        intraday_return = (close_price / open_price - 1.0) if open_price > 0 else 0.0
        financing_cost = max(exposure - 1.0, 0.0) * financing_rate_daily
        equity_value = max(equity_value * (1.0 + exposure * intraday_return - financing_cost), 0.0)
        total_asset = equity_value
        if prev_total_asset and prev_total_asset > 0:
            tw_nav *= max((total_asset - external_flow) / prev_total_asset, 0.0)
        prev_total_asset = total_asset
        equity_rows.append(
            {
                "date": trade_date,
                "total_asset": total_asset,
                "market_value": total_asset * exposure,
                "cash_pool": total_asset * max(1.0 - exposure, 0.0),
                "external_flow": external_flow,
                "exposure": exposure,
                "tw_nav": tw_nav,
            }
        )
    return _build_strategy_artifact_from_rows(
        name=name,
        equity_rows=equity_rows,
        trade_rows=trade_rows,
        extra={"strong_exposure": strong_exposure, "weak_exposure": weak_exposure},
    )


def simulate_futures_family(
    *,
    name: str,
    futures_df: pd.DataFrame,
    strong_exposure: float,
    weak_exposure: float,
    fee_info: Mapping[str, Any],
) -> StrategyArtifact:
    if futures_df.empty or len(futures_df) < 160:
        return _empty_artifact(name, extra={"strong_exposure": strong_exposure, "weak_exposure": weak_exposure})
    frame = futures_df.copy().reset_index(drop=True)
    frame["ma150"] = frame["close"].rolling(150).mean()
    frame["ma150_slope"] = frame["ma150"].diff(20)
    execution_dates = set(_build_monthly_execution_dates(frame["date"]))
    cash = 0.0
    contracts = 0
    multiplier = _safe_int(fee_info.get("contract_multiplier"), FUTURES_FALLBACK_COST["contract_multiplier"])
    margin_rate = _safe_float(fee_info.get("margin_rate"), FUTURES_FALLBACK_COST["margin_rate"])
    fixed_fee = _safe_float(fee_info.get("fixed_fee_per_contract"), FUTURES_FALLBACK_COST["fixed_fee_per_contract"])
    slippage_bps = _safe_float(fee_info.get("slippage_bps"), FUTURES_FALLBACK_COST["slippage_bps"])
    prev_total_asset: float | None = None
    tw_nav = 1.0
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(frame.itertuples(index=False)):
        trade_date = pd.Timestamp(row.date)
        external_flow = 0.0
        if trade_date in execution_dates:
            cash += MONTHLY_CONTRIBUTION
            external_flow += MONTHLY_CONTRIBUTION
        target_exposure = weak_exposure
        if idx > 0:
            prev = frame.iloc[idx - 1]
            if np.isfinite(prev["ma150"]) and np.isfinite(prev["ma150_slope"]) and prev["close"] > prev["ma150"] and prev["ma150_slope"] > 0:
                target_exposure = strong_exposure
        open_price = _safe_float(row.open)
        notional_per_contract = open_price * multiplier if open_price > 0 else 0.0
        desired_contracts = 0
        if notional_per_contract > 0 and cash > 0:
            max_by_notional = math.floor(target_exposure * cash / notional_per_contract)
            max_by_margin = math.floor(cash / max(notional_per_contract * margin_rate, 1.0))
            desired_contracts = max(0, min(max_by_notional, max_by_margin))
        delta = desired_contracts - contracts
        if delta != 0:
            fee_paid = abs(delta) * fixed_fee
            slippage_paid = abs(delta) * notional_per_contract * (slippage_bps / 10000.0)
            cash -= fee_paid + slippage_paid
            trade_rows.append(
                {
                    "date": trade_date,
                    "side": "buy" if delta > 0 else "sell",
                    "contracts": abs(delta),
                    "price": open_price,
                    "cash_amount": fee_paid + slippage_paid,
                    "reason": "futures_rebalance",
                }
            )
            contracts = desired_contracts
        close_price = _safe_float(row.close)
        pnl = contracts * multiplier * (close_price - open_price)
        cash += pnl
        total_asset = max(cash, 0.0)
        gross_notional = contracts * close_price * multiplier
        exposure = gross_notional / total_asset if total_asset > 0 else 0.0
        if prev_total_asset and prev_total_asset > 0:
            tw_nav *= max((total_asset - external_flow) / prev_total_asset, 0.0)
        prev_total_asset = total_asset
        equity_rows.append(
            {
                "date": trade_date,
                "total_asset": total_asset,
                "market_value": gross_notional,
                "cash_pool": cash,
                "external_flow": external_flow,
                "exposure": exposure,
                "tw_nav": tw_nav,
                "contracts": contracts,
            }
        )
    return _build_strategy_artifact_from_rows(
        name=name,
        equity_rows=equity_rows,
        trade_rows=trade_rows,
        extra={"strong_exposure": strong_exposure, "weak_exposure": weak_exposure, "fee_info": dict(fee_info)},
    )


def simulate_cash_sleeve_scheduler(
    *,
    cash_price_df: pd.DataFrame,
    funding_needs: Mapping[pd.Timestamp, float],
    idle_cash_by_date: Mapping[pd.Timestamp, float] | None = None,
    lot_size: int = 100,
) -> dict[str, Any]:
    if cash_price_df.empty:
        return {
            "listed_before_start": False,
            "pre_listing_idle_days": 0,
            "open_redemption_days": 0,
            "close_rebuild_days": 0,
            "ending_cash": 0.0,
            "ending_shares": 0,
        }
    frame = cash_price_df.copy().sort_values("date").reset_index(drop=True)
    idle_map = {pd.Timestamp(key): _safe_float(value) for key, value in dict(idle_cash_by_date or {}).items()}
    listing_date = pd.Timestamp(frame["date"].iloc[0])
    pre_listing_idle_days = sum(1 for date in idle_map if pd.Timestamp(date) < listing_date)
    cash = sum(value for date, value in idle_map.items() if pd.Timestamp(date) < listing_date)
    shares = 0
    open_redemption_days = 0
    close_rebuild_days = 0
    for row in frame.itertuples(index=False):
        trade_date = pd.Timestamp(row.date)
        cash += idle_map.get(trade_date, 0.0)
        need = _safe_float(funding_needs.get(trade_date), 0.0)
        if need > cash and shares > 0 and _safe_float(row.open) > 0:
            required = need - cash
            redeem_shares = _round_down_lot(required / _safe_float(row.open), lot_size)
            redeem_shares = min(max(redeem_shares, lot_size), shares) if required > 0 else 0
            if redeem_shares > 0:
                cash += redeem_shares * _safe_float(row.open)
                shares -= redeem_shares
                open_redemption_days += 1
        if need > 0:
            cash = max(cash - need, 0.0)
        if cash > 0 and _safe_float(row.close) > 0:
            rebuild_shares = _round_down_lot(cash / _safe_float(row.close), lot_size)
            if rebuild_shares > 0:
                shares += rebuild_shares
                cash -= rebuild_shares * _safe_float(row.close)
                close_rebuild_days += 1
    return {
        "listed_before_start": bool(listing_date <= pd.Timestamp(frame["date"].iloc[0])),
        "pre_listing_idle_days": int(pre_listing_idle_days),
        "open_redemption_days": int(open_redemption_days),
        "close_rebuild_days": int(close_rebuild_days),
        "ending_cash": float(cash),
        "ending_shares": int(shares),
    }


def _build_candidate_validation(candidate_runs: Mapping[str, StrategyArtifact]) -> dict[str, Any]:
    if len(candidate_runs) < 2:
        return {"status": "skipped", "reason": "candidate_count_lt_2"}
    daily_matrix = pd.DataFrame({key: run.daily_returns for key, run in candidate_runs.items()}).fillna(0.0)
    if daily_matrix.empty:
        return {"status": "skipped", "reason": "empty_daily_matrix"}
    monthly_returns = ((daily_matrix + 1.0).groupby(daily_matrix.index.to_period("M")).prod() - 1.0).sort_index()
    score_panel = monthly_returns.rolling(6, min_periods=3).mean()
    factor_panel = score_panel.iloc[:-1].to_numpy(dtype=float)
    return_panel = monthly_returns.shift(-1).iloc[:-1].to_numpy(dtype=float)
    result: dict[str, Any] = {"status": "ok", "candidate_count": len(candidate_runs)}
    if factor_panel.shape[0] >= 72:
        wf = WalkForwardValidator(train_window=60, test_window=12, step=12, min_samples_per_period=2)
        result["walk_forward"] = asdict(wf.validate(factor_panel, return_panel))
    else:
        result["walk_forward"] = {"status": "skipped", "reason": "insufficient_months"}
    if factor_panel.shape[0] >= 24:
        pkf = PurgedKFoldCV(n_folds=min(5, max(2, factor_panel.shape[0] // 12)), purge_gap=1, min_samples_per_period=2)
        result["purged_kfold"] = asdict(pkf.validate(factor_panel, return_panel))
    else:
        result["purged_kfold"] = {"status": "skipped", "reason": "insufficient_months"}
    matrix = daily_matrix.to_numpy(dtype=float)
    result["multiple_testing"] = {
        "pbo": probability_of_backtest_overfitting(matrix, n_splits=min(8, max(2, matrix.shape[0] // 50)), seed=13),
        "white_reality_check": white_reality_check(matrix, n_bootstrap=200, seed=13),
        "hansen_spa": hansen_spa_test(matrix, n_bootstrap=200, seed=13, center="consistent"),
    }
    return result


def resolve_default_instruments(end_date: str) -> tuple[dict[str, ResolvedInstrument], dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    resolved: dict[str, ResolvedInstrument] = {}
    prices: dict[str, pd.DataFrame] = {}
    dividends: dict[str, pd.DataFrame] = {}
    futures_fee_info: dict[str, Any] = dict(FUTURES_FALLBACK_COST)
    configs = {
        "risk_core": {
            "category": "risk_core",
            "keyword_group": "hs300",
            "keywords": ["沪深300ETF", "沪深300", "300ETF"],
            "code_hints": ["510300", "159919", "510310"],
            "locked_code": "510300",
        },
        "cash_money": {
            "category": "cash_sleeve",
            "keyword_group": "money_etf",
            "keywords": ["货币ETF", "华宝添益", "货币"],
            "code_hints": ["511990", "159001"],
        },
        "cash_short_bond": {
            "category": "cash_sleeve",
            "keyword_group": "short_bond_etf",
            "keywords": ["短融ETF", "短债ETF", "短融", "短债"],
            "code_hints": ["511360"],
        },
        "cash_treasury": {
            "category": "cash_sleeve",
            "keyword_group": "treasury_etf",
            "keywords": ["十年国债ETF", "国债ETF", "政金债ETF", "十年国债", "国债"],
            "code_hints": ["511260", "511010", "511520", "511580"],
        },
        "style_300": {
            "category": "style",
            "keyword_group": "hs300",
            "keywords": ["沪深300ETF", "沪深300", "300ETF"],
            "code_hints": ["510300", "159919"],
            "locked_code": "510300",
        },
        "style_500": {
            "category": "style",
            "keyword_group": "zz500",
            "keywords": ["中证500ETF", "中证500", "500ETF"],
            "code_hints": ["510500", "159922"],
        },
        "style_chinext": {
            "category": "style",
            "keyword_group": "chinext",
            "keywords": ["创业板ETF", "创业板"],
            "code_hints": ["159915", "159949"],
        },
        "style_div_lowvol": {
            "category": "style",
            "keyword_group": "dividend_lowvol",
            "keywords": ["红利低波ETF", "红利低波"],
            "code_hints": ["512890", "515300"],
        },
    }
    cache: dict[str, tuple[ResolvedInstrument, pd.DataFrame, pd.DataFrame]] = {}
    for key, payload in configs.items():
        cache_key = ",".join(payload["code_hints"])
        if cache_key in cache:
            instrument, history, dividend = cache[cache_key]
        else:
            instrument, history, dividend = resolve_etf_instrument(end_date=end_date, **payload)
            cache[cache_key] = (instrument, history, dividend)
        resolved[key] = instrument
        prices[key] = history
        dividends[key] = dividend
    futures_instrument, futures_history, futures_fee_info = resolve_if_futures(end_date)
    resolved["futures_if0"] = futures_instrument
    prices["futures_if0"] = futures_history
    dividends["futures_if0"] = pd.DataFrame(columns=["ex_date", "per_share_dividend"])
    return resolved, prices, dividends, futures_fee_info


def _slice_price_map(price_map: Mapping[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {key: _slice_frame(frame, start, end) for key, frame in price_map.items()}


def _build_family_candidate_runs(
    family: str,
    *,
    price_map: Mapping[str, pd.DataFrame],
    assumptions: FactoryBacktestAssumptions,
    futures_fee_info: Mapping[str, Any],
) -> dict[str, StrategyArtifact]:
    base_calendar = price_map.get("risk_core", pd.DataFrame())
    if family == "family_a":
        instruments = {
            key: frame
            for key, frame in price_map.items()
            if key in {"risk_core", "cash_money", "cash_short_bond", "cash_treasury"} and not frame.empty
        }
        runs: dict[str, StrategyArtifact] = {}
        for lookback_months in DEFAULT_ROTATION_LOOKBACK_MONTHS:
            for trend_window in (150,):
                candidate_id = f"lb{lookback_months}_ma{trend_window}"
                runs[candidate_id] = simulate_monthly_rotation_family(
                    name=f"{family}_{candidate_id}",
                    base_calendar=base_calendar,
                    instrument_frames=instruments,
                    lookback_months=lookback_months,
                    trend_window=trend_window,
                    assumptions=assumptions,
                )
        return runs
    if family == "family_b":
        instruments = {
            key: frame
            for key, frame in price_map.items()
            if key in {"style_300", "style_500", "style_chinext", "style_div_lowvol"} and not frame.empty
        }
        runs = {}
        for lookback_months in DEFAULT_ROTATION_LOOKBACK_MONTHS:
            for trend_window in (100,):
                candidate_id = f"lb{lookback_months}_ma{trend_window}"
                runs[candidate_id] = simulate_monthly_rotation_family(
                    name=f"{family}_{candidate_id}",
                    base_calendar=base_calendar,
                    instrument_frames=instruments,
                    lookback_months=lookback_months,
                    trend_window=trend_window,
                    assumptions=assumptions,
                )
        return runs
    if family == "family_c":
        runs = {}
        price_df = price_map.get("risk_core", pd.DataFrame())
        for strong in DEFAULT_LEVERAGE_GRID:
            for weak in (0.0, 1.0):
                candidate_id = f"strong_{strong:.1f}_weak_{weak:.1f}"
                runs[candidate_id] = simulate_leveraged_family(
                    name=f"{family}_{candidate_id}",
                    price_df=price_df,
                    strong_exposure=strong,
                    weak_exposure=weak,
                    assumptions=assumptions,
                )
        return runs
    if family == "family_d":
        runs = {}
        futures_df = price_map.get("futures_if0", pd.DataFrame())
        for strong in DEFAULT_LEVERAGE_GRID:
            for weak in (0.0, 1.0):
                candidate_id = f"strong_{strong:.1f}_weak_{weak:.1f}"
                runs[candidate_id] = simulate_futures_family(
                    name=f"{family}_{candidate_id}",
                    futures_df=futures_df,
                    strong_exposure=strong,
                    weak_exposure=weak,
                    fee_info=futures_fee_info,
                )
        return runs
    return {}
