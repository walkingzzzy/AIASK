import { Bot, ChevronDown } from "lucide-react";
import type { TaskThread, TimelineEvent } from "../types";
import { compact, JsonPanel, StatusBadge } from "./shared";

function eventName(value: unknown, fallback = "event"): string {
  if (!value || typeof value !== "object") return fallback;
  const record = value as Record<string, unknown>;
  return String(record.event || record.type || fallback);
}

function eventStatus(value: unknown): string {
  if (!value || typeof value !== "object") return "ready";
  const record = value as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? (record.data as Record<string, unknown>) : {};
  return compact(record.status || data.status || "ready");
}

function eventTimestamp(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return compact(record.created_at || record.timestamp || "");
}

function eventBody(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? (record.data as Record<string, unknown>) : {};
  const content = record.content || data.content || record.message || data.message;
  return typeof content === "string" && content.trim() ? content : undefined;
}

function isApprovalEvent(value: unknown): boolean {
  const name = eventName(value, "").toLowerCase();
  return name.includes("approval") || name.includes("intent") || name.includes("control");
}

function timelineEventKey(value: unknown): string {
  if (!value || typeof value !== "object") return compact(value);
  const record = value as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? (record.data as Record<string, unknown>) : {};
  const parts = [
    eventName(record, "event"),
    compact(record.run_id || data.run_id || ""),
    compact(record.created_at || data.created_at || record.timestamp || data.timestamp || ""),
    compact(record.status || data.status || ""),
    eventBody(record) || ""
  ];
  const semantic = parts.join("|");
  if (parts.slice(1).some((part) => part && part !== "-")) return semantic;
  const explicitId = record.id || data.id;
  if (explicitId) return `id:${compact(explicitId)}`;
  return semantic;
}

function looseTimelineEventKey(value: unknown): string {
  return [eventName(value, "event"), eventStatus(value), eventBody(value) || ""].join("|");
}

export function buildTimeline(thread: TaskThread | null, runEvents: unknown[]): TimelineEvent[] {
  if (!thread) return [];
  const response = thread.response;
  const seen = new Set<string>();
  const seenLoose = new Set<string>();
  const events: TimelineEvent[] = [
    {
      id: `${thread.id}:input`,
      kind: "user",
      title: "用户指令",
      body: thread.prompt,
      status: "ready"
    }
  ];

  if (!response || response.status === "in_progress") {
    events.push({
      id: `${thread.id}:thinking`,
      kind: "assistant",
      title: "AIASK 正在处理",
      body: "正在等待模型输出和工具事件。",
      status: "in_progress"
    });
    return events;
  }

  events.push({
    id: `${thread.id}:answer`,
    kind: "assistant",
    title: "智能体回复",
    body: response.output_text || response.status,
    status: response.status
  });

  (response.metadata?.tool_calls || []).forEach((tool, index) => {
    events.push({
      id: `${thread.id}:tool:${tool.id || index}`,
      kind: "tool",
      title: tool.name || "Tool call",
      subtitle: tool.id,
      payload: tool,
      status: "ready"
    });
  });

  (response.metadata?.audit_events || []).forEach((audit, index) => {
    const name = eventName(audit, "审计事件");
    seen.add(timelineEventKey(audit));
    seenLoose.add(looseTimelineEventKey(audit));
    events.push({
      id: `${thread.id}:audit:${index}`,
      kind: isApprovalEvent(audit) ? "approval" : "event",
      title: name,
      subtitle: eventTimestamp(audit),
      body: eventBody(audit),
      payload: audit,
      status: eventStatus(audit)
    });
  });

  runEvents.forEach((event, index) => {
    const key = timelineEventKey(event);
    const looseKey = looseTimelineEventKey(event);
    if (seen.has(key) || seenLoose.has(looseKey)) return;
    seen.add(key);
    seenLoose.add(looseKey);
    events.push({
      id: `${thread.id}:run:${index}`,
      kind: isApprovalEvent(event) ? "approval" : "event",
      title: eventName(event, "运行事件"),
      subtitle: eventTimestamp(event),
      body: eventBody(event),
      payload: event,
      status: eventStatus(event)
    });
  });

  return events;
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return (
      <div className="empty-thread">
        <Bot size={28} />
        <strong>开始一个任务</strong>
        <span>在下方输入指令后，AIASK 会在这里展示回复、工具调用、审批和运行事件。</span>
      </div>
    );
  }

  return (
    <div className="timeline">
      {events.map((event) => (
        <article className={`timeline-card ${event.kind}`} key={event.id}>
          <div className="timeline-marker" />
          <div className="timeline-card-head">
            <div>
              <span>{event.kind}</span>
              <h3>{event.title}</h3>
              {event.subtitle && <p>{event.subtitle}</p>}
            </div>
            <StatusBadge status={event.status} />
          </div>
          {event.body && <p className="timeline-body">{event.body}</p>}
          {event.payload !== undefined && (
            <details className="raw-details">
              <summary>
                原始数据
                <ChevronDown size={14} />
              </summary>
              <JsonPanel value={event.payload} />
            </details>
          )}
        </article>
      ))}
    </div>
  );
}
