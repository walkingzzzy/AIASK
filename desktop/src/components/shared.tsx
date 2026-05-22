import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle
} from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { CapabilityMatrixItem } from "../types";

export function compact(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value || "-";
  return JSON.stringify(value);
}

export function shortText(value: string, max = 88): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max - 1)}...` : normalized;
}

export function statusTone(status?: string): "ok" | "warn" | "bad" | "neutral" {
  if (!status) return "neutral";
  const normalized = status.toLowerCase();
  if (["implemented", "ready", "passed", "success", "completed", "online", "aiask_online", "live_backend"].includes(normalized)) return "ok";
  if (
    [
      "partial",
      "live_pending",
      "live_unverified",
      "unconfigured",
      "skipped_missing_credentials",
      "in_progress",
      "queued",
      "aiask_degraded",
      "fixture_degraded",
      "mock_fixture",
      "reviewing"
    ].includes(normalized)
  ) return "warn";
  if (["gated", "disabled", "not_loaded", "not_required", "idle", "unknown"].includes(normalized)) return "neutral";
  if (["failed", "missing", "blocked", "error", "aiask_offline", "aiask_forbidden", "aiask_unauthorized"].includes(normalized)) return "bad";
  return "neutral";
}

export function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json-panel">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

export function StatusBadge({ status, label }: { status?: string; label?: string }) {
  const tone = statusTone(status || label);
  const Icon = tone === "ok" ? CheckCircle2 : tone === "bad" ? XCircle : tone === "warn" ? AlertTriangle : Activity;
  const text = label || status || "unknown";
  return (
    <span className={`status-badge ${tone}`} title={text}>
      <Icon size={13} />
      {text}
    </span>
  );
}

export function IconButton({
  children,
  label,
  active,
  ...props
}: {
  children: ReactNode;
  label: string;
  active?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button aria-label={label} className={`icon-action ${active ? "active" : ""}`} title={label} type="button" {...props}>
      {children}
      <span>{label}</span>
    </button>
  );
}

export function MetricCard({ label, value, status }: { label: string; value: string | number; status?: string }) {
  return (
    <div className={`metric-card ${statusTone(status)}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function CapabilityRow({ item }: { item: CapabilityMatrixItem }) {
  const label = item.reference || item.feature || "feature";
  return (
    <div className={`capability-row ${statusTone(item.status)}`} title={item.description || item.live_status || item.code_status || ""}>
      <div>
        <span>{item.area}</span>
        <strong>{label}</strong>
      </div>
      <StatusBadge status={item.status} />
      <small>{(item.aiask_tools || []).join(", ") || "excluded"}</small>
    </div>
  );
}
