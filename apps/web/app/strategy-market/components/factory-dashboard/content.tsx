'use client';

import { Badge, SectionCard } from '@/components/ui';
import {
  formatCountSummary,
  formatFactoryMetricValue,
  formatMixedFlag,
  formatRatioPercent,
  formatTaskLabel,
  getFactoryRunStatusLabel,
  getFactoryRunStatusVariant,
  hasRunAuditMetrics,
  sortCountEntries,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  CapabilityBadge,
  DailySnapshotResponse,
  FactoryGenerationLaneQualityItem,
  FactoryQualityBaseline,
  FactoryQualitySummarySnapshot,
  FactoryRunDetailResponse,
  FactoryRunItem,
  FactoryRunSummary,
  FactoryStatusResponse,
  FactoryValidationFamilyQualityPanelItem,
  RunStatusFilter,
  TrendMetricKey,
} from '../../types';
import {
  FACTORY_TREND_METRICS,
  FactoryCapabilityStateStrip,
  FactoryRunComparisonTable,
  FactoryRunFailurePanel,
  FactoryRunTrendPanel,
} from './run-panels';
import {
  FactoryMetric,
  FactoryQualityAuditPanel,
  FactoryRunStructureDiagnosticsPanel,
  FactoryTaskStructurePanel,
} from './metrics';
import { FactoryGovernancePlanePanel } from './governance-plane';
import { FactoryFeedbackLoopPanel } from './feedback-loop';
import { FactoryHighConfidenceQualityPanel } from './high-confidence';
import {
  FactoryProviderDiagnosticsPanel,
  FactorySignalQualityRegistryPanel,
} from './signal-diagnostics';
import {
  distributionsDiffer,
  firstDefinedValue,
  formatArtifactScore,
  formatCountWithRate,
  formatGradeDistributionSummary,
  generationTierBadgeVariant,
  isObjectRecord,
  providerControlBadgeVariant,
  toDisplayCountEntries,
  toDisplayNumber,
  toDisplayText,
  toObjectArray,
} from './formatters';
import { FactoryResearchPlanePanel } from './research-plane';

/* ---------- small building blocks ---------- */

function FactoryFamilyQualityPanel({
  title,
  items,
}: {
  title: string;
  items: FactoryValidationFamilyQualityPanelItem[];
}) {
  if (items.length === 0) return null;

  return (
    <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="text-xs font-medium text-text-primary">{title}</div>
      <div className="space-y-2">
        {items.slice(0, 4).map((item, idx) => {
          const family = toDisplayText(item.strategy_family) ?? 'unknown';
          const holdingBucket = toDisplayText(item.holding_period_bucket) ?? 'unknown';
          const validationFocus = toDisplayText(item.validation_focus) ?? 'unknown';
          const rawARate = firstDefinedValue(item.family_raw_a_rate, item.raw_validation_a_rate);
          const rawBRate = firstDefinedValue(item.family_raw_b_rate, item.raw_validation_b_rate);
          const meanTradeDensity = firstDefinedValue(item.family_mean_trade_density, item.mean_trade_density);
          const meanPostCostSharpe = firstDefinedValue(
            item.family_mean_post_cost_sharpe,
            item.mean_post_cost_sharpe,
          );
          const meanDsr = firstDefinedValue(item.family_mean_dsr, item.mean_deflated_sharpe_ratio);
          const meanPbo = firstDefinedValue(item.family_mean_pbo, item.mean_pbo);

          return (
            <div
              key={`${family}-${holdingBucket}-${validationFocus}-${idx}`}
              className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="font-medium text-text-primary">
                  {family} · {holdingBucket} · {validationFocus}
                </div>
                <Badge variant="neutral">{item.strategy_count ?? 0} 个样本</Badge>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <div>Raw A / B：{formatRatioPercent(rawARate)} / {formatRatioPercent(rawBRate)}</div>
                <div>Strict / Live：{formatCountWithRate(item.strict_incubation_ready_count, item.strict_incubation_ready_rate)} / {formatCountWithRate(item.live_candidate_ready_count, item.live_candidate_ready_rate)}</div>
                <div>Raw B及以上：{formatCountWithRate(item.raw_b_or_above_count, item.raw_b_or_above_rate)}</div>
                <div>Raw B 中 Strict：{formatRatioPercent(item.strict_ready_given_raw_b_rate)}</div>
                <div>Raw B 中 Live：{formatRatioPercent(item.live_ready_given_raw_b_rate)}</div>
                <div>Raw 分布：{formatGradeDistributionSummary(item.raw_validation_grade_distribution)}</div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div>Trade density：{formatArtifactScore(meanTradeDensity, 4)}</div>
                <div>Post-cost Sharpe：{formatArtifactScore(meanPostCostSharpe, 4)}</div>
                <div>DSR：{formatArtifactScore(meanDsr, 4)}</div>
                <div>PBO：{formatArtifactScore(meanPbo, 4)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FactoryGenerationLanePanel({
  title,
  items,
  description,
}: {
  title: string;
  items: FactoryGenerationLaneQualityItem[];
  description?: string | null;
}) {
  if (items.length === 0) return null;

  return (
    <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        <Badge variant="neutral">
          {items.reduce((sum, item) => sum + Number(item.strategy_count ?? 0), 0)} 个样本
        </Badge>
      </div>
      {description ? (
        <div className="text-xs text-text-secondary">{description}</div>
      ) : null}
      <div className="space-y-2">
        {items.slice(0, 5).map((item, idx) => {
          const laneLabel = toDisplayText(item.lane_label) ?? 'Unknown';
          const generationTier = toDisplayText(item.generation_tier) ?? 'unknown';
          const generatorModeSummary = formatCountSummary(item.generator_mode_counts ?? {});
          const statusSummary = formatCountSummary(item.status_counts ?? {});
          const familySummary = formatCountSummary(item.strategy_family_counts ?? {});
          return (
            <div
              key={`${laneLabel}-${generationTier}-${idx}`}
              className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="font-medium text-text-primary">{laneLabel}</div>
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant={generationTierBadgeVariant(generationTier)}>{generationTier}</Badge>
                  <Badge variant="neutral">{item.strategy_count ?? 0} 个样本</Badge>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <div>Raw A / B：{formatRatioPercent(item.raw_validation_a_rate)} / {formatRatioPercent(item.raw_validation_b_rate)}</div>
                <div>Raw B及以上：{formatCountWithRate(item.raw_b_or_above_count, item.raw_b_or_above_rate)}</div>
                <div>Strict / Live：{formatCountWithRate(item.strict_incubation_ready_count, item.strict_incubation_ready_rate)} / {formatCountWithRate(item.live_candidate_ready_count, item.live_candidate_ready_rate)}</div>
                <div>Promotion-ready：{formatCountWithRate(item.promotion_ready_count, item.promotion_ready_rate)}</div>
                <div>Quality pass：{formatCountWithRate(item.quality_passed_count, item.quality_pass_rate)}</div>
                <div>Raw 分布：{formatGradeDistributionSummary(item.raw_validation_grade_distribution)}</div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <div>生成模式：{generatorModeSummary || '-'}</div>
                <div>状态分布：{statusSummary || '-'}</div>
                <div>Family 分布：{familySummary || '-'}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FactoryQualityLensPanel({
  title,
  summary,
  description,
}: {
  title: string;
  summary: Partial<FactoryRunSummary> | FactoryQualitySummarySnapshot | Record<string, unknown> | null | undefined;
  description?: string;
}) {
  const payload: Record<string, unknown> = isObjectRecord(summary) ? summary : {};
  const rawDistribution = payload.raw_validation_grade_distribution;
  const effectiveDistribution = firstDefinedValue(
    payload.effective_validation_grade_distribution,
    payload.validation_grade_distribution,
  );
  const familyPanel = toObjectArray(payload.validation_family_quality_panel) as FactoryValidationFamilyQualityPanelItem[];
  const hasQualityData = [
    rawDistribution,
    effectiveDistribution,
    payload.raw_validation_total_score_mean,
    payload.raw_validation_b_rate,
    payload.strict_incubation_ready_rate,
    payload.live_candidate_ready_rate,
    payload.raw_b_or_above_rate,
    payload.strict_ready_given_raw_b_rate,
    payload.live_ready_given_raw_b_rate,
    familyPanel.length,
  ].some((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (isObjectRecord(value)) return Object.keys(value).length > 0;
    return value != null && value !== '';
  });

  if (!hasQualityData) return null;

  const hasEffectiveAdjustment = distributionsDiffer(rawDistribution, effectiveDistribution);

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        <Badge variant={hasEffectiveAdjustment ? 'warning' : 'success'}>
          {hasEffectiveAdjustment ? '存在有效等级修正' : 'raw / effective 一致'}
        </Badge>
      </div>
      {description ? (
        <div className="text-xs text-text-secondary">{description}</div>
      ) : null}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <FactoryMetric title="Raw A率" value={formatRatioPercent(toDisplayNumber(payload.raw_validation_a_rate))} />
        <FactoryMetric title="Raw B率" value={formatRatioPercent(toDisplayNumber(payload.raw_validation_b_rate))} />
        <FactoryMetric title="Raw B及以上" value={formatCountWithRate(payload.raw_b_or_above_count, payload.raw_b_or_above_rate)} />
        <FactoryMetric title="Strict就绪" value={formatCountWithRate(payload.strict_incubation_ready_count, payload.strict_incubation_ready_rate)} />
        <FactoryMetric title="Live就绪" value={formatCountWithRate(payload.live_candidate_ready_count, payload.live_candidate_ready_rate)} />
        <FactoryMetric title="Raw B中 Strict / Live" value={`${formatRatioPercent(toDisplayNumber(payload.strict_ready_given_raw_b_rate))} / ${formatRatioPercent(toDisplayNumber(payload.live_ready_given_raw_b_rate))}`} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-text-secondary">
        <div>原始分布：{formatGradeDistributionSummary(rawDistribution)}</div>
        <div>有效分布：{formatGradeDistributionSummary(effectiveDistribution)}</div>
        <div>
          Raw 分数：均值 {formatArtifactScore(payload.raw_validation_total_score_mean, 2)} / P50 {formatArtifactScore(payload.raw_validation_total_score_p50, 2)} / P90 {formatArtifactScore(payload.raw_validation_total_score_p90, 2)}
        </div>
      </div>
      <FactoryFamilyQualityPanel title="Family 质量面板" items={familyPanel} />
    </div>
  );
}

function FactoryQualityBaselinePanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const qualityBaseline: Partial<FactoryQualityBaseline> = factoryStatus?.quality_baseline ?? {};
  const cohort: NonNullable<FactoryQualityBaseline['submitted_strategy_cohort']> =
    qualityBaseline.submitted_strategy_cohort ?? {};
  const statusCounts = toDisplayCountEntries(cohort.status_counts);

  if (!qualityBaseline.contract_version && Object.keys(cohort).length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <FactoryQualityLensPanel
        title="已提交 Cohort Raw 质量口径"
        summary={cohort}
        description="聚焦 submitted / incubating / listed 三类工厂策略，看 strict / live 提升是否建立在 raw B/A 增长上。"
      />
      <FactoryGenerationLanePanel
        title="生成层级对照基线"
        items={Array.isArray(cohort.generation_lane_quality_panel)
          ? cohort.generation_lane_quality_panel
          : []}
        description={toDisplayText(cohort.generation_lane_definition)}
      />
      {(statusCounts.length > 0
        || cohort.strict_live_alignment_gap_count != null
        || cohort.validation_grade_d_strict_incubation_pass_count != null
        || cohort.validation_grade_d_promotion_ready_count != null) && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">Cohort 对齐与风险备注</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <FactoryMetric title="工厂策略数" value={cohort.factory_strategy_count ?? 0} />
            <FactoryMetric title="Strict/Live 缺口" value={formatCountWithRate(cohort.strict_live_alignment_gap_count, cohort.strict_live_alignment_gap_rate)} />
            <FactoryMetric title="D级仍过 Strict" value={formatCountWithRate(cohort.validation_grade_d_strict_incubation_pass_count, cohort.validation_grade_d_strict_incubation_pass_rate)} />
            <FactoryMetric title="D级仍可晋级" value={formatCountWithRate(cohort.validation_grade_d_promotion_ready_count, cohort.validation_grade_d_promotion_ready_rate)} />
          </div>
          {statusCounts.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">状态分布</div>
              <div className="flex flex-wrap gap-2">
                {statusCounts.map(([status, count]) => (
                  <Badge key={status} variant="neutral">
                    {formatTaskLabel(status)} {count}
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

function FactoryRunDetailPanel({
  detail,
  loading,
  error,
}: {
  detail: FactoryRunDetailResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <div className="mt-3 text-xs text-text-secondary">加载运行详情...</div>;
  }
  if (error) {
    return <div className="mt-3 text-xs text-danger">加载详情失败：{error}</div>;
  }
  if (!detail) {
    return <div className="mt-3 text-xs text-text-secondary">暂无运行详情</div>;
  }

  const snapshotRows = Object.entries(detail.snapshot_summary ?? {});
  const stageRows = Object.entries(detail.stages ?? {});
  const summary = detail.summary ?? {};

  return (
    <div className="mt-3 rounded border border-border bg-surface px-3 py-3 space-y-3">
      <div>
        <div className="text-xs font-medium">运行标识</div>
        <div className="mt-1 text-xs text-text-secondary break-all">{detail.run_id ?? '-'}</div>
      </div>

      <div>
        <div className="text-xs font-medium">运行摘要</div>
        <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
          <div>候选生成：{summary.candidates_spawned ?? 0}</div>
          <div>研究任务：{summary.autonomy_task_count ?? summary.autonomy_task_briefs?.length ?? 0}</div>
          <div>事件任务：{summary.event_task_count ?? 0}</div>
          <div>快照任务：{summary.snapshot_task_count ?? 0}</div>
          <div>提交数：{summary.submitted ?? 0}</div>
          <div>质检通过：{summary.passed_quality_gate ?? 0}</div>
          <div>淘汰数：{summary.eliminated ?? 0}</div>
          <div>混合模式：{formatMixedFlag(summary.event_snapshot_mixed)}</div>
        </div>
      </div>

      <FactoryTaskStructurePanel summary={summary} />
      <FactoryQualityAuditPanel summary={summary} />
      <FactoryQualityLensPanel
        title="运行质量口径"
        summary={summary}
        description="这里直接看 raw / effective 分布，以及 strict / live 是否由 raw B/A 样本支撑。"
      />
      <FactoryFeedbackLoopPanel
        title="生命周期反馈闭环"
        summary={summary}
        feedbackSummary={detail.feedback_summary ?? null}
      />
      <FactoryResearchPlanePanel detail={detail} />
      <FactoryGovernancePlanePanel detail={detail} />

      {snapshotRows.length > 0 && (
        <div>
          <div className="text-xs font-medium">快照摘要</div>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
            {snapshotRows.map(([key, value]) => (
              <div key={key}>{key}: {String(value ?? '-')}</div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs font-medium">阶段结果</div>
        {stageRows.length > 0 ? (
          <div className="mt-1 space-y-2">
            {stageRows.map(([stage, payload]) => (
              <div key={stage} className="rounded border border-border px-2 py-2 text-xs text-text-secondary">
                <div className="font-medium text-text-primary mb-1">{stage}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(payload ?? {}).map(([key, value]) => (
                    <div key={key}>{key}: {String(value ?? '-')}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-1 text-xs text-text-secondary">暂无阶段详情</div>
        )}
      </div>

      {detail.error && (
        <div className="text-xs text-danger">错误信息：{detail.error}</div>
      )}
    </div>
  );
}

/* ---------- main export ---------- */

export type FactoryDashboardProps = {
  factoryStatus: FactoryStatusResponse | null | undefined;
  latestSnapshot: DailySnapshotResponse | null;
  capabilityBadges: CapabilityBadge[];
  capabilitiesError: string | null;
  dailySnapshotError: string | null;
  factorySummary: NonNullable<FactoryStatusResponse['last_summary']>;
  snapshotCompletionRatio?: number | null;
  snapshotDegraded: boolean;
  snapshotFailureCount: number;
  /* run factory */
  onRunFactory: () => void;
  runFactoryPending: boolean;
  runFactoryError: string | null;
  /* runs */
  factoryRunsLoading: boolean;
  factoryRuns: FactoryRunItem[];
  filteredRuns: FactoryRunItem[];
  failedRuns: FactoryRunItem[];
  comparableRuns: FactoryRunItem[];
  trendRuns: FactoryRunItem[];
  /* filters / expand */
  runStatusFilter: RunStatusFilter;
  onRunStatusFilterChange: (value: RunStatusFilter) => void;
  trendMetricKey: TrendMetricKey;
  onTrendMetricKeyChange: (value: TrendMetricKey) => void;
  expandedRunId: string | null;
  onExpandedRunIdChange: (id: string | null) => void;
  expandedRun: FactoryRunDetailResponse | null;
  expandedRunLoading: boolean;
  expandedRunError: string | null;
};

export function FactoryDashboard({
  factoryStatus,
  latestSnapshot,
  capabilityBadges,
  capabilitiesError,
  dailySnapshotError,
  factorySummary,
  snapshotCompletionRatio,
  snapshotDegraded,
  snapshotFailureCount,
  onRunFactory,
  runFactoryPending,
  runFactoryError,
  factoryRunsLoading,
  factoryRuns,
  filteredRuns,
  failedRuns,
  comparableRuns,
  trendRuns,
  runStatusFilter,
  onRunStatusFilterChange,
  trendMetricKey,
  onTrendMetricKeyChange,
  expandedRunId,
  onExpandedRunIdChange,
  expandedRun,
  expandedRunLoading,
  expandedRunError,
}: FactoryDashboardProps) {
  return (
    <SectionCard className="mt-4 p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="m-0">策略工厂运行态</h3>
          <p className="m-0 mt-1 text-sm text-text-secondary">
            调度状态：{factoryStatus?.running ? '运行中' : '未启动'} · 上次运行：{factoryStatus?.last_run ?? '暂无'}
            {factoryStatus?.spec_completeness_mode ? ` · 完整性模式：${factoryStatus.spec_completeness_mode}` : ''}
            {latestSnapshot?.snapshot_date ? ` · 最新快照：${latestSnapshot.snapshot_date}` : ''}
          </p>
        </div>
        <button
          onClick={onRunFactory}
          disabled={runFactoryPending}
          className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
        >
          {runFactoryPending ? '运行中...' : '立即运行一轮工厂'}
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3 mt-4 text-sm">
        <FactoryMetric title="候选生成" value={factorySummary.candidates_spawned ?? 0} />
        <FactoryMetric title="AI生成" value={factorySummary.autonomy_generated ?? 0} />
        <FactoryMetric title="通过回测" value={factorySummary.candidates_passed_backtest ?? 0} />
        <FactoryMetric title="去重后" value={factorySummary.candidates_after_dedup ?? 0} />
        <FactoryMetric title="质检通过" value={factorySummary.passed_quality_gate ?? 0} />
        <FactoryMetric title="快照完成率" value={formatRatioPercent(snapshotCompletionRatio)} />
        <FactoryMetric title="快照状态" value={snapshotDegraded ? '降级' : '正常'} />
        <FactoryMetric title="快照异常数" value={snapshotFailureCount} />
        <FactoryMetric title="淘汰数" value={factorySummary.eliminated ?? 0} />
        <FactoryMetric title="耗时(秒)" value={factorySummary.elapsed_seconds ?? '-'} />
      </div>
      <FactoryTaskStructurePanel summary={factorySummary} />
      <FactoryQualityAuditPanel summary={factorySummary} />
      <FactoryQualityLensPanel
        title="最近一轮 Raw 质量口径"
        summary={factorySummary}
        description="优先看原始 validation 等级，再看 effective 等级与 strict / live 对齐情况，避免把门禁修正误当成质量提升。"
      />
      <FactoryQualityBaselinePanel factoryStatus={factoryStatus} />
      <FactoryHighConfidenceQualityPanel factoryStatus={factoryStatus} />
      <FactorySignalQualityRegistryPanel factoryStatus={factoryStatus} />
      <FactoryProviderDiagnosticsPanel factoryStatus={factoryStatus} />
      <FactoryFeedbackLoopPanel title="P3 反馈闭环" summary={factorySummary} compact />
      <FactoryCapabilityStateStrip factoryStatus={factoryStatus} />
      <div className="mt-3 flex flex-wrap gap-2">
        {capabilityBadges.map((item) => (
          <Badge key={item.key} variant={item.enabled ? 'success' : 'neutral'}>
            {item.label}{item.enabled ? '已接入' : '未接入'}
          </Badge>
        ))}
      </div>
      {latestSnapshot && (
        <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-2 text-xs text-text-secondary space-y-1">
          <div>
            恐慌贪婪：{latestSnapshot.fear_greed_index ?? '-'} · 已上架策略：{latestSnapshot.summary?.listed_count ?? '-'} · 缺失字段：{latestSnapshot.missing_fields?.length ?? 0}
          </div>
          {latestSnapshot.hot_sectors?.length ? <div>热点板块：{latestSnapshot.hot_sectors.slice(0, 4).join('、')}</div> : null}
          {snapshotFailureCount > 0 ? (
            <div className={snapshotDegraded ? 'text-warning' : ''}>
              快照异常：{(latestSnapshot.failure_reasons ?? []).slice(0, 3).join('；') || '存在异常但未返回原因'}
            </div>
          ) : null}
        </div>
      )}
      {capabilitiesError && <p className="mt-3 mb-0 text-sm text-danger">能力接口加载失败：{capabilitiesError}</p>}
      {dailySnapshotError && <p className="mt-3 mb-0 text-sm text-danger">日快照加载失败：{dailySnapshotError}</p>}
      {factoryStatus?.last_result?.status === 'failed' && (
        <p className="mt-3 mb-0 text-sm text-danger">最近一次工厂运行失败：{factoryStatus?.last_result?.error ?? '未知错误'}</p>
      )}
      {factoryStatus?.last_result?.status === 'partial' && (
        <p className="mt-3 mb-0 text-sm text-warning">最近一次工厂运行为降级完成，建议优先查看阶段详情和降级原因。</p>
      )}
      {factoryStatus?.last_result?.status === 'skipped' && (
        <p className="mt-3 mb-0 text-sm text-text-secondary">最近一次工厂运行被跳过，通常是运行开关关闭或 readiness 未通过。</p>
      )}
      {runFactoryError && <p className="mt-3 mb-0 text-sm text-danger">{runFactoryError}</p>}
      {factoryRunsLoading && <p className="mt-3 mb-0 text-sm text-text-secondary">加载运行历史...</p>}
      {!factoryRunsLoading && factoryRuns.length === 0 && (
        <p className="mt-3 mb-0 text-sm text-text-secondary">暂无工厂运行历史</p>
      )}
      {factoryRuns.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-text-secondary">状态筛选：</span>
          {[
            { key: 'all', label: '全部' },
            { key: 'success', label: '成功' },
            { key: 'partial', label: '部分成功' },
            { key: 'skipped', label: '已跳过' },
            { key: 'failed', label: '失败' },
          ].map((item) => (
            <button
              key={item.key}
              onClick={() => onRunStatusFilterChange(item.key as RunStatusFilter)}
              className={`px-2 py-1 text-xs rounded border cursor-pointer ${runStatusFilter === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
      {!factoryRunsLoading && factoryRuns.length > 0 && filteredRuns.length === 0 && (
        <p className="mt-3 mb-0 text-sm text-text-secondary">当前筛选条件下暂无运行记录</p>
      )}
      {filteredRuns.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-sm font-medium">最近运行历史</div>
          {filteredRuns.map((item) => (
            <div key={item.run_id ?? item.started_at} className="rounded border border-border bg-surface-alt px-3 py-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <Badge variant={getFactoryRunStatusVariant(item.status)}>
                  {getFactoryRunStatusLabel(item.status)}
                </Badge>
                <span className="text-text-secondary">{item.completed_at ?? item.started_at ?? '-'}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 text-xs text-text-secondary">
                <span>候选 {item.summary?.candidates_spawned ?? 0}</span>
                <span>去重后 {item.summary?.candidates_after_dedup ?? 0}</span>
                <span>提交 {item.summary?.submitted ?? 0}</span>
                <span>质检通过 {item.summary?.passed_quality_gate ?? 0}</span>
                <span>淘汰 {item.summary?.eliminated ?? 0}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="neutral">
                  研究任务 {item.summary?.autonomy_task_count ?? item.summary?.autonomy_task_briefs?.length ?? 0}
                </Badge>
                <Badge variant="neutral">事件 {item.summary?.event_task_count ?? 0}</Badge>
                <Badge variant="neutral">快照 {item.summary?.snapshot_task_count ?? 0}</Badge>
                <Badge variant={item.summary?.event_snapshot_mixed ? 'success' : 'neutral'}>
                  混合 {formatMixedFlag(item.summary?.event_snapshot_mixed)}
                </Badge>
                {(item.summary?.partial_stage_count ?? 0) > 0 ? (
                  <Badge variant="warning">
                    降级阶段 {item.summary?.partial_stage_count}
                  </Badge>
                ) : null}
                {(item.summary?.failed_stage_count ?? 0) > 0 ? (
                  <Badge variant="danger">
                    失败阶段 {item.summary?.failed_stage_count}
                  </Badge>
                ) : null}
                {(item.summary?.skipped_stage_count ?? 0) > 0 ? (
                  <Badge variant="neutral">
                    跳过阶段 {item.summary?.skipped_stage_count}
                  </Badge>
                ) : null}
                {(item.summary?.budget_feedback_family_count ?? 0) > 0 ? (
                  <Badge variant="info">
                    反馈家族 {item.summary?.budget_feedback_family_count}
                  </Badge>
                ) : null}
                {(item.summary?.budget_feedback_promotion_review_count ?? 0) > 0 ? (
                  <Badge variant="success">
                    晋级评审 {item.summary?.budget_feedback_promotion_review_count}
                  </Badge>
                ) : null}
                {(item.summary?.blocked_feedback_task_count ?? 0) > 0 ? (
                  <Badge variant="warning">
                    阻断任务 {item.summary?.blocked_feedback_task_count}
                  </Badge>
                ) : null}
                {(item.summary?.planned_feedback_cooldown_task_count ?? 0) > 0 ? (
                  <Badge variant="warning">
                    冷却任务 {item.summary?.planned_feedback_cooldown_task_count}
                  </Badge>
                ) : null}
                {item.summary?.external_llm_provider_control_mode ? (
                  <Badge variant={providerControlBadgeVariant(item.summary.external_llm_provider_control_mode)}>
                    Provider {formatTaskLabel(item.summary.external_llm_provider_control_mode)}
                  </Badge>
                ) : null}
                {item.summary?.external_llm_provider_suppressed ? (
                  <Badge variant="warning">Provider 抑制</Badge>
                ) : null}
                {item.summary?.external_llm_provider_cooldown ? (
                  <Badge variant="warning">Provider 冷却</Badge>
                ) : null}
                {(item.summary?.suppressed_generator_modes?.length ?? 0) > 0 ? (
                  <Badge variant="warning">
                    受抑制模式 {item.summary?.suppressed_generator_modes?.length ?? 0}
                  </Badge>
                ) : null}
                {(() => {
                  const [topSource] = sortCountEntries(item.summary?.task_source_counts);
                  return topSource ? (
                    <Badge variant="neutral">
                      主导来源 {formatTaskLabel(topSource[0])} {topSource[1]}
                    </Badge>
                  ) : null;
                })()}
                {(() => {
                  const [topType] = sortCountEntries(item.summary?.scanner_task_types);
                  return topType ? (
                    <Badge variant="info">
                      主导机会 {formatTaskLabel(topType[0])} {topType[1]}
                    </Badge>
                  ) : null;
                })()}
              </div>
              {hasRunAuditMetrics(item.summary) ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {item.summary?.deflated_sharpe_ratio_avg != null ? (
                    <Badge variant="info">
                      DSR 均值 {formatFactoryMetricValue(item.summary?.deflated_sharpe_ratio_avg, 2)}
                    </Badge>
                  ) : null}
                  <Badge variant={(item.summary?.high_pbo_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    高 PBO {item.summary?.high_pbo_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.formal_multiple_testing_count ?? 0) > 0 ? 'success' : 'neutral'}>
                    正式多重检验 {item.summary?.formal_multiple_testing_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.weak_white_reality_check_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    弱 White RC {item.summary?.weak_white_reality_check_count ?? 0}
                  </Badge>
                  <Badge variant={(item.summary?.weak_hansen_spa_count ?? 0) > 0 ? 'warning' : 'neutral'}>
                    弱 Hansen SPA {item.summary?.weak_hansen_spa_count ?? 0}
                  </Badge>
                </div>
              ) : null}
              <div className="mt-2 text-xs text-text-secondary">
                耗时：{item.elapsed_seconds ?? item.summary?.elapsed_seconds ?? '-'} 秒
              </div>
              {(item.summary?.skip_reason || (item.summary?.skip_reasons ?? []).length > 0) && (
                <div className="mt-2 text-xs text-text-secondary">
                  跳过原因：{item.summary?.skip_reason ?? item.summary?.skip_reasons?.join(' / ')}
                </div>
              )}
              {(item.summary?.external_llm_provider_control_reasons?.length ?? 0) > 0 && (
                <div className="mt-2 text-xs text-text-secondary">
                  Provider 原因：{item.summary?.external_llm_provider_control_reasons?.map((item) => formatTaskLabel(item)).join(' / ')}
                </div>
              )}
              {item.error && <div className="mt-2 text-xs text-danger">错误：{item.error}</div>}
              {item.run_id && (
                <div className="mt-3">
                  <button
                    onClick={() => onExpandedRunIdChange(expandedRunId === item.run_id ? null : item.run_id ?? null)}
                    className="px-2 py-1 text-xs rounded border border-border cursor-pointer hover:bg-surface"
                  >
                    {expandedRunId === item.run_id ? '收起详情' : '查看详情'}
                  </button>
                </div>
              )}
              {expandedRunId === item.run_id && (
                <FactoryRunDetailPanel
                  loading={expandedRunLoading}
                  detail={expandedRun}
                  error={expandedRunError}
                />
              )}
            </div>
          ))}
        </div>
      )}
      {comparableRuns.length > 1 && (
        <div className="mt-5">
          <div className="text-sm font-medium mb-2">最近运行对比</div>
          <FactoryRunComparisonTable runs={comparableRuns} />
        </div>
      )}
      {trendRuns.length > 1 && (
        <div className="mt-5">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div className="text-sm font-medium">运行趋势</div>
            <div className="flex flex-wrap items-center gap-2">
                {FACTORY_TREND_METRICS.map((item) => (
                <button
                  key={item.key}
                  onClick={() => onTrendMetricKeyChange(item.key as TrendMetricKey)}
                  className={`px-2 py-1 text-xs rounded border cursor-pointer ${trendMetricKey === item.key ? 'border-primary text-primary bg-primary/5' : 'border-border hover:bg-surface'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <FactoryRunTrendPanel runs={trendRuns} metricKey={trendMetricKey} />
          <FactoryRunStructureDiagnosticsPanel runs={trendRuns} />
        </div>
      )}
      {failedRuns.length > 0 && (
        <div className="mt-5">
          <div className="text-sm font-medium mb-2">失败原因聚合</div>
          <FactoryRunFailurePanel runs={failedRuns} totalRuns={factoryRuns.length} />
        </div>
      )}
    </SectionCard>
  );
}
