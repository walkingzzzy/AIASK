import { ArrowRight, Clock3, Filter, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { DesktopRunSummary, MainView, NormalizedRunEvent } from "../../types";

const KIND_OPTIONS = ["all", "tool", "approval", "gateway", "mcp", "error", "system"] as const;
type EventKind = Exclude<(typeof KIND_OPTIONS)[number], "all">;

function normalizedKind(event: NormalizedRunEvent): EventKind {
  const kind = String(event.kind || "").toLowerCase();
  if (["tool", "approval", "gateway", "mcp", "error", "system"].includes(kind)) return kind as EventKind;
  const eventType = String(event.event_type || event.event || "").toLowerCase();
  const title = String(event.title || "").toLowerCase();
  const payload = event.data || {};
  if (eventType.includes("approval") || eventType.includes("intent") || title.includes("approval")) return "approval";
  if (eventType.includes("gateway") || title.includes("gateway") || payload.platform) return "gateway";
  if (eventType.includes("mcp") || title.includes("mcp")) return "mcp";
  if (eventType.includes("error") || eventType.includes("failed") || event.severity === "error") return "error";
  if (eventType.includes("tool") || title.includes("tool")) return "tool";
  return "system";
}

function inferJumpTarget(event: NormalizedRunEvent): MainView {
  const kind = normalizedKind(event);
  if (kind === "approval" || kind === "tool") return "tools-intents-approvals";
  if (kind === "mcp") return "mcp-connectors";
  if (kind === "gateway") return "gateway";
  if (kind === "error") return "readiness-health";
  return "runs-events";
}

function normalizeEvent(event: NormalizedRunEvent): NormalizedRunEvent {
  const kind = normalizedKind(event);
  const data = event.data && typeof event.data === "object" ? event.data : {};
  const title = event.title || event.event_type || event.event || `${kind}.event`;
  const severity = event.severity || (kind === "error" ? "error" : "info");
  return {
    ...event,
    data,
    kind,
    title,
    severity,
    event_type: event.event_type || event.event,
    status: event.status || String(data.status || severity),
    tool_name: event.tool_name || (typeof data.tool_name === "string" ? data.tool_name : typeof data.tool === "string" ? data.tool : undefined),
    error_message:
      event.error_message ||
      (typeof data.error_message === "string" ? data.error_message : typeof data.error === "string" ? data.error : undefined),
    jump_target: event.jump_target || inferJumpTarget({ ...event, kind }),
  };
}

function eventTime(event: NormalizedRunEvent): string {
  return String(event.created_at || event.timestamp || "-");
}

function lastEventLabel(run: DesktopRunSummary): string {
  const event = run.last_event ? normalizeEvent(run.last_event) : null;
  return event ? String(event.title || event.event_type || event.event || "event") : "not_loaded";
}

export function RunsEventsPage({
  endpoint,
  apiToken,
  controlToken,
  onOpenView,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  onOpenView: (view: MainView) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [runs, setRuns] = useState<DesktopRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [events, setEvents] = useState<NormalizedRunEvent[]>([]);
  const [filterKind, setFilterKind] = useState<(typeof KIND_OPTIONS)[number]>("all");
  const [viewMode, setViewMode] = useState<"timeline" | "list">("timeline");
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function loadRunEvents(runId: string) {
    const runEvents = await api.runEvents(runId, controlToken.trim() || apiToken);
    setEvents((runEvents || []).map(normalizeEvent));
  }

  async function loadRuns() {
    setBusy(true);
    try {
      const payload = await api.runsList({ limit: 80 });
      const nextRuns = payload.data || [];
      setRuns(nextRuns);
      const nextRunId = selectedRunId || nextRuns[0]?.run_id || "";
      setSelectedRunId(nextRunId);
      setMessage("RUNS_LOADED");
      if (nextRunId) {
        await loadRunEvents(nextRunId);
      } else {
        setEvents([]);
      }
    } catch (error) {
      setMessage(formatApiError(error));
      setEvents([]);
      setRuns([]);
    } finally {
      setBusy(false);
    }
  }

  async function selectRun(runId: string) {
    setBusy(true);
    try {
      setSelectedRunId(runId);
      await loadRunEvents(runId);
      setMessage("RUN_EVENTS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadRuns().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const visibleEvents = useMemo(
    () => events.filter((item) => filterKind === "all" || normalizedKind(item) === filterKind),
    [events, filterKind]
  );

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Agent 运行</span>
          <h1>运行 / 事件</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message} label={message} />
          <button className="small-button" disabled={busy} onClick={() => loadRuns()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="page-split">
          <section className="capability-section session-list-panel">
            <div className="section-header">
              <div>
                <span>{runs.length} 个运行</span>
                <h3>运行摘要</h3>
              </div>
              <Clock3 size={18} />
            </div>
            <div className="mini-list">
              {runs.map((run) => (
                <button
                  className={selectedRunId === run.run_id ? "active" : ""}
                  key={run.run_id}
                  onClick={() => selectRun(run.run_id)}
                  type="button"
                >
                  <strong>{run.run_id}</strong>
                  <span>{run.status || "unknown"}</span>
                  <span>
                    工具 {run.tool_call_count ?? 0} / 审批 {run.approval_count ?? 0} / 错误 {run.error_count ?? 0}
                  </span>
                  <span>最近事件：{lastEventLabel(run)}</span>
                  <span className="session-flags">
                    {run.has_pending_approval ? <StatusBadge status="queued" label="approval" /> : null}
                    {run.has_errors ? <StatusBadge status="error" label="error" /> : null}
                  </span>
                </button>
              ))}
              {!runs.length ? <p className="muted">暂无运行摘要。</p> : null}
            </div>
          </section>

          <section className="capability-section session-detail-panel">
            <div className="section-header">
              <div>
                <span>{selectedRunId || "未选择"}</span>
                <h3>运行事件</h3>
              </div>
              <div className="header-actions">
                <div className="segmented" role="group" aria-label="runs view mode">
                  <button className={viewMode === "timeline" ? "active" : ""} onClick={() => setViewMode("timeline")} type="button">
                    时间线
                  </button>
                  <button className={viewMode === "list" ? "active" : ""} onClick={() => setViewMode("list")} type="button">
                    列表
                  </button>
                </div>
              </div>
            </div>

            <div className="filter-row">
              <select value={filterKind} onChange={(event) => setFilterKind(event.target.value as (typeof KIND_OPTIONS)[number])}>
                {KIND_OPTIONS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </div>

            <div className={viewMode === "timeline" ? "mini-list event-timeline-list" : "mini-list"}>
              {visibleEvents.map((event, index) => {
                const normalized = normalizeEvent(event);
                const jumpTarget = normalized.jump_target || inferJumpTarget(normalized);
                return (
                  <article className="event-row" key={`${normalized.id || normalized.event || "event"}:${index}`}>
                    <div className="event-row-head">
                      <strong>{normalized.title || normalized.event || "Event"}</strong>
                      <StatusBadge status={normalized.severity || normalized.status || normalized.kind} label={String(normalized.kind || "system")} />
                    </div>
                    <span>{eventTime(normalized)}</span>

                    {normalized.tool_name ? (
                      <div className="event-meta">
                        <span className="event-label">工具:</span>
                        <code>{String(normalized.tool_name)}</code>
                      </div>
                    ) : null}
                    {normalized.error_message ? (
                      <div className="event-meta error">
                        <span className="event-label">错误:</span>
                        <span>{String(normalized.error_message)}</span>
                      </div>
                    ) : null}

                    <button className="small-button" onClick={() => onOpenView(jumpTarget as MainView)} type="button">
                      <ArrowRight size={13} />
                      跳转到 {String(jumpTarget)}
                    </button>
                    <details className="raw-details">
                      <summary>
                        <Filter size={13} />
                        原始事件
                      </summary>
                      <JsonPanel value={normalized} />
                    </details>
                  </article>
                );
              })}
              {!visibleEvents.length ? <p className="muted">当前筛选条件下没有事件。</p> : null}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
