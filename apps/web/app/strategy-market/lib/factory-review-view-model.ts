import { fmtNum, fmtPct } from '@/lib/data-utils';
import type {
  AiExperiment,
  DomainEvent,
  DomainProjection,
  EventFilters,
  FactoryReviewSection,
  IncubationAccount,
  IncubationMetric,
  IncubationOverviewResponse,
  IncubationPipelineSnapshot,
  PaperAccount,
  PaperAccountResponse,
  PaperNav,
  PaperOrder,
  PaperPosition,
  ProjectionSnapshot,
  PromotionReview,
  ReviewReportResponse,
  RiskEvent,
  RuntimeAlert,
  RuntimeControl,
  RuntimeRiskSnapshot,
  StrategyEventsResponse,
  TaskRun,
  VectorIndexSnapshot,
  VectorProfile,
} from '@/app/strategy-market/types';

export const FACTORY_SECTION_TABS: ReadonlyArray<{ key: FactoryReviewSection; label: string }> = [
  { key: 'summary', label: '工厂摘要' },
  { key: 'incubation', label: '孵化闭环' },
  { key: 'runtime', label: '运行风控' },
  { key: 'vectors', label: '向量检索' },
  { key: 'experiments', label: '实验事件' },
];

export function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function shortText(value: unknown, length = 12) {
  const text = String(value ?? '');
  if (!text) return '-';
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function formatObjectSummary(value: Record<string, unknown> | null | undefined, length = 48) {
  const entries = Object.entries(value ?? {}).filter(([, item]) => {
    if (item == null || item === '') return false;
    if (Array.isArray(item)) return item.length > 0;
    return true;
  });
  if (!entries.length) return '-';
  return shortText(entries.map(([key, item]) => `${key}:${Array.isArray(item) ? item.join(',') : String(item)}`).join(' / '), length);
}

function formatIssueSummary(values: Array<string | null | undefined>, length = 48) {
  const issues = values.map((item) => String(item ?? '').trim()).filter(Boolean);
  if (!issues.length) return '-';
  return shortText(issues.join(' / '), length);
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
}

function highConfidenceText(...values: unknown[]) {
  for (const value of values) {
    const text = String(value ?? '').trim().toLowerCase();
    if (text) return text;
  }
  return '';
}

function finiteOrNull(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatExecutionLineageStatus(value: unknown) {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'mapped_runtime_action') return 'mapped runtime';
  if (normalized === 'unmapped_runtime_action') return 'unmapped runtime';
  if (normalized === 'mapped_trade_step') return 'mapped step';
  if (normalized === 'claim_only') return 'claim only';
  if (normalized === 'missing') return 'missing';
  return normalized || '-';
}

type BuildFactoryReviewViewModelArgs = {
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
  paperNavRowsProp: PaperNav[];
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
};

export function buildFactoryReviewViewModel({
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
}: BuildFactoryReviewViewModelArgs) {
  const review = report && typeof report === 'object' ? report : null;
  const incubationRecord = asRecord(incubation);
  const reportSummary = asRecord((review as Record<string, unknown> | null)?.summary);
  const evidenceAlignmentAudit = asRecord((review as Record<string, unknown> | null)?.evidence_alignment_audit);
  const signalQualitySnapshot = asRecord(
    incubationRecord.signal_quality_snapshot ?? reportSummary.signal_quality_snapshot,
  );
  const executionQualitySnapshot = asRecord(
    incubationRecord.execution_quality_snapshot ?? reportSummary.execution_quality_snapshot,
  );
  const predictionTraceLedger = asRecord(
    incubationRecord.prediction_trace_ledger ?? reportSummary.prediction_trace_ledger,
  );
  const signalQuality = asRecord(
    incubationRecord.signal_quality ?? reportSummary.signal_quality ?? signalQualitySnapshot,
  );
  const executionQuality = asRecord(
    incubationRecord.execution_quality ?? reportSummary.execution_quality ?? executionQualitySnapshot,
  );
  const executionAudit = asRecord(executionQuality.audit);
  const executionDiagnostics = asRecord(incubationRecord.execution_diagnostics);
  const semanticLineage = asRecord(incubationRecord.semantic_lineage);
  const executionLineage = asRecord(incubationRecord.execution_lineage);
  const runtimePlaybookProvenance = asRecord(
    incubationRecord.runtime_playbook_provenance ?? semanticLineage.runtime_playbook_provenance,
  );
  const hardGateResult = asRecord(
    latestIncubationPipelineSnapshot?.hard_gate_result ?? incubationRecord.hard_gate_result,
  );
  const semanticClaimCount = Object.keys(asRecord(asRecord(semanticLineage.claim_to_trade_plan_map).claim_to_trade_step_ids)).length;
  const semanticTradeStepCount = Object.keys(asRecord(asRecord(semanticLineage.trade_plan_to_dsl_map).trade_step_to_dsl_sections)).length;
  const executionLineageSummaryRows = [
    {
      item: 'Claim-level Lineage',
      value: `${executionLineage.claim_count ?? semanticClaimCount ?? 0} claims`,
    },
    {
      item: 'Step-level Lineage',
      value: `${executionLineage.trade_step_count ?? executionLineage.mapped_trade_step_count ?? semanticTradeStepCount ?? 0} steps`,
    },
    {
      item: 'Runtime Actions',
      value: `${executionLineage.runtime_action_count ?? 0} / unmapped ${executionLineage.unmapped_runtime_action_count ?? 0}`,
    },
    {
      item: 'Lineage 状态',
      value: formatObjectSummary(asRecord(executionLineage.lineage_status_counts), 56),
    },
    {
      item: 'Reason 分布',
      value: formatObjectSummary(asRecord(executionLineage.runtime_action_reason_counts), 56),
    },
  ].filter((row) => row.value !== '-' && row.value !== '0 claims' && row.value !== '0 steps');
  const executionLineageRows = asRecordArray(executionLineage.recent_runtime_actions).map((item) => ({
    signal_date: String(item.signal_date ?? '-'),
    code: String(item.code ?? '-'),
    runtime_action_reason: String(item.runtime_action_reason ?? '-'),
    applied_claim_id: String(item.applied_claim_id ?? '-'),
    applied_trade_step_id: String(item.applied_trade_step_id ?? '-'),
    lineage_status: formatExecutionLineageStatus(item.lineage_status),
    runtime_action_source: shortText(item.runtime_action_source, 36),
  }));

  const summaryState = {
    highConfidencePanel: {
      predictionQualityLabel: highConfidenceText(
        incubationRecord.prediction_quality_label,
        reportSummary.prediction_quality_label,
        signalQualitySnapshot.status,
      ),
      executionQualityLabel: highConfidenceText(
        incubationRecord.execution_quality_label,
        reportSummary.execution_quality_label,
        executionQuality.execution_quality_label,
        executionQualitySnapshot.status,
      ),
      confidenceContractStatus: highConfidenceText(
        incubationRecord.confidence_contract_status,
        reportSummary.confidence_contract_status,
      ),
      qualityDiagnosis: String(
        incubationRecord.quality_diagnosis ?? reportSummary.quality_diagnosis ?? '',
      ).trim(),
      primarySkillLcb: finiteOrNull(signalQuality.primary_skill_lcb),
      coverageRatio: finiteOrNull(signalQuality.coverage_ratio),
      executionConversionEfficiency: finiteOrNull(
        executionQuality.execution_conversion_efficiency
          ?? executionAudit.execution_conversion_efficiency
          ?? executionQuality.nav_conversion_proxy,
      ),
    },
    blockers: incubation?.blockers ?? [],
    riskFlags: incubation?.risk_flags ?? [],
    executionLineageSummaryRows,
    executionLineageRows,
    forwardRows: (incubation?.forward_returns ?? []).map((item) => ({
      label: item.label ?? '-',
      hit_rate: item.hit_rate == null ? '-' : fmtPct(item.hit_rate),
      forward_ic: item.forward_ic == null ? '-' : fmtNum(item.forward_ic, 4),
      forward_sharpe: item.forward_sharpe == null ? '-' : fmtNum(item.forward_sharpe, 4),
    })),
    eventRows: (events?.events ?? []).map((item, index) => ({
      id: `${item.created_at ?? index}`,
      created_at: formatDateTime(item.created_at),
      transition: `${item.from_status ?? '初始'} → ${item.to_status ?? '-'}`,
      actor_id: item.actor_id ?? '-',
      reason: item.reason ?? '-',
      metadata: Object.entries(item.metadata ?? {}).map(([key, value]) => `${key}: ${String(value)}`).join(' / ') || '-',
    })),
    projectionRows: [
      { item: '当前状态', value: domainProjection?.current_status ?? '-' },
      { item: '快照版本', value: latestProjectionSnapshot?.aggregate_version ?? '-' },
      { item: '最近重建时间', value: formatDateTime(latestProjectionSnapshot?.rebuilt_at) },
      { item: '重建来源', value: latestProjectionSnapshot?.source ?? '-' },
      { item: '快照任务', value: latestProjectionSnapshot?.task_run_id ?? '-' },
      { item: '聚合版本', value: domainProjection?.aggregate_version ?? '-' },
      { item: '状态事件数', value: domainProjection?.status_event_count ?? '-' },
      { item: '领域事件数', value: domainProjection?.domain_event_count ?? '-' },
      { item: '开放风险数', value: domainProjection?.open_risk_count ?? '-' },
      {
        item: '运行控制',
        value: `${domainProjection?.runtime_control_mode ?? runtimeControl?.control_mode ?? 'active'} / ${domainProjection?.runtime_control_status ?? runtimeControl?.status ?? '-'}`,
      },
      {
        item: '最近晋级建议',
        value: `${domainProjection?.latest_promotion_status ?? latestPromotionReview?.status ?? '-'} / ${domainProjection?.latest_promotion_recommendation ?? latestPromotionReview?.recommendation ?? '-'}`,
      },
      { item: 'AI 周期数', value: domainProjection?.ai_cycle_count ?? '-' },
      { item: '运行周期数', value: domainProjection?.runtime_cycle_count ?? '-' },
      { item: '最近领域事件', value: formatDateTime(domainProjection?.last_domain_event_at) },
    ],
  };

  const incubationState = {
    promotionReviewRows: promotionReviews.map((item) => ({
      reviewed_at: formatDateTime(item.reviewed_at),
      status: item.status ?? '-',
      recommendation: item.recommendation ?? '-',
      score: fmtNum(item.score, 4),
      stage: item.stage ?? '-',
      review_source: item.review_source ?? '-',
      blockers: shortText((item.blockers ?? []).join(' / ') || '-', 36),
      risk_flags: shortText((item.risk_flags ?? []).join(' / ') || '-', 36),
    })),
    incubationPipelineOverviewRows: [
      { item: '当前阶段', value: latestIncubationPipelineSnapshot?.pipeline_stage ?? currentAccount?.stage ?? '-' },
      { item: '流水线状态', value: latestIncubationPipelineSnapshot?.pipeline_status ?? '-' },
      { item: '硬门状态', value: latestIncubationPipelineSnapshot?.gate_status ?? '-' },
      { item: '硬门原因', value: shortText((latestIncubationPipelineSnapshot?.gate_reasons ?? []).join(' / ') || '-', 48) },
      { item: '硬门结果', value: hardGateResult.passed == null ? '-' : hardGateResult.passed ? '通过' : '未通过' },
      { item: 'Signal Snapshot', value: String(signalQualitySnapshot.status ?? '-') },
      { item: 'Execution Snapshot', value: String(executionQualitySnapshot.status ?? '-') },
      {
        item: 'Trace Ledger',
        value: formatIssueSummary(
          [
            String(predictionTraceLedger.prediction_trace_id ?? ''),
            predictionTraceLedger.contract_version ? 'v2' : '',
            Array.isArray(predictionTraceLedger.evidence_gap_codes)
              ? `gaps:${predictionTraceLedger.evidence_gap_codes.length}`
              : '',
          ],
          48,
        ),
      },
      {
        item: 'Trace 缺口',
        value: formatIssueSummary(
          Array.isArray(predictionTraceLedger.evidence_gap_codes)
            ? predictionTraceLedger.evidence_gap_codes.map((item) => String(item))
            : [],
          64,
        ),
      },
      {
        item: '硬门语义',
        value: formatIssueSummary(
          [
            String(hardGateResult.pipeline_stage ?? ''),
            String(hardGateResult.signal_stage_without_execution_gate ?? ''),
            String(hardGateResult.execution_audit_gate_status ?? ''),
          ],
          48,
        ),
      },
      { item: '最新决策', value: latestIncubationPipelineSnapshot?.latest_decision ?? latestMetric?.decision ?? '-' },
      { item: '优先级分', value: fmtNum(latestIncubationPipelineSnapshot?.priority_score ?? latestIncubationPipelineSnapshot?.readiness_score, 4) },
      { item: '兼容准备度', value: fmtNum(latestIncubationPipelineSnapshot?.readiness_score, 4) },
      { item: '执行诊断模式', value: executionDiagnostics.diagnostic_only ? 'diagnostic_only' : 'hard_gate' },
      {
        item: '语义链路',
        value: formatIssueSummary(
          [
            `claims:${semanticClaimCount || 0}`,
            `steps:${semanticTradeStepCount || 0}`,
            `playbook:${Array.isArray(runtimePlaybookProvenance.derivation_labels) ? runtimePlaybookProvenance.derivation_labels.join(',') : ''}`,
            `runtime:${executionLineage.runtime_action_count ?? 0}`,
          ],
          64,
        ),
      },
      { item: '观察天数', value: latestIncubationPipelineSnapshot?.observed_days ?? '-' },
      { item: '晋级连击', value: latestIncubationPipelineSnapshot?.promote_streak ?? '-' },
      { item: '暂停连击', value: latestIncubationPipelineSnapshot?.halt_streak ?? '-' },
      { item: '下一动作', value: latestIncubationPipelineSnapshot?.next_action ?? '-' },
      { item: '自动评审', value: latestIncubationPipelineSnapshot?.auto_review ? '是' : '否' },
      { item: '自动晋级', value: latestIncubationPipelineSnapshot?.auto_promoted ? '是' : '否' },
      { item: '最近评估', value: formatDateTime(latestIncubationPipelineSnapshot?.evaluated_at) },
    ],
    incubationPipelineRows: incubationPipelineSnapshots.map((item) => ({
      evaluated_at: formatDateTime(item.evaluated_at),
      pipeline_stage: item.pipeline_stage ?? '-',
      pipeline_status: item.pipeline_status ?? '-',
      gate_status: item.gate_status ?? '-',
      gate_reasons: shortText((item.gate_reasons ?? []).join(' / ') || '-', 36),
      readiness_score: fmtNum(item.readiness_score, 4),
      priority_score: fmtNum(item.priority_score ?? item.readiness_score, 4),
      observed_days: item.observed_days ?? 0,
      promote_streak: item.promote_streak ?? 0,
      halt_streak: item.halt_streak ?? 0,
      latest_decision: item.latest_decision ?? '-',
      next_action: item.next_action ?? '-',
      auto_review: item.auto_review ? '是' : '否',
      auto_promoted: item.auto_promoted ? '是' : '否',
    })),
    metricRows: incubationMetrics.map((item) => ({
      metric_date: item.metric_date ?? '-',
      nav: fmtNum(item.nav, 4),
      daily_return: fmtPct(item.daily_return),
      max_drawdown: fmtPct(item.max_drawdown),
      sharpe_ratio: fmtNum(item.sharpe_ratio, 2),
      exposure_rate: fmtPct(item.exposure_rate),
      alpha_decay: fmtNum(item.alpha_decay, 3),
      drift_score: fmtNum(item.drift_score, 3),
      decision: item.decision ?? '-',
    })),
    paperAccountOverviewRows: [
      { item: '账户ID', value: paperAccount?.id ?? currentAccount?.account_id ?? '-' },
      { item: '账户状态', value: paperAccount?.status ?? '-' },
      { item: '孵化阶段', value: paperAccount?.incubation_stage ?? currentAccount?.stage ?? '-' },
      { item: '初始资金', value: fmtNum(paperAccount?.initial_capital, 2) },
      { item: '当前现金', value: fmtNum(paperAccount?.current_capital ?? latestPaperNav?.cash, 2) },
      { item: '总资产', value: fmtNum(paperAccount?.total_value ?? latestPaperNav?.total_value, 2) },
      { item: '最新市值', value: fmtNum(latestPaperNav?.market_value, 2) },
      { item: '可晋级', value: paperAccount?.promotion_candidate ? '是' : '否' },
      { item: '订单数', value: paperOrderSummary?.total_orders ?? '-' },
      { item: '成交数', value: paperOrderSummary?.total_trades ?? '-' },
      { item: '成交额', value: fmtNum(paperOrderSummary?.trade_amount, 2) },
      { item: '最近NAV日', value: latestPaperNav?.nav_date ?? '-' },
    ],
    paperPositionRows: paperPositions.map((item) => ({
      stock_code: item.stock_code ?? '-',
      quantity: item.quantity ?? 0,
      cost_price: fmtNum(item.cost_price, 4),
      current_price: fmtNum(item.current_price, 4),
      market_value: fmtNum(item.market_value, 2),
      profit_rate: fmtPct(item.profit_rate),
    })),
    paperOrderRows: paperOrders.map((item) => ({
      signal_date: item.signal_date ?? '-',
      code: item.code ?? '-',
      direction: item.direction === 'buy' ? '买入' : item.direction === 'sell' ? '卖出' : '-',
      shares: item.shares ?? 0,
      price: fmtNum(item.price, 4),
      status: item.status ?? '-',
      commission: fmtNum(item.commission, 2),
      source: item.source ?? '-',
      filled_at: formatDateTime(item.filled_at),
    })),
    paperNavTableRows: paperNavRowsProp.map((item) => ({
      nav_date: item.nav_date ?? '-',
      total_value: fmtNum(item.total_value, 2),
      cash: fmtNum(item.cash, 2),
      market_value: fmtNum(item.market_value, 2),
      daily_return: fmtPct(item.daily_return),
    })),
  };

  const runtimeState = {
    riskRows: riskEvents.map((item) => ({
      detected_at: formatDateTime(item.detected_at),
      severity: item.severity ?? '-',
      event_type: item.event_type ?? '-',
      action: item.action ?? '-',
      status: item.status ?? '-',
      title: item.title ?? '-',
      reason: item.reason ?? '-',
    })),
    runtimeRiskOverviewRows: [
      { item: '风险姿态', value: latestRuntimeRiskSnapshot?.posture_level ?? '-' },
      { item: '升级级别', value: latestRuntimeRiskSnapshot?.escalation_level ?? '-' },
      { item: '控制模式', value: latestRuntimeRiskSnapshot?.control_mode ?? runtimeControl?.control_mode ?? '-' },
      { item: '开放事件数', value: latestRuntimeRiskSnapshot?.open_event_count ?? riskEvents.length },
      { item: '关键事件数', value: latestRuntimeRiskSnapshot?.critical_open_count ?? '-' },
      { item: '建议动作', value: latestRuntimeRiskSnapshot?.recommended_action ?? '-' },
      { item: '可恢复', value: latestRuntimeRiskSnapshot?.recovery_eligible ? '是' : '否' },
      { item: '最近评估', value: formatDateTime(latestRuntimeRiskSnapshot?.evaluated_at) },
    ],
    runtimeAlertOverviewRows: [
      { item: '开放告警数', value: runtimeAlerts.filter((item) => item.status !== 'resolved').length },
      { item: '已确认数', value: runtimeAlerts.filter((item) => item.status === 'acknowledged').length },
      { item: '已解决数', value: runtimeAlerts.filter((item) => item.status === 'resolved').length },
      { item: '最高级别', value: runtimeAlerts[0]?.severity ?? '-' },
      { item: '最新分类', value: runtimeAlerts[0]?.category ?? '-' },
      { item: '最近更新时间', value: formatDateTime(runtimeAlerts[0]?.updated_at ?? runtimeAlerts[0]?.created_at) },
    ],
    runtimeAlertRows: runtimeAlerts.map((item) => ({
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
    })),
    runtimeRiskSnapshotRows: runtimeRiskSnapshots.map((item) => ({
      evaluated_at: formatDateTime(item.evaluated_at),
      posture_level: item.posture_level ?? '-',
      escalation_level: item.escalation_level ?? 0,
      control_mode: item.control_mode ?? '-',
      open_event_count: item.open_event_count ?? 0,
      critical_open_count: item.critical_open_count ?? 0,
      warning_open_count: item.warning_open_count ?? 0,
      recommended_action: item.recommended_action ?? '-',
      recovery_eligible: item.recovery_eligible ? '是' : '否',
    })),
  };

  const vectorState = {
    profileRows: vectorProfiles.map((item) => ({
      profile_type: item.profile_type ?? '-',
      vector_method: item.vector_method ?? '-',
      metric: item.metric ?? '-',
      vector_dim: item.vector_dim ?? 0,
      backend: item.backend ?? '-',
      index_version: item.index_version ?? '-',
      signature: shortText(item.signature, 16),
    })),
    vectorIndexOverviewRows: [
      { item: '当前索引版本', value: latestVectorIndexSnapshot?.index_version ?? '-' },
      { item: '索引状态', value: latestVectorIndexSnapshot?.status ?? '-' },
      { item: '画像数', value: latestVectorIndexSnapshot?.profile_count ?? '-' },
      { item: '桶数', value: latestVectorIndexSnapshot?.bucket_count ?? '-' },
      { item: '向量维度', value: latestVectorIndexSnapshot?.vector_dim ?? '-' },
      { item: '激活时间', value: formatDateTime(latestVectorIndexSnapshot?.activated_at ?? latestVectorIndexSnapshot?.built_at) },
    ],
    indexSnapshotRows: vectorIndexSnapshots.map((item) => ({
      built_at: formatDateTime(item.built_at ?? item.created_at),
      index_version: item.index_version ?? '-',
      status: item.status ?? '-',
      profile_count: item.profile_count ?? 0,
      bucket_count: item.bucket_count ?? 0,
      vector_dim: item.vector_dim ?? 0,
      backend: item.backend ?? '-',
      source: item.source ?? '-',
    })),
    similarProfileRows: similarProfiles.map((item) => ({
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
    })),
  };

  const experimentState = {
    experimentRows: aiExperiments.map((item) => {
      const committeeReview = (item.evaluation?.committee_review ?? {}) as NonNullable<AiExperiment['evaluation']>['committee_review'];
      const alignmentIssues = Array.isArray(committeeReview?.alignment_issues) ? committeeReview.alignment_issues : [];
      const executionIssues = Array.isArray(committeeReview?.execution_issues) ? committeeReview.execution_issues : [];
      const capacityIssues = Array.isArray(committeeReview?.capacity_issues) ? committeeReview.capacity_issues : [];
      const acceptBlockers = Array.isArray(committeeReview?.accept_blockers) ? committeeReview.accept_blockers : [];
      return {
        experiment_id: item.experiment_id ?? '-',
        lineage: `${shortText(item.parent_strategy_id ?? item.strategy_id, 10)} → ${shortText(item.generated_strategy_id, 10)}`,
        source: item.source ?? '-',
        generator_type: item.generator_type ?? '-',
        optimizer_type: item.optimizer_type ?? '-',
        score: committeeReview?.final_score == null ? '-' : fmtNum(committeeReview.final_score, 4),
        review_decision: committeeReview?.decision ?? '-',
        review_breakdown: [
          `执行 ${fmtNum(committeeReview?.execution_score, 2)}`,
          `容量 ${fmtNum(committeeReview?.capacity_score, 2)}`,
          `对齐 ${fmtNum(committeeReview?.task_alignment_score, 2)}`,
          `新颖 ${fmtNum(committeeReview?.novelty_score, 2)}`,
        ].join(' / '),
        review_issues: formatIssueSummary(
          [...alignmentIssues, ...executionIssues, ...capacityIssues, ...acceptBlockers],
          56,
        ),
        rank: committeeReview?.rank ?? '-',
        champion: committeeReview?.is_champion ? '是' : '否',
        status: item.status ?? '-',
        hypothesis: shortText(item.hypothesis, 28),
        created_at: formatDateTime(item.created_at),
      };
    }),
    taskRunRows: taskRuns.map((item) => ({
      started_at: formatDateTime(item.started_at),
      completed_at: formatDateTime(item.completed_at),
      task_name: item.task_name ?? '-',
      task_scope: item.task_scope ?? '-',
      status: item.status ?? '-',
      trace_id: shortText(item.trace_id, 14),
      result: shortText(Object.entries(item.result ?? {}).slice(0, 4).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48),
      error: shortText(item.error ?? '-', 28),
    })),
    domainEventRows: domainEvents.map((item) => ({
      created_at: formatDateTime(item.created_at),
      event_type: item.event_type ?? '-',
      source: item.source ?? '-',
      severity: item.severity ?? '-',
      aggregate: `${item.aggregate_type ?? '-'} / ${shortText(item.aggregate_id, 12)}`,
      payload: shortText(Object.entries(item.payload ?? {}).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48),
    })),
  };

  const validationProfile = review?.validation_profile ?? {};
  const constraintCheck = review?.constraint_check ?? {};
  const attemptAdjustment = review?.attempt_adjustment ?? {};
  const taskPreference = review?.task_preference ?? {};
  const committeeReview = review?.committee_review ?? {};
  const committeeAlignmentIssues = Array.isArray(committeeReview.alignment_issues) ? committeeReview.alignment_issues : [];
  const committeeExecutionIssues = Array.isArray(committeeReview.execution_issues) ? committeeReview.execution_issues : [];
  const committeeCapacityIssues = Array.isArray(committeeReview.capacity_issues) ? committeeReview.capacity_issues : [];
  const committeeAcceptBlockers = Array.isArray(committeeReview.accept_blockers) ? committeeReview.accept_blockers : [];
  const reviewAuditRows = [
    { item: 'Bootstrap CI 下界', value: fmtNum(review?.quality_gate?.bootstrap_ci_lower, 4) },
    { item: '参数敏感性', value: fmtPct(review?.quality_gate?.param_sensitivity) },
    { item: '多重检验模式', value: review?.run_correction?.multiple_testing_mode ?? review?.quality_gate?.multiple_testing_mode ?? '-' },
    { item: 'Deflated Sharpe Ratio', value: fmtNum(review?.run_correction?.deflated_sharpe_ratio ?? review?.quality_gate?.deflated_sharpe_ratio, 4) },
    { item: 'PBO', value: fmtNum(review?.run_correction?.pbo ?? review?.quality_gate?.pbo, 4) },
    { item: 'White Reality Check p-value', value: fmtNum(review?.run_correction?.white_reality_check_pvalue ?? review?.quality_gate?.white_reality_check_pvalue, 4) },
    { item: 'Hansen SPA p-value', value: fmtNum(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue, 4) },
    { item: '验证画像', value: `${validationProfile.profile ?? '-'} / ${validationProfile.validation_focus ?? '-'}` },
    { item: '主验证层', value: review?.summary?.primary_validation_layer ?? validationProfile.primary_validation_layer ?? '-' },
    { item: 'Refresh 模式', value: review?.summary?.refresh_mode ?? review?.refresh_mode ?? '-' },
    {
      item: '评审结论',
      value: formatIssueSummary([
        review?.summary?.committee_decision ?? committeeReview.decision ?? '',
        committeeReview.final_score == null ? '' : `score:${fmtNum(committeeReview.final_score, 4)}`,
        committeeReview.rank == null ? '' : `rank:${committeeReview.rank}`,
        committeeReview.is_champion ? 'champion' : '',
      ], 64),
    },
    {
      item: '评审拆解',
      value: formatIssueSummary([
        committeeReview.execution_score == null ? '' : `执行:${fmtNum(committeeReview.execution_score, 2)}`,
        committeeReview.capacity_score == null ? '' : `容量:${fmtNum(committeeReview.capacity_score, 2)}`,
        committeeReview.task_alignment_score == null ? '' : `对齐:${fmtNum(committeeReview.task_alignment_score, 2)}`,
        committeeReview.novelty_score == null ? '' : `新颖:${fmtNum(committeeReview.novelty_score, 2)}`,
      ], 64),
    },
    {
      item: '约束审计',
      value: formatIssueSummary([
        constraintCheck.constraint_violation ? `violation:${constraintCheck.constraint_violation}` : '',
        constraintCheck.intersection_ratio == null ? '' : `intersection:${fmtPct(constraintCheck.intersection_ratio)}`,
        constraintCheck.expansion_applied ? `expansion:${constraintCheck.expansion_reason ?? 'applied'}` : '',
      ], 64),
    },
    {
      item: '证据门禁',
      value: formatIssueSummary([
        String(reportSummary.evidence_gate_status ?? evidenceAlignmentAudit.market_fact_gate_status ?? ''),
        reportSummary.hard_fact_count == null ? '' : `hard:${reportSummary.hard_fact_count}`,
        reportSummary.degraded_fact_count == null ? '' : `degraded:${reportSummary.degraded_fact_count}`,
      ], 64),
    },
    {
      item: '证据债务',
      value: formatIssueSummary(
        Array.isArray(reportSummary.evidence_debt_reasons)
          ? reportSummary.evidence_debt_reasons as string[]
          : Array.isArray(evidenceAlignmentAudit.evidence_debt_reasons)
          ? evidenceAlignmentAudit.evidence_debt_reasons as string[]
          : [],
        64,
      ),
    },
    {
      item: '池子画像',
      value: formatIssueSummary([
        String(reportSummary.pool_profile ?? review?.pool_profile ?? ''),
        String(reportSummary.volatility_bucket ?? review?.volatility_bucket ?? ''),
        String(review?.liquidity_bucket ?? ''),
      ], 64),
    },
    { item: '仓位假设', value: review?.position_assumption ?? '-' },
    { item: '成本假设', value: formatObjectSummary(review?.cost_assumptions, 64) },
    { item: '显式成本拆分', value: formatObjectSummary(review?.explicit_cost_breakdown, 64) },
    { item: '隐式成本拆分', value: formatObjectSummary(review?.implicit_cost_breakdown, 64) },
    {
      item: '尝试惩罚',
      value: formatIssueSummary([
        attemptAdjustment.penalty == null ? '' : `penalty:${fmtNum(attemptAdjustment.penalty, 4)}`,
        attemptAdjustment.selection_ratio == null ? '' : `selection:${fmtPct(attemptAdjustment.selection_ratio)}`,
        attemptAdjustment.attempt_count == null ? '' : `attempts:${attemptAdjustment.attempt_count}`,
      ], 64),
    },
    {
      item: '任务偏好',
      value: formatIssueSummary([
        taskPreference.preference_strength ?? '',
        Array.isArray(taskPreference.preferred_strategy_types) && taskPreference.preferred_strategy_types.length
          ? taskPreference.preferred_strategy_types.join(',')
          : '',
        taskPreference.override_applied ? 'override' : '',
      ], 64),
    },
    { item: '偏好原因', value: taskPreference.preference_reason ?? '-' },
    {
      item: '评审问题',
      value: formatIssueSummary([
        ...committeeAlignmentIssues,
        ...committeeExecutionIssues,
        ...committeeCapacityIssues,
        ...committeeAcceptBlockers,
      ], 64),
    },
    { item: '置信合同', value: summaryState.highConfidencePanel.confidenceContractStatus || '-' },
    { item: '质量诊断', value: summaryState.highConfidencePanel.qualityDiagnosis || '-' },
    { item: '预测质量', value: summaryState.highConfidencePanel.predictionQualityLabel || '-' },
    { item: '执行质量', value: summaryState.highConfidencePanel.executionQualityLabel || '-' },
    { item: '风控来源', value: formatIssueSummary([String(reportSummary.risk_regime_fit ?? ''), String(reportSummary.stop_rule_source ?? '')], 64) },
    { item: '任务签名', value: shortText(review?.task_signature, 64) },
    { item: '去重匹配类型', value: review?.dedup_report?.match_type ?? '唯一候选' },
    { item: '参数相似度', value: fmtNum(review?.dedup_report?.param_similarity, 4) },
    { item: '向量相似度', value: fmtNum(review?.dedup_report?.vector_similarity, 4) },
    { item: '去重说明', value: review?.dedup_report?.reason ?? '-' },
    { item: '审查来源', value: review?.summary?.review_source ?? '-' },
    { item: '当前报告类型', value: review?.report_type ?? '-' },
  ];

  return {
    review,
    summaryState,
    incubationState,
    runtimeState,
    vectorState,
    experimentState,
    reviewAuditRows,
  };
}
