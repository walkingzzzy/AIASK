'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AccountPerformanceDashboard from '@/app/performance/components/account-performance-dashboard';
import PerformanceContextPanels from '@/app/performance/components/performance-context-panels';
import PerformanceHero from '@/app/performance/components/performance-hero';
import PortfolioAttributionDashboard from '@/app/performance/components/portfolio-attribution-dashboard';
import PerformanceSecondarySidebar from '@/app/performance/components/performance-secondary-sidebar';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  PaperTradingAccountsResponse,
  PaperTradingNavPoint,
  PaperTradingPerformanceMetrics,
  PaperTradingPerformancePoint,
  PaperTradingNavHistoryResponse,
  PaperTradingPerformanceResponse,
  PaperTradingPosition,
  PaperTradingPositionsResponse,
  PaperTradingSummary,
  PerformanceAttributionResponse,
  PerformanceBenchmarkComparisonResponse,
} from '@aiask/shared-types';

type PerformanceMode = 'account' | 'portfolio';
type PerformanceMobilePrimaryTab = 'filters' | 'dashboard';

type PortfolioOption = {
  id: string;
  name: string;
  description: string;
};

const WINDOW_PRESETS = [7, 30, 90, 252] as const;
const MODE_TABS = [
  { key: 'account', label: '账户绩效' },
  { key: 'portfolio', label: '组合归因' },
] as const;
const BENCHMARK_OPTIONS = [
  { code: '000300', label: '沪深300' },
  { code: '000905', label: '中证500' },
  { code: '000852', label: '中证1000' },
  { code: '000001', label: '上证指数' },
] as const;

function clampDays(value: unknown, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.min(Math.max(Math.trunc(parsed), 7), 504);
}

function normalizePortfolioOptions(raw: unknown): PortfolioOption[] {
  return extractArray(raw, 'portfolios')
    .map((item) => {
      const id = String(item.id ?? item.portfolio_id ?? '').trim();
      if (!id) return null;
      return {
        id,
        name: String(item.name ?? `组合 ${id}`),
        description: item.description != null ? String(item.description) : '',
      };
    })
    .filter((item): item is { id: string; name: string; description: string } => item != null);
}

export default function PerformancePage() {
  const router = useRouter();
  const searchParams = useStableSearchParams();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const sourceExecutionId = searchParams.get('execution_id') ?? '';
  const initialMode = (() => {
    const raw = searchParams.get('mode');
    if (raw === 'portfolio' || raw === 'account') return raw;
    return searchParams.get('portfolio_id') ? 'portfolio' : 'account';
  })() satisfies PerformanceMode;

  const [mode, setMode] = useState<PerformanceMode>(initialMode);
  const [accountId, setAccountId] = useState(searchParams.get('account_id') ?? '');
  const [portfolioId, setPortfolioId] = useState(searchParams.get('portfolio_id') ?? '');
  const [benchmark, setBenchmark] = useState(searchParams.get('benchmark') ?? '000300');
  const [days, setDays] = useState<number>(() => {
    const raw = Number(searchParams.get('days') ?? 30);
    return Number.isFinite(raw) && raw > 0 ? raw : 30;
  });
  const [mobilePrimaryTab, setMobilePrimaryTab] = useState<PerformanceMobilePrimaryTab>('filters');
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const contextInitializedRef = useRef(false);
  const collapseToTabs = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  const accountQs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : '';
  const selectedPortfolioId = portfolioId && /^\d+$/.test(portfolioId) ? Number(portfolioId) : null;
  const portfolioLookbackDays = Math.max(days, 20);

  const accountsQ = useApiQuery<PaperTradingAccountsResponse | unknown[]>('/paper-trading/accounts');
  const summaryQ = useApiQuery<PaperTradingSummary>(
    accountQs ? `/paper-trading/summary${accountQs}` : '/paper-trading/summary',
    { enabled: mode === 'account' },
  );
  const positionsQ = useApiQuery<PaperTradingPositionsResponse>(
    accountQs ? `/paper-trading/positions${accountQs}` : '/paper-trading/positions',
    { enabled: mode === 'account' },
  );
  const navQ = useApiQuery<PaperTradingNavHistoryResponse>(
    accountQs ? `/paper-trading/nav-history${accountQs}` : '/paper-trading/nav-history',
    { enabled: mode === 'account' },
  );
  const performanceQ = useApiQuery<PaperTradingPerformanceResponse>(
    `/paper-trading/performance${accountQs ? `${accountQs}&days=${days}` : `?days=${days}`}`,
    { enabled: mode === 'account' },
  );

  const portfoliosQ = useApiQuery<unknown>('/portfolio/list');
  const portfolioDetailQ = useApiQuery<unknown>(
    selectedPortfolioId ? `/portfolio/get?portfolioId=${selectedPortfolioId}` : null,
    { enabled: mode === 'portfolio' && selectedPortfolioId != null },
  );
  const attributionQ = useApiQuery<PerformanceAttributionResponse>(
    selectedPortfolioId
      ? `/performance/attribution?portfolioId=${selectedPortfolioId}&lookbackDays=${portfolioLookbackDays}&benchmark=${encodeURIComponent(benchmark)}`
      : null,
    { enabled: mode === 'portfolio' && selectedPortfolioId != null },
  );
  const benchmarkQ = useApiQuery<PerformanceBenchmarkComparisonResponse>(
    selectedPortfolioId
      ? `/performance/benchmark-comparison?portfolioId=${selectedPortfolioId}&lookbackDays=${portfolioLookbackDays}&benchmark=${encodeURIComponent(benchmark)}`
      : null,
    { enabled: mode === 'portfolio' && selectedPortfolioId != null },
  );

  const accounts = useMemo(
    () => extractArray(accountsQ.data, 'accounts', 'items', 'data') as Array<{ account_id?: string }>,
    [accountsQ.data],
  );
  const portfolios = useMemo(() => normalizePortfolioOptions(portfoliosQ.data), [portfoliosQ.data]);

  useEffect(() => {
    if (mode !== 'portfolio' || portfolios.length === 0) return;
    if (!portfolioId || !portfolios.some((item) => item.id === portfolioId)) {
      const timer = window.setTimeout(() => {
        setPortfolioId(portfolios[0].id);
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [mode, portfolioId, portfolios]);

  useEffect(() => {
    if (!workbenchHydrated) return;

    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (workspaceChanged) {
      contextInitializedRef.current = false;
    }

    if (searchParams.toString()) {
      contextInitializedRef.current = true;
      return;
    }

    if (contextInitializedRef.current) return;
    contextInitializedRef.current = true;

    const deferredUpdates: Array<() => void> = [];
    if (workbenchContext.mode === 'portfolio' || workbenchContext.portfolioId) {
      deferredUpdates.push(() => {
        setMode('portfolio');
        if (workbenchContext.portfolioId) setPortfolioId(workbenchContext.portfolioId);
        if (workbenchContext.benchmark) setBenchmark(workbenchContext.benchmark);
      });
    } else if (workbenchContext.mode === 'account' || workbenchContext.accountId) {
      deferredUpdates.push(() => {
        setMode('account');
        if (workbenchContext.accountId) setAccountId(workbenchContext.accountId);
      });
    }

    if (typeof workbenchContext.days === 'number' && workbenchContext.days > 0) {
      deferredUpdates.push(() => setDays(workbenchContext.days!));
    }
    if (!deferredUpdates.length) return;
    const timer = window.setTimeout(() => {
      deferredUpdates.forEach((apply) => apply());
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeWorkspaceId, searchParams, workbenchContext, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated || !contextInitializedRef.current) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set('mode', mode);
    params.set('days', String(days));

    if (mode === 'account') {
      if (accountId) params.set('account_id', accountId);
      else params.delete('account_id');
      params.delete('portfolio_id');
      params.delete('benchmark');
    } else {
      if (portfolioId) params.set('portfolio_id', portfolioId);
      else params.delete('portfolio_id');
      params.set('benchmark', benchmark);
      params.delete('account_id');
    }

    const nextQs = params.toString();
    if (nextQs !== searchParams.toString()) {
      router.replace(`/performance?${nextQs}`, { scroll: false });
    }
  }, [accountId, benchmark, days, mode, portfolioId, router, searchParams, workbenchHydrated]);

  const selectedPortfolio = useMemo(
    () => portfolios.find((item) => item.id === portfolioId) ?? null,
    [portfolioId, portfolios],
  );
  const portfolioDetail = useMemo(() => extractObject(portfolioDetailQ.data), [portfolioDetailQ.data]);
  const portfolioHoldings = useMemo(() => extractArray(portfolioDetailQ.data, 'holdings'), [portfolioDetailQ.data]);

  const positions = useMemo(() => positionsQ.data?.positions ?? [], [positionsQ.data]);
  const navData = useMemo(() => navQ.data?.nav ?? [], [navQ.data]);
  const performanceData = useMemo(() => performanceQ.data?.dailyReturns ?? [], [performanceQ.data]);
  const accountMetrics = performanceQ.data?.metrics ?? {};
  const totalValue = Number(summaryQ.data?.total_value ?? summaryQ.data?.account?.total_value ?? 0);
  const totalReturnPct = Number(summaryQ.data?.total_return_pct ?? 0);
  const topPositions = useMemo(
    () => [...positions].sort((a, b) => Number(b.market_value ?? 0) - Number(a.market_value ?? 0)).slice(0, 8),
    [positions],
  );
  const navCategories = useMemo(() => navData.map((item) => String(item.nav_date ?? '').slice(5)), [navData]);
  const navValues = useMemo(() => navData.map((item) => Number(item.total_value ?? 0)), [navData]);
  const perfCategories = useMemo(
    () => performanceData.map((item) => String(item.date ?? '').slice(5)),
    [performanceData],
  );
  const perfReturns = useMemo(
    () => performanceData.map((item) => Number(item.dailyReturn ?? 0) * 100),
    [performanceData],
  );

  const attribution = attributionQ.data;
  const benchmarkComparison = benchmarkQ.data;
  const attributionByStock = useMemo(() => attribution?.attributionByStock ?? [], [attribution?.attributionByStock]);
  const sectorPerformance = useMemo(() => attribution?.sectorPerformance ?? [], [attribution?.sectorPerformance]);
  const waterfallData = useMemo(
    () => [
      { name: '个股选择', value: Number(attribution?.attribution?.stockSelection?.contribution ?? 0) },
      { name: '行业配置', value: Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0) },
      { name: '择时', value: Number(attribution?.attribution?.timing?.contribution ?? 0) },
    ],
    [
      attribution?.attribution?.sectorAllocation?.contribution,
      attribution?.attribution?.stockSelection?.contribution,
      attribution?.attribution?.timing?.contribution,
    ],
  );
  const sectorBarItems = useMemo(
    () => sectorPerformance.slice(0, 8).map((item) => ({ label: item.sector, value: Number(item.returnPct ?? 0) })),
    [sectorPerformance],
  );
  const portfolioName =
    attribution?.portfolioName ||
    selectedPortfolio?.name ||
    (selectedPortfolioId ? `组合 ${selectedPortfolioId}` : '未选择组合');
  const portfolioTotalAssets = Number(portfolioDetail.totalAssets ?? portfolioDetail.currentValue ?? 0);
  const portfolioTotalReturnPct = Number(attribution?.totalReturnPct ?? portfolioDetail.totalReturn ?? 0);
  const portfolioMessage = attribution?.message ?? benchmarkComparison?.message ?? null;
  const outperformance = benchmarkComparison?.outperformance === true;
  const isAccountMode = mode === 'account';
  const selectedBenchmark = useMemo(
    () => BENCHMARK_OPTIONS.find((item) => item.code === benchmark) ?? null,
    [benchmark],
  );
  const attributionSorted = useMemo(
    () => [...attributionByStock].sort((a, b) => Number(b.contributionPct ?? 0) - Number(a.contributionPct ?? 0)),
    [attributionByStock],
  );
  const topContributor = attributionSorted[0] ?? null;
  const weakContributor = useMemo(
    () =>
      [...attributionByStock].sort((a, b) => Number(a.contributionPct ?? 0) - Number(b.contributionPct ?? 0))[0] ??
      null,
    [attributionByStock],
  );
  const accountLeader = topPositions[0] ?? null;
  const focusStockCode = useMemo(
    () => String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? '').trim(),
    [accountLeader?.stock_code, isAccountMode, topContributor?.code],
  );
  const portfolioNarrative = useMemo(() => {
    if (isAccountMode) {
      const accountLeadCode = String(accountLeader?.stock_code ?? '').trim();
      const accountLeadName = String(accountLeader?.stock_name ?? accountLeadCode).trim();
      if (!accountLeadCode) {
        return '当前账户还没有足够持仓，先形成稳定持仓后，净值、回撤和绩效指标才有持续复盘意义。';
      }
      return `当前账户更适合从持仓绩效回看。领先持仓为 ${accountLeadName || accountLeadCode}，可以直接跳个股详情或研究页，再对照风险中心看收益是否建立在可接受回撤上。`;
    }

    const topCode = String(topContributor?.code ?? '').trim();
    const weakCode = String(weakContributor?.code ?? '').trim();
    const benchmarkLabel = selectedBenchmark?.label ?? benchmark;
    if (!topCode && !weakCode) {
      return `当前组合已接入 ${benchmarkLabel} 基准，但还没有足够的个股归因明细。建议先确认组合持仓，再重新拉取归因。`;
    }

    const components = [
      Number(attribution?.attribution?.stockSelection?.contribution ?? 0) > 0
        ? '股票选择是正贡献来源'
        : '股票选择没有形成正贡献',
      Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0) > 0
        ? '行业配置在增厚收益'
        : '行业配置没有形成显著正贡献',
      outperformance ? '组合当前跑赢基准' : '组合当前未跑赢基准',
    ];
    const contributorText = topCode
      ? `最大正贡献来自 ${topCode}`
      : weakCode
        ? `当前最需要复盘的拖累标的是 ${weakCode}`
        : '当前暂无可识别的贡献股';
    return `${components.join('，')}。${contributorText}，建议直接联动到个股详情和研究页继续排查。`;
  }, [
    accountLeader?.stock_code,
    accountLeader?.stock_name,
    attribution?.attribution?.sectorAllocation?.contribution,
    attribution?.attribution?.stockSelection?.contribution,
    benchmark,
    isAccountMode,
    outperformance,
    selectedBenchmark?.label,
    topContributor?.code,
    weakContributor?.code,
  ]);

  const refreshAccountData = useCallback(async () => {
    await Promise.allSettled([summaryQ.refetch(), positionsQ.refetch(), navQ.refetch(), performanceQ.refetch()]);
  }, [navQ, performanceQ, positionsQ, summaryQ]);

  const refreshPortfolioData = useCallback(async () => {
    await Promise.allSettled([
      portfoliosQ.refetch(),
      portfolioDetailQ.refetch(),
      attributionQ.refetch(),
      benchmarkQ.refetch(),
    ]);
  }, [attributionQ, benchmarkQ, portfolioDetailQ, portfoliosQ]);

  const refreshActiveModeData = useCallback(async () => {
    if (mode === 'portfolio') {
      await refreshPortfolioData();
      return;
    }
    await refreshAccountData();
  }, [mode, refreshAccountData, refreshPortfolioData]);

  const riskHref = useMemo(() => {
    const params = new URLSearchParams();
    params.set('lookbackDays', String(mode === 'account' ? days : portfolioLookbackDays));
    if (mode === 'portfolio' && selectedPortfolioId != null) {
      params.set('portfolioId', String(selectedPortfolioId));
    }
    return `/risk?${params.toString()}`;
  }, [days, mode, portfolioLookbackDays, selectedPortfolioId]);

  const paperHref = useMemo(() => {
    const params = new URLSearchParams();
    params.set('mode', 'account');
    params.set('days', String(days));
    if (accountId) params.set('account_id', accountId);
    return `/paper-trading${params.toString() ? `?${params.toString()}` : ''}`;
  }, [accountId, days]);

  const portfolioHref = useMemo(() => {
    const params = new URLSearchParams();
    if (selectedPortfolioId != null) params.set('portfolioId', String(selectedPortfolioId));
    return `/portfolio${params.toString() ? `?${params.toString()}` : ''}`;
  }, [selectedPortfolioId]);

  const windowPresets = isAccountMode ? WINDOW_PRESETS : [30, 90, 252, 504];
  const activeModeLabel = isAccountMode ? '账户绩效' : '组合归因';
  const pageSummary = isAccountMode
    ? `当前账户 ${accountId || '默认账户'}，观察窗口 ${days} 天，总资产 ${fmtNum(totalValue)}，累计收益率 ${fmtPct(totalReturnPct)}，最大回撤 ${fmtPct(Number(accountMetrics.maxDrawdown ?? 0) * 100)}。`
    : `当前组合为 ${portfolioName}，基准 ${benchmark}，观察窗口 ${portfolioLookbackDays} 天。组合收益 ${fmtPct(portfolioTotalReturnPct)}，超额收益 ${fmtPct(Number(benchmarkComparison?.excessReturnPct ?? 0))}，信息比率 ${fmtNum(Number(benchmarkComparison?.informationRatio ?? 0))}。`;

  useEffect(() => {
    if (!workbenchHydrated || !contextInitializedRef.current) return;
    updateWorkbenchContext({
      mode,
      accountId: isAccountMode ? accountId || null : null,
      portfolioId: isAccountMode ? null : portfolioId || null,
      benchmark: isAccountMode ? null : benchmark,
      days,
      executionId: sourceExecutionId || null,
      stockCode: focusStockCode || null,
    });
  }, [
    accountId,
    benchmark,
    days,
    focusStockCode,
    isAccountMode,
    mode,
    portfolioId,
    sourceExecutionId,
    updateWorkbenchContext,
    workbenchHydrated,
  ]);

  const openStockTarget = useCallback(
    (code?: string) => {
      const nextCode = (code ?? '').trim();
      if (!nextCode) {
        throw new Error('当前没有可打开的股票代码');
      }
      updateWorkbenchContext({ stockCode: nextCode });
      addWorkbenchTask({
        pageKey: 'performance',
        title: `查看 ${nextCode} 个股详情`,
        href: `/stock?code=${encodeURIComponent(nextCode)}`,
        kind: 'stock-review',
        payload: { code: nextCode },
      });
      router.push(`/stock?code=${encodeURIComponent(nextCode)}`);
    },
    [addWorkbenchTask, router, updateWorkbenchContext],
  );

  const openResearchTarget = useCallback(
    (code?: string) => {
      const nextCode = (code ?? '').trim();
      if (!nextCode) {
        throw new Error('当前没有可打开的股票代码');
      }
      updateWorkbenchContext({ stockCode: nextCode, eventCode: nextCode });
      addWorkbenchTask({
        pageKey: 'performance',
        title: `查看 ${nextCode} 研究事件`,
        href: `/research?code=${encodeURIComponent(nextCode)}`,
        kind: 'research-review',
        payload: { code: nextCode },
      });
      router.push(`/research?code=${encodeURIComponent(nextCode)}`);
    },
    [addWorkbenchTask, router, updateWorkbenchContext],
  );

  const openRiskWorkspace = useCallback(() => {
    updateWorkbenchContext({
      mode,
      accountId: isAccountMode ? accountId || null : null,
      portfolioId: isAccountMode ? null : selectedPortfolioId != null ? String(selectedPortfolioId) : null,
      benchmark: isAccountMode ? null : benchmark,
      days,
      lookbackDays: isAccountMode ? days : portfolioLookbackDays,
      stockCode: focusStockCode || null,
      executionId: sourceExecutionId || null,
    });
    addWorkbenchTask({
      pageKey: 'performance',
      title: isAccountMode ? '去风险中心复盘账户回撤' : '去风险中心复盘组合暴露',
      href: riskHref,
      kind: 'risk-review',
      payload: {
        mode,
        accountId: accountId || undefined,
        portfolioId: selectedPortfolioId ?? undefined,
        lookbackDays: isAccountMode ? days : portfolioLookbackDays,
      },
    });
    router.push(riskHref);
  }, [
    accountId,
    addWorkbenchTask,
    benchmark,
    days,
    focusStockCode,
    isAccountMode,
    mode,
    portfolioLookbackDays,
    riskHref,
    router,
    selectedPortfolioId,
    sourceExecutionId,
    updateWorkbenchContext,
  ]);

  const applyPerformanceContext = useCallback(
    (payload?: Record<string, unknown>) => {
      if (!payload) {
        return { message: '未提供可更新的绩效上下文' };
      }

      const nextMode = payload.mode === 'account' || payload.mode === 'portfolio' ? payload.mode : null;
      if (nextMode) {
        setMode(nextMode);
      }

      const nextDays = clampDays(payload.days, days);
      if (nextDays !== days) {
        setDays(nextDays);
      }

      const nextAccountId =
        typeof payload.accountId === 'string'
          ? payload.accountId.trim()
          : typeof payload.account_id === 'string'
            ? payload.account_id.trim()
            : '';
      if (nextAccountId) {
        setAccountId(nextAccountId);
        setMode('account');
      }

      const nextPortfolioId =
        typeof payload.portfolioId === 'string'
          ? payload.portfolioId.trim()
          : typeof payload.portfolio_id === 'string'
            ? payload.portfolio_id.trim()
            : typeof payload.portfolioId === 'number' && Number.isFinite(payload.portfolioId)
              ? String(payload.portfolioId)
              : typeof payload.portfolio_id === 'number' && Number.isFinite(payload.portfolio_id)
                ? String(payload.portfolio_id)
                : '';
      if (nextPortfolioId) {
        setPortfolioId(nextPortfolioId);
        setMode('portfolio');
      }

      const nextBenchmark = typeof payload.benchmark === 'string' ? payload.benchmark.trim() : '';
      if (nextBenchmark && BENCHMARK_OPTIONS.some((item) => item.code === nextBenchmark)) {
        setBenchmark(nextBenchmark);
      }

      return {
        message: `已更新绩效上下文${nextMode ? `，模式 ${nextMode === 'account' ? '账户绩效' : '组合归因'}` : ''}${nextPortfolioId ? `，组合 ${nextPortfolioId}` : ''}${nextBenchmark ? `，基准 ${nextBenchmark}` : ''}${nextDays ? `，窗口 ${nextDays} 天` : ''}`,
      };
    },
    [days],
  );

  const currentView = useMemo(
    () => ({
      mode,
      accountId,
      portfolioId,
      benchmark,
      days,
    }),
    [accountId, benchmark, days, mode, portfolioId],
  );

  usePageContext({
    pageKey: 'performance',
    title: '绩效中心',
    summary: pageSummary,
    tags: isAccountMode
      ? [activeModeLabel, `${days} 天`, `${positions.length} 持仓`]
      : [activeModeLabel, `${portfolioLookbackDays} 天`, benchmark, outperformance ? '跑赢基准' : '未跑赢基准'],
    suggestions: isAccountMode
      ? [
          '刷新当前账户绩效数据',
          '切换到组合归因视角',
          accountLeader ? `打开 ${String(accountLeader.stock_code ?? '')} 查看持仓细节` : '打开风险中心对照回撤与暴露',
        ]
      : [
          '刷新当前组合归因',
          topContributor ? `打开 ${String(topContributor.code ?? '')} 查看最大贡献股` : '切换到账户绩效视角',
          '总结当前组合的超额收益来源',
        ],
    raw: isAccountMode
      ? {
          mode,
          accountId: accountId || 'default',
          days,
          totalValue,
          totalReturnPct,
          positions: positions.length,
          metrics: accountMetrics,
        }
      : {
          mode,
          portfolioId: selectedPortfolioId,
          portfolioName,
          benchmark,
          days: portfolioLookbackDays,
          totalReturnPct: portfolioTotalReturnPct,
          excessReturnPct: benchmarkComparison?.excessReturnPct ?? null,
          informationRatio: benchmarkComparison?.informationRatio ?? null,
          outperformance,
        },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'performance.refresh',
        label: isAccountMode ? '刷新账户绩效' : '刷新组合归因',
        description: isAccountMode ? '刷新账户概览、净值和绩效指标' : '刷新组合归因和基准对比数据',
        keywords: ['刷新', '绩效', isAccountMode ? '账户' : '组合'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: async () => {
          await refreshActiveModeData();
          return { message: isAccountMode ? '已刷新账户绩效' : '已刷新组合归因' };
        },
      },
      {
        id: 'performance.update-context',
        label: '更新绩效上下文',
        description:
          '支持 payload: mode, accountId, portfolioId, benchmark, days。用于让 Copilot 直接切换账户、组合、基准和观察窗口。',
        keywords: ['更新上下文', '切换组合', '切换基准', 'payload'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: (payload: Record<string, unknown> | undefined) => applyPerformanceContext(payload),
      },
      {
        id: 'performance.switch.account',
        label: '切到账户绩效',
        description: '查看模拟账户净值、收益率和持仓表现',
        keywords: ['账户绩效', '净值'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          setMode('account');
          return { message: '已切到账户绩效视角' };
        },
      },
      {
        id: 'performance.switch.portfolio',
        label: '切到组合归因',
        description: '查看组合归因、行业配置和基准对比',
        keywords: ['组合归因', '基准'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          setMode('portfolio');
          return { message: '已切到组合归因视角' };
        },
      },
      {
        id: 'performance.window.30',
        label: '切换到 30 天窗口',
        description: '查看近 30 天绩效或归因表现',
        keywords: ['30天', '窗口'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          setDays(30);
          return { message: '已切换到 30 天窗口' };
        },
      },
      {
        id: 'performance.window.90',
        label: '切换到 90 天窗口',
        description: '查看近 90 天绩效或归因表现',
        keywords: ['90天', '窗口'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          setDays(90);
          return { message: '已切换到 90 天窗口' };
        },
      },
      {
        id: 'performance.open-risk',
        label: '打开风险中心',
        description: '进入风险中心对照回撤、暴露和 VaR',
        keywords: ['风险中心', '回撤', 'VaR'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          openRiskWorkspace();
          return { message: '已打开风险中心' };
        },
      },
      {
        id: 'performance.open-source',
        label: isAccountMode ? '打开模拟交易' : '打开组合页',
        description: isAccountMode ? '回到模拟交易页查看委托与持仓' : '回到组合页查看组合和持仓配置',
        keywords: [isAccountMode ? '模拟交易' : '组合', isAccountMode ? '持仓' : '归因'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: () => {
          router.push(isAccountMode ? paperHref : portfolioHref);
          return { message: isAccountMode ? '已打开模拟交易页' : '已打开组合页' };
        },
      },
      {
        id: 'performance.open-stock',
        label: '打开贡献股详情',
        description: '支持 payload: code。默认打开当前最重要的贡献股或领先持仓。',
        keywords: ['贡献股', '个股详情'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: (payload: Record<string, unknown> | undefined) => {
          const nextCode =
            typeof payload?.code === 'string' && payload.code.trim()
              ? payload.code.trim()
              : String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? '').trim();
          openStockTarget(nextCode);
          return { message: `已打开 ${nextCode} 个股详情` };
        },
      },
      {
        id: 'performance.open-research',
        label: '打开贡献股研究',
        description: '支持 payload: code。默认打开当前最重要的贡献股或领先持仓的研究页。',
        keywords: ['贡献股', '研究页', '研报'],
        scope: 'page' as const,
        pageKey: 'performance',
        run: (payload: Record<string, unknown> | undefined) => {
          const nextCode =
            typeof payload?.code === 'string' && payload.code.trim()
              ? payload.code.trim()
              : String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? '').trim();
          openResearchTarget(nextCode);
          return { message: `已打开 ${nextCode} 研究页` };
        },
      },
    ],
    [
      accountLeader?.stock_code,
      applyPerformanceContext,
      isAccountMode,
      openRiskWorkspace,
      openResearchTarget,
      openStockTarget,
      paperHref,
      portfolioHref,
      refreshActiveModeData,
      router,
      topContributor?.code,
    ],
  );

  usePageActions(pageActions);

  const heroWindowLabel = `${isAccountMode ? days : portfolioLookbackDays} 天`;
  const heroWindowHint = isAccountMode ? '账户净值与收益率复盘' : `基准 ${selectedBenchmark?.label ?? benchmark}`;
  const heroPrimaryMetricLabel = isAccountMode ? '总资产' : '组合收益率';
  const heroPrimaryMetricValue = isAccountMode ? fmtNum(totalValue) : fmtPct(portfolioTotalReturnPct);
  const heroPrimaryMetricHint = isAccountMode
    ? `累计收益率 ${fmtPct(totalReturnPct)}`
    : `超额收益 ${fmtPct(Number(benchmarkComparison?.excessReturnPct ?? 0))}`;
  const focusMetricHint = isAccountMode
    ? accountLeader?.stock_name
      ? `${accountLeader.stock_name} 为当前领先持仓`
      : '当前还没有领先持仓'
    : topContributor?.code
      ? `最大正贡献来自 ${topContributor.code}`
      : '当前暂无贡献股明细';
  const accountErrorMessage = summaryQ.error || positionsQ.error || navQ.error || performanceQ.error || null;
  const portfolioErrorMessage = portfolioDetailQ.error || attributionQ.error || benchmarkQ.error || null;
  const linkedStockCode = String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? '').trim();
  const mobilePrimaryTabs = useMemo(
    () => [
      { key: 'filters', label: '条件' },
      { key: 'dashboard', label: isAccountMode ? '账户面板' : '归因面板' },
    ],
    [isAccountMode],
  );

  return (
    <PageContainer>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <TabBar tabs={MODE_TABS} active={mode} onChange={setMode} />
      </div>

      <PerformanceHero
        isAccountMode={isAccountMode}
        activeModeLabel={activeModeLabel}
        outperformance={outperformance}
        sourceExecutionId={sourceExecutionId}
        onRefresh={() => void refreshActiveModeData()}
        onOpenRisk={openRiskWorkspace}
        focusStockCode={focusStockCode}
        onOpenStock={focusStockCode ? () => openStockTarget(focusStockCode) : null}
        onOpenResearch={focusStockCode ? () => openResearchTarget(focusStockCode) : null}
        currentEntityLabel={isAccountMode ? `账户 ${accountId || '默认账户'}` : portfolioName}
        windowLabel={heroWindowLabel}
        windowHint={heroWindowHint}
        primaryMetricLabel={heroPrimaryMetricLabel}
        primaryMetricValue={heroPrimaryMetricValue}
        primaryMetricHint={heroPrimaryMetricHint}
        focusMetricHint={focusMetricHint}
        pageSummary={pageSummary}
        benchmarkLabel={selectedBenchmark?.label ?? benchmark}
        portfolioNarrative={portfolioNarrative}
      />

      <WorkspaceToolbar
        pageKey="performance"
        currentView={currentView}
        onApplyView={(snapshot) => {
          applyPerformanceContext(snapshot);
        }}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />

      <WorkspaceSplitLayout
        pageKey="performance"
        primaryLabel="绩效主区"
        secondaryLabel="绩效摘要"
        defaultMobileTab="primary"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            {collapseToTabs ? (
              <TabBar tabs={mobilePrimaryTabs} active={mobilePrimaryTab} onChange={setMobilePrimaryTab} />
            ) : null}

            {!collapseToTabs || mobilePrimaryTab === 'filters' ? (
              <PerformanceContextPanels
                isAccountMode={isAccountMode}
                accountId={accountId}
                accounts={accounts}
                onAccountChange={setAccountId}
                portfolios={portfolios}
                portfolioId={portfolioId}
                onPortfolioChange={setPortfolioId}
                benchmark={benchmark}
                benchmarkOptions={[...BENCHMARK_OPTIONS]}
                onBenchmarkChange={setBenchmark}
                windowPresets={windowPresets}
                days={days}
                onDaysChange={setDays}
                portfolioNarrative={portfolioNarrative}
                activeModeLabel={activeModeLabel}
                portfolioLookbackDays={portfolioLookbackDays}
                selectedBenchmarkLabel={selectedBenchmark?.label ?? benchmark}
                topContributorCode={String(topContributor?.code ?? '')}
                weakContributorCode={String(weakContributor?.code ?? '')}
                linkedStockCode={linkedStockCode}
                onOpenRisk={openRiskWorkspace}
                onOpenStock={linkedStockCode ? () => openStockTarget(linkedStockCode) : null}
                onOpenResearch={linkedStockCode ? () => openResearchTarget(linkedStockCode) : null}
              />
            ) : null}

            {!collapseToTabs || mobilePrimaryTab === 'dashboard' ? (
              <>
                {!isAccountMode && portfoliosQ.isFetching && portfolios.length === 0 ? (
                  <LoadingState text="加载组合列表中..." />
                ) : null}
                {!isAccountMode && portfoliosQ.error ? <ErrorState text={portfoliosQ.error} /> : null}

                {!isAccountMode && portfolios.length === 0 && !portfoliosQ.isFetching ? (
                  <SectionCard className="mt-4 p-4">
                    <EmptyState
                      text="当前还没有可归因的组合。"
                      hint="先在组合页创建一个组合并添加持仓，归因和基准对比才有意义。"
                      action={
                        <Link href="/portfolio" className="action-chip text-sm no-underline text-inherit">
                          去创建组合
                        </Link>
                      }
                    />
                  </SectionCard>
                ) : null}

                {isAccountMode ? (
                  <AccountPerformanceDashboard
                    errorMessage={accountErrorMessage}
                    totalValue={totalValue}
                    totalReturnPct={totalReturnPct}
                    accountMetrics={accountMetrics as PaperTradingPerformanceMetrics}
                    days={days}
                    navData={navData as PaperTradingNavPoint[]}
                    navCategories={navCategories}
                    navValues={navValues}
                    performanceData={performanceData as PaperTradingPerformancePoint[]}
                    perfCategories={perfCategories}
                    perfReturns={perfReturns}
                    topPositions={topPositions as PaperTradingPosition[]}
                    onOpenStockTarget={openStockTarget}
                    onOpenResearchTarget={openResearchTarget}
                  />
                ) : (
                  <PortfolioAttributionDashboard
                    errorMessage={portfolioErrorMessage}
                    isLoading={portfolioDetailQ.isFetching || attributionQ.isFetching || benchmarkQ.isFetching}
                    attribution={attribution}
                    benchmarkComparison={benchmarkComparison}
                    portfolioMessage={portfolioMessage}
                    portfolioName={portfolioName}
                    portfolioHoldingsCount={portfolioHoldings.length || attributionByStock.length}
                    attributionByStock={attributionByStock}
                    portfolioTotalReturnPct={portfolioTotalReturnPct}
                    portfolioTotalAssets={portfolioTotalAssets}
                    waterfallData={waterfallData}
                    sectorBarItems={sectorBarItems}
                    outperformance={outperformance}
                    selectedPortfolioId={selectedPortfolioId}
                    portfolioLookbackDays={portfolioLookbackDays}
                    benchmark={benchmark}
                    onOpenStockTarget={openStockTarget}
                    onOpenResearchTarget={openResearchTarget}
                  />
                )}
              </>
            ) : null}
          </div>
        }
        secondary={
          <PerformanceSecondarySidebar
            isAccountMode={isAccountMode}
            activeModeLabel={activeModeLabel}
            portfolioNarrative={portfolioNarrative}
            days={days}
            portfolioLookbackDays={portfolioLookbackDays}
            selectedBenchmarkLabel={selectedBenchmark?.label ?? benchmark}
            focusStockCode={focusStockCode}
            onOpenRisk={openRiskWorkspace}
            onOpenStock={focusStockCode ? () => openStockTarget(focusStockCode) : null}
            onOpenResearch={focusStockCode ? () => openResearchTarget(focusStockCode) : null}
            totalValue={totalValue}
            totalReturnPct={totalReturnPct}
            accountMetrics={accountMetrics as PaperTradingPerformanceMetrics}
            accountLeaderCode={String(accountLeader?.stock_code ?? '')}
            topPositions={topPositions as PaperTradingPosition[]}
            portfolioName={portfolioName}
            portfolioHoldingsCount={portfolioHoldings.length || attributionByStock.length}
            portfolioTotalReturnPct={portfolioTotalReturnPct}
            benchmark={benchmark}
            benchmarkOptions={[...BENCHMARK_OPTIONS]}
            onBenchmarkChange={setBenchmark}
            benchmarkComparison={benchmarkComparison}
            attribution={attribution}
            outperformance={outperformance}
            portfolioMessage={portfolioMessage}
            topContributorCode={String(topContributor?.code ?? '')}
            weakContributorCode={String(weakContributor?.code ?? '')}
            onOpenStockTarget={openStockTarget}
            onOpenResearchTarget={openResearchTarget}
          />
        }
      />
    </PageContainer>
  );
}
