'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { PageContainer, TabBar, SectionCard, KpiCard, KpiGrid, DataTable, Badge, StockCodeInput } from '@/components/ui';
import { CandlestickChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { useSearchParams } from 'next/navigation';
import { cacheText } from '@/lib/api';
import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useToast } from '@/components/ui/toast';
import { EmptyState } from '@/components/status-state';
import type { CacheMeta, NormalizedQuote, NormalizedKlinePoint, NormalizedOrderBook } from '@aiask/shared-types';

type Period = 'daily' | 'weekly' | 'monthly';
type QuoteData = { quote?: NormalizedQuote; tool?: string; meta?: CacheMeta };
type KlineData = { kline?: NormalizedKlinePoint[]; tool?: string; meta?: CacheMeta };
type ObData = { orderBook?: NormalizedOrderBook; tool?: string; meta?: CacheMeta };
type MarketTab = 'main' | 'limitup' | 'blocks' | 'trade' | 'index' | 'minute' | 'search';
type SavedMarketView = {
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

type InitialMarketViewState = SavedMarketView;

const DEFAULT_MARKET_CODE = '600519';
const MARKET_STARTER_CODES = [
  { code: '600519', label: '贵州茅台' },
  { code: '000001', label: '平安银行' },
  { code: '300750', label: '宁德时代' },
] as const;

const TABS = [
  { key: 'main', label: '基础行情' },
  { key: 'limitup', label: '涨停板' },
  { key: 'blocks', label: '板块' },
  { key: 'trade', label: '逐笔' },
  { key: 'index', label: '指数' },
  { key: 'minute', label: '分时' },
  { key: 'search', label: '搜索' },
] as const;

const MARKET_VIEW_STORAGE_KEY = 'aiask.market.saved-view.v1';

const MARKET_VIEW_PRESETS: Array<{ key: string; label: string; apply: () => Partial<SavedMarketView> }> = [
  { key: 'default', label: '基础看盘', apply: () => ({ activeTab: 'main', period: 'daily', submittedPeriod: 'daily' }) },
  { key: 'limitup', label: '涨停复盘', apply: () => ({ activeTab: 'limitup' }) },
  { key: 'blocks', label: '板块轮动', apply: () => ({ activeTab: 'blocks', blockCode: '' }) },
  { key: 'index', label: '指数盯盘', apply: () => ({ activeTab: 'index', indexCode: '000300' }) },
];

function isMarketTab(value: string | null): value is MarketTab {
  return value != null && TABS.some((tab) => tab.key === value);
}

function formatStableDateTime(value: string | number | null | undefined) {
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

function isPeriod(value: unknown): value is Period {
  return value === 'daily' || value === 'weekly' || value === 'monthly';
}

function resolveInitialMarketViewState({
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
  const base: InitialMarketViewState = {
    activeTab: initialTab,
    code: DEFAULT_MARKET_CODE,
    submittedCode: null,
    period: 'daily',
    submittedPeriod: 'daily',
    indexCode: initialIndexCode,
    searchKeyword: '',
    minutePeriod: '5m',
    blockCode: initialBlock,
  };

  if (typeof window === 'undefined') {
    return base;
  }

  const hasExplicitContext = Boolean(
    task || from || initialBlock || initialTab !== 'main' || initialIndexCode !== '000001',
  );
  if (hasExplicitContext) {
    return base;
  }

  try {
    const raw = window.localStorage.getItem(MARKET_VIEW_STORAGE_KEY);
    if (!raw) {
      return {
        ...base,
        submittedCode: DEFAULT_MARKET_CODE,
      };
    }

    const saved = JSON.parse(raw) as Partial<SavedMarketView>;
    return {
      activeTab: saved.activeTab && isMarketTab(saved.activeTab) ? saved.activeTab : base.activeTab,
      code: typeof saved.code === 'string' ? saved.code : base.code,
      submittedCode:
        typeof saved.submittedCode === 'string' || saved.submittedCode === null
          ? (saved.submittedCode ?? null)
          : base.submittedCode,
      period: isPeriod(saved.period) ? saved.period : base.period,
      submittedPeriod: isPeriod(saved.submittedPeriod) ? saved.submittedPeriod : base.submittedPeriod,
      indexCode: typeof saved.indexCode === 'string' && saved.indexCode ? saved.indexCode : base.indexCode,
      searchKeyword: typeof saved.searchKeyword === 'string' ? saved.searchKeyword : base.searchKeyword,
      minutePeriod: typeof saved.minutePeriod === 'string' && saved.minutePeriod ? saved.minutePeriod : base.minutePeriod,
      blockCode: typeof saved.blockCode === 'string' ? saved.blockCode : base.blockCode,
    };
  } catch {
    return {
      ...base,
      submittedCode: DEFAULT_MARKET_CODE,
    };
  }
}

export default function MarketPage() {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const requestedIndexCode = (searchParams.get('indexCode') || '').trim();
  const requestedBlock = (searchParams.get('block') || '').trim();
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const initialTab: MarketTab = requestedIndexCode ? 'index' : (isMarketTab(requestedTab) ? requestedTab : 'main');
  const initialBlock = requestedBlock;

  return (
    <MarketPageInner
      key={`${initialTab}:${requestedIndexCode}:${requestedBlock}`}
      initialTab={initialTab}
      initialIndexCode={requestedIndexCode || '000001'}
      initialBlock={initialBlock}
      task={task}
      from={from}
    />
  );
}

function MarketPageInner({
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
}) {
  const [initialView] = useState<InitialMarketViewState>(() =>
    resolveInitialMarketViewState({
      initialTab,
      initialIndexCode,
      initialBlock,
      task,
      from,
    }),
  );
  const { toast } = useToast();
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode(initialView.code);
  const [period, setPeriod] = useState<Period>(initialView.period);
  const [activeTab, setActiveTab] = useState<MarketTab>(initialView.activeTab);
  const [submittedCode, setSubmittedCode] = useState<string | null>(initialView.submittedCode);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>(initialView.submittedPeriod);
  const activeCode = submittedCode ?? resolvedCode ?? null;

  const quoteQ = useApiQuery<QuoteData>(
    activeCode ? `/market/quote?code=${encodeURIComponent(activeCode)}` : null,
    {
      parse: (raw) => {
        const obj = ensureRecord(raw, '行情报价');
        if ('quote' in obj && obj.quote != null && typeof obj.quote !== 'object') {
          throw new Error('行情报价.quote字段应为对象');
        }
        return obj as QuoteData;
      },
    },
  );
  const klineQ = useApiQuery<KlineData>(
    activeCode ? `/market/kline?code=${encodeURIComponent(activeCode)}&period=${submittedPeriod}` : null,
    {
      parse: (raw) => {
        const obj = ensureRecord(raw, '行情K线');
        if ('kline' in obj && obj.kline != null && !Array.isArray(obj.kline)) {
          throw new Error('行情K线.kline字段应为数组');
        }
        return obj as KlineData;
      },
    },
  );
  const obQ = useApiQuery<ObData>(
    activeCode ? `/market/order-book?code=${encodeURIComponent(activeCode)}` : null,
    {
      parse: (raw) => {
        const obj = ensureRecord(raw, '行情盘口');
        if ('orderBook' in obj && obj.orderBook != null && typeof obj.orderBook !== 'object') {
          throw new Error('行情盘口.orderBook字段应为对象');
        }
        return obj as ObData;
      },
    },
  );

  // Tab-level query paths (null = disabled)
  const [limitUpPath, setLimitUpPath] = useState<string | null>(null);
  const [limitUpStatsPath, setLimitUpStatsPath] = useState<string | null>(null);
  const [blocksPath, setBlocksPath] = useState<string | null>(null);
  const [tradePath, setTradePath] = useState<string | null>(null);
  const [indexPath, setIndexPath] = useState<string | null>(null);
  const [minutePath, setMinutePath] = useState<string | null>(null);
  const [searchPath, setSearchPath] = useState<string | null>(null);
  const [stockListPath, setStockListPath] = useState<string | null>(null);
  const [blockStocksPath, setBlockStocksPath] = useState<string | null>(null);
  const [indexCode, setIndexCode] = useState(initialView.indexCode);
  const [searchKeyword, setSearchKeyword] = useState(initialView.searchKeyword);
  const [minutePeriod, setMinutePeriod] = useState(initialView.minutePeriod);
  const [blockCode, setBlockCode] = useState(initialView.blockCode);
  const [batchCodes, setBatchCodes] = useState('');
  const effectiveLimitUpPath = activeTab === 'limitup' ? (limitUpPath ?? '/market/limit-up') : null;
  const effectiveLimitUpStatsPath = activeTab === 'limitup' ? (limitUpStatsPath ?? '/market/limit-up-stats') : null;
  const effectiveBlocksPath = activeTab === 'blocks' ? (blocksPath ?? '/market/blocks?blockType=industry') : null;
  const effectiveTradePath = activeTab === 'trade' ? tradePath : null;
  const effectiveIndexPath = activeTab === 'index'
    ? (indexPath ?? `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim() || '000001')}`)
    : null;
  const effectiveMinutePath = activeTab === 'minute' && activeCode
    ? (minutePath ?? `/market/minute-kline?code=${encodeURIComponent(activeCode)}&period=${minutePeriod}`)
    : null;
  const effectiveSearchPath = activeTab === 'search' ? searchPath : null;
  const effectiveStockListPath = activeTab === 'search' ? stockListPath : null;
  const effectiveBlockStocksPath = activeTab === 'blocks' && blockCode.trim()
    ? (blockStocksPath ?? `/market/block-stocks?blockCode=${encodeURIComponent(blockCode.trim())}`)
    : null;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const payload: SavedMarketView = {
      activeTab,
      code,
      submittedCode,
      period,
      submittedPeriod,
      indexCode,
      searchKeyword,
      minutePeriod,
      blockCode,
    };
    window.localStorage.setItem(MARKET_VIEW_STORAGE_KEY, JSON.stringify(payload));
  }, [activeTab, blockCode, code, indexCode, minutePeriod, period, searchKeyword, submittedCode, submittedPeriod]);

  function saveCurrentView() {
    if (typeof window === 'undefined') return;
    const payload: SavedMarketView = {
      activeTab,
      code,
      submittedCode,
      period,
      submittedPeriod,
      indexCode,
      searchKeyword,
      minutePeriod,
      blockCode,
    };
    window.localStorage.setItem(MARKET_VIEW_STORAGE_KEY, JSON.stringify(payload));
    toast('当前行情视图已保存', 'success');
  }

  function applyPreset(preset: Partial<SavedMarketView>) {
    if (preset.activeTab && isMarketTab(preset.activeTab)) setActiveTab(preset.activeTab);
    if (preset.code != null) setCode(preset.code);
    if (preset.submittedCode !== undefined) setSubmittedCode(preset.submittedCode);
    if (preset.period) setPeriod(preset.period);
    if (preset.submittedPeriod) setSubmittedPeriod(preset.submittedPeriod);
    if (preset.indexCode != null) setIndexCode(preset.indexCode);
    if (preset.searchKeyword != null) setSearchKeyword(preset.searchKeyword);
    if (preset.minutePeriod != null) setMinutePeriod(preset.minutePeriod);
    if (preset.blockCode != null) setBlockCode(preset.blockCode);
  }

  const limitUpQ = useApiQuery<unknown>(effectiveLimitUpPath, {
    parse: (raw) => ensureRecordOrArray(raw, '涨停列表'),
  });
  const limitUpStatsQ = useApiQuery<unknown>(effectiveLimitUpStatsPath, {
    parse: (raw) => ensureRecord(raw, '涨停统计详情'),
  });
  const blocksQ = useApiQuery<unknown>(effectiveBlocksPath, {
    parse: (raw) => ensureRecordOrArray(raw, '板块列表'),
  });
  const tradeQ = useApiQuery<unknown>(effectiveTradePath, {
    parse: (raw) => ensureRecordOrArray(raw, '逐笔成交'),
  });
  const indexQuoteQ = useApiQuery<unknown>(effectiveIndexPath, {
    parse: (raw) => ensureRecord(raw, '指数行情'),
  });
  const minuteKlineQ = useApiQuery<unknown>(effectiveMinutePath, {
    parse: (raw) => ensureRecordOrArray(raw, '分时K线'),
  });
  const searchQ = useApiQuery<unknown>(effectiveSearchPath, {
    parse: (raw) => ensureRecordOrArray(raw, '股票搜索结果'),
  });
  const stockListQ = useApiQuery<unknown>(effectiveStockListPath, {
    parse: (raw) => ensureRecordOrArray(raw, '股票列表'),
  });
  const blockStocksQ = useApiQuery<unknown>(effectiveBlockStocksPath, {
    parse: (raw) => ensureRecordOrArray(raw, '板块成分股'),
  });
  const batchQuotes = useApiMutation<unknown>({
    parse: (raw) => ensureRecordOrArray(raw, '批量行情'),
  });

  const tabPending = limitUpQ.isFetching || blocksQ.isFetching || tradeQ.isFetching || indexQuoteQ.isFetching || minuteKlineQ.isFetching || searchQ.isFetching || stockListQ.isFetching || blockStocksQ.isFetching || batchQuotes.isPending || limitUpStatsQ.isFetching;
  const tabError = limitUpQ.error || blocksQ.error || tradeQ.error || indexQuoteQ.error || minuteKlineQ.error || searchQ.error || blockStocksQ.error || batchQuotes.error || limitUpStatsQ.error;
  const primaryActionCls = 'px-3 py-1 rounded-full border border-primary text-xs text-primary cursor-pointer';
  const secondaryActionCls = 'px-3 py-1 rounded-full border border-border text-xs text-text-secondary cursor-pointer';
  const secondaryLinkCls = 'px-3 py-1 rounded-full border border-border text-xs text-text-secondary no-underline';

  const loading = quoteQ.isFetching || klineQ.isFetching || obQ.isFetching;
  const showPrimaryLoading = submittedCode != null && loading;

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const c = code.trim();
    if (c === activeCode && period === submittedPeriod) {
      quoteQ.refetch(); klineQ.refetch(); obQ.refetch();
    } else {
      setSubmittedCode(c);
      setSubmittedPeriod(period);
    }
  }

  const quote = quoteQ.data;
  const kline = klineQ.data;
  const ob = obQ.data;

  const candles = useMemo(() => kline?.kline ?? [], [kline]);
  const obView = useMemo(() => ob?.orderBook ?? { bids: [], asks: [], timestamp: null }, [ob]);
  // Sort ascending by date so newest candle appears on the right (standard chart convention)
  const candleData = useMemo(() => candles
    .map((x) => ({ date: x.date.slice(0, 10), open: x.open, close: x.close, low: x.low, high: x.high, volume: x.volume }))
    .sort((a, b) => a.date.localeCompare(b.date)), [candles]);

  const limitUpRows = useMemo(() => extractArray(limitUpQ.data) as Record<string, unknown>[], [limitUpQ.data]);
  const limitUpStatsObj = useMemo(() => extractObject(limitUpStatsQ.data) as Record<string, unknown> | null, [limitUpStatsQ.data]);
  const blocksRows = useMemo(() => extractArray(blocksQ.data) as Record<string, unknown>[], [blocksQ.data]);
  const blockStocksRows = useMemo(() => extractArray(blockStocksQ.data) as Record<string, unknown>[], [blockStocksQ.data]);
  const tradeRows = useMemo(() => extractArray(tradeQ.data) as Record<string, unknown>[], [tradeQ.data]);
  const indexObj = useMemo(() => {
    const o = extractObject(indexQuoteQ.data);
    return (o.quote ? extractObject(o.quote) : o) as Record<string, unknown> | null;
  }, [indexQuoteQ.data]);
  const minuteRows = useMemo(() => extractArray(minuteKlineQ.data) as Record<string, unknown>[], [minuteKlineQ.data]);
  const searchRows = useMemo(() => extractArray(searchQ.data) as Record<string, unknown>[], [searchQ.data]);
  const stockListRows = useMemo(() => extractArray(stockListQ.data) as Record<string, unknown>[], [stockListQ.data]);
  const batchRows = useMemo(() => extractArray(batchQuotes.data) as Record<string, unknown>[], [batchQuotes.data]);

  const quoteCache = quote?.meta?.cache;
  const klineCache = kline?.meta?.cache;
  const obCache = ob?.meta?.cache;
  const freshness = [quote?.meta?.fetchedAt, kline?.meta?.fetchedAt, ob?.meta?.fetchedAt].filter(Boolean).sort().at(-1) ?? '';
  const activeDisplayCode = activeCode || submittedCode || code.trim();
  const activeDisplayName = String((quote?.quote?.name ?? quote?.quote?.code ?? activeDisplayCode) || '当前标的');

  const tradeColumns = useMemo(() => [
    { key: 'time', label: '时间' },
    { key: 'price', label: '价格', align: 'right' as const },
    { key: 'volume', label: '成交量', align: 'right' as const },
    {
      key: 'direction', label: '方向',
      render: (v: unknown) => {
        const s = String(v ?? '');
        const isBuy = /买|buy/i.test(s);
        const isSell = /卖|sell/i.test(s);
        return <Badge variant={isBuy ? 'danger' : isSell ? 'success' : 'neutral'}>{s || '-'}</Badge>;
      },
    },
  ], []);

  const minuteCandleData = useMemo(() => minuteRows.map((r) => ({
    date: String(r.time ?? r.date ?? r.datetime ?? ''),
    open: Number(r.open ?? 0), close: Number(r.close ?? 0),
    low: Number(r.low ?? 0), high: Number(r.high ?? 0), volume: Number(r.volume ?? 0),
  })), [minuteRows]);
  return (
    <PageContainer>
      <h1>行情看板</h1>
      {(from || task) ? <div className="text-xs text-text-secondary mb-2">上下文跳转{from ? ` · 来源: ${from}` : ''}{task ? ` · 任务: ${task}` : ''}</div> : null}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
        <SectionCard className="p-4 xl:sticky xl:top-16">
          <form onSubmit={onSubmit} className="grid gap-3 lg:grid-cols-[minmax(0,220px)_120px_auto] lg:items-end">
            <StockCodeInput id="market-code" label="股票代码" value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>K线周期</span>
              <select value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="K线周期" className="border border-border rounded px-2 py-2 text-sm">
                <option value="daily">日线</option><option value="weekly">周线</option><option value="monthly">月线</option>
              </select>
            </label>
            <div className="flex gap-2 flex-wrap lg:justify-end">
              <button type="submit" disabled={showPrimaryLoading} className="px-4 py-2 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{showPrimaryLoading ? '加载中...' : '查询行情'}</button>
              <button type="button" onClick={saveCurrentView} className="px-3 py-2 rounded border border-primary text-primary hover:bg-primary/5 cursor-pointer text-sm">保存当前视图</button>
            </div>
          </form>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-text-secondary">首次进入可直接看这些示例标的</span>
            {MARKET_STARTER_CODES.map((item) => (
              <button
                key={item.code}
                type="button"
                onClick={() => {
                  setCode(item.code);
                  setSubmittedCode(item.code);
                  setSubmittedPeriod(period);
                }}
                className="px-2.5 py-1 rounded-full border border-border text-xs text-text-secondary hover:text-primary hover:border-primary cursor-pointer"
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="mt-3 text-text-secondary text-sm">
            更新：{formatStableDateTime(quoteQ.dataUpdatedAt)} ｜ 抓取：{formatStableDateTime(freshness)}
          </div>
          <details className="text-xs text-text-muted mt-1">
            <summary className="cursor-pointer">缓存详情</summary>
            <span>行情：{cacheText(quoteCache)} ｜ K线：{cacheText(klineCache)} ｜ 盘口：{cacheText(obCache)}</span>
          </details>
          <div className="mt-4 overflow-x-auto pb-1">
            <div className="min-w-max">
              <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-text-secondary">常用视图</span>
            {MARKET_VIEW_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => {
                  applyPreset(preset.apply());
                  toast(`已切换到${preset.label}`, 'info');
                }}
                className="px-2.5 py-1 rounded border border-border text-xs text-text-secondary hover:text-primary hover:border-primary cursor-pointer"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </SectionCard>

        <aside className="grid gap-4 xl:sticky xl:top-16">
          <SectionCard className="p-4 min-h-49">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="mt-0 mb-1">右侧摘要动作区</h3>
                <p className="m-0 text-xs leading-5 text-text-secondary">把盯盘后的高频动作固定在这里，避免在长页面里来回找按钮。</p>
              </div>
              <Badge variant="info">摘要</Badge>
            </div>
            <div className="mt-3 rounded-2xl border border-border bg-surface-alt/40 px-3 py-3">
              <div className="text-xs text-text-secondary">当前聚焦</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{activeDisplayName}</div>
              <div className="mt-1 text-xs text-text-secondary">代码：{activeDisplayCode || '未选择'} · 任务：{TABS.find((tab) => tab.key === activeTab)?.label ?? '基础行情'}</div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <button type="button" onClick={() => applyPreset({ activeTab: 'main' })} className="rounded-xl border border-border px-3 py-2 text-left text-sm cursor-pointer hover:bg-surface-alt">回基础行情</button>
              <button type="button" onClick={() => applyPreset({ activeTab: 'blocks' })} className="rounded-xl border border-border px-3 py-2 text-left text-sm cursor-pointer hover:bg-surface-alt">看板块轮动</button>
              <Link href={activeDisplayCode ? `/paper-trading?code=${encodeURIComponent(activeDisplayCode)}&from=market` : '/paper-trading?from=market'} className="rounded-xl border border-border px-3 py-2 text-sm no-underline text-inherit hover:bg-surface-alt">去模拟交易</Link>
              <Link href={activeDisplayCode ? `/research?code=${encodeURIComponent(activeDisplayCode)}&from=market` : '/research?from=market'} className="rounded-xl border border-border px-3 py-2 text-sm no-underline text-inherit hover:bg-surface-alt">去研究页补充信息</Link>
            </div>
          </SectionCard>
        </aside>
      </div>
      {quoteQ.error ? <p className="text-error mt-3">降级提示：{quoteQ.error}</p> : null}
      {tabError ? <p className="text-error text-sm mt-1">{tabError}</p> : null}

      {/* ── 基础行情 cards always shown below the tab bar ── */}
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_320px] xl:items-start">
        <SectionCard className="min-h-105 p-3">
          <h3 className="mt-0">K线图（{period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'}）</h3>
          {candleData.length ? (
            <CandlestickChart data={candleData} height={360} />
          ) : (
            <div className="flex min-h-85 items-center">
              <EmptyState
                text="当前标的还没有可展示的 K 线"
                hint="你可以先切到示例标的确认页面正常，再决定是否换代码或切换到指数、板块视图继续看盘。"
                action={
                  <>
                    {MARKET_STARTER_CODES.slice(0, 2).map((item) => (
                      <button
                        key={`kline-${item.code}`}
                        type="button"
                        onClick={() => {
                          setCode(item.code);
                          setSubmittedCode(item.code);
                          setSubmittedPeriod(period);
                        }}
                        className={primaryActionCls}
                      >
                        看 {item.label}
                      </button>
                    ))}
                    <button type="button" onClick={() => applyPreset({ activeTab: 'index', indexCode: '000300' })} className={secondaryActionCls}>
                      切到指数盯盘
                    </button>
                  </>
                }
              />
            </div>
          )}
        </SectionCard>

        <div className="grid gap-4">
          <SectionCard className="min-h-55 p-3">
            <h3 className="mt-0">实时行情摘要</h3>
            {quote?.quote ? (() => {
              const q = quote.quote;
              const chg = Number(q.change ?? 0);
              const clr = chg >= 0 ? 'text-danger' : 'text-success';
              return (
                <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 xl:grid-cols-2">
                  <div className="col-span-full flex flex-wrap items-center gap-1">股票：<StockLink code={String(q.code)} name={String(q.name ?? '')} /><WatchlistButton code={String(q.code)} name={String(q.name ?? '')} /></div>
                  <div>现价：<span className={clr}>{fmtNum(q.price as number | null, 2)}</span></div>
                  <div>涨跌：<span className={clr}>{fmtNum(q.change as number | null, 2)}</span></div>
                  <div>涨跌幅：<span className={clr}>{fmtPct(q.changePercent as number | null)}</span></div>
                  <div>成交量：{fmtAmount(q.volume as number | null)}</div>
                  <div>成交额：{fmtAmount(q.amount as number | null)}</div>
                  <div>最高：{fmtNum(q.high as number | null, 2)}</div>
                  <div>最低：{fmtNum(q.low as number | null, 2)}</div>
                  <div>开盘：{fmtNum(q.open as number | null, 2)}</div>
                  <div>昨收：{fmtNum(q.prevClose as number | null, 2)}</div>
                </div>
              );
            })() : (
              <div className="flex min-h-35 items-center">
                <EmptyState
                  text="当前没有可展示的行情摘要"
                  hint="首次进入建议直接点上方示例标的；如果你想先看整体环境，也可以切到板块或涨停复盘视图。"
                  action={
                    <>
                      <button type="button" onClick={() => applyPreset({ activeTab: 'blocks' })} className={primaryActionCls}>
                        去看板块轮动
                      </button>
                      <button type="button" onClick={() => applyPreset({ activeTab: 'limitup' })} className={secondaryActionCls}>
                        去看涨停复盘
                      </button>
                    </>
                  }
                />
              </div>
            )}
          </SectionCard>

          <SectionCard className="min-h-55 p-3">
            <h3 className="mt-0">五档盘口</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="font-medium text-danger mb-1">卖盘</div>
                {[...obView.asks].reverse().map((x, i, arr) => <div key={`a${i}`} className="flex justify-between py-0.5 text-danger/80">
                  <span>卖{arr.length - i}</span><span>{fmtNum(x.price, 2)}</span><span>{fmtAmount(x.volume)}</span>
                </div>)}
              </div>
              <div>
                <div className="font-medium text-success mb-1">买盘</div>
                {obView.bids.map((x, i) => <div key={`b${i}`} className="flex justify-between py-0.5 text-success/80">
                  <span>买{i + 1}</span><span>{fmtNum(x.price, 2)}</span><span>{fmtAmount(x.volume)}</span>
                </div>)}
              </div>
            </div>
          </SectionCard>
        </div>
      </div>

      {activeTab === 'limitup' ? (
        <SectionCard tabAttached>
          <button type="button" disabled={tabPending} onClick={() => {
            if (effectiveLimitUpPath) limitUpQ.refetch(); else setLimitUpPath('/market/limit-up');
            if (effectiveLimitUpStatsPath) limitUpStatsQ.refetch(); else setLimitUpStatsPath('/market/limit-up-stats');
          }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '刷新'}</button>
          {limitUpStatsObj ? (
            <KpiGrid cols={3}>
              <KpiCard title="涨停总数" value={limitUpStatsObj.totalLimitUp as number ?? limitUpStatsObj.total as number ?? '-'} />
              <KpiCard title="首板数量" value={limitUpStatsObj.firstBoard as number ?? limitUpStatsObj.first_board as number ?? '-'} />
              <KpiCard title="封板成功率" value={fmtPct(Number(limitUpStatsObj.successRate ?? limitUpStatsObj.success_rate ?? 0))} />
            </KpiGrid>
          ) : null}
          {limitUpRows.length ? <DataTable rows={limitUpRows} columns={[
            { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
            { key: 'name', label: '名称' },
            { key: 'price', label: '现价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: 'changePercent', label: '涨幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
            { key: 'continuousDays', label: '连板', align: 'right' as const },
            { key: 'industry', label: '行业' },
            { key: '_watch', label: '', width: 40, render: (_: unknown, row: Record<string, unknown>) => <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} /> },
          ]} maxHeight={400} onExport={() => exportCSV(limitUpRows, 'limit-up')} /> : (
            !tabPending && !limitUpQ.error ? (
              <EmptyState
                text="当前还没有涨停榜单"
                hint="如果你在做日内复盘，可以先刷新榜单；如果更想看整体强弱，先去板块轮动通常更直接。"
                action={
                  <>
                    <button type="button" onClick={() => applyPreset({ activeTab: 'blocks' })} className={primaryActionCls}>
                      看板块轮动
                    </button>
                    <Link href="/research" className={secondaryLinkCls}>去研究页找催化</Link>
                  </>
                }
              />
            ) : null
          )}
        </SectionCard>
      ) : null}
      {activeTab === 'blocks' ? (
        <SectionCard tabAttached>
          <button type="button" disabled={tabPending} onClick={() => {
            if (effectiveBlocksPath) blocksQ.refetch(); else setBlocksPath('/market/blocks?blockType=industry');
          }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '加载行业板块'}</button>
          {blocksRows.length ? <DataTable rows={blocksRows} columns={[
            { key: 'code', label: '板块代码' },
            { key: 'name', label: '板块名称' },
            { key: 'stockCount', label: '股票数', align: 'right' as const },
            { key: 'avgChange', label: '平均涨幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
            { key: 'leaderName', label: '领涨股' },
          ]} maxHeight={400} onExport={() => exportCSV(blocksRows, 'blocks')} searchable onRowClick={(row) => {
            const c = String(row.code ?? '');
            if (c) {
              setBlockCode(c);
              const p = `/market/block-stocks?blockCode=${encodeURIComponent(c)}`;
              if (p === effectiveBlockStocksPath) blockStocksQ.refetch(); else setBlockStocksPath(p);
            }
          }} />
            : (!tabPending && !blocksQ.error ? (
              <EmptyState
                text="先加载行业板块再看轮动"
                hint="板块页更适合作为行情入口：先找到强弱板块，再点进成分股或回个股页继续看。"
                action={
                  <>
                    <button type="button" onClick={() => {
                      if (effectiveBlocksPath) blocksQ.refetch(); else setBlocksPath('/market/blocks?blockType=industry');
                    }} className={primaryActionCls}>
                      加载行业板块
                    </button>
                    <Link href="/fund-flow" className={secondaryLinkCls}>去看资金流向</Link>
                  </>
                }
              />
            ) : null)}
          <div className="flex gap-2 items-center mt-2">
            <input value={blockCode} onChange={(e) => setBlockCode(e.target.value)} placeholder="板块代码" aria-label="板块代码" className="w-40 px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              const p = `/market/block-stocks?blockCode=${encodeURIComponent(blockCode.trim())}`;
              if (p === effectiveBlockStocksPath) blockStocksQ.refetch(); else setBlockStocksPath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">查看成分股</button>
          </div>
          {blockStocksRows.length ? <DataTable rows={blockStocksRows} columns={[
            { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
            { key: 'name', label: '名称' },
            { key: 'price', label: '现价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: 'changePercent', label: '涨跌幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
          ]} maxHeight={400} onExport={() => exportCSV(blockStocksRows, 'block-stocks')} /> : null}
        </SectionCard>
      ) : null}
      {activeTab === 'trade' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="股票代码" aria-label="股票代码" className="w-35 px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              if (!validate()) return;
              const p = `/market/trade-details?code=${encodeURIComponent(code.trim())}`;
              if (p === tradePath) tradeQ.refetch(); else setTradePath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '查询逐笔明细'}</button>
          </div>
          {tradeRows.length ? <DataTable rows={tradeRows} columns={tradeColumns} maxHeight={400} onExport={() => exportCSV(tradeRows, 'trade-details')} />
            : (!tabPending && !tradeQ.error ? (
              <EmptyState
                text="输入股票代码后查看逐笔成交"
                hint="逐笔明细更适合在你已经锁定标的后使用；如果还没锁定，先去搜索或看基础行情会更快。"
                action={
                  <>
                    <button type="button" onClick={() => applyPreset({ activeTab: 'search' })} className={primaryActionCls}>
                      先去搜索标的
                    </button>
                    <button type="button" onClick={() => {
                      setCode(DEFAULT_MARKET_CODE);
                      setSubmittedCode(DEFAULT_MARKET_CODE);
                    }} className={secondaryActionCls}>
                      加载示例标的
                    </button>
                  </>
                }
              />
            ) : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'index' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={indexCode} onChange={(e) => setIndexCode(e.target.value)} placeholder="指数代码 如 000001" aria-label="指数代码" className="w-40 px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              const p = `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim())}`;
              if (p === effectiveIndexPath) indexQuoteQ.refetch(); else setIndexPath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '查询指数行情'}</button>
          </div>
          {indexObj ? (
            <KpiGrid cols={4}>
              <KpiCard title="指数名称" value={String(indexObj.name ?? indexObj.index_name ?? '-')} />
              <KpiCard title="最新点位" value={fmtNum(indexObj.price ?? indexObj.close ?? null)} />
              <KpiCard title="涨跌幅" value={fmtPct(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? null)} change={Number(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? 0)} />
              <KpiCard title="成交额" value={fmtAmount(indexObj.amount ?? indexObj.turnover ?? null)} />
              <KpiCard title="最高" value={fmtNum(indexObj.high ?? null)} />
              <KpiCard title="最低" value={fmtNum(indexObj.low ?? null)} />
              <KpiCard title="开盘" value={fmtNum(indexObj.open ?? null)} />
              <KpiCard title="昨收" value={fmtNum(indexObj.prevClose ?? indexObj.prev_close ?? null)} />
            </KpiGrid>
          ) : (!tabPending && !indexQuoteQ.error ? (
            <EmptyState
              text="输入指数代码后查看指数行情"
              hint="如果你只是想先判断大盘环境，可直接看 000001 上证指数或 000300 沪深300。"
              action={
                <>
                  <button type="button" onClick={() => setIndexCode('000001')} className={primaryActionCls}>示例：000001</button>
                  <button type="button" onClick={() => setIndexCode('000300')} className={secondaryActionCls}>示例：000300</button>
                </>
              }
            />
          ) : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'minute' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="股票代码" aria-label="股票代码" className="w-35 px-2 py-1 border border-border rounded text-sm" />
            <select value={minutePeriod} onChange={(e) => setMinutePeriod(e.target.value)} aria-label="分时周期" className="border border-border rounded px-2 py-1 text-sm">
              <option value="1m">1分钟</option><option value="5m">5分钟</option><option value="15m">15分钟</option><option value="30m">30分钟</option><option value="60m">60分钟</option>
            </select>
            <button type="button" disabled={tabPending} onClick={() => {
              if (!validate()) return;
              const p = `/market/minute-kline?code=${encodeURIComponent(code.trim())}&period=${minutePeriod}`;
              if (p === effectiveMinutePath) minuteKlineQ.refetch(); else setMinutePath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '查询分时'}</button>
          </div>
          {minuteCandleData.length ? <CandlestickChart data={minuteCandleData} height={360} />
            : (!tabPending && !minuteKlineQ.error ? (
              <EmptyState
                text="选择周期后加载分钟级 K 线"
                hint="分时更适合盘中确认节奏；如果只是看方向，先用基础行情日线会更稳。"
                action={
                  <>
                    <button type="button" onClick={() => setMinutePeriod('5m')} className={primaryActionCls}>用 5 分钟周期</button>
                    <button type="button" onClick={() => applyPreset({ activeTab: 'main' })} className={secondaryActionCls}>回基础行情</button>
                  </>
                }
              />
            ) : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'search' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={searchKeyword} onChange={(e) => setSearchKeyword(e.target.value)} placeholder="搜索股票" aria-label="搜索关键词" className="w-50 px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              const p = `/market/search?keyword=${encodeURIComponent(searchKeyword.trim())}`;
              if (p === searchPath) searchQ.refetch(); else setSearchPath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '搜索中...' : '搜索'}</button>
          </div>
          {searchRows.length ? <DataTable rows={searchRows} columns={[
            { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
            { key: 'name', label: '名称' },
            { key: 'industry', label: '行业' },
            { key: '_watch', label: '', width: 40, sortable: false, render: (_: unknown, row: Record<string, unknown>) => <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} /> },
          ]} maxHeight={300} onExport={() => exportCSV(searchRows, 'search-results')} searchable /> : (
            !tabPending && !searchQ.error ? (
              <EmptyState
                text="先输入名称或代码开始搜索"
                hint="如果你还不确定代码，可以搜名称、行业词，或者直接加载全市场列表后再筛。"
                action={
                  <>
                    <button type="button" onClick={() => {
                      if (stockListPath) stockListQ.refetch(); else setStockListPath('/market/stock-list');
                    }} className={primaryActionCls}>
                      加载全市场列表
                    </button>
                    <Link href="/watchlist" className={secondaryLinkCls}>去自选股挑选</Link>
                  </>
                }
              />
            ) : null
          )}
          <div className="flex gap-2 items-center mt-3">
            <button type="button" disabled={tabPending} onClick={() => {
              if (stockListPath) stockListQ.refetch(); else setStockListPath('/market/stock-list');
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">加载全部股票列表</button>
          </div>
          {stockListRows.length ? <DataTable rows={stockListRows} columns={[
            { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
            { key: 'name', label: '名称' },
            { key: '_watch', label: '', width: 40, sortable: false, render: (_: unknown, row: Record<string, unknown>) => <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} /> },
          ]} maxHeight={300} onExport={() => exportCSV(stockListRows, 'stock-list')} searchable pageSize={50} /> : null}
          <div className="flex gap-2 items-center mt-3">
            <input value={batchCodes} onChange={(e) => setBatchCodes(e.target.value)} placeholder="批量代码，逗号分隔" aria-label="批量股票代码" className="w-75 px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => batchQuotes.trigger('/market/batch-quotes', { method: 'POST' }, { codes: batchCodes.split(',').map((s) => s.trim()) })} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">批量行情</button>
          </div>
          {batchRows.length ? <DataTable rows={batchRows} columns={[
            { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
            { key: 'name', label: '名称' },
            { key: 'price', label: '现价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: 'changePercent', label: '涨跌幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
            { key: 'volume', label: '成交量', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
            { key: 'amount', label: '成交额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
            { key: 'high', label: '最高', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: 'low', label: '最低', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: '_watch', label: '', width: 40, sortable: false, render: (_: unknown, row: Record<string, unknown>) => <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} /> },
          ]} maxHeight={300} onExport={() => exportCSV(batchRows, 'batch-quotes')} /> : null}
        </SectionCard>
      ) : null}
    </PageContainer>
  );
}
