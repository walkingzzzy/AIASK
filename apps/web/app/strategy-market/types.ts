import type { Strategy } from '@/components/strategy-card';

export type { Strategy };

// ---------------------------------------------------------------------------
// List page types (strategy-market/page.tsx)
// ---------------------------------------------------------------------------

export type RankingResponse = { strategies?: Strategy[] } | Strategy[];

export type FactoryAutonomyTaskBrief = {
  task_id?: string;
  task_source?: string;
  opportunity_type?: string;
  generation_limit?: number;
  generated_count?: number;
};

export type FactoryRunSummary = {
  candidates_spawned?: number;
  candidates_passed_backtest?: number;
  candidates_after_dedup?: number;
  passed_quality_gate?: number;
  autonomy_generated?: number;
  autonomy_task_count?: number;
  event_task_count?: number;
  snapshot_task_count?: number;
  snapshot_degraded?: boolean;
  snapshot_completion_ratio?: number;
  snapshot_failure_reason_count?: number;
  task_source_counts?: Record<string, number>;
  scanner_task_types?: Record<string, number>;
  event_snapshot_mixed?: boolean;
  autonomy_task_briefs?: FactoryAutonomyTaskBrief[];
  submitted?: number;
  eliminated?: number;
  elapsed_seconds?: number;
};

export type FactoryStatusResponse = {
  running?: boolean;
  run_time?: string;
  last_run?: string | null;
  last_summary?: FactoryRunSummary;
  last_result?: {
    status?: string;
    error?: string;
  };
};

export type CapabilityResponse = {
  daily_snapshot?: boolean;
  paper_incubation?: boolean;
  incubation_pipeline?: boolean;
  runtime_risk?: boolean;
  risk_snapshots?: boolean;
  risk_recovery?: boolean;
  execution_risk?: boolean;
  runtime_controls?: boolean;
  promotion_pipeline?: boolean;
  projection_snapshots?: boolean;
  event_replay?: boolean;
  vector_platform?: boolean;
  vector_governance?: boolean;
  persistent_vector_index?: boolean;
  ann_vector_search?: boolean;
  ai_generation?: boolean;
  multi_agent_review?: boolean;
  quality_governance?: boolean;
  domain_events?: boolean;
  domain_projection?: boolean;
  runtime_cycle?: boolean;
};

export type DailySnapshotResponse = {
  snapshot_date?: string;
  fear_greed_index?: number;
  degraded?: boolean;
  failure_reasons?: string[];
  missing_fields?: string[];
  hot_sectors?: string[];
  cold_sectors?: string[];
  summary?: {
    listed_count?: number;
  };
  completeness?: {
    completion_ratio?: number;
  };
};

export type FactoryRunsResponse = {
  items?: Array<{
    run_id?: string;
    status?: string;
    started_at?: string;
    completed_at?: string | null;
    elapsed_seconds?: number;
    error?: string | null;
    summary?: FactoryRunSummary;
    stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
  }>;
  count?: number;
};

export type FactoryRunDetailResponse = {
  run_id?: string;
  status?: string;
  started_at?: string;
  completed_at?: string | null;
  elapsed_seconds?: number;
  error?: string | null;
  summary?: FactoryRunSummary;
  snapshot_summary?: Record<string, string | number | null | undefined>;
  stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
};

export type FactoryRunItem = NonNullable<FactoryRunsResponse['items']>[number];
export type RunStatusFilter = 'all' | 'success' | 'failed';
export type TrendMetricKey =
  | 'candidates_spawned'
  | 'submitted'
  | 'passed_quality_gate'
  | 'elapsed_seconds'
  | 'autonomy_task_count'
  | 'event_task_count'
  | 'snapshot_task_count';

export type CapabilityBadge = {
  key: string;
  label: string;
  enabled: boolean;
};

// ---------------------------------------------------------------------------
// Detail page types (strategy-market/[id]/page.tsx)
// ---------------------------------------------------------------------------

export type StrategyMetric = {
  period?: string;
  total_return?: number;
  annual_return?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  win_rate?: number;
  calmar_ratio?: number;
  trade_count?: number;
};

export type StrategyReview = {
  user_id: string;
  rating: number;
  comment?: string;
  created_at?: string;
};

export type StrategyCore = {
  id: string;
  name: string;
  description?: string;
  strategy_type?: string;
  status?: string;
  author_id?: string;
  subscriber_count?: number;
  avg_rating?: number;
  review_count?: number;
  factor_weights?: Record<string, number>;
  metrics?: StrategyMetric[];
  reviews?: StrategyReview[];
};

export type SignalStatsResponse = {
  hit_rate?: Record<string, number>;
  forward_ic?: Record<string, number>;
  forward_sharpe?: Record<string, number>;
  total_signals?: number;
};

export type Signal = {
  signal_date?: string;
  code?: string;
  signal?: number;
  score?: number;
};

export type SignalsResponse = {
  signals?: Signal[];
  count?: number;
  subscriber?: boolean;
};

export type ReviewReportResponse = {
  passed?: boolean;
  report_type?: string;
  reports?: Array<{
    report_type?: string;
    updated_at?: string;
    summary?: {
      review_source?: string;
      validation_grade?: string;
    };
  }>;
  summary?: {
    status_after_review?: string;
    validation_grade?: string;
    review_source?: string;
  };
  quality_gate?: {
    wf_ic_ir?: number;
    pkf_ic?: number;
    bootstrap_ci_lower?: number;
    param_sensitivity?: number;
    reasons?: string[];
    reason_codes?: string[];
  };
  dedup_report?: {
    duplicate?: boolean;
    match_type?: string | null;
    param_similarity?: number;
    vector_similarity?: number;
    reason?: string;
  };
};

export type StrategyEventsResponse = {
  events?: Array<{
    event_type?: string;
    from_status?: string | null;
    to_status?: string;
    actor_id?: string;
    reason?: string;
    created_at?: string;
    metadata?: Record<string, unknown>;
  }>;
  count?: number;
};

export type IncubationOverviewResponse = {
  status?: string;
  sharpe_ratio?: number;
  max_drawdown?: number;
  total_signals?: number;
  minimum_signal_count?: number;
  hit_rate_5d?: number | null;
  forward_ic_5d?: number | null;
  forward_sharpe_5d?: number | null;
  promotion_ready?: boolean;
  deprecation_risk?: boolean;
  blockers?: string[];
  risk_flags?: string[];
  observed_forward_days?: number[];
  missing_forward_days?: number[];
  forward_returns?: Array<{
    label?: string;
    hit_rate?: number | null;
    forward_ic?: number | null;
    forward_sharpe?: number | null;
  }>;
  blockers_by_period?: Record<string, string[]>;
  risk_flags_by_period?: Record<string, string[]>;
  validation_grade?: string | null;
};

export type IncubationAccount = {
  strategy_id?: string;
  account_id?: string;
  stage?: string;
  status?: string;
  source_run_id?: string;
  metadata?: Record<string, unknown>;
};

export type IncubationMetric = {
  metric_date?: string;
  account_id?: string;
  stage?: string;
  decision?: string;
  nav?: number;
  total_value?: number;
  cash?: number;
  market_value?: number;
  daily_return?: number;
  max_drawdown?: number;
  sharpe_ratio?: number;
  hit_rate_5d?: number;
  forward_ic_5d?: number;
  forward_sharpe_5d?: number;
  total_signals?: number;
  total_orders?: number;
  total_trades?: number;
  turnover_rate?: number;
  exposure_rate?: number;
  alpha_decay?: number;
  drift_score?: number;
};

export type PaperAccount = {
  id?: string;
  name?: string;
  initial_capital?: number;
  current_capital?: number;
  total_value?: number;
  strategy_id?: string;
  account_type?: string;
  incubation_stage?: string;
  promotion_candidate?: boolean;
  status?: string;
  risk_rules?: Record<string, unknown>;
};

export type PaperPosition = {
  account_id?: string;
  stock_code?: string;
  stock_name?: string;
  quantity?: number;
  cost_price?: number;
  current_price?: number;
  market_value?: number;
  profit_rate?: number;
};

export type PaperOrder = {
  id?: number;
  account_id?: string;
  strategy_id?: string;
  signal_date?: string;
  source?: string;
  code?: string;
  direction?: string;
  shares?: number;
  price?: number;
  order_type?: string;
  stop_price?: number | null;
  status?: string;
  commission?: number;
  reason?: string | null;
  filled_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type PaperNav = {
  id?: number;
  account_id?: string;
  nav_date?: string;
  total_value?: number;
  cash?: number;
  market_value?: number;
  daily_return?: number;
  created_at?: string;
};

export type PaperAccountResponse = {
  account?: PaperAccount | null;
  binding?: IncubationAccount | null;
  positions?: PaperPosition[];
  latest_nav?: PaperNav | null;
  order_summary?: {
    total_orders?: number;
    total_trades?: number;
    trade_amount?: number;
  };
};

export type IncubationPipelineSnapshot = {
  id?: number;
  strategy_id?: string;
  account_id?: string | null;
  pipeline_stage?: string;
  pipeline_status?: string;
  observed_days?: number;
  promote_streak?: number;
  halt_streak?: number;
  latest_decision?: string;
  readiness_score?: number;
  next_action?: string;
  auto_review?: boolean;
  auto_promoted?: boolean;
  blockers?: string[];
  risk_flags?: string[];
  summary?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  task_run_id?: number | null;
  source?: string;
  evaluated_at?: string;
};

export type RuntimeRiskSnapshot = {
  id?: number;
  strategy_id?: string;
  account_id?: string | null;
  posture_level?: string;
  escalation_level?: number;
  control_mode?: string;
  open_event_count?: number;
  critical_open_count?: number;
  warning_open_count?: number;
  recommended_action?: string;
  recovery_eligible?: boolean;
  blockers?: string[];
  summary?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  task_run_id?: number | null;
  source?: string;
  evaluated_at?: string;
};

export type RiskEvent = {
  id?: number;
  severity?: string;
  event_type?: string;
  action?: string;
  status?: string;
  title?: string;
  reason?: string;
  detected_at?: string;
  payload?: Record<string, unknown>;
};

export type RuntimeControl = {
  strategy_id?: string;
  account_id?: string | null;
  control_mode?: string;
  status?: string;
  source?: string;
  trigger_event_type?: string | null;
  reason?: string | null;
  action_summary?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  activated_at?: string;
  released_at?: string | null;
  updated_at?: string;
};

export type RuntimeAlert = {
  alert_id?: number;
  strategy_id?: string;
  account_id?: string | null;
  alert_key?: string;
  category?: string;
  severity?: string;
  status?: string;
  title?: string;
  message?: string;
  escalation_level?: number;
  channels?: string[];
  related_event_ids?: number[];
  metadata?: Record<string, unknown>;
  source?: string;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type PromotionReview = {
  id?: number;
  strategy_id?: string;
  account_id?: string | null;
  review_source?: string;
  stage?: string;
  status?: string;
  recommendation?: string;
  score?: number;
  blockers?: string[];
  risk_flags?: string[];
  summary?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  reviewed_at?: string;
};

export type DomainProjection = {
  strategy_id?: string;
  current_status?: string;
  aggregate_version?: number;
  status_event_count?: number;
  domain_event_count?: number;
  open_risk_count?: number;
  runtime_control_mode?: string;
  runtime_control_status?: string;
  latest_promotion_status?: string;
  latest_promotion_recommendation?: string;
  latest_incubation_decision?: string;
  ai_cycle_count?: number;
  runtime_cycle_count?: number;
  last_status_event_at?: string;
  last_domain_event_at?: string;
  phases?: Record<string, boolean>;
  timeline?: Array<{
    timestamp?: string;
    event_type?: string;
    source?: string;
    summary?: string;
  }>;
};

export type ProjectionSnapshot = {
  id?: number;
  strategy_id?: string;
  projection_type?: string;
  aggregate_version?: number;
  current_status?: string;
  runtime_control_mode?: string;
  timeline_count?: number;
  projection?: DomainProjection;
  metadata?: Record<string, unknown>;
  task_run_id?: number | null;
  source?: string;
  rebuilt_at?: string;
};

export type VectorProfile = {
  id?: number;
  profile_id?: number;
  strategy_id?: string;
  profile_type?: string;
  vector_method?: string;
  metric?: string;
  vector_dim?: number;
  signature?: string;
  backend?: string;
  index_name?: string;
  index_version?: string;
  similarity?: number;
  coarse_score?: number;
  bucket_id?: string | null;
  query_bucket_id?: string | null;
  candidate_count?: number;
  retrieval_mode?: string;
  metadata?: Record<string, unknown>;
};

export type VectorIndexSnapshot = {
  id?: number;
  index_name?: string;
  index_version?: string;
  status?: string;
  profile_type?: string;
  vector_method?: string;
  metric?: string;
  backend?: string;
  profile_count?: number;
  bucket_count?: number;
  vector_dim?: number;
  centroids?: Array<{
    bucket_id?: string;
    size?: number;
    neighbors?: string[];
    mean_similarity?: number;
  }>;
  metadata?: Record<string, unknown>;
  task_run_id?: number | null;
  source?: string;
  built_at?: string;
  activated_at?: string;
  created_at?: string;
};

export type DomainEvent = {
  id?: number;
  strategy_id?: string | null;
  aggregate_type?: string;
  aggregate_id?: string | null;
  event_type?: string;
  source?: string;
  severity?: string;
  correlation_id?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type AiExperiment = {
  experiment_id?: string;
  strategy_id?: string | null;
  parent_strategy_id?: string | null;
  generated_strategy_id?: string | null;
  task_run_id?: number | null;
  source?: string;
  generator_type?: string;
  optimizer_type?: string;
  status?: string;
  hypothesis?: string;
  evaluation?: {
    committee_review?: {
      final_score?: number;
      decision?: string;
      rank?: number;
      is_champion?: boolean;
    };
  };
  result?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type TaskRun = {
  id?: number;
  strategy_id?: string | null;
  task_name?: string;
  task_scope?: string;
  task_key?: string;
  status?: string;
  trace_id?: string;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string | null;
  started_at?: string;
  completed_at?: string | null;
};

export type ListResponse<T> = {
  items?: T[];
  count?: number;
  latest?: T | null;
};

export type StrategyDetailResponse = {
  strategy?: StrategyCore;
  metrics?: StrategyMetric[];
  reviews?: StrategyReview[];
  nav_series?: number[];
  latest_quality_report?: ReviewReportResponse | null;
  incubation_account?: IncubationAccount | null;
  latest_incubation_metric?: IncubationMetric | null;
  latest_promotion_review?: PromotionReview | null;
  latest_projection_snapshot?: ProjectionSnapshot | null;
  latest_vector_index_snapshot?: VectorIndexSnapshot | null;
  latest_incubation_pipeline_snapshot?: IncubationPipelineSnapshot | null;
  latest_runtime_risk_snapshot?: RuntimeRiskSnapshot | null;
  runtime_control?: RuntimeControl | null;
  runtime_alerts?: RuntimeAlert[];
  open_risk_events?: RiskEvent[];
  vector_profiles?: VectorProfile[];
  similar_vector_profiles?: VectorProfile[];
  domain_events?: DomainEvent[];
  task_runs?: TaskRun[];
};

export type EventFilters = {
  event_type: string;
  from_status: string;
  to_status: string;
  actor_id: string;
  start_time: string;
  end_time: string;
  limit: string;
};
