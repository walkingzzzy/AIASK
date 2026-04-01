import { Badge, DataTable, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import { executionChipButtonCls } from '@/app/execution/components/execution-panel-styles';
import type { PaperTradingPendingOrdersResponse } from '@aiask/shared-types';

type ExecutionPendingOrdersPanelProps = {
  pendingOrders: PaperTradingPendingOrdersResponse['orders'];
  onRefresh: () => void;
};

export default function ExecutionPendingOrdersPanel({
  pendingOrders,
  onRefresh,
}: ExecutionPendingOrdersPanelProps) {
  return (
    <SectionCard>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="m-0 font-medium">当前挂单</h3>
        <button type="button" onClick={onRefresh} className={executionChipButtonCls}>
          刷新挂单
        </button>
      </div>
      <DataTable
        rows={pendingOrders as unknown as Record<string, unknown>[]}
        emptyText="暂无挂单"
        columns={[
          {
            key: 'created_at',
            label: '时间',
            render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
          },
          { key: 'code', label: '代码' },
          { key: 'direction', label: '方向' },
          { key: 'shares', label: '数量' },
          {
            key: 'price',
            label: '价格',
            render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
          },
          { key: 'status', label: '状态' },
        ]}
        mobileCardRender={(row) => (
          <div className="space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">
                  {String(row.code ?? '-')} · {String(row.direction ?? '-')}
                </div>
                <div className="text-xs text-text-secondary">{String(row.created_at ?? '').slice(0, 16) || '-'}</div>
              </div>
              <Badge variant={String(row.status ?? '').includes('fill') ? 'success' : 'warning'}>
                {String(row.status ?? '-')}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
              <div>数量：{String(row.shares ?? '-')}</div>
              <div>价格：{row.price == null ? '-' : fmtNum(Number(row.price), 2)}</div>
            </div>
          </div>
        )}
      />
    </SectionCard>
  );
}
