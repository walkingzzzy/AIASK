'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid } from '@/components/ui';
import { CandlestickChart, LineChart, GaugeChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import type { NormalizedQuote, NormalizedKlinePoint, Envelope } from '@aiask/shared-types';
import { authedFetch, cacheText } from '@/lib/api';

type Period = 'daily' | 'weekly' | 'monthly';
type QuoteData = { quote?: NormalizedQuote; meta?: { cache?: unknown; fetchedAt?: string } };
type KlineData = { kline?: NormalizedKlinePoint[]; meta?: { cache?: unknown; fetchedAt?: string } };

export default function StockPage() {
  const { code, setCode, codeError, validate } = useStockCode('600519');
  const [period, setPeriod] = useState<Period>('daily');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [kline, setKline] = useState<KlineData | null>(null);

  const techApi = useApiMutation<Record<string, unknown>>();
  const sentimentApi = useApiMutation<Record<string, unknown>>();

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const c = code.trim();
    setLoading(true);
    setError(null);
    try {
      const [q, k] = await Promise.all([
        authedFetch(`/market/quote?code=${encodeURIComponent(c)}`),
        authedFetch(`/market/kline?code=${encodeURIComponent(c)}&period=${period}&limit=250`),
      ]);
      setQuote(((await q.json()) as Envelope<QuoteData>).data ?? null);
      setKline(((await k.json()) as Envelope<KlineData>).data ?? null);
      techApi.trigger(`/technical/indicators?code=${encodeURIComponent(c)}&indicators=RSI,MACD,KDJ`);
      sentimentApi.trigger(`/sentiment/stock?code=${encodeURIComponent(c)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败');
    } finally { setLoading(false); }
  }

  const candleData = useMemo(() => (kline?.kline ?? []).map((x) => ({
    date: x.date.slice(0, 10), open: x.open, close: x.close, low: x.low, high: x.high, volume: x.volume,
  })), [kline]);

  const q = quote?.quote;
  const sentimentScore = Number(sentimentApi.data?.score ?? sentimentApi.data?.sentiment_score ?? 0);

  return (
    <PageContainer>
      <h1>股票详情</h1>
      <form onSubmit={onSubmit} className="flex gap-2.5 flex-wrap items-center">
        <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} placeholder="如 600519" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
        {codeError ? <span className="text-error text-xs">{codeError}</span> : null}
        <select value={period} onChange={(e) => setPeriod(e.target.value as Period)} className="border border-border rounded px-2 py-1 text-sm">
          <option value="daily">日线</option><option value="weekly">周线</option><option value="monthly">月线</option>
        </select>
        <button type="submit" disabled={loading} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{loading ? '加载中...' : '查询'}</button>
      </form>
      {loading ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      {q && (
        <KpiGrid cols={4}>
          <KpiCard title="现价" value={fmtNum(Number(q.price))} />
          <KpiCard title="涨跌幅" value={fmtPct(Number(q.changePercent))} change={Number(q.changePercent)} />
          <KpiCard title="成交额" value={fmtAmount(Number(q.amount))} />
          <KpiCard title="最高/最低" value={`${fmtNum(Number(q.high))} / ${fmtNum(Number(q.low))}`} />
        </KpiGrid>
      )}

      <SectionCard className="mt-4 p-3">
        <h3 className="mt-0">K线图（{period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'}）</h3>
        {candleData.length ? <CandlestickChart data={candleData} height={420} /> : <p className="text-text-secondary text-sm">暂无K线数据</p>}
      </SectionCard>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {techApi.data && (
          <SectionCard className="p-3">
            <h3 className="mt-0">技术指标</h3>
            <KpiGrid cols={3}>
              {Object.entries(techApi.data).filter(([k]) => !['tool', 'meta', 'code'].includes(k)).map(([k, v]) => (
                <KpiCard key={k} title={k.toUpperCase()} value={v != null ? fmtNum(Number(v), 2) : '-'} />
              ))}
            </KpiGrid>
          </SectionCard>
        )}
        {sentimentScore > 0 && (
          <SectionCard className="p-3">
            <h3 className="mt-0">市场情绪</h3>
            <GaugeChart value={sentimentScore} min={0} max={100} title="情绪指数" height={200} />
          </SectionCard>
        )}
      </div>
    </PageContainer>
  );
}
