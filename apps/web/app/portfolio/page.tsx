'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable } from '@/components/ui';
import { PieChart, BarChart, LineChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

type OptData = { optimization?: { expectedReturn?: number; expectedRisk?: number; sharpe?: number; weights?: Record<string, number> | Array<{ code: string; weight: number }> } };
type RiskData = { riskMetrics?: { var95?: number; var99?: number; cvar?: number; beta?: number; volatility?: number; riskContribution?: Record<string, number> } };
type StressScenario = { name?: string; impact?: number; description?: string };
type StressData = { stressResult?: { scenarios?: StressScenario[] } };

export default function PortfolioPage() {
  const [portfolioId, setPortfolioId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const portfolioListApi = useApiMutation<unknown>();
  const portfolioDetailApi = useApiMutation<unknown>();
  const optimizeApi = useApiMutation<OptData>();
  const riskApi = useApiMutation<RiskData>();
  const stressApi = useApiMutation<StressData>();

  const loading = portfolioListApi.isPending || portfolioDetailApi.isPending || optimizeApi.isPending || riskApi.isPending || stressApi.isPending;
  const error = formError || portfolioListApi.error || portfolioDetailApi.error || optimizeApi.error || riskApi.error || stressApi.error;

  function loadList() { portfolioListApi.trigger('/portfolio/list'); }
  function loadDetail() {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    portfolioDetailApi.trigger(`/portfolio/get?portfolioId=${encodeURIComponent(portfolioId.trim())}`);
  }
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

  const detailObj = useMemo(() => portfolioDetailApi.data ? extractObject(portfolioDetailApi.data) as Record<string, unknown> | null : null, [portfolioDetailApi.data]);
  const detailHoldings = useMemo(() => extractArray(portfolioDetailApi.data, 'holdings', 'positions', 'data') as Record<string, unknown>[], [portfolioDetailApi.data]);
  const portfolioList = useMemo(() => extractArray(portfolioListApi.data) as Record<string, unknown>[], [portfolioListApi.data]);

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
        <div className="flex gap-2 flex-wrap items-center">
          <input value={portfolioId} onChange={(e) => { setPortfolioId(e.target.value); setFormError(null); }} placeholder="portfolioId" className="w-[140px] px-2 py-1 border border-border rounded text-sm" />
          <button type="button" onClick={loadList}>组合列表</button>
          <button type="button" onClick={loadDetail}>查看详情</button>
          <button type="button" onClick={optimize}>优化配置</button>
          <button type="button" onClick={analyzeRisk}>风险分析</button>
          <button type="button" onClick={runStress}>压力测试</button>
        </div>
      </SectionCard>

      {portfolioList.length > 0 && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">组合列表</h3>
          <DataTable rows={portfolioList} pageSize={10} onExport={() => exportCSV(portfolioList, 'portfolio-list')} />
        </SectionCard>
      )}

      {detailObj && (
        <SectionCard className="mt-4 p-3">
          <h3 className="mt-0">组合详情</h3>
          <KpiGrid cols={4}>
            <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
            <KpiCard title="总资产" value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null} />
            <KpiCard title="总收益" value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null} change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null} />
            <KpiCard title="持仓数" value={detailHoldings.length || null} />
          </KpiGrid>
          {detailHoldings.length > 0 && <DataTable rows={detailHoldings} pageSize={10} onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')} />}
        </SectionCard>
      )}

      {weightSlices.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <SectionCard className="p-3">
            <h3 className="mt-0">配置权重</h3>
            <PieChart data={weightSlices} donut height={300} />
          </SectionCard>
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
