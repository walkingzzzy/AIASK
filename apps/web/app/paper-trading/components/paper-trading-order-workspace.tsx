import type { FormEvent } from 'react';
import { Badge, SectionCard, StockCodeInput } from '@/components/ui';
import {
  paperTradingChipButtonCls,
  paperTradingNoteCardCls,
} from '@/app/paper-trading/components/paper-trading-panel-styles';
import { fmtNum } from '@/lib/data-utils';

type PaperTradingOrderWorkspaceProps = {
  showAccountBootstrap: boolean;
  handleOrder: (event: FormEvent) => void;
  code: string;
  setCode: (value: string) => void;
  codeError: string | null;
  direction: 'buy' | 'sell';
  setDirection: (value: 'buy' | 'sell') => void;
  quantity: string;
  setQuantity: (value: string) => void;
  orderType: 'market' | 'limit' | 'stop';
  setOrderType: (value: 'market' | 'limit' | 'stop') => void;
  price: string;
  setPrice: (value: string) => void;
  stopPrice: string;
  setStopPrice: (value: string) => void;
  useComplianceCheck: boolean;
  setUseComplianceCheck: (value: boolean) => void;
  urgentExecution: boolean;
  setUrgentExecution: (value: boolean) => void;
  placePending: boolean;
  routeExecutionPending: boolean;
  compliancePending: boolean;
  directionLabel: string;
  orderTypeLabel: string;
  trimmedCode: string;
  quantityValue: number;
  accountId: string;
  previewUnitPrice: number | null;
  estimatedAmount: number | null;
  riskHints: string[];
  formError: string | null;
  formStatus: string | null;
  lastActionResult: string | null;
  onLoadExampleOrder: (code?: string) => void;
};

export default function PaperTradingOrderWorkspace({
  showAccountBootstrap,
  handleOrder,
  code,
  setCode,
  codeError,
  direction,
  setDirection,
  quantity,
  setQuantity,
  orderType,
  setOrderType,
  price,
  setPrice,
  stopPrice,
  setStopPrice,
  useComplianceCheck,
  setUseComplianceCheck,
  urgentExecution,
  setUrgentExecution,
  placePending,
  routeExecutionPending,
  compliancePending,
  directionLabel,
  orderTypeLabel,
  trimmedCode,
  quantityValue,
  accountId,
  previewUnitPrice,
  estimatedAmount,
  riskHints,
  formError,
  formStatus,
  lastActionResult,
  onLoadExampleOrder,
}: PaperTradingOrderWorkspaceProps) {
  return (
    <SectionCard className="mb-4 p-4 sm:p-5">
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] 2xl:items-start">
        <div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Order Workspace</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">委托输入与提交流程</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                把参数输入、风控开关和示例引导放在同一块 glass 表单里，提交前就能确认方向、账户、价格和执行路径。
              </p>
            </div>
            {showAccountBootstrap ? (
              <div className="panel-soft rounded-[20px] px-3 py-2 text-xs text-text-secondary">
                首笔交易建议使用示例代码和 100 股市价单
              </div>
            ) : null}
          </div>

          <form onSubmit={handleOrder} className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StockCodeInput id="paper-order-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>交易方向</span>
              <select
                id="paper-order-direction"
                value={direction}
                onChange={(event) => setDirection(event.target.value as 'buy' | 'sell')}
                className="text-sm"
              >
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>数量</span>
              <input
                id="paper-order-quantity"
                type="number"
                min={1}
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                placeholder="数量"
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>订单类型</span>
              <select
                id="paper-order-type"
                value={orderType}
                onChange={(event) => setOrderType(event.target.value as 'market' | 'limit' | 'stop')}
                className="text-sm"
              >
                <option value="market">市价单</option>
                <option value="limit">限价单</option>
                <option value="stop">止损单</option>
              </select>
            </label>

            {orderType === 'limit' || orderType === 'market' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>价格</span>
                <input
                  id="paper-order-price"
                  type="number"
                  step="0.01"
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                  placeholder={orderType === 'market' ? '价格（可选）' : '输入限价'}
                  className="text-sm"
                />
              </label>
            ) : null}
            {orderType === 'stop' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>止损价</span>
                <input
                  id="paper-order-stop-price"
                  type="number"
                  step="0.01"
                  value={stopPrice}
                  onChange={(event) => setStopPrice(event.target.value)}
                  placeholder="输入止损价"
                  className="text-sm"
                />
              </label>
            ) : null}

            <div className="sm:col-span-2 xl:col-span-4 grid gap-3 md:grid-cols-2">
              <label
                htmlFor="paper-order-compliance-check"
                className="panel-soft flex cursor-pointer items-start gap-3 rounded-[22px] p-3 text-sm text-text-secondary"
              >
                <input
                  id="paper-order-compliance-check"
                  type="checkbox"
                  checked={useComplianceCheck}
                  onChange={(event) => setUseComplianceCheck(event.target.checked)}
                  className="mt-0.5 rounded border-border accent-primary"
                />
                <span>
                  下单前执行合规风控。
                  <span className="mt-1 block text-xs text-text-muted">
                    先检查规则再决定是否继续提交，更适合有账户约束的模拟流程。
                  </span>
                </span>
              </label>
              <label
                htmlFor="paper-order-urgent-execution"
                className="panel-soft flex cursor-pointer items-start gap-3 rounded-[22px] p-3 text-sm text-text-secondary"
              >
                <input
                  id="paper-order-urgent-execution"
                  type="checkbox"
                  checked={urgentExecution}
                  onChange={(event) => setUrgentExecution(event.target.checked)}
                  className="mt-0.5 rounded border-border accent-primary"
                />
                <span>
                  启用极速智能路由。
                  <span className="mt-1 block text-xs text-text-muted">
                    由 Execution Manager 优先决定提交路径，更适合需要更快模拟反馈的场景。
                  </span>
                </span>
              </label>
            </div>

            <div className="sm:col-span-2 xl:col-span-4 flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={placePending || routeExecutionPending || compliancePending}
                className={`inline-flex min-h-[42px] cursor-pointer items-center justify-center rounded-full px-5 py-2 text-sm font-medium text-white shadow-[0_18px_38px_-24px_rgba(15,23,42,0.4)] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 ${direction === 'buy' ? 'bg-danger' : 'bg-success'}`}
              >
                {placePending || routeExecutionPending
                  ? '提交中...'
                  : compliancePending
                    ? '风控检查中...'
                    : direction === 'buy'
                      ? '确认买入'
                      : '确认卖出'}
              </button>
              <button type="button" onClick={() => onLoadExampleOrder('600519')} className={paperTradingChipButtonCls}>
                载入茅台示例
              </button>
              <button type="button" onClick={() => onLoadExampleOrder('000001')} className={paperTradingChipButtonCls}>
                载入平安银行示例
              </button>
            </div>
          </form>
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-text-primary">订单预览</div>
              <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
                在确认弹窗前先核对方向、数量、价格、账户与执行路径，移动端也能直接抓到关键信息。
              </p>
            </div>
            <Badge variant={direction === 'buy' ? 'danger' : 'success'}>{directionLabel}</Badge>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">标的 / 类型</div>
              <div className="metric-value mt-3 text-[1.45rem]">{trimmedCode || '待填写代码'}</div>
              <div className="mt-1 text-xs text-text-secondary">{orderTypeLabel}</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">数量 / 账户</div>
              <div className="metric-value mt-3 text-[1.45rem]">
                {Number.isFinite(quantityValue) && quantityValue > 0 ? `${quantityValue} 股` : '待填写数量'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">{accountId || '默认账户'}</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">预览价格</div>
              <div className="metric-value mt-3 text-[1.45rem]">
                {previewUnitPrice != null && Number.isFinite(previewUnitPrice) && previewUnitPrice > 0
                  ? fmtNum(previewUnitPrice, 2)
                  : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {orderType === 'market' ? '市价单可不填写价格' : '需要有效价格才能形成完整预览'}
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">预估金额</div>
              <div className="metric-value mt-3 text-[1.45rem]">{estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {urgentExecution ? '当前会优先走极速智能路由' : '当前按标准模拟提交流程处理'}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-[22px] border border-white/45 bg-white/36 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.52)]">
            <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">提交前提醒</div>
            <div className="mt-3 space-y-2">
              {riskHints.map((hint) => (
                <div key={hint} className="text-xs leading-6 text-text-secondary">
                  {hint}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {formError ? (
        <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs font-medium text-danger" role="alert">
          {formError}
        </div>
      ) : null}
      {formStatus ? (
        <div className="panel-soft mt-3 rounded-[20px] px-4 py-3 text-xs text-primary" role="status">
          {formStatus}
        </div>
      ) : null}
      {lastActionResult ? (
        <div className="panel-soft mt-3 rounded-[20px] px-4 py-3 text-xs text-success">{lastActionResult}</div>
      ) : null}
    </SectionCard>
  );
}
