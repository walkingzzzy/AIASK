
    @staticmethod
    def run_backtest(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        return_trades: bool = False
    ) -> Dict[str, Any]:
        """运行回测"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        params = params or {}
        initial_capital = float(params.get("initial_capital", 100000) or 100000)
        commission = float(params.get("commission", 0.0003) or 0.0)

        closes = np.array([k['close'] for k in klines])
        volumes = np.array([k.get('volume', 0.0) for k in klines])

        # 兼容两种成本口径：
        # 1) 显式 slippage（费率）参数
        # 2) slippage_model 推导费率（旧口径）
        explicit_slippage = float(params.get("slippage", 0.0) or 0.0)
        model_slippage_rate = _compute_slippage_rate(closes, volumes, params, 0.0)
        slippage_rate = explicit_slippage if explicit_slippage > 0 else model_slippage_rate
        total_cost_rate = max(0.0, commission + slippage_rate)

        slippage_model_raw = params.get("slippage_model")
        slippage_calc: Optional[SlippageCalculator] = None
        if slippage_model_raw:
            normalized = str(slippage_model_raw).strip().lower()
            if normalized in {"fixed", "volume_based", "market_impact"}:
                slippage_calc = SlippageCalculator(
                    model_type=_resolve_slippage_model(normalized)
                )

        tradability_mask: Optional[np.ndarray] = None
        if bool(params.get("tradability_filter", False)):
            tradability_mask = _build_tradability_mask(
                closes=closes,
                volumes=volumes,
                code=code,
                is_st=bool(params.get("is_st", False)),
            )

        has_execution_overrides = any(
            [
                params.get("max_position_pct") is not None,
                bool(str(params.get("position_assumption") or "").strip()),
                bool(str(params.get("target_weight_scheme") or "").strip()),
                bool(str(params.get("market_ruleset") or "").strip()),
                bool(params.get("t_plus_one")),
                int(params.get("min_trade_lot") or 0) > 1,
                _safe_float(params.get("market_impact_bps", 0.0), 0.0) > 0,
                _safe_float(params.get("sell_tax_rate", 0.0), 0.0) > 0,
            ]
        )
        advanced_exec_enabled = (slippage_calc is not None) or (tradability_mask is not None) or has_execution_overrides
        from .strategy_registry import StrategyRegistry as _Reg

        runtime_inst, execution_semantic_mode = _Reg.create_runtime_strategy(strategy, params)
        if runtime_inst is not None and execution_semantic_mode == "compiled_dsl":
            if hasattr(runtime_inst, 'generate_entry_exit_masks_from_klines'):
                _entry, _exit = runtime_inst.generate_entry_exit_masks_from_klines(klines)
            else:
                _entry, _exit = runtime_inst.generate_entry_exit_masks(closes, volumes)
            _sim = _simulate_trades_from_masks(
                closes=closes,
                volumes=volumes,
                entry_mask=_entry,
                exit_mask=_exit,
                initial_capital=initial_capital,
                commission_rate=commission,
                slippage_calc=slippage_calc,
                tradability_mask=tradability_mask,
                return_trades=return_trades,
                klines=klines,
                params=params,
                signal_events=(
                    runtime_inst.generate_signal_events_from_klines(klines)
                    if hasattr(runtime_inst, 'generate_signal_events_from_klines')
                    else runtime_inst.generate_signal_events(closes, volumes)
                    if hasattr(runtime_inst, 'generate_signal_events')
                    else None
                ),
            )
            _payload = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(_sim['final_capital']),
                'total_return': float(_sim['total_return']),
                'max_drawdown': float(_sim['max_drawdown']),
                'sharpe_ratio': float(_sim['sharpe_ratio']),
                'trades_count': int(_sim['trades_count']),
                'win_rate': float(_sim['win_rate']),
                'avg_holding_days': float(_sim.get('avg_holding_days') or 0.0),
                'turnover_proxy': float(_sim.get('turnover_proxy') or 0.0),
                'params': params,
            }
            if return_trades:
                _payload['trades'] = _sim.get('trades') or []
                _payload['fills'] = _sim.get('fills') or []
            _payload['round_trip_positions'] = _sim.get('round_trip_positions') or []
            _payload['closed_round_trip_count'] = int(_sim.get('closed_round_trip_count') or 0)
            _payload['winning_round_trip_count'] = int(_sim.get('winning_round_trip_count') or 0)
            _payload['execution_summary'] = dict(_sim.get('execution_summary') or {})
            _finalize_backtest_payload(_payload, _sim['equity'], params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': _payload}

        if strategy == 'ma_cross':
            short_period = params.get('short_period', 5)
            long_period = params.get('long_period', 20)

            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes, klines=klines)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                    params=params,
                    signal_events=None,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                    payload['fills'] = sim.get('fills') or []
                payload['round_trip_positions'] = sim.get('round_trip_positions') or []
                payload['closed_round_trip_count'] = int(sim.get('closed_round_trip_count') or 0)
                payload['winning_round_trip_count'] = int(sim.get('winning_round_trip_count') or 0)
                payload['execution_summary'] = dict(sim.get('execution_summary') or {})
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': payload}

            if return_trades:
                result = _backtest_ma_cross_with_trades_jit(
                    closes, short_period, long_period, initial_capital, total_cost_rate
                )
                (final_capital, total_return, max_dd, sharpe, total_trades, win_rate, equity,
                 trade_count, trade_indices, trade_types, trade_prices, trade_shares, trade_profits) = result

                trades_detail = []
                for i in range(trade_count):
                    idx = int(trade_indices[i])
                    trades_detail.append({
                        'index': idx,
                        'time': klines[idx].get('date', klines[idx].get('trade_date', '')),
                        'price': float(trade_prices[i]),
                        'signal': int(trade_types[i]),
                        'shares': int(trade_shares[i]),
                        'profit': float(trade_profits[i])
                    })

                data = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(final_capital),
                    'total_return': float(total_return),
                    'max_drawdown': float(max_dd),
                    'sharpe_ratio': float(sharpe),
                    'trades_count': int(total_trades),
                    'win_rate': float(win_rate),
                    'params': params,
                    'trades': trades_detail
                }
                _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': data}

            result = _backtest_ma_cross_jit(
                closes, short_period, long_period, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

        elif strategy == 'buy_and_hold':
            entry_idx = 0
            exit_idx = len(closes) - 1
            if tradability_mask is not None:
                tradable_idx = np.where(tradability_mask)[0]
                if len(tradable_idx) < 2:
                    return {'success': False, 'error': 'No enough tradable days for buy_and_hold'}
                entry_idx = int(tradable_idx[0])
                exit_idx = int(tradable_idx[-1])

            entry_price = float(closes[entry_idx])
            exit_price = float(closes[exit_idx])
            if slippage_calc is not None:
                buy_slip = slippage_calc.calculate(
                    price=entry_price,
                    volume=float(volumes[entry_idx]) if entry_idx < len(volumes) else 0.0,
                    order_size=float(initial_capital / max(entry_price, 1e-8)),
                    is_buy=True,
                )
                entry_price = float(buy_slip.get("execution_price", entry_price))
                sell_slip = slippage_calc.calculate(
                    price=exit_price,
                    volume=float(volumes[exit_idx]) if exit_idx < len(volumes) else 0.0,
                    order_size=float(initial_capital / max(entry_price, 1e-8)),
                    is_buy=False,
                )
                exit_price = float(sell_slip.get("execution_price", exit_price))

            buy_price = entry_price * (1 + total_cost_rate)
            shares = initial_capital / buy_price if buy_price > 0 else 0.0
            final_capital = shares * exit_price * (1 - total_cost_rate)
            total_return = (final_capital - initial_capital) / initial_capital

            equity = shares * closes
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            max_dd = float(np.max(drawdown))

            data = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': max_dd,
                'sharpe_ratio': 0.0,
                'trades_count': 1,
                'win_rate': 1.0 if total_return > 0 else 0.0,
                'avg_holding_days': float(max(1, exit_idx - entry_idx)),
                'turnover_proxy': float(((shares * buy_price) + (shares * exit_price)) / initial_capital) if initial_capital > 0 else 0.0,
            }
            if tradability_mask is not None:
                data['tradability_filter'] = True
                data['entry_index'] = entry_idx
                data['exit_index'] = exit_idx
            if slippage_calc is not None:
                data['slippage_model'] = str(slippage_model_raw).strip().lower()
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {
                'success': True,
                'data': data
            }

        elif strategy == 'momentum':
            lookback = params.get('lookback', 20)
            threshold = params.get('threshold', 0.02)
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes, klines=klines)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                    params=params,
                    signal_events=None,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                    payload['fills'] = sim.get('fills') or []
                payload['round_trip_positions'] = sim.get('round_trip_positions') or []
                payload['closed_round_trip_count'] = int(sim.get('closed_round_trip_count') or 0)
                payload['winning_round_trip_count'] = int(sim.get('winning_round_trip_count') or 0)
                payload['execution_summary'] = dict(sim.get('execution_summary') or {})
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': payload}

            result = _backtest_momentum_jit(
                closes, lookback, threshold, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

        elif strategy == 'rsi':
            rsi_period = params.get('rsi_period', 12)
            oversold = params.get('oversold', 18)
            overbought = params.get('overbought', 64)
            regime_filter_enabled = 1 if bool(params.get('regime_filter_enabled', True)) else 0
            noise_filter_enabled = 1 if bool(params.get('noise_filter_enabled', True)) else 0
            noise_window = int(params.get('noise_window', 6) or 6)
            noise_ceiling = float(params.get('noise_ceiling', 6.0) or 6.0)
            bearish_regime_threshold = float(
                params.get('bearish_regime_threshold', -0.05) or -0.05
            )
            regime_break_threshold = float(
                params.get('regime_break_threshold', 0.015) or 0.015
            )
            repair_confirmation_enabled = 1 if bool(
                params.get('repair_confirmation_enabled', True)
            ) else 0
            repair_confirmation_window = int(
                params.get('repair_confirmation_window', 6) or 6
            )
            repair_confirmation_rebound_pct = float(
                params.get('repair_confirmation_rebound_pct', 0.008) or 0.008
            )
            repair_confirmation_rsi_reclaim = float(
                params.get('repair_confirmation_rsi_reclaim', 24.0) or 24.0
            )
            liquidity_confirmation_enabled = 1 if bool(
                params.get('liquidity_confirmation_enabled', True)
            ) else 0
            liquidity_window = int(params.get('liquidity_window', 8) or 8)
            liquidity_volume_floor_ratio = float(
                params.get('liquidity_volume_floor_ratio', 0.8) or 0.8
            )
            structure_confirmation_enabled = 1 if bool(
                params.get('structure_confirmation_enabled', True)
            ) else 0
            structure_window = int(params.get('structure_window', 4) or 4)
            structure_close_location_min = float(
                params.get('structure_close_location_min', 0.55) or 0.55
            )
            structure_body_return_min = float(
                params.get('structure_body_return_min', 0.0015) or 0.0015
            )
            mean_reversion_exit_min_hold_bars = int(
                params.get('mean_reversion_exit_min_hold_bars', 4) or 4
            )
            mean_reversion_exit_buffer = float(
                params.get('mean_reversion_exit_buffer', -0.002) or -0.002
            )
            max_hold_bars = int(params.get('max_hold_bars', 6) or 6)
            adverse_regime_exit_enabled = 1 if bool(
                params.get('adverse_regime_exit_enabled', True)
            ) else 0
            adverse_noise_ceiling = float(
                params.get('adverse_noise_ceiling', noise_ceiling) or noise_ceiling
            )
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes, klines=klines)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                    params=params,
                    signal_events=None,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                    payload['fills'] = sim.get('fills') or []
                payload['round_trip_positions'] = sim.get('round_trip_positions') or []
                payload['closed_round_trip_count'] = int(sim.get('closed_round_trip_count') or 0)
                payload['winning_round_trip_count'] = int(sim.get('winning_round_trip_count') or 0)
                payload['execution_summary'] = dict(sim.get('execution_summary') or {})
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': payload}

            result = _backtest_rsi_jit(
                closes,
                volumes,
                rsi_period,
                oversold,
                overbought,
                regime_filter_enabled,
                noise_filter_enabled,
                noise_window,
                noise_ceiling,
                bearish_regime_threshold,
                regime_break_threshold,
                repair_confirmation_enabled,
                repair_confirmation_window,
                repair_confirmation_rebound_pct,
                repair_confirmation_rsi_reclaim,
                liquidity_confirmation_enabled,
                liquidity_window,
                liquidity_volume_floor_ratio,
                structure_confirmation_enabled,
                structure_window,
                structure_close_location_min,
                structure_body_return_min,
                mean_reversion_exit_min_hold_bars,
                mean_reversion_exit_buffer,
                max_hold_bars,
                adverse_regime_exit_enabled,
                adverse_noise_ceiling,
                initial_capital,
                total_cost_rate,
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

        # Generic registry fallback for custom/factory strategies
        _inst, _execution_semantic_mode = _Reg.create_runtime_strategy(strategy, params)
        if _inst is not None:
            if hasattr(_inst, 'generate_entry_exit_masks_from_klines'):
                _masks = _inst.generate_entry_exit_masks_from_klines(klines)
            else:
                _masks = _inst.generate_entry_exit_masks(closes, volumes)
            if _masks is not None and _masks[0] is not None:
                _entry, _exit = _masks
                _sim = _simulate_trades_from_masks(
                    closes=closes, volumes=volumes,
                    entry_mask=_entry, exit_mask=_exit,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                    params=params,
                    signal_events=(
                        _inst.generate_signal_events_from_klines(klines)
                        if hasattr(_inst, 'generate_signal_events_from_klines')
                        else _inst.generate_signal_events(closes, volumes)
                        if hasattr(_inst, 'generate_signal_events')
                        else None
                    ),
                )
                _payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(_sim['final_capital']),
                    'total_return': float(_sim['total_return']),
                    'max_drawdown': float(_sim['max_drawdown']),
                    'sharpe_ratio': float(_sim['sharpe_ratio']),
                    'trades_count': int(_sim['trades_count']),
                    'win_rate': float(_sim['win_rate']),
                    'avg_holding_days': float(_sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(_sim.get('turnover_proxy') or 0.0),
                    'params': params,
                }
                if return_trades:
                    _payload['trades'] = _sim.get('trades') or []
                    _payload['fills'] = _sim.get('fills') or []
                _payload['round_trip_positions'] = _sim.get('round_trip_positions') or []
                _payload['closed_round_trip_count'] = int(_sim.get('closed_round_trip_count') or 0)
                _payload['winning_round_trip_count'] = int(_sim.get('winning_round_trip_count') or 0)
                _payload['execution_summary'] = dict(_sim.get('execution_summary') or {})
                _finalize_backtest_payload(_payload, _sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': _payload}

        return {'success': False, 'error': f'Unknown strategy: {strategy}'}
