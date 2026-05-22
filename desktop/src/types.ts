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

export type InspectorTab = "details" | "diagnostics" | "tools" | "skills" | "intents" | "settings";
export type MainView =
  | "overview"
  | "workbench"
  | "agent"
  | "coverage"
  | "models"
  | "data"
  | "mcp"
  | "automation"
  | "strategy-factory"
  | "factor-factory"
  | "incubation"
  | "quant"
  | "capabilities"
  | "diagnostics"
  | "tools"
  | "skills"
  | "user"
  | "settings"
  | "event-console";
export type CapabilityTab = "overview" | "coverage" | "hermes" | "mcp" | "connectors" | "factory" | "incubation" | "skills" | "plugins" | "ai";

export interface TaskThread {
  id: string;
  title: string;
  prompt: string;
  createdAt: string;
  status: string;
  sessionId?: string;
  runId?: string;
  response?: AgentResponse;
}

export type TimelineEventKind = "user" | "assistant" | "tool" | "approval" | "event";

export interface TimelineEvent {
  id: string;
  kind: TimelineEventKind;
  title: string;
  subtitle?: string;
  body?: string;
  status?: string;
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

export interface FinancialSystemReadiness {
  object: string;
  status: string;
  production_ready: boolean;
  required_gates: FinancialReadinessGate[];
  optional_gates: FinancialReadinessGate[];
  summary: Record<string, number>;
  parity?: Record<string, unknown>;
  disclaimer?: string;
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
