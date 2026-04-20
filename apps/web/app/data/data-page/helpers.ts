import type { ResourceKey } from './config';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function stringifyValue(value: unknown) {
  if (value == null || value === '') return '-';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function buildResourcePath(kind: ResourceKey, identifier: string) {
  switch (kind) {
    case 'toolCatalog':
      return '/data/tool-catalog';
    case 'workflowGuide':
      return `/data/workflow-guide?name=${encodeURIComponent(identifier)}`;
    case 'runSnapshot':
      return `/data/run-snapshot?runId=${encodeURIComponent(identifier)}`;
    case 'datasetQuality':
      return `/data/dataset-quality?datasetId=${encodeURIComponent(identifier)}`;
    case 'datasetProfile':
      return `/data/dataset-profile?datasetId=${encodeURIComponent(identifier)}`;
    case 'factorProfile':
      return `/data/factor-profile?factorId=${encodeURIComponent(identifier)}`;
    case 'modelProfile':
      return `/data/model-profile?modelId=${encodeURIComponent(identifier)}`;
    case 'strategyGovernance':
      return `/data/strategy-governance?strategyId=${encodeURIComponent(identifier)}`;
    case 'experimentSummary':
      return `/data/experiment-summary?experimentId=${encodeURIComponent(identifier)}`;
    case 'governanceReport':
      return '/data/governance-report';
    default:
      return '/data/tool-catalog';
  }
}

export function buildResourceSummaryRows(obj: Record<string, unknown>) {
  return Object.entries(obj)
    .filter(([, value]) => value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    .slice(0, 12)
    .map(([field, value]) => ({ field, value: stringifyValue(value) }));
}

function readOptionNumber(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (value == null || value === '') continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function normalizeOptionRow(row: Record<string, unknown>) {
  const type = String(row.type ?? row.option_type ?? row.side ?? '').toLowerCase();
  return {
    ...row,
    strike: readOptionNumber(row, ['strike', 'strikePrice', 'exercise_price']),
    lastPrice: readOptionNumber(row, ['lastPrice', 'last', 'price', 'close']),
    volume: readOptionNumber(row, ['volume', 'trade_volume']),
    openInterest: readOptionNumber(row, ['openInterest', 'open_interest', 'oi']),
    impliedVol: readOptionNumber(row, ['impliedVol', 'impliedVolatility', 'implied_volatility', 'iv']),
    type,
  };
}
