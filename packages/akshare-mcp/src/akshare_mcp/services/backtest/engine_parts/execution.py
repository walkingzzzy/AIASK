
    @staticmethod
    def run_portfolio_backtest(
        market_data: Dict[str, List[Union[Dict[str, Any], Any]]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        return_trades: bool = False,
    ) -> Dict[str, Any]:
        if not market_data:
            return {'success': False, 'error': 'No portfolio market data'}

        normalized_data: dict[str, list[dict[str, Any]]] = {}
        for raw_code, raw_klines in dict(market_data or {}).items():
            code = str(raw_code or '').strip()
            if not code or not raw_klines:
                continue
            rows = _ensure_dict_list(raw_klines)
            if rows:
                normalized_data[code] = rows
        if len(normalized_data) <= 1:
            return {'success': False, 'error': 'Portfolio backtest requires at least two instruments'}

        common_len = min(len(rows) for rows in normalized_data.values())
        if common_len < 3:
            return {'success': False, 'error': 'Insufficient shared kline data for portfolio backtest'}

        args = dict(params or {})
        initial_capital = float(args.get("initial_capital", 100000) or 100000)
        commission = float(args.get("commission", 0.0003) or 0.0)
        codes = list(normalized_data.keys())
        weights, normalized_scheme, allocation_mode = _resolve_portfolio_weights(codes, args)
        active_codes = [code for code in codes if float(weights.get(code, 0.0) or 0.0) > 0]
        if len(active_codes) <= 1:
            return {'success': False, 'error': 'Portfolio backtest requires at least two weighted instruments'}

        slippage_model_raw = args.get("slippage_model")
        slippage_calc: Optional[SlippageCalculator] = None
        if slippage_model_raw:
            normalized_slippage_model = str(slippage_model_raw).strip().lower()
            if normalized_slippage_model in {"fixed", "volume_based", "market_impact"}:
                slippage_calc = SlippageCalculator(
                    model_type=_resolve_slippage_model(normalized_slippage_model)
                )

        a_share_rules = str(args.get("market_ruleset") or "cn_equity").strip().lower() in {"cn_equity", "a_share", "ashare", "cn_stock", "china_equity"}
        lot_size = max(1, int(args.get("min_trade_lot", 100 if a_share_rules else 1) or (100 if a_share_rules else 1)))
        sell_tax_rate = _safe_float(args.get("sell_tax_rate"), 0.001 if a_share_rules else 0.0)
        t_plus_one = bool(args.get("t_plus_one", a_share_rules))

        portfolio_payload_context = {
            "tradable_days": 0,
            "total_days": int(common_len),
            "tradability_filter": bool(args.get("tradability_filter", False)),
        }
        closes_by_code: dict[str, np.ndarray] = {}
        volumes_by_code: dict[str, np.ndarray] = {}
        tradability_masks: dict[str, np.ndarray | None] = {}
        entry_masks: dict[str, np.ndarray] = {}
        exit_masks: dict[str, np.ndarray] = {}
        signal_events_by_code: dict[str, list[dict[str, Any]]] = {}
        aligned_klines: dict[str, list[dict[str, Any]]] = {}
        tradable_day_min: Optional[int] = None

        for code in active_codes:
            rows = list(normalized_data.get(code) or [])[-common_len:]
            closes = np.array([float(item.get('close', 0.0) or 0.0) for item in rows], dtype=float)
            volumes = np.array([float(item.get('volume', 0.0) or 0.0) for item in rows], dtype=float)
            if closes.size != common_len or np.count_nonzero(closes > 0) < 3:
                return {'success': False, 'error': f'Insufficient aligned kline data for {code}'}

            tradability_mask: Optional[np.ndarray] = None
            if bool(args.get("tradability_filter", False)):
                tradability_mask = _build_tradability_mask(
                    closes=closes,
                    volumes=volumes,
                    code=code,
                    is_st=bool(args.get("is_st", False)),
                )
                tradable_days = int(np.sum(tradability_mask))
                tradable_day_min = tradable_days if tradable_day_min is None else min(tradable_day_min, tradable_days)
            masks = _build_portfolio_strategy_masks(strategy, rows, closes, volumes, args)
            if masks is None:
                return {'success': False, 'error': f'Insufficient data for strategy signals on {code}'}

            closes_by_code[code] = closes
            volumes_by_code[code] = volumes
            tradability_masks[code] = tradability_mask
            entry_masks[code], exit_masks[code], signal_events = masks
            signal_events_by_code[code] = list(signal_events or [])
            aligned_klines[code] = rows

        if tradable_day_min is not None:
            portfolio_payload_context["tradable_days"] = int(tradable_day_min)

        explicit_slippage = _safe_float(args.get("slippage", 0.0), 0.0)
        portfolio_closes = np.average(
            np.vstack([closes_by_code[code] for code in active_codes]),
            axis=0,
            weights=[float(weights.get(code, 0.0) or 0.0) for code in active_codes],
        )
        portfolio_volumes = np.sum(
            np.vstack([volumes_by_code[code] for code in active_codes]),
            axis=0,
        )
        model_slippage_rate = _compute_slippage_rate(portfolio_closes, portfolio_volumes, args, 0.0)
        market_impact_bps = _safe_float(args.get("market_impact_bps", 0.0), 0.0)
        _implementation_shortfall_proxy, _shortfall_source, shortfall_components, _tradability_summary, _capacity_summary = _estimate_implementation_shortfall(
            portfolio_payload_context,
            args,
            closes=portfolio_closes,
            volumes=portfolio_volumes,
            explicit_slippage_rate=explicit_slippage,
            model_slippage_rate=model_slippage_rate,
            market_impact_bps=market_impact_bps,
        )
        base_slippage_bps = 0.0 if slippage_calc is not None else float(shortfall_components.get("effective_slippage_bps") or 0.0)
        per_side_extra_cost_rate = max(0.0, base_slippage_bps / 10000.0)

        cash = float(initial_capital)
        holdings: dict[str, int] = {code: 0 for code in active_codes}
        position_cost_basis: dict[str, float] = {}
        entry_indices: dict[str, int] = {}
        pending_exit: dict[str, bool] = {code: False for code in active_codes}
        position_realized_profit: dict[str, float] = {code: 0.0 for code in active_codes}
        equity = np.full(common_len, float(initial_capital), dtype=np.float64)
        cash_curve = np.full(common_len, float(initial_capital), dtype=np.float64)
        gross_exposure_curve = np.zeros(common_len, dtype=np.float64)
        net_exposure_curve = np.zeros(common_len, dtype=np.float64)
        trades_detail: List[Dict[str, Any]] = []
        fills_detail: List[Dict[str, Any]] = []
        total_traded_notional = 0.0
        holding_periods: List[int] = []
        completed_round_trips = 0
        wins = 0
        executed_codes: set[str] = set()
        order_attempt_count = 0
        failed_order_count = 0
        partial_fill_count = 0
        requested_shares_total = 0
        filled_shares_total = 0
        rejected_shares_total = 0
        blocked_reason_counts: dict[str, int] = {}
        actual_participation_rates: list[float] = []
        adv_utilizations: list[float] = []
        execution_penalty_bps_notional = 0.0
        execution_penalty_bps_weight = 0.0

        def _mark_equity(index: int) -> None:
            gross_notional = sum(float(holdings[code]) * float(closes_by_code[code][index]) for code in active_codes)
            mark_to_market = cash + gross_notional
            equity[index] = mark_to_market
            cash_curve[index] = cash
            exposure_ratio = gross_notional / mark_to_market if mark_to_market > 0 else 0.0
            gross_exposure_curve[index] = exposure_ratio
            net_exposure_curve[index] = exposure_ratio

        def _record_fill_attempt(
            *,
            code: str,
            fill_info: dict[str, Any],
            index: int,
            signal: int,
            price: Optional[float] = None,
            profit: Optional[float] = None,
            holding_days: Optional[int] = None,
        ) -> None:
            nonlocal order_attempt_count, failed_order_count, partial_fill_count
            nonlocal requested_shares_total, filled_shares_total, rejected_shares_total
            requested = int(fill_info.get("requested_shares") or 0)
            filled = int(fill_info.get("filled_shares") or 0)
            rejected = int(fill_info.get("rejected_shares") or 0)
            order_attempt_count += 1
            requested_shares_total += requested
            filled_shares_total += filled
            rejected_shares_total += rejected
            participation = fill_info.get("actual_participation_rate")
            if participation:
                actual_participation_rates.append(float(participation))
            adv_util = fill_info.get("adv_utilization")
            if adv_util is not None:
                adv_utilizations.append(float(adv_util))
            if filled <= 0:
                failed_order_count += 1
                reason = str(fill_info.get("blocked_reason") or "fill_blocked")
                blocked_reason_counts[reason] = blocked_reason_counts.get(reason, 0) + 1
            elif fill_info.get("partial_fill"):
                partial_fill_count += 1
                reason = str(fill_info.get("blocked_reason") or "capacity_limited")
                blocked_reason_counts[reason] = blocked_reason_counts.get(reason, 0) + 1

            if not return_trades:
                return
            fills_detail.append(
                {
                    "code": code,
                    "index": int(index),
                    "time": str(aligned_klines[code][index].get('date', aligned_klines[code][index].get('trade_date', aligned_klines[code][index].get('time', '')))),
                    "signal": int(signal),
                    "price": None if price is None else float(price),
                    "requested_shares": requested,
                    "filled_shares": filled,
                    "rejected_shares": rejected,
                    "fill_ratio": round(filled / max(requested, 1), 6) if requested > 0 else 0.0,
                    "blocked_reason": fill_info.get("blocked_reason"),
                    "partial_fill": bool(fill_info.get("partial_fill")),
                    "profit": None if profit is None else float(profit),
                    "holding_days": None if holding_days is None else int(holding_days),
                }
            )

        for i in range(common_len - 1):
            next_index = int(i + 1)

            for code in active_codes:
                shares = int(holdings.get(code) or 0)
                reduce_event = next(
                    (
                        item for item in signal_events_by_code.get(code, [])
                        if int(item.get('index') or -1) == i and int(item.get('signal') or 0) < 0 and str(item.get('action') or '').strip().lower() == 'reduce'
                    ),
                    None,
                )
                if shares <= 0 or not (bool(exit_masks[code][i]) or bool(pending_exit.get(code)) or reduce_event is not None):
                    continue
                buy_index = int(entry_indices.get(code, -1))
                if t_plus_one and buy_index >= 0 and next_index <= buy_index:
                    continue

                pending_exit[code] = True
                fill_info = _resolve_order_fill(
                    shares,
                    index=next_index,
                    volumes=volumes_by_code[code],
                    tradability_mask=tradability_masks.get(code),
                    lot_size=lot_size,
                    args=args,
                )
                requested_exit_shares = shares
                if reduce_event is not None:
                    requested_exit_shares = _round_down_lot(
                        max(1, int(round(float(shares) * float(reduce_event.get('units') or 0.0)))),
                        lot_size,
                    )
                    if requested_exit_shares <= 0:
                        requested_exit_shares = shares
                    fill_info = _resolve_order_fill(
                        requested_exit_shares,
                        index=next_index,
                        volumes=volumes_by_code[code],
                        tradability_mask=tradability_masks.get(code),
                        lot_size=lot_size,
                        args=args,
                    )
                if int(fill_info.get("filled_shares") or 0) <= 0:
                    _record_fill_attempt(code=code, fill_info=fill_info, index=next_index, signal=-1)
                    continue

                filled_shares = int(fill_info.get("filled_shares") or 0)
                exec_price = float(closes_by_code[code][next_index])
                dynamic_extra_cost_rate = max(
                    per_side_extra_cost_rate,
                    float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
                )
                if slippage_calc is not None:
                    slip = slippage_calc.calculate(
                        price=exec_price,
                        volume=float(volumes_by_code[code][next_index]) if next_index < len(volumes_by_code[code]) else 0.0,
                        order_size=float(filled_shares),
                        is_buy=False,
                    )
                    exec_price = float(slip.get("execution_price", exec_price))
                sell_price = max(0.0, exec_price * (1 - commission - dynamic_extra_cost_rate - sell_tax_rate))
                revenue = float(filled_shares) * sell_price
                shares_before = int(holdings.get(code) or 0)
                average_cost = (
                    float(position_cost_basis.get(code, 0.0)) / float(shares_before)
                    if shares_before > 0
                    else 0.0
                )
                realized_cost = average_cost * float(filled_shares)
                profit = float(revenue - realized_cost)
                total_traded_notional += revenue
                execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * revenue
                execution_penalty_bps_weight += revenue
                cash += revenue
                holdings[code] = max(0, shares_before - filled_shares)
                position_cost_basis[code] = average_cost * float(holdings[code])
                position_realized_profit[code] = float(position_realized_profit.get(code, 0.0) + profit)
                holding_days = max(1, next_index - buy_index) if buy_index >= 0 else 0
                if return_trades:
                    trades_detail.append(
                        {
                            'code': code,
                            'index': next_index,
                            'time': str(aligned_klines[code][next_index].get('date', aligned_klines[code][next_index].get('trade_date', aligned_klines[code][next_index].get('time', '')))),
                            'price': float(sell_price),
                            'signal': -1,
                            'action': 'reduce' if reduce_event is not None else 'exit',
                            'reason': (reduce_event or {}).get('reason'),
                            'shares': int(filled_shares),
                            'profit': float(profit),
                            'holding_days': holding_days,
                        }
                    )
                _record_fill_attempt(
                    code=code,
                    fill_info=fill_info,
                    index=next_index,
                    signal=-1,
                    price=float(sell_price),
                    profit=float(profit),
                    holding_days=holding_days,
                )
                if reduce_event is not None and holdings[code] > 0:
                    pending_exit[code] = False
                if holdings[code] <= 0:
                    if float(position_realized_profit.get(code, 0.0)) > 0:
                        wins += 1
                    if buy_index >= 0:
                        holding_periods.append(max(1, next_index - buy_index))
                    completed_round_trips += 1
                    pending_exit[code] = False
                    position_realized_profit[code] = 0.0
                    position_cost_basis.pop(code, None)
                    entry_indices.pop(code, None)

            equity_before_entry = cash
            for code in active_codes:
                shares = int(holdings.get(code) or 0)
                if shares > 0:
                    equity_before_entry += float(shares) * float(closes_by_code[code][i])

            for code in sorted(active_codes, key=lambda item: (-float(weights.get(item, 0.0) or 0.0), item)):
                if int(holdings.get(code) or 0) > 0 or not bool(entry_masks[code][i]):
                    continue
                tradability_mask = tradability_masks.get(code)
                tradable_now = True if tradability_mask is None else bool(tradability_mask[i])
                tradable_next = True if tradability_mask is None else bool(tradability_mask[next_index])
                if not (tradable_now and tradable_next):
                    continue

                base_weight = float(weights.get(code, 0.0) or 0.0)
                if base_weight <= 0:
                    continue
                target_notional = max(0.0, equity_before_entry * base_weight)
                if target_notional <= 0 or cash <= 0:
                    continue

                exec_price = float(closes_by_code[code][next_index])
                approx_price = exec_price * (1 + commission + per_side_extra_cost_rate)
                if approx_price <= 0:
                    continue
                affordable_notional = min(cash, target_notional)
                estimated_shares = _round_down_lot(int(affordable_notional / approx_price), lot_size)
                if estimated_shares <= 0:
                    continue

                fill_info = _resolve_order_fill(
                    estimated_shares,
                    index=next_index,
                    volumes=volumes_by_code[code],
                    tradability_mask=tradability_masks.get(code),
                    lot_size=lot_size,
                    args=args,
                )
                if int(fill_info.get("filled_shares") or 0) <= 0:
                    _record_fill_attempt(code=code, fill_info=fill_info, index=next_index, signal=1)
                    continue

                dynamic_extra_cost_rate = max(
                    per_side_extra_cost_rate,
                    float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
                )
                if slippage_calc is not None:
                    slip = slippage_calc.calculate(
                        price=exec_price,
                        volume=float(volumes_by_code[code][next_index]) if next_index < len(volumes_by_code[code]) else 0.0,
                        order_size=float(fill_info.get("filled_shares") or estimated_shares),
                        is_buy=True,
                    )
                    exec_price = float(slip.get("execution_price", exec_price))

                buy_price = exec_price * (1 + commission + dynamic_extra_cost_rate)
                if buy_price <= 0:
                    continue
                shares = _round_down_lot(
                    int(min(cash / buy_price, float(fill_info.get("filled_shares") or estimated_shares))),
                    lot_size,
                )
                if shares <= 0:
                    _record_fill_attempt(
                        code=code,
                        fill_info={
                            **dict(fill_info),
                            "filled_shares": 0,
                            "rejected_shares": int(fill_info.get("requested_shares") or estimated_shares),
                            "blocked_reason": "cash_insufficient_after_slippage",
                            "partial_fill": False,
                        },
                        index=next_index,
                        signal=1,
                    )
                    continue

                trade_cost = float(shares) * buy_price
                cash -= trade_cost
                holdings[code] = shares
                position_cost_basis[code] = trade_cost
                entry_indices[code] = next_index
                pending_exit[code] = False
                position_realized_profit[code] = 0.0
                total_traded_notional += trade_cost
                execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * trade_cost
                execution_penalty_bps_weight += trade_cost
                executed_codes.add(code)
                if return_trades:
                    trades_detail.append(
                        {
                            'code': code,
                            'index': next_index,
                            'time': str(aligned_klines[code][next_index].get('date', aligned_klines[code][next_index].get('trade_date', aligned_klines[code][next_index].get('time', '')))),
                            'price': float(buy_price),
                            'signal': 1,
                            'shares': int(shares),
                            'profit': 0.0,
                        }
                    )
                _record_fill_attempt(
                    code=code,
                    fill_info={
                        **dict(fill_info),
                        "filled_shares": int(shares),
                        "rejected_shares": max(0, int(fill_info.get("requested_shares") or shares) - int(shares)),
                        "partial_fill": int(shares) < int(fill_info.get("requested_shares") or shares),
                        "blocked_reason": (
                            "cash_insufficient_after_slippage"
                            if int(shares) < int(fill_info.get("filled_shares") or shares)
                            else fill_info.get("blocked_reason")
                        ),
                    },
                    index=next_index,
                    signal=1,
                    price=float(buy_price),
                    profit=0.0,
                )

            _mark_equity(i)

        last_index = common_len - 1
        for code in active_codes:
            shares = int(holdings.get(code) or 0)
            if shares <= 0:
                continue
            fill_info = _resolve_order_fill(
                shares,
                index=last_index,
                volumes=volumes_by_code[code],
                tradability_mask=tradability_masks.get(code),
                lot_size=lot_size,
                args=args,
            )
            if int(fill_info.get("filled_shares") or 0) <= 0:
                _record_fill_attempt(code=code, fill_info=fill_info, index=last_index, signal=-1)
                continue

            filled_shares = int(fill_info.get("filled_shares") or 0)
            exec_price = float(closes_by_code[code][last_index])
            dynamic_extra_cost_rate = max(
                per_side_extra_cost_rate,
                float(fill_info.get("execution_penalty_bps") or 0.0) / 10000.0 / 2.0,
            )
            if slippage_calc is not None:
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes_by_code[code][last_index]) if last_index < len(volumes_by_code[code]) else 0.0,
                    order_size=float(filled_shares),
                    is_buy=False,
                )
                exec_price = float(slip.get("execution_price", exec_price))
            sell_price = max(0.0, exec_price * (1 - commission - dynamic_extra_cost_rate - sell_tax_rate))
            revenue = float(filled_shares) * sell_price
            shares_before = int(holdings.get(code) or 0)
            average_cost = (
                float(position_cost_basis.get(code, 0.0)) / float(shares_before)
                if shares_before > 0
                else 0.0
            )
            realized_cost = average_cost * float(filled_shares)
            profit = revenue - realized_cost
            position_realized_profit[code] = float(position_realized_profit.get(code, 0.0) + profit)
            holdings[code] = max(0, shares_before - filled_shares)
            position_cost_basis[code] = average_cost * float(holdings[code])
            buy_index = int(entry_indices.get(code, -1))
            if buy_index >= 0 and holdings[code] <= 0:
                holding_periods.append(max(1, last_index - buy_index))
            total_traded_notional += revenue
            execution_penalty_bps_notional += float(fill_info.get("execution_penalty_bps") or 0.0) * revenue
            execution_penalty_bps_weight += revenue
            cash += revenue
            holding_days = max(1, last_index - buy_index) if buy_index >= 0 else 0
            if return_trades:
                trades_detail.append(
                    {
                        'code': code,
                        'index': last_index,
                        'time': str(aligned_klines[code][last_index].get('date', aligned_klines[code][last_index].get('trade_date', aligned_klines[code][last_index].get('time', '')))),
                        'price': float(sell_price),
                        'signal': -1,
                        'shares': int(filled_shares),
                        'profit': float(profit),
                        'holding_days': holding_days,
                    }
                )
            _record_fill_attempt(
                code=code,
                fill_info=fill_info,
                index=last_index,
                signal=-1,
                price=float(sell_price),
                profit=float(profit),
                holding_days=holding_days,
            )
            if holdings[code] <= 0:
                if float(position_realized_profit.get(code, 0.0)) > 0:
                    wins += 1
                completed_round_trips += 1
                position_realized_profit[code] = 0.0
                position_cost_basis.pop(code, None)
                entry_indices.pop(code, None)
                pending_exit[code] = False

        _mark_equity(last_index)
        final_capital, total_return, max_dd, sharpe = _summarize_portfolio_equity(equity, initial_capital)
        avg_holding_days = float(np.mean(holding_periods)) if holding_periods else 0.0
        turnover_proxy = (total_traded_notional / initial_capital) if initial_capital > 0 else 0.0
        win_rate = (wins / completed_round_trips) if completed_round_trips > 0 else 0.0
        execution_summary = {
            "order_attempt_count": int(order_attempt_count),
            "filled_order_count": int(max(0, order_attempt_count - failed_order_count)),
            "failed_order_count": int(failed_order_count),
            "partial_fill_count": int(partial_fill_count),
            "requested_shares": int(requested_shares_total),
            "filled_shares": int(filled_shares_total),
            "rejected_shares": int(rejected_shares_total),
            "fill_rate": round(filled_shares_total / max(requested_shares_total, 1), 6) if requested_shares_total > 0 else 0.0,
            "failed_fill_rate": round(failed_order_count / max(order_attempt_count, 1), 6) if order_attempt_count > 0 else 0.0,
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

        payload = {
            'strategy': strategy,
            'portfolio_mode': 'shared_cash',
            'portfolio_engine_version': 'shared_cash_v1',
            'component_count': len(active_codes),
            'component_codes': active_codes,
            'allocation_mode': allocation_mode,
            'allocation_weights': {code: round(float(weights.get(code, 0.0) or 0.0), 6) for code in active_codes if float(weights.get(code, 0.0) or 0.0) > 0},
            'requested_weight_scheme': normalized_scheme,
            'executed_component_codes': sorted(executed_codes),
            'initial_capital': float(initial_capital),
            'final_capital': float(final_capital),
            'total_return': float(total_return),
            'max_drawdown': float(max_dd),
            'sharpe_ratio': float(sharpe),
            'trades_count': int(len(trades_detail)) if return_trades else int(max(0, order_attempt_count - failed_order_count)),
            'win_rate': float(win_rate),
            'avg_holding_days': float(avg_holding_days),
            'turnover_proxy': float(turnover_proxy),
            'cash_curve': cash_curve.astype(float, copy=False).tolist(),
            'gross_exposure_curve': gross_exposure_curve.astype(float, copy=False).tolist(),
            'net_exposure_curve': net_exposure_curve.astype(float, copy=False).tolist(),
            'execution_summary': execution_summary,
            'params': args,
        }
        if return_trades:
            payload['trades'] = list(trades_detail)
            payload['fills'] = list(fills_detail)
        _finalize_backtest_payload(payload, equity, params=args, closes=portfolio_closes, volumes=portfolio_volumes)
        payload.setdefault('tradability_summary', {})
        payload['tradability_summary'].update(
            {
                'failed_order_count': int(execution_summary['failed_order_count']),
                'blocked_reason_counts': dict(execution_summary['blocked_reason_counts']),
            }
        )
        payload.setdefault('capacity_summary', {})
        payload['capacity_summary'].update(
            {
                'avg_participation_rate': execution_summary['avg_participation_rate'],
                'max_participation_rate': execution_summary['max_participation_rate'],
                'avg_adv_utilization': execution_summary['avg_adv_utilization'],
                'max_adv_utilization': execution_summary['max_adv_utilization'],
                'partial_fill_count': int(execution_summary['partial_fill_count']),
            }
        )
        payload.setdefault('implementation_shortfall_components', {})
        payload['implementation_shortfall_components'].update(
            {
                'avg_execution_penalty_bps': execution_summary['avg_execution_penalty_bps'],
                'execution_fill_rate': execution_summary['fill_rate'],
            }
        )
        payload['equity_curve'] = list(payload.get('equity_curve') or [])
        return {'success': True, 'data': payload}
