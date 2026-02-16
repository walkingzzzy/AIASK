# 报告输出规则（日/周/月）

## 通用规则
- 所有结论必须可追溯到工具输出，避免空泛判断。
- 统一包含：数据时间窗口、组合敞口、风险指标、异常事项、下一步动作。
- 若数据不可用，禁止使用 `-` 占位符，必须写明 `reason`。
- 报告数值字段统一包含：`value`、`unit`、`precision`、`window`（必要时补充 `basis`/`method`）。
- 默认数据源优先级：`TimescaleDB -> Tushare Pro -> AkShare`，并在 `data_limitations` 中保留降级说明。

## 日报（交易日）
- 目标：盘后快速复盘 + 次日关注清单。
- 必填字段（JSON 与 Markdown 对齐）：
  - `index_summary`：主要指数行情（含点位与涨跌幅，窗口 `T-1D ~ T`）
  - `capital_and_events`：北向资金与重大事件摘要（单位需明确）
  - `daily_return`：当日收益率（`%`）
  - `vs_benchmark`：相对基准收益（默认 `000300`，`%`）
  - `contributors_and_detractors`：主要贡献与拖累（含贡献口径）
  - `core_risk_metrics`：`max_drawdown` / `volatility` / `var` / `cvar`
  - `daily_alerts`：当日告警列表（阈值触发依据）
  - `execution_summary`：成交与执行质量摘要（若无执行数据写 reason）
  - `watchlist`：次日关注清单（建议与阈值）
- 风险指标计算规范：
  - `max_drawdown`：历史路径最大回撤（窗口默认 `T-20D ~ T`）
  - `volatility`：日收益标准差年化（`std * sqrt(252)`）
  - `var` / `cvar`：历史模拟法，默认 95% 置信度
- 情绪判断规范：
  - 必须使用量化阈值（如主要指数平均涨跌幅）给出 `bullish` / `neutral` / `bearish`。
- 建议数据源：
  - `semantic.generate_daily_report`
  - `market.quote / market.kline`
  - `news.get_market_news`
  - `alerts.check_all_alerts`
  - `performance_manager(action=calculate_metrics)`

## 周报（每周）
- 目标：评估策略有效性与执行偏差。
- 必填：
  - 周度收益、波动、回撤、换手
  - 行业/风格暴露变化
  - 执行质量（成交偏差、滑点、成本）
  - 下周调仓计划与风控参数
- 建议数据源：
  - `performance_manager(action=benchmark_comparison)`
  - `risk_manager(action=risk_exposure)`
  - `execution_manager(action=summary)`

## 月报（每月）
- 目标：归因、复盘、制度化改进。
- 必填：
  - 月度绩效与基准对比
  - 归因拆解（行业、因子、个股）
  - 压力测试与极端情景结论
  - 下月策略调整、仓位计划、风险预算
- 建议数据源：
  - `performance_manager(action=attribution)`
  - `risk_manager(action=stress_test)`
  - `backtest_manager(action=compare)`
