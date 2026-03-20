'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, DataTable, KpiCard, KpiGrid } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

type HoldingOp = { portfolioId: string; code: string; shares: string; costPrice: string };
type BacktestResult = { artifactId?: string; backtestId?: unknown; [k: string]: unknown };
type MetricsData = { metrics?: { totalReturn?: unknown; sharpe?: unknown; maxDrawdown?: unknown }; [k: string]: unknown };
type OptData = { optimization?: { expectedReturn?: unknown; expectedRisk?: unknown; sharpe?: unknown; weights?: unknown }; [k: string]: unknown };
type RiskData = { riskMetrics?: { var95?: unknown; var99?: unknown; cvar?: unknown; beta?: unknown; volatility?: unknown }; [k: string]: unknown };
type StressScenario = { name?: string; impact?: unknown; description?: string };
type StressData = { stressResult?: { scenarios?: StressScenario[] }; [k: string]: unknown };
type PortfolioDetailRecord = Record<string, unknown> & {
  strategyAllocations?: Array<Record<string, unknown>>;
};

function WorkbenchField({
  id,
  label,
  value,
  onChange,
  placeholder,
  className = '',
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <label htmlFor={id} className={`grid gap-1 text-xs text-text-secondary ${className}`}>
      <span>{label}</span>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary"
      />
    </label>
  );
}

export default function StrategyPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [strategy, setStrategy] = useState('ma_cross');
  const [artifactId, setArtifactId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [portfolioName, setPortfolioName] = useState('我的策略组合');
  const [holdingOp, setHoldingOp] = useState<HoldingOp>({ portfolioId: '', code: '600519', shares: '100', costPrice: '1' });
  const [backtestListPath, setBacktestListPath] = useState<string | null>(null);
  const [portfolioListPath, setPortfolioListPath] = useState<string | null>(null);
  const [portfolioDetailPath, setPortfolioDetailPath] = useState<string | null>(null);

  // GET reads → useApiQuery
  const metricsQ = useApiQuery<MetricsData>(
    artifactId ? `/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}` : null,
  );
  const backtestListQ = useApiQuery<unknown>(backtestListPath);
  const portfolioListQ = useApiQuery<unknown>(portfolioListPath);
  const portfolioDetailQ = useApiQuery<unknown>(portfolioDetailPath);

  // POST / DELETE writes → useApiMutation
  const backtestApi = useApiMutation<BacktestResult>();
  const optimizeApi = useApiMutation<OptData>();
  const riskAnalysisApi = useApiMutation<RiskData>();
  const stressTestApi = useApiMutation<StressData>();
  const actionApi = useApiMutation<unknown>();

  const loading = backtestApi.isPending || metricsQ.isFetching || backtestListQ.isFetching ||
    portfolioListQ.isFetching || portfolioDetailQ.isFetching || optimizeApi.isPending ||
    riskAnalysisApi.isPending || stressTestApi.isPending || actionApi.isPending;
  const error = formError || backtestApi.error || metricsQ.error || backtestListQ.error ||
    portfolioListQ.error || portfolioDetailQ.error || optimizeApi.error ||
    riskAnalysisApi.error || stressTestApi.error || actionApi.error;
  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, { code: trimmedCode, strategy });
      const aid = String(data?.artifactId ?? '');
      setArtifactId(aid);
    } catch { /* captured */ }
  }
  function loadBacktests() {
    const p = '/backtest/list?limit=10';
    if (p === backtestListPath) backtestListQ.refetch(); else setBacktestListPath(p);
  }
  function loadMetrics(id = artifactId) {
    const trimId = id.trim();
    if (!trimId) return setFormError('请先提供 artifactId');
    if (trimId !== artifactId) setArtifactId(trimId);
    else metricsQ.refetch();
  }
  async function createPortfolio() {
    setFormError(null);
    if (!portfolioName.trim()) return setFormError('组合名称不能为空');
    try {
      const data = await actionApi.triggerAsync('/portfolio/create', { method: 'POST' }, { name: portfolioName.trim(), initialCapital: '100000' });
      const createdId = data && typeof data === 'object' && 'portfolioId' in data ? String((data as { portfolioId?: unknown }).portfolioId ?? '') : '';
      if (createdId) {
        setHoldingOp((prev) => ({ ...prev, portfolioId: createdId }));
        const detailPath = `/portfolio/get?portfolioId=${encodeURIComponent(createdId)}`;
        if (detailPath === portfolioDetailPath) portfolioDetailQ.refetch(); else setPortfolioDetailPath(detailPath);
      }
      const p = '/portfolio/list';
      if (p === portfolioListPath) portfolioListQ.refetch(); else setPortfolioListPath(p);
    } catch { /* captured */ }
  }
  function loadPortfolios() {
    const p = '/portfolio/list';
    if (p === portfolioListPath) portfolioListQ.refetch(); else setPortfolioListPath(p);
  }
  async function addHolding() {
    setFormError(null);
    if (!/^\d+$/.test(holdingOp.portfolioId) || !/^\d{6}$/.test(holdingOp.code)) return setFormError('持仓参数不合法');
    try {
      await actionApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, holdingOp);
      const p = '/portfolio/list';
      if (p === portfolioListPath) portfolioListQ.refetch(); else setPortfolioListPath(p);
    } catch { /* captured */ }
  }
  async function removeHolding() {
    setFormError(null);
    if (!/^\d+$/.test(holdingOp.portfolioId) || !/^\d{6}$/.test(holdingOp.code)) return setFormError('持仓参数不合法');
    try {
      await actionApi.triggerAsync(`/portfolio/remove-holding?portfolioId=${encodeURIComponent(holdingOp.portfolioId)}&code=${holdingOp.code}`, { method: 'DELETE' });
      const p = '/portfolio/list';
      if (p === portfolioListPath) portfolioListQ.refetch(); else setPortfolioListPath(p);
    } catch { /* captured */ }
  }
  function loadPortfolioDetail() {
    setFormError(null);
    if (!holdingOp.portfolioId) return setFormError('请输入 portfolioId');
    const p = `/portfolio/get?portfolioId=${encodeURIComponent(holdingOp.portfolioId)}`;
    if (p === portfolioDetailPath) portfolioDetailQ.refetch(); else setPortfolioDetailPath(p);
  }
  function optimizePortfolio() {
    setFormError(null);
    if (!holdingOp.portfolioId) return setFormError('请输入 portfolioId');
    optimizeApi.trigger('/portfolio/optimize', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
  }
  function analyzeRisk() {
    setFormError(null);
    if (!holdingOp.portfolioId) return setFormError('请输入 portfolioId');
    riskAnalysisApi.trigger('/portfolio/risk-analysis', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
  }
  function runStressTest() {
    setFormError(null);
    if (!holdingOp.portfolioId) return setFormError('请输入 portfolioId');
    stressTestApi.trigger('/portfolio/stress-test', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
  }
  const metrics = metricsQ.data?.metrics;
  const optData = optimizeApi.data;
  const riskData = riskAnalysisApi.data;
  const stressData = stressTestApi.data;

  const detailObj = useMemo(() => {
    if (!portfolioDetailQ.data || typeof portfolioDetailQ.data !== 'object') return null;
    return portfolioDetailQ.data as PortfolioDetailRecord;
  }, [portfolioDetailQ.data]);
  const detailHoldings = useMemo(() => extractArray(portfolioDetailQ.data, 'holdings', 'positions', 'data') as Record<string, unknown>[], [portfolioDetailQ.data]);
  const detailStrategies = useMemo(() => extractArray(portfolioDetailQ.data, 'strategyAllocations') as Record<string, unknown>[], [portfolioDetailQ.data]);
  const backtestRows = useMemo(() => {
    const rows = extractArray(backtestListQ.data, 'results', 'items', 'data');
    return rows.map((item) => ({
      backtestId: String(item.id ?? item.backtest_id ?? '-'),
      code: String(item.code ?? '-'),
      strategy: String(item.strategy ?? '-'),
      startDate: String(item.start_date ?? '-'),
      endDate: String(item.end_date ?? '-'),
      totalReturn: item.total_return,
      maxDrawdown: item.max_drawdown,
      sharpe: item.sharpe_ratio,
      createdAt: String(item.created_at ?? '-'),
    }));
  }, [backtestListQ.data]);
  const portfolioRows = useMemo(() => (
    extractArray(portfolioListQ.data, 'portfolios', 'items', 'data').map((item) => ({
      id: item.id ?? '-',
      name: item.name ?? '-',
      description: item.description ?? '-',
      strategyAllocationCount: item.strategyAllocationCount ?? 0,
      strategyAllocationSummary: item.strategyAllocationSummary ?? '-',
      currentValue: item.currentValue,
      createdAt: item.createdAt ?? '-',
    }))
  ), [portfolioListQ.data]);

  const optWeights = useMemo(() => {
    const w = optData?.optimization?.weights;
    if (Array.isArray(w)) return w as Record<string, unknown>[];
    if (w && typeof w === 'object') return Object.entries(w as Record<string, unknown>).map(([k, v]) => ({ code: k, weight: v }));
    return [] as Record<string, unknown>[];
  }, [optData]);

  const stressScenarios = useMemo(() => {
    const s = stressData?.stressResult?.scenarios;
    if (Array.isArray(s)) return s as Record<string, unknown>[];
    return extractArray(stressData, 'scenarios', 'data') as Record<string, unknown>[];
  }, [stressData]);

  return (
    <PageContainer>
      <h1>策略工作台</h1>
      <p className="mt-2 text-sm text-text-secondary">建议先在试验区跑回测、确认 artifact 与收益指标，再进入落地区创建组合、调仓并做优化与风控分析。</p>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <KpiGrid cols={3}>
        <KpiCard title="Artifact ID" value={artifactId || null} />
        <KpiCard title="Backtest ID" value={backtestApi.data?.backtestId != null ? String(backtestApi.data.backtestId) : null} />
        <KpiCard title="总收益" value={metrics?.totalReturn != null ? fmtPct(Number(metrics.totalReturn)) : null} change={metrics?.totalReturn != null ? Number(metrics.totalReturn) : null} />
        <KpiCard title="夏普比率" value={metrics?.sharpe != null ? fmtNum(Number(metrics.sharpe), 2) : null} />
        <KpiCard title="最大回撤" value={metrics?.maxDrawdown != null ? fmtPct(Number(metrics.maxDrawdown)) : null} />
      </KpiGrid>

      <SectionCard>
        <h3 className="mt-0">试验区 · 回测执行</h3>
        <fieldset className="mb-4 rounded-xl border border-border bg-surface-alt/30 p-3">
          <legend className="px-1 text-sm font-medium text-text-primary">运行新的回测</legend>
          <p className="mt-1 mb-3 text-xs text-text-secondary">先确认标的和策略标识，再运行回测并保留 artifactId 供后续指标刷新。</p>
          <form onSubmit={runBacktest} className="grid gap-3 lg:grid-cols-[160px_220px_auto_auto] items-end">
            <StockCodeInput id="strategy-backtest-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
            <WorkbenchField
              id="strategy-backtest-name"
              label="策略标识"
              value={strategy}
              onChange={setStrategy}
              placeholder="例如 ma_cross"
            />
            <button type="submit">运行回测</button>
            <button type="button" onClick={loadBacktests}>最近回测</button>
          </form>
        </fieldset>
        <fieldset className="rounded-xl border border-border bg-surface-alt/30 p-3">
          <legend className="px-1 text-sm font-medium text-text-primary">回测结果定位</legend>
          <div className="grid gap-3 md:grid-cols-[minmax(0,260px)_auto] items-end">
            <WorkbenchField
              id="strategy-artifact-id"
              label="Artifact ID"
              value={artifactId}
              onChange={setArtifactId}
              placeholder="粘贴或保留最近一次回测的 artifactId"
            />
            <div className="flex gap-2">
              <button type="button" onClick={() => loadMetrics()}>刷新指标</button>
            </div>
          </div>
        </fieldset>
        {backtestRows.length > 0 && (
          <DataTable
            rows={backtestRows}
            columns={[
              { key: 'backtestId', label: '回测ID' },
              { key: 'code', label: '代码' },
              { key: 'strategy', label: '策略' },
              { key: 'startDate', label: '开始日期' },
              { key: 'endDate', label: '结束日期' },
              { key: 'totalReturn', label: '总收益', align: 'right', render: (value) => fmtPct(Number(value ?? 0)) },
              { key: 'maxDrawdown', label: '最大回撤', align: 'right', render: (value) => fmtPct(Number(value ?? 0)) },
              { key: 'sharpe', label: 'Sharpe', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'createdAt', label: '创建时间' },
            ]}
            pageSize={6}
            searchable
          />
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">落地区 · 组合管理</h3>
        <fieldset className="mb-4 rounded-xl border border-border bg-surface-alt/30 p-3">
          <legend className="px-1 text-sm font-medium text-text-primary">创建组合</legend>
          <p className="mt-1 mb-3 text-xs text-text-secondary">先建组合容器，再把选定策略和持仓逐步落地到组合里。</p>
          <div className="grid gap-3 md:grid-cols-[minmax(0,240px)_auto_auto] items-end">
            <WorkbenchField
              id="strategy-portfolio-name"
              label="组合名称"
              value={portfolioName}
              onChange={setPortfolioName}
              placeholder="例如 我的策略组合"
            />
            <button type="button" onClick={createPortfolio}>创建组合</button>
            <button type="button" onClick={loadPortfolios}>组合列表</button>
          </div>
        </fieldset>
        <fieldset className="rounded-xl border border-border bg-surface-alt/30 p-3">
          <legend className="px-1 text-sm font-medium text-text-primary">持仓与详情操作</legend>
          <div className="grid gap-3 lg:grid-cols-[140px_140px_120px_120px_auto_auto_auto] items-end">
            <WorkbenchField
              id="strategy-portfolio-id"
              label="组合 ID"
              value={holdingOp.portfolioId}
              onChange={(value) => setHoldingOp({ ...holdingOp, portfolioId: value })}
              placeholder="输入 portfolioId"
            />
            <WorkbenchField
              id="strategy-holding-code"
              label="股票代码"
              value={holdingOp.code}
              onChange={(value) => setHoldingOp({ ...holdingOp, code: value.slice(0, 6) })}
              placeholder="6 位股票代码"
            />
            <WorkbenchField
              id="strategy-holding-shares"
              label="持仓股数"
              value={holdingOp.shares}
              onChange={(value) => setHoldingOp({ ...holdingOp, shares: value })}
              placeholder="例如 100"
            />
            <WorkbenchField
              id="strategy-holding-cost"
              label="成本价"
              value={holdingOp.costPrice}
              onChange={(value) => setHoldingOp({ ...holdingOp, costPrice: value })}
              placeholder="例如 12.56"
            />
            <button type="button" onClick={addHolding}>加仓</button>
            <button type="button" onClick={removeHolding}>减仓</button>
            <button type="button" onClick={loadPortfolioDetail}>查看详情</button>
          </div>
        </fieldset>
        {portfolioRows.length > 0 && (
          <DataTable
            rows={portfolioRows}
            columns={[
              { key: 'id', label: '组合ID' },
              { key: 'name', label: '组合名称' },
              { key: 'description', label: '描述' },
              { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
              { key: 'strategyAllocationSummary', label: '策略配置' },
              { key: 'currentValue', label: '当前资产', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'createdAt', label: '创建时间' },
            ]}
            pageSize={6}
            searchable
            onRowClick={(row) => {
              const selectedId = String(row.id ?? '').trim();
              if (!selectedId || selectedId === '-') return;
              setHoldingOp((prev) => ({ ...prev, portfolioId: selectedId }));
              const detailPath = `/portfolio/get?portfolioId=${encodeURIComponent(selectedId)}`;
              if (detailPath === portfolioDetailPath) portfolioDetailQ.refetch(); else setPortfolioDetailPath(detailPath);
            }}
          />
        )}
        {detailObj && (
          <div className="mt-3">
            <KpiGrid cols={4}>
              <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
              <KpiCard title="总资产" value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null} />
              <KpiCard title="总收益" value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null} change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null} />
              <KpiCard title="持仓数" value={detailHoldings.length || null} />
            </KpiGrid>
            {detailStrategies.length > 0 && (
              <DataTable
                rows={detailStrategies}
                columns={[
                  { key: 'strategyId', label: '策略ID', render: (_value, row) => String(row.strategyId ?? row.strategy_id ?? '-') },
                  { key: 'weight', label: '权重', align: 'right', render: (value) => fmtPct(Number(value ?? 0) * 100) },
                ]}
                className="mt-3"
              />
            )}
            {detailHoldings.length > 0 && (
              <DataTable rows={detailHoldings} pageSize={10} onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')} />
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">落地区 · 组合优化与风控</h3>
        <p className="mt-1 text-sm text-text-secondary">以下动作默认基于当前填写的组合 ID 执行，适合在持仓落地后继续做优化、风险和压力校验。</p>
        <div className="flex gap-2">
          <button type="button" onClick={optimizePortfolio}>优化配置</button>
          <button type="button" onClick={analyzeRisk}>风险分析</button>
          <button type="button" onClick={runStressTest}>压力测试</button>
        </div>

        {optData?.optimization && (
          <div className="mt-3">
            <KpiGrid cols={3}>
              <KpiCard title="预期收益" value={optData.optimization.expectedReturn != null ? fmtPct(Number(optData.optimization.expectedReturn)) : null} />
              <KpiCard title="预期风险" value={optData.optimization.expectedRisk != null ? fmtPct(Number(optData.optimization.expectedRisk)) : null} />
              <KpiCard title="夏普比率" value={optData.optimization.sharpe != null ? fmtNum(Number(optData.optimization.sharpe), 2) : null} />
            </KpiGrid>
            {optWeights.length > 0 && (
              <DataTable rows={optWeights} onExport={() => exportCSV(optWeights, 'optimization-weights')} />
            )}
          </div>
        )}

        {riskData?.riskMetrics && (
          <div className="mt-3">
            <KpiGrid cols={3}>
              <KpiCard title="VaR (95%)" value={riskData.riskMetrics.var95 != null ? fmtPct(Number(riskData.riskMetrics.var95)) : null} />
              <KpiCard title="VaR (99%)" value={riskData.riskMetrics.var99 != null ? fmtPct(Number(riskData.riskMetrics.var99)) : null} />
              <KpiCard title="CVaR" value={riskData.riskMetrics.cvar != null ? fmtPct(Number(riskData.riskMetrics.cvar)) : null} />
              <KpiCard title="Beta" value={riskData.riskMetrics.beta != null ? fmtNum(Number(riskData.riskMetrics.beta), 2) : null} />
              <KpiCard title="波动率" value={riskData.riskMetrics.volatility != null ? fmtPct(Number(riskData.riskMetrics.volatility)) : null} />
            </KpiGrid>
          </div>
        )}

        {stressScenarios.length > 0 && (
          <div className="mt-3">
            <DataTable
              rows={stressScenarios}
              columns={[
                { key: 'name', label: '场景' },
                { key: 'impact', label: '影响', align: 'right' as const, render: (v: unknown) => {
                  const n = Number(v);
                  return <span style={{ color: n < 0 ? '#ef4444' : '#10b981' }}>{fmtPct(n)}</span>;
                }},
                { key: 'description', label: '描述' },
              ]}
              onExport={() => exportCSV(stressScenarios, 'stress-test')}
            />
          </div>
        )}
      </SectionCard>
    </PageContainer>
  );
}
