'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useOnboarding } from '@/components/onboarding';
import ResultWorkbench from '@/components/result-workbench';
import { ErrorState, LoadingState } from '@/components/status-state';
import { Badge, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { extractArray } from '@/lib/data-utils';
import { apiKeys } from '@/lib/query-keys';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import { useAuthStore } from '@/store/auth-store';
import { useCartStore } from '@/store/cart-store';
import type {
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunDetailResponse,
  FactoryRunsResponse,
  FactoryStatusResponse,
  RankingResponse,
  RunStatusFilter,
  Strategy,
  TrendMetricKey,
} from './types';
import { CartDrawer } from './components/CartDrawer';
import { FactoryDashboard } from './components/FactoryDashboard';
import { StrategyMarketCatalogSection } from './components/StrategyMarketCatalogSection';
import {
  StrategyMarketEmptyStateSection,
  StrategyMarketFactoryOverviewSection,
  StrategyMarketObservabilitySection,
} from './components/StrategyMarketFactorySections';
import { StrategyMarketHeroSection } from './components/StrategyMarketHeroSection';
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
import {
  parseFactoryRunDetailResponse,
  parseFactoryRunsResponse,
  parseFactoryStatusResponse,
} from './lib/contracts';

const RANKING_PAGE_LIMIT = 200;
type StrategyWorkspace = 'market' | 'favorites' | 'mine' | 'factory';

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
  const generation = isRecord(raw.generation) ? raw.generation : {};
  const submission = isRecord(raw.submission) ? raw.submission : {};
  const generatedCount = Number(raw.generated_count ?? generation.count ?? Number.NaN);
  const reviewedCount = Number(raw.reviewed_count ?? raw.reviewed ?? Number.NaN);
  const submittedCount = Number(
    raw.submitted_count
      ?? submission.submitted_count
      ?? raw.submitted
      ?? Number.NaN,
  );
  const traceId = String(
    (isRecord(raw.task_run) ? raw.task_run.trace_id : raw.trace_id) ?? '',
  ).trim();
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
  const searchParams = useStableSearchParams();
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? user?.username ?? null;
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
  const [showFactoryDetails, setShowFactoryDetails] = useState(
    workspace === 'factory' || shouldOpenFactoryFromTask(task),
  );
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [runStatusFilter, setRunStatusFilter] = useState<RunStatusFilter>('all');
  const [trendMetricKey, setTrendMetricKey] = useState<TrendMetricKey>('candidates_spawned');
  const [showCart, setShowCart] = useState(false);
  const [showFeatured, setShowFeatured] = useState(false);
  const [sortBy, setSortBy] = useState<StrategySortKey>('totalReturn');
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc');

  const rankQ = useApiQuery<RankingResponse>(
    `/strategy-market/ranking?limit=${RANKING_PAGE_LIMIT}&status=all` +
      (category === 'all' ? '' : `&strategy_type=${category}`),
    {
      critical: true,
      parse: (raw) => ensureRecordOrArray(raw, '策略榜单') as RankingResponse,
    },
  );
  const factoryStatusQ = useApiQuery<FactoryStatusResponse>(
    '/strategy-market/factory/status',
    { parse: parseFactoryStatusResponse, critical: true },
  );
  const capabilitiesQ = useApiQuery<CapabilityResponse>('/strategy-market/capabilities', { critical: true });
  const favoritesQ = useApiQuery<RankingResponse>(
    userId ? '/strategy-market/my-favorites' : null,
    {
      enabled: Boolean(userId),
      parse: (raw) => ensureRecordOrArray(raw, '我的收藏') as RankingResponse,
    },
  );
  const myStrategiesQ = useApiQuery<RankingResponse>(
    userId ? '/strategy-market/my-strategies?limit=50' : null,
    {
      enabled: Boolean(userId),
      parse: (raw) => ensureRecordOrArray(raw, '我的策略') as RankingResponse,
    },
  );
  const dailySnapshotQ = useApiQuery<DailySnapshotResponse>('/strategy-market/daily-snapshot', { critical: true });
  const factoryRunsQ = useApiQuery<FactoryRunsResponse>(
    '/strategy-market/factory/runs?limit=5',
    { parse: parseFactoryRunsResponse, critical: true },
  );
  const factoryObservabilityQ = useApiQuery<unknown>(
    '/strategy-market/factory/observability',
    { staleTime: 15_000, critical: true },
  );
  const factoryRunDetailQ = useApiQuery<FactoryRunDetailResponse>(
    expandedRunId ? `/strategy-market/factory/runs/${encodeURIComponent(expandedRunId)}` : null,
    { parse: parseFactoryRunDetailResponse, critical: true },
  );

  const runFactoryApi = useApiMutation({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '策略工厂请求已受理，结果会稍后同步到运行态面板',
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
  const marketStatusCounts = useMemo(
    () => getStrategyStatusCounts(marketStrategiesAll),
    [marketStrategiesAll],
  );
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
  const workspaceStrategies = workspace === 'favorites'
    ? favoriteStrategies
    : workspace === 'mine'
      ? myStrategies
      : marketStrategies;
  const strategies = useMemo(
    () => workspaceStrategies.filter((strategy) => matchesIncubationStageFilter(strategy, incubationStageFilter)),
    [incubationStageFilter, workspaceStrategies],
  );
  const marketStatusLabel = useMemo(
    () => resolveStatusSegmentLabel(marketStatusSegment),
    [marketStatusSegment],
  );
  const marketStatusHelpText = useMemo(
    () => resolveStatusSegmentHelpText(marketStatusSegment),
    [marketStatusSegment],
  );
  const incubationStageLabel = useMemo(
    () => resolveIncubationStageFilterLabel(incubationStageFilter),
    [incubationStageFilter],
  );

  const factorySummary = useMemo(() => factoryStatusQ.data?.last_summary ?? {}, [factoryStatusQ.data]);
  const factoryCapabilities = useMemo(() => capabilitiesQ.data ?? {}, [capabilitiesQ.data]);
  const actorPermissions = useMemo(
    () => capabilitiesQ.data?.actor_permissions ?? {},
    [capabilitiesQ.data],
  );
  const canRunFactory = Boolean(actorPermissions.can_run_factory);
  const canAiGenerate = Boolean(actorPermissions.can_ai_generate);
  const canCreatePersonalStrategy = Boolean(actorPermissions.can_create_personal_strategy && userId);
  const canViewOperatorPanels = Boolean(actorPermissions.can_view_operator_panels);
  const aiGenerateSummary = useMemo(
    () => (aiGenerateApi.data ? summarizeAiGenerateResult(aiGenerateApi.data) : null),
    [aiGenerateApi.data],
  );

  const latestSnapshot = dailySnapshotQ.data ?? null;
  const snapshotCompletionRatio =
    factorySummary.snapshot_completion_ratio ?? latestSnapshot?.completeness?.completion_ratio;
  const snapshotFailureCount =
    factorySummary.snapshot_failure_reason_count ?? latestSnapshot?.failure_reasons?.length ?? 0;
  const snapshotDegraded = factorySummary.snapshot_degraded ?? latestSnapshot?.degraded ?? false;

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
      { key: 'research_protocol_v2', label: '研究协议V2', enabled: factoryCapabilities.research_protocol_v2_enabled ?? false },
      { key: 'gate_model_v2', label: '门禁模型V2', enabled: factoryCapabilities.gate_model_v2_enabled ?? false },
      { key: 'trace_ledger_v2', label: '追踪账本V2', enabled: factoryCapabilities.trace_ledger_v2_enabled ?? false },
      { key: 'feedback_v2', label: '反馈闭环V2', enabled: factoryCapabilities.feedback_v2_enabled ?? false },
    ],
    [factoryCapabilities],
  );

  const factoryRuns = useMemo(() => factoryRunsQ.data?.items ?? [], [factoryRunsQ.data]);
  const failedRuns = useMemo(() => factoryRuns.filter((item) => item.status === 'failed'), [factoryRuns]);
  const filteredRuns = useMemo(() => {
    if (runStatusFilter === 'all') return factoryRuns;
    return factoryRuns.filter((item) => item.status === runStatusFilter);
  }, [factoryRuns, runStatusFilter]);
  const comparableRuns = useMemo(() => filteredRuns.slice(0, 5), [filteredRuns]);
  const trendRuns = useMemo(() => [...comparableRuns].reverse(), [comparableRuns]);

  const workspaceLoading = workspace === 'factory'
    ? factoryStatusQ.isPending || factoryRunsQ.isPending
    : workspace === 'favorites'
      ? favoritesQ.isPending
      : workspace === 'mine'
        ? myStrategiesQ.isPending
        : rankQ.isPending;
  const workspaceError = workspace === 'factory'
    ? (factoryStatusQ.error ?? factoryRunsQ.error)
    : workspace === 'favorites'
      ? favoritesQ.error
      : workspace === 'mine'
        ? myStrategiesQ.error
        : rankQ.error;
  const showEmptyStrategyState = workspace !== 'factory'
    && !workspaceLoading
    && !workspaceError
    && (
      workspace === 'market'
        ? category === 'all' && !search.trim() && marketCatalogStrategies.length === 0
        : strategies.length === 0
    );
  const featuredStrategies = useMemo(() => strategies.slice(0, 3), [strategies]);

  const factoryOverview = useMemo(
    () => [
      { label: '调度状态', value: factoryStatusQ.data?.running ? '运行中' : '待命' },
      { label: '候选生成', value: String(factorySummary.candidates_spawned ?? 0) },
      { label: '质检通过', value: String(factorySummary.passed_quality_gate ?? 0) },
      { label: '最新快照', value: latestSnapshot?.snapshot_date ?? '暂无' },
    ],
    [
      factoryStatusQ.data?.running,
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
    () => (isRecord(factoryObservabilityQ.data) ? factoryObservabilityQ.data : {}),
    [factoryObservabilityQ.data],
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
  const factoryObservabilityErrors = useMemo(
    () => (Array.isArray(factoryObservabilityRoot.errors) ? factoryObservabilityRoot.errors : []),
    [factoryObservabilityRoot],
  );
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
  const workspaceLabel = workspace === 'favorites'
    ? '我的收藏'
    : workspace === 'mine'
      ? '我的策略'
      : workspace === 'factory'
        ? '工厂运行态'
        : '市场策略';
  const workspaceSummary = workspace === 'favorites'
    ? `只保留你已经收藏的策略，方便继续比较、复制为个人版本或加入组合。当前孵化阶段筛选为“${incubationStageLabel}”。`
    : workspace === 'mine'
      ? `这里集中管理你的个人策略草稿与个人版本，优先做编辑、AI 优化和模拟盘测试。当前孵化阶段筛选为“${incubationStageLabel}”。`
      : workspace === 'factory'
        ? '工厂运行、快照、可观测性与最近 run 集中在这里，不再和市场榜单混排。'
        : `市场目录按生命周期分层展示，当前处于“${marketStatusLabel}”分层，孵化阶段筛选为“${incubationStageLabel}”。${marketStatusHelpText}`;
  const workspaceCountLabel = workspace === 'favorites'
    ? '已收藏策略'
    : workspace === 'mine'
      ? '个人策略'
      : workspace === 'factory'
        ? '最近工厂运行'
        : `${marketStatusLabel}策略`;

  const expandedRun = useMemo(() => {
    if (!expandedRunId) return null;
    const detail = factoryRunDetailQ.data;
    if (detail?.run_id === expandedRunId) return detail;
    return null;
  }, [factoryRunDetailQ.data, expandedRunId]);

  const updateWorkspace = useCallback((next: StrategyWorkspace) => {
    const qs = new URLSearchParams(searchParams.toString());
    if (next === 'market') {
      qs.delete('workspace');
    } else {
      qs.set('workspace', next);
    }
    const nextHref = qs.toString() ? `/strategy-market?${qs.toString()}` : '/strategy-market';
    router.push(nextHref);
  }, [router, searchParams]);

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
    const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    const strategyRecord = record.strategy && typeof record.strategy === 'object'
      ? record.strategy as Record<string, unknown>
      : null;
    const nextId = String(record.strategy_id ?? strategyRecord?.id ?? '').trim();
    if (nextId) {
      router.push(`/strategy-market/${encodeURIComponent(nextId)}`);
    }
  }, [category, createPersonalStrategyApi, router, userId]);

  useEffect(() => {
    if (category !== 'all' || search.trim() || showFactoryDetails || showFeatured || cartItems.length > 0) {
      completeStep('strategy-market');
    }
  }, [cartItems.length, category, completeStep, search, showFactoryDetails, showFeatured]);

  const pageActions = useMemo(
    () => [
      {
        id: 'strategy-market.switch-market',
        label: '切到市场策略',
        description: '查看市场榜单和可见策略目录',
        keywords: ['市场策略', '榜单'],
        scope: 'page' as const,
        pageKey: 'strategy-market',
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
        ? [{
            id: 'strategy-market.create-personal',
            label: '新建个人策略',
            description: '创建一条新的个人策略草稿',
            keywords: ['新建', '个人策略'],
            scope: 'page' as const,
            pageKey: 'strategy-market',
            run: async () => {
              await handleCreatePersonalStrategy();
              return { message: '已创建新的个人策略草稿' };
            },
          }]
        : []),
      ...(canAiGenerate
        ? [{
            id: 'strategy-market.ai-generate',
            label: 'AI 生成策略',
            description: '调用策略工厂的 AI 生成入口创建候选策略',
            keywords: ['AI生成', '策略工厂'],
            scope: 'page' as const,
            pageKey: 'strategy-market',
            run: async () => {
              await aiGenerateApi.triggerAsync(
                '/strategy-market/ai/generate',
                { method: 'POST' },
                { limit: 3, auto_submit: false },
              );
              return { message: '已触发 AI 策略生成，请到工厂运行态查看结果' };
            },
          }]
        : []),
    ],
    [
      aiGenerateApi,
      canAiGenerate,
      canCreatePersonalStrategy,
      featuredStrategies,
      handleCreatePersonalStrategy,
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
      workspace,
    ],
  );

  usePageActions(pageActions);
  const strategyMarketSummary = workspace === 'market'
    ? `${workspaceLabel} 当前分层 ${marketStatusLabel}，孵化阶段 ${incubationStageLabel}，共 ${strategies.length} 条，目录总量 ${marketCatalogStrategies.length} 条，分类 ${activeCategoryLabel}，搜索词 ${search.trim() || '无'}，${showFeatured ? '仅看精选' : '展示全部'}。`
    : `${workspaceLabel} 当前孵化阶段 ${incubationStageLabel}，可见 ${strategies.length} 条，分类 ${activeCategoryLabel}，搜索词 ${search.trim() || '无'}，${showFeatured ? '仅看精选' : '展示全部'}。`;
  const strategyMarketEvidence = [
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
    ...(snapshotDegraded ? ['当前工厂快照处于降级态，运行指标需要二次核对。'] : []),
    ...((workspace === 'factory' && failedRuns.length > 0) ? [`最近运行中有 ${failedRuns.length} 个失败 run。`] : []),
  ];
  const strategyMarketResult = buildLocalResultContract({
    summary: strategyMarketSummary,
    availableViews: strategies.length > 1 || factoryRuns.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['strategy-market.refresh', 'strategy-market.toggle-factory', 'strategy-market.open-workspace', 'strategy-market.open-cart'],
    recommendedLinks: strategyMarketLinks,
    evidence: strategyMarketEvidence,
    riskNotes: strategyMarketRiskNotes,
    freshness: dailySnapshotQ.data?.snapshot_date ? { asOf: dailySnapshotQ.data.snapshot_date, label: '策略快照' } : null,
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
    objectType: workspace === 'factory' ? 'strategy' : 'strategy-list',
    objectId: workspace === 'factory' ? 'factory-runtime' : `${workspace}:${category}:${search.trim() || 'all'}`,
    resultType: workspace === 'factory' ? 'strategy-factory-runtime' : 'strategy-catalog',
    tags: [
      `${workspaceLabel} ${strategies.length} 条`,
      ...(workspace === 'market' ? [`状态分层 ${marketStatusLabel}`, `目录总量 ${marketCatalogStrategies.length} 条`] : []),
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
    recommendedActions: strategyMarketResult.recommendedActions ?? [],
    recommendedLinks: strategyMarketResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(strategyMarketResult.evidence),
    riskNotes: strategyMarketResult.riskNotes ?? [],
    freshness: strategyMarketResult.freshness ?? null,
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
      canAiGenerate,
      canCreatePersonalStrategy,
      aiGenerateSummary,
      entryQuery: entryQuery ?? null,
      entryCategory: entryCategory ?? null,
    },
  });

  return (
    <PageContainer className="space-y-5">
      <SectionCard className="mt-0">
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
            {workspace === 'market' ? <Badge variant="neutral">目录总量 {marketCatalogStrategies.length}</Badge> : null}
            {userId ? <Badge variant="neutral">当前用户 {userId}</Badge> : <Badge variant="warning">未登录</Badge>}
            {canViewOperatorPanels ? <Badge variant="success">可看运营面板</Badge> : <Badge variant="neutral">用户视图</Badge>}
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
        onRunFactory={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
        onAiGenerate={() => {
          void aiGenerateApi.triggerAsync('/strategy-market/ai/generate', { method: 'POST' }, { limit: 3, auto_submit: false });
        }}
        onToggleCart={() => setShowCart((prev) => !prev)}
        onToggleFactoryDetails={() => setShowFactoryDetails((prev) => !prev)}
        onCreatePersonalStrategy={() => {
          void handleCreatePersonalStrategy();
        }}
      />

      <ResultWorkbench pageKey="strategy-market" title="策略工作台" result={strategyMarketResult} />

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
          />

          <StrategyMarketObservabilitySection
            isPending={factoryObservabilityQ.isPending}
            error={factoryObservabilityQ.error}
            schedulerStale={Boolean(factoryObservabilityOverview.scheduler_stale)}
            activeFactorCount={Number(factoryObservabilityOverview.active_factor_count ?? 0)}
            degraded={Boolean(factoryObservabilityRoot.degraded)}
            latestFactoryStatus={String(factoryObservabilityOverview.latest_factory_status ?? '-')}
            governedFactorCount={String(factoryObservabilityOverview.governed_factor_count ?? '-')}
            passedQualityGate={String(factoryObservabilityOverview.passed_quality_gate ?? '-')}
            championCount={String(factoryObservabilityOverview.champion_count ?? 0)}
            challengerCount={String(factoryObservabilityOverview.challenger_count ?? 0)}
            schedulerQualityStatus={String(factoryObservabilityOverview.scheduler_quality_status ?? '-')}
            recentGeneratedCandidateCount={String(factoryObservabilityOverview.recent_generated_candidate_count ?? '-')}
            recentValidatedCandidateCount={String(factoryObservabilityOverview.recent_validated_candidate_count ?? '-')}
            retrainPlanCount={String(factoryObservabilityOverview.retrain_plan_count ?? '-')}
            latestFactoryRunId={String(factoryObservabilityOverview.latest_factory_run_id ?? '-')}
            schedulerFreshnessSec={
              factoryObservabilityScheduler.freshness_sec == null ? null : Number(factoryObservabilityScheduler.freshness_sec)
            }
            blockedFactorCount={Number(factoryObservabilityOverview.blocked_factor_count ?? 0)}
            factoryRunsCount={extractArray(factoryObservabilityFactory, 'runs').length}
            recentGovernedActiveCountAfterRun={Number(factoryObservabilityOverview.recent_governed_active_count_after_run ?? 0)}
            retrainPendingCount={Number(factoryObservabilityOverview.retrain_pending_count ?? 0)}
            errors={factoryObservabilityErrors}
            stageRows={factoryObservabilityStageRows}
            familyRows={factoryObservabilityFamilyRows}
            recentRunGeneratedCount={Number(factoryObservabilityRecentRun.generated_candidate_count ?? 0)}
            recentRunValidatedCount={Number(factoryObservabilityRecentRun.validated_candidate_count ?? 0)}
            recentRunGovernedCount={Number(factoryObservabilityRecentRun.governed_active_count_after_run ?? 0)}
            regimeRows={factoryObservabilityRegimeRows}
            retrainQueue={factoryObservabilityRetrainQueue as Array<Record<string, unknown>>}
            retrainStatusSummary={
              Object.entries(
                isRecord(factoryObservabilityRetrainSummary.status_counts)
                  ? factoryObservabilityRetrainSummary.status_counts
                  : {},
              )
                .map(([status, count]) => `${status}:${count}`)
                .join(' / ')
            }
          />
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
            onRunFactory={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
            onShowFactoryDetails={() => updateWorkspace('factory')}
          />
        )
      ) : null}

      {workspace === 'factory' && showFactoryDetails ? (
        <FactoryDashboard
          factoryStatus={factoryStatusQ.data}
          latestSnapshot={latestSnapshot}
          capabilityBadges={capabilityBadges}
          capabilitiesError={capabilitiesQ.error}
          dailySnapshotError={dailySnapshotQ.error}
          factorySummary={factorySummary}
          snapshotCompletionRatio={snapshotCompletionRatio}
          snapshotDegraded={snapshotDegraded}
          snapshotFailureCount={snapshotFailureCount}
          onRunFactory={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
          runFactoryPending={runFactoryApi.isPending}
          runFactoryError={runFactoryApi.error}
          factoryRunsLoading={factoryRunsQ.isPending}
          factoryRuns={factoryRuns}
          filteredRuns={filteredRuns}
          failedRuns={failedRuns}
          comparableRuns={comparableRuns}
          trendRuns={trendRuns}
          runStatusFilter={runStatusFilter}
          onRunStatusFilterChange={setRunStatusFilter}
          trendMetricKey={trendMetricKey}
          onTrendMetricKeyChange={setTrendMetricKey}
          expandedRunId={expandedRunId}
          onExpandedRunIdChange={setExpandedRunId}
          expandedRun={expandedRun}
          expandedRunLoading={factoryRunDetailQ.isPending}
          expandedRunError={factoryRunDetailQ.error}
        />
      ) : null}

      {showCart ? <CartDrawer onClose={() => setShowCart(false)} /> : null}
    </PageContainer>
  );
}
