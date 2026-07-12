import type { AiaskApi } from "../services/aiaskApi";
import { objectData, toList } from "../services/api/core";
import type {
  ConnectionSettings,
  Metric,
  Tone,
  UnknownRecord,
  ViewId,
  WorkbenchContext
} from "../types";

export interface PageProps {
  view: ViewId;
  api: AiaskApi;
  settings?: ConnectionSettings;
  updateSettings?: (patch: Partial<ConnectionSettings>) => void;
  controlAvailable: boolean;
  workbench?: WorkbenchContext;
  setSelectedThreadId?: (threadId: string) => void;
  setSelectedRunId?: (runId: string) => void;
  setSelectedMessageId?: (messageId: string) => void;
  setSelectedApprovalId?: (approvalId: string) => void;
  setSelectedArtifactId?: (artifactId: string) => void;
  setSelectedReviewTab?: (tab: WorkbenchContext["selectedReviewTab"]) => void;
  reloadWorkbench?: () => Promise<void>;
  realtimeConnected?: boolean;
}

export function list<T extends UnknownRecord = UnknownRecord>(payload: unknown): T[] {
  return toList<T>(payload);
}

export function dataObject<T extends UnknownRecord = UnknownRecord>(payload: unknown, fallback: UnknownRecord = {}): T {
  return objectData<T>(payload, fallback as T);
}

export function valueOf(record: UnknownRecord, keys: string[], fallback = "-"): string {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== "") return String(value);
  }
  return fallback;
}

export function statusTone(status: unknown): Tone {
  const normalized = String(status || "").toLowerCase();
  if (["ready", "ok", "success", "completed", "available", "connected", "active"].some((item) => normalized.includes(item))) {
    return "success";
  }
  if (["warn", "stale", "missing", "pending", "degraded", "requires"].some((item) => normalized.includes(item))) {
    return "warning";
  }
  if (["error", "failed", "blocked", "invalid", "down"].some((item) => normalized.includes(item))) {
    return "danger";
  }
  if (["gated", "control"].some((item) => normalized.includes(item))) {
    return "gated";
  }
  return "neutral";
}

export function metric(label: string, value: unknown, tone: Tone = "neutral", detail?: string): Metric {
  return {
    label,
    value: value === undefined || value === null || value === "" ? "-" : String(value),
    tone,
    detail
  };
}

export function firstArray(record: UnknownRecord, preferred: string[]): UnknownRecord[] {
  for (const key of preferred) {
    const value = record[key];
    if (Array.isArray(value)) return value as UnknownRecord[];
  }
  const found = Object.values(record).find(Array.isArray);
  return Array.isArray(found) ? (found as UnknownRecord[]) : [];
}
