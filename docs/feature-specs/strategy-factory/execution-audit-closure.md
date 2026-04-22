# Strategy Factory：Execution Audit 闭环

## 覆盖范围

- 本文覆盖 execution-audit 从 BFF 入口、MCP action、TimescaleDB acceptance、孵化阶段 gate，到本地脚本入口的当前闭环。
- 重点收口：
  - `execution_audit_gate_status` taxonomy
  - acceptance 返回字段
  - `bootstrap_ready` / `promotion_hard_gate_pending` 的真实语义
  - replay / acceptance 脚本入口
  - 仍然只对本机路径成立的边界

## 事实来源

- BFF：
  - `apps/bff/src/strategy/strategy-incubation.controller.ts`
  - `apps/bff/src/strategy/strategy.service.core.ts`
- Storage / lifecycle：
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation_parts/queries.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/confidence.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/incubation.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py`
- Governance / reporting：
  - `packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py`
- 脚本：
  - `scripts/strategy-execution-audit-acceptance.py`
  - `scripts/strategy-incubation-history-replay.py`
- 测试：
  - `packages/akshare-mcp/tests/test_execution_audit_replay_contract.py`
  - `packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py`

## 取证方式

- `rg -n "execution_audit_gate_status|bootstrap_ready|promotion_hard_gate_pending" packages/akshare-mcp/src packages/strategy-factory/src scripts`
- `rg -n "run_execution_audit_acceptance|get_strategy_trade_audit_summary|_build_execution_audit_blocker_details" packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation_parts/queries.py`
- `rg -n "execution-audit|executionAuditAcceptance" apps/bff/src/strategy`

## 不覆盖范围

- 不展开 paper trading 撮合实现细节。
- 不把历史 acceptance 报告里的绝对路径、旧版 schema version、旧 blocker 文案继续当成当前 contract。

## BFF 入口

- `GET /api/strategy-market/:id/execution-audit`
  - `apps/bff/src/strategy/strategy-incubation.controller.ts::executionAuditAcceptance`
  - query `backfill` 默认 `false`
- `POST /api/strategy-market/:id/execution-audit/run`
  - `apps/bff/src/strategy/strategy-incubation.controller.ts::runExecutionAuditAcceptance`
  - body `backfill` 默认 `true`
- 两个入口最终都走：
  - `apps/bff/src/strategy/strategy.service.core.ts::executionAuditAcceptance`
  - 通过 `strategy_manager` action `execution_audit_acceptance`

## execution_audit_gate_status taxonomy

`packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/confidence.py::evaluate_execution_audit_gate` 当前只输出：

- `missing`
- `bootstrap_pending`
- `insufficient_samples`
- `failed_metrics`
- `bootstrap_ready`
- `passed`

当前判定规则已锁定为：

- `missing`
  - 没有 summary，或 `realized_trade_count <= 0` 且没有 runtime evidence
- `bootstrap_pending`
  - 有 runtime evidence，但 `realized_trade_count <= 0`
- `insufficient_samples`
  - `realized_trade_count > 0`，但仍低于 `bootstrap_trade_floor`
- `failed_metrics`
  - 已达到 bootstrap floor，但以下任一 hard metric 未达标：
    - `trade_expectancy > 0`
    - `pnl_conversion_efficiency > 0`
    - `execution_conversion_efficiency >= 0.20`
- `bootstrap_ready`
  - 上面 3 个 metric 都通过
  - 但 `realized_trade_count < required_trade_count`
- `passed`
  - metric 通过，且 `realized_trade_count >= required_trade_count`

## trade audit summary 字段

`queries.py::get_strategy_trade_audit_summary` 当前稳定输出：

- `approximate`
- `audit_grade`
- `method`
- `source_tables`
- `mapped_position_count`
- `strategy_type`
- `realized_trade_count`
- `incomplete_position_count`
- `trade_expectancy`
- `pnl_conversion_efficiency`
- `execution_conversion_efficiency`
- `execution_win_rate`
- `avg_win_loss_ratio`
- `realized_pnl_total`
- `audit_ready_for_hard_gate`
- `bootstrap_gate_ready`
- `execution_audit_gate_status`
- `execution_audit_gate_reasons`
- `hard_gate_metric_passes`
- `hard_gate_metrics`
- `bootstrap_trade_floor`
- `required_trade_count`

其中：

- `bootstrap_gate_ready` 仅代表 `gate_status in {"bootstrap_ready", "passed"}`
- `audit_ready_for_hard_gate` 仅代表 `gate_status == "passed"`
- 所以 `bootstrap_ready` 不是最终通过，只是“bootstrap 样本与指标已够，但 production hard gate 仍未过”

## acceptance 返回字段

`queries.py::run_execution_audit_acceptance` 当前返回：

- `status`
- `strategy_id`
- `method = "execution_audit_acceptance_v1"`
- `backfill_executed`
- `backfill_result`
- `acceptance_matrix`
- `blockers`
- `blocker_details`
- `gap_categories`
- `actionable_todos`
- `verification`
- `trade_audit_summary`
- `recommendations`

其中顶层 `status` 当前不是 `execution_audit_gate_status` 的别名，而是 acceptance 结果状态：

- `ready`
  - `acceptance_matrix.overall_ready == true`
- `pending_data`
  - `overall_ready == false`
  - 且 `realized_trade_count <= 0`
  - 且首个 blocker 不是 `execution_audit_schema_incomplete`
- `needs_attention`
  - 其他未 ready 场景

`acceptance_matrix` 当前固定包含：

- `schema_ready`
- `migration_ready`
- `orders_position_link_ready`
- `trades_position_link_ready`
- `native_lineage_ready`
- `fill_round_trip_ready`
- `bootstrap_gate_ready`
- `hard_gate_ready`
- `trade_evidence_ready`
- `overall_ready`

`overall_ready` 当前不看 `bootstrap_gate_ready`，而是必须同时满足：

- `schema_ready`
- `migration_ready`
- `orders_position_link_ready`
- `trades_position_link_ready`
- `native_lineage_ready`
- `fill_round_trip_ready`
- `hard_gate_ready`
- `trade_evidence_ready`

这意味着：

- `bootstrap_ready` 会让 `bootstrap_gate_ready = true`
- 但仍然无法让 `overall_ready = true`
- 文档里不能再把 `bootstrap_ready` 写成 acceptance pass

## blocker / gap 语义

当前 blocker 生成逻辑来自 `queries.py::_build_execution_audit_blocker_details` 与 `run_execution_audit_acceptance`：

- `realized_trade_evidence_insufficient`
  - `sample_gap`
  - 真实已平仓样本不足，或仍有未闭合仓位
- `bootstrap_pending`
  - `sample_gap`
  - 只有运行痕迹，还没有第一批 realized trade
- `insufficient_samples`
  - `sample_gap`
  - 已有 realized trade，但还没到 bootstrap trade floor
- `promotion_hard_gate_pending`
  - `sample_gap`
  - 只在 `execution_audit_gate_status == "bootstrap_ready"` 时出现
  - 表示 bootstrap 已过，但 production hard gate 仍未过
- 其他 hard gate 未过场景
  - 直接用 `gate_status` 自身作为 blocker
  - 当前典型是 `failed_metrics`

这也解释了两个容易写错的点：

- `bootstrap_ready` 对 acceptance 来说不是 pass，而是 blocker `promotion_hard_gate_pending`
- `promotion_hard_gate_pending` 属于 `sample_gap`，不是 `performance_gap`

## 闭环到 incubation / governance 的传播

- `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/incubation.py`
  - 只有 `execution_audit_gate_status == "passed"` 才可能把 `graduation_ready` / `candidate` 继续保留下来
  - `failed_metrics` 会把 pipeline stage 打成 `failed`
  - 其他非 passed 状态默认把策略留在 `observe`
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py`
  - `missing` / `bootstrap_pending` / `insufficient_samples` / `bootstrap_ready` / `failed_metrics` 都会进入 execution gate 风险或 blocker 语义
- `packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py`
  - `missing`
  - `bootstrap_pending`
  - `insufficient_samples`
  - `bootstrap_ready`
  - `insufficient_evidence`
  - 上述状态都会被追加到 `evidence_gap_codes`：`execution_audit_gate:<status>`
- `packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py`
  - 已锁定 `bootstrap_ready` 仍然要写入 `execution_audit_gate:bootstrap_ready`

## 脚本入口

### 1. acceptance

入口：

```bash
python scripts/strategy-execution-audit-acceptance.py
```

当前稳定参数：

- `--strategy-ids`
- `--statuses`
- `--limit`
- `--offset`
- `--selection-mode {status,runtime_evidence}`
- `--backfill`
- `--fail-on-blockers`
- `--report-dir`
- `--version-tag`

当前输出 contract：

- `report_type = "execution_audit_acceptance"`
- `schema_version = "execution_audit_acceptance.v2"`
- JSON 与 Markdown 都会落盘

### 2. replay

入口：

```bash
python scripts/strategy-incubation-history-replay.py
```

当前稳定参数：

- `--strategy-ids`
- `--from-acceptance-report`
- `--sample-gap-only`
- `--statuses`
- `--limit`
- `--start-date`
- `--end-date`
- `--max-dates`
- `--signal-dates-only`
- `--force-close-open-positions`
- `--reset-state`
- `--skip-acceptance`
- `--report-dir`
- `--version-tag`

当前 replay 侧与 acceptance 的闭环语义：

- `--from-acceptance-report` 只接受 `report_type = "execution_audit_acceptance"` 的 JSON
- `--sample-gap-only` 会筛出：
  - `gap_categories` 含 `sample_gap`
  - 或 blocker 命中 sample-gap blocker 集合
  - 或 `trade_audit_summary.execution_audit_gate_status in {"bootstrap_pending", "insufficient_samples", "bootstrap_ready"}`
- `packages/akshare-mcp/tests/test_execution_audit_replay_contract.py`
  - 已锁定 `bootstrap_ready` 必须被 replay summary 识别为 `sample_gap`

## 已知限制

- `scripts/strategy-execution-audit-acceptance.py` 默认 report dir 是仓库内 `reports/execution-audit-acceptance`
- `scripts/strategy-incubation-history-replay.py` 默认 report dir 是仓库内 `reports/incubation-history-replay`
- 两个脚本都会把路径 `resolve()` 后写入结果：
  - `env_source`
  - `source_acceptance_report`
  - `report_json`
  - `report_md`
- 这些字段可能出现 `/Users/mac/Desktop/股票/...` 这类绝对路径；它们只在当前机器 / 当前工作树成立，不能再被文档表述成通用跨环境路径契约。
- `packages/akshare-mcp/src/akshare_mcp/env_loader.py::load_mcp_env` 当前只按 repo-local 候选路径找 `.env`，属于本地运行时约束，不是部署平台的标准 secrets 发现协议。
- `--reset-state` 会直接删除选定策略的 runtime state；它是破坏性重放准备步骤，不是只读预演。
