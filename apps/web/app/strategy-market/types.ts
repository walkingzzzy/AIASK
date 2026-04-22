import type { FactoryRunsResponse } from '@aiask/shared-types';
import type {
  AiExperiment,
  DomainEvent,
  DomainProjection,
  ExecutionAuditAcceptanceResponse,
  IncubationAccount,
  IncubationMetric,
  IncubationOverviewResponse,
  IncubationPipelineSnapshot,
  PaperAccountResponse,
  PaperNav,
  PaperOrder,
  ProjectionSnapshot,
  PromotionReview,
  ReviewReportResponse,
  RiskEvent,
  RuntimeAlert,
  RuntimeControl,
  RuntimeRiskSnapshot,
  ResearchWindowStatus,
  StrategyFavoriteState,
  StrategyOwnerState,
  StrategyPaperSessionState,
  StrategyPresentationDto,
  StrategyEventsResponse,
  TopNSnapshot,
  TaskRun,
  VectorIndexSnapshot,
  VectorProfile,
} from '@aiask/shared-types';

export type {
  Strategy,
  StrategyIncubationSurface,
  RankingResponse,
  FactoryAutonomyTaskBrief,
  FactoryRunSummary,
  FactoryStatusResponse,
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunsResponse,
  FactoryRunDetailResponse,
  FactoryGovernancePlaneArtifact,
  FactoryGovernanceGateArtifact,
  FactoryGateStageResult,
  FactoryGovernanceBacktestThresholdsByType,
  FactoryGovernanceCommitteeReview,
  FactoryGovernanceConstraintCheck,
  FactoryPredictionTraceLedgerEntry,
  FactoryPredictionTraceLedgerNode,
  FactoryPredictionTraceLedgerSummary,
  FactoryProtocolVersionsSummary,
  FactoryPredictionTraceSummary,
  FactoryGovernanceDedupArtifact,
  FactoryGateFamilyOutcomeSummary,
  FactoryGovernanceSubmissionArtifact,
  FactoryGovernanceEvidenceArtifact,
  FactoryGovernanceDedupBrief,
  FactoryGovernanceIncubationBudgetSummary,
  FactoryGovernanceStrategyBrief,
  FactoryGovernanceValidationProfile,
  FactoryGovernanceEvidenceStrategyBrief,
  FactoryFeedbackGeneratorModeControl,
  FactoryFeedbackSummary,
  FactoryGenerationLaneQualityItem,
  FactoryQualityBaseline,
  FactoryQualitySummarySnapshot,
  FactoryTopNResponse,
  FullMarketScoreRow,
  FactorySignalQualityRegistry,
  FactorySignalQualityRegistryDriftCheck,
  FactoryValidationFamilyQualityPanelItem,
  ResearchWindowStatus,
  StrategyEvidenceAlignmentAudit,
  StrategyPredictionTraceGateDecisions,
  StrategyReviewReportSummary,
  StrategyMetric,
  StrategyReview,
  StrategyCore,
  TopNSnapshot,
  SignalStatsResponse,
  Signal,
  SignalsResponse,
  ReviewReportResponse,
  StrategyOwnerState,
  StrategyFavoriteState,
  StrategyPaperSessionState,
  StrategyPresentationDto,
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
  ExecutionAuditAcceptanceResponse,
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

export type RunStatusFilter = 'all' | 'success' | 'partial' | 'skipped' | 'failed';

export type FactoryReviewSection =
  | 'summary'
  | 'incubation'
  | 'runtime'
  | 'vectors'
  | 'experiments';

export type TrendMetricKey =
  | 'candidates_spawned'
  | 'submitted'
  | 'passed_quality_gate'
  | 'elapsed_seconds'
  | 'autonomy_task_count'
  | 'event_task_count'
  | 'snapshot_task_count'
  | 'deflated_sharpe_ratio_avg'
  | 'high_pbo_count'
  | 'formal_multiple_testing_count';

export type CapabilityBadge = {
  key: string;
  label: string;
  enabled: boolean;
};

export type StrategyClosureReviewResponse = {
  strategy_id?: string;
  as_of?: string;
  correlation_id?: string;
  factory_run_id?: string;
  stale?: boolean;
  owner_state?: StrategyOwnerState;
  favorite_state?: StrategyFavoriteState;
  paper_session_state?: StrategyPaperSessionState;
  presentation?: StrategyPresentationDto;
  data_freshness?: Record<string, unknown>;
  report?: ReviewReportResponse | null;
  events?: StrategyEventsResponse | null;
  incubation?: {
    overview?: IncubationOverviewResponse | null;
    current_account?: IncubationAccount | null;
    latest_metric?: IncubationMetric | null;
    paper_account?: PaperAccountResponse | null;
    paper_orders?: PaperOrder[];
    paper_nav_rows?: PaperNav[];
    pipeline?: { latest?: IncubationPipelineSnapshot | null; items?: IncubationPipelineSnapshot[]; count?: number };
    promotion_reviews?: { latest?: PromotionReview | null; items?: PromotionReview[]; count?: number };
    execution_audit_acceptance?: ExecutionAuditAcceptanceResponse | null;
  } | null;
  runtime?: {
    control?: RuntimeControl | null;
    risk_events?: RiskEvent[];
    risk_snapshots?: { latest?: RuntimeRiskSnapshot | null; items?: RuntimeRiskSnapshot[]; count?: number };
    alerts?: RuntimeAlert[];
  } | null;
  vectors?: {
    profiles?: VectorProfile[];
    similar_profiles?: VectorProfile[];
    index_snapshots?: { latest?: VectorIndexSnapshot | null; items?: VectorIndexSnapshot[]; count?: number };
  } | null;
  domain?: {
    projection?: DomainProjection | null;
    latest_projection_snapshot?: ProjectionSnapshot | null;
    projection_snapshots?: ProjectionSnapshot[];
    events?: DomainEvent[];
  } | null;
  ai?: {
    experiments?: AiExperiment[];
    task_runs?: TaskRun[];
  } | null;
  factory?: {
    research_window?: ResearchWindowStatus | null;
    full_market_topn?: TopNSnapshot | null;
    latest_run?: FactoryRunItem | null;
    runs?: FactoryRunItem[];
  } | null;
};
