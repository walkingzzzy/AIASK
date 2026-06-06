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
        baseline: "Hermes v0.15.1 full runtime capability reference",
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        full_mode_active: authorized
      },
      parity: {
        baseline: "Hermes v0.15.1 full runtime capability reference",
        scope: "hermes_full_runtime",
        strict_status: "in_progress",
        status: "in_progress",
        strict_hermes_tool_count: 57,
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
          total: 6,
          implemented_count: 6,
          partial_count: 0,
          missing_count: 0,
          missing: [],
          partial: [],
          implemented: [
            { hermes_tool: "computer_use", area: "computer_use", status: "implemented", aiask_tools: ["agent_computer_use"] },
            { hermes_tool: "video_generate", area: "multimodal", status: "live_unverified", aiask_tools: ["agent_video_generate"] },
            { hermes_tool: "x_search", area: "web", status: "live_unverified", aiask_tools: ["agent_x_search"] },
            { platform: "line", area: "platform", status: "implemented", aiask_adapter: "line" },
            { platform: "simplex", area: "platform", status: "implemented", aiask_adapter: "simplex" },
            { platform: "teams", area: "platform", status: "implemented", aiask_adapter: "teams" }
          ]
        }
      },
      readiness: { object: "aiask.hermes_readiness", embedded_vendor_runtime: false, missing_features: [] },
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
            name: "risk-plugin",
            enabled: true,
            source: "local",
            version: "0.1.0",
            description: "Mock risk plugin",
            tools: [{ name: "risk_echo" }],
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

function connectorsSummaryPayload() {
  return {
    data: {
      total: 4,
      connected: 2,
      configured: 3,
      by_type: {
        financial: { count: 1, connected: 1 },
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
          id: "risk-plugin",
          name: "Risk plugin",
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
          { name: "agent_memory_search", capability: "memory", category: "memory", status: "ready", side_effect: "read_only", description: "Mock memory search" },
          { name: "agent_action_intent_create", capability: "approval", category: "governance", status: "ready", side_effect: "stateful", description: "Mock approval intent" }
        ]
      });
    }
    if (path === "/v1/hermes/status") {
      return fulfillJson(route, {
        object: "aiask.hermes_status",
        implementation: "aiask_native",
        baseline: "Hermes v0.15.1 full runtime capability reference",
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
    if (path === "/v1/desktop/runs") {
      return fulfillJson(route, { object: "list", data: workbenchSummaryPayload().recent_runs });
    }
    if (path === "/v1/desktop/settings/status") {
      return fulfillJson(route, settingsStatusPayload(authorized));
    }
    if (path === "/v1/desktop/data/status") {
      const codes = url.searchParams.get("codes")?.split(",").filter(Boolean) || ["600519", "000001", "000858"];
      const maxStaleDays = Number(url.searchParams.get("max_stale_days") || 5);
      return fulfillJson(route, desktopDataStatusPayload(codes, maxStaleDays));
    }
    if (path === "/v1/desktop/data/sync-plan") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, dataSyncPlanPayload(body));
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
            name: "risk-plugin",
            enabled: true,
            source: "local",
            version: "0.1.0",
            description: "Mock risk plugin",
            tools: [{ name: "risk_echo" }],
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
    if (path === "/v1/tools/agent_strategy_domain_events") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, strategyEventsEnvelope(typeof body.event_type === "string" ? body.event_type : null));
    }
    if (path === "/v1/tools/agent_quant_data_gate") {
      return fulfillJson(route, { success: true, data: { status: "partial", missing: ["000858"], stale: ["000001"] }, error: null, error_code: null });
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
      return fulfillJson(route, { data: [] });
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
    if (path === "/v1/terminal/backends" || path === "/v1/terminal/sessions") {
      return fulfillJson(route, { data: [] });
    }
    if (path === "/v1/learning/status") {
      return fulfillJson(route, { status: "ready" });
    }
    if (path === "/v1/learning/review") {
      return fulfillJson(route, { data: [] });
    }
    if (path === "/v1/rl/environments") {
      return fulfillJson(route, { data: { default: "mock" } });
    }
    if (path === "/v1/rl/runs") {
      return fulfillJson(route, { data: [] });
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
  Overview: "Overview",
  Agent: "Workbench",
  Workbench: "Workbench",
  "Coverage Matrix": "Coverage",
  Models: "Models",
  "Data & Sync": "Data",
  MCP: "MCP / Connectors",
  Skills: "Plugins / Skills",
  Automation: "Automation",
  "Strategy Factory": "Strategy Factory",
  "Factor Factory": "Factor Factory",
  Incubation: "Incubation Factory",
  "Local User": "User",
  Tools: "Tools",
  Capabilities: "Capabilities",
  "Event Console": "Event Console",
  "Factory Events": "Factory Events",
  Diagnostics: "Diagnostics",
  "Agent Status": "Agent",
  Workflows: "Workflows",
  Settings: "Settings / Mode"
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
  Connect: "连接智能体",
  Refresh: "刷新",
  Run: "运行",
  Search: "搜索",
  "Sync Agent state": "同步 AIASK 状态",
  "Finance safe mode": "金融安全模式",
  "Finance safe": "金融安全",
  "Hermes full mode": "Hermes full 模式",
  "Hermes full": "Hermes full",
  "Run thread task": "运行线程任务",
  "Load run events": "加载运行事件",
  "Load run events for selected task": "加载所选任务的运行事件",
  "Generate sync plan": "生成同步计划",
  "Create approval intent": "创建审批意图",
  "Refresh capability review": "刷新能力评审",
  "Register local MCP server": "注册本地 MCP 服务",
  "Discover or refresh MCP server": "发现或刷新 MCP 服务",
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
  "Save profile": "保存 profile",
  "Save local profile": "保存画像",
  "Run safe probe": "运行安全探测",
  "Fill example": "填充示例",
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
  "Connector detail": "详情",
  "Connector test": "测试",
  Reauthorize: "重新认证",
  "risk-review Risk review": "risk-review Risk review",
  "Load messages": "加载消息",
  "Run the first registered plugin tool": "运行第一个已注册插件工具",
  "Load plugin commands": "加载插件命令",
  "Test plugin command": "测试插件命令",
  "Fill example for agent_factory_status": "为 agent_factory_status 填充示例",
  "Fill example for agent_memory_search": "为 agent_memory_search 填充示例",
  "Fill example for agent_quant_data_gate": "为 agent_quant_data_gate 填充示例",
  "Search tools input": "搜索工具输入"
};

const PLACEHOLDER_LABELS: Record<string, string> = {
  "resource uri": "资源 URI",
  "prompt name": "提示词名称",
  "OAuth server name": "OAuth 服务名称",
  "Ask AIASK to research, code, inspect tools, or continue a session...": "让 AIASK 做研究、写代码、检查工具，或继续一个会话...",
  "Search local sessions, responses, and memory": "搜索本地会话、回复和记忆",
  "Search tools": "搜索工具",
  "Search area, tool, platform...": "搜索领域、工具、平台...",
  "payload text": "payload 文本"
};

const SETTINGS_STRUCTURE_BUTTONS = [
  "返回对话",
  "常规",
  "连接",
  "令牌与权限",
  "技能管理",
  "自动化管理",
  "应用集成",
  "Webhook",
  "插件与技能包",
  "模型状态",
  "MCP 管理入口",
  "工作流入口",
  "数据路径",
  "学习 / RL",
  "安全扫描",
  "高级诊断入口",
  "关于"
];

const LEGACY_REPLACEMENT_BUTTONS = [
  "前往 Workbench",
  "前往 Settings / Mode",
  "前往 Tools / Intents / Approvals",
  "前往 MCP / Connectors",
  "前往 Runs / Events",
  "前往 Readiness / Health",
  "前往 Plugins / Skills",
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

Object.assign(VIEW_LABELS, {
  Overview: "Overview",
  Agent: "Workbench",
  Workbench: "Workbench",
  "Coverage Matrix": "Coverage",
  Models: "Models",
  "Data & Sync": "Data",
  MCP: "MCP / Connectors",
  Skills: "Plugins / Skills",
  Automation: "Automation",
  "Strategy Factory": "Strategy Factory",
  "Factor Factory": "Factor Factory",
  Incubation: "Incubation Factory",
  "Local User": "User",
  Tools: "Tools",
  Capabilities: "Capabilities",
  "Event Console": "Event Console",
  "Factory Events": "Factory Events",
  Diagnostics: "Diagnostics",
  "Agent Status": "Agent",
  Workflows: "Workflows",
  Settings: "Settings / Mode"
});

Object.assign(CONTROL_LABELS, {
  Refresh: "刷新",
  "Sync Agent state": "同步 AIASK 状态",
  "Test connection": "测试连接",
  "Reset endpoint to default Agent endpoint": "恢复默认 Agent 端点",
  "Save profile": "保存 profile"
});

async function openOverview(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AIASK Workbench" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "session-first 主路径" })).toBeVisible();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toBeVisible();
}

async function openSettings(page: Page) {
  if (await page.getByRole("button", { name: "返回对话", exact: true }).count()) return;
  await page.getByRole("navigation").getByRole("button", { name: viewLabel("Settings"), exact: true }).click();
}

async function setControlToken(page: Page) {
  await openSettings(page);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  const controlTokenInput = page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input");
  await expect(controlTokenInput).toHaveCount(1);
  await controlTokenInput.fill(CONTROL_TOKEN);
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText("AIASK_ONLINE").first()).toBeVisible();
  await page.getByRole("button", { name: "返回对话", exact: true }).click();
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

async function openMainView(page: Page, name: string) {
  const backToChat = page.getByRole("button", { name: "返回对话", exact: true });
  if (name !== "Settings" && (await backToChat.count())) {
    await backToChat.click();
  }

  if (name === "Agent" || name === "Workbench") {
    await page.getByRole("navigation").getByRole("button", { name: viewLabel("Agent"), exact: true }).click();
    return;
  }

  if (WORKFLOW_ENTRY_VIEWS.has(name)) {
    await page.getByRole("navigation").getByRole("button", { name: viewLabel("Workflows"), exact: true }).click();
    await clickShortcutByLabel(page, viewLabel(name));
    return;
  }

  if (SETTINGS_MODEL_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "模型状态", exact: true }).click();
    await clickShortcutByLabel(page, "打开模型状态页");
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
  if (await navigationButton.count()) {
    await navigationButton.click();
    return;
  }
  await page.getByRole("button", { name: label, exact: true }).click();
}

async function openCapabilityTab(page: Page, name: string) {
  await page.locator(".capabilities-tabs").getByRole("button", { name: tabLabel(name), exact: true }).click();
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
        mainRect.right > sidebarRect.left + 1
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
  options: { structural?: string[]; gated?: string[] } = {}
) {
  const allowed = new Set(
    [...covered, ...(options.structural || []), ...(options.gated || [])].flatMap((name) => [
      name,
      controlLabel(name),
      tabLabel(name),
      viewLabel(name)
    ])
  );
  const visibleButtonControls = inventory.controls.filter((control) => control.tag === "button" || control.tag === "a");
  const visibleButtonNames = uniqueNames(visibleButtonControls);
  const missing = visibleButtonNames
    .filter((name) => !allowed.has(name))
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
    await expect
      .poll(async () => page.locator("body").evaluate((body) => (body as HTMLElement).innerText), {
        message: `${pageName} should show ${expectedText}`,
        timeout: 7_500
      })
      .toContain(expectedText);
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
  await expect(page.getByText("缺少控制令牌 Control token", { exact: false }).first()).toBeVisible();
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
  await expect(page.getByText("implemented").first()).toBeVisible();

  await page.unroute(`${API_ORIGIN}/**`);
  await setupApiMocks(page, { factoryMode: "degraded" });
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("数据库已配置，但 strategy manager 返回错误。", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("STRATEGY_FACTORY_UNAVAILABLE").first()).toBeVisible();
  await expect(page.getByText("partial").first()).toBeVisible();
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
  await expect(page.getByText("Provider openai / live / base URL 已配置")).toBeVisible();
  await expect(page.getByText("API key")).toBeVisible();
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
  await page.getByRole("button", { name: controlLabel("Run") }).click();
  await expect(page.getByRole("heading", { name: "智能体回复" })).toBeVisible();
  await expect(page.getByText("AIASK_OK").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.started" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.started" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.completed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.delta" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.completed" })).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Load run events for selected task") }).click();
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

test("Data & Sync workspace renders database preflight and creates a gated sync intent in mock mode", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await expect(page.getByText("/tmp/akshare_mcp.sqlite3").first()).toBeAttached();

  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText("SYNC_PLAN_READY")).toBeVisible();
  await expect(page.getByText("data_sync.run_once", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Create approval intent") })).toBeDisabled();

  await setControlToken(page);
  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText("SYNC_INTENT_CREATED")).toBeVisible();
  await expect(page.getByText("intent_e2e_approved_path", { exact: true })).toBeVisible();
});

test("Unified control console opens every primary page and exercises safe mock controls", async ({ page }) => {
  test.setTimeout(120_000);
  await setupApiMocks(page);
  await openOverview(page);

  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText("AIASK_ONLINE").first()).toBeVisible();
  await setControlToken(page);

  await openMainView(page, "Agent");
  await expect(page.getByRole("heading", { name: "AIASK Workbench" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText("AIASK_ONLINE").first()).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Hermes full") }).click();
  await expect(page.getByRole("button", { name: controlLabel("Hermes full") })).toHaveAttribute("aria-pressed", "true");

  await openMainView(page, "Models");
  await expect(page.getByRole("heading", { name: "LLM 提供方配置" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("MODEL_STATUS_LOADED")).toBeVisible();

  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText("SYNC_INTENT_CREATED")).toBeVisible();

  await openMainView(page, "MCP");
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
  await expect(page.getByRole("heading", { name: "AIASK Workbench" })).toBeVisible();
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
  await jobRow.getByRole("button", { name: controlLabel("Inspect") }).click();
  await jobRow.getByRole("button", { name: controlLabel("Pause") }).click();
  await expect(automationResult).toContainText("updated");
  await jobRow.getByRole("button", { name: controlLabel("Run") }).click();
  await expect(automationResult).toContainText("completed");
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  await expect(page.getByRole("heading", { name: "自动化管理" }).first()).toBeVisible();
  const managedAutomationResult = page.locator(".capability-section").filter({ hasText: "运行输出" });
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await expect(managedJobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(1);
  await managedJobRow.getByRole("button", { name: controlLabel("Delete") }).click();
  await expect(managedAutomationResult).toContainText("deleted");

  await openMainView(page, "Strategy Factory");
  await expect(page.getByRole("heading", { name: "调度器、运行和晋升评审" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText("STRATEGY_FACTORY_INTENT_CREATED")).toBeVisible();

  await openMainView(page, "Factor Factory");
  await expect(page.getByRole("heading", { name: "因子挖掘与活跃池" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText("FACTOR_RUN_INTENT_CREATED")).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText("FACTOR_MAINTENANCE_INTENT_CREATED")).toBeVisible();

  await openMainView(page, "Incubation");
  await expect(page.getByRole("heading", { name: "生命周期与命中率控制" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Run intent"), exact: true }).click();
  await expect(page.getByText("INCUBATION_RUN_ONCE_INTENT_CREATED")).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Dry-run intent") }).click();
  await expect(page.getByText("INCUBATION_DRY_RUN_INTENT_CREATED")).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText("INCUBATION_MAINTENANCE_INTENT_CREATED")).toBeVisible();

  await openMainView(page, "Local User");
  await expect(page.getByRole("heading", { name: "画像与本地数据范围" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Save local profile") }).click();
  await expect(page.getByText("LOCAL_PROFILE_SAVED")).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await page.getByRole("button", { name: controlLabel("Search") }).click();
  await expect(page.getByText("USER_DATA_SEARCHED")).toBeVisible();

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
  await page.getByRole("button", { name: controlLabel("Disable") }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");
  await page.getByRole("button", { name: controlLabel("Test tool"), exact: true }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");

  await openMainView(page, "Event Console");
  await expect(page.getByRole("heading", { name: "生命周期、风险与孵化事件" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("EVENTS_LOADED")).toBeVisible();

  await openMainView(page, "Diagnostics");
  await expect(page.getByRole("heading", { name: "Hermes 原生对齐" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("系统健康中心")).toBeVisible();

  await openMainView(page, "Agent Status");
  await expect(page.getByRole("heading", { name: "运行状态" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("AGENT_STATUS_LOADED")).toBeVisible();

  await openMainView(page, "Settings");
  await expect(page.getByRole("heading", { name: "设置中心" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await page.getByRole("button", { name: "模型状态", exact: true }).click();
  await expect(page.getByText("只读查看模型提供方")).toBeVisible();
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Save profile") }).click();
  await expect(page.locator("label.settings-row").filter({ hasText: "Profile 名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText("AIASK_ONLINE").first()).toBeVisible();
  await page.getByRole("button", { name: "返回对话", exact: true }).click();
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
  await clickAndRecord(report, page, "Workbench", "Sync Agent state", "AIASK_ONLINE");
  assertMainButtonCoverage(workbenchInventory, [
    "Sync Agent state",
    "Finance safe mode",
    "Finance safe",
    "Hermes full",
    "Run thread task",
    "E2E session 2026-05-21T08:00:00.000Z",
    "run_fixture completed / 工具 0 / 审批 0",
    "Readiness",
    "Tools / Intents / Approvals",
    "MCP / Connectors",
    "Gateway",
    "Gateway gated",
    "Plugins / Skills gated",
    "Extensions internal",
  ]);

  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText("SYNC_PLAN_READY")).toBeVisible();
  report.actions.push({ page: "Data & Sync gated", control: "Generate sync plan", result: "clicked", note: "plan generated without write intent" });
  await expectDisabledAndRecord(report, page, "Data & Sync gated", "Create approval intent", "control token required");

  await openMainView(page, "MCP");
  await expectDisabledAndRecord(report, page, "MCP gated", "Register local MCP server", "control token required or already registered");
  await expectDisabledAndRecord(report, page, "MCP gated", "Discover or refresh MCP server", "control token required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Read MCP resource", "control token and resource uri required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Get MCP prompt", "control token and prompt name required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Start MCP OAuth flow", "control token and server required");

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
    "E2E session 2026-05-21T08:00:00.000Z",
    "run_fixture completed / 工具 0 / 审批 0",
    "Readiness",
    "Tools / Intents / Approvals",
    "MCP / Connectors",
    "Gateway",
    "Gateway ready",
    "Plugins / Skills ready",
    "Extensions internal",
  ]);

  await openMainView(page, "Models");
  const modelsInventory = await recordInventory(report, page, "Models");
  await clickAndRecord(report, page, "Models", "Refresh", "MODEL_STATUS_LOADED");
  assertMainButtonCoverage(modelsInventory, ["Refresh"]);

  await openMainView(page, "Data & Sync");
  const dataInventory = await recordInventory(report, page, "Data & Sync");
  await page.locator("label.field-row").filter({ hasText: "证券代码" }).locator("textarea").fill("600519, 000001");
  await clickAndRecord(report, page, "Data & Sync", "Refresh", "DATA_STATUS_LOADED");
  await clickAndRecord(report, page, "Data & Sync", "Generate sync plan", "SYNC_PLAN_READY");
  const dataInventoryWithPlan = await collectMainInventory(page, "Data & Sync with plan");
  await clickAndRecord(report, page, "Data & Sync", "Create approval intent", "SYNC_INTENT_CREATED");
  assertMainButtonCoverage(dataInventoryWithPlan, ["Refresh", "Generate sync plan", "Create approval intent"]);
  assertMainButtonCoverage(dataInventory, ["Refresh", "Generate sync plan"]);

  await openMainView(page, "MCP");
  const mcpInventory = await recordInventory(report, page, "MCP");
  await clickAndRecord(report, page, "MCP", "Refresh", "CONNECTORS_LOADED");
  const firstConnector = page.locator(".connector-item").first();
  await firstConnector.getByRole("button", { name: controlLabel("Connector detail"), exact: true }).click();
  await expect(page.locator("body")).toContainText("CONNECTOR_DETAIL_LOADED");
  report.actions.push({ page: "MCP", control: "Connector detail", result: "clicked", note: "CONNECTOR_DETAIL_LOADED" });
  await firstConnector.getByRole("button", { name: controlLabel("Connector test"), exact: true }).click();
  await expect(page.locator("body")).toContainText("CONNECTOR_TESTED");
  report.actions.push({ page: "MCP", control: "Connector test", result: "clicked", note: "CONNECTOR_TESTED" });
  await expectDisabledAndRecord(report, page, "MCP", "Register local MCP server", "already registered in mock");
  await clickAndRecord(report, page, "MCP", "Discover or refresh MCP server", "finance-demo");
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
    "Disable plugin",
    "Configure",
    "Test tool",
    "Run the first registered plugin tool",
    "Load plugin commands",
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
  await clickAndRecord(report, page, "Automation", "Inspect", "每日研究监控", jobRow);
  await clickAndRecord(report, page, "Automation", "Pause", "updated", jobRow);
  await clickAndRecord(report, page, "Automation", "Run", "completed", jobRow);
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);
  assertMainButtonCoverage(automationInventory, ["Refresh", "Create job", "Inspect", "Pause", "Run"]);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  const automationManagementInventory = await recordInventory(report, page, "Automation management");
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await clickAndRecord(report, page, "Automation management", "Delete", "deleted", managedJobRow);
  assertMainButtonCoverage(automationManagementInventory, ["Refresh", "Create job", "Inspect", "Pause", "Run", "Delete"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });

  await openMainView(page, "Strategy Factory");
  const strategyInventory = await recordInventory(report, page, "Strategy Factory");
  await clickAndRecord(report, page, "Strategy Factory", "Refresh capability review", "Mock 数据");
  await clickAndRecord(report, page, "Strategy Factory", "Create run intent", "STRATEGY_FACTORY_INTENT_CREATED");
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

  await openMainView(page, "Local User");
  const userInventory = await recordInventory(report, page, "Local User");
  await clickAndRecord(report, page, "Local User", "Refresh", "LOCAL_PROFILE_LOADED");
  await clickAndRecord(report, page, "Local User", "Save local profile", "LOCAL_PROFILE_SAVED");
  await expectDisabledAndRecord(report, page, "Local User", "Search", "query required");
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await clickAndRecord(report, page, "Local User", "Search", "USER_DATA_SEARCHED");
  assertMainButtonCoverage(userInventory, ["Refresh", "Load messages", "Save local profile", "Search"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Tools");
  const toolsInventory = await recordInventory(report, page, "Tools");
  await page.getByPlaceholder(placeholderLabel("Search tools")).fill("factory");
  await expect(page.getByText("agent_factory_status")).toBeVisible();
  report.actions.push({ page: "Tools", control: "Search tools input", result: "typed", note: "agent_factory_status visible" });
  assertMainButtonCoverage(toolsInventory, [
    "Fill example for agent_factory_status",
    "Fill example for agent_memory_search",
    "Fill example for agent_quant_data_gate",
    "Run safe probe"
  ], {
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
  await clickAndRecord(report, page, "Capabilities / Plugins", "Disable");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");
  await clickAndRecord(report, page, "Capabilities / Plugins", "Test tool");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");
  assertMainButtonCoverage(pluginsInventory, [
    "Disable",
    "Disable plugin",
    "Configure",
    "Test tool",
    "Run the first registered plugin tool",
    "Load plugin commands",
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
  const diagnosticsInventory = await recordInventory(report, page, "Diagnostics");
  await clickAndRecord(report, page, "Diagnostics", "Refresh", "系统健康中心");
  assertMainButtonCoverage(diagnosticsInventory, ["Refresh"], {
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
  await page.locator("label.settings-row").filter({ hasText: "Endpoint" }).locator("input").fill(API_ORIGIN);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  await page.locator("label.settings-row").filter({ hasText: "API 令牌" }).locator("input").fill("api-token-mock");
  await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(CONTROL_TOKEN);
  await clickAndRecord(report, page, "Settings", "Refresh");
  await page.getByRole("button", { name: "模型状态", exact: true }).click();
  await expect(page.getByText("只读查看模型提供方")).toBeVisible();
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Save profile");
  await expect(page.locator("label.settings-row").filter({ hasText: "Profile 名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Test connection", "AIASK_ONLINE");
  assertMainButtonCoverage(settingsInventory, ["Refresh", "Reset endpoint to default Agent endpoint", "Save profile", "Test connection"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });
  await page.getByRole("button", { name: "返回对话", exact: true }).click();

  await page.setViewportSize({ width: 980, height: 760 });
  await openMainView(page, "Overview");
  const narrowOverview = await recordInventory(report, page, "Overview narrow");
  assertMainButtonCoverage(narrowOverview, ["Refresh"]);
  await page.screenshot({ path: path.join(reportDir, "narrow-overview.png"), fullPage: true });
  report.screenshots.push(path.join(reportDir, "narrow-overview.png"));

  await writeFile(path.join(reportDir, "playwright-full-matrix-report.json"), JSON.stringify(report, null, 2), "utf8");
});

test.describe("optional live desktop smoke", () => {
  test.skip(process.env.AIASK_DESKTOP_RUN_LIVE !== "1", "set AIASK_DESKTOP_RUN_LIVE=1 and run a real backend on 127.0.0.1:8767");

  test("connects to the real backend and runs the visible AI smoke path", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: controlLabel("Connect") }).click();
    await expect(page.getByText("AIASK_ONLINE").first()).toBeVisible();

    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await openSettings(page);
    await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
    await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(token);
    await page.getByRole("button", { name: "返回对话", exact: true }).click();
    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "AI Tests");
    await expect(page.locator(".capability-banner").filter({ hasText: "AI 测试" })).toBeVisible();
    await page.getByRole("button", { name: controlLabel("Run AI Smoke") }).click();
    await expect(page.locator(".capability-section").filter({ hasText: "冒烟测试结果" })).toContainText("true", { timeout: 30_000 });
  });
});
