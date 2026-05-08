import { PieChart, BarChart } from '@/components/charts';
import { EmptyState } from '@/components/status-state';
import { DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import type { OptData, PortfolioDetailRecord, RiskData } from '../portfolio-page.types';

type ChartSlice = { name: string; value: number };
type ChartBar = { label: string; value: number };

type PortfolioListSectionProps = {
  portfolioList: Record<string, unknown>[];
  activePortfolioId: string;
  onSelectPortfolio: (portfolioId: string) => void;
};

export function PortfolioListSection({
  portfolioList,
  activePortfolioId,
  onSelectPortfolio,
}: PortfolioListSectionProps) {
  if (portfolioList.length === 0) return null;

  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-medium">组合列表</h3>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            点按一行即可切换当前组合，并同步查看详情、加仓和分析入口。
          </p>
        </div>
      </div>
      <div className="mt-4">
        <DataTable
          rows={portfolioList}
          columns={[
            { key: 'id', label: '组合ID' },
            { key: 'name', label: '组合名称' },
            { key: 'description', label: '描述' },
            { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
            { key: 'strategyAllocationSummary', label: '策略配置' },
            {
              key: 'initialCapital',
              label: '初始资金',
              align: 'right',
              render: (value) => fmtNum(Number(value ?? 0), 2),
            },
            {
              key: 'currentValue',
              label: '当前资产',
              align: 'right',
              render: (value) => fmtNum(Number(value ?? 0), 2),
            },
            { key: 'createdAt', label: '创建时间' },
          ]}
          pageSize={10}
          searchable
          onExport={() => exportCSV(portfolioList, 'portfolio-list')}
          mobileCardRender={(row) => {
            const rowId = String(row.id ?? '-');
            const isActive = rowId === activePortfolioId;
            return (
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-text-primary">{String(row.name ?? rowId)}</div>
                    <div className="text-xs text-text-secondary">组合 ID：{rowId}</div>
                  </div>
                  <div className={`text-xs ${isActive ? 'text-primary' : 'text-text-secondary'}`}>
                    {isActive ? '已选中' : '点按切换'}
                  </div>
                </div>
                <div className="text-xs text-text-secondary">描述：{String(row.description ?? '-')}</div>
                <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                  <div>策略数：{String(row.strategyAllocationCount ?? '-')}</div>
                  <div>初始资金：{fmtNum(Number(row.initialCapital ?? 0), 2)}</div>
                  <div className="col-span-2">当前资产：{fmtNum(Number(row.currentValue ?? 0), 2)}</div>
                </div>
              </div>
            );
          }}
          onRowClick={(row) => {
            const selectedId = String(row.id ?? '').trim();
            if (!selectedId || selectedId === '-') return;
            onSelectPortfolio(selectedId);
          }}
        />
      </div>
    </SectionCard>
  );
}

type PortfolioEmptySelectionSectionProps = {
  activePortfolioId: string;
};

export function PortfolioEmptySelectionSection({
  activePortfolioId,
}: PortfolioEmptySelectionSectionProps) {
  if (activePortfolioId) return null;

  return (
    <SectionCard className="mt-0 p-4">
      <EmptyState
        text="还没有选中组合。可以先从“组合列表”点选一条，或在上方创建新组合后继续。"
        hint="后续的详情、加仓、优化和压力测试都会围绕当前选中的组合展开。"
      />
    </SectionCard>
  );
}

type PortfolioDetailSectionProps = {
  detailObj: PortfolioDetailRecord | null;
  detailHoldings: Record<string, unknown>[];
  detailStrategies: Record<string, unknown>[];
};

export function PortfolioDetailSection({
  detailObj,
  detailHoldings,
  detailStrategies,
}: PortfolioDetailSectionProps) {
  if (!detailObj) return null;

  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-medium">组合详情</h3>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            详情区负责回答“当前组合是什么、现在持了什么、策略权重如何分布”这三个问题。
          </p>
        </div>
      </div>
      <KpiGrid cols={4} className="mt-4">
        <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
        <KpiCard title="总资产" value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null} />
        <KpiCard
          title="总收益"
          value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null}
          change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null}
        />
        <KpiCard title="持仓数" value={detailHoldings.length} />
      </KpiGrid>

      {detailStrategies.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">策略配置</div>
          <DataTable
            rows={detailStrategies}
            columns={[
              {
                key: 'strategyId',
                label: '策略ID',
                render: (_value, row) => String(row.strategyId ?? row.strategy_id ?? '-'),
              },
              { key: 'weight', label: '权重', align: 'right', render: (value) => fmtPct(Number(value ?? 0) * 100) },
            ]}
            mobileCardRender={(row) => (
              <div className="space-y-2">
                <div className="text-sm font-medium text-text-primary">
                  策略 {String(row.strategyId ?? row.strategy_id ?? '-')}
                </div>
                <div className="text-xs text-text-secondary">权重：{fmtPct(Number(row.weight ?? 0) * 100)}</div>
              </div>
            )}
          />
        </div>
      ) : null}

      {detailHoldings.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">持仓明细</div>
          <DataTable
            rows={detailHoldings}
            pageSize={10}
            onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')}
            mobileCardRender={(row) => (
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-medium text-text-primary">
                    {String(row.code ?? row.stockCode ?? '-')}
                  </div>
                  <div className="text-xs text-text-secondary">
                    数量：{String(row.shares ?? row.quantity ?? '-')}
                  </div>
                </div>
                <div className="text-xs text-text-secondary">
                  成本价：{fmtNum(Number(row.costPrice ?? row.cost_price ?? 0), 2)}
                </div>
                <div className="text-xs text-text-secondary">
                  市值：{fmtNum(Number(row.marketValue ?? row.market_value ?? 0), 2)}
                </div>
              </div>
            )}
          />
        </div>
      ) : null}
    </SectionCard>
  );
}

type PortfolioChartsSectionProps = {
  weightSlices: ChartSlice[];
  riskBars: ChartBar[];
};

export function PortfolioChartsSection({ weightSlices, riskBars }: PortfolioChartsSectionProps) {
  if (weightSlices.length === 0 && riskBars.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {weightSlices.length > 0 ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">配置权重</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                优化结果出来后，先看权重分布是否真的符合当前研究判断和风险预算。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <PieChart data={weightSlices} donut height={300} />
          </div>
        </SectionCard>
      ) : null}
      {riskBars.length > 0 ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">风险贡献度</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                把风险来源单独拉出来，能更快判断是单只股票、行业还是配置比例在拖累组合。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <BarChart items={riskBars} colorByValue height={300} yAxisName="贡献 %" />
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}

type PortfolioOptimizationSummarySectionProps = {
  optimization: OptData['optimization'] | null | undefined;
};

export function PortfolioOptimizationSummarySection({
  optimization,
}: PortfolioOptimizationSummarySectionProps) {
  if (!optimization) return null;

  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-medium">优化结果摘要</h3>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            用核心 KPI 先判断这次优化是提升了收益效率，还是只是换了一套更冒险的配置。
          </p>
        </div>
      </div>
      <KpiGrid cols={3} className="mt-4">
        <KpiCard title="预期收益" value={fmtPct(Number(optimization.expectedReturn))} />
        <KpiCard title="预期风险" value={fmtPct(Number(optimization.expectedRisk))} />
        <KpiCard title="夏普比率" value={fmtNum(Number(optimization.sharpe), 2)} />
      </KpiGrid>
    </SectionCard>
  );
}

type PortfolioRiskMetricsSectionProps = {
  riskMetrics: RiskData['riskMetrics'] | null | undefined;
};

export function PortfolioRiskMetricsSection({ riskMetrics }: PortfolioRiskMetricsSectionProps) {
  if (!riskMetrics) return null;

  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-medium">风险指标</h3>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            风险区用 VaR、CVaR、Beta 和波动率来确认这套组合是否还在你的容忍区间内。
          </p>
        </div>
      </div>
      <KpiGrid cols={5} className="mt-4">
        <KpiCard title="VaR (95%)" value={fmtPct(Number(riskMetrics.var95))} />
        <KpiCard title="VaR (99%)" value={fmtPct(Number(riskMetrics.var99))} />
        <KpiCard title="CVaR" value={fmtPct(Number(riskMetrics.cvar))} />
        <KpiCard title="Beta" value={fmtNum(Number(riskMetrics.beta), 2)} />
        <KpiCard title="波动率" value={fmtPct(Number(riskMetrics.volatility))} />
      </KpiGrid>
    </SectionCard>
  );
}

type PortfolioStressTestSectionProps = {
  stressScenarios: Record<string, unknown>[];
};

export function PortfolioStressTestSection({
  stressScenarios,
}: PortfolioStressTestSectionProps) {
  if (stressScenarios.length === 0) return null;

  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-medium">压力测试</h3>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            压力场景用于回答“如果市场波动加剧，这套组合最先会被什么拖累”。
          </p>
        </div>
      </div>
      <div className="mt-4">
        <DataTable
          rows={stressScenarios}
          onExport={() => exportCSV(stressScenarios, 'stress-test')}
          mobileCardRender={(row) => (
            <div className="space-y-2">
              <div className="text-sm font-medium text-text-primary">{String(row.name ?? '-')}</div>
              <div className="text-xs text-text-secondary">影响：{fmtPct(Number(row.impact ?? 0))}</div>
              <div className="text-xs text-text-secondary">{String(row.description ?? '无额外说明')}</div>
            </div>
          )}
        />
      </div>
    </SectionCard>
  );
}
