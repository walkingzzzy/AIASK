'use client';

import { SectionCard, KpiCard, KpiGrid, Badge, DataTable } from '@/components/ui';
import { LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import type {
  ReviewReportResponse,
  StrategyEventsResponse,
  IncubationOverviewResponse,
  IncubationAccount,
  IncubationMetric,
  PromotionReview,
  ProjectionSnapshot,
  RuntimeControl,
  DomainProjection,
  IncubationPipelineSnapshot,
  PaperAccount,
  PaperPosition,
  PaperAccountResponse,
  PaperNav,
  PaperOrder,
  RuntimeRiskSnapshot,
  RuntimeAlert,
  RiskEvent,
  VectorProfile,
  VectorIndexSnapshot,
  DomainEvent,
  AiExperiment,
  TaskRun,
  EventFilters,
} from '../types';

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

export type FactoryReviewPanelProps = {
  report: ReviewReportResponse | null | undefined;
  events: StrategyEventsResponse | null | undefined;
  incubation: IncubationOverviewResponse | null | undefined;
  currentAccount: IncubationAccount | null | undefined;
  latestMetric: IncubationMetric | null | undefined;
  latestPromotionReview: PromotionReview | null | undefined;
  latestProjectionSnapshot: ProjectionSnapshot | null | undefined;
  runtimeControl: RuntimeControl | null | undefined;
  domainProjection: DomainProjection | null | undefined;
  latestIncubationPipelineSnapshot: IncubationPipelineSnapshot | null | undefined;
  incubationPipelineSnapshots: IncubationPipelineSnapshot[];
  paperAccount: PaperAccount | null;
  paperPositions: PaperPosition[];
  paperOrderSummary: PaperAccountResponse['order_summary'] | null;
  latestPaperNav: PaperNav | null;
  paperOrders: PaperOrder[];
  paperNavRows: PaperNav[];
  latestRuntimeRiskSnapshot: RuntimeRiskSnapshot | null | undefined;
  runtimeAlerts: RuntimeAlert[];
  runtimeRiskSnapshots: RuntimeRiskSnapshot[];
  promotionReviews: PromotionReview[];
  incubationMetrics: IncubationMetric[];
  riskEvents: RiskEvent[];
  vectorProfiles: VectorProfile[];
  similarProfiles: VectorProfile[];
  vectorIndexSnapshots: VectorIndexSnapshot[];
  latestVectorIndexSnapshot: VectorIndexSnapshot | null | undefined;
  domainEvents: DomainEvent[];
  aiExperiments: AiExperiment[];
  taskRuns: TaskRun[];
  eventFilters: EventFilters;
  onEventFilterChange: (key: keyof EventFilters, value: string) => void;
  onRebuildProjection: () => void;
  rebuildProjectionPending: boolean;
  onRunIncubationPipeline: () => void;
  runIncubationPipelinePending: boolean;
  onRunIncubationSync: () => void;
  runIncubationSyncPending: boolean;
  onRunRiskScan: () => void;
  runRiskScanPending: boolean;
  onRunRuntimeAlertDispatch: () => void;
  runRuntimeAlertDispatchPending: boolean;
  onAckRuntimeAlert: (alertId: number) => void;
  ackRuntimeAlertPending: boolean;
  onRiskRecovery: () => void;
  riskRecoveryPending: boolean;
  loading: boolean;
};

export function FactoryReviewPanel({
  report,
  events,
  incubation,
  currentAccount,
  latestMetric,
  latestPromotionReview,
  latestProjectionSnapshot,
  runtimeControl,
  domainProjection,
  latestIncubationPipelineSnapshot,
  incubationPipelineSnapshots,
  paperAccount,
  paperPositions,
  paperOrderSummary,
  latestPaperNav,
  paperOrders,
  paperNavRows: paperNavRowsProp,
  latestRuntimeRiskSnapshot,
  runtimeAlerts,
  runtimeRiskSnapshots,
  promotionReviews,
  incubationMetrics,
  riskEvents,
  vectorProfiles,
  similarProfiles,
  vectorIndexSnapshots,
  latestVectorIndexSnapshot,
  domainEvents,
  aiExperiments,
  taskRuns,
  eventFilters,
  onEventFilterChange,
  onRebuildProjection,
  rebuildProjectionPending,
  onRunIncubationPipeline,
  runIncubationPipelinePending,
  onRunIncubationSync,
  runIncubationSyncPending,
  onRunRiskScan,
  runRiskScanPending,
  onRunRuntimeAlertDispatch,
  runRuntimeAlertDispatchPending,
  onAckRuntimeAlert,
  ackRuntimeAlertPending,
  onRiskRecovery,
  riskRecoveryPending,
  loading,
}: FactoryReviewPanelProps) {
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
  const promotionReviewRows = promotionReviews.map((item) => ({
    reviewed_at: formatDateTime(item.reviewed_at),
    status: item.status ?? '-',
    recommendation: item.recommendation ?? '-',
    score: fmtNum(item.score ?? 0, 4),
    stage: item.stage ?? '-',
    review_source: item.review_source ?? '-',
    blockers: shortText((item.blockers ?? []).join(' / ') || '-', 36),
    risk_flags: shortText((item.risk_flags ?? []).join(' / ') || '-', 36),
  }));
  const projectionRows = [
    { item: '当前状态', value: domainProjection?.current_status ?? '-' },
    { item: '快照版本', value: latestProjectionSnapshot?.aggregate_version ?? 0 },
    { item: '最近重建时间', value: formatDateTime(latestProjectionSnapshot?.rebuilt_at) },
    { item: '重建来源', value: latestProjectionSnapshot?.source ?? '-' },
    { item: '快照任务', value: latestProjectionSnapshot?.task_run_id ?? '-' },
    { item: '聚合版本', value: domainProjection?.aggregate_version ?? 0 },
    { item: '状态事件数', value: domainProjection?.status_event_count ?? 0 },
    { item: '领域事件数', value: domainProjection?.domain_event_count ?? 0 },
    { item: '开放风险数', value: domainProjection?.open_risk_count ?? 0 },
    { item: '运行控制', value: `${domainProjection?.runtime_control_mode ?? runtimeControl?.control_mode ?? 'active'} / ${domainProjection?.runtime_control_status ?? runtimeControl?.status ?? '-'}` },
    { item: '最近晋级建议', value: `${domainProjection?.latest_promotion_status ?? latestPromotionReview?.status ?? '-'} / ${domainProjection?.latest_promotion_recommendation ?? latestPromotionReview?.recommendation ?? '-'}` },
    { item: 'AI 周期数', value: domainProjection?.ai_cycle_count ?? 0 },
    { item: '运行周期数', value: domainProjection?.runtime_cycle_count ?? 0 },
    { item: '最近领域事件', value: formatDateTime(domainProjection?.last_domain_event_at) },
  ];
  const vectorIndexOverviewRows = [
    { item: '当前索引版本', value: latestVectorIndexSnapshot?.index_version ?? '-' },
    { item: '索引状态', value: latestVectorIndexSnapshot?.status ?? '-' },
    { item: '画像数', value: latestVectorIndexSnapshot?.profile_count ?? 0 },
    { item: '桶数', value: latestVectorIndexSnapshot?.bucket_count ?? 0 },
    { item: '向量维度', value: latestVectorIndexSnapshot?.vector_dim ?? 0 },
    { item: '激活时间', value: formatDateTime(latestVectorIndexSnapshot?.activated_at ?? latestVectorIndexSnapshot?.built_at) },
  ];
  const incubationPipelineOverviewRows = [
    { item: '当前阶段', value: latestIncubationPipelineSnapshot?.pipeline_stage ?? currentAccount?.stage ?? '-' },
    { item: '流水线状态', value: latestIncubationPipelineSnapshot?.pipeline_status ?? '-' },
    { item: '最新决策', value: latestIncubationPipelineSnapshot?.latest_decision ?? latestMetric?.decision ?? '-' },
    { item: '准备度', value: fmtNum(latestIncubationPipelineSnapshot?.readiness_score ?? 0, 4) },
    { item: '观察天数', value: latestIncubationPipelineSnapshot?.observed_days ?? 0 },
    { item: '晋级连击', value: latestIncubationPipelineSnapshot?.promote_streak ?? 0 },
    { item: '暂停连击', value: latestIncubationPipelineSnapshot?.halt_streak ?? 0 },
    { item: '下一动作', value: latestIncubationPipelineSnapshot?.next_action ?? '-' },
    { item: '自动评审', value: latestIncubationPipelineSnapshot?.auto_review ? '是' : '否' },
    { item: '自动晋级', value: latestIncubationPipelineSnapshot?.auto_promoted ? '是' : '否' },
    { item: '最近评估', value: formatDateTime(latestIncubationPipelineSnapshot?.evaluated_at) },
  ];
  const incubationPipelineRows = incubationPipelineSnapshots.map((item) => ({
    evaluated_at: formatDateTime(item.evaluated_at),
    pipeline_stage: item.pipeline_stage ?? '-',
    pipeline_status: item.pipeline_status ?? '-',
    readiness_score: fmtNum(item.readiness_score ?? 0, 4),
    observed_days: item.observed_days ?? 0,
    promote_streak: item.promote_streak ?? 0,
    halt_streak: item.halt_streak ?? 0,
    latest_decision: item.latest_decision ?? '-',
    next_action: item.next_action ?? '-',
    auto_review: item.auto_review ? '是' : '否',
    auto_promoted: item.auto_promoted ? '是' : '否',
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
  const paperAccountOverviewRows = [
    { item: '账户ID', value: paperAccount?.id ?? currentAccount?.account_id ?? '-' },
    { item: '账户状态', value: paperAccount?.status ?? '-' },
    { item: '孵化阶段', value: paperAccount?.incubation_stage ?? currentAccount?.stage ?? '-' },
    { item: '初始资金', value: fmtNum(paperAccount?.initial_capital ?? 0, 2) },
    { item: '当前现金', value: fmtNum(paperAccount?.current_capital ?? latestPaperNav?.cash ?? 0, 2) },
    { item: '总资产', value: fmtNum(paperAccount?.total_value ?? latestPaperNav?.total_value ?? 0, 2) },
    { item: '最新市值', value: fmtNum(latestPaperNav?.market_value ?? 0, 2) },
    { item: '可晋级', value: paperAccount?.promotion_candidate ? '是' : '否' },
    { item: '订单数', value: paperOrderSummary?.total_orders ?? 0 },
    { item: '成交数', value: paperOrderSummary?.total_trades ?? 0 },
    { item: '成交额', value: fmtNum(paperOrderSummary?.trade_amount ?? 0, 2) },
    { item: '最近NAV日', value: latestPaperNav?.nav_date ?? '-' },
  ];
  const paperPositionRows = paperPositions.map((item) => ({
    stock_code: item.stock_code ?? '-',
    quantity: item.quantity ?? 0,
    cost_price: fmtNum(item.cost_price ?? 0, 4),
    current_price: fmtNum(item.current_price ?? 0, 4),
    market_value: fmtNum(item.market_value ?? 0, 2),
    profit_rate: fmtPct(item.profit_rate ?? 0),
  }));
  const paperOrderRows = paperOrders.map((item) => ({
    signal_date: item.signal_date ?? '-',
    code: item.code ?? '-',
    direction: item.direction === 'buy' ? '买入' : item.direction === 'sell' ? '卖出' : '-',
    shares: item.shares ?? 0,
    price: fmtNum(item.price ?? 0, 4),
    status: item.status ?? '-',
    commission: fmtNum(item.commission ?? 0, 2),
    source: item.source ?? '-',
    filled_at: formatDateTime(item.filled_at),
  }));
  const paperNavTableRows = paperNavRowsProp.map((item) => ({
    nav_date: item.nav_date ?? '-',
    total_value: fmtNum(item.total_value ?? 0, 2),
    cash: fmtNum(item.cash ?? 0, 2),
    market_value: fmtNum(item.market_value ?? 0, 2),
    daily_return: fmtPct(item.daily_return ?? 0),
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
  const runtimeRiskOverviewRows = [
    { item: '风险姿态', value: latestRuntimeRiskSnapshot?.posture_level ?? '-' },
    { item: '升级级别', value: latestRuntimeRiskSnapshot?.escalation_level ?? 0 },
    { item: '控制模式', value: latestRuntimeRiskSnapshot?.control_mode ?? runtimeControl?.control_mode ?? '-' },
    { item: '开放事件数', value: latestRuntimeRiskSnapshot?.open_event_count ?? riskEvents.length },
    { item: '关键事件数', value: latestRuntimeRiskSnapshot?.critical_open_count ?? 0 },
    { item: '建议动作', value: latestRuntimeRiskSnapshot?.recommended_action ?? '-' },
    { item: '可恢复', value: latestRuntimeRiskSnapshot?.recovery_eligible ? '是' : '否' },
    { item: '最近评估', value: formatDateTime(latestRuntimeRiskSnapshot?.evaluated_at) },
  ];
  const runtimeAlertOverviewRows = [
    { item: '开放告警数', value: runtimeAlerts.filter((item) => item.status !== 'resolved').length },
    { item: '已确认数', value: runtimeAlerts.filter((item) => item.status === 'acknowledged').length },
    { item: '已解决数', value: runtimeAlerts.filter((item) => item.status === 'resolved').length },
    { item: '最高级别', value: runtimeAlerts[0]?.severity ?? '-' },
    { item: '最新分类', value: runtimeAlerts[0]?.category ?? '-' },
    { item: '最近更新时间', value: formatDateTime(runtimeAlerts[0]?.updated_at ?? runtimeAlerts[0]?.created_at) },
  ];
  const runtimeAlertRows = runtimeAlerts.map((item) => ({
    alert_id: item.alert_id ?? 0,
    created_at: formatDateTime(item.created_at),
    updated_at: formatDateTime(item.updated_at),
    severity: item.severity ?? '-',
    category: item.category ?? '-',
    status: item.status ?? '-',
    title: item.title ?? '-',
    message: item.message ?? '-',
    escalation_level: item.escalation_level ?? 0,
    acknowledged_by: item.acknowledged_by ?? '-',
    acknowledged_at: formatDateTime(item.acknowledged_at),
  }));
  const runtimeRiskSnapshotRows = runtimeRiskSnapshots.map((item) => ({
    evaluated_at: formatDateTime(item.evaluated_at),
    posture_level: item.posture_level ?? '-',
    escalation_level: item.escalation_level ?? 0,
    control_mode: item.control_mode ?? '-',
    open_event_count: item.open_event_count ?? 0,
    critical_open_count: item.critical_open_count ?? 0,
    warning_open_count: item.warning_open_count ?? 0,
    recommended_action: item.recommended_action ?? '-',
    recovery_eligible: item.recovery_eligible ? '是' : '否',
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
  const indexSnapshotRows = vectorIndexSnapshots.map((item) => ({
    built_at: formatDateTime(item.built_at ?? item.created_at),
    index_version: item.index_version ?? '-',
    status: item.status ?? '-',
    profile_count: item.profile_count ?? 0,
    bucket_count: item.bucket_count ?? 0,
    vector_dim: item.vector_dim ?? 0,
    backend: item.backend ?? '-',
    source: item.source ?? '-',
  }));
  const similarProfileRows = similarProfiles.map((item) => ({
    strategy_id: item.strategy_id ?? '-',
    profile_type: item.profile_type ?? '-',
    similarity: item.similarity == null ? '-' : fmtNum(item.similarity, 4),
    coarse_score: item.coarse_score == null ? '-' : fmtNum(item.coarse_score, 4),
    bucket_id: item.bucket_id ?? '-',
    query_bucket_id: item.query_bucket_id ?? '-',
    candidate_count: item.candidate_count ?? 0,
    retrieval_mode: item.retrieval_mode ?? '-',
    backend: item.backend ?? '-',
    index_version: item.index_version ?? '-',
    signature: shortText(item.signature, 16),
  }));
  const experimentRows = aiExperiments.map((item) => ({
    experiment_id: item.experiment_id ?? '-',
    lineage: `${shortText(item.parent_strategy_id ?? item.strategy_id, 10)} → ${shortText(item.generated_strategy_id, 10)}`,
    source: item.source ?? '-',
    generator_type: item.generator_type ?? '-',
    optimizer_type: item.optimizer_type ?? '-',
    score: item.evaluation?.committee_review?.final_score == null ? '-' : fmtNum(item.evaluation?.committee_review?.final_score, 4),
    rank: item.evaluation?.committee_review?.rank ?? '-',
    champion: item.evaluation?.committee_review?.is_champion ? '是' : '否',
    status: item.status ?? '-',
    hypothesis: shortText(item.hypothesis, 28),
    created_at: formatDateTime(item.created_at),
  }));
  const taskRunRows = taskRuns.map((item) => ({
    started_at: formatDateTime(item.started_at),
    completed_at: formatDateTime(item.completed_at),
    task_name: item.task_name ?? '-',
    task_scope: item.task_scope ?? '-',
    status: item.status ?? '-',
    trace_id: shortText(item.trace_id, 14),
    result: shortText(Object.entries(item.result ?? {}).slice(0, 4).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48),
    error: shortText(item.error ?? '-', 28),
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
        <h3 className="mt-0">运行时控制面</h3>
        <div className="flex flex-wrap gap-2 mb-3">
          <Badge variant={(runtimeControl?.control_mode ?? 'active') === 'active' ? 'success' : (runtimeControl?.control_mode ?? '').includes('halt') || (runtimeControl?.control_mode ?? '') === 'manual_stop' ? 'danger' : 'warning'}>
            控制模式: {runtimeControl?.control_mode ?? 'active'}
          </Badge>
          <Badge variant={runtimeControl?.status === 'released' ? 'success' : 'info'}>
            控制状态: {runtimeControl?.status ?? 'released'}
          </Badge>
          {runtimeControl?.source ? <Badge variant="neutral">来源: {runtimeControl.source}</Badge> : null}
          {latestPromotionReview?.recommendation ? <Badge variant={latestPromotionReview.recommendation === 'promote' ? 'success' : latestPromotionReview.recommendation === 'deprecate' ? 'danger' : 'warning'}>最近晋级建议: {latestPromotionReview.recommendation}</Badge> : null}
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={[
            { item: '触发事件', value: runtimeControl?.trigger_event_type ?? '-' },
            { item: '控制原因', value: runtimeControl?.reason ?? '-' },
            { item: '激活时间', value: formatDateTime(runtimeControl?.activated_at) },
            { item: '释放时间', value: formatDateTime(runtimeControl?.released_at) },
            { item: '控制摘要', value: shortText(Object.entries(runtimeControl?.action_summary ?? {}).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48) },
          ]}
        />
      </SectionCard>

      <SectionCard className="p-3">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="mt-0 mb-0">事件投影 / 回放视图</h3>
          <button
            onClick={onRebuildProjection}
            disabled={rebuildProjectionPending}
            className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {rebuildProjectionPending ? '重建中...' : '重建投影'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={projectionRows}
        />
      </SectionCard>

      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">孵化流水线</h3>
          <button
            type="button"
            onClick={onRunIncubationPipeline}
            disabled={runIncubationPipelinePending}
            className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {runIncubationPipelinePending ? '执行中...' : '执行流水线'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={incubationPipelineOverviewRows}
        />
        {incubationPipelineRows.length ? (
          <DataTable
            columns={[
              { key: 'evaluated_at', label: '评估时间' },
              { key: 'pipeline_stage', label: '阶段' },
              { key: 'pipeline_status', label: '状态', render: (value) => <Badge variant={value === 'ready_for_review' || value === 'promoted' ? 'success' : value === 'blocked' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'readiness_score', label: '准备度' },
              { key: 'observed_days', label: '观察天数' },
              { key: 'promote_streak', label: '晋级连击' },
              { key: 'halt_streak', label: '暂停连击' },
              { key: 'latest_decision', label: '最新决策' },
              { key: 'next_action', label: '下一动作' },
              { key: 'auto_review', label: '自动评审' },
              { key: 'auto_promoted', label: '自动晋级' },
            ]}
            rows={incubationPipelineRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化流水线快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">晋级评审记录</h3>
        {promotionReviewRows.length ? (
          <DataTable
            columns={[
              { key: 'reviewed_at', label: '评审时间' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'approved' ? 'success' : value === 'rejected' ? 'danger' : 'warning'}>{String(value ?? '-')}</Badge> },
              { key: 'recommendation', label: '建议' },
              { key: 'score', label: '评分' },
              { key: 'stage', label: '阶段' },
              { key: 'review_source', label: '来源' },
              { key: 'blockers', label: '阻塞项' },
              { key: 'risk_flags', label: '风险项' },
            ]}
            rows={promotionReviewRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无晋级评审记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">模拟盘账户 / NAV 闭环</h3>
          <button
            type="button"
            onClick={onRunIncubationSync}
            disabled={runIncubationSyncPending}
            className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
          >
            {runIncubationSyncPending ? '同步中...' : '执行孵化同步'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={paperAccountOverviewRows}
        />
        {paperNavTableRows.length ? (
          <DataTable
            columns={[
              { key: 'nav_date', label: '日期' },
              { key: 'total_value', label: '总资产' },
              { key: 'cash', label: '现金' },
              { key: 'market_value', label: '市值' },
              { key: 'daily_return', label: '日收益' },
            ]}
            rows={paperNavTableRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无模拟盘 NAV 快照</p>
        )}
        {paperPositionRows.length ? (
          <DataTable
            columns={[
              { key: 'stock_code', label: '代码' },
              { key: 'quantity', label: '持仓' },
              { key: 'cost_price', label: '成本价' },
              { key: 'current_price', label: '现价' },
              { key: 'market_value', label: '市值' },
              { key: 'profit_rate', label: '浮盈率' },
            ]}
            rows={paperPositionRows}
            pageSize={8}
          />
        ) : null}
        {paperOrderRows.length ? (
          <DataTable
            columns={[
              { key: 'signal_date', label: '信号日' },
              { key: 'code', label: '代码' },
              { key: 'direction', label: '方向' },
              { key: 'shares', label: '股数' },
              { key: 'price', label: '成交价' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'filled' ? 'success' : value === 'rejected' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'commission', label: '费用' },
              { key: 'source', label: '来源' },
              { key: 'filled_at', label: '成交时间' },
            ]}
            rows={paperOrderRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无模拟盘订单记录</p>
        )}
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
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">运行时风险姿态</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRunRiskScan}
              disabled={runRiskScanPending}
              className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
            >
              {runRiskScanPending ? '扫描中...' : '执行风控扫描'}
            </button>
            <button
              type="button"
              onClick={onRiskRecovery}
              disabled={riskRecoveryPending}
              className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
            >
              {riskRecoveryPending ? '恢复中...' : '尝试恢复'}
            </button>
          </div>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={runtimeRiskOverviewRows}
        />
        {runtimeRiskSnapshotRows.length ? (
          <DataTable
            columns={[
              { key: 'evaluated_at', label: '评估时间' },
              { key: 'posture_level', label: '姿态', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'guarded' ? 'warning' : value === 'recovering' ? 'info' : 'success'}>{String(value ?? '-')}</Badge> },
              { key: 'escalation_level', label: '升级级别' },
              { key: 'control_mode', label: '控制模式' },
              { key: 'open_event_count', label: '开放事件' },
              { key: 'critical_open_count', label: '关键事件' },
              { key: 'warning_open_count', label: '预警事件' },
              { key: 'recommended_action', label: '建议动作' },
              { key: 'recovery_eligible', label: '可恢复' },
            ]}
            rows={runtimeRiskSnapshotRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无风险姿态快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">运行态告警</h3>
          <button
            type="button"
            onClick={onRunRuntimeAlertDispatch}
            disabled={runRuntimeAlertDispatchPending}
            className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
          >
            {runRuntimeAlertDispatchPending ? '分发中...' : '重新分发告警'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={runtimeAlertOverviewRows}
        />
        {runtimeAlertRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '创建时间' },
              { key: 'updated_at', label: '更新时间' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'high' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'category', label: '分类' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'resolved' ? 'success' : value === 'acknowledged' ? 'info' : 'warning'}>{String(value ?? '-')}</Badge> },
              { key: 'title', label: '标题' },
              { key: 'message', label: '内容' },
              { key: 'escalation_level', label: '升级级别' },
              { key: 'acknowledged_by', label: '确认人' },
              { key: 'acknowledged_at', label: '确认时间' },
              {
                key: 'alert_id',
                label: '操作',
                render: (value, row) => {
                  const alertId = Number(value ?? 0);
                  const status = String(row.status ?? '');
                  if (!alertId || status === 'resolved' || status === 'acknowledged') return '-';
                  return (
                    <button
                      type="button"
                      onClick={() => onAckRuntimeAlert(alertId)}
                      disabled={ackRuntimeAlertPending}
                      className="px-2 py-1 text-xs rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
                    >
                      {ackRuntimeAlertPending ? '处理中...' : '确认'}
                    </button>
                  );
                },
              },
            ]}
            rows={runtimeAlertRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无运行态告警</p>
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
        <h3 className="mt-0">持久化向量索引</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <DataTable
            columns={[
              { key: 'item', label: '项目' },
              { key: 'value', label: '值' },
            ]}
            rows={vectorIndexOverviewRows}
          />
          <div className="rounded-lg border border-border/60 bg-surface/60 p-3 text-sm text-text-secondary">
            最近一次 ANN-like 索引快照记录聚类桶、向量维度与重建版本，用于相似策略粗召回后再精排。
          </div>
        </div>
        {indexSnapshotRows.length ? (
          <DataTable
            columns={[
              { key: 'built_at', label: '构建时间' },
              { key: 'index_version', label: '索引版本' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'active' ? 'success' : value === 'stale' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'profile_count', label: '画像数' },
              { key: 'bucket_count', label: '桶数' },
              { key: 'vector_dim', label: '维度' },
              { key: 'backend', label: '后端' },
              { key: 'source', label: '来源' },
            ]}
            rows={indexSnapshotRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无持久化向量索引快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">相似策略检索</h3>
        {similarProfileRows.length ? (
          <DataTable
            columns={[
              { key: 'strategy_id', label: '相似策略' },
              { key: 'profile_type', label: '画像类型' },
              { key: 'similarity', label: '相似度' },
              { key: 'coarse_score', label: '粗排分' },
              { key: 'bucket_id', label: '命中桶' },
              { key: 'query_bucket_id', label: '查询桶' },
              { key: 'candidate_count', label: '候选数' },
              { key: 'retrieval_mode', label: '召回模式' },
              { key: 'backend', label: '后端' },
              { key: 'index_version', label: '索引版本' },
              { key: 'signature', label: '签名' },
            ]}
            rows={similarProfileRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无相似策略命中</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">任务运行记录</h3>
        {taskRunRows.length ? (
          <DataTable
            columns={[
              { key: 'started_at', label: '开始时间' },
              { key: 'completed_at', label: '完成时间' },
              { key: 'task_name', label: '任务' },
              { key: 'task_scope', label: '范围' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'completed' ? 'success' : value === 'failed' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'trace_id', label: 'Trace' },
              { key: 'result', label: '结果摘要' },
              { key: 'error', label: '错误' },
            ]}
            rows={taskRunRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无任务运行记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">AI 生成实验</h3>
        {experimentRows.length ? (
          <DataTable
            columns={[
              { key: 'experiment_id', label: '实验ID' },
              { key: 'lineage', label: '父子策略' },
              { key: 'source', label: '来源' },
              { key: 'generator_type', label: '生成器' },
              { key: 'optimizer_type', label: '优化器' },
              { key: 'score', label: '评分' },
              { key: 'rank', label: '排序' },
              { key: 'champion', label: '冠军' },
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
