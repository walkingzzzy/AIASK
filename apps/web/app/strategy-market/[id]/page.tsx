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
import type {
  StrategyCore,
  StrategyDetailResponse,
  StrategyMetric,
  SignalStatsResponse,
  SignalsResponse,
  ReviewReportResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationMetric,
  IncubationPipelineSnapshot,
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
} from '../types';
import { LiveTrackingPanel } from '../components/LiveTrackingPanel';
import { FactoryReviewPanel } from '../components/FactoryReviewPanel';

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const detailQ = useApiQuery<StrategyDetailResponse | StrategyCore>(id ? `/strategy-market/${id}` : null);
  const subscribeApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const reviewApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '评价已提交' });
  const rebuildProjectionApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '事件投影已重建' });
  const runIncubationPipelineApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '孵化流水线已执行' });
  const runIncubationSyncApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '模拟盘孵化同步已执行' });
  const runRiskScanApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '风控扫描已执行' });
  const riskRecoveryApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '已发起恢复尝试' });
  const runRuntimeAlertDispatchApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '运行告警已重新分发' });
  const ackRuntimeAlertApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '告警已确认' });
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
  const paperAccountQ = useApiQuery<PaperAccountResponse>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/paper-account?limit=20` : null,
  );
  const paperOrdersQ = useApiQuery<ListResponse<PaperOrder>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/paper-orders?limit=20` : null,
  );
  const paperNavQ = useApiQuery<ListResponse<PaperNav>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/paper-nav?limit=20` : null,
  );
  const incubationPipelineQ = useApiQuery<ListResponse<IncubationPipelineSnapshot>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/incubation-pipeline?limit=10` : null,
  );
  const riskEventsQ = useApiQuery<ListResponse<RiskEvent>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/risk-events?limit=20` : null,
  );
  const riskSnapshotsQ = useApiQuery<ListResponse<RuntimeRiskSnapshot>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/risk-snapshots?limit=10` : null,
  );
  const vectorProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/vector-profiles?limit=10` : null,
  );
  const similarProfilesQ = useApiQuery<ListResponse<VectorProfile>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/vector-ann-search?limit=10` : null,
  );
  const vectorIndexSnapshotsQ = useApiQuery<ListResponse<VectorIndexSnapshot>>(
    activeTab === 'factory' ? '/strategy-market/vector-indexes/snapshots?index_name=strategy_behavior&limit=10' : null,
  );
  const aiExperimentsQ = useApiQuery<ListResponse<AiExperiment>>(
    id && activeTab === 'factory' ? `/strategy-market/ai/experiments?strategy_id=${encodeURIComponent(id)}&limit=10` : null,
  );
  const domainEventsQ = useApiQuery<ListResponse<DomainEvent>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/domain-events?limit=20` : null,
  );
  const taskRunsQ = useApiQuery<ListResponse<TaskRun>>(
    id && activeTab === 'factory' ? `/strategy-market/task-runs?strategy_id=${encodeURIComponent(id)}&limit=10` : null,
  );
  const runtimeControlQ = useApiQuery<RuntimeControl>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/runtime-control` : null,
  );
  const runtimeAlertsQ = useApiQuery<ListResponse<RuntimeAlert>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/runtime-alerts?limit=20` : null,
  );
  const promotionReviewsQ = useApiQuery<ListResponse<PromotionReview>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/promotion-reviews?limit=10` : null,
  );
  const domainProjectionQ = useApiQuery<DomainProjection>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/domain-projection?limit=100` : null,
  );
  const projectionSnapshotQ = useApiQuery<ListResponse<ProjectionSnapshot>>(
    id && activeTab === 'factory' ? `/strategy-market/${id}/domain-projection/snapshot?limit=10` : null,
  );

  /* ---------- derived data ---------- */

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
  const latestPromotionReview = promotionReviewsQ.data?.latest ?? detail?.latest_promotion_review ?? null;
  const latestProjectionSnapshot = projectionSnapshotQ.data?.latest ?? detail?.latest_projection_snapshot ?? null;
  const latestVectorIndexSnapshot = vectorIndexSnapshotsQ.data?.latest ?? detail?.latest_vector_index_snapshot ?? null;
  const latestIncubationPipelineSnapshot = incubationPipelineQ.data?.latest ?? detail?.latest_incubation_pipeline_snapshot ?? null;
  const paperAccount = paperAccountQ.data?.account ?? null;
  const paperPositions = paperAccountQ.data?.positions ?? [];
  const paperOrderSummary = paperAccountQ.data?.order_summary ?? null;
  const latestPaperNav = paperNavQ.data?.latest ?? paperAccountQ.data?.latest_nav ?? null;
  const paperOrders = paperOrdersQ.data?.items ?? [];
  const paperNavRows = paperNavQ.data?.items ?? [];
  const latestRuntimeRiskSnapshot = riskSnapshotsQ.data?.latest ?? detail?.latest_runtime_risk_snapshot ?? null;
  const runtimeControl = runtimeControlQ.data ?? detail?.runtime_control ?? null;
  const runtimeAlerts = (runtimeAlertsQ.data?.items?.length ? runtimeAlertsQ.data.items : detail?.runtime_alerts) ?? [];
  const domainProjection = domainProjectionQ.data ?? latestProjectionSnapshot?.projection ?? null;
  const openRiskEvents = (riskEventsQ.data?.items?.length ? riskEventsQ.data.items : detail?.open_risk_events) ?? [];
  const vectorProfiles = (vectorProfilesQ.data?.items?.length ? vectorProfilesQ.data.items : detail?.vector_profiles) ?? [];
  const similarProfiles = (similarProfilesQ.data?.items?.length ? similarProfilesQ.data.items : detail?.similar_vector_profiles) ?? [];
  const vectorIndexSnapshots = vectorIndexSnapshotsQ.data?.items ?? [];
  const incubationPipelineSnapshots = incubationPipelineQ.data?.items ?? [];
  const runtimeRiskSnapshots = riskSnapshotsQ.data?.items ?? [];
  const domainEvents = (domainEventsQ.data?.items?.length ? domainEventsQ.data.items : detail?.domain_events) ?? [];
  const taskRuns = (taskRunsQ.data?.items?.length ? taskRunsQ.data.items : detail?.task_runs) ?? [];

  const allMetrics = useMemo(() => {
    if (!metrics.length) return null;
    return metrics.find((m) => m.period === 'all') ?? metrics[0];
  }, [metrics]);

  const factorBars = useMemo(() => {
    if (!strategy?.factor_weights) return [];
    return Object.entries(strategy.factor_weights).map(([key, value]) => ({ name: key, value: Number(value) || 0 }));
  }, [strategy]);

  const navCategories = useMemo(() => navSeries.map((_, index) => `${index + 1}`), [navSeries]);

  /* ---------- handlers ---------- */

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

  async function handleRunIncubationPipeline() {
    if (!id) return;
    await runIncubationPipelineApi.triggerAsync(`/strategy-market/${id}/incubation-pipeline/run`, { method: 'POST' }, { auto_apply_review: true, source: 'web_detail' });
  }

  async function handleRunIncubationSync() {
    if (!id) return;
    await runIncubationSyncApi.triggerAsync(`/strategy-market/${id}/incubation-sync/run`, { method: 'POST' }, {});
  }

  async function handleRunRiskScan() {
    if (!id) return;
    await runRiskScanApi.triggerAsync(`/strategy-market/${id}/risk-scan/run`, { method: 'POST' }, { enforce_actions: true });
  }

  async function handleRiskRecovery() {
    if (!id) return;
    await riskRecoveryApi.triggerAsync(`/strategy-market/${id}/risk-recovery`, { method: 'POST' }, { source: 'web_detail' });
  }

  async function handleRunRuntimeAlertDispatch() {
    if (!id) return;
    await runRuntimeAlertDispatchApi.triggerAsync(`/strategy-market/${id}/runtime-alerts/dispatch`, { method: 'POST' }, { source: 'web_detail' });
  }

  async function handleAckRuntimeAlert(alertId: number) {
    if (!alertId) return;
    await ackRuntimeAlertApi.triggerAsync(`/strategy-market/runtime-alerts/${alertId}/ack`, { method: 'POST' }, { acknowledged_by: userId ?? 'web_detail', source: 'web_detail' });
  }

  /* ---------- early returns ---------- */

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
          latestPromotionReview={latestPromotionReview}
          latestProjectionSnapshot={latestProjectionSnapshot}
          runtimeControl={runtimeControl}
          domainProjection={domainProjection}
          latestIncubationPipelineSnapshot={latestIncubationPipelineSnapshot}
          incubationPipelineSnapshots={incubationPipelineSnapshots}
          paperAccount={paperAccount}
          paperPositions={paperPositions}
          paperOrderSummary={paperOrderSummary}
          latestPaperNav={latestPaperNav}
          paperOrders={paperOrders}
          paperNavRows={paperNavRows}
          latestRuntimeRiskSnapshot={latestRuntimeRiskSnapshot}
          runtimeAlerts={runtimeAlerts}
          runtimeRiskSnapshots={runtimeRiskSnapshots}
          promotionReviews={promotionReviewsQ.data?.items ?? []}
          incubationMetrics={incubationMetricsQ.data?.items ?? []}
          riskEvents={openRiskEvents}
          vectorProfiles={vectorProfiles}
          similarProfiles={similarProfiles}
          vectorIndexSnapshots={vectorIndexSnapshots}
          latestVectorIndexSnapshot={latestVectorIndexSnapshot}
          domainEvents={domainEvents}
          aiExperiments={aiExperimentsQ.data?.items ?? []}
          taskRuns={taskRuns}
          eventFilters={eventFilters}
          onEventFilterChange={(key, value) => setEventFilters((prev) => ({ ...prev, [key]: value }))}
          onRebuildProjection={() => rebuildProjectionApi.trigger(`/strategy-market/${id}/domain-projection/rebuild`, { method: 'POST' }, { source: 'web_detail' })}
          rebuildProjectionPending={rebuildProjectionApi.isPending}
          onRunIncubationPipeline={handleRunIncubationPipeline}
          runIncubationPipelinePending={runIncubationPipelineApi.isPending}
          onRunIncubationSync={handleRunIncubationSync}
          runIncubationSyncPending={runIncubationSyncApi.isPending}
          onRunRiskScan={handleRunRiskScan}
          runRiskScanPending={runRiskScanApi.isPending}
          onRunRuntimeAlertDispatch={handleRunRuntimeAlertDispatch}
          runRuntimeAlertDispatchPending={runRuntimeAlertDispatchApi.isPending}
          onAckRuntimeAlert={handleAckRuntimeAlert}
          ackRuntimeAlertPending={ackRuntimeAlertApi.isPending}
          onRiskRecovery={handleRiskRecovery}
          riskRecoveryPending={riskRecoveryApi.isPending}
          loading={reviewReportQ.isPending || eventsQ.isPending || incubationQ.isPending || incubationMetricsQ.isPending || paperAccountQ.isPending || paperOrdersQ.isPending || paperNavQ.isPending || incubationPipelineQ.isPending || riskEventsQ.isPending || riskSnapshotsQ.isPending || runtimeAlertsQ.isPending || vectorProfilesQ.isPending || similarProfilesQ.isPending || vectorIndexSnapshotsQ.isPending || aiExperimentsQ.isPending || domainEventsQ.isPending || taskRunsQ.isPending || runtimeControlQ.isPending || promotionReviewsQ.isPending || domainProjectionQ.isPending || projectionSnapshotQ.isPending}
        />
      ) : null}
    </PageContainer>
  );
}
