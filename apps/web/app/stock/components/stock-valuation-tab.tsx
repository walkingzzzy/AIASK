import { GaugeChart } from '@/components/charts';
import { KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import type { StockValuationOverview } from '@aiask/shared-types';

type StockValuationTabProps = {
  valuationMetrics: StockValuationOverview;
  hasResponse: boolean;
  isFetching: boolean;
};

export default function StockValuationTab({
  valuationMetrics,
  hasResponse,
  isFetching,
}: StockValuationTabProps) {
  const pe = Number(valuationMetrics.pe ?? valuationMetrics.pe_ttm ?? 0);
  const pb = Number(valuationMetrics.pb ?? 0);
  const ps = Number(valuationMetrics.ps ?? 0);
  const pcf = Number(valuationMetrics.pcf ?? 0);
  const marketCap = Number(valuationMetrics.market_cap ?? 0);
  const floatMarketCap = Number(valuationMetrics.float_market_cap ?? 0);
  const peHist = valuationMetrics.pe_percentile;
  const pbHist = valuationMetrics.pb_percentile;

  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">估值分析</h3>
      {hasResponse ? (
        <div className="space-y-4">
          <KpiGrid cols={4}>
            <KpiCard title="PE(TTM)" value={pe > 0 ? fmtNum(pe, 2) : '亏损'} />
            <KpiCard title="PB" value={fmtNum(pb, 2)} />
            <KpiCard title="PS" value={fmtNum(ps, 2)} />
            <KpiCard title="PCF" value={pcf > 0 ? fmtNum(pcf, 2) : '-'} />
            <KpiCard title="总市值" value={fmtAmount(marketCap)} suffix="元" />
            <KpiCard title="流通市值" value={floatMarketCap > 0 ? fmtAmount(floatMarketCap) : '-'} suffix="元" />
            {peHist != null ? <KpiCard title="PE历史分位" value={fmtPct(Number(peHist))} /> : null}
            {pbHist != null ? <KpiCard title="PB历史分位" value={fmtPct(Number(pbHist))} /> : null}
          </KpiGrid>
          {pe > 0 ? (
            <div className="mt-2">
              <GaugeChart
                value={Math.min(pe, 100)}
                min={0}
                max={100}
                title={pe < 15 ? '低估' : pe < 30 ? '合理' : pe < 60 ? '偏高' : '高估'}
                height={180}
              />
              <p className="mt-1 text-center text-xs text-text-secondary">PE估值水平参考</p>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-text-secondary">{isFetching ? '加载中...' : '查询股票后显示估值数据'}</p>
      )}
    </SectionCard>
  );
}
