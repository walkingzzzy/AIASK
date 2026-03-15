import type { FactoryRunsResponse } from '@aiask/shared-types';

export type {
  Strategy,
  RankingResponse,
  FactoryAutonomyTaskBrief,
  FactoryRunSummary,
  FactoryStatusResponse,
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunsResponse,
  FactoryRunDetailResponse,
  StrategyMetric,
  StrategyReview,
  StrategyCore,
  SignalStatsResponse,
  Signal,
  SignalsResponse,
  ReviewReportResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationAccount,
  IncubationMetric,
  PaperAccount,
  PaperPosition,
  PaperOrder,
  PaperNav,
  PaperAccountResponse,
  IncubationPipelineSnapshot,
  RuntimeRiskSnapshot,
  RiskEvent,
  RuntimeControl,
  RuntimeAlert,
  PromotionReview,
  DomainProjection,
  ProjectionSnapshot,
  VectorProfile,
  VectorIndexSnapshot,
  DomainEvent,
  AiExperiment,
  TaskRun,
  ListResponse,
  StrategyDetailResponse,
  EventFilters,
} from '@aiask/shared-types';

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
