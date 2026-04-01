import { BarChart } from '@/components/charts';
import { KpiCard, SectionCard } from '@/components/ui';
import { fmtAmount } from '@/lib/data-utils';
import type { StockFundFlowEntry } from '@aiask/shared-types';

type StockFundFlowTabProps = {
  fundFlowChart: Array<{ label: string; value: number }>;
  fundFlowItems: StockFundFlowEntry[];
  isFetching: boolean;
  hasResponse: boolean;
};

export default function StockFundFlowTab({
  fundFlowChart,
  fundFlowItems,
  isFetching,
  hasResponse,
}: StockFundFlowTabProps) {
  const latest = fundFlowItems[fundFlowItems.length - 1] as Record<string, unknown> | undefined;

  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">资金流向（近20日）</h3>
      {fundFlowChart.length > 0 ? (
        <BarChart items={fundFlowChart} height={300} yAxisName="净流入" colorByValue />
      ) : (
        <p className="text-sm text-text-secondary">{isFetching ? '加载中...' : hasResponse ? '暂无资金流向数据' : '查询股票后显示资金流向'}</p>
      )}
      {fundFlowItems.length > 0 ? (
        <div className="mt-3 grid grid-cols-3 gap-2">
          <KpiCard title="最近净流入" value={fmtAmount(Number(latest?.netInflow ?? 0))} />
          <KpiCard title="主力流入" value={fmtAmount(Number(latest?.mainInflow ?? 0))} />
          <KpiCard title="散户流入" value={fmtAmount(Number(latest?.retailInflow ?? 0))} />
        </div>
      ) : null}
    </SectionCard>
  );
}
