'use client';

import { useMemo, useState } from 'react';
import { Badge, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { StrategyCard, type Strategy } from '@/components/strategy-card';
import { useCartStore } from '@/store/cart-store';
import { ensureRecordOrArray } from '@/lib/query-parse';
import { apiKeys } from '@/lib/query-keys';

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'momentum', label: '动量' },
  { key: 'value', label: '价值' },
  { key: 'quality', label: '质量' },
  { key: 'multi_factor', label: '多因子' },
  { key: 'macro', label: '宏观' },
] as const;

type RankingResponse = { strategies?: Strategy[] } | Strategy[];

type FactoryStatusResponse = {
  running?: boolean;
  run_time?: string;
  last_run?: string | null;
  last_summary?: {
    candidates_spawned?: number;
    candidates_passed_backtest?: number;
    candidates_after_dedup?: number;
    passed_quality_gate?: number;
    autonomy_generated?: number;
    snapshot_degraded?: boolean;
    snapshot_completion_ratio?: number;
    snapshot_failure_reason_count?: number;
    eliminated?: number;
    elapsed_seconds?: number;
  };
  last_result?: {
    status?: string;
    error?: string;
  };
};

type CapabilityResponse = {
  daily_snapshot?: boolean;
  paper_incubation?: boolean;
  runtime_risk?: boolean;
  execution_risk?: boolean;
  vector_platform?: boolean;
  vector_governance?: boolean;
  ai_generation?: boolean;
  multi_agent_review?: boolean;
  quality_governance?: boolean;
  domain_events?: boolean;
  runtime_cycle?: boolean;
};

type DailySnapshotResponse = {
  snapshot_date?: string;
  fear_greed_index?: number;
  degraded?: boolean;
  failure_reasons?: string[];
  missing_fields?: string[];
  hot_sectors?: string[];
  cold_sectors?: string[];
  summary?: {
    listed_count?: number;
  };
  completeness?: {
    completion_ratio?: number;
  };
};

type FactoryRunsResponse = {
  items?: Array<{
    run_id?: string;
    status?: string;
    started_at?: string;
    completed_at?: string | null;
    elapsed_seconds?: number;
    error?: string | null;
    summary?: {
      candidates_spawned?: number;
      candidates_after_dedup?: number;
      submitted?: number;
      passed_quality_gate?: number;
      eliminated?: number;
      elapsed_seconds?: number;
    };
    stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
  }>;
  count?: number;
};

type FactoryRunDetailResponse = {
  run_id?: string;
  status?: string;
  started_at?: string;
  completed_at?: string | null;
  elapsed_seconds?: number;
  error?: string | null;
  summary?: Record<string, number | string | null | undefined>;
  snapshot_summary?: Record<string, string | number | null | undefined>;
  stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
};

type FactoryRunItem = NonNullable<FactoryRunsResponse['items']>[number];
type RunStatusFilter = 'all' | 'success' | 'failed';
type TrendMetricKey = 'candidates_spawned' | 'submitted' | 'passed_quality_gate' | 'elapsed_seconds';

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
      { key: 'vector_platform', label: '向量平台', enabled: factoryCapabilities.vector_platform ?? false },
      { key: 'vector_governance', label: '索引治理', enabled: factoryCapabilities.vector_governance ?? false },
      { key: 'ai_generation', label: 'AI生成', enabled: factoryCapabilities.ai_generation ?? false },
      { key: 'multi_agent_review', label: '多代理评审', enabled: factoryCapabilities.multi_agent_review ?? false },
      { key: 'quality_governance', label: '质量治理', enabled: factoryCapabilities.quality_governance ?? false },
      { key: 'domain_events', label: '领域事件', enabled: factoryCapabilities.domain_events ?? false },
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

      <SectionCard className="mt-4 p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 className="m-0">策略工厂运行态</h3>
            <p className="m-0 mt-1 text-sm text-text-secondary">
              调度状态：{factoryStatusQ.data?.running ? '运行中' : '未启动'} · 上次运行：{factoryStatusQ.data?.last_run ?? '暂无'}
              {latestSnapshot?.snapshot_date ? ` · 最新快照：${latestSnapshot.snapshot_date}` : ''}
            </p>
          </div>
          <button
            onClick={() => runFactoryApi.trigger('/strategy-market/factory/run-once', { method: 'POST' })}
            disabled={runFactoryApi.isPending}
            className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {runFactoryApi.isPending ? '运行中...' : '立即运行一轮工厂'}
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3 mt-4 text-sm">
          <FactoryMetric title="候选生成" value={factorySummary.candidates_spawned ?? 0} />
          <FactoryMetric title="AI生成" value={factorySummary.autonomy_generated ?? 0} />
          <FactoryMetric title="通过回测" value={factorySummary.candidates_passed_backtest ?? 0} />
          <FactoryMetric title="去重后" value={factorySummary.candidates_after_dedup ?? 0} />
          <FactoryMetric title="质检通过" value={factorySummary.passed_quality_gate ?? 0} />
          <FactoryMetric title="快照完成率" value={formatRatioPercent(snapshotCompletionRatio)} />
          <FactoryMetric title="快照状态" value={snapshotDegraded ? '降级' : '正常'} />
          <FactoryMetric title="快照异常数" value={snapshotFailureCount} />
          <FactoryMetric title="淘汰数" value={factorySummary.eliminated ?? 0} />
          <FactoryMetric title="耗时(秒)" value={factorySummary.elapsed_seconds ?? '-'} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {capabilityBadges.map((item) => (
            <Badge key={item.key} variant={item.enabled ? 'success' : 'neutral'}>
              {item.label}{item.enabled ? '已接入' : '未接入'}
            </Badge>
          ))}
        </div>
        {latestSnapshot && (
          <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-2 text-xs text-text-secondary space-y-1">
            <div>
              恐慌贪婪：{latestSnapshot.fear_greed_index ?? '-'} · 已上架策略：{latestSnapshot.summary?.listed_count ?? '-'} · 缺失字段：{latestSnapshot.missing_fields?.length ?? 0}
            </div>
            {latestSnapshot.hot_sectors?.length ? <div>热点板块：{latestSnapshot.hot_sectors.slice(0, 4).join('、')}</div> : null}
            {snapshotFailureCount > 0 ? (
              <div className={snapshotDegraded ? 'text-warning' : ''}>
                快照异常：{(latestSnapshot.failure_reasons ?? []).slice(0, 3).join('；') || '存在异常但未返回原因'}
              </div>
            ) : null}
          </div>
        )}
        {capabilitiesQ.error && <p className="mt-3 mb-0 text-sm text-danger">能力接口加载失败：{capabilitiesQ.error}</p>}
        {dailySnapshotQ.error && <p className="mt-3 mb-0 text-sm text-danger">日快照加载失败：{dailySnapshotQ.error}</p>}
        {factoryStatusQ.data?.last_result?.status === 'failed' && (
          <p className="mt-3 mb-0 text-sm text-danger">最近一次工厂运行失败：{factoryStatusQ.data?.last_result?.error ?? '未知错误'}</p>
        )}
        {runFactoryApi.error && <p className="mt-3 mb-0 text-sm text-danger">{runFactoryApi.error}</p>}
        {factoryRunsQ.isPending && <p className="mt-3 mb-0 text-sm text-text-secondary">加载运行历史...</p>}
        {!factoryRunsQ.isPending && factoryRuns.length === 0 && (
          <p className="mt-3 mb-0 text-sm text-text-secondary">暂无工厂运行历史</p>
        )}
        {factoryRuns.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs text-text-secondary">状态筛选：</span>
            {[
              { key: 'all', label: '全部' },
              { key: 'success', label: '成功' },
              { key: 'failed', label: '失败' },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setRunStatusFilter(item.key as RunStatusFilter)}
                className={`px-2 py-1 text-xs rounded border cursor-pointer ${runStatusFilter === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
        {!factoryRunsQ.isPending && factoryRuns.length > 0 && filteredRuns.length === 0 && (
          <p className="mt-3 mb-0 text-sm text-text-secondary">当前筛选条件下暂无运行记录</p>
        )}
        {filteredRuns.length > 0 && (
          <div className="mt-4 space-y-2">
            <div className="text-sm font-medium">最近运行历史</div>
            {filteredRuns.map((item) => (
              <div key={item.run_id ?? item.started_at} className="rounded border border-border bg-surface-alt px-3 py-2">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium">{item.status === 'success' ? '成功' : item.status === 'failed' ? '失败' : (item.status ?? '-')}</span>
                  <span className="text-text-secondary">{item.completed_at ?? item.started_at ?? '-'}</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 text-xs text-text-secondary">
                  <span>候选 {item.summary?.candidates_spawned ?? 0}</span>
                  <span>去重后 {item.summary?.candidates_after_dedup ?? 0}</span>
                  <span>提交 {item.summary?.submitted ?? 0}</span>
                  <span>质检通过 {item.summary?.passed_quality_gate ?? 0}</span>
                  <span>淘汰 {item.summary?.eliminated ?? 0}</span>
                </div>
                <div className="mt-2 text-xs text-text-secondary">
                  耗时：{item.elapsed_seconds ?? item.summary?.elapsed_seconds ?? '-'} 秒
                </div>
                {item.error && <div className="mt-2 text-xs text-danger">错误：{item.error}</div>}
                {item.run_id && (
                  <div className="mt-3">
                    <button
                      onClick={() => setExpandedRunId((current) => (current === item.run_id ? null : item.run_id ?? null))}
                      className="px-2 py-1 text-xs rounded border border-border cursor-pointer hover:bg-surface"
                    >
                      {expandedRunId === item.run_id ? '收起详情' : '查看详情'}
                    </button>
                  </div>
                )}
                {expandedRunId === item.run_id && (
                  <FactoryRunDetailPanel
                    loading={factoryRunDetailQ.isPending}
                    detail={expandedRun}
                    error={factoryRunDetailQ.error}
                  />
                )}
              </div>
            ))}
          </div>
        )}
        {comparableRuns.length > 1 && (
          <div className="mt-5">
            <div className="text-sm font-medium mb-2">最近运行对比</div>
            <FactoryRunComparisonTable runs={comparableRuns} />
          </div>
        )}
        {trendRuns.length > 1 && (
          <div className="mt-5">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <div className="text-sm font-medium">运行趋势</div>
              <div className="flex flex-wrap items-center gap-2">
                {[
                  { key: 'candidates_spawned', label: '候选生成' },
                  { key: 'submitted', label: '提交数' },
                  { key: 'passed_quality_gate', label: '质检通过' },
                  { key: 'elapsed_seconds', label: '耗时' },
                ].map((item) => (
                  <button
                    key={item.key}
                    onClick={() => setTrendMetricKey(item.key as TrendMetricKey)}
                    className={`px-2 py-1 text-xs rounded border cursor-pointer ${trendMetricKey === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <FactoryRunTrendPanel runs={trendRuns} metricKey={trendMetricKey} />
          </div>
        )}
        {failedRuns.length > 0 && (
          <div className="mt-5">
            <div className="text-sm font-medium mb-2">失败原因聚合</div>
            <FactoryRunFailurePanel runs={failedRuns} totalRuns={factoryRuns.length} />
          </div>
        )}
      </SectionCard>

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

      {/* Cart Drawer */}
      {showCart && <CartDrawer onClose={() => setShowCart(false)} />}
    </PageContainer>
  );
}

function FactoryMetric({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded border border-border px-3 py-2 bg-surface-alt">
      <div className="text-xs text-text-secondary">{title}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function formatRatioPercent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${Math.round(Number(value) * 100)}%`;
}

function FactoryRunComparisonTable({
  runs,
}: {
  runs: FactoryRunItem[];
}) {
  const rows = [
    {
      label: '状态',
      value: (run: FactoryRunItem) => (
        run.status === 'success' ? '成功' : run.status === 'failed' ? '失败' : (run.status ?? '-')
      ),
    },
    {
      label: '候选生成',
      value: (run: FactoryRunItem) => String(run.summary?.candidates_spawned ?? 0),
    },
    {
      label: '去重后',
      value: (run: FactoryRunItem) => String(run.summary?.candidates_after_dedup ?? 0),
    },
    {
      label: '提交数',
      value: (run: FactoryRunItem) => String(run.summary?.submitted ?? 0),
    },
    {
      label: '质检通过',
      value: (run: FactoryRunItem) => String(run.summary?.passed_quality_gate ?? 0),
    },
    {
      label: '淘汰数',
      value: (run: FactoryRunItem) => String(run.summary?.eliminated ?? 0),
    },
    {
      label: '耗时(秒)',
      value: (run: FactoryRunItem) => String(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? '-'),
    },
  ];

  return (
    <div className="overflow-x-auto rounded border border-border bg-surface-alt">
      <table className="min-w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-surface">
            <th className="px-3 py-2 text-left font-medium whitespace-nowrap">指标</th>
            {runs.map((run, idx) => (
              <th key={run.run_id ?? run.started_at ?? idx} className="px-3 py-2 text-left font-medium whitespace-nowrap min-w-28">
                <div>第 {idx + 1} 次</div>
                <div className="mt-1 text-caption text-text-secondary font-normal">
                  {run.completed_at ?? run.started_at ?? '-'}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-border last:border-b-0">
              <td className="px-3 py-2 font-medium whitespace-nowrap">{row.label}</td>
              {runs.map((run, idx) => (
                <td key={`${row.label}-${run.run_id ?? run.started_at ?? idx}`} className="px-3 py-2 whitespace-nowrap text-text-secondary">
                  {row.value(run)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FactoryRunTrendPanel({ runs, metricKey }: { runs: FactoryRunItem[]; metricKey: TrendMetricKey }) {
  const successCount = runs.filter((run) => run.status === 'success').length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : 0;
  const avgElapsed = runs.length > 0
    ? (runs.reduce((sum, run) => sum + Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0), 0) / runs.length).toFixed(1)
    : '0.0';
  const latest = runs[runs.length - 1];
  const first = runs[0];

  const metrics = [
    { key: 'candidates_spawned', label: '候选生成', value: (run: FactoryRunItem) => Number(run.summary?.candidates_spawned ?? 0) },
    { key: 'submitted', label: '提交数', value: (run: FactoryRunItem) => Number(run.summary?.submitted ?? 0) },
    { key: 'passed_quality_gate', label: '质检通过', value: (run: FactoryRunItem) => Number(run.summary?.passed_quality_gate ?? 0) },
    { key: 'elapsed_seconds', label: '耗时(秒)', value: (run: FactoryRunItem) => Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0) },
  ];
  const activeMetric = metrics.find((metric) => metric.key === metricKey) ?? metrics[0];

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近成功率" value={`${successRate}%`} />
        <FactoryMetric title="平均耗时(秒)" value={avgElapsed} />
        <FactoryMetric title="最新候选数" value={latest?.summary?.candidates_spawned ?? 0} />
        <FactoryMetric title="最新质检通过" value={latest?.summary?.passed_quality_gate ?? 0} />
      </div>

      <div className="mt-4 space-y-3">
        {(() => {
          const values = runs.map(activeMetric.value);
          const max = Math.max(...values, 1);
          const latestValue = activeMetric.value(latest);
          const firstValue = activeMetric.value(first);
          const delta = latestValue - firstValue;

          return (
            <div className="rounded border border-border bg-surface px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium">{activeMetric.label}</span>
                <span className="text-text-secondary">
                  最新 {latestValue} · 较最早 {delta > 0 ? '+' : ''}{delta}
                </span>
              </div>
              <div className="mt-2 flex items-end gap-2 h-24">
                {runs.map((run, idx) => {
                  const value = activeMetric.value(run);
                  const height = Math.max((value / max) * 100, value > 0 ? 8 : 2);
                  return (
                    <div key={`${activeMetric.key}-${run.run_id ?? idx}`} className="flex-1 min-w-0">
                      <div className="h-20 flex items-end">
                        <div
                          className={`w-full rounded-t ${run.status === 'failed' ? 'bg-danger/70' : 'bg-primary/70'}`}
                          style={{ height: `${height}%` }}
                          title={`${activeMetric.label}: ${value}`}
                        />
                      </div>
                      <div className="mt-1 text-center text-caption text-text-secondary truncate">
                        {idx + 1}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

function FactoryRunFailurePanel({ runs, totalRuns }: { runs: FactoryRunItem[]; totalRuns: number }) {
  const failureRate = totalRuns > 0 ? Math.round((runs.length / totalRuns) * 100) : 0;
  const latestFailed = runs[0];
  const reasonBuckets = new Map<string, { count: number; example: string }>();
  const stageBuckets = new Map<string, number>();
  const unclassifiedExamples = new Map<string, number>();
  const matchedLabels = new Set<string>();
  let matchedCount = 0;

  runs.forEach((run) => {
    const fingerprint = getFactoryRunErrorFingerprint(run.error);
    const current = reasonBuckets.get(fingerprint.label);
    reasonBuckets.set(fingerprint.label, {
      count: (current?.count ?? 0) + 1,
      example: current?.example ?? fingerprint.example,
    });

    if (fingerprint.matched) {
      matchedCount += 1;
      matchedLabels.add(fingerprint.label);
    } else {
      unclassifiedExamples.set(fingerprint.example, (unclassifiedExamples.get(fingerprint.example) ?? 0) + 1);
    }

    const stage = detectFailedStage(run);
    stageBuckets.set(stage, (stageBuckets.get(stage) ?? 0) + 1);
  });

  const topReasons = [...reasonBuckets.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3);
  const topStages = [...stageBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const topUnclassifiedExamples = [...unclassifiedExamples.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const unclassifiedCount = runs.length - matchedCount;
  const matchRate = runs.length > 0 ? Math.round((matchedCount / runs.length) * 100) : 0;
  const coverageCount = matchedLabels.size;

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近失败次数" value={runs.length} />
        <FactoryMetric title="失败率" value={`${failureRate}%`} />
        <FactoryMetric title="最近失败阶段" value={detectFailedStage(latestFailed)} />
        <FactoryMetric title="最近失败时间" value={shortFactoryRunTime(latestFailed.completed_at ?? latestFailed.started_at)} />
      </div>

      <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
        <div className="text-xs font-medium mb-3">规则命中统计</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FactoryMetric title="规则命中失败" value={matchedCount} />
          <FactoryMetric title="规则命中率" value={`${matchRate}%`} />
          <FactoryMetric title="未分类错误" value={unclassifiedCount} />
          <FactoryMetric title="覆盖指纹种类" value={coverageCount} />
        </div>

        <div className="mt-3 text-xs text-text-secondary">
          统计口径：规则命中率 = 已命中规则失败数 / 最近失败总数；覆盖指纹种类仅统计已命中规则的错误类别。
        </div>

        {topUnclassifiedExamples.length > 0 && (
          <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3">
            <div className="text-xs font-medium mb-2">未分类错误示例</div>
            <div className="space-y-2 text-xs text-text-secondary">
              {topUnclassifiedExamples.map(([example, count]) => (
                <div key={example} className="flex items-start justify-between gap-3">
                  <span className="break-all">{example}</span>
                  <span className="shrink-0">{count} 次</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">常见错误原因</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topReasons.map(([reason, meta]) => (
              <div key={reason} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-all">{reason}</div>
                  <div className="mt-1 text-caption text-text-tertiary break-all">示例：{meta.example}</div>
                </div>
                <span className="shrink-0">{meta.count} 次</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">失败阶段分布</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topStages.map(([stage, count]) => (
              <div key={stage} className="flex items-center justify-between gap-3">
                <span>{stage}</span>
                <span>{count} 次</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {latestFailed?.error && (
        <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">最近失败详情</div>
          <div className="text-xs text-danger break-all">{normalizeFactoryRunError(latestFailed.error)}</div>
          <div className="mt-2 text-caption text-text-secondary">
            错误指纹：{getFactoryRunErrorFingerprint(latestFailed.error).label}
          </div>
        </div>
      )}
    </div>
  );
}

function getFactoryRunErrorFingerprint(error?: string | null) {
  const example = normalizeFactoryRunError(error);
  const normalized = example.toLowerCase();

  const rules: Array<{ label: string; patterns: RegExp[] }> = [
    { label: '超时错误', patterns: [/timeout/i, /timed out/i, /deadline/i, /超时/] },
    { label: '网络连接错误', patterns: [/connection/i, /network/i, /socket/i, /dns/i, /refused/i, /unreachable/i, /http/i] },
    { label: '数据库错误', patterns: [/postgres/i, /database/i, /sql/i, /asyncpg/i, /timescaledb/i, /db error/i] },
    { label: '权限错误', patterns: [/permission/i, /forbidden/i, /unauthorized/i, /access denied/i, /鉴权/, /权限/] },
    { label: '配置缺失', patterns: [/missing/i, /env/i, /config/i, /credential/i, /token/i, /api key/i, /配置/] },
    { label: '输入校验错误', patterns: [/invalid/i, /validation/i, /valueerror/i, /typeerror/i, /keyerror/i, /assert/i, /参数/, /校验/] },
    { label: '依赖加载错误', patterns: [/module not found/i, /importerror/i, /cannot import/i, /no module named/i, /dependency/i] },
  ];

  const matched = rules.find((rule) => rule.patterns.some((pattern) => pattern.test(normalized)));
  return {
    label: matched?.label ?? '未分类错误',
    example,
    matched: Boolean(matched),
  };
}

function normalizeFactoryRunError(error?: string | null) {
  const text = String(error ?? '').trim();
  if (!text) return '未知错误';
  return text
    .split('\n')[0]
    .replace(/\s+/g, ' ')
    .replace(/[0-9]{4}-[0-9]{2}-[0-9]{2}[ t][0-9:.+-zZ]*/g, '<time>')
    .replace(/[0-9a-f]{8,}/gi, '<id>')
    .replace(/\b\d+\b/g, '<num>')
    .slice(0, 80);
}

function shortFactoryRunTime(value?: string | null) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

function detectFailedStage(run?: FactoryRunItem | null) {
  if (!run || run.status !== 'failed') return '-';
  const order = ['collect', 'spawn', 'backtest', 'deduplicate', 'submit', 'elimination'];
  const stages = run.stages ?? {};
  for (const name of order) {
    const stage = stages[name];
    if (!stage) return name;
    if (stage.ok === false) return name;
  }
  return 'unknown';
}

function FactoryRunDetailPanel({
  detail,
  loading,
  error,
}: {
  detail: FactoryRunDetailResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <div className="mt-3 text-xs text-text-secondary">加载运行详情...</div>;
  }
  if (error) {
    return <div className="mt-3 text-xs text-danger">加载详情失败：{error}</div>;
  }
  if (!detail) {
    return <div className="mt-3 text-xs text-text-secondary">暂无运行详情</div>;
  }

  const snapshotRows = Object.entries(detail.snapshot_summary ?? {});
  const stageRows = Object.entries(detail.stages ?? {});

  return (
    <div className="mt-3 rounded border border-border bg-surface px-3 py-3 space-y-3">
      <div>
        <div className="text-xs font-medium">运行标识</div>
        <div className="mt-1 text-xs text-text-secondary break-all">{detail.run_id ?? '-'}</div>
      </div>

      {snapshotRows.length > 0 && (
        <div>
          <div className="text-xs font-medium">快照摘要</div>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
            {snapshotRows.map(([key, value]) => (
              <div key={key}>{key}: {String(value ?? '-')}</div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs font-medium">阶段结果</div>
        {stageRows.length > 0 ? (
          <div className="mt-1 space-y-2">
            {stageRows.map(([stage, payload]) => (
              <div key={stage} className="rounded border border-border px-2 py-2 text-xs text-text-secondary">
                <div className="font-medium text-text-primary mb-1">{stage}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(payload ?? {}).map(([key, value]) => (
                    <div key={key}>{key}: {String(value ?? '-')}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-1 text-xs text-text-secondary">暂无阶段详情</div>
        )}
      </div>

      {detail.error && (
        <div className="text-xs text-danger">错误信息：{detail.error}</div>
      )}
    </div>
  );
}

function CartDrawer({ onClose }: { onClose: () => void }) {
  const { items, removeStrategy, setWeight, clear } = useCartStore();
  const createApi = useApiMutation();
  const [name, setName] = useState('');

  const totalWeight = items.reduce((sum, i) => sum + i.weight, 0);
  const weightValid = items.length > 0 && Math.abs(totalWeight - 100) < 0.01;

  function autoBalance() {
    const w = Math.floor(100 / items.length);
    const remainder = 100 - w * items.length;
    items.forEach((item, idx) => setWeight(item.strategyId, w + (idx === 0 ? remainder : 0)));
  }

  async function handleSubmit() {
    if (!weightValid) return;
    const portfolioName = name.trim() || `策略组合 ${new Date().toLocaleDateString()}`;
    await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, {
      name: portfolioName,
      description: `策略组合: ${items.map((i) => `${i.name}(${i.weight}%)`).join(', ')}`,
      strategies: items.map((i) => ({ strategyId: i.strategyId, weight: i.weight / 100 })),
    });
    clear();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-85 bg-surface-alt border-l border-border p-4 overflow-y-auto z-10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="m-0 text-sm font-semibold">组合购物车 ({items.length})</h3>
          <button onClick={onClose} className="text-lg cursor-pointer">✕</button>
        </div>

        {items.length === 0 && <p className="text-text-secondary text-sm">购物车为空，请从策略列表添加策略</p>}

        {items.map((item) => (
          <div key={item.strategyId} className="flex items-center gap-2 py-2 border-b border-border">
            <div className="flex-1 text-sm truncate">{item.name}</div>
            <input
              type="number"
              min={0}
              max={100}
              value={item.weight}
              onChange={(e) => setWeight(item.strategyId, Number(e.target.value))}
              className="w-14 px-1 py-0.5 border border-border rounded text-xs text-center"
              placeholder="%"
            />
            <span className="text-[10px] text-text-secondary">%</span>
            <button onClick={() => removeStrategy(item.strategyId)} className="text-danger text-xs cursor-pointer">删除</button>
          </div>
        ))}

        {items.length > 0 && (
          <>
            <div className={`text-xs mt-2 ${weightValid ? 'text-success' : 'text-danger'}`}>
              权重合计: {totalWeight.toFixed(1)}%{!weightValid && ' (需等于100%)'}
            </div>
            <div className="mt-3 space-y-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="组合名称（可选）"
                className="w-full px-2 py-1 border border-border rounded text-xs"
              />
              <div className="flex gap-2">
                <button onClick={autoBalance} className="flex-1 px-2 py-1 text-xs border border-border rounded cursor-pointer hover:bg-surface-alt">
                  等权分配
                </button>
                <button onClick={clear} className="flex-1 px-2 py-1 text-xs border border-border rounded cursor-pointer hover:bg-surface-alt">
                  清空
                </button>
              </div>
              <button
                onClick={handleSubmit}
                disabled={!weightValid || createApi.isPending}
                className="w-full px-2 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
              >
                {createApi.isPending ? '创建中...' : '创建策略组合'}
              </button>
              {createApi.error && <p className="text-danger text-xs">{createApi.error}</p>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
