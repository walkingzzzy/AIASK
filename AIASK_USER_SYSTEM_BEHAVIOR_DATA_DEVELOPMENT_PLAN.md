# AIASK User System, Behavior Data, Conversation, And Tool Audit Development Plan

> Status: implemented. The user requested full development beyond P0; this document now tracks the delivered user-system foundation and remaining future hardening.
> Date: 2026-06-12

## 0. Implementation Summary

Delivered scope:

- Agent state storage now records user activity events, tool invocation audits, feedback events, and per-user data policy.
- Agent HTTP exposes behavior event recording, feedback, user activity, analytics summary, export/delete preview and execution, retention sweep, learning dataset, recommendations, and data-policy routes.
- FastAPI routes and the simple fallback branch in `server.py` are aligned for the new Desktop-facing endpoints.
- Runtime and direct HTTP tool calls record sanitized `agent_*` tool invocation audits.
- Desktop API client, mock API, and Local User workspace expose user activity, tool audit, feedback, retention policy, export/delete preview, learning eligibility, recommendations, privacy-preserving aggregate analytics, and audit posture panels.
- Tests cover storage, HTTP contracts, Desktop API methods, mock UI behavior, redaction, cross-user/control gating, retention dry-runs, learning gates, and export/delete preview.

Verification performed:

- `python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/runtime.py`
- `uv run pytest packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_desktop_workbench_contracts.py`
- `uv run pytest packages/agent/tests/test_tool_registry.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_endpoint_drift_gate.py`
- `npm run typecheck` from `desktop/`
- `npm test -- src/services/aiaskApi.test.ts` from `desktop/`
- `npm test -- src/features/user/LocalUserWorkspace.test.tsx` from `desktop/`

## 1. Background

AIASK already has partial persistence, but it is not yet a unified user system:

- Agent stores sessions, messages, responses, runs, run events, handoffs, subgoals, and search indexes in `packages/agent/src/aiask_agent/session_store.py`.
- Desktop already reads and saves a local profile through `/v1/desktop/users/local-profile`.
- Quant Core and AKShare MCP include app-level auth/audit migrations such as `app_users`, `app_sessions`, `audit_logs`, and `frontend_behavior_events`.
- Tool usage is partly visible through `run_events`, but there is no first-class tool invocation audit table with stable query semantics.
- User behavior, product analytics, learning data, privacy boundaries, and retention rules are not yet one coherent contract.

The goal is to create a privacy-aware user data foundation that helps core product optimization, Agent quality improvement, tool reliability analysis, and future personalized workflows.

## 2. Non-Negotiable Architecture Boundaries

Follow the current AIASK package rules:

- Desktop consumes Agent HTTP only.
- Desktop must not import Python packages, call MCP tools directly, call managers directly, or write runtime databases directly.
- Model-visible tools remain behind the `agent_*` facade.
- Raw AKShare manager names must not become model-visible tools.
- Side-effectful, external-platform, strategy-lifecycle, plugin mutation, file/terminal/browser write, gateway delivery, and trade-risk actions keep ActionIntent or equivalent guardrails.
- Secret values from `.env`, model provider credentials, broker credentials, tokens, cookies, and API keys must never be logged or returned.

## 3. Product Goals

P0 goals:

- Give every relevant request a consistent user context.
- Persist conversation history and run history by user, session, and run.
- Record tool usage with outcome, duration, side-effect level, approval linkage, and sanitized input/output summaries.
- Record frontend behavior events needed to improve product workflows.
- Provide user-level search and activity APIs for Desktop.
- Add explicit data retention and privacy rules.

P1 goals:

- Add feedback events for message, tool, run, strategy, and page-level quality signals.
- Build analytics summaries for page usage, tool failure rate, workflow funnels, and model cost/quality.
- Add data export/delete controls for local user data.
- Feed safe, user-approved facts into memory and learning loops.

P2 goals:

- Build personalized workflow recommendations.
- Add privacy-preserving aggregation and opt-in learning datasets.
- Add admin dashboards for reliability, retention, and audit posture.

## 4. Data Classes

### 4.1 User Profile Data

Keep:

- `user_id`
- `profile_name`
- role and permission summary
- risk level
- language and UI preferences
- preferred market, symbols, model, data source, and toolset
- retention and learning consent settings
- timestamps

Do not keep:

- raw passwords
- raw tokens
- raw model provider keys
- raw broker credentials
- unredacted private identifiers unless explicitly required and encrypted

### 4.2 Conversation Data

Keep:

- `session_id`
- `user_id`
- title
- source view/page
- model mode/toolset
- messages
- assistant responses
- created/updated timestamps
- soft delete metadata
- searchable sanitized content

Retention:

- Default local conversation history can be long-lived.
- User must be able to delete, export, and eventually configure retention.
- Deleted messages stay soft-deleted only where audit/debug requires it; otherwise support hard-delete cleanup.

### 4.3 Run And Event Data

Keep:

- `run_id`
- `session_id`
- `user_id`
- `trace_id`
- status
- model/provider metadata without secrets
- cost/token usage summary when available
- lifecycle events
- approval markers
- error code and degraded/fallback reasons

Retention:

- Detailed events: default 180 days.
- Aggregated metrics: long-lived.
- Approval and trade-risk events: longer retention, configurable.

### 4.4 Tool Invocation Data

Keep:

- tool name
- `agent_*` facade name where applicable
- capability/category
- side-effect level
- `user_id`, `session_id`, `run_id`, `trace_id`
- sanitized input summary
- sanitized output summary
- status: queued, running, succeeded, failed, denied, cancelled
- duration
- error code
- approval/action intent id
- source chain
- secrets redaction flag

Do not keep:

- raw secret-bearing payloads
- full file contents unless the tool result is explicitly a user-visible artifact
- raw terminal output beyond a safe summary and bounded tail
- broker/order credentials

### 4.5 Frontend Behavior Data

Keep:

- page key
- route
- event type
- target type/id/test id
- safe label
- session id
- user id
- source: desktop/web/tauri/mock
- safe payload
- timestamp

Recommended event types:

- `page_view`
- `button_click`
- `tab_change`
- `search_submit`
- `filter_change`
- `form_submit`
- `modal_open`
- `error_seen`
- `run_opened`
- `tool_opened`
- `approval_decision`
- `feedback_submit`

Do not keep:

- keystroke-level tracking
- raw form values by default
- sensitive field values
- full prompt text as behavior payload, because prompts already belong to conversation storage

### 4.6 Feedback And Learning Data

Keep:

- target type: message, run, tool, page, strategy, model
- target id
- rating or feedback type
- optional comment after redaction
- whether it may be used for learning
- timestamp

This data should drive:

- tool reliability ranking
- model/provider quality analysis
- UI workflow improvement
- learning proposal generation

## 5. Proposed Agent Storage Additions

Primary owner: `packages/agent/src/aiask_agent/session_store.py`.

Add these tables to the Agent state database first, because Desktop already talks to Agent HTTP and most runtime state already lands there.

```sql
CREATE TABLE IF NOT EXISTS user_activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    session_id TEXT,
    run_id TEXT,
    trace_id TEXT,
    page_key TEXT,
    route TEXT,
    event_type TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    target_label TEXT,
    target_testid TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'desktop',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invocation_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    session_id TEXT,
    run_id TEXT,
    trace_id TEXT,
    tool_name TEXT NOT NULL,
    capability TEXT,
    category TEXT,
    side_effect TEXT,
    status TEXT NOT NULL,
    input_summary_json TEXT NOT NULL DEFAULT '{}',
    output_summary_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_summary TEXT,
    duration_ms INTEGER,
    approval_id TEXT,
    action_intent_id TEXT,
    source_chain_json TEXT NOT NULL DEFAULT '[]',
    secrets_redacted INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    session_id TEXT,
    run_id TEXT,
    target_type TEXT NOT NULL,
    target_id TEXT,
    feedback_type TEXT NOT NULL,
    rating INTEGER,
    comment TEXT,
    allow_learning INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data_policies (
    user_id TEXT PRIMARY KEY,
    event_ttl_days INTEGER NOT NULL DEFAULT 90,
    audit_ttl_days INTEGER NOT NULL DEFAULT 180,
    run_event_ttl_days INTEGER NOT NULL DEFAULT 180,
    tool_payload_ttl_days INTEGER NOT NULL DEFAULT 90,
    conversation_retention TEXT NOT NULL DEFAULT 'keep_until_user_deletes',
    allow_product_analytics INTEGER NOT NULL DEFAULT 1,
    allow_learning INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
```

Recommended indexes:

- `user_activity_events(user_id, created_at DESC)`
- `user_activity_events(session_id, created_at DESC)`
- `user_activity_events(page_key, created_at DESC)`
- `tool_invocations(user_id, created_at DESC)`
- `tool_invocations(run_id, created_at ASC)`
- `tool_invocations(tool_name, created_at DESC)`
- `feedback_events(user_id, created_at DESC)`
- `feedback_events(target_type, target_id)`

## 6. User Context Contract

Add a small Agent-side user context resolver.

Inputs:

- explicit request fields: `user_id`, `session_id`, `run_id`
- headers where appropriate: request id, client id, source
- local profile fallback
- runtime-generated `trace_id`

Output:

```json
{
  "user_id": "local",
  "session_id": "sess_x",
  "run_id": "run_x",
  "trace_id": "trace_x",
  "source": "desktop",
  "mode": "finance_safe",
  "toolset": "finance_safe"
}
```

Rules:

- Missing `user_id` falls back to local profile only in Desktop local mode.
- Cross-user reads require explicit admin/control permission.
- Manager/domain packages receive only the resolved `user_id` and necessary scope flags.
- No domain package becomes the source of truth for Desktop identity.

## 7. Proposed HTTP API

Agent routes to add:

- `POST /v1/desktop/events`
  - Records one event or a small batch of frontend behavior events.
  - Uses normal API token, not control token.

- `POST /v1/desktop/feedback`
  - Records feedback on message, run, tool, page, strategy, or model result.
  - Uses normal API token.

- `GET /v1/desktop/users/{user_id}/activity`
  - Lists recent sessions, runs, tool invocations, feedback, and behavior events.
  - Cross-user access requires control/admin gate.

- `GET /v1/desktop/analytics/summary`
  - Returns aggregate counts and quality signals for Desktop dashboards.
  - Control-token gated if it can expose multi-user data.

- `GET /v1/desktop/users/{user_id}/data-policy`
  - Reads retention/learning/product analytics preferences.

- `PATCH /v1/desktop/users/{user_id}/data-policy`
  - Updates user-owned policy. Admin override requires control gate.

Fallback/simple ASGI branch in `server.py` must stay aligned for routes that are implemented there.

## 8. Desktop Integration Plan

Primary files:

- `desktop/src/services/aiaskApi.ts`
- `desktop/src/mockApi.ts`
- workbench, sessions, runs/events, tools/intents/approvals, settings, local user pages

Add:

- `AiaskApi.recordEvents(events)`
- `AiaskApi.recordFeedback(body)`
- `AiaskApi.userActivity(userId, filters)`
- `AiaskApi.userDataPolicyGet(userId)`
- `AiaskApi.userDataPolicySave(userId, patch)`

Event instrumentation should start narrow:

- page view on main workspace changes
- workbench send/stop/steer/resume
- session open and message load
- run detail open and run event stream errors
- tool invocation from Desktop tool pages
- approval confirm/deny
- search submit
- data sync plan intent creation
- feedback click/comment

Avoid:

- keypress tracking
- raw prompt duplication in behavior events
- raw secrets or form credentials

## 9. Tool Invocation Audit Plan

Primary files:

- `packages/agent/src/aiask_agent/runtime.py`
- `packages/agent/src/aiask_agent/tool_registry.py`
- `packages/agent/src/aiask_agent/server.py`
- `packages/agent/src/aiask_agent/session_store.py`

Implementation approach:

1. Add `record_tool_invocation_start`.
2. Add `record_tool_invocation_finish`.
3. Wrap model-driven `agent_*` tool execution in the runtime.
4. Wrap direct HTTP `/v1/tools/{tool_name}` and `/v1/hermes/admin/tools/{tool_name}` calls.
5. Link ActionIntent/Approval ids when present.
6. Store sanitized summaries instead of raw payloads.

Sanitization rules:

- Redact known secret keys by name.
- Truncate large JSON.
- Store counts, status, ids, symbols, and error codes instead of full raw payloads when possible.
- Mark `secrets_redacted=true` by default.

## 10. Privacy, Security, And Retention

Default retention:

- frontend behavior events: 90 days
- detailed tool input/output summaries: 90 days
- HTTP/audit logs: 180 days
- run events: 180 days
- approvals and trade-risk events: 365 days or configured policy
- conversation messages: keep until user deletes, with export/delete controls
- long-term memory: keep until user deletes or memory policy expires it

Deletion model:

- User-facing delete should remove or anonymize personal records.
- Audit-required records may be retained with content removed and ids anonymized where possible.
- Side-effect history should not pretend external side effects were rolled back.

Security requirements:

- No `.env` values in responses, logs, analytics, or docs.
- No raw API keys, passwords, broker tokens, cookies, or refresh tokens in event payloads.
- Cross-user reads must be gated.
- Multi-user analytics must aggregate by default.

## 11. Development Phases

### Phase 0: Design Confirmation

Deliverable:

- This plan in the repository root.

Exit criteria:

- User confirms whether to proceed with development.
- Scope is agreed: P0 only or P0 plus selected P1 items.

### Phase 1: Agent Storage And Context

Deliverables:

- Extend `AgentSessionStore` schema.
- Add user context resolver.
- Add event, tool invocation, feedback, and policy methods.
- Add focused unit tests.

Suggested tests:

- schema migration creates new tables and indexes
- event batch insert/list works
- tool invocation start/finish updates status and duration
- sanitizer redacts secret-like keys
- data policy defaults are stable

### Phase 2: Agent HTTP Routes

Deliverables:

- Add FastAPI routes.
- Keep simple ASGI fallback aligned where needed.
- Add API contract tests.

Suggested tests:

- `POST /v1/desktop/events`
- `POST /v1/desktop/feedback`
- `GET /v1/desktop/users/{user_id}/activity`
- cross-user access rejection without control/admin gate
- `GET/PATCH data-policy`

### Phase 3: Tool Invocation Wrapping

Deliverables:

- Runtime records model-driven tool calls.
- Direct HTTP tool invocation records audit rows.
- Approval/action intent ids are linked where available.

Suggested tests:

- successful tool records `succeeded`
- failing tool records `failed` and error code
- side-effect metadata is preserved
- raw secrets are redacted from summaries

### Phase 4: Desktop Event And Feedback Integration

Deliverables:

- API client methods.
- Mock API support.
- Narrow instrumentation on core pages.
- Local User page shows activity and policy.

Suggested tests:

- `desktop/src/services/aiaskApi.test.ts`
- relevant hook/component tests
- mock e2e for event submission and feedback submission

### Phase 5: Retention And Analytics

Deliverables:

- Retention sweep for Agent state database.
- Dry-run first, apply gated.
- Analytics summary route.
- Desktop dashboard panels.

Suggested tests:

- dry-run does not delete
- apply deletes only allowlisted rows older than policy
- minimum keep floor works
- market data tables are never affected

## 12. Acceptance Criteria For P0

P0 is complete only when:

- New Agent tables exist and are migrated safely on existing state databases.
- Every Agent response/run can be associated with `user_id`, `session_id`, `run_id`, and `trace_id` where applicable.
- Desktop can submit behavior events without control token.
- Tool invocations are recorded for model-driven and direct HTTP tool calls.
- Input/output summaries are redacted and bounded.
- User feedback can be recorded.
- User activity can be queried by user in Desktop.
- Cross-user access is gated.
- Retention policy defaults are queryable and editable by the owning user.
- Tests cover storage, HTTP contracts, redaction, tool audit, and Desktop client behavior.

## 13. Open Questions Before Development

1. Should P0 store data only in Agent state SQLite first, or also mirror selected user/profile data into Quant Core `app_users` immediately?
2. Should product analytics be opt-out by default for local Desktop, or opt-in from the start?
3. Should conversation retention default to permanent local history, 180 days, or user-configurable on first launch?
4. Should full message content be allowed for learning only after explicit user feedback, or can the system derive private local-only summaries automatically?
5. Which pages should be instrumented in the first Desktop pass: Workbench only, or Workbench plus Sessions/Runs/Tools/Approvals?

## 14. Recommended Initial Scope

Recommended first implementation scope:

- Agent state SQLite only.
- P0 schema plus storage methods.
- `POST /v1/desktop/events`.
- `POST /v1/desktop/feedback`.
- tool invocation audit wrapper.
- activity query for Local User page.
- minimal Desktop instrumentation for Workbench, Sessions, Runs/Events, Tools/Approvals.
- retention policy table with defaults, but retention sweep can be implemented in the next phase if needed.

This gives AIASK immediate product optimization data without overcommitting to a large account/auth rewrite.
