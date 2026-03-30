'use client';

import { FormEvent, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, TabBar, SkeletonCard, Skeleton } from '@/components/ui';
import { CandlestickChart, BarChart, GaugeChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, fmtAmount, extractArray, extractObject } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { WatchlistButton } from '@/components/watchlist-button';
import { tradingInterval } from '@/lib/trading-hours';
import { fmt } from '@/lib/api';
import { useQuoteSubscription, type QuoteData as LiveQuoteData } from '@/lib/ws';
import Link from 'next/link';
import { AIDiagnosisPanel } from '@/components/ai-diagnosis-panel';
import { PeerComparisonTable } from '@/components/peer-comparison';
import { StockCapitalPanel } from '@/components/stock-capital-panel';
import { unwrapToolPayload } from '@/lib/tool-result';
import type {
  MarketKlineResponseDto,
  MarketQuoteResponseDto,
  NormalizedOrderBook,
  NormalizedQuote,
  StockDetailActionCard,
  StockDetailAggregateDto,
  StockFundFlowEntry,
  StockFundamentalOverview,
  StockNewsItem,
  StockSentimentSnapshot,
  StockValuationOverview,
} from '@aiask/shared-types';

type Period = 'daily' | 'weekly' | 'monthly';
type QuoteData = MarketQuoteResponseDto;
type KlineData = MarketKlineResponseDto;

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const PRIMARY_LINK_CLS =
  'inline-flex items-center justify-center rounded-full bg-[linear-gradient(135deg,#0b6bcb,#2f8cff)] px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] no-underline transition hover:-translate-y-0.5';
const REASON_CHIP_CLS =
  'inline-flex items-center rounded-full border border-glass-border bg-white/42 px-3 py-1.5 text-xs text-text-secondary shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]';

export default function StockPage() {
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode('600519');
  const [period, setPeriod] = useState<Period>('daily');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>('daily');
  const activeCode = submittedCode ?? resolvedCode ?? null;

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
  const [infoTab, setInfoTab] = useState<string>('chart');
  const [wsQuotes, setWsQuotes] = useState<Record<string, Partial<NormalizedQuote>>>({});
  const liveQuoteCode = activeCode;

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

  const INFO_TABS = useMemo(
    () =>
      [
        { key: 'chart', label: 'K线图' },
        { key: 'tech', label: '技术面' },
        { key: 'fund', label: '资金流' },
        { key: 'basic', label: '基本面' },
        { key: 'shares', label: '股本' },
        { key: 'valuation', label: '估值' },
        { key: 'peers', label: '同行对比' },
        { key: 'ai', label: 'AI诊断' },
        { key: 'news', label: '资讯' },
      ] as const,
    [],
  );

  function doFetch(c: string) {
    techApi.trigger('/technical/indicators', { method: 'POST' }, { code: c, indicators: ['RSI', 'MACD', 'KDJ'] });
    patternsApi.trigger('/technical/patterns', { method: 'POST' }, { code: c });
  }

  // 自动查询：URL 或 Store 携带了有效代码时自动触发
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      doFetch(resolvedCode);
    }
  }, [resolvedCode]); // eslint-disable-line react-hooks/exhaustive-deps

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const c = String(form.get('stockCode') ?? code).trim();
    const nextPeriod = String(form.get('period') ?? period) as Period;
    setCode(c);
    if (!validate(c)) return;
    if (c === activeCode && nextPeriod === submittedPeriod) {
      quoteQ.refetch();
      klineQ.refetch();
      sentimentQ.refetch();
      fundFlowQ.refetch();
      fundamentalQ.refetch();
      newsQ.refetch();
    } else {
      setSubmittedCode(c);
      setSubmittedPeriod(nextPeriod);
    }
    doFetch(c);
  }

  const candleData = useMemo(
    () =>
      (klineQ.data?.kline ?? []).map((x) => ({
        date: x.date.slice(0, 10),
        open: x.open,
        close: x.close,
        low: x.low,
        high: x.high,
        volume: x.volume,
      })),
    [klineQ.data],
  );
  const wsQuote = liveQuoteCode ? (wsQuotes[liveQuoteCode] ?? null) : null;

  const q = useMemo<NormalizedQuote | undefined>(() => {
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
  const hasQuoteData = Boolean(q);
  const hasKlineData = candleData.length > 0;
  const loading =
    hasRequested &&
    ((!hasQuoteData && (quoteQ.isPending || quoteQ.isFetching)) ||
      (!hasQuoteData && !hasKlineData && (klineQ.isPending || klineQ.isFetching)));
  const error =
    quoteQ.error || klineQ.error || sentimentQ.error || fundFlowQ.error || fundamentalQ.error || newsQ.error;

  const contextCode = useMemo(() => String(q?.code ?? activeCode ?? '').trim(), [activeCode, q?.code]);
  const sentimentPayload = useMemo(() => unwrapToolPayload(sentimentQ.data), [sentimentQ.data]);
  const sentimentScore = Number(sentimentPayload.score ?? sentimentPayload.sentiment_score ?? 0);
  const SKIP_KEYS = [
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

  const fundFlowItems = useMemo(() => extractArray(fundFlowQ.data, 'flows') as StockFundFlowEntry[], [fundFlowQ.data]);
  const fundFlowChart = useMemo(
    () =>
      fundFlowItems.slice(-20).map((x) => ({
        label: String(x.date ?? '').slice(5),
        value: Number(x.netInflow ?? x.net_inflow ?? 0),
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
    const ob = raw.orderBook ? extractObject(raw.orderBook) : raw;
    const bids = Array.isArray(ob.bids) ? (ob.bids as Array<{ price: number; volume: number }>) : [];
    const asks = Array.isArray(ob.asks) ? (ob.asks as Array<{ price: number; volume: number }>).slice().reverse() : [];
    return {
      symbol: String(ob.symbol ?? contextCode ?? ''),
      bids,
      asks,
      timestamp: typeof ob.timestamp === 'string' ? ob.timestamp : null,
    };
  }, [contextCode, orderBookQ.data]);

  const quickLinks = useMemo(() => {
    const c = contextCode;
    if (!c) return [];
    return [
      { label: '资金流向', href: `/fund-flow?code=${c}` },
      { label: '基本面', href: `/fundamental?code=${c}` },
      { label: '技术分析', href: `/technical?code=${c}` },
      { label: '研报公告', href: `/research?code=${c}` },
      { label: '估值分析', href: `/valuation?code=${c}` },
      { label: '情绪分析', href: `/sentiment?code=${c}` },
    ];
  }, [contextCode]);

  const actionCard = useMemo<StockDetailActionCard | null>(() => {
    if (!contextCode || !q) return null;
    const changePercent = Number(q.changePercent ?? q.change_pct ?? 0);
    const valuationPe = Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? q.pe ?? NaN);
    const turnoverCandidate = Number(klineQ.data?.kline?.at(-1)?.turnover ?? NaN);
    const turnoverRate =
      Number.isFinite(turnoverCandidate) && turnoverCandidate > 0 && turnoverCandidate <= 100
        ? turnoverCandidate
        : null;
    const reasons: string[] = [];

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

    reasons.push(`短线情绪分数 ${fmtNum(sentimentScore, 0)}`);
    reasons.push(`当日涨跌幅 ${fmtPct(changePercent)}`);
    if (Number.isFinite(valuationPe)) reasons.push(`PE 约 ${fmtNum(valuationPe, 2)}`);
    if (turnoverRate != null) reasons.push(`最近换手约 ${fmtNum(turnoverRate, 2)}%`);

    return {
      title,
      tone,
      summary,
      reasons,
      links: quickLinks.slice(0, 3),
    };
  }, [contextCode, klineQ.data?.kline, q, quickLinks, sentimentScore, valuationMetrics.pe, valuationMetrics.pe_ttm]);

  const stockDetail = useMemo<StockDetailAggregateDto>(() => {
    const sentiment: StockSentimentSnapshot | null = contextCode
      ? {
          score: sentimentScore,
          sentiment_score: sentimentScore,
          signal: typeof sentimentPayload.signal === 'string' ? sentimentPayload.signal : undefined,
          label: typeof sentimentPayload.label === 'string' ? sentimentPayload.label : undefined,
          summary: typeof sentimentPayload.summary === 'string' ? sentimentPayload.summary : undefined,
        }
      : null;
    return {
      code: contextCode,
      quote: q ?? null,
      kline: klineQ.data?.kline ?? [],
      orderBook,
      sentiment,
      fundFlow: fundFlowItems,
      fundamental: fundamentalObj,
      valuation: valuationMetrics,
      news: newsItems,
      actions: actionCard ? [actionCard] : [],
    };
  }, [
    actionCard,
    contextCode,
    fundamentalObj,
    fundFlowItems,
    klineQ.data?.kline,
    newsItems,
    orderBook,
    q,
    sentimentPayload.label,
    sentimentPayload.signal,
    sentimentPayload.summary,
    sentimentScore,
    valuationMetrics,
  ]);

  usePageContext({
    pageKey: 'stock',
    title: q ? `${q.name} ${contextCode}` : '股票详情',
    summary: q
      ? `${contextCode} 当前价 ${fmtNum(Number(q.price), 2)}，涨跌幅 ${fmtPct(Number(q.changePercent ?? q.change_pct ?? 0))}，情绪分数 ${fmtNum(sentimentScore, 0)}。`
      : `股票详情页，当前输入 ${code || '未填写'}。`,
    stockCode: contextCode || undefined,
    tags: [
      submittedPeriod === 'daily' ? '日线' : submittedPeriod === 'weekly' ? '周线' : '月线',
      infoTab,
      q ? `PE ${fmtNum(Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? 0), 2)}` : '未加载估值',
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
      hasQuote: Boolean(q),
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
          if (!contextCode) {
            return { message: '当前还没有有效股票代码' };
          }
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

  // Update page title with stock name
  useEffect(() => {
    if (q) document.title = `${q.name}(${activeCode ?? ''}) | AIASK`;
    return () => {
      document.title = 'AIASK 智能股票分析';
    };
  }, [activeCode, q]);

  const priceChangePct = Number(q?.changePercent ?? q?.change_pct ?? 0);
  const chgColor = priceChangePct >= 0 ? 'text-danger' : 'text-success';
  const amplitude =
    q?.high && q?.low && q?.prevClose
      ? (((Number(q.high) - Number(q.low)) / Number(q.prevClose)) * 100).toFixed(2) + '%'
      : '-';
  const activeTabLabel = INFO_TABS.find((item) => item.key === infoTab)?.label ?? 'K线图';
  const currentFocusCode = contextCode || code.trim() || '600519';
  const refreshStatus = quoteQ.isFetching ? '数据刷新中' : q ? '已同步最新报价' : '等待首次加载';
  const refreshTimeText = quoteQ.dataUpdatedAt
    ? new Date(quoteQ.dataUpdatedAt).toLocaleString('zh-CN', { hour12: false })
    : '尚未刷新';
  const heroNotes = q
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
  return (
    <PageContainer className="app-theme-market space-y-4">
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Stock Workspace</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={q ? 'success' : loading ? 'warning' : 'neutral'}>
                {q ? '报价已加载' : loading ? '加载中' : '等待查询'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              {q ? `${q.name} ${activeCode ?? ''}` : '个股详情工作台'}
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这次重构把个股页收束成一条更清晰的阅读路径：先锁定代码和周期，再看报价、主图和行动卡，最后跳转到资金流、研究、交易或
              AI 诊断，不再让加载态把主区打散。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="submit" form="stock-query-form" disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
                {loading ? '加载中...' : '查询当前股票'}
              </button>
              <AskAiButton
                stockCode={contextCode || undefined}
                summary={
                  q ? `${q.name}，现价 ${fmtNum(Number(q.price), 2)}，涨跌幅 ${fmtPct(priceChangePct)}` : undefined
                }
                prompt={contextCode ? `请分析 ${contextCode} 当前个股页信号` : '请分析当前个股页'}
                label="解读当前个股"
              />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{currentFocusCode}</div>
                <div className="mt-1 text-xs text-text-secondary">当前工作区聚焦标的</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标签</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">当前正在阅读的分析视角</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">刷新状态</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{refreshStatus}</div>
                <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前振幅</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{amplitude}</div>
                <div className="mt-1 text-xs text-text-secondary">用于判断短线波动强弱</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
              <div className="mt-4 space-y-3">
                {heroNotes.map((note) => (
                  <div key={note} className={NOTE_CARD_CLS}>
                    {note}
                  </div>
                ))}
              </div>
            </div>
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷动作</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {q ? <WatchlistButton code={contextCode || code.trim()} name={String(q.name ?? '')} size="md" /> : null}
                {contextCode ? (
                  <>
                    <Link href={`/paper-trading?code=${contextCode}`} className={PRIMARY_LINK_CLS}>
                      去模拟交易
                    </Link>
                    <Link href={`/backtest?code=${contextCode}`} className={LINK_CHIP_CLS}>
                      策略回测
                    </Link>
                    <Link href={`/assistant?code=${contextCode}`} className={LINK_CHIP_CLS}>
                      AI诊断
                    </Link>
                  </>
                ) : null}
              </div>
              {quickLinks.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {quickLinks.map((link) => (
                    <Link key={link.href} href={link.href} className={LINK_CHIP_CLS}>
                      {link.label}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.06fr)_320px]">
        <div className={PANEL_CLS}>
          <form id="stock-query-form" onSubmit={onSubmit} className="grid gap-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="eyebrow">Query Deck</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">代码、周期与刷新入口</h2>
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  先固定标的与周期，再让下方所有图表、指标与资讯沿同一上下文刷新，避免每个模块各自加载、阅读顺序被打散。
                </p>
              </div>
              <Badge variant="info">{period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'}</Badge>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">股票代码</span>
                <input
                  name="stockCode"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  maxLength={6}
                  placeholder="如 600519"
                  aria-label="股票代码"
                  className={`${FIELD_CLS} w-[180px]`}
                />
              </label>
              <label className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">K线周期</span>
                <select
                  name="period"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value as Period)}
                  aria-label="K线周期"
                  className={`${FIELD_CLS} w-[120px]`}
                >
                  <option value="daily">日线</option>
                  <option value="weekly">周线</option>
                  <option value="monthly">月线</option>
                </select>
              </label>
              <button type="submit" disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
                {loading ? '加载中...' : '立即查询'}
              </button>
            </div>
            {codeError ? (
              <span className="text-xs text-error" role="alert">
                {codeError}
              </span>
            ) : null}
          </form>
        </div>

        <div className="grid gap-4">
          <div className={PANEL_CLS}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前状态</div>
            <div className="mt-4 grid gap-3">
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">报价刷新</div>
                <div className="mt-3 text-sm font-semibold text-text-primary">{refreshStatus}</div>
                <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">短线情绪</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{fmtNum(sentimentScore, 0)}</div>
                <div className="mt-1 text-xs text-text-secondary">结合价格和量能一起理解更稳妥</div>
              </div>
            </div>
          </div>
          <div className={PANEL_CLS}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步建议</div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => setInfoTab('chart')} className={HERO_SECONDARY_BUTTON_CLS}>
                看主图
              </button>
              <button type="button" onClick={() => setInfoTab('fund')} className={HERO_SECONDARY_BUTTON_CLS}>
                看资金流
              </button>
              <button type="button" onClick={() => setInfoTab('valuation')} className={HERO_SECONDARY_BUTTON_CLS}>
                看估值
              </button>
            </div>
          </div>
        </div>
      </div>
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="mt-0 min-h-[320px] p-4 sm:p-5">
        {q ? (
          <>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="eyebrow">Snapshot</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">报价与关键指标</h2>
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  这一屏优先回答“现在价格处在什么位置、波动强弱如何、还有哪些最值得继续看”的问题。
                </p>
              </div>
              <Badge variant={priceChangePct >= 0 ? 'danger' : 'success'}>
                {priceChangePct >= 0 ? '偏强' : '承压'}
              </Badge>
            </div>
            <KpiGrid cols={4}>
              <KpiCard title="现价" value={fmtNum(Number(q.price))} className={chgColor} />
              <KpiCard title="涨跌幅" value={fmtPct(Number(q.changePercent))} className={chgColor} />
              <KpiCard title="涨跌额" value={fmtNum(Number(q.change), 2)} className={chgColor} />
              <KpiCard title="振幅" value={amplitude} />
              <KpiCard title="成交量" value={fmtAmount(Number(q.volume))} suffix="股" />
              <KpiCard title="成交额" value={fmtAmount(Number(q.amount))} suffix="元" />
              <KpiCard title="最高/最低" value={`${fmtNum(Number(q.high))} / ${fmtNum(Number(q.low))}`} />
              <KpiCard title="开盘/昨收" value={`${fmtNum(Number(q.open))} / ${fmtNum(Number(q.prevClose))}`} />
            </KpiGrid>

            {/* Quick Navigation + Actions */}
            <div className="flex gap-2 flex-wrap mt-3">
              {quickLinks.map((lnk) => (
                <Link key={lnk.href} href={lnk.href} className={LINK_CHIP_CLS}>
                  {lnk.label}
                </Link>
              ))}
              {contextCode && (
                <>
                  <Link href={`/paper-trading?code=${contextCode}`} className={PRIMARY_LINK_CLS}>
                    去模拟下单
                  </Link>
                  <Link href={`/backtest?code=${contextCode}`} className={LINK_CHIP_CLS}>
                    回测分析
                  </Link>
                  <Link href={`/assistant?code=${contextCode}`} className={LINK_CHIP_CLS}>
                    AI诊断
                  </Link>
                </>
              )}
            </div>
          </>
        ) : (
          <div className="space-y-4" aria-hidden="true">
            <KpiGrid cols={4}>
              {Array.from({ length: 8 }).map((_, index) => (
                <SkeletonCard key={index} />
              ))}
            </KpiGrid>
            <div className="flex gap-2 flex-wrap">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="w-[96px]" height={28} />
              ))}
            </div>
            <div className="pt-2">
              {loading ? (
                <LoadingState text="正在加载个股报价与关键指标..." />
              ) : (
                <p className="m-0 text-sm text-text-secondary">
                  输入股票代码后，这里会先展示报价头部、关键指标和快捷动作，避免结果返回时把主图整体推下去。
                </p>
              )}
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard className="mt-0 min-h-[200px] p-4 sm:p-5">
        {stockDetail.actions?.[0] ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_280px]">
            <div className="panel-soft rounded-[24px] p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="mt-0 mb-1">{stockDetail.actions[0].title}</h3>
                  <p className="m-0 text-sm leading-6 text-text-secondary">{stockDetail.actions[0].summary}</p>
                </div>
                <Badge variant={stockDetail.actions[0].tone}>行动建议</Badge>
              </div>
              <div className="flex flex-wrap gap-2 mt-4">
                {stockDetail.actions[0].reasons.map((reason) => (
                  <span key={reason} className={REASON_CHIP_CLS}>
                    {reason}
                  </span>
                ))}
              </div>
            </div>
            <div className="panel-soft rounded-[24px] p-4 sm:p-5">
              <div className="metric-label">推荐动作</div>
              <div className="mt-3 space-y-2">
                {stockDetail.actions[0].links.map((link, index) => (
                  <Link key={link.href} href={link.href} className={index === 0 ? PRIMARY_LINK_CLS : LINK_CHIP_CLS}>
                    {link.label}
                  </Link>
                ))}
              </div>
              <p className="m-0 mt-4 text-xs leading-6 text-text-secondary">
                先沿主建议继续跳转，再按需要补充到研究页、交易页或回测页，避免在个股页停留过久。
              </p>
            </div>
          </div>
        ) : q ? (
          <EmptyState
            text="行动卡已预留完成。"
            hint="当报价、情绪和估值信号汇总完成后，这里会给出下一步操作建议，不再把图表区整体向下挤。"
            className="py-10"
          />
        ) : (
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="w-56" height={22} />
            <Skeleton className="w-full" height={18} />
            <div className="flex gap-2 flex-wrap">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="w-[92px]" height={28} />
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      <div className={PANEL_CLS}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Detail Tabs</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">分层阅读各个分析维度</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              建议先看主图和技术面，再看资金、估值、AI 诊断和资讯。这样更容易把价格位置、交易结构和基本面叙事串起来。
            </p>
          </div>
          <Badge variant="neutral">{activeTabLabel}</Badge>
        </div>
        <div className="mt-4">
          <TabBar tabs={INFO_TABS} active={infoTab} onChange={setInfoTab} />
        </div>
      </div>

      {infoTab === 'chart' && (
        <SectionCard tabAttached className="min-h-[560px] p-4 sm:p-5">
          <h3 className="mt-0">
            K线图（{submittedPeriod === 'daily' ? '日线' : submittedPeriod === 'weekly' ? '周线' : '月线'}）
          </h3>
          {klineQ.isFetching && !candleData.length ? (
            <div className="space-y-3" aria-hidden="true">
              <Skeleton className="w-full" height={420} />
              <div className="grid grid-cols-2 gap-4">
                <Skeleton className="w-full" height={96} />
                <Skeleton className="w-full" height={96} />
              </div>
            </div>
          ) : candleData.length ? (
            <CandlestickChart data={candleData} height={420} />
          ) : (
            <EmptyState
              text="暂无 K 线数据"
              hint="主图区已保留固定高度。切换股票或周期时，图表会在原位置刷新，不再把盘口和下方内容整体推移。"
            />
          )}
          {(orderBook.bids.length > 0 || orderBook.asks.length > 0) && (
            <div className="mt-4">
              <h3 className="mt-0">五档盘口</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-text-muted text-xs mb-1 flex justify-between">
                    <span>卖盘</span>
                    <span>价格 / 数量</span>
                  </div>
                  {orderBook.asks.map((a, i) => (
                    <div key={i} className="metric-tile mb-2 flex justify-between px-3 py-2 text-success">
                      <span>卖{orderBook.asks.length - i}</span>
                      <span>
                        {fmtNum(a.price, 2)} / {fmtAmount(a.volume)}
                      </span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-text-muted text-xs mb-1 flex justify-between">
                    <span>买盘</span>
                    <span>价格 / 数量</span>
                  </div>
                  {orderBook.bids.map((b, i) => (
                    <div key={i} className="metric-tile mb-2 flex justify-between px-3 py-2 text-danger">
                      <span>买{i + 1}</span>
                      <span>
                        {fmtNum(b.price, 2)} / {fmtAmount(b.volume)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'tech' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h3 className="mt-0">技术指标</h3>
              {techApi.data ? (
                (() => {
                  const payload = unwrapToolPayload(techApi.data);
                  const rsi = payload.rsi as Record<string, unknown> | undefined;
                  const macd = payload.macd as Record<string, unknown> | undefined;
                  const kdj = payload.kdj as Record<string, unknown> | undefined;
                  const rsiVal = Number(rsi?.value ?? 0);
                  const rsiSignal = String(rsi?.signal ?? 'hold');
                  const rsiLabel =
                    rsiSignal === 'buy'
                      ? '买入'
                      : rsiSignal === 'sell'
                        ? '卖出'
                        : rsiVal > 70
                          ? '超买'
                          : rsiVal < 30
                            ? '超卖'
                            : '中性';
                  const rsiColor = rsiVal > 70 ? 'text-danger' : rsiVal < 30 ? 'text-success' : '';
                  const macdArr = (macd?.macd ?? macd?.MACD) as number[] | undefined;
                  const sigArr = (macd?.signal ?? macd?.Signal) as number[] | undefined;
                  const macdLast = macdArr?.length ? macdArr[macdArr.length - 1] : null;
                  const sigLast = sigArr?.length ? sigArr[sigArr.length - 1] : null;
                  const macdCross = macdLast != null && sigLast != null ? (macdLast > sigLast ? '金叉' : '死叉') : '-';
                  const macdCrossColor =
                    macdCross === '金叉' ? 'text-danger' : macdCross === '死叉' ? 'text-success' : '';
                  const kArr = (kdj?.k ?? kdj?.K) as number[] | undefined;
                  const dArr = (kdj?.d ?? kdj?.D) as number[] | undefined;
                  const jArr = (kdj?.j ?? kdj?.J) as number[] | undefined;
                  const kLast = kArr?.length ? kArr[kArr.length - 1] : null;
                  const dLast = dArr?.length ? dArr[dArr.length - 1] : null;
                  const jLast = jArr?.length ? jArr[jArr.length - 1] : null;
                  const kdjSignal = kLast != null && dLast != null ? (kLast > dLast ? '金叉' : '死叉') : '-';
                  const kdjColor = kdjSignal === '金叉' ? 'text-danger' : kdjSignal === '死叉' ? 'text-success' : '';
                  return (
                    <div className="space-y-3">
                      <div className="panel-soft rounded-[22px] p-4">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">RSI(14)</span>
                          <Badge
                            variant={
                              rsiColor.includes('danger')
                                ? 'danger'
                                : rsiColor.includes('success')
                                  ? 'success'
                                  : 'neutral'
                            }
                          >
                            {rsiLabel}
                          </Badge>
                        </div>
                        <div className={`text-2xl font-bold mt-1 ${rsiColor}`}>{fmtNum(rsiVal, 2)}</div>
                      </div>
                      <div className="panel-soft rounded-[22px] p-4">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">MACD</span>
                          <Badge
                            variant={
                              macdCrossColor.includes('danger')
                                ? 'danger'
                                : macdCrossColor.includes('success')
                                  ? 'success'
                                  : 'neutral'
                            }
                          >
                            {macdCross}
                          </Badge>
                        </div>
                        <div className="text-sm mt-1 text-text-secondary">
                          DIF: {fmtNum(macdLast, 2)} / DEA: {fmtNum(sigLast, 2)}
                        </div>
                      </div>
                      <div className="panel-soft rounded-[22px] p-4">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">KDJ</span>
                          <Badge
                            variant={
                              kdjColor.includes('danger')
                                ? 'danger'
                                : kdjColor.includes('success')
                                  ? 'success'
                                  : 'neutral'
                            }
                          >
                            {kdjSignal}
                          </Badge>
                        </div>
                        <div className="text-sm mt-1 text-text-secondary">
                          K: {fmtNum(kLast, 2)} / D: {fmtNum(dLast, 2)} / J: {fmtNum(jLast, 2)}
                        </div>
                      </div>
                    </div>
                  );
                })()
              ) : (
                <p className="text-text-secondary text-sm">查询股票后显示技术指标</p>
              )}
            </div>
            <div>
              <h3 className="mt-0">K线形态</h3>
              {patternsApi.data ? (
                (() => {
                  const raw = unwrapToolPayload(patternsApi.data);
                  const arr = (Array.isArray(raw.patterns) ? raw.patterns : []) as Record<string, unknown>[];
                  return arr.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {arr.map((p, i) => (
                        <Badge key={i} variant={p.bullish ? 'danger' : 'success'}>
                          {String(p.name ?? p.pattern ?? '')} {p.reliability === 'high' ? '★' : ''}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-text-secondary text-sm">未检测到形态信号</p>
                  );
                })()
              ) : (
                <p className="text-text-secondary text-sm">查询股票后显示形态检测</p>
              )}
            </div>
          </div>
          {sentimentQ.data && (
            <div className="mt-4">
              <h3 className="mt-0">市场情绪</h3>
              <GaugeChart
                value={sentimentScore || 50}
                min={0}
                max={100}
                title={sentimentScore > 50 ? '偏多' : sentimentScore < 50 ? '偏空' : '中性'}
                height={200}
              />
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'fund' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">资金流向（近20日）</h3>
          {fundFlowChart.length > 0 ? (
            <BarChart items={fundFlowChart} height={300} yAxisName="净流入" colorByValue />
          ) : (
            <p className="text-text-secondary text-sm">
              {fundFlowQ.isFetching ? '加载中...' : fundFlowQ.data ? '暂无资金流向数据' : '查询股票后显示资金流向'}
            </p>
          )}
          {fundFlowItems.length > 0 && (
            <div className="mt-3 grid grid-cols-3 gap-2">
              <KpiCard
                title="最近净流入"
                value={fmtAmount(
                  Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).netInflow ?? 0),
                )}
              />
              <KpiCard
                title="主力流入"
                value={fmtAmount(
                  Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).mainInflow ?? 0),
                )}
              />
              <KpiCard
                title="散户流入"
                value={fmtAmount(
                  Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).retailInflow ?? 0),
                )}
              />
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'basic' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">基本面概览</h3>
          {fundamentalObj && Object.keys(fundamentalObj).length > 0 ? (
            <KpiGrid cols={4}>
              {Object.entries(fundamentalObj)
                .filter(([k]) => !SKIP_KEYS.includes(k))
                .flatMap(([k, v]) => {
                  // Flatten nested objects (e.g. financials: { roe, netProfit })
                  if (v && typeof v === 'object' && !Array.isArray(v)) {
                    return Object.entries(v as Record<string, unknown>).map(
                      ([sk, sv]) => [sk, sv] as [string, unknown],
                    );
                  }
                  return [[k, v] as [string, unknown]];
                })
                .slice(0, 16)
                .map(([k, v]) => {
                  const num = Number(v);
                  const display =
                    v == null
                      ? '-'
                      : !isNaN(num) && v !== ''
                        ? Math.abs(num) > 1e6
                          ? fmtAmount(num)
                          : fmtNum(num, 2)
                        : String(v);
                  const labels: Record<string, string> = {
                    roe: 'ROE',
                    netProfit: '净利润',
                    revenue: '营收',
                    debtRatio: '资产负债率',
                    pe: 'PE',
                    pb: 'PB',
                    ps: 'PS',
                    marketCap: '总市值',
                    eps: 'EPS',
                    bps: '每股净资产',
                    totalShares: '总股本',
                    floatShares: '流通股本',
                  };
                  return <KpiCard key={k} title={labels[k] ?? k} value={display} />;
                })}
            </KpiGrid>
          ) : (
            <p className="text-text-secondary text-sm">
              {fundamentalQ.isFetching
                ? '加载中...'
                : fundamentalQ.data
                  ? '暂无基本面数据'
                  : '查询股票后显示基本面数据'}
            </p>
          )}
        </SectionCard>
      )}

      {infoTab === 'news' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">最新资讯</h3>
          {newsItems.length > 0 ? (
            <div className="space-y-3 max-h-[500px] overflow-auto">
              {newsItems.slice(0, 20).map((item: Record<string, unknown>, i: number) => (
                <div key={i} className="panel-soft rounded-[22px] p-4">
                  {item.url ? (
                    <a
                      href={String(item.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-sm text-primary hover:underline"
                    >
                      {fmt(item.title as string)}
                    </a>
                  ) : (
                    <div className="font-medium text-sm">{fmt(item.title as string)}</div>
                  )}
                  <div className="text-xs text-text-muted mt-0.5">
                    {fmt(item.date as string)} {item.source ? `｜ ${fmt(item.source as string)}` : ''}
                  </div>
                  {item.summary ? (
                    <div className="text-xs text-text-secondary mt-1">{String(item.summary).slice(0, 120)}</div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-text-secondary text-sm">{newsQ.isFetching ? '加载中...' : '查询股票后显示相关资讯'}</p>
          )}
        </SectionCard>
      )}

      {infoTab === 'shares' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">🏦 股本结构</h3>
          {activeCode ? (
            <StockCapitalPanel code={activeCode} />
          ) : (
            <p className="text-text-secondary text-sm">查询股票后显示股本数据</p>
          )}
        </SectionCard>
      )}

      {infoTab === 'valuation' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">估值分析</h3>
          {valuationQ.data ? (
            (() => {
              const pe = Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? 0);
              const pb = Number(valuationMetrics.pb ?? 0);
              const ps = Number(valuationMetrics.ps ?? 0);
              const pcf = Number(valuationMetrics.pcf ?? 0);
              const mktCap = Number(valuationMetrics.market_cap ?? 0);
              const cirMktCap = Number(valuationMetrics.float_market_cap ?? 0);
              const peHist = valuationMetrics.pe_percentile;
              const pbHist = valuationMetrics.pb_percentile;
              return (
                <div className="space-y-4">
                  <KpiGrid cols={4}>
                    <KpiCard title="PE(TTM)" value={pe > 0 ? fmtNum(pe, 2) : '亏损'} />
                    <KpiCard title="PB" value={fmtNum(pb, 2)} />
                    <KpiCard title="PS" value={fmtNum(ps, 2)} />
                    <KpiCard title="PCF" value={pcf > 0 ? fmtNum(pcf, 2) : '-'} />
                    <KpiCard title="总市值" value={fmtAmount(mktCap)} suffix="元" />
                    <KpiCard title="流通市值" value={cirMktCap > 0 ? fmtAmount(cirMktCap) : '-'} suffix="元" />
                    {peHist != null && <KpiCard title="PE历史分位" value={fmtPct(Number(peHist))} />}
                    {pbHist != null && <KpiCard title="PB历史分位" value={fmtPct(Number(pbHist))} />}
                  </KpiGrid>
                  {pe > 0 && (
                    <div className="mt-2">
                      <GaugeChart
                        value={Math.min(pe, 100)}
                        min={0}
                        max={100}
                        title={pe < 15 ? '低估' : pe < 30 ? '合理' : pe < 60 ? '偏高' : '高估'}
                        height={180}
                      />
                      <p className="text-xs text-text-secondary text-center mt-1">PE估值水平参考</p>
                    </div>
                  )}
                </div>
              );
            })()
          ) : (
            <p className="text-text-secondary text-sm">
              {valuationQ.isFetching ? '加载中...' : '查询股票后显示估值数据'}
            </p>
          )}
        </SectionCard>
      )}

      {infoTab === 'ai' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">🤖 AI 智能诊断</h3>
          {activeCode ? (
            <AIDiagnosisPanel key={activeCode} code={activeCode} />
          ) : (
            <p className="text-text-secondary text-sm">请先查询股票代码</p>
          )}
        </SectionCard>
      )}

      {infoTab === 'peers' && (
        <SectionCard tabAttached className="p-4 sm:p-5">
          <h3 className="mt-0">🏭 同行业对比</h3>
          {activeCode ? (
            <PeerComparisonTable code={activeCode} />
          ) : (
            <p className="text-text-secondary text-sm">查询股票后显示同行对比</p>
          )}
        </SectionCard>
      )}
    </PageContainer>
  );
}
