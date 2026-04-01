import { useMemo } from 'react';
import { SectionCard } from '@/components/ui';
import { CandlestickChart } from '@/components/charts';
import { EmptyState } from '@/components/status-state';
import {
  marketFieldCls,
  marketPrimaryButtonCls,
  marketSecondaryButtonCls,
  marketSelectCls,
} from '@/app/market/components/market-panel-styles';

type MarketMinuteTabProps = {
  code: string;
  onCodeChange: (value: string) => void;
  minutePeriod: string;
  onMinutePeriodChange: (value: string) => void;
  tabPending: boolean;
  minuteRows: Record<string, unknown>[];
  error: string | null;
  onQueryMinute: () => void;
  onShowMain: () => void;
};

export default function MarketMinuteTab({
  code,
  onCodeChange,
  minutePeriod,
  onMinutePeriodChange,
  tabPending,
  minuteRows,
  error,
  onQueryMinute,
  onShowMain,
}: MarketMinuteTabProps) {
  const minuteCandleData = useMemo(
    () =>
      minuteRows.map((row) => ({
        date: String(row.time ?? row.date ?? row.datetime ?? ''),
        open: Number(row.open ?? 0),
        close: Number(row.close ?? 0),
        low: Number(row.low ?? 0),
        high: Number(row.high ?? 0),
        volume: Number(row.volume ?? 0),
      })),
    [minuteRows],
  );

  return (
    <SectionCard tabAttached>
      <div className="flex items-center gap-2">
        <input
          value={code}
          onChange={(e) => onCodeChange(e.target.value)}
          maxLength={6}
          placeholder="股票代码"
          aria-label="股票代码"
          className={`w-35 ${marketFieldCls}`}
        />
        <select
          value={minutePeriod}
          onChange={(e) => onMinutePeriodChange(e.target.value)}
          aria-label="分时周期"
          className={marketSelectCls}
        >
          <option value="1m">1分钟</option>
          <option value="5m">5分钟</option>
          <option value="15m">15分钟</option>
          <option value="30m">30分钟</option>
          <option value="60m">60分钟</option>
        </select>
        <button type="button" disabled={tabPending} onClick={onQueryMinute} className={marketPrimaryButtonCls}>
          {tabPending ? '加载中...' : '查询分时'}
        </button>
      </div>
      {minuteCandleData.length ? (
        <CandlestickChart data={minuteCandleData} height={360} />
      ) : !tabPending && !error ? (
        <EmptyState
          text="选择周期后加载分钟级 K 线"
          hint="分时更适合盘中确认节奏；如果只是看方向，先用基础行情日线会更稳。"
          action={
            <>
              <button type="button" onClick={() => onMinutePeriodChange('5m')} className={marketPrimaryButtonCls}>
                用 5 分钟周期
              </button>
              <button type="button" onClick={onShowMain} className={marketSecondaryButtonCls}>
                回基础行情
              </button>
            </>
          }
        />
      ) : null}
    </SectionCard>
  );
}
