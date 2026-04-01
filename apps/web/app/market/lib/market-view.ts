export type Period = 'daily' | 'weekly' | 'monthly';

export type MarketTab = 'main' | 'limitup' | 'blocks' | 'trade' | 'index' | 'minute' | 'search';

export type SavedMarketView = {
  activeTab: MarketTab;
  code: string;
  submittedCode: string | null;
  period: Period;
  submittedPeriod: Period;
  indexCode: string;
  searchKeyword: string;
  minutePeriod: string;
  blockCode: string;
};

export type InitialMarketViewState = SavedMarketView;

export const DEFAULT_MARKET_CODE = '600519';

export const MARKET_STARTER_CODES = [
  { code: '600519', label: '贵州茅台' },
  { code: '000001', label: '平安银行' },
  { code: '300750', label: '宁德时代' },
] as const;

export const TABS = [
  { key: 'main', label: '基础行情' },
  { key: 'limitup', label: '涨停板' },
  { key: 'blocks', label: '板块' },
  { key: 'trade', label: '逐笔' },
  { key: 'index', label: '指数' },
  { key: 'minute', label: '分时' },
  { key: 'search', label: '搜索' },
] as const;

export const MARKET_VIEW_STORAGE_KEY = 'aiask.market.saved-view.v1';

export const MARKET_VIEW_PRESETS: Array<{ key: string; label: string; apply: () => Partial<SavedMarketView> }> = [
  {
    key: 'default',
    label: '基础看盘',
    apply: () => ({ activeTab: 'main', period: 'daily', submittedPeriod: 'daily' }),
  },
  { key: 'limitup', label: '涨停复盘', apply: () => ({ activeTab: 'limitup' }) },
  { key: 'blocks', label: '板块轮动', apply: () => ({ activeTab: 'blocks', blockCode: '' }) },
  { key: 'index', label: '指数盯盘', apply: () => ({ activeTab: 'index', indexCode: '000300' }) },
];

export function isMarketTab(value: string | null): value is MarketTab {
  return value != null && TABS.some((tab) => tab.key === value);
}

export function formatStableDateTime(value: string | number | null | undefined) {
  if (value == null || value === '') return '-';
  if (typeof value === 'number' && value <= 0) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.getTime() <= 0) return '-';
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  const seconds = String(date.getUTCSeconds()).padStart(2, '0');
  return `${year}/${month}/${day} ${hours}:${minutes}:${seconds} UTC`;
}

export function isPeriod(value: unknown): value is Period {
  return value === 'daily' || value === 'weekly' || value === 'monthly';
}

export function resolveInitialMarketViewState({
  initialTab,
  initialIndexCode,
  initialBlock,
  task,
  from,
}: {
  initialTab: MarketTab;
  initialIndexCode: string;
  initialBlock: string;
  task: string | null;
  from: string | null;
}): InitialMarketViewState {
  const hasExplicitContext = Boolean(
    task || from || initialBlock || initialTab !== 'main' || initialIndexCode !== '000001',
  );
  return {
    activeTab: initialTab,
    code: DEFAULT_MARKET_CODE,
    submittedCode: hasExplicitContext ? null : DEFAULT_MARKET_CODE,
    period: 'daily',
    submittedPeriod: 'daily',
    indexCode: initialIndexCode,
    searchKeyword: '',
    minutePeriod: '5m',
    blockCode: initialBlock,
  };
}
