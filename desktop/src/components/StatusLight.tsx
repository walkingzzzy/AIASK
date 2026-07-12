import { AlertCircle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

type StatusLightStatus = "connected" | "disconnected" | "testing" | "degraded" | "unknown";

interface StatusLightProps {
  status: StatusLightStatus;
  label?: string;
  showLabel?: boolean;
  size?: number;
}

const statusConfig = {
  connected: {
    icon: CheckCircle2,
    color: "#22c55e",
    label: "已连接"
  },
  disconnected: {
    icon: XCircle,
    color: "#ef4444",
    label: "未连接"
  },
  testing: {
    icon: Loader2,
    color: "#eab308",
    label: "检查中"
  },
  degraded: {
    icon: AlertCircle,
    color: "#f97316",
    label: "降级"
  },
  unknown: {
    icon: Circle,
    color: "#9ca3af",
    label: "未知"
  }
} as const;

function displayStatusLabel(label: string) {
  const normalized = label.trim().toLowerCase();
  const labels: Record<string, string> = {
    connected: "已连接",
    ready: "就绪",
    success: "成功",
    ok: "正常",
    enabled: "已启用",
    active: "启用中",
    configured: "已配置",
    available: "可用",
    running: "运行中",
    healthy: "健康",
    passed: "通过",
    testing: "检查中",
    pending: "待处理",
    loading: "加载中",
    starting: "启动中",
    queued: "排队中",
    degraded: "降级",
    partial: "部分可用",
    warning: "警告",
    stale: "已过期",
    limited: "受限",
    approval: "需审批",
    requires: "需要处理",
    gated: "受控",
    disconnected: "未连接",
    failed: "失败",
    error: "错误",
    disabled: "已停用",
    inactive: "未启用",
    missing: "缺失",
    stopped: "已停止",
    denied: "已拒绝",
    blocked: "已阻止",
    unhealthy: "不健康",
    enforced: "已强制执行"
  };
  return labels[normalized] || label;
}

export function StatusLight({ status, label, showLabel = true, size = 20 }: StatusLightProps) {
  const config = statusConfig[status];
  const Icon = config.icon;
  const displayLabel = displayStatusLabel(label || config.label);

  return (
    <div className="status-light" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
      <Icon
        size={size}
        color={config.color}
        style={{
          animation: status === "testing" ? "spin 1s linear infinite" : undefined
        }}
      />
      {showLabel ? <span style={{ fontSize: "0.875rem", color: "#6b7280" }}>{displayLabel}</span> : null}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

function normalizeStatus(value: unknown): StatusLightStatus {
  if (typeof value === "boolean") {
    return value ? "connected" : "disconnected";
  }

  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "unknown";

  if (
    [
      "connected",
      "ready",
      "success",
      "ok",
      "enabled",
      "active",
      "configured",
      "available",
      "running",
      "healthy",
      "passed"
    ].some((token) => normalized.includes(token))
  ) {
    return "connected";
  }

  if (["testing", "pending", "loading", "starting", "queued"].some((token) => normalized.includes(token))) {
    return "testing";
  }

  if (["degraded", "partial", "warning", "stale", "limited", "approval", "requires", "gated"].some((token) => normalized.includes(token))) {
    return "degraded";
  }

  if (
    [
      "disconnected",
      "failed",
      "error",
      "disabled",
      "inactive",
      "missing",
      "stopped",
      "denied",
      "blocked",
      "unhealthy"
    ].some((token) => normalized.includes(token))
  ) {
    return "disconnected";
  }

  return "unknown";
}

export function inferStatusFromData(data: unknown): StatusLightStatus {
  if (!data || typeof data !== "object") {
    return normalizeStatus(data);
  }

  const obj = data as Record<string, unknown>;
  const error = obj.error || obj.error_code || obj.errors;

  if (error) {
    return "disconnected";
  }

  if (obj.warnings) {
    return "degraded";
  }

  const candidates = [
    obj.status,
    obj.state,
    obj.health,
    obj.mode,
    obj.side_effect,
    obj.enabled,
    obj.configured,
    obj.connected,
    obj.running,
    obj.api_key_configured
  ];

  for (const candidate of candidates) {
    const normalized = normalizeStatus(candidate);
    if (normalized !== "unknown") {
      return normalized;
    }
  }

  return "unknown";
}
