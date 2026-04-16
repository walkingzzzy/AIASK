'use client';

import { Badge, SectionCard } from '@/components/ui';
import {
  aggregateSummaryCounts,
  detectFailedStage,
  formatCountSummary,
  formatFactoryMetricValue,
  formatMixedFlag,
  formatRatioPercent,
  formatTaskLabel,
  getFactoryRunErrorFingerprint,
  getFactoryRunStatusLabel,
  getFactoryRunStatusVariant,
  hasRunAuditMetrics,
  normalizeFactoryRunError,
  shortFactoryRunTime,
  sortCountEntries,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  CapabilityBadge,
  DailySnapshotResponse,
  FactoryGovernanceDedupArtifact,
  FactoryGovernanceDedupBrief,
  FactoryGovernanceEvidenceArtifact,
  FactoryGovernanceEvidenceStrategyBrief,
  FactoryGenerationLaneQualityItem,
  FactoryGateStageResult,
  FactoryGovernanceGateArtifact,
  FactoryGovernancePlaneArtifact,
  FactoryPredictionTraceLedgerEntry,
  FactoryPredictionTraceLedgerNode,
  FactoryPredictionTraceLedgerSummary,
  FactoryPredictionTraceSummary,
  FactoryProtocolVersionsSummary,
  FactoryGovernanceSubmissionArtifact,
  FactoryGovernanceStrategyBrief,
  FactoryQualityBaseline,
  FactoryQualitySummarySnapshot,
  FactoryRunDetailResponse,
  FactoryRunItem,
  FactoryRunSummary,
  FactoryStatusResponse,
  FactoryValidationFamilyQualityPanelItem,
  RunStatusFilter,
  StrategyPredictionTraceGateDecisions,
  TrendMetricKey,
} from '../types';

/* ---------- small building blocks ---------- */

function FactoryMetric({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded border border-border px-3 py-2 bg-surface-alt">
      <div className="text-xs text-text-secondary">{title}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function FactoryTaskStructurePanel({
  summary,
}: {
  summary: FactoryRunSummary;
}) {
  const taskSourceEntries = Object.entries(summary.task_source_counts ?? {});
  const scannerTaskTypeEntries = Object.entries(summary.scanner_task_types ?? {});
  const autonomyTaskBriefs = summary.autonomy_task_briefs ?? [];
  const hasTaskSummary = [
    summary.autonomy_task_count,
    summary.event_task_count,
    summary.snapshot_task_count,
  ].some((value) => value != null)
    || taskSourceEntries.length > 0
    || scannerTaskTypeEntries.length > 0
    || autonomyTaskBriefs.length > 0;

  if (!hasTaskSummary) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3 text-xs text-text-secondary space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="font-medium text-text-primary">任务结构</span>
        <span>{summary.event_snapshot_mixed ? '事件 + 快照混合' : '单来源任务'}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>研究任务：{summary.autonomy_task_count ?? autonomyTaskBriefs.length ?? '-'}</div>
        <div>事件任务：{summary.event_task_count ?? 0}</div>
        <div>快照任务：{summary.snapshot_task_count ?? 0}</div>
        <div>混合模式：{summary.event_snapshot_mixed ? '是' : '否'}</div>
      </div>
      {taskSourceEntries.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">来源分布</div>
          <div className="flex flex-wrap gap-2">
            {taskSourceEntries.map(([key, count]) => (
              <Badge key={key} variant="neutral">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {scannerTaskTypeEntries.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">机会类型</div>
          <div className="flex flex-wrap gap-2">
            {scannerTaskTypeEntries.slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="info">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {autonomyTaskBriefs.length > 0 && (
        <div className="space-y-2">
          <div className="font-medium text-text-primary">最近任务摘要</div>
          <div className="space-y-1">
            {autonomyTaskBriefs.slice(0, 4).map((item, idx) => (
              <div
                key={item.task_id ?? `${item.task_source ?? 'task'}-${idx}`}
                className="rounded border border-border bg-surface px-2 py-2"
              >
                <div className="text-text-primary">
                  {formatTaskLabel(item.opportunity_type)} · {formatTaskLabel(item.task_source)}
                </div>
                <div className="mt-1">
                  task_id: {item.task_id ?? '-'} · 预算 {item.generated_count ?? 0}/{item.generation_limit ?? '-'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FactoryRunStructureDiagnosticsPanel({ runs }: { runs: FactoryRunItem[] }) {
  const latest = runs[runs.length - 1];
  const earliest = runs[0];
  const mixedRunCount = runs.filter((run) => run.summary?.event_snapshot_mixed).length;
  const mixedRunRatio = runs.length > 0 ? Math.round((mixedRunCount / runs.length) * 100) : 0;
  const aggregatedSources = aggregateSummaryCounts(runs, (summary) => summary.task_source_counts);
  const aggregatedTypes = aggregateSummaryCounts(runs, (summary) => summary.scanner_task_types);
  const hasStructureData = mixedRunCount > 0
    || Object.keys(aggregatedSources).length > 0
    || Object.keys(aggregatedTypes).length > 0
    || Boolean(latest?.summary?.task_source_counts)
    || Boolean(earliest?.summary?.task_source_counts);

  if (!hasStructureData) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="混合运行次数" value={mixedRunCount} />
        <FactoryMetric title="混合占比" value={`${mixedRunRatio}%`} />
        <FactoryMetric title="累计来源类别" value={Object.keys(aggregatedSources).length || 0} />
        <FactoryMetric title="累计机会类型" value={Object.keys(aggregatedTypes).length || 0} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-text-secondary">
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="font-medium text-text-primary">最早一轮来源结构</div>
          <div className="mt-2">{formatCountSummary(earliest?.summary?.task_source_counts)}</div>
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="font-medium text-text-primary">最新一轮来源结构</div>
          <div className="mt-2">{formatCountSummary(latest?.summary?.task_source_counts)}</div>
        </div>
      </div>

      {Object.keys(aggregatedSources).length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">窗口期累计来源分布</div>
          <div className="flex flex-wrap gap-2">
            {sortCountEntries(aggregatedSources).slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="neutral">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {Object.keys(aggregatedTypes).length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">窗口期热点机会类型</div>
          <div className="flex flex-wrap gap-2">
            {sortCountEntries(aggregatedTypes).slice(0, 6).map(([key, count]) => (
              <Badge key={key} variant="info">
                {formatTaskLabel(key)} {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FactoryQualityAuditPanel({ summary }: { summary: FactoryRunSummary }) {
  const hasAuditMetrics = [
    summary.formal_multiple_testing_count,
    summary.deflated_sharpe_ratio_avg,
    summary.high_pbo_count,
    summary.weak_white_reality_check_count,
    summary.weak_hansen_spa_count,
    summary.attempt_adjusted_gate_failed,
  ].some((value) => value != null);

  if (!hasAuditMetrics) return null;

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="text-xs font-medium text-text-primary">统计审计</div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <FactoryMetric title="正式多重检验" value={summary.formal_multiple_testing_count ?? 0} />
        <FactoryMetric title="平均 DSR" value={summary.deflated_sharpe_ratio_avg == null ? '-' : Number(summary.deflated_sharpe_ratio_avg).toFixed(2)} />
        <FactoryMetric title="高 PBO 数" value={summary.high_pbo_count ?? 0} />
        <FactoryMetric title="弱 White RC" value={summary.weak_white_reality_check_count ?? 0} />
        <FactoryMetric title="弱 Hansen SPA" value={summary.weak_hansen_spa_count ?? 0} />
        <FactoryMetric title="尝试惩罚失败" value={summary.attempt_adjusted_gate_failed ?? 0} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <FactoryMetric title="约束违例" value={summary.constraint_violation_count ?? 0} />
        <FactoryMetric title="交集均值" value={formatRatioPercent(summary.target_symbol_intersection_ratio_avg)} />
        <FactoryMetric title="扩池次数" value={summary.universe_expansion_count ?? 0} />
        <FactoryMetric title="偏好错配" value={summary.preference_mismatch_warning_count ?? 0} />
        <FactoryMetric title="事件窗污染" value={summary.event_window_contamination_warning_count ?? 0} />
        <FactoryMetric title="成本审计缺失" value={summary.cost_audit_missing_count ?? 0} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-text-secondary">
        <div>平均 proxy DSR：{summary.deflated_sharpe_proxy_avg == null ? '-' : Number(summary.deflated_sharpe_proxy_avg).toFixed(2)}</div>
        <div>高 PBO proxy：{summary.high_pbo_proxy_count ?? 0}</div>
        <div>尝试惩罚均值：{summary.attempt_adjusted_score_avg == null ? '-' : Number(summary.attempt_adjusted_score_avg).toFixed(2)}</div>
        <div>目标池交集均值：{formatRatioPercent(summary.target_symbol_intersection_ratio_avg)}</div>
      </div>
    </div>
  );
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asTypedObject<T extends Record<string, unknown>>(value: unknown): Partial<T> {
  return isObjectRecord(value) ? (value as Partial<T>) : {};
}

function toDisplayCountEntries(value: unknown) {
  if (!isObjectRecord(value)) return [] as Array<[string, number]>;
  return Object.entries(value)
    .map(([key, raw]) => [key, Number(raw)] as [string, number])
    .filter(([, count]) => Number.isFinite(count) && count > 0);
}

function toDisplayCountRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(toDisplayCountEntries(value));
}

function toObjectArray(value: unknown) {
  if (!Array.isArray(value)) return [] as Array<Record<string, unknown>>;
  return value.filter((item): item is Record<string, unknown> => isObjectRecord(item));
}

function toDisplayTextList(value: unknown, limit = 4) {
  if (!Array.isArray(value)) return [] as string[];
  return value
    .map((item) => String(item ?? '').trim())
    .filter(Boolean)
    .slice(0, limit);
}

function toDisplayText(value: unknown) {
  if (value == null) return null;
  const text = String(value).trim();
  return text || null;
}

function toDisplayNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function firstDefinedValue<T>(...values: Array<T | null | undefined>) {
  for (const value of values) {
    if (value != null) return value;
  }
  return null;
}

function formatArtifactValue(value: unknown) {
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '-';
  if (value == null || value === '') return '-';
  return String(value);
}

function formatArtifactScore(value: unknown, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : '-';
}

function shortArtifactText(value: unknown, length = 48) {
  const text = toDisplayText(value);
  if (!text) return '-';
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function formatArtifactObjectSummary(value: unknown, limit = 4) {
  if (!isObjectRecord(value)) return '-';
  const entries = Object.entries(value)
    .filter(([, raw]) => {
      if (raw == null || raw === '') return false;
      if (Array.isArray(raw)) return raw.length > 0;
      if (isObjectRecord(raw)) return Object.keys(raw).length > 0;
      return true;
    })
    .slice(0, limit)
    .map(([key, raw]) => `${key}:${Array.isArray(raw) ? raw.join(',') : String(raw)}`);
  return entries.length > 0 ? entries.join(' / ') : '-';
}

function formatConstraintAuditSummary(value: unknown) {
  if (!isObjectRecord(value)) return '-';
  const parts: string[] = [];
  const violation = toDisplayText(value.constraint_violation);
  const expansionReason = toDisplayText(value.expansion_reason);
  const alignmentViolation = toDisplayText(value.alignment_contract_violation);
  const intersectionRatio = Number(value.intersection_ratio);
  if (violation) parts.push(`violation:${violation}`);
  if (Number.isFinite(intersectionRatio)) {
    parts.push(`intersection:${formatRatioPercent(intersectionRatio)}`);
  }
  if (Boolean(value.expansion_applied)) {
    parts.push(`expansion:${expansionReason ?? 'applied'}`);
  }
  if (alignmentViolation) {
    parts.push(`alignment:${alignmentViolation}`);
  }
  return parts.length > 0 ? parts.join(' / ') : '-';
}

function formatAttemptAdjustmentSummary(value: unknown) {
  if (!isObjectRecord(value)) return '-';
  const parts: string[] = [];
  const penalty = Number(value.penalty);
  const selectionRatio = Number(value.selection_ratio);
  const attemptCount = Number(value.attempt_count);
  if (Number.isFinite(penalty) && penalty > 0) {
    parts.push(`penalty:${penalty.toFixed(4)}`);
  }
  if (Number.isFinite(selectionRatio)) {
    parts.push(`selection:${formatRatioPercent(selectionRatio)}`);
  }
  if (Number.isFinite(attemptCount) && attemptCount > 0) {
    parts.push(`attempts:${attemptCount}`);
  }
  return parts.length > 0 ? parts.join(' / ') : '-';
}

function previewBadgeVariant(status: unknown): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(status ?? '').trim().toLowerCase();
  if (!normalized) return 'neutral';
  if (['success', 'succeeded', 'completed', 'recorded', 'ready', 'proceed', 'healthy'].includes(normalized)) {
    return 'success';
  }
  if (['failed', 'error', 'blocked', 'rejected', 'halted'].includes(normalized)) {
    return 'danger';
  }
  if (['partial', 'running', 'pending', 'degraded', 'warning'].includes(normalized)) {
    return 'warning';
  }
  return 'info';
}

function toLedgerEntries(value: unknown): FactoryPredictionTraceLedgerEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is FactoryPredictionTraceLedgerEntry => isObjectRecord(item));
}

function asLedgerNode(value: unknown): Partial<FactoryPredictionTraceLedgerNode> {
  return asTypedObject<FactoryPredictionTraceLedgerNode>(value);
}

function asTraceGateDecisions(value: unknown): Partial<StrategyPredictionTraceGateDecisions> {
  return asTypedObject<StrategyPredictionTraceGateDecisions>(value);
}

function traceNodeHasFallback(node: Partial<FactoryPredictionTraceLedgerNode> | undefined) {
  return String(node?.source_mode ?? '').trim().toLowerCase() === 'summary_fallback';
}

function traceNodeSummary(node: Partial<FactoryPredictionTraceLedgerNode> | undefined) {
  const available = Boolean(node?.available);
  const count = toDisplayNumber(node?.count);
  const status = toDisplayText(node?.status);
  return [
    available ? 'Y' : 'N',
    count != null ? String(count) : '-',
    status ?? '-',
  ].join(' / ');
}

function traceNodeDetails(node: Partial<FactoryPredictionTraceLedgerNode> | undefined, preferredKeys: string[]) {
  const payload = node ?? {};
  return preferredKeys
    .map((key) => [key, payload[key as keyof FactoryPredictionTraceLedgerNode]] as const)
    .filter(([, value]) => {
      if (value == null || value === '') return false;
      if (Array.isArray(value)) return value.length > 0;
      if (isObjectRecord(value)) return Object.keys(value).length > 0;
      return true;
    });
}

function providerControlBadgeVariant(
  mode: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(mode ?? '').trim().toLowerCase();
  if (!normalized) return 'neutral';
  if (normalized === 'suppress') return 'danger';
  if (normalized === 'cooldown') return 'warning';
  if (normalized === 'limited') return 'info';
  if (normalized === 'normal') return 'success';
  return previewBadgeVariant(normalized);
}

function validationGradeBadgeVariant(
  grade: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(grade ?? '').trim().toUpperCase();
  if (!normalized) return 'neutral';
  if (normalized === 'A' || normalized === 'B') return 'success';
  if (normalized === 'C') return 'warning';
  if (normalized === 'D') return 'danger';
  return 'info';
}

function formatCountWithRate(count: unknown, rate: unknown) {
  const normalizedCount = toDisplayNumber(count);
  const formattedRate = formatRatioPercent(toDisplayNumber(rate));
  if (normalizedCount == null) return formattedRate;
  return `${normalizedCount} / ${formattedRate}`;
}

function gradeDistributionEntries(value: unknown) {
  if (!isObjectRecord(value)) return [] as Array<[string, number]>;
  const preferredOrder = ['A', 'B', 'C', 'D'];
  const entries = Object.entries(value)
    .map(([grade, rawCount]) => [String(grade).trim().toUpperCase(), Number(rawCount)] as [string, number])
    .filter(([grade, count]) => grade && Number.isFinite(count) && count > 0);

  entries.sort(([leftGrade], [rightGrade]) => {
    const leftIndex = preferredOrder.indexOf(leftGrade);
    const rightIndex = preferredOrder.indexOf(rightGrade);
    const normalizedLeftIndex = leftIndex === -1 ? preferredOrder.length : leftIndex;
    const normalizedRightIndex = rightIndex === -1 ? preferredOrder.length : rightIndex;
    return normalizedLeftIndex - normalizedRightIndex || leftGrade.localeCompare(rightGrade);
  });
  return entries;
}

function formatGradeDistributionSummary(value: unknown) {
  const entries = gradeDistributionEntries(value);
  if (entries.length === 0) return '-';
  return entries.map(([grade, count]) => `${grade}:${count}`).join(' / ');
}

function distributionsDiffer(left: unknown, right: unknown) {
  return formatGradeDistributionSummary(left) !== formatGradeDistributionSummary(right);
}

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

function generationTierBadgeVariant(
  tier: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(tier ?? '').trim().toUpperCase();
  if (normalized === 'L3') return 'warning';
  if (normalized === 'L2') return 'info';
  if (normalized === 'L1') return 'success';
  return 'neutral';
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
  const qualityBaseline = asTypedObject<Record<string, unknown>>(
    factoryStatus?.quality_baseline,
  ) as Partial<FactoryQualityBaseline>;
  const cohort = asTypedObject<Record<string, unknown>>(
    qualityBaseline.submitted_strategy_cohort,
  ) as NonNullable<FactoryQualityBaseline['submitted_strategy_cohort']>;
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

function FactoryHighConfidenceQualityPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const qualityUiV2Enabled = Boolean(
    factoryStatus?.quality_ui_v2_enabled ?? factoryStatus?.feature_flags?.quality_ui_v2_enabled,
  );
  const qualityBaseline = asTypedObject<Record<string, unknown>>(
    factoryStatus?.quality_baseline,
  ) as Partial<FactoryQualityBaseline>;
  const latestRun = asTypedObject<Record<string, unknown>>(
    qualityBaseline.latest_run,
  ) as Partial<FactoryQualitySummarySnapshot>;
  const cohort = asTypedObject<Record<string, unknown>>(
    qualityBaseline.submitted_strategy_cohort,
  ) as NonNullable<FactoryQualityBaseline['submitted_strategy_cohort']>;

  if (!qualityUiV2Enabled) return null;

  const hasHighConfidenceData = [
    latestRun.prediction_quality_distribution,
    latestRun.execution_quality_distribution,
    latestRun.evidence_alignment_distribution,
    latestRun.confidence_contract_ready_rate,
    cohort.prediction_quality_distribution,
    cohort.execution_quality_distribution,
    cohort.evidence_alignment_distribution,
    cohort.confidence_contract_ready_rate,
  ].some((value) => {
    if (isObjectRecord(value)) return Object.keys(value).length > 0;
    return value != null;
  });

  if (!hasHighConfidenceData) return null;

  const sections = [
    {
      key: 'latest',
      title: '最近一轮',
      summary: latestRun,
    },
    {
      key: 'cohort',
      title: '已提交 Cohort',
      summary: cohort,
    },
  ].filter((item) => {
    const summary = item.summary;
    return [
      summary.prediction_quality_distribution,
      summary.execution_quality_distribution,
      summary.evidence_alignment_distribution,
      summary.confidence_contract_ready_rate,
    ].some((value) => {
      if (isObjectRecord(value)) return Object.keys(value).length > 0;
      return value != null;
    });
  });

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt p-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">高置信质量面板</div>
        <Badge variant="info">UI V2</Badge>
      </div>
      <div className="text-xs text-text-secondary">
        预测质量、执行质量、证据对齐和合同就绪率按 cohort / 最近一轮并排展示，旧 KPI 卡片保持不变。
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {sections.map(({ key, title, summary }) => (
          <div
            key={key}
            className="rounded border border-border bg-surface px-3 py-3 space-y-3 text-xs text-text-secondary"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="font-medium text-text-primary">{title}</div>
              <Badge variant="neutral">
                合同就绪率 {formatRatioPercent(toDisplayNumber(summary.confidence_contract_ready_rate))}
              </Badge>
            </div>
            <div className="grid grid-cols-1 gap-2">
              <div>预测质量：{formatCountSummary(summary.prediction_quality_distribution ?? {}) || '-'}</div>
              <div>执行质量：{formatCountSummary(summary.execution_quality_distribution ?? {}) || '-'}</div>
              <div>证据对齐：{formatCountSummary(summary.evidence_alignment_distribution ?? {}) || '-'}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FactorySignalQualityRegistryPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const registry = asTypedObject<Record<string, unknown>>(factoryStatus?.signal_quality_registry);
  const snapshot = asTypedObject<Record<string, unknown>>(
    firstDefinedValue(registry.snapshot, registry),
  );
  const buyProbability = asTypedObject<Record<string, unknown>>(
    firstDefinedValue(snapshot.buy_probability, registry.buy_probability),
  );
  const sentiment = asTypedObject<Record<string, unknown>>(
    firstDefinedValue(snapshot.sentiment, registry.sentiment),
  );
  const factor = asTypedObject<Record<string, unknown>>(
    firstDefinedValue(snapshot.factor, registry.factor),
  );
  const drift = asTypedObject<Record<string, unknown>>(registry.drift);
  const driftChecks = asTypedObject<Record<string, unknown>>(drift.checks);
  const driftEntries = Object.entries(driftChecks)
    .map(([key, value]) => ({
      key,
      payload: asTypedObject<Record<string, unknown>>(value),
    }))
    .filter(({ payload }) => Object.keys(payload).length > 0);
  const recentProbability = toObjectArray(registry.recent_probability);
  const recentSentiment = toObjectArray(registry.recent_sentiment);
  const recentFactor = toObjectArray(registry.recent_factor);

  const hasRegistryData = [
    buyProbability.entry_count,
    sentiment.entry_count,
    factor.entry_count,
    drift.overall_status,
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
        <Badge variant={String(drift.overall_status ?? '').toLowerCase() === 'degraded' ? 'warning' : 'info'}>
          drift {toDisplayText(drift.overall_status) ?? 'partial'}
        </Badge>
      </div>
      <div className="text-xs text-text-secondary">
        probability / sentiment / factor 的 recent quality 和 drift summary 放在同一块，作为工厂 dashboard 的观测闭环。
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="概率条目" value={toDisplayNumber(buyProbability.entry_count) ?? 0} />
        <FactoryMetric title="情绪条目" value={toDisplayNumber(sentiment.entry_count) ?? 0} />
        <FactoryMetric title="因子条目" value={toDisplayNumber(factor.entry_count) ?? 0} />
        <FactoryMetric title="总条目" value={toDisplayNumber(snapshot.total_entries ?? registry.total_entries) ?? 0} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 text-xs text-text-secondary">
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">买入概率</div>
          <div>质量分布：{formatCountSummary(toDisplayCountRecord(buyProbability.quality_distribution)) || '-'}</div>
          <div>Brier：{formatFactoryMetricValue(toDisplayNumber(asTypedObject<Record<string, unknown>>(buyProbability.brier_score).mean), 4)}</div>
          <div>ECE：{formatFactoryMetricValue(toDisplayNumber(asTypedObject<Record<string, unknown>>(buyProbability.ece).mean), 4)}</div>
          {recentProbability.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent: {recentProbability.slice(0, 2).map((item) => `${toDisplayText(item.code) ?? '-'} ${toDisplayText(item.quality) ?? 'unknown'}`).join(' / ')}
            </div>
          ) : null}
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">情绪质量</div>
          <div>情绪分布：{formatCountSummary(toDisplayCountRecord(sentiment.sentiment_distribution)) || '-'}</div>
          <div>稳定性：{formatCountSummary(toDisplayCountRecord(sentiment.stability_distribution)) || '-'}</div>
          <div>news alpha：{formatFactoryMetricValue(toDisplayNumber(asTypedObject<Record<string, unknown>>(sentiment.news_alpha_5d).mean), 4)}</div>
          {recentSentiment.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent: {recentSentiment.slice(0, 2).map((item) => `${toDisplayText(item.code) ?? '-'} ${toDisplayText(item.sentiment) ?? 'neutral'}`).join(' / ')}
            </div>
          ) : null}
        </div>
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="font-medium text-text-primary">因子质量</div>
          <div>评级分布：{formatCountSummary(toDisplayCountRecord(factor.rating_distribution)) || '-'}</div>
          <div>前视风险：{formatCountSummary(toDisplayCountRecord(factor.lookahead_risk_distribution)) || '-'}</div>
          <div>OOS RankIC：{formatFactoryMetricValue(toDisplayNumber(asTypedObject<Record<string, unknown>>(factor.oos_rank_ic_mean).mean), 4)}</div>
          {recentFactor.length ? (
            <div className="rounded border border-border bg-surface-alt px-2 py-2">
              recent: {recentFactor.slice(0, 2).map((item) => `${toDisplayText(item.factor_name) ?? '-'} ${toDisplayText(item.rating) ?? 'unknown'}`).join(' / ')}
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

function FactoryProviderDiagnosticsPanel({
  factoryStatus,
}: {
  factoryStatus: FactoryStatusResponse | null | undefined;
}) {
  const diagnostics = asTypedObject<Record<string, unknown>>(
    firstDefinedValue(
      factoryStatus?.recent_run_diagnostics,
      isObjectRecord(factoryStatus?.quality_baseline)
        ? factoryStatus?.quality_baseline?.recent_run_diagnostics
        : undefined,
    ),
  );
  const readinessDecisionCounts = toDisplayCountEntries(diagnostics.readiness_decision_counts);
  const blockerReasonTop = toObjectArray(diagnostics.blocker_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const warningReasonTop = toObjectArray(diagnostics.warning_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedDiagnostics = asTypedObject<Record<string, unknown>>(diagnostics.governed_pool_diagnostics);
  const governedWarningTop = toObjectArray(governedDiagnostics.warning_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedBlockingTop = toObjectArray(governedDiagnostics.blocking_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedExclusionTop = toObjectArray(governedDiagnostics.exclusion_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const governedIneligibleTop = toObjectArray(governedDiagnostics.ineligible_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const evidenceDebtDiagnostics = asTypedObject<Record<string, unknown>>(diagnostics.evidence_debt_diagnostics);
  const evidenceDebtWarningTop = toObjectArray(evidenceDebtDiagnostics.warning_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const providerWindowDiagnostics = asTypedObject<Record<string, unknown>>(diagnostics.provider_control_diagnostics);
  const controlModeCounts = toDisplayCountEntries(diagnostics.external_llm_provider_control_mode_counts);
  const controlReasonTop = toObjectArray(diagnostics.external_llm_provider_control_reason_topn)
    .map((item) => ({
      reason: toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
  const suppressedModeTop = toObjectArray(diagnostics.suppressed_generator_mode_topn)
    .map((item) => ({
      mode: toDisplayText(item.mode) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.mode && Number.isFinite(item.count) && item.count > 0);
  const recentRuns = toObjectArray(diagnostics.recent_runs);
  const analyzedRunCount = toDisplayNumber(diagnostics.analyzed_run_count);
  const blockedRunCount = toDisplayNumber(diagnostics.readiness_blocked_count);
  const submitStageEnteredCount = toDisplayNumber(diagnostics.submit_stage_entered_count);
  const submittedPositiveCount = toDisplayNumber(diagnostics.submitted_positive_count);
  const suppressedRunCount = toDisplayNumber(diagnostics.external_llm_provider_suppressed_run_count);
  const cooldownRunCount = toDisplayNumber(diagnostics.external_llm_provider_cooldown_run_count);
  const governedBlockedRatioLatest = formatRatioPercent(
    toDisplayNumber(governedDiagnostics.latest_governed_blocked_ratio),
  );
  const governedBlockedRatioMean = formatRatioPercent(
    toDisplayNumber(governedDiagnostics.recent_governed_blocked_ratio_mean),
  );
  const governedStrictShortfallLatest = toDisplayNumber(
    governedDiagnostics.latest_governed_candidate_pool_strict_shortfall_count,
  );
  const governedStrictShortfallMean = toDisplayNumber(
    governedDiagnostics.recent_governed_candidate_pool_strict_shortfall_mean,
  );
  const governedBlockedCandidateLatest = toDisplayNumber(
    governedDiagnostics.latest_governed_blocked_candidate_count,
  );
  const governedBlockedCandidateMean = toDisplayNumber(
    governedDiagnostics.recent_governed_blocked_candidate_count_mean,
  );
  const evidenceDebtRatioLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.latest_budget_feedback_evidence_debt_ratio),
  );
  const evidenceDebtRatioMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.recent_budget_feedback_evidence_debt_ratio_mean),
  );
  const zeroSignalRatioLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.latest_budget_feedback_zero_signal_ratio),
  );
  const zeroSignalRatioMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.recent_budget_feedback_zero_signal_ratio_mean),
  );
  const forwardCoverageLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.latest_budget_feedback_forward_window_coverage_ratio),
  );
  const forwardCoverageMean = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.recent_budget_feedback_forward_window_coverage_ratio_mean),
  );
  const promotionReadyLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.latest_budget_feedback_promotion_ready_ratio),
  );
  const promotionReviewLatest = formatRatioPercent(
    toDisplayNumber(evidenceDebtDiagnostics.latest_budget_feedback_promotion_review_coverage_ratio),
  );
  const providerAttemptActiveRuns = toDisplayNumber(providerWindowDiagnostics.active_attempt_run_count);
  const providerAttemptZeroRuns = toDisplayNumber(providerWindowDiagnostics.zero_attempt_run_count);
  const providerStageAttemptLatest = toDisplayNumber(providerWindowDiagnostics.latest_stage_attempt_count);
  const providerStageAttemptMean = toDisplayNumber(providerWindowDiagnostics.recent_stage_attempt_count_mean);
  const providerRealRequestLatest = toDisplayNumber(providerWindowDiagnostics.latest_real_request_count);
  const providerRealRequestMean = toDisplayNumber(providerWindowDiagnostics.recent_real_request_count_mean);
  const providerSkipRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.latest_compatibility_skip_ratio),
  );
  const providerSkipRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.recent_compatibility_skip_ratio_mean),
  );
  const providerFailureRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.latest_compatibility_failure_ratio),
  );
  const providerFailureRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.recent_compatibility_failure_ratio_mean),
  );
  const providerEffectiveRatioLatest = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.latest_effective_response_ratio),
  );
  const providerEffectiveRatioMean = formatRatioPercent(
    toDisplayNumber(providerWindowDiagnostics.recent_effective_response_ratio_mean),
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
    evidenceDebtDiagnostics.latest_budget_feedback_evidence_debt_ratio,
    evidenceDebtDiagnostics.latest_budget_feedback_zero_signal_ratio,
    evidenceDebtDiagnostics.latest_budget_feedback_forward_window_coverage_ratio,
  ].some(Boolean);
  const hasProviderWindow = [
    providerAttemptActiveRuns,
    providerAttemptZeroRuns,
    providerStageAttemptLatest,
    providerRealRequestLatest,
    providerWindowDiagnostics.latest_compatibility_skip_ratio,
    providerWindowDiagnostics.latest_effective_response_ratio,
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
        {analyzedRunCount != null ? (
          <Badge variant="neutral">近 {analyzedRunCount} 轮</Badge>
        ) : null}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <FactoryMetric title="Readiness 阻断" value={formatCountWithRate(blockedRunCount, diagnostics.readiness_blocked_rate)} />
        <FactoryMetric title="进入 Submit" value={formatCountWithRate(submitStageEnteredCount, diagnostics.submit_stage_entered_rate)} />
        <FactoryMetric title="实际提交" value={formatCountWithRate(submittedPositiveCount, diagnostics.submitted_positive_rate)} />
        <FactoryMetric title="Provider 抑制" value={formatCountWithRate(suppressedRunCount, diagnostics.external_llm_provider_suppressed_run_rate)} />
        <FactoryMetric title="Provider 冷却" value={formatCountWithRate(cooldownRunCount, diagnostics.external_llm_provider_cooldown_run_rate)} />
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
                <FactoryMetric title="Blocked 比率" value={`${governedBlockedRatioLatest} / ${governedBlockedRatioMean}`} />
                <FactoryMetric title="Strict shortfall" value={`${governedStrictShortfallLatest ?? '-'} / ${governedStrictShortfallMean == null ? '-' : formatFactoryMetricValue(governedStrictShortfallMean, 1)}`} />
                <FactoryMetric title="Blocked 候选" value={`${governedBlockedCandidateLatest ?? '-'} / ${governedBlockedCandidateMean == null ? '-' : formatFactoryMetricValue(governedBlockedCandidateMean, 1)}`} />
                <FactoryMetric title="Source 候选" value={toDisplayNumber(governedDiagnostics.latest_governed_source_candidate_count) ?? '-'} />
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
                <FactoryMetric title="Stage attempts" value={`${providerStageAttemptLatest ?? '-'} / ${providerStageAttemptMean == null ? '-' : formatFactoryMetricValue(providerStageAttemptMean, 1)}`} />
                <FactoryMetric title="真实请求" value={`${providerRealRequestLatest ?? '-'} / ${providerRealRequestMean == null ? '-' : formatFactoryMetricValue(providerRealRequestMean, 1)}`} />
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

      {(blockerReasonTop.length > 0 || warningReasonTop.length > 0 || controlReasonTop.length > 0 || suppressedModeTop.length > 0) && (
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
              const evidenceDebtRatio = formatRatioPercent(toDisplayNumber(item.budget_feedback_evidence_debt_ratio));
              const providerAttemptCount = toDisplayNumber(item.external_llm_stage_attempt_count) ?? 0;
              const providerRealRequestCount = toDisplayNumber(item.external_llm_real_request_count) ?? 0;
              const providerSkipRatio = formatRatioPercent(toDisplayNumber(item.external_llm_compatibility_skip_ratio));
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
                  <div>Provider Skip / Failure / Effective：{providerSkipRatio} / {providerFailureRatio} / {providerEffectiveRatio}</div>
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

function FactoryPreviewSection({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        {typeof count === 'number' && (
          <Badge variant="neutral">{count} 条</Badge>
        )}
      </div>
      {children}
    </div>
  );
}

function toReasonTopEntries(value: unknown) {
  return toObjectArray(value)
    .map((item) => ({
      reason: toDisplayText(item.reason) ?? toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
}

function toBooleanSupportEntries(value: unknown) {
  if (!isObjectRecord(value)) return [] as Array<{ key: string; enabled: boolean }>;
  return Object.entries(value)
    .filter(([, raw]) => typeof raw === 'boolean')
    .map(([key, raw]) => ({ key, enabled: Boolean(raw) }));
}

function FactoryArtifactCard({
  title,
  artifact,
  fields,
}: {
  title: string;
  artifact: Record<string, unknown>;
  fields: Array<{ key: string; label: string }>;
}) {
  if (!isObjectRecord(artifact) || !artifact.available) return null;
  return (
    <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        <Badge variant="success">已观测</Badge>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-text-secondary">
        <div>契约版本：{formatArtifactValue(artifact.contract_version)}</div>
        {fields.map((field) => (
          <div key={field.key}>
            {field.label}：{formatArtifactValue(artifact[field.key])}
          </div>
        ))}
      </div>
    </div>
  );
}

function FactoryFeedbackLoopPanel({
  title,
  summary,
  feedbackSummary,
  compact = false,
}: {
  title: string;
  summary?: Partial<FactoryRunSummary> | null;
  feedbackSummary?: Record<string, unknown> | null;
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
  const generatorModeControls = isObjectRecord(summary?.generator_mode_controls)
    ? Object.entries(summary.generator_mode_controls).filter(([, payload]) => isObjectRecord(payload))
    : [];
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
          {feedbackContractVersion && (
            <Badge variant="neutral">契约 {feedbackContractVersion}</Badge>
          )}
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
          {externalLlmProviderSuppressed ? (
            <Badge variant="warning">Provider 抑制中</Badge>
          ) : null}
          {externalLlmProviderCooldown ? (
            <Badge variant="warning">Provider 冷却中</Badge>
          ) : null}
        </div>
      </div>

      <div className={`grid grid-cols-2 ${compact ? 'md:grid-cols-3 xl:grid-cols-6' : 'md:grid-cols-4 xl:grid-cols-8'} gap-3`}>
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
        <div className={`grid grid-cols-1 ${compact ? 'xl:grid-cols-3' : 'xl:grid-cols-3'} gap-3`}>
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

      {!compact && (suppressedFamilies.length > 0 || suppressedTargetPools.length > 0 || suppressedGeneratorModes.length > 0) && (
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

      {!compact && (externalLlmProviderControlReasons.length > 0 || externalLlmProviderSuppressed || externalLlmProviderCooldown) && (
        <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
          <div className="text-xs font-medium text-text-primary">外部 LLM Provider</div>
          <div className="flex flex-wrap gap-2">
            {externalLlmProviderControlMode ? (
              <Badge variant={providerControlBadgeVariant(externalLlmProviderControlMode)}>
                模式 {formatTaskLabel(externalLlmProviderControlMode)}
              </Badge>
            ) : null}
            {externalLlmProviderSuppressed ? (
              <Badge variant="warning">已触发抑制</Badge>
            ) : null}
            {externalLlmProviderCooldown ? (
              <Badge variant="warning">已触发冷却</Badge>
            ) : null}
          </div>
          {externalLlmProviderControlReasons.length > 0 && (
            <div className="text-xs text-text-secondary">
              原因码：{externalLlmProviderControlReasons.map((item) => formatTaskLabel(item)).join(' / ')}
            </div>
          )}
        </div>
      )}

      {!compact && generatorModeControls.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">生成模式控制明细</div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {generatorModeControls.slice(0, 6).map(([mode, payload]) => {
              const record = payload as Record<string, unknown>;
              const controlMode = toDisplayText(record.control_mode);
              const source = toDisplayText(record.source);
              const families = toDisplayTextList(record.families, 4);
              const controlReasons = toDisplayTextList(record.control_reasons, 4);

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
                      {source && (
                        <Badge variant="neutral">{formatTaskLabel(source)}</Badge>
                      )}
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

function FactoryResearchPlanePanel({ detail }: { detail: FactoryRunDetailResponse }) {
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
                  <Badge variant={previewBadgeVariant(readinessDecision)}>
                    {readinessDecision}
                  </Badge>
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
                      {family && (
                        <Badge variant="info">{formatTaskLabel(family)}</Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {registryStage && (
                        <Badge variant="neutral">阶段 {formatTaskLabel(registryStage)}</Badge>
                      )}
                      {latestValidationAt && (
                        <Badge variant="neutral">
                          验证 {shortFactoryRunTime(latestValidationAt)}
                        </Badge>
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
                            {taskSource && (
                              <Badge variant="neutral">{formatTaskLabel(taskSource)}</Badge>
                            )}
                            {opportunityType && (
                              <Badge variant="info">{formatTaskLabel(opportunityType)}</Badge>
                            )}
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
                    {candidateFamily && (
                      <Badge variant="info">{formatTaskLabel(candidateFamily)}</Badge>
                    )}
                    {taskSource && (
                      <Badge variant="neutral">{formatTaskLabel(taskSource)}</Badge>
                    )}
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

function FactoryPredictionTraceLedgerPanel({
  ledger,
  predictionTraceId,
}: {
  ledger: Partial<FactoryPredictionTraceLedgerSummary>;
  predictionTraceId?: string | null;
}) {
  const entries = toLedgerEntries(ledger.entries);
  if (entries.length === 0) return null;

  const renderNodeCell = (
    nodeLike: unknown,
    detailKeys: string[],
  ) => {
    const node = asLedgerNode(nodeLike);
    const fallback = traceNodeHasFallback(node);
    const detailRows = traceNodeDetails(node, detailKeys);
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{traceNodeSummary(node)}</span>
          {fallback ? <Badge variant="warning">降级</Badge> : null}
        </div>
        {detailRows.length > 0 && (
          <details className="text-[11px] text-text-secondary">
            <summary className="cursor-pointer select-none">详情</summary>
            <div className="mt-1 space-y-1">
              {detailRows.map(([key, raw]) => (
                <div key={String(key)}>
                  {String(key)}: {Array.isArray(raw) ? raw.join(' / ') : isObjectRecord(raw) ? formatArtifactObjectSummary(raw) : String(raw)}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs font-medium text-text-primary">Prediction Trace Ledger</div>
        <div className="text-xs text-text-secondary">
          Trace 数：{entries.length}
          {predictionTraceId ? ` · 当前 ${predictionTraceId}` : ''}
        </div>
      </div>
      <div className="overflow-x-auto rounded border border-border bg-surface">
        <table className="min-w-full text-xs text-left text-text-secondary">
          <thead className="bg-surface-alt text-text-primary">
            <tr>
              <th className="px-3 py-2 font-medium">trace_id</th>
              <th className="px-3 py-2 font-medium">signal</th>
              <th className="px-3 py-2 font-medium">order</th>
              <th className="px-3 py-2 font-medium">fill</th>
              <th className="px-3 py-2 font-medium">round_trip</th>
              <th className="px-3 py-2 font-medium">pnl</th>
              <th className="px-3 py-2 font-medium">gate</th>
              <th className="px-3 py-2 font-medium">gaps</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, idx) => {
              const signalNode = asLedgerNode(entry.signal_event);
              const orderNode = asLedgerNode(entry.intended_order);
              const fillNode = asLedgerNode(entry.actual_fill);
              const roundTripNode = asLedgerNode(entry.position_round_trip);
              const pnlNode = asLedgerNode(entry.pnl_audit_summary);
              const gateDecisions = asTraceGateDecisions(entry.gate_decisions);
              const hasFallback = [signalNode, orderNode, fillNode, roundTripNode, pnlNode].some(traceNodeHasFallback);
              const familyOutcomeSummary = asTypedObject<Record<string, unknown>>(entry.family_outcome_summary);
              const gapCodes = toDisplayTextList(entry.evidence_gap_codes, 8);
              return (
                <tr key={String(entry.prediction_trace_id ?? idx)} className="border-t border-border align-top">
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="font-medium text-text-primary break-all">
                        {String(entry.prediction_trace_id ?? '-')}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {hasFallback ? <Badge variant="warning">summary_fallback</Badge> : <Badge variant="success">entity_backed</Badge>}
                        {predictionTraceId && entry.prediction_trace_id === predictionTraceId ? <Badge variant="info">当前</Badge> : null}
                      </div>
                      <details className="text-[11px] text-text-secondary">
                        <summary className="cursor-pointer select-none">展开</summary>
                        <div className="mt-1 space-y-1">
                          <div>artifact_ids: {toDisplayTextList(entry.artifact_ids, 8).join(' / ') || '-'}</div>
                          <div>retrieval_context_ids: {toDisplayTextList(entry.retrieval_context_ids, 8).join(' / ') || '-'}</div>
                          <div>family_outcome: {formatArtifactObjectSummary(familyOutcomeSummary, 6)}</div>
                        </div>
                      </details>
                    </div>
                  </td>
                  <td className="px-3 py-2">{renderNodeCell(signalNode, ['latest_signal_snapshot_id', 'recent_signal_ids', 'signal_evidence_count', 'runtime_action_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(orderNode, ['paper_account_id', 'order_ids', 'order_status_counts'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(fillNode, ['trade_ids', 'linked_signal_count', 'linked_position_count', 'realized_trade_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(roundTripNode, ['position_ids', 'mapped_position_count', 'closed_position_count', 'round_trip_close_rate', 'incomplete_position_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(pnlNode, ['nav_row_count', 'realized_pnl_total', 'trade_expectancy', 'pnl_conversion_efficiency', 'execution_conversion_efficiency'])}</td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap gap-1">
                        {toDisplayText(gateDecisions.execution_audit_gate_status) ? (
                          <Badge variant={previewBadgeVariant(gateDecisions.execution_audit_gate_status)}>
                            {formatTaskLabel(gateDecisions.execution_audit_gate_status)}
                          </Badge>
                        ) : null}
                        <Badge variant={gateDecisions.hard_gate_passed ? 'success' : 'neutral'}>
                          hard_gate {gateDecisions.hard_gate_passed ? 'pass' : 'hold'}
                        </Badge>
                        <Badge variant={gateDecisions.promotion_ready ? 'success' : 'warning'}>
                          promotion {gateDecisions.promotion_ready ? 'ready' : 'hold'}
                        </Badge>
                      </div>
                      {toDisplayTextList(gateDecisions.failure_reasons, 6).length > 0 ? (
                        <details className="text-[11px] text-text-secondary">
                          <summary className="cursor-pointer select-none">failure_reasons</summary>
                          <div className="mt-1 break-all">{toDisplayTextList(gateDecisions.failure_reasons, 6).join(' / ')}</div>
                        </details>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap gap-1">
                        {gapCodes.length > 0 ? gapCodes.map((code) => (
                          <Badge key={code} variant="warning">{code}</Badge>
                        )) : <span>-</span>}
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FactoryGovernancePlanePanel({ detail }: { detail: FactoryRunDetailResponse }) {
  const governancePlane = asTypedObject<FactoryGovernancePlaneArtifact>(detail.governance_plane);
  const gateArtifact = asTypedObject<FactoryGovernanceGateArtifact>(detail.gate_artifact);
  const gateArtifactV2 = asTypedObject<FactoryGovernanceGateArtifact>(detail.gate_artifact_v2);
  const dedupArtifact = asTypedObject<FactoryGovernanceDedupArtifact>(detail.dedup_artifact);
  const submissionArtifact = asTypedObject<FactoryGovernanceSubmissionArtifact>(detail.submission_artifact);
  const governanceEvidenceArtifact = asTypedObject<FactoryGovernanceEvidenceArtifact>(detail.governance_evidence_artifact);
  const gateA = asTypedObject<FactoryGateStageResult>(detail.gate_a ?? gateArtifactV2.gate_a ?? governancePlane.gate_a);
  const gateB = asTypedObject<FactoryGateStageResult>(detail.gate_b ?? gateArtifactV2.gate_b ?? governancePlane.gate_b);
  const gateC = asTypedObject<FactoryGateStageResult>(detail.gate_c ?? gateArtifactV2.gate_c ?? governancePlane.gate_c);
  const protocolVersions = asTypedObject<FactoryProtocolVersionsSummary>(
    detail.protocol_versions ?? gateArtifactV2.protocol_versions ?? governancePlane.protocol_versions,
  );
  const predictionTraceSummary = asTypedObject<FactoryPredictionTraceSummary>(
    detail.prediction_trace_summary ?? gateArtifactV2.prediction_trace_summary ?? governancePlane.prediction_trace_summary,
  );
  const predictionTraceLedger = asTypedObject<FactoryPredictionTraceLedgerSummary>(
    detail.prediction_trace_ledger ?? gateArtifactV2.prediction_trace_ledger ?? governancePlane.prediction_trace_ledger,
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
    ? dedupArtifact.kept_briefs as FactoryGovernanceDedupBrief[]
    : [];
  const droppedBriefs = Array.isArray(dedupArtifact.dropped_briefs)
    ? dedupArtifact.dropped_briefs as FactoryGovernanceDedupBrief[]
    : [];
  const strategyBriefs = Array.isArray(submissionArtifact.strategy_briefs)
    ? submissionArtifact.strategy_briefs as FactoryGovernanceStrategyBrief[]
    : [];
  const strategyEvidenceBriefs = Array.isArray(governanceEvidenceArtifact.strategy_evidence_briefs)
    ? governanceEvidenceArtifact.strategy_evidence_briefs as FactoryGovernanceEvidenceStrategyBrief[]
    : [];
  const incubationBudgetSummary = asTypedObject<Record<string, unknown>>(submissionArtifact.incubation_budget_summary);
  const incubationFamilyCounts = toDisplayCountEntries(incubationBudgetSummary.family_counts);
  const backtestThresholdsByType = asTypedObject<Record<string, Record<string, unknown>>>(gateArtifact.backtest_thresholds_by_type);
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

      {(gateStageRows.length > 0 || Object.keys(protocolVersions).length > 0 || predictionTraceLedgerEntries.length > 0 || sampleTraceIds.length > 0 || detail.prediction_trace_id) && (
        <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
          <div className="text-xs font-medium text-text-primary">V2 门禁与追踪</div>
          {gateStageRows.length > 0 && (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
              {gateStageRows.map(({ label, gate }) => {
                const blockingReasons = Array.isArray(gate.blocking_reasons)
                  ? gate.blocking_reasons
                    .map((item) => (typeof item === 'string' ? item : String(item.reason ?? item.reason_code ?? item.count ?? '')))
                    .filter(Boolean)
                  : [];
                const revisionActions = Array.isArray(gate.revision_actions)
                  ? gate.revision_actions.map((item) => String(item)).filter(Boolean)
                  : [];
                return (
                  <div key={label} className="rounded border border-border bg-surface px-3 py-3 text-xs text-text-secondary space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium text-text-primary">{label}</div>
                      <Badge variant={previewBadgeVariant(gate.status)}>{formatTaskLabel(gate.status ?? 'pending')}</Badge>
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
                Trace 覆盖：{formatArtifactValue(predictionTraceSummary.trace_count)} / 缺失 {formatArtifactValue(predictionTraceSummary.missing_count)}
              </div>
              {predictionTraceLedgerEntries.length > 0 ? (
                <FactoryPredictionTraceLedgerPanel
                  ledger={predictionTraceLedger}
                  predictionTraceId={detail.prediction_trace_id ?? null}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {detail.prediction_trace_id ? <Badge variant="info">{String(detail.prediction_trace_id)}</Badge> : null}
                  {sampleTraceIds.filter((item) => item !== detail.prediction_trace_id).slice(0, 4).map((item) => (
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
            <FactoryMetric title="约束审计" value={Number(submissionArtifact.constraint_check_count ?? governanceEvidenceArtifact.constraint_check_count ?? 0)} />
            <FactoryMetric title="验证画像" value={Number(submissionArtifact.validation_profile_count ?? governanceEvidenceArtifact.validation_profile_count ?? 0)} />
            <FactoryMetric title="事件窗配置" value={Number(submissionArtifact.event_window_config_count ?? governanceEvidenceArtifact.event_window_config_count ?? 0)} />
            <FactoryMetric title="仓位假设" value={Number(submissionArtifact.position_assumption_count ?? governanceEvidenceArtifact.position_assumption_count ?? 0)} />
            <FactoryMetric title="成本假设" value={Number(submissionArtifact.cost_assumptions_count ?? governanceEvidenceArtifact.cost_assumptions_count ?? 0)} />
            <FactoryMetric title="尝试惩罚" value={Number(submissionArtifact.attempt_adjustment_count ?? governanceEvidenceArtifact.attempt_adjustment_count ?? 0)} />
            <FactoryMetric title="评审结果" value={Number(submissionArtifact.committee_review_count ?? governanceEvidenceArtifact.committee_review_count ?? 0)} />
            <FactoryMetric title="任务签名" value={Number(submissionArtifact.task_signature_count ?? governanceEvidenceArtifact.task_signature_count ?? 0)} />
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
        <FactoryPreviewSection title="治理原因预览" count={gateFailureReasons.length + submissionFailureReasons.length}>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {gateFailureReasons.length > 0 && (
              <div className="rounded border border-border bg-surface px-3 py-3 space-y-2">
                <div className="text-xs font-medium text-text-primary">Gate-3 失败原因</div>
                <div className="space-y-2 text-xs text-text-secondary">
                  {gateFailureReasons.slice(0, 4).map((item) => (
                    <div key={`gate-${item.reason}`} className="flex items-center justify-between gap-3">
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
                    <div key={`submission-${item.reason}`} className="flex items-center justify-between gap-3">
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
                            {refreshMode && (
                              <Badge variant="info">{formatTaskLabel(refreshMode)}</Badge>
                            )}
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
        <FactoryPreviewSection title="Submission / Evidence" count={strategyBriefs.length + strategyEvidenceBriefs.length}>
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
                    const committeeReview = asTypedObject<Record<string, unknown>>(item.committee_review);
                    const validationProfile = asTypedObject<Record<string, unknown>>(item.validation_profile);
                    const constraintCheck = asTypedObject<Record<string, unknown>>(item.constraint_check);
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
                            <div className="mt-1 break-all">strategy_id: {formatArtifactValue(item.strategy_id)}</div>
                          </div>
                          {strategyStatus && (
                            <Badge variant={previewBadgeVariant(strategyStatus)}>
                              {formatTaskLabel(strategyStatus)}
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {submissionLane && (
                            <Badge variant="neutral">{formatTaskLabel(submissionLane)}</Badge>
                          )}
                          {actionType && (
                            <Badge variant="info">{formatTaskLabel(actionType)}</Badge>
                          )}
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
                            <Badge variant="neutral">主验证 {formatTaskLabel(primaryValidationLayer)}</Badge>
                          )}
                          {refreshMode && (
                            <Badge variant="neutral">{formatTaskLabel(refreshMode)}</Badge>
                          )}
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
                          {item.created_strategy_pool ? (
                            <Badge variant="success">已创建入池</Badge>
                          ) : null}
                          {item.created_audit_only ? (
                            <Badge variant="warning">仅审计落档</Badge>
                          ) : null}
                          {item.refreshed_existing ? (
                            <Badge variant="info">刷新已有</Badge>
                          ) : null}
                          {item.live_candidate_ready ? (
                            <Badge variant="success">Live 候选</Badge>
                          ) : null}
                          {item.live_review_ready ? (
                            <Badge variant="info">待运行审查</Badge>
                          ) : null}
                          {item.direct_trade_candidate ? (
                            <Badge variant="warning">直达交易候选</Badge>
                          ) : null}
                        </div>
                        <div>
                          评审拆解：
                          {[
                            Number.isFinite(committeeExecutionScore) ? `执行:${committeeExecutionScore.toFixed(2)}` : '',
                            Number.isFinite(committeeCapacityScore) ? `容量:${committeeCapacityScore.toFixed(2)}` : '',
                            Number.isFinite(committeeAlignmentScore) ? `对齐:${committeeAlignmentScore.toFixed(2)}` : '',
                          ].filter(Boolean).join(' / ') || '-'}
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

/* ---------- sub-panels ---------- */

function FactoryRunComparisonTable({ runs }: { runs: FactoryRunItem[] }) {
  const rows = [
    {
      label: '状态',
      value: (run: FactoryRunItem) => getFactoryRunStatusLabel(run.status),
    },
    { label: '候选生成', value: (run: FactoryRunItem) => String(run.summary?.candidates_spawned ?? 0) },
    { label: '去重后', value: (run: FactoryRunItem) => String(run.summary?.candidates_after_dedup ?? 0) },
    { label: '提交数', value: (run: FactoryRunItem) => String(run.summary?.submitted ?? 0) },
    { label: '质检通过', value: (run: FactoryRunItem) => String(run.summary?.passed_quality_gate ?? 0) },
    { label: '研究任务', value: (run: FactoryRunItem) => String(run.summary?.autonomy_task_count ?? run.summary?.autonomy_task_briefs?.length ?? 0) },
    { label: '事件任务', value: (run: FactoryRunItem) => String(run.summary?.event_task_count ?? 0) },
    { label: '快照任务', value: (run: FactoryRunItem) => String(run.summary?.snapshot_task_count ?? 0) },
    { label: '混合模式', value: (run: FactoryRunItem) => formatMixedFlag(run.summary?.event_snapshot_mixed) },
    {
      label: '来源摘要',
      value: (run: FactoryRunItem) => formatCountSummary(run.summary?.task_source_counts),
      wrap: true,
    },
    {
      label: '主导来源',
      value: (run: FactoryRunItem) => {
        const [top] = sortCountEntries(run.summary?.task_source_counts);
        return top ? `${formatTaskLabel(top[0])} ${top[1]}` : '-';
      },
    },
    {
      label: '机会类型摘要',
      value: (run: FactoryRunItem) => formatCountSummary(run.summary?.scanner_task_types),
      wrap: true,
    },
    {
      label: '主导机会类型',
      value: (run: FactoryRunItem) => {
        const [top] = sortCountEntries(run.summary?.scanner_task_types);
        return top ? `${formatTaskLabel(top[0])} ${top[1]}` : '-';
      },
      wrap: true,
    },
    { label: '淘汰数', value: (run: FactoryRunItem) => String(run.summary?.eliminated ?? 0) },
    { label: '平均 DSR', value: (run: FactoryRunItem) => formatFactoryMetricValue(run.summary?.deflated_sharpe_ratio_avg, 2) },
    { label: '高 PBO 数', value: (run: FactoryRunItem) => String(run.summary?.high_pbo_count ?? 0) },
    { label: '正式多重检验', value: (run: FactoryRunItem) => String(run.summary?.formal_multiple_testing_count ?? 0) },
    { label: '弱 White RC', value: (run: FactoryRunItem) => String(run.summary?.weak_white_reality_check_count ?? 0) },
    { label: '弱 Hansen SPA', value: (run: FactoryRunItem) => String(run.summary?.weak_hansen_spa_count ?? 0) },
    { label: '耗时(秒)', value: (run: FactoryRunItem) => String(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? '-') },
  ];

  return (
    <div className="overflow-x-auto rounded border border-border bg-surface-alt">
      <table className="min-w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-surface">
            <th className="px-3 py-2 text-left font-medium whitespace-nowrap">指标</th>
            {runs.map((run, idx) => (
              <th key={run.run_id ?? run.started_at ?? idx} className="px-3 py-2 text-left font-medium whitespace-nowrap min-w-28">
                <div>第 {idx + 1} 次</div>
                <div className="mt-1 text-caption text-text-secondary font-normal">
                  {run.completed_at ?? run.started_at ?? '-'}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-border last:border-b-0">
              <td className="px-3 py-2 font-medium whitespace-nowrap">{row.label}</td>
              {runs.map((run, idx) => (
                <td
                  key={`${row.label}-${run.run_id ?? run.started_at ?? idx}`}
                  className={`px-3 py-2 text-text-secondary ${row.wrap ? 'whitespace-normal align-top min-w-36' : 'whitespace-nowrap'}`}
                >
                  {row.value(run)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FactoryRunTrendPanel({ runs, metricKey }: { runs: FactoryRunItem[]; metricKey: TrendMetricKey }) {
  const successCount = runs.filter((run) => run.status === 'success').length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : 0;
  const avgElapsed = runs.length > 0
    ? (runs.reduce((sum, run) => sum + Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0), 0) / runs.length).toFixed(1)
    : '0.0';
  const latest = runs[runs.length - 1];
  const first = runs[0];

  const metrics = [
    { key: 'candidates_spawned', label: '候选生成', value: (run: FactoryRunItem) => Number(run.summary?.candidates_spawned ?? 0) },
    { key: 'submitted', label: '提交数', value: (run: FactoryRunItem) => Number(run.summary?.submitted ?? 0) },
    { key: 'passed_quality_gate', label: '质检通过', value: (run: FactoryRunItem) => Number(run.summary?.passed_quality_gate ?? 0) },
    { key: 'elapsed_seconds', label: '耗时(秒)', value: (run: FactoryRunItem) => Number(run.elapsed_seconds ?? run.summary?.elapsed_seconds ?? 0) },
    {
      key: 'autonomy_task_count',
      label: '研究任务',
      value: (run: FactoryRunItem) => Number(run.summary?.autonomy_task_count ?? run.summary?.autonomy_task_briefs?.length ?? 0),
    },
    { key: 'event_task_count', label: '事件任务', value: (run: FactoryRunItem) => Number(run.summary?.event_task_count ?? 0) },
    { key: 'snapshot_task_count', label: '快照任务', value: (run: FactoryRunItem) => Number(run.summary?.snapshot_task_count ?? 0) },
    { key: 'deflated_sharpe_ratio_avg', label: '平均 DSR', value: (run: FactoryRunItem) => Number(run.summary?.deflated_sharpe_ratio_avg ?? 0), digits: 2 },
    { key: 'high_pbo_count', label: '高 PBO 数', value: (run: FactoryRunItem) => Number(run.summary?.high_pbo_count ?? 0) },
    { key: 'formal_multiple_testing_count', label: '正式多重检验', value: (run: FactoryRunItem) => Number(run.summary?.formal_multiple_testing_count ?? 0) },
  ];
  const activeMetric = metrics.find((metric) => metric.key === metricKey) ?? metrics[0];

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近成功率" value={`${successRate}%`} />
        <FactoryMetric title="平均耗时(秒)" value={avgElapsed} />
        <FactoryMetric title="最新候选数" value={latest?.summary?.candidates_spawned ?? 0} />
        <FactoryMetric title="最新质检通过" value={latest?.summary?.passed_quality_gate ?? 0} />
      </div>

      <div className="mt-4 space-y-3">
        {(() => {
          const values = runs.map(activeMetric.value);
          const max = Math.max(...values, 1);
          const latestValue = activeMetric.value(latest);
          const firstValue = activeMetric.value(first);
          const delta = latestValue - firstValue;
          const digits = activeMetric.digits ?? 0;

          return (
            <div className="rounded border border-border bg-surface px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium">{activeMetric.label}</span>
                <span className="text-text-secondary">
                  最新 {formatFactoryMetricValue(latestValue, digits)} · 较最早 {delta > 0 ? '+' : ''}{formatFactoryMetricValue(delta, digits)}
                </span>
              </div>
              <div className="mt-2 flex items-end gap-2 h-24">
                {runs.map((run, idx) => {
                  const value = activeMetric.value(run);
                  const height = Math.max((value / max) * 100, value > 0 ? 8 : 2);
                  return (
                    <div key={`${activeMetric.key}-${run.run_id ?? idx}`} className="flex-1 min-w-0">
                      <div className="h-20 flex items-end">
                        <div
                          className={`w-full rounded-t ${
                            run.status === 'failed'
                              ? 'bg-danger/70'
                              : run.status === 'partial'
                                ? 'bg-warning/70'
                                : run.status === 'skipped'
                                  ? 'bg-text-secondary/40'
                                  : 'bg-primary/70'
                          }`}
                          style={{ height: `${height}%` }}
                          title={`${activeMetric.label}: ${formatFactoryMetricValue(value, digits)}`}
                        />
                      </div>
                      <div className="mt-1 text-center text-caption text-text-secondary truncate">
                        {idx + 1}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

function FactoryRunFailurePanel({ runs, totalRuns }: { runs: FactoryRunItem[]; totalRuns: number }) {
  const failureRate = totalRuns > 0 ? Math.round((runs.length / totalRuns) * 100) : 0;
  const latestFailed = runs[0];
  const reasonBuckets = new Map<string, { count: number; example: string }>();
  const stageBuckets = new Map<string, number>();
  const unclassifiedExamples = new Map<string, number>();
  const matchedLabels = new Set<string>();
  let matchedCount = 0;

  runs.forEach((run) => {
    const fingerprint = getFactoryRunErrorFingerprint(run.error);
    const current = reasonBuckets.get(fingerprint.label);
    reasonBuckets.set(fingerprint.label, {
      count: (current?.count ?? 0) + 1,
      example: current?.example ?? fingerprint.example,
    });

    if (fingerprint.matched) {
      matchedCount += 1;
      matchedLabels.add(fingerprint.label);
    } else {
      unclassifiedExamples.set(fingerprint.example, (unclassifiedExamples.get(fingerprint.example) ?? 0) + 1);
    }

    const stage = detectFailedStage(run);
    stageBuckets.set(stage, (stageBuckets.get(stage) ?? 0) + 1);
  });

  const topReasons = [...reasonBuckets.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3);
  const topStages = [...stageBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const topUnclassifiedExamples = [...unclassifiedExamples.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const unclassifiedCount = runs.length - matchedCount;
  const matchRate = runs.length > 0 ? Math.round((matchedCount / runs.length) * 100) : 0;
  const coverageCount = matchedLabels.size;

  return (
    <div className="rounded border border-border bg-surface-alt p-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FactoryMetric title="最近失败次数" value={runs.length} />
        <FactoryMetric title="失败率" value={`${failureRate}%`} />
        <FactoryMetric title="最近失败阶段" value={detectFailedStage(latestFailed)} />
        <FactoryMetric title="最近失败时间" value={shortFactoryRunTime(latestFailed.completed_at ?? latestFailed.started_at)} />
      </div>

      <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
        <div className="text-xs font-medium mb-3">规则命中统计</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FactoryMetric title="规则命中失败" value={matchedCount} />
          <FactoryMetric title="规则命中率" value={`${matchRate}%`} />
          <FactoryMetric title="未分类错误" value={unclassifiedCount} />
          <FactoryMetric title="覆盖指纹种类" value={coverageCount} />
        </div>

        <div className="mt-3 text-xs text-text-secondary">
          统计口径：规则命中率 = 已命中规则失败数 / 最近失败总数；覆盖指纹种类仅统计已命中规则的错误类别。
        </div>

        {topUnclassifiedExamples.length > 0 && (
          <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3">
            <div className="text-xs font-medium mb-2">未分类错误示例</div>
            <div className="space-y-2 text-xs text-text-secondary">
              {topUnclassifiedExamples.map(([example, count]) => (
                <div key={example} className="flex items-start justify-between gap-3">
                  <span className="break-all">{example}</span>
                  <span className="shrink-0">{count} 次</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">常见错误原因</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topReasons.map(([reason, meta]) => (
              <div key={reason} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-all">{reason}</div>
                  <div className="mt-1 text-caption text-text-tertiary break-all">示例：{meta.example}</div>
                </div>
                <span className="shrink-0">{meta.count} 次</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">失败阶段分布</div>
          <div className="space-y-2 text-xs text-text-secondary">
            {topStages.map(([stage, count]) => (
              <div key={stage} className="flex items-center justify-between gap-3">
                <span>{stage}</span>
                <span>{count} 次</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {latestFailed?.error && (
        <div className="mt-4 rounded border border-border bg-surface px-3 py-3">
          <div className="text-xs font-medium mb-2">最近失败详情</div>
          <div className="text-xs text-danger break-all">{normalizeFactoryRunError(latestFailed.error)}</div>
          <div className="mt-2 text-caption text-text-secondary">
            错误指纹：{getFactoryRunErrorFingerprint(latestFailed.error).label}
          </div>
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
        feedbackSummary={isObjectRecord(detail.feedback_summary) ? detail.feedback_summary : null}
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

function FactoryCapabilityStateStrip({ factoryStatus }: { factoryStatus: FactoryStatusResponse | null | undefined }) {
  if (!factoryStatus) return null;

  const items = [
    {
      key: 'trace-ledger',
      label: 'Trace Ledger V2',
      implemented: Boolean(factoryStatus.trace_ledger_v2_implemented),
      enabled: Boolean(factoryStatus.trace_ledger_v2_enabled),
    },
    {
      key: 'gate-report',
      label: 'Gate Report V2',
      implemented: Boolean(factoryStatus.governance_gate_report_v2_implemented),
      enabled: Boolean(factoryStatus.gate_model_v2_enabled),
    },
    {
      key: 'entity-chain',
      label: 'Execution Entity Chain',
      implemented: Boolean(factoryStatus.execution_audit_entity_chain_available),
      enabled: Boolean(factoryStatus.execution_audit_entity_chain_available),
    },
  ];

  return (
    <div className="mt-3 rounded border border-border bg-surface-alt px-3 py-3 text-xs text-text-secondary">
      <div className="font-medium text-text-primary">治理能力读面</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <Badge key={item.key} variant={item.implemented ? (item.enabled ? 'success' : 'warning') : 'neutral'}>
            {item.label} {item.implemented ? '已实现' : '未实现'} / {item.enabled ? '已启用' : '未启用'}
          </Badge>
        ))}
      </div>
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
                {[
                { key: 'candidates_spawned', label: '候选生成' },
                { key: 'submitted', label: '提交数' },
                { key: 'passed_quality_gate', label: '质检通过' },
                { key: 'elapsed_seconds', label: '耗时' },
                { key: 'autonomy_task_count', label: '研究任务' },
                { key: 'event_task_count', label: '事件任务' },
                { key: 'snapshot_task_count', label: '快照任务' },
                { key: 'deflated_sharpe_ratio_avg', label: '平均 DSR' },
                { key: 'high_pbo_count', label: '高 PBO 数' },
                { key: 'formal_multiple_testing_count', label: '正式多重检验' },
              ].map((item) => (
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
