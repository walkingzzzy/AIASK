'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import { PageContainer, KpiCard, KpiGrid, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useMobile } from '@/hooks/use-mobile';
import { extractObject, extractArray, fmtAmount } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { tradingInterval } from '@/lib/trading-hours';
import { useAuthStore } from '@/store/auth-store';
import { useDashboardPrefs } from '@/hooks/use-dashboard-prefs';
import { useHydrated } from '@/hooks/use-hydrated';
import type { DashboardModuleKey } from '@/hooks/use-dashboard-prefs';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';
import { hasLoggedInHint } from '@/lib/auth';
import { useWatchlistStore } from '@/store/watchlist-store';
import { useStockContext } from '@/store/stock-context';

import { MarketOverview } from '@/components/home/MarketOverview';
import { PersonalSecondaryCards, WatchlistRecent } from '@/components/home/PersonalDashboard';
import { FundFlowSection } from '@/components/home/FundFlowSection';
import { DashboardCards } from '@/components/home/DashboardCards';
import type { DashboardCard } from '@/components/home/DashboardCards';
import { SystemStatus } from '@/components/home/SystemStatus';
import type {
  AlertItem,
  DashboardMarketAnomaly,
  DashboardMarketNewsItem,
  DashboardMarketNewsResponse,
  DashboardQuoteSnapshot,
  PaperTradingPosition,
  PaperTradingPositionsResponse,
  PaperTradingSummary,
} from '@aiask/shared-types';

const poll = tradingInterval(60_000);
const slowPoll = tradingInterval(180_000);
const INDEX_CODES = ['000001', '399001', '399006', '000688'] as const;
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
type HomeDetailsTab = 'market' | 'personal' | 'operations';
type HomeSummaryTab = 'market' | 'account' | 'operations';

function toFiniteNumber(value: unknown): number | null {
  if (value == null || value === '') return null;
  const normalized = typeof value === 'string' ? value.replace(/[%\s,]/g, '') : value;
  const n = Number(normalized);
  return Number.isFinite(n) ? n : null;
}

function normalizeDashboardQuote(raw: Record<string, unknown>): DashboardQuoteSnapshot | null {
  const code = String(raw.code ?? '').trim();
  const name = String(raw.name ?? raw.index_name ?? '').trim();
  const price = toFiniteNumber(raw.price ?? raw.close ?? raw.current);
  const change = toFiniteNumber(raw.change);
  const changePercent = toFiniteNumber(raw.changePercent ?? raw.change_pct ?? raw.pct_change);

  if (!code && !name) return null;

  return {
    code,
    name,
    price,
    change,
    changePercent,
    change_pct: changePercent,
  };
}

function normalizePaperPositionsPayload(raw: unknown): PaperTradingPositionsResponse {
  const payload = ensureRecordOrArray(raw, '模拟盘持仓(首页)');
  return {
    positions: extractArray(payload, 'positions', 'items', 'data') as PaperTradingPosition[],
  };
}

function normalizeMarketNewsPayload(raw: unknown): DashboardMarketNewsResponse {
  const payload = ensureRecordOrArray(raw, '市场快讯(首页)');
  return {
    items: extractArray(payload, 'items', 'news', 'data') as DashboardMarketNewsItem[],
  };
}

function normalizeAlertsPayload(raw: unknown): { items?: AlertItem[] } {
  const payload = ensureRecordOrArray(raw, '活跃预警(首页)');
  return {
    items: extractArray(payload, 'items', 'alerts', 'data') as AlertItem[],
  };
}

export default function HomePage() {
  const router = useRouter();
  const mounted = useHydrated();
  const compactHome = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactHero = useMobile(RESPONSIVE_BREAKPOINTS.tablet);
  const [dateStr, setDateStr] = useState('');
  const [pageVisible, setPageVisible] = useState(() =>
    typeof document === 'undefined' ? true : document.visibilityState === 'visible',
  );
  const [detailTab, setDetailTab] = useState<HomeDetailsTab>('market');
  const [summaryTab, setSummaryTab] = useState<HomeSummaryTab>('market');
  const [showDashboardSettings, setShowDashboardSettings] = useState(false);
  const liveRefetch = pageVisible ? poll : false;
  const lazyRefetch = pageVisible ? slowPoll : false;

  const user = useAuthStore((s) => s.user);
  const canLoadPersonalized = mounted && Boolean(user || hasLoggedInHint());

  /* ── Data queries ─────────────────────────────────────────────── */
  const idxQ = useApiQuery<unknown>('/market/index-batch-quotes', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    body: { codes: INDEX_CODES },
    parse: (r) => ensureRecordOrArray(r, '首页指数批量'),
    redirectOnUnauthorized: false,
  });
  const limitUpQ = useApiQuery<unknown>('/market/limit-up-stats', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (r) => ensureRecord(r, '涨停统计'),
    redirectOnUnauthorized: false,
  });
  const northQ = useApiQuery<unknown>('/fund-flow/north', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (r) => ensureRecordOrArray(r, '北向资金'),
    redirectOnUnauthorized: false,
  });
  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (r) => ensureRecord(r, '恐慌贪婪指数'),
    redirectOnUnauthorized: false,
  });
  const healthQ = useApiQuery<unknown>('/health/mcp', { enabled: mounted, redirectOnUnauthorized: false });
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile', {
    enabled: canLoadPersonalized,
    parse: (r) => ensureRecord(r, '用户配置'),
    redirectOnUnauthorized: false,
  });
  const paperSumQ = useApiQuery<PaperTradingSummary>('/paper-trading/summary', {
    enabled: canLoadPersonalized,
    parse: (r) => ensureRecord(r, '模拟盘概览(首页)') as PaperTradingSummary,
    redirectOnUnauthorized: false,
  });
  const paperPosQ = useApiQuery<PaperTradingPositionsResponse>('/paper-trading/positions', {
    enabled: canLoadPersonalized,
    parse: normalizePaperPositionsPayload,
    redirectOnUnauthorized: false,
  });
  const newsQ = useApiQuery<DashboardMarketNewsResponse>('/research/market-news?limit=5', {
    enabled: mounted,
    parse: normalizeMarketNewsPayload,
    redirectOnUnauthorized: false,
  });

  const { visibility: dashboardVisibility, toggle: toggleDashboardModule } = useDashboardPrefs(mounted, profileQ);

  const sectorQ = useApiQuery<unknown>('/market/blocks?blockType=industry&limit=20', {
    enabled: mounted && dashboardVisibility.market,
    refetchInterval: lazyRefetch,
    placeholderData: 'keepPrevious',
    parse: (r) => ensureRecordOrArray(r, '板块行情(首页)'),
    redirectOnUnauthorized: false,
  });
  const sectorFlowQ = useApiQuery<unknown>('/fund-flow/sector', {
    enabled: mounted && dashboardVisibility['fund-flow'],
    refetchInterval: lazyRefetch,
    placeholderData: 'keepPrevious',
    parse: (r) => ensureRecordOrArray(r, '板块资金流(首页)'),
    redirectOnUnauthorized: false,
  });
  const alertsQ = useApiQuery<{ items?: AlertItem[] }>('/alerts/list?status=active', {
    enabled: canLoadPersonalized && dashboardVisibility.alerts,
    parse: normalizeAlertsPayload,
    redirectOnUnauthorized: false,
  });
  const riskQ = useApiQuery<unknown>('/risk/summary?lookbackDays=252', {
    enabled: canLoadPersonalized && dashboardVisibility.risk,
    parse: (r) => ensureRecord(r, '风险汇总(首页)'),
    redirectOnUnauthorized: false,
  });

  const strategySubsQ = useApiQuery<unknown>(user ? '/strategy-market/my-subscriptions' : null, {
    enabled: mounted && dashboardVisibility.strategy && Boolean(user),
    parse: (r) => ensureRecordOrArray(r, '策略订阅(首页)'),
    redirectOnUnauthorized: false,
  });

  const watchlistItems = useWatchlistStore((s) => s.groups.flatMap((g) => g.items));
  const recentStocks = useStockContext((s) => s.recent);
  const hydratedWatchlistItems = mounted ? watchlistItems : [];
  const hydratedRecentStocks = mounted ? recentStocks : [];

  /* ── WS real-time quotes ─────────────────────────────────────── */
  const wsQuotesRef = useRef<Map<string, DashboardQuoteSnapshot>>(new Map());
  const [, setWsQuoteTick] = useState(0);
  const handleWsQuote = useCallback((data: QuoteData) => {
    wsQuotesRef.current.set(data.code, data as DashboardQuoteSnapshot);
    setWsQuoteTick((t) => t + 1);
  }, []);
  useQuoteSubscription({ codes: [...INDEX_CODES], type: 'index', onUpdate: handleWsQuote });

  const quoteCodes = useMemo(() => {
    const s = new Set<string>();
    watchlistItems.forEach((i) => s.add(i.code));
    recentStocks.slice(0, 8).forEach((i) => s.add(i.code));
    return Array.from(s);
  }, [watchlistItems, recentStocks]);
  const batchQ = useApiQuery<unknown>(quoteCodes.length > 0 ? '/market/batch-quotes' : null, {
    enabled: mounted && pageVisible,
    refetchInterval: lazyRefetch,
    body: { codes: quoteCodes },
    placeholderData: 'keepPrevious',
    redirectOnUnauthorized: false,
  });
  const quoteMap = useMemo(() => {
    const m = new Map<string, DashboardQuoteSnapshot>();
    extractArray(batchQ.data, 'quotes', 'items', 'data').forEach((q) => {
      const c = String(q.code ?? '');
      if (c) m.set(c, q as DashboardQuoteSnapshot);
    });
    return m;
  }, [batchQ.data]);

  /* ── Lifecycle ─────────────────────────────────────────────────── */
  useEffect(() => {
    const updateDate = () => setDateStr(new Date().toLocaleString('zh-CN', { hour12: false }));
    updateDate();
    const timer = window.setInterval(updateDate, 60_000);
    const onVis = () => setPageVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);
  useEffect(() => {
    document.title = '首页 | AIASK';
    return () => {
      document.title = 'AIASK 智能股票分析';
    };
  }, []);

  /* ── Derived data ─────────────────────────────────────────────── */
  const lastUpdated = idxQ.dataUpdatedAt ? new Date(idxQ.dataUpdatedAt) : null;
  const indices = useMemo<DashboardQuoteSnapshot[]>(() => {
    const arr = extractArray(idxQ.data, 'quotes', 'items', 'data');
    if (arr.length > 0) {
      return arr
        .map((item) => {
          const record = extractObject(item);
          return normalizeDashboardQuote(record.quote ? extractObject(record.quote) : record);
        })
        .filter((item): item is DashboardQuoteSnapshot => item != null);
    }
    const obj = extractObject(idxQ.data);
    const normalized = normalizeDashboardQuote(obj.quote ? extractObject(obj.quote) : obj);
    return normalized ? [normalized] : [];
  }, [idxQ.data]);
  const validIndices = useMemo(() => indices.filter((item) => item.code || item.name), [indices]);

  const luStats = extractObject(limitUpQ.data);
  const northFlows = extractArray(northQ.data, 'items', 'flows');
  const latestNorth = northFlows.length
    ? [...northFlows].sort((a, b) =>
        String(a.date ?? a.tradeDate ?? '').localeCompare(String(b.date ?? b.tradeDate ?? '')),
      )[northFlows.length - 1]
    : null;
  const fgRaw = extractObject(fearGreedQ.data);
  const fgObj =
    fgRaw.result && typeof fgRaw.result === 'object' ? extractObject(fgRaw.result as Record<string, unknown>) : fgRaw;
  const fgValue = Number(fgObj.index ?? fgObj.value ?? fgObj.fear_greed_index ?? 50);
  const fgLabel =
    fgValue <= 25 ? '极度恐惧' : fgValue <= 40 ? '恐惧' : fgValue <= 60 ? '中性' : fgValue <= 75 ? '贪婪' : '极度贪婪';
  const sectors = useMemo(() => extractArray(sectorQ.data, 'blocks', 'items', 'data'), [sectorQ.data]);
  const sectorFlows = useMemo(() => {
    const raw = extractArray(sectorFlowQ.data, 'flows', 'items', 'data');
    const mapped = raw
      .slice(0, 10)
      .map((x) => ({
        label: String(x.name ?? x.sector ?? '').slice(0, 6),
        value: Number(x.netInflow ?? x.net_inflow ?? x.main_net_inflow ?? 0),
      }));
    return mapped.some((m) => m.value !== 0) ? mapped : [];
  }, [sectorFlowQ.data]);
  const health = healthQ.data as Record<string, unknown> | null;
  const mcp = (health?.mcp ?? {}) as Record<string, unknown>;
  const activeAlerts = useMemo<AlertItem[]>(() => alertsQ.data?.items ?? [], [alertsQ.data]);
  const paperSummary = useMemo(() => (paperSumQ.data ?? {}) as PaperTradingSummary, [paperSumQ.data]);
  const paperAccount = useMemo(
    () => (paperSummary.account ?? {}) as NonNullable<PaperTradingSummary['account']>,
    [paperSummary],
  );
  const paperPositions = useMemo<PaperTradingPosition[]>(() => paperPosQ.data?.positions ?? [], [paperPosQ.data]);
  const marketNews = useMemo<DashboardMarketNewsItem[]>(() => newsQ.data?.items ?? [], [newsQ.data]);
  const riskSummary = useMemo(() => extractObject(riskQ.data), [riskQ.data]);
  const riskDegraded = Boolean(riskSummary.degraded);
  const riskEmpty = Boolean(riskSummary.empty);
  const riskMs = useMemo(() => {
    const raw = extractObject(riskSummary.moduleStatus);
    return { var: extractObject(raw.var), stress: extractObject(raw.stress), exposure: extractObject(raw.exposure) };
  }, [riskSummary]);
  const riskSource = extractObject(riskSummary.sourceContext);
  const strategySubs = useMemo(
    () => extractArray(strategySubsQ.data, 'strategies', 'items', 'data'),
    [strategySubsQ.data],
  );
  const activeAlertCount = mounted ? activeAlerts.length : 0;
  const watchlistCount = hydratedWatchlistItems.length;
  const primaryStockCode = hydratedRecentStocks[0]?.code || hydratedWatchlistItems[0]?.code || undefined;
  const displayDateStr = mounted ? dateStr : '';

  /* ── Module statuses ──────────────────────────────────────────── */
  const moduleStatuses = useMemo(() => {
    const st = (err: boolean, loading: boolean) =>
      err ? ('error' as const) : loading ? ('loading' as const) : ('ok' as const);
    return {
      market: st(Boolean(idxQ.error || sectorQ.error), idxQ.isFetching || sectorQ.isFetching),
      'fund-flow': st(Boolean(northQ.error || sectorFlowQ.error), northQ.isFetching || sectorFlowQ.isFetching),
      alerts: st(Boolean(alertsQ.error), alertsQ.isFetching),
      sentiment: st(Boolean(fearGreedQ.error), fearGreedQ.isFetching),
      strategy: st(Boolean(strategySubsQ.error), strategySubsQ.isFetching),
      risk: st(Boolean(riskQ.error || riskDegraded), riskQ.isFetching),
    } as Record<DashboardModuleKey, 'ok' | 'loading' | 'error'>;
  }, [
    idxQ.error,
    sectorQ.error,
    idxQ.isFetching,
    sectorQ.isFetching,
    northQ.error,
    sectorFlowQ.error,
    northQ.isFetching,
    sectorFlowQ.isFetching,
    alertsQ.error,
    alertsQ.isFetching,
    fearGreedQ.error,
    fearGreedQ.isFetching,
    strategySubsQ.error,
    strategySubsQ.isFetching,
    riskQ.error,
    riskQ.isFetching,
    riskDegraded,
  ]);

  /* ── Quick actions & anomalies ────────────────────────────────── */
  const latestNorthValue = Number(latestNorth?.total ?? latestNorth?.netInflow ?? latestNorth?.net_inflow ?? 0);
  const latestNorthLabel = latestNorth ? fmtAmount(latestNorthValue) : '暂无数据';

  const marketAnomalies = useMemo<DashboardMarketAnomaly[]>(() => {
    const luCount = Number(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? 0);
    const topSec = sectors[0] ?? null;
    const flowTop = sectorFlows[0] ?? null;
    const out: DashboardMarketAnomaly[] = [];
    if (luCount > 0)
      out.push({
        title: '涨停家数',
        value: `${luCount} 家`,
        href: '/market?tab=limitup&from=home',
        tone: luCount >= 80 ? 'danger' : 'warning',
      });
    if (topSec) {
      const c = Number(topSec.avgChange ?? topSec.avg_change ?? topSec.change_pct ?? 0);
      out.push({
        title: `板块热力 · ${String(topSec.name ?? '行业')}`,
        value: `${c >= 0 ? '+' : ''}${c.toFixed(2)}%`,
        href: `/market?tab=blocks&block=${encodeURIComponent(String(topSec.code ?? ''))}&from=home`,
        tone: c >= 0 ? 'danger' : 'success',
      });
    }
    if (flowTop)
      out.push({
        title: `资金流向 · ${flowTop.label}`,
        value: fmtAmount(flowTop.value),
        href: '/fund-flow?from=home',
        tone: flowTop.value >= 0 ? 'danger' : 'success',
      });
    if (latestNorth) {
      const v = Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? 0);
      out.push({
        title: '北向净流入',
        value: fmtAmount(v),
        href: '/fund-flow?from=home',
        tone: v >= 0 ? 'danger' : 'success',
      });
    }
    return out.slice(0, 4);
  }, [luStats, sectors, sectorFlows, latestNorth]);
  const heroCapabilities = [
    {
      icon: '📈',
      title: '实时行情与监控',
      meta: '行情看板 · 指数板块 · 资金流 · 自选联动',
    },
    {
      icon: '🧠',
      title: '研究分析能力',
      meta: '研报公告 · 基本面 · 技术面 · AI 解读',
    },
    {
      icon: '🧪',
      title: '策略筛选与验证',
      meta: '策略超市 · 回测分析 · 因子分析 · 订阅跟踪',
    },
    {
      icon: '🛡️',
      title: '交易执行与风控',
      meta: '模拟交易 · 组合管理 · 告警中心 · 风险巡检',
    },
  ];
  const heroHighlights = [
    '适合盘前准备、盘中跟踪、策略验证和盘后复盘。',
    '把市场、研究、策略和交易放进同一个工作区。',
    '支持从单只股票跟踪延伸到组合与策略订阅。',
  ];
  const heroRuntimeCards = [
    {
      label: '市场情绪',
      value: fgLabel,
      hint: '来自首页情绪模块',
      tone: 'text-text-primary',
    },
    {
      label: '活跃告警',
      value: activeAlertCount > 0 ? `${activeAlertCount} 条` : '无',
      hint: '当前告警中心状态',
      tone: activeAlertCount > 0 ? 'text-danger' : 'text-text-primary',
    },
    {
      label: '最近刷新',
      value: lastUpdated ? lastUpdated.toLocaleTimeString('zh-CN') : '暂无',
      hint: '首页数据更新时间',
      tone: 'text-text-primary',
    },
    {
      label: '北向资金',
      value: latestNorthLabel,
      hint: '增量资金参考',
      tone: latestNorthValue >= 0 ? 'text-danger' : 'text-success',
    },
  ];
  const heroEntryLinks = [
    {
      href: '/market?from=home',
      icon: '📈',
      title: '行情看板',
      description: '查看指数、板块、自选和市场异动',
    },
    {
      href: '/research?from=home',
      icon: '🧠',
      title: '研究中心',
      description: '进入研报公告、基本面和技术面分析',
    },
    {
      href: '/strategy-market?from=home',
      icon: '🧪',
      title: '策略超市',
      description: '筛选策略并继续进入详情或回测',
    },
    {
      href: '/risk?lookbackDays=252&from=home',
      icon: '🛡️',
      title: '风险中心',
      description: '查看风险摘要、告警和巡检结果',
    },
  ];
  const visibleHeroCapabilities = compactHero ? heroCapabilities.slice(0, 2) : heroCapabilities;
  const hiddenHeroCapabilities = compactHero ? heroCapabilities.slice(2) : [];
  const visibleHeroEntryLinks = compactHome ? heroEntryLinks.slice(0, 2) : heroEntryLinks;
  const hiddenHeroEntryLinks = compactHome ? heroEntryLinks.slice(2) : [];
  const visibleHeroRuntimeCards = compactHome ? heroRuntimeCards.slice(0, 2) : heroRuntimeCards;
  const hiddenHeroRuntimeCards = compactHome ? heroRuntimeCards.slice(2) : [];

  const anomalyDegraded = Boolean(limitUpQ.error || sectorQ.error || sectorFlowQ.error || northQ.error);
  const nickname = String(profileQ.data?.nickname ?? user?.nickname ?? user?.username ?? '投资者');
  const topSectorName = String(sectors[0]?.name ?? '暂无热点');
  const topSectorChange = Number(sectors[0]?.avgChange ?? sectors[0]?.avg_change ?? sectors[0]?.change_pct ?? 0);
  const riskStatusLabel = riskEmpty ? '等待持仓' : riskDegraded ? '降级中' : riskQ.error ? '异常' : '正常';
  const moduleErrorCount = Object.values(moduleStatuses).filter((status) => status === 'error').length;
  const detailTabs = [
    { key: 'market', label: '市场深看' },
    { key: 'personal', label: '个人跟踪' },
    { key: 'operations', label: '运行与风险' },
  ] as const;

  /* ── Dashboard cards (risk / strategy / alerts) ───────────────── */
  const dashboardCards: DashboardCard[] = useMemo(
    () => [
      {
        key: 'risk',
        title: '风险巡检',
        pending: riskQ.isPending,
        error: riskQ.error,
        empty: riskEmpty,
        href: '/risk?lookbackDays=252&from=home',
        content: (
          <KpiGrid cols={3}>
            <KpiCard title="组合ID" value={String(riskSummary.portfolioId ?? '-')} />
            <KpiCard title="回看天数" value={String(riskSummary.lookbackDays ?? '-')} />
            <KpiCard title="降级状态" value={riskDegraded ? '是' : '否'} />
          </KpiGrid>
        ),
        emptyText: '还没有可巡检的风险上下文',
        emptyHint: '如果还没有组合或模拟持仓，风险页不会产出有意义的 VaR、压测和暴露结果。',
        emptyAction: (
          <>
            <Link
              href="/portfolio"
              className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
            >
              先建组合
            </Link>
            <Link
              href="/paper-trading"
              className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline"
            >
              去模拟盘
            </Link>
          </>
        ),
        footer: (
          <div className="mt-2 text-xs text-text-secondary">
            {riskEmpty
              ? String(riskMs.var?.reason ?? '暂无真实持仓风险数据')
              : `VaR: ${riskMs.var?.ok === false ? '异常' : '正常'} | 压测: ${riskMs.stress?.ok === false ? '异常' : '正常'} | 暴露: ${riskMs.exposure?.ok === false ? '异常' : '正常'}`}
            {riskSource.mode ? ` | 来源: ${String(riskSource.mode)}` : ''}
          </div>
        ),
      },
      {
        key: 'strategy',
        title: '策略动态',
        pending: user ? strategySubsQ.isPending : false,
        error: user ? strategySubsQ.error : null,
        empty: user ? strategySubs.length === 0 : false,
        href: '/strategy-market?from=home',
        content: (
          <KpiGrid cols={3}>
            <KpiCard title="订阅策略" value={strategySubs.length} />
            <KpiCard title="活跃用户" value={user?.username ?? '-'} />
            <KpiCard title="状态" value={user ? (strategySubs.length > 0 ? '已订阅' : '待订阅') : '未登录'} />
          </KpiGrid>
        ),
        emptyText: '还没有订阅任何策略',
        emptyHint: '可以先去策略超市按收益、回撤或风险偏好筛选，再订阅适合你的策略。',
        emptyAction: (
          <Link
            href="/strategy-market?from=home"
            className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
          >
            去策略超市
          </Link>
        ),
        footer: user ? (
          strategySubs.length > 0 ? (
            <div className="mt-2 text-xs text-text-secondary">
              最近订阅：{String(strategySubs[0]?.name ?? strategySubs[0]?.strategy_name ?? '-')}
            </div>
          ) : null
        ) : (
          <div className="mt-2 text-xs text-text-secondary">登录后可查看你的订阅策略动态</div>
        ),
      },
      {
        key: 'alerts',
        title: '告警中心',
        pending: alertsQ.isPending,
        error: alertsQ.error,
        empty: activeAlerts.length === 0,
        href: '/alerts?status=active&from=home',
        content: (
          <KpiGrid cols={3}>
            <KpiCard title="活跃告警" value={activeAlerts.length} />
            <KpiCard title="今日重点" value={activeAlerts[0]?.code ? String(activeAlerts[0]?.code) : '-'} />
            <KpiCard title="告警状态" value={activeAlerts.length > 0 ? '运行中' : '空'} />
          </KpiGrid>
        ),
        emptyText: '当前没有活跃告警',
        emptyHint: '如果你在跟踪自选股，建议先配置价格、均线或指标阈值告警，避免盘中反复手动盯盘。',
        emptyAction: (
          <Link
            href="/alerts?from=home"
            className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline"
          >
            创建告警
          </Link>
        ),
        footer:
          activeAlerts.length > 0 ? (
            <div className="mt-2 text-xs text-text-secondary">
              示例：{String(activeAlerts[0]?.indicator ?? '-')} {String(activeAlerts[0]?.condition ?? '')}{' '}
              {String(activeAlerts[0]?.value ?? '')}
            </div>
          ) : null,
      },
    ],
    [
      riskQ.isPending,
      riskQ.error,
      riskSummary,
      riskDegraded,
      riskEmpty,
      riskMs,
      riskSource,
      strategySubsQ.isPending,
      strategySubsQ.error,
      strategySubs,
      user,
      alertsQ.isPending,
      alertsQ.error,
      activeAlerts,
    ],
  );

  usePageContext({
    pageKey: 'home',
    title: '首页',
    summary: `当前监控 ${validIndices.length} 个指数，${marketAnomalies.length} 条市场异常，活跃告警 ${activeAlertCount} 条，自选股 ${watchlistCount} 只。`,
    stockCode: primaryStockCode,
    tags: [
      `${validIndices.length} 个指数`,
      `${activeAlertCount} 条告警`,
      `${watchlistCount} 只自选`,
      fgLabel,
    ],
    suggestions: [
      '总结首页最值得关注的市场信号',
      '把今天的风险、策略和告警整理成行动清单',
      '结合我的自选股给出盘中巡检建议',
    ],
    raw: {
      indices: validIndices.length,
      marketAnomalies: marketAnomalies.length,
      alerts: activeAlertCount,
      watchlist: watchlistCount,
      fearGreed: fgValue,
      northFund: Number(latestNorth?.total ?? latestNorth?.netInflow ?? latestNorth?.net_inflow ?? 0),
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'home.refresh',
        label: '刷新首页总览',
        description: '刷新指数、资金流、风险卡片与告警状态',
        keywords: ['刷新', '首页'],
        scope: 'page' as const,
        pageKey: 'home',
        run: async () => {
          await Promise.allSettled([
            idxQ.refetch(),
            limitUpQ.refetch(),
            northQ.refetch(),
            fearGreedQ.refetch(),
            alertsQ.refetch(),
            riskQ.refetch(),
            newsQ.refetch(),
          ]);
          return { message: '已刷新首页数据' };
        },
      },
      {
        id: 'home.open-risk',
        label: '打开风险巡检',
        description: '跳转到风险页面查看 VaR 与降级状态',
        keywords: ['风险', '巡检'],
        scope: 'page' as const,
        pageKey: 'home',
        run: () => {
          router.push('/risk?lookbackDays=252&from=home');
          return { message: '已打开风险巡检' };
        },
      },
      {
        id: 'home.open-watchlist',
        label: '打开自选股',
        description: '跳转到自选股查看重点标的',
        keywords: ['自选', 'watchlist'],
        scope: 'page' as const,
        pageKey: 'home',
        run: () => {
          router.push('/watchlist');
          return { message: '已打开自选股' };
        },
      },
    ],
    [alertsQ, fearGreedQ, idxQ, limitUpQ, newsQ, northQ, riskQ, router],
  );

  usePageActions(pageActions);

  const summaryTabs = [
    { key: 'market', label: '市场摘要' },
    { key: 'account', label: '账户摘要' },
    { key: 'operations', label: '运行摘要' },
  ] as const;

  const marketSummarySection = (
    <section className={PANEL_CLS}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="eyebrow">市场摘要</div>
          <h3 className="mb-0 mt-2 text-xl font-semibold tracking-[-0.03em] text-text-primary">今天市场在发生什么</h3>
        </div>
        <Link href="/market" className={LINK_CHIP_CLS}>
          去行情页
        </Link>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">情绪温度</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">{fgLabel}</div>
          <div className="mt-1 text-xs text-text-secondary">恐贪 {fgValue.toFixed(0)}</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">北向资金</div>
          <div className={`mt-3 text-lg font-semibold ${latestNorthValue >= 0 ? 'text-danger' : 'text-success'}`}>
            {latestNorthLabel}
          </div>
          <div className="mt-1 text-xs text-text-secondary">最近增量资金方向</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">板块热点</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">{topSectorName}</div>
          <div className={`mt-1 text-xs ${topSectorChange >= 0 ? 'text-danger' : 'text-success'}`}>
            {topSectorChange >= 0 ? '+' : ''}
            {topSectorChange.toFixed(2)}%
          </div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">涨停家数</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">
            {String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}
          </div>
          <div className="mt-1 text-xs text-text-secondary">情绪扩散速度参考</div>
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {validIndices.slice(0, 4).map((item) => {
          const changePercent = Number(item.changePercent ?? item.change_pct ?? 0);
          return (
            <Link
              key={`${item.code}-${item.name}`}
              href={`/market?tab=index&indexCode=${encodeURIComponent(String(item.code || ''))}`}
              className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-3 text-sm no-underline text-inherit"
            >
              <div className="truncate font-medium text-text-primary">{String(item.name ?? item.code ?? '指数')}</div>
              <div className={`mt-1 text-xs ${changePercent >= 0 ? 'text-danger' : 'text-success'}`}>
                {changePercent >= 0 ? '+' : ''}
                {changePercent.toFixed(2)}%
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );

  const accountSummarySection = (
    <section className={PANEL_CLS}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="eyebrow">账户摘要</div>
          <h3 className="mb-0 mt-2 text-xl font-semibold tracking-[-0.03em] text-text-primary">你的资产与跟踪重点</h3>
        </div>
        <Link href="/paper-trading" className={LINK_CHIP_CLS}>
          去模拟交易
        </Link>
      </div>
      <p className="mb-0 mt-3 text-sm leading-7 text-text-secondary">
        欢迎回来，{nickname}。这一块只保留账户状态、自选数量和当前需要优先处理的提醒。
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">总资产</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">
            {fmtAmount(paperSummary.total_value ?? paperAccount.total_value)}
          </div>
          <div className="mt-1 text-xs text-text-secondary">当前资金规模</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">总收益率</div>
          <div
            className={`mt-3 text-lg font-semibold ${Number(paperSummary.total_return_pct ?? 0) >= 0 ? 'text-danger' : 'text-success'}`}
          >
            {Number(paperSummary.total_return_pct ?? 0).toFixed(2)}%
          </div>
          <div className="mt-1 text-xs text-text-secondary">账户表现快照</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">持仓 / 自选</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">
            {paperPositions.length} / {watchlistCount}
          </div>
          <div className="mt-1 text-xs text-text-secondary">同时看仓位和候选标的</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">活跃告警</div>
          <div className={`mt-3 text-lg font-semibold ${activeAlerts.length > 0 ? 'text-danger' : 'text-text-primary'}`}>
            {activeAlerts.length}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            {activeAlerts[0]?.code ? `优先关注 ${String(activeAlerts[0].code)}` : '当前没有活跃告警'}
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href="/watchlist" className={LINK_CHIP_CLS}>
          管理自选股
        </Link>
        <Link href={primaryStockCode ? `/stock?code=${encodeURIComponent(primaryStockCode)}` : '/stock'} className={LINK_CHIP_CLS}>
          打开重点个股
        </Link>
        <Link href="/alerts?status=active" className={LINK_CHIP_CLS}>
          查看告警
        </Link>
      </div>
    </section>
  );

  const operationsSummarySection = (
    <section className={PANEL_CLS}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="eyebrow">运行摘要</div>
          <h3 className="mb-0 mt-2 text-xl font-semibold tracking-[-0.03em] text-text-primary">风险、策略与系统是否稳定</h3>
        </div>
        <Link href="/risk?lookbackDays=252&from=home" className={LINK_CHIP_CLS}>
          去风险中心
        </Link>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">风险状态</div>
          <div className={`mt-3 text-lg font-semibold ${riskStatusLabel === '正常' ? 'text-text-primary' : 'text-danger'}`}>
            {riskStatusLabel}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            {riskEmpty ? '还没有可巡检持仓' : riskSource.mode ? `来源 ${String(riskSource.mode)}` : '查看 VaR 与压测'}
          </div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">策略订阅</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">{user ? strategySubs.length : '-'}</div>
          <div className="mt-1 text-xs text-text-secondary">
            {user ? (strategySubs.length > 0 ? '已建立策略跟踪' : '还没有订阅策略') : '登录后显示'}
          </div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">首页模块</div>
          <div className={`mt-3 text-lg font-semibold ${moduleErrorCount > 0 ? 'text-danger' : 'text-text-primary'}`}>
            {moduleErrorCount > 0 ? `${moduleErrorCount} 个异常` : '运行正常'}
          </div>
          <div className="mt-1 text-xs text-text-secondary">模块加载与接口状态摘要</div>
        </div>
        <div className="metric-tile rounded-[22px] p-4">
          <div className="metric-label">市场异动</div>
          <div className="mt-3 text-lg font-semibold text-text-primary">{marketAnomalies[0]?.title ?? '暂无重点'}</div>
          <div className="mt-1 text-xs text-text-secondary">{marketAnomalies[0]?.value ?? '等待交易时段或刷新'}</div>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <div className={NOTE_CARD_CLS}>
          {strategySubs[0]?.name
            ? `最近订阅策略：${String(strategySubs[0].name ?? strategySubs[0].strategy_name ?? '-')}`
            : '策略、风险和系统状态的完整内容已收进下方标签页。'}
        </div>
        <div className={NOTE_CARD_CLS}>
          {healthQ.error ? '健康接口当前存在异常，可在下方运行与风险页继续排查。' : '健康状态、模块配置和系统细节不再默认占据首页首屏。'}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href="/strategy-market?from=home" className={LINK_CHIP_CLS}>
          去策略超市
        </Link>
        <Link href="/alerts?status=active&from=home" className={LINK_CHIP_CLS}>
          去告警中心
        </Link>
        <Link href="/backtest?from=home" className={LINK_CHIP_CLS}>
          去回测分析
        </Link>
      </div>
    </section>
  );

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <PageContainer className="app-theme-market space-y-4">
      <section className="page-hero p-4 sm:p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,23vw,360px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-primary/15 bg-white/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
                AIASK
              </span>
              <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1 text-xs text-text-primary">
                A 股投研平台
              </span>
              <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1 text-xs text-text-primary">
                市场 · 研究 · 策略 · 交易
              </span>
            </div>
            <h1 className="mb-0 mt-4 text-[1.9rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.2rem]">
              一个覆盖市场、研究、策略与交易的智能股票分析平台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              AIASK 面向 A 股场景提供市场观察、研究分析、策略验证、模拟交易和风险管理的一体化能力。首页默认只保留平台介绍和少量核心摘要，详细的市场、自选、策略和系统模块都收进下方标签页与折叠区。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link href="/market?task=watchlist-scan&from=home" className={HERO_PRIMARY_BUTTON_CLS}>
                进入行情看板
              </Link>
              <Link href="/research?from=home" className={HERO_SECONDARY_BUTTON_CLS}>
                查看研究中心
              </Link>
              <Link href="/strategy-market?from=home" className={HERO_SECONDARY_BUTTON_CLS}>
                浏览策略超市
              </Link>
              <AskAiButton
                stockCode={primaryStockCode}
                prompt="请概括 AIASK 首页当前展示的市场、研究、策略和风险重点"
                label="AI 解读首页"
              />
            </div>

            <div className="mt-5">
              <div className="eyebrow">核心能力</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {visibleHeroCapabilities.map((item, index) => (
                <div
                  key={item.title}
                  className={`rounded-[22px] border border-white/45 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] ${
                    index === 0
                      ? 'bg-white/38'
                      : index === 1
                        ? 'bg-white/32'
                        : index === 2
                          ? 'bg-white/28'
                          : 'bg-white/24'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[14px] border border-white/55 bg-white/45 text-base shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
                      {item.icon}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-text-primary">{item.title}</div>
                      <div className="mt-1 text-xs leading-6 text-text-secondary">{item.meta}</div>
                    </div>
                  </div>
                </div>
              ))}
              </div>
              {hiddenHeroCapabilities.length > 0 ? (
                <details className="mt-3 rounded-[20px] border border-white/45 bg-white/24 px-4 py-3">
                  <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开剩余能力</summary>
                  <div className="mt-3 grid gap-3">
                    {hiddenHeroCapabilities.map((item) => (
                      <div key={item.title} className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-3">
                        <div className="text-sm font-medium text-text-primary">{item.title}</div>
                        <div className="mt-1 text-xs leading-6 text-text-secondary">{item.meta}</div>
                      </div>
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
          </div>

          {compactHome ? (
            <details className={PANEL_CLS}>
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开平台概览与入口</summary>
              <div className="mt-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">平台概览</div>
                <p className="mt-3 text-sm leading-7 text-text-secondary">
                  AIASK 提供统一的投研平台体验，而不是分散的单页工具。你可以在这里连续完成观察、研究、验证和跟踪。
                </p>
                <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">常用入口</div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {visibleHeroEntryLinks.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="metric-tile flex items-center gap-2 rounded-[18px] px-3 py-2.5 no-underline text-inherit"
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] border border-white/55 bg-white/42 text-sm">
                        {item.icon}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-text-primary">{item.title}</div>
                        <div className="text-[11px] text-text-secondary">{item.description}</div>
                      </div>
                    </Link>
                  ))}
                </div>
                <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前运行概况</div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {visibleHeroRuntimeCards.map((item) => (
                    <div key={item.label} className="rounded-[18px] border border-white/45 bg-white/28 px-3 py-2.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
                      <div className={`mt-1.5 text-sm font-medium ${item.tone}`}>{item.value}</div>
                      <div className="mt-1 text-[11px] text-text-secondary">{item.hint}</div>
                    </div>
                  ))}
                </div>
                <details className="mt-3 rounded-[18px] border border-white/45 bg-white/24 px-3 py-3">
                  <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开更多平台说明</summary>
                  <div className="mt-3 space-y-3">
                    {heroHighlights.map((note) => (
                      <div key={note} className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-2 text-xs text-text-secondary">
                        {note}
                      </div>
                    ))}
                    {hiddenHeroEntryLinks.length > 0 ? (
                      <div className="grid grid-cols-2 gap-2">
                        {hiddenHeroEntryLinks.map((item) => (
                          <Link
                            key={item.href}
                            href={item.href}
                            className="metric-tile flex items-center gap-2 rounded-[18px] px-3 py-2.5 no-underline text-inherit"
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] border border-white/55 bg-white/42 text-sm">
                              {item.icon}
                            </span>
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-text-primary">{item.title}</div>
                              <div className="text-[11px] text-text-secondary">{item.description}</div>
                            </div>
                          </Link>
                        ))}
                      </div>
                    ) : null}
                    {hiddenHeroRuntimeCards.length > 0 ? (
                      <div className="grid grid-cols-2 gap-2">
                        {hiddenHeroRuntimeCards.map((item) => (
                          <div key={item.label} className="rounded-[18px] border border-white/45 bg-white/28 px-3 py-2.5">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
                            <div className={`mt-1.5 text-sm font-medium ${item.tone}`}>{item.value}</div>
                            <div className="mt-1 text-[11px] text-text-secondary">{item.hint}</div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </details>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                    去模拟交易
                  </Link>
                  <Link href="/portfolio" className={LINK_CHIP_CLS}>
                    去组合管理
                  </Link>
                  <Link href="/watchlist" className={LINK_CHIP_CLS}>
                    去自选股
                  </Link>
                </div>
                <div className="mt-3 text-xs text-text-secondary">当前时间 {displayDateStr || '等待同步'}</div>
              </div>
            </details>
          ) : (
          <div className={PANEL_CLS}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">平台概览</div>
            <p className="mt-3 text-sm leading-7 text-text-secondary">
              AIASK 提供统一的投研平台体验，而不是分散的单页工具。你可以在这里连续完成观察、研究、验证和跟踪。
            </p>
            <div className="mt-4 space-y-2">
              {heroHighlights.map((note) => (
                <div key={note} className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-2 text-xs text-text-secondary">
                  {note}
                </div>
              ))}
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">常用入口</div>
            <div className="mt-3 grid grid-cols-2 gap-2">
                {heroEntryLinks.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="metric-tile flex items-center gap-2 rounded-[18px] px-3 py-2.5 no-underline text-inherit transition hover:-translate-y-0.5"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] border border-white/55 bg-white/42 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
                      {item.icon}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-text-primary">{item.title}</div>
                      <div className="text-[11px] text-text-secondary">{item.description}</div>
                    </div>
                  </Link>
                ))}
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前运行概况</div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {heroRuntimeCards.map((item) => (
                <div key={item.label} className="rounded-[18px] border border-white/45 bg-white/28 px-3 py-2.5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
                  <div className={`mt-1.5 text-sm font-medium ${item.tone}`}>{item.value}</div>
                  <div className="mt-1 text-[11px] text-text-secondary">{item.hint}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                去模拟交易
              </Link>
              <Link href="/portfolio" className={LINK_CHIP_CLS}>
                去组合管理
              </Link>
              <Link href="/watchlist" className={LINK_CHIP_CLS}>
                去自选股
              </Link>
            </div>
            <div className="mt-3 text-xs text-text-secondary">当前时间 {displayDateStr || '等待同步'}</div>
          </div>
          )}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="eyebrow">核心摘要</div>
            <h2 className="mb-0 mt-2 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary">
              首页默认只展示 3 块关键信息
            </h2>
            <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
              先回答今天的市场状态、你的账户情况，以及当前需要注意的风险与运行状态。完整行情、自选、资讯和系统细节放到下面再展开。
            </p>
          </div>
          <span className="text-xs text-text-secondary">其余模块已收纳到折叠区</span>
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          {compactHome ? (
            <div className="space-y-3 xl:col-span-3">
              <TabBar tabs={summaryTabs} active={summaryTab} onChange={setSummaryTab} />
              {summaryTab === 'market' ? marketSummarySection : null}
              {summaryTab === 'account' ? accountSummarySection : null}
              {summaryTab === 'operations' ? operationsSummarySection : null}
            </div>
          ) : (
            <>
              {marketSummarySection}
              {accountSummarySection}
              {operationsSummarySection}
            </>
          )}
        </div>
      </section>

      {/* ── 完整模块：标签页 + 折叠区 ── */}
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-2 rounded-[16px] border border-border bg-surface px-4 py-3 text-sm font-medium text-text-secondary hover:bg-surface-alt">
          <span className="transition-transform group-open:rotate-90">▶</span>
          <span>展开完整首页模块</span>
        </summary>
        <div className="mt-3 space-y-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="eyebrow">完整模块</div>
              <h2 className="mb-0 mt-2 text-[1.5rem] font-semibold tracking-[-0.03em] text-text-primary">把长内容放到这里再展开</h2>
              <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                首页默认不再平铺完整仪表盘。需要时再切到对应标签查看详细市场、自选、风险和系统模块。
              </p>
            </div>
            <TabBar<HomeDetailsTab> tabs={detailTabs} active={detailTab} onChange={setDetailTab} />
          </div>

          {detailTab === 'market' ? (
            <div className="space-y-4">
              <MarketOverview
                mounted={mounted}
                dateStr={displayDateStr}
                lastUpdated={lastUpdated}
                fgValue={fgValue}
                luStats={luStats}
                latestNorth={latestNorth}
                fmtAmount={fmtAmount}
                dashboardVisibility={dashboardVisibility}
                idxQ={idxQ}
                validIndices={validIndices}
                INDEX_CODES={INDEX_CODES}
                sectorQ={sectorQ}
                sectors={sectors}
              />
              <FundFlowSection
                dashboardVisibility={dashboardVisibility}
                fmtAmount={fmtAmount}
                fearGreedQ={fearGreedQ}
                fgValue={fgValue}
                fgLabel={fgLabel}
                sectorFlowQ={sectorFlowQ}
                sectorFlows={sectorFlows}
                limitUpQ={limitUpQ}
                luStats={luStats}
                northQ={northQ}
                latestNorth={latestNorth}
                northFlows={northFlows}
              />
            </div>
          ) : null}

          {detailTab === 'personal' ? (
            <div className="space-y-4">
              <PersonalSecondaryCards
                watchlistItems={hydratedWatchlistItems}
                paperPositions={paperPositions}
                marketNews={marketNews}
                quoteMap={quoteMap}
              />
              <WatchlistRecent
                mounted={mounted}
                watchlistItems={hydratedWatchlistItems}
                recentStocks={hydratedRecentStocks}
                quoteMap={quoteMap}
                batchQIsFetching={batchQ.isFetching}
              />
            </div>
          ) : null}

          {detailTab === 'operations' ? (
            <div className="space-y-4">
              <DashboardCards
                mounted={mounted}
                dashboardVisibility={dashboardVisibility}
                dashboardCards={dashboardCards}
                marketAnomalies={marketAnomalies}
                anomalyDegraded={anomalyDegraded}
              />
              <SystemStatus
                moduleStatuses={moduleStatuses}
                showDashboardSettings={showDashboardSettings}
                setShowDashboardSettings={setShowDashboardSettings}
                dashboardVisibility={dashboardVisibility}
                toggleDashboardModule={toggleDashboardModule}
                healthQ={healthQ}
                health={health}
                mcp={mcp}
              />
            </div>
          ) : null}
        </div>
      </details>
    </PageContainer>
  );
}
