'use client';

import { useMemo } from 'react';
import { SectionCard, KpiCard, KpiGrid, Badge, TabBar } from '@/components/ui';
import { LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  buildFactoryReviewViewModel,
  FACTORY_SECTION_TABS,
  shortText,
} from '@/app/strategy-market/lib/factory-review-view-model';
import { qualityBadgeVariant, qualityLabelText } from './helpers';
import {
  ExperimentsSection,
  IncubationSection,
  RuntimeSection,
  SummarySection,
  VectorsSection,
} from './sections';
import type { FactoryReviewPanelProps } from './types';

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
  executionAuditAcceptance,
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
  onRunExecutionAuditAcceptance,
  runExecutionAuditAcceptancePending,
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
  const showHighConfidencePanel = highConfidenceQualityUiEnabled && [
    highConfidencePanel.predictionQualityLabel,
    highConfidencePanel.executionQualityLabel,
    highConfidencePanel.confidenceContractStatus,
    highConfidencePanel.qualityDiagnosis,
  ].some(Boolean);
  const signalSnapshotStatus = String(
    incubation?.signal_quality_snapshot?.status ?? highConfidencePanel.predictionQualityLabel,
  ).trim().toLowerCase();
  const executionSnapshotStatus = String(
    incubation?.execution_quality_snapshot?.status ?? highConfidencePanel.executionQualityLabel,
  ).trim().toLowerCase();
  const traceEvidenceGapCodes = (incubation?.prediction_trace_ledger?.evidence_gap_codes ?? []).map((item) => String(item));
  const hardGateReasons = (incubation?.hard_gate_result?.reasons ?? []).map((item) => String(item));
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
        <SummarySection
          review={review}
          incubation={incubation}
          latestMetric={latestMetric}
          currentAccount={currentAccount}
        latestPromotionReview={latestPromotionReview}
        runtimeControl={runtimeControl}
        executionAuditAcceptance={executionAuditAcceptance}
        summaryState={summaryState}
        reviewAuditRows={reviewAuditRows}
        eventFilters={eventFilters}
        onEventFilterChange={onEventFilterChange}
        onRebuildProjection={onRebuildProjection}
        rebuildProjectionPending={rebuildProjectionPending}
        onRunExecutionAuditAcceptance={onRunExecutionAuditAcceptance}
        runExecutionAuditAcceptancePending={runExecutionAuditAcceptancePending}
        promotionReadyBadge={promotionReadyBadge}
        signalSnapshotStatus={signalSnapshotStatus}
        executionSnapshotStatus={executionSnapshotStatus}
          traceEvidenceGapCodes={traceEvidenceGapCodes}
        />
      ) : null}

      {!activeSectionLoading && activeSection === 'incubation' ? (
        <IncubationSection
          incubationState={incubationState}
          onRunIncubationPipeline={onRunIncubationPipeline}
          runIncubationPipelinePending={runIncubationPipelinePending}
          onRunIncubationSync={onRunIncubationSync}
          runIncubationSyncPending={runIncubationSyncPending}
        />
      ) : null}

      {!activeSectionLoading && activeSection === 'runtime' ? (
        <RuntimeSection
          runtimeState={runtimeState}
          onRunRiskScan={onRunRiskScan}
          runRiskScanPending={runRiskScanPending}
          onRiskRecovery={onRiskRecovery}
          riskRecoveryPending={riskRecoveryPending}
          onRunRuntimeAlertDispatch={onRunRuntimeAlertDispatch}
          runRuntimeAlertDispatchPending={runRuntimeAlertDispatchPending}
          onAckRuntimeAlert={onAckRuntimeAlert}
          ackRuntimeAlertPending={ackRuntimeAlertPending}
        />
      ) : null}

      {!activeSectionLoading && activeSection === 'vectors' ? (
        <VectorsSection vectorState={vectorState} />
      ) : null}

      {!activeSectionLoading && activeSection === 'experiments' ? (
        <ExperimentsSection experimentState={experimentState} />
      ) : null}
    </div>
  );
}
