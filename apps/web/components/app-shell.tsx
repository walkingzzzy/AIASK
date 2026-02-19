'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode, useEffect, useState } from 'react';
import { useAuthStore } from '@/store/auth-store';
import { readCookie } from '@/lib/auth';
import { BFF_BASE } from '@/lib/api';
import { useMobile } from '@/hooks/use-mobile';
import { useTheme } from '@/hooks/use-theme';

const NAV = [
  { href: '/', label: '首页' },
  { href: '/market', label: '行情' },
  { href: '/fundamental', label: '基本面' },
  { href: '/research', label: '研报' },
  { href: '/fund-flow', label: '资金流' },
  { href: '/alerts', label: '告警' },
  { href: '/strategy', label: '策略' },
  { href: '/factor', label: '因子' },
  { href: '/risk', label: '风控' },
  { href: '/assistant', label: '智能助手' },
  { href: '/chat', label: 'AI 对话' },
  { href: '/tdx', label: 'TDX联动' },
  { href: '/valuation', label: '估值' },
  { href: '/technical', label: '技术' },
  { href: '/sentiment', label: '情绪' },
  { href: '/search', label: '搜索' },
  { href: '/data', label: '数据' },
  { href: '/user', label: '用户中心' },
];

/* PLACEHOLDER_REST */

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
  const label = theme === 'light' ? '☀' : theme === 'dark' ? '🌙' : '⚙';
  return (
    <button
      onClick={() => setTheme(next)}
      className="text-sm px-2 py-1 rounded border border-border cursor-pointer"
      title={`当前: ${theme}，点击切换`}
    >
      {label}
    </button>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, setUser, logout } = useAuthStore();
  const isMobile = useMobile();
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const token = readCookie('access_token');
    if (!token || user) return;
    fetch(`${BFF_BASE}/auth/me`, { headers: { authorization: `Bearer ${token}` }, cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.authenticated && d.user) setUser(d.user);
      })
      .catch(() => {});
  }, [user, setUser]);

  if (pathname === '/login') return <>{children}</>;

  const navContent = (
    <>
      <div className="px-4 pb-4 font-bold text-base flex items-center justify-between">
        <span>AIASK</span>
        {isMobile ? (
          <button onClick={() => setDrawerOpen(false)} className="text-lg cursor-pointer">✕</button>
        ) : null}
      </div>
      {NAV.map((n) => (
        <Link
          key={n.href}
          href={n.href}
          onClick={() => setDrawerOpen(false)}
          className={`block px-4 py-2 no-underline text-sm ${
            pathname === n.href
              ? 'text-nav-active bg-nav-active-bg font-semibold'
              : 'text-nav-text font-normal'
          }`}
        >
          {n.label}
        </Link>
      ))}
    </>
  );

  return (
    <div className="flex min-h-screen">
      {isMobile ? (
        <>
          {drawerOpen ? (
            <div className="fixed inset-0 z-50 flex">
              <div className="fixed inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
              <nav className="relative w-[220px] bg-sidebar border-r border-sidebar-border py-4 overflow-y-auto z-10">
                {navContent}
              </nav>
            </div>
          ) : null}
        </>
      ) : (
        <nav className="w-[180px] bg-sidebar border-r border-sidebar-border py-4 shrink-0 overflow-y-auto">
          {navContent}
        </nav>
      )}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-12 border-b border-sidebar-border flex items-center justify-between px-4 gap-3 shrink-0">
          <div className="flex items-center gap-2">
            {isMobile ? (
              <button onClick={() => setDrawerOpen(true)} className="text-lg cursor-pointer">☰</button>
            ) : null}
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {user ? <span className="text-text-secondary text-sm">{user.username}</span> : null}
            {user ? (
              <button
                onClick={() => { logout(); window.location.href = '/login'; }}
                className="cursor-pointer text-sm"
              >
                退出
              </button>
            ) : null}
          </div>
        </header>
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
