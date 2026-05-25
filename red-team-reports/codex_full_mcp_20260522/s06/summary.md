# S06 · 北向、两融、龙虎榜、大宗交易口径互斥 — 平安银行 000001

- **判定**: ✅ 通过 (32/31 工具,Pass=13 / Degraded=19 / Fail=0)
- **耗时**: 11:38:50 → 11:40:18 (约 90s)
- **标的**: 平安银行 000001,收盘 ¥10.68 / -0.19% / 60d -2.11% / RSI 30.55

## 🔥 本场景重大发现 — 资金面口径直接打架(8 条 finding,4 high)

### 1. 同标的两个决策工具结论相反(S06-F01)

| 工具 | recommendation | score | 依据 |
|---|---|---|---|
| `build_stock_context(000001)` | **sell** | **24.0** | 8 条 evidence (4 highlights / 4 risks),risks 包括 ROE 2.67/负债率 91/MA mixed/mom_20d 负 |
| `should_i_buy(000001, balanced)` | **hold** | **75.0** | 加权:valuation 45 + technical 40 + fundamental -10;buy_probability **64.05%** |

**Shared input**:PE 4.85 / PB 0.45 / RSI 30.55 / mom_60d -2.11% / ROE 2.67

`should_i_buy` 自标 `prediction_quality.quality="low"` calibration_gap=0.44 brier=0.194 (即模型自己说不准) — 但仍然给 hold/64% buy_prob。两工具看同一组数据,**评分映射完全不同 → 反向结论**。这是 S04-F03(decision_manager PE 缺失)之后**第二次发现的内部决策模型互斥**。

### 2. get_margin_data 全市场 schema 半残废(S06-F02)

```
5/21  marginBalance=0          totalBalance=0          marginBuy=99.33      ← 单字段
5/20  marginBalance=0          totalBalance=0          marginBuy=100.05     ← 单字段
5/19  marginBalance=0          totalBalance=0          marginBuy=101.23     ← 单字段
5/18  marginBalance=14622.77亿 totalBalance=14756.14亿 marginBuy=1409.33亿  ← 完整
5/15  marginBalance=28472.68亿 totalBalance=28675.49亿 marginBuy=3299.26亿  ← 但是 5/18 的 2 倍?!
```

前 3 日 schema 半残;后续 5/18→5/15 数值翻倍(可能是 unit conversion bug 或分库合并 bug)。**AI 看 5/21 数据会以为两融为 0,实际可能是 28万亿**。

### 3. get_margin_ranking sort_by 参数被忽略(S06-F03)

| sort_by | 返回前 5 |
|---|---|
| `balance` | 601318 / 688256 / 600519 / 600030 / 603986 |
| `change` | **完全相同** |
| `ratio` | **完全相同** |

`sort_by` 三种取值返回**完全一样的顺序** — 参数没传到 SQL ORDER BY。

### 4. 单位口径不一致 mkt_cap(S06-F04)

| 工具 | 601318 marketCap 字段值 | 推测单位 |
|---|---|---|
| `get_realtime_quote(601318)` | 5722.32 | 亿元 |
| `get_north_fund_top` 行 #10 | 28667655846.62 | 元 = 286.68 亿元 |
| `get_stock_info(000001)` | 209196000000.0 | 元 = 2091.96 亿元 |

`north_fund_top.marketCap` 实际是**北向持股市值**(不是总市值),但字段名和 tooltip 都叫 `marketCap`。三种单位混用。

### 5. 全市场龙虎榜 6+ 交易日全跪(S06-F05)

```
fallback_reason 12 条:
  sina:20260520:provider_unavailable
  eastmoney:20260520:provider_unavailable
  sina:20260519...
  ...
  eastmoney:20260515:provider_unavailable
data=[]
```

sina + eastmoney 两源同时 unavailable,无 db 备份链;但工具仍 success=true。

## 🎯 资金面交叉验证矩阵(平安银行 000001)

| 维度 | 数值 | 来源 |
|---|---|---|
| 北向持股 | 5.71 亿股 / 2.94% | `get_north_fund_holding` (季报 2026-03-31) |
| 两融余额 5/21 | ¥55.35 亿 (+4.76% from 5/6) | `get_margin_data` 30d |
| 主力净流入 | **¥0** super/large/middle/small 全 null | `get_stock_fund_flow` |
| 大宗交易 30d | **0 条** | `get_block_trades` |
| 龙虎榜 30d | **0 条** | `get_dragon_tiger` (但全市场也空) |
| 板块涨幅 5/22 | -0.89% (全国性银行) | `get_sector_fund_flow` |
| 个股涨幅 5/22 | -0.19% / 60d -2.11% | `get_realtime_quote` + `get_kline` |

**信号矛盾**:两融加杠杆(+4.76%) vs 股价小跌 vs 主力净流入=0 + 大宗交易=0 → **资金面没有明确方向,与五粮液(回购+增持但价跌)/茅台(评级买入但价跌)模式不同**。这次是真"沉睡股"。

## 🚨 工具间数据不一致(本场景新增 8 条 finding,其中 high 4 条)

### 4 条 high

- **S06-F01**:同标的两决策工具反向(build_stock_context=sell vs should_i_buy=hold)
- **S06-F02**:get_margin_data 全市场 schema 半残废 + unit explosion
- **S06-F03**:get_margin_ranking sort_by 参数被忽略(三种 sort 返回相同结果)
- **S06-F05**:全市场龙虎榜 6 交易日全跪

### 4 条 medium

- **S06-F04**:mkt_cap 单位不一致(三工具差 20 倍)
- **S06-F06**:data_validation GE silent pass(evaluated_expectations=0 时 passed=true)
- **S06-F07**:build_stock_context 银行→新能源产业链误关联(**S02-F01 复现**)
- **S06-F08**:get_stock_info 数值字段返空字符串(totalShares="" 但 raw.tdx_total_shares=19405918800)

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s06_capital_consistency` | dataset | data_validation,validation_id `val-c2e342d10f9b`,GE backend,**evaluated_expectations=0 silent pass** |
| `log_recommendation_audit` | **persist** | user_id=codex_full_mcp_20260522 / strategy_id=codex_full_mcp_20260522_s06_audit / action=hold |
| 6 个 audit_event_id | read_only | trading_data_manager 三种 action / calculate_technical_indicators / data_validation |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **~106/161** (S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6)
- 已通过场景: **6/22**
- 累计 Fail: **0**
- 累计推荐 bug: **29 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8,其中 high 累计 12 条)

## 关键观察:S06 暴露了"工具内部一致性"层面的问题

S04 找到决策路径不一致(decision_manager 取不到 PE/PB),S05 找到事件层不接受反向证据,**S06 找到 (a) 同标的两个决策工具直接给反向 recommendation,(b) sort 参数被忽略,(c) schema/unit 完全不统一**。

**核心问题模式**:
1. **决策模型互斥** — `build_stock_context` 和 `should_i_buy` 看同一组 evidence,但分别给 sell/hold,**没有 framework-level 的 score reconciliation**
2. **参数沉默忽略** — `sort_by` 不报错就直接走 default,**应该返回 unsupported_param warning**
3. **Unit 混用** — marketCap 在 3 个工具有 3 种单位,**应统一为元 + 字段语义 (total / holding / market_value)**
4. **Silent pass** — GE 空 suite 直接 passed=true,**数据校验工具最关键的反向 case 没覆盖**

这些都是 AI agent 在多 tool 协同链中**最隐蔽的"信任陷阱"**。
