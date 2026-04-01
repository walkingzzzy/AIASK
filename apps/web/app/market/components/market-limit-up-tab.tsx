import Link from 'next/link';
import { DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { marketLinkChipCls, marketPrimaryButtonCls } from '@/app/market/components/market-panel-styles';

type MarketLimitUpTabProps = {
  tabPending: boolean;
  limitUpRows: Record<string, unknown>[];
  limitUpStatsObj: Record<string, unknown> | null;
  error: string | null;
  onRefresh: () => void;
  onShowBlocks: () => void;
};

export default function MarketLimitUpTab({
  tabPending,
  limitUpRows,
  limitUpStatsObj,
  error,
  onRefresh,
  onShowBlocks,
}: MarketLimitUpTabProps) {
  return (
    <SectionCard tabAttached>
      <button type="button" disabled={tabPending} onClick={onRefresh} className={marketPrimaryButtonCls}>
        {tabPending ? '加载中...' : '刷新'}
      </button>
      {limitUpStatsObj ? (
        <KpiGrid cols={3}>
          <KpiCard
            title="涨停总数"
            value={(limitUpStatsObj.totalLimitUp as number) ?? (limitUpStatsObj.total as number) ?? '-'}
          />
          <KpiCard
            title="首板数量"
            value={(limitUpStatsObj.firstBoard as number) ?? (limitUpStatsObj.first_board as number) ?? '-'}
          />
          <KpiCard
            title="封板成功率"
            value={fmtPct(Number(limitUpStatsObj.successRate ?? limitUpStatsObj.success_rate ?? 0))}
          />
        </KpiGrid>
      ) : null}
      {limitUpRows.length ? (
        <DataTable
          rows={limitUpRows}
          columns={[
            {
              key: 'code',
              label: '代码',
              render: (v: unknown, row: Record<string, unknown>) => (
                <StockLink code={String(v)} name={String(row.name ?? '')} />
              ),
            },
            { key: 'name', label: '名称' },
            {
              key: 'price',
              label: '现价',
              align: 'right' as const,
              render: (v: unknown) => fmtNum(v as number, 2),
            },
            {
              key: 'changePercent',
              label: '涨幅',
              align: 'right' as const,
              render: (v: unknown) => (
                <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
              ),
            },
            { key: 'continuousDays', label: '连板', align: 'right' as const },
            { key: 'industry', label: '行业' },
            {
              key: '_watch',
              label: '',
              width: 40,
              render: (_: unknown, row: Record<string, unknown>) => (
                <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
              ),
            },
          ]}
          maxHeight={400}
          onExport={() => exportCSV(limitUpRows, 'limit-up')}
        />
      ) : !tabPending && !error ? (
        <EmptyState
          text="当前还没有涨停榜单"
          hint="如果你在做日内复盘，可以先刷新榜单；如果更想看整体强弱，先去板块轮动通常更直接。"
          action={
            <>
              <button type="button" onClick={onShowBlocks} className={marketPrimaryButtonCls}>
                看板块轮动
              </button>
              <Link href="/research" className={marketLinkChipCls}>
                去研究页找催化
              </Link>
            </>
          }
        />
      ) : null}
    </SectionCard>
  );
}
