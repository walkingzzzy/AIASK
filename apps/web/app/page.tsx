'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import { PageContainer, KpiCard, KpiGrid } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { extractObject, extractArray, fmtAmount } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
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
import { PersonalDashboard, WatchlistRecent } from '@/components/home/PersonalDashboard';
import { FundFlowSection } from '@/components/home/FundFlowSection';
import { DashboardCards } from '@/components/home/DashboardCards';
import type { DashboardCard } from '@/components/home/DashboardCards';
import { SystemStatus } from '@/components/home/SystemStatus';
import type {
  AlertItem,
  DashboardMarketAnomaly,
  DashboardMarketNewsItem,
  DashboardMarketNewsResponse,
  DashboardQuickAction,
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
  const [dateStr, setDateStr] = useState('');
  const [pageVisible, setPageVisible] = useState(() =>
    typeof document === 'undefined' ? true : document.visibilityState === 'visible',
  );
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
    document.title = '市场概览 | AIASK';
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
  const quickActions = useMemo<DashboardQuickAction[]>(() => {
    const dc = mounted ? primaryStockCode || '600519' : '600519';
    return [
      {
        href: '/market?task=watchlist-scan&from=home',
        icon: '📈',
        title: '盘中看盘',
        description: '直达行情看板并聚焦任务流',
      },
      {
        href: `/stock?code=${encodeURIComponent(dc)}&task=stock-review&from=home`,
        icon: '🔍',
        title: '个股复盘',
        description: `优先打开 ${dc}`,
      },
      { href: '/risk?lookbackDays=252&from=home', icon: '🛡️', title: '风险巡检', description: '查看 VaR 与降级状态' },
      {
        href: '/strategy-market?task=ranking&from=home',
        icon: '🧪',
        title: '策略筛选',
        description: '进入策略超市排名页',
      },
      {
        href: `/backtest?code=${encodeURIComponent(dc)}&from=home`,
        icon: '📊',
        title: '快速回测',
        description: '带代码进入回测分析',
      },
    ];
  }, [mounted, primaryStockCode]);
  const latestNorthValue = Number(latestNorth?.total ?? latestNorth?.netInflow ?? latestNorth?.net_inflow ?? 0);
  const latestNorthLabel = latestNorth ? fmtAmount(latestNorthValue) : '暂无数据';
  const priorityActions = quickActions.slice(0, 4);
  const heroNotes = [
    `优先先看 ${fgLabel}、指数和北向流向，再决定是去行情、风险还是策略页继续深入。`,
    activeAlertCount > 0
      ? `当前有 ${activeAlertCount} 条活跃告警，首页不建议停留过久，最好尽快回到对应工作流处理。`
      : '当前没有活跃告警，适合把时间留给市场轮动、板块热力和自选复盘。',
    `最近更新 ${lastUpdated ? lastUpdated.toLocaleTimeString('zh-CN') : '暂无刷新记录'}，如果你要做即时判断，建议先手动刷新一次首页数据。`,
  ];

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

  const anomalyDegraded = Boolean(limitUpQ.error || sectorQ.error || sectorFlowQ.error || northQ.error);
  const nickname = String(profileQ.data?.nickname ?? user?.nickname ?? user?.username ?? '投资者');

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
    title: '首页总览',
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

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <PageContainer className="app-theme-market space-y-4">
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-primary/15 bg-white/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">
                Home Workspace
              </span>
              <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1 text-xs text-text-primary">
                {fgLabel}
              </span>
              <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1 text-xs text-text-primary">
                {activeAlertCount > 0 ? `${activeAlertCount} 条活跃告警` : '当前无活跃告警'}
              </span>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              首页总览工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              首页现在不再只是卡片堆叠入口，而是统一的起始工作台。先看情绪、指数、资金和异常，再决定下一步进入行情、自选、风险还是策略路径，让首页真正承担“分发动作”的职责。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <AskAiButton
                stockCode={primaryStockCode}
                prompt="请总结今日市场状态、主要指数和需要关注的信号"
                label="AI 市场晨会"
              />
              <Link href="/market?task=watchlist-scan&from=home" className={HERO_PRIMARY_BUTTON_CLS}>
                去行情看板
              </Link>
              <Link href="/watchlist" className={HERO_SECONDARY_BUTTON_CLS}>
                打开自选股
              </Link>
              <Link href="/risk?lookbackDays=252&from=home" className={HERO_SECONDARY_BUTTON_CLS}>
                风险巡检
              </Link>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前时间</div>
                <div className="mt-3 text-base font-semibold text-text-primary">{displayDateStr || '等待同步'}</div>
                <div className="mt-1 text-xs text-text-secondary">用于判断行情节奏与刷新时点</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">市场异动</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{marketAnomalies.length}</div>
                <div className="mt-1 text-xs text-text-secondary">今日值得优先查看的异常线索</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">北向资金</div>
                <div className={`mt-3 text-xl font-semibold ${latestNorthValue >= 0 ? 'text-danger' : 'text-success'}`}>
                  {latestNorthLabel}
                </div>
                <div className="mt-1 text-xs text-text-secondary">帮助判断增量资金强弱</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">自选池</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{watchlistCount}</div>
                <div className="mt-1 text-xs text-text-secondary">和首页行情联动的重点标的数量</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">今日优先动作</div>
              <div className="mt-4 grid gap-2">
                {priorityActions.map((action) => (
                  <Link
                    key={action.href}
                    href={action.href}
                    className="metric-tile flex items-center gap-3 rounded-[22px] px-3 py-3 no-underline text-inherit transition hover:-translate-y-0.5"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[14px] border border-white/55 bg-white/42 text-base shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
                      {action.icon}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-text-primary">{action.title}</div>
                      <div className="text-xs text-text-secondary">{action.description}</div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">操作提示</div>
              <div className="mt-4 space-y-3">
                {heroNotes.map((note) => (
                  <div key={note} className={NOTE_CARD_CLS}>
                    {note}
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/research" className={LINK_CHIP_CLS}>
                  去研究页
                </Link>
                <Link href="/strategy-market" className={LINK_CHIP_CLS}>
                  去策略超市
                </Link>
                <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                  去模拟交易
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="eyebrow">Market Workspace</div>
            <h2 className="mb-0 mt-2 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary">
              指数、板块与资金脉冲
            </h2>
            <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
              市场总览区继续承接首页的主阅读链路。先看情绪与交易状态，再看主要指数和板块热力，让“今天市场在哪里变化”在同一段视觉路径里被回答。
            </p>
          </div>
          <Link href="/market" className={LINK_CHIP_CLS}>
            打开完整行情工作台
          </Link>
        </div>
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
      </div>

      {/* ── 第二屏：持仓/自选 + 风险/策略/告警 ── */}
      <PersonalDashboard
        nickname={nickname}
        paperSummary={paperSummary}
        paperAccount={paperAccount}
        paperPositions={paperPositions}
        activeAlerts={activeAlerts}
        watchlistItems={hydratedWatchlistItems}
        recentStocks={hydratedRecentStocks}
        quoteMap={quoteMap}
        batchQIsFetching={batchQ.isFetching}
        mounted={mounted}
        marketNews={marketNews}
        quickActions={quickActions}
      />
      <DashboardCards
        mounted={mounted}
        dashboardVisibility={dashboardVisibility}
        dashboardCards={dashboardCards}
        marketAnomalies={marketAnomalies}
        anomalyDegraded={anomalyDegraded}
      />

      {/* ── 第三屏（折叠区）：资金流、自选近期、系统状态 ── */}
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-2 rounded-[16px] border border-border bg-surface px-4 py-3 text-sm font-medium text-text-secondary hover:bg-surface-alt">
          <span className="transition-transform group-open:rotate-90">▶</span>
          <span>更多数据 · 资金流向、自选动态、系统状态</span>
        </summary>
        <div className="mt-3 space-y-4">
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
          <WatchlistRecent
            mounted={mounted}
            watchlistItems={hydratedWatchlistItems}
            recentStocks={hydratedRecentStocks}
            quoteMap={quoteMap}
            batchQIsFetching={batchQ.isFetching}
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
      </details>
    </PageContainer>
  );
}
