import { KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import { marketFieldCls, marketPrimaryButtonCls, marketSecondaryButtonCls } from '@/app/market/components/market-panel-styles';

type MarketIndexTabProps = {
  indexCode: string;
  onIndexCodeChange: (value: string) => void;
  tabPending: boolean;
  indexObj: Record<string, unknown> | null;
  error: string | null;
  onQueryIndex: () => void;
  onUseExampleCode: (code: string) => void;
};

export default function MarketIndexTab({
  indexCode,
  onIndexCodeChange,
  tabPending,
  indexObj,
  error,
  onQueryIndex,
  onUseExampleCode,
}: MarketIndexTabProps) {
  return (
    <SectionCard tabAttached>
      <div className="flex items-center gap-2">
        <input
          value={indexCode}
          onChange={(e) => onIndexCodeChange(e.target.value)}
          placeholder="指数代码 如 000001"
          aria-label="指数代码"
          className={`w-40 ${marketFieldCls}`}
        />
        <button type="button" disabled={tabPending} onClick={onQueryIndex} className={marketPrimaryButtonCls}>
          {tabPending ? '加载中...' : '查询指数行情'}
        </button>
      </div>
      {indexObj ? (
        <KpiGrid cols={4}>
          <KpiCard title="指数名称" value={String(indexObj.name ?? indexObj.index_name ?? '-')} />
          <KpiCard title="最新点位" value={fmtNum(indexObj.price ?? indexObj.close ?? null)} />
          <KpiCard
            title="涨跌幅"
            value={fmtPct(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? null)}
            change={Number(indexObj.changePercent ?? indexObj.change_pct ?? indexObj.pct_change ?? 0)}
          />
          <KpiCard title="成交额" value={fmtAmount(indexObj.amount ?? indexObj.turnover ?? null)} />
          <KpiCard title="最高" value={fmtNum(indexObj.high ?? null)} />
          <KpiCard title="最低" value={fmtNum(indexObj.low ?? null)} />
          <KpiCard title="开盘" value={fmtNum(indexObj.open ?? null)} />
          <KpiCard title="昨收" value={fmtNum(indexObj.prevClose ?? indexObj.prev_close ?? null)} />
        </KpiGrid>
      ) : !tabPending && !error ? (
        <EmptyState
          text="输入指数代码后查看指数行情"
          hint="如果你只是想先判断大盘环境，可直接看 000001 上证指数或 000300 沪深300。"
          action={
            <>
              <button type="button" onClick={() => onUseExampleCode('000001')} className={marketPrimaryButtonCls}>
                示例：000001
              </button>
              <button type="button" onClick={() => onUseExampleCode('000300')} className={marketSecondaryButtonCls}>
                示例：000300
              </button>
            </>
          }
        />
      ) : null}
    </SectionCard>
  );
}
