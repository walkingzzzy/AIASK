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
      className={`glass glass-hover rounded-xl p-4 no-underline text-inherit block transition-transform hover:scale-[1.02] ${className}`}
      aria-label={title}
    >
      <div className="text-2xl mb-2">{icon}</div>
      <div className="font-semibold text-sm">{title}</div>
      {description ? (
        <div className="text-xs text-text-secondary mt-1">{description}</div>
      ) : null}
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
        : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5';
  return <div className={`grid gap-3 ${colClass} ${className}`}>{children}</div>;
}
