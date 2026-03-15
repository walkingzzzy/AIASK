'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { LineChart, Chart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import type {
  BacktestBatchResponse,
  BacktestBatchResultItem,
  BacktestFailureReason,
  BacktestHistoryItem,
  BacktestListResponse,
  BacktestMetricsResponse,
  BacktestRunResponse,
  MarketKlineResponseDto,
} from '@aiask/shared-types';

type BacktestResult = {
  total_return?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  win_rate?: number;
  trades_count?: number;
  final_capital?: number;
  initial_capital?: number;
  equity_curve?: number[];
  dates?: string[];
  trades?: BacktestRunResponse['trades'];
  profit_factor?: number;
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

const COST_PRESETS = [
  { key: 'short', label: '短线模板', initialCapital: 50000, commission: 0.0005, slippage: 0.001 },
  { key: 'swing', label: '中线模板', initialCapital: 100000, commission: 0.0003, slippage: 0.0005 },
  { key: 'conservative', label: '保守成本', initialCapital: 200000, commission: 0.0008, slippage: 0.0015 },
] as const;

function defaultDate(offsetDays: number) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function describeBacktestFailure(message: string | null): BacktestFailureReason | null {
  const text = String(message ?? '').trim();
  if (!text) return null;
  if (/K线数据不足|No kline data|至少50天/.test(text)) {
    return { reasonCode: 'insufficient_kline_data', reason: '历史 K 线不足，无法满足回测窗口要求' };
  }
  if (/不支持的策略|unsupported/i.test(text)) {
    return { reasonCode: 'unsupported_strategy', reason: '当前策略参数不受支持，请切换策略或校正参数' };
  }
  if (/HTTP 502|调用 MCP/.test(text)) {
    return { reasonCode: 'upstream_unavailable', reason: '上游回测服务暂时不可用，请稍后重试' };
  }
  return { reasonCode: 'backtest_run_failed', reason: text };
}

export default function BacktestPage() {
  const searchParams = useSearchParams();
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const from = searchParams.get('from');
  const [strategy, setStrategy] = useState('ma_cross');
  const [formError, setFormError] = useState<string | null>(null);
  const [runFailure, setRunFailure] = useState<BacktestFailureReason | null>(null);
  const [tdxMessage, setTdxMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const backtestApi = useApiMutation<BacktestRunResponse>();
  const [runResult, setRunResult] = useState<BacktestRunResponse | null>(null);
  const [artifactMetricsPath, setArtifactMetricsPath] = useState<string | null>(null);
  const benchmarkQ = useApiQuery<MarketKlineResponseDto>(
    runResult?.equity_curve?.length ? '/market/kline?code=000300&period=daily&limit=500' : null,
  );
  const artifactMetricsQ = useApiQuery<BacktestMetricsResponse>(artifactMetricsPath);
  // P3-4: Persistent history from DB
  const historyQ = useApiQuery<BacktestListResponse>('/backtest/list?limit=20');

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

  function pushHistory(entry: HistoryEntry) {
    setHistory((prev) => {
      const dup = prev.find((h) => h.code === entry.code && h.strategy === entry.strategy && Math.abs(h.ts - entry.ts) < 5000);
      if (dup) return prev;
      return [entry, ...prev].slice(0, 20);
    });
  }

  function buildRunRequestBody() {
    const body: Record<string, unknown> = {
      code: trimmedCode,
      strategy,
      startDate,
      endDate,
      initialCapital: String(initialCapital),
      commission: String(commission),
      slippage: String(slippage),
    };
    if (strategy === 'ma_cross') {
      body.shortPeriod = String(shortPeriod);
      body.longPeriod = String(longPeriod);
    }
    if (strategy === 'momentum') {
      body.lookback = String(lookback);
      body.threshold = String(threshold);
    }
    if (strategy === 'rsi') {
      body.rsiPeriod = String(rsiPeriod);
      body.oversold = String(oversold);
      body.overbought = String(overbought);
    }
    return body;
  }

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    setRunFailure(null);
    setTdxMessage(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, buildRunRequestBody());
      setRunResult(data ?? null);
      if (data?.metrics?.totalReturn != null) {
        pushHistory({
          code: trimmedCode,
          strategy,
          totalReturn: Number(data.metrics.totalReturn ?? 0),
          sharpe: Number(data.metrics.sharpe ?? 0),
          maxDrawdown: Number(data.metrics.maxDrawdown ?? 0),
          winRate: Number(data.metrics.winRate ?? 0),
          ts: Date.now(),
        });
      }
      setArtifactMetricsPath(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : '回测运行失败';
      setFormError(message);
      setRunFailure(describeBacktestFailure(message));
    }
  }

  // P3-5: TDX push
  const tdxApi = useApiMutation();
  async function sendToTdx() {
    setTdxMessage(null);
    tdxApi.reset();
    try {
      const data = await tdxApi.triggerAsync('/backtest/send-to-tdx', { method: 'POST' }, { code: trimmedCode, strategy });
      const nested = data && typeof data === 'object'
        ? ((data as Record<string, unknown>).data ?? data) as Record<string, unknown>
        : null;
      const tdxStatus = nested && typeof nested === 'object'
        ? (((nested.tdx_send_status ?? nested.tdx_send_result) as Record<string, unknown> | undefined) ?? null)
        : null;
      if (tdxStatus?.success === false) {
        setTdxMessage(String(tdxStatus.message ?? '发送到 TDX 失败'));
        return;
      }
      setTdxMessage('回测结果已发送到 TDX。');
    } catch (err) {
      setTdxMessage(err instanceof Error ? err.message : '发送到 TDX 失败');
    }
  }

  // P3-3: Batch backtest
  const batchApi = useApiMutation<BacktestBatchResponse>();
  const [batchCodes, setBatchCodes] = useState('');
  const [batchResults, setBatchResults] = useState<BacktestBatchResultItem[]>([]);
  async function runBatch() {
    const codes = batchCodes.split(/[,，\s]+/).map((c) => c.trim()).filter((c) => /^\d{6}$/.test(c));
    if (!codes.length) return;
    try {
      const body: Record<string, unknown> = {
        codes,
        strategy,
        startDate,
        endDate,
        initialCapital: String(initialCapital),
        commission: String(commission),
      };
      if (strategy === 'ma_cross') {
        body.shortPeriod = String(shortPeriod);
        body.longPeriod = String(longPeriod);
      }
      const data = await batchApi.triggerAsync('/backtest/batch', { method: 'POST' }, body);
      setBatchResults(Array.isArray(data?.results) ? data.results : []);
    } catch { /* captured by hook */ }
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

  // Equity curve data
  const rawEquityCurve = useMemo(() => m?.equity_curve ?? [], [m]);
  const rawDates = useMemo(() => m?.dates ?? [], [m]);
  const firstActiveIndex = useMemo(() => {
    const idx = rawEquityCurve.findIndex((value) => Number(value) > 0);
    return idx >= 0 ? idx : 0;
  }, [rawEquityCurve]);
  const equityCurve = useMemo(() => rawEquityCurve.slice(firstActiveIndex), [firstActiveIndex, rawEquityCurve]);
  const dates = useMemo(
    () => (rawDates.length === rawEquityCurve.length ? rawDates.slice(firstActiveIndex) : rawDates),
    [firstActiveIndex, rawDates, rawEquityCurve.length],
  );
  const equityCategories = useMemo(() => dates.length === equityCurve.length ? dates : equityCurve.map((_, i) => `${i}`), [equityCurve, dates]);

  // Normalize to NAV (starting at 1.0)
  const navSeries = useMemo(() => {
    if (!equityCurve.length) return [];
    const firstPositive = equityCurve.find((value) => value > 0);
    const base = firstPositive && firstPositive > 0 ? firstPositive : (equityCurve[0] || 1);
    return equityCurve.map((v) => +((v / base)).toFixed(4));
  }, [equityCurve]);

  // Benchmark NAV (沪深300 normalized to 1.0)
  const benchmarkNav = useMemo(() => {
    const raw = benchmarkQ.data?.kline;
    if (!raw?.length || !equityCurve.length) return [];
    const closes = raw.map((k) => Number(k.close ?? 0)).filter((value) => value > 0);
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
  const historyRows = useMemo(
    () => extractArray(historyQ.data, 'items', 'results', 'history', 'data') as BacktestHistoryItem[],
    [historyQ.data],
  );

  // P2-1: Buy/sell markers for NAV chart
  const tradeMarkers = useMemo(() => {
    if (!trades.length || !dates.length) return { buy: [] as [string, number][], sell: [] as [string, number][] };
    const dateIdx = new Map(dates.map((d, i) => [d, i]));
    const buy: [string, number][] = [];
    const sell: [string, number][] = [];
    for (const t of trades) {
      const ed = String(t.date ?? '').slice(0, 10);
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

  function applyCostPreset(preset: typeof COST_PRESETS[number]) {
    setInitialCapital(preset.initialCapital);
    setCommission(preset.commission);
    setSlippage(preset.slippage);
    setShowAdvanced(true);
  }

  return (
    <PageContainer>
      <h1>回测分析</h1>
      {from ? <div className="text-xs text-text-secondary mb-2">上下文跳转 · 来源: {from}</div> : null}
      <p className="text-sm text-text-secondary mt-1 mb-3">按“基础参数 → 策略参数 → 成本假设”的顺序完成配置，减少首屏参数墙带来的理解成本。</p>
      <form onSubmit={runBacktest} className="space-y-3">
        <SectionCard className="p-4">
          <fieldset className="space-y-3">
            <legend className="px-1 text-sm font-semibold">基础参数</legend>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5 xl:items-end">
              <StockCodeInput id="backtest-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
              <label htmlFor="backtest-strategy" className="grid gap-1">
                <span className={labelCls}>策略</span>
                <select id="backtest-strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)} className={`${inputCls} w-full`}>
                  {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </label>
              <label htmlFor="backtest-start-date" className="grid gap-1">
                <span className={labelCls}>开始日期</span>
                <input id="backtest-start-date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={`${inputCls} w-full`} />
              </label>
              <label htmlFor="backtest-end-date" className="grid gap-1">
                <span className={labelCls}>结束日期</span>
                <input id="backtest-end-date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={`${inputCls} w-full`} />
              </label>
              <div className="flex gap-2 flex-wrap xl:justify-end">
                <button type="submit" disabled={loading} className="px-4 py-2 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm">{loading ? '运行中...' : '运行回测'}</button>
                {m ? <button type="button" onClick={sendToTdx} disabled={tdxApi.isPending} className="px-3 py-2 border border-border rounded cursor-pointer disabled:opacity-50 text-sm">{tdxApi.isPending ? '发送中...' : '发送到 TDX'}</button> : null}
              </div>
            </div>
          </fieldset>
        </SectionCard>

        <SectionCard className="p-4">
          <fieldset className="space-y-3">
            <legend className="px-1 text-sm font-semibold">策略参数</legend>
            {strategy === 'ma_cross' ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:max-w-[360px]">
                <label htmlFor="backtest-short-period" className="grid gap-1">
                  <span className={labelCls}>短周期</span>
                  <input id="backtest-short-period" type="number" value={shortPeriod} onChange={(e) => setShortPeriod(+e.target.value)} min={2} max={100} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-long-period" className="grid gap-1">
                  <span className={labelCls}>长周期</span>
                  <input id="backtest-long-period" type="number" value={longPeriod} onChange={(e) => setLongPeriod(+e.target.value)} min={5} max={250} className={`${inputCls} w-full`} />
                </label>
              </div>
            ) : null}
            {strategy === 'momentum' ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:max-w-[360px]">
                <label htmlFor="backtest-lookback" className="grid gap-1">
                  <span className={labelCls}>回看周期</span>
                  <input id="backtest-lookback" type="number" value={lookback} onChange={(e) => setLookback(+e.target.value)} min={5} max={120} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-threshold" className="grid gap-1">
                  <span className={labelCls}>阈值</span>
                  <input id="backtest-threshold" type="number" value={threshold} onChange={(e) => setThreshold(+e.target.value)} step={0.005} min={0} max={0.5} className={`${inputCls} w-full`} />
                </label>
              </div>
            ) : null}
            {strategy === 'rsi' ? (
              <div className="grid gap-3 sm:grid-cols-3 lg:max-w-[560px]">
                <label htmlFor="backtest-rsi-period" className="grid gap-1">
                  <span className={labelCls}>RSI 周期</span>
                  <input id="backtest-rsi-period" type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(+e.target.value)} min={2} max={50} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-oversold" className="grid gap-1">
                  <span className={labelCls}>超卖线</span>
                  <input id="backtest-oversold" type="number" value={oversold} onChange={(e) => setOversold(+e.target.value)} min={5} max={50} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-overbought" className="grid gap-1">
                  <span className={labelCls}>超买线</span>
                  <input id="backtest-overbought" type="number" value={overbought} onChange={(e) => setOverbought(+e.target.value)} min={50} max={95} className={`${inputCls} w-full`} />
                </label>
              </div>
            ) : null}
            {strategy === 'buy_and_hold' ? <p className="m-0 text-sm text-text-secondary">买入持有不需要额外策略参数，适合做基准对照。</p> : null}
          </fieldset>
        </SectionCard>

        <SectionCard className="p-4">
          <fieldset className="space-y-3">
            <legend className="px-1 text-sm font-semibold">成本假设</legend>
            <div className="flex gap-2 flex-wrap">
              {COST_PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => applyCostPreset(preset)}
                  className="px-3 py-1 text-xs rounded-full border border-border cursor-pointer hover:bg-surface-alt"
                >
                  {preset.label}
                </button>
              ))}
              <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className="text-xs text-primary cursor-pointer">
                {showAdvanced ? '▼ 收起高级选项' : '▶ 高级选项'}
              </button>
            </div>
            {showAdvanced ? (
              <div className="grid gap-3 sm:grid-cols-3 lg:max-w-[520px]">
                <label htmlFor="backtest-initial-capital" className="grid gap-1">
                  <span className={labelCls}>初始资金</span>
                  <input id="backtest-initial-capital" type="number" value={initialCapital} onChange={(e) => setInitialCapital(+e.target.value)} min={10000} step={10000} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-commission" className="grid gap-1">
                  <span className={labelCls}>手续费率</span>
                  <input id="backtest-commission" type="number" value={commission} onChange={(e) => setCommission(+e.target.value)} step={0.0001} min={0} max={0.01} className={`${inputCls} w-full`} />
                </label>
                <label htmlFor="backtest-slippage" className="grid gap-1">
                  <span className={labelCls}>滑点</span>
                  <input id="backtest-slippage" type="number" value={slippage} onChange={(e) => setSlippage(+e.target.value)} step={0.0001} min={0} max={0.01} className={`${inputCls} w-full`} />
                </label>
              </div>
            ) : (
              <p className="m-0 text-sm text-text-secondary">可以先点上方预设模板快速填入成本参数；只有在需要贴近真实成交时，再展开高级选项微调手续费和滑点。</p>
            )}
          </fieldset>
        </SectionCard>
        {tdxMessage ? <p className={`text-sm ${tdxApi.error ? 'text-danger' : 'text-success'}`}>{tdxMessage}</p> : null}
      </form>
      {loading ? <LoadingState text="回测运行中..." /> : null}
      {error ? <ErrorState text={error} /> : null}
      {runFailure ? (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">失败原因</h3>
          <KpiGrid cols={2}>
            <KpiCard title="原因代码" value={runFailure.reasonCode} />
            <KpiCard title="建议动作" value={runFailure.reason} />
          </KpiGrid>
        </SectionCard>
      ) : null}

      {m && (
        <>
          {runResult?.artifactId ? (
            <SectionCard className="mt-4 p-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="mt-0 mb-1">回测制品</h3>
                  <div className="text-xs text-text-secondary">artifactId: <code>{runResult.artifactId}</code></div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const path = `/backtest/metrics?artifactId=${encodeURIComponent(runResult.artifactId ?? '')}`;
                    if (artifactMetricsPath === path) void artifactMetricsQ.refetch();
                    else setArtifactMetricsPath(path);
                  }}
                  disabled={artifactMetricsQ.isFetching}
                  className="px-3 py-1 border border-border rounded cursor-pointer disabled:opacity-50 text-sm"
                >
                  {artifactMetricsQ.isFetching ? '加载中...' : '查看追踪指标'}
                </button>
              </div>
              {artifactMetricsQ.data?.metrics ? (
                <KpiGrid cols={3} className="mt-3">
                  <KpiCard title="追踪收益" value={fmtPct(artifactMetricsQ.data.metrics.totalReturn ?? null)} change={artifactMetricsQ.data.metrics.totalReturn ?? undefined} />
                  <KpiCard title="追踪夏普" value={fmtNum(artifactMetricsQ.data.metrics.sharpe ?? null, 2)} />
                  <KpiCard title="追踪回撤" value={fmtPct(artifactMetricsQ.data.metrics.maxDrawdown ?? null)} />
                  <KpiCard title="追踪胜率" value={fmtPct(artifactMetricsQ.data.metrics.winRate ?? null)} />
                  <KpiCard title="追踪交易数" value={artifactMetricsQ.data.metrics.totalTrades ?? '-'} />
                  <KpiCard title="追踪盈亏比" value={fmtNum(artifactMetricsQ.data.metrics.profitFactor ?? null, 2)} />
                </KpiGrid>
              ) : null}
              {artifactMetricsQ.error ? <p className="text-danger text-sm mt-2">{artifactMetricsQ.error}</p> : null}
            </SectionCard>
          ) : null}

          <KpiGrid cols={4}>
            <KpiCard title="总收益" value={fmtPct(m.total_return)} change={m.total_return ?? undefined} />
            <KpiCard title="夏普比率" value={fmtNum(m.sharpe_ratio, 2)} />
            <KpiCard title="最大回撤" value={fmtPct(m.max_drawdown)} />
            <KpiCard title="胜率" value={fmtPct(m.win_rate)} />
            <KpiCard title="交易次数" value={m.trades_count ?? '-'} />
            <KpiCard title="初始资金" value={fmtAmount(m.initial_capital)} />
            <KpiCard title="最终资金" value={fmtAmount(m.final_capital)} />
            <KpiCard title="盈亏比" value={fmtNum(m.profit_factor, 2)} />
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
        const dbRows = historyRows.map((r) => ({
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
        {batchApi.error ? <p className="text-danger text-sm mt-2">{batchApi.error}</p> : null}
        {batchResults.length > 0 && (
          <DataTable rows={batchResults} columns={[
            { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
            {
              key: 'success',
              label: '状态',
              render: (v: unknown) => {
                const success = v !== false;
                return <Badge variant={success ? 'success' : 'danger'}>{success ? '成功' : '失败'}</Badge>;
              },
            },
            { key: 'total_return', label: '总收益', align: 'right' as const, render: (v: unknown) => v == null ? '-' : <span className={Number(v) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(Number(v))}</span> },
            { key: 'sharpe_ratio', label: '夏普', align: 'right' as const, render: (v: unknown) => v == null ? '-' : fmtNum(Number(v), 2) },
            { key: 'max_drawdown', label: '最大回撤', align: 'right' as const, render: (v: unknown) => v == null ? '-' : fmtPct(Number(v)) },
            { key: 'win_rate', label: '胜率', align: 'right' as const, render: (v: unknown) => v == null ? '-' : fmtPct(Number(v)) },
            { key: 'trades_count', label: '交易次数', align: 'right' as const },
            { key: 'reasonCode', label: '失败代码' },
            { key: 'reason', label: '失败原因' },
          ]} onExport={() => exportCSV(batchResults, 'batch-backtest')} />
        )}
      </SectionCard>
    </PageContainer>
  );
}
