import { KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtAmount, fmtNum } from '@/lib/data-utils';
import type { StockFundamentalOverview } from '@aiask/shared-types';

type StockFundamentalTabProps = {
  fundamental: StockFundamentalOverview | null;
  isFetching: boolean;
  hasResponse: boolean;
  skipKeys: string[];
};

const FUNDAMENTAL_LABELS: Record<string, string> = {
  roe: 'ROE',
  netProfit: '净利润',
  revenue: '营收',
  debtRatio: '资产负债率',
  pe: 'PE',
  pb: 'PB',
  ps: 'PS',
  marketCap: '总市值',
  eps: 'EPS',
  bps: '每股净资产',
  totalShares: '总股本',
  floatShares: '流通股本',
};

export default function StockFundamentalTab({
  fundamental,
  isFetching,
  hasResponse,
  skipKeys,
}: StockFundamentalTabProps) {
  const items =
    fundamental && Object.keys(fundamental).length > 0
      ? Object.entries(fundamental)
          .filter(([key]) => !skipKeys.includes(key))
          .flatMap(([key, value]) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
              return Object.entries(value as Record<string, unknown>).map(([subKey, subValue]) => [subKey, subValue] as [string, unknown]);
            }
            return [[key, value] as [string, unknown]];
          })
          .slice(0, 16)
      : [];

  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">基本面概览</h3>
      {items.length > 0 ? (
        <KpiGrid cols={4}>
          {items.map(([key, value]) => {
            const num = Number(value);
            const display =
              value == null
                ? '-'
                : !Number.isNaN(num) && value !== ''
                  ? Math.abs(num) > 1e6
                    ? fmtAmount(num)
                    : fmtNum(num, 2)
                  : String(value);
            return <KpiCard key={key} title={FUNDAMENTAL_LABELS[key] ?? key} value={display} />;
          })}
        </KpiGrid>
      ) : (
        <p className="text-sm text-text-secondary">{isFetching ? '加载中...' : hasResponse ? '暂无基本面数据' : '查询股票后显示基本面数据'}</p>
      )}
    </SectionCard>
  );
}
