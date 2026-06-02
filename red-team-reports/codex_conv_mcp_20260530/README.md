# AIASK AKShare MCP 红队复测 v3 · 对话式 48 场景全量深测

- **Run ID**: `codex_conv_mcp_20260530`
- **方法**: 对话式真实工具调用（Kiro + sequential-thinking 协调），非脚本回放
- **基准时间**: 2026-05-30 周六 Asia/Shanghai（非交易时段 / 周末休市）
- **目标日**: 2026-05-29（最近交易日）/ 2026-05-30（当日）
- **基线锚点**（开场实测）:
  - 工具基线: **163**（`available_tools.count=163`，`fallback_used=false`）
  - 分类基线: **33**（`get_available_categories=33`）
- **user_id**: `redteam_conv_20260530`
- **资金**: 100 万 / 组合
- **护栏**:
  - `live_trading_manager` 全部 `dry_run` / 不带 `confirm_token`，绝不传真实令牌
  - 不调用破坏性工具（`clear_cache` / `clear_dead_letters`）除非在隔离验证路径且显式说明
  - paper-trading / 组合 / 自选 / 告警 一律使用隔离 user_id，建后即查不污染主数据

## 与历史 run 的差异

| 维度 | v1 (20260522) | v2 (20260526) | **v3 本次 (20260530)** |
|---|---|---|---|
| 方法 | 对话式 | 对话式 | 对话式（+thinking 协调） |
| 场景数 | 22 | 22 | **48** |
| 每场景工具调用 | 3-5 | 3-5 | **≥30** |
| 目标总调用 | ~97 | ~97 | **≥1440** |
| 工具去重覆盖 | ~80 | ~80 | **163/163 全覆盖目标** |

## 判定规则（沿用 v2）

- **Pass**: `success=true`，`fallback_used=false` 或 fallback_chain 完整，数据合理
- **Degraded**: `success=true`，`fallback_used=true` 或 `quality_flags` 含 stale/partial，但 `source_chain` 显式
- **Fail-graceful**: `success=false`，但 `error_code` 显式 + `degraded=true`（正确错误路径）
- **Fail-schema**: schema 异常 / 异常抛栈 / 护栏绕过（**唯一真正的 bug 等级**）

## 48 场景规划（每场景 ≥30 次真实工具调用）

| # | 场景 | 主题 |
|---|---|---|
| N01 | 工具发现与契约审计 | available_tools / contracts / skills / search |
| N02 | 个股全景行情链 | 单股 quote/kline/orderbook/盘口全维度 |
| N03 | 多股批量行情对比 | batch_quotes / 多标的横向 |
| N04 | 技术分析全指标 | MA/EMA/RSI/MACD/KDJ/BOLL/ATR + 形态 |
| N05 | K线形态与相似形态检索 | patterns / similar / vector |
| N06 | 财务基本面深挖 | financials / 杜邦 / 估值指标 |
| N07 | 估值多方法 consensus | DCF/DDM/相对/consensus |
| N08 | DCF 情景与敏感性 | scenario_dcf / 行业模板 / 历史估值 |
| N09 | 资金流全维度 | 个股/板块/概念/北向 |
| N10 | 北向与龙虎榜与大宗 | north_fund / dragon_tiger / block_trades |
| N11 | 新闻公告研报聚合 | news / notices / research / 盈利预测 |
| N12 | 情绪三件套 | stock/market/sector sentiment + 恐贪 |
| N13 | 因子库与单因子 | factor_library / calculate_factor / profile |
| N14 | 因子 IC 与 OOS 验证 | factor_ic / validate_oos |
| N15 | 因子稳健性与回测 | robustness / backtest_factor |
| N16 | 单股回测与绩效 | run_simple_backtest / performance |
| N17 | 批量回测 | run_batch_backtest / benchmark |
| N18 | 组合优化 | optimize_portfolio 多方法 |
| N19 | 组合风险与压力测试 | analyze_risk / stress_test |
| N20 | Barra 风险分解 | analyze_portfolio_risk_barra |
| N21 | 决策门控与融合 | run_decision_gate / fuse / build_*context |
| N22 | should_i_buy / sell | 决策单点 + 多 style |
| N23 | 统一决策 summary/details | get_unified_decision* |
| N24 | 期权希腊字母链 | options_manager greeks/iv/price |
| N25 | 可转债与新股 | cb_info / ipo / capital |
| N26 | 板块与产业链 | sector_manager / industry_chain |
| N27 | 选股器与语义搜索 | screener / parse_selection / semantic |
| N28 | 向量相似检索 | search_by_kline / similar_stocks / vector |
| N29 | 宏观指标 | macro_manager / get_macro_indicator |
| N30 | 市场情绪上下文与恐贪 | market_sentiment_context / fear_greed |
| N31 | 涨停板与每日报告 | limit_up / generate_daily_report |
| N32 | 自选股 CRUD | watchlist_manager 全 action |
| N33 | 告警 CRUD | alerts_manager / create_*_alert / check |
| N34 | 模拟交易全流程 | paper_trading_manager 全 action |
| N35 | 实盘 dry_run 护栏 | live_trading_manager dry_run |
| N36 | 合规检查 | compliance_manager 全 action |
| N37 | 用户画像与 KYC | user_manager / user_profile |
| N38 | 数据同步与新鲜度 | data_sync / check_db_freshness / sync |
| N39 | 缓存与 dead-letter | cache_stats / sync_status / dead_letters |
| N40 | AI 工作流-个股深度 | analyze_stock_(product_)workflow |
| N41 | AI 工作流-因子候选 | factor_candidate_workflow |
| N42 | AI 工作流-策略复核 | strategy_review_workflow |
| N43 | AI 工作流-预测诊断/数据质量 | prediction_diagnosis / data_quality |
| N44 | 策略超市生命周期 | strategy_manager 全 action |
| N45 | 技能系统 | list/search/run_skill |
| N46 | 交易计划与关键价位 | generate_trade_plan / key_levels / stop |
| N47 | 条件收益与信号命中率 | conditional_returns / signal_hit_rate |
| N48 | 全工具回归收尾 | 163 工具回归 + 跨场景一致性 |

## 目录

- `sNN/` — 每场景一个目录，内含 `status.json`（逐工具判定）+ `summary.md`（人读摘要）
- `final/` — 收尾生成 `coverage_matrix_v3.md` + `findings_v3.md` + `delta_v2_v3.md`

## 状态

**已完成** — 48/48 场景全部完成，**1471** 次真实工具调用（精确汇总），final 报告已生成。

- 完成时间: 2026-05-30T20:10+08:00
- 总 finding 条目: **211**（HIGH 57 / MEDIUM 76 / LOW 78，逐场景计数；含 3 系统级根因的多场景复现）
- Fail-schema 工具行: **106**
- findings_v3.md: 全量发现汇总（3系统级根因 + 逐场景 finding 聚类）
- coverage_matrix_v3.md: 33分类覆盖矩阵（Fail-schema 列为近似归类）
- delta_v2_v3.md: 与 v2 (20260526) 差异对比
