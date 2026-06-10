import { AlertTriangle, BarChart3, BriefcaseBusiness, Landmark, Play, RefreshCw, Search, ShieldCheck, Workflow } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { GatedState, MetricCard, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  FinancialManagerAction,
  FinancialManagerCatalog,
  FinancialManagerGroup,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult,
  FinancialManagerStatus
} from "../../types";

type WorkflowStepStatus = "idle" | "running" | "ready" | "blocked" | "failed";
type WorkflowStepKind = "financial_query" | "session_search" | "memory_search" | "mcp_resource" | "mcp_prompt";
type ReadOnlyWorkflowResult = Record<string, unknown> & { tool?: string; meta?: Record<string, unknown> };

type ReadOnlyWorkflowStep = {
  id: string;
  label: string;
  endpoint: string;
  kind: WorkflowStepKind;
  tool: string;
  capability_id?: string;
  action_id?: string;
  query?: string;
  params?: Record<string, unknown>;
  status: WorkflowStepStatus;
  detail: string;
  result?: ReadOnlyWorkflowResult;
};

const READ_ONLY_WORKFLOW_STEPS: ReadOnlyWorkflowStep[] = [
  {
    id: "stock_analysis",
    label: "个股分析",
    endpoint: "/v1/desktop/financial-manager/query",
    kind: "financial_query",
    tool: "agent_analyze_stock",
    capability_id: "stock-analysis",
    action_id: "analyze_stock",
    params: { code: "600519", include_decision: false },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "portfolio_risk",
    label: "组合风险",
    endpoint: "/v1/desktop/financial-manager/query",
    kind: "financial_query",
    tool: "agent_portfolio_risk",
    capability_id: "portfolio",
    action_id: "risk",
    params: { codes: ["600519", "000001"], weights: [0.5, 0.5] },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "quant_data_gate",
    label: "量化数据门禁",
    endpoint: "/v1/desktop/financial-manager/query",
    kind: "financial_query",
    tool: "agent_quant_data_gate",
    capability_id: "quant",
    action_id: "data_gate",
    params: { codes: ["600519", "000001"], max_stale_days: 5 },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "session_search",
    label: "会话搜索",
    endpoint: "/v1/search?query=AIASK&limit=5",
    kind: "session_search",
    tool: "agent_session_search",
    query: "AIASK",
    params: { limit: 5 },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "memory_search",
    label: "记忆搜索",
    endpoint: "/v1/tools/agent_memory_search",
    kind: "memory_search",
    tool: "agent_memory_search",
    query: "AIASK",
    params: { limit: 5 },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "mcp_resource",
    label: "MCP 资源",
    endpoint: "/v1/mcp/resources/read",
    kind: "mcp_resource",
    tool: "mcp_resource_read",
    params: { uri: "aiask://quotes" },
    status: "idle",
    detail: "等待运行"
  },
  {
    id: "mcp_prompt",
    label: "MCP 提示词",
    endpoint: "/v1/mcp/prompts/get",
    kind: "mcp_prompt",
    tool: "mcp_prompt_get",
    params: { name: "risk-review" },
    status: "idle",
    detail: "等待运行"
  }
];

const FINANCIAL_GROUP_LABELS: Record<string, string> = {
  "market-research": "市场与研究",
  "portfolio-watchlist": "组合与自选",
  "risk-performance": "风险与绩效",
  "quant-backtest": "量化与回测",
  "paper-execution": "纸上交易与执行",
  "broker-readonly": "券商只读"
};

const FINANCIAL_ACTION_LABELS: Record<string, string> = {
  "stock-analysis.analyze_stock": "个股分析",
  "portfolio.risk": "组合风险",
  "quant.data_gate": "量化数据门禁",
  "backtest.suite": "回测套件",
  "portfolio.create": "创建组合意图",
  "broker-live.place_order": "实盘下单",
  "research.reports": "研究报告",
  "watchlist.list": "自选列表",
  "watchlist.add": "添加自选股意图",
  "watchlist.create": "创建自选意图",
  "paper.submit_order": "纸上交易下单意图",
  "paper-trading.orders": "纸上交易订单",
  "broker-ths.positions": "同花顺持仓只读",
  "broker-readonly.positions": "券商持仓只读"
};

function safeJsonParse(value: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
}

function cloneWorkflowSteps(): ReadOnlyWorkflowStep[] {
  return READ_ONLY_WORKFLOW_STEPS.map((step) => ({ ...step, params: { ...step.params } }));
}

function actionKey(action: FinancialManagerAction): string {
  return `${action.capability_id}::${action.action_id}`;
}

function modeLabel(mode?: string) {
  if (mode === "read_only") return "只读";
  if (mode === "stateful_intent") return "意图";
  if (mode === "blocked") return "禁用";
  return mode || "unknown";
}

function groupLabel(group: FinancialManagerGroup | undefined, fallback: string) {
  return FINANCIAL_GROUP_LABELS[group?.id || fallback] || group?.label || fallback.replace(/-/g, " ");
}

function actionLabel(action?: FinancialManagerAction | null): string {
  if (!action) return "选择一个动作";
  return FINANCIAL_ACTION_LABELS[`${action.capability_id}.${action.action_id}`] || action.label;
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function isStockAnalysisAction(action?: FinancialManagerAction | null): boolean {
  return action?.capability_id === "stock-analysis" && action.action_id === "analyze_stock";
}

function boolValue(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1";
}

function stockCodeFromParams(params?: Record<string, unknown> | null): string {
  const value = params?.code || params?.stock_code || params?.symbol || params?.ticker || "600519";
  return String(value).trim();
}

function summaryText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return compact(value);
  return String(value);
}

function pickSummaryText(records: Array<Record<string, unknown> | null>, keys: string[]): string {
  for (const record of records) {
    if (!record) continue;
    for (const key of keys) {
      const value = summaryText(record[key]);
      if (value !== "-") return value;
    }
  }
  return "-";
}

function stockAnalysisSummary(result?: FinancialManagerQueryResult | FinancialManagerIntentResult | null) {
  if (!result) return null;
  if (result.capability_id && (result.capability_id !== "stock-analysis" || result.action_id !== "analyze_stock")) return null;
  const resultRecord = result as unknown as Record<string, unknown>;
  const data = objectRecord(result.data);
  const records = [
    data,
    objectRecord(data?.analysis),
    objectRecord(data?.result),
    objectRecord(data?.decision),
    objectRecord(data?.summary)
  ];
  return {
    code: pickSummaryText(records, ["code", "stock_code", "symbol", "ticker"]),
    rating: pickSummaryText(records, ["rating", "recommendation", "signal", "action"]),
    risk: pickSummaryText(records, ["risk", "risk_level", "risk_rating"]),
    decision: pickSummaryText(records, ["decision", "decision_label", "suggestion", "advice"]),
    status: resultDataStatus(result as FinancialManagerQueryResult),
    tool: String(resultRecord.tool || "agent_analyze_stock")
  };
}

function actionAvailability(action?: FinancialManagerAction | null): Record<string, unknown> | null {
  return objectRecord(action?.availability);
}

function resultAvailability(result?: FinancialManagerQueryResult | FinancialManagerIntentResult | null): Record<string, unknown> | null {
  const data = objectRecord(result?.data);
  return objectRecord(data?.availability);
}

function resultDataStatus(result?: FinancialManagerQueryResult): string {
  const data = objectRecord(result?.data);
  return String(data?.status || result?.error_code || (result?.success ? "ready" : "failed"));
}

function sideEffectLevel(result?: unknown): string {
  const record = objectRecord(result);
  const meta = objectRecord(record?.meta);
  const sideEffect = objectRecord(meta?.side_effect);
  return String(sideEffect?.level || "read_only");
}

function workflowStatusFromResult(result: FinancialManagerQueryResult): WorkflowStepStatus {
  const status = resultDataStatus(result).toLowerCase();
  if (status === "blocked" || String(result.error_code || "").includes("UNAVAILABLE")) return "blocked";
  if (result.success) return "ready";
  return "failed";
}

function workflowMcpServer(status?: FinancialManagerStatus | null): string | undefined {
  const mcp = objectRecord(status?.mcp);
  const servers = Array.isArray(mcp?.servers) ? mcp.servers : [];
  const firstServer = objectRecord(servers[0]);
  return typeof firstServer?.name === "string" ? firstServer.name : undefined;
}

function countEvidenceItems(value: unknown): number | null {
  const record = objectRecord(value);
  const data = record?.data;
  if (Array.isArray(data)) return data.length;
  const dataRecord = objectRecord(data);
  if (Array.isArray(dataRecord?.items)) return dataRecord.items.length;
  if (Array.isArray(dataRecord?.data)) return dataRecord.data.length;
  return null;
}

function genericWorkflowStatus(value: unknown): WorkflowStepStatus {
  const record = objectRecord(value);
  const data = objectRecord(record?.data);
  const success = typeof record?.success === "boolean" ? record.success : typeof data?.success === "boolean" ? data.success : true;
  const errorCode = String(record?.error_code || data?.error_code || "");
  if (!success && (errorCode.includes("UNAVAILABLE") || errorCode.includes("BLOCKED"))) return "blocked";
  return success ? "ready" : "failed";
}

function workflowDetail(step: ReadOnlyWorkflowStep, value: unknown): string {
  if (step.kind === "financial_query") return (value as FinancialManagerQueryResult).error_code || resultDataStatus(value as FinancialManagerQueryResult);
  const itemCount = countEvidenceItems(value);
  if (itemCount !== null) return `${itemCount} 条证据`;
  const record = objectRecord(value);
  const data = objectRecord(record?.data);
  const status = String(data?.status || record?.status || record?.error_code || data?.error_code || "ready");
  if (step.kind === "mcp_resource") return String(data?.uri || step.params?.uri || status);
  if (step.kind === "mcp_prompt") return String(data?.name || step.params?.name || status);
  return status;
}

function workflowToolLabel(step: ReadOnlyWorkflowStep): string {
  const record = objectRecord(step.result);
  return String(record?.tool || step.tool || "待调用");
}

function workflowResult(step: ReadOnlyWorkflowStep, response: unknown): ReadOnlyWorkflowResult {
  const record = objectRecord(response);
  return {
    ...(record || { value: response }),
    tool: String(record?.tool || step.tool),
    evidence: response
  };
}

function availabilityExplanation(reason?: unknown): string {
  const code = String(reason || "");
  if (code === "agent_tool_ready" || code === "agent_mcp_wrapped_tool_ready") return "可运行";
  if (code === "mcp_tool_discovered_but_agent_registry_not_refreshed") return "MCP 工具已发现，但 Agent 工具注册表尚未刷新";
  if (code === "no_financial_mcp_server_registered") return "未发现已注册的金融 MCP server";
  if (code === "mcp_tool_not_discovered") return "金融 MCP server 未提供目标工具";
  if (code === "agent_tool_missing" || code === "action_intent_tool_missing") return "Agent 工具注册表缺少目标工具";
  if (code === "action_intent_ready") return "需要通过 ActionIntent 审批路径执行";
  if (code === "blocked") return "高风险动作已阻断";
  return code || "可用性状态";
}

export function FinancialManagerWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [catalog, setCatalog] = useState<FinancialManagerCatalog | null>(null);
  const [status, setStatus] = useState<FinancialManagerStatus | null>(null);
  const [activeGroup, setActiveGroup] = useState("overview");
  const [selectedKey, setSelectedKey] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [rationale, setRationale] = useState("金融经理台桌面复核");
  const [result, setResult] = useState<FinancialManagerQueryResult | FinancialManagerIntentResult | null>(null);
  const [workflowSteps, setWorkflowSteps] = useState<ReadOnlyWorkflowStep[]>(() => cloneWorkflowSteps());
  const [stockCode, setStockCode] = useState("600519");
  const [includeDecision, setIncludeDecision] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);

  const groups = catalog?.groups || [];
  const actions = catalog?.actions || [];
  const selectedAction = actions.find((item) => actionKey(item) === selectedKey) || null;
  const visibleActions = activeGroup === "overview" ? actions.slice(0, 8) : actions.filter((item) => item.group === activeGroup);
  const selectedAvailability = actionAvailability(selectedAction);
  const resultAvailabilityDetail = resultAvailability(result);
  const isStockAnalysisSelected = isStockAnalysisAction(selectedAction);
  const stockSummary = (isStockAnalysisSelected || result?.capability_id === "stock-analysis") ? stockAnalysisSummary(result) : null;

  function syncStockParams(nextCode: string, nextIncludeDecision: boolean) {
    let current: Record<string, unknown> = {};
    try {
      current = safeJsonParse(paramsText);
    } catch {
      current = {};
    }
    setParamsText(JSON.stringify({ ...current, code: nextCode.trim(), include_decision: nextIncludeDecision }, null, 2));
  }

  function syncStockControlsFromParams(params?: Record<string, unknown> | null) {
    setStockCode(stockCodeFromParams(params));
    setIncludeDecision(boolValue(params?.include_decision));
  }

  function changeParamsText(value: string) {
    setParamsText(value);
    if (!isStockAnalysisSelected) return;
    try {
      const params = safeJsonParse(value);
      setStockCode(stockCodeFromParams(params));
      setIncludeDecision(boolValue(params.include_decision));
    } catch {
      // Keep the quick controls stable while the JSON editor is temporarily invalid.
    }
  }

  function changeStockCode(value: string) {
    setStockCode(value);
    syncStockParams(value, includeDecision);
  }

  function changeIncludeDecision(value: boolean) {
    setIncludeDecision(value);
    syncStockParams(stockCode, value);
  }

  async function refresh() {
    setBusy(true);
    try {
      const [nextCatalog, nextStatus] = await Promise.all([client.financialManagerCatalog(), client.financialManagerStatus()]);
      setCatalog(nextCatalog);
      setStatus(nextStatus);
      const nextAction = nextCatalog.actions.find((item) => item.mode === "read_only" && item.available) || nextCatalog.actions[0];
      if (nextAction && !selectedKey) {
        setSelectedKey(actionKey(nextAction));
        setParamsText(JSON.stringify(nextAction.default_params || {}, null, 2));
        if (isStockAnalysisAction(nextAction)) syncStockControlsFromParams(objectRecord(nextAction.default_params));
      }
      setMessage("FINANCIAL_MANAGER_READY");
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

  function selectAction(action: FinancialManagerAction) {
    setSelectedKey(actionKey(action));
    setParamsText(JSON.stringify(action.default_params || {}, null, 2));
    if (isStockAnalysisAction(action)) syncStockControlsFromParams(objectRecord(action.default_params));
    setResult(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedAction) return;
    if (isStockAnalysisAction(selectedAction) && !stockCode.trim()) {
      setMessage("STOCK_CODE_REQUIRED");
      return;
    }
    setBusy(true);
    try {
      const parsedParams = safeJsonParse(paramsText);
      const params = isStockAnalysisAction(selectedAction)
        ? { ...parsedParams, code: stockCode.trim(), include_decision: includeDecision }
        : parsedParams;
      if (isStockAnalysisAction(selectedAction)) setParamsText(JSON.stringify(params, null, 2));
      const payload = {
        capability_id: selectedAction.capability_id,
        action_id: selectedAction.action_id,
        params
      };
      const response =
        selectedAction.mode === "stateful_intent"
          ? await client.financialManagerIntent({ ...payload, rationale, user_id: userId })
          : await client.financialManagerQuery(payload);
      setResult(response);
      setMessage(response.success ? "FINANCIAL_ACTION_OK" : response.error_code || response.error || "FINANCIAL_ACTION_FAILED");
      if (selectedAction.mode === "stateful_intent") await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function runReadOnlyWorkflow() {
    setWorkflowBusy(true);
    setMessage("FINANCIAL_WORKFLOW_RUNNING");
    setWorkflowSteps(cloneWorkflowSteps().map((step) => ({ ...step, status: "idle", detail: "排队中", result: undefined })));
    try {
      let activeStatus = status;
      if (!catalog || !status) {
        const [nextCatalog, nextStatus] = await Promise.all([client.financialManagerCatalog(), client.financialManagerStatus()]);
        setCatalog(nextCatalog);
        setStatus(nextStatus);
        activeStatus = nextStatus;
      }
      const server = workflowMcpServer(activeStatus);
      const nextSteps = cloneWorkflowSteps();
      for (const step of nextSteps) {
        setWorkflowSteps((current) => current.map((item) => (item.id === step.id ? { ...item, status: "running", detail: "调用 Agent HTTP" } : item)));
        try {
          let response: unknown;
          if (step.kind === "financial_query") {
            response = await client.financialManagerQuery({
              capability_id: step.capability_id || "",
              action_id: step.action_id || "",
              params: step.params
            });
          } else if (step.kind === "session_search") {
            response = await client.search(step.query || "AIASK", { user_id: userId, limit: Number(step.params?.limit || 5) });
          } else if (step.kind === "memory_search") {
            response = await client.memorySearch({ query: step.query || "AIASK", user_id: userId, limit: Number(step.params?.limit || 5) });
          } else if (step.kind === "mcp_resource") {
            response = await client.mcpResourceRead(String(step.params?.uri || "aiask://quotes"), server);
          } else {
            response = await client.mcpPromptGet(String(step.params?.name || "risk-review"), {}, server);
          }
          const normalized = workflowResult(step, response);
          const stepStatus = step.kind === "financial_query" ? workflowStatusFromResult(response as FinancialManagerQueryResult) : genericWorkflowStatus(response);
          const detail = workflowDetail(step, response);
          setWorkflowSteps((current) =>
            current.map((item) => (item.id === step.id ? { ...item, status: stepStatus, detail, result: normalized } : item))
          );
        } catch (error) {
          setWorkflowSteps((current) =>
            current.map((item) => (item.id === step.id ? { ...item, status: "failed", detail: formatApiError(error) } : item))
          );
        }
      }
      setMessage("FINANCIAL_WORKFLOW_DONE");
    } finally {
      setWorkflowBusy(false);
    }
  }

  return (
    <section className="capabilities-workspace financial-manager-workspace">
      <header className="capabilities-header">
        <div>
          <span>金融经理台</span>
          <h1>金融经理台</h1>
          <p>组合、风控、研究、量化、纸上交易和券商只读连接统一进入 Agent 安全网关。</p>
        </div>
        <div className="button-row">
          <StatusBadge status={status?.status || message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="diagnostics-summary wide">
            <MetricCard label="就绪动作" value={catalog?.summary?.ready ?? 0} status="ready" />
            <MetricCard label="审批意图" value={catalog?.summary?.intent_ready ?? 0} status="partial" />
            <MetricCard label="已阻断" value={catalog?.summary?.blocked ?? 0} status="blocked" />
            <MetricCard label="实盘交易" value={status?.broker?.live_trading_enabled ? "enabled" : "disabled"} status="not_required" />
          </div>

          <div className="financial-manager-grid">
            <aside className="financial-manager-side">
              <button className={activeGroup === "overview" ? "active" : ""} onClick={() => setActiveGroup("overview")} type="button">
                <Landmark size={16} />
                总览
              </button>
              {groups
                .filter((group) => group.id !== "overview")
                .map((group) => (
                  <button className={activeGroup === group.id ? "active" : ""} key={group.id} onClick={() => setActiveGroup(group.id)} type="button">
                    <BriefcaseBusiness size={16} />
                    {groupLabel(group, group.id)}
                  </button>
                ))}
            </aside>

            <section className="financial-manager-main">
              {activeGroup === "overview" && (
                <>
                  <div className="capability-section">
                    <div className="section-header">
                      <div>
                        <span>安全边界</span>
                        <h3>只读查询 + ActionIntent</h3>
                      </div>
                      <ShieldCheck size={18} />
                    </div>
                    <div className="notice warn">
                      <AlertTriangle size={14} />
                      真实实盘下单和撤单在 V1 中固定禁用；券商区域只展示账户、持仓、订单、成交等只读查询。
                    </div>
                    <RawEvidencePanel title="安全边界 JSON" value={{ safety: catalog?.safety, broker: status?.broker, mcp: status?.mcp }} />
                  </div>

                  <section className="capability-section financial-workflow-panel">
                    <div className="section-header">
                      <div>
                        <span>只读证据链</span>
                        <h3>金融 Agent 只读工作流</h3>
                      </div>
                      <button className="small-button" disabled={busy || workflowBusy} onClick={runReadOnlyWorkflow} type="button">
                        <Workflow size={15} />
                        运行只读工作流
                      </button>
                    </div>
                    <div className="financial-workflow-steps">
                      {workflowSteps.map((step, index) => (
                        <article className={`financial-workflow-step ${step.status}`} key={step.id}>
                          <div className="financial-workflow-step-head">
                            <span>{index + 1}</span>
                            <div>
                              <strong>{step.label}</strong>
                              <small>{step.capability_id && step.action_id ? `${step.capability_id} / ${step.action_id}` : step.kind}</small>
                            </div>
                            <StatusBadge status={step.status} />
                          </div>
                          <dl>
                            <div>
                              <dt>接口</dt>
                              <dd>{step.endpoint}</dd>
                            </div>
                            <div>
                              <dt>工具</dt>
                              <dd>{step.result ? workflowToolLabel(step) : "待调用"}</dd>
                            </div>
                            <div>
                              <dt>副作用级别</dt>
                              <dd>{sideEffectLevel(step.result)}</dd>
                            </div>
                            <div>
                              <dt>结果</dt>
                              <dd>{step.detail}</dd>
                            </div>
                          </dl>
                          {step.result && <RawEvidencePanel title={`${step.label} JSON`} value={step.result} />}
                        </article>
                      ))}
                    </div>
                  </section>
                </>
              )}

              <div className="financial-action-list">
                {visibleActions.map((action) => (
                  <button className={selectedKey === actionKey(action) ? "active" : ""} key={actionKey(action)} onClick={() => selectAction(action)} type="button">
                    <div>
                      <strong>{actionLabel(action)}</strong>
                      <span>{action.capability_id} / {action.action_id}</span>
                    </div>
                    <StatusBadge status={action.status || action.mode} label={modeLabel(action.mode)} />
                  </button>
                ))}
              </div>

              <form className="financial-action-runner" onSubmit={submit}>
                <div className="section-header">
                  <div>
                    <span>{selectedAction ? `${selectedAction.capability_id}.${selectedAction.action_id}` : "未选择"}</span>
                    <h3>{actionLabel(selectedAction)}</h3>
                  </div>
                  <StatusBadge status={selectedAction?.status || "not_loaded"} />
                </div>
                {isStockAnalysisSelected && (
                  <div className="stock-analysis-runner">
                    <label className="field-row">
                      <span>证券代码</span>
                      <input
                        aria-label="stock analysis code"
                        placeholder="600519"
                        value={stockCode}
                        onChange={(event) => changeStockCode(event.target.value)}
                      />
                    </label>
                    <label className="stock-analysis-toggle">
                      <input
                        aria-label="include stock decision"
                        checked={includeDecision}
                        type="checkbox"
                        onChange={(event) => changeIncludeDecision(event.target.checked)}
                      />
                      <span>包含决策辅助</span>
                    </label>
                    <div className="stock-analysis-route">
                      <StatusBadge status="read_only" label="只读" />
                      <code>agent_analyze_stock</code>
                      <code>/v1/desktop/financial-manager/query</code>
                    </div>
                  </div>
                )}
                <textarea aria-label="financial action params" value={paramsText} onChange={(event) => changeParamsText(event.target.value)} rows={8} />
                {selectedAvailability && (
                  <div className="notice">
                    <strong>{availabilityExplanation(selectedAvailability.reason_code)} ({String(selectedAvailability.reason_code || selectedAction?.status || "availability")})</strong>
                    <span>{compact(selectedAvailability)}</span>
                  </div>
                )}
                {selectedAction?.mode === "stateful_intent" && (
                  <input aria-label="financial action rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
                )}
                <button className="primary-button" disabled={busy || !selectedAction || selectedAction.mode === "blocked"} type="submit">
                  {selectedAction?.mode === "stateful_intent" ? <ShieldCheck size={15} /> : <Play size={15} />}
                  {selectedAction?.mode === "stateful_intent" ? "创建意图" : "运行查询"}
                </button>
                {selectedAction?.mode === "blocked" && (
                  <GatedState
                    reason={selectedAction.blocked_reason || "该动作在当前版本禁用。"}
                    status="blocked"
                    title="动作已阻断"
                  />
                )}
              </form>

              <section className="capability-section">
                <div className="section-header">
                  <div>
                    <span>{message}</span>
                    <h3>结果</h3>
                  </div>
                  <BarChart3 size={18} />
                </div>
                {resultAvailabilityDetail && (
                  <div className="notice warn">
                    <strong>{availabilityExplanation(resultAvailabilityDetail.reason_code)} ({String(resultAvailabilityDetail.reason_code || result?.error_code || "availability")})</strong>
                    <span>{compact(resultAvailabilityDetail)}</span>
                  </div>
                )}
                {stockSummary && (
                  <div className="stock-analysis-summary" aria-label="stock analysis summary">
                    <MetricCard label="代码" value={stockSummary.code} status={stockSummary.status} />
                    <MetricCard label="评级" value={stockSummary.rating} status={stockSummary.status} />
                    <MetricCard label="风险" value={stockSummary.risk} status={stockSummary.risk} />
                    <MetricCard label="决策" value={stockSummary.decision} status={stockSummary.status} />
                    <div className="stock-analysis-tool">
                      <Search size={15} />
                      <span>{stockSummary.tool}</span>
                    </div>
                  </div>
                )}
                <RawEvidencePanel title="动作结果 JSON" value={result || { status: message, selected: selectedAction ? compact(selectedAction) : null }} />
              </section>
            </section>
          </div>
        </div>
      </div>
    </section>
  );
}
