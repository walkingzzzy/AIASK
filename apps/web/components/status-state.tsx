'use client';

import { ReactNode } from 'react';

export function LoadingState({ text = '加载中...' }: { text?: string }) {
  return <p className="text-text-secondary">{text}</p>;
}

export function ErrorState({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="text-error">
      <p className="m-0">降级提示：{text}</p>
      {hint ? <p className="mt-1 mb-0 text-warning">{hint}</p> : null}
    </div>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <p className="text-text-secondary">{text}</p>;
}

export function MetaLine({ children }: { children: ReactNode }) {
  return <div className="mt-2 text-text-secondary text-sm">{children}</div>;
}
