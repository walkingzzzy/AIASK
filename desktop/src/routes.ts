import type { DeferredViewId, ViewId } from "./types";

export const V1_DEFERRED_VIEWS: readonly DeferredViewId[] = [
  "strategy-factory",
  "factor-factory",
  "incubation",
  "factory-events"
] as const;

export const V1_ROUTES: Record<ViewId, string> = {
  workbench: "/",
  models: "/models",
  "projects-contexts": "/projects",
  "user-profile": "/user-profile",
  "sessions-runs": "/sessions-runs",
  "tools-approvals": "/tools-approvals",
  integrations: "/integrations",
  "mcp-connectors": "/mcp-connectors",
  "plugins-skills": "/plugins-skills",
  "gateway-webhooks": "/gateway-webhooks",
  "stock-data-sources": "/stock-data-sources",
  "data-sync": "/data-sync",
  "finance-lab": "/finance",
  "stock-radar": "/stock-radar",
  "market-temperature": "/market-temperature",
  "quant-research": "/quant-research",
  "financial-manager": "/financial-manager",
  "my-strategy": "/personal/my-strategy",
  "my-stocks": "/personal/my-stocks",
  automation: "/automation",
  workflows: "/workflows",
  "settings-security": "/settings",
  "readiness-health": "/readiness",
  "local-user-memory": "/local-user-memory",
  "learning-rl": "/learning-rl",
  "native-diagnostics": "/native-diagnostics"
};

export const DEFERRED_ROUTE_ALIASES: Record<string, ViewId> = {
  "/approvals": "tools-approvals",
  "/mcp": "mcp-connectors",
  "/connectors": "mcp-connectors",
  "/skills": "plugins-skills",
  "/plugins": "plugins-skills",
  "/gateway": "gateway-webhooks",
  "/finance-lab": "finance-lab",
  "/user": "local-user-memory",
  "/profile": "user-profile",
  "/strategy-factory": "finance-lab",
  "/factor-factory": "finance-lab",
  "/incubation": "finance-lab",
  "/factory-events": "finance-lab",
  "/finance/strategy": "finance-lab",
  "/finance/factor": "finance-lab",
  "/finance/incubation": "finance-lab",
  "/finance/events": "finance-lab"
};

const VIEW_BY_ROUTE = Object.entries(V1_ROUTES).reduce<Record<string, ViewId>>(
  (acc, [view, route]) => ({ ...acc, [route]: view as ViewId }),
  {}
);

export function routeToView(pathname: string): ViewId {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  return VIEW_BY_ROUTE[normalized] ?? DEFERRED_ROUTE_ALIASES[normalized] ?? "workbench";
}

export function viewToRoute(view: ViewId): string {
  return V1_ROUTES[view];
}

export function isDeferredView(view: string): view is DeferredViewId {
  return V1_DEFERRED_VIEWS.includes(view as DeferredViewId);
}

export const V1_COMPATIBLE_ALIASES = Object.entries(DEFERRED_ROUTE_ALIASES).map(([path, view]) => ({
  path,
  view
}));
