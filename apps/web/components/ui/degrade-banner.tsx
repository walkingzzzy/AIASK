'use client';

import { useState, type ReactNode } from 'react';

export type DegradeBannerProps = {
  /** 降级原因描述 */
  reason: string;
  /** 补充说明或操作建议 */
  detail?: string;
  /** 严重程度：warning（黄）/ error（红）/ info（蓝） */
  severity?: 'warning' | 'error' | 'info';
  /** 是否可以手动关闭 */
  dismissible?: boolean;
  /** 右侧操作区（如重试按钮） */
  action?: ReactNode;
  className?: string;
};

const SEVERITY_STYLES = {
  warning: {
    wrapper: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
    icon: '⚠',
  },
  error: {
    wrapper: 'bg-red-500/10 border-red-500/30 text-red-300',
    icon: '✕',
  },
  info: {
    wrapper: 'bg-blue-500/10 border-blue-500/30 text-blue-300',
    icon: 'ℹ',
  },
};

/**
 * DegradeBanner — 降级状态横幅
 *
 * 当数据服务降级、使用缓存或部分失败时展示。
 *
 * ```tsx
 * <DegradeBanner
 *   reason="行情数据来自缓存，可能不是最新"
 *   detail="实时行情服务暂不可用，已切换至 10 分钟延迟数据"
 *   severity="warning"
 *   action={<button onClick={refetch}>重试</button>}
 * />
 * ```
 */
export function DegradeBanner({
  reason,
  detail,
  severity = 'warning',
  dismissible = true,
  action,
  className = '',
}: DegradeBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const { wrapper, icon } = SEVERITY_STYLES[severity];

  return (
    <div
      role="alert"
      className={[
        'flex items-start gap-2 rounded-md border px-3 py-2 text-sm',
        wrapper,
        className,
      ].join(' ')}
    >
      <span className="shrink-0 text-base leading-5" aria-hidden="true">{icon}</span>
      <div className="min-w-0 flex-1">
        <span className="font-medium">{reason}</span>
        {detail ? <span className="ml-1 opacity-75 text-xs">{detail}</span> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
      {dismissible ? (
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 opacity-60 hover:opacity-100 transition-opacity text-xs px-1"
          aria-label="关闭提示"
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}
