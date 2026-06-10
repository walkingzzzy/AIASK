import { Activity, Bot, Boxes, BrainCircuit, Cable, Factory, FlaskConical, Layers3, Puzzle, RefreshCw, ServerCog, ShieldCheck } from "lucide-react";
import type { ElementType } from "react";
import { useEffect, useMemo, useState } from "react";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import type { CapabilityTab, CapabilityWorkbenchPayload } from "../../types";
import { GatedState, MetricCard, RawEvidencePanel, StatusBadge, localizeBlockedReason } from "../../components/shared";
import { AiTestingPanel } from "../ai-testing/AiTestingPanel";
import { ConnectorsPanel } from "../connectors/ConnectorsPanel";
import { IncubationFactoryPanel } from "../incubation/IncubationFactoryPanel";
import { StrategyFactoryPanel } from "../factory/StrategyFactoryPanel";
import { McpPanel } from "../mcp/McpPanel";
import { SkillsPanel } from "../skills/SkillsPanel";
import { CoverageMatrixPanel } from "./CoverageMatrixPanel";
import { HermesPanel } from "./HermesPanel";
import { PluginsPanel } from "./PluginsPanel";
import { capabilityIssues, collectCapabilityRows, itemLabel } from "./capabilityUtils";

const tabs: Array<{ id: CapabilityTab; label: string; icon: ElementType }> = [
  { id: "overview", label: "总览", icon: Activity },
  { id: "coverage", label: "覆盖矩阵", icon: ShieldCheck },
  { id: "connectors", label: "连接器", icon: Cable },
  { id: "hermes", label: "Hermes", icon: Boxes },
  { id: "mcp", label: "MCP", icon: ServerCog },
  { id: "factory", label: "策略工厂", icon: Factory },
  { id: "incubation", label: "孵化", icon: FlaskConical },
  { id: "skills", label: "技能", icon: Layers3 },
  { id: "plugins", label: "插件", icon: Puzzle },
  { id: "ai", label: "AI 测试", icon: BrainCircuit }
];

function sourceMeta(source?: string | null): { status: string; label: string } {
  if (source === "mock_fixture") return { status: "fixture_degraded", label: "Mock 数据" };
  if (source === "gated") return { status: "gated", label: "真实后端受限" };
  if (source === "offline") return { status: "offline", label: "离线" };
  return { status: "live_backend", label: "真实后端" };
}

function summaryStatusMeta(status?: string | null): { status: string; label: string } {
  if (status === "in_progress") return { status: "live_pending", label: "代码对齐完成，等待真实验证" };
  if (!status) return { status: "not_loaded", label: "未加载" };
  return { status, label: status };
}

function Overview({ payload, message }: { payload: CapabilityWorkbenchPayload | null; message: string }) {
  const counts = payload?.summary.counts || {};
  const rows = useMemo(() => collectCapabilityRows(payload), [payload]);
  const issues = capabilityIssues(payload);
  const control = payload?.summary.control;
  const financialSystem = payload?.financial_system;
  const source = payload?.summary.source || (payload ? "live_backend" : "offline");
  const sourceBadge = sourceMeta(source);
  const summaryBadge = summaryStatusMeta(payload?.summary.status);
  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>能力中心</span>
          <h2>运行时评审面板</h2>
          <p>从当前 Agent 端点统一查看后端对齐、MCP 发现、工厂、技能、插件和 AI 检查结果。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={sourceBadge.status} label={sourceBadge.label} />
          <StatusBadge status={summaryBadge.status} label={summaryBadge.label} />
        </div>
      </div>

      <div className="diagnostics-summary wide">
        <MetricCard label="已实现" value={counts.implemented || 0} status="implemented" />
        <MetricCard label="真实未验" value={counts.live_unverified || 0} status="live_unverified" />
        <MetricCard label="未配置" value={counts.unconfigured || 0} status="unconfigured" />
        <MetricCard label="失败/缺失" value={(counts.failed || 0) + (counts.missing || 0)} status={(counts.failed || 0) + (counts.missing || 0) ? "failed" : "implemented"} />
      </div>

      {financialSystem && (
        <div className="capability-section compact-section">
          <div className="section-header">
            <div>
              <span>金融系统闸门</span>
              <h3>生产就绪状态</h3>
            </div>
            <StatusBadge status={financialSystem.status} label={financialSystem.production_ready ? "production ready" : financialSystem.status} />
          </div>
          <div className="mini-list">
            {financialSystem.required_gates.map((gate) => (
              <article key={gate.name}>
                <strong>{gate.name}</strong>
                <span>{gate.required ? "required" : "optional"}</span>
                <StatusBadge status={gate.status} />
                <p>{gate.detail}</p>
              </article>
            ))}
          </div>
          {financialSystem.disclaimer && <p className="muted">{financialSystem.disclaimer}</p>}
        </div>
      )}

      {payload && (
        <div className="capability-section compact-section">
          <div className="kv-grid">
            <span>完整模式</span>
            <strong>{control?.full_mode_enabled ? "已开启" : "未开启"}</strong>
            <span>控制令牌</span>
            <strong>{control?.control_token_configured ? "已配置" : "未配置"}</strong>
            <span>控制授权</span>
            <strong>{String(control?.control_authorized ?? control?.authorized ?? false)}</strong>
            <span>受限原因</span>
            <strong>{localizeBlockedReason(control?.gated_reason || control?.reason) || "-"}</strong>
          </div>
        </div>
      )}

      {!payload?.summary.control.authorized && (
        <GatedState
          reason={payload?.summary.control.gated_reason || payload?.summary.control.reason || "需要控制令牌才能查看完整 MCP、技能、插件、网关、终端和 RL 数据。"}
          status="gated"
          title="能力评审受限"
        />
      )}

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{issues.length} 个问题</span>
              <h3>可处理缺口</h3>
            </div>
          </div>
          <div className="mini-list">
            {issues.slice(0, 12).map((issue) => (
              <article key={`${itemLabel(issue)}:${issue.area || ""}`}>
                <strong>{itemLabel(issue)}</strong>
                <span>{issue.area || issue.status || "能力"}</span>
                <p>{Array.isArray(issue.missing_aiask_tools) ? issue.missing_aiask_tools.join(", ") : issue.error || "需要配置或实现。"}</p>
              </article>
            ))}
            {!issues.length && <p className="muted">当前能力台账没有代码层缺口。</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{rows.length} 项检查</span>
              <h3>最近就绪条目</h3>
            </div>
          </div>
          <div className="mini-list">
            {rows.slice(0, 10).map((item) => (
              <article key={`${itemLabel(item as Record<string, unknown>)}:${item.area || ""}`}>
                <strong>{itemLabel(item as Record<string, unknown>)}</strong>
                <span>{item.area || "-"}</span>
                <StatusBadge status={item.status} />
              </article>
            ))}
          </div>
        </div>
      </section>

      <RawEvidencePanel title="原始能力中心数据" value={payload || { status: "not_loaded", message }} />
    </div>
  );
}

export function CapabilitiesWorkspace({
  endpoint,
  apiToken,
  controlToken,
  initialTab = "overview"
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  initialTab?: CapabilityTab;
}) {
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);
  const [activeTab, setActiveTab] = useState<CapabilityTab>(initialTab);
  const sourceBadge = sourceMeta(payload?.summary.source || (payload ? "live_backend" : "offline"));
  const summaryBadge = summaryStatusMeta(payload?.summary.status || message || "not_loaded");

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>能力中心</span>
          <h1>运行时评审</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={sourceBadge.status} label={sourceBadge.label} />
          <StatusBadge status={summaryBadge.status} label={summaryBadge.label} />
          <button aria-label="刷新能力评审" className="small-button" disabled={busy} onClick={() => refresh()} title="刷新能力评审" type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              aria-label={tab.label}
              aria-pressed={activeTab === tab.id}
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              title={tab.label}
              type="button"
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="capabilities-body">
        {!payload && busy && (
          <div className="empty-thread">
            <Bot size={28} />
            <strong>正在加载能力</strong>
            <span>正在读取 Hermes 对齐、MCP、策略工厂、技能和 AI 诊断。</span>
          </div>
        )}
        {activeTab === "overview" && <Overview payload={payload} message={message} />}
        {activeTab === "coverage" && <CoverageMatrixPanel capabilities={payload} />}
        {activeTab === "connectors" && <ConnectorsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />}
        {activeTab === "hermes" && <HermesPanel payload={payload} />}
        {activeTab === "mcp" && <McpPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "factory" && <StrategyFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} payload={payload} />}
        {activeTab === "incubation" && <IncubationFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />}
        {activeTab === "skills" && <SkillsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "plugins" && <PluginsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />}
        {activeTab === "ai" && <AiTestingPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} payload={payload} />}
      </div>
    </section>
  );
}
