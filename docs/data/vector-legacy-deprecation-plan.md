# 向量层旧表退役计划（Vector Legacy Tables Deprecation）

> 起始日期：2026-05-18
> 维护原则：与 [PROJECT_AUDIT_REPORT.md §7.6](../../PROJECT_AUDIT_REPORT.md) 同源；任何新代码不得新增旧表写入。

---

## 1. 涉及表

| 旧表 | 角色 | 新表（统一向量层） |
|---|---|---|
| `stock_embeddings` | 个股向量画像 | `vector_profiles`（profile_type='stock_behavior'） |
| `pattern_vectors` | K线形态向量 | `vector_profiles`（profile_type='pattern'） + `kline_pattern_windows` |
| `vector_documents` | 市场文档向量 | `market_documents` + `market_doc_chunks`（FTS5 索引） |

旧表定义位置：[`_schema_market_phase_3.py:203, 209, 220`](../../packages/akshare-mcp/src/akshare_mcp/storage/sqlite/_schema_market_phase_3.py)。
新表定义位置：[`schema_vector.py`](../../packages/akshare-mcp/src/akshare_mcp/storage/sqlite/schema_vector.py)（统一向量层 schema）。

---

## 2. 当前调用方（PR-11 起带 deprecation log）

| 文件:行 | 行为 |
|---|---|
| `services/market_context.py:714-746` | 写入 `vector_documents`（双写：旧表 + 新表 `market_documents`） |
| `services/db_first_market_context.py:128-381` | 读取 `vector_documents` 用于市场上下文回灌 |
| `services/vector_backfill.py:120-423` | 写入时给 source 标 `vector_documents_legacy` |
| `tools/managers/_data_sync_manager_support_core.py:862-884` | 仅统计三张旧表 row count |
| `services/pattern_embedding_pipeline.py` | 写入 `pattern_vectors` |
| `services/pattern_recognition.py` | 读取 `pattern_vectors` |

每条写入路径在 PR-11 之后会 emit 一行 WARN：
```
[deprecation] writing to legacy vector table; migrate to vector_profiles by 2026-08-01
```

---

## 3. 时间线

| 阶段 | 日期 | 动作 |
|---|---|---|
| **T0** | 2026-05-18 | 本计划写入；写入路径加 deprecation 日志（PR-11） |
| **T1** | 2026-06-30 | 所有"双写"改为只写统一表；旧表降为只读 |
| **T2** | 2026-07-15 | 数据同步任务把旧表存量数据回填到 `vector_profiles / market_documents` |
| **T3** | 2026-08-01 | 旧表写入路径全部移除；只保留只读 fallback（30 天观察期） |
| **T4** | 2026-09-01 | 删除 `_schema_market_phase_3.py` 的旧表 CREATE 语句；删除 callers；写一个 `archive_legacy_vector_tables.py` 一次性脚本备份并 DROP TABLE |

---

## 4. 切换清单（PR 拆分）

每条都对应一个独立 PR，按顺序执行：

- [ ] PR-A：把 `services/market_context.py:714` 的双写改为只写 `market_documents`；保留旧表只读 fallback。
- [ ] PR-B：`services/db_first_market_context.py:128` 改读 `market_documents` 而不是 `vector_documents`。
- [ ] PR-C：`services/vector_backfill.py:120` 删除 source 标记，统一走新 schema。
- [ ] PR-D：`services/pattern_embedding_pipeline.py` 写入改为 `vector_profiles` (profile_type='pattern')；`pattern_recognition.py` 跟随读迁移。
- [ ] PR-E：`tools/managers/_data_sync_manager_support_core.py:862` 的统计加旧/新对比；预留 30 天观察。
- [ ] PR-F（T4）：编写 `archive_legacy_vector_tables.py`，导出旧表为 jsonl 后 DROP TABLE。

---

## 5. 监控建议

T1-T3 期间在 monitoring/grafana 配两个 panel：

1. `legacy_vector_writes_total{table=...}` — 来自 `logger.warning("[deprecation]...")` 的统计
2. `legacy_vector_row_count{table=...}` — 来自每日 `_data_sync_manager_support_core.py:862` 的 row count

任意 panel 在 T3（2026-08-01）之后仍 > 0 → 阻断 T4 删表。

---

## 6. 回退计划

如果 T4 之后某条数据丢失需要恢复：

1. 旧表的 jsonl 备份在 `data/archive/legacy_vector_tables_YYYYMMDD/` 目录（参见 PR-F 脚本）
2. `scripts/restore_legacy_vector_table.py <table>` 一键恢复（待 T3 时编写）
