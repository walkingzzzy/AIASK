import { extractArray } from '@/lib/data-utils';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import type { Strategy } from '../types';
import { resolveMarketStatusMeta } from '../lib/incubation-surface';

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
export type StrategyMarketStatusSegment = 'visible' | 'submitted' | 'draft' | 'rejected' | 'archived' | 'all';
export type StrategyMarketStatusCounts = Record<StrategyMarketStatusSegment, number>;

const VISIBLE_STRATEGY_STATUSES = new Set(['listed', 'incubating']);

const STATUS_SEGMENT_META: Record<StrategyMarketStatusSegment, { label: string; helpText: string }> = {
  visible: {
    label: '市场可见',
    helpText: '只展示已经进入市场可见层的策略，包含 listed 和 incubating。',
  },
  submitted: {
    label: '已提交',
    helpText: '查看已经提交但还未进入市场可见层的策略，适合继续跟踪提交后状态。',
  },
  draft: {
    label: '草稿',
    helpText: '查看仍停留在草稿态的策略，适合继续编辑、补实验或等待下一轮工厂处理。',
  },
  rejected: {
    label: '已淘汰',
    helpText: '查看被工厂淘汰或驳回的策略，便于排查质量门、回测和审计原因。',
  },
  archived: {
    label: '已归档',
    helpText: '查看已经归档的历史策略，适合回顾曾经上架或处理过的旧策略。',
  },
  all: {
    label: '全部状态',
    helpText: '按统一目录查看所有状态的策略，用于确认工厂实际产出总量。',
  },
};

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

export function normalizeStrategyStatusSegment(raw?: string | null): StrategyMarketStatusSegment {
  const value = String(raw ?? '').trim().toLowerCase();
  if (value === 'submitted' || value === 'draft' || value === 'rejected' || value === 'archived' || value === 'all') {
    return value;
  }
  return 'visible';
}

export function resolveStrategyStatusMeta(status?: string | null) {
  return resolveMarketStatusMeta(status);
}

export function resolveStatusSegmentLabel(segment: StrategyMarketStatusSegment) {
  return STATUS_SEGMENT_META[segment].label;
}

export function resolveStatusSegmentHelpText(segment: StrategyMarketStatusSegment) {
  return STATUS_SEGMENT_META[segment].helpText;
}

export function matchesStrategyStatusSegment(strategy: Strategy, segment: StrategyMarketStatusSegment) {
  if (segment === 'all') return true;
  const status = String((strategy as Strategy & { status?: string }).status ?? '').trim().toLowerCase();
  if (segment === 'visible') {
    return VISIBLE_STRATEGY_STATUSES.has(status);
  }
  return status === segment;
}

export function getStrategyStatusCounts(strategies: Strategy[]): StrategyMarketStatusCounts {
  return {
    visible: strategies.filter((strategy) => matchesStrategyStatusSegment(strategy, 'visible')).length,
    submitted: strategies.filter((strategy) => matchesStrategyStatusSegment(strategy, 'submitted')).length,
    draft: strategies.filter((strategy) => matchesStrategyStatusSegment(strategy, 'draft')).length,
    rejected: strategies.filter((strategy) => matchesStrategyStatusSegment(strategy, 'rejected')).length,
    archived: strategies.filter((strategy) => matchesStrategyStatusSegment(strategy, 'archived')).length,
    all: strategies.length,
  };
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
