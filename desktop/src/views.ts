import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  BrainCircuit,
  CalendarClock,
  ClipboardList,
  Database,
  Factory,
  FlaskConical,
  FolderGit2,
  GitBranchPlus,
  Landmark,
  LayoutList,
  LineChart,
  MessageSquare,
  MessagesSquare,
  PlugZap,
  Puzzle,
  Radio,
  SearchCheck,
  ServerCog,
  Settings,
  ShieldCheck,
  UserRound,
  Wrench,
  Zap,
} from "lucide-react";
import type { ElementType } from "react";
import type { ComponentType, ReactNode } from "react";
import type { MainView } from "./types";

export interface ViewRegistryItem {
  id: MainView;
  label: string;
  icon: ElementType;
  description: string;
  group: "workspace" | "finance" | "ops" | "settings" | "agent" | "legacy";
  route?: string;
  requiresControlToken?: boolean;
  requiresFullMode?: boolean;
  mountPosition?: "primary" | "secondary" | "hidden";
  render?: () => ReactNode;
  component?: ComponentType<Record<string, never>>;
  legacy?: boolean;
  replacementView?: MainView;
  badge?: string;
  diagnosticOnly?: boolean;
}

export interface ViewGroup {
  id: string;
  label: string;
  items: ViewRegistryItem[];
  defaultCollapsed?: boolean;
  diagnosticOnly?: boolean;
}

export const VIEW_REGISTRY: ViewRegistryItem[] = [
  {
    id: "workbench",
    label: "Workbench",
    icon: MessageSquare,
    description: "Agent primary entry with a session-first workflow.",
    group: "workspace",
    route: "/workbench",
    mountPosition: "primary",
  },
  {
    id: "projects-contexts",
    label: "Projects / Contexts",
    icon: FolderGit2,
    description: "Endpoint, project context, backend mode, and environment readiness.",
    group: "workspace",
    route: "/projects-contexts",
    mountPosition: "primary",
  },
  {
    id: "sessions",
    label: "Sessions",
    icon: MessagesSquare,
    description: "Session management and detail view.",
    group: "agent",
    route: "/sessions",
    requiresControlToken: true,
    requiresFullMode: true,
    badge: "Full",
  },
  {
    id: "runs-events",
    label: "Runs / Events",
    icon: LayoutList,
    description: "Run summaries, timeline view, and event filters.",
    group: "agent",
    route: "/runs-events",
  },
  {
    id: "tools-intents-approvals",
    label: "Approvals",
    icon: ShieldCheck,
    description: "Tool catalog, intents, approvals, and control flow.",
    group: "workspace",
    route: "/tools-intents-approvals",
  },
  {
    id: "finance-lab",
    label: "Finance Lab",
    icon: SearchCheck,
    description: "Finance task templates for research, strategy, factor, data, and events.",
    group: "finance",
    route: "/finance-lab",
    mountPosition: "primary",
  },
  {
    id: "integrations",
    label: "Integrations",
    icon: PlugZap,
    description: "Unified MCP, Gateway, Plugins, Skills, and connector health.",
    group: "ops",
    route: "/integrations",
    mountPosition: "primary",
  },
  {
    id: "plugins-skills",
    label: "Plugins / Skills",
    icon: Puzzle,
    description: "Native plugin and skill lifecycle operations.",
    group: "ops",
    route: "/plugins-skills",
    requiresControlToken: true,
    mountPosition: "primary",
  },
  {
    id: "financial-manager",
    label: "Financial Manager",
    icon: Landmark,
    description: "Portfolio, watchlist, risk, and controlled execution.",
    group: "finance",
  },
  {
    id: "quant",
    label: "Quant Research",
    icon: LineChart,
    description: "Research runs and structured reports.",
    group: "finance",
  },
  {
    id: "strategy-factory",
    label: "Strategy Factory",
    icon: Factory,
    description: "Strategy generation, review, and factory status.",
    group: "finance",
  },
  {
    id: "factor-factory",
    label: "Factor Factory",
    icon: BarChart3,
    description: "Factor mining and active pool health.",
    group: "finance",
  },
  {
    id: "incubation",
    label: "Incubation Factory",
    icon: FlaskConical,
    description: "Lifecycle management and hit-rate review.",
    group: "finance",
  },
  {
    id: "data",
    label: "Data",
    icon: Database,
    description: "Data health, sync planning, and freshness checks.",
    group: "finance",
  },
  {
    id: "automation",
    label: "Automations",
    icon: CalendarClock,
    description: "Automation triage, schedules, and workflow runs.",
    group: "workspace",
    route: "/automations",
    mountPosition: "primary",
  },
  {
    id: "workflows",
    label: "Workflows",
    icon: GitBranchPlus,
    description: "Business workflow hub for finance operations.",
    group: "finance",
  },
  {
    id: "factory-events",
    label: "Factory Events",
    icon: Radio,
    description: "Factory event creation, preview, and review.",
    group: "finance",
    route: "/factory-events",
  },
  {
    id: "mcp-connectors",
    label: "MCP / Connectors",
    icon: PlugZap,
    description: "MCP discovery, auth, and connector health.",
    group: "ops",
    route: "/mcp-connectors",
  },
  {
    id: "gateway",
    label: "Gateway",
    icon: ServerCog,
    description: "Gateway platforms, messages, and directory state.",
    group: "ops",
    route: "/gateway",
  },
  {
    id: "readiness-health",
    label: "Readiness / Health",
    icon: Activity,
    description: "Operational health and system readiness.",
    group: "ops",
    route: "/readiness-health",
  },
  {
    id: "extensions-pilot",
    label: "Extensions Pilot",
    icon: PlugZap,
    description: "Internal AIASK-native page and slot registry.",
    group: "ops",
    route: "/extensions-pilot",
    requiresControlToken: true,
    mountPosition: "secondary",
    badge: "Internal",
  },
  {
    id: "settings",
    label: "Settings",
    icon: Settings,
    description: "Endpoint, tokens, profile, and mode controls.",
    group: "settings",
  },
  {
    id: "overview",
    label: "Overview",
    icon: Boxes,
    description: "Legacy system overview entry.",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "agent",
    label: "Agent",
    icon: Bot,
    description: "Legacy agent runtime page.",
    group: "legacy",
    legacy: true,
    replacementView: "workbench",
    diagnosticOnly: true,
  },
  {
    id: "capabilities",
    label: "Capabilities",
    icon: Boxes,
    description: "Legacy capabilities workbench entry.",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "coverage",
    label: "Coverage",
    icon: ClipboardList,
    description: "Legacy coverage matrix entry.",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "tools",
    label: "Tools",
    icon: Wrench,
    description: "Legacy tool catalog entry.",
    group: "legacy",
    legacy: true,
    replacementView: "tools-intents-approvals",
    diagnosticOnly: true,
  },
  {
    id: "mcp",
    label: "MCP",
    icon: PlugZap,
    description: "Legacy MCP entry.",
    group: "legacy",
    legacy: true,
    replacementView: "mcp-connectors",
    diagnosticOnly: true,
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    icon: Activity,
    description: "Legacy diagnostics entry.",
    group: "legacy",
    legacy: true,
    replacementView: "readiness-health",
    diagnosticOnly: true,
  },
  {
    id: "event-console",
    label: "Event Console",
    icon: Zap,
    description: "Legacy event console entry.",
    group: "legacy",
    legacy: true,
    replacementView: "runs-events",
    diagnosticOnly: true,
  },
  {
    id: "skills",
    label: "Skills",
    icon: BrainCircuit,
    description: "Legacy skills page.",
    group: "legacy",
    legacy: true,
    replacementView: "plugins-skills",
    diagnosticOnly: true,
  },
  {
    id: "user",
    label: "User",
    icon: UserRound,
    description: "Legacy local user page.",
    group: "legacy",
    legacy: true,
    replacementView: "settings",
    diagnosticOnly: true,
  },
  {
    id: "models",
    label: "Models",
    icon: BrainCircuit,
    description: "Legacy model status page.",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
];

function pick(ids: MainView[]): ViewRegistryItem[] {
  return ids.map((id) => {
    const item = VIEW_REGISTRY.find((view) => view.id === id);
    if (!item) throw new Error(`Missing view registry item: ${id}`);
    return item;
  });
}

export const VIEW_GROUPS: ViewGroup[] = [
  {
    id: "primary",
    label: "Workspace",
    items: pick(["workbench", "projects-contexts", "runs-events", "tools-intents-approvals", "finance-lab", "integrations", "automation", "settings"]),
  },
  {
    id: "advanced-finance",
    label: "Advanced Finance",
    defaultCollapsed: true,
    items: pick([
      "financial-manager",
      "quant",
      "strategy-factory",
      "factor-factory",
      "incubation",
      "data",
      "automation",
      "workflows",
      "factory-events",
    ]),
  },
  {
    id: "advanced-ops",
    label: "Advanced Ops",
    defaultCollapsed: true,
    items: pick(["plugins-skills", "mcp-connectors", "gateway", "readiness-health", "extensions-pilot", "settings"]),
  },
  {
    id: "legacy",
    label: "Legacy / Advanced",
    defaultCollapsed: true,
    diagnosticOnly: true,
    items: pick([
      "overview",
      "agent",
      "capabilities",
      "coverage",
      "tools",
      "mcp",
      "diagnostics",
      "event-console",
      "skills",
      "user",
      "models",
    ]),
  },
];

export function getViewItem(view: MainView): ViewRegistryItem | undefined {
  return VIEW_REGISTRY.find((item) => item.id === view);
}
