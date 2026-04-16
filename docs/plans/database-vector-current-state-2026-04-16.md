# 数据库与向量层当前实况

更新时间：2026-04-16（Asia/Shanghai）

## 目标

这份文档记录仓库当前已经落地、并且在本地 production-like 环境中实际存在的数据库与向量层实现，用于后续统一治理与兼容迁移。

## 运行拓扑

- BFF 持久化层：
  - 路径：`apps/bff/src/db/db.service.ts`
  - 连接方式：Node `pg` 连接池
  - 启动行为：自动执行 `apps/bff/migrations`
- MCP / 核心数据层：
  - 路径：`packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/`
  - 连接方式：`asyncpg`
  - 底座：TimescaleDB + PostgreSQL
  - 启动行为：按 market / strategy / vector schema 初始化
- 缓存层：
  - Redis 容器在线，用于 BFF / MCP 缓存与短期状态

## 本地运行实例

- PostgreSQL 数据库：`stockdb`
- TimescaleDB 容器：`akshare-timescaledb`
- Redis 容器：`aiask-redis`
- pgAdmin 容器：`akshare-pgadmin`
- 已启用扩展：
  - `timescaledb 2.25.2`
  - `vector 0.8.1`

## 实际表族与行数

### BFF / 应用表

- `app_schema_migrations`: `4`
- `app_users`: `15`
- `app_sessions`: `936`
- `audit_logs`: `110208`
- `unified_decision_diff_audit`: `7`

### 市场 / 基础数据

- `kline_1d`: `1045110`
- `stock_quotes`: `6164`
- `financials`: `9068`

### 策略 / 因子 / 调度

- `strategies`: `24`
- `strategy_factory_runs`: `32`
- `strategy_task_runs`: `2443`
- `strategy_generation_experiments`: `506`
- `daily_snapshot_history`: `32`
- `factor_values`: `18480`
- `factor_ic_history`: `69`
- `sync_tasks`: `246`
- `sync_schedules`: `5`

### 运行时 / 孵化

这些表结构已存在，但当前基本没有真实业务数据：

- `strategy_incubation_accounts`: `0`
- `strategy_incubation_metrics`: `0`
- `strategy_runtime_risk_events`: `0`
- `strategy_runtime_controls`: `0`
- `strategy_runtime_risk_snapshots`: `0`
- `strategy_runtime_alerts`: `0`
- `strategy_projection_snapshots`: `0`

## 向量层现状

### 统一向量层 `vector_*`

当前统一向量层已经是主要运行路径：

- `vector_profiles`: `6058`
- `vector_profile_store`: `6058`
- `vector_index_snapshots`: `11`
- `vector_index_items`: `436`
- `vector_index_item_store`: `436`

活跃 collection 示例：

- `market_doc_chunks`: `5389`
- `factor_candidate_embeddings`: `150`
- `stock_profile_embeddings`: `15`
- `kline_pattern_embeddings`: `10`
- `strategy_behavior_embeddings`: `66`
- `strategy_behavior_embeddings__text_embedding_3_small__d120__cosine__unit`: `224`
- `strategy_behavior_embeddings__text_embedding_3_small__d1536__cosine__unit`: `202`

### 兼容层 `strategy_vector_*`

旧策略向量表仍在库内，主要承担兼容与可观测职责：

- `strategy_vector_profiles`: `0`
- `strategy_vector_profile_store`: `0`
- `strategy_vector_index_items`: `0`
- `strategy_vector_index_item_store`: `0`
- `strategy_vector_index_snapshots`: `10`
- `vector_index_registry`: `5`

结论：统一层已经承载主要 profile / snapshot / item 数据，legacy 表主要留下历史快照与 registry 痕迹。

## 检索路径与实际行为

### 策略向量检索

- 统一层检索顺序：
  1. `vector_index_item_store` pgvector ANN
  2. `vector_profile_store` pgvector exact
  3. JSON exact scan
- 实测：
  - `factory_1774231662_b3d4b3e3` 相似搜索返回 `3` 条
  - `backend_used=pgvector`
  - `retrieval_mode=unified_pgvector_ann`
  - 无 fallback

### 市场文档检索

- `market_documents + market_doc_chunks` 已在统一向量层使用
- 仍保留 hybrid lexical + dense 语义
- 实测 `601318 + 派现` 可返回结果，但抽样结果里 dense score 可为空，说明：
  - lexical 路径正常
  - ANN snapshot 覆盖仍小于 raw chunk 归档覆盖

### K 线模式检索

- `kline_pattern_embeddings` 当前量级很低
- 实测 `search_by_kline(..., search_backend='db')` 可出现：
  - `backend_used=python`
  - `fallback_reason=db_empty_result`
- 当前应视为 degraded 路径，而不是稳定的 DB 向量检索能力

## 治理判断

- 统一向量层应作为 source of truth
- legacy `strategy_vector_*` 应保留只读兼容与历史清理能力，但不应再作为治理面主口径
- `vector_health`、`vector_profiles`、`vector_index_snapshots`、`vector_cleanup` 均应优先围绕统一层返回
- `vector_cleanup` 默认应先清理 unified 历史版本，再按需清理 legacy

## 当前仍存在的风险

- K 线向量集合覆盖不足，DB 检索经常回退
- 市场文档 raw chunk 与 ANN snapshot 覆盖不完全一致
- legacy registry / snapshot 仍对部分老链路可见，容易让调用方误判 source of truth
- BFF 与 MCP 仍是双配置入口：
  - BFF 使用 `DATABASE_URL`
  - MCP 使用 `DB_*`
  - 两者当前能连到同一库，但治理上仍有漂移风险
