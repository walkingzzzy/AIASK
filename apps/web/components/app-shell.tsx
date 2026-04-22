'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import CopilotDock from '@/components/copilot-dock';
import { NotificationBell } from '@/components/notification-bell';
import { Onboarding, OnboardingProvider } from '@/components/onboarding';
import { useMobile } from '@/hooks/use-mobile';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { useHydrated } from '@/hooks/use-hydrated';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useBffAvailability } from '@/lib/bff-availability';
import { describeActionableElement, ensureBehaviorSessionId, flushBehaviorEvents, resolveBehaviorPageKey, trackBehaviorEvent } from '@/lib/behavior-tracker';
import { useTheme } from '@/hooks/use-theme';
import { hasLoggedInHint, probeAuthSession } from '@/lib/auth';
import { pageActionBus, type PageActionDefinition } from '@/lib/page-action-bus';
import { isPublicPathname } from '@/lib/public-routes';
import { useWsStatus, type WsConnectionStatus } from '@/lib/ws';
import { useAuthStore, type User } from '@/store/auth-store';
import { useCopilotStore } from '@/store/copilot-store';
import { useStockContext } from '@/store/stock-context';
import { resolveWorkspaceLayout, selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

type NavItem = { href: string; label: string };
type NavGroup = { label: string; icon: string; svgPath: string; items: NavItem[] };

const TOUR_ATTRS: Record<string, string> = {
  '/': 'dashboard',
  '/assistant': 'ai-center',
  '/watchlist': 'watchlist',
  '/paper-trading': 'paper-trading',
  '/settings': 'settings',
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: '看盘',
    icon: 'MK',
    svgPath: 'M3 3v18h18M9 17V9m4 8V5m4 12v-4',
    items: [
      { href: '/', label: '首页' },
      { href: '/market', label: '行情看板' },
      { href: '/watchlist', label: '自选股' },
    ],
  },
  {
    label: '研究',
    icon: 'RS',
    svgPath: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    items: [
      { href: '/research', label: '研报公告' },
      { href: '/fundamental', label: '基本面' },
      { href: '/technical', label: '技术分析' },
      { href: '/sentiment', label: '情绪分析' },
    ],
  },
  {
    label: '策略',
    icon: 'ST',
    svgPath: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
    items: [
      { href: '/strategy-market', label: '策略超市' },
      { href: '/backtest', label: '回测分析' },
      { href: '/factor-analysis', label: '因子分析' },
    ],
  },
  {
    label: '交易',
    icon: 'TR',
    svgPath: 'M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4',
    items: [
      { href: '/paper-trading', label: '模拟交易' },
      { href: '/portfolio', label: '组合管理' },
      { href: '/risk', label: '风控中心' },
    ],
  },
  {
    label: 'AI',
    icon: 'AI',
    svgPath: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
    items: [
      { href: '/assistant', label: 'AI 中心' },
      { href: '/search', label: '智能搜索' },
    ],
  },
];

const UTILITY_LINKS: NavItem[] = [
  { href: '/alerts', label: '告警管理' },
  { href: '/notifications', label: '通知中心' },
  { href: '/decision', label: '统一决策' },
  { href: '/workspace-templates', label: '工作区模板' },
];

const FALLBACK_PAGE_LABELS: Record<string, string> = {
  '/skills': '技能中心',
  '/events': '事件中心',
  '/execution': '执行中心',
  '/performance': '绩效分析',
  '/screener': '条件选股',
};

const STOCK_AWARE_PATHS = new Set([
  '/stock',
  '/market',
  '/watchlist',
  '/fundamental',
  '/technical',
  '/fund-flow',
  '/sentiment',
  '/research',
  '/valuation',
  '/backtest',
  '/factor-analysis',
  '/paper-trading',
  '/alerts',
  '/assistant',
  '/search',
  '/data',
  '/events',
  '/execution',
  '/performance',
  '/decision',
]);

const WS_STATUS_MAP: Record<WsConnectionStatus, { color: string; label: string }> = {
  connected: { color: '#22c55e', label: '已连接' },
  connecting: { color: '#eab308', label: '重连中' },
  disconnected: { color: '#ef4444', label: '断开' },
};

function buildHref(basePath: string, stockCode: string) {
  if (!stockCode || !STOCK_AWARE_PATHS.has(basePath)) return basePath;
  return `${basePath}?code=${encodeURIComponent(stockCode)}`;
}

function getTourAttr(href: string) {
  return TOUR_ATTRS[href];
}

function groupContainsPath(group: NavGroup, path: string) {
  return group.items.some((item) => (item.href === '/' ? path === '/' : path.startsWith(item.href)));
}

function findNavLabel(path: string) {
  if (/^\/strategy-market\/[^/]+/.test(path)) {
    return '策略详情';
  }
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      if (item.href === '/' ? path === '/' : path.startsWith(item.href)) {
        return item.label;
      }
    }
  }
  for (const item of UTILITY_LINKS) {
    if (path.startsWith(item.href)) return item.label;
  }
  for (const [href, label] of Object.entries(FALLBACK_PAGE_LABELS)) {
    if (path.startsWith(href)) return label;
  }
  return path === '/' ? '首页总览' : path;
}

function resolveShellTheme(path: string) {
  if (
    path === '/' ||
    path.startsWith('/market') ||
    path.startsWith('/stock') ||
    path.startsWith('/watchlist') ||
    path.startsWith('/fund-flow') ||
    path.startsWith('/technical') ||
    path.startsWith('/sentiment') ||
    path.startsWith('/macro') ||
    path.startsWith('/options')
  ) {
    return 'market';
  }

  if (
    path.startsWith('/research') ||
    path.startsWith('/fundamental') ||
    path.startsWith('/valuation') ||
    path.startsWith('/search') ||
    path.startsWith('/assistant') ||
    path.startsWith('/chat') ||
    path.startsWith('/skills') ||
    path.startsWith('/workspace-templates')
  ) {
    return 'research';
  }

  if (path.startsWith('/strategy') || path.startsWith('/factor') || path.startsWith('/backtest')) {
    return 'strategy';
  }

  if (
    path.startsWith('/paper-trading') ||
    path.startsWith('/portfolio') ||
    path.startsWith('/risk') ||
    path.startsWith('/alerts') ||
    path.startsWith('/notifications') ||
    path.startsWith('/decision') ||
    path.startsWith('/execution') ||
    path.startsWith('/performance')
  ) {
    return 'trade';
  }

  return 'default';
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
  const label = theme === 'light' ? '☀' : theme === 'dark' ? '🌙' : '⚙';
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="rounded-full border border-glass-border bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(246,250,255,0.4))] px-2.5 py-1 text-sm shadow-[0_12px_26px_-20px_rgba(15,23,42,0.28)] backdrop-blur-xl"
      title={`当前: ${theme}，点击切换`}
    >
      {label}
    </button>
  );
}

function WsIndicator() {
  const status = useWsStatus();
  const hydrated = useHydrated();
  const { color, label } = hydrated ? WS_STATUS_MAP[status] : WS_STATUS_MAP.connecting;

  return (
    <span
      className="flex items-center gap-1 rounded-full border border-glass-border bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(246,250,255,0.4))] px-2.5 py-1 text-xs text-text-secondary backdrop-blur-xl"
      title={`WebSocket: ${label}`}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block' }} />
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}

function NavSection({
  group,
  pathname,
  stockCode,
  onNavigate,
}: {
  group: NavGroup;
  pathname: string;
  stockCode: string;
  onNavigate?: () => void;
}) {
  const isActive = groupContainsPath(group, pathname);

  return (
    <div className="mb-5">
      <div
        className={`mb-2 flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${isActive ? 'text-nav-active' : 'text-text-muted'}`}
      >
        <span
          aria-hidden="true"
          className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full border px-1.5 transition-colors ${isActive ? 'border-primary/20 bg-[rgba(11,107,203,0.10)]' : 'border-border bg-surface-alt'}`}
        >
          <svg
            className={`h-3.5 w-3.5 ${isActive ? 'text-nav-active' : 'text-text-muted'}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            viewBox="0 0 24 24"
          >
            <path d={group.svgPath} />
          </svg>
        </span>
        <span>{group.label}</span>
      </div>
      <div className="grid gap-1">
        {group.items.map((item) => {
          const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={buildHref(item.href, stockCode)}
              data-tour={getTourAttr(item.href)}
              onClick={onNavigate}
              className={`rounded-2xl px-3 py-2.5 text-sm no-underline transition ${
                active
                  ? 'border border-primary/18 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(229,241,255,0.68))] text-nav-active shadow-[0_18px_34px_-26px_rgba(11,107,203,0.42)]'
                  : 'border border-transparent text-nav-text hover:bg-white/55 hover:text-text-primary'
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function CompactNav({
  pathname,
  stockCode,
  onNavigate,
}: {
  pathname: string;
  stockCode: string;
  onNavigate?: () => void;
}) {
  return (
    <div className="grid gap-2 px-2">
      {NAV_GROUPS.flatMap((group) =>
        group.items.map((item) => {
          const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={buildHref(item.href, stockCode)}
              onClick={onNavigate}
              title={item.label}
              className={`flex h-11 items-center justify-center rounded-2xl no-underline text-xs transition ${
                active
                  ? 'border border-primary/18 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(229,241,255,0.68))] text-nav-active shadow-[0_18px_34px_-26px_rgba(11,107,203,0.42)]'
                  : 'border border-transparent text-nav-text hover:bg-white/55'
              }`}
            >
              <span className="font-medium tracking-[0.08em]">{item.label.slice(0, 2)}</span>
            </Link>
          );
        }),
      )}
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const rawPathname = useStablePathname();
  const pathname = rawPathname ?? '/';
  const useOverlayDock = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const storeCode = useStockContext((state) => state.code);
  const hydrated = useHydrated();
  const isAuthPage = rawPathname ? isPublicPathname(rawPathname) : false;
  const [drawerOpen, setDrawerOpen] = useState(false);

  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const createWorkspace = useWorkbenchStore((state) => state.createWorkspace);
  const updateLayout = useWorkbenchStore((state) => state.updateLayout);
  const lastSyncedAt = useWorkbenchStore((state) => state.lastSyncedAt);
  const dockOpen = useCopilotStore((state) => state.dockOpen);
  const setDockOpen = useCopilotStore((state) => state.setDockOpen);
  const setGlobalActions = useCopilotStore((state) => state.setGlobalActions);
  const pageVisitRef = useRef<{ route: string; pageKey: string; enteredAt: number; label: string } | null>(null);

  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const bffAvailability = useBffAvailability({ probeOnMount: !isAuthPage });
  const layout = useMemo(() => resolveWorkspaceLayout(activeWorkspace.layout), [activeWorkspace.layout]);
  const currentStockCode = hydrated ? storeCode || activeWorkspace.context.stockCode || '' : '';
  const isStrategyMarketPage = pathname === '/strategy-market' || pathname.startsWith('/strategy-market/');
  const shellWorkspaceName = isStrategyMarketPage ? '策略工作区' : activeWorkspace.name;
  const shellHeaderStockCode = isStrategyMarketPage ? '' : currentStockCode;
  const isAiCenterPage = pathname === '/assistant' || pathname.startsWith('/assistant/');
  const dockRequested = hydrated && !isAiCenterPage && (layout.dockVisible || dockOpen);
  const showPersistentDock = dockRequested && !useOverlayDock;
  const showOverlayDock = dockOpen && !isAiCenterPage && useOverlayDock;

  useEffect(() => {
    if (isAuthPage || user) return;
    if (!hasLoggedInHint()) return;
    if (!bffAvailability.reachable) return;
    probeAuthSession<{ authenticated?: boolean; user?: User }>()
      .then((data) => {
        if (data?.authenticated && data.user) setUser(data.user);
      })
      .catch(() => {});
  }, [bffAvailability.reachable, isAuthPage, setUser, user]);

  useEffect(() => {
    if (dockOpen && !layout.dockVisible) {
      updateLayout({ dockVisible: true });
    }
  }, [dockOpen, layout.dockVisible, updateLayout]);

  const globalActions = useMemo<PageActionDefinition[]>(
    () => [
      {
        id: 'global.open-home',
        label: '打开首页',
        description: '跳转到首页总览',
        keywords: ['首页', '总览'],
        scope: 'global',
        run: () => {
          router.push('/');
          return { message: '已打开首页' };
        },
      },
      {
        id: 'global.open-watchlist',
        label: '打开自选股',
        description: '跳转到自选股页',
        keywords: ['自选', 'watchlist'],
        scope: 'global',
        run: () => {
          router.push('/watchlist');
          return { message: '已打开自选股' };
        },
      },
      {
        id: 'global.open-search',
        label: '打开智能搜索',
        description: '跳转到智能搜索页',
        keywords: ['搜索', 'search'],
        scope: 'global',
        run: () => {
          router.push('/search');
          return { message: '已打开智能搜索' };
        },
      },
      {
        id: 'global.open-workspace-templates',
        label: '打开工作区模板',
        description: '查看工作区模板与编排入口',
        keywords: ['工作区', '模板'],
        scope: 'global',
        run: () => {
          router.push('/workspace-templates');
          return { message: '已打开工作区模板' };
        },
      },
      {
        id: 'global.new-workspace',
        label: '新建工作区',
        description: '创建一个新的工作区',
        keywords: ['工作区', '新建'],
        scope: 'global',
        exposeToCopilot: false,
        run: () => {
          createWorkspace();
          return { message: '已新建工作区' };
        },
      },
      {
        id: 'global.toggle-nav',
        label: layout.navCollapsed ? '展开导航' : '收起导航',
        description: '切换左侧导航栏显示状态',
        keywords: ['导航', '折叠'],
        scope: 'global',
        run: () => {
          updateLayout({ navCollapsed: !layout.navCollapsed });
          return { message: layout.navCollapsed ? '已展开导航' : '已收起导航' };
        },
      },
      {
        id: 'global.open-copilot',
        label: showPersistentDock || showOverlayDock ? '聚焦 Copilot' : '打开 Copilot',
        description: '打开右侧 Copilot 面板',
        keywords: ['copilot', 'ai', '助手'],
        scope: 'global',
        run: () => {
          updateLayout({ dockVisible: true });
          setDockOpen(true);
          return { message: '已打开 Copilot' };
        },
      },
    ],
    [createWorkspace, layout.navCollapsed, router, setDockOpen, showOverlayDock, showPersistentDock, updateLayout],
  );

  useEffect(() => {
    setGlobalActions(globalActions.map(({ run: _run, ...meta }) => meta));
    const unregisters = globalActions.map((action) => pageActionBus.register(action));
    return () => {
      unregisters.forEach((dispose) => dispose());
      setGlobalActions([]);
    };
  }, [globalActions, setGlobalActions]);

  useEffect(() => {
    ensureBehaviorSessionId();
  }, []);

  useEffect(() => {
    if (isAuthPage) return;
    const pageKey = resolveBehaviorPageKey(pathname);
    const label = findNavLabel(pathname);
    const now = Date.now();
    const previous = pageVisitRef.current;

    if (previous && previous.route !== pathname) {
      trackBehaviorEvent({
        pageKey: previous.pageKey,
        route: previous.route,
        eventType: 'page_leave',
        targetType: 'page',
        targetLabel: previous.label,
        payload: { durationMs: now - previous.enteredAt },
        source: 'app-shell.route',
      });
      trackBehaviorEvent({
        pageKey,
        route: pathname,
        eventType: 'route_change',
        targetType: 'page',
        targetLabel: `${previous.route} -> ${pathname}`,
        payload: { from: previous.route, to: pathname },
        source: 'app-shell.route',
      });
      void flushBehaviorEvents();
    }

    trackBehaviorEvent({
      pageKey,
      route: pathname,
      eventType: 'page_enter',
      targetType: 'page',
      targetLabel: label,
      source: 'app-shell.route',
    });
    pageVisitRef.current = { route: pathname, pageKey, enteredAt: now, label };
  }, [isAuthPage, pathname]);

  useEffect(() => {
    if (isAuthPage) return;

    function handleClick(event: MouseEvent) {
      const meta = describeActionableElement(event.target);
      if (!meta) return;
      trackBehaviorEvent({
        pageKey: resolveBehaviorPageKey(pathname),
        route: pathname,
        eventType: meta.eventType,
        targetType: meta.targetType,
        targetLabel: meta.targetLabel,
        targetId: meta.targetId,
        targetTestId: meta.targetTestId,
        payload: meta.payload,
        source: 'app-shell.click',
      });
    }

    function handleSubmit(event: Event) {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form) return;
      const submitter = (event as SubmitEvent).submitter instanceof HTMLElement ? (event as SubmitEvent).submitter : null;
      trackBehaviorEvent({
        pageKey: resolveBehaviorPageKey(pathname),
        route: pathname,
        eventType: 'form_submit',
        targetType: 'form',
        targetLabel: submitter?.textContent?.trim() || form.getAttribute('aria-label') || 'form_submit',
        targetId: form.id || undefined,
        payload: {
          action: form.getAttribute('action') || undefined,
          method: form.getAttribute('method') || undefined,
        },
        source: 'app-shell.submit',
      });
    }

    function handleChange(event: Event) {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement || target instanceof HTMLInputElement)) return;
      if (target instanceof HTMLInputElement && !['checkbox', 'radio'].includes(target.type)) return;
      trackBehaviorEvent({
        pageKey: resolveBehaviorPageKey(pathname),
        route: pathname,
        eventType: target instanceof HTMLSelectElement ? 'filter_change' : 'view_toggle',
        targetType: target.tagName.toLowerCase(),
        targetLabel: target.getAttribute('aria-label') || target.id || target.name || undefined,
        targetId: target.id || target.name || undefined,
        payload: {
          value: target instanceof HTMLSelectElement ? target.value : target.checked,
        },
        source: 'app-shell.change',
      });
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        void flushBehaviorEvents();
      }
    }

    document.addEventListener('click', handleClick, true);
    document.addEventListener('submit', handleSubmit, true);
    document.addEventListener('change', handleChange, true);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('click', handleClick, true);
      document.removeEventListener('submit', handleSubmit, true);
      document.removeEventListener('change', handleChange, true);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isAuthPage, pathname]);

  if (isAuthPage) {
    return <>{children}</>;
  }

  // 在水合完成前使用默认布局值，避免持久化 store 与 SSR 默认值不一致导致结构性 hydration 错误
  const navRailWidth = hydrated ? (layout.navCollapsed ? 84 : layout.navWidth) : layout.navWidth;
  const navCollapsed = hydrated && layout.navCollapsed;
  const pageWidthClass = layout.pageWidth === 'focused' ? 'mx-auto max-w-7xl' : 'mx-auto max-w-[1820px]';
  const desktopDockWidth = `clamp(280px, 22vw, ${layout.dockWidth}px)`;
  const syncText = lastSyncedAt
    ? `同步 ${new Date(lastSyncedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
    : '本地工作区';
  const activePageLabel = findNavLabel(pathname);
  const shellTheme = resolveShellTheme(pathname);

  const desktopNav = (
    <aside className="app-shell-sidebar hidden shrink-0 xl:flex xl:flex-col" style={{ width: navRailWidth }}>
      <div className="border-b border-sidebar-border px-4 py-4">
        <div className="eyebrow mb-2">AIASK 导航</div>
        <div className="flex items-center justify-between gap-2">
          <Link href="/" className="no-underline text-lg font-semibold text-text-primary">
            AIASK
          </Link>
          <button
            type="button"
            onClick={() => updateLayout({ navCollapsed: !layout.navCollapsed })}
            className="rounded-full border border-border bg-surface px-2 py-1 text-xs shadow-sm"
            aria-label={navCollapsed ? '展开导航' : '收起导航'}
            suppressHydrationWarning
          >
            {navCollapsed ? '»' : '«'}
          </button>
        </div>
        {!navCollapsed ? (
          <p className="mb-0 mt-3 text-xs leading-5 text-text-secondary">
            统一查看市场、研究、策略和交易模块。
          </p>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        {navCollapsed ? (
          <CompactNav pathname={pathname} stockCode={currentStockCode} />
        ) : (
          <>
            {NAV_GROUPS.map((group) => (
              <NavSection key={group.label} group={group} pathname={pathname} stockCode={currentStockCode} />
            ))}
            <div className="mt-6 border-t border-sidebar-border pt-4">
              <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                辅助入口
              </div>
              <div className="grid gap-1">
                {UTILITY_LINKS.map((item) => {
                  const active = pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={buildHref(item.href, currentStockCode)}
                      className={`rounded-2xl px-3 py-2 text-sm no-underline transition ${
                        active
                          ? 'border border-primary/18 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(229,241,255,0.68))] text-nav-active shadow-[0_18px_34px_-26px_rgba(11,107,203,0.42)]'
                          : 'border border-transparent text-nav-text hover:bg-white/55 hover:text-text-primary'
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
      <div className="border-t border-sidebar-border px-4 py-4 text-xs text-text-secondary">
        <div className="font-medium text-text-primary" suppressHydrationWarning>{shellWorkspaceName}</div>
        <div className="mt-1" suppressHydrationWarning>{syncText}</div>
        {!navCollapsed ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href="/settings"
              className="rounded-full border border-border bg-surface px-3 py-1 no-underline text-inherit"
            >
              设置
            </Link>
            <Link
              href="/skills"
              className="rounded-full border border-border bg-surface px-3 py-1 no-underline text-inherit"
            >
              技能中心
            </Link>
          </div>
        ) : null}
      </div>
    </aside>
  );

  const mobileDrawer = drawerOpen ? (
    <div className="fixed inset-0 z-50 flex xl:hidden">
      <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
      <nav className="relative z-10 flex w-[85vw] max-w-[320px] flex-col rounded-r-lg border border-sidebar-border bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(244,249,255,0.58))] shadow-[0_32px_72px_-32px_rgba(15,23,42,0.42)] backdrop-blur-2xl">
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-sidebar-border px-4 py-4">
          <Link
            href="/"
            onClick={() => setDrawerOpen(false)}
            className="no-underline text-base font-semibold text-text-primary"
          >
            AIASK
          </Link>
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="rounded-full border border-border bg-surface px-3 py-1 text-sm"
          >
            关闭
          </button>
        </div>

        {/* 工作流切换 */}
        <div className="px-4 pt-4 pb-2">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">切换工作流</div>
          <div className="grid grid-cols-2 gap-2">
            {NAV_GROUPS.map((group) => {
              const isActive = groupContainsPath(group, pathname);
              const firstItem = group.items[0];
              return (
                <Link
                  key={group.label}
                  href={buildHref(firstItem.href, currentStockCode)}
                  onClick={() => setDrawerOpen(false)}
                  className={`flex flex-col items-center justify-center gap-1.5 rounded-[18px] border p-3 no-underline transition ${
                    isActive
                      ? 'border-primary/20 bg-nav-active-bg text-nav-active'
                      : 'border-border bg-surface text-text-secondary hover:border-border hover:bg-surface-alt hover:text-text-primary'
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-full border text-[11px] font-bold tracking-wider ${
                      isActive ? 'border-primary/20 bg-primary/10 text-primary' : 'border-border bg-surface-alt'
                    }`}
                  >
                    {group.icon}
                  </span>
                  <span className="text-xs font-medium">{group.label}</span>
                </Link>
              );
            })}
          </div>
        </div>

        {/* 当前工作流的子页面 */}
        {NAV_GROUPS.filter((g) => groupContainsPath(g, pathname)).map((group) => (
          <div key={group.label} className="border-t border-sidebar-border px-4 py-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              {group.label} 页面
            </div>
            <div className="grid gap-1">
              {group.items.map((item) => {
                const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={buildHref(item.href, currentStockCode)}
                    onClick={() => setDrawerOpen(false)}
                    className={`rounded-2xl px-3 py-2 text-sm no-underline transition ${
                      active ? 'bg-nav-active-bg text-nav-active' : 'text-nav-text hover:bg-surface'
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}

        {/* 更多入口 */}
        <div className="border-t border-sidebar-border px-4 py-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">更多</div>
          <div className="grid gap-1">
            {UTILITY_LINKS.map((item) => (
              <Link
                key={item.href}
                href={buildHref(item.href, currentStockCode)}
                onClick={() => setDrawerOpen(false)}
                className="rounded-2xl px-3 py-2 text-sm no-underline text-nav-text hover:bg-surface"
              >
                {item.label}
              </Link>
            ))}
            <Link
              href="/settings"
              onClick={() => setDrawerOpen(false)}
              className="rounded-2xl px-3 py-2 text-sm no-underline text-nav-text hover:bg-surface"
            >
              设置中心
            </Link>
          </div>
        </div>
      </nav>
    </div>
  ) : null;

  const mobileDock = showOverlayDock ? (
    <div className="fixed inset-0 z-50 flex justify-end 2xl:hidden">
      <div className="absolute inset-0 bg-black/40" onClick={() => setDockOpen(false)} />
      <div className="relative z-10 h-full w-[90vw] max-w-[420px] rounded-l-lg border border-border bg-[linear-gradient(180deg,rgba(255,255,255,0.76),rgba(244,249,255,0.58))] shadow-[0_32px_72px_-32px_rgba(15,23,42,0.42)] backdrop-blur-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-medium text-text-primary">AI 助手</div>
            <div className="text-xs text-text-secondary">按需展开，不常驻占据主画布</div>
          </div>
          <button
            type="button"
            onClick={() => setDockOpen(false)}
            className="rounded-full border border-border px-3 py-1 text-xs"
          >
            关闭
          </button>
        </div>
        <div className="h-[calc(100%-57px)]">
          <CopilotDock />
        </div>
      </div>
    </div>
  ) : null;

  return (
    <OnboardingProvider>
      <div className={`app-shell-root app-theme-${shellTheme}`}>
        <div className="app-shell-ambient" aria-hidden="true">
          <span className="app-shell-orb app-shell-orb-1" />
          <span className="app-shell-orb app-shell-orb-2" />
          <span className="app-shell-orb app-shell-orb-3" />
        </div>
        <Onboarding />
        {mobileDrawer}
        {mobileDock}
        <div className="app-shell-frame">
          {desktopNav}
          <div className="app-shell-main-column flex flex-1 flex-col">
            <header className="app-shell-header sticky top-4 z-30 flex items-center justify-between px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => setDrawerOpen(true)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-lg shadow-sm xl:hidden"
                  aria-label="打开导航"
                >
                  ☰
                </button>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-[0.18em] text-text-muted">
                    当前页面
                  </div>
                  <div className="truncate text-base font-semibold text-text-primary">{activePageLabel}</div>
                  <div className="truncate text-[11px] text-text-secondary" suppressHydrationWarning>
                    {shellWorkspaceName}
                    {shellHeaderStockCode ? <span className="ml-2 font-mono text-primary">{shellHeaderStockCode}</span> : null}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!isAiCenterPage ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (showPersistentDock || showOverlayDock) {
                        updateLayout({ dockVisible: false });
                        setDockOpen(false);
                        return;
                      }
                      updateLayout({ dockVisible: true });
                      setDockOpen(true);
                    }}
                    className="hidden rounded-full border border-border bg-surface px-3 py-1.5 text-xs shadow-sm lg:inline-flex"
                  >
                    {showPersistentDock || showOverlayDock ? '收起 AI' : '打开 AI'}
                  </button>
                ) : null}
                <WsIndicator />
                <NotificationBell />
                <ThemeToggle />
                {user ? (
                  <Link href="/settings" className="flex items-center gap-2 no-underline text-inherit">
                    {user.avatarUrl ? (
                      <img
                        src={user.avatarUrl}
                        alt="用户头像"
                        className="h-8 w-8 rounded-full border border-border object-cover"
                      />
                    ) : (
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white shadow-sm">
                        {(user.nickname ?? user.username).slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <span className="hidden text-sm text-text-secondary xl:inline">{user.nickname || user.username}</span>
                  </Link>
                ) : null}
                {user ? (
                  <button
                    type="button"
                    onClick={() => {
                      logout();
                      window.location.href = '/login';
                    }}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs shadow-sm"
                  >
                    退出
                  </button>
                ) : null}
              </div>
            </header>

            <div className="app-shell-main">
              <main className="app-shell-content mobile-safe-bottom min-w-0 flex-1 overflow-auto">
                <div className={`${pageWidthClass} w-full px-2 py-2 sm:px-4 md:px-5 lg:px-6`}>{children}</div>
              </main>
              {showPersistentDock ? (
                <aside className="app-shell-dock hidden shrink-0 2xl:flex" style={{ width: desktopDockWidth }}>
                  <CopilotDock />
                </aside>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </OnboardingProvider>
  );
}
