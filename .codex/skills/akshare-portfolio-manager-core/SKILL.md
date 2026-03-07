---
name: akshare-portfolio-manager-core
description: 顶级基金经理核心流程：目标与约束、组合构建、执行、风险与绩效闭环。
---

# 目标
把“投研-组合-合规-执行-监控-复盘”串成可执行闭环，避免只给分析不落地。

# 强制阶段流程（必须按顺序执行）
- 阶段 0（账户与偏好）：
  - 用 `user_manager(action=get_profile)`、`get_user_profile` 获取风险偏好与投资者画像。
  - 用 `update_user_profile` 写入或更新画像快照。
  - 若无历史配置，先落地 IPS 关键字段（目标收益、最大回撤、流动性约束）。
- 阶段 1（研究与事件）：
  - 候选池先用 `search_stocks` 或 `semantic_stock_search` 归一化代码。
  - 用 `research_manager(action=get_reports)` 获取研报摘要。
  - 用 `event_manager(action=upcoming_events)` 检查未来催化与风险事件。
- 阶段 2（组合构建）：
  - 用 `optimize_portfolio` 生成目标权重。
  - 用 `analyze_portfolio_risk`、`analyze_portfolio_risk_barra` 与 `stress_test_portfolio` 做事前风险评估。
- 阶段 3（合规闸门）：
  - 用 `compliance_manager(action=check_order)` 做拟下单合规检查。
  - 输出建议前用 `log_recommendation_audit` 记录推荐审计日志。
  - 不通过则回到阶段 2 调整权重/仓位规模。
- 阶段 4（执行计划）：
  - 大额单优先 `execution_manager(action=twap|vwap)`，小额单可直接执行。
  - 记录执行参数（总量、时长、切片）用于复盘。
- 阶段 5（落地与监控）：
  - 用 `portfolio_manager(action=create)` 创建组合。
  - 用 `portfolio_manager(action=add_holding)` 记录持仓。
  - 用 `watchlist_manager(action=add)` 与 `live_trading_manager(action=monitor)` 建立盘中跟踪。
  - 用 `alerts_manager(action=create)` 建立风控告警。
- 阶段 6（复盘闭环）：
  - 用 `risk_manager(action=calculate_var|stress_test)` 做事后风险复盘。
  - 用 `performance_manager(action=calculate_metrics|benchmark_comparison)` 输出绩效与基准对比。
  - 用 `benchmark_manager(action=run_daily|get_report)` 输出统一评分与历史报告快照。
  - 必要时用 `data_sync_manager(action=status|sync)` + `get_sync_status` 做数据一致性检查。

# 失败与兜底
- 目标不清晰：先输出目标问卷与示例区间，不进入建仓阶段。
- 研究数据不足：`research_manager` 失败时改用 `get_stock_news` + `get_market_news`。
- 事件日历不可用：`event_manager` 失败时改用 `get_stock_notices`。
- 合规检查不可用：`compliance_manager` 失败时暂停自动执行，仅输出待人工复核订单草案。
- 执行引擎不可用：`execution_manager` 失败时降级为分批手工执行，并缩小单笔规模。
- 实盘监控不可用：`live_trading_manager` 失败时改用 `watchlist_manager` + `alerts_manager` 维持最小监控。
- 数据链路异常：`data_sync_manager` 失败时用 `data_warmup` 或 `sync_kline_data` 补齐关键数据。

# 参考
- 管理器工具：`user_manager`、`research_manager`、`event_manager`、`portfolio_manager`、`compliance_manager`、`execution_manager`、`watchlist_manager`、`live_trading_manager`、`alerts_manager`、`risk_manager`、`performance_manager`、`benchmark_manager`、`data_sync_manager`。
- 配套原子工具：`get_user_profile`、`update_user_profile`、`log_recommendation_audit`、`analyze_portfolio_risk_barra`。
