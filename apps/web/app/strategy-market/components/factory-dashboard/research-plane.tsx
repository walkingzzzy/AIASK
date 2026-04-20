'use client';

import { Badge } from '@/components/ui';
import {
  formatTaskLabel,
  shortFactoryRunTime,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type { FactoryRunDetailResponse } from '../../types';

import { FactoryMetric } from './metrics';
import {
  formatArtifactScore,
  formatArtifactValue,
  isObjectRecord,
  previewBadgeVariant,
  toDisplayCountEntries,
  toDisplayNumber,
  toDisplayText,
  toDisplayTextList,
  toObjectArray,
} from './formatters';
import { FactoryArtifactCard, FactoryPreviewSection } from './shared';

export function FactoryResearchPlanePanel({
  detail,
}: {
  detail: FactoryRunDetailResponse;
}) {
  const researchPlane = isObjectRecord(detail.research_plane) ? detail.research_plane : {};
  const researchSummary = isObjectRecord(detail.research_summary) ? detail.research_summary : {};
  const researchArtifact = isObjectRecord(detail.research_artifact) ? detail.research_artifact : {};
  const taskArtifact = isObjectRecord(detail.task_artifact) ? detail.task_artifact : {};
  const candidateArtifact = isObjectRecord(detail.candidate_artifact) ? detail.candidate_artifact : {};
  const evidenceArtifact = isObjectRecord(detail.evidence_artifact) ? detail.evidence_artifact : {};
  const readinessReference = isObjectRecord(researchArtifact.readiness_reference)
    ? researchArtifact.readiness_reference
    : {};
  const lineagePreview = toObjectArray(researchArtifact.top_candidate_lineage_preview);
  const plannedTaskBriefs = toObjectArray(taskArtifact.planned_task_briefs);
  const taskResultBriefs = toObjectArray(taskArtifact.task_result_briefs);
  const candidateBriefs = toObjectArray(candidateArtifact.candidate_briefs);
  const experimentBriefs = toObjectArray(evidenceArtifact.experiment_briefs);
  const blockingReasonCodes = toDisplayTextList(readinessReference.blocking_reason_codes, 6);
  const readinessDecision = toDisplayText(readinessReference.decision);
  const sourceChain = Array.isArray(researchPlane.source_chain)
    ? researchPlane.source_chain.map((item) => String(item)).filter(Boolean)
    : [];
  const candidateFamilyCounts = toDisplayCountEntries(candidateArtifact.family_counts);
  const candidateSourceCounts = toDisplayCountEntries(candidateArtifact.task_source_counts);
  const llmStatusCounts = toDisplayCountEntries(evidenceArtifact.external_llm_status_counts);
  const lifecycleFeedbackFamilyCount = toDisplayNumber(researchArtifact.lifecycle_feedback_family_count);
  const lifecycleFeedbackStrategyCount = toDisplayNumber(researchArtifact.lifecycle_feedback_strategy_count);
  const lifecycleFeedbackTargetPoolScopeCount = toDisplayNumber(
    researchArtifact.lifecycle_feedback_target_pool_scope_count,
  );
  const lifecycleFeedbackGeneratorModeScopeCount = toDisplayNumber(
    researchArtifact.lifecycle_feedback_generator_mode_scope_count,
  );
  const lifecycleFeedbackRuntimeAlertCount = toDisplayNumber(
    researchArtifact.lifecycle_feedback_runtime_alert_count,
  );
  const lifecycleFeedbackPromotionReviewCount = toDisplayNumber(
    researchArtifact.lifecycle_feedback_promotion_review_count,
  );
  const lifecycleFeedbackPromotionStatuses = toDisplayCountEntries(
    researchArtifact.lifecycle_feedback_promotion_review_status_counts,
  );
  const hasLifecycleFeedbackInput =
    Boolean(researchArtifact.lifecycle_feedback_input_available)
    || lifecycleFeedbackFamilyCount != null
    || lifecycleFeedbackStrategyCount != null
    || lifecycleFeedbackTargetPoolScopeCount != null
    || lifecycleFeedbackGeneratorModeScopeCount != null
    || lifecycleFeedbackRuntimeAlertCount != null
    || lifecycleFeedbackPromotionReviewCount != null
    || lifecycleFeedbackPromotionStatuses.length > 0;

  const hasResearchPlane =
    Boolean(researchPlane.available)
    || Boolean(researchArtifact.available)
    || Boolean(taskArtifact.available)
    || Boolean(candidateArtifact.available)
    || Boolean(evidenceArtifact.available);

  if (!hasResearchPlane) return null;

  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-medium">研究平面</div>
        <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
          <div>总契约：{formatArtifactValue(researchPlane.contract_version)}</div>
          <div>平面可用：{formatArtifactValue(researchPlane.available)}</div>
          <div>平面类型：{formatArtifactValue(researchPlane.plane)}</div>
          <div>Research Summary：{formatArtifactValue(researchSummary.research_plane_contract_version)}</div>
        </div>
      </div>

      {sourceChain.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">证据来源链</div>
          <div className="flex flex-wrap gap-2">
            {sourceChain.slice(0, 8).map((item) => (
              <Badge key={item} variant="neutral">
                {item}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <FactoryArtifactCard
          title="Research Artifact"
          artifact={researchArtifact}
          fields={[
            { key: 'active_factor_count', label: '活跃因子' },
            { key: 'active_candidate_count', label: '活跃候选' },
            { key: 'factor_source_mode', label: '因子来源' },
            { key: 'governed_candidate_pool_active', label: '治理池激活' },
            { key: 'lifecycle_feedback_input_available', label: '反馈输入' },
            { key: 'lifecycle_feedback_family_count', label: '反馈家族' },
            { key: 'lifecycle_feedback_promotion_review_count', label: '晋级评审' },
          ]}
        />
        <FactoryArtifactCard
          title="Task Artifact"
          artifact={taskArtifact}
          fields={[
            { key: 'planned_task_count', label: '规划任务' },
            { key: 'executed_task_count', label: '执行任务' },
            { key: 'generated_candidate_count', label: '生成候选' },
            { key: 'event_task_count', label: '事件任务' },
            { key: 'snapshot_task_count', label: '快照任务' },
          ]}
        />
        <FactoryArtifactCard
          title="Candidate Artifact"
          artifact={candidateArtifact}
          fields={[
            { key: 'candidate_count', label: '候选总数' },
            { key: 'targeted_candidate_count', label: '定向候选' },
            { key: 'experiment_linked_count', label: '实验关联' },
            { key: 'candidate_contract_ready_count', label: '合同就绪' },
            { key: 'candidate_evidence_ready_count', label: '证据就绪' },
          ]}
        />
        <FactoryArtifactCard
          title="Evidence Artifact"
          artifact={evidenceArtifact}
          fields={[
            { key: 'experiment_count', label: '实验记录' },
            { key: 'task_evidence_count', label: '任务证据' },
            { key: 'task_run_count', label: '任务运行' },
            { key: 'external_llm_status', label: '外部 LLM' },
            { key: 'external_llm_network_request_count', label: '网络请求' },
          ]}
        />
      </div>

      {hasLifecycleFeedbackInput && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-xs font-medium text-text-primary">生命周期反馈输入</div>
            <div className="flex flex-wrap gap-2">
              <Badge variant={researchArtifact.lifecycle_feedback_input_available ? 'success' : 'warning'}>
                {researchArtifact.lifecycle_feedback_input_available ? '输入可用' : '输入待补'}
              </Badge>
              {toDisplayText(researchArtifact.lifecycle_feedback_input_contract_version) && (
                <Badge variant="neutral">
                  契约 {formatArtifactValue(researchArtifact.lifecycle_feedback_input_contract_version)}
                </Badge>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <FactoryMetric title="反馈家族" value={lifecycleFeedbackFamilyCount ?? '-'} />
            <FactoryMetric title="策略样本" value={lifecycleFeedbackStrategyCount ?? '-'} />
            <FactoryMetric title="目标池范围" value={lifecycleFeedbackTargetPoolScopeCount ?? '-'} />
            <FactoryMetric title="生成模式范围" value={lifecycleFeedbackGeneratorModeScopeCount ?? '-'} />
            <FactoryMetric title="运行告警" value={lifecycleFeedbackRuntimeAlertCount ?? '-'} />
            <FactoryMetric title="晋级评审" value={lifecycleFeedbackPromotionReviewCount ?? '-'} />
          </div>
          {lifecycleFeedbackPromotionStatuses.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">晋级评审状态</div>
              <div className="flex flex-wrap gap-2">
                {lifecycleFeedbackPromotionStatuses.map(([key, count]) => (
                  <Badge key={key} variant={previewBadgeVariant(key)}>
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {(Object.keys(readinessReference).length > 0 || lineagePreview.length > 0) && (
        <FactoryPreviewSection title="Readiness / Lineage" count={lineagePreview.length}>
          {Object.keys(readinessReference).length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs font-medium text-text-primary">准备度引用</div>
                {readinessDecision && (
                  <Badge variant={previewBadgeVariant(readinessDecision)}>{readinessDecision}</Badge>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-text-secondary">
                <div>准备度：{formatArtifactScore(readinessReference.readiness_score)}</div>
                <div>是否可推进：{formatArtifactValue(readinessReference.can_proceed)}</div>
                <div>阻断项：{blockingReasonCodes.length}</div>
              </div>
              {blockingReasonCodes.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">阻断原因</div>
                  <div className="flex flex-wrap gap-2">
                    {blockingReasonCodes.map((code) => (
                      <Badge key={code} variant="warning">
                        {formatTaskLabel(code)}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {lineagePreview.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {lineagePreview.slice(0, 3).map((item, idx) => {
                const family = toDisplayText(item.family);
                const registryStage = toDisplayText(item.registry_stage);
                const latestValidationAt = toDisplayText(item.latest_validation_at);

                return (
                  <div
                    key={String(item.artifact_id ?? item.name ?? idx)}
                    className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-medium text-text-primary break-all">
                          {formatArtifactValue(item.name ?? item.artifact_id)}
                        </div>
                        <div className="mt-1 break-all">artifact_id: {formatArtifactValue(item.artifact_id)}</div>
                      </div>
                      {family && <Badge variant="info">{formatTaskLabel(family)}</Badge>}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {registryStage && (
                        <Badge variant="neutral">阶段 {formatTaskLabel(registryStage)}</Badge>
                      )}
                      {latestValidationAt && (
                        <Badge variant="neutral">验证 {shortFactoryRunTime(latestValidationAt)}</Badge>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </FactoryPreviewSection>
      )}

      {(plannedTaskBriefs.length > 0 || taskResultBriefs.length > 0) && (
        <FactoryPreviewSection title="Task Briefs" count={plannedTaskBriefs.length + taskResultBriefs.length}>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {plannedTaskBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">规划任务</div>
                <div className="space-y-2">
                  {plannedTaskBriefs.slice(0, 4).map((item, idx) => {
                    const taskSource = toDisplayText(item.task_source);
                    const opportunityType = toDisplayText(item.opportunity_type);

                    return (
                      <div
                        key={String(item.task_id ?? item.event_id ?? idx)}
                        className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-medium text-text-primary break-all">
                            {formatArtifactValue(item.task_id ?? item.event_id ?? item.theme_code)}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {taskSource && <Badge variant="neutral">{formatTaskLabel(taskSource)}</Badge>}
                            {opportunityType && <Badge variant="info">{formatTaskLabel(opportunityType)}</Badge>}
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>家族：{formatArtifactValue(item.candidate_family)}</div>
                          <div>因子：{formatArtifactValue(item.factor_name)}</div>
                          <div>预算上限：{formatArtifactValue(item.generation_limit)}</div>
                          <div>目标池：{formatArtifactValue(item.theme_code)}</div>
                        </div>
                        <div className="break-all">
                          标的：{toDisplayTextList(item.target_symbols, 4).join(' / ') || '-'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {taskResultBriefs.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">执行结果</div>
                <div className="space-y-2">
                  {taskResultBriefs.slice(0, 4).map((item, idx) => {
                    const status = toDisplayText(item.status);
                    const externalLlmStatus = toDisplayText(item.external_llm_status);

                    return (
                      <div
                        key={String(item.task_run_id ?? item.task_id ?? idx)}
                        className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-medium text-text-primary break-all">
                            {formatArtifactValue(item.task_run_id ?? item.task_id)}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {status && (
                              <Badge variant={previewBadgeVariant(status)}>
                                {formatTaskLabel(status)}
                              </Badge>
                            )}
                            {externalLlmStatus && (
                              <Badge variant={previewBadgeVariant(externalLlmStatus)}>
                                LLM {formatTaskLabel(externalLlmStatus)}
                              </Badge>
                            )}
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>任务：{formatArtifactValue(item.task_id)}</div>
                          <div>来源：{formatArtifactValue(item.task_source)}</div>
                          <div>生成：{formatArtifactValue(item.generated_count)}</div>
                          <div>复核：{formatArtifactValue(item.reviewed_count)}</div>
                          <div>证据：{formatArtifactValue(item.evidence_count)}</div>
                          <div>机会：{formatArtifactValue(item.opportunity_type)}</div>
                        </div>
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

      {candidateBriefs.length > 0 && (
        <FactoryPreviewSection title="Candidate Briefs" count={candidateBriefs.length}>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {candidateBriefs.slice(0, 6).map((item, idx) => {
              const contractReady = item.candidate_contract_ready == null ? null : Boolean(item.candidate_contract_ready);
              const evidenceReady = item.evidence_ready == null ? null : Boolean(item.evidence_ready);
              const candidateFamily = toDisplayText(item.candidate_family);
              const taskSource = toDisplayText(item.task_source);
              const generatorMode = toDisplayText(item.generator_mode);

              return (
                <div
                  key={String(item.name ?? item.experiment_id ?? idx)}
                  className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium text-text-primary break-all">
                        {formatArtifactValue(item.name)}
                      </div>
                      <div className="mt-1 break-all">策略类型：{formatArtifactValue(item.strategy_type)}</div>
                    </div>
                    <div className="flex flex-wrap gap-2 justify-end">
                      {contractReady != null && (
                        <Badge variant={contractReady ? 'success' : 'neutral'}>
                          契约{contractReady ? '就绪' : '缺失'}
                        </Badge>
                      )}
                      {evidenceReady != null && (
                        <Badge variant={evidenceReady ? 'success' : 'warning'}>
                          证据{evidenceReady ? '就绪' : '待补'}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {candidateFamily && <Badge variant="info">{formatTaskLabel(candidateFamily)}</Badge>}
                    {taskSource && <Badge variant="neutral">{formatTaskLabel(taskSource)}</Badge>}
                    {generatorMode && (
                      <Badge variant={previewBadgeVariant(generatorMode)}>
                        {formatTaskLabel(generatorMode)}
                      </Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>目标池：{formatArtifactValue(item.target_pool_id)}</div>
                    <div>实验：{formatArtifactValue(item.experiment_id)}</div>
                  </div>
                  <div className="break-all">
                    标的：{toDisplayTextList(item.target_symbols, 4).join(' / ') || '-'}
                  </div>
                </div>
              );
            })}
          </div>
        </FactoryPreviewSection>
      )}

      {experimentBriefs.length > 0 && (
        <FactoryPreviewSection title="Experiment Briefs" count={experimentBriefs.length}>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {experimentBriefs.slice(0, 6).map((item, idx) => {
              const status = toDisplayText(item.status);

              return (
                <div
                  key={String(item.experiment_id ?? item.task_id ?? idx)}
                  className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="font-medium text-text-primary break-all">
                      {formatArtifactValue(item.experiment_id)}
                    </div>
                    {status && (
                      <Badge variant={previewBadgeVariant(status)}>
                        {formatTaskLabel(status)}
                      </Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>task_id：{formatArtifactValue(item.task_id)}</div>
                    <div>strategy_id：{formatArtifactValue(item.strategy_id)}</div>
                    <div>模式：{formatArtifactValue(item.generator_mode)}</div>
                    <div>状态：{formatArtifactValue(item.status)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </FactoryPreviewSection>
      )}

      {(candidateFamilyCounts.length > 0 || candidateSourceCounts.length > 0 || llmStatusCounts.length > 0) && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">研究平面分布</div>
          {candidateFamilyCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">候选家族</div>
              <div className="flex flex-wrap gap-2">
                {candidateFamilyCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="info">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {candidateSourceCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">候选来源</div>
              <div className="flex flex-wrap gap-2">
                {candidateSourceCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {llmStatusCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">LLM 状态</div>
              <div className="flex flex-wrap gap-2">
                {llmStatusCounts.slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="neutral">
                    {formatTaskLabel(key)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
