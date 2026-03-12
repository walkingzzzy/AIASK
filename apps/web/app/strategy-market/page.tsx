'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { StrategyCard } from '@/components/strategy-card';
import { useCartStore } from '@/store/cart-store';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { apiKeys } from '@/lib/query-keys';
import type {
  RankingResponse,
  FactoryStatusResponse,
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunsResponse,
  FactoryRunDetailResponse,
  Strategy,
  RunStatusFilter,
  TrendMetricKey,
} from './types';
import { FactoryDashboard } from './components/FactoryDashboard';
import { CartDrawer } from './components/CartDrawer';

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'momentum', label: '动量' },
  { key: 'value', label: '价值' },
  { key: 'quality', label: '质量' },
  { key: 'multi_factor', label: '多因子' },
  { key: 'macro', label: '宏观' },
] as const;

export default function StrategyMarketPage() {
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const rankQ = useApiQuery<RankingResponse>(
    '/strategy-market/ranking?limit=50' + (category === 'all' ? '' : '&strategy_type=' + category),
    {
      parse: (raw) => ensureRecordOrArray(raw, '策略榜单') as RankingResponse,
    },
  );
  const factoryStatusQ = useApiQuery<FactoryStatusResponse>('/strategy-market/factory/status');
  const capabilitiesQ = useApiQuery<CapabilityResponse>('/strategy-market/capabilities');
  const dailySnapshotQ = useApiQuery<DailySnapshotResponse>('/strategy-market/daily-snapshot');
  const factoryRunsQ = useApiQuery<FactoryRunsResponse>('/strategy-market/factory/runs?limit=5');
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
  const addToCart = useCartStore((s) => s.addStrategy);
  const cartItems = useCartStore((s) => s.items);

  /* ---------- derived data ---------- */

  const strategies = useMemo(() => {
    const d = rankQ.data;
    const raw = Array.isArray(d) ? d : (d as Record<string, unknown>)?.strategies ?? d ?? [];
    const list = Array.isArray(raw) ? raw as Strategy[] : [];
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter((s) =>
      s.name.toLowerCase().includes(q) ||
      (s.description ?? '').toLowerCase().includes(q) ||
      (s.strategy_type ?? '').toLowerCase().includes(q),
    );
  }, [rankQ.data, search]);

  const factorySummary = useMemo(() => {
    const raw = factoryStatusQ.data;
    return raw?.last_summary ?? {};
  }, [factoryStatusQ.data]);
  const factoryCapabilities = capabilitiesQ.data ?? {};
  const latestSnapshot = dailySnapshotQ.data ?? null;
  const snapshotCompletionRatio = factorySummary.snapshot_completion_ratio ?? latestSnapshot?.completeness?.completion_ratio;
  const snapshotFailureCount = factorySummary.snapshot_failure_reason_count ?? latestSnapshot?.failure_reasons?.length ?? 0;
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

  const [showCart, setShowCart] = useState(false);

  const expandedRun = useMemo(() => {
    if (!expandedRunId) return null;
    const detail = factoryRunDetailQ.data;
    if (detail?.run_id === expandedRunId) return detail;
    return null;
  }, [factoryRunDetailQ.data, expandedRunId]);

  /* ---------- render ---------- */

  return (
    <PageContainer>
      <div className="flex items-center justify-between">
        <h1>策略超市</h1>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索策略名称..."
            className="px-2 py-1 border border-border rounded text-sm w-45"
          />
          <button
            onClick={() => setShowCart(!showCart)}
            className="relative px-3 py-1 text-sm rounded border border-border cursor-pointer hover:bg-surface-alt"
          >
            组合购物车
            {cartItems.length > 0 && (
              <span className="absolute -top-1.5 -right-1.5 bg-primary text-white text-[10px] w-4 h-4 rounded-full flex items-center justify-center">
                {cartItems.length}
              </span>
            )}
          </button>
        </div>
      </div>

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

      <TabBar tabs={CATEGORIES} active={category} onChange={(c) => { setCategory(c); setSearch(''); }} />

      {rankQ.isPending && <LoadingState text="加载策略列表..." />}
      {rankQ.error && <ErrorState text={rankQ.error} />}

      {strategies.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mt-4">
          {strategies.map((s) => (
            <StrategyCard
              key={s.id}
              s={s}
              onAdd={(st) => addToCart({ strategyId: st.id, name: st.name, weight: 0 })}
            />
          ))}
        </div>
      )}

      {!rankQ.isPending && strategies.length === 0 && !rankQ.error && (
        <SectionCard className="mt-4 p-6 text-center text-text-secondary">
          暂无已发布的策略
        </SectionCard>
      )}

      {showCart && <CartDrawer onClose={() => setShowCart(false)} />}
    </PageContainer>
  );
}
