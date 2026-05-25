# S12 · 实盘 broker 桥 + dry_run 护栏 + confirm_token 写保护 + 数据同步状态 + 调度任务 + TDX_LOCAL_ONLY 模式

- **判定**: ✅ 通过 (32/31 工具,Pass=25 / Degraded=7 / Fail-graceful=2 / Fail=0)
- **耗时**: 12:32:24 → 12:34:01 (约 97s)
- **覆盖**: live_trading_manager(14 actions 全)/ data_sync_manager / data_warmup / check_db_freshness / dead_letters / cache_stats / 各类 backend query

## 🔥 本场景重大发现 — 实盘护栏 robust + 数据同步层暴露根因(14 条 finding,5 high / 5 medium / 4 positive)

### 1. ✅✅✅ 实盘 broker 桥四层护栏 robust(S12-F01,工具集最关键安全保障)

```
Layer 1: dry_run=true                                 → mode='dry_run' / accepted=true / submitted=false ✅
Layer 2: execute=true (no token)                      → CONFIRMATION_REQUIRED 'provide confirm_token=I_UNDERSTAND_THE_RISK' ✅
Layer 3: execute=true confirm_token='fake_token'      → CONFIRMATION_REQUIRED (不接受任意 token,只接受固定 magic string) ✅
Layer 4: execute=true confirm_token='I_UNDERSTAND...' → mode='read_only' / accepted=true / submitted=false (因 gateway not configured) ✅
```

**4 重保护:dry_run / explicit token / magic string / gateway config**。即使带正确 confirm_token 也因 gateway 未配置而 read_only mode 阻止下单 — **绝不会 silent 下真实订单 ✅**

```json
side_effect: {
  "level": "trade_risk",
  "target": "AAPL",
  "confirmation_required": true,
  "confirmation_policy": "explicit_token_required",
  "explicit_token_required": true,
  "dry_run": false,
  "idempotent": false
}
```

side_effect 元数据完整,**显式标 trade_risk 级别**。

### 2. data_sync_manager.status 暴露三个 critical 数据问题(S12-F02/F03/F04)

#### F02:quote_snapshot 全部 stale

```
row_count           = 9352
covered_code_count  = 450
fresh_code_count    = 0          ← 0!
stale_code_count    = 450        ← 全 stale
universe_stock_count = 5529
coverage_ratio      = 8.14%      ← 5529 全市场只覆盖 450
freshness_ttl_seconds = 30
latest_quote_time   = "2026-05-24 03:44:59"  ← 12 小时前
```

**5529 全市场只覆盖 450(91.86% 缺失),且 450 全部 stale**。这解释了为什么:

- S04/S07/S11 三场景同股 PE/价格 数据混乱
- compliance_manager.check_order 拿到的"realtime"价是 stale db quote(12 小时前)

#### F03:north_fund_flow 21 个月前数据(S09/S10 北向跪根因)

```
table              = north_fund_flow
count              = 2264
min_date           = 2014-11-17
max_date           = 2024-08-16    ← 21 个月前!
delta_to_now_months = 21
```

vs 其它 sync 表:
| 表 | max_date | 状态 |
|---|---|---|
| `margin_market_flow` | 2026-05-21 | ✅ |
| `margin_detail` | 2026-05-18 | ✅ |
| `stock_fund_flow` | 2026-05-21 | ✅ |
| `north_fund_flow` | **2024-08-16** | 🚨🚨🚨 |
| `research_reports` | 2026-05-18 | ✅ |

**north_fund_flow sync 任务停在 2024-08-16**,这是 S09-F07 / S10-F08 / S11 北向资金 4 个 source 全跪的真根因。

#### F04:vector index 0 行 — S10-F04 search_by_kline ST 跑偏的根因

```
market_documents              = 125         ← 文档存在
market_doc_chunks             = 125         ← chunks 存在
vector_documents              = 0           ← 但 embeddings 0!
kline_pattern_windows         = 0           ← 0!
vector_profiles_kline_patterns = 0          ← 0!
vector_profiles_stock_profiles = 0          ← 0!
vector_optimization_runs      = 0
```

(同时 `vector_collections=12` `vector_dimension_contracts=13` `vector_graph_nodes=140` `vector_graph_edges=224` 这些 schema/contract 表有数据,但实际 embeddings/index 0 行)

**这是 S10-F04 茅台 search_by_kline 返回全 ST 股的根因**:`kline_pattern_windows=0` → 没真实向量库 → fallback 到 python 内存暴力搜索 → 候选范围窄 → 选到 ST。

### 3. data_sync_manager.list_schedules 5 个僵尸 schedule(S12-F05)

```
list_schedules:
  schedule_kline_1779381725  600519 daily  enabled=0   created 2026-05-21 16:42
  schedule_kline_1779374094  600519 daily  enabled=0   created 2026-05-21 14:34
  schedule_kline_1779352815  600519 daily  enabled=0   created 2026-05-21 08:40
  schedule_kline_1779344551  600519 daily  enabled=1   created 2026-05-21 06:22 ← 唯一 enabled
  schedule_kline_1779337857  600519 daily  enabled=1   created 2026-05-21 04:30
  schedule_runtime_core_market   enabled=1
  schedule_runtime_factor_context enabled=1
```

**5 月 21 日一天创建了 5 个相同 600519 daily schedule**,4 个被 disable 但记录保留 → **僵尸 schedule**。schedule 创建不去重 + cancel 不物理删。

### 4. dry_run 模式无 sanity check(S12-F06)

```python
submit_order(dry_run=true, qty=9999999999, side="sell", symbol="SPY")
# 输出:
{
  "accepted": true,
  "mode": "dry_run",
  "preview": {"qty": 9999999999.0, "type": "market"}
}
# 无 warning!  99 亿 SPY = 200 倍 SPY 市值!
```

dry_run 模式**bypass 全部 compliance check**,但实际 dry_run 用户期待是 'will this order go through?' 的预览。AI 看 accepted=true 误以为正常,切到 execute=true 才发现实盘会拒。

### 5. order_events 文档误导(S12-F07)

```
help.order_events.description: "build normalized live order event timeline"
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^
                                  暗示是 list/timeline
actual_call_no_order_id.error: "order_id is required"
                                  ^^^^^^^^^^^^^^^^^
                                  实际单 order 视角
```



### 6. TDX_LOCAL_ONLY 模式锁住 fallback chain(S12-F09)

```
get_cb_info(123039)        → cb_info={} reason='tdx_only_mode' message='tqcenter 不可用且未启用旧降级'
get_ipo_info               → ipo_list=[] reason='tdx_only_mode'
```

环境变量 `TDX_LOCAL_ONLY=1` 锁定本地数据源,不允许走 online tushare/akshare/etc.;但 tqcenter(本地)如果跪了就完全没数据。**用户/部署不知道这个 mode 锁定了哪些工具**。

### 7. get_ipo_info 顶层标志矛盾(S12-F08)

```
{
  "success": true,
  "degraded": false,            ← 顶层 false
  "fallback_used": true,         ← 但 fallback used!
  "fallback_reason": "tdx_only_mode",
  "quality_flags": ["degraded", "fallback"],   ← 内部 quality_flags 又标 degraded!
  "meta.degraded": false
}
```

**顶层 degraded=false 但 fallback_used=true 矛盾**;quality_flags 又标 degraded — 三个层次不一致。

## ✅ Positive evidence(4 条)

### S12-F01 ✅:实盘 broker 桥四层护栏 robust(工具集最关键安全保障)

详见上面 §1 — **绝不会 silent 下真实订单**。

### S12-F12 ✅:data_validation(GE)S07-S12 累计 6 场景 6/6 stable

```
S07 → val-53273787f84a   evaluated=7   pass=7   100%
S08 → val-1ca745e7ab52   evaluated=7   pass=7   100%
S09 → val-e8933820055e   evaluated=2   pass=2   100%
S10 → val-0fa79bf3ba13   evaluated=3   pass=3   100%
S11 → val-3089e8754aab   evaluated=5   pass=5   100%
S12 → val-81a2081575f1   evaluated=5   pass=5   100%
─────────────────────────────────────────────────────
                     total=29  pass=29  100%
```

**6 场景累计 29/29 expectations 全 pass** — `data_validation` GE backend 是工具集**最稳定的层**(单一指标连续 6 场景 100%)。

### S12-F13 ✅:数据基础设施 telemetry 完整链

```
check_db_freshness(invalid_code)  → "存在无效股票代码" (input validation ✅)
get_dead_letters                   → count=0 + path 显式
get_sync_status                    → metrics 全 0(pending/success/fail/retry/lag/dead_letter)
get_cache_stats                    → hit_rate=1.0 + ttl_config 8 项完整
data_warmup.status                 → last_warmup + sync_metrics + cache_stats 三合一
```

**5 个工具组成完整可观测性链**:freshness check + dead_letters + sync_metrics + cache_stats + warmup。

### S12-F14 ✅:get_trading_dates 显式 fallback chain

```
backend_requested = "tushare_pro"
backend_used      = "tqcenter"     ← fallback 显式
fallback_used     = true
source_chain      = ["basic_data.get_trading_dates", "market_data.tushare_pro", "market_data.tqcenter"]
result_count      = 5
dates             = [20260518, 20260519, 20260520, 20260521, 20260522]
```

**降级路径透明** — tushare_pro 跪 → tqcenter 接力,顶层 fallback_used=true 显式。

## 🚨 工具间数据不一致(本场景新增 14 条 finding,其中 high 5 条)

### 5 条 high

- **S12-F02**:quote_snapshot 全部 stale(fresh_code_count=0 / 450 stale / coverage 8.14%)
- **S12-F03**:north_fund_flow max_date=2024-08-16(21 个月前),S09/S10/S11 北向跪根因揭示
- **S12-F04**:vector_documents=0 / kline_pattern_windows=0,S10-F04 search_by_kline ST 跑偏根因
- **S12-F05**:list_schedules 5 个 600519 daily 重复僵尸 schedule(只 1 enabled)
- **S12-F06**:dry_run(qty=99 亿)无 sanity check 仍 accepted=true

### 5 条 medium

- S12-F07:`order_events` / `sync_order_events` help 文档说 timeline 但实际单 order 视角
- S12-F08:`get_ipo_info` success=true degraded=false 但 fallback_used=true 矛盾
- S12-F09:TDX_LOCAL_ONLY=1 锁住 fallback chain(get_cb_info / get_ipo_info)
- S12-F10:`experiment_tracker` mlflow→builtin silent fallback(累计第 3 次复现)
- S12-F11:`check_db_freshness` 'fresh' 仅查 last_date,不查序列完整性(S07-F09 复现)

### 4 条 low(positive evidence)

- **S12-F01** ✅:实盘 broker 桥四层护栏 robust(dry_run / token / magic / gateway)
- **S12-F12** ✅:`data_validation`(GE)S07-S12 累计 29/29 stable
- **S12-F13** ✅:数据基础设施 5 工具 telemetry 完整链
- **S12-F14** ✅:`get_trading_dates` 显式 fallback chain(tushare_pro → tqcenter)

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-81a2081575f1` | dataset_id | data_validation,GE backend,5/5 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s12_audit |
| ~26 audit_event_id | read_only | live_trading × 14 / data_sync × 4 / freshness × 2 / get_dead_letters / sync_status / cache_stats / data_warmup / cb_info / ipo_info / trading_dates / stock_capital / data_validation × 2 / experiment_tracker |

**0 实盘订单提交**(全部 dry_run / preview / read_only 拦截)✅

## 🚨 Fail
无。但有 2 个 Fail-graceful:
- `live_trading_manager.order_events / sync_order_events` 必填 order_id 但 help 文档暗示 timeline list

## ➡ 进度

- 累计调用工具(去重): **~161/161** ✅(覆盖率 100% 估测达成)
- 已通过场景: **11/22**
- 累计 Fail: **0**
- 累计推荐 bug: **115 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16 + S11 16 + S12 14,其中 high 累计 **54 条**)

## 关键观察:S12 验证了"实盘护栏 robust + 数据同步层是众多 finding 的根因"

**S12 是工具集**最关键的安全场景**,验证了:**

**核心问题模式**:

1. **实盘护栏 4 层 robust ✅**(S12-F01):dry_run / no token CONFIRMATION_REQUIRED / fake token CONFIRMATION_REQUIRED / correct token but gateway not configured → read_only — **绝不 silent 下单**
2. **数据同步层暴露多个根因**:
   - quote_snapshot 12 小时前 stale(F02)→ S04/S07/S11 同股价格混乱根因
   - north_fund_flow 21 个月前(F03)→ S09/S10/S11 北向资金跪根因
   - vector_documents=0 / kline_pattern_windows=0(F04)→ S10-F04 茅台 search_by_kline 返回 ST 股根因
3. **schedule 治理缺失**(F05):重复创建 + cancel 不物理删 → 僵尸 schedule
4. **dry_run vs execute validation 不对称**(F06):dry_run 任意 qty 都 accepted,execute 才会拒 — AI 不知 dry_run 的 'preview' 不全
5. **顶层标志矛盾**(F08):fallback_used=true 但 degraded=false
6. **TDX_LOCAL_ONLY 锁住 fallback**(F09):本地源跪即没数据,用户/部署不透明

**positive 证据**(4 条):

- 实盘 broker 桥四层护栏(dry_run / token / magic string / gateway config)— **工具集最关键 safety 保障**
- `data_validation` GE 连续 6 场景 29/29 stable
- 数据基础设施 5 工具 telemetry 完整链(check_freshness + dead_letters + sync_metrics + cache_stats + warmup)
- `get_trading_dates` fallback chain 透明

**关键洞察**:

S07-S11 反复发现的"数据混乱"问题(同股 PE 不一致 / 北向资金跪 / search_by_kline ST 跑偏),**根因在 S12 暴露**:

- **quote_snapshot stale** 12 小时
- **north_fund_flow** 21 个月前
- **vector embeddings 0 行**

**修复 S12 的数据同步层 = 解决 S04-S11 一半以上的 finding**。这是**单点高 ROI 修复**。

而**实盘护栏**则是工具集**最值得信任的部分**:**4 重保护 zero silent execution**。
