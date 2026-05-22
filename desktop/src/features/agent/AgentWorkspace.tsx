import { Activity, Bot, Boxes, Database, Factory, RefreshCw, ShieldCheck, UserRound, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, DesktopSettingsStatus, HealthDetailed, ToolCatalogItem } from "../../types";

const FINANCE_TOOL_NAMES = [
  "agent_analyze_stock",
  "agent_quant_data_gate",
  "agent_factor_validation",
  "agent_backtest_suite",
  "agent_portfolio_risk",
  "agent_quant_research_run",
  "agent_factory_status",
  "agent_factory_runs",
  "agent_strategy_review_snapshot",
  "agent_strategy_domain_events",
  "agent_incubation_factory_status",
  "agent_memory_search",
  "agent_session_search"
];

const HERMES_GROUPS: Array<{ label: string; area: string; tools: string[] }> = [
  { label: "Files", area: "general_read", tools: ["agent_file_list", "agent_file_read"] },
  { label: "Terminal", area: "terminal_backend", tools: ["agent_terminal_backends"] },
  { label: "Browser", area: "browser", tools: ["agent_browser_snapshot", "agent_browser_console"] },
  { label: "Web", area: "web", tools: ["agent_web_search"] },
  { label: "Gateway", area: "platform_gateway", tools: ["agent_gateway_status", "agent_gateway_platforms"] },
  { label: "Learning/RL", area: "learning", tools: ["agent_learning_status", "agent_learning_review", "agent_rl_list_environments", "agent_rl_get_config"] },
  { label: "Extensions", area: "skills/plugins/mcp", tools: ["agent_skill_list", "agent_plugin_list", "agent_mcp_manage"] },
  { label: "Jobs and handoff", area: "cron_admin/memory_admin", tools: ["agent_job_list", "agent_job_create", "agent_session_handoff"] }
];

function toolNames(tools: ToolCatalogItem[]): Set<string> {
  return new Set(tools.map((tool) => tool.name));
}

function registeredToolNames(tools: ToolCatalogItem[], health: HealthDetailed | null): Set<string> {
  return new Set([...toolNames(tools), ...(health?.tools?.names || [])]);
}

function groupStatus(names: string[], registered: Set<string>, fullMode: boolean): string {
  const available = names.filter((name) => registered.has(name)).length;
  if (available === names.length) return "implemented";
  if (available > 0) return "partial";
  return fullMode ? "missing" : "gated";
}

export function AgentWorkspace({
  endpoint,
  apiToken,
  controlToken,
  health,
  onRefreshHealth
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  health: HealthDetailed | null;
  onRefreshHealth: () => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityWorkbenchPayload | null>(null);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, toolsPayload, capabilitiesPayload] = await Promise.all([
        api.settingsStatus(),
        api.tools(),
        api.capabilities()
      ]);
      setSettings(settingsPayload);
      setTools(toolsPayload.data || []);
      setCapabilities(capabilitiesPayload);
      onRefreshHealth();
      setMessage("AGENT_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const agent = settings?.agent || {};
  const registered = registeredToolNames(tools, health);
  const financeCount = FINANCE_TOOL_NAMES.filter((name) => registered.has(name)).length;
  const fullMode = Boolean(agent.toolset === "general_full" || health?.hermes?.full_mode_active || health?.hermes?.full_mode_enabled);
  const mcp = capabilities?.mcp;
  const strategy = capabilities?.strategy_factory;
  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Agent</span>
          <h1>Runtime status</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : health?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{endpoint}</span>
              <h2>{health?.service || "AIASK Agent"}</h2>
              <p>Loopback Agent HTTP API, tool registry, run storage, and control-token readiness.</p>
            </div>
            <Bot size={24} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="Status" value={health?.status || "offline"} status={health?.status || "not_loaded"} />
            <MetricCard label="Toolset" value={String(agent.toolset || health?.tools?.toolset || "-")} status="ready" />
            <MetricCard label="Tools" value={health?.tools?.count ?? 0} status={(health?.tools?.count || 0) > 0 ? "ready" : "not_loaded"} />
            <MetricCard label="Control" value={agent.control_authorized ? "authorized" : agent.control_token_configured ? "configured" : "missing"} status={agent.control_authorized ? "ready" : "gated"} />
          </div>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Finance safe</span>
                <h3>Financial Agent ability coverage</h3>
              </div>
              <ShieldCheck size={18} />
            </div>
            <div className="diagnostics-summary wide">
              <MetricCard label="Finance tools" value={`${financeCount}/${FINANCE_TOOL_NAMES.length}`} status={financeCount === FINANCE_TOOL_NAMES.length ? "implemented" : "partial"} />
              <MetricCard label="Data gate" value={registered.has("agent_quant_data_gate") ? "ready" : "missing"} status={registered.has("agent_quant_data_gate") ? "implemented" : "missing"} />
              <MetricCard label="Backtest/Risk" value={registered.has("agent_backtest_suite") && registered.has("agent_portfolio_risk") ? "ready" : "partial"} status={registered.has("agent_backtest_suite") && registered.has("agent_portfolio_risk") ? "implemented" : "partial"} />
              <MetricCard label="Memory/session" value={registered.has("agent_memory_search") && registered.has("agent_session_search") ? "ready" : "missing"} status={registered.has("agent_memory_search") && registered.has("agent_session_search") ? "implemented" : "missing"} />
            </div>
            <div className="mini-list">
              {FINANCE_TOOL_NAMES.map((name) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <span>{registered.has(name) ? "registered in current Agent tool catalog" : "not registered in current toolset"}</span>
                  <StatusBadge status={registered.has(name) ? "implemented" : "missing"} />
                </article>
              ))}
            </div>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Hermes full</span>
                  <h3>Full-mode ability groups</h3>
                </div>
                <Boxes size={18} />
              </div>
              <div className="mini-list">
                {HERMES_GROUPS.map((group) => (
                  <article key={group.label}>
                    <strong>{group.label}</strong>
                    <span>{group.area} / {group.tools.filter((name) => registered.has(name)).length} of {group.tools.length} tools registered</span>
                    <StatusBadge status={groupStatus(group.tools, registered, fullMode)} />
                  </article>
                ))}
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>MCP and factories</span>
                  <h3>Runtime operation surfaces</h3>
                </div>
                <Wrench size={18} />
              </div>
              <div className="kv-grid">
                <span>MCP servers</span>
                <strong>{String(mcp?.servers?.length ?? "-")}</strong>
                <span>MCP tools</span>
                <strong>{String(mcp?.tools?.length ?? "-")}</strong>
                <span>MCP status</span>
                <strong>{String(mcp?.gated ? "gated" : mcp?.discovery_status || "-")}</strong>
                <span>Strategy factory</span>
                <strong>{String(strategy?.status?.success ? "ready" : strategy?.status?.error_code || "-")}</strong>
              </div>
              <div className="mini-list">
                <article>
                  <strong>Data and sync</strong>
                  <span>Database freshness and sync plan intent use the Agent desktop facade.</span>
                  <Database size={16} />
                </article>
                <article>
                  <strong>Factory actions</strong>
                  <span>Strategy, factor, and incubation writes create durable approval intents.</span>
                  <Factory size={16} />
                </article>
                <article>
                  <strong>Local user</strong>
                  <span>Responses, sessions, jobs, memory, and quant research use the current local user scope.</span>
                  <UserRound size={16} />
                </article>
              </div>
            </article>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Runtime</span>
                  <h3>Configuration</h3>
                </div>
                <Activity size={18} />
              </div>
              <div className="kv-grid">
                <span>Model</span>
                <strong>{String(agent.model || health?.runtime?.model || "-")}</strong>
                <span>Iterations</span>
                <strong>{String(agent.max_iterations || health?.runtime?.max_iterations || "-")}</strong>
                <span>API token</span>
                <strong>{agent.api_token_configured ? "configured" : "loopback/open"}</strong>
                <span>Control reason</span>
                <strong>{String(agent.control_reason || "-")}</strong>
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Health</span>
                  <h3>Detailed payload</h3>
                </div>
                <StatusBadge status={health?.status || "not_loaded"} />
              </div>
              <JsonPanel value={health || { status: "not_loaded" }} />
            </article>
          </section>

          <details className="raw-details">
            <summary>Raw Agent settings</summary>
            <JsonPanel value={settings || { status: "not_loaded" }} />
          </details>
        </div>
      </div>
    </section>
  );
}
