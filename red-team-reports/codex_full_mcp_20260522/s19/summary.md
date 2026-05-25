# S19 · 执行 / 实盘 / 策略 + 用户/权限/审计 + 风险监控 + 治理巡检

- **判定**: ✅ 通过 (31/31 工具,Pass=14 / Degraded=10 / Fail-graceful=7 / Fail=0)
- **耗时**: 16:55:13 → 17:03:10 (约 8 分钟)
- **覆盖**: strategy_manager(70 actions:capabilities/factory_status/runtime_alerts/runtime_cycle_status 等)/ paper_trading(8 actions:list/summary/positions/orders/order_events/nav_history/matching_status/nav_status)/ execution_manager × 2 / live_trading(gateway_status)/ compliance(check_order × 3 + rules)/ user(get_profile / assess_kyc / list)/ alerts(help/create/list)/ risk(calculate_var/stress_test)/ governance_check_workflow / experiment_tracker / data_validation / log_audit

## 🔥 6 条 high finding

### 1. user_manager 强制 auth check 但 paper_trading 不强制(S19-F01)

```
user_manager.get_profile(user_id=codex_full_mcp_20260522):
  → AUTH_ERROR "user_id 与当前调用身份不匹配,禁止跨用户访问"

user_manager.assess_kyc(user_id=codex_full_mcp_20260522):
  → AUTH_ERROR(同上)

user_manager.list:
  → 1 user(只有 default)        ← codex 用户不存在!

vs.

paper_trading_manager.list_accounts(user_id=codex_full_mcp_20260522):
  → 2 accounts(351521db / 55c4e3a8)  ← user 不存在但 account 存在!
```

**user_manager 与 paper_trading 权限模型完全脱钩**:user 不存在不影响 paper_trading 创建账户;但 user_manager 拒绝跨用户访问。AI 同时调两 manager 拿到矛盾结果。

### 2. paper_trading 撮合引擎 + NAV 引擎都 running=false(S19-F02)

```
matching_status:  running=false  scan_count=0   last_scan=null
nav_status:       running=false  last_run=null  run_time="15:30:00"

但 paper_trading.list_accounts 仍允许 place_order
account=351521db pending_orders=0 positions=1(601318 × 3500)
order_events 显示 5/24 04:23 有 1 个 limit order 被 cancelled
```

**核心引擎都没运行但 paper_trading 仍接单** — 所有挂单都不会成交,持仓 NAV 不更新;**实质上是 mock service**。

### 3. order_book 全 0 触发 compliance + execution_manager 双重阻断(S19-F03)

```
compliance.check_order(600519, qty=100):
  passed=false  blocked=true
  violations=["实时盘口卖量为 0,当前疑似无法买入"]   ← 触发 violation
  realtime.top_ask_volume=0 / top_bid_volume=0

execution_manager.twap(600519, total_quantity=1000):
  success=false
  compliance_gate.compliance_blocked=true
  compliance_violations=["实时盘口卖量为 0,..."]   ← 同 violation
  error="合规闸门阻断: 实时盘口卖量为 0,当前疑似无法买入"
```

S18-F04 order_book 全 0 → S19 这里**触发 compliance/execution 双重阻断**,所有订单 100% blocked。无法测试任何下单链路。

### 4. governance_check_workflow online_offline 不一致(S19-F04)

```
overall_status: warning
issues: ["online_offline:inconsistent"]

backtest_assumptions:
  reference_price=0.0
  commission_rate=0.0003
  slippage_bps=0.0          ← 回测零滑点!
  market_impact_bps=0.0     ← 回测零市场冲击!

execution_assumptions:
  slippage_bps=5.0          ← 实际执行 5bps
  market_impact_bps=3.0     ← 实际 3bps

gaps: 2 (slippage_bps delta=5 / market_impact_bps delta=3)
warnings:
  - "回测使用零滑点假设,与执行模式差距显著"
  - "回测使用零市场冲击假设,AI 应注意此差距"
```

**回测 vs 执行假设 8bps 总成本 gap** — graceful 标 warning ✅ 但 backtest 出来的 sharpe 都得打折。

### 5. strategy_factory 143 策略全 D 级 zero_signal(S19-F05)

```
submitted_strategy_cohort:
  factory_strategy_count: 143         ← 提交 143 个
  status_counts: {"submitted": 143}
  validation_grade_distribution: {"D": 142, "UNKNOWN": 1}
  raw_validation_d_rate: 99.3%        ← 99% D 级
  zero_signal_rate: 100%              ← 100% 零信号!
  promotion_ready_rate: 0.0%

recent 5 runs:
  status:    [partial_llm × 2, partial_infra × 1, success × 1, partial × 1]
  submitted: [0, 0, 0, 0, 0]          ← 5 次全 0 提交
  warning_reason_topn:
    - governed_candidate_pool_blocked_candidates: 5
    - governed_candidate_pool_provisional: 5
  governed_blocked_ratio: 92.68%     ← 38/41 候选被 block
```

**策略工厂运转但完全没有产出**;143 累计 submitted 全 D 级零信号。AI 调 `strategy_manager.list` 看到 0 active strategies,但 cohort 显示 143 个 submitted — 命名让 AI 困惑。

### 6. alerts_manager.create 拒绝 HTML escape 后的 < operator(S19-F06)

```
input.condition: "&lt;"   ← MCP 工具调用强制 escape
output.error:    "不支持的条件: &lt;. 支持: >, <, >=, <=, =="
```

但 MCP 工具调用 schema 让 `<` 字符必须 HTML escape,服务器接收后又因为没 unescape 而 reject — **协议层 escape 与业务层验证冲突**。alerts.list 显式查到的 alert 含 raw `<`/`>`(price>1500 / price<1200)说明可以 raw 接收,只是不能 HTML escape。

## ✅ 4 positive

### S19-F12 ✅:risk_manager 完整(VaR + stress_test 多场景)

```
calculate_var(95% conf, 3 codes, weights=[0.4,0.3,0.3]):
  VaR  = -1.03%  (-10341 元)
  CVaR = -1.43%  (-14299 元)
  volatility = 0.70%
  max_drawdown = -2.33%

stress_test(2 scenarios):
  market_crash:        -21.00% loss(severity=high, recommendation=consider hedging)
  interest_rate_hike:  -10.50% loss(severity=medium, risk acceptable)
  layer_losses 完整:    market_loss + volatility_penalty + liquidity_penalty
```

**3 method × 多 layer × scenario 完整** ✅。

### S19-F13 ✅:paper_trading order_events 极完整

```
events × 3:
  - order_id=5    code=600519  cancelled (5/24 04:24)
                  schema_version=v1  event_category=order_lifecycle
                  transition={from: pending, to: cancelled}
  - order_id=2d6dd370  code=601318  filled (5/24 04:23)
                  shares=3500  price=53.68  amount=187880  commission=56.364
                  event_category=execution
  - order_id=5    code=600519  created (5/24 04:23)
                  shares=100  price=1290.00  order_type=limit

summary.by_type:     {cancelled: 1, filled: 1, created: 1}
summary.by_category: {order_lifecycle: 2, execution: 1}
```

✅ **schema_version=v1 + event_category + transition + raw_payload 完整**;state machine 清晰。

### S19-F14 ✅:compliance.rules 8 规则完整

```
8 rules:
  1. position_limit:        单只股票持仓不超过净资产 10%
  2. single_order_shares:   单笔数量不超过 1,000,000 股
  3. single_order_amount:   单笔金额不超过 50,000,000 元
  4. lot_size:              买入数量建议为 100 的整数倍
  5. trading_hours:         9:30-11:30 / 13:00-15:00
  6. st_restriction:        ST 股票每日涨跌幅限制 5%
  7. suspended:             停牌股票不可交易
  8. limit_up_down:         涨跌停股票限制交易
```

✅ A 股监管完整覆盖 ✅。

### S19-F15 ✅:data_validation 累计 12 场景 62/62 stable

```
S07-S18: 56/56  +  S19: 6/6
─────────────────────────
                total: 62/62  100%
```

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **19/22**
- 累计 Fail: **0**
- 累计推荐 bug: **214 条**(S02-S18 累计 199 + S19 新增 15,其中 high 累计 **98 条**)

## 关键观察:S19 验证了"权限/引擎/治理三层全断节"

**核心问题**:

1. **user_manager 与 paper_trading 完全脱钩**(F01):user 不存在但 account 存在
2. **撮合 + NAV 引擎都 running=false**(F02):mock service 形式接单
3. **order_book volume=0 → compliance/execution 双重 100% 阻断**(F03):无法测任何下单
4. **回测零成本假设 vs 实际 8bps 成本**(F04):governance 标 warning ✅ 但 backtest sharpe 失真
5. **143 策略全 D 级 zero_signal**(F05):工厂运转零产出
6. **MCP escape vs 业务 unescape 冲突**(F06):HTML escape 字符被业务 reject

**positive 证据**:
- risk_manager 极完整(VaR + CVaR + stress_test layer_losses)
- order_events schema v1(category + transition + payload)清晰
- compliance 8 规则完整覆盖 A 股监管
- data_validation 12 场景 62/62 stable

**累计 19/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计 bug 214(其中 high 98),22 场景红队复测剩 3 场景(S20-S22)。
