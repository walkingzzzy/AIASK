---
name: akshare-trading-decision
description: 个股交易决策的端到端流程：从行情获取到关键价位识别、信号融合、场景化交易计划生成、止损止盈计算；适用于"给我 XX 的交易策略/买卖建议"类请求。
capability_tier: live_orchestrated
runtime_status: executable
product_surfaces: ["mcp", "bff", "web", "artifact"]
artifacts: ["analysis_report_bundle", "trade_plan"]
backing_tools: ["run_skill", "analyze_stock_product_workflow"]
backing_managers: ["decision_manager", "market_insight_manager"]
regulatory_scope: ["research_disclosure", "trade_risk_disclosure"]
role_tags: ["trader", "research", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 提供交易决策的推荐调用路径与信号简化规则，不代表文中涉及的所有工具在任意行情环境下都能给出正确预测。
>
> 交易计划仅为量化参考，不构成投资建议；实际执行需结合市场实时状况、个人风险承受能力和资金管理纪律。

# 目标

一次性生成可执行的结构化交易计划，解决两个核心问题：
1. **关键价位不能粗糙** — 每个价位必须附带确认条件和破位操作
2. **交易信号不能繁杂** — 开仓/平仓判据最多 3 个信号

# 信号简化规则（强制）

```
开仓判据限制（最多 3 个信号）：
  主信号 (1)：趋势方向 — MACD方向 或 均线排列（二选一）
  触发信号 (1)：入场时机 — RSI回到阈值 / 关键位企稳 / K线形态（三选一）
  确认信号 (1)：成交量放大 或 主力资金流入（二选一）

平仓判据限制：
  止损：ATR 止损位（入场时确定，固定不变）
  止盈：关键阻力位（1-2 个，由 get_key_levels 提供）
  追踪：最高价回撤 ATR×1.5（动态更新）

禁止：
  - 开仓判据不得超过 3 个信号
  - 不得输出 "RSI + MACD + KDJ + 布林 + 均线都显示…" 式的信号堆砌
  - 分析层面可查看多个指标，但最终决策必须收敛到上述 3 个
```

# 使用流程

## Step 1：确认标的

- 用户给名称/简称时，先 `search_stocks` 确认代码
- 确认后用 `get_realtime_quote` 获取实时价格

## Step 2：一键生成交易计划（推荐路径）

```
generate_trade_plan(code, capital, risk_per_trade, style)
```

该工具内部自动完成：
- 关键价位计算（调用 `get_key_levels`）
- 技术指标计算（MA/MACD/RSI/ATR/布林）
- K 线形态识别
- 资金流获取
- 信号融合（主信号 + 触发信号 + 确认信号）
- 场景化方案生成（回调买入 / 突破追涨 / 深度抄底）
- 止损止盈与仓位计算

返回结构包含：
- `direction`：方向判断（buy/wait_pullback/watch/avoid）
- `confidence`：置信度 0-1
- `signal_summary`：3 个信号的简洁结论 + 冲突说明
- `scenarios`：场景化入场方案（每个带入场价/止损/止盈/若错则…）
- `key_levels`：关键价位（带确认条件和破位操作）
- `position_management`：仓位管理参数

## Step 3（可选）：单独查看关键价位

```
get_key_levels(code, lookback_days)
```

返回多方法投票的支撑/阻力位，每个附带：
- `strength`：1-5 强度
- `sources`：来源算法列表（Pivot/成交密集区/斐波那契/前高前低/均线）
- `confirmation`：确认条件（如"需缩量企稳 2 日"）
- `breach_action`：突破/跌破后的操作建议

## Step 4（可选）：精细计算止损止盈

```
calculate_stop_levels(code, entry_price, direction, atr_multiplier, capital, risk_per_trade)
```

返回：
- ATR 动态止损 + 结构止损（取更保守者）
- 1:1 / 1:2 / 1:3 风险收益比止盈位
- 基于风险预算的建议仓位（A 股整手对齐）

## Step 5（可选）：信号命中率验证

```
get_signal_hit_rate(code, signal)
```

支持的信号：
- 原有：`rsi_oversold`、`macd_golden_cross`、`ma_bullish_alignment`
- 新增：`rsi_overbought`、`macd_death_cross`、`ma_death_cross`、`volume_breakout`、`bollinger_break_upper`、`bollinger_break_lower`、`ma_bearish_alignment`
- 组合：`rsi_oversold_and_macd_golden`、`volume_and_ma_bullish`

## Step 6（可选）：买入/卖出决策参考

- 买入建议：`should_i_buy(code, investment_style)`
- 卖出建议：`should_i_sell(code, buy_price, holding_days)`

这两个工具现已纳入支撑/阻力位、布林带、ATR 波动率打分。

# 输出格式规范

交易计划输出应按以下结构组织：

```
## 方向判断
[buy/wait_pullback/watch/avoid] + 置信度 + 一句话理由

## 信号摘要（最多 3 个）
- 主信号：[趋势方向判定]
- 触发信号：[入场时机判定]
- 确认信号：[量/资金面确认]
- 冲突提示（如有）

## 交易场景
### 场景 A：[推荐方案名]
- 条件：…
- 入场：价格 / 股数 / 金额
- 止损：价格 / 方法 / 最大亏损
- 止盈：价格 / 减仓比例 / 风险收益比
- 若错：[跌破/突破后怎么办]

### 场景 B / C …

## 关键价位
[支撑/阻力位表格，含强度和操作建议]

## 风控纪律
[仓位限制 / 单笔风险 / 硬止损线]
```

# 失败与兜底

- `generate_trade_plan` K 线不足 60 根：提示用户该标的数据不足，建议选择上市时间更长的标的
- `get_key_levels` 数据不足：降级为仅输出均线关键位（MA20/MA60）
- 资金流获取失败：确认信号标记为"数据不可用"，置信度下调
- 工具分流：`generate_trade_plan` 失败时，按 `get_key_levels → calculate_stop_levels → should_i_buy` 逐步降级手动拼装

# 与其他 Skill 的关系

| 需求 | 使用 Skill |
|------|-----------|
| 纯市场数据获取 | `akshare-market` |
| 技术指标/因子分析（研究向） | `akshare-quant` |
| 组合优化/回测 | `akshare-portfolio` |
| 策略工厂/批量策略管理 | `akshare-strategy-factory` |
| **个股交易策略/买卖建议** | **本 Skill** |

# 参考

- 读取 `references/tools.md` 了解三个核心工具的参数与返回要点。
