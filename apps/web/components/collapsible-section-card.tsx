'use client';

import { ReactNode } from 'react';
import { Badge } from '@/components/ui';

type CollapsibleSectionCardProps = {
  eyebrow?: string;
  title: string;
  summary?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
};

export default function CollapsibleSectionCard({
  eyebrow,
  title,
  summary,
  badge,
  actions,
  defaultOpen = false,
  className = '',
  children,
}: CollapsibleSectionCardProps) {
  return (
    <details className={`panel-soft rounded-[28px] p-4 sm:p-5 ${className}`} open={defaultOpen}>
      <summary className="flex cursor-pointer list-none flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h2 className="mb-0 text-xl font-semibold text-text-primary">{title}</h2>
            {badge}
          </div>
          {summary ? <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{summary}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          <Badge variant="neutral">{defaultOpen ? '默认展开' : '按需展开'}</Badge>
        </div>
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}
