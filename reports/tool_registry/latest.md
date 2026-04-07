# AKShare MCP Tool Registry

- 导出时间: 2026-04-07T11:12:51+08:00
- 工具总数: **155**
- 使用 unwrap 定位的工具数: **22**
- 缺少实现路径的工具数: **0**
- 缺少 docstring 的工具数: **5**

## 分类统计

| Category | Count |
|----------|-------|
| `alerts` | 4 |
| `backtest` | 4 |
| `basic_data` | 4 |
| `compliance` | 1 |
| `data_sync` | 10 |
| `decision` | 12 |
| `execution` | 1 |
| `factor` | 1 |
| `finance` | 10 |
| `fund_flow` | 9 |
| `general` | 13 |
| `industry_chain` | 1 |
| `macro` | 2 |
| `market` | 14 |
| `news` | 9 |
| `options` | 2 |
| `paper_trading` | 1 |
| `performance` | 1 |
| `portfolio` | 5 |
| `quant` | 11 |
| `research` | 3 |
| `risk` | 3 |
| `screening` | 1 |
| `search` | 4 |
| `sector` | 3 |
| `semantic` | 4 |
| `sentiment` | 8 |
| `skills` | 3 |
| `strategy` | 1 |
| `technical` | 4 |
| `user` | 1 |
| `vector` | 4 |
| `watchlist` | 1 |

## Runtime Registry

| Tool | Category | Async | Wrapper | Implementation | Signature |
|------|----------|-------|---------|----------------|-----------|
| `ai_workflow_artifact` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(artifact_id: 'str') -> 'dict[str, Any]'` |
| `alerts_manager` | `alerts` | yes | `alerts_manager.py` | `alerts_manager.py` | `(action: 'str', params: 'dict \| None' = None, kwargs: 'Any' = None, user_id: 'str \| None' = None, status: 'str \| None' = None, code: 'str \| None' = None, indicator: 'str \| None' = None, condition: 'str \| None' = None, value: 'float \| None' = None, alert_id: 'str \| None' = None)` |
| `analyze_portfolio_risk` | `portfolio` | yes | `portfolio.py` | `portfolio.py` | `(holdings: Optional[List[Dict[str, Any]]] = None, lookback_days: int = 252, portfolio_id: Optional[str] = None, codes: Optional[List[str]] = None, weights: Optional[List[float]] = None)` |
| `analyze_portfolio_risk_barra` | `portfolio` | yes | `portfolio.py` | `portfolio.py` | `(holdings: List[Dict[str, Any]], lookback_days: int = 252)` |
| `analyze_research_report` | `general` | yes | `research.py` | `research.py` | `(code: str)` |
| `analyze_stock_sentiment` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(code: str \| None = None, stock_code: str \| None = None, symbol: str \| None = None, ticker: str \| None = None)` |
| `analyze_stock_workflow` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(code: 'str', investment_style: 'str' = 'balanced', include_kline: 'bool' = True, include_financials: 'bool' = True, include_decision: 'bool' = True, kline_limit: 'int' = 90, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `available_tools` | `search` | no | `search.py` | `search.py` | `(category: str \| None = None, include_contracts: bool = True)` |
| `backtest_factor` | `quant` | yes | `quant.py` | `quant.py` | `(codes: list, factor: str, groups: int = 5, holding_days: int = 20, commission: float = 0.0003, slippage: float = 0.0, slippage_model: str = '', tradability_filter: bool = False, is_st: bool = False, rebalance_step: int = 0, max_periods: int = 0, start_date: Optional[str] = None, end_date: Optional[str] = None, include_perf_breakdown: bool = True)` |
| `backtest_manager` | `backtest` | yes | `backtest_manager.py` | `backtest_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `batch_sync_klines` | `data_sync` | yes | `data_sync.py` | `data_sync.py` | `(codes: List[str], start_date: str = '', end_date: str = '', period: str = 'daily') -> dict` |
| `benchmark_manager` | `backtest` | yes | `benchmark_manager.py` | `benchmark_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `build_event_context` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None, news_limit: 'int' = 12, notice_days: 'int' = 30, report_limit: 'int' = 6)` |
| `build_quant_context` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `build_stock_context` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `calculate_factor` | `quant` | yes | `quant.py` | `quant.py` | `(code: str, factor: str, start_date: Optional[str] = None, end_date: Optional[str] = None)` |
| `calculate_factor_ic` | `quant` | yes | `quant.py` | `quant.py` | `(codes: list, factor: str, period: int = 20, enable_neutralization: bool = True, bootstrap_n: int = 1000, bootstrap_confidence: float = 0.95, include_perf_breakdown: bool = True)` |
| `calculate_fear_greed_index` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `()` |
| `calculate_technical_indicators` | `technical` | yes | `technical.py` | `technical.py` | `(code: str, indicators: List[str], period: str = 'daily', limit: int = 250)` |
| `check_all_alerts` | `alerts` | yes | `alerts.py` | `alerts.py` | `(status: str = 'active', alert_type: str = 'all')` |
| `check_candlestick_patterns` | `technical` | yes | `technical.py` | `technical.py` | `(code: str, period: str = 'daily', limit: int = 100)` |
| `clear_cache` | `data_sync` | no | `data_sync.py` | `data_sync.py` | `() -> dict` |
| `clear_dead_letters` | `data_sync` | no | `data_sync.py` | `data_sync.py` | `() -> dict` |
| `compliance_manager` | `compliance` | yes | `compliance_manager.py` | `compliance_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `comprehensive_manager` | `research` | yes | `comprehensive_manager.py` | `comprehensive_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None)` |
| `create_combo_alert` | `alerts` | yes | `alerts.py` | `alerts.py` | `(name: str, conditions: List[Dict[str, Any]], logic: str = 'AND')` |
| `create_indicator_alert` | `alerts` | yes | `alerts.py` | `alerts.py` | `(code: str, indicator: str, condition: str, value: float)` |
| `data_quality_workflow` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(dataset_id: 'str \| None' = None, records: 'list[dict[str, Any]] \| None' = None, required_fields: 'list[str] \| None' = None, as_of_field: 'str \| None' = None, as_of_value: 'str \| None' = None, source: 'str' = 'workflow.input', source_chain: 'list[str] \| None' = None, minimum_quality_threshold: 'float' = 0.95, persist_artifact: 'bool' = False, output_artifact_id: 'str \| None' = None, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `data_sync_manager` | `data_sync` | yes | `data_sync_manager.py` | `data_sync_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, codes: list[str] \| None = None, task_id: str \| None = None, task_type: str \| None = None, period: str \| None = None, status: str \| None = None, schedule: str \| None = None, force: bool \| None = None, limit: int \| None = None, priority: str \| None = None)` |
| `data_validation` | `general` | yes | `adapter_tools.py` | `adapter_tools.py` | `(action: 'str' = 'validate', records: 'list[dict[str, Any]] \| None' = None, expectations: 'dict[str, Any] \| None' = None, dataset_id: 'str \| None' = None, minimum_quality_threshold: 'float' = 0.95) -> 'dict[str, Any]'` |
| `data_warmup` | `data_sync` | yes | `data_warmup.py` | `data_warmup.py` | `(action: str, stocks: Union[List[str], str, NoneType] = None, lookback_days: int = 250, force_update: bool = False, include_financials: bool = True)` |
| `dcf_valuation` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, discount_rate: float = 0.1, growth_rate: float = 0.05, years: int = 5, risk_free_rate: float = 0.03, beta: float = 1.0, market_risk_premium: float = 0.06, cost_of_debt: float = 0.05, tax_rate: float = 0.25, equity_weight: float = 0.7, debt_weight: float = 0.3, terminal_growth_rate: Optional[float] = None, capex_ratio: float = 0.04, depreciation_ratio: float = 0.03, nwc_ratio: float = 0.01, enable_sensitivity: bool = True, enable_distribution: bool = False, distribution_samples: int = 1000, distribution_growth_std: float = 0.2, distribution_margin_std: float = 0.15, distribution_discount_std: float = 0.1, distribution_terminal_std: float = 0.1, distribution_seed: Optional[int] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `ddm_valuation` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, dividend: Optional[float] = None, growth_rate: float = 0.05, required_return: float = 0.1, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `decision_manager` | `decision` | yes | `decision_manager.py` | `decision_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None, codes: list[str] \| None = None, weights: list[float] \| None = None, investment_style: str \| None = None, criteria: dict \| None = None, limit: int \| None = None, portfolio_id: str \| int \| None = None)` |
| `event_manager` | `news` | yes | `event_manager.py` | `event_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `execution_manager` | `execution` | yes | `execution_manager.py` | `execution_manager.py` | `(action: 'str', params: 'dict \| None' = None, kwargs: 'Any' = None, dry_run: 'bool' = False) -> 'dict'` |
| `experiment_tracker` | `general` | yes | `adapter_tools.py` | `adapter_tools.py` | `(action: 'str', experiment_name: 'str \| None' = None, run_id: 'str \| None' = None, metric_key: 'str \| None' = None, metric_value: 'float \| None' = None, metric_step: 'int \| None' = None, artifact_key: 'str \| None' = None, artifact_data: 'dict[str, Any] \| None' = None, params: 'dict[str, Any] \| None' = None, tags: 'dict[str, str] \| None' = None, limit: 'int' = 20) -> 'dict[str, Any]'` |
| `factor_candidate_workflow` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(task: 'str' = 'pipeline', code: 'str \| None' = None, codes: 'list[str] \| None' = None, artifact_id: 'str \| None' = None, candidate_index: 'int' = 0, candidate_count: 'int' = 6, lookback_bars: 'int \| None' = None, horizon_days: 'int \| None' = None, max_dates: 'int \| None' = None, allow_fallback: 'bool' = True, persist_artifact: 'bool' = True, write_memory: 'bool' = True, run_scheduler_now: 'bool' = False, idempotency_key: 'str \| None' = None, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `factor_robustness_check` | `quant` | yes | `quant.py` | `quant.py` | `(codes: list, factor: str, windows: list = None, param_variations: list = None, start_date: Optional[str] = None, end_date: Optional[str] = None, include_perf_breakdown: bool = True)` |
| `find_similar_patterns` | `quant` | yes | `quant.py` | `quant.py` | `(code: str, window_days: int = 20, top_n: int = 10, forward_days: list = None, lookback_days: int = 360)` |
| `fundamental_analysis_manager` | `finance` | yes | `fundamental_analysis_manager.py` | `fundamental_analysis_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None)` |
| `fuse_decision_payload` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, investment_style: 'str' = 'balanced', user_id: 'str \| None' = None, stock_context: 'dict \| None' = None, quant_context: 'dict \| None' = None, event_context: 'dict \| None' = None, user_context: 'dict \| None' = None, gate: 'dict \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `generate_daily_report` | `semantic` | yes | `daily_report.py` | `daily_report.py` | `(date: Optional[str] = None)` |
| `get_analyst_ranking` | `news` | no | `cache_manager.py` | `research.py` | `(year: str = '') -> dict` |
| `get_available_categories` | `search` | no | `search.py` | `search.py` | `()` |
| `get_available_patterns` | `technical` | no | `technical.py` | `technical.py` | `()` |
| `get_batch_quotes` | `market` | no | `quote.py` | `quote.py` | `(stock_codes: list[str]) -> dict` |
| `get_batch_quotes_compat` | `market` | no | `quote.py` | `quote.py` | `(codes: list[str]) -> dict` |
| `get_block_stocks` | `sector` | yes | `server.py` | `server.py` | `(block_code: 'str')` |
| `get_block_trades` | `fund_flow` | no | `fund_flow_market.py` | `fund_flow_market.py` | `(date: str = '', stock_code: str = '', limit: int = 500) -> dict` |
| `get_cache_stats` | `data_sync` | no | `data_sync.py` | `data_sync.py` | `() -> dict` |
| `get_cb_info` | `basic_data` | yes | `basic_data.py` | `basic_data.py` | `(code: Optional[str] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None)` |
| `get_concept_fund_flow` | `fund_flow` | no | `cache_manager.py` | `fund_flow_sector.py` | `(top_n: int = 20) -> dict` |
| `get_conditional_returns` | `quant` | yes | `quant.py` | `quant.py` | `(code: str, conditions: Any = None, forward_days: list = None, logic: str = 'AND', lookback_days: int = 250)` |
| `get_dead_letters` | `data_sync` | no | `data_sync.py` | `data_sync.py` | `(limit: int = 20) -> dict` |
| `get_dragon_tiger` | `fund_flow` | no | `fund_flow_market.py` | `fund_flow_market.py` | `(date: str = '', stock_code: str = '') -> dict` |
| `get_factor_library` | `quant` | no | `quant.py` | `quant.py` | `(category: str = 'all')` |
| `get_factor_profile` | `factor` | yes | `factor_profile.py` | `factor_profile.py` | `(code: str, factors: str = 'rsi,macd,momentum', lookback_days: int = 250)` |
| `get_financials` | `finance` | yes | `cache_manager.py` | `finance.py` | `(stock_code: str) -> dict` |
| `get_historical_valuation` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, days: int = 30, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `get_index_quote` | `market` | no | `quote.py` | `quote.py` | `(index_code: str) -> dict` |
| `get_industry_chain` | `semantic` | no | `industry_chain.py` | `industry_chain.py` | `(keyword: Optional[str] = None, chain_id: Optional[str] = None)` |
| `get_investment_analysis` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `get_ipo_info` | `basic_data` | yes | `basic_data.py` | `basic_data.py` | `(ipo_type: int = 2, include_future: bool = True)` |
| `get_kline` | `market` | yes | `cache_manager.py` | `kline.py` | `(stock_code: str, period: str = 'daily', limit: int = 100) -> dict` |
| `get_kline_data` | `market` | yes | `kline.py` | `kline.py` | `(code: str, period: str = 'daily', start_date: str = None, end_date: str = None, limit: int = 30, adjust: str = '') -> dict` |
| `get_limit_up_statistics` | `market` | no | `cache_manager.py` | `limit_up.py` | `(date: str = '') -> dict` |
| `get_limit_up_stocks` | `market` | no | `cache_manager.py` | `limit_up.py` | `(date: str = '') -> dict` |
| `get_macro_indicator` | `macro` | no | `cache_manager.py` | `macro.py` | `(indicator: str, limit: int = 120) -> dict` |
| `get_margin_data` | `risk` | no | `fund_flow_market.py` | `fund_flow_market.py` | `(stock_code: str = '', days: int = 30) -> dict` |
| `get_margin_ranking` | `risk` | no | `fund_flow_market.py` | `fund_flow_market.py` | `(top_n: int = 20, sort_by: str = 'balance') -> dict` |
| `get_market_blocks` | `sector` | yes | `server.py` | `server.py` | `(block_type: 'str' = 'industry', limit: 'int \| None' = None)` |
| `get_market_news` | `news` | no | `cache_manager.py` | `news_feed.py` | `(limit: int = 20) -> dict` |
| `get_market_sentiment_context` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(north_days: int = 5, margin_days: int = 10, top_sector_n: int = 5)` |
| `get_minute_kline` | `market` | no | `cache_manager.py` | `kline.py` | `(stock_code: str, period: str = '5m', limit: int = 300) -> dict` |
| `get_north_fund` | `fund_flow` | no | `cache_manager.py` | `fund_flow_north.py` | `(days: int = 30) -> dict` |
| `get_north_fund_holding` | `fund_flow` | no | `fund_flow_north.py` | `fund_flow_north.py` | `(stock_code: str) -> dict` |
| `get_north_fund_top` | `fund_flow` | no | `fund_flow_north.py` | `fund_flow_north.py` | `(top_n: int = 20) -> dict` |
| `get_option_chain` | `options` | no | `cache_manager.py` | `options.py` | `(underlying: str, expiry_month: str = '', limit: int = 200) -> dict` |
| `get_order_book` | `market` | no | `cache_manager.py` | `order_book.py` | `(stock_code: str) -> dict` |
| `get_profit_forecast` | `news` | no | `cache_manager.py` | `research.py` | `(symbol: str = '') -> dict` |
| `get_realtime_quote` | `market` | no | `quote.py` | `quote.py` | `(stock_code: str) -> dict` |
| `get_research_reports` | `news` | no | `cache_manager.py` | `research.py` | `(symbol: str = '', stock_code: str = '', limit: int = 10, *, prefer_db: bool = True) -> dict` |
| `get_research_summary` | `general` | yes | `research.py` | `research.py` | `(code: str, limit: int = 10)` |
| `get_sector_fund_flow` | `fund_flow` | no | `cache_manager.py` | `fund_flow_sector.py` | `(top_n: int = 20) -> dict` |
| `get_signal_hit_rate` | `quant` | yes | `quant.py` | `quant.py` | `(code: str, signal: str = 'rsi_oversold', forward_days: list = None, lookback_days: int = 250, signal_params: Optional[Dict[str, Any]] = None)` |
| `get_stock_capital` | `basic_data` | yes | `basic_data.py` | `basic_data.py` | `(code: Optional[str] = None, dates: Optional[List[str]] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `get_stock_fund_flow` | `fund_flow` | no | `fund_flow.py` | `fund_flow.py` | `(stock_code: str, *, prefer_db: bool = True) -> dict` |
| `get_stock_info` | `finance` | no | `cache_manager.py` | `finance.py` | `(stock_code: str) -> dict` |
| `get_stock_list` | `market` | no | `cache_manager.py` | `stock_list.py` | `() -> dict` |
| `get_stock_news` | `news` | no | `cache_manager.py` | `news_feed.py` | `(stock_code: str, limit: int = 20, *, prefer_db: bool = True) -> dict` |
| `get_stock_notices` | `news` | no | `cache_manager.py` | `notices.py` | `(start_date: str, end_date: str, types: Optional[list[str]] = None, stock_code: str = '', *, prefer_db: bool = True) -> dict` |
| `get_stock_research` | `news` | no | `cache_manager.py` | `research.py` | `(stock_code: str, limit: int = 10) -> dict` |
| `get_stock_text_signals` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(code: str \| None = None, news_limit: int = 20, notice_days: int = 30, report_limit: int = 10, stock_code: str \| None = None, symbol: str \| None = None, ticker: str \| None = None)` |
| `get_sync_status` | `data_sync` | no | `data_sync.py` | `data_sync.py` | `() -> dict` |
| `get_tool_contract` | `search` | no | `search.py` | `search.py` | `(tool_name: str)` |
| `get_trade_details` | `market` | no | `cache_manager.py` | `order_book.py` | `(stock_code: str, limit: int = 20) -> dict` |
| `get_trading_dates` | `basic_data` | yes | `basic_data.py` | `basic_data.py` | `(start_date: Optional[str] = None, end_date: Optional[str] = None, count: int = -1)` |
| `get_unified_decision` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, detail_level: 'str' = 'summary', investment_style: 'str' = 'balanced', user_id: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `get_unified_decision_details` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, investment_style: 'str' = 'balanced', user_id: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `get_unified_decision_summary` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, investment_style: 'str' = 'balanced', user_id: 'str \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `get_user_profile` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(user_id: str = 'default')` |
| `get_valuation_metrics` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `governance_check_workflow` | `general` | yes | `governance_workflow.py` | `governance_workflow.py` | `(target_type: 'str' = 'system', target_id: 'str \| None' = None, ic_history: 'list[float] \| None' = None, factor_expression: 'str' = '', factor_category: 'str \| None' = None, existing_factor_pool: 'list[str] \| None' = None, current_metrics: 'dict[str, Any] \| None' = None, baseline_metrics: 'dict[str, Any] \| None' = None, posture_level: 'str' = 'safe', control_mode: 'str' = 'active', open_alert_count: 'int' = 0, recovery_eligible: 'bool' = False, max_drawdown_pct: 'float \| None' = None, days_since_last_trade: 'int \| None' = None, backtest_assumptions: 'dict[str, Any] \| None' = None, execution_assumptions: 'dict[str, Any] \| None' = None, include_factor_decay: 'bool' = True, include_crowding: 'bool' = True, include_model_drift: 'bool' = True, include_strategy_health: 'bool' = True, include_consistency: 'bool' = True, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `industry_chain_manager` | `industry_chain` | yes | `industry_chain_manager.py` | `industry_chain_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `insight_manager` | `research` | yes | `insight_manager.py` | `insight_manager.py` | `(action: 'str', params: 'dict \| None' = None, kwargs: 'Any' = None)` |
| `limit_up_manager` | `market` | yes | `limit_up_manager.py` | `limit_up_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `list_factors` | `quant` | no | `quant.py` | `quant.py` | `(category: str = 'all')` |
| `list_industry_templates` | `finance` | yes | `valuation.py` | `valuation.py` | `()` |
| `list_skills` | `skills` | no | `skills.py` | `skills.py` | `()` |
| `live_trading_manager` | `general` | yes | `live_trading_manager.py` | `live_trading_manager.py` | `(action: 'str', params: 'dict \| None' = None, kwargs: 'Any' = None, code: 'str \| None' = None, symbol: 'str \| None' = None, order_id: 'str \| None' = None, status: 'str \| None' = None, limit: 'int \| None' = None, symbols: 'list[str] \| None' = None, confirm_token: 'str \| None' = None, dry_run: 'bool \| None' = None, side: 'str \| None' = None, qty: 'float \| None' = None, quantity: 'float \| None' = None, notional: 'float \| None' = None, type: 'str \| None' = None, time_in_force: 'str \| None' = None, limit_price: 'float \| None' = None, stop_price: 'float \| None' = None, client_order_id: 'str \| None' = None, extended_hours: 'bool \| None' = None, artifact_id: 'str \| None' = None, output_artifact_id: 'str \| None' = None, paper_account_id: 'str \| None' = None, execute: 'bool \| None' = None, persist_artifact: 'bool \| None' = None)` |
| `log_recommendation_audit` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(user_id: str = 'default', strategy_id: str = '', code: str = '', stock_code: str = '', action: str = '', emotion_polarity: float = 0.0, emotion_intensity: float = 0.0, cognitive_biases='', risk_aversion: float = 2.5, kyc_level: str = '', reasoning_chain: str = '')` |
| `macro_manager` | `macro` | yes | `macro_manager.py` | `macro_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `market_insight_manager` | `market` | yes | `market_insight_manager.py` | `market_insight_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, sector: str \| None = None)` |
| `optimize_portfolio` | `portfolio` | yes | `portfolio.py` | `portfolio.py` | `(stocks: List[str], method: str = 'equal_weight', lookback_days: int = 252, risk_aversion: float = 1.0, risk_free_rate: float = 0.03, market_weights: Optional[List[float]] = None, views: Optional[List[Dict[str, Any]]] = None, risk_budgets: Optional[List[float]] = None, max_weight: float = 0.35)` |
| `options_manager` | `options` | yes | `options_manager.py` | `options_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `paper_trading_manager` | `paper_trading` | yes | `paper_trading_manager.py` | `paper_trading_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, user_id: str \| None = None, account_id: str \| None = None, code: str \| None = None, price: float \| None = None, shares: int \| None = None, quantity: int \| None = None, order_id: str \| None = None, trade_type: str \| None = None, direction: str \| None = None, order_type: str \| None = None, stop_price: float \| None = None, name: str \| None = None, initial_capital: float \| None = None, limit: int \| None = None) -> dict` |
| `parse_selection_query` | `semantic` | no | `query_parser.py` | `query_parser.py` | `(query: str)` |
| `performance_manager` | `performance` | yes | `performance_manager.py` | `performance_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, portfolio_id: str \| int \| None = None, backtest_id: str \| None = None, artifact_id: str \| None = None, benchmark: str \| None = None, lookback_days: int \| None = None) -> dict` |
| `portfolio_manager` | `portfolio` | yes | `portfolio_manager.py` | `portfolio_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, user_id: str \| None = None, portfolio_id: int \| None = None, code: str \| None = None, shares: int \| None = None, cost_price: float \| None = None, name: str \| None = None, description: str \| None = None, initial_capital: float \| None = None, updates: dict \| None = None)` |
| `prediction_diagnosis_workflow` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(probabilities: 'list[float]', labels: 'list[Any] \| None' = None, outcomes: 'list[Any] \| None' = None, raw_scores: 'list[float] \| None' = None, method: 'str' = 'raw', platt_a: 'float' = 1.0, platt_b: 'float' = 0.0, coverage_target: 'float' = 0.9, dataset_id: 'str \| None' = None, run_id: 'str \| None' = None, persist_artifact: 'bool' = False, output_artifact_id: 'str \| None' = None, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `quant_manager` | `quant` | yes | `quant_manager.py` | `quant_manager.py` | `(action: str, code: Optional[str] = None, kwargs: Any = None, params: Any = None) -> dict` |
| `relative_valuation` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, metrics: Optional[List[str]] = None, peers: Optional[List[str]] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `research_manager` | `research` | yes | `research_manager.py` | `research_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None, limit: int \| None = None)` |
| `risk_manager` | `risk` | yes | `risk_manager.py` | `risk_manager.py` | `(action: 'str', params: 'dict \| None' = None, kwargs: 'Any' = None, portfolio_id: 'str \| int \| None' = None, codes: 'list[str] \| None' = None, weights: 'list[float] \| None' = None, scenario: 'str \| None' = None, scenarios: 'list[str] \| None' = None, confidence: 'float \| None' = None, method: 'str \| None' = None, lookback_days: 'int \| None' = None, portfolio_value: 'float \| None' = None) -> 'dict'` |
| `run_batch_backtest` | `backtest` | yes | `backtest.py` | `backtest.py` | `(codes: List[str], strategy: str = 'ma_cross', start_date: Optional[str] = None, end_date: Optional[str] = None, initial_capital: float = 100000, commission: float = 0.0003, short_period: int = 5, long_period: int = 20, use_parallel: bool = True, fetch_concurrency: int = 8, warmup_before_fetch: bool = False, as_of: Optional[str] = None)` |
| `run_decision_gate` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, investment_style: 'str' = 'balanced', user_id: 'str \| None' = None, stock_context: 'dict \| None' = None, quant_context: 'dict \| None' = None, event_context: 'dict \| None' = None, user_context: 'dict \| None' = None, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `run_simple_backtest` | `backtest` | yes | `backtest.py` | `backtest.py` | `(code: str, strategy: str = 'ma_cross', start_date: Optional[str] = None, end_date: Optional[str] = None, initial_capital: float = 100000, commission: float = 0.0003, short_period: int = 5, long_period: int = 20, benchmark: str = '000300', slippage: float = 0.0, as_of: Optional[str] = None)` |
| `run_skill` | `skills` | yes | `skills.py` | `skills.py` | `(skill_id: 'str', params: 'dict' = None)` |
| `scenario_dcf_valuation` | `finance` | yes | `valuation.py` | `valuation.py` | `(code: Optional[str] = None, base_revenue: float = 0.0, industry: Optional[str] = None, years: int = 5, tax_rate: float = 0.25, risk_free_rate: float = 0.028, market_risk_premium: float = 0.06, shares_outstanding: Optional[float] = None, bull_probability: float = 0.25, base_probability: float = 0.5, bear_probability: float = 0.25, bull_growth_premium: float = 0.05, bear_growth_discount: float = 0.05, bull_margin_premium: float = 0.03, bear_margin_discount: float = 0.03, custom_scenarios: Optional[List[dict]] = None, growth_rate: Optional[float] = None, profit_margin: Optional[float] = None, capex_ratio: Optional[float] = None, depreciation_ratio: Optional[float] = None, nwc_ratio: Optional[float] = None, beta: Optional[float] = None, equity_weight: Optional[float] = None, debt_weight: Optional[float] = None, cost_of_debt: Optional[float] = None, terminal_growth: Optional[float] = None, enable_distribution: bool = False, distribution_samples: int = 1000, distribution_growth_std: float = 0.2, distribution_margin_std: float = 0.15, distribution_discount_std: float = 0.1, distribution_terminal_std: float = 0.1, distribution_seed: Optional[int] = None, stock_code: Optional[str] = None, symbol: Optional[str] = None, ticker: Optional[str] = None)` |
| `screener_manager` | `screening` | yes | `screener_manager.py` | `screener_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `search_by_kline` | `vector` | yes | `vector.py` | `vector.py` | `(code: 'str', days: 'int' = 20, top_n: 'int' = 10, search_backend: 'str' = 'db', allow_fallback: 'bool' = True)` |
| `search_research` | `news` | no | `cache_manager.py` | `research.py` | `(keyword: str = '', stock_code: str = '', days: int = 90) -> dict` |
| `search_research_db` | `general` | yes | `research.py` | `research.py` | `(keyword: str = None, stock_code: str = None, days: int = 30)` |
| `search_similar_stocks` | `vector` | yes | `vector.py` | `vector.py` | `(code: 'str', top_n: 'int' = 10, similarity_type: 'str' = 'both', search_backend: 'str' = 'db', allow_fallback: 'bool' = True)` |
| `search_skills` | `skills` | no | `skills.py` | `skills.py` | `(keyword: 'str')` |
| `search_stocks` | `search` | yes | `search.py` | `search.py` | `(keyword: str, limit: int = 20)` |
| `sector_manager` | `sector` | yes | `sector_manager.py` | `sector_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, sector: str \| None = None, block_code: str \| None = None, block_type: str \| None = None, sectors: list[str] \| None = None, period: int \| None = None, days: int \| None = None)` |
| `semantic_stock_search` | `vector` | yes | `vector.py` | `vector.py` | `(query: 'str', limit: 'int' = 20)` |
| `sentiment_manager` | `sentiment` | yes | `sentiment_manager.py` | `sentiment_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `should_i_buy` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, investment_style: 'str' = 'balanced', as_of: 'str' = '', adjust: 'str' = '', price_source_policy: 'str' = 'auto', explain: 'bool' = True, strict_mode: 'bool' = False, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `should_i_sell` | `decision` | yes | `decision.py` | `decision.py` | `(code: 'str \| None' = None, buy_price: 'float' = 0.0, holding_days: 'int' = 0, stock_code: 'str \| None' = None, symbol: 'str \| None' = None, ticker: 'str \| None' = None)` |
| `smart_stock_diagnosis` | `semantic` | yes | `diagnosis.py` | `diagnosis.py` | `(stock_code: str)` |
| `strategy_manager` | `strategy` | yes | `strategy_manager.py` | `strategy_manager.py` | `(action: str, kwargs: Any = '{}', params: Any = None) -> dict` |
| `strategy_review_workflow` | `general` | yes | `ai_workflows.py` | `ai_workflows.py` | `(strategy_id: 'str', include_factory_status: 'bool' = True, include_review_report: 'bool' = True, include_runtime_alerts: 'bool' = True, run_factory_once: 'bool' = False, run_runtime_cycle: 'bool' = False, idempotency_key: 'str \| None' = None, as_of: 'str \| None' = None) -> 'dict[str, Any]'` |
| `stress_test_portfolio` | `portfolio` | yes | `portfolio.py` | `portfolio.py` | `(holdings: List[Dict[str, Any]], scenarios: Optional[List[str]] = None)` |
| `sync_kline_data` | `data_sync` | yes | `data_sync.py` | `data_sync.py` | `(stock_code: str, period: str = 'daily', start_date: str = '', end_date: str = '', limit: int = 100, use_cache: bool = True) -> dict` |
| `sync_trading_calendar` | `data_sync` | yes | `data_sync.py` | `data_sync.py` | `(year: int = None) -> dict` |
| `technical_analysis_manager` | `technical` | yes | `technical_analysis_manager.py` | `technical_analysis_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None, indicators: Optional[List[str]] = None, period: str = 'daily', limit: int = 250)` |
| `trading_data_manager` | `fund_flow` | yes | `trading_data_manager.py` | `trading_data_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None)` |
| `update_user_profile` | `sentiment` | yes | `sentiment.py` | `sentiment.py` | `(user_id: str = 'default', neuroticism: float = 0.5, openness: float = 0.5, herd_tendency: float = 0.5, greed_fear_axis: float = 0.0, confidence: float = 0.5)` |
| `user_manager` | `user` | yes | `user_manager.py` | `user_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, user_id: str \| None = None, actor_user_id: str \| None = None, preferences: dict \| None = None, limit: int \| None = None, allow_cross_user: bool \| None = None)` |
| `validate_factor_oos` | `quant` | yes | `quant.py` | `quant.py` | `(codes: list, factor: str, factor_lookback: int = 20, forward_period: int = 20, panel_periods: int = 180, wf_train_window: int = 60, wf_test_window: int = 20, wf_step: int = 0, kfold_n_folds: int = 5, kfold_purge_gap: int = 5, bootstrap_n: int = 1000, bootstrap_confidence: float = 0.95, validation_parallel: bool = True, max_workers: int = 0, bootstrap_mode: str = '', start_date: Optional[str] = None, end_date: Optional[str] = None, include_perf_breakdown: bool = True)` |
| `vector_search_manager` | `vector` | yes | `vector_search_manager.py` | `vector_search_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, code: str \| None = None, query: str \| None = None, top_n: int \| None = None, days: int \| None = None, similarity_type: str \| None = None, doc_types: list[str] \| None = None, limit: int \| None = None, search_backend: str \| None = None)` |
| `watchlist_manager` | `watchlist` | yes | `watchlist_manager.py` | `watchlist_manager.py` | `(action: str, params: dict \| None = None, kwargs: Any = None, user_id: str \| None = None, group_id: str \| None = None, code: str \| None = None, codes: list[str] \| None = None, name: str \| None = None, note: str \| None = None, color: str \| None = None, limit: int \| None = None, sort_order: int \| None = None)` |
