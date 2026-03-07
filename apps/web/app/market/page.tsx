'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { PageContainer, TabBar, SectionCard, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
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
import type { CacheMeta, NormalizedQuote, NormalizedKlinePoint, NormalizedOrderBook } from '@aiask/shared-types';

type Period = 'daily' | 'weekly' | 'monthly';
type QuoteData = { quote?: NormalizedQuote; tool?: string; meta?: CacheMeta };
type KlineData = { kline?: NormalizedKlinePoint[]; tool?: string; meta?: CacheMeta };
type ObData = { orderBook?: NormalizedOrderBook; tool?: string; meta?: CacheMeta };
type MarketTab = 'main' | 'limitup' | 'blocks' | 'trade' | 'index' | 'minute' | 'search';

const TABS = [
  { key: 'main', label: '基础行情' },
  { key: 'limitup', label: '涨停板' },
  { key: 'blocks', label: '板块' },
  { key: 'trade', label: '逐笔' },
  { key: 'index', label: '指数' },
  { key: 'minute', label: '分时' },
  { key: 'search', label: '搜索' },
] as const;

export default function MarketPage() {
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get('tab') as MarketTab) || 'main';
  const initialBlock = searchParams.get('block') || '';

  const { code, setCode, codeError, validate, resolvedCode } = useStockCode();
  const [period, setPeriod] = useState<Period>('daily');
  const [activeTab, setActiveTab] = useState<MarketTab>(initialTab);
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>('daily');

  // 自动查询：URL 或 Store 携带了有效代码时自动触发
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setSubmittedCode(resolvedCode);
    }
  }, [resolvedCode]);

  const quoteQ = useApiQuery<QuoteData>(
    submittedCode ? `/market/quote?code=${encodeURIComponent(submittedCode)}` : null,
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
    submittedCode ? `/market/kline?code=${encodeURIComponent(submittedCode)}&period=${submittedPeriod}` : null,
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
    submittedCode ? `/market/order-book?code=${encodeURIComponent(submittedCode)}` : null,
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

  const limitUpQ = useApiQuery<unknown>(limitUpPath, {
    parse: (raw) => ensureRecordOrArray(raw, '涨停列表'),
  });
  const limitUpStatsQ = useApiQuery<unknown>(limitUpStatsPath, {
    parse: (raw) => ensureRecord(raw, '涨停统计详情'),
  });
  const blocksQ = useApiQuery<unknown>(blocksPath, {
    parse: (raw) => ensureRecordOrArray(raw, '板块列表'),
  });
  const tradeQ = useApiQuery<unknown>(tradePath, {
    parse: (raw) => ensureRecordOrArray(raw, '逐笔成交'),
  });
  const indexQuoteQ = useApiQuery<unknown>(indexPath, {
    parse: (raw) => ensureRecord(raw, '指数行情'),
  });
  const minuteKlineQ = useApiQuery<unknown>(minutePath, {
    parse: (raw) => ensureRecordOrArray(raw, '分时K线'),
  });
  const searchQ = useApiQuery<unknown>(searchPath, {
    parse: (raw) => ensureRecordOrArray(raw, '股票搜索结果'),
  });
  const stockListQ = useApiQuery<unknown>(stockListPath, {
    parse: (raw) => ensureRecordOrArray(raw, '股票列表'),
  });
  const blockStocksQ = useApiQuery<unknown>(blockStocksPath, {
    parse: (raw) => ensureRecordOrArray(raw, '板块成分股'),
  });
  const batchQuotes = useApiMutation<unknown>({
    parse: (raw) => ensureRecordOrArray(raw, '批量行情'),
  });

  const [indexCode, setIndexCode] = useState('000001');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [minutePeriod, setMinutePeriod] = useState('5m');
  const [blockCode, setBlockCode] = useState(initialBlock);
  const [batchCodes, setBatchCodes] = useState('');

  const tabPending = limitUpQ.isFetching || blocksQ.isFetching || tradeQ.isFetching || indexQuoteQ.isFetching || minuteKlineQ.isFetching || searchQ.isFetching || stockListQ.isFetching || blockStocksQ.isFetching || batchQuotes.isPending || limitUpStatsQ.isFetching;
  const tabError = limitUpQ.error || blocksQ.error || tradeQ.error || indexQuoteQ.error || minuteKlineQ.error || searchQ.error || blockStocksQ.error || batchQuotes.error || limitUpStatsQ.error;

  const loading = quoteQ.isFetching || klineQ.isFetching || obQ.isFetching;

  // Auto-load limit-up data when switching to that tab
  useEffect(() => {
    if (activeTab === 'limitup' && !limitUpPath) {
      setLimitUpPath('/market/limit-up');
      setLimitUpStatsPath('/market/limit-up-stats');
    }
  }, [activeTab, limitUpPath]);

  // Auto-load blocks + constituent stocks when arriving from homepage with block param
  useEffect(() => {
    if (activeTab === 'blocks' && !blocksPath) {
      setBlocksPath('/market/blocks?blockType=industry');
      if (initialBlock) {
        setBlockStocksPath(`/market/block-stocks?blockCode=${encodeURIComponent(initialBlock)}`);
      }
    }
  }, [activeTab, blocksPath, initialBlock]);

  // Auto-load index quote when switching to index tab
  useEffect(() => {
    if (activeTab === 'index' && !indexPath) {
      setIndexPath(`/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim())}`);
    }
  }, [activeTab, indexPath, indexCode]);

  // Auto-load minute kline when switching to minute tab with a valid code
  useEffect(() => {
    const c = resolvedCode || submittedCode;
    if (activeTab === 'minute' && !minutePath && c) {
      setMinutePath(`/market/minute-kline?code=${encodeURIComponent(c)}&period=${minutePeriod}`);
    }
  }, [activeTab, minutePath, resolvedCode, submittedCode, minutePeriod]);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const c = code.trim();
    if (c === submittedCode && period === submittedPeriod) {
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
      <form onSubmit={onSubmit} className="flex gap-2.5 flex-wrap items-center">
        <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="如 600519" aria-label="股票代码" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
        {codeError ? <span className="text-error text-xs" role="alert">{codeError}</span> : null}
        <select value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="K线周期" className="border border-border rounded px-2 py-1 text-sm">
          <option value="daily">日线</option><option value="weekly">周线</option><option value="monthly">月线</option>
        </select>
        <button type="submit" disabled={loading} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{loading ? '加载中...' : '查询'}</button>
      </form>
      {quoteQ.error ? <p className="text-error">降级提示：{quoteQ.error}</p> : null}
      <div className="mt-2.5 text-text-secondary text-sm">
        更新：{quoteQ.dataUpdatedAt ? new Date(quoteQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'}
      </div>
      <details className="text-xs text-text-muted mt-1">
        <summary className="cursor-pointer">缓存详情</summary>
        <span>行情：{cacheText(quoteCache)} ｜ K线：{cacheText(klineCache)} ｜ 盘口：{cacheText(obCache)}</span>
      </details>

      {/* ── Tab bar moved immediately after cache info for quick access ── */}
      <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />
      {tabError ? <p className="text-error text-sm mt-1">{tabError}</p> : null}

      {/* ── 基础行情 cards always shown below the tab bar ── */}
      <SectionCard className="mt-4 p-3">
        <h3 className="mt-0">K线图（{period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'}）</h3>
        {candleData.length ? <CandlestickChart data={candleData} height={360} /> : <p>暂无K线数据</p>}
      </SectionCard>

      <SectionCard className="mt-4 p-3">
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

      <SectionCard className="mt-4 p-3">
        <h3 className="mt-0">实时行情摘要</h3>
        {quote?.quote ? (() => {
          const q = quote.quote;
          const chg = Number(q.change ?? 0);
          const chgPct = Number(q.changePercent ?? 0);
          const clr = chg >= 0 ? 'text-danger' : 'text-success';
          return (
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div className="flex items-center gap-1">股票：<StockLink code={String(q.code)} name={String(q.name ?? '')} /><WatchlistButton code={String(q.code)} name={String(q.name ?? '')} /></div>
              <div>现价：<span className={clr}>{fmtNum(q.price as number | null, 2)}</span></div>
              <div>涨跌：<span className={clr}>{fmtNum(q.change as number | null, 2)}</span></div>
              <div>涨跌幅：<span className={clr}>{fmtPct(q.changePercent as number | null)}</span></div>
              <div>成交量：{fmtAmount(q.volume as number | null)}</div>
              <div>成交额：{fmtAmount(q.amount as number | null)}</div>
              <div>最高：{fmtNum(q.high as number | null, 2)}</div>
              <div>最低：{fmtNum(q.low as number | null, 2)}</div>
              <div>开盘：{fmtNum(q.open as number | null, 2)}</div>
              <div>昨收：{fmtNum(q.prevClose as number | null, 2)}</div>
            </div>);
        })() : <p>暂无行情数据</p>}
      </SectionCard>

      {activeTab === 'limitup' ? (
        <SectionCard tabAttached>
          <button type="button" disabled={tabPending} onClick={() => {
            if (limitUpPath) limitUpQ.refetch(); else setLimitUpPath('/market/limit-up');
            if (limitUpStatsPath) limitUpStatsQ.refetch(); else setLimitUpStatsPath('/market/limit-up-stats');
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
          ]} maxHeight={400} onExport={() => exportCSV(limitUpRows, 'limit-up')} /> : null}
        </SectionCard>
      ) : null}
      {activeTab === 'blocks' ? (
        <SectionCard tabAttached>
          <button type="button" disabled={tabPending} onClick={() => {
            if (blocksPath) blocksQ.refetch(); else setBlocksPath('/market/blocks?blockType=industry');
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
              if (p === blockStocksPath) blockStocksQ.refetch(); else setBlockStocksPath(p);
            }
          }} />
            : (!tabPending && !blocksQ.error ? <p className="text-text-muted text-sm mt-3 text-center">点击"加载行业板块"查看板块行情，可点击行搜索成分股</p> : null)}
          <div className="flex gap-2 items-center mt-2">
            <input value={blockCode} onChange={(e) => setBlockCode(e.target.value)} placeholder="板块代码" aria-label="板块代码" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              const p = `/market/block-stocks?blockCode=${encodeURIComponent(blockCode.trim())}`;
              if (p === blockStocksPath) blockStocksQ.refetch(); else setBlockStocksPath(p);
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
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="股票代码" aria-label="股票代码" className="w-[140px] px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              if (!validate()) return;
              const p = `/market/trade-details?code=${encodeURIComponent(code.trim())}`;
              if (p === tradePath) tradeQ.refetch(); else setTradePath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '查询逐笔明细'}</button>
          </div>
          {tradeRows.length ? <DataTable rows={tradeRows} columns={tradeColumns} maxHeight={400} onExport={() => exportCSV(tradeRows, 'trade-details')} />
            : (!tabPending && !tradeQ.error ? <p className="text-text-muted text-sm mt-3 text-center">输入股票代码，点击"查询逐笔明细"查看实时成交记录</p> : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'index' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={indexCode} onChange={(e) => setIndexCode(e.target.value)} placeholder="指数代码 如 000001" aria-label="指数代码" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
            <button type="button" disabled={tabPending} onClick={() => {
              const p = `/market/index-quote?indexCode=${encodeURIComponent(indexCode.trim())}`;
              if (p === indexPath) indexQuoteQ.refetch(); else setIndexPath(p);
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
          ) : (!tabPending && !indexQuoteQ.error ? <p className="text-text-muted text-sm mt-3 text-center">输入指数代码，点击"查询指数行情"</p> : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'minute' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="股票代码" aria-label="股票代码" className="w-[140px] px-2 py-1 border border-border rounded text-sm" />
            <select value={minutePeriod} onChange={(e) => setMinutePeriod(e.target.value)} aria-label="分时周期" className="border border-border rounded px-2 py-1 text-sm">
              <option value="1m">1分钟</option><option value="5m">5分钟</option><option value="15m">15分钟</option><option value="30m">30分钟</option><option value="60m">60分钟</option>
            </select>
            <button type="button" disabled={tabPending} onClick={() => {
              if (!validate()) return;
              const p = `/market/minute-kline?code=${encodeURIComponent(code.trim())}&period=${minutePeriod}`;
              if (p === minutePath) minuteKlineQ.refetch(); else setMinutePath(p);
            }} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{tabPending ? '加载中...' : '查询分时'}</button>
          </div>
          {minuteCandleData.length ? <CandlestickChart data={minuteCandleData} height={360} />
            : (!tabPending && !minuteKlineQ.error ? <p className="text-text-muted text-sm mt-3 text-center">选择周期并点击"查询分时"加载分钟级 K 线</p> : null)}
        </SectionCard>
      ) : null}

      {activeTab === 'search' ? (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <input value={searchKeyword} onChange={(e) => setSearchKeyword(e.target.value)} placeholder="搜索股票" aria-label="搜索关键词" className="w-[200px] px-2 py-1 border border-border rounded text-sm" />
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
          ]} maxHeight={300} onExport={() => exportCSV(searchRows, 'search-results')} searchable /> : null}
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
            <input value={batchCodes} onChange={(e) => setBatchCodes(e.target.value)} placeholder="批量代码，逗号分隔" aria-label="批量股票代码" className="w-[300px] px-2 py-1 border border-border rounded text-sm" />
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

