# MCP 价值挖掘与价值分析优化方案

- 文档版本：v1.0
- 编制日期：2026-02-16
- 适用范围：`C:\Users\1\Desktop\股票`
- 目标系统：`packages/akshare-mcp`

## 1. 目标

在现有 MCP 服务基础上，完成“可研究、可执行、可风控、可复盘”的价值挖掘与价值分析能力升级，重点解决以下问题：

1. 因子库“声明支持”与“实际可计算”不一致。
2. 因子回测成本与可交易性约束不足，结果可执行性弱。
3. 推荐与组合建议的候选池过窄，覆盖不足。
4. 压力测试与估值分布化能力不够，风险区间表达不足。

## 2. 当前缺口（已验证）

1. `calculate_factor` 对 `trend/reversal/growth/size` 计算失败，和因子库声明不一致。
2. `backtest_factor` 的回撤为代理值（非完整路径回撤），且未接入真实交易成本链路。
3. 可交易性过滤默认关闭，涨跌停处理为保守简化规则。
4. `decision_manager(action="recommend")` 使用固定示例股票池，非全市场筛选。
5. 风险模块场景为静态 shock，缺少路径化联动与更真实的尾部建模。
6. 估值模块缺少参数分布与估值区间输出（目前以点估值/三情景为主）。

## 3. 总体实施策略

1. 先修复一致性（P0），再扩展深度（P1），最后提升研究效率（P2）。
2. 先 manager 后原子工具，保持对外协议兼容，避免破坏现有调用方。
3. 每项改造必须包含：单测、回归测试、性能门槛、回退开关。
4. 不做模拟交付，所有能力进入真实代码路径并可由 MCP 工具直接调用。

## 4. 分阶段方案

## 4.1 P0（必须优先，1-2 周）

### P0-1 因子实现一致性修复

- 目标：让 `SUPPORTED_FACTORS` 中公开因子均可被 `calculate_factor/factor_ic/backtest_factor` 真实计算。
- 代码范围：
  - `packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/factor_calculator.py`
- 实施项：
  1. 补齐 `trend/reversal/growth/size` 在 `_calculate_factor_value` 的计算分支。
  2. 统一 financial 字段映射（如 `market_cap/total_mv/circ_mv`、`revenue_growth/profit_growth`）。
  3. 对缺失数据返回结构化错误原因，不再仅返回 `Failed to calculate factor`。
- 验收标准：
  1. `get_factor_library` 中状态为 `supported` 的因子，`calculate_factor` 成功率 >= 95%（在具备数据前提下）。
  2. 新增单测覆盖 8 个因子最小可用路径。

### P0-2 因子回测可执行性增强

- 目标：把因子回测从“统计展示”升级为“可执行评估”。
- 代码范围：
  - `packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/backtest.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/slippage.py`
- 实施项：
  1. 在分组回测中引入路径净值与真实 `max_drawdown` 计算。
  2. 接入 `commission/slippage/slippage_model/tradability_filter` 参数，支持从 `backtest_factor` 透传。
  3. 输出成交约束统计：不可交易比例、有效成交比例、平均冲击成本。
- 验收标准：
  1. `backtest_factor` 返回真实净值路径和非代理回撤。
  2. 成本参数变化能显著影响回测结果（有测试断言）。

### P0-3 推荐引擎候选池扩展

- 目标：从固定样本推荐改为可配置股票池筛选。
- 代码范围：
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/decision_manager.py`
- 实施项：
  1. 用 `codes` 参数优先，缺省时从 `get_stock_list` + 条件过滤构建池。
  2. 支持 `universe_limit/sector_filter/liquidity_filter`。
  3. 返回推荐时附数据覆盖率与过滤链路。
- 验收标准：
  1. `recommend(limit=50)` 可返回 > 5 条候选（数据可用时）。
  2. 不再出现硬编码样本池行为。

### P0-4 风险压力测试增强（第一阶段）

- 目标：在现有静态场景上加入可解释分层和组合联动约束。
- 代码范围：
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/risk_manager.py`
- 实施项：
  1. 支持自定义场景参数（市场、波动、流动性惩罚）。
  2. 输出场景分层损失拆解（市场/波动/流动性）的一致口径。
  3. 为 `portfolio_id` 与 `codes+weights` 双路径统一结果结构。
- 验收标准：
  1. 压测结果可复现（同参数、同数据一致）。
  2. 输出字段稳定，便于前端与报告消费。

## 4.2 P1（重要增强，2-4 周）

### P1-1 估值区间化（分布而非点估）

- 代码范围：`packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- 实施项：
  1. 新增 DCF 参数分布抽样（增长率、利润率、WACC、终值增长率）与置信区间输出。
  2. 支持 `p10/p50/p90` 与估值区间宽度风险提示。
  3. 保持现有 `dcf_valuation/scenario_dcf_valuation` 协议兼容。
- 验收标准：
  1. 返回点估值 + 区间估值并附样本数与假设分布。
  2. 单测验证边界参数与稳定性。

### P1-2 相对估值可比集优化

- 代码范围：`packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
- 实施项：
  1. 加入成长、盈利质量、现金流口径一致性过滤。
  2. 输出可比集构建日志（筛选前后数量、放宽策略）。
  3. 增加行业中位数偏离风险标记。
- 验收标准：
  1. `relative_valuation` 返回 `peer_pool_build` 的完整过程信息。
  2. 可比集不足时有明确降级说明。

### P1-3 绩效披露增强

- 代码范围：`packages/akshare-mcp/src/akshare_mcp/tools/managers/performance_manager.py`
- 实施项：
  1. 补充费用口径字段（手续费、滑点、冲击假设）。
  2. 增加 rolling 指标（rolling sharpe / rolling drawdown）。
  3. 归因结果与 benchmark 对齐同一数据窗口。
- 验收标准：
  1. 报告端可直接消费，无需二次补算。
  2. 时间窗口、费用口径可审计可追溯。

## 4.3 P2（研究效率提升，持续迭代）

1. 另类因子从关键词规则升级为可解释文本信号管线（保留降级路径）。
2. 因子研究加入更严格稳健性检验（多窗口、参数敏感性、样本切换）。
3. 引入实验注册标准模板，统一 artifact 元数据字段。

## 5. 交付顺序与里程碑

1. 里程碑 M1（P0-1/P0-2）：因子可算 + 回测可执行。
2. 里程碑 M2（P0-3/P0-4）：推荐与风险模块可用于组合决策。
3. 里程碑 M3（P1 全部）：估值区间化 + 可比集增强 + 绩效披露升级。

## 6. 验收与测试清单

1. 单元测试：
   - 因子计算分支覆盖（8 因子）。
   - 回测成本与可交易性参数影响断言。
   - 估值区间输出稳定性和边界参数断言。
2. 集成测试：
   - `quant_manager -> backtest_manager -> performance_manager` 全链路。
   - `decision_manager -> compliance_manager -> execution_manager` 门禁链路。
3. 回归测试：
   - 现有接口字段不破坏。
   - 旧调用参数继续可用。

## 7. 风险与回退

1. 风险：新参数增多导致调用复杂度上升。
   - 回退：保持默认参数与兼容路径，文档化 `kwargs` 示例。
2. 风险：性能波动（尤其 OOS 与分布估值）。
   - 回退：引入 `fast_mode` / `full_mode`。
3. 风险：数据缺失导致结果不稳定。
   - 回退：统一 `source_chain + data_quality + fallback_reason` 输出。

## 8. 立即执行建议（本周）

1. 先落地 P0-1：修复 4 个失效因子分支并补单测。
2. 再落地 P0-2：给 `backtest_factor` 接入真实成本与回撤路径。
3. 最后落地 P0-3：替换硬编码推荐池，打通全市场候选链路。

