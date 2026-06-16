export function mockSettingsStatus(
  aiStatus: Record<string, unknown>,
  stockDataSources: Record<string, unknown>,
  profile: Record<string, unknown>
) {
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
      ai_status: aiStatus,
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
    stock_data_sources: stockDataSources,
    profile,
    secrets_redacted: true
  };
}
