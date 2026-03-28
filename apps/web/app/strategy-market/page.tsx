'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Badge, DataTable, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { AskAiButton } from '@/components/ask-ai-button';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { StrategyCard } from '@/components/strategy-card';
import { useCartStore } from '@/store/cart-store';
import { extractArray, fmtPct, fmtNum } from '@/lib/data-utils';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { apiKeys } from '@/lib/query-keys';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
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

const STRATEGY_TYPE_LABELS: Record<string, string> = {
  momentum: '动量',
  value: '价值',
  quality: '质量',
  quality_factor: '质量',
  multi_factor: '多因子',
  macro: '宏观',
  ma_cross: '均线',
  dsl_rule: 'DSL',
};

function resolveCategoryLabel(key?: string | null) {
  const type = String(key ?? 'all');
  if (STRATEGY_TYPE_LABELS[type]) return STRATEGY_TYPE_LABELS[type];
  return CATEGORIES.find((item) => item.key === type)?.label ?? type;
}

export default function StrategyMarketPage() {
  const searchParams = useSearchParams();
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [showFactoryDetails, setShowFactoryDetails] = useState(false);
  const task = searchParams.get('task');
  const from = searchParams.get('from');
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
  const [showCart, setShowCart] = useState(false);
  const [showFeatured, setShowFeatured] = useState(false);
  type SortKey = 'totalReturn' | 'sharpe' | 'maxDrawdown' | 'subscriber_count';
  const [sortBy, setSortBy] = useState<SortKey>('totalReturn');
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc');

  /* ---------- derived data ---------- */

  const strategies = useMemo(() => {
    const list = extractArray(rankQ.data, 'strategies', 'items', 'data') as Strategy[];
    let filtered = list;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      filtered = list.filter((s) =>
        s.name.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q) ||
        (s.strategy_type ?? '').toLowerCase().includes(q),
      );
    }
    return [...filtered].sort((a, b) => {
      const ma = getStrategyMetricSnapshot(a);
      const mb = getStrategyMetricSnapshot(b);
      let va: number;
      let vb: number;
      if (sortBy === 'subscriber_count') {
        va = Number(a.subscriber_count ?? 0);
        vb = Number(b.subscriber_count ?? 0);
      } else {
        va = Number(ma[sortBy] ?? Number.NEGATIVE_INFINITY);
        vb = Number(mb[sortBy] ?? Number.NEGATIVE_INFINITY);
      }
      return sortDir === 'desc' ? vb - va : va - vb;
    });
  }, [rankQ.data, search, sortBy, sortDir]);

  const factorySummary = useMemo(() => {
    const raw = factoryStatusQ.data;
    return raw?.last_summary ?? {};
  }, [factoryStatusQ.data]);
  const factoryCapabilities = useMemo(
    () => capabilitiesQ.data ?? {},
    [capabilitiesQ.data],
  );
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

  const showEmptyStrategyState = !rankQ.isPending && strategies.length === 0 && !rankQ.error;
  const featuredStrategies = useMemo(() => strategies.slice(0, 3), [strategies]);
  const factoryOverview = useMemo(
    () => [
      { label: '调度状态', value: factoryStatusQ.data?.running ? '运行中' : '待命' },
      { label: '候选生成', value: String(factorySummary.candidates_spawned ?? 0) },
      { label: '质检通过', value: String(factorySummary.passed_quality_gate ?? 0) },
      { label: '最新快照', value: latestSnapshot?.snapshot_date ?? '暂无' },
    ],
    [factoryStatusQ.data?.running, factorySummary.candidates_spawned, factorySummary.passed_quality_gate, latestSnapshot?.snapshot_date],
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

  const strategyColumns = useMemo(() => [
    {
      key: 'name',
      label: '策略',
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        return (
          <div className="min-w-[200px]">
            <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
              <div className="font-semibold text-text-primary">{strategy.name}</div>
              <div className="mt-1 text-xs text-text-secondary">{strategy.description || strategy.strategy_type || '暂无描述'}</div>
            </Link>
          </div>
        );
      },
    },
    {
      key: 'strategy_type',
      label: '类型',
      render: (value: unknown) => {
        const type = String(value ?? '其他');
        const label = resolveCategoryLabel(type);
        const variant = type === 'momentum' || type === 'ma_cross'
          ? 'info'
          : type === 'value'
            ? 'success'
            : type === 'quality' || type === 'quality_factor'
              ? 'warning'
              : 'neutral';
        return <Badge variant={variant}>{label}</Badge>;
      },
    },
    {
      key: 'annual_return',
      label: '年化收益',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => {
        const value = Number(getStrategyMetricSnapshot(row as Strategy).totalReturn ?? 0);
        return <span className={value >= 0 ? 'text-success font-medium' : 'text-danger font-medium'}>{fmtPct(value)}</span>;
      },
    },
    {
      key: 'sharpe_ratio',
      label: 'Sharpe',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => fmtNum(getStrategyMetricSnapshot(row as Strategy).sharpe ?? 0, 2),
    },
    {
      key: 'max_drawdown',
      label: '最大回撤',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => <span className="text-danger font-medium">{fmtPct(getStrategyMetricSnapshot(row as Strategy).maxDrawdown ?? 0)}</span>,
    },
    {
      key: 'subscriber_count',
      label: '订阅',
      align: 'right' as const,
      render: (value: unknown) => String(value ?? 0),
    },
    {
      key: '_actions',
      label: '操作',
      sortable: false,
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        return (
          <div className="flex justify-end gap-2">
            <Link href={`/strategy-market/${strategy.id}`} className="rounded-full border border-border bg-surface px-3 py-1 text-xs no-underline text-text-secondary">
              详情
            </Link>
            <button
              type="button"
              onClick={() => addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 })}
              className="rounded-full bg-primary px-3 py-1 text-xs text-white shadow-sm"
            >
              加入组合
            </button>
          </div>
        );
      },
    },
  ], [addToCart]);

  const expandedRun = useMemo(() => {
    if (!expandedRunId) return null;
    const detail = factoryRunDetailQ.data;
    if (detail?.run_id === expandedRunId) return detail;
    return null;
  }, [factoryRunDetailQ.data, expandedRunId]);

  /* ---------- render ---------- */

  return (
    <PageContainer className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.18fr)_360px]">
        <div className="rounded-[28px] border border-border bg-surface p-6 shadow-sm">
          <div className="eyebrow">Strategy Workspace</div>
          <h1 className="mt-3">先看筛选结果，再决定订阅、组合和工厂动作。</h1>
          <p className="page-lead mt-3 mb-0">
            策略页首屏改成两层结构：上层只保留工厂摘要与精选候选，下层用表格完成对比和筛选。工厂运行态默认下沉，不再和选策略任务抢注意力。
          </p>
          {(from || task) ? (
            <div className="mt-4 text-xs text-text-secondary">
              上下文跳转{from ? ` · 来源: ${from}` : ''}{task ? ` · 任务: ${task}` : ''}
            </div>
          ) : null}
          <div className="mt-5 flex flex-wrap gap-2">
            {capabilityBadges.slice(0, 8).map((item) => (
              <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
                {item.label}
              </Badge>
            ))}
          </div>
        </div>

        <SectionCard className="mt-0">
          <div className="eyebrow">目录摘要</div>
          <h2 className="mt-2">当前目录</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">目录策略数</div>
              <div className="mt-2 text-2xl font-semibold text-text-primary">{strategies.length}</div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">已启用能力</div>
              <div className="mt-2 text-2xl font-semibold text-text-primary">{enabledCapabilityCount}</div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">最佳年化</div>
              <div className={`mt-2 text-lg font-semibold ${(bestAnnualReturn ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                {bestAnnualReturn == null || !Number.isFinite(bestAnnualReturn) ? '-' : fmtPct(bestAnnualReturn)}
              </div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">最佳 Sharpe</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">
                {bestSharpe == null || !Number.isFinite(bestSharpe) ? '-' : fmtNum(bestSharpe, 2)}
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <AskAiButton
              prompt={`当前策略目录共 ${strategies.length} 个策略，请推荐几个值得重点关注的，并说明理由`}
              label="AI 推荐策略"
            />
            <button
              type="button"
              onClick={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
              disabled={runFactoryApi.isPending}
              className="rounded-full bg-primary px-4 py-2 text-sm text-white shadow-sm disabled:opacity-50"
            >
              {runFactoryApi.isPending ? '工厂运行中...' : '立即运行一轮工厂'}
            </button>
            <button
              type="button"
              onClick={() => setShowCart((prev) => !prev)}
              className="relative rounded-full border border-border bg-surface px-4 py-2 text-sm text-text-secondary"
            >
              组合购物车
              {cartItems.length > 0 ? (
                <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] text-white">
                  {cartItems.length}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => setShowFactoryDetails((prev) => !prev)}
              className="rounded-full border border-border bg-surface px-4 py-2 text-sm text-text-secondary"
              aria-expanded={showFactoryDetails}
            >
              {showFactoryDetails ? '收起工厂运行态' : '展开工厂运行态'}
            </button>
          </div>
          {runFactoryApi.error ? <p className="mb-0 mt-3 text-sm text-danger">{runFactoryApi.error}</p> : null}
        </SectionCard>
      </section>

      <SectionCard className="mt-0">
        <div className="flex flex-col gap-3">
          {/* 行 1：搜索 + 排序 + 视图切换 + 操作 */}
          <div className="toolbar-strip">
            <div className="flex flex-wrap items-center gap-2 flex-1">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索策略名称 / 描述"
                aria-label="搜索策略名称、描述或类型"
                className="w-48 px-3 py-2 text-sm"
              />
              <span className="text-xs text-text-muted hidden sm:inline">排序</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                aria-label="排序字段"
                className="w-28 px-2 py-2 text-xs"
              >
                <option value="totalReturn">按年化</option>
                <option value="sharpe">按 Sharpe</option>
                <option value="maxDrawdown">按最大回撤</option>
                <option value="subscriber_count">按订阅数</option>
              </select>
              <button
                type="button"
                onClick={() => setSortDir((d) => d === 'desc' ? 'asc' : 'desc')}
                className="action-chip text-xs"
                title={sortDir === 'desc' ? '当前降序' : '当前升序'}
              >
                {sortDir === 'desc' ? '↓ 降序' : '↑ 升序'}
              </button>
              <button
                type="button"
                onClick={() => setShowFeatured((v) => !v)}
                className="action-chip text-xs ml-auto"
              >
                {showFeatured ? '收起精选卡片' : '展开精选卡片'}
              </button>
              <Link href="/paper-trading?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去模拟盘
              </Link>
              <Link href="/portfolio?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去组合页
              </Link>
            </div>
          </div>
          {/* 行 2：分类 Tab + 结果数 */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="overflow-x-auto">
              <TabBar
                tabs={CATEGORIES}
                active={category}
                onChange={(c) => { setCategory(c); setSearch(''); }}
              />
            </div>
            <span className="ml-auto text-xs text-text-muted shrink-0">
              共 <span className="font-semibold text-text-primary">{strategies.length}</span> 个策略
            </span>
          </div>
        </div>
      </SectionCard>

      <SectionCard className="mt-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">工厂概况</div>
            <h2 className="mt-2">{showEmptyStrategyState ? '先确认工厂有没有产出' : '只看关键工厂指标'}</h2>
          </div>
          <Badge variant={snapshotDegraded ? 'warning' : 'success'}>
            {snapshotDegraded ? '快照存在降级' : '快照完整'}
          </Badge>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {factoryOverview.map((item) => (
            <div key={item.label} className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">{item.label}</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{item.value}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
          <span className="rounded-full border border-border bg-surface px-3 py-1">
            快照完成率 {snapshotCompletionRatio == null ? '-' : fmtPct(snapshotCompletionRatio)}
          </span>
          <span className="rounded-full border border-border bg-surface px-3 py-1">
            失败原因 {snapshotFailureCount}
          </span>
          <span className="rounded-full border border-border bg-surface px-3 py-1">
            最近失败运行 {failedRuns.length}
          </span>
        </div>
      </SectionCard>

      {rankQ.isPending ? <LoadingState text="加载策略列表..." /> : null}
      {rankQ.error ? <ErrorState text={rankQ.error} /> : null}

      {showEmptyStrategyState ? (
        <SectionCard className="mt-0">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2>当前还没有可选策略</h2>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                常见原因是工厂尚未运行、最新候选还在质量门控里，或者策略仍停留在孵化态。建议先执行工厂，再去看详细运行态确认卡点。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
                disabled={runFactoryApi.isPending}
                className="rounded-full bg-primary px-4 py-2 text-sm text-white shadow-sm disabled:opacity-50"
              >
                {runFactoryApi.isPending ? '运行中...' : '立即运行一轮工厂'}
              </button>
              <button
                type="button"
                onClick={() => setShowFactoryDetails(true)}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm text-text-secondary"
              >
                查看工厂运行态
              </button>
              <Link href="/paper-trading" className="rounded-full border border-border bg-surface px-4 py-2 text-sm no-underline text-text-secondary">
                了解孵化后的落地路径
              </Link>
            </div>
          </div>
        </SectionCard>
      ) : (
        <>
          {showFeatured ? (
            <SectionCard className="mt-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">精选策略卡片</div>
                  <h2 className="mt-1">前 3 个候选（按当前排序）</h2>
                </div>
                <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3 text-sm text-text-secondary">
                  分类：<span className="font-semibold text-text-primary">{activeCategoryLabel}</span>
                </div>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-3">
                {featuredStrategies.map((strategy) => (
                  <StrategyCard
                    key={strategy.id}
                    s={strategy}
                    onAdd={(item) => addToCart({ strategyId: item.id, name: item.name, weight: 0 })}
                  />
                ))}
              </div>
            </SectionCard>
          ) : null}

          <SectionCard className="mt-0">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div>
                <div className="eyebrow">全量目录</div>
                <h2 className="mt-1">策略表格视图</h2>
              </div>
              <span className="text-xs text-text-muted">共 {strategies.length} 条 · 按 <b className="text-text-primary">{sortBy === 'totalReturn' ? '年化' : sortBy === 'sharpe' ? 'Sharpe' : sortBy === 'maxDrawdown' ? '最大回撤' : '订阅数'}</b> {sortDir === 'desc' ? '降序' : '升序'}</span>
            </div>
            <DataTable
              rows={strategies as Record<string, unknown>[]}
              columns={strategyColumns}
              rowKey="id"
              maxHeight={560}
              mobileCardRender={(row) => {
                const strategy = row as Strategy;
                const metrics = getStrategyMetricSnapshot(strategy);
                return (
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
                          <div className="text-sm font-semibold text-text-primary">{strategy.name}</div>
                        </Link>
                        <div className="mt-1 text-xs text-text-secondary">
                          {strategy.description || strategy.strategy_type || '暂无描述'}
                        </div>
                      </div>
                      <Badge variant="neutral">{resolveCategoryLabel(strategy.strategy_type)}</Badge>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs text-text-secondary">
                      <div>
                        <div className="metric-label">年化</div>
                        <div className={`mt-2 text-sm font-semibold ${(metrics.totalReturn ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {fmtPct(metrics.totalReturn ?? 0)}
                        </div>
                      </div>
                      <div>
                        <div className="metric-label">Sharpe</div>
                        <div className="mt-2 text-sm font-semibold text-text-primary">
                          {fmtNum(metrics.sharpe ?? 0, 2)}
                        </div>
                      </div>
                      <div>
                        <div className="metric-label">回撤</div>
                        <div className="mt-2 text-sm font-semibold text-danger">
                          {fmtPct(metrics.maxDrawdown ?? 0)}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-2 border-t border-border pt-3 text-xs text-text-secondary">
                      <span>{strategy.subscriber_count ?? 0} 人订阅</span>
                      <button
                        type="button"
                        onClick={() => addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 })}
                        className="rounded-full bg-primary px-3 py-1.5 text-xs text-white shadow-sm"
                      >
                        加入组合
                      </button>
                    </div>
                  </div>
                );
              }}
            />
          </SectionCard>
        </>
      )}

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

      {showCart && <CartDrawer onClose={() => setShowCart(false)} />}
    </PageContainer>
  );
}
