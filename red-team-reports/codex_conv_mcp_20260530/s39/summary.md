# N39 · 缓存与 dead-letter（只读）

**工具**: get_cache_stats / get_sync_status / get_dead_letters
**调用**: 30 次 · **结论**: pass_with_high_finding
**护栏**: 全程只读，绝未调用 clear_cache/clear_dead_letters

## 覆盖
- get_cache_stats × 8（一致性）
- get_sync_status × 7（一致性）
- get_dead_letters × limit(0/1/2/3/4/5/6/7/8/10/20/50/100)

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N39-ROOT | **high** | **★★根因证据**：dead-letter 显示 000001 真实价 11 元 K 线被 `index_close_out_of_range: expected [1000,30000]; possible cross-symbol contamination` 拒绝入库——系统把 000001 当上证指数。这是 N34-F1/N36-F1/N38 的 000001↔sh000001 混淆 bug 的底层根因 |
| F-N39-1 | low | get_sync_status 两个 dead_letter 计数(metrics.dead_letter=5 vs dead_letters.count=1)不一致无说明 |
| F-N39-2 | low | get_cache_stats 字段在 data 与顶层冗余重复 |
| F-N39-3 | low | dead-letter 同一失败因重试重复写入 4 条 |

## 正向能力
- **★★★ dead-letter 提供根因证据**：cross_symbol_contamination 校验把平安银行 11 元当指数拒绝，校验机制本身是正向防御(拦截可疑数据并落盘可追溯)。
- **★★ 记录详尽可追溯**：kind/source/stock_code/failed_at/rejections(reason/date/code)。
- **★★ 只读幂等稳定**：cache_stats/sync_status/dead_letters 多次调用完全一致，无副作用。
- **★ limit 截断正确**，limit=0 边界校验报错，ttl_config 分级合理。
- 数据质量校验层主动拦截可疑数据是正向防御。

## standing caveat
全程只读未调用 clear_*；dead-letter 含 5 条 000001 写入失败记录(历史 run 残留)；cache 统计为进程累计。
