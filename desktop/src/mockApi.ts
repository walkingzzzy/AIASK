import type { ApiHeaders } from "./api";
import type {
  AgentArtifactRecord,
  AgentSourceRecord,
  CapabilityWorkbenchPayload,
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HandoffQueuePayload,
  HandoffRecord,
  NormalizedRunEvent,
  RecentSessionSummary,
  RunTraceEvalPayload,
  SessionResumeContextPayload,
  ToolCatalogItem,
  UserActivityEvent,
  UserDataPolicy,
} from "./types";

interface MockOptions {
  method?: string;
  token?: string;
  body?: unknown;
  headers?: ApiHeaders;
}

const CONTROL_TOKEN = "mock-control-token";
const HERMES_BASELINE = "Hermes v0.16.0 full runtime capability reference";
const HERMES_BASELINE_VERSION = "0.16.0";
const HERMES_RELEASE_TAG = "v2026.6.5";
const HERMES_V016_BASELINE = "Hermes v0.16.0 Surface Release capability reference";

const financeTools: ToolCatalogItem[] = [
  { name: "agent_tool_catalog", capability: "tool_catalog", category: "financial_read", side_effect: "read_only", description: "Return the AIASK Agent tool catalog." },
  { name: "agent_analyze_stock", capability: "stock_analysis", category: "financial_read", side_effect: "read_only", description: "Run a stock analysis workflow.", input_schema: { type: "object", properties: { code: { type: "string" }, include_decision: { type: "boolean" } } }, examples: [{ arguments: { code: "600519", include_decision: false } }] },
  { name: "agent_stock_live_quote", capability: "stock_live_quote", category: "financial_read", side_effect: "read_only", description: "Fetch realtime stock quotes with provider and source-chain evidence.", input_schema: { type: "object", properties: { code: { type: "string" }, include_source_chain: { type: "boolean" } }, required: ["code"] }, examples: [{ arguments: { code: "600519", include_source_chain: true } }] },
  { name: "agent_stock_news_digest", capability: "stock_news_digest", category: "financial_read", side_effect: "read_only", description: "Fetch linked stock or market news and preserve citation evidence.", input_schema: { type: "object", properties: { code: { type: "string" }, limit: { type: "integer" }, include_links: { type: "boolean" } } }, examples: [{ arguments: { code: "600519", limit: 10, include_links: true } }] },
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

let mockActivityEvents: UserActivityEvent[] = [];
let mockToolInvocations: Array<Record<string, unknown>> = [];
let mockFeedbackEvents: Array<Record<string, unknown>> = [];
let mockUserDataPolicies: Record<string, UserDataPolicy> = {};

function mockNow() {
  return "2026-06-12T00:00:00Z";
}

function redactedAuditValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactedAuditValue);
  if (!value || typeof value !== "object") return value;
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const lowered = key.toLowerCase();
    result[key] = lowered.includes("token") || lowered.includes("secret") || lowered.includes("password") || lowered.includes("api_key")
      ? "[redacted]"
      : redactedAuditValue(item);
  }
  return result;
}

function userPolicy(userId = String(profile.user_id || "local")): UserDataPolicy {
  if (!mockUserDataPolicies[userId]) {
    mockUserDataPolicies[userId] = {
      user_id: userId,
      event_ttl_days: 90,
      audit_ttl_days: 180,
      run_event_ttl_days: 180,
      tool_payload_ttl_days: 90,
      conversation_retention: "keep_until_user_deletes",
      allow_product_analytics: true,
      allow_learning: false,
      updated_at: mockNow()
    };
  }
  return mockUserDataPolicies[userId];
}

function recordMockToolInvocation(tool: string, body: Record<string, unknown>) {
  const item = {
    id: mockToolInvocations.length + 1,
    invocation_id: `tool_mock_${mockToolInvocations.length + 1}`,
    user_id: String(body.user_id || profile.user_id || "local"),
    session_id: body.session_id || "sess_mock",
    run_id: body.run_id || null,
    trace_id: body.trace_id || `trace_mock_${mockToolInvocations.length + 1}`,
    tool_name: tool,
    status: "succeeded",
    input_summary: redactedAuditValue(body),
    output_summary: { success: true },
    duration_ms: 5,
    source_chain: ["desktop.mockApi"],
    secrets_redacted: true,
    created_at: mockNow(),
    updated_at: mockNow()
  };
  mockToolInvocations = [item, ...mockToolInvocations].slice(0, 100);
}

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
    id: "evt_quote",
    event: "market.quote_snapshot",
    event_type: "market.quote_snapshot",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:00Z",
    kind: "tool",
    title: "market.quote_snapshot: 600519",
    severity: "info",
    status: "completed",
    tool_name: "agent_stock_live_quote",
    jump_target: "runs-events",
    data: {
      artifact_id: "art_mock_quote",
      code: "600519",
      price: 123.45,
      provider: "akshare/sina",
      data_timestamp: "2026-05-22T09:00:00+08:00"
    },
  },
  {
    id: "evt_source",
    event: "news.source_linked",
    event_type: "news.source_linked",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:00Z",
    kind: "tool",
    title: "news.source_linked: Mock 财经新闻",
    severity: "info",
    status: "completed",
    tool_name: "agent_stock_news_digest",
    jump_target: "runs-events",
    data: {
      source_id: "src_mock_news",
      title: "Mock 财经新闻",
      url: "https://example.com/aiask/mock-news",
      provider: "eastmoney",
      published_at: "2026-05-22T08:55:00+08:00"
    },
  },
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

const mockAgentArtifacts: AgentArtifactRecord[] = [
  {
    artifact_id: "art_mock_quote",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_quote",
    tool_name: "agent_stock_live_quote",
    kind: "quote_snapshot",
    title: "600519 实时行情快照",
    preview_text: "价格 123.45，来源 akshare/sina，时间 2026-05-22T09:00:00+08:00",
    preview_json: {
      code: "600519",
      price: 123.45,
      change_pct: 1.23,
      provider: "akshare/sina",
      data_timestamp: "2026-05-22T09:00:00+08:00"
    },
    status: "ready",
    metadata: { source_chain: ["desktop.mockApi", "akshare", "sina"] },
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  },
  {
    artifact_id: "art_mock_news",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_news",
    tool_name: "agent_stock_news_digest",
    kind: "news_digest",
    title: "600519 新闻摘要",
    preview_text: "1 条带链接的新闻来源已保存。",
    preview_json: {
      items: [
        {
          title: "Mock 财经新闻",
          url: "https://example.com/aiask/mock-news",
          provider: "eastmoney",
          published_at: "2026-05-22T08:55:00+08:00"
        }
      ]
    },
    status: "ready",
    metadata: { source_chain: ["desktop.mockApi", "eastmoney"] },
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  },
  {
    artifact_id: "art_mock_script",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_script",
    tool_name: "agent_execute_python",
    kind: "script",
    title: "call_mock_script_snippet.py",
    path: "mock://aiask/artifacts/sess_mock/run_mock/call_mock_script_snippet.py",
    mime_type: "text/x-python",
    size_bytes: 54,
    sha256: "mock-sha256",
    preview_text: "print('AIASK mock script artifact')",
    status: "ready",
    metadata: { language: "python", persisted_from: "agent_execute_python" },
    created_at: "2026-05-22T09:00:01Z",
    updated_at: "2026-05-22T09:00:01Z"
  },
  {
    artifact_id: "art_mock_terminal",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_terminal",
    tool_name: "agent_terminal",
    kind: "terminal_output",
    title: "agent_terminal output",
    mime_type: "text/plain",
    preview_text: "PS> npm test -- --runInBand\nPASS workbench evidence smoke",
    preview_json: {
      command: "npm test -- --runInBand",
      exit_code: 0,
      stdout: "PASS workbench evidence smoke",
      stderr: ""
    },
    status: "ready",
    metadata: { persisted_from: "agent_terminal" },
    created_at: "2026-05-22T09:00:02Z",
    updated_at: "2026-05-22T09:00:02Z"
  }
];

const mockAgentSources: AgentSourceRecord[] = [
  {
    source_id: "src_mock_quote_provider",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_quote",
    tool_name: "agent_stock_live_quote",
    provider: "sina",
    source_type: "market_quote",
    title: "sina data source",
    fetched_at: "2026-05-22T09:00:00Z",
    data_timestamp: "2026-05-22T09:00:00+08:00",
    metadata: { source_chain: ["desktop.mockApi", "akshare", "sina"] },
    created_at: "2026-05-22T09:00:00Z"
  },
  {
    source_id: "src_mock_news",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_news",
    tool_name: "agent_stock_news_digest",
    provider: "eastmoney",
    source_type: "news",
    title: "Mock 财经新闻",
    url: "https://example.com/aiask/mock-news",
    published_at: "2026-05-22T08:55:00+08:00",
    fetched_at: "2026-05-22T09:00:00Z",
    excerpt: "Mock 新闻来源链接，用于验证 Desktop 证据展示。",
    metadata: { source_chain: ["desktop.mockApi", "eastmoney"] },
    created_at: "2026-05-22T09:00:00Z"
  }
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
    archived: false,
    archived_at: null,
    archived_reason: null,
    handoff_state: {
      status: "active",
      handoff_id: "handoff_mock",
      target: "risk_specialist",
      source_run_id: "run_source_mock",
      source_tool_call_id: "call_handoff_mock",
      context_snapshot_id: "ctxsnap_mock_source",
      active_run_id: "run_mock",
      summary: "Continue with risk review.",
      reason: "risk escalation",
      updated_at: "2026-05-22T09:00:02Z",
      activated_at: "2026-05-22T09:00:02Z",
      metadata: { handoff_kind: "ownership_transfer" },
    },
    handoff_status: "active",
    handoff_target: "risk_specialist",
    handoff_id: "handoff_mock",
    handoff_context_snapshot_id: "ctxsnap_mock_source",
    active_agent: "risk_specialist",
    active_context_snapshot_id: "ctxsnap_mock_source",
    metadata: {
      source: "desktop.mockApi",
      handoff_status: "active",
      handoff_target: "risk_specialist",
      active_agent: "risk_specialist",
      active_context_snapshot_id: "ctxsnap_mock_source",
    },
  },
];

const initialMockSessionMessages: Array<Record<string, unknown>> = [
  { id: 1, message_id: "msg_user", role: "user", content: "mock question", created_at: "2026-05-22T09:00:01Z" },
  { id: 2, message_id: "msg_assistant", role: "assistant", content: "mock answer", created_at: "2026-05-22T09:00:02Z" },
];

let mockSessionMessages: Array<Record<string, unknown>> = initialMockSessionMessages.map((item) => ({ ...item }));

export function resetMockApiState(): void {
  mockSessionSummaries.splice(0, mockSessionSummaries.length, {
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
    archived: false,
    archived_at: null,
    archived_reason: null,
    handoff_state: {
      status: "active",
      handoff_id: "handoff_mock",
      target: "risk_specialist",
      source_run_id: "run_source_mock",
      source_tool_call_id: "call_handoff_mock",
      context_snapshot_id: "ctxsnap_mock_source",
      active_run_id: "run_mock",
      summary: "Continue with risk review.",
      reason: "risk escalation",
      updated_at: "2026-05-22T09:00:02Z",
      activated_at: "2026-05-22T09:00:02Z",
      metadata: { handoff_kind: "ownership_transfer" },
    },
    handoff_status: "active",
    handoff_target: "risk_specialist",
    handoff_id: "handoff_mock",
    handoff_context_snapshot_id: "ctxsnap_mock_source",
    active_agent: "risk_specialist",
    active_context_snapshot_id: "ctxsnap_mock_source",
    metadata: {
      source: "desktop.mockApi",
      handoff_status: "active",
      handoff_target: "risk_specialist",
      active_agent: "risk_specialist",
      active_context_snapshot_id: "ctxsnap_mock_source",
    },
  });
  mockSessionMessages = initialMockSessionMessages.map((item) => ({ ...item }));
}

function filterMockArtifacts({
  runId,
  sessionId,
  kind,
  limit = 100
}: {
  runId?: string;
  sessionId?: string;
  kind?: string | null;
  limit?: number;
}): AgentArtifactRecord[] {
  return mockAgentArtifacts
    .filter((item) => !runId || item.run_id === runId)
    .filter((item) => !sessionId || item.session_id === sessionId)
    .filter((item) => !kind || item.kind === kind)
    .slice(0, Math.max(1, Math.min(limit || 100, 1000)));
}

function filterMockSources({
  runId,
  sessionId,
  sourceType,
  limit = 100
}: {
  runId?: string;
  sessionId?: string;
  sourceType?: string | null;
  limit?: number;
}): AgentSourceRecord[] {
  return mockAgentSources
    .filter((item) => !runId || item.run_id === runId)
    .filter((item) => !sessionId || item.session_id === sessionId)
    .filter((item) => !sourceType || item.source_type === sourceType)
    .slice(0, Math.max(1, Math.min(limit || 100, 1000)));
}

function mockRunTraceEval(runId: string): RunTraceEvalPayload {
  const runSources = filterMockSources({ runId, limit: 100 });
  const runArtifacts = filterMockArtifacts({ runId, limit: 100 });
  const runToolInvocations = mockToolInvocations.filter((item) => item.run_id === runId);
  const toolInvocationCount = Math.max(1, runToolInvocations.length);
  return {
    object: "aiask.run_trace_eval",
    implementation: "desktop_mock",
    run_id: runId,
    session_id: runId === "run_mock" ? "sess_mock" : null,
    status: "healthy",
    score: 100,
    checks: [
      {
        id: "model_trace",
        label: "Model call trace",
        status: "pass",
        detail: "model.started=1, model.completed=1",
        evidence: { started: 1, completed: 1 },
      },
      {
        id: "tool_trace",
        label: "Tool invocation trace",
        status: "pass",
        detail: `tool_invocations=${toolInvocationCount}, failed=0`,
        evidence: { invocations: toolInvocationCount, failed: 0 },
      },
      {
        id: "context_snapshot",
        label: "Context snapshot",
        status: "pass",
        detail: "context snapshot present",
        evidence: {
          context_snapshot_id: "ctxsnap_mock_source",
          source_message_count: 2,
          source_count: runSources.length,
          artifact_count: runArtifacts.length,
          risk_flags: [],
        },
      },
      {
        id: "evidence_chain",
        label: "Evidence chain",
        status: "pass",
        detail: `sources=${runSources.length}, artifacts=${runArtifacts.length}`,
        evidence: { sources: runSources.length, artifacts: runArtifacts.length },
      },
      {
        id: "handoff_trace",
        label: "Handoff trace",
        status: "pass",
        detail: "handoff_events=1",
        evidence: { events: ["handoff.policy_applied"] },
      },
      {
        id: "guardrail_trace",
        label: "Guardrail trace",
        status: "pass",
        detail: "guardrail_events=0",
        evidence: { events: [] },
      },
    ],
    summary: {
      event_count: mockRunEvents.filter((item) => item.run_id === runId).length || mockRunEvents.length,
      tool_invocation_count: toolInvocationCount,
      failed_tool_invocation_count: 0,
      context_snapshot_count: 1,
      source_count: runSources.length,
      artifact_count: runArtifacts.length,
      handoff_event_count: 1,
      guardrail_event_count: 0,
      error_event_count: 0,
    },
    latest_context_snapshot: {
      snapshot_id: "ctxsnap_mock_source",
      session_id: "sess_mock",
      run_id: runId,
      trace_id: "trace_mock",
      context_summary_id: "ctxsum_mock",
      compacted: false,
      message_count: 2,
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: runSources.map((item) => item.source_id),
      artifact_ids: runArtifacts.map((item) => item.artifact_id),
      risk_flags: [],
      created_at: "2026-05-22T09:00:02Z",
    },
    risk_flags: [],
    secrets_redacted: true,
  };
}

function mockArtifactContent(artifactId: string) {
  const artifact = mockAgentArtifacts.find((item) => item.artifact_id === artifactId);
  if (!artifact) return null;
  return {
    object: "artifact.content",
    artifact_id: artifactId,
    encoding: "text",
    mime_type: artifact.mime_type || "text/plain",
    bytes: String(artifact.preview_text || "").length,
    truncated: false,
    content: artifact.preview_text || JSON.stringify(artifact.preview_json || artifact, null, 2)
  };
}

function currentMockSessionSummaries(): RecentSessionSummary[] {
  return mockSessionSummaries.map((session) => {
    if (session.session_id !== "sess_mock") return session;
    const lastMessage = mockSessionMessages[mockSessionMessages.length - 1];
    return {
      ...session,
      message_count: mockSessionMessages.length,
      last_message_at: String(lastMessage?.created_at || session.last_message_at || ""),
    };
  });
}

function mockHandoffRecord(session = currentMockSessionSummaries()[0]): HandoffRecord {
  const state = session.handoff_state || {};
  return {
    handoff_id: String(session.handoff_id || state.handoff_id || "handoff_mock"),
    session_id: session.session_id,
    user_id: session.user_id || String(profile.user_id || "local"),
    target: session.handoff_target || state.target || "risk_specialist",
    status: "requested",
    runtime_status: session.handoff_status || state.status || "active",
    reason: String(state.reason || "risk escalation"),
    summary: String(state.summary || "Continue with risk review."),
    metadata: { context_snapshot_id: session.handoff_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source" },
    created_at: session.created_at,
    updated_at: session.updated_at,
    session_title: session.title,
    handoff_state: state,
    active_agent: session.active_agent || state.target || "risk_specialist",
    active_context_snapshot_id: session.active_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source",
    resume_context_snapshot_id: session.active_context_snapshot_id || session.handoff_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source",
    resume_ready: true,
    secrets_redacted: true,
  };
}

function mockHandoffQueue(filters: { userId?: string | null; sessionId?: string | null; status?: string | null; includeCompleted?: boolean; limit?: number } = {}): HandoffQueuePayload {
  const status = String(filters.status || "").toLowerCase();
  const rows = currentMockSessionSummaries()
    .filter((session) => !filters.userId || session.user_id === filters.userId)
    .filter((session) => !filters.sessionId || session.session_id === filters.sessionId)
    .filter((session) => session.handoff_state || session.handoff_status || session.active_agent)
    .map((session) => mockHandoffRecord(session))
    .filter((item) => !status || status === "all" || item.runtime_status === status)
    .filter((item) => filters.includeCompleted || !["completed", "failed", "cancelled", "canceled"].includes(String(item.runtime_status || item.status || "")));
  const limited = rows.slice(0, Math.max(1, Math.min(filters.limit || 100, 500)));
  const summary = limited.reduce<Record<string, number>>((acc, item) => {
    const key = String(item.runtime_status || item.status || "unknown");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, { total: limited.length });
  return {
    object: "aiask.handoff_queue",
    implementation: "aiask_native",
    data: limited,
    count: limited.length,
    summary,
    filters,
    secrets_redacted: true,
  };
}

function mockSessionResumeContext(sessionId: string): SessionResumeContextPayload {
  const session = currentMockSessionSummaries().find((item) => item.session_id === sessionId) || currentMockSessionSummaries()[0];
  const handoff = mockHandoffRecord(session);
  const snapshotId = String(handoff.resume_context_snapshot_id || "ctxsnap_mock_source");
  return {
    object: "aiask.session_resume_context",
    implementation: "aiask_native",
    session_id: sessionId,
    session,
    handoff,
    handoff_state: session.handoff_state || null,
    context_snapshot: {
      snapshot_id: snapshotId,
      session_id: session.session_id,
      context_summary_id: "ctxsum_mock_source",
      risk_flags: ["mock_resume"],
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: ["src_mock_news"],
      artifact_ids: ["art_mock_quote"],
      summary: "Mock resume snapshot",
      secrets_redacted: true,
    },
    resume_context: {
      session_id: session.session_id,
      handoff_id: handoff.handoff_id,
      target: handoff.target,
      status: handoff.runtime_status,
      context_snapshot_id: snapshotId,
      context_summary_id: "ctxsum_mock_source",
      risk_flags: ["mock_resume"],
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: ["src_mock_news"],
      artifact_ids: ["art_mock_quote"],
      summary: String(session.handoff_state?.summary || "Continue with risk review."),
      reason: String(session.handoff_state?.reason || "risk escalation"),
      resume_prompt: `继续会话 ${session.session_id}。当前任务接管目标为 ${handoff.target || "risk_specialist"}；请基于上下文快照 ${snapshotId} 继续推进。`,
    },
    secrets_redacted: true,
  };
}

function mockWorkbenchSummary(): DesktopWorkbenchSummary {
  return {
    recent_sessions: currentMockSessionSummaries(),
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

function mockBrokerAnalytics(provider = "qmt") {
  const isThs = provider === "tonghuashun" || provider === "ths";
  const profile = isThs ? mockThsBrokerProfile : mockBrokerProfile;
  const accounts = isThs ? mockThsBrokerAccounts : mockBrokerAccounts;
  const positions = isThs ? mockThsBrokerPositions : mockBrokerPositions;
  const orders = isThs ? mockThsBrokerOrders : mockBrokerOrders;
  const deals = isThs ? mockThsBrokerDeals : mockBrokerDeals;
  const totalAsset = isThs ? 86000 : 100000;
  const cashAvailable = isThs ? 24000 : 12000;
  const marketValue = isThs ? 62000 : 88000;
  const topPositions = isThs
    ? [
        { symbol: "300750", name: "CATL", market_value: 44000, position_pct: 0.7097 },
        { symbol: "600036", name: "CMB", market_value: 18000, position_pct: 0.2903 }
      ]
    : [
        { symbol: "600519", name: "Kweichow Moutai", market_value: 45000, position_pct: 0.5114 },
        { symbol: "000001", name: "Ping An Bank", market_value: 43000, position_pct: 0.4886 }
      ];
  return {
    analytics_id: isThs ? "broker_analytics_mock_ths" : "broker_analytics_mock_qmt",
    broker_profile_id: profile.broker_profile_id,
    user_id: "local",
    provider: profile.provider,
    period_start: null,
    period_end: null,
    metrics: {
      account_count: accounts.length,
      position_count: positions.length,
      order_count: orders.length,
      deal_count: deals.length,
      total_asset: totalAsset,
      cash_available: cashAvailable,
      market_value: marketValue,
      cash_ratio: cashAvailable / totalAsset,
      top_position_concentration: Number(topPositions[0].position_pct),
      top_positions: topPositions,
      trade_count: isThs ? 2 : 2,
      buy_count: isThs ? 0 : 2,
      sell_count: isThs ? 2 : 0,
      buy_sell_imbalance: isThs ? -1 : 1,
      deal_amount_total: isThs ? 22000 : 45000
    },
    signals: {
      limitations: ["historical account snapshots are insufficient for drawdown analytics"],
      generated_at: "2026-06-12T00:00:00Z"
    },
    risk_flags: [{ code: "HIGH_SINGLE_POSITION_CONCENTRATION", severity: "warning", value: 0.5114 }],
    source_snapshot_ids: {
      accounts: accounts.map((item) => item.snapshot_id),
      positions: positions.map((item) => item.snapshot_id),
      orders: orders.map((item) => item.snapshot_id),
      deals: deals.map((item) => item.snapshot_id)
    },
    model_version: "deterministic-p0",
    created_at: "2026-06-12T00:00:00Z"
  };
}

function brokerSnapshotPayload(provider = "qmt") {
  const isThs = provider === "tonghuashun" || provider === "ths";
  return {
    object: "aiask.desktop.broker_readonly",
    success: true,
    data: {
      profiles: [isThs ? mockThsBrokerProfile : mockBrokerProfile],
      accounts: isThs ? mockThsBrokerAccounts : mockBrokerAccounts,
      positions: isThs ? mockThsBrokerPositions : mockBrokerPositions,
      orders: isThs ? mockThsBrokerOrders : mockBrokerOrders,
      deals: isThs ? mockThsBrokerDeals : mockBrokerDeals,
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

let mockModelConfig = {
  preset: "openai",
  provider: "openai",
  model: "gpt-5.4",
  base_url: "https://api.openai.com/v1",
  api_key_configured: true,
  mock: true,
  prompt_cache_enabled: false,
  prompt_cache_recent_messages: 3
};

const stockDataSourcePresets = [
  {
    provider: "akshare",
    label: "AKShare / AKTools",
    markets: ["CN", "HK", "US", "FX", "Futures", "Options"],
    categories: ["quote", "kline", "fundamental", "macro", "news"],
    auth_type: "none",
    default_base_url: "",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds", "user_agent"],
    env_keys: ["AKSHARE_MCP_SQLITE_PATH", "AIASK_SQLITE_PATH"],
    documentation_url: "https://akshare.akfamily.xyz/introduction.html",
    note: "开源数据采集器；也可以配置 AKTools HTTP base_url。"
  },
  {
    provider: "tushare",
    label: "Tushare Pro",
    markets: ["CN"],
    categories: ["quote", "kline", "fundamental", "calendar", "finance"],
    auth_type: "token",
    default_base_url: "http://api.tushare.pro",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute", "fields"],
    env_keys: ["TUSHARE_TOKEN"],
    documentation_url: "https://tushare.pro/document/1?doc_id=40",
    note: "Tushare Pro HTTP API；部分接口需要积分或权限。"
  },
  {
    provider: "tdx",
    label: "TongDaXin HQ",
    markets: ["CN"],
    categories: ["quote", "kline", "local_vipdoc"],
    auth_type: "host_port",
    default_host: "119.147.212.81",
    default_port: 7709,
    required_fields: ["host", "port"],
    optional_fields: ["timeout_seconds", "local_vipdoc_path"],
    env_keys: ["TDX_SERVER_IP", "TDX_SERVER_PORT", "TDX_LOCAL_ONLY", "TDX_VIPDOC_PATH"],
    documentation_url: null,
    note: "通达信行情 TCP 或本地 vipdoc 数据源；只读行情无需 API Key。"
  },
  {
    provider: "finnhub",
    label: "Finnhub",
    markets: ["US", "Global"],
    categories: ["quote", "kline", "fundamental", "news", "economic"],
    auth_type: "token",
    default_base_url: "https://finnhub.io/api/v1",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "symbol", "timeout_seconds", "rate_limit_per_minute"],
    env_keys: ["FINNHUB_API_KEY", "FINNHUB_TOKEN"],
    documentation_url: "https://finnhub.io/docs/api/introduction",
    note: "Token REST API；测试会使用示例股票代码。"
  },
  {
    provider: "duckduckgo",
    label: "DuckDuckGo HTML Search",
    markets: ["Global"],
    categories: ["web_search", "news", "research"],
    auth_type: "none",
    default_base_url: "https://duckduckgo.com/html/",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute"],
    env_keys: [],
    documentation_url: "https://duckduckgo.com/",
    note: "无密钥公开搜索 fallback。"
  },
  {
    provider: "tavily",
    label: "Tavily Search",
    markets: ["Global"],
    categories: ["web_search", "deep_research", "news", "research"],
    auth_type: "bearer",
    default_base_url: "https://api.tavily.com",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "search_depth"],
    env_keys: ["TAVILY_API_KEY"],
    documentation_url: "https://docs.tavily.com/documentation/api-reference/endpoint/search",
    note: "深度联网搜索 API；保存后可通过 agent_web_search 调用。"
  },
  {
    provider: "brave_search",
    label: "Brave Search API",
    markets: ["Global"],
    categories: ["web_search", "news", "research"],
    auth_type: "subscription_token",
    default_base_url: "https://api.search.brave.com/res/v1",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "country", "search_lang"],
    env_keys: ["BRAVE_SEARCH_API_KEY", "BRAVE_SEARCH_SUBSCRIPTION_TOKEN"],
    documentation_url: "https://api-dashboard.search.brave.com/app/documentation/web-search/get-started",
    note: "使用 X-Subscription-Token 的搜索 API。"
  },
  {
    provider: "serpapi",
    label: "SerpApi",
    markets: ["Global"],
    categories: ["web_search", "search_engine_results", "news", "research"],
    auth_type: "api_key",
    default_base_url: "https://serpapi.com/search.json",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "engine", "location"],
    env_keys: ["SERPAPI_API_KEY"],
    documentation_url: "https://serpapi.com/search-api",
    note: "搜索引擎结果 API；适合 Google/Bing SERP。"
  },
  {
    provider: "exa",
    label: "Exa Search",
    markets: ["Global"],
    categories: ["web_search", "neural_search", "research"],
    auth_type: "api_key_header",
    default_base_url: "https://api.exa.ai",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "search_type"],
    env_keys: ["EXA_API_KEY"],
    documentation_url: "https://docs.exa.ai/reference/search",
    note: "神经/相似度搜索 API。"
  }
];

let mockStockDataSources: Array<Record<string, unknown>> = [
  {
    id: "mock:akshare",
    provider: "akshare",
    name: "Mock AKShare 本地源",
    enabled: true,
    priority: 10,
    base_url: "",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["quote", "kline", "fundamental"],
    markets: ["CN", "HK", "US"],
    timeout_seconds: 8,
    notes: "Mock 默认数据源"
  },
  {
    id: "mock:tushare",
    provider: "tushare",
    name: "Mock Tushare Pro",
    enabled: true,
    priority: 20,
    base_url: "http://api.tushare.pro",
    api_key: "mock-tushare-token",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["quote", "kline", "fundamental"],
    markets: ["CN"],
    symbol: "600519",
    timeout_seconds: 8,
    rate_limit_per_minute: 120,
    notes: "用于前端连通性验证的脱敏条目"
  },
  {
    id: "mock:duckduckgo",
    provider: "duckduckgo",
    name: "DuckDuckGo fallback",
    enabled: true,
    priority: 50,
    base_url: "https://duckduckgo.com/html/",
    source: "mock",
    status: "ready",
    configured: true,
    categories: ["web_search", "research"],
    markets: ["Global"]
  }
];

const aiProviderPresets = [
  { id: "openai", label: "OpenAI", provider: "openai", provider_type: "openai", base_url: "https://api.openai.com/v1", default_model: "gpt-4.1-mini", model_list_supported: true },
  { id: "deepseek", label: "DeepSeek", provider: "openai", provider_type: "openai_compatible", base_url: "https://api.deepseek.com", default_model: "deepseek-chat", model_list_supported: true },
  { id: "dashscope-qwen-cn", label: "通义千问 / DashScope 北京", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "dashscope-qwen-intl", label: "Qwen / DashScope 美国弗吉尼亚", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope-us.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "anthropic", label: "Anthropic Claude", provider: "anthropic", provider_type: "anthropic_messages", base_url: "https://api.anthropic.com/v1", default_model: "claude-sonnet-4-5", model_list_supported: true },
  { id: "custom-openai-compatible", label: "自定义 OpenAI 兼容", provider: "openai", provider_type: "openai_compatible", base_url: "", default_model: "", model_list_supported: true },
  { id: "mock", label: "本地 Mock", provider: "mock", provider_type: "mock", base_url: "", default_model: "mock-local", model_list_supported: false }
];

function aiStatus() {
  const promptCacheSupported = mockModelConfig.provider === "anthropic";
  const promptCache = {
    object: "aiask.prompt_cache_policy",
    enabled: Boolean(mockModelConfig.prompt_cache_enabled && promptCacheSupported),
    requested_enabled: Boolean(mockModelConfig.prompt_cache_enabled),
    supported: promptCacheSupported,
    provider: mockModelConfig.provider,
    provider_type: promptCacheSupported ? "anthropic_messages" : mockModelConfig.provider === "mock" ? "mock" : "openai_compatible",
    strategy: "system_and_recent",
    system_prompt: Boolean(mockModelConfig.prompt_cache_enabled && promptCacheSupported),
    recent_non_system_messages: mockModelConfig.prompt_cache_enabled && promptCacheSupported ? mockModelConfig.prompt_cache_recent_messages : 0,
    cache_control: mockModelConfig.prompt_cache_enabled && promptCacheSupported ? { type: "ephemeral" } : null,
    secrets_redacted: true,
  };
  return {
    object: "aiask.ai_status",
    provider: mockModelConfig.provider,
    model: mockModelConfig.model,
    base_url_configured: Boolean(mockModelConfig.base_url),
    base_url: mockModelConfig.base_url || null,
    api_key_configured: mockModelConfig.api_key_configured,
    mock: mockModelConfig.mock,
    configured: true,
    runtime_client: "mock",
    prompt_cache: promptCache,
    config_source: { loaded: true, path: "mock://aiask/.env", source: "project_root", secrets_redacted: true },
    secrets_redacted: true
  };
}

function aiConfig() {
  const status = aiStatus();
  return {
    object: "aiask.ai_config",
    status: "ready",
    current: {
      provider: status.provider,
      model: status.model,
      base_url: status.base_url,
      api_key_configured: status.api_key_configured,
      base_url_configured: status.base_url_configured,
      mock: status.mock,
      configured: status.configured,
      prompt_cache: status.prompt_cache,
      secrets_redacted: true
    },
    editable: {
      provider_env: "AIASK_AGENT_MODEL_PROVIDER",
      model_env: "AIASK_AGENT_MODEL",
      base_url_env: "OPENAI_BASE_URL",
      api_key_env: "OPENAI_API_KEY",
      env_file: "mock://aiask/.env",
      env_source: "project_root"
    },
    presets: aiProviderPresets,
    actions: {
      save: { method: "PATCH", path: "/v1/ai/config", requires_control_token: true },
      models: { method: "GET", path: "/v1/ai/models" },
      smoke: { method: "POST", path: "/v1/ai/smoke" }
    },
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

function stockDataSourceConfigured(source: Record<string, unknown>): boolean {
  const preset = stockDataSourcePresets.find((item) => item.provider === source.provider);
  const required = preset?.required_fields || [];
  if (!required.length) return true;
  return required.every((field) => {
    if (field === "api_key") return Boolean(String(source.api_key || source.token || "").trim());
    if (field === "port") return Number(source.port || 0) > 0;
    return Boolean(String(source[field] || "").trim());
  });
}

function redactStockDataSource(source: Record<string, unknown>): Record<string, unknown> {
  const configured = stockDataSourceConfigured(source);
  const enabled = source.enabled !== false;
  return {
    ...source,
    api_key: source.api_key ? "[redacted]" : "",
    token: source.token ? "[redacted]" : "",
    password: source.password ? "[redacted]" : "",
    api_key_configured: Boolean(String(source.api_key || source.token || source.password || "").trim()),
    configured,
    enabled,
    status: enabled ? configured ? "ready" : "unconfigured" : "disabled",
    secrets_redacted: true
  };
}

function mergeStockDataSourceDraft(
  base: Record<string, unknown> | undefined,
  draft: Record<string, unknown>
): Record<string, unknown> {
  const merged = { ...(base || {}) };
  for (const [key, value] of Object.entries(draft)) {
    const lowered = key.toLowerCase();
    const secretField = lowered.includes("api_key") || lowered.includes("token") || lowered.includes("secret") || lowered.includes("password");
    if (secretField && (value === null || value === "" || value === undefined) && base) continue;
    merged[key] = value;
  }
  return merged;
}

function stockDataSourcesStatus() {
  const sources = mockStockDataSources.map(redactStockDataSource);
  return {
    object: "aiask.stock_data_sources",
    status: sources.some((source) => source.status === "ready") ? "ready" : "unconfigured",
    configured_count: sources.filter((source) => source.configured).length,
    ready_count: sources.filter((source) => source.status === "ready").length,
    presets: stockDataSourcePresets,
    sources,
    config_path: "mock://aiask/stock_data_sources.json",
    config_source: { source: "desktop.mockApi", loaded: true },
    secrets_redacted: true
  };
}

function saveMockStockDataSource(body: Record<string, unknown>) {
  const provider = String(body.provider || "").trim();
  const preset = stockDataSourcePresets.find((item) => item.provider === provider);
  if (!provider || !preset) {
    return { object: "aiask.stock_data_source", source: { provider, status: "unsupported", configured: false }, secrets_redacted: true };
  }
  const id = String(body.id || "").trim() || `mock:${provider}:${Date.now()}`;
  const existing = mockStockDataSources.find((source) => source.id === id);
  const next: Record<string, unknown> = {
    ...(existing || {}),
    ...body,
    id,
    provider,
    name: String(body.name || existing?.name || preset.label),
    enabled: body.enabled !== false,
    updated_at: "2026-06-12T00:00:00Z",
    source: "mock"
  };
  if (!body.api_key && existing?.api_key) next.api_key = existing.api_key;
  if (!body.password && existing?.password) next.password = existing.password;
  if (existing) {
    mockStockDataSources = mockStockDataSources.map((source) => source.id === id ? next : source);
  } else {
    mockStockDataSources = [next, ...mockStockDataSources];
  }
  return { object: "aiask.stock_data_source", source: redactStockDataSource(next), secrets_redacted: true };
}

function testMockStockDataSource(body: Record<string, unknown>) {
  const inline = body.source && typeof body.source === "object" && !Array.isArray(body.source)
    ? body.source as Record<string, unknown>
    : body;
  const inlineId = String(inline.id || body.id || "").trim();
  const stored = inlineId
    ? mockStockDataSources.find((item) => item.id === inlineId)
    : undefined;
  const source = body.source && typeof body.source === "object" && !Array.isArray(body.source)
    ? mergeStockDataSourceDraft(stored, inline)
    : String(inline.provider || "").trim()
      ? inline
      : mockStockDataSources.find((item) => item.id === body.id) || mockStockDataSources.find((item) => item.provider === body.provider) || {};
  const provider = String(source.provider || body.provider || "").trim();
  const configured = stockDataSourceConfigured(source);
  const enabled = source.enabled !== false;
  const success = Boolean(provider && configured && enabled);
  return {
    object: "aiask.stock_data_source_test",
    provider,
    mode: String(body.mode || "connectivity"),
    success,
    status: success ? "ready" : enabled ? "unconfigured" : "disabled",
    configured,
    latency_ms: 8,
    sample_count: success ? 3 : 0,
    http_status: provider && !["akshare", "tdx"].includes(provider) ? 200 : undefined,
    error_code: success ? undefined : "MOCK_SOURCE_UNCONFIGURED",
    error: success ? null : "Mock 数据源缺少必填字段或已停用。",
    source: redactStockDataSource(source),
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
    status: envelope("agent_factory_status", {
      status: "ready",
      runtime_enabled: true,
      event_runtime_mode: "readonly",
      daily_run_count: 7,
      cycle_count: 24,
      recent_run_diagnostics: {
        analyzed_run_count: 5,
        quality_progress: {
          recent_raw_b_or_above_rate_mean: 0.5,
          recent_strict_ready_given_raw_b_rate_mean: 0
        },
        blocker_reason_topn: [
          { reason_code: "diagnostic_only_not_allowed_for_incubation", count: 15 },
          { reason_code: "default_profile_not_allowed_for_single_name_runtime", count: 10 },
          { reason_code: "execution_readiness_tier:missing_executable_contract", count: 10 }
        ],
        recent_runs: [{ run_id: "run_factory_1", status: "completed" }]
      },
      strict_incubation_blocker_summary: {
        contract_version: "strategy_factory.strict_incubation_blockers.v1",
        status: "blocked",
        headline: "Recent runs still fail formal admission because strict incubation readiness is zero.",
        window_size: 5,
        analyzed_run_count: 5,
        analyzed_strategy_count: 20,
        submitted_count: 35,
        strict_not_ready_count: 20,
        raw_b_or_above_count: 10,
        raw_b_or_above_rate: 0.5,
        strict_ready_given_raw_b_count: 0,
        strict_ready_given_raw_b_rate: 0,
        observe_lane_count: 18,
        diagnostic_lane_count: 2,
        top_blockers: [
          {
            reason_code: "diagnostic_only_not_allowed_for_incubation",
            count: 15,
            label: "Diagnostic-only runtime cannot enter formal incubation.",
            next_action: "Route only non-diagnostic runtime evidence to formal incubation; keep diagnostic samples in observe."
          },
          {
            reason_code: "default_profile_not_allowed_for_single_name_runtime",
            count: 10,
            label: "Default runtime profile is not allowed for single-name formal runtime.",
            next_action: "Attach a single-name runtime profile before requesting formal admission."
          },
          {
            reason_code: "execution_readiness_tier:missing_executable_contract",
            count: 10,
            label: "Executable contract readiness is missing.",
            next_action: "Persist the executable DSL/runtime contract and replay admission."
          }
        ],
        sample_blocked_strategies: [
          {
            strategy_id: "factory_mock_strict_1",
            family: "momentum",
            grade: "A",
            submission_lane: "observe_incubation",
            strict_incubation_ready: false,
            blockers: [
              "diagnostic_only_not_allowed_for_incubation",
              "default_profile_not_allowed_for_single_name_runtime",
              "execution_readiness_tier:missing_executable_contract"
            ]
          }
        ],
        next_action: "Route only non-diagnostic runtime evidence to formal incubation; keep diagnostic samples in observe."
      },
      configured: true,
      database_configured: true,
      run_count: 7
    }),
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

const mockIncubationHitRateReport = {
  report_date: "2026-06-05",
  generated_at: "2026-06-05T02:45:00Z",
  summary: {
    total_incubating: 8,
    total_with_signals: 7,
    auto_promoted: 1,
    stage_counts: {
      candidate: 3,
      observe: 2,
      graduation_ready: 1,
      blocked: 2
    }
  },
  hit_rate_dashboard: {
    overall: {
      total_signals: 38,
      hit_count: 23,
      hit_rate: 0.6053,
      avg_skill_lcb: 0.018,
      avg_forward_sharpe: 0.86,
      strategy_count: 8
    },
    by_family: {
      momentum: {
        hit_rate: 0.667,
        total_n: 18,
        avg_skill_lcb: 0.041,
        avg_forward_sharpe: 1.22,
        strategy_count: 3,
        promotion_ready_count: 1,
        blocked_count: 0,
        missing_forward_windows: 0
      },
      mean_reversion: {
        hit_rate: 0.455,
        total_n: 11,
        avg_skill_lcb: -0.012,
        avg_forward_sharpe: 0.21,
        strategy_count: 2,
        promotion_ready_count: 0,
        blocked_count: 1,
        missing_forward_windows: 2
      },
      event_driven: {
        hit_rate: 0.52,
        total_n: 9,
        avg_skill_lcb: 0.005,
        avg_forward_sharpe: 0.48,
        strategy_count: 3,
        promotion_ready_count: 0,
        blocked_count: 2,
        missing_forward_windows: 3
      }
    },
    by_regime: {
      bull: {
        hit_rate: 0.71,
        total_n: 14,
        avg_skill_lcb: 0.052,
        avg_forward_sharpe: 1.34,
        strategy_count: 3,
        promotion_ready_count: 1,
        blocked_count: 0,
        missing_forward_windows: 0
      },
      range: {
        hit_rate: 0.46,
        total_n: 13,
        avg_skill_lcb: -0.018,
        avg_forward_sharpe: 0.16,
        strategy_count: 3,
        promotion_ready_count: 0,
        blocked_count: 1,
        missing_forward_windows: 2
      },
      volatile: {
        hit_rate: 0.5,
        total_n: 11,
        avg_skill_lcb: 0.002,
        avg_forward_sharpe: 0.32,
        strategy_count: 2,
        promotion_ready_count: 0,
        blocked_count: 2,
        missing_forward_windows: 3
      }
    },
    by_stage: {
      candidate: { hit_rate: 0.54, total_n: 18, avg_skill_lcb: 0.006, strategy_count: 3, blocked_count: 1 },
      observe: { hit_rate: 0.49, total_n: 9, avg_skill_lcb: -0.004, strategy_count: 2, blocked_count: 1 },
      graduation_ready: { hit_rate: 0.667, total_n: 6, avg_skill_lcb: 0.041, strategy_count: 1, promotion_ready_count: 1 },
      blocked: { hit_rate: 0.42, total_n: 5, avg_skill_lcb: -0.022, strategy_count: 2, blocked_count: 2 }
    },
    trend: {
      available: true,
      improvement: 0.074,
      direction: "improving"
    }
  },
  promotion_blocker_summary: {
    status: "blocked",
    blocked_strategy_count: 3,
    top_blockers: [
      {
        reason_code: "missing_forward_window_5d",
        count: 3,
        label: "5d forward window is not complete.",
        next_action: "Wait for the 5d forward verification window or exclude incomplete samples from promotion review."
      },
      {
        reason_code: "execution_audit_pending",
        count: 2,
        label: "Execution audit replay has not accepted the strategy.",
        next_action: "Run execution audit replay and attach acceptance evidence before graduation."
      },
      {
        reason_code: "governance_review_required",
        count: 1,
        label: "Governance review is required before promotion.",
        next_action: "Complete governance review for the graduation-ready strategy."
      }
    ]
  },
  feedback_actions: {
    families_to_boost: ["momentum"],
    families_to_cooldown: ["mean_reversion"],
    families_to_freeze: ["event_driven"]
  },
  lifecycle_evidence: [
    {
      strategy_id: "strategy_momentum_cn",
      strategy_name: "Momentum CN",
      family: "momentum",
      regime: "bull",
      current_stage: "graduation_ready",
      lifecycle_state: "graduation_ready",
      observed_days: 24,
      trade_days: 18,
      hit_rate: 0.667,
      skill_lcb: 0.041,
      forward_sharpe: 1.22,
      forward_windows_completed: ["1d", "3d", "5d"],
      execution_audit: { status: "passed", accepted: true, replay_count: 12 },
      risk_gate: "passed",
      governance_status: "review_required",
      promotion_blockers: ["governance_review_required"],
      next_action: "Complete governance review and attach reviewer acceptance."
    },
    {
      strategy_id: "strategy_event_cn",
      strategy_name: "Event CN",
      family: "event_driven",
      regime: "volatile",
      current_stage: "blocked",
      lifecycle_state: "blocked",
      observed_days: 11,
      trade_days: 6,
      hit_rate: 0.5,
      skill_lcb: 0.002,
      forward_sharpe: 0.32,
      forward_windows_completed: ["1d", "3d"],
      execution_audit: { status: "pending", accepted: false, replay_count: 0 },
      risk_gate: "passed",
      governance_status: "not_started",
      promotion_blockers: ["missing_forward_window_5d", "execution_audit_pending"],
      next_action: "Finish the 5d forward window and rerun execution audit."
    },
    {
      strategy_id: "strategy_reversal_cn",
      strategy_name: "Mean Reversion CN",
      family: "mean_reversion",
      regime: "range",
      current_stage: "observe",
      lifecycle_state: "observe",
      observed_days: 14,
      trade_days: 9,
      hit_rate: 0.455,
      skill_lcb: -0.012,
      forward_sharpe: 0.21,
      forward_windows_completed: ["1d"],
      execution_audit: { status: "not_started", accepted: false, replay_count: 0 },
      risk_gate: "soft_fail",
      governance_status: "not_started",
      promotion_blockers: ["weak_skill_lcb", "missing_forward_window_3d", "missing_forward_window_5d"],
      next_action: "Keep in observe until skill LCB and forward windows recover."
    }
  ],
  source_chain: ["desktop.mockApi", "incubation_factory.hit_rate_report_generated"]
};

const mockIncubationDomainEvents = [
  {
    id: "inc_evt_report_001",
    event_id: "inc_evt_report_001",
    event_type: "incubation_factory.hit_rate_report_generated",
    aggregate_id: "incubation_factory",
    severity: "info",
    created_at: "2026-06-05T02:45:00Z",
    payload: mockIncubationHitRateReport
  },
  {
    id: "inc_evt_stage_001",
    event_id: "inc_evt_stage_001",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_momentum_cn",
    strategy_id: "strategy_momentum_cn",
    status: "graduation_ready",
    severity: "info",
    created_at: "2026-06-05T02:40:00Z",
    payload: {
      strategy_id: "strategy_momentum_cn",
      strategy_name: "Momentum CN",
      from_stage: "observe",
      to_stage: "graduation_ready",
      family: "momentum",
      regime: "bull",
      lifecycle_state: "graduation_ready",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[0]
    }
  },
  {
    id: "inc_evt_stage_002",
    event_id: "inc_evt_stage_002",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_event_cn",
    strategy_id: "strategy_event_cn",
    status: "blocked",
    severity: "warn",
    created_at: "2026-06-05T02:35:00Z",
    payload: {
      strategy_id: "strategy_event_cn",
      strategy_name: "Event CN",
      from_stage: "candidate",
      to_stage: "blocked",
      family: "event_driven",
      regime: "volatile",
      lifecycle_state: "blocked",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[1],
      promotion_blockers: ["missing_forward_window_5d", "execution_audit_pending"]
    }
  },
  {
    id: "inc_evt_stage_003",
    event_id: "inc_evt_stage_003",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_reversal_cn",
    strategy_id: "strategy_reversal_cn",
    status: "observe",
    severity: "warn",
    created_at: "2026-06-05T02:30:00Z",
    payload: {
      strategy_id: "strategy_reversal_cn",
      strategy_name: "Mean Reversion CN",
      from_stage: "candidate",
      to_stage: "observe",
      family: "mean_reversion",
      regime: "range",
      lifecycle_state: "observe",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[2],
      promotion_blockers: ["weak_skill_lcb", "missing_forward_window_3d", "missing_forward_window_5d"]
    }
  },
  {
    id: "factory_evt_run_001",
    event_id: "factory_evt_run_001",
    event_type: "factory.run_completed",
    aggregate_id: "factory_run_mock",
    strategy_id: "strategy_mock",
    status: "completed",
    severity: "info",
    created_at: "2026-06-05T01:55:00Z",
    payload: {
      decision: "review",
      strategy_id: "strategy_mock",
      candidate_count: 12
    }
  }
];

function incubationFactoryStatusPayload() {
  return {
    status: "ready",
    run_count: 3,
    error_count: 0,
    last_run_at: "2026-06-05T02:45:00Z",
    last_result_status: "completed",
    report: mockIncubationHitRateReport,
    latest_lifecycle_state: mockIncubationHitRateReport.lifecycle_evidence[0],
    promotion_blocker_summary: mockIncubationHitRateReport.promotion_blocker_summary,
    source_chain: ["desktop.mockApi", "agent_incubation_factory_status"]
  };
}

function strategyDomainEventsPayload(body: Record<string, unknown>) {
  const requestedType = String(body.event_type || "");
  const limit = safeLimit(body.limit, 20);
  const events = requestedType
    ? mockIncubationDomainEvents.filter((event) => event.event_type === requestedType)
    : mockIncubationDomainEvents;
  return {
    events: events.slice(0, limit),
    count: events.length,
    event_type: requestedType || "all",
    source_chain: ["desktop.mockApi", "agent_strategy_domain_events"]
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
        baseline: HERMES_BASELINE,
        baseline_version: HERMES_BASELINE_VERSION,
        baseline_release_tag: HERMES_RELEASE_TAG,
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        full_mode_active: true,
        evaluated_toolset: "general_full"
      },
      parity: {
        object: "aiask.capability_parity",
        baseline: HERMES_BASELINE,
        baseline_version: HERMES_BASELINE_VERSION,
        baseline_release_tag: HERMES_RELEASE_TAG,
        scope: "hermes_full_runtime",
        legacy_scope: "financial_product_runtime",
        embedded_vendor_runtime: false,
        required_count: 12,
        covered_count: 12,
        complete_count: 11,
        coverage_ratio: 1,
        complete_ratio: 0.92,
        status: "in_progress",
        strict_status: "in_progress",
        strict_hermes_tool_count: 58,
        strict_gateway_platform_count: 22,
        code_status: "present",
        core_code_status: "present",
        mock_status: "passed",
        live_status: "live_unverified",
        live_unverified_count: 27,
        feature_count: 19,
        implemented_features_count: 19,
        matrix: [],
        v014_delta: {
          baseline: "Hermes v0.14.0 full runtime capability reference",
          release_tag: "v2026.5.16",
          total: 18,
          implemented_count: 11,
          partial_count: 5,
          missing_count: 0,
          excluded_by_design_count: 2,
          implemented: [{ reference: "browser_snapshot", area: "browser", aiask_tools: ["agent_browser_snapshot"], missing_aiask_tools: [], status: "implemented" }],
          partial: [{ reference: "rl_training", area: "rl", aiask_tools: ["agent_rl_list_environments"], missing_aiask_tools: [], status: "live_unverified", required_env: ["TINKER_API_KEY", "WANDB_API_KEY"] }],
          missing: [],
          excluded_by_design: [{ reference: "openai_compatible_local_proxy", area: "models", aiask_tools: ["agent_model_manage"], missing_aiask_tools: [], status: "excluded_by_design" }]
        },
        v016_delta: {
          baseline: HERMES_V016_BASELINE,
          release_tag: HERMES_RELEASE_TAG,
          total: 19,
          implemented_count: 6,
          partial_count: 13,
          missing_count: 0,
          excluded_by_design_count: 0,
          implemented: [
            { reference: "desktop_native_shell", feature: "desktop_native_shell", area: "desktop", aiask_tools: ["agent_tool_catalog"], missing_aiask_tools: [], status: "implemented" },
            { reference: "undo_last_turns", feature: "undo_last_turns", area: "session", aiask_tools: ["agent_tui_status"], missing_aiask_tools: [], status: "implemented" },
            { reference: "checkpoint_and_rollback", feature: "checkpoint_and_rollback", area: "file", aiask_tools: ["agent_file_checkpoint", "agent_file_rollback"], missing_aiask_tools: [], status: "implemented" },
            { reference: "model_picker_profiles_and_fallback", feature: "model_picker_profiles_and_fallback", area: "models", aiask_tools: ["agent_model_manage"], missing_aiask_tools: [], status: "implemented" }
          ],
          partial: [
            { reference: "prompt_caching_controls", feature: "prompt_caching_controls", area: "models", aiask_tools: ["agent_model_manage"], missing_aiask_tools: [], status: "implemented", description: "AIASK exposes prompt-cache policy/status and applies Anthropic cache_control markers when enabled." },
            { reference: "session_archive_search_and_links", feature: "session_archive_search_and_links", area: "session", aiask_tools: ["agent_session_search", "agent_session_handoff"], missing_aiask_tools: [], status: "partial", description: "Mock parity includes session search, archive/unarchive list filtering, include_archived flags, and Desktop archive/restore controls; cross-profile links remain partial." },
            { reference: "browser_backend_matrix", feature: "browser_backend_matrix", area: "browser", aiask_tools: ["agent_browser_navigate"], missing_aiask_tools: [], status: "partial" }
          ],
          missing: []
        }
      },
      readiness: {
        object: "aiask.hermes_readiness",
        status: "ready",
        parity_baseline: HERMES_BASELINE,
        baseline_version: HERMES_BASELINE_VERSION,
        baseline_release_tag: HERMES_RELEASE_TAG,
        live_evidence: {
          object: "aiask.hermes_live_evidence",
          baseline: HERMES_BASELINE,
          baseline_version: HERMES_BASELINE_VERSION,
          baseline_release_tag: HERMES_RELEASE_TAG,
          code_status: "present",
          core_code_status: "present",
          mock_status: "passed",
          live_status: "live_unverified",
          strict_status: "in_progress",
          live_unverified_count: 27,
          required_env_names: ["OPENAI_API_KEY", "TINKER_API_KEY", "WANDB_API_KEY"],
          required_env_groups: ["OPENAI_API_KEY", "TINKER_API_KEY", "WANDB_API_KEY"],
          items: [
            { kind: "tool", name: "rl_start_training", area: "rl", code_status: "present", mock_status: "passed", live_status: "skipped_missing_credentials", required_env: ["TINKER_API_KEY", "WANDB_API_KEY"], safe_to_smoke: true }
          ]
        }
      },
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
          { name: "factory_status", method: "POST", path: "/v1/tools/agent_factory_status", observes: ["success", "runtime_enabled", "event_runtime_mode", "daily_run_count", "cycle_count"] },
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
    stock_data_sources: stockDataSourcesStatus(),
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
  if (tool === "agent_stock_live_quote") {
    const code = String(body.code || body.stock_code || body.symbol || body.ticker || "600519");
    return envelope(tool, {
      code,
      price: 123.45,
      change: 1.5,
      change_pct: 1.23,
      volume: 1200000,
      amount: 148140000,
      provider: "sina",
      data_timestamp: "2026-05-22T09:00:00+08:00",
      source_chain: ["desktop.mockApi", "akshare", "sina"],
      fallback_reason: null
    });
  }
  if (tool === "agent_stock_news_digest") {
    const code = String(body.code || body.stock_code || body.symbol || body.ticker || "600519");
    return envelope(tool, {
      code,
      items: [
        {
          title: "Mock 财经新闻",
          url: "https://example.com/aiask/mock-news",
          provider: "eastmoney",
          published_at: "2026-05-22T08:55:00+08:00",
          excerpt: "Mock 新闻来源链接，用于验证 Desktop 证据展示。"
        }
      ],
      source_chain: ["desktop.mockApi", "eastmoney"],
      fetched_at: "2026-05-22T09:00:00Z"
    });
  }
  if (tool === "agent_factory_status") return strategyFactory().status;
  if (tool === "agent_factory_runs") return strategyFactory().runs;
  if (tool === "agent_strategy_review_snapshot") return strategyFactory().review_snapshot;
  if (tool === "agent_incubation_factory_status") return envelope(tool, incubationFactoryStatusPayload());
  if (tool === "agent_strategy_domain_events") return envelope(tool, strategyDomainEventsPayload(body));
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
  if (cleanPath === "/v1/desktop/stock-data-sources" && method === "GET") return ok(stockDataSourcesStatus() as T);
  if (cleanPath === "/v1/desktop/stock-data-sources" && method === "POST") return ok(saveMockStockDataSource(body) as T);
  if (cleanPath === "/v1/desktop/stock-data-sources/test") return ok(testMockStockDataSource(body) as T);
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
  if (cleanPath === "/v1/desktop/events" && method === "POST") {
    const rawEvents = Array.isArray(body.events) ? body.events : [body];
    const events = rawEvents
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
      .map((item, index) => ({
        id: mockActivityEvents.length + index + 1,
        user_id: String(item.user_id || profile.user_id || "local"),
        session_id: item.session_id ? String(item.session_id) : "sess_mock",
        run_id: item.run_id ? String(item.run_id) : null,
        trace_id: item.trace_id ? String(item.trace_id) : `trace_mock_event_${mockActivityEvents.length + index + 1}`,
        page_key: item.page_key ? String(item.page_key) : null,
        route: item.route ? String(item.route) : null,
        event_type: String(item.event_type || "event"),
        target_type: item.target_type ? String(item.target_type) : null,
        target_id: item.target_id ? String(item.target_id) : null,
        target_label: item.target_label ? String(item.target_label) : null,
        target_testid: item.target_testid ? String(item.target_testid) : null,
        payload: redactedAuditValue(item.payload || {}) as Record<string, unknown>,
        source: String(item.source || "desktop.mock"),
        created_at: mockNow()
      }));
    mockActivityEvents = [...events, ...mockActivityEvents].slice(0, 200);
    return ok({ object: "list", data: events, count: events.length, secrets_redacted: true } as T);
  }
  if (cleanPath === "/v1/desktop/feedback" && method === "POST") {
    const feedback = {
      id: mockFeedbackEvents.length + 1,
      feedback_id: String(body.feedback_id || `feedback_mock_${mockFeedbackEvents.length + 1}`),
      user_id: String(body.user_id || profile.user_id || "local"),
      session_id: body.session_id || "sess_mock",
      run_id: body.run_id || null,
      target_type: String(body.target_type || "page"),
      target_id: body.target_id || null,
      feedback_type: String(body.feedback_type || "thumbs_up"),
      rating: body.rating ?? null,
      comment: body.comment || null,
      allow_learning: Boolean(body.allow_learning),
      payload: redactedAuditValue(body.payload || {}),
      created_at: mockNow()
    };
    mockFeedbackEvents = [feedback, ...mockFeedbackEvents].slice(0, 100);
    return ok({ object: "aiask.feedback", data: feedback, secrets_redacted: true } as T);
  }
  const userActivityMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/activity$/);
  if (userActivityMatch) {
    const userId = decodeURIComponent(userActivityMatch[1]);
    const limit = Number(query.get("limit") || 20);
    return ok({
      object: "aiask.user_activity",
      user_id: userId,
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId).slice(0, limit),
      runs: mockRunSummaries.slice(0, limit),
      events: mockActivityEvents.filter((event) => !event.user_id || event.user_id === userId).slice(0, limit),
      tool_invocations: mockToolInvocations.filter((item) => !item.user_id || item.user_id === userId).slice(0, limit),
      feedback: mockFeedbackEvents.filter((item) => !item.user_id || item.user_id === userId).slice(0, limit),
      policy: userPolicy(userId),
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/analytics/summary") {
    const userId = query.get("user_id") || undefined;
    const events = mockActivityEvents.filter((event) => !userId || event.user_id === userId);
    const tools = mockToolInvocations.filter((item) => !userId || item.user_id === userId);
    const feedback = mockFeedbackEvents.filter((item) => !userId || item.user_id === userId);
    const toolNames = Array.from(new Set(tools.map((item) => String(item.tool_name || "tool"))));
    return ok({
      object: "aiask.analytics_summary",
      scope: userId ? "user" : "aggregate",
      user_id: userId || null,
      totals: { events: events.length, tool_invocations: tools.length, feedback: feedback.length },
      events_by_type: Array.from(new Set(events.map((event) => event.event_type))).map((event_type) => ({
        event_type,
        count: events.filter((event) => event.event_type === event_type).length
      })),
      pages: Array.from(new Set(events.map((event) => event.page_key || event.route || "unknown"))).map((page_key) => ({
        page_key,
        count: events.filter((event) => (event.page_key || event.route || "unknown") === page_key).length
      })),
      tools: toolNames.map((tool_name) => {
        const rows = tools.filter((item) => item.tool_name === tool_name);
        const failed = rows.filter((item) => item.status !== "succeeded").length;
        return { tool_name, count: rows.length, succeeded: rows.length - failed, failed, failure_rate: rows.length ? failed / rows.length : 0, avg_duration_ms: 5 };
      }),
      feedback: Array.from(new Set(feedback.map((item) => `${item.target_type}:${item.feedback_type}`))).map((key) => {
        const [target_type, feedback_type] = key.split(":");
        return { target_type, feedback_type, count: feedback.filter((item) => `${item.target_type}:${item.feedback_type}` === key).length, avg_rating: null };
      }),
      secrets_redacted: true
    } as T);
  }
  const userExportMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
  if (userExportMatch) {
    const userId = decodeURIComponent(userExportMatch[1]);
    return ok({
      object: "aiask.user_data_export",
      user_id: userId,
      exported_at: mockNow(),
      profile_policy: userPolicy(userId),
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId),
      messages: mockSessionMessages,
      runs: mockRunSummaries,
      run_events: mockRunEvents,
      activity_events: mockActivityEvents.filter((event) => !event.user_id || event.user_id === userId),
      tool_invocations: mockToolInvocations.filter((item) => !item.user_id || item.user_id === userId),
      feedback: mockFeedbackEvents.filter((item) => !item.user_id || item.user_id === userId),
      sources: mockAgentSources.filter((item) => !item.user_id || item.user_id === userId),
      artifacts: mockAgentArtifacts.filter((item) => !item.user_id || item.user_id === userId),
      analytics: {
        object: "aiask.analytics_summary",
        scope: "user",
        user_id: userId,
        totals: { events: mockActivityEvents.length, tool_invocations: mockToolInvocations.length, feedback: mockFeedbackEvents.length },
        events_by_type: [],
        pages: [],
        tools: [],
        feedback: [],
        secrets_redacted: true
      },
      secrets_redacted: true
    } as T);
  }
  const userDeleteMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/delete$/);
  if (userDeleteMatch && method === "POST") {
    const userId = decodeURIComponent(userDeleteMatch[1]);
    const dryRun = body.dry_run !== false;
    const counts = {
      sessions: currentMockSessionSummaries().filter((session) => !session.user_id || session.user_id === userId).length,
      messages: mockSessionMessages.length,
      responses: 0,
      runs: mockRunSummaries.length,
      run_events: mockRunEvents.length,
      activity_events: mockActivityEvents.filter((event) => !event.user_id || event.user_id === userId).length,
      tool_invocations: mockToolInvocations.filter((item) => !item.user_id || item.user_id === userId).length,
      feedback: mockFeedbackEvents.filter((item) => !item.user_id || item.user_id === userId).length,
      sources: mockAgentSources.filter((item) => !item.user_id || item.user_id === userId).length,
      artifacts: mockAgentArtifacts.filter((item) => !item.user_id || item.user_id === userId).length,
      search_rows: 0
    };
    if (!dryRun) {
      mockActivityEvents = mockActivityEvents.filter((event) => event.user_id !== userId);
      mockToolInvocations = mockToolInvocations.filter((item) => item.user_id !== userId);
      mockFeedbackEvents = mockFeedbackEvents.filter((item) => item.user_id !== userId);
    }
    return ok({
      object: "aiask.user_data_delete",
      user_id: userId,
      dry_run: dryRun,
      hard_delete: Boolean(body.hard_delete),
      anonymized_user_id: body.hard_delete ? null : `deleted:${userId}`,
      counts,
      deleted_at: dryRun ? undefined : mockNow(),
      external_side_effects: "not_rolled_back",
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/desktop/retention/sweep" && method === "POST") {
    return ok({
      object: "aiask.retention_sweep",
      dry_run: body.dry_run !== false,
      user_id: body.user_id || null,
      counts: { user_activity_events: 0, tool_invocations_payloads: 0, run_events: 0, feedback_events: 0, messages: 0 },
      tables: ["user_activity_events", "tool_invocations_payloads", "run_events", "feedback_events", "messages"],
      market_data_affected: false,
      secrets_redacted: true
    } as T);
  }
  const learningMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/learning-dataset$/);
  if (learningMatch) {
    const userId = decodeURIComponent(learningMatch[1]);
    const policy = userPolicy(userId);
    const items = policy.allow_learning ? mockFeedbackEvents.filter((item) => item.user_id === userId && item.allow_learning) : [];
    return ok({
      object: "aiask.learning_dataset",
      user_id: userId,
      allowed: Boolean(policy.allow_learning),
      items,
      count: items.length,
      reason: policy.allow_learning ? undefined : "learning_not_allowed",
      secrets_redacted: true
    } as T);
  }
  const recommendationMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/recommendations$/);
  if (recommendationMatch) {
    const userId = decodeURIComponent(recommendationMatch[1]);
    return ok({
      object: "aiask.workflow_recommendations",
      user_id: userId,
      data_source: "local_user_activity",
      data: [
        { id: "feedback:collect", kind: "feedback_collection", priority: "medium", title: "Collect explicit feedback", reason: "Mock recommendation." }
      ],
      count: 1,
      secrets_redacted: true
    } as T);
  }
  const userPolicyMatch = cleanPath.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
  if (userPolicyMatch) {
    const userId = decodeURIComponent(userPolicyMatch[1]);
    if (method === "PATCH") {
      mockUserDataPolicies[userId] = { ...userPolicy(userId), ...body, user_id: userId, updated_at: mockNow() };
    }
    return ok({ object: "aiask.user_data_policy", data: userPolicy(userId) } as T);
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
  if (cleanPath === "/v1/ai/config" && method === "GET") return ok(aiConfig() as T);
  if (cleanPath === "/v1/ai/config" && method === "PATCH") {
    const preset = aiProviderPresets.find((item) => item.id === body.preset);
    const provider = String(body.provider || preset?.provider || mockModelConfig.provider);
    const model = String(body.model || preset?.default_model || mockModelConfig.model);
    const baseUrl = String(body.base_url ?? preset?.base_url ?? mockModelConfig.base_url);
    mockModelConfig = {
      preset: String(body.preset || preset?.id || "custom-openai-compatible"),
      provider,
      model,
      base_url: baseUrl,
      api_key_configured: Boolean(body.api_key || mockModelConfig.api_key_configured || provider === "mock"),
      mock: true,
      prompt_cache_enabled: Boolean(body.prompt_cache_enabled),
      prompt_cache_recent_messages: Math.max(0, Math.min(Number(body.prompt_cache_recent_messages || 3), 20))
    };
    const status = aiStatus();
    return ok({
      object: "aiask.ai_config",
      saved: true,
      provider: mockModelConfig.provider,
      model: mockModelConfig.model,
      base_url_configured: Boolean(mockModelConfig.base_url),
      api_key_configured: mockModelConfig.api_key_configured,
      mock: mockModelConfig.mock,
      configured: true,
      prompt_cache: status.prompt_cache,
      updated_keys: ["AIASK_AGENT_MODEL_PROVIDER", "AIASK_AGENT_MODEL", "OPENAI_BASE_URL", "AIASK_AGENT_PROMPT_CACHE_ENABLED", "AIASK_AGENT_PROMPT_CACHE_RECENT_MESSAGES", ...(body.api_key ? ["OPENAI_API_KEY"] : [])],
      env_file: "mock://aiask/.env",
      secrets_redacted: true
    } as T);
  }
  if (cleanPath === "/v1/ai/smoke") return ok({ object: "aiask.ai_smoke", configured: true, success: true, provider: mockModelConfig.provider, model: body.model || mockModelConfig.model, mock: true, latency_ms: 5, response_preview: "AI_SMOKE_PASSED", secrets_redacted: true } as T);
  if (cleanPath === "/v1/ai/models") return ok({ data: [{ id: mockModelConfig.model, object: "model", owned_by: mockModelConfig.provider }, { id: `${mockModelConfig.model}-mini`, object: "model", owned_by: mockModelConfig.provider }], configured: true } as T);
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
  const runTraceEvalMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/trace-eval$/);
  if (runTraceEvalMatch) {
    return ok(mockRunTraceEval(decodeURIComponent(runTraceEvalMatch[1])) as T);
  }
  const runArtifactsMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/artifacts$/);
  if (runArtifactsMatch) {
    const runId = decodeURIComponent(runArtifactsMatch[1]);
    return ok({
      object: "list",
      run_id: runId,
      data: filterMockArtifacts({
        runId,
        kind: query.get("kind"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const runSourcesMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/sources$/);
  if (runSourcesMatch) {
    const runId = decodeURIComponent(runSourcesMatch[1]);
    return ok({
      object: "list",
      run_id: runId,
      data: filterMockSources({
        runId,
        sourceType: query.get("source_type"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const runToolInvocationsMatch = cleanPath.match(/^\/v1\/runs\/([^/]+)\/tool-invocations$/);
  if (runToolInvocationsMatch) {
    const runId = decodeURIComponent(runToolInvocationsMatch[1]);
    const limit = Number(query.get("limit") || 100);
    return ok({
      object: "list",
      run_id: runId,
      data: mockToolInvocations.filter((item) => item.run_id === runId).slice(0, Math.max(1, Math.min(limit || 100, 1000)))
    } as T);
  }
  const sessionArtifactsMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/artifacts$/);
  if (sessionArtifactsMatch) {
    const sessionId = decodeURIComponent(sessionArtifactsMatch[1]);
    return ok({
      object: "list",
      session_id: sessionId,
      data: filterMockArtifacts({
        sessionId,
        kind: query.get("kind"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const sessionSourcesMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/sources$/);
  if (sessionSourcesMatch) {
    const sessionId = decodeURIComponent(sessionSourcesMatch[1]);
    return ok({
      object: "list",
      session_id: sessionId,
      data: filterMockSources({
        sessionId,
        sourceType: query.get("source_type"),
        limit: Number(query.get("limit") || 100)
      })
    } as T);
  }
  const artifactContentMatch = cleanPath.match(/^\/v1\/artifacts\/([^/]+)\/content$/);
  if (artifactContentMatch) {
    const artifactId = decodeURIComponent(artifactContentMatch[1]);
    const content = mockArtifactContent(artifactId);
    return ok((content || { object: "error", error: "artifact not found", artifact_id: artifactId }) as T);
  }
  const artifactMatch = cleanPath.match(/^\/v1\/artifacts\/([^/]+)$/);
  if (artifactMatch) {
    const artifactId = decodeURIComponent(artifactMatch[1]);
    return ok(({ object: "artifact", ...(mockAgentArtifacts.find((item) => item.artifact_id === artifactId) || { artifact_id: artifactId, status: "missing" }) }) as T);
  }
  const sourceMatch = cleanPath.match(/^\/v1\/sources\/([^/]+)$/);
  if (sourceMatch) {
    const sourceId = decodeURIComponent(sourceMatch[1]);
    return ok(({ object: "source", ...(mockAgentSources.find((item) => item.source_id === sourceId) || { source_id: sourceId, source_type: "missing" }) }) as T);
  }
  if (cleanPath === "/v1/search") {
    const includeArchived = query.get("include_archived") === "true";
    const activeSessions = currentMockSessionSummaries().filter((session) => includeArchived || !session.archived);
    return ok({
      object: "list",
      include_archived: includeArchived,
      data: activeSessions.map((session) => ({
        kind: "response",
        object_id: "resp_mock",
        session_id: session.session_id,
        user_id: session.user_id || profile.user_id,
        content: "Mock 回复命中",
      })),
    } as T);
  }
  if (cleanPath === "/v1/hermes/sessions") {
    const includeArchived = query.get("include_archived") === "true";
    return ok({
      object: "list",
      include_archived: includeArchived,
      data: currentMockSessionSummaries().filter((session) => includeArchived || !session.archived),
    } as T);
  }
  if (cleanPath === "/v1/hermes/handoffs") {
    return ok(mockHandoffQueue({
      userId: query.get("user_id"),
      sessionId: query.get("session_id"),
      status: query.get("status"),
      includeCompleted: query.get("include_completed") === "true",
      limit: Number(query.get("limit") || 100),
    }) as T);
  }
  const sessionResumeContextMatch = cleanPath.match(/^\/v1\/hermes\/sessions\/([^/]+)\/resume-context$/);
  if (sessionResumeContextMatch) {
    return ok(mockSessionResumeContext(decodeURIComponent(sessionResumeContextMatch[1])) as T);
  }
  const sessionUndoMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/undo$/);
  if (sessionUndoMatch && method === "POST") {
    const sessionId = decodeURIComponent(sessionUndoMatch[1]);
    const turnsValue = Number(body.turns || 1);
    const turns = Math.max(1, Math.min(Math.floor(Number.isFinite(turnsValue) ? turnsValue : 1), 100));
    const userIndexes = mockSessionMessages
      .map((item, index) => ({ role: String(item.role || ""), index }))
      .filter((item) => item.role === "user")
      .map((item) => item.index)
      .reverse()
      .slice(0, turns);
    const cutoff = userIndexes.length ? Math.min(...userIndexes) : -1;
    const deleted = cutoff >= 0 ? mockSessionMessages.slice(cutoff) : [];
    if (cutoff >= 0) mockSessionMessages = mockSessionMessages.slice(0, cutoff);
    return ok({
      object: "aiask.session_undo",
      implementation: "aiask_native",
      session_id: sessionId,
      turns_requested: turns,
      turns_undone: userIndexes.length,
      message_ids: deleted.map((item) => item.id || item.message_id),
      message_count: deleted.length,
      deleted_at: "2026-05-22T09:00:03Z",
      deleted_reason: String(body.reason || "desktop session undo"),
      deleted_by: "mock-control-token",
      soft_deleted: true,
      side_effects_rolled_back: false,
      external_side_effects: "not_rolled_back",
    } as T);
  }
  const sessionArchiveMatch = cleanPath.match(/^\/v1\/sessions\/([^/]+)\/archive$/);
  if (sessionArchiveMatch && method === "POST") {
    const sessionId = decodeURIComponent(sessionArchiveMatch[1]);
    const archived = body.archived !== false;
    const target = mockSessionSummaries.find((session) => session.session_id === sessionId);
    if (target) {
      target.archived = archived;
      target.archived_at = archived ? "2026-05-22T09:00:04Z" : null;
      target.archived_reason = archived ? String(body.reason || "desktop session archive") : null;
      target.metadata = {
        ...(target.metadata || {}),
        archived,
        archived_at: target.archived_at,
        archived_reason: target.archived_reason,
      };
    }
    return ok({
      object: "aiask.session_archive",
      implementation: "aiask_native",
      session_id: sessionId,
      archived,
      archived_at: target?.archived_at || null,
      archived_reason: target?.archived_reason || null,
      session: target,
    } as T);
  }
  if (cleanPath.startsWith("/v1/sessions/") && cleanPath.endsWith("/messages")) {
    return ok({ object: "list", data: mockSessionMessages } as T);
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
  if (toolMatch) {
    const toolName = decodeURIComponent(toolMatch[1]);
    recordMockToolInvocation(toolName, body);
    return ok(toolResult(toolName, body) as T);
  }
  const hermesToolMatch = cleanPath.match(/^\/v1\/hermes\/admin\/tools\/([^/]+)$/);
  if (hermesToolMatch) {
    const toolName = decodeURIComponent(hermesToolMatch[1]);
    recordMockToolInvocation(toolName, body);
    return ok(toolResult(toolName, body) as T);
  }

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
  if (cleanPath === "/v1/desktop/broker-readiness") {
    return ok({
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
    } as T);
  }
  if (cleanPath === "/v1/desktop/broker/sync") {
    const provider = String(body.provider || "qmt");
    const isThs = provider === "tonghuashun" || provider === "ths";
    const accounts = isThs ? mockThsBrokerAccounts : mockBrokerAccounts;
    const positions = isThs ? mockThsBrokerPositions : mockBrokerPositions;
    const orders = isThs ? mockThsBrokerOrders : mockBrokerOrders;
    const deals = isThs ? mockThsBrokerDeals : mockBrokerDeals;
    if (!body.consent) {
      return ok({
        object: "aiask.desktop.broker_readonly",
        success: false,
        data: null,
        error: "broker read-only sync requires explicit user consent",
        error_code: "BROKER_CONSENT_REQUIRED",
        read_only: true,
        live_trading_enabled: false,
        secrets_redacted: true
      } as T);
    }
    return ok({
      object: "aiask.desktop.broker_readonly",
      success: true,
      data: {
        sync_id: isThs ? "broker_sync_mock_ths" : "broker_sync_mock_qmt",
        profile: isThs ? mockThsBrokerProfile : mockBrokerProfile,
        counts: {
          accounts: accounts.length,
          positions: positions.length,
          orders: orders.length,
          deals: deals.length
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
    } as T);
  }
  if (cleanPath === "/v1/desktop/broker/accounts" || cleanPath === "/v1/desktop/broker/positions" || cleanPath === "/v1/desktop/broker/orders") {
    return ok(brokerSnapshotPayload(String(query.get("provider") || "qmt")) as T);
  }
  if (cleanPath === "/v1/desktop/broker/analytics/latest" || cleanPath === "/v1/desktop/broker/analytics/run") {
    const provider = cleanPath.endsWith("/run") ? String(body.provider || "qmt") : String(query.get("provider") || "qmt");
    return ok({
      object: "aiask.desktop.broker_readonly.analytics",
      success: true,
      data: { analytics: mockBrokerAnalytics(provider) },
      error: null,
      read_only: true,
      live_trading_enabled: false,
      secrets_redacted: true,
      source_chain: ["desktop.mockApi", "aiask_agent.broker_readonly"]
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
