
    @staticmethod
    def optimize_parameters(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None
    ) -> Dict[str, Any]:
        """参数优化（网格搜索）"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        param_ranges = param_ranges or {}

        if strategy == 'ma_cross':
            short_periods = param_ranges.get('short_period', [5, 10, 15])
            long_periods = param_ranges.get('long_period', [20, 30, 40])

            best_params = None
            best_metric = -float('inf')
            all_results = []

            for short in short_periods:
                for long in long_periods:
                    if short >= long:
                        continue
                    params = {
                        'initial_capital': 100000, 'commission': 0.0003,
                        'short_period': short, 'long_period': long,
                    }
                    result = BacktestEngine.run_backtest(code, klines, strategy, params)
                    if result['success']:
                        data = result['data']
                        metric = data['sharpe_ratio'] * (1 - data['max_drawdown'])
                        all_results.append({
                            'params': params, 'metric': metric,
                            'total_return': data['total_return'],
                            'sharpe_ratio': data['sharpe_ratio'],
                            'max_drawdown': data['max_drawdown'],
                        })
                        if metric > best_metric:
                            best_metric = metric
                            best_params = params

            return {
                'success': True,
                'data': {
                    'best_params': best_params,
                    'best_metric': best_metric,
                    'all_results': all_results,
                }
            }

        return {'success': False, 'error': f'Parameter optimization not supported for strategy: {strategy}'}

    @staticmethod
    def monte_carlo_simulation(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        runs: int = 1000,
        bootstrap_method: str = 'normal',
    ) -> Dict[str, Any]:
        """蒙特卡洛模拟

        Args:
            bootstrap_method: 'normal' (正态分布) 或 'block' (Block Bootstrap，保留序列自相关)
        """
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        params = params or {}
        closes = np.array([k['close'] for k in klines])

        returns = np.diff(closes) / closes[:-1]
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        # Block Bootstrap 参数
        block_size = max(5, int(params.get('block_size', 20)))

        final_capitals = []
        max_drawdowns = []

        for _ in range(runs):
            if bootstrap_method == 'block' and len(returns) >= block_size:
                # Block Bootstrap: 随机抽取连续块拼接，保留序列自相关
                n_blocks = max(1, len(returns) // block_size + 1)
                sim_parts = []
                for _ in range(n_blocks):
                    start = np.random.randint(0, max(1, len(returns) - block_size + 1))
                    sim_parts.append(returns[start:start + block_size])
                simulated_returns = np.concatenate(sim_parts)[:len(returns)]
            else:
                simulated_returns = np.random.normal(mean_return, std_return, len(returns))

            simulated_closes = closes[0] * np.cumprod(1 + simulated_returns)
            simulated_closes = np.insert(simulated_closes, 0, closes[0])

            simulated_klines = [
                {'close': float(c), 'date': klines[i]['date']}
                for i, c in enumerate(simulated_closes)
            ]

            result = BacktestEngine.run_backtest(code, simulated_klines, strategy, params)
            if result['success']:
                final_capitals.append(result['data']['final_capital'])
                max_drawdowns.append(result['data']['max_drawdown'])

        if not final_capitals:
            return {'success': False, 'error': 'Simulation failed'}

        final_capitals = np.array(final_capitals)
        max_drawdowns = np.array(max_drawdowns)

        return {
            'success': True,
            'data': {
                'runs': runs,
                'bootstrap_method': bootstrap_method,
                'best_case': float(np.max(final_capitals)),
                'worst_case': float(np.min(final_capitals)),
                'average': float(np.mean(final_capitals)),
                'median': float(np.median(final_capitals)),
                'confidence_95': float(np.percentile(final_capitals, 5)),
                'avg_drawdown': float(np.mean(max_drawdowns)),
                'max_drawdown': float(np.max(max_drawdowns)),
            }
        }

    @staticmethod
    def walk_forward_analysis(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None,
        train_window: int = 250,
        test_window: int = 60
    ) -> Dict[str, Any]:
        """Walk-Forward分析"""
        klines = _ensure_dict_list(klines)

        if len(klines) < train_window + test_window:
            return {'success': False, 'error': 'Insufficient data for walk-forward analysis'}

        segments = []
        capital = 100000

        i = 0
        while i + train_window + test_window <= len(klines):
            train_klines = klines[i:i+train_window]
            opt_result = BacktestEngine.optimize_parameters(
                code, train_klines, strategy, param_ranges
            )
            if not opt_result['success']:
                break

            best_params = opt_result['data']['best_params']
            test_klines = klines[i+train_window:i+train_window+test_window]
            test_result = BacktestEngine.run_backtest(code, test_klines, strategy, best_params)

            if test_result['success']:
                data = test_result['data']
                segments.append({
                    'period': f"{test_klines[0]['date']} to {test_klines[-1]['date']}",
                    'params': best_params,
                    'return': data['total_return'],
                    'sharpe': data['sharpe_ratio'],
                    'max_drawdown': data['max_drawdown'],
                })
                capital *= (1 + data['total_return'])

            i += test_window

        if not segments:
            return {'success': False, 'error': 'Walk-forward analysis failed'}

        overall_return = (capital - 100000) / 100000

        return {
            'success': True,
            'data': {
                'segments': segments,
                'overall_return': overall_return,
                'final_capital': capital,
            }
        }
