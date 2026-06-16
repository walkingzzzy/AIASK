import { API_ORIGIN } from "./capabilitiesMockConstants";

export type FactoryMode = "success" | "degraded";

export function hermesTools() {
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

export function capabilityPayload(authorized: boolean, factoryMode: FactoryMode) {
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

export function aiStatus() {
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

export function aiConfigPayload() {
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

export function localProfilePayload(overrides: Record<string, unknown> = {}) {
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

export function settingsStatusPayload(authorized: boolean) {
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
