'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, DataTable } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { useCartStore } from '@/store/cart-store';
import { useAuthStore } from '@/store/auth-store';

type StrategyDetail = {
  id: string;
  name: string;
  description?: string;
  strategy_type?: string;
  status?: string;
  author_id?: string;
  subscriber_count?: number;
  avg_rating?: number;
  factor_weights?: Record<string, number>;
  metrics?: Array<{
    period?: string;
    total_return?: number;
    annual_return?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    calmar_ratio?: number;
    trade_count?: number;
  }>;
  reviews?: Array<{
    user_id: string;
    rating: number;
    comment?: string;
    created_at?: string;
  }>;
};

type DetailResponse = StrategyDetail;

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

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const detailApi = useApiMutation<DetailResponse>();
  const subscribeApi = useApiMutation();
  const reviewApi = useApiMutation();
  const signalStatsApi = useApiMutation<SignalStatsResponse>();
  const signalsApi = useApiMutation<SignalsResponse>();
  const addToCart = useCartStore((st) => st.addStrategy);
  const user = useAuthStore((st) => st.user);
  const userId = user?.id || user?.username || 'default';
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'tracking'>('overview');

  useEffect(() => {
    if (id) detailApi.trigger(`/strategy-market/${id}`);
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (id && activeTab === 'tracking') {
      signalStatsApi.trigger(`/strategy-market/${id}/signal-stats`);
      signalsApi.trigger(`/strategy-market/${id}/signals?user_id=${userId}&limit=50`);
    }
  }, [id, activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const s = useMemo(() => {
    const raw = detailApi.data;
    return (raw && typeof raw === 'object' && 'id' in raw ? raw : null) as StrategyDetail | null;
  }, [detailApi.data]);

  const allMetrics = useMemo(() => {
    if (!s?.metrics?.length) return null;
    return s.metrics.find((m) => m.period === 'all') ?? s.metrics[0];
  }, [s]);

  const factorBars = useMemo(() => {
    if (!s?.factor_weights) return [];
    return Object.entries(s.factor_weights).map(([k, v]) => ({ name: k, value: Number(v) || 0 }));
  }, [s]);

  async function handleSubscribe() {
    await subscribeApi.triggerAsync(`/strategy-market/${id}/subscribe`, { method: 'POST' }, { user_id: userId });
    detailApi.trigger(`/strategy-market/${id}`);
  }

  async function handleReview() {
    await reviewApi.triggerAsync(`/strategy-market/${id}/review`, { method: 'POST' }, { user_id: userId, rating, comment });
    setComment('');
    setRating(5);
    detailApi.trigger(`/strategy-market/${id}`);
  }

  if (detailApi.isPending) return <PageContainer><LoadingState text="加载策略详情..." /></PageContainer>;
  if (detailApi.error) return <PageContainer><ErrorState text={detailApi.error} /></PageContainer>;
  if (!s) return <PageContainer><p className="text-text-secondary">策略不存在</p></PageContainer>;

  const statusVariant = (['published', 'listed'].includes(s.status ?? '')) ? 'success'
    : s.status === 'incubating' ? 'warning'
    : (['archived', 'deprecated', 'rejected'].includes(s.status ?? '')) ? 'danger'
    : 'neutral';

  return (
    <PageContainer>
      <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">&larr; 返回策略超市</Link>
      <div className="flex items-center gap-3 flex-wrap mt-2">
        <h1 className="m-0">{s.name}</h1>
        <Badge variant={statusVariant}>{s.status}</Badge>
        <span className="text-text-secondary text-sm">作者: {s.author_id ?? '-'}</span>
        <span className="text-text-secondary text-sm">{s.subscriber_count ?? 0} 订阅</span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => addToCart({ strategyId: s.id, name: s.name, weight: 0 })}
            className="px-3 py-1 text-sm rounded border border-primary text-primary cursor-pointer hover:bg-primary/10"
          >
            加入组合
          </button>
          <button
            onClick={handleSubscribe}
            disabled={subscribeApi.isPending}
            className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {subscribeApi.isPending ? '处理中...' : '订阅策略'}
          </button>
        </div>
      </div>

      {s.description && <p className="text-text-secondary text-sm mt-2">{s.description}</p>}

      {/* Tab bar */}
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
      </div>

      {activeTab === 'overview' && (<>
      {allMetrics && (
        <KpiGrid cols={6}>
          <KpiCard title="总收益" value={fmtPct(allMetrics.total_return ?? 0)} change={allMetrics.total_return} />
          <KpiCard title="年化收益" value={fmtPct(allMetrics.annual_return ?? 0)} />
          <KpiCard title="Sharpe" value={fmtNum(allMetrics.sharpe_ratio ?? 0, 2)} />
          <KpiCard title="最大回撤" value={fmtPct(allMetrics.max_drawdown ?? 0)} />
          <KpiCard title="胜率" value={fmtPct(allMetrics.win_rate ?? 0)} />
          <KpiCard title="交易次数" value={allMetrics.trade_count ?? '-'} />
        </KpiGrid>
      )}
      {s.metrics && s.metrics.length > 1 && (() => {
        const sorted = [...s.metrics].sort((a, b) => (a.period ?? '').localeCompare(b.period ?? ''));
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
      })()}

      {factorBars.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">因子暴露度</h3>
          <BarChart
            categories={factorBars.map((f) => f.name)}
            series={[{ name: '权重', data: factorBars.map((f) => f.value), color: '#6366f1' }]}
            height={220}
          />
        </SectionCard>
      )}

      <SectionCard className="mt-4 p-3">
        <h3 className="mt-0">用户评价 {s.avg_rating != null && <span className="text-amber-500 text-sm ml-2">{'★'.repeat(Math.round(s.avg_rating))} {s.avg_rating.toFixed(1)}</span>}</h3>

        <div className="flex gap-2 items-center mb-3">
          <select value={rating} onChange={(e) => setRating(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm">
            {[5, 4, 3, 2, 1].map((v) => <option key={v} value={v}>{v} 星</option>)}
          </select>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="写一条评价..."
            className="flex-1 border border-border rounded px-2 py-1 text-sm"
          />
          <button
            onClick={handleReview}
            disabled={reviewApi.isPending}
            className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            提交
          </button>
        </div>

        {s.reviews?.length ? (
          <div className="space-y-2">
            {s.reviews.map((r, i) => (
              <div key={i} className="text-sm border-b border-border pb-2">
                <span className="text-amber-400">{'★'.repeat(r.rating)}</span>
                <span className="text-text-secondary ml-2">{r.user_id}</span>
                {r.comment && <p className="mt-1 text-text-secondary">{r.comment}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-text-secondary text-sm">暂无评价</p>
        )}
      </SectionCard>
      </>)}

      {activeTab === 'tracking' && (
        <LiveTrackingPanel
          stats={signalStatsApi.data}
          signals={signalsApi.data}
          statsLoading={signalStatsApi.isPending}
          signalsLoading={signalsApi.isPending}
        />
      )}
    </PageContainer>
  );
}

/* ── LiveTrackingPanel ── */

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

  // Build forward IC time series for chart
  const icCategories = forwardDays.map((d) => `${d}D`);
  const icValues = forwardDays.map((d) => st.forward_ic?.[d] ?? 0);
  const sharpeValues = forwardDays.map((d) => st.forward_sharpe?.[d] ?? 0);

  return (
    <div className="mt-4 space-y-4">
      {statsLoading ? (
        <LoadingState text="加载信号统计..." />
      ) : (
        <>
          <KpiGrid cols={4}>
            <KpiCard title="总信号数" value={st.total_signals ?? 0} />
            {forwardDays.slice(0, 1).map((d) => (
              <KpiCard key={`hr-${d}`} title={`${d}D 命中率`} value={fmtPct(st.hit_rate?.[d] ?? 0)} />
            ))}
            {forwardDays.slice(0, 1).map((d) => (
              <KpiCard key={`ic-${d}`} title={`${d}D 前向IC`} value={fmtNum(st.forward_ic?.[d] ?? 0, 4)} />
            ))}
            {forwardDays.slice(0, 1).map((d) => (
              <KpiCard key={`sp-${d}`} title={`${d}D 前向Sharpe`} value={fmtNum(st.forward_sharpe?.[d] ?? 0, 4)} />
            ))}
          </KpiGrid>

          {forwardDays.length > 0 && (
            <SectionCard className="p-3">
              <h3 className="mt-0">前向验证指标</h3>
              <DataTable
                columns={[
                  { key: 'period', label: '周期' },
                  { key: 'hit_rate', label: '命中率' },
                  { key: 'forward_ic', label: '前向IC' },
                  { key: 'forward_sharpe', label: '前向Sharpe' },
                ]}
                rows={forwardDays.map((d) => ({
                  period: `${d} 天`,
                  hit_rate: fmtPct(st.hit_rate?.[d] ?? 0),
                  forward_ic: fmtNum(st.forward_ic?.[d] ?? 0, 4),
                  forward_sharpe: fmtNum(st.forward_sharpe?.[d] ?? 0, 4),
                }))}
              />
            </SectionCard>
          )}

          {icCategories.length > 1 && (
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
          )}
        </>
      )}

      <SectionCard className="p-3">
        <h3 className="mt-0">信号历史 {sig.subscriber === false && <span className="text-text-secondary text-xs ml-2">(非订阅者，数据延迟1-3天)</span>}</h3>
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
            rows={sig.signals.map((s) => ({
              signal_date: s.signal_date ?? '-',
              code: s.code ?? '-',
              direction: s.signal === 1 ? '买入' : s.signal === -1 ? '卖出' : '持有',
              score: fmtNum(s.score ?? 0, 2),
            }))}
          />
        ) : (
          <p className="text-text-secondary text-sm">暂无信号数据</p>
        )}
      </SectionCard>
    </div>
  );
}