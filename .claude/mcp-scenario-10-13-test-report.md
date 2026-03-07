# MCP Tools Test Report (Scenarios 10–13)

**Server:** user-akshare-stock  
**Date:** 2026-03-06

---

## Scenario 10: TDX全量指标 (stock 600519)

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | tdx_calculate_macd | ✅ | DIF/DEA/MACD 100 points, source=python_fallback |
| 2 | tdx_calculate_kdj | ✅ | K/D/J 100 points, source=python_fallback |
| 3 | tdx_calculate_rsi | ✅ | RSI1/RSI2/RSI3 100 points, source=python_fallback |
| 4 | tdx_calculate_boll | ✅ | BOLL/UB/LB 100 points, source=python_fallback |
| 5 | tdx_calculate_trix | ✅ | TRIX/MATRIX 100 points, source=python_fallback |
| 6 | tdx_calculate_dma | ✅ | DIF/AMA 100 points, source=python_fallback |
| 7 | tdx_calculate_expma | ✅ | EXPMA1/EXPMA2 100 points, source=python_fallback |
| 8 | tdx_calculate_dmi | ✅ | PDI/MDI/ADX/ADXR 100 points, source=python_fallback |
| 9 | tdx_calculate_cr | ✅ | CR/MA1–MA4 100 points, source=python_fallback |
| 10 | tdx_calculate_vr | ✅ | VR 100 points, source=python_fallback |
| 11 | tdx_calculate_indicator | ✅ | formula_name="MACD" (param: formula_name, not indicator_name) |
| 12 | tdx_get_formula_data | ✅ | 100 K-lines, Date/OHLCV/Amount, source=python_fallback |
| 13 | tdx_get_expert_signals | ✅ | ENTERLONG/EXITLONG, latest_signal sell@1466.21, formula_name (not indicator_name) |
| 14 | tdx_custom_formula_calc | ❌ | TdxQuant不可用; schema uses formula_name (no raw "formula" param) |
| 15 | tdx_screen_stocks | ✅ | 2 matched (000100, 000725), formula_name="MACD金叉" |

---

## Scenario 11: TDX前端联动

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | create_watchlist | ❌ | TdxQuant不可用; schema: block_code, block_name, stock_codes (not name) |
| 2 | add_stocks_to_watchlist | ❌ | TdxQuant不可用; schema: block_code, stock_codes (not sector_name) |
| 3 | delete_watchlist | ❌ | TdxQuant不可用; schema: block_code (not name) |
| 4 | tdx_rename_sector | ❌ | TdxQuant不可用; schema: block_code, new_name |
| 5 | tdx_clear_sector | ❌ | TdxQuant不可用; schema: block_code |
| 6 | push_message | ❌ | TdxQuant不可用; schema: message (not title+content) |
| 7 | push_warn | ❌ | TdxQuant不可用; schema: stock_code, price, reason (not title+content) |
| 8 | send_backtest_result | ❌ | TdxQuant不可用; schema: stock_code, time_list, data_list |
| 9 | send_backtest_trades | ❌ | TdxQuant不可用; schema: stock_code, trades |
| 10 | tdx_download_data | ❌ | TdxQuant不可用; schema: stock_code, date, data_type |
| 11 | tdx_send_file | ❌ | TdxQuant不可用; schema: file_path |
| 12 | get_user_sectors | ❌ | TdxQuant不可用; success=false, data=[] |
| 13 | tdx_manage_subscription | ❌ | TdxQuant不可用; schema: action, stock_codes |
| 14 | tdx_refresh_data | ❌ | TdxQuant不可用; schema: refresh_type, market, force, stock_codes, period |

---

## Scenario 12: TDX交易数据

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | tdx_list_available_fields | ✅ | gp/bk/sc fields listed (GP1–GP21, BK5–BK19, SC1–SC31) |
| 2 | tdx_get_stock_trading_data | ❌ | TdxQuant不可用; 需盘后数据包 |
| 3 | tdx_get_sector_trading_data | ❌ | 无可用BK字段 (fields需BK5/BK9等); TdxQuant不可用 |
| 4 | tdx_get_market_trading_data | ❌ | TdxQuant不可用; 需盘后数据包 |
| 5 | trading_data_manager | ✅ | help: dragon_tiger, block_trades, institutional_flow |
| 6 | data_sync_manager | ✅ | help: status, sync, get_task, list_tasks, cancel_task, schedule |

---

## Scenario 13: 策略回测

| # | Tool | Status | Key Data or Error |
|---|------|--------|-------------------|
| 1 | run_simple_backtest | ✅ | 86KB output; 600519 ma_cross, total_return, equity_curve |
| 2 | run_batch_backtest | ✅ | 2 codes (600519, 000858), avg_return -2.61%, execution 3.34s |
| 3 | run_backtest_and_send_to_tdx | ✅ | backtest success; TDX send may fail (TdxQuant不可用) |
| 4 | backtest_manager | ✅ | help: run, save, list, get, compare |
| 5 | strategy_manager | ✅ | help: create, publish, list, subscribe, rank, etc. |
| 6 | benchmark_manager | ✅ | help: run_daily, get_report |
| 7 | performance_manager | ✅ | help: calculate_metrics, backtest_metrics, attribution, benchmark_comparison |
| 8 | generate_daily_report | ✅ | date 2026-03-06, market_summary, stats, hot_sectors, capital_flow, sentiment |

---

## Schema Notes

- **tdx_calculate_indicator**: use `formula_name`, not `indicator_name`
- **tdx_get_expert_signals**: use `formula_name`, not `indicator_name`
- **tdx_custom_formula_calc**: uses `formula_name` for built-in formulas; no raw `formula` param for expressions like `C/REF(C,1)-1`
- **create_watchlist**: requires `block_code`, `block_name`, `stock_codes` (not `name`)
- **add_stocks_to_watchlist**: requires `block_code`, `stock_codes` (not `sector_name`)
- **delete_watchlist**: requires `block_code` (not `name`)
- **push_message**: requires `message` (use `"title|content"` for multi-line)
- **push_warn**: requires `stock_code`, `price`, `reason` (not title+content)
- **trading_data_manager** / **data_sync_manager** / **backtest_manager** / **benchmark_manager** / **performance_manager**: require `action` and `kwargs` (JSON string, e.g. `"{}"`)
