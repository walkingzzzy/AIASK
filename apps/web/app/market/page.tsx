'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { PageContainer, TabBar, SectionCard, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { AskAiButton } from '@/components/ask-ai-button';
import { CandlestickChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useHydrated } from '@/hooks/use-hydrated';
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
  {
    key: 'default',
    label: '基础看盘',
    apply: () => ({ activeTab: 'main', period: 'daily', submittedPeriod: 'daily' }),
  },
  { key: 'limitup', label: '涨停复盘', apply: () => ({ activeTab: 'limitup' }) },
  { key: 'blocks', label: '板块轮动', apply: () => ({ activeTab: 'blocks', blockCode: '' }) },
  { key: 'index', label: '指数盯盘', apply: () => ({ activeTab: 'index', indexCode: '000300' }) },
];
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)] disabled:cursor-not-allowed disabled:opacity-50';
const CHIP_BUTTON_CLS =
  'action-chip cursor-pointer text-xs text-text-primary disabled:cursor-not-allowed disabled:opacity-50';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

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
  const hasExplicitContext = Boolean(
    task || from || initialBlock || initialTab !== 'main' || initialIndexCode !== '000001',
  );
  const base: InitialMarketViewState = {
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
  return base;
}

export default function MarketPage() {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const requestedIndexCode = (searchParams.get('indexCode') || '').trim();
  const requestedBlock = (searchParams.get('block') || '').trim();
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const initialTab: MarketTab = requestedIndexCode ? 'index' : isMarketTab(requestedTab) ? requestedTab : 'main';
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
  const hydrated = useHydrated();
  const hasExplicitContext = Boolean(
    task || from || initialBlock || initialTab !== 'main' || initialIndexCode !== '000001',
  );
  const [initialView] = useState<InitialMarketViewState>(() =>
    resolveInitialMarketViewState({
      initialTab,
      initialIndexCode,
      initialBlock,
      task,
      from,
    }),
  );
  const [savedViewReady, setSavedViewReady] = useState(false);
  const { toast } = useToast();
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode(initialView.code);
  const [period, setPeriod] = useState<Period>(initialView.period);
  const [activeTab, setActiveTab] = useState<MarketTab>(initialView.activeTab);
  const [submittedCode, setSubmittedCode] = useState<string | null>(initialView.submittedCode);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>(initialView.submittedPeriod);
  const activeCode = submittedCode ?? resolvedCode ?? null;

  const quoteQ = useApiQuery<QuoteData>(activeCode ? `/market/quote?code=${encodeURIComponent(activeCode)}` : null, {
    parse: (raw) => {
      const obj = ensureRecord(raw, '行情报价');
      if ('quote' in obj && obj.quote != null && typeof obj.quote !== 'object') {
        throw new Error('行情报价.quote字段应为对象');
      }
      return obj as QuoteData;
    },
  });
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
  const obQ = useApiQuery<ObData>(activeCode ? `/market/order-book?code=${encodeURIComponent(activeCode)}` : null, {
    parse: (raw) => {
      const obj = ensureRecord(raw, '行情盘口');
      if ('orderBook' in obj && obj.orderBook != null && typeof obj.orderBook !== 'object') {
        throw new Error('行情盘口.orderBook字段应为对象');
      }
      return obj as ObData;
    },
  });

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
  const effectiveIndexPath =
    activeTab === 'index'
      ? (indexPath ?? `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim() || '000001')}`)
      : null;
  const effectiveMinutePath =
    activeTab === 'minute' && activeCode
      ? (minutePath ?? `/market/minute-kline?code=${encodeURIComponent(activeCode)}&period=${minutePeriod}`)
      : null;
  const effectiveSearchPath = activeTab === 'search' ? searchPath : null;
  const effectiveStockListPath = activeTab === 'search' ? stockListPath : null;
  const effectiveBlockStocksPath =
    activeTab === 'blocks' && blockCode.trim()
      ? (blockStocksPath ?? `/market/block-stocks?blockCode=${encodeURIComponent(blockCode.trim())}`)
      : null;

  const applyPreset = useCallback(
    (preset: Partial<SavedMarketView>) => {
      if (preset.activeTab && isMarketTab(preset.activeTab)) setActiveTab(preset.activeTab);
      if (preset.code != null) setCode(preset.code);
      if (preset.submittedCode !== undefined) setSubmittedCode(preset.submittedCode);
      if (preset.period) setPeriod(preset.period);
      if (preset.submittedPeriod) setSubmittedPeriod(preset.submittedPeriod);
      if (preset.indexCode != null) setIndexCode(preset.indexCode);
      if (preset.searchKeyword != null) setSearchKeyword(preset.searchKeyword);
      if (preset.minutePeriod != null) setMinutePeriod(preset.minutePeriod);
      if (preset.blockCode != null) setBlockCode(preset.blockCode);
    },
    [setCode],
  );

  useEffect(() => {
    if (!hydrated) return;
    if (hasExplicitContext) {
      setSavedViewReady(true);
      return;
    }
    try {
      const raw = window.localStorage.getItem(MARKET_VIEW_STORAGE_KEY);
      if (!raw) {
        setSavedViewReady(true);
        return;
      }
      const saved = JSON.parse(raw) as Partial<SavedMarketView>;
      applyPreset({
        activeTab: saved.activeTab && isMarketTab(saved.activeTab) ? saved.activeTab : undefined,
        code: typeof saved.code === 'string' ? saved.code : undefined,
        submittedCode:
          typeof saved.submittedCode === 'string' || saved.submittedCode === null
            ? (saved.submittedCode ?? null)
            : undefined,
        period: isPeriod(saved.period) ? saved.period : undefined,
        submittedPeriod: isPeriod(saved.submittedPeriod) ? saved.submittedPeriod : undefined,
        indexCode: typeof saved.indexCode === 'string' && saved.indexCode ? saved.indexCode : undefined,
        searchKeyword: typeof saved.searchKeyword === 'string' ? saved.searchKeyword : undefined,
        minutePeriod: typeof saved.minutePeriod === 'string' && saved.minutePeriod ? saved.minutePeriod : undefined,
        blockCode: typeof saved.blockCode === 'string' ? saved.blockCode : undefined,
      });
    } catch {
      // Ignore invalid saved view payloads and keep deterministic initial state.
    } finally {
      setSavedViewReady(true);
    }
  }, [applyPreset, hasExplicitContext, hydrated]);

  useEffect(() => {
    if (typeof window === 'undefined' || !hydrated || !savedViewReady) return;
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
  }, [
    activeTab,
    blockCode,
    code,
    hydrated,
    indexCode,
    minutePeriod,
    period,
    savedViewReady,
    searchKeyword,
    submittedCode,
    submittedPeriod,
  ]);

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

  const tabPending =
    limitUpQ.isFetching ||
    blocksQ.isFetching ||
    tradeQ.isFetching ||
    indexQuoteQ.isFetching ||
    minuteKlineQ.isFetching ||
    searchQ.isFetching ||
    stockListQ.isFetching ||
    blockStocksQ.isFetching ||
    batchQuotes.isPending ||
    limitUpStatsQ.isFetching;
  const tabError =
    limitUpQ.error ||
    blocksQ.error ||
    tradeQ.error ||
    indexQuoteQ.error ||
    minuteKlineQ.error ||
    searchQ.error ||
    blockStocksQ.error ||
    batchQuotes.error ||
    limitUpStatsQ.error;
  const primaryActionCls = HERO_PRIMARY_BUTTON_CLS;
  const secondaryActionCls = HERO_SECONDARY_BUTTON_CLS;
  const secondaryLinkCls = LINK_CHIP_CLS;
  const compactInputCls = FIELD_CLS;
  const compactSelectCls = `${FIELD_CLS} pr-10`;
  const sidebarActionCardCls =
    'panel-soft rounded-[24px] px-4 py-3 text-left no-underline text-inherit transition hover:-translate-y-0.5';

  const loading = quoteQ.isFetching || klineQ.isFetching || obQ.isFetching;
  const showPrimaryLoading = hydrated && submittedCode != null && loading;

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const c = code.trim();
    if (c === activeCode && period === submittedPeriod) {
      quoteQ.refetch();
      klineQ.refetch();
      obQ.refetch();
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
  const candleData = useMemo(
    () =>
      candles
        .map((x) => ({
          date: x.date.slice(0, 10),
          open: x.open,
          close: x.close,
          low: x.low,
          high: x.high,
          volume: x.volume,
        }))
        .sort((a, b) => a.date.localeCompare(b.date)),
    [candles],
  );

  const limitUpRows = useMemo(() => extractArray(limitUpQ.data) as Record<string, unknown>[], [limitUpQ.data]);
  const limitUpStatsObj = useMemo(
    () => extractObject(limitUpStatsQ.data) as Record<string, unknown> | null,
    [limitUpStatsQ.data],
  );
  const blocksRows = useMemo(() => extractArray(blocksQ.data) as Record<string, unknown>[], [blocksQ.data]);
  const blockStocksRows = useMemo(
    () => extractArray(blockStocksQ.data) as Record<string, unknown>[],
    [blockStocksQ.data],
  );
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
  const freshness =
    [quote?.meta?.fetchedAt, kline?.meta?.fetchedAt, ob?.meta?.fetchedAt].filter(Boolean).sort().at(-1) ?? '';
  const activeDisplayCode = activeCode || submittedCode || code.trim();
  const activeDisplayName = String((quote?.quote?.name ?? quote?.quote?.code ?? activeDisplayCode) || '当前标的');
  const activeTaskLabel = TABS.find((tab) => tab.key === activeTab)?.label ?? '基础行情';
  const activePeriodLabel =
    activeTab === 'main'
      ? submittedPeriod === 'daily'
        ? '日线'
        : submittedPeriod === 'weekly'
          ? '周线'
          : '月线'
      : activeTab === 'minute'
        ? `${minutePeriod} 分时`
        : activeTaskLabel;
  const freshnessLabel = formatStableDateTime(quoteQ.dataUpdatedAt);
  const quickJumpLinks = activeDisplayCode
    ? [
        { label: '个股详情', href: `/stock?code=${encodeURIComponent(activeDisplayCode)}` },
        { label: '技术分析', href: `/technical?code=${encodeURIComponent(activeDisplayCode)}` },
        { label: '研究页', href: `/research?code=${encodeURIComponent(activeDisplayCode)}` },
        { label: '模拟交易', href: `/paper-trading?code=${encodeURIComponent(activeDisplayCode)}&from=market` },
      ]
    : [
        { label: '去行情总览', href: '/market' },
        { label: '去自选股', href: '/watchlist' },
        { label: '去策略超市', href: '/strategy-market' },
      ];
  const heroNotes =
    activeTab === 'blocks'
      ? [
          '板块视图更适合作为盘面入口，先看强弱，再决定是否回个股继续深挖。',
          '如果板块热度和个股走势矛盾，优先看板块扩散和资金方向，而不是急着下结论。',
          '选强板块后再展开成分股，会比直接在海量个股里搜索更节省注意力。',
        ]
      : activeTab === 'limitup'
        ? [
            '涨停复盘适合回答“今天谁在带节奏”，不适合替代主行情视图长期停留。',
            '如果榜单很空，先回基础行情和板块热力，不要在空榜里反复刷新。',
            '看到连板标的后，建议继续去研究页找催化，再决定是否进入交易路径。',
          ]
        : [
            '基础行情先看价格、周期和盘口，再决定是否切到板块、涨停或分时。',
            '如果只是想判断环境，指数和板块通常比个股更适合作为第一眼入口。',
            '你可以先保存一套常用视图，让盘中切换更快，避免每次重复配置查询条件。',
          ];

  const tradeColumns = useMemo(
    () => [
      { key: 'time', label: '时间' },
      { key: 'price', label: '价格', align: 'right' as const },
      { key: 'volume', label: '成交量', align: 'right' as const },
      {
        key: 'direction',
        label: '方向',
        render: (v: unknown) => {
          const s = String(v ?? '');
          const isBuy = /买|buy/i.test(s);
          const isSell = /卖|sell/i.test(s);
          return <Badge variant={isBuy ? 'danger' : isSell ? 'success' : 'neutral'}>{s || '-'}</Badge>;
        },
      },
    ],
    [],
  );

  const minuteCandleData = useMemo(
    () =>
      minuteRows.map((r) => ({
        date: String(r.time ?? r.date ?? r.datetime ?? ''),
        open: Number(r.open ?? 0),
        close: Number(r.close ?? 0),
        low: Number(r.low ?? 0),
        high: Number(r.high ?? 0),
        volume: Number(r.volume ?? 0),
      })),
    [minuteRows],
  );
  const activeQuote = quote?.quote ?? null;
  const activeChange = Number(activeQuote?.change ?? 0);
  const activeChangeTone = activeChange >= 0 ? 'text-success' : 'text-danger';
  const cacheStatusItems = [
    { label: '行情缓存', value: cacheText(quoteCache) },
    { label: 'K 线缓存', value: cacheText(klineCache) },
    { label: '盘口缓存', value: cacheText(obCache) },
  ];
  const workspaceSummary =
    activeTab === 'blocks'
      ? '当前更适合先读板块强弱和扩散节奏，再决定是否回到单只股票继续深挖。'
      : activeTab === 'limitup'
        ? '当前以涨停结构为主，适合快速判断市场主线和连板情绪，而不是停留在单一标的。'
        : activeTab === 'index'
          ? '当前聚焦指数环境，先确认大盘方向，再决定是否切回个股或板块视图。'
          : activeTab === 'minute'
            ? '当前以分钟节奏确认盘中变化，适合辅助判断，不建议替代中期趋势视图。'
            : activeTab === 'search'
              ? '当前以搜索和筛选为主，先完成候选锁定，再回到主图与盘口工作区。'
              : '当前处于基础行情工作流，先确认趋势和价格，再结合摘要与盘口组织下一步动作。';
  const chartDescription =
    activeTab === 'minute'
      ? `当前展示 ${activePeriodLabel} 节奏，适合盘中确认结构变化。`
      : `当前主图以 ${activePeriodLabel} 为核心，先读趋势，再决定是否切换到板块、涨停或分时。`;
  const pageOffline = quoteQ.error === '数据服务暂不可用' || tabError === '数据服务暂不可用';
  const quoteErrorMessage = quoteQ.error && quoteQ.error !== '数据服务暂不可用' ? quoteQ.error : null;
  const tabErrorMessage = tabError && tabError !== '数据服务暂不可用' ? tabError : null;

  return (
    <PageContainer className="space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
        <section className="page-hero p-6 sm:p-7 xl:p-8">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl space-y-4">
                <div className="eyebrow">行情工作台 · {activeTaskLabel}</div>
                <div className="space-y-3">
                  <h1>{activeDisplayName}</h1>
                  <p className="page-lead mb-0">
                    先锁定观察标的，再围绕 {activePeriodLabel} 主图、实时摘要与盘口深度推进判断。这个工作台已经按
                    「查询、读图、决策」重排了阅读路径，减少来回跳视线的成本。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <AskAiButton
                    stockCode={activeDisplayCode}
                    prompt={activeDisplayCode ? `请解读 ${activeDisplayCode} 的当前走势与盘口` : '请分析当前行情看板'}
                    label="解读当前行情"
                  />
                  <AskAiButton
                    stockCode={activeDisplayCode}
                    prompt={activeDisplayCode ? `请给 ${activeDisplayCode} 一个下一步交易建议` : '请给出行情操作建议'}
                    label="交易建议"
                  />
                  <Link
                    href={
                      activeDisplayCode
                        ? `/research?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                        : '/research?from=market'
                    }
                    className={secondaryLinkCls}
                  >
                    去研究页补信息
                  </Link>
                </div>
              </div>

              <div className={`${PANEL_CLS} w-full max-w-[360px] space-y-4 self-stretch`}>
                <div>
                  <div className="eyebrow">当前聚焦</div>
                  <h2 className="mt-2">{activeDisplayCode || '等待选择标的'}</h2>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">{workspaceSummary}</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                    <div className="metric-label">当前任务</div>
                    <div className="mt-2 text-base font-semibold text-text-primary">{activeTaskLabel}</div>
                  </div>
                  <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                    <div className="metric-label">观察周期</div>
                    <div className="mt-2 text-base font-semibold text-text-primary">{activePeriodLabel}</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="metric-tile px-4 py-4">
                <div className="metric-label">当前标的</div>
                <div className="mt-2 text-lg font-semibold text-text-primary">{activeDisplayCode || '未选择'}</div>
              </div>
              <div className="metric-tile px-4 py-4">
                <div className="metric-label">实时价格</div>
                <div className={`mt-2 text-lg font-semibold ${activeChangeTone}`}>
                  {fmtNum(activeQuote?.price as number | null, 2)}
                </div>
              </div>
              <div className="metric-tile px-4 py-4">
                <div className="metric-label">涨跌幅</div>
                <div className={`mt-2 text-lg font-semibold ${activeChangeTone}`}>
                  {fmtPct(activeQuote?.changePercent as number | null)}
                </div>
              </div>
              <div className="metric-tile px-4 py-4">
                <div className="metric-label">数据刷新</div>
                <div className="mt-2 text-sm font-medium text-text-primary">{freshnessLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">抓取 {formatStableDateTime(freshness)}</div>
              </div>
            </div>

            {from || task ? (
              <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                来源：{from ?? '-'} ｜ 任务：{task ?? '-'}
              </div>
            ) : null}
          </div>
        </section>

        <div className="grid gap-4">
          <section className="page-hero p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="eyebrow">盘中提示</div>
                <h2 className="mt-2">观察节奏</h2>
              </div>
              <Badge variant="info">{activePeriodLabel}</Badge>
            </div>
            <div className="mt-4 grid gap-3">
              {heroNotes.map((note) => (
                <div key={note} className={`${NOTE_CARD_CLS} px-4 py-3 leading-6`}>
                  {note}
                </div>
              ))}
            </div>
          </section>

          <section className={`${PANEL_CLS} rounded-[32px]`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="eyebrow">快捷跳转</div>
                <h2 className="mt-2">继续下一步</h2>
              </div>
              <Badge variant="neutral">联动页面</Badge>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              {quickJumpLinks.map((link) => (
                <Link key={link.href} href={link.href} className={sidebarActionCardCls}>
                  <div className="text-sm font-medium text-text-primary">{link.label}</div>
                  <div className="mt-1 text-xs text-text-secondary">把当前观察上下文带到下一页继续分析。</div>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </section>

      <SectionCard className="mt-0">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_320px]">
          <div className="grid gap-4">
            <div className={`${PANEL_CLS} rounded-[30px]`}>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="eyebrow">查询与预设</div>
                    <h2 className="mt-2">先完成输入，再进入主图工作区</h2>
                    <p className="mt-2 text-sm leading-6 text-text-secondary">
                      用统一的输入和预设切换路径，减少盘中重复填写与多次切 tab 的动作。
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {MARKET_STARTER_CODES.map((item) => (
                      <button
                        key={`starter-inline-${item.code}`}
                        type="button"
                        onClick={() => {
                          setCode(item.code);
                          setSubmittedCode(item.code);
                          setSubmittedPeriod(period);
                        }}
                        className={`${CHIP_BUTTON_CLS} ${submittedCode === item.code ? 'border-primary/28 bg-primary/10 text-primary shadow-[0_16px_30px_-24px_rgba(11,107,203,0.46)]' : ''}`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                <form onSubmit={onSubmit} className="grid gap-3 xl:grid-cols-[minmax(0,220px)_140px_minmax(0,1fr)]">
                  <label className="flex flex-col gap-2">
                    <span className="metric-label">股票代码</span>
                    <div className="flex flex-col gap-1">
                      <input
                        id="market-code"
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        maxLength={6}
                        placeholder="输入股票代码"
                        aria-label="股票代码"
                        aria-invalid={codeError ? true : undefined}
                        className={`w-full ${compactInputCls}`}
                      />
                      {codeError ? <span className="px-1 text-xs text-error">{codeError}</span> : null}
                    </div>
                  </label>

                  <label className="flex flex-col gap-2">
                    <span className="metric-label">K 线周期</span>
                    <select
                      value={period}
                      onChange={(e) => setPeriod(e.target.value as Period)}
                      aria-label="K线周期"
                      className={`w-full ${compactSelectCls}`}
                    >
                      <option value="daily">日线</option>
                      <option value="weekly">周线</option>
                      <option value="monthly">月线</option>
                    </select>
                  </label>

                  <div className="flex flex-col gap-2">
                    <span className="metric-label">执行动作</span>
                    <div className="flex flex-wrap gap-2">
                      <button type="submit" disabled={showPrimaryLoading} className={primaryActionCls}>
                        {showPrimaryLoading ? '加载中' : '查询主行情'}
                      </button>
                      <button type="button" onClick={saveCurrentView} className={secondaryActionCls}>
                        保存视图
                      </button>
                    </div>
                  </div>
                </form>

                <div className="grid gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="metric-label">视图预设</span>
                    {MARKET_VIEW_PRESETS.map((preset) => (
                      <button
                        key={preset.key}
                        type="button"
                        onClick={() => {
                          applyPreset(preset.apply());
                          toast(`已切换到${preset.label}`, 'info');
                        }}
                        className={CHIP_BUTTON_CLS}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className={`${PANEL_CLS} rounded-[30px]`}>
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div className="overflow-x-auto">
                  <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />
                </div>
                <div className="flex flex-wrap gap-2">
                  {cacheStatusItems.map((item) => (
                    <div key={item.label} className={`${NOTE_CARD_CLS} px-3 py-2`}>
                      <span className="metric-label">{item.label}</span>
                      <div className="mt-1 text-sm font-medium text-text-primary">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className={`${PANEL_CLS} rounded-[30px]`}>
            <div>
              <div className="eyebrow">当前视图</div>
              <h2 className="mt-2">查询状态</h2>
              <p className="mt-2 text-sm leading-6 text-text-secondary">
                当前工作流已锁定 {activeDisplayName}，接下来优先看 {activePeriodLabel} 主图和右侧摘要。
              </p>
            </div>
            <div className="mt-4 grid gap-3">
              <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                <div className="metric-label">当前代码</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{activeDisplayCode || '未选择'}</div>
              </div>
              <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                <div className="metric-label">当前周期</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{activePeriodLabel}</div>
              </div>
              <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                <div className="metric-label">刷新时间</div>
                <div className="mt-2 text-sm font-medium text-text-primary">{freshnessLabel}</div>
              </div>
              <div className={`${NOTE_CARD_CLS} px-4 py-3`}>
                <div className="metric-label">建议阅读顺序</div>
                <div className="mt-2 text-sm leading-6 text-text-secondary">
                  查询条件 → 主图结构 → 即时摘要 → 下一步动作。
                </div>
              </div>
            </div>
          </div>
        </div>
      </SectionCard>

      {pageOffline || quoteErrorMessage || tabErrorMessage ? (
        <div className="grid gap-3 md:grid-cols-2">
          {pageOffline ? (
            <div className={`${NOTE_CARD_CLS} border-primary/18 px-4 py-3 text-text-secondary md:col-span-2`}>
              数据服务当前未连接，页面已切换为离线壳层展示。你仍然可以查看布局、切换预设和继续导航；等 BFF
              恢复后点击“查询主行情”即可重新拉取数据。
            </div>
          ) : null}
          {quoteErrorMessage ? (
            <div className={`${NOTE_CARD_CLS} border-danger/15 px-4 py-3 text-danger`}>
              降级提示：{quoteErrorMessage}
            </div>
          ) : null}
          {tabErrorMessage ? (
            <div className={`${NOTE_CARD_CLS} border-danger/15 px-4 py-3 text-danger`}>{tabErrorMessage}</div>
          ) : null}
        </div>
      ) : null}

      <section className="page-hero p-4 sm:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)] xl:items-start">
          <div className={`${PANEL_CLS} min-h-[560px] rounded-[30px]`}>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="eyebrow">主图工作区</div>
                <h2 className="mt-2">K 线主图 · {activePeriodLabel}</h2>
                <p className="mt-2 text-sm leading-6 text-text-secondary">{chartDescription}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="neutral">{activeTaskLabel}</Badge>
                <Badge variant={activeChange >= 0 ? 'success' : 'danger'}>
                  {activeQuote ? `${fmtPct(activeQuote.changePercent as number | null)}` : '等待行情'}
                </Badge>
              </div>
            </div>

            {candleData.length ? (
              <div className="overflow-hidden rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.56),rgba(240,246,255,0.3))] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.76)]">
                <CandlestickChart data={candleData} height={420} />
              </div>
            ) : (
              <div className="flex min-h-[380px] items-center rounded-[26px] border border-dashed border-white/75 bg-white/24 p-4">
                <EmptyState
                  variant="full"
                  className="w-full border-white/70 bg-white/44"
                  text="当前标的还没有可展示的 K 线"
                  hint="先切到示例标的确认页面正常，再决定是否换代码或切换到指数、板块视图继续看盘。"
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
                      <button
                        type="button"
                        onClick={() => applyPreset({ activeTab: 'index', indexCode: '000300' })}
                        className={secondaryActionCls}
                      >
                        切到指数盯盘
                      </button>
                    </>
                  }
                />
              </div>
            )}

            <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_clamp(240px,22vw,320px)]">
              <div className={`${NOTE_CARD_CLS} px-4 py-4`}>
                <div className="metric-label">读图提醒</div>
                <div className="mt-2 text-sm leading-6 text-text-secondary">
                  先看趋势方向和波动区间，再结合右侧摘要里的价格、涨跌幅和成交额确认当前判断是否成立。
                </div>
              </div>
              <div className={`${NOTE_CARD_CLS} px-4 py-4`}>
                <div className="metric-label">快捷联动</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {quickJumpLinks.slice(0, 3).map((link) => (
                    <Link key={`chart-${link.href}`} href={link.href} className={LINK_CHIP_CLS}>
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <aside className="grid gap-4 xl:sticky xl:top-24">
            <div className={`${PANEL_CLS} rounded-[30px]`}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">即时摘要</div>
                  <h2 className="mt-2">实时行情</h2>
                </div>
                <Badge variant="info">主任务</Badge>
              </div>
              {activeQuote ? (
                <div className="space-y-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2 rounded-[20px] border border-white/65 bg-white/42 px-4 py-3">
                    <StockLink code={String(activeQuote.code)} name={String(activeQuote.name ?? '')} />
                    <WatchlistButton code={String(activeQuote.code)} name={String(activeQuote.name ?? '')} />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
                    <div className="metric-tile px-4 py-3">
                      <div className="metric-label">现价</div>
                      <div className={`mt-2 text-2xl font-semibold ${activeChangeTone}`}>
                        {fmtNum(activeQuote.price as number | null, 2)}
                      </div>
                    </div>
                    <div className="metric-tile px-4 py-3">
                      <div className="metric-label">涨跌幅</div>
                      <div className={`mt-2 text-2xl font-semibold ${activeChangeTone}`}>
                        {fmtPct(activeQuote.changePercent as number | null)}
                      </div>
                    </div>
                    <div className="metric-tile px-4 py-3 text-text-secondary">
                      <div className="metric-label">成交额</div>
                      <div className="mt-2 text-base font-semibold text-text-primary">
                        {fmtAmount(activeQuote.amount as number | null)}
                      </div>
                    </div>
                    <div className="metric-tile px-4 py-3 text-text-secondary">
                      <div className="metric-label">成交量</div>
                      <div className="mt-2 text-base font-semibold text-text-primary">
                        {fmtAmount(activeQuote.volume as number | null)}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                    <div className="metric-tile px-3 py-2">
                      涨跌：<span className={activeChangeTone}>{fmtNum(activeQuote.change as number | null, 2)}</span>
                    </div>
                    <div className="metric-tile px-3 py-2">开盘：{fmtNum(activeQuote.open as number | null, 2)}</div>
                    <div className="metric-tile px-3 py-2">最高：{fmtNum(activeQuote.high as number | null, 2)}</div>
                    <div className="metric-tile px-3 py-2">最低：{fmtNum(activeQuote.low as number | null, 2)}</div>
                    <div className="metric-tile px-3 py-2">
                      昨收：{fmtNum(activeQuote.prevClose as number | null, 2)}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex min-h-[280px] items-center rounded-[26px] border border-dashed border-white/75 bg-white/24 p-4">
                  <EmptyState
                    variant="full"
                    className="w-full border-white/70 bg-white/44"
                    text="当前没有可展示的行情摘要"
                    hint="首次进入建议直接点示例标的；如果你想先看整体环境，也可以切到板块或涨停复盘视图。"
                    action={
                      <>
                        <button
                          type="button"
                          onClick={() => applyPreset({ activeTab: 'blocks' })}
                          className={primaryActionCls}
                        >
                          去看板块轮动
                        </button>
                        <button
                          type="button"
                          onClick={() => applyPreset({ activeTab: 'limitup' })}
                          className={secondaryActionCls}
                        >
                          去看涨停复盘
                        </button>
                      </>
                    }
                  />
                </div>
              )}
            </div>

            <div className={`${PANEL_CLS} rounded-[30px]`}>
              <div className="mb-4">
                <div className="eyebrow">执行动作</div>
                <h2 className="mt-2">下一步</h2>
              </div>
              <div className="grid gap-2">
                <button
                  type="button"
                  onClick={() => applyPreset({ activeTab: 'main' })}
                  className={sidebarActionCardCls}
                >
                  <div className="text-sm font-medium text-text-primary">回基础行情</div>
                  <div className="mt-1 text-xs text-text-secondary">回到价格、K 线和实时摘要主视图。</div>
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset({ activeTab: 'blocks' })}
                  className={sidebarActionCardCls}
                >
                  <div className="text-sm font-medium text-text-primary">看板块轮动</div>
                  <div className="mt-1 text-xs text-text-secondary">先看强弱板块，再决定是否切回个股。</div>
                </button>
                <Link
                  href={
                    activeDisplayCode
                      ? `/paper-trading?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                      : '/paper-trading?from=market'
                  }
                  className={sidebarActionCardCls}
                >
                  <div className="text-sm font-medium text-text-primary">去模拟交易</div>
                  <div className="mt-1 text-xs text-text-secondary">把当前观察标的直接带入交易工作流。</div>
                </Link>
                <Link
                  href={
                    activeDisplayCode
                      ? `/research?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                      : '/research?from=market'
                  }
                  className={sidebarActionCardCls}
                >
                  <div className="text-sm font-medium text-text-primary">去研究页补充信息</div>
                  <div className="mt-1 text-xs text-text-secondary">把行情判断补上研报、公告和资讯背景。</div>
                </Link>
              </div>
            </div>

            <div className={`${PANEL_CLS} rounded-[30px]`}>
              <div className="mb-4">
                <div className="eyebrow">盘口深度</div>
                <h2 className="mt-2">五档盘口</h2>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-danger">卖盘</div>
                  {[...obView.asks].reverse().map((x, i, arr) => (
                    <div
                      key={`a${i}`}
                      className="metric-tile mb-2 flex justify-between rounded-[18px] px-3 py-2 text-danger/80"
                    >
                      <span>卖{arr.length - i}</span>
                      <span>{fmtNum(x.price, 2)}</span>
                      <span>{fmtAmount(x.volume)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-success">买盘</div>
                  {obView.bids.map((x, i) => (
                    <div
                      key={`b${i}`}
                      className="metric-tile mb-2 flex justify-between rounded-[18px] px-3 py-2 text-success/80"
                    >
                      <span>买{i + 1}</span>
                      <span>{fmtNum(x.price, 2)}</span>
                      <span>{fmtAmount(x.volume)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </section>

      {activeTab === 'limitup' ? (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={tabPending}
            onClick={() => {
              if (effectiveLimitUpPath) limitUpQ.refetch();
              else setLimitUpPath('/market/limit-up');
              if (effectiveLimitUpStatsPath) limitUpStatsQ.refetch();
              else setLimitUpStatsPath('/market/limit-up-stats');
            }}
            className={`${primaryActionCls} disabled:opacity-50`}
          >
            {tabPending ? '加载中...' : '刷新'}
          </button>
          {limitUpStatsObj ? (
            <KpiGrid cols={3}>
              <KpiCard
                title="涨停总数"
                value={(limitUpStatsObj.totalLimitUp as number) ?? (limitUpStatsObj.total as number) ?? '-'}
              />
              <KpiCard
                title="首板数量"
                value={(limitUpStatsObj.firstBoard as number) ?? (limitUpStatsObj.first_board as number) ?? '-'}
              />
              <KpiCard
                title="封板成功率"
                value={fmtPct(Number(limitUpStatsObj.successRate ?? limitUpStatsObj.success_rate ?? 0))}
              />
            </KpiGrid>
          ) : null}
          {limitUpRows.length ? (
            <DataTable
              rows={limitUpRows}
              columns={[
                {
                  key: 'code',
                  label: '代码',
                  render: (v: unknown, row: Record<string, unknown>) => (
                    <StockLink code={String(v)} name={String(row.name ?? '')} />
                  ),
                },
                { key: 'name', label: '名称' },
                {
                  key: 'price',
                  label: '现价',
                  align: 'right' as const,
                  render: (v: unknown) => fmtNum(v as number, 2),
                },
                {
                  key: 'changePercent',
                  label: '涨幅',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
                { key: 'continuousDays', label: '连板', align: 'right' as const },
                { key: 'industry', label: '行业' },
                {
                  key: '_watch',
                  label: '',
                  width: 40,
                  render: (_: unknown, row: Record<string, unknown>) => (
                    <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
                  ),
                },
              ]}
              maxHeight={400}
              onExport={() => exportCSV(limitUpRows, 'limit-up')}
            />
          ) : !tabPending && !limitUpQ.error ? (
            <EmptyState
              text="当前还没有涨停榜单"
              hint="如果你在做日内复盘，可以先刷新榜单；如果更想看整体强弱，先去板块轮动通常更直接。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => applyPreset({ activeTab: 'blocks' })}
                    className={primaryActionCls}
                  >
                    看板块轮动
                  </button>
                  <Link href="/research" className={secondaryLinkCls}>
                    去研究页找催化
                  </Link>
                </>
              }
            />
          ) : null}
        </SectionCard>
      ) : null}
      {activeTab === 'blocks' ? (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={tabPending}
            onClick={() => {
              if (effectiveBlocksPath) blocksQ.refetch();
              else setBlocksPath('/market/blocks?blockType=industry');
            }}
            className={`${primaryActionCls} disabled:opacity-50`}
          >
            {tabPending ? '加载中...' : '加载行业板块'}
          </button>
          {blocksRows.length ? (
            <DataTable
              rows={blocksRows}
              columns={[
                { key: 'code', label: '板块代码' },
                { key: 'name', label: '板块名称' },
                { key: 'stockCount', label: '股票数', align: 'right' as const },
                {
                  key: 'avgChange',
                  label: '平均涨幅',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
                { key: 'leaderName', label: '领涨股' },
              ]}
              maxHeight={400}
              onExport={() => exportCSV(blocksRows, 'blocks')}
              searchable
              onRowClick={(row) => {
                const c = String(row.code ?? '');
                if (c) {
                  setBlockCode(c);
                  const p = `/market/block-stocks?blockCode=${encodeURIComponent(c)}`;
                  if (p === effectiveBlockStocksPath) blockStocksQ.refetch();
                  else setBlockStocksPath(p);
                }
              }}
            />
          ) : !tabPending && !blocksQ.error ? (
            <EmptyState
              text="先加载行业板块再看轮动"
              hint="板块页更适合作为行情入口：先找到强弱板块，再点进成分股或回个股页继续看。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (effectiveBlocksPath) blocksQ.refetch();
                      else setBlocksPath('/market/blocks?blockType=industry');
                    }}
                    className={primaryActionCls}
                  >
                    加载行业板块
                  </button>
                  <Link href="/fund-flow" className={secondaryLinkCls}>
                    去看资金流向
                  </Link>
                </>
              }
            />
          ) : null}
          <div className="flex gap-2 items-center mt-2">
            <input
              value={blockCode}
              onChange={(e) => setBlockCode(e.target.value)}
              placeholder="板块代码"
              aria-label="板块代码"
              className={`w-40 ${compactInputCls}`}
            />
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                const p = `/market/block-stocks?blockCode=${encodeURIComponent(blockCode.trim())}`;
                if (p === effectiveBlockStocksPath) blockStocksQ.refetch();
                else setBlockStocksPath(p);
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              查看成分股
            </button>
          </div>
          {blockStocksRows.length ? (
            <DataTable
              rows={blockStocksRows}
              columns={[
                {
                  key: 'code',
                  label: '代码',
                  render: (v: unknown, row: Record<string, unknown>) => (
                    <StockLink code={String(v)} name={String(row.name ?? '')} />
                  ),
                },
                { key: 'name', label: '名称' },
                {
                  key: 'price',
                  label: '现价',
                  align: 'right' as const,
                  render: (v: unknown) => fmtNum(v as number, 2),
                },
                {
                  key: 'changePercent',
                  label: '涨跌幅',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
              ]}
              maxHeight={400}
              onExport={() => exportCSV(blockStocksRows, 'block-stocks')}
            />
          ) : null}
        </SectionCard>
      ) : null}
      {activeTab === 'trade' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={6}
              placeholder="股票代码"
              aria-label="股票代码"
              className={`w-35 ${compactInputCls}`}
            />
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                if (!validate()) return;
                const p = `/market/trade-details?code=${encodeURIComponent(code.trim())}`;
                if (p === tradePath) tradeQ.refetch();
                else setTradePath(p);
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              {tabPending ? '加载中...' : '查询逐笔明细'}
            </button>
          </div>
          {tradeRows.length ? (
            <DataTable
              rows={tradeRows}
              columns={tradeColumns}
              maxHeight={400}
              onExport={() => exportCSV(tradeRows, 'trade-details')}
            />
          ) : !tabPending && !tradeQ.error ? (
            <EmptyState
              text="输入股票代码后查看逐笔成交"
              hint="逐笔明细更适合在你已经锁定标的后使用；如果还没锁定，先去搜索或看基础行情会更快。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => applyPreset({ activeTab: 'search' })}
                    className={primaryActionCls}
                  >
                    先去搜索标的
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCode(DEFAULT_MARKET_CODE);
                      setSubmittedCode(DEFAULT_MARKET_CODE);
                    }}
                    className={secondaryActionCls}
                  >
                    加载示例标的
                  </button>
                </>
              }
            />
          ) : null}
        </SectionCard>
      ) : null}

      {activeTab === 'index' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input
              value={indexCode}
              onChange={(e) => setIndexCode(e.target.value)}
              placeholder="指数代码 如 000001"
              aria-label="指数代码"
              className={`w-40 ${compactInputCls}`}
            />
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                const p = `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim())}`;
                if (p === effectiveIndexPath) indexQuoteQ.refetch();
                else setIndexPath(p);
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              {tabPending ? '加载中...' : '查询指数行情'}
            </button>
          </div>
          {indexObj ? (
            <KpiGrid cols={4}>
              <KpiCard title="指数名称" value={String(indexObj.name ?? indexObj.index_name ?? '-')} />
              <KpiCard title="最新点位" value={fmtNum(indexObj.price ?? indexObj.close ?? null)} />
              <KpiCard
                title="涨跌幅"
                value={fmtPct(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? null)}
                change={Number(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? 0)}
              />
              <KpiCard title="成交额" value={fmtAmount(indexObj.amount ?? indexObj.turnover ?? null)} />
              <KpiCard title="最高" value={fmtNum(indexObj.high ?? null)} />
              <KpiCard title="最低" value={fmtNum(indexObj.low ?? null)} />
              <KpiCard title="开盘" value={fmtNum(indexObj.open ?? null)} />
              <KpiCard title="昨收" value={fmtNum(indexObj.prevClose ?? indexObj.prev_close ?? null)} />
            </KpiGrid>
          ) : !tabPending && !indexQuoteQ.error ? (
            <EmptyState
              text="输入指数代码后查看指数行情"
              hint="如果你只是想先判断大盘环境，可直接看 000001 上证指数或 000300 沪深300。"
              action={
                <>
                  <button type="button" onClick={() => setIndexCode('000001')} className={primaryActionCls}>
                    示例：000001
                  </button>
                  <button type="button" onClick={() => setIndexCode('000300')} className={secondaryActionCls}>
                    示例：000300
                  </button>
                </>
              }
            />
          ) : null}
        </SectionCard>
      ) : null}

      {activeTab === 'minute' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={6}
              placeholder="股票代码"
              aria-label="股票代码"
              className={`w-35 ${compactInputCls}`}
            />
            <select
              value={minutePeriod}
              onChange={(e) => setMinutePeriod(e.target.value)}
              aria-label="分时周期"
              className={compactSelectCls}
            >
              <option value="1m">1分钟</option>
              <option value="5m">5分钟</option>
              <option value="15m">15分钟</option>
              <option value="30m">30分钟</option>
              <option value="60m">60分钟</option>
            </select>
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                if (!validate()) return;
                const p = `/market/minute-kline?code=${encodeURIComponent(code.trim())}&period=${minutePeriod}`;
                if (p === effectiveMinutePath) minuteKlineQ.refetch();
                else setMinutePath(p);
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              {tabPending ? '加载中...' : '查询分时'}
            </button>
          </div>
          {minuteCandleData.length ? (
            <CandlestickChart data={minuteCandleData} height={360} />
          ) : !tabPending && !minuteKlineQ.error ? (
            <EmptyState
              text="选择周期后加载分钟级 K 线"
              hint="分时更适合盘中确认节奏；如果只是看方向，先用基础行情日线会更稳。"
              action={
                <>
                  <button type="button" onClick={() => setMinutePeriod('5m')} className={primaryActionCls}>
                    用 5 分钟周期
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset({ activeTab: 'main' })}
                    className={secondaryActionCls}
                  >
                    回基础行情
                  </button>
                </>
              }
            />
          ) : null}
        </SectionCard>
      ) : null}

      {activeTab === 'search' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              placeholder="搜索股票"
              aria-label="搜索关键词"
              className={`w-50 ${compactInputCls}`}
            />
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                const p = `/market/search?keyword=${encodeURIComponent(searchKeyword.trim())}`;
                if (p === searchPath) searchQ.refetch();
                else setSearchPath(p);
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              {tabPending ? '搜索中...' : '搜索'}
            </button>
          </div>
          {searchRows.length ? (
            <DataTable
              rows={searchRows}
              columns={[
                {
                  key: 'code',
                  label: '代码',
                  render: (v: unknown, row: Record<string, unknown>) => (
                    <StockLink code={String(v)} name={String(row.name ?? '')} />
                  ),
                },
                { key: 'name', label: '名称' },
                { key: 'industry', label: '行业' },
                {
                  key: '_watch',
                  label: '',
                  width: 40,
                  sortable: false,
                  render: (_: unknown, row: Record<string, unknown>) => (
                    <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
                  ),
                },
              ]}
              maxHeight={300}
              onExport={() => exportCSV(searchRows, 'search-results')}
              searchable
            />
          ) : !tabPending && !searchQ.error ? (
            <EmptyState
              text="先输入名称或代码开始搜索"
              hint="如果你还不确定代码，可以搜名称、行业词，或者直接加载全市场列表后再筛。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (stockListPath) stockListQ.refetch();
                      else setStockListPath('/market/stock-list');
                    }}
                    className={primaryActionCls}
                  >
                    加载全市场列表
                  </button>
                  <Link href="/watchlist" className={secondaryLinkCls}>
                    去自选股挑选
                  </Link>
                </>
              }
            />
          ) : null}
          <div className="flex gap-2 items-center mt-3">
            <button
              type="button"
              disabled={tabPending}
              onClick={() => {
                if (stockListPath) stockListQ.refetch();
                else setStockListPath('/market/stock-list');
              }}
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              加载全部股票列表
            </button>
          </div>
          {stockListRows.length ? (
            <DataTable
              rows={stockListRows}
              columns={[
                {
                  key: 'code',
                  label: '代码',
                  render: (v: unknown, row: Record<string, unknown>) => (
                    <StockLink code={String(v)} name={String(row.name ?? '')} />
                  ),
                },
                { key: 'name', label: '名称' },
                {
                  key: '_watch',
                  label: '',
                  width: 40,
                  sortable: false,
                  render: (_: unknown, row: Record<string, unknown>) => (
                    <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
                  ),
                },
              ]}
              maxHeight={300}
              onExport={() => exportCSV(stockListRows, 'stock-list')}
              searchable
              pageSize={50}
            />
          ) : null}
          <div className="flex gap-2 items-center mt-3">
            <input
              value={batchCodes}
              onChange={(e) => setBatchCodes(e.target.value)}
              placeholder="批量代码，逗号分隔"
              aria-label="批量股票代码"
              className={`w-75 ${compactInputCls}`}
            />
            <button
              type="button"
              disabled={tabPending}
              onClick={() =>
                batchQuotes.trigger(
                  '/market/batch-quotes',
                  { method: 'POST' },
                  { codes: batchCodes.split(',').map((s) => s.trim()) },
                )
              }
              className={`${primaryActionCls} disabled:opacity-50`}
            >
              批量行情
            </button>
          </div>
          {batchRows.length ? (
            <DataTable
              rows={batchRows}
              columns={[
                {
                  key: 'code',
                  label: '代码',
                  render: (v: unknown, row: Record<string, unknown>) => (
                    <StockLink code={String(v)} name={String(row.name ?? '')} />
                  ),
                },
                { key: 'name', label: '名称' },
                {
                  key: 'price',
                  label: '现价',
                  align: 'right' as const,
                  render: (v: unknown) => fmtNum(v as number, 2),
                },
                {
                  key: 'changePercent',
                  label: '涨跌幅',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
                {
                  key: 'volume',
                  label: '成交量',
                  align: 'right' as const,
                  render: (v: unknown) => fmtAmount(v as number),
                },
                {
                  key: 'amount',
                  label: '成交额',
                  align: 'right' as const,
                  render: (v: unknown) => fmtAmount(v as number),
                },
                { key: 'high', label: '最高', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                { key: 'low', label: '最低', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                {
                  key: '_watch',
                  label: '',
                  width: 40,
                  sortable: false,
                  render: (_: unknown, row: Record<string, unknown>) => (
                    <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
                  ),
                },
              ]}
              maxHeight={300}
              onExport={() => exportCSV(batchRows, 'batch-quotes')}
            />
          ) : null}
        </SectionCard>
      ) : null}
    </PageContainer>
  );
}
