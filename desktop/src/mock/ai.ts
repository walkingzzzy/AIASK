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

const aiProviderPresets = [
  { id: "openai", label: "OpenAI", provider: "openai", provider_type: "openai", base_url: "https://api.openai.com/v1", default_model: "gpt-4.1-mini", model_list_supported: true },
  { id: "deepseek", label: "DeepSeek", provider: "openai", provider_type: "openai_compatible", base_url: "https://api.deepseek.com", default_model: "deepseek-chat", model_list_supported: true },
  { id: "dashscope-qwen-cn", label: "DashScope Qwen CN", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "dashscope-qwen-intl", label: "DashScope Qwen Intl", provider: "openai", provider_type: "openai_compatible", base_url: "https://dashscope-us.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", model_list_supported: true },
  { id: "anthropic", label: "Anthropic Claude", provider: "anthropic", provider_type: "anthropic_messages", base_url: "https://api.anthropic.com/v1", default_model: "claude-sonnet-4-5", model_list_supported: true },
  { id: "custom-openai-compatible", label: "Custom OpenAI compatible", provider: "openai", provider_type: "openai_compatible", base_url: "", default_model: "", model_list_supported: true },
  { id: "mock", label: "Local Mock", provider: "mock", provider_type: "mock", base_url: "", default_model: "mock-local", model_list_supported: false }
];

export function mockAiStatus() {
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

export function mockAiConfig() {
  const status = mockAiStatus();
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

export function saveMockAiConfig(body: Record<string, unknown>) {
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
  const status = mockAiStatus();
  return {
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
  };
}

export function mockAiSmoke(body: Record<string, unknown>) {
  return {
    object: "aiask.ai_smoke",
    configured: true,
    success: true,
    provider: mockModelConfig.provider,
    model: body.model || mockModelConfig.model,
    mock: true,
    latency_ms: 5,
    response_preview: "AI_SMOKE_PASSED",
    secrets_redacted: true
  };
}

export function mockAiModels() {
  return {
    data: [
      { id: mockModelConfig.model, object: "model", owned_by: mockModelConfig.provider },
      { id: `${mockModelConfig.model}-mini`, object: "model", owned_by: mockModelConfig.provider }
    ],
    configured: true
  };
}

export function mockResponseCreate(body: Record<string, unknown>) {
  return {
    id: "resp_mock",
    object: "response",
    status: "completed",
    output_text: "AIASK_OK",
    metadata: {
      session_id: body.session_id || "sess_mock",
      run_id: "run_mock",
      mode: body.mode || "finance_safe",
      audit_events: [{ event: "mock" }]
    }
  };
}

export function mockResponseGet(responseId: string) {
  return {
    id: responseId,
    object: "response",
    status: "completed",
    output_text: "AIASK_OK",
    metadata: {
      session_id: "sess_mock",
      run_id: "run_mock",
      mode: "finance_safe",
      audit_events: [{ event: "mock" }]
    }
  };
}

export function mockResponseDelete(responseId: string) {
  return { id: responseId, object: "response.deleted", deleted: true };
}
