import type { ApiHeaders } from "./api";
import type { CapabilityWorkbenchPayload, ToolCatalogItem } from "./types";

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
  { name: "agent_factor_validation", capability: "factor_validation", category: "financial_read", side_effect: "read_only", description: "Validate factor signals.", input_schema: { type: "object", properties: { codes: { type: "array" }, factors: { type: "array" } } }, examples: [{ arguments: { codes: ["600519", "000001"], factors: ["momentum"] } }] },
  { name: "agent_backtest_suite", capability: "backtest_suite", category: "financial_read", side_effect: "read_only", description: "Run strategy backtests.", input_schema: { type: "object", properties: { codes: { type: "array" }, strategy: { type: "string" } } }, examples: [{ arguments: { codes: ["600519", "000001"], strategy: "ma_cross" } }] },
  { name: "agent_portfolio_risk", capability: "portfolio_risk", category: "financial_read", side_effect: "read_only", description: "Analyze portfolio risk.", input_schema: { type: "object", properties: { codes: { type: "array" }, weights: { type: "array" } } }, examples: [{ arguments: { codes: ["600519", "000001"], weights: [0.5, 0.5] } }] },
  { name: "agent_quant_research_run", capability: "quant_research_run", category: "financial_read", side_effect: "read_only", description: "Run quant research pipeline." },
  { name: "agent_factory_status", capability: "strategy_factory_status", category: "financial_read", side_effect: "read_only", description: "Read strategy factory status.", input_schema: { type: "object", properties: { recent_run_limit: { type: "integer" } } } },
  { name: "agent_factory_runs", capability: "strategy_factory_runs", category: "financial_read", side_effect: "read_only", description: "List strategy factory runs.", input_schema: { type: "object", properties: { limit: { type: "integer" } } } },
  { name: "agent_strategy_review_snapshot", capability: "strategy_review_snapshot", category: "financial_read", side_effect: "read_only", description: "Read strategy review snapshots.", input_schema: { type: "object", properties: { limit: { type: "integer" } } } },
  { name: "agent_strategy_domain_events", capability: "strategy_domain_events", category: "financial_read", side_effect: "read_only", description: "List strategy domain events.", input_schema: { type: "object", properties: { event_type: { type: "string" }, limit: { type: "integer" } } } },
  { name: "agent_incubation_factory_status", capability: "incubation_factory_status", category: "financial_read", side_effect: "read_only", description: "Read incubation factory status." },
  { name: "agent_action_intent_create", capability: "action_intent_create", category: "financial_stateful", side_effect: "durable_intent", description: "Create an approval intent." },
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
  { name: "agent_model_manage", capability: "model_manage", category: "model_provider", side_effect: "stateful", description: "Inspect model providers." },
  { name: "agent_memory_manage", capability: "memory_manage", category: "memory_admin", side_effect: "stateful", description: "Manage memory providers." },
  { name: "agent_gateway_status", capability: "platform_gateway_status", category: "platform_gateway", side_effect: "read_only", description: "Read gateway status." },
  { name: "agent_gateway_platforms", capability: "platform_gateway_platforms", category: "platform_gateway", side_effect: "read_only", description: "List gateway platforms." },
  { name: "agent_learning_status", capability: "learning_status", category: "learning", side_effect: "read_only", description: "Read learning loop status." },
  { name: "agent_learning_review", capability: "learning_review", category: "learning", side_effect: "read_only", description: "Review learning proposals." },
  { name: "agent_rl_list_environments", capability: "rl_list_environments", category: "rl_training", side_effect: "read_only", description: "List RL environments." },
  { name: "agent_rl_get_config", capability: "rl_get_config", category: "rl_training", side_effect: "read_only", description: "Read RL config." },
  { name: "agent_job_list", capability: "cron_list", category: "cron_admin", side_effect: "read_only", description: "List background jobs." },
  { name: "agent_job_create", capability: "cron_create", category: "cron_admin", side_effect: "stateful", description: "Create background jobs." },
  { name: "agent_session_handoff", capability: "session_handoff", category: "memory_admin", side_effect: "stateful", description: "Manage session handoffs." }
];

let profile = {
  object: "aiask.local_profile",
  user_id: "local",
  profile_name: "Mock Local Operator",
  storage: "local_json",
  path: "mock://aiask/local-profile.json",
  updated_at: "2026-05-22T09:00:00Z",
  status: "ready",
  secrets_redacted: true
};

let jobs: Array<Record<string, unknown>> = [
  {
    job_id: "job_mock_research",
    name: "Daily research monitor",
    prompt: "Review mock market data.",
    schedule: "*/30 * * * *",
    enabled: true,
    user_id: "local",
    last_run_at: null
  }
];

const intents = new Map<string, Record<string, unknown>>();

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

function strategyFactory() {
  return {
    status: envelope("agent_factory_status", { status: "ready", configured: true, database_configured: true, run_count: 7 }),
    runs: envelope("agent_factory_runs", { runs: [{ run_id: "factory_run_mock", status: "completed", candidates: 12 }] }),
    review_snapshot: envelope("agent_strategy_review_snapshot", { status: "ready", reviews: [{ strategy_id: "strategy_mock", decision: "incubate" }] })
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
      memory: { status: "ready", provider: "sqlite" },
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
      auth_configured: true,
      auth_env_vars: ["AKSHARE_MCP_TOKEN"],
      missing_auth_env_vars: [],
      error_code: null,
      detail: null,
      servers: [{ name: "akshare-local", domain: "finance", transport: "streamable_http", configured: true }],
      tools: [
        { server: "akshare-local", name: "get_realtime_quote", wrapped_name: "agent_mcp_akshare_get_realtime_quote", domain: "quote", description: "Realtime quote" },
        { server: "akshare-local", name: "get_kline", wrapped_name: "agent_mcp_akshare_get_kline", domain: "kline", description: "K-line data" },
        { server: "akshare-local", name: "get_macro_indicator", wrapped_name: "agent_mcp_akshare_get_macro_indicator", domain: "macro", description: "Macro indicator" },
        { server: "akshare-local", name: "get_option_chain", wrapped_name: "agent_mcp_akshare_get_option_chain", domain: "options", description: "Option chain" }
      ],
      resources: [{ uri: "aiask://quotes", name: "quote resource" }],
      prompts: [{ name: "risk-review", description: "Risk review prompt" }],
      oauth: [{ server: "akshare-local", status: "mock_ready" }]
    },
    strategy_factory: strategyFactory(),
    quant: { data_status: { status: "ready" }, status: "ready" },
    financial_system: {
      object: "aiask.financial_readiness",
      status: "ready",
      production_ready: false,
      required_gates: [{ name: "approval_intents", status: "ready", required: true, detail: "Mock intent gate ready" }],
      optional_gates: [],
      summary: { ready: 1 },
      disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
    },
    skills: { gated: false, root: "mock://aiask/skills", skills: [{ name: "risk-review", description: "Risk review", path: "mock://skills/risk-review" }] },
    skill_packs: { object: "skill_packs", status: "ready", available_count: 2, packs: [{ name: "finance" }] },
    plugins: [{ name: "audit-plugin", enabled: true, source: "mock", description: "Audit hooks", tools: [{ name: "ping" }], commands: [], hooks: [] }],
    providers: { status: "ready" },
    memory: { status: "ready" },
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
    memory: { status: "ready", provider: "sqlite", path: "mock://aiask/agent_state.sqlite3" },
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
  if (tool === "agent_factor_validation") return envelope(tool, { status: "passed", ic_mean: 0.04, factors: body.factors || ["momentum"] });
  if (tool === "agent_backtest_suite") return envelope(tool, { status: "completed", sharpe: 1.2, max_drawdown: -0.08 });
  if (tool === "agent_portfolio_risk") return envelope(tool, { status: "completed", var_95: -0.021, stress: "passed" });
  if (tool === "agent_analyze_stock") return envelope(tool, { code: body.code || "600519", rating: "mock_watch", risk: "medium" });
  if (tool === "agent_factory_status") return strategyFactory().status;
  if (tool === "agent_factory_runs") return strategyFactory().runs;
  if (tool === "agent_strategy_review_snapshot") return strategyFactory().review_snapshot;
  if (tool === "agent_incubation_factory_status") return envelope(tool, { run_count: 3, error_count: 0, last_result_status: "completed" });
  if (tool === "agent_strategy_domain_events") return envelope(tool, { events: [{ event_type: body.event_type || "factory.run_completed", payload: { decision: "review" } }] });
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
  if (tool === "agent_job_list") return envelope(tool, { jobs });
  return envelope(tool, { status: "mock_ok", arguments: body });
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
  const { cleanPath } = parsePath(path);

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
  if (cleanPath === "/v1/desktop/settings/status") return ok(settingsStatus() as T);
  if (cleanPath === "/v1/desktop/data/status") return ok(dataStatus() as T);
  if (cleanPath === "/v1/desktop/data/sync-plan") {
    return ok({
      object: "aiask.desktop_data_sync_plan",
      status: "ready",
      data_status: dataStatus(),
      intent_request: {
        action: "data_sync.run_once",
        params: { codes: body.codes || ["600519"], task_type: body.task_type || "kline", period: body.period || "daily" },
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
  if (cleanPath === "/v1/ai/status") return ok(aiStatus() as T);
  if (cleanPath === "/v1/ai/smoke") return ok({ object: "aiask.ai_smoke", configured: true, success: true, provider: "project-root-api", model: body.model || "gpt-5.4", mock: true, latency_ms: 5, response_preview: "AI_SMOKE_PASSED", secrets_redacted: true } as T);
  if (cleanPath === "/v1/ai/models") return ok({ data: [{ id: "gpt-5.4", object: "model", owned_by: "project-root-api" }, { id: "gpt-5.4-mini", object: "model", owned_by: "project-root-api" }], configured: true } as T);
  if (cleanPath === "/v1/responses") return ok({ id: "resp_mock", object: "response", status: "completed", output_text: "AIASK_OK", metadata: { session_id: body.session_id || "sess_mock", run_id: "run_mock", mode: body.mode || "finance_safe", audit_events: [{ event: "mock" }] } } as T);
  if (cleanPath === "/v1/runs/run_mock/events") return ok({ object: "list", data: [{ id: "evt_mock", event: "run.completed", data: { status: "completed" } }] } as T);
  if (cleanPath === "/v1/search") return ok({ object: "list", data: [{ kind: "response", object_id: "resp_mock", session_id: "sess_mock", user_id: profile.user_id, content: "mock response hit" }] } as T);
  if (cleanPath === "/v1/hermes/sessions") return ok({ object: "list", data: [{ session_id: "sess_mock", title: "Mock research session", user_id: profile.user_id, updated_at: "2026-05-22T09:00:00Z" }] } as T);
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
  if (cleanPath === "/v1/terminal/sessions") {
    return ok({ object: "list", data: [{ session_id: "terminal_mock", backend: "local-powershell", status: "idle", user_id: profile.user_id }] } as T);
  }
  if (cleanPath === "/v1/gateway/status") {
    return ok({ object: "aiask.gateway_status", status: "ready", enabled_platforms: ["desktop"], pending_messages: 0 } as T);
  }
  if (cleanPath === "/v1/gateway/platforms") {
    return ok({ object: "list", data: [{ platform: "desktop", status: "ready" }, { platform: "discord", status: "missing_credentials" }] } as T);
  }
  if (cleanPath === "/v1/gateway/messages") {
    return ok({ object: "list", data: [{ message_id: "msg_gateway_mock", platform: "desktop", status: "delivered", user_id: profile.user_id }] } as T);
  }
  if (cleanPath === "/v1/gateway/directory") {
    return ok({ object: "list", data: [{ platform: "desktop", kind: "user", id: profile.user_id, display_name: profile.profile_name }] } as T);
  }
  if (cleanPath === "/v1/learning/status") {
    return ok({ object: "aiask.learning_status", status: "ready", proposal_count: 1, apply_requires_control: true } as T);
  }
  if (cleanPath === "/v1/learning/review") {
    return ok({ object: "list", data: [{ proposal_id: "learn_mock", status: "pending_review", summary: "Mock prompt improvement proposal" }] } as T);
  }
  if (cleanPath === "/v1/rl/environments") {
    return ok({ object: "list", data: { environments: [{ id: "finance_safe_eval", status: "ready" }], missing_env: ["TINKER_API_KEY"] } } as T);
  }
  if (cleanPath === "/v1/rl/config") {
    return ok({ object: "aiask.rl_config", status: "configured", provider: "mock", secrets_redacted: true } as T);
  }
  if (cleanPath === "/v1/rl/runs") {
    return ok({ object: "list", data: [{ run_id: "rl_mock", environment: "finance_safe_eval", status: "dry_run_ready" }] } as T);
  }
  if (cleanPath === "/v1/webhooks") {
    return ok({ object: "list", data: [{ webhook_id: "webhook_mock", platform: "desktop", status: "ready" }] } as T);
  }
  if (cleanPath === "/v1/approvals") {
    return ok({ object: "list", data: Array.from(intents.values()) } as T);
  }

  if (cleanPath === "/v1/jobs" && method === "GET") return ok({ object: "list", data: jobs } as T);
  if (cleanPath === "/v1/jobs" && method === "POST") {
    const job = { job_id: `job_mock_${jobs.length + 1}`, enabled: body.enabled ?? true, user_id: body.user_id || profile.user_id, ...body };
    jobs = [job, ...jobs];
    return ok({ object: "aiask.job", job } as T);
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
  if (cleanPath.startsWith("/v1/plugins/") && method === "PATCH") return ok({ object: "plugin_updated", enabled: body.enabled } as T);
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

  if (cleanPath === "/v1/connectors/summary") return ok({ status: "ready", data: { connectors: [{ type: "mcp", name: "akshare-local", status: "ready" }] } } as T);
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
    return ok(envelope("agent_quant_research_run", { research: { research_id: "research_mock", status: "completed", payload: { stages: [] }, report: { object: "report", research_id: "research_mock", status: "completed", summary: { benchmark: "000300", universe_size: 2, factor_count: 2 }, stages: [], disclaimer: "MOCK_NOT_INVESTMENT_ADVICE" } } }) as T);
  }
  if (cleanPath.includes("/report")) return ok({ object: "report", research_id: "research_mock", status: "completed", summary: { benchmark: "000300" } } as T);

  return ok({ object: "mock.unhandled", path: cleanPath, method, data: {}, status: "ready" } as T);
}

export { CONTROL_TOKEN as MOCK_CONTROL_TOKEN };
