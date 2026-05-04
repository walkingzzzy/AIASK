'use client';

import { Badge } from '@/components/ui';
import {
  formatCountSummary,
  formatTaskLabel,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  FactoryGovernanceBacktestThresholdsByType,
  FactoryGovernanceCommitteeReview,
  FactoryGovernanceConstraintCheck,
  FactoryGovernanceDedupArtifact,
  FactoryGovernanceDedupBrief,
  FactoryGovernanceEvidenceArtifact,
  FactoryGovernanceEvidenceStrategyBrief,
  FactoryGateStageResult,
  FactoryGovernanceGateArtifact,
  FactoryGovernanceIncubationBudgetSummary,
  FactoryGovernancePlaneArtifact,
  FactoryGovernanceSubmissionArtifact,
  FactoryGovernanceStrategyBrief,
  FactoryGovernanceValidationProfile,
  FactoryPredictionTraceLedgerSummary,
  FactoryPredictionTraceSummary,
  FactoryProtocolVersionsSummary,
  FactoryRunDetailResponse,
} from '../../types';

import { FactoryMetric } from './metrics';
import {
  asTypedObject,
  formatArtifactObjectSummary,
  formatArtifactScore,
  formatArtifactValue,
  formatAttemptAdjustmentSummary,
  formatConstraintAuditSummary,
  previewBadgeVariant,
  shortArtifactText,
  toBooleanSupportEntries,
  toDisplayCountEntries,
  toDisplayText,
  toDisplayTextList,
  toReasonTopEntries,
  validationGradeBadgeVariant,
} from './formatters';
import { FactoryArtifactCard, FactoryPreviewSection } from './shared';
import {
  FactoryPredictionTraceLedgerPanel,
  toLedgerEntries,
} from './trace-ledger';

export function FactoryGovernancePlanePanel({
  detail,
}: {
  detail: FactoryRunDetailResponse;
}) {
  const governancePlane = asTypedObject<FactoryGovernancePlaneArtifact>(detail.governance_plane);
  const gateArtifact = asTypedObject<FactoryGovernanceGateArtifact>(detail.gate_artifact);
  const gateArtifactV2 = asTypedObject<FactoryGovernanceGateArtifact>(detail.gate_artifact_v2);
  const dedupArtifact = asTypedObject<FactoryGovernanceDedupArtifact>(detail.dedup_artifact);
  const submissionArtifact = asTypedObject<FactoryGovernanceSubmissionArtifact>(detail.submission_artifact);
  const governanceEvidenceArtifact = asTypedObject<FactoryGovernanceEvidenceArtifact>(detail.governance_evidence_artifact);
  const gateA = asTypedObject<FactoryGateStageResult>(
    detail.gate_a ?? gateArtifactV2.gate_a ?? governancePlane.gate_a,
  );
  const gateB = asTypedObject<FactoryGateStageResult>(
    detail.gate_b ?? gateArtifactV2.gate_b ?? governancePlane.gate_b,
  );
  const gateC = asTypedObject<FactoryGateStageResult>(
    detail.gate_c ?? gateArtifactV2.gate_c ?? governancePlane.gate_c,
  );
  const protocolVersions = asTypedObject<FactoryProtocolVersionsSummary>(
    detail.protocol_versions ?? gateArtifactV2.protocol_versions ?? governancePlane.protocol_versions,
  );
  const predictionTraceSummary = asTypedObject<FactoryPredictionTraceSummary>(
    detail.prediction_trace_summary
    ?? gateArtifactV2.prediction_trace_summary
    ?? governancePlane.prediction_trace_summary,
  );
  const predictionTraceLedger = asTypedObject<FactoryPredictionTraceLedgerSummary>(
    detail.prediction_trace_ledger
    ?? gateArtifactV2.prediction_trace_ledger
    ?? governancePlane.prediction_trace_ledger,
  );
  const sourceChain = Array.isArray(governancePlane.source_chain)
    ? governancePlane.source_chain.map((item) => String(item)).filter(Boolean)
    : [];
  const gateFailureReasons = toReasonTopEntries(gateArtifact.gate_3_failure_reason_topn);
  const submissionFailureReasons = toReasonTopEntries(submissionArtifact.gate_3_failure_reason_topn);
  const refreshModeCounts = toDisplayCountEntries(dedupArtifact.refresh_mode_counts);
  const duplicateLevelCounts = toDisplayCountEntries(dedupArtifact.duplicate_level_counts);
  const submissionLaneCounts = toDisplayCountEntries(submissionArtifact.submission_lane_counts);
  const submissionActionTypeCounts = toDisplayCountEntries(submissionArtifact.submission_action_type_counts);
  const strategyStatusCounts = toDisplayCountEntries(submissionArtifact.strategy_status_counts);
  const committeeDecisionCounts = toDisplayCountEntries(submissionArtifact.committee_decision_counts);
  const primaryValidationLayerCounts = toDisplayCountEntries(submissionArtifact.primary_validation_layer_counts);
  const validationProfileCounts = toDisplayCountEntries(submissionArtifact.validation_profile_counts);
  const constraintViolationCounts = toDisplayCountEntries(submissionArtifact.constraint_violation_counts);
  const vectorBackendCounts = toDisplayCountEntries(governanceEvidenceArtifact.vector_backend_counts);
  const extensionSupport = toBooleanSupportEntries(governanceEvidenceArtifact.extension_interface_support);
  const keptBriefs = Array.isArray(dedupArtifact.kept_briefs)
    ? (dedupArtifact.kept_briefs as FactoryGovernanceDedupBrief[])
    : [];
  const droppedBriefs = Array.isArray(dedupArtifact.dropped_briefs)
    ? (dedupArtifact.dropped_briefs as FactoryGovernanceDedupBrief[])
    : [];
  const strategyBriefs = Array.isArray(submissionArtifact.strategy_briefs)
    ? (submissionArtifact.strategy_briefs as FactoryGovernanceStrategyBrief[])
    : [];
  const strategyEvidenceBriefs = Array.isArray(governanceEvidenceArtifact.strategy_evidence_briefs)
    ? (governanceEvidenceArtifact.strategy_evidence_briefs as FactoryGovernanceEvidenceStrategyBrief[])
    : [];
  const incubationBudgetSummary = asTypedObject<FactoryGovernanceIncubationBudgetSummary>(
    submissionArtifact.incubation_budget_summary,
  );
  const incubationFamilyCounts = toDisplayCountEntries(incubationBudgetSummary.family_counts);
  const backtestThresholdsByType = asTypedObject<FactoryGovernanceBacktestThresholdsByType>(
    gateArtifact.backtest_thresholds_by_type,
  );
  const gateStageRows = [
    { label: 'Gate A', gate: gateA },
    { label: 'Gate B', gate: gateB },
    { label: 'Gate C', gate: gateC },
  ].filter(({ gate }) => Object.keys(gate).length > 0);
  const sampleTraceIds = Array.isArray(predictionTraceSummary.sample_trace_ids)
    ? predictionTraceSummary.sample_trace_ids.map((item) => String(item)).filter(Boolean)
    : [];
  const predictionTraceLedgerEntries = toLedgerEntries(predictionTraceLedger.entries);
  const hasAuditSliceCoverage = [
    submissionArtifact.constraint_check_count,
    submissionArtifact.validation_profile_count,
    submissionArtifact.event_window_config_count,
    submissionArtifact.position_assumption_count,
    submissionArtifact.cost_assumptions_count,
    submissionArtifact.attempt_adjustment_count,
    submissionArtifact.committee_review_count,
    submissionArtifact.task_signature_count,
    governanceEvidenceArtifact.constraint_check_count,
    governanceEvidenceArtifact.validation_profile_count,
  ].some((value) => Number(value ?? 0) > 0);

  const hasGovernancePlane =
    Boolean(governancePlane.available)
    || Boolean(gateArtifact.available)
    || Boolean(dedupArtifact.available)
    || Boolean(submissionArtifact.available)
    || Boolean(governanceEvidenceArtifact.available);

  if (!hasGovernancePlane) return null;

  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-medium">治理平面</div>
        <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
          <div>总契约：{formatArtifactValue(governancePlane.contract_version)}</div>
          <div>平面可用：{formatArtifactValue(governancePlane.available)}</div>
          <div>平面类型：{formatArtifactValue(governancePlane.plane)}</div>
          <div>Gate-3 通过：{formatArtifactValue(submissionArtifact.gate_3_passed)}</div>
        </div>
      </div>

      {sourceChain.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">治理证据来源链</div>
          <div className="flex flex-wrap gap-2">
            {sourceChain.slice(0, 8).map((item) => (
              <Badge key={item} variant="neutral">
                {item}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {(gateStageRows.length > 0
        || Object.keys(protocolVersions).length > 0
        || predictionTraceLedgerEntries.length > 0
        || sampleTraceIds.length > 0
        || detail.prediction_trace_id) && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">V2 门禁与追踪</div>
          {gateStageRows.length > 0 && (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
              {gateStageRows.map(({ label, gate }) => {
                const blockingReasons = Array.isArray(gate.blocking_reasons)
                  ? gate.blocking_reasons
                      .map((item) =>
                        typeof item === 'string'
                          ? item
                          : String(item.reason ?? item.reason_code ?? item.count ?? ''),
                      )
                      .filter(Boolean)
                  : [];
                const revisionActions = Array.isArray(gate.revision_actions)
                  ? gate.revision_actions.map((item) => String(item)).filter(Boolean)
                  : [];

                return (
                  <div
                    key={label}
                    className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium text-text-primary">{label}</div>
                      <Badge variant={previewBadgeVariant(gate.status)}>
                        {formatTaskLabel(gate.status ?? 'pending')}
                      </Badge>
                    </div>
                    <div>契约：{formatArtifactValue(gate.contract_version)}</div>
                    <div>阻断：{blockingReasons.slice(0, 2).join(' / ') || '-'}</div>
                    <div>修订：{revisionActions.slice(0, 2).join(' / ') || '-'}</div>
                  </div>
                );
              })}
            </div>
          )}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 text-xs text-text-secondary">
            <div>研究协议：{formatCountSummary(protocolVersions.research_protocol_version_counts ?? {}) || '-'}</div>
            <div>候选契约：{formatCountSummary(protocolVersions.candidate_contract_version_counts ?? {}) || '-'}</div>
            <div>完整性：{formatCountSummary(protocolVersions.spec_completeness_counts ?? {}) || '-'}</div>
          </div>
          {(detail.prediction_trace_id || predictionTraceSummary.trace_count != null) && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">
                追踪覆盖：{formatArtifactValue(predictionTraceSummary.trace_count)} / 缺失{' '}
                {formatArtifactValue(predictionTraceSummary.missing_count)}
              </div>
              {predictionTraceLedgerEntries.length > 0 ? (
                <FactoryPredictionTraceLedgerPanel
                  ledger={predictionTraceLedger}
                  predictionTraceId={detail.prediction_trace_id ?? null}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {detail.prediction_trace_id ? (
                    <Badge variant="info">{String(detail.prediction_trace_id)}</Badge>
                  ) : null}
                  {sampleTraceIds
                    .filter((item) => item !== detail.prediction_trace_id)
                    .slice(0, 4)
                    .map((item) => (
                      <Badge key={item} variant="neutral">
                        {item}
                      </Badge>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <FactoryArtifactCard
          title="Gate Artifact"
          artifact={gateArtifact}
          fields={[
            { key: 'gate_0_passed', label: 'Gate-0 通过' },
            { key: 'gate_2_passed', label: 'Gate-2 通过' },
            { key: 'gate_3_passed', label: 'Gate-3 通过' },
            { key: 'gate_3_failed', label: 'Gate-3 失败' },
            { key: 'gate_3_provisional_passed', label: '临时通过' },
          ]}
        />
        <FactoryArtifactCard
          title="Gate Artifact V2"
          artifact={gateArtifactV2}
          fields={[
            { key: 'available', label: 'V2 可用' },
            { key: 'contract_version', label: '契约版本' },
          ]}
        />
        <FactoryArtifactCard
          title="Dedup Artifact"
          artifact={dedupArtifact}
          fields={[
            { key: 'input_count', label: '输入候选' },
            { key: 'kept_count', label: '保留候选' },
            { key: 'dropped_count', label: '淘汰候选' },
            { key: 'refreshed_existing_count', label: '刷新已有' },
            { key: 'vector_checks', label: '向量检查' },
          ]}
        />
        <FactoryArtifactCard
          title="Submission Artifact"
          artifact={submissionArtifact}
          fields={[
            { key: 'strategy_count', label: '策略记录' },
            { key: 'submitted_count', label: '已提交' },
            { key: 'created_strategy_pool_count', label: '入池创建' },
            { key: 'refreshed_count', label: '刷新数' },
            { key: 'gate_3_passed', label: 'Gate-3 通过' },
          ]}
        />
        <FactoryArtifactCard
          title="Governance Evidence"
          artifact={governanceEvidenceArtifact}
          fields={[
            { key: 'quality_report_count', label: '质检报告' },
            { key: 'multiple_testing_registry_record_count', label: '多重检验记录' },
            { key: 'lineage_id_count', label: 'Lineage ID' },
            { key: 'vector_profile_count', label: '向量画像' },
            { key: 'cost_assumptions_count', label: '成本假设' },
          ]}
        />
      </div>

      {hasAuditSliceCoverage && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">候选审计切片覆盖</div>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
            <FactoryMetric
              title="约束审计"
              value={Number(submissionArtifact.constraint_check_count ?? governanceEvidenceArtifact.constraint_check_count ?? 0)}
            />
            <FactoryMetric
              title="验证画像"
              value={Number(submissionArtifact.validation_profile_count ?? governanceEvidenceArtifact.validation_profile_count ?? 0)}
            />
            <FactoryMetric
              title="事件窗配置"
              value={Number(submissionArtifact.event_window_config_count ?? governanceEvidenceArtifact.event_window_config_count ?? 0)}
            />
            <FactoryMetric
              title="仓位假设"
              value={Number(submissionArtifact.position_assumption_count ?? governanceEvidenceArtifact.position_assumption_count ?? 0)}
            />
            <FactoryMetric
              title="成本假设"
              value={Number(submissionArtifact.cost_assumptions_count ?? governanceEvidenceArtifact.cost_assumptions_count ?? 0)}
            />
            <FactoryMetric
              title="尝试惩罚"
              value={Number(submissionArtifact.attempt_adjustment_count ?? governanceEvidenceArtifact.attempt_adjustment_count ?? 0)}
            />
            <FactoryMetric
              title="评审结果"
              value={Number(submissionArtifact.committee_review_count ?? governanceEvidenceArtifact.committee_review_count ?? 0)}
            />
            <FactoryMetric
              title="任务签名"
              value={Number(submissionArtifact.task_signature_count ?? governanceEvidenceArtifact.task_signature_count ?? 0)}
            />
          </div>
        </div>
      )}

      {(refreshModeCounts.length > 0
        || duplicateLevelCounts.length > 0
        || submissionLaneCounts.length > 0
        || submissionActionTypeCounts.length > 0
        || strategyStatusCounts.length > 0
        || committeeDecisionCounts.length > 0
        || primaryValidationLayerCounts.length > 0
        || validationProfileCounts.length > 0
        || constraintViolationCounts.length > 0
        || vectorBackendCounts.length > 0
        || extensionSupport.length > 0
        || incubationFamilyCounts.length > 0
        || Object.keys(backtestThresholdsByType).length > 0) && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">治理分布</div>
          {refreshModeCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">Refresh 模式</div>
              <div className="flex flex-wrap gap-2">
                {refreshModeCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="info">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {duplicateLevelCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">重复级别</div>
              <div className="flex flex-wrap gap-2">
                {duplicateLevelCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="warning">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {submissionLaneCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">提交通道</div>
              <div className="flex flex-wrap gap-2">
                {submissionLaneCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {submissionActionTypeCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">提交动作</div>
              <div className="flex flex-wrap gap-2">
                {submissionActionTypeCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="info">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {strategyStatusCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">策略状态</div>
              <div className="flex flex-wrap gap-2">
                {strategyStatusCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant={previewBadgeVariant(key)}>
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {committeeDecisionCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">评审结论</div>
              <div className="flex flex-wrap gap-2">
                {committeeDecisionCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant={previewBadgeVariant(key)}>
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {primaryValidationLayerCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">主验证层</div>
              <div className="flex flex-wrap gap-2">
                {primaryValidationLayerCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="info">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {validationProfileCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">验证画像</div>
              <div className="flex flex-wrap gap-2">
                {validationProfileCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {constraintViolationCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">约束违例</div>
              <div className="flex flex-wrap gap-2">
                {constraintViolationCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="warning">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {vectorBackendCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">向量后端</div>
              <div className="flex flex-wrap gap-2">
                {vectorBackendCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {incubationFamilyCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">孵化预算分布</div>
              <div className="flex flex-wrap gap-2">
                {incubationFamilyCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="info">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {Object.keys(backtestThresholdsByType).length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">Backtest 阈值类型</div>
              <div className="flex flex-wrap gap-2">
                {Object.keys(backtestThresholdsByType).slice(0, 6).map((key) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {extensionSupport.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">扩展接口支持</div>
              <div className="flex flex-wrap gap-2">
                {extensionSupport.map((item) => (
                  <Badge key={item.key} variant={item.enabled ? 'success' : 'neutral'}>
                    {formatTaskLabel(item.key)} {item.enabled ? '已接入' : '未接入'}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {(gateFailureReasons.length > 0 || submissionFailureReasons.length > 0) && (
        <FactoryPreviewSection
          title="治理原因预览"
          count={gateFailureReasons.length + submissionFailureReasons.length}
        >
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {gateFailureReasons.length > 0 && (
              <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
                <div className="text-xs font-medium text-text-primary">Gate-3 失败原因</div>
                <div className="space-y-2 text-xs text-text-secondary">
                  {gateFailureReasons.slice(0, 4).map((item) => (
                    <div
                      key={`gate-${item.reason}`}
                      className="flex items-center justify-between gap-3"
                    >
                      <span className="break-all">{formatTaskLabel(item.reason)}</span>
                      <span>{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {submissionFailureReasons.length > 0 && (
              <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
                <div className="text-xs font-medium text-text-primary">提交阶段失败原因</div>
                <div className="space-y-2 text-xs text-text-secondary">
                  {submissionFailureReasons.slice(0, 4).map((item) => (
                    <div
                      key={`submission-${item.reason}`}
                      className="flex items-center justify-between gap-3"
                    >
                      <span className="break-all">{formatTaskLabel(item.reason)}</span>
                      <span>{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </FactoryPreviewSection>
      )}

      {(keptBriefs.length > 0 || droppedBriefs.length > 0) && (
        <FactoryPreviewSection title="Dedup Decisions" count={keptBriefs.length + droppedBriefs.length}>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {keptBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">保留候选</div>
                <div className="space-y-2">
                  {keptBriefs.slice(0, 4).map((item, idx) => {
                    const refreshMode = toDisplayText(item.refresh_mode);
                    const refreshDecisionBasis = toDisplayText(item.refresh_decision_basis);

                    return (
                      <div
                        key={String(item.matched_strategy_id ?? item.strategy_type ?? idx)}
                        className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-medium text-text-primary break-all">
                            {formatArtifactValue(item.strategy_type)}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant={Boolean(item.refresh_existing) ? 'success' : 'neutral'}>
                              {Boolean(item.refresh_existing) ? '刷新已有' : '保留新候选'}
                            </Badge>
                            {refreshMode && <Badge variant="info">{formatTaskLabel(refreshMode)}</Badge>}
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>生成器：{formatArtifactValue(item.generator_type)}</div>
                          <div>家族：{formatArtifactValue(item.candidate_family_id)}</div>
                          <div>目标重合：{formatArtifactScore(item.target_overlap, 4)}</div>
                          <div>命中策略：{formatArtifactValue(item.matched_strategy_id)}</div>
                        </div>
                        <div>决策依据：{refreshDecisionBasis ?? '-'}</div>
                        <div className="break-all">
                          标的：{toDisplayTextList(item.target_symbols, 4).join(' / ') || '-'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {droppedBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">淘汰候选</div>
                <div className="space-y-2">
                  {droppedBriefs.slice(0, 4).map((item, idx) => {
                    const duplicateLevel = toDisplayText(item.duplicate_level);
                    const revisionTriggerReason = toDisplayText(item.revision_trigger_reason);

                    return (
                      <div
                        key={String(item.matched_strategy_id ?? item.strategy_type ?? idx)}
                        className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-medium text-text-primary break-all">
                            {formatArtifactValue(item.strategy_type)}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant={Boolean(item.duplicate) ? 'warning' : 'neutral'}>
                              {Boolean(item.duplicate) ? '重复候选' : '未保留'}
                            </Badge>
                            {duplicateLevel && (
                              <Badge variant="warning">{formatTaskLabel(duplicateLevel)}</Badge>
                            )}
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>生成器：{formatArtifactValue(item.generator_type)}</div>
                          <div>家族：{formatArtifactValue(item.candidate_family_id)}</div>
                          <div>目标重合：{formatArtifactScore(item.target_overlap, 4)}</div>
                          <div>命中策略：{formatArtifactValue(item.matched_strategy_id)}</div>
                        </div>
                        <div>修订触发：{revisionTriggerReason ?? '-'}</div>
                        <div className="break-all">
                          标的：{toDisplayTextList(item.target_symbols, 4).join(' / ') || '-'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </FactoryPreviewSection>
      )}

      {(strategyBriefs.length > 0 || strategyEvidenceBriefs.length > 0) && (
        <FactoryPreviewSection
          title="Submission / Evidence"
          count={strategyBriefs.length + strategyEvidenceBriefs.length}
        >
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {strategyBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">提交策略</div>
                <div className="space-y-2">
                  {strategyBriefs.slice(0, 4).map((item, idx) => {
                    const submissionLane = toDisplayText(item.submission_lane);
                    const actionType = toDisplayText(item.submission_action_type);
                    const candidateFamily = toDisplayText(item.candidate_family);
                    const generatorMode = toDisplayText(item.generator_mode);
                    const strategyStatus = toDisplayText(item.status);
                    const rawValidationGrade = toDisplayText(item.raw_validation_grade);
                    const effectiveValidationGrade = toDisplayText(
                      item.effective_validation_grade ?? item.validation_grade,
                    );
                    const validationAdjustmentReason = toDisplayText(
                      item.validation_grade_adjustment_reason,
                    );
                    const committeeReview = asTypedObject<FactoryGovernanceCommitteeReview>(item.committee_review);
                    const validationProfile = asTypedObject<FactoryGovernanceValidationProfile>(item.validation_profile);
                    const constraintCheck = asTypedObject<FactoryGovernanceConstraintCheck>(item.constraint_check);
                    const committeeDecision = toDisplayText(committeeReview.decision);
                    const committeeFinalScore = Number(committeeReview.final_score);
                    const committeeExecutionScore = Number(committeeReview.execution_score);
                    const committeeCapacityScore = Number(committeeReview.capacity_score);
                    const committeeAlignmentScore = Number(committeeReview.task_alignment_score);
                    const validationProfileName = toDisplayText(validationProfile.profile);
                    const validationFocus = toDisplayText(validationProfile.validation_focus);
                    const primaryValidationLayer = toDisplayText(item.primary_validation_layer)
                      ?? toDisplayText(validationProfile.primary_validation_layer);
                    const refreshMode = toDisplayText(item.refresh_mode);
                    const positionAssumption = toDisplayText(item.position_assumption);
                    const taskSignature = toDisplayText(item.task_signature);
                    const constraintSummary = formatConstraintAuditSummary(constraintCheck);
                    const eventWindowSummary = formatArtifactObjectSummary(item.event_window_config, 4);
                    const costSummary = formatArtifactObjectSummary(item.cost_assumptions, 4);
                    const explicitCostSummary = formatArtifactObjectSummary(item.explicit_cost_breakdown, 3);
                    const implicitCostSummary = formatArtifactObjectSummary(item.implicit_cost_breakdown, 3);
                    const attemptAdjustmentSummary = formatAttemptAdjustmentSummary(item.attempt_adjustment);
                    const committeeIssueSummary = shortArtifactText(
                      [
                        ...toDisplayTextList(committeeReview.alignment_issues, 3),
                        ...toDisplayTextList(committeeReview.execution_issues, 3),
                        ...toDisplayTextList(committeeReview.capacity_issues, 3),
                        ...toDisplayTextList(committeeReview.accept_blockers, 3),
                      ].join(' / ') || '-',
                      80,
                    );

                    return (
                      <div
                        key={String(item.strategy_id ?? item.name ?? idx)}
                        className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-medium text-text-primary break-all">
                              {formatArtifactValue(item.name ?? item.strategy_id)}
                            </div>
                            <div className="mt-1 break-all">
                              strategy_id: {formatArtifactValue(item.strategy_id)}
                            </div>
                          </div>
                          {strategyStatus && (
                            <Badge variant={previewBadgeVariant(strategyStatus)}>
                              {formatTaskLabel(strategyStatus)}
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {submissionLane && <Badge variant="neutral">{formatTaskLabel(submissionLane)}</Badge>}
                          {actionType && <Badge variant="info">{formatTaskLabel(actionType)}</Badge>}
                          {candidateFamily && (
                            <Badge variant="info">{formatTaskLabel(candidateFamily)}</Badge>
                          )}
                          {generatorMode && (
                            <Badge variant={previewBadgeVariant(generatorMode)}>
                              {formatTaskLabel(generatorMode)}
                            </Badge>
                          )}
                          {validationProfileName && (
                            <Badge variant="info">{formatTaskLabel(validationProfileName)}</Badge>
                          )}
                          {rawValidationGrade && (
                            <Badge variant={validationGradeBadgeVariant(rawValidationGrade)}>
                              Raw {rawValidationGrade}
                            </Badge>
                          )}
                          {effectiveValidationGrade && (
                            <Badge variant={validationGradeBadgeVariant(effectiveValidationGrade)}>
                              Effective {effectiveValidationGrade}
                            </Badge>
                          )}
                          {committeeDecision && (
                            <Badge variant={previewBadgeVariant(committeeDecision)}>
                              {formatTaskLabel(committeeDecision)}
                              {Number.isFinite(committeeFinalScore) ? ` ${committeeFinalScore.toFixed(4)}` : ''}
                            </Badge>
                          )}
                          {primaryValidationLayer && (
                            <Badge variant="neutral">
                              主验证 {formatTaskLabel(primaryValidationLayer)}
                            </Badge>
                          )}
                          {refreshMode && <Badge variant="neutral">{formatTaskLabel(refreshMode)}</Badge>}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>向量画像：{formatArtifactValue(item.vector_profile_id)}</div>
                          <div>多重检验：{formatArtifactValue(item.multiple_testing_registry_record_id)}</div>
                          <div>源候选：{formatArtifactValue(item.source_candidate_artifact_id)}</div>
                          <div>目标池：{formatArtifactValue(item.target_pool_id)}</div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant={Boolean(item.has_constraint_check) ? 'success' : 'warning'}>
                            约束审计{Boolean(item.has_constraint_check) ? '已挂载' : '缺失'}
                          </Badge>
                          <Badge variant={Boolean(item.has_validation_profile) ? 'success' : 'warning'}>
                            验证画像{Boolean(item.has_validation_profile) ? '已挂载' : '缺失'}
                          </Badge>
                          <Badge variant={Boolean(item.has_event_window_config) ? 'success' : 'warning'}>
                            事件窗{Boolean(item.has_event_window_config) ? '已挂载' : '缺失'}
                          </Badge>
                          <Badge variant={Boolean(item.has_attempt_adjustment) ? 'success' : 'neutral'}>
                            尝试惩罚{Boolean(item.has_attempt_adjustment) ? '已挂载' : '未触发'}
                          </Badge>
                          <Badge variant={Boolean(item.has_committee_review) ? 'success' : 'warning'}>
                            评审结果{Boolean(item.has_committee_review) ? '已挂载' : '缺失'}
                          </Badge>
                          {item.created_strategy_pool ? <Badge variant="success">已创建入池</Badge> : null}
                          {item.created_audit_only ? <Badge variant="warning">仅审计落档</Badge> : null}
                          {item.refreshed_existing ? <Badge variant="info">刷新已有</Badge> : null}
                          {item.live_candidate_ready ? <Badge variant="success">Live 候选</Badge> : null}
                          {item.live_review_ready ? <Badge variant="info">待运行审查</Badge> : null}
                          {item.direct_trade_candidate ? <Badge variant="warning">直达交易候选</Badge> : null}
                        </div>
                        <div>
                          评审拆解：
                          {[
                            Number.isFinite(committeeExecutionScore)
                              ? `执行:${committeeExecutionScore.toFixed(2)}`
                              : '',
                            Number.isFinite(committeeCapacityScore)
                              ? `容量:${committeeCapacityScore.toFixed(2)}`
                              : '',
                            Number.isFinite(committeeAlignmentScore)
                              ? `对齐:${committeeAlignmentScore.toFixed(2)}`
                              : '',
                          ]
                            .filter(Boolean)
                            .join(' / ') || '-'}
                        </div>
                        <div>约束审计：{constraintSummary}</div>
                        <div>评审问题：{committeeIssueSummary}</div>
                        <div>
                          评级分离：
                          {rawValidationGrade ?? '-'} → {effectiveValidationGrade ?? '-'}
                          {validationAdjustmentReason ? ` / ${validationAdjustmentReason}` : ''}
                        </div>
                        <div>
                          Raw / Effective 分数：
                          {formatArtifactScore(item.raw_validation_total_score, 2)}
                          {' / '}
                          {formatArtifactScore(item.validation_total_score, 2)}
                        </div>
                        <div>验证焦点：{validationFocus ?? '-'}</div>
                        <div>事件窗：{eventWindowSummary}</div>
                        <div>仓位 / 惩罚：{positionAssumption ?? '-'} / {attemptAdjustmentSummary}</div>
                        <div>成本假设：{costSummary}</div>
                        <div>显式 / 隐式成本：{explicitCostSummary} / {implicitCostSummary}</div>
                        <div>任务签名：{shortArtifactText(taskSignature, 56)}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {strategyEvidenceBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">治理证据</div>
                <div className="space-y-2">
                  {strategyEvidenceBriefs.slice(0, 4).map((item, idx) => (
                    <div
                      key={String(item.strategy_id ?? item.name ?? idx)}
                      className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-medium text-text-primary break-all">
                            {formatArtifactValue(item.name ?? item.strategy_id)}
                          </div>
                          <div className="mt-1 break-all">lineage: {formatArtifactValue(item.lineage_id)}</div>
                        </div>
                        {toDisplayText(item.vector_backend) && (
                          <Badge variant="neutral">{formatTaskLabel(String(item.vector_backend))}</Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant={Boolean(item.has_multiple_testing_registry) ? 'success' : 'warning'}>
                          多重检验{Boolean(item.has_multiple_testing_registry) ? '已登记' : '缺失'}
                        </Badge>
                        <Badge variant={Boolean(item.has_cost_assumptions) ? 'success' : 'warning'}>
                          成本假设{Boolean(item.has_cost_assumptions) ? '已接入' : '缺失'}
                        </Badge>
                        <Badge variant={Boolean(item.has_execution_reality) ? 'success' : 'warning'}>
                          执行现实{Boolean(item.has_execution_reality) ? '已接入' : '缺失'}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>状态：{formatArtifactValue(item.status)}</div>
                        <div>通道：{formatArtifactValue(item.submission_lane)}</div>
                        <div>动作：{formatArtifactValue(item.submission_action_type)}</div>
                        <div>向量画像：{formatArtifactValue(item.vector_profile_id)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </FactoryPreviewSection>
      )}
    </div>
  );
}
