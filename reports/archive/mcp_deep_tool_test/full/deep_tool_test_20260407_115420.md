# AKShare MCP 155 Tools Deep Conversational Functional Test

- Executed at: `2026-04-07T12:00:06+08:00`
- Runtime tool count: **155**
- Tools passed: **123**
- Tools failed: **32**
- Total cases: **465**
- Case pass rate: **86.24%**
- Average latency: **736.5 ms**

## Input Audit

- `packages/akshare-mcp/TOOL_DOC_AUDIT_RAW.json`: missing
- Runtime registry fallback: `/Users/mac/Desktop/股票/reports/tool_registry/latest.json`
- Legacy results baseline: `/Users/mac/Desktop/股票/.mcp_full_test_results.json`

## Historical Comparison

- Fixed vs legacy: **36**
- Persistent failures: **3**
- Regressions: **29**

## Workflow Results

| Workflow | Status | Total Latency |
|----------|--------|---------------|
| `market_to_decision` | PASS | 708 ms |
| `finance_to_comprehensive` | PASS | 11 ms |
| `text_to_unified_decision` | PASS | 1741 ms |

## Defects

| Severity | Tool | Case | Observed | Historical |
|----------|------|------|----------|------------|
| P0 | `factor_candidate_workflow` | `primary` | timeout>45.0s | `ok` |
| P0 | `factor_candidate_workflow` | `variant` | timeout>45.0s | `ok` |
| P1 | `batch_sync_klines` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `batch_sync_klines` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `benchmark_manager` | `help` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `benchmark_manager` | `run_daily` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `calculate_factor` | `atr_factor` | time data '20250407' does not match format '%Y-%m-%d' | `error` |
| P1 | `clear_cache` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `clear_cache` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `clear_dead_letters` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `clear_dead_letters` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `execution_manager` | `twap_dry_run` | total_shares or total_quantity is required | `ok` |
| P1 | `fundamental_analysis_manager` | `intrinsic_value` | no valid free cash flow input for dcf valuation | `ok` |
| P1 | `fuse_decision_payload` | `primary` | quality_meta_not_observed; source_chain_not_observed | `error` |
| P1 | `fuse_decision_payload` | `with_partial_context` | quality_meta_not_observed; source_chain_not_observed | `error` |
| P1 | `get_batch_quotes` | `primary` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_batch_quotes` | `variant` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_batch_quotes_compat` | `primary` | missing_envelope_keys:timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_batch_quotes_compat` | `variant` | missing_envelope_keys:timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_block_stocks` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_block_stocks` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_concept_fund_flow` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_concept_fund_flow` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_dead_letters` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_dead_letters` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_dragon_tiger` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_dragon_tiger` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_index_quote` | `primary` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_index_quote` | `variant` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_investment_analysis` | `alias_variant` | quality_meta_not_observed; source_chain_not_observed | `failed` |
| P1 | `get_investment_analysis` | `primary` | quality_meta_not_observed; source_chain_not_observed | `failed` |
| P1 | `get_kline` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_kline` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_kline_data` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_kline_data` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_limit_up_statistics` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_limit_up_statistics` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_limit_up_stocks` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_limit_up_stocks` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_market_blocks` | `primary` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_market_blocks` | `variant` | missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_market_news` | `primary` | quality_meta_not_observed; source_chain_not_observed; slow_response>10000ms | `ok` |
| P1 | `get_minute_kline` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_minute_kline` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_north_fund` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_north_fund` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_north_fund_holding` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_north_fund_holding` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_north_fund_top` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_north_fund_top` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_order_book` | `primary` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_order_book` | `variant` | missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_realtime_quote` | `bank_variant` | missing_envelope_keys:timestamp | `error` |
| P1 | `get_realtime_quote` | `primary` | missing_envelope_keys:timestamp | `error` |
| P1 | `get_stock_fund_flow` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_stock_fund_flow` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_stock_info` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_stock_info` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_stock_list` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P1 | `get_stock_list` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |

## Tool Matrix

| Tool | Category | Status | Quality Meta | Source Chain | Avg Latency | Historical |
|------|----------|--------|--------------|--------------|-------------|------------|
| `ai_workflow_artifact` | `general` | `passed` | yes | yes | 0 ms | `failed` |
| `alerts_manager` | `alerts` | `passed` | no | no | 1 ms | `ok` |
| `analyze_portfolio_risk` | `portfolio` | `passed` | yes | yes | 40 ms | `ok` |
| `analyze_portfolio_risk_barra` | `portfolio` | `passed` | yes | yes | 9 ms | `ok` |
| `analyze_research_report` | `general` | `passed` | no | no | 1 ms | `ok` |
| `analyze_stock_sentiment` | `sentiment` | `passed` | yes | no | 5 ms | `ok` |
| `analyze_stock_workflow` | `general` | `passed` | yes | yes | 2277 ms | `failed` |
| `available_tools` | `search` | `passed` | yes | yes | 3 ms | `ok` |
| `backtest_factor` | `quant` | `passed` | yes | yes | 36 ms | `failed` |
| `backtest_manager` | `backtest` | `passed` | yes | yes | 543 ms | `ok` |
| `batch_sync_klines` | `data_sync` | `failed` | no | no | 90 ms | `ok` |
| `benchmark_manager` | `backtest` | `passed` | no | no | 22 ms | `ok` |
| `build_event_context` | `decision` | `passed` | yes | yes | 158 ms | `error` |
| `build_quant_context` | `decision` | `passed` | yes | yes | 129 ms | `error` |
| `build_stock_context` | `decision` | `passed` | yes | yes | 417 ms | `error` |
| `calculate_factor` | `quant` | `failed` | no | no | 7 ms | `error` |
| `calculate_factor_ic` | `quant` | `passed` | yes | yes | 14 ms | `failed` |
| `calculate_fear_greed_index` | `sentiment` | `passed` | no | no | 359 ms | `ok` |
| `calculate_technical_indicators` | `technical` | `passed` | yes | yes | 2 ms | `ok` |
| `check_all_alerts` | `alerts` | `failed` | no | no | 2952 ms | `failed` |
| `check_candlestick_patterns` | `technical` | `passed` | yes | yes | 7 ms | `ok` |
| `clear_cache` | `data_sync` | `failed` | no | no | 0 ms | `ok` |
| `clear_dead_letters` | `data_sync` | `failed` | no | no | 0 ms | `ok` |
| `compliance_manager` | `compliance` | `passed` | no | no | 211 ms | `ok` |
| `comprehensive_manager` | `research` | `passed` | yes | yes | 189 ms | `ok` |
| `create_combo_alert` | `alerts` | `passed` | no | no | 3 ms | `ok` |
| `create_indicator_alert` | `alerts` | `passed` | no | no | 2 ms | `ok` |
| `data_quality_workflow` | `general` | `passed` | yes | yes | 0 ms | `ok` |
| `data_sync_manager` | `data_sync` | `passed` | no | no | 76 ms | `ok` |
| `data_validation` | `general` | `passed` | yes | yes | 1 ms | `failed` |
| `data_warmup` | `data_sync` | `passed` | no | no | 33 ms | `failed` |
| `dcf_valuation` | `finance` | `passed` | yes | yes | 2 ms | `failed` |
| `ddm_valuation` | `finance` | `passed` | yes | yes | 0 ms | `failed` |
| `decision_manager` | `decision` | `passed` | yes | yes | 588 ms | `ok` |
| `event_manager` | `news` | `passed` | yes | yes | 204 ms | `ok` |
| `execution_manager` | `execution` | `failed` | no | no | 1 ms | `ok` |
| `experiment_tracker` | `general` | `passed` | yes | yes | 0 ms | `failed` |
| `factor_candidate_workflow` | `general` | `failed` | no | no | 45001 ms | `ok` |
| `factor_robustness_check` | `quant` | `passed` | no | no | 102 ms | `ok` |
| `find_similar_patterns` | `quant` | `passed` | no | no | 11 ms | `ok` |
| `fundamental_analysis_manager` | `finance` | `failed` | yes | yes | 59 ms | `ok` |
| `fuse_decision_payload` | `decision` | `passed` | no | no | 724 ms | `error` |
| `generate_daily_report` | `semantic` | `passed` | no | no | 3837 ms | `ok` |
| `get_analyst_ranking` | `news` | `passed` | no | no | 78 ms | `ok` |
| `get_available_categories` | `search` | `passed` | yes | yes | 0 ms | `ok` |
| `get_available_patterns` | `technical` | `passed` | yes | yes | 0 ms | `ok` |
| `get_batch_quotes` | `market` | `failed` | no | no | 401 ms | `ok` |
| `get_batch_quotes_compat` | `market` | `failed` | no | no | 748 ms | `ok` |
| `get_block_stocks` | `sector` | `failed` | no | no | 110 ms | `ok` |
| `get_block_trades` | `fund_flow` | `failed` | yes | yes | 2549 ms | `ok` |
| `get_cache_stats` | `data_sync` | `passed` | no | no | 0 ms | `ok` |
| `get_cb_info` | `basic_data` | `passed` | yes | yes | 41 ms | `failed` |
| `get_concept_fund_flow` | `fund_flow` | `passed` | no | no | 629 ms | `ok` |
| `get_conditional_returns` | `quant` | `passed` | no | no | 24 ms | `failed` |
| `get_dead_letters` | `data_sync` | `failed` | no | no | 0 ms | `ok` |
| `get_dragon_tiger` | `fund_flow` | `passed` | no | no | 325 ms | `ok` |
| `get_factor_library` | `quant` | `passed` | no | no | 0 ms | `ok` |
| `get_factor_profile` | `factor` | `passed` | no | no | 1601 ms | `ok` |
| `get_financials` | `finance` | `passed` | yes | yes | 0 ms | `ok` |
| `get_historical_valuation` | `finance` | `passed` | yes | yes | 44 ms | `failed` |
| `get_index_quote` | `market` | `failed` | no | no | 936 ms | `ok` |
| `get_industry_chain` | `semantic` | `passed` | no | no | 0 ms | `ok` |
| `get_investment_analysis` | `decision` | `passed` | no | no | 23 ms | `failed` |
| `get_ipo_info` | `basic_data` | `passed` | yes | yes | 201 ms | `ok` |
| `get_kline` | `market` | `failed` | yes | yes | 137 ms | `ok` |
| `get_kline_data` | `market` | `failed` | yes | yes | 657 ms | `ok` |
| `get_limit_up_statistics` | `market` | `failed` | yes | yes | 1876 ms | `ok` |
| `get_limit_up_stocks` | `market` | `failed` | yes | yes | 1721 ms | `ok` |
| `get_macro_indicator` | `macro` | `passed` | yes | yes | 146 ms | `ok` |
| `get_margin_data` | `risk` | `passed` | no | no | 142 ms | `ok` |
| `get_margin_ranking` | `risk` | `passed` | no | no | 127 ms | `ok` |
| `get_market_blocks` | `sector` | `failed` | no | no | 113 ms | `ok` |
| `get_market_news` | `news` | `passed` | no | no | 6770 ms | `ok` |
| `get_market_sentiment_context` | `sentiment` | `passed` | yes | yes | 4454 ms | `ok` |
| `get_minute_kline` | `market` | `failed` | yes | yes | 1789 ms | `ok` |
| `get_north_fund` | `fund_flow` | `passed` | no | no | 113 ms | `ok` |
| `get_north_fund_holding` | `fund_flow` | `passed` | no | no | 70 ms | `ok` |
| `get_north_fund_top` | `fund_flow` | `passed` | no | no | 65 ms | `ok` |
| `get_option_chain` | `options` | `passed` | yes | yes | 448 ms | `ok` |
| `get_order_book` | `market` | `failed` | no | no | 112 ms | `ok` |
| `get_profit_forecast` | `news` | `passed` | no | no | 570 ms | `ok` |
| `get_realtime_quote` | `market` | `failed` | yes | yes | 333 ms | `error` |
| `get_research_reports` | `news` | `passed` | no | no | 231 ms | `ok` |
| `get_research_summary` | `general` | `passed` | no | no | 131 ms | `ok` |
| `get_sector_fund_flow` | `fund_flow` | `passed` | no | no | 6853 ms | `ok` |
| `get_signal_hit_rate` | `quant` | `passed` | no | no | 45 ms | `ok` |
| `get_stock_capital` | `basic_data` | `passed` | yes | yes | 158 ms | `failed` |
| `get_stock_fund_flow` | `fund_flow` | `passed` | no | no | 105 ms | `ok` |
| `get_stock_info` | `finance` | `passed` | no | no | 700 ms | `ok` |
| `get_stock_list` | `market` | `passed` | no | no | 0 ms | `ok` |
| `get_stock_news` | `news` | `passed` | no | no | 216 ms | `ok` |
| `get_stock_notices` | `news` | `passed` | no | no | 7271 ms | `error` |
| `get_stock_research` | `news` | `passed` | no | no | 163 ms | `ok` |
| `get_stock_text_signals` | `sentiment` | `passed` | yes | yes | 135 ms | `failed` |
| `get_sync_status` | `data_sync` | `failed` | no | no | 0 ms | `ok` |
| `get_tool_contract` | `search` | `passed` | yes | yes | 0 ms | `ok` |
| `get_trade_details` | `market` | `failed` | no | no | 268 ms | `ok` |
| `get_trading_dates` | `basic_data` | `passed` | yes | yes | 162 ms | `ok` |
| `get_unified_decision` | `decision` | `passed` | yes | no | 755 ms | `error` |
| `get_unified_decision_details` | `decision` | `passed` | yes | no | 806 ms | `error` |
| `get_unified_decision_summary` | `decision` | `passed` | yes | no | 872 ms | `error` |
| `get_user_profile` | `sentiment` | `passed` | no | no | 4 ms | `ok` |
| `get_valuation_metrics` | `finance` | `passed` | yes | no | 2 ms | `failed` |
| `governance_check_workflow` | `general` | `passed` | yes | yes | 0 ms | `ok` |
| `industry_chain_manager` | `industry_chain` | `failed` | yes | yes | 0 ms | `ok` |
| `insight_manager` | `research` | `passed` | yes | yes | 0 ms | `ok` |
| `limit_up_manager` | `market` | `passed` | yes | yes | 285 ms | `ok` |
| `list_factors` | `quant` | `passed` | no | no | 0 ms | `ok` |
| `list_industry_templates` | `finance` | `passed` | no | no | 0 ms | `ok` |
| `list_skills` | `skills` | `passed` | no | no | 4 ms | `ok` |
| `live_trading_manager` | `general` | `passed` | no | no | 49 ms | `ok` |
| `log_recommendation_audit` | `sentiment` | `failed` | no | no | 3 ms | `ok` |
| `macro_manager` | `macro` | `passed` | yes | yes | 766 ms | `ok` |
| `market_insight_manager` | `market` | `passed` | yes | yes | 3577 ms | `ok` |
| `optimize_portfolio` | `portfolio` | `passed` | yes | yes | 12 ms | `error` |
| `options_manager` | `options` | `passed` | no | no | 291 ms | `ok` |
| `paper_trading_manager` | `paper_trading` | `passed` | no | no | 3 ms | `ok` |
| `parse_selection_query` | `semantic` | `passed` | no | no | 0 ms | `ok` |
| `performance_manager` | `performance` | `passed` | yes | yes | 1 ms | `ok` |
| `portfolio_manager` | `portfolio` | `passed` | yes | yes | 2 ms | `ok` |
| `prediction_diagnosis_workflow` | `general` | `passed` | yes | yes | 1 ms | `error` |
| `quant_manager` | `quant` | `failed` | yes | yes | 5 ms | `ok` |
| `relative_valuation` | `finance` | `passed` | no | no | 12 ms | `failed` |
| `research_manager` | `research` | `passed` | yes | yes | 148 ms | `ok` |
| `risk_manager` | `risk` | `passed` | yes | yes | 12 ms | `ok` |
| `run_batch_backtest` | `backtest` | `passed` | yes | yes | 19 ms | `ok` |
| `run_decision_gate` | `decision` | `passed` | no | no | 758 ms | `error` |
| `run_simple_backtest` | `backtest` | `failed` | yes | yes | 419 ms | `ok` |
| `run_skill` | `skills` | `passed` | no | no | 1465 ms | `ok` |
| `scenario_dcf_valuation` | `finance` | `passed` | yes | no | 0 ms | `failed` |
| `screener_manager` | `screening` | `passed` | no | no | 5 ms | `ok` |
| `search_by_kline` | `vector` | `passed` | no | no | 68 ms | `error` |
| `search_research` | `news` | `passed` | no | no | 357 ms | `ok` |
| `search_research_db` | `general` | `passed` | no | no | 2 ms | `ok` |
| `search_similar_stocks` | `vector` | `passed` | no | no | 62 ms | `error` |
| `search_skills` | `skills` | `passed` | no | no | 1 ms | `error` |
| `search_stocks` | `search` | `passed` | yes | yes | 87 ms | `ok` |
| `sector_manager` | `sector` | `passed` | yes | yes | 490 ms | `ok` |
| `semantic_stock_search` | `vector` | `passed` | no | no | 274 ms | `error` |
| `sentiment_manager` | `sentiment` | `failed` | yes | yes | 150 ms | `ok` |
| `should_i_buy` | `decision` | `passed` | yes | yes | 37 ms | `error` |
| `should_i_sell` | `decision` | `passed` | no | no | 22 ms | `error` |
| `smart_stock_diagnosis` | `semantic` | `passed` | no | no | 14 ms | `ok` |
| `strategy_manager` | `strategy` | `passed` | yes | yes | 11 ms | `ok` |
| `strategy_review_workflow` | `general` | `passed` | yes | yes | 3 ms | `ok` |
| `stress_test_portfolio` | `portfolio` | `passed` | yes | yes | 0 ms | `ok` |
| `sync_kline_data` | `data_sync` | `failed` | no | no | 2 ms | `ok` |
| `sync_trading_calendar` | `data_sync` | `failed` | no | no | 131 ms | `ok` |
| `technical_analysis_manager` | `technical` | `passed` | yes | yes | 5 ms | `ok` |
| `trading_data_manager` | `fund_flow` | `passed` | yes | yes | 117 ms | `ok` |
| `update_user_profile` | `sentiment` | `passed` | no | no | 2 ms | `ok` |
| `user_manager` | `user` | `passed` | yes | yes | 2 ms | `ok` |
| `validate_factor_oos` | `quant` | `passed` | yes | yes | 53 ms | `failed` |
| `vector_search_manager` | `vector` | `failed` | yes | yes | 34 ms | `ok` |
| `watchlist_manager` | `watchlist` | `passed` | no | no | 1 ms | `ok` |

## Detailed Defects

### P0 `factor_candidate_workflow` / `primary`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/ai_workflows.py`
- Repro payload: `{"candidate_count": 6, "codes": ["600519", "000001"], "task": "pipeline"}`
- Observed: `timeout>45.0s`

### P0 `factor_candidate_workflow` / `variant`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/ai_workflows.py`
- Repro payload: `{"candidate_count": 6, "codes": ["300750", "688981", "002415"], "task": "pipeline"}`
- Observed: `timeout>45.0s`

### P1 `batch_sync_klines` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"codes": ["600519"]}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `batch_sync_klines` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"codes": ["300750", "688981", "002415"]}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `benchmark_manager` / `help`

- Category: `backtest`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/benchmark_manager.py`
- Repro payload: `{"action": "help"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `benchmark_manager` / `run_daily`

- Category: `backtest`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/benchmark_manager.py`
- Repro payload: `{"action": "run_daily"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `calculate_factor` / `atr_factor`

- Category: `quant`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"code": "000001", "end_date": "20260407", "factor": "atr_14", "start_date": "20250407"}`
- Observed: `time data '20250407' does not match format '%Y-%m-%d'`

### P1 `clear_cache` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `clear_cache` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `clear_dead_letters` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `clear_dead_letters` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `execution_manager` / `twap_dry_run`

- Category: `execution`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/execution_manager.py`
- Repro payload: `{"action": "twap", "dry_run": true, "params": {"code": "600519", "qty": 100, "side": "buy"}}`
- Observed: `total_shares or total_quantity is required`

### P1 `fundamental_analysis_manager` / `intrinsic_value`

- Category: `finance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/fundamental_analysis_manager.py`
- Repro payload: `{"action": "intrinsic_value", "code": "600036"}`
- Observed: `no valid free cash flow input for dcf valuation`

### P1 `fuse_decision_payload` / `primary`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"code": "600519", "investment_style": "balanced"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `fuse_decision_payload` / `with_partial_context`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"code": "000001", "event_context": {"news": []}, "stock_context": {"code": "000001"}}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_batch_quotes` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"codes": ["600519"], "stock_codes": ["600519"]}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_batch_quotes` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"codes": ["300750", "688981", "002415"], "stock_codes": ["600519"]}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_batch_quotes_compat` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"codes": ["600519"]}`
- Observed: `missing_envelope_keys:timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_batch_quotes_compat` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"codes": ["300750", "688981", "002415"]}`
- Observed: `missing_envelope_keys:timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_block_stocks` / `primary`

- Category: `sector`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/server.py`
- Repro payload: `{"block_code": "new_jjhy"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_block_stocks` / `variant`

- Category: `sector`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/server.py`
- Repro payload: `{"_variant_marker": "extra", "block_code": "new_jjhy"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_concept_fund_flow` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_sector.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_concept_fund_flow` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_sector.py`
- Repro payload: `{"top_n": 5}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_dead_letters` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"limit": 10}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_dead_letters` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"limit": 15}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_dragon_tiger` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_market.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_dragon_tiger` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_market.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_index_quote` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"index_code": "000001"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_index_quote` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"_variant_marker": "extra", "index_code": "000001"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_investment_analysis` / `alias_variant`

- Category: `decision`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_investment_analysis` / `primary`

- Category: `decision`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_kline` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 3, "stock_code": "600519"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_kline` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 3, "stock_code": "000001"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_kline_data` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"code": "600519", "limit": 10}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_kline_data` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"code": "000001", "limit": 10}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_limit_up_statistics` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/limit_up.py`
- Repro payload: `{"date": "2026-04-06"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_limit_up_statistics` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/limit_up.py`
- Repro payload: `{"_variant_marker": "extra", "date": "2026-04-06"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_limit_up_stocks` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/limit_up.py`
- Repro payload: `{"date": "2026-04-06"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_limit_up_stocks` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/limit_up.py`
- Repro payload: `{"_variant_marker": "extra", "date": "2026-04-06"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_market_blocks` / `primary`

- Category: `sector`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/server.py`
- Repro payload: `{"limit": 10}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_market_blocks` / `variant`

- Category: `sector`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/server.py`
- Repro payload: `{"limit": 15}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_market_news` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`
- Repro payload: `{"limit": 5}`
- Observed: `quality_meta_not_observed; source_chain_not_observed; slow_response>10000ms`

### P1 `get_minute_kline` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 60, "period": "5m", "stock_code": "600519"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_minute_kline` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 40, "period": "15m", "stock_code": "000001"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_north_fund` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{"days": 30}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_north_fund` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{"days": 60}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_north_fund_holding` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_north_fund_holding` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_north_fund_top` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_north_fund_top` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py`
- Repro payload: `{"top_n": 5}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_order_book` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_order_book` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_realtime_quote` / `bank_variant`

- Category: `market`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_realtime_quote` / `primary`

- Category: `market`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_stock_fund_flow` / `primary`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_fund_flow` / `variant`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_info` / `primary`

- Category: `finance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/finance.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_info` / `variant`

- Category: `finance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/finance.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_list` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/stock_list.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_list` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/stock_list.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `get_stock_notices` / `all_notices`

- Category: `news`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/notices.py`
- Repro payload: `{"end_date": "2026-04-07", "prefer_db": false, "start_date": "2026-03-08"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed; slow_response>10000ms`

### P1 `get_sync_status` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_sync_status` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_trade_details` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py`
- Repro payload: `{"limit": 10, "stock_code": "600519"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `get_trade_details` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/order_book.py`
- Repro payload: `{"limit": 10, "stock_code": "000001"}`
- Observed: `missing_envelope_keys:source,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `industry_chain_manager` / `get_chain`

- Category: `industry_chain`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/industry_chain_manager.py`
- Repro payload: `{"action": "get_chain", "params": {"keyword": "白酒"}}`
- Observed: `需要提供行业名称（可传 industry / keyword / query / sector / chain_id 等）`

### P1 `industry_chain_manager` / `related_stocks`

- Category: `industry_chain`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/industry_chain_manager.py`
- Repro payload: `{"action": "related_stocks", "params": {"keyword": "半导体"}}`
- Observed: `需要提供股票代码或产业链关键词`

### P1 `list_industry_templates` / `primary`

- Category: `finance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `list_industry_templates` / `variant`

- Category: `finance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `market_insight_manager` / `sector_analysis`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/market_insight_manager.py`
- Repro payload: `{"action": "sector_analysis", "sector": "白酒"}`
- Observed: `slow_response>10000ms`

### P1 `quant_manager` / `calculate_factors`

- Category: `quant`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`
- Repro payload: `{"action": "calculate_factors", "code": "600519", "params": {"factors": ["mom_5d", "atr_14"]}}`
- Observed: `Unsupported factors: ['mom_5d', 'atr_14']. Supported: ['alternative_composite', 'capital_flow', 'event', 'growth', 'liquidity', 'momentum', 'quality', 'sentiment', 'value', 'volatility']`

### P1 `relative_valuation` / `bank_variant`

- Category: `finance`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- Repro payload: `{"metrics": ["pe_ratio"], "peers": ["601166", "000001"], "stock_code": "600036"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `relative_valuation` / `primary`

- Category: `finance`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- Repro payload: `{"code": "600519", "metrics": ["pe_ratio", "pb_ratio"], "peers": ["000858", "000596", "600809"]}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `run_decision_gate` / `primary`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"code": "600519", "investment_style": "balanced"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `run_decision_gate` / `variant`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"investment_style": "value", "stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `run_simple_backtest` / `variant`

- Category: `backtest`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/backtest.py`
- Repro payload: `{"code": "000001", "end_date": "20260407", "start_date": "20260107", "stock_codes": "600519", "strategy": "buy_and_hold"}`
- Observed: `Error executing tool run_simple_backtest: 无法解析 as_of 时间：'20260407'`

### P1 `sentiment_manager` / `stock_sentiment`

- Category: `sentiment`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/sentiment_manager.py`
- Repro payload: `{"action": "stock_sentiment", "params": {"code": "000858"}}`
- Observed: `需要提供股票代码`

### P1 `should_i_sell` / `primary`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"buy_price": 1500.0, "code": "600519", "holding_days": 120}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `should_i_sell` / `variant`

- Category: `decision`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/decision.py`
- Repro payload: `{"buy_price": 10.0, "holding_days": 30, "stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P1 `sync_kline_data` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"limit": 10, "stock_code": "600519"}`
- Observed: `missing_envelope_keys:cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `sync_kline_data` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"limit": 10, "stock_code": "000001"}`
- Observed: `missing_envelope_keys:cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `sync_trading_calendar` / `primary`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{}`
- Observed: `missing_envelope_keys:cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `sync_trading_calendar` / `variant`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"year": "2025"}`
- Observed: `missing_envelope_keys:cached,timestamp; quality_meta_not_observed; source_chain_not_observed`

### P1 `vector_search_manager` / `market_docs`

- Category: `vector`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/vector_search_manager.py`
- Repro payload: `{"action": "market_docs", "limit": 5, "query": "白酒 行业 研报"}`
- Observed: `需要提供股票代码`

### P2 `alerts_manager` / `create_indicator`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/alerts_manager.py`
- Repro payload: `{"action": "create", "code": "600519", "condition": ">", "indicator": "rsi", "user_id": "deep_user_20260407_115420", "value": 70}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `alerts_manager` / `list_active`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/alerts_manager.py`
- Repro payload: `{"action": "list", "status": "active", "user_id": "deep_user_20260407_115420"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_research_report` / `primary`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_research_report` / `variant`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_stock_sentiment` / `primary`

- Category: `sentiment`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py`
- Repro payload: `{"code": "600519"}`
- Observed: `source_chain_not_observed`

### P2 `analyze_stock_sentiment` / `variant`

- Category: `sentiment`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py`
- Repro payload: `{"code": "000001"}`
- Observed: `source_chain_not_observed`

### P2 `batch_sync_klines` / `missing_required`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"codes": []}`
- Observed: `missing_envelope_keys:source,cached,timestamp`

### P2 `calculate_factor` / `mom_factor`

- Category: `quant`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"code": "600519", "end_date": "2026-04-07", "factor": "mom_5d", "start_date": "2025-04-07"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `calculate_fear_greed_index` / `primary`

- Category: `sentiment`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `calculate_fear_greed_index` / `variant`

- Category: `sentiment`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py`
- Repro payload: `{"unexpected": "variant"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `check_all_alerts` / `default`

- Category: `alerts`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `check_all_alerts` / `indicator_only`

- Category: `alerts`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"alert_type": "indicator", "status": "active"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `check_all_alerts` / `invalid_type`

- Category: `alerts`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"alert_type": "unknown"}`
- Observed: `unexpected_behavior`

### P2 `clear_cache` / `unexpected_extra`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"__unexpected__": "x"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; extra_params_accepted_or_ignored`

### P2 `clear_dead_letters` / `unexpected_extra`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_sync.py`
- Repro payload: `{"__unexpected__": "x"}`
- Observed: `missing_envelope_keys:source,cached,timestamp; extra_params_accepted_or_ignored`

### P2 `compliance_manager` / `check_trade`

- Category: `compliance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/compliance_manager.py`
- Repro payload: `{"action": "check_trade", "params": {"code": "600519", "price": 1700.0, "qty": 100, "side": "buy"}}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `compliance_manager` / `rules`

- Category: `compliance`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/compliance_manager.py`
- Repro payload: `{"action": "rules"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `create_combo_alert` / `primary`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"conditions": [{"code": "600519", "condition": ">", "indicator": "rsi", "value": 99}], "logic": "AND", "name": "mcp_smoke_combo_20260407_115420"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `create_combo_alert` / `variant`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"_variant_marker": "extra", "conditions": [{"code": "600519", "condition": ">", "indicator": "rsi", "value": 99}], "logic": "AND", "name": "mcp_smoke_combo_20260407_115420"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `create_indicator_alert` / `primary`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"code": "600519", "condition": ">", "indicator": "rsi", "value": 99.0}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `create_indicator_alert` / `variant`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/alerts.py`
- Repro payload: `{"code": "000001", "condition": ">", "indicator": "rsi", "value": 99.0}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `data_sync_manager` / `list_tasks`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/data_sync_manager.py`
- Repro payload: `{"action": "list_tasks", "limit": 5}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `data_sync_manager` / `status`

- Category: `data_sync`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/data_sync_manager.py`
- Repro payload: `{"action": "status"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `data_warmup` / `status`

- Category: `data_sync`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_warmup.py`
- Repro payload: `{"action": "status"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `data_warmup` / `warmup`

- Category: `data_sync`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/data_warmup.py`
- Repro payload: `{"action": "warmup", "include_financials": false, "lookback_days": 30, "stocks": ["600519"]}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `execution_manager` / `get_config`

- Category: `execution`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/execution_manager.py`
- Repro payload: `{"action": "get_config"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `factor_candidate_workflow` / `unexpected_extra`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/ai_workflows.py`
- Repro payload: `{"__unexpected__": "x"}`
- Observed: `timeout>45.0s`

### P2 `factor_robustness_check` / `primary`

- Category: `quant`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"codes": ["600519", "000001"], "factor": "mom_5d"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `factor_robustness_check` / `variant`

- Category: `quant`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"codes": ["300750", "688981", "002415"], "factor": "mom_5d"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `find_similar_patterns` / `primary`

- Category: `quant`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"code": "600519", "lookback_days": 90}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `find_similar_patterns` / `variant`

- Category: `quant`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
- Repro payload: `{"code": "000001", "lookback_days": 90}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `generate_daily_report` / `primary`

- Category: `semantic`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/semantic/daily_report.py`
- Repro payload: `{"date": "2026-04-06"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `generate_daily_report` / `variant`

- Category: `semantic`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/semantic/daily_report.py`
- Repro payload: `{"_variant_marker": "extra", "date": "2026-04-06"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_analyst_ranking` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_analyst_ranking` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"year": "2025"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_block_trades` / `negative_limit`

- Category: `fund_flow`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_market.py`
- Repro payload: `{"limit": -1, "stock_code": "600519"}`
- Observed: `unexpected_behavior`

## Improvement Suggestions

1. Fix wrapper signature mismatches and missing helpers first. `unexpected keyword argument 'args'` and `NameError` issues are P0 because they block core read-only flows.
2. Unify alias normalization against runtime schema. Several legacy smoke failures came from `codes` vs `code`, `query` vs `keyword`, and missing default date arguments.
3. Standardize quality metadata across market, finance, technical, valuation, decision, and backtest tools. At minimum expose `source_chain` and quality/degraded state in one consistent location.
4. Expand workflow-safe stateful test fixtures. Tools such as `ai_workflow_artifact`, `performance_manager`, and strategy-related actions benefit from reusable setup artifacts instead of hard-coded nonexistent IDs.
5. Restore the missing audit artifact. The requested `TOOL_DOC_AUDIT_RAW.json` is absent, so runtime registry export is currently the only reliable source of truth.

