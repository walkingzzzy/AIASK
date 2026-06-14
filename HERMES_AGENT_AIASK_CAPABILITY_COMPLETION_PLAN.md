# Hermes Agent vs AIASK Capability Completion Plan

Last updated: 2026-06-12

## 1. External Hermes Baseline

Baseline used for this plan:

- Hermes Agent version: `0.16.0`
- Release tag: `v2026.6.5`
- Release name: `Hermes Agent v0.16.0 (2026.6.5) - The Surface Release`
- Primary sources:
  - https://hermes-agent.nousresearch.com/
  - https://github.com/NousResearch/hermes-agent/releases/tag/v2026.6.5
  - https://pypi.org/project/hermes-agent/0.16.0/
  - https://raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md

Key Hermes capabilities confirmed from public docs/release metadata:

1. Native desktop app for macOS/Linux/Windows, with chat UI, session list/search/archive, file drop/paste, command palette, self-update, model picker, multi-profile sessions, and Simplified Chinese UI.
2. CLI/TUI with multiline editing, slash-command autocomplete, conversation history, interrupt/redirect, streaming tool output, model switching, session switching, `/retry`, `/undo [N]`, `/compress`, `/usage`, `/skills`, `/stop`.
3. Messaging gateway across Telegram, Discord, Slack, WhatsApp, Signal, Email, Home Assistant, and additional platform adapters.
4. Persistent memory, self-improving skills, skill curation, Skills Hub taps, session search, user modeling, and cross-session recall.
5. Tool system with file, terminal, browser, web search, media, voice/TTS/transcription, MCP, Tool Gateway/Nous Portal integration, and approval/sudo/secret prompts.
6. Scheduled automations via natural-language cron and platform delivery.
7. Delegation/subagents, parallel workstreams, Python/RPC-style pipelines, and multi-agent/kanban workflows.
8. Multiple terminal/backends and deployment targets: local, Docker, SSH, Singularity, Modal, Daytona, server/VPS/cloud.
9. Web dashboard/admin surface for MCP catalog, messaging channels, credentials, webhooks, memory, gateway controls, auth, debug/update flows.
10. Security/reliability controls: command approvals, sandbox/container isolation, SSRF hardening, subprocess credential stripping, patched Starlette, guarded file paths, update/install safeguards.

## 2. AIASK Actual Implementation Snapshot

Current AIASK implementation is not a vendor import of Hermes. It is an AIASK-native Agent runtime with Hermes-aligned capability surfaces.

Implemented or present:

- Agent runtime: FastAPI routes in `packages/agent/src/aiask_agent/server.py`, session/run/event storage, response APIs, tool registry, ActionIntent/approval flow, readiness and capability parity APIs.
- Tool policy: model-visible tools remain behind the `agent_*` facade; default toolset remains `finance_safe`; `general_full` remains gated by env and control token.
- Native/general tools: file, patch, search, terminal/process, browser/CDP/vision, web search/extract, media, todo/subgoal, jobs/cron, gateway/connectors, plugins/skills, RL/learning, MCP aggregation.
- Desktop: React/Vite/Tauri app uses Agent HTTP only; Agent pages cover Sessions, Runs/Events, Tools/Intents/Approvals, Gateway, Readiness/Health, MCP/Connectors, Plugins/Skills.
- Financial specialization: AKShare/Strategy/Factor/Incubation/Quant/Finance MCP planes are stronger than stock Hermes for AIASK's finance domain.
- Readiness/parity: Hermes baseline is surfaced as `0.16.0 / v2026.6.5`; readiness now exposes baseline fields, live evidence, and v0.16 delta status.

Non-negotiable AIASK boundaries:

- Do not embed or import Hermes vendor runtime.
- Do not expose raw manager/MCP stateful action names as model-visible tools.
- Do not read or document secret values; environment variable names only.
- Do not implement live trading paths or broker actions as part of Hermes parity.
- Stateful or external operations require control-token and/or ActionIntent guardrails.
- Desktop must remain an Agent HTTP client.

## 3. Capability Comparison

| Hermes capability area | AIASK current state | Gap / decision |
| --- | --- | --- |
| Native desktop app | AIASK Desktop exists with workbench, Agent pages, readiness, sessions, runs, tools, gateway, MCP, plugins/skills. | Continue feature-by-feature parity, not code import. |
| CLI/TUI | AIASK TUI has parser, autocomplete, session resume, run stop/steer, tools/sessions/skills/approvals. | `/undo [N]` implemented in this phase; `/retry`, `/compress`, richer model picker remain. |
| Sessions/search/archive | AIASK has session store, runs/events, FTS search, handoffs, Desktop Sessions page, archive/unarchive API, include-archived list/search flags, and Desktop archive/restore controls. | Cross-profile links and full Hermes desktop session-management parity remain partial. |
| `/undo [N]` | Implemented as AIASK-native session-context soft undo. | External side effects are intentionally not rolled back. |
| Model picker/providers | AIASK has provider config/status/smoke/models, fallback-oriented status, Desktop provider/model search, and prompt-cache policy controls. | Provider breadth continues to expand; OAuth subscription proxy remains excluded by design. |
| Tool Gateway/Nous Portal | AIASK has provider-gated tools and env-based connectors. | No local OAuth/subscription proxy by design. |
| Browser/web/media | AIASK has local browser/CDP/vision, web search/extract, image/audio/video-adjacent tools. | Cloud browser breadth remains partial. |
| Memory/skills/learning | AIASK has memory, session/search, skills/plugins, learning proposals, RL/MoA surfaces. | Hermes-style autonomous skill curation parity remains partial. |
| Cron/jobs | AIASK exposes jobs/cron tools and routes. | Platform delivery breadth remains partial. |
| Gateway platforms | AIASK has gateway daemon/connectors/webhooks and platform pages. | Full Hermes platform matrix remains partial. |
| Web dashboard/admin | AIASK Desktop Agent pages cover many admin flows. | Browser-based admin dashboard parity remains partial. |
| Security/safety | AIASK has tool policy, full-mode gate, control token, ActionIntent, advisory/security surfaces. | Keep expanding negative tests before adding risky tools. |

## 4. Execution Log

### Phase 0/1 - Baseline, Readiness, Evidence

Status: completed.

Completed changes:

- Unified Hermes baseline to `0.16.0 / v2026.6.5`.
- Added `baseline_version`, `baseline_release_tag`, `live_evidence`, and `live_readiness` into Hermes status/readiness payloads.
- Preserved required env var names while redacting values.
- Added v0.16 delta summary to readiness/parity payloads.
- Updated Desktop types, mock API, capability utilities, readiness/capability tests, and historical docs.

Previously verified:

- `uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_native_full_parity.py packages/agent/tests/test_live_readiness_smoke_script.py`
- `npm test -- --run src/hooks/useHermesConsole.test.tsx src/components/DiagnosticsPanel.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx src/features/agent-pages/ReadinessHealthPage.test.tsx`
- `npm run typecheck`
- `npx playwright test e2e/capabilities.spec.ts --project=chromium`

### Phase 4A - Hermes `/undo [N]`

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- Storage: `messages` now supports `deleted_at`, `deleted_reason`, and `deleted_by` soft-delete metadata.
- Active session context excludes soft-deleted messages from `get_messages`, message lists, message counts, latest-message timestamps, and search.
- `AgentSessionStore.undo_last_turns(session_id, turns=N)` soft-deletes the last N user turns and every later assistant/tool message.
- API: `POST /v1/sessions/{session_id}/undo` returns `aiask.session_undo` and requires Hermes full/control authorization.
- Fallback/simple server route is aligned with the FastAPI route.
- TUI: `/undo [N]` is available in autocomplete and calls the remote undo API for the current session.
- Desktop: `AiaskApi.sessionUndo`, mock route, `SessionUndoPayload`, and a Sessions page `Undo last turn` button were added.
- Parity: `undo_last_turns` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- This is conversation/session-context undo, not universal rollback.
- It does not reverse external side effects, tool writes, gateway sends, approvals, jobs, or broker/manager actions.
- Existing run events and audit evidence remain preserved.
- The API response explicitly reports `side_effects_rolled_back: false` and `external_side_effects: "not_rolled_back"`.

Verification:

- `uv run pytest packages/agent/tests/test_session_memory_todo.py -q` -> 4 passed.
- `uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q` -> 4 passed.
- `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py -q` -> 18 passed.
- From `desktop/`: `npm run typecheck` -> passed.
- From `desktop/`: `npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom` -> 8 passed.

Note: `npm test -- --run src/features/agent-pages/SessionsPage.test.tsx` invokes this repo's broader `vitest run src` script and currently runs unrelated suites too. In that broader run, `McpConnectorsPage.test.tsx` and `StockDataSourcesPanel.test.tsx` had unrelated text/assertion failures; the targeted SessionsPage suite passed with `npx vitest run`.

### Phase 4B - File checkpoint and rollback

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- `agent_file_write` and `agent_file_patch` now create pre-change checkpoints by default.
- `agent_file_checkpoint` creates an explicit rollback point for an allowed workspace file.
- `agent_file_rollback` restores by `checkpoint_id`, or restores the latest checkpoint for a path.
- TUI adds `/rollback <checkpoint_id>` and `/rollback latest <path>` as a control-token backed remote tool call.
- Rollback creates a `pre_rollback_checkpoint` before restoring so the rollback action itself remains reversible.
- Parity: `checkpoint_and_rollback` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- Rollback is limited to local files under configured AIASK workspace roots.
- It does not roll back external side effects, gateway sends, jobs, approvals, live trading, manager state, database changes, or non-file runtime state.
- Checkpoint data is stored under the Agent state/checkpoint directory, not exposed as model-visible secrets.

Verification:

- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py packages/agent/tests/test_hermes_full_expanded_capabilities.py packages/agent/tests/test_capability_completeness.py packages/agent/tests/test_hermes_native_live_adapters.py` -> 49 passed.
- Regression: `uv run pytest packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_hermes_native_live_adapters.py` -> 26 passed.
- From `desktop/`: `npm run typecheck` -> passed.
- From `desktop/`: `npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom` -> 8 passed.

### Phase 4C - Context reference files and URLs

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- Added `aiask_agent.context_references` as a read-only runtime resolver for Hermes-style context.
- Agent run setup now auto-loads project context files from configured workspace roots:
  - `SOUL.md`
  - `.hermes.md`
  - `HERMES.md`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.cursorrules`
- User prompts can include `@file:<path>` / `@path:<path>` for workspace-scoped local files.
- User prompts can include `@url:https://...` or `@https://...` for HTTP(S) reference pages.
- Resolved references are injected into the model turn as a `context_references` system message before planning/LLM calls.
- Resolved local files are persisted as `agent_artifacts`; resolved URLs are persisted as `agent_sources`.
- Runs emit `context.references_resolved` events with source/artifact identifiers.
- Parity: `context_reference_files_and_urls` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- File references are read-only and constrained to `AIASK_AGENT_WORKSPACE_ROOTS`.
- URL references allow only absolute HTTP(S) URLs.
- Private, loopback, link-local, and multicast URL targets remain blocked unless the existing `AIASK_AGENT_ALLOW_PRIVATE_WEB` override is explicitly enabled.
- File/URL bodies are byte/character limited before model injection.
- External URL content is treated as bounded reference context and does not authorize command execution or tool side effects.
- No vendor Hermes runtime is imported.

Verification:

- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_runtime_injects_hermes_style_context_references -q` -> 1 passed.
- `uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py -q` -> 4 passed.
- `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py -q` -> 25 passed.

### Phase 2A - Model picker profiles and fallback

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- Agent already exposes provider presets, model configuration save, model-list fetching, smoke tests, provider status, credential pools, fallback order, and model-list fallback.
- Desktop `ModelsWorkspace` now adds fuzzy filtering for provider presets and available model IDs.
- The provider search matches preset id, label, provider, provider type, base URL, default model, and notes.
- The model search filters model options and preview rows without changing saved configuration.
- Parity: `model_picker_profiles_and_fallback` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- Saving model configuration still requires the control token.
- Secrets remain redacted; API keys are never echoed back into Desktop UI.
- OAuth subscription proxy flows remain excluded by design.

Verification:

- From `desktop/`: `npm run typecheck` -> passed.
- From `desktop/`: `npx vitest run src/features/models/ModelsWorkspace.test.tsx --environment jsdom` -> 1 passed.
- Agent parity regression: `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py` -> 25 passed.

### Phase 2B - Prompt caching controls

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- Agent exposes a prompt-cache policy through AI status/config, model provider status/readiness, and `agent_model_manage` with `action="prompt_cache"`.
- Anthropic Messages requests apply `cache_control: {"type": "ephemeral"}` to the system prompt and the configured number of recent non-system messages when enabled.
- Config save accepts `prompt_cache_enabled` and `prompt_cache_recent_messages`, writing only non-secret env keys:
  - `AIASK_AGENT_PROMPT_CACHE_ENABLED`
  - `AIASK_AGENT_PROMPT_CACHE_STRATEGY`
  - `AIASK_AGENT_PROMPT_CACHE_RECENT_MESSAGES`
- Desktop Models page shows Prompt Cache status and lets the user save the cache toggle/recent-message count with the same control-token-gated model config flow.
- Parity: `prompt_caching_controls` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- AIASK only applies Anthropic-compatible `cache_control` semantics where supported.
- OpenAI-compatible providers are reported as unsupported for this policy unless they expose equivalent semantics.
- No secret values are logged, returned, or written into documentation.

Verification:

- `uv run pytest packages/agent/tests/test_ai_status_and_smoke.py -q` -> 10 passed, 1 skipped.
- From `desktop/`: `npm run typecheck` -> passed.
- From `desktop/`: `npx vitest run src/features/models/ModelsWorkspace.test.tsx --environment jsdom` -> 1 passed.
- Agent parity regression: `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py -q` -> 25 passed.

Note: A combined long-running pytest command covering session, model, and Hermes suites timed out at 180 seconds in this environment; the same suites passed when run as targeted commands.

### Phase 3A - Session archive/search management

Status: implemented for archive/search; broader Hermes session-link parity remains partial.

Implemented AIASK-native behavior:

- Storage: session archive state is stored in `sessions.metadata_json` with `archived`, `archived_at`, `archived_reason`, and actor/update metadata.
- Listing: `AgentSessionStore.list_sessions()` hides archived sessions by default and supports `include_archived=True`.
- Search: `/v1/search` and `AgentSessionStore.search()` hide archived sessions by default and support `include_archived=true`.
- API: `POST /v1/sessions/{session_id}/archive` archives or restores a session and requires Hermes full/control authorization.
- Fallback/simple server route is aligned with the FastAPI route.
- Desktop: `AiaskApi.sessionsList(..., includeArchived)`, `AiaskApi.sessionArchive`, `SessionArchivePayload`, mock routes, a Sessions page `显示归档` toggle, archive/restore controls, and archived-session badges were added.
- Parity: `session_archive_search_and_links` remains `partial` because cross-profile links and exact Hermes desktop session-link semantics are not fully implemented.

Safety boundary:

- Archive/unarchive changes local session metadata only.
- It does not delete messages, responses, run events, approvals, handoffs, jobs, gateway messages, files, or external side effects.
- Archived sessions are hidden from default list/search views but remain recoverable through `include_archived`.

Verification:

- `uv run pytest packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_desktop_workbench_contracts.py -q` -> 10 passed.
- From `desktop/`: `npm run typecheck` -> passed.
- From `desktop/`: `npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom` -> 9 passed.
- Agent parity regression: `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py -q` -> 25 passed.

### Phase 6A - Hermes external memory provider catalog

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- `MemoryProviderManager.status()` now exposes an explicit Hermes external-provider catalog.
- The catalog includes Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, and Supermemory.
- Each provider reports:
  - `configured`
  - `status`
  - `required_env`
  - `capabilities`
  - `integration_status`
  - `secrets_redacted`
- `MemoryProviderManager.catalog()` returns a catalog-focused payload.
- `agent_memory_manage` now supports `action="catalog"` through the model-visible `agent_*` facade.
- `MemoryProviderManager.audit()` checks catalog completeness and reports explicit issues if provider rows are missing.
- Parity: `external_memory_provider_catalog_breadth` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- SQLite remains the durable default memory backend.
- External memory providers are catalog/readiness entries unless credentials and an explicit future sync implementation are configured.
- A configured external provider reports `live_unverified`; AIASK does not silently send memory to third-party services.
- Only env var names are surfaced; secret values remain redacted.

Verification:

- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_memory_provider_catalog_covers_hermes_external_providers -q` -> 1 passed.
- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_memory_provider_catalog_covers_hermes_external_providers packages/agent/tests/test_hermes_reference_guardrails.py -q` -> 5 passed.
- `uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py -q` -> 30 passed.

### Phase 7A - Hermes media provider catalog

Status: implemented and target-verified in this pass.

Implemented AIASK-native behavior:

- Added a read-only AIASK media provider catalog covering:
  - OpenAI vision
  - OpenAI image generation
  - AIASK/OpenAI-compatible video endpoint
  - OpenAI TTS
  - Edge TTS local dependency
  - OpenAI STT/transcription
  - iFlytek voice provider slots
  - Local Whisper dependency slot
- Added `agent_media_provider_catalog` as a model-visible `agent_*` tool in `general_full`.
- The catalog reports modality, provider type, configured status, required env names, default model hints, local dependencies, and redaction status.
- `/health/detailed` now includes Hermes `live_evidence` so required env names remain diagnostically visible while values stay redacted.
- Existing media tools remain separate and gated:
  - `agent_vision_analyze`
  - `agent_image_generate`
  - `agent_video_generate`
  - `agent_text_to_speech`
  - `agent_transcribe_audio`
- Parity: `media_provider_catalog_breadth` moved from `partial` to `implemented` in the Hermes v0.16 delta.

Safety boundary:

- `agent_media_provider_catalog` is read-only and does not create media or call external media providers.
- Configured providers report readiness/catalog state only; real provider calls remain inside the existing explicit media tools.
- Only env var names and model hints are surfaced; secret values remain redacted.
- Local dependency-backed providers report dependency status without installing packages.

Verification:

- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_media_provider_catalog_reports_multimodal_readiness -q` -> 1 passed.
- `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_media_provider_catalog_reports_multimodal_readiness packages/agent/tests/test_extended_agent_capabilities.py::test_provider_backed_vision_tts_and_stt_are_real_calls packages/agent/tests/test_extended_agent_capabilities.py::test_provider_tools_report_unconfigured_without_credentials -q` -> 3 passed.
- `uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py -q` -> 31 passed.
- Final targeted regression: `uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_runtime_injects_hermes_style_context_references packages/agent/tests/test_extended_agent_capabilities.py::test_memory_provider_catalog_covers_hermes_external_providers packages/agent/tests/test_extended_agent_capabilities.py::test_media_provider_catalog_reports_multimodal_readiness packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_hermes_native_live_adapters.py packages/agent/tests/test_desktop_capabilities_api.py -q` -> 32 passed.
- Final v0.16 delta snapshot: 10 implemented / 9 partial / 0 missing / 0 excluded.

## 5. Remaining Development Roadmap

Phase 3 - Session management:

- Archive/unarchive and default archive-aware search/list filtering are implemented.
- Continue richer search/detail flows and explicit session-link/cross-profile contracts.
- Consider cross-session/cross-profile links only through explicit Agent HTTP contracts.
- Add resume/retry/compress parity where safe.

Phase 4 - Context and files:

- Context reference files and URL injection are implemented.
- Continue Desktop affordances for visible per-turn context chips/history if needed.
- Keep all context expansion read-only and workspace/SSRF guarded.

Phase 5 - Gateway/admin breadth:

- Expand visible platform coverage and degraded/unavailable states.
- Keep send/delivery operations behind ActionIntent/control-token guardrails.

Phase 6 - Learning/skills/delegation:

- Hermes external memory provider catalog breadth is implemented as readiness/catalog coverage.
- Improve skill curation, self-reflection, and learning proposal workflows.
- Extend subgoal/subrun visibility without exposing raw internal managers.

Phase 7 - Media/provider breadth:

- Media provider catalog breadth is implemented as read-only readiness/catalog coverage.
- Continue adding real provider adapters only behind explicit env configuration and tool invocations.

## 6. Acceptance Criteria

A Hermes-aligned capability can be marked implemented only when:

1. The source-of-truth code path exists in AIASK, not just a mock.
2. Agent HTTP contracts are typed and Desktop consumes them through `AiaskApi`.
3. Stateful paths are gated by control token and/or ActionIntent.
4. Tests cover positive and negative/guarded paths.
5. Parity/readiness surfaces clearly distinguish implemented, partial, excluded-by-design, and live-unverified.
6. Documentation records the exact safety boundary.
