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
