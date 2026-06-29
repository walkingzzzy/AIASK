# Desktop API And UI Workflows

## Stack And Boundary

Primary manifest: `desktop/package.json`.

Stack:

- React 18, Vite 6, TypeScript.
- Tauri 2 CLI.
- `lucide-react` icons.
- Vitest/jsdom and Playwright.

Desktop consumes the Agent HTTP API through `desktop/src/services/aiaskApi.ts` and local mock support through `desktop/src/mock/mockData.ts`. It must not call Python packages, AKShare MCP, Strategy Factory, or managers directly.

## Current App Shape

The app shell in `desktop/src/App.tsx` uses:

- `desktop/src/views.ts` for primary, finance, ops, and legacy view groups.
- `desktop/src/routes.ts` for route-to-view mapping.
- the current shell/sidebar/inspector/context composition inside `App.tsx`.
- `useConnectionSettings` for endpoint/token/profile/mode state.
- `useAsyncResource` plus `AiaskApi` methods for workbench, sessions, runs, approvals, and page data.

Current main view groups:

- Task Workspace: Workbench, Projects & Models, Runs, Approvals.
- Finance Research: Finance Lab, Data Sources, Data Sync, Stock Radar, Market Temperature, Quant Research, Financial Manager.
- Integration Surfaces: Integrations overview, MCP / Connectors, Plugins / Skills, Gateway / Webhooks.
- Automation & Ops: Automation, Workflows, Readiness / Health, Local User Memory, Learning / RL, Native Diagnostics, Settings.
- Personal Assets remain lightweight local pages; direct Strategy / Factor / Incubation product entries are intentionally hidden from the primary Desktop navigation.

## API Client Areas

`AiaskApi` currently wraps:

- Health, detailed health, tools, capabilities, Hermes status/readiness/parity.
- Desktop settings, data status/sync plan, local profile.
- Workbench summary, recent runs, sessions, session messages, run events, run stop/steer/cancel.
- AI status/smoke/models and `/v1/responses`.
- Read-only tool calls and ActionIntent create/get/confirm/deny.
- Stock radar status/candidates/digest.
- Quant research presets/runs/reports.
- Financial Manager catalog/status/query/intent.
- Factor factory status and controlled intent flows through Agent APIs.
- Skills, plugins, plugin tools/commands.
- MCP servers/tools/resources/prompts/OAuth/resource read/prompt get.
- Gateway status, daemon status, platforms, pairing, messages, directory, send intent, retry, start/stop/health.
- Approvals, connectors, webhooks, jobs, learning, RL, security/ops panels.

When adding or changing API methods, update mock behavior and targeted tests.

## Finance Workspaces

Current finance pages are implemented primarily in `desktop/src/pages/FinancePages.tsx` and `desktop/src/pages/EnhancedFinancePages.tsx`.

Important active product surfaces:

- Finance Lab overview and boundary notice.
- Data source and sync readiness flows.
- Stock Radar candidates, digest, and intent creation.
- Quant research runs and reports.
- Financial Manager read-only broker and controlled intent flows.

Strategy / Factor / Incubation capabilities still exist in backend and runtime layers, but the Desktop V1 shell treats them as internal or redirected capabilities rather than first-class visible product entries.

## UI Rules

- Use existing components and CSS classes before adding new patterns.
- Keep operational pages dense, scannable, and restrained.
- Use icons from `lucide-react`.
- Keep button/action labels clear about gated, read-only, mock, dry-run, approval, and trade-risk states.
- Do not add marketing or landing pages.
- Do not put Desktop-side controls around backend guardrails; backend policy remains authoritative.
