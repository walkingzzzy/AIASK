import { Activity, Bot, Database, GitBranch, Globe2, KeyRound, ServerCog, ShieldCheck, Wrench } from "lucide-react";
import { StatusBadge } from "./shared";
import type { HealthDetailed, HermesStatus, TaskThread, ToolCatalogItem } from "../types";

export function AppContextPanel({
  controlToken,
  endpoint,
  health,
  hermesStatus,
  selectedThread,
  status,
  tools
}: {
  controlToken: string;
  endpoint: string;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  selectedThread?: TaskThread | null;
  status: string;
  tools: ToolCatalogItem[];
}) {
  const fullModeReady = Boolean(hermesStatus?.full_mode_enabled || health?.hermes?.full_mode_enabled || health?.hermes?.full_mode_active);
  const controlReady = Boolean(controlToken.trim() && health?.control?.token_configured);
  const toolset = health?.tools?.toolset || hermesStatus?.evaluated_toolset || "finance_safe";

  return (
    <aside className="context-panel" aria-label="环境上下文">
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
          <StatusBadge status={status} label={status} />
        </div>
        <div className="context-row">
          <Globe2 size={15} />
          <span>Endpoint</span>
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
        <div className="context-list">
          <div className="context-row">
            <KeyRound size={15} />
            <span>控制令牌</span>
            <StatusBadge status={controlReady ? "ready" : "gated"} label={controlReady ? "已填写/服务端已配置" : "未就绪"} />
          </div>
          <div className="context-row">
            <ServerCog size={15} />
            <span>Hermes full</span>
            <StatusBadge status={fullModeReady ? "ready" : "gated"} label={fullModeReady ? "已开启" : "未开启"} />
          </div>
          <div className="context-row">
            <Wrench size={15} />
            <span>工具集</span>
            <strong>{toolset}</strong>
          </div>
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
            <StatusBadge status={selectedThread.status} label={selectedThread.status} />
          </div>
        ) : (
          <div className="context-empty">
            <strong>暂无选中线程</strong>
            <span>运行智能体任务后，这里会显示回复、模型、Token、审批和事件详情。</span>
          </div>
        )}
      </section>

      <section className="context-card muted-card">
        <div className="context-card-head">
          <div>
            <span>来源</span>
            <strong>本地桌面端</strong>
          </div>
        </div>
        <p>右侧面板用于常驻显示连接、授权、工具和当前任务上下文，避免用户在多个页面之间来回寻找状态。</p>
      </section>
    </aside>
  );
}
