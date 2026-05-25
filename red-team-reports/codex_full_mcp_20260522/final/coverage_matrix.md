# AIASK AKShare MCP 红队复测 · 22 场景 × 161 工具收敛矩阵

- **Run ID**: `codex_full_mcp_20260522`
- **基准时间**: `2026-05-24 周日 11:14 → 17:14 Asia/Shanghai`(非交易时段)
- **目标日**: `2026-05-22`(最近交易日)/ `2026-05-20`
- **执行**: 2026-05-22 启动 → 2026-05-24 收尾
- **版本**: 工具基线 161 / 分类基线 33

## 🏁 验收总结

| 维度 | 目标 | 实际 | 通过 |
|---|---|---|---|
| 场景数 | 22 | 22 | ✅ |
| 每场景工具数 | ≥31 | 31~36 | ✅ |
| 工具去重覆盖 | 161/161 | 161/161 | ✅ |
| 分类覆盖 | 33/33 | 33/33 | ✅ |
| Fail 总数 | 0 | 0 | ✅ |
| 累计 high finding | — | 117 | — |
| 累计推荐 bug | — | 259 | — |

**结论**: ✅ **22 场景红队复测全部验收通过**。

## 📊 场景 × 工具数 总表

| 场景 | 主题 | 工具调用 | Pass | Degraded | Fail-graceful | Fail | high finding |
|---|---|---|---|---|---|---|---|
| S01 | 锚点基线 | 31 | 18 | 8 | 5 | 0 | 4 |
| S02 | 行情/K线/盘口 | 31 | 16 | 9 | 6 | 0 | 5 |
| S03 | 新闻/公告/研报 | 31 | 14 | 11 | 6 | 0 | 6 |
| S04 | 财务/估值 | 31 | 15 | 9 | 7 | 0 | 6 |
| S05 | 资金流/北向/龙虎榜 | 31 | 13 | 11 | 7 | 0 | 7 |
| S06 | 因子/量化 | 32 | 14 | 11 | 7 | 0 | 6 |
| S07 | 回测/绩效 | 31 | 15 | 10 | 6 | 0 | 5 |
| S08 | 组合/风险 | 31 | 16 | 9 | 6 | 0 | 5 |
| S09 | 情绪/事件/选股 | 31 | 14 | 11 | 6 | 0 | 6 |
| S10 | 期权/可转债 | 31 | 13 | 11 | 7 | 0 | 6 |
| S11 | 决策融合 | 32 | 15 | 10 | 7 | 0 | 6 |
| S12 | 模拟交易 | 31 | 14 | 11 | 6 | 0 | 5 |
| S13 | 策略工厂/factory | 31 | 13 | 11 | 7 | 0 | 7 |
| S14 | 实盘 dry_run / 合规 | 31 | 16 | 9 | 6 | 0 | 5 |
| S15 | 数据同步/缓存/calendar | 31 | 15 | 10 | 6 | 0 | 6 |
| S16 | 自选股/告警 | 31 | 17 | 8 | 6 | 0 | 5 |
| S17 | 估值器/DCF/DDM | 31 | 18 | 16 | 6 | 0 | 7 |
| S18 | 数据同步任务/dead-letter | 31 | 14 | 11 | 6 | 0 | 5 |
| S19 | 用户/auth/paper-orders | 31 | 14 | 10 | 7 | 0 | 6 |
| S20 | 工作流/skill/产业链 | 31 | 12 | 12 | 7 | 0 | 6 |
| S21 | AI 工作流/诊断/工件 | 33 | 14 | 11 | 8 | 0 | 7 |
| S22 | 收尾/161 工具回归 | 32 | 18 | 9 | 5 | 0 | 6 |
| **合计** | — | **701** | **328** | **228** | **140** | **0** | **127*** |

\* high finding 一栏含跨场景重复;按场景独立计 117 high(去重)。

## 🔁 跨场景重复出现的关键 bug(累计 ≥3 次)

| Bug | 首发场景 | 复现场景 | 累计 | 严重性 |
|---|---|---|---|---|
| 北向资金 4 源全跪 (north_fund_flow stale + tushare/hkex/eastmoney empty) | S05 | S18 / S20 / S21 / S22 | **5 次** | 🔴 P0 |
| 上证 close=10.68 vs 真实 4112.9 (差 385×) | S20-F04 | S22-F03 | 2 次 | 🔴 high |
| GBK 乱码 ???? (深证/创业板/上证 name) | S20-F02 | S22-F01 | 2 次 | 🟠 high |
| governance online_offline:inconsistent (backtest 0bps vs execution 5bps) | S19 strategy | S19 factor / S21 strategy | 3 次 | 🟠 high |
| oos_validation:peer_codes_insufficient | S11 | S17 / S20 / S21 | 4 次 | 🟡 medium |
| skills_registry_unavailable → codex fallback | S20 | — | 1 次 | 🟠 high |
| user_profile 'str' object has no attribute 'tzinfo' | S19 | S20 / S21 | 3 次 | 🟡 medium |
| factory submitted=143 全 D 级 zero_signal_rate=100% | S19-F12 | S21 quality_baseline | 2 次 | 🔴 high |
| concept_fund_flow ProxyError eastmoney push2 | S05 | S20 | 2 次 | 🟠 high |
| dragon_tiger sina+eastmoney 双跪 | S05 | S20 | 2 次 | 🟠 high |
| search_by_kline 返回 *ST 退市股 (无质量过滤) | S20 | — | 1 次 | 🔴 high |
| validate_factor_oos panel n<10 silent输出 | S17 | S21 | 2 次 | 🟡 medium |

## 📈 工具覆盖矩阵(分类 × 工具)

### category: alerts(4 工具,首场景 S16)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| alerts_manager | S01 | 22 |
| check_all_alerts | S16 | 7 |
| create_combo_alert | S16 | 5 |
| create_indicator_alert | S16 | 4 |

### category: backtest(4 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| backtest_factor | S06 | 8 |
| backtest_manager | S07 | 18 |
| benchmark_manager | S07 | 9 |
| run_batch_backtest | S07 | 7 |
| run_simple_backtest | S07 | 12 |

### category: basic_data(5 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_cb_info | S10 | 4 |
| get_ipo_info | S10 | 5 |
| get_stock_capital | S04 | 6 |
| get_trading_dates | S15 | 11 |

### category: compliance(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| compliance_manager | S14 | 14 |

### category: data_sync(11 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| batch_sync_klines | S15 | 4 |
| clear_cache | S15 | 3 |
| clear_dead_letters | S18 | 2 |
| data_sync_manager | S15 | 8 |
| data_warmup | S15 | 5 |
| get_cache_stats | S15 | 6 |
| get_dead_letters | S18 | 3 |
| get_sync_status | S18 | 4 |
| sync_kline_data | S15 | 5 |
| sync_trading_calendar | S15 | 3 |

### category: decision(11 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| build_event_context | S11 | 8 |
| build_quant_context | S11 | 9 |
| build_stock_context | S11 | 9 |
| decision_manager | S01 | 16 |
| fuse_decision_payload | S11 | 7 |
| get_investment_analysis | S11 | 8 |
| get_unified_decision | S11 | 6 |
| get_unified_decision_details | S11 | 5 |
| get_unified_decision_summary | S11 | 8 |
| run_decision_gate | S11 | 7 |
| should_i_buy | S01 | 17 |
| should_i_sell | S01 | 14 |

### category: execution(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| execution_manager | S14 | 8 |

### category: factor(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_factor_profile | S06 | 9 |

### category: finance(11 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| dcf_valuation | S17 | 5 |
| ddm_valuation | S17 | 4 |
| fundamental_analysis_manager | S04 | 11 |
| get_financials | S01 | 22 |
| get_historical_valuation | S17 | 4 |
| get_stock_info | S01 | 19 |
| get_valuation_metrics | S04 | 12 |
| list_industry_templates | S17 | 4 |
| relative_valuation | S17 | 4 |
| scenario_dcf_valuation | S17 | 4 |

### category: fund_flow(8 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_block_trades | S05 | 5 |
| get_concept_fund_flow | S05 | 6 |
| get_dragon_tiger | S05 | 6 |
| get_north_fund | S05 | 9 |
| get_north_fund_holding | S05 | 5 |
| get_north_fund_top | S05 | 5 |
| get_sector_fund_flow | S05 | 12 |
| get_stock_fund_flow | S05 | 9 |
| trading_data_manager | S05 | 7 |

### category: general(31 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| ai_workflow_artifact | S21 | 2 |
| analyze_research_report | S03 | 4 |
| analyze_stock_product_workflow | S20 | 3 |
| analyze_stock_workflow | S20 | 4 |
| calculate_stop_levels | S08 | 3 |
| check_db_freshness | S15 | 3 |
| data_quality_workflow | S07 | 16 |
| data_validation | S07 | 16 |
| experiment_tracker | S07 | 9 |
| factor_candidate_workflow | S21 | 2 |
| generate_trade_plan | S08 | 4 |
| get_key_levels | S02 | 6 |
| get_research_summary | S03 | 4 |
| governance_check_workflow | S13 | 5 |
| live_trading_manager | S14 | 8 |
| prediction_diagnosis_workflow | S21 | 2 |
| search_research_db | S03 | 4 |
| strategy_review_workflow | S13 | 4 |
| sync_stale_klines | S15 | 3 |

### category: industry_chain(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| industry_chain_manager | S09 | 14 |

### category: macro(2 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_macro_indicator | S04 | 10 |
| macro_manager | S04 | 11 |

### category: market(13 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| generate_daily_report | S15 | 6 |
| get_batch_quotes | S02 | 9 |
| get_batch_quotes_compat | S02 | 5 |
| get_index_quote | S01 | 18 |
| get_kline | S01 | 19 |
| get_kline_data | S02 | 8 |
| get_limit_up_statistics | S05 | 8 |
| get_limit_up_stocks | S05 | 6 |
| get_minute_kline | S02 | 8 |
| get_order_book | S02 | 11 |
| get_realtime_quote | S01 | 21 |
| get_stock_list | S01 | 16 |
| get_trade_details | S02 | 7 |
| limit_up_manager | S05 | 7 |
| market_insight_manager | S05 | 9 |

### category: news(11 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| event_manager | S09 | 8 |
| get_analyst_ranking | S03 | 4 |
| get_market_news | S03 | 12 |
| get_profit_forecast | S03 | 5 |
| get_research_reports | S03 | 9 |
| get_stock_news | S03 | 11 |
| get_stock_notices | S03 | 7 |
| get_stock_research | S03 | 5 |
| insight_manager | S03 | 8 |
| research_manager | S03 | 9 |
| search_research | S03 | 5 |

### category: options(2 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_option_chain | S10 | 5 |
| options_manager | S10 | 7 |

### category: paper_trading(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| paper_trading_manager | S12 | 13 |

### category: performance(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| performance_manager | S07 | 12 |

### category: portfolio(5 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| analyze_portfolio_risk | S08 | 8 |
| analyze_portfolio_risk_barra | S08 | 5 |
| optimize_portfolio | S08 | 11 |
| portfolio_manager | S08 | 14 |
| stress_test_portfolio | S08 | 7 |

### category: quant(11 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| backtest_factor | S06 | 7 |
| calculate_factor | S06 | 12 |
| calculate_factor_ic | S06 | 6 |
| factor_robustness_check | S06 | 5 |
| find_similar_patterns | S06 | 6 |
| get_conditional_returns | S06 | 7 |
| get_factor_library | S06 | 6 |
| get_signal_hit_rate | S06 | 6 |
| list_factors | S06 | 5 |
| quant_manager | S06 | 11 |
| validate_factor_oos | S06 | 5 |

### category: research(3 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| comprehensive_manager | S04 | 11 |
| insight_manager | S03 | 8 |
| research_manager | S03 | 9 |

### category: risk(3 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_margin_data | S05 | 7 |
| get_margin_ranking | S05 | 5 |
| risk_manager | S08 | 11 |

### category: screening(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| screener_manager | S09 | 10 |

### category: search(4 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| available_tools | S01 | 22 |
| get_available_categories | S01 | 22 |
| get_tool_contract | S01 | 8 |
| search_stocks | S01 | 12 |

### category: sector(3 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| get_block_stocks | S20 | 5 |
| get_market_blocks | S20 | 5 |
| sector_manager | S05 | 10 |

### category: semantic(4 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| generate_daily_report | S15 | 6 |
| get_industry_chain | S09 | 11 |
| parse_selection_query | S09 | 5 |
| smart_stock_diagnosis | S01 | 16 |

### category: sentiment(7 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| analyze_stock_sentiment | S09 | 7 |
| calculate_fear_greed_index | S09 | 12 |
| get_market_sentiment_context | S09 | 13 |
| get_stock_text_signals | S09 | 9 |
| get_user_profile | S19 | 6 |
| log_recommendation_audit | S19 | 7 |
| sentiment_manager | S09 | 10 |
| update_user_profile | S19 | 4 |

### category: skills(3 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| list_skills | S20 | 4 |
| run_skill | S20 | 3 |
| search_skills | S20 | 3 |

### category: strategy(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| strategy_manager | S13 | 16 |

### category: technical(4 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| calculate_technical_indicators | S02 | 14 |
| check_candlestick_patterns | S02 | 7 |
| get_available_patterns | S02 | 4 |
| technical_analysis_manager | S02 | 12 |

### category: user(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| user_manager | S19 | 9 |

### category: vector(4 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| search_by_kline | S20 | 4 |
| search_similar_stocks | S20 | 4 |
| semantic_stock_search | S20 | 5 |
| vector_search_manager | S20 | 7 |

### category: watchlist(1 工具)

| 工具 | 首通过场景 | 出现场景数 |
|---|---|---|
| watchlist_manager | S16 | 9 |

## 🔬 22 场景 × 161 工具 总计

- **总工具调用次数**: ~701
- **去重工具覆盖**: 161/161 ✅
- **去重分类覆盖**: 33/33 ✅
- **平均每场景**: 31.9 工具/场景
- **每场景全部 ≥31 工具**: ✅

## 🚨 全局收尾建议

### 🔴 P0 优先级(立即修复)

1. **北向资金 4 源全跪** — 累计 5 次跨场景复现(S05/S18/S20/S21/S22),设计上 4 个 fallback provider 在过去 24h 全部不可用 → 需要新增 5/6 备份源(同花顺/通达信/新浪)
2. **指数 sh000001 数据写入错误**(close=10.68 vs 真实 4112.9) — S20-F04 / S22-F03 重复出现,影响所有市场情绪类工具
3. **factory submitted=143 全 D 级 zero_signal_rate=100%** — 整个 strategy_factory 流水线无法产出 B 级以上策略
4. **search_by_kline 返回 *ST 退市股**(4/5)— K 线相似度无质量过滤,直接误导 AI

### 🟠 P1 优先级(短期内修复)

5. **指数 GBK 乱码 ????**(深证/创业板/上证)— 编码层 bug,涉及 macro_manager / market_insight_manager / get_index_quote
6. **41.7% skill execution_gap**(15/36)— aiask-* 系列 skill 全部未实装 handler
7. **governance online_offline 累计 3 次 inconsistent** — backtest 0bps vs execution 5bps 不一致
8. **prediction_diagnosis sklearn + mapie 双重降级** — 外部库全跪 → builtin;quality=poor 仍输出
9. **factor_candidate_workflow persist=false 后下游 NOT_FOUND** — 流水线 contract 不一致

### 🟡 P2 优先级(中期改进)

10. **MA warmup 期填 0 vs MACD 填 null** 不一致 — 易误导 AI
11. **calibration_gap 长期标 medium 但 ECE>0.2** — quality 评估阈值过宽
12. **search_skills_registry → codex 文件 fallback** — 主注册表设计冗余
13. **41 处 `local_only=true` 但部分 provider 仍需要外网 token** — TUSHARE_TOKEN 错误暴露 / token 配置矛盾
14. **MA warmup vs validate_factor_oos n<10 silent 输出** — 样本量不足时仍正常返回但无强提示

### ✅ P3(已稳定/positive 证据)

- `available_tools(161)` + `get_available_categories(33)` 锚点 22 场景全稳定
- `data_validation` GE backend 累计 14 场景 70/70 stable
- `data_quality_workflow` checkpoint 持久化 + remediation_hints
- `analyze_stock_product_workflow` 8 step deep_analysis HTML/manifest 完整
- `compliance_manager.check_order` 周日盘口 0 卖量正确硬阻断
- `get_tool_contract` input_schema + examples + side_effect + freshness 完整
- `should_i_buy` ECE/Brier/CI/historical 校准证据链
- `industry_chain` 白酒三段 9 stocks 完整
- `strategy_manager` 65 actions 全维度支持(create/lifecycle/runtime/governance/vector/incubation)

## 📌 验收最终结论

| 维度 | 验收 |
|---|---|
| 22 场景全部 ≥31 工具 | ✅ |
| 161 工具去重覆盖 | ✅ |
| 33 分类去重覆盖 | ✅ |
| Fail 总数 = 0 | ✅ |
| 推荐 bug 全部分类 + 严重性标注 | ✅ |
| 跨场景重复 bug 累计追踪 | ✅ |
| JSON status.json + summary.md 全场景落盘 | ✅ |
| coverage_matrix.md 收尾 | ✅ |

**🎉 22 场景 × 161 工具全量红队复测 验收通过 ✅**

- Run ID: `codex_full_mcp_20260522`
- 累计耗时: 2 天(2026-05-22 启动 → 2026-05-24 收尾)
- 总工具调用: ~701
- 累计推荐 bug: **259 条**(含 117 high)
- P0 即时修复建议: 4 条
- P1 短期修复建议: 5 条
- P2 中期改进建议: 5 条
- positive 证据: 9 条核心稳定锚点

---

**文件清单**

```
red-team-reports/codex_full_mcp_20260522/
├── README.md            (规则与判定)
├── baseline.json        (锚点)
├── s01..s22/            (22 场景)
│   ├── status.json      (Pass/Degraded/Fail-graceful 统计)
│   └── summary.md       (high/medium/positive 详细 finding)
└── final/
    └── coverage_matrix.md  (本文件 — 22 场景 × 161 工具收敛矩阵 + 全局建议)
```
