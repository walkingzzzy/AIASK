import { Activity, Bot, Boxes, Database, Factory, RefreshCw, ShieldCheck, UserRound, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, DesktopSettingsStatus, HealthDetailed, ToolCatalogItem } from "../../types";

const FINANCE_TOOL_NAMES = [
  "agent_analyze_stock",
  "agent_quant_data_gate",
  "agent_factor_validation",
  "agent_backtest_suite",
  "agent_portfolio_risk",
  "agent_quant_research_run",
  "agent_factory_status",
  "agent_factory_runs",
  "agent_strategy_review_snapshot",
  "agent_strategy_domain_events",
  "agent_incubation_factory_status",
  "agent_memory_search",
  "agent_session_search"
];

const HERMES_GROUPS: Array<{ label: string; area: string; tools: string[] }> = [
  { label: "文件", area: "general_read", tools: ["agent_file_list", "agent_file_read"] },
  { label: "终端", area: "terminal_backend", tools: ["agent_terminal_backends"] },
  { label: "浏览器", area: "browser", tools: ["agent_browser_snapshot", "agent_browser_console"] },
  { label: "网页", area: "web", tools: ["agent_web_search"] },
  { label: "网关", area: "platform_gateway", tools: ["agent_gateway_status", "agent_gateway_platforms"] },
  { label: "学习/RL", area: "learning", tools: ["agent_learning_status", "agent_learning_review", "agent_rl_list_environments", "agent_rl_get_config"] },
  { label: "扩展", area: "skills/plugins/mcp", tools: ["agent_skill_list", "agent_plugin_list", "agent_mcp_manage"] },
  { label: "任务与交接", area: "cron_admin/memory_admin", tools: ["agent_job_list", "agent_job_create", "agent_session_handoff"] }
];

function toolNames(tools: ToolCatalogItem[]): Set<string> {
  return new Set(tools.map((tool) => tool.name));
}

function registeredToolNames(tools: ToolCatalogItem[], health: HealthDetailed | null): Set<string> {
  return new Set([...toolNames(tools), ...(health?.tools?.names || [])]);
}

function groupStatus(names: string[], registered: Set<string>, fullMode: boolean): string {
  const available = names.filter((name) => registered.has(name)).length;
  if (available === names.length) return "implemented";
  if (available > 0) return "partial";
  return fullMode ? "missing" : "gated";
}

export function AgentWorkspace({
  endpoint,
  apiToken,
  controlToken,
  health,
  onRefreshHealth
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  health: HealthDetailed | null;
  onRefreshHealth: () => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityWorkbenchPayload | null>(null);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, toolsPayload, capabilitiesPayload] = await Promise.all([
        api.settingsStatus(),
        api.tools(),
        api.capabilities()
      ]);
      setSettings(settingsPayload);
      setTools(toolsPayload.data || []);
      setCapabilities(capabilitiesPayload);
      onRefreshHealth();
      setMessage("AGENT_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const agent = settings?.agent || {};
  const registered = registeredToolNames(tools, health);
  const financeCount = FINANCE_TOOL_NAMES.filter((name) => registered.has(name)).length;
  const fullMode = Boolean(agent.toolset === "general_full" || health?.hermes?.full_mode_active || health?.hermes?.full_mode_enabled);
  const mcp = capabilities?.mcp;
  const strategy = capabilities?.strategy_factory;
  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>智能体</span>
          <h1>运行状态</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : health?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{endpoint}</span>
              <h2>{health?.service || "AIASK Agent"}</h2>
              <p>本机 Agent HTTP API、工具注册表、运行存储和控制令牌就绪状态。</p>
            </div>
            <Bot size={24} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="状态" value={health?.status || "离线"} status={health?.status || "not_loaded"} />
            <MetricCard label="工具集" value={String(agent.toolset || health?.tools?.toolset || "-")} status="ready" />
            <MetricCard label="工具" value={health?.tools?.count ?? 0} status={(health?.tools?.count || 0) > 0 ? "ready" : "not_loaded"} />
            <MetricCard label="控制" value={agent.control_authorized ? "已授权" : agent.control_token_configured ? "已配置" : "缺失"} status={agent.control_authorized ? "ready" : "gated"} />
          </div>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>金融安全</span>
                <h3>金融智能体能力覆盖</h3>
              </div>
              <ShieldCheck size={18} />
            </div>
            <div className="diagnostics-summary wide">
              <MetricCard label="金融工具" value={`${financeCount}/${FINANCE_TOOL_NAMES.length}`} status={financeCount === FINANCE_TOOL_NAMES.length ? "implemented" : "partial"} />
              <MetricCard label="数据闸门" value={registered.has("agent_quant_data_gate") ? "就绪" : "缺失"} status={registered.has("agent_quant_data_gate") ? "implemented" : "missing"} />
              <MetricCard label="回测/风险" value={registered.has("agent_backtest_suite") && registered.has("agent_portfolio_risk") ? "就绪" : "部分"} status={registered.has("agent_backtest_suite") && registered.has("agent_portfolio_risk") ? "implemented" : "partial"} />
              <MetricCard label="记忆/会话" value={registered.has("agent_memory_search") && registered.has("agent_session_search") ? "就绪" : "缺失"} status={registered.has("agent_memory_search") && registered.has("agent_session_search") ? "implemented" : "missing"} />
            </div>
            <div className="mini-list">
              {FINANCE_TOOL_NAMES.map((name) => (
                <article key={name}>
                  <strong>{name}</strong>
                  <span>{registered.has(name) ? "已注册到当前 Agent 工具目录" : "当前工具集中未注册"}</span>
                  <StatusBadge status={registered.has(name) ? "implemented" : "missing"} />
                </article>
              ))}
            </div>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Hermes full</span>
                  <h3>Full mode 能力分组</h3>
                </div>
                <Boxes size={18} />
              </div>
              <div className="mini-list">
                {HERMES_GROUPS.map((group) => (
                  <article key={group.label}>
                    <strong>{group.label}</strong>
                    <span>{group.area} / 已注册 {group.tools.filter((name) => registered.has(name)).length}/{group.tools.length} 个工具</span>
                    <StatusBadge status={groupStatus(group.tools, registered, fullMode)} />
                  </article>
                ))}
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>MCP 与工厂</span>
                  <h3>运行操作面</h3>
                </div>
                <Wrench size={18} />
              </div>
              <div className="kv-grid">
                <span>MCP 服务</span>
                <strong>{String(mcp?.servers?.length ?? "-")}</strong>
                <span>MCP 工具</span>
                <strong>{String(mcp?.tools?.length ?? "-")}</strong>
                <span>MCP 状态</span>
                <strong>{String(mcp?.gated ? "gated" : mcp?.discovery_status || "-")}</strong>
                <span>策略工厂</span>
                <strong>{String(strategy?.status?.success ? "ready" : strategy?.status?.error_code || "-")}</strong>
              </div>
              <div className="mini-list">
                <article>
                  <strong>数据与同步</strong>
                  <span>数据库新鲜度和同步计划意图通过 Agent 桌面 facade 执行。</span>
                  <Database size={16} />
                </article>
                <article>
                  <strong>工厂操作</strong>
                  <span>策略、因子和孵化写入操作都会创建持久化审批意图。</span>
                  <Factory size={16} />
                </article>
                <article>
                  <strong>本地用户</strong>
                  <span>回复、会话、任务、记忆和量化研究都会使用当前本地用户作用域。</span>
                  <UserRound size={16} />
                </article>
              </div>
            </article>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>运行时</span>
                  <h3>配置</h3>
                </div>
                <Activity size={18} />
              </div>
              <div className="kv-grid">
                <span>模型</span>
                <strong>{String(agent.model || health?.runtime?.model || "-")}</strong>
                <span>迭代次数</span>
                <strong>{String(agent.max_iterations || health?.runtime?.max_iterations || "-")}</strong>
                <span>API token</span>
                <strong>{agent.api_token_configured ? "已配置" : "loopback/open"}</strong>
                <span>控制原因</span>
                <strong>{String(agent.control_reason || "-")}</strong>
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>健康状态</span>
                  <h3>详细载荷</h3>
                </div>
                <StatusBadge status={health?.status || "not_loaded"} />
              </div>
              <JsonPanel value={health || { status: "not_loaded" }} />
            </article>
          </section>

          <details className="raw-details">
            <summary>原始 Agent 设置</summary>
            <JsonPanel value={settings || { status: "not_loaded" }} />
          </details>
        </div>
      </div>
    </section>
  );
}
