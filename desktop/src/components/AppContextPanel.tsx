import { Activity, Bot, Database, GitBranch, Globe2, KeyRound, ServerCog, ShieldCheck, Wrench } from "lucide-react";
import { GatedState, StatusBadge, statusLabel } from "./shared";
import type { HealthDetailed, HermesStatus, TaskThread, ToolCatalogItem } from "../types";

function connectionSummary(status: string, health: HealthDetailed | null) {
  const online = status === "AIASK_ONLINE" || health?.status === "online";
  if (online) return { label: "在线，可以使用", detail: "Agent 已响应，当前页面可以读取会话、工具和运行状态。", tone: "ready" };
  if (status === "AIASK_DISCONNECTED") return { label: "尚未连接", detail: "请先同步 Agent 状态，或在设置里检查端点。", tone: "gated" };
  return { label: statusLabel(status), detail: "连接或权限状态需要复核，请打开准备度 / 健康页查看原因。", tone: status };
}

function toolsetSummary(toolset: string) {
  if (toolset === "general_full") {
    return { label: "完整工具集", detail: "可查看通用工具；写入、外部平台和高风险动作仍需控制令牌与审批。" };
  }
  return { label: "金融安全工具集", detail: "适合日常研究、数据检查和只读分析，默认不直接执行高风险动作。" };
}

export function AppContextPanel({
  controlToken,
  endpoint,
  health,
  hermesStatus,
  selectedThread,
  status,
  tools,
  compact = false,
  onOpenSettings,
  onOpenWorkbench
}: {
  controlToken: string;
  endpoint: string;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  selectedThread?: TaskThread | null;
  status: string;
  tools: ToolCatalogItem[];
  compact?: boolean;
  onOpenSettings?: () => void;
  onOpenWorkbench?: () => void;
}) {
  const fullModeReady = Boolean(hermesStatus?.full_mode_enabled || health?.hermes?.full_mode_enabled || health?.hermes?.full_mode_active);
  const controlReady = Boolean(controlToken.trim() && health?.control?.token_configured);
  const toolset = health?.tools?.toolset || hermesStatus?.evaluated_toolset || "finance_safe";
  const connection = connectionSummary(status, health);
  const toolsetInfo = toolsetSummary(toolset);

  return (
    <aside className={`context-panel ${compact ? "compact" : ""}`} aria-label="环境上下文">
      <section className="context-card compact">
        <div className="context-card-head">
          <div>
            <span>进度</span>
            <strong>当前运行环境</strong>
          </div>
          <Activity size={16} />
        </div>
        <div className="context-row">
          <Bot size={15} />
          <span>Agent</span>
          <StatusBadge status={connection.tone} label={connection.label} />
        </div>
        <p className="context-card-copy">{connection.detail}</p>
        <div className="context-row">
          <Globe2 size={15} />
          <span>Agent 端点</span>
          <code>{endpoint}</code>
        </div>
      </section>

      <section className="context-card">
        <div className="context-card-head">
          <div>
            <span>环境信息</span>
            <strong>权限与能力</strong>
          </div>
          <ShieldCheck size={16} />
        </div>
        {compact && (!controlReady || !fullModeReady) && (
          <GatedState
            action={
              onOpenSettings ? (
                <button className="small-button" onClick={onOpenSettings} type="button">
                  打开设置
                </button>
              ) : undefined
            }
            reason={!controlReady ? "control token required" : "full mode required"}
            status={!controlReady ? "gated" : "unconfigured"}
            title={!controlReady ? "控制令牌未就绪" : "完整模式未开启"}
          />
        )}
        <div className="context-list">
          <div className="context-row">
            <KeyRound size={15} />
            <span>控制令牌</span>
            <StatusBadge status={controlReady ? "ready" : "gated"} label={controlReady ? "可执行受控操作" : "仅可查看/研究"} />
          </div>
          <div className="context-row">
            <ServerCog size={15} />
            <span>完整模式</span>
            <StatusBadge status={fullModeReady ? "ready" : "gated"} label={fullModeReady ? "已开启" : "未开启"} />
          </div>
          <div className="context-row">
            <Wrench size={15} />
            <span>工具集</span>
            <strong>{toolsetInfo.label}</strong>
          </div>
          <p className="context-card-copy">{toolsetInfo.detail}</p>
          <div className="context-row">
            <Database size={15} />
            <span>工具数量</span>
            <strong>{tools.length || health?.tools?.count || 0}</strong>
          </div>
        </div>
      </section>

      <section className="context-card">
        <div className="context-card-head">
          <div>
            <span>当前任务</span>
            <strong>{selectedThread ? "复核摘要" : "等待任务线程"}</strong>
          </div>
          <GitBranch size={16} />
        </div>
        {selectedThread ? (
          <div className="context-task">
            <strong>{selectedThread.title}</strong>
            <span>{selectedThread.sessionId || selectedThread.id}</span>
            <p>{selectedThread.prompt || "该任务暂无输入摘要。"}</p>
            <StatusBadge status={selectedThread.status} label={statusLabel(selectedThread.status)} />
          </div>
        ) : (
          <div className="context-empty">
            <strong>暂无选中线程</strong>
            <span>开始任务后，这里会汇总当前回复、模型、审批和事件状态。</span>
            {compact && onOpenWorkbench && (
              <button className="small-button" onClick={onOpenWorkbench} type="button">
                返回工作台
              </button>
            )}
          </div>
        )}
      </section>

      {!compact && (
      <section className="context-card muted-card">
        <div className="context-card-head">
          <div>
            <span>来源</span>
            <strong>本地桌面端</strong>
          </div>
        </div>
        <p>右侧面板用于常驻显示连接、授权、工具和当前任务上下文，避免用户在多个页面之间来回寻找状态。</p>
      </section>
      )}
    </aside>
  );
}
