import {
  AlertTriangle,
  ChevronDown,
  Database,
  FlaskConical,
  RefreshCw,
  Search,
  ShieldCheck
} from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type { CapabilityParity, FullModeConsoleData, HealthDetailed, HermesStatus } from "../types";
import { CapabilityRow, JsonPanel, MetricCard, StatusBadge } from "./shared";

type TerminalSessionState = {
  backend?: string;
  message: string;
  payload?: unknown;
  status: "idle" | "loading" | "success" | "error";
};

type TerminalBackendsState = {
  items: unknown[];
  message: string;
  status: "idle" | "loading" | "success" | "error";
};

function terminalBackendName(backends?: unknown[]): string {
  const first = backends?.find((item) => item && typeof item === "object") as Record<string, unknown> | undefined;
  const name = first?.name || first?.backend || first?.id;
  return typeof name === "string" ? name : "";
}

function DiagnosticsSummary({ parity }: { parity?: CapabilityParity }) {
  return (
    <div className="diagnostics-summary">
      <MetricCard label="覆盖率" value={parity ? `${Math.round(parity.coverage_ratio * 100)}%` : "-"} status={parity?.status} />
      <MetricCard label="完成率" value={parity ? `${Math.round(parity.complete_ratio * 100)}%` : "-"} status={parity?.mock_status || parity?.status} />
      <MetricCard label="功能" value={parity ? `${parity.implemented_features_count ?? 0}/${parity.feature_count ?? 0}` : "-"} status={parity?.status} />
      <MetricCard label="真实环境" value={parity?.live_status || "-"} status={parity?.live_status} />
    </div>
  );
}

export function DiagnosticsPanel({
  apiToken,
  endpoint,
  parity,
  hermesStatus,
  fullConsole,
  health,
  message,
  controlToken,
  busy,
  onRefresh
}: {
  apiToken: string;
  endpoint: string;
  parity?: CapabilityParity;
  hermesStatus: HermesStatus | null;
  fullConsole: FullModeConsoleData;
  health: HealthDetailed | null;
  message: string;
  controlToken: string;
  busy: boolean;
  onRefresh: () => void;
}) {
  const [terminalSessions, setTerminalSessions] = useState<TerminalSessionState>({ message: "", status: "idle" });
  const [terminalBackends, setTerminalBackends] = useState<TerminalBackendsState>({ items: [], message: "", status: "idle" });
  const featureItems = parity?.feature_mapping || [];
  const missingItems = parity?.missing_features || [];
  const matrixItems = parity?.matrix || [];
  const displayedTerminalBackends = useMemo(
    () => (fullConsole.terminalBackends?.length ? fullConsole.terminalBackends : terminalBackends.items),
    [fullConsole.terminalBackends, terminalBackends.items]
  );
  const selectedTerminalBackend = terminalBackendName(displayedTerminalBackends);
  const subsystemRows = [
    { label: "Gateway", count: fullConsole.gatewayPlatforms?.length ?? "-", raw: fullConsole.gatewayStatus },
    { label: "终端", count: displayedTerminalBackends.length || "-", raw: displayedTerminalBackends },
    { label: "学习", count: fullConsole.learningReview?.length ?? "-", raw: fullConsole.learningStatus },
    { label: "RL", count: fullConsole.rlRuns?.length ?? "-", raw: fullConsole.rlReadiness || fullConsole.rlEnvironments },
    { label: "插件", count: fullConsole.plugins?.length ?? "-", raw: fullConsole.pluginHooks },
    { label: "MCP", count: fullConsole.mcpTools?.length ?? "-", raw: fullConsole.mcpTools }
  ] as const;

  async function loadTerminalBackends(force = false) {
    if (!controlToken.trim() || (!force && displayedTerminalBackends.length) || terminalBackends.status === "loading") {
      return;
    }
    setTerminalBackends({ items: [], message: "TERMINAL_BACKENDS_LOADING", status: "loading" });
    try {
      const api = new AiaskApi({ endpoint, apiToken, controlToken });
      const payload = await api.terminalBackends();
      setTerminalBackends({
        items: payload.data || [],
        message: "TERMINAL_BACKENDS_LOADED",
        status: "success"
      });
    } catch (error) {
      setTerminalBackends({ items: [], message: formatApiError(error), status: "error" });
    }
  }

  function refreshDiagnostics() {
    setTerminalBackends({ items: [], message: "", status: "idle" });
    setTerminalSessions({ message: "", status: "idle" });
    onRefresh();
    void loadTerminalBackends(true);
  }

  async function loadTerminalSessions() {
    if (!controlToken.trim()) {
      setTerminalSessions({ message: "CONTROL_TOKEN_REQUIRED", status: "error" });
      return;
    }
    if (!selectedTerminalBackend) {
      setTerminalSessions({ message: "TERMINAL_BACKEND_NOT_LOADED", status: "error" });
      return;
    }
    setTerminalSessions({ backend: selectedTerminalBackend, message: "TERMINAL_BACKEND_SESSIONS_LOADING", status: "loading" });
    try {
      const api = new AiaskApi({ endpoint, apiToken, controlToken });
      const payload = await api.terminalBackendSessions(selectedTerminalBackend, 50);
      setTerminalSessions({
        backend: selectedTerminalBackend,
        message: "TERMINAL_BACKEND_SESSIONS_LOADED",
        payload,
        status: "success"
      });
    } catch (error) {
      setTerminalSessions({
        backend: selectedTerminalBackend,
        message: formatApiError(error),
        status: "error"
      });
    }
  }

  return (
    <div className="inspector-scroll">
      <div className="panel-heading">
        <div>
          <span>诊断</span>
          <h2>Hermes 原生对齐</h2>
        </div>
        <button className="small-button" disabled={busy} onClick={refreshDiagnostics} type="button">
          <RefreshCw size={14} className={busy ? "spin" : ""} />
          刷新
        </button>
      </div>

      <DiagnosticsSummary parity={parity} />

      <section className="subsystem-list">
        <h3>系统健康中心</h3>
        <div className="health-signal-grid">
          <div>
            <Database size={15} />
            <span>智能体</span>
            <StatusBadge status={health?.status || "not_loaded"} />
          </div>
          <div>
            <Search size={15} />
            <span>语义搜索</span>
            <StatusBadge status={fullConsole.memory || fullConsole.providers ? "implemented" : "not_loaded"} label={fullConsole.memory ? "可见" : "未知"} />
          </div>
          <div>
            <FlaskConical size={15} />
            <span>孵化</span>
            <StatusBadge status={fullConsole.readiness ? "implemented" : "not_loaded"} label={fullConsole.readiness ? "已跟踪" : "未知"} />
          </div>
          <div>
            <ShieldCheck size={15} />
            <span>控制</span>
            <StatusBadge status={controlToken.trim() ? "implemented" : "gated"} label={controlToken.trim() ? "已授权" : "需要令牌"} />
          </div>
        </div>
      </section>

      {!controlToken.trim() && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          控制令牌会解锁网关、终端、学习、RL、插件和 MCP 管理详情。
        </div>
      )}

      <div className="kv-grid">
        <span>实现</span>
        <strong>{hermesStatus?.implementation || "-"}</strong>
        <span>基线</span>
        <strong>{hermesStatus?.baseline || "-"}</strong>
        <span>外部运行时</span>
        <strong>{String(hermesStatus?.embedded_vendor_runtime ?? false)}</strong>
        <span>工具集</span>
        <strong>{hermesStatus?.evaluated_toolset || "-"}</strong>
      </div>

      <section className="subsystem-list">
        <h3>子系统</h3>
        {subsystemRows.map(({ label, count, raw }) => (
          <details className="subsystem-row" key={label}>
            <summary onClick={label === "终端" ? () => void loadTerminalBackends() : undefined}>
              <span>{label}</span>
              <strong>{count}</strong>
            </summary>
            <JsonPanel value={raw || { status: "not_loaded" }} />
            {label === "终端" && (
              <div className="subsystem-actions">
                <button
                  className="small-button"
                  disabled={terminalSessions.status === "loading" || !controlToken.trim() || !selectedTerminalBackend}
                  onClick={loadTerminalSessions}
                  type="button"
                >
                  <RefreshCw size={13} className={terminalSessions.status === "loading" ? "spin" : ""} />
                  加载终端会话
                </button>
                <StatusBadge
                  status={
                    terminalSessions.status === "success"
                      ? "ready"
                      : terminalSessions.status === "error"
                        ? "gated"
                        : terminalSessions.status === "loading"
                          ? "running"
                          : selectedTerminalBackend
                            ? "read_only"
                            : "not_loaded"
                  }
                  label={terminalSessions.message || selectedTerminalBackend || "未加载后端"}
                />
                {terminalBackends.message ? <p className="status-line">{terminalBackends.message}</p> : null}
                {terminalSessions.payload ? <JsonPanel value={terminalSessions.payload} /> : null}
              </div>
            )}
          </details>
        ))}
      </section>

      <section className="capability-list">
        <h3>功能就绪状态</h3>
        {missingItems.length > 0 && (
          <div className="notice bad">
            <AlertTriangle size={15} />
            {missingItems.length} 个功能缺口需要处理。
          </div>
        )}
        {(featureItems.length ? featureItems : matrixItems).slice(0, 20).map((item) => (
          <CapabilityRow item={item} key={item.feature || item.reference} />
        ))}
        {!featureItems.length && !matrixItems.length && <p className="muted">请刷新诊断以加载对齐数据。</p>}
      </section>

      <details className="raw-details">
        <summary>
          原始诊断数据
          <ChevronDown size={14} />
        </summary>
        <p className="status-line">{message || "ready"}</p>
        <JsonPanel value={fullConsole} />
      </details>
    </div>
  );
}
