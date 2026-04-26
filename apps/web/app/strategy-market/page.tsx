'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useOnboarding } from '@/components/onboarding';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { ErrorState, LoadingState, PageStatusCard } from '@/components/status-state';
import { Badge, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { extractArray } from '@/lib/data-utils';
import { apiKeys } from '@/lib/query-keys';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import { useAuthStore } from '@/store/auth-store';
import { useCartStore } from '@/store/cart-store';
import type {
  CapabilityResponse,
  FactoryMarketViewResponse,
  StrategyCapabilityDiagnosticsResponse,
  RankingResponse,
  RunStatusFilter,
  Strategy,
  StrategyRuntimeActionContractItem,
  TrendMetricKey,
} from './types';
import { CartDrawer } from './components/CartDrawer';
import { FactoryDashboard } from './components/FactoryDashboard';
import { StrategyCapabilityGapPanel } from './components/StrategyCapabilityGapPanel';
import {
  StrategyFactoryRawArtifactsPanel,
  StrategyFactoryVectorGovernancePanel,
} from './components/StrategyFactoryGovernancePanels';
import { StrategyMarketCatalogSection } from './components/StrategyMarketCatalogSection';
import {
  StrategyMarketEmptyStateSection,
  StrategyMarketFactoryOverviewSection,
  StrategyMarketObservabilitySection,
} from './components/StrategyMarketFactorySections';
import { StrategyMarketHeroSection } from './components/StrategyMarketHeroSection';
import { StrategyMarketOperatorPanel } from './components/StrategyMarketOperatorPanel';
import {
  countRows,
  filterAndSortStrategies,
  getStrategyStatusCounts,
  isRecord,
  matchesStrategyStatusSegment,
  normalizeStrategyStatusSegment,
  resolveCategoryLabel,
  resolveStatusSegmentHelpText,
  resolveStatusSegmentLabel,
  type StrategyMarketStatusSegment,
  type StrategySortKey,
} from './components/strategy-market-support';
import {
  matchesIncubationStageFilter,
  normalizeIncubationStageFilter,
  resolveIncubationStageFilterLabel,
  type StrategyIncubationStageFilter,
} from './lib/incubation-surface';
import { parseFactoryMarketViewResponse, parseStrategyCapabilityDiagnosticsResponse } from './lib/contracts';
import { buildFactoryMarketViewModel } from './lib/factory-market-view-model';

const RANKING_PAGE_LIMIT = 40;
type StrategyWorkspace = 'market' | 'favorites' | 'mine' | 'factory';

type HeroMetricTone = 'default' | 'success' | 'danger';
type HeroMetricItem = {
  key: string;
  label: string;
  value: string;
  tone?: HeroMetricTone;
};

function normalizeHeroMetricCards(
  cards: Array<Record<string, unknown>> | null | undefined,
  prefix: string,
): HeroMetricItem[] {
  return (cards ?? [])
    .map((card, index) => {
      const key = String(card.key ?? `${prefix}-${index + 1}`).trim();
      const label = String(card.label ?? '').trim();
      const value = String(card.value ?? '').trim();
      const toneRaw = String(card.tone ?? '').trim();
      const tone: HeroMetricTone | undefined =
        toneRaw === 'success' || toneRaw === 'danger' || toneRaw === 'default' ? toneRaw : undefined;
      if (!key || !label || !value) return null;
      return { key, label, value, ...(tone ? { tone } : {}) };
    })
    .filter((item): item is HeroMetricItem => Boolean(item));
}

function shouldOpenFactoryFromTask(task: string | null) {
  if (!task) return false;
  return task === 'factory_cycle' || task === 'factory_review' || task === 'factory_runtime';
}

function normalizeWorkspace(raw: string | null): StrategyWorkspace {
  return raw === 'favorites' || raw === 'mine' || raw === 'factory' ? raw : 'market';
}

function summarizeAiGenerateResult(raw: unknown) {
  if (!isRecord(raw)) {
    return 'AI 生成策略已执行，结果请到工厂运行态和实验事件面板继续查看。';
  }
  if (isRecord(raw.job)) {
    const job = raw.job as Record<string, unknown>;
    return `AI 生成任务已提交，job ${String(job.job_id ?? '-')} 当前状态 ${String(job.status ?? '-')}`;
  }
  const generation = isRecord(raw.generation) ? raw.generation : {};
  const submission = isRecord(raw.submission) ? raw.submission : {};
  const generatedCount = Number(raw.generated_count ?? generation.count ?? Number.NaN);
  const reviewedCount = Number(raw.reviewed_count ?? raw.reviewed ?? Number.NaN);
  const submittedCount = Number(raw.submitted_count ?? submission.submitted_count ?? raw.submitted ?? Number.NaN);
  const traceId = String((isRecord(raw.task_run) ? raw.task_run.trace_id : raw.trace_id) ?? '').trim();
  const snapshotDate = String(raw.snapshot_date ?? '').trim();
  const parts: string[] = [];
  if (Number.isFinite(generatedCount)) parts.push(`生成 ${generatedCount} 条候选`);
  if (Number.isFinite(reviewedCount)) parts.push(`评审 ${reviewedCount} 条`);
  if (Number.isFinite(submittedCount)) parts.push(`提交 ${submittedCount} 条`);
  if (snapshotDate) parts.push(`快照 ${snapshotDate}`);
  if (traceId) parts.push(`trace ${traceId}`);
  return parts.length
    ? `${parts.join('，')}。结果已同步到工厂运行态和实验事件面板。`
    : 'AI 生成策略已执行，结果请到工厂运行态和实验事件面板继续查看。';
}

export default function StrategyMarketPage() {
  const { completeStep } = useOnboarding();
  const router = useRouter();
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const searchParams = useStableSearchParams();
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? user?.username ?? null;
  const localUserIsAdmin = String(user?.role ?? '').trim().toLowerCase() === 'admin';
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const workspace = normalizeWorkspace(searchParams.get('workspace'));
  const entryQuery = searchParams.get('q');
  const entryCategory = searchParams.get('category');
  const [category, setCategory] = useState<string>(entryCategory?.trim() || 'all');
  const [search, setSearch] = useState(entryQuery?.trim() || '');
  const [marketStatusSegment, setMarketStatusSegment] = useState<StrategyMarketStatusSegment>(() =>
    normalizeStrategyStatusSegment(searchParams.get('status')),
  );
  const [incubationStageFilter, setIncubationStageFilter] = useState<StrategyIncubationStageFilter>(() =>
    normalizeIncubationStageFilter(searchParams.get('incubation_stage') ?? searchParams.get('stage')),
  );
  const [showFactoryDetails, setShowFactoryDetails] = useState(shouldOpenFactoryFromTask(task));
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [runStatusFilter, setRunStatusFilter] = useState<RunStatusFilter>('all');
  const [trendMetricKey, setTrendMetricKey] = useState<TrendMetricKey>('candidates_spawned');
  const [showCart, setShowCart] = useState(false);
  const [showFeatured, setShowFeatured] = useState(false);
  const [sortBy, setSortBy] = useState<StrategySortKey>('totalReturn');
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc');
  const isMarketWorkspace = workspace === 'market';
  const isFavoritesWorkspace = workspace === 'favorites';
  const isMineWorkspace = workspace === 'mine';
  const isFactoryWorkspace = workspace === 'factory';
  const shouldLoadFactoryDetails = isFactoryWorkspace && showFactoryDetails;

  const rankQ = useApiQuery<RankingResponse>(
    isMarketWorkspace
      ? `/strategy-market/ranking?limit=${RANKING_PAGE_LIMIT}&status=all` +
          (category === 'all' ? '' : `&strategy_type=${category}`)
      : null,
    {
      enabled: isMarketWorkspace,
      critical: true,
      parse: (raw) => ensureRecordOrArray(raw, '策略榜单') as RankingResponse,
    },
  );
  const factoryMarketViewQ = useApiQuery<FactoryMarketViewResponse>(
    isFactoryWorkspace
      ? `/strategy-market/factory/market-view?include_details=${shouldLoadFactoryDetails ? 'true' : 'false'}${shouldLoadFactoryDetails && expandedRunId ? `&run_id=${encodeURIComponent(expandedRunId)}` : ''}`
      : null,
    {
      enabled: isFactoryWorkspace,
      parse: parseFactoryMarketViewResponse,
      critical: true,
    },
  );
  const capabilityDiagnosticsQ = useApiQuery<StrategyCapabilityDiagnosticsResponse>(
    isFactoryWorkspace ? '/strategy-market/diagnostics/gaps' : null,
    {
      enabled: isFactoryWorkspace,
      staleTime: 60_000,
      parse: parseStrategyCapabilityDiagnosticsResponse,
      nonFatal: true,
    },
  );
  const capabilitiesQ = useApiQuery<CapabilityResponse>(!isFactoryWorkspace ? '/strategy-market/capabilities' : null, {
    enabled: !isFactoryWorkspace,
    critical: true,
  });
  const favoritesQ = useApiQuery<RankingResponse>(
    isFavoritesWorkspace && userId ? '/strategy-market/my-favorites' : null,
    {
      enabled: isFavoritesWorkspace && Boolean(userId),
      parse: (raw) => ensureRecordOrArray(raw, '我的收藏') as RankingResponse,
    },
  );
  const myStrategiesQ = useApiQuery<RankingResponse>(
    isMineWorkspace && userId ? '/strategy-market/my-strategies?limit=50' : null,
    {
      enabled: isMineWorkspace && Boolean(userId),
      parse: (raw) => ensureRecordOrArray(raw, '我的策略') as RankingResponse,
    },
  );

  const runFactoryApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '策略工厂请求已受理，结果会稍后同步到运行态面板',
  });
  const lastDispatchId = useMemo(() => {
    const record = isRecord(runFactoryApi.data) ? runFactoryApi.data : {};
    return String(record.dispatch_id ?? record.request_id ?? '').trim() || null;
  }, [runFactoryApi.data]);
  const dailySnapshotsQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace ? '/strategy-market/daily-snapshots?limit=5' : null,
    { enabled: isFactoryWorkspace, nonFatal: true, staleTime: 60_000 },
  );
  const latestTopnQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace ? '/strategy-market/factory/topn/latest?limit=10' : null,
    { enabled: isFactoryWorkspace, nonFatal: true, staleTime: 60_000 },
  );
  const runTopnQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace && expandedRunId ? `/strategy-market/factory/runs/${encodeURIComponent(expandedRunId)}/topn?limit=10` : null,
    { enabled: isFactoryWorkspace && Boolean(expandedRunId), nonFatal: true, staleTime: 60_000 },
  );
  const dispatchStatusQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace && lastDispatchId ? `/strategy-market/factory/dispatches/${encodeURIComponent(lastDispatchId)}` : null,
    { enabled: isFactoryWorkspace && Boolean(lastDispatchId), nonFatal: true, refetchInterval: 3000 },
  );
  const vectorHealthQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace ? '/strategy-market/vector-health?index_name=strategy_behavior&limit_versions=10' : null,
    { enabled: isFactoryWorkspace, nonFatal: true, staleTime: 60_000 },
  );
  const vectorIndexesQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace ? '/strategy-market/vector-indexes?index_name=strategy_behavior&limit=20' : null,
    { enabled: isFactoryWorkspace, nonFatal: true, staleTime: 60_000 },
  );
  const vectorIndexSnapshotsFactoryQ = useApiQuery<Record<string, unknown>>(
    isFactoryWorkspace ? '/strategy-market/vector-indexes/snapshots?index_name=strategy_behavior&limit=10' : null,
    { enabled: isFactoryWorkspace, nonFatal: true, staleTime: 60_000 },
  );
  const vectorReconcileApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '向量索引对账已提交',
  });
  const vectorRebuildApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '向量索引重建已提交',
  });
  const vectorCleanupApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '向量清理 dry-run 已提交',
  });
  const aiGenerateApi = useApiMutation<Record<string, unknown>>({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: 'AI 策略生成已触发，结果会同步到工厂运行态与实验面板',
  });
  const createPersonalStrategyApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '个人策略草稿已创建',
  });
  const strategyRuntimeActionApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '策略动作已执行',
  });

  const addToCart = useCartStore((state) => state.addStrategy);
  const cartItems = useCartStore((state) => state.items);

  const marketCatalogStrategies = useMemo(
    () => filterAndSortStrategies(rankQ.data, '', sortBy, sortDir),
    [rankQ.data, sortBy, sortDir],
  );
  const marketStrategiesAll = useMemo(
    () => filterAndSortStrategies(rankQ.data, search, sortBy, sortDir),
    [rankQ.data, search, sortBy, sortDir],
  );
  const marketStatusCounts = useMemo(() => getStrategyStatusCounts(marketStrategiesAll), [marketStrategiesAll]);
  const marketStrategies = useMemo(
    () => marketStrategiesAll.filter((strategy) => matchesStrategyStatusSegment(strategy, marketStatusSegment)),
    [marketStatusSegment, marketStrategiesAll],
  );
  const favoriteStrategies = useMemo(
    () => filterAndSortStrategies(favoritesQ.data, search, sortBy, sortDir),
    [favoritesQ.data, search, sortBy, sortDir],
  );
  const myStrategies = useMemo(
    () => filterAndSortStrategies(myStrategiesQ.data, search, sortBy, sortDir),
    [myStrategiesQ.data, search, sortBy, sortDir],
  );
  const workspaceStrategies =
    workspace === 'favorites' ? favoriteStrategies : workspace === 'mine' ? myStrategies : marketStrategies;
  const strategies = useMemo(
    () => workspaceStrategies.filter((strategy) => matchesIncubationStageFilter(strategy, incubationStageFilter)),
    [incubationStageFilter, workspaceStrategies],
  );
  const personalStrategyWorkspaceContext = useMemo(
    () =>
      isMineWorkspace
        ? {
            workspace: 'mine',
            userId,
            strategyCount: myStrategies.length,
            editableCount: myStrategies.filter((strategy) => {
              const ownerState = isRecord((strategy as unknown as Record<string, unknown>).owner_state)
                ? ((strategy as unknown as Record<string, unknown>).owner_state as Record<string, unknown>)
                : {};
              return Boolean(ownerState.editable);
            }).length,
            draftCount: myStrategies.filter(
              (strategy) =>
                String(strategy.status ?? '')
                  .trim()
                  .toLowerCase() === 'draft',
            ).length,
            strategySummaries: myStrategies.slice(0, 5).map((strategy) => {
              const ownerState = isRecord((strategy as unknown as Record<string, unknown>).owner_state)
                ? ((strategy as unknown as Record<string, unknown>).owner_state as Record<string, unknown>)
                : {};
              return {
                id: strategy.id,
                name: strategy.name,
                status: strategy.status ?? null,
                strategyType: strategy.strategy_type ?? null,
                editable: Boolean(ownerState.editable),
                personalStrategy: Boolean(ownerState.personal_strategy),
              };
            }),
          }
        : null,
    [isMineWorkspace, myStrategies, userId],
  );
  const marketStatusLabel = useMemo(() => resolveStatusSegmentLabel(marketStatusSegment), [marketStatusSegment]);
  const marketStatusHelpText = useMemo(() => resolveStatusSegmentHelpText(marketStatusSegment), [marketStatusSegment]);
  const incubationStageLabel = useMemo(
    () => resolveIncubationStageFilterLabel(incubationStageFilter),
    [incubationStageFilter],
  );

  const factoryMarketView = useMemo(
    () => (isFactoryWorkspace ? (factoryMarketViewQ.data ?? null) : null),
    [factoryMarketViewQ.data, isFactoryWorkspace],
  );
  const factoryViewModel = useMemo(
    () => buildFactoryMarketViewModel(factoryMarketView, expandedRunId),
    [expandedRunId, factoryMarketView],
  );
  const factoryStatus = factoryViewModel.status;
  const latestSnapshot = factoryViewModel.latestSnapshot;
  const factorySummary = factoryViewModel.summary;
  const factoryCapabilities = useMemo(
    () => (isFactoryWorkspace ? factoryViewModel.capabilities : (capabilitiesQ.data ?? {})),
    [capabilitiesQ.data, factoryViewModel.capabilities, isFactoryWorkspace],
  );
  const actorPermissions = useMemo(
    () => (isFactoryWorkspace ? factoryViewModel.actorPermissions : (factoryCapabilities.actor_permissions ?? {})),
    [factoryCapabilities, factoryViewModel.actorPermissions, isFactoryWorkspace],
  );
  const canRunFactory = Boolean(actorPermissions.can_run_factory || localUserIsAdmin);
  const canAiGenerate = Boolean(actorPermissions.can_ai_generate || localUserIsAdmin);
  const canCreatePersonalStrategy = Boolean(actorPermissions.can_create_personal_strategy && userId);
  const canViewOperatorPanels = Boolean(actorPermissions.can_view_operator_panels || localUserIsAdmin);
  const aiGenerateSummary = useMemo(
    () => (aiGenerateApi.data ? summarizeAiGenerateResult(aiGenerateApi.data) : null),
    [aiGenerateApi.data],
  );

  const factorySectionErrors = factoryViewModel.sectionErrors;
  const snapshotCompletionRatio = factoryViewModel.snapshotCompletionRatio;
  const snapshotFailureCount = factoryViewModel.snapshotFailureCount;
  const snapshotDegraded = factoryViewModel.snapshotDegraded;

  const capabilityBadges = useMemo(
    () => [
      { key: 'daily_snapshot', label: '日快照', enabled: factoryCapabilities.daily_snapshot ?? false },
      { key: 'paper_incubation', label: '模拟盘孵化', enabled: factoryCapabilities.paper_incubation ?? false },
      { key: 'runtime_risk', label: '实时风控', enabled: factoryCapabilities.runtime_risk ?? false },
      { key: 'execution_risk', label: '执行风控', enabled: factoryCapabilities.execution_risk ?? false },
      { key: 'runtime_controls', label: '控制平面', enabled: factoryCapabilities.runtime_controls ?? false },
      { key: 'promotion_pipeline', label: '晋级流水线', enabled: factoryCapabilities.promotion_pipeline ?? false },
      { key: 'projection_snapshots', label: '投影快照', enabled: factoryCapabilities.projection_snapshots ?? false },
      { key: 'event_replay', label: '事件回放', enabled: factoryCapabilities.event_replay ?? false },
      { key: 'vector_platform', label: '向量平台', enabled: factoryCapabilities.vector_platform ?? false },
      { key: 'vector_governance', label: '索引治理', enabled: factoryCapabilities.vector_governance ?? false },
      { key: 'ai_generation', label: 'AI生成', enabled: factoryCapabilities.ai_generation ?? false },
      { key: 'multi_agent_review', label: '多代理评审', enabled: factoryCapabilities.multi_agent_review ?? false },
      { key: 'quality_governance', label: '质量治理', enabled: factoryCapabilities.quality_governance ?? false },
      { key: 'domain_events', label: '领域事件', enabled: factoryCapabilities.domain_events ?? false },
      { key: 'domain_projection', label: '事件投影', enabled: factoryCapabilities.domain_projection ?? false },
      { key: 'runtime_cycle', label: '运行闭环', enabled: factoryCapabilities.runtime_cycle ?? false },
      {
        key: 'research_protocol_v2',
        label: '研究协议V2',
        enabled: factoryCapabilities.research_protocol_v2_enabled ?? false,
      },
      { key: 'gate_model_v2', label: '门禁模型V2', enabled: factoryCapabilities.gate_model_v2_enabled ?? false },
      { key: 'trace_ledger_v2', label: '追踪账本V2', enabled: factoryCapabilities.trace_ledger_v2_enabled ?? false },
      { key: 'feedback_v2', label: '反馈闭环V2', enabled: factoryCapabilities.feedback_v2_enabled ?? false },
    ],
    [factoryCapabilities],
  );

  const factoryRuns = factoryViewModel.factoryRuns;
  const failedRuns = factoryViewModel.failedRuns;
  const filteredRuns = useMemo(() => {
    if (runStatusFilter === 'all') return factoryRuns;
    return factoryRuns.filter((item) => item.status === runStatusFilter);
  }, [factoryRuns, runStatusFilter]);
  const comparableRuns = useMemo(() => filteredRuns.slice(0, 5), [filteredRuns]);
  const trendRuns = useMemo(() => [...comparableRuns].reverse(), [comparableRuns]);

  const factoryWorkspaceReady = Boolean(factoryStatus || factoryRuns.length > 0);
  const factoryPrimaryErrors = [factorySectionErrors.status, factorySectionErrors.runs].filter(
    (value): value is string => Boolean(value),
  );
  const factoryWorkspaceError =
    factoryMarketViewQ.error || (factoryPrimaryErrors.length > 1 ? factoryPrimaryErrors[0] : null);
  const factoryWorkspaceDegradedReason =
    !factoryWorkspaceError && factoryPrimaryErrors.length === 1
      ? factoryPrimaryErrors[0]
      : !factoryWorkspaceError
        ? (factoryMarketView?.errors?.[0] ?? null)
        : null;
  const workspaceLoading =
    workspace === 'factory'
      ? !factoryWorkspaceReady && factoryMarketViewQ.isPending
      : workspace === 'favorites'
        ? favoritesQ.isPending
        : workspace === 'mine'
          ? myStrategiesQ.isPending
          : rankQ.isPending;
  const workspaceError =
    workspace === 'factory'
      ? factoryWorkspaceError
      : workspace === 'favorites'
        ? favoritesQ.error
        : workspace === 'mine'
          ? myStrategiesQ.error
          : rankQ.error;
  const showEmptyStrategyState =
    workspace !== 'factory' &&
    !workspaceLoading &&
    !workspaceError &&
    (workspace === 'market'
      ? category === 'all' && !search.trim() && marketCatalogStrategies.length === 0
      : strategies.length === 0);
  const featuredStrategies = useMemo(() => strategies.slice(0, 3), [strategies]);

  const factoryOverview = useMemo(
    () =>
      factoryMarketView?.surface?.overview_cards?.length
        ? factoryMarketView.surface.overview_cards.map((item) => ({
            label: item.label ?? '-',
            value: item.value ?? '-',
          }))
        : [
            { label: '调度状态', value: factoryStatus?.running ? '运行中' : '待命' },
            { label: '候选生成', value: String(factorySummary.candidates_spawned ?? 0) },
            { label: '质检通过', value: String(factorySummary.passed_quality_gate ?? 0) },
            { label: '最新快照', value: latestSnapshot?.snapshot_date ?? '暂无' },
          ],
    [
      factoryMarketView,
      factoryStatus?.running,
      factorySummary.candidates_spawned,
      factorySummary.passed_quality_gate,
      latestSnapshot?.snapshot_date,
    ],
  );
  const bestAnnualReturn = useMemo(() => {
    if (!strategies.length) return null;
    return strategies.reduce((best, strategy) => {
      const value = Number(getStrategyMetricSnapshot(strategy).totalReturn ?? Number.NEGATIVE_INFINITY);
      return value > best ? value : best;
    }, Number.NEGATIVE_INFINITY);
  }, [strategies]);
  const bestSharpe = useMemo(() => {
    if (!strategies.length) return null;
    return strategies.reduce((best, strategy) => {
      const value = Number(getStrategyMetricSnapshot(strategy).sharpe ?? Number.NEGATIVE_INFINITY);
      return value > best ? value : best;
    }, Number.NEGATIVE_INFINITY);
  }, [strategies]);
  const enabledCapabilityCount = useMemo(
    () => capabilityBadges.filter((item) => item.enabled).length,
    [capabilityBadges],
  );
  const activeCategoryLabel = useMemo(() => resolveCategoryLabel(category), [category]);
  const factoryObservabilityRoot = useMemo(
    () => (isRecord(factoryMarketView?.observability) ? factoryMarketView.observability : {}),
    [factoryMarketView],
  );
  const factoryObservabilityOverview = useMemo(
    () => (isRecord(factoryObservabilityRoot.overview) ? factoryObservabilityRoot.overview : {}),
    [factoryObservabilityRoot],
  );
  const factoryObservabilityFactory = useMemo(
    () => (isRecord(factoryObservabilityRoot.factory) ? factoryObservabilityRoot.factory : {}),
    [factoryObservabilityRoot],
  );
  const factoryObservabilityGovernance = useMemo(
    () => (isRecord(factoryObservabilityRoot.factor_governance) ? factoryObservabilityRoot.factor_governance : {}),
    [factoryObservabilityRoot],
  );
  const factoryObservabilityScheduler = useMemo(
    () => (isRecord(factoryObservabilityGovernance.scheduler) ? factoryObservabilityGovernance.scheduler : {}),
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityRecentRun = useMemo(
    () => (isRecord(factoryObservabilityGovernance.recent_run) ? factoryObservabilityGovernance.recent_run : {}),
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityRegistrySummary = useMemo(
    () =>
      isRecord(factoryObservabilityGovernance.registry_summary) ? factoryObservabilityGovernance.registry_summary : {},
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityActivePool = useMemo(
    () => (isRecord(factoryObservabilityGovernance.active_pool) ? factoryObservabilityGovernance.active_pool : {}),
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityRetrainSummary = useMemo(
    () =>
      isRecord(factoryObservabilityGovernance.retrain_summary) ? factoryObservabilityGovernance.retrain_summary : {},
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityRetrainQueue = useMemo(
    () => extractArray(factoryObservabilityGovernance, 'retrain_queue'),
    [factoryObservabilityGovernance],
  );
  const factoryObservabilityErrors = useMemo(() => {
    const errors = Array.isArray(factoryObservabilityRoot.errors) ? factoryObservabilityRoot.errors : [];
    return factorySectionErrors.observability ? [factorySectionErrors.observability, ...errors] : errors;
  }, [factoryObservabilityRoot, factorySectionErrors.observability]);
  const factoryObservabilityFamilyRows = useMemo(
    () => extractArray(factoryObservabilityActivePool, 'family_summary'),
    [factoryObservabilityActivePool],
  );
  const factoryObservabilityRegimeRows = useMemo(
    () => countRows(factoryObservabilityActivePool.regime_summary, 'regime_summary'),
    [factoryObservabilityActivePool],
  );
  const factoryObservabilityStageRows = useMemo(
    () => countRows(factoryObservabilityRegistrySummary.registry_stage_counts, 'registry_stage'),
    [factoryObservabilityRegistrySummary],
  );
  const visibleFactoryOutputs = factoryViewModel.visibleOutputs;
  const workspaceLabel =
    workspace === 'favorites'
      ? '我的收藏'
      : workspace === 'mine'
        ? '我的策略'
        : workspace === 'factory'
          ? '工厂运行态'
          : '市场策略';
  const workspaceSummary =
    workspace === 'favorites'
      ? `只保留你已经收藏的策略，方便继续比较、复制为个人版本或加入组合。当前孵化阶段筛选为“${incubationStageLabel}”。`
      : workspace === 'mine'
        ? `这里集中管理你的个人策略草稿与个人版本，优先做编辑、AI 优化和模拟盘测试。当前孵化阶段筛选为“${incubationStageLabel}”。`
        : workspace === 'factory'
          ? `工厂运行、快照、可观测性与最近 run 集中在这里；当前最近 ${factoryRuns.length} 个 run，失败 ${failedRuns.length} 个，工厂明细${showFactoryDetails ? '已展开' : '默认收起'}。`
          : `市场目录按生命周期分层展示，当前处于“${marketStatusLabel}”分层，孵化阶段筛选为“${incubationStageLabel}”。${marketStatusHelpText}`;
  const workspaceCountLabel =
    workspace === 'favorites'
      ? '已收藏策略'
      : workspace === 'mine'
        ? '个人策略'
        : workspace === 'factory'
          ? '最近工厂运行'
          : `${marketStatusLabel}策略`;
  const heroSummaryMetrics = useMemo(
    () =>
      workspace === 'factory'
        ? factoryMarketView?.surface?.hero_cards?.length
          ? normalizeHeroMetricCards(
              factoryMarketView.surface.hero_cards as Array<Record<string, unknown>>,
              'factory-hero',
            )
          : [
              { key: 'factory-runs', label: '最近工厂运行', value: String(factoryRuns.length) },
              {
                key: 'factory-dispatch',
                label: '调度状态',
                value: factoryStatus?.running ? '运行中' : '待命',
                tone: factoryStatus?.running ? ('success' as const) : ('default' as const),
              },
              {
                key: 'factory-failed-runs',
                label: '最近失败运行',
                value: String(failedRuns.length),
                tone: failedRuns.length > 0 ? ('danger' as const) : ('success' as const),
              },
              { key: 'factory-latest-snapshot', label: '最新快照', value: latestSnapshot?.snapshot_date ?? '暂无' },
            ]
        : undefined,
    [
      factoryMarketView,
      factoryRuns.length,
      factoryStatus?.running,
      failedRuns.length,
      latestSnapshot?.snapshot_date,
      workspace,
    ],
  );
  const heroObservabilityMetrics = useMemo(
    () =>
      factoryMarketView?.surface?.observability_cards?.length
        ? normalizeHeroMetricCards(
            factoryMarketView.surface.observability_cards as Array<Record<string, unknown>>,
            'factory-observability',
          )
        : [
            {
              key: 'observability-factory-status',
              label: '工厂状态',
              value: factoryStatus?.running ? '运行中' : '待命',
              tone: factoryStatus?.running ? ('success' as const) : ('default' as const),
            },
            {
              key: 'observability-active-factor-count',
              label: '活跃因子',
              value: String(factoryObservabilityOverview.active_factor_count ?? 0),
            },
            {
              key: 'observability-scheduler-quality-status',
              label: '调度质量',
              value: String(factoryObservabilityOverview.scheduler_quality_status ?? '-'),
              tone: factoryObservabilityOverview.scheduler_stale ? ('danger' as const) : ('success' as const),
            },
          ],
    [
      factoryMarketView,
      factoryObservabilityOverview.active_factor_count,
      factoryObservabilityOverview.scheduler_quality_status,
      factoryObservabilityOverview.scheduler_stale,
      factoryStatus?.running,
    ],
  );
  const heroAiRecommendationPrompt =
    workspace === 'factory'
      ? `当前工厂运行态最近 ${factoryRuns.length} 个 run，失败 ${failedRuns.length} 个，调度 ${factoryStatus?.running ? '运行中' : '待命'}，请建议下一步该优先检查哪些工厂动作、治理项或运行链路。`
      : `当前${workspaceLabel}共 ${strategies.length} 个策略，请推荐几个值得重点关注的，并说明理由`;

  const updateWorkspace = useCallback(
    (next: StrategyWorkspace) => {
      const qs = new URLSearchParams(searchParams.toString());
      if (next === 'market') {
        qs.delete('workspace');
      } else {
        qs.set('workspace', next);
      }
      const nextHref = qs.toString() ? `/strategy-market?${qs.toString()}` : '/strategy-market';
      router.push(nextHref);
    },
    [router, searchParams],
  );

  const handleCreatePersonalStrategy = useCallback(async () => {
    if (!userId) {
      window.alert('请先登录后再创建个人策略');
      return;
    }
    const now = new Date();
    const payload = await createPersonalStrategyApi.triggerAsync(
      '/strategy-market/create',
      { method: 'POST' },
      {
        name: `我的策略 ${now.toLocaleDateString('zh-CN')}`,
        strategy_type: category === 'all' ? 'custom' : category,
        description: '个人策略草稿，可继续编辑、AI 优化和模拟盘测试。',
        params: {
          metadata: {
            created_from: 'strategy_market.mine',
            created_at: now.toISOString(),
          },
        },
        factor_weights: {},
        tags: ['personal_strategy', 'draft_personal_strategy'],
      },
    );
    const record = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
    const strategyRecord =
      record.strategy && typeof record.strategy === 'object' ? (record.strategy as Record<string, unknown>) : null;
    const nextId = String(record.strategy_id ?? strategyRecord?.id ?? '').trim();
    if (nextId) {
      router.push(`/strategy-market/${encodeURIComponent(nextId)}`);
    }
  }, [category, createPersonalStrategyApi, router, userId]);

  const handleRunFactoryOperatorJob = useCallback(() => {
    if (!window.confirm('确认提交策略工厂后台调度任务？')) return;
    runFactoryApi.trigger(
      '/strategy-market/factory/dispatch/run',
      { method: 'POST' },
      {},
    );
  }, [runFactoryApi]);

  const handleVectorReconcile = useCallback(() => {
    vectorReconcileApi.trigger(
      '/strategy-market/vector-indexes/reconcile',
      { method: 'POST' },
      { index_name: 'strategy_behavior', profile_type: 'behavior', limit_profiles: 500 },
    );
  }, [vectorReconcileApi]);

  const handleVectorRebuild = useCallback(() => {
    if (!window.confirm('确认重建 strategy_behavior 向量索引？')) return;
    vectorRebuildApi.trigger(
      '/strategy-market/vector-indexes/rebuild',
      { method: 'POST' },
      { index_name: 'strategy_behavior', profile_type: 'behavior', limit: 500 },
    );
  }, [vectorRebuildApi]);

  const handleVectorCleanupDryRun = useCallback(() => {
    vectorCleanupApi.trigger(
      '/strategy-market/vector-indexes/cleanup',
      { method: 'POST' },
      { index_name: 'strategy_behavior', dry_run: true, keep_versions: 3, limit_versions: 50 },
    );
  }, [vectorCleanupApi]);

  const handleRuntimeAction = useCallback(async (action: StrategyRuntimeActionContractItem, strategy: Strategy) => {
    if (action.status === 'unavailable') {
      window.alert(action.unavailable_reason ?? '当前动作不可用');
      return;
    }
    if (action.requires_confirmation) {
      const confirmed = window.confirm(action.confirm?.message ?? `确认执行“${action.label}”？`);
      if (!confirmed) return;
    }
    if (action.navigation?.href && !action.endpoint) {
      router.push(action.navigation.href);
      return;
    }
    if (!action.endpoint?.path) {
      window.alert('动作合同缺少可执行入口');
      return;
    }
    const payload = await strategyRuntimeActionApi.triggerAsync(
      action.endpoint.path,
      { method: action.endpoint.method },
      action.endpoint.body ?? {},
    );
    const record = isRecord(payload) ? payload : {};
    if (action.id === 'save_as_personal_strategy') {
      const strategyRecord = isRecord(record.strategy) ? record.strategy : {};
      const nextId = String(record.strategy_id ?? strategyRecord.id ?? '').trim();
      if (nextId) {
        router.push(`/strategy-market/${encodeURIComponent(nextId)}`);
      }
      return;
    }
    if (action.id === 'open_personal_paper_session') {
      const session = isRecord(record.session) ? record.session : {};
      const account = isRecord(record.account) ? record.account : {};
      const accountId = String(account.id ?? session.account_id ?? '').trim();
      const qs = new URLSearchParams({
        from: 'strategy-market',
        strategy_id: String(strategy.id),
        mode: 'personal-strategy',
        ...(accountId ? { account_id: accountId } : {}),
      });
      router.push(`/paper-trading?${qs.toString()}`);
      return;
    }
    if (action.navigation?.href) {
      router.push(action.navigation.href);
    }
  }, [router, strategyRuntimeActionApi]);

  useEffect(() => {
    if (category !== 'all' || search.trim() || showFactoryDetails || showFeatured || cartItems.length > 0) {
      completeStep('strategy-market');
    }
  }, [cartItems.length, category, completeStep, search, showFactoryDetails, showFeatured]);

  const pageActions = useMemo(
    () => [
      {
        id: 'strategy-market.refresh',
        label: '刷新策略页',
        description: '刷新当前策略工作区的数据',
        keywords: ['刷新', '更新'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: async () => {
          await Promise.all([
            rankQ.refetch(),
            favoritesQ.refetch(),
            myStrategiesQ.refetch(),
            factoryMarketViewQ.refetch(),
            capabilityDiagnosticsQ.refetch(),
            dailySnapshotsQ.refetch(),
            latestTopnQ.refetch(),
            vectorHealthQ.refetch(),
            vectorIndexesQ.refetch(),
            vectorIndexSnapshotsFactoryQ.refetch(),
          ]);
          return { message: '策略页已刷新' };
        },
      },
      {
        id: 'strategy-market.open-workspace',
        label: '打开策略工作区',
        description: '打开指定策略工作区或当前工作区',
        keywords: ['打开', '工作区', '切换'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: (payload?: Record<string, unknown>) => {
          const next = normalizeWorkspace(String(payload?.workspace ?? workspace));
          updateWorkspace(next);
          return { message: `已打开${next === 'market' ? '市场策略' : next === 'favorites' ? '我的收藏' : next === 'mine' ? '我的策略' : '工厂运行态'}工作区` };
        },
      },
      {
        id: 'strategy-market.switch-market',
        label: '切到市场策略',
        description: '查看市场榜单和可见策略目录',
        keywords: ['市场策略', '榜单'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          updateWorkspace('market');
          return { message: '已切到市场策略工作区' };
        },
      },
      {
        id: 'strategy-market.switch-favorites',
        label: '切到我的收藏',
        description: '查看你已经收藏的策略',
        keywords: ['我的收藏', '收藏'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          updateWorkspace('favorites');
          return { message: '已切到我的收藏工作区' };
        },
      },
      {
        id: 'strategy-market.switch-mine',
        label: '切到我的策略',
        description: '查看并管理你的个人策略',
        keywords: ['我的策略', '个人策略'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          updateWorkspace('mine');
          return { message: '已切到我的策略工作区' };
        },
      },
      {
        id: 'strategy-market.switch-factory',
        label: '切到工厂运行态',
        description: '查看工厂运行与可观测性',
        keywords: ['工厂', '运行态'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          updateWorkspace('factory');
          return { message: '已切到工厂运行态工作区' };
        },
      },
      {
        id: 'strategy-market.clear-filters',
        label: '清空筛选',
        description: '重置分类、搜索词和精选模式',
        keywords: ['清空', '筛选'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          setCategory('all');
          setSearch('');
          setMarketStatusSegment('visible');
          setIncubationStageFilter('all');
          setShowFeatured(false);
          return { message: '已清空策略筛选条件' };
        },
      },
      {
        id: 'strategy-market.toggle-featured',
        label: showFeatured ? '关闭精选模式' : '只看精选策略',
        description: '切换是否只保留精选策略',
        keywords: ['精选', '筛选'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          setShowFeatured((prev) => !prev);
          return { message: showFeatured ? '已切回全部策略' : '已切换为精选策略' };
        },
      },
      {
        id: 'strategy-market.toggle-factory',
        label: showFactoryDetails ? '收起工厂运行态' : '展开工厂运行态',
        description: '切换工厂运行态与可观测性面板',
        keywords: ['工厂', '运行态'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          if (workspace !== 'factory') {
            updateWorkspace('factory');
            return { message: '已切到工厂运行态工作区' };
          }
          setShowFactoryDetails((prev) => !prev);
          return { message: showFactoryDetails ? '已收起工厂运行态' : '已展开工厂运行态' };
        },
      },
      {
        id: 'strategy-market.open-cart',
        label: '打开策略购物车',
        description: '打开当前策略购物车查看待配置条目',
        keywords: ['购物车', '策略'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          setShowCart(true);
          return { message: '已打开策略购物车' };
        },
      },
      {
        id: 'strategy-market.open-top-strategy',
        label: '打开当前第一条策略详情',
        description: '进入当前工作区排序最靠前的策略详情页',
        keywords: ['榜单', '详情'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
        run: () => {
          const topStrategy = featuredStrategies[0] ?? strategies[0];
          if (!topStrategy?.id) {
            throw new Error('当前没有可打开的策略详情');
          }
          router.push(`/strategy-market/${encodeURIComponent(String(topStrategy.id))}`);
          return { message: `已打开 ${topStrategy.name} 的策略详情` };
        },
      },
      ...(canCreatePersonalStrategy
        ? [
            {
              id: 'strategy-market.create-personal',
              label: '新建个人策略',
              description: '创建一条新的个人策略草稿',
              keywords: ['新建', '个人策略'],
              scope: 'page' as const,
              pageKey: 'strategy-market',
              mutationEffect: 'stateful' as const,
              run: async () => {
                await handleCreatePersonalStrategy();
                return { message: '已创建新的个人策略草稿' };
              },
            },
          ]
        : []),
      ...(canAiGenerate
        ? [
            {
              id: 'strategy-market.ai-generate',
              label: 'AI 生成策略',
              description: '调用策略工厂的 AI 生成入口创建候选策略',
              keywords: ['AI生成', '策略工厂'],
              scope: 'page' as const,
              pageKey: 'strategy-market',
              mutationEffect: 'stateful' as const,
              run: async () => {
                if (!window.confirm('确认提交 AI 生成策略任务？')) {
                  return { message: '已取消 AI 策略生成' };
                }
                await aiGenerateApi.triggerAsync(
                  '/strategy-market/operator/jobs',
                  { method: 'POST' },
                  {
                    action: 'ai_generate',
                    params: { limit: 3, auto_submit: false },
                    confirmed: true,
                    confirmation_text: 'ai_generate',
                    reason: 'strategy_market_ai_generate',
                    timeout_ms: 120000,
                  },
                );
                return { message: '已触发 AI 策略生成，请到工厂运行态查看结果' };
              },
            },
          ]
        : []),
    ],
    [
      aiGenerateApi,
      canAiGenerate,
      canCreatePersonalStrategy,
      capabilityDiagnosticsQ,
      dailySnapshotsQ,
      featuredStrategies,
      factoryMarketViewQ,
      favoritesQ,
      handleCreatePersonalStrategy,
      latestTopnQ,
      myStrategiesQ,
      rankQ,
      router,
      setCategory,
      setIncubationStageFilter,
      setMarketStatusSegment,
      setSearch,
      setShowCart,
      setShowFactoryDetails,
      setShowFeatured,
      showFactoryDetails,
      showFeatured,
      strategies,
      updateWorkspace,
      vectorHealthQ,
      vectorIndexesQ,
      vectorIndexSnapshotsFactoryQ,
      workspace,
    ],
  );

  usePageActions(pageActions);
  const strategyMarketSummary =
    workspace === 'market'
      ? `${workspaceLabel} 当前分层 ${marketStatusLabel}，孵化阶段 ${incubationStageLabel}，共 ${strategies.length} 条，目录总量 ${marketCatalogStrategies.length} 条，分类 ${activeCategoryLabel}，搜索词 ${search.trim() || '无'}，${showFeatured ? '仅看精选' : '展示全部'}。`
      : workspace === 'factory'
        ? `${workspaceLabel} 最近 ${factoryRuns.length} 个 run，失败 ${failedRuns.length} 个，调度 ${factoryStatus?.running ? '运行中' : '待命'}，${showFactoryDetails ? '已展开工厂明细' : '明细默认收起'}。`
        : `${workspaceLabel} 当前孵化阶段 ${incubationStageLabel}，可见 ${strategies.length} 条，分类 ${activeCategoryLabel}，搜索词 ${search.trim() || '无'}，${showFeatured ? '仅看精选' : '展示全部'}。`;
  const strategyMarketEvidence =
    workspace === 'factory'
      ? [
          { label: '工作区', value: workspaceLabel },
          { label: '最近运行', value: String(factoryRuns.length) },
          { label: '失败运行', value: String(failedRuns.length) },
          { label: '调度状态', value: factoryStatus?.running ? '运行中' : '待命' },
          { label: '可见产物', value: String(visibleFactoryOutputs.length) },
          { label: '明细面板', value: showFactoryDetails ? '已展开' : '已收起' },
        ]
      : [
          { label: '工作区', value: workspaceLabel },
          { label: '策略数', value: String(strategies.length) },
          ...(workspace === 'market' ? [{ label: '目录总量', value: String(marketCatalogStrategies.length) }] : []),
          { label: '孵化阶段', value: incubationStageLabel },
          { label: '分类', value: activeCategoryLabel },
          { label: '搜索词', value: search.trim() || '无' },
        ];
  const strategyMarketLinks = [
    { id: 'strategy-market-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
    { id: 'strategy-market-open-skills-link', label: '技能中心', href: '/skills?from=strategy-market' },
    { id: 'strategy-market-open-data-link', label: '数据中心', href: '/data' },
    { id: 'strategy-market-open-research-link', label: '研究中心', href: '/research' },
  ];
  const strategyMarketRiskNotes = [
    ...(workspaceError ? [`当前工作区存在错误：${workspaceError}`] : []),
    ...(workspace === 'factory' && factoryWorkspaceDegradedReason
      ? [`工厂主链部分降级：${factoryWorkspaceDegradedReason}`]
      : []),
    ...(snapshotDegraded ? ['当前工厂快照处于降级态，运行指标需要二次核对。'] : []),
    ...(workspace === 'factory' && failedRuns.length > 0 ? [`最近运行中有 ${failedRuns.length} 个失败 run。`] : []),
  ];
  const strategyMarketResult = buildLocalResultContract({
    summary: strategyMarketSummary,
    status: workspaceError
      ? 'unavailable'
      : snapshotDegraded || (workspace === 'factory' && Boolean(factoryWorkspaceDegradedReason))
        ? 'degraded'
        : workspace === 'factory'
          ? factoryWorkspaceReady
            ? 'ready'
            : 'empty'
          : strategies.length === 0
            ? 'empty'
            : 'ready',
    availableViews: strategies.length > 1 || factoryRuns.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: [
      'strategy-market.refresh',
      'strategy-market.toggle-factory',
      'strategy-market.open-workspace',
      'strategy-market.open-cart',
    ],
    recommendedLinks: strategyMarketLinks,
    recommendedNextActions: [
      workspace === 'factory'
        ? showFactoryDetails
          ? '先看工厂运行态是否稳定，再决定回到目录还是继续追 run 细节。'
          : '先看概况与最近 run，再按需展开工厂明细。'
        : '先在当前工作区收紧分类、状态和孵化阶段，再决定是否展开工厂面板。',
      workspace === 'factory'
        ? factoryRuns.length === 0
          ? '如果近期没有 run，优先触发一轮工厂或检查调度状态。'
          : '只在需要排查治理链路时，再展开工厂联动观测。'
        : strategies.length === 0
          ? '当前没有命中策略，优先调整筛选而不是继续翻空状态。'
          : '只有在筛完一轮仍无结论时，再展开策略工作台看补充动作。',
    ],
    evidence: strategyMarketEvidence,
    riskNotes: strategyMarketRiskNotes,
    emptyState: {
      title: '当前筛选还没有命中策略',
      description: '先调整分类、搜索词或孵化阶段，不要在空目录里继续停留。',
      example: 'workspace=market，category=all，status=all',
    },
    degradedState:
      snapshotDegraded || workspaceError
        ? {
            title: '策略页当前处于降级或错误态',
            description: '先恢复目录或工厂链路，再继续解释运行指标。',
            reason: workspaceError || strategyMarketRiskNotes.join('；'),
          }
        : null,
    freshness: latestSnapshot?.snapshot_date ? { asOf: latestSnapshot.snapshot_date, label: '策略快照' } : null,
    platformMeta: {
      sourceTool: 'strategy-market',
      sourceChain: [workspace, category, marketStatusSegment, incubationStageFilter],
      degraded: snapshotDegraded || Boolean(workspaceError),
      fallbackReason: workspaceError ? [workspaceError] : undefined,
    },
    workbenchTask: defaultWorkbenchTask(
      'strategy-market',
      `复查${workspaceLabel}`,
      searchParams.toString() ? `/strategy-market?${searchParams.toString()}` : '/strategy-market',
      'strategy-market-review',
      { workspace, category, search, marketStatusSegment, incubationStageFilter, showFeatured },
    ),
  });

  usePageContext({
    pageKey: 'strategy-market',
    title: '策略超市',
    summary: strategyMarketSummary,
    primaryGoal: '在最少筛选动作里定位下一批值得继续处理的策略或工厂运行项。',
    requiredInputs: ['workspace', 'category 或 search'],
    objectType:
      workspace === 'factory' ? 'strategy' : workspace === 'mine' ? 'personal-strategy-workspace' : 'strategy-list',
    objectId:
      workspace === 'factory'
        ? 'factory-runtime'
        : workspace === 'mine'
          ? `mine:${userId ?? 'anonymous'}`
          : `${workspace}:${category}:${search.trim() || 'all'}`,
    resultType:
      workspace === 'factory'
        ? 'strategy-factory-runtime'
        : workspace === 'mine'
          ? 'personal-strategy-catalog'
          : 'strategy-catalog',
    tags: [
      `${workspaceLabel} ${strategies.length} 条`,
      ...(workspace === 'market'
        ? [`状态分层 ${marketStatusLabel}`, `目录总量 ${marketCatalogStrategies.length} 条`]
        : []),
      `孵化阶段 ${incubationStageLabel}`,
      activeCategoryLabel,
      showFeatured ? '精选模式' : '全部策略',
      workspace === 'factory' ? (showFactoryDetails ? '工厂面板展开' : '工厂面板收起') : '目录工作区',
      `${cartItems.length} 个购物车条目`,
    ],
    suggestions: [
      '先总结当前工作区最值得继续处理的策略或运行状态',
      '如果需要页面联动，请选择一个低风险动作直接执行',
      '帮我判断现在应该继续筛策略、看我的收藏，还是去工厂运行态',
    ],
    recommendedNextActions: strategyMarketResult.recommendedNextActions,
    recommendedActions: strategyMarketResult.recommendedActions ?? [],
    recommendedLinks: strategyMarketResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(strategyMarketResult.evidence),
    riskNotes: strategyMarketResult.riskNotes ?? [],
    freshness: strategyMarketResult.freshness ?? null,
    dataFreshness: strategyMarketResult.freshness?.updatedAt ?? strategyMarketResult.freshness?.asOf ?? null,
    degradedReason: strategyMarketRiskNotes,
    raw: {
      workspace,
      category,
      search,
      marketStatusSegment,
      marketStatusLabel,
      marketStatusCounts,
      marketCatalogTotal: marketCatalogStrategies.length,
      incubationStageFilter,
      incubationStageLabel,
      showFeatured,
      showFactoryDetails,
      cartItems: cartItems.length,
      topStrategy: featuredStrategies[0]
        ? {
            id: featuredStrategies[0].id,
            name: featuredStrategies[0].name,
          }
        : null,
      enabledCapabilityCount,
      failedRuns: failedRuns.length,
      visibleFactoryOutputCount: visibleFactoryOutputs.length,
      visibleFactoryOutputs: visibleFactoryOutputs.map((item) => ({
        kind: item.kind ?? null,
        title: item.title ?? null,
        status: item.status ?? null,
      })),
      canAiGenerate,
      canCreatePersonalStrategy,
      aiGenerateSummary,
      personalStrategyWorkspace: personalStrategyWorkspaceContext,
      entryQuery: entryQuery ?? null,
      entryCategory: entryCategory ?? null,
    },
  });

  return (
    <PageContainer className="space-y-5">
      <SectionCard className="mt-0">
        {compactLayout ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="eyebrow">Workspace Switch</div>
                <div className="mt-2 text-sm font-medium text-text-primary">当前工作区：{workspaceLabel}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="info">
                  {workspaceCountLabel} {workspace === 'factory' ? factoryRuns.length : strategies.length}
                </Badge>
                {workspace === 'market' ? <Badge variant="neutral">目录 {marketCatalogStrategies.length}</Badge> : null}
              </div>
            </div>
            <TabBar
              tabs={[
                { key: 'market', label: '市场策略' },
                { key: 'favorites', label: '我的收藏' },
                { key: 'mine', label: '我的策略' },
                { key: 'factory', label: '工厂运行态' },
              ]}
              active={workspace}
              onChange={(value) => updateWorkspace(value as StrategyWorkspace)}
            />
            <Link
              href="/strategy-market/diagnostics"
              className="inline-flex rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary no-underline"
            >
              核心链路验收
            </Link>
            <p className="mb-0 text-xs leading-6 text-text-secondary">{workspaceSummary}</p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">Workspace Switch</div>
                <h2 className="mt-2 mb-0">当前工作区：{workspaceLabel}</h2>
                <p className="mt-2 mb-0 text-sm leading-7 text-text-secondary">{workspaceSummary}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="info">
                  {workspaceCountLabel} {workspace === 'factory' ? factoryRuns.length : strategies.length}
                </Badge>
                {workspace === 'market' ? (
                  <Badge variant="neutral">目录总量 {marketCatalogStrategies.length}</Badge>
                ) : null}
                {userId ? <Badge variant="neutral">当前用户 {userId}</Badge> : <Badge variant="warning">未登录</Badge>}
                {canViewOperatorPanels ? (
                  <Badge variant="success">可看运营面板</Badge>
                ) : (
                  <Badge variant="neutral">用户视图</Badge>
                )}
                <Link
                  href="/strategy-market/diagnostics"
                  className="inline-flex rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-text-primary no-underline"
                >
                  核心链路验收
                </Link>
              </div>
            </div>
            <div className="mt-4">
              <TabBar
                tabs={[
                  { key: 'market', label: '市场策略' },
                  { key: 'favorites', label: '我的收藏' },
                  { key: 'mine', label: '我的策略' },
                  { key: 'factory', label: '工厂运行态' },
                ]}
                active={workspace}
                onChange={(value) => updateWorkspace(value as StrategyWorkspace)}
              />
            </div>
          </>
        )}
      </SectionCard>

      <StrategyMarketHeroSection
        from={from}
        task={task}
        workspace={workspace}
        capabilityBadges={capabilityBadges}
        strategyCount={strategies.length}
        enabledCapabilityCount={enabledCapabilityCount}
        bestAnnualReturn={bestAnnualReturn}
        bestSharpe={bestSharpe}
        summaryMetrics={heroSummaryMetrics}
        observabilitySummary={heroObservabilityMetrics}
        aiRecommendationPrompt={heroAiRecommendationPrompt}
        runFactoryPending={runFactoryApi.isPending}
        runFactoryError={runFactoryApi.error}
        aiGeneratePending={aiGenerateApi.isPending}
        aiGenerateError={aiGenerateApi.error}
        aiGenerateSummary={aiGenerateSummary}
        cartItemsCount={cartItems.length}
        showFactoryDetails={showFactoryDetails}
        canRunFactory={canRunFactory}
        canAiGenerate={canAiGenerate}
        canCreatePersonalStrategy={canCreatePersonalStrategy}
        onRunFactory={handleRunFactoryOperatorJob}
        onAiGenerate={() => {
          if (!window.confirm('确认提交 AI 生成策略任务？')) return;
          void aiGenerateApi.triggerAsync(
            '/strategy-market/operator/jobs',
            { method: 'POST' },
            {
              action: 'ai_generate',
              params: { limit: 3, auto_submit: false },
              confirmed: true,
              confirmation_text: 'ai_generate',
              reason: 'strategy_market_ai_generate',
              timeout_ms: 120000,
            },
          );
        }}
        onToggleCart={() => setShowCart((prev) => !prev)}
        onToggleFactoryDetails={() => setShowFactoryDetails((prev) => !prev)}
        onCreatePersonalStrategy={() => {
          void handleCreatePersonalStrategy();
        }}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection
          pageKey="strategy-market"
          title="策略工作台"
          result={strategyMarketResult}
          summaryMode="strip"
        />
      ) : null}

      {workspaceError ? (
        <PageStatusCard
          status="unavailable"
          title="当前工作区加载失败"
          reason={workspaceError}
          freshness={latestSnapshot?.snapshot_date ?? null}
          primaryAction={
            <button
              type="button"
              onClick={() => updateWorkspace('market')}
              className="action-chip cursor-pointer text-sm text-text-primary"
            >
              回到市场策略
            </button>
          }
          secondaryAction={
            <button
              type="button"
              onClick={() => {
                setCategory('all');
                setSearch('');
                setIncubationStageFilter('all');
              }}
              className="action-chip cursor-pointer text-sm text-text-primary"
            >
              清空筛选
            </button>
          }
          example="workspace=market，category=all，status=all"
          className="mt-4"
        />
      ) : null}

      {workspace !== 'factory' ? (
        <StrategyMarketCatalogSection
          category={category}
          setCategory={setCategory}
          search={search}
          setSearch={setSearch}
          showFeatured={showFeatured}
          setShowFeatured={setShowFeatured}
          sortBy={sortBy}
          setSortBy={setSortBy}
          sortDir={sortDir}
          toggleSortDir={() => setSortDir((value) => (value === 'desc' ? 'asc' : 'desc'))}
          strategies={strategies}
          activeCategoryLabel={activeCategoryLabel}
          showStatusFilters={workspace === 'market'}
          statusSegment={marketStatusSegment}
          setStatusSegment={setMarketStatusSegment}
          statusCounts={marketStatusCounts}
          statusLabel={marketStatusLabel}
          statusHelpText={marketStatusHelpText}
          incubationStageFilter={incubationStageFilter}
          setIncubationStageFilter={setIncubationStageFilter}
          catalogTotalCount={marketCatalogStrategies.length}
          featuredStrategies={featuredStrategies}
          onAddToCart={(strategy: Strategy) => {
            addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
            setShowCart(true);
          }}
          onRuntimeAction={handleRuntimeAction}
          showPersonalTestingBadge={workspace === 'mine'}
          showResults={!showEmptyStrategyState}
          emptyText={
            workspace === 'market'
              ? `当前“${marketStatusLabel} / ${incubationStageLabel}”筛选下暂无策略，请切换状态分层、孵化阶段或调整搜索条件。`
              : `当前“${incubationStageLabel}”筛选下暂无策略。`
          }
        />
      ) : null}

      {workspace === 'factory' ? (
        <div className="space-y-5">
          <StrategyMarketFactoryOverviewSection
            showEmptyStrategyState={false}
            snapshotDegraded={snapshotDegraded}
            factoryOverview={factoryOverview}
            snapshotCompletionRatio={snapshotCompletionRatio}
            snapshotFailureCount={snapshotFailureCount}
            failedRunsCount={failedRuns.length}
            visibleOutputs={visibleFactoryOutputs}
          />

          {canViewOperatorPanels ? (
            <StrategyMarketOperatorPanel
              enabled={canViewOperatorPanels}
              factoryStatus={factoryStatus}
              latestRun={factoryRuns[0] ?? null}
            />
          ) : null}

          <StrategyFactoryRawArtifactsPanel
            dailySnapshots={dailySnapshotsQ.data}
            latestTopn={latestTopnQ.data}
            runTopn={runTopnQ.data}
            dispatchStatus={dispatchStatusQ.data}
            expandedRunId={expandedRunId}
            lastDispatchId={lastDispatchId}
            isPending={dailySnapshotsQ.isPending || latestTopnQ.isPending || runTopnQ.isPending || dispatchStatusQ.isPending}
            errors={[dailySnapshotsQ.error, latestTopnQ.error, runTopnQ.error, dispatchStatusQ.error]}
          />

          <StrategyFactoryVectorGovernancePanel
            vectorHealth={vectorHealthQ.data}
            vectorIndexes={vectorIndexesQ.data}
            vectorSnapshots={vectorIndexSnapshotsFactoryQ.data}
            canViewOperatorPanels={canViewOperatorPanels}
            isPending={vectorHealthQ.isPending || vectorIndexesQ.isPending || vectorIndexSnapshotsFactoryQ.isPending}
            errors={[vectorHealthQ.error, vectorIndexesQ.error, vectorIndexSnapshotsFactoryQ.error]}
            onReconcile={handleVectorReconcile}
            onRebuild={handleVectorRebuild}
            onCleanupDryRun={handleVectorCleanupDryRun}
            reconcilePending={vectorReconcileApi.isPending}
            rebuildPending={vectorRebuildApi.isPending}
            cleanupPending={vectorCleanupApi.isPending}
          />

          <StrategyCapabilityGapPanel
            diagnostics={capabilityDiagnosticsQ.data}
            isPending={capabilityDiagnosticsQ.isPending}
            error={capabilityDiagnosticsQ.error}
          />

          {!showFactoryDetails ? (
            <SectionCard className="mt-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">Factory Details</div>
                  <h2 className="mt-2">工厂明细默认按需展开</h2>
                  <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                    联动观测、候选治理、retrain 队列和 run
                    细节都属于慢接口，默认收起以保证工厂工作区先可用；需要排查时再展开。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowFactoryDetails(true)}
                  className="action-chip cursor-pointer text-sm text-text-primary"
                >
                  展开工厂明细
                </button>
              </div>
            </SectionCard>
          ) : (
            <StrategyMarketObservabilitySection
              isPending={factoryMarketViewQ.isPending}
              error={factorySectionErrors.observability ?? null}
              schedulerStale={Boolean(factoryObservabilityOverview.scheduler_stale)}
              activeFactorCount={Number(factoryObservabilityOverview.active_factor_count ?? 0)}
              degraded={Boolean(factoryObservabilityRoot.degraded)}
              latestFactoryStatus={String(factoryObservabilityOverview.latest_factory_status ?? '-')}
              governedFactorCount={String(factoryObservabilityOverview.governed_factor_count ?? '-')}
              passedQualityGate={String(factoryObservabilityOverview.passed_quality_gate ?? '-')}
              championCount={String(factoryObservabilityOverview.champion_count ?? 0)}
              challengerCount={String(factoryObservabilityOverview.challenger_count ?? 0)}
              schedulerQualityStatus={String(factoryObservabilityOverview.scheduler_quality_status ?? '-')}
              recentGeneratedCandidateCount={String(
                factoryObservabilityOverview.recent_generated_candidate_count ?? '-',
              )}
              recentValidatedCandidateCount={String(
                factoryObservabilityOverview.recent_validated_candidate_count ?? '-',
              )}
              retrainPlanCount={String(factoryObservabilityOverview.retrain_plan_count ?? '-')}
              latestFactoryRunId={String(factoryObservabilityOverview.latest_factory_run_id ?? '-')}
              schedulerFreshnessSec={
                factoryObservabilityScheduler.freshness_sec == null
                  ? null
                  : Number(factoryObservabilityScheduler.freshness_sec)
              }
              blockedFactorCount={Number(factoryObservabilityOverview.blocked_factor_count ?? 0)}
              factoryRunsCount={extractArray(factoryObservabilityFactory, 'runs').length}
              recentGovernedActiveCountAfterRun={Number(
                factoryObservabilityOverview.recent_governed_active_count_after_run ?? 0,
              )}
              retrainPendingCount={Number(factoryObservabilityOverview.retrain_pending_count ?? 0)}
              errors={factoryObservabilityErrors}
              stageRows={factoryObservabilityStageRows}
              familyRows={factoryObservabilityFamilyRows}
              recentRunGeneratedCount={Number(factoryObservabilityRecentRun.generated_candidate_count ?? 0)}
              recentRunValidatedCount={Number(factoryObservabilityRecentRun.validated_candidate_count ?? 0)}
              recentRunGovernedCount={Number(factoryObservabilityRecentRun.governed_active_count_after_run ?? 0)}
              regimeRows={factoryObservabilityRegimeRows}
              retrainQueue={factoryObservabilityRetrainQueue as Array<Record<string, unknown>>}
              retrainStatusSummary={Object.entries(
                isRecord(factoryObservabilityRetrainSummary.status_counts)
                  ? factoryObservabilityRetrainSummary.status_counts
                  : {},
              )
                .map(([status, count]) => `${status}:${count}`)
                .join(' / ')}
            />
          )}
        </div>
      ) : null}

      {workspaceLoading ? (
        <LoadingState text={workspace === 'factory' ? '加载工厂运行态...' : '加载策略目录...'} />
      ) : null}
      {workspaceError ? <ErrorState text={workspaceError} /> : null}

      {showEmptyStrategyState ? (
        workspace === 'favorites' && !userId ? (
          <SectionCard className="mt-0 p-4 sm:p-5">
            <div className="eyebrow">Favorites Login</div>
            <h2 className="mt-2">登录后才能查看我的收藏</h2>
            <p className="mt-2 mb-0 text-sm leading-7 text-text-secondary">
              当前账号未登录，因此收藏列表为空。先登录，再把市场策略标记为收藏，后续才能在这里继续筛选和复制。
            </p>
          </SectionCard>
        ) : workspace === 'mine' && !userId ? (
          <SectionCard className="mt-0 p-4 sm:p-5">
            <div className="eyebrow">My Strategies Login</div>
            <h2 className="mt-2">登录后才能查看我的策略</h2>
            <p className="mt-2 mb-0 text-sm leading-7 text-text-secondary">
              个人策略和 AI 优化、模拟盘测试都依赖当前用户身份。请先登录，再创建或复制你的个人策略。
            </p>
          </SectionCard>
        ) : (
          <StrategyMarketEmptyStateSection
            runFactoryPending={runFactoryApi.isPending}
            onRunFactory={handleRunFactoryOperatorJob}
            onShowFactoryDetails={() => updateWorkspace('factory')}
          />
        )
      ) : null}

      {workspace === 'factory' && showFactoryDetails ? (
        <FactoryDashboard
          viewModel={factoryViewModel}
          capabilityBadges={capabilityBadges}
          capabilitiesError={factorySectionErrors.capabilities ?? null}
          dailySnapshotError={factorySectionErrors.snapshot ?? null}
          onRunFactory={handleRunFactoryOperatorJob}
          runFactoryPending={runFactoryApi.isPending}
          runFactoryError={runFactoryApi.error}
          factoryRunsLoading={Boolean(factoryMarketViewQ.isPending && factoryRuns.length === 0)}
          filteredRuns={filteredRuns}
          comparableRuns={comparableRuns}
          trendRuns={trendRuns}
          runStatusFilter={runStatusFilter}
          onRunStatusFilterChange={setRunStatusFilter}
          trendMetricKey={trendMetricKey}
          onTrendMetricKeyChange={setTrendMetricKey}
          expandedRunId={expandedRunId}
          onExpandedRunIdChange={setExpandedRunId}
          expandedRunLoading={Boolean(showFactoryDetails && expandedRunId && factoryMarketViewQ.isPending)}
          expandedRunError={factorySectionErrors.expanded_run ?? null}
        />
      ) : null}

      {showCart ? <CartDrawer onClose={() => setShowCart(false)} /> : null}
    </PageContainer>
  );
}
