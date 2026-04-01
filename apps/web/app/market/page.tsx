'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import MarketBlocksTab from '@/app/market/components/market-blocks-tab';
import MarketHeroSection from '@/app/market/components/market-hero-section';
import MarketIndexTab from '@/app/market/components/market-index-tab';
import MarketLimitUpTab from '@/app/market/components/market-limit-up-tab';
import MarketMainWorkspace from '@/app/market/components/market-main-workspace';
import MarketMinuteTab from '@/app/market/components/market-minute-tab';
import MarketQueryShell from '@/app/market/components/market-query-shell';
import MarketSearchTab from '@/app/market/components/market-search-tab';
import MarketTradeTab from '@/app/market/components/market-trade-tab';
import { PageContainer } from '@/components/ui';
import {
  DEFAULT_MARKET_CODE,
  MARKET_VIEW_STORAGE_KEY,
  TABS,
  formatStableDateTime,
  isMarketTab,
  isPeriod,
  resolveInitialMarketViewState,
  type InitialMarketViewState,
  type MarketTab,
  type Period,
  type SavedMarketView,
} from '@/app/market/lib/market-view';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useHydrated } from '@/hooks/use-hydrated';
import { useStockCode } from '@/hooks/use-stock-code';
import { useSearchParams } from 'next/navigation';
import { cacheText } from '@/lib/api';
import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { useToast } from '@/components/ui/toast';
import type { CacheMeta, NormalizedQuote, NormalizedKlinePoint, NormalizedOrderBook } from '@aiask/shared-types';

type QuoteData = { quote?: NormalizedQuote; tool?: string; meta?: CacheMeta };
type KlineData = { kline?: NormalizedKlinePoint[]; tool?: string; meta?: CacheMeta };
type ObData = { orderBook?: NormalizedOrderBook; tool?: string; meta?: CacheMeta };
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

  function refreshLimitUpTab() {
    if (effectiveLimitUpPath) limitUpQ.refetch();
    else setLimitUpPath('/market/limit-up');
    if (effectiveLimitUpStatsPath) limitUpStatsQ.refetch();
    else setLimitUpStatsPath('/market/limit-up-stats');
  }

  function loadBlocksTab() {
    if (effectiveBlocksPath) blocksQ.refetch();
    else setBlocksPath('/market/blocks?blockType=industry');
  }

  function loadBlockStocks(nextBlockCode = blockCode) {
    const path = `/market/block-stocks?blockCode=${encodeURIComponent(nextBlockCode.trim())}`;
    if (path === effectiveBlockStocksPath) blockStocksQ.refetch();
    else setBlockStocksPath(path);
  }

  function selectBlock(nextBlockCode: string) {
    setBlockCode(nextBlockCode);
    loadBlockStocks(nextBlockCode);
  }

  function queryTradeTab() {
    if (!validate()) return;
    const path = `/market/trade-details?code=${encodeURIComponent(code.trim())}`;
    if (path === tradePath) tradeQ.refetch();
    else setTradePath(path);
  }

  function queryIndexTab() {
    const path = `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim())}`;
    if (path === effectiveIndexPath) indexQuoteQ.refetch();
    else setIndexPath(path);
  }

  function queryMinuteTab() {
    if (!validate()) return;
    const path = `/market/minute-kline?code=${encodeURIComponent(code.trim())}&period=${minutePeriod}`;
    if (path === effectiveMinutePath) minuteKlineQ.refetch();
    else setMinutePath(path);
  }

  function searchStocks() {
    const path = `/market/search?keyword=${encodeURIComponent(searchKeyword.trim())}`;
    if (path === searchPath) searchQ.refetch();
    else setSearchPath(path);
  }

  function loadStockList() {
    if (stockListPath) stockListQ.refetch();
    else setStockListPath('/market/stock-list');
  }

  function runBatchQuotes() {
    batchQuotes.trigger(
      '/market/batch-quotes',
      { method: 'POST' },
      { codes: batchCodes.split(',').map((item) => item.trim()) },
    );
  }

  const useStarterCode = useCallback(
    (nextCode: string) => {
      setCode(nextCode);
      setSubmittedCode(nextCode);
      setSubmittedPeriod(period);
    },
    [period, setCode],
  );

  const applyMarketPreset = useCallback(
    (preset: Partial<SavedMarketView>, label?: string) => {
      applyPreset(preset);
      if (label) {
        toast(`已切换到${label}`, 'info');
      }
    },
    [applyPreset, toast],
  );

  return (
    <PageContainer className="space-y-5">
      <MarketHeroSection
        activeTaskLabel={activeTaskLabel}
        activeDisplayName={activeDisplayName}
        activeDisplayCode={activeDisplayCode}
        activePeriodLabel={activePeriodLabel}
        workspaceSummary={workspaceSummary}
        activeQuote={activeQuote}
        activeChangeTone={activeChangeTone}
        freshnessLabel={freshnessLabel}
        freshness={freshness}
        from={from}
        task={task}
        heroNotes={heroNotes}
        quickJumpLinks={quickJumpLinks}
      />

      <MarketQueryShell
        code={code}
        onCodeChange={setCode}
        codeError={codeError}
        period={period}
        onPeriodChange={setPeriod}
        onSubmit={onSubmit}
        showPrimaryLoading={showPrimaryLoading}
        onSaveCurrentView={saveCurrentView}
        submittedCode={submittedCode}
        onUseStarterCode={useStarterCode}
        onApplyPreset={applyMarketPreset}
        activeTab={activeTab}
        onActiveTabChange={setActiveTab}
        cacheStatusItems={cacheStatusItems}
        activeDisplayName={activeDisplayName}
        activeDisplayCode={activeDisplayCode}
        activePeriodLabel={activePeriodLabel}
        freshnessLabel={freshnessLabel}
      />

      <MarketMainWorkspace
        pageOffline={pageOffline}
        quoteErrorMessage={quoteErrorMessage}
        tabErrorMessage={tabErrorMessage}
        activePeriodLabel={activePeriodLabel}
        chartDescription={chartDescription}
        activeTaskLabel={activeTaskLabel}
        activeChange={activeChange}
        activeChangeTone={activeChangeTone}
        activeQuote={activeQuote}
        candleData={candleData}
        activeDisplayCode={activeDisplayCode}
        quickJumpLinks={quickJumpLinks}
        onUseStarterCode={useStarterCode}
        onApplyPreset={applyPreset}
        obView={obView}
      />

      {activeTab === 'limitup' ? (
        <MarketLimitUpTab
          tabPending={tabPending}
          limitUpRows={limitUpRows}
          limitUpStatsObj={limitUpStatsObj}
          error={limitUpQ.error}
          onRefresh={refreshLimitUpTab}
          onShowBlocks={() => applyPreset({ activeTab: 'blocks' })}
        />
      ) : null}
      {activeTab === 'blocks' ? (
        <MarketBlocksTab
          tabPending={tabPending}
          blocksRows={blocksRows}
          blockStocksRows={blockStocksRows}
          blocksError={blocksQ.error}
          blockCode={blockCode}
          onBlockCodeChange={setBlockCode}
          onLoadBlocks={loadBlocksTab}
          onLoadBlockStocks={() => loadBlockStocks()}
          onSelectBlock={selectBlock}
        />
      ) : null}
      {activeTab === 'trade' ? (
        <MarketTradeTab
          code={code}
          onCodeChange={setCode}
          tabPending={tabPending}
          tradeRows={tradeRows}
          error={tradeQ.error}
          onQueryTrade={queryTradeTab}
          onShowSearch={() => applyPreset({ activeTab: 'search' })}
          onLoadSample={() => {
            setCode(DEFAULT_MARKET_CODE);
            setSubmittedCode(DEFAULT_MARKET_CODE);
          }}
        />
      ) : null}

      {activeTab === 'index' ? (
        <MarketIndexTab
          indexCode={indexCode}
          onIndexCodeChange={setIndexCode}
          tabPending={tabPending}
          indexObj={indexObj}
          error={indexQuoteQ.error}
          onQueryIndex={queryIndexTab}
          onUseExampleCode={setIndexCode}
        />
      ) : null}

      {activeTab === 'minute' ? (
        <MarketMinuteTab
          code={code}
          onCodeChange={setCode}
          minutePeriod={minutePeriod}
          onMinutePeriodChange={setMinutePeriod}
          tabPending={tabPending}
          minuteRows={minuteRows}
          error={minuteKlineQ.error}
          onQueryMinute={queryMinuteTab}
          onShowMain={() => applyPreset({ activeTab: 'main' })}
        />
      ) : null}

      {activeTab === 'search' ? (
        <MarketSearchTab
          searchKeyword={searchKeyword}
          onSearchKeywordChange={setSearchKeyword}
          tabPending={tabPending}
          searchRows={searchRows}
          searchError={searchQ.error}
          onSearch={searchStocks}
          onLoadStockList={loadStockList}
          stockListRows={stockListRows}
          batchCodes={batchCodes}
          onBatchCodesChange={setBatchCodes}
          onBatchQuotes={runBatchQuotes}
          batchRows={batchRows}
        />
      ) : null}
    </PageContainer>
  );
}
