# AIASK Native Hermes Financial Product Parity

Date: 2026-04-27

This matrix tracks AIASK-native parity against Hermes Agent 0.16.0, release tag
`v2026.6.5` ("The Surface Release"). The original financial-product runtime
scope is retained as a compatibility label, `v0.14_delta` remains a historical
capability layer, and `v0.16_delta` tracks the Surface Release additions.

The executable source of truth is
`packages/agent/src/aiask_agent/capabilities.py`; `/v1/capabilities/parity` and
`/v1/hermes/status` return the live status.

## Scope

Included:

- Financial-safe agent loop, sessions, run events, context compaction, planner,
  memory, todo, clarification, subagent delegation, and audit records.
- AIASK-native terminal/process/file/code/browser/web/skills/plugins/MCP/cron
  webhook, platform gateway, Home Assistant, TUI status, RL/Atropos, MoA, and
  terminal-backend controls for the AIASK `general_full` runtime.
- Provider-backed multimodal hooks that report `configured=false` when required
  credentials are missing.

Excluded:

- Hermes website/docs engineering and upstream packaging internals.
- Importing, embedding, shelling out to, or sidecar-running the Hermes runtime.

## Current Status

As implemented in this branch, AIASK covers the required financial-product
capability names through `agent_*` tools, but several areas remain marked
`partial` because they depend on provider credentials, optional platform
services, or deeper runtime behavior:

- `terminal`: approval, session cwd tracking, foreground execution, and managed
  background process list/read/kill exist; interactive PTY parity remains
  partial.
- `web_extract`: native fetch/extract exists; browser-grade extraction remains
  partial.
- `vision_analyze`, `image_generate`, `text_to_speech`: provider hooks are real
  but require configured credentials.
- `execute_code`: Python execution exists with `aiask_tools` RPC access to the
  currently enabled safe AIASK tools; multi-language and remote sandbox parity
  remains partial.
- `delegate_task`: in-process subagents exist; richer multi-agent coordination is
  partial.
- `send_message` and `platform_gateway`: native gateway records inbound/outbound
  traffic and exposes the Hermes platform matrix; live external adapters remain
  credential-gated and partial.
- `mcp_client`: config, catalog, resources, prompts, and OAuth status surfaces
  exist; live non-stdio transports and OAuth flows remain partial.
- `homeassistant`, `rl_training`, `terminal_backends`, `learning_loop`, `moa`,
  `feishu`, and `discord`: native `agent_*` tools and management surfaces now
  exist, but provider credentials and live platform workers keep them partial.

## Verification

The following tests enforce the boundary and current behavior:

- `packages/agent/tests/test_no_hermes_dependency.py`
- `packages/agent/tests/test_native_full_parity.py`
- `packages/agent/tests/test_extended_agent_capabilities.py`
- `packages/agent/tests/test_server.py`

Desktop Full Mode now reads the AIASK-native endpoints directly:

- `/v1/capabilities/parity`
- `/v1/hermes/status`
- `/v1/hermes/tools`
- `/v1/processes`
- `/v1/browser/sessions`
- `/v1/skills`
- `/v1/plugins`
- `/v1/mcp/*`
- `/v1/jobs`
- `/v1/webhooks`
- `/v1/approvals`
- `/v1/runs/{run_id}/events`
