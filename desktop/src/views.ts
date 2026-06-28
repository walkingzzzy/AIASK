import {
  Activity,
  BarChart3,
  Bot,
  BrainCircuit,
  BriefcaseBusiness,
  ClipboardCheck,
  CloudCog,
  Database,
  Gauge,
  GitBranch,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  LineChart,
  MemoryStick,
  MessageSquareText,
  Network,
  PlugZap,
  Radar,
  ScrollText,
  Settings,
  Sparkles,
  UserRound,
  TableProperties,
  TrendingUp,
  Star
} from "lucide-react";

import { V1_ROUTES } from "./routes";
import type { ViewDefinition } from "./types";

export const V1_VIEWS: ViewDefinition[] = [
  {
    id: "workbench",
    label: "Workbench",
    shortLabel: "Workbench",
    route: V1_ROUTES.workbench,
    group: "core",
    description: "Thread-first task workspace with timeline, composer, artifacts, approvals, and review entry points.",
    icon: MessageSquareText,
    spec: "workbench-layout"
  },
  {
    id: "projects-contexts",
    label: "Projects & Models",
    shortLabel: "Projects",
    route: V1_ROUTES["projects-contexts"],
    group: "core",
    description: "Project context, user profile, evidence references, and environment boundaries.",
    icon: BriefcaseBusiness,
    spec: "projects-context"
  },
  {
    id: "user-profile",
    label: "Projects & Models",
    shortLabel: "Profile",
    route: V1_ROUTES["user-profile"],
    group: "core",
    description: "Investment profile, preferences, memory signals, and reusable personal context.",
    icon: UserRound,
    spec: "user-profile"
  },
  {
    id: "models",
    label: "Projects & Models",
    shortLabel: "Models",
    route: V1_ROUTES.models,
    group: "core",
    description: "Provider readiness, model availability, connection settings, and smoke tests.",
    icon: KeyRound,
    spec: "model-readiness"
  },
  {
    id: "sessions-runs",
    label: "Runs",
    shortLabel: "Runs",
    route: V1_ROUTES["sessions-runs"],
    group: "core",
    description: "Linked sessions, runs, events, artifacts, and evidence trails.",
    icon: ScrollText,
    spec: "runs-evidence"
  },
  {
    id: "tools-approvals",
    label: "Approvals",
    shortLabel: "Approvals",
    route: V1_ROUTES["tools-approvals"],
    group: "core",
    description: "Unified review flow for tools, ActionIntents, approval queues, and decisions.",
    icon: ClipboardCheck,
    spec: "approvals-flow"
  },
  {
    id: "finance-lab",
    label: "Finance Lab",
    shortLabel: "Overview",
    route: V1_ROUTES["finance-lab"],
    group: "finance",
    description: "Finance shell for overview, data, radar, temperature, quant, and manager surfaces.",
    icon: LayoutDashboard,
    spec: "finance-lab"
  },
  {
    id: "stock-data-sources",
    label: "Finance Lab",
    shortLabel: "Data Sources",
    route: V1_ROUTES["stock-data-sources"],
    group: "finance",
    description: "Stock data provider setup, testing, redaction, and readiness status.",
    icon: Database,
    spec: "stock-data-sources"
  },
  {
    id: "data-sync",
    label: "Finance Lab",
    shortLabel: "Data Sync",
    route: V1_ROUTES["data-sync"],
    group: "finance",
    description: "Database status, freshness, missing items, and dry-run sync planning.",
    icon: TableProperties,
    spec: "data-sync"
  },
  {
    id: "stock-radar",
    label: "Finance Lab",
    shortLabel: "Radar",
    route: V1_ROUTES["stock-radar"],
    group: "finance",
    description: "Candidate stocks, digest summaries, risk signals, and controlled actions.",
    icon: Radar,
    spec: "stock-radar"
  },
  {
    id: "market-temperature",
    label: "Finance Lab",
    shortLabel: "Temperature",
    route: V1_ROUTES["market-temperature"],
    group: "finance",
    description: "Market breadth, hot and cold sectors, cache readiness, and read-only diagnostics.",
    icon: Gauge,
    spec: "market-temperature"
  },
  {
    id: "quant-research",
    label: "Finance Lab",
    shortLabel: "Quant",
    route: V1_ROUTES["quant-research"],
    group: "finance",
    description: "Presets, research runs, reports, metrics, and evidence panels.",
    icon: LineChart,
    spec: "quant-research"
  },
  {
    id: "financial-manager",
    label: "Finance Lab",
    shortLabel: "Manager",
    route: V1_ROUTES["financial-manager"],
    group: "finance",
    description: "Catalog, status, read-only query, controlled intents, and broker read-only data.",
    icon: BarChart3,
    spec: "financial-manager"
  },
  {
    id: "my-strategy",
    label: "Personal Assets",
    shortLabel: "My Strategy",
    route: "/personal/my-strategy",
    group: "personal",
    description: "Manage personal investment strategies, track performance and holdings.",
    icon: TrendingUp,
    spec: "my-strategy"
  },
  {
    id: "my-stocks",
    label: "Personal Assets",
    shortLabel: "My Stocks",
    route: "/personal/my-stocks",
    group: "personal",
    description: "Manage personal stock pools with tags and notes.",
    icon: Star,
    spec: "my-stocks"
  },
  {
    id: "integrations",
    label: "Integrations",
    shortLabel: "Overview",
    route: V1_ROUTES.integrations,
    group: "integrations",
    description: "Top-level shell for MCP, connectors, plugins, skills, and gateway surfaces.",
    icon: Network,
    spec: "integrations-overview"
  },
  {
    id: "mcp-connectors",
    label: "Integrations",
    shortLabel: "MCP",
    route: V1_ROUTES["mcp-connectors"],
    group: "integrations",
    description: "MCP servers, tools, resources, prompts, OAuth, and connector health.",
    icon: PlugZap,
    spec: "mcp-connectors"
  },
  {
    id: "plugins-skills",
    label: "Integrations",
    shortLabel: "Plugins",
    route: V1_ROUTES["plugins-skills"],
    group: "integrations",
    description: "Runtime skills, plugins, commands, self-tests, and controlled changes.",
    icon: Sparkles,
    spec: "plugins-skills"
  },
  {
    id: "gateway-webhooks",
    label: "Integrations",
    shortLabel: "Gateway",
    route: V1_ROUTES["gateway-webhooks"],
    group: "integrations",
    description: "Platform status, message directory, daemon state, and webhook feedback.",
    icon: CloudCog,
    spec: "gateway-webhooks"
  },
  {
    id: "automation",
    label: "Automations",
    shortLabel: "Triage",
    route: V1_ROUTES.automation,
    group: "ops",
    description: "Triage inbox, historical runs, scheduled tasks, and controlled job actions.",
    icon: GitBranch,
    spec: "automation-triage"
  },
  {
    id: "workflows",
    label: "Automations",
    shortLabel: "Workflow",
    route: V1_ROUTES.workflows,
    group: "ops",
    description: "Workflow map from data intake through radar, market, quant, manager, and gateway.",
    icon: Activity,
    spec: "workflow-map"
  },
  {
    id: "readiness-health",
    label: "Operations",
    shortLabel: "Readiness",
    route: V1_ROUTES["readiness-health"],
    group: "ops",
    description: "Environment status, gates, health diagnostics, capabilities, and next actions.",
    icon: HeartPulse,
    spec: "readiness-health"
  },
  {
    id: "local-user-memory",
    label: "Operations",
    shortLabel: "Memory",
    route: V1_ROUTES["local-user-memory"],
    group: "ops",
    description: "Local profile, activity, data policy, export, and delete previews.",
    icon: MemoryStick,
    spec: "local-user-memory"
  },
  {
    id: "learning-rl",
    label: "Operations",
    shortLabel: "Learning / RL",
    route: V1_ROUTES["learning-rl"],
    group: "ops",
    description: "Learning status, review proposals, RL environments, and run inspection.",
    icon: BrainCircuit,
    spec: "learning-rl"
  },
  {
    id: "native-diagnostics",
    label: "Operations",
    shortLabel: "Native",
    route: V1_ROUTES["native-diagnostics"],
    group: "ops",
    description: "Read-only diagnostics for files, terminal, browser, and process capabilities.",
    icon: Bot,
    spec: "native-diagnostics"
  },
  {
    id: "settings-security",
    label: "Settings",
    shortLabel: "Settings",
    route: V1_ROUTES["settings-security"],
    group: "ops",
    description: "Connection, token, mode, theme, shortcut, and advanced settings.",
    icon: Settings,
    spec: "settings-security"
  }
];

export const NAV_GROUPS = [
  { id: "core", label: "Task Workspace" },
  { id: "finance", label: "Finance Research" },
  { id: "personal", label: "Personal Assets" },
  { id: "integrations", label: "Integration Surfaces" },
  { id: "ops", label: "Automation & Ops" }
] as const;
