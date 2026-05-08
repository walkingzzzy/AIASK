import { CandlestickChart } from '@/components/charts';
import { EmptyState } from '@/components/status-state';
import { SectionCard, Skeleton } from '@/components/ui';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { fmtAmount, fmtNum } from '@/lib/data-utils';
import { getStockPeriodLabel, type Period } from '@/app/stock/lib/stock-detail-view';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
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
  emptyHint?: string | null;
};

export default function StockChartTab({ period, isFetching, candleData, orderBook, emptyHint }: StockChartTabProps) {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const mobileOnlyDetected = useMobile(RESPONSIVE_BREAKPOINTS.mobile);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const mobileOnly = hydrated ? mobileOnlyDetected : true;
  const chartHeight = compactLayout ? (mobileOnly ? 200 : 220) : 420;

  return (
    <SectionCard tabAttached className={`${compactLayout ? 'min-h-[300px]' : 'min-h-[560px]'} p-4 sm:p-5`}>
      <h3 className="mt-0">K线图（{getStockPeriodLabel(period)}）</h3>
      {isFetching && !candleData.length ? (
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="w-full" height={chartHeight} />
          {!compactLayout ? (
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="w-full" height={96} />
              <Skeleton className="w-full" height={96} />
            </div>
          ) : null}
        </div>
      ) : candleData.length ? (
        <CandlestickChart data={candleData} height={chartHeight} />
      ) : (
        <EmptyState
          text="暂无 K 线数据"
          hint={emptyHint ?? '当前股票或周期暂时没有可绘制的 K 线。可以切换周期、重新查询，或回到行情页确认标的状态。'}
        />
      )}
      {(orderBook.bids.length > 0 || orderBook.asks.length > 0) && (
        compactLayout ? (
          <details className="mt-4 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开五档盘口</summary>
            <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
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
          </details>
        ) : (
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
        )
      )}
    </SectionCard>
  );
}
