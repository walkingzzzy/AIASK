import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type UnknownRecord = Record<string, unknown>;

export type ApiMode = "mock" | "live";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "gated";

export interface ConnectionSettings {
  baseUrl: string;
  apiToken: string;
  controlToken: string;
  mode: ApiMode;
  userId: string;
}

export interface ApiProblem {
  status: number;
  title: string;
  detail?: string;
  code?: string;
  raw?: unknown;
}

export interface ApiEnvelope<T = unknown> {
  object?: string;
  data?: T;
  success?: boolean;
  error?: string | null;
  error_code?: string | null;
  [key: string]: unknown;
}

export interface Metric {
  label: string;
  value: string | number;
  tone?: Tone;
  detail?: string;
}

export interface TableColumn<T extends UnknownRecord = UnknownRecord> {
  key: keyof T | string;
  header: string;
  render?: (item: T) => ReactNode;
  width?: string;
}

export type ViewId =
  | "workbench"
  | "models"
  | "projects-contexts"
  | "sessions-runs"
  | "tools-approvals"
  | "integrations"
  | "mcp-connectors"
  | "plugins-skills"
  | "gateway-webhooks"
  | "stock-data-sources"
  | "data-sync"
  | "finance-lab"
  | "stock-radar"
  | "market-temperature"
  | "quant-research"
  | "financial-manager"
  | "automation"
  | "workflows"
  | "settings-security"
  | "readiness-health"
  | "local-user-memory"
  | "learning-rl"
  | "native-diagnostics";

export type DeferredViewId =
  | "strategy-factory"
  | "factor-factory"
  | "incubation"
  | "factory-events";

export interface ViewDefinition {
  id: ViewId;
  label: string;
  shortLabel: string;
  route: string;
  group: "core" | "integrations" | "finance" | "ops";
  description: string;
  icon: LucideIcon;
  spec: string;
}

export interface WorkbenchMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  status?: string;
  sources?: UnknownRecord[];
}

export interface RunEvent {
  id?: string | number;
  event_id?: string | number;
  type?: string;
  name?: string;
  status?: string;
  message?: string;
  created_at?: string;
  timestamp?: string;
  data?: unknown;
  payload?: unknown;
}

export interface OptionItem {
  label: string;
  value: string;
}
