export type TechnicalIndicatorSeries = {
  name: string;
  data: number[];
  color: string;
};

export type TechnicalIndicatorSummary = {
  key: string;
  entries: [string, string][];
};

function formatNumber(value: number) {
  if (!Number.isFinite(value)) return '-';
  if (Number.isInteger(value)) return String(value);
  if (Math.abs(value) >= 100) return value.toFixed(2);
  if (Math.abs(value) >= 1) return String(Number(value.toFixed(2)));
  return String(Number(value.toFixed(4)));
}

function parseNumericSeries(value: unknown): number[] | null {
  if (Array.isArray(value) && value.length > 0) {
    const normalized = value.map((item) => {
      if (typeof item === 'number' && Number.isFinite(item)) return item;
      if (typeof item === 'string' && item.trim() !== '' && Number.isFinite(Number(item))) return Number(item);
      if (item == null || item === '') return Number.NaN;
      return null;
    });
    if (normalized.every((item) => item !== null) && normalized.some((item) => typeof item === 'number' && Number.isFinite(item))) {
      return normalized as number[];
    }
  }

  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text.includes(',')) return null;
  const parts = text.split(',').map((item) => item.trim()).filter(Boolean);
  if (!parts.length) return null;
  const numbers = parts.map((item) => Number(item));
  if (numbers.some((item) => !Number.isFinite(item))) return null;
  return numbers;
}

function summarizeSeries(values: number[]) {
  if (!values.length) return '空序列';
  const latest = [...values].reverse().find((item) => Number.isFinite(item));
  return latest == null ? `共 ${values.length} 点` : `最新 ${formatNumber(latest)}（${values.length} 点）`;
}

function formatScalar(value: unknown): string {
  if (value == null || value === '') return '-';
  if (typeof value === 'number') return formatNumber(value);
  if (typeof value === 'boolean') return String(value);
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return `共 ${value.length} 项`;
  if (typeof value === 'object') return '已返回对象';
  return String(value);
}

export function parseIndicatorPayload(
  raw: unknown,
  colors: readonly string[],
): { series: TechnicalIndicatorSeries[]; summary: TechnicalIndicatorSummary[] } {
  const obj = raw as Record<string, unknown> | null;
  if (!obj || typeof obj !== 'object') {
    return { series: [], summary: [] };
  }

  const series: TechnicalIndicatorSeries[] = [];
  const summary: TechnicalIndicatorSummary[] = [];
  let colorIndex = 0;

  for (const [key, value] of Object.entries(obj)) {
    const directSeries = parseNumericSeries(value);
    if (directSeries) {
      series.push({
        name: key.toUpperCase(),
        data: directSeries,
        color: colors[colorIndex++ % colors.length],
      });
      continue;
    }

    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      summary.push({ key: key.toUpperCase(), entries: [['value', formatScalar(value)]] });
      continue;
    }

    const inner = value as Record<string, unknown>;
    const entries: [string, string][] = [];

    for (const [subKey, subValue] of Object.entries(inner)) {
      const nestedSeries = parseNumericSeries(subValue);
      if (nestedSeries) {
        series.push({
          name: `${key.toUpperCase()}_${subKey}`,
          data: nestedSeries,
          color: colors[colorIndex++ % colors.length],
        });
        entries.push([subKey, summarizeSeries(nestedSeries)]);
        continue;
      }
      entries.push([subKey, formatScalar(subValue)]);
    }

    if (entries.length > 0) {
      summary.push({ key: key.toUpperCase(), entries });
    }
  }

  return { series, summary };
}
