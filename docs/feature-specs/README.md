# Feature Specs

## 覆盖范围

- 本目录只覆盖 `2026-04-21` 当前 worktree 里刚刚收口、且已经被代码与测试锁死的 3 个专题：
  - `observability / health` 状态模型
  - `mcp job / transport` 契约
  - `execution-audit` 闭环
- 本目录不尝试恢复历史上完整的 `docs/feature-specs/` 树，只保留当前仍需要作为事实基线引用的最小子集。

## 事实来源

- 第一事实来源是当前源码与测试。
- 其中优先参考：
  - `apps/bff/src/health/*`
  - `apps/bff/src/observability/*`
  - `apps/bff/src/mcp-gateway/*`
  - `apps/bff/src/mcp-jobs/*`
  - `packages/shared-types/src/common.ts`
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation_parts/queries.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/*`
  - `scripts/strategy-execution-audit-acceptance.py`
  - `scripts/strategy-incubation-history-replay.py`

## 取证方式

- `rg -n "normal|degraded|untrusted|blocked|vector_health" apps/bff/src/health apps/bff/src/observability`
- `rg -n "McpTransportSnapshot|McpJobRecord|MCP_JOB_" packages/shared-types/src apps/bff/src/mcp-gateway apps/bff/src/mcp-jobs`
- `rg -n "execution_audit_gate_status|run_execution_audit_acceptance|bootstrap_ready|promotion_hard_gate_pending" packages/akshare-mcp/src packages/strategy-factory/src scripts`

## 不覆盖范围

- 不再沿用历史 full-tree 文档里的 handler 数量、旧 envelope、旧状态名或旧路径说明。
- 不把本机绝对路径、临时 fixture 路径、历史报告路径写成跨环境契约。
- 不把 archive / plan 类历史文档里的时点结论提升为当前事实。

## 文档导航

- [App Layer：Health / Observability 状态模型](./app-layer/runtime-health-observability.md)
- [App Layer：MCP Jobs / Transport 契约](./app-layer/mcp-jobs-and-transport.md)
- [Strategy Factory：Execution Audit 闭环](./strategy-factory/execution-audit-closure.md)

## 已知限制

- `docs/feature-specs/` 当前是最小恢复版；未覆盖的旧模块说明应回到当前源码，不应默认认为“文档缺失即能力缺失”。
- 文档中提到的本机路径限制会显式写在各专题的“已知限制”中；这些限制描述的是当前实现边界，不是建议继续沿用本机路径。
