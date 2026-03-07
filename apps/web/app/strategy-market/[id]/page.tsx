'use client';

import { useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, DataTable } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { useCartStore } from '@/store/cart-store';
import { useAuthStore } from '@/store/auth-store';

type StrategyMetric = {
  period?: string;
  total_return?: number;
  annual_return?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  win_rate?: number;
  calmar_ratio?: number;
  trade_count?: number;
};

type StrategyReview = {
  user_id: string;
  rating: number;
  comment?: string;
  created_at?: string;
};

type StrategyCore = {
  id: string;
  name: string;
  description?: string;
  strategy_type?: string;
  status?: string;
  author_id?: string;
  subscriber_count?: number;
  avg_rating?: number;
  review_count?: number;
  factor_weights?: Record<string, number>;
  metrics?: StrategyMetric[];
  reviews?: StrategyReview[];
};

type SignalStatsResponse = {
  hit_rate?: Record<string, number>;
  forward_ic?: Record<string, number>;
  forward_sharpe?: Record<string, number>;
  total_signals?: number;
};

type Signal = {
  signal_date?: string;
  code?: string;
  signal?: number;
  score?: number;
};

type SignalsResponse = {
  signals?: Signal[];
  count?: number;
  subscriber?: boolean;
};

type ReviewReportResponse = {
  passed?: boolean;
  report_type?: string;
  reports?: Array<{
    report_type?: string;
    updated_at?: string;
    summary?: {
      review_source?: string;
      validation_grade?: string;
    };
  }>;
  summary?: {
    status_after_review?: string;
    validation_grade?: string;
    review_source?: string;
  };
  quality_gate?: {
    wf_ic_ir?: number;
    pkf_ic?: number;
    bootstrap_ci_lower?: number;
    param_sensitivity?: number;
    reasons?: string[];
    reason_codes?: string[];
  };
  dedup_report?: {
    duplicate?: boolean;
    match_type?: string | null;
    param_similarity?: number;
    vector_similarity?: number;
    reason?: string;
  };
};

type StrategyEventsResponse = {
  events?: Array<{
    event_type?: string;
    from_status?: string | null;
    to_status?: string;
    actor_id?: string;
    reason?: string;
    created_at?: string;
    metadata?: Record<string, unknown>;
  }>;
  count?: number;
};

type IncubationOverviewResponse = {
  status?: string;
  sharpe_ratio?: number;
  max_drawdown?: number;
  total_signals?: number;
  minimum_signal_count?: number;
  hit_rate_5d?: number | null;
  forward_ic_5d?: number | null;
  forward_sharpe_5d?: number | null;
  promotion_ready?: boolean;
  deprecation_risk?: boolean;
  blockers?: string[];
  risk_flags?: string[];
  observed_forward_days?: number[];
  missing_forward_days?: number[];
  forward_returns?: Array<{
    label?: string;
    hit_rate?: number | null;
    forward_ic?: number | null;
    forward_sharpe?: number | null;
  }>;
  blockers_by_period?: Record<string, string[]>;
  risk_flags_by_period?: Record<string, string[]>;
  validation_grade?: string | null;
};

type IncubationAccount = {
  strategy_id?: string;
  account_id?: string;
  stage?: string;
  status?: string;
  source_run_id?: string;
  metadata?: Record<string, unknown>;
};

type IncubationMetric = {
  metric_date?: string;
  account_id?: string;
  stage?: string;
  decision?: string;
  nav?: number;
  total_value?: number;
  cash?: number;
  market_value?: number;
  daily_return?: number;
  max_drawdown?: number;
  sharpe_ratio?: number;
  hit_rate_5d?: number;
  forward_ic_5d?: number;
  forward_sharpe_5d?: number;
  total_signals?: number;
  total_orders?: number;
  total_trades?: number;
  turnover_rate?: number;
  exposure_rate?: number;
  alpha_decay?: number;
  drift_score?: number;
};

type RiskEvent = {
  id?: number;
  severity?: string;
  event_type?: string;
  action?: string;
  status?: string;
  title?: string;
  reason?: string;
  detected_at?: string;
  payload?: Record<string, unknown>;
};

type VectorProfile = {
  id?: number;
  strategy_id?: string;
  profile_type?: string;
  vector_method?: string;
  metric?: string;
  vector_dim?: number;
  signature?: string;
  backend?: string;
  index_version?: string;
  metadata?: Record<string, unknown>;
};

type DomainEvent = {
  id?: number;
  strategy_id?: string | null;
  aggregate_type?: string;
  aggregate_id?: string | null;
  event_type?: string;
  source?: string;
  severity?: string;
  correlation_id?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string;
};

type AiExperiment = {
  experiment_id?: string;
  strategy_id?: string;
  source?: string;
  generator_type?: string;
  optimizer_type?: string;
  status?: string;
  hypothesis?: string;
  created_at?: string;
  updated_at?: string;
};

type ListResponse<T> = {
  items?: T[];
  count?: number;
  latest?: T | null;
};

type StrategyDetailResponse = {
  strategy?: StrategyCore;
  metrics?: StrategyMetric[];
  reviews?: StrategyReview[];
  nav_series?: number[];
  latest_quality_report?: ReviewReportResponse | null;
  incubation_account?: IncubationAccount | null;
  latest_incubation_metric?: IncubationMetric | null;
  open_risk_events?: RiskEvent[];
  vector_profiles?: VectorProfile[];
  domain_events?: DomainEvent[];
};

type EventFilters = {
  event_type: string;
  from_status: string;
  to_status: string;
  actor_id: string;
  start_time: string;
  end_time: string;
  limit: string;
};

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function shortText(value: unknown, length = 12) {
  const text = String(value ?? '');
  if (!text) return '-';
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const detailQ = useApiQuery<StrategyDetailResponse | StrategyCore>(id ? `/strategy-market/${id}` : null);
  const subscribeApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const reviewApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const addToCart = useCartStore((st) => st.addStrategy);
  const user = useAuthStore((st) => st.user);
  const userId = user?.id ?? user?.username ?? null;
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'tracking' | 'factory'>('overview');
  const [eventFilters, setEventFilters] = useState<EventFilters>({
    event_type: 'status_change',
    from_status: '',
    to_status: '',
    actor_id: '',
    start_time: '',
    end_time: '',
    limit: '20',
  });

  const eventsPath = useMemo(() => {
    if (!id || activeTab !== 'factory') return null;
    const qs = new URLSearchParams();
    Object.entries(eventFilters).forEach(([key, value]) => {
      if (value) qs.set(key, value);
    });
    if (!qs.has('limit')) qs.set('limit', '20');
    return `/strategy-market/${id}/events?${qs.toString()}`;
  }, [activeTab, eventFilters, id]);

  const signalStatsQ = useApiQuery<SignalStatsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signal-stats` : null,
  );
  const signalsQ = useApiQuery<SignalsResponse>(
    id && activeTab === 'tracking' ? `/strategy-market/${id}/signals?user_id=${encodeURIComponent(userId ?? 'default')}&limit=50` : null,
  );
  const reviewReportQ = useApiQuery<ReviewReportResponse>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/review-report` : null,
  );
  const eventsQ = useApiQuery<StrategyEventsResponse>(eventsPath);
  const incubationQ = useApiQuery<IncubationOverviewResponse>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/incubation-overview` : null,
  );
  const incubationMetricsQ = useApiQuery<ListResponse<IncubationMetric>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/incubation-metrics?limit=12` : null,
  );
  const riskEventsQ = useApiQuery<ListResponse<RiskEvent>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/risk-events?limit=20` : null,
  );
  const vectorProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/vector-profiles?limit=10` : null,
  );
  const aiExperimentsQ = useApiQuery<ListResponse<AiExperiment>>(
    id && activeTab === 'factory' ? `/strategy-market/ai/experiments?strategy_id=${encodeURIComponent(id)}&limit=10` : null,
  );
  const domainEventsQ = useApiQuery<ListResponse<DomainEvent>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/domain-events?limit=20` : null,
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
  const metrics = detail?.metrics ?? strategy?.metrics ?? [];
  const reviews = detail?.reviews ?? strategy?.reviews ?? [];
  const navSeries = detail?.nav_series ?? [];
  const latestQualityReport = detail?.latest_quality_report ?? null;
  const incubationAccount = detail?.incubation_account ?? null;
  const latestIncubationMetric = detail?.latest_incubation_metric ?? null;
  const openRiskEvents = (riskEventsQ.data?.items?.length ? riskEventsQ.data.items : detail?.open_risk_events) ?? [];
  const vectorProfiles = (vectorProfilesQ.data?.items?.length ? vectorProfilesQ.data.items : detail?.vector_profiles) ?? [];
  const domainEvents = (domainEventsQ.data?.items?.length ? domainEventsQ.data.items : detail?.domain_events) ?? [];

  const allMetrics = useMemo(() => {
    if (!metrics.length) return null;
    return metrics.find((m) => m.period === 'all') ?? metrics[0];
  }, [metrics]);

  const factorBars = useMemo(() => {
    if (!strategy?.factor_weights) return [];
    return Object.entries(strategy.factor_weights).map(([key, value]) => ({ name: key, value: Number(value) || 0 }));
  }, [strategy]);

  const navCategories = useMemo(() => navSeries.map((_, index) => `${index + 1}`), [navSeries]);

  async function handleSubscribe() {
    if (!userId) {
      window.alert('请先登录后再订阅策略');
      return;
    }
    await subscribeApi.triggerAsync(`/strategy-market/${id}/subscribe`, { method: 'POST' }, { user_id: userId });
  }

  async function handleReview() {
    if (!userId) {
      window.alert('请先登录后再提交评价');
      return;
    }
    await reviewApi.triggerAsync(`/strategy-market/${id}/review`, { method: 'POST' }, { user_id: userId, rating, comment });
    setComment('');
    setRating(5);
  }

  if (detailQ.isPending) return <PageContainer><LoadingState text="加载策略详情..." /></PageContainer>;
  if (detailQ.error) return <PageContainer><ErrorState text={detailQ.error} /></PageContainer>;
  if (!strategy) return <PageContainer><p className="text-text-secondary">策略不存在</p></PageContainer>;

  const statusVariant = ['published', 'listed'].includes(strategy.status ?? '')
    ? 'success'
    : strategy.status === 'incubating'
      ? 'warning'
      : ['archived', 'deprecated', 'rejected', 'suspended'].includes(strategy.status ?? '')
        ? 'danger'
        : 'neutral';

  return (
    <PageContainer>
      <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">&larr; 返回策略超市</Link>
      <div className="flex items-center gap-3 flex-wrap mt-2">
        <h1 className="m-0">{strategy.name}</h1>
        <Badge variant={statusVariant}>{strategy.status ?? '-'}</Badge>
        <span className="text-text-secondary text-sm">作者: {strategy.author_id ?? '-'}</span>
        <span className="text-text-secondary text-sm">{strategy.subscriber_count ?? 0} 订阅</span>
        {latestIncubationMetric?.decision ? <Badge variant={latestIncubationMetric.decision === 'promote' ? 'success' : latestIncubationMetric.decision === 'halt' ? 'danger' : 'info'}>孵化决策: {latestIncubationMetric.decision}</Badge> : null}
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 })}
            className="px-3 py-1 text-sm rounded border border-primary text-primary cursor-pointer hover:bg-primary/10"
          >
            加入组合
          </button>
          <button
            onClick={handleSubscribe}
            disabled={subscribeApi.isPending || !userId}
            className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {subscribeApi.isPending ? '处理中...' : !userId ? '登录后订阅' : '订阅策略'}
          </button>
        </div>
      </div>

      {strategy.description ? <p className="text-text-secondary text-sm mt-2">{strategy.description}</p> : null}

      <div className="flex gap-0 border-b border-border mt-4">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 text-sm cursor-pointer border-b-2 ${activeTab === 'overview' ? 'border-primary text-primary font-medium' : 'border-transparent text-text-secondary hover:text-primary'}`}
        >
          策略概览
        </button>
        <button
          onClick={() => setActiveTab('tracking')}
          className={`px-4 py-2 text-sm cursor-pointer border-b-2 ${activeTab === 'tracking' ? 'border-primary text-primary font-medium' : 'border-transparent text-text-secondary hover:text-primary'}`}
        >
          实盘跟踪
        </button>
        <button
          onClick={() => setActiveTab('factory')}
          className={`px-4 py-2 text-sm cursor-pointer border-b-2 ${activeTab === 'factory' ? 'border-primary text-primary font-medium' : 'border-transparent text-text-secondary hover:text-primary'}`}
        >
          工厂审查
        </button>
      </div>

      {activeTab === 'overview' ? (
        <>
          {allMetrics ? (
            <KpiGrid cols={6}>
              <KpiCard title="总收益" value={fmtPct(allMetrics.total_return ?? 0)} change={allMetrics.total_return} />
              <KpiCard title="年化收益" value={fmtPct(allMetrics.annual_return ?? 0)} />
              <KpiCard title="Sharpe" value={fmtNum(allMetrics.sharpe_ratio ?? 0, 2)} />
              <KpiCard title="最大回撤" value={fmtPct(allMetrics.max_drawdown ?? 0)} />
              <KpiCard title="胜率" value={fmtPct(allMetrics.win_rate ?? 0)} />
              <KpiCard title="交易次数" value={allMetrics.trade_count ?? '-'} />
            </KpiGrid>
          ) : null}

          <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-4 mt-4">
            {navSeries.length > 1 ? (
              <SectionCard className="p-3 mt-0">
                <h3 className="mt-0">净值轨迹</h3>
                <LineChart categories={navCategories} series={[{ name: 'NAV', data: navSeries, color: '#1a73e8' }]} height={280} />
              </SectionCard>
            ) : null}
            <SectionCard className="p-3 mt-0">
              <h3 className="mt-0">运行摘要</h3>
              <KpiGrid cols={2}>
                <KpiCard title="孵化阶段" value={incubationAccount?.stage ?? latestIncubationMetric?.stage ?? '-'} />
                <KpiCard title="账户状态" value={incubationAccount?.status ?? '-'} />
                <KpiCard title="最新NAV" value={fmtNum(latestIncubationMetric?.nav ?? 0, 4)} />
                <KpiCard title="开放风险事件" value={openRiskEvents.length} />
                <KpiCard title="向量画像数" value={vectorProfiles.length} />
                <KpiCard title="质量评级" value={latestQualityReport?.summary?.validation_grade ?? '-'} />
              </KpiGrid>
              <div className="mt-3 flex flex-wrap gap-2 text-sm">
                {latestIncubationMetric?.decision ? (
                  <Badge variant={latestIncubationMetric.decision === 'promote' ? 'success' : latestIncubationMetric.decision === 'halt' ? 'danger' : 'warning'}>
                    最新决策: {latestIncubationMetric.decision}
                  </Badge>
                ) : null}
                {incubationQ.data?.promotion_ready ? <Badge variant="success">达到上架条件</Badge> : <Badge variant="warning">仍在孵化观察</Badge>}
                {openRiskEvents.length > 0 ? <Badge variant="danger">存在实时风控告警</Badge> : <Badge variant="neutral">无实时风控告警</Badge>}
              </div>
            </SectionCard>
          </div>

          {metrics.length > 1 ? (() => {
            const sorted = [...metrics].sort((a, b) => (a.period ?? '').localeCompare(b.period ?? ''));
            const periods = sorted.map((m) => m.period ?? '');
            const returns = sorted.map((m) => Number(m.total_return ?? 0));
            const sharpes = sorted.map((m) => Number(m.sharpe_ratio ?? 0));
            return (
              <SectionCard className="mt-4 p-3">
                <h3 className="mt-0">各期表现</h3>
                <LineChart
                  categories={periods}
                  series={[
                    { name: '总收益', data: returns, color: '#1a73e8' },
                    { name: 'Sharpe', data: sharpes, color: '#f59e0b', yAxisIndex: 1 },
                  ]}
                  height={260}
                  yAxisName="收益率"
                  y2AxisName="Sharpe"
                />
              </SectionCard>
            );
          })() : null}

          {factorBars.length > 0 ? (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">因子暴露度</h3>
              <BarChart items={factorBars.map((item) => ({ label: item.name, value: item.value, color: '#6366f1' }))} height={220} />
            </SectionCard>
          ) : null}

          <SectionCard className="mt-4 p-3">
            <h3 className="mt-0">
              用户评价
              {strategy.avg_rating != null ? <span className="text-amber-500 text-sm ml-2">{'★'.repeat(Math.round(strategy.avg_rating))} {strategy.avg_rating.toFixed(1)}</span> : null}
            </h3>

            <div className="flex gap-2 items-center mb-3">
              <select value={rating} onChange={(e) => setRating(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm">
                {[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} 星</option>)}
              </select>
              <input
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="写一条评价..."
                className="flex-1 border border-border rounded px-2 py-1 text-sm"
              />
              <button
                onClick={handleReview}
                disabled={reviewApi.isPending || !userId}
                className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
              >
                {reviewApi.isPending ? '提交中...' : !userId ? '登录后可评价' : '提交'}
              </button>
            </div>

            {reviews.length ? (
              <div className="space-y-2">
                {reviews.map((review, index) => (
                  <div key={`${review.user_id}-${review.created_at ?? index}`} className="text-sm border-b border-border pb-2">
                    <span className="text-amber-400">{'★'.repeat(review.rating)}</span>
                    <span className="text-text-secondary ml-2">{review.user_id}</span>
                    {review.comment ? <p className="mt-1 text-text-secondary">{review.comment}</p> : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-text-secondary text-sm">暂无评价</p>
            )}
          </SectionCard>
        </>
      ) : null}

      {activeTab === 'tracking' ? (
        <LiveTrackingPanel
          stats={signalStatsQ.data}
          signals={signalsQ.data}
          statsLoading={signalStatsQ.isPending}
          signalsLoading={signalsQ.isPending}
        />
      ) : null}

      {activeTab === 'factory' ? (
        <FactoryReviewPanel
          report={reviewReportQ.data ?? latestQualityReport}
          events={eventsQ.data}
          incubation={incubationQ.data}
          currentAccount={incubationAccount}
          latestMetric={latestIncubationMetric}
          incubationMetrics={incubationMetricsQ.data?.items ?? []}
          riskEvents={openRiskEvents}
          vectorProfiles={vectorProfiles}
          domainEvents={domainEvents}
          aiExperiments={aiExperimentsQ.data?.items ?? []}
          eventFilters={eventFilters}
          onEventFilterChange={(key, value) => setEventFilters((prev) => ({ ...prev, [key]: value }))}
          loading={reviewReportQ.isPending || eventsQ.isPending || incubationQ.isPending || incubationMetricsQ.isPending || riskEventsQ.isPending || vectorProfilesQ.isPending || aiExperimentsQ.isPending || domainEventsQ.isPending}
        />
      ) : null}
    </PageContainer>
  );
}

function LiveTrackingPanel({
  stats,
  signals,
  statsLoading,
  signalsLoading,
}: {
  stats: SignalStatsResponse | null | undefined;
  signals: SignalsResponse | null | undefined;
  statsLoading: boolean;
  signalsLoading: boolean;
}) {
  const st = (stats && typeof stats === 'object' ? stats : {}) as SignalStatsResponse;
  const sig = (signals && typeof signals === 'object' ? signals : {}) as SignalsResponse;
  const forwardDays = Object.keys(st.hit_rate ?? {}).map(Number).sort((a, b) => a - b);
  const icCategories = forwardDays.map((day) => `${day}D`);
  const icValues = forwardDays.map((day) => st.forward_ic?.[day] ?? 0);
  const sharpeValues = forwardDays.map((day) => st.forward_sharpe?.[day] ?? 0);

  return (
    <div className="mt-4 space-y-4">
      {statsLoading ? (
        <LoadingState text="加载信号统计..." />
      ) : (
        <>
          <KpiGrid cols={4}>
            <KpiCard title="总信号数" value={st.total_signals ?? 0} />
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`hr-${day}`} title={`${day}D 命中率`} value={fmtPct(st.hit_rate?.[day] ?? 0)} />)}
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`ic-${day}`} title={`${day}D 前向IC`} value={fmtNum(st.forward_ic?.[day] ?? 0, 4)} />)}
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`sp-${day}`} title={`${day}D 前向Sharpe`} value={fmtNum(st.forward_sharpe?.[day] ?? 0, 4)} />)}
          </KpiGrid>

          {forwardDays.length > 0 ? (
            <SectionCard className="p-3">
              <h3 className="mt-0">前向验证指标</h3>
              <DataTable
                columns={[
                  { key: 'period', label: '周期' },
                  { key: 'hit_rate', label: '命中率' },
                  { key: 'forward_ic', label: '前向IC' },
                  { key: 'forward_sharpe', label: '前向Sharpe' },
                ]}
                rows={forwardDays.map((day) => ({
                  period: `${day} 天`,
                  hit_rate: fmtPct(st.hit_rate?.[day] ?? 0),
                  forward_ic: fmtNum(st.forward_ic?.[day] ?? 0, 4),
                  forward_sharpe: fmtNum(st.forward_sharpe?.[day] ?? 0, 4),
                }))}
              />
            </SectionCard>
          ) : null}

          {icCategories.length > 1 ? (
            <SectionCard className="p-3">
              <h3 className="mt-0">前向 IC / Sharpe 趋势</h3>
              <LineChart
                categories={icCategories}
                series={[
                  { name: '前向IC', data: icValues, color: '#1a73e8' },
                  { name: '前向Sharpe', data: sharpeValues, color: '#f59e0b', yAxisIndex: 1 },
                ]}
                height={240}
                yAxisName="IC"
                y2AxisName="Sharpe"
              />
            </SectionCard>
          ) : null}
        </>
      )}

      <SectionCard className="p-3">
        <h3 className="mt-0">信号历史 {sig.subscriber === false ? <span className="text-text-secondary text-xs ml-2">(非订阅者，数据延迟1-3天)</span> : null}</h3>
        {signalsLoading ? (
          <LoadingState text="加载信号..." />
        ) : sig.signals?.length ? (
          <DataTable
            columns={[
              { key: 'signal_date', label: '日期' },
              { key: 'code', label: '代码' },
              { key: 'direction', label: '方向' },
              { key: 'score', label: '强度' },
            ]}
            rows={sig.signals.map((item) => ({
              signal_date: item.signal_date ?? '-',
              code: item.code ?? '-',
              direction: item.signal === 1 ? '买入' : item.signal === -1 ? '卖出' : '持有',
              score: fmtNum(item.score ?? 0, 2),
            }))}
          />
        ) : (
          <p className="text-text-secondary text-sm">暂无信号数据</p>
        )}
      </SectionCard>
    </div>
  );
}

function FactoryReviewPanel({
  report,
  events,
  incubation,
  currentAccount,
  latestMetric,
  incubationMetrics,
  riskEvents,
  vectorProfiles,
  domainEvents,
  aiExperiments,
  eventFilters,
  onEventFilterChange,
  loading,
}: {
  report: ReviewReportResponse | null | undefined;
  events: StrategyEventsResponse | null | undefined;
  incubation: IncubationOverviewResponse | null | undefined;
  currentAccount: IncubationAccount | null | undefined;
  latestMetric: IncubationMetric | null | undefined;
  incubationMetrics: IncubationMetric[];
  riskEvents: RiskEvent[];
  vectorProfiles: VectorProfile[];
  domainEvents: DomainEvent[];
  aiExperiments: AiExperiment[];
  eventFilters: EventFilters;
  onEventFilterChange: (key: keyof EventFilters, value: string) => void;
  loading: boolean;
}) {
  const review = (report && typeof report === 'object' ? report : {}) as ReviewReportResponse;
  const blockers = incubation?.blockers ?? [];
  const riskFlags = incubation?.risk_flags ?? [];
  const forwardRows = (incubation?.forward_returns ?? []).map((item) => ({
    label: item.label ?? '-',
    hit_rate: item.hit_rate == null ? '-' : fmtPct(item.hit_rate),
    forward_ic: item.forward_ic == null ? '-' : fmtNum(item.forward_ic, 4),
    forward_sharpe: item.forward_sharpe == null ? '-' : fmtNum(item.forward_sharpe, 4),
  }));
  const eventRows = (events?.events ?? []).map((item, index) => ({
    id: `${item.created_at ?? index}`,
    created_at: formatDateTime(item.created_at),
    transition: `${item.from_status ?? '初始'} → ${item.to_status ?? '-'}`,
    actor_id: item.actor_id ?? '-',
    reason: item.reason ?? '-',
    metadata: Object.entries(item.metadata ?? {}).map(([key, value]) => `${key}: ${String(value)}`).join(' / ') || '-',
  }));
  const metricRows = incubationMetrics.map((item) => ({
    metric_date: item.metric_date ?? '-',
    nav: fmtNum(item.nav ?? 0, 4),
    daily_return: fmtPct(item.daily_return ?? 0),
    max_drawdown: fmtPct(item.max_drawdown ?? 0),
    sharpe_ratio: fmtNum(item.sharpe_ratio ?? 0, 2),
    exposure_rate: fmtPct(item.exposure_rate ?? 0),
    alpha_decay: fmtNum(item.alpha_decay ?? 0, 3),
    drift_score: fmtNum(item.drift_score ?? 0, 3),
    decision: item.decision ?? '-',
  }));
  const riskRows = riskEvents.map((item) => ({
    detected_at: formatDateTime(item.detected_at),
    severity: item.severity ?? '-',
    event_type: item.event_type ?? '-',
    action: item.action ?? '-',
    status: item.status ?? '-',
    title: item.title ?? '-',
    reason: item.reason ?? '-',
  }));
  const profileRows = vectorProfiles.map((item) => ({
    profile_type: item.profile_type ?? '-',
    vector_method: item.vector_method ?? '-',
    metric: item.metric ?? '-',
    vector_dim: item.vector_dim ?? 0,
    backend: item.backend ?? '-',
    index_version: item.index_version ?? '-',
    signature: shortText(item.signature, 16),
  }));
  const experimentRows = aiExperiments.map((item) => ({
    experiment_id: item.experiment_id ?? '-',
    source: item.source ?? '-',
    generator_type: item.generator_type ?? '-',
    optimizer_type: item.optimizer_type ?? '-',
    status: item.status ?? '-',
    hypothesis: shortText(item.hypothesis, 28),
    created_at: formatDateTime(item.created_at),
  }));
  const domainEventRows = domainEvents.map((item) => ({
    created_at: formatDateTime(item.created_at),
    event_type: item.event_type ?? '-',
    source: item.source ?? '-',
    severity: item.severity ?? '-',
    aggregate: `${item.aggregate_type ?? '-'} / ${shortText(item.aggregate_id, 12)}`,
    payload: shortText(Object.entries(item.payload ?? {}).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48),
  }));

  if (loading) {
    return <div className="mt-4"><LoadingState text="加载工厂审查数据..." /></div>;
  }

  return (
    <div className="mt-4 space-y-4">
      <KpiGrid cols={6}>
        <KpiCard title="质量门禁" value={review.passed ? '通过' : '未通过'} />
        <KpiCard title="验证评级" value={review.summary?.validation_grade ?? incubation?.validation_grade ?? '-'} />
        <KpiCard title="Walk-Forward IC IR" value={fmtNum(review.quality_gate?.wf_ic_ir ?? 0, 4)} />
        <KpiCard title="Purged K-Fold IC" value={fmtNum(review.quality_gate?.pkf_ic ?? 0, 4)} />
        <KpiCard title="孵化信号数" value={incubation?.total_signals ?? latestMetric?.total_signals ?? 0} />
        <KpiCard title="5日命中率" value={fmtPct(incubation?.hit_rate_5d ?? latestMetric?.hit_rate_5d ?? 0)} />
      </KpiGrid>

      <SectionCard className="p-3">
        <h3 className="mt-0">工厂质检摘要</h3>
        <DataTable
          columns={[
            { key: 'item', label: '指标' },
            { key: 'value', label: '结果' },
          ]}
          rows={[
            { item: 'Bootstrap CI 下界', value: fmtNum(review.quality_gate?.bootstrap_ci_lower ?? 0, 4) },
            { item: '参数敏感性', value: fmtPct(review.quality_gate?.param_sensitivity ?? 0) },
            { item: '去重匹配类型', value: review.dedup_report?.match_type ?? '唯一候选' },
            { item: '参数相似度', value: fmtNum(review.dedup_report?.param_similarity ?? 0, 4) },
            { item: '向量相似度', value: fmtNum(review.dedup_report?.vector_similarity ?? 0, 4) },
            { item: '去重说明', value: review.dedup_report?.reason ?? '-' },
            { item: '审查来源', value: review.summary?.review_source ?? '-' },
            { item: '当前报告类型', value: review.report_type ?? '-' },
          ]}
        />
        {review.quality_gate?.reasons?.length ? (
          <div className="mt-3 text-sm text-danger">
            <div className="font-medium mb-1">未通过原因</div>
            <ul className="m-0 pl-5">
              {review.quality_gate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          </div>
        ) : null}
        {review.reports?.length ? (
          <div className="mt-3 text-sm text-text-secondary">
            <div className="font-medium mb-1">报告历史</div>
            <ul className="m-0 pl-5">
              {review.reports.map((item, index) => (
                <li key={`${item.report_type ?? 'report'}-${item.updated_at ?? index}`}>
                  {item.report_type ?? '-'} / {item.summary?.review_source ?? '-'} / {item.summary?.validation_grade ?? '-'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">孵化观察窗口</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <KpiCard title="Sharpe" value={fmtNum(incubation?.sharpe_ratio ?? latestMetric?.sharpe_ratio ?? 0, 2)} />
          <KpiCard title="最大回撤" value={fmtPct(incubation?.max_drawdown ?? latestMetric?.max_drawdown ?? 0)} />
          <KpiCard title="前向IC(5D)" value={fmtNum(incubation?.forward_ic_5d ?? latestMetric?.forward_ic_5d ?? 0, 4)} />
          <KpiCard title="前向Sharpe(5D)" value={fmtNum(incubation?.forward_sharpe_5d ?? latestMetric?.forward_sharpe_5d ?? 0, 4)} />
        </div>
        <div className="flex gap-2 flex-wrap text-sm">
          <Badge variant={incubation?.promotion_ready ? 'success' : 'warning'}>
            {incubation?.promotion_ready ? '达到上架条件' : '仍在观察中'}
          </Badge>
          <Badge variant={incubation?.deprecation_risk ? 'danger' : 'neutral'}>
            {incubation?.deprecation_risk ? '存在淘汰风险' : '暂无淘汰风险'}
          </Badge>
          {currentAccount?.account_id ? <Badge variant="info">模拟盘账户: {currentAccount.account_id}</Badge> : null}
          {latestMetric?.decision ? <Badge variant={latestMetric.decision === 'promote' ? 'success' : latestMetric.decision === 'halt' ? 'danger' : 'warning'}>最新决策: {latestMetric.decision}</Badge> : null}
        </div>
        {blockers.length ? (
          <div className="mt-3 text-sm text-text-secondary">
            <div className="font-medium mb-1">晋级阻塞项</div>
            <ul className="m-0 pl-5">
              {blockers.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {riskFlags.length ? (
          <div className="mt-3 text-sm text-danger">
            <div className="font-medium mb-1">风险提示</div>
            <ul className="m-0 pl-5">
              {riskFlags.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {forwardRows.length ? (
          <div className="mt-3">
            <DataTable
              columns={[
                { key: 'label', label: '观察窗口' },
                { key: 'hit_rate', label: '命中率' },
                { key: 'forward_ic', label: '前向IC' },
                { key: 'forward_sharpe', label: '前向Sharpe' },
              ]}
              rows={forwardRows}
            />
          </div>
        ) : null}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">模拟盘孵化指标</h3>
        {metricRows.length ? (
          <DataTable
            columns={[
              { key: 'metric_date', label: '日期' },
              { key: 'nav', label: 'NAV' },
              { key: 'daily_return', label: '日收益' },
              { key: 'max_drawdown', label: '回撤' },
              { key: 'sharpe_ratio', label: 'Sharpe' },
              { key: 'exposure_rate', label: '暴露率' },
              { key: 'alpha_decay', label: 'Alpha衰减' },
              { key: 'drift_score', label: '漂移分数' },
              { key: 'decision', label: '决策' },
            ]}
            rows={metricRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化指标沉淀</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">运行时风控事件</h3>
        {riskRows.length ? (
          <DataTable
            columns={[
              { key: 'detected_at', label: '发现时间' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'high' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'event_type', label: '事件类型' },
              { key: 'action', label: '动作' },
              { key: 'status', label: '状态' },
              { key: 'title', label: '标题' },
              { key: 'reason', label: '原因' },
            ]}
            rows={riskRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无实时风险事件</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">向量画像 / 去重画像</h3>
        {profileRows.length ? (
          <DataTable
            columns={[
              { key: 'profile_type', label: '画像类型' },
              { key: 'vector_method', label: '向量方法' },
              { key: 'metric', label: '相似度' },
              { key: 'vector_dim', label: '维度' },
              { key: 'backend', label: '后端' },
              { key: 'index_version', label: '索引版本' },
              { key: 'signature', label: '签名' },
            ]}
            rows={profileRows}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无向量画像</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">AI 生成实验</h3>
        {experimentRows.length ? (
          <DataTable
            columns={[
              { key: 'experiment_id', label: '实验ID' },
              { key: 'source', label: '来源' },
              { key: 'generator_type', label: '生成器' },
              { key: 'optimizer_type', label: '优化器' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'accepted' ? 'success' : value === 'rejected' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'hypothesis', label: '假设' },
              { key: 'created_at', label: '创建时间' },
            ]}
            rows={experimentRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无 AI 生成实验记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">领域事件流</h3>
        {domainEventRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '时间' },
              { key: 'event_type', label: '事件' },
              { key: 'source', label: '来源' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'warning' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'aggregate', label: '聚合对象' },
              { key: 'payload', label: 'Payload 摘要' },
            ]}
            rows={domainEventRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无领域事件</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">生命周期事件流</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.event_type} onChange={(e) => onEventFilterChange('event_type', e.target.value)} placeholder="事件类型" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.from_status} onChange={(e) => onEventFilterChange('from_status', e.target.value)} placeholder="起始状态" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.to_status} onChange={(e) => onEventFilterChange('to_status', e.target.value)} placeholder="目标状态" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.actor_id} onChange={(e) => onEventFilterChange('actor_id', e.target.value)} placeholder="触发方" />
          <input className="border rounded px-3 py-2 text-sm" type="date" value={eventFilters.start_time} onChange={(e) => onEventFilterChange('start_time', e.target.value)} />
          <input className="border rounded px-3 py-2 text-sm" type="date" value={eventFilters.end_time} onChange={(e) => onEventFilterChange('end_time', e.target.value)} />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.limit} onChange={(e) => onEventFilterChange('limit', e.target.value)} placeholder="返回条数" />
        </div>
        {eventRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '时间' },
              { key: 'transition', label: '状态流转' },
              { key: 'actor_id', label: '触发方' },
              { key: 'reason', label: '原因' },
              { key: 'metadata', label: 'Metadata 摘要' },
            ]}
            rows={eventRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无生命周期事件</p>
        )}
      </SectionCard>
    </div>
  );
}
