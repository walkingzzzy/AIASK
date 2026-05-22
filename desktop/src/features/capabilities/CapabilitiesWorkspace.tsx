import { Activity, Bot, Boxes, BrainCircuit, Cable, Factory, FlaskConical, Layers3, Puzzle, RefreshCw, ServerCog, ShieldCheck } from "lucide-react";
import type { ElementType } from "react";
import { useEffect, useMemo, useState } from "react";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import type { CapabilityTab, CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { AiTestingPanel } from "../ai-testing/AiTestingPanel";
import { ConnectorsPanel } from "../connectors/ConnectorsPanel";
import { IncubationFactoryPanel } from "../incubation/IncubationFactoryPanel";
import { StrategyFactoryPanel } from "../factory/StrategyFactoryPanel";
import { McpPanel } from "../mcp/McpPanel";
import { SkillsPanel } from "../skills/SkillsPanel";
import { CoverageMatrixPanel } from "./CoverageMatrixPanel";
import { HermesPanel } from "./HermesPanel";
import { PluginsPanel } from "./PluginsPanel";
import { capabilityIssues, collectCapabilityRows, itemLabel } from "./capabilityUtils";

const tabs: Array<{ id: CapabilityTab; label: string; icon: ElementType }> = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "coverage", label: "Coverage Matrix", icon: ShieldCheck },
  { id: "connectors", label: "Connectors", icon: Cable },
  { id: "hermes", label: "Hermes", icon: Boxes },
  { id: "mcp", label: "MCP", icon: ServerCog },
  { id: "factory", label: "Strategy Factory", icon: Factory },
  { id: "incubation", label: "Incubation", icon: FlaskConical },
  { id: "skills", label: "Skills", icon: Layers3 },
  { id: "plugins", label: "Plugins", icon: Puzzle },
  { id: "ai", label: "AI Tests", icon: BrainCircuit }
];

function sourceMeta(source?: string | null): { status: string; label: string } {
  if (source === "mock_fixture") return { status: "fixture_degraded", label: "Mock fixture" };
  if (source === "gated") return { status: "gated", label: "Gated live backend" };
  if (source === "offline") return { status: "offline", label: "Offline" };
  return { status: "live_backend", label: "Live backend" };
}

function summaryStatusMeta(status?: string | null): { status: string; label: string } {
  if (status === "in_progress") return { status: "live_pending", label: "code parity complete, live pending" };
  if (!status) return { status: "not_loaded", label: "not loaded" };
  return { status, label: status };
}

function Overview({ payload, message }: { payload: CapabilityWorkbenchPayload | null; message: string }) {
  const counts = payload?.summary.counts || {};
  const rows = useMemo(() => collectCapabilityRows(payload), [payload]);
  const issues = capabilityIssues(payload);
  const control = payload?.summary.control;
  const financialSystem = payload?.financial_system;
  const source = payload?.summary.source || (payload ? "live_backend" : "offline");
  const sourceBadge = sourceMeta(source);
  const summaryBadge = summaryStatusMeta(payload?.summary.status);
  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Capabilities</span>
          <h2>Runtime review board</h2>
          <p>Review backend parity, MCP discovery, factories, skills, plugins, and AI checks from the active Agent endpoint.</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={sourceBadge.status} label={sourceBadge.label} />
          <StatusBadge status={summaryBadge.status} label={summaryBadge.label} />
        </div>
      </div>

      <div className="diagnostics-summary wide">
        <MetricCard label="Implemented" value={counts.implemented || 0} status="implemented" />
        <MetricCard label="Live unverified" value={counts.live_unverified || 0} status="live_unverified" />
        <MetricCard label="Unconfigured" value={counts.unconfigured || 0} status="unconfigured" />
        <MetricCard label="Failed/Missing" value={(counts.failed || 0) + (counts.missing || 0)} status={(counts.failed || 0) + (counts.missing || 0) ? "failed" : "implemented"} />
      </div>

      {financialSystem && (
        <div className="capability-section compact-section">
          <div className="section-header">
            <div>
              <span>Financial system gate</span>
              <h3>Production readiness</h3>
            </div>
            <StatusBadge status={financialSystem.status} label={financialSystem.production_ready ? "production ready" : financialSystem.status} />
          </div>
          <div className="mini-list">
            {financialSystem.required_gates.map((gate) => (
              <article key={gate.name}>
                <strong>{gate.name}</strong>
                <span>{gate.required ? "required" : "optional"}</span>
                <StatusBadge status={gate.status} />
                <p>{gate.detail}</p>
              </article>
            ))}
          </div>
          {financialSystem.disclaimer && <p className="muted">{financialSystem.disclaimer}</p>}
        </div>
      )}

      {payload && (
        <div className="capability-section compact-section">
          <div className="kv-grid">
            <span>Full mode</span>
            <strong>{control?.full_mode_enabled ? "enabled" : "disabled"}</strong>
            <span>Control token</span>
            <strong>{control?.control_token_configured ? "configured" : "not configured"}</strong>
            <span>Control authorized</span>
            <strong>{String(control?.control_authorized ?? control?.authorized ?? false)}</strong>
            <span>Gated reason</span>
            <strong>{control?.gated_reason || control?.reason || "-"}</strong>
          </div>
        </div>
      )}

      {!payload?.summary.control.authorized && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          {payload?.summary.control.gated_reason || payload?.summary.control.reason || "Control token is required for full MCP, skills, plugins, gateway, terminal, and RL data."}
        </div>
      )}

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{issues.length} issues</span>
              <h3>Actionable gaps</h3>
            </div>
          </div>
          <div className="mini-list">
            {issues.slice(0, 12).map((issue) => (
              <article key={`${itemLabel(issue)}:${issue.area || ""}`}>
                <strong>{itemLabel(issue)}</strong>
                <span>{issue.area || issue.status || "capability"}</span>
                <p>{Array.isArray(issue.missing_aiask_tools) ? issue.missing_aiask_tools.join(", ") : issue.error || "Needs configuration or implementation."}</p>
              </article>
            ))}
            {!issues.length && <p className="muted">No code-level gaps in the current capability ledger.</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{rows.length} checks</span>
              <h3>Recent readiness rows</h3>
            </div>
          </div>
          <div className="mini-list">
            {rows.slice(0, 10).map((item) => (
              <article key={`${itemLabel(item as Record<string, unknown>)}:${item.area || ""}`}>
                <strong>{itemLabel(item as Record<string, unknown>)}</strong>
                <span>{item.area || "-"}</span>
                <StatusBadge status={item.status} />
              </article>
            ))}
          </div>
        </div>
      </section>

      <details className="raw-details">
        <summary>Raw capability workbench</summary>
        <p className="status-line">{message || "ready"}</p>
        <JsonPanel value={payload || { status: "not_loaded" }} />
      </details>
    </div>
  );
}

export function CapabilitiesWorkspace({
  endpoint,
  apiToken,
  controlToken,
  initialTab = "overview"
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  initialTab?: CapabilityTab;
}) {
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);
  const [activeTab, setActiveTab] = useState<CapabilityTab>(initialTab);
  const sourceBadge = sourceMeta(payload?.summary.source || (payload ? "live_backend" : "offline"));
  const summaryBadge = summaryStatusMeta(payload?.summary.status || message || "not_loaded");

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Capability Workbench</span>
          <h1>Runtime review</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={sourceBadge.status} label={sourceBadge.label} />
          <StatusBadge status={summaryBadge.status} label={summaryBadge.label} />
          <button aria-label="Refresh capability review" className="small-button" disabled={busy} onClick={() => refresh()} title="Refresh capability review" type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              aria-label={tab.label}
              aria-pressed={activeTab === tab.id}
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              title={tab.label}
              type="button"
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="capabilities-body">
        {!payload && busy && (
          <div className="empty-thread">
            <Bot size={28} />
            <strong>Loading capabilities</strong>
            <span>Reading Hermes parity, MCP, strategy factory, skills, and AI diagnostics.</span>
          </div>
        )}
        {activeTab === "overview" && <Overview payload={payload} message={message} />}
        {activeTab === "coverage" && <CoverageMatrixPanel capabilities={payload} />}
        {activeTab === "connectors" && <ConnectorsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />}
        {activeTab === "hermes" && <HermesPanel payload={payload} />}
        {activeTab === "mcp" && <McpPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "factory" && <StrategyFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} payload={payload} />}
        {activeTab === "incubation" && <IncubationFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />}
        {activeTab === "skills" && <SkillsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "plugins" && <PluginsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "ai" && <AiTestingPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} payload={payload} />}
      </div>
    </section>
  );
}
