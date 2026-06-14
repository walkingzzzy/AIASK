import { Cable, CircleGauge, PlugZap, Puzzle, ShieldCheck } from "lucide-react";
import { StatusBadge } from "../../components/shared";
import type { HealthDetailed, HermesStatus, MainView, ToolCatalogItem } from "../../types";

const integrationEntries: Array<{
  id: MainView;
  title: string;
  label: string;
  description: string;
  icon: typeof PlugZap;
  needsControl?: boolean;
}> = [
  {
    id: "mcp-connectors",
    title: "MCP 与连接器",
    label: "MCP / 连接器",
    description: "发现 MCP 服务、资源、提示词、OAuth 状态和连接器健康。",
    icon: PlugZap,
    needsControl: true
  },
  {
    id: "gateway",
    title: "Gateway 投递",
    label: "Gateway",
    description: "查看平台、守护进程、消息、目录、重试和发送意图。",
    icon: Cable,
    needsControl: true
  },
  {
    id: "plugins-skills",
    title: "插件与技能",
    label: "插件 / 技能",
    description: "管理原生插件生命周期，并把技能应用回工作台线程。",
    icon: Puzzle,
    needsControl: true
  },
  {
    id: "tools-intents-approvals",
    title: "工具与审批",
    label: "审批",
    description: "工具目录、意图、审批和受控流程管理。",
    icon: ShieldCheck,
    needsControl: true
  },
  {
    id: "readiness-health",
    title: "准备度与健康",
    label: "准备度 / 健康",
    description: "复核模型、MCP、Gateway、插件和金融系统门控。",
    icon: CircleGauge
  }
];

export function IntegrationsPage({
  controlToken,
  health,
  hermesStatus,
  onOpenView,
  tools
}: {
  controlToken: string;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  onOpenView: (view: MainView) => void;
  tools: ToolCatalogItem[];
}) {
  const controlReady = Boolean(controlToken.trim());
  const fullModeReady = Boolean(health?.hermes?.full_mode_active || hermesStatus?.full_mode_active);

  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>集成与运维</span>
          <h1>集成</h1>
          <p>MCP、Gateway、插件、技能、连接器和准备度的统一入口；受控动作保持可见，并继续走安全门控。</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={controlReady ? "ready" : "gated"} label={controlReady ? "控制已就绪" : "控制受限"} />
          <StatusBadge status={fullModeReady ? "ready" : "gated"} label={fullModeReady ? "完整模式" : "安全模式"} />
          <StatusBadge status="ready" label={`${tools.length || health?.tools?.count || 0} 个工具`} />
        </div>
      </header>

      <div className="capabilities-body">
        <div className="optimization-grid">
          {integrationEntries.map((entry) => {
            const Icon = entry.icon;
            const gated = entry.needsControl && !controlReady;
            return (
              <button
                aria-label={`打开 ${entry.label}`}
                className="optimization-card action-card"
                key={entry.id}
                onClick={() => onOpenView(entry.id)}
                type="button"
              >
                <Icon size={18} />
                <span>{entry.label}</span>
                <h2>{entry.title}</h2>
                <p>{entry.description}</p>
                <StatusBadge status={gated ? "gated" : "ready"} label={gated ? "需要控制令牌" : "可查看"} />
              </button>
            );
          })}
        </div>

        <section className="capability-section">
          <div className="section-header">
            <div>
              <span>安全边界</span>
              <h3>ActionIntent 仍是状态型动作的唯一授权链路</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          <p className="muted">
            这个聚合页只重组前端入口。所有会改变状态的集成动作仍然使用现有 Agent 路由、控制令牌门控和审批流程。
          </p>
        </section>
      </div>
    </section>
  );
}
