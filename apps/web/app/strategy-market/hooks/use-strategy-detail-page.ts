'use client';

import { useCallback, useMemo, useState } from 'react';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import type {
  CapabilityResponse,
  StrategyDetailResponse,
  SignalStatsResponse,
  SignalsResponse,
  ReviewReportResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationMetric,
  IncubationPipelineSnapshot,
  ExecutionAuditAcceptanceResponse,
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
  StrategyClosureReviewResponse,
  StrategyPaperContextResponse,
} from '../types';
import {
  parseIncubationOverviewResponse,
  parseReviewReportResponse,
  parseStrategyDetailResponse,
  parseStrategyPaperContextResponse,
} from '../lib/contracts';

export type StrategyDetailTab = 'overview' | 'tracking' | 'factory';
type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';
const FACTORY_SECTION_STALE_TIME = 60_000;
type StrategySubscriptionRow = { strategy_id?: string; id?: string };
type StrategySubscriptionsResponse = { subscriptions?: StrategySubscriptionRow[]; items?: StrategySubscriptionRow[]; count?: number };

export function useStrategyDetailPage(id: string | null, userId: string | null) {
  const detailQ = useApiQuery<StrategyDetailResponse>(
    id ? `/strategy-market/${id}` : null,
    { parse: parseStrategyDetailResponse },
  );
  const paperContextQ = useApiQuery<StrategyPaperContextResponse>(
    id && userId ? `/strategy-market/${id}/paper-context` : null,
    {
      enabled: Boolean(id && userId),
      nonFatal: true,
      staleTime: FACTORY_SECTION_STALE_TIME,
      parse: parseStrategyPaperContextResponse,
    },
  );
  const capabilitiesQ = useApiQuery<CapabilityResponse>(
    id ? '/strategy-market/capabilities' : null,
    { enabled: Boolean(id), staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const mySubscriptionsQ = useApiQuery<StrategySubscriptionsResponse>(
    userId ? '/strategy-market/my-favorites' : null,
    { enabled: Boolean(userId), staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const subscribeApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const reviewApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '评价已提交' });
  const rebuildProjectionApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '事件投影已重建' });
  const runIncubationPipelineApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '孵化流水线已执行' });
  const runIncubationSyncApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '模拟盘孵化同步已执行' });
  const runExecutionAuditAcceptanceApi = useApiMutation({
    invalidates: [apiKeys.strategy()],
    successToast: '执行审计校验已重跑',
  });
  const runRiskScanApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '风控扫描已执行' });
  const riskRecoveryApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '已发起恢复尝试' });
  const runRuntimeAlertDispatchApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '运行告警已重新分发' });
  const ackRuntimeAlertApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '告警已确认' });
  const setRuntimeControlApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '运行控制已更新' });
  const resolveRiskEventApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '风险事件已解决' });
  const runRuntimeCycleApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '运行闭环已触发' });
  const aiGenerateCandidateApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: 'AI 候选生成任务已提交' });

  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [activeTab, setActiveTab] = useState<StrategyDetailTab>('overview');
  const strategyScopeKey = id ?? '';
  const subscriptionScopeKey = `${id ?? ''}:${userId ?? ''}`;
  const [activeFactorySectionState, setActiveFactorySectionState] = useState<{
    key: string;
    value: FactoryReviewSection;
  }>({ key: strategyScopeKey, value: 'summary' });
  const [subscriptionOverrideState, setSubscriptionOverrideState] = useState<{
    key: string;
    value: boolean | null;
  }>({ key: subscriptionScopeKey, value: null });
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
  const activeFactorySection = activeFactorySectionState.key === strategyScopeKey
    ? activeFactorySectionState.value
    : 'summary';
  const setActiveFactorySection = useCallback((value: FactoryReviewSection) => {
    setActiveFactorySectionState({ key: strategyScopeKey, value });
  }, [strategyScopeKey]);
  const subscriptionOverride = subscriptionOverrideState.key === subscriptionScopeKey
    ? subscriptionOverrideState.value
    : null;
  const setSubscriptionOverride = useCallback((value: boolean | null) => {
    setSubscriptionOverrideState({ key: subscriptionScopeKey, value });
  }, [subscriptionScopeKey]);

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
  }, [eventFilters, id]);
  const closureReviewQ = useApiQuery<StrategyClosureReviewResponse>(
    id && factoryMode ? `/strategy-market/${id}/closure-review` : null,
    {
      enabled: factoryMode,
      staleTime: FACTORY_SECTION_STALE_TIME,
    },
  );
  const useLegacyFactoryQueries = Boolean(factoryMode && closureReviewQ.error);

  const signalStatsQ = useApiQuery<SignalStatsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signal-stats` : null,
  );
  const signalsQ = useApiQuery<SignalsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signals?limit=50` : null,
  );
  const reviewReportQ = useApiQuery<ReviewReportResponse>(
    id ? `/strategy-market/${id}/review-report` : null,
    {
      enabled: factorySummaryMode && useLegacyFactoryQueries,
      staleTime: FACTORY_SECTION_STALE_TIME,
      parse: parseReviewReportResponse,
    },
  );
  const eventsQ = useApiQuery<StrategyEventsResponse>(eventsPath, {
    enabled: factorySummaryMode && useLegacyFactoryQueries,
    staleTime: FACTORY_SECTION_STALE_TIME,
    placeholderData: 'keepPrevious',
  });
  const incubationQ = useApiQuery<IncubationOverviewResponse>(
    id ? `/strategy-market/${id}/incubation-overview` : null,
    {
      enabled: (factorySummaryMode || factoryIncubationMode) && useLegacyFactoryQueries,
      staleTime: FACTORY_SECTION_STALE_TIME,
      parse: parseIncubationOverviewResponse,
    },
  );
  const incubationMetricsQ = useApiQuery<ListResponse<IncubationMetric>>(
    id ? `/strategy-market/${id}/incubation-metrics?limit=12` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperAccountQ = useApiQuery<PaperAccountResponse>(
    id ? `/strategy-market/${id}/paper-account?limit=20` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperOrdersQ = useApiQuery<ListResponse<PaperOrder>>(
    id ? `/strategy-market/${id}/paper-orders?limit=20` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const paperNavQ = useApiQuery<ListResponse<PaperNav>>(
    id ? `/strategy-market/${id}/paper-nav?limit=20` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const incubationPipelineQ = useApiQuery<ListResponse<IncubationPipelineSnapshot>>(
    id ? `/strategy-market/${id}/incubation-pipeline?limit=10` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const executionAuditAcceptanceQ = useApiQuery<ExecutionAuditAcceptanceResponse>(
    id ? `/strategy-market/${id}/execution-audit` : null,
    {
      enabled: (factorySummaryMode || factoryIncubationMode) && useLegacyFactoryQueries,
      staleTime: FACTORY_SECTION_STALE_TIME,
    },
  );
  const riskEventsQ = useApiQuery<ListResponse<RiskEvent>>(
    id ? `/strategy-market/${id}/risk-events?limit=20` : null,
    { enabled: factoryRuntimeMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const riskSnapshotsQ = useApiQuery<ListResponse<RuntimeRiskSnapshot>>(
    id ? `/strategy-market/${id}/risk-snapshots?limit=10` : null,
    { enabled: factoryRuntimeMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const vectorProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id ? `/strategy-market/${id}/vector-profiles?limit=10` : null,
    { enabled: factoryVectorMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const similarProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id ? `/strategy-market/${id}/vector-ann-search?limit=10` : null,
    { enabled: factoryVectorMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const vectorIndexSnapshotsQ = useApiQuery<ListResponse<VectorIndexSnapshot>>(
    '/strategy-market/vector-indexes/snapshots?index_name=strategy_behavior&limit=10',
    { enabled: factoryVectorMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const aiExperimentsQ = useApiQuery<ListResponse<AiExperiment>>(
    id ? `/strategy-market/ai/experiments?strategy_id=${encodeURIComponent(strategyIdParam)}&limit=10` : null,
    { enabled: factoryExperimentMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const domainEventsQ = useApiQuery<ListResponse<DomainEvent>>(
    id ? `/strategy-market/${id}/domain-events?limit=20` : null,
    { enabled: factoryExperimentMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const taskRunsQ = useApiQuery<ListResponse<TaskRun>>(
    id ? `/strategy-market/task-runs?strategy_id=${encodeURIComponent(strategyIdParam)}&limit=10` : null,
    { enabled: factoryExperimentMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const runtimeControlQ = useApiQuery<RuntimeControl>(
    id ? `/strategy-market/${id}/runtime-control` : null,
    {
      enabled: (factorySummaryMode || factoryRuntimeMode) && useLegacyFactoryQueries,
      staleTime: FACTORY_SECTION_STALE_TIME,
    },
  );
  const runtimeAlertsQ = useApiQuery<ListResponse<RuntimeAlert>>(
    id ? `/strategy-market/${id}/runtime-alerts?limit=20` : null,
    { enabled: factoryRuntimeMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const promotionReviewsQ = useApiQuery<ListResponse<PromotionReview>>(
    id ? `/strategy-market/${id}/promotion-reviews?limit=10` : null,
    { enabled: factoryIncubationMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const domainProjectionQ = useApiQuery<DomainProjection>(
    id ? `/strategy-market/${id}/domain-projection?limit=100` : null,
    { enabled: factorySummaryMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );
  const projectionSnapshotQ = useApiQuery<ListResponse<ProjectionSnapshot>>(
    id ? `/strategy-market/${id}/domain-projection/snapshot?limit=20` : null,
    { enabled: factorySummaryMode && useLegacyFactoryQueries, staleTime: FACTORY_SECTION_STALE_TIME },
  );

  const detail = detailQ.data;
  const closureReview = closureReviewQ.data;
  const closureIncubation = closureReview?.incubation ?? null;
  const closureRuntime = closureReview?.runtime ?? null;
  const closureVectors = closureReview?.vectors ?? null;
  const closureDomain = closureReview?.domain ?? null;
  const closureAi = closureReview?.ai ?? null;

  const strategy = detail?.strategy ?? null;
  const ownerState = closureReview?.owner_state ?? detail?.owner_state ?? null;
  const favoriteState = closureReview?.favorite_state ?? detail?.favorite_state ?? null;
  const paperSessionState = closureReview?.paper_session_state ?? detail?.paper_session_state ?? null;
  const presentation = closureReview?.presentation ?? detail?.presentation ?? null;
  const runtimeActionContract =
    closureReview?.runtime_action_contract ??
    detail?.runtime_action_contract ??
    strategy?.runtime_action_contract ??
    detail?.view_model?.actions?.runtime_action_contract ??
    null;
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
  const latestQualityReport = closureReview?.report ?? reviewReportQ.data ?? detailViewModel?.quality?.latest_report ?? detail?.latest_quality_report ?? null;
  const incubationOverview = closureIncubation?.overview ?? incubationQ.data ?? detail?.incubation_overview ?? detailViewModel?.incubation?.overview ?? null;
  const incubationAccount = closureIncubation?.current_account ?? detailViewModel?.incubation?.account ?? detail?.incubation_account ?? null;
  const latestIncubationMetric = closureIncubation?.latest_metric ?? detailViewModel?.incubation?.latest_metric ?? detail?.latest_incubation_metric ?? null;
  const latestPromotionReview = closureIncubation?.promotion_reviews?.latest ?? promotionReviewsQ.data?.latest ?? detail?.latest_promotion_review ?? null;
  const latestProjectionSnapshot = closureDomain?.latest_projection_snapshot ?? projectionSnapshotQ.data?.latest ?? detailViewModel?.domain?.latest_projection_snapshot ?? detail?.latest_projection_snapshot ?? null;
  const latestVectorIndexSnapshot = closureVectors?.index_snapshots?.latest ?? vectorIndexSnapshotsQ.data?.latest ?? detailViewModel?.vectors?.latest_index_snapshot ?? detail?.latest_vector_index_snapshot ?? null;
  const latestIncubationPipelineSnapshot = closureIncubation?.pipeline?.latest ?? incubationPipelineQ.data?.latest ?? detailViewModel?.incubation?.latest_pipeline_snapshot ?? detail?.latest_incubation_pipeline_snapshot ?? null;
  const paperAccount = closureIncubation?.paper_account?.account ?? paperAccountQ.data?.account ?? null;
  const paperPositions = closureIncubation?.paper_account?.positions ?? paperAccountQ.data?.positions ?? [];
  const paperOrderSummary = closureIncubation?.paper_account?.order_summary ?? paperAccountQ.data?.order_summary ?? null;
  const latestPaperNav = closureIncubation?.paper_account?.latest_nav ?? paperNavQ.data?.latest ?? paperAccountQ.data?.latest_nav ?? null;
  const paperOrders = closureIncubation?.paper_orders ?? paperOrdersQ.data?.items ?? [];
  const paperNavRows = closureIncubation?.paper_nav_rows ?? paperNavQ.data?.items ?? [];
  const latestRuntimeRiskSnapshot = closureRuntime?.risk_snapshots?.latest ?? riskSnapshotsQ.data?.latest ?? detailViewModel?.runtime?.latest_risk_snapshot ?? detail?.latest_runtime_risk_snapshot ?? null;
  const runtimeControl = closureRuntime?.control ?? runtimeControlQ.data ?? detailViewModel?.runtime?.control ?? detail?.runtime_control ?? null;
  const runtimeAlerts = closureRuntime?.alerts ?? (runtimeAlertsQ.data?.items?.length ? runtimeAlertsQ.data.items : detailViewModel?.runtime?.alerts ?? detail?.runtime_alerts) ?? [];
  const domainProjection = closureDomain?.projection ?? domainProjectionQ.data ?? latestProjectionSnapshot?.projection ?? null;
  const openRiskEvents = closureRuntime?.risk_events ?? (riskEventsQ.data?.items?.length ? riskEventsQ.data.items : detailViewModel?.runtime?.risk_events ?? detail?.open_risk_events) ?? [];
  const vectorProfiles = closureVectors?.profiles ?? (vectorProfilesQ.data?.items?.length ? vectorProfilesQ.data.items : detailViewModel?.vectors?.profiles ?? detail?.vector_profiles) ?? [];
  const similarProfiles = closureVectors?.similar_profiles ?? (similarProfilesQ.data?.items?.length ? similarProfilesQ.data.items : detailViewModel?.vectors?.similar_profiles ?? detail?.similar_vector_profiles) ?? [];
  const vectorIndexSnapshots = closureVectors?.index_snapshots?.items ?? vectorIndexSnapshotsQ.data?.items ?? [];
  const incubationPipelineSnapshots = closureIncubation?.pipeline?.items ?? incubationPipelineQ.data?.items ?? [];
  const runtimeRiskSnapshots = closureRuntime?.risk_snapshots?.items ?? riskSnapshotsQ.data?.items ?? [];
  const domainEvents = closureDomain?.events ?? (domainEventsQ.data?.items?.length ? domainEventsQ.data.items : detailViewModel?.domain?.events ?? detail?.domain_events) ?? [];
  const taskRuns = closureAi?.task_runs ?? (taskRunsQ.data?.items?.length ? taskRunsQ.data.items : detailViewModel?.domain?.task_runs ?? detail?.task_runs) ?? [];
  const subscribedStrategyIds = useMemo(() => {
    const rows = mySubscriptionsQ.data?.subscriptions ?? mySubscriptionsQ.data?.items ?? [];
    return new Set(
      rows
        .map((item) => String(item.strategy_id ?? item.id ?? '').trim())
        .filter(Boolean),
    );
  }, [mySubscriptionsQ.data]);
  const isSubscribed = Boolean(
    id
      && (
        subscriptionOverride
        ?? favoriteState?.favorited
        ?? subscribedStrategyIds.has(id)
      ),
  );
  const highConfidenceQualityUiEnabled = Boolean(
    capabilitiesQ.data?.quality_ui_v2_enabled,
  );
  const detailRecord = (detail ?? {}) as Record<string, unknown>;
  const closureRecord = (closureReview ?? {}) as Record<string, unknown>;
  const factoryReadDegraded = Boolean(
    detailQ.trust.degraded
    || closureReviewQ.trust.degraded
    || detailRecord.degraded_detail
    || detailRecord.degraded
    || closureRecord.degraded,
  );
  const factoryReadDegradedReason = [
    ...detailQ.trust.reasons,
    ...closureReviewQ.trust.reasons,
    String(detailRecord.degraded_reason ?? detailRecord.fallback_reason ?? closureRecord.degraded_reason ?? closureRecord.fallback_reason ?? '').trim(),
  ].filter(Boolean).join('；') || null;
  const blockFactoryWrite = () => {
    window.alert(factoryReadDegradedReason || '策略详情存在降级读取，写入动作已暂停。');
  };

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
      window.alert('请先登录后再收藏策略');
      return;
    }
    if (!id) return;

    if (isSubscribed) {
      await subscribeApi.triggerAsync(`/strategy-market/${id}/favorite`, { method: 'DELETE' }, {});
      setSubscriptionOverride(false);
      return;
    }

    await subscribeApi.triggerAsync(`/strategy-market/${id}/favorite`, { method: 'POST' }, {});
    setSubscriptionOverride(true);
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
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await runIncubationPipelineApi.triggerAsync(
      `/strategy-market/${id}/incubation-pipeline/run`,
      { method: 'POST' },
      { auto_apply_review: true, source: 'web_detail' },
    );
  }

  async function handleRunIncubationSync() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await runIncubationSyncApi.triggerAsync(`/strategy-market/${id}/incubation-sync/run`, { method: 'POST' }, {});
  }

  async function handleRunExecutionAuditAcceptance() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await runExecutionAuditAcceptanceApi.triggerAsync(
      `/strategy-market/${id}/execution-audit/run`,
      { method: 'POST' },
      { backfill: true },
    );
  }

  async function handleRunRiskScan() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await runRiskScanApi.triggerAsync(
      `/strategy-market/${id}/risk-scan/run`,
      { method: 'POST' },
      { enforce_actions: true },
    );
  }

  async function handleRiskRecovery() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await riskRecoveryApi.triggerAsync(`/strategy-market/${id}/risk-recovery`, { method: 'POST' }, { source: 'web_detail' });
  }

  async function handleRunRuntimeAlertDispatch() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    await runRuntimeAlertDispatchApi.triggerAsync(
      `/strategy-market/${id}/runtime-alerts/dispatch`,
      { method: 'POST' },
      { source: 'web_detail' },
    );
  }

  async function handleAckRuntimeAlert(alertId: number) {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!alertId) return;
    await ackRuntimeAlertApi.triggerAsync(
      `/strategy-market/runtime-alerts/${alertId}/ack`,
      { method: 'POST' },
      { acknowledged_by: userId ?? 'web_detail', source: 'web_detail' },
    );
  }

  async function handleSetRuntimeControl(controlMode: string) {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    const confirmed = window.confirm(`确认将运行控制模式设置为 ${controlMode}？`);
    if (!confirmed) return;
    await setRuntimeControlApi.triggerAsync(
      `/strategy-market/${id}/runtime-control`,
      { method: 'POST' },
      {
        control_mode: controlMode,
        reason: 'web_detail_runtime_governance',
        source: 'web_detail',
        trigger_event_type: 'manual_operator_control',
      },
    );
  }

  async function handleResolveRiskEvent(eventId: number) {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!eventId) return;
    const confirmed = window.confirm(`确认解决风险事件 ${eventId}？`);
    if (!confirmed) return;
    await resolveRiskEventApi.triggerAsync(
      `/strategy-market/risk-events/${eventId}/resolve`,
      { method: 'POST' },
      { resolution: 'resolved_from_web_detail' },
    );
  }

  async function handleRunRuntimeCycle() {
    if (factoryReadDegraded) return blockFactoryWrite();
    const confirmed = window.confirm('确认触发运行态闭环？');
    if (!confirmed) return;
    await runRuntimeCycleApi.triggerAsync('/strategy-market/runtime-cycle/run', { method: 'POST' }, {});
  }

  async function handleAiGenerateCandidate() {
    if (factoryReadDegraded) return blockFactoryWrite();
    if (!id) return;
    const confirmed = window.confirm('确认围绕当前策略提交 AI 候选生成任务？');
    if (!confirmed) return;
    await aiGenerateCandidateApi.triggerAsync(
      '/strategy-market/operator/jobs',
      { method: 'POST' },
      {
        action: 'ai_generate',
        params: { limit: 3, parent_strategy_id: id, auto_submit: false },
        confirmed: true,
        confirmation_text: 'ai_generate',
        reason: 'strategy_detail_experiment_section',
        timeout_ms: 120000,
      },
    );
  }

  const factorySectionLoading: Record<FactoryReviewSection, boolean> = {
    summary: closureReviewQ.isPending || (useLegacyFactoryQueries && (
      reviewReportQ.isPending ||
      eventsQ.isPending ||
      incubationQ.isPending ||
      executionAuditAcceptanceQ.isPending ||
      runtimeControlQ.isPending ||
      domainProjectionQ.isPending ||
      projectionSnapshotQ.isPending
    )),
    incubation: closureReviewQ.isPending || (useLegacyFactoryQueries && (
      incubationQ.isPending ||
      executionAuditAcceptanceQ.isPending ||
      incubationMetricsQ.isPending ||
      paperAccountQ.isPending ||
      paperOrdersQ.isPending ||
      paperNavQ.isPending ||
      incubationPipelineQ.isPending ||
      promotionReviewsQ.isPending
    )),
    runtime: closureReviewQ.isPending || (useLegacyFactoryQueries && (
      runtimeControlQ.isPending ||
      riskEventsQ.isPending ||
      riskSnapshotsQ.isPending ||
      runtimeAlertsQ.isPending
    )),
    vectors: closureReviewQ.isPending || (useLegacyFactoryQueries && (
      vectorProfilesQ.isPending ||
      similarProfilesQ.isPending ||
      vectorIndexSnapshotsQ.isPending
    )),
    experiments: closureReviewQ.isPending || (useLegacyFactoryQueries && (
      aiExperimentsQ.isPending ||
      domainEventsQ.isPending ||
      taskRunsQ.isPending
    )),
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
      incubationOverview,
      latestQualityReport,
      incubationAccount,
      latestIncubationMetric,
      paperAccount,
      latestPaperNav,
      paperNavRows,
      openRiskEvents,
      vectorProfiles,
      highConfidenceQualityUiEnabled,
      promotionReady: Boolean(incubationOverview?.promotion_ready),
      ownerState,
      favoriteState,
      paperSessionState,
      paperContext: paperContextQ.data,
      presentation,
      runtimeActionContract,
      rating,
      setRating,
      comment,
      setComment,
      isSubscribed,
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
      highConfidenceQualityUiEnabled,
      canViewOperatorPanels: Boolean(capabilitiesQ.data?.actor_permissions?.can_view_operator_panels),
      readDegraded: factoryReadDegraded,
      readDegradedReason: factoryReadDegradedReason,
      strategyIncubationSurface: strategy?.incubation_surface ?? null,
      paperContext: paperContextQ.data,
      report: latestQualityReport,
      events: closureReview?.events ?? eventsQ.data,
      incubation: incubationOverview,
      currentAccount: incubationAccount,
      latestMetric: latestIncubationMetric,
      latestPromotionReview,
      latestProjectionSnapshot,
      runtimeControl,
      domainProjection,
      latestIncubationPipelineSnapshot,
      executionAuditAcceptance: closureIncubation?.execution_audit_acceptance ?? executionAuditAcceptanceQ.data,
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
      promotionReviews: closureIncubation?.promotion_reviews?.items ?? promotionReviewsQ.data?.items ?? [],
      incubationMetrics: incubationMetricsQ.data?.items ?? [],
      riskEvents: openRiskEvents,
      vectorProfiles,
      similarProfiles,
      vectorIndexSnapshots,
      latestVectorIndexSnapshot,
      domainEvents,
      aiExperiments: closureAi?.experiments ?? aiExperimentsQ.data?.items ?? [],
      taskRuns,
      ownerState,
      favoriteState,
      paperSessionState,
      presentation,
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
      onRunExecutionAuditAcceptance: handleRunExecutionAuditAcceptance,
      runExecutionAuditAcceptancePending: runExecutionAuditAcceptanceApi.isPending,
      onRunRiskScan: handleRunRiskScan,
      runRiskScanPending: runRiskScanApi.isPending,
      onRunRuntimeAlertDispatch: handleRunRuntimeAlertDispatch,
      runRuntimeAlertDispatchPending: runRuntimeAlertDispatchApi.isPending,
      onAckRuntimeAlert: handleAckRuntimeAlert,
      ackRuntimeAlertPending: ackRuntimeAlertApi.isPending,
      onRiskRecovery: handleRiskRecovery,
      riskRecoveryPending: riskRecoveryApi.isPending,
      onSetRuntimeControl: handleSetRuntimeControl,
      setRuntimeControlPending: setRuntimeControlApi.isPending,
      onResolveRiskEvent: handleResolveRiskEvent,
      resolveRiskEventPending: resolveRiskEventApi.isPending,
      onRunRuntimeCycle: handleRunRuntimeCycle,
      runRuntimeCyclePending: runRuntimeCycleApi.isPending,
      onAiGenerateCandidate: handleAiGenerateCandidate,
      aiGenerateCandidatePending: aiGenerateCandidateApi.isPending,
      loading: factoryLoading,
    },
  };
}
