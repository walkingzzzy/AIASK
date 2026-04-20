export { normalizeStrategyDetailResponse } from '@aiask/shared-types';

export type StrategyManagerCallOptions = {
  timeoutMs?: number;
};

export type BackgroundFactoryRunStatus = 'queued' | 'running' | 'success' | 'failed';

export type BackgroundFactoryRunState = {
  request_id: string;
  status: BackgroundFactoryRunStatus;
  started_at: string;
  completed_at: string | null;
  message: string;
  error: string | null;
  upstream_run_id?: string | null;
};

export type RankingCacheKeyParams = {
  status?: string;
  strategy_type?: string;
  limit?: number;
  rank_keys?: string[];
  offset?: number;
};

export function detachTimer<T extends NodeJS.Timeout | ReturnType<typeof setInterval> | ReturnType<typeof setTimeout>>(
  timer: T,
): T {
  timer.unref?.();
  return timer;
}

export function getMarketTimeParts(
  now: Date,
  timezone: string,
): { year: string; month: string; day: string; hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now);

  const readPart = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
  return {
    year: readPart('year'),
    month: readPart('month'),
    day: readPart('day'),
    hour: Number(readPart('hour')),
    minute: Number(readPart('minute')),
  };
}

export function buildRankingCacheKey(params: RankingCacheKeyParams) {
  const status = params.status || 'visible';
  const type = params.strategy_type || 'all';
  const limit = params.limit || 50;
  const offset = params.offset || 0;
  const rankKeys = (params.rank_keys || []).join(',');
  return `strategy:ranking:${status}:${type}:${limit}:${offset}:${rankKeys}`;
}

export function buildFactoryRunsCacheKey(limit?: number) {
  return `strategy:factory:runs:${Math.max(1, Math.min(200, Number(limit) || 20))}`;
}

export function buildFactoryRunDetailCacheKey(runId: string) {
  return `strategy:factory:run:${runId}`;
}
