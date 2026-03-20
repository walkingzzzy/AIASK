'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { useCartStore } from '@/store/cart-store';
import { useAuthStore } from '@/store/auth-store';
import { LiveTrackingPanel } from '../components/LiveTrackingPanel';
import { FactoryReviewPanel } from '../components/FactoryReviewPanel';
import { useStrategyDetailPage } from '../hooks/use-strategy-detail-page';

function extractTraceId(text: string | null): string | null {
  const source = String(text ?? '');
  const match = source.match(/trace[_-]?[A-Za-z0-9]+/i) ?? source.match(/traceId:\s*([A-Za-z0-9_-]+)/i);
  if (!match) return null;
  return match[1] ?? match[0] ?? null;
}

function isMissingStrategyError(text: string | null): boolean {
  const source = String(text ?? '').toLowerCase();
  return source.includes('404')
    || source.includes('not_found')
    || source.includes('strategy not found')
    || source.includes('不存在')
    || source.includes('未找到');
}

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const addToCart = useCartStore((st) => st.addStrategy);
  const user = useAuthStore((st) => st.user);
  const userId = user?.id ?? user?.username ?? null;
  const {
    detailLoading,
    detailError,
    strategy,
    statusVariant,
    activeTab,
    setActiveTab,
    overview,
    trackingPanelProps,
    factoryPanelProps,
  } = useStrategyDetailPage(id ?? null, userId);

  const {
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
    promotionReady,
    rating,
    setRating,
    comment,
    setComment,
    subscribePending,
    reviewPending,
    handleSubscribe,
    handleReview,
  } = overview;

  if (detailLoading) return <PageContainer><LoadingState text="加载策略详情..." /></PageContainer>;

  const traceId = extractTraceId(detailError);
  const missingStrategy = !strategy || isMissingStrategyError(detailError);

  if (detailError || !strategy) {
    return (
      <PageContainer narrow>
        <SectionCard className="p-5">
          <div className="mb-4">
            <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">&larr; 返回策略超市</Link>
          </div>
          {missingStrategy ? (
            <EmptyState
              text="策略不存在或已下架"
              hint={`你访问的策略 ID「${id ?? '-'}」目前不可用，可能是链接无效、策略已归档，或当前环境没有这条记录。`}
              action={(
                <>
                  <Link href="/strategy-market" className="px-3 py-2 rounded border border-primary text-primary no-underline hover:bg-primary/10">
                    返回策略列表
                  </Link>
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="px-3 py-2 rounded border border-border bg-surface-alt cursor-pointer"
                  >
                    重新加载
                  </button>
                </>
              )}
            />
          ) : (
            <>
              <ErrorState
                text="策略详情暂时无法加载"
                hint="可以先返回策略超市重新选择，或稍后再试；原始接口路径和技术细节已下沉到下方折叠区。"
              />
              <div className="mt-4 flex gap-2 flex-wrap">
                <Link href="/strategy-market" className="px-3 py-2 rounded border border-primary text-primary no-underline hover:bg-primary/10">
                  返回策略列表
                </Link>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="px-3 py-2 rounded border border-border bg-surface-alt cursor-pointer"
                >
                  重新加载
                </button>
              </div>
            </>
          )}
          {detailError ? (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-text-muted">查看技术详情</summary>
              <div className="mt-2 rounded-xl border border-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
                <div>策略 ID：{id ?? '-'}</div>
                {traceId ? <div className="mt-1">Trace ID：{traceId}</div> : null}
                <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{detailError}</pre>
              </div>
            </details>
          ) : null}
        </SectionCard>
      </PageContainer>
    );
  }

  const sampleStart = strategy.sample_start_date ?? paperNavRows[0]?.nav_date ?? null;
  const sampleEnd = strategy.sample_end_date ?? paperNavRows[paperNavRows.length - 1]?.nav_date ?? null;
  const sampleWindow = sampleStart && sampleEnd ? `${sampleStart} - ${sampleEnd}` : sampleStart ?? sampleEnd ?? '-';
  const turnoverRate = latestIncubationMetric?.turnover_rate ?? null;
  const capacityValue = strategy.capacity ?? paperAccount?.total_value ?? latestPaperNav?.total_value ?? null;
  const capacityLabel = strategy.capacity_label ?? '当前模拟容量';

  /* ---------- render ---------- */

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
            disabled={subscribePending || !userId}
            className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {subscribePending ? '处理中...' : !userId ? '登录后订阅' : '订阅策略'}
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
                {promotionReady ? <Badge variant="success">达到上架条件</Badge> : <Badge variant="warning">仍在孵化观察</Badge>}
                {openRiskEvents.length > 0 ? <Badge variant="danger">存在实时风控告警</Badge> : <Badge variant="neutral">无实时风控告警</Badge>}
              </div>
            </SectionCard>
          </div>

          <SectionCard className="mt-4 p-3">
            <h3 className="mt-0">可信信息</h3>
            <KpiGrid cols={3}>
              <KpiCard title="样本期" value={sampleWindow} />
              <KpiCard title="最近换手" value={turnoverRate == null ? '-' : fmtPct(turnoverRate)} />
              <KpiCard title={capacityLabel} value={capacityValue == null ? '-' : fmtNum(capacityValue, 2)} />
            </KpiGrid>
            <div className="mt-2 text-xs text-text-secondary">
              样本期优先取策略合同字段，缺失时回退到孵化账户 NAV 区间；容量优先展示合同声明，缺失时回退到模拟盘当前总资产。
            </div>
          </SectionCard>

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
                disabled={reviewPending || !userId}
                className="px-3 py-1 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
              >
                {reviewPending ? '提交中...' : !userId ? '登录后可评价' : '提交'}
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
        <LiveTrackingPanel {...trackingPanelProps} />
      ) : null}

      {activeTab === 'factory' ? (
        <FactoryReviewPanel {...factoryPanelProps} />
      ) : null}
    </PageContainer>
  );
}
