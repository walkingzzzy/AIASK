# akshare-portfolio 工具清单

## 回测
- run_simple_backtest(code: str, strategy: str = 'ma_cross', start_date: str = None, end_date: str = None, initial_capital: float = 100000, commission: float = 0.0003, short_period: int = 5, long_period: int = 20)
- run_batch_backtest(codes: list[str], strategy: str = 'ma_cross', start_date: str = None, end_date: str = None, initial_capital: float = 100000, commission: float = 0.0003, short_period: int = 5, long_period: int = 20, use_parallel: bool = True)

## 组合/风险
- optimize_portfolio(stocks: list[str], method: str = 'equal_weight', lookback_days: int = 252, risk_aversion: float = 1.0, risk_free_rate: float = 0.03, market_weights: list[float] = None, views: list[dict] = None, risk_budgets: list[float] = None)
- analyze_portfolio_risk(holdings: list[dict], lookback_days: int = 252)
- stress_test_portfolio(holdings: list[dict], scenarios: list[str] = None)

## 管理器（持久化/查询历史）
- portfolio_manager(action: str, **kwargs)
- backtest_manager(action: str, **kwargs)
- risk_manager(action: str, **kwargs)
- performance_manager(action: str, **kwargs)

## 关键参数说明
- holdings: [{code: str, weight: float}] 或含 cost/quantity
- strategy: ma_cross/momentum/rsi（以实现为准）
