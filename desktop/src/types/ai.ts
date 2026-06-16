export interface AiStatus {
  object: string;
  provider: string;
  model: string;
  base_url_configured: boolean;
  base_url?: string | null;
  api_key_configured: boolean;
  mock: boolean;
  configured: boolean;
  runtime_client?: string;
  prompt_cache?: PromptCachePolicy;
  config_source?: {
    loaded?: boolean;
    path?: string | null;
    source?: string;
    secrets_redacted?: boolean;
  };
  secrets_redacted: boolean;
}

export interface PromptCachePolicy {
  object?: string;
  enabled?: boolean;
  requested_enabled?: boolean;
  supported?: boolean;
  provider?: string;
  provider_type?: string;
  strategy?: string;
  system_prompt?: boolean;
  recent_non_system_messages?: number;
  cache_control?: Record<string, unknown> | null;
  env?: Record<string, string>;
  notes?: string[];
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface AiSmokeResult {
  object: string;
  configured: boolean;
  success: boolean;
  provider?: string;
  mock?: boolean;
  model?: string;
  latency_ms?: number;
  response_preview?: string;
  usage?: Record<string, unknown>;
  tool_call_count?: number;
  error_code?: string;
  error?: string;
  secrets_redacted?: boolean;
}

export interface AiProviderPreset {
  id: string;
  label: string;
  provider: string;
  provider_type?: string;
  base_url?: string;
  default_model?: string;
  api_key_url?: string;
  docs_url?: string;
  model_list_supported?: boolean;
  notes?: string[];
  category?: string;
  api_key_optional?: boolean;
}

export interface AiConfigPayload {
  object: string;
  status: string;
  current: {
    provider: string;
    model: string;
    base_url?: string | null;
    api_key_configured: boolean;
    base_url_configured: boolean;
    mock: boolean;
    configured: boolean;
    prompt_cache?: PromptCachePolicy;
    secrets_redacted: boolean;
  };
  editable: {
    provider_env: string;
    model_env: string;
    base_url_env: string;
    api_key_env: string;
    env_file: string;
    env_source: string;
  };
  presets: AiProviderPreset[];
  actions?: Record<string, unknown>;
  docs?: Record<string, string>;
  config_source?: AiStatus["config_source"];
  secrets_redacted: boolean;
}

export interface AiConfigSavePayload {
  preset?: string;
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  replace_api_key?: boolean;
  prompt_cache_enabled?: boolean;
  prompt_cache_recent_messages?: number;
}

export interface AiConfigSaveResult {
  object: string;
  saved: boolean;
  provider: string;
  model: string;
  base_url_configured: boolean;
  api_key_configured: boolean;
  mock: boolean;
  configured: boolean;
  prompt_cache?: PromptCachePolicy;
  updated_keys: string[];
  env_file?: string;
  config_source?: AiStatus["config_source"];
  secrets_redacted: boolean;
}
