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
    label: "证据",
    detail: "数据、语义搜索和来源材料",
    icon: Search,
    tools: ["agent_quant_data_gate", "agent_memory_search", "agent_web_search"]
  },
  {
    id: "research",
    label: "研究",
    detail: "因子检查和候选策略研究",
    icon: BarChart3,
    tools: ["agent_factor_validation", "agent_quant_research_run", "agent_backtest_suite"]
  },
  {
    id: "incubation",
    label: "孵化",
    detail: "生命周期状态、命中率报告和晋升信号",
    icon: FlaskConical,
    tools: ["agent_factory_status", "agent_incubation_factory_status", "agent_strategy_domain_events"]
  },
  {
    id: "risk",
    label: "风险",
    detail: "组合风险、治理检查和确认意图",
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
          <span>动作记录</span>
          <h3>智能体活动</h3>
        </div>
        <StatusBadge status={events.length ? "implemented" : "not_loaded"} label={events.length ? "已记录" : "空闲"} />
      </div>
      <div className="diagnostics-summary wide">
        <div className="metric-card">
          <span>工具调用</span>
          <strong>{toolEvents}</strong>
          <small>会在时间线中展示，并保留原始 envelope。</small>
        </div>
        <div className={`metric-card ${approvals > 0 ? "warn" : "neutral"}`}>
          <span>确认事项</span>
          <strong>{approvals}</strong>
          <small>{hasConfirmTool ? "持久化意图保护已注册。" : "意图保护尚未加载。"}</small>
        </div>
        <div className="metric-card">
          <span>事件</span>
          <strong>{auditEvents}</strong>
          <small>运行和策略事件会自动去重。</small>
        </div>
        <div className="metric-card ok">
          <span>交易模式</span>
          <strong>先预览</strong>
          <small>真实执行必须经过确认。</small>
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
          <span>用户流程</span>
          <h3>从研究到孵化的闭环</h3>
        </div>
        <StatusBadge status={online ? "implemented" : "not_loaded"} label={online ? "就绪" : "离线"} />
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
          <span>系统健康</span>
          <h3>运行信号</h3>
        </div>
        <Activity size={18} />
      </div>
      <div className="health-signal-grid">
        <div>
          <Database size={15} />
          <span>智能体</span>
          <StatusBadge status={health?.status || "not_loaded"} />
        </div>
        <div>
          <Database size={15} />
          <span>工具</span>
          <strong>{tools.length}</strong>
        </div>
        <div>
          <FlaskConical size={15} />
          <span>工厂</span>
          <StatusBadge status={factoryReady ? "implemented" : "not_loaded"} label={factoryReady ? "就绪" : "缺失"} />
        </div>
        <div>
          <Activity size={15} />
          <span>孵化</span>
          <StatusBadge status={incubationReady ? "implemented" : "not_loaded"} label={incubationReady ? "就绪" : "缺失"} />
        </div>
        <div>
          <Search size={15} />
          <span>证据</span>
          <StatusBadge status={dataReady ? "implemented" : "not_loaded"} label={dataReady ? "就绪" : "缺失"} />
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
      label: "智能体摘要",
      count: events.length,
      status: events.length ? "reviewing" : "ready",
      detail: events.length ? "最近运行活动可供检查。" : "启动一个任务线程后会生成可复核的任务轨迹。",
      icon: Bot
    },
    {
      label: "审批",
      count: approvals,
      status: approvals ? "queued" : "ready",
      detail: approvals ? `${approvals} 个确认事件正在时间线中等待处理。` : "当前没有待处理的确认意图。",
      icon: GitPullRequest
    },
    {
      label: "工具与事件",
      count: toolEvents || readyTools,
      status: toolEvents || auditEvents ? "reviewing" : "ready",
      detail: toolEvents ? `已记录 ${toolEvents} 次工具调用。` : `${readyTools} 个只读操作可用。`,
      icon: TerminalSquare
    }
  ];

  return (
    <section className="review-queue-panel">
      <div className="section-header">
        <div>
          <span>复核队列</span>
          <h3>当前线程状态</h3>
        </div>
        <StatusBadge status={events.length ? "reviewing" : "ready"} label={events.length ? "复核中" : "就绪"} />
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
          <h1>{selectedThread?.title || "你想让 AIASK 做什么？"}</h1>
          <p className="header-subtitle">{profileName || "本地操作者"} / {userId || "local"}</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={status} label={status === "AIASK_ONLINE" ? "在线" : status} />
          <button
            aria-label={status === "AIASK_DISCONNECTED" ? "连接智能体" : "同步智能体状态"}
            className="small-button"
            disabled={busy}
            onClick={onRefresh}
            title={status === "AIASK_DISCONNECTED" ? "连接智能体" : "同步智能体状态"}
            type="button"
          >
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            {status === "AIASK_DISCONNECTED" ? "连接" : "同步"}
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
          <div aria-label="智能体模式" className="segmented" role="group">
            <button
              aria-pressed={agentMode === "finance_safe"}
              className={agentMode === "finance_safe" ? "active" : ""}
              onClick={() => onAgentModeChange("finance_safe")}
              title="金融安全模式"
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
              title={controlToken.trim() ? "Hermes full 模式" : "Hermes full 模式需要控制令牌"}
              type="button"
            >
              <ShieldCheck size={13} />
              Hermes full
            </button>
          </div>
          <label className="session-field">
            <span>会话</span>
            <input value={sessionId} onChange={(event) => onSessionIdChange(event.target.value)} placeholder="新会话" />
          </label>
          {busy && (
            <button aria-label="任务运行中" className="ghost-button" disabled title="任务运行中" type="button">
              <Square size={13} />
              运行中
            </button>
          )}
        </div>
        {agentMode === "hermes_full" && !controlToken.trim() && (
          <div className="notice warn compact-notice">
            <ShieldCheck size={14} />
            Hermes full 模式需要先在设置中填写控制令牌。
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
