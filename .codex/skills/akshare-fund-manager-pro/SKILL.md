---
name: akshare-fund-manager-pro
description: 顶级基金经理专业流程：投研、组合、执行、风控、TDX联动与日报/周报/月报模板输出的一体化闭环。
---

# 目标
把“研究结论”转成“可执行组合与可复盘报告”，并稳定打通 TDX 前端联动。

# 适用触发
- 用户要求“像顶级基金经理一样做完整流程”。
- 需要“研究-执行-风控-复盘-报告”的端到端输出。
- 需要把结果同步到 TDX 客户端并持续跟踪。

# 强制阶段流程（按顺序执行）
- 阶段 0（能力探测）：
  - 用 `list_skills`、`search_skills`、`available_tools`、`get_available_categories` 确认本轮可用能力。
  - 需要模板化自动流时，使用 `run_skill` 调用已封装技能。
- 阶段 1（数据与运行前置）：
  - 用 `sync_trading_calendar` 与 `get_trading_dates` 校验交易日。
  - 用 `batch_sync_klines` 预拉核心标的数据。
  - 用 `get_cache_stats` 检查缓存命中率，必要时 `clear_cache`。
  - 若同步异常，用 `get_dead_letters` 诊断，必要时 `clear_dead_letters` 清理后重跑。
- 阶段 2（自上而下研判）：
  - 用 `macro_manager` 和 `market_insight_manager` 做宏观与市场状态判断。
  - 用 `sector_manager`、`insight_manager`、`sentiment_manager` 判断板块与情绪。
  - 事件补充：`get_ipo_info`、`get_cb_info`、`get_industry_chain`、`industry_chain_manager`。
- 阶段 3（标的池构建）：
  - 用 `get_stock_list` 构建初始池。
  - 用 `search_stocks` / `semantic_stock_search` 做代码归一。
  - 用 `screener_manager` 做条件筛选，用 `get_stock_capital` 过滤股本结构风险。
- 阶段 4（深度研究与决策）：
  - 用 `comprehensive_manager`、`decision_manager` 输出多维结论。
  - 需要策略生命周期扫描、淘汰或批量治理时，用 `strategy_manager`。
  - 用 `fundamental_analysis_manager`、`technical_analysis_manager` 做交叉验证。
  - 用 `trading_data_manager` 与 `limit_up_manager` 补充交易行为信息。
  - 用 `should_i_buy`、`should_i_sell` 生成买卖建议草案（仅供参考，不替代风控/合规）。
- 阶段 5（组合与执行）：
  - 用 `optimize_portfolio`、`analyze_portfolio_risk`、`stress_test_portfolio` 构建组合并做风险压测。
  - 用 `risk_manager` 做 VaR/暴露复核。
  - 用 `portfolio_manager` 落地仓位。
  - 用 `compliance_manager` 做合规闸门后，交由 `execution_manager` 执行。
- 阶段 6（监控与告警）：
  - 用 `watchlist_manager`、`live_trading_manager` 建立跟踪。
  - 用 `alerts_manager` 建立规则，并用 `check_all_alerts` 做巡检。
- 阶段 7（TDX 深度联动）：
  - 前端联动按 `akshare-tdx-front-sync` 与 `../akshare-tdx-front-sync/references/scenario_templates.md` 执行。
  - 公式补充可用 `tdx_calculate_cr`、`tdx_calculate_dma`、`tdx_calculate_dmi`、`tdx_calculate_expma`、`tdx_calculate_trix`、`tdx_calculate_vr`。
  - 深度尽调可用 `tdx_get_f10_info`、`tdx_get_financial_snapshot`、`tdx_get_financial_history`、`tdx_download_data`。
- 阶段 8（仿真与外部兼容）：
  - 用 `paper_trading_manager` 做预演与成交行为检查。
  - Node 兼容行情输出可用 `get_batch_quotes_compat`。
- 阶段 9（复盘与报告）：
  - 用 `performance_manager`、`benchmark_manager`、`backtest_manager` 形成绩效复盘与基准评分。
  - 报告模板按 `references/reporting_rules.md`：
    - 日报：`assets/templates/daily_report_template.md`
    - 周报：`assets/templates/weekly_report_template.md`
    - 月报：`assets/templates/monthly_report_template.md`

# 失败与分流
- 发现器不可用：`search_skills` / `available_tools` 失败时，直接按本 skill 固定阶段执行。
- 数据预热失败：`batch_sync_klines` 失败时降级到 `get_kline_data` 按需拉取。
- 交易日历异常：`sync_trading_calendar` 失败时改用 `get_trading_dates` 最近窗口。
- 研究管理器失败：`comprehensive_manager` 或 `decision_manager` 失败时，回退到基本面 + 技术面双轨分析。
- 执行管理器失败：`execution_manager` 失败时只输出下单计划，不执行，并保留告警监控。
- 监控链路失败：`live_trading_manager` 失败时回退到 `watchlist_manager` + `alerts_manager`。
- TDX 链路失败：先走非 TDX 报告与告警链路，待客户端恢复后补发。

# 参考
- 报告规则：`references/reporting_rules.md`
- TDX 场景：`../akshare-tdx-front-sync/references/scenario_templates.md`
