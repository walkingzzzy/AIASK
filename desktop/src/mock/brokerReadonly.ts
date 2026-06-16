const mockBrokerProfile = {
  broker_profile_id: "broker_profile_mock_qmt",
  user_id: "local",
  provider: "qmt",
  display_name: "QMT / MiniQMT",
  account_ref_hash: "mock_hash_3f7c2a81",
  market: "cn_a",
  read_only_enabled: true,
  write_enabled: false,
  consent_status: "granted",
  last_sync_at: "2026-06-12T00:00:00Z",
  status: "ready",
  error_code: null
};

const mockThsBrokerProfile = {
  ...mockBrokerProfile,
  broker_profile_id: "broker_profile_mock_ths",
  provider: "tonghuashun",
  display_name: "同花顺",
  account_ref_hash: "mock_ths_hash_91c6b4d0"
};

const mockBrokerAccounts = [
  {
    snapshot_id: "broker_account_mock_1",
    broker_profile_id: mockBrokerProfile.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    account_ref_hash: mockBrokerProfile.account_ref_hash,
    currency: "CNY",
    total_asset: 100000,
    cash_available: 12000,
    market_value: 88000,
    frozen_cash: 0,
    buying_power: 12000,
    observed_at: "2026-06-12T00:00:00Z",
    created_at: "2026-06-12T00:00:00Z"
  }
];

const mockThsBrokerAccounts = [
  {
    ...mockBrokerAccounts[0],
    snapshot_id: "broker_account_mock_ths_1",
    broker_profile_id: mockThsBrokerProfile.broker_profile_id,
    provider: "tonghuashun",
    account_ref_hash: mockThsBrokerProfile.account_ref_hash,
    total_asset: 86000,
    cash_available: 24000,
    market_value: 62000,
    buying_power: 24000
  }
];

const mockBrokerPositions = [
  {
    snapshot_id: "broker_position_mock_1",
    broker_profile_id: mockBrokerProfile.broker_profile_id,
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
    observed_at: "2026-06-12T00:00:00Z"
  },
  {
    snapshot_id: "broker_position_mock_2",
    broker_profile_id: mockBrokerProfile.broker_profile_id,
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
    observed_at: "2026-06-12T00:00:00Z"
  }
];

const mockThsBrokerPositions = [
  {
    ...mockBrokerPositions[0],
    snapshot_id: "broker_position_mock_ths_1",
    broker_profile_id: mockThsBrokerProfile.broker_profile_id,
    provider: "tonghuashun",
    symbol: "300750",
    exchange: "SZ",
    name: "CATL",
    quantity: 200,
    available_quantity: 200,
    cost_basis: 210,
    last_price: 220,
    market_value: 44000,
    unrealized_pnl: 2000,
    unrealized_pnl_pct: 0.0476
  },
  {
    ...mockBrokerPositions[1],
    snapshot_id: "broker_position_mock_ths_2",
    broker_profile_id: mockThsBrokerProfile.broker_profile_id,
    provider: "tonghuashun",
    symbol: "600036",
    exchange: "SH",
    name: "CMB",
    quantity: 600,
    cost_basis: 30,
    last_price: 30,
    market_value: 18000,
    unrealized_pnl: 0,
    unrealized_pnl_pct: 0
  }
];

const mockBrokerOrders = [
  {
    snapshot_id: "broker_order_mock_1",
    broker_profile_id: mockBrokerProfile.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    order_ref_hash: "mock_order_hash_1",
    symbol: "600519",
    side: "buy",
    order_type: "limit",
    price: 450,
    quantity: 100,
    filled_quantity: 100,
    status: "filled",
    submitted_at: "2026-06-12T09:35:00+08:00",
    observed_at: "2026-06-12T00:00:00Z"
  }
];

const mockThsBrokerOrders = [
  {
    ...mockBrokerOrders[0],
    snapshot_id: "broker_order_mock_ths_1",
    broker_profile_id: mockThsBrokerProfile.broker_profile_id,
    provider: "tonghuashun",
    order_ref_hash: "mock_ths_order_hash_1",
    symbol: "300750",
    side: "sell",
    price: 220,
    quantity: 100,
    filled_quantity: 100
  }
];

const mockBrokerDeals = [
  {
    snapshot_id: "broker_deal_mock_1",
    broker_profile_id: mockBrokerProfile.broker_profile_id,
    user_id: "local",
    provider: "qmt",
    deal_ref_hash: "mock_deal_hash_1",
    order_ref_hash: "mock_order_hash_1",
    symbol: "600519",
    side: "buy",
    price: 450,
    quantity: 100,
    amount: 45000,
    fee: 12,
    occurred_at: "2026-06-12T09:36:00+08:00",
    observed_at: "2026-06-12T00:00:00Z"
  }
];

const mockThsBrokerDeals = [
  {
    ...mockBrokerDeals[0],
    snapshot_id: "broker_deal_mock_ths_1",
    broker_profile_id: mockThsBrokerProfile.broker_profile_id,
    provider: "tonghuashun",
    deal_ref_hash: "mock_ths_deal_hash_1",
    order_ref_hash: "mock_ths_order_hash_1",
    symbol: "300750",
    side: "sell",
    price: 220,
    quantity: 100,
    amount: 22000
  }
];

function isThsProvider(provider = "qmt") {
  return provider === "tonghuashun" || provider === "ths";
}

function brokerRows(provider = "qmt") {
  const isThs = isThsProvider(provider);
  return {
    isThs,
    profile: isThs ? mockThsBrokerProfile : mockBrokerProfile,
    accounts: isThs ? mockThsBrokerAccounts : mockBrokerAccounts,
    positions: isThs ? mockThsBrokerPositions : mockBrokerPositions,
    orders: isThs ? mockThsBrokerOrders : mockBrokerOrders,
    deals: isThs ? mockThsBrokerDeals : mockBrokerDeals
  };
}

export function mockBrokerAnalytics(provider = "qmt") {
  const rows = brokerRows(provider);
  const totalAsset = rows.isThs ? 86000 : 100000;
  const cashAvailable = rows.isThs ? 24000 : 12000;
  const marketValue = rows.isThs ? 62000 : 88000;
  const topPositions = rows.isThs
    ? [
        { symbol: "300750", name: "CATL", market_value: 44000, position_pct: 0.7097 },
        { symbol: "600036", name: "CMB", market_value: 18000, position_pct: 0.2903 }
      ]
    : [
        { symbol: "600519", name: "Kweichow Moutai", market_value: 45000, position_pct: 0.5114 },
        { symbol: "000001", name: "Ping An Bank", market_value: 43000, position_pct: 0.4886 }
      ];
  return {
    analytics_id: rows.isThs ? "broker_analytics_mock_ths" : "broker_analytics_mock_qmt",
    broker_profile_id: rows.profile.broker_profile_id,
    user_id: "local",
    provider: rows.profile.provider,
    period_start: null,
    period_end: null,
    metrics: {
      account_count: rows.accounts.length,
      position_count: rows.positions.length,
      order_count: rows.orders.length,
      deal_count: rows.deals.length,
      total_asset: totalAsset,
      cash_available: cashAvailable,
      market_value: marketValue,
      cash_ratio: cashAvailable / totalAsset,
      top_position_concentration: Number(topPositions[0].position_pct),
      top_positions: topPositions,
      trade_count: rows.isThs ? 2 : 2,
      buy_count: rows.isThs ? 0 : 2,
      sell_count: rows.isThs ? 2 : 0,
      buy_sell_imbalance: rows.isThs ? -1 : 1,
      deal_amount_total: rows.isThs ? 22000 : 45000
    },
    signals: {
      limitations: ["historical account snapshots are insufficient for drawdown analytics"],
      generated_at: "2026-06-12T00:00:00Z"
    },
    risk_flags: [{ code: "HIGH_SINGLE_POSITION_CONCENTRATION", severity: "warning", value: 0.5114 }],
    source_snapshot_ids: {
      accounts: rows.accounts.map((item) => item.snapshot_id),
      positions: rows.positions.map((item) => item.snapshot_id),
      orders: rows.orders.map((item) => item.snapshot_id),
      deals: rows.deals.map((item) => item.snapshot_id)
    },
    model_version: "deterministic-p0",
    created_at: "2026-06-12T00:00:00Z"
  };
}

export function mockBrokerReadiness() {
  return {
    object: "aiask.desktop.broker_readiness",
    status: "ready",
    connectors: [
      {
        provider: "qmt",
        label: "QMT / MiniQMT",
        status: "ready",
        configured: true,
        ready: true,
        read_only: true,
        live_trading_enabled: false,
        required_env: ["QMT_PATH", "QMT_ACCOUNT"],
        missing_env: [],
        optional_env: ["QMT_ACCOUNT_TYPE", "QMT_SESSION_ID"],
        required_tools: ["qmt_query_account", "qmt_query_position", "qmt_query_orders"],
        missing_tools: [],
        environment_checks: [
          "Install and sign in to MiniQMT on the same Windows host as the Agent.",
          "Install the XtQuant SDK in the Agent Python environment.",
          "Set QMT_PATH and QMT_ACCOUNT in the Agent startup environment, then restart Agent.",
          "Register a financial MCP server exposing QMT read-only tools."
        ],
        authorization_notes: [
          "Desktop only sends provider and explicit read-only consent to Agent HTTP.",
          "Account identifiers are hashed before snapshots are stored.",
          "Live order placement and cancellation remain disabled from this surface."
        ],
        test_entry: { method: "POST", path: "/v1/desktop/broker/sync", consent_required: true }
      },
      {
        provider: "tonghuashun",
        label: "Tonghuashun",
        status: "unconfigured",
        configured: false,
        ready: false,
        read_only: true,
        live_trading_enabled: false,
        required_env: ["THS_CLIENT_PATH"],
        missing_env: ["THS_CLIENT_PATH"],
        optional_env: ["THS_TRADE_ACCOUNT", "THS_BROKER"],
        required_tools: ["ths_query_balance", "ths_query_position", "ths_query_orders", "ths_query_deals"],
        missing_tools: ["ths_query_balance", "ths_query_position", "ths_query_orders", "ths_query_deals"],
        environment_checks: [
          "Install and sign in to the Tonghuashun desktop trading client on Windows.",
          "Install easytrader in the Agent Python environment.",
          "Set THS_CLIENT_PATH and restart Agent.",
          "Register a financial MCP server exposing THS read-only tools."
        ],
        authorization_notes: [
          "Desktop only sends provider and explicit read-only consent to Agent HTTP.",
          "Credentials stay in Agent startup environment or OS secret store.",
          "Live order placement and cancellation remain disabled from this surface."
        ],
        test_entry: { method: "POST", path: "/v1/desktop/broker/sync", consent_required: true }
      }
    ],
    mcp: { registration: { status: "mock" }, servers: [{ name: "qmt-local", domain: "financial", status: "ready" }] },
    latest_analytics: mockBrokerAnalytics(),
    live_trading_enabled: false,
    read_only: true,
    secrets_redacted: true
  };
}

export function mockBrokerSync(body: Record<string, unknown>) {
  const provider = String(body.provider || "qmt");
  const rows = brokerRows(provider);
  if (!body.consent) {
    return {
      object: "aiask.desktop.broker_readonly",
      success: false,
      data: null,
      error: "broker read-only sync requires explicit user consent",
      error_code: "BROKER_CONSENT_REQUIRED",
      read_only: true,
      live_trading_enabled: false,
      secrets_redacted: true
    };
  }
  return {
    object: "aiask.desktop.broker_readonly",
    success: true,
    data: {
      sync_id: rows.isThs ? "broker_sync_mock_ths" : "broker_sync_mock_qmt",
      profile: rows.profile,
      counts: {
        accounts: rows.accounts.length,
        positions: rows.positions.length,
        orders: rows.orders.length,
        deals: rows.deals.length
      },
      errors: [],
      analytics: mockBrokerAnalytics(provider)
    },
    error: null,
    read_only: true,
    live_trading_enabled: false,
    secrets_redacted: true,
    source_chain: ["desktop.mockApi", "aiask_agent.broker_readonly"],
    generated_at: 1781193600
  };
}

export function mockBrokerSnapshotPayload(provider = "qmt") {
  const rows = brokerRows(provider);
  return {
    object: "aiask.desktop.broker_readonly",
    success: true,
    data: {
      profiles: [rows.profile],
      accounts: rows.accounts,
      positions: rows.positions,
      orders: rows.orders,
      deals: rows.deals,
      analytics: mockBrokerAnalytics(provider)
    },
    error: null,
    read_only: true,
    live_trading_enabled: false,
    secrets_redacted: true,
    source_chain: ["desktop.mockApi", "aiask_agent.broker_readonly"],
    generated_at: 1781193600
  };
}

export function mockBrokerAnalyticsPayload(provider = "qmt") {
  return {
    object: "aiask.desktop.broker_readonly.analytics",
    success: true,
    data: { analytics: mockBrokerAnalytics(provider) },
    error: null,
    read_only: true,
    live_trading_enabled: false,
    secrets_redacted: true,
    source_chain: ["desktop.mockApi", "aiask_agent.broker_readonly"]
  };
}
