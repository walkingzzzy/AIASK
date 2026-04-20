'use client';

import { FormEvent, useMemo, useState } from 'react';
import BacktestConfigWorkspace from '@/app/backtest/components/backtest-config-workspace';
import BacktestHero from '@/app/backtest/components/backtest-hero';
import BacktestHistoryBatch from '@/app/backtest/components/backtest-history-batch';
import { backtestChipButtonCls, backtestNavCardCls } from '@/app/backtest/components/backtest-panel-styles';
import {
  PageContainer,
  SectionCard,
  KpiCard,
  KpiGrid,
  DataTable,
  Badge,
  TabBar,
  Skeleton,
  SkeletonCard,
} from '@/components/ui';
import { LineChart, Chart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import type {
  BacktestBatchResponse,
  BacktestBatchResultItem,
  BacktestFailureReason,
  BacktestHistoryItem,
  BacktestListResponse,
  BacktestMetricsResponse,
  BacktestOptimizationResponse,
  BacktestRunResponse,
  BacktestWalkForwardResponse,
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
  code: string;
  strategy: string;
  totalReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  ts: number;
};

type BacktestSurfaceTab = 'results' | 'setup' | 'research' | 'history';
type BacktestResultTab = 'overview' | 'chart' | 'trades' | 'diagnostics';

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
const BACKTEST_SURFACE_TABS = [
  { key: 'results', label: '结果总览' },
  { key: 'setup', label: '配置与运行' },
  { key: 'research', label: '参数研究' },
  { key: 'history', label: '历史与批量' },
] as const;
const BACKTEST_RESULT_TABS = [
  { key: 'overview', label: '摘要' },
  { key: 'chart', label: '曲线' },
  { key: 'trades', label: '交易' },
  { key: 'diagnostics', label: '诊断' },
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
  const searchParams = useStableSearchParams();
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const from = searchParams.get('from');
  const [surfaceTab, setSurfaceTab] = useState<BacktestSurfaceTab>('results');
  const [resultTab, setResultTab] = useState<BacktestResultTab>('overview');
  const [strategy, setStrategy] = useState('ma_cross');
  const [formError, setFormError] = useState<string | null>(null);
  const [runFailure, setRunFailure] = useState<BacktestFailureReason | null>(null);
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
      const dup = prev.find(
        (h) => h.code === entry.code && h.strategy === entry.strategy && Math.abs(h.ts - entry.ts) < 5000,
      );
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
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, buildRunRequestBody());
      setRunResult(data ?? null);
      setSurfaceTab('results');
      setResultTab('overview');
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
      setSurfaceTab('results');
      setResultTab('overview');
    }
  }

  // P3-3: Batch backtest
  const batchApi = useApiMutation<BacktestBatchResponse>();
  const [batchCodes, setBatchCodes] = useState('');
  const [batchResults, setBatchResults] = useState<BacktestBatchResultItem[]>([]);
  const optimizeApi = useApiMutation<BacktestOptimizationResponse>();
  const walkForwardApi = useApiMutation<BacktestWalkForwardResponse>();
  const [researchObjective, setResearchObjective] = useState<'balanced' | 'sharpe' | 'total_return'>('balanced');
  const [topN, setTopN] = useState(5);
  const [maxCandidates, setMaxCandidates] = useState(8);
  const [trainDays, setTrainDays] = useState(180);
  const [testDays, setTestDays] = useState(60);
  const [stepDays, setStepDays] = useState(30);
  const [maxFolds, setMaxFolds] = useState(4);
  async function runBatch() {
    const codes = batchCodes
      .split(/[,，\s]+/)
      .map((c) => c.trim())
      .filter((c) => /^\d{6}$/.test(c));
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
      setSurfaceTab('history');
    } catch {
      /* captured by hook */
    }
  }

  async function runOptimization() {
    setFormError(null);
    setSurfaceTab('research');
    if (!validate()) return;
    const body = {
      ...buildRunRequestBody(),
      objective: researchObjective,
      topN: String(topN),
      maxCandidates: String(maxCandidates),
    };
    await optimizeApi.triggerAsync('/backtest/optimize', { method: 'POST' }, body);
  }

  async function runWalkForward() {
    setFormError(null);
    setSurfaceTab('research');
    if (!validate()) return;
    const body = {
      ...buildRunRequestBody(),
      objective: researchObjective,
      trainDays: String(trainDays),
      testDays: String(testDays),
      stepDays: String(stepDays),
      maxFolds: String(maxFolds),
    };
    await walkForwardApi.triggerAsync('/backtest/walk-forward', { method: 'POST' }, body);
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
  const equityCategories = useMemo(
    () => (dates.length === equityCurve.length ? dates : equityCurve.map((_, i) => `${i}`)),
    [equityCurve, dates],
  );

  // Normalize to NAV (starting at 1.0)
  const navSeries = useMemo(() => {
    if (!equityCurve.length) return [];
    const firstPositive = equityCurve.find((value) => value > 0);
    const base = firstPositive && firstPositive > 0 ? firstPositive : equityCurve[0] || 1;
    return equityCurve.map((v) => +(v / base).toFixed(4));
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
      return prev > 0 ? +(((v - prev) / prev) * 100).toFixed(3) : 0;
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
  const mergedHistoryRows = useMemo(() => {
    const dbRows = historyRows.map((r) => ({
      code: String(r.code ?? ''),
      strategy: String(r.strategy ?? ''),
      totalReturn: Number(r.total_return ?? 0),
      sharpe: Number(r.sharpe_ratio ?? 0),
      maxDrawdown: Number(r.max_drawdown ?? 0),
      winRate: 0,
      ts: new Date(String(r.created_at ?? '')).getTime() || 0,
    }));
    return [
      ...history,
      ...dbRows.filter(
        (d) => !history.some((h) => h.code === d.code && h.strategy === d.strategy && Math.abs(h.ts - d.ts) < 60000),
      ),
    ].slice(0, 30);
  }, [history, historyRows]);

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
      if (xi != null && xi < navSeries.length && navSeries[xi] != null)
        sell.push([equityCategories[xi], navSeries[xi]]);
    }
    return { buy, sell };
  }, [trades, dates, navSeries, equityCategories]);

  // P2-2: Monthly returns heatmap
  const monthlyHeatmap = useMemo(() => {
    if (equityCurve.length < 2 || !dates.length)
      return { data: [] as [number, number, number][], months: [] as string[], years: [] as string[] };
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
    const monthLabels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];
    for (const [ym, v] of sorted) {
      const [y, mo] = ym.split('-');
      yearsSet.add(y);
      monthsSet.add(mo);
      const ret = v.first > 0 ? +(((v.last - v.first) / v.first) * 100).toFixed(2) : 0;
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
      const rets = window.slice(1).map((v, j) => (window[j] > 0 ? (v - window[j]) / window[j] : 0));
      const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
      const std = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length);
      sharpe.push(std > 0 ? +((mean * 252) / (std * Math.sqrt(252))).toFixed(2) : 0);
      let peak = window[0];
      let maxDd = 0;
      for (const v of window) {
        if (v > peak) peak = v;
        const d = peak > 0 ? (peak - v) / peak : 0;
        if (d > maxDd) maxDd = d;
      }
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
    for (const r of dailyReturns) {
      const idx = Math.min(Math.floor((r - min) / step), nBins - 1);
      counts[idx]++;
    }
    return { bins, counts };
  }, [dailyReturns]);

  const strategyLabel = STRATEGIES.find((item) => item.value === strategy)?.label ?? strategy;
  const runStatusLabel = loading ? '运行中' : m ? '已生成结果' : '等待运行';
  const runStatusVariant = loading ? 'warning' : m ? 'success' : 'neutral';
  const dateRangeLabel = `${startDate || '-'} ~ ${endDate || '-'}`;
  const configurationSummary = showAdvanced
    ? `初始资金 ${fmtAmount(initialCapital)} · 手续费 ${fmtNum(commission * 100, 2)}% · 滑点 ${fmtNum(slippage * 100, 2)}%`
    : '使用默认成本设定或模板，适合先完成第一轮策略可行性判断';

  function applyCostPreset(preset: { initialCapital: number; commission: number; slippage: number }) {
    setInitialCapital(preset.initialCapital);
    setCommission(preset.commission);
    setSlippage(preset.slippage);
    setShowAdvanced(true);
  }

  const hasAnyResultBlock = loading || Boolean(error) || Boolean(runFailure) || Boolean(m);

  const sectionTabMap: Record<string, { surface: BacktestSurfaceTab; result?: BacktestResultTab }> = {
    'backtest-overview': { surface: 'results', result: 'overview' },
    'backtest-chart': { surface: 'results', result: 'chart' },
    'backtest-trades': { surface: 'results', result: 'trades' },
    'backtest-research': { surface: 'research' },
    'backtest-history': { surface: 'history' },
    'backtest-batch': { surface: 'history' },
  };

  function scrollToSection(id: string) {
    if (typeof document === 'undefined') return;
    const target = sectionTabMap[id];
    if (target) {
      setSurfaceTab(target.surface);
      if (target.result) setResultTab(target.result);
      window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 40);
      return;
    }
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <PageContainer className="app-theme-strategy">
      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Workspace Layers</div>
            <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">回测任务切换</h3>
            <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
              默认只展开当前步骤。先配置并运行，再切换到结果、研究或历史，避免净值曲线、交易明细和批量结果同时平铺成长页。
            </p>
          </div>
          <Badge variant={hasAnyResultBlock ? 'info' : 'neutral'}>
            {surfaceTab === 'setup'
              ? '配置与运行'
              : surfaceTab === 'results'
                ? '结果解读'
                : surfaceTab === 'research'
                  ? '参数研究'
                  : '历史与批量'}
          </Badge>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <TabBar tabs={BACKTEST_SURFACE_TABS} active={surfaceTab} onChange={setSurfaceTab} />
          {surfaceTab === 'results' ? (
            <TabBar tabs={BACKTEST_RESULT_TABS} active={resultTab} onChange={setResultTab} />
          ) : null}
        </div>
      </SectionCard>

      <BacktestHero
        loading={loading}
        runStatusLabel={runStatusLabel}
        runStatusVariant={runStatusVariant}
        artifactId={runResult?.artifactId}
        from={from}
        onScrollToSection={scrollToSection}
        trimmedCode={trimmedCode}
        strategyLabel={strategyLabel}
        startDate={startDate}
        dateRangeLabel={dateRangeLabel}
        totalReturn={m?.total_return ?? null}
        maxDrawdown={m?.max_drawdown ?? null}
        batchResultsCount={batchResults.length}
        hasAnyResultBlock={hasAnyResultBlock}
        configurationSummary={configurationSummary}
      />

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="策略" value={strategyLabel} />
        <KpiCard title="总收益" value={m ? fmtPct(m.total_return) : null} change={m?.total_return ?? undefined} />
        <KpiCard title="夏普比率" value={m ? fmtNum(m.sharpe_ratio, 2) : null} />
        <KpiCard title="最大回撤" value={m ? fmtPct(m.max_drawdown) : null} />
        <KpiCard title="交易次数" value={m?.trades_count ?? null} />
      </KpiGrid>

      {loading ? <LoadingState text="回测运行中..." /> : null}
      {error ? <ErrorState text={error} /> : null}
      {runFailure ? (
        <SectionCard className="mt-4 p-4 sm:p-5">
          <h3 className="mt-0">失败原因</h3>
          <KpiGrid cols={2}>
            <KpiCard title="原因代码" value={runFailure.reasonCode} />
            <KpiCard title="建议动作" value={runFailure.reason} />
          </KpiGrid>
        </SectionCard>
      ) : null}

      {surfaceTab === 'setup' ? (
        <div className="space-y-4">
          <BacktestConfigWorkspace
            code={code}
            setCode={setCode}
            codeError={codeError}
            strategy={strategy}
            setStrategy={setStrategy}
            strategies={STRATEGIES}
            startDate={startDate}
            setStartDate={setStartDate}
            endDate={endDate}
            setEndDate={setEndDate}
            shortPeriod={shortPeriod}
            setShortPeriod={setShortPeriod}
            longPeriod={longPeriod}
            setLongPeriod={setLongPeriod}
            lookback={lookback}
            setLookback={setLookback}
            threshold={threshold}
            setThreshold={setThreshold}
            rsiPeriod={rsiPeriod}
            setRsiPeriod={setRsiPeriod}
            oversold={oversold}
            setOversold={setOversold}
            overbought={overbought}
            setOverbought={setOverbought}
            showAdvanced={showAdvanced}
            setShowAdvanced={setShowAdvanced}
            initialCapital={initialCapital}
            setInitialCapital={setInitialCapital}
            commission={commission}
            setCommission={setCommission}
            slippage={slippage}
            setSlippage={setSlippage}
            costPresets={COST_PRESETS}
            onApplyCostPreset={applyCostPreset}
            configurationSummary={configurationSummary}
            runBacktest={runBacktest}
          />

          <SectionCard className="p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">Reading Flow</div>
                <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">结果阅读顺序</h3>
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  先看摘要，再看净值曲线，最后按需进入交易、历史和批量结果。长内容不再默认全部展开。
                </p>
              </div>
              <Badge variant={hasAnyResultBlock ? 'info' : 'neutral'}>{hasAnyResultBlock ? '已有结果' : '等待运行'}</Badge>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <button type="button" onClick={() => scrollToSection('backtest-overview')} className={backtestNavCardCls}>
                <div className="font-medium text-text-primary">1. 结果摘要</div>
                <div className="mt-2 text-xs text-text-secondary">先判断收益、回撤和胜率是否值得继续分析。</div>
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-chart')} className={backtestNavCardCls}>
                <div className="font-medium text-text-primary">2. 净值曲线</div>
                <div className="mt-2 text-xs text-text-secondary">确认收益是否平滑，是否依赖单段行情。</div>
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-research')} className={backtestNavCardCls}>
                <div className="font-medium text-text-primary">3. 参数研究</div>
                <div className="mt-2 text-xs text-text-secondary">继续跑参数优化和 walk-forward，验证稳健性。</div>
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-history')} className={backtestNavCardCls}>
                <div className="font-medium text-text-primary">4. 历史与批量</div>
                <div className="mt-2 text-xs text-text-secondary">横向对比同类回测，避免只盯一次结果。</div>
              </button>
            </div>
          </SectionCard>
        </div>
      ) : null}

      {surfaceTab === 'results' ? (
        <div className="space-y-4">
          {resultTab === 'overview' ? (
            <>
              <div id="backtest-overview">
                <SectionCard className="min-h-[220px] p-4 sm:p-5">
                  <h3 className="mt-0">结果总览</h3>
                  {loading ? (
                    <div className="space-y-3" aria-hidden="true">
                      <KpiGrid cols={4}>
                        {Array.from({ length: 8 }).map((_, index) => (
                          <SkeletonCard key={index} />
                        ))}
                      </KpiGrid>
                    </div>
                  ) : m ? (
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
                  ) : (
                    <EmptyState
                      text="运行一次回测后，这里会先给出收益、回撤和胜率摘要。"
                      hint="先看这组摘要，再进入图表或交易明细，会比直接拉长页面更容易判断结果。"
                    />
                  )}
                </SectionCard>
              </div>

              {m && runResult?.artifactId ? (
                <SectionCard className="p-4 sm:p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="mb-1 mt-0">回测制品</h3>
                      <div className="text-xs text-text-secondary">
                        artifactId: <code>{runResult.artifactId}</code>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const path = `/backtest/metrics?artifactId=${encodeURIComponent(runResult.artifactId ?? '')}`;
                        if (artifactMetricsPath === path) void artifactMetricsQ.refetch();
                        else setArtifactMetricsPath(path);
                      }}
                      disabled={artifactMetricsQ.isFetching}
                      className={backtestChipButtonCls}
                    >
                      {artifactMetricsQ.isFetching ? '加载中...' : '查看追踪指标'}
                    </button>
                  </div>
                  {artifactMetricsQ.data?.metrics ? (
                    <KpiGrid cols={3} className="mt-3">
                      <KpiCard
                        title="追踪收益"
                        value={fmtPct(artifactMetricsQ.data.metrics.totalReturn ?? null)}
                        change={artifactMetricsQ.data.metrics.totalReturn ?? undefined}
                      />
                      <KpiCard title="追踪夏普" value={fmtNum(artifactMetricsQ.data.metrics.sharpe ?? null, 2)} />
                      <KpiCard title="追踪回撤" value={fmtPct(artifactMetricsQ.data.metrics.maxDrawdown ?? null)} />
                      <KpiCard title="追踪胜率" value={fmtPct(artifactMetricsQ.data.metrics.winRate ?? null)} />
                      <KpiCard title="追踪交易数" value={artifactMetricsQ.data.metrics.totalTrades ?? '-'} />
                      <KpiCard title="追踪盈亏比" value={fmtNum(artifactMetricsQ.data.metrics.profitFactor ?? null, 2)} />
                    </KpiGrid>
                  ) : null}
                  {artifactMetricsQ.error ? <p className="mt-2 text-sm text-danger">{artifactMetricsQ.error}</p> : null}
                </SectionCard>
              ) : null}
            </>
          ) : null}

          {resultTab === 'chart' ? (
            <>
              <div id="backtest-chart">
                <SectionCard className="min-h-[360px] p-4 sm:p-5">
                  <h3 className="mt-0">净值曲线</h3>
                  {loading ? (
                    <div className="space-y-3" aria-hidden="true">
                      <Skeleton className="w-48" height={18} />
                      <Skeleton className="w-full" height={280} />
                    </div>
                  ) : equityCurve.length > 0 ? (
                    <Chart
                      option={{
                        tooltip: { trigger: 'axis' },
                        legend: { data: ['策略净值', ...(benchmarkNav.length ? ['沪深300'] : [])] },
                        grid: { top: 40, right: 20, bottom: 30, left: 50 },
                        xAxis: { type: 'category', data: equityCategories },
                        yAxis: { type: 'value', name: '净值', scale: true },
                        series: [
                          {
                            name: '策略净值',
                            type: 'line',
                            data: navSeries,
                            smooth: true,
                            itemStyle: { color: '#1a73e8' },
                            areaStyle: { opacity: 0.15 },
                            markPoint: {
                              symbol: 'arrow',
                              symbolSize: 10,
                              data: [
                                ...tradeMarkers.buy.map(([x, y]) => ({
                                  coord: [x, y],
                                  itemStyle: { color: '#ef4444' },
                                  symbolRotate: 0,
                                })),
                                ...tradeMarkers.sell.map(([x, y]) => ({
                                  coord: [x, y],
                                  itemStyle: { color: '#22c55e' },
                                  symbolRotate: 180,
                                })),
                              ],
                            },
                          },
                          ...(benchmarkNav.length
                            ? [
                                {
                                  name: '沪深300',
                                  type: 'line' as const,
                                  data: benchmarkNav,
                                  smooth: true,
                                  itemStyle: { color: '#9ca3af' },
                                },
                              ]
                            : []),
                        ],
                      }}
                      height={320}
                    />
                  ) : (
                    <EmptyState
                      text="运行回测后，这里会固定展示策略净值与基准线。"
                      hint="图表独立成页签后，不再把下方交易和诊断内容一起推成长页。"
                    />
                  )}
                </SectionCard>
              </div>

              {drawdownSeries.length > 0 ? (
                <SectionCard className="p-4 sm:p-5">
                  <h3 className="mt-0">回撤曲线</h3>
                  <LineChart
                    categories={equityCategories}
                    series={[{ name: '回撤 (%)', data: drawdownSeries, areaStyle: true, color: '#ef4444' }]}
                    height={200}
                    yAxisName="回撤 %"
                  />
                </SectionCard>
              ) : null}

              {dailyReturns.length > 0 ? (
                <SectionCard className="p-4 sm:p-5">
                  <h3 className="mt-0">每日收益率</h3>
                  <LineChart
                    categories={equityCategories.slice(1)}
                    series={[{ name: '日收益率 (%)', data: dailyReturns, type: 'bar', color: '#3b82f6' }]}
                    height={200}
                    yAxisName="收益率 %"
                  />
                </SectionCard>
              ) : null}
            </>
          ) : null}

          {resultTab === 'trades' ? (
            <div id="backtest-trades">
              <SectionCard className="p-4 sm:p-5">
                <h3 className="mt-0">交易明细</h3>
                {trades.length > 0 ? (
                  <DataTable
                    rows={trades}
                    columns={[
                      {
                        key: 'date',
                        label: '日期',
                        render: (v: unknown, row: Record<string, unknown>) =>
                          String(v ?? row.entry_date ?? row.trade_date ?? '-').slice(0, 10),
                      },
                      {
                        key: 'type',
                        label: '方向',
                        render: (v: unknown, row: Record<string, unknown>) => {
                          const d = String(v ?? row.direction ?? row.side ?? '');
                          const isBuy = /buy|买|long/i.test(d);
                          return <Badge variant={isBuy ? 'danger' : 'success'}>{d || '-'}</Badge>;
                        },
                      },
                      {
                        key: 'price',
                        label: '价格',
                        align: 'right' as const,
                        render: (v: unknown, row: Record<string, unknown>) =>
                          fmtNum((v ?? row.entry_price) as number, 2),
                      },
                      {
                        key: 'exit_price',
                        label: '平仓价',
                        align: 'right' as const,
                        render: (v: unknown) => (v != null ? fmtNum(v as number, 2) : '-'),
                      },
                      {
                        key: 'shares',
                        label: '数量',
                        align: 'right' as const,
                        render: (v: unknown, row: Record<string, unknown>) =>
                          fmtNum((v ?? row.quantity ?? row.amount) as number, 0),
                      },
                      {
                        key: 'profit',
                        label: '盈亏',
                        align: 'right' as const,
                        render: (v: unknown, row: Record<string, unknown>) => {
                          const n = Number(v ?? row.pnl ?? 0);
                          return <span className={n >= 0 ? 'text-danger' : 'text-success'}>{fmtNum(n, 2)}</span>;
                        },
                      },
                    ]}
                    pageSize={10}
                    onExport={() => exportCSV(trades, 'backtest-trades')}
                    mobileCardRender={(row) => {
                      const rawDirection = String(row.type ?? row.direction ?? row.side ?? '');
                      const isBuy = /buy|买|long/i.test(rawDirection);
                      const profit = Number(row.profit ?? row.pnl ?? 0);
                      return (
                        <div className="space-y-2 text-sm">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-xs text-text-secondary">交易日期</div>
                              <div className="font-medium">
                                {String(row.date ?? row.entry_date ?? row.trade_date ?? '-').slice(0, 10)}
                              </div>
                            </div>
                            <Badge variant={isBuy ? 'danger' : 'success'}>{rawDirection || '-'}</Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div>价格：{fmtNum((row.price ?? row.entry_price) as number, 2)}</div>
                            <div>平仓价：{row.exit_price != null ? fmtNum(row.exit_price as number, 2) : '-'}</div>
                            <div>数量：{fmtNum((row.shares ?? row.quantity ?? row.amount) as number, 0)}</div>
                            <div>
                              盈亏：
                              <span className={profit >= 0 ? 'text-danger' : 'text-success'}>{fmtNum(profit, 2)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    }}
                  />
                ) : (
                  <EmptyState text="暂无交易明细" hint="当回测没有形成交易记录时，这里会保持精简空态。" />
                )}
              </SectionCard>
            </div>
          ) : null}

          {resultTab === 'diagnostics' ? (
            <>
              {rollingMetrics.sharpe.length > 0 ? (
                <SectionCard className="p-4 sm:p-5">
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
              ) : null}

              {returnsHist.bins.length > 0 ? (
                <SectionCard className="p-4 sm:p-5">
                  <h3 className="mt-0">收益分布</h3>
                  <Chart
                    option={{
                      tooltip: { trigger: 'axis' },
                      grid: { top: 20, right: 20, bottom: 30, left: 50 },
                      xAxis: { type: 'category', data: returnsHist.bins, name: '日收益率 (%)' },
                      yAxis: { type: 'value', name: '频次' },
                      series: [
                        { type: 'bar', data: returnsHist.counts, itemStyle: { color: '#3b82f6' }, barWidth: '90%' },
                      ],
                    }}
                    height={200}
                  />
                </SectionCard>
              ) : null}

              {monthlyHeatmap.data.length > 0 ? (
                <SectionCard className="p-4 sm:p-5">
                  <h3 className="mt-0">月度收益热力图</h3>
                  <Chart
                    option={{
                      tooltip: {
                        formatter: (p: { data: number[] }) =>
                          `${monthlyHeatmap.years[p.data[1]]}年${monthlyHeatmap.months[p.data[0]]}月: ${p.data[2]}%`,
                      },
                      grid: { top: 10, right: 20, bottom: 40, left: 60 },
                      xAxis: {
                        type: 'category',
                        data: monthlyHeatmap.months.map((month) => `${month}月`),
                        splitArea: { show: true },
                      },
                      yAxis: { type: 'category', data: monthlyHeatmap.years, splitArea: { show: true } },
                      visualMap: {
                        min: -10,
                        max: 10,
                        calculable: true,
                        orient: 'horizontal',
                        left: 'center',
                        bottom: 0,
                        inRange: { color: ['#22c55e', '#f5f5f5', '#ef4444'] },
                      },
                      series: [
                        {
                          type: 'heatmap',
                          data: monthlyHeatmap.data,
                          label: { show: true, formatter: (p: { data: number[] }) => `${p.data[2]}%`, fontSize: 10 },
                        },
                      ],
                    }}
                    height={Math.max(160, monthlyHeatmap.years.length * 40 + 80)}
                  />
                </SectionCard>
              ) : null}

              {!rollingMetrics.sharpe.length && !returnsHist.bins.length && !monthlyHeatmap.data.length ? (
                <SectionCard className="p-4 sm:p-5">
                  <EmptyState text="暂无诊断指标" hint="当前结果不足以生成滚动指标、收益分布或月度热力图。" />
                </SectionCard>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {surfaceTab === 'research' ? (
        <div id="backtest-research">
          <SectionCard className="p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">Research Workflow</div>
                <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">参数优化与 Walk-Forward</h3>
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  单次回测只告诉你这次跑得怎么样。参数优化和 walk-forward 才能回答它是不是稳定、是不是过拟合。
                </p>
              </div>
              <Badge variant={optimizeApi.data || walkForwardApi.data ? 'info' : 'neutral'}>
                {optimizeApi.data || walkForwardApi.data ? '已有研究结果' : '待运行'}
              </Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {[
                { key: 'balanced', label: '均衡' },
                { key: 'sharpe', label: 'Sharpe 优先' },
                { key: 'total_return', label: '收益优先' },
              ].map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setResearchObjective(item.key as 'balanced' | 'sharpe' | 'total_return')}
                  className={backtestChipButtonCls}
                  aria-pressed={researchObjective === item.key}
                >
                  {researchObjective === item.key ? `目标: ${item.label}` : item.label}
                </button>
              ))}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
              <label className="space-y-2 text-sm text-text-secondary">
                <span>优化候选数</span>
                <input
                  type="number"
                  min={1}
                  max={24}
                  value={maxCandidates}
                  onChange={(e) => setMaxCandidates(Number(e.target.value) || 8)}
                />
              </label>
              <label className="space-y-2 text-sm text-text-secondary">
                <span>展示 TopN</span>
                <input type="number" min={1} max={12} value={topN} onChange={(e) => setTopN(Number(e.target.value) || 5)} />
              </label>
              <label className="space-y-2 text-sm text-text-secondary">
                <span>训练窗口</span>
                <input
                  type="number"
                  min={30}
                  max={720}
                  value={trainDays}
                  onChange={(e) => setTrainDays(Number(e.target.value) || 180)}
                />
              </label>
              <label className="space-y-2 text-sm text-text-secondary">
                <span>测试窗口</span>
                <input
                  type="number"
                  min={10}
                  max={365}
                  value={testDays}
                  onChange={(e) => setTestDays(Number(e.target.value) || 60)}
                />
              </label>
              <label className="space-y-2 text-sm text-text-secondary">
                <span>滑动步长</span>
                <input
                  type="number"
                  min={5}
                  max={180}
                  value={stepDays}
                  onChange={(e) => setStepDays(Number(e.target.value) || 30)}
                />
              </label>
              <label className="space-y-2 text-sm text-text-secondary">
                <span>最多折数</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={maxFolds}
                  onChange={(e) => setMaxFolds(Number(e.target.value) || 4)}
                />
              </label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  void runOptimization();
                }}
                disabled={optimizeApi.isPending}
                className={backtestChipButtonCls}
              >
                {optimizeApi.isPending ? '参数优化中...' : '运行参数优化'}
              </button>
              <button
                type="button"
                onClick={() => {
                  void runWalkForward();
                }}
                disabled={walkForwardApi.isPending}
                className={backtestChipButtonCls}
              >
                {walkForwardApi.isPending ? 'Walk-forward 运行中...' : '运行 Walk-forward'}
              </button>
            </div>
            {optimizeApi.error ? <p className="mt-3 text-sm text-danger">{optimizeApi.error}</p> : null}
            {walkForwardApi.error ? <p className="mt-3 text-sm text-danger">{walkForwardApi.error}</p> : null}

            {optimizeApi.data ? (
              <div className="mt-5 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="m-0 text-lg font-semibold text-text-primary">参数优化结果</h4>
                  <Badge variant={optimizeApi.data.bestCandidate?.success ? 'success' : 'warning'}>
                    已评估 {optimizeApi.data.evaluatedCount ?? 0} 组
                  </Badge>
                </div>
                <KpiGrid cols={4}>
                  <KpiCard title="目标函数" value={String(optimizeApi.data.objective ?? '-')} />
                  <KpiCard title="最佳候选" value={optimizeApi.data.bestCandidate?.candidateId ?? '-'} />
                  <KpiCard
                    title="最佳 Sharpe"
                    value={fmtNum(optimizeApi.data.bestCandidate?.metrics?.sharpe ?? null, 2)}
                  />
                  <KpiCard
                    title="最佳回撤"
                    value={fmtPct(optimizeApi.data.bestCandidate?.metrics?.maxDrawdown ?? null)}
                  />
                </KpiGrid>
                <DataTable
                  rows={(optimizeApi.data.candidates ?? []).map((item) => ({
                    candidateId: item.candidateId ?? '-',
                    success: item.success ? '是' : '否',
                    score: item.score == null ? '-' : fmtNum(item.score, 4),
                    params:
                      Object.entries(item.params ?? {})
                        .map(([key, value]) => `${key}:${String(value)}`)
                        .join(' / ') || '-',
                    totalReturn: fmtPct(item.metrics?.totalReturn ?? null),
                    sharpe: fmtNum(item.metrics?.sharpe ?? null, 2),
                    maxDrawdown: fmtPct(item.metrics?.maxDrawdown ?? null),
                    artifactId: item.artifactId ?? '-',
                    error: item.error ?? '-',
                  }))}
                  columns={[
                    { key: 'candidateId', label: '候选' },
                    { key: 'success', label: '成功' },
                    { key: 'score', label: '评分' },
                    { key: 'params', label: '参数' },
                    { key: 'totalReturn', label: '总收益' },
                    { key: 'sharpe', label: 'Sharpe' },
                    { key: 'maxDrawdown', label: '回撤' },
                  ]}
                  pageSize={6}
                  onExport={() => exportCSV(optimizeApi.data?.candidates ?? [], 'backtest-optimization-candidates')}
                />
              </div>
            ) : null}

            {walkForwardApi.data ? (
              <div className="mt-5 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="m-0 text-lg font-semibold text-text-primary">Walk-Forward 结果</h4>
                  <Badge variant={walkForwardApi.data.summary?.passed ? 'success' : 'warning'}>
                    {walkForwardApi.data.summary?.passed ? '通过稳健性验证' : '需要复核'}
                  </Badge>
                </div>
                <KpiGrid cols={4}>
                  <KpiCard title="折数" value={walkForwardApi.data.summary?.foldCount ?? '-'} />
                  <KpiCard title="正向占比" value={fmtPct(walkForwardApi.data.summary?.positiveFoldRatio ?? null)} />
                  <KpiCard title="平均测试 Sharpe" value={fmtNum(walkForwardApi.data.summary?.avgTestSharpe ?? null, 2)} />
                  <KpiCard title="最差回撤" value={fmtPct(walkForwardApi.data.summary?.worstDrawdown ?? null)} />
                </KpiGrid>
                <DataTable
                  rows={(walkForwardApi.data.folds ?? []).map((item) => ({
                    fold: item.fold ?? '-',
                    trainWindow: `${item.trainStart ?? '-'} ~ ${item.trainEnd ?? '-'}`,
                    testWindow: `${item.testStart ?? '-'} ~ ${item.testEnd ?? '-'}`,
                    score: item.score == null ? '-' : fmtNum(item.score, 4),
                    passed: item.passed ? '是' : '否',
                    testReturn: fmtPct(item.testMetrics?.totalReturn ?? null),
                    testSharpe: fmtNum(item.testMetrics?.sharpe ?? null, 2),
                    testDrawdown: fmtPct(item.testMetrics?.maxDrawdown ?? null),
                    error: item.error ?? '-',
                  }))}
                  columns={[
                    { key: 'fold', label: '折' },
                    { key: 'trainWindow', label: '训练窗口' },
                    { key: 'testWindow', label: '测试窗口' },
                    { key: 'score', label: '评分' },
                    { key: 'passed', label: '通过' },
                    { key: 'testReturn', label: '测试收益' },
                    { key: 'testSharpe', label: '测试 Sharpe' },
                    { key: 'testDrawdown', label: '测试回撤' },
                  ]}
                  pageSize={6}
                  onExport={() => exportCSV(walkForwardApi.data?.folds ?? [], 'backtest-walk-forward-folds')}
                />
              </div>
            ) : null}
          </SectionCard>
        </div>
      ) : null}

      {surfaceTab === 'history' ? (
        <BacktestHistoryBatch
          historyRows={mergedHistoryRows}
          historyLoading={historyQ.isFetching}
          batchCodes={batchCodes}
          onBatchCodesChange={setBatchCodes}
          onRunBatch={() => {
            void runBatch();
          }}
          batchPending={batchApi.isPending}
          batchError={batchApi.error}
          batchResults={batchResults}
        />
      ) : null}
    </PageContainer>
  );
}
