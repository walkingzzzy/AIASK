'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Badge, PageContainer } from '@/components/ui';
import { ErrorState } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { tradingInterval } from '@/lib/trading-hours';
import { unwrapToolPayload } from '@/lib/tool-result';
import { useQuoteSubscription, type QuoteData as LiveQuoteData } from '@/lib/ws';
import StockActionCard from '@/app/stock/components/stock-action-card';
import StockDetailTabs from '@/app/stock/components/stock-detail-tabs';
import StockHero from '@/app/stock/components/stock-hero';
import StockQueryShell from '@/app/stock/components/stock-query-shell';
import StockSnapshot from '@/app/stock/components/stock-snapshot';
import {
  STOCK_DETAIL_SKIP_KEYS,
  STOCK_INFO_TABS,
  type Period,
  type StockInfoTab,
} from '@/app/stock/lib/stock-detail-view';
import type {
  MarketKlineResponseDto,
  MarketQuoteResponseDto,
  NormalizedOrderBook,
  NormalizedQuote,
  StockDetailActionCard,
  StockFundFlowEntry,
  StockFundamentalOverview,
  StockNewsItem,
  StockValuationOverview,
} from '@aiask/shared-types';

type QuoteData = MarketQuoteResponseDto;
type KlineData = MarketKlineResponseDto;

export default function StockPage() {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const mobileOnlyDetected = useMobile(RESPONSIVE_BREAKPOINTS.mobile);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const mobileOnly = hydrated ? mobileOnlyDetected : true;
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode('600519');
  const [period, setPeriod] = useState<Period>('daily');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>('daily');
  const [infoTab, setInfoTab] = useState<StockInfoTab>('chart');
  const [wsQuotes, setWsQuotes] = useState<Record<string, Partial<NormalizedQuote>>>({});

  const activeCode = submittedCode ?? resolvedCode ?? null;
  const liveQuoteCode = activeCode;

  const quoteQ = useApiQuery<QuoteData>(activeCode ? `/market/quote?code=${encodeURIComponent(activeCode)}` : null, {
    refetchInterval: tradingInterval(30_000),
    parse: (raw) => {
      const obj = ensureRecord(raw, '个股行情');
      if ('quote' in obj && obj.quote != null && typeof obj.quote !== 'object') {
        throw new Error('个股行情.quote 字段类型异常');
      }
      return obj as QuoteData;
    },
  });
  const klineQ = useApiQuery<KlineData>(
    activeCode ? `/market/kline?code=${encodeURIComponent(activeCode)}&period=${submittedPeriod}&limit=250` : null,
    {
      parse: (raw) => {
        const obj = ensureRecord(raw, 'K线');
        if ('kline' in obj && obj.kline != null && !Array.isArray(obj.kline)) {
          throw new Error('K线.kline 字段类型异常');
        }
        return obj as KlineData;
      },
    },
  );
  const techApi = useApiMutation<Record<string, unknown>>({
    parse: (raw) => ensureRecord(raw, '技术指标'),
  });
  const patternsApi = useApiMutation<Record<string, unknown>>({
    parse: (raw) => {
      const obj = ensureRecord(raw, '形态识别');
      if ('patterns' in obj && obj.patterns != null && !Array.isArray(obj.patterns)) {
        throw new Error('形态识别.patterns 字段类型异常');
      }
      return obj;
    },
  });
  const sentimentQ = useApiQuery<Record<string, unknown>>(
    activeCode ? `/sentiment/stock?code=${encodeURIComponent(activeCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '个股情绪') },
  );
  const fundFlowQ = useApiQuery<unknown>(
    activeCode ? `/fund-flow/stock?code=${encodeURIComponent(activeCode)}` : null,
    { parse: (raw) => ensureRecordOrArray(raw, '个股资金流') },
  );
  const fundamentalQ = useApiQuery<unknown>(
    activeCode ? `/fundamental/overview?code=${encodeURIComponent(activeCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '个股基本面') },
  );
  const newsQ = useApiQuery<unknown>(
    activeCode ? `/research/stock-news?code=${encodeURIComponent(activeCode)}` : null,
    { parse: (raw) => ensureRecordOrArray(raw, '个股资讯') },
  );
  const orderBookQ = useApiQuery<unknown>(
    activeCode ? `/market/order-book?code=${encodeURIComponent(activeCode)}` : null,
    { refetchInterval: tradingInterval(10_000), parse: (raw) => ensureRecord(raw, '个股盘口') },
  );
  const valuationQ = useApiQuery<unknown>(
    activeCode ? `/valuation/overview?code=${encodeURIComponent(activeCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '估值概览') },
  );

  const handleWsQuote = useCallback((data: LiveQuoteData) => {
    const liveCode = String(data.code ?? '').trim();
    if (!liveCode) return;
    setWsQuotes((prev) => ({ ...prev, [liveCode]: data as Partial<NormalizedQuote> }));
  }, []);

  useQuoteSubscription({
    codes: liveQuoteCode ? [liveQuoteCode] : [],
    type: 'stock',
    enabled: Boolean(liveQuoteCode),
    onUpdate: handleWsQuote,
  });

  function doFetch(nextCode: string) {
    techApi.trigger('/technical/indicators', { method: 'POST' }, { code: nextCode, indicators: ['RSI', 'MACD', 'KDJ'] });
    patternsApi.trigger('/technical/patterns', { method: 'POST' }, { code: nextCode });
  }

  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      doFetch(resolvedCode);
    }
  }, [resolvedCode]); // eslint-disable-line react-hooks/exhaustive-deps

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextCode = String(form.get('stockCode') ?? code).trim();
    const nextPeriod = String(form.get('period') ?? period) as Period;
    setCode(nextCode);
    if (!validate(nextCode)) return;

    if (nextCode === activeCode && nextPeriod === submittedPeriod) {
      quoteQ.refetch();
      klineQ.refetch();
      sentimentQ.refetch();
      fundFlowQ.refetch();
      fundamentalQ.refetch();
      newsQ.refetch();
    } else {
      setSubmittedCode(nextCode);
      setSubmittedPeriod(nextPeriod);
    }
    doFetch(nextCode);
  }

  const candleData = useMemo(
    () =>
      (klineQ.data?.kline ?? []).map((item) => ({
        date: item.date.slice(0, 10),
        open: item.open,
        close: item.close,
        low: item.low,
        high: item.high,
        volume: item.volume,
      })),
    [klineQ.data],
  );
  const wsQuote = liveQuoteCode ? (wsQuotes[liveQuoteCode] ?? null) : null;
  const quote = useMemo<NormalizedQuote | undefined>(() => {
    const base = quoteQ.data?.quote;
    if (!base && !wsQuote) return undefined;
    return {
      ...(base ?? ({} as NormalizedQuote)),
      ...(wsQuote ?? {}),
      code: String(wsQuote?.code ?? base?.code ?? liveQuoteCode ?? ''),
      name: String(wsQuote?.name ?? base?.name ?? ''),
    } as NormalizedQuote;
  }, [liveQuoteCode, quoteQ.data?.quote, wsQuote]);

  const hasRequested = Boolean(activeCode);
  const hasQuoteData = Boolean(quote);
  const hasKlineData = candleData.length > 0;
  const loading =
    hasRequested &&
    ((!hasQuoteData && (quoteQ.isPending || quoteQ.isFetching)) ||
      (!hasQuoteData && !hasKlineData && (klineQ.isPending || klineQ.isFetching)));
  const error =
    quoteQ.error || klineQ.error || sentimentQ.error || fundFlowQ.error || fundamentalQ.error || newsQ.error;

  const contextCode = useMemo(() => String(quote?.code ?? activeCode ?? '').trim(), [activeCode, quote?.code]);
  const sentimentPayload = useMemo(() => unwrapToolPayload(sentimentQ.data), [sentimentQ.data]);
  const sentimentScore = Number(sentimentPayload.score ?? sentimentPayload.sentiment_score ?? 0);

  const fundFlowItems = useMemo(() => extractArray(fundFlowQ.data, 'flows') as StockFundFlowEntry[], [fundFlowQ.data]);
  const fundFlowChart = useMemo(
    () =>
      fundFlowItems.slice(-20).map((item) => ({
        label: String(item.date ?? '').slice(5),
        value: Number(item.netInflow ?? item.net_inflow ?? 0),
      })),
    [fundFlowItems],
  );
  const fundamentalObj = useMemo(
    () => extractObject(fundamentalQ.data) as StockFundamentalOverview | null,
    [fundamentalQ.data],
  );
  const newsItems = useMemo(() => extractArray(newsQ.data, 'items', 'news', 'data') as StockNewsItem[], [newsQ.data]);
  const valuationMetrics = useMemo(() => {
    const root = unwrapToolPayload(valuationQ.data);
    const metricsSource = (root.metrics ?? root.metric ?? root) as Record<string, unknown>;
    return extractObject(metricsSource) as StockValuationOverview;
  }, [valuationQ.data]);
  const orderBook = useMemo<NormalizedOrderBook>(() => {
    const raw = extractObject(orderBookQ.data);
    const source = raw.orderBook ? extractObject(raw.orderBook) : raw;
    return {
      symbol: String(source.symbol ?? contextCode ?? ''),
      bids: Array.isArray(source.bids) ? (source.bids as Array<{ price: number; volume: number }>) : [],
      asks: Array.isArray(source.asks)
        ? (source.asks as Array<{ price: number; volume: number }>).slice().reverse()
        : [],
      timestamp: typeof source.timestamp === 'string' ? source.timestamp : null,
    };
  }, [contextCode, orderBookQ.data]);

  const quickLinks = useMemo(() => {
    if (!contextCode) return [];
    return [
      { label: '资金流向', href: `/fund-flow?code=${contextCode}` },
      { label: '基本面', href: `/fundamental?code=${contextCode}` },
      { label: '技术分析', href: `/technical?code=${contextCode}` },
      { label: '研报公告', href: `/research?code=${contextCode}` },
      { label: '估值分析', href: `/valuation?code=${contextCode}` },
      { label: '情绪分析', href: `/sentiment?code=${contextCode}` },
    ];
  }, [contextCode]);

  const actionCard = useMemo<StockDetailActionCard | null>(() => {
    if (!contextCode || !quote) return null;

    const changePercent = Number(quote.changePercent ?? quote.change_pct ?? 0);
    const valuationPe = Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? quote.pe ?? Number.NaN);
    const turnoverCandidate = Number(klineQ.data?.kline?.at(-1)?.turnover ?? Number.NaN);
    const turnoverRate =
      Number.isFinite(turnoverCandidate) && turnoverCandidate > 0 && turnoverCandidate <= 100 ? turnoverCandidate : null;
    const reasons = [`短线情绪分数 ${fmtNum(sentimentScore, 0)}`, `当日涨跌幅 ${fmtPct(changePercent)}`];

    let title = '行动卡: 维持观察';
    let tone: StockDetailActionCard['tone'] = 'info';
    let summary = '价格与基本面尚未形成单边信号，优先跟踪量价、情绪与估值的下一次共振。';

    if (sentimentScore >= 65 && changePercent >= 2) {
      title = '行动卡: 跟踪强势延续';
      tone = 'danger';
      summary = '价格与情绪同步走强，适合先看量能延续，再决定是否分批跟踪。';
    } else if (sentimentScore <= 35 || changePercent <= -3) {
      title = '行动卡: 先看风险释放';
      tone = 'warning';
      summary = '短线承压或情绪偏弱，先确认支撑与资金承接，再考虑下一步动作。';
    }

    if (Number.isFinite(valuationPe)) reasons.push(`PE 约 ${fmtNum(valuationPe, 2)}`);
    if (turnoverRate != null) reasons.push(`最近换手约 ${fmtNum(turnoverRate, 2)}%`);

    return {
      title,
      tone,
      summary,
      reasons,
      links: quickLinks.slice(0, 3),
    };
  }, [contextCode, klineQ.data?.kline, quickLinks, quote, sentimentScore, valuationMetrics.pe, valuationMetrics.pe_ttm]);

  usePageContext({
    pageKey: 'stock',
    title: quote ? `${quote.name} ${contextCode}` : '股票详情',
    summary: quote
      ? `${contextCode} 当前价 ${fmtNum(Number(quote.price), 2)}，涨跌幅 ${fmtPct(Number(quote.changePercent ?? quote.change_pct ?? 0))}，情绪分数 ${fmtNum(sentimentScore, 0)}。`
      : `股票详情页，当前输入 ${code || '未填写'}。`,
    stockCode: contextCode || undefined,
    tags: [
      submittedPeriod === 'daily' ? '日线' : submittedPeriod === 'weekly' ? '周线' : '月线',
      infoTab,
      quote ? `PE ${fmtNum(Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? 0), 2)}` : '未加载估值',
    ],
    suggestions: [
      contextCode ? `总结 ${contextCode} 当前最强和最弱的信号` : '选择一个股票后总结当前信号',
      '结合技术面、资金流和估值给出短中期观察重点',
      '把当前个股页整理成一个复盘清单',
    ],
    raw: {
      code: contextCode || null,
      period: submittedPeriod,
      tab: infoTab,
      hasQuote: Boolean(quote),
      sentimentScore,
      fundFlowItems: fundFlowItems.length,
      newsItems: newsItems.length,
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'stock.refresh',
        label: '刷新个股数据',
        description: '刷新行情、K 线、情绪、资金流和新闻',
        keywords: ['刷新', '行情', '个股'],
        scope: 'page' as const,
        pageKey: 'stock',
        run: async () => {
          await Promise.allSettled([
            quoteQ.refetch(),
            klineQ.refetch(),
            sentimentQ.refetch(),
            fundFlowQ.refetch(),
            fundamentalQ.refetch(),
            newsQ.refetch(),
            orderBookQ.refetch(),
            valuationQ.refetch(),
          ]);
          return { message: `已刷新 ${contextCode || code} 个股数据` };
        },
      },
      {
        id: 'stock.open-research',
        label: '切到研报公告',
        description: '打开当前股票的研报公告页',
        keywords: ['研报', '公告'],
        scope: 'page' as const,
        pageKey: 'stock',
        run: () => {
          if (!contextCode) return { message: '当前还没有有效股票代码' };
          window.location.href = `/research?code=${encodeURIComponent(contextCode)}`;
          return { message: `已打开 ${contextCode} 研报公告` };
        },
      },
      {
        id: 'stock.switch-tab',
        label: '切到 AI 诊断',
        description: '在当前个股页切换到 AI 诊断标签',
        keywords: ['AI', '诊断', 'tab'],
        scope: 'page' as const,
        pageKey: 'stock',
        run: () => {
          setInfoTab('ai');
          return { message: '已切换到 AI 诊断标签' };
        },
      },
    ],
    [code, contextCode, fundFlowQ, fundamentalQ, klineQ, newsQ, orderBookQ, quoteQ, sentimentQ, valuationQ],
  );

  usePageActions(pageActions);

  useEffect(() => {
    if (quote) document.title = `${quote.name}(${activeCode ?? ''}) | AIASK`;
    return () => {
      document.title = 'AIASK 智能股票分析';
    };
  }, [activeCode, quote]);

  const priceChangePct = Number(quote?.changePercent ?? quote?.change_pct ?? 0);
  const chgColor = priceChangePct >= 0 ? 'text-danger' : 'text-success';
  const amplitude =
    quote?.high && quote?.low && quote?.prevClose
      ? `${(((Number(quote.high) - Number(quote.low)) / Number(quote.prevClose)) * 100).toFixed(2)}%`
      : '-';
  const activeTabLabel = STOCK_INFO_TABS.find((item) => item.key === infoTab)?.label ?? 'K线图';
  const currentFocusCode = contextCode || code.trim() || '600519';
  const refreshStatus = quoteQ.isFetching ? '数据刷新中' : quote ? '已同步最新报价' : '等待首次加载';
  const refreshTimeText = quoteQ.dataUpdatedAt
    ? new Date(quoteQ.dataUpdatedAt).toLocaleString('zh-CN', { hour12: false })
    : '尚未刷新';
  const heroNotes = quote
    ? [
        `当前主阅读路径是“报价 → ${activeTabLabel} → 行动卡 → 下一步跳转”，先别一上来就在所有 tab 间来回切。`,
        `短线情绪分数 ${fmtNum(sentimentScore, 0)}，建议结合价格涨跌幅 ${fmtPct(priceChangePct)} 一起看，而不是单独解读某一个指标。`,
        '如果你已经确认是重点标的，下一步优先去资金流、研究页或模拟交易，不要把个股页当成终点。',
      ]
    : [
        '先输入代码并确认周期，再看报价和主图，首屏现在会优先保留关键指标与动作入口。',
        '技术面、估值、新闻和 AI 诊断都保留在同一页内，但建议顺着 tab 从左到右阅读。',
        '第一次使用时优先跑 600519 之类的熟悉标的，更容易判断信号是否合理。',
      ];
  const askAiSummary = quote ? `${quote.name}，现价 ${fmtNum(Number(quote.price), 2)}，涨跌幅 ${fmtPct(priceChangePct)}` : undefined;

  return (
    <PageContainer className="app-theme-market space-y-4">
      {compactLayout ? (
        <section className="page-hero p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">个股详情</Badge>
            <Badge variant="neutral">{activeTabLabel}</Badge>
            <Badge variant={hasQuoteData ? 'success' : loading ? 'warning' : 'neutral'}>
              {hasQuoteData ? '报价已加载' : loading ? '加载中' : '等待查询'}
            </Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2rem]">
            {quote ? `${quote.name} ${activeCode ?? ''}` : '个股详情'}
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-6 text-text-secondary">
            先确认代码和周期，再看报价快照与当前标签页。行动卡和更多跳转已下沉，不再占满默认首屏。
          </p>
          <div className={`mt-4 grid gap-3 ${mobileOnly ? 'sm:grid-cols-2' : 'sm:grid-cols-2 xl:grid-cols-4'}`}>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">当前代码</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{currentFocusCode}</div>
              <div className="mt-1 text-xs text-text-secondary">{refreshStatus}</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">现价</div>
              <div className={`mt-2 text-lg font-semibold ${chgColor}`}>{quote ? fmtNum(Number(quote.price), 2) : '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">当前标签 {activeTabLabel}</div>
            </div>
            {!mobileOnly ? (
              <>
                <div className="metric-tile rounded-[24px] p-4">
                  <div className="metric-label">涨跌幅</div>
                  <div className={`mt-2 text-lg font-semibold ${chgColor}`}>{quote ? fmtPct(priceChangePct) : '-'}</div>
                  <div className="mt-1 text-xs text-text-secondary">报价快照已并入首屏</div>
                </div>
                <div className="metric-tile rounded-[24px] p-4">
                  <div className="metric-label">当前振幅</div>
                  <div className="mt-2 text-lg font-semibold text-text-primary">{amplitude}</div>
                  <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
                </div>
              </>
            ) : null}
          </div>
          {mobileOnly ? (
            <details className="mt-3 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开更多报价快照</summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="metric-tile rounded-[24px] p-4">
                  <div className="metric-label">涨跌幅</div>
                  <div className={`mt-2 text-lg font-semibold ${chgColor}`}>{quote ? fmtPct(priceChangePct) : '-'}</div>
                  <div className="mt-1 text-xs text-text-secondary">报价快照已并入首屏</div>
                </div>
                <div className="metric-tile rounded-[24px] p-4">
                  <div className="metric-label">当前振幅</div>
                  <div className="mt-2 text-lg font-semibold text-text-primary">{amplitude}</div>
                  <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
                </div>
              </div>
            </details>
          ) : null}
        </section>
      ) : (
        <StockHero
          activeTabLabel={activeTabLabel}
          title={quote ? `${quote.name} ${activeCode ?? ''}` : '个股详情工作台'}
          loading={loading}
          hasQuote={hasQuoteData}
          askAiStockCode={contextCode || undefined}
          askAiSummary={askAiSummary}
          currentFocusCode={currentFocusCode}
          refreshStatus={refreshStatus}
          refreshTimeText={refreshTimeText}
          amplitude={amplitude}
          heroNotes={heroNotes}
          quickLinks={quickLinks}
          watchlistCode={contextCode || code.trim()}
          watchlistName={String(quote?.name ?? '')}
        />
      )}

      <StockQueryShell
        code={code}
        onCodeChange={setCode}
        codeError={codeError}
        period={period}
        onPeriodChange={setPeriod}
        onSubmit={onSubmit}
        loading={loading}
        refreshStatus={refreshStatus}
        refreshTimeText={refreshTimeText}
        sentimentScore={sentimentScore}
        onTabChange={setInfoTab}
      />

      {error ? <ErrorState text={error} /> : null}

      {!compactLayout ? (
        <StockSnapshot
          quote={quote}
          loading={loading}
          priceChangePct={priceChangePct}
          chgColor={chgColor}
          amplitude={amplitude}
          quickLinks={quickLinks}
          contextCode={contextCode}
        />
      ) : null}

      {compactLayout ? (
        <details className="panel-soft overflow-hidden rounded-[28px] p-4 sm:p-5">
          <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开行动卡与下一步</summary>
          <div className="mt-4">
            <StockActionCard actionCard={actionCard} hasQuote={hasQuoteData} />
          </div>
        </details>
      ) : (
        <StockActionCard actionCard={actionCard} hasQuote={hasQuoteData} />
      )}

      <StockDetailTabs
        infoTab={infoTab}
        onInfoTabChange={setInfoTab}
        activeTabLabel={activeTabLabel}
        submittedPeriod={submittedPeriod}
        klineFetching={klineQ.isFetching}
        candleData={candleData}
        orderBook={orderBook}
        technicalData={techApi.data}
        patternData={patternsApi.data}
        showSentiment={Boolean(sentimentQ.data)}
        sentimentScore={sentimentScore}
        fundFlowChart={fundFlowChart}
        fundFlowItems={fundFlowItems}
        fundFlowFetching={fundFlowQ.isFetching}
        hasFundFlowResponse={Boolean(fundFlowQ.data)}
        fundamental={fundamentalObj}
        fundamentalFetching={fundamentalQ.isFetching}
        hasFundamentalResponse={Boolean(fundamentalQ.data)}
        skipKeys={STOCK_DETAIL_SKIP_KEYS}
        newsItems={newsItems}
        newsFetching={newsQ.isFetching}
        valuationMetrics={valuationMetrics}
        hasValuationResponse={Boolean(valuationQ.data)}
        valuationFetching={valuationQ.isFetching}
        activeCode={activeCode}
      />
    </PageContainer>
  );
}
