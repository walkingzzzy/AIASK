import type { ApiHeaders } from "./api";
import type {
  CapabilityWorkbenchPayload,
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  NormalizedRunEvent,
  RecentSessionSummary,
  ToolCatalogItem,
} from "./types";

interface MockOptions {
  method?: string;
  token?: string;
  body?: unknown;
  headers?: ApiHeaders;
}

const CONTROL_TOKEN = "mock-control-token";

const financeTools: ToolCatalogItem[] = [
  { name: "agent_tool_catalog", capability: "tool_catalog", category: "financial_read", side_effect: "read_only", description: "Return the AIASK Agent tool catalog." },
  { name: "agent_analyze_stock", capability: "stock_analysis", category: "financial_read", side_effect: "read_only", description: "Run a stock analysis workflow.", input_schema: { type: "object", properties: { code: { type: "string" }, include_decision: { type: "boolean" } } }, examples: [{ arguments: { code: "600519", include_decision: false } }] },
  { name: "agent_data_validation", capability: "data_validation", category: "financial_read", side_effect: "read_only", description: "Validate financial datasets.", input_schema: { type: "object", properties: { action: { type: "string" } } }, examples: [{ arguments: { action: "backend" } }] },
  { name: "agent_quant_data_gate", capability: "quant_data_gate", category: "financial_read", side_effect: "read_only", description: "Check local market data readiness.", input_schema: { type: "object", properties: { codes: { type: "array" }, max_stale_days: { type: "integer" } } }, examples: [{ arguments: { codes: ["600519", "000001"], max_stale_days: 5 } }] },
  { name: "agent_market_temperature_snapshot", capability: "market_temperature_snapshot", category: "financial_read", side_effect: "read_only", description: "Read the market temperature and industry breadth snapshot.", input_schema: { type: "object", properties: { limit: { type: "integer" }, top_n: { type: "integer" }, as_of: { type: "string" }, min_bars: { type: "integer" }, use_cache: { type: "boolean" } } }, examples: [{ arguments: { limit: 300, top_n: 8, min_bars: 20, use_cache: true } }] },
  { name: "agent_market_temperature_cache_readiness", capability: "market_temperature_cache_readiness", category: "financial_read", side_effect: "read_only", description: "Read freshness and quality readiness for the durable market temperature cache.", input_schema: { type: "object", properties: { as_of: { type: "string" }, max_stale_days: { type: "integer" } } }, examples: [{ arguments: { max_stale_days: 1 } }] },
  { name: "agent_market_temperature_cache_history", capability: "market_temperature_cache_history", category: "financial_read", side_effect: "read_only", description: "List recent durable market temperature cache entries.", input_schema: { type: "object", properties: { limit: { type: "integer" }, include_snapshot: { type: "boolean" } } }, examples: [{ arguments: { limit: 10, include_snapshot: false } }] },
  { name: "agent_market_temperature_industry_history", capability: "market_temperature_industry_history", category: "financial_read", side_effect: "read_only", description: "List cached industry temperature history.", input_schema: { type: "object", properties: { industry: { type: "string" }, limit: { type: "integer" }, top_n: { type: "integer" }, match_mode: { type: "string" }, include_source_chain: { type: "boolean" } } }, examples: [{ arguments: { industry: "801780", limit: 60 } }] },
  { name: "agent_market_temperature_industry_constituents", capability: "market_temperature_industry_constituents", category: "financial_read", side_effect: "read_only", description: "List local stock-universe constituents for one market temperature industry.", input_schema: { type: "object", properties: { industry: { type: "string" }, limit: { type: "integer" }, offset: { type: "integer" }, match_mode: { type: "string" }, include_source_chain: { type: "boolean" } }, required: ["industry"] }, examples: [{ arguments: { industry: "801780", limit: 50 } }] },
  { name: "agent_market_temperature_forward_validation", capability: "market_temperature_forward_validation", category: "financial_read", side_effect: "read_only", description: "Read PIT forward-validation matrix for cached market temperature states.", input_schema: { type: "object", properties: { limit: { type: "integer" }, horizons: { type: "array" }, target_field: { type: "string" }, benchmark_code: { type: "string" }, min_samples: { type: "integer" }, neutral_band_pct: { type: "number" }, include_samples: { type: "boolean" } } }, examples: [{ arguments: { limit: 180, horizons: [1, 3, 5], target_field: "benchmark_return", benchmark_code: "000300" } }] },
  { name: "agent_factor_validation", capability: "factor_validation", category: "financial_read", side_effect: "read_only", description: "Validate factor signals.", input_schema: { type: "object", properties: { codes: { type: "array" }, factors: { type: "array" } } }, examples: [{ arguments: { codes: ["600519", "000001"], factors: ["momentum"] } }] },
  { name: "agent_backtest_suite", capability: "backtest_suite", category: "financial_read", side_effect: "read_only", description: "Run strategy backtests.", input_schema: { type: "object", properties: { codes: { type: "array" }, strategy: { type: "string" } } }, examples: [{ arguments: { codes: ["600519", "000001"], strategy: "ma_cross" } }] },
  { name: "agent_portfolio_risk", capability: "portfolio_risk", category: "financial_read", side_effect: "read_only", description: "Analyze portfolio risk.", input_schema: { type: "object", properties: { codes: { type: "array" }, weights: { type: "array" } } }, examples: [{ arguments: { codes: ["600519", "000001"], weights: [0.5, 0.5] } }] },
  { name: "agent_quant_research_run", capability: "quant_research_run", category: "financial_read", side_effect: "read_only", description: "Run quant research pipeline." },
  { name: "agent_factory_status", capability: "strategy_factory_status", category: "financial_read", side_effect: "read_only", description: "Read strategy factory status.", input_schema: { type: "object", properties: { recent_run_limit: { type: "integer" } } } },
  { name: "agent_factory_runs", capability: "strategy_factory_runs", category: "financial_read", side_effect: "read_only", description: "List strategy factory runs.", input_schema: { type: "object", properties: { limit: { type: "integer" } } } },
  { name: "agent_strategy_review_snapshot", capability: "strategy_review_snapshot", category: "financial_read", side_effect: "read_only", description: "Read strategy review snapshots.", input_schema: { type: "object", properties: { limit: { type: "integer" } } } },
  { name: "agent_strategy_domain_events", capability: "strategy_domain_events", category: "financial_read", side_effect: "read_only", description: "List strategy domain events.", input_schema: { type: "object", properties: { event_type: { type: "string" }, limit: { type: "integer" } } } },
  { name: "agent_factory_event_list", capability: "factory_event_list", category: "financial_read", side_effect: "read_only", description: "列出策略工厂事件。" },
  { name: "agent_factory_event_preview_tasks", capability: "factory_event_preview_tasks", category: "financial_read", side_effect: "read_only", description: "预览策略工厂事件任务。" },
  { name: "agent_factory_event_lineage", capability: "factory_event_lineage", category: "financial_read", side_effect: "read_only", description: "读取策略工厂事件血缘。" },
  { name: "agent_factory_theme_exposure_status", capability: "factory_theme_exposure_status", category: "financial_read", side_effect: "read_only", description: "Read theme exposure status." },
  { name: "agent_factory_event_outbox_status", capability: "factory_event_outbox_status", category: "financial_read", side_effect: "read_only", description: "Read factory event outbox status." },
  { name: "agent_incubation_factory_status", capability: "incubation_factory_status", category: "financial_read", side_effect: "read_only", description: "Read incubation factory status." },
  { name: "agent_trade_prediction_status", capability: "trade_prediction_status", category: "financial_read", side_effect: "read_only", description: "Read trade prediction scoring status." },
  { name: "agent_trade_prediction_outcomes", capability: "trade_prediction_outcomes", category: "financial_read", side_effect: "read_only", description: "List trade prediction outcomes." },
  { name: "agent_trade_prediction_matrix", capability: "trade_prediction_matrix", category: "financial_read", side_effect: "read_only", description: "Read trade prediction contribution matrix." },
  { name: "agent_stock_radar_status", capability: "stock_radar_status", category: "financial_read", side_effect: "read_only", description: "Read stock radar status." },
  { name: "agent_stock_radar_candidates", capability: "stock_radar_candidates", category: "financial_read", side_effect: "read_only", description: "List stock radar candidates." },
  { name: "agent_stock_radar_digest", capability: "stock_radar_digest", category: "financial_read", side_effect: "read_only", description: "Preview stock radar digest." },
  { name: "agent_action_intent_create", capability: "action_intent_create", category: "financial_stateful", side_effect: "durable_intent", description: "创建审批意图。" },
  { name: "agent_action_intent_get", capability: "action_intent_get", category: "financial_read", side_effect: "read_only", description: "Read an approval intent." },
  { name: "agent_memory_search", capability: "memory_search", category: "financial_read", side_effect: "read_only", description: "Search financial memory.", input_schema: { type: "object", properties: { query: { type: "string" }, user_id: { type: "string" } } } },
  { name: "agent_session_search", capability: "session_search", category: "financial_read", side_effect: "read_only", description: "Search sessions and responses.", input_schema: { type: "object", properties: { query: { type: "string" }, user_id: { type: "string" } } } }
];

const hermesTools: ToolCatalogItem[] = [
  { name: "agent_file_list", capability: "file_list", category: "general_read", side_effect: "read_only", description: "List workspace files.", input_schema: { type: "object", properties: { path: { type: "string" }, limit: { type: "integer" } } } },
  { name: "agent_file_read", capability: "file_read", category: "general_read", side_effect: "read_only", description: "Read a workspace file.", input_schema: { type: "object", properties: { path: { type: "string" } } } },
  { name: "agent_terminal_backends", capability: "terminal_backends", category: "terminal_backend", side_effect: "read_only", description: "List terminal backend status." },
  { name: "agent_browser_snapshot", capability: "browser_snapshot", category: "browser", side_effect: "read_only", description: "Read browser snapshot." },
  { name: "agent_browser_console", capability: "browser_console", category: "browser", side_effect: "read_only", description: "Read browser console messages." },
  { name: "agent_web_search", capability: "web_search", category: "web", side_effect: "read_only", description: "Search the web.", input_schema: { type: "object", properties: { query: { type: "string" } } } },
  { name: "agent_skill_list", capability: "skill_list", category: "skills", side_effect: "read_only", description: "List native skills." },
  { name: "agent_plugin_list", capability: "plugin_list", category: "plugins", side_effect: "read_only", description: "List native plugins." },
  { name: "agent_mcp_manage", capability: "mcp_manage", category: "mcp_admin", side_effect: "stateful", description: "Manage MCP servers." },
  { name: "agent_model_manage", capability: "model_manage", category: "model_provider", side_effect: "stateful", description: "查看模型提供方。" },
  { name: "agent_memory_manage", capability: "memory_manage", category: "memory_admin", side_effect: "stateful", description: "管理记忆提供方。" },
  { name: "agent_gateway_status", capability: "platform_gateway_status", category: "platform_gateway", side_effect: "read_only", description: "Read gateway status." },
  { name: "agent_gateway_platforms", capability: "platform_gateway_platforms", category: "platform_gateway", side_effect: "read_only", description: "List gateway platforms." },
  { name: "agent_learning_status", capability: "learning_status", category: "learning", side_effect: "read_only", description: "Read learning loop status." },
  { name: "agent_learning_review", capability: "learning_review", category: "learning", side_effect: "read_only", description: "Review learning proposals." },
  { name: "agent_rl_list_environments", capability: "rl_list_environments", category: "rl_training", side_effect: "read_only", description: "List RL environments." },
  { name: "agent_rl_get_config", capability: "rl_get_config", category: "rl_training", side_effect: "read_only", description: "Read RL config." },
  { name: "agent_job_list", capability: "cron_list", category: "cron_admin", side_effect: "read_only", description: "List background jobs." },
  { name: "agent_job_create", capability: "cron_create", category: "cron_admin", side_effect: "stateful", description: "创建后台任务。" },
  { name: "agent_session_handoff", capability: "session_handoff", category: "memory_admin", side_effect: "stateful", description: "管理会话交接。" }
];

let profile = {
  object: "aiask.local_profile",
  user_id: "local",
  profile_name: "Mock 本地操作者",
  storage: "local_json",
  path: "mock://aiask/local-profile.json",
  updated_at: "2026-05-22T09:00:00Z",
  status: "ready",
  secrets_redacted: true
};

let jobs: Array<Record<string, unknown>> = [
  {
    job_id: "job_mock_research",
    name: "每日研究监控",
    prompt: "复盘 mock 市场数据。",
    schedule: "*/30 * * * *",
    enabled: true,
    user_id: "local",
    last_run_at: null
  }
];

const intents = new Map<string, Record<string, unknown>>();

const mockRunEvents: NormalizedRunEvent[] = [
  {
    id: "evt_tool",
    event: "tool.called",
    event_type: "tool.called",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:01Z",
    kind: "tool",
    title: "tool.called: agent_analyze_stock",
    severity: "info",
    status: "completed",
    tool_name: "agent_analyze_stock",
    jump_target: "tools-intents-approvals",
    data: { tool: "agent_analyze_stock", status: "completed" },
  },
  {
    id: "evt_approval",
    event: "approval.intent_created",
    event_type: "approval.intent_created",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:02Z",
    kind: "approval",
    title: "approval.intent_created",
    severity: "info",
    status: "pending",
    jump_target: "tools-intents-approvals",
    data: { intent_id: "intent_mock_pending", status: "pending" },
  },
];

const mockRunSummaries: DesktopRunSummary[] = [
  {
    run_id: "run_mock",
    session_id: "sess_mock",
    status: "completed",
    response_id: "resp_mock",
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:02Z",
    event_count: mockRunEvents.length,
    tool_call_count: 1,
    approval_count: 1,
    error_count: 0,
    last_event: mockRunEvents[mockRunEvents.length - 1],
    has_errors: false,
    has_pending_approval: true,
  },
];

const mockSessionSummaries: RecentSessionSummary[] = [
  {
    session_id: "sess_mock",
    title: "Mock 研究会话",
    user_id: profile.user_id,
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:02Z",
    last_message_at: "2026-05-22T09:00:02Z",
    last_run_id: "run_mock",
    last_run_summary: mockRunSummaries[0],
    last_event: mockRunEvents[mockRunEvents.length - 1],
    message_count: 2,
    has_errors: false,
    has_pending_approval: true,
    status: "completed",
    metadata: { source: "desktop.mockApi" },
  },
];

function mockWorkbenchSummary(): DesktopWorkbenchSummary {
  return {
    recent_sessions: mockSessionSummaries,
    recent_runs: mockRunSummaries,
    queues: {
      pending_intents: 1,
      pending_approvals: 1,
      gateway_failed: 1,
      mcp_degraded: 1,
    },
    access: {
      full_mode_active: true,
      control_token_configured: true,
      sessions_admin_available: true,
    },
  };
}

function financialManagerCatalog() {
  const groups = [
    { id: "overview", label: "总览", description: "准备度与安全状态" },
    { id: "market-research", label: "市场与研究", description: "个股、研究、板块、情绪、技术面和期权" },
    { id: "portfolio-watchlist", label: "组合与自选", description: "组合与自选只读查询，以及审批意图" },
    { id: "risk-performance", label: "风险与绩效", description: "风险、VaR、暴露、归因和决策支持" },
    { id: "quant-backtest", label: "量化与回测", description: "量化研究和回测套件" },
    { id: "paper-execution", label: "纸上交易与执行", description: "纸上交易和执行计划" },
    { id: "broker-readonly", label: "券商只读", description: "仅查询券商账户和订单" }
  ];
  const actions = [
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

export function isMockEndpoint(endpoint: string): boolean {
  return endpoint.trim().replace(/\/+$/, "") === "mock://aiask";
}

function authorized(options: MockOptions): boolean {
  return Boolean((options.token || "").trim());
}

function envelope(tool: string, data: unknown, success = true) {
  return {
    success,
    data,
    error: success ? null : "mock_error",
    ...(success ? {} : { error_code: "MOCK_ERROR" }),
    meta: {
      trace_id: `mock_trace_${Date.now()}`,
      source_chain: ["desktop.mockApi"],
      side_effect: { level: "read_only", target: tool, confirmation_required: false, idempotent: true }
    }
  };
}

function aiStatus() {
  return {
    object: "aiask.ai_status",
    provider: "project-root-api",
    model: "gpt-5.4",
    base_url_configured: true,
    api_key_configured: true,
    mock: true,
    configured: true,
    runtime_client: "mock",
    config_source: { loaded: true, path: "mock://aiask/.env", source: "project_root", secrets_redacted: true },
    secrets_redacted: true
  };
}

function dataStatus() {
  return {
    object: "aiask.desktop_data_status",
    status: "ready",
    database: {
      backend: "sqlite",
      path: "mock://aiask/akshare.sqlite3",
      configured: true,
      writable: true,
      sources: ["tdx_local", "tushare", "akshare"]
    },
    freshness: {
      "600519": { status: "fresh", source: "tdx_local" },
      "000001": { status: "fresh", source: "tushare" }
    },
    quality_gate: envelope("agent_quant_data_gate", { status: "passed", missing: [], stale: [] }),
    data_validation: { status: "passed" },
    codes: ["600519", "000001"],
    max_stale_days: 5,
    missing_count: 0,
    stale_count: 0,
    secrets_redacted: true
  };
}

function marketTemperatureSnapshot(body: Record<string, unknown> = {}) {
  const topN = Math.max(1, Math.min(Number(body.top_n || 8), 12));
  const asOf = String(body.as_of || "2026-06-08");
  const industries = [
    {
      code: "801750",
      name: "计算机",
      date: asOf,
      stock_count: 48,
      trend_known_count: 48,
      above_ma20_count: 37,
      ma20_breadth: 0.7708,
      advance_count: 34,
      decline_count: 11,
      flat_count: 3,
      advance_ratio: 0.7083,
      avg_pct_change: 1.28,
      weighted_pct_change: 1.16,
      amount: 428.35,
      market_cap: 18342.5,
      market_cap_weight: 0.118,
      temperature: 74.42,
      state: "warm"
    },
    {
      code: "801080",
      name: "电子",
      date: asOf,
      stock_count: 62,
      trend_known_count: 61,
      above_ma20_count: 45,
      ma20_breadth: 0.7377,
      advance_count: 41,
      decline_count: 18,
      flat_count: 3,
      advance_ratio: 0.6613,
      avg_pct_change: 0.94,
      weighted_pct_change: 1.02,
      amount: 512.9,
      market_cap: 22640.2,
      market_cap_weight: 0.146,
      temperature: 71.83,
      state: "warm"
    },
    {
      code: "801780",
      name: "银行",
      date: asOf,
      stock_count: 34,
      trend_known_count: 34,
      above_ma20_count: 18,
      ma20_breadth: 0.5294,
      advance_count: 17,
      decline_count: 15,
      flat_count: 2,
      advance_ratio: 0.5,
      avg_pct_change: 0.18,
      weighted_pct_change: 0.12,
      amount: 216.72,
      market_cap: 31200.8,
      market_cap_weight: 0.201,
      temperature: 53.27,
      state: "neutral"
    },
    {
      code: "801120",
      name: "食品饮料",
      date: asOf,
      stock_count: 42,
      trend_known_count: 41,
      above_ma20_count: 14,
      ma20_breadth: 0.3415,
      advance_count: 12,
      decline_count: 28,
      flat_count: 2,
      advance_ratio: 0.2857,
      avg_pct_change: -0.84,
      weighted_pct_change: -0.71,
      amount: 148.42,
      market_cap: 17420.1,
      market_cap_weight: 0.112,
      temperature: 32.06,
      state: "cool"
    },
    {
      code: "801730",
      name: "电力设备",
      date: asOf,
      stock_count: 55,
      trend_known_count: 52,
      above_ma20_count: 13,
      ma20_breadth: 0.25,
      advance_count: 15,
      decline_count: 37,
      flat_count: 3,
      advance_ratio: 0.2727,
      avg_pct_change: -1.12,
      weighted_pct_change: -1.28,
      amount: 276.54,
      market_cap: 20680.7,
      market_cap_weight: 0.133,
      temperature: 27.34,
      state: "cool"
    }
  ];
  return {
    contract_version: "market_temperature.v1",
    as_of: asOf,
    market: {
      stock_count: 300,
      trend_known_count: 296,
      above_ma20_count: 162,
      ma20_breadth: 0.5473,
      advance_count: 151,
      decline_count: 136,
      flat_count: 13,
      advance_ratio: 0.5033,
      avg_pct_change: 0.12,
      weighted_pct_change: 0.18,
      amount: 4280.6,
      market_cap: 155080.4,
      temperature: 55.84,
      state: "neutral"
    },
    industries,
    hot_industries: industries.slice(0, topN),
    cold_industries: [...industries].sort((left, right) => Number(left.temperature) - Number(right.temperature)).slice(0, topN),
    quality: {
      status: "healthy",
      warnings: [],
      input_rows: 300,
      valid_stock_count: 300,
      invalid_stock_rows: 0,
      industry_count: industries.length,
      unknown_industry_count: 0,
      trend_coverage: 0.9867,
      universe_limit: Number(body.limit || 300),
      universe_count: 300,
      loaded_stock_rows: 300,
      missing_kline_rows: 0,
      contract_version: "market_temperature.v1"
    },
    source_chain: ["desktop.mockApi", "market_temperature.fixture"]
  };
}

function marketTemperatureCacheReadiness(body: Record<string, unknown> = {}) {
  const snapshot = marketTemperatureSnapshot(body);
  const asOf = String(body.as_of || snapshot.as_of || "2026-06-08");
  const maxStaleDays = Math.max(0, Math.trunc(Number(body.max_stale_days ?? 1)));
  return {
    ready: true,
    status: "fresh",
    read_only: true,
    as_of: asOf,
    requested_as_of: body.as_of ? asOf : null,
    max_stale_days: maxStaleDays,
    staleness_days: 1,
    quality_status: snapshot.quality.status,
    degraded: false,
    warnings: [],
    market_temperature: snapshot.market.temperature,
    market_state: snapshot.market.state,
    stock_count: snapshot.market.stock_count,
    industry_count: snapshot.quality.industry_count,
    cache: {
      created_at: `${asOf}T15:00:00Z`,
      updated_at: `${asOf}T15:05:00Z`,
      source: "market_temperature_snapshots"
    },
    blockers: [],
    source_chain: ["desktop.mockApi", "market_temperature.cache_readiness.fixture"]
  };
}

function marketTemperatureCacheHistory(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 10)), 365));
  const includeSnapshot = Boolean(body.include_snapshot);
  const rows = [
    {
      as_of: "2026-06-08",
      market_temperature: 55.84,
      market_state: "neutral",
      stock_count: 300,
      industry_count: 5,
      quality_status: "healthy",
      warnings: [],
      created_at: "2026-06-08T15:00:00Z",
      updated_at: "2026-06-08T15:05:00Z"
    },
    {
      as_of: "2026-06-07",
      market_temperature: 47.2,
      market_state: "neutral",
      stock_count: 298,
      industry_count: 5,
      quality_status: "healthy",
      warnings: [],
      created_at: "2026-06-07T15:00:00Z",
      updated_at: "2026-06-07T15:04:00Z"
    },
    {
      as_of: "2026-06-06",
      market_temperature: 32.4,
      market_state: "cool",
      stock_count: 294,
      industry_count: 5,
      quality_status: "degraded",
      warnings: ["partial_kline_coverage"],
      created_at: "2026-06-06T15:00:00Z",
      updated_at: "2026-06-06T15:03:00Z"
    }
  ].slice(0, limit);
  const items = includeSnapshot
    ? rows.map((row) => ({ ...row, snapshot: marketTemperatureSnapshot({ ...body, as_of: row.as_of }) }))
    : rows;
  return {
    items,
    count: items.length,
    limit,
    include_snapshot: includeSnapshot,
    source_chain: ["desktop.mockApi", "market_temperature.cache_history.fixture"]
  };
}

function marketTemperatureIndustryHistory(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 3)), 365));
  const topN = Math.max(1, Math.min(Math.trunc(Number(body.top_n || 3)), 50));
  const query = String(body.industry || "").trim().toLowerCase();
  const matchMode = String(body.match_mode || "exact").toLowerCase() === "contains" ? "contains" : "exact";
  const includeSourceChain = Boolean(body.include_source_chain);
  const dateRows = [
    { as_of: "2026-06-06", offset: -8, market_temperature: 32.4, market_state: "cool" },
    { as_of: "2026-06-07", offset: -3, market_temperature: 47.2, market_state: "neutral" },
    { as_of: "2026-06-08", offset: 0, market_temperature: 55.84, market_state: "neutral" }
  ].slice(-limit);
  const matchesQuery = (item: Record<string, unknown>) => {
    if (!query) return true;
    const tokens = [item.code, item.name].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean);
    return matchMode === "contains" ? tokens.some((token) => token.includes(query)) : tokens.some((token) => token === query);
  };
  const items = dateRows.flatMap((dateRow) => {
    const snapshot = marketTemperatureSnapshot({ ...body, as_of: dateRow.as_of });
    const industries = (snapshot.industries || []).filter(matchesQuery);
    const selected = query ? industries : industries.slice(0, topN);
    return selected.map((industry) => ({
      as_of: dateRow.as_of,
      code: industry.code,
      name: industry.name,
      temperature: Number(industry.temperature || 0) + dateRow.offset,
      state: industry.state,
      ma20_breadth: industry.ma20_breadth,
      advance_count: industry.advance_count,
      decline_count: industry.decline_count,
      flat_count: industry.flat_count,
      stock_count: industry.stock_count,
      market_cap_weight: industry.market_cap_weight,
      market_temperature: dateRow.market_temperature,
      market_state: dateRow.market_state,
      quality_status: snapshot.quality.status,
      warnings: snapshot.quality.warnings,
      updated_at: `${dateRow.as_of}T15:05:00Z`,
      ...(includeSourceChain ? { source_chain: snapshot.source_chain } : {})
    }));
  });
  return {
    items,
    count: items.length,
    limit,
    top_n: topN,
    industry: query || null,
    match_mode: matchMode,
    include_source_chain: includeSourceChain,
    source_chain: ["desktop.mockApi", "market_temperature.industry_history.fixture"]
  };
}

function marketTemperatureIndustryConstituents(body: Record<string, unknown> = {}) {
  const limit = Math.max(1, Math.min(Math.trunc(Number(body.limit || 50)), 1000));
  const offset = Math.max(0, Math.min(Math.trunc(Number(body.offset || 0)), 10000));
  const query = String(body.industry || "").trim().toLowerCase();
  const matchMode = String(body.match_mode || "contains").toLowerCase() === "exact" ? "exact" : "contains";
  const includeSourceChain = Boolean(body.include_source_chain);
  const snapshot = marketTemperatureSnapshot(body);
  const industryRows = snapshot.industries || [];
  const rows = industryRows.flatMap((industry, industryIndex) => {
    const baseCode = String(industry.code || `801${industryIndex}`);
    const industryName = String(industry.name || baseCode);
    return [
      {
        code: industryIndex === 2 ? "000001" : `${industryIndex + 1}00001`,
        name: industryIndex === 2 ? "Ping An Bank" : `${industryName} Leader`,
        industry: industryName,
        sector: industryName,
        market: industryIndex === 2 ? "SZ" : "SH",
        market_cap: Number(industry.market_cap || 1000) * 0.18,
        pe_ratio: 8.4 + industryIndex,
        pb_ratio: 0.7 + industryIndex / 10,
        list_date: "2001-01-01",
        industry_code: baseCode
      },
      {
        code: industryIndex === 2 ? "600036" : `${industryIndex + 1}00002`,
        name: industryIndex === 2 ? "CMB" : `${industryName} Growth`,
        industry: industryName,
        sector: industryName,
        market: "SH",
        market_cap: Number(industry.market_cap || 1000) * 0.12,
        pe_ratio: 11.2 + industryIndex,
        pb_ratio: 1.1 + industryIndex / 10,
        list_date: "2004-01-01",
        industry_code: baseCode
      }
    ];
  });
  const matchesQuery = (item: Record<string, unknown>) => {
    if (!query) return false;
    const tokens = [item.industry, item.sector, item.industry_code].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean);
    return matchMode === "exact" ? tokens.some((token) => token === query) : tokens.some((token) => token.includes(query));
  };
  const matches = rows.filter(matchesQuery);
  const items = matches.slice(offset, offset + limit).map((item) => ({
    code: item.code,
    name: item.name,
    industry_code: item.industry_code,
    industry: item.industry,
    sector: item.sector,
    market: item.market,
    market_cap: item.market_cap,
    pe_ratio: item.pe_ratio,
    pb_ratio: item.pb_ratio,
    list_date: item.list_date,
    ...(includeSourceChain ? { source_chain: ["desktop.mockApi", "market_temperature.industry_constituents.fixture"] } : {})
  }));
  return {
    items,
    count: items.length,
    total_matches: matches.length,
    limit,
    offset,
    industry: String(body.industry || ""),
    match_mode: matchMode,
    include_source_chain: includeSourceChain,
    source_chain: ["desktop.mockApi", "market_temperature.industry_constituents.fixture"]
  };
}

function marketTemperatureForwardValidation(body: Record<string, unknown> = {}) {
  const limit = Math.max(2, Math.min(Math.trunc(Number(body.limit || 180)), 365));
  const rawHorizons = Array.isArray(body.horizons) ? body.horizons : [1, 3, 5];
  const horizons = rawHorizons.map((item) => Math.max(1, Math.min(Math.trunc(Number(item || 1)), 20))).filter((item, index, items) => items.indexOf(item) === index);
  const targetField = String(body.target_field || "benchmark_return");
  const benchmarkCode = String(body.benchmark_code || "000300");
  const matrix = {
    warm: {
      "1d": { sample_n: 18, direction_hits: 12, reliable: true, avg_forward_return: 0.42, hit_rate: 0.6667, min_forward_return: -1.1, max_forward_return: 1.8 },
      "3d": { sample_n: 16, direction_hits: 10, reliable: true, avg_forward_return: 0.76, hit_rate: 0.625, min_forward_return: -1.6, max_forward_return: 2.7 },
      "5d": { sample_n: 12, direction_hits: 7, reliable: true, avg_forward_return: 0.94, hit_rate: 0.5833, min_forward_return: -2.2, max_forward_return: 3.5 }
    },
    neutral: {
      "1d": { sample_n: 24, direction_hits: 15, reliable: true, avg_forward_return: 0.06, hit_rate: 0.625, min_forward_return: -0.8, max_forward_return: 0.9 },
      "3d": { sample_n: 22, direction_hits: 12, reliable: true, avg_forward_return: 0.18, hit_rate: 0.5455, min_forward_return: -1.2, max_forward_return: 1.3 },
      "5d": { sample_n: 18, direction_hits: 10, reliable: true, avg_forward_return: 0.25, hit_rate: 0.5556, min_forward_return: -1.9, max_forward_return: 2.0 }
    },
    cool: {
      "1d": { sample_n: 14, direction_hits: 8, reliable: true, avg_forward_return: -0.31, hit_rate: 0.5714, min_forward_return: -1.7, max_forward_return: 1.0 },
      "3d": { sample_n: 12, direction_hits: 8, reliable: true, avg_forward_return: -0.64, hit_rate: 0.6667, min_forward_return: -2.3, max_forward_return: 1.4 },
      "5d": { sample_n: 9, direction_hits: 6, reliable: true, avg_forward_return: -0.72, hit_rate: 0.6667, min_forward_return: -2.8, max_forward_return: 1.9 }
    }
  };
  return {
    matrix,
    states: Object.keys(matrix),
    horizons,
    count: 145,
    snapshot_count: 72,
    limit,
    target_field: targetField,
    requested_target_field: targetField,
    benchmark_code: benchmarkCode,
    benchmark_status: targetField === "benchmark_return" ? "available" : "not_requested",
    benchmark_bar_count: targetField === "benchmark_return" ? 76 : 0,
    min_samples: Number(body.min_samples || 3),
    neutral_band_pct: Number(body.neutral_band_pct ?? 0.2),
    include_samples: Boolean(body.include_samples),
    samples: [],
    source_chain: ["desktop.mockApi", "market_temperature.forward_validation.fixture"]
  };
}

function strategyFactory() {
  return {
    status: envelope("agent_factory_status", { status: "ready", configured: true, database_configured: true, run_count: 7 }),
    runs: envelope("agent_factory_runs", { runs: [{ run_id: "factory_run_mock", status: "completed", candidates: 12 }] }),
    review_snapshot: envelope("agent_strategy_review_snapshot", { status: "ready", reviews: [{ strategy_id: "strategy_mock", decision: "incubate" }] })
  };
}

const mockTradePredictionOutcomes = [
  {
    outcome_id: "tpo_mock_001",
    prediction_id: "tp_mock_001",
    strategy_id: "strategy_momentum_cn",
    stock_code: "600519",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "ok",
    data_quality_status: "ok",
    trade_prediction_score: 0.82,
    outcome_json: {
      direction_hit: true,
      target_touch: true,
      risk_proxy_score: 0.78,
      time_bucket_hit_rate: 0.75,
      entry_window_hit: true,
      exit_window_hit: true,
      planned_trade_return: 0.034
    },
    metadata: { family: "momentum", stage: "candidate", regime: "bull", event: "policy_shock", factor: "momentum_20d" },
    calculated_at: "2026-06-04T07:15:00Z"
  },
  {
    outcome_id: "tpo_mock_002",
    prediction_id: "tp_mock_002",
    strategy_id: "strategy_reversal_cn",
    stock_code: "000001",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "partial_intraday_missing",
    data_quality_status: "intraday_missing",
    trade_prediction_score: 0.51,
    outcome_json: {
      direction_hit: true,
      target_touch: false,
      risk_proxy_score: 0.44,
      planned_trade_return: 0.008
    },
    metadata: { family: "mean_reversion", stage: "observe", regime: "range", event: "earnings", factor: "reversal_5d" },
    calculated_at: "2026-06-04T07:20:00Z"
  },
  {
    outcome_id: "tpo_mock_003",
    prediction_id: "tp_mock_003",
    strategy_id: "strategy_event_cn",
    stock_code: "002475",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_daily_v1",
    score_status: "partial_daily_only",
    data_quality_status: "ok",
    trade_prediction_score: 0.66,
    outcome_json: {
      direction_hit: true,
      target_touch: true,
      risk_proxy_score: 0.62,
      planned_trade_return: 0.019
    },
    metadata: { family: "event_driven", stage: "graduation_ready", regime: "volatile", event: "supply_chain", factor: "event_strength" },
    calculated_at: "2026-06-03T07:10:00Z"
  },
  {
    outcome_id: "tpo_mock_004",
    prediction_id: "tp_mock_004",
    strategy_id: "strategy_event_cn",
    stock_code: "300750",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_v2",
    score_status: "insufficient_samples",
    data_quality_status: "partial_gap",
    trade_prediction_score: 0.38,
    outcome_json: {
      direction_hit: false,
      target_touch: false,
      risk_proxy_score: 0.31,
      time_bucket_hit_rate: 0.25,
      entry_window_hit: false,
      exit_window_hit: false,
      planned_trade_return: -0.012
    },
    metadata: { family: "event_driven", stage: "candidate", regime: "volatile", event: "policy_shock", factor: "event_strength" },
    calculated_at: "2026-06-03T07:18:00Z"
  }
];

const mockStockRadarRun = {
  run_id: "radar_mock_20260608",
  mode: "dry_run",
  status: "completed",
  started_at: "2026-06-08T14:35:00+08:00",
  completed_at: "2026-06-08T14:36:00+08:00",
  summary: { candidate_count: 2, tier_counts: { alert: 1, watch: 1 }, docs_scanned: 18 },
  degraded_flags: ["llm_unavailable_rules_only", "late_session_volume_disabled", "rss_feeds_not_configured"],
  metadata: { no_trade_instructions: true }
};

const mockStockRadarCandidates = [
  {
    candidate_id: "radar_cand_mock_001",
    run_id: mockStockRadarRun.run_id,
    symbol: "300750",
    stock_name: "CATL",
    tier: "alert",
    radar_score: 84.5,
    event_id: "radar_evt_mock_001",
    event_type: "ai_compute_cooperation",
    direction: "positive",
    summary: "Official announcement matched AI compute cooperation keywords; source is Tier-A CNINFO.",
    source_doc_uids: ["cninfo:mock:001"],
    source_chain: [{ provider: "cninfo", source_tier: "tier_a", url: "https://static.cninfo.com.cn/finalpage/mock.pdf" }],
    extraction: { themes: ["AI", "compute"], confidence: 0.74, llm_status: "unavailable", status: "provisional" },
    confirmations: { late_session_volume: { status: "disabled" }, dragon_tiger: { status: "degraded" } },
    risk_flags: [],
    push_status: "pending"
  },
  {
    candidate_id: "radar_cand_mock_002",
    run_id: mockStockRadarRun.run_id,
    symbol: "600000",
    stock_name: "PF Bank",
    tier: "watch",
    radar_score: 66.0,
    event_id: "radar_evt_mock_002",
    event_type: "buyback",
    direction: "positive",
    summary: "Buyback announcement entered the observation pool; funding confirmation is unavailable.",
    source_doc_uids: ["cninfo:mock:002"],
    source_chain: [{ provider: "cninfo", source_tier: "tier_a", url: "https://static.cninfo.com.cn/finalpage/mock2.pdf" }],
    extraction: { themes: ["buyback"], confidence: 0.68, llm_status: "unavailable", status: "provisional" },
    confirmations: { fund_flow: { status: "degraded" }, late_session_volume: { status: "disabled" } },
    risk_flags: [],
    push_status: "pending"
  }
];

function stockRadarPayload() {
  const digest = [
    "AIASK Stock Radar Digest",
    "run=radar_mock_20260608 status=completed",
    "300750 CATL 84.5 alert ai_compute_cooperation: Official announcement matched AI compute cooperation keywords",
    "600000 PF Bank 66 watch buyback: Buyback announcement entered the observation pool"
  ].join("\n");
  return {
    status: "completed",
    configured: true,
    latest_run: mockStockRadarRun,
    counts: { alert: 1, watch: 1 },
    candidates: mockStockRadarCandidates,
    digest_preview: digest,
    push_logs: [{ push_id: "radar_push_mock", channel: "preview", status: "preview", candidate_count: 2, created_at: "2026-06-08T14:36:10+08:00" }]
  };
}

function queryRecord(query?: URLSearchParams): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  query?.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

function safeLimit(value: unknown, fallback = 100): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(Math.trunc(parsed), 1000)) : fallback;
}

function matchesFilter(item: Record<string, unknown>, filters: Record<string, unknown>, key: string): boolean {
  const value = filters[key];
  if (value === undefined || value === null || value === "") return true;
  return String(item[key] || "") === String(value);
}

function tradePredictionOutcomeItems(filters: Record<string, unknown> = {}) {
  const limit = safeLimit(filters.limit, 100);
  return mockTradePredictionOutcomes
    .filter((item) =>
      ["prediction_id", "strategy_id", "stock_code", "score_version", "score_status", "data_quality_status"].every((key) =>
        matchesFilter(item, filters, key)
      )
    )
    .filter((item) => {
      const date = String(item.actual_trading_date || "");
      const lte = String(filters.actual_trading_date_lte || "");
      const gte = String(filters.actual_trading_date_gte || "");
      if (lte && date > lte) return false;
      if (gte && date < gte) return false;
      return true;
    })
    .slice(0, limit);
}

function tradePredictionStatus(filters: Record<string, unknown> = {}) {
  const outcomes = tradePredictionOutcomeItems(filters);
  const scoreStatusCounts: Record<string, number> = {};
  const scoreVersionCounts: Record<string, number> = {};
  const dataQualityCounts: Record<string, number> = {};
  const scoreDistribution: Record<string, number> = {};
  const scores: number[] = [];
  const evaluated = new Set<string>();
  let partialCount = 0;

  for (const outcome of outcomes) {
    const scoreStatus = String(outcome.score_status || "unknown");
    const scoreVersion = String(outcome.score_version || "unknown");
    const dataQuality = String(outcome.data_quality_status || "unknown");
    scoreStatusCounts[scoreStatus] = (scoreStatusCounts[scoreStatus] || 0) + 1;
    scoreVersionCounts[scoreVersion] = (scoreVersionCounts[scoreVersion] || 0) + 1;
    dataQualityCounts[dataQuality] = (dataQualityCounts[dataQuality] || 0) + 1;
    evaluated.add(String(outcome.prediction_id));
    if (["partial_daily_only", "partial_intraday_missing", "insufficient_samples", "post_hoc_rejected"].includes(scoreStatus)) {
      partialCount += 1;
    }
    const score = Number(outcome.trade_prediction_score);
    if (Number.isFinite(score)) {
      scores.push(score);
      const bucket = score >= 0.8 ? "0.80-1.00" : score >= 0.6 ? "0.60-0.79" : score >= 0.4 ? "0.40-0.59" : score >= 0.2 ? "0.20-0.39" : "0.00-0.19";
      scoreDistribution[bucket] = (scoreDistribution[bucket] || 0) + 1;
    }
  }

  const pendingCount = filters.strategy_id || filters.stock_code ? 0 : 1;
  return {
    object: "trade_prediction.status",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    prediction_count: outcomes.length + pendingCount,
    outcome_count: outcomes.length,
    sample_n: evaluated.size,
    pending_count: pendingCount,
    evaluated_count: evaluated.size,
    partial_count: partialCount,
    prediction_status_counts: { frozen: outcomes.length, pending: pendingCount },
    score_status_counts: scoreStatusCounts,
    latest_score_status_counts: scoreStatusCounts,
    score_version_counts: scoreVersionCounts,
    data_quality_status_counts: dataQualityCounts,
    latest_data_quality_status_counts: dataQualityCounts,
    score_distribution: scoreDistribution,
    score_summary: {
      avg: scores.length ? Number((scores.reduce((sum, score) => sum + score, 0) / scores.length).toFixed(6)) : null,
      min: scores.length ? Math.min(...scores) : null,
      max: scores.length ? Math.max(...scores) : null
    }
  };
}

function tradePredictionOutcomes(filters: Record<string, unknown> = {}) {
  const items = tradePredictionOutcomeItems(filters);
  return {
    object: "trade_prediction.outcomes",
    status: "ready",
    configured: true,
    items,
    count: items.length
  };
}

function tradePredictionMatrix(filters: Record<string, unknown> = {}) {
  const rawDimensions = filters.dimensions;
  const dimensions = Array.isArray(rawDimensions)
    ? rawDimensions.map(String).filter(Boolean)
    : String(rawDimensions || "family,stage,regime,event,factor").split(",").map((item) => item.trim()).filter(Boolean);
  const items = tradePredictionOutcomeItems(filters);
  const cells = new Map<string, { dimension: string; value: string; scores: number[]; directionHits: number; targetTouches: number; statusCounts: Record<string, number>; dataQualityCounts: Record<string, number> }>();
  for (const item of items) {
    const metadata = (item.metadata || {}) as Record<string, unknown>;
    const outcomeJson = (item.outcome_json || {}) as Record<string, unknown>;
    for (const dimension of dimensions) {
      const value = String(metadata[dimension] || "unknown");
      const key = `${dimension}:${value}`;
      const cell = cells.get(key) || { dimension, value, scores: [], directionHits: 0, targetTouches: 0, statusCounts: {}, dataQualityCounts: {} };
      const score = Number(item.trade_prediction_score);
      if (Number.isFinite(score)) cell.scores.push(score);
      if (outcomeJson.direction_hit) cell.directionHits += 1;
      if (outcomeJson.target_touch) cell.targetTouches += 1;
      const status = String(item.score_status || "unknown");
      const quality = String(item.data_quality_status || "unknown");
      cell.statusCounts[status] = (cell.statusCounts[status] || 0) + 1;
      cell.dataQualityCounts[quality] = (cell.dataQualityCounts[quality] || 0) + 1;
      cells.set(key, cell);
    }
  }
  const rows = Array.from(cells.values())
    .map((cell) => {
      const sample_n = cell.scores.length;
      const scoreAvg = sample_n ? cell.scores.reduce((sum, score) => sum + score, 0) / sample_n : null;
      const scoreLcb = scoreAvg === null || sample_n === 0 ? null : Math.max(0, scoreAvg - 1.96 * Math.sqrt((scoreAvg * (1 - scoreAvg)) / sample_n));
      return {
        dimension: cell.dimension,
        value: cell.value,
        sample_n,
        score_avg: scoreAvg === null ? null : Number(scoreAvg.toFixed(6)),
        score_lcb_95: scoreLcb === null ? null : Number(scoreLcb.toFixed(6)),
        direction_hit_rate: sample_n ? Number((cell.directionHits / sample_n).toFixed(6)) : null,
        target_touch_rate: sample_n ? Number((cell.targetTouches / sample_n).toFixed(6)) : null,
        score_status_counts: cell.statusCounts,
        data_quality_status_counts: cell.dataQualityCounts
      };
    })
    .sort((left, right) => String(left.dimension).localeCompare(String(right.dimension)) || right.sample_n - left.sample_n);
  return {
    object: "trade_prediction.matrix",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    score_version: filters.score_version ? String(filters.score_version) : null,
    dimensions,
    rows,
    row_count: rows.length
  };
}

function capabilities(): CapabilityWorkbenchPayload {
  const allTools = [...financeTools, ...hermesTools];
  return {
    object: "aiask.desktop_capabilities",
    summary: {
      status: "implemented",
      source: "mock_fixture",
      counts: { implemented: 42, live_unverified: 3, unconfigured: 2, failed: 0 },
      issue_count: 0,
      control: {
        authorized: true,
        full_mode_enabled: true,
        control_token_configured: true,
        control_authorized: true,
        reason: null
      },
      refreshed_at: Date.now() / 1000
    },
    hermes: {
      status: {
        object: "aiask.hermes_status",
        implementation: "aiask_native",
        baseline: "Hermes full parity",
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        full_mode_active: true,
        evaluated_toolset: "general_full"
      },
      parity: {
        object: "aiask.capability_parity",
        baseline: "hermes_native",
        scope: "hermes_full_runtime",
        embedded_vendor_runtime: false,
        required_count: 12,
        covered_count: 12,
        complete_count: 11,
        coverage_ratio: 1,
        complete_ratio: 0.92,
        status: "implemented",
        strict_status: "in_progress",
        matrix: [],
        v014_delta: {
          total: 4,
          implemented_count: 3,
          partial_count: 1,
          missing_count: 0,
          implemented: [{ reference: "browser_snapshot", area: "browser", aiask_tools: ["agent_browser_snapshot"], missing_aiask_tools: [], status: "implemented" }],
          partial: [{ reference: "rl_training", area: "rl", aiask_tools: ["agent_rl_list_environments"], missing_aiask_tools: [], status: "skipped_missing_credentials", required_env: ["TINKER_API_KEY"] }],
          missing: []
        }
      },
      readiness: { status: "ready" },
      tool_mapping: allTools.map((tool) => ({
        hermes_tool: tool.name.replace(/^agent_/, ""),
        reference: tool.name,
        area: tool.category || "tool",
        aiask_tools: [tool.name],
        missing_aiask_tools: [],
        status: tool.side_effect === "read_only" ? "implemented" : "live_unverified"
      })),
      platform_mapping: [{ platform: "discord", reference: "discord_server", area: "delivery", aiask_tools: ["agent_discord_server"], missing_aiask_tools: [], status: "skipped_missing_credentials" }],
      feature_mapping: [
        { feature: "dynamic_mcp_tools", reference: "dynamic_mcp_tools", area: "mcp", aiask_tools: ["agent_mcp_manage"], missing_aiask_tools: [], status: "implemented" },
        { feature: "native_plugins", reference: "dynamic_plugin_tools", area: "plugins", aiask_tools: ["agent_plugin_manage"], missing_aiask_tools: [], status: "implemented" },
        { feature: "learning_loop", reference: "learning_loop", area: "learning", aiask_tools: ["agent_learning_status"], missing_aiask_tools: [], status: "implemented" }
      ],
      issues: [],
      providers: { status: "ready", configured_count: 1 },
      memory: {
        object: "aiask.memory_provider_status",
        status: "implemented",
        active_provider: "sqlite",
        default_provider: "sqlite",
        providers: [
          { name: "sqlite", type: "sqlite", configured: true, status: "implemented", capabilities: ["save", "search", "status"] },
          { name: "vector", type: "semantic_memory", configured: false, status: "skipped_missing_credentials", required_env: ["AIASK_VECTOR_MEMORY_URL"] }
        ],
        secrets_redacted: true
      },
      acp: { status: "ready" },
      security: { status: "ready" },
      skill_packs: { object: "skill_packs", status: "ready", available_count: 2, packs: [{ name: "finance" }, { name: "desktop" }] }
    },
    mcp: {
      gated: false,
      registration_status: "registered",
      discovery_status: "discovered",
      discovered_counts: { tools: 4, resources: 1, prompts: 1 },
      configured: true,
      config_path: "mock://aiask/mcp_servers.json",
      config_exists: true,
      detected_service_port: "3100",
      detected_service_url: "http://127.0.0.1:3100/mcp",
      suggested_registration_url: "http://127.0.0.1:3100/mcp",
      auth_configured: false,
      auth_env_vars: ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"],
      missing_auth_env_vars: ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"],
      error_code: null,
      detail: null,
      servers: [{ name: "akshare-local", domain: "finance", transport: "streamable_http", configured: true }],
      tools: [
        { server: "akshare-local", name: "get_realtime_quote", wrapped_name: "agent_mcp_akshare_get_realtime_quote", domain: "quote", description: "实时行情" },
        { server: "akshare-local", name: "get_kline", wrapped_name: "agent_mcp_akshare_get_kline", domain: "kline", description: "K 线数据" },
        { server: "akshare-local", name: "get_macro_indicator", wrapped_name: "agent_mcp_akshare_get_macro_indicator", domain: "macro", description: "宏观指标" },
        { server: "akshare-local", name: "get_option_chain", wrapped_name: "agent_mcp_akshare_get_option_chain", domain: "options", description: "期权链" }
      ],
      resources: [{ uri: "aiask://quotes", name: "行情资源" }],
      prompts: [{ name: "risk-review", description: "风险复盘提示词" }],
      oauth: [{ server: "akshare-local", status: "missing", error: "需要授权" }]
    },
    strategy_factory: strategyFactory(),
    quant: { data_status: { status: "ready" }, status: "ready" },
    financial_system: {
      object: "aiask.financial_readiness",
      status: "ready",
      production_ready: false,
      required_gates: [
        { name: "approval_intents", status: "ready", required: true, detail: "Mock intent gate ready" },
        {
          name: "semantic_search",
          status: "ready",
          required: true,
          detail: "Memory search and session search probes are callable",
          evidence: {
            active_provider: "sqlite",
            memory_tool_registered: true,
            session_tool_registered: true,
            memory_probe_success: true,
            session_probe_success: true
          }
        }
      ],
      optional_gates: [
        {
          name: "vector_provider",
          status: "degraded",
          required: false,
          detail: "External vector memory provider is optional; built-in SQLite memory/session search remains the readiness baseline",
          evidence: {
            active_provider: "sqlite",
            configured: false,
            required_env: ["AIASK_VECTOR_MEMORY_URL"]
          }
        }
      ],
      next_actions: [
        {
          action_id: "run_live_financial_workflow",
          title: "运行一次只读金融工作流",
          detail: "先运行金融经理台只读查询，再运行量化研究，确认报告完成或明确被数据新鲜度阻塞。",
          priority: "recommended",
          target_page: "financial-manager",
          endpoint: "/v1/desktop/financial-manager/query"
        },
        {
          action_id: "configure_mcp_auth",
          title: "配置 MCP 授权变量",
          detail: "Mock AKShare MCP 已注册但缺少授权变量；真实环境中请在 Agent 进程配置后刷新发现。",
          priority: "recommended",
          target_page: "mcp-connectors",
          endpoint: "/v1/mcp/tools",
          env_vars: ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"],
          gate: "mcp_aggregation"
        }
      ],
      live_smoke: {
        object: "aiask.live_smoke_checklist",
        status: "ready",
        script: "scripts/ops/live_readiness_smoke.py",
        working_directory: "packages/agent",
        self_test_command: "uv run python ..\\..\\scripts\\ops\\live_readiness_smoke.py --self-test --pretty",
        live_command: "uv run python ..\\..\\scripts\\ops\\live_readiness_smoke.py --endpoint http://127.0.0.1:8767 --pretty",
        environment_note: "Run from packages/agent so the Agent runtime dependencies are loaded; root or system Python may report missing FastAPI/pandas dependencies.",
        checks: [
          { name: "health", method: "GET", path: "/health/detailed" },
          { name: "tools", method: "GET", path: "/v1/tools" },
          { name: "financial_readiness", method: "GET", path: "/v1/financial-system/readiness" },
          { name: "workbench_summary", method: "GET", path: "/v1/desktop/workbench/summary?session_limit=5&run_limit=5" },
          { name: "memory_status", method: "GET", path: "/v1/desktop/settings/status" },
          { name: "session_search", method: "GET", path: "/v1/search?query=AIASK&limit=5" },
          { name: "memory_search", method: "POST", path: "/v1/tools/agent_memory_search" },
          { name: "mcp_servers", method: "GET", path: "/v1/mcp/servers?all=true" },
          { name: "mcp_tools", method: "GET", path: "/v1/mcp/tools?all=true" },
          { name: "financial_manager_catalog", method: "GET", path: "/v1/desktop/financial-manager/catalog" },
          { name: "financial_manager_query", method: "POST", path: "/v1/desktop/financial-manager/query" },
          { name: "data_status", method: "GET", path: "/v1/desktop/data/status?codes=600519,000001&max_stale_days=5" },
          { name: "factory_status", method: "POST", path: "/v1/tools/agent_factory_status", observes: ["success", "configured", "database_configured", "run_count"] },
          { name: "market_temperature_cache", method: "POST", path: "/v1/tools/agent_market_temperature_cache_readiness", observes: ["ready", "status", "blockers", "warnings"] },
          { name: "market_temperature_forward_validation", method: "POST", path: "/v1/tools/agent_market_temperature_forward_validation", observes: ["benchmark_status", "quality_status", "warnings", "sample_count"] },
          { name: "quant_research", method: "POST", path: "/v1/desktop/quant/research-runs" }
        ]
      },
      summary: { ready: 1 },
      disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
    },
    skills: { gated: false, root: "mock://aiask/skills", skills: [{ name: "risk-review", description: "风险复盘", path: "mock://skills/risk-review" }] },
    skill_packs: { object: "skill_packs", status: "ready", available_count: 2, packs: [{ name: "finance" }] },
    plugins: [{ name: "audit-plugin", enabled: true, source: "mock", description: "审计钩子", tools: [{ name: "ping" }], commands: [], hooks: [] }],
    providers: { status: "ready" },
    memory: {
      object: "aiask.memory_provider_status",
      status: "implemented",
      active_provider: "sqlite",
      default_provider: "sqlite",
      providers: [
        { name: "sqlite", type: "sqlite", configured: true, status: "implemented", capabilities: ["save", "search", "status"] },
        { name: "vector", type: "semantic_memory", configured: false, status: "skipped_missing_credentials", required_env: ["AIASK_VECTOR_MEMORY_URL"] }
      ],
      secrets_redacted: true
    },
    acp: { status: "ready" },
    security: { status: "ready" },
    ai: aiStatus(),
    raw_refs: { backend: "mock://aiask" }
  };
}

function settingsStatus() {
  return {
    object: "aiask.desktop_settings_status",
    agent: {
      toolset: "general_full",
      model: "gpt-5.4",
      max_iterations: 8,
      api_token_configured: true,
      control_token_configured: true,
      control_authorized: true,
      control_reason: "mock_authorized"
    },
    llm: {
      ai_status: aiStatus(),
      providers: { status: "ready", configured_count: 1, providers: [{ name: "project-root-api", type: "openai_compatible", model: "gpt-5.4", configured: true, status: "ready" }] }
    },
    memory: {
      object: "aiask.memory_provider_status",
      status: "implemented",
      active_provider: "sqlite",
      default_provider: "sqlite",
      providers: [
        { name: "sqlite", type: "sqlite", configured: true, status: "implemented", path: "mock://aiask/agent_state.sqlite3", capabilities: ["save", "search", "status"] },
        { name: "vector", type: "semantic_memory", configured: false, status: "skipped_missing_credentials", required_env: ["AIASK_VECTOR_MEMORY_URL"] }
      ],
      secrets_redacted: true
    },
    databases: {
      agent_state: { path: "mock://aiask/agent_state.sqlite3", writable: true },
      intent_state: { path: "mock://aiask/intents.sqlite3", writable: true },
      quant_research: { path: "mock://aiask/quant.sqlite3", writable: true },
      akshare: { path: "mock://aiask/akshare.sqlite3", writable: true }
    },
    profile,
    secrets_redacted: true
  };
}

function createIntent(body: Record<string, unknown>) {
  const id = `intent_mock_${intents.size + 1}`;
  const intent = {
    intent_id: id,
    action: body.action || "mock.action",
    target_tool: "agent_action_intent_create",
    target_action: body.action || "mock.action",
    status: "awaiting_confirmation",
    params: body.params || {},
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  };
  intents.set(id, intent);
  return envelope("agent_action_intent_create", { intent });
}

function toolResult(tool: string, body: Record<string, unknown>) {
  if (tool === "agent_tool_catalog") return envelope(tool, { tools: [...financeTools, ...hermesTools] });
  if (tool === "agent_quant_data_gate") return envelope(tool, { status: "passed", codes: body.codes || ["600519"], missing: [], stale: [] });
  if (tool === "agent_market_temperature_snapshot") return envelope(tool, marketTemperatureSnapshot(body));
  if (tool === "agent_market_temperature_cache_readiness") return envelope(tool, marketTemperatureCacheReadiness(body));
  if (tool === "agent_market_temperature_cache_history") return envelope(tool, marketTemperatureCacheHistory(body));
  if (tool === "agent_market_temperature_industry_history") return envelope(tool, marketTemperatureIndustryHistory(body));
  if (tool === "agent_market_temperature_industry_constituents") return envelope(tool, marketTemperatureIndustryConstituents(body));
  if (tool === "agent_market_temperature_forward_validation") return envelope(tool, marketTemperatureForwardValidation(body));
  if (tool === "agent_factor_validation") return envelope(tool, { status: "passed", ic_mean: 0.04, factors: body.factors || ["momentum"] });
  if (tool === "agent_backtest_suite") return envelope(tool, { status: "completed", sharpe: 1.2, max_drawdown: -0.08 });
  if (tool === "agent_portfolio_risk") return envelope(tool, { status: "completed", var_95: -0.021, stress: "passed" });
  if (tool === "agent_analyze_stock") {
    const code = String(body.code || body.stock_code || body.symbol || "600519");
    return envelope(tool, {
      status: "ready",
      code,
      rating: "mock_watch",
      risk: "medium",
      decision: body.include_decision ? "observe_only" : "not_requested",
      summary: { signal: "watch", source: "desktop.mockApi", investment_advice: false }
    });
  }
  if (tool === "agent_factory_status") return strategyFactory().status;
  if (tool === "agent_factory_runs") return strategyFactory().runs;
  if (tool === "agent_strategy_review_snapshot") return strategyFactory().review_snapshot;
  if (tool === "agent_incubation_factory_status") return envelope(tool, { run_count: 3, error_count: 0, last_result_status: "completed" });
  if (tool === "agent_strategy_domain_events") return envelope(tool, { events: [{ event_type: body.event_type || "factory.run_completed", payload: { decision: "review" } }] });
  if (tool === "agent_trade_prediction_status") return envelope(tool, tradePredictionStatus(body));
  if (tool === "agent_trade_prediction_outcomes") return envelope(tool, tradePredictionOutcomes(body));
  if (tool === "agent_trade_prediction_matrix") return envelope(tool, tradePredictionMatrix(body));
  if (tool === "agent_stock_radar_status") return envelope(tool, stockRadarPayload());
  if (tool === "agent_stock_radar_candidates") return envelope(tool, { status: "ready", candidates: mockStockRadarCandidates, count: mockStockRadarCandidates.length });
  if (tool === "agent_stock_radar_digest") return envelope(tool, stockRadarPayload());
  if (tool === "agent_factory_event_list") {
    const events = [
      {
        event_id: "evt_mock_001",
        event_name: "稀土出口管制(mock)",
        event_type: "policy_shock",
        event_source: "manual",
        status: body.status || "active",
        direction: "bullish",
        intensity: 0.85,
        confidence: 0.7,
        primary_themes: ["critical_minerals", "rare_earth"],
        operator_id: "operator_alice",
        approver_id: "approver_bob",
        created_at: "2026-05-24T08:00:00Z",
        valid_from: "2026-05-24T08:00:00Z",
        valid_until: "2026-06-24T08:00:00Z"
      },
      {
        event_id: "evt_mock_002",
        event_name: "AI 芯片新规(mock)",
        event_type: "regulation",
        event_source: "news_llm",
        status: "pending_review",
        direction: "bearish",
        intensity: 0.6,
        confidence: 0.55,
        primary_themes: ["AI_chip"],
        operator_id: "news_pipeline",
        approver_id: null,
        created_at: "2026-05-24T07:30:00Z",
        valid_from: "2026-05-24T07:30:00Z",
        valid_until: "2026-05-31T07:30:00Z"
      }
    ];
    return envelope(tool, { events, count: events.length });
  }
  if (tool === "agent_factory_event_preview_tasks") {
    return envelope(tool, {
      event_id: body.event_id || "evt_mock_001",
      impacts: [
        { theme_code: "critical_minerals", depth: 0, magnitude: 0.85, source_path: "primary" },
        { theme_code: "rare_earth", depth: 0, magnitude: 0.85, source_path: "primary" },
        { theme_code: "metals_processing", depth: 1, magnitude: 0.42, source_path: "critical_minerals -> metals_processing" }
      ],
      candidate_symbols: ["600111", "600259", "600392", "002460", "300618"],
      target_count: 5,
      warnings: [],
      preview_mode: "real_bfs"
    });
  }
  if (tool === "agent_factory_event_lineage") return envelope(tool, { lineage: [{ event_id: body.event_id || "evt_mock_001", task_id: "task_mock", status: "planned" }] });
  if (tool === "agent_factory_theme_exposure_status") return envelope(tool, { status: "ready", exposures: [{ theme: body.theme || "AI_chip", exposure: 0.42 }] });
  if (tool === "agent_factory_event_outbox_status") return envelope(tool, { counts: { pending: 0, sent: 2 }, latest: [] });
  // PR-G (Phase 5, 2026-05-24): factory event trigger console mocks so
  // the new ``Factory Events`` view renders without a backend.
  if (tool === "agent_strategy_manager") {
    const action = String(body.action || "");
    let parsedKwargs: Record<string, unknown> = {};
    if (typeof body.kwargs === "string") {
      try { parsedKwargs = JSON.parse(body.kwargs as string); } catch { parsedKwargs = {}; }
    } else if (body.kwargs && typeof body.kwargs === "object") {
      parsedKwargs = body.kwargs as Record<string, unknown>;
    }
    if (action === "factory_event_list") {
      const events = [
        {
          event_id: "evt_mock_001",
          event_name: "稀土出口管制(mock)",
          event_type: "policy_shock",
          event_source: "manual",
          status: parsedKwargs.status || "active",
          direction: "bullish",
          intensity: 0.85,
          confidence: 0.7,
          primary_themes: ["critical_minerals", "rare_earth"],
          operator_id: "operator_alice",
          approver_id: "approver_bob",
          created_at: "2026-05-24T08:00:00Z",
          valid_from: "2026-05-24T08:00:00Z",
          valid_until: "2026-06-24T08:00:00Z"
        },
        {
          event_id: "evt_mock_002",
          event_name: "AI 芯片新规(mock)",
          event_type: "regulation",
          event_source: "news_llm",
          status: "pending_review",
          direction: "bearish",
          intensity: 0.6,
          confidence: 0.55,
          primary_themes: ["AI_chip"],
          operator_id: "news_pipeline",
          approver_id: null,
          created_at: "2026-05-24T07:30:00Z",
          valid_from: "2026-05-24T07:30:00Z",
          valid_until: "2026-05-31T07:30:00Z"
        }
      ];
      return envelope(tool, { events, count: events.length });
    }
    if (action === "factory_event_preview_tasks") {
      return envelope(tool, {
        event_id: parsedKwargs.event_id || "evt_mock_001",
        impacts: [
          { theme_code: "critical_minerals", depth: 0, magnitude: 0.85, source_path: "primary" },
          { theme_code: "rare_earth", depth: 0, magnitude: 0.85, source_path: "primary" },
          { theme_code: "metals_processing", depth: 1, magnitude: 0.42, source_path: "critical_minerals -> metals_processing" }
        ],
        candidate_symbols: ["600111", "600259", "600392", "002460", "300618"],
        target_count: 5,
        warnings: [],
        preview_mode: "real_bfs"
      });
    }
    return envelope(tool, { action, message: "mock strategy_manager handler" });
  }
  if (tool === "agent_memory_search") return envelope(tool, { items: [{ memory_id: "mem_mock", content: "mock memory hit", user_id: body.user_id || "local" }] });
  if (tool === "agent_session_search") return envelope(tool, { items: [{ session_id: "sess_mock", content: "mock session hit", user_id: body.user_id || "local" }] });
  if (tool === "agent_file_list") return envelope(tool, { entries: [{ path: "README.md", type: "file" }, { path: "desktop", type: "directory" }] });
  if (tool === "agent_file_read") return envelope(tool, { path: body.path || "README.md", text: "Mock file content preview." });
  if (tool === "agent_terminal_backends") return envelope(tool, { backends: [{ name: "local-powershell", status: "ready" }] });
  if (tool === "agent_browser_snapshot") return envelope(tool, { title: "AIASK Desktop Mock", url: "mock://browser", nodes: [{ role: "main", name: "Unified console" }] });
  if (tool === "agent_browser_console") return envelope(tool, { messages: [] });
  if (tool === "agent_web_search") return envelope(tool, { results: [{ title: "AIASK mock result", url: "https://example.com/aiask" }] });
  if (tool === "agent_skill_list") return envelope(tool, capabilities().skills);
  if (tool === "agent_plugin_list") return envelope(tool, { plugins: capabilities().plugins });
  if (tool === "agent_mcp_manage") return envelope(tool, { servers: capabilities().mcp.servers, tools: capabilities().mcp.tools });
  if (tool === "agent_model_manage") return envelope(tool, aiStatus());
  if (tool === "agent_memory_manage") return envelope(tool, { status: "ready", provider: "sqlite", user_id: body.user_id || profile.user_id });
  if (tool === "agent_gateway_status") return envelope(tool, { status: "ready", enabled_platforms: ["desktop"] });
  if (tool === "agent_gateway_platforms") return envelope(tool, { platforms: [{ platform: "desktop", status: "ready" }] });
  if (tool === "agent_learning_status") return envelope(tool, { status: "ready", proposal_count: 1 });
  if (tool === "agent_learning_review") return envelope(tool, { proposals: [{ proposal_id: "learn_mock", status: "pending_review" }] });
  if (tool === "agent_rl_list_environments") return envelope(tool, { environments: [{ id: "finance_safe_eval", status: "ready" }] });
  if (tool === "agent_rl_get_config") return envelope(tool, { status: "configured", secrets_redacted: true });
  if (tool === "agent_security_scan") {
    return envelope(tool, {
      status: "completed",
      target: body.text ? "text" : body.path || ".",
      include_env: false,
      findings: [],
      secrets_redacted: true,
      arguments: body
    });
  }
  if (tool === "agent_job_list") return envelope(tool, { jobs });
  return envelope(tool, { status: "mock_ok", arguments: body });
}

function quantResearchArtifact(researchId = "research_mock") {
  const stages = [
    { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum", "volatility"], benchmark: "000300" }, error: null },
    { name: "data_gate", status: "completed", output: { status: "ready", ready: true, missing: [], stale: [], coverage: { requested: 2, ready: 2 } }, error: null },
    { name: "factor_validation", status: "completed", output: { status: "passed", ic_mean: 0.041, coverage: 0.92, redundant_factors: [] }, error: null },
    { name: "backtest_suite", status: "completed", output: { status: "completed", oos_sharpe: 1.12, max_drawdown: -0.082, turnover: 0.18 }, error: null },
    { name: "portfolio_risk", status: "completed", output: { status: "completed", var_95: -0.021, concentration: "medium", stress: "passed" }, error: null },
    { name: "strategy_factory_review", status: "completed", output: { status: "reviewing", recommendation: "observe", decision: "not_promoted" }, error: null }
  ];
  return {
    research_id: researchId,
    status: "completed",
    payload: { stages },
    report: {
      object: "aiask.quant_research_report",
      research_id: researchId,
      status: "completed",
      summary: { benchmark: "000300", universe_size: 2, factor_count: 2, failed_stage: null },
      universe: ["600519", "000001"],
      backtest_assumptions: { cost_bps: 3, slippage_bps: 1, benchmark: "000300", rebalance_frequency: "monthly" },
      backtest: { oos_sharpe: 1.12, walk_forward_score: 0.68, max_drawdown: -0.082 },
      portfolio_risk: { var_95: -0.021, concentration: "medium", stress: "passed" },
      strategy_factory: { status: "reviewing", recommendation: "observe", decision: "not_promoted" },
      limitations: ["Mock research is decision support only."],
      stages,
      disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
    }
  };
}

function parsePath(path: string): { cleanPath: string; query: URLSearchParams } {
  const [cleanPath, query = ""] = path.split("?");
  return { cleanPath, query: new URLSearchParams(query) };
}

function ok<T>(payload: T): Promise<T> {
  return Promise.resolve(payload);
}

export async function mockRequestJson<T>(path: string, options: MockOptions = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const body = (options.body && typeof options.body === "object" ? options.body : {}) as Record<string, unknown>;
  const { cleanPath, query } = parsePath(path);

  if (cleanPath === "/health" || cleanPath === "/health/detailed") {
    return ok({
      status: "ok",
      service: "AIASK Agent Mock",
      runtime: { model: "gpt-5.4", max_iterations: 8 },
      tools: { count: financeTools.length + hermesTools.length, names: [...financeTools, ...hermesTools].map((tool) => tool.name), toolset: "general_full" },
      hermes: { mode: "hermes_full", full_mode_enabled: true, full_mode_active: true, parity: capabilities().hermes.parity },
      control: { loopback_only: true, token_configured: true }
    } as T);
  }
  if (cleanPath === "/v1/tools" || cleanPath === "/v1/hermes/tools") return ok({ data: cleanPath.includes("hermes") ? [...financeTools, ...hermesTools] : financeTools } as T);
  if (cleanPath === "/v1/desktop/capabilities") return ok(capabilities() as T);
  if (cleanPath === "/v1/desktop/workbench/summary") return ok({ object: "aiask.desktop.workbench.summary", ...mockWorkbenchSummary() } as T);
  if (cleanPath === "/v1/desktop/runs") return ok({ object: "list", data: mockRunSummaries } as T);
  if (cleanPath === "/v1/desktop/settings/status") return ok(settingsStatus() as T);
  if (cleanPath === "/v1/desktop/data/status") return ok(dataStatus() as T);
  if (cleanPath === "/v1/desktop/data/sync-plan") {
    return ok({
      object: "aiask.desktop_data_sync_plan",
      status: "ready",
      data_status: dataStatus(),
      intent_request: {
        action: "data_sync.sync",
        params: {
          codes: body.codes || ["600519"],
          task_type: body.task_type || "kline",
          period: body.period || "daily",
          limit: body.task_type === "market_temperature_snapshot_cache" ? 1000 : undefined,
          top_n: body.task_type === "market_temperature_snapshot_cache" ? 20 : undefined,
          min_bars: body.task_type === "market_temperature_snapshot_cache" ? 20 : undefined
        },
        rationale: "Mock sync plan approval."
      },
      side_effect: { level: "stateful", confirmation_required: true },
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/users/local-profile" && method === "GET") return ok(profile as T);
  if (cleanPath === "/v1/desktop/users/local-profile" && ["POST", "PATCH"].includes(method)) {
    profile = { ...profile, user_id: String(body.user_id || profile.user_id), profile_name: String(body.profile_name || profile.profile_name), updated_at: "2026-05-22T09:05:00Z" };
    return ok(profile as T);
  }
  if (cleanPath === "/v1/desktop/factor-factory/status") {
    return ok({
      object: "aiask.factor_factory_status",
      status: "ready",
      configured: true,
      factory: { initialized: true, pool_loaded_from_db: true, pool_size: 2, run_count: 4 },
      active_factors: [{ factor_id: "factor_momentum", name: "momentum_20d", family: "momentum", quality_score: 0.74 }],
      engine_health: { llm_primary: "ready", gp_classic: "ready", rule_seed: "ready" },
      pool_health: { active_promoted_count: 1, quarantine_count: 0 },
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/status") {
    return ok(envelope("agent_trade_prediction_status", tradePredictionStatus(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/outcomes") {
    return ok(envelope("agent_trade_prediction_outcomes", tradePredictionOutcomes(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/desktop/trade-predictions/matrix") {
    return ok(envelope("agent_trade_prediction_matrix", tradePredictionMatrix(queryRecord(query))) as T);
  }
  if (cleanPath === "/v1/ai/status") return ok(aiStatus() as T);
  if (cleanPath === "/v1/ai/smoke") return ok({ object: "aiask.ai_smoke", configured: true, success: true, provider: "project-root-api", model: body.model || "gpt-5.4", mock: true, latency_ms: 5, response_preview: "AI_SMOKE_PASSED", secrets_redacted: true } as T);
  if (cleanPath === "/v1/ai/models") return ok({ data: [{ id: "gpt-5.4", object: "model", owned_by: "project-root-api" }, { id: "gpt-5.4-mini", object: "model", owned_by: "project-root-api" }], configured: true } as T);
  if (cleanPath === "/v1/responses") return ok({ id: "resp_mock", object: "response", status: "completed", output_text: "AIASK_OK", metadata: { session_id: body.session_id || "sess_mock", run_id: "run_mock", mode: body.mode || "finance_safe", audit_events: [{ event: "mock" }] } } as T);
  const responseMatch = cleanPath.match(/^\/v1\/responses\/([^/]+)$/);
  if (responseMatch) {
    const responseId = decodeURIComponent(responseMatch[1]);
    if (method === "DELETE") return ok({ id: responseId, object: "response.deleted", deleted: true } as T);
    return ok({ id: responseId, object: "response", status: "completed", output_text: "AIASK_OK", metadata: { session_id: "sess_mock", run_id: "run_mock", mode: "finance_safe", audit_events: [{ event: "mock" }] } } as T);
  }
  const runActionMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)(?:\/(cancel|stop|steer))?$/);
  if (runActionMatch && !cleanPath.endsWith("/events")) {
    const runId = decodeURIComponent(runActionMatch[1]);
    const action = runActionMatch[2];
    if (!action) return ok({ object: "run", run_id: runId, status: "completed", payload: { mock: true } } as T);
    return ok({ object: action === "steer" ? "run.steer" : "run", run_id: runId, status: action === "steer" ? "running" : "cancelled", event: { event: `run.${action}`, data: body } } as T);
  }
  if (cleanPath === "/v1/runs/run_mock/events" || cleanPath === "/v1/runs/run_mock/events/stream") {
    return ok({ object: "list", data: mockRunEvents } as T);
  }
  if (cleanPath === "/v1/search") return ok({ object: "list", data: [{ kind: "response", object_id: "resp_mock", session_id: "sess_mock", user_id: profile.user_id, content: "Mock 回复命中" }] } as T);
  if (cleanPath === "/v1/hermes/sessions") return ok({ object: "list", data: mockSessionSummaries } as T);
  if (cleanPath.startsWith("/v1/sessions/") && cleanPath.endsWith("/messages")) {
    return ok({ object: "list", data: [{ message_id: "msg_user", role: "user", content: "mock question" }, { message_id: "msg_assistant", role: "assistant", content: "mock answer" }] } as T);
  }
  if (cleanPath === "/v1/hermes/status" || cleanPath === "/v1/capabilities/parity" || cleanPath === "/v1/hermes/readiness") {
    const payload = cleanPath.includes("parity") ? capabilities().hermes.parity : cleanPath.includes("readiness") ? capabilities().hermes.readiness : capabilities().hermes.status;
    return ok(payload as T);
  }
  if (cleanPath === "/v1/hermes/toolsets") {
    return ok({
      object: "list",
      data: [
        { name: "finance_safe", default: false, enabled: true },
        { name: "general_full", default: true, enabled: true }
      ]
    } as T);
  }
  if (cleanPath === "/v1/hermes/config") {
    return ok({
      object: "aiask.hermes_config",
      toolset: "general_full",
      general_tools_enabled: true,
      control_token_configured: true,
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/financial-system/readiness") return ok(capabilities().financial_system as T);

  if (cleanPath === "/v1/processes") {
    return ok({ object: "list", data: [{ pid: "mock-agent", name: "AIASK Agent Mock", status: "running", source: "desktop.mockApi" }] } as T);
  }
  if (cleanPath === "/v1/browser/sessions") {
    return ok({ object: "list", data: [{ name: "default", provider: "playwright", persistent: true, status: "ready" }] } as T);
  }
  if (cleanPath === "/v1/terminal/backends") {
    return ok({ object: "list", data: [{ name: "local-powershell", shell: "powershell", status: "ready", read_only_probe: true }] } as T);
  }
  const terminalBackendSessionsMatch = cleanPath.match(/^\/v1\/terminal\/backends\/([^/]+)\/sessions$/);
  if (terminalBackendSessionsMatch) {
    const backend = decodeURIComponent(terminalBackendSessionsMatch[1]);
    const limit = Number(query.get("limit") || 200);
    return ok({
      object: "list",
      backend,
      data: [
        {
          session_id: "terminal_mock",
          backend,
          status: "idle",
          user_id: profile.user_id,
          shell: backend.includes("powershell") ? "powershell" : "terminal",
          updated_at: "2026-05-22T09:00:00Z"
        }
      ].slice(0, limit)
    } as T);
  }
  if (cleanPath === "/v1/terminal/sessions") {
    return ok({ object: "list", data: [{ session_id: "terminal_mock", backend: "local-powershell", status: "idle", user_id: profile.user_id }] } as T);
  }
  if (cleanPath === "/v1/gateway/status") {
    return ok({ object: "aiask.gateway_status", status: "ready", enabled_platforms: ["desktop"], pending_messages: 0 } as T);
  }
  if (cleanPath === "/v1/gateway/daemon/status") {
    return ok({ object: "gateway.daemon", data: { enabled: true, running: true, listeners: { desktop: { status: "ready" } } } } as T);
  }
  if (cleanPath === "/v1/gateway/platforms") {
    return ok({ object: "list", data: [{ platform: "desktop", status: "ready" }, { platform: "discord", status: "missing_credentials" }] } as T);
  }
  const gatewayPlatformMatch = cleanPath.match(/^\/v1\/gateway\/platforms\/([^/]+)\/(start|stop|health)$/);
  if (gatewayPlatformMatch) {
    return ok({ object: "gateway.platform", data: { platform: decodeURIComponent(gatewayPlatformMatch[1]), status: gatewayPlatformMatch[2] === "stop" ? "stopped" : "ready" } } as T);
  }
  if (cleanPath === "/v1/gateway/messages") {
    return ok({
      object: "list",
      data: [
        { message_id: "msg_gateway_mock", platform: "desktop", status: "delivered", user_id: profile.user_id },
        {
          message_id: "msg_gateway_failed",
          platform: "discord",
          target: "ops-alerts",
          status: "failed",
          content: "Mock Gateway 投递失败",
          error_message: "missing DISCORD_BOT_TOKEN",
          retry_count: 1,
          created_at: "2026-05-22T09:00:00Z"
        }
      ]
    } as T);
  }
  const gatewayRetryMatch = cleanPath.match(/^\/v1\/gateway\/messages\/([^/]+)\/retry$/);
  if (gatewayRetryMatch) {
    return ok({ object: "gateway.retry", data: { message_id: decodeURIComponent(gatewayRetryMatch[1]), status: "queued" } } as T);
  }
  if (cleanPath === "/v1/gateway/directory") {
    return ok({ object: "list", data: [{ platform: "desktop", kind: "user", id: profile.user_id, display_name: profile.profile_name }] } as T);
  }
  if (cleanPath === "/v1/gateway/directory/refresh") {
    return ok({ object: "gateway.directory_refresh", data: [{ platform: "desktop", kind: "user", id: profile.user_id }] } as T);
  }
  if (cleanPath === "/v1/learning/status") {
    return ok({ object: "aiask.learning_status", status: "ready", proposal_count: 1, apply_requires_control: true } as T);
  }
  if (cleanPath === "/v1/learning/review") {
    return ok({ object: "list", data: [{ proposal_id: "learn_mock", status: "pending_review", summary: "Mock 提示词改进建议" }] } as T);
  }
  if (cleanPath === "/v1/learning/apply") {
    return ok({ object: "learning.proposal", data: { proposal_id: body.proposal_id, status: "applied" } } as T);
  }
  if (cleanPath === "/v1/rl/environments") {
    return ok({ object: "list", data: { environments: [{ id: "finance_safe_eval", status: "ready" }], missing_env: ["TINKER_API_KEY"] } } as T);
  }
  if (cleanPath === "/v1/rl/config") {
    return ok({ object: "aiask.rl_config", status: "configured", provider: "mock", secrets_redacted: true } as T);
  }
  if (cleanPath === "/v1/rl/runs") {
    if (method === "POST") return ok({ object: "rl.run", data: { run_id: "rl_mock_new", environment: body.environment || "finance_safe_eval", status: "running" } } as T);
    return ok({ object: "list", data: [{ run_id: "rl_mock", environment: "finance_safe_eval", status: "dry_run_ready" }] } as T);
  }
  const rlRunDetailMatch = cleanPath.match(/^\/v1\/rl\/runs\/([^/]+)$/);
  if (rlRunDetailMatch) {
    return ok({ object: "rl.run", data: { run_id: decodeURIComponent(rlRunDetailMatch[1]), environment: "finance_safe_eval", status: "dry_run_ready" } } as T);
  }
  const rlRunMatch = cleanPath.match(/^\/v1\/rl\/runs\/([^/]+)\/(stop|results|logs)$/);
  if (rlRunMatch) {
    return ok({ object: `rl.${rlRunMatch[2]}`, data: { run_id: decodeURIComponent(rlRunMatch[1]), status: rlRunMatch[2] === "stop" ? "stopped" : "ready" } } as T);
  }
  if (cleanPath === "/v1/webhooks") {
    if (method === "POST") return ok({ object: "webhook", data: { webhook_id: `webhook_mock_${Date.now()}`, ...body, enabled: true } } as T);
    return ok({ object: "list", data: [{ webhook_id: "webhook_mock", name: "Mock Webhook", events: ["MCP UI 冒烟测试"], prompt: "mock", enabled: true, status: "ready" }] } as T);
  }
  const webhookMatch = cleanPath.match(/^\/v1\/webhooks\/([^/]+)(?:\/trigger)?$/);
  if (webhookMatch) {
    if (method === "DELETE") return ok({ object: "webhook.deleted", deleted: true, webhook_id: decodeURIComponent(webhookMatch[1]) } as T);
    if (cleanPath.endsWith("/trigger")) return ok(envelope("agent_webhook", { webhook_id: decodeURIComponent(webhookMatch[1]), rendered: true }) as T);
  }
  if (cleanPath === "/v1/approvals") {
    return ok({ object: "list", data: Array.from(intents.values()) } as T);
  }
  const approvalMatch = cleanPath.match(/^\/v1\/approvals\/([^/]+)\/(approve|deny)$/);
  if (approvalMatch) {
    return ok({ object: "approval", approval_id: decodeURIComponent(approvalMatch[1]), status: approvalMatch[2] === "approve" ? "approved" : "denied" } as T);
  }

  if (cleanPath === "/v1/jobs" && method === "GET") return ok({ object: "list", data: jobs } as T);
  if (cleanPath === "/v1/jobs" && method === "POST") {
    const job = { job_id: `job_mock_${jobs.length + 1}`, enabled: body.enabled ?? true, user_id: body.user_id || profile.user_id, ...body };
    jobs = [job, ...jobs];
    return ok({ object: "aiask.job", job } as T);
  }
  const jobRunsMatch = cleanPath.match(/^\/v1\/jobs\/([^/]+)\/runs$/);
  if (jobRunsMatch) {
    const jobId = decodeURIComponent(jobRunsMatch[1]);
    return ok({ object: "list", job_id: jobId, data: [{ job_run_id: `jobrun_${jobId}`, job_id: jobId, status: "completed", response_id: "resp_mock", run_id: "run_mock", duration_ms: 15, started_at: "2026-05-22T09:00:00Z", finished_at: "2026-05-22T09:00:01Z" }] } as T);
  }
  const jobMatch = cleanPath.match(/^\/v1\/jobs\/([^/]+)(?:\/run)?$/);
  if (jobMatch) {
    const jobId = decodeURIComponent(jobMatch[1]);
    if (cleanPath.endsWith("/run")) return ok(envelope("agent_job_run", { run_id: `run_${jobId}`, job_id: jobId, output_text: "mock job run" }) as T);
    if (method === "PATCH") {
      jobs = jobs.map((job) => String(job.job_id) === jobId ? { ...job, ...body } : job);
      return ok({ object: "aiask.job", job: jobs.find((job) => String(job.job_id) === jobId) } as T);
    }
    if (method === "DELETE") {
      jobs = jobs.filter((job) => String(job.job_id) !== jobId);
      return ok({ object: "aiask.job_deleted", deleted: true, job_id: jobId } as T);
    }
  }

  if (cleanPath === "/intents" && method === "GET") {
    return ok({ object: "list", data: Array.from(intents.values()) } as T);
  }
  if (cleanPath === "/intents" && method === "POST") {
    if (!authorized(options)) throw new Error("AIASK_UNAUTHORIZED");
    return ok(createIntent(body) as T);
  }
  const intentMatch = cleanPath.match(/^\/intents\/([^/]+)(?:\/(confirm|deny))?$/);
  if (intentMatch) {
    const id = decodeURIComponent(intentMatch[1]);
    const action = intentMatch[2];
    const intent = intents.get(id) || { intent_id: id, action: "mock.action", target_tool: "agent_action_intent_create", target_action: "mock.action", status: "awaiting_confirmation", params: {} };
    if (action) intent.status = action === "confirm" ? "confirmed" : "denied";
    intents.set(id, intent);
    return ok(envelope("agent_action_intent_get", { intent }) as T);
  }

  const toolMatch = cleanPath.match(/^\/v1\/tools\/([^/]+)$/);
  if (toolMatch) return ok(toolResult(decodeURIComponent(toolMatch[1]), body) as T);
  const hermesToolMatch = cleanPath.match(/^\/v1\/hermes\/admin\/tools\/([^/]+)$/);
  if (hermesToolMatch) return ok(toolResult(decodeURIComponent(hermesToolMatch[1]), body) as T);

  if (cleanPath === "/v1/skills" && method === "GET") return ok({ data: capabilities().skills } as T);
  if (cleanPath === "/v1/skills" && method === "POST") return ok({ object: "skill", status: "installed", name: body.name } as T);
  if (cleanPath.startsWith("/v1/skills/") && method === "PATCH") return ok({ object: "skill", status: "updated" } as T);
  if (cleanPath.startsWith("/v1/skills/") && method === "DELETE") return ok({ object: "skill", status: "deleted" } as T);
  if (cleanPath === "/v1/plugins" && method === "GET") return ok({ data: capabilities().plugins } as T);
  if (cleanPath === "/v1/plugins" && method === "POST") return ok({ object: "plugin_upserted", success: true, data: { name: body.name || "local-plugin", enabled: body.enabled ?? true } } as T);
  if (cleanPath.startsWith("/v1/plugins/") && method === "PATCH") return ok({ object: "plugin_updated", enabled: body.enabled } as T);
  const pluginCommandsMatch = cleanPath.match(/^\/v1\/plugins\/([^/]+)\/commands$/);
  if (pluginCommandsMatch) return ok({ object: "list", data: [{ name: "doctor", description: "Run plugin diagnostics", enabled: true }] } as T);
  const pluginCommandTestMatch = cleanPath.match(/^\/v1\/plugins\/([^/]+)\/commands\/([^/]+)\/test$/);
  if (pluginCommandTestMatch) {
    return ok({ object: "plugin.command_test", success: true, data: { plugin: decodeURIComponent(pluginCommandTestMatch[1]), command: decodeURIComponent(pluginCommandTestMatch[2]), status: "ready" }, error: null } as T);
  }
  if (cleanPath.includes("/tools/") && cleanPath.endsWith("/test")) return ok({ object: "plugin_tool_tested", success: true } as T);

  if (cleanPath === "/v1/mcp/servers") return ok({ data: capabilities().mcp.servers } as T);
  if (cleanPath === "/v1/mcp/tools") return ok({ data: capabilities().mcp.tools } as T);
  if (cleanPath === "/v1/mcp/resources") return ok({ data: capabilities().mcp.resources } as T);
  if (cleanPath === "/v1/mcp/prompts") return ok({ data: capabilities().mcp.prompts } as T);
  if (cleanPath === "/v1/mcp/oauth_status") return ok({ data: capabilities().mcp.oauth } as T);
  if (cleanPath === "/v1/mcp/register-local") return ok({ success: true, data: { status: "registered", server: body.name || "akshare-local" } } as T);
  if (cleanPath === "/v1/mcp/discover") return ok({ success: true, data: { status: "discovered", server: body.server || "akshare-local", tools: capabilities().mcp.tools } } as T);
  if (cleanPath === "/v1/mcp/resources/read") return ok({ success: true, data: { uri: body.uri, result: { text: "quote resource ok" } } } as T);
  if (cleanPath === "/v1/mcp/prompts/get") return ok({ success: true, data: { prompt: "risk prompt ok", name: body.name } } as T);
  if (cleanPath === "/v1/mcp/oauth/start") return ok({ success: false, error_code: "oauth_required", data: { server: body.server, configured: false } } as T);

  if (cleanPath === "/v1/connectors/summary") return ok({ status: "ready", data: { total: 3, connected: 1, configured: 2, connectors: [{ type: "mcp", name: "akshare-local", status: "ready" }, { type: "platform", name: "discord", status: "missing_credentials", missing_env: ["DISCORD_BOT_TOKEN"] }, { type: "financial", name: "tongdaxin", status: "ready" }] } } as T);
  if (cleanPath === "/v1/connectors") {
    return ok({ object: "list", data: [{ type: "mcp", name: "akshare-local", category: "data", status: "ready", configured: true, connected: true }, { type: "platform", name: "discord", category: "communication", status: "missing_credentials", configured: false, connected: false, missing_env: ["DISCORD_BOT_TOKEN"] }, { type: "financial", name: "tongdaxin", category: "data", status: "ready", configured: true, connected: true }] } as T);
  }
  const connectorMatch = cleanPath.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)(?:\/test)?$/);
  if (connectorMatch) {
    return ok({ object: cleanPath.endsWith("/test") ? "connector.test" : "connector.detail", data: { type: decodeURIComponent(connectorMatch[1]), name: decodeURIComponent(connectorMatch[2]), configured: true, connected: true, status: "ready", missing_env: [] } } as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/catalog") return ok(financialManagerCatalog() as T);
  if (cleanPath === "/v1/desktop/financial-manager/status") {
    return ok({
      object: "aiask.desktop.financial_manager.status",
      status: "ready",
      readiness: capabilities().financial_system,
      catalog_summary: financialManagerCatalog().summary,
      mcp: { registration: capabilities().mcp.registration_status, servers: capabilities().mcp.servers },
      broker: { live_trading_enabled: false, read_only_surfaces: ["ths_query_position", "qmt_query_account"], blocked_actions: ["ths_place_order", "qmt_place_order"] },
      recent_intents: Array.from(intents.values()).slice(-5),
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/query") {
    const action = financialManagerCatalog().actions.find((item) => item.capability_id === body.capability_id && item.action_id === body.action_id);
    if (action?.mode === "blocked") return ok({ object: "aiask.desktop.financial_manager.query", success: false, data: { reason: action.blocked_reason }, error: action.blocked_reason, error_code: "FINANCIAL_ACTION_BLOCKED", secrets_redacted: true } as T);
    if (action?.mode === "stateful_intent") return ok({ object: "aiask.desktop.financial_manager.query", success: false, data: { required_endpoint: "/v1/desktop/financial-manager/intent" }, error: "stateful financial actions must be created as ActionIntent", error_code: "FINANCIAL_ACTION_REQUIRES_INTENT", secrets_redacted: true } as T);
    if (body.capability_id === "stock-analysis" && body.action_id === "analyze_stock") {
      const params = body.params && typeof body.params === "object" && !Array.isArray(body.params)
        ? body.params as Record<string, unknown>
        : {};
      const code = String(params.code || params.stock_code || params.symbol || "600519");
      return ok({
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
      } as T);
    }
    if (body.capability_id === "portfolio" && body.action_id === "risk") {
      return ok({
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
      } as T);
    }
    if (body.capability_id === "quant" && body.action_id === "data_gate") {
      const params = body.params && typeof body.params === "object" && !Array.isArray(body.params)
        ? body.params as Record<string, unknown>
        : {};
      return ok({
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
      } as T);
    }
    return ok({ object: "aiask.desktop.financial_manager.query", capability_id: body.capability_id, action_id: body.action_id, tool: action?.tool || "mock_tool", success: true, data: { status: "ready", params: body.params || action?.default_params || {}, rows: [{ code: "600519", signal: "watch", risk: "medium" }] }, error: null, meta: { side_effect: { level: "read_only", confirmation_required: false } }, secrets_redacted: true } as T);
  }
  if (cleanPath === "/v1/desktop/financial-manager/intent") {
    const action = financialManagerCatalog().actions.find((item) => item.capability_id === body.capability_id && item.action_id === body.action_id);
    if (action?.mode === "blocked") return ok({ object: "aiask.desktop.financial_manager.intent", success: false, data: { reason: action.blocked_reason }, error: action.blocked_reason, error_code: "FINANCIAL_ACTION_BLOCKED", secrets_redacted: true } as T);
    const intent = {
      intent_id: `intent_fin_${Date.now()}`,
      action: action?.intent_action || "financial_manager.mock",
      target_tool: "financial_manager",
      target_action: action?.intent_action || "mock",
      status: "awaiting_confirmation",
      params: body.params || action?.default_params || {},
      rationale: body.rationale || "金融经理台 mock 意图"
    };
    intents.set(intent.intent_id, intent);
    return ok({ object: "aiask.desktop.financial_manager.intent", capability_id: body.capability_id, action_id: body.action_id, success: true, data: { intent }, error: null, meta: { side_effect: { level: "stateful", confirmation_required: true } }, secrets_redacted: true } as T);
  }
  if (cleanPath === "/v1/desktop/quant/presets") {
    return ok({
      object: "aiask.quant_presets",
      data_status: { status: "ready", database: dataStatus().database },
      templates: [{ id: "mock", label: "Mock", universe: ["600519", "000001"], benchmark: "000300", factors: ["momentum", "volatility"], rebalance_frequency: "monthly", cost_bps: 3, slippage_bps: 1 }],
      factor_library: ["momentum", "volatility", "value"],
      risk_defaults: { max_weight: 0.35 },
      disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
    } as T);
  }
  if (cleanPath === "/v1/desktop/quant/research-runs") {
    return ok(envelope("agent_quant_research_run", { research: quantResearchArtifact() }) as T);
  }
  const quantReportMatch = cleanPath.match(/^\/v1\/desktop\/quant\/research-runs\/([^/]+)\/report$/);
  if (quantReportMatch) return ok(quantResearchArtifact(decodeURIComponent(quantReportMatch[1])).report as T);
  if (cleanPath === "/v1/desktop/stock-radar/status") return ok(envelope("agent_stock_radar_status", stockRadarPayload()) as T);
  if (cleanPath === "/v1/desktop/stock-radar/candidates") {
    const filters = queryRecord(query);
    const tier = String(filters.tier || "");
    const items = tier ? mockStockRadarCandidates.filter((item) => item.tier === tier) : mockStockRadarCandidates;
    return ok(envelope("agent_stock_radar_candidates", { status: "ready", candidates: items, count: items.length }) as T);
  }
  if (cleanPath === "/v1/desktop/stock-radar/digest") return ok(envelope("agent_stock_radar_digest", stockRadarPayload()) as T);

  return ok({ object: "mock.unhandled", path: cleanPath, method, data: {}, status: "ready" } as T);
}

export { CONTROL_TOKEN as MOCK_CONTROL_TOKEN };
