import type { FormEvent, KeyboardEvent } from "react";
import {
  CheckCircle2,
  Clock3,
  RefreshCw,
  Send,
  ShieldCheck,
  Square,
  Wrench,
  Zap,
} from "lucide-react";
import { Timeline } from "./Timeline";
import { StatusBadge } from "./shared";
import { SlotRenderer } from "../extensions/extensionRegistry";
import type {
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HealthDetailed,
  MainView,
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
    apiToken: hasApiToken ? "已填写" : "未填写",
    controlToken: hasControlToken ? "已填写" : "未填写",
  };
}

function runLabel(run: DesktopRunSummary): string {
  return `${run.status} / 工具 ${run.tool_call_count ?? 0} / 审批 ${run.approval_count ?? 0}`;
}

export function WorkbenchView({
  agentMode,
  apiToken,
  busy,
  controlToken,
  endpoint,
  health,
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

  return (
    <>
      <header className="workbench-header">
        <div>
          <span className="endpoint-chip">{endpoint}</span>
          <h1>{selectedThread?.title || "AIASK Workbench"}</h1>
          <p className="header-subtitle">
            {(profileName || "本地操作者") + " / " + (userId || "local")}
          </p>
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
          <StatusBadge status={status} label={status === "AIASK_ONLINE" ? "在线" : status} />
          <button
            aria-label={status === "AIASK_DISCONNECTED" ? "连接 AIASK" : "同步 AIASK 状态"}
            className="small-button"
            disabled={busy}
            onClick={onRefresh}
            type="button"
          >
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            {status === "AIASK_DISCONNECTED" ? "连接" : "同步"}
          </button>
        </div>
      </header>

      <section className="thread-surface">
        <div className="thread-command-center">
          <section className="workflow-panel">
            <div className="section-header">
              <div>
                <span>Workbench</span>
                <h3>session-first 主路径</h3>
              </div>
              <StatusBadge status={access.fullModeReady ? "implemented" : "partial"} label={agentMode} />
            </div>

            <div className="diagnostics-summary wide">
              <div className="metric-card">
                <span>当前模式</span>
                <strong>{agentMode}</strong>
                <small>默认工具集继续保持 finance_safe。</small>
              </div>
              <div className="metric-card">
                <span>API Token</span>
                <strong>{access.apiToken}</strong>
                <small>Workbench 主路径只依赖 API token 安全接口。</small>
              </div>
              <div className="metric-card">
                <span>Control Token</span>
                <strong>{access.controlToken}</strong>
                <small>Sessions 和 full mode 运维页需要它。</small>
              </div>
              <div className="metric-card">
                <span>Full Mode</span>
                <strong>{access.fullModeReady ? "可用" : "未激活"}</strong>
                <small>决定是否可以进入 Sessions 与完整管理页。</small>
              </div>
            </div>

            <div className="workbench-summary-grid">
              <article className="summary-card">
                <strong>最近会话</strong>
                <div className="summary-list">
                  {(summary?.recent_sessions || []).slice(0, 5).map((session) => (
                    <button
                      key={session.session_id}
                      onClick={() => (onOpenSession ? onOpenSession(session.session_id) : onOpenView("sessions"))}
                      type="button"
                    >
                      <span>{session.title || session.session_id}</span>
                      <small>{session.last_message_at || "-"}</small>
                    </button>
                  ))}
                  {!summary?.recent_sessions?.length && <p className="muted">暂无最近会话摘要。</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>最近运行</strong>
                <div className="summary-list">
                  {recentRuns.slice(0, 5).map((run) => (
                    <button key={run.run_id} onClick={() => onOpenView("runs-events")} type="button">
                      <span>{run.run_id}</span>
                      <small>{runLabel(run)}</small>
                    </button>
                  ))}
                  {!recentRuns.length && <p className="muted">暂无最近运行摘要。</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>待处理队列</strong>
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

            <div className="quick-link-row">
              <button className="small-button" onClick={() => onOpenView("readiness-health")} type="button">
                <Zap size={13} />
                Readiness
              </button>
              <button className="small-button" onClick={() => onOpenView("tools-intents-approvals")} type="button">
                <Wrench size={13} />
                Tools / Intents / Approvals
              </button>
              <button className="small-button" onClick={() => onOpenView("mcp-connectors")} type="button">
                <ShieldCheck size={13} />
                MCP / Connectors
              </button>
              <button className="small-button" onClick={() => onOpenView("gateway")} type="button">
                <Clock3 size={13} />
                Gateway
              </button>
              <SlotRenderer
                controlToken={controlToken}
                fullModeActive={access.fullModeReady}
                onOpenView={onOpenView}
                slot="workbench.quick-actions"
              />
            </div>
          </section>

          <Timeline events={timelineEvents} />
        </div>
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <div className="composer-toolbar">
          <div aria-label="智能体模式" className="segmented" role="group">
            <button
              aria-pressed={agentMode === "finance_safe"}
              className={agentMode === "finance_safe" ? "active" : ""}
              onClick={() => onAgentModeChange("finance_safe")}
              type="button"
            >
              <CheckCircle2 size={13} />
              金融安全
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
            <span>会话</span>
            <input
              value={sessionId}
              onChange={(event) => onSessionIdChange(event.target.value)}
              placeholder="新会话"
            />
          </label>

          {busy && (
            <button aria-label="任务运行中" className="ghost-button" disabled title="任务运行中" type="button">
              <Square size={13} />
              运行中
            </button>
          )}

          <span className="muted">{tools.length} 个工具可用</span>
        </div>

        {agentMode === "hermes_full" && !controlToken.trim() && (
          <div className="notice warn compact-notice">
            <ShieldCheck size={14} />
            Hermes full 模式需要先在 Settings / Mode 中填写 control token。
          </div>
        )}

        <div className="composer-input-row">
          <textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="让 AIASK 做研究、写代码、检查工具，或继续一个会话..."
          />
          <button className="send-button" disabled={busy || !prompt.trim()} title="运行线程任务" type="submit">
            <Send size={16} />
            运行
          </button>
        </div>
      </form>
    </>
  );
}
