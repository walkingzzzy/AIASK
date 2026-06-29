---
name: aiask-desktop-workbench
description: Use this skill when working on the AIASK Desktop React/Vite/Tauri app, including the App shell, view registry, Agent HTTP client, workbench thread flow, finance lab pages, integrations, automation and ops surfaces, local mock payloads, desktop tests, e2e flows, or frontend build commands.
---

# AIASK Desktop Workbench

## Workflow

1. Read [references/api-and-ui-workflows.md](references/api-and-ui-workflows.md) before changing App shell, view routing, API calls, hooks, mock data, or feature panels.
2. Read [references/build-and-tests.md](references/build-and-tests.md) before running validation or changing build/test config.
3. Use `aiask-desktop-agent-pages` for the task-workspace, integrations, and ops control pages when the change is mainly about page behavior or control surfaces.
4. Keep Desktop as an Agent HTTP client only; do not import Python packages or call MCP/managers directly.
5. Preserve the current operational-workbench style, lucide icons, token/mode gates, mock/live distinction, and the V1 decision to hide direct Strategy/Factor/Incubation product entry points behind safer surfaces.

## Key Files

- `desktop/src/App.tsx`
- `desktop/src/views.ts`
- `desktop/src/routes.ts`
- `desktop/src/services/aiaskApi.ts`
- `desktop/src/mock/mockData.ts`
- `desktop/src/hooks/useConnectionSettings.ts`
- `desktop/src/hooks/useAsyncResource.ts`
- `desktop/src/pages/`
- `desktop/src/components/`
- `desktop/e2e/aiask-v1.spec.ts`
- `desktop/e2e/aiask-v1-p0-p4-completeness.spec.ts`
