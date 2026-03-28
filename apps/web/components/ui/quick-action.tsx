'use client';

import Link from 'next/link';

export function QuickAction({
  href,
  icon,
  title,
  description,
  className = '',
}: {
  href: string;
  icon: string;
  title: string;
  description?: string;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={`surface-card block rounded-[20px] p-4 no-underline text-inherit transition hover:border-primary/20 hover:shadow-md ${className}`}
      aria-label={title}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-xl text-primary">
          {icon}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">任务入口</span>
      </div>
      <div className="text-sm font-semibold text-text-primary">{title}</div>
      {description ? <div className="mt-1 text-xs leading-5 text-text-secondary">{description}</div> : null}
    </Link>
  );
}

export function QuickActionGrid({
  children,
  cols = 5,
  className = '',
}: {
  children: React.ReactNode;
  cols?: 3 | 4 | 5;
  className?: string;
}) {
  const colClass =
    cols === 3
      ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
      : cols === 4
        ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4'
        : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-5';
  return <div className={`grid gap-3 ${colClass} ${className}`}>{children}</div>;
}
