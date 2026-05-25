# S02 · 开盘前多源行情冲突与指数身份污染

- **判定**: ✅ 通过 (32/32 工具,Pass=12 / Degraded=20 / Fail=0)
- **耗时**: 11:17:57 → 11:19:30 (约 93s)

## 🎯 攻击点验证

### 1. 指数 / 股票同码 `000001`身份解析(关键测试)

| 工具 | 视为 | 数据 | 结论 |
|---|---|---|---|
| `get_index_quote("000001")` | **上证指数** | price/open/high/low **全部 null**,name `"????"` | 工具识别正确,但 3 条降级链(eastmoney/sina/tushare)全跪 → **Degraded** |
| `get_realtime_quote("000001")` | **平安银行** | 10.68 / -0.19% / PE 4.81 / PB 0.45 | 走股票通道,数据正常 |
| `get_kline("000001")` | **平安银行** | 5 日 daily 完整 | 走股票通道,正常 |
| `get_minute_kline("000001")` | **平安银行** | 5m × 10 段 sina 直拉 | fallback 但正常 |

**结论**:工具自身契约层面"指数 vs 股票"识别正确,身份未污染。`get_index_quote` 链路全跪是真实上游问题(tushare token 错+eastmoney 空+sina 失败),符合 Degraded。

### 2. 数据源冲突可观测

`get_batch_quotes(5 codes)` 内部混合了两条来源:
- 600519/000001 → `db.stock_quotes`(刚好新鲜,fallback_used=false)
- 000858/002304/510050 → `tqcenter`(db_snapshot_stale 触发 fallback)
- 顶层标 `degraded=true` 因"批中至少一只走 fallback",**契约一致**

### 3. 涨停板 + 日报互相矛盾(预期内)

- `get_limit_up_stocks("2026-05-22")` → `data=[]`, `source="none"`
- `get_limit_up_statistics("2026-05-22")` → 0/0/0/0,但能正常返回 schema
- `generate_daily_report("2026-05-22")` 内部:
  - 三大指数 close=0、volume=null
  - 但 hot_sectors 有真实数据("电力行业 +3.29%、半导体 +3.04%")
  - 同一份报告**内部三个数据通道不同步**,自带 `degraded=true` + `quality_flags: ["market_summary_zero_or_null_index_values"...]`
- 这是真实多源不一致,工具自身已经显式声明 → 符合 Degraded

### 4. 护栏链 — 合规 + 决策闸门连锁

`compliance_manager.check_order(000001 buy 100 @ 10.68)`:
- `blocked=true`, violations=["**实时盘口卖量为 0，当前疑似无法买入**"]
- 配套:limit_up=11.77 / limit_down=9.63 / top_ask_volume=0 / top_bid_volume=0
- warnings 提示 "当前时间不在交易时段内（仅提示，部分券商支持预委托）"

`run_decision_gate(000001, balanced)`:
- `blocked=true`, `veto_reason="indicative_order_blocked"`
- `blocking_flags=[{name:"compliance", severity:"high", source:"compliance_manager"}]`
- **闸门正确合并合规拒绝信号,不绕过**

## ⚠ 数据警告(Degraded 但符合契约)

| # | 工具 / 路径 | 现象 | 建议 |
|---|---|---|---|
| ① | `get_index_quote("000001")` | 全降级链 null;包含 `tushare_index_daily失败: 您的token不对` | tushare token 已显式失败,sina/eastmoney 都空。建议:**指数源直接全跪时返回 success=false,不要 success=true + price=null**,避免下游误以为价格是 0 |
| ② | `get_index_quote` name 字段 | `"????"` 编码乱码 | sina 返回的中文名编码降级时变成 `?`。建议在乱码检测时改用空串 |
| ③ | `build_stock_context("000001")` | **银行被关联成新能源产业链**。`industry_keyword="全国性银行"` + `matched=true` + `chain_id="new_energy"` | **疑似 bug**:`industry_chain_snapshot.matched=true` 但实际是关键词 fallback 返回全部预置链。`matched` 应当反映"关键词真命中" |
| ④ | `get_limit_up_stocks/statistics` | tushare/akshare 都空 → `[]` 但顶层 `success=true` | 周日预期。但建议加 `data_quality.fallback_reason` 显式说明"非交易日/无可用数据源" |
| ⑤ | `check_db_freshness(指数)` | 399001/399006/000300 全部 `missing` | 预期。指数 K 线没在我们日常 sync 列表里 |
| ⑥ | `get_market_blocks` | `source="db_stale"`,`fallback_reason="using stale db cache because live providers are unavailable"`,**multi_source_reconciliation.mismatch=true** | 已显式 quality_gate 标 degraded |
| ⑦ | `get_block_stocks(全国性银行)` | 5 只都 `price=0.0 changePercent=0.0` | 板块成分股查询时不带行情;预期 schema |

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s02_idx_conflict` | dataset_id | data_quality_workflow read-only,GX checkpoint=`codex_full_mcp_20260522_s02_idx_conflict_runtime_checkpoint`,validation_id=`val-310386ead97f` |
| `data_quality_workflow:1779592770913:06b68341` | run_id | read_only,自然回收 |
| 缓存 1 文件 0.0016MB | 由 get_minute_kline / get_kline_data 写入,可在场景结束时由 S12 清理 |

## 🚨 Fail
无。

## 🐛 推荐修复(非阻塞,留作后续 PR)

1. **`build_stock_context` 产业链关联误报**:`industry_chain.matched` 字段语义和实际不符;银行关联到新能源产业链是误导性数据。应在 `get_industry_chain` 没真匹配到时把 `matched=false` 且 `chains=[]`/或返回前 1 条但显式标 `matched=false`。
2. **`get_index_quote` 全降级链空时返回**:目前 `success=true` + `price=null` 容易把下游污染为 0。建议改为 `success=false` 且 `error_code=UPSTREAM_INDEX_UNAVAILABLE`。
3. **`get_index_quote.name` 编码乱码**:sina 中文名解码失败时存进了 `"????"`,应当过滤为空字符串。

## ➡ 进度对全局

- 累计调用工具(去重): **57/161** (S01 33 + S02 新增 24)
- 已通过场景: **2/22**
- 累计 Fail: **0**
- 累计推荐 bug 修复: 3 条(S02)
