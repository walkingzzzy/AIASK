# AIASK Code Graph

This repo can generate a bounded Graphify code graph for architecture navigation and Agent experiments.

## Purpose

The graph turns AIASK source code, selected tests, and architecture docs into nodes and edges. The curated output is smaller than the full Graphify graph and adds AIASK-specific HTTP endpoint edges so Desktop callers can be connected to Agent FastAPI routes.

Use it for:

- tracing Desktop `AiaskApi` calls to Agent endpoints and handlers
- checking cross-package dependencies between Agent, AKShare MCP, Strategy Factory, Quant Core, and root runners
- finding high-degree hubs before refactors
- giving a future read-only Agent tool a compact architecture index

Do not use it as an execution path. Desktop must still call the Agent HTTP API only, and any model-visible Agent graph tool must use the `agent_*` naming policy.

## Build

From the repo root:

```powershell
python scripts/code_graph/build_aiask_code_graph.py
```

The default output is:

```text
reports/code-graph/<timestamp>/
  graphify-out/
    graph.json
    graph.raw.json
    GRAPH_REPORT.md
    EVAL_SUMMARY.json
  curated/
    core.graph.json
    agent.graph.json
    akshare-mcp.graph.json
    strategy-factory.graph.json
    aiask-quant-core.graph.json
    desktop.graph.json
    root-runners.graph.json
    tests.graph.json
    docs.graph.json
    cross-package-edges.json
    endpoint-map.json
    CURATED_SUMMARY.json
    CURATED_REPORT.md
  RUN_SUMMARY.json
```

The builder creates a temporary corpus outside the repo by default and removes it after a successful run. It intentionally excludes secrets, databases, logs, caches, virtualenvs, `node_modules`, runtime data, and generated reports.

## Agent Tool

When `AIASK_AGENT_TOOLSET=general_full` and `AIASK_AGENT_ENABLE_GENERAL_TOOLS=1`, the Agent exposes a read-only `agent_code_graph_query` tool. It reads an existing curated graph only; it does not run Graphify, execute code, scan arbitrary files, or call managers.

Supported actions:

- `summary`
- `search`
- `endpoint`
- `explain`
- `affected`

Set `AIASK_CODE_GRAPH_DIR` or pass `graph_dir` to point at a curated graph directory. The path must stay under an allowed Agent workspace root or the AIASK repo root.

## Query

Examples:

```powershell
uvx --from graphifyy graphify.exe explain "endpoint_v1_mcp_servers" --graph "reports/code-graph/<timestamp>/curated/core.graph.json"
uvx --from graphifyy graphify.exe affected "endpoint_v1_mcp_servers" --relation calls --depth 1 --graph "reports/code-graph/<timestamp>/curated/core.graph.json"
uvx --from graphifyy graphify.exe explain "services_aiaskapi_aiaskapi" --graph "reports/code-graph/<timestamp>/curated/core.graph.json"
```

`explain` and explicit node/endpoint queries are currently more reliable than broad natural-language `query` on the large graph.

## Notes

- `graphify-out/graph.html` may be skipped or fail for large graphs because Graphify avoids rendering very large HTML visualizations.
- The curated graph keeps Graphify's relation names traversable by mapping AIASK endpoint links to `calls` and preserving the original endpoint semantics in `endpoint_relation`.
- The first production integration should be read-only: an Agent-side `agent_code_graph_*` tool that reads `curated/core.graph.json` and `endpoint-map.json`, with no manager calls and no runtime side effects.
