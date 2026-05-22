import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  FlaskConical,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  XCircle
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

interface IncubationRunnerStatus {
  run_time?: string;
  dry_run?: boolean;
  run_count?: number;
  error_count?: number;
  last_run_at?: string | null;
  last_result_status?: string | null;
  [key: string]: unknown;
}

interface IncubationReport {
  report_date?: string;
  generated_at?: string;
  summary?: {
    total_incubating?: number;
    total_with_signals?: number;
    auto_promoted?: number;
    stage_counts?: Record<string, number>;
  };
  hit_rate_dashboard?: {
    overall?: {
      total_signals?: number;
      hit_count?: number;
      hit_rate?: number;
      avg_skill_lcb?: number;
      avg_forward_sharpe?: number;
      strategy_count?: number;
    };
    by_family?: Record<string, Record<string, number>>;
    by_stage?: Record<string, Record<string, number>>;
    trend?: {
      available?: boolean;
      improvement?: number;
      direction?: "improving" | "declining" | "stable";
    };
  };
  feedback_actions?: {
    families_to_boost?: string[];
    families_to_cooldown?: string[];
    families_to_freeze?: string[];
  };
  [key: string]: unknown;
}

interface StageEvent {
  id: string;
  strategy_id?: string;
  strategy_name?: string;
  event_type: string;
  from_stage?: string;
  to_stage?: string;
  severity?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown, fallback = 0): number {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function percent(value: unknown): string {
  return `${Math.round(asNumber(value) * 100)}%`;
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function eventListFromData(data: unknown): StageEvent[] {
  const record = recordFromUnknown(data);
  const rawEvents = Array.isArray(record.events) ? record.events : [];
  return rawEvents.map((item, index) => {
    const event = recordFromUnknown(item);
    const payload = recordFromUnknown(event.payload);
    return {
      id: compact(event.id || event.event_id || `${event.event_type || "event"}:${index}`),
      strategy_id: compact(event.strategy_id || payload.strategy_id || event.aggregate_id),
      strategy_name: compact(payload.strategy_name || payload.name || event.strategy_id || event.aggregate_id),
      event_type: compact(event.event_type || "unknown"),
      from_stage: compact(payload.from_stage),
      to_stage: compact(payload.to_stage || payload.stage || event.status),
      severity: compact(event.severity || payload.severity || "info"),
      created_at: compact(event.created_at || event.timestamp || payload.created_at),
      payload
    };
  });
}

function latestReportFromEvents(events: StageEvent[]): IncubationReport | null {
  const reportEvent = events.find((event) => event.event_type === "incubation_factory.hit_rate_report_generated");
  const payload = recordFromUnknown(reportEvent?.payload);
  return payload.hit_rate_dashboard || payload.summary ? (payload as IncubationReport) : null;
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    warmup: "Warmup",
    observe: "Observe",
    candidate: "Candidate",
    graduation_ready: "Graduation ready",
    promoted: "Promoted",
    paused: "Paused",
    failed: "Failed",
    retired: "Retired"
  };
  return labels[stage] || stage || "Unknown";
}

function stageTone(stage: string): string {
  if (["promoted", "graduation_ready"].includes(stage)) return "implemented";
  if (["failed", "retired"].includes(stage)) return "failed";
  if (["candidate", "observe", "warmup", "paused"].includes(stage)) return "partial";
  return "not_loaded";
}

function StageDistribution({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (!entries.length) {
    return (
      <div className="empty-mini">
        <FlaskConical size={22} />
        <span>No lifecycle stage counts are available yet.</span>
      </div>
    );
  }
  return (
    <div className="lifecycle-board">
      {entries.map(([stage, count]) => (
        <article className={`lifecycle-column ${stageTone(stage)}`} key={stage}>
          <span>{stageLabel(stage)}</span>
          <strong>{count}</strong>
          <small>{Math.round((count / Math.max(total, 1)) * 100)}% of tracked strategies</small>
        </article>
      ))}
    </div>
  );
}

function FamilyHealth({ report }: { report: IncubationReport | null }) {
  const families = Object.entries(report?.hit_rate_dashboard?.by_family || {}).sort(
    ([, left], [, right]) => asNumber(right.avg_skill_lcb) - asNumber(left.avg_skill_lcb)
  );
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Factor and family health</span>
          <h3>What the incubator is learning</h3>
        </div>
        <Activity size={18} />
      </div>
      <div className="mini-list">
        {families.slice(0, 8).map(([family, metrics]) => {
          const lcb = asNumber(metrics.avg_skill_lcb);
          const status = lcb > 0.02 ? "implemented" : lcb < -0.01 ? "failed" : "partial";
          return (
            <article className={`capability-row ${status === "implemented" ? "ok" : status === "failed" ? "bad" : "warn"}`} key={family}>
              <div>
                <span>{percent(metrics.hit_rate)} hit rate | n={compact(metrics.total_n)}</span>
                <strong>{family}</strong>
              </div>
              <StatusBadge status={status} label={`lcb ${lcb.toFixed(3)}`} />
              <small>Forward Sharpe {asNumber(metrics.avg_forward_sharpe).toFixed(2)} | strategies {compact(metrics.strategy_count)}</small>
            </article>
          );
        })}
        {!families.length && <p className="muted">No family-level hit-rate report has been generated yet.</p>}
      </div>
    </section>
  );
}

function StageTimeline({ events }: { events: StageEvent[] }) {
  const stageEvents = events.filter((event) => event.event_type.includes("incubation")).slice(0, 12);
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Recent lifecycle events</span>
          <h3>Promotion, pause, and retirement trail</h3>
        </div>
        <Clock size={18} />
      </div>
      <div className="mini-list">
        {stageEvents.map((event) => {
          const toStage = event.to_stage || "recorded";
          const Icon = ["promoted", "graduation_ready"].includes(toStage)
            ? CheckCircle2
            : ["failed", "retired"].includes(toStage)
              ? XCircle
              : ArrowUpRight;
          return (
            <article className={`capability-row ${stageTone(toStage) === "implemented" ? "ok" : stageTone(toStage) === "failed" ? "bad" : "warn"}`} key={event.id}>
              <div>
                <span>{formatTime(event.created_at)}</span>
                <strong>
                  <Icon size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
                  {event.strategy_name || event.strategy_id || event.event_type}
                </strong>
              </div>
              <StatusBadge status={stageTone(toStage)} label={stageLabel(toStage)} />
              <small>{event.from_stage && event.to_stage ? `${stageLabel(event.from_stage)} -> ${stageLabel(event.to_stage)}` : event.event_type}</small>
            </article>
          );
        })}
        {!stageEvents.length && <p className="muted">No incubation lifecycle events are available yet.</p>}
      </div>
    </section>
  );
}

function FeedbackActions({ report }: { report: IncubationReport | null }) {
  const actions = report?.feedback_actions || {};
  const boosts = actions.families_to_boost || [];
  const cooldown = actions.families_to_cooldown || [];
  const freeze = actions.families_to_freeze || [];
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Recommended operations</span>
          <h3>Factory feedback</h3>
        </div>
        <ShieldCheck size={18} />
      </div>
      <div className="feedback-grid">
        <article>
          <TrendingUp size={16} />
          <strong>Boost</strong>
          <span>{boosts.length ? boosts.join(", ") : "No boost recommendation"}</span>
        </article>
        <article>
          <TrendingDown size={16} />
          <strong>Cooldown</strong>
          <span>{cooldown.length ? cooldown.join(", ") : "No cooldown recommendation"}</span>
        </article>
        <article>
          <XCircle size={16} />
          <strong>Freeze</strong>
          <span>{freeze.length ? freeze.join(", ") : "No freeze recommendation"}</span>
        </article>
      </div>
    </section>
  );
}

export function IncubationFactoryPanel({ endpoint, apiToken, controlToken = "" }: { endpoint: string; apiToken: string; controlToken?: string }) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [status, setStatus] = useState<IncubationRunnerStatus | null>(null);
  const [report, setReport] = useState<IncubationReport | null>(null);
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [intentEnvelope, setIntentEnvelope] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusEnvelope, eventEnvelope] = await Promise.all([
        client.incubationFactoryStatus(),
        client.strategyDomainEvents({ event_type: "incubation_factory.hit_rate_report_generated", limit: 5 })
      ]);
      const runner = recordFromUnknown(statusEnvelope.data);
      setStatus(runner);

      const reportFromStatus = recordFromUnknown(runner.report);
      const reportEvents = eventListFromData(eventEnvelope.data);
      const latestReport = reportFromStatus.hit_rate_dashboard ? (reportFromStatus as IncubationReport) : latestReportFromEvents(reportEvents);
      setReport(latestReport);

      const stageEnvelope = await client.strategyDomainEvents({ event_type: "incubation.stage_transitioned", limit: 40 });
      setEvents([...eventListFromData(stageEnvelope.data), ...reportEvents]);
      setMessage(statusEnvelope.success ? "INCUBATION_LOADED" : statusEnvelope.error || "INCUBATION_DEGRADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    fetchData().catch(() => undefined);
  }, [fetchData]);

  async function createIntent(action: "run_once" | "dry_run" | "maintenance") {
    setLoading(true);
    try {
      const envelope = await client.factoryIntentCreate(
        `incubation_factory.${action}`,
        { source: "desktop_incubation_factory" },
        `Run Incubation Factory ${action} from Desktop.`
      );
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? `INCUBATION_${action.toUpperCase()}_INTENT_CREATED` : envelope.error || "INCUBATION_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  const overall = report?.hit_rate_dashboard?.overall || {};
  const trend = report?.hit_rate_dashboard?.trend || {};
  const stageCounts = report?.summary?.stage_counts || {};
  const runnerStatus = status?.last_result_status || (status ? "idle" : "not_loaded");
  const runnerTone = runnerStatus === "completed" ? "implemented" : runnerStatus === "failed" ? "failed" : "partial";

  return (
    <div className="capability-stack">
      <section className="capability-banner">
        <div>
          <span>Incubation Center</span>
          <h2>Strategy lifecycle and hit-rate dashboard</h2>
          <p>
            This center turns the incubation factory into an operator view: lifecycle stage, recent failures, hit-rate health, and promotion
            evidence are shown together before any strategy is allowed to graduate.
          </p>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : runnerTone} label={message} />
          <button className="small-button" disabled={loading} onClick={fetchData} type="button">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </section>

      <section className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>Approved operations</span>
            <h3>Run, dry-run, and maintenance intents</h3>
          </div>
          <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label={controlToken.trim() ? "control ready" : "control required"} />
        </div>
        <div className="button-row">
          <button className="primary-button" disabled={loading || !controlToken.trim()} onClick={() => createIntent("run_once")} type="button">
            Run intent
          </button>
          <button className="small-button" disabled={loading || !controlToken.trim()} onClick={() => createIntent("dry_run")} type="button">
            Dry-run intent
          </button>
          <button className="small-button" disabled={loading || !controlToken.trim()} onClick={() => createIntent("maintenance")} type="button">
            Maintenance intent
          </button>
        </div>
        {intentEnvelope ? <JsonPanel value={intentEnvelope} /> : null}
      </section>

      {message.startsWith("AIASK_") && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          {message}. Incubation status will load once the Agent API and strategy storage are reachable.
        </div>
      )}

      <div className="diagnostics-summary wide">
        <MetricCard label="Runner" value={runnerStatus} status={runnerTone} />
        <MetricCard label="Runs" value={status?.run_count ?? "-"} status="implemented" />
        <MetricCard label="Errors" value={status?.error_count ?? "-"} status={(status?.error_count || 0) > 0 ? "failed" : "implemented"} />
        <MetricCard label="Last run" value={formatTime(status?.last_run_at)} />
        <MetricCard label="Hit rate" value={overall.hit_rate === undefined ? "-" : percent(overall.hit_rate)} status={asNumber(overall.hit_rate) >= 0.5 ? "implemented" : "partial"} />
        <MetricCard label="Skill LCB" value={overall.avg_skill_lcb === undefined ? "-" : asNumber(overall.avg_skill_lcb).toFixed(4)} status={asNumber(overall.avg_skill_lcb) > 0 ? "implemented" : "partial"} />
        <MetricCard label="Forward Sharpe" value={overall.avg_forward_sharpe === undefined ? "-" : asNumber(overall.avg_forward_sharpe).toFixed(2)} />
        <MetricCard label="Trend" value={compact(trend.direction || "unknown")} status={trend.direction === "improving" ? "implemented" : trend.direction === "declining" ? "failed" : "partial"} />
      </div>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>Strategy lifecycle board</span>
            <h3>Where strategies are in the incubation funnel</h3>
          </div>
          <FlaskConical size={18} />
        </div>
        <StageDistribution counts={stageCounts} />
      </section>

      <div className="capability-grid two">
        <FamilyHealth report={report} />
        <FeedbackActions report={report} />
      </div>

      <StageTimeline events={events} />

      <details className="raw-details">
        <summary>Raw incubation data</summary>
        <JsonPanel value={{ status, report, events }} />
      </details>
    </div>
  );
}
