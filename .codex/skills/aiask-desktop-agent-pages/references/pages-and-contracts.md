# Desktop Agent Pages And Contracts

## Pages

Primary files: `desktop/src/pages/AgentPages.tsx`, `desktop/src/pages/IntegrationPages.tsx`, and `desktop/src/pages/OpsPages.tsx`.

Current pages:

- `WorkbenchPage`: thread-first workspace with message composer, file upload, response streaming, artifacts, review tabs, and finance context.
- `SessionsRunsPage`: recent sessions, run summaries, event loading, filters, resume flow, run steer/stop/cancel, and event drill-down.
- `ToolsApprovalsPage`: tool directory, intent queue, approvals review, and gated action handling.
- `McpConnectorsPage`: MCP server CRUD, tools/resources/prompts inspection, OAuth, and connector summary/testing through Agent routes.
- `PluginsSkillsPage`: runtime skill and plugin state, create/toggle/delete flows, self-tests, and preview actions.
- `GatewayWebhooksPage`: platform status, daemon state, pairing, directory refresh, messages, retries, send preview, and webhook visibility.
- `ReadinessHealthPage`: readiness dimensions, capability parity, financial-system gates, and navigation to remediation surfaces.
- `LocalUserMemoryPage` and `LearningRlPage`: local profile/data policy visibility, learning review/apply, RL environments, RL runs, and result/log inspection.
- `Enhanced*Pages` wrappers route V1 views onto these current page modules and hide direct Strategy/Factor/Incubation product entry points from the primary Desktop navigation.

## API Usage

Use `AiaskApi` methods for:

- `workbenchSummary`, `runsList`, `runEvents`, `sessionsList`, `sessionMessages`.
- `tools`, `intentsList`, `approvalsList`, approval decisions.
- `gatewayStatus`, `gatewayDaemon`, `gatewayPlatforms`, `gatewayPairing`, `gatewayMessages`, `gatewayDirectory`, retry/start/stop/health.
- `mcp*` endpoints and connector routes.
- `skills`, skill create/update/delete, plugin list/enable/test/commands.
- `jobs`, `learning*`, `rl*`, `capabilityParity`, readiness, health, and full/native diagnostics.

When adding an Agent page control:

- Prefer read-only route first.
- Use ActionIntent or gated API for mutation.
- Update `desktop/src/mock/mockData.ts`, `desktop/src/services/aiaskApi.ts`, and relevant tests.
- Make unavailable/gated/degraded states visible.

## Navigation

`desktop/src/views.ts` and `desktop/src/routes.ts` are the route/view registry. Task workspace, integrations, and ops pages live there; the current app shell favors those surfaces over direct legacy feature entries.

`App.tsx` owns `selectView`, `viewRenderers`, and the shell layout. Keep replacement navigation centralized there rather than duplicating routing logic in individual pages.

## Tests

Run:

- `npm test` for component/page tests.
- `npm run test:e2e:mock` when navigation, visible page matrix, or safe mock controls change.

Useful page tests:

- `desktop/src/services/aiaskApi.test.ts`
- `desktop/src/App.test.tsx`
- `desktop/e2e/aiask-v1.spec.ts`
- `desktop/e2e/aiask-v1-p0-p4-completeness.spec.ts`
