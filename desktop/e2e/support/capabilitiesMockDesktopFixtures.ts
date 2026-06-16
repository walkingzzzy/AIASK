export function connectorsSummaryPayload() {
  return {
    data: {
      total: 5,
      connected: 3,
      configured: 4,
      by_type: {
        financial: { count: 2, connected: 2 },
        platform: { count: 1, connected: 0 },
        mcp: { count: 1, connected: 1 },
        plugin: { count: 1, connected: 0 }
      },
      connectors: [
        {
          id: "akshare",
          name: "AKShare MCP",
          type: "financial",
          category: "data",
          enabled: true,
          configured: true,
          connected: true,
          status: "ready",
          description: "Mock AKShare data connector",
          metadata: { tools_read: ["quote"] }
        },
        {
          id: "financial:tongdaxin",
          name: "tongdaxin",
          type: "financial",
          category: "data",
          enabled: true,
          configured: true,
          connected: true,
          status: "ready",
          description: "Mock Tongdaxin market connector",
          metadata: { tools_read: ["quote"], wizard: "financial:tongdaxin" }
        },
        {
          id: "feishu",
          name: "Feishu",
          type: "platform",
          category: "communication",
          enabled: true,
          configured: false,
          connected: false,
          status: "auth_missing",
          description: "Mock messaging connector",
          missing_env: ["FEISHU_APP_ID"]
        },
        {
          id: "finance-demo",
          name: "finance-demo",
          type: "mcp",
          category: "tool",
          enabled: true,
          configured: true,
          connected: true,
          status: "connected",
          description: "Mock MCP server"
        },
        {
          id: "audit-plugin",
          name: "Audit plugin",
          type: "plugin",
          category: "tool",
          enabled: false,
          configured: true,
          connected: false,
          status: "disabled",
          description: "Mock plugin connector"
        }
      ]
    }
  };
}

export function connectorFixtureList() {
  const summary = connectorsSummaryPayload().data as { connectors: Array<Record<string, unknown>> };
  return summary.connectors;
}

export function connectorFixture(type: string, name: string) {
  return connectorFixtureList().find((connector) => {
    const connectorType = String(connector.type || "");
    const connectorId = String(connector.id || "");
    const connectorName = String(connector.name || "");
    return connectorType === type && (connectorId === name || connectorName === name);
  });
}

export function workbenchSummaryPayload() {
  return {
    recent_sessions: [
      {
        session_id: "session_fixture",
        title: "E2E session",
        user_id: "local-e2e",
        created_at: "2026-05-21T07:59:00.000Z",
        last_message_at: "2026-05-21T08:00:00.000Z",
        last_run_id: "run_fixture",
        message_count: 2,
        status: "completed"
      }
    ],
    recent_runs: [
      {
        run_id: "run_fixture",
        session_id: "session_fixture",
        status: "completed",
        created_at: "2026-05-21T08:00:00.000Z",
        updated_at: "2026-05-21T08:00:03.000Z",
        event_count: 5,
        tool_call_count: 0,
        approval_count: 0,
        error_count: 0
      }
    ],
    queues: {
      pending_intents: 1,
      pending_approvals: 1,
      gateway_failed: 1,
      mcp_degraded: 0
    },
    access: {
      full_mode_active: true,
      control_token_configured: true,
      sessions_admin_available: true
    }
  };
}

export function financialManagerCatalogPayload() {
  return {
    object: "aiask.desktop.financial_manager.catalog",
    groups: [
      { id: "overview", label: "总览", description: "准备度和安全状态" },
      { id: "market-research", label: "市场与研究", description: "个股分析和研究读取" },
      { id: "risk-performance", label: "风险与绩效", description: "风险和数据准备度" },
      { id: "portfolio-watchlist", label: "组合与自选", description: "组合读取和审批意图" },
      { id: "broker-readonly", label: "券商只读", description: "券商只读查询" }
    ],
    actions: [
      {
        capability_id: "portfolio",
        action_id: "risk",
        group: "risk-performance",
        label: "组合风险",
        mode: "read_only",
        status: "ready",
        available: true,
        tool: "agent_portfolio_risk",
        default_params: { codes: ["600519", "000001"], weights: [0.5, 0.5] },
        availability: { reason_code: "agent_tool_ready", required_tool: "agent_portfolio_risk", agent_registry_has_tool: true }
      },
      {
        capability_id: "stock-analysis",
        action_id: "analyze_stock",
        group: "market-research",
        label: "个股分析",
        mode: "read_only",
        status: "ready",
        available: true,
        tool: "agent_analyze_stock",
        default_params: { code: "600519", include_decision: false },
        availability: { reason_code: "agent_tool_ready", required_tool: "agent_analyze_stock", agent_registry_has_tool: true }
      },
      {
        capability_id: "quant",
        action_id: "data_gate",
        group: "risk-performance",
        label: "量化数据门禁",
        mode: "read_only",
        status: "ready",
        available: true,
        tool: "agent_quant_data_gate",
        default_params: { codes: ["600519", "000001"], max_stale_days: 5 },
        availability: { reason_code: "agent_tool_ready", required_tool: "agent_quant_data_gate", agent_registry_has_tool: true }
      },
      {
        capability_id: "portfolio",
        action_id: "create",
        group: "portfolio-watchlist",
        label: "创建组合意图",
        mode: "stateful_intent",
        status: "intent_ready",
        available: true,
        intent_action: "portfolio_manager.create",
        default_params: { name: "Desktop portfolio" }
      },
      {
        capability_id: "broker-live",
        action_id: "place_order",
        group: "broker-readonly",
        label: "实盘下单",
        mode: "blocked",
        status: "blocked",
        available: false,
        blocked_reason: "金融经理台 V1 固定禁用实盘券商下单。"
      }
    ],
    summary: { ready: 3, intent_ready: 1, blocked: 1 },
    safety: { mode: "read_only_plus_intents", live_trading_enabled: false, stateful_execution: "action_intent_only", secrets_redacted: true },
    secrets_redacted: true
  };
}

export const brokerProfileFixture = {
  broker_profile_id: "broker_profile_e2e_qmt",
  user_id: "local",
  provider: "qmt",
  display_name: "QMT / MiniQMT",
  account_ref_hash: "broker_hash_e2e",
  market: "cn_a",
  read_only_enabled: true,
  write_enabled: false,
  consent_status: "granted",
  last_sync_at: "2026-06-12T00:00:00.000Z",
  status: "ready",
  error_code: null
};

export const brokerAccountsFixture = [
  {
    snapshot_id: "broker_account_e2e_1",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    account_ref_hash: brokerProfileFixture.account_ref_hash,
    currency: "CNY",
    total_asset: 100000,
    cash_available: 12000,
    market_value: 88000,
    frozen_cash: 0,
    buying_power: 12000,
    observed_at: "2026-06-12T00:00:00.000Z",
    created_at: "2026-06-12T00:00:00.000Z"
  }
];

export const brokerPositionsFixture = [
  {
    snapshot_id: "broker_position_e2e_1",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    symbol: "600519",
    exchange: "SH",
    name: "Kweichow Moutai",
    quantity: 100,
    available_quantity: 100,
    cost_basis: 420,
    last_price: 450,
    market_value: 45000,
    unrealized_pnl: 3000,
    unrealized_pnl_pct: 0.0714,
    observed_at: "2026-06-12T00:00:00.000Z"
  },
  {
    snapshot_id: "broker_position_e2e_2",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    symbol: "000001",
    exchange: "SZ",
    name: "Ping An Bank",
    quantity: 1000,
    available_quantity: 1000,
    cost_basis: 43.8,
    last_price: 43,
    market_value: 43000,
    unrealized_pnl: -800,
    unrealized_pnl_pct: -0.0183,
    observed_at: "2026-06-12T00:00:00.000Z"
  }
];

export const brokerOrdersFixture = [
  {
    snapshot_id: "broker_order_e2e_1",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    order_ref_hash: "broker_order_hash_e2e_1",
    symbol: "600519",
    side: "buy",
    order_type: "limit",
    price: 450,
    quantity: 100,
    filled_quantity: 100,
    status: "filled",
    submitted_at: "2026-06-12T09:35:00+08:00",
    observed_at: "2026-06-12T00:00:00.000Z"
  }
];

export const brokerDealsFixture = [
  {
    snapshot_id: "broker_deal_e2e_1",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    deal_ref_hash: "broker_deal_hash_e2e_1",
    order_ref_hash: "broker_order_hash_e2e_1",
    symbol: "600519",
    side: "buy",
    price: 450,
    quantity: 100,
    amount: 45000,
    fee: 12,
    occurred_at: "2026-06-12T09:36:00+08:00",
    observed_at: "2026-06-12T00:00:00.000Z"
  }
];

export function brokerAnalyticsFixture() {
  return {
    analytics_id: "broker_analytics_e2e_qmt",
    broker_profile_id: brokerProfileFixture.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    period_start: null,
    period_end: null,
    metrics: {
      account_count: brokerAccountsFixture.length,
      position_count: brokerPositionsFixture.length,
      order_count: brokerOrdersFixture.length,
      deal_count: brokerDealsFixture.length,
      total_asset: 100000,
      cash_available: 12000,
      market_value: 88000,
      cash_ratio: 0.12,
      top_position_concentration: 0.5114,
      top_positions: [
        { symbol: "600519", name: "Kweichow Moutai", market_value: 45000, position_pct: 0.5114 },
        { symbol: "000001", name: "Ping An Bank", market_value: 43000, position_pct: 0.4886 }
      ],
      trade_count: 1,
      buy_count: 1,
      sell_count: 0,
      buy_sell_imbalance: 1,
      deal_amount_total: 45000
    },
    signals: {
      limitations: ["historical account snapshots are insufficient for drawdown analytics"],
      generated_at: "2026-06-12T00:00:00.000Z"
    },
    risk_flags: [{ code: "HIGH_SINGLE_POSITION_CONCENTRATION", severity: "warning", value: 0.5114 }],
    source_snapshot_ids: {
      accounts: ["broker_account_e2e_1"],
      positions: ["broker_position_e2e_1", "broker_position_e2e_2"],
      orders: ["broker_order_e2e_1"],
      deals: ["broker_deal_e2e_1"]
    },
    model_version: "deterministic-e2e",
    created_at: "2026-06-12T00:00:00.000Z"
  };
}

export function brokerSnapshotPayload() {
  return {
    object: "aiask.desktop.broker_readonly",
    success: true,
    data: {
      profiles: [brokerProfileFixture],
      accounts: brokerAccountsFixture,
      positions: brokerPositionsFixture,
      orders: brokerOrdersFixture,
      deals: brokerDealsFixture,
      analytics: brokerAnalyticsFixture()
    },
    error: null,
    read_only: true,
    live_trading_enabled: false,
    secrets_redacted: true,
    source_chain: ["desktop.e2e.fixture", "aiask_agent.broker_readonly"],
    generated_at: 1781193600
  };
}

export function brokerReadinessPayload() {
  return {
    object: "aiask.desktop.broker_readiness",
    status: "ready",
    connectors: [
      {
        provider: "qmt",
        configured: true,
        ready: true,
        read_only: true,
        live_trading_enabled: false,
        required_env: [],
        missing_env: [],
        optional_env: [],
        required_tools: ["qmt_query_account", "qmt_query_position", "qmt_query_orders"],
        missing_tools: []
      },
      {
        provider: "ths",
        configured: false,
        ready: false,
        read_only: true,
        live_trading_enabled: false,
        required_env: ["THS_MCP_SERVER"],
        missing_env: ["THS_MCP_SERVER"],
        optional_env: [],
        required_tools: ["ths_query_position"],
        missing_tools: ["ths_query_position"]
      }
    ],
    mcp: { registration: "registered", servers: [{ name: "finance-demo", domain: "financial" }] },
    latest_analytics: brokerAnalyticsFixture(),
    live_trading_enabled: false,
    read_only: true,
    secrets_redacted: true
  };
}

export function financialManagerQueryPayload(body: Record<string, unknown>) {
  const capabilityId = String(body.capability_id || "");
  const actionId = String(body.action_id || "");
  if (capabilityId === "stock-analysis" && actionId === "analyze_stock") {
    const params = typeof body.params === "object" && body.params && !Array.isArray(body.params)
      ? body.params as Record<string, unknown>
      : {};
    const code = String(params.code || params.stock_code || params.symbol || "600519");
    return {
      object: "aiask.desktop.financial_manager.query",
      capability_id: capabilityId,
      action_id: actionId,
      tool: "agent_analyze_stock",
      success: true,
      data: {
        status: "ready",
        code,
        rating: "mock_watch",
        risk: "medium",
        decision: params.include_decision ? "observe_only" : "not_requested",
        analysis: { signal: "watch", confidence: 0.72, investment_advice: false }
      },
      error: null,
      meta: { side_effect: { level: "read_only", target: "agent_analyze_stock", confirmation_required: false, idempotent: true } },
      secrets_redacted: true
    };
  }
  if (capabilityId === "quant" && actionId === "data_gate") {
    return {
      object: "aiask.desktop.financial_manager.query",
      capability_id: capabilityId,
      action_id: actionId,
      tool: "agent_quant_data_gate",
      success: true,
      data: {
        status: "ready",
        ready: true,
        codes: ["600519", "000001"],
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
    capability_id: capabilityId || "portfolio",
    action_id: actionId || "risk",
    tool: "agent_portfolio_risk",
    success: true,
    data: {
      status: "ready",
      portfolio_risk: { var_95: -0.021, stress: "passed", concentration: "medium" }
    },
    error: null,
    meta: { side_effect: { level: "read_only", target: "agent_portfolio_risk", confirmation_required: false, idempotent: true } },
    secrets_redacted: true
  };
}

export function runEventsPayload() {
  return {
    object: "list",
    data: [
      { id: "evt_1", kind: "system", event: "run.started", title: "run.started", run_id: "run_fixture", created_at: "2026-05-21T08:00:00.000Z", status: "started" },
      { id: "evt_2", kind: "system", event: "model.started", title: "model.started", run_id: "run_fixture", created_at: "2026-05-21T08:00:01.000Z" },
      { id: "evt_3", kind: "system", event: "model.completed", title: "model.completed", run_id: "run_fixture", created_at: "2026-05-21T08:00:02.000Z" },
      { id: "evt_4", kind: "system", event: "model.delta", title: "model.delta", run_id: "run_fixture", created_at: "2026-05-21T08:00:02.500Z", data: { content: "AIASK_OK" } },
      { id: "evt_5", kind: "system", event: "run.completed", title: "run.completed", run_id: "run_fixture", created_at: "2026-05-21T08:00:03.000Z", status: "completed" }
    ]
  };
}
