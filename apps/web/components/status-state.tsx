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
    <div className="mt-2 rounded-[22px] border border-danger/20 bg-[linear-gradient(180deg,rgba(217,45,32,0.12),rgba(255,255,255,0.52))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-xl" role="alert">
      <p className="m-0 text-sm font-medium text-error">{text}</p>
      {hint ? <p className="mb-0 mt-1 text-xs text-text-secondary">{hint}</p> : null}
      {onRetry ? (
        <button onClick={onRetry} className="mt-3 rounded-full border border-danger/20 px-3 py-1 text-xs text-error">重试</button>
      ) : null}
    </div>
  );
}

export function UnavailableState({
  text = '当前页面所需服务暂不可用',
  hint,
  onRetry,
}: {
  text?: string;
  hint?: string;
  onRetry?: () => void;
}) {
  return <ErrorState text={text} hint={hint ?? '请稍后重试，或先检查 BFF / MCP / 上游服务状态。'} onRetry={onRetry} />;
}

export function PrerequisiteState({
  text,
  hint,
  action,
}: {
  text: string;
  hint?: string;
  action?: ReactNode;
}) {
  return <EmptyState text={text} hint={hint} action={action} variant="full" />;
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
      <div className={`flex items-center gap-3 rounded-[16px] border border-dashed border-border/70 bg-[linear-gradient(145deg,rgba(255,255,255,0.42),rgba(240,248,255,0.26))] px-4 py-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.64)] backdrop-blur-sm ${className}`}>
        {icon ? (
          <span className="shrink-0 text-text-muted">{icon}</span>
        ) : (
          <span className="shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-xl bg-[rgba(11,107,203,0.08)] text-primary/60">
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    <div className={`flex flex-col items-center justify-center rounded-[22px] border border-dashed border-border/70 bg-[linear-gradient(145deg,rgba(255,255,255,0.42),rgba(240,248,255,0.26))] px-6 py-12 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.64)] backdrop-blur-sm ${className}`}>
      {icon ? (
        <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,rgba(11,107,203,0.12),rgba(56,214,255,0.08))] text-primary shadow-[0_8px_20px_-10px_rgba(11,107,203,0.24)]">
          {icon}
        </span>
      ) : (
        <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,rgba(11,107,203,0.10),rgba(56,214,255,0.06))] text-primary/60 shadow-[0_8px_20px_-10px_rgba(11,107,203,0.16)]">
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
        </span>
      )}
      <p className="m-0 text-sm font-semibold text-text-primary">{text}</p>
      {hint ? <p className="mt-1.5 max-w-xs text-xs leading-5 text-text-muted">{hint}</p> : null}
      {action ? <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function MetaLine({ children }: { children: ReactNode }) {
  return <div className="mt-2 text-text-secondary text-sm">{children}</div>;
}
