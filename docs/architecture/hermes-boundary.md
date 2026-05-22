# Hermes Capability Boundary Decision

Date: 2026-04-27

## Decision

`vendor/hermes-agent-upstream/` is retained only as upstream reference source.
It is not part of the AIASK runtime, package dependency graph, import path, CI
test target, or release artifact.

AIASK must implement Hermes-class capabilities natively in `packages/agent`.
The project must not satisfy parity by embedding, importing, shelling out to, or
sidecar-running Hermes. Hermes source is a behavioral specification and review
reference only.

AIASK owns its runtime and capability surface:

- `aiask_agent.runtime` owns the financial agent loop.
- `aiask_agent.server` owns the local HTTP API.
- `aiask_agent.tools` owns the `agent_*` tool surface visible to the model.
- `aiask_agent.adapters` owns calls into `akshare-mcp` and `strategy-factory`.
- `aiask_agent.intents` owns durable action intents and confirmation state.
- `aiask_agent.native_capabilities` owns AIASK-native Hermes-class tools such as
  web, skills, plugins, clarify, todos, vision, image generation, TTS, and
  messaging outbox behavior.
- `aiask_agent.capabilities` owns the executable financial-product parity
  matrix returned by `/v1/capabilities/parity` and `/v1/hermes/status`.
- `aiask_agent.process_registry`, `aiask_agent.webhooks`,
  `aiask_agent.plugin_runtime`, and `aiask_agent.mcp_client` own the native
  management surfaces used by the desktop Full Mode console.

Hermes concepts may be studied, but code must be rewritten into AIASK-owned
modules with tests and financial safety policy.

## Repository Boundary

Allowed:

- Keep `vendor/hermes-agent-upstream/LICENSE`, README, release notes, and source
  files for architecture review and future comparison.
- Read Hermes implementations of model adapters, tool registries, API shape,
  context compression, and MCP connection patterns as reference material.
- Add AIASK-native modules that implement equivalent behavior under
  `packages/agent/src/aiask_agent`.

Forbidden:

- Import from `vendor/hermes-agent-upstream`, `run_agent`, `model_tools`,
  `toolsets`, `tools.mcp_tool`, `gateway.platforms`, or `hermes_cli`.
- Add `hermes-agent` as a dependency in any `pyproject.toml`, lock file, script,
  or runtime configuration.
- Expose vendor Hermes terminal, file, browser, code execution, delegate,
  messaging gateway, skill hub, plugin, or cron tooling to AIASK tasks.
- Let desktop clients call Hermes APIs, MCP directly, or strategy managers
  directly as the production baseline.

## Runtime Boundary

```text
Desktop / CLI / future clients
        |
AIASK Agent HTTP API
        |
AIASK Agent Runtime
        |
agent_* AIASK-native tool registry
        |
AIASK adapters
        |
akshare-mcp + strategy-factory
```

The model may see only `agent_*` tools. `finance_safe` remains the default
runtime mode. `hermes_full` is an AIASK-native full-capability mode guarded by
`AIASK_AGENT_ENABLE_HERMES_FULL=1` and a control token; it does not import or
execute vendor Hermes.

Direct manager names such as
`strategy_manager`, `live_trading_manager`, `execution_manager`, and
`paper_trading_manager` must not be exposed to the model.

Stateful or risky actions must be represented as durable action intents first.
Confirming or denying an intent is a deterministic control operation, not a
free-text model turn.

## Parity Reporting

AIASK reports financial-product parity through
`docs/architecture/hermes-financial-product-parity.md` and the live
`/v1/capabilities/parity` endpoint. A registered `agent_*` mapping proves that
AIASK has an owned capability surface; it does not automatically prove full
runtime equivalence. Capabilities that depend on provider credentials, optional
platform services, interactive sessions, or deeper runtime behavior must stay
marked `partial` until tests prove complete behavior.

## Vendor Hygiene

The upstream Hermes snapshot must stay clean:

- No `.env` files.
- No `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, or similar
  local caches.
- No `node_modules`, `dist`, `build`, or generated frontend bundles.
- No local secrets, API keys, machine-specific config, or generated databases.

If the reference snapshot becomes unnecessary, delete `vendor/hermes-agent-upstream/`
instead of partially importing it into active packages.

## Enforcement

`packages/agent/tests/test_no_hermes_dependency.py` scans active package files
for forbidden Hermes runtime references. Keep that test broad enough to cover
all active packages under `packages/**`, while excluding `vendor/**` and
historical documentation.
