# MCP Tools Test Report – Scenarios 14–20

**Server:** user-akshare-stock  
**Date:** 2026-03-06

---

## Scenario 14: 投研全链路

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | search_research | ✅ | 7 reports for "人工智能", total=7 |
| 2 | get_analyst_ranking | ✅ | 50 analysts, 申万宏源 rank 1 (116 reports) |
| 3 | get_research_reports | ✅ | stock_code valid, 10 reports for 600519 |
| 4 | get_stock_research | ✅ | 3 reports for 600519 (limit=3) |
| 5 | get_stock_notices | ✅ | events returned (start_date/end_date valid) |
| 6 | dcf_valuation | ✅ | intrinsic_value≈1.94B, WACC 7.43% |
| 7 | ddm_valuation | ✅ | intrinsic_value 324.64, Gordon model |
| 8 | relative_valuation | ✅ | PE 20.35, PB 7.73, 24 peers |
| 9 | scenario_dcf_valuation | ✅ | weighted_intrinsic_value≈227B |
| 10 | list_industry_templates | ✅ | 5 templates: 银行/制造/科技/消费/医药 |
| 11 | parse_selection_query | ✅ | parsed ROE>20%, suggestion for screener |
| 12 | get_industry_chain | ✅ | 白酒产业链 (liquor) |
| 13 | fundamental_analysis_manager | ✅ | help: analyze/dupont/compare (requires kwargs) |
| 14 | research_manager | ✅ | help: get_reports/get_ratings (requires kwargs) |
| 15 | insight_manager | ✅ | help: list/generate/daily_brief (requires kwargs) |

---

## Scenario 15: Manager工作流

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | comprehensive_manager | ✅ | help: full_analysis/quick_scan (requires kwargs) |
| 2 | decision_manager | ✅ | help: analyze/recommend/portfolio_advice (requires kwargs) |
| 3 | portfolio_manager | ✅ | help: list/create/get/add_holding etc. (requires kwargs) |
| 4 | quant_manager | ✅ | help: calculate_factors/factor_ic/backtest_factor (requires kwargs) |
| 5 | risk_manager | ✅ | help: calculate_var/stress_test/risk_exposure (requires kwargs) |
| 6 | sentiment_manager | ✅ | help: market_sentiment/stock_sentiment (requires kwargs) |
| 7 | vector_search_manager | ✅ | help: similar_patterns/similar_stocks (requires kwargs) |

---

## Scenario 16: 数据运维

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | sync_trading_calendar | ✅ | 242 trading dates for 2026 |
| 2 | sync_kline_data | ✅ | stock_code valid, 100 rows from timescaledb |
| 3 | batch_sync_klines | ✅ | codes (not stock_codes) valid, success=2 |
| 4 | get_sync_status | ✅ | pending=1, success=2, dead_letter=0 |
| 5 | get_cache_stats | ✅ | hit_rate 0.25, file_count 3 |
| 6 | clear_cache | ✅ | cleared 3 files |
| 7 | get_dead_letters | ✅ | count 0, path returned |
| 8 | clear_dead_letters | ✅ | removed 0 |
| 9 | data_warmup | ✅ | action=status, sync_metrics returned |
| 10 | data_sync_manager | ✅ | help: status/sync/list_tasks (requires kwargs) |

---

## Scenario 17: Skills+用户

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | list_skills | ✅ | 20 skills from codex_registry |
| 2 | search_skills | ✅ | 5 quant skills for keyword "quant" |
| 3 | run_skill | ✅ | akshare-market smoke_test completed (4 steps) |
| 4 | update_user_profile | ✅ | neuroticism 0.4, openness 0.7 recorded |
| 5 | get_user_profile | ✅ | weighted_profile, snapshot_count 5 |

---

## Scenario 18: 审计合规

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | log_recommendation_audit | ✅ | logged with user_id/action/reasoning_chain/stock_code |
| 2 | compliance_manager | ✅ | help: check_order/get_restrictions (requires kwargs) |
| 3 | user_manager | ✅ | help: get_profile/update_preferences/assess_kyc |
| 4 | alerts_manager | ✅ | help: list/create/check/update/delete (requires kwargs) |
| 5 | execution_manager | ✅ | help: twap/vwap/list/summary (requires kwargs) |

---

## Scenario 19: 语义搜索

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | semantic_stock_search | ✅ | 20 results for "新能源汽车龙头" |
| 2 | search_similar_stocks | ✅ | 10 similar to 300750 (宁德时代), 美的集团 0.55 |
| 3 | search_by_kline | ✅ | 10 K-line similar, 国药一致 0.64 |
| 4 | parse_selection_query | ✅ | parsed pb_ratio<1, suggestion for screener |
| 5 | get_industry_chain | ✅ | 半导体产业链 (semiconductor) |

---

## Scenario 20: 日终复盘+剩余Manager

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | generate_daily_report | ✅ | date 2026-03-06, 上证4124, 涨停99只 |
| 2 | portfolio_manager | ✅ | help: list/create/get/add_holding etc. |
| 3 | performance_manager | ✅ | help: calculate_metrics/attribution (requires kwargs) |
| 4 | benchmark_manager | ✅ | help: run_daily/get_report (requires kwargs) |
| 5 | risk_manager | ✅ | help: calculate_var/stress_test |
| 6 | insight_manager | ✅ | help: list/generate/daily_brief |
| 7 | industry_chain_manager | ✅ | help: get_chain/related_stocks (requires kwargs) |
| 8 | strategy_manager | ✅ | help: create/publish/list/detail etc. |

---

## Schema Notes

- **get_research_reports**: `stock_code` or `symbol` both valid.
- **batch_sync_klines**: uses `codes`, not `stock_codes`.
- **Managers (fundamental_analysis_manager, research_manager, insight_manager, comprehensive_manager, decision_manager, portfolio_manager, quant_manager, risk_manager, sentiment_manager, vector_search_manager, data_sync_manager, compliance_manager, alerts_manager, execution_manager, performance_manager, benchmark_manager, industry_chain_manager)**: require `kwargs` (use `"{}"` for help).
- **list_industry_templates**: no params.
- **data_warmup**: requires `action` (warmup/status/clear).
- **log_recommendation_audit**: user_id, action, reasoning_chain, stock_code all optional with defaults.
