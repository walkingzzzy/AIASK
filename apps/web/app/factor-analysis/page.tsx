'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, KpiCard, KpiGrid } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';

type FactorItem = { name: string; description: string; category: string };
type LibraryResponse = { data?: { factors?: FactorItem[] } };
type IcResponse = { data?: { ic?: number; ic_ir?: number; p_value?: number; [k: string]: unknown } };
type BacktestResponse = { data?: { group_returns?: Record<string, number>; [k: string]: unknown } };
type IcHistoryItem = { date: string; ic_value?: number; rank_ic?: number; stock_count?: number };
type IcHistoryResponse = { data?: { history?: IcHistoryItem[]; [k: string]: unknown } };
type DecayPoint = { date: string; value: number };
type DecayResponse = {
  data?: {
    half_life?: number | null;
    sample_count?: number;
    decay_curve?: DecayPoint[];
    [k: string]: unknown;
  };
};

export default function FactorAnalysisPage() {
  const libraryApi = useApiMutation<LibraryResponse>();
  const icApi = useApiMutation<IcResponse>();
  const btApi = useApiMutation<BacktestResponse>();
  const icHistoryApi = useApiMutation<IcHistoryResponse>();
  const decayApi = useApiMutation<DecayResponse>();
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [factor, setFactor] = useState('momentum');
  const [loaded, setLoaded] = useState(false);

  function loadLibrary() {
    if (!loaded) { libraryApi.trigger('/factor/library'); setLoaded(true); }
  }

  const factors = useMemo(() => {
    const raw = libraryApi.data?.data?.factors ?? libraryApi.data?.data ?? [];
    return Array.isArray(raw) ? raw as FactorItem[] : [];
  }, [libraryApi.data]);

  function runAnalysis() {
    if (!validate()) return;
    const body = { factor_name: factor, stock_codes: [trimmedCode] };
    icApi.trigger('/factor/ic', { method: 'POST' }, body);
    btApi.trigger('/factor/backtest', { method: 'POST' }, body);
    icHistoryApi.trigger(`/factor/ic-history?factor_name=${encodeURIComponent(factor)}&period=20&limit=60`);
    decayApi.trigger(`/factor/decay?factor_name=${encodeURIComponent(factor)}&period=20&limit=60`);
  }

  const ic = icApi.data?.data;
  const groupReturns = btApi.data?.data?.group_returns;
  const groupBars = useMemo(() => {
    if (!groupReturns) return { cats: [] as string[], vals: [] as number[] };
    const entries = Object.entries(groupReturns).sort(([a], [b]) => a.localeCompare(b));
    return { cats: entries.map(([k]) => k), vals: entries.map(([, v]) => Number(v) || 0) };
  }, [groupReturns]);

  const icHistory = useMemo(() => {
    const raw = icHistoryApi.data?.data?.history ?? icHistoryApi.data?.data ?? [];
    const list = Array.isArray(raw) ? raw as IcHistoryItem[] : [];
    if (!list.length) return null;
    const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date));
    return {
      dates: sorted.map((r) => r.date),
      ic: sorted.map((r) => Number(r.ic_value ?? 0)),
      rankIc: sorted.map((r) => Number(r.rank_ic ?? 0)),
    };
  }, [icHistoryApi.data]);

  const decayView = useMemo(() => {
    const raw = decayApi.data?.data?.decay_curve ?? decayApi.data?.data ?? [];
    const curve = Array.isArray(raw) ? raw as DecayPoint[] : [];
    const halfLifeRaw = decayApi.data?.data?.half_life;
    const sampleCountRaw = decayApi.data?.data?.sample_count;
    if (!curve.length && halfLifeRaw == null && sampleCountRaw == null) return null;
    return {
      halfLife: typeof halfLifeRaw === 'number' ? halfLifeRaw : null,
      sampleCount: Number(sampleCountRaw ?? curve.length) || 0,
      dates: curve.map((p) => p.date),
      values: curve.map((p) => Number(p.value ?? 0)),
    };
  }, [decayApi.data]);

  const loading = icApi.isPending || btApi.isPending || icHistoryApi.isPending || decayApi.isPending;
  const error = icApi.error || btApi.error || icHistoryApi.error || decayApi.error;

  return (
    <PageContainer>
      <h1>因子分析</h1>

      <div className="flex gap-2 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} />
        <select
          value={factor}
          onChange={(e) => setFactor(e.target.value)}
          onFocus={loadLibrary}
          className="px-2 py-1 border border-border rounded text-sm min-w-[160px]"
        >
          {factors.length > 0
            ? factors.map((f) => <option key={f.name} value={f.name}>{f.name} - {f.description}</option>)
            : <option value={factor}>{factor}</option>
          }
        </select>
        <button
          onClick={runAnalysis}
          disabled={loading}
          className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm"
        >
          {loading ? '分析中...' : '运行分析'}
        </button>
      </div>

      {loading && <LoadingState text="因子分析中..." />}
      {error && <ErrorState text={error} />}

      {(ic || decayView) && (
        <KpiGrid cols={5}>
          <KpiCard title="IC" value={fmtNum(ic?.ic ?? 0, 4)} />
          <KpiCard title="IC IR" value={fmtNum(ic?.ic_ir ?? 0, 4)} />
          <KpiCard title="P-Value" value={fmtNum(ic?.p_value ?? 0, 4)} />
          <KpiCard title="信号半衰期" value={decayView?.halfLife == null ? '--' : `${decayView.halfLife}`} />
          <KpiCard title="衰减样本数" value={`${decayView?.sampleCount ?? 0}`} />
        </KpiGrid>
      )}

      {icHistory && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">IC 时序走势</h3>
          <LineChart
            categories={icHistory.dates}
            series={[
              { name: 'IC', data: icHistory.ic, color: '#1a73e8' },
              { name: 'Rank IC', data: icHistory.rankIc, color: '#f59e0b' },
            ]}
            height={260}
            yAxisName="IC值"
          />
        </SectionCard>
      )}

      {decayView && decayView.dates.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">信号衰减曲线（|IC|归一化）</h3>
          <LineChart
            categories={decayView.dates}
            series={[{ name: 'Decay', data: decayView.values, color: '#10b981' }]}
            height={240}
            yAxisName="相对强度"
          />
        </SectionCard>
      )}

      {groupBars.cats.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">因子分组回测收益</h3>
          <BarChart
            categories={groupBars.cats}
            series={[{ name: '组收益', data: groupBars.vals, color: '#6366f1' }]}
            height={280}
            yAxisName="收益率"
          />
        </SectionCard>
      )}
    </PageContainer>
  );
}