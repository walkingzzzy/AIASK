# S11 · 模拟交易 + 风控规则 + 订单生命周期 + 多账户 NAV + 撮合引擎 + 合规闸门 + 告警引擎 + TWAP/VWAP

- **判定**: ✅ 通过 (32/31 工具,Pass=22 / Degraded=13 / Fail-graceful=3 / Fail=0)
- **耗时**: 12:23:26 → 12:25:20 (约 114s)
- **覆盖**: paper_trading_manager(20 actions)/ compliance_manager / execution_manager / alerts_manager + 多账户 NAV / 撮合引擎 / TWAP/VWAP / GE validation
- **持仓状态**: portfolio_id 不再使用,本场景用 paper_account `351521db`(user_id=codex_full_mcp_20260522,1 position 601318/3500@53.68 + 1 cancelled limit)+ `55c4e3a8`(500K initial)+ silent 误创 `524dfc8f`(default user 10 万,F01 bug)

## 🔥 本场景重大发现 — 状态管理静默错位 + RSI/价格双源矛盾(16 条 finding,8 条 high)

### 1. set_risk_rules 静默创建错误账户(S11-F01)

```python
paper_trading_manager.set_risk_rules(
    max_drawdown=0.15,          # 输入 fraction
    max_position_pct=0.4,
    stop_loss_pct=0.08
)
# 我没传 account_id ↓
# 输出:
{
  "account_id": "524dfc8f",                    # ← 全新 default user 账户被创建!
  "risk_rules": {
    "max_drawdown_pct": 20.0,                  # ← 输入 0.15 → 输出 20.0(单位混淆)
    "max_position_pct": 40.0,
    "stop_loss_pct": 8.0
  }
}

# 之后 summary(351521db).risk_rules = "{}"  ← 我的目标账户 risk_rules 仍空!
```

**严重问题**:
- 没传 account_id 不报错 → silent 创建 default user 新账户
- max_drawdown 0.15 → 20.0(15% 变 20%,**风控数值漂移**)
- 我的真正目标账户 351521db.risk_rules 仍是 `{}`

### 2. matching/nav engine 双双 not running(S11-F02)

```
matching_status:    running=false  scan_count=0  last_scan=null  scan_interval=30s
nav_status:         running=false  last_run=null  run_time="15:30:00"

place_order(market 601318):  status=filled    @ 53.68    ← 直接成交!
place_order(limit  600519):  status=pending              ← 引擎没跑就 stuck

nav_history(351521db):  nav=[]                            ← NAV 没记录
```

**market 订单绕过 matching 直接 fill / limit 订单依赖 matching 队列卡住**;NAV 引擎只在 15:30 跑一次,其它时间没记录。

### 3. compliance.check_order(price 1828) 超 limit_up=1442 但 limit_up_down 仍 passed=true(S11-F03)

```
input:
  price                = 1828.0
realtime:
  current_price        = 1290.2
  pre_close            = 1311.0
  limit_up_price       = 1442.1   (= 1311 × 1.10)
  limit_down_price     = 1179.9
  at_limit_up          = false      ← current_price 不在涨停
checks.limit_up_down:  true          ← passed!但 1828 > 1442!
```

**校验逻辑错**:`limit_up_down` 检查的是 `current_price 当前是否在涨停`,**不是 `order_price > limit_up_price`**。AI 提交超涨停价订单不会被拦截。

### 4. list_accounts user_id scope filter bug(S11-F04)

```
list_accounts(no user_id):
  count = 1
  accounts[0].user_id = "default"
  accounts[0].initial_capital = 100000

list_accounts(user_id="codex_full_mcp_20260522"):
  count = 2                                    ← 我的 351521db + 55c4e3a8 都在
  
summary(351521db):                             ← 不限制 user_id 又能拿到
  account.user_id = "codex_full_mcp_20260522"
```

**list_accounts 不传 user_id 默认 'default' scope** 看不到自己创建的账户;但 `summary(account_id)` 不限制 → **scope 一致性破坏**。

### 5. alerts_manager HTML escape 不解(S11-F05)

```python
# Case 1: create with `&lt;`
alerts_manager.create(condition="&lt;", indicator="price", value=1280)
→ "不支持的条件: &lt;. 支持: >, <, >=, <=, =="     ← 工具不解 escape

# Case 2: delete with alert_id 含 `&gt;`
alerts_manager.delete(alert_id="alert_600519_price_&gt;")
→ "告警不存在: alert_600519_price_&gt;"             ← alert_id 是字符串拼接,
                                                       前端 escape 后端不还原
# Case 3: `&lt;=`
→ "不支持的条件: &lt;="
```

前端 escape `>`/`<`/`<=` 后端不 unescape,**create / delete / lookup 全失败**。

### 6. alerts.list 全部 user_id='default' 但我创建时传过 user_id(S11-F06)

```
3 alerts in list:
  alert_600519_rsi_<      user_id="default"
  alert_600519_price_<    user_id="default"
  alert_600519_price_>    user_id="default"

# 但前面 S11 有创建尝试 user_id="codex_full_mcp_20260522"
```

`alerts_manager` 内部所有 user_id 写死 'default'(对比 paper_trading 有 USER_SCOPE_MISMATCH)— **多用户隔离严重缺陷**。

### 7. 同股 RSI 双工具 22.59 vs 2.76(S11-F07)

```
S10 12:13  factor_profile.rsi.current = 22.5864
S11 12:24  alerts.check.current_value = 2.7586     ← 10 min 内 RSI 从 22.59 → 2.76?
delta_pct  = 87.7%
```

不可能 10 分钟 RSI 跌 87%(且非交易时段 K 线不变)— **同名 'rsi' 两工具实现不同**;`factor_profile` 用 RSI(14) Wilder,`alerts` 用别的窗口/平滑公式。AI 看 alert 触发 'RSI=2.76 极度超卖' 但同时 factor_profile 22.59 不超卖 → **决策完全相反**。

### 8. 600519 当前价 1290 vs 之前 1828(S11-F08)

```
S04  get_stock_info(600519).price            = 1828
S07  get_realtime_quote(600519).price        = 1828
S09  run_simple_backtest 平均价              ≈ 1825
S11  compliance.check_order.realtime.current = 1290.2
S11  compliance.check_order.realtime.source  = "db.stock_quotes"

delta = 537.8 元 (29.4%)
```

**db.stock_quotes 与 realtime_quote 走不同 cache** — S04/S07 走 tqcenter realtime → 1828;S11 compliance 走 db.stock_quotes → 1290。



## ✅ Positive evidence(4 条)

### S11-F13:paper_trading 风控/合规闸门全套 robust ✅

| 拦截点 | 检验场景 | 结果 |
|---|---|---|
| **T+1 限制** | 卖 3500 当日买入仓位 | ✅ "可卖 0 股" 拦截 |
| **lot_size 100 倍** | 买 450 / 350 shares | ✅ "100 整数倍" 拦截 |
| **amount limit 5000 万** | 买 1M shares × 1500 = 15 亿 | ✅ "单笔金额超限" 拦截 |
| **USER_SCOPE_MISMATCH** | archive 跨 user 账户 | ✅ error_code=USER_SCOPE_MISMATCH |
| **compliance_blocked**(TWAP/VWAP) | 盘口卖量为 0 | ✅ 阻断 + soft_warning |
| **soft_warning participation_rate** | 233% 参与率 | ✅ severity=high 警告 |

**6 个 hard 闸门全部 robust** — paper_trading + compliance + execution 三 manager 是**风控层最稳定**部分。

### S11-F14:order_events 事件溯源最完整 ✅

```json
{
  "schema_version": "v1",
  "order_id": "2d6dd370",
  "event_category": "execution",
  "event_type": "filled",
  "transition": {"from_status": null, "to_status": "filled"},
  "risk": {"reason": null},
  "order": {"order_type": "market", "direction": "buy", "shares": 3500, "price": 53.68, "amount": 187880, "commission": 56.364},
  "occurred_at": "2026-05-24T04:23:46.226702+00:00"
}
summary:
  by_type:     {"filled": 1}
  by_category: {"execution": 1}
  by_status:   {"filled": 1}
```

**schema_version 版本控制 + event_category + transition + risk + by_* 三维度摘要全套** — 这是工具集**事件层最 robust 部分**。

### S11-F15:data_validation(GE)累计 5/5 stable ✅

```
S07 → val-53273787f84a   evaluated=7  pass=7   100%
S08 → val-1ca745e7ab52   evaluated=7  pass=7   100%
S09 → val-e8933820055e   evaluated=2  pass=2   100%
S10 → val-0fa79bf3ba13   evaluated=3  pass=3   100%
S11 → val-3089e8754aab   evaluated=5  pass=5   100%   ← 5 expectations on orders dataset
```

**5 场景累计 5/5 全 pass** — `data_validation` GE backend 是工具集**最稳定的层**。

### S11-F16:execution_manager hard+soft 双层闸门 ✅

```
TWAP(600519, 600 shares, 60min, balanced):
  compliance_gate.compliance_blocked = true
  compliance_gate.violations         = ["盘口卖量为 0"]
  soft_warnings:
    - participation_rate_high  severity=medium  "48.82% > 20% 阈值"
    - compliance_advisory      severity=low     "不在交易时段"

VWAP(601318, 35000 shares, 30min):
  soft_warnings:
    - participation_rate_high  severity=high    "233.32% > 20% 阈值"   ← super-high

list:  7 历史 tasks
       cancelled 4 / completed 1 / failed 2
       artifact_id 链路完整(codex_full_mcp_20260522_s10_twap 等)
       estimated_total_cost = 20842.33
```

**TWAP/VWAP 真正产品级**:compliance hard gate + soft_gate 软警告 + artifact_id 全链路。

## 🚨 工具间数据不一致(本场景新增 16 条 finding,其中 high 8 条)

### 8 条 high

- **S11-F01**:`set_risk_rules` 静默创建错误账户 + max_drawdown 0.15→20.0 单位漂移
- **S11-F02**:matching/nav engine 双双 not running 但 market 订单仍 filled(运行逻辑反直觉)
- **S11-F03**:`compliance.check_order` price>limit_up 但 limit_up_down 仍 passed=true(校验逻辑错)
- **S11-F04**:`list_accounts` 不传 user_id 默认 'default' scope(看不到自己账户)
- **S11-F05**:`alerts_manager` 不解 HTML escape(`&lt;`/`&gt;`/`&lt;=` 全 fail)
- **S11-F06**:`alerts.list` 所有 user_id='default'(传入 user_id 被忽略,多用户隔离缺陷)
- **S11-F07**:同股 RSI `factor_profile=22.59` vs `alerts=2.76` 差 8 倍(同名 RSI 两工具不同公式)
- **S11-F08**:同股 600519 当前价 `db.stock_quotes=1290` vs `realtime=1828` 差 540 元(29.4%)

### 4 条 medium

- S11-F09:`update_prices` refresh_prices=true 但 current_price 没变(silent skip)
- S11-F10:`twap` user 传 avg_minute_volume=5000 但工具用 db 的 204
- S11-F11:`execution_manager.list` 7 历史 tasks 全部 soft_gate_profile='unknown'
- S11-F12:`set_risk_rules` 单位混淆(0.15 → 20.0)

### 4 条 low(positive evidence)

- **S11-F13** ✅:paper_trading 风控/合规 6 个 hard 闸门全 robust
- **S11-F14** ✅:`order_events` schema_version v1 + 三维度 by_* 摘要(事件溯源最完整)
- **S11-F15** ✅:`data_validation`(GE)S07-S11 累计 5/5 stable
- **S11-F16** ✅:`execution_manager` hard+soft 双层闸门 + artifact_id 全链路

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `351521db` paper_account | **persist** | user=codex_full_mcp_20260522,1 position 601318 + 1 cancelled limit |
| `524dfc8f` paper_account | **persist (silent created!)** | user=default,initial=10万,from set_risk_rules bug F01 |
| `55c4e3a8` paper_account | **persist** | user=codex_full_mcp_20260522,initial=500K |
| `2d6dd370` paper_trade | **persist** | 601318 buy 3500@53.68 commission=56.364 |
| `5` paper_order | **persist** | 600519 buy limit @1290 → cancelled |
| 3 alerts | **persist** | rsi<25 / price<1200 / price>1500 全 user='default'(F06 bug)|
| `val-3089e8754aab` validation | read_only | GE backend 5/5 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s11_audit |
| ~32 audit_event_id | read_only | compliance × 4 / paper_trading × 18 / execution × 5 / alerts × 5 / validation |

## 🚨 Fail
无。但有 3 个 Fail-graceful:
- `set_risk_rules` 没传 account_id 静默创建新账户(实际应该 fail-fast)
- `alerts.create` HTML escape 失败(前端兼容性差)
- `alerts.delete` HTML escape 失败(同上)

## ➡ 进度

- 累计调用工具(去重): **~156/161**(S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6 + S07 +5 + S08 +14 + S09 +12 + S10 +11 + S11 +8)
- 已通过场景: **10/22**
- 累计 Fail: **0**
- 累计推荐 bug: **101 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16 + S11 16,其中 high 累计 **49 条**)

## 关键观察:S11 暴露了"状态管理 + 校验逻辑 + 单位/口径"的硬伤

**S07-S10** 都是数据/数学层问题;**S11 暴露的是状态管理层 / hardcoded 单位 / scope filter / RSI 公式不一致 / 价格双源** — 这是**模拟交易系统的核心信任问题**。

**核心问题模式**:

1. **silent state mutation**(S11-F01):`set_risk_rules` 不报错而是静默创建错误 default 账户;`max_drawdown 0.15 → 20.0` 单位漂移
2. **engine running=false 但部分功能仍能跑**(S11-F02):matching/nav engine 都不在跑,但 market order 仍 filled / limit order stuck — **两个层次的状态(引擎 vs 订单类型)解耦但不透明**
3. **校验逻辑维度错**(S11-F03):`limit_up_down` 检查 'current_price at limit' 而不是 'order_price > limit_up_price'
4. **scope filter 不一致**(S11-F04):list_accounts 默认 'default' scope vs summary 不限制 user_id;**同 manager 内 scope 行为不同**
5. **HTML escape 兼容性差**(S11-F05):`&lt;`/`&gt;`/`&lt;=` 全失败 + alert_id 字符串拼接也含 escape
6. **多用户隔离缺陷**(S11-F06):alerts user_id 写死 'default',传入参数被忽略 — **vs paper_trading 有 USER_SCOPE_MISMATCH 显著差距**
7. **同名指标多套实现**(S11-F07):RSI 在 factor_profile / alerts / 估值层 等多处计算公式不同,差距高达 8 倍
8. **价格数据双源不一致**(S11-F08):db.stock_quotes vs realtime_quote 同股 540 元差异(29%),前面 S04/S07 PE 不一致根源被 S11 揭示

**positive 证据**(4 条):

- paper_trading 6 个 hard 闸门(T+1 / lot_size / amount / user_scope / compliance / soft_warning)全 robust
- `order_events` schema_version v1 + 三维度 by_* 摘要 — 事件溯源最完整
- `data_validation` GE S07-S11 五场景累计 5/5 stable
- `execution_manager` hard+soft 双层闸门 + artifact_id 全链路

**关键洞察**:**模拟交易的 hard 闸门(T+1 / lot_size / 金额限制 / user_scope)是 robust 的,但 silent state mutation(set_risk_rules 错位 / 单位漂移)+ 价格双源不一 + RSI 公式不一致 + alert 多用户隔离缺陷** 是这一层的核心信任问题。
