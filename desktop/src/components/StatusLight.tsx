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
    label: "Connected"
  },
  disconnected: {
    icon: XCircle,
    color: "#ef4444",
    label: "Disconnected"
  },
  testing: {
    icon: Loader2,
    color: "#eab308",
    label: "Testing"
  },
  degraded: {
    icon: AlertCircle,
    color: "#f97316",
    label: "Degraded"
  },
  unknown: {
    icon: Circle,
    color: "#9ca3af",
    label: "Unknown"
  }
} as const;

export function StatusLight({ status, label, showLabel = true, size = 20 }: StatusLightProps) {
  const config = statusConfig[status];
  const Icon = config.icon;
  const displayLabel = label || config.label;

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
