'use client';

import { Badge } from '@/components/ui';
import { formatTaskLabel } from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  FactoryFeedbackGeneratorModeControl,
  FactoryFeedbackSummary,
  FactoryRunSummary,
} from '../../types';

import { FactoryMetric } from './metrics';
import {
  firstDefinedValue,
  previewBadgeVariant,
  providerControlBadgeVariant,
  toDisplayCountEntries,
  toDisplayNumber,
  toDisplayText,
  toDisplayTextList,
} from './formatters';

export function FactoryFeedbackLoopPanel({
  title,
  summary,
  feedbackSummary,
  compact = false,
}: {
  title: string;
  summary?: Partial<FactoryRunSummary> | null;
  feedbackSummary?: FactoryFeedbackSummary | null;
  compact?: boolean;
}) {
  const feedbackContractVersion = toDisplayText(
    firstDefinedValue(
      feedbackSummary?.lifecycle_feedback_input_contract_version,
      summary?.lifecycle_feedback_input_contract_version,
    ),
  );
  const lifecycleInputObserved = firstDefinedValue(
    typeof feedbackSummary?.lifecycle_feedback_input_observed === 'boolean'
      ? Boolean(feedbackSummary.lifecycle_feedback_input_observed)
      : undefined,
    summary?.lifecycle_feedback_input_available,
  );
  const feedbackAvailable = firstDefinedValue(
    typeof feedbackSummary?.feedback_available === 'boolean'
      ? Boolean(feedbackSummary.feedback_available)
      : undefined,
    summary?.budget_feedback_available,
  );
  const familyCount = toDisplayNumber(
    firstDefinedValue(feedbackSummary?.family_count, summary?.budget_feedback_family_count),
  );
  const strategyCount = toDisplayNumber(
    firstDefinedValue(feedbackSummary?.strategy_count, summary?.budget_feedback_strategy_count),
  );
  const targetPoolScopeCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.target_pool_scope_count,
      summary?.budget_feedback_target_pool_scope_count,
    ),
  );
  const generatorModeScopeCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.generator_mode_scope_count,
      summary?.budget_feedback_generator_mode_scope_count,
    ),
  );
  const runtimeAlertCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.runtime_alert_count,
      summary?.budget_feedback_runtime_alert_count,
    ),
  );
  const runtimeRiskEventCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.runtime_risk_event_count,
      summary?.budget_feedback_runtime_risk_event_count,
    ),
  );
  const promotionReviewCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.promotion_review_count,
      summary?.budget_feedback_promotion_review_count,
    ),
  );
  const blockedTaskCount = toDisplayNumber(
    firstDefinedValue(feedbackSummary?.blocked_task_count, summary?.blocked_feedback_task_count),
  );
  const cooldownTaskCount = toDisplayNumber(
    firstDefinedValue(
      feedbackSummary?.planned_cooldown_task_count,
      summary?.planned_feedback_cooldown_task_count,
    ),
  );
  const promotionReviewStatusCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.promotion_review_status_counts,
      summary?.budget_feedback_promotion_review_status_counts,
    ),
  );
  const plannedControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.planned_control_mode_counts,
      summary?.planned_feedback_control_mode_counts,
    ),
  );
  const plannedTargetPoolControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.planned_target_pool_control_mode_counts,
      summary?.planned_feedback_target_pool_control_mode_counts,
    ),
  );
  const plannedGeneratorModeControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.planned_generator_mode_control_mode_counts,
      summary?.planned_feedback_generator_mode_control_mode_counts,
    ),
  );
  const selectedControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.selected_control_mode_counts,
      summary?.selected_feedback_control_mode_counts,
    ),
  );
  const selectedTargetPoolControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.selected_target_pool_control_mode_counts,
      summary?.selected_feedback_target_pool_control_mode_counts,
    ),
  );
  const selectedGeneratorModeControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.selected_generator_mode_control_mode_counts,
      summary?.selected_feedback_generator_mode_control_mode_counts,
    ),
  );
  const submissionControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.submission_control_mode_counts,
      summary?.feedback_control_mode_counts,
    ),
  );
  const submissionTargetPoolControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.submission_target_pool_control_mode_counts,
      summary?.feedback_target_pool_control_mode_counts,
    ),
  );
  const submissionGeneratorModeControlModeCounts = toDisplayCountEntries(
    firstDefinedValue(
      feedbackSummary?.submission_generator_mode_control_mode_counts,
      summary?.feedback_generator_mode_control_mode_counts,
    ),
  );
  const suppressedFamilies = toDisplayTextList(
    firstDefinedValue(feedbackSummary?.suppressed_families, summary?.suppressed_families),
    6,
  );
  const suppressedTargetPools = toDisplayTextList(
    firstDefinedValue(feedbackSummary?.suppressed_target_pools, summary?.suppressed_target_pools),
    6,
  );
  const suppressedGeneratorModes = toDisplayTextList(
    firstDefinedValue(
      feedbackSummary?.suppressed_generator_modes,
      summary?.suppressed_generator_modes,
    ),
    6,
  );
  const externalLlmProviderControlMode = toDisplayText(summary?.external_llm_provider_control_mode);
  const externalLlmProviderControlReasons = toDisplayTextList(
    summary?.external_llm_provider_control_reasons,
    6,
  );
  const externalLlmProviderSuppressed = firstDefinedValue(
    typeof summary?.external_llm_provider_suppressed === 'boolean'
      ? Boolean(summary.external_llm_provider_suppressed)
      : undefined,
    externalLlmProviderControlMode === 'suppress'
      || suppressedGeneratorModes.includes('external_llm')
      || submissionGeneratorModeControlModeCounts.some(([key]) => key === 'suppress'),
  );
  const externalLlmProviderCooldown = firstDefinedValue(
    typeof summary?.external_llm_provider_cooldown === 'boolean'
      ? Boolean(summary.external_llm_provider_cooldown)
      : undefined,
    externalLlmProviderControlMode === 'cooldown',
  );
  const generatorModeControls = Object.entries(summary?.generator_mode_controls ?? {}).filter(
    ([, payload]) => Boolean(payload),
  ) as Array<[string, FactoryFeedbackGeneratorModeControl]>;
  const controlModeSections = [
    {
      key: 'planned',
      title: '规划控制',
      variant: 'warning' as const,
      entries: plannedControlModeCounts,
      poolEntries: plannedTargetPoolControlModeCounts,
      modeEntries: plannedGeneratorModeControlModeCounts,
    },
    {
      key: 'selected',
      title: '候选选择控制',
      variant: 'info' as const,
      entries: selectedControlModeCounts,
      poolEntries: selectedTargetPoolControlModeCounts,
      modeEntries: selectedGeneratorModeControlModeCounts,
    },
    {
      key: 'submission',
      title: '提交控制',
      variant: 'success' as const,
      entries: submissionControlModeCounts,
      poolEntries: submissionTargetPoolControlModeCounts,
      modeEntries: submissionGeneratorModeControlModeCounts,
    },
  ].filter(
    (section) => section.entries.length > 0 || section.poolEntries.length > 0 || section.modeEntries.length > 0,
  );
  const hasFeedbackData = [
    feedbackContractVersion,
    lifecycleInputObserved != null,
    feedbackAvailable != null,
    familyCount != null,
    strategyCount != null,
    targetPoolScopeCount != null,
    generatorModeScopeCount != null,
    runtimeAlertCount != null,
    runtimeRiskEventCount != null,
    promotionReviewCount != null,
    blockedTaskCount != null,
    cooldownTaskCount != null,
    promotionReviewStatusCounts.length > 0,
    controlModeSections.length > 0,
    suppressedFamilies.length > 0,
    suppressedTargetPools.length > 0,
    suppressedGeneratorModes.length > 0,
    externalLlmProviderControlMode,
    externalLlmProviderControlReasons.length > 0,
    externalLlmProviderSuppressed,
    externalLlmProviderCooldown,
    generatorModeControls.length > 0,
  ].some(Boolean);

  if (!hasFeedbackData) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        <div className="flex flex-wrap gap-2">
          {feedbackContractVersion && <Badge variant="neutral">契约 {feedbackContractVersion}</Badge>}
          {lifecycleInputObserved != null && (
            <Badge variant={lifecycleInputObserved ? 'success' : 'neutral'}>
              生命周期输入{lifecycleInputObserved ? '已接入' : '未接入'}
            </Badge>
          )}
          {feedbackAvailable != null && (
            <Badge variant={feedbackAvailable ? 'success' : 'warning'}>
              反馈摘要{feedbackAvailable ? '可用' : '待补'}
            </Badge>
          )}
          {externalLlmProviderControlMode && (
            <Badge variant={providerControlBadgeVariant(externalLlmProviderControlMode)}>
              外部 LLM {formatTaskLabel(externalLlmProviderControlMode)}
            </Badge>
          )}
          {externalLlmProviderSuppressed ? <Badge variant="warning">Provider 抑制中</Badge> : null}
          {externalLlmProviderCooldown ? <Badge variant="warning">Provider 冷却中</Badge> : null}
        </div>
      </div>

      <div
        className={`grid grid-cols-2 ${compact ? 'md:grid-cols-3 xl:grid-cols-6' : 'md:grid-cols-4 xl:grid-cols-8'} gap-3`}
      >
        <FactoryMetric title="反馈家族" value={familyCount ?? '-'} />
        <FactoryMetric title="策略样本" value={strategyCount ?? '-'} />
        <FactoryMetric title="目标池范围" value={targetPoolScopeCount ?? '-'} />
        <FactoryMetric title="生成模式范围" value={generatorModeScopeCount ?? '-'} />
        <FactoryMetric title="运行告警" value={runtimeAlertCount ?? '-'} />
        <FactoryMetric title="晋级评审" value={promotionReviewCount ?? '-'} />
        {!compact && (
          <>
            <FactoryMetric title="运行风险事件" value={runtimeRiskEventCount ?? '-'} />
            <FactoryMetric title="阻断任务" value={blockedTaskCount ?? '-'} />
            <FactoryMetric title="冷却任务" value={cooldownTaskCount ?? '-'} />
          </>
        )}
      </div>

      {promotionReviewStatusCounts.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">晋级评审状态</div>
          <div className="flex flex-wrap gap-2">
            {promotionReviewStatusCounts.map(([key, count]) => (
              <Badge key={key} variant={previewBadgeVariant(key)}>
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {controlModeSections.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
          {controlModeSections.map((section) => (
            <div key={section.key} className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">{section.title}</div>
              {section.entries.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {section.entries.map(([key, count]) => (
                    <Badge key={key} variant={section.variant}>
                      {formatTaskLabel(key)} {count}
                    </Badge>
                  ))}
                </div>
              )}
              {!compact && section.poolEntries.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">目标池约束</div>
                  <div className="flex flex-wrap gap-2">
                    {section.poolEntries.map(([key, count]) => (
                      <Badge key={key} variant="neutral">
                        {formatTaskLabel(key)} {count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {!compact && section.modeEntries.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">生成模式约束</div>
                  <div className="flex flex-wrap gap-2">
                    {section.modeEntries.map(([key, count]) => (
                      <Badge key={key} variant="neutral">
                        {formatTaskLabel(key)} {count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!compact
        && (suppressedFamilies.length > 0
          || suppressedTargetPools.length > 0
          || suppressedGeneratorModes.length > 0) && (
          <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
            <div className="text-xs font-medium text-text-primary">受抑制范围</div>
            {suppressedFamilies.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs text-text-secondary">家族</div>
                <div className="flex flex-wrap gap-2">
                  {suppressedFamilies.map((item) => (
                    <Badge key={item} variant="warning">
                      {formatTaskLabel(item)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {suppressedTargetPools.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs text-text-secondary">目标池</div>
                <div className="flex flex-wrap gap-2">
                  {suppressedTargetPools.map((item) => (
                    <Badge key={item} variant="warning">
                      {formatTaskLabel(item)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {suppressedGeneratorModes.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs text-text-secondary">生成模式</div>
                <div className="flex flex-wrap gap-2">
                  {suppressedGeneratorModes.map((item) => (
                    <Badge key={item} variant="warning">
                      {formatTaskLabel(item)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

      {!compact
        && (externalLlmProviderControlReasons.length > 0
          || externalLlmProviderSuppressed
          || externalLlmProviderCooldown) && (
          <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
            <div className="text-xs font-medium text-text-primary">外部 LLM Provider</div>
            <div className="flex flex-wrap gap-2">
              {externalLlmProviderControlMode ? (
                <Badge variant={providerControlBadgeVariant(externalLlmProviderControlMode)}>
                  模式 {formatTaskLabel(externalLlmProviderControlMode)}
                </Badge>
              ) : null}
              {externalLlmProviderSuppressed ? <Badge variant="warning">已触发抑制</Badge> : null}
              {externalLlmProviderCooldown ? <Badge variant="warning">已触发冷却</Badge> : null}
            </div>
            {externalLlmProviderControlReasons.length > 0 && (
              <div className="text-xs text-text-secondary">
                原因码：
                {externalLlmProviderControlReasons.map((item) => formatTaskLabel(item)).join(' / ')}
              </div>
            )}
          </div>
        )}

      {!compact && generatorModeControls.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">生成模式控制明细</div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {generatorModeControls.slice(0, 6).map(([mode, payload]) => {
              const controlMode = toDisplayText(payload.control_mode);
              const source = Array.isArray(payload.source)
                ? payload.source.map((item) => String(item)).filter(Boolean).join(' / ')
                : toDisplayText(payload.source);
              const families = toDisplayTextList(payload.families, 4);
              const controlReasons = toDisplayTextList(payload.control_reasons, 4);

              return (
                <div
                  key={mode}
                  className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="font-medium text-text-primary">{formatTaskLabel(mode)}</div>
                    <div className="flex flex-wrap gap-2">
                      {controlMode && (
                        <Badge variant={previewBadgeVariant(controlMode)}>
                          {formatTaskLabel(controlMode)}
                        </Badge>
                      )}
                      {source && <Badge variant="neutral">{formatTaskLabel(source)}</Badge>}
                    </div>
                  </div>
                  <div>家族：{families.join(' / ') || '-'}</div>
                  <div>原因：{controlReasons.join(' / ') || '-'}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
