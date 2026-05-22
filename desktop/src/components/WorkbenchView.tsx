import type { FormEvent, KeyboardEvent } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  FlaskConical,
  GitPullRequest,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Square,
  TerminalSquare
} from "lucide-react";
import { Timeline } from "./Timeline";
import { StatusBadge } from "./shared";
import type { HealthDetailed, TimelineEvent, TaskThread, ToolCatalogItem } from "../types";

const WORKFLOW_STAGES = [
  {
    id: "evidence",
    label: "Evidence",
    detail: "Data, semantic search, and source packages",
    icon: Search,
    tools: ["agent_quant_data_gate", "agent_memory_search", "agent_web_search"]
  },
  {
    id: "research",
    label: "Research",
    detail: "Factor checks and candidate strategy work",
    icon: BarChart3,
    tools: ["agent_factor_validation", "agent_quant_research_run", "agent_backtest_suite"]
  },
  {
    id: "incubation",
    label: "Incubation",
    detail: "Lifecycle status, hit-rate reports, and promotion signals",
    icon: FlaskConical,
    tools: ["agent_factory_status", "agent_incubation_factory_status", "agent_strategy_domain_events"]
  },
  {
    id: "risk",
    label: "Risk",
    detail: "Portfolio risk, governance, and confirmation intents",
    icon: ShieldCheck,
    tools: ["agent_portfolio_risk", "agent_governance_check", "agent_action_intent_create"]
  }
] as const;

function toolSet(tools: ToolCatalogItem[]): Set<string> {
  return new Set(tools.map((tool) => tool.name));
}

function stageStatus(stageTools: readonly string[], registered: Set<string>, online: boolean): string {
  if (!online) return "not_loaded";
  const available = stageTools.filter((tool) => registered.has(tool)).length;
  if (available === stageTools.length) return "implemented";
  if (available > 0) return "partial";
  return "not_loaded";
}

function countEvents(events: TimelineEvent[], kind: TimelineEvent["kind"]): number {
  return events.filter((event) => event.kind === kind).length;
}

function toolSideEffectLabel(tool: ToolCatalogItem): string {
  const sideEffect = tool.side_effect;
  if (typeof sideEffect === "string") return sideEffect;
  if (sideEffect && typeof sideEffect === "object" && "level" in sideEffect && typeof sideEffect.level === "string") {
    return sideEffect.level;
  }
  return "unknown";
}

function ActionOverview({ events, tools }: { events: TimelineEvent[]; tools: ToolCatalogItem[] }) {
  const toolEvents = countEvents(events, "tool");
  const approvals = countEvents(events, "approval");
  const auditEvents = countEvents(events, "event");
  const hasConfirmTool = tools.some((tool) => tool.name === "agent_action_intent_create");

  return (
    <section className="workflow-panel">
      <div className="section-header">
        <div>
          <span>Action record</span>
          <h3>Agent activity</h3>
        </div>
        <StatusBadge status={events.length ? "implemented" : "not_loaded"} label={events.length ? "tracked" : "idle"} />
      </div>
      <div className="diagnostics-summary wide">
        <div className="metric-card">
          <span>Tool calls</span>
          <strong>{toolEvents}</strong>
          <small>Visible in the timeline with raw envelopes.</small>
        </div>
        <div className={`metric-card ${approvals > 0 ? "warn" : "neutral"}`}>
          <span>Confirmations</span>
          <strong>{approvals}</strong>
          <small>{hasConfirmTool ? "Durable intent guard is registered." : "Intent guard not loaded."}</small>
        </div>
        <div className="metric-card">
          <span>Events</span>
          <strong>{auditEvents}</strong>
          <small>Run and strategy events are deduplicated.</small>
        </div>
        <div className="metric-card ok">
          <span>Trading mode</span>
          <strong>Preview first</strong>
          <small>Live execution must go through confirmation.</small>
        </div>
      </div>
    </section>
  );
}

function WorkflowOverview({ health, tools }: { health: HealthDetailed | null; tools: ToolCatalogItem[] }) {
  const registered = toolSet(tools);
  const online = health?.status === "ok" || health?.status === "healthy" || registered.size > 0;

  return (
    <section className="workflow-panel">
      <div className="section-header">
        <div>
          <span>User journey</span>
          <h3>Research to incubation loop</h3>
        </div>
        <StatusBadge status={online ? "implemented" : "not_loaded"} label={online ? "ready" : "offline"} />
      </div>
      <div className="workflow-grid">
        {WORKFLOW_STAGES.map((stage) => {
          const Icon = stage.icon;
          const status = stageStatus(stage.tools, registered, online);
          return (
            <article className={`workflow-card ${status}`} key={stage.id}>
              <div className="workflow-card-head">
                <Icon size={16} />
                <StatusBadge status={status} />
              </div>
              <strong>{stage.label}</strong>
              <span>{stage.detail}</span>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function SystemHealthStrip({ health, tools }: { health: HealthDetailed | null; tools: ToolCatalogItem[] }) {
  const toolNames = toolSet(tools);
  const factoryReady = toolNames.has("agent_factory_status");
  const incubationReady = toolNames.has("agent_incubation_factory_status");
  const dataReady = toolNames.has("agent_quant_data_gate") || toolNames.has("agent_data_validation");

  return (
    <section className="workflow-panel">
      <div className="section-header">
        <div>
          <span>System health</span>
          <h3>Operational signals</h3>
        </div>
        <Activity size={18} />
      </div>
      <div className="health-signal-grid">
        <div>
          <Database size={15} />
          <span>Agent</span>
          <StatusBadge status={health?.status || "not_loaded"} />
        </div>
        <div>
          <Database size={15} />
          <span>Tools</span>
          <strong>{tools.length}</strong>
        </div>
        <div>
          <FlaskConical size={15} />
          <span>Factory</span>
          <StatusBadge status={factoryReady ? "implemented" : "not_loaded"} label={factoryReady ? "ready" : "missing"} />
        </div>
        <div>
          <Activity size={15} />
          <span>Incubation</span>
          <StatusBadge status={incubationReady ? "implemented" : "not_loaded"} label={incubationReady ? "ready" : "missing"} />
        </div>
        <div>
          <Search size={15} />
          <span>Evidence</span>
          <StatusBadge status={dataReady ? "implemented" : "not_loaded"} label={dataReady ? "ready" : "missing"} />
        </div>
      </div>
    </section>
  );
}

function ReviewQueue({ events, tools }: { events: TimelineEvent[]; tools: ToolCatalogItem[] }) {
  const toolEvents = countEvents(events, "tool");
  const approvals = countEvents(events, "approval");
  const auditEvents = countEvents(events, "event");
  const readyTools = tools.filter((tool) => toolSideEffectLabel(tool) === "read_only").length;
  const reviewItems = [
    {
      label: "Agent summary",
      count: events.length,
      status: events.length ? "reviewing" : "ready",
      detail: events.length ? "Recent run activity is ready for inspection." : "Start a thread to create a reviewable task trace.",
      icon: Bot
    },
    {
      label: "Approvals",
      count: approvals,
      status: approvals ? "queued" : "ready",
      detail: approvals ? `${approvals} confirmation events waiting in the timeline.` : "No confirmation intents are pending.",
      icon: GitPullRequest
    },
    {
      label: "Tools and events",
      count: toolEvents || readyTools,
      status: toolEvents || auditEvents ? "reviewing" : "ready",
      detail: toolEvents ? `${toolEvents} tool calls recorded.` : `${readyTools} read-only actions available.`,
      icon: TerminalSquare
    }
  ];

  return (
    <section className="review-queue-panel">
      <div className="section-header">
        <div>
          <span>Review queue</span>
          <h3>Current thread state</h3>
        </div>
        <StatusBadge status={events.length ? "reviewing" : "ready"} label={events.length ? "reviewing" : "ready"} />
      </div>
      <div className="review-queue-list">
        {reviewItems.map((item) => {
          const Icon = item.icon;
          return (
            <article className="review-item" key={item.label}>
              <div className="review-item-icon">
                <Icon size={15} />
              </div>
              <div>
                <div className="review-item-head">
                  <strong>{item.label}</strong>
                  <StatusBadge status={item.status} label={String(item.count)} />
                </div>
                <span>{item.detail}</span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function WorkbenchView({
  agentMode,
  busy,
  controlToken,
  endpoint,
  health,
  onAgentModeChange,
  onComposerKeyDown,
  onPromptChange,
  onRefresh,
  onSessionIdChange,
  onSubmit,
  prompt,
  profileName,
  selectedThread,
  sessionId,
  status,
  timelineEvents,
  tools,
  userId
}: {
  agentMode: "finance_safe" | "hermes_full";
  busy: boolean;
  controlToken: string;
  endpoint: string;
  health: HealthDetailed | null;
  onAgentModeChange: (mode: "finance_safe" | "hermes_full") => void;
  onComposerKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onPromptChange: (value: string) => void;
  onRefresh: () => void;
  onSessionIdChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  prompt: string;
  profileName?: string;
  selectedThread: TaskThread | null;
  sessionId: string;
  status: string;
  timelineEvents: TimelineEvent[];
  tools: ToolCatalogItem[];
  userId?: string;
}) {
  return (
    <>
      <header className="workbench-header">
        <div>
          <span className="endpoint-chip">{endpoint}</span>
          <h1>{selectedThread?.title || "What should AIASK work on?"}</h1>
          <p className="header-subtitle">{profileName || "Local Operator"} / {userId || "local"}</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={status} label={status === "AIASK_ONLINE" ? "online" : status} />
          <button
            aria-label={status === "AIASK_DISCONNECTED" ? "Connect to Agent" : "Sync Agent state"}
            className="small-button"
            disabled={busy}
            onClick={onRefresh}
            title={status === "AIASK_DISCONNECTED" ? "Connect to Agent" : "Sync Agent state"}
            type="button"
          >
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            {status === "AIASK_DISCONNECTED" ? "Connect" : "Sync"}
          </button>
        </div>
      </header>

      <section className="thread-surface">
        <div className="thread-command-center">
          <ReviewQueue events={timelineEvents} tools={tools} />
          <div className="workflow-dashboard">
            <WorkflowOverview health={health} tools={tools} />
            <ActionOverview events={timelineEvents} tools={tools} />
            <SystemHealthStrip health={health} tools={tools} />
          </div>
        </div>
        <Timeline events={timelineEvents} />
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <div className="composer-toolbar">
          <div aria-label="Agent mode" className="segmented" role="group">
            <button
              aria-pressed={agentMode === "finance_safe"}
              className={agentMode === "finance_safe" ? "active" : ""}
              onClick={() => onAgentModeChange("finance_safe")}
              title="Finance safe mode"
              type="button"
            >
              <CheckCircle2 size={13} />
              Finance safe
            </button>
            <button
              aria-pressed={agentMode === "hermes_full"}
              className={agentMode === "hermes_full" ? "active" : ""}
              disabled={!controlToken.trim()}
              onClick={() => onAgentModeChange("hermes_full")}
              title={controlToken.trim() ? "Hermes full mode" : "Hermes full mode requires a control token"}
              type="button"
            >
              <ShieldCheck size={13} />
              Hermes full
            </button>
          </div>
          <label className="session-field">
            <span>Session</span>
            <input value={sessionId} onChange={(event) => onSessionIdChange(event.target.value)} placeholder="new session" />
          </label>
          {busy && (
            <button aria-label="Run in progress" className="ghost-button" disabled title="Run in progress" type="button">
              <Square size={13} />
              Running
            </button>
          )}
        </div>
        {agentMode === "hermes_full" && !controlToken.trim() && (
          <div className="notice warn compact-notice">
            <ShieldCheck size={14} />
            Hermes full mode needs a control token in Settings.
          </div>
        )}
        <div className="composer-input-row">
          <textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="Ask AIASK to research, code, inspect tools, or continue a session..."
          />
          <button className="send-button" disabled={busy || !prompt.trim()} title="Run thread task" type="submit">
            <Send size={16} />
            Run
          </button>
        </div>
      </form>
    </>
  );
}
