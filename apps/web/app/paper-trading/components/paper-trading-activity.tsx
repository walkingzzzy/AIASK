import { LineChart, PieChart } from '@/components/charts';
import { DataTable, SectionCard } from '@/components/ui';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import type {
  PaperTradingNavPoint,
  PaperTradingPendingOrder,
  PaperTradingPosition,
  PaperTradingTrade,
} from '@aiask/shared-types';

type PaperTradingActivityProps = {
  showAccountBootstrap: boolean;
  positions: PaperTradingPosition[];
  onQuickSell: (position: PaperTradingPosition) => void;
  pending: PaperTradingPendingOrder[];
  cancelingOrderIds: number[];
  onCancel: (orderId: number) => void;
  trades: PaperTradingTrade[];
  navData: PaperTradingNavPoint[];
  navCategories: string[];
  navValues: number[];
};

export default function PaperTradingActivity({
  showAccountBootstrap,
  positions,
  onQuickSell,
  pending,
  cancelingOrderIds,
  onCancel,
  trades,
  navData,
  navCategories,
  navValues,
}: PaperTradingActivityProps) {
  return (
    <>
      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="m-0 font-medium">持仓 ({positions.length})</h3>
            <p className="mb-0 mt-2 text-sm text-text-secondary">持仓区保留快速卖出入口，方便从复盘直接回到下一步交易动作。</p>
          </div>
        </div>
        {positions.length > 0 ? (
          <DataTable
            columns={[
              { key: 'stock_code', label: '代码' },
              { key: 'stock_name', label: '名称' },
              { key: 'quantity', label: '数量' },
              { key: 'sellable', label: '可卖' },
              { key: 'cost_price', label: '成本', render: (value: unknown) => fmtNum(Number(value), 2) },
              { key: 'current_price', label: '现价', render: (value: unknown) => fmtNum(Number(value), 2) },
              { key: 'market_value', label: '市值', render: (value: unknown) => fmtNum(Number(value)) },
              {
                key: 'profit_rate',
                label: '盈亏率',
                render: (value: unknown) => {
                  const amount = Number(value) * 100;
                  return (
                    <span className={amount >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>
                      {fmtPct(amount)}
                    </span>
                  );
                },
              },
              {
                key: 'action',
                label: '操作',
                render: (_value: unknown, row: Record<string, unknown>) => (
                  <button
                    type="button"
                    onClick={() => onQuickSell(row as PaperTradingPosition)}
                    className="action-chip cursor-pointer text-[11px] text-primary"
                  >
                    快速卖出
                  </button>
                ),
              },
            ]}
            rows={positions as Record<string, unknown>[]}
            mobileCardRender={(row) => {
              const profitRate = Number(row.profit_rate ?? 0) * 100;
              return (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-text-primary">
                        {String(row.stock_name ?? row.stock_code ?? '-')}
                      </div>
                      <div className="text-xs text-text-secondary">代码：{String(row.stock_code ?? '-')}</div>
                    </div>
                    <div className={`text-xs font-medium ${profitRate >= 0 ? 'text-danger' : 'text-success'}`}>
                      {fmtPct(profitRate)}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                    <div>数量：{String(row.quantity ?? '-')}</div>
                    <div>可卖：{String(row.sellable ?? '-')}</div>
                    <div>成本：{fmtNum(Number(row.cost_price ?? 0), 2)}</div>
                    <div>现价：{fmtNum(Number(row.current_price ?? 0), 2)}</div>
                    <div className="col-span-2">市值：{fmtNum(Number(row.market_value ?? 0))}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onQuickSell(row as PaperTradingPosition)}
                    className="action-chip cursor-pointer text-[11px] text-primary"
                  >
                    快速卖出
                  </button>
                </div>
              );
            }}
          />
        ) : (
          <div className="panel-soft mt-4 rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            {showAccountBootstrap ? '完成首笔下单后，这里会显示持仓摘要和快速卖出入口。' : '暂无持仓'}
          </div>
        )}
      </SectionCard>

      {positions.length > 0 ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">持仓分布</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                用更柔和的图表容器观察资金集中度，快速判断账户是否过度押注单一标的。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <PieChart
              data={positions.map((position) => ({
                name: position.stock_name || position.stock_code || '未知',
                value: Number(position.market_value ?? 0),
              }))}
              donut
              height={260}
            />
          </div>
        </SectionCard>
      ) : null}

      {pending.length > 0 ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">挂单 ({pending.length})</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">挂单区保留撤单入口，方便在发现风控或价格偏差时直接修正。</p>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              columns={[
                { key: 'code', label: '代码' },
                { key: 'direction', label: '方向' },
                { key: 'shares', label: '数量' },
                { key: 'order_type', label: '类型' },
                { key: 'price', label: '价格', render: (value: unknown) => (value ? fmtNum(Number(value), 2) : '-') },
                { key: 'stop_price', label: '止损价', render: (value: unknown) => (value ? fmtNum(Number(value), 2) : '-') },
                {
                  key: 'id',
                  label: '操作',
                  render: (_value: unknown, row: Record<string, unknown>) => (
                    <button
                      type="button"
                      onClick={() => onCancel(Number(row.id))}
                      disabled={cancelingOrderIds.includes(Number(row.id))}
                      className="action-chip cursor-pointer text-[11px] text-danger disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {cancelingOrderIds.includes(Number(row.id)) ? '撤单中...' : '撤单'}
                    </button>
                  ),
                },
              ]}
              rows={pending as Record<string, unknown>[]}
              mobileCardRender={(row) => {
                const orderId = Number(row.id ?? 0);
                const isCanceling = cancelingOrderIds.includes(orderId);
                return (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">
                          {String(row.code ?? '-')} · {String(row.direction ?? '-')}
                        </div>
                        <div className="text-xs text-text-secondary">
                          {String(row.order_type ?? '-')} / {String(row.shares ?? '-')} 股
                        </div>
                      </div>
                      <div className="text-xs text-text-secondary">#{orderId || '-'}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div>价格：{row.price ? fmtNum(Number(row.price), 2) : '-'}</div>
                      <div>止损价：{row.stop_price ? fmtNum(Number(row.stop_price), 2) : '-'}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onCancel(orderId)}
                      disabled={isCanceling}
                      className="action-chip cursor-pointer text-[11px] text-danger disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isCanceling ? '撤单中...' : '撤单'}
                    </button>
                  </div>
                );
              }}
            />
          </div>
        </SectionCard>
      ) : null}

      {!showAccountBootstrap ? (
        <>
          <SectionCard className="mb-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="m-0 font-medium">成交记录</h3>
                <p className="mb-0 mt-2 text-sm text-text-secondary">把成交时间、方向、金额和佣金保留在同一块，方便回溯一次委托的真实落地结果。</p>
              </div>
            </div>
            {trades.length > 0 ? (
              <div className="mt-4">
                <DataTable
                  columns={[
                    { key: 'trade_time', label: '时间', render: (value: unknown) => String(value ?? '').slice(0, 16) },
                    { key: 'stock_code', label: '代码' },
                    { key: 'trade_type', label: '方向' },
                    { key: 'quantity', label: '数量' },
                    { key: 'price', label: '价格', render: (value: unknown) => fmtNum(Number(value), 2) },
                    { key: 'amount', label: '金额', render: (value: unknown) => fmtNum(Number(value)) },
                    { key: 'commission', label: '佣金', render: (value: unknown) => fmtNum(Number(value), 4) },
                  ]}
                  rows={trades as Record<string, unknown>[]}
                  mobileCardRender={(row) => (
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-text-primary">
                            {String(row.stock_code ?? '-')} · {String(row.trade_type ?? '-')}
                          </div>
                          <div className="text-xs text-text-secondary">
                            时间：{String(row.trade_time ?? '').slice(0, 16) || '-'}
                          </div>
                        </div>
                        <div className="text-xs text-text-secondary">{String(row.quantity ?? '-')} 股</div>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                        <div>价格：{fmtNum(Number(row.price ?? 0), 2)}</div>
                        <div>金额：{fmtNum(Number(row.amount ?? 0))}</div>
                        <div className="col-span-2">佣金：{fmtNum(Number(row.commission ?? 0), 4)}</div>
                      </div>
                    </div>
                  )}
                />
              </div>
            ) : (
              <div className="panel-soft mt-4 rounded-[22px] px-4 py-3 text-sm text-text-secondary">暂无成交</div>
            )}
          </SectionCard>

          {navData.length > 1 ? (
            <SectionCard className="p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">账户净值走势</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    净值曲线用于确认模拟交易是否真的沉淀成稳定账户表现，而不只是零散的单笔结果。
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <LineChart categories={navCategories} series={[{ name: '净值', data: navValues }]} />
              </div>
            </SectionCard>
          ) : null}
        </>
      ) : null}
    </>
  );
}
