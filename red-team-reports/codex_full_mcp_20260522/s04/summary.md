# S04 · 白酒龙头利润质量与估值陷阱

- **判定**: ✅ 通过 (32/32 工具,Pass=22 / Degraded=10 / Fail=0)
- **耗时**: 11:25:30 → 11:28:50 (约 200s)

## 🔥 本场景重大发现 — 估值通道大冲突(伪精度陷阱被精确激活)

### 1. 同股内在价值四个工具差 9.5 倍

| 来源 | 茅台总市值/总价值 | 折溢价 |
|---|---|---|
| 当前市价 | **¥1.61 万亿**(¥1290.20 × 12.52 亿股) | 锚 |
| `ddm_valuation`(g=6%, ke=10%) | ¥1.19 万亿 = 每股 ¥954 | -26% |
| `dcf_valuation`(g=8%, dr=10%) | ¥1.03 万亿 = 每股 ¥825 | -36% |
| `scenario_dcf_valuation`(消费模板) | **¥1262 亿 = 每股 ¥100.74** | **-92%** |

`scenario_dcf` 用消费模板套 profit_margin=14%、growth=10%——而茅台**实际净利率 50%、ROE 10%、毛利率 89.76%**,模板严重低估护城河。

### 2. relative_valuation 同股给出相反结论

- **PE**:target 19.91 < 行业均 46.43 → 折价 57%(`risk_flag="high_discount"`)→ "极度被低估"
- **PB**:target 6.07 > 行业均 1.99 → 溢价 205%(`risk_flag="high_premium"`)→ "极度被高估"

茅台 ROE 远高于同行,但 BPS 不到行业 1/3,所以 PE 极低 / PB 极高——**真实的财务结构信号**,但工具没合并成"PE-PB 反向是 ROE 主导特征"的解释。

### 3. 研报全多头 + 0 目标价 + 股价 60 天 -13%

近 90 天仅 2 篇研报(华鑫买入 + 万联增持),**100% bullish + 0 个目标价**;同期茅台从约 ¥1490 → ¥1290,跌 13%。**评级与价格严重背离**,这是估值陷阱核心特征。

### 4. 两融加杠杆抄底被套

| 日期 | margin_balance | 茅台收盘 |
|---|---|---|
| 5/6 | ¥18.33 亿 | ¥1373 |
| 5/18 | ¥19.42 亿(+5.9%) | ¥1290(-6%) |

杠杆资金在持续加仓接住下跌,但价格仍下行。**真实"散户接盘"信号**。

## 🚨 工具间数据不一致(本场景新增 4 条 high 级 finding)

### S04-F03 — `decision_manager.analyze` PE/PB 取不到,但其它工具能取

```
decision_manager.fundamental.pe_ratio = null
decision_manager.data_quality.missing_fields = ["pe_ratio","pb_ratio"]
decision_manager.score_penalty = 8.0  ← 因为这个扣分推 sell

get_valuation_metrics.pe_ratio = 19.91  ← 同时刻同 db.stocks
build_stock_context.valuation.pe = 19.91
```

`decision_manager` 内部估值取数路径与同时段其他工具不对齐,导致 raw_total 41 → final 33 推 sell。

### S04-F04 — `research_manager.get_reports` vs 4 个研报工具不一致

```
research_manager.get_reports(600519) = count 0 "暂无研报"

get_research_reports = 2 篇 (华鑫 + 万联)
analyze_research_report = 2 篇
search_research_db = 2 篇
get_research_summary = 2 篇
```

5 个工具读同一份 `research.db`,只有 `research_manager` 路径漏看了。这是 manager 调底层服务时绕开了 `db.research_reports`。

### 其它 high 发现

- S04-F01:估值三模型差 9.5x,缺 cross-model reconciliation
- S04-F02:`relative_valuation` PE 折价 + PB 溢价反向结论,缺合并解释

## 🎯 决策 + 护栏链路完整闭环

| 工具 | 关键事实 |
|---|---|
| `should_i_buy(600519, conservative)` | `recommendation="avoid"`,score 40,**buy_probability 5.57%**,7 条证据,calibration_gap -0.27,brier 0.073(quality 自标 low) |
| `should_i_sell(600519, buy=1500, days=90)` | **`recommendation="sell"`**,亏 14%(-209.8),已跌破 ATR 止损 1458.4,score 45 |
| `run_decision_gate(600519, conservative)` | `blocked=true`(同 S02),`position_cap_pct=0.1`(conservative vs balanced 0.2),compliance 触发 |
| `decision_manager.analyze` | `recommendation="sell"`,score 33(被 PE/PB 缺失扣 8 分,见 S04-F03) |

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s04_valuation_paradox` | dataset | data_validation read_only,GX 4/4 passed,validation_id `val-c2192389e58e` |
| `audit:data_validation:validate:1779593326363:8a4039d4` | audit_event_id | |
| `log_recommendation_audit` | **persist** | user_id=codex_full_mcp_20260522 / strategy_id=codex_full_mcp_20260522_s04_audit / 跨进程持久,**清理需查 audit table** |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **88/161** (S01 33 + S02 +24 + S03 +12 + S04 +19)
- 已通过场景: **4/22**
- 累计 Fail: **0**
- 累计推荐 bug: **14 条**(S02 3 + S03 5 + S04 6,其中 S04 出 4 条 high)

## 关键观察:Bug 找到的越来越深

S01-S03 主要是数据源/契约层不一致,**S04 开始触及决策与估值的语义层不一致**。一个标的同时让 DCF 给 ¥825、scenario_DCF 给 ¥101、PE 给折价 57%、PB 给溢价 205% — 这是教科书级的估值陷阱,但工具自身没合并这些矛盾信号给 AI。
