'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, StockCodeInput } from '@/components/ui';
import { PieChart, BarChart, LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { useStockCode } from '@/hooks/use-stock-code';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';

type OptData = { optimization?: { expectedReturn?: number; expectedRisk?: number; sharpe?: number; weights?: Record<string, number> | Array<{ code: string; weight: number }> } };
type RiskData = { riskMetrics?: { var95?: number; var99?: number; cvar?: number; beta?: number; volatility?: number; riskContribution?: Record<string, number> } };
type StressScenario = { name?: string; impact?: number; description?: string };
type StressData = { stressResult?: { scenarios?: StressScenario[] } };
type PortfolioDetailRecord = Record<string, unknown> & {
  strategyAllocations?: Array<Record<string, unknown>>;
};

export default function PortfolioPage() {
  const [portfolioId, setPortfolioId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Create portfolio
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newCapital, setNewCapital] = useState('1000000');
  const createApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.portfolio()]] });

  // Add holding
  const { code: holdCode, setCode: setHoldCode, codeError: holdCodeError, validate: validateHold, trimmedCode: holdTrimmed } = useStockCode();
  const [holdShares, setHoldShares] = useState('100');
  const [holdCost, setHoldCost] = useState('');
  const addHoldingApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.portfolio()]] });

  // Read queries
  const listQ = useApiQuery<unknown>('/portfolio/list', {
    parse: (raw) => ensureRecordOrArray(raw, '组合列表'),
  });
  const detailQ = useApiQuery<unknown>(
    portfolioId.trim() ? `/portfolio/get?portfolioId=${encodeURIComponent(portfolioId.trim())}` : null,
    {
      parse: (raw) => ensureRecordOrArray(raw, '组合详情'),
    },
  );

  // POST computations (user-triggered, keep as mutations)
  const optimizeApi = useApiMutation<OptData>({ parse: (raw) => ensureRecord(raw, '组合优化') as OptData });
  const riskApi = useApiMutation<RiskData>({ parse: (raw) => ensureRecord(raw, '组合风险') as RiskData });
  const stressApi = useApiMutation<StressData>({ parse: (raw) => ensureRecord(raw, '压力测试') as StressData });

  const loading = listQ.isFetching || detailQ.isFetching || optimizeApi.isPending || riskApi.isPending || stressApi.isPending || createApi.isPending || addHoldingApi.isPending;
  const error = formError || listQ.error || detailQ.error || optimizeApi.error || riskApi.error || stressApi.error || createApi.error || addHoldingApi.error;

  function optimize() {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    optimizeApi.trigger('/portfolio/optimize', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }
  function analyzeRisk() {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    riskApi.trigger('/portfolio/risk-analysis', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }
  function runStress() {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    stressApi.trigger('/portfolio/stress-test', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }
  async function handleCreate() {
    if (!newName.trim()) return setFormError('请输入组合名称');
    try {
      const data = await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, {
        name: newName.trim(), description: newDesc.trim(), initialCapital: newCapital.trim() || '1000000',
      });
      const createdId = data && typeof data === 'object' && 'portfolioId' in data ? String((data as { portfolioId?: unknown }).portfolioId ?? '') : '';
      if (createdId) {
        setPortfolioId(createdId);
      }
      setNewName(''); setNewDesc('');
    } catch { /* captured */ }
  }
  async function handleAddHolding() {
    if (!portfolioId.trim()) return setFormError('请先输入 portfolioId');
    if (!validateHold()) return;
    try {
      await addHoldingApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, {
        portfolioId: portfolioId.trim(),
        code: holdTrimmed,
        shares: holdShares.trim() || '100',
        ...(holdCost.trim() ? { costPrice: holdCost.trim() } : {}),
      });
      setHoldCode(''); setHoldShares('100'); setHoldCost('');
    } catch { /* captured */ }
  }

  const detailObj = useMemo(() => {
    if (!detailQ.data || typeof detailQ.data !== 'object') return null;
    return detailQ.data as PortfolioDetailRecord;
  }, [detailQ.data]);
  const detailHoldings = useMemo(() => extractArray(detailQ.data, 'holdings', 'positions', 'data') as Record<string, unknown>[], [detailQ.data]);
  const detailStrategies = useMemo(() => extractArray(detailQ.data, 'strategyAllocations') as Record<string, unknown>[], [detailQ.data]);
  const portfolioList = useMemo(() => extractArray(listQ.data) as Record<string, unknown>[], [listQ.data]);

  // Optimization weights for PieChart
  const weightSlices = useMemo(() => {
    const w = optimizeApi.data?.optimization?.weights;
    if (!w) return [];
    if (Array.isArray(w)) return w.map((item) => ({ name: item.code, value: +(Number(item.weight) * 100).toFixed(1) }));
    return Object.entries(w).map(([k, v]) => ({ name: k, value: +(Number(v) * 100).toFixed(1) }));
  }, [optimizeApi.data]);

  // Risk contribution for BarChart
  const riskBars = useMemo(() => {
    const rc = riskApi.data?.riskMetrics?.riskContribution;
    if (!rc || typeof rc !== 'object') return [];
    return Object.entries(rc).map(([k, v]) => ({ label: k, value: +(Number(v) * 100).toFixed(2) }));
  }, [riskApi.data]);

  const stressScenarios = useMemo(() => {
    const s = stressApi.data?.stressResult?.scenarios;
    if (Array.isArray(s)) return s as Record<string, unknown>[];
    return extractArray(stressApi.data, 'scenarios', 'data') as Record<string, unknown>[];
  }, [stressApi.data]);

  return (
    <PageContainer>
      <h1>投资组合</h1>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="p-3">
        <h2 className="mt-0 text-base font-semibold">当前组合操作</h2>
        <p className="text-sm text-text-secondary mt-1 mb-3">先从下方列表选择组合，或先创建一个新组合。选中后再执行加仓、优化、风险分析和压力测试。</p>
        <div className="flex gap-2 flex-wrap items-end">
          <label htmlFor="portfolio-selected-id" className="grid gap-1 text-xs text-text-secondary">
            <span>当前组合 ID</span>
            <input id="portfolio-selected-id" value={portfolioId} onChange={(e) => { setPortfolioId(e.target.value); setFormError(null); }} placeholder="选择或输入组合 ID" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
          </label>
          <button type="button" onClick={() => listQ.refetch()}>组合列表</button>
          <button type="button" onClick={() => { if (!portfolioId.trim()) { setFormError('请输入 portfolioId'); return; } detailQ.refetch(); }}>查看详情</button>
          <button type="button" onClick={optimize}>优化配置</button>
          <button type="button" onClick={analyzeRisk}>风险分析</button>
          <button type="button" onClick={runStress}>压力测试</button>
        </div>
      </SectionCard>

      {/* Create Portfolio */}
      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">创建组合</h3>
        <div className="flex gap-2 flex-wrap items-end">
          <label htmlFor="portfolio-new-name" className="grid gap-1 text-xs text-text-secondary">
            <span>组合名称</span>
            <input id="portfolio-new-name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="输入组合名称" className="w-[160px] px-2 py-1 rounded text-sm" />
          </label>
          <label htmlFor="portfolio-new-desc" className="grid gap-1 text-xs text-text-secondary">
            <span>描述</span>
            <input id="portfolio-new-desc" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="可选" className="w-[200px] px-2 py-1 rounded text-sm" />
          </label>
          <label htmlFor="portfolio-new-capital" className="grid gap-1 text-xs text-text-secondary">
            <span>初始资金</span>
            <input id="portfolio-new-capital" value={newCapital} onChange={(e) => setNewCapital(e.target.value)} placeholder="1000000" type="number" className="w-[140px] px-2 py-1 rounded text-sm" />
          </label>
          <button type="button" onClick={handleCreate} disabled={createApi.isPending}>{createApi.isPending ? '创建中...' : '创建'}</button>
        </div>
        {createApi.data != null && <p className="text-success text-xs mt-2">创建成功，已自动选中新组合。</p>}
      </SectionCard>

      {/* Add Holding (only when portfolioId is set) */}
      {portfolioId.trim() && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0">添加持仓（组合 {portfolioId}）</h3>
          <div className="flex gap-2 flex-wrap items-end">
            <StockCodeInput id="portfolio-holding-code" label="股票代码" value={holdCode} onChange={setHoldCode} error={holdCodeError} placeholder="股票代码" />
            <label htmlFor="portfolio-holding-shares" className="grid gap-1 text-xs text-text-secondary">
              <span>股数</span>
              <input id="portfolio-holding-shares" value={holdShares} onChange={(e) => setHoldShares(e.target.value)} placeholder="100" type="number" className="w-[100px] px-2 py-1 rounded text-sm" />
            </label>
            <label htmlFor="portfolio-holding-cost" className="grid gap-1 text-xs text-text-secondary">
              <span>成本价</span>
              <input id="portfolio-holding-cost" value={holdCost} onChange={(e) => setHoldCost(e.target.value)} placeholder="可选" type="number" step="0.01" className="w-[140px] px-2 py-1 rounded text-sm" />
            </label>
            <button type="button" onClick={handleAddHolding} disabled={addHoldingApi.isPending}>{addHoldingApi.isPending ? '添加中...' : '添加'}</button>
          </div>
          {addHoldingApi.data != null && <p className="text-success text-xs mt-2">添加成功</p>}
        </SectionCard>
      )}

      {portfolioList.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">组合列表</h3>
          <DataTable
            rows={portfolioList}
            columns={[
              { key: 'id', label: '组合ID' },
              { key: 'name', label: '组合名称' },
              { key: 'description', label: '描述' },
              { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
              { key: 'strategyAllocationSummary', label: '策略配置' },
              { key: 'initialCapital', label: '初始资金', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'currentValue', label: '当前资产', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'createdAt', label: '创建时间' },
            ]}
            pageSize={10}
            searchable
            onExport={() => exportCSV(portfolioList, 'portfolio-list')}
            onRowClick={(row) => {
              const selectedId = String(row.id ?? '').trim();
              if (!selectedId || selectedId === '-') return;
              setPortfolioId(selectedId);
              setFormError(null);
            }}
          />
        </SectionCard>
      )}

      {!portfolioId.trim() ? (
        <SectionCard className="mt-4 p-4">
          <EmptyState text="还没有选中组合。可以先从“组合列表”点选一条，或在上方创建新组合后继续。"/>
        </SectionCard>
      ) : null}

      {detailObj && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">组合详情</h3>
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
          {detailHoldings.length > 0 && <DataTable rows={detailHoldings} pageSize={10} onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')} />}
        </SectionCard>
      )}

      {(weightSlices.length > 0 || riskBars.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          {weightSlices.length > 0 && (
            <SectionCard className="p-3">
              <h3 className="mt-0">配置权重</h3>
              <PieChart data={weightSlices} donut height={300} />
            </SectionCard>
          )}
          {riskBars.length > 0 && (
            <SectionCard className="p-3">
              <h3 className="mt-0">风险贡献度</h3>
              <BarChart items={riskBars} colorByValue height={300} yAxisName="贡献 %" />
            </SectionCard>
          )}
        </div>
      )}

      {optimizeApi.data?.optimization && (
        <SectionCard className="mt-4 p-3">
          <KpiGrid cols={3}>
            <KpiCard title="预期收益" value={fmtPct(Number(optimizeApi.data.optimization.expectedReturn))} />
            <KpiCard title="预期风险" value={fmtPct(Number(optimizeApi.data.optimization.expectedRisk))} />
            <KpiCard title="夏普比率" value={fmtNum(Number(optimizeApi.data.optimization.sharpe), 2)} />
          </KpiGrid>
        </SectionCard>
      )}

      {riskApi.data?.riskMetrics && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">风险指标</h3>
          <KpiGrid cols={5}>
            <KpiCard title="VaR (95%)" value={fmtPct(Number(riskApi.data.riskMetrics.var95))} />
            <KpiCard title="VaR (99%)" value={fmtPct(Number(riskApi.data.riskMetrics.var99))} />
            <KpiCard title="CVaR" value={fmtPct(Number(riskApi.data.riskMetrics.cvar))} />
            <KpiCard title="Beta" value={fmtNum(Number(riskApi.data.riskMetrics.beta), 2)} />
            <KpiCard title="波动率" value={fmtPct(Number(riskApi.data.riskMetrics.volatility))} />
          </KpiGrid>
        </SectionCard>
      )}

      {stressScenarios.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">压力测试</h3>
          <DataTable rows={stressScenarios} onExport={() => exportCSV(stressScenarios, 'stress-test')} />
        </SectionCard>
      )}
    </PageContainer>
  );
}
