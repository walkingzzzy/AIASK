import { extractArray } from '@/lib/data-utils';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import type { Strategy } from '../types';

export const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'momentum', label: '动量' },
  { key: 'value', label: '价值' },
  { key: 'quality', label: '质量' },
  { key: 'multi_factor', label: '多因子' },
  { key: 'macro', label: '宏观' },
] as const;

export const STRATEGY_TYPE_LABELS: Record<string, string> = {
  momentum: '动量',
  value: '价值',
  quality: '质量',
  quality_factor: '质量',
  multi_factor: '多因子',
  macro: '宏观',
  ma_cross: '均线',
  dsl_rule: 'DSL',
};

export type StrategySortKey = 'totalReturn' | 'sharpe' | 'maxDrawdown' | 'subscriber_count';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function countRows(value: unknown, keyLabel: string) {
  if (!isRecord(value)) return [];
  return Object.entries(value)
    .map(([key, count]) => ({
      [keyLabel]: key,
      count: Number(count ?? 0),
    }))
    .sort((left, right) => Number(right.count ?? 0) - Number(left.count ?? 0));
}

export function resolveCategoryLabel(key?: string | null) {
  const type = String(key ?? 'all');
  if (STRATEGY_TYPE_LABELS[type]) return STRATEGY_TYPE_LABELS[type];
  return CATEGORIES.find((item) => item.key === type)?.label ?? type;
}

export function filterAndSortStrategies(
  raw: unknown,
  search: string,
  sortBy: StrategySortKey,
  sortDir: 'desc' | 'asc',
) {
  const list = extractArray(raw, 'strategies', 'items', 'data') as Strategy[];
  let filtered = list;
  if (search.trim()) {
    const query = search.trim().toLowerCase();
    filtered = list.filter(
      (strategy) =>
        strategy.name.toLowerCase().includes(query) ||
        (strategy.description ?? '').toLowerCase().includes(query) ||
        (strategy.strategy_type ?? '').toLowerCase().includes(query),
    );
  }
  return [...filtered].sort((left, right) => {
    const leftMetrics = getStrategyMetricSnapshot(left);
    const rightMetrics = getStrategyMetricSnapshot(right);
    let leftValue: number;
    let rightValue: number;
    if (sortBy === 'subscriber_count') {
      leftValue = Number(left.subscriber_count ?? 0);
      rightValue = Number(right.subscriber_count ?? 0);
    } else {
      leftValue = Number(leftMetrics[sortBy] ?? Number.NEGATIVE_INFINITY);
      rightValue = Number(rightMetrics[sortBy] ?? Number.NEGATIVE_INFINITY);
    }
    return sortDir === 'desc' ? rightValue - leftValue : leftValue - rightValue;
  });
}
