# S05 · 白酒消费股事件流冲突 — 利好密集 vs 价格逆向

- **判定**: ✅ 通过 (35/31 工具,Pass=14 / Degraded=14 / Fail=0)
- **耗时**: 11:30:10 → 11:35:30 (约 320s)
- **标的**: 五粮液 (000858),收盘 ¥84.03 / -1.55% / 60d -19.4%

## 🔥 本场景重大发现 — 利好出尽 + 信号自相矛盾(高强度)

### 1. 事件链报 bullish/high,价格暴跌

| 维度 | 数据 |
|---|---|
| `build_event_context.event_direction` | **bullish** |
| `build_event_context.event_intensity` | **high** |
| `veto_candidates` | 8 条(回购+集团增持,5/22 集中发布) |
| `smart_stock_diagnosis.recommendation` | **sell** |
| 60 天动量 | **-19.4%** |
| RSI 14 | **13.59 极度超卖** |
| 最大回撤 | 36.81% |

### 2. OOS 验证显示 bullish 标签是反向信号

`analyze_stock_sentiment` 内部跑了 OOS 验证:

| 持有期 | bullish 标签命中率 |
|---|---|
| 5 天 | 12.5% |
| 10 天 | **0%** |
| 20 天 | **0%** |
| `alpha_5d_bull_vs_bear` | **-0.0244**(反向 alpha) |
| `signal_reverses_on_longer_horizon` | **true** |

**工具内部已经知道 bullish 是反向预测,但 build_event_context 没用这个证据自我修正,仍然报 bullish high。**

### 3. 大宗交易 5/22 折价 -6.45% 与同日 8 条回购公告反向

```
2026-05-22 大宗交易 #5
  买方: 华泰证券股份有限公司 北京西三环北路营业部
  卖方: 中信证券股份有限公司 北京广通天路证券营业部
  数量: 80 万股 @ ¥83.05
  金额: ¥6644 万
  折价: -6.45% (vs 同日收盘 ¥88.78)
  --------
  同日有 8 条公告:回购进展 + 集团增持
```

机构在公布利好的同日折价出货 ¥6644 万——经典的"机构借利好出货"信号,但 `build_event_context` 只读 announcements,不读 block_trades。

### 4. 两融加杠杆抄底被套(5/6 → 5/21 +4.86%)

| 日期 | margin_balance |
|---|---|
| 5/6 | ¥58.69 亿 |
| 5/21 | ¥61.57 亿(+4.86%) |
| 期间股价 | ¥84-85 持平 |

杠杆资金在持续加仓但价格不涨,与茅台模式相同(S04 茅台 5/6→5/18 +5.9% 但跌 -6%)。

## 🚨 工具间数据不一致(本场景新增 7 条 finding,其中 4 条 high)

### S05-F01 (high):事件链 bullish 与价格 60d -19.4% 反向,缺 self_consistency_check

`build_event_context` 只看文本极性,不看 (a) 公告与价格的时间错位 (b) 大宗交易折价 (c) 资金流向。**利好出尽信号识别能力为 0**。

### S05-F02 (high):OOS hit_rate=0/0/12.5% 工具自己测出来了但不修正 event_intensity

`analyze_stock_sentiment` 知道 bullish 是反向信号,`build_event_context` 不知道。两个 tool 各自独立。

### S05-F04 (high):search_stocks/semantic_stock_search 中文名'五粮液'查询 = 0

```python
search_stocks(keyword='五粮液').count == 0
semantic_stock_search(query='五粮液').count == 0
hint = "建议尝试'白酒'或代码"
```

**搜索索引没建中文全名字段**——用户口语化输入"五粮液"三个字找不到股票。这是发现性的基础 bug。同 S03-F04 ETF 简称的问题。

### S05-F05 (medium):五粮液 6 个研报工具 + 1 个 profit_forecast = 全 0

```
get_research_reports/research_manager.get_reports/search_research_db
get_research_summary/analyze_research_report/get_stock_research
search_research/get_profit_forecast → 全部 count=0
```

vs S04 茅台 (5/5 个工具不一致,有的 2 篇有的 0 篇)。五粮液研报库 **完全空**——数据同步任务覆盖缺失。

### S05-F06 (medium):log_recommendation_audit action 枚举与 fuse_decision_payload 输出不一致

```
fuse_decision_payload.action = "watch"
log_recommendation_audit(action="watch") → "action 仅支持 buy/sell/hold"  ✗
log_recommendation_audit(action="hold")  → logged=true                    ✓
```

下游 audit 表枚举 = `buy/sell/hold`,上游决策枚举 = `buy/sell/hold/watch`。AI 直接转写第一次必失败。

### 其它 finding

- S05-F03 (medium):大宗交易折价 -6.45% 与同日回购利好反向,事件链未合并
- S05-F07 (low):`get_margin_data` quality_gate 期望 db.margin_detail 实得 akshare,reconciliation=warning

## 🎯 决策 + 护栏链路

| 工具 | 关键事实 |
|---|---|
| `build_event_context(000858)` | event_direction=**bullish** intensity=**high** 8 veto_candidates |
| `run_decision_gate(000858, balanced)` | **blocked=true** event_direction=bullish high (7 veto_candidates) |
| `fuse_decision_payload(000858, balanced)` | **action=watch** confidence=0.35 final_score=23.05 (stock 11 / quant 21 / event 58.75) veto_reason=indicative_order_blocked |
| `smart_stock_diagnosis(000858)` | **sell** 60d -19.4% RSI 13.59 ROE 6.30 max_dd 36.81 |
| `analyze_stock_sentiment(000858)` | score 46.02 neutral;**OOS bullish_hit=0/0/12.5%** signal_reverses=true |
| `log_recommendation_audit(action=hold)` | logged=true (action=watch 第一次被枚举校验拒绝) |

**关键观察**:`fuse_decision_payload` 把 event 拉到 58.75 但被 quant 21 拉下,最终 final_score=23 给 watch——这说明融合机制起了作用。但若 AI 单独消费 `build_event_context` 会被 bullish high 误导。

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `log_recommendation_audit` | **persist** | user_id=codex_full_mcp_20260522 / strategy_id=codex_full_mcp_20260522_s05_audit / action=hold (从 watch 降级) |
| 6 个 audit_event_id | read_only | research_manager / search_research_db / get_research_summary / analyze_research_report / comprehensive_manager / search_stocks |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **~100/161** (S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12)
- 已通过场景: **5/22**
- 累计 Fail: **0**
- 累计推荐 bug: **21 条**(S02 3 + S03 5 + S04 6 + S05 7,其中 high 累计 8 条)

## 关键观察:S05 触及"AI 决策的反向证据闭环缺失"

S04 暴露的是估值通道间不一致,**S05 暴露的是事件层与价格层、与历史 OOS 验证之间的反向证据没有合并机制**。

工具自己内部知道:
- bullish 标签历史命中率 0%/0%/12.5%(`analyze_stock_sentiment.OOS`)
- 价格 60 天 -19.4% / RSI 13.59 极度超卖(`smart_stock_diagnosis`)
- 大宗交易折价 -6.45%(`get_block_trades`)
- 两融加杠杆抄底被套(`get_margin_data`)

但 `build_event_context` 仍然单方面输出 bullish high,不接受这些反向证据。这是典型的**"消息面 AI 不看价格、价量 AI 不看消息面"**的孤岛模式。
