# 报告输出规则（日/周/月）

## 通用规则
- 所有结论必须可追溯到工具输出，避免空泛判断。
- 统一包含：数据时间窗口、组合敞口、风险指标、异常事项、下一步动作。
- 若有不可用数据，必须在“数据限制”中明确说明。

## 日报（交易日）
- 目标：盘后快速复盘 + 次日关注清单。
- 必填：
  - 市场概览（指数、涨跌结构、情绪）
  - 组合当日收益与主要贡献
  - 风险事件与告警状态
  - 次日重点观察标的与阈值
- 建议数据源：
  - `market_insight_manager`
  - `sentiment_manager`
  - `check_all_alerts`
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
