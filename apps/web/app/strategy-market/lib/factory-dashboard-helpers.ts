import type { FactoryRunItem, FactoryRunSummary } from '@/app/strategy-market/types';

export function formatRatioPercent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${Math.round(Number(value) * 100)}%`;
}

export function formatFactoryMetricValue(value?: number | null, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(digits);
}

export function hasRunAuditMetrics(summary?: FactoryRunSummary | null) {
  if (!summary) return false;
  return [
    summary.deflated_sharpe_ratio_avg,
    summary.high_pbo_count,
    summary.formal_multiple_testing_count,
    summary.weak_white_reality_check_count,
    summary.weak_hansen_spa_count,
  ].some((value) => value != null);
}

export function normalizeFactoryRunError(error?: string | null) {
  const text = String(error ?? '').trim();
  if (!text) return '未知错误';
  return text
    .split('\n')[0]
    .replace(/\s+/g, ' ')
    .replace(/[0-9]{4}-[0-9]{2}-[0-9]{2}[ t][0-9:.+-zZ]*/g, '<time>')
    .replace(/[0-9a-f]{8,}/gi, '<id>')
    .replace(/\b\d+\b/g, '<num>')
    .slice(0, 80);
}

export function getFactoryRunErrorFingerprint(error?: string | null) {
  const example = normalizeFactoryRunError(error);
  const normalized = example.toLowerCase();

  const rules: Array<{ label: string; patterns: RegExp[] }> = [
    { label: '超时错误', patterns: [/timeout/i, /timed out/i, /deadline/i, /超时/] },
    { label: '网络连接错误', patterns: [/connection/i, /network/i, /socket/i, /dns/i, /refused/i, /unreachable/i, /http/i] },
    { label: '数据库错误', patterns: [/postgres/i, /database/i, /sql/i, /asyncpg/i, /timescaledb/i, /db error/i] },
    { label: '权限错误', patterns: [/permission/i, /forbidden/i, /unauthorized/i, /access denied/i, /鉴权/, /权限/] },
    { label: '配置缺失', patterns: [/missing/i, /env/i, /config/i, /credential/i, /token/i, /api key/i, /配置/] },
    { label: '输入校验错误', patterns: [/invalid/i, /validation/i, /valueerror/i, /typeerror/i, /keyerror/i, /assert/i, /参数/, /校验/] },
    { label: '依赖加载错误', patterns: [/module not found/i, /importerror/i, /cannot import/i, /no module named/i, /dependency/i] },
  ];

  const matched = rules.find((rule) => rule.patterns.some((pattern) => pattern.test(normalized)));
  return {
    label: matched?.label ?? '未分类错误',
    example,
    matched: Boolean(matched),
  };
}

export function shortFactoryRunTime(value?: string | null) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

export function getFactoryRunStatusLabel(status?: string | null) {
  switch (String(status ?? '').trim().toLowerCase()) {
    case 'success':
      return '成功';
    case 'partial':
      return '部分成功';
    case 'skipped':
      return '已跳过';
    case 'failed':
      return '失败';
    default:
      return String(status ?? '-');
  }
}

export function getFactoryRunStatusVariant(status?: string | null): 'success' | 'warning' | 'danger' | 'neutral' {
  switch (String(status ?? '').trim().toLowerCase()) {
    case 'success':
      return 'success';
    case 'partial':
      return 'warning';
    case 'failed':
      return 'danger';
    case 'skipped':
      return 'neutral';
    default:
      return 'neutral';
  }
}

export function detectFailedStage(run?: FactoryRunItem | null) {
  if (!run || run.status !== 'failed') return '-';
  if (run.pipeline?.failed_stage) return run.pipeline.failed_stage;
  const order = ['collect', 'spawn', 'backtest', 'deduplicate', 'submit', 'elimination'];
  const stages = run.stages ?? {};
  for (const name of order) {
    const stage = stages[name];
    if (!stage) return name;
    if (stage.ok === false) return name;
  }
  return 'unknown';
}

export function formatTaskLabel(value?: string | null) {
  if (!value) return '-';
  if (value === 'event_driven') return '事件驱动';
  if (value === 'snapshot') return '快照';
  return String(value).replaceAll('_', ' ');
}

export function formatMixedFlag(value?: boolean | null) {
  return value ? '是' : '否';
}

export function sortCountEntries(record?: Record<string, number> | null) {
  return Object.entries(record ?? {}).sort((a, b) => Number(b[1] ?? 0) - Number(a[1] ?? 0));
}

export function formatCountSummary(record?: Record<string, number> | null, limit = 3) {
  const entries = sortCountEntries(record).slice(0, limit);
  if (entries.length === 0) return '-';
  return entries.map(([key, count]) => `${formatTaskLabel(key)} ${count}`).join(' · ');
}

export function aggregateSummaryCounts(
  runs: FactoryRunItem[],
  selector: (summary: FactoryRunSummary) => Record<string, number> | undefined,
) {
  const merged = new Map<string, number>();
  runs.forEach((run) => {
    const counts = selector(run.summary ?? {});
    Object.entries(counts ?? {}).forEach(([key, count]) => {
      merged.set(key, (merged.get(key) ?? 0) + Number(count ?? 0));
    });
  });
  return Object.fromEntries(sortCountEntries(Object.fromEntries(merged.entries())));
}
