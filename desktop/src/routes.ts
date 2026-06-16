import type { MainView } from "./types";

export const ROUTES = {
  HOME: "/",
  WORKBENCH: "/",
  RUNS: "/runs",
  ARTIFACTS: "/artifacts",
  INTEGRATIONS: "/integrations",
  INTEGRATIONS_MCP: "/integrations/mcp",
  INTEGRATIONS_PLUGINS: "/integrations/plugins",
  INTEGRATIONS_TOOLS: "/integrations/tools",
  INTEGRATIONS_GATEWAY: "/integrations/gateway",
  FINANCE: "/finance",
  FINANCE_MANAGER: "/finance/manager",
  FINANCE_MARKET_TEMPERATURE: "/finance/market-temperature",
  FINANCE_QUANT: "/finance/quant",
  FINANCE_STRATEGY: "/finance/strategy",
  FINANCE_FACTOR: "/finance/factor",
  FINANCE_INCUBATION: "/finance/incubation",
  FINANCE_DATA: "/finance/data",
  FINANCE_WORKFLOWS: "/finance/workflows",
  FINANCE_EVENTS: "/finance/events",
  READINESS: "/readiness",
  SETTINGS: "/settings",
  SESSIONS: "/sessions",
  MODELS: "/settings/models",
  PROJECTS: "/projects",
  AUTOMATION: "/automation",
  EXTENSIONS: "/extensions",
  LEGACY_OVERVIEW: "/legacy/overview",
  LEGACY_AGENT: "/legacy/agent",
  LEGACY_CAPABILITIES: "/legacy/capabilities",
  LEGACY_COVERAGE: "/legacy/coverage",
  LEGACY_TOOLS: "/legacy/tools",
  LEGACY_MCP: "/legacy/mcp",
  LEGACY_DIAGNOSTICS: "/legacy/diagnostics",
  LEGACY_EVENT_CONSOLE: "/legacy/event-console",
  LEGACY_SKILLS: "/legacy/skills",
  LEGACY_USER: "/legacy/user"
} as const;

const VIEW_ROUTES: Record<MainView, string> = {
  workbench: ROUTES.WORKBENCH,
  "projects-contexts": ROUTES.PROJECTS,
  sessions: ROUTES.SESSIONS,
  "runs-events": ROUTES.RUNS,
  artifacts: ROUTES.ARTIFACTS,
  "tools-intents-approvals": ROUTES.INTEGRATIONS_TOOLS,
  "finance-lab": ROUTES.FINANCE,
  integrations: ROUTES.INTEGRATIONS,
  "plugins-skills": ROUTES.INTEGRATIONS_PLUGINS,
  "extensions-pilot": ROUTES.EXTENSIONS,
  "financial-manager": ROUTES.FINANCE_MANAGER,
  "market-temperature": ROUTES.FINANCE_MARKET_TEMPERATURE,
  automation: ROUTES.AUTOMATION,
  data: ROUTES.FINANCE_DATA,
  "factor-factory": ROUTES.FINANCE_FACTOR,
  "factory-events": ROUTES.FINANCE_EVENTS,
  gateway: ROUTES.INTEGRATIONS_GATEWAY,
  incubation: ROUTES.FINANCE_INCUBATION,
  "mcp-connectors": ROUTES.INTEGRATIONS_MCP,
  quant: ROUTES.FINANCE_QUANT,
  "readiness-health": ROUTES.READINESS,
  settings: ROUTES.SETTINGS,
  "strategy-factory": ROUTES.FINANCE_STRATEGY,
  workflows: ROUTES.FINANCE_WORKFLOWS,
  agent: ROUTES.LEGACY_AGENT,
  capabilities: ROUTES.LEGACY_CAPABILITIES,
  coverage: ROUTES.LEGACY_COVERAGE,
  diagnostics: ROUTES.LEGACY_DIAGNOSTICS,
  "event-console": ROUTES.LEGACY_EVENT_CONSOLE,
  mcp: ROUTES.LEGACY_MCP,
  models: ROUTES.MODELS,
  overview: ROUTES.LEGACY_OVERVIEW,
  tools: ROUTES.LEGACY_TOOLS,
  skills: ROUTES.LEGACY_SKILLS,
  user: ROUTES.LEGACY_USER
};

const ROUTE_VIEWS = new Map<string, MainView>(
  Object.entries(VIEW_ROUTES).map(([view, route]) => [route, view as MainView])
);

const ROUTE_ALIASES: Record<string, MainView> = {
  "/workbench": "workbench",
  "/runs-events": "runs-events",
  "/agent-artifacts": "artifacts",
  "/readiness-health": "readiness-health",
  "/finance-lab": "finance-lab",
  "/financial-manager": "financial-manager",
  "/market-temperature": "market-temperature",
  "/factory-events": "factory-events",
  "/mcp-connectors": "mcp-connectors",
  "/plugins-skills": "plugins-skills",
  "/tools-intents-approvals": "tools-intents-approvals",
  "/projects-contexts": "projects-contexts",
  "/automations": "automation",
  "/extensions-pilot": "extensions-pilot",
  "/models": "models",
  "/overview": "overview",
  "/agent": "agent",
  "/capabilities": "capabilities",
  "/coverage": "coverage",
  "/tools": "tools",
  "/mcp": "mcp",
  "/diagnostics": "diagnostics",
  "/event-console": "event-console",
  "/skills": "skills",
  "/user": "user"
};

export interface ViewRouteMatch {
  view: MainView;
  matched: boolean;
}

export function viewToRoute(view: MainView): string {
  return VIEW_ROUTES[view] || ROUTES.HOME;
}

export function routeToView(pathname: string): ViewRouteMatch {
  const normalized = normalizeRoutePath(pathname);
  const direct = ROUTE_VIEWS.get(normalized) || ROUTE_ALIASES[normalized];
  if (direct) return { view: direct, matched: true };
  if (normalized.startsWith("/thread/")) return { view: "workbench", matched: true };
  return { view: "workbench", matched: false };
}

export function navigationParentView(view: MainView): MainView {
  if (
    [
      "financial-manager",
      "market-temperature",
      "quant",
      "strategy-factory",
      "factor-factory",
      "incubation",
      "data",
      "workflows",
      "factory-events"
    ].includes(view)
  ) {
    return "finance-lab";
  }
  if (["mcp-connectors", "gateway", "plugins-skills", "tools-intents-approvals"].includes(view)) {
    return "integrations";
  }
  return view;
}

export function isViewRouteActive(pathname: string, view: MainView): boolean {
  const match = routeToView(pathname);
  if (!match.matched) return false;
  const activeView = match.view;
  return navigationParentView(activeView) === view || activeView === view;
}

function normalizeRoutePath(pathname: string): string {
  const clean = pathname.split("?")[0]?.replace(/\/+$/, "") || "/";
  return clean || "/";
}
