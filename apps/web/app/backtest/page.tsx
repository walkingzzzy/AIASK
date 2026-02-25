'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { LineChart, Chart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';

type BacktestResult = {
  total_return?: number; sharpe_ratio?: number; max_drawdown?: number;
  win_rate?: number; trades_count?: number; final_capital?: number;
  initial_capital?: number; equity_curve?: number[]; dates?: string[];
  trades?: Record<string, unknown>[]; profit_factor?: number;
};

type RunResponse = {
  artifactId?: string;
  metrics?: { totalReturn: number | null; sharpe: number | null; maxDrawdown: number | null; winRate: number | null; totalTrades: number | null; profitFactor: number | null };
  equity_curve?: number[];
  dates?: string[];
  trades?: Record<string, unknown>[];
  profit_factor?: number | null;
  initial_capital?: number | null;
  final_capital?: number | null;
};

type HistoryEntry = {
  code: string; strategy: string; totalReturn: number; sharpe: number;
  maxDrawdown: number; winRate: number; ts: number;
};

const STRATEGIES = [
  { value: 'ma_cross', label: '均线交叉' },
  { value: 'momentum', label: '动量策略' },
  { value: 'rsi', label: 'RSI策略' },
  { value: 'buy_and_hold', label: '买入持有' },
] as const;

function defaultDate(offsetDays: number) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function BacktestPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [strategy, setStrategy] = useState('ma_cross');
  const [formError, setFormError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const backtestApi = useApiMutation<RunResponse>();
  const [runResult, setRunResult] = useState<RunResponse | null>(null);
  const benchmarkQ = useApiQuery<{ kline?: Array<Record<string, number>> }>(
    runResult?.equity_curve?.length ? '/market/kline?code=000300&period=daily&limit=500' : null,
  );
  // P3-4: Persistent history from DB
  const historyQ = useApiQuery<{ result?: Record<string, unknown>[] }>('/backtest/list?limit=20');

  // Date range
  const [startDate, setStartDate] = useState(() => defaultDate(-365));
  const [endDate, setEndDate] = useState(() => defaultDate(0));

  // Strategy params
  const [shortPeriod, setShortPeriod] = useState(5);
  const [longPeriod, setLongPeriod] = useState(20);
  const [lookback, setLookback] = useState(20);
  const [threshold, setThreshold] = useState(0.02);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [oversold, setOversold] = useState(30);
  const [overbought, setOverbought] = useState(70);

  // Advanced config
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [initialCapital, setInitialCapital] = useState(100000);
  const [commission, setCommission] = useState(0.0003);
  const [slippage, setSlippage] = useState(0);

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    const body: Record<string, unknown> = {
      code: trimmedCode, strategy, startDate, endDate,
      initialCapital: String(initialCapital),
    };
    if (strategy === 'ma_cross') { body.shortPeriod = String(shortPeriod); body.longPeriod = String(longPeriod); }
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, body);
      setRunResult(data ?? null);
    } catch { /* captured */ }
  }

  // P3-5: TDX push
  const tdxApi = useApiMutation();
  async function sendToTdx() {
    try { await tdxApi.triggerAsync('/backtest/send-to-tdx', { method: 'POST' }, { code: trimmedCode, strategy }); } catch { /* */ }
  }

  // P3-3: Batch backtest
  const batchApi = useApiMutation<{ data?: Record<string, unknown>[] }>();
  const [batchCodes, setBatchCodes] = useState('');
  const [batchResults, setBatchResults] = useState<Record<string, unknown>[]>([]);
  async function runBatch() {
    const codes = batchCodes.split(/[,，\s]+/).map((c) => c.trim()).filter((c) => /^\d{6}$/.test(c));
    if (!codes.length) return;
    try {
      const data = await batchApi.triggerAsync('/backtest/batch', { method: 'POST' }, { codes, strategy, initialCapital: String(initialCapital) });
      const results = Array.isArray(data?.data) ? data.data : (data as Record<string, unknown>)?.results as Record<string, unknown>[] ?? [];
      setBatchResults(Array.isArray(results) ? results : []);
    } catch { /* */ }
  }

  // Build BacktestResult from run response
  const m: BacktestResult | undefined = useMemo(() => {
    if (!runResult?.metrics) return undefined;
    const rm = runResult.metrics;
    return {
      total_return: rm.totalReturn ?? undefined,
      sharpe_ratio: rm.sharpe ?? undefined,
      max_drawdown: rm.maxDrawdown ?? undefined,
      win_rate: rm.winRate ?? undefined,
      trades_count: rm.totalTrades ?? undefined,
      initial_capital: runResult.initial_capital ?? undefined,
      final_capital: runResult.final_capital ?? undefined,
      equity_curve: runResult.equity_curve,
      dates: runResult.dates,
      trades: runResult.trades,
      profit_factor: runResult.profit_factor ?? rm.profitFactor ?? undefined,
    };
  }, [runResult]);
  const loading = backtestApi.isPending;
  const error = formError || backtestApi.error;

  // Save to history when new result arrives
  useEffect(() => {
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
  const dates = useMemo(() => m?.dates ?? [], [m]);
  const equityCategories = useMemo(() => dates.length === equityCurve.length ? dates : equityCurve.map((_, i) => `${i}`), [equityCurve, dates]);

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

  // P2-1: Buy/sell markers for NAV chart
  const tradeMarkers = useMemo(() => {
    if (!trades.length || !dates.length) return { buy: [] as [string, number][], sell: [] as [string, number][] };
    const dateIdx = new Map(dates.map((d, i) => [d, i]));
    const buy: [string, number][] = [];
    const sell: [string, number][] = [];
    for (const t of trades) {
      const ed = String(t.date ?? '').slice(0, 10);
      const xd = String(t.exit_price != null ? (t as Record<string, unknown>).date : '').slice(0, 10);
      const ei = dateIdx.get(ed);
      if (ei != null && navSeries[ei] != null) buy.push([equityCategories[ei], navSeries[ei]]);
      // exit date: estimate from holding_days
      const hd = Number(t.holding_days ?? 0);
      const xi = ei != null ? ei + hd : undefined;
      if (xi != null && xi < navSeries.length && navSeries[xi] != null) sell.push([equityCategories[xi], navSeries[xi]]);
    }
    return { buy, sell };
  }, [trades, dates, navSeries, equityCategories]);

  // P2-2: Monthly returns heatmap
  const monthlyHeatmap = useMemo(() => {
    if (equityCurve.length < 2 || !dates.length) return { data: [] as [number, number, number][], months: [] as string[], years: [] as string[] };
    const monthly = new Map<string, { first: number; last: number }>();
    for (let i = 0; i < equityCurve.length; i++) {
      const ym = (dates[i] ?? '').slice(0, 7);
      if (!ym) continue;
      const entry = monthly.get(ym);
      if (!entry) monthly.set(ym, { first: equityCurve[i], last: equityCurve[i] });
      else entry.last = equityCurve[i];
    }
    const sorted = [...monthly.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const yearsSet = new Set<string>();
    const monthsSet = new Set<string>();
    const data: [number, number, number][] = [];
    const monthLabels = ['01','02','03','04','05','06','07','08','09','10','11','12'];
    for (const [ym, v] of sorted) {
      const [y, mo] = ym.split('-');
      yearsSet.add(y);
      monthsSet.add(mo);
      const ret = v.first > 0 ? +((v.last - v.first) / v.first * 100).toFixed(2) : 0;
      data.push([monthLabels.indexOf(mo), [...yearsSet].sort().indexOf(y), ret]);
    }
    return { data, months: monthLabels, years: [...yearsSet].sort() };
  }, [equityCurve, dates]);

  // P2-3: Rolling sharpe (60-day window)
  const rollingMetrics = useMemo(() => {
    const W = 60;
    if (equityCurve.length < W + 1) return { sharpe: [] as number[], drawdown: [] as number[], cats: [] as string[] };
    const sharpe: number[] = [];
    const dd: number[] = [];
    const cats: string[] = [];
    for (let i = W; i < equityCurve.length; i++) {
      const window = equityCurve.slice(i - W, i + 1);
      const rets = window.slice(1).map((v, j) => window[j] > 0 ? (v - window[j]) / window[j] : 0);
      const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
      const std = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length);
      sharpe.push(std > 0 ? +((mean * 252) / (std * Math.sqrt(252))).toFixed(2) : 0);
      let peak = window[0];
      let maxDd = 0;
      for (const v of window) { if (v > peak) peak = v; const d = peak > 0 ? (peak - v) / peak : 0; if (d > maxDd) maxDd = d; }
      dd.push(+(maxDd * 100).toFixed(2));
      cats.push(equityCategories[i] ?? `${i}`);
    }
    return { sharpe, drawdown: dd, cats };
  }, [equityCurve, equityCategories]);

  // P2-4: Returns distribution histogram
  const returnsHist = useMemo(() => {
    if (dailyReturns.length < 10) return { bins: [] as string[], counts: [] as number[] };
    const min = Math.min(...dailyReturns);
    const max = Math.max(...dailyReturns);
    const range = max - min || 1;
    const nBins = Math.min(30, Math.max(10, Math.ceil(Math.sqrt(dailyReturns.length))));
    const step = range / nBins;
    const counts = new Array(nBins).fill(0);
    const bins: string[] = [];
    for (let i = 0; i < nBins; i++) bins.push((min + step * (i + 0.5)).toFixed(2));
    for (const r of dailyReturns) { const idx = Math.min(Math.floor((r - min) / step), nBins - 1); counts[idx]++; }
    return { bins, counts };
  }, [dailyReturns]);

  const inputCls = 'px-2 py-1 border border-border rounded text-sm bg-surface';
  const labelCls = 'text-xs text-text-secondary';

  return (
    <PageContainer>
      <h1>回测分析</h1>
      <form onSubmit={runBacktest} className="space-y-3">
        {/* Row 1: core inputs */}
        <div className="flex gap-2 flex-wrap items-end">
          <div><label className={labelCls}>股票代码</label><StockCodeInput value={code} onChange={setCode} error={codeError} /></div>
          <div>
            <label className={labelCls}>策略</label>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className={`${inputCls} w-[140px]`}>
              {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div><label className={labelCls}>开始日期</label><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={`${inputCls} w-[140px]`} /></div>
          <div><label className={labelCls}>结束日期</label><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={`${inputCls} w-[140px]`} /></div>
          <button type="submit" disabled={loading} className="px-4 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm h-[30px]">{loading ? '运行中...' : '运行回测'}</button>
          {m && <button type="button" onClick={sendToTdx} disabled={tdxApi.isPending} className="px-3 py-1 border border-border rounded cursor-pointer disabled:opacity-50 text-sm h-[30px]">{tdxApi.isPending ? '发送中...' : '发送到 TDX'}</button>}
        </div>

        {/* Row 2: strategy-specific params */}
        {strategy === 'ma_cross' && (
          <div className="flex gap-3 items-end flex-wrap">
            <div><label className={labelCls}>短周期</label><input type="number" value={shortPeriod} onChange={(e) => setShortPeriod(+e.target.value)} min={2} max={100} className={`${inputCls} w-[80px]`} /></div>
            <div><label className={labelCls}>长周期</label><input type="number" value={longPeriod} onChange={(e) => setLongPeriod(+e.target.value)} min={5} max={250} className={`${inputCls} w-[80px]`} /></div>
          </div>
        )}
        {strategy === 'momentum' && (
          <div className="flex gap-3 items-end flex-wrap">
            <div><label className={labelCls}>回看周期</label><input type="number" value={lookback} onChange={(e) => setLookback(+e.target.value)} min={5} max={120} className={`${inputCls} w-[80px]`} /></div>
            <div><label className={labelCls}>阈值</label><input type="number" value={threshold} onChange={(e) => setThreshold(+e.target.value)} step={0.005} min={0} max={0.5} className={`${inputCls} w-[80px]`} /></div>
          </div>
        )}
        {strategy === 'rsi' && (
          <div className="flex gap-3 items-end flex-wrap">
            <div><label className={labelCls}>RSI周期</label><input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(+e.target.value)} min={2} max={50} className={`${inputCls} w-[80px]`} /></div>
            <div><label className={labelCls}>超卖线</label><input type="number" value={oversold} onChange={(e) => setOversold(+e.target.value)} min={5} max={50} className={`${inputCls} w-[80px]`} /></div>
            <div><label className={labelCls}>超买线</label><input type="number" value={overbought} onChange={(e) => setOverbought(+e.target.value)} min={50} max={95} className={`${inputCls} w-[80px]`} /></div>
          </div>
        )}

        {/* Row 3: advanced config (collapsible) */}
        <div>
          <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className="text-xs text-primary cursor-pointer">
            {showAdvanced ? '▼ 收起高级选项' : '▶ 高级选项'}
          </button>
          {showAdvanced && (
            <div className="flex gap-3 items-end flex-wrap mt-2">
              <div><label className={labelCls}>初始资金</label><input type="number" value={initialCapital} onChange={(e) => setInitialCapital(+e.target.value)} min={10000} step={10000} className={`${inputCls} w-[120px]`} /></div>
              <div><label className={labelCls}>手续费率</label><input type="number" value={commission} onChange={(e) => setCommission(+e.target.value)} step={0.0001} min={0} max={0.01} className={`${inputCls} w-[100px]`} /></div>
              <div><label className={labelCls}>滑点</label><input type="number" value={slippage} onChange={(e) => setSlippage(+e.target.value)} step={0.0001} min={0} max={0.01} className={`${inputCls} w-[100px]`} /></div>
            </div>
          )}
        </div>
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
            <KpiCard title="盈亏比" value={fmtNum(Number(m.profit_factor), 2)} />
          </KpiGrid>

          {equityCurve.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">净值曲线</h3>
              <Chart option={{
                tooltip: { trigger: 'axis' },
                legend: { data: ['策略净值', ...(benchmarkNav.length ? ['沪深300'] : [])] },
                grid: { top: 40, right: 20, bottom: 30, left: 50 },
                xAxis: { type: 'category', data: equityCategories },
                yAxis: { type: 'value', name: '净值', scale: true },
                series: [
                  {
                    name: '策略净值', type: 'line', data: navSeries, smooth: true,
                    itemStyle: { color: '#1a73e8' }, areaStyle: { opacity: 0.15 },
                    markPoint: {
                      symbol: 'arrow', symbolSize: 10,
                      data: [
                        ...tradeMarkers.buy.map(([x, y]) => ({ coord: [x, y], itemStyle: { color: '#ef4444' }, symbolRotate: 0 })),
                        ...tradeMarkers.sell.map(([x, y]) => ({ coord: [x, y], itemStyle: { color: '#22c55e' }, symbolRotate: 180 })),
                      ],
                    },
                  },
                  ...(benchmarkNav.length ? [{ name: '沪深300', type: 'line' as const, data: benchmarkNav, smooth: true, itemStyle: { color: '#9ca3af' } }] : []),
                ],
              }} height={320} />
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

          {/* P2-3: Rolling Sharpe & Drawdown */}
          {rollingMetrics.sharpe.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">滚动指标（60日窗口）</h3>
              <LineChart
                categories={rollingMetrics.cats}
                series={[
                  { name: '滚动夏普', data: rollingMetrics.sharpe, color: '#1a73e8' },
                  { name: '滚动回撤 (%)', data: rollingMetrics.drawdown, color: '#ef4444', yAxisIndex: 1 },
                ]}
                height={240}
                yAxisName="夏普比率"
                y2AxisName="回撤 %"
              />
            </SectionCard>
          )}

          {/* P2-4: Returns Distribution Histogram */}
          {returnsHist.bins.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">收益分布</h3>
              <Chart option={{
                tooltip: { trigger: 'axis' },
                grid: { top: 20, right: 20, bottom: 30, left: 50 },
                xAxis: { type: 'category', data: returnsHist.bins, name: '日收益率 (%)' },
                yAxis: { type: 'value', name: '频次' },
                series: [{ type: 'bar', data: returnsHist.counts, itemStyle: { color: '#3b82f6' }, barWidth: '90%' }],
              }} height={200} />
            </SectionCard>
          )}

          {/* P2-2: Monthly Returns Heatmap */}
          {monthlyHeatmap.data.length > 0 && (
            <SectionCard className="mt-4 p-3">
              <h3 className="mt-0">月度收益热力图</h3>
              <Chart option={{
                tooltip: { formatter: (p: { data: number[] }) => `${monthlyHeatmap.years[p.data[1]]}年${monthlyHeatmap.months[p.data[0]]}月: ${p.data[2]}%` },
                grid: { top: 10, right: 20, bottom: 40, left: 60 },
                xAxis: { type: 'category', data: monthlyHeatmap.months.map((m) => `${m}月`), splitArea: { show: true } },
                yAxis: { type: 'category', data: monthlyHeatmap.years, splitArea: { show: true } },
                visualMap: { min: -10, max: 10, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#22c55e', '#f5f5f5', '#ef4444'] } },
                series: [{ type: 'heatmap', data: monthlyHeatmap.data, label: { show: true, formatter: (p: { data: number[] }) => `${p.data[2]}%`, fontSize: 10 } }],
              }} height={Math.max(160, monthlyHeatmap.years.length * 40 + 80)} />
            </SectionCard>
          )}
        </>
      )}

      {/* Strategy Comparison History (merged: session + DB) */}
      {(() => {
        const dbRows = (historyQ.data?.result ?? []).map((r) => ({
          code: String(r.code ?? ''), strategy: String(r.strategy ?? ''),
          totalReturn: Number(r.total_return ?? 0), sharpe: Number(r.sharpe_ratio ?? 0),
          maxDrawdown: Number(r.max_drawdown ?? 0), winRate: 0,
          ts: new Date(String(r.created_at ?? '')).getTime() || 0,
        }));
        const merged = [...history, ...dbRows.filter((d) => !history.some((h) => h.code === d.code && h.strategy === d.strategy && Math.abs(h.ts - d.ts) < 60000))].slice(0, 30);
        return merged.length > 0 ? (
          <SectionCard className="mt-4 p-3">
            <h3 className="mt-0">回测历史对比 ({merged.length})</h3>
            <DataTable
              rows={merged}
              columns={[
                { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                { key: 'strategy', label: '策略' },
                { key: 'totalReturn', label: '总收益', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
                { key: 'sharpe', label: '夏普', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                { key: 'maxDrawdown', label: '最大回撤', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
                { key: 'winRate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
                { key: 'ts', label: '时间', render: (v: unknown) => { const t = v as number; return t > 0 ? new Date(t).toLocaleString('zh-CN') : '-'; } },
              ]}
              onExport={() => exportCSV(merged, 'backtest-history')}
            />
          </SectionCard>
        ) : null;
      })()}

      {/* P3-3: Batch Backtest */}
      <SectionCard className="mt-4 p-3">
        <h3 className="mt-0">批量回测对比</h3>
        <div className="flex gap-2 items-end flex-wrap">
          <div>
            <label className={labelCls}>股票代码（逗号分隔）</label>
            <input value={batchCodes} onChange={(e) => setBatchCodes(e.target.value)} placeholder="600519,000858,601318" className={`${inputCls} w-[280px]`} />
          </div>
          <button type="button" onClick={runBatch} disabled={batchApi.isPending} className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{batchApi.isPending ? '运行中...' : '批量回测'}</button>
        </div>
        {batchResults.length > 0 && (
          <DataTable rows={batchResults} columns={[
            { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
            { key: 'total_return', label: '总收益', align: 'right' as const, render: (v: unknown) => <span className={Number(v) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(Number(v))}</span> },
            { key: 'sharpe_ratio', label: '夏普', align: 'right' as const, render: (v: unknown) => fmtNum(Number(v), 2) },
            { key: 'max_drawdown', label: '最大回撤', align: 'right' as const, render: (v: unknown) => fmtPct(Number(v)) },
            { key: 'win_rate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(Number(v)) },
            { key: 'trades_count', label: '交易次数', align: 'right' as const },
          ]} onExport={() => exportCSV(batchResults, 'batch-backtest')} />
        )}
      </SectionCard>
    </PageContainer>
  );
}
