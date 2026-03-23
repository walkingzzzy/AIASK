'use client';

import { useEffect, useMemo, useState } from 'react';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import type {
  StrategyCore,
  StrategyDetailResponse,
  SignalStatsResponse,
  SignalsResponse,
  ReviewReportResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationMetric,
  IncubationPipelineSnapshot,
  PaperAccountResponse,
  PaperOrder,
  PaperNav,
  RuntimeRiskSnapshot,
  RuntimeControl,
  RuntimeAlert,
  RiskEvent,
  VectorProfile,
  VectorIndexSnapshot,
  DomainEvent,
  DomainProjection,
  ProjectionSnapshot,
  AiExperiment,
  TaskRun,
  PromotionReview,
  ListResponse,
  EventFilters,
  FactoryReviewSection,
} from '../types';

export type StrategyDetailTab = 'overview' | 'tracking' | 'factory';
type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';
const FACTORY_SECTION_STALE_TIME = 60_000;

export function useStrategyDetailPage(id: string | null, userId: string | null) {
  const detailQ = useApiQuery<StrategyDetailResponse | StrategyCore>(id ? `/strategy-market/${id}` : null);
  const subscribeApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const reviewApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '评价已提交' });
  const rebuildProjectionApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '事件投影已重建' });
  const runIncubationPipelineApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '孵化流水线已执行' });
  const runIncubationSyncApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '模拟盘孵化同步已执行' });
  const runRiskScanApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '风控扫描已执行' });
  const riskRecoveryApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '已发起恢复尝试' });
  const runRuntimeAlertDispatchApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '运行告警已重新分发' });
  const ackRuntimeAlertApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '告警已确认' });

  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [activeTab, setActiveTab] = useState<StrategyDetailTab>('overview');
  const [activeFactorySection, setActiveFactorySection] = useState<FactoryReviewSection>('summary');
  const [eventFilters, setEventFilters] = useState<EventFilters>({
    event_type: 'status_change',
    from_status: '',
    to_status: '',
    actor_id: '',
    start_time: '',
    end_time: '',
    limit: '20',
  });
  const factoryMode = Boolean(id && activeTab === 'factory');
  const strategyIdParam = id ?? '';

  useEffect(() => {
    setActiveFactorySection('summary');
  }, [id]);

  const factorySummaryMode = Boolean(factoryMode && activeFactorySection === 'summary');
  const factoryIncubationMode = Boolean(factoryMode && activeFactorySection === 'incubation');
  const factoryRuntimeMode = Boolean(factoryMode && activeFactorySection === 'runtime');
  const factoryVectorMode = Boolean(factoryMode && activeFactorySection === 'vectors');
  const factoryExperimentMode = Boolean(factoryMode && activeFactorySection === 'experiments');

  const eventsPath = useMemo(() => {
    if (!id) return null;
    const qs = new URLSearchParams();
    Object.entries(eventFilters).forEach(([key, value]) => {
      if (value) qs.set(key, value);
    });
    if (!qs.has('limit')) qs.set('limit', '20');
    return `/strategy-market/${id}/events?${qs.toString()}`;
  }, [eventFilters, factoryMode, id]);

  const signalStatsQ = useApiQuery<SignalStatsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signal-stats` : null,
  );
  const signalsQ = useApiQuery<SignalsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signals?limit=50` : null,
  );
  const reviewReportQ = useApiQuery<ReviewReportResponse>(
    id ? `/strategy-market/${id}/review-report` : null,
    { enabled: factorySummaryMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const eventsQ = useApiQuery<StrategyEventsResponse>(eventsPath, {
    enabled: factorySummaryMode,
    staleTime: FACTORY_SECTION_STALE_TIME,
    placeholderData: 'keepPrevious',
  });
  const incubationQ = useApiQuery<IncubationOverviewResponse>(
    id ? `/strategy-market/${id}/incubation-overview` : null,
    {
      enabled: factorySummaryMode || factoryIncubationMode,
      staleTime: FACTORY_SECTION_STALE_TIME,
    },
  );
  const incubationMetricsQ = useApiQuery<ListResponse<IncubationMetric>>(
    id ? `/strategy-market/${id}/incubation-metrics?limit=12` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperAccountQ = useApiQuery<PaperAccountResponse>(
    id ? `/strategy-market/${id}/paper-account?limit=20` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperOrdersQ = useApiQuery<ListResponse<PaperOrder>>(
    id ? `/strategy-market/${id}/paper-orders?limit=20` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperNavQ = useApiQuery<ListResponse<PaperNav>>(
    id ? `/strategy-market/${id}/paper-nav?limit=20` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const incubationPipelineQ = useApiQuery<ListResponse<IncubationPipelineSnapshot>>(
    id ? `/strategy-market/${id}/incubation-pipeline?limit=10` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const riskEventsQ = useApiQuery<ListResponse<RiskEvent>>(
    id ? `/strategy-market/${id}/risk-events?limit=20` : null,
    { enabled: factoryRuntimeMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const riskSnapshotsQ = useApiQuery<ListResponse<RuntimeRiskSnapshot>>(
    id ? `/strategy-market/${id}/risk-snapshots?limit=10` : null,
    { enabled: factoryRuntimeMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const vectorProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id ? `/strategy-market/${id}/vector-profiles?limit=10` : null,
    { enabled: factoryVectorMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const similarProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id ? `/strategy-market/${id}/vector-ann-search?limit=10` : null,
    { enabled: factoryVectorMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const vectorIndexSnapshotsQ = useApiQuery<ListResponse<VectorIndexSnapshot>>(
    '/strategy-market/vector-indexes/snapshots?index_name=strategy_behavior&limit=10',
    { enabled: factoryVectorMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const aiExperimentsQ = useApiQuery<ListResponse<AiExperiment>>(
    id ? `/strategy-market/ai/experiments?strategy_id=${encodeURIComponent(strategyIdParam)}&limit=10` : null,
    { enabled: factoryExperimentMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const domainEventsQ = useApiQuery<ListResponse<DomainEvent>>(
    id ? `/strategy-market/${id}/domain-events?limit=20` : null,
    { enabled: factoryExperimentMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const taskRunsQ = useApiQuery<ListResponse<TaskRun>>(
    id ? `/strategy-market/task-runs?strategy_id=${encodeURIComponent(strategyIdParam)}&limit=10` : null,
    { enabled: factoryExperimentMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const runtimeControlQ = useApiQuery<RuntimeControl>(
    id ? `/strategy-market/${id}/runtime-control` : null,
    {
      enabled: factorySummaryMode || factoryRuntimeMode,
      staleTime: FACTORY_SECTION_STALE_TIME,
    },
  );
  const runtimeAlertsQ = useApiQuery<ListResponse<RuntimeAlert>>(
    id ? `/strategy-market/${id}/runtime-alerts?limit=20` : null,
    { enabled: factoryRuntimeMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const promotionReviewsQ = useApiQuery<ListResponse<PromotionReview>>(
    id ? `/strategy-market/${id}/promotion-reviews?limit=10` : null,
    { enabled: factoryIncubationMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const domainProjectionQ = useApiQuery<DomainProjection>(
    id ? `/strategy-market/${id}/domain-projection?limit=100` : null,
    { enabled: factorySummaryMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const projectionSnapshotQ = useApiQuery<ListResponse<ProjectionSnapshot>>(
    id ? `/strategy-market/${id}/domain-projection/snapshot?limit=20` : null,
    { enabled: factorySummaryMode, staleTime: FACTORY_SECTION_STALE_TIME },
  );

  const detail = useMemo(() => {
    const raw = detailQ.data;
    if (raw && typeof raw === 'object' && 'strategy' in raw) {
      return raw as StrategyDetailResponse;
    }
    if (raw && typeof raw === 'object' && 'id' in raw) {
      return {
        strategy: raw as StrategyCore,
        metrics: (raw as StrategyCore).metrics,
        reviews: (raw as StrategyCore).reviews,
      } as StrategyDetailResponse;
    }
    return null;
  }, [detailQ.data]);

  const strategy = detail?.strategy ?? null;
  const metrics = useMemo(
    () => detail?.metrics ?? strategy?.metrics ?? [],
    [detail?.metrics, strategy?.metrics],
  );
  const reviews = detail?.reviews ?? strategy?.reviews ?? [];
  const detailViewModel = detail?.view_model ?? null;
  const navSeries = useMemo(
    () => detail?.nav_series ?? [],
    [detail?.nav_series],
  );
  const latestQualityReport = detailViewModel?.quality?.latest_report ?? detail?.latest_quality_report ?? null;
  const incubationAccount = detailViewModel?.incubation?.account ?? detail?.incubation_account ?? null;
  const latestIncubationMetric = detailViewModel?.incubation?.latest_metric ?? detail?.latest_incubation_metric ?? null;
  const latestPromotionReview = promotionReviewsQ.data?.latest ?? detail?.latest_promotion_review ?? null;
  const latestProjectionSnapshot = projectionSnapshotQ.data?.latest ?? detailViewModel?.domain?.latest_projection_snapshot ?? detail?.latest_projection_snapshot ?? null;
  const latestVectorIndexSnapshot = vectorIndexSnapshotsQ.data?.latest ?? detailViewModel?.vectors?.latest_index_snapshot ?? detail?.latest_vector_index_snapshot ?? null;
  const latestIncubationPipelineSnapshot = incubationPipelineQ.data?.latest ?? detailViewModel?.incubation?.latest_pipeline_snapshot ?? detail?.latest_incubation_pipeline_snapshot ?? null;
  const paperAccount = paperAccountQ.data?.account ?? null;
  const paperPositions = paperAccountQ.data?.positions ?? [];
  const paperOrderSummary = paperAccountQ.data?.order_summary ?? null;
  const latestPaperNav = paperNavQ.data?.latest ?? paperAccountQ.data?.latest_nav ?? null;
  const paperOrders = paperOrdersQ.data?.items ?? [];
  const paperNavRows = paperNavQ.data?.items ?? [];
  const latestRuntimeRiskSnapshot = riskSnapshotsQ.data?.latest ?? detailViewModel?.runtime?.latest_risk_snapshot ?? detail?.latest_runtime_risk_snapshot ?? null;
  const runtimeControl = runtimeControlQ.data ?? detailViewModel?.runtime?.control ?? detail?.runtime_control ?? null;
  const runtimeAlerts = (runtimeAlertsQ.data?.items?.length ? runtimeAlertsQ.data.items : detailViewModel?.runtime?.alerts ?? detail?.runtime_alerts) ?? [];
  const domainProjection = domainProjectionQ.data ?? latestProjectionSnapshot?.projection ?? null;
  const openRiskEvents = (riskEventsQ.data?.items?.length ? riskEventsQ.data.items : detailViewModel?.runtime?.risk_events ?? detail?.open_risk_events) ?? [];
  const vectorProfiles = (vectorProfilesQ.data?.items?.length ? vectorProfilesQ.data.items : detailViewModel?.vectors?.profiles ?? detail?.vector_profiles) ?? [];
  const similarProfiles = (similarProfilesQ.data?.items?.length ? similarProfilesQ.data.items : detailViewModel?.vectors?.similar_profiles ?? detail?.similar_vector_profiles) ?? [];
  const vectorIndexSnapshots = vectorIndexSnapshotsQ.data?.items ?? [];
  const incubationPipelineSnapshots = incubationPipelineQ.data?.items ?? [];
  const runtimeRiskSnapshots = riskSnapshotsQ.data?.items ?? [];
  const domainEvents = (domainEventsQ.data?.items?.length ? domainEventsQ.data.items : detailViewModel?.domain?.events ?? detail?.domain_events) ?? [];
  const taskRuns = (taskRunsQ.data?.items?.length ? taskRunsQ.data.items : detailViewModel?.domain?.task_runs ?? detail?.task_runs) ?? [];

  const allMetrics = useMemo(() => {
    if (!metrics.length) return null;
    return metrics.find((item) => item.period === 'all') ?? metrics[0];
  }, [metrics]);

  const factorBars = useMemo(() => {
    if (!strategy?.factor_weights) return [];
    return Object.entries(strategy.factor_weights).map(([key, value]) => ({
      name: key,
      value: Number(value) || 0,
    }));
  }, [strategy]);

  const navCategories = useMemo(
    () => navSeries.map((_, index) => `${index + 1}`),
    [navSeries],
  );

  const statusVariant: BadgeVariant = ['published', 'listed'].includes(strategy?.status ?? '')
    ? 'success'
    : strategy?.status === 'incubating'
      ? 'warning'
      : ['archived', 'deprecated', 'rejected', 'suspended'].includes(strategy?.status ?? '')
        ? 'danger'
        : 'neutral';

  async function handleSubscribe() {
    if (!userId) {
      window.alert('请先登录后再订阅策略');
      return;
    }
    await subscribeApi.triggerAsync(`/strategy-market/${id}/subscribe`, { method: 'POST' }, {});
  }

  async function handleReview() {
    if (!userId) {
      window.alert('请先登录后再提交评价');
      return;
    }
    await reviewApi.triggerAsync(`/strategy-market/${id}/review`, { method: 'POST' }, { rating, comment });
    setComment('');
    setRating(5);
  }

  async function handleRunIncubationPipeline() {
    if (!id) return;
    await runIncubationPipelineApi.triggerAsync(
      `/strategy-market/${id}/incubation-pipeline/run`,
      { method: 'POST' },
      { auto_apply_review: true, source: 'web_detail' },
    );
  }

  async function handleRunIncubationSync() {
    if (!id) return;
    await runIncubationSyncApi.triggerAsync(`/strategy-market/${id}/incubation-sync/run`, { method: 'POST' }, {});
  }

  async function handleRunRiskScan() {
    if (!id) return;
    await runRiskScanApi.triggerAsync(
      `/strategy-market/${id}/risk-scan/run`,
      { method: 'POST' },
      { enforce_actions: true },
    );
  }

  async function handleRiskRecovery() {
    if (!id) return;
    await riskRecoveryApi.triggerAsync(`/strategy-market/${id}/risk-recovery`, { method: 'POST' }, { source: 'web_detail' });
  }

  async function handleRunRuntimeAlertDispatch() {
    if (!id) return;
    await runRuntimeAlertDispatchApi.triggerAsync(
      `/strategy-market/${id}/runtime-alerts/dispatch`,
      { method: 'POST' },
      { source: 'web_detail' },
    );
  }

  async function handleAckRuntimeAlert(alertId: number) {
    if (!alertId) return;
    await ackRuntimeAlertApi.triggerAsync(
      `/strategy-market/runtime-alerts/${alertId}/ack`,
      { method: 'POST' },
      { acknowledged_by: userId ?? 'web_detail', source: 'web_detail' },
    );
  }

  const factorySectionLoading: Record<FactoryReviewSection, boolean> = {
    summary:
      reviewReportQ.isPending ||
      eventsQ.isPending ||
      incubationQ.isPending ||
      runtimeControlQ.isPending ||
      domainProjectionQ.isPending ||
      projectionSnapshotQ.isPending,
    incubation:
      incubationQ.isPending ||
      incubationMetricsQ.isPending ||
      paperAccountQ.isPending ||
      paperOrdersQ.isPending ||
      paperNavQ.isPending ||
      incubationPipelineQ.isPending ||
      promotionReviewsQ.isPending,
    runtime:
      runtimeControlQ.isPending ||
      riskEventsQ.isPending ||
      riskSnapshotsQ.isPending ||
      runtimeAlertsQ.isPending,
    vectors:
      vectorProfilesQ.isPending ||
      similarProfilesQ.isPending ||
      vectorIndexSnapshotsQ.isPending,
    experiments:
      aiExperimentsQ.isPending ||
      domainEventsQ.isPending ||
      taskRunsQ.isPending,
  };
  const factoryLoading = factorySectionLoading[activeFactorySection];

  return {
    detailLoading: detailQ.isPending,
    detailError: detailQ.error,
    strategy,
    statusVariant,
    activeTab,
    setActiveTab,
    overview: {
      metrics,
      allMetrics,
      reviews,
      navSeries,
      navCategories,
      factorBars,
      latestQualityReport,
      incubationAccount,
      latestIncubationMetric,
      paperAccount,
      latestPaperNav,
      paperNavRows,
      openRiskEvents,
      vectorProfiles,
      promotionReady: Boolean(incubationQ.data?.promotion_ready),
      rating,
      setRating,
      comment,
      setComment,
      subscribePending: subscribeApi.isPending,
      reviewPending: reviewApi.isPending,
      handleSubscribe,
      handleReview,
    },
    trackingPanelProps: {
      stats: signalStatsQ.data,
      signals: signalsQ.data,
      statsLoading: signalStatsQ.isPending,
      signalsLoading: signalsQ.isPending,
    },
    factoryPanelProps: {
      report: reviewReportQ.data ?? latestQualityReport,
      events: eventsQ.data,
      incubation: incubationQ.data,
      currentAccount: incubationAccount,
      latestMetric: latestIncubationMetric,
      latestPromotionReview,
      latestProjectionSnapshot,
      runtimeControl,
      domainProjection,
      latestIncubationPipelineSnapshot,
      incubationPipelineSnapshots,
      paperAccount,
      paperPositions,
      paperOrderSummary,
      latestPaperNav,
      paperOrders,
      paperNavRows,
      latestRuntimeRiskSnapshot,
      runtimeAlerts,
      runtimeRiskSnapshots,
      promotionReviews: promotionReviewsQ.data?.items ?? [],
      incubationMetrics: incubationMetricsQ.data?.items ?? [],
      riskEvents: openRiskEvents,
      vectorProfiles,
      similarProfiles,
      vectorIndexSnapshots,
      latestVectorIndexSnapshot,
      domainEvents,
      aiExperiments: aiExperimentsQ.data?.items ?? [],
      taskRuns,
      activeSection: activeFactorySection,
      onSectionChange: setActiveFactorySection,
      sectionLoading: factorySectionLoading,
      eventFilters,
      onEventFilterChange: (key: keyof EventFilters, value: string) => {
        setEventFilters((prev) => ({ ...prev, [key]: value }));
      },
      onRebuildProjection: () => rebuildProjectionApi.trigger(
        `/strategy-market/${id}/domain-projection/rebuild`,
        { method: 'POST' },
        { source: 'web_detail' },
      ),
      rebuildProjectionPending: rebuildProjectionApi.isPending,
      onRunIncubationPipeline: handleRunIncubationPipeline,
      runIncubationPipelinePending: runIncubationPipelineApi.isPending,
      onRunIncubationSync: handleRunIncubationSync,
      runIncubationSyncPending: runIncubationSyncApi.isPending,
      onRunRiskScan: handleRunRiskScan,
      runRiskScanPending: runRiskScanApi.isPending,
      onRunRuntimeAlertDispatch: handleRunRuntimeAlertDispatch,
      runRuntimeAlertDispatchPending: runRuntimeAlertDispatchApi.isPending,
      onAckRuntimeAlert: handleAckRuntimeAlert,
      ackRuntimeAlertPending: ackRuntimeAlertApi.isPending,
      onRiskRecovery: handleRiskRecovery,
      riskRecoveryPending: riskRecoveryApi.isPending,
      loading: factoryLoading,
    },
  };
}
