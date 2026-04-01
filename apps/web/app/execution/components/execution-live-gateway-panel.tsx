import type { FormEventHandler } from 'react';
import { Badge, DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import {
  executionChipButtonCls,
  executionNoteCardCls,
  executionPrimaryButtonCls,
} from '@/app/execution/components/execution-panel-styles';
import type {
  LiveTradingGatewayStatusResponse,
  LiveTradingMirrorToPaperResponse,
  LiveTradingSubmitOrderResponse,
  LiveTradingSyncOrderEventsResponse,
} from '@aiask/shared-types';

type LiveGatewayAccount = {
  account_id?: string | null;
  status?: string | null;
  cash?: number | null;
  portfolio_value?: number | null;
};

type LiveOrderStatus = {
  order_id?: string | null;
  symbol?: string | null;
  status?: string | null;
  filled_qty?: string | number | null;
};

type LiveReceipt = {
  message_type?: string | null;
  status?: string | null;
  reason?: string | null;
};

export type ExecutionLiveGatewayPanelProps = {
  liveGateway: LiveTradingGatewayStatusResponse | null;
  liveAccount: LiveGatewayAccount | null;
  liveGatewayReady: boolean;
  liveGatewayRefreshing: boolean;
  livePositions: Record<string, unknown>[];
  liveOrders: Record<string, unknown>[];
  liveOrdersStatus: string;
  liveFillRows: Record<string, unknown>[];
  liveEventRows: Record<string, unknown>[];
  liveOrderStatus: LiveOrderStatus | null;
  liveReceipt: LiveReceipt | null;
  liveSubmitResult: LiveTradingSubmitOrderResponse | null;
  liveMirrorResult: LiveTradingMirrorToPaperResponse | null;
  liveSyncEventsResult: LiveTradingSyncOrderEventsResponse | null;
  liveEventArtifactId: string;
  liveEventArtifactCount: number;
  liveEventCurrentStatus: string;
  submittedLiveOrderId: string;
  liveForm: {
    symbol: string;
    side: 'buy' | 'sell';
    qty: string;
    orderType: 'market' | 'limit' | 'stop';
    limitPrice: string;
    stopPrice: string;
    dryRun: boolean;
    mirrorExecute: boolean;
    orderIdInput: string;
  };
  pending: {
    submit: boolean;
    cancel: boolean;
    mirror: boolean;
    sync: boolean;
  };
  errors: {
    gateway?: string | null;
    account?: string | null;
    positions?: string | null;
    orders?: string | null;
    fills?: string | null;
    orderStatus?: string | null;
    receipt?: string | null;
    events?: string | null;
    form?: string | null;
    submit?: string | null;
    cancel?: string | null;
    mirror?: string | null;
    sync?: string | null;
  };
  onRefresh: () => void;
  onSymbolChange: (value: string) => void;
  onSideChange: (value: 'buy' | 'sell') => void;
  onQtyChange: (value: string) => void;
  onOrderTypeChange: (value: 'market' | 'limit' | 'stop') => void;
  onLiveOrdersStatusChange: (value: string) => void;
  onLimitPriceChange: (value: string) => void;
  onStopPriceChange: (value: string) => void;
  onDryRunChange: (value: boolean) => void;
  onMirrorExecuteChange: (value: boolean) => void;
  onOrderIdInputChange: (value: string) => void;
  onSubmitOrder: () => void;
  onMirrorToPaper: () => void;
  onOrderQuery: FormEventHandler<HTMLFormElement>;
  onCancelOrder: () => void;
  onSelectLiveOrder: (row: Record<string, unknown>) => void;
  onSyncEvents: () => void;
  onOpenArtifactDetail: (artifactId: string) => void;
  onUseArtifactForQuery: (artifactId: string) => void;
};

export default function ExecutionLiveGatewayPanel({
  liveGateway,
  liveAccount,
  liveGatewayReady,
  liveGatewayRefreshing,
  livePositions,
  liveOrders,
  liveOrdersStatus,
  liveFillRows,
  liveEventRows,
  liveOrderStatus,
  liveReceipt,
  liveSubmitResult,
  liveMirrorResult,
  liveSyncEventsResult,
  liveEventArtifactId,
  liveEventArtifactCount,
  liveEventCurrentStatus,
  submittedLiveOrderId,
  liveForm,
  pending,
  errors,
  onRefresh,
  onSymbolChange,
  onSideChange,
  onQtyChange,
  onOrderTypeChange,
  onLiveOrdersStatusChange,
  onLimitPriceChange,
  onStopPriceChange,
  onDryRunChange,
  onMirrorExecuteChange,
  onOrderIdInputChange,
  onSubmitOrder,
  onMirrorToPaper,
  onOrderQuery,
  onCancelOrder,
  onSelectLiveOrder,
  onSyncEvents,
  onOpenArtifactDetail,
  onUseArtifactForQuery,
}: ExecutionLiveGatewayPanelProps) {
  return (
    <SectionCard className="mb-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="m-0 font-medium">Live Gateway</h3>
          <p className="mb-0 mt-1 text-xs text-text-secondary">
            当前产品侧已接入真实券商网关主入口。默认只读预览，只有在网关显式开启写权限时才会真正下单或撤单。
          </p>
        </div>
        <button type="button" onClick={onRefresh} className={executionChipButtonCls}>
          {liveGatewayRefreshing ? '刷新中...' : '刷新网关'}
        </button>
      </div>

      <KpiGrid cols={6} className="mt-4">
        <KpiCard title="Provider" value={liveGateway?.provider || '-'} />
        <KpiCard title="配置状态" value={liveGateway?.configured ? '已配置' : '未配置'} />
        <KpiCard title="连接状态" value={liveGateway?.connected ? '已连接' : '未连接'} />
        <KpiCard title="模式" value={liveGateway?.read_only ? '只读/预览' : '可写'} />
        <KpiCard title="真实订单" value={liveOrders.length} />
        <KpiCard title="成交回报" value={liveFillRows.length} />
      </KpiGrid>

      <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <div className="panel-soft rounded-[24px] p-4">
          <div className="text-sm font-medium text-text-primary">网关状态与账户</div>
          <div className="mt-2 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
            <div>Base URL：{liveGateway?.base_url || '-'}</div>
            <div>Paper：{liveGateway?.paper ? '是' : '否'}</div>
            <div>账户：{liveAccount?.account_id || '-'}</div>
            <div>状态：{liveAccount?.status || '-'}</div>
            <div>现金：{liveAccount?.cash != null ? fmtNum(liveAccount.cash) : '-'}</div>
            <div>净值：{liveAccount?.portfolio_value != null ? fmtNum(liveAccount.portfolio_value) : '-'}</div>
          </div>
          {liveGateway?.error ? <p className="mt-3 mb-0 text-xs text-danger">{liveGateway.error}</p> : null}
          {errors.gateway ? <p className="mt-2 mb-0 text-xs text-danger">{errors.gateway}</p> : null}
          {errors.account ? <p className="mt-2 mb-0 text-xs text-danger">{errors.account}</p> : null}
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-text-primary">真实订单预览 / 提交</div>
              <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
                把真实网关的订单参数、dry-run 和镜像动作收在一块更松弛的 glass 表单里，减少“配置区 + 结果区”割裂感。
              </p>
            </div>
            <Badge variant={liveForm.dryRun ? 'info' : 'warning'}>
              {liveForm.dryRun ? '当前为预览模式' : '当前允许真实动作'}
            </Badge>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>标的</span>
              <input
                value={liveForm.symbol}
                onChange={(event) => onSymbolChange(event.target.value)}
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>方向</span>
              <select
                value={liveForm.side}
                onChange={(event) => onSideChange(event.target.value as 'buy' | 'sell')}
                className="text-sm"
              >
                <option value="buy">buy</option>
                <option value="sell">sell</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>数量</span>
              <input
                type="number"
                min={1}
                value={liveForm.qty}
                onChange={(event) => onQtyChange(event.target.value)}
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>订单类型</span>
              <select
                value={liveForm.orderType}
                onChange={(event) => onOrderTypeChange(event.target.value as 'market' | 'limit' | 'stop')}
                className="text-sm"
              >
                <option value="market">market</option>
                <option value="limit">limit</option>
                <option value="stop">stop</option>
              </select>
            </label>
            {liveForm.orderType === 'limit' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>Limit Price</span>
                <input
                  type="number"
                  step="0.01"
                  value={liveForm.limitPrice}
                  onChange={(event) => onLimitPriceChange(event.target.value)}
                  className="text-sm"
                />
              </label>
            ) : null}
            {liveForm.orderType === 'stop' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>Stop Price</span>
                <input
                  type="number"
                  step="0.01"
                  value={liveForm.stopPrice}
                  onChange={(event) => onStopPriceChange(event.target.value)}
                  className="text-sm"
                />
              </label>
            ) : null}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className={`${executionNoteCardCls} flex items-center gap-2`}>
              <input
                type="checkbox"
                checked={liveForm.dryRun}
                onChange={(event) => onDryRunChange(event.target.checked)}
              />
              dry_run / 预览模式
            </label>
            <label className={`${executionNoteCardCls} flex items-center gap-2`}>
              <input
                type="checkbox"
                checked={liveForm.mirrorExecute}
                onChange={(event) => onMirrorExecuteChange(event.target.checked)}
              />
              mirror 执行到 paper
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSubmitOrder}
              disabled={pending.submit}
              className={executionPrimaryButtonCls}
            >
              {pending.submit ? '处理中...' : '预览 / 提交订单'}
            </button>
            <button
              type="button"
              onClick={onMirrorToPaper}
              disabled={pending.mirror}
              className={executionChipButtonCls}
            >
              {pending.mirror ? '镜像中...' : '镜像到 Paper'}
            </button>
          </div>
          <form onSubmit={onOrderQuery} className="mt-3 flex flex-wrap items-end gap-2">
            <label className="flex min-w-[220px] flex-1 flex-col gap-2 text-xs text-text-secondary">
              <span>order_id</span>
              <input
                value={liveForm.orderIdInput}
                onChange={(event) => onOrderIdInputChange(event.target.value)}
                className="text-sm"
              />
            </label>
            <button type="submit" className={executionChipButtonCls}>
              查询订单
            </button>
            <button
              type="button"
              onClick={onCancelOrder}
              disabled={pending.cancel}
              className={executionChipButtonCls}
            >
              {pending.cancel ? '处理中...' : '预览 / 撤单'}
            </button>
          </form>
          {errors.form ? <p className="mt-2 mb-0 text-xs text-danger">{errors.form}</p> : null}
          {errors.submit ? <p className="mt-2 mb-0 text-xs text-danger">{errors.submit}</p> : null}
          {errors.cancel ? <p className="mt-2 mb-0 text-xs text-danger">{errors.cancel}</p> : null}
          {errors.mirror ? <p className="mt-2 mb-0 text-xs text-danger">{errors.mirror}</p> : null}
          {errors.sync ? <p className="mt-2 mb-0 text-xs text-danger">{errors.sync}</p> : null}
        </div>
      </div>

      <div className="mt-4 grid gap-4 2xl:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-text-primary">真实持仓</div>
            <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
              {liveGatewayReady ? `${livePositions.length} 条` : '网关未就绪'}
            </Badge>
          </div>
          <DataTable
            rows={livePositions}
            emptyText="暂无真实持仓"
            columns={[
              { key: 'symbol', label: '标的' },
              { key: 'side', label: '方向' },
              { key: 'qty', label: '数量' },
              {
                key: 'avg_entry_price',
                label: '成本价',
                render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
              },
              {
                key: 'market_value',
                label: '市值',
                render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
              },
            ]}
          />
          {errors.positions ? <p className="mt-2 mb-0 text-xs text-danger">{errors.positions}</p> : null}
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium text-text-primary">真实订单</div>
              <select
                value={liveOrdersStatus}
                onChange={(event) => onLiveOrdersStatusChange(event.target.value)}
                className="w-auto min-w-[92px] text-xs"
              >
                <option value="open">open</option>
                <option value="closed">closed</option>
                <option value="all">all</option>
              </select>
            </div>
            <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
              {liveGatewayReady ? `${liveOrders.length} 条` : '网关未就绪'}
            </Badge>
          </div>
          <DataTable
            rows={liveOrders}
            emptyText="暂无真实订单"
            onRowClick={onSelectLiveOrder}
            columns={[
              { key: 'order_id', label: '订单 ID' },
              { key: 'symbol', label: '标的' },
              { key: 'side', label: '方向' },
              { key: 'status', label: '状态' },
              { key: 'qty', label: '数量' },
              {
                key: 'submitted_at',
                label: '提交时间',
                render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
              },
            ]}
          />
          <p className="mt-2 mb-0 text-xs text-text-secondary">
            点击订单行可直接切换下方的回执、成交回报和事件链。
          </p>
          {errors.orders ? <p className="mt-2 mb-0 text-xs text-danger">{errors.orders}</p> : null}
          {liveOrderStatus ? (
            <div className={`${executionNoteCardCls} mt-3`}>
              订单 {liveOrderStatus.order_id || '-'} · {liveOrderStatus.symbol || '-'} ·{' '}
              {liveOrderStatus.status || '-'} · 已成交 {liveOrderStatus.filled_qty ?? '-'}
            </div>
          ) : null}
          {liveReceipt ? (
            <div className={`${executionNoteCardCls} mt-3`}>
              券商回执 {liveReceipt.message_type || '-'} · {liveReceipt.status || '-'} ·{' '}
              {liveReceipt.reason || '无补充原因'}
            </div>
          ) : null}
          {errors.orderStatus ? <p className="mt-2 mb-0 text-xs text-danger">{errors.orderStatus}</p> : null}
          {errors.receipt ? <p className="mt-2 mb-0 text-xs text-danger">{errors.receipt}</p> : null}
          {liveSubmitResult ? (
            <div className={`${executionNoteCardCls} mt-3`}>
              {liveSubmitResult.submitted
                ? `真实订单已提交：${liveSubmitResult.order?.order_id || '-'}`
                : `当前返回为 ${liveSubmitResult.mode || 'preview'}，未真正提交真实订单。`}
            </div>
          ) : null}
          {liveMirrorResult ? (
            <div className={`${executionNoteCardCls} mt-3`}>
              {liveMirrorResult.message ? (
                <span>{liveMirrorResult.message}</span>
              ) : (
                <>
                  镜像候选 {liveMirrorResult.mirrorable_count ?? 0} 条，已下发到 paper{' '}
                  {liveMirrorResult.placed_order_count ?? 0} 条，paper 账户{' '}
                  {liveMirrorResult.paper_account_id || '-'}。
                </>
              )}
            </div>
          ) : null}
          {liveSyncEventsResult?.artifact_id ? (
            <div className={`${executionNoteCardCls} mt-3`}>
              事件快照已同步，artifact {liveSyncEventsResult.artifact_id}。
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-4 2xl:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-text-primary">成交回报</div>
            <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
              {liveGatewayReady ? `${liveFillRows.length} 条` : '网关未就绪'}
            </Badge>
          </div>
          <DataTable
            rows={liveFillRows}
            emptyText={submittedLiveOrderId.trim() ? '当前订单暂无成交回报' : '暂无成交回报'}
            columns={[
              { key: 'occurred_at', label: '成交时间' },
              { key: 'symbol', label: '标的' },
              { key: 'side', label: '方向' },
              { key: 'qty', label: '数量' },
              {
                key: 'price',
                label: '成交价',
                render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
              },
              {
                key: 'amount',
                label: '成交额',
                render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
              },
              {
                key: 'commission',
                label: '佣金',
                render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
              },
            ]}
          />
          {errors.fills ? <p className="mt-2 mb-0 text-xs text-danger">{errors.fills}</p> : null}
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium text-text-primary">订单事件链</div>
              <Badge variant={submittedLiveOrderId.trim() ? 'info' : 'neutral'}>
                {submittedLiveOrderId.trim() || '未选择订单'}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {liveEventArtifactId ? (
                <button
                  type="button"
                  onClick={() => onOpenArtifactDetail(liveEventArtifactId)}
                  className={executionChipButtonCls}
                >
                  查看 artifact 详情
                </button>
              ) : null}
              <button
                type="button"
                onClick={onSyncEvents}
                disabled={pending.sync}
                className={executionChipButtonCls}
              >
                {pending.sync ? '同步中...' : '同步事件快照'}
              </button>
            </div>
          </div>
          {submittedLiveOrderId.trim() ? (
            <>
              <KpiGrid cols={4} className="mb-3">
                <KpiCard title="事件数" value={liveEventRows.length} />
                <KpiCard title="回执" value={liveReceipt?.message_type || '-'} />
                <KpiCard title="当前状态" value={liveEventCurrentStatus || '-'} />
                <KpiCard title="同步 artifact" value={liveSyncEventsResult?.artifact_id || '-'} />
              </KpiGrid>
              {liveEventArtifactId ? (
                <div className={`${executionNoteCardCls} mb-3`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      当前事件链快照已写入 artifact {liveEventArtifactId}，已收集 {liveEventArtifactCount}{' '}
                      条事件，可跳转独立详情页查看完整链路。
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => onUseArtifactForQuery(liveEventArtifactId)}
                        className={executionChipButtonCls}
                      >
                        回填到 artifact 查询
                      </button>
                      <button
                        type="button"
                        onClick={() => onOpenArtifactDetail(liveEventArtifactId)}
                        className={executionChipButtonCls}
                      >
                        打开详情页
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
              <DataTable
                rows={liveEventRows}
                emptyText="当前订单暂无事件记录"
                columns={[
                  { key: 'occurred_at', label: '时间' },
                  { key: 'event_type', label: '事件' },
                  { key: 'event_category', label: '类别' },
                  { key: 'event_status', label: '状态' },
                  { key: 'from_status', label: '前状态' },
                  { key: 'to_status', label: '后状态' },
                  { key: 'fill_qty', label: '成交量' },
                  {
                    key: 'fill_price',
                    label: '成交价',
                    render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                  },
                ]}
              />
            </>
          ) : (
            <div className={`${executionNoteCardCls} p-4`}>
              输入 `order_id` 并查询订单后，这里会显示提交、回执、成交、撤单的完整事件链。
            </div>
          )}
          {errors.events ? <p className="mt-2 mb-0 text-xs text-danger">{errors.events}</p> : null}
        </div>
      </div>
    </SectionCard>
  );
}
