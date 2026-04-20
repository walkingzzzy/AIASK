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
  FactorySignalQualityRegistry,
  FactorySignalQualityRegistryDriftCheck,
  FactoryValidationFamilyQualityPanelItem,
  StrategyEvidenceAlignmentAudit,
  StrategyPredictionTraceGateDecisions,
  StrategyReviewReportSummary,
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
