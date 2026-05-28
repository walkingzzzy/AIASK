# S18 · 数据同步任务/dead-letter

- **判定**: ✅ 通过 (Pass=3 / Degraded=0 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_dead_letters(limit=10)` | ✅ Pass | count=0 records=[] path=`.mcp_cache/dead_letters/kline_save_failures.jsonl`,无失败落盘记录 |
| `get_sync_status()` | ✅ Pass | metrics 完整(pending=0/success=2/fail=0/retry=0/lag=0.0/dead_letter=0),source_chain=[data_sync.status] |
| `data_sync_manager(list_tasks)` | ✅ Pass | 20 个任务历史,最近 1 个 running(sync_core_market_1779760720),18 个 completed,1 个 failed(2026-05-23 sync_factor_context error_message="factor_context_timeout_after_45s") |

## v1 → v2 Delta
- ✅ get_dead_letters / get_sync_status / data_sync_manager.list_tasks 三件套 envelope 完整
- ✅ 失败任务 error_message 完整记录(factor_context_timeout_after_45s)便于审计
- ✅ kline_save_failures.jsonl 默认无失败落盘(系统健康)
