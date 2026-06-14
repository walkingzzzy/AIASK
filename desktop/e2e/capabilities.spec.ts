import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";

const API_ORIGIN = "http://127.0.0.1:8767";
const CONTROL_TOKEN = "secret";

type FactoryMode = "success" | "degraded";

function hermesTools() {
  const required = [
    { hermes_tool: "discord_server", area: "platform", status: "implemented", aiask_tools: ["agent_discord_server"] },
    {
      hermes_tool: "feishu_drive_list_comment_replies",
      area: "platform",
      status: "implemented",
      aiask_tools: ["agent_feishu_drive_list_comment_replies"]
    },
    { hermes_tool: "rl_start_training", area: "rl", status: "live_unverified", aiask_tools: ["agent_rl_start_training"] },
    { hermes_tool: "terminal", area: "terminal", status: "implemented", aiask_tools: ["agent_terminal"] },
    { hermes_tool: "send_message", area: "delivery", status: "implemented", aiask_tools: ["agent_message_send"] },
    { hermes_tool: "computer_use", area: "computer_use", status: "implemented", aiask_tools: ["agent_computer_use"] },
    { hermes_tool: "video_generate", area: "multimodal", status: "live_unverified", aiask_tools: ["agent_video_generate"] },
    { hermes_tool: "x_search", area: "web", status: "live_unverified", aiask_tools: ["agent_x_search"] }
  ];
  const fillers = Array.from({ length: 54 - required.length }, (_, index) => ({
    hermes_tool: `fixture_tool_${String(index + 1).padStart(2, "0")}`,
    area: index % 2 ? "browser" : "memory",
    status: "implemented",
    aiask_tools: [`agent_fixture_tool_${String(index + 1).padStart(2, "0")}`]
  }));
  return [...required, ...fillers].map((item) => ({
    ...item,
    code_status: "present",
    mock_status: "passed",
    live_status: item.status === "live_unverified" ? "skipped_missing_credentials" : "not_required",
    missing_aiask_tools: []
  }));
}

function gatewayPlatforms() {
  const names = [
    "feishu",
    "dingtalk",
    "wecom",
    "weixin",
    "email",
    "webhook",
    "api_server",
    "telegram",
    "discord",
    "slack",
    "line",
    "teams",
    "whatsapp",
    "signal",
    "simplex",
    "matrix",
    "mattermost",
    "sms",
    "qqbot",
    "bluebubbles",
    "homeassistant",
    "wecom_callback"
  ];
  return names.map((name) => ({
    platform: name,
    aiask_adapter: name,
    status: name === "discord" ? "live_unverified" : "implemented",
    code_status: "present",
    mock_status: "passed",
    live_status: name === "discord" ? "skipped_missing_credentials" : "not_required"
  }));
}

function featureMapping() {
  return [
    {
      feature: "gateway_direct_delivery",
      area: "delivery",
      status: "implemented",
      code_status: "present",
      mock_status: "passed",
      live_status: "not_required",
      aiask_tools: ["agent_gateway_direct_deliver", "agent_gateway_send_message"],
      missing_aiask_tools: []
    },
    {
      feature: "mcp_tools",
      area: "mcp",
      status: "implemented",
      code_status: "present",
      mock_status: "passed",
      live_status: "not_required",
      aiask_tools: ["agent_mcp_manage"],
      missing_aiask_tools: []
    },
    {
      feature: "strategy_factory",
      area: "factory",
      status: "implemented",
      code_status: "present",
      mock_status: "passed",
      live_status: "not_required",
      aiask_tools: ["agent_factory_status", "agent_factory_runs", "agent_strategy_review_snapshot"],
      missing_aiask_tools: []
    }
  ];
}

function factoryEnvelope(mode: FactoryMode, kind: "status" | "runs" | "review") {
  if (mode === "degraded") {
    return {
      success: false,
      data: {
        configured: false,
        dependency: "strategy_factory",
        database_backend: "sqlite",
        database_configured: true,
        database_writable: true,
        database_path: "/tmp/akshare_mcp.sqlite3",
        detail: "E2E fixture: simulated strategy factory unavailable"
      },
      error: "E2E fixture: simulated strategy factory unavailable",
      error_code: "STRATEGY_FACTORY_UNAVAILABLE"
    };
  }
  const data =
    kind === "status"
      ? { configured: true, scheduler: "running", queued: 0, last_run_id: "factory_run_1" }
      : kind === "runs"
        ? { configured: true, runs: [{ run_id: "factory_run_1", status: "completed", universe: "CSI300" }] }
        : { configured: true, reviews: [{ strategy_id: "risk-review", decision: "promote", status: "approved" }] };
  return { success: true, data, error: null, error_code: null };
}

function capabilityPayload(authorized: boolean, factoryMode: FactoryMode) {
  const tools = hermesTools();
  const platforms = gatewayPlatforms();
  const features = featureMapping();
  const mcp = authorized
    ? {
        gated: false,
        registration_status: "registered",
        configured: true,
        config_path: "/tmp/mcp_servers.json",
        config_exists: true,
        detected_service_port: "3100",
        suggested_registration_url: "http://127.0.0.1:3100/mcp",
        servers: [
          {
            name: "finance-demo",
            domain: "financial",
            transport: "stdio",
            tools: ["quote"],
            resources_enabled: true,
            resources: [{ uri: "aiask://quotes" }],
            prompts_enabled: true,
            prompts: [{ name: "risk-review" }],
            oauth_configured: true,
            oauth_token_available: false
          }
        ],
        tools: [
          {
            server: "finance-demo",
            domain: "financial",
            transport: "stdio",
            name: "quote",
            wrapped_name: "agent_mcp_finance_demo_quote",
            description: "quote tool"
          }
        ],
        resources: [{ server: "finance-demo", uri: "aiask://quotes" }],
        prompts: [{ server: "finance-demo", name: "risk-review" }],
        oauth: [{ server: "finance-demo", configured: true, token_available: false }]
      }
    : {
        gated: true,
        reason: "control token required",
        registration_status: "not_registered",
        configured: false,
        config_path: "/tmp/mcp_servers.json",
        config_exists: false,
        servers: [],
        tools: [],
        resources: [],
        prompts: [],
        oauth: []
      };

  return {
    object: "aiask.desktop_capabilities",
    summary: {
      source: "mock_fixture",
      status: "in_progress",
      counts: { implemented: 74, live_unverified: 2, unconfigured: 0, failed: 0, missing: 0, gated: authorized ? 0 : 1 },
      issue_count: 0,
      control: {
        authorized,
        reason: authorized ? null : "control token required",
        full_mode_enabled: true,
        control_token_configured: true,
        control_authorized: authorized,
        gated_reason: authorized ? null : "control token required"
      },
      refreshed_at: 1777467000
    },
    hermes: {
      status: {
        implementation: "aiask_native",
        baseline: "Hermes v0.16.0 full runtime capability reference",
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        full_mode_active: authorized
      },
      parity: {
        baseline: "Hermes v0.16.0 full runtime capability reference",
        baseline_version: "0.16.0",
        baseline_release_tag: "v2026.6.5",
        scope: "hermes_full_runtime",
        strict_status: "in_progress",
        status: "in_progress",
        strict_hermes_tool_count: 58,
        strict_gateway_platform_count: 22,
        missing_hermes_tools: [],
        missing_gateway_platforms: [],
        missing_features: [],
        code_status: "present",
        core_code_status: "present",
        mock_status: "passed",
        live_status: "live_unverified",
        v014_delta: {
          baseline: "Hermes v0.14.0 full runtime capability reference",
          release_tag: "v2026.5.16",
          total: 18,
          implemented_count: 11,
          partial_count: 5,
          missing_count: 0,
          excluded_by_design_count: 2,
          missing: [],
          partial: [
            { hermes_tool: "video_generate", area: "multimodal", status: "live_unverified", aiask_tools: ["agent_video_generate"], required_env: ["AIASK_VIDEO_API_URL", "AIASK_VIDEO_API_KEY"] },
            { hermes_tool: "x_search", area: "web", status: "live_unverified", aiask_tools: ["agent_x_search"], required_env: ["X_BEARER_TOKEN|X_API_KEY"] }
          ],
          implemented: [
            { hermes_tool: "computer_use", area: "computer_use", status: "implemented", aiask_tools: ["agent_computer_use"] },
            { platform: "line", area: "platform", status: "implemented", aiask_adapter: "line" },
            { platform: "simplex", area: "platform", status: "implemented", aiask_adapter: "simplex" },
            { platform: "teams", area: "platform", status: "implemented", aiask_adapter: "teams" }
          ],
          excluded_by_design: [
            { feature: "openai_compatible_local_proxy", area: "models", status: "excluded_by_design", aiask_tools: ["agent_model_manage"] },
            { feature: "oauth_subscription_providers", area: "models", status: "excluded_by_design", aiask_tools: ["agent_model_manage"] }
          ]
        },
        v016_delta: {
          baseline: "Hermes v0.16.0 Surface Release capability reference",
          release_tag: "v2026.6.5",
          total: 19,
          implemented_count: 3,
          partial_count: 16,
          missing_count: 0,
          excluded_by_design_count: 0,
          missing: [],
          partial: [
            { feature: "model_picker_profiles_and_fallback", area: "models", status: "partial", aiask_tools: ["agent_model_manage"] },
            { feature: "undo_last_turns", area: "session", status: "partial", aiask_tools: ["agent_tui_status"] },
            { feature: "checkpoint_and_rollback", area: "file", status: "partial", aiask_tools: ["agent_file_patch"] }
          ],
          implemented: [
            { feature: "desktop_native_shell", area: "desktop", status: "implemented", aiask_tools: ["agent_tool_catalog"] }
          ]
        }
      },
      readiness: {
        object: "aiask.hermes_readiness",
        embedded_vendor_runtime: false,
        parity_baseline: "Hermes v0.16.0 full runtime capability reference",
        baseline_version: "0.16.0",
        baseline_release_tag: "v2026.6.5",
        missing_features: [],
        live_evidence: {
          object: "aiask.hermes_live_evidence",
          baseline_version: "0.16.0",
          baseline_release_tag: "v2026.6.5",
          code_status: "present",
          core_code_status: "present",
          mock_status: "passed",
          live_status: "live_unverified",
          strict_status: "in_progress",
          live_unverified_count: 27,
          required_env_names: ["OPENAI_API_KEY", "TINKER_API_KEY", "WANDB_API_KEY"],
          required_env_groups: ["OPENAI_API_KEY", "TINKER_API_KEY", "WANDB_API_KEY"],
          items: []
        }
      },
      tool_mapping: tools,
      platform_mapping: platforms,
      feature_mapping: features,
      issues: []
    },
    mcp,
    strategy_factory: {
      status: factoryEnvelope(factoryMode, "status"),
      runs: factoryEnvelope(factoryMode, "runs"),
      review_snapshot: factoryEnvelope(factoryMode, "review")
    },
    skills: authorized ? { root: "/tmp/aiask-skills", skills: [{ name: "risk-review", description: "Risk review", active: true }] } : { gated: true },
    plugins: authorized
      ? [
          {
            name: "audit-plugin",
            enabled: true,
            source: "local",
            version: "0.1.0",
            description: "Mock audit plugin",
            tools: [{ name: "audit_echo" }],
            commands: [],
            hooks: []
          }
        ]
      : { gated: true },
    skill_packs: { object: "aiask.skill_packs", status: "ready", available_count: 1, packs: [{ name: "quant-operator", installed: true }] },
    ai: aiStatus(),
    raw_refs: {
      parity: "/v1/capabilities/parity",
      readiness: "/v1/hermes/readiness",
      mcp_servers: "/v1/mcp/servers",
      skills: "/v1/skills",
      ai_status: "/v1/ai/status"
    }
  };
}

function aiStatus() {
  return {
    object: "aiask.ai_status",
    provider: "openai",
    model: "gpt-5.4",
    base_url_configured: true,
    base_url: "http://localhost:8317/v1",
    api_key_configured: true,
    mock: false,
    configured: true,
    runtime_client: "OpenAIChatClient",
    secrets_redacted: true
  };
}

const aiProviderPresets = [
  { id: "openai", label: "OpenAI", provider: "openai", provider_type: "openai", base_url: "https://api.openai.com/v1", default_model: "gpt-4.1-mini", model_list_supported: true },
  { id: "deepseek", label: "DeepSeek", provider: "openai", provider_type: "openai_compatible", base_url: "https://api.deepseek.com", default_model: "deepseek-chat", model_list_supported: true },
  { id: "dashscope-qwen-cn", label: "通义千问 / DashScope 北京", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "dashscope-qwen-intl", label: "Qwen / DashScope 美国弗吉尼亚", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope-us.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "anthropic", label: "Anthropic Claude", provider: "anthropic", provider_type: "anthropic_messages", base_url: "https://api.anthropic.com/v1", default_model: "claude-sonnet-4-5", model_list_supported: true },
  { id: "custom-openai-compatible", label: "自定义 OpenAI 兼容", provider: "openai", provider_type: "openai_compatible", base_url: "", default_model: "", model_list_supported: true },
  { id: "mock", label: "本地 Mock", provider: "mock", provider_type: "mock", base_url: "", default_model: "mock-local", model_list_supported: false }
];

function aiConfigPayload() {
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
      secrets_redacted: true
    },
    editable: {
      provider_env: "AIASK_AGENT_MODEL_PROVIDER",
      model_env: "AIASK_AGENT_MODEL",
      base_url_env: "OPENAI_BASE_URL",
      api_key_env: "OPENAI_API_KEY",
      env_file: "/tmp/aiask/.env",
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

function localProfilePayload(overrides: Record<string, unknown> = {}) {
  return {
    object: "aiask.desktop.local_profile",
    user_id: "local-e2e",
    profile_name: "E2E 本地操作者",
    storage: "sqlite",
    path: "/tmp/aiask-agent-state.sqlite3",
    updated_at: "2026-05-21T08:00:00.000Z",
    status: "ready",
    secrets_redacted: true,
    ...overrides
  };
}

function settingsStatusPayload(authorized: boolean) {
  return {
    object: "aiask.desktop_settings_status",
    agent: {
      endpoint: API_ORIGIN,
      toolset: "finance_safe",
      model: "gpt-5.4",
      max_iterations: 12,
      api_token_configured: false,
      control_token_configured: true,
      control_authorized: authorized,
      control_reason: authorized ? null : "control token required"
    },
    llm: {
      ai_status: aiStatus(),
      providers: {
        object: "aiask.model_providers",
        status: "ready",
        configured_count: 2,
        providers: [
          { name: "openai", type: "openai_compatible", model: "gpt-5.4", status: "ready", configured: true },
          { name: "fallback", type: "openai_compatible", model: "gpt-5.2", status: "ready", configured: true }
        ]
      }
    },
    memory: {
      object: "aiask.memory_status",
      status: "ready",
      sqlite_path: "/tmp/aiask-agent-state.sqlite3",
      response_count: 4,
      session_count: 2,
      secrets_redacted: true
    },
    databases: {
      agent_state: { backend: "sqlite", path: "/tmp/aiask-agent-state.sqlite3", configured: true, writable: true },
      intent_state: { backend: "sqlite", path: "/tmp/aiask-intents.sqlite3", configured: true, writable: true },
      quant_research: { backend: "sqlite", path: "/tmp/aiask-quant.sqlite3", configured: true, writable: true },
      akshare: { backend: "sqlite", path: "/tmp/akshare_mcp.sqlite3", configured: true, writable: true }
    },
    profile: localProfilePayload(),
    secrets_redacted: true
  };
}

function quantPresetsPayload() {
  return {
    object: "aiask.quant_presets",
    data_status: {
      status: "unconfigured",
      database: {
        backend: "sqlite",
        path: "/tmp/akshare_mcp.sqlite3",
        configured: true,
        writable: false,
        sources: ["default"],
        required_for_full_quant: true,
        setup_hint: "Configure a writable SQLite database path to enable full quant research."
      }
    },
    templates: [
      {
        id: "balanced_factor_research",
        label: "Balanced factor research",
        universe: ["600519", "000001"],
        benchmark: "000300",
        factors: ["momentum"],
        rebalance_frequency: "monthly",
        cost_bps: 3,
        slippage_bps: 1,
        risk_limits: { max_weight: 0.35, var_limit: 0.08 }
      }
    ],
    factor_library: ["momentum", "volatility", "value"],
    risk_defaults: { lookback_days: 252, max_weight: 0.35 },
    disclaimer: "NOT_INVESTMENT_ADVICE: This research artifact is decision support only and is not a trading instruction."
  };
}

function desktopDataStatusPayload(codes = ["600519", "000001", "000858"], maxStaleDays = 5) {
  return {
    object: "aiask.desktop_data_status",
    status: "partial",
    database: {
      backend: "sqlite",
      path: "/tmp/akshare_mcp.sqlite3",
      configured: true,
      writable: true,
      sources: ["akshare_fixture", "tdx_fixture"],
      setup_hint: "E2E mock database is writable."
    },
    presets: quantPresetsPayload(),
    quality_gate: {
      success: false,
      data: {
        status: "partial",
        checked: codes,
        missing: ["000858"],
        stale: ["000001"],
        max_stale_days: maxStaleDays
      },
      error: null,
      error_code: null
    },
    data_validation: { status: "partial", row_count: 1888 },
    freshness: {
      "600519": { status: "fresh", last_date: "2026-05-20" },
      "000001": { status: "stale", last_date: "2026-05-10" },
      "000858": { status: "missing", last_date: null }
    },
    codes,
    max_stale_days: maxStaleDays,
    missing_count: 1,
    stale_count: 1,
    secrets_redacted: true
  };
}

const stockDataSourcePresets = [
  {
    provider: "akshare",
    label: "AKShare / AKTools",
    markets: ["CN", "HK", "US"],
    categories: ["quote", "kline", "fundamental"],
    auth_type: "none",
    default_base_url: "",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds"],
    documentation_url: "https://akshare.akfamily.xyz/introduction.html",
    note: "Open data source for local market data checks."
  },
  {
    provider: "tushare",
    label: "Tushare Pro",
    markets: ["CN"],
    categories: ["quote", "kline", "fundamental"],
    auth_type: "token",
    default_base_url: "http://api.tushare.pro",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "timeout_seconds", "rate_limit_per_minute"],
    documentation_url: "https://tushare.pro/document/1?doc_id=40",
    note: "Token based China market data source."
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
    documentation_url: null,
    note: "Read-only quote host or local vipdoc source."
  },
  {
    provider: "duckduckgo",
    label: "DuckDuckGo HTML Search",
    markets: ["Global"],
    categories: ["web_search", "research"],
    auth_type: "none",
    default_base_url: "https://duckduckgo.com/html/",
    required_fields: [],
    optional_fields: ["base_url", "timeout_seconds"],
    documentation_url: "https://duckduckgo.com/",
    note: "No-key web search fallback."
  },
  {
    provider: "tavily",
    label: "Tavily Search",
    markets: ["Global"],
    categories: ["web_search", "deep_research"],
    auth_type: "bearer",
    default_base_url: "https://api.tavily.com",
    required_fields: ["api_key"],
    optional_fields: ["base_url", "search_depth"],
    documentation_url: "https://docs.tavily.com/documentation/api-reference/endpoint/search",
    note: "Deep web search API."
  }
];

function redactStockDataSource(source: Record<string, unknown>): Record<string, unknown> {
  return {
    ...source,
    api_key: source.api_key ? "[redacted]" : "",
    password: source.password ? "[redacted]" : "",
    token: source.token ? "[redacted]" : "",
    api_key_configured: Boolean(source.api_key || source.token || source.password),
    configured: source.configured ?? true,
    status: source.enabled === false ? "disabled" : source.status || "ready",
    secrets_redacted: true
  };
}

function mergeStockDataSourceDraft(base: Record<string, unknown> | undefined, draft: Record<string, unknown>): Record<string, unknown> {
  const merged = { ...(base || {}) };
  for (const [key, value] of Object.entries(draft)) {
    const lowered = key.toLowerCase();
    const secretField = lowered.includes("api_key") || lowered.includes("token") || lowered.includes("secret") || lowered.includes("password");
    if (secretField && (value === null || value === "" || value === undefined) && base) continue;
    merged[key] = value;
  }
  return merged;
}

function stockDataSourcesPayload(sources: Array<Record<string, unknown>>) {
  const redactedSources = sources.map(redactStockDataSource);
  return {
    object: "aiask.stock_data_sources",
    status: "ready",
    configured_count: redactedSources.filter((source) => source.configured !== false).length,
    ready_count: redactedSources.filter((source) => source.status === "ready").length,
    presets: stockDataSourcePresets,
    sources: redactedSources,
    config_path: "/tmp/aiask-stock-data-sources.json",
    config_source: { source: "e2e_fixture", loaded: true },
    secrets_redacted: true
  };
}

function dataSyncPlanPayload(body: Record<string, unknown> = {}) {
  const codes = Array.isArray(body.codes) ? body.codes.map(String) : ["600519", "000001", "000858"];
  const maxStaleDays = Number(body.max_stale_days || 5);
  const taskType = String(body.task_type || "kline");
  const period = String(body.period || "daily");
  return {
    object: "aiask.desktop_data_sync_plan",
    status: "ready",
    data_status: desktopDataStatusPayload(codes, maxStaleDays),
    intent_request: {
      action: "data_sync.run_once",
      params: { codes, max_stale_days: maxStaleDays, task_type: taskType, period },
      rationale: "E2E mock sync plan approval."
    },
    commands: [{ command: "sync", task_type: taskType, period, codes }],
    side_effect: { level: "stateful", confirmation_required: true },
    secrets_redacted: true
  };
}

function stockRadarStatusPayload() {
  return {
    status: "ready",
    counts: { alert: 1, watch: 1, observe: 0, reject: 0 },
    degraded_flags: [],
    latest_run: {
      run_id: "radar_e2e_20260608",
      status: "completed",
      started_at: "2026-06-08T14:30:00+08:00",
      finished_at: "2026-06-08T14:31:00+08:00"
    },
    digest_preview: "企微 / Telegram 预览：北方稀土、工业富联进入观察池，不含交易指令。"
  };
}

function stockRadarCandidatesPayload(tier = "") {
  const candidates = [
    {
      candidate_id: "radar_candidate_e2e_001",
      run_id: "radar_e2e_20260608",
      symbol: "600111",
      stock_name: "北方稀土",
      tier: "alert",
      radar_score: 84.5,
      event_id: "radar_event_e2e_001",
      event_type: "policy_shock",
      direction: "bullish",
      summary: "稀土出口管制事件触发观察池候选，证据链来自政策新闻与主题暴露。",
      source_doc_uids: ["doc_radar_policy_001", "doc_radar_theme_002"],
      source_chain: [{ uid: "doc_radar_policy_001", kind: "news", title: "稀土出口管制" }],
      extraction: { confidence: 0.82, event_type: "policy_shock" },
      confirmations: { cross_source: true, theme_exposure: "critical_minerals" },
      risk_flags: []
    },
    {
      candidate_id: "radar_candidate_e2e_002",
      run_id: "radar_e2e_20260608",
      symbol: "601138",
      stock_name: "工业富联",
      tier: "watch",
      radar_score: 66.0,
      event_id: "radar_event_e2e_002",
      event_type: "supply_chain",
      direction: "neutral",
      summary: "供应链文本触发观察级候选，仍需更多确认。",
      source_doc_uids: ["doc_radar_supply_001"],
      source_chain: [{ uid: "doc_radar_supply_001", kind: "filing", title: "供应链观察" }],
      extraction: { confidence: 0.64, event_type: "supply_chain" },
      confirmations: { cross_source: false },
      risk_flags: ["needs_confirmation"]
    }
  ];
  const filtered = tier ? candidates.filter((candidate) => candidate.tier === tier) : candidates;
  return { status: "ready", candidates: filtered, count: filtered.length };
}

function stockRadarDigestPayload() {
  return {
    status: "ready",
    digest_preview: "企微 / Telegram 预览：北方稀土进入警报观察，工业富联进入观察列表。仅为观察池信息，不含买卖指令。",
    channels: ["wecom", "telegram"],
    push_logs: [{ push_id: "radar_push_e2e", channel: "preview", status: "preview", candidate_count: 2 }]
  };
}

function marketTemperatureSnapshotPayload(body: Record<string, unknown> = {}) {
  const asOf = String(body.as_of || "2026-06-08");
  const industries = [
    {
      code: "801750",
      name: "计算机",
      stock_count: 48,
      ma20_breadth: 0.7708,
      advance_count: 34,
      decline_count: 11,
      amount: 428.35,
      market_cap_weight: 0.118,
      temperature: 74.42,
      state: "warm"
    },
    {
      code: "801080",
      name: "电子",
      stock_count: 62,
      ma20_breadth: 0.738,
      advance_count: 41,
      decline_count: 18,
      amount: 512.9,
      market_cap_weight: 0.146,
      temperature: 71.84,
      state: "warm"
    },
    {
      code: "801780",
      name: "银行",
      stock_count: 34,
      ma20_breadth: 0.5294,
      advance_count: 17,
      decline_count: 15,
      amount: 216.72,
      market_cap_weight: 0.201,
      temperature: 53.27,
      state: "neutral"
    },
    {
      code: "801730",
      name: "电力设备",
      stock_count: 55,
      ma20_breadth: 0.25,
      advance_count: 15,
      decline_count: 37,
      amount: 276.54,
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
      ma20_breadth: 0.5473,
      advance_count: 151,
      decline_count: 136,
      flat_count: 13,
      advance_ratio: 0.5033,
      avg_pct_change: 0.12,
      weighted_pct_change: 0.18,
      temperature: 55.84,
      state: "neutral"
    },
    industries,
    hot_industries: industries.slice(0, 3),
    cold_industries: industries.slice().reverse(),
    quality: {
      status: "healthy",
      warnings: [],
      trend_coverage: 0.9867,
      loaded_stock_rows: 300,
      missing_kline_rows: 0,
      industry_count: industries.length
    },
    source_chain: ["desktop.e2e", "market_temperature.fixture"]
  };
}

function marketTemperatureCacheReadinessPayload(body: Record<string, unknown> = {}) {
  return {
    ready: true,
    status: "fresh",
    read_only: true,
    as_of: String(body.as_of || "2026-06-08"),
    max_stale_days: 1,
    staleness_days: 1,
    quality_status: "healthy",
    degraded: false,
    warnings: [],
    blockers: [],
    cache: { updated_at: "2026-06-08T15:05:00Z", source: "market_temperature_snapshots" },
    source_chain: ["desktop.e2e", "cache_readiness"]
  };
}

function marketTemperatureCacheHistoryPayload() {
  return {
    items: [
      { as_of: "2026-06-08", market_temperature: 55.84, market_state: "neutral", stock_count: 300, industry_count: 4, quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" },
      { as_of: "2026-06-07", market_temperature: 47.2, market_state: "neutral", stock_count: 298, industry_count: 4, quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-06", market_temperature: 32.4, market_state: "cool", stock_count: 294, industry_count: 4, quality_status: "degraded", warnings: ["partial data"], updated_at: "2026-06-06T15:03:00Z" }
    ],
    count: 3,
    limit: 10,
    include_snapshot: false,
    source_chain: ["desktop.e2e", "cache_history"]
  };
}

function marketTemperatureIndustryHistoryPayload() {
  return {
    items: [
      { as_of: "2026-06-07", code: "801750", name: "计算机", temperature: 71.4, state: "warm", ma20_breadth: 0.771, advance_count: 34, decline_count: 11, stock_count: 48, market_temperature: 47.2, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-07", code: "801780", name: "银行", temperature: 50.3, state: "neutral", ma20_breadth: 0.529, advance_count: 17, decline_count: 15, stock_count: 34, market_temperature: 47.2, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-07T15:04:00Z" },
      { as_of: "2026-06-08", code: "801750", name: "计算机", temperature: 74.4, state: "warm", ma20_breadth: 0.771, advance_count: 34, decline_count: 11, stock_count: 48, market_temperature: 55.8, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" },
      { as_of: "2026-06-08", code: "801780", name: "银行", temperature: 53.3, state: "neutral", ma20_breadth: 0.529, advance_count: 17, decline_count: 15, stock_count: 34, market_temperature: 55.8, market_state: "neutral", quality_status: "healthy", warnings: [], updated_at: "2026-06-08T15:05:00Z" }
    ],
    count: 4,
    limit: 10,
    top_n: 3,
    include_source_chain: false,
    source_chain: ["desktop.e2e", "industry_history"]
  };
}

function marketTemperatureIndustryConstituentsPayload(body: Record<string, unknown> = {}) {
  const industry = String(body.industry || "计算机");
  return {
    items: [
      { code: "300001", name: "计算机 Leader", industry, sector: industry, market: "SZ", market_cap: 1820.5, pe_ratio: 24.1, pb_ratio: 3.2, list_date: "2010-01-08" },
      { code: "600001", name: "计算机 Growth", industry, sector: industry, market: "SH", market_cap: 1302.4, pe_ratio: 19.7, pb_ratio: 2.8, list_date: "2008-04-21" }
    ],
    count: 2,
    total_matches: 2,
    limit: 8,
    offset: 0,
    industry,
    match_mode: "contains",
    include_source_chain: false,
    source_chain: ["desktop.e2e", "industry_constituents"]
  };
}

function marketTemperatureForwardValidationPayload() {
  return {
    matrix: {
      warm: {
        "1d": { sample_n: 18, direction_hits: 12, reliable: true, avg_forward_return: 0.42, hit_rate: 0.667 },
        "3d": { sample_n: 16, direction_hits: 10, reliable: true, avg_forward_return: 0.76, hit_rate: 0.625 }
      },
      neutral: {
        "1d": { sample_n: 24, direction_hits: 15, reliable: true, avg_forward_return: 0.06, hit_rate: 0.625 },
        "3d": { sample_n: 22, direction_hits: 12, reliable: true, avg_forward_return: 0.18, hit_rate: 0.545 }
      },
      cool: {
        "1d": { sample_n: 14, direction_hits: 8, reliable: true, avg_forward_return: -0.31, hit_rate: 0.571 },
        "3d": { sample_n: 12, direction_hits: 8, reliable: true, avg_forward_return: -0.64, hit_rate: 0.667 }
      }
    },
    states: ["warm", "neutral", "cool"],
    horizons: [1, 3, 5],
    count: 56,
    snapshot_count: 30,
    limit: 120,
    target_field: "benchmark_return",
    requested_target_field: "benchmark_return",
    benchmark_code: "000300",
    benchmark_status: "available",
    benchmark_bar_count: 76,
    min_samples: 3,
    include_samples: false,
    samples: [],
    source_chain: ["desktop.e2e", "forward_validation"]
  };
}

function factoryEventListPayload() {
  return {
    events: [
      {
        event_id: "evt_e2e_001",
        event_name: "稀土出口管制(e2e)",
        event_type: "policy_shock",
        event_source: "manual",
        status: "active",
        direction: "bullish",
        intensity: 0.85,
        confidence: 0.7,
        primary_themes: ["critical_minerals"],
        operator_id: "operator_e2e",
        approver_id: "approver_e2e",
        created_at: "2026-06-08T14:20:00+08:00"
      }
    ],
    count: 1
  };
}

function factoryEventPreviewTasksPayload(eventId = "evt_e2e_001") {
  return {
    event_id: eventId,
    impacts: [{ theme_code: "critical_minerals", depth: 0, magnitude: 0.85 }],
    candidate_symbols: ["600111", "600259"],
    target_count: 2,
    warnings: [],
    preview_mode: "real_bfs"
  };
}

function factoryEventLineagePayload(eventId = "evt_e2e_001") {
  return {
    lineage: [
      {
        lineage_id: 1,
        event_id: eventId,
        event_name: "稀土出口管制(e2e)",
        event_status: "active",
        task_id: "event_evt_e2e_001_critical_minerals",
        theme_code: "critical_minerals",
        impact_direction: "positive",
        impact_magnitude: 0.85,
        target_symbols: ["600111", "600259"],
        target_count: 2,
        breadth_resolved: "narrow",
        generated_at: "2026-06-08T14:22:00+08:00",
        gate_1_passed: 1,
        strategies_submitted: 1
      }
    ],
    count: 1
  };
}

function quantResearchRunPayload() {
  return {
    success: true,
    data: {
      research: {
        research_id: "research_e2e_quant_1",
        status: "blocked",
        payload: {
          stages: [
            { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum"] }, error: null },
            { name: "data_gate", status: "blocked", output: { status: "unconfigured", blocking_reason: "LOCAL_DATABASE_REQUIRED" }, error: "LOCAL_DATABASE_REQUIRED" }
          ]
        },
        report: {
          object: "aiask.quant_research_report",
          research_id: "research_e2e_quant_1",
          status: "blocked",
          summary: {
            benchmark: "000300",
            universe_size: 2,
            factor_count: 1,
            failed_stage: "data_gate"
          },
          universe: ["600519", "000001"],
          backtest_assumptions: {
            cost_bps: 3,
            slippage_bps: 1,
            rebalance_frequency: "monthly"
          },
          strategy_factory: null,
          disclaimer: "NOT_INVESTMENT_ADVICE: This research artifact is decision support only and is not a trading instruction.",
          stages: [
            { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum"] }, error: null },
            { name: "data_gate", status: "blocked", output: { status: "unconfigured", blocking_reason: "LOCAL_DATABASE_REQUIRED" }, error: "LOCAL_DATABASE_REQUIRED" }
          ],
          limitations: ["Full quant mode requires a writable SQLite database."]
        }
      }
    },
    error: null
  };
}

function factorFactoryStatusPayload() {
  return {
    object: "aiask.desktop.factor_factory_status",
    status: "ready",
    configured: true,
    factory: {
      initialized: true,
      pool_loaded_from_db: true,
      pool_size: 3,
      run_count: 7,
      last_run_id: "factor_run_e2e_1"
    },
    active_factors: [
      { factor_id: "factor_momentum_20d", name: "20d momentum", family: "momentum", quality_score: 0.73, status: "promoted" },
      { factor_id: "factor_value_cashflow", name: "cashflow value", family: "value", quality_score: 0.61, status: "candidate" }
    ],
    engine_health: {
      llm_primary: { status: "ready" },
      gp_classic: { status: "ready" },
      rule_seed: { status: "ready" }
    },
    pool_health: {
      active_promoted_count: 1,
      quarantine_count: 0
    },
    secrets_redacted: true
  };
}

function jobsPayload() {
  return {
    object: "list",
    data: [
      {
        job_id: "job_e2e_research",
        name: "每日研究监控",
        prompt: "复盘最新市场数据，并总结需要关注的风险提醒。",
        schedule: "*/30 * * * *",
        toolset: "finance_safe",
        enabled: true,
        last_run_at: "2026-05-21T07:30:00.000Z",
        last_result: { status: "completed", run_id: "run_job_e2e" }
      }
    ]
  };
}

function intentEnvelope(action = "factory_run_once") {
  return {
    success: true,
    data: {
      intent: {
        intent_id: "intent_e2e_approved_path",
        action,
        target_tool: "agent_action_intent_create",
        target_action: action,
        status: "awaiting_confirmation",
        params: { source: "desktop_e2e" },
        created_at: "2026-05-21T08:00:00.000Z",
        updated_at: "2026-05-21T08:00:00.000Z"
      }
    },
    error: null,
    error_code: null
  };
}

function incubationStatusEnvelope() {
  return {
    success: true,
    data: {
      run_time: "nightly",
      dry_run: true,
      run_count: 12,
      error_count: 0,
      last_run_at: "2026-05-21T07:00:00.000Z",
      last_result_status: "completed",
      report: {
        report_date: "2026-05-21",
        summary: {
          total_incubating: 6,
          total_with_signals: 4,
          auto_promoted: 1,
          stage_counts: { warmup: 2, observe: 2, candidate: 1, promoted: 1 }
        },
        hit_rate_dashboard: {
          overall: {
            total_signals: 18,
            hit_count: 11,
            hit_rate: 0.61,
            avg_skill_lcb: 0.022,
            avg_forward_sharpe: 1.17,
            strategy_count: 6
          },
          by_family: {
            momentum: { hit_rate: 0.65, total_n: 10, avg_skill_lcb: 0.031, avg_forward_sharpe: 1.2, strategy_count: 3 },
            value: { hit_rate: 0.55, total_n: 8, avg_skill_lcb: 0.011, avg_forward_sharpe: 0.8, strategy_count: 2 }
          },
          trend: { available: true, improvement: 0.04, direction: "improving" }
        },
        feedback_actions: {
          families_to_boost: ["momentum"],
          families_to_cooldown: ["low_liquidity"],
          families_to_freeze: []
        }
      }
    },
    error: null,
    error_code: null
  };
}

function strategyEventsEnvelope(eventType?: string | null) {
  const reportEvent = {
    id: "event_hit_rate_report",
    event_type: "incubation_factory.hit_rate_report_generated",
    severity: "info",
    created_at: "2026-05-21T07:00:00.000Z",
    payload: incubationStatusEnvelope().data.report
  };
  const stageEvent = {
    id: "event_stage_promoted",
    event_type: "incubation.stage_transitioned",
    severity: "info",
    created_at: "2026-05-21T07:10:00.000Z",
    strategy_id: "strategy_e2e_momentum",
    payload: {
      strategy_id: "strategy_e2e_momentum",
      strategy_name: "E2E momentum strategy",
      from_stage: "candidate",
      to_stage: "promoted",
      reason: "mock forward verification passed"
    }
  };
  const factoryEvent = {
    id: "event_factory_run_completed",
    event_type: "factory.run_completed",
    severity: "info",
    created_at: "2026-05-21T07:20:00.000Z",
    strategy_id: "strategy_e2e_factory",
    payload: { decision: "review", message: "mock factory cycle completed" }
  };
  const events = [reportEvent, stageEvent, factoryEvent].filter((event) => !eventType || event.event_type === eventType);
  return { success: true, data: { events }, error: null, error_code: null };
}

type TradePredictionOutcomeFixture = {
  outcome_id: string;
  prediction_id: string;
  strategy_id: string;
  stock_code: string;
  actual_trading_date: string;
  score_version: string;
  score_status: string;
  data_quality_status: string;
  trade_prediction_score: number;
  outcome_json: Record<string, unknown>;
  metadata: Record<string, unknown>;
  calculated_at: string;
};

const tradePredictionOutcomesFixture: TradePredictionOutcomeFixture[] = [
  {
    outcome_id: "tpo_e2e_001",
    prediction_id: "tp_e2e_001",
    strategy_id: "strategy_e2e_momentum",
    stock_code: "600519",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "ok",
    data_quality_status: "ok",
    trade_prediction_score: 0.82,
    outcome_json: { direction_hit: true, target_touch: true, planned_trade_return: 0.034 },
    metadata: { family: "momentum", stage: "candidate", regime: "bull", event: "policy_shock", factor: "momentum_20d" },
    calculated_at: "2026-06-04T07:15:00Z"
  },
  {
    outcome_id: "tpo_e2e_002",
    prediction_id: "tp_e2e_002",
    strategy_id: "strategy_e2e_reversal",
    stock_code: "000001",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "partial_intraday_missing",
    data_quality_status: "intraday_missing",
    trade_prediction_score: 0.51,
    outcome_json: { direction_hit: true, target_touch: false, planned_trade_return: 0.008 },
    metadata: { family: "mean_reversion", stage: "observe", regime: "range", event: "earnings", factor: "reversal_5d" },
    calculated_at: "2026-06-04T07:20:00Z"
  },
  {
    outcome_id: "tpo_e2e_003",
    prediction_id: "tp_e2e_003",
    strategy_id: "strategy_e2e_event",
    stock_code: "300750",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_v2",
    score_status: "insufficient_samples",
    data_quality_status: "partial_gap",
    trade_prediction_score: 0.38,
    outcome_json: { direction_hit: false, target_touch: false, planned_trade_return: -0.012 },
    metadata: { family: "event_driven", stage: "candidate", regime: "volatile", event: "policy_shock", factor: "event_strength" },
    calculated_at: "2026-06-03T07:18:00Z"
  }
];

function queryRecord(query: URLSearchParams): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  query.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

function safeLimit(value: unknown, fallback = 100): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(Math.trunc(parsed), 1000)) : fallback;
}

function matchesTradePredictionFilter(item: TradePredictionOutcomeFixture, filters: Record<string, unknown>, key: keyof TradePredictionOutcomeFixture): boolean {
  const value = filters[key];
  if (value === undefined || value === null || value === "") return true;
  return String(item[key] || "") === String(value);
}

function tradePredictionOutcomeItems(filters: Record<string, unknown> = {}) {
  const limit = safeLimit(filters.limit, 100);
  return tradePredictionOutcomesFixture
    .filter((item) =>
      (["prediction_id", "strategy_id", "stock_code", "score_version", "score_status", "data_quality_status"] as const).every((key) =>
        matchesTradePredictionFilter(item, filters, key)
      )
    )
    .slice(0, limit);
}

function countBy<T>(items: T[], valueFor: (item: T) => string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const value = valueFor(item);
    counts[value] = (counts[value] || 0) + 1;
  }
  return counts;
}

function tradePredictionStatus(filters: Record<string, unknown> = {}) {
  const outcomes = tradePredictionOutcomeItems(filters);
  const scores = outcomes.map((outcome) => outcome.trade_prediction_score).filter((score) => Number.isFinite(score));
  const partialCount = outcomes.filter((outcome) => outcome.score_status !== "ok").length;
  const scoreDistribution = countBy(outcomes, (outcome) =>
    outcome.trade_prediction_score >= 0.8
      ? "0.80-1.00"
      : outcome.trade_prediction_score >= 0.6
        ? "0.60-0.79"
        : outcome.trade_prediction_score >= 0.4
          ? "0.40-0.59"
          : "0.00-0.39"
  );
  return {
    object: "trade_prediction.status",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    prediction_count: outcomes.length + 1,
    outcome_count: outcomes.length,
    sample_n: outcomes.length,
    pending_count: 1,
    evaluated_count: outcomes.length,
    partial_count: partialCount,
    prediction_status_counts: { frozen: outcomes.length, pending: 1 },
    score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
    latest_score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
    score_version_counts: countBy(outcomes, (outcome) => outcome.score_version),
    data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status),
    latest_data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status),
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
  const dimensions = String(filters.dimensions || "family,stage,regime,event,factor")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const rows = dimensions.flatMap((dimension) => {
    const grouped = new Map<string, TradePredictionOutcomeFixture[]>();
    for (const outcome of tradePredictionOutcomeItems(filters)) {
      const value = String(outcome.metadata[dimension] || "unknown");
      grouped.set(value, [...(grouped.get(value) || []), outcome]);
    }
    return Array.from(grouped.entries()).map(([value, outcomes]) => {
      const sampleN = outcomes.length;
      const scoreAvg = outcomes.reduce((sum, outcome) => sum + outcome.trade_prediction_score, 0) / sampleN;
      const scoreLcb = Math.max(0, scoreAvg - 1.96 * Math.sqrt((scoreAvg * (1 - scoreAvg)) / sampleN));
      return {
        dimension,
        value,
        sample_n: sampleN,
        score_avg: Number(scoreAvg.toFixed(6)),
        score_lcb_95: Number(scoreLcb.toFixed(6)),
        direction_hit_rate: Number((outcomes.filter((outcome) => outcome.outcome_json.direction_hit).length / sampleN).toFixed(6)),
        target_touch_rate: Number((outcomes.filter((outcome) => outcome.outcome_json.target_touch).length / sampleN).toFixed(6)),
        score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
        data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status)
      };
    });
  });
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

function tradePredictionEnvelope(data: unknown) {
  return { success: true, data, error: null, error_code: null };
}

function connectorsSummaryPayload() {
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

function connectorFixtureList() {
  const summary = connectorsSummaryPayload().data as { connectors: Array<Record<string, unknown>> };
  return summary.connectors;
}

function connectorFixture(type: string, name: string) {
  return connectorFixtureList().find((connector) => {
    const connectorType = String(connector.type || "");
    const connectorId = String(connector.id || "");
    const connectorName = String(connector.name || "");
    return connectorType === type && (connectorId === name || connectorName === name);
  });
}

function workbenchSummaryPayload() {
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

function financialManagerCatalogPayload() {
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

const brokerProfileFixture = {
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

const brokerAccountsFixture = [
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

const brokerPositionsFixture = [
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

const brokerOrdersFixture = [
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

const brokerDealsFixture = [
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

function brokerAnalyticsFixture() {
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

function brokerSnapshotPayload() {
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

function brokerReadinessPayload() {
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

function financialManagerQueryPayload(body: Record<string, unknown>) {
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

function runEventsPayload() {
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

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload)
  });
}

async function setupApiMocks(page: Page, options: { factoryMode?: FactoryMode } = {}) {
  const factoryMode = options.factoryMode || "success";
  let webhookSubscriptions = [
    {
      webhook_id: "webhook_fixture",
      name: "Mock Webhook",
      events: ["MCP UI smoke test"],
      prompt: "mock",
      enabled: true,
      status: "ready"
    }
  ];
  let stockDataSources: Array<Record<string, unknown>> = [
    {
      id: "e2e:akshare",
      provider: "akshare",
      name: "E2E AKShare 本地源",
      enabled: true,
      priority: 10,
      base_url: "",
      status: "ready",
      configured: true,
      categories: ["quote", "kline", "fundamental"],
      markets: ["CN", "HK", "US"],
      timeout_seconds: 8,
      notes: "E2E default source"
    },
    {
      id: "e2e:tushare",
      provider: "tushare",
      name: "Tushare 主账号",
      enabled: true,
      priority: 20,
      base_url: "http://api.tushare.pro",
      api_key: "mock-stock-token",
      status: "ready",
      configured: true,
      categories: ["quote", "kline", "fundamental"],
      markets: ["CN"],
      symbol: "600519",
      timeout_seconds: 8
    },
    {
      id: "e2e:duckduckgo",
      provider: "duckduckgo",
      name: "DuckDuckGo fallback",
      enabled: true,
      priority: 50,
      base_url: "https://duckduckgo.com/html/",
      status: "ready",
      configured: true,
      categories: ["web_search", "research"],
      markets: ["Global"]
    }
  ];
  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const authorized = request.headers().authorization === `Bearer ${CONTROL_TOKEN}`;

    if (path === "/health/detailed") {
      return fulfillJson(route, {
        object: "aiask.health",
        status: "ok",
        service: "AIASK Agent E2E Mock",
        runtime: { model: "gpt-5.4", max_iterations: 12, model_timeout_seconds: 60, tool_timeout_seconds: 30 },
        tools: { count: 13, toolset: "finance_safe" },
        hermes: { full_mode_enabled: true, full_mode_active: authorized, parity: capabilityPayload(authorized, factoryMode).hermes.parity },
        control: { loopback_only: true, token_configured: true }
      });
    }
    if (path === "/v1/tools") {
      return fulfillJson(route, {
        object: "list",
        data: [
          { name: "agent_terminal", capability: "terminal", category: "system", status: "ready", side_effect: "read_only", description: "Mock terminal metadata" },
          { name: "agent_factory_status", capability: "factory", category: "quant", status: "ready", side_effect: "read_only", description: "Mock factory status" },
          { name: "agent_mcp_manage", capability: "mcp", category: "integration", status: "gated", side_effect: "stateful", description: "Mock MCP management" },
          { name: "agent_quant_data_gate", capability: "data", category: "quant", status: "ready", side_effect: "read_only", description: "Mock data gate" },
          { name: "agent_portfolio_risk", capability: "portfolio_risk", category: "financial_read", status: "ready", side_effect: "read_only", description: "Mock portfolio risk" },
          { name: "agent_memory_search", capability: "memory", category: "memory", status: "ready", side_effect: "read_only", description: "Mock memory search" },
          { name: "agent_action_intent_create", capability: "approval", category: "governance", status: "ready", side_effect: "stateful", description: "Mock approval intent" }
        ]
      });
    }
    if (path === "/v1/hermes/status") {
      return fulfillJson(route, {
        object: "aiask.hermes_status",
        implementation: "aiask_native",
        baseline: "Hermes v0.16.0 full runtime capability reference",
        baseline_version: "0.16.0",
        baseline_release_tag: "v2026.6.5",
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        parity: capabilityPayload(authorized, factoryMode).hermes.parity
      });
    }
    if (path === "/v1/desktop/capabilities") {
      return fulfillJson(route, capabilityPayload(authorized, factoryMode));
    }
    if (path === "/v1/desktop/workbench/summary") {
      return fulfillJson(route, workbenchSummaryPayload());
    }
    if (path === "/v1/desktop/events") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      const events = Array.isArray(body.events) ? body.events : [];
      return fulfillJson(route, {
        object: "list",
        data: events.map((event: Record<string, unknown>, index: number) => ({
          id: `event_${index + 1}`,
          recorded_at: "2026-06-12T00:00:00.000Z",
          ...event,
          payload: event.payload || {},
        })),
        count: events.length,
        secrets_redacted: true,
      });
    }
    if (path === "/v1/desktop/feedback") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        object: "aiask.feedback",
        data: {
          feedback_id: "feedback_e2e",
          user_id: body.user_id || "local-e2e",
          session_id: body.session_id || "session_fixture",
          target_type: body.target_type || "page",
          target_id: body.target_id || "workbench",
          feedback_type: body.feedback_type || "thumbs_up",
          rating: body.rating ?? 5,
          allow_learning: body.allow_learning === true,
          payload: {},
          created_at: "2026-06-12T00:00:00.000Z"
        },
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/analytics/summary") {
      const userId = url.searchParams.get("user_id");
      return fulfillJson(route, {
        object: "aiask.analytics_summary",
        scope: userId ? "user" : "aggregate",
        user_id: userId || null,
        totals: { events: 1, tool_invocations: 1, feedback: 1 },
        events_by_type: [{ event_type: "page_view", count: 1 }],
        pages: [{ page_key: "workbench", count: 1 }],
        tools: [{ tool_name: "agent_tool_catalog", count: 1, succeeded: 1, failed: 0, failure_rate: 0, avg_duration_ms: 5 }],
        feedback: [{ target_type: "page", feedback_type: "thumbs_up", count: 1, avg_rating: 5 }],
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/retention/sweep") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        object: "aiask.retention_sweep",
        dry_run: body.dry_run !== false,
        user_id: body.user_id || null,
        counts: { user_activity_events: 0, tool_invocations_payloads: 0, run_events: 0, feedback_events: 0, messages: 0 },
        tables: ["user_activity_events", "tool_invocations_payloads", "run_events", "feedback_events", "messages"],
        market_data_affected: false,
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/runs") {
      return fulfillJson(route, { object: "list", data: workbenchSummaryPayload().recent_runs });
    }
    if (path === "/v1/desktop/settings/status") {
      return fulfillJson(route, settingsStatusPayload(authorized));
    }
    const userActivityMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/activity$/);
    if (userActivityMatch) {
      const userId = decodeURIComponent(userActivityMatch[1]);
      return fulfillJson(route, {
        object: "aiask.user_activity",
        user_id: userId,
        sessions: workbenchSummaryPayload().recent_sessions,
        runs: workbenchSummaryPayload().recent_runs,
        events: [
          {
            id: "activity_page_view",
            user_id: userId,
            page_key: "workbench",
            event_type: "page_view",
            source: "desktop.e2e",
            created_at: "2026-06-12T00:00:00.000Z",
          },
        ],
        tool_invocations: [],
        feedback: [],
        policy: {
          user_id: userId,
          event_ttl_days: 30,
          audit_ttl_days: 90,
          run_event_ttl_days: 90,
          tool_payload_ttl_days: 14,
          conversation_retention: "local",
          allow_product_analytics: false,
          allow_learning: true,
          updated_at: "2026-06-12T00:00:00.000Z",
        },
        secrets_redacted: true,
      });
    }
    const userExportMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
    if (userExportMatch) {
      const userId = decodeURIComponent(userExportMatch[1]);
      return fulfillJson(route, {
        object: "aiask.user_data_export",
        user_id: userId,
        exported_at: "2026-06-12T00:00:00.000Z",
        profile_policy: {
          user_id: userId,
          event_ttl_days: 30,
          audit_ttl_days: 90,
          run_event_ttl_days: 90,
          tool_payload_ttl_days: 14,
          conversation_retention: "local",
          allow_product_analytics: false,
          allow_learning: true,
          updated_at: "2026-06-12T00:00:00.000Z"
        },
        sessions: workbenchSummaryPayload().recent_sessions,
        messages: [{ message_id: "msg_fixture", role: "assistant", content: "AIASK_OK" }],
        runs: workbenchSummaryPayload().recent_runs,
        run_events: runEventsPayload().data,
        activity_events: [{ id: "activity_page_view", user_id: userId, page_key: "workbench", event_type: "page_view", payload: {}, created_at: "2026-06-12T00:00:00.000Z" }],
        tool_invocations: [{ invocation_id: "tool_e2e", tool_name: "agent_tool_catalog", status: "succeeded", secrets_redacted: true }],
        feedback: [{ feedback_id: "feedback_e2e", target_type: "page", feedback_type: "thumbs_up", allow_learning: true }],
        sources: [],
        artifacts: [],
        analytics: {
          object: "aiask.analytics_summary",
          scope: "user",
          user_id: userId,
          totals: { events: 1, tool_invocations: 1, feedback: 1 },
          events_by_type: [{ event_type: "page_view", count: 1 }],
          pages: [{ page_key: "workbench", count: 1 }],
          tools: [{ tool_name: "agent_tool_catalog", count: 1, succeeded: 1, failed: 0, failure_rate: 0, avg_duration_ms: 5 }],
          feedback: [{ target_type: "page", feedback_type: "thumbs_up", count: 1, avg_rating: 5 }],
          secrets_redacted: true
        },
        secrets_redacted: true
      });
    }
    const userDeleteMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/delete$/);
    if (userDeleteMatch) {
      const userId = decodeURIComponent(userDeleteMatch[1]);
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        object: "aiask.user_data_delete",
        user_id: userId,
        dry_run: body.dry_run !== false,
        hard_delete: body.hard_delete === true,
        anonymized_user_id: body.hard_delete === true ? null : `deleted:${userId}`,
        counts: { sessions: 1, messages: 1, responses: 1, runs: 1, run_events: 5, activity_events: 1, tool_invocations: 1, feedback: 1, sources: 0, artifacts: 0, search_rows: 0 },
        external_side_effects: "not_rolled_back",
        secrets_redacted: true
      });
    }
    const userLearningMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/learning-dataset$/);
    if (userLearningMatch) {
      const userId = decodeURIComponent(userLearningMatch[1]);
      return fulfillJson(route, {
        object: "aiask.learning_dataset",
        user_id: userId,
        allowed: true,
        items: [{ kind: "feedback", target_type: "page", feedback_type: "thumbs_up", rating: 5, created_at: "2026-06-12T00:00:00.000Z" }],
        count: 1,
        secrets_redacted: true
      });
    }
    const userRecommendationsMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/recommendations$/);
    if (userRecommendationsMatch) {
      const userId = decodeURIComponent(userRecommendationsMatch[1]);
      return fulfillJson(route, {
        object: "aiask.workflow_recommendations",
        user_id: userId,
        data_source: "local_user_activity",
        data: [{ id: "feedback:collect", kind: "feedback_collection", priority: "medium", title: "Collect explicit feedback", reason: "E2E recommendation." }],
        count: 1,
        secrets_redacted: true
      });
    }
    const userPolicyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
    if (userPolicyMatch) {
      const userId = decodeURIComponent(userPolicyMatch[1]);
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        object: "aiask.user_data_policy",
        data: {
          user_id: userId,
          event_ttl_days: body.event_ttl_days ?? 30,
          audit_ttl_days: body.audit_ttl_days ?? 90,
          run_event_ttl_days: body.run_event_ttl_days ?? 90,
          tool_payload_ttl_days: body.tool_payload_ttl_days ?? 14,
          conversation_retention: body.conversation_retention || "local",
          allow_product_analytics: body.allow_product_analytics ?? false,
          allow_learning: body.allow_learning ?? true,
          updated_at: "2026-06-12T00:00:00.000Z",
        },
        secrets_redacted: true,
      });
    }
    if (path === "/v1/desktop/data/status") {
      const codes = url.searchParams.get("codes")?.split(",").filter(Boolean) || ["600519", "000001", "000858"];
      const maxStaleDays = Number(url.searchParams.get("max_stale_days") || 5);
      return fulfillJson(route, desktopDataStatusPayload(codes, maxStaleDays));
    }
    if (path === "/v1/desktop/stock-data-sources") {
      if (request.method() === "POST") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        const id = String(body.id || `e2e:${body.provider || "source"}:${stockDataSources.length + 1}`);
        const saved = { ...body, id, status: "ready", configured: true, updated_at: "2026-06-12T00:00:00Z" };
        stockDataSources = [saved, ...stockDataSources.filter((source) => source.id !== id)];
        return fulfillJson(route, { object: "aiask.stock_data_source", source: redactStockDataSource(saved), secrets_redacted: true });
      }
      return fulfillJson(route, stockDataSourcesPayload(stockDataSources));
    }
    if (path === "/v1/desktop/stock-data-sources/test") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      const inline = body.source && typeof body.source === "object" && !Array.isArray(body.source)
        ? body.source as Record<string, unknown>
        : null;
      const inlineId = String(inline?.id || body.id || "");
      const source = inline
        ? mergeStockDataSourceDraft(stockDataSources.find((item) => item.id === inlineId), inline)
        : stockDataSources.find((item) => item.id === body.id) || stockDataSources[0];
      return fulfillJson(route, {
        object: "aiask.stock_data_source_test",
        provider: source.provider || "akshare",
        mode: body.mode || "connectivity",
        success: true,
        status: "ready",
        configured: true,
        latency_ms: 12,
        sample_count: 3,
        source: redactStockDataSource(source),
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/data/sync-plan") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, dataSyncPlanPayload(body));
    }
    if (path === "/v1/desktop/financial-manager/catalog") {
      return fulfillJson(route, financialManagerCatalogPayload());
    }
    if (path === "/v1/desktop/financial-manager/status") {
      return fulfillJson(route, {
        object: "aiask.desktop.financial_manager.status",
        status: "ready",
        catalog_summary: financialManagerCatalogPayload().summary,
        broker: { live_trading_enabled: false, read_only_surfaces: ["ths_query_position"], blocked_actions: ["ths_place_order"] },
        mcp: { registration: "registered", servers: [{ name: "finance-demo", domain: "financial" }] },
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/financial-manager/query") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, financialManagerQueryPayload(body));
    }
    if (path === "/v1/desktop/broker-readiness") {
      return fulfillJson(route, brokerReadinessPayload());
    }
    if (path === "/v1/desktop/broker/sync") {
      return fulfillJson(route, {
        object: "aiask.desktop.broker_readonly",
        success: true,
        data: {
          sync_id: "broker_sync_e2e_qmt",
          profile: brokerProfileFixture,
          counts: {
            accounts: brokerAccountsFixture.length,
            positions: brokerPositionsFixture.length,
            orders: brokerOrdersFixture.length,
            deals: brokerDealsFixture.length
          },
          errors: [],
          analytics: brokerAnalyticsFixture()
        },
        error: null,
        read_only: true,
        live_trading_enabled: false,
        secrets_redacted: true,
        source_chain: ["desktop.e2e.fixture", "aiask_agent.broker_readonly"]
      });
    }
    if (path === "/v1/desktop/broker/accounts" || path === "/v1/desktop/broker/positions" || path === "/v1/desktop/broker/orders") {
      return fulfillJson(route, brokerSnapshotPayload());
    }
    if (path === "/v1/desktop/broker/analytics/latest" || path === "/v1/desktop/broker/analytics/run") {
      return fulfillJson(route, {
        object: "aiask.desktop.broker_readonly.analytics",
        success: true,
        data: brokerAnalyticsFixture(),
        error: null,
        read_only: true,
        live_trading_enabled: false,
        secrets_redacted: true,
        source_chain: ["desktop.e2e.fixture", "aiask_agent.broker_readonly"]
      });
    }
    if (path === "/v1/desktop/stock-radar/status") {
      return fulfillJson(route, { success: true, data: stockRadarStatusPayload(), error: null, error_code: null });
    }
    if (path === "/v1/desktop/stock-radar/candidates") {
      return fulfillJson(route, {
        success: true,
        data: stockRadarCandidatesPayload(url.searchParams.get("tier") || ""),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/desktop/stock-radar/digest") {
      return fulfillJson(route, { success: true, data: stockRadarDigestPayload(), error: null, error_code: null });
    }
    if (path === "/v1/desktop/users/local-profile") {
      if (request.method() === "PATCH") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        return fulfillJson(route, localProfilePayload(body));
      }
      return fulfillJson(route, localProfilePayload());
    }
    if (path === "/v1/desktop/factor-factory/status") {
      return fulfillJson(route, factorFactoryStatusPayload());
    }
    if (path === "/v1/desktop/quant/presets") {
      return fulfillJson(route, quantPresetsPayload());
    }
    if (path === "/v1/desktop/quant/research-runs") {
      return fulfillJson(route, quantResearchRunPayload());
    }
    if (path === "/v1/hermes/readiness") {
      return fulfillJson(route, capabilityPayload(true, factoryMode).hermes.readiness);
    }
    if (path === "/v1/capabilities/parity") {
      return fulfillJson(route, capabilityPayload(true, factoryMode).hermes.parity);
    }
    if (path === "/v1/hermes/tools") {
      return fulfillJson(route, { data: hermesTools().map((tool) => ({ name: tool.aiask_tools[0], capability: tool.area, category: tool.area, status: tool.status, side_effect: "read_only", description: tool.hermes_tool })) });
    }
    if (path === "/v1/hermes/admin/tools/agent_security_scan") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: {
          status: "completed",
          target: body.text ? "text" : body.path || ".",
          include_env: body.include_env === true,
          findings: [],
          arguments: body
        },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/processes") {
      return fulfillJson(route, { data: [{ pid: 101, name: "aiask-agent", status: "running" }] });
    }
    if (path === "/v1/browser/sessions") {
      return fulfillJson(route, { data: [{ id: "browser_e2e", status: "idle" }] });
    }
    if (path === "/v1/skills") {
      if (request.method() === "POST") return fulfillJson(route, { success: true, data: { name: "e2e-skill", status: "installed" } });
      return fulfillJson(route, { data: { root: "/tmp/aiask-skills", skills: [{ name: "risk-review", description: "Risk review", path: "/tmp/aiask-skills/risk-review/SKILL.md", updated_at: "2026-05-21T08:00:00.000Z" }] } });
    }
    if (path.startsWith("/v1/skills/")) {
      if (request.method() === "DELETE") return fulfillJson(route, { success: true, data: { status: "deleted" } });
      return fulfillJson(route, { success: true, data: { status: "updated" } });
    }
    if (path === "/v1/plugins") {
      return fulfillJson(route, {
        data: [
          {
            name: "audit-plugin",
            enabled: true,
            source: "local",
            version: "0.1.0",
            description: "Mock audit plugin",
            tools: [{ name: "audit_echo" }],
            commands: [],
            hooks: []
          }
        ]
      });
    }
    if (path.startsWith("/v1/plugins/") && path.endsWith("/test")) {
      return fulfillJson(route, { success: true, data: { status: "plugin_tool_tested" } });
    }
    if (path.startsWith("/v1/plugins/")) {
      return fulfillJson(route, { success: true, data: { status: "plugin_updated" } });
    }
    if (path === "/v1/mcp/servers") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.servers });
    }
    if (path === "/v1/mcp/tools") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.tools });
    }
    if (path === "/v1/mcp/resources") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.resources });
    }
    if (path === "/v1/mcp/prompts") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.prompts });
    }
    if (path === "/v1/mcp/oauth_status") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.oauth });
    }
    if (path === "/v1/mcp/resources/read") {
      return fulfillJson(route, { object: "mcp.resource", data: { success: true, server: "finance-demo", uri: "aiask://quotes", result: { text: "quote resource ok" } } });
    }
    if (path === "/v1/mcp/prompts/get") {
      return fulfillJson(route, { object: "mcp.prompt", data: { success: true, server: "finance-demo", name: "risk-review", prompt: "risk prompt ok" } });
    }
    if (path === "/v1/mcp/oauth/start") {
      return fulfillJson(route, { object: "mcp.oauth_start", data: { status: "oauth_required", server: "finance-demo", authorization_url: "https://auth.local/authorize" } });
    }
    if (path === "/v1/mcp/register-local") {
      return fulfillJson(route, { object: "mcp.registration", success: true, data: { server: { name: "finance-demo", url: "http://127.0.0.1:3100/mcp" } } });
    }
    if (path === "/v1/mcp/discover") {
      return fulfillJson(route, { object: "mcp.discovery", success: true, data: { server: "finance-demo", tools_count: 1, resources_count: 1, prompts_count: 1 } });
    }
    if (path === "/v1/connectors/summary") {
      return fulfillJson(route, connectorsSummaryPayload());
    }
    if (path === "/v1/connectors") {
      const type = url.searchParams.get("type");
      const category = url.searchParams.get("category");
      const connectors = connectorFixtureList().filter((connector) => {
        const typeMatches = !type || String(connector.type || "") === type;
        const categoryMatches = !category || String(connector.category || "") === category;
        return typeMatches && categoryMatches;
      });
      return fulfillJson(route, { object: "list", data: connectors });
    }
    const connectorTestMatch = path.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)\/test$/);
    if (connectorTestMatch) {
      const connectorType = decodeURIComponent(connectorTestMatch[1]);
      const connectorName = decodeURIComponent(connectorTestMatch[2]);
      const connector = connectorFixture(connectorType, connectorName) || { type: connectorType, name: connectorName };
      return fulfillJson(route, {
        object: "aiask.connector_test",
        data: { ...connector, last_test_status: "passed", test_result: { status: "passed", action: "connector.test" } }
      });
    }
    const connectorDetailMatch = path.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)$/);
    if (connectorDetailMatch) {
      const connectorType = decodeURIComponent(connectorDetailMatch[1]);
      const connectorName = decodeURIComponent(connectorDetailMatch[2]);
      const connector = connectorFixture(connectorType, connectorName) || { type: connectorType, name: connectorName };
      return fulfillJson(route, { object: "aiask.connector_detail", data: connector });
    }
    if (path === "/v1/ai/status") {
      return fulfillJson(route, aiStatus());
    }
    if (path === "/v1/ai/config") {
      if (request.method() === "PATCH") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        return fulfillJson(route, {
          object: "aiask.ai_config",
          saved: true,
          provider: body.provider || "openai",
          model: body.model || "gpt-5.4",
          base_url_configured: true,
          api_key_configured: true,
          mock: false,
          configured: true,
          updated_keys: ["AIASK_AGENT_MODEL_PROVIDER", "AIASK_AGENT_MODEL", "OPENAI_BASE_URL"],
          env_file: "/tmp/aiask/.env",
          secrets_redacted: true
        });
      }
      return fulfillJson(route, aiConfigPayload());
    }
    if (path === "/v1/ai/smoke") {
      return fulfillJson(route, {
        object: "aiask.ai_smoke",
        configured: true,
        success: true,
        provider: "openai",
        mock: false,
        model: "gpt-5.4",
        latency_ms: 123,
        response_preview: "AIASK model smoke ok.",
        usage: { total_tokens: 12 },
        tool_call_count: 0,
        secrets_redacted: true
      });
    }
    if (path === "/v1/ai/models") {
      return fulfillJson(route, {
        object: "list",
        configured: true,
        provider: "openai",
        unsupported: false,
        data: [
          { id: "gpt-5.4", owned_by: "fixture" },
          { id: "gpt-5.2", owned_by: "fixture" }
        ]
      });
    }
    if (path === "/v1/responses") {
      return fulfillJson(route, {
        id: "resp_fixture",
        object: "response",
        created_at: 1777467084,
        status: "completed",
        model: "gpt-5.4",
        output_text: "AIASK_OK",
        output: [{ type: "message", role: "assistant", content: [{ type: "output_text", text: "AIASK_OK" }] }],
        usage: { total_tokens: 20 },
        metadata: {
          session_id: "session_fixture",
          run_id: "run_fixture",
          mode: "finance_safe",
          tool_calls: [],
          audit_events: [
            { event: "run.started", run_id: "run_fixture", created_at: "2026-04-29T12:51:17.000Z" },
            { event: "model.started", run_id: "run_fixture", created_at: "2026-04-29T12:51:18.000Z" },
            { event: "model.completed", run_id: "run_fixture", created_at: "2026-04-29T12:51:19.000Z" },
            { event: "model.delta", run_id: "run_fixture", content: "AIASK_OK", created_at: "2026-04-29T12:51:19.000Z" },
            { event: "run.completed", run_id: "run_fixture", status: "completed", created_at: "2026-04-29T12:51:20.000Z" }
          ]
        }
      });
    }
    if (path === "/v1/runs/run_fixture/events") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "id: 1",
          "event: run.started",
          "data: {\"id\":\"evt_1\",\"kind\":\"system\",\"title\":\"run.started\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:00.000Z\",\"status\":\"started\"}",
          "",
          "id: 2",
          "event: model.started",
          "data: {\"id\":\"evt_2\",\"kind\":\"system\",\"title\":\"model.started\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:01.000Z\"}",
          "",
          "id: 3",
          "event: model.completed",
          "data: {\"id\":\"evt_3\",\"kind\":\"system\",\"title\":\"model.completed\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:02.000Z\"}",
          "",
          "id: 4",
          "event: model.delta",
          "data: {\"id\":\"evt_4\",\"kind\":\"system\",\"title\":\"model.delta\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:02.500Z\",\"data\":{\"content\":\"AIASK_OK\"}}",
          "",
          "id: 5",
          "event: run.completed",
          "data: {\"id\":\"evt_5\",\"kind\":\"system\",\"title\":\"run.completed\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:03.000Z\",\"status\":\"completed\"}",
          "",
          ""
        ].join("\n")
      });
    }
    const runArtifactsMatch = path.match(/^\/v1\/runs\/([^/]+)\/artifacts$/);
    if (runArtifactsMatch) {
      const runId = decodeURIComponent(runArtifactsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        run_id: runId,
        data: [
          {
            artifact_id: "artifact_e2e_summary",
            run_id: runId,
            session_id: "session_fixture",
            user_id: "local-e2e",
            kind: "report",
            title: "Agent 回复摘要",
            preview_text: "AIASK_OK",
            status: "completed",
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const runSourcesMatch = path.match(/^\/v1\/runs\/([^/]+)\/sources$/);
    if (runSourcesMatch) {
      const runId = decodeURIComponent(runSourcesMatch[1]);
      return fulfillJson(route, {
        object: "list",
        run_id: runId,
        data: [
          {
            source_id: "source_e2e_run",
            run_id: runId,
            session_id: "session_fixture",
            user_id: "local-e2e",
            provider: "e2e",
            source_type: "fixture",
            title: "E2E run source",
            excerpt: "Mock source for run evidence.",
            source_tier: "fixture",
            credibility_score: 1,
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const sessionArtifactsMatch = path.match(/^\/v1\/sessions\/([^/]+)\/artifacts$/);
    if (sessionArtifactsMatch) {
      const sessionId = decodeURIComponent(sessionArtifactsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        session_id: sessionId,
        data: [
          {
            artifact_id: "artifact_e2e_session",
            session_id: sessionId,
            user_id: "local-e2e",
            kind: "note",
            title: "Session fixture artifact",
            preview_text: "AIASK_OK session artifact",
            status: "completed",
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const sessionSourcesMatch = path.match(/^\/v1\/sessions\/([^/]+)\/sources$/);
    if (sessionSourcesMatch) {
      const sessionId = decodeURIComponent(sessionSourcesMatch[1]);
      return fulfillJson(route, {
        object: "list",
        session_id: sessionId,
        data: [
          {
            source_id: "source_e2e_session",
            session_id: sessionId,
            user_id: "local-e2e",
            provider: "e2e",
            source_type: "fixture",
            title: "E2E session source",
            excerpt: "Mock source for session evidence.",
            source_tier: "fixture",
            credibility_score: 1,
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    if (path === "/v1/jobs") {
      if (request.method() === "POST") {
        return fulfillJson(route, {
          object: "aiask.job",
          job_id: "job_e2e_created",
          status: "created",
          enabled: true,
          name: "每日研究监控"
        });
      }
      return fulfillJson(route, jobsPayload());
    }
    if (path.match(/^\/v1\/jobs\/[^/]+\/run$/)) {
      return fulfillJson(route, {
        success: true,
        data: { job_id: "job_e2e_research", run_id: "run_job_e2e", status: "completed", output_text: "job ok" },
        error: null,
        error_code: null
      });
    }
    if (path.match(/^\/v1\/jobs\/[^/]+\/runs$/)) {
      return fulfillJson(route, {
        object: "list",
        data: [
          {
            run_id: "run_job_e2e",
            job_id: "job_e2e_research",
            status: "completed",
            started_at: "2026-05-21T07:30:00.000Z",
            finished_at: "2026-05-21T07:30:03.000Z",
            duration_ms: 3000,
            output_text: "job ok"
          }
        ]
      });
    }
    if (path.match(/^\/v1\/jobs\/[^/]+$/)) {
      if (request.method() === "DELETE") return fulfillJson(route, { object: "aiask.job", job_id: "job_e2e_research", status: "deleted" });
      return fulfillJson(route, { object: "aiask.job", job_id: "job_e2e_research", status: "updated", enabled: false });
    }
    if (path === "/intents") {
      if (request.method() === "GET") {
        return fulfillJson(route, {
          object: "list",
          data: [
            {
              ...intentEnvelope("data_sync.run_once").data.intent,
              action: "data_sync.run_once"
            }
          ]
        });
      }
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, intentEnvelope(String(body.action || "desktop.intent")));
    }
    if (path.match(/^\/intents\/[^/]+$/)) {
      return fulfillJson(route, intentEnvelope("desktop.intent"));
    }
    if (path.match(/^\/intents\/[^/]+\/(confirm|deny)$/)) {
      const action = path.endsWith("/confirm") ? "confirmed" : "denied";
      return fulfillJson(route, {
        success: true,
        data: { intent: { ...intentEnvelope("desktop.intent").data.intent, status: action } },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_incubation_factory_status") {
      return fulfillJson(route, incubationStatusEnvelope());
    }
    if (path === "/v1/desktop/trade-predictions/status") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionStatus(queryRecord(url.searchParams))));
    }
    if (path === "/v1/desktop/trade-predictions/outcomes") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionOutcomes(queryRecord(url.searchParams))));
    }
    if (path === "/v1/desktop/trade-predictions/matrix") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionMatrix(queryRecord(url.searchParams))));
    }
    if (path === "/v1/tools/agent_market_temperature_snapshot") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureSnapshotPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_cache_readiness") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureCacheReadinessPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_cache_history") {
      return fulfillJson(route, { success: true, data: marketTemperatureCacheHistoryPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_industry_history") {
      return fulfillJson(route, { success: true, data: marketTemperatureIndustryHistoryPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_industry_constituents") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureIndustryConstituentsPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_forward_validation") {
      return fulfillJson(route, { success: true, data: marketTemperatureForwardValidationPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_strategy_domain_events") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, strategyEventsEnvelope(typeof body.event_type === "string" ? body.event_type : null));
    }
    if (path === "/v1/tools/agent_factory_event_list") {
      return fulfillJson(route, { success: true, data: factoryEventListPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_factory_event_preview_tasks") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: factoryEventPreviewTasksPayload(String(body.event_id || "evt_e2e_001")),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_event_lineage") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: factoryEventLineagePayload(String(body.event_id || "evt_e2e_001")),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_theme_exposure_status") {
      return fulfillJson(route, {
        success: true,
        data: { row_count: 42, symbol_count: 12, theme_count: 3, latest_updated_at: "2026-06-08T14:24:00+08:00" },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_event_outbox_status") {
      return fulfillJson(route, {
        success: true,
        data: { counts: { processed: 2, failed: 0 }, latest: [] },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_quant_data_gate") {
      return fulfillJson(route, { success: true, data: { status: "partial", missing: ["000858"], stale: ["000001"] }, error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_web_search") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: {
          provider: body.provider || "duckduckgo",
          results: [
            { title: "AIASK data source guide", url: "https://example.test/aiask-data-source", snippet: "Mock search result for E2E." },
            { title: "Market data connectivity", url: "https://example.test/market-data", snippet: "Connectivity check passed." }
          ],
          query: body.query || "AIASK"
        },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_memory_search") {
      return fulfillJson(route, { success: true, data: [{ kind: "memory", content: "mock memory hit" }], error: null, error_code: null });
    }
    if (path === "/v1/hermes/sessions") {
      return fulfillJson(route, { object: "list", data: [{ session_id: "session_fixture", title: "E2E session", user_id: "local-e2e", updated_at: "2026-05-21T08:00:00.000Z" }] });
    }
    if (path.match(/^\/v1\/sessions\/[^/]+\/messages$/)) {
      return fulfillJson(route, { object: "list", data: [{ role: "assistant", content: "AIASK_OK" }] });
    }
    if (path === "/v1/search") {
      return fulfillJson(route, { object: "list", data: [{ kind: "response", object_id: "resp_fixture", session_id: "session_fixture", user_id: "local-e2e", content: "AIASK_OK search result" }] });
    }
    if (path === "/v1/webhooks") {
      if (request.method() === "POST") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        const created = {
          webhook_id: "webhook_fixture_created",
          name: String(body.name || "Created Webhook"),
          events: Array.isArray(body.events) ? body.events : ["MCP UI smoke test"],
          prompt: String(body.prompt || ""),
          enabled: true,
          status: "ready"
        };
        webhookSubscriptions = [created, ...webhookSubscriptions];
        return fulfillJson(route, { object: "webhook", data: created });
      }
      return fulfillJson(route, { object: "list", data: webhookSubscriptions });
    }
    const webhookMatch = path.match(/^\/v1\/webhooks\/([^/]+)$/);
    if (webhookMatch && request.method() === "DELETE") {
      const webhookId = decodeURIComponent(webhookMatch[1]);
      webhookSubscriptions = webhookSubscriptions.filter((item) => item.webhook_id !== webhookId);
      return fulfillJson(route, { object: "webhook.deleted", deleted: true, webhook_id: webhookId });
    }
    if (path === "/v1/approvals") {
      return fulfillJson(route, { data: [intentEnvelope("desktop.intent").data.intent] });
    }
    if (path === "/v1/gateway/status") {
      return fulfillJson(route, { object: "aiask.gateway_status", status: "ready", configured: true, updated_at: "2026-05-21T08:00:00.000Z" });
    }
    if (path === "/v1/gateway/daemon/status") {
      return fulfillJson(route, { object: "aiask.gateway_daemon_status", data: { enabled: true, running: true, listeners: { local: "running" } } });
    }
    if (path === "/v1/gateway/platforms") {
      return fulfillJson(route, { object: "list", data: [{ platform: "local", status: "ready", enabled: true, configured: true }] });
    }
    if (path === "/v1/gateway/messages") {
      return fulfillJson(route, {
        object: "list",
        data: [
          {
            message_id: "gateway_msg_failed",
            platform: "local",
            target: "ops",
            status: "failed",
            content: "mock failed gateway message",
            error_message: "mock delivery failed",
            retry_count: 1,
            created_at: "2026-05-21T08:00:00.000Z"
          }
        ]
      });
    }
    if (path === "/v1/gateway/directory") {
      return fulfillJson(route, { object: "list", data: [{ platform: "local", kind: "channel", target: "ops", updated_at: "2026-05-21T08:00:00.000Z" }] });
    }
    if (path === "/v1/gateway/directory/refresh") {
      return fulfillJson(route, { object: "aiask.gateway_directory_refresh", success: true, data: { refreshed: true } });
    }
    if (path.match(/^\/v1\/gateway\/messages\/[^/]+\/retry$/)) {
      return fulfillJson(route, { object: "aiask.gateway_retry", success: true, data: { retried: true } });
    }
    if (path.match(/^\/v1\/gateway\/platforms\/[^/]+\/(start|stop)$/)) {
      return fulfillJson(route, { object: "aiask.gateway_platform_action", success: true, data: { status: "ok" } });
    }
    if (path.match(/^\/v1\/gateway\/platforms\/[^/]+\/health$/)) {
      return fulfillJson(route, { object: "aiask.gateway_platform_health", success: true, data: { status: "ready" } });
    }
    if (path === "/v1/terminal/backends") {
      return fulfillJson(route, {
        object: "list",
        data: [{ name: "local-powershell", shell: "powershell", status: "ready", read_only_probe: true }]
      });
    }
    if (path === "/v1/terminal/sessions") {
      return fulfillJson(route, {
        object: "list",
        data: [{ session_id: "terminal_fixture", backend: "local-powershell", status: "idle", user_id: "local-e2e" }]
      });
    }
    const terminalBackendSessionsMatch = path.match(/^\/v1\/terminal\/backends\/([^/]+)\/sessions$/);
    if (terminalBackendSessionsMatch) {
      const backend = decodeURIComponent(terminalBackendSessionsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        backend,
        data: [{ session_id: "terminal_fixture", backend, status: "idle", user_id: "local-e2e" }]
      });
    }
    if (path === "/v1/learning/status") {
      return fulfillJson(route, { status: "ready" });
    }
    if (path === "/v1/learning/review") {
      return fulfillJson(route, { object: "list", data: [{ proposal_id: "learn_fixture", status: "pending_review", title: "Mock 学习建议", summary: "Apply a safer prompt." }] });
    }
    if (path === "/v1/learning/apply") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { object: "learning.proposal", data: { proposal_id: body.proposal_id || "learn_fixture", status: "applied" } });
    }
    if (path === "/v1/rl/environments") {
      return fulfillJson(route, { object: "list", data: { environments: [{ id: "finance_safe_eval", status: "ready" }], default: "finance_safe_eval" } });
    }
    if (path === "/v1/rl/config") {
      if (request.method() === "PATCH") return fulfillJson(route, { object: "aiask.rl_config", data: { status: "updated" } });
      return fulfillJson(route, { object: "aiask.rl_config", data: { provider: "mock", max_steps: 10, status: "configured" }, secrets_redacted: true });
    }
    if (path === "/v1/rl/runs") {
      if (request.method() === "POST") return fulfillJson(route, { object: "rl.run", data: { run_id: "rl_fixture_new", environment: "finance_safe_eval", status: "running" } });
      return fulfillJson(route, { object: "list", data: [{ run_id: "rl_fixture", environment: "finance_safe_eval", status: "dry_run_ready" }] });
    }
    const rlRunMatch = path.match(/^\/v1\/rl\/runs\/([^/]+)(?:\/(stop|results|logs))?$/);
    if (rlRunMatch) {
      const runId = decodeURIComponent(rlRunMatch[1]);
      const action = rlRunMatch[2];
      if (action === "stop") return fulfillJson(route, { object: "rl.stop", data: { run_id: runId, status: "stopped" } });
      if (action === "results") return fulfillJson(route, { object: "rl.results", data: { run_id: runId, metrics: { reward: 1 } } });
      if (action === "logs") return fulfillJson(route, { object: "rl.logs", data: { run_id: runId, lines: ["mock rl log"] } });
      return fulfillJson(route, { object: "rl.run", data: { run_id: runId, environment: "finance_safe_eval", status: "dry_run_ready" } });
    }
    return fulfillJson(route, { error: `Unhandled fixture route: ${path}` }, 500);
  });
}

test.beforeEach(async ({ page }) => {
  const consoleMessages: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 400 && !response.url().includes("/@vite")) {
      failedResponses.push(`${status} ${response.url()}`);
    }
  });
  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("aiask.endpoint", "http://127.0.0.1:8767");
    localStorage.setItem("aiask.endpoint.verified", "1");
    localStorage.setItem("aiask.endpoint.autoconnect", "1");
  });
  (page as Page & { _aiaskConsoleMessages?: string[] })._aiaskConsoleMessages = consoleMessages;
  (page as Page & { _aiaskFailedResponses?: string[] })._aiaskFailedResponses = failedResponses;
});

test.afterEach(async ({ page }) => {
  const consoleMessages = (page as Page & { _aiaskConsoleMessages?: string[] })._aiaskConsoleMessages || [];
  const failedResponses = (page as Page & { _aiaskFailedResponses?: string[] })._aiaskFailedResponses || [];
  expect(consoleMessages).toEqual([]);
  expect(failedResponses).toEqual([]);
});

const VIEW_LABELS: Record<string, string> = {
  Overview: "总览",
  Agent: "工作台",
  Workbench: "工作台",
  Sessions: "会话",
  "Runs / Events": "运行 / 事件",
  "Coverage Matrix": "覆盖矩阵",
  Models: "模型配置",
  "Data & Sync": "数据",
  MCP: "MCP / 连接器",
  Skills: "插件 / 技能",
  "Projects / Contexts": "项目 / 上下文",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  Automation: "自动化",
  Readiness: "准备度 / 健康",
  "Financial Manager": "金融经理台",
  "Market Temperature": "市场温度",
  "Quant Research": "量化研究",
  "Strategy Factory": "策略工厂",
  "Factor Factory": "因子工厂",
  Incubation: "孵化工厂",
  "Local User": "本地用户",
  Tools: "工具",
  Capabilities: "能力中心",
  "Event Console": "事件控制台",
  "Factory Events": "工厂事件",
  Diagnostics: "诊断",
  "Agent Status": "智能体",
  Workflows: "工作流",
  Settings: "设置"
};

const TAB_LABELS: Record<string, string> = {
  Overview: "总览",
  "Coverage Matrix": "覆盖矩阵",
  Connectors: "连接器",
  Hermes: "Hermes",
  MCP: "MCP",
  "Strategy Factory": "策略工厂",
  Incubation: "孵化",
  Skills: "技能",
  Plugins: "插件",
  "AI Tests": "AI 测试"
};

const CONTROL_LABELS: Record<string, string> = {
  "Sync QMT read-only": "Sync QMT read-only",
  Connect: "连接 AIASK",
  Refresh: "刷新",
  Run: "运行线程任务",
  Search: "搜索",
  "Sync Agent state": "同步 AIASK 状态",
  "Finance safe mode": "Finance safe",
  "Finance safe": "金融安全",
  "Hermes full mode": "Hermes full 模式",
  "Hermes full": "Hermes full",
  "Run thread task": "运行线程任务",
  "Load run events": "加载运行事件",
  "Load run events for selected task": "Load events for the selected run",
  "Generate sync plan": "生成同步计划",
  "Create approval intent": "创建审批意图",
  "Run research": "运行研究",
  "Run read-only workflow": "运行只读工作流",
  "Run query": "运行查询",
  "Refresh capability review": "刷新能力评审",
  "Register local MCP server": "注册本地 MCP 服务",
  "Discover or refresh MCP server": "发现或刷新 MCP 服务",
  "Run MCP read-only smoke": "运行 MCP 只读冒烟测试",
  "Read MCP resource": "读取 MCP 资源",
  "Get MCP prompt": "获取 MCP 提示词",
  "Start MCP OAuth flow": "启动 MCP OAuth 流程",
  Install: "安装",
  Update: "更新",
  Delete: "删除",
  "Create job": "创建任务",
  Inspect: "查看",
  Pause: "暂停",
  Resume: "恢复",
  "Create run intent": "创建运行意图",
  "Maintenance intent": "创建维护意图",
  "Run intent": "创建运行意图",
  "Dry-run intent": "创建试运行意图",
  "Save profile": "保存画像",
  "Save local profile": "保存画像",
  "Run safe probe": "运行安全探测",
  "Run safe probe for agent_": "运行安全探测 agent_",
  "Fill example": "填充示例",
  "Fill example for agent_": "为 agent_",
  Disable: "禁用",
  "Disable plugin": "禁用插件",
  Enable: "启用",
  Configure: "配置",
  "Test tool": "测试",
  "Self-test": "自检",
  "Save plugin": "保存插件",
  "Run AI Smoke": "运行 AI 冒烟测试",
  "List Models": "列出模型",
  "Test connection": "测试连接",
  "Reset endpoint to default Agent endpoint": "恢复默认 Agent 端点",
  "Refresh connectors": "刷新连接器",
  "Load terminal sessions": "加载终端会话",
  "Connector detail": "详情",
  "Connector test": "测试",
  Reauthorize: "重新认证",
  "risk-review Risk review": "risk-review Risk review",
  "Projects / Contexts": "项目 / 上下文",
  "Plugins / Skills gated": "插件 / 技能 受限",
  "Plugins / Skills ready": "插件 / 技能 就绪",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  "Load messages": "加载消息",
  "Preview Export/Delete": "Preview Export/Delete",
  "Preview Aggregate Governance": "Preview Aggregate Governance",
  "Run the first registered plugin tool": "运行第一个已注册插件工具",
  "Load plugin commands": "加载插件命令",
  "Test plugin command": "测试插件命令",
  "Disable plugin audit-plugin": "禁用插件 audit-plugin",
  "Enable plugin audit-plugin": "启用插件 audit-plugin",
  "Configure plugin audit-plugin": "配置插件 audit-plugin",
  "Test plugin audit-plugin": "测试插件 audit-plugin",
  "Test first plugin tool audit-plugin": "测试插件首个工具 audit-plugin",
  "Load commands for plugin audit-plugin": "加载插件命令 audit-plugin",
  "Inspect job 每日研究监控": "查看任务 每日研究监控",
  "Pause job 每日研究监控": "暂停任务 每日研究监控",
  "Run job 每日研究监控": "运行任务 每日研究监控",
  "Delete job 每日研究监控": "删除任务 每日研究监控",
  "Search tools input": "搜索工具输入",
  "初始化 Bootstrap": "初始化引导",
  "排空 outbox": "排空出站队列"
};

const PLACEHOLDER_LABELS: Record<string, string> = {
  "resource uri": "资源 URI",
  "prompt name": "提示词名称",
  "OAuth server name": "OAuth 服务名称",
  "Ask AIASK to research, code, inspect tools, or continue a session...": "让 AIASK 研究、检查工具、生成报告，或继续当前线程...",
  "Search local sessions, responses, and memory": "搜索本地会话、回复和记忆",
  "Search tools": "搜索工具",
  "Search area, tool, platform...": "搜索领域、工具、平台...",
  "payload text": "载荷文本"
};

const EXPECTED_TEXT_LABELS: Record<string, string> = {
  BROKER_SYNCED: "BROKER_SYNCED",
  AGENT_STATUS_LOADED: "智能体状态已加载",
  AGGREGATE_GOVERNANCE_PREVIEWED: "AGGREGATE_GOVERNANCE_PREVIEWED",
  AIASK_ONLINE: "在线",
  CONNECTORS_LOADED: "连接器已加载",
  DATA_STATUS_LOADED: "数据状态已加载",
  EVENTS_LOADED: "事件已加载",
  FACTOR_FACTORY_LOADED: "因子工厂已加载",
  FACTOR_MAINTENANCE_INTENT_CREATED: "因子维护意图已创建",
  FACTOR_RUN_INTENT_CREATED: "因子运行意图已创建",
  FACTORY_RELAY_LOADED: "接力状态已加载",
  INCUBATION_DRY_RUN_INTENT_CREATED: "孵化试运行意图已创建",
  INCUBATION_LOADED: "孵化状态已加载",
  INCUBATION_MAINTENANCE_INTENT_CREATED: "孵化维护意图已创建",
  INCUBATION_RUN_ONCE_INTENT_CREATED: "孵化运行意图已创建",
  JOBS_LOADED: "任务已加载",
  LOCAL_PROFILE_LOADED: "本地画像已加载",
  LOCAL_PROFILE_SAVED: "本地画像已保存",
  MARKET_TEMPERATURE_LOADED: "快照已加载",
  MODELS_LOADED: "模型列表已加载",
  MODEL_STATUS_LOADED: "模型状态已加载",
  RADAR_LOADED: "雷达已加载",
  STOCK_DATA_SOURCE_TEST_PASSED: "数据源测试通过",
  STRATEGY_FACTORY_INTENT_CREATED: "策略工厂意图已创建",
  SYNC_INTENT_CREATED: "同步审批意图已创建",
  SYNC_PLAN_READY: "同步计划已生成",
  USER_DATA_EXPORT_PREVIEWED: "USER_DATA_EXPORT_PREVIEWED",
  USER_DATA_SEARCHED: "用户数据已搜索",
  WEB_SEARCH_PASSED: "搜索调用成功"
};

const SETTINGS_STRUCTURE_BUTTONS = [
  "返回对话",
  "返回工作台",
  "常规",
  "连接",
  "令牌与权限",
  "技能管理",
  "自动化管理",
  "应用集成",
  "Webhook",
  "插件与技能包",
  "模型配置",
  "MCP 管理入口",
  "工作流入口",
  "股票数据源",
  "数据路径",
  "学习 / RL",
  "安全扫描",
  "高级诊断入口",
  "关于"
];

const LEGACY_REPLACEMENT_BUTTONS = [
  "前往工作台",
  "前往 工作台",
  "前往设置",
  "前往 设置",
  "前往 审批",
  "前往 MCP / 连接器",
  "前往 运行 / 事件",
  "前往 准备度 / 健康",
  "前往 插件 / 技能",
  "前往审批",
  "前往 审批",
  "前往集成",
  "前往 集成",
];

const WORKBENCH_SAFE_PATH_BUTTONS = [
  "打开准备度",
  "打开 MCP",
  "打开本地用户",
  "打开金融经理台",
  "打开数据",
  "打开金融实验室",
];

function viewLabel(name: string) {
  return VIEW_LABELS[name] || name;
}

function tabLabel(name: string) {
  return TAB_LABELS[name] || name;
}

function controlLabel(name: string) {
  return CONTROL_LABELS[name] || name;
}

function placeholderLabel(name: string) {
  return PLACEHOLDER_LABELS[name] || name;
}

function expectedTextLabel(text: string) {
  return EXPECTED_TEXT_LABELS[text] || text;
}

async function expandAdvancedMcpOperations(page: Page) {
  const advanced = page.locator("details.mcp-operations-panel");
  if (await advanced.count()) {
    await advanced.evaluate((node) => {
      if (node instanceof HTMLDetailsElement) node.open = true;
    });
  }
}

Object.assign(VIEW_LABELS, {
  Overview: "总览",
  Agent: "工作台",
  Workbench: "工作台",
  Sessions: "会话",
  "Runs / Events": "运行 / 事件",
  "Coverage Matrix": "覆盖矩阵",
  Models: "模型配置",
  "Data & Sync": "数据",
  MCP: "MCP / 连接器",
  Skills: "插件 / 技能",
  "Projects / Contexts": "项目 / 上下文",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  Automation: "自动化",
  "Financial Manager": "金融经理台",
  "Market Temperature": "市场温度",
  "Quant Research": "量化研究",
  "Strategy Factory": "策略工厂",
  "Factor Factory": "因子工厂",
  Incubation: "孵化工厂",
  "Local User": "本地用户",
  Tools: "工具",
  Capabilities: "能力中心",
  "Event Console": "事件控制台",
  "Factory Events": "工厂事件",
  Diagnostics: "诊断",
  "Agent Status": "智能体",
  Workflows: "工作流",
  Settings: "设置"
});

const VIEW_IDS: Record<string, string> = {
  Overview: "overview",
  Agent: "workbench",
  Workbench: "workbench",
  "Runs / Events": "runs-events",
  "Coverage Matrix": "coverage",
  Models: "models",
  "Data & Sync": "data",
  MCP: "mcp-connectors",
  Skills: "plugins-skills",
  "Projects / Contexts": "projects-contexts",
  Approvals: "tools-intents-approvals",
  "Finance Lab": "finance-lab",
  Integrations: "integrations",
  Automation: "automation",
  Readiness: "readiness-health",
  "Financial Manager": "financial-manager",
  "Market Temperature": "market-temperature",
  "Quant Research": "quant",
  "Strategy Factory": "strategy-factory",
  "Factor Factory": "factor-factory",
  Incubation: "incubation",
  "Local User": "user",
  Tools: "tools",
  Capabilities: "capabilities",
  "Event Console": "event-console",
  "Factory Events": "factory-events",
  Diagnostics: "diagnostics",
  "Agent Status": "agent",
  Workflows: "workflows",
  Settings: "settings"
};

const VIEW_GROUP_IDS: Record<string, string> = {
  workbench: "primary",
  "projects-contexts": "primary",
  "runs-events": "primary",
  "tools-intents-approvals": "primary",
  "finance-lab": "primary",
  integrations: "primary",
  automation: "primary",
  settings: "primary",
  "financial-manager": "advanced-finance",
  "market-temperature": "advanced-finance",
  quant: "advanced-finance",
  "strategy-factory": "advanced-finance",
  "factor-factory": "advanced-finance",
  incubation: "advanced-finance",
  data: "advanced-finance",
  workflows: "advanced-finance",
  "factory-events": "advanced-finance",
  "plugins-skills": "advanced-ops",
  "mcp-connectors": "advanced-ops",
  gateway: "advanced-ops",
  "readiness-health": "advanced-ops",
  "extensions-pilot": "advanced-ops",
  models: "advanced-ops",
  overview: "legacy",
  agent: "legacy",
  capabilities: "legacy",
  coverage: "legacy",
  tools: "legacy",
  mcp: "legacy",
  diagnostics: "legacy",
  "event-console": "legacy",
  skills: "legacy",
  user: "legacy"
};

Object.assign(CONTROL_LABELS, {
  Refresh: "刷新",
  "Sync Agent state": "同步 AIASK 状态",
  "Test connection": "测试连接",
  "Reset endpoint to default Agent endpoint": "恢复默认 Agent 端点",
  "Save profile": "保存画像",
  "Update snapshot": "更新快照",
  "Load terminal sessions": "加载终端会话",
  "Refresh radar": "刷新雷达",
  "Create radar run intent": "创建雷达运行意图",
  "Create radar push preview intent": "创建推送预览意图",
  "Create radar schedule intent": "创建调度意图",
  "Run MCP read-only smoke": "运行 MCP 只读冒烟测试",
  "初始化 Bootstrap": "初始化引导",
  "排空 outbox": "排空出站队列"
});

async function openOverview(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "线程优先工作台" })).toBeVisible();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toBeVisible();
}

async function openSettings(page: Page) {
  if (await settingsReturnButton(page).count()) return;
  await page.getByRole("region", { name: "主工作区" }).getByRole("button", { name: viewLabel("Settings"), exact: true }).click();
}

function settingsReturnButton(page: Page) {
  return page.locator(".settings-shell").getByRole("button", { name: /^(返回对话|返回工作台)$/ });
}

async function openSettingsSection(page: Page, sectionLabel: string) {
  await openSettings(page);
  await page.getByRole("navigation", { name: "设置导航" }).getByRole("button", { name: sectionLabel, exact: true }).click();
}

async function clickSettingsPanelRefresh(page: Page) {
  await page.locator(".settings-section-stack").getByRole("button", { name: controlLabel("Refresh"), exact: true }).last().click();
}

async function setControlToken(page: Page, token = CONTROL_TOKEN) {
  await openSettings(page);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  const controlTokenInput = page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input");
  await expect(controlTokenInput).toHaveCount(1);
  await controlTokenInput.fill(token);
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await settingsReturnButton(page).click();
}

const WORKFLOW_ENTRY_VIEWS = new Set<string>();
const SETTINGS_MODEL_VIEWS = new Set<string>();
const SETTINGS_MCP_VIEWS = new Set<string>();
const SETTINGS_ADVANCED_VIEWS = new Set<string>();

async function clickShortcutByLabel(page: Page, label: string) {
  const shortcut = page.locator("button.settings-shortcut, article.workflow-hub-card button, .workflow-hub-card button").filter({ hasText: label });
  await expect(shortcut.first()).toBeVisible();
  await shortcut.first().click();
}

async function openCollapsedNavGroup(page: Page, groupName: string, targetLabel: string) {
  const navigation = page.getByRole("navigation");
  const group = navigation.locator(`section[aria-label="${groupName}"]`);
  if (!(await group.count())) return false;
  const groupToggle = group.getByRole("button", { name: groupName, exact: true });
  if (!(await group.getByRole("button", { name: targetLabel, exact: true }).count())) {
    if (!(await groupToggle.count()) || !(await groupToggle.first().isVisible())) return false;
    await groupToggle.click();
  }
  const target = group.getByRole("button", { name: targetLabel, exact: true });
  if (!(await target.count())) return false;
  await target.click();
  return true;
}

async function openMainViewById(page: Page, name: string) {
  const viewId = VIEW_IDS[name];
  if (!viewId) return false;
  const navigation = page.getByRole("navigation");
  const selector = `button[data-view-id="${viewId}"]`;
  let target = navigation.locator(selector);
  const groupId = VIEW_GROUP_IDS[viewId];
  const group = groupId ? navigation.locator(`section[data-view-group-id="${groupId}"]`) : null;
  if (!(await target.count()) && group && (await group.count())) {
    const toggle = group.getByRole("button").first();
    if ((await toggle.count()) && (await toggle.isVisible())) await toggle.click();
    target = navigation.locator(selector);
  }
  if (!(await target.count())) return false;
  await expect(target.first(), `Sidebar view ${name} should be visible`).toBeVisible({ timeout: 15_000 });
  await target.first().click();
  await waitForMainViewReady(page, name);
  return true;
}

async function waitForMainViewReady(page: Page, context: string) {
  await expect(page.getByLabel("Loading view"), `${context} loading fallback should finish`).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator("main h1, main h2, main h3").first(), `${context} should render a heading`).toBeVisible({ timeout: 15_000 });
}

async function openMainView(page: Page, name: string) {
  const backToChat = settingsReturnButton(page);
  if (name !== "Settings" && (await backToChat.count())) {
    await backToChat.click();
  }

  if (name === "Agent" || name === "Workbench") {
    await page.getByRole("navigation").getByRole("button", { name: viewLabel("Agent"), exact: true }).click();
    await waitForMainViewReady(page, name);
    return;
  }

  if (name === "Settings") {
    await openSettings(page);
    await waitForMainViewReady(page, name);
    return;
  }

  if (await openMainViewById(page, name)) return;

  if (name === "Sessions") {
    const sessionsButton = page.getByRole("button").filter({ hasText: viewLabel("Sessions") }).first();
    await expect(sessionsButton, "Sessions sidebar button should be visible").toBeVisible({ timeout: 15_000 });
    await sessionsButton.click();
    await waitForMainViewReady(page, name);
    return;
  }

  if (WORKFLOW_ENTRY_VIEWS.has(name)) {
    await page.getByRole("navigation").getByRole("button", { name: viewLabel("Workflows"), exact: true }).click();
    await clickShortcutByLabel(page, viewLabel(name));
    await waitForMainViewReady(page, name);
    return;
  }

  if (SETTINGS_MODEL_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "模型配置", exact: true }).click();
    await clickShortcutByLabel(page, "打开模型配置页");
    return;
  }

  if (SETTINGS_MCP_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "MCP 管理入口", exact: true }).click();
    await clickShortcutByLabel(page, "打开 MCP 管理页");
    return;
  }

  if (SETTINGS_ADVANCED_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "高级诊断入口", exact: true }).click();
    await clickShortcutByLabel(page, viewLabel(name));
    return;
  }

  const label = viewLabel(name);
  const navigationButton = page.getByRole("navigation").getByRole("button", { name: label, exact: true });
  const navigationButtonCount = await navigationButton.count();
  if (navigationButtonCount) {
    await navigationButton.first().click();
    await waitForMainViewReady(page, name);
    return;
  }
  const navigationTextButton = page.getByRole("navigation").getByRole("button").filter({ hasText: label });
  const navigationTextButtonCount = await navigationTextButton.count();
  if (navigationTextButtonCount) {
    await navigationTextButton.first().click();
    await waitForMainViewReady(page, name);
    return;
  }
  for (const groupName of ["高级金融", "高级运维", "旧入口 / 高级诊断"]) {
    if (await openCollapsedNavGroup(page, groupName, label)) {
      await waitForMainViewReady(page, name);
      return;
    }
  }
  await page.getByRole("button", { name: label, exact: true }).click();
  await waitForMainViewReady(page, name);
}

async function openCapabilityTab(page: Page, name: string) {
  const tab = page.locator(".capabilities-tabs").getByRole("button", { name: tabLabel(name), exact: true });
  await expect(tab, `Capability tab ${name} should be visible`).toBeVisible({ timeout: 15_000 });
  await tab.click();
  await expect(tab, `Capability tab ${name} should become active`).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
  await waitForMainViewReady(page, `Capabilities / ${name}`);
}

interface FrontendControl {
  tag: string;
  name: string;
  disabled: boolean;
  placeholder: string;
  className: string;
  outerHTML: string;
  parentText: string;
  rect: { x: number; y: number; width: number; height: number };
}

interface FrontendInventory {
  page: string;
  viewport: string;
  headings: string[];
  controls: FrontendControl[];
  summary: {
    controlCount: number;
    buttonCount: number;
    inputCount: number;
    disabledCount: number;
    overflowX: boolean;
    mojibakeCount: number;
    textOverflow: Array<{ tag: string; text: string; scrollWidth: number; clientWidth: number }>;
    nestedCardCount: number;
    sidebarMainOverlap: boolean;
    oversizedRadius: Array<{ tag: string; text: string; radius: string }>;
    tinyButtons: string[];
  };
}

interface MatrixReport {
  generated_at: string;
  mode: "mock_safe";
  command_results: string[];
  pages: FrontendInventory[];
  actions: Array<{ page: string; control: string; result: string; note?: string }>;
  gated: Array<{ page: string; control: string; result: string; note?: string }>;
  layout: Array<{ page: string; viewport: string; status: string; checks: FrontendInventory["summary"] }>;
  screenshots: string[];
  assumptions: string[];
}

function uniqueNames(items: FrontendControl[]): string[] {
  return Array.from(new Set(items.map((item) => item.name).filter(Boolean))).sort();
}

async function collectMainInventory(page: Page, pageName: string): Promise<FrontendInventory> {
  return page.locator("body").evaluate((body, label) => {
    const visible = (element: Element) => {
      const closedDetails = element.closest("details:not([open])");
      if (closedDetails && !element.closest("summary")) return false;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const textOf = (element: Element) => {
      const input = element as HTMLInputElement;
      const labelled = "labels" in input && input.labels?.[0] ? input.labels[0].innerText : "";
      return (
        element.getAttribute("aria-label") ||
        element.getAttribute("title") ||
        labelled ||
        (element as HTMLElement).innerText ||
        input.value ||
        input.placeholder ||
        input.name ||
        input.id ||
        element.tagName
      )
        .replace(/\s+/g, " ")
        .trim();
    };
    const main = body.querySelector("main") || body;
    const controls = Array.from(main.querySelectorAll("button,input,textarea,select,a,[role='button'],[role='tab']"))
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const input = element as HTMLInputElement;
        return {
        tag: element.tagName.toLowerCase(),
        name: textOf(element).slice(0, 140),
        disabled: Boolean(input.disabled) || element.getAttribute("aria-disabled") === "true",
        placeholder: input.placeholder || "",
        className: String((element as HTMLElement).className || ""),
        outerHTML: (element as HTMLElement).outerHTML.slice(0, 260),
        parentText: ((element.parentElement as HTMLElement | null)?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 260),
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
            height: Math.round(rect.height)
          }
        };
      });
    const headings = Array.from(main.querySelectorAll("h1,h2,h3"))
      .filter(visible)
      .map((heading) => (heading as HTMLElement).innerText.replace(/\s+/g, " ").trim())
      .slice(0, 12);
    const bodyText = body.textContent || "";
    const mojibakeCount = ["锟", "�", "脙", "脗", "閿", "焲", "莽", "猫", "茅"].reduce(
      (count, marker) => count + bodyText.split(marker).length - 1,
      0
    );
    const textOverflow = Array.from(main.querySelectorAll("button,.capability-section,.metric-card,.field-row,.settings-row,.job-row,.tool-row,.event-card"))
      .filter(visible)
      .filter((element) => (element as HTMLElement).scrollWidth > (element as HTMLElement).clientWidth + 2)
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        text: textOf(element).slice(0, 120),
        scrollWidth: (element as HTMLElement).scrollWidth,
        clientWidth: (element as HTMLElement).clientWidth
      }))
      .slice(0, 20);
    const nestedCardCount = Array.from(main.querySelectorAll(".capability-section .capability-section, .metric-card .metric-card, .card .card")).filter(visible).length;
    const sidebar = body.querySelector(".sidebar");
    const mainRect = main.getBoundingClientRect();
    const sidebarRect = sidebar?.getBoundingClientRect();
    const sidebarMainOverlap = Boolean(
      sidebarRect &&
        sidebarRect.width > 0 &&
        mainRect.width > 0 &&
        mainRect.left < sidebarRect.right - 1 &&
        mainRect.right > sidebarRect.left + 1 &&
        mainRect.top < sidebarRect.bottom - 1 &&
        mainRect.bottom > sidebarRect.top + 1
    );
    const oversizedRadius = Array.from(main.querySelectorAll("button,.capability-section,.metric-card,.capability-card,.event-card,.job-row"))
      .filter(visible)
      .map((element) => ({ element, radius: getComputedStyle(element).borderRadius }))
      .filter(({ radius }) => parseFloat(radius) > 12)
      .map(({ element, radius }) => ({ tag: element.tagName.toLowerCase(), text: textOf(element).slice(0, 100), radius }))
      .slice(0, 20);
    const tinyButtons = controls
      .filter((control) => control.tag === "button" && (control.rect.width < 28 || control.rect.height < 24))
      .map((control) => control.name);
    return {
      page: label,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      headings,
      controls,
      summary: {
        controlCount: controls.length,
        buttonCount: controls.filter((control) => control.tag === "button" || control.tag === "a").length,
        inputCount: controls.filter((control) => ["input", "textarea", "select"].includes(control.tag)).length,
        disabledCount: controls.filter((control) => control.disabled).length,
        overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
        mojibakeCount,
        textOverflow,
        nestedCardCount,
        sidebarMainOverlap,
        oversizedRadius,
        tinyButtons
      }
    };
  }, pageName);
}

function expectCleanInventory(inventory: FrontendInventory) {
  expect(inventory.headings.length, `${inventory.page} should expose visible headings`).toBeGreaterThan(0);
  expect(inventory.summary.overflowX, `${inventory.page} has horizontal overflow`).toBe(false);
  expect(inventory.summary.mojibakeCount, `${inventory.page} has mojibake text`).toBe(0);
  expect(inventory.summary.textOverflow, `${inventory.page} has clipped text`).toEqual([]);
  expect(inventory.summary.nestedCardCount, `${inventory.page} nests cards inside cards`).toBe(0);
  expect(inventory.summary.sidebarMainOverlap, `${inventory.page} sidebar overlaps main workspace`).toBe(false);
  expect(inventory.summary.oversizedRadius, `${inventory.page} uses oversized operational card/button radii`).toEqual([]);
  expect(inventory.summary.tinyButtons, `${inventory.page} has too-small buttons`).toEqual([]);
}

function assertMainButtonCoverage(
  inventory: FrontendInventory,
  covered: string[],
  options: { structural?: string[]; gated?: string[]; allowedPrefixes?: string[] } = {}
) {
  const allowed = new Set(
    [...covered, ...(options.structural || []), ...(options.gated || [])].flatMap((name) => [
      name,
      controlLabel(name),
      tabLabel(name),
      viewLabel(name)
    ])
  );
  const allowedPrefixes = (options.allowedPrefixes || []).flatMap((prefix) => [
    prefix,
    controlLabel(prefix),
    tabLabel(prefix),
    viewLabel(prefix)
  ]);
  const visibleButtonControls = inventory.controls.filter((control) => control.tag === "button" || control.tag === "a");
  const visibleButtonNames = uniqueNames(visibleButtonControls);
  const missing = visibleButtonNames
    .filter((name) => !allowed.has(name) && !allowedPrefixes.some((prefix) => name.startsWith(prefix)))
    .map((name) => {
      const control = visibleButtonControls.find((item) => item.name === name);
      return {
        name,
        className: control?.className || "",
        outerHTML: control?.outerHTML || "",
        parentText: control?.parentText || "",
        rect: control?.rect,
      };
    });
  expect(missing, `${inventory.page} has visible buttons without matrix classification`).toEqual([]);
}

async function recordInventory(report: MatrixReport, page: Page, pageName: string) {
  await waitForMainViewReady(page, pageName);
  const inventory = await collectMainInventory(page, pageName);
  expectCleanInventory(inventory);
  report.pages.push(inventory);
  report.layout.push({ page: pageName, viewport: inventory.viewport, status: "passed", checks: inventory.summary });
  return inventory;
}

async function clickAndRecord(
  report: MatrixReport,
  page: Page,
  pageName: string,
  buttonName: string,
  expectedText?: string,
  scope = page.locator("body")
) {
  const actualName = controlLabel(buttonName);
  const button = scope.getByRole("button", { name: actualName, exact: true });
  await expect(button, `${pageName} ${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${pageName} ${buttonName} should be enabled`).toBeEnabled();
  await button.click();
  if (expectedText) {
    const visibleExpectedText = expectedTextLabel(expectedText);
    await expect
      .poll(async () => page.locator("body").evaluate((body) => (body as HTMLElement).innerText), {
        message: `${pageName} should show ${visibleExpectedText}`,
        timeout: 7_500
      })
      .toContain(visibleExpectedText);
  }
  report.actions.push({ page: pageName, control: buttonName, result: "clicked", note: expectedText });
}

async function expectDisabledAndRecord(report: MatrixReport, page: Page, pageName: string, buttonName: string, note?: string) {
  const actualName = controlLabel(buttonName);
  const button = page.getByRole("button", { name: actualName, exact: true });
  await expect(button, `${pageName} ${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${pageName} ${buttonName} should be disabled`).toBeDisabled();
  report.gated.push({ page: pageName, control: buttonName, result: "disabled", note });
}

test("MCP panel gates controls without token and executes resource, prompt, and OAuth calls with token", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);

  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "MCP");
  await expect(page.getByText(/缺少控制令牌|需要控制令牌/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Read MCP resource"), exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: controlLabel("Get MCP prompt"), exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: controlLabel("Start MCP OAuth flow"), exact: true })).toBeDisabled();

  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "MCP");
  await expect(page.getByText("完整 MCP 运行时数据已加载。")).toBeVisible();
  await expect(page.getByText("1 个已配置")).toBeVisible();
  await expect(page.getByText("agent_mcp_finance_demo_quote")).toBeVisible();
  await expect(page.getByText("可用资源 1 个")).toBeVisible();
  await expect(page.getByText("可用提示词 1 个")).toBeVisible();
  await expect(page.getByText("OAuth 条目 1 个")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await page.getByRole("button", { name: controlLabel("Read MCP resource"), exact: true }).click();
  await expect(page.getByText("quote resource ok")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await page.getByRole("button", { name: controlLabel("Get MCP prompt"), exact: true }).click();
  await expect(page.getByText("risk prompt ok")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await page.getByRole("button", { name: controlLabel("Start MCP OAuth flow"), exact: true }).click();
  await expect(page.getByText("oauth_required")).toBeVisible();
});

test("Strategy Factory panel renders success envelopes and structured degraded readiness", async ({ page }) => {
  await setupApiMocks(page, { factoryMode: "success" });
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Strategy Factory");

  await expect(page.getByRole("heading", { name: "调度器、运行和晋升评审" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "工厂状态" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "最近运行" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "评审快照" })).toBeVisible();
  await expect(page.getByText("已实现").first()).toBeVisible();

  await page.unroute(`${API_ORIGIN}/**`);
  await setupApiMocks(page, { factoryMode: "degraded" });
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("数据库已配置，但 strategy manager 返回错误。", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("STRATEGY_FACTORY_UNAVAILABLE").first()).toBeVisible();
  await expect(page.getByText("部分就绪").first()).toBeVisible();
});

test("Hermes capability tables expose v0.14 tool, platform, and feature parity with search and status filters", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Hermes");

  await expect(page.getByText("运行时为 AIASK-native。是否嵌入 vendor runtime：false")).toBeVisible();
  await expect(page.getByText("54 项")).toBeVisible();
  await expect(page.getByText("原始 Hermes payload")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hermes 工具映射" })).toBeVisible();

  const featureSection = page.locator(".capability-section").filter({ hasText: "功能映射" });
  const toolSection = page.locator(".capability-section").filter({ hasText: "Hermes 工具映射" });
  const platformSection = page.locator(".capability-section").filter({ hasText: "网关平台映射" });

  await expect(platformSection).toContainText("22 项");

  await featureSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("gateway_direct_delivery");
  await expect(featureSection).toContainText("agent_gateway_direct_deliver");

  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("discord_server");
  await expect(toolSection).toContainText("agent_discord_server");
  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("feishu_drive_list_comment_replies");
  await expect(toolSection).toContainText("agent_feishu_drive_list_comment_replies");
  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("rl_start_training");
  await expect(toolSection).toContainText("agent_rl_start_training");

  await toolSection.locator("select").selectOption("live_unverified");
  await expect(toolSection).toContainText("rl_start_training");
  await toolSection.locator("select").selectOption("missing");
  await expect(toolSection).toContainText("没有符合筛选条件的记录。");
});

test("AI Tests panel runs model status, smoke, model list, and Workbench response flow", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "AI Tests");

  await expect(page.getByRole("heading", { name: "gpt-5.4" })).toBeVisible();
  await expect(page.getByText("提供方 openai / 真实后端 / 基础 URL 已配置")).toBeVisible();
  await expect(page.getByText("API 密钥")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("sk-");

  await page.getByRole("button", { name: controlLabel("Run AI Smoke") }).click();
  await expect(page.getByText("AI_SMOKE_PASSED")).toBeVisible();
  await expect(page.locator(".capability-section").filter({ hasText: "冒烟测试结果" })).toContainText("AIASK model smoke ok.");
  await expect(page.getByText("123ms")).toBeVisible();

  await page.getByRole("button", { name: controlLabel("List Models") }).click();
  await expect(page.getByText("AI_MODELS_LOADED")).toBeVisible();
  const modelsSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "模型", exact: true }) });
  await expect(modelsSection).toContainText("gpt-5.4");
  await expect(modelsSection).toContainText("gpt-5.2");

  await openMainView(page, "Agent");
  await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("请只回复 AIASK_OK");
  await page.getByRole("button", { name: controlLabel("Run"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "智能体回复" })).toBeVisible();
  await expect(page.getByText("AIASK_OK").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.started" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.started" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.completed" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.delta" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.completed" }).first()).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Load run events for selected task"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "run.completed" }).first()).toBeVisible();
});

test("Capabilities workspace remains usable at desktop and narrow widths without raw JSON walls", async ({ page }) => {
  await setupApiMocks(page);
  await page.setViewportSize({ width: 1200, height: 829 });
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await expect(page.getByRole("heading", { name: "运行时评审", exact: true })).toBeVisible();
  await expect(page.getByText("Mock 数据").first()).toBeVisible();
  await expect(page.locator(".capabilities-workspace")).toBeVisible();
  await expect(page.locator(".capability-banner")).toContainText("后端对齐");
  await expect(page.locator(".raw-details").first()).toContainText("原始能力中心数据");

  await page.setViewportSize({ width: 980, height: 760 });
  await expect(page.locator(".capabilities-workspace")).toBeVisible();
  await expect(page.getByRole("button", { name: tabLabel("AI Tests") })).toBeVisible();
});

test("Market Temperature workspace renders localized cache panels and stays single-column on mobile", async ({ page }) => {
  await setupApiMocks(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openOverview(page);
  await openMainView(page, "Market Temperature");

  await expect(page.getByRole("heading", { name: "市场温度" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "缓存就绪" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "缓存历史" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行业历史" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "前向验证" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行业成分股" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Cache readiness");
  await expect(page.locator("main")).not.toContainText("Forward validation");
  await page.getByRole("button", { name: controlLabel("Update snapshot"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("MARKET_TEMPERATURE_LOADED"))).toBeVisible();

  const inventory = await collectMainInventory(page, "Market Temperature mobile");
  expectCleanInventory(inventory);
});

test("Data & Sync workspace renders database preflight and creates a gated sync intent in mock mode", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await expect(page.getByText("/tmp/akshare_mcp.sqlite3").first()).toBeAttached();
  await expect(page.getByRole("heading", { name: "数据闸门复核" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "agent_quant_data_gate" }).first()).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  await expect(page.getByText("data_sync.run_once", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Create approval intent") })).toBeDisabled();

  await setControlToken(page);
  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_INTENT_CREATED"))).toBeVisible();
  await expect(page.getByText("intent_e2e_approved_path", { exact: true })).toBeVisible();
});

test("Settings advanced management panels execute integrations, webhooks, RL, security, and automation flows", async ({ page }) => {
  test.setTimeout(90_000);
  const requestedPaths: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(API_ORIGIN)) {
      const url = new URL(request.url());
      requestedPaths.push(`${request.method()} ${url.pathname}`);
    }
  });

  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);

  await openSettingsSection(page, "应用集成");
  await clickSettingsPanelRefresh(page);
  await expect(page.getByText("INTEGRATIONS_LOADED")).toBeVisible();
  const connectorRow = page.locator(".connector-item").filter({ hasText: "tongdaxin" }).first();
  await connectorRow.getByRole("button", { name: "详情", exact: true }).click();
  await connectorRow.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText("连接器测试完成")).toBeVisible();
  await connectorRow.getByRole("button", { name: /生成配置片段/ }).click();
  await page.locator(".wizard-panel input").first().fill("119.147.212.81");
  await page.locator(".wizard-panel input").nth(1).fill("7709");
  await page.getByRole("button", { name: /下一步/ }).click();
  await page.getByRole("button", { name: /完成/ }).click();
  await expect(page.locator(".env-block")).toContainText("TDX_SERVER_IP=119.147.212.81");
  const platformRow = page.locator(".capability-section").filter({ hasText: "Gateway 平台" }).locator(".job-row").first();
  await platformRow.getByRole("button", { name: "健康", exact: true }).click();
  await platformRow.getByRole("button", { name: "启动", exact: true }).click();
  await platformRow.getByRole("button", { name: "停止", exact: true }).click();
  await page.locator("form").filter({ hasText: "消息发送预览" }).getByLabel("目标").fill("ops-room");
  await page.locator("form").filter({ hasText: "消息发送预览" }).getByRole("button", { name: "创建发送审批" }).click();
  await expect(page.getByText("GATEWAY_INTENT_CREATED")).toBeVisible();
  expect(requestedPaths).toContain("GET /v1/gateway/platforms/local/health");
  expect(requestedPaths).toContain("POST /v1/gateway/platforms/local/start");
  expect(requestedPaths).toContain("POST /v1/gateway/platforms/local/stop");

  await openSettingsSection(page, "Webhook");
  await clickSettingsPanelRefresh(page);
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).toContainText("Mock Webhook");
  await page.getByRole("button", { name: "创建 Webhook", exact: true }).click();
  expect(requestedPaths).toContain("POST /v1/webhooks");
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).toContainText("codex-mcp-test-webhook");
  await page.getByRole("button", { name: "创建触发审批", exact: true }).click();
  await expect(page.getByText("WEBHOOK_TRIGGER_INTENT_CREATED")).toBeVisible();
  const webhookRow = page.locator(".job-row").filter({ hasText: "Mock Webhook" }).first();
  await webhookRow.getByRole("button", { name: "删除", exact: true }).click();
  expect(requestedPaths).toContain("DELETE /v1/webhooks/webhook_fixture");
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).not.toContainText("Mock Webhook");

  await openSettingsSection(page, "学习 / RL");
  await clickSettingsPanelRefresh(page);
  await expect(page.getByText("LEARNING_RL_LOADED")).toBeVisible();
  const configBox = page.locator(".capability-section").filter({ hasText: "RL 配置" }).locator("textarea");
  await configBox.fill("{");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(page.getByText("RL_CONFIG_JSON_INVALID")).toBeVisible();
  await configBox.fill("{\"max_steps\":5}");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("updated");
  const proposalRow = page.locator(".job-row").filter({ hasText: "Mock 学习建议" }).first();
  await proposalRow.getByRole("button", { name: "应用", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("applied");
  await page.getByRole("button", { name: "启动训练", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("rl_fixture_new");
  const runRow = page.locator(".job-row").filter({ hasText: "finance_safe_eval" }).first();
  await runRow.getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText("RL_RUN_DETAIL_LOADED")).toBeVisible();
  await runRow.getByRole("button", { name: "结果", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("reward");
  await runRow.getByRole("button", { name: "日志", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("mock rl log");
  await runRow.getByRole("button", { name: /停止/ }).click();
  await expect(page.locator(".raw-details")).toContainText("stopped");

  await openSettingsSection(page, "安全扫描");
  await page.getByLabel("文本片段").fill("password=secret\nAIASK_AGENT_CONTROL_TOKEN=token");
  await page.getByRole("button", { name: "运行扫描", exact: true }).click();
  await expect(page.getByText("SECURITY_SCAN_COMPLETED")).toBeVisible();
  await expect(page.locator(".raw-details")).toContainText("[redacted]");
  await expect(page.locator(".raw-details")).not.toContainText("password=secret");
  await expect(page.locator(".raw-details")).not.toContainText("AIASK_AGENT_CONTROL_TOKEN=token");

  await openSettingsSection(page, "股票数据源");
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"))).toBeVisible();
  await page.getByRole("button", { name: /DuckDuckGo fallback/ }).click();
  await page.getByRole("button", { name: "调用搜索", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("WEB_SEARCH_PASSED"))).toBeVisible();
  await expect(page.locator(".raw-details")).toContainText("[redacted]");
  await expect(page.locator(".raw-details")).not.toContainText("mock-stock-token");

  await openSettingsSection(page, "自动化管理");
  await clickSettingsPanelRefresh(page);
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" }).first();
  await managedJobRow.getByRole("button", { name: /查看任务/ }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "已选任务" })).toContainText("run_job_e2e");
  await managedJobRow.getByRole("button", { name: /运行任务/ }).click();
  await expect(page.locator(".capability-section").filter({ hasText: "运行输出" })).toContainText("job ok");
  await managedJobRow.getByRole("button", { name: /删除任务/ }).click();
  await expect(page.locator(".capability-section").filter({ hasText: "运行输出" })).toContainText("deleted");
});

test("Quant Research workspace explains staged blockers and next actions in mock mode", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await openMainView(page, "Quant Research");
  await expect(page.getByRole("heading", { name: "数据、因子、回测与组合风险" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "阶段结论与下一步" })).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Run research") }).click();
  await expect(page.getByText("RESEARCH_RUN_CREATED")).toBeVisible();
  await expect(page.getByText("research_e2e_quant_1", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("LOCAL_DATABASE_REQUIRED").first()).toBeVisible();
  await expect(page.getByText("配置可写 SQLite 数据库并完成行情同步，然后重新运行研究。")).toBeVisible();
  await expect(page.getByText("数据闸门 原始证据")).toBeVisible();
});

test("Unified control console opens every primary page and exercises safe mock controls", async ({ page }) => {
  test.setTimeout(120_000);
  await setupApiMocks(page);
  await openOverview(page);

  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await setControlToken(page);

  await openMainView(page, "Agent");
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Hermes full") }).click();
  await expect(page.getByRole("button", { name: controlLabel("Hermes full") })).toHaveAttribute("aria-pressed", "true");

  await openMainView(page, "Models");
  await expect(page.getByRole("heading", { name: "LLM 提供方、模型获取与测试" })).toBeVisible();
  const providerSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "已配置提供方" }) });
  await expect(providerSection).toBeVisible();
  await expect(providerSection.locator("strong", { hasText: "openai" }).first()).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("MODEL_STATUS_LOADED"))).toBeVisible();

  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "MCP");
  await expandAdvancedMcpOperations(page);
  await expect(page.getByRole("heading", { name: "连接器评审队列" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Discover or refresh MCP server") }).click();
  await expect(page.locator("body")).toContainText("finance-demo");
  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await page.getByRole("button", { name: controlLabel("Read MCP resource") }).click();
  await expect(page.getByText("quote resource ok")).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await page.getByRole("button", { name: controlLabel("Get MCP prompt") }).click();
  await expect(page.getByText("risk prompt ok")).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await page.getByRole("button", { name: controlLabel("Start MCP OAuth flow") }).click();
  await expect(page.getByText("oauth_required")).toBeVisible();

  await openMainView(page, "Skills");
  await expect(page.getByRole("heading", { name: "已安装 1 个技能" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("risk-review Risk review") }).click();
  await page.getByRole("button", { name: "应用到对话" }).click();
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toHaveValue(/risk-review/);
  await openSettings(page);
  await page.getByRole("button", { name: "技能管理", exact: true }).click();
  const skillControl = page.locator(".capability-section").filter({ hasText: "安装或更新技能" });
  const skillResult = page.locator(".capability-section").filter({ hasText: "结果" });
  await skillControl.getByRole("textbox").first().fill("e2e-skill");
  await page.getByRole("button", { name: controlLabel("Install") }).click();
  await expect(skillResult).toContainText("installed");
  await page.getByRole("button", { name: controlLabel("Update") }).click();
  await expect(skillResult).toContainText("updated");
  await page.getByRole("button", { name: controlLabel("Delete") }).click();
  await expect(skillResult).toContainText("deleted");

  await openMainView(page, "Automation");
  await expect(page.getByRole("heading", { name: "AI 自动化任务" })).toBeVisible();
  const automationResult = page.locator(".capability-section").filter({ hasText: "运行输出" });
  await page.getByRole("button", { name: controlLabel("Create job") }).click();
  await expect(automationResult).toContainText("created");
  const jobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await jobRow.getByRole("button", { name: controlLabel("Inspect job 每日研究监控") }).click();
  await jobRow.getByRole("button", { name: controlLabel("Pause job 每日研究监控") }).click();
  await expect(automationResult).toContainText("updated");
  await jobRow.getByRole("button", { name: controlLabel("Run job 每日研究监控") }).click();
  await expect(automationResult).toContainText("completed");
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  await expect(page.getByRole("heading", { name: "自动化管理" }).first()).toBeVisible();
  const managedAutomationResult = page.locator(".capability-section").filter({ hasText: "运行输出" });
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await expect(managedJobRow.getByRole("button", { name: controlLabel("Delete job 每日研究监控") })).toHaveCount(1);
  await managedJobRow.getByRole("button", { name: controlLabel("Delete job 每日研究监控") }).click();
  await expect(managedAutomationResult).toContainText("deleted");

  await openMainView(page, "Strategy Factory");
  await expect(page.getByRole("heading", { name: "调度器、运行和晋升评审" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText(expectedTextLabel("STRATEGY_FACTORY_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Factor Factory");
  await expect(page.getByRole("heading", { name: "因子挖掘与活跃池" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText(expectedTextLabel("FACTOR_RUN_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText(expectedTextLabel("FACTOR_MAINTENANCE_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Incubation");
  await expect(page.getByRole("heading", { name: "生命周期与命中率控制" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Run intent"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_RUN_ONCE_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Dry-run intent") }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_DRY_RUN_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_MAINTENANCE_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Local User");
  await expect(page.getByRole("heading", { name: "画像与本地数据范围" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "记忆状态" })).toBeVisible();
  await expect(page.getByText("Agent 记忆")).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Save local profile") }).click();
  await expect(page.getByText(expectedTextLabel("LOCAL_PROFILE_SAVED"))).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await page.getByRole("button", { name: controlLabel("Search"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("USER_DATA_SEARCHED"))).toBeVisible();

  await openMainView(page, "Tools");
  await expect(page.getByRole("heading", { name: "可用操作与安全探测" })).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("Search tools")).fill("factory");
  await expect(page.getByText("agent_factory_status")).toBeVisible();

  await openMainView(page, "Capabilities");
  await expect(page.getByRole("heading", { name: "运行时评审", exact: true })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh capability review") }).click();
  await expect(page.getByText("Mock 数据").first()).toBeVisible();
  await openCapabilityTab(page, "Connectors");
  await expect(page.getByRole("heading", { name: "应用绑定与集成" })).toBeVisible();
  await openCapabilityTab(page, "Plugins");
  await expect(page.getByRole("heading", { name: "原生插件与技能包治理" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Test plugin audit-plugin"), exact: true }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");
  await page.getByRole("button", { name: controlLabel("Disable plugin audit-plugin") }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");

  await openMainView(page, "Event Console");
  await expect(page.getByRole("heading", { name: "生命周期、风险与孵化事件" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("EVENTS_LOADED"))).toBeVisible();

  await openMainView(page, "Diagnostics");
  await expect(page.getByRole("heading", { name: "Hermes 原生对齐" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("系统健康中心")).toBeVisible();

  await openMainView(page, "Agent Status");
  await expect(page.getByRole("heading", { name: "运行状态" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("AGENT_STATUS_LOADED"))).toBeVisible();

  await openMainView(page, "Settings");
  await expect(page.getByRole("heading", { name: "设置中心" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await page.getByRole("button", { name: "模型配置", exact: true }).click();
  await expect(page.getByText("进入模型页选择提供方")).toBeVisible();
  await page.getByRole("button", { name: "股票数据源", exact: true }).click();
  await expect(page.getByText("配置行情、K 线、基本面和搜索类数据源")).toBeVisible();
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"))).toBeVisible();
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Save profile") }).click();
  await expect(page.locator("label.settings-row").filter({ hasText: "画像名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await settingsReturnButton(page).click();
});

test("Full frontend matrix inventories every page, classifies every button, and validates Codex-style layout in mock mode", async ({ page }) => {
  test.setTimeout(180_000);
  await setupApiMocks(page);
  const report: MatrixReport = {
    generated_at: new Date().toISOString(),
    mode: "mock_safe",
    command_results: [
      "npm.cmd run typecheck: run separately by acceptance workflow",
      "npm.cmd test: run separately by acceptance workflow",
      "npm.cmd run test:e2e:mock: this matrix is part of the mock suite"
    ],
    pages: [],
    actions: [],
    gated: [],
    layout: [],
    screenshots: [],
    assumptions: [
      "Mock API intercepts all http://127.0.0.1:8767 calls.",
      "State-changing controls are clicked only against the mock backend.",
      "Live Agent validation is limited to the optional read-only smoke test."
    ]
  };
  const reportDir = path.join(process.cwd(), "test-results", "full-frontend");
  await mkdir(reportDir, { recursive: true });

  await page.setViewportSize({ width: 1440, height: 960 });
  await openOverview(page);

  await page.screenshot({ path: path.join(reportDir, "desktop-workbench.png"), fullPage: true });
  report.screenshots.push(path.join(reportDir, "desktop-workbench.png"));

  const workbenchInventory = await recordInventory(report, page, "Workbench");
  await expect(page.getByRole("region", { name: "金融 Agent 安全链路" })).toBeVisible();
  await expect(page.getByText("现在可以复核什么")).toBeVisible();
  report.actions.push({ page: "Workbench", control: "金融 Agent 安全链路", result: "visible", note: "Workbench surfaces read-only mode, MCP, memory, financial manager, data, and factory navigation" });
  await clickAndRecord(report, page, "Workbench", "Sync Agent state", "AIASK_ONLINE");
  assertMainButtonCoverage(workbenchInventory, [
    "Sync Agent state",
    "Finance safe mode",
    "Finance safe",
    "Hermes full",
    "Run thread task",
    "打开会话：E2E session 已完成 · 2026-05-21 16:00",
    "查看运行：运行已完成 工具 0 次 · 审批 0 项 · 错误 0 个",
    ...WORKBENCH_SAFE_PATH_BUTTONS,
    "准备度",
    "Readiness",
    "Projects / Contexts",
    "Approvals",
    "Finance Lab",
    "Integrations",
    "Gateway",
    "Gateway gated",
    "Gateway 受限",
    "Plugins / Skills gated",
    "扩展 内部",
    "Extensions internal",
    "Open evidence",
    "source_e2e_run",
  ]);

  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  report.actions.push({ page: "Data & Sync gated", control: "Generate sync plan", result: "clicked", note: "plan generated without write intent" });
  await expectDisabledAndRecord(report, page, "Data & Sync gated", "Create approval intent", "control token required");

  await openMainView(page, "MCP");
  await expandAdvancedMcpOperations(page);
  await expectDisabledAndRecord(report, page, "MCP gated", "Register local MCP server", "control token required or already registered");
  await expectDisabledAndRecord(report, page, "MCP gated", "Discover or refresh MCP server", "control token required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Run MCP read-only smoke", "control token required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Read MCP resource", "control token and resource uri required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Get MCP prompt", "control token and prompt name required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Start MCP OAuth flow", "control token and server required");

  await openMainView(page, "Finance Lab");
  await expect(page.getByRole("heading", { name: "工厂接力总览" })).toBeVisible();
  await expect(page.locator("body")).toContainText("因子工厂");
  await expect(page.locator("body")).toContainText("策略工厂");
  await expect(page.locator("body")).toContainText("孵化工厂");

  await openMainView(page, "Skills");
  await expect(page.getByText("需要控制令牌", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Install"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Update"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Delete"), exact: true })).toHaveCount(0);
  report.gated.push(
    { page: "Skills gated", control: "Install", result: "absent", note: "control form hidden until authorized" },
    { page: "Skills gated", control: "Update", result: "absent", note: "control form hidden until authorized" },
    { page: "Skills gated", control: "Delete", result: "absent", note: "control form hidden until authorized" }
  );

  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Plugins");
  await expect(page.getByRole("button", { name: controlLabel("Disable"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Test tool"), exact: true })).toHaveCount(0);
  report.gated.push(
    { page: "Plugins gated", control: "Disable", result: "absent", note: "plugin rows hidden until authorized" },
    { page: "Plugins gated", control: "Test tool", result: "absent", note: "plugin rows hidden until authorized" }
  );

  await setControlToken(page);

  await openMainView(page, "Agent");
  const agentInventory = await recordInventory(report, page, "Agent");
  await clickAndRecord(report, page, "Agent", "Sync Agent state", "AIASK_ONLINE");
  await clickAndRecord(report, page, "Agent", "Hermes full");
  await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("请只回复 AIASK_OK");
  await clickAndRecord(report, page, "Agent", "Run", "AIASK_OK");
  await clickAndRecord(report, page, "Agent inspector", "Load run events for selected task", "run.completed");
  assertMainButtonCoverage(agentInventory, [
    "Sync Agent state",
    "Finance safe mode",
    "Finance safe",
    "Hermes full",
    "Hermes full mode",
    "Run thread task",
    "打开会话：E2E session 已完成 · 2026-05-21 16:00",
    "查看运行：运行已完成 工具 0 次 · 审批 0 项 · 错误 0 个",
    ...WORKBENCH_SAFE_PATH_BUTTONS,
    "准备度",
    "Readiness",
    "Projects / Contexts",
    "Approvals",
    "Finance Lab",
    "Integrations",
    "Gateway",
    "Gateway ready",
    "Gateway 就绪",
    "插件 / 技能 就绪",
    "扩展 内部",
    "Extensions internal",
    "Open evidence",
    "source_e2e_run",
  ]);

  await openMainView(page, "Models");
  const modelsInventory = await recordInventory(report, page, "Models");
  const matrixProviderSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "已配置提供方" }) });
  await expect(matrixProviderSection).toBeVisible();
  await expect(matrixProviderSection.locator("strong", { hasText: "openai" }).first()).toBeVisible();
  report.actions.push({ page: "Models", control: "Provider status", result: "visible", note: "modelProviderStatus payload visible" });
  await clickAndRecord(report, page, "Models", "Refresh", "MODEL_STATUS_LOADED");
  await clickAndRecord(report, page, "Models", "获取模型", "MODELS_LOADED");
  await clickAndRecord(report, page, "Models", "测试模型", "AIASK model smoke ok.");
  assertMainButtonCoverage(modelsInventory, ["Refresh", "保存配置", "获取模型", "测试模型"], {
    allowedPrefixes: [
      "OpenAI",
      "DeepSeek",
      "通义千问 / DashScope 北京",
      "Qwen / DashScope 美国弗吉尼亚",
      "Anthropic Claude",
      "自定义 OpenAI 兼容",
      "本地 Mock"
    ]
  });

  await openMainView(page, "Readiness");
  const readinessInventory = await recordInventory(report, page, "Readiness");
  await expect(page.getByRole("heading", { name: "真实金融流程前置检查" })).toBeVisible();
  await expect(page.getByText("1. 模式与模型")).toBeVisible();
  await expect(page.getByText("2. MCP 与连接器")).toBeVisible();
  await expect(page.getByText("3. 记忆与搜索")).toBeVisible();
  await expect(page.getByText("4. 金融 Agent 流程")).toBeVisible();
  await expect(page.getByText("5. 数据与量化研究")).toBeVisible();
  await expect(page.getByText("6. 工厂接力")).toBeVisible();
  report.actions.push({ page: "Readiness", control: "运行前检查", result: "visible", note: "mode, MCP, memory, financial agent, data, and factory relay path visible" });
  assertMainButtonCoverage(readinessInventory, [
    "Refresh",
    "刷新完整控制台"
  ], {
    allowedPrefixes: [
      "前往",
      "打开设置",
      "打开MCP / 连接器",
      "打开本地用户 / 记忆",
      "打开金融经理台",
      "打开数据",
      "打开金融实验室"
    ]
  });

  await openMainView(page, "Data & Sync");
  const dataInventory = await recordInventory(report, page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据闸门复核" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "agent_quant_data_gate" }).first()).toBeVisible();
  report.actions.push({ page: "Data & Sync", control: "Data gate evidence", result: "visible", note: "agent_quant_data_gate read-only result visible" });
  await page.locator("label.field-row").filter({ hasText: "证券代码" }).locator("textarea").fill("600519, 000001");
  await clickAndRecord(report, page, "Data & Sync", "Refresh", "DATA_STATUS_LOADED");
  await clickAndRecord(report, page, "Data & Sync", "Generate sync plan", "SYNC_PLAN_READY");
  const dataInventoryWithPlan = await collectMainInventory(page, "Data & Sync with plan");
  await clickAndRecord(report, page, "Data & Sync", "Create approval intent", "SYNC_INTENT_CREATED");
  assertMainButtonCoverage(dataInventoryWithPlan, ["Refresh", "Generate sync plan", "Create approval intent"]);
  assertMainButtonCoverage(dataInventory, ["Refresh", "Generate sync plan"]);

  await openMainView(page, "Financial Manager");
  const financialManagerInventory = await recordInventory(report, page, "Financial Manager");
  await expect(page.getByRole("heading", { name: "金融 Agent 只读工作流" })).toBeVisible();
  await clickAndRecord(report, page, "Financial Manager", "Run read-only workflow", "FINANCIAL_WORKFLOW_DONE");
  await expect(page.getByText("agent_portfolio_risk").first()).toBeVisible();
  await expect(page.getByText("agent_analyze_stock").first()).toBeVisible();
  await expect(page.getByText("agent_quant_data_gate").first()).toBeVisible();
  await expect(page.getByText("agent_session_search").first()).toBeVisible();
  await expect(page.getByText("agent_memory_search").first()).toBeVisible();
  await expect(page.locator("body")).toContainText("AIASK_OK search result");
  await expect(page.locator("body")).toContainText("mock memory hit");
  await expect(page.locator("body")).toContainText("quote resource ok");
  await expect(page.locator("body")).toContainText("risk prompt ok");
  report.actions.push({ page: "Financial Manager", control: "Read-only Agent workflow evidence", result: "visible", note: "portfolio, quant, session search, memory search, and MCP evidence visible" });
  await page.getByRole("button", { name: "市场与研究", exact: true }).click();
  await page.getByRole("button", { name: /个股分析/ }).click();
  await page.getByLabel("stock analysis code").fill("300750");
  await page.getByLabel("include stock decision").check();
  await clickAndRecord(report, page, "Financial Manager", "Run query", "mock_watch");
  await expect(page.locator("body")).toContainText("300750");
  await expect(page.locator("body")).toContainText("observe_only");
  const stockSummary = page.getByLabel("stock analysis summary");
  const stockSummaryValues = await stockSummary.locator(".metric-card strong").filter({ hasText: /mock_watch|observe_only/ }).all();
  expect(stockSummaryValues).toHaveLength(2);
  for (const value of stockSummaryValues) {
    const box = await value.evaluate((element) => {
      const style = window.getComputedStyle(element);
      const lineHeight = Number.parseFloat(style.lineHeight);
      return { height: element.getBoundingClientRect().height, lineHeight: Number.isFinite(lineHeight) ? lineHeight : 24 };
    });
    expect(box.height).toBeLessThan(box.lineHeight * 1.35);
  }
  report.actions.push({ page: "Financial Manager", control: "Stock analysis query", result: "visible", note: "agent_analyze_stock read-only query accepts a stock code and renders summary evidence" });
  assertMainButtonCoverage(financialManagerInventory, ["Refresh", "Run read-only workflow", "Run query"], {
    allowedPrefixes: ["总览", "市场与研究", "风险与绩效", "组合与自选", "券商只读", "组合风险", "个股分析", "量化数据门禁", "创建组合意图", "实盘下单"]
  });

  await openMainView(page, "MCP");
  const mcpInventory = await recordInventory(report, page, "MCP");
  await clickAndRecord(report, page, "MCP", "Refresh", "连接器已加载");
  const firstConnector = page.locator(".connector-item").first();
  await firstConnector.getByRole("button", { name: controlLabel("Connector detail"), exact: true }).click();
  await expect(page.locator("body")).toContainText("连接器详情已加载");
  report.actions.push({ page: "MCP", control: "Connector detail", result: "clicked", note: "连接器详情已加载" });
  await firstConnector.getByRole("button", { name: controlLabel("Connector test"), exact: true }).click();
  await expect(page.locator("body")).toContainText("连接器测试完成");
  report.actions.push({ page: "MCP", control: "Connector test", result: "clicked", note: "连接器测试完成" });
  await expandAdvancedMcpOperations(page);
  await expectDisabledAndRecord(report, page, "MCP", "Register local MCP server", "already registered in mock");
  await clickAndRecord(report, page, "MCP", "Discover or refresh MCP server", "finance-demo");
  await clickAndRecord(report, page, "MCP", "Run MCP read-only smoke", "只读冒烟测试已完成");
  await expect(page.locator("body")).toContainText("quote resource ok");
  await expect(page.locator("body")).toContainText("risk prompt ok");
  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await clickAndRecord(report, page, "MCP", "Read MCP resource", "quote resource ok");
  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await clickAndRecord(report, page, "MCP", "Get MCP prompt", "risk prompt ok");
  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await clickAndRecord(report, page, "MCP", "Start MCP OAuth flow", "oauth_required");
  assertMainButtonCoverage(mcpInventory, [
    "Refresh",
    "Connector detail",
    "Connector test",
    "Register local MCP server",
    "Discover or refresh MCP server",
    "Run MCP read-only smoke",
    "Read MCP resource",
    "Get MCP prompt",
    "Start MCP OAuth flow",
    "Reauthorize"
  ]);

  await openMainView(page, "Skills");
  const skillsInventory = await recordInventory(report, page, "Skills");
  await clickAndRecord(report, page, "Skills", "risk-review Risk review");
  await page.getByRole("button", { name: "应用到对话" }).click();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toHaveValue(/risk-review/);
  report.actions.push({ page: "Skills", control: "应用到对话", result: "clicked", note: "recommended prompt copied to composer" });
  assertMainButtonCoverage(skillsInventory, [
    "Refresh",
    "risk-review Risk review",
    "应用到对话",
    "Install",
    "Update",
    "Delete",
    "Disable plugin audit-plugin",
    "Configure plugin audit-plugin",
    "Test plugin audit-plugin",
    "Test first plugin tool audit-plugin",
    "Load commands for plugin audit-plugin",
    "Save plugin"
  ]);

  await openSettings(page);
  await page.getByRole("button", { name: "技能管理", exact: true }).click();
  const skillsManagementInventory = await recordInventory(report, page, "Skills management");
  const skillSection = page.locator(".capability-section").filter({ hasText: "安装或更新技能" });
  await skillSection.getByRole("textbox").first().fill("e2e-skill");
  await clickAndRecord(report, page, "Skills management", "Install", "installed");
  await clickAndRecord(report, page, "Skills management", "Update", "updated");
  await clickAndRecord(report, page, "Skills management", "Delete", "deleted");
  assertMainButtonCoverage(skillsManagementInventory, ["Refresh", "risk-review Risk review", "Install", "Update", "Delete"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });

  await openMainView(page, "Automation");
  const automationInventory = await recordInventory(report, page, "Automation");
  await clickAndRecord(report, page, "Automation", "Refresh", "JOBS_LOADED");
  await clickAndRecord(report, page, "Automation", "Create job", "created");
  const jobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await clickAndRecord(report, page, "Automation", "Inspect job 每日研究监控", "每日研究监控", jobRow);
  await clickAndRecord(report, page, "Automation", "Pause job 每日研究监控", "updated", jobRow);
  await clickAndRecord(report, page, "Automation", "Run job 每日研究监控", "completed", jobRow);
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);
  assertMainButtonCoverage(automationInventory, ["Refresh", "Create job", "Inspect job 每日研究监控", "Pause job 每日研究监控", "Run job 每日研究监控"]);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  const automationManagementInventory = await recordInventory(report, page, "Automation management");
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await clickAndRecord(report, page, "Automation management", "Delete job 每日研究监控", "deleted", managedJobRow);
  assertMainButtonCoverage(automationManagementInventory, ["Refresh", "Create job", "Inspect job 每日研究监控", "Pause job 每日研究监控", "Run job 每日研究监控", "Delete job 每日研究监控"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });

  await openMainView(page, "Finance Lab");
  await expect(page.locator("body")).toContainText(expectedTextLabel("FACTORY_RELAY_LOADED"));
  const financeLabInventory = await recordInventory(report, page, "Finance Lab");
  await page.getByLabel(/我确认本次只读测试可读取/).check();
  await clickAndRecord(report, page, "Finance Lab", "Sync QMT read-only", "BROKER_SYNCED");
  await clickAndRecord(report, page, "Finance Lab", "刷新接力状态", "FACTORY_RELAY_LOADED");
  await expect(page.locator("body")).toContainText("20d momentum");
  await expect(page.locator("body")).toContainText("risk-review");
  await expect(page.locator("body")).toContainText("completed");
  assertMainButtonCoverage(financeLabInventory, [
    "Sync QMT read-only",
    "检查环境",
    "运行只读测试并生成分析",
    "刷新接力状态",
    "查看因子池",
    "打开策略评审",
    "查看孵化看板",
    "打开因子工厂",
    "打开策略工厂",
    "打开孵化工厂",
    "财务管理",
    "量化研究",
    "策略工厂",
    "因子工厂",
    "孵化工厂",
    "数据",
    "事件工厂"
  ], {
    allowedPrefixes: ["QMT / MiniQMT", "同花顺"]
  });
  await clickAndRecord(report, page, "Finance Lab", "查看因子池", "因子挖掘与活跃池");

  await openMainView(page, "Market Temperature");
  await expect(page.getByRole("heading", { name: "缓存就绪" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "前向验证" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Cache readiness");
  const marketTemperatureInventory = await recordInventory(report, page, "Market Temperature");
  await clickAndRecord(report, page, "Market Temperature", "Update snapshot", "MARKET_TEMPERATURE_LOADED");
  assertMainButtonCoverage(marketTemperatureInventory, ["Refresh", "Update snapshot"]);

  await openMainView(page, "Strategy Factory");
  const strategyInventory = await recordInventory(report, page, "Strategy Factory");
  await clickAndRecord(report, page, "Strategy Factory", "Refresh capability review", "Mock 数据");
  await clickAndRecord(report, page, "Strategy Factory", "Create run intent", "STRATEGY_FACTORY_INTENT_CREATED");
  await expect(page.locator("[aria-label='strategy factory intent summary']")).toContainText("intent_e2e_approved_path");
  await expect(page.locator("[aria-label='strategy factory intent summary']")).toContainText("agent_action_intent_create");
  assertMainButtonCoverage(strategyInventory, ["Refresh capability review", "Create run intent"], {
    structural: ["Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openMainView(page, "Factor Factory");
  const factorInventory = await recordInventory(report, page, "Factor Factory");
  await clickAndRecord(report, page, "Factor Factory", "Refresh", "FACTOR_FACTORY_LOADED");
  await clickAndRecord(report, page, "Factor Factory", "Create run intent", "FACTOR_RUN_INTENT_CREATED");
  await clickAndRecord(report, page, "Factor Factory", "Maintenance intent", "FACTOR_MAINTENANCE_INTENT_CREATED");
  assertMainButtonCoverage(factorInventory, ["Refresh", "Create run intent", "Maintenance intent"]);

  await openMainView(page, "Incubation");
  const incubationInventory = await recordInventory(report, page, "Incubation");
  await clickAndRecord(report, page, "Incubation", "Refresh", "INCUBATION_LOADED");
  await clickAndRecord(report, page, "Incubation", "Run intent", "INCUBATION_RUN_ONCE_INTENT_CREATED");
  await clickAndRecord(report, page, "Incubation", "Dry-run intent", "INCUBATION_DRY_RUN_INTENT_CREATED");
  await clickAndRecord(report, page, "Incubation", "Maintenance intent", "INCUBATION_MAINTENANCE_INTENT_CREATED");
  assertMainButtonCoverage(incubationInventory, ["Refresh", "Run intent", "Dry-run intent", "Maintenance intent"]);

  await openMainView(page, "Factory Events");
  await page.getByRole("tab", { name: "雷达", exact: true }).click();
  await expect(page.getByRole("heading", { name: "股票雷达观察池" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "北方稀土" }).first()).toBeVisible();
  const factoryEventsRadarInventory = await recordInventory(report, page, "Factory Events / Radar");
  await clickAndRecord(report, page, "Factory Events / Radar", "Refresh radar", "RADAR_LOADED");
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar run intent", "股票雷达运行 意图");
  await expect(page.getByRole("button", { name: controlLabel("Create radar run intent"), exact: true })).toBeEnabled();
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar push preview intent", "股票雷达推送预览 意图");
  await expect(page.getByRole("button", { name: controlLabel("Create radar push preview intent"), exact: true })).toBeEnabled();
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar schedule intent", "股票雷达调度预览 意图");
  await page.getByRole("tab", { name: "事件", exact: true }).click();
  await expect(page.getByRole("heading", { name: "当前生效的事件注入" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Pause"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "最近意图派发" })).toBeVisible();
  await expect(page.locator("main")).toContainText("意图 intent_e2e_approved_path 已确认");
  assertMainButtonCoverage(factoryEventsRadarInventory, [
    "Refresh",
    "刷新状态",
    "初始化 Bootstrap",
    "刷新暴露",
    "排空 outbox",
    "运行回归",
    "Refresh radar",
    "Create radar run intent",
    "Create radar push preview intent",
    "Create radar schedule intent"
  ], {
    structural: ["雷达", "事件", "创建", "预览", "血缘"]
  });

  await openMainView(page, "Local User");
  const userInventory = await recordInventory(report, page, "Local User");
  await expect(page.getByRole("heading", { name: "记忆状态" })).toBeVisible();
  report.actions.push({ page: "Local User", control: "Memory status", result: "visible", note: "memoryStatus payload visible" });
  await clickAndRecord(report, page, "Local User", "Refresh", "LOCAL_PROFILE_LOADED");
  await clickAndRecord(report, page, "Local User", "Save local profile", "LOCAL_PROFILE_SAVED");
  await expectDisabledAndRecord(report, page, "Local User", "Search", "query required");
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await clickAndRecord(report, page, "Local User", "Search", "USER_DATA_SEARCHED");
  await clickAndRecord(report, page, "Local User", "Preview Export/Delete", "USER_DATA_EXPORT_PREVIEWED");
  await clickAndRecord(report, page, "Local User", "Preview Aggregate Governance", "AGGREGATE_GOVERNANCE_PREVIEWED");
  assertMainButtonCoverage(userInventory, ["Refresh", "Load messages", "Save local profile", "Search", "Preview Export/Delete", "Preview Aggregate Governance"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Tools");
  const toolsInventory = await recordInventory(report, page, "Tools");
  await page.getByPlaceholder(placeholderLabel("Search tools")).fill("factory");
  await expect(page.getByText("agent_factory_status")).toBeVisible();
  report.actions.push({ page: "Tools", control: "Search tools input", result: "typed", note: "agent_factory_status visible" });
  assertMainButtonCoverage(toolsInventory, [], {
    allowedPrefixes: ["Fill example for agent_", "Run safe probe for agent_"],
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Capabilities");
  const capabilitiesInventory = await recordInventory(report, page, "Capabilities");
  await clickAndRecord(report, page, "Capabilities", "Refresh capability review", "Mock 数据");
  assertMainButtonCoverage(capabilitiesInventory, ["Refresh capability review"], {
    structural: ["Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Connectors");
  const connectorsInventory = await recordInventory(report, page, "Capabilities / Connectors");
  await clickAndRecord(report, page, "Capabilities / Connectors", "Refresh connectors", "CONNECTORS_LOADED");
  assertMainButtonCoverage(connectorsInventory, ["Refresh connectors"], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Hermes");
  const hermesInventory = await recordInventory(report, page, "Capabilities / Hermes");
  await page.locator(".capability-section").filter({ hasText: "Hermes 工具映射" }).getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("discord_server");
  await expect(page.getByText("agent_discord_server").first()).toBeVisible();
  report.actions.push({ page: "Capabilities / Hermes", control: "Hermes search and status filters", result: "typed", note: "agent_discord_server visible" });
  assertMainButtonCoverage(hermesInventory, [], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Plugins");
  const pluginsInventory = await recordInventory(report, page, "Capabilities / Plugins");
  await clickAndRecord(report, page, "Capabilities / Plugins", "Test plugin audit-plugin");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");
  await clickAndRecord(report, page, "Capabilities / Plugins", "Disable plugin audit-plugin");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");
  assertMainButtonCoverage(pluginsInventory, [
    "Disable plugin audit-plugin",
    "Configure plugin audit-plugin",
    "Test plugin audit-plugin",
    "Test first plugin tool audit-plugin",
    "Load commands for plugin audit-plugin",
    "Save plugin"
  ], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "AI Tests");
  const aiTestsInventory = await recordInventory(report, page, "Capabilities / AI Tests");
  await clickAndRecord(report, page, "Capabilities / AI Tests", "Refresh");
  await expect(page.getByRole("heading", { name: "gpt-5.4" })).toBeVisible();
  await clickAndRecord(report, page, "Capabilities / AI Tests", "Run AI Smoke", "AI_SMOKE_PASSED");
  await clickAndRecord(report, page, "Capabilities / AI Tests", "List Models", "AI_MODELS_LOADED");
  assertMainButtonCoverage(aiTestsInventory, ["Refresh", "Run AI Smoke", "List Models"], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openMainView(page, "Event Console");
  const eventInventory = await recordInventory(report, page, "Event Console");
  await page.getByPlaceholder(placeholderLabel("payload text")).fill("mock");
  await clickAndRecord(report, page, "Event Console", "Refresh", "EVENTS_LOADED");
  assertMainButtonCoverage(eventInventory, ["Refresh"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Diagnostics");
  await clickAndRecord(report, page, "Diagnostics", "Refresh", "系统健康中心");
  await page.locator(".subsystem-row").filter({ has: page.locator("summary", { hasText: "终端" }) }).locator("summary").click();
  await expect(page.getByText("local-powershell").first()).toBeVisible();
  const diagnosticsInventory = await recordInventory(report, page, "Diagnostics");
  await clickAndRecord(report, page, "Diagnostics", "Load terminal sessions", "TERMINAL_BACKEND_SESSIONS_LOADED");
  assertMainButtonCoverage(diagnosticsInventory, ["Refresh", "Load terminal sessions"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Agent Status");
  const agentStatusInventory = await recordInventory(report, page, "Agent Status");
  await clickAndRecord(report, page, "Agent Status", "Refresh", "AGENT_STATUS_LOADED");
  assertMainButtonCoverage(agentStatusInventory, ["Refresh"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Settings");
  const settingsInventory = await recordInventory(report, page, "Settings");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.locator("label.settings-row").filter({ hasText: "Agent 端点" }).locator("input").fill(API_ORIGIN);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  await page.locator("label.settings-row").filter({ hasText: "API 令牌" }).locator("input").fill("api-token-mock");
  await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(CONTROL_TOKEN);
  await clickAndRecord(report, page, "Settings", "Refresh");
  await page.getByRole("button", { name: "模型配置", exact: true }).click();
  await expect(page.getByText("进入模型页选择提供方")).toBeVisible();
  await page.getByRole("button", { name: "股票数据源", exact: true }).click();
  const stockDataSourcesInventory = await recordInventory(report, page, "Settings / Stock data sources");
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await clickAndRecord(report, page, "Settings / Stock data sources", "测试连接", expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"));
  await page.getByRole("button", { name: /DuckDuckGo fallback/ }).click();
  await clickAndRecord(report, page, "Settings / Stock data sources", "调用搜索", expectedTextLabel("WEB_SEARCH_PASSED"));
  assertMainButtonCoverage(stockDataSourcesInventory, ["Refresh", "打开官方文档", "保存数据源", "测试连接", "调用搜索"], {
    structural: SETTINGS_STRUCTURE_BUTTONS,
    allowedPrefixes: ["AKShare / AKTools", "Tushare Pro", "TongDaXin HQ", "DuckDuckGo HTML Search", "Tavily Search", "E2E AKShare", "Tushare 主账号", "DuckDuckGo fallback"]
  });
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Save profile");
  await expect(page.locator("label.settings-row").filter({ hasText: "画像名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Test connection", "AIASK_ONLINE");
  assertMainButtonCoverage(settingsInventory, ["Refresh", "Reset endpoint to default Agent endpoint", "Save profile", "Test connection"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });
  await settingsReturnButton(page).click();

  await page.setViewportSize({ width: 980, height: 760 });
  await openMainView(page, "Overview");
  const narrowOverview = await recordInventory(report, page, "Overview narrow");
  assertMainButtonCoverage(narrowOverview, ["Refresh"]);
  await page.screenshot({ path: path.join(reportDir, "narrow-overview.png"), fullPage: true });
  report.screenshots.push(path.join(reportDir, "narrow-overview.png"));

  await writeFile(path.join(reportDir, "playwright-full-matrix-report.json"), JSON.stringify(report, null, 2), "utf8");
});

async function liveBodyText(page: Page): Promise<string> {
  return page.locator("body").evaluate((body) => (body as HTMLElement).innerText);
}

async function expectLiveBodyToMatch(page: Page, pattern: RegExp, message: string, timeout = 10_000) {
  await expect
    .poll(async () => liveBodyText(page), { message, timeout })
    .toMatch(pattern);
}

async function clickLiveButtonWhenEnabled(page: Page, buttonName: string, timeout = 15_000) {
  const button = page.getByRole("button", { name: controlLabel(buttonName), exact: true });
  await expect(button, `${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${buttonName} should be enabled`).toBeEnabled({ timeout });
  await button.click();
}

async function clickLiveButtonIfEnabled(page: Page, buttonName: string) {
  const button = page.getByRole("button", { name: controlLabel(buttonName), exact: true }).first();
  if ((await button.count()) === 0) return false;
  await expect(button).toBeVisible();
  if (await button.isDisabled()) return false;
  await button.click();
  return true;
}

async function clickFirstVisibleButtonContaining(page: Page, text: string) {
  const button = page.getByRole("button").filter({ hasText: text }).first();
  if ((await button.count()) === 0) return false;
  await expect(button).toBeVisible();
  await button.click();
  return true;
}

async function openLastRawEvidencePanel(page: Page) {
  const panels = page.locator("main details.raw-evidence-panel, main details.raw-details");
  const count = await panels.count();
  if (!count) return false;
  const panel = panels.nth(count - 1);
  if ((await panel.getAttribute("open")) === null) {
    await panel.locator("summary").click();
  }
  return true;
}

async function expectNoLiveSecretLeak(page: Page) {
  await expect(page.locator("body")).not.toContainText(/(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}/);
  await expect(page.locator("body")).not.toContainText(/api[_-]?key\s*[:=]\s*[^,\s}]+/i);
}

async function assertLivePageHealth(page: Page, name: string, bodyPattern: RegExp, timeout = 30_000) {
  await openMainView(page, name);
  await expectLiveBodyToMatch(page, bodyPattern, `live ${name} should render expected domain content`, timeout);
  const inventory = await collectMainInventory(page, `Live ${name}`);
  expectCleanInventory(inventory);
  await expectNoLiveSecretLeak(page);
}

async function assertLiveSettingsSectionHealth(page: Page, sectionLabel: string, bodyPattern: RegExp, timeout = 30_000) {
  await openSettings(page);
  const settingsNav = page.getByRole("navigation", { name: "设置导航" });
  const sectionButton = settingsNav.getByRole("button", { name: sectionLabel, exact: true });
  await expect(sectionButton, `settings section ${sectionLabel} should be available`).toHaveCount(1);
  await sectionButton.click();
  await expectLiveBodyToMatch(page, bodyPattern, `live settings section ${sectionLabel} should render expected content`, timeout);
  const inventory = await collectMainInventory(page, `Live Settings / ${sectionLabel}`);
  expectCleanInventory(inventory);
  await expectNoLiveSecretLeak(page);
}

test.describe("optional live desktop smoke", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(process.env.AIASK_DESKTOP_RUN_LIVE !== "1", "set AIASK_DESKTOP_RUN_LIVE=1 and run a real backend on 127.0.0.1:8767");
  test.setTimeout(150_000);

  test("covers real backend model, Hermes, MCP, factory, financial, and status pages", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);

    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "AI Tests");
    await expect(page.locator(".capability-banner").filter({ hasText: tabLabel("AI Tests") })).toBeVisible();
    await clickLiveButtonWhenEnabled(page, "Run AI Smoke", 30_000);
    await expectLiveBodyToMatch(page, /AI_SMOKE_PASSED|aiask\.ai_smoke|true/, "live AI smoke result should render", 30_000);
    await clickLiveButtonWhenEnabled(page, "List Models", 30_000);
    await expectLiveBodyToMatch(page, /AI_MODELS_LOADED|mock-live-model|aiask_mock|"object":\s*"list"/, "live model list should render", 30_000);
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Agent");
    await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("Return exactly AIASK_LIVE_OK.");
    await page.getByRole("button", { name: controlLabel("Run"), exact: true }).click();
    await expectLiveBodyToMatch(page, /AIASK_LIVE_OK|run\.completed|model\.completed/, "live workbench response should render", 45_000);
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "Hermes");
    await expect(page.locator(".capability-section").first()).toBeVisible();
    await expectLiveBodyToMatch(page, /Hermes|agent_[a-z0-9_]+|baseline/i, "live Hermes capability tables should render", 30_000);

    await openMainView(page, "MCP");
    await expectLiveBodyToMatch(page, /MCP|not_registered|discovered|unconfigured|gated/i, "live MCP page should render a clear state", 30_000);
    await clickLiveButtonWhenEnabled(page, "Refresh", 30_000);
    await expectLiveBodyToMatch(page, /CONNECTORS_LOADED|杩炴帴鍣ㄥ凡鍔犺浇|connector|MCP/i, "live MCP connectors should refresh visibly", 30_000);
    const liveConnectorItems = page.locator(".connector-item");
    const liveConnectorCount = await liveConnectorItems.count();
    if (liveConnectorCount > 0) {
      const firstConnector = liveConnectorItems.first();
      const detailButton = firstConnector.getByRole("button", { name: controlLabel("Connector detail"), exact: true });
      if ((await detailButton.count()) === 1 && !(await detailButton.isDisabled())) {
        await detailButton.click();
        await expectLiveBodyToMatch(page, /CONNECTOR_DETAIL_LOADED|杩炴帴鍣ㄨ鎯呭凡鍔犺浇|connector_detail|configured|connected/i, "live connector detail should render", 30_000);
      }
      const testButton = firstConnector.getByRole("button", { name: controlLabel("Connector test"), exact: true });
      if ((await testButton.count()) === 1 && !(await testButton.isDisabled())) {
        await testButton.click();
        await expectLiveBodyToMatch(page, /CONNECTOR_TESTED|连接器测试完成|杩炴帴鍣ㄦ祴璇曞畬鎴?|connector\.test|last_test_status|passed|failed|disconnected|connected|未配置|就绪/i, "live connector test should render", 45_000);
      }
    }
    const ranMcpSmoke = await clickLiveButtonIfEnabled(page, "Run MCP read-only smoke");
    if (ranMcpSmoke) {
      await expectLiveBodyToMatch(page, /MCP_SMOKE_DONE|鍙鍐掔儫娴嬭瘯宸插畬鎴?|success|blocked|failed|\/v1\/mcp\/resources\/read|\/v1\/mcp\/prompts\/get|MCP/i, "live MCP read-only smoke should finish visibly", 45_000);
    }
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Strategy Factory");
    await expect(page.locator(".capability-card")).toHaveCount(3, { timeout: 30_000 });
    await expectLiveBodyToMatch(page, /strategy_factory|agent_factory_status|CONTROL_TOKEN_REQUIRED|DESKTOP_TOOL_UNAVAILABLE|true|false/, "live Strategy Factory cards should render structured envelopes", 30_000);
    const createdFactoryIntent = await clickLiveButtonIfEnabled(page, "Create run intent");
    if (createdFactoryIntent) {
      await expectLiveBodyToMatch(page, /STRATEGY_FACTORY_INTENT_CREATED|STRATEGY_FACTORY_INTENT_FAILED|factory_run_once|desktop_strategy_factory|intent_id|awaiting_confirmation|CONTROL_TOKEN/i, "live Strategy Factory intent result should render", 30_000);
    }

    await openMainView(page, "Financial Manager");
    await expectLiveBodyToMatch(page, /agent_analyze_stock|stock-analysis|read_only_plus_intents/, "live Financial Manager catalog should expose stock analysis", 30_000);
    await expect(page.getByRole("button", { name: controlLabel("Refresh"), exact: true }).first()).toBeEnabled({ timeout: 30_000 });
    if ((await page.getByLabel("stock analysis code").count()) === 0) {
      expect(await clickFirstVisibleButtonContaining(page, "stock-analysis")).toBe(true);
    }
    await expect(page.getByLabel("stock analysis code")).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("stock analysis code").fill("600519");
    const includeDecision = page.getByLabel("include stock decision");
    if (await includeDecision.isChecked()) {
      await includeDecision.uncheck();
    }
    await page.getByLabel("financial action params").fill(JSON.stringify({
      code: "600519",
      include_decision: false,
      include_financials: false,
      include_kline: false,
      kline_limit: 20
    }, null, 2));
    await clickLiveButtonWhenEnabled(page, "Run query", 20_000);
    await expectLiveBodyToMatch(page, /FINANCIAL_ACTION_OK|FINANCIAL_ACTION_FAILED|INTERNAL_ERROR|agent_analyze_stock|stock-analysis|600519/, "live stock analysis query should render a structured result", 60_000);
    await openLastRawEvidencePanel(page);
    const liveStockSummary = page.getByLabel("stock analysis summary");
    if ((await liveStockSummary.count()) > 0) {
      await expect(liveStockSummary).toBeVisible({ timeout: 30_000 });
      await expectLiveBodyToMatch(page, /600519|agent_analyze_stock|read_only|confirmation_required|not_requested|observe_only/i, "live stock summary should include code, tool, and read-only evidence", 30_000);
    } else {
      await expectLiveBodyToMatch(page, /FINANCIAL_ACTION_FAILED|INTERNAL_ERROR|error_code|availability|agent_analyze_stock|stock-analysis/i, "live stock failure should remain structured and diagnosable", 30_000);
    }
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Readiness");
    await expectLiveBodyToMatch(page, /AIASK|MCP|Hermes|financial|factory|ready|gated|unconfigured/i, "live readiness and frontend status should render", 30_000);
  });

  test("connects to the real backend and runs the visible AI smoke path", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);
    await openSettings(page);
    await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
    await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(token);
    await settingsReturnButton(page).click();
    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "AI Tests");
    await expect(page.locator(".capability-banner").filter({ hasText: "AI 测试" })).toBeVisible();
    await page.getByRole("button", { name: controlLabel("Run AI Smoke") }).click();
    await expect(page.locator(".capability-section").filter({ hasText: "冒烟测试结果" })).toContainText("true", { timeout: 30_000 });
  });

  test("renders the expanded live frontend matrix without layout regressions", async ({ page }) => {
    test.setTimeout(300_000);
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);

    const livePages: Array<{ name: string; pattern: RegExp; timeout?: number }> = [
      { name: "Projects / Contexts", pattern: /Agent|端点|上下文|finance_safe|AIASK/i },
      { name: "Sessions", pattern: /会话|session|消息|full|控制|暂无/i },
      { name: "Runs / Events", pattern: /运行|事件|run|timeline|暂无/i },
      { name: "Approvals", pattern: /审批|意图|approval|intent|工具/i },
      { name: "Finance Lab", pattern: /金融实验室|因子|策略工厂|孵化|数据|接力/i },
      { name: "Market Temperature", pattern: /市场温度|market_temperature|MARKET_TEMPERATURE|数据质量|热行业|冷行业|DESKTOP_TOOL_UNAVAILABLE|INTERNAL_ERROR/i, timeout: 45_000 },
      { name: "Quant Research", pattern: /量化研究|quant|数据|因子|research|SQLite/i },
      { name: "Data & Sync", pattern: /数据|agent_quant_data_gate|同步|新鲜度|DATA_STATUS/i },
      { name: "Factor Factory", pattern: /因子|FACTOR_FACTORY|活跃池|维护|DESKTOP_TOOL_UNAVAILABLE|CONTROL_TOKEN/i, timeout: 45_000 },
      { name: "Incubation", pattern: /INCUBATION_LOADED|孵化状态已加载|INCUBATION_DEGRADED|DESKTOP_TOOL_UNAVAILABLE/i, timeout: 45_000 },
      { name: "Automation", pattern: /自动化|任务|job|cron|JOBS|调度/i },
      { name: "Workflows", pattern: /工作流|workflow|金融|任务|Agent/i },
      { name: "Factory Events", pattern: /工厂事件|雷达|event|outbox|FACTORY|事件/i, timeout: 45_000 },
      { name: "Integrations", pattern: /集成|MCP|Gateway|插件|技能|连接器/i },
      { name: "Skills", pattern: /插件|技能|plugin|skill|受限|就绪/i },
      { name: "Gateway", pattern: /Gateway|平台|daemon|消息|目录|受限|就绪/i },
      { name: "Models", pattern: /模型|provider|AI|status|提供方|mock-live-model/i },
      { name: "Settings", pattern: /设置|Agent 端点|令牌|模型配置|连接/i },
      { name: "Overview", pattern: /总览|运行概览|系统|健康|Agent/i },
      { name: "Coverage Matrix", pattern: /覆盖矩阵|能力|implemented|partial|Hermes/i },
      { name: "Tools", pattern: /工具|agent_|safe|probe|目录/i },
      { name: "Capabilities", pattern: /能力中心|Hermes|MCP|策略工厂|AI 测试/i },
      { name: "Diagnostics", pattern: /诊断|系统健康中心|子系统|终端|Gateway/i },
      { name: "Agent Status", pattern: /智能体|Agent|工具集|状态|健康/i },
      { name: "Local User", pattern: /本地用户|画像|搜索|local|memory|记忆/i },
      { name: "Event Console", pattern: /事件控制台|事件|payload|刷新|event/i }
    ];

    for (const item of livePages) {
      await assertLivePageHealth(page, item.name, item.pattern, item.timeout);
    }

    const settingsSections: Array<{ label: string; pattern: RegExp; timeout?: number }> = [
      { label: "常规", pattern: /默认行为|默认模式|画像名称|本地用户/i },
      { label: "连接", pattern: /Agent 连接|Agent 端点|测试连接|默认本地 Agent/i },
      { label: "令牌与权限", pattern: /令牌与完整模式|API 令牌|控制令牌|完整模式/i },
      { label: "技能管理", pattern: /技能管理|安装或更新技能|已安装|原始技能/i },
      { label: "自动化管理", pattern: /自动化管理|任务|调度|工具集|删除/i },
      { label: "应用集成", pattern: /应用集成|连接器|Gateway|平台|消息/i },
      { label: "Webhook", pattern: /Webhook|订阅|触发|受控/i },
      { label: "插件与技能包", pattern: /插件与技能包|插件|skill pack|技能包/i },
      { label: "模型配置", pattern: /模型配置|提供方|模型|密钥|冒烟测试/i },
      { label: "MCP 管理入口", pattern: /MCP 管理入口|MCP 服务|资源|提示词|OAuth/i },
      { label: "工作流入口", pattern: /工作流入口|数据与同步|策略工厂|因子工厂|孵化/i },
      { label: "股票数据源", pattern: /股票数据源|数据源配置|Tushare|DuckDuckGo|测试连接/i },
      { label: "数据路径", pattern: /数据路径|数据库|Agent|量化|AKShare/i },
      { label: "学习 / RL", pattern: /学习|RL|环境|运行|结果/i },
      { label: "安全扫描", pattern: /安全扫描|扫描|修复建议|环境变量/i },
      { label: "高级诊断入口", pattern: /高级诊断入口|运行概览|工具目录|能力中心|诊断/i },
      { label: "关于", pattern: /关于 AIASK Desktop|Agent HTTP API|桌面端|版本/i }
    ];

    for (const section of settingsSections) {
      await assertLiveSettingsSectionHealth(page, section.label, section.pattern, section.timeout);
    }
  });
});
