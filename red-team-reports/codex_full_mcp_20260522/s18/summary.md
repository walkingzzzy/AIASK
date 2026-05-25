# S18 · 数据同步 / 缓存 / 死信 / 调度 / 时间精度护栏

- **判定**: ✅ 通过 (31/31 工具,Pass=14 / Degraded=11 / Fail-graceful=6 / Fail=0)
- **耗时**: 16:51:39 → 16:52:55 (约 76 秒)
- **覆盖**: data_sync_manager(8 actions:status/sync/get_task/list_tasks/list_schedules/cancel/run_due/help)/ data_warmup × 2 / get_dead_letters / get_cache_stats / get_trading_dates / sync_trading_calendar / sync_kline_data × 2 / batch_sync_klines / sync_stale_klines / check_db_freshness / get_kline_data / 实时(realtime × 2 / order_book / index / trade_details / minute_kline)+ ipo / cb / capital / north_fund / macro / data_validation / log_audit

## 🔥 5 条 high finding

### 1. 10 sync task 全空跑但标 completed(S18-F01)

```
list_tasks(limit=10):
  10 个 task 全部:
    codes:    "[\"[]\"]"        ← 无目标 stock
    progress:  0
    total:     0
    status:    "completed"     ← 但仍标完成!
  task_types:
    sync_core_market:    5
    sync_factor_context: 5
  time:  2026-05-23 09:08 → 2026-05-24 01:16(24h 内 6 次 pair)
```

**空任务标 completed**误导监控。schedule_runtime_core_market / factor_context 每天调度但 codes=[] 空跑。

### 2. quote_snapshot 覆盖率 8.14%(S18-F02)

```
quote_snapshot:
  row_count:           9353
  covered_code_count:   450     ← 仅覆盖 450 stocks
  fresh_code_count:       0     ← 0 fresh!
  stale_code_count:     450     ← 全 stale
  universe_stock_count: 5529
  coverage_ratio:        0.0814 ← 8.14% 全市场
  freshness_ttl_seconds:    30
```

**91.86% 全市场股票无 quote 缓存**。AI 调 batch_quotes/选股/组合 mark-to-market 严重依赖外部源 fallback。

### 3. 北向资金 4 源全跪 + 内部缓存 stale 21 月(S18-F03)

```
get_north_fund(5d):
  items: []           source: none
  sources_status:
    north_fund_flow:   stale          ← 内部缓存 max_date=2024-08-16 stale 21 月!
    tushare:           empty/bad_date
    hkex:              empty/bad_date
    eastmoney_direct:  empty/bad_date
```

**北向资金链路完全瘫痪**。build_stock_context.fund_flow_snapshot 全部填不出来。

### 4. get_order_book level-2 深度全 0(S18-F04)

```
get_order_book(600519):
  bids: [{price: 1290.2, volume: 0}]   ← volume=0!
  asks: [{price: 1290.2, volume: 0}]   ← volume=0!
  depth_degraded:        true          ← graceful 标 ✅
  depth_degraded_reason: "db_snapshot_has_quote_without_level2_depth"
```

**graceful 标了但 AI 看到 1 档 volume=0 无意义** — 流动性评分无法计算。

### 5. get_cb_info / get_macro_indicator 单源单点失败(S18-F05)

```
get_cb_info(123039):
  cb_info: {}
  source: "none"
  message: "tqcenter 不可用且未启用旧降级"
  fallback_reason: "tdx_only_mode"

get_macro_indicator(cpi):
  records: []
  fallback_reason: "provider unavailable: akshare.macro_china_cpi"
  multi_source_reconciliation.mismatch: true
```

**多源策略形同虚设** — 可转债走 tqcenter 单源,CPI 走 akshare 单源,任一源失效即全跪。

## ✅ 3 positive

### S18-F09 ✅:缓存温升验证成功

```
1st call: backend=tqcenter   fallback=true(db_snapshot_stale)
2nd call: backend=db.stock_quotes   fallback=false   freshness=0.447s
```

第 1 次 fallback 写回 db,第 2 次直接 cache hit — **温升机制正确**。

### S18-F10 ✅:死信队列空 + sync 100% 成功

```
sync_metrics:  pending=0  success=4  fail=0  retry=0  dead_letter=0  lag=0.001ms
cache:         hit_rate=80%
```

**底层管道整体 healthy**。

### S18-F11 ✅:data_validation 累计 11 场景 56/56

```
S07-S17:  49/49     S18:  7/7
─────────────────────────────────
            total: 56/56  100%
```

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-de18846f40ab` | dataset_id | data_validation 7/7 |
| `log_audit` | persist | strategy_id=codex_full_mcp_20260522_s18_data_sync_audit |
| `batch_sync_klines/sync_kline_data` | **persist** | 写 db 5 bars × 2 codes(从 API)|
| `data_warmup(warmup, 30d)` | **persist** | 写 30d × 2 codes(财务+kline 全量预热)|

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **18/22**
- 累计 Fail: **0**
- 累计推荐 bug: **199 条**(S02-S17 累计 188 + S18 新增 11,其中 high 累计 **92 条**)

## 关键观察:S18 验证了"数据基础设施层广泛碎裂 + 同步监控误标"

**核心问题模式**:

1. **sync 监控误标**(F01):空任务标 completed,24h 内 6 次空跑
2. **缓存覆盖率不足**(F02):quote_snapshot 8.14%,91% 股票每次 quote 都打外部源
3. **北向链路全瘫**(F03):4 源全跪 + 内部缓存 stale 21 月
4. **L2 深度数据缺失**(F04):order_book 1 档 volume=0
5. **多源策略失效**(F05):cb / macro 单源单点失败 — 优先级 chain 不真实跑

**positive 证据**:
- 缓存温升机制正确(F09)
- 死信队列空 + sync 100% 成功(F10)
- data_validation 11 场景 56/56(F11)

**关键洞察**:S18 暴露**数据基础设施分层质量极不均**:
- **底层管道**(sync metrics/dead_letters/cache hit_rate)→ healthy ✅
- **覆盖广度**(quote_snapshot 8.14%/北向 21 月 stale)→ severely degraded
- **多源 fallback**(cb/macro/north_fund 单源单点)→ formal 多源 / 实际单源
- **任务监控语义**(空任务标 completed)→ misleading

**累计 18/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计 bug 199(其中 high 92),22 场景红队复测剩 4 场景(S19-S22)。
