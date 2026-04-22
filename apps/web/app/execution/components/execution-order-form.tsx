import type { FormEventHandler } from 'react';
import { StockCodeInput, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import {
  executionNoteCardCls,
  executionPrimaryButtonCls,
  executionSidePanelCls,
} from '@/app/execution/components/execution-panel-styles';

type ExecutionOrderFormProps = {
  code: string;
  codeError: string | null;
  onCodeChange: (value: string) => void;
  direction: 'buy' | 'sell';
  onDirectionChange: (value: 'buy' | 'sell') => void;
  quantity: string;
  onQuantityChange: (value: string) => void;
  urgency: 'normal' | 'high';
  onUrgencyChange: (value: 'normal' | 'high') => void;
  orderType: 'market' | 'limit' | 'stop';
  onOrderTypeChange: (value: 'market' | 'limit' | 'stop') => void;
  price: string;
  onPriceChange: (value: string) => void;
  stopPrice: string;
  onStopPriceChange: (value: string) => void;
  accountId: string;
  onAccountIdChange: (value: string) => void;
  accounts: Array<{ account_id?: string }>;
  artifactIdInput: string;
  onArtifactIdChange: (value: string) => void;
  estimatedAmount: number | null;
  formError: string | null;
  routeExecutionError: string | null;
  routeExecutionPending: boolean;
  onSubmit: FormEventHandler<HTMLFormElement>;
};

export default function ExecutionOrderForm({
  code,
  codeError,
  onCodeChange,
  direction,
  onDirectionChange,
  quantity,
  onQuantityChange,
  urgency,
  onUrgencyChange,
  orderType,
  onOrderTypeChange,
  price,
  onPriceChange,
  stopPrice,
  onStopPriceChange,
  accountId,
  onAccountIdChange,
  accounts,
  artifactIdInput,
  onArtifactIdChange,
  estimatedAmount,
  formError,
  routeExecutionError,
  routeExecutionPending,
  onSubmit,
}: ExecutionOrderFormProps) {
  return (
    <SectionCard className="mb-4">
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div>
          <h3 className="m-0 font-medium">智能执行参数</h3>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            这里把模拟执行的输入参数、账户上下文和 artifact 关联一起整理成更松弛的表单栅格，减少旧式后台感。
          </p>
          <form onSubmit={onSubmit} className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StockCodeInput id="execution-code" label="股票代码" value={code} onChange={onCodeChange} error={codeError} />
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>方向</span>
              <select
                value={direction}
                onChange={(event) => onDirectionChange(event.target.value as 'buy' | 'sell')}
                className="text-sm"
              >
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>数量</span>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(event) => onQuantityChange(event.target.value)}
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>执行模式</span>
              <select
                value={urgency}
                onChange={(event) => onUrgencyChange(event.target.value as 'normal' | 'high')}
                className="text-sm"
              >
                <option value="normal">标准 TWAP</option>
                <option value="high">高优先级 VWAP</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>订单类型</span>
              <select
                value={orderType}
                onChange={(event) => onOrderTypeChange(event.target.value as 'market' | 'limit' | 'stop')}
                className="text-sm"
              >
                <option value="market">市价单</option>
                <option value="limit">限价单</option>
                <option value="stop">止损单</option>
              </select>
            </label>
            {orderType === 'market' || orderType === 'limit' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>价格</span>
                <input
                  type="number"
                  step="0.01"
                  value={price}
                  onChange={(event) => onPriceChange(event.target.value)}
                  className="text-sm"
                />
              </label>
            ) : null}
            {orderType === 'stop' ? (
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>止损价</span>
                <input
                  type="number"
                  step="0.01"
                  value={stopPrice}
                  onChange={(event) => onStopPriceChange(event.target.value)}
                  className="text-sm"
                />
              </label>
            ) : null}
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>账户</span>
              <select
                value={accountId}
                onChange={(event) => onAccountIdChange(event.target.value)}
                className="text-sm"
              >
                <option value="">默认账户</option>
                {accounts.map((account, index) => (
                  <option key={account.account_id ?? index} value={account.account_id ?? ''}>
                    {account.account_id ?? `账户 ${index + 1}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>artifact_id</span>
              <input
                value={artifactIdInput}
                onChange={(event) => onArtifactIdChange(event.target.value)}
                placeholder="可选，用于任务编排追踪"
                className="text-sm"
              />
            </label>
            <div className="col-span-2 flex items-end gap-2 sm:col-span-4">
              <button type="submit" disabled={routeExecutionPending} className={executionPrimaryButtonCls}>
                {routeExecutionPending ? '执行中...' : '提交执行'}
              </button>
            </div>
          </form>
          {formError ? <p className="mt-2 text-xs font-medium text-danger">{formError}</p> : null}
          {routeExecutionError ? <p className="mt-2 text-xs font-medium text-danger">{routeExecutionError}</p> : null}
        </div>

        <div className={executionSidePanelCls}>
          <div className="text-sm font-medium text-text-primary">提交前提醒</div>
          <div className="mt-4 space-y-3">
            <div className={executionNoteCardCls}>
              执行中心会同时调用智能路由和模拟盘下单，所以它属于真实的交易模拟动作，不建议让 AI 自动提交。
            </div>
            <div className={executionNoteCardCls}>高优先级模式会优先走 `VWAP`，标准模式走 `TWAP`。</div>
            <div className={executionNoteCardCls}>执行结果中的 `execution_id` 可继续用于查询状态。</div>
            <div className={executionNoteCardCls}>
              预估金额：{estimatedAmount != null ? fmtNum(estimatedAmount) : '待输入价格后计算'}。
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
