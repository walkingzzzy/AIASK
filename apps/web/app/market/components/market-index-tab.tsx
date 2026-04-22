import { KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import { marketFieldCls, marketPrimaryButtonCls } from '@/app/market/components/market-panel-styles';

type MarketIndexTabProps = {
  indexCode: string;
  onIndexCodeChange: (value: string) => void;
  tabPending: boolean;
  indexObj: Record<string, unknown> | null;
  error: string | null;
  onQueryIndex: () => void;
};

export default function MarketIndexTab({
  indexCode,
  onIndexCodeChange,
  tabPending,
  indexObj,
  error,
  onQueryIndex,
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
          hint="请输入真实指数代码后再查询；如果你只想看整体环境，也可以先切回首页或板块视图。"
        />
      ) : null}
    </SectionCard>
  );
}
