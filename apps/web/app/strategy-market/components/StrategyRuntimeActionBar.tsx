'use client';

import type {
  StrategyRuntimeActionContract,
  StrategyRuntimeActionContractItem,
  StrategyRuntimeActionId,
} from '../types';

type StrategyRuntimeActionBarProps = {
  contract?: StrategyRuntimeActionContract | null;
  pendingActionId?: StrategyRuntimeActionId | null;
  onAction: (action: StrategyRuntimeActionContractItem) => void | Promise<void>;
  compact?: boolean;
  className?: string;
};

function statusText(action: StrategyRuntimeActionContractItem) {
  if (action.status === 'confirm_required') return '需确认';
  if (action.status === 'unavailable') return '不可用';
  return '可点击';
}

function actionButtonClass(action: StrategyRuntimeActionContractItem, compact: boolean) {
  const base = compact
    ? 'rounded-full px-2.5 py-1.5 text-[11px]'
    : 'rounded-full px-3.5 py-2 text-sm';
  if (action.status === 'unavailable') {
    return `${base} cursor-not-allowed border border-border bg-surface-alt text-text-muted opacity-75`;
  }
  if (action.status === 'confirm_required') {
    return `${base} border border-primary/35 bg-primary/10 text-primary hover:bg-primary/15`;
  }
  return `${base} border border-border bg-surface text-text-primary hover:border-primary/45 hover:text-primary`;
}

export function StrategyRuntimeActionBar({
  contract,
  pendingActionId,
  onAction,
  compact = false,
  className = '',
}: StrategyRuntimeActionBarProps) {
  const actionLookup = new Map((contract?.actions ?? []).map((action) => [action.id, action]));
  const orderedActions = (contract?.default_order ?? [])
    .map((id) => actionLookup.get(id))
    .filter((action): action is StrategyRuntimeActionContractItem => Boolean(action));
  const actions = orderedActions.length ? orderedActions : (contract?.actions ?? []);
  const blocked = actions.filter((action) => action.status === 'unavailable' && action.unavailable_reason);

  if (!contract) {
    return (
      <div className={`rounded-[18px] border border-border bg-surface-alt/60 px-3 py-2 text-xs text-text-secondary ${className}`}>
        动作合同未返回，行动栏暂不渲染本地推断按钮。
      </div>
    );
  }

  return (
    <div className={className} data-testid="strategy-runtime-action-contract">
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => {
          const pending = pendingActionId === action.id;
          const disabled = action.status === 'unavailable' || pending;
          const reason = action.unavailable_reason ?? '';
          return (
            <button
              key={action.id}
              type="button"
              disabled={disabled}
              title={reason || action.description || action.label}
              aria-label={`${action.label}，${statusText(action)}${reason ? `，${reason}` : ''}`}
              onClick={() => {
                if (disabled) return;
                void onAction(action);
              }}
              className={actionButtonClass(action, compact)}
            >
              <span>{pending ? '正在执行...' : compact ? (action.short_label ?? action.label) : action.label}</span>
              {!compact ? <span className="ml-1 text-[11px] opacity-70">· {statusText(action)}</span> : null}
            </button>
          );
        })}
      </div>
      {blocked.length ? (
        <div className={`mt-2 ${compact ? 'text-[11px] leading-5' : 'text-xs leading-6'} text-text-secondary`}>
          {blocked.map((action) => (
            <div key={`${action.id}:reason`}>
              {action.short_label ?? action.label}：{action.unavailable_reason}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
