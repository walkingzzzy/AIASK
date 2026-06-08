import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Circle,
  FileJson,
  Info,
  LockKeyhole,
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
    return "缺少 Control token。请在启动 Agent 时设置 AIASK_AGENT_CONTROL_TOKEN 或 AIASK_LOCAL_CONTROL_TOKEN，并在 Settings 中填写同一个值。";
  }
  if (normalized.includes("control token") && (normalized.includes("invalid") || normalized.includes("unauthorized") || normalized.includes("forbidden"))) {
    return "Control token 未通过验证。请确认 Settings 中的令牌与 Agent 启动环境一致。";
  }
  if (normalized.includes("full mode") || normalized.includes("hermes full") || normalized.includes("general_full")) {
    return "Agent 未开启 full mode。请使用 AIASK_AGENT_ENABLE_HERMES_FULL=1、AIASK_AGENT_TOOLSET=general_full 和 AIASK_AGENT_ENABLE_GENERAL_TOOLS=1 启动。";
  }
  if (normalized.includes("offline") || normalized.includes("not reachable") || normalized.includes("failed to fetch")) {
    return "当前 Agent endpoint 不可达。请确认本地 Agent 已启动，并优先使用默认端点 http://127.0.0.1:8767。";
  }
  if (normalized.includes("authorization required")) {
    return "MCP 授权缺失。请在 Agent 进程中配置对应授权环境变量。";
  }
  return value;
}

export function confirmAction(actionLabel: string, detail?: string): boolean {
  const message = [actionLabel, detail, "此操作会改变当前任务、运行或集成状态，请确认后继续。"].filter(Boolean).join("\n\n");
  if (typeof window === "undefined" || typeof window.confirm !== "function") return true;
  const confirmSource = String(window.confirm);
  if (window.navigator?.userAgent?.toLowerCase().includes("jsdom") && confirmSource.includes("notImplemented")) return true;
  try {
    return window.confirm(message) !== false;
  } catch {
    return true;
  }
}

export type StatusTone = "ok" | "warn" | "bad" | "neutral";

const STATUS_LABELS: Record<string, string> = {
  aiask_degraded: "服务降级",
  aiask_forbidden: "无权限",
  aiask_offline: "离线",
  aiask_online: "在线",
  aiask_unauthorized: "未授权",
  approval_required: "需审批",
  blocked: "已阻塞",
  completed: "已完成",
  degraded: "降级",
  disabled: "已停用",
  error: "错误",
  failed: "失败",
  fixture_degraded: "Mock 降级",
  gated: "受限",
  idle: "空闲",
  implemented: "已实现",
  in_progress: "进行中",
  live: "Live",
  live_backend: "Live",
  live_pending: "Live 待验证",
  live_unverified: "Live 未验证",
  missing: "缺失",
  mock: "Mock",
  mock_fixture: "Mock 数据",
  not_loaded: "未加载",
  not_required: "无需处理",
  online: "在线",
  open: "待处理",
  partial: "部分就绪",
  passed: "通过",
  queued: "排队中",
  read_only: "只读",
  ready: "就绪",
  resolved: "已解决",
  reviewing: "复核中",
  running: "运行中",
  skipped_missing_credentials: "缺少凭据",
  success: "成功",
  unconfigured: "未配置",
  unknown: "未知"
};

export function statusLabel(status?: string, fallback?: string): string {
  const text = fallback || status || "unknown";
  const normalized = text.toLowerCase();
  return STATUS_LABELS[normalized] || text;
}

export function statusTone(status?: string): StatusTone {
  if (!status) return "neutral";
  const normalized = status.toLowerCase();
  if (
    [
      "implemented",
      "ready",
      "passed",
      "success",
      "completed",
      "online",
      "aiask_online",
      "live_backend",
      "live",
      "mock"
    ].includes(normalized)
  ) return "ok";
  if (
    [
      "partial",
      "live_pending",
      "live_unverified",
      "unconfigured",
      "skipped_missing_credentials",
      "in_progress",
      "queued",
      "running",
      "aiask_degraded",
      "fixture_degraded",
      "mock_fixture",
      "reviewing",
      "approval_required",
      "degraded"
    ].includes(normalized)
  ) return "warn";
  if (["gated", "disabled", "not_loaded", "not_required", "idle", "unknown", "read_only"].includes(normalized)) return "neutral";
  if (["failed", "missing", "blocked", "error", "aiask_offline", "aiask_forbidden", "aiask_unauthorized"].includes(normalized)) return "bad";
  return "neutral";
}

export function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json-panel">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

export function StatusBadge({
  status,
  label,
  technicalLabel,
  title,
  tone: toneOverride
}: {
  status?: string;
  label?: string;
  technicalLabel?: string;
  title?: string;
  tone?: StatusTone;
}) {
  const raw = status || label || "unknown";
  const tone = toneOverride || statusTone(raw);
  const Icon = tone === "ok" ? CheckCircle2 : tone === "bad" ? XCircle : tone === "warn" ? AlertTriangle : Activity;
  const text = label || statusLabel(raw);
  const titleText = title || [technicalLabel || raw, text !== raw ? text : ""].filter(Boolean).join(" / ");
  return (
    <span className={`status-badge ${tone}`} title={titleText}>
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

export function RawEvidencePanel({
  children,
  open = false,
  title = "Raw evidence",
  value
}: {
  children?: ReactNode;
  open?: boolean;
  title?: string;
  value?: unknown;
}) {
  return (
    <details className="raw-details raw-evidence-panel" open={open}>
      <summary>
        <span><FileJson size={14} /> {title}</span>
        <ChevronDown size={14} />
      </summary>
      {children || <JsonPanel value={value} />}
    </details>
  );
}

export function EmptyState({
  action,
  body,
  icon,
  title
}: {
  action?: ReactNode;
  body: string;
  icon?: ReactNode;
  title: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon || <Circle size={24} />}</div>
      <strong>{title}</strong>
      <span>{body}</span>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}

export function GatedState({
  action,
  reason,
  status = "gated",
  title = "需要完成配置"
}: {
  action?: ReactNode;
  reason: string;
  status?: string;
  title?: string;
}) {
  return (
    <div className="gated-state">
      <div className="gated-state-head">
        <LockKeyhole size={16} />
        <strong>{title}</strong>
        <StatusBadge status={status} />
      </div>
      <p>{localizeBlockedReason(reason) || reason}</p>
      {action && <div className="button-row">{action}</div>}
    </div>
  );
}

export function ConfirmActionButton({
  actionLabel,
  children,
  confirmDetail,
  isDanger = false,
  onConfirmed,
  ...props
}: {
  actionLabel: string;
  confirmDetail?: string;
  isDanger?: boolean;
  onConfirmed: () => void;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick">) {
  return (
    <button
      {...props}
      className={`${props.className || "small-button"} ${isDanger ? "danger" : ""}`.trim()}
      onClick={() => {
        if (props.disabled) return;
        if (!confirmAction(actionLabel, confirmDetail)) return;
        onConfirmed();
      }}
      type={props.type || "button"}
    >
      {children || (
        <>
          <Info size={14} />
          {actionLabel}
        </>
      )}
    </button>
  );
}

export function CapabilityRow({ item }: { item: CapabilityMatrixItem }) {
  const label = item.reference || item.feature || "Capability";
  return (
    <div className={`capability-row ${statusTone(item.status)}`} title={item.description || item.live_status || item.code_status || ""}>
      <div>
        <span>{item.area}</span>
        <strong>{label}</strong>
      </div>
      <StatusBadge status={item.status} />
      <small>{(item.aiask_tools || []).join(", ") || "Not mapped"}</small>
    </div>
  );
}
