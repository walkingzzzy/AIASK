'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, TabBar } from '@/components/ui';
import { QuickAction, QuickActionGrid } from '@/components/ui/quick-action';
import { CandlestickChart, BarChart, GaugeChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, fmtAmount, extractArray, extractObject } from '@/lib/data-utils';
import { WatchlistButton } from '@/components/watchlist-button';
import { tradingInterval } from '@/lib/trading-hours';
import { fmt } from '@/lib/api';
import Link from 'next/link';

type Period = 'daily' | 'weekly' | 'monthly';
type QuoteData = { quote?: import('@aiask/shared-types').NormalizedQuote; meta?: { cache?: unknown; fetchedAt?: string } };
type KlineData = { kline?: import('@aiask/shared-types').NormalizedKlinePoint[]; meta?: { cache?: unknown; fetchedAt?: string } };

export default function StockPage() {
  const { code, setCode, codeError, validate } = useStockCode('600519');
  const [period, setPeriod] = useState<Period>('daily');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedPeriod, setSubmittedPeriod] = useState<Period>('daily');

  const quoteQ = useApiQuery<QuoteData>(
    submittedCode ? `/market/quote?code=${encodeURIComponent(submittedCode)}` : null,
    { refetchInterval: tradingInterval(30_000) },
  );
  const klineQ = useApiQuery<KlineData>(
    submittedCode ? `/market/kline?code=${encodeURIComponent(submittedCode)}&period=${submittedPeriod}&limit=250` : null,
  );

  const techApi = useApiMutation<Record<string, unknown>>();
  const patternsApi = useApiMutation<Record<string, unknown>>();

  const sentimentQ = useApiQuery<Record<string, unknown>>(
    submittedCode ? `/sentiment/stock?code=${encodeURIComponent(submittedCode)}` : null,
  );
  const fundFlowQ = useApiQuery<unknown>(
    submittedCode ? `/fund-flow/stock?code=${encodeURIComponent(submittedCode)}` : null,
  );
  const fundamentalQ = useApiQuery<unknown>(
    submittedCode ? `/fundamental/overview?code=${encodeURIComponent(submittedCode)}` : null,
  );
  const newsQ = useApiQuery<unknown>(
    submittedCode ? `/research/stock-news?code=${encodeURIComponent(submittedCode)}` : null,
  );
  const [infoTab, setInfoTab] = useState<string>('chart');

  const INFO_TABS = useMemo(() => [
    { key: 'chart', label: 'K线图' },
    { key: 'tech', label: '技术面' },
    { key: 'fund', label: '资金流' },
    { key: 'basic', label: '基本面' },
    { key: 'news', label: '资讯' },
  ] as const, []);

  function doFetch(c: string) {
    techApi.trigger('/technical/indicators', { method: 'POST' }, { code: c, indicators: ['RSI', 'MACD', 'KDJ'] });
    patternsApi.trigger('/technical/patterns', { method: 'POST' }, { code: c });
  }

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

  const q = quoteQ.data?.quote;
  const sentimentScore = Number(sentimentQ.data?.score ?? sentimentQ.data?.sentiment_score ?? 0);
  const SKIP_KEYS = ['tool', 'meta', 'code', 'sourceTool', 'result', 'traceId', 'success', 'data'];

  const fundFlowItems = useMemo(() => extractArray(fundFlowQ.data, 'flows'), [fundFlowQ.data]);
  const fundFlowChart = useMemo(() => fundFlowItems.slice(-20).map((x: Record<string, unknown>) => ({
    label: String(x.date ?? '').slice(5),
    value: Number(x.netInflow ?? 0),
  })), [fundFlowItems]);

  const fundamentalObj = useMemo(() => extractObject(fundamentalQ.data) as Record<string, unknown> | null, [fundamentalQ.data]);
  const newsItems = useMemo(() => extractArray(newsQ.data, 'items', 'news', 'data'), [newsQ.data]);

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

  return (
    <PageContainer>
      <div className="flex items-center gap-3">
        <h1 className="mb-0">股票详情</h1>
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
            <KpiCard title="名称" value={String(q.name ?? '-')} />
            <KpiCard title="现价" value={fmtNum(Number(q.price))} />
            <KpiCard title="涨跌幅" value={fmtPct(Number(q.changePercent))} change={Number(q.changePercent)} />
            <KpiCard title="涨跌额" value={fmtNum(Number(q.change), 2)} />
            <KpiCard title="成交量" value={fmtNum(Number(q.volume), 0)} />
            <KpiCard title="成交额" value={fmtAmount(Number(q.amount))} />
            <KpiCard title="最高/最低" value={`${fmtNum(Number(q.high))} / ${fmtNum(Number(q.low))}`} />
            <KpiCard title="开盘/昨收" value={`${fmtNum(Number(q.open))} / ${fmtNum(Number(q.prevClose))}`} />
          </KpiGrid>

          {/* Quick Navigation */}
          <div className="flex gap-2 flex-wrap mt-3">
            {quickLinks.map((lnk) => (
              <Link key={lnk.href} href={lnk.href} className="text-xs px-2.5 py-1 rounded-full border border-border text-text-secondary hover:text-primary hover:border-primary transition-colors no-underline">
                {lnk.label} →
              </Link>
            ))}
          </div>
        </>
      )}

      {/* Next Step Actions */}
      {submittedCode && (
        <QuickActionGrid cols={3} className="mt-4">
          <QuickAction href={`/paper-trading?code=${submittedCode}`} icon="💹" title="去模拟下单" description="用模拟资金测试交易策略" />
          <QuickAction href={`/backtest?code=${submittedCode}`} icon="📊" title="加入回测" description="用历史数据验证策略表现" />
          <QuickAction href={`/assistant?code=${submittedCode}`} icon="🤖" title="AI 诊断" description="智能分析买卖建议" />
        </QuickActionGrid>
      )}

      {/* Tabbed Info Sections */}
      <TabBar tabs={INFO_TABS} active={infoTab} onChange={setInfoTab} />

      {infoTab === 'chart' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">K线图（{period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'}）</h3>
          {candleData.length ? <CandlestickChart data={candleData} height={420} /> : <p className="text-text-secondary text-sm">暂无K线数据</p>}
        </SectionCard>
      )}

      {infoTab === 'tech' && (
        <SectionCard tabAttached className="p-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h3 className="mt-0">技术指标</h3>
              {techApi.data ? (
                <KpiGrid cols={3}>
                  {Object.entries((techApi.data.result as Record<string, unknown>) ?? techApi.data).filter(([k]) => !SKIP_KEYS.includes(k)).map(([k, v]) => (
                    <KpiCard key={k} title={k.toUpperCase()} value={v != null && typeof v === 'number' ? fmtNum(v, 2) : typeof v === 'string' ? v : '-'} />
                  ))}
                </KpiGrid>
              ) : <p className="text-text-secondary text-sm">查询股票后显示技术指标</p>}
            </div>
            <div>
              <h3 className="mt-0">K线形态</h3>
              {patternsApi.data ? (
                <div className="flex flex-wrap gap-2">
                  {Object.entries((patternsApi.data.result as Record<string, unknown>) ?? patternsApi.data).filter(([k]) => !SKIP_KEYS.includes(k)).map(([k, v]) => {
                    const detected = v === true || v === 1 || String(v).toLowerCase() === 'true';
                    return <Badge key={k} variant={detected ? 'danger' : 'neutral'}>{k}{detected ? ' ✓' : ''}</Badge>;
                  })}
                  {Object.entries((patternsApi.data.result as Record<string, unknown>) ?? patternsApi.data).filter(([k]) => !SKIP_KEYS.includes(k)).length === 0 && (
                    <p className="text-text-secondary text-sm">未检测到形态信号</p>
                  )}
                </div>
              ) : <p className="text-text-secondary text-sm">查询股票后显示形态检测</p>}
            </div>
          </div>
          {sentimentScore > 0 && (
            <div className="mt-4">
              <h3 className="mt-0">市场情绪</h3>
              <GaugeChart value={sentimentScore} min={0} max={100} title="情绪指数" height={200} />
            </div>
          )}
        </SectionCard>
      )}

      {infoTab === 'fund' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">资金流向（近20日）</h3>
          {fundFlowChart.length > 0 ? (
            <BarChart items={fundFlowChart} height={300} yAxisName="净流入" colorByValue />
          ) : <p className="text-text-secondary text-sm">{fundFlowQ.isFetching ? '加载中...' : '查询股票后显示资金流向'}</p>}
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
              {Object.entries(fundamentalObj).filter(([k]) => !SKIP_KEYS.includes(k)).slice(0, 16).map(([k, v]) => {
                const num = Number(v);
                const display = !isNaN(num) && v !== '' && v !== null
                  ? (Math.abs(num) > 1e6 ? fmtAmount(num) : fmtNum(num, 2))
                  : String(v ?? '-');
                return <KpiCard key={k} title={k} value={display} />;
              })}
            </KpiGrid>
          ) : <p className="text-text-secondary text-sm">{fundamentalQ.isFetching ? '加载中...' : '查询股票后显示基本面数据'}</p>}
        </SectionCard>
      )}

      {infoTab === 'news' && (
        <SectionCard tabAttached className="p-3">
          <h3 className="mt-0">最新资讯</h3>
          {newsItems.length > 0 ? (
            <div className="space-y-3 max-h-[500px] overflow-auto">
              {newsItems.slice(0, 20).map((item: Record<string, unknown>, i: number) => (
                <div key={i} className="py-2 border-b border-border/50">
                  <div className="font-medium text-sm">{fmt(item.title as string)}</div>
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
    </PageContainer>
  );
}
