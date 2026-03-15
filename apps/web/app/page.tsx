'use client';

import Link from 'next/link';
import { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import { PageContainer, KpiCard, KpiGrid } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractObject, extractArray, fmtAmount } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { tradingInterval } from '@/lib/trading-hours';
import { useAuthStore } from '@/store/auth-store';
import { useDashboardPrefs } from '@/hooks/use-dashboard-prefs';
import { useHydrated } from '@/hooks/use-hydrated';
import type { DashboardModuleKey } from '@/hooks/use-dashboard-prefs';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';
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
  const mounted = useHydrated();
  const [dateStr, setDateStr] = useState('');
  const [pageVisible, setPageVisible] = useState(() => (typeof document === 'undefined' ? true : document.visibilityState === 'visible'));
  const [showDashboardSettings, setShowDashboardSettings] = useState(false);
  const liveRefetch = pageVisible ? poll : false;
  const lazyRefetch = pageVisible ? slowPoll : false;

  /* ── Data queries ─────────────────────────────────────────────── */
  const idxQ       = useApiQuery<unknown>('/market/index-batch-quotes', { enabled: mounted, refetchInterval: liveRefetch, placeholderData: 'keepPrevious', body: { codes: INDEX_CODES }, parse: (r) => ensureRecordOrArray(r, '首页指数批量') });
  const limitUpQ   = useApiQuery<unknown>('/market/limit-up-stats', { enabled: mounted, refetchInterval: liveRefetch, placeholderData: 'keepPrevious', parse: (r) => ensureRecord(r, '涨停统计') });
  const northQ     = useApiQuery<unknown>('/fund-flow/north', { enabled: mounted, refetchInterval: liveRefetch, placeholderData: 'keepPrevious', parse: (r) => ensureRecordOrArray(r, '北向资金') });
  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', { enabled: mounted, refetchInterval: liveRefetch, placeholderData: 'keepPrevious', parse: (r) => ensureRecord(r, '恐慌贪婪指数') });
  const healthQ    = useApiQuery<unknown>('/health/mcp', { enabled: mounted });
  const profileQ   = useApiQuery<Record<string, unknown>>('/auth/profile', { enabled: mounted, parse: (r) => ensureRecord(r, '用户配置') });
  const paperSumQ  = useApiQuery<PaperTradingSummary>('/paper-trading/summary', { enabled: mounted, parse: (r) => ensureRecord(r, '模拟盘概览(首页)') as PaperTradingSummary });
  const paperPosQ  = useApiQuery<PaperTradingPositionsResponse>('/paper-trading/positions', { enabled: mounted, parse: normalizePaperPositionsPayload });
  const newsQ      = useApiQuery<DashboardMarketNewsResponse>('/research/market-news?limit=5', { enabled: mounted, parse: normalizeMarketNewsPayload });

  const { visibility: dashboardVisibility, toggle: toggleDashboardModule } = useDashboardPrefs(mounted, profileQ);

  const sectorQ     = useApiQuery<unknown>('/market/blocks?blockType=industry&limit=20', { enabled: mounted && dashboardVisibility.market, refetchInterval: lazyRefetch, placeholderData: 'keepPrevious', parse: (r) => ensureRecordOrArray(r, '板块行情(首页)') });
  const sectorFlowQ = useApiQuery<unknown>('/fund-flow/sector', { enabled: mounted && dashboardVisibility['fund-flow'], refetchInterval: lazyRefetch, placeholderData: 'keepPrevious', parse: (r) => ensureRecordOrArray(r, '板块资金流(首页)') });
  const alertsQ     = useApiQuery<{ items?: AlertItem[] }>('/alerts/list?status=active', { enabled: mounted && dashboardVisibility.alerts, parse: normalizeAlertsPayload });
  const riskQ       = useApiQuery<unknown>('/risk/summary?lookbackDays=252', { enabled: mounted && dashboardVisibility.risk, parse: (r) => ensureRecord(r, '风险汇总(首页)') });

  const user = useAuthStore((s) => s.user);
  const strategySubsQ = useApiQuery<unknown>(
    user ? '/strategy-market/my-subscriptions' : null,
    { enabled: mounted && dashboardVisibility.strategy && Boolean(user), parse: (r) => ensureRecordOrArray(r, '策略订阅(首页)') },
  );

  const watchlistItems = useWatchlistStore((s) => s.groups.flatMap((g) => g.items));
  const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
  const recentStocks = useStockContext((s) => s.recent);
  useEffect(() => { syncFromServer(); }, [syncFromServer]);

  /* ── WS real-time quotes ─────────────────────────────────────── */
  const wsQuotesRef = useRef<Map<string, DashboardQuoteSnapshot>>(new Map());
  const [, setWsQuoteTick] = useState(0);
  const handleWsQuote = useCallback((data: QuoteData) => { wsQuotesRef.current.set(data.code, data as DashboardQuoteSnapshot); setWsQuoteTick((t) => t + 1); }, []);
  useQuoteSubscription({ codes: [...INDEX_CODES], type: 'index', onUpdate: handleWsQuote });

  const quoteCodes = useMemo(() => { const s = new Set<string>(); watchlistItems.forEach((i) => s.add(i.code)); recentStocks.slice(0, 8).forEach((i) => s.add(i.code)); return Array.from(s); }, [watchlistItems, recentStocks]);
  const batchQ = useApiQuery<unknown>(quoteCodes.length > 0 ? '/market/batch-quotes' : null, { enabled: mounted && pageVisible, refetchInterval: lazyRefetch, body: { codes: quoteCodes }, placeholderData: 'keepPrevious' });
  const quoteMap = useMemo(() => { const m = new Map<string, DashboardQuoteSnapshot>(); extractArray(batchQ.data, 'quotes', 'items', 'data').forEach((q) => { const c = String(q.code ?? ''); if (c) m.set(c, q as DashboardQuoteSnapshot); }); return m; }, [batchQ.data]);

  /* ── Lifecycle ─────────────────────────────────────────────────── */
  useEffect(() => {
    const updateDate = () => setDateStr(new Date().toLocaleString('zh-CN', { hour12: false }));
    updateDate();
    const timer = window.setInterval(updateDate, 60_000);
    const onVis = () => setPageVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVis); };
  }, []);
  useEffect(() => { document.title = '市场概览 | AIASK'; return () => { document.title = 'AIASK 智能股票分析'; }; }, []);

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
  const latestNorth = northFlows.length ? [...northFlows].sort((a, b) => String(a.date ?? a.tradeDate ?? '').localeCompare(String(b.date ?? b.tradeDate ?? '')))[northFlows.length - 1] : null;
  const fgRaw = extractObject(fearGreedQ.data);
  const fgObj = (fgRaw.result && typeof fgRaw.result === 'object') ? extractObject(fgRaw.result as Record<string, unknown>) : fgRaw;
  const fgValue = Number(fgObj.index ?? fgObj.value ?? fgObj.fear_greed_index ?? 50);
  const fgLabel = fgValue <= 25 ? '极度恐惧' : fgValue <= 40 ? '恐惧' : fgValue <= 60 ? '中性' : fgValue <= 75 ? '贪婪' : '极度贪婪';
  const sectors = useMemo(() => extractArray(sectorQ.data, 'blocks', 'items', 'data'), [sectorQ.data]);
  const sectorFlows = useMemo(() => { const raw = extractArray(sectorFlowQ.data, 'flows', 'items', 'data'); const mapped = raw.slice(0, 10).map((x) => ({ label: String(x.name ?? x.sector ?? '').slice(0, 6), value: Number(x.netInflow ?? x.net_inflow ?? x.main_net_inflow ?? 0) })); return mapped.some((m) => m.value !== 0) ? mapped : []; }, [sectorFlowQ.data]);
  const health = healthQ.data as Record<string, unknown> | null;
  const mcp = (health?.mcp ?? {}) as Record<string, unknown>;
  const activeAlerts = useMemo<AlertItem[]>(() => alertsQ.data?.items ?? [], [alertsQ.data]);
  const paperSummary = useMemo(() => (paperSumQ.data ?? {}) as PaperTradingSummary, [paperSumQ.data]);
  const paperAccount = useMemo(() => (paperSummary.account ?? {}) as NonNullable<PaperTradingSummary['account']>, [paperSummary]);
  const paperPositions = useMemo<PaperTradingPosition[]>(() => paperPosQ.data?.positions ?? [], [paperPosQ.data]);
  const marketNews = useMemo<DashboardMarketNewsItem[]>(() => newsQ.data?.items ?? [], [newsQ.data]);
  const riskSummary = useMemo(() => extractObject(riskQ.data), [riskQ.data]);
  const riskDegraded = Boolean(riskSummary.degraded);
  const riskEmpty = Boolean(riskSummary.empty);
  const riskMs = useMemo(() => { const raw = extractObject(riskSummary.moduleStatus); return { var: extractObject(raw.var), stress: extractObject(raw.stress), exposure: extractObject(raw.exposure) }; }, [riskSummary]);
  const riskSource = extractObject(riskSummary.sourceContext);
  const strategySubs = useMemo(() => extractArray(strategySubsQ.data, 'strategies', 'items', 'data'), [strategySubsQ.data]);

  /* ── Module statuses ──────────────────────────────────────────── */
  const moduleStatuses = useMemo(() => {
    const st = (err: boolean, loading: boolean) => err ? 'error' as const : loading ? 'loading' as const : 'ok' as const;
    return {
      market: st(Boolean(idxQ.error || sectorQ.error), idxQ.isFetching || sectorQ.isFetching),
      'fund-flow': st(Boolean(northQ.error || sectorFlowQ.error), northQ.isFetching || sectorFlowQ.isFetching),
      alerts: st(Boolean(alertsQ.error), alertsQ.isFetching),
      sentiment: st(Boolean(fearGreedQ.error), fearGreedQ.isFetching),
      strategy: st(Boolean(strategySubsQ.error), strategySubsQ.isFetching),
      risk: st(Boolean(riskQ.error || riskDegraded), riskQ.isFetching),
    } as Record<DashboardModuleKey, 'ok' | 'loading' | 'error'>;
  }, [idxQ.error, sectorQ.error, idxQ.isFetching, sectorQ.isFetching, northQ.error, sectorFlowQ.error, northQ.isFetching, sectorFlowQ.isFetching, alertsQ.error, alertsQ.isFetching, fearGreedQ.error, fearGreedQ.isFetching, strategySubsQ.error, strategySubsQ.isFetching, riskQ.error, riskQ.isFetching, riskDegraded]);

  /* ── Quick actions & anomalies ────────────────────────────────── */
  const quickActions = useMemo<DashboardQuickAction[]>(() => {
    const dc = mounted ? recentStocks[0]?.code || watchlistItems[0]?.code || '600519' : '600519';
    return [
      { href: '/market?task=watchlist-scan&from=home', icon: '📈', title: '盘中看盘', description: '直达行情看板并聚焦任务流' },
      { href: `/stock?code=${encodeURIComponent(dc)}&task=stock-review&from=home`, icon: '🔍', title: '个股复盘', description: `优先打开 ${dc}` },
      { href: '/risk?lookbackDays=252&from=home', icon: '🛡️', title: '风险巡检', description: '查看 VaR 与降级状态' },
      { href: '/strategy-market?task=ranking&from=home', icon: '🧪', title: '策略筛选', description: '进入策略超市排名页' },
      { href: `/backtest?code=${encodeURIComponent(dc)}&from=home`, icon: '📊', title: '快速回测', description: '带代码进入回测分析' },
    ];
  }, [mounted, recentStocks, watchlistItems]);

  const marketAnomalies = useMemo<DashboardMarketAnomaly[]>(() => {
    const luCount = Number(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? 0);
    const topSec = sectors[0] ?? null;
    const flowTop = sectorFlows[0] ?? null;
    const out: DashboardMarketAnomaly[] = [];
    if (luCount > 0) out.push({ title: '涨停家数', value: `${luCount} 家`, href: '/market?tab=limitup&from=home', tone: luCount >= 80 ? 'danger' : 'warning' });
    if (topSec) { const c = Number(topSec.avgChange ?? topSec.avg_change ?? topSec.change_pct ?? 0); out.push({ title: `板块热力 · ${String(topSec.name ?? '行业')}`, value: `${c >= 0 ? '+' : ''}${c.toFixed(2)}%`, href: `/market?tab=blocks&block=${encodeURIComponent(String(topSec.code ?? ''))}&from=home`, tone: c >= 0 ? 'danger' : 'success' }); }
    if (flowTop) out.push({ title: `资金流向 · ${flowTop.label}`, value: fmtAmount(flowTop.value), href: '/fund-flow?from=home', tone: flowTop.value >= 0 ? 'danger' : 'success' });
    if (latestNorth) { const v = Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? 0); out.push({ title: '北向净流入', value: fmtAmount(v), href: '/fund-flow?from=home', tone: v >= 0 ? 'danger' : 'success' }); }
    return out.slice(0, 4);
  }, [luStats, sectors, sectorFlows, latestNorth]);

  const anomalyDegraded = Boolean(limitUpQ.error || sectorQ.error || sectorFlowQ.error || northQ.error);
  const nickname = String(profileQ.data?.nickname ?? user?.nickname ?? user?.username ?? '投资者');

  /* ── Dashboard cards (risk / strategy / alerts) ───────────────── */
  const dashboardCards: DashboardCard[] = useMemo(() => [
    {
      key: 'risk', title: '风险巡检', pending: riskQ.isPending, error: riskQ.error, empty: riskEmpty, href: '/risk?lookbackDays=252&from=home',
      content: <KpiGrid cols={3}><KpiCard title="组合ID" value={String(riskSummary.portfolioId ?? '-')} /><KpiCard title="回看天数" value={String(riskSummary.lookbackDays ?? '-')} /><KpiCard title="降级状态" value={riskDegraded ? '是' : '否'} /></KpiGrid>,
      emptyText: '还没有可巡检的风险上下文',
      emptyHint: '如果还没有组合或模拟持仓，风险页不会产出有意义的 VaR、压测和暴露结果。',
      emptyAction: (
        <>
          <Link href="/portfolio" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">先建组合</Link>
          <Link href="/paper-trading" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">去模拟盘</Link>
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
      key: 'strategy', title: '策略动态', pending: user ? strategySubsQ.isPending : false, error: user ? strategySubsQ.error : null, empty: user ? strategySubs.length === 0 : false, href: '/strategy-market?from=home',
      content: <KpiGrid cols={3}><KpiCard title="订阅策略" value={strategySubs.length} /><KpiCard title="活跃用户" value={user?.username ?? '-'} /><KpiCard title="状态" value={user ? (strategySubs.length > 0 ? '已订阅' : '待订阅') : '未登录'} /></KpiGrid>,
      emptyText: '还没有订阅任何策略',
      emptyHint: '可以先去策略超市按收益、回撤或风险偏好筛选，再订阅适合你的策略。',
      emptyAction: <Link href="/strategy-market?from=home" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">去策略超市</Link>,
      footer: user ? (strategySubs.length > 0 ? <div className="mt-2 text-xs text-text-secondary">最近订阅：{String(strategySubs[0]?.name ?? strategySubs[0]?.strategy_name ?? '-')}</div> : null) : <div className="mt-2 text-xs text-text-secondary">登录后可查看你的订阅策略动态</div>,
    },
    {
      key: 'alerts', title: '告警中心', pending: alertsQ.isPending, error: alertsQ.error, empty: activeAlerts.length === 0, href: '/alerts?status=active&from=home',
      content: <KpiGrid cols={3}><KpiCard title="活跃告警" value={activeAlerts.length} /><KpiCard title="今日重点" value={activeAlerts[0]?.code ? String(activeAlerts[0]?.code) : '-'} /><KpiCard title="告警状态" value={activeAlerts.length > 0 ? '运行中' : '空'} /></KpiGrid>,
      emptyText: '当前没有活跃告警',
      emptyHint: '如果你在跟踪自选股，建议先配置价格、均线或指标阈值告警，避免盘中反复手动盯盘。',
      emptyAction: <Link href="/alerts?from=home" className="rounded-full border border-primary px-3 py-1 text-xs text-primary no-underline">创建告警</Link>,
      footer: activeAlerts.length > 0 ? <div className="mt-2 text-xs text-text-secondary">示例：{String(activeAlerts[0]?.indicator ?? '-')} {String(activeAlerts[0]?.condition ?? '')} {String(activeAlerts[0]?.value ?? '')}</div> : null,
    },
  ], [riskQ.isPending, riskQ.error, riskSummary, riskDegraded, riskEmpty, riskMs, riskSource, strategySubsQ.isPending, strategySubsQ.error, strategySubs, user, alertsQ.isPending, alertsQ.error, activeAlerts]);

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <PageContainer>
      <PersonalDashboard
        nickname={nickname} paperSummary={paperSummary} paperAccount={paperAccount}
        paperPositions={paperPositions} activeAlerts={activeAlerts} watchlistItems={watchlistItems}
        recentStocks={recentStocks} quoteMap={quoteMap} batchQIsFetching={batchQ.isFetching}
        mounted={mounted} marketNews={marketNews} quickActions={quickActions}
      />
      <MarketOverview
        mounted={mounted} dateStr={dateStr} lastUpdated={lastUpdated} fgValue={fgValue} luStats={luStats}
        latestNorth={latestNorth} fmtAmount={fmtAmount} dashboardVisibility={dashboardVisibility}
        idxQ={idxQ} validIndices={validIndices} INDEX_CODES={INDEX_CODES}
        sectorQ={sectorQ} sectors={sectors}
      />
      <SystemStatus
        moduleStatuses={moduleStatuses} showDashboardSettings={showDashboardSettings}
        setShowDashboardSettings={setShowDashboardSettings} dashboardVisibility={dashboardVisibility}
        toggleDashboardModule={toggleDashboardModule} healthQ={healthQ} health={health} mcp={mcp}
      />
      <DashboardCards
        mounted={mounted} dashboardVisibility={dashboardVisibility} dashboardCards={dashboardCards}
        marketAnomalies={marketAnomalies} anomalyDegraded={anomalyDegraded}
      />
      <FundFlowSection
        dashboardVisibility={dashboardVisibility} fmtAmount={fmtAmount} fearGreedQ={fearGreedQ}
        fgValue={fgValue} fgLabel={fgLabel} sectorFlowQ={sectorFlowQ} sectorFlows={sectorFlows}
        limitUpQ={limitUpQ} luStats={luStats} northQ={northQ} latestNorth={latestNorth} northFlows={northFlows}
      />
      <WatchlistRecent
        mounted={mounted} watchlistItems={watchlistItems} recentStocks={recentStocks}
        quoteMap={quoteMap} batchQIsFetching={batchQ.isFetching}
      />
    </PageContainer>
  );
}
