import {
  AlertTriangle,
  ChevronDown,
  Database,
  FlaskConical,
  RefreshCw,
  Search,
  ShieldCheck
} from "lucide-react";
import type { CapabilityParity, FullModeConsoleData, HealthDetailed, HermesStatus } from "../types";
import { CapabilityRow, JsonPanel, MetricCard, StatusBadge } from "./shared";

function DiagnosticsSummary({ parity }: { parity?: CapabilityParity }) {
  return (
    <div className="diagnostics-summary">
      <MetricCard label="Coverage" value={parity ? `${Math.round(parity.coverage_ratio * 100)}%` : "-"} status={parity?.status} />
      <MetricCard label="Complete" value={parity ? `${Math.round(parity.complete_ratio * 100)}%` : "-"} status={parity?.mock_status || parity?.status} />
      <MetricCard label="Features" value={parity ? `${parity.implemented_features_count ?? 0}/${parity.feature_count ?? 0}` : "-"} status={parity?.status} />
      <MetricCard label="Live" value={parity?.live_status || "-"} status={parity?.live_status} />
    </div>
  );
}

export function DiagnosticsPanel({
  parity,
  hermesStatus,
  fullConsole,
  health,
  message,
  controlToken,
  busy,
  onRefresh
}: {
  parity?: CapabilityParity;
  hermesStatus: HermesStatus | null;
  fullConsole: FullModeConsoleData;
  health: HealthDetailed | null;
  message: string;
  controlToken: string;
  busy: boolean;
  onRefresh: () => void;
}) {
  const featureItems = parity?.feature_mapping || [];
  const missingItems = parity?.missing_features || [];
  const matrixItems = parity?.matrix || [];
  const subsystemRows = [
    ["Gateway", fullConsole.gatewayPlatforms?.length ?? "-", fullConsole.gatewayStatus],
    ["Terminal", fullConsole.terminalBackends?.length ?? "-", fullConsole.terminalBackends],
    ["Learning", fullConsole.learningReview?.length ?? "-", fullConsole.learningStatus],
    ["RL", fullConsole.rlRuns?.length ?? "-", fullConsole.rlReadiness || fullConsole.rlEnvironments],
    ["Plugins", fullConsole.plugins?.length ?? "-", fullConsole.pluginHooks],
    ["MCP", fullConsole.mcpTools?.length ?? "-", fullConsole.mcpTools]
  ] as const;

  return (
    <div className="inspector-scroll">
      <div className="panel-heading">
        <div>
          <span>Diagnostics</span>
          <h2>Hermes native parity</h2>
        </div>
        <button className="small-button" disabled={busy} onClick={onRefresh} type="button">
          <RefreshCw size={14} className={busy ? "spin" : ""} />
          Refresh
        </button>
      </div>

      <DiagnosticsSummary parity={parity} />

      <section className="subsystem-list">
        <h3>System health center</h3>
        <div className="health-signal-grid">
          <div>
            <Database size={15} />
            <span>Agent</span>
            <StatusBadge status={health?.status || "not_loaded"} />
          </div>
          <div>
            <Search size={15} />
            <span>Semantic search</span>
            <StatusBadge status={fullConsole.memory || fullConsole.providers ? "implemented" : "not_loaded"} label={fullConsole.memory ? "visible" : "unknown"} />
          </div>
          <div>
            <FlaskConical size={15} />
            <span>Incubation</span>
            <StatusBadge status={fullConsole.readiness ? "implemented" : "not_loaded"} label={fullConsole.readiness ? "tracked" : "unknown"} />
          </div>
          <div>
            <ShieldCheck size={15} />
            <span>Control</span>
            <StatusBadge status={controlToken.trim() ? "implemented" : "gated"} label={controlToken.trim() ? "authorized" : "token required"} />
          </div>
        </div>
      </section>

      {!controlToken.trim() && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          Control token unlocks gateway, terminal, learning, RL, plugin, and MCP management details.
        </div>
      )}

      <div className="kv-grid">
        <span>Implementation</span>
        <strong>{hermesStatus?.implementation || "-"}</strong>
        <span>Baseline</span>
        <strong>{hermesStatus?.baseline || "-"}</strong>
        <span>Vendor runtime</span>
        <strong>{String(hermesStatus?.embedded_vendor_runtime ?? false)}</strong>
        <span>Toolset</span>
        <strong>{hermesStatus?.evaluated_toolset || "-"}</strong>
      </div>

      <section className="subsystem-list">
        <h3>Subsystems</h3>
        {subsystemRows.map(([label, count, raw]) => (
          <details className="subsystem-row" key={label}>
            <summary>
              <span>{label}</span>
              <strong>{count}</strong>
            </summary>
            <JsonPanel value={raw || { status: "not_loaded" }} />
          </details>
        ))}
      </section>

      <section className="capability-list">
        <h3>Feature readiness</h3>
        {missingItems.length > 0 && (
          <div className="notice bad">
            <AlertTriangle size={15} />
            {missingItems.length} feature gaps need attention.
          </div>
        )}
        {(featureItems.length ? featureItems : matrixItems).slice(0, 20).map((item) => (
          <CapabilityRow item={item} key={item.feature || item.reference} />
        ))}
        {!featureItems.length && !matrixItems.length && <p className="muted">Refresh diagnostics to load parity data.</p>}
      </section>

      <details className="raw-details">
        <summary>
          Raw diagnostics
          <ChevronDown size={14} />
        </summary>
        <p className="status-line">{message || "ready"}</p>
        <JsonPanel value={fullConsole} />
      </details>
    </div>
  );
}
