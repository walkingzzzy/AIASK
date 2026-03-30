'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  PageContainer,
  SectionCard,
  KpiCard,
  KpiGrid,
  StockCodeInput,
  DataTable,
  Badge,
  Skeleton,
  SkeletonCard,
  SkeletonTable,
} from '@/components/ui';
import { LineChart, Chart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
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
  code: string;
  strategy: string;
  totalReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  ts: number;
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
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NAV_CARD_CLS =
  'panel-soft rounded-[24px] p-4 text-left text-sm transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(15,23,42,0.2)]';

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

  // P3-3: Batch backtest
  const batchApi = useApiMutation<BacktestBatchResponse>();
  const [batchCodes, setBatchCodes] = useState('');
  const [batchResults, setBatchResults] = useState<BacktestBatchResultItem[]>([]);
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
    } catch {
      /* captured by hook */
    }
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

  const inputCls = 'text-sm text-text-primary';
  const labelCls = 'text-xs text-text-secondary';
  const strategyLabel = STRATEGIES.find((item) => item.value === strategy)?.label ?? strategy;
  const runStatusLabel = loading ? '运行中' : m ? '已生成结果' : '等待运行';
  const runStatusVariant = loading ? 'warning' : m ? 'success' : 'neutral';
  const dateRangeLabel = `${startDate || '-'} ~ ${endDate || '-'}`;
  const configurationSummary = showAdvanced
    ? `初始资金 ${fmtAmount(initialCapital)} · 手续费 ${fmtNum(commission * 100, 2)}% · 滑点 ${fmtNum(slippage * 100, 2)}%`
    : '使用默认成本设定或模板，适合先完成第一轮策略可行性判断';

  function applyCostPreset(preset: (typeof COST_PRESETS)[number]) {
    setInitialCapital(preset.initialCapital);
    setCommission(preset.commission);
    setSlippage(preset.slippage);
    setShowAdvanced(true);
  }

  const hasAnyResultBlock = loading || Boolean(error) || Boolean(runFailure) || Boolean(m);

  function scrollToSection(id: string) {
    if (typeof document === 'undefined') return;
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <PageContainer className="app-theme-strategy">
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Backtest Workspace</Badge>
              <Badge variant={runStatusVariant}>{runStatusLabel}</Badge>
              <Badge variant={runResult?.artifactId ? 'success' : 'neutral'}>
                {runResult?.artifactId ? `Artifact ${runResult.artifactId}` : '尚未生成 Artifact'}
              </Badge>
              {from ? <Badge variant="neutral">来源 {from}</Badge> : null}
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              回测分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页把策略回测配置、结果阅读和跨标的比较收进一条完整链路。先完成参数配置并运行回测，再顺着摘要、净值曲线、历史对比和批量回测去判断一个策略是不是值得继续推进。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="submit" form="backtest-config-form" disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
                {loading ? '运行中...' : '运行回测'}
              </button>
              <button
                type="button"
                onClick={() => scrollToSection('backtest-overview')}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                查看结果总览
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-chart')} className={CHIP_BUTTON_CLS}>
                看净值曲线
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-history')} className={CHIP_BUTTON_CLS}>
                看历史对比
              </button>
              <button type="button" onClick={() => scrollToSection('backtest-batch')} className={CHIP_BUTTON_CLS}>
                看批量回测
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '600519'}</div>
                <div className="mt-1 text-xs text-text-secondary">{strategyLabel}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">回测区间</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{startDate.slice(5)}</div>
                <div className="mt-1 text-xs text-text-secondary">{dateRangeLabel}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关键读数</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{m ? fmtPct(m.total_return) : '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {m ? `回撤 ${fmtPct(m.max_drawdown)}` : '等待回测结果'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {batchResults.length > 0 ? batchResults.length : hasAnyResultBlock ? '对比' : '运行'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {batchResults.length > 0
                    ? '批量结果已可比较'
                    : hasAnyResultBlock
                      ? '继续看历史与批量验证'
                      : '先完成首轮回测'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前配置</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  策略：
                  <span className="font-medium text-text-primary">{strategyLabel}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  日期：
                  <span className="font-medium text-text-primary">{dateRangeLabel}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  成本：
                  <span className="font-medium text-text-primary">{configurationSummary}</span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先确认标的、策略和日期区间，避免错误的样本设置污染整轮判断。</div>
                <div className={NOTE_CARD_CLS}>2. 再看总收益、回撤和胜率，先判断这次回测值不值得继续展开。</div>
                <div className={NOTE_CARD_CLS}>
                  3. 最后再看历史对比和批量回测，确认结果是否具有可复制性，而不是一次性幸运样本。
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="策略" value={strategyLabel} />
        <KpiCard title="总收益" value={m ? fmtPct(m.total_return) : null} change={m?.total_return ?? undefined} />
        <KpiCard title="夏普比率" value={m ? fmtNum(m.sharpe_ratio, 2) : null} />
        <KpiCard title="最大回撤" value={m ? fmtPct(m.max_drawdown) : null} />
        <KpiCard title="交易次数" value={m?.trades_count ?? null} />
      </KpiGrid>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Configuration Workspace</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">回测配置</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              按“基础参数 → 策略参数 →
              成本假设”的顺序完成配置，减少首屏参数墙带来的理解成本，也让回测逻辑更容易被快速复查。
            </p>
          </div>
        </div>

        <form id="backtest-config-form" onSubmit={runBacktest} className="mt-4 grid gap-4 xl:grid-cols-3">
          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="eyebrow">Basic Setup</div>
            <div className="mt-4 grid gap-3">
              <StockCodeInput
                id="backtest-stock-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
              />
              <label htmlFor="backtest-strategy" className="grid gap-1">
                <span className={labelCls}>策略</span>
                <select
                  id="backtest-strategy"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  className={`${inputCls} w-full`}
                >
                  {STRATEGIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label htmlFor="backtest-start-date" className="grid gap-1">
                  <span className={labelCls}>开始日期</span>
                  <input
                    id="backtest-start-date"
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className={`${inputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-end-date" className="grid gap-1">
                  <span className={labelCls}>结束日期</span>
                  <input
                    id="backtest-end-date"
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className={`${inputCls} w-full`}
                  />
                </label>
              </div>
            </div>
            <div className={`${NOTE_CARD_CLS} mt-4`}>
              先完成基础参数，再去调整策略细节和成本假设；首轮判断更看方向性，不必一开始就把每个参数调到极细。
            </div>
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="eyebrow">Strategy Setup</div>
            <div className="mt-4">
              {strategy === 'ma_cross' ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label htmlFor="backtest-short-period" className="grid gap-1">
                    <span className={labelCls}>短周期</span>
                    <input
                      id="backtest-short-period"
                      type="number"
                      value={shortPeriod}
                      onChange={(e) => setShortPeriod(+e.target.value)}
                      min={2}
                      max={100}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                  <label htmlFor="backtest-long-period" className="grid gap-1">
                    <span className={labelCls}>长周期</span>
                    <input
                      id="backtest-long-period"
                      type="number"
                      value={longPeriod}
                      onChange={(e) => setLongPeriod(+e.target.value)}
                      min={5}
                      max={250}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                </div>
              ) : null}
              {strategy === 'momentum' ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label htmlFor="backtest-lookback" className="grid gap-1">
                    <span className={labelCls}>回看周期</span>
                    <input
                      id="backtest-lookback"
                      type="number"
                      value={lookback}
                      onChange={(e) => setLookback(+e.target.value)}
                      min={5}
                      max={120}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                  <label htmlFor="backtest-threshold" className="grid gap-1">
                    <span className={labelCls}>阈值</span>
                    <input
                      id="backtest-threshold"
                      type="number"
                      value={threshold}
                      onChange={(e) => setThreshold(+e.target.value)}
                      step={0.005}
                      min={0}
                      max={0.5}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                </div>
              ) : null}
              {strategy === 'rsi' ? (
                <div className="grid gap-3 sm:grid-cols-3">
                  <label htmlFor="backtest-rsi-period" className="grid gap-1">
                    <span className={labelCls}>RSI 周期</span>
                    <input
                      id="backtest-rsi-period"
                      type="number"
                      value={rsiPeriod}
                      onChange={(e) => setRsiPeriod(+e.target.value)}
                      min={2}
                      max={50}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                  <label htmlFor="backtest-oversold" className="grid gap-1">
                    <span className={labelCls}>超卖线</span>
                    <input
                      id="backtest-oversold"
                      type="number"
                      value={oversold}
                      onChange={(e) => setOversold(+e.target.value)}
                      min={5}
                      max={50}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                  <label htmlFor="backtest-overbought" className="grid gap-1">
                    <span className={labelCls}>超买线</span>
                    <input
                      id="backtest-overbought"
                      type="number"
                      value={overbought}
                      onChange={(e) => setOverbought(+e.target.value)}
                      min={50}
                      max={95}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                </div>
              ) : null}
              {strategy === 'buy_and_hold' ? (
                <div className={NOTE_CARD_CLS}>买入持有不需要额外策略参数，适合拿来做基准对照或快速 sanity check。</div>
              ) : null}
            </div>
            {strategy !== 'buy_and_hold' ? (
              <div className={`${NOTE_CARD_CLS} mt-4`}>
                不同策略的参数只负责表达交易节奏，不负责替代样本验证。先看结果方向，再决定是否继续细调参数。
              </div>
            ) : null}
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="eyebrow">Cost Setup</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {COST_PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => applyCostPreset(preset)}
                  className={CHIP_BUTTON_CLS}
                >
                  {preset.label}
                </button>
              ))}
              <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className={CHIP_BUTTON_CLS}>
                {showAdvanced ? '收起高级选项' : '展开高级选项'}
              </button>
            </div>
            {showAdvanced ? (
              <div className="mt-4 grid gap-3">
                <label htmlFor="backtest-initial-capital" className="grid gap-1">
                  <span className={labelCls}>初始资金</span>
                  <input
                    id="backtest-initial-capital"
                    type="number"
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(+e.target.value)}
                    min={10000}
                    step={10000}
                    className={`${inputCls} w-full`}
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label htmlFor="backtest-commission" className="grid gap-1">
                    <span className={labelCls}>手续费率</span>
                    <input
                      id="backtest-commission"
                      type="number"
                      value={commission}
                      onChange={(e) => setCommission(+e.target.value)}
                      step={0.0001}
                      min={0}
                      max={0.01}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                  <label htmlFor="backtest-slippage" className="grid gap-1">
                    <span className={labelCls}>滑点</span>
                    <input
                      id="backtest-slippage"
                      type="number"
                      value={slippage}
                      onChange={(e) => setSlippage(+e.target.value)}
                      step={0.0001}
                      min={0}
                      max={0.01}
                      className={`${inputCls} w-full`}
                    />
                  </label>
                </div>
              </div>
            ) : (
              <div className={`${NOTE_CARD_CLS} mt-4`}>
                可以先点上方模板快速填入成本参数；只有在需要贴近真实成交时，再展开高级选项微调手续费和滑点。
              </div>
            )}
            {showAdvanced ? <div className={`${NOTE_CARD_CLS} mt-4`}>{configurationSummary}</div> : null}
          </div>
        </form>
      </SectionCard>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="eyebrow">Reading Flow</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">结果阅读顺序</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              移动端优先看摘要，再看净值曲线，最后按需展开交易明细、历史对比和批量结果，避免一进入就是长表格。
            </p>
          </div>
          <Badge variant={hasAnyResultBlock ? 'info' : 'neutral'}>{hasAnyResultBlock ? '已有结果' : '等待运行'}</Badge>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <button type="button" onClick={() => scrollToSection('backtest-overview')} className={NAV_CARD_CLS}>
            <div className="font-medium text-text-primary">1. 先看结果总览</div>
            <div className="mt-2 text-xs text-text-secondary">快速判断收益、回撤和胜率是否值得继续分析。</div>
          </button>
          <button type="button" onClick={() => scrollToSection('backtest-chart')} className={NAV_CARD_CLS}>
            <div className="font-medium text-text-primary">2. 再看净值曲线</div>
            <div className="mt-2 text-xs text-text-secondary">确认收益是否平滑、是否依赖单段行情。</div>
          </button>
          <button type="button" onClick={() => scrollToSection('backtest-history')} className={NAV_CARD_CLS}>
            <div className="font-medium text-text-primary">3. 对比历史结果</div>
            <div className="mt-2 text-xs text-text-secondary">横向比较策略与标的，避免只盯一次结果。</div>
          </button>
          <button type="button" onClick={() => scrollToSection('backtest-batch')} className={NAV_CARD_CLS}>
            <div className="font-medium text-text-primary">4. 最后看批量回测</div>
            <div className="mt-2 text-xs text-text-secondary">把同一策略放到多只股票上，检验可复制性。</div>
          </button>
        </div>
        {m ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="metric-tile rounded-[22px] px-4 py-3 text-sm">
              <div className="text-xs text-text-secondary">当前结论</div>
              <div className="mt-2 font-medium text-text-primary">
                {String(code)} · {strategyLabel}
              </div>
            </div>
            <div className="metric-tile rounded-[22px] px-4 py-3 text-sm">
              <div className="text-xs text-text-secondary">总收益</div>
              <div
                className={
                  Number(m.total_return ?? 0) >= 0 ? 'mt-2 font-medium text-danger' : 'mt-2 font-medium text-success'
                }
              >
                {fmtPct(m.total_return)}
              </div>
            </div>
            <div className="metric-tile rounded-[22px] px-4 py-3 text-sm">
              <div className="text-xs text-text-secondary">最大回撤</div>
              <div className="mt-2 font-medium text-text-primary">{fmtPct(m.max_drawdown)}</div>
            </div>
            <div className="metric-tile rounded-[22px] px-4 py-3 text-sm">
              <div className="text-xs text-text-secondary">交易次数</div>
              <div className="mt-2 font-medium text-text-primary">{m.trades_count ?? '-'}</div>
            </div>
          </div>
        ) : null}
      </SectionCard>
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

      <div id="backtest-overview">
        <SectionCard className="mt-4 min-h-[220px] p-4 sm:p-5">
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
              hint="首屏先看这组摘要，再继续看净值曲线和交易明细，会比直接进入长表格更容易判断结果是否值得继续分析。"
            />
          )}
        </SectionCard>
      </div>

      <div id="backtest-chart">
        <SectionCard className="mt-4 min-h-[360px] p-4 sm:p-5">
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
              text="主图区域已预留完成。"
              hint="运行回测后，这里会固定显示策略净值与基准线，避免结果返回时把下方内容整体推移。"
            />
          )}
        </SectionCard>
      </div>

      {m && (
        <>
          {runResult?.artifactId ? (
            <SectionCard className="mt-4 p-4 sm:p-5">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="mt-0 mb-1">回测制品</h3>
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
                  className={CHIP_BUTTON_CLS}
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
              {artifactMetricsQ.error ? <p className="text-danger text-sm mt-2">{artifactMetricsQ.error}</p> : null}
            </SectionCard>
          ) : null}

          {drawdownSeries.length > 0 && (
            <SectionCard className="mt-4 p-4 sm:p-5">
              <h3 className="mt-0">回撤曲线</h3>
              <LineChart
                categories={equityCategories}
                series={[{ name: '回撤 (%)', data: drawdownSeries, areaStyle: true, color: '#ef4444' }]}
                height={200}
                yAxisName="回撤 %"
              />
            </SectionCard>
          )}

          {dailyReturns.length > 0 && (
            <SectionCard className="mt-4 p-4 sm:p-5">
              <h3 className="mt-0">每日收益率</h3>
              <LineChart
                categories={equityCategories.slice(1)}
                series={[{ name: '日收益率 (%)', data: dailyReturns, type: 'bar', color: '#3b82f6' }]}
                height={200}
                yAxisName="收益率 %"
              />
            </SectionCard>
          )}

          {trades.length > 0 && (
            <div id="backtest-trades">
              <SectionCard className="mt-4 p-4 sm:p-5">
                <h3 className="mt-0">交易明细</h3>
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
                      render: (v: unknown, row: Record<string, unknown>) => fmtNum((v ?? row.entry_price) as number, 2),
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
              </SectionCard>
            </div>
          )}

          {/* P2-3: Rolling Sharpe & Drawdown */}
          {rollingMetrics.sharpe.length > 0 && (
            <SectionCard className="mt-4 p-4 sm:p-5">
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
            <SectionCard className="mt-4 p-4 sm:p-5">
              <h3 className="mt-0">收益分布</h3>
              <Chart
                option={{
                  tooltip: { trigger: 'axis' },
                  grid: { top: 20, right: 20, bottom: 30, left: 50 },
                  xAxis: { type: 'category', data: returnsHist.bins, name: '日收益率 (%)' },
                  yAxis: { type: 'value', name: '频次' },
                  series: [{ type: 'bar', data: returnsHist.counts, itemStyle: { color: '#3b82f6' }, barWidth: '90%' }],
                }}
                height={200}
              />
            </SectionCard>
          )}

          {/* P2-2: Monthly Returns Heatmap */}
          {monthlyHeatmap.data.length > 0 && (
            <SectionCard className="mt-4 p-4 sm:p-5">
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
                    data: monthlyHeatmap.months.map((m) => `${m}月`),
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
          )}
        </>
      )}

      <div id="backtest-history">
        <SectionCard className="mt-4 min-h-[240px] p-4 sm:p-5">
          <h3 className="mt-0">回测历史对比 {mergedHistoryRows.length > 0 ? `(${mergedHistoryRows.length})` : ''}</h3>
          {historyQ.isFetching ? (
            <SkeletonTable rows={5} cols={7} />
          ) : mergedHistoryRows.length > 0 ? (
            <DataTable
              rows={mergedHistoryRows}
              columns={[
                { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                { key: 'strategy', label: '策略' },
                {
                  key: 'totalReturn',
                  label: '总收益',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
                {
                  key: 'sharpe',
                  label: '夏普',
                  align: 'right' as const,
                  render: (v: unknown) => fmtNum(v as number, 2),
                },
                {
                  key: 'maxDrawdown',
                  label: '最大回撤',
                  align: 'right' as const,
                  render: (v: unknown) => fmtPct(v as number),
                },
                { key: 'winRate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
                {
                  key: 'ts',
                  label: '时间',
                  render: (v: unknown) => {
                    const t = v as number;
                    return t > 0 ? new Date(t).toLocaleString('zh-CN') : '-';
                  },
                },
              ]}
              onExport={() => exportCSV(mergedHistoryRows, 'backtest-history')}
              mobileCardRender={(row) => (
                <div className="space-y-2 text-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs text-text-secondary">标的 / 策略</div>
                      <div className="font-medium">
                        <StockLink code={String(row.code)} /> · {String(row.strategy ?? '-')}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-text-secondary">总收益</div>
                      <div
                        className={
                          Number(row.totalReturn ?? 0) >= 0 ? 'text-danger font-medium' : 'text-success font-medium'
                        }
                      >
                        {fmtPct(Number(row.totalReturn ?? 0))}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>夏普：{fmtNum(Number(row.sharpe ?? 0), 2)}</div>
                    <div>胜率：{fmtPct(Number(row.winRate ?? 0))}</div>
                    <div>回撤：{fmtPct(Number(row.maxDrawdown ?? 0))}</div>
                    <div>时间：{row.ts ? new Date(Number(row.ts)).toLocaleDateString('zh-CN') : '-'}</div>
                  </div>
                </div>
              )}
            />
          ) : (
            <EmptyState
              text="还没有可对比的历史回测。"
              hint="运行过的结果会自动进入这里，方便横向比较不同标的和策略。"
            />
          )}
        </SectionCard>
      </div>

      {/* P3-3: Batch Backtest */}
      <div id="backtest-batch">
        <SectionCard className="mt-4 min-h-[220px] p-4 sm:p-5">
          <h3 className="mt-0">批量回测对比</h3>
          <div className="panel-soft mt-3 flex flex-wrap items-end gap-3 rounded-[24px] p-4">
            <div className="grid gap-1">
              <label htmlFor="backtest-batch-codes" className={labelCls}>
                股票代码（逗号分隔）
              </label>
              <input
                id="backtest-batch-codes"
                value={batchCodes}
                onChange={(e) => setBatchCodes(e.target.value)}
                placeholder="600519,000858,601318"
                className={`${inputCls} w-[280px]`}
              />
            </div>
            <button type="button" onClick={runBatch} disabled={batchApi.isPending} className={HERO_PRIMARY_BUTTON_CLS}>
              {batchApi.isPending ? '运行中...' : '批量回测'}
            </button>
          </div>
          {batchApi.error ? <p className="text-danger text-sm mt-2">{batchApi.error}</p> : null}
          {batchApi.isPending ? (
            <div className="mt-3">
              <SkeletonTable rows={4} cols={6} />
            </div>
          ) : batchResults.length > 0 ? (
            <DataTable
              rows={batchResults}
              columns={[
                { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                {
                  key: 'success',
                  label: '状态',
                  render: (v: unknown) => {
                    const success = v !== false;
                    return <Badge variant={success ? 'success' : 'danger'}>{success ? '成功' : '失败'}</Badge>;
                  },
                },
                {
                  key: 'total_return',
                  label: '总收益',
                  align: 'right' as const,
                  render: (v: unknown) =>
                    v == null ? (
                      '-'
                    ) : (
                      <span className={Number(v) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(Number(v))}</span>
                    ),
                },
                {
                  key: 'sharpe_ratio',
                  label: '夏普',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtNum(Number(v), 2)),
                },
                {
                  key: 'max_drawdown',
                  label: '最大回撤',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtPct(Number(v))),
                },
                {
                  key: 'win_rate',
                  label: '胜率',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtPct(Number(v))),
                },
                { key: 'trades_count', label: '交易次数', align: 'right' as const },
                { key: 'reasonCode', label: '失败代码' },
                { key: 'reason', label: '失败原因' },
              ]}
              onExport={() => exportCSV(batchResults, 'batch-backtest')}
              mobileCardRender={(row) => {
                const success = row.success !== false;
                return (
                  <div className="space-y-2 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-xs text-text-secondary">股票代码</div>
                        <div className="font-medium">
                          <StockLink code={String(row.code)} />
                        </div>
                      </div>
                      <Badge variant={success ? 'success' : 'danger'}>{success ? '成功' : '失败'}</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        总收益：
                        {row.total_return == null ? (
                          '-'
                        ) : (
                          <span className={Number(row.total_return) >= 0 ? 'text-danger' : 'text-success'}>
                            {fmtPct(Number(row.total_return))}
                          </span>
                        )}
                      </div>
                      <div>夏普：{row.sharpe_ratio == null ? '-' : fmtNum(Number(row.sharpe_ratio), 2)}</div>
                      <div>最大回撤：{row.max_drawdown == null ? '-' : fmtPct(Number(row.max_drawdown))}</div>
                      <div>胜率：{row.win_rate == null ? '-' : fmtPct(Number(row.win_rate))}</div>
                      <div>交易次数：{fmtNum((row.trades_count ?? 0) as number, 0)}</div>
                      <div>失败代码：{String(row.reasonCode ?? '-')}</div>
                    </div>
                    {!success && row.reason ? (
                      <div className="text-xs text-text-secondary">失败原因：{String(row.reason)}</div>
                    ) : null}
                  </div>
                );
              }}
            />
          ) : (
            <EmptyState
              text="输入多只股票代码后，这里会显示批量回测对比表。"
              hint="结果区已固定预留，批量运行完成后不会把页面其他模块整体挤开。"
            />
          )}
        </SectionCard>
      </div>
    </PageContainer>
  );
}
