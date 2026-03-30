'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { BarChart, LineChart, WaterfallChart } from '@/components/charts';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { Badge, DataTable, KpiCard, KpiGrid, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  PaperTradingAccountsResponse,
  PaperTradingNavHistoryResponse,
  PaperTradingPerformanceResponse,
  PaperTradingPositionsResponse,
  PaperTradingSummary,
  PerformanceAttributionResponse,
  PerformanceBenchmarkComparisonResponse,
} from '@aiask/shared-types';

type PerformanceMode = 'account' | 'portfolio';

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
  const searchParams = useSearchParams();
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
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const contextInitializedRef = useRef(false);

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
  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

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

  return (
    <PageContainer>
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Performance Workspace</Badge>
              <Badge variant={isAccountMode ? 'neutral' : 'warning'}>{activeModeLabel}</Badge>
              {!isAccountMode ? (
                <Badge variant={outperformance ? 'success' : 'warning'}>
                  {outperformance ? '当前跑赢基准' : '当前未跑赢基准'}
                </Badge>
              ) : null}
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              绩效复盘工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里不只看收益数字，而是把账户净值、组合归因、基准对照和下一跳动作收进一套连续界面。你可以先定观察窗口，再顺着风险中心、研究页和个股详情继续拆解收益来源。
            </p>
            {sourceExecutionId ? (
              <div className="mt-4 inline-flex rounded-full border border-white/45 bg-white/32 px-3 py-1.5 text-xs text-text-secondary shadow-sm">
                来源执行任务：<span className="ml-1 font-medium text-text-primary">{sourceExecutionId}</span>
              </div>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => void refreshActiveModeData()} className={heroPrimaryButtonCls}>
                刷新当前数据
              </button>
              <button type="button" onClick={() => openRiskWorkspace()} className={heroSecondaryButtonCls}>
                打开风险中心
              </button>
              {focusStockCode ? (
                <>
                  <button
                    type="button"
                    onClick={() => openStockTarget(focusStockCode)}
                    className={heroSecondaryButtonCls}
                  >
                    查看重点股票
                  </button>
                  <button
                    type="button"
                    onClick={() => openResearchTarget(focusStockCode)}
                    className={heroSecondaryButtonCls}
                  >
                    查看研究页
                  </button>
                </>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前视角</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeModeLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {isAccountMode ? `账户 ${accountId || '默认账户'}` : portfolioName}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">观察窗口</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {isAccountMode ? days : portfolioLookbackDays} 天
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {isAccountMode ? '账户净值与收益率复盘' : `基准 ${selectedBenchmark?.label ?? benchmark}`}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                  {isAccountMode ? '总资产' : '组合收益率'}
                </div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {isAccountMode ? fmtNum(totalValue) : fmtPct(portfolioTotalReturnPct)}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {isAccountMode
                    ? `累计收益率 ${fmtPct(totalReturnPct)}`
                    : `超额收益 ${fmtPct(Number(benchmarkComparison?.excessReturnPct ?? 0))}`}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">重点标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{focusStockCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {isAccountMode
                    ? accountLeader?.stock_name
                      ? `${accountLeader.stock_name} 为当前领先持仓`
                      : '当前还没有领先持仓'
                    : topContributor?.code
                      ? `最大正贡献来自 ${topContributor.code}`
                      : '当前暂无贡献股明细'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {isAccountMode ? `${accountId || '默认账户'} 账户复盘` : `${portfolioName} 组合归因`}
              </div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  核心摘要：<span className="font-medium text-text-primary">{pageSummary}</span>
                </div>
                {!isAccountMode ? (
                  <div className={noteCardCls}>
                    基准口径：
                    <span className="font-medium text-text-primary">{selectedBenchmark?.label ?? benchmark}</span>
                  </div>
                ) : null}
                <div className={noteCardCls}>
                  联动股票：<span className="font-medium text-text-primary">{focusStockCode || '暂无'}</span>
                </div>
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步动作</div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>{portfolioNarrative}</div>
                <div className={noteCardCls}>
                  {isAccountMode
                    ? '先核对回撤和胜率，再决定是否追到单只股票。'
                    : '先看超额收益来源，再判断是配置问题还是个股问题。'}
                </div>
                <div className={noteCardCls}>
                  {focusStockCode
                    ? `当前可直接跳转 ${focusStockCode} 的研究页和详情页。`
                    : '如果没有聚焦股票，先在持仓或归因列表中选一只拖累股或贡献股。'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <WorkspaceToolbar
        pageKey="performance"
        currentView={currentView}
        onApplyView={(snapshot) => {
          applyPerformanceContext(snapshot);
        }}
        supportsPagePanels
      />

      <TabBar tabs={MODE_TABS} active={mode} onChange={setMode} />

      <WorkspaceSplitLayout
        pageKey="performance"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            <SectionCard tabAttached className="p-4">
              <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
                <div>
                  <h3 className="m-0 font-medium">{isAccountMode ? '账户绩效上下文' : '组合归因上下文'}</h3>
                  <p className="mb-0 mt-1 text-sm text-text-secondary">
                    {isAccountMode
                      ? '用于观察模拟账户净值、波动、回撤和核心持仓，适合从交易结果往回看。'
                      : '用于观察组合收益是由个股选择、行业配置还是择时带来的，适合从研究和配置往后复盘。'}
                  </p>
                </div>
                <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
                  <div className="font-medium text-text-primary">联动建议</div>
                  <ol className="mb-0 mt-2 space-y-1 pl-4">
                    <li>先确认当前查看的是账户还是组合。</li>
                    <li>再切换窗口长度，避免短周期和长周期混用。</li>
                    <li>最后跳到风险中心，核对收益和风险是否匹配。</li>
                  </ol>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                {isAccountMode ? (
                  <select
                    value={accountId}
                    onChange={(event) => setAccountId(event.target.value)}
                    className="w-auto min-w-[148px] text-sm"
                  >
                    <option value="">默认账户</option>
                    {accounts.map((account, index) => (
                      <option key={account.account_id ?? index} value={account.account_id ?? ''}>
                        {account.account_id ?? `账户 ${index + 1}`}
                      </option>
                    ))}
                  </select>
                ) : (
                  <>
                    <select
                      value={portfolioId}
                      onChange={(event) => setPortfolioId(event.target.value)}
                      className="w-auto min-w-[168px] text-sm"
                    >
                      <option value="">选择组合</option>
                      {portfolios.map((portfolio) => (
                        <option key={portfolio.id} value={portfolio.id}>
                          {portfolio.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={benchmark}
                      onChange={(event) => setBenchmark(event.target.value)}
                      className="w-auto min-w-[144px] text-sm"
                    >
                      {BENCHMARK_OPTIONS.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </>
                )}
                {windowPresets.map((windowDays) => (
                  <button
                    key={windowDays}
                    type="button"
                    onClick={() => setDays(windowDays)}
                    className={`action-chip cursor-pointer text-xs ${days === windowDays ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                  >
                    {windowDays} 天
                  </button>
                ))}
              </div>
            </SectionCard>

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

            <SectionCard className="mt-4 p-4">
              <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                <div>
                  <h3 className="m-0 font-medium">{isAccountMode ? '账户复盘说明' : '归因解释与下一步动作'}</h3>
                  <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">{portfolioNarrative}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" onClick={() => openRiskWorkspace()} className={chipButtonCls}>
                      打开风险中心
                    </button>
                    {(isAccountMode ? accountLeader?.stock_code : topContributor?.code) ? (
                      <button
                        type="button"
                        onClick={() =>
                          openStockTarget(
                            String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? ''),
                          )
                        }
                        className={chipButtonCls}
                      >
                        打开重点股票详情
                      </button>
                    ) : null}
                    {(isAccountMode ? accountLeader?.stock_code : topContributor?.code) ? (
                      <button
                        type="button"
                        onClick={() =>
                          openResearchTarget(
                            String((isAccountMode ? accountLeader?.stock_code : topContributor?.code) ?? ''),
                          )
                        }
                        className={chipButtonCls}
                      >
                        打开重点股票研究
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="panel-soft rounded-[24px] p-4">
                  <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">当前联动上下文</div>
                  <div className="mt-3 space-y-2 text-xs text-text-secondary">
                    <div>
                      当前模式：<span className="font-medium text-text-primary">{activeModeLabel}</span>
                    </div>
                    <div>
                      观察窗口：
                      <span className="font-medium text-text-primary">
                        {isAccountMode ? days : portfolioLookbackDays} 天
                      </span>
                    </div>
                    <div>
                      基准口径：
                      <span className="font-medium text-text-primary">
                        {isAccountMode ? '账户净值视角' : (selectedBenchmark?.label ?? benchmark)}
                      </span>
                    </div>
                    {!isAccountMode && topContributor?.code ? (
                      <div>
                        最大贡献股：<span className="font-medium text-text-primary">{topContributor.code}</span>
                      </div>
                    ) : null}
                    {!isAccountMode && weakContributor?.code ? (
                      <div>
                        主要拖累股：<span className="font-medium text-text-primary">{weakContributor.code}</span>
                      </div>
                    ) : null}
                  </div>
                  {!isAccountMode ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {BENCHMARK_OPTIONS.map((item) => (
                        <button
                          key={item.code}
                          type="button"
                          onClick={() => setBenchmark(item.code)}
                          className={`action-chip cursor-pointer text-[11px] ${benchmark === item.code ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </SectionCard>

            {isAccountMode ? (
              <>
                {summaryQ.error || positionsQ.error || navQ.error || performanceQ.error ? (
                  <ErrorState
                    text={summaryQ.error || positionsQ.error || navQ.error || performanceQ.error || '账户绩效加载失败'}
                  />
                ) : null}

                <KpiGrid cols={5} className="mb-4 mt-4">
                  <KpiCard title="总资产" value={fmtNum(totalValue)} />
                  <KpiCard title="累计收益率" value={fmtPct(totalReturnPct)} change={totalReturnPct} />
                  <KpiCard title="夏普比率" value={fmtNum(Number(accountMetrics.sharpe ?? 0))} />
                  <KpiCard
                    title="最大回撤"
                    value={fmtPct(Number(accountMetrics.maxDrawdown ?? 0) * 100)}
                    change={Number(accountMetrics.maxDrawdown ?? 0) * 100}
                  />
                  <KpiCard
                    title="胜率"
                    value={fmtPct(Number(accountMetrics.winRate ?? 0) * 100)}
                    change={Number(accountMetrics.winRate ?? 0) * 100}
                  />
                </KpiGrid>

                <div className="grid gap-4 2xl:grid-cols-2">
                  <SectionCard className="p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <h3 className="m-0 font-medium">净值曲线</h3>
                      <button
                        type="button"
                        onClick={() =>
                          exportCSV(
                            navData.map((item) => ({
                              日期: item.nav_date ?? '',
                              总资产: item.total_value ?? 0,
                              现金: item.cash ?? 0,
                              持仓市值: item.market_value ?? 0,
                              日收益率: item.daily_return ?? 0,
                            })),
                            `performance-nav-${days}.csv`,
                          )
                        }
                        className={chipButtonCls}
                      >
                        导出净值
                      </button>
                    </div>
                    {navData.length > 1 ? (
                      <LineChart categories={navCategories} series={[{ name: '总资产', data: navValues }]} />
                    ) : (
                      <p className="text-sm text-text-secondary">暂无足够净值数据</p>
                    )}
                  </SectionCard>

                  <SectionCard className="p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <h3 className="m-0 font-medium">日收益率</h3>
                      <button
                        type="button"
                        onClick={() =>
                          exportCSV(
                            performanceData.map((item) => ({
                              日期: item.date ?? '',
                              总资产: item.totalValue ?? 0,
                              日收益率: item.dailyReturn ?? 0,
                            })),
                            `performance-returns-${days}.csv`,
                          )
                        }
                        className={chipButtonCls}
                      >
                        导出收益
                      </button>
                    </div>
                    {performanceData.length > 1 ? (
                      <LineChart categories={perfCategories} series={[{ name: '日收益率(%)', data: perfReturns }]} />
                    ) : (
                      <p className="text-sm text-text-secondary">暂无足够收益数据</p>
                    )}
                  </SectionCard>
                </div>

                <SectionCard className="p-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h3 className="m-0 font-medium">核心持仓</h3>
                    <span className="text-xs text-text-secondary">按市值排序展示前 8 只</span>
                  </div>
                  <DataTable
                    rows={topPositions as unknown as Record<string, unknown>[]}
                    emptyText="暂无持仓"
                    columns={[
                      { key: 'stock_code', label: '代码' },
                      { key: 'stock_name', label: '名称' },
                      { key: 'quantity', label: '数量' },
                      { key: 'cost_price', label: '成本', render: (value: unknown) => fmtNum(Number(value ?? 0), 2) },
                      {
                        key: 'current_price',
                        label: '现价',
                        render: (value: unknown) => fmtNum(Number(value ?? 0), 2),
                      },
                      { key: 'market_value', label: '市值', render: (value: unknown) => fmtNum(Number(value ?? 0)) },
                      {
                        key: 'profit_rate',
                        label: '盈亏率',
                        render: (value: unknown) => fmtPct(Number(value ?? 0) * 100),
                      },
                      {
                        key: 'actions',
                        label: '联动',
                        sortable: false,
                        render: (_value: unknown, row: Record<string, unknown>) => {
                          const rowCode = String(row.stock_code ?? '').trim();
                          if (!rowCode) return '-';
                          return (
                            <div className="flex flex-wrap gap-2">
                              <button type="button" onClick={() => openStockTarget(rowCode)} className={chipButtonCls}>
                                详情
                              </button>
                              <button
                                type="button"
                                onClick={() => openResearchTarget(rowCode)}
                                className={chipButtonCls}
                              >
                                研究
                              </button>
                            </div>
                          );
                        },
                      },
                    ]}
                    mobileCardRender={(row) => (
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-text-primary">
                              {String(row.stock_name ?? row.stock_code ?? '-')}
                            </div>
                            <div className="text-xs text-text-secondary">代码：{String(row.stock_code ?? '-')}</div>
                          </div>
                          <div className="text-xs text-text-secondary">
                            {fmtPct(Number(row.profit_rate ?? 0) * 100)}
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                          <div>数量：{String(row.quantity ?? '-')}</div>
                          <div>市值：{fmtNum(Number(row.market_value ?? 0))}</div>
                          <div>成本：{fmtNum(Number(row.cost_price ?? 0), 2)}</div>
                          <div>现价：{fmtNum(Number(row.current_price ?? 0), 2)}</div>
                        </div>
                        {String(row.stock_code ?? '').trim() ? (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => openStockTarget(String(row.stock_code ?? ''))}
                              className={chipButtonCls}
                            >
                              打开详情
                            </button>
                            <button
                              type="button"
                              onClick={() => openResearchTarget(String(row.stock_code ?? ''))}
                              className={chipButtonCls}
                            >
                              打开研究
                            </button>
                          </div>
                        ) : null}
                      </div>
                    )}
                  />
                </SectionCard>
              </>
            ) : (
              <>
                {portfolioDetailQ.error || attributionQ.error || benchmarkQ.error ? (
                  <ErrorState
                    text={portfolioDetailQ.error || attributionQ.error || benchmarkQ.error || '组合归因加载失败'}
                  />
                ) : null}

                {(portfolioDetailQ.isFetching || attributionQ.isFetching || benchmarkQ.isFetching) && !attribution ? (
                  <LoadingState text="加载组合归因中..." />
                ) : null}

                {portfolioMessage ? <MetaLine>{portfolioMessage}</MetaLine> : null}

                <KpiGrid cols={5} className="mb-4 mt-4">
                  <KpiCard title="当前组合" value={portfolioName} />
                  <KpiCard title="持仓数量" value={portfolioHoldings.length || attributionByStock.length} />
                  <KpiCard
                    title="组合收益率"
                    value={fmtPct(portfolioTotalReturnPct)}
                    change={portfolioTotalReturnPct}
                  />
                  <KpiCard
                    title="基准收益率"
                    value={fmtPct(Number(benchmarkComparison?.benchmarkReturnPct ?? 0))}
                    change={Number(benchmarkComparison?.benchmarkReturnPct ?? 0)}
                  />
                  <KpiCard
                    title="超额收益"
                    value={fmtPct(Number(benchmarkComparison?.excessReturnPct ?? 0))}
                    change={Number(benchmarkComparison?.excessReturnPct ?? 0)}
                  />
                </KpiGrid>

                <KpiGrid cols={5} className="mb-4">
                  <KpiCard title="组合资产" value={fmtNum(portfolioTotalAssets)} />
                  <KpiCard title="信息比率" value={fmtNum(Number(benchmarkComparison?.informationRatio ?? 0))} />
                  <KpiCard
                    title="跟踪误差"
                    value={fmtPct(Number(benchmarkComparison?.trackingErrorPct ?? 0))}
                    change={Number(benchmarkComparison?.trackingErrorPct ?? 0)}
                  />
                  <KpiCard
                    title="股票选择贡献"
                    value={fmtPct(Number(attribution?.attribution?.stockSelection?.contribution ?? 0))}
                    change={Number(attribution?.attribution?.stockSelection?.contribution ?? 0)}
                  />
                  <KpiCard
                    title="行业配置贡献"
                    value={fmtPct(Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0))}
                    change={Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0)}
                  />
                </KpiGrid>

                <div className="grid gap-4 2xl:grid-cols-2">
                  <SectionCard className="p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <h3 className="m-0 font-medium">收益归因拆解</h3>
                      <Badge variant={outperformance ? 'success' : 'warning'}>
                        {outperformance ? '跑赢基准' : '未跑赢基准'}
                      </Badge>
                    </div>
                    {waterfallData.some((item) => item.value !== 0) ? (
                      <WaterfallChart data={waterfallData} height={320} />
                    ) : (
                      <p className="text-sm text-text-secondary">暂无足够归因分解数据</p>
                    )}
                  </SectionCard>

                  <SectionCard className="p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <h3 className="m-0 font-medium">行业收益表现</h3>
                      <span className="text-xs text-text-secondary">按行业收益率展示前 8 项</span>
                    </div>
                    {sectorBarItems.length > 0 ? (
                      <BarChart items={sectorBarItems} height={320} horizontal colorByValue yAxisName="收益率(%)" />
                    ) : (
                      <p className="text-sm text-text-secondary">暂无行业收益数据</p>
                    )}
                  </SectionCard>
                </div>

                <SectionCard className="p-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h3 className="m-0 font-medium">个股贡献明细</h3>
                    <button
                      type="button"
                      onClick={() =>
                        exportCSV(
                          attributionByStock.map((item) => ({
                            代码: item.code ?? '',
                            行业: item.sector ?? '',
                            权重占比: item.weightPct ?? 0,
                            区间收益率: item.stockReturnPct ?? 0,
                            生命周期收益率: item.lifetimeReturnPct ?? 0,
                            贡献度: item.contributionPct ?? 0,
                          })),
                          `performance-attribution-${selectedPortfolioId ?? 'portfolio'}-${portfolioLookbackDays}.csv`,
                        )
                      }
                      className={chipButtonCls}
                    >
                      导出归因
                    </button>
                  </div>
                  <DataTable
                    rows={attributionByStock as unknown as Record<string, unknown>[]}
                    emptyText="暂无个股归因数据"
                    columns={[
                      { key: 'code', label: '代码' },
                      { key: 'sector', label: '行业' },
                      { key: 'weightPct', label: '权重占比', render: (value: unknown) => fmtPct(Number(value ?? 0)) },
                      {
                        key: 'stockReturnPct',
                        label: '区间收益率',
                        render: (value: unknown) => fmtPct(Number(value ?? 0)),
                      },
                      {
                        key: 'lifetimeReturnPct',
                        label: '生命周期收益率',
                        render: (value: unknown) => fmtPct(Number(value ?? 0)),
                      },
                      {
                        key: 'contributionPct',
                        label: '贡献度',
                        render: (value: unknown) => fmtPct(Number(value ?? 0)),
                      },
                      {
                        key: 'actions',
                        label: '联动',
                        sortable: false,
                        render: (_value: unknown, row: Record<string, unknown>) => {
                          const rowCode = String(row.code ?? '').trim();
                          if (!rowCode) return '-';
                          return (
                            <div className="flex flex-wrap gap-2">
                              <button type="button" onClick={() => openStockTarget(rowCode)} className={chipButtonCls}>
                                详情
                              </button>
                              <button
                                type="button"
                                onClick={() => openResearchTarget(rowCode)}
                                className={chipButtonCls}
                              >
                                研究
                              </button>
                            </div>
                          );
                        },
                      },
                    ]}
                    searchable
                    mobileCardRender={(row) => (
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-text-primary">{String(row.code ?? '-')}</div>
                            <div className="text-xs text-text-secondary">{String(row.sector ?? '未知行业')}</div>
                          </div>
                          <div className="text-xs text-text-secondary">{fmtPct(Number(row.contributionPct ?? 0))}</div>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                          <div>权重：{fmtPct(Number(row.weightPct ?? 0))}</div>
                          <div>区间收益：{fmtPct(Number(row.stockReturnPct ?? 0))}</div>
                          <div>生命周期收益：{fmtPct(Number(row.lifetimeReturnPct ?? 0))}</div>
                          <div>贡献：{fmtPct(Number(row.contributionPct ?? 0))}</div>
                        </div>
                        {String(row.code ?? '').trim() ? (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => openStockTarget(String(row.code ?? ''))}
                              className={chipButtonCls}
                            >
                              打开详情
                            </button>
                            <button
                              type="button"
                              onClick={() => openResearchTarget(String(row.code ?? ''))}
                              className={chipButtonCls}
                            >
                              打开研究
                            </button>
                          </div>
                        ) : null}
                      </div>
                    )}
                  />
                </SectionCard>

                <SectionCard className="p-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h3 className="m-0 font-medium">基准对比与窗口审计</h3>
                    <span className="text-xs text-text-secondary">用于核对超额收益来源是否可靠</span>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                    <div className={noteCardCls}>
                      <div className="text-xs text-text-secondary">基准代码</div>
                      <div className="mt-1 text-sm font-medium text-text-primary">
                        {benchmarkComparison?.benchmark ?? benchmark}
                      </div>
                    </div>
                    <div className={noteCardCls}>
                      <div className="text-xs text-text-secondary">年化超额收益</div>
                      <div className="mt-1 text-sm font-medium text-text-primary">
                        {fmtPct(Number(benchmarkComparison?.annualizedExcessReturnPct ?? 0))}
                      </div>
                    </div>
                    <div className={noteCardCls}>
                      <div className="text-xs text-text-secondary">对齐交易日</div>
                      <div className="mt-1 text-sm font-medium text-text-primary">
                        {String(benchmarkComparison?.alignedDays ?? '-')}
                      </div>
                    </div>
                    <div className={noteCardCls}>
                      <div className="text-xs text-text-secondary">归因方法</div>
                      <div className="mt-1 text-sm font-medium text-text-primary">{attribution?.method ?? '-'}</div>
                    </div>
                  </div>
                  {attribution?.benchmarkAlignment?.alignmentMethod ? (
                    <MetaLine>基准对齐方式：{attribution.benchmarkAlignment.alignmentMethod}</MetaLine>
                  ) : null}
                  {benchmarkComparison?.alignedDays != null ? (
                    <MetaLine>组合与基准对齐交易日：{benchmarkComparison.alignedDays}</MetaLine>
                  ) : null}
                  {attribution?.attribution?.timing?.basis ? (
                    <MetaLine>择时贡献口径：{attribution.attribution.timing.basis}</MetaLine>
                  ) : null}
                </SectionCard>
              </>
            )}
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <div className={sidePanelCls}>
              <div className="text-sm font-medium text-text-primary">当前联动摘要</div>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">{portfolioNarrative}</p>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  模式：<span className="font-medium text-text-primary">{activeModeLabel}</span>
                </div>
                <div className={noteCardCls}>
                  观察窗口：
                  <span className="font-medium text-text-primary">
                    {isAccountMode ? days : portfolioLookbackDays} 天
                  </span>
                </div>
                <div className={noteCardCls}>
                  基准：
                  <span className="font-medium text-text-primary">
                    {isAccountMode ? '账户净值视角' : (selectedBenchmark?.label ?? benchmark)}
                  </span>
                </div>
                {focusStockCode ? (
                  <div className={noteCardCls}>
                    焦点股票：<span className="font-medium text-text-primary">{focusStockCode}</span>
                  </div>
                ) : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => openRiskWorkspace()} className={chipButtonCls}>
                  打开风险中心
                </button>
                {focusStockCode ? (
                  <button type="button" onClick={() => openStockTarget(focusStockCode)} className={chipButtonCls}>
                    打开股票详情
                  </button>
                ) : null}
                {focusStockCode ? (
                  <button type="button" onClick={() => openResearchTarget(focusStockCode)} className={chipButtonCls}>
                    打开研究页
                  </button>
                ) : null}
              </div>
            </div>

            {isAccountMode ? (
              <>
                <KpiGrid cols={2}>
                  <KpiCard title="总资产" value={fmtNum(totalValue)} />
                  <KpiCard title="累计收益率" value={fmtPct(totalReturnPct)} change={totalReturnPct} />
                  <KpiCard title="夏普比率" value={fmtNum(Number(accountMetrics.sharpe ?? 0))} />
                  <KpiCard
                    title="最大回撤"
                    value={fmtPct(Number(accountMetrics.maxDrawdown ?? 0) * 100)}
                    change={Number(accountMetrics.maxDrawdown ?? 0) * 100}
                  />
                  <KpiCard
                    title="胜率"
                    value={fmtPct(Number(accountMetrics.winRate ?? 0) * 100)}
                    change={Number(accountMetrics.winRate ?? 0) * 100}
                  />
                </KpiGrid>

                <SectionCard className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">持仓快照</div>
                    <Badge variant={accountLeader ? 'success' : 'neutral'}>
                      {accountLeader?.stock_code || '暂无核心持仓'}
                    </Badge>
                  </div>
                  <div className="mt-3 space-y-3">
                    {topPositions.slice(0, 5).map((item) => (
                      <div key={`${item.stock_code}-${item.stock_name}`} className={noteCardCls}>
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-sm font-medium text-text-primary">
                              {item.stock_name || item.stock_code}
                            </div>
                            <div className="text-xs text-text-secondary">{item.stock_code || '-'}</div>
                          </div>
                          <div className="text-xs text-text-secondary">
                            {fmtPct(Number(item.profit_rate ?? 0) * 100)}
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => openStockTarget(String(item.stock_code ?? ''))}
                            className={chipButtonCls}
                          >
                            详情
                          </button>
                          <button
                            type="button"
                            onClick={() => openResearchTarget(String(item.stock_code ?? ''))}
                            className={chipButtonCls}
                          >
                            研究
                          </button>
                        </div>
                      </div>
                    ))}
                    {topPositions.length === 0 ? (
                      <div className="text-xs text-text-secondary">当前账户暂无核心持仓。</div>
                    ) : null}
                  </div>
                </SectionCard>
              </>
            ) : (
              <>
                <KpiGrid cols={2}>
                  <KpiCard title="当前组合" value={portfolioName} />
                  <KpiCard title="持仓数量" value={portfolioHoldings.length || attributionByStock.length} />
                  <KpiCard
                    title="组合收益率"
                    value={fmtPct(portfolioTotalReturnPct)}
                    change={portfolioTotalReturnPct}
                  />
                  <KpiCard
                    title="基准收益率"
                    value={fmtPct(Number(benchmarkComparison?.benchmarkReturnPct ?? 0))}
                    change={Number(benchmarkComparison?.benchmarkReturnPct ?? 0)}
                  />
                  <KpiCard
                    title="超额收益"
                    value={fmtPct(Number(benchmarkComparison?.excessReturnPct ?? 0))}
                    change={Number(benchmarkComparison?.excessReturnPct ?? 0)}
                  />
                  <KpiCard title="信息比率" value={fmtNum(Number(benchmarkComparison?.informationRatio ?? 0))} />
                  <KpiCard
                    title="跟踪误差"
                    value={fmtPct(Number(benchmarkComparison?.trackingErrorPct ?? 0))}
                    change={Number(benchmarkComparison?.trackingErrorPct ?? 0)}
                  />
                  <KpiCard
                    title="股票选择贡献"
                    value={fmtPct(Number(attribution?.attribution?.stockSelection?.contribution ?? 0))}
                    change={Number(attribution?.attribution?.stockSelection?.contribution ?? 0)}
                  />
                  <KpiCard
                    title="行业配置贡献"
                    value={fmtPct(Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0))}
                    change={Number(attribution?.attribution?.sectorAllocation?.contribution ?? 0)}
                  />
                </KpiGrid>

                <SectionCard className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">基准与贡献审计</div>
                    <Badge variant={outperformance ? 'success' : 'warning'}>
                      {outperformance ? '跑赢基准' : '未跑赢基准'}
                    </Badge>
                  </div>
                  {portfolioMessage ? <MetaLine>{portfolioMessage}</MetaLine> : null}
                  <div className="mt-3 space-y-2 text-xs text-text-secondary">
                    <div>
                      基准代码：
                      <span className="font-medium text-text-primary">
                        {benchmarkComparison?.benchmark ?? benchmark}
                      </span>
                    </div>
                    <div>
                      年化超额收益：
                      <span className="font-medium text-text-primary">
                        {fmtPct(Number(benchmarkComparison?.annualizedExcessReturnPct ?? 0))}
                      </span>
                    </div>
                    <div>
                      对齐交易日：
                      <span className="font-medium text-text-primary">
                        {String(benchmarkComparison?.alignedDays ?? '-')}
                      </span>
                    </div>
                    <div>
                      归因方法：<span className="font-medium text-text-primary">{attribution?.method ?? '-'}</span>
                    </div>
                    {topContributor?.code ? (
                      <div>
                        最大贡献股：<span className="font-medium text-text-primary">{topContributor.code}</span>
                      </div>
                    ) : null}
                    {weakContributor?.code ? (
                      <div>
                        主要拖累股：<span className="font-medium text-text-primary">{weakContributor.code}</span>
                      </div>
                    ) : null}
                  </div>
                  {!isAccountMode ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {BENCHMARK_OPTIONS.map((item) => (
                        <button
                          key={item.code}
                          type="button"
                          onClick={() => setBenchmark(item.code)}
                          className={`action-chip cursor-pointer text-[11px] ${benchmark === item.code ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </SectionCard>
              </>
            )}
          </div>
        }
      />
    </PageContainer>
  );
}
