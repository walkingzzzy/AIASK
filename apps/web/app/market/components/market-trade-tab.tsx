import { DataTable, SectionCard, Badge } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import {
  marketFieldCls,
  marketPrimaryButtonCls,
} from '@/app/market/components/market-panel-styles';
import { exportCSV } from '@/lib/export';

type MarketTradeTabProps = {
  code: string;
  onCodeChange: (value: string) => void;
  tabPending: boolean;
  tradeRows: Record<string, unknown>[];
  error: string | null;
  onQueryTrade: () => void;
  onShowSearch: () => void;
};

export default function MarketTradeTab({
  code,
  onCodeChange,
  tabPending,
  tradeRows,
  error,
  onQueryTrade,
  onShowSearch,
}: MarketTradeTabProps) {
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
        <button type="button" disabled={tabPending} onClick={onQueryTrade} className={marketPrimaryButtonCls}>
          {tabPending ? '加载中...' : '查询逐笔明细'}
        </button>
      </div>
      {tradeRows.length ? (
        <DataTable
          rows={tradeRows}
          columns={[
            { key: 'time', label: '时间' },
            { key: 'price', label: '价格', align: 'right' as const },
            { key: 'volume', label: '成交量', align: 'right' as const },
            {
              key: 'direction',
              label: '方向',
              render: (v: unknown) => {
                const text = String(v ?? '');
                const isBuy = /买|buy/i.test(text);
                const isSell = /卖|sell/i.test(text);
                return <Badge variant={isBuy ? 'danger' : isSell ? 'success' : 'neutral'}>{text || '-'}</Badge>;
              },
            },
          ]}
          maxHeight={400}
          onExport={() => exportCSV(tradeRows, 'trade-details')}
        />
      ) : !tabPending && !error ? (
        <EmptyState
          text="输入股票代码后查看逐笔成交"
          hint="逐笔明细更适合在你已经锁定标的后使用；如果还没锁定，先去搜索或看基础行情会更快。"
          action={
            <>
              <button type="button" onClick={onShowSearch} className={marketPrimaryButtonCls}>
                先去搜索标的
              </button>
            </>
          }
        />
      ) : null}
    </SectionCard>
  );
}
