'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

type BacktestResult = {
  total_return?: number; sharpe_ratio?: number; max_drawdown?: number;
  win_rate?: number; trades_count?: number; final_capital?: number;
  initial_capital?: number; equity_curve?: number[];
  slippage_model_note?: string; trades?: Record<string, unknown>[];
  [k: string]: unknown;
};

export default function BacktestPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [strategy, setStrategy] = useState('ma_cross');
  const [formError, setFormError] = useState<string | null>(null);
  const backtestApi = useApiMutation<{ artifactId?: string; backtestId?: unknown }>();
  const metricsApi = useApiMutation<{ metrics?: BacktestResult }>();
  const benchmarkApi = useApiMutation<{ kline?: Array<Record<string, number>> }>();

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, { code: trimmedCode, strategy });
      const aid = String(data?.artifactId ?? '');
      if (aid) {
        metricsApi.trigger(`/backtest/metrics?artifactId=${encodeURIComponent(aid)}`);
        benchmarkApi.trigger('/market/kline?code=000300&period=daily&limit=500');
      }
    } catch { /* captured */ }
  }

  const m = metricsApi.data?.metrics;
  const loading = backtestApi.isPending || metricsApi.isPending;
  const error = formError || backtestApi.error || metricsApi.error;

  // Equity curve data
  const equityCurve = useMemo(() => m?.equity_curve ?? [], [m]);
  const equityCategories = useMemo(() => equityCurve.map((_, i) => `${i}`), [equityCurve]);

  // Normalize to NAV (starting at 1.0)
  const navSeries = useMemo(() => {
    if (!equityCurve.length) return [];
    const base = equityCurve[0] || 1;
    return equityCurve.map((v) => +((v / base)).toFixed(4));
  }, [equityCurve]);

  // Benchmark NAV (沪深300 normalized to 1.0)
  const benchmarkNav = useMemo(() => {
    const raw = benchmarkApi.data?.kline;
    if (!raw?.length || !equityCurve.length) return [];
    const closes = raw.map((k) => k.close ?? k.收盘 ?? 0).filter(Boolean);
    if (!closes.length) return [];
    const base = closes[0] || 1;
    return closes.slice(0, equityCurve.length).map((v) => +(v / base).toFixed(4));
  }, [benchmarkApi.data, equityCurve.length]);

  // Daily returns
  const dailyReturns = useMemo(() => {
    if (equityCurve.length < 2) return [];
    return equityCurve.slice(1).map((v, i) => {
      const prev = equityCurve[i];
      return prev > 0 ? +((v - prev) / prev * 100).toFixed(3) : 0;
    });
  }, [equityCurve]);

  // Drawdown curve
  const drawdownSeries = useMemo(() => {
    if (!equityCurve.length) return [];
    let peak = equityCurve[0];
    return equityCurve.map((v) => {
      if (v > peak) peak = v;
      return peak > 0 ? +(((v - peak) / peak) * 100).toFixed(3) : 0;
    });
  }, [equityCurve]);

  const trades = useMemo(() => (m?.trades ?? []) as Record<string, unknown>[], [m]);

  return (
    <PageContainer>
      <h1>回测分析</h1>
      <form onSubmit={runBacktest} className="flex gap-2 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} />
        <input value={strategy} onChange={(e) => setStrategy(e.target.value)} placeholder="策略，如 ma_cross" className="w-[180px] px-2 py-1 border border-border rounded text-sm" />
        <button type="submit" disabled={loading} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{loading ? '运行中...' : '运行回测'}</button>
      </form>
      {loading ? <LoadingState text="回测运行中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      {m && (
        <>
          <KpiGrid cols={5}>
            <KpiCard title="总收益" value={fmtPct(Number(m.total_return))} change={Number(m.total_return)} />
            <KpiCard title="夏普比率" value={fmtNum(Number(m.sharpe_ratio), 2)} />
            <KpiCard title="最大回撤" value={fmtPct(Number(m.max_drawdown))} />
            <KpiCard title="胜率" value={fmtPct(Number(m.win_rate))} />
            <KpiCard title="交易次数" value={m.trades_count ?? '-'} />
          </KpiGrid>

          {equityCurve.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">净值曲线</h3>
              <LineChart
                categories={equityCategories}
                series={[
                  { name: '策略净值', data: navSeries, areaStyle: true, color: '#1a73e8' },
                  ...(benchmarkNav.length ? [{ name: '沪深300', data: benchmarkNav, color: '#9ca3af' }] : []),
                ]}
                height={320}
                yAxisName="净值"
              />
            </SectionCard>
          )}

          {drawdownSeries.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">回撤曲线</h3>
              <LineChart
                categories={equityCategories}
                series={[
                  { name: '回撤 (%)', data: drawdownSeries, areaStyle: true, color: '#ef4444' },
                ]}
                height={200}
                yAxisName="回撤 %"
              />
            </SectionCard>
          )}

          {dailyReturns.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">每日收益率</h3>
              <LineChart
                categories={equityCategories.slice(1)}
                series={[
                  { name: '日收益率 (%)', data: dailyReturns, type: 'bar', color: '#3b82f6' },
                ]}
                height={200}
                yAxisName="收益率 %"
              />
            </SectionCard>
          )}

          {trades.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">交易明细</h3>
              <DataTable rows={trades} pageSize={10} onExport={() => exportCSV(trades, 'backtest-trades')} />
            </SectionCard>
          )}

          {m.slippage_model_note && (
            <p className="text-text-secondary text-xs mt-2">{m.slippage_model_note}</p>
          )}
        </>
      )}
    </PageContainer>
  );
}
