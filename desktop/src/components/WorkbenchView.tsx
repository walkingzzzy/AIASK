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
import { StatusBadge, statusLabel } from "./shared";
import { ArtifactsPanel, ReviewPanel, SourcesPanel, buildTaskArtifacts, buildTaskReviewComments } from "./TaskPanels";
import { SlotRenderer } from "../extensions/extensionRegistry";
import type {
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HealthDetailed,
  MainView,
  RecentSessionSummary,
  AgentArtifactRecord,
  AgentSourceRecord,
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
    apiToken: hasApiToken ? "已填写" : "未填写",
    controlToken: hasControlToken ? "已填写" : "未填写",
  };
}

function modeDisplay(mode: "finance_safe" | "hermes_full") {
  return mode === "hermes_full"
    ? { label: "完整模式", detail: "可使用通用工具；高风险动作仍需审批。" }
    : { label: "金融安全模式", detail: "默认只做研究、查询和受控审批。" };
}

function backendDisplay(mockMode?: boolean) {
  return mockMode
    ? { label: "演示数据", detail: "当前使用本地 Mock 数据，不会影响真实账户或外部平台。" }
    : { label: "真实后端", detail: "当前连接本地 Agent 服务，所有受控动作仍走审批和令牌校验。" };
}

function connectionDisplay(status: string, health: HealthDetailed | null) {
  const online = status === "AIASK_ONLINE" || health?.status === "online";
  if (online) return { label: "在线，可以开始任务", detail: "Agent 已响应，工作台可以同步会话、运行和工具状态。", tone: "ready" };
  if (status === "AIASK_DISCONNECTED") return { label: "尚未连接", detail: "点击同步或检查 Agent 端点后再开始任务。", tone: "gated" };
  return { label: statusLabel(status), detail: "请先打开准备度 / 健康页查看连接或权限原因。", tone: status };
}

function shortId(value?: string) {
  if (!value) return "-";
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

function looksLikeTechnicalId(value?: string) {
  return Boolean(value && /^[a-f0-9_-]{18,}$/i.test(value.trim()));
}

function readableTime(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function runSummary(run: DesktopRunSummary) {
  const errorCount = run.error_count ?? 0;
  const approvalCount = run.approval_count ?? 0;
  const toolCount = run.tool_call_count ?? 0;
  const detail = [`工具 ${toolCount} 次`, `审批 ${approvalCount} 项`, `错误 ${errorCount} 个`].join(" · ");
  return {
    title: `运行${statusLabel(run.status)}`,
    detail,
    technical: shortId(run.run_id),
  };
}

function sessionSummary(session: RecentSessionSummary) {
  const status = session.has_pending_approval ? "有待审批" : session.has_errors ? "有错误需查看" : statusLabel(session.status || "completed");
  const lastSeen = session.last_message_at || session.updated_at || session.created_at || "-";
  const title = session.title && !looksLikeTechnicalId(session.title) ? session.title : `${status}会话`;
  return {
    title,
    detail: `${status} · ${readableTime(lastSeen)}`,
    technical: shortId(session.session_id),
  };
}

function queueSummary(queue: DesktopWorkbenchSummary["queues"]) {
  const total = queue.pending_intents + queue.pending_approvals + queue.gateway_failed + queue.mcp_degraded;
  if (!total) return "暂无待处理事项";
  const parts = [
    queue.pending_intents ? `${queue.pending_intents} 个待确认意图` : "",
    queue.pending_approvals ? `${queue.pending_approvals} 个审批` : "",
    queue.gateway_failed ? `${queue.gateway_failed} 个消息失败` : "",
    queue.mcp_degraded ? `${queue.mcp_degraded} 个 MCP 降级` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function toolDirectory(tools: ToolCatalogItem[], health: HealthDetailed | null) {
  return new Set([...tools.map((tool) => tool.name), ...(health?.tools?.names || [])]);
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
  selectedRunArtifacts,
  selectedRunSources,
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
  selectedRunArtifacts?: AgentArtifactRecord[];
  selectedRunSources?: AgentSourceRecord[];
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
    timelineEvents,
    durableArtifacts: selectedRunArtifacts,
    durableSources: selectedRunSources,
    endpoint
  });
  const reviewComments = buildTaskReviewComments(artifacts);
  const mode = modeDisplay(agentMode);
  const backend = backendDisplay(mockMode);
  const connection = connectionDisplay(status, health);
  const currentRun = recentRuns[0];
  const currentRunSummary = currentRun ? runSummary(currentRun) : null;
  const taskContext: TaskContextSummary = {
    projectLabel: profileName || "本地工作区",
    threadLabel: selectedThread?.title || sessionId || "新线程",
    runLabel: selectedThread?.runId || currentRun?.run_id || "-",
    mode: agentMode as TaskContextSummary["mode"],
    backendMode: (mockMode ? "mock" : "live") as TaskContextSummary["backendMode"],
    endpoint,
    healthStatus: status,
    pendingApprovals: queue.pending_approvals,
    pendingIntents: queue.pending_intents,
    artifactCount: artifacts.length + (selectedRunSources?.length || 0),
  };
  const knownTools = toolDirectory(tools, health);
  const hasTool = (name: string) => knownTools.has(name);
  const safePathSteps: Array<{
    key: string;
    label: string;
    status: string;
    detail: string;
    target: MainView;
    action: string;
  }> = [
    {
      key: "mode",
      label: "1. 模式 / 模型",
      status: status === "AIASK_ONLINE" || health?.status === "online" ? "ready" : "partial",
      detail: `${mode.label}；当前模型 ${health?.runtime?.model || "待加载"}。${mode.detail}`,
      target: "readiness-health",
      action: "打开准备度",
    },
    {
      key: "mcp",
      label: "2. MCP / 连接器",
      status: queue.mcp_degraded ? "partial" : status === "AIASK_ONLINE" ? "ready" : "partial",
      detail: queue.mcp_degraded ? `${queue.mcp_degraded} 个 MCP 降级，先复核聚合状态。` : "复核服务器、资源、提示词和 OAuth 状态。",
      target: "mcp-connectors",
      action: "打开 MCP",
    },
    {
      key: "memory",
      label: "3. 记忆 / 搜索",
      status: hasTool("agent_memory_search") && hasTool("agent_session_search") ? "ready" : "partial",
      detail: hasTool("agent_memory_search") && hasTool("agent_session_search") ? "会话搜索和金融记忆搜索已在工具目录。" : "等待工具目录刷新或后端暴露记忆搜索。",
      target: "user",
      action: "打开本地用户",
    },
    {
      key: "financial-manager",
      label: "4. 金融经理台",
      status: hasTool("agent_portfolio_risk") ? "ready" : "partial",
      detail: hasTool("agent_portfolio_risk") ? "组合风险、只读查询和安全 workflow 可复核。" : "等待金融只读工具进入 Agent 工具目录。",
      target: "financial-manager",
      action: "打开金融经理台",
    },
    {
      key: "data",
      label: "5. 数据 / 量化门禁",
      status: hasTool("agent_quant_data_gate") ? "ready" : "partial",
      detail: hasTool("agent_quant_data_gate") ? "量化数据门禁工具可用于只读预检。" : "先检查数据同步、SQLite 和工具目录。",
      target: "data",
      action: "打开数据",
    },
    {
      key: "factory",
      label: "6. 工厂接力",
      status: hasTool("agent_factory_status") ? "ready" : "partial",
      detail: hasTool("agent_factory_status") ? "策略、因子和孵化入口可从金融实验室接力。" : "等待工厂状态工具或运行快照加载。",
      target: "finance-lab",
      action: "打开金融实验室",
    },
  ];

  return (
    <>
      <header className="workbench-header task-object-header">
        <div>
          <span className="endpoint-chip">{connection.label}</span>
          <h1>{selectedThread?.title || "AIASK 工作台"}</h1>
          <p className="header-subtitle">
            {(profileName || "本地操作员") + " / " + (userId || "local") + " · " + backend.label + " · " + endpoint}
          </p>
          <div className="task-context-strip" aria-label="任务上下文">
            <StatusBadge status={mockMode ? "mock" : "live"} label={backend.label} />
            <StatusBadge status={connection.tone} label={connection.label} />
            <span><GitBranch size={13} /> {taskContext.threadLabel}</span>
            <span><Zap size={13} /> {mode.label}</span>
            <span><FileSearch size={13} /> {taskContext.artifactCount} 个产物</span>
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
        <div className="thread-command-center optimized">
          <section className="workflow-panel">
            <div className="section-header">
              <div>
                <span>任务中枢</span>
                <h3>线程优先工作台</h3>
              </div>
              <StatusBadge status={access.fullModeReady ? "ready" : "partial"} label={mode.label} />
            </div>

            <div className="task-object-grid">
              <div className="metric-card">
                <span>连接状态</span>
                <strong>{connection.label}</strong>
                <small>{connection.detail}</small>
              </div>
              <div className="metric-card">
                <span>当前任务</span>
                <strong>{selectedThread?.title || currentRunSummary?.title || "等待新任务"}</strong>
                <small>{selectedThread?.runId ? `运行编号 ${shortId(selectedThread.runId)}` : currentRunSummary ? currentRunSummary.detail : "输入需求后，AIASK 会在这里显示进度和结果。"}</small>
              </div>
              <div className="metric-card">
                <span>待处理事项</span>
                <strong>{queue.pending_intents + queue.pending_approvals + queue.gateway_failed + queue.mcp_degraded} 项</strong>
                <small>{queueSummary(queue)}</small>
              </div>
              <div className="metric-card">
                <span>可用范围</span>
                <strong>{mode.label}</strong>
                <small>{mode.detail} API 令牌{access.apiToken}；控制令牌{access.controlToken}。</small>
              </div>
            </div>

            <div className="workbench-summary-grid">
              <article className="summary-card">
                <strong>最近会话</strong>
                <div className="summary-list">
                  {(summary?.recent_sessions || []).slice(0, 4).map((session) => (
                    <button
                      aria-label={`打开会话：${sessionSummary(session).title} ${sessionSummary(session).detail}`}
                      className="summary-action-button"
                      key={session.session_id}
                      onClick={() => (onOpenSession ? onOpenSession(session.session_id) : onOpenView("runs-events"))}
                      type="button"
                    >
                      {(() => {
                        const item = sessionSummary(session);
                        return (
                          <>
                            <span>{item.title}</span>
                            <small>{item.detail}</small>
                            <em>{item.technical}</em>
                          </>
                        );
                      })()}
                    </button>
                  ))}
                  {!summary?.recent_sessions?.length && <p className="muted">暂无最近会话。</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>最近运行</strong>
                <div className="summary-list">
                  {recentRuns.slice(0, 4).map((run) => (
                    <button
                      aria-label={`查看运行：${runSummary(run).title} ${runSummary(run).detail}`}
                      className="summary-action-button"
                      key={run.run_id}
                      onClick={() => onOpenView("runs-events")}
                      type="button"
                    >
                      {(() => {
                        const item = runSummary(run);
                        return (
                          <>
                            <span>{item.title}</span>
                            <small>{item.detail}</small>
                            <em>{item.technical}</em>
                          </>
                        );
                      })()}
                    </button>
                  ))}
                  {!recentRuns.length && <p className="muted">暂无最近运行。</p>}
                </div>
              </article>

              <article className="summary-card">
                <strong>操作队列</strong>
                <p className="summary-card-copy">{queueSummary(queue)}</p>
                <div className="summary-kv">
                  <span>意图</span>
                  <strong>{queue.pending_intents}</strong>
                  <span>审批</span>
                  <strong>{queue.pending_approvals}</strong>
                  <span>Gateway</span>
                  <strong>{queue.gateway_failed}</strong>
                  <span>MCP</span>
                  <strong>{queue.mcp_degraded}</strong>
                </div>
              </article>
            </div>

            <section className="workbench-safe-path" aria-label="金融 Agent 安全链路">
              <div className="section-header">
                <div>
                  <span>金融 Agent 安全链路</span>
                  <h3>现在可以复核什么</h3>
                </div>
                <StatusBadge status="read_only" label="只读导航" />
              </div>
              <div className="safe-path-grid">
                {safePathSteps.map((step) => (
                  <article className={`safe-path-step ${step.status}`} key={step.key}>
                    <div>
                      <strong>{step.label}</strong>
                      <StatusBadge status={step.status} />
                    </div>
                    <p>{step.detail}</p>
                    <button className="small-button" onClick={() => onOpenView(step.target)} type="button">
                      <FileSearch size={13} />
                      {step.action}
                    </button>
                  </article>
                ))}
              </div>
              <p className="muted compact-copy">
                这里的入口只做只读导航；状态型、外部平台和交易风险动作仍需要 ActionIntent、控制令牌和后端护栏。
              </p>
            </section>

            <div className="quick-link-row context-actions">
              <button className="small-button" onClick={() => onOpenView("projects-contexts")} type="button">
                <Database size={13} />
                项目 / 上下文
              </button>
              <button className="small-button" onClick={() => onOpenView("tools-intents-approvals")} type="button">
                <ShieldCheck size={13} />
                审批
              </button>
              <button className="small-button" onClick={() => onOpenView("finance-lab")} type="button">
                <Wrench size={13} />
                金融实验室
              </button>
              <button className="small-button" onClick={() => onOpenView("integrations")} type="button">
                <Clock3 size={13} />
                集成
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
            <SourcesPanel sources={selectedRunSources} compact endpoint={endpoint} apiToken={controlToken.trim() || apiToken} />
            <ArtifactsPanel artifacts={artifacts} compact apiToken={controlToken.trim() || apiToken} />
            <ReviewPanel comments={reviewComments} compact />
          </div>
        </div>
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <div className="composer-toolbar">
          <div aria-label="Agent 模式" className="segmented" role="group">
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
              aria-label="会话 ID"
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
            Hermes full 需要先在 Settings 中填写控制令牌。
          </div>
        )}

        <div className="composer-input-row">
          <textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="让 AIASK 研究、检查工具、生成报告，或继续当前线程..."
          />
          <button aria-label="运行线程任务" className="send-button" disabled={busy || !prompt.trim()} title="运行线程任务" type="submit">
            <Send size={16} />
            运行
          </button>
        </div>
      </form>
    </>
  );
}
