'use client';

import { Badge } from '@/components/ui';
import {
  formatCountSummary,
  formatFactoryMetricValue,
  formatRatioPercent,
  formatTaskLabel,
  getFactoryRunStatusLabel,
  getFactoryRunStatusVariant,
  shortFactoryRunTime,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type { FactoryStatusResponse } from '../../types';

import { FactoryMetric } from './metrics';
import {
  formatCountWithRate,
  previewBadgeVariant,
  providerControlBadgeVariant,
  toDisplayCountEntries,
  toDisplayCountRecord,
  toDisplayNumber,
  toDisplayText,
  toDisplayTextList,
} from './formatters';

export function FactorySignalQualityRegistryPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const registry = factoryStatus?.signal_quality_registry;
  const snapshot = registry?.snapshot ?? registry;
  const buyProbability = snapshot?.buy_probability ?? registry?.buy_probability;
  const sentiment = snapshot?.sentiment ?? registry?.sentiment;
  const factor = snapshot?.factor ?? registry?.factor;
  const drift = registry?.drift;
  const driftChecks = drift?.checks ?? {};
  const driftEntries = Object.entries(driftChecks)
    .map(([key, value]) => ({
      key,
      payload: value ?? {},
    }))
    .filter(({ payload }) => Object.keys(payload).length > 0);
  const recentProbability = registry?.recent_probability ?? [];
  const recentSentiment = registry?.recent_sentiment ?? [];
  const recentFactor = registry?.recent_factor ?? [];

  const hasRegistryData = [
    buyProbability?.entry_count,
    sentiment?.entry_count,
    factor?.entry_count,
    drift?.overall_status,
    recentProbability.length,
    recentSentiment.length,
    recentFactor.length,
  ].some((value) => {
    if (typeof value === 'number') return value > 0;
    return value != null && value !== '';
  });

  if (!hasRegistryData) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">Signal Quality Registry</div>
        <Badge
          variant={String(drift?.overall_status ?? '').toLowerCase() === 'degraded' ? 'warning' : 'info'}
        >
          drift {toDisplayText(drift?.overall_status) ?? 'partial'}
        </Badge>
      </div>
      <div className="text-xs text-text-secondary">
        probability / sentiment / factor 的 recent quality 和 drift summary 放在同一块，作为工厂 dashboard 的观测闭环。
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="概率条目" value={toDisplayNumber(buyProbability?.entry_count) ?? 0} />
        <FactoryMetric title="情绪条目" value={toDisplayNumber(sentiment?.entry_count) ?? 0} />
        <FactoryMetric title="因子条目" value={toDisplayNumber(factor?.entry_count) ?? 0} />
        <FactoryMetric title="总条目" value={toDisplayNumber(snapshot?.total_entries ?? registry?.total_entries) ?? 0} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 text-xs text-text-secondary">
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">买入概率</div>
          <div>质量分布：{formatCountSummary(toDisplayCountRecord(buyProbability?.quality_distribution)) || '-'}</div>
          <div>
            Brier：
            {formatFactoryMetricValue(
              toDisplayNumber(buyProbability?.brier_score?.mean),
              4,
            )}
          </div>
          <div>
            ECE：
            {formatFactoryMetricValue(
              toDisplayNumber(buyProbability?.ece?.mean),
              4,
            )}
          </div>
          {recentProbability.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent:{' '}
              {recentProbability
                .slice(0, 2)
                .map((item) => `${toDisplayText(item.code) ?? '-'} ${toDisplayText(item.quality) ?? 'unknown'}`)
                .join(' / ')}
            </div>
          ) : null}
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">情绪质量</div>
          <div>情绪分布：{formatCountSummary(toDisplayCountRecord(sentiment?.sentiment_distribution)) || '-'}</div>
          <div>稳定性：{formatCountSummary(toDisplayCountRecord(sentiment?.stability_distribution)) || '-'}</div>
          <div>
            news alpha：
            {formatFactoryMetricValue(
              toDisplayNumber(sentiment?.news_alpha_5d?.mean),
              4,
            )}
          </div>
          {recentSentiment.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent:{' '}
              {recentSentiment
                .slice(0, 2)
                .map(
                  (item) =>
                    `${toDisplayText(item.code) ?? '-'} ${toDisplayText(item.sentiment) ?? 'neutral'}`,
                )
                .join(' / ')}
            </div>
          ) : null}
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">因子质量</div>
          <div>评级分布：{formatCountSummary(toDisplayCountRecord(factor?.rating_distribution)) || '-'}</div>
          <div>前视风险：{formatCountSummary(toDisplayCountRecord(factor?.lookahead_risk_distribution)) || '-'}</div>
          <div>
            OOS RankIC：
            {formatFactoryMetricValue(
              toDisplayNumber(factor?.oos_rank_ic_mean?.mean),
              4,
            )}
          </div>
          {recentFactor.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent:{' '}
              {recentFactor
                .slice(0, 2)
                .map(
                  (item) =>
                    `${toDisplayText(item.factor_name) ?? '-'} ${toDisplayText(item.rating) ?? 'unknown'}`,
                )
                .join(' / ')}
            </div>
          ) : null}
        </div>
      </div>
      {driftEntries.length ? (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">Drift Summary</div>
          <div className="flex flex-wrap gap-2">
            {driftEntries.map(({ key, payload }) => (
              <Badge
                key={key}
                variant={String(payload.status ?? '').toLowerCase() === 'degraded' ? 'warning' : 'neutral'}
              >
                {key}: {toDisplayText(payload.status) ?? 'unknown'}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function FactoryProviderDiagnosticsPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const diagnostics = factoryStatus?.recent_run_diagnostics ?? factoryStatus?.quality_baseline?.recent_run_diagnostics;
  const readinessDecisionCounts = toDisplayCountEntries(diagnostics?.readiness_decision_counts);
  const blockerReasonTop = (diagnostics?.blocker_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const warningReasonTop = (diagnostics?.warning_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedDiagnostics = diagnostics?.governed_pool_diagnostics;
  const governedWarningTop = (governedDiagnostics?.warning_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedBlockingTop = (governedDiagnostics?.blocking_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedExclusionTop = (governedDiagnostics?.exclusion_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedIneligibleTop = (governedDiagnostics?.ineligible_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const evidenceDebtDiagnostics = diagnostics?.evidence_debt_diagnostics;
  const evidenceDebtWarningTop = (evidenceDebtDiagnostics?.warning_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const providerWindowDiagnostics = diagnostics?.provider_control_diagnostics;
  const controlModeCounts = toDisplayCountEntries(diagnostics?.external_llm_provider_control_mode_counts);
  const controlReasonTop = (diagnostics?.external_llm_provider_control_reason_topn ?? [])
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const suppressedModeTop = (diagnostics?.suppressed_generator_mode_topn ?? [])
    .map((item) => ({
      mode: toDisplayText(item.mode) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.mode && Number.isFinite(item.count) && item.count > 0);
  const recentRuns = diagnostics?.recent_runs ?? [];
  const analyzedRunCount = toDisplayNumber(diagnostics?.analyzed_run_count);
  const blockedRunCount = toDisplayNumber(diagnostics?.readiness_blocked_count);
  const submitStageEnteredCount = toDisplayNumber(diagnostics?.submit_stage_entered_count);
  const submittedPositiveCount = toDisplayNumber(diagnostics?.submitted_positive_count);
  const suppressedRunCount = toDisplayNumber(diagnostics?.external_llm_provider_suppressed_run_count);
  const cooldownRunCount = toDisplayNumber(diagnostics?.external_llm_provider_cooldown_run_count);
  const governedBlockedRatioLatest = formatRatioPercent(
    toDisplayNumber(governedDiagnostics?.latest_governed_blocked_ratio),
  );
  const governedBlockedRatioMean = formatRatioPercent(
    toDisplayNumber(governedDiagnostics?.recent_governed_blocked_ratio_mean),
  );
  const governedStrictShortfallLatest = toDisplayNumber(
    governedDiagnostics?.latest_governed_candidate_pool_strict_shortfall_count,
  );
  const governedStrictShortfallMean = toDisplayNumber(
    governedDiagnostics?.recent_governed_candidate_pool_strict_shortfall_mean,
  );
  const governedBlockedCandidateLatest = toDisplayNumber(
    governedDiagnostics?.latest_governed_blocked_candidate_count,
  );
  const governedBlockedCandidateMean = toDisplayNumber(
    governedDiagnostics?.recent_governed_blocked_candidate_count_mean,
  );
  const evidenceDebtRatioLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.latest_budget_feedback_evidence_debt_ratio),
  );
  const evidenceDebtRatioMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.recent_budget_feedback_evidence_debt_ratio_mean),
  );
  const zeroSignalRatioLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.latest_budget_feedback_zero_signal_ratio),
  );
  const zeroSignalRatioMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.recent_budget_feedback_zero_signal_ratio_mean),
  );
  const forwardCoverageLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.latest_budget_feedback_forward_window_coverage_ratio),
  );
  const forwardCoverageMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.recent_budget_feedback_forward_window_coverage_ratio_mean),
  );
  const promotionReadyLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.latest_budget_feedback_promotion_ready_ratio),
  );
  const promotionReviewLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics?.latest_budget_feedback_promotion_review_coverage_ratio),
  );
  const providerAttemptActiveRuns = toDisplayNumber(providerWindowDiagnostics?.active_attempt_run_count);
  const providerAttemptZeroRuns = toDisplayNumber(providerWindowDiagnostics?.zero_attempt_run_count);
  const providerStageAttemptLatest = toDisplayNumber(providerWindowDiagnostics?.latest_stage_attempt_count);
  const providerStageAttemptMean = toDisplayNumber(providerWindowDiagnostics?.recent_stage_attempt_count_mean);
  const providerRealRequestLatest = toDisplayNumber(providerWindowDiagnostics?.latest_real_request_count);
  const providerRealRequestMean = toDisplayNumber(providerWindowDiagnostics?.recent_real_request_count_mean);
  const providerSkipRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.latest_compatibility_skip_ratio),
  );
  const providerSkipRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.recent_compatibility_skip_ratio_mean),
  );
  const providerFailureRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.latest_compatibility_failure_ratio),
  );
  const providerFailureRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.recent_compatibility_failure_ratio_mean),
  );
  const providerEffectiveRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.latest_effective_response_ratio),
  );
  const providerEffectiveRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics?.recent_effective_response_ratio_mean),
  );
  const hasGovernedBreakdown = [
    governedWarningTop.length,
    governedBlockingTop.length,
    governedExclusionTop.length,
    governedIneligibleTop.length,
    governedStrictShortfallLatest,
    governedBlockedCandidateLatest,
  ].some((value) => (typeof value === 'number' ? value > 0 : Boolean(value)));
  const hasEvidenceDebtBreakdown = [
    evidenceDebtWarningTop.length,
    evidenceDebtDiagnostics?.latest_budget_feedback_evidence_debt_ratio,
    evidenceDebtDiagnostics?.latest_budget_feedback_zero_signal_ratio,
    evidenceDebtDiagnostics?.latest_budget_feedback_forward_window_coverage_ratio,
  ].some(Boolean);
  const hasProviderWindow = [
    providerAttemptActiveRuns,
    providerAttemptZeroRuns,
    providerStageAttemptLatest,
    providerRealRequestLatest,
    providerWindowDiagnostics?.latest_compatibility_skip_ratio,
    providerWindowDiagnostics?.latest_effective_response_ratio,
  ].some(Boolean);
  const hasProviderDiagnostics = [
    analyzedRunCount,
    readinessDecisionCounts.length,
    blockerReasonTop.length,
    warningReasonTop.length,
    blockedRunCount,
    submitStageEnteredCount,
    submittedPositiveCount,
    controlModeCounts.length,
    suppressedRunCount,
    cooldownRunCount,
    hasGovernedBreakdown,
    hasEvidenceDebtBreakdown,
    hasProviderWindow,
    controlReasonTop.length,
    suppressedModeTop.length,
    recentRuns.length,
  ].some((value) => (typeof value === 'number' ? value > 0 : Boolean(value)));

  if (!hasProviderDiagnostics) return null;

  return (
    <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">默认运行阻断与 Provider 诊断</div>
        {analyzedRunCount != null ? <Badge variant="neutral">近 {analyzedRunCount} 轮</Badge> : null}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <FactoryMetric
          title="Readiness 阻断"
          value={formatCountWithRate(blockedRunCount, diagnostics?.readiness_blocked_rate)}
        />
        <FactoryMetric
          title="进入 Submit"
          value={formatCountWithRate(submitStageEnteredCount, diagnostics?.submit_stage_entered_rate)}
        />
        <FactoryMetric
          title="实际提交"
          value={formatCountWithRate(submittedPositiveCount, diagnostics?.submitted_positive_rate)}
        />
        <FactoryMetric
          title="Provider 抑制"
          value={formatCountWithRate(
            suppressedRunCount,
            diagnostics?.external_llm_provider_suppressed_run_rate,
          )}
        />
        <FactoryMetric
          title="Provider 冷却"
          value={formatCountWithRate(
            cooldownRunCount,
            diagnostics?.external_llm_provider_cooldown_run_rate,
          )}
        />
        <FactoryMetric title="控制模式数" value={controlModeCounts.length} />
      </div>

      {(readinessDecisionCounts.length > 0 || controlModeCounts.length > 0) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {readinessDecisionCounts.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">Readiness 决策分布</div>
              <div className="flex flex-wrap gap-2">
                {readinessDecisionCounts.map(([decision, count]) => (
                  <Badge key={decision} variant={previewBadgeVariant(decision)}>
                    {formatTaskLabel(decision)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {controlModeCounts.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">Provider 模式分布</div>
              <div className="flex flex-wrap gap-2">
                {controlModeCounts.map(([mode, count]) => (
                  <Badge key={mode} variant={providerControlBadgeVariant(mode)}>
                    {formatTaskLabel(mode)} {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {(hasGovernedBreakdown || hasEvidenceDebtBreakdown || hasProviderWindow) && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
          {hasGovernedBreakdown && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
              <div className="text-xs font-medium text-text-primary">Governed Pool 子因子</div>
              <div className="grid grid-cols-2 gap-3">
                <FactoryMetric
                  title="Blocked 比率"
                  value={`${governedBlockedRatioLatest} / ${governedBlockedRatioMean}`}
                />
                <FactoryMetric
                  title="Strict shortfall"
                  value={`${governedStrictShortfallLatest ?? '-'} / ${governedStrictShortfallMean == null ? '-' : formatFactoryMetricValue(governedStrictShortfallMean, 1)}`}
                />
                <FactoryMetric
                  title="Blocked 候选"
                  value={`${governedBlockedCandidateLatest ?? '-'} / ${governedBlockedCandidateMean == null ? '-' : formatFactoryMetricValue(governedBlockedCandidateMean, 1)}`}
                />
                <FactoryMetric
                  title="Source 候选"
                  value={toDisplayNumber(governedDiagnostics?.latest_governed_source_candidate_count) ?? '-'}
                />
              </div>
              {governedBlockingTop.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">Blocking 细项</div>
                  <div className="flex flex-wrap gap-2">
                    {governedBlockingTop.slice(0, 5).map((item) => (
                      <Badge key={`${item.reason}-${item.count}`} variant="danger">
                        {formatTaskLabel(item.reason)} {item.count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {governedExclusionTop.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">Exclusion 细项</div>
                  <div className="flex flex-wrap gap-2">
                    {governedExclusionTop.slice(0, 5).map((item) => (
                      <Badge key={`${item.reason}-${item.count}`} variant="warning">
                        {formatTaskLabel(item.reason)} {item.count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {(governedWarningTop.length > 0 || governedIneligibleTop.length > 0) && (
                <div className="space-y-2">
                  {governedWarningTop.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {governedWarningTop.slice(0, 4).map((item) => (
                        <Badge key={`${item.reason}-${item.count}`} variant="warning">
                          {formatTaskLabel(item.reason)} {item.count}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {governedIneligibleTop.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {governedIneligibleTop.slice(0, 4).map((item) => (
                        <Badge key={`${item.reason}-${item.count}`} variant="neutral">
                          {formatTaskLabel(item.reason)} {item.count}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {hasEvidenceDebtBreakdown && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
              <div className="text-xs font-medium text-text-primary">Evidence Debt 子因子</div>
              <div className="grid grid-cols-2 gap-3">
                <FactoryMetric title="Debt 比率" value={`${evidenceDebtRatioLatest} / ${evidenceDebtRatioMean}`} />
                <FactoryMetric title="零信号比率" value={`${zeroSignalRatioLatest} / ${zeroSignalRatioMean}`} />
                <FactoryMetric title="Forward 覆盖" value={`${forwardCoverageLatest} / ${forwardCoverageMean}`} />
                <FactoryMetric title="晋级 / 评审" value={`${promotionReadyLatest} / ${promotionReviewLatest}`} />
              </div>
              {evidenceDebtWarningTop.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary">Debt 预警拆分</div>
                  <div className="flex flex-wrap gap-2">
                    {evidenceDebtWarningTop.slice(0, 6).map((item) => (
                      <Badge key={`${item.reason}-${item.count}`} variant="warning">
                        {formatTaskLabel(item.reason)} {item.count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {hasProviderWindow && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
              <div className="text-xs font-medium text-text-primary">Provider 兼容性窗口</div>
              <div className="grid grid-cols-2 gap-3">
                <FactoryMetric title="活跃尝试轮数" value={providerAttemptActiveRuns ?? '-'} />
                <FactoryMetric title="零尝试轮数" value={providerAttemptZeroRuns ?? '-'} />
                <FactoryMetric
                  title="Stage attempts"
                  value={`${providerStageAttemptLatest ?? '-'} / ${providerStageAttemptMean == null ? '-' : formatFactoryMetricValue(providerStageAttemptMean, 1)}`}
                />
                <FactoryMetric
                  title="真实请求"
                  value={`${providerRealRequestLatest ?? '-'} / ${providerRealRequestMean == null ? '-' : formatFactoryMetricValue(providerRealRequestMean, 1)}`}
                />
                <FactoryMetric title="Skip 比率" value={`${providerSkipRatioLatest} / ${providerSkipRatioMean}`} />
                <FactoryMetric title="Failure 比率" value={`${providerFailureRatioLatest} / ${providerFailureRatioMean}`} />
              </div>
              <div className="text-xs text-text-secondary">
                Effective 响应：{providerEffectiveRatioLatest} / {providerEffectiveRatioMean}
              </div>
            </div>
          )}
        </div>
      )}

      {(blockerReasonTop.length > 0
        || warningReasonTop.length > 0
        || controlReasonTop.length > 0
        || suppressedModeTop.length > 0) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {blockerReasonTop.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">主要阻断原因</div>
              <div className="flex flex-wrap gap-2">
                {blockerReasonTop.slice(0, 6).map((item) => (
                  <Badge key={`${item.reason}-${item.count}`} variant="danger">
                    {formatTaskLabel(item.reason)} {item.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {warningReasonTop.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">主要预警原因</div>
              <div className="flex flex-wrap gap-2">
                {warningReasonTop.slice(0, 6).map((item) => (
                  <Badge key={`${item.reason}-${item.count}`} variant="warning">
                    {formatTaskLabel(item.reason)} {item.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {controlReasonTop.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">Provider 主要原因码</div>
              <div className="flex flex-wrap gap-2">
                {controlReasonTop.slice(0, 6).map((item) => (
                  <Badge key={`${item.reason}-${item.count}`} variant="warning">
                    {formatTaskLabel(item.reason)} {item.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {suppressedModeTop.length > 0 && (
            <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
              <div className="text-xs font-medium text-text-primary">被压制生成模式</div>
              <div className="flex flex-wrap gap-2">
                {suppressedModeTop.slice(0, 6).map((item) => (
                  <Badge key={`${item.mode}-${item.count}`} variant="warning">
                    {formatTaskLabel(item.mode)} {item.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {recentRuns.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">最近运行 Provider 轨迹</div>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
            {recentRuns.slice(0, 3).map((item, idx) => {
              const runId = toDisplayText(item.run_id) ?? `run-${idx + 1}`;
              const status = toDisplayText(item.status) ?? 'unknown';
              const readinessDecision = toDisplayText(item.readiness_decision) ?? 'unknown';
              const blockingReasons = toDisplayTextList(item.blocking_reason_codes, 3);
              const warningReasons = toDisplayTextList(item.warning_reason_codes, 3);
              const providerMode = toDisplayText(item.external_llm_provider_control_mode);
              const reasons = toDisplayTextList(item.external_llm_provider_control_reasons, 3);
              const suppressedModes = toDisplayTextList(item.suppressed_generator_modes, 3);
              const completedAt = toDisplayText(item.completed_at) ?? toDisplayText(item.started_at);
              const providerSuppressed = Boolean(item.external_llm_provider_suppressed);
              const providerCooldown = Boolean(item.external_llm_provider_cooldown);
              const governedBlockedRatio = formatRatioPercent(toDisplayNumber(item.governed_blocked_ratio));
              const evidenceDebtRatio = formatRatioPercent(
                toDisplayNumber(item.budget_feedback_evidence_debt_ratio),
              );
              const providerAttemptCount = toDisplayNumber(item.external_llm_stage_attempt_count) ?? 0;
              const providerRealRequestCount = toDisplayNumber(item.external_llm_real_request_count) ?? 0;
              const providerSkipRatio = formatRatioPercent(
                toDisplayNumber(item.external_llm_compatibility_skip_ratio),
              );
              const providerFailureRatio = formatRatioPercent(
                toDisplayNumber(item.external_llm_compatibility_failure_ratio),
              );
              const providerEffectiveRatio = formatRatioPercent(
                toDisplayNumber(item.external_llm_effective_response_ratio),
              );

              return (
                <div
                  key={`${runId}-${idx}`}
                  className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="font-medium text-text-primary">{runId}</div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={getFactoryRunStatusVariant(status)}>
                        {getFactoryRunStatusLabel(status)}
                      </Badge>
                      <Badge variant={previewBadgeVariant(readinessDecision)}>
                        readiness {formatTaskLabel(readinessDecision)}
                      </Badge>
                      {providerMode && (
                        <Badge variant={providerControlBadgeVariant(providerMode)}>
                          {formatTaskLabel(providerMode)}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div>时间：{shortFactoryRunTime(completedAt)}</div>
                  <div className="flex flex-wrap gap-2">
                    {blockingReasons.length > 0 ? <Badge variant="danger">存在阻断</Badge> : null}
                    {warningReasons.length > 0 ? <Badge variant="warning">存在预警</Badge> : null}
                    {providerSuppressed ? <Badge variant="warning">Provider 抑制</Badge> : null}
                    {providerCooldown ? <Badge variant="warning">Provider 冷却</Badge> : null}
                  </div>
                  <div>阻断：{blockingReasons.join(' / ') || '-'}</div>
                  <div>预警：{warningReasons.join(' / ') || '-'}</div>
                  <div>Governed / Debt：{governedBlockedRatio} / {evidenceDebtRatio}</div>
                  <div>Provider 探针 / 请求：{providerAttemptCount} / {providerRealRequestCount}</div>
                  <div>
                    Provider Skip / Failure / Effective：
                    {providerSkipRatio} / {providerFailureRatio} / {providerEffectiveRatio}
                  </div>
                  <div>原因：{reasons.join(' / ') || '-'}</div>
                  <div>受抑制模式：{suppressedModes.join(' / ') || '-'}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
