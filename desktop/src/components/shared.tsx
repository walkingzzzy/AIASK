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
    return "缺少控制令牌。请在启动 Agent 时设置 AIASK_AGENT_CONTROL_TOKEN 或 AIASK_LOCAL_CONTROL_TOKEN，并在设置中填写同一个值。";
  }
  if (normalized.includes("control token") && (normalized.includes("invalid") || normalized.includes("unauthorized") || normalized.includes("forbidden"))) {
    return "控制令牌未通过验证。请确认设置中的令牌与 Agent 启动环境一致。";
  }
  if (normalized.includes("full mode") || normalized.includes("hermes full") || normalized.includes("general_full")) {
    return "Agent 未开启完整模式。请使用 AIASK_AGENT_ENABLE_HERMES_FULL=1、AIASK_AGENT_TOOLSET=general_full 和 AIASK_AGENT_ENABLE_GENERAL_TOOLS=1 启动。";
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
  const maybeMock = window.confirm as unknown as { _isMockFunction?: boolean; mock?: unknown };
  const mockedConfirm = Boolean(maybeMock._isMockFunction || maybeMock.mock);
  if (window.navigator?.userAgent?.toLowerCase().includes("jsdom") && !mockedConfirm) return true;
  try {
    return window.confirm(message) !== false;
  } catch {
    return true;
  }
}

export type StatusTone = "ok" | "warn" | "bad" | "neutral";

const STATUS_LABELS: Record<string, string> = {
  active: "已激活",
  agent_status_loaded: "智能体状态已加载",
  aiask_degraded: "服务降级",
  aiask_disconnected: "未连接",
  aiask_forbidden: "无权限",
  aiask_offline: "离线",
  aiask_online: "在线",
  aiask_unauthorized: "未授权",
  approval_required: "需要审批",
  approvals_loaded: "审批已加载",
  available: "可用",
  blocked: "已阻塞",
  bootstrap_confirmed: "引导已确认",
  bootstrap_not_run: "引导未运行",
  bootstrap_pending: "引导运行中",
  capabilities_synced: "能力已同步",
  completed: "已完成",
  configured: "已配置",
  connector_detail_loaded: "连接器详情已加载",
  connector_tested: "连接器测试完成",
  connectors_loaded: "连接器已加载",
  connectors_not_loaded: "连接器尚未加载",
  data_status_loaded: "数据状态已加载",
  degraded: "降级",
  delivered: "已送达",
  discovered: "已发现",
  disabled: "已停用",
  dry_run_ready: "试运行就绪",
  enabled: "已启用",
  error: "错误",
  events_degraded: "事件加载降级",
  events_loaded: "事件已加载",
  factor_factory_loaded: "因子工厂已加载",
  factor_maintenance_intent_created: "因子维护意图已创建",
  factor_run_intent_created: "因子运行意图已创建",
  factory_relay_loaded: "工厂接力状态已加载",
  failed: "失败",
  fixture_degraded: "Mock 降级",
  fresh: "新鲜",
  gated: "受限",
  healthy: "健康",
  idle: "空闲",
  implemented: "已实现",
  incubation_degraded: "孵化状态降级",
  incubation_dry_run_intent_created: "孵化试运行意图已创建",
  incubation_loaded: "孵化状态已加载",
  incubation_maintenance_intent_created: "孵化维护意图已创建",
  incubation_run_once_intent_created: "孵化运行意图已创建",
  info: "信息",
  in_progress: "进行中",
  intent_ready: "意图就绪",
  jobs_loaded: "任务已加载",
  lineages_loaded: "血缘已加载",
  lineage_not_loaded: "血缘未加载",
  live: "Live",
  live_backend: "Live",
  live_pending: "Live 待验证",
  live_unverified: "Live 未验证",
  local_profile_loaded: "本地画像已加载",
  local_profile_saved: "本地画像已保存",
  maintenance_not_loaded: "维护状态未加载",
  maintenance_status_degraded: "维护状态降级",
  maintenance_status_loaded: "维护状态已加载",
  mcp_smoke_done: "只读 smoke 测试已完成",
  mcp_smoke_not_run: "只读 smoke 测试未运行",
  mcp_smoke_running: "只读 smoke 测试运行中",
  missing: "缺失",
  missing_credentials: "缺少凭据",
  missing_dependency: "缺少依赖",
  missing_mcp_tool: "缺少 MCP 工具",
  mock: "Mock",
  mock_fixture: "Mock 数据",
  model_status_loaded: "模型状态已加载",
  not_loaded: "未加载",
  not_ready: "未就绪",
  not_required: "无需处理",
  off: "关闭",
  ok: "正常",
  online: "在线",
  open: "待处理",
  overview_loaded: "总览已加载",
  partial: "部分就绪",
  passed: "通过",
  pending: "待处理",
  pending_review: "待复核",
  queued: "排队中",
  radar_degraded: "雷达状态降级",
  radar_loaded: "雷达已加载",
  radar_not_loaded: "雷达未加载",
  read_only: "只读",
  ready: "就绪",
  recorded: "已记录",
  registered: "已注册",
  resolved: "已解决",
  reviewing: "复核中",
  run_events_loaded: "运行事件已加载",
  running: "运行中",
  skipped_missing_credentials: "缺少凭据",
  stale: "陈旧",
  strategy_factory_intent_created: "策略工厂意图已创建",
  success: "成功",
  sync_intent_created: "同步审批意图已创建",
  sync_plan_ready: "同步计划已生成",
  unavailable: "不可用",
  unavailable_fallback_to_weighted_pct_change: "基准不可用，已降级",
  unconfigured: "未配置",
  unknown: "未知",
  user_data_searched: "用户数据已搜索",
  warning: "警告"
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
      "active",
      "available",
      "completed",
      "configured",
      "delivered",
      "discovered",
      "enabled",
      "fresh",
      "healthy",
      "implemented",
      "intent_ready",
      "live",
      "live_backend",
      "mock",
      "ok",
      "online",
      "passed",
      "ready",
      "recorded",
      "registered",
      "resolved",
      "success",
      "aiask_online"
    ].includes(normalized)
  ) return "ok";
  if (
    [
      "approval_required",
      "aiask_degraded",
      "degraded",
      "dry_run_ready",
      "fixture_degraded",
      "in_progress",
      "live_pending",
      "live_unverified",
      "mock_fixture",
      "partial",
      "pending",
      "pending_review",
      "queued",
      "reviewing",
      "running",
      "skipped_missing_credentials",
      "stale",
      "unavailable_fallback_to_weighted_pct_change",
      "unconfigured",
      "warning"
    ].includes(normalized)
  ) return "warn";
  if (["disabled", "gated", "idle", "info", "not_loaded", "not_required", "read_only", "unknown"].includes(normalized)) return "neutral";
  if (
    [
      "aiask_forbidden",
      "aiask_offline",
      "aiask_unauthorized",
      "blocked",
      "error",
      "failed",
      "missing",
      "missing_credentials",
      "missing_dependency",
      "missing_mcp_tool",
      "not_ready",
      "unavailable"
    ].includes(normalized)
  ) return "bad";
  return "neutral";
}

const REDACTED_JSON_VALUE = "[redacted]";
const SENSITIVE_KEY_PATTERN = /(^|[\s_-])(api[\s_-]?key|authorization|bearer|client[\s_-]?secret|password|private[\s_-]?key|secret|token)([\s_-]|$)/i;
const SENSITIVE_VALUE_PATTERN =
  /(bearer\s+[A-Za-z0-9._~+/=-]{16,}|sk-[A-Za-z0-9_-]{20,}|(?:api[_-]?key|password|secret|token|authorization)\s*[:=]\s*["']?[^,\s}\n]+)/i;

export function redactJsonValue(value: unknown, key = ""): unknown {
  const sensitiveKey = SENSITIVE_KEY_PATTERN.test(key);
  if (typeof value === "string") {
    if ((sensitiveKey && value.trim()) || SENSITIVE_VALUE_PATTERN.test(value)) return REDACTED_JSON_VALUE;
    return value;
  }
  if (value === null || value === undefined || typeof value !== "object") return value;
  if (sensitiveKey) return REDACTED_JSON_VALUE;
  if (Array.isArray(value)) return value.map((item) => redactJsonValue(item));
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([entryKey, entryValue]) => [
      entryKey,
      redactJsonValue(entryValue, entryKey)
    ])
  );
}

export function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json-panel">{JSON.stringify(redactJsonValue(value ?? {}), null, 2)}</pre>;
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
  const text = statusLabel(label || raw);
  const titleText = title || [technicalLabel || raw, text !== raw ? text : ""].filter(Boolean).join(" / ");
  return (
    <span className={`status-badge ${tone}`} title={titleText}>
      <Icon size={13} />
      <span className="status-badge-text">{text}</span>
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
  const displayValue = typeof value === "string" ? statusLabel(value) : value;
  return (
    <div className={`metric-card ${statusTone(status)}`}>
      <span>{label}</span>
      <strong>{displayValue}</strong>
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
