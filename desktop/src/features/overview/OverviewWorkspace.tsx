import { Activity, BarChart3, Bot, CalendarClock, Database, Factory, FlaskConical, Layers3, RefreshCw, ServerCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, DesktopDataStatus, DesktopSettingsStatus, FactorFactoryStatus, HealthDetailed } from "../../types";

function factoryEnvelopeStatus(value: unknown): string {
  const envelope = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  if (envelope.success === true) return "ready";
  if ((envelope.data as Record<string, unknown> | undefined)?.gated) return "gated";
  if (envelope.error_code) return "unconfigured";
  return "not_loaded";
}

export function OverviewWorkspace({
  endpoint,
  apiToken,
  controlToken,
  health,
  autoRefresh = true
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  health: HealthDetailed | null;
  autoRefresh?: boolean;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [data, setData] = useState<DesktopDataStatus | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityWorkbenchPayload | null>(null);
  const [factor, setFactor] = useState<FactorFactoryStatus | null>(null);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, dataPayload, capabilitiesPayload, factorPayload, jobsPayload] = await Promise.all([
        api.settingsStatus(),
        api.dataStatus(),
        api.capabilities(),
        api.factorFactoryStatus(20),
        api.jobsList()
      ]);
      setSettings(settingsPayload);
      setData(dataPayload);
      setCapabilities(capabilitiesPayload);
      setFactor(factorPayload);
      setJobs(jobsPayload.data || []);
      setMessage("OVERVIEW_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!autoRefresh) return;
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken, autoRefresh]);

  const mcp = capabilities?.mcp;
  const skills = capabilities?.skills?.skills || [];
  const plugins = Array.isArray(capabilities?.plugins) ? capabilities?.plugins : [];
  const strategyFactory = capabilities?.strategy_factory;
  const control = capabilities?.summary.control;
  const profile = settings?.profile;

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Overview</span>
          <h1>Unified command console</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
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
              <h2>{profile?.profile_name || "Local Operator"}</h2>
              <p>Agent, model providers, databases, MCP, skills, automation, and the three factories are shown as one operator surface.</p>
            </div>
            <div className="status-cluster">
              <StatusBadge status={health?.status || "not_loaded"} label={health?.status || "offline"} />
              <StatusBadge status={control?.authorized ? "ready" : "gated"} label={control?.authorized ? "control authorized" : "control gated"} />
            </div>
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="Agent" value={health?.status || "offline"} status={health?.status || "not_loaded"} />
            <MetricCard label="LLM" value={settings?.llm.ai_status?.provider || "-"} status={settings?.llm.ai_status?.configured ? "ready" : "unconfigured"} />
            <MetricCard label="Database" value={data?.database?.writable === false ? "blocked" : data?.status || "-"} status={data?.status} />
            <MetricCard label="Jobs" value={jobs.length} status={jobs.length ? "ready" : "not_loaded"} />
          </div>

          <section className="capability-grid three">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Agent runtime</span>
                  <h3>Endpoint and user scope</h3>
                </div>
                <Bot size={18} />
              </div>
              <div className="kv-grid">
                <span>User</span>
                <strong>{profile?.user_id || "local"}</strong>
                <span>Mode</span>
                <strong>{compact(settings?.agent?.toolset)}</strong>
                <span>Tools</span>
                <strong>{health?.tools?.count ?? "-"}</strong>
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>MCP and skills</span>
                  <h3>Extension plane</h3>
                </div>
                <ServerCog size={18} />
              </div>
              <div className="kv-grid">
                <span>MCP</span>
                <strong>{mcp?.discovery_status || "-"}</strong>
                <span>Skills</span>
                <strong>{Array.isArray(skills) ? skills.length : 0}</strong>
                <span>Plugins</span>
                <strong>{plugins?.length || 0}</strong>
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Data quality</span>
                  <h3>Freshness gate</h3>
                </div>
                <Database size={18} />
              </div>
              <div className="kv-grid">
                <span>Codes</span>
                <strong>{data?.codes?.length || 0}</strong>
                <span>Missing</span>
                <strong>{data?.missing_count ?? "-"}</strong>
                <span>Stale</span>
                <strong>{data?.stale_count ?? "-"}</strong>
              </div>
            </article>
          </section>

          <section className="capability-grid three">
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>Strategy Factory</span>
                  <h3>Generation and review</h3>
                </div>
                <Factory size={18} />
              </div>
              <StatusBadge status={factoryEnvelopeStatus(strategyFactory?.status)} />
              <p className="muted">Recent runs and review snapshots are available from the dedicated factory page.</p>
            </article>
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>Factor Factory</span>
                  <h3>Mining and pool health</h3>
                </div>
                <BarChart3 size={18} />
              </div>
              <StatusBadge status={factor?.status || "not_loaded"} />
              <p className="muted">{factor?.active_factors?.length || 0} active factors in the desktop snapshot.</p>
            </article>
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>Incubation Factory</span>
                  <h3>Forward verification</h3>
                </div>
                <FlaskConical size={18} />
              </div>
              <StatusBadge status={factoryEnvelopeStatus(capabilities?.strategy_factory?.review_snapshot)} label="review linked" />
              <p className="muted">Lifecycle events and hit-rate reports are shown in the incubation page.</p>
            </article>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Automation</span>
                  <h3>Scheduled jobs</h3>
                </div>
                <CalendarClock size={18} />
              </div>
              <div className="mini-list">
                {jobs.slice(0, 5).map((job) => (
                  <article key={String(job.job_id || job.id)}>
                    <strong>{String(job.name || job.job_id)}</strong>
                    <span>{String(job.schedule || job.interval_seconds || "manual")}</span>
                    <StatusBadge status={job.enabled ? "ready" : "disabled"} label={job.enabled ? "enabled" : "disabled"} />
                  </article>
                ))}
                {!jobs.length && <p className="muted">No automation jobs are configured.</p>}
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Installed skills</span>
                  <h3>Operator playbooks</h3>
                </div>
                <Layers3 size={18} />
              </div>
              <div className="mini-list">
                {(Array.isArray(skills) ? skills : []).slice(0, 6).map((skill) => (
                  <article key={String(skill.name)}>
                    <strong>{String(skill.name)}</strong>
                    <span>{String(skill.description || skill.path || "No description")}</span>
                  </article>
                ))}
                {!Array.isArray(skills) || !skills.length ? <p className="muted">Skills are gated until control access is available.</p> : null}
              </div>
            </article>
          </section>

          <details className="raw-details">
            <summary>Raw overview snapshot</summary>
            <JsonPanel value={{ settings, data, capabilities, factor, jobs }} />
          </details>
        </div>
      </div>
    </section>
  );
}
