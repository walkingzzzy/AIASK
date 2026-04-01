import { CandlestickChart } from '@/components/charts';
import { EmptyState } from '@/components/status-state';
import { SectionCard, Skeleton } from '@/components/ui';
import { fmtAmount, fmtNum } from '@/lib/data-utils';
import { getStockPeriodLabel, type Period } from '@/app/stock/lib/stock-detail-view';
import type { NormalizedOrderBook } from '@aiask/shared-types';

type CandlePoint = {
  date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
};

type StockChartTabProps = {
  period: Period;
  isFetching: boolean;
  candleData: CandlePoint[];
  orderBook: NormalizedOrderBook;
};

export default function StockChartTab({ period, isFetching, candleData, orderBook }: StockChartTabProps) {
  return (
    <SectionCard tabAttached className="min-h-[560px] p-4 sm:p-5">
      <h3 className="mt-0">K线图（{getStockPeriodLabel(period)}）</h3>
      {isFetching && !candleData.length ? (
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="w-full" height={420} />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="w-full" height={96} />
            <Skeleton className="w-full" height={96} />
          </div>
        </div>
      ) : candleData.length ? (
        <CandlestickChart data={candleData} height={420} />
      ) : (
        <EmptyState
          text="暂无 K 线数据"
          hint="主图区已保留固定高度。切换股票或周期时，图表会在原位置刷新，不再把盘口和下方内容整体推移。"
        />
      )}
      {(orderBook.bids.length > 0 || orderBook.asks.length > 0) && (
        <div className="mt-4">
          <h3 className="mt-0">五档盘口</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="mb-1 flex justify-between text-xs text-text-muted">
                <span>卖盘</span>
                <span>价格 / 数量</span>
              </div>
              {orderBook.asks.map((ask, index) => (
                <div key={`${ask.price}-${index}`} className="metric-tile mb-2 flex justify-between px-3 py-2 text-success">
                  <span>卖{orderBook.asks.length - index}</span>
                  <span>
                    {fmtNum(ask.price, 2)} / {fmtAmount(ask.volume)}
                  </span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 flex justify-between text-xs text-text-muted">
                <span>买盘</span>
                <span>价格 / 数量</span>
              </div>
              {orderBook.bids.map((bid, index) => (
                <div key={`${bid.price}-${index}`} className="metric-tile mb-2 flex justify-between px-3 py-2 text-danger">
                  <span>买{index + 1}</span>
                  <span>
                    {fmtNum(bid.price, 2)} / {fmtAmount(bid.volume)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
