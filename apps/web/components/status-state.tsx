'use client';

import { ReactNode } from 'react';

export function LoadingState({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 py-4 text-text-secondary">
      <div className="relative w-5 h-5">
        <div className="absolute inset-0 rounded-full border-2 border-primary/30" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-primary animate-[spin_0.8s_linear_infinite]" />
      </div>
      <span className="text-sm">{text}</span>
    </div>
  );
}

export function ErrorState({ text, hint, onRetry }: { text: string; hint?: string; onRetry?: () => void }) {
  return (
    <div className="mt-2 rounded-[18px] border border-danger/20 bg-danger/8 p-4" role="alert">
      <p className="m-0 text-sm font-medium text-error">{text}</p>
      {hint ? <p className="mb-0 mt-1 text-xs text-text-secondary">{hint}</p> : null}
      {onRetry ? (
        <button onClick={onRetry} className="mt-3 rounded-full border border-danger/20 px-3 py-1 text-xs text-error">重试</button>
      ) : null}
    </div>
  );
}

/**
 * 紧凑空状态组件
 * - compact（默认）：小图标 + 一行提示 + CTA，高度约 80px
 * - full：居中图标 + 标题 + 说明，适合整页空状态
 */
export function EmptyState({
  icon,
  text,
  hint,
  action,
  variant = 'compact',
  className = '',
}: {
  icon?: ReactNode;
  text: string;
  hint?: string;
  action?: ReactNode;
  variant?: 'compact' | 'full';
  className?: string;
}) {
  if (variant === 'compact') {
    return (
      <div className={`flex items-center gap-3 rounded-md border border-dashed border-border bg-surface-alt/60 px-4 py-3 ${className}`}>
        {icon ? (
          <span className="shrink-0 text-text-muted">{icon}</span>
        ) : (
          <span className="shrink-0 text-text-muted opacity-50">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            </svg>
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="m-0 text-sm text-text-secondary">{text}</p>
          {hint ? <p className="m-0 mt-0.5 text-xs text-text-muted">{hint}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
    );
  }

  return (
    <div className={`flex flex-col items-center justify-center rounded-[18px] border border-dashed border-border bg-surface-alt/60 px-4 py-10 text-center ${className}`}>
      {icon ? (
        <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-surface text-text-muted shadow-sm">
          {icon}
        </span>
      ) : (
        <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-surface text-text-muted shadow-sm">
          <svg className="h-5 w-5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
        </span>
      )}
      <p className="m-0 text-sm font-medium text-text-primary">{text}</p>
      {hint ? <p className="mt-1 max-w-sm text-xs leading-5 text-text-muted">{hint}</p> : null}
      {action ? <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function MetaLine({ children }: { children: ReactNode }) {
  return <div className="mt-2 text-text-secondary text-sm">{children}</div>;
}
