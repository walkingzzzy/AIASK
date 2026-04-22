# 历史报告归档

`reports/archive/` 存放已经不再作为当前入口、但仍值得追溯的历史运行快照。

## 归档范围

### 1. MCP 深度对话式测试快照

目录：`reports/archive/mcp_deep_tool_test/`

- `full/`
- `heavy_smoke/`
- `heavy_smoke2/`
- `smoke/`
- `smoke2/`

这些目录保留各套件对应的 dated `md/json` 快照；当前主路径只保留 `latest.*`。

### 2. Tool Registry 历史导出

目录：`reports/archive/tool_registry/`

- `tool_registry_20260407_111251.md`
- `tool_registry_20260407_111251.json`

### 3. Strategy Factory 吞吐历史快照

目录：`reports/archive/strategy_factory/`

- `strategy-factory-throughput-manual-full-run-20260406-150403.md`
- `strategy-factory-throughput-full-run-20260406-20260406-164122.md`
- `strategy-factory-throughput-full-run-20260406-retry-20260406-171054.md`
- `strategy-factory-throughput-full-run-20260406-no-json-fix-20260406-173423.md`
- `strategy-factory-throughput-full-run-20260406-no-json-fix-v2-20260406-174119.md`

### 4. Vector Acceptance 历史快照

目录：`reports/archive/vector-acceptance/`

- `vector_p0_p4_acceptance_livecheck_20260325.*`
- `vector_p0_p4_acceptance_livecheck_20260325_retry1.*`
- `vector_p0_p4_acceptance_livecheck_20260325_retry2.*`

### 5. 510300 回测历史报告

目录：`reports/archive/backtests/510300/`

- `510300沪深300ETF定投回测第一版报告.md`

## 使用边界

1. 这些文件保留运行证据，不保留“当前仍然成立”的权威性。
2. 如需引用当前结果，请优先使用主路径中的 `latest.*`。
3. 如果后续再次生成同类报告，优先更新主路径入口，再决定是否把旧 `latest` 下沉到归档。
4. 像 `510300` 这类专题研究若已经有更高版本正式报告，旧版应留在归档而不是继续占用根目录。
