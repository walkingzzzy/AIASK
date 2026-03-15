'use client';

import { ReactNode } from 'react';

export function LoadingState({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 py-4">
      <div className="relative w-5 h-5">
        <div className="absolute inset-0 rounded-full border-2 border-primary/30" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-primary animate-[spin_0.8s_linear_infinite]" />
      </div>
      <span className="text-text-secondary text-sm">{text}</span>
    </div>
  );
}

export function ErrorState({ text, hint, onRetry }: { text: string; hint?: string; onRetry?: () => void }) {
  return (
    <div className="glass rounded-xl p-3 mt-2 border-l-4 border-l-danger" role="alert">
      <p className="m-0 text-error text-sm">{text}</p>
      {hint ? <p className="mt-1 mb-0 text-warning text-xs">{hint}</p> : null}
      {onRetry ? (
        <button onClick={onRetry} className="mt-2 text-xs text-primary underline cursor-pointer">重试</button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  text,
  hint,
  action,
  className = '',
}: {
  text: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center justify-center py-8 text-text-secondary ${className}`}>
      <svg className="w-10 h-10 mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
      <p className="text-sm">{text}</p>
      {hint ? <p className="mt-1 max-w-xl text-center text-xs text-text-muted">{hint}</p> : null}
      {action ? <div className="mt-3 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function MetaLine({ children }: { children: ReactNode }) {
  return <div className="mt-2 text-text-secondary text-sm">{children}</div>;
}
