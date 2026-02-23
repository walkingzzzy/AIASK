'use client';

import Link from 'next/link';

/**
 * 可点击的股票代码组件 — 点击跳转到个股详情页
 */
export function StockLink({
  code,
  name,
  className,
}: {
  code: string | number;
  name?: string;
  className?: string;
}) {
  const c = String(code).trim();
  if (!c || c === '-') return <span className={className}>{c || '-'}</span>;

  return (
    <Link
      href={`/stock?code=${encodeURIComponent(c)}`}
      className={`text-primary hover:underline cursor-pointer no-underline ${className ?? ''}`}
      title={name ? `${name} (${c}) — 点击查看详情` : `${c} — 点击查看详情`}
    >
      {name ?? c}
    </Link>
  );
}
