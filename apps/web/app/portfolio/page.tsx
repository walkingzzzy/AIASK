'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ResponsiveResultWorkbench from '@/components/responsive-result-workbench';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { ConfirmDialog, PageContainer, Badge, SectionCard, TabBar } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { useStockCode } from '@/hooks/use-stock-code';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { readTransactionConfirmations } from '@/lib/transaction-confirmations';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { useCartStore } from '@/store/cart-store';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import {
  PortfolioChartsSection,
  PortfolioDetailSection,
  PortfolioEmptySelectionSection,
  PortfolioListSection,
  PortfolioOptimizationSummarySection,
  PortfolioRiskMetricsSection,
  PortfolioStressTestSection,
} from './components/portfolio-detail-sections';
import {
  PortfolioOperationWorkspaceSection,
  PortfolioSidebarSummary,
} from './components/portfolio-overview-sections';
import type {
  OptData,
  PendingPortfolioAction,
  PortfolioDetailRecord,
  RiskData,
  StressData,
} from './portfolio-page.types';

export default function PortfolioPage() {
  const searchParams = useStableSearchParams();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const queryPortfolioId = searchParams.get('portfolio_id')?.trim() ?? '';
  const [portfolioId, setPortfolioId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingPortfolioAction | null>(null);
  const [lastPrimaryRefreshAt, setLastPrimaryRefreshAt] = useState<string | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<'list' | 'compose' | 'detail' | 'ops'>('list');
  const cartItems = useCartStore((state) => state.items);
  const clearCart = useCartStore((state) => state.clear);

  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newCapital, setNewCapital] = useState('1000000');
  const createApi = useApiMutation<unknown>({ effects: ['portfolio.changed'] });
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');

  const {
    code: holdCode,
    setCode: setHoldCode,
    codeError: holdCodeError,
    validate: validateHold,
    trimmedCode: holdTrimmed,
  } = useStockCode();
  const [holdShares, setHoldShares] = useState('100');
  const [holdCost, setHoldCost] = useState('');
  const addHoldingApi = useApiMutation<unknown>({ effects: ['portfolio.changed'] });

  const listQ = useApiQuery<unknown>('/portfolio/list', {
    parse: (raw) => ensureRecordOrArray(raw, '组合列表'),
  });
  const detailQ = useApiQuery<unknown>(
    portfolioId.trim() ? `/portfolio/get?portfolioId=${encodeURIComponent(portfolioId.trim())}` : null,
    {
      parse: (raw) => ensureRecordOrArray(raw, '组合详情'),
    },
  );

  const optimizeApi = useApiMutation<OptData>({ parse: (raw) => ensureRecord(raw, '组合优化') as OptData });
  const riskApi = useApiMutation<RiskData>({ parse: (raw) => ensureRecord(raw, '组合风险') as RiskData });
  const stressApi = useApiMutation<StressData>({ parse: (raw) => ensureRecord(raw, '压力测试') as StressData });

  const loading =
    profileQ.isFetching ||
    listQ.isFetching ||
    detailQ.isFetching ||
    optimizeApi.isPending ||
    riskApi.isPending ||
    stressApi.isPending ||
    createApi.isPending ||
    addHoldingApi.isPending;
  const error =
    formError ||
    listQ.error ||
    detailQ.error ||
    optimizeApi.error ||
    riskApi.error ||
    stressApi.error ||
    createApi.error ||
    addHoldingApi.error;
  const confirmPrefs = useMemo(() => readTransactionConfirmations(profileQ.data), [profileQ.data]);

  const optimize = useCallback(() => {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    optimizeApi.trigger('/portfolio/optimize', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }, [optimizeApi, portfolioId]);

  const analyzeRisk = useCallback(() => {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    riskApi.trigger('/portfolio/risk-analysis', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }, [portfolioId, riskApi]);

  const runStress = useCallback(() => {
    if (!portfolioId.trim()) return setFormError('请输入 portfolioId');
    stressApi.trigger('/portfolio/stress-test', { method: 'POST' }, { portfolioId: portfolioId.trim() });
  }, [portfolioId, stressApi]);

  const cartTotalWeight = useMemo(
    () => cartItems.reduce((sum, item) => sum + Number(item.weight ?? 0), 0),
    [cartItems],
  );
  const cartWeightValid = cartItems.length > 0 && Math.abs(cartTotalWeight - 100) < 0.01;

  const executeCreatePortfolio = useCallback(async (payload: {
    name: string;
    description: string;
    initialCapital: string;
    strategies?: Array<{ strategyId: string; weight: number }>;
  }) => {
    const data = await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, payload);
    const createdId =
      data && typeof data === 'object' && 'portfolioId' in data
        ? String((data as { portfolioId?: unknown }).portfolioId ?? '')
        : '';
    if (createdId) {
      setPortfolioId(createdId);
      setWorkspaceTab('detail');
    }
    setNewName('');
    setNewDesc('');
    if (payload.strategies?.length) {
      clearCart();
    }
  }, [clearCart, createApi]);

  async function handleCreate() {
    if (!newName.trim()) return setFormError('请输入组合名称');
    const payload = {
      name: newName.trim(),
      description: newDesc.trim(),
      initialCapital: newCapital.trim() || '1000000',
    };
    try {
      if (confirmPrefs.portfolioRebalance) {
        setPendingAction({
          type: 'create',
          summary: `${payload.name} · 初始资金 ${payload.initialCapital}`,
          payload,
        });
        return;
      }
      await executeCreatePortfolio(payload);
    } catch {
      /* captured */
    }
  }

  const handleCreateFromCart = useCallback(async () => {
    if (!cartItems.length) {
      setFormError('购物车为空，无法创建策略组合');
      return;
    }
    if (!cartWeightValid) {
      setFormError('购物车权重合计必须等于 100%');
      return;
    }
    const payload = {
      name: newName.trim() || `策略组合 ${new Date().toLocaleDateString('zh-CN')}`,
      description: newDesc.trim() || `来自购物车的策略组合：${cartItems.map((item) => `${item.name}(${item.weight}%)`).join('，')}`,
      initialCapital: newCapital.trim() || '1000000',
      strategies: cartItems.map((item) => ({
        strategyId: item.strategyId,
        weight: Number(item.weight) / 100,
      })),
    };
    try {
      if (confirmPrefs.portfolioRebalance) {
        setPendingAction({
          type: 'create',
          summary: `${payload.name} · 购物车 ${cartItems.length} 条策略`,
          payload,
        });
        return;
      }
      await executeCreatePortfolio(payload);
    } catch {
      /* captured */
    }
  }, [
    cartItems,
    cartWeightValid,
    confirmPrefs.portfolioRebalance,
    executeCreatePortfolio,
    newCapital,
    newDesc,
    newName,
  ]);

  async function executeAddHolding(payload: { portfolioId: string; code: string; shares: string; costPrice?: string }) {
    await addHoldingApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, payload);
    setHoldCode('');
    setHoldShares('100');
    setHoldCost('');
  }

  async function handleAddHolding() {
    if (!portfolioId.trim()) return setFormError('请先输入 portfolioId');
    if (!validateHold()) return;
    const payload = {
      portfolioId: portfolioId.trim(),
      code: holdTrimmed,
      shares: holdShares.trim() || '100',
      ...(holdCost.trim() ? { costPrice: holdCost.trim() } : {}),
    };
    try {
      if (confirmPrefs.portfolioRebalance) {
        setPendingAction({
          type: 'addHolding',
          summary: `组合 ${payload.portfolioId} · ${payload.code} · ${payload.shares} 股`,
          payload,
        });
        return;
      }
      await executeAddHolding(payload);
    } catch {
      /* captured */
    }
  }

  async function handleConfirmAction() {
    if (!pendingAction) return;
    const action = pendingAction;
    setPendingAction(null);
    if (action.type === 'create') {
      await executeCreatePortfolio(action.payload);
      return;
    }
    await executeAddHolding(action.payload);
  }

  const detailObj = useMemo(() => {
    if (!detailQ.data || typeof detailQ.data !== 'object') return null;
    return detailQ.data as PortfolioDetailRecord;
  }, [detailQ.data]);
  const detailHoldings = useMemo(
    () => extractArray(detailQ.data, 'holdings', 'positions', 'data') as Record<string, unknown>[],
    [detailQ.data],
  );
  const detailStrategies = useMemo(
    () => extractArray(detailQ.data, 'strategyAllocations') as Record<string, unknown>[],
    [detailQ.data],
  );
  const portfolioList = useMemo(() => extractArray(listQ.data) as Record<string, unknown>[], [listQ.data]);

  const weightSlices = useMemo(() => {
    const w = optimizeApi.data?.optimization?.weights;
    if (!w) return [];
    if (Array.isArray(w)) return w.map((item) => ({ name: item.code, value: +(Number(item.weight) * 100).toFixed(1) }));
    return Object.entries(w).map(([key, value]) => ({ name: key, value: +(Number(value) * 100).toFixed(1) }));
  }, [optimizeApi.data]);

  const riskBars = useMemo(() => {
    const contribution = riskApi.data?.riskMetrics?.riskContribution;
    if (!contribution || typeof contribution !== 'object') return [];
    return Object.entries(contribution).map(([key, value]) => ({
      label: key,
      value: +(Number(value) * 100).toFixed(2),
    }));
  }, [riskApi.data]);

  const stressScenarios = useMemo(() => {
    const scenarios = stressApi.data?.stressResult?.scenarios;
    if (Array.isArray(scenarios)) return scenarios as Record<string, unknown>[];
    return extractArray(stressApi.data, 'scenarios', 'data') as Record<string, unknown>[];
  }, [stressApi.data]);

  const activePortfolioId = portfolioId.trim();
  const selectedPortfolio = useMemo(
    () => portfolioList.find((item) => String(item.id ?? '').trim() === activePortfolioId) ?? null,
    [portfolioList, activePortfolioId],
  );
  const portfolioDisplayName = selectedPortfolio ? String(selectedPortfolio.name ?? activePortfolioId) : '尚未选择组合';
  const portfolioNextStep = activePortfolioId ? '继续查看详情、加仓或执行分析' : '先创建新组合或在列表中选择组合';
  const currentAssetsDisplay =
    detailObj?.totalAssets != null
      ? fmtNum(Number(detailObj.totalAssets), 2)
      : selectedPortfolio
        ? fmtNum(Number(selectedPortfolio.currentValue ?? 0), 2)
        : '-';
  const latestPortfolioRefreshAt =
    [listQ.dataUpdatedAt, detailQ.dataUpdatedAt]
      .filter((value): value is number => typeof value === 'number' && value > 0)
      .sort((left, right) => right - left)[0] ?? null;
  const latestPortfolioRefreshText = latestPortfolioRefreshAt
    ? new Date(latestPortfolioRefreshAt).toLocaleString('zh-CN')
    : '等待首个组合快照';

  useEffect(() => {
    const timer = window.setTimeout(() => {
    if (activePortfolioId) {
      setWorkspaceTab((prev) => (prev === 'list' ? 'detail' : prev));
      return;
    }
    setWorkspaceTab((prev) => {
      if (cartItems.length > 0 && prev === 'list') return 'compose';
      return prev === 'detail' || prev === 'ops' ? 'list' : prev;
    });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activePortfolioId, cartItems.length]);

  const refreshPortfolio = useCallback(async () => {
    const tasks = [listQ.refetch()];
    if (portfolioId.trim()) {
      tasks.push(detailQ.refetch());
    }
    await Promise.allSettled(tasks);
    setLastPrimaryRefreshAt(new Date().toLocaleString('zh-CN'));
  }, [detailQ, listQ, portfolioId]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged) return;
    const timer = window.setTimeout(() => {
      setPortfolioId(queryPortfolioId || (workbenchContext.portfolioId ?? ''));
      setHoldCode(workbenchContext.stockCode ?? '');
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    activeWorkspaceId,
    queryPortfolioId,
    setHoldCode,
    workbenchContext.portfolioId,
    workbenchContext.stockCode,
    workbenchHydrated,
  ]);

  useEffect(() => {
    if (!workbenchHydrated || !queryPortfolioId) return;
    const timer = window.setTimeout(() => {
      setPortfolioId(queryPortfolioId);
      setWorkspaceTab('detail');
    }, 0);
    return () => window.clearTimeout(timer);
  }, [queryPortfolioId, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      portfolioId: activePortfolioId || null,
      stockCode: holdTrimmed || null,
      mode: activePortfolioId ? 'portfolio' : null,
    });
  }, [activePortfolioId, holdTrimmed, updateWorkbenchContext, workbenchHydrated]);

  const pageActions = useMemo(
    () => [
      {
        id: 'portfolio.refresh',
        label: '刷新组合',
        description: '刷新组合列表与当前组合详情',
        keywords: ['刷新', '组合'],
        scope: 'page' as const,
        pageKey: 'portfolio',
        run: async () => {
          await refreshPortfolio();
          return { message: '已刷新组合数据' };
        },
      },
      {
        id: 'portfolio.optimize',
        label: '执行组合优化',
        description: '对当前组合执行优化配置',
        keywords: ['优化', '组合'],
        scope: 'page' as const,
        pageKey: 'portfolio',
        run: () => {
          optimize();
          return { message: '已触发组合优化' };
        },
      },
      {
        id: 'portfolio.risk',
        label: '执行风险分析',
        description: '对当前组合执行风险分析',
        keywords: ['风险', '分析'],
        scope: 'page' as const,
        pageKey: 'portfolio',
        run: () => {
          analyzeRisk();
          return { message: '已触发风险分析' };
        },
      },
      {
        id: 'portfolio.stress',
        label: '执行压力测试',
        description: '对当前组合执行压力测试',
        keywords: ['压力测试', 'stress'],
        scope: 'page' as const,
        pageKey: 'portfolio',
        run: () => {
          runStress();
          return { message: '已触发压力测试' };
        },
      },
      ...(cartItems.length > 0
        ? [{
            id: 'portfolio.create-from-cart',
            label: '用购物车创建策略组合',
            description: '把当前策略购物车直接转换成策略组合',
            keywords: ['购物车', '策略组合'],
            scope: 'page' as const,
            pageKey: 'portfolio',
            run: async () => {
              setWorkspaceTab('compose');
              await handleCreateFromCart();
              return { message: '已开始用购物车创建策略组合' };
            },
          }]
        : []),
    ],
    [analyzeRisk, cartItems.length, handleCreateFromCart, optimize, refreshPortfolio, runStress],
  );

  usePageActions(pageActions);

  const portfolioSummary = `当前选中组合 ${selectedPortfolio ? String(selectedPortfolio.name ?? activePortfolioId) : '未选择'}，组合总数 ${portfolioList.length}，持仓 ${detailHoldings.length} 条。`;
  const portfolioEvidence = useMemo(
    () => [
      { label: '当前组合', value: portfolioDisplayName },
      { label: '组合总数', value: String(portfolioList.length) },
      { label: '持仓数量', value: String(detailHoldings.length) },
      { label: '策略数量', value: String(detailStrategies.length) },
      { label: '购物车策略', value: String(cartItems.length) },
    ],
    [cartItems.length, detailHoldings.length, detailStrategies.length, portfolioDisplayName, portfolioList.length],
  );
  const portfolioLinks = useMemo(
    () => [
      activePortfolioId ? { id: 'portfolio-open-risk', label: '去风险中心', href: `/risk?portfolioId=${encodeURIComponent(activePortfolioId)}` } : { id: 'portfolio-open-risk', label: '去风险中心', href: '/risk' },
      activePortfolioId ? { id: 'portfolio-open-performance', label: '去绩效中心', href: `/performance?mode=portfolio&portfolio_id=${encodeURIComponent(activePortfolioId)}` } : { id: 'portfolio-open-performance', label: '去绩效中心', href: '/performance' },
      { id: 'portfolio-open-strategy', label: '去策略超市', href: '/strategy-market?from=portfolio' },
      { id: 'portfolio-open-skills', label: '去技能中心', href: '/skills?from=portfolio' },
    ],
    [activePortfolioId],
  );
  const portfolioRiskNotes = useMemo(() => {
    const notes: string[] = [];
    if (!activePortfolioId) notes.push('当前还没有选中组合，建议先锁定组合后再执行优化和风控动作。');
    if (!detailHoldings.length) notes.push('当前组合没有持仓，后续风险和绩效结果可能为空。');
    return notes;
  }, [activePortfolioId, detailHoldings.length]);
  const portfolioResult = useMemo(
    () =>
      buildLocalResultContract({
        summary: portfolioSummary,
        pageActions,
        preferredActionIds: ['portfolio.refresh', 'portfolio.optimize', 'portfolio.risk', 'portfolio.stress'],
        recommendedLinks: portfolioLinks,
        evidence: portfolioEvidence,
        riskNotes: portfolioRiskNotes,
        workbenchTask: defaultWorkbenchTask('portfolio', `组合工作台：${portfolioDisplayName}`, activePortfolioId ? `/portfolio?portfolio_id=${encodeURIComponent(activePortfolioId)}` : '/portfolio', 'portfolio-review', {
          portfolioId: activePortfolioId || null,
          holdingCount: detailHoldings.length,
        }),
      }),
    [activePortfolioId, detailHoldings.length, pageActions, portfolioDisplayName, portfolioEvidence, portfolioLinks, portfolioRiskNotes, portfolioSummary],
  );

  usePageContext({
    pageKey: 'portfolio',
    title: '组合管理',
    summary: portfolioSummary,
    stockCode: holdTrimmed || undefined,
    objectType: activePortfolioId ? 'portfolio' : 'workspace',
    objectId: activePortfolioId || 'portfolio',
    resultType: 'portfolio-summary',
    tags: [
      `${portfolioList.length} 个组合`,
      `${detailHoldings.length} 条持仓`,
      activePortfolioId ? `组合 ${activePortfolioId}` : '未选择组合',
      cartItems.length ? `${cartItems.length} 条购物车策略` : null,
    ].filter((item): item is string => Boolean(item)),
    suggestions: [
      activePortfolioId ? `评估组合 ${activePortfolioId} 当前配置和风险` : '先选择一个组合，再评估配置和风险',
      '总结当前组合列表里最值得继续跟进的标的',
      '给出组合优化、风控和压力测试的下一步顺序',
    ],
    recommendedActions: portfolioResult.recommendedActions,
    recommendedLinks: portfolioResult.recommendedLinks,
    evidenceSummary: evidenceToSummary(portfolioResult.evidence),
    riskNotes: portfolioResult.riskNotes ?? [],
    freshness: portfolioResult.freshness ?? null,
    raw: {
      portfolioId: activePortfolioId || null,
      portfolioCount: portfolioList.length,
      holdingCount: detailHoldings.length,
      strategyCount: detailStrategies.length,
      cartItemCount: cartItems.length,
    },
  });

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      portfolioId,
      holdCode,
      holdShares,
      holdCost,
    }),
    [holdCode, holdCost, holdShares, portfolioId],
  );
  const workspaceTabLabel =
    workspaceTab === 'list'
      ? '组合列表'
      : workspaceTab === 'compose'
        ? '创建与加仓'
        : workspaceTab === 'detail'
          ? '组合详情'
          : '优化与风控';

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (typeof snapshot.portfolioId === 'string') {
        setPortfolioId(snapshot.portfolioId);
      }
      if (typeof snapshot.holdCode === 'string') {
        setHoldCode(snapshot.holdCode);
      }
      if (typeof snapshot.holdShares === 'string' || typeof snapshot.holdShares === 'number') {
        setHoldShares(String(snapshot.holdShares));
      }
      if (typeof snapshot.holdCost === 'string' || typeof snapshot.holdCost === 'number') {
        setHoldCost(String(snapshot.holdCost));
      }
    },
    [setHoldCode],
  );

  const primaryContent = (
    <>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">组合工作台</Badge>
              <Badge variant={activePortfolioId ? 'success' : 'warning'}>
                {activePortfolioId ? `组合 ${portfolioDisplayName}` : '等待选择组合'}
              </Badge>
              <Badge variant={optimizeApi.data?.optimization ? 'success' : 'neutral'}>
                {optimizeApi.data?.optimization ? '已有优化结果' : '尚未优化'}
              </Badge>
              <Badge variant={riskApi.data?.riskMetrics ? 'warning' : 'neutral'}>
                {riskApi.data?.riskMetrics ? '已有风险分析' : '尚未分析'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              组合管理工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              先锁定目标组合，再选择维护持仓、查看组合详情，或继续做优化、风险分析和压力测试。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  void refreshPortfolio();
                }}
                data-testid="page-primary-action"
                data-action-testid="portfolio-refresh-action"
                className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                刷新组合列表
              </button>
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前组合 {portfolioDisplayName} ｜ 当前视图 {workspaceTabLabel}
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                组合 {portfolioList.length} 个 ｜ 持仓 {detailHoldings.length} 条 ｜ 策略 {detailStrategies.length} 条
              </p>
              <p className="mt-2 mb-0 text-xs text-text-secondary">
                最近数据：{latestPortfolioRefreshText}
                {lastPrimaryRefreshAt ? ` ｜ 手动刷新：${lastPrimaryRefreshAt}` : ''}
              </p>
            </div>
          </div>

          <details className="panel-soft rounded-[28px] p-4 sm:p-5" open>
            <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              当前聚焦与下一步
            </summary>
            <div className="mt-4 space-y-3">
              <div className="metric-tile rounded-[22px] p-3 text-xs text-text-secondary">
                当前组合：<span className="font-medium text-text-primary">{portfolioDisplayName}</span>
              </div>
              <div className="metric-tile rounded-[22px] p-3 text-xs text-text-secondary">
                当前资产：<span className="font-medium text-text-primary">{currentAssetsDisplay}</span>
              </div>
              <div className="metric-tile rounded-[22px] p-3 text-xs text-text-secondary">{portfolioNextStep}</div>
            </div>
          </details>
        </div>
      </section>

      <ResponsiveResultWorkbench pageKey="portfolio" title="组合结果工作台" result={portfolioResult} />

      {loading ? <LoadingState text="正在加载组合数据..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">工作流</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">当前工作流</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              按列表、创建与加仓、详情、优化与风控分步处理，便于在同一组合下复查每个动作。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            组合 {portfolioList.length} 个 ｜ 当前组合 {activePortfolioId || '未选择'}
          </div>
        </div>
        <div className="mt-4">
          <TabBar
            tabs={[
              { key: 'list', label: '组合列表' },
              { key: 'compose', label: '创建与加仓' },
              { key: 'detail', label: '组合详情' },
              { key: 'ops', label: '优化与风控' },
            ]}
            active={workspaceTab}
            onChange={(key) => setWorkspaceTab(key as typeof workspaceTab)}
          />
        </div>
        <SectionCard tabAttached>
          {workspaceTab === 'list' ? (
            <>
              <PortfolioListSection
                portfolioList={portfolioList}
                activePortfolioId={activePortfolioId}
                onSelectPortfolio={(selectedId) => {
                  setPortfolioId(selectedId);
                  setFormError(null);
                  setWorkspaceTab('detail');
                }}
              />
              {!activePortfolioId && portfolioList.length === 0 ? (
                <EmptyState text="还没有组合数据" hint="先创建一个组合，或者稍后刷新组合列表。" />
              ) : null}
            </>
          ) : null}

          {workspaceTab === 'compose' ? (
            <>
              {cartItems.length > 0 ? (
                <SectionCard className="mt-0 p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="eyebrow">策略购物车</div>
                      <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">待创建的策略分配</h3>
                      <p className="mt-2 mb-0 text-sm leading-7 text-text-secondary">
                        当前购物车里有 {cartItems.length} 条策略，权重合计 {cartTotalWeight.toFixed(1)}%。确认权重后，可直接生成一组可跟踪的策略组合。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={cartWeightValid ? 'success' : 'warning'}>
                        {cartWeightValid ? '权重已就绪' : '权重未满 100%'}
                      </Badge>
                      <button
                        type="button"
                        onClick={() => void handleCreateFromCart()}
                        disabled={!cartWeightValid || createApi.isPending}
                        className="rounded-full bg-primary px-4 py-2 text-sm text-white disabled:opacity-50"
                      >
                        {createApi.isPending ? '创建中...' : '用购物车创建策略组合'}
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {cartItems.map((item) => (
                      <div key={item.strategyId} className="metric-tile rounded-[22px] p-4 text-sm text-text-secondary">
                        <div className="font-medium text-text-primary">{item.name}</div>
                        <div className="mt-2">策略 ID：{item.strategyId}</div>
                        <div className="mt-1">权重：{item.weight}%</div>
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}
              <PortfolioOperationWorkspaceSection
                activePortfolioId={activePortfolioId}
                portfolioDisplayName={portfolioDisplayName}
                portfolioNextStep={portfolioNextStep}
                portfolioCount={portfolioList.length}
                currentAssetsDisplay={currentAssetsDisplay}
                portfolioId={portfolioId}
                onPortfolioIdChange={setPortfolioId}
                setFormError={setFormError}
                onRefetchList={() => {
                  void listQ.refetch();
                }}
                onRefetchDetail={() => {
                  void detailQ.refetch();
                }}
                onOptimize={optimize}
                onAnalyzeRisk={analyzeRisk}
                onRunStress={runStress}
                newName={newName}
                onNewNameChange={setNewName}
                newDesc={newDesc}
                onNewDescChange={setNewDesc}
                newCapital={newCapital}
                onNewCapitalChange={setNewCapital}
                onCreate={() => {
                  void handleCreate();
                }}
                createPending={createApi.isPending}
                createSuccess={createApi.data != null}
                holdCode={holdCode}
                onHoldCodeChange={setHoldCode}
                holdCodeError={holdCodeError}
                holdShares={holdShares}
                onHoldSharesChange={setHoldShares}
                holdCost={holdCost}
                onHoldCostChange={setHoldCost}
                onAddHolding={() => {
                  void handleAddHolding();
                }}
                addHoldingPending={addHoldingApi.isPending}
                addHoldingSuccess={addHoldingApi.data != null}
              />
            </>
          ) : null}

          {workspaceTab === 'detail' ? (
            <>
              <PortfolioEmptySelectionSection activePortfolioId={activePortfolioId} />
              <PortfolioDetailSection
                detailObj={detailObj}
                detailHoldings={detailHoldings}
                detailStrategies={detailStrategies}
              />
              <PortfolioChartsSection weightSlices={weightSlices} riskBars={riskBars} />
            </>
          ) : null}

          {workspaceTab === 'ops' ? (
            <>
              <SectionCard className="mt-0 p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="eyebrow">优化与风控</div>
                    <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">优化与风控</h3>
                    <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                      在已选组合上运行优化、风险分析和压力测试，结果会回到下方摘要卡片用于继续复盘。
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={optimize} className="action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]">
                    优化配置
                  </button>
                  <button type="button" onClick={analyzeRisk} className="action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]">
                    风险分析
                  </button>
                  <button type="button" onClick={runStress} className="action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]">
                    压力测试
                  </button>
                </div>
              </SectionCard>
              <PortfolioOptimizationSummarySection optimization={optimizeApi.data?.optimization} />
              <PortfolioRiskMetricsSection riskMetrics={riskApi.data?.riskMetrics} />
              <PortfolioStressTestSection stressScenarios={stressScenarios} />
            </>
          ) : null}
        </SectionCard>
      </div>
    </>
  );

  const secondaryContent = (
    <PortfolioSidebarSummary
      portfolioDisplayName={portfolioDisplayName}
      portfolioCount={portfolioList.length}
      holdingCount={detailHoldings.length}
      strategyCount={detailStrategies.length}
      holdTrimmed={holdTrimmed}
      holdShares={holdShares}
      holdCost={holdCost}
      hasOptimization={Boolean(optimizeApi.data?.optimization)}
      hasRiskMetrics={Boolean(riskApi.data?.riskMetrics)}
      stressScenarioCount={stressScenarios.length}
    />
  );

  return (
    <PageContainer>
      <WorkspaceToolbar
        pageKey="portfolio"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />
      <WorkspaceSplitLayout
        pageKey="portfolio"
        primary={primaryContent}
        secondary={secondaryContent}
        mobileSummary={
          <div className="panel-soft rounded-[24px] px-4 py-3 text-sm text-text-secondary">
            组合 {portfolioDisplayName} ｜ 持仓 {detailHoldings.length} 条 ｜ 当前视图 {workspaceTabLabel}
          </div>
        }
        maxDefaultSections={0}
      />
      <ConfirmDialog
        open={pendingAction != null}
        title={pendingAction?.type === 'create' ? '确认创建组合' : '确认添加持仓'}
        confirmText={pendingAction?.type === 'create' ? '确认创建' : '确认添加'}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => {
          void handleConfirmAction();
        }}
      >
        <div className="space-y-2">
          <div>当前操作已开启“组合调仓”二次确认。</div>
          <div className="text-xs text-text-secondary">
            即将执行：
            <span className="ml-1 font-medium text-text-primary">{pendingAction?.summary ?? '-'}</span>
          </div>
        </div>
      </ConfirmDialog>
    </PageContainer>
  );
}
