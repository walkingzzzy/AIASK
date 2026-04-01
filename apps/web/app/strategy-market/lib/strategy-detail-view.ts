import type { FactoryReviewSection } from '@/app/strategy-market/types';

export const DETAIL_TABS = [
  { key: 'overview', label: '策略概览' },
  { key: 'tracking', label: '实盘跟踪' },
  { key: 'factory', label: '工厂审查' },
] as const;

export const FACTORY_SECTIONS: FactoryReviewSection[] = ['summary', 'incubation', 'runtime', 'vectors', 'experiments'];

export function extractTraceId(text: string | null): string | null {
  const source = String(text ?? '');
  const match = source.match(/trace[_-]?[A-Za-z0-9]+/i) ?? source.match(/traceId:\s*([A-Za-z0-9_-]+)/i);
  if (!match) return null;
  return match[1] ?? match[0] ?? null;
}

export function isMissingStrategyError(text: string | null): boolean {
  const source = String(text ?? '').toLowerCase();
  return (
    source.includes('404') ||
    source.includes('not_found') ||
    source.includes('strategy not found') ||
    source.includes('不存在') ||
    source.includes('未找到')
  );
}

export function firstFiniteNumber(...values: Array<number | null | undefined>) {
  for (const value of values) {
    if (value != null && Number.isFinite(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

export function formatMultipleTestingMode(value?: string | null) {
  const mode = String(value ?? '').trim();
  if (!mode) return '-';
  if (mode === 'formal_runtime') return '正式论文实现';
  if (mode === 'paper_runtime') return '论文实现';
  if (mode === 'runtime_proxy') return '运行时代理';
  return mode.replaceAll('_', ' ');
}
