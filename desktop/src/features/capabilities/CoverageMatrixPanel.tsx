import { Activity, Database, Factory, Filter, Layers3, ServerCog, ShieldCheck, UserRound, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import type {
  CapabilityMatrixItem,
  CapabilityWorkbenchPayload,
  DesktopDataStatus,
  DesktopSettingsStatus,
  FactorFactoryStatus,
  HealthDetailed,
  ToolCatalogItem
} from "../../types";
import { collectCapabilityRows, itemLabel } from "./capabilityUtils";

interface CoverageRow {
  id: string;
  domain: string;
  capability: string;
  backend: string;
  desktopApi: string;
  frontend: string;
  testPath: string;
  status: string;
  notes?: string;
  source?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function sideEffectLabel(tool: ToolCatalogItem): string {
  const sideEffect = tool.side_effect;
  if (typeof sideEffect === "string") return sideEffect || "unknown";
  if (isRecord(sideEffect) && typeof sideEffect.level === "string") return sideEffect.level || "unknown";
  return "unknown";
}

function rowStatus(value: unknown, fallback = "not_loaded"): string {
  if (!value) return fallback;
  if (typeof value === "string") return value;
  if (!isRecord(value)) return fallback;
  if (value.success === true) return "implemented";
  if (value.success === false) return value.error_code ? "unconfigured" : "failed";
  if (typeof value.status === "string") return value.status;
  return fallback;
}

function normalizeStatus(status: string): string {
  const value = status.toLowerCase();
  if (["ready", "implemented", "passed", "success", "live_backend"].includes(value)) return "implemented";
  if (["partial", "live_unverified", "skipped_missing_credentials", "unconfigured", "gated"].includes(value)) return value;
  if (["failed", "missing", "blocked", "error"].includes(value)) return "failed";
  return value || "not_loaded";
}

function rowFromTool(tool: ToolCatalogItem): CoverageRow {
  const sideEffect = sideEffectLabel(tool);
  const readOnly = sideEffect === "read_only";
  return {
    id: `tool:${tool.name}`,
    domain: tool.category || tool.capability || "agent_tool",
    capability: tool.name,
    backend: "Agent tool registry",
    desktopApi: readOnly ? `/v1/tools/${tool.name}` : "control token / intent gated",
    frontend: readOnly ? "Tools safe probe" : "Tools gated action record",
    testPath: readOnly ? "Click Fill example or Run safe probe in Tools." : "Verify disabled/gated state; create intent only from approved panels.",
    status: normalizeStatus(tool.status || (readOnly ? "implemented" : "gated")),
    notes: tool.description,
    source: tool
  };
}

function rowFromHermes(item: CapabilityMatrixItem, index: number): CoverageRow {
  const tools = Array.isArray(item.aiask_tools) ? item.aiask_tools.join(", ") : compact(item.aiask_tools);
  return {
    id: `hermes:${itemLabel(item)}:${index}`,
    domain: `Hermes / ${item.area || "parity"}`,
    capability: itemLabel(item),
    backend: String(item.code_status || item.live_status || item.status || "mapped"),
    desktopApi: tools || "/v1/hermes/status",
    frontend: "Capabilities / Hermes and Coverage Matrix",
    testPath: "Filter Hermes rows and verify mapped AIASK tools or credential gaps.",
    status: normalizeStatus(String(item.status || item.live_status || item.code_status || "live_unverified")),
    notes: String(item.description || item.error || item.required_env || ""),
    source: item
  };
}

function appendIf(rows: CoverageRow[], row: CoverageRow | null | undefined) {
  if (row) rows.push(row);
}

export function buildCoverageRows({
  capabilities,
  data,
  factor,
  health,
  jobs = [],
  settings,
  tools = []
}: {
  capabilities?: CapabilityWorkbenchPayload | null;
  data?: DesktopDataStatus | null;
  factor?: FactorFactoryStatus | null;
  health?: HealthDetailed | null;
  jobs?: Array<Record<string, unknown>>;
  settings?: DesktopSettingsStatus | null;
  tools?: ToolCatalogItem[];
}): CoverageRow[] {
  const rows: CoverageRow[] = [];
  rows.push(...tools.map(rowFromTool));
  rows.push(...collectCapabilityRows(capabilities || null).map(rowFromHermes));

  appendIf(rows, {
    id: "runtime:agent",
    domain: "Agent runtime",
    capability: "health, tool registry, response runtime",
    backend: health?.service || "AIASK Agent",
    desktopApi: "/health/detailed, /v1/tools, /v1/responses",
    frontend: "Overview, Agent, Workbench, Tools",
    testPath: "Click Sync/Refresh, run a safe prompt, inspect timeline and run events.",
    status: normalizeStatus(health?.status || "not_loaded"),
    notes: `${health?.tools?.count ?? 0} tools / ${health?.tools?.toolset || "unknown"}`
  });

  const llm = settings?.llm.ai_status;
  appendIf(rows, {
    id: "runtime:llm",
    domain: "Models",
    capability: "LLM provider, model, root project API env",
    backend: llm?.configured ? "configured" : "missing/mock",
    desktopApi: "/v1/desktop/settings/status, /v1/ai/status, /v1/ai/models",
    frontend: "Models, Settings, Capabilities / AI Tests",
    testPath: "Refresh models and run AI smoke; verify secrets are redacted.",
    status: normalizeStatus(llm?.configured ? "implemented" : "unconfigured"),
    notes: `${llm?.provider || "-"} / ${llm?.model || "-"}`
  });

  appendIf(rows, {
    id: "data:sync",
    domain: "Data & Sync",
    capability: "SQLite/AKShare freshness, quality gate, sync-plan intent",
    backend: data?.database?.writable === false ? "database blocked" : data?.status || "not_loaded",
    desktopApi: "/v1/desktop/data/status, /v1/desktop/data/sync-plan, /intents",
    frontend: "Data & Sync",
    testPath: "Refresh data, generate plan, create approval intent only with control token.",
    status: normalizeStatus(data?.status || "not_loaded"),
    notes: `${data?.codes?.length || 0} codes / missing ${data?.missing_count ?? "-"} / stale ${data?.stale_count ?? "-"}`
  });

  const mcp = capabilities?.mcp;
  appendIf(rows, {
    id: "mcp:service",
    domain: "MCP",
    capability: "registered servers, tools, resources, prompts, OAuth",
    backend: mcp?.gated ? "control gated" : mcp?.discovery_status || "not_loaded",
    desktopApi: "/v1/mcp/* via Agent",
    frontend: "MCP, Capabilities / MCP",
    testPath: "Discover server, read safe resource, get prompt, start OAuth in mock/control mode.",
    status: normalizeStatus(mcp?.gated ? "gated" : mcp?.discovery_status || "not_loaded"),
    notes: `${mcp?.tools?.length || 0} tools / ${mcp?.resources?.length || 0} resources / ${mcp?.prompts?.length || 0} prompts`
  });
  (mcp?.tools || []).forEach((tool, index) => {
    rows.push({
      id: `mcp-tool:${tool.server || "server"}:${tool.wrapped_name || tool.name}:${index}`,
      domain: `MCP / ${tool.domain || tool.server || "server"}`,
      capability: tool.wrapped_name || tool.name,
      backend: tool.configured === false ? "unconfigured" : "discovered",
      desktopApi: "/v1/mcp/tools, /v1/tools/agent_mcp_*",
      frontend: "MCP dynamic tools, Tools safe probe",
      testPath: "Inspect tool contract; run only read-only wrapped MCP tools.",
      status: normalizeStatus(tool.configured === false ? "unconfigured" : "implemented"),
      notes: tool.description || tool.name,
      source: tool
    });
  });

  const strategy = capabilities?.strategy_factory;
  appendIf(rows, {
    id: "factory:strategy",
    domain: "Strategy Factory",
    capability: "scheduler status, recent runs, review snapshot, run intent",
    backend: rowStatus(strategy?.status),
    desktopApi: "agent_factory_status, agent_factory_runs, /intents",
    frontend: "Strategy Factory, Capabilities / Strategy Factory",
    testPath: "Refresh status and create run intent; confirm only through approval inspector.",
    status: normalizeStatus(rowStatus(strategy?.status)),
    source: strategy
  });

  appendIf(rows, {
    id: "factory:factor",
    domain: "Factor Mining Factory",
    capability: "active pool, engine health, run and maintenance intents",
    backend: factor?.configured === false ? "unconfigured" : factor?.status || "not_loaded",
    desktopApi: "/v1/desktop/factor-factory/status, /intents",
    frontend: "Factor Factory",
    testPath: "Refresh status, create run intent and maintenance intent in mock/control mode.",
    status: normalizeStatus(factor?.status || "not_loaded"),
    notes: `${factor?.active_factors?.length || 0} active factors`,
    source: factor
  });

  appendIf(rows, {
    id: "factory:incubation",
    domain: "Incubation Factory",
    capability: "runner status, lifecycle events, hit-rate dashboard, run/dry-run/maintenance intents",
    backend: rowStatus(strategy?.review_snapshot),
    desktopApi: "agent_incubation_factory_status, agent_strategy_domain_events, /intents",
    frontend: "Incubation",
    testPath: "Refresh lifecycle board and create run/dry-run/maintenance intents in mock/control mode.",
    status: normalizeStatus(rowStatus(strategy?.review_snapshot)),
    source: strategy?.review_snapshot
  });

  const profile = settings?.profile;
  appendIf(rows, {
    id: "user:local",
    domain: "Local User",
    capability: "local profile, user_id scope, sessions, messages, memory search",
    backend: profile?.status || "ready",
    desktopApi: "/v1/desktop/users/local-profile, /v1/hermes/sessions, /v1/search, agent_memory_search",
    frontend: "Local User, Settings, Workbench",
    testPath: "Save local profile, list sessions, load messages, search user data and memory.",
    status: normalizeStatus(profile?.status || "implemented"),
    notes: `${profile?.user_id || "local"} / ${profile?.profile_name || "Local Operator"}`
  });

  appendIf(rows, {
    id: "automation:jobs",
    domain: "Automation",
    capability: "job list/create/update/delete/run with user ownership",
    backend: jobs.length ? "configured" : "empty",
    desktopApi: "/v1/jobs",
    frontend: "Automation",
    testPath: "Create, inspect, pause/resume, run, and delete a mock job.",
    status: normalizeStatus(jobs.length ? "implemented" : "not_loaded"),
    notes: `${jobs.length} jobs`
  });

  const skills = capabilities?.skills?.skills || [];
  appendIf(rows, {
    id: "skills:native",
    domain: "Skills",
    capability: "native skill list, install/update/delete, skill packs",
    backend: capabilities?.skills?.gated ? "control gated" : "loaded",
    desktopApi: "/v1/skills, agent_skill_*",
    frontend: "Skills, Capabilities / Skills and Plugins",
    testPath: "Verify gated state; install/update/delete only in mock/control mode.",
    status: normalizeStatus(capabilities?.skills?.gated ? "gated" : "implemented"),
    notes: `${Array.isArray(skills) ? skills.length : 0} skills`
  });

  const pluginList = Array.isArray(capabilities?.plugins)
    ? capabilities?.plugins
    : isRecord(capabilities?.plugins) && Array.isArray(capabilities?.plugins.data)
      ? capabilities?.plugins.data
      : [];
  appendIf(rows, {
    id: "plugins:native",
    domain: "Plugins",
    capability: "native plugin registry, enable/disable, tool test",
    backend: isRecord(capabilities?.plugins) && capabilities?.plugins.gated ? "control gated" : "loaded",
    desktopApi: "/v1/plugins, agent_plugin_*",
    frontend: "Capabilities / Plugins",
    testPath: "Verify gated state; toggle and test tool only in mock/control mode.",
    status: normalizeStatus(isRecord(capabilities?.plugins) && capabilities?.plugins.gated ? "gated" : "implemented"),
    notes: `${pluginList?.length || 0} plugins`
  });

  return rows;
}

export function CoverageMatrixPanel({
  capabilities,
  data,
  factor,
  health,
  jobs = [],
  settings,
  tools = []
}: {
  capabilities?: CapabilityWorkbenchPayload | null;
  data?: DesktopDataStatus | null;
  factor?: FactorFactoryStatus | null;
  health?: HealthDetailed | null;
  jobs?: Array<Record<string, unknown>>;
  settings?: DesktopSettingsStatus | null;
  tools?: ToolCatalogItem[];
}) {
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("all");
  const [status, setStatus] = useState("all");
  const rows = useMemo(
    () => buildCoverageRows({ capabilities, data, factor, health, jobs, settings, tools }),
    [capabilities, data, factor, health, jobs, settings, tools]
  );
  const domains = useMemo(() => Array.from(new Set(rows.map((row) => row.domain))).sort(), [rows]);
  const statuses = useMemo(() => Array.from(new Set(rows.map((row) => row.status))).sort(), [rows]);
  const visible = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesQuery = !normalizedQuery || JSON.stringify(row).toLowerCase().includes(normalizedQuery);
      const matchesDomain = domain === "all" || row.domain === domain;
      const matchesStatus = status === "all" || row.status === status;
      return matchesQuery && matchesDomain && matchesStatus;
    });
  }, [domain, query, rows, status]);

  const counts = rows.reduce<Record<string, number>>((bucket, row) => {
    bucket[row.status] = (bucket[row.status] || 0) + 1;
    return bucket;
  }, {});
  const implemented = counts.implemented || counts.ready || 0;
  const gated = (counts.gated || 0) + (counts.unconfigured || 0);
  const failed = (counts.failed || 0) + (counts.missing || 0) + (counts.blocked || 0);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Coverage Matrix</span>
          <h2>Actual project capability coverage</h2>
          <p>
            This matrix is built from live Agent HTTP surfaces, Hermes parity, MCP discovery, factories, user state, and Desktop API coverage.
          </p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={failed ? "failed" : gated ? "partial" : "implemented"} label={`${rows.length} capabilities`} />
          <StatusBadge status={capabilities?.summary.source || "not_loaded"} label={capabilities?.summary.source || "not loaded"} />
        </div>
      </div>

      <div className="diagnostics-summary wide">
        <MetricCard label="Implemented" value={implemented} status="implemented" />
        <MetricCard label="Gated/Config" value={gated} status={gated ? "partial" : "implemented"} />
        <MetricCard label="Failed/Missing" value={failed} status={failed ? "failed" : "implemented"} />
        <MetricCard label="Rows" value={rows.length} status={rows.length ? "ready" : "not_loaded"} />
      </div>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>Traceability</span>
            <h3>Source to frontend test path</h3>
          </div>
          <Filter size={18} />
        </div>
        <div className="coverage-filters">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search capability, API, frontend, tool..." />
          <select value={domain} onChange={(event) => setDomain(event.target.value)}>
            <option value="all">all domains</option>
            {domains.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">all status</option>
            {statuses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="coverage-table">
          <div className="coverage-row coverage-head">
            <span>Capability</span>
            <span>Backend</span>
            <span>Desktop API</span>
            <span>Frontend</span>
            <span>Test Path</span>
            <span>Status</span>
          </div>
          {visible.map((row) => (
            <details className="coverage-row coverage-item" key={row.id}>
              <summary>
                <strong>{row.capability}</strong>
                <span>{row.backend}</span>
                <span>{row.desktopApi}</span>
                <span>{row.frontend}</span>
                <span>{row.testPath}</span>
                <StatusBadge status={row.status} />
              </summary>
              <div className="coverage-detail">
                <div className="kv-grid">
                  <span>Domain</span>
                  <strong>{row.domain}</strong>
                  <span>Notes</span>
                  <strong>{row.notes || "-"}</strong>
                </div>
                <JsonPanel value={row.source || row} />
              </div>
            </details>
          ))}
          {!visible.length && <p className="muted table-empty">No capability rows match the filters.</p>}
        </div>
      </section>

      <section className="capability-grid three">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Finance Safe</span>
              <h3>Agent and quant read tools</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          <p className="muted">Stock analysis, data gate, factor validation, backtest, risk, strategy events, memory, and session search are tested through safe probes.</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Hermes Full</span>
              <h3>Full-mode parity</h3>
            </div>
            <Wrench size={18} />
          </div>
          <p className="muted">File, terminal, browser, web, multimodal, gateway, learning, RL, skills, plugins, MCP, and jobs stay control-token gated.</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Factories</span>
              <h3>Approved operations</h3>
            </div>
            <Factory size={18} />
          </div>
          <p className="muted">Strategy, factor, and incubation factories expose status read paths and create durable intents for state changes.</p>
        </article>
      </section>

      <section className="capability-grid three">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Data Plane</span>
              <h3>DB and MCP</h3>
            </div>
            <Database size={18} />
          </div>
          <p className="muted">SQLite/AKShare readiness, TDX/Tushare source status, dynamic MCP tools, resources, prompts, and OAuth are covered through Agent HTTP.</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>User Plane</span>
              <h3>Profile and memory</h3>
            </div>
            <UserRound size={18} />
          </div>
          <p className="muted">Local profile, user_id propagation, sessions, messages, responses, jobs, and financial memory search are visible and testable.</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Extensions</span>
              <h3>Skills and plugins</h3>
            </div>
            <Layers3 size={18} />
          </div>
          <p className="muted">Native skill and plugin management stays explicit, gated, and mock-testable without loading external dashboard JavaScript.</p>
        </article>
      </section>
    </div>
  );
}
