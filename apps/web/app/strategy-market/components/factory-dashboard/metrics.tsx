'use client';

import { Badge } from '@/components/ui';
import {
  aggregateSummaryCounts,
  formatCountSummary,
  formatRatioPercent,
  formatTaskLabel,
  sortCountEntries,
} from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type { FactoryRunItem, FactoryRunSummary } from '../../types';

export function FactoryMetric({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded border border-border px-3 py-2 bg-surface-alt">
      <div className="text-xs text-text-secondary">{title}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

export function FactoryTaskStructurePanel({
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

export function FactoryRunStructureDiagnosticsPanel({ runs }: { runs: FactoryRunItem[] }) {
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

export function FactoryQualityAuditPanel({ summary }: { summary: FactoryRunSummary }) {
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
