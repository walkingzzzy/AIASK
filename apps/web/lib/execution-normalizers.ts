export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function toFiniteNumber(value: unknown): number | null {
  if (value == null) return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function briefDateTime(value: unknown): string {
  const text = String(value ?? '').trim();
  return text ? text.slice(0, 19).replace('T', ' ') : '-';
}

export function findExecutionId(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const root = payload as Record<string, unknown>;
  const candidates = [
    root.execution_id,
    root.executionId,
    root.task_id,
    root.taskId,
    root.id,
    (root.execution as Record<string, unknown> | undefined)?.task_id,
    (root.execution as Record<string, unknown> | undefined)?.taskId,
    (root.execution as Record<string, unknown> | undefined)?.execution_id,
    (root.execution as Record<string, unknown> | undefined)?.executionId,
    (root.execution as Record<string, unknown> | undefined)?.id,
  ];
  const hit =
    candidates.find((item) => typeof item === 'string' && item.trim()) ??
    candidates.find((item) => typeof item === 'number');
  return hit == null ? '' : String(hit);
}

export function briefSummary(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '暂无执行返回';
  const record = payload as Record<string, unknown>;
  const parts = [
    record.status ? `状态 ${String(record.status)}` : null,
    record.profile ? `策略 ${String(record.profile)}` : null,
    record.warning_count != null ? `告警 ${String(record.warning_count)}` : null,
    record.has_high_severity != null ? `高严重级 ${record.has_high_severity ? '是' : '否'}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : '暂无执行摘要';
}

export function isTransientMutationError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return /failed to fetch|networkerror|load failed/i.test(message);
}

export type ExecutionInsight = {
  taskId: string;
  code: string;
  status: string;
  algorithm: string;
  totalShares: number | null;
  durationMinutes: number | null;
  slices: number | null;
  warningCount: number;
  hasHighSeverity: boolean;
  estimatedCostTotal: number | null;
  lifecycleCount: number | null;
  softGateProfile: string;
};

export function readExecutionInsight(payload: unknown): ExecutionInsight | null {
  if (!payload || typeof payload !== 'object') return null;

  const root = asRecord(payload);
  const task = asRecord(root.task);
  const plan = asRecord(task.plan);
  const softGate = asRecord(root.soft_gate ?? root.softGate ?? task.soft_gate ?? task.softGate);
  const costModel = asRecord(root.cost_model ?? root.costModel ?? task.cost_model ?? task.costModel);
  const estimated = asRecord(costModel.estimated);
  const warnings = Array.isArray(root.warnings)
    ? root.warnings
    : Array.isArray(task.pretrade_warnings)
      ? task.pretrade_warnings
      : [];
  const warningCount = Number(
    softGate.warning_count ?? softGate.warningCount ?? root.warning_count ?? root.warningCount ?? warnings.length,
  );

  const insight = {
    taskId: findExecutionId(root) || findExecutionId(task),
    code: String(task.code ?? root.code ?? '').trim(),
    status: String(task.status ?? root.status ?? '').trim(),
    algorithm: String(task.algorithm ?? root.algorithm ?? '').trim(),
    totalShares: toFiniteNumber(task.total_shares ?? task.total_quantity ?? root.total_shares ?? root.total_quantity),
    durationMinutes: toFiniteNumber(plan.duration_minutes ?? plan.duration ?? root.duration_minutes ?? root.duration),
    slices: toFiniteNumber(plan.slices ?? root.slices),
    warningCount: Number.isFinite(warningCount) ? warningCount : warnings.length,
    hasHighSeverity: Boolean(
      softGate.has_high_severity ?? softGate.hasHighSeverity ?? root.has_high_severity ?? root.hasHighSeverity,
    ),
    estimatedCostTotal: toFiniteNumber(root.estimated_cost_total ?? root.estimatedCostTotal ?? estimated.total),
    lifecycleCount: toFiniteNumber(
      root.lifecycle_count ?? root.lifecycleCount ?? (Array.isArray(task.lifecycle) ? task.lifecycle.length : null),
    ),
    softGateProfile: String(softGate.profile ?? root.profile ?? '').trim(),
  };

  const hasExplicitWarningSignal =
    softGate.warning_count != null ||
    softGate.warningCount != null ||
    root.warning_count != null ||
    root.warningCount != null ||
    root.has_high_severity != null ||
    root.hasHighSeverity != null ||
    warnings.length > 0;
  const hasExecutionSignal = Boolean(
    insight.taskId ||
      insight.code ||
      insight.status ||
      insight.algorithm ||
      insight.totalShares != null ||
      insight.durationMinutes != null ||
      insight.slices != null ||
      insight.estimatedCostTotal != null ||
      insight.lifecycleCount != null ||
      insight.softGateProfile ||
      hasExplicitWarningSignal,
  );

  return hasExecutionSignal ? insight : null;
}
