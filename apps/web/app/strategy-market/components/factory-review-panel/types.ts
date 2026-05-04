'use client';

import type { buildFactoryReviewViewModel } from '@/app/strategy-market/lib/factory-review-view-model';
import type {
  ReviewReportResponse,
  StrategyIncubationSurface,
  StrategyPresentationDto,
  StrategyPaperContextResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationAccount,
  IncubationMetric,
  ExecutionAuditAcceptanceResponse,
  PromotionReview,
  ProjectionSnapshot,
  RuntimeControl,
  DomainProjection,
  IncubationPipelineSnapshot,
  PaperAccount,
  PaperPosition,
  PaperAccountResponse,
  PaperNav,
  PaperOrder,
  RuntimeRiskSnapshot,
  RuntimeAlert,
  RiskEvent,
  StrategyOwnerState,
  StrategyPaperSessionState,
  VectorProfile,
  VectorIndexSnapshot,
  DomainEvent,
  AiExperiment,
  TaskRun,
  EventFilters,
  FactoryReviewSection,
} from '../../types';

export type FactoryReviewViewModel = ReturnType<typeof buildFactoryReviewViewModel>;
export type FactoryReviewSummaryState = FactoryReviewViewModel['summaryState'];
export type FactoryReviewIncubationState = FactoryReviewViewModel['incubationState'];
export type FactoryReviewRuntimeState = FactoryReviewViewModel['runtimeState'];
export type FactoryReviewVectorState = FactoryReviewViewModel['vectorState'];
export type FactoryReviewExperimentState = FactoryReviewViewModel['experimentState'];
export type FactoryReviewAuditRows = FactoryReviewViewModel['reviewAuditRows'];

export type FactoryReviewPanelProps = {
  highConfidenceQualityUiEnabled: boolean;
  canViewOperatorPanels: boolean;
  readDegraded?: boolean;
  readDegradedReason?: string | null;
  strategyStatus?: string | null;
  strategyIncubationSurface?: StrategyIncubationSurface | null;
  paperContext?: StrategyPaperContextResponse | null;
  ownerState?: StrategyOwnerState | null;
  paperSessionState?: StrategyPaperSessionState | null;
  report: ReviewReportResponse | null | undefined;
  presentation?: StrategyPresentationDto | null;
  events: StrategyEventsResponse | null | undefined;
  incubation: IncubationOverviewResponse | null | undefined;
  currentAccount: IncubationAccount | null | undefined;
  latestMetric: IncubationMetric | null | undefined;
  latestPromotionReview: PromotionReview | null | undefined;
  latestProjectionSnapshot: ProjectionSnapshot | null | undefined;
  runtimeControl: RuntimeControl | null | undefined;
  domainProjection: DomainProjection | null | undefined;
  latestIncubationPipelineSnapshot: IncubationPipelineSnapshot | null | undefined;
  executionAuditAcceptance: ExecutionAuditAcceptanceResponse | null | undefined;
  incubationPipelineSnapshots: IncubationPipelineSnapshot[];
  paperAccount: PaperAccount | null;
  paperPositions: PaperPosition[];
  paperOrderSummary: PaperAccountResponse['order_summary'] | null;
  latestPaperNav: PaperNav | null;
  paperOrders: PaperOrder[];
  paperNavRows: PaperNav[];
  latestRuntimeRiskSnapshot: RuntimeRiskSnapshot | null | undefined;
  runtimeAlerts: RuntimeAlert[];
  runtimeRiskSnapshots: RuntimeRiskSnapshot[];
  promotionReviews: PromotionReview[];
  incubationMetrics: IncubationMetric[];
  riskEvents: RiskEvent[];
  vectorProfiles: VectorProfile[];
  similarProfiles: VectorProfile[];
  vectorIndexSnapshots: VectorIndexSnapshot[];
  latestVectorIndexSnapshot: VectorIndexSnapshot | null | undefined;
  domainEvents: DomainEvent[];
  aiExperiments: AiExperiment[];
  taskRuns: TaskRun[];
  activeSection: FactoryReviewSection;
  onSectionChange: (section: FactoryReviewSection) => void;
  sectionLoading: Record<FactoryReviewSection, boolean>;
  eventFilters: EventFilters;
  onEventFilterChange: (key: keyof EventFilters, value: string) => void;
  onRebuildProjection: () => void;
  rebuildProjectionPending: boolean;
  onRunIncubationPipeline: () => void;
  runIncubationPipelinePending: boolean;
  onRunIncubationSync: () => void;
  runIncubationSyncPending: boolean;
  onRunExecutionAuditAcceptance: () => void;
  runExecutionAuditAcceptancePending: boolean;
  onRunRiskScan: () => void;
  runRiskScanPending: boolean;
  onRunRuntimeAlertDispatch: () => void;
  runRuntimeAlertDispatchPending: boolean;
  onAckRuntimeAlert: (alertId: number) => void;
  ackRuntimeAlertPending: boolean;
  onRiskRecovery: () => void;
  riskRecoveryPending: boolean;
  onSetRuntimeControl: (controlMode: string) => void;
  setRuntimeControlPending: boolean;
  onResolveRiskEvent: (eventId: number) => void;
  resolveRiskEventPending: boolean;
  onRunRuntimeCycle: () => void;
  runRuntimeCyclePending: boolean;
  onAiGenerateCandidate: () => void;
  aiGenerateCandidatePending: boolean;
  loading: boolean;
};
