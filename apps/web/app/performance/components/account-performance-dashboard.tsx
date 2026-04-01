import { DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { ErrorState } from '@/components/status-state';
import { LineChart } from '@/components/charts';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { performanceChipButtonCls } from '@/app/performance/components/performance-panel-styles';
import type {
  PaperTradingNavPoint,
  PaperTradingPerformanceMetrics,
  PaperTradingPerformancePoint,
  PaperTradingPosition,
} from '@aiask/shared-types';

type AccountPerformanceDashboardProps = {
  errorMessage: string | null;
  totalValue: number;
  totalReturnPct: number;
  accountMetrics: PaperTradingPerformanceMetrics;
  days: number;
  navData: PaperTradingNavPoint[];
  navCategories: string[];
  navValues: number[];
  performanceData: PaperTradingPerformancePoint[];
  perfCategories: string[];
  perfReturns: number[];
  topPositions: PaperTradingPosition[];
  onOpenStockTarget: (code: string) => void;
  onOpenResearchTarget: (code: string) => void;
};

export default function AccountPerformanceDashboard({
  errorMessage,
  totalValue,
  totalReturnPct,
  accountMetrics,
  days,
  navData,
  navCategories,
  navValues,
  performanceData,
  perfCategories,
  perfReturns,
  topPositions,
  onOpenStockTarget,
  onOpenResearchTarget,
}: AccountPerformanceDashboardProps) {
  return (
    <>
      {errorMessage ? <ErrorState text={errorMessage} /> : null}

      <KpiGrid cols={5} className="mb-4 mt-4">
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="累计收益率" value={fmtPct(totalReturnPct)} change={totalReturnPct} />
        <KpiCard title="夏普比率" value={fmtNum(Number(accountMetrics.sharpe ?? 0))} />
        <KpiCard
          title="最大回撤"
          value={fmtPct(Number(accountMetrics.maxDrawdown ?? 0) * 100)}
          change={Number(accountMetrics.maxDrawdown ?? 0) * 100}
        />
        <KpiCard
          title="胜率"
          value={fmtPct(Number(accountMetrics.winRate ?? 0) * 100)}
          change={Number(accountMetrics.winRate ?? 0) * 100}
        />
      </KpiGrid>

      <div className="grid gap-4 2xl:grid-cols-2">
        <SectionCard className="p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h3 className="m-0 font-medium">净值曲线</h3>
            <button
              type="button"
              onClick={() =>
                exportCSV(
                  navData.map((item) => ({
                    日期: item.nav_date ?? '',
                    总资产: item.total_value ?? 0,
                    现金: item.cash ?? 0,
                    持仓市值: item.market_value ?? 0,
                    日收益率: item.daily_return ?? 0,
                  })),
                  `performance-nav-${days}.csv`,
                )
              }
              className={performanceChipButtonCls}
            >
              导出净值
            </button>
          </div>
          {navData.length > 1 ? (
            <LineChart categories={navCategories} series={[{ name: '总资产', data: navValues }]} />
          ) : (
            <p className="text-sm text-text-secondary">暂无足够净值数据</p>
          )}
        </SectionCard>

        <SectionCard className="p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h3 className="m-0 font-medium">日收益率</h3>
            <button
              type="button"
              onClick={() =>
                exportCSV(
                  performanceData.map((item) => ({
                    日期: item.date ?? '',
                    总资产: item.totalValue ?? 0,
                    日收益率: item.dailyReturn ?? 0,
                  })),
                  `performance-returns-${days}.csv`,
                )
              }
              className={performanceChipButtonCls}
            >
              导出收益
            </button>
          </div>
          {performanceData.length > 1 ? (
            <LineChart categories={perfCategories} series={[{ name: '日收益率(%)', data: perfReturns }]} />
          ) : (
            <p className="text-sm text-text-secondary">暂无足够收益数据</p>
          )}
        </SectionCard>
      </div>

      <SectionCard className="p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h3 className="m-0 font-medium">核心持仓</h3>
          <span className="text-xs text-text-secondary">按市值排序展示前 8 只</span>
        </div>
        <DataTable
          rows={topPositions as unknown as Record<string, unknown>[]}
          emptyText="暂无持仓"
          columns={[
            { key: 'stock_code', label: '代码' },
            { key: 'stock_name', label: '名称' },
            { key: 'quantity', label: '数量' },
            { key: 'cost_price', label: '成本', render: (value: unknown) => fmtNum(Number(value ?? 0), 2) },
            {
              key: 'current_price',
              label: '现价',
              render: (value: unknown) => fmtNum(Number(value ?? 0), 2),
            },
            { key: 'market_value', label: '市值', render: (value: unknown) => fmtNum(Number(value ?? 0)) },
            {
              key: 'profit_rate',
              label: '盈亏率',
              render: (value: unknown) => fmtPct(Number(value ?? 0) * 100),
            },
            {
              key: 'actions',
              label: '联动',
              sortable: false,
              render: (_value: unknown, row: Record<string, unknown>) => {
                const rowCode = String(row.stock_code ?? '').trim();
                if (!rowCode) return '-';
                return (
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => onOpenStockTarget(rowCode)} className={performanceChipButtonCls}>
                      详情
                    </button>
                    <button
                      type="button"
                      onClick={() => onOpenResearchTarget(rowCode)}
                      className={performanceChipButtonCls}
                    >
                      研究
                    </button>
                  </div>
                );
              },
            },
          ]}
          mobileCardRender={(row) => (
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-text-primary">{String(row.stock_name ?? row.stock_code ?? '-')}</div>
                  <div className="text-xs text-text-secondary">代码：{String(row.stock_code ?? '-')}</div>
                </div>
                <div className="text-xs text-text-secondary">{fmtPct(Number(row.profit_rate ?? 0) * 100)}</div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                <div>数量：{String(row.quantity ?? '-')}</div>
                <div>市值：{fmtNum(Number(row.market_value ?? 0))}</div>
                <div>成本：{fmtNum(Number(row.cost_price ?? 0), 2)}</div>
                <div>现价：{fmtNum(Number(row.current_price ?? 0), 2)}</div>
              </div>
              {String(row.stock_code ?? '').trim() ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onOpenStockTarget(String(row.stock_code ?? ''))}
                    className={performanceChipButtonCls}
                  >
                    打开详情
                  </button>
                  <button
                    type="button"
                    onClick={() => onOpenResearchTarget(String(row.stock_code ?? ''))}
                    className={performanceChipButtonCls}
                  >
                    打开研究
                  </button>
                </div>
              ) : null}
            </div>
          )}
        />
      </SectionCard>
    </>
  );
}
