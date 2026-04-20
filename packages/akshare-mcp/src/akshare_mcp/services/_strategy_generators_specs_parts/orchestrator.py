

class _LLMProxyStrategyGeneratorSpecsMixin:
        @staticmethod
        def _fallback_variant_seed(task: dict[str, Any], target_symbols: list[str], candidate: dict[str, Any]) -> int:
            seed_text = "|".join([
                str(task.get('task_id') or ''),
                str(task.get('theme') or ''),
                str(task.get('opportunity_type') or ''),
                str(candidate.get('category') or ''),
                *[str(code) for code in list(target_symbols or [])[:6]],
            ])
            return sum(ord(ch) for ch in seed_text if ch)

        @staticmethod
        def _local_category_strategy_types(
            category: str,
            research_task: Optional[dict[str, Any]] = None,
        ) -> tuple[str, ...]:
            task = _normalize_research_task_contract(research_task)
            opportunity_type = str(task.get('opportunity_type') or '').strip().lower()

            if category == 'momentum':
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    return ('event_structure_breakout', 'momentum', 'volatility_breakout')
                return ('momentum',)
            if category == 'trend':
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    return ('ma_cross', 'north_capital_track')
                return ('ma_cross',)
            if category == 'reversal':
                if opportunity_type == 'oversold_repair':
                    return ('margin_divergence', 'gap_fill', 'mean_reversion_short')
                return ('margin_divergence', 'gap_fill')
            if category == 'value':
                if opportunity_type == 'factor_acceleration':
                    return ('multi_factor', 'value_factor')
                return ('value_factor', 'multi_factor')
            if category == 'quality':
                if opportunity_type == 'factor_acceleration':
                    return ('multi_factor', 'quality_factor')
                return ('quality_factor', 'multi_factor')
            if category == 'growth':
                return ('growth_factor', 'momentum')
            if category == 'volatility':
                return ('event_structure_breakout', 'volatility_breakout', 'ma_cross', 'macro_timing')
            if category == 'risk_adjusted':
                return ('multi_factor', 'quality_factor')
            if category == 'sentiment':
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    return ('momentum', 'north_capital_track')
                return ('momentum', 'sector_rotation')
            if category == 'event':
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    return ('event_structure_breakout', 'sector_rotation', 'momentum', 'north_capital_track')
                if opportunity_type == 'factor_acceleration':
                    return ('event_structure_breakout', 'momentum', 'sector_rotation', 'north_capital_track')
                return ('momentum', 'sector_rotation')
            if category == 'liquidity':
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    return ('event_structure_breakout', 'north_capital_track', 'margin_divergence', 'growth_factor')
                return ('margin_divergence', 'growth_factor')
            return ()

        @classmethod
        def _resolve_local_fallback_target(
            cls,
            category: str,
            research_task: Optional[dict[str, Any]] = None,
        ) -> Optional[tuple[str, dict[str, Any]]]:
            templates = {
                'momentum': {'lookback': 20, 'threshold': 0.02},
                'ma_cross': {'short_period': 8, 'long_period': 34},
                'rsi': {
                    'rsi_period': 12,
                    'oversold': 18,
                    'overbought': 64,
                    'regime_filter_enabled': True,
                    'allowed_entry_regimes': ['bear_calm', 'bear_volatile'],
                    'noise_filter_enabled': True,
                    'noise_window': 6,
                    'noise_ceiling': 6.0,
                    'regime_break_threshold': 0.015,
                    'repair_confirmation_enabled': True,
                    'repair_confirmation_window': 6,
                    'repair_confirmation_rebound_pct': 0.008,
                    'repair_confirmation_rsi_reclaim': 24.0,
                    'liquidity_confirmation_enabled': True,
                    'liquidity_window': 8,
                    'liquidity_volume_floor_ratio': 0.8,
                    'structure_confirmation_enabled': True,
                    'structure_window': 4,
                    'structure_close_location_min': 0.55,
                    'structure_body_return_min': 0.0015,
                    'max_active_symbols': 2,
                    'universe_selection_profile': 'repair_liquidity_fit_v1',
                    'mean_reversion_exit_min_hold_bars': 4,
                    'mean_reversion_exit_buffer': -0.002,
                    'max_hold_bars': 6,
                    'adverse_regime_exit_enabled': True,
                    'adverse_exit_regimes': ['range_volatile'],
                    'adverse_noise_ceiling': 6.0,
                },
                'margin_divergence': {
                    'fear_threshold': 43,
                    'greed_threshold': 60,
                    'lookback': 12,
                    'rebound_window': 3,
                    'repair_drawdown_floor': -0.06,
                    'repair_rebound_pct': 0.012,
                    'dryup_window': 3,
                    'dryup_max_ratio': 0.9,
                    'liquidity_window': 8,
                    'entry_volume_floor_ratio': 1.0,
                    'structure_window': 4,
                    'structure_close_location_min': 0.58,
                    'structure_body_return_min': 0.002,
                    'max_hold_bars': 8,
                    'adverse_volume_break_ratio': 0.72,
                    'adverse_close_break_pct': -0.012,
                    'max_active_symbols': 2,
                    'universe_selection_profile': 'liquidity_divergence_fit_v1',
                },
                'event_structure_breakout': {
                    'breakout_window': 12,
                    'breakout_buffer_pct': 0.002,
                    'contraction_window': 5,
                    'contraction_max_range_ratio': 0.06,
                    'volume_window': 8,
                    'breakout_volume_ratio_min': 1.0,
                    'structure_window': 4,
                    'structure_close_location_min': 0.62,
                    'structure_body_return_min': 0.003,
                    'event_impulse_window': 5,
                    'event_impulse_threshold': 0.015,
                    'max_hold_bars': 8,
                    'breakout_failure_close_buffer': -0.012,
                    'adverse_volume_ratio_max': 0.85,
                    'max_active_symbols': 3,
                    'universe_selection_profile': 'event_structure_breakout_fit_v1',
                },
                'gap_fill': {'rsi_period': 6, 'oversold': 24, 'overbought': 58},
                'mean_reversion_short': {'rsi_period': 8, 'oversold': 28, 'overbought': 62},
                'value_factor': {'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2},
                'quality_factor': {'lookback': 120, 'buy_quantile': 0.88, 'sell_quantile': 0.12},
                'growth_factor': {'lookback': 40, 'buy_quantile': 0.75, 'sell_quantile': 0.25},
                'multi_factor': {'factor_weights': {'quality': 0.4, 'value': 0.35, 'momentum': 0.25}, 'lookback': 36},
                'volatility_breakout': {'lookback': 12, 'threshold': 0.018},
                'north_capital_track': {'lookback': 10, 'threshold': 0.01},
                'sector_rotation': {'factor_weights': {'momentum': 0.45, 'quality': 0.3, 'value': 0.25}, 'lookback': 20},
                'macro_timing': {'fear_threshold': 24, 'greed_threshold': 74, 'lookback': 36},
            }
            for strategy_type in cls._local_category_strategy_types(category, research_task=research_task):
                params = templates.get(strategy_type)
                if params is not None:
                    return strategy_type, dict(params)
            return None

        @classmethod
        def _adapt_local_fallback_params(
            cls,
            strategy_type: str,
            params: dict[str, Any],
            task: dict[str, Any],
            candidate: dict[str, Any],
            target_symbols: list[str],
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            adapted = dict(params or {})
            if not task:
                return adapted, {
                    'variant_seed': 0,
                    'profile': 'default',
                    'task_opportunity_type': None,
                }
            opportunity_type = str(task.get('opportunity_type') or 'default').strip().lower() or 'default'
            variant_seed = cls._fallback_variant_seed(task, target_symbols, candidate)
            bucket = variant_seed % 5
            symbol_count = max(1, len(target_symbols or []))

            if strategy_type == 'momentum':
                lookback_map = {
                    'sector_breakout': [22, 26, 30, 36, 42],
                    'rotation_balanced': [26, 30, 36, 42, 48],
                    'industry_leadership': [24, 28, 32, 36, 42],
                    'factor_acceleration': [18, 22, 26, 30, 36],
                    'default': [22, 26, 30, 36, 42],
                }
                threshold_map = {
                    'sector_breakout': [0.011, 0.013, 0.015, 0.017, 0.019],
                    'rotation_balanced': [0.01, 0.012, 0.014, 0.016, 0.018],
                    'industry_leadership': [0.011, 0.013, 0.015, 0.017, 0.019],
                    'factor_acceleration': [0.009, 0.011, 0.013, 0.015, 0.017],
                    'default': [0.01, 0.012, 0.014, 0.016, 0.018],
                }
                lookbacks = lookback_map.get(opportunity_type, lookback_map['default'])
                thresholds = threshold_map.get(opportunity_type, threshold_map['default'])
                adapted['lookback'] = int(lookbacks[bucket])
                adapted['threshold'] = round(float(thresholds[(bucket + symbol_count) % len(thresholds)]), 4)
            elif strategy_type == 'ma_cross':
                short_map = {
                    'sector_breakout': [6, 8, 10, 12, 14],
                    'rotation_balanced': [8, 10, 12, 14, 16],
                    'industry_leadership': [6, 8, 10, 12, 14],
                    'default': [8, 10, 12, 14, 16],
                }
                long_map = {
                    'sector_breakout': [28, 34, 40, 48, 56],
                    'rotation_balanced': [34, 40, 48, 56, 64],
                    'industry_leadership': [30, 36, 42, 50, 58],
                    'default': [32, 38, 46, 54, 62],
                }
                shorts = short_map.get(opportunity_type, short_map['default'])
                longs = long_map.get(opportunity_type, long_map['default'])
                adapted['short_period'] = int(shorts[bucket])
                adapted['long_period'] = int(max(longs[(bucket + 1) % len(longs)], adapted['short_period'] + 18))
            elif strategy_type == 'rsi':
                adapted['rsi_period'] = int([8, 10, 12, 14, 16][bucket])
                adapted['oversold'] = int([16, 18, 20, 22, 24][bucket])
                adapted['overbought'] = int([60, 62, 64, 66, 68][bucket])
                adapted['regime_filter_enabled'] = True
                adapted['allowed_entry_regimes'] = ['bear_calm', 'bear_volatile']
                adapted['noise_filter_enabled'] = True
                adapted['noise_window'] = 6
                adapted['noise_ceiling'] = round(float([5.5, 6.0, 6.0, 6.5, 7.0][bucket]), 2)
                adapted['regime_break_threshold'] = 0.015
                adapted['repair_confirmation_enabled'] = True
                adapted['repair_confirmation_window'] = 6
                adapted['repair_confirmation_rebound_pct'] = 0.008
                adapted['repair_confirmation_rsi_reclaim'] = 24.0
                adapted['liquidity_confirmation_enabled'] = True
                adapted['liquidity_window'] = 8
                adapted['liquidity_volume_floor_ratio'] = 0.8
                adapted['structure_confirmation_enabled'] = True
                adapted['structure_window'] = 4
                adapted['structure_close_location_min'] = 0.55
                adapted['structure_body_return_min'] = 0.0015
                adapted['max_active_symbols'] = 2
                adapted['universe_selection_profile'] = 'repair_liquidity_fit_v1'
                adapted['mean_reversion_exit_min_hold_bars'] = 4
                adapted['mean_reversion_exit_buffer'] = -0.002
                adapted['max_hold_bars'] = 6
                adapted['adverse_regime_exit_enabled'] = True
                adapted['adverse_exit_regimes'] = ['range_volatile']
                adapted['adverse_noise_ceiling'] = adapted['noise_ceiling']
            elif strategy_type in {'gap_fill', 'mean_reversion_short'}:
                adapted['rsi_period'] = int([4, 5, 6, 8, 10][bucket])
                adapted['oversold'] = int([20, 22, 24, 26, 28][bucket])
                adapted['overbought'] = int([56, 58, 60, 62, 64][bucket])
            elif strategy_type == 'margin_divergence':
                adapted['fear_threshold'] = int([40, 42, 43, 45, 47][bucket])
                adapted['greed_threshold'] = int([58, 60, 62, 64, 66][bucket])
                adapted['lookback'] = int([10, 12, 14, 16, 18][bucket])
                adapted['rebound_window'] = int([2, 3, 3, 4, 4][bucket])
                adapted['repair_drawdown_floor'] = float([-0.05, -0.055, -0.06, -0.065, -0.07][bucket])
                adapted['repair_rebound_pct'] = float([0.008, 0.01, 0.012, 0.014, 0.016][bucket])
                adapted['dryup_window'] = 3
                adapted['dryup_max_ratio'] = float([0.95, 0.92, 0.9, 0.88, 0.85][bucket])
                adapted['liquidity_window'] = 8
                adapted['entry_volume_floor_ratio'] = float([0.95, 1.0, 1.02, 1.05, 1.08][bucket])
                adapted['structure_window'] = 4
                adapted['structure_close_location_min'] = float([0.54, 0.56, 0.58, 0.6, 0.62][bucket])
                adapted['structure_body_return_min'] = float([0.001, 0.0015, 0.002, 0.0025, 0.003][bucket])
                adapted['max_hold_bars'] = int([6, 7, 8, 9, 10][bucket])
                adapted['adverse_volume_break_ratio'] = float([0.76, 0.74, 0.72, 0.7, 0.68][bucket])
                adapted['adverse_close_break_pct'] = float([-0.01, -0.011, -0.012, -0.013, -0.014][bucket])
                adapted['max_active_symbols'] = 2
                adapted['universe_selection_profile'] = 'liquidity_divergence_fit_v1'
            elif strategy_type == 'event_structure_breakout':
                adapted['breakout_window'] = int([10, 12, 12, 14, 16][bucket])
                adapted['breakout_buffer_pct'] = float([0.002, 0.002, 0.004, 0.004, 0.006][bucket])
                adapted['contraction_window'] = int([4, 5, 5, 6, 6][bucket])
                adapted['contraction_max_range_ratio'] = float([0.08, 0.06, 0.06, 0.05, 0.045][bucket])
                adapted['volume_window'] = int([6, 8, 8, 10, 10][bucket])
                adapted['breakout_volume_ratio_min'] = float([0.95, 1.0, 1.0, 1.1, 1.2][bucket])
                adapted['structure_window'] = int([3, 4, 4, 5, 5][bucket])
                adapted['structure_close_location_min'] = float([0.58, 0.6, 0.62, 0.64, 0.66][bucket])
                adapted['structure_body_return_min'] = float([0.002, 0.0025, 0.003, 0.0035, 0.004][bucket])
                adapted['event_impulse_window'] = int([4, 5, 5, 6, 7][bucket])
                adapted['event_impulse_threshold'] = float([0.01, 0.015, 0.015, 0.02, 0.03][bucket])
                adapted['max_hold_bars'] = int([6, 7, 8, 9, 10][bucket])
                adapted['breakout_failure_close_buffer'] = float([-0.01, -0.011, -0.012, -0.013, -0.014][bucket])
                adapted['adverse_volume_ratio_max'] = float([0.9, 0.88, 0.85, 0.82, 0.8][bucket])
                adapted['max_active_symbols'] = min(3, symbol_count)
                adapted['universe_selection_profile'] = 'event_structure_breakout_fit_v1'
            elif strategy_type in {'quality_factor', 'value_factor', 'growth_factor'}:
                if strategy_type == 'quality_factor':
                    lookbacks = [84, 96, 120, 144, 180] if opportunity_type == 'sector_breakout' else [96, 120, 144, 180, 216]
                    buy_quantiles = [0.82, 0.86, 0.88, 0.9, 0.92]
                    sell_quantiles = [0.06, 0.08, 0.1, 0.12, 0.14]
                else:
                    lookbacks = [24, 30, 36, 45, 60] if opportunity_type == 'sector_breakout' else [30, 40, 50, 60, 72]
                    buy_quantiles = [0.58, 0.62, 0.66, 0.7, 0.75]
                    sell_quantiles = [0.22, 0.26, 0.3, 0.34, 0.38]
                adapted['lookback'] = int(lookbacks[bucket])
                adapted['buy_quantile'] = round(float(buy_quantiles[bucket]), 4)
                adapted['sell_quantile'] = round(float(sell_quantiles[(bucket + 2) % len(sell_quantiles)]), 4)
            elif strategy_type == 'volatility_breakout':
                lookbacks = {
                    'sector_breakout': [6, 8, 10, 12, 15],
                    'industry_leadership': [8, 10, 12, 15, 18],
                    'factor_acceleration': [5, 6, 8, 10, 12],
                    'default': [8, 10, 12, 15, 18],
                }
                thresholds = {
                    'sector_breakout': [0.008, 0.01, 0.012, 0.015, 0.018],
                    'industry_leadership': [0.009, 0.011, 0.013, 0.016, 0.02],
                    'factor_acceleration': [0.007, 0.009, 0.011, 0.013, 0.015],
                    'default': [0.01, 0.012, 0.015, 0.018, 0.02],
                }
                adapted['lookback'] = int(lookbacks.get(opportunity_type, lookbacks['default'])[bucket])
                adapted['threshold'] = round(float(thresholds.get(opportunity_type, thresholds['default'])[bucket]), 4)
            elif strategy_type == 'north_capital_track':
                lookbacks = {
                    'sector_breakout': [5, 8, 10, 12, 15],
                    'industry_leadership': [8, 10, 12, 15, 20],
                    'default': [8, 10, 12, 15, 18],
                }
                thresholds = {
                    'sector_breakout': [0.005, 0.007, 0.009, 0.011, 0.013],
                    'industry_leadership': [0.006, 0.008, 0.01, 0.012, 0.015],
                    'default': [0.006, 0.008, 0.01, 0.012, 0.014],
                }
                adapted['lookback'] = int(lookbacks.get(opportunity_type, lookbacks['default'])[bucket])
                adapted['threshold'] = round(float(thresholds.get(opportunity_type, thresholds['default'])[bucket]), 4)
            elif strategy_type in {'multi_factor', 'sector_rotation'}:
                if opportunity_type in {'sector_breakout', 'industry_leadership'}:
                    weight_sets = [
                        {'momentum': 0.5, 'quality': 0.3, 'value': 0.2},
                        {'momentum': 0.45, 'growth': 0.35, 'quality': 0.2},
                        {'momentum': 0.4, 'quality': 0.35, 'value': 0.25},
                        {'growth': 0.45, 'momentum': 0.35, 'quality': 0.2},
                        {'momentum': 0.42, 'quality': 0.28, 'value': 0.3},
                    ]
                    lookbacks = [10, 12, 15, 18, 20]
                elif opportunity_type == 'oversold_repair':
                    weight_sets = [
                        {'value': 0.45, 'quality': 0.35, 'momentum': 0.2},
                        {'value': 0.5, 'quality': 0.3, 'momentum': 0.2},
                        {'value': 0.4, 'quality': 0.4, 'momentum': 0.2},
                        {'value': 0.42, 'quality': 0.33, 'reversal': 0.25},
                        {'value': 0.38, 'quality': 0.37, 'momentum': 0.25},
                    ]
                    lookbacks = [18, 20, 24, 30, 36]
                else:
                    weight_sets = [
                        {'quality': 0.4, 'value': 0.35, 'momentum': 0.25},
                        {'quality': 0.35, 'growth': 0.35, 'momentum': 0.3},
                        {'quality': 0.38, 'value': 0.32, 'momentum': 0.3},
                        {'quality': 0.33, 'growth': 0.37, 'momentum': 0.3},
                        {'quality': 0.36, 'value': 0.29, 'growth': 0.35},
                    ]
                    lookbacks = [15, 18, 20, 24, 30]
                adapted['factor_weights'] = dict(weight_sets[bucket])
                adapted['lookback'] = int(lookbacks[bucket])
            elif strategy_type == 'macro_timing':
                adapted['fear_threshold'] = int([22, 24, 26, 28, 30][bucket])
                adapted['greed_threshold'] = int([70, 72, 74, 76, 78][bucket])
                adapted['lookback'] = int([24, 30, 36, 42, 48][bucket])

            profile = {
                'variant_seed': variant_seed,
                'variant_bucket': bucket,
                'profile': opportunity_type,
                'task_opportunity_type': opportunity_type,
                'symbol_count': symbol_count,
            }
            return adapted, profile

        @classmethod
        def _conservative_execution_profile(
            cls,
            strategy_type: str,
            task: dict[str, Any],
            *,
            template_contract: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            task_source = str(task.get('task_source') or '').strip().lower()
            template = dict(template_contract or {})
            if task_source == 'event_driven' and not dict(task.get('holding_window') or {}):
                holding_horizon = {'min_days': 1, 'max_days': 10}
            else:
                holding_horizon = dict(
                    task.get('holding_window')
                    or template.get('holding_horizon')
                    or _default_holding_horizon(strategy_type, task, task_source)
                )
            max_days = int(holding_horizon.get('max_days') or 0)
            min_days = int(holding_horizon.get('min_days') or 0)

            if task_source != 'event_driven':
                if strategy_type == 'momentum':
                    max_days = max(max_days, 24)
                elif strategy_type in {'ma_cross', 'volatility_breakout', 'north_capital_track', 'margin_divergence'}:
                    max_days = max(max_days, 20)
                elif strategy_type in {'gap_fill', 'mean_reversion_short', 'rsi'}:
                    max_days = max(max_days, 12)
                elif strategy_type == 'quality_factor':
                    max_days = max(max_days, 30)
                elif strategy_type in {'value_factor', 'growth_factor', 'multi_factor', 'sector_rotation', 'macro_timing'}:
                    max_days = max(max_days, 24)
                else:
                    max_days = max(max_days, 15)
                min_days = max(min_days, max(1, min(max_days - 1, max_days // 4)))
            else:
                max_days = max(max_days, 10)
                if min_days <= 0:
                    min_days = 1

            holding_horizon['max_days'] = int(max_days)
            if min_days > 0:
                holding_horizon['min_days'] = int(min(min_days, max_days))

            risk_rules = dict(template.get('risk_rules') or _default_risk_rules(task_source, holding_horizon))
            if task_source == 'event_driven':
                risk_rules['max_holding_days'] = int(holding_horizon.get('max_days') or 10)
            else:
                risk_rules['max_holding_days'] = max(
                    int(risk_rules.get('max_holding_days') or 0),
                    int(holding_horizon.get('max_days') or 0),
                )

            rebalance_rule = dict(template.get('rebalance_rule') or _default_rebalance_rule(strategy_type, task_source))
            if task_source == 'event_driven':
                rebalance_rule = {'mode': 'event_driven_hold'}
            else:
                mode = str(rebalance_rule.get('mode') or '').strip().lower()
                frequency_days = int(rebalance_rule.get('frequency_days') or 0)
                base_frequency = max(4, min(int(holding_horizon.get('max_days') or 10), max(1, int(holding_horizon.get('max_days') or 10) // 2)))
                if strategy_type == 'momentum':
                    base_frequency = max(base_frequency, 8)
                elif strategy_type == 'ma_cross':
                    base_frequency = max(base_frequency, 7)
                elif strategy_type == 'quality_factor':
                    base_frequency = max(base_frequency, 12)
                if mode in {'', 'signal_rebalance'}:
                    rebalance_rule = {'mode': 'periodic_rebalance', 'frequency_days': max(4, frequency_days or base_frequency)}
                elif mode == 'periodic_rebalance':
                    rebalance_rule['frequency_days'] = max(4, frequency_days or base_frequency)
                elif mode == 'regime_rebalance':
                    rebalance_rule['frequency_days'] = max(8, frequency_days or max(base_frequency, 8))

            trade_plan = dict(template.get('trade_plan') or {})
            if task_source == 'event_driven':
                trade_plan = {
                    'entry_bias': 'event_follow_through',
                    'exit_bias': 'time_stop_or_signal_reversal',
                }
            elif not trade_plan:
                trade_plan = {
                    'entry_bias': 'signal_confirmed',
                    'exit_bias': 'time_stop_or_signal_reversal',
                }
            elif task_source != 'event_driven' and not str(trade_plan.get('exit_bias') or '').strip():
                trade_plan['exit_bias'] = 'periodic_rebalance_or_signal_reversal'

            return {
                'holding_horizon': holding_horizon,
                'risk_rules': risk_rules,
                'rebalance_rule': rebalance_rule,
                'trade_plan': trade_plan,
            }

        @classmethod
        def _local_category_rank(cls, category: str, research_task: Optional[dict[str, Any]] = None) -> tuple[int, int]:
            task = _normalize_research_task_contract(research_task)
            opportunity_type = str(task.get('opportunity_type') or '').strip().lower()
            task_source = str(task.get('task_source') or '').strip().lower()
            strategy_preferences = [str(item).strip().lower() for item in list(task.get('preferred_strategy_types') or task.get('strategy_preferences') or []) if str(item).strip()]
            category_to_types = {
                key: cls._local_category_strategy_types(key, research_task=task)
                for key in (
                    'momentum',
                    'event',
                    'sentiment',
                    'trend',
                    'volatility',
                    'reversal',
                    'quality',
                    'risk_adjusted',
                    'value',
                    'growth',
                    'liquidity',
                )
            }
            if opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'} or task_source == 'event_driven':
                preferred_categories = ['event', 'momentum', 'trend', 'growth', 'liquidity', 'sentiment', 'quality', 'risk_adjusted', 'volatility', 'value', 'reversal']
            elif opportunity_type == 'oversold_repair':
                preferred_categories = ['reversal', 'value', 'quality', 'risk_adjusted', 'trend', 'momentum', 'event', 'sentiment', 'growth', 'liquidity', 'volatility']
            elif opportunity_type == 'factor_acceleration':
                preferred_categories = ['event', 'quality', 'growth', 'momentum', 'trend', 'liquidity', 'value', 'risk_adjusted', 'sentiment', 'volatility', 'reversal']
            else:
                preferred_categories = ['momentum', 'trend', 'quality', 'value', 'growth', 'event', 'sentiment', 'risk_adjusted', 'liquidity', 'volatility', 'reversal']

            prioritize_opportunity = task_source == 'event_driven' and opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'}
            if strategy_preferences and not prioritize_opportunity:
                matched_index = len(strategy_preferences)
                for idx, strategy_type in enumerate(category_to_types.get(category, ())):
                    if strategy_type in strategy_preferences:
                        matched_index = min(matched_index, strategy_preferences.index(strategy_type))
                if matched_index < len(strategy_preferences):
                    return (matched_index, preferred_categories.index(category) if category in preferred_categories else len(preferred_categories))

            return (
                len(strategy_preferences) + 1,
                preferred_categories.index(category) if category in preferred_categories else len(preferred_categories),
            )

        @classmethod
        def _local_candidate_to_spec(cls, candidate: dict, research_task: Optional[dict[str, Any]] = None) -> Optional[StrategySpec]:
            category = str(candidate.get('category') or 'custom')
            target = cls._resolve_local_fallback_target(category, research_task=research_task)
            if not target:
                return None
            task = _normalize_research_task_contract(research_task)
            event_context = _extract_event_context(task)
            task_source = str(task.get('task_source') or '').strip().lower()
            candidate_target_inputs = [
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
            ]
            if not cls._normalize_code_list(
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
            ):
                candidate_target_inputs = [
                    task.get('target_symbols'),
                    task.get('stock_pool'),
                ]
            target_resolution = _apply_target_symbol_policy(
                candidate_target_inputs,
                task,
                fallback_symbols=[task.get('target_symbols'), task.get('stock_pool')],
                limit=8,
            )
            target_symbols = list(target_resolution.get('target_symbols') or [])
            stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
            strategy_type, params = target
            params, fallback_profile = cls._adapt_local_fallback_params(strategy_type, params, task, candidate, target_symbols)
            template_contract = _rule_template_contract(strategy_type)
            execution_profile = cls._conservative_execution_profile(
                strategy_type,
                task,
                template_contract=template_contract,
            )
            validation_profile = {
                'profile': 'event_trade_validation' if task.get('validation_focus') == 'event_target_only' else 'trade_rule_validation',
                'validation_focus': task.get('validation_focus'),
                'primary_validation_layer': 'target' if task.get('validation_focus') == 'event_target_only' else 'combined',
            }
            template_validation_profile = dict(template_contract.get('validation_profile') or {})
            for key in (
                'objective_profile',
                'trade_density_preference',
                'regime_required',
                'cost_robust_required',
                'entry_selectivity',
                'preferred_regime',
                'avoid_regime',
            ):
                if template_validation_profile.get(key) not in (None, '', [], {}):
                    validation_profile[key] = template_validation_profile.get(key)
            holding_horizon = dict(execution_profile.get('holding_horizon') or {})
            risk_rules = dict(execution_profile.get('risk_rules') or {})
            rebalance_rule = dict(execution_profile.get('rebalance_rule') or {})
            trade_plan = dict(execution_profile.get('trade_plan') or {})
            semantic_contract_bundle = _build_rule_semantic_contract_bundle(
                strategy_type,
                strategy_name=str(candidate.get('name') or 'AI 候选策略'),
                description=str(candidate.get('description') or candidate.get('rationale') or ''),
                source='event_driven_local_fallback' if task_source == 'event_driven' else 'llm_proxy_local_fallback',
                regime=str(task.get('opportunity_type') or task_source or 'snapshot'),
                fg=0,
                factor_summary={},
                trade_plan=trade_plan,
                holding_horizon=holding_horizon,
                risk_rules=risk_rules,
                target_symbols=target_symbols,
                rationale=str(candidate.get('rationale') or candidate.get('description') or task.get('rationale') or ''),
                template_contract=template_contract,
            )
            trade_plan = dict(semantic_contract_bundle.get("trade_plan") or trade_plan)
            tags = ['local_rule_v1', 'llm_proxy_fallback', category]
            if target_symbols:
                tags.append('targeted_universe')
            portfolio_spec = {
                'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
            }
            execution_assumptions = {
                'commission_rate': 0.00025,
                'slippage_bps': 8 if task_source == 'event_driven' else 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
            }
            precompile_validation = validate_precompile_candidate_contract(
                {
                    **candidate,
                    'strategy_type': strategy_type,
                    'research_task': dict(task),
                    'target_symbols': list(target_symbols),
                    'stock_pool': dict(stock_pool),
                    'portfolio_spec': dict(portfolio_spec),
                    'execution_assumptions': dict(execution_assumptions),
                    'validation_profile': dict(validation_profile),
                    'constraint_check': dict(target_resolution.get('constraint_check') or {}),
                },
                research_task=task,
                source='local_rule_v1',
            )
            if not precompile_validation.accepted:
                candidate["_generator_precompile_reject_reasons"] = list(precompile_validation.reject_reasons)
                candidate["_generator_precompile_validation"] = precompile_validation.to_dict()
                return None
            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=str(candidate.get('name') or 'AI 候选策略'),
                description=str(candidate.get('description') or candidate.get('rationale') or ''),
                tags=list(dict.fromkeys(tags)),
                metadata={
                    'generator_type': str(candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1'),
                    'generation_reason': {
                        'source': 'event_driven_local_fallback' if task_source == 'event_driven' else 'llm_proxy_local_fallback',
                        'category': category,
                        'formula': candidate.get('formula'),
                        'rationale': candidate.get('rationale'),
                        'engine': candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1',
                        'fallback_reason': 'external_llm_unavailable',
                        'target_symbols': list(target_symbols),
                        'stock_pool': stock_pool,
                        'fallback_profile': fallback_profile,
                        'template_generation_profile': (
                            template_contract.get('template_generation_profile')
                            or dict(template_contract.get('rule_template_contract') or {}).get('template_generation_profile')
                        ),
                        'rule_template_contract': dict(template_contract.get('rule_template_contract') or {}),
                    },
                    'target_symbols': list(target_symbols),
                    'stock_pool': stock_pool,
                    'selection_logic': list(task.get('selection_logic') or []),
                    'research_scope': dict(task.get('analysis_scope') or {}),
                    'research_task': task,
                    'event_context': event_context,
                    'hypothesis': str(candidate.get('rationale') or candidate.get('description') or task.get('rationale') or ''),
                    'holding_horizon': holding_horizon,
                    'trade_plan': trade_plan,
                    'risk_rules': risk_rules,
                    'evidence_chain': dict(semantic_contract_bundle.get("evidence_chain") or {}),
                    'prediction_contract': dict(semantic_contract_bundle.get("prediction_contract") or {}),
                    'confidence_contract': dict(semantic_contract_bundle.get("confidence_contract") or {}),
                    'claim_to_trade_plan_map': dict(semantic_contract_bundle.get("claim_to_trade_plan_map") or {}),
                    'position_sizing': {
                        'mode': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
                        'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                    },
                    'execution_notes': 'use liquid names and respect tradability filter',
                    'rebalance_rule': rebalance_rule,
                    'portfolio_spec': dict(precompile_validation.portfolio_spec),
                    'execution_assumptions': dict(precompile_validation.execution_assumptions),
                    'validation_profile': dict(precompile_validation.validation_profile),
                    'targeting_policy': {
                        'target_symbol_policy': task.get('target_symbol_policy'),
                        'universe_expansion_policy': task.get('universe_expansion_policy'),
                        'validation_focus': task.get('validation_focus'),
                    },
                    'holding_rationale': template_contract.get('holding_rationale'),
                    'alpha_half_life': template_contract.get('alpha_half_life'),
                    'cost_sensitivity_grid': dict(template_contract.get('cost_sensitivity_grid') or {}),
                    'position_model': template_contract.get('position_model'),
                    'capacity_assumption': dict(template_contract.get('capacity_assumption') or {}),
                    'market_regime_assumption': template_contract.get('market_regime_assumption'),
                    'failure_mode': deepcopy(template_contract.get('failure_mode')),
                    'constraint_check': dict(precompile_validation.constraint_check),
                    'fallback_profile': fallback_profile,
                    'rule_template_contract': dict(template_contract.get('rule_template_contract') or {}),
                    'source_candidate': candidate,
                },
            )

        @classmethod
        def _normalize_stock_pool(cls, payload: Any, target_symbols: list[str]) -> dict[str, Any]:
            if isinstance(payload, dict):
                symbols = cls._normalize_code_list(payload.get('symbols') or payload.get('codes') or payload.get('stock_codes') or target_symbols)
                return {
                    'selection_mode': str(payload.get('selection_mode') or payload.get('mode') or ('explicit' if symbols else 'screened')).strip() or 'screened',
                    'symbols': symbols,
                    'filters': dict(payload.get('filters') or {}),
                    'rationale': payload.get('rationale'),
                }
            return {
                'selection_mode': 'explicit' if target_symbols else 'screened',
                'symbols': list(target_symbols),
                'filters': {},
                'rationale': None,
            }

        @classmethod
        def _external_candidate_to_spec(cls, candidate: dict, provider_payload: dict, market_frame: Optional[pd.DataFrame] = None) -> Optional[StrategySpec]:
            open_dsl_result = compile_open_dsl_candidate(candidate, market_frame=market_frame)
            lowered = None
            hypothesis_artifact: dict[str, Any] = {}
            hypothesis_lowering_audit: dict[str, Any] = {}
            if open_dsl_result.accepted:
                compiled = dict(open_dsl_result.compiled or {})
                hypothesis_artifact = dict(candidate.get('hypothesis_artifact') or {})
                hypothesis_lowering_audit = {
                    **dict(open_dsl_result.audit or {}),
                    'mode': 'l3_open_dsl',
                    'accepted': True,
                }
            else:
                if open_dsl_result.attempted:
                    candidate["_open_dsl_reject_reasons"] = list(open_dsl_result.reject_reasons)
                    candidate["_open_dsl_audit"] = dict(open_dsl_result.audit or {})
                    if is_open_dsl_candidate(candidate):
                        return None
                hypothesis_result = LLMHypothesisGenerator.build(
                    candidate,
                    research_task=provider_payload.get('research_task') or {},
                    provider_payload=provider_payload,
                )
                if hypothesis_result.accepted:
                    lowered = HypothesisLoweringCompiler.lower(
                        candidate,
                        hypothesis=hypothesis_result.to_artifact(),
                        research_task=provider_payload.get('research_task') or {},
                        source='external_llm',
                    )
                    if lowered.accepted:
                        candidate = dict(lowered.candidate)
                        hypothesis_artifact = dict(lowered.hypothesis_artifact or {})
                        hypothesis_lowering_audit = dict(lowered.audit or {})
                    else:
                        candidate["_hypothesis_compile_reject_reasons"] = list(lowered.reject_reasons)
                        candidate["_hypothesis_compile_audit"] = dict(lowered.audit or {})
                else:
                    candidate["_hypothesis_reject_reasons"] = list(hypothesis_result.reject_reasons)

                if lowered is None or not lowered.accepted:
                    if not bool(candidate.get("_legacy_contract_defaults_applied")):
                        return None
                try:
                    compiled = compile_strategy_blueprint(candidate, market_frame=market_frame, tune_for_factory=True)
                except Exception:
                    return None
            compiled_meta = dict(compiled.get('metadata') or {})
            activity = dict(compiled_meta.get('dsl_activity') or {})
            analysis = dict(provider_payload.get('analysis') or {})
            research_context = dict(provider_payload.get('research_context') or {})
            research_task = _normalize_research_task_contract(provider_payload.get('research_task') or {})
            if bool(research_context.get('blocked_by_target_universe')):
                return None
            targeted_task = bool(list(research_task.get('target_symbols') or []))
            targeted_fallback_symbols = [
                research_task.get('same_theme_symbols'),
                research_task.get('theme_members'),
                (research_task.get('event_context') or {}).get('same_theme_symbols'),
                (research_task.get('event_context') or {}).get('theme_members'),
                research_task.get('target_symbols'),
            ]
            broad_fallback_symbols = [
                research_context.get('candidate_universe_symbols'),
                dict(research_context.get('task_target_context') or {}).get('candidate_universe_symbols'),
                research_task.get('target_symbols'),
            ]
            target_resolution = _apply_target_symbol_policy([
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
                ((candidate.get('dsl') or {}).get('metadata') or {}).get('target_symbols'),
                ((candidate.get('dsl') or {}).get('metadata') or {}).get('stock_pool'),
            ], research_task, fallback_symbols=(targeted_fallback_symbols if targeted_task else broad_fallback_symbols), limit=8)
            target_symbols = list(target_resolution.get('target_symbols') or [])
            stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
            selection_logic = candidate.get('selection_logic') or analysis.get('selection_notes') or []
            if isinstance(selection_logic, str):
                selection_logic = [selection_logic]
            elif not isinstance(selection_logic, list):
                selection_logic = [selection_logic] if selection_logic else []
            params = dict(compiled.get('params') or {})
            if target_symbols and str(compiled.get('strategy_type') or 'dsl_rule') == 'dsl_rule':
                dsl = dict(params.get('dsl') or {})
                dsl_metadata = dict(dsl.get('metadata') or {})
                dsl_metadata['target_symbols'] = list(target_symbols)
                dsl_metadata['stock_pool'] = stock_pool
                dsl['metadata'] = dsl_metadata
                params['dsl'] = dsl
            metadata = {
                **compiled_meta,
                'generator_type': 'external_llm_open_dsl' if open_dsl_result.accepted else 'external_llm',
                'candidate_lane': 'l3_open_dsl' if open_dsl_result.accepted else 'l2_hypothesis_lowering',
                'hypothesis': str(candidate.get('hypothesis') or candidate.get('rationale') or candidate.get('description') or ''),
                'hypothesis_artifact': dict(hypothesis_artifact or {}),
                'hypothesis_artifact_id': hypothesis_artifact.get('artifact_id'),
                'hypothesis_lowering_audit': dict(hypothesis_lowering_audit or {}),
                'holding_rationale': candidate.get('holding_rationale'),
                'alpha_half_life': candidate.get('alpha_half_life'),
                'cost_sensitivity_grid': dict(candidate.get('cost_sensitivity_grid') or {}),
                'position_model': candidate.get('position_model'),
                'capacity_assumption': candidate.get('capacity_assumption'),
                'validation_focus': candidate.get('validation_focus'),
                'holding_horizon': dict(candidate.get('holding_horizon') or research_task.get('holding_window') or {}),
                'trade_plan': dict(candidate.get('trade_plan') or {}),
                'risk_rules': dict(candidate.get('risk_rules') or ((params.get('dsl') or {}).get('risk_rules') or {})),
                'position_sizing': dict(candidate.get('position_sizing') or {}),
                'execution_notes': candidate.get('execution_notes'),
                'rebalance_rule': dict(candidate.get('rebalance_rule') or {'mode': 'event_driven_hold' if research_task.get('task_source') == 'event_driven' else 'signal_rebalance'}),
                'portfolio_spec': dict(candidate.get('portfolio_spec') or {
                    'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                    'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
                }),
                'execution_assumptions': dict(candidate.get('execution_assumptions') or {
                    'commission_rate': 0.00025,
                    'slippage_bps': 8 if research_task.get('task_source') == 'event_driven' else 5,
                    'tradability_filter': True,
                    'slippage_model': 'fixed',
                }),
                'validation_profile': dict(candidate.get('validation_profile') or {
                    'profile': 'event_trade_validation' if research_task.get('validation_focus') == 'event_target_only' else 'trade_rule_validation',
                    'validation_focus': research_task.get('validation_focus'),
                    'primary_validation_layer': 'target' if research_task.get('validation_focus') == 'event_target_only' else 'combined',
                }),
                'targeting_policy': dict(candidate.get('targeting_policy') or {
                    'target_symbol_policy': research_task.get('target_symbol_policy'),
                    'universe_expansion_policy': research_task.get('universe_expansion_policy'),
                    'validation_focus': research_task.get('validation_focus'),
                }),
                'constraint_check': dict(candidate.get('constraint_check') or target_resolution.get('constraint_check') or {}),
                'generation_reason': {
                    'provider': provider_payload.get('provider'),
                    'model': provider_payload.get('model'),
                    'rationale': candidate.get('rationale'),
                    'analysis': analysis,
                    'research_context': research_context,
                    'constraint_check': dict(candidate.get('constraint_check') or target_resolution.get('constraint_check') or {}),
                    'target_symbols': list(target_symbols),
                    'stock_pool': stock_pool,
                    'selection_logic': list(selection_logic),
                    'dsl_summary': (params or {}).get('dsl') or {},
                    'dsl_activity': activity,
                    'dsl_tuning': compiled_meta.get('dsl_tuning') or {},
                },
                'llm_prompt': provider_payload.get('prompt') or {},
                'llm_analysis': analysis,
                'llm_research_context': research_context,
                'open_dsl_audit': dict(open_dsl_result.audit or {}),
                'open_dsl_reject_reasons': list(candidate.get('_open_dsl_reject_reasons') or []),
                'llm_response': {
                    'provider': provider_payload.get('provider'),
                    'model': provider_payload.get('model'),
                    'analysis': analysis,
                    'research_context': research_context,
                    'research_task': provider_payload.get('research_task') or {},
                    'candidate': candidate,
                    'content': provider_payload.get('content'),
                    'request_metrics': provider_payload.get('request_metrics') or {},
                },
                'target_symbols': list(target_symbols),
                'stock_pool': stock_pool,
                'selection_logic': list(selection_logic),
                'research_scope': dict(research_context.get('analysis_scope') or {}),
                'research_task': research_task,
                'source_candidate': candidate,
            }
            tags = ['external_llm', *(compiled.get('tags') or []), *(candidate.get('tags') or [])]
            if open_dsl_result.accepted:
                tags.extend(['open_dsl', 'llm_defined'])
            if target_symbols:
                tags.append('targeted_universe')
            return StrategySpec(
                strategy_type=str(compiled.get('strategy_type') or 'dsl_rule'),
                params=params,
                name=str(compiled.get('name') or candidate.get('name') or '外部 AI 策略'),
                description=str(compiled.get('description') or candidate.get('description') or candidate.get('rationale') or ''),
                tags=list(dict.fromkeys(tags)),
                metadata=metadata,
            )

        @staticmethod
        def _spec_preflight_score(spec: StrategySpec) -> float:
            activity = dict(spec.metadata.get('dsl_activity') or {})
            score = float(activity.get('score') or 0.0)
            tuning = dict(spec.metadata.get('dsl_tuning') or {})
            if tuning.get('applied'):
                score += 0.1
            return score

        @classmethod
        def _is_viable_external_spec(cls, spec: StrategySpec) -> bool:
            activity = dict(spec.metadata.get('dsl_activity') or {})
            if not activity:
                return True
            entry_count = int(activity.get('entry_count') or 0)
            exit_count = int(activity.get('exit_count') or 0)
            return entry_count > 0 and exit_count > 0 and cls._spec_preflight_score(spec) >= 0.8

        async def _recent_experiments(self, db, parent_strategies: Optional[list[dict]] = None) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for parent in list(parent_strategies or [])[:3]:
                parent_id = str((parent or {}).get('id') or '').strip()
                if not parent_id or not hasattr(db, 'list_strategy_generation_experiments'):
                    continue
                rows.extend(await db.list_strategy_generation_experiments(parent_strategy_id=parent_id, limit=5))
            summary = []
            for row in rows[:12]:
                evaluation = dict(row.get('evaluation') or {})
                committee_review = dict(evaluation.get('committee_review') or {})
                strategy_spec = dict(row.get('strategy_spec') or {})
                hypothesis_artifact = dict(
                    strategy_spec.get('hypothesis_artifact')
                    or evaluation.get('hypothesis_artifact')
                    or {}
                )
                summary.append({
                    'parent_strategy_id': row.get('parent_strategy_id') or row.get('strategy_id'),
                    'generator_type': row.get('generator_type'),
                    'status': row.get('status'),
                    'final_score': committee_review.get('final_score'),
                    'decision': committee_review.get('decision'),
                    'parameters': row.get('parameters') or {},
                    'target_symbols': list(strategy_spec.get('target_symbols') or [])[:6],
                    'family_hint': hypothesis_artifact.get('family_hint'),
                    'validation_focus': hypothesis_artifact.get('validation_focus'),
                    'replay_ready': bool(strategy_spec.get('replay_contract') or hypothesis_artifact),
                })
            return summary
