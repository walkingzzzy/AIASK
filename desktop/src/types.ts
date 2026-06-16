export * from "./types/ai";
export * from "./types/finance";
export * from "./types/workbench";

import type { AiStatus } from "./types/ai";
import type { QuantPresetPayload, QuantResearchRun } from "./types/finance";
import type { NormalizedRunEvent, RecentSessionSummary, RunRecord } from "./types/workbench";

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

export type InspectorTab = "details" | "artifacts" | "review" | "diagnostics" | "tools" | "skills" | "intents" | "settings";
export type MainView =
  | "workbench"
  | "projects-contexts"
  | "sessions"
  | "runs-events"
  | "artifacts"
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

export type CapabilityTab = "overview" | "coverage" | "hermes" | "mcp" | "connectors" | "factory" | "incubation" | "skills" | "plugins" | "ai";

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
