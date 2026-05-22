
def _resolve_order_fill(
    requested_shares: int,
    *,
    index: int,
    volumes: np.ndarray,
    tradability_mask: Optional[np.ndarray],
    lot_size: int,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    requested = max(0, int(requested_shares or 0))
    normalized_lot = max(1, int(lot_size or 1))
    if requested <= 0:
        return {
            "requested_shares": 0,
            "filled_shares": 0,
            "rejected_shares": 0,
            "partial_fill": False,
            "blocked_reason": "no_requested_shares",
            "actual_participation_rate": 0.0,
            "adv_utilization": None,
            "rolling_adv_20": _rolling_average_volume(volumes, index),
            "capacity_limited": False,
            "execution_penalty_bps": 0.0,
        }

    day_volume = float(volumes[index]) if 0 <= index < len(volumes) else 0.0
    rolling_adv_20 = _rolling_average_volume(volumes, index)
    tradable = True if tradability_mask is None else bool(tradability_mask[index])
    if not tradable:
        return {
            "requested_shares": requested,
            "filled_shares": 0,
            "rejected_shares": requested,
            "partial_fill": False,
            "blocked_reason": "not_tradable",
            "day_volume": day_volume,
            "rolling_adv_20": rolling_adv_20,
            "actual_participation_rate": 0.0,
            "adv_utilization": None,
            "capacity_limited": False,
            "execution_penalty_bps": 0.0,
        }
    if day_volume <= 0:
        return {
            "requested_shares": requested,
            "filled_shares": 0,
            "rejected_shares": requested,
            "partial_fill": False,
            "blocked_reason": "zero_volume",
            "day_volume": day_volume,
            "rolling_adv_20": rolling_adv_20,
            "actual_participation_rate": 0.0,
            "adv_utilization": None,
            "capacity_limited": False,
            "execution_penalty_bps": 0.0,
        }

    max_fillable = requested
    capacity_caps: list[int] = []
    capacity_participation_rate = _safe_float(args.get("capacity_participation_rate"), 0.0)
    adv_ratio_limit = _safe_float(args.get("adv_ratio_limit"), 0.0)
    if capacity_participation_rate > 0:
        capacity_caps.append(max(0, int(np.floor(day_volume * capacity_participation_rate))))
    if adv_ratio_limit > 0 and rolling_adv_20 > 0:
        capacity_caps.append(max(0, int(np.floor(rolling_adv_20 * adv_ratio_limit))))
    if capacity_caps:
        max_fillable = min(max_fillable, min(capacity_caps))
    filled = _round_down_lot(max_fillable, normalized_lot)
    if filled <= 0:
        blocked_reason = "capacity_below_lot" if capacity_caps else "below_min_trade_lot"
        return {
            "requested_shares": requested,
            "filled_shares": 0,
            "rejected_shares": requested,
            "partial_fill": False,
            "blocked_reason": blocked_reason,
            "day_volume": day_volume,
            "rolling_adv_20": rolling_adv_20,
            "actual_participation_rate": 0.0,
            "adv_utilization": None,
            "capacity_limited": bool(capacity_caps),
            "execution_penalty_bps": 0.0,
        }

    rejected = max(0, requested - filled)
    actual_participation_rate = (filled / day_volume) if day_volume > 0 else 0.0
    actual_adv_ratio = (filled / rolling_adv_20) if rolling_adv_20 > 0 else 0.0
    adv_utilization = (actual_adv_ratio / adv_ratio_limit) if adv_ratio_limit > 0 else None

    arrival_policy = str(args.get("arrival_price_policy") or "next_open_proxy").strip().lower()
    arrival_bps = _ARRIVAL_PRICE_POLICY_BPS.get(arrival_policy)
    if arrival_bps is None:
        arrival_bps = 2.0 if "open" in arrival_policy else 1.0
    market_impact_bps = _safe_float(args.get("market_impact_bps"), 0.0)
    capacity_penalty_bps = _estimate_capacity_penalty_bps(
        args,
        actual_participation_rate=actual_participation_rate,
        adv_utilization=adv_utilization,
    )

    return {
        "requested_shares": requested,
        "filled_shares": filled,
        "rejected_shares": rejected,
        "partial_fill": rejected > 0,
        "blocked_reason": "capacity_limited" if rejected > 0 else None,
        "day_volume": day_volume,
        "rolling_adv_20": rolling_adv_20,
        "actual_participation_rate": round(actual_participation_rate, 6),
        "actual_adv_ratio": round(actual_adv_ratio, 6) if actual_adv_ratio > 0 else 0.0,
        "adv_utilization": round(adv_utilization, 4) if adv_utilization is not None else None,
        "capacity_limited": bool(capacity_caps and rejected > 0),
        "execution_penalty_bps": round(arrival_bps + max(0.0, market_impact_bps) + capacity_penalty_bps, 4),
        "capacity_penalty_bps": round(capacity_penalty_bps, 4),
    }

def _build_strategy_masks(
    strategy: str,
    closes: np.ndarray,
    params: Dict[str, Any],
    volumes: Optional[np.ndarray] = None,
    klines: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """为策略构建 entry/exit 掩码。"""
    n = len(closes)
    strategy = str(strategy or "").strip().lower()

    from .strategy_registry import StrategyRegistry

    runtime_instance, execution_semantic_mode = StrategyRegistry.create_runtime_strategy(strategy, params)
    if runtime_instance is not None:
        if klines and hasattr(runtime_instance, "generate_entry_exit_masks_from_klines"):
            try:
                return runtime_instance.generate_entry_exit_masks_from_klines(klines)
            except Exception:
                pass
        if execution_semantic_mode == "compiled_dsl" or hasattr(runtime_instance, "generate_entry_exit_masks"):
            try:
                return runtime_instance.generate_entry_exit_masks(closes, volumes)
            except Exception:
                pass

    if strategy == "ma_cross":
        short_period = max(2, int(params.get("short_period", 5)))
        long_period = max(short_period + 1, int(params.get("long_period", 20)))
        if n < long_period + 2:
            return None

        short_ma = np.full(n, np.nan, dtype=np.float64)
        long_ma = np.full(n, np.nan, dtype=np.float64)
        for i in range(short_period - 1, n):
            short_ma[i] = float(np.mean(closes[i - short_period + 1 : i + 1]))
        for i in range(long_period - 1, n):
            long_ma[i] = float(np.mean(closes[i - long_period + 1 : i + 1]))

        entry = np.zeros(n, dtype=bool)
        exit_ = np.zeros(n, dtype=bool)
        for i in range(long_period, n):
            if (
                short_ma[i - 1] <= long_ma[i - 1]
                and short_ma[i] > long_ma[i]
            ):
                entry[i] = True
            elif (
                short_ma[i - 1] >= long_ma[i - 1]
                and short_ma[i] < long_ma[i]
            ):
                exit_[i] = True
        return entry, exit_

    if strategy == "momentum":
        lookback = max(2, int(params.get("lookback", params.get("period", 20))))
        threshold = float(params.get("threshold", 0.02) or 0.02)
        if n < lookback + 2:
            return None

        momentum = np.zeros(n, dtype=np.float64)
        for i in range(lookback, n):
            base = closes[i - lookback]
            if base > 0:
                momentum[i] = (closes[i] - base) / base

        entry = momentum > threshold
        exit_ = momentum < -threshold
        entry[:lookback] = False
        exit_[:lookback] = False
        return entry, exit_

    if strategy == "rsi":
        rsi_period = max(2, int(params.get("rsi_period", 14)))
        oversold = float(params.get("oversold", 30) or 30)
        overbought = float(params.get("overbought", 70) or 70)
        if n < rsi_period + 2:
            return None

        rsi = np.full(n, np.nan, dtype=np.float64)
        for i in range(rsi_period, n):
            gains = 0.0
            losses = 0.0
            for j in range(i - rsi_period + 1, i + 1):
                change = closes[j] - closes[j - 1]
                if change > 0:
                    gains += change
                else:
                    losses -= change
            avg_gain = gains / rsi_period
            avg_loss = losses / rsi_period
            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        entry = rsi < oversold
        exit_ = rsi > overbought
        entry[:rsi_period] = False
        exit_[:rsi_period] = False
        return entry, exit_

    # Fallback: try StrategyRegistry for user-submitted strategies
    klass = StrategyRegistry.get(strategy)
    if klass is not None:
        instance = klass()
        instance.set_parameters(params)
        return instance.generate_entry_exit_masks(closes, volumes)

    return None

def _simulate_trades_from_masks(
    closes: np.ndarray,
    volumes: np.ndarray,
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    initial_capital: float,
    commission_rate: float,
    slippage_calc: Optional[SlippageCalculator] = None,
    tradability_mask: Optional[np.ndarray] = None,
    return_trades: bool = False,
    klines: Optional[List[Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    signal_events: Optional[List[StrategySignalEvent]] = None,
) -> Dict[str, Any]:
    """按 entry/exit 掩码执行交易仿真，支持逐笔滑点与可交易过滤。"""
    n = len(closes)
    args = dict(params or {})
    a_share_rules = _is_a_share_ruleset(args)
    lot_size = max(1, int(args.get("min_trade_lot", 100 if a_share_rules else 1) or (100 if a_share_rules else 1)))
    sell_tax_rate = _safe_float(args.get("sell_tax_rate"), 0.001 if a_share_rules else 0.0)
    t_plus_one = bool(args.get("t_plus_one", a_share_rules))
    position_pct = _resolve_position_pct(args)
    payload_context = {
        "tradable_days": int(np.sum(tradability_mask)) if tradability_mask is not None else int(np.sum(volumes > 0)),
        "total_days": int(n),
        "tradability_filter": bool(tradability_mask is not None),
    }
    explicit_slippage = _safe_float(args.get("slippage", 0.0), 0.0)
    model_slippage = _compute_slippage_rate(closes, volumes, args, 0.0)
    market_impact_bps = _safe_float(args.get("market_impact_bps", 0.0), 0.0)
    _implementation_shortfall_proxy, _shortfall_source, shortfall_components, _tradability_summary, _capacity_summary = _estimate_implementation_shortfall(
        payload_context,
        args,
        closes=closes,
        volumes=volumes,
        explicit_slippage_rate=explicit_slippage,
        model_slippage_rate=model_slippage,
        market_impact_bps=market_impact_bps,
    )
    base_slippage_bps = 0.0 if slippage_calc is not None else float(shortfall_components.get("effective_slippage_bps") or 0.0)
    per_side_extra_cost_rate = max(0.0, base_slippage_bps / 10000.0)
    cash = float(initial_capital)
    shares = 0
    buy_price = 0.0
    buy_index = -1
    pending_exit = False
    trades = 0
    wins = 0
    equity = np.full(n, float(initial_capital), dtype=np.float64)
    trades_detail: List[Dict[str, Any]] = []
    fills_detail: List[Dict[str, Any]] = []
    total_traded_notional = 0.0
    holding_periods: List[int] = []
    order_attempt_count = 0
    failed_order_count = 0
    partial_fill_count = 0
    requested_shares_total = 0
    filled_shares_total = 0
    rejected_shares_total = 0
    blocked_reason_counts: Dict[str, int] = {}
    actual_participation_rates: List[float] = []
    adv_utilizations: List[float] = []
    execution_penalty_bps_notional = 0.0
    execution_penalty_bps_weight = 0.0
    reduce_units_by_index: Dict[int, float] = {}
    exit_reason_by_index: Dict[int, str] = {}
    round_trip_positions: List[Dict[str, Any]] = []
    current_round_trip: Optional[Dict[str, Any]] = None
    round_trip_sequence = 0
    closed_round_trip_count = 0
    winning_round_trip_count = 0
    if signal_events:
        for event in signal_events:
            idx = int(event.get("index") or 0)
            signal = int(event.get("signal") or 0)
            action = str(event.get("action") or "").strip().lower()
            if signal < 0 and action == "reduce":
                units = float(event.get("units") or 0.0)
                if 0 <= idx < n and units > 0:
                    reduce_units_by_index[idx] = min(1.0, max(reduce_units_by_index.get(idx, 0.0), units))
                    exit_reason_by_index[idx] = str(event.get("reason") or action)
            elif signal < 0 and action == "exit" and 0 <= idx < n:
                exit_reason_by_index[idx] = str(event.get("reason") or action)

    def _trade_time(index: int) -> str:
        if klines is None or index < 0 or index >= len(klines):
            return ""
        row = klines[index]
        return str(row.get("date", row.get("trade_date", row.get("time", ""))))

    def _start_round_trip(index: int, quantity: int, entry_price: float) -> None:
        nonlocal current_round_trip, round_trip_sequence
        round_trip_sequence += 1
        current_round_trip = {
            "round_trip_id": f"round_trip_{round_trip_sequence}",
            "status": "open",
            "entry_index": int(index),
            "entry_time": _trade_time(index),
            "entry_qty": int(quantity),
            "entry_notional": float(quantity * entry_price),
            "remaining_qty": int(quantity),
            "exited_qty": 0,
            "exit_notional": 0.0,
            "avg_entry_price": float(entry_price),
            "avg_exit_price": None,
            "realized_pnl": 0.0,
            "realized_return": None,
            "hold_days": None,
            "exit_index": None,
            "exit_time": None,
            "exit_reason": None,
            "partial_exit_count": 0,
            "exit_actions": [],
        }

    def _record_round_trip_exit(
        index: int,
        quantity: int,
        exit_price: float,
        realized_pnl: float,
        *,
        action: str,
        reason: Optional[str],
    ) -> None:
        nonlocal current_round_trip, closed_round_trip_count, winning_round_trip_count
        if current_round_trip is None or quantity <= 0:
            return
        current_round_trip["exited_qty"] = int(current_round_trip.get("exited_qty") or 0) + int(quantity)
        current_round_trip["remaining_qty"] = max(
            0,
            int(current_round_trip.get("remaining_qty") or 0) - int(quantity),
        )
        current_round_trip["exit_notional"] = float(current_round_trip.get("exit_notional") or 0.0) + float(quantity * exit_price)
        current_round_trip["realized_pnl"] = float(current_round_trip.get("realized_pnl") or 0.0) + float(realized_pnl)
        if int(current_round_trip.get("remaining_qty") or 0) > 0:
            current_round_trip["partial_exit_count"] = int(current_round_trip.get("partial_exit_count") or 0) + 1
        current_round_trip["exit_actions"] = list(current_round_trip.get("exit_actions") or []) + [
            {
                "index": int(index),
                "time": _trade_time(index),
                "action": action,
                "reason": reason,
                "qty": int(quantity),
                "price": float(exit_price),
                "realized_pnl": float(realized_pnl),
            }
        ]
        current_round_trip["exit_reason"] = str(reason or action or current_round_trip.get("exit_reason") or "").strip() or None
        if int(current_round_trip.get("remaining_qty") or 0) <= 0:
            entry_notional = float(current_round_trip.get("entry_notional") or 0.0)
            exited_qty = int(current_round_trip.get("exited_qty") or 0)
            current_round_trip.update(
                {
                    "status": "closed",
                    "avg_exit_price": float(current_round_trip.get("exit_notional") or 0.0) / max(exited_qty, 1),
                    "realized_return": (
                        float(current_round_trip.get("realized_pnl") or 0.0) / entry_notional
                        if entry_notional > 0
                        else 0.0
                    ),
                    "hold_days": max(1, int(index - int(current_round_trip.get("entry_index") or index))),
                    "exit_index": int(index),
                    "exit_time": _trade_time(index),
                }
            )
            round_trip_positions.append(current_round_trip)
            closed_round_trip_count += 1
            if float(current_round_trip.get("realized_pnl") or 0.0) > 0:
                winning_round_trip_count += 1
            current_round_trip = None

    def _finalize_open_round_trip(index: int, *, status: str, reason: Optional[str]) -> None:
        nonlocal current_round_trip
        if current_round_trip is None:
            return
        entry_notional = float(current_round_trip.get("entry_notional") or 0.0)
        exited_qty = int(current_round_trip.get("exited_qty") or 0)
        current_round_trip.update(
            {
                "status": status,
                "avg_exit_price": (
                    float(current_round_trip.get("exit_notional") or 0.0) / exited_qty
                    if exited_qty > 0
                    else None
                ),
                "realized_return": (
                    float(current_round_trip.get("realized_pnl") or 0.0) / entry_notional
                    if entry_notional > 0
                    else 0.0
                ),
                "hold_days": max(1, int(index - int(current_round_trip.get("entry_index") or index))),
                "exit_index": int(index) if exited_qty > 0 else None,
                "exit_time": _trade_time(index) if exited_qty > 0 else None,
                "exit_reason": str(reason or current_round_trip.get("exit_reason") or status).strip() or status,
            }
        )
        round_trip_positions.append(current_round_trip)
        current_round_trip = None

    def _round_trip_metrics() -> tuple[float, float]:
        closed_positions = [
            item for item in round_trip_positions if str(item.get("status") or "").lower() == "closed"
        ]
        win_rate = (
            float(winning_round_trip_count / max(closed_round_trip_count, 1))
            if closed_round_trip_count > 0
            else 0.0
        )
        avg_hold_days = (
            float(np.mean([float(item.get("hold_days") or 0.0) for item in closed_positions]))
            if closed_positions
            else 0.0
        )
        return win_rate, avg_hold_days

    for i in range(n - 1):
        tradable = True if tradability_mask is None else bool(tradability_mask[i])
        # Next-bar execution: signal on bar i, execute at bar i+1 close (proxy for next open)
        next_tradable = True if tradability_mask is None else bool(tradability_mask[i + 1])
        if entry_mask[i] and shares == 0 and cash > 0 and tradable and next_tradable:
            exec_price = float(closes[i + 1])
            approx_price = exec_price * (1 + commission_rate + per_side_extra_cost_rate)
            max_entry_notional = max(0.0, (cash + shares * closes[i]) * position_pct)
            affordable_cash = min(cash, max_entry_notional) if max_entry_notional > 0 else cash
            est_shares = int(affordable_cash / approx_price) if approx_price > 0 else 0
            est_shares = _round_down_lot(est_shares, lot_size)
            fill_info = _resolve_order_fill(
                est_shares,
                index=i + 1,
                volumes=volumes,
                tradability_mask=tradability_mask,
                lot_size=lot_size,
                args=args,
            )
            order_attempt_count += 1
            requested_shares_total += int(fill_info.get("requested_shares") or 0)
            filled_shares_total += int(fill_info.get("filled_shares") or 0)
            rejected_shares_total += int(fill_info.get("rejected_shares") or 0)
            if fill_info.get("actual_participation_rate"):
                actual_participation_rates.append(float(fill_info["actual_participation_rate"]))
            if fill_info.get("adv_utilization") is not None:
                adv_utilizations.append(float(fill_info["adv_utilization"]))
            if int(fill_info.get("filled_shares") or 0) <= 0:
                failed_order_count += 1
                blocked_reason = str(fill_info.get("blocked_reason") or "entry_blocked")
                blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1
                if return_trades:
                    trade_time = ""
                    if klines is not None and i + 1 < len(klines):
                        row = klines[i + 1]
                        trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
                    fills_detail.append(
                        {
                            "index": int(i + 1),
                            "time": trade_time,
                            "signal": 1,
                            "requested_shares": int(fill_info.get("requested_shares") or 0),
                            "filled_shares": 0,
                            "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                            "fill_ratio": 0.0,
                            "blocked_reason": blocked_reason,
                        }
                    )
                equity[i] = cash
                continue
            if fill_info.get("partial_fill"):
                partial_fill_count += 1
                blocked_reason = str(fill_info.get("blocked_reason") or "capacity_limited")
                blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1

            est_shares = int(fill_info.get("filled_shares") or 0)
            dynamic_extra_cost_rate = max(
                per_side_extra_cost_rate,
                float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
            )
            if slippage_calc is not None:
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i + 1]) if i + 1 < len(volumes) else 0.0,
                    order_size=float(est_shares),
                    is_buy=True,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            buy_price = exec_price * (1 + commission_rate + dynamic_extra_cost_rate)
            max_entry_notional = max(0.0, (cash + shares * closes[i]) * position_pct)
            affordable_cash = min(cash, max_entry_notional) if max_entry_notional > 0 else cash
            max_shares = int(affordable_cash / buy_price) if buy_price > 0 else 0
            max_shares = _round_down_lot(min(max_shares, est_shares), lot_size)
            if max_shares > 0:
                shares = max_shares
                cash -= shares * buy_price
                trades += 1
                buy_index = int(i + 1)
                pending_exit = False
                total_traded_notional += float(shares * buy_price)
                _start_round_trip(int(i + 1), shares, buy_price)
                execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * float(shares * buy_price)
                execution_penalty_bps_weight += float(shares * buy_price)
                if return_trades:
                    trade_time = _trade_time(int(i + 1))
                    trades_detail.append(
                        {
                            "index": int(i + 1),
                            "time": trade_time,
                            "price": float(buy_price),
                            "signal": 1,
                            "shares": int(shares),
                            "profit": 0.0,
                        }
                    )
                    fills_detail.append(
                        {
                            "index": int(i + 1),
                            "time": trade_time,
                            "price": float(buy_price),
                            "signal": 1,
                            "requested_shares": int(fill_info.get("requested_shares") or shares),
                            "filled_shares": int(shares),
                            "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                            "fill_ratio": round(int(shares) / max(int(fill_info.get("requested_shares") or shares), 1), 6),
                            "blocked_reason": fill_info.get("blocked_reason"),
                            "partial_fill": bool(fill_info.get("partial_fill")),
                        }
                    )

        elif (pending_exit or exit_mask[i] or i in reduce_units_by_index) and shares > 0 and tradable and next_tradable:
            if t_plus_one and buy_index >= 0 and (i + 1) <= buy_index:
                equity[i] = cash + shares * closes[i]
                continue
            pending_exit = True
            exec_price = float(closes[i + 1])
            requested_exit_shares = shares
            if i in reduce_units_by_index:
                requested_exit_shares = _round_down_lot(max(1, int(round(float(shares) * float(reduce_units_by_index[i])))), lot_size)
                if requested_exit_shares <= 0:
                    requested_exit_shares = shares
            fill_info = _resolve_order_fill(
                requested_exit_shares,
                index=i + 1,
                volumes=volumes,
                tradability_mask=tradability_mask,
                lot_size=lot_size,
                args=args,
            )
            order_attempt_count += 1
            requested_shares_total += int(fill_info.get("requested_shares") or 0)
            filled_shares_total += int(fill_info.get("filled_shares") or 0)
            rejected_shares_total += int(fill_info.get("rejected_shares") or 0)
            if fill_info.get("actual_participation_rate"):
                actual_participation_rates.append(float(fill_info["actual_participation_rate"]))
            if fill_info.get("adv_utilization") is not None:
                adv_utilizations.append(float(fill_info["adv_utilization"]))
            if int(fill_info.get("filled_shares") or 0) <= 0:
                failed_order_count += 1
                blocked_reason = str(fill_info.get("blocked_reason") or "exit_blocked")
                blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1
                if return_trades:
                    trade_time = ""
                    if klines is not None and i + 1 < len(klines):
                        row = klines[i + 1]
                        trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
                    fills_detail.append(
                        {
                            "index": int(i + 1),
                            "time": trade_time,
                            "signal": -1,
                            "action": "reduce" if i in reduce_units_by_index else "exit",
                            "reason": exit_reason_by_index.get(i),
                            "requested_shares": int(fill_info.get("requested_shares") or 0),
                            "filled_shares": 0,
                            "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                            "fill_ratio": 0.0,
                            "blocked_reason": blocked_reason,
                        }
                    )
                equity[i] = cash + shares * closes[i]
                continue
            if fill_info.get("partial_fill"):
                partial_fill_count += 1
                blocked_reason = str(fill_info.get("blocked_reason") or "capacity_limited")
                blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1
            sell_shares = int(fill_info.get("filled_shares") or 0)
            dynamic_extra_cost_rate = max(
                per_side_extra_cost_rate,
                float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
            )
            if slippage_calc is not None:
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i + 1]) if i + 1 < len(volumes) else 0.0,
                    order_size=float(sell_shares),
                    is_buy=False,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            sell_price = exec_price * (1 - commission_rate - dynamic_extra_cost_rate - sell_tax_rate)
            sell_price = max(0.0, sell_price)
            revenue = sell_shares * sell_price
            avg_entry_cost = (
                float(current_round_trip.get("entry_notional") or 0.0) / max(int(current_round_trip.get("entry_qty") or 0), 1)
                if current_round_trip is not None
                else float(buy_price)
            )
            profit = revenue - (sell_shares * avg_entry_cost)
            cash += revenue
            trades += 1
            total_traded_notional += float(revenue)
            execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * float(revenue)
            execution_penalty_bps_weight += float(revenue)
            if buy_index >= 0 and shares == sell_shares:
                holding_periods.append(max(1, int(i + 1 - buy_index)))
            _record_round_trip_exit(
                int(i + 1),
                sell_shares,
                sell_price,
                profit,
                action="reduce" if i in reduce_units_by_index else "exit",
                reason=exit_reason_by_index.get(i),
            )
            if return_trades:
                trade_time = _trade_time(int(i + 1))
                trades_detail.append(
                    {
                        "index": int(i + 1),
                            "time": trade_time,
                            "price": float(sell_price),
                            "signal": -1,
                            "action": "reduce" if i in reduce_units_by_index else "exit",
                            "reason": exit_reason_by_index.get(i),
                            "shares": int(sell_shares),
                            "profit": float(profit),
                            "holding_days": max(1, int(i + 1 - buy_index)) if buy_index >= 0 else 0,
                        }
                    )
                fills_detail.append(
                    {
                        "index": int(i + 1),
                        "time": trade_time,
                        "price": float(sell_price),
                        "signal": -1,
                        "action": "reduce" if i in reduce_units_by_index else "exit",
                        "reason": exit_reason_by_index.get(i),
                        "requested_shares": int(fill_info.get("requested_shares") or sell_shares),
                        "filled_shares": int(sell_shares),
                        "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                        "fill_ratio": round(int(sell_shares) / max(int(fill_info.get("requested_shares") or sell_shares), 1), 6),
                        "blocked_reason": fill_info.get("blocked_reason"),
                        "partial_fill": bool(fill_info.get("partial_fill")),
                    }
                )
            shares = max(0, shares - sell_shares)
            if shares == 0:
                buy_index = -1
                pending_exit = False
            elif i in reduce_units_by_index:
                pending_exit = False

        equity[i] = cash + shares * closes[i]
    equity[n - 1] = cash + shares * float(closes[n - 1])

    if shares > 0:
        i = n - 1
        exec_price = float(closes[i])
        fill_info = _resolve_order_fill(
            shares,
            index=i,
            volumes=volumes,
            tradability_mask=tradability_mask,
            lot_size=lot_size,
            args=args,
        )
        order_attempt_count += 1
        requested_shares_total += int(fill_info.get("requested_shares") or 0)
        filled_shares_total += int(fill_info.get("filled_shares") or 0)
        rejected_shares_total += int(fill_info.get("rejected_shares") or 0)
        if fill_info.get("actual_participation_rate"):
            actual_participation_rates.append(float(fill_info["actual_participation_rate"]))
        if fill_info.get("adv_utilization") is not None:
            adv_utilizations.append(float(fill_info["adv_utilization"]))
        if int(fill_info.get("filled_shares") or 0) <= 0:
            failed_order_count += 1
            blocked_reason = str(fill_info.get("blocked_reason") or "final_exit_blocked")
            blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1
            if return_trades:
                trade_time = _trade_time(int(i))
                fills_detail.append(
                    {
                        "index": int(i),
                        "time": trade_time,
                        "signal": -1,
                        "requested_shares": int(fill_info.get("requested_shares") or 0),
                        "filled_shares": 0,
                        "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                        "fill_ratio": 0.0,
                        "blocked_reason": blocked_reason,
                    }
                )
            equity[n - 1] = cash + shares * float(closes[n - 1])
            _finalize_open_round_trip(int(i), status="incomplete", reason=blocked_reason)
            shares = 0
            buy_index = -1
            win_rate, avg_holding_days = _round_trip_metrics()
            return {
                "final_capital": float(equity[n - 1]),
                "total_return": float((float(equity[n - 1]) - initial_capital) / initial_capital if initial_capital > 0 else 0.0),
                "max_drawdown": float(np.max((np.maximum.accumulate(equity) - equity) / np.maximum(np.maximum.accumulate(equity), 1e-9))),
                "sharpe_ratio": 0.0,
                "trades_count": int(trades),
                "win_rate": float(win_rate),
                "avg_holding_days": float(avg_holding_days),
                "turnover_proxy": float(total_traded_notional / initial_capital) if initial_capital > 0 else 0.0,
                "equity": equity,
                "round_trip_positions": round_trip_positions,
                "closed_round_trip_count": int(closed_round_trip_count),
                "winning_round_trip_count": int(winning_round_trip_count),
                "trades": trades_detail if return_trades else None,
                "fills": fills_detail if return_trades else None,
                "execution_summary": {
                    "order_attempt_count": int(order_attempt_count),
                    "failed_order_count": int(failed_order_count),
                    "partial_fill_count": int(partial_fill_count),
                    "requested_shares": int(requested_shares_total),
                    "filled_shares": int(filled_shares_total),
                    "rejected_shares": int(rejected_shares_total),
                    "fill_rate": round(filled_shares_total / max(requested_shares_total, 1), 6) if requested_shares_total > 0 else 0.0,
                    "failed_fill_rate": round(failed_order_count / max(order_attempt_count, 1), 6) if order_attempt_count > 0 else 0.0,
                    "blocked_reason_counts": blocked_reason_counts,
                },
            }
        if fill_info.get("partial_fill"):
            partial_fill_count += 1
            blocked_reason = str(fill_info.get("blocked_reason") or "capacity_limited")
            blocked_reason_counts[blocked_reason] = blocked_reason_counts.get(blocked_reason, 0) + 1
        sell_shares = int(fill_info.get("filled_shares") or 0)
        dynamic_extra_cost_rate = max(
            per_side_extra_cost_rate,
            float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
        )
        if slippage_calc is not None:
            slip = slippage_calc.calculate(
                price=exec_price,
                volume=float(volumes[i]) if i < len(volumes) else 0.0,
                order_size=float(sell_shares),
                is_buy=False,
            )
            exec_price = float(slip.get("execution_price", exec_price))
        sell_price = exec_price * (1 - commission_rate - dynamic_extra_cost_rate - sell_tax_rate)
        sell_price = max(0.0, sell_price)
        revenue = sell_shares * sell_price
        avg_entry_cost = (
            float(current_round_trip.get("entry_notional") or 0.0) / max(int(current_round_trip.get("entry_qty") or 0), 1)
            if current_round_trip is not None
            else float(buy_price)
        )
        profit = revenue - (sell_shares * avg_entry_cost)
        cash += revenue
        trades += 1
        total_traded_notional += float(revenue)
        execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * float(revenue)
        execution_penalty_bps_weight += float(revenue)
        if buy_index >= 0:
            holding_periods.append(max(1, int(i - buy_index)))
        _record_round_trip_exit(
            int(i),
            sell_shares,
            sell_price,
            profit,
            action="exit",
            reason="final_exit",
        )
        if return_trades:
            trade_time = _trade_time(int(i))
            trades_detail.append(
                {
                        "index": int(i),
                        "time": trade_time,
                        "price": float(sell_price),
                        "signal": -1,
                        "shares": int(sell_shares),
                        "profit": float(profit),
                        "holding_days": max(1, int(i - buy_index)) if buy_index >= 0 else 0,
                    }
                )
            fills_detail.append(
                {
                    "index": int(i),
                    "time": trade_time,
                    "price": float(sell_price),
                    "signal": -1,
                    "requested_shares": int(fill_info.get("requested_shares") or sell_shares),
                    "filled_shares": int(sell_shares),
                    "rejected_shares": int(fill_info.get("rejected_shares") or 0),
                    "fill_ratio": round(int(sell_shares) / max(int(fill_info.get("requested_shares") or sell_shares), 1), 6),
                    "blocked_reason": fill_info.get("blocked_reason"),
                    "partial_fill": bool(fill_info.get("partial_fill")),
                }
            )
        shares = max(0, shares - sell_shares)
        buy_index = -1
        if shares > 0:
            _finalize_open_round_trip(int(i), status="incomplete", reason="final_exit_partial_fill")

    final_capital = float(cash + shares * float(closes[n - 1]))
    total_return = (final_capital - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    max_dd = 0.0
    peak = float(equity[0]) if len(equity) else float(initial_capital)
    for val in equity:
        if val > peak:
            peak = float(val)
        if peak > 0:
            dd = (peak - float(val)) / peak
            if dd > max_dd:
                max_dd = dd

    sharpe = 0.0
    if len(equity) > 1:
        eq_prev = equity[:-1]
        eq_next = equity[1:]
        valid = eq_prev > 0
        if np.any(valid):
            rets = (eq_next[valid] - eq_prev[valid]) / eq_prev[valid]
            if len(rets) > 1:
                std = float(np.std(rets))
                if std > 0:
                    annual_ret = float(np.mean(rets)) * 252.0
                    annual_std = std * np.sqrt(252.0)
                    risk_free_rate = 0.02  # 年化无风险利率
                    sharpe = float((annual_ret - risk_free_rate) / annual_std)

    if current_round_trip is not None:
        _finalize_open_round_trip(int(n - 1), status="open_mark_to_market", reason="backtest_ended_with_open_position")
    win_rate, avg_holding_days = _round_trip_metrics()
    turnover_proxy = (total_traded_notional / initial_capital) if initial_capital > 0 else 0.0
    fill_rate = (filled_shares_total / requested_shares_total) if requested_shares_total > 0 else 0.0
    failed_fill_rate = (failed_order_count / order_attempt_count) if order_attempt_count > 0 else 0.0
    execution_summary = {
        "order_attempt_count": int(order_attempt_count),
        "filled_order_count": int(max(0, order_attempt_count - failed_order_count)),
        "failed_order_count": int(failed_order_count),
        "partial_fill_count": int(partial_fill_count),
        "requested_shares": int(requested_shares_total),
        "filled_shares": int(filled_shares_total),
        "rejected_shares": int(rejected_shares_total),
        "fill_rate": round(fill_rate, 6),
        "failed_fill_rate": round(failed_fill_rate, 6),
        "blocked_reason_counts": dict(blocked_reason_counts),
        "avg_participation_rate": round(float(np.mean(actual_participation_rates)), 6) if actual_participation_rates else 0.0,
        "max_participation_rate": round(float(np.max(actual_participation_rates)), 6) if actual_participation_rates else 0.0,
        "avg_adv_utilization": round(float(np.mean(adv_utilizations)), 6) if adv_utilizations else None,
        "max_adv_utilization": round(float(np.max(adv_utilizations)), 6) if adv_utilizations else None,
        "avg_execution_penalty_bps": round(
            execution_penalty_bps_notional / execution_penalty_bps_weight,
            4,
        ) if execution_penalty_bps_weight > 0 else 0.0,
    }
    return {
        "final_capital": final_capital,
        "total_return": float(total_return),
        "max_drawdown": float(max_dd),
        "sharpe_ratio": float(sharpe),
        "trades_count": int(trades),
        "win_rate": float(win_rate),
        "avg_holding_days": float(avg_holding_days),
        "turnover_proxy": float(turnover_proxy),
        "equity": equity,
        "round_trip_positions": round_trip_positions,
        "closed_round_trip_count": int(closed_round_trip_count),
        "winning_round_trip_count": int(winning_round_trip_count),
        "trades": trades_detail if return_trades else None,
        "fills": fills_detail if return_trades else None,
        "execution_summary": execution_summary,
    }
