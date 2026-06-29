---
name: aiask-desktop-agent-pages
description: Use this skill when working on AIASK Desktop task-workspace and integration control pages, including Workbench, Sessions/Runs, Tools/Intents/Approvals, MCP/Connectors, Plugins/Skills, Gateway/Webhooks, Readiness/Health, local memory/learning/RL surfaces, route/view wiring, and related desktop page tests.
---

# AIASK Desktop Agent Pages

## Workflow

1. Read [references/pages-and-contracts.md](references/pages-and-contracts.md) before changing Agent page behavior, API usage, filters, action buttons, or navigation.
2. Read [references/extension-registry.md](references/extension-registry.md) before changing internal extension pages or slots.
3. Keep all pages backed by `AiaskApi`; do not add direct MCP, manager, Python, or filesystem calls.
4. Preserve gate visibility for control token and full mode.
5. Update current page tests, service tests, and mock payload handling when changing page behavior.

## Key Files

- `desktop/src/pages/AgentPages.tsx`
- `desktop/src/pages/IntegrationPages.tsx`
- `desktop/src/pages/OpsPages.tsx`
- `desktop/src/pages/EnhancedAgentPages.tsx`
- `desktop/src/pages/EnhancedIntegrationPages.tsx`
- `desktop/src/pages/EnhancedOpsPages.tsx`
- `desktop/src/views.ts`
- `desktop/src/App.tsx`
- `desktop/src/services/aiaskApi.ts`
- `desktop/src/mock/mockData.ts`
- `desktop/src/services/aiaskApi.test.ts`
- `desktop/e2e/aiask-v1.spec.ts`
