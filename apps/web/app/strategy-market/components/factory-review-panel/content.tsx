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
import {
  resolveIncubationSurface,
  resolveMarketStatusMeta,
  resolveStrategyDisplayStatus,
} from '@/app/strategy-market/lib/incubation-surface';
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
  canViewOperatorPanels,
  strategyStatus,
  ownerState,
  paperSessionState,
  report,
  presentation,
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
  const resolvedSection = canViewOperatorPanels ? activeSection : 'summary';
  const activeSectionLoading = sectionLoading[resolvedSection] || loading;
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
  const displayStatus = resolveStrategyDisplayStatus({
    strategyStatus,
    ownerState,
    paperSessionState,
  });
  const marketStatus = resolveMarketStatusMeta(strategyStatus);
  const incubationSurface = resolveIncubationSurface({
    strategyStatus,
    overview: incubation,
    account: currentAccount,
    latestMetric,
    latestPipelineSnapshot: latestIncubationPipelineSnapshot,
  });
  const showIncubationStage = !ownerState?.personal_strategy || incubationSurface.enteredIncubator;

  return (
    <div className="mt-4 space-y-4" data-testid="strategy-detail-factory-review">
      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Closure Summary</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">
              闭环状态总览
            </h3>
            <p className="mt-2 mb-0 text-sm leading-7 text-text-secondary">
              {presentation?.stage_summary || '先看当前阶段说明，再决定是否需要深入到孵化、运行时或实验明细。'}
            </p>
          </div>
          <Badge variant={canViewOperatorPanels ? 'info' : 'neutral'}>
            {canViewOperatorPanels ? '运营视图可用' : '默认用户视图'}
          </Badge>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge variant={displayStatus.variant}>{displayStatus.label}</Badge>
          {displayStatus.label !== marketStatus.label ? (
            <Badge variant={marketStatus.variant}>市场状态 · {marketStatus.label}</Badge>
          ) : null}
          {showIncubationStage ? <Badge variant={incubationSurface.stage.variant}>{incubationSurface.stage.label}</Badge> : null}
          <Badge variant={incubationSurface.promotionReady ? 'success' : 'warning'}>
            {incubationSurface.promotionReady ? '可推进晋级' : '继续孵化观察'}
          </Badge>
          <Badge variant={incubationSurface.latestDecision.variant}>
            最新决策 · {incubationSurface.latestDecision.label}
          </Badge>
          <Badge variant={incubationSurface.executionAuditGate.variant}>
            执行审计 · {incubationSurface.executionAuditGate.label}
          </Badge>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="metric-tile rounded-[22px] p-4 text-sm text-text-secondary">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">状态条</div>
            <div className="mt-2 space-y-2 text-text-primary">
              <div>市场状态：{marketStatus.label}</div>
              <div>孵化阶段：{showIncubationStage ? incubationSurface.stage.label : '未接入真实孵化'}</div>
              <div>最新决策：{incubationSurface.latestDecision.label}</div>
            </div>
          </div>
          <div className="metric-tile rounded-[22px] p-4 text-sm text-text-secondary">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">门禁与阻塞</div>
            <div className="mt-2 space-y-2 text-text-primary">
              <div>执行审计：{incubationSurface.executionAuditGate.label}</div>
              <div>阻塞项：{incubationSurface.blockerCount}</div>
              <div>风险事件：{incubationSurface.riskCount}</div>
            </div>
          </div>
          <div className="metric-tile rounded-[22px] p-4 text-sm text-text-secondary">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">建议动作</div>
            <div className="mt-2 text-text-primary">{presentation?.recommended_action || '先确认当前分区是否需要补证据，再决定是否深入运营明细。'}</div>
            <div className="mt-2 text-xs leading-6 text-text-secondary">
              {presentation?.why_watch || '关注当前阶段的证据是否足够支持下一步动作。'}
            </div>
          </div>
        </div>
      </SectionCard>

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

      {canViewOperatorPanels ? (
        <div className="overflow-x-auto">
          <TabBar tabs={FACTORY_SECTION_TABS} active={activeSection} onChange={onSectionChange} />
        </div>
      ) : (
        <SectionCard className="p-3 text-sm text-text-secondary">
          当前账号默认只展示用户视图摘要。若需要查看孵化、运行时、向量和实验的原始分区，请使用具备运营权限的账号。
        </SectionCard>
      )}

      {activeSectionLoading ? (
        <SectionCard className="p-4">
          <LoadingState text="加载当前工厂分组数据..." />
        </SectionCard>
      ) : null}

      {!activeSectionLoading && resolvedSection === 'summary' ? (
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

      {!activeSectionLoading && resolvedSection === 'incubation' ? (
        <IncubationSection
          incubationState={incubationState}
          onRunIncubationPipeline={onRunIncubationPipeline}
          runIncubationPipelinePending={runIncubationPipelinePending}
          onRunIncubationSync={onRunIncubationSync}
          runIncubationSyncPending={runIncubationSyncPending}
        />
      ) : null}

      {!activeSectionLoading && resolvedSection === 'runtime' ? (
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

      {!activeSectionLoading && resolvedSection === 'vectors' ? (
        <VectorsSection vectorState={vectorState} />
      ) : null}

      {!activeSectionLoading && resolvedSection === 'experiments' ? (
        <ExperimentsSection experimentState={experimentState} />
      ) : null}
    </div>
  );
}
