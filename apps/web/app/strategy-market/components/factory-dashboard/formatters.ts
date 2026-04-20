'use client';

import { formatRatioPercent } from '@/app/strategy-market/lib/factory-dashboard-helpers';

export function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function asTypedObject<T extends Record<string, unknown>>(value: unknown): Partial<T> {
  return isObjectRecord(value) ? (value as Partial<T>) : {};
}

export function toDisplayCountEntries(value: unknown) {
  if (!isObjectRecord(value)) return [] as Array<[string, number]>;
  return Object.entries(value)
    .map(([key, raw]) => [key, Number(raw)] as [string, number])
    .filter(([, count]) => Number.isFinite(count) && count > 0);
}

export function toDisplayCountRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(toDisplayCountEntries(value));
}

export function toObjectArray(value: unknown) {
  if (!Array.isArray(value)) return [] as Array<Record<string, unknown>>;
  return value.filter((item): item is Record<string, unknown> => isObjectRecord(item));
}

export function toDisplayTextList(value: unknown, limit = 4) {
  if (!Array.isArray(value)) return [] as string[];
  return value
    .map((item) => String(item ?? '').trim())
    .filter(Boolean)
    .slice(0, limit);
}

export function toDisplayText(value: unknown) {
  if (value == null) return null;
  const text = String(value).trim();
  return text || null;
}

export function toDisplayNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function firstDefinedValue<T>(...values: Array<T | null | undefined>) {
  for (const value of values) {
    if (value != null) return value;
  }
  return null;
}

export function formatArtifactValue(value: unknown) {
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '-';
  if (value == null || value === '') return '-';
  return String(value);
}

export function formatArtifactScore(value: unknown, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : '-';
}

export function shortArtifactText(value: unknown, length = 48) {
  const text = toDisplayText(value);
  if (!text) return '-';
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

export function formatArtifactObjectSummary(value: unknown, limit = 4) {
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

export function formatConstraintAuditSummary(value: unknown) {
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

export function formatAttemptAdjustmentSummary(value: unknown) {
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

export function previewBadgeVariant(status: unknown): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
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

export function providerControlBadgeVariant(
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

export function validationGradeBadgeVariant(
  grade: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(grade ?? '').trim().toUpperCase();
  if (!normalized) return 'neutral';
  if (normalized === 'A' || normalized === 'B') return 'success';
  if (normalized === 'C') return 'warning';
  if (normalized === 'D') return 'danger';
  return 'info';
}

export function formatCountWithRate(count: unknown, rate: unknown) {
  const normalizedCount = toDisplayNumber(count);
  const formattedRate = formatRatioPercent(toDisplayNumber(rate));
  if (normalizedCount == null) return formattedRate;
  return `${normalizedCount} / ${formattedRate}`;
}

export function gradeDistributionEntries(value: unknown) {
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

export function formatGradeDistributionSummary(value: unknown) {
  const entries = gradeDistributionEntries(value);
  if (entries.length === 0) return '-';
  return entries.map(([grade, count]) => `${grade}:${count}`).join(' / ');
}

export function distributionsDiffer(left: unknown, right: unknown) {
  return formatGradeDistributionSummary(left) !== formatGradeDistributionSummary(right);
}

export function generationTierBadgeVariant(
  tier: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(tier ?? '').trim().toUpperCase();
  if (normalized === 'L3') return 'warning';
  if (normalized === 'L2') return 'info';
  if (normalized === 'L1') return 'success';
  return 'neutral';
}

export function toReasonTopEntries(value: unknown) {
  return toObjectArray(value)
    .map((item) => ({
      reason: toDisplayText(item.reason) ?? toDisplayText(item.reason_code) ?? '-',
      count: Number(item.count ?? 0),
    }))
    .filter((item) => item.reason && Number.isFinite(item.count) && item.count > 0);
}

export function toBooleanSupportEntries(value: unknown) {
  if (!isObjectRecord(value)) return [] as Array<{ key: string; enabled: boolean }>;
  return Object.entries(value)
    .filter(([, raw]) => typeof raw === 'boolean')
    .map(([key, raw]) => ({ key, enabled: Boolean(raw) }));
}
