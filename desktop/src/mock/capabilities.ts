import type { AiStatus, ToolCatalogItem } from "../types";

const HERMES_BASELINE = "Hermes v0.16.0 full runtime capability reference";
const HERMES_BASELINE_VERSION = "0.16.0";
const HERMES_RELEASE_TAG = "v2026.6.5";
const HERMES_V016_BASELINE = "Hermes v0.16.0 Surface Release capability reference";

export function mockHermesCapabilities(allTools: ToolCatalogItem[]) {
  return {
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
  };
}

export function mockMcpCapabilitySection() {
  return {
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
  };
}

export function mockStaticCapabilitySections(aiStatus: AiStatus) {
  return {
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
    ai: aiStatus,
    raw_refs: { backend: "mock://aiask" }
  };
}

export function mockFinancialSystemReadiness() {
  return {
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
  };
}
