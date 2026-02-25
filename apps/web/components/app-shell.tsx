'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode, useEffect, useMemo, useState } from 'react';
import { useAuthStore } from '@/store/auth-store';
import { useStockContext } from '@/store/stock-context';
import { BFF_BASE } from '@/lib/api';
import { useMobile } from '@/hooks/use-mobile';
import { useTheme } from '@/hooks/use-theme';

/* ── 分组导航定义 ── */
type NavItem = { href: string; label: string };
type NavGroup = { label: string; icon: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: '行情',
    icon: '📈',
    items: [
      { href: '/', label: '首页' },
      { href: '/market', label: '行情看板' },
      { href: '/stock', label: '个股详情' },
    ],
  },
  {
    label: '分析',
    icon: '🔍',
    items: [
      { href: '/fundamental', label: '基本面' },
      { href: '/technical', label: '技术分析' },
      { href: '/fund-flow', label: '资金流向' },
      { href: '/sentiment', label: '情绪分析' },
      { href: '/research', label: '研报公告' },
      { href: '/valuation', label: '估值分析' },
    ],
  },
  {
    label: '策略',
    icon: '🧪',
    items: [
      { href: '/strategy-market', label: '策略超市' },
      { href: '/backtest', label: '回测分析' },
      { href: '/factor', label: '因子研究' },
      { href: '/factor-analysis', label: '因子分析' },
    ],
  },
  {
    label: '交易',
    icon: '💹',
    items: [
      { href: '/paper-trading', label: '模拟交易' },
      { href: '/portfolio', label: '组合管理' },
      { href: '/risk', label: '风控中心' },
      { href: '/alerts', label: '告警管理' },
    ],
  },
  {
    label: '工具',
    icon: '🛠',
    items: [
      { href: '/assistant', label: '智能助手' },
      { href: '/chat', label: 'AI 对话' },
      { href: '/tdx', label: 'TDX联动' },
      { href: '/search', label: '智能搜索' },
      { href: '/data', label: '数据中心' },
    ],
  },
];

/** 需要携带股票代码的页面路径 */
const STOCK_AWARE_PATHS = new Set([
  '/stock', '/market', '/fundamental', '/technical', '/fund-flow',
  '/sentiment', '/research', '/valuation', '/backtest', '/factor-analysis',
  '/paper-trading', '/alerts', '/assistant', '/tdx', '/search', '/data',
]);

function buildHref(basePath: string, stockCode: string): string {
  if (!stockCode || !STOCK_AWARE_PATHS.has(basePath)) return basePath;
  return `${basePath}?code=${encodeURIComponent(stockCode)}`;
}

/* ── 判断某个分组是否包含当前路径 ── */
function groupContainsPath(group: NavGroup, path: string) {
  return group.items.some((item) =>
    item.href === '/' ? path === '/' : path.startsWith(item.href),
  );
}

/* ── 可折叠导航分组 ── */
function NavSection({
  group,
  pathname,
  openKey,
  onToggle,
  onNavigate,
  stockCode,
}: {
  group: NavGroup;
  pathname: string;
  openKey: string | null;
  onToggle: (label: string) => void;
  onNavigate: () => void;
  stockCode: string;
}) {
  const isActive = groupContainsPath(group, pathname);
  const isOpen = openKey === group.label || isActive;

  return (
    <div className="mb-0.5">
      <button
        onClick={() => onToggle(group.label)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold uppercase tracking-wider cursor-pointer rounded-md mx-1 transition-colors ${
          isActive
            ? 'text-nav-active bg-nav-active-bg/30'
            : 'text-text-secondary hover:text-nav-text hover:bg-white/5'
        }`}
      >
        <span className="text-sm">{group.icon}</span>
        <span className="flex-1 text-left">{group.label}</span>
        <span className={`text-[10px] transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
      </button>
      {isOpen ? (
        <div className="ml-2 mt-0.5">
          {group.items.map((item) => {
            const active = item.href === '/'
              ? pathname === '/'
              : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={buildHref(item.href, stockCode)}
                onClick={onNavigate}
                className={`block px-4 py-1.5 no-underline text-sm rounded-md mx-1 transition-all ${
                  active
                    ? 'text-nav-active bg-nav-active-bg/60 font-semibold'
                    : 'text-nav-text font-normal hover:bg-white/10'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

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
  const storeCode = useStockContext((s) => s.code);
  const isMobile = useMobile();
  const [mounted, setMounted] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  useEffect(() => {
    if (user) return;
    fetch(`${BFF_BASE}/auth/me`, { credentials: 'include', cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.authenticated && d.user) setUser(d.user);
      })
      .catch(() => {});
  }, [user, setUser]);

  useEffect(() => { setMounted(true); }, []);

  // 仅在客户端挂载后使用 store 中的股票代码，避免 SSR/CSR hydration 不匹配
  const currentStockCode = mounted ? storeCode : '';

  if (pathname === '/login' || pathname === '/register') return <>{children}</>;

  const handleToggle = (label: string) => {
    setOpenGroup((prev) => (prev === label ? null : label));
  };

  const handleNavigate = () => setDrawerOpen(false);

  const navContent = (
    <>
      <div className="px-4 pb-3 font-bold text-base flex items-center justify-between">
        <Link href="/" className="no-underline">
          <span className="bg-gradient-to-r from-primary to-purple-500 bg-clip-text text-transparent font-bold">
            AIASK
          </span>
        </Link>
        {isMobile ? (
          <button onClick={() => setDrawerOpen(false)} className="text-lg cursor-pointer">✕</button>
        ) : null}
      </div>
      <div className="flex flex-col gap-0.5">
        {NAV_GROUPS.map((group) => (
          <NavSection
            key={group.label}
            group={group}
            pathname={pathname}
            openKey={openGroup}
            onToggle={handleToggle}
            onNavigate={handleNavigate}
            stockCode={currentStockCode}
          />
        ))}
      </div>
      {/* 用户中心固定在底部 */}
      <div className="mt-auto pt-3 border-t border-glass-border mx-2">
        <Link
          href="/user"
          onClick={handleNavigate}
          className={`block px-4 py-2 no-underline text-sm rounded-md mx-1 transition-all ${
            pathname === '/user'
              ? 'text-nav-active bg-nav-active-bg/60 font-semibold'
              : 'text-nav-text font-normal hover:bg-white/10'
          }`}
        >
          👤 用户中心
        </Link>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen">
      {isMobile ? (
        <>
          {drawerOpen ? (
            <div className="fixed inset-0 z-50 flex">
              <div className="fixed inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
              <nav className="relative w-[220px] glass-strong py-4 overflow-y-auto z-10 border-r border-glass-border flex flex-col">
                {navContent}
              </nav>
            </div>
          ) : null}
        </>
      ) : (
        <nav className="w-[200px] glass-strong py-4 shrink-0 overflow-y-auto border-r border-glass-border flex flex-col">
          {navContent}
        </nav>
      )}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-12 glass flex items-center justify-between px-4 gap-3 shrink-0 sticky top-0 z-10">
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
