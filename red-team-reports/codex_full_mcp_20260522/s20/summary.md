# S20 · 工作流 / AI 技能 / 产业链 / 板块 / 主题事件驱动

- **判定**: ✅ 通过 (31/31 工具,Pass=12 / Degraded=12 / Fail-graceful=7 / Fail=0)
- **耗时**: 17:04:44 → 17:06:18 (约 1 分 34 秒)
- **覆盖**: list_skills(36 skills 含 21 executable + 15 no_handler)/ search_skills / run_skill(akshare-market smoke 4-step)/ industry_chain × 2 / sector_manager × 2 / market_insight × 1 / event_manager × 1 / macro_manager × 2 / get_market_blocks / get_block_stocks / fear_greed / market_sentiment_context / search_similar / search_by_kline / semantic_search / concept_fund_flow / dragon_tiger / market_news / calculate_factor / data_validation / log_audit

## 🔥 6 条 high finding

### 1. 36 skills 中 15 个未实装 handler(execution_gap)(S20-F01)

```
total_count: 36
executable_count: 21       (来自 runtime_contract)
registered_only_count: 15  (execution_mode=no_handler)
executor_coverage_ratio: 0.5833    ← 41.7% 技能未实装

未实装 15 个:
  - aiask-agent-{integrations-gateway,memory,native-tools,runtime}
  - aiask-akshare-{manager-plane,mcp-data,research-analytics}
  - aiask-{desktop-workbench,factor-mining-factory,finance-mcp-servers,
           incubation-factory,repo-orientation,strategy-factory}
  - gh-{address-comments,fix-ci}

backend_requested: skills_registry
backend_used: codex_registry
fallback_used: true
fallback_reason: "skills_registry_unavailable"
```

**主 skills_registry 不可用 fallback 到 codex 文件**;且 41.7% 技能 register 但无 handler。

### 2. macro_manager 指数名称 GBK 乱码(S20-F02)

```
sh000001:  上证指数  (4112.9)         ← 正常
sz399001:  ????      (null)           ← GBK→UTF-8 乱码!
sz399006:  ????      (null)           ← GBK→UTF-8 乱码!
```

**深证成指/创业板指中文名 4 个 ? 替代** — 编码层 bug;value 也 null。

### 3. market_insight_manager 上证 K 线 unavailable(S20-F03)

```
analysisMode: "quote_fallback"
quality_flags:
  - index_quote_degraded
  - index_kline_degraded
  - index_kline_unavailable     ← K 线全部不可用
fallback_reason:
  - "eastmoney_index_single returned empty"
  - "所有数据源均无法获取指数 000001 的K线数据"

ma5/ma20/ma60 都用 currentPrice=4112.9 填充       ← MA 全相同
support=4067.75 resistance=4120.09 都来自 quote 当日 high/low
```

**指数 K 线全跪 → ma5/ma20/ma60 fallback 到当日 quote** = 假 MA 失真 ✅(分析模式标 quote_fallback)。

### 4. get_market_sentiment_context 上证 close=10.68(应为 4112.9)(S20-F04)

```
index_context:
  code: sh000001
  close: 10.68         ← 上证指数怎么 10.68!
  change_5d_pct: -2.82
  change_20d_pct: -3.61

vs.macro_manager.market_overview.sh000001.value: 4112.9
vs.market_insight_manager.currentPrice: 4112.9
```

**上证 close=10.68 vs 4112.9 差 385 倍** — 同概念两工具值差极大;可能用了某 stock 的 close 而非指数。

### 5. 多源资金流全瘫(S20-F05)

```
get_concept_fund_flow:
  data: []
  fallback_reason: "HTTPSConnectionPool ProxyError ... eastmoney/push2"

get_dragon_tiger(2026-05-22):
  data: []
  fallback_chain: [sina, eastmoney]  全 provider_unavailable
  freshness_sla: failed (age 234378s vs max 86400s)

get_market_sentiment_context.northbound_flow_{1d,3d,5d}: null
margin_balance_latest: 0.0(但 5/18 历史显示 1462亿)
```

**concept fund / dragon_tiger / northbound 全跪**(同 S18-F03 北向链路全瘫复现 + 进一步扩展);但 margin 的 5/18 之前历史正常 → 数据写入断点。

### 6. search_by_kline 返回 4 个 *ST 退市股(S20-F06)

```
search_by_kline(600519 茅台, 20d):
  results × 5:
    - *ST莫高     similarity=0.5753
    - *ST西发     similarity=0.5197
    - *ST尼雅     similarity=0.5165
    - *ST岩石     similarity=0.4996
    - 古越龙山    similarity=0.4918
```

**4/5 全是 *ST 退市股** — K 线相似度无视 ST 风险/质量过滤;AI 调用看 5 个相似茅台 K 线的股票拿到全是 *ST 股。

## ✅ 4 positive

### S20-F12 ✅:run_skill(akshare-market, smoke_test)4 步全 OK

```
4 steps × 4 success:
  - get_realtime_quote:  600519 PE=19.53 PB=5.96 ✅
  - get_kline:            30 bars (4/8 - 5/22)
  - get_minute_kline:     30 bars 5m (5/22)
  - get_order_book:       depth_degraded=true ✅(graceful)

execution_mode: orchestrated
total_steps: 4
success_count: 4
failed_count: 0
latency_ms: 24105
```

**skill orchestrator 编排 4 步骤全成功 ✅**(虽然其中 3 个内部 degraded)。

### S20-F13 ✅:semantic_stock_search 三层匹配完整

```
query: "白酒龙头"
results × 3:
  - 600519 贵州茅台   PE=19.91 PB=6.07 score=2.05  match=[industry, industry_context, sector_seed]
  - 000858 五粮液     PE=26.33 PB=2.60 score=2.05  match=[industry, industry_context, sector_seed]
  - 002304 洋河股份   PE=66.53 PB=1.38 score=2.05  match=[industry, industry_context, sector_seed]
```

**3 层 match(industry/industry_context/sector_seed)+ score=2.05 一致** = 关键词 → 行业映射 → 股票完整匹配 ✅。

### S20-F14 ✅:sector_rotation 30d + industry_chain 三段

```
sector_rotation(30d):
  strong: 玻璃玻纤+27.82% / 仪器仪表+22.25% / 电池+20.22%
  weak:   农产品加工-14.14% / 次新股-7.64% / 银行-7.28%
  market_style: growth
  rotation_advice 完整(10 sectors overweight/underweight)

industry_chain(新能源汽车):
  upstream:   002460 / 300750 / 603799
  midstream:  300750 / 002594 / 002129
  downstream: 002594 / 600104 / 300750

calculate_fear_greed_index = 47 (neutral)
  components: momentum 43 / volatility 56 / volume 44 / breadth 45
```

✅ 板块轮动 + 产业链三段 + 恐贪指数 4 components 都 robust。

### S20-F15 ✅:data_validation 累计 13 场景 66/66 stable

```
S07-S19: 62/62  +  S20: 4/4
─────────────────────────
                total: 66/66  100%
```

## 🔬 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-eee446b5e3fb` | dataset_id | data_validation 4/4 |
| `log_audit` | persist | strategy_id=codex_full_mcp_20260522_s20_workflow_audit |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **20/22**
- 累计 Fail: **0**
- 累计推荐 bug: **229 条**(S02-S19 累计 214 + S20 新增 15,其中 high 累计 **104 条**)

## 关键观察:S20 验证了"工作流 + 板块 + 主题层完整性参差"

**核心问题**:

1. **41.7% skill execution_gap**(F01):aiask 自身 skill 全部未实装 handler
2. **指数 GBK 乱码**(F02):深证成指/创业板指 name 全 ????
3. **上证 close 10.68 vs 4112.9 差 385 倍**(F04):同概念两工具数据完全不一
4. **K 线索引 unavailable + concept_fund/dragon_tiger 全跪**(F03/F05)
5. **search_by_kline 返回 *ST 退市股**(F06):无质量过滤

**positive 证据**:
- run_skill orchestrator 4 步骤编排成功(F12)
- semantic_stock_search 3 层匹配完整(F13)
- sector_rotation 30d + industry_chain + fear_greed 完整(F14)
- data_validation 累计 13 场景 66/66 stable(F15)

**累计 20/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计 bug 229(其中 high 104),22 场景红队复测剩 2 场景(S21-S22)。
