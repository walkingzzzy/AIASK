import Link from 'next/link';
import { DataTable, SectionCard } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  marketFieldCls,
  marketLinkChipCls,
  marketPrimaryButtonCls,
} from '@/app/market/components/market-panel-styles';

type MarketBlocksTabProps = {
  tabPending: boolean;
  blocksRows: Record<string, unknown>[];
  blockStocksRows: Record<string, unknown>[];
  blocksError: string | null;
  blockCode: string;
  onBlockCodeChange: (value: string) => void;
  onLoadBlocks: () => void;
  onLoadBlockStocks: () => void;
  onSelectBlock: (blockCode: string) => void;
};

export default function MarketBlocksTab({
  tabPending,
  blocksRows,
  blockStocksRows,
  blocksError,
  blockCode,
  onBlockCodeChange,
  onLoadBlocks,
  onLoadBlockStocks,
  onSelectBlock,
}: MarketBlocksTabProps) {
  return (
    <SectionCard tabAttached>
      <button type="button" disabled={tabPending} onClick={onLoadBlocks} className={marketPrimaryButtonCls}>
        {tabPending ? '加载中...' : '加载行业板块'}
      </button>
      {blocksRows.length ? (
        <DataTable
          rows={blocksRows}
          columns={[
            { key: 'code', label: '板块代码' },
            { key: 'name', label: '板块名称' },
            { key: 'stockCount', label: '股票数', align: 'right' as const },
            {
              key: 'avgChange',
              label: '平均涨幅',
              align: 'right' as const,
              render: (v: unknown) => (
                <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
              ),
            },
            { key: 'leaderName', label: '领涨股' },
          ]}
          maxHeight={400}
          onExport={() => exportCSV(blocksRows, 'blocks')}
          searchable
          onRowClick={(row) => {
            const nextCode = String(row.code ?? '');
            if (nextCode) onSelectBlock(nextCode);
          }}
        />
      ) : !tabPending && !blocksError ? (
        <EmptyState
          text="先加载行业板块再看轮动"
          hint="板块页更适合作为行情入口：先找到强弱板块，再点进成分股或回个股页继续看。"
          action={
            <>
              <button type="button" onClick={onLoadBlocks} className={marketPrimaryButtonCls}>
                加载行业板块
              </button>
              <Link href="/fund-flow" className={marketLinkChipCls}>
                去看资金流向
              </Link>
            </>
          }
        />
      ) : null}
      <div className="mt-2 flex items-center gap-2">
        <input
          value={blockCode}
          onChange={(e) => onBlockCodeChange(e.target.value)}
          placeholder="板块代码"
          aria-label="板块代码"
          className={`w-40 ${marketFieldCls}`}
        />
        <button type="button" disabled={tabPending} onClick={onLoadBlockStocks} className={marketPrimaryButtonCls}>
          查看成分股
        </button>
      </div>
      {blockStocksRows.length ? (
        <DataTable
          rows={blockStocksRows}
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
              label: '涨跌幅',
              align: 'right' as const,
              render: (v: unknown) => (
                <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
              ),
            },
          ]}
          maxHeight={400}
          onExport={() => exportCSV(blockStocksRows, 'block-stocks')}
        />
      ) : null}
    </SectionCard>
  );
}
