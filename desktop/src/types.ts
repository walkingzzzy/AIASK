export interface HealthDetailed {
  status: string;
  service: string;
  host?: string;
  port?: number;
  runtime?: {
    model?: string;
    max_iterations?: number;
    model_timeout_seconds?: number;
    tool_timeout_seconds?: number;
  };
  tools?: {
    count?: number;
    names?: string[];
    toolset?: string;
  };
  hermes?: {
    mode?: string;
    full_mode_enabled?: boolean;
    full_mode_active?: boolean;
    parity?: CapabilityParity;
  };
  control?: {
    loopback_only?: boolean;
    token_configured?: boolean;
  };
}

export interface ToolCatalogItem {
  name: string;
  capability: string;
  category?: string;
  status?: string;
  visibility?: "api_safe" | "full_mode_only" | string;
  interaction_mode?: "read_only" | "intent" | "approval" | "blocked" | string;
  confirmation_required?: boolean;
  blocked_reason?: string | null;
  side_effect:
    | string
    | {
        level?: string;
        target?: string;
        confirmation_required?: boolean;
        idempotent?: boolean;
      };
  description: string;
  parameters?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  freshness?: Record<string, unknown>;
  examples?: unknown[];
  contract_version?: string;
  contract_source?: "akshare_mcp.tool_catalog" | "runtime_inferred" | "agent_schema" | string;
  source_policy?: Record<string, unknown>;
  standard_model?: string;
  provider_choices?: unknown[];
  provider_status?: Record<string, unknown>;
  quality_gate?: Record<string, unknown>;
  reconciliation?: Record<string, unknown>;
  form_schema?: Record<string, unknown>;
}

export interface ToolEnvelope {
  success: boolean;
  data: unknown;
  error: string | null;
  error_code?: string;
  meta?: {
    trace_id?: string;
    audit_event_id?: string;
    source_chain?: string[];
    side_effect?: {
      level?: string;
      target?: string;
      confirmation_required?: boolean;
      idempotent?: boolean;
    };
  };
}

export interface TradePredictionStatus {
  object?: string;
  status?: string;
  configured?: boolean;
  generated_at?: string;
  prediction_count?: number;
  outcome_count?: number;
  sample_n?: number;
  pending_count?: number;
  evaluated_count?: number;
  partial_count?: number;
  prediction_status_counts?: Record<string, number>;
  score_status_counts?: Record<string, number>;
  latest_score_status_counts?: Record<string, number>;
  score_version_counts?: Record<string, number>;
  data_quality_status_counts?: Record<string, number>;
  latest_data_quality_status_counts?: Record<string, number>;
  score_distribution?: Record<string, number>;
  score_summary?: {
    avg?: number | null;
    min?: number | null;
    max?: number | null;
  };
  error?: string | null;
  error_code?: string;
  [key: string]: unknown;
}

export interface TradePredictionOutcome {
  outcome_id?: string;
  prediction_id?: string;
  strategy_id?: string;
  stock_code?: string;
  actual_trading_date?: string;
  score_version?: string;
  score_status?: string;
  data_quality_status?: string;
  trade_prediction_score?: number | null;
  outcome_json?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  calculated_at?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface TradePredictionOutcomes {
  object?: string;
  status?: string;
  configured?: boolean;
  items?: TradePredictionOutcome[];
  count?: number;
  error?: string | null;
  error_code?: string;
  [key: string]: unknown;
}

export interface TradePredictionMatrixRow {
  dimension?: string;
  value?: string;
  sample_n?: number;
  score_avg?: number | null;
  score_lcb_95?: number | null;
  direction_hit_rate?: number | null;
  target_touch_rate?: number | null;
  score_status_counts?: Record<string, number>;
  data_quality_status_counts?: Record<string, number>;
  [key: string]: unknown;
}

export interface TradePredictionMatrix {
  object?: string;
  status?: string;
  configured?: boolean;
  generated_at?: string;
  score_version?: string | null;
  dimensions?: string[];
  rows?: TradePredictionMatrixRow[];
  row_count?: number;
  error?: string | null;
  error_code?: string;
  [key: string]: unknown;
}

export interface MarketTemperatureSummary {
  stock_count?: number;
  trend_known_count?: number;
  above_ma20_count?: number;
  ma20_breadth?: number | null;
  advance_count?: number;
  decline_count?: number;
  flat_count?: number;
  advance_ratio?: number | null;
  avg_pct_change?: number | null;
  weighted_pct_change?: number | null;
  amount?: number | null;
  market_cap?: number | null;
  temperature?: number | null;
  state?: string;
  [key: string]: unknown;
}

export interface MarketTemperatureIndustry extends MarketTemperatureSummary {
  code?: string;
  name?: string;
  date?: string;
  market_cap_weight?: number | null;
}

export interface MarketTemperatureQuality {
  status?: string;
  warnings?: string[];
  input_rows?: number;
  valid_stock_count?: number;
  invalid_stock_rows?: number;
  industry_count?: number;
  unknown_industry_count?: number;
  trend_coverage?: number | null;
  universe_limit?: number;
  universe_count?: number;
  loaded_stock_rows?: number;
  missing_kline_rows?: number;
  contract_version?: string;
  [key: string]: unknown;
}

export interface MarketTemperatureSnapshot {
  contract_version?: string;
  as_of?: string;
  market?: MarketTemperatureSummary;
  industries?: MarketTemperatureIndustry[];
  hot_industries?: MarketTemperatureIndustry[];
  cold_industries?: MarketTemperatureIndustry[];
  quality?: MarketTemperatureQuality;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureCacheReadiness {
  ready?: boolean;
  status?: string;
  read_only?: boolean;
  as_of?: string | null;
  requested_as_of?: string | null;
  max_stale_days?: number;
  staleness_days?: number | null;
  quality_status?: string;
  degraded?: boolean;
  warnings?: string[];
  market_temperature?: number | null;
  market_state?: string | null;
  stock_count?: number;
  industry_count?: number;
  cache?: {
    created_at?: string | null;
    updated_at?: string | null;
    source?: string;
    [key: string]: unknown;
  };
  blockers?: string[];
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureCacheHistoryItem {
  as_of?: string;
  contract_version?: string;
  market_temperature?: number | null;
  market_state?: string | null;
  stock_count?: number;
  industry_count?: number;
  quality_status?: string;
  warnings?: string[];
  created_at?: string | null;
  updated_at?: string | null;
  snapshot?: MarketTemperatureSnapshot;
  [key: string]: unknown;
}

export interface MarketTemperatureCacheHistory {
  items?: MarketTemperatureCacheHistoryItem[];
  count?: number;
  limit?: number;
  include_snapshot?: boolean;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureIndustryHistoryItem {
  as_of?: string;
  code?: string;
  name?: string;
  temperature?: number | null;
  state?: string;
  ma20_breadth?: number | null;
  advance_count?: number;
  decline_count?: number;
  flat_count?: number;
  stock_count?: number;
  market_cap_weight?: number | null;
  market_temperature?: number | null;
  market_state?: string | null;
  quality_status?: string;
  warnings?: string[];
  updated_at?: string | null;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureIndustryHistory {
  items?: MarketTemperatureIndustryHistoryItem[];
  count?: number;
  limit?: number;
  top_n?: number;
  industry?: string | null;
  match_mode?: string;
  include_source_chain?: boolean;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureIndustryConstituent {
  code?: string;
  name?: string;
  industry_code?: string | null;
  industry?: string;
  sector?: string;
  market?: string | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  list_date?: string | null;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureIndustryConstituents {
  items?: MarketTemperatureIndustryConstituent[];
  count?: number;
  total_matches?: number;
  limit?: number;
  offset?: number;
  industry?: string;
  match_mode?: string;
  include_source_chain?: boolean;
  source_chain?: string[];
  [key: string]: unknown;
}

export interface MarketTemperatureForwardValidationCell {
  sample_n?: number;
  direction_hits?: number;
  reliable?: boolean;
  avg_forward_return?: number | null;
  hit_rate?: number | null;
  min_forward_return?: number | null;
  max_forward_return?: number | null;
  [key: string]: unknown;
}

export interface MarketTemperatureForwardValidation {
  matrix?: Record<string, Record<string, MarketTemperatureForwardValidationCell>>;
  states?: string[];
  horizons?: number[];
  count?: number;
  snapshot_count?: number;
  limit?: number;
  target_field?: string;
  requested_target_field?: string;
  benchmark_code?: string | null;
  benchmark_status?: string;
  benchmark_bar_count?: number;
  min_samples?: number;
  neutral_band_pct?: number;
  include_samples?: boolean;
  samples?: Record<string, unknown>[];
  source_chain?: string[];
  [key: string]: unknown;
}

export interface AgentToolCall {
  id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: ToolEnvelope | unknown;
}

export interface AgentResponse {
  id: string;
  object: string;
  status: string;
  output_text: string;
  metadata?: {
    session_id?: string;
    run_id?: string;
    mode?: string;
    tool_calls?: AgentToolCall[];
    audit_events?: Record<string, unknown>[];
  };
}

export interface ResponseRecord extends AgentResponse {
  model?: string;
  usage?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RunRecord {
  run_id?: string;
  id?: string;
  object?: string;
  status?: string;
  response_id?: string;
  session_id?: string;
  created_at?: string;
  updated_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export type InspectorTab = "details" | "artifacts" | "review" | "diagnostics" | "tools" | "skills" | "intents" | "settings";
export type MainView =
  | "workbench"
  | "projects-contexts"
  | "sessions"
  | "runs-events"
  | "tools-intents-approvals"
  | "finance-lab"
  | "integrations"
  | "plugins-skills"
  | "extensions-pilot"
  | "financial-manager"
  | "market-temperature"
  | "automation"
  | "data"
  | "factor-factory"
  | "factory-events"
  | "gateway"
  | "incubation"
  | "mcp-connectors"
  | "quant"
  | "readiness-health"
  | "settings"
  | "strategy-factory"
  | "workflows"
  | "agent"
  | "capabilities"
  | "coverage"
  | "diagnostics"
  | "event-console"
  | "mcp"
  | "models"
  | "overview"
  | "tools"
  | "skills"
  | "user"
  ;

export type TaskArtifactKind =
  | "report"
  | "strategy"
  | "factor"
  | "data"
  | "screenshot"
  | "json"
  | "run"
  | "approval"
  | "note"
  | "file"
  | "code"
  | "script"
  | "terminal_output"
  | "quote_snapshot"
  | "news_digest"
  | "chart"
  | "table"
  | "patch";

export interface TaskArtifact {
  id: string;
  kind: TaskArtifactKind;
  title: string;
  description?: string;
  status?: string;
  source?: string;
  sourceView?: MainView;
  createdAt?: string;
  path?: string;
  targetPath?: string;
  href?: string;
  severity?: "info" | "warning" | "critical";
  thumbnailPath?: string;
  value?: unknown;
}

export interface AgentArtifactRecord {
  artifact_id: string;
  user_id?: string;
  session_id?: string;
  run_id?: string;
  trace_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  kind: TaskArtifactKind | string;
  title: string;
  path?: string;
  uri?: string;
  mime_type?: string;
  size_bytes?: number;
  sha256?: string;
  preview_text?: string;
  preview_json?: unknown;
  source_id?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface AgentSourceRecord {
  source_id: string;
  user_id?: string;
  session_id?: string;
  run_id?: string;
  trace_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  provider?: string;
  source_type: string;
  title?: string;
  url?: string;
  published_at?: string;
  fetched_at?: string;
  data_timestamp?: string;
  excerpt?: string;
  source_tier?: string;
  credibility_score?: number;
  metadata?: Record<string, unknown>;
  created_at?: string;
  [key: string]: unknown;
}

export interface TaskReviewComment {
  id: string;
  targetId: string;
  targetType: "artifact" | "run" | "page" | "screenshot" | "thread";
  body: string;
  status?: "open" | "resolved";
  createdAt?: string;
  targetPath?: string;
  severity?: "info" | "warning" | "critical";
}

export interface TaskContextSummary {
  projectLabel: string;
  threadLabel: string;
  runLabel: string;
  mode: "finance_safe" | "hermes_full";
  backendMode: "mock" | "live";
  endpoint: string;
  healthStatus: string;
  pendingApprovals: number;
  pendingIntents: number;
  artifactCount: number;
}
export type CapabilityTab = "overview" | "coverage" | "hermes" | "mcp" | "connectors" | "factory" | "incubation" | "skills" | "plugins" | "ai";

export interface TaskThread {
  id: string;
  title: string;
  prompt: string;
  createdAt: string;
  status: string;
  sessionId?: string;
  runId?: string;
  lastMessageAt?: string;
  response?: AgentResponse;
}

export type TimelineEventKind = "user" | "assistant" | "tool" | "approval" | "gateway" | "mcp" | "error" | "system" | "event";

export interface SessionHandoffState {
  status?: string;
  handoff_id?: string | null;
  target?: string | null;
  source_run_id?: string | null;
  source_tool_call_id?: string | null;
  context_snapshot_id?: string | null;
  active_run_id?: string | null;
  active_trace_id?: string | null;
  summary?: string | null;
  reason?: string | null;
  updated_at?: string;
  activated_at?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RecentSessionSummary {
  session_id: string;
  title: string;
  user_id?: string;
  created_at?: string;
  updated_at?: string;
  last_message_at?: string;
  last_run_id?: string;
  last_event?: NormalizedRunEvent | Record<string, unknown> | null;
  last_run_summary?: DesktopRunSummary | null;
  message_count?: number;
  has_errors?: boolean;
  has_pending_approval?: boolean;
  status?: string;
  archived?: boolean;
  archived_at?: string | null;
  archived_reason?: string | null;
  handoff_state?: SessionHandoffState | null;
  handoff_status?: string | null;
  handoff_target?: string | null;
  handoff_id?: string | null;
  handoff_context_snapshot_id?: string | null;
  active_agent?: string | null;
  active_context_snapshot_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface HandoffRecord {
  handoff_id: string;
  session_id?: string;
  user_id?: string;
  target?: string | null;
  status?: string;
  runtime_status?: string;
  reason?: string | null;
  summary?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  session_title?: string | null;
  handoff_state?: SessionHandoffState | null;
  active_agent?: string | null;
  active_context_snapshot_id?: string | null;
  resume_context_snapshot_id?: string | null;
  resume_ready?: boolean;
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface HandoffQueuePayload {
  object: "aiask.handoff_queue" | string;
  implementation?: string;
  data: HandoffRecord[];
  count?: number;
  summary?: Record<string, number>;
  filters?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface SessionResumeContextPayload {
  object: "aiask.session_resume_context" | string;
  implementation?: string;
  session_id: string;
  session?: RecentSessionSummary;
  handoff?: HandoffRecord | null;
  handoff_state?: SessionHandoffState | null;
  context_snapshot?: Record<string, unknown> | null;
  resume_context?: {
    session_id?: string;
    handoff_id?: string | null;
    target?: string | null;
    status?: string | null;
    context_snapshot_id?: string | null;
    context_summary_id?: string | null;
    risk_flags?: string[];
    source_message_ids?: string[];
    source_ids?: string[];
    artifact_ids?: string[];
    summary?: string | null;
    reason?: string | null;
    resume_prompt?: string;
    [key: string]: unknown;
  };
  secrets_redacted?: boolean;
}

export interface SessionUndoPayload {
  object: "aiask.session_undo";
  implementation?: string;
  session_id: string;
  turns_requested: number;
  turns_undone: number;
  message_ids: Array<number | string>;
  message_count: number;
  deleted_at?: string;
  deleted_reason?: string;
  deleted_by?: string;
  soft_deleted?: boolean;
  side_effects_rolled_back: boolean;
  external_side_effects: string;
}

export interface SessionArchivePayload {
  object: "aiask.session_archive";
  implementation?: string;
  session_id: string;
  archived: boolean;
  archived_at?: string | null;
  archived_reason?: string | null;
  session?: RecentSessionSummary & { metadata?: Record<string, unknown> };
}

export interface DesktopRunSummary {
  run_id: string;
  session_id?: string;
  status: string;
  response_id?: string;
  created_at?: string;
  updated_at?: string;
  event_count?: number;
  tool_call_count?: number;
  approval_count?: number;
  error_count?: number;
  last_event?: NormalizedRunEvent | null;
  has_errors?: boolean;
  has_pending_approval?: boolean;
}

export interface DesktopWorkbenchSummary {
  recent_sessions: RecentSessionSummary[];
  recent_runs?: DesktopRunSummary[];
  queues: {
    pending_intents: number;
    pending_approvals: number;
    gateway_failed: number;
    mcp_degraded: number;
  };
  access: {
    full_mode_active: boolean;
    control_token_configured?: boolean;
    sessions_admin_available: boolean;
  };
}

export interface NormalizedRunEvent {
  id?: string;
  event?: string;
  event_type?: string;
  run_id?: string;
  created_at?: string;
  status?: string;
  kind?: string;
  title?: string;
  severity?: string;
  tool_name?: string | null;
  error_message?: string | null;
  jump_target?: MainView | string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RunTraceEvalCheck {
  id: string;
  label?: string;
  status: "pass" | "warn" | "fail" | string;
  detail?: string;
  evidence?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RunTraceEvalPayload {
  object: "aiask.run_trace_eval" | string;
  implementation?: string;
  run_id: string;
  session_id?: string | null;
  status: "healthy" | "degraded" | "failed" | string;
  score?: number;
  checks: RunTraceEvalCheck[];
  summary: {
    event_count?: number;
    tool_invocation_count?: number;
    failed_tool_invocation_count?: number;
    context_snapshot_count?: number;
    source_count?: number;
    artifact_count?: number;
    handoff_event_count?: number;
    guardrail_event_count?: number;
    error_event_count?: number;
    [key: string]: unknown;
  };
  latest_context_snapshot?: Record<string, unknown> | null;
  risk_flags?: string[];
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface TimelineEvent {
  id: string;
  kind: TimelineEventKind;
  title: string;
  subtitle?: string;
  body?: string;
  status?: string;
  severity?: string;
  jumpTarget?: MainView | string;
  payload?: unknown;
}

export interface DiagnosticsSummary {
  status: string;
  coverage?: number;
  complete?: number;
  implementedFeatures?: number;
  featureCount?: number;
  liveStatus?: string;
}

export interface HermesStatus {
  object: string;
  implementation: string;
  baseline: string;
  baseline_version?: string;
  baseline_release_tag?: string;
  embedded_vendor_runtime: boolean;
  full_mode_enabled: boolean;
  full_mode_active: boolean;
  full_scope?: string;
  evaluated_toolset?: string;
  parity?: CapabilityParity;
  platform_gateway?: unknown;
  terminal_backends?: unknown[];
  learning_loop?: unknown;
  rl_training?: unknown;
  tui?: unknown;
  providers?: unknown;
  memory?: unknown;
  acp?: unknown;
  security?: unknown;
  skill_packs?: unknown;
}

export interface CapabilityMatrixItem {
  [key: string]: unknown;
  reference: string;
  feature?: string;
  area: string;
  required?: boolean;
  aiask_tools: string[];
  missing_aiask_tools: string[];
  code_status?: "present" | "missing" | string;
  mock_status?: "passed" | "blocked" | string;
  live_status?: "not_required" | "skipped_missing_credentials" | "ready" | string;
  required_env?: string[];
  description?: string;
  status: "implemented" | "partial" | "blocked" | "skipped_missing_credentials" | "planned" | "excluded" | "live_unverified" | "unconfigured" | "failed" | string;
}

export interface CapabilityDeltaSummary {
  baseline?: string;
  release_tag?: string;
  total?: number;
  implemented_count?: number;
  partial_count?: number;
  missing_count?: number;
  excluded_by_design_count?: number;
  implemented?: CapabilityMatrixItem[];
  partial?: CapabilityMatrixItem[];
  missing?: CapabilityMatrixItem[];
  excluded_by_design?: CapabilityMatrixItem[];
}

export interface CapabilityParity {
  object: string;
  baseline: string;
  baseline_version?: string;
  baseline_release_tag?: string;
  scope: string;
  legacy_scope?: string;
  embedded_vendor_runtime: boolean;
  required_count: number;
  covered_count: number;
  complete_count: number;
  coverage_ratio: number;
  complete_ratio: number;
  status: string;
  matrix: CapabilityMatrixItem[];
  feature_mapping?: CapabilityMatrixItem[];
  missing_features?: CapabilityMatrixItem[];
  core_code_status?: string;
  core_missing_hermes_tools?: CapabilityMatrixItem[];
  core_missing_gateway_platforms?: CapabilityMatrixItem[];
  core_missing_features?: CapabilityMatrixItem[];
  v014_delta?: CapabilityDeltaSummary;
  v016_delta?: CapabilityDeltaSummary;
  strict_hermes_tool_count?: number;
  strict_gateway_platform_count?: number;
  missing_hermes_tools?: CapabilityMatrixItem[];
  missing_gateway_platforms?: CapabilityMatrixItem[];
  live_unverified_count?: number;
  excluded_by_design_count?: number;
  excluded_by_design_features?: CapabilityMatrixItem[];
  implemented_features_count?: number;
  feature_count?: number;
  code_status?: string;
  mock_status?: string;
  live_status?: string;
  strict_status?: string;
}

export interface FullModeConsoleData {
  parity?: CapabilityParity;
  readiness?: unknown;
  processes?: unknown[];
  browserSessions?: unknown[];
  skills?: unknown;
  plugins?: unknown[];
  mcpServers?: unknown[];
  mcpTools?: unknown[];
  mcpResources?: unknown[];
  mcpPrompts?: unknown[];
  mcpOauth?: unknown[];
  webhooks?: unknown[];
  approvals?: unknown[];
  jobs?: unknown[];
  runEvents?: unknown[];
  gatewayStatus?: unknown;
  gatewayPlatforms?: unknown[];
  gatewayMessages?: unknown[];
  gatewayDirectory?: unknown[];
  terminalBackends?: unknown[];
  terminalSessions?: unknown[];
  learningStatus?: unknown;
  learningReview?: unknown[];
  rlEnvironments?: unknown;
  rlRuns?: unknown[];
  homeAssistant?: unknown;
  moa?: unknown;
  dynamicMcpTools?: unknown[];
  dynamicPluginTools?: unknown[];
  pluginHooks?: unknown;
  tuiController?: unknown;
  rlReadiness?: unknown;
  providers?: unknown;
  memory?: unknown;
  acp?: unknown;
  security?: unknown;
  skillPacks?: unknown;
}

export interface HermesConsoleSnapshot {
  hermesStatus: HermesStatus;
  hermesTools: ToolCatalogItem[];
  fullConsole: FullModeConsoleData;
  message: string;
}

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

export interface McpServerView {
  name: string;
  domain?: string;
  transport?: string;
  configured?: boolean;
  enabled?: boolean;
  tools?: unknown[];
  resources?: unknown[];
  prompts?: unknown[];
  partial_success?: boolean;
  warnings?: unknown[];
  unsupported_methods?: string[];
  [key: string]: unknown;
}

export interface McpToolView {
  name: string;
  wrapped_name?: string;
  server?: string;
  description?: string;
  transport?: string;
  domain?: string;
  configured?: boolean;
  [key: string]: unknown;
}

export interface SkillView {
  name: string;
  description?: string;
  path?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface PluginSummaryView {
  name?: string;
  enabled?: boolean;
  ready?: boolean;
  configured?: boolean;
  status?: string;
  failure_reason?: string | null;
  error?: string | null;
  error_code?: string | null;
  test_status?: string;
  tool_count?: number;
  command_count?: number;
  hook_count?: number;
  source?: string;
  version?: string;
  description?: string;
  tools?: unknown[];
  commands?: unknown[];
  hooks?: unknown[];
  [key: string]: unknown;
}

export interface SkillPackStatusView {
  object?: string;
  status?: string;
  packs?: unknown[];
  installed_count?: number;
  available_count?: number;
  missing?: unknown[];
  [key: string]: unknown;
}

export interface SettingsFieldSchema {
  key: "endpoint" | "apiToken" | "controlToken" | "agentMode";
  label: string;
  type: "text" | "password" | "select";
  description?: string;
  options?: Array<{ label: string; value: string }>;
}

export interface StrategyFactoryView {
  status?: ToolEnvelope | null;
  runs?: ToolEnvelope | null;
  review_snapshot?: ToolEnvelope | null;
}

export interface LocalProfile {
  object?: string;
  user_id: string;
  profile_name: string;
  storage?: string;
  path?: string;
  updated_at?: string | null;
  status?: string;
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface UserActivityEvent {
  id?: number | string;
  user_id?: string;
  session_id?: string | null;
  run_id?: string | null;
  trace_id?: string | null;
  page_key?: string | null;
  route?: string | null;
  event_type: string;
  target_type?: string | null;
  target_id?: string | null;
  target_label?: string | null;
  target_testid?: string | null;
  payload?: Record<string, unknown>;
  source?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface ToolInvocationAudit {
  id?: number | string;
  invocation_id?: string;
  user_id?: string | null;
  session_id?: string | null;
  run_id?: string | null;
  trace_id?: string | null;
  tool_name: string;
  capability?: string | null;
  category?: string | null;
  side_effect?: string | null;
  status: string;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
  error_code?: string | null;
  error_summary?: string | null;
  duration_ms?: number | null;
  approval_id?: string | null;
  action_intent_id?: string | null;
  source_chain?: string[];
  secrets_redacted?: boolean;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface FeedbackEvent {
  id?: number | string;
  feedback_id?: string;
  user_id?: string | null;
  session_id?: string | null;
  run_id?: string | null;
  target_type: string;
  target_id?: string | null;
  feedback_type: string;
  rating?: number | null;
  comment?: string | null;
  allow_learning?: boolean;
  payload?: Record<string, unknown>;
  created_at?: string;
  [key: string]: unknown;
}

export interface UserDataPolicy {
  user_id: string;
  event_ttl_days: number;
  audit_ttl_days: number;
  run_event_ttl_days: number;
  tool_payload_ttl_days: number;
  conversation_retention: string;
  allow_product_analytics: boolean;
  allow_learning: boolean;
  updated_at?: string;
  [key: string]: unknown;
}

export interface UserActivityPayload {
  object: string;
  user_id: string;
  sessions: RecentSessionSummary[];
  runs: RunRecord[];
  events: UserActivityEvent[];
  tool_invocations: ToolInvocationAudit[];
  feedback: FeedbackEvent[];
  policy: UserDataPolicy;
  secrets_redacted?: boolean;
}

export interface UserAnalyticsSummary {
  object: string;
  scope: string;
  user_id?: string | null;
  totals: {
    events: number;
    tool_invocations: number;
    feedback: number;
  };
  events_by_type: Array<Record<string, unknown>>;
  pages: Array<Record<string, unknown>>;
  tools: Array<Record<string, unknown>>;
  feedback: Array<Record<string, unknown>>;
  secrets_redacted?: boolean;
}

export interface UserDataExport {
  object: string;
  user_id: string;
  exported_at: string;
  profile_policy: UserDataPolicy;
  sessions: RecentSessionSummary[];
  messages: Array<Record<string, unknown>>;
  runs: RunRecord[];
  run_events: NormalizedRunEvent[];
  activity_events: UserActivityEvent[];
  tool_invocations: ToolInvocationAudit[];
  feedback: FeedbackEvent[];
  sources?: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  analytics: UserAnalyticsSummary;
  secrets_redacted?: boolean;
}

export interface UserDataDeleteResult {
  object: string;
  user_id: string;
  dry_run: boolean;
  hard_delete: boolean;
  anonymized_user_id?: string | null;
  counts: Record<string, number>;
  deleted_at?: string;
  external_side_effects?: string;
  secrets_redacted?: boolean;
}

export interface RetentionSweepResult {
  object: string;
  dry_run: boolean;
  user_id?: string | null;
  counts: Record<string, number>;
  tables: string[];
  market_data_affected: boolean;
  secrets_redacted?: boolean;
}

export interface UserLearningDataset {
  object: string;
  user_id: string;
  allowed: boolean;
  items: Array<Record<string, unknown>>;
  count?: number;
  reason?: string;
  secrets_redacted?: boolean;
}

export interface WorkflowRecommendationPayload {
  object: string;
  user_id: string;
  data_source: string;
  data: Array<Record<string, unknown>>;
  count: number;
  secrets_redacted?: boolean;
}

export interface DesktopSettingsStatus {
  object: string;
  agent: Record<string, unknown>;
  llm: {
    ai_status?: AiStatus;
    providers?: unknown;
  };
  memory?: unknown;
  databases: Record<string, unknown>;
  stock_data_sources?: StockDataSourcesStatus;
  profile: LocalProfile;
  secrets_redacted: boolean;
}

export interface StockDataSourcePreset {
  provider: string;
  label: string;
  markets: string[];
  categories: string[];
  auth_type: string;
  default_base_url?: string | null;
  default_host?: string | null;
  default_port?: number | null;
  required_fields?: string[];
  optional_fields?: string[];
  env_keys?: string[];
  documentation_url?: string | null;
  note?: string | null;
}

export interface StockDataSourceConfig {
  id?: string;
  provider: string;
  name?: string;
  enabled?: boolean;
  priority?: number;
  base_url?: string | null;
  api_key?: string;
  token?: string;
  host?: string | null;
  port?: number | string | null;
  username?: string;
  password?: string;
  client_path?: string | null;
  account_id?: string | null;
  session_id?: string | null;
  symbol?: string | null;
  interval?: string | null;
  dataset?: string | null;
  timeout_seconds?: number | string | null;
  rate_limit_per_minute?: number | string | null;
  markets?: string[];
  notes?: string | null;
  extra?: Record<string, unknown>;
  configured?: boolean;
  status?: string;
  label?: string;
  auth_type?: string;
  required_fields?: string[];
  optional_fields?: string[];
  api_key_configured?: boolean;
  source?: string;
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface StockDataSourcesStatus {
  object: string;
  status: string;
  configured_count: number;
  ready_count: number;
  presets: StockDataSourcePreset[];
  sources: StockDataSourceConfig[];
  config_path?: string;
  config_source?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface StockDataSourceTestResult {
  object: string;
  provider: string;
  mode: string;
  success: boolean;
  status: string;
  configured?: boolean;
  latency_ms?: number;
  sample_count?: number;
  http_status?: number;
  error_code?: string;
  error?: string | null;
  source?: StockDataSourceConfig;
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface AuthState {
  controlTokenConfigured: boolean;
  controlTokenProvided: boolean;
  controlAuthorized?: boolean;
  fullModeEnabled?: boolean;
  fullModeActive?: boolean;
  reason?: string | null;
}

export interface ConnectorDetail {
  id?: string;
  name: string;
  type: string;
  category?: string;
  enabled?: boolean;
  configured?: boolean;
  connected?: boolean;
  status?: string;
  description?: string;
  env_keys?: string[];
  missing_env?: string[];
  metadata?: Record<string, unknown>;
}

export interface GatewayPlatform {
  platform?: string;
  name?: string;
  enabled?: boolean;
  configured?: boolean;
  connected?: boolean;
  status?: string;
  missing_env?: string[];
  [key: string]: unknown;
}

export interface GatewayMessage {
  message_id?: string;
  id?: string;
  platform?: string;
  direction?: string;
  target?: string;
  status?: string;
  message?: string;
  content?: string;
  created_at?: string;
  updated_at?: string;
  last_retry_at?: string;
  retry_count?: number;
  error?: string | null;
  error_message?: string | null;
  failure_reason?: string | null;
  error_code?: string | null;
  [key: string]: unknown;
}

export interface GatewayDaemonStatus {
  object?: string;
  data?: {
    enabled?: boolean;
    running?: boolean;
    listeners?: Record<string, unknown>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface PluginCommand {
  name?: string;
  command?: string;
  description?: string;
  enabled?: boolean;
  schema?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WebhookSubscription {
  webhook_id: string;
  name: string;
  events?: string[];
  prompt?: string;
  deliver?: unknown;
  enabled?: boolean;
  secret_configured?: boolean;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface LearningProposal {
  proposal_id?: string;
  id?: string;
  status?: string;
  title?: string;
  summary?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface RlRun {
  run_id?: string;
  environment?: string;
  status?: string;
  started_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ApprovalItem {
  approval_id?: string;
  id?: string;
  status?: string;
  action?: string;
  reason?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface JobRunRecord {
  job_run_id: string;
  job_id: string;
  status: string;
  response_id?: string | null;
  run_id?: string | null;
  error?: string | null;
  duration_ms?: number | null;
  started_at?: string;
  finished_at?: string | null;
  payload?: Record<string, unknown>;
}

export interface FactoryEventRecord {
  event_id?: string;
  id?: string;
  event_name?: string;
  name?: string;
  event_type?: string;
  status?: string;
  source?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface DesktopDataStatus {
  object: string;
  status: string;
  database?: Record<string, unknown>;
  presets?: QuantPresetPayload;
  quality_gate?: ToolEnvelope;
  data_validation?: unknown;
  freshness?: unknown;
  codes: string[];
  max_stale_days: number;
  missing_count: number;
  stale_count: number;
  secrets_redacted?: boolean;
}

export interface DesktopDataSyncPlan {
  object: string;
  status: string;
  data_status?: DesktopDataStatus;
  intent_request: {
    action: string;
    params: Record<string, unknown>;
    rationale?: string;
  };
  commands?: Array<Record<string, unknown>>;
  side_effect?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface FactorFactoryStatus {
  object: string;
  status: string;
  configured?: boolean;
  factory?: Record<string, unknown>;
  active_factors?: Array<Record<string, unknown>>;
  engine_health?: Record<string, unknown>;
  pool_health?: Record<string, unknown>;
  error?: string;
  error_code?: string;
  secrets_redacted?: boolean;
}

export interface QuantPresetPayload {
  object: string;
  data_status: {
    status: string;
    database?: {
      backend?: string;
      path?: string;
      configured?: boolean;
      writable?: boolean;
      sources?: string[];
      setup_hint?: string;
      required_for_full_quant?: boolean;
    };
  };
  templates: Array<{
    id: string;
    label: string;
    universe: string[];
    benchmark: string;
    factors: string[];
    rebalance_frequency: string;
    cost_bps: number;
    slippage_bps: number;
    risk_limits?: Record<string, unknown>;
  }>;
  factor_library: string[];
  risk_defaults: Record<string, unknown>;
  disclaimer: string;
}

export interface QuantResearchReport {
  object: string;
  research_id: string;
  status: string;
  summary: {
    universe_size?: number;
    factor_count?: number;
    benchmark?: string;
    failed_stage?: string | null;
  };
  data_window?: Record<string, unknown>;
  universe?: string[];
  factor_evidence?: unknown;
  backtest_assumptions?: Record<string, unknown>;
  backtest?: unknown;
  portfolio_risk?: unknown;
  strategy_factory?: unknown;
  limitations?: string[];
  disclaimer?: string;
  stages?: Array<{ name: string; status: string; output?: unknown; error?: string | null }>;
}

export interface QuantResearchRun {
  research_id: string;
  status: string;
  payload: {
    arguments?: Record<string, unknown>;
    stages?: Array<{ name: string; status: string; output?: unknown; error?: string | null }>;
  };
  report: QuantResearchReport;
  created_at?: string;
  updated_at?: string;
}

export interface CapabilityIssue {
  area?: string;
  reference?: string;
  feature?: string;
  hermes_tool?: string;
  platform?: string;
  status?: string;
  error?: string;
  missing_aiask_tools?: string[];
  [key: string]: unknown;
}

export interface CapabilityDomain {
  status?: string;
  gated?: boolean;
  reason?: string;
  counts?: Record<string, number>;
  items?: unknown[];
  [key: string]: unknown;
}

export interface FinancialReadinessGate {
  name: string;
  status: string;
  required: boolean;
  detail: string;
  evidence?: Record<string, unknown>;
}

export interface FinancialNextAction {
  action_id: string;
  title: string;
  detail: string;
  priority: "critical" | "recommended" | "optional" | string;
  target_page: MainView | string;
  endpoint?: string;
  env_vars?: string[];
  gate?: string;
}

export interface FinancialSystemReadiness {
  object: string;
  status: string;
  production_ready: boolean;
  required_gates: FinancialReadinessGate[];
  optional_gates: FinancialReadinessGate[];
  next_actions?: FinancialNextAction[];
  live_smoke?: {
    object?: string;
    status?: string;
    script?: string;
    working_directory?: string;
    self_test_command?: string;
    live_command?: string;
    environment_note?: string;
    checks?: Array<{ name?: string; method?: string; path?: string; observes?: string[] }>;
    [key: string]: unknown;
  };
  summary: Record<string, number>;
  parity?: Record<string, unknown>;
  disclaimer?: string;
}

export type FinancialManagerMode = "read_only" | "stateful_intent" | "blocked" | string;

export interface FinancialManagerGroup {
  id: string;
  label: string;
  description?: string;
}

export interface FinancialManagerAction {
  capability_id: string;
  action_id: string;
  group: string;
  label: string;
  mode: FinancialManagerMode;
  execution_mode?: "read_only" | "intent_only" | "confirmed_execute" | "confirmed_execute_dry_run_only" | "blocked" | string;
  status?: string;
  available?: boolean;
  tool?: string;
  wrapped_tool?: string;
  mcp_tool?: string;
  mcp_action?: string;
  intent_action?: string;
  default_params?: Record<string, unknown>;
  blocked_reason?: string;
  side_effect?: Record<string, unknown>;
  availability?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface FinancialManagerCatalog {
  object: string;
  groups: FinancialManagerGroup[];
  actions: FinancialManagerAction[];
  summary?: Record<string, number>;
  safety?: Record<string, unknown>;
  stateful_execution?: string;
  confirmed_action_scope?: string[];
  dry_run_only_actions?: string[];
  secrets_redacted?: boolean;
}

export interface FinancialManagerStatus {
  object: string;
  status: string;
  readiness?: FinancialSystemReadiness | Record<string, unknown>;
  catalog_summary?: Record<string, number>;
  mcp?: Record<string, unknown>;
  stateful_execution?: string;
  confirmed_action_scope?: string[];
  dry_run_only_actions?: string[];
  broker?: Record<string, unknown>;
  recent_intents?: unknown[];
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface FinancialManagerQueryResult {
  object: string;
  capability_id?: string;
  action_id?: string;
  tool?: string;
  success: boolean;
  data?: unknown;
  error?: string | null;
  error_code?: string;
  meta?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface FinancialManagerIntentResult {
  object: string;
  capability_id?: string;
  action_id?: string;
  success: boolean;
  data?: unknown;
  error?: string | null;
  error_code?: string;
  meta?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface BrokerConnectorReadiness {
  provider: string;
  label?: string;
  status: string;
  configured: boolean;
  ready: boolean;
  read_only: boolean;
  live_trading_enabled: boolean;
  required_env?: string[];
  missing_env?: string[];
  optional_env?: string[];
  required_tools?: string[];
  missing_tools?: string[];
  environment_checks?: string[];
  authorization_notes?: string[];
  test_entry?: {
    method?: string;
    path?: string;
    consent_required?: boolean;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface BrokerReadinessPayload {
  object: string;
  status: string;
  connectors: BrokerConnectorReadiness[];
  mcp?: Record<string, unknown>;
  latest_analytics?: BrokerAnalyticsRecord | null;
  live_trading_enabled: boolean;
  read_only: boolean;
  secrets_redacted?: boolean;
}

export interface BrokerAccountSnapshot {
  snapshot_id?: string;
  broker_profile_id?: string;
  user_id?: string;
  provider?: string;
  account_ref_hash?: string;
  currency?: string;
  total_asset?: number | null;
  cash_available?: number | null;
  market_value?: number | null;
  frozen_cash?: number | null;
  buying_power?: number | null;
  observed_at?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrokerPositionSnapshot {
  snapshot_id?: string;
  broker_profile_id?: string;
  user_id?: string;
  provider?: string;
  symbol?: string;
  exchange?: string | null;
  name?: string | null;
  quantity?: number | null;
  available_quantity?: number | null;
  cost_basis?: number | null;
  last_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  position_pct?: number | null;
  observed_at?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrokerOrderSnapshot {
  snapshot_id?: string;
  broker_profile_id?: string;
  user_id?: string;
  provider?: string;
  order_ref_hash?: string;
  symbol?: string;
  side?: string | null;
  order_type?: string | null;
  price?: number | null;
  quantity?: number | null;
  filled_quantity?: number | null;
  status?: string | null;
  submitted_at?: string | null;
  updated_at?: string | null;
  observed_at?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrokerDealSnapshot {
  snapshot_id?: string;
  broker_profile_id?: string;
  user_id?: string;
  provider?: string;
  deal_ref_hash?: string;
  order_ref_hash?: string;
  symbol?: string;
  side?: string | null;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  fee?: number | null;
  occurred_at?: string | null;
  observed_at?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrokerProfile {
  broker_profile_id: string;
  user_id?: string;
  provider?: string;
  display_name?: string;
  account_ref_hash?: string;
  market?: string;
  read_only_enabled?: boolean;
  write_enabled?: boolean;
  consent_status?: string;
  last_sync_at?: string | null;
  status?: string;
  error_code?: string | null;
  [key: string]: unknown;
}

export interface BrokerAnalyticsRecord {
  analytics_id?: string;
  broker_profile_id?: string;
  user_id?: string;
  provider?: string;
  period_start?: string | null;
  period_end?: string | null;
  metrics?: Record<string, unknown>;
  signals?: Record<string, unknown>;
  risk_flags?: Array<Record<string, unknown>>;
  source_snapshot_ids?: Record<string, unknown>;
  model_version?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrokerSnapshotData {
  profiles?: BrokerProfile[];
  accounts?: BrokerAccountSnapshot[];
  positions?: BrokerPositionSnapshot[];
  orders?: BrokerOrderSnapshot[];
  deals?: BrokerDealSnapshot[];
  analytics?: BrokerAnalyticsRecord | null;
}

export interface BrokerSnapshotPayload {
  object: string;
  success: boolean;
  data?: BrokerSnapshotData | null;
  error?: string | null;
  error_code?: string;
  read_only: boolean;
  live_trading_enabled: boolean;
  secrets_redacted?: boolean;
  source_chain?: string[];
  generated_at?: number;
}

export interface BrokerSyncPayload extends BrokerSnapshotPayload {
  data?: {
    sync_id?: string;
    profile?: BrokerProfile;
    counts?: Record<string, number>;
    errors?: Array<Record<string, unknown>>;
    analytics?: BrokerAnalyticsRecord;
  } | null;
}

export interface BrokerAnalyticsPayload {
  object: string;
  success: boolean;
  data?: { analytics?: BrokerAnalyticsRecord | null } | null;
  error?: string | null;
  error_code?: string;
  read_only: boolean;
  live_trading_enabled: boolean;
  secrets_redacted?: boolean;
  source_chain?: string[];
}

export interface CapabilityWorkbenchPayload {
  object: string;
  summary: {
    status: string;
    source?: "live_backend" | "mock_fixture" | "gated" | "offline" | string;
    counts: Record<string, number>;
    issue_count: number;
    control: {
      authorized: boolean;
      reason?: string | null;
      full_mode_enabled?: boolean;
      control_token_configured?: boolean;
      control_authorized?: boolean;
      control_reason?: string | null;
      gated_reason?: string | null;
    };
    refreshed_at: number;
  };
  hermes: {
    status: Partial<HermesStatus>;
    parity: CapabilityParity;
    readiness: unknown;
    tool_mapping: CapabilityMatrixItem[];
    platform_mapping: CapabilityMatrixItem[];
    feature_mapping: CapabilityMatrixItem[];
    issues: CapabilityIssue[];
    providers?: unknown;
    memory?: unknown;
    acp?: unknown;
    security?: unknown;
    skill_packs?: unknown;
  };
  mcp: {
    gated: boolean;
    reason?: string | null;
    registration_status?: string;
    discovery_status?: string;
    discovered_counts?: {
      tools?: number;
      resources?: number;
      prompts?: number;
    };
    configured?: boolean;
    config_path?: string;
    config_exists?: boolean;
    detected_service_port?: string | null;
    detected_service_url?: string | null;
    suggested_registration_url?: string | null;
    auth_configured?: boolean;
    auth_env_vars?: string[];
    missing_auth_env_vars?: string[];
    partial_success?: boolean;
    warnings?: unknown[];
    unsupported_methods?: string[];
    error_code?: string | null;
    detail?: string | null;
    servers: McpServerView[];
    tools: McpToolView[];
    resources: unknown[];
    prompts: unknown[];
    oauth: unknown[];
  };
  strategy_factory: StrategyFactoryView;
  quant?: {
    presets?: QuantPresetPayload;
    recent_runs?: QuantResearchRun[];
    data_status?: QuantPresetPayload["data_status"];
    status?: string;
  };
  financial_system?: FinancialSystemReadiness;
  skills: { gated?: boolean; reason?: string; skills?: SkillView[]; root?: string; [key: string]: unknown };
  skill_packs?: unknown;
  plugins?: unknown;
  providers?: unknown;
  memory?: unknown;
  acp?: unknown;
  security?: unknown;
  ai: AiStatus;
  raw_refs: Record<string, string>;
}

export interface IntentRecord {
  intent_id: string;
  action: string;
  target_tool: string;
  target_action: string;
  status: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
}
