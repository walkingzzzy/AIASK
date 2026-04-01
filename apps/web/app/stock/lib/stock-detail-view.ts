export type Period = 'daily' | 'weekly' | 'monthly';

export type StockInfoTab = 'chart' | 'tech' | 'fund' | 'basic' | 'shares' | 'valuation' | 'peers' | 'ai' | 'news';

export const STOCK_INFO_TABS: Array<{ key: StockInfoTab; label: string }> = [
  { key: 'chart', label: 'K线图' },
  { key: 'tech', label: '技术面' },
  { key: 'fund', label: '资金流' },
  { key: 'basic', label: '基本面' },
  { key: 'shares', label: '股本' },
  { key: 'valuation', label: '估值' },
  { key: 'peers', label: '同行对比' },
  { key: 'ai', label: 'AI诊断' },
  { key: 'news', label: '资讯' },
];

export const STOCK_DETAIL_SKIP_KEYS = [
  'tool',
  'meta',
  'code',
  'sourceTool',
  'sourceTools',
  'argsMatched',
  'result',
  'traceId',
  'success',
  'data',
  'error',
  'source',
  'cached',
  'timestamp',
  'source_chain',
  'attempted_sources',
  'fallback_used',
  'fallback_reason',
  'data_timestamp',
];

export function getStockPeriodLabel(period: Period) {
  if (period === 'weekly') return '周线';
  if (period === 'monthly') return '月线';
  return '日线';
}
