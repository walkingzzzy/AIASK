'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, StockCodeInput, Badge } from '@/components/ui';
import { PieChart, BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { useStockCode } from '@/hooks/use-stock-code';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

type OptData = {
  optimization?: {
    expectedReturn?: number;
    expectedRisk?: number;
    sharpe?: number;
    weights?: Record<string, number> | Array<{ code: string; weight: number }>;
  };
};
type RiskData = {
  riskMetrics?: {
    var95?: number;
    var99?: number;
    cvar?: number;
    beta?: number;
    volatility?: number;
    riskContribution?: Record<string, number>;
  };
};
type StressScenario = { name?: string; impact?: number; description?: string };
type StressData = { stressResult?: { scenarios?: StressScenario[] } };
type PortfolioDetailRecord = Record<string, unknown> & {
  strategyAllocations?: Array<Record<string, unknown>>;
};

export default function PortfolioPage() {
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const [portfolioId, setPortfolioId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Create portfolio
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newCapital, setNewCapital] = useState('1000000');
  const createApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.portfolio()]] });

  // Add holding
  const {
    code: holdCode,
    setCode: setHoldCode,
    codeError: holdCodeError,
    validate: validateHold,
    trimmedCode: holdTrimmed,
  } = useStockCode();
  const [holdShares, setHoldShares] = useState('100');
  const [holdCost, setHoldCost] = useState('');
  const addHoldingApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.portfolio()]] });

  // Read queries
  const listQ = useApiQuery<unknown>('/portfolio/list', {
    parse: (raw) => ensureRecordOrArray(raw, '组合列表'),
  });
  const detailQ = useApiQuery<unknown>(
    portfolioId.trim() ? `/portfolio/get?portfolioId=${encodeURIComponent(portfolioId.trim())}` : null,
    {
      parse: (raw) => ensureRecordOrArray(raw, '组合详情'),
    },
  );

  // POST computations (user-triggered, keep as mutations)
  const optimizeApi = useApiMutation<OptData>({ parse: (raw) => ensureRecord(raw, '组合优化') as OptData });
  const riskApi = useApiMutation<RiskData>({ parse: (raw) => ensureRecord(raw, '组合风险') as RiskData });
  const stressApi = useApiMutation<StressData>({ parse: (raw) => ensureRecord(raw, '压力测试') as StressData });

  const loading =
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
  async function handleCreate() {
    if (!newName.trim()) return setFormError('请输入组合名称');
    try {
      const data = await createApi.triggerAsync(
        '/portfolio/create',
        { method: 'POST' },
        {
          name: newName.trim(),
          description: newDesc.trim(),
          initialCapital: newCapital.trim() || '1000000',
        },
      );
      const createdId =
        data && typeof data === 'object' && 'portfolioId' in data
          ? String((data as { portfolioId?: unknown }).portfolioId ?? '')
          : '';
      if (createdId) {
        setPortfolioId(createdId);
      }
      setNewName('');
      setNewDesc('');
    } catch {
      /* captured */
    }
  }
  async function handleAddHolding() {
    if (!portfolioId.trim()) return setFormError('请先输入 portfolioId');
    if (!validateHold()) return;
    try {
      await addHoldingApi.triggerAsync(
        '/portfolio/add-holding',
        { method: 'POST' },
        {
          portfolioId: portfolioId.trim(),
          code: holdTrimmed,
          shares: holdShares.trim() || '100',
          ...(holdCost.trim() ? { costPrice: holdCost.trim() } : {}),
        },
      );
      setHoldCode('');
      setHoldShares('100');
      setHoldCost('');
    } catch {
      /* captured */
    }
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

  // Optimization weights for PieChart
  const weightSlices = useMemo(() => {
    const w = optimizeApi.data?.optimization?.weights;
    if (!w) return [];
    if (Array.isArray(w)) return w.map((item) => ({ name: item.code, value: +(Number(item.weight) * 100).toFixed(1) }));
    return Object.entries(w).map(([k, v]) => ({ name: k, value: +(Number(v) * 100).toFixed(1) }));
  }, [optimizeApi.data]);

  // Risk contribution for BarChart
  const riskBars = useMemo(() => {
    const rc = riskApi.data?.riskMetrics?.riskContribution;
    if (!rc || typeof rc !== 'object') return [];
    return Object.entries(rc).map(([k, v]) => ({ label: k, value: +(Number(v) * 100).toFixed(2) }));
  }, [riskApi.data]);

  const stressScenarios = useMemo(() => {
    const s = stressApi.data?.stressResult?.scenarios;
    if (Array.isArray(s)) return s as Record<string, unknown>[];
    return extractArray(stressApi.data, 'scenarios', 'data') as Record<string, unknown>[];
  }, [stressApi.data]);
  const activePortfolioId = portfolioId.trim();
  const selectedPortfolio = useMemo(
    () => portfolioList.find((item) => String(item.id ?? '').trim() === activePortfolioId) ?? null,
    [portfolioList, activePortfolioId],
  );
  const portfolioDisplayName = selectedPortfolio ? String(selectedPortfolio.name ?? activePortfolioId) : '尚未选择组合';
  const portfolioNextStep = activePortfolioId ? '继续查看详情、加仓或执行分析' : '先创建新组合或在列表中选择组合';

  useEffect(() => {
    if (!workbenchHydrated) return;
    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged) return;
    const timer = window.setTimeout(() => {
      setPortfolioId(workbenchContext.portfolioId ?? '');
      setHoldCode(workbenchContext.stockCode ?? '');
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeWorkspaceId, setHoldCode, workbenchContext.portfolioId, workbenchContext.stockCode, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      portfolioId: activePortfolioId || null,
      stockCode: holdTrimmed || null,
      mode: activePortfolioId ? 'portfolio' : null,
    });
  }, [activePortfolioId, holdTrimmed, updateWorkbenchContext, workbenchHydrated]);

  usePageContext({
    pageKey: 'portfolio',
    title: '组合管理',
    summary: `当前选中组合 ${selectedPortfolio ? String(selectedPortfolio.name ?? activePortfolioId) : '未选择'}，组合总数 ${portfolioList.length}，持仓 ${detailHoldings.length} 条。`,
    stockCode: holdTrimmed || undefined,
    tags: [
      `${portfolioList.length} 个组合`,
      `${detailHoldings.length} 条持仓`,
      activePortfolioId ? `组合 ${activePortfolioId}` : '未选择组合',
    ],
    suggestions: [
      activePortfolioId ? `评估组合 ${activePortfolioId} 当前配置和风险` : '先选择一个组合，再评估配置和风险',
      '总结当前组合列表里最值得继续跟进的标的',
      '给出组合优化、风控和压力测试的下一步顺序',
    ],
    raw: {
      portfolioId: activePortfolioId || null,
      portfolioCount: portfolioList.length,
      holdingCount: detailHoldings.length,
      strategyCount: detailStrategies.length,
    },
  });

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
          await Promise.allSettled([listQ.refetch(), detailQ.refetch()]);
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
    ],
    [analyzeRisk, detailQ, listQ, optimize, runStress],
  );

  usePageActions(pageActions);

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      portfolioId,
      holdCode,
      holdShares,
      holdCost,
    }),
    [holdCode, holdCost, holdShares, portfolioId],
  );

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
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Portfolio Workspace</Badge>
              <Badge variant={activePortfolioId ? 'success' : 'warning'}>
                {activePortfolioId ? '已锁定当前组合' : '等待选择组合'}
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
              组合页不再让创建、加仓、优化和风险分析同时争夺注意力，而是把它们收束成一套连续的工作流。先锁定目标组合，再顺着持仓维护、配置优化和风险复盘依次推进。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => listQ.refetch()} className={heroPrimaryButtonCls}>
                刷新组合列表
              </button>
              <button type="button" onClick={optimize} className={heroSecondaryButtonCls}>
                优化配置
              </button>
              <button type="button" onClick={analyzeRisk} className={heroSecondaryButtonCls}>
                风险分析
              </button>
              <button type="button" onClick={runStress} className={heroSecondaryButtonCls}>
                压力测试
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前组合</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolioDisplayName}</div>
                <div className="mt-1 text-xs text-text-secondary">{activePortfolioId || '请先从列表选择'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">组合规模</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolioList.length}</div>
                <div className="mt-1 text-xs text-text-secondary">已创建组合总数</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">持仓 / 策略</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {detailHoldings.length} / {detailStrategies.length}
                </div>
                <div className="mt-1 text-xs text-text-secondary">持仓条目 / 策略配置</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{holdTrimmed || '待选标的'}</div>
                <div className="mt-1 text-xs text-text-secondary">{portfolioNextStep}</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{portfolioDisplayName}</div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  组合 ID：<span className="font-medium text-text-primary">{activePortfolioId || '未选择'}</span>
                </div>
                <div className={noteCardCls}>
                  待加仓股票：<span className="font-medium text-text-primary">{holdTrimmed || '未填写'}</span>
                </div>
                <div className={noteCardCls}>
                  当前资产：
                  <span className="font-medium text-text-primary">
                    {detailObj?.totalAssets != null
                      ? fmtNum(Number(detailObj.totalAssets), 2)
                      : selectedPortfolio
                        ? fmtNum(Number(selectedPortfolio.currentValue ?? 0), 2)
                        : '-'}
                  </span>
                </div>
              </div>
              <div className="mt-4">
                <AskAiButton
                  stockCode={holdTrimmed || undefined}
                  summary={`当前组合 ${portfolioDisplayName}，持仓 ${detailHoldings.length} 条`}
                  prompt="请评估当前组合结构、风险和下一步优化方向"
                />
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步动作</div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>{portfolioNextStep}</div>
                <div className={noteCardCls}>
                  {activePortfolioId
                    ? '先确认组合详情，再决定继续加仓、优化还是做风险复盘。'
                    : '先从下方列表点选组合，或创建一个新组合作为本次工作对象。'}
                </div>
                <div className={noteCardCls}>
                  {stressScenarios.length > 0
                    ? `已生成 ${stressScenarios.length} 个压力场景，可继续判断拖累来源。`
                    : '如果已经选好组合，下一步优先做风险分析或压力测试。'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="mt-0 p-4 sm:p-5">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
          <div>
            <div className="eyebrow">Operation Workspace</div>
            <h2 className="mt-2 mb-0 text-xl font-semibold text-text-primary">锁定组合后再展开动作</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              优先从组合列表点选目标组合；创建成功后也会自动选中。锁定对象之后，再继续做加仓、优化、风险分析和压力测试，能明显减少上下文切换。
            </p>
            <div className="toolbar-strip mt-4">
              <label
                htmlFor="portfolio-selected-id"
                className="flex min-w-[220px] flex-col gap-2 text-xs text-text-secondary"
              >
                <span>当前组合 ID</span>
                <input
                  id="portfolio-selected-id"
                  value={portfolioId}
                  onChange={(event) => {
                    setPortfolioId(event.target.value);
                    setFormError(null);
                  }}
                  placeholder="优先从列表选择；必要时可手动输入"
                  className="text-sm"
                />
              </label>
              <button type="button" onClick={() => listQ.refetch()} className={chipButtonCls}>
                组合列表
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!activePortfolioId) {
                    setFormError('请先选择组合');
                    return;
                  }
                  detailQ.refetch();
                }}
                className={chipButtonCls}
              >
                查看详情
              </button>
              <button type="button" onClick={optimize} className={chipButtonCls}>
                优化配置
              </button>
              <button type="button" onClick={analyzeRisk} className={chipButtonCls}>
                风险分析
              </button>
              <button type="button" onClick={runStress} className={chipButtonCls}>
                压力测试
              </button>
            </div>
          </div>

          <div className="panel-soft rounded-[24px] p-4">
            <div className="text-sm font-medium text-text-primary">当前上下文</div>
            <div className="mt-3 space-y-3">
              <div className={noteCardCls}>
                当前选中：
                <span className="font-medium text-text-primary">{portfolioDisplayName}</span>
              </div>
              <div className={noteCardCls}>
                组合总数：
                <span className="font-medium text-text-primary">{portfolioList.length}</span>
              </div>
              <div className={noteCardCls}>
                当前建议：
                <span className="font-medium text-text-primary">{portfolioNextStep}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="text-sm font-medium text-text-primary">创建组合</div>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              先定义名称、描述和初始资金，创建成功后会自动切到新组合，方便继续下一个动作。
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>组合名称</span>
                <input
                  id="portfolio-new-name"
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="输入组合名称"
                  className="text-sm"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>描述</span>
                <input
                  id="portfolio-new-desc"
                  value={newDesc}
                  onChange={(event) => setNewDesc(event.target.value)}
                  placeholder="可选"
                  className="text-sm"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-text-secondary md:col-span-2">
                <span>初始资金</span>
                <input
                  id="portfolio-new-capital"
                  value={newCapital}
                  onChange={(event) => setNewCapital(event.target.value)}
                  placeholder="1000000"
                  type="number"
                  className="text-sm"
                />
              </label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={createApi.isPending}
                className={heroPrimaryButtonCls}
              >
                {createApi.isPending ? '创建中...' : '创建组合'}
              </button>
            </div>
            {createApi.data != null ? (
              <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs text-success">
                创建成功，已自动选中新组合。
              </div>
            ) : null}
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="text-sm font-medium text-text-primary">
              {activePortfolioId ? `添加持仓（组合 ${activePortfolioId}）` : '添加持仓'}
            </div>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              {activePortfolioId
                ? '将持仓维护收在单独的 glass 面板里，便于在同一个上下文里完成加仓与复盘。'
                : '先选中一个组合，持仓表单才会绑定到正确的组合上下文。'}
            </p>
            {activePortfolioId ? (
              <>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <StockCodeInput
                    id="portfolio-holding-code"
                    label="股票代码"
                    value={holdCode}
                    onChange={setHoldCode}
                    error={holdCodeError}
                    placeholder="股票代码"
                  />
                  <label className="flex flex-col gap-2 text-xs text-text-secondary">
                    <span>股数</span>
                    <input
                      id="portfolio-holding-shares"
                      value={holdShares}
                      onChange={(event) => setHoldShares(event.target.value)}
                      placeholder="100"
                      type="number"
                      className="text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-2 text-xs text-text-secondary md:col-span-2">
                    <span>成本价</span>
                    <input
                      id="portfolio-holding-cost"
                      value={holdCost}
                      onChange={(event) => setHoldCost(event.target.value)}
                      placeholder="可选"
                      type="number"
                      step="0.01"
                      className="text-sm"
                    />
                  </label>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleAddHolding}
                    disabled={addHoldingApi.isPending}
                    className={heroPrimaryButtonCls}
                  >
                    {addHoldingApi.isPending ? '添加中...' : '添加持仓'}
                  </button>
                </div>
                {addHoldingApi.data != null ? (
                  <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs text-success">
                    添加成功，组合详情已刷新。
                  </div>
                ) : null}
              </>
            ) : (
              <div className="panel-soft mt-4 rounded-[22px] px-4 py-3 text-sm text-text-secondary">
                先从下方组合列表选择一条组合，或先创建新组合后再继续加仓。
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      {portfolioList.length > 0 ? (
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">组合列表</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                列表区承担“切换当前工作对象”的角色，点按一行就能把详情、加仓和分析统一切过去。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              rows={portfolioList}
              columns={[
                { key: 'id', label: '组合ID' },
                { key: 'name', label: '组合名称' },
                { key: 'description', label: '描述' },
                { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
                { key: 'strategyAllocationSummary', label: '策略配置' },
                {
                  key: 'initialCapital',
                  label: '初始资金',
                  align: 'right',
                  render: (value) => fmtNum(Number(value ?? 0), 2),
                },
                {
                  key: 'currentValue',
                  label: '当前资产',
                  align: 'right',
                  render: (value) => fmtNum(Number(value ?? 0), 2),
                },
                { key: 'createdAt', label: '创建时间' },
              ]}
              pageSize={10}
              searchable
              onExport={() => exportCSV(portfolioList, 'portfolio-list')}
              mobileCardRender={(row) => {
                const rowId = String(row.id ?? '-');
                const isActive = rowId === activePortfolioId;
                return (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{String(row.name ?? rowId)}</div>
                        <div className="text-xs text-text-secondary">组合 ID：{rowId}</div>
                      </div>
                      <div className={`text-xs ${isActive ? 'text-primary' : 'text-text-secondary'}`}>
                        {isActive ? '已选中' : '点按切换'}
                      </div>
                    </div>
                    <div className="text-xs text-text-secondary">描述：{String(row.description ?? '-')}</div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div>策略数：{String(row.strategyAllocationCount ?? '-')}</div>
                      <div>初始资金：{fmtNum(Number(row.initialCapital ?? 0), 2)}</div>
                      <div className="col-span-2">当前资产：{fmtNum(Number(row.currentValue ?? 0), 2)}</div>
                    </div>
                  </div>
                );
              }}
              onRowClick={(row) => {
                const selectedId = String(row.id ?? '').trim();
                if (!selectedId || selectedId === '-') return;
                setPortfolioId(selectedId);
                setFormError(null);
              }}
            />
          </div>
        </SectionCard>
      ) : null}

      {!activePortfolioId ? (
        <SectionCard className="mt-0 p-4">
          <EmptyState
            text="还没有选中组合。可以先从“组合列表”点选一条，或在上方创建新组合后继续。"
            hint="后续的详情、加仓、优化和压力测试都会围绕当前选中的组合展开。"
          />
        </SectionCard>
      ) : null}

      {detailObj ? (
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">组合详情</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                详情区负责回答“当前组合是什么、现在持了什么、策略权重如何分布”这三个问题。
              </p>
            </div>
          </div>
          <KpiGrid cols={4} className="mt-4">
            <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
            <KpiCard
              title="总资产"
              value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null}
            />
            <KpiCard
              title="总收益"
              value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null}
              change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null}
            />
            <KpiCard title="持仓数" value={detailHoldings.length || null} />
          </KpiGrid>

          {detailStrategies.length > 0 ? (
            <div className="mt-4">
              <div className="mb-2 text-sm font-medium text-text-primary">策略配置</div>
              <DataTable
                rows={detailStrategies}
                columns={[
                  {
                    key: 'strategyId',
                    label: '策略ID',
                    render: (_value, row) => String(row.strategyId ?? row.strategy_id ?? '-'),
                  },
                  { key: 'weight', label: '权重', align: 'right', render: (value) => fmtPct(Number(value ?? 0) * 100) },
                ]}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="text-sm font-medium text-text-primary">
                      策略 {String(row.strategyId ?? row.strategy_id ?? '-')}
                    </div>
                    <div className="text-xs text-text-secondary">权重：{fmtPct(Number(row.weight ?? 0) * 100)}</div>
                  </div>
                )}
              />
            </div>
          ) : null}

          {detailHoldings.length > 0 ? (
            <div className="mt-4">
              <div className="mb-2 text-sm font-medium text-text-primary">持仓明细</div>
              <DataTable
                rows={detailHoldings}
                pageSize={10}
                onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-sm font-medium text-text-primary">
                        {String(row.code ?? row.stockCode ?? '-')}
                      </div>
                      <div className="text-xs text-text-secondary">
                        数量：{String(row.shares ?? row.quantity ?? '-')}
                      </div>
                    </div>
                    <div className="text-xs text-text-secondary">
                      成本价：{fmtNum(Number(row.costPrice ?? row.cost_price ?? 0), 2)}
                    </div>
                    <div className="text-xs text-text-secondary">
                      市值：{fmtNum(Number(row.marketValue ?? row.market_value ?? 0), 2)}
                    </div>
                  </div>
                )}
              />
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      {weightSlices.length > 0 || riskBars.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {weightSlices.length > 0 ? (
            <SectionCard className="p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">配置权重</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    优化结果出来后，先看权重分布是否真的符合当前研究判断和风险预算。
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <PieChart data={weightSlices} donut height={300} />
              </div>
            </SectionCard>
          ) : null}
          {riskBars.length > 0 ? (
            <SectionCard className="p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">风险贡献度</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    把风险来源单独拉出来，能更快判断是单只股票、行业还是配置比例在拖累组合。
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <BarChart items={riskBars} colorByValue height={300} yAxisName="贡献 %" />
              </div>
            </SectionCard>
          ) : null}
        </div>
      ) : null}

      {optimizeApi.data?.optimization ? (
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">优化结果摘要</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                用核心 KPI 先判断这次优化是提升了收益效率，还是只是换了一套更冒险的配置。
              </p>
            </div>
          </div>
          <KpiGrid cols={3} className="mt-4">
            <KpiCard title="预期收益" value={fmtPct(Number(optimizeApi.data.optimization.expectedReturn))} />
            <KpiCard title="预期风险" value={fmtPct(Number(optimizeApi.data.optimization.expectedRisk))} />
            <KpiCard title="夏普比率" value={fmtNum(Number(optimizeApi.data.optimization.sharpe), 2)} />
          </KpiGrid>
        </SectionCard>
      ) : null}

      {riskApi.data?.riskMetrics ? (
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">风险指标</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                风险区用 VaR、CVaR、Beta 和波动率来确认这套组合是否还在你的容忍区间内。
              </p>
            </div>
          </div>
          <KpiGrid cols={5} className="mt-4">
            <KpiCard title="VaR (95%)" value={fmtPct(Number(riskApi.data.riskMetrics.var95))} />
            <KpiCard title="VaR (99%)" value={fmtPct(Number(riskApi.data.riskMetrics.var99))} />
            <KpiCard title="CVaR" value={fmtPct(Number(riskApi.data.riskMetrics.cvar))} />
            <KpiCard title="Beta" value={fmtNum(Number(riskApi.data.riskMetrics.beta), 2)} />
            <KpiCard title="波动率" value={fmtPct(Number(riskApi.data.riskMetrics.volatility))} />
          </KpiGrid>
        </SectionCard>
      ) : null}

      {stressScenarios.length > 0 ? (
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">压力测试</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                压力场景用于回答“如果市场波动加剧，这套组合最先会被什么拖累”。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              rows={stressScenarios}
              onExport={() => exportCSV(stressScenarios, 'stress-test')}
              mobileCardRender={(row) => (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-text-primary">{String(row.name ?? '-')}</div>
                  <div className="text-xs text-text-secondary">影响：{fmtPct(Number(row.impact ?? 0))}</div>
                  <div className="text-xs text-text-secondary">{String(row.description ?? '无额外说明')}</div>
                </div>
              )}
            />
          </div>
        </SectionCard>
      ) : null}
    </>
  );

  const secondaryContent = (
    <SectionCard className="p-4 sm:p-5">
      <div className="eyebrow">Portfolio Summary</div>
      <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">组合工作区摘要</h3>
      <div className="mt-4 grid gap-3">
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">组合概览</div>
          <div className="metric-value mt-3 text-[1.45rem]">{portfolioDisplayName}</div>
          <div className="mt-2 text-xs text-text-secondary">
            组合数 {portfolioList.length} · 持仓 {detailHoldings.length} · 策略 {detailStrategies.length}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">待执行动作</div>
          <div className="metric-value mt-3 text-[1.45rem]">{holdTrimmed || '未设标的'}</div>
          <div className="mt-2 text-xs text-text-secondary">
            股数 {holdShares || '-'} · 成本价 {holdCost || '未填写'}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            优化结果 {optimizeApi.data?.optimization ? '已生成' : '未生成'}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">分析进度</div>
          <div className="metric-value mt-3 text-[1.45rem]">
            {optimizeApi.data?.optimization ? '优化' : '-'} / {riskApi.data?.riskMetrics ? '风险' : '-'}
          </div>
          <div className="mt-2 text-xs text-text-secondary">压力场景 {stressScenarios.length} 条</div>
        </div>
        <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
          保存视图后，可以把当前组合、加仓参数和分析入口固定成一套组合复盘工作台，在策略页和绩效页之间来回复用。
        </div>
      </div>
    </SectionCard>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar pageKey="portfolio" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      <WorkspaceSplitLayout pageKey="portfolio" primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
