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

export function getStrategyMetricSnapshot(strategy: StrategyMetricCarrier | null | undefined): StrategyMetricSnapshot {
  const description = String(strategy?.description ?? '');
  const summaryMatch = description.match(STRATEGY_BACKTEST_SUMMARY_REGEX);
  const parsedSharpe = summaryMatch ? Number(summaryMatch[1]) : null;
  const parsedReturn = summaryMatch ? Number(summaryMatch[2]) : null;
  const parsedDrawdown = summaryMatch ? Number(summaryMatch[3]) : null;

  return {
    totalReturn: resolveNumber(
      strategy?.metrics?.annual_return,
      strategy?.metrics?.total_return,
      strategy?.total_return,
      parsedReturn,
    ),
    sharpe: resolveNumber(
      strategy?.metrics?.sharpe_ratio,
      strategy?.sharpe_ratio,
      parsedSharpe,
    ),
    maxDrawdown: resolveNumber(
      strategy?.metrics?.max_drawdown,
      strategy?.max_drawdown,
      parsedDrawdown,
    ),
  };
}
