'use client';

import { useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { PageContainer } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray } from '@/lib/data-utils';
import { apiKeys } from '@/lib/query-keys';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import { useCartStore } from '@/store/cart-store';
import type {
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunDetailResponse,
  FactoryRunsResponse,
  FactoryStatusResponse,
  RankingResponse,
  RunStatusFilter,
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
  isRecord,
  resolveCategoryLabel,
  type StrategySortKey,
} from './components/strategy-market-support';

export default function StrategyMarketPage() {
  const searchParams = useSearchParams();
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [showFactoryDetails, setShowFactoryDetails] = useState(false);
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const rankQ = useApiQuery<RankingResponse>(
    '/strategy-market/ranking?limit=50' + (category === 'all' ? '' : `&strategy_type=${category}`),
    {
      parse: (raw) => ensureRecordOrArray(raw, '策略榜单') as RankingResponse,
    },
  );
  const factoryStatusQ = useApiQuery<FactoryStatusResponse>('/strategy-market/factory/status');
  const capabilitiesQ = useApiQuery<CapabilityResponse>('/strategy-market/capabilities');
  const dailySnapshotQ = useApiQuery<DailySnapshotResponse>('/strategy-market/daily-snapshot');
  const factoryRunsQ = useApiQuery<FactoryRunsResponse>('/strategy-market/factory/runs?limit=5');
  const factoryObservabilityQ = useApiQuery<unknown>('/strategy-market/factory/observability', { staleTime: 15_000 });
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [runStatusFilter, setRunStatusFilter] = useState<RunStatusFilter>('all');
  const [trendMetricKey, setTrendMetricKey] = useState<TrendMetricKey>('candidates_spawned');
  const factoryRunDetailQ = useApiQuery<FactoryRunDetailResponse>(
    expandedRunId ? `/strategy-market/factory/runs/${encodeURIComponent(expandedRunId)}` : null,
  );
  const runFactoryApi = useApiMutation({
    invalidates: [apiKeys.strategy()],
    successToast: '策略工厂已完成一次运行',
  });
  const addToCart = useCartStore((state) => state.addStrategy);
  const cartItems = useCartStore((state) => state.items);
  const [showCart, setShowCart] = useState(false);
  const [showFeatured, setShowFeatured] = useState(false);
  const [sortBy, setSortBy] = useState<StrategySortKey>('totalReturn');
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc');

  const strategies = useMemo(
    () => filterAndSortStrategies(rankQ.data, search, sortBy, sortDir),
    [rankQ.data, search, sortBy, sortDir],
  );

  const factorySummary = useMemo(() => factoryStatusQ.data?.last_summary ?? {}, [factoryStatusQ.data]);
  const factoryCapabilities = useMemo(() => capabilitiesQ.data ?? {}, [capabilitiesQ.data]);
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

  const showEmptyStrategyState = !rankQ.isPending && strategies.length === 0 && !rankQ.error;
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
    () => extractArray(factoryObservabilityActivePool, 'regime_summary'),
    [factoryObservabilityActivePool],
  );
  const factoryObservabilityStageRows = useMemo(
    () => countRows(factoryObservabilityRegistrySummary.registry_stage_counts, 'registry_stage'),
    [factoryObservabilityRegistrySummary],
  );
  const expandedRun = useMemo(() => {
    if (!expandedRunId) return null;
    const detail = factoryRunDetailQ.data;
    if (detail?.run_id === expandedRunId) return detail;
    return null;
  }, [factoryRunDetailQ.data, expandedRunId]);

  return (
    <PageContainer className="space-y-5">
      <StrategyMarketHeroSection
        from={from}
        task={task}
        capabilityBadges={capabilityBadges}
        strategyCount={strategies.length}
        enabledCapabilityCount={enabledCapabilityCount}
        bestAnnualReturn={bestAnnualReturn}
        bestSharpe={bestSharpe}
        runFactoryPending={runFactoryApi.isPending}
        runFactoryError={runFactoryApi.error}
        cartItemsCount={cartItems.length}
        showFactoryDetails={showFactoryDetails}
        onRunFactory={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
        onToggleCart={() => setShowCart((prev) => !prev)}
        onToggleFactoryDetails={() => setShowFactoryDetails((prev) => !prev)}
      />

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
        featuredStrategies={featuredStrategies}
        onAddToCart={(strategy) => addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 })}
        showResults={!showEmptyStrategyState}
      />

      <StrategyMarketFactoryOverviewSection
        showEmptyStrategyState={showEmptyStrategyState}
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

      {rankQ.isPending ? <LoadingState text="加载策略列表..." /> : null}
      {rankQ.error ? <ErrorState text={rankQ.error} /> : null}

      {showEmptyStrategyState ? (
        <StrategyMarketEmptyStateSection
          runFactoryPending={runFactoryApi.isPending}
          onRunFactory={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
          onShowFactoryDetails={() => setShowFactoryDetails(true)}
        />
      ) : null}

      {showFactoryDetails ? (
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
