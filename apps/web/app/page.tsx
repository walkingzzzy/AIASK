'use client';

import { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge, Skeleton, SkeletonCard, QuickAction, QuickActionGrid } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractObject, extractArray, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { BFF_BASE } from '@/lib/api';
import { ErrorState, EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import Link from 'next/link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useWatchlistStore } from '@/store/watchlist-store';
import { useStockContext } from '@/store/stock-context';
import { tradingInterval, isTradingHours } from '@/lib/trading-hours';
import { useAuthStore } from '@/store/auth-store';
import { useDashboardPrefs, DASHBOARD_MODULES } from '@/hooks/use-dashboard-prefs';
import type { DashboardModuleKey } from '@/hooks/use-dashboard-prefs';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';

const poll = tradingInterval(60_000);
const slowPoll = tradingInterval(180_000);

const INDEX_CODES = ['000001', '399001', '399006', '000688'] as const;

export default function HomePage() {
  const [dateStr, setDateStr] = useState('');
  const [mounted, setMounted] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [showDashboardSettings, setShowDashboardSettings] = useState(false);

  const liveRefetch = pageVisible ? poll : false;
  const lazyRefetch = pageVisible ? slowPoll : false;

  const idxQ = useApiQuery<unknown>(
    '/market/batch-quotes',
    {
      enabled: mounted,
      refetchInterval: liveRefetch,
      placeholderData: 'keepPrevious',
      body: { codes: INDEX_CODES },
      parse: (raw) => ensureRecordOrArray(raw, '首页指数批量'),
    },
  );
  const limitUpQ = useApiQuery<unknown>('/market/limit-up-stats', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (raw) => ensureRecord(raw, '涨停统计'),
  });
  const northQ = useApiQuery<unknown>('/fund-flow/north', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (raw) => ensureRecordOrArray(raw, '北向资金'),
  });
  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', {
    enabled: mounted,
    refetchInterval: liveRefetch,
    placeholderData: 'keepPrevious',
    parse: (raw) => ensureRecord(raw, '恐慌贪婪指数'),
  });
  const healthQ = useApiQuery<unknown>('/health/mcp', { enabled: mounted });
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile', { enabled: mounted, parse: (raw) => ensureRecord(raw, '用户配置') });
  const paperSummaryQ = useApiQuery<Record<string, unknown>>('/paper-trading/summary', { enabled: mounted, parse: (raw) => ensureRecord(raw, '模拟盘概览(首页)') });
  const paperPositionsQ = useApiQuery<unknown>('/paper-trading/positions', { enabled: mounted, parse: (raw) => ensureRecordOrArray(raw, '模拟盘持仓(首页)') });
  const marketNewsQ = useApiQuery<unknown>('/research/market-news?limit=5', { enabled: mounted, parse: (raw) => ensureRecordOrArray(raw, '市场快讯(首页)') });
  const { visibility: dashboardVisibility, toggle: toggleDashboardModule } = useDashboardPrefs(mounted, profileQ);
  const sectorQ = useApiQuery<unknown>('/market/blocks?blockType=industry&limit=20', { enabled: mounted && dashboardVisibility.market, refetchInterval: lazyRefetch, placeholderData: 'keepPrevious', parse: (raw) => ensureRecordOrArray(raw, '板块行情(首页)') });
  const sectorFlowQ = useApiQuery<unknown>('/fund-flow/sector', { enabled: mounted && dashboardVisibility['fund-flow'], refetchInterval: lazyRefetch, placeholderData: 'keepPrevious', parse: (raw) => ensureRecordOrArray(raw, '板块资金流(首页)') });
  const alertsQ = useApiQuery<unknown>('/alerts/list?status=active', { enabled: mounted && dashboardVisibility.alerts, parse: (raw) => ensureRecordOrArray(raw, '活跃预警(首页)') });
  const riskQ = useApiQuery<unknown>('/risk/summary?lookbackDays=252', {
    enabled: mounted && dashboardVisibility.risk,
    parse: (raw) => ensureRecord(raw, '风险汇总(首页)'),
  });
  const user = useAuthStore((s) => s.user);
  const strategyUserId = user?.id ?? user?.username ?? null;
  const strategySubsQ = useApiQuery<unknown>(
    strategyUserId ? `/strategy-market/my-subscriptions?user_id=${encodeURIComponent(strategyUserId)}` : null,
    { enabled: mounted && dashboardVisibility.strategy && Boolean(strategyUserId), parse: (raw) => ensureRecordOrArray(raw, '策略订阅(首页)') },
  );
  const watchlistItems = useWatchlistStore((s) => s.groups.flatMap((g) => g.items));
  const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
  const recentStocks = useStockContext((s) => s.recent);

  // Sync watchlist from server on mount
  useEffect(() => { syncFromServer(); }, [syncFromServer]);

  // ── WS real-time quotes ──
  const wsQuotesRef = useRef<Map<string, Record<string, unknown>>>(new Map());
  const [wsQuoteTick, setWsQuoteTick] = useState(0);

  const handleWsQuote = useCallback((data: QuoteData) => {
    wsQuotesRef.current.set(data.code, data as Record<string, unknown>);
    setWsQuoteTick((t) => t + 1);
  }, []);

  useQuoteSubscription({
    codes: [...INDEX_CODES],
    type: 'index',
    onUpdate: handleWsQuote,
  });

  // Collect unique codes from watchlist + recent for batch quote
  const quoteCodes = useMemo(() => {
    const set = new Set<string>();
    watchlistItems.forEach((i) => set.add(i.code));
    recentStocks.slice(0, 8).forEach((i) => set.add(i.code));
    return Array.from(set);
  }, [watchlistItems, recentStocks]);
  const batchQ = useApiQuery<unknown>(
    quoteCodes.length > 0 ? '/market/batch-quotes' : null,
    { enabled: mounted && pageVisible, refetchInterval: lazyRefetch, body: { codes: quoteCodes }, placeholderData: 'keepPrevious' },
  );
  const quoteMap = useMemo(() => {
    const m = new Map<string, Record<string, unknown>>();
    const arr = extractArray(batchQ.data, 'quotes', 'items', 'data');
    arr.forEach((q) => { const c = String(q.code ?? ''); if (c) m.set(c, q); });
    return m;
  }, [batchQ.data]);

  useEffect(() => {
    setMounted(true);

    const updateDate = () => {
      setDateStr(new Date().toLocaleString('zh-CN', { hour12: false }));
    };
    updateDate();
    const timer = window.setInterval(updateDate, 60_000);

    const handleVisibilityChange = () => {
      setPageVisible(document.visibilityState === 'visible');
    };
    handleVisibilityChange();
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const lastUpdated = idxQ.dataUpdatedAt ? new Date(idxQ.dataUpdatedAt) : null;

  const indices = useMemo(() => {
    const arr = extractArray(idxQ.data, 'quotes', 'items', 'data');
    if (arr.length > 0) return arr.map((d) => { const o = extractObject(d); return o.quote ? extractObject(o.quote) : o; }).filter((o) => o.code || o.name);
    // fallback: single object with nested quote
    const obj = extractObject(idxQ.data);
    return obj.code || obj.name ? [obj.quote ? extractObject(obj.quote) : obj] : [];
  }, [idxQ.data]);
  const validIndices = useMemo(
    () => indices.filter((o) => Number.isFinite(Number(o.price ?? o.close ?? o.current))),
    [indices],
  );
  const luStats = extractObject(limitUpQ.data);
  const northFlows = extractArray(northQ.data, 'items', 'flows');
  const latestNorth = northFlows.length
    ? [...northFlows].sort((a, b) => String(a.date ?? a.tradeDate ?? '').localeCompare(String(b.date ?? b.tradeDate ?? '')))[northFlows.length - 1]
    : null;
  const fgRaw = extractObject(fearGreedQ.data);
  const fgObj = (fgRaw.result && typeof fgRaw.result === 'object')
    ? extractObject((fgRaw.result as Record<string, unknown>)) : fgRaw;
  const fgValue = Number(fgObj.index ?? fgObj.value ?? fgObj.fear_greed_index ?? 50);
  const fgLabel = fgValue <= 25 ? '极度恐惧' : fgValue <= 40 ? '恐惧' : fgValue <= 60 ? '中性' : fgValue <= 75 ? '贪婪' : '极度贪婪';

  const sectors = useMemo(() => extractArray(sectorQ.data, 'blocks', 'items', 'data'), [sectorQ.data]);
  const sectorFlows = useMemo(() => {
    const raw = extractArray(sectorFlowQ.data, 'flows', 'items', 'data');
    const mapped = raw.slice(0, 10).map((x) => ({
      label: String(x.name ?? x.sector ?? '').slice(0, 6),
      value: Number(x.netInflow ?? x.net_inflow ?? x.main_net_inflow ?? 0),
    }));
    // If all values are 0 (all netInflow null), treat as no data
    return mapped.some((m) => m.value !== 0) ? mapped : [];
  }, [sectorFlowQ.data]);

  const health = healthQ.data as Record<string, unknown> | null;
  const mcp = (health?.mcp ?? {}) as Record<string, unknown>;

  const activeAlerts = useMemo(() => extractArray(alertsQ.data, 'items', 'alerts', 'data'), [alertsQ.data]);
  const paperSummary = useMemo(() => extractObject(paperSummaryQ.data), [paperSummaryQ.data]);
  const paperAccount = useMemo(() => extractObject(paperSummary.account), [paperSummary]);
  const paperPositions = useMemo(() => extractArray(paperPositionsQ.data, 'positions', 'items', 'data'), [paperPositionsQ.data]);
  const marketNews = useMemo(() => extractArray(marketNewsQ.data, 'items', 'news', 'data'), [marketNewsQ.data]);
  const riskSummary = useMemo(() => extractObject(riskQ.data), [riskQ.data]);
  const riskDegraded = Boolean(riskSummary.degraded);
  const riskModuleStatusRaw = extractObject(riskSummary.moduleStatus);
  const riskModuleStatus = {
    var: extractObject(riskModuleStatusRaw.var),
    stress: extractObject(riskModuleStatusRaw.stress),
    exposure: extractObject(riskModuleStatusRaw.exposure),
  };
  const strategySubs = useMemo(() => extractArray(strategySubsQ.data, 'strategies', 'items', 'data'), [strategySubsQ.data]);

  const moduleStatuses = useMemo(() => {
    const marketErr = Boolean(idxQ.error || sectorQ.error);
    const marketLoading = idxQ.isFetching || sectorQ.isFetching;
    const flowErr = Boolean(northQ.error || sectorFlowQ.error);
    const flowLoading = northQ.isFetching || sectorFlowQ.isFetching;
    const alertsErr = Boolean(alertsQ.error);
    const alertsLoading = alertsQ.isFetching;
    const sentimentErr = Boolean(fearGreedQ.error);
    const sentimentLoading = fearGreedQ.isFetching;
    const strategyErr = Boolean(strategySubsQ.error);
    const strategyLoading = strategySubsQ.isFetching;
    const riskErr = Boolean(riskQ.error || riskDegraded);
    const riskLoading = riskQ.isFetching;

    return {
      market: marketErr ? 'error' : marketLoading ? 'loading' : 'ok',
      'fund-flow': flowErr ? 'error' : flowLoading ? 'loading' : 'ok',
      alerts: alertsErr ? 'error' : alertsLoading ? 'loading' : 'ok',
      sentiment: sentimentErr ? 'error' : sentimentLoading ? 'loading' : 'ok',
      strategy: strategyErr ? 'error' : strategyLoading ? 'loading' : 'ok',
      risk: riskErr ? 'error' : riskLoading ? 'loading' : 'ok',
    } as Record<DashboardModuleKey, 'ok' | 'loading' | 'error'>;
  }, [
    idxQ.error, sectorQ.error,
    idxQ.isFetching, sectorQ.isFetching,
    northQ.error, sectorFlowQ.error, northQ.isFetching, sectorFlowQ.isFetching,
    alertsQ.error, alertsQ.isFetching,
    fearGreedQ.error, fearGreedQ.isFetching,
    strategySubsQ.error, strategySubsQ.isFetching,
    riskQ.error, riskQ.isFetching, riskDegraded,
  ]);

  const quickActions = useMemo(() => {
    const defaultCode = recentStocks[0]?.code || watchlistItems[0]?.code || '600519';
    return [
      {
        href: '/market?task=watchlist-scan&from=home',
        icon: '📈',
        title: '盘中看盘',
        description: '直达行情看板并聚焦任务流',
      },
      {
        href: `/stock?code=${encodeURIComponent(defaultCode)}&task=stock-review&from=home`,
        icon: '🔍',
        title: '个股复盘',
        description: `优先打开 ${defaultCode}`,
      },
      {
        href: '/risk?lookbackDays=252&from=home',
        icon: '🛡️',
        title: '风险巡检',
        description: '查看 VaR 与降级状态',
      },
      {
        href: '/strategy-market?task=ranking&from=home',
        icon: '🧪',
        title: '策略筛选',
        description: '进入策略超市排名页',
      },
      {
        href: `/backtest?code=${encodeURIComponent(defaultCode)}&from=home`,
        icon: '📊',
        title: '快速回测',
        description: '带代码进入回测分析',
      },
    ];
  }, [recentStocks, watchlistItems]);

  const marketAnomalies = useMemo(() => {
    const limitUpCount = Number(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? 0);
    const topSector = sectors[0] ?? null;
    const flowTop = sectorFlows[0] ?? null;
    const out: Array<{ title: string; value: string; href: string; tone: 'danger' | 'success' | 'info' | 'warning' }> = [];
    if (limitUpCount > 0) {
      out.push({
        title: '涨停家数',
        value: `${limitUpCount} 家`,
        href: '/market?tab=limitup&from=home',
        tone: limitUpCount >= 80 ? 'danger' : 'warning',
      });
    }
    if (topSector) {
      const chg = Number(topSector.avgChange ?? topSector.avg_change ?? topSector.change_pct ?? 0);
      out.push({
        title: `板块热力 · ${String(topSector.name ?? '行业')}`,
        value: `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`,
        href: `/market?tab=blocks&block=${encodeURIComponent(String(topSector.code ?? ''))}&from=home`,
        tone: chg >= 0 ? 'danger' : 'success',
      });
    }
    if (flowTop) {
      out.push({
        title: `资金流向 · ${flowTop.label}`,
        value: fmtAmount(flowTop.value),
        href: '/fund-flow?from=home',
        tone: flowTop.value >= 0 ? 'danger' : 'success',
      });
    }
    if (latestNorth) {
      const val = Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? 0);
      out.push({
        title: '北向净流入',
        value: fmtAmount(val),
        href: '/fund-flow?from=home',
        tone: val >= 0 ? 'danger' : 'success',
      });
    }
    return out.slice(0, 4);
  }, [luStats, sectors, sectorFlows, latestNorth]);

  const anomalyDegraded = Boolean(limitUpQ.error || sectorQ.error || sectorFlowQ.error || northQ.error);

  const dashboardCards = useMemo(() => [
    {
      key: 'risk' as const,
      title: '风险巡检',
      pending: riskQ.isPending,
      error: riskQ.error,
      content: (
        <KpiGrid cols={3}>
          <KpiCard title="组合ID" value={String(riskSummary.portfolioId ?? '-')} />
          <KpiCard title="回看天数" value={String(riskSummary.lookbackDays ?? '-')} />
          <KpiCard title="降级状态" value={riskDegraded ? '是' : '否'} />
        </KpiGrid>
      ),
      empty: !riskSummary.lookbackDays,
      href: '/risk?lookbackDays=252&from=home',
      footer: (
        <div className="mt-2 text-xs text-text-secondary">
          VaR: {riskModuleStatus.var?.ok === false ? '异常' : '正常'} ｜ 压测: {riskModuleStatus.stress?.ok === false ? '异常' : '正常'} ｜ 暴露: {riskModuleStatus.exposure?.ok === false ? '异常' : '正常'}
        </div>
      ),
    },
    {
      key: 'strategy' as const,
      title: '策略动态',
      pending: strategyUserId ? strategySubsQ.isPending : false,
      error: strategyUserId ? strategySubsQ.error : null,
      content: (
        <KpiGrid cols={3}>
          <KpiCard title="订阅策略" value={strategySubs.length} />
          <KpiCard title="活跃用户" value={user?.username ?? '-'} />
          <KpiCard title="状态" value={strategyUserId ? (strategySubs.length > 0 ? '已订阅' : '待订阅') : '未登录'} />
        </KpiGrid>
      ),
      empty: strategyUserId ? strategySubs.length === 0 : false,
      href: '/strategy-market?from=home',
      footer: strategyUserId
        ? (strategySubs.length > 0
          ? <div className="mt-2 text-xs text-text-secondary">最近订阅：{String(strategySubs[0]?.name ?? strategySubs[0]?.strategy_name ?? '-')}</div>
          : null)
        : <div className="mt-2 text-xs text-text-secondary">登录后可查看你的订阅策略动态</div>,
    },
    {
      key: 'alerts' as const,
      title: '告警中心',
      pending: alertsQ.isPending,
      error: alertsQ.error,
      content: (
        <KpiGrid cols={3}>
          <KpiCard title="活跃告警" value={activeAlerts.length} />
          <KpiCard title="今日重点" value={activeAlerts[0]?.code ? String(activeAlerts[0]?.code) : '-'} />
          <KpiCard title="告警状态" value={activeAlerts.length > 0 ? '运行中' : '空'} />
        </KpiGrid>
      ),
      empty: activeAlerts.length === 0,
      href: '/alerts?status=active&from=home',
      footer: activeAlerts.length > 0 ? (
        <div className="mt-2 text-xs text-text-secondary">示例：{String(activeAlerts[0]?.indicator ?? '-')} {String(activeAlerts[0]?.condition ?? '')} {String(activeAlerts[0]?.value ?? '')}</div>
      ) : null,
    },
  ], [
    riskQ.isPending, riskQ.error, riskSummary, riskDegraded, riskModuleStatus,
    strategySubsQ.isPending, strategySubsQ.error, strategySubs, strategyUserId, user,
    alertsQ.isPending, alertsQ.error, activeAlerts,
  ]);


  useEffect(() => {
    document.title = '市场概览 | AIASK';
    return () => { document.title = 'AIASK 智能股票分析'; };
  }, []);

  return (
    <PageContainer>
      <div className="mb-4">
        <h1 className="mb-1">欢迎回来，{String(profileQ.data?.nickname ?? user?.nickname ?? user?.username ?? '投资者')}</h1>
        <div className="text-sm text-text-secondary">这里会优先展示你的资产、自选、告警和市场快讯。</div>
      </div>

      <div data-tour="dashboard">
        <SectionCard className="p-4 mb-4">
          <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
            <h3 className="mt-0 mb-0">个人总览</h3>
            <Link href="/paper-trading" className="text-xs text-primary no-underline">进入模拟盘</Link>
          </div>
          <KpiGrid cols={4}>
            <KpiCard title="总资产" value={fmtAmount(paperSummary.total_value ?? paperAccount.total_value)} />
            <KpiCard title="总收益率" value={fmtPct(paperSummary.total_return_pct ?? 0)} change={Number(paperSummary.total_return_pct ?? 0)} />
            <KpiCard title="持仓数" value={paperPositions.length} />
            <KpiCard title="活跃告警" value={activeAlerts.length} />
          </KpiGrid>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <SectionCard className="p-4 lg:col-span-1">
          <div className="flex items-center justify-between mb-2">
            <h3 className="mt-0 mb-0">自选股行情</h3>
            <Link href="/watchlist" className="text-xs text-primary no-underline">更多</Link>
          </div>
          <div className="space-y-1.5">
            {watchlistItems.slice(0, 5).map((item) => {
              const q = quoteMap.get(item.code);
              const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
              return <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30"><StockLink code={item.code} name={item.name || item.code} /><span className={chg >= 0 ? 'text-danger text-xs' : 'text-success text-xs'}>{q ? `${fmtNum(q.price, 2)} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '--'}</span></div>;
            })}
            {watchlistItems.length === 0 ? <EmptyState text="暂无自选股" /> : null}
          </div>
        </SectionCard>
        <SectionCard className="p-4 lg:col-span-1">
          <div className="flex items-center justify-between mb-2">
            <h3 className="mt-0 mb-0">持仓概览</h3>
            <Link href="/paper-trading" className="text-xs text-primary no-underline">更多</Link>
          </div>
          <div className="space-y-1.5">
            {paperPositions.slice(0, 5).map((item, i) => <div key={String(item.stock_code ?? i)} className="flex items-center justify-between text-sm py-1 border-b border-border/30"><StockLink code={String(item.stock_code ?? '')} name={String(item.stock_name ?? item.stock_code ?? '')} /><span className={Number(item.profit_rate ?? 0) >= 0 ? 'text-danger text-xs' : 'text-success text-xs'}>{fmtPct(item.profit_rate ?? 0)}</span></div>)}
            {paperPositions.length === 0 ? <EmptyState text="暂无持仓" /> : null}
          </div>
        </SectionCard>
        <SectionCard className="p-4 lg:col-span-1">
          <div className="flex items-center justify-between mb-2">
            <h3 className="mt-0 mb-0">市场快讯</h3>
            <Link href="/research" className="text-xs text-primary no-underline">更多</Link>
          </div>
          <div className="space-y-2">
            {marketNews.slice(0, 5).map((item, i) => <div key={String(item.id ?? item.title ?? i)} className="text-sm pb-2 border-b border-border/30"><div className="font-medium line-clamp-2">{String(item.title ?? item.name ?? '未命名快讯')}</div><div className="text-xs text-text-secondary mt-1">{String(item.publish_time ?? item.time ?? item.date ?? '-')}</div></div>)}
            {marketNews.length === 0 ? <EmptyState text="暂无市场快讯" /> : null}
          </div>
        </SectionCard>
      </div>

      {/* Market Pulse Bar */}
      <div className="glass rounded-xl p-4 mb-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isTradingHours() ? 'bg-success animate-pulse' : 'bg-text-muted'}`} />
          <span className="text-sm font-medium">{isTradingHours() ? '交易中' : '已休市'}</span>
          <span className="text-xs text-text-muted">
            {dateStr}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-text-secondary">
          {lastUpdated && <span>更新: {lastUpdated.toLocaleTimeString('zh-CN')}</span>}
          <span>恐贪: <span className={fgValue > 60 ? 'text-danger font-medium' : fgValue < 40 ? 'text-success font-medium' : 'font-medium'}>{fgValue.toFixed(0)}</span></span>
          <span>涨停: <span className="font-medium">{String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}</span></span>
          <span>北向: <span className={Number(latestNorth?.total ?? latestNorth?.netInflow ?? 0) >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>{fmtAmount(latestNorth?.total ?? latestNorth?.netInflow)}</span></span>
        </div>
      </div>

      {/* Module Status + Settings */}
      <SectionCard className="p-4 mb-4">
        <div className="flex items-center justify-between gap-3 mb-2">
          <h3 className="mt-0 mb-0">模块状态</h3>
          <button
            type="button"
            onClick={() => setShowDashboardSettings((v) => !v)}
            className="text-xs px-2 py-1 rounded border border-border cursor-pointer"
          >
            {showDashboardSettings ? '收起模块配置' : '配置首页模块'}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {DASHBOARD_MODULES.map((m) => {
            const status = moduleStatuses[m.key];
            const variant = status === 'ok' ? 'success' : status === 'loading' ? 'warning' : 'danger';
            const text = status === 'ok' ? '正常' : status === 'loading' ? '加载中' : '异常';
            return (
              <Badge key={m.key} variant={variant}>{m.label}: {text}</Badge>
            );
          })}
        </div>
        {showDashboardSettings ? (
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2">
            {DASHBOARD_MODULES.map((m) => (
              <label key={m.key} className="text-xs text-text-secondary flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={dashboardVisibility[m.key]}
                  onChange={() => toggleDashboardModule(m.key)}
                />
                {m.label}
              </label>
            ))}
          </div>
        ) : null}
      </SectionCard>

      {/* Task-flow Quick Actions */}
      <SectionCard className="p-4 mb-4">
        <h3 className="mt-0">任务流入口</h3>
        <QuickActionGrid cols={5}>
          {quickActions.map((a) => (
            <QuickAction key={a.href} href={a.href} icon={a.icon} title={a.title} description={a.description} />
          ))}
        </QuickActionGrid>
      </SectionCard>

      {/* Personal workbench cards */}
      {mounted ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {dashboardCards
            .filter((c) => dashboardVisibility[c.key])
            .map((card) => (
              <SectionCard key={card.key} className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="mt-0 mb-0">{card.title}</h3>
                  <Link href={card.href} className="text-xs text-primary no-underline">查看详情</Link>
                </div>
                {card.error ? <ErrorState text={card.error} />
                  : card.pending ? <KpiGrid cols={3}><SkeletonCard /><SkeletonCard /><SkeletonCard /></KpiGrid>
                    : card.empty ? <EmptyState text="暂无可展示数据" />
                      : card.content}
                {card.footer}
              </SectionCard>
            ))}
        </div>
      ) : null}

      {/* Market anomaly feed */}
      <SectionCard className="p-4 mb-4">
        <h3 className="mt-0">市场异动榜</h3>
        {anomalyDegraded && marketAnomalies.length > 0 && (
          <div className="text-xs text-warning mb-2">部分数据源不可用，异动信息可能不完整</div>
        )}
        {marketAnomalies.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {marketAnomalies.map((item) => (
              <Link key={`${item.title}-${item.href}`} href={item.href} className="glass rounded-lg px-3 py-2 no-underline text-inherit flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{item.title}</div>
                  <div className={`text-xs ${item.tone === 'danger' ? 'text-danger' : item.tone === 'success' ? 'text-success' : item.tone === 'warning' ? 'text-warning' : 'text-primary'}`}>{item.value}</div>
                </div>
                <span className="text-xs text-text-secondary">查看</span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState text="暂无异动数据" />
        )}
      </SectionCard>

      {/* Multi-Index Quotes */}
      {dashboardVisibility['market'] && <SectionCard className="p-4">
        <h3 className="mt-0">主要指数</h3>
        {idxQ.error ? <ErrorState text={idxQ.error} onRetry={() => idxQ.refetch()} /> : null}
        {validIndices.length > 0 ? (
          <KpiGrid cols={4}>
            {validIndices.map((q, i) => {
              const chg = Number(q.changePercent ?? q.change_pct ?? q.changePct ?? 0);
              const chgAmt = Number(q.change ?? 0);
              return (
                <Link key={i} href={`/market?indexCode=${String(q.code ?? INDEX_CODES[i])}`} className="no-underline text-inherit">
                  <KpiCard
                    title={String(q.name ?? q.index_name ?? q.code ?? `指数${i + 1}`)}
                    value={fmtNum(q.price ?? q.close ?? q.current, 2)}
                    suffix={chgAmt ? ' ' + (chgAmt > 0 ? '+' : '') + fmtNum(chgAmt, 2) : undefined}
                    change={chg}
                    changeType="percent"
                  />
                </Link>
              );
            })}
          </KpiGrid>
        ) : idxQ.isPending ? (
          <KpiGrid cols={4}>
            <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
          </KpiGrid>
        ) : !idxQ.error ? (
          <EmptyState text="主要指数暂无可用行情" />
        ) : null}
      </SectionCard>}

      {/* Sector Heatmap */}
      {dashboardVisibility['market'] && <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">板块热力</h3>
        {sectorQ.error ? <ErrorState text={sectorQ.error} onRetry={() => sectorQ.refetch()} /> : null}
        {sectors.length > 0 ? (
          <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
            {sectors.map((s, i) => {
              const chg = Number(s.avgChange ?? s.avg_change ?? s.change_pct ?? 0);
              return (
                <Link key={i} href={`/market?tab=blocks&block=${encodeURIComponent(String(s.code ?? s.block_code ?? ''))}`}
                  className={`glass rounded-lg p-2 text-center text-xs no-underline text-inherit ${chg >= 0 ? 'border border-danger/30' : 'border border-success/30'} transition-transform hover:scale-105`}
                  aria-label={`${String(s.name ?? '')} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}>
                  <div className="truncate font-medium">{String(s.name ?? '').slice(0, 6)}</div>
                  <div className={`text-sm font-bold ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</div>
                </Link>
              );
            })}
          </div>
        ) : sectorQ.isPending ? (
          <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
            {Array.from({ length: 20 }).map((_, i) => (
              <Skeleton key={i} height={52} />
            ))}
          </div>
        ) : !sectorQ.error ? <EmptyState text="暂无板块热力数据" /> : null}
      </SectionCard>}

      {/* Fear-Greed + Sector Fund Flow side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['sentiment'] && <SectionCard className="p-4">
          <h3 className="mt-0">恐贪指数</h3>
          {fearGreedQ.error ? <ErrorState text={fearGreedQ.error} onRetry={() => fearGreedQ.refetch()} /> : null}
          {fearGreedQ.data != null ? (
            <GaugeChart
              value={fgValue}
              min={0}
              max={100}
              title={fgLabel}
              height={200}
              zones={[
                { start: 0, end: 25, color: COLORS.down },
                { start: 25, end: 40, color: COLORS.warning },
                { start: 40, end: 60, color: '#94a3b8' },
                { start: 60, end: 75, color: '#f97316' },
                { start: 75, end: 100, color: COLORS.up },
              ]}
            />
          ) : fearGreedQ.isPending ? <Skeleton height={200} /> : !fearGreedQ.error ? <EmptyState text="暂无恐贪数据" /> : null}
        </SectionCard>}

        {dashboardVisibility['fund-flow'] && <SectionCard className="p-4">
          <h3 className="mt-0">板块资金流向</h3>
          {sectorFlowQ.error ? <ErrorState text={sectorFlowQ.error} onRetry={() => sectorFlowQ.refetch()} /> : null}
          {sectorFlows.length > 0 ? (
            <BarChart items={sectorFlows} height={200} yAxisName="净流入(亿)" colorByValue horizontal />
          ) : sectorFlowQ.isPending ? <Skeleton height={200} /> : !sectorFlowQ.error ? <EmptyState text="暂无板块资金流向" /> : null}
        </SectionCard>}
      </div>

      {/* Limit-Up Stats + North Fund side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        {dashboardVisibility['market'] && <SectionCard className="p-4">
          <h3 className="mt-0">涨停统计</h3>
          {limitUpQ.error ? <ErrorState text={limitUpQ.error} onRetry={() => limitUpQ.refetch()} /> : null}
          {limitUpQ.data ? (
            <>
              <KpiGrid cols={3}>
                <KpiCard title="涨停家数" value={String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')} />
                <KpiCard title="首板" value={String(luStats.firstBoard ?? luStats.first_board ?? '-')} />
                <KpiCard title="连板成功率" value={fmtPct(luStats.successRate ?? luStats.success_rate)} />
              </KpiGrid>
              {Number(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? 0) === 0 && (
                <p className="text-text-muted text-xs mt-2">盘前/盘后数据为零属正常现象</p>
              )}
            </>
          ) : limitUpQ.isPending ? (
            <KpiGrid cols={3}>
              <SkeletonCard /><SkeletonCard /><SkeletonCard />
            </KpiGrid>
          ) : !limitUpQ.error ? <EmptyState text="暂无涨停统计数据" /> : null}
        </SectionCard>}

        {dashboardVisibility['fund-flow'] && <SectionCard className="p-4">
          <h3 className="mt-0">北向资金</h3>
          {northQ.error ? <ErrorState text={northQ.error} onRetry={() => northQ.refetch()} /> : null}
          {latestNorth ? (
            <KpiGrid cols={2}>
              <KpiCard
                title="今日净流入"
                value={fmtAmount(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow)}
                change={Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? null)}
                changeType="absolute"
              />
              <KpiCard title="累计净流入" value={fmtAmount(latestNorth.cumulative ?? latestNorth.cumNetInflow ?? latestNorth.cum_net_inflow)} />
            </KpiGrid>
          ) : northQ.isPending ? (
            <KpiGrid cols={2}>
              <SkeletonCard /><SkeletonCard />
            </KpiGrid>
          ) : !northQ.error ? <EmptyState text="暂无北向资金数据（非交易时段）" /> : null}
        </SectionCard>}
      </div>

      {/* North Fund Trend */}
      {dashboardVisibility['fund-flow'] && <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">北向资金走势（近20日）</h3>
        {northFlows.length > 1 ? (
          <BarChart
            items={northFlows.slice(-20).map((x) => ({
              label: String(x.date ?? '').slice(5),
              value: Number(x.total ?? x.netInflow ?? x.net_inflow ?? 0) / 1e8,
            }))}
            height={240}
            yAxisName="净流入(亿)"
            colorByValue
          />
        ) : northQ.isPending ? <Skeleton height={240} /> : <EmptyState text="暂无北向资金走势（非交易时段）" />}
      </SectionCard>}

      {/* Watchlist + Recent Stocks */}
      {mounted && (watchlistItems.length > 0 || recentStocks.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          {watchlistItems.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">我的自选 ({watchlistItems.length})</h3>
              <div className="space-y-1.5">
                {watchlistItems.slice(0, 8).map((item) => {
                  const q = quoteMap.get(item.code);
                  const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
                  return (
                    <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                      <StockLink code={item.code} name={item.name || item.code} />
                      <div className="flex items-center gap-2">
                        {q ? <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                          : batchQ.isFetching ? <Skeleton width={80} height={16} /> : null}
                        <WatchlistButton code={item.code} name={item.name} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}
          {recentStocks.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">最近查看</h3>
              <div className="space-y-1.5">
                {recentStocks.slice(0, 8).map((item) => {
                  const q = quoteMap.get(item.code);
                  const chg = Number(q?.changePercent ?? q?.change_pct ?? 0);
                  return (
                    <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                      <StockLink code={item.code} name={item.name ? `${item.name} ${item.code}` : item.code} />
                      {q ? <span className={`text-xs font-medium ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{fmtNum(q.price, 2)} {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                        : batchQ.isFetching ? <Skeleton width={80} height={16} />
                          : <span className="text-xs text-text-muted">{new Date(item.ts).toLocaleDateString('zh-CN')}</span>}
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}
        </div>
      )}

      <details className="mt-6">
        <summary className="cursor-pointer text-text-secondary text-sm">BFF / MCP 健康状态</summary>
        <SectionCard className="p-4 mt-2">
          {healthQ.error ? <ErrorState text={healthQ.error} onRetry={() => healthQ.refetch()} />
            : healthQ.isPending ? <Skeleton height={60} />
              : health ? (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>服务: <Badge variant={String(health.status) === 'ok' ? 'success' : 'warning'}>{String(health.status ?? '-')}</Badge></div>
                  <div>MCP: <Badge variant={mcp.reachable ? 'success' : 'danger'}>{mcp.reachable ? '已连接' : '未连接'}</Badge></div>
                  <div>工具数: {String(mcp.toolCount ?? '-')} / {String(mcp.expectedTools ?? '-')}</div>
                  <div>匹配: <Badge variant={mcp.matched ? 'success' : 'warning'}>{String(mcp.matched ?? '-')}</Badge></div>
                </div>
              ) : <EmptyState text={`暂无健康数据：${BFF_BASE}`} />}
        </SectionCard>
      </details>
    </PageContainer>
  );
}
