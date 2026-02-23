'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, fmtAmount, extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';

type BacktestResult = {
  total_return?: number; sharpe_ratio?: number; max_drawdown?: number;
  win_rate?: number; trades_count?: number; final_capital?: number;
  initial_capital?: number; equity_curve?: number[];
  slippage_model_note?: string; trades?: Record<string, unknown>[];
  profitFactor?: number; profit_factor?: number;
  [k: string]: unknown;
};

type HistoryEntry = {
  code: string; strategy: string; totalReturn: number; sharpe: number;
  maxDrawdown: number; winRate: number; ts: number;
};

export default function BacktestPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [strategy, setStrategy] = useState('ma_cross');
  const [formError, setFormError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const backtestApi = useApiMutation<{ artifactId?: string; backtestId?: unknown }>();
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const metricsQ = useApiQuery<{ result?: { data?: BacktestResult }; metrics?: BacktestResult; [k: string]: unknown }>(
    artifactId ? `/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}` : null,
  );
  const benchmarkQ = useApiQuery<{ kline?: Array<Record<string, number>> }>(
    artifactId ? '/market/kline?code=000300&period=daily&limit=500' : null,
  );

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, { code: trimmedCode, strategy });
      const aid = String(data?.artifactId ?? '');
      if (aid) setArtifactId(aid);
    } catch { /* captured */ }
  }

  const m = metricsQ.data?.result?.data ?? metricsQ.data?.metrics ?? metricsQ.data as BacktestResult | undefined;
  const loading = backtestApi.isPending || metricsQ.isFetching;
  const error = formError || backtestApi.error || metricsQ.error;

  // Save to history when new result arrives
  useMemo(() => {
    if (!m || !m.total_return) return;
    const entry: HistoryEntry = {
      code: trimmedCode, strategy, totalReturn: Number(m.total_return ?? 0),
      sharpe: Number(m.sharpe_ratio ?? 0), maxDrawdown: Number(m.max_drawdown ?? 0),
      winRate: Number(m.win_rate ?? 0), ts: Date.now(),
    };
    setHistory((prev) => {
      const dup = prev.find((h) => h.code === entry.code && h.strategy === entry.strategy && Math.abs(h.ts - entry.ts) < 5000);
      if (dup) return prev;
      return [entry, ...prev].slice(0, 20);
    });
  }, [m, trimmedCode, strategy]);

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
    const raw = benchmarkQ.data?.kline;
    if (!raw?.length || !equityCurve.length) return [];
    const closes = raw.map((k) => k.close ?? k.收盘 ?? 0).filter(Boolean);
    if (!closes.length) return [];
    const base = closes[0] || 1;
    return closes.slice(0, equityCurve.length).map((v) => +(v / base).toFixed(4));
  }, [benchmarkQ.data, equityCurve.length]);

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
          <KpiGrid cols={4}>
            <KpiCard title="总收益" value={fmtPct(Number(m.total_return))} change={Number(m.total_return)} />
            <KpiCard title="夏普比率" value={fmtNum(Number(m.sharpe_ratio), 2)} />
            <KpiCard title="最大回撤" value={fmtPct(Number(m.max_drawdown))} />
            <KpiCard title="胜率" value={fmtPct(Number(m.win_rate))} />
            <KpiCard title="交易次数" value={m.trades_count ?? '-'} />
            <KpiCard title="初始资金" value={fmtAmount(Number(m.initial_capital))} />
            <KpiCard title="最终资金" value={fmtAmount(Number(m.final_capital))} />
            <KpiCard title="盈亏比" value={fmtNum(Number(m.profitFactor ?? m.profit_factor), 2)} />
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
              <DataTable rows={trades} columns={[
                { key: 'date', label: '日期', render: (v: unknown, row: Record<string, unknown>) => String(v ?? row.entry_date ?? row.trade_date ?? '-').slice(0, 10) },
                { key: 'type', label: '方向', render: (v: unknown, row: Record<string, unknown>) => {
                  const d = String(v ?? row.direction ?? row.side ?? '');
                  const isBuy = /buy|买|long/i.test(d);
                  return <Badge variant={isBuy ? 'danger' : 'success'}>{d || '-'}</Badge>;
                }},
                { key: 'price', label: '价格', align: 'right' as const, render: (v: unknown, row: Record<string, unknown>) => fmtNum((v ?? row.entry_price) as number, 2) },
                { key: 'exit_price', label: '平仓价', align: 'right' as const, render: (v: unknown) => v != null ? fmtNum(v as number, 2) : '-' },
                { key: 'shares', label: '数量', align: 'right' as const, render: (v: unknown, row: Record<string, unknown>) => fmtNum((v ?? row.quantity ?? row.amount) as number, 0) },
                { key: 'profit', label: '盈亏', align: 'right' as const, render: (v: unknown, row: Record<string, unknown>) => {
                  const n = Number(v ?? row.pnl ?? 0);
                  return <span className={n >= 0 ? 'text-danger' : 'text-success'}>{fmtNum(n, 2)}</span>;
                }},
              ]} pageSize={10} onExport={() => exportCSV(trades, 'backtest-trades')} />
            </SectionCard>
          )}

          {m.slippage_model_note && (
            <p className="text-text-secondary text-xs mt-2">{m.slippage_model_note}</p>
          )}
        </>
      )}

      {/* Strategy Comparison History */}
      {history.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">回测历史对比 ({history.length})</h3>
          <DataTable
            rows={history}
            columns={[
              { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
              { key: 'strategy', label: '策略' },
              { key: 'totalReturn', label: '总收益', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
              { key: 'sharpe', label: '夏普', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
              { key: 'maxDrawdown', label: '最大回撤', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
              { key: 'winRate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
              { key: 'ts', label: '时间', render: (v: unknown) => new Date(v as number).toLocaleTimeString('zh-CN') },
            ]}
            onExport={() => exportCSV(history, 'backtest-history')}
          />
        </SectionCard>
      )}
    </PageContainer>
  );
}
