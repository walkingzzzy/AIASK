'use client';

import { FormEvent, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, TabBar } from '@/components/ui';
import { CandlestickChart, BarChart, GaugeChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
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

type Period = 'daily' | 'weekly' | 'monthly';
type NormalizedQuote = import('@aiask/shared-types').NormalizedQuote;
type QuoteData = { quote?: NormalizedQuote; meta?: { cache?: unknown; fetchedAt?: string } };
type KlineData = { kline?: import('@aiask/shared-types').NormalizedKlinePoint[]; meta?: { cache?: unknown; fetchedAt?: string } };

export default function StockPage() {
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode('600519');
  const [period, setPeriod] = useState<Period>('daily');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>('daily');

  const quoteQ = useApiQuery<QuoteData>(
    submittedCode ? `/market/quote?code=${encodeURIComponent(submittedCode)}` : null,
    {
      refetchInterval: tradingInterval(30_000),
      parse: (raw) => {
        const obj = ensureRecord(raw, '个股行情');
        if ('quote' in obj && obj.quote != null && typeof obj.quote !== 'object') {
          throw new Error('个股行情.quote 字段类型异常');
        }
        return obj as QuoteData;
      },
    },
  );
  const klineQ = useApiQuery<KlineData>(
    submittedCode ? `/market/kline?code=${encodeURIComponent(submittedCode)}&period=${submittedPeriod}&limit=250` : null,
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
    submittedCode ? `/sentiment/stock?code=${encodeURIComponent(submittedCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '个股情绪') },
  );
  const fundFlowQ = useApiQuery<unknown>(
    submittedCode ? `/fund-flow/stock?code=${encodeURIComponent(submittedCode)}` : null,
    { parse: (raw) => ensureRecordOrArray(raw, '个股资金流') },
  );
  const fundamentalQ = useApiQuery<unknown>(
    submittedCode ? `/fundamental/overview?code=${encodeURIComponent(submittedCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '个股基本面') },
  );
  const newsQ = useApiQuery<unknown>(
    submittedCode ? `/research/stock-news?code=${encodeURIComponent(submittedCode)}` : null,
    { parse: (raw) => ensureRecordOrArray(raw, '个股资讯') },
  );
  const orderBookQ = useApiQuery<unknown>(
    submittedCode ? `/market/order-book?code=${encodeURIComponent(submittedCode)}` : null,
    { refetchInterval: tradingInterval(10_000), parse: (raw) => ensureRecord(raw, '个股盘口') },
  );
  const valuationQ = useApiQuery<unknown>(
    submittedCode ? `/valuation/overview?code=${encodeURIComponent(submittedCode)}` : null,
    { parse: (raw) => ensureRecord(raw, '估值概览') },
  );
  const [infoTab, setInfoTab] = useState<string>('chart');
  const wsQuotesRef = useRef<Map<string, Partial<NormalizedQuote>>>(new Map());
  const [wsQuoteTick, setWsQuoteTick] = useState(0);
  const liveQuoteCode = submittedCode ?? resolvedCode ?? null;

  const handleWsQuote = useCallback((data: LiveQuoteData) => {
    const liveCode = String(data.code ?? '').trim();
    if (!liveCode) return;
    wsQuotesRef.current.set(liveCode, data as Partial<NormalizedQuote>);
    setWsQuoteTick((tick) => tick + 1);
  }, []);

  useQuoteSubscription({
    codes: liveQuoteCode ? [liveQuoteCode] : [],
    type: 'stock',
    enabled: Boolean(liveQuoteCode),
    onUpdate: handleWsQuote,
  });

  const INFO_TABS = useMemo(() => [
    { key: 'chart', label: 'K线图' },
    { key: 'tech', label: '技术面' },
    { key: 'fund', label: '资金流' },
    { key: 'basic', label: '基本面' },
    { key: 'shares', label: '股本' },
    { key: 'valuation', label: '估值' },
    { key: 'peers', label: '同行对比' },
    { key: 'ai', label: 'AI诊断' },
    { key: 'news', label: '资讯' },
  ] as const, []);

  function doFetch(c: string) {
    techApi.trigger('/technical/indicators', { method: 'POST' }, { code: c, indicators: ['RSI', 'MACD', 'KDJ'] });
    patternsApi.trigger('/technical/patterns', { method: 'POST' }, { code: c });
  }

  // 自动查询：URL 或 Store 携带了有效代码时自动触发
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setSubmittedCode(resolvedCode);
      doFetch(resolvedCode);
    }
  }, [resolvedCode]); // eslint-disable-line react-hooks/exhaustive-deps

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const c = code.trim();
    if (c === submittedCode && period === submittedPeriod) {
      quoteQ.refetch(); klineQ.refetch();
      sentimentQ.refetch(); fundFlowQ.refetch(); fundamentalQ.refetch(); newsQ.refetch();
    } else {
      setSubmittedCode(c);
      setSubmittedPeriod(period);
    }
    doFetch(c);
  }

  const loading = quoteQ.isFetching || klineQ.isFetching || sentimentQ.isFetching || fundFlowQ.isFetching || fundamentalQ.isFetching || newsQ.isFetching;
  const error = quoteQ.error || klineQ.error || sentimentQ.error || fundFlowQ.error || fundamentalQ.error || newsQ.error;

  const candleData = useMemo(() => (klineQ.data?.kline ?? []).map((x) => ({
    date: x.date.slice(0, 10), open: x.open, close: x.close, low: x.low, high: x.high, volume: x.volume,
  })), [klineQ.data]);

  const wsQuote = useMemo(() => {
    if (!liveQuoteCode) return null;
    return wsQuotesRef.current.get(liveQuoteCode) ?? null;
  }, [liveQuoteCode, wsQuoteTick]);

  const q = useMemo<NormalizedQuote | undefined>(() => {
    const base = quoteQ.data?.quote;
    if (!base && !wsQuote) return undefined;
    return {
      ...(base ?? {} as NormalizedQuote),
      ...(wsQuote ?? {}),
      code: String(wsQuote?.code ?? base?.code ?? liveQuoteCode ?? ''),
      name: String(wsQuote?.name ?? base?.name ?? ''),
    } as NormalizedQuote;
  }, [liveQuoteCode, quoteQ.data?.quote, wsQuote]);
  const sentimentScore = Number(sentimentQ.data?.score ?? sentimentQ.data?.sentiment_score ?? 0);
  const SKIP_KEYS = ['tool', 'meta', 'code', 'sourceTool', 'sourceTools', 'argsMatched', 'result', 'traceId', 'success', 'data', 'error', 'source', 'cached', 'timestamp', 'source_chain', 'attempted_sources', 'fallback_used', 'fallback_reason', 'data_timestamp'];

  /** Unwrap nested MCP envelope: { result: { data: payload } } → payload */
  function unwrapPayload(raw: Record<string, unknown> | null | undefined): Record<string, unknown> {
    if (!raw) return {};
    const r = (raw.result ?? raw) as Record<string, unknown>;
    let payload: Record<string, unknown> = r;
    if (r && typeof r === 'object' && 'data' in r && r.data && typeof r.data === 'object' && !Array.isArray(r.data)) {
      payload = r.data as Record<string, unknown>;
    }
    // If payload has a single non-metadata key whose value is a plain object, unwrap it
    const keys = Object.keys(payload).filter((k) => !SKIP_KEYS.includes(k));
    if (keys.length === 1 && payload[keys[0]] && typeof payload[keys[0]] === 'object' && !Array.isArray(payload[keys[0]])) {
      return payload[keys[0]] as Record<string, unknown>;
    }
    return payload;
  }

  const fundFlowItems = useMemo(() => extractArray(fundFlowQ.data, 'flows'), [fundFlowQ.data]);
  const fundFlowChart = useMemo(() => fundFlowItems.slice(-20).map((x: Record<string, unknown>) => ({
    label: String(x.date ?? '').slice(5),
    value: Number(x.netInflow ?? 0),
  })), [fundFlowItems]);

  const fundamentalObj = useMemo(() => extractObject(fundamentalQ.data) as Record<string, unknown> | null, [fundamentalQ.data]);
  const newsItems = useMemo(() => extractArray(newsQ.data, 'items', 'news', 'data'), [newsQ.data]);

  const orderBook = useMemo(() => {
    const raw = extractObject(orderBookQ.data);
    const ob = raw.orderBook ? extractObject(raw.orderBook) : raw;
    const bids = Array.isArray(ob.bids) ? ob.bids as Array<{ price: number; volume: number }> : [];
    const asks = Array.isArray(ob.asks) ? (ob.asks as Array<{ price: number; volume: number }>).slice().reverse() : [];
    return { bids, asks };
  }, [orderBookQ.data]);

  const quickLinks = useMemo(() => {
    const c = code.trim();
    if (!c) return [];
    return [
      { label: '资金流向', href: `/fund-flow?code=${c}` },
      { label: '基本面', href: `/fundamental?code=${c}` },
      { label: '技术分析', href: `/technical?code=${c}` },
      { label: '研报公告', href: `/research?code=${c}` },
      { label: '估值分析', href: `/valuation?code=${c}` },
      { label: '情绪分析', href: `/sentiment?code=${c}` },
    ];
  }, [code]);

  // Update page title with stock name
  useEffect(() => {
    if (q) document.title = `${q.name}(${submittedCode}) | AIASK`;
    return () => { document.title = 'AIASK 智能股票分析'; };
  }, [q, submittedCode]);

  const chgColor = Number(q?.changePercent) >= 0 ? 'text-danger' : 'text-success';
  const amplitude = q?.high && q?.low && q?.prevClose
    ? ((Number(q.high) - Number(q.low)) / Number(q.prevClose) * 100).toFixed(2) + '%' : '-';

  return (
    <PageContainer>
      <div className="flex items-center gap-3">
        <h1 className="mb-0">{q ? `${q.name} ${submittedCode}` : '股票详情'}</h1>
        {q && <WatchlistButton code={code.trim()} name={String(q.name ?? '')} size="md" />}
        {quoteQ.isFetching && <span className="text-xs text-text-muted animate-pulse">刷新中...</span>}
        {quoteQ.dataUpdatedAt ? <span className="text-xs text-text-muted">自动刷新: {new Date(quoteQ.dataUpdatedAt).toLocaleTimeString('zh-CN')}</span> : null}
      </div>
      <form onSubmit={onSubmit} className="flex gap-2.5 flex-wrap items-center">
        <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="如 600519" aria-label="股票代码" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
        {codeError ? <span className="text-error text-xs" role="alert">{codeError}</span> : null}
        <select value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="K线周期" className="border border-border rounded px-2 py-1 text-sm">
          <option value="daily">日线</option><option value="weekly">周线</option><option value="monthly">月线</option>
        </select>
        <button type="submit" disabled={loading} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{loading ? '加载中...' : '查询'}</button>
      </form>
      {loading && !q ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      {q && (
        <>
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
              <Link key={lnk.href} href={lnk.href} className="text-xs px-2.5 py-1 rounded-full border border-border text-text-secondary hover:text-primary hover:border-primary transition-colors no-underline">
                {lnk.label} →
              </Link>
            ))}
            {submittedCode && <>
              <Link href={`/paper-trading?code=${submittedCode}`} className="text-xs px-2.5 py-1 rounded-full border border-primary/50 text-primary hover:bg-primary hover:text-white transition-colors no-underline">💹 模拟下单</Link>
              <Link href={`/backtest?code=${submittedCode}`} className="text-xs px-2.5 py-1 rounded-full border border-primary/50 text-primary hover:bg-primary hover:text-white transition-colors no-underline">📊 回测</Link>
              <Link href={`/assistant?code=${submittedCode}`} className="text-xs px-2.5 py-1 rounded-full border border-primary/50 text-primary hover:bg-primary hover:text-white transition-colors no-underline">🤖 AI诊断</Link>
            </>}
          </div>
        </>
      )}

      {/* Tabbed Info Sections */}
      <TabBar tabs={INFO_TABS} active={infoTab} onChange={setInfoTab} />

      {infoTab === 'chart' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">K线图（{submittedPeriod === 'daily' ? '日线' : submittedPeriod === 'weekly' ? '周线' : '月线'}）</h3>
          {candleData.length ? <CandlestickChart data={candleData} height={420} /> : <p className="text-text-secondary text-sm">暂无K线数据</p>}
          {(orderBook.bids.length > 0 || orderBook.asks.length > 0) && (
            <div className="mt-4">
              <h3 className="mt-0">五档盘口</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-text-muted text-xs mb-1 flex justify-between"><span>卖盘</span><span>价格 / 数量</span></div>
                  {orderBook.asks.map((a, i) => (
                    <div key={i} className="flex justify-between py-0.5 text-success">
                      <span>卖{orderBook.asks.length - i}</span>
                      <span>{fmtNum(a.price, 2)} / {fmtAmount(a.volume)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-text-muted text-xs mb-1 flex justify-between"><span>买盘</span><span>价格 / 数量</span></div>
                  {orderBook.bids.map((b, i) => (
                    <div key={i} className="flex justify-between py-0.5 text-danger">
                      <span>买{i + 1}</span>
                      <span>{fmtNum(b.price, 2)} / {fmtAmount(b.volume)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'tech' && (
        <SectionCard tabAttached className="p-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h3 className="mt-0">技术指标</h3>
              {techApi.data ? (() => {
                const payload = unwrapPayload(techApi.data as Record<string, unknown>);
                const rsi = payload.rsi as Record<string, unknown> | undefined;
                const macd = payload.macd as Record<string, unknown> | undefined;
                const kdj = payload.kdj as Record<string, unknown> | undefined;
                const rsiVal = Number(rsi?.value ?? 0);
                const rsiSignal = String(rsi?.signal ?? 'hold');
                const rsiLabel = rsiSignal === 'buy' ? '买入' : rsiSignal === 'sell' ? '卖出' : rsiVal > 70 ? '超买' : rsiVal < 30 ? '超卖' : '中性';
                const rsiColor = rsiVal > 70 ? 'text-danger' : rsiVal < 30 ? 'text-success' : '';
                const macdArr = (macd?.macd ?? macd?.MACD) as number[] | undefined;
                const sigArr = (macd?.signal ?? macd?.Signal) as number[] | undefined;
                const macdLast = macdArr?.length ? macdArr[macdArr.length - 1] : null;
                const sigLast = sigArr?.length ? sigArr[sigArr.length - 1] : null;
                const macdCross = macdLast != null && sigLast != null ? (macdLast > sigLast ? '金叉' : '死叉') : '-';
                const macdCrossColor = macdCross === '金叉' ? 'text-danger' : macdCross === '死叉' ? 'text-success' : '';
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
                    <div className="glass rounded-lg p-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium">RSI(14)</span>
                        <Badge variant={rsiColor.includes('danger') ? 'danger' : rsiColor.includes('success') ? 'success' : 'neutral'}>{rsiLabel}</Badge>
                      </div>
                      <div className={`text-2xl font-bold mt-1 ${rsiColor}`}>{fmtNum(rsiVal, 2)}</div>
                    </div>
                    <div className="glass rounded-lg p-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium">MACD</span>
                        <Badge variant={macdCrossColor.includes('danger') ? 'danger' : macdCrossColor.includes('success') ? 'success' : 'neutral'}>{macdCross}</Badge>
                      </div>
                      <div className="text-sm mt-1 text-text-secondary">
                        DIF: {fmtNum(macdLast, 2)} / DEA: {fmtNum(sigLast, 2)}
                      </div>
                    </div>
                    <div className="glass rounded-lg p-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium">KDJ</span>
                        <Badge variant={kdjColor.includes('danger') ? 'danger' : kdjColor.includes('success') ? 'success' : 'neutral'}>{kdjSignal}</Badge>
                      </div>
                      <div className="text-sm mt-1 text-text-secondary">
                        K: {fmtNum(kLast, 2)} / D: {fmtNum(dLast, 2)} / J: {fmtNum(jLast, 2)}
                      </div>
                    </div>
                  </div>
                );
              })() : <p className="text-text-secondary text-sm">查询股票后显示技术指标</p>}
            </div>
            <div>
              <h3 className="mt-0">K线形态</h3>
              {patternsApi.data ? (() => {
                const raw = unwrapPayload(patternsApi.data as Record<string, unknown>);
                const arr = (Array.isArray(raw.patterns) ? raw.patterns : []) as Record<string, unknown>[];
                return arr.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {arr.map((p, i) => (
                      <Badge key={i} variant={p.bullish ? 'danger' : 'success'}>
                        {String(p.name ?? p.pattern ?? '')} {p.reliability === 'high' ? '★' : ''}
                      </Badge>
                    ))}
                  </div>
                ) : <p className="text-text-secondary text-sm">未检测到形态信号</p>;
              })() : <p className="text-text-secondary text-sm">查询股票后显示形态检测</p>}
            </div>
          </div>
          {sentimentQ.data && (
            <div className="mt-4">
              <h3 className="mt-0">市场情绪</h3>
              <GaugeChart value={sentimentScore || 50} min={0} max={100} title={sentimentScore > 50 ? '偏多' : sentimentScore < 50 ? '偏空' : '中性'} height={200} />
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'fund' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">资金流向（近20日）</h3>
          {fundFlowChart.length > 0 ? (
            <BarChart items={fundFlowChart} height={300} yAxisName="净流入" colorByValue />
          ) : <p className="text-text-secondary text-sm">{fundFlowQ.isFetching ? '加载中...' : fundFlowQ.data ? '暂无资金流向数据' : '查询股票后显示资金流向'}</p>}
          {fundFlowItems.length > 0 && (
            <div className="mt-3 grid grid-cols-3 gap-2">
              <KpiCard title="最近净流入" value={fmtAmount(Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).netInflow ?? 0))}
                change={Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).netInflow ?? 0)} />
              <KpiCard title="主力流入" value={fmtAmount(Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).mainInflow ?? 0))} />
              <KpiCard title="散户流入" value={fmtAmount(Number((fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown>).retailInflow ?? 0))} />
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'basic' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">基本面概览</h3>
          {fundamentalObj && Object.keys(fundamentalObj).length > 0 ? (
            <KpiGrid cols={4}>
              {Object.entries(fundamentalObj).filter(([k]) => !SKIP_KEYS.includes(k)).flatMap(([k, v]) => {
                // Flatten nested objects (e.g. financials: { roe, netProfit })
                if (v && typeof v === 'object' && !Array.isArray(v)) {
                  return Object.entries(v as Record<string, unknown>).map(([sk, sv]) => [sk, sv] as [string, unknown]);
                }
                return [[k, v] as [string, unknown]];
              }).slice(0, 16).map(([k, v]) => {
                const num = Number(v);
                const display = v == null ? '-'
                  : !isNaN(num) && v !== '' ? (Math.abs(num) > 1e6 ? fmtAmount(num) : fmtNum(num, 2))
                    : String(v);
                const labels: Record<string, string> = { roe: 'ROE', netProfit: '净利润', revenue: '营收', debtRatio: '资产负债率', pe: 'PE', pb: 'PB', ps: 'PS', marketCap: '总市值', eps: 'EPS', bps: '每股净资产', totalShares: '总股本', floatShares: '流通股本' };
                return <KpiCard key={k} title={labels[k] ?? k} value={display} />;
              })}
            </KpiGrid>
          ) : <p className="text-text-secondary text-sm">{fundamentalQ.isFetching ? '加载中...' : fundamentalQ.data ? '暂无基本面数据' : '查询股票后显示基本面数据'}</p>}
        </SectionCard>
      )}

      {infoTab === 'news' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">最新资讯</h3>
          {newsItems.length > 0 ? (
            <div className="space-y-3 max-h-[500px] overflow-auto">
              {newsItems.slice(0, 20).map((item: Record<string, unknown>, i: number) => (
                <div key={i} className="py-2 border-b border-border/50">
                  {item.url ? (
                    <a href={String(item.url)} target="_blank" rel="noopener noreferrer" className="font-medium text-sm text-primary hover:underline">{fmt(item.title as string)}</a>
                  ) : (
                    <div className="font-medium text-sm">{fmt(item.title as string)}</div>
                  )}
                  <div className="text-xs text-text-muted mt-0.5">
                    {fmt(item.date as string)} {item.source ? `｜ ${fmt(item.source as string)}` : ''}
                  </div>
                  {item.summary ? <div className="text-xs text-text-secondary mt-1">{String(item.summary).slice(0, 120)}</div> : null}
                </div>
              ))}
            </div>
          ) : <p className="text-text-secondary text-sm">{newsQ.isFetching ? '加载中...' : '查询股票后显示相关资讯'}</p>}
        </SectionCard>
      )}

      {infoTab === 'shares' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">🏦 股本结构</h3>
          {submittedCode ? (
            <StockCapitalPanel code={submittedCode} />
          ) : <p className="text-text-secondary text-sm">查询股票后显示股本数据</p>}
        </SectionCard>
      )}

      {infoTab === 'valuation' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">估值分析</h3>
          {valuationQ.data ? (() => {
            const val = extractObject(valuationQ.data) as Record<string, unknown>;
            const pe = Number(val.pe ?? val.PE ?? val.pe_ttm ?? 0);
            const pb = Number(val.pb ?? val.PB ?? 0);
            const ps = Number(val.ps ?? val.PS ?? 0);
            const pcf = Number(val.pcf ?? val.PCF ?? 0);
            const mktCap = Number(val.marketCap ?? val.market_cap ?? val.total_mv ?? 0);
            const cirMktCap = Number(val.cirMarketCap ?? val.circ_mv ?? 0);
            const peHist = val.pe_percentile ?? val.pePercentile;
            const pbHist = val.pb_percentile ?? val.pbPercentile;
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
          })() : <p className="text-text-secondary text-sm">{valuationQ.isFetching ? '加载中...' : '查询股票后显示估值数据'}</p>}
        </SectionCard>
      )}

      {infoTab === 'ai' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">🤖 AI 智能诊断</h3>
          {submittedCode ? (
            <AIDiagnosisPanel code={submittedCode} />
          ) : <p className="text-text-secondary text-sm">请先查询股票代码</p>}
        </SectionCard>
      )}

      {infoTab === 'peers' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">🏭 同行业对比</h3>
          {submittedCode ? (
            <PeerComparisonTable code={submittedCode} />
          ) : <p className="text-text-secondary text-sm">查询股票后显示同行对比</p>}
        </SectionCard>
      )}
    </PageContainer>
  );
}
