import { Activity, AlertTriangle, ArrowRight, CheckCircle2, ListChecks, PlayCircle, RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";
import { DiagnosticsPanel } from "../../components/DiagnosticsPanel";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { ReadinessDiagnostic } from "../../components/ReadinessDiagnostic";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import type { FinancialNextAction, FinancialReadinessGate, FullModeConsoleData, HealthDetailed, HermesStatus, MainView } from "../../types";
import "../../components/AgentEnhancements.css";

interface DiagnosticResult {
  category: string;
  status: "healthy" | "warning" | "error";
  title: string;
  message: string;
  fix_suggestions: string[];
  related_page?: string;
}

type SafeRunPathStep = {
  id: string;
  label: string;
  detail: string;
  status: string;
  target_page: MainView | string;
  evidence: string;
};

const STATUS_TEXT: Record<string, string> = {
  blocked: "阻塞",
  completed: "已完成",
  control_token_required: "需要控制令牌",
  degraded: "降级",
  discovered: "已发现",
  gated: "受限",
  healthy: "健康",
  implemented: "已实现",
  missing: "缺失",
  not_loaded: "未加载",
  not_required: "无需处理",
  ok: "正常",
  partial: "部分就绪",
  ready: "就绪",
  registered: "已注册",
  auth_missing: "授权缺失",
  live_pending: "等待真实验证",
  live_unverified: "Live 未验证",
  warning: "警告",
};

function statusText(status?: unknown): string {
  const value = String(status || "not_loaded");
  return STATUS_TEXT[value.toLowerCase()] || value;
}

function toolsetText(value?: unknown): string {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "general_full") return "完整工具集";
  if (normalized === "finance_safe") return "金融安全工具集";
  return value ? String(value) : "金融安全工具集";
}

function providerText(value?: unknown): string {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "sqlite") return "本地数据库";
  if (normalized === "not_loaded") return "未加载";
  if (!value) return "未加载";
  return String(value);
}

function messageText(message: string): string {
  if (!message) return "就绪";
  if (message === "CAPABILITIES_SYNCED") return "能力已同步";
  return message;
}

function readinessStatus(value: unknown): string {
  if (!value || typeof value !== "object") return "not_loaded";
  const record = value as Record<string, unknown>;
  return String(record.status || record.live_status || record.object || "ready");
}

function priorityLabel(priority?: string) {
  if (priority === "critical") return "关键";
  if (priority === "recommended") return "建议";
  if (priority === "optional") return "可选";
  return priority || "建议";
}

function priorityStatus(priority?: string) {
  if (priority === "critical") return "blocked";
  if (priority === "recommended") return "partial";
  if (priority === "optional") return "not_required";
  return "partial";
}

function actionTitle(action: FinancialNextAction): string {
  const fallback = action.title || action.action_id;
  const titles: Record<string, string> = {
    configure_mcp_auth: "配置 MCP 授权变量",
    configure_model_provider: "配置真实模型提供方",
    configure_writable_database: "配置可写本地数据库",
    enable_full_mode_when_needed: "按需开启完整模式",
    inspect_strategy_factory: "检查策略工厂准备度",
    register_or_discover_mcp: "注册或发现金融 MCP 服务",
    run_live_financial_workflow: "运行一次只读金融工作流",
    set_control_token: "设置 Agent 控制令牌",
    verify_semantic_search: "验证记忆和会话搜索",
  };
  return titles[action.action_id] || fallback;
}

function actionDetail(action: FinancialNextAction): string {
  const fallback = action.detail || "";
  const details: Record<string, string> = {
    configure_mcp_auth: "MCP 已注册但缺少授权变量；请在 Agent 进程中配置后刷新发现。",
    configure_model_provider: "设置 OpenAI 兼容模型提供方，并在模型配置页点击测试验证。",
    configure_writable_database: "设置 AIASK_SQLITE_PATH 或 AKSHARE_MCP_SQLITE_PATH 到可写 SQLite 文件。",
    enable_full_mode_when_needed: "默认 finance_safe 模式较窄；只有高级工具需要时再开启完整模式。",
    inspect_strategy_factory: "打开策略工厂面板检查状态、运行记录、快照和数据库/runtime 错误。",
    register_or_discover_mcp: "在 MCP / 连接器页面注册本地 AKShare MCP 服务并刷新工具发现。",
    run_live_financial_workflow: "先运行金融经理台只读查询，再运行量化研究，确认报告完成或被数据新鲜度明确阻塞。",
    set_control_token: "状态变更、MCP 管理、完整模式操作和审批流需要控制令牌。",
    verify_semantic_search: "运行只读记忆/会话搜索 smoke，再依赖 Agent 回忆和运行历史搜索。",
  };
  return details[action.action_id] || fallback;
}

function actionContextLabel(action: FinancialNextAction): string {
  const contexts: Record<string, string> = {
    configure_mcp_auth: "MCP 授权",
    configure_model_provider: "模型连通性",
    configure_writable_database: "本地数据库",
    enable_full_mode_when_needed: "完整模式",
    inspect_strategy_factory: "策略工厂",
    register_or_discover_mcp: "MCP 服务发现",
    run_live_financial_workflow: "只读金融验证",
    set_control_token: "控制令牌",
    verify_semantic_search: "记忆与搜索",
  };
  return contexts[action.action_id] || action.gate || action.title || "建议处理";
}

function gateByName(
  financial: { required_gates?: FinancialReadinessGate[]; optional_gates?: FinancialReadinessGate[] } | undefined,
  name: string
): FinancialReadinessGate | undefined {
  return [...(financial?.required_gates || []), ...(financial?.optional_gates || [])].find((gate) => gate.name === name);
}

function envelopeStatus(value: unknown): string {
  if (!value || typeof value !== "object") return "not_loaded";
  const record = value as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : {};
  const errorCode = String(record.error_code || "");
  const error = String(record.error || "");
  if (errorCode.includes("CONTROL_TOKEN") || error.toLowerCase().includes("control token")) return "gated";
  if (record.success === false) return String(record.error_code || data.status || "failed");
  return String(data.status || record.status || (record.success === true ? "ready" : "not_loaded"));
}

function countItems(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function pageDisplayName(page?: MainView | string): string {
  if (!page) return "相关页面";
  const normalized = String(page).toLowerCase();
  if (normalized.includes("setting")) return "设置";
  if (normalized.includes("mcp")) return "MCP / 连接器";
  if (normalized.includes("gateway")) return "Gateway";
  if (normalized.includes("financial-manager") || normalized.includes("financial manager")) return "金融经理台";
  if (normalized.includes("finance-lab") || normalized.includes("finance")) return "金融实验室";
  if (normalized.includes("data")) return "数据";
  if (normalized.includes("user")) return "本地用户 / 记忆";
  if (normalized.includes("readiness") || normalized.includes("health")) return "准备度 / 健康";
  return String(page);
}

export function ReadinessHealthPage({
  endpoint,
  apiToken,
  controlToken,
  fullConsole,
  health,
  hermesStatus,
  onOpenView,
  onRefreshHermes,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  fullConsole: FullModeConsoleData;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  onOpenView: (view: MainView) => void;
  onRefreshHermes: () => void;
}) {
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  const financial = payload?.financial_system;
  const providerStatus = readinessStatus(payload?.providers || payload?.ai || fullConsole.providers);
  const mcpStatus = String(payload?.mcp?.discovery_status || payload?.mcp?.registration_status || "not_loaded");
  const gatewayStatus = readinessStatus(fullConsole.gatewayStatus);
  const pluginStatus = fullConsole.plugins?.length ? "ready" : controlToken.trim() ? "not_loaded" : "gated";
  const modeTokenStatus = controlToken.trim() ? "ready" : "gated";
  const semanticGate = gateByName(financial, "semantic_search");
  const vectorGate = gateByName(financial, "vector_provider");
  const memoryPayload = payload?.memory || fullConsole.memory;
  const memoryRecord = memoryPayload && typeof memoryPayload === "object" ? memoryPayload as Record<string, unknown> : {};
  const memoryProvider = String(
    memoryRecord.active_provider ||
    memoryRecord.provider ||
    memoryRecord.default_provider ||
    semanticGate?.evidence?.active_provider ||
    "not_loaded"
  );
  const memorySearchStatus = semanticGate?.status || readinessStatus(memoryPayload);
  const toolset = health?.tools?.toolset || hermesStatus?.evaluated_toolset || "finance_safe";
  const nextActions = financial?.next_actions || [];
  const liveSmoke = financial?.live_smoke;
  const mcpReady = !payload?.mcp?.gated && (mcpStatus === "discovered" || mcpStatus === "registered" || mcpStatus === "ready");
  const strategyStatus = envelopeStatus(payload?.strategy_factory?.status);
  const requiredReady = financial?.required_gates?.filter((gate) => gate.status === "ready").length || 0;
  const requiredTotal = financial?.required_gates?.length || 0;
  const marketSmokeCovered = liveSmoke?.checks?.some((check) => check.name === "market_temperature_forward_validation");
  const providerOperational = ["ready", "ok", "implemented", "configured"].includes(providerStatus);
  const gatewayOperational = ["ready", "ok", "healthy"].includes(gatewayStatus);

  const safeRunPath: SafeRunPathStep[] = [
    {
      id: "mode_model",
      label: "1. 模式与模型",
      detail: "确认 Agent 端点、模型提供方、工具集和控制令牌状态，再进入金融流程。",
      status: providerOperational ? modeTokenStatus : providerStatus,
      target_page: "settings",
      evidence: `${toolsetText(toolset)} / 控制 ${statusText(modeTokenStatus)}`
    },
    {
      id: "mcp_connectors",
      label: "2. MCP 与连接器",
      detail: "确认 MCP 注册、发现、资源、提示词和连接器认证，再依赖真实金融数据。",
      status: mcpReady ? "ready" : mcpStatus,
      target_page: "mcp-connectors",
      evidence: `${countItems(payload?.mcp?.servers)} 个服务 / ${countItems(payload?.mcp?.tools)} 个工具 / ${payload?.mcp?.missing_auth_env_vars?.length || 0} 个授权缺口`
    },
    {
      id: "memory_search",
      label: "3. 记忆与搜索",
      detail: "确认会话搜索和金融记忆搜索能取回历史上下文。",
      status: memorySearchStatus,
      target_page: "user",
      evidence: `${providerText(memoryProvider)} / 向量 ${statusText(vectorGate?.status || "not_loaded")}`
    },
    {
      id: "financial_agent",
      label: "4. 金融 Agent 流程",
      detail: "先跑金融经理台只读证据链，再创建任何 ActionIntent。",
      status: financial?.status || "not_loaded",
      target_page: "financial-manager",
      evidence: `${requiredReady}/${requiredTotal} 个必需门控就绪`
    },
    {
      id: "data_quant",
      label: "5. 数据与量化研究",
      detail: "用数据新鲜度、市场温度和量化研究阶段证明流程已就绪，或明确说明被哪里阻塞。",
      status: payload?.quant?.data_status?.status || payload?.quant?.status || "not_loaded",
      target_page: "data",
      evidence: marketSmokeCovered ? "已覆盖市场温度和量化研究检查" : "市场温度检查待确认"
    },
    {
      id: "factory_relay",
      label: "6. 工厂接力",
      detail: "在数据和金融只读门控清晰后，再检查因子、策略、孵化的接力链路。",
      status: strategyStatus,
      target_page: "finance-lab",
      evidence: "因子 / 策略 / 孵化接力"
    }
  ];

  const diagnosticResults = useMemo((): DiagnosticResult[] => {
    const results: DiagnosticResult[] = [];

    if (!providerOperational) {
      results.push({
        category: "AI 提供方",
        status: providerStatus === "not_loaded" ? "warning" : "error",
        title: "AI 提供方连接异常",
        message: `当前状态：${statusText(providerStatus)}。无法可靠调用 AI 模型。`,
        fix_suggestions: ["检查 API 端点配置", "验证 API 令牌是否有效", "确认后端服务正在运行", "查看后端日志了解详细错误"],
        related_page: "settings"
      });
    }

    if (payload?.mcp?.missing_auth_env_vars?.length) {
      results.push({
        category: "MCP",
        status: "warning",
        title: "MCP 服务需要补齐授权变量",
        message: `缺少授权变量：${payload.mcp.missing_auth_env_vars.join(", ")}`,
        fix_suggestions: ["前往 MCP / 连接器页面", "确认本地 AKShare MCP 注册状态", "在 Agent 进程中配置缺失环境变量", "刷新 MCP 发现"],
        related_page: "mcp-connectors"
      });
    }

    if (!controlToken.trim()) {
      results.push({
        category: "控制令牌",
        status: "warning",
        title: "控制令牌未配置",
        message: "部分管理功能、审批流和完整模式能力需要控制令牌。",
        fix_suggestions: ["前往设置页面", "填写控制令牌", "保存配置后刷新健康页"],
        related_page: "settings"
      });
    }

    if (!gatewayOperational) {
      results.push({
        category: "Gateway",
        status: controlToken.trim() ? "error" : "warning",
        title: controlToken.trim() ? "Gateway 连接异常" : "Gateway 管理详情未解锁",
        message: controlToken.trim()
          ? `当前状态：${statusText(gatewayStatus)}。跨平台消息投递可能受影响。`
          : "缺少控制令牌，因此尚未读取 Gateway 守护进程、平台和消息详情。",
        fix_suggestions: controlToken.trim()
          ? ["检查 Gateway 服务状态", "验证网络连接", "查看 Gateway 错误日志"]
          : ["前往设置页面", "填写控制令牌", "刷新 Gateway 或健康页"],
        related_page: "gateway"
      });
    }

    if (financial?.required_gates?.some((gate) => gate.status !== "ready")) {
      const failedGates = financial.required_gates.filter((gate) => gate.status !== "ready");
      results.push({
        category: "Financial System",
        status: "warning",
        title: "金融系统门控未全部就绪",
        message: `${failedGates.length} 个门控需要处理：${failedGates.map((gate) => gate.name).join(", ")}`,
        fix_suggestions: failedGates.map((gate) => `配置 ${gate.name}: ${gate.detail || "查看 readiness payload"}`),
        related_page: "financial-manager"
      });
    }

    if (semanticGate && semanticGate.status !== "ready") {
      results.push({
        category: "Memory/Search",
        status: "warning",
        title: "记忆与会话搜索探针失败",
        message: `${semanticGate.name}: ${semanticGate.detail}`,
        fix_suggestions: ["运行准备度页的技术联调清单", "检查记忆搜索和会话搜索是否能返回结果", "确认 Agent 状态数据库可写"],
        related_page: "readiness-health"
      });
    }

    return results;
  }, [payload, controlToken, providerStatus, providerOperational, gatewayStatus, gatewayOperational, financial, semanticGate]);

  function handleNavigate(page?: string) {
    if (!page) return;
    onOpenView(pageToView(page));
  }

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>运维与连接</span>
          <h1>准备度 / 健康</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={messageText(message)} />
          <button className="small-button" disabled={busy} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>准备度诊断</span>
              <h2>10-20 秒定位主要问题层</h2>
              <p>优先检查 AI 提供方、Gateway、插件、MCP、金融系统、记忆搜索、模式与令牌，快速判断是配置、授权还是后端离线问题。</p>
            </div>
            <Activity size={22} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="AI 提供方" value={statusText(providerStatus)} status={providerStatus} />
            <MetricCard label="Gateway" value={statusText(gatewayStatus)} status={gatewayStatus} />
            <MetricCard label="插件" value={statusText(pluginStatus)} status={pluginStatus} />
            <MetricCard label="MCP" value={statusText(mcpStatus)} status={mcpStatus} />
            <MetricCard label="金融系统" value={statusText(financial?.status || "not_loaded")} status={financial?.status} />
            <MetricCard label="记忆 / 搜索" value={statusText(memorySearchStatus)} status={memorySearchStatus} />
            <MetricCard label="模式 / 令牌" value={modeTokenStatus === "ready" ? "就绪" : "受限"} status={modeTokenStatus} />
          </div>

          {!!diagnosticResults.length && <ReadinessDiagnostic results={diagnosticResults} onNavigate={handleNavigate} />}

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>运行前检查</span>
                <h3>真实金融流程前置检查</h3>
              </div>
              <PlayCircle size={18} />
            </div>
            <div className="capability-grid three">
              {safeRunPath.map((step) => (
                <article className={`capability-row ${step.status === "ready" || step.status === "ok" ? "ok" : "warn"}`} key={step.id}>
                  <div>
                    <span>{step.evidence}</span>
                    <strong>{step.label}</strong>
                  </div>
                  <StatusBadge status={step.status} label={statusText(step.status)} />
                  <small>{step.detail}</small>
                  <button
                    aria-label={`打开${pageDisplayName(step.target_page)}：${step.label}`}
                    className="small-button"
                    onClick={() => handleNavigate(step.target_page)}
                    type="button"
                  >
                    <ArrowRight size={13} />
                    打开{pageDisplayName(step.target_page)}
                  </button>
                </article>
              ))}
            </div>
            <div className="notice info compact">
              <CheckCircle2 size={14} />
              <span>这些步骤都是只读导航检查；涉及状态变更或交易风险的动作仍必须经过 ActionIntent 和后端防护。</span>
            </div>
          </section>

          <div className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>下一步行动</span>
                  <h3>现在最该做什么</h3>
                </div>
                <ListChecks size={18} />
              </div>
              <div className="mini-list">
                {nextActions.map((action: FinancialNextAction) => (
                  <article className="capability-row" key={action.action_id}>
                    <div>
                      <span>{actionContextLabel(action)}</span>
                      <strong>{actionTitle(action)}</strong>
                    </div>
                    <StatusBadge status={priorityStatus(action.priority)} label={priorityLabel(action.priority)} />
                    <small>{actionDetail(action)}</small>
                    {action.env_vars?.length ? <small>环境变量：{action.env_vars.join(", ")}</small> : null}
                    <button
                      aria-label={`前往 ${pageDisplayName(action.target_page)}：${actionTitle(action)}`}
                      className="small-button"
                      onClick={() => handleNavigate(action.target_page)}
                      type="button"
                    >
                      <ArrowRight size={13} />
                      前往 {pageDisplayName(action.target_page)}
                    </button>
                  </article>
                ))}
                {!nextActions.length && (
                  <article className="capability-row ok">
                    <div>
                      <span>ready</span>
                      <strong>没有阻塞项</strong>
                    </div>
                    <StatusBadge status="ready" label="就绪" />
                    <small>可以从金融实验室开始执行只读验证。</small>
                  </article>
                )}
              </div>
            </section>

            <section className="capability-section readiness-smoke-summary">
              <div className="section-header">
                <div>
                  <span>真实联调</span>
                  <h3>检查清单状态</h3>
                </div>
                <StatusBadge status={liveSmoke?.status || "not_loaded"} label={statusText(liveSmoke?.status || "not_loaded")} />
              </div>
              <div className="kv-grid">
                <span>检查数</span>
                <strong>{liveSmoke?.checks?.length || 0}</strong>
                <span>状态</span>
                <strong>{statusText(liveSmoke?.status || "not_loaded")}</strong>
              </div>
              <p className="muted">日常使用只需要看状态和检查数；脚本命令与接口清单放在下面的技术详情中，排障时再展开。</p>
              <details className="readiness-technical-details">
                <summary>
                  <span>
                    <strong>技术联调清单</strong>
                    <small>脚本、命令和接口端点。</small>
                  </span>
                </summary>
                <div className="kv-grid">
                  <span>脚本</span>
                  <strong>{liveSmoke?.script || "scripts/ops/live_readiness_smoke.py"}</strong>
                  <span>工作目录</span>
                  <strong>{liveSmoke?.working_directory || "packages/agent"}</strong>
                  <span>Self-test</span>
                  <strong>{liveSmoke?.self_test_command || "uv run python ..\\..\\scripts\\ops\\live_readiness_smoke.py --self-test --pretty"}</strong>
                  <span>Live 命令</span>
                  <strong>{liveSmoke?.live_command || "uv run python ..\\..\\scripts\\ops\\live_readiness_smoke.py --endpoint http://127.0.0.1:8767 --pretty"}</strong>
                </div>
                <p className="muted">{liveSmoke?.environment_note || "请从 packages/agent 目录运行，确保加载 Agent runtime 依赖。"}</p>
                <div className="mini-list">
                  {(liveSmoke?.checks || []).slice(0, 16).map((check, index) => (
                    <article key={`${check.name || "check"}-${index}`}>
                      <strong>{check.name || `check-${index + 1}`}</strong>
                      <p>{check.method || "GET"} {check.path || "-"}</p>
                      {!!check.observes?.length && <small>观测字段：{check.observes.join(", ")}</small>}
                    </article>
                  ))}
                  {!liveSmoke?.checks?.length && (
                    <article>
                      <strong>等待后端 readiness payload</strong>
                      <p>刷新后会显示真实联调脚本需要验证的端点。</p>
                    </article>
                  )}
                </div>
              </details>
            </section>
          </div>

          {!controlToken.trim() && (
            <div className="notice warn">
              <AlertTriangle size={14} />
              <span>当前缺少控制令牌，会话、Gateway、插件、MCP 管理和完整模式运维数据会被锁定。</span>
            </div>
          )}

          <div className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>系统摘要</span>
                  <h3>快速定位</h3>
                </div>
              </div>
              <div className="kv-grid">
                <span>Agent</span>
                <strong>{statusText(health?.status || "not_loaded")}</strong>
                <span>工具集</span>
                <strong>{toolsetText(toolset)}</strong>
                <span>完整模式</span>
                <strong>{health?.hermes?.full_mode_active ? "已激活" : health?.hermes?.full_mode_enabled ? "已开启" : "关闭"}</strong>
                <span>控制令牌</span>
                <strong>{controlToken.trim() ? "已填写" : "未填写"}</strong>
                <span>MCP 缺少授权</span>
                <strong>{payload?.mcp?.missing_auth_env_vars?.join(", ") || "-"}</strong>
                <span>金融门控</span>
                <strong>{requiredTotal}</strong>
                <span>记忆提供方</span>
                <strong>{providerText(memoryProvider)}</strong>
                <span>语义搜索</span>
                <strong>{statusText(semanticGate?.status || "not_loaded")}</strong>
                <span>向量提供方</span>
                <strong>{statusText(vectorGate?.status || "not_loaded")}</strong>
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>问题提示</span>
                  <h3>高优先级缺口</h3>
                </div>
              </div>
              <div className="mini-list">
                {!health?.status || health.status === "ok" || health.status === "healthy" ? null : (
                  <article>
                    <strong>Agent 连接异常</strong>
                    <p>先检查 Agent 端点、后端进程和健康检查。</p>
                  </article>
                )}
                {payload?.mcp?.missing_auth_env_vars?.length ? (
                  <article>
                    <strong>MCP 授权缺失</strong>
                    <p>{payload.mcp.missing_auth_env_vars.join(", ")}</p>
                  </article>
                ) : null}
                {!controlToken.trim() ? (
                  <article>
                    <strong>控制令牌未填写</strong>
                    <p>完整模式管理面与审批流无法完整工作。</p>
                  </article>
                ) : null}
                {financial?.required_gates?.filter((item) => item.status !== "ready").map((item) => (
                  <article key={item.name}>
                    <strong>{item.name}</strong>
                    <p>{item.detail}</p>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <details className="capability-section readiness-technical-details">
            <summary>
              <span>
                <strong>高级诊断：完整模式控制台</strong>
                <small>包含英文能力清单和底层状态，排障时展开。</small>
              </span>
            </summary>
            <button className="small-button" disabled={busy} onClick={onRefreshHermes} type="button">
              <RefreshCw size={14} />
              刷新完整控制台
            </button>
            <DiagnosticsPanel
              apiToken={apiToken}
              busy={busy}
              controlToken={controlToken}
              endpoint={endpoint}
              fullConsole={fullConsole}
              health={health}
              hermesStatus={hermesStatus}
              message={message}
              onRefresh={onRefreshHermes}
              parity={health?.hermes?.parity}
            />
          </details>

          <details className="raw-details">
            <summary>原始准备度载荷</summary>
            <JsonPanel value={{ payload, health, hermesStatus }} />
          </details>
        </div>
      </div>
    </section>
  );
}

function pageToView(page: string): MainView {
  const normalized = page.toLowerCase();
  if (normalized === "user" || normalized.includes("memory") || normalized.includes("local user")) return "user";
  if (normalized.includes("finance-lab") || normalized.includes("finance lab")) return "finance-lab";
  if (normalized.includes("quant")) return "quant";
  if (normalized.includes("data")) return "data";
  if (normalized.includes("strategy")) return "strategy-factory";
  if (normalized.includes("factor")) return "factor-factory";
  if (normalized.includes("incubation")) return "incubation";
  if (normalized.includes("mcp") || normalized.includes("connector")) return "mcp-connectors";
  if (normalized.includes("gateway")) return "gateway";
  if (normalized.includes("tool") || normalized.includes("approval") || normalized.includes("intent")) return "tools-intents-approvals";
  if (normalized.includes("financial") || normalized.includes("finance")) return "financial-manager";
  if (normalized.includes("plugin") || normalized.includes("skill")) return "plugins-skills";
  if (normalized.includes("setting") || normalized.includes("connection") || normalized.includes("control token")) return "settings";
  return "readiness-health";
}
