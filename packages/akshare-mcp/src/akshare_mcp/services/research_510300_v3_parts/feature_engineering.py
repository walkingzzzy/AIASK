

def _fund_candidates_for_keywords(keywords: Sequence[str], code_hints: Sequence[str]) -> list[dict[str, Any]]:
    universe = _load_fund_universe()
    pattern = "|".join(keywords)
    matched = universe[
        universe["基金简称"].str.contains(pattern, na=False)
        | universe["基金代码"].isin([str(code).zfill(6) for code in code_hints])
    ].copy()
    matched = matched.loc[
        matched["基金代码"].str.match(r"^[15]\d{5}$", na=False)
        | matched["基金代码"].isin([str(code).zfill(6) for code in code_hints])
    ]
    rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in matched.itertuples(index=False):
        code = str(getattr(row, "基金代码", "")).zfill(6)
        if code in seen_codes:
            continue
        seen_codes.add(code)
        rows.append(
            {
                "code": code,
                "name": str(getattr(row, "基金简称", code)),
                "fund_type": str(getattr(row, "基金类型", "")),
            }
        )
    return rows


def resolve_etf_instrument(
    *,
    category: str,
    keyword_group: str,
    keywords: Sequence[str],
    code_hints: Sequence[str],
    end_date: str,
    locked_code: str | None = None,
) -> tuple[ResolvedInstrument, pd.DataFrame, pd.DataFrame]:
    attempted: list[dict[str, Any]] = []
    resolved_history = pd.DataFrame()
    resolved_dividends = pd.DataFrame()
    selected: dict[str, Any] | None = None
    failures: list[str] = []
    if locked_code:
        normalized_code = str(locked_code).zfill(6)
        universe = _load_fund_universe()
        matched = universe.loc[universe["基金代码"] == normalized_code]
        if matched.empty:
            candidates = [{"code": normalized_code, "name": normalized_code, "fund_type": "unknown"}]
        else:
            row = matched.iloc[0]
            candidates = [
                {
                    "code": normalized_code,
                    "name": str(row.get("基金简称", normalized_code)),
                    "fund_type": str(row.get("基金类型", "")),
                }
            ]
    else:
        candidates = _fund_candidates_for_keywords(keywords, code_hints)
    for candidate in candidates:
        code = candidate["code"]
        try:
            history = _fetch_etf_history(code, end_date=end_date)
        except Exception as exc:
            attempted.append({**candidate, "status": "history_error", "reason": str(exc)})
            failures.append(f"{code}:history_error")
            continue
        if len(history) < 60:
            attempted.append({**candidate, "status": "insufficient_history", "history_rows": int(len(history))})
            failures.append(f"{code}:insufficient_history")
            continue
        dividends = _fetch_etf_dividends(code, end_date=end_date)
        record = {
            **candidate,
            "symbol": _normalize_symbol(code),
            "status": "ok",
            "history_rows": int(len(history)),
            "first_trade_date": history["date"].iloc[0].strftime("%Y-%m-%d"),
            "last_trade_date": history["date"].iloc[-1].strftime("%Y-%m-%d"),
            "median_amount_60d": _median_amount_60(history),
            "dividend_rows": int(len(dividends)),
        }
        attempted.append(record)
        if selected is None or _candidate_sort_key(record) < _candidate_sort_key(selected):
            selected = record
            resolved_history = history
            resolved_dividends = dividends
    if selected is None:
        unresolved = ResolvedInstrument(
            category=category,
            keyword_group=keyword_group,
            code="",
            symbol="",
            name="",
            source="fund_name_em",
            history_rows=0,
            first_trade_date="",
            last_trade_date="",
            median_amount_60d=0.0,
            candidates=attempted,
            failure_reason=";".join(failures) or "no_candidate",
        )
        return unresolved, resolved_history, resolved_dividends
    resolved = ResolvedInstrument(
        category=category,
        keyword_group=keyword_group,
        code=str(selected["code"]),
        symbol=str(selected["symbol"]),
        name=str(selected["name"]),
        source="locked_code+fund_etf_hist_sina" if locked_code else "fund_name_em+fund_etf_hist_sina",
        history_rows=int(selected["history_rows"]),
        first_trade_date=str(selected["first_trade_date"]),
        last_trade_date=str(selected["last_trade_date"]),
        median_amount_60d=float(selected["median_amount_60d"]),
        candidates=attempted,
    )
    return resolved, resolved_history, resolved_dividends


def resolve_if_futures(end_date: str) -> tuple[ResolvedInstrument, pd.DataFrame, dict[str, Any]]:
    attempted: list[dict[str, Any]] = []
    fee_info = dict(FUTURES_FALLBACK_COST)
    fee_info["fallback_triggered"] = True
    try:
        history = _fetch_futures_history("IF0", end_date=end_date)
        attempted.append(
            {
                "symbol": "IF0",
                "status": "ok" if not history.empty else "empty",
                "history_rows": int(len(history)),
                "first_trade_date": history["date"].iloc[0].strftime("%Y-%m-%d") if not history.empty else "",
                "last_trade_date": history["date"].iloc[-1].strftime("%Y-%m-%d") if not history.empty else "",
            }
        )
    except Exception as exc:
        history = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        attempted.append({"symbol": "IF0", "status": "history_error", "reason": str(exc)})
    try:
        with _ProxyBypass():
            fees = ak.futures_fees_info()
        filtered = fees.loc[fees["品种代码"].astype(str) == "IF"].copy()
        if not filtered.empty:
            row = filtered.iloc[0]
            fee_info = {
                "slippage_bps": FUTURES_FALLBACK_COST["slippage_bps"],
                "fixed_fee_per_contract": _safe_float(row.get("1手开仓费用"), FUTURES_FALLBACK_COST["fixed_fee_per_contract"]),
                "margin_rate": _safe_float(row.get("做多保证金率"), FUTURES_FALLBACK_COST["margin_rate"]),
                "contract_multiplier": _safe_int(row.get("合约乘数"), FUTURES_FALLBACK_COST["contract_multiplier"]),
                "fallback_triggered": False,
            }
    except Exception:
        pass
    resolved = ResolvedInstrument(
        category="futures",
        keyword_group="IF0",
        code="IF0",
        symbol="IF0",
        name="沪深300股指期货连续主力",
        source="futures_main_sina",
        history_rows=int(len(history)),
        first_trade_date=history["date"].iloc[0].strftime("%Y-%m-%d") if not history.empty else "",
        last_trade_date=history["date"].iloc[-1].strftime("%Y-%m-%d") if not history.empty else "",
        median_amount_60d=_median_amount_60(history),
        candidates=attempted,
        failure_reason=None if not history.empty else "missing_futures_history",
    )
    return resolved, history, fee_info


def required_summary_fields() -> set[str]:
    return {
        "research_protocol",
        "instrument_resolution",
        "cost_scenarios",
        "oos_folds",
        "cash_sleeve_results",
        "enhancement_results",
        "selection_gate",
        "final_recommendation",
    }


def build_monthly_windows(
    trade_dates: Iterable[pd.Timestamp] | pd.Index | pd.Series,
    *,
    train_months: int,
    test_months: int,
    step_months: int,
) -> list[dict[str, pd.Timestamp]]:
    trade_index = pd.Index(pd.to_datetime(list(trade_dates)))
    if trade_index.empty:
        return []
    frame = pd.DataFrame({"date": trade_index}).sort_values("date")
    frame["month"] = frame["date"].dt.to_period("M")
    grouped = frame.groupby("month")["date"]
    month_first = grouped.min().tolist()
    month_last = grouped.max().tolist()
    windows: list[dict[str, pd.Timestamp]] = []
    cursor = train_months
    while cursor + test_months <= len(month_last):
        train_start_idx = cursor - train_months
        train_end_idx = cursor - 1
        test_start_idx = cursor
        test_end_idx = cursor + test_months - 1
        windows.append(
            {
                "train_start": pd.Timestamp(month_first[train_start_idx]),
                "train_end": pd.Timestamp(month_last[train_end_idx]),
                "test_start": pd.Timestamp(month_first[test_start_idx]),
                "test_end": pd.Timestamp(month_last[test_end_idx]),
            }
        )
        cursor += step_months
    return windows


def _slice_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[(frame["date"] >= start) & (frame["date"] <= end)].copy().reset_index(drop=True)


def _slice_dividends(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[(frame["ex_date"] >= start) & (frame["ex_date"] <= end)].copy().reset_index(drop=True)


def _legacy_assumptions(slippage_bps: float) -> FactoryBacktestAssumptions:
    return FactoryBacktestAssumptions(
        commission_rate=0.00025,
        slippage_bps=float(slippage_bps),
        slippage_model="fixed",
        min_trade_lot=100,
        sell_tax_rate=0.0,
        market_ruleset="cn_equity",
    )


def _metrics_rank_key(metrics: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -_safe_float(metrics.get("cagr")),
        _safe_float(metrics.get("max_drawdown")),
        _safe_float(metrics.get("average_exposure")),
    )


def _daily_returns_from_nav(curve: pd.DataFrame) -> pd.Series:
    if curve.empty or "tw_nav" not in curve:
        return pd.Series(dtype=float)
    nav = pd.to_numeric(curve["tw_nav"], errors="coerce").ffill().fillna(1.0)
    returns = nav.pct_change().fillna(0.0)
    returns.index = pd.to_datetime(curve["date"])
    return returns


def _summarize_nav_curve(curve: pd.DataFrame) -> dict[str, Any]:
    if curve.empty or "tw_nav" not in curve:
        return {
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "average_exposure": 0.0,
            "total_return": 0.0,
            "final_total_asset": 0.0,
        }
    nav = pd.to_numeric(curve["tw_nav"], errors="coerce").fillna(1.0)
    running_max = nav.cummax()
    drawdown = (nav / running_max - 1.0).min() if not nav.empty else 0.0
    start_date = pd.Timestamp(curve["date"].iloc[0])
    end_date = pd.Timestamp(curve["date"].iloc[-1])
    years = max((end_date - start_date).days / 365.2425, 0.0)
    final_nav = float(nav.iloc[-1]) if not nav.empty else 1.0
    return {
        "cagr": float(final_nav ** (1.0 / years) - 1.0) if years > 0 and final_nav > 0 else 0.0,
        "max_drawdown": abs(float(drawdown)) if nav.size else 0.0,
        "average_exposure": float(pd.to_numeric(curve.get("exposure", 0.0), errors="coerce").fillna(0.0).mean()),
        "total_return": float(final_nav - 1.0),
        "final_total_asset": float(pd.to_numeric(curve.get("total_asset", 0.0), errors="coerce").fillna(0.0).iloc[-1]) if "total_asset" in curve else 0.0,
    }


def _chain_oos_curves(curves: Sequence[pd.DataFrame]) -> pd.DataFrame:
    if not curves:
        return pd.DataFrame(columns=["date", "tw_nav", "exposure", "total_asset"])
    nav_anchor = 1.0
    combined: list[pd.DataFrame] = []
    for idx, curve in enumerate(curves):
        if curve.empty:
            continue
        segment = curve.copy()
        segment["date"] = pd.to_datetime(segment["date"])
        segment["tw_nav"] = pd.to_numeric(segment["tw_nav"], errors="coerce").fillna(1.0) * nav_anchor
        nav_anchor = float(segment["tw_nav"].iloc[-1])
        if idx > 0:
            segment = segment.iloc[1:].copy()
        combined.append(segment)
    if not combined:
        return pd.DataFrame(columns=["date", "tw_nav", "exposure", "total_asset"])
    return pd.concat(combined, ignore_index=True)


def _serialize_strategy(strategy: Any) -> StrategyArtifact:
    metrics = asdict(strategy.metrics) if dataclass_is_instance(strategy.metrics) else dict(strategy.metrics)
    return StrategyArtifact(
        name=str(strategy.name),
        metrics=metrics,
        equity_curve=strategy.equity_curve.copy(),
        trades=strategy.trades.copy(),
        daily_returns=_daily_returns_from_nav(strategy.equity_curve),
        extra=dict(strategy.extra or {}),
    )


def run_legacy_core_suite(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    *,
    slippage_bps: float,
    scheme2_take_profit_grid: Sequence[float] = DEFAULT_TAKE_PROFIT_GRID,
) -> tuple[dict[str, StrategyArtifact], list[dict[str, Any]]]:
    legacy = _load_legacy_module()
    assumptions = _legacy_assumptions(slippage_bps)
    _trade_dates, monthly_schedule, next_trade_after_ex = legacy.build_trading_calendar(price_df, dividend_df)
    indicators = legacy.build_indicator_frame(price_df)

    scheme1 = legacy.simulate_monthly_dca(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        name="scheme1",
        description="legacy frozen baseline: monthly DCA",
        fixed_external_injection=True,
        take_profit_pct=None,
    )
    scheme2_candidates: list[StrategyArtifact] = []
    for take_profit_pct in scheme2_take_profit_grid:
        candidate = legacy.simulate_monthly_dca(
            price_df,
            dividend_df,
            monthly_schedule,
            next_trade_after_ex,
            assumptions,
            name="scheme2",
            description="legacy frozen scheme2 with variable take-profit",
            fixed_external_injection=False,
            take_profit_pct=float(take_profit_pct),
        )
        serialized = _serialize_strategy(candidate)
        serialized.extra["take_profit_pct"] = float(take_profit_pct)
        scheme2_candidates.append(serialized)
    scheme2_candidates.sort(key=lambda item: _metrics_rank_key(item.metrics))
    scheme2_best = scheme2_candidates[0]

    optimized_candidates = legacy.search_optimization_candidates(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        indicators,
    )
    optimized_payloads = [
        {
            "ma_window": candidate.ma_window,
            "rsi_floor": candidate.rsi_floor,
            "rsi_cap": candidate.rsi_cap,
            "sell_rsi": candidate.sell_rsi,
            "use_slope": candidate.use_slope,
            "metrics": asdict(candidate.metrics),
        }
        for candidate in optimized_candidates
    ]
    best_candidate = optimized_candidates[0]
    optimized = legacy.simulate_regime_strategy(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        indicators,
        ma_window=best_candidate.ma_window,
        rsi_floor=best_candidate.rsi_floor,
        rsi_cap=best_candidate.rsi_cap,
        sell_rsi=best_candidate.sell_rsi,
        use_slope=best_candidate.use_slope,
    )
    optimized_serialized = _serialize_strategy(optimized)
    optimized_serialized.extra.update(
        {
            "ma_window": int(best_candidate.ma_window),
            "rsi_floor": int(best_candidate.rsi_floor),
            "rsi_cap": int(best_candidate.rsi_cap),
            "sell_rsi": int(best_candidate.sell_rsi),
            "use_slope": bool(best_candidate.use_slope),
        }
    )
    return {
        "scheme1": _serialize_strategy(scheme1),
        "scheme2": scheme2_best,
        "optimized_regime": optimized_serialized,
    }, optimized_payloads


def _empty_artifact(name: str, *, extra: Optional[dict[str, Any]] = None) -> StrategyArtifact:
    empty_curve = pd.DataFrame(columns=["date", "total_asset", "exposure", "tw_nav"])
    return StrategyArtifact(
        name=name,
        metrics=_summarize_nav_curve(empty_curve),
        equity_curve=empty_curve,
        trades=pd.DataFrame(columns=["date", "side", "price", "cash_amount", "reason"]),
        daily_returns=pd.Series(dtype=float),
        extra=dict(extra or {}),
    )


def _build_monthly_execution_dates(calendar: pd.Series | pd.Index | Iterable[pd.Timestamp]) -> list[pd.Timestamp]:
    trade_index = pd.Index(pd.to_datetime(list(calendar))).sort_values()
    if trade_index.empty:
        return []
    frame = pd.DataFrame({"date": trade_index})
    month_ends = frame.groupby(frame["date"].dt.to_period("M"))["date"].max().tolist()
    execution_dates: list[pd.Timestamp] = []
    for month_end in month_ends:
        idx = trade_index.searchsorted(pd.Timestamp(month_end))
        if idx + 1 < len(trade_index):
            execution_dates.append(pd.Timestamp(trade_index[idx + 1]))
        else:
            execution_dates.append(pd.Timestamp(month_end))
    return execution_dates


def _round_down_lot(shares: float, lot_size: int = 100) -> int:
    return int(math.floor(float(shares) / float(lot_size)) * lot_size)


def _trade_price(frame: pd.DataFrame, date: pd.Timestamp, column: str) -> float | None:
    row = frame.loc[frame["date"] == date]
    if row.empty:
        return None
    value = _safe_float(row.iloc[0].get(column), np.nan)
    return None if not np.isfinite(value) or value <= 0 else float(value)


def _monthly_score(
    frame: pd.DataFrame,
    signal_date: pd.Timestamp,
    *,
    lookback_months: int,
    trend_window: int,
) -> float | None:
    current_rows = frame.loc[frame["date"] <= signal_date].copy()
    if current_rows.empty:
        return None
    current_rows = current_rows.sort_values("date").reset_index(drop=True)
    if len(current_rows) <= trend_window:
        return None
    lookback_days = max(21, int(lookback_months * 21))
    if len(current_rows) <= lookback_days:
        return None
    closes = pd.to_numeric(current_rows["close"], errors="coerce").fillna(0.0)
    current_close = float(closes.iloc[-1])
    prior_close = float(closes.iloc[-lookback_days])
    trend_ma = float(closes.rolling(trend_window).mean().iloc[-1])
    if prior_close <= 0 or trend_ma <= 0 or current_close <= 0:
        return None
    if current_close <= trend_ma:
        return None
    return current_close / prior_close - 1.0


def _build_strategy_artifact_from_rows(
    *,
    name: str,
    equity_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    extra: Optional[dict[str, Any]] = None,
) -> StrategyArtifact:
    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    if not equity_curve.empty:
        equity_curve["date"] = pd.to_datetime(equity_curve["date"])
    if not trades.empty:
        trades["date"] = pd.to_datetime(trades["date"])
    return StrategyArtifact(
        name=name,
        metrics=_summarize_nav_curve(equity_curve),
        equity_curve=equity_curve,
        trades=trades,
        daily_returns=_daily_returns_from_nav(equity_curve),
        extra=dict(extra or {}),
    )
