'use client';

import { useMemo } from 'react';
import { SectionCard, KpiCard, KpiGrid, Badge, DataTable, TabBar } from '@/components/ui';
import { LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  buildFactoryReviewViewModel,
  FACTORY_SECTION_TABS,
  formatDateTime,
  shortText,
} from '@/app/strategy-market/lib/factory-review-view-model';
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
  FactoryReviewSection,
} from '../types';

export type FactoryReviewPanelProps = {
  highConfidenceQualityUiEnabled: boolean;
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
  activeSection: FactoryReviewSection;
  onSectionChange: (section: FactoryReviewSection) => void;
  sectionLoading: Record<FactoryReviewSection, boolean>;
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

function qualityBadgeVariant(
  value: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong' || normalized === 'comparable_ready' || normalized === 'passed') return 'success';
  if (normalized === 'candidate') return 'info';
  if (normalized === 'mixed' || normalized === 'diagnostic_ready') return 'info';
  if (normalized === 'insufficient_evidence' || normalized === 'insufficient') return 'warning';
  if (normalized === 'weak' || normalized === 'missing') return 'danger';
  return 'neutral';
}

function qualityLabelText(value: unknown) {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong') return '强';
  if (normalized === 'mixed') return '混合';
  if (normalized === 'weak') return '弱';
  if (normalized === 'insufficient_evidence') return '证据不足';
  if (normalized === 'missing') return '缺失';
  if (normalized === 'insufficient') return '样本不足';
  if (normalized === 'candidate') return '候选';
  if (normalized === 'passed') return '通过';
  if (normalized === 'diagnostic_ready') return '诊断可用';
  if (normalized === 'comparable_ready') return '可比较';
  return normalized || '-';
}

export function FactoryReviewPanel({
  highConfidenceQualityUiEnabled,
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
  activeSection,
  onSectionChange,
  sectionLoading,
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
  const { review, summaryState, incubationState, runtimeState, vectorState, experimentState, reviewAuditRows } = useMemo(
    () =>
      buildFactoryReviewViewModel({
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
        paperNavRowsProp,
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
      }),
    [
      aiExperiments,
      currentAccount,
      domainEvents,
      domainProjection,
      events,
      incubation,
      incubationMetrics,
      incubationPipelineSnapshots,
      latestIncubationPipelineSnapshot,
      latestMetric,
      latestPaperNav,
      latestPromotionReview,
      latestProjectionSnapshot,
      latestRuntimeRiskSnapshot,
      latestVectorIndexSnapshot,
      paperAccount,
      paperNavRowsProp,
      paperOrderSummary,
      paperOrders,
      paperPositions,
      promotionReviews,
      report,
      riskEvents,
      runtimeAlerts,
      runtimeControl,
      runtimeRiskSnapshots,
      similarProfiles,
      taskRuns,
      vectorIndexSnapshots,
      vectorProfiles,
    ],
  );
  const activeSectionLoading = sectionLoading[activeSection] || loading;
  const highConfidencePanel = summaryState.highConfidencePanel;
  const incubationRecord = incubation as Record<string, unknown> | null | undefined;
  const showHighConfidencePanel = highConfidenceQualityUiEnabled && [
    highConfidencePanel.predictionQualityLabel,
    highConfidencePanel.executionQualityLabel,
    highConfidencePanel.confidenceContractStatus,
    highConfidencePanel.qualityDiagnosis,
  ].some(Boolean);
  const signalSnapshotStatus = String(
    incubationRecord?.signal_quality_snapshot
      && typeof incubationRecord.signal_quality_snapshot === 'object'
      ? (incubationRecord.signal_quality_snapshot as Record<string, unknown>).status
      : highConfidencePanel.predictionQualityLabel,
  ).trim().toLowerCase();
  const executionSnapshotStatus = String(
    incubationRecord?.execution_quality_snapshot
      && typeof incubationRecord.execution_quality_snapshot === 'object'
      ? (incubationRecord.execution_quality_snapshot as Record<string, unknown>).status
      : highConfidencePanel.executionQualityLabel,
  ).trim().toLowerCase();
  const predictionTraceLedger = (
    incubationRecord?.prediction_trace_ledger
    && typeof incubationRecord.prediction_trace_ledger === 'object'
  ) ? incubationRecord.prediction_trace_ledger as Record<string, unknown> : {};
  const traceEvidenceGapCodes = Array.isArray(predictionTraceLedger.evidence_gap_codes)
    ? predictionTraceLedger.evidence_gap_codes.map((item) => String(item))
    : [];
  const hardGateReasons = (
    incubationRecord?.hard_gate_result
    && typeof incubationRecord.hard_gate_result === 'object'
    && Array.isArray((incubationRecord.hard_gate_result as Record<string, unknown>).reasons)
  )
    ? ((incubationRecord.hard_gate_result as Record<string, unknown>).reasons as unknown[]).map((item) => String(item))
    : [];
  const traceBlockingCodes = new Set([
    'missing_actual_fill',
    'missing_position_round_trip',
    'missing_pnl_audit',
    'missing_pnl_audit_summary',
  ]);
  const promotionBlockedBySnapshots = (
    (signalSnapshotStatus && signalSnapshotStatus !== 'strong')
    || (executionSnapshotStatus && !['strong', 'passed'].includes(executionSnapshotStatus))
    || hardGateReasons.length > 0
    || traceEvidenceGapCodes.some((item) => traceBlockingCodes.has(item))
  );
  const promotionReadyBadge = Boolean(incubation?.promotion_ready) && !promotionBlockedBySnapshots;

  return (
    <div className="mt-4 space-y-4">
      <KpiGrid cols={6}>
        <KpiCard title="质量门禁" value={review == null ? '-' : review.passed ? '通过' : '未通过'} />
        <KpiCard
          title="验证评级"
          value={
            review?.summary?.effective_validation_grade
            ?? review?.summary?.validation_grade
            ?? incubation?.effective_validation_grade
            ?? incubation?.validation_grade
            ?? '-'
          }
        />
        <KpiCard title="Walk-Forward IC IR" value={fmtNum(review?.quality_gate?.wf_ic_ir, 4)} />
        <KpiCard title="Purged K-Fold IC" value={fmtNum(review?.quality_gate?.pkf_ic, 4)} />
        <KpiCard title="证据门禁" value={review?.summary?.evidence_gate_status ?? '-'} />
        <KpiCard title="池子画像" value={review?.summary?.pool_profile ?? review?.pool_profile ?? '-'} />
        <KpiCard title="孵化信号数" value={incubation?.total_signals ?? latestMetric?.total_signals ?? '-'} />
        <KpiCard title="5日命中率" value={fmtPct(incubation?.hit_rate_5d ?? latestMetric?.hit_rate_5d)} />
      </KpiGrid>

      {(
        review?.summary?.raw_validation_grade
        || review?.summary?.effective_validation_grade
        || incubation?.raw_validation_grade
        || incubation?.effective_validation_grade
      ) ? (
        <SectionCard className="p-3">
          <div className="flex gap-2 flex-wrap text-sm">
            <Badge variant="neutral">
              Raw: {review?.summary?.raw_validation_grade ?? incubation?.raw_validation_grade ?? '-'}
            </Badge>
            <Badge variant="info">
              Effective: {review?.summary?.effective_validation_grade ?? review?.summary?.validation_grade ?? incubation?.effective_validation_grade ?? incubation?.validation_grade ?? '-'}
            </Badge>
            {(review?.summary?.validation_grade_adjustment_reason ?? incubation?.validation_grade_adjustment_reason) ? (
              <Badge variant="warning">
                调整原因: {shortText(review?.summary?.validation_grade_adjustment_reason ?? incubation?.validation_grade_adjustment_reason, 28)}
              </Badge>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {showHighConfidencePanel ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="mt-0">高置信质量面板</h3>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                评审链路里同步展示预测、执行和合同状态，只做 additive 呈现，不替代现有质量门卡片。
              </p>
            </div>
            <Badge variant="info">High Confidence</Badge>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {highConfidencePanel.predictionQualityLabel ? (
              <Badge variant={qualityBadgeVariant(highConfidencePanel.predictionQualityLabel)}>
                预测质量: {qualityLabelText(highConfidencePanel.predictionQualityLabel)}
              </Badge>
            ) : null}
            {highConfidencePanel.executionQualityLabel ? (
              <Badge variant={qualityBadgeVariant(highConfidencePanel.executionQualityLabel)}>
                执行质量: {qualityLabelText(highConfidencePanel.executionQualityLabel)}
              </Badge>
            ) : null}
            {highConfidencePanel.confidenceContractStatus ? (
              <Badge variant={qualityBadgeVariant(highConfidencePanel.confidenceContractStatus)}>
                合同状态: {qualityLabelText(highConfidencePanel.confidenceContractStatus)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预测轴</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {highConfidencePanel.primarySkillLcb == null ? '-' : fmtNum(highConfidencePanel.primarySkillLcb, 4)}
              </div>
              <div className="mt-1 text-xs text-text-secondary">primary skill LCB</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">覆盖率</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {highConfidencePanel.coverageRatio == null ? '-' : fmtPct(highConfidencePanel.coverageRatio)}
              </div>
              <div className="mt-1 text-xs text-text-secondary">signal / forward coverage</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">执行轴</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {highConfidencePanel.executionConversionEfficiency == null
                  ? '-'
                  : fmtPct(highConfidencePanel.executionConversionEfficiency)}
              </div>
              <div className="mt-1 text-xs text-text-secondary">execution conversion efficiency</div>
            </div>
          </div>
          <div className="mt-3 rounded-[24px] border border-border bg-surface-alt px-4 py-3 text-sm text-text-secondary">
            {highConfidencePanel.qualityDiagnosis || '当前评审链路尚无额外高置信诊断文本，先以标签和合同状态作为参考。'}
          </div>
        </SectionCard>
      ) : null}

      <div className="overflow-x-auto">
        <TabBar tabs={FACTORY_SECTION_TABS} active={activeSection} onChange={onSectionChange} />
      </div>

      {activeSectionLoading ? (
        <SectionCard className="p-4">
          <LoadingState text="加载当前工厂分组数据..." />
        </SectionCard>
      ) : null}

      {!activeSectionLoading && activeSection === 'summary' ? (
        <>
          <SectionCard className="p-3">
            <h3 className="mt-0">工厂质检摘要</h3>
            <DataTable
              columns={[
                { key: 'item', label: '指标' },
                { key: 'value', label: '结果' },
              ]}
              rows={reviewAuditRows}
            />
            {(
              review?.run_correction?.multiple_testing_mode
              || review?.validation_profile?.profile
              || review?.position_assumption
              || review?.committee_review?.decision
              || review?.task_preference?.preference_strength
              || Number(review?.attempt_adjustment?.penalty ?? 0) > 0
              || review?.constraint_check?.constraint_violation
            ) ? (
              <div className="mt-3 flex gap-2 flex-wrap text-sm">
                {review?.run_correction?.multiple_testing_mode ? (
                  <Badge variant={review.run_correction.multiple_testing_mode === 'formal_runtime' ? 'success' : 'warning'}>
                    多重检验: {review.run_correction.multiple_testing_mode === 'formal_runtime' ? '正式论文实现' : review.run_correction.multiple_testing_mode}
                  </Badge>
                ) : null}
                {(review?.run_correction?.pbo ?? review?.quality_gate?.pbo) != null ? (
                  <Badge variant={Number(review?.run_correction?.pbo ?? review?.quality_gate?.pbo) > 0.55 ? 'danger' : 'info'}>
                    PBO {fmtNum(review?.run_correction?.pbo ?? review?.quality_gate?.pbo, 4)}
                  </Badge>
                ) : null}
                {(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue) != null ? (
                  <Badge variant={Number(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue) > 0.2 ? 'warning' : 'success'}>
                    SPA p {fmtNum(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue, 4)}
                  </Badge>
                ) : null}
                {review?.validation_profile?.profile ? (
                  <Badge variant="neutral">
                    验证画像: {review.validation_profile.profile}
                  </Badge>
                ) : null}
                {review?.committee_review?.decision ? (
                  <Badge variant={review.committee_review.decision === 'accept' ? 'success' : review.committee_review.decision === 'reject' ? 'danger' : 'warning'}>
                    评审: {review.committee_review.decision}
                    {review.committee_review.final_score != null ? ` ${fmtNum(review.committee_review.final_score, 4)}` : ''}
                  </Badge>
                ) : null}
                {review?.committee_review?.execution_score != null ? (
                  <Badge variant={Number(review.committee_review.execution_score) >= 0.5 ? 'success' : 'warning'}>
                    执行 {fmtNum(review.committee_review.execution_score, 2)}
                  </Badge>
                ) : null}
                {review?.committee_review?.capacity_score != null ? (
                  <Badge variant={Number(review.committee_review.capacity_score) >= 0.5 ? 'success' : 'warning'}>
                    容量 {fmtNum(review.committee_review.capacity_score, 2)}
                  </Badge>
                ) : null}
                {review?.committee_review?.task_alignment_score != null ? (
                  <Badge variant={Number(review.committee_review.task_alignment_score) >= 0.45 ? 'success' : 'warning'}>
                    对齐 {fmtNum(review.committee_review.task_alignment_score, 2)}
                  </Badge>
                ) : null}
                {review?.position_assumption ? (
                  <Badge variant="neutral">
                    仓位: {review.position_assumption}
                  </Badge>
                ) : null}
                {review?.task_preference?.preference_strength ? (
                  <Badge variant={review.task_preference.preference_strength === 'hard' ? 'warning' : 'info'}>
                    偏好强度: {review.task_preference.preference_strength}
                  </Badge>
                ) : null}
                {review?.task_preference?.override_applied ? (
                  <Badge variant="success">
                    证据已压过偏好
                  </Badge>
                ) : null}
                {Number(review?.attempt_adjustment?.penalty ?? 0) > 0 ? (
                  <Badge variant="warning">
                    尝试惩罚 {fmtNum(review?.attempt_adjustment?.penalty, 4)}
                  </Badge>
                ) : null}
                {review?.constraint_check?.constraint_violation ? (
                  <Badge variant="danger">
                    约束违例: {review.constraint_check.constraint_violation}
                  </Badge>
                ) : null}
              </div>
            ) : null}
            {review?.quality_gate?.reasons?.length ? (
              <div className="mt-3 text-sm text-danger">
                <div className="font-medium mb-1">未通过原因</div>
                <ul className="m-0 pl-5">
                  {review.quality_gate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              </div>
            ) : null}
            {review?.reports?.length ? (
              <div className="mt-3 text-sm text-text-secondary">
                <div className="font-medium mb-1">报告历史</div>
                <ul className="m-0 pl-5">
                  {review.reports.map((item, index) => (
                    <li key={`${item.report_type ?? 'report'}-${item.updated_at ?? index}`}>
                      {item.report_type ?? '-'} / {item.summary?.review_source ?? '-'} / {item.summary?.raw_validation_grade ?? item.summary?.validation_grade ?? '-'} → {item.summary?.effective_validation_grade ?? item.summary?.validation_grade ?? '-'}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">孵化观察窗口</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <KpiCard title="Sharpe" value={fmtNum(incubation?.sharpe_ratio ?? latestMetric?.sharpe_ratio, 2)} />
              <KpiCard title="最大回撤" value={fmtPct(incubation?.max_drawdown ?? latestMetric?.max_drawdown)} />
              <KpiCard title="前向IC(5D)" value={fmtNum(incubation?.forward_ic_5d ?? latestMetric?.forward_ic_5d, 4)} />
              <KpiCard title="前向Sharpe(5D)" value={fmtNum(incubation?.forward_sharpe_5d ?? latestMetric?.forward_sharpe_5d, 4)} />
            </div>
            <div className="flex gap-2 flex-wrap text-sm">
              <Badge variant={promotionReadyBadge ? 'success' : 'warning'}>
                {promotionReadyBadge ? '达到上架条件' : '快照/Trace 仍在观察中'}
              </Badge>
              <Badge variant={incubation?.deprecation_risk ? 'danger' : 'neutral'}>
                {incubation?.deprecation_risk ? '存在淘汰风险' : '暂无淘汰风险'}
              </Badge>
              {signalSnapshotStatus ? (
                <Badge variant={qualityBadgeVariant(signalSnapshotStatus)}>
                  Signal Snapshot: {qualityLabelText(signalSnapshotStatus)}
                </Badge>
              ) : null}
              {executionSnapshotStatus ? (
                <Badge variant={qualityBadgeVariant(executionSnapshotStatus)}>
                  Execution Snapshot: {qualityLabelText(executionSnapshotStatus)}
                </Badge>
              ) : null}
              {traceEvidenceGapCodes.length ? (
                <Badge variant="warning">
                  Trace 缺口 {traceEvidenceGapCodes.length}
                </Badge>
              ) : null}
              {currentAccount?.account_id ? <Badge variant="info">模拟盘账户: {currentAccount.account_id}</Badge> : null}
              {latestMetric?.decision ? <Badge variant={latestMetric.decision === 'promote' ? 'success' : latestMetric.decision === 'halt' ? 'danger' : 'warning'}>最新决策: {latestMetric.decision}</Badge> : null}
            </div>
            {summaryState.blockers.length ? (
              <div className="mt-3 text-sm text-text-secondary">
                <div className="font-medium mb-1">晋级阻塞项</div>
                <ul className="m-0 pl-5">
                  {summaryState.blockers.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {summaryState.riskFlags.length ? (
              <div className="mt-3 text-sm text-danger">
                <div className="font-medium mb-1">风险提示</div>
                <ul className="m-0 pl-5">
                  {summaryState.riskFlags.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {summaryState.forwardRows.length ? (
              <div className="mt-3">
                <DataTable
                  columns={[
                    { key: 'label', label: '观察窗口' },
                    { key: 'hit_rate', label: '命中率' },
                    { key: 'forward_ic', label: '前向IC' },
                    { key: 'forward_sharpe', label: '前向Sharpe' },
                  ]}
                  rows={summaryState.forwardRows}
                />
              </div>
            ) : null}
          </SectionCard>

          {summaryState.executionLineageSummaryRows.length || summaryState.executionLineageRows.length ? (
            <SectionCard className="p-3">
              <h3 className="mt-0">执行链路</h3>
              <p className="mb-3 text-sm text-text-secondary">
                把 claim-level lineage、Step-level Lineage 和 runtime action 一起放出来，方便直接核对运行态动作到底落到哪一个 trade step。
              </p>
              {summaryState.executionLineageSummaryRows.length ? (
                <DataTable
                  columns={[
                    { key: 'item', label: '项目' },
                    { key: 'value', label: '值' },
                  ]}
                  rows={summaryState.executionLineageSummaryRows}
                />
              ) : null}
              {summaryState.executionLineageRows.length ? (
                <div className="mt-3">
                  <DataTable
                    columns={[
                      { key: 'signal_date', label: '信号日' },
                      { key: 'code', label: '标的' },
                      { key: 'runtime_action_reason', label: '动作' },
                      { key: 'applied_claim_id', label: 'Claim' },
                      { key: 'applied_trade_step_id', label: 'Trade Step' },
                      { key: 'lineage_status', label: '状态' },
                      { key: 'runtime_action_source', label: '来源' },
                    ]}
                    rows={summaryState.executionLineageRows}
                    pageSize={6}
                  />
                </div>
              ) : null}
            </SectionCard>
          ) : null}

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
              rows={summaryState.projectionRows}
            />
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
            {summaryState.eventRows.length ? (
              <DataTable
                columns={[
                  { key: 'created_at', label: '时间' },
                  { key: 'transition', label: '状态流转' },
                  { key: 'actor_id', label: '触发方' },
                  { key: 'reason', label: '原因' },
                  { key: 'metadata', label: 'Metadata 摘要' },
                ]}
                rows={summaryState.eventRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无生命周期事件</p>
            )}
          </SectionCard>
        </>
      ) : null}

      {!activeSectionLoading && activeSection === 'incubation' ? (
        <>
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
              rows={incubationState.incubationPipelineOverviewRows}
            />
            {incubationState.incubationPipelineRows.length ? (
              <DataTable
                columns={[
                  { key: 'evaluated_at', label: '评估时间' },
                  { key: 'pipeline_stage', label: '阶段' },
                  { key: 'pipeline_status', label: '状态', render: (value) => <Badge variant={value === 'ready_for_review' || value === 'promoted' ? 'success' : value === 'blocked' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
                  { key: 'gate_status', label: '硬门状态' },
                  { key: 'gate_reasons', label: '硬门原因' },
                  { key: 'priority_score', label: '优先级分' },
                  { key: 'readiness_score', label: '兼容准备度' },
                  { key: 'observed_days', label: '观察天数' },
                  { key: 'promote_streak', label: '晋级连击' },
                  { key: 'halt_streak', label: '暂停连击' },
                  { key: 'latest_decision', label: '最新决策' },
                  { key: 'next_action', label: '下一动作' },
                  { key: 'auto_review', label: '自动评审' },
                  { key: 'auto_promoted', label: '自动晋级' },
                ]}
                rows={incubationState.incubationPipelineRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无孵化流水线快照</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">晋级评审记录</h3>
            {incubationState.promotionReviewRows.length ? (
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
                rows={incubationState.promotionReviewRows}
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
              rows={incubationState.paperAccountOverviewRows}
            />
            {incubationState.paperNavTableRows.length ? (
              <DataTable
                columns={[
                  { key: 'nav_date', label: '日期' },
                  { key: 'total_value', label: '总资产' },
                  { key: 'cash', label: '现金' },
                  { key: 'market_value', label: '市值' },
                  { key: 'daily_return', label: '日收益' },
                ]}
                rows={incubationState.paperNavTableRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无模拟盘 NAV 快照</p>
            )}
            {incubationState.paperPositionRows.length ? (
              <DataTable
                columns={[
                  { key: 'stock_code', label: '代码' },
                  { key: 'quantity', label: '持仓' },
                  { key: 'cost_price', label: '成本价' },
                  { key: 'current_price', label: '现价' },
                  { key: 'market_value', label: '市值' },
                  { key: 'profit_rate', label: '浮盈率' },
                ]}
                rows={incubationState.paperPositionRows}
                pageSize={8}
              />
            ) : null}
            {incubationState.paperOrderRows.length ? (
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
                rows={incubationState.paperOrderRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无模拟盘订单记录</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">模拟盘孵化指标</h3>
            {incubationState.metricRows.length ? (
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
                rows={incubationState.metricRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无孵化指标沉淀</p>
            )}
          </SectionCard>
        </>
      ) : null}

      {!activeSectionLoading && activeSection === 'runtime' ? (
        <>
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
              rows={runtimeState.runtimeRiskOverviewRows}
            />
            {runtimeState.runtimeRiskSnapshotRows.length ? (
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
                rows={runtimeState.runtimeRiskSnapshotRows}
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
              rows={runtimeState.runtimeAlertOverviewRows}
            />
            {runtimeState.runtimeAlertRows.length ? (
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
                rows={runtimeState.runtimeAlertRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无运行态告警</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">运行时风控事件</h3>
            {runtimeState.riskRows.length ? (
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
                rows={runtimeState.riskRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无实时风险事件</p>
            )}
          </SectionCard>
        </>
      ) : null}

      {!activeSectionLoading && activeSection === 'vectors' ? (
        <>
          <SectionCard className="p-3">
            <h3 className="mt-0">向量画像 / 去重画像</h3>
            {vectorState.profileRows.length ? (
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
                rows={vectorState.profileRows}
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
                rows={vectorState.vectorIndexOverviewRows}
              />
              <div className="rounded-lg border border-border/60 bg-surface/60 p-3 text-sm text-text-secondary">
                最近一次 ANN-like 索引快照记录聚类桶、向量维度与重建版本，用于相似策略粗召回后再精排。
              </div>
            </div>
            {vectorState.indexSnapshotRows.length ? (
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
                rows={vectorState.indexSnapshotRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无持久化向量索引快照</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">相似策略检索</h3>
            {vectorState.similarProfileRows.length ? (
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
                rows={vectorState.similarProfileRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无相似策略命中</p>
            )}
          </SectionCard>
        </>
      ) : null}

      {!activeSectionLoading && activeSection === 'experiments' ? (
        <>
          <SectionCard className="p-3">
            <h3 className="mt-0">任务运行记录</h3>
            {experimentState.taskRunRows.length ? (
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
                rows={experimentState.taskRunRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无任务运行记录</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">AI 生成实验</h3>
            {experimentState.experimentRows.length ? (
              <DataTable
                columns={[
                  { key: 'experiment_id', label: '实验ID' },
                  { key: 'lineage', label: '父子策略' },
                  { key: 'source', label: '来源' },
                  { key: 'generator_type', label: '生成器' },
                  { key: 'optimizer_type', label: '优化器' },
                  { key: 'score', label: '评分' },
                  { key: 'review_decision', label: '委员会决策' },
                  { key: 'review_breakdown', label: '评分拆解' },
                  { key: 'review_issues', label: '主要问题' },
                  { key: 'rank', label: '排序' },
                  { key: 'champion', label: '冠军' },
                  { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'accepted' ? 'success' : value === 'rejected' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
                  { key: 'hypothesis', label: '假设' },
                  { key: 'created_at', label: '创建时间' },
                ]}
                rows={experimentState.experimentRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无 AI 生成实验记录</p>
            )}
          </SectionCard>

          <SectionCard className="p-3">
            <h3 className="mt-0">领域事件流</h3>
            {experimentState.domainEventRows.length ? (
              <DataTable
                columns={[
                  { key: 'created_at', label: '时间' },
                  { key: 'event_type', label: '事件' },
                  { key: 'source', label: '来源' },
                  { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'warning' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
                  { key: 'aggregate', label: '聚合对象' },
                  { key: 'payload', label: 'Payload 摘要' },
                ]}
                rows={experimentState.domainEventRows}
                pageSize={8}
              />
            ) : (
              <p className="text-sm text-text-secondary">暂无领域事件</p>
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
