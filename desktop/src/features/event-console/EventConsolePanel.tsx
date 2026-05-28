import { AlertTriangle, Clock3, Filter, RefreshCw, Search, ShieldCheck, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, shortText } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

interface StrategyDomainEvent {
  id: string;
  strategy_id?: string;
  aggregate_id?: string;
  aggregate_type?: string;
  event_type: string;
  severity?: string;
  status?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

interface Props {
  endpoint: string;
  apiToken: string;
}

const EVENT_TYPE_OPTIONS = [
  "",
  "incubation.stage_transitioned",
  "incubation_factory.hit_rate_report_generated",
  "factory.run_completed",
  "runtime.risk_event",
  "strategy.promoted",
  "strategy.deprecated"
];

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function eventListFromData(data: unknown): StrategyDomainEvent[] {
  const record = recordFromUnknown(data);
  const rawEvents = Array.isArray(record.events) ? record.events : Array.isArray(data) ? data : [];
  return rawEvents.map((item, index) => {
    const event = recordFromUnknown(item);
    const payload = recordFromUnknown(event.payload);
    return {
      ...event,
      id: compact(event.id || event.event_id || event.rowid || `${event.event_type || "event"}:${index}`),
      event_type: compact(event.event_type || event.type || "unknown"),
      strategy_id: compact(event.strategy_id || payload.strategy_id || event.aggregate_id),
      severity: compact(event.severity || payload.severity || "info"),
      status: compact(event.status || payload.status || "recorded"),
      created_at: compact(event.created_at || event.timestamp || payload.created_at),
      payload
    };
  });
}

function eventTitle(event: StrategyDomainEvent): string {
  const payload = recordFromUnknown(event.payload);
  return compact(payload.strategy_name || payload.title || payload.name || event.strategy_id || event.aggregate_id || event.event_type);
}

function eventSummary(event: StrategyDomainEvent): string {
  const payload = recordFromUnknown(event.payload);
  const parts = [
    payload.reason,
    payload.decision,
    payload.from_stage && payload.to_stage ? `${payload.from_stage} -> ${payload.to_stage}` : "",
    payload.error,
    payload.message
  ]
    .map((part) => compact(part))
    .filter((part) => part !== "-");
  return shortText(parts.join(" | ") || compact(event.event_type), 150);
}

function formatTime(value?: string): string {
  if (!value || value === "-") return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function EventConsolePanel({ endpoint, apiToken }: Props) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken }), [apiToken, endpoint]);
  const [events, setEvents] = useState<StrategyDomainEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");
  const [strategyId, setStrategyId] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState("");
  const [query, setQuery] = useState("");

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const envelope = await client.strategyDomainEvents({
        strategy_id: strategyId.trim() || undefined,
        event_type: eventType || undefined,
        severity: severity || undefined,
        limit: 100
      });
      const nextEvents = eventListFromData(envelope.data);
      setEvents(nextEvents);
      setMessage(envelope.success ? "EVENTS_LOADED" : envelope.error || "EVENTS_DEGRADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }, [client, eventType, severity, strategyId]);

  useEffect(() => {
    loadEvents().catch(() => undefined);
  }, [loadEvents]);

  const filteredEvents = events.filter((event) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return JSON.stringify(event).toLowerCase().includes(needle);
  });

  const criticalCount = filteredEvents.filter((event) => ["high", "critical", "error"].includes(compact(event.severity).toLowerCase())).length;
  const incubationCount = filteredEvents.filter((event) => event.event_type.includes("incubation")).length;

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>策略事件控制台</span>
          <h1>生命周期、风险与孵化事件</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "implemented"} label={message} />
          <button className="small-button" disabled={loading} onClick={loadEvents} type="button">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-banner">
            <div>
              <span>只读 Agent 工具</span>
              <h2>真实策略领域事件</h2>
              <p>
                控制台通过 `/v1/tools` 读取 `agent_strategy_domain_events`。这里刻意保持只读，方便操作者查看生命周期变化，同时不绕过 Agent 安全边界。
              </p>
            </div>
            <div className="status-cluster">
              <StatusBadge status="implemented" label={`${filteredEvents.length} 条可见`} />
              <StatusBadge status={criticalCount ? "failed" : "implemented"} label={`${criticalCount} 条严重`} />
              <StatusBadge status={incubationCount ? "implemented" : "not_loaded"} label={`${incubationCount} 条孵化`} />
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>筛选</span>
                <h3>查找需要关注的事件</h3>
              </div>
              <Filter size={18} />
            </div>
            <div className="event-filter-grid">
              <label>
                <span>策略</span>
                <input value={strategyId} onChange={(event) => setStrategyId(event.target.value)} placeholder="策略 ID" />
              </label>
              <label>
                <span>事件类型</span>
                <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
                  {EVENT_TYPE_OPTIONS.map((option) => (
                    <option key={option || "all"} value={option}>
                      {option || "全部事件"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>严重级别</span>
                <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
                  <option value="">全部级别</option>
                  <option value="info">info</option>
                  <option value="warning">warning</option>
                  <option value="high">high</option>
                  <option value="critical">critical</option>
                </select>
              </label>
              <label>
                <span>搜索</span>
                <div className="search-field">
                  <Search size={14} />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="payload 文本" />
                </div>
              </label>
            </div>
          </section>

          {message.startsWith("AIASK_") && (
            <div className="notice warn">
              <AlertTriangle size={15} />
              {message}. Agent API 可用后事件控制台会自动恢复。
            </div>
          )}

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>最近事件</span>
                <h3>生命周期流</h3>
              </div>
              <Zap size={18} />
            </div>
            <div className="event-list">
              {filteredEvents.map((event) => (
                <article className="event-card" key={event.id}>
                  <div className="event-card-main">
                    <div className="event-card-icon">
                      <Clock3 size={15} />
                    </div>
                    <div>
                      <span>{event.event_type}</span>
                      <strong>{eventTitle(event)}</strong>
                      <p>{eventSummary(event)}</p>
                    </div>
                  </div>
                  <div className="event-card-meta">
                    <StatusBadge status={event.severity} label={event.severity || "info"} />
                    <small>{formatTime(event.created_at)}</small>
                  </div>
                  <details className="raw-details">
                    <summary>证据 payload</summary>
                    <JsonPanel value={event} />
                  </details>
                </article>
              ))}
              {!filteredEvents.length && (
                <div className="empty-mini">
                  <ShieldCheck size={24} />
                  <span>没有匹配的策略事件。请调整筛选条件，或在工厂/孵化运行后刷新。</span>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
