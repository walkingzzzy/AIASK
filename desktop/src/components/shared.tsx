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

export function localizeBlockedReason(reason?: unknown): string {
  const value = typeof reason === "string" ? reason.trim() : "";
  if (!value) return "";
  const normalized = value.toLowerCase();
  if (normalized.includes("control token") && (normalized.includes("not configured") || normalized.includes("missing") || normalized.includes("required"))) {
    return "缺少控制令牌 Control token。请在启动 Agent 时设置 AIASK_AGENT_CONTROL_TOKEN 或 AIASK_LOCAL_CONTROL_TOKEN，并在设置中填写同一个值。";
  }
  if (normalized.includes("control token") && (normalized.includes("invalid") || normalized.includes("unauthorized") || normalized.includes("forbidden"))) {
    return "控制令牌 Control token 未通过验证。请确认设置中的令牌与 Agent 启动环境一致。";
  }
  if (normalized.includes("full mode") || normalized.includes("hermes full") || normalized.includes("general_full")) {
    return "Agent 未开启 full mode。请使用 AIASK_AGENT_ENABLE_HERMES_FULL=1、AIASK_AGENT_TOOLSET=general_full 和 AIASK_AGENT_ENABLE_GENERAL_TOOLS=1 启动。";
  }
  if (normalized.includes("offline") || normalized.includes("not reachable") || normalized.includes("failed to fetch")) {
    return "当前 Agent 端点不可达。请确认本地 Agent 已启动，并优先使用默认端点 http://127.0.0.1:8767。";
  }
  if (normalized.includes("authorization required")) {
    return "MCP 授权缺失。请在 Agent 进程中配置对应授权环境变量。";
  }
  return value;
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
  const label = item.reference || item.feature || "功能";
  return (
    <div className={`capability-row ${statusTone(item.status)}`} title={item.description || item.live_status || item.code_status || ""}>
      <div>
        <span>{item.area}</span>
        <strong>{label}</strong>
      </div>
      <StatusBadge status={item.status} />
      <small>{(item.aiask_tools || []).join(", ") || "未纳入"}</small>
    </div>
  );
}
