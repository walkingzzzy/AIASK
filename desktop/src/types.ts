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

export type TaskArtifactKind = "report" | "strategy" | "factor" | "data" | "screenshot" | "json" | "run" | "approval" | "note";

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
  severity?: "info" | "warning" | "critical";
  thumbnailPath?: string;
  value?: unknown;
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
  metadata?: Record<string, unknown>;
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

export interface CapabilityParity {
  object: string;
  baseline: string;
  scope: string;
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
  v014_delta?: {
    baseline?: string;
    release_tag?: string;
    total?: number;
    implemented_count?: number;
    partial_count?: number;
    missing_count?: number;
    implemented?: CapabilityMatrixItem[];
    partial?: CapabilityMatrixItem[];
    missing?: CapabilityMatrixItem[];
  };
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
  config_source?: {
    loaded?: boolean;
    path?: string | null;
    source?: string;
    secrets_redacted?: boolean;
  };
  secrets_redacted: boolean;
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

export interface DesktopSettingsStatus {
  object: string;
  agent: Record<string, unknown>;
  llm: {
    ai_status?: AiStatus;
    providers?: unknown;
  };
  memory?: unknown;
  databases: Record<string, unknown>;
  profile: LocalProfile;
  secrets_redacted: boolean;
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
