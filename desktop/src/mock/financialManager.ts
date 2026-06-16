import type { CapabilityWorkbenchPayload } from "../types";

type FinancialManagerAction = {
  capability_id: string;
  action_id: string;
  group: string;
  label: string;
  mode: string;
  status: string;
  available: boolean;
  tool?: string;
  intent_action?: string;
  mcp_tool?: string;
  blocked_reason?: string;
  default_params?: Record<string, unknown>;
};

function findFinancialManagerAction(body: Record<string, unknown>): FinancialManagerAction | undefined {
  return mockFinancialManagerCatalog().actions.find((item) => item.capability_id === body.capability_id && item.action_id === body.action_id);
}

function bodyParams(body: Record<string, unknown>): Record<string, unknown> {
  return body.params && typeof body.params === "object" && !Array.isArray(body.params)
    ? body.params as Record<string, unknown>
    : {};
}

export function mockFinancialManagerCatalog() {
  const groups = [
    { id: "overview", label: "总览", description: "准备度与安全状态" },
    { id: "market-research", label: "市场与研究", description: "个股、研究、板块、情绪、技术面和期权" },
    { id: "portfolio-watchlist", label: "组合与自选", description: "组合与自选只读查询，以及审批意图" },
    { id: "risk-performance", label: "风险与绩效", description: "风险、VaR、暴露、归因和决策支持" },
    { id: "quant-backtest", label: "量化与回测", description: "量化研究和回测套件" },
    { id: "paper-execution", label: "纸上交易与执行", description: "纸上交易和执行计划" },
    { id: "broker-readonly", label: "券商只读", description: "仅查询券商账户和订单" }
  ];
  const actions: FinancialManagerAction[] = [
    { capability_id: "stock-analysis", action_id: "analyze_stock", group: "market-research", label: "个股分析", mode: "read_only", status: "ready", available: true, tool: "agent_analyze_stock", default_params: { code: "600519", include_decision: false } },
    { capability_id: "portfolio", action_id: "risk", group: "risk-performance", label: "组合风险", mode: "read_only", status: "ready", available: true, tool: "agent_portfolio_risk", default_params: { codes: ["600519", "000001"], weights: [0.5, 0.5] } },
    { capability_id: "quant", action_id: "data_gate", group: "quant-backtest", label: "量化数据门禁", mode: "read_only", status: "ready", available: true, tool: "agent_quant_data_gate", default_params: { codes: ["600519"], max_stale_days: 5 } },
    { capability_id: "backtest", action_id: "suite", group: "quant-backtest", label: "回测套件", mode: "read_only", status: "ready", available: true, tool: "agent_backtest_suite", default_params: { codes: ["600519"], strategy: "ma_cross" } },
    { capability_id: "portfolio", action_id: "create", group: "portfolio-watchlist", label: "创建组合意图", mode: "stateful_intent", status: "intent_ready", available: true, intent_action: "portfolio_manager.create", default_params: { name: "Desktop portfolio" } },
    { capability_id: "watchlist", action_id: "add", group: "portfolio-watchlist", label: "添加自选股意图", mode: "stateful_intent", status: "intent_ready", available: true, intent_action: "watchlist_manager.add", default_params: { group: "default", code: "600519" } },
    { capability_id: "paper", action_id: "submit_order", group: "paper-execution", label: "纸上交易下单意图", mode: "stateful_intent", status: "intent_ready", available: true, intent_action: "paper_trading_manager.submit_order", default_params: { code: "600519", side: "buy", quantity: 100, dry_run: true } },
    { capability_id: "broker-ths", action_id: "positions", group: "broker-readonly", label: "同花顺持仓只读", mode: "read_only", status: "missing_mcp_tool", available: false, mcp_tool: "ths_query_position", default_params: {} },
    { capability_id: "broker-live", action_id: "place_order", group: "broker-readonly", label: "实盘下单", mode: "blocked", status: "blocked", available: false, blocked_reason: "金融经理台 V1 固定禁用实盘券商下单。" }
  ];
  return {
    object: "aiask.desktop.financial_manager.catalog",
    groups,
    actions,
    summary: { ready: 4, intent_ready: 3, missing_mcp_tool: 1, blocked: 1 },
    safety: { mode: "read_only_plus_intents", live_trading_enabled: false, stateful_execution: "action_intent_only", secrets_redacted: true },
    secrets_redacted: true
  };
}

export function mockFinancialManagerStatus(capabilities: CapabilityWorkbenchPayload, recentIntents: Record<string, unknown>[]) {
  return {
    object: "aiask.desktop.financial_manager.status",
    status: "ready",
    readiness: capabilities.financial_system,
    catalog_summary: mockFinancialManagerCatalog().summary,
    mcp: { registration: capabilities.mcp.registration_status, servers: capabilities.mcp.servers },
    broker: { live_trading_enabled: false, read_only_surfaces: ["ths_query_position", "qmt_query_account"], blocked_actions: ["ths_place_order", "qmt_place_order"] },
    recent_intents: recentIntents,
    secrets_redacted: true
  };
}

export function mockFinancialManagerQuery(body: Record<string, unknown>) {
  const action = findFinancialManagerAction(body);
  if (action?.mode === "blocked") return { object: "aiask.desktop.financial_manager.query", success: false, data: { reason: action.blocked_reason }, error: action.blocked_reason, error_code: "FINANCIAL_ACTION_BLOCKED", secrets_redacted: true };
  if (action?.mode === "stateful_intent") return { object: "aiask.desktop.financial_manager.query", success: false, data: { required_endpoint: "/v1/desktop/financial-manager/intent" }, error: "stateful financial actions must be created as ActionIntent", error_code: "FINANCIAL_ACTION_REQUIRES_INTENT", secrets_redacted: true };
  if (body.capability_id === "stock-analysis" && body.action_id === "analyze_stock") {
    const params = bodyParams(body);
    const code = String(params.code || params.stock_code || params.symbol || "600519");
    return {
      object: "aiask.desktop.financial_manager.query",
      capability_id: body.capability_id,
      action_id: body.action_id,
      tool: "agent_analyze_stock",
      success: true,
      data: {
        status: "ready",
        code,
        rating: "mock_watch",
        risk: "medium",
        decision: params.include_decision ? "observe_only" : "not_requested",
        analysis: {
          signal: "watch",
          confidence: 0.72,
          data_source: "desktop.mockApi",
          investment_advice: false
        }
      },
      error: null,
      meta: { side_effect: { level: "read_only", target: "agent_analyze_stock", confirmation_required: false, idempotent: true } },
      secrets_redacted: true
    };
  }
  if (body.capability_id === "portfolio" && body.action_id === "risk") {
    return {
      object: "aiask.desktop.financial_manager.query",
      capability_id: body.capability_id,
      action_id: body.action_id,
      tool: "agent_portfolio_risk",
      success: true,
      data: {
        status: "ready",
        params: body.params || action?.default_params || {},
        portfolio_risk: { var_95: -0.021, stress: "passed", concentration: "medium" }
      },
      error: null,
      meta: { side_effect: { level: "read_only", target: "agent_portfolio_risk", confirmation_required: false, idempotent: true } },
      secrets_redacted: true
    };
  }
  if (body.capability_id === "quant" && body.action_id === "data_gate") {
    const params = bodyParams(body);
    return {
      object: "aiask.desktop.financial_manager.query",
      capability_id: body.capability_id,
      action_id: body.action_id,
      tool: "agent_quant_data_gate",
      success: true,
      data: {
        status: "ready",
        ready: true,
        codes: Array.isArray(params.codes) ? params.codes : ["600519", "000001"],
        max_stale_days: params.max_stale_days || 5,
        coverage: { requested: 2, missing_count: 0, stale_count: 0 },
        blocking_reason: null
      },
      error: null,
      meta: { side_effect: { level: "read_only", target: "agent_quant_data_gate", confirmation_required: false, idempotent: true } },
      secrets_redacted: true
    };
  }
  return {
    object: "aiask.desktop.financial_manager.query",
    capability_id: body.capability_id,
    action_id: body.action_id,
    tool: action?.tool || "mock_tool",
    success: true,
    data: { status: "ready", params: body.params || action?.default_params || {}, rows: [{ code: "600519", signal: "watch", risk: "medium" }] },
    error: null,
    meta: { side_effect: { level: "read_only", confirmation_required: false } },
    secrets_redacted: true
  };
}

export function mockFinancialManagerIntent(body: Record<string, unknown>, registerIntent: (id: string, intent: Record<string, unknown>) => void) {
  const action = findFinancialManagerAction(body);
  if (action?.mode === "blocked") return { object: "aiask.desktop.financial_manager.intent", success: false, data: { reason: action.blocked_reason }, error: action.blocked_reason, error_code: "FINANCIAL_ACTION_BLOCKED", secrets_redacted: true };
  const intent = {
    intent_id: `intent_fin_${Date.now()}`,
    action: action?.intent_action || "financial_manager.mock",
    target_tool: "financial_manager",
    target_action: action?.intent_action || "mock",
    status: "awaiting_confirmation",
    params: body.params || action?.default_params || {},
    rationale: body.rationale || "金融经理台 mock 意图"
  };
  registerIntent(intent.intent_id, intent);
  return {
    object: "aiask.desktop.financial_manager.intent",
    capability_id: body.capability_id,
    action_id: body.action_id,
    success: true,
    data: { intent },
    error: null,
    meta: { side_effect: { level: "stateful", confirmation_required: true } },
    secrets_redacted: true
  };
}
