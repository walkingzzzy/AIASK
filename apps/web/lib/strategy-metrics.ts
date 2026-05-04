import type { Strategy } from '@aiask/shared-types';

export type StrategyMetricSnapshot = {
  totalReturn: number | null;
  sharpe: number | null;
  maxDrawdown: number | null;
};

type StrategyMetricCarrier = Partial<Strategy> & {
  total_return?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown?: number | null;
};

const STRATEGY_BACKTEST_SUMMARY_REGEX = /Sharpe\s*([+-]?\d+(?:\.\d+)?)\s*\|\s*收益\s*([+-]?\d+(?:\.\d+)?)%\s*\|\s*回撤\s*([+-]?\d+(?:\.\d+)?)%/i;

function resolveNumber(...values: unknown[]) {
  for (const value of values) {
    if (value == null || value === '') continue;
    const numeric = Number(value);
    if (!Number.isNaN(numeric)) return numeric;
  }
  return null;
}

export function normalizeStrategyPercentMetric(value: unknown, unit: 'ratio' | 'percent' | 'auto' = 'ratio'): number | null {
  if (value == null || value === '') return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (unit === 'percent') return numeric;
  if (unit === 'ratio') return numeric * 100;
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
}

function resolvePercentMetric(
  ...candidates: Array<{ value: unknown; unit: 'ratio' | 'percent' }>
) {
  for (const candidate of candidates) {
    const normalized = normalizeStrategyPercentMetric(candidate.value, candidate.unit);
    if (normalized != null) return normalized;
  }
  return null;
}

export function getStrategyMetricSnapshot(strategy: StrategyMetricCarrier | null | undefined): StrategyMetricSnapshot {
  const description = String(strategy?.description ?? '');
  const summaryMatch = description.match(STRATEGY_BACKTEST_SUMMARY_REGEX);
  const parsedSharpe = summaryMatch ? Number(summaryMatch[1]) : null;
  const parsedReturn = summaryMatch ? Number(summaryMatch[2]) : null;
  const parsedDrawdown = summaryMatch ? Number(summaryMatch[3]) : null;

  return {
    totalReturn: resolvePercentMetric(
      { value: strategy?.metrics?.annual_return, unit: 'ratio' },
      { value: strategy?.metrics?.total_return, unit: 'ratio' },
      { value: strategy?.total_return, unit: 'ratio' },
      { value: parsedReturn, unit: 'percent' },
    ),
    sharpe: resolveNumber(
      strategy?.metrics?.sharpe_ratio,
      strategy?.sharpe_ratio,
      parsedSharpe,
    ),
    maxDrawdown: resolvePercentMetric(
      { value: strategy?.metrics?.max_drawdown, unit: 'ratio' },
      { value: strategy?.max_drawdown, unit: 'ratio' },
      { value: parsedDrawdown, unit: 'percent' },
    ),
  };
}
