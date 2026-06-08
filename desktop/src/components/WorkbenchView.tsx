import type { FormEvent, KeyboardEvent } from "react";
import {
  CheckCircle2,
  Clock3,
  Database,
  FileSearch,
  GitBranch,
  RefreshCw,
  Send,
  ShieldCheck,
  Square,
  Wrench,
  Zap,
} from "lucide-react";
import { Timeline } from "./Timeline";
import { StatusBadge } from "./shared";
import { ArtifactsPanel, ReviewPanel, buildTaskArtifacts, buildTaskReviewComments } from "./TaskPanels";
import { SlotRenderer } from "../extensions/extensionRegistry";
import type {
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HealthDetailed,
  MainView,
  TaskContextSummary,
  TaskThread,
  TimelineEvent,
  ToolCatalogItem,
} from "../types";

function accessLabel(
  health: HealthDetailed | null,
  hasApiToken: boolean,
  hasControlToken: boolean,
  summary: DesktopWorkbenchSummary | null
) {
  const fullModeReady = Boolean(summary?.access.full_mode_active || health?.hermes?.full_mode_active);
  return {
    fullModeReady,
    apiToken: hasApiToken ? "configured" : "missing",
    controlToken: hasControlToken ? "configured" : "missing",
  };
}

function runLabel(run: DesktopRunSummary): string {
  return `${run.status} / tools ${run.tool_call_count ?? 0} / approvals ${run.approval_count ?? 0}`;
}

export function WorkbenchView({
  agentMode,
  apiToken,
  busy,
  controlToken,
  endpoint,
  health,
  mockMode,
  onAgentModeChange,
  onComposerKeyDown,
  onOpenSession,
  onOpenView,
  onPromptChange,
  onRefresh,
  onSessionIdChange,
  onSubmit,
  prompt,
  profileName,
  recentRuns,
  selectedThread,
  sessionId,
  status,
  summary,
  timelineEvents,
  tools,
  userId,
}: {
  agentMode: "finance_safe" | "hermes_full";
  apiToken: string;
  busy: boolean;
  controlToken: string;
  endpoint: string;
  health: HealthDetailed | null;
  mockMode?: boolean;
  onAgentModeChange: (mode: "finance_safe" | "hermes_full") => void;
  onComposerKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onOpenSession?: (sessionId: string) => void;
  onOpenView: (view: MainView) => void;
  onPromptChange: (value: string) => void;
  onRefresh: () => void;
  onSessionIdChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  prompt: string;
  profileName?: string;
  recentRuns: DesktopRunSummary[];
  selectedThread: TaskThread | null;
  sessionId: string;
  status: string;
  summary: DesktopWorkbenchSummary | null;
  timelineEvents: TimelineEvent[];
  tools: ToolCatalogItem[];
  userId?: string;
}) {
  const access = accessLabel(health, !!apiToken.trim(), !!controlToken.trim(), summary);
  const queue = summary?.queues || {
    pending_intents: 0,
    pending_approvals: 0,
    gateway_failed: 0,
    mcp_degraded: 0,
  };
  const artifacts = buildTaskArtifacts({
    selectedThread,
    selectedResponse: selectedThread?.response,
    recentRuns,
    timelineEvents
  });
  const reviewComments = buildTaskReviewComments(artifacts);
  const taskContext: TaskContextSummary = {
    projectLabel: profileName || "Local workspace",
    threadLabel: selectedThread?.title || sessionId || "New thread",
    runLabel: selectedThread?.runId || recentRuns[0]?.run_id || "-",
    mode: agentMode,
    backendMode: mockMode ? "mock" : "live",
    endpoint,
    healthStatus: status,
    pendingApprovals: queue.pending_approvals,
    pendingIntents: queue.pending_intents,
    artifactCount: artifacts.length,
  };

  return (
    <>
      <header className="workbench-header task-object-header">
        <div>
          <span className="endpoint-chip">{endpoint}</span>
          <h1>{selectedThread?.title || "AIASK Workbench"}</h1>
          <p className="header-subtitle">
            {(profileName || "Local operator") + " / " + (userId || "local")}
          </p>
          <div className="task-context-strip" aria-label="Task context">
            <StatusBadge status={taskContext.backendMode} label={taskContext.backendMode} />
            <StatusBadge status={status === "AIASK_ONLINE" ? "ready" : status} label={status === "AIASK_ONLINE" ? "online" : status} />
            <span><GitBranch size={13} /> {taskContext.threadLabel}</span>
            <span><Zap size={13} /> {taskContext.mode}</span>
            <span><FileSearch size={13} /> {taskContext.artifactCount} artifacts</span>
          </div>
          <div className="extension-slot-row header-slot">
            <SlotRenderer
              controlToken={controlToken}
              fullModeActive={access.fullModeReady}
              onOpenView={onOpenView}
              slot="header-left"
            />
          </div>
        </div>
        <div className="header-actions">
          <SlotRenderer
            controlToken={controlToken}
            fullModeActive={access.fullModeReady}
            onOpenView={onOpenView}
            slot="header-right"
          />
          <button
            aria-label={status === "AIASK_DISCONNECTED" ? "Connect AIASK" : "Refresh AIASK status"}
            className="small-button"
            disabled={busy}
            onClick={onRefresh}
            type="button"
          >
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            {status === "AIASK_DISCONNECTED" ? "Connect" : "Sync"}
          </button>
        </div>
      </header>

      <section className="thread-surface">
        <div className="thread-command-center optimized">
          <section className="workflow-panel">
            <div className="section-header">
              <div>
                <span>Command center</span>
                <h3>Thread-first workspace</h3>
              </div>
              <StatusBadge status={access.fullModeReady ? "ready" : "partial"} label={agentMode} />
            </div>

            <div className="task-object-grid">
              <div className="metric-card">
                <span>Project / Context</span>
                <strong>{taskContext.projectLabel}</strong>
                <small>{taskContext.backendMode === "mock" ? "Mock data is active" : "Live backend mode"}</small>
              </div>
              <div className="metric-card">
                <span>Run</span>
                <strong>{taskContext.runLabel}</strong>
                <small>Current or latest run for this thread</small>
              </div>
              <div className="metric-card">
                <span>Pending work</span>
                <strong>{queue.pending_intents + queue.pending_approvals}</strong>
                <small>{queue.pending_intents} intents / {queue.pending_approvals} approvals</small>
              </div>
              <div className="metric-card">
                <span>Access</span>
                <strong>{access.fullModeReady ? "full ready" : "safe mode"}</strong>
                <small>API {access.apiToken}; control {access.controlToken}</small>
              </div>
            </div>

            <div className="workbench-summary-grid">
              <article className="summary-card">
                <strong>Recent sessions</strong>
                <div className="summary-list">
                  {(summary?.recent_sessions || []).slice(0, 4).map((session) => (
                    <button
                      key={session.session_id}
                      onClick={() => (onOpenSession ? onOpenSession(session.session_id) : onOpenView("runs-events"))}
                      type="button"
                    >
                      <span>{session.title || session.session_id}</span>
                      <small>{session.last_message_at || "-"}</small>
                    </button>
                  ))}
                  {!summary?.recent_sessions?.length && <p className="muted">No recent sessions yet.</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>Recent runs</strong>
                <div className="summary-list">
                  {recentRuns.slice(0, 4).map((run) => (
                    <button key={run.run_id} onClick={() => onOpenView("runs-events")} type="button">
                      <span>{run.run_id}</span>
                      <small>{runLabel(run)}</small>
                    </button>
                  ))}
                  {!recentRuns.length && <p className="muted">No recent runs yet.</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>Operational queue</strong>
                <div className="summary-kv">
                  <span>Intents</span>
                  <strong>{queue.pending_intents}</strong>
                  <span>Approvals</span>
                  <strong>{queue.pending_approvals}</strong>
                  <span>Gateway</span>
                  <strong>{queue.gateway_failed}</strong>
                  <span>MCP</span>
                  <strong>{queue.mcp_degraded}</strong>
                </div>
              </article>
            </div>

            <div className="quick-link-row context-actions">
              <button className="small-button" onClick={() => onOpenView("projects-contexts")} type="button">
                <Database size={13} />
                Projects / Contexts
              </button>
              <button className="small-button" onClick={() => onOpenView("tools-intents-approvals")} type="button">
                <ShieldCheck size={13} />
                Approvals
              </button>
              <button className="small-button" onClick={() => onOpenView("finance-lab")} type="button">
                <Wrench size={13} />
                Finance Lab
              </button>
              <button className="small-button" onClick={() => onOpenView("integrations")} type="button">
                <Clock3 size={13} />
                Integrations
              </button>
              <SlotRenderer
                controlToken={controlToken}
                fullModeActive={access.fullModeReady}
                onOpenView={onOpenView}
                slot="workbench.quick-actions"
              />
            </div>
          </section>

          <div className="task-evidence-column">
            <Timeline events={timelineEvents} />
            <ArtifactsPanel artifacts={artifacts} compact />
            <ReviewPanel comments={reviewComments} compact />
          </div>
        </div>
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <div className="composer-toolbar">
          <div aria-label="Agent mode" className="segmented" role="group">
            <button
              aria-pressed={agentMode === "finance_safe"}
              className={agentMode === "finance_safe" ? "active" : ""}
              onClick={() => onAgentModeChange("finance_safe")}
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
              type="button"
            >
              <ShieldCheck size={13} />
              Hermes full
            </button>
          </div>

          <label className="session-field">
            <span>Session</span>
            <input
              value={sessionId}
              onChange={(event) => onSessionIdChange(event.target.value)}
              placeholder="New session"
            />
          </label>

          {busy && (
            <button aria-label="Task running" className="ghost-button" disabled title="Task running" type="button">
              <Square size={13} />
              Running
            </button>
          )}

          <span className="muted">{tools.length} tools available</span>
        </div>

        {agentMode === "hermes_full" && !controlToken.trim() && (
          <div className="notice warn compact-notice">
            <ShieldCheck size={14} />
            Hermes full requires a Control token in Settings.
          </div>
        )}

        <div className="composer-input-row">
          <textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="Ask AIASK to research, inspect tools, produce a report, or continue the selected thread..."
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
