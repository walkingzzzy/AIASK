# AIASK 功能演示文档（DEMO）

> 本文用于展示 AIASK 项目当前可见能力的典型使用方式。
> 说明：本文属于演示文档，不代表所有场景在任意环境下都可直接运行；工具数量、Skills 数量与能力覆盖请以当前运行时审计结果和实际部署环境为准。
> 约束：本文示例只使用当前仓库可见的 skill / tool 名称，但不代表每个场景都已经过当前机器的端到端回归。

## 0. 当前演示基线（2026-04-26 复核）

- MCP tools：`161`
- MCP resources：`3`
- MCP prompts：`7`
- 本地 skills：`21`
- Web 页面路由：`48`
- BFF 一级模块：`42`

补充说明：

1. 本文出现的核心示例工具名已和当前运行时注册结果核对，包括：`get_realtime_quote`、`get_kline`、`get_order_book`、`get_minute_kline`、`get_financials`、`get_valuation_metrics`、`get_stock_research`、`run_simple_backtest`、`backtest_manager`、`optimize_portfolio`、`analyze_portfolio_risk`、`stress_test_portfolio`、`create_indicator_alert`、`create_combo_alert`、`generate_daily_report`、`should_i_buy`、`smart_stock_diagnosis`、`decision_manager`、`strategy_manager`、`strategy_review_workflow`。
2. 若要先完成接入与启动，优先看 [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md) 和 [`../packages/akshare-mcp/README.md`](../packages/akshare-mcp/README.md)。

## 1. 快速开始（5 分钟上手）

### 1.1 目标
用最小步骤完成一次“对话式行情查询 + 日线 K 线拉取”，不写代码、不跑脚本。

### 1.2 前置条件
- MCP 服务已启动并可被 AI 客户端连接（Claude Desktop / Cursor）。
- 若要提升结构化覆盖：建议配置 `TUSHARE_TOKEN`。
- 若要提升缓存命中与回放能力：建议启用数据库与同步任务。
- 若不确定配置是否完整，先对照 [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md)。

### 1.3 对话式最小用例（可直接复制）
**你对 AI 说：**
> 帮我查 600519 最新行情，并返回最近 5 条日线 K 线，结果用简表展示。

**可能调用的工具（示例）：**
- `get_realtime_quote`
- `get_kline`

**示例返回（文本示例）：**
```text
行情：600519（贵州茅台）
最新价：17xx.xx  涨跌幅：x.xx%

最近5条日K：
2026-xx-xx  open:xxxx  high:xxxx  low:xxxx  close:xxxx
...
```

### 1.4 常见问题
- 返回 `success=false`：通常是网络或上游源暂不可用，可稍后重试。
- 价格为 `None`：可能处于非交易时段，返回最近收盘快照。
- 盘中实时性不稳定：优先检查网络连通性、令牌配置和上游数据源状态。

---

## 2. 演示场景分类总览

| 场景分类 | 业务目标 | 推荐入口 |
|---|---|---|
| 行情查询 | 实时价格、盘口、分钟级波动跟踪 | Skills: `akshare-market` / Tools: quote、kline、order_book |
| 基本面分析 | 财务质量、估值、研报与公告联合判断 | Skills: `akshare-fundamental` / Tools: financials、valuation、research |
| 量化回测 | 策略有效性验证与参数对比 | Skills: `akshare-quant-research-process` / Tools: `run_simple_backtest`、`backtest_manager` |
| 组合管理 | 持仓优化、风险暴露、压力测试 | Skills: `akshare-fund-manager-pro` / Tools: portfolio、risk、optimize |
| 告警与跟踪 | 价格提醒、条件组合、日报输出 | Skills: `akshare-macro-options-alerts` / Tools: alerts、watchlist、report |
| 策略工厂 | 查看工厂运行状态、策略评审与孵化信息 | Skills: `akshare-strategy-factory` / Tools: `strategy_manager`、`strategy_review_workflow` |

---

## 3. 进阶场景演示（对话式工具测试）

### 3.1 场景 A：行情查询（盘中盯盘）
**场景描述**：快速获取单票行情、盘口与分钟 K 线，辅助盘中决策。

**推荐使用**：
- Skills：`akshare-market`
- MCP Tools：`get_realtime_quote`、`get_order_book`、`get_minute_kline`

**对话式测试**
- 你对 AI 说：
  > 帮我看下 000001 的最新价、买卖五档和最近 20 根 5 分钟 K 线，按“价格-量能-波动”给个简短结论。
- 可能调用的工具（示例）：
  1. `get_realtime_quote("000001")`
  2. `get_order_book("000001")`
  3. `get_minute_kline("000001", period="5m", limit=20)`
- 示例返回（可能出现的结果）：
  - 最新价与涨跌幅
  - 买一到买五、卖一到卖五价格/量
  - 最近 20 根 5m K 线的高低点与成交量变化

**关键配置**：`AKSHARE_SPOT_TTL_SECONDS`、`AKSHARE_SPOT_TIMEOUT_SECONDS`

**注意事项**：分钟 K 在非交易时段可能返回当日最后快照。

### 3.2 场景 B：基本面分析（财务 + 估值 + 研究）
**场景描述**：做“是否值得继续研究”的第一轮筛查。

**推荐使用**：
- Skills：`akshare-fundamental`、`akshare-fund-news`
- MCP Tools：`get_financials`、`get_valuation_metrics`、`get_stock_research`

**对话式测试**
- 你对 AI 说：
  > 请对 600519 做一轮基本面快筛：财务健康度、当前估值水平、最近研报观点，最后给“继续研究/暂缓”建议。
- 可能调用的工具（示例）：
  1. `get_financials("600519")`
  2. `get_valuation_metrics("600519")`
  3. `get_stock_research("600519", limit=5)`
- 示例返回（可能出现的结果）：
  - 营收/利润/ROE 等核心财务指标摘要
  - PE/PB/PS 等估值指标区间判断
  - 最近研报数量、评级倾向、目标价分布（如可得）

**关键配置**：建议配置 `TUSHARE_TOKEN` 以提升结构化数据覆盖。

**注意事项**：部分财务数据是日频/T+1 更新，不应与盘中指标混用。

### 3.3 场景 C：量化回测（策略可行性）
**场景描述**：验证策略在历史区间的收益、回撤、胜率等表现。

**推荐使用**：
- Skills：`akshare-quant-research-process`
- MCP Tools：`run_simple_backtest`

**对话式测试**
- 你对 AI 说：
  > 用均线交叉策略回测 600519（2023-01-01 到 2025-12-31），输出收益率、最大回撤、夏普比率，并给参数调优建议。
- AI 预期调用：
  1. `run_simple_backtest(code="600519", strategy="ma_cross", start_date="2023-01-01", end_date="2025-12-31", short_period=5, long_period=20)`
- 预期返回（示例）：
  - 累计收益、年化收益、最大回撤、夏普
  - 交易次数、胜率、盈亏比
  - 参数建议（如 short/long 周期可调范围）

补充说明：
- `run_simple_backtest` 当前直接返回回测结果，不会自动生成可供 `performance_manager(action="backtest_metrics")` 二次查询的 `artifact_id`
- 若需要“落库后再查绩效”的演示，应改用 `backtest_manager`

**关键配置**：并行优化时可安装 `ray[default]`。

**注意事项**：先小样本验证，再扩到批量回测，避免参数过拟合。

### 3.4 场景 D：组合管理（优化 + 风控）
**场景描述**：给定股票池，输出权重建议并进行风险分析。

**推荐使用**：
- Skills：`akshare-fund-manager-pro`
- MCP Tools：`optimize_portfolio`、`analyze_portfolio_risk`、`stress_test_portfolio`

**对话式测试**
- 你对 AI 说：
  > 我有股票池 [600519, 000858, 601318]，风险偏好平衡。请先给风险平价权重，再做一次压力测试并提示主要风险暴露。
- AI 预期调用：
  1. `optimize_portfolio(stocks=["600519","000858","601318"], method="risk_parity", lookback_days=252)`
  2. `analyze_portfolio_risk(...)`
  3. `stress_test_portfolio(...)`
- 预期返回（示例）：
  - 建议权重与组合波动/回撤指标
  - VaR/CVaR 或情景压力结果
  - 主要风险来源（行业集中度、个股相关性等）

**关键配置**：建议启用数据库以沉淀历史结果并支持复盘。

**注意事项**：优化结果依赖历史窗口，不同窗口会导致权重变化。

### 3.5 场景 E：告警与日报联动
**场景描述**：将研究结论沉淀为提醒和日报，方便持续跟踪。

**推荐使用**：
- Skills：`akshare-macro-options-alerts`
- MCP Tools：`create_indicator_alert`、`create_combo_alert`、`generate_daily_report`

**对话式测试**
- 你对 AI 说：
  > 给 600519 设置一个跌破 1350 的提醒，再做一个“RSI>80 且成交量放大 2 倍”的组合提醒。最后把今天的分析整理成日报摘要。
- AI 预期调用：
  1. `create_indicator_alert(code="600519", indicator="price", condition="<", value=1350)`
  2. `create_combo_alert(name="momentum-alert", conditions=[...], logic="AND")`
  3. `generate_daily_report()`
- 预期返回（示例）：
  - 预警创建状态
  - 触发条件摘要
  - 当日市场与组合跟踪报告

**关键配置**：建议配置数据库与通知通道，便于后续检查和复盘。

**注意事项**：预警是辅助提醒，不应替代仓位控制和合规判断。

### 3.6 场景 F：策略工厂与策略评审
**场景描述**：查看当前工厂运行状态、最近运行记录，并对单个策略做只读评审聚合。

**推荐使用**：
- Skills：`akshare-strategy-factory`
- MCP Tools：`strategy_manager`、`strategy_review_workflow`

**对话式测试**
- 你对 AI 说：
  > 帮我查看当前策略工厂运行状态，列出最近 3 次工厂运行摘要；再对某个策略做一次 review 汇总，重点看当前状态、质量报告和运行告警。
- AI 预期调用：
  1. `strategy_manager(action="factory_status")`
  2. `strategy_manager(action="factory_runs", params={"limit": 3})`
  3. `strategy_review_workflow(strategy_id="...", include_factory_status=true, include_review_report=true, include_runtime_alerts=true)`
- 预期返回（示例）：
  - 当前工厂是否运行、最近一次运行结果、候选/提交/门禁摘要
  - 最近 3 次工厂运行记录
  - 单个策略的当前状态、review 报告、runtime alerts、只读聚合摘要

**关键配置**：建议启用数据库与策略工厂相关表，便于看到完整运行历史。

**注意事项**：
- `strategy_review_workflow` 默认是只读聚合；只有显式打开 `run_factory_once` 或 `run_runtime_cycle` 才会产生状态性动作。
- 当前开发入口以 [`../策略工厂/README.md`](../策略工厂/README.md) 和 [`../策略工厂/策略工厂整改详细清单.md`](../策略工厂/策略工厂整改详细清单.md) 为准。

---

## 4. AI 客户端提示词示例（Claude Desktop / Cursor）

### 4.1 快速分析提示词
```text
请用 AIASK 先执行 akshare-market 获取 600519 最新行情与近 20 根 5 分钟 K 线，
再用 akshare-fundamental 给出财务与估值摘要，最后输出“观察/继续研究/回避”建议。
```

### 4.2 研究到回测提示词
```text
请走 akshare-quant-research-process：
1) 先做数据质量检查；2) 用 ma_cross 在 2023-01-01~2025-12-31 回测 600519；
3) 输出收益、最大回撤、夏普，并给出参数调优建议。
```

### 4.3 组合投顾提示词
```text
我有股票池 [600519, 000858, 601318]，风险偏好平衡。
请使用 akshare-fund-manager-pro 先做风险诊断，再给一版风险平价权重和压力测试结论。
```

---

## 5. 完整工作流演示（研究 → 回测 → 风控 → 跟踪）

1. **研究阶段**：`akshare-market` + `akshare-fundamental`
2. **验证阶段**：`akshare-quant-research-process`
3. **风控阶段**：`akshare-fund-manager-pro`
4. **跟踪阶段**：`alerts_manager` / `watchlist_manager` / `generate_daily_report`
5. **策略工厂评审阶段**：`strategy_manager` / `strategy_review_workflow`

**工作流输出应至少包含**：
- 投资结论（买入/观察/回避）
- 关键证据（行情、财务、回测指标、风险指标）
- 风险提示（数据时效、回测偏差、执行约束）

---

## 6. 备注
- 本文示例聚焦“可运行与可复现”；不同环境下数据源命中路径会不同（主源/降级源）。
- 本文示例使用的 skill / tool 名称均来自当前仓库可见实现，但是否能在当前环境完整跑通仍受数据库、令牌、上游数据源与客户端配置影响。
- 如需扩展演示，可按相同模板新增“输入参数 + 预期输出 + 配置 + 注意事项”。

---

## 7. 新手模式演示（非专业用户）

> 目标：让不懂金融术语、不会写代码的用户，也能在 1~3 分钟内得到“可执行建议 + 风险边界 + 数据来源”。

### 7.1 新手模式统一输出卡片
演示中建议固定输出 6 项：
1. **结论**：买入 / 观望 / 减仓
2. **三条理由**：只讲结论依据，不堆术语
3. **怎么做**：仓位、价格区间、止损/止盈
4. **主要风险**：最多 2 条
5. **数据来源与时效**：来源链路 + 更新时间
6. **合规提示**：不承诺收益，建议结合自身风险承受能力

### 7.2 场景一：今天这只股票能不能买？
**你对 AI 说：**
> 我是新手，帮我判断 601288 今天是否适合买入，用简单语言告诉我该怎么做。

**AI 预期调用（内部）**：`should_i_buy`、`smart_stock_diagnosis`、`get_realtime_quote`

**你会看到（示例）**：
- 结论：**可小仓位试探**
- 理由：趋势中性偏强、估值不高、回撤风险可控
- 动作：先 30% 仓位；回落到 X~Y 分批补；跌破 Z 暂停加仓
- 风险：盘中波动放大；行业情绪转弱
- 数据来源：AKShare/Tushare/公开行情源（自动降级）
- 时效性：行情为盘中近实时，财务为最近披露期

### 7.3 场景二：我有 10 万元，怎么分配更稳？
**你对 AI 说：**
> 我有 10 万，风险偏好保守，帮我做一个分散配置方案，给出每只大概买多少。

**AI 预期调用（内部）**：`decision_manager(portfolio_advice)`、`optimize_portfolio`、`analyze_portfolio_risk`

**你会看到（示例）**：
- 结论：**分散配置，避免单票过重**
- 动作：A 30%、B 25%、C 20%、防御仓 15%、现金 10%
- 风险：行业集中度偏高时提示降权
- 数据来源：历史行情 + 风险指标库
- 时效性：建议按交易日更新

### 7.4 场景三：我的持仓要不要止盈止损？
**你对 AI 说：**
> 我 8 天前买了 000001，成本 11.20，帮我判断现在该持有还是减仓，并告诉我止盈止损位。

**AI 预期调用（内部）**：`should_i_sell`、`get_realtime_quote`；若用户要求顺带创建提醒，再调用 `alerts_manager`

**你会看到（示例）**：
- 结论：**减仓 20% + 设置保护线**
- 动作：跌破 X 提醒止损；到达 Y 分批止盈
- 风险：追涨回撤；消息面扰动
- 数据来源：实时行情 + 技术信号
- 时效性：交易时段近实时

### 7.5 场景四：今天市场风险大吗？
**你对 AI 说：**
> 今天整体市场风险高不高？我现在 80% 仓位要不要降一点？

**AI 预期调用（内部）**：`generate_daily_report`、`sentiment_manager(action="market_sentiment")`、`get_market_sentiment_context`

**你会看到（示例）**：
- 结论：**黄灯（偏谨慎）**
- 动作：建议仓位从 80% 降至 60%
- 风险依据：北向资金流向、涨跌家数、波动变化
- 数据来源：指数/资金流/情绪聚合数据
- 时效性：盘中动态 + 收盘复盘

### 7.6 场景五：先模拟一周，再决定是否实盘
**你对 AI 说：**
> 我先不实盘，按你的建议做 7 天模拟交易，看看结果再说。

**AI 预期调用（内部）**：`paper_trading_manager`；若要先补一段历史回测基线，再决定是否进入模拟，可补 `run_simple_backtest`

**你会看到（示例）**：
- 结果：模拟收益、最大回撤、胜率、执行纪律评分
- 结论：达标则小额实盘；不达标继续模拟
- 风险：历史/模拟不代表未来
- 数据来源：历史 + 实时行情
- 时效性：每日收盘更新

补充说明：
- `paper_trading_manager` 当前负责模拟账户、委托、NAV 历史和订单流水；若要看模拟账户绩效，更接近实际链路的是 `summary` / `nav_history` / `orders`
- `run_simple_backtest` 更适合做“历史基线参考”，不等价于模拟账户的真实 7 天运行结果
- `performance_manager` 当前面向组合与回测绩效，不是模拟交易账户的直接查询入口

---

## 8. 用户回答卡片 JSON（前端渲染示例载荷）

> 用途：给前端演示“新手模式”回答的渲染格式。
> 边界：本节是渲染示例，不是当前 MCP 层稳定 contract；统一决策稳定契约请以 `docs/plans/统一决策对象协议.md` 为准。

### 8.1 JSON 结构（示例）
```json
{
  "version": "1.0",
  "scene": "buy_decision",
  "action": "buy",
  "confidence": 0.72,
  "summary": "可小仓位试探，等待回踩确认",
  "reasons": [
    "短期趋势中性偏强",
    "估值处于可接受区间",
    "回撤风险可控"
  ],
  "execution_plan": {
    "position": "30%",
    "buy_zone": "10.80-11.00",
    "stop_loss": "10.45",
    "take_profit": ["11.60", "11.90"]
  },
  "risks": [
    "盘中波动可能放大",
    "行业情绪走弱会拖累价格"
  ],
  "data_provenance": [
    {
      "source": "akshare_live",
      "dataset": "realtime_quote",
      "timestamp": "2026-02-18T10:35:00+08:00"
    },
    {
      "source": "tushare",
      "dataset": "financials",
      "timestamp": "2026-02-17"
    }
  ],
  "timeliness": {
    "market_data": "交易时段近实时",
    "fundamental_data": "最近披露期"
  },
  "compliance_notice": "本结果仅供参考，不构成投资建议，不承诺收益。"
}
```

### 8.2 字段约束（建议）
- `action`：`buy | hold | reduce | watch`
- `confidence`：0~1，小于 0.55 默认输出“观望”
- `reasons`：建议 2~4 条，每条不超过 18 字
- `risks`：至少 1 条，最多 3 条
- `data_provenance`：建议至少 1 条，并带 `timestamp`
- `compliance_notice`：演示载荷建议返回；BFF 归一化层当前也会在缺失时补默认免责声明

### 8.3 前端展示建议
- 首屏只显示：结论、动作、风险（3 秒可读）
- 二级展开：理由、来源、时效性
- 风险高时（如 `action=reduce`）：按钮默认“先看风险解释”
- 若后续增强前端联动，可把 `stop_loss` / `take_profit` 映射为告警创建动作；当前默认卡片并未直接内置“一键创建提醒”按钮

---

- 若面向纯新手演示，建议优先使用第 7 节与第 8 节内容；第 3~5 节作为专业模式补充。
