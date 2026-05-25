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
  Gauge,
  Layers3,
  MessageSquare,
  Radio,
  ServerCog,
  Settings,
  UserRound,
  Wrench,
  Zap
} from "lucide-react";
import type { ElementType } from "react";
import type { MainView } from "./types";

export interface ViewRegistryItem {
  id: MainView;
  label: string;
  icon: ElementType;
}

export const VIEW_REGISTRY: ViewRegistryItem[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "workbench", label: "Agent", icon: MessageSquare },
  { id: "coverage", label: "Coverage Matrix", icon: ClipboardList },
  { id: "models", label: "Models", icon: BrainCircuit },
  { id: "data", label: "Data & Sync", icon: Database },
  { id: "mcp", label: "MCP", icon: ServerCog },
  { id: "skills", label: "Skills", icon: Layers3 },
  { id: "automation", label: "Automation", icon: CalendarClock },
  { id: "strategy-factory", label: "Strategy Factory", icon: Factory },
  { id: "factor-factory", label: "Factor Factory", icon: BarChart3 },
  { id: "incubation", label: "Incubation", icon: FlaskConical },
  { id: "user", label: "Local User", icon: UserRound },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "capabilities", label: "Capabilities", icon: Boxes },
  { id: "event-console", label: "Event Console", icon: Zap },
  { id: "factory-events", label: "Factory Events", icon: Radio },
  { id: "diagnostics", label: "Diagnostics", icon: Activity },
  { id: "agent", label: "Agent Status", icon: Bot },
  { id: "settings", label: "Settings", icon: Settings }
];
