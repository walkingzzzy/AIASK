import Link from 'next/link';
import { DataTable, SectionCard } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { exportCSV } from '@/lib/export';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import {
  marketFieldCls,
  marketLinkChipCls,
  marketPrimaryButtonCls,
} from '@/app/market/components/market-panel-styles';

type MarketSearchTabProps = {
  searchKeyword: string;
  onSearchKeywordChange: (value: string) => void;
  tabPending: boolean;
  searchRows: Record<string, unknown>[];
  searchError: string | null;
  onSearch: () => void;
  onLoadStockList: () => void;
  stockListRows: Record<string, unknown>[];
  batchCodes: string;
  onBatchCodesChange: (value: string) => void;
  onBatchQuotes: () => void;
  batchRows: Record<string, unknown>[];
};

export default function MarketSearchTab({
  searchKeyword,
  onSearchKeywordChange,
  tabPending,
  searchRows,
  searchError,
  onSearch,
  onLoadStockList,
  stockListRows,
  batchCodes,
  onBatchCodesChange,
  onBatchQuotes,
  batchRows,
}: MarketSearchTabProps) {
  return (
    <SectionCard tabAttached>
      <div className="flex items-center gap-2">
        <input
          value={searchKeyword}
          onChange={(e) => onSearchKeywordChange(e.target.value)}
          placeholder="搜索股票"
          aria-label="搜索关键词"
          className={`w-50 ${marketFieldCls}`}
        />
        <button type="button" disabled={tabPending} onClick={onSearch} className={marketPrimaryButtonCls}>
          {tabPending ? '搜索中...' : '搜索'}
        </button>
      </div>
      {searchRows.length ? (
        <DataTable
          rows={searchRows}
          columns={[
            {
              key: 'code',
              label: '代码',
              render: (v: unknown, row: Record<string, unknown>) => (
                <StockLink code={String(v)} name={String(row.name ?? '')} />
              ),
            },
            { key: 'name', label: '名称' },
            { key: 'industry', label: '行业' },
            {
              key: '_watch',
              label: '',
              width: 40,
              sortable: false,
              render: (_: unknown, row: Record<string, unknown>) => (
                <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
              ),
            },
          ]}
          maxHeight={300}
          onExport={() => exportCSV(searchRows, 'search-results')}
          searchable
        />
      ) : !tabPending && !searchError ? (
        <EmptyState
          text="先输入名称或代码开始搜索"
          hint="如果你还不确定代码，可以搜名称、行业词，或者直接加载全市场列表后再筛。"
          action={
            <>
              <button type="button" onClick={onLoadStockList} className={marketPrimaryButtonCls}>
                加载全市场列表
              </button>
              <Link href="/watchlist" className={marketLinkChipCls}>
                去自选股挑选
              </Link>
            </>
          }
        />
      ) : null}
      <div className="mt-3 flex items-center gap-2">
        <button type="button" disabled={tabPending} onClick={onLoadStockList} className={marketPrimaryButtonCls}>
          加载全部股票列表
        </button>
      </div>
      {stockListRows.length ? (
        <DataTable
          rows={stockListRows}
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
              key: '_watch',
              label: '',
              width: 40,
              sortable: false,
              render: (_: unknown, row: Record<string, unknown>) => (
                <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
              ),
            },
          ]}
          maxHeight={300}
          onExport={() => exportCSV(stockListRows, 'stock-list')}
          searchable
          pageSize={50}
        />
      ) : null}
      <div className="mt-3 flex items-center gap-2">
        <input
          value={batchCodes}
          onChange={(e) => onBatchCodesChange(e.target.value)}
          placeholder="批量代码，逗号分隔"
          aria-label="批量股票代码"
          className={`w-75 ${marketFieldCls}`}
        />
        <button type="button" disabled={tabPending} onClick={onBatchQuotes} className={marketPrimaryButtonCls}>
          批量行情
        </button>
      </div>
      {batchRows.length ? (
        <DataTable
          rows={batchRows}
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
            {
              key: 'volume',
              label: '成交量',
              align: 'right' as const,
              render: (v: unknown) => fmtAmount(v as number),
            },
            {
              key: 'amount',
              label: '成交额',
              align: 'right' as const,
              render: (v: unknown) => fmtAmount(v as number),
            },
            { key: 'high', label: '最高', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            { key: 'low', label: '最低', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
            {
              key: '_watch',
              label: '',
              width: 40,
              sortable: false,
              render: (_: unknown, row: Record<string, unknown>) => (
                <WatchlistButton code={String(row.code)} name={String(row.name ?? '')} />
              ),
            },
          ]}
          maxHeight={300}
          onExport={() => exportCSV(batchRows, 'batch-quotes')}
        />
      ) : null}
    </SectionCard>
  );
}
