'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import ResponsiveResultWorkbench from '@/components/responsive-result-workbench';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import {
  Badge,
  ConfirmDialog,
  DataTable,
  KpiCard,
  KpiGrid,
  PageContainer,
  SectionCard,
  StockCodeInput,
  TabBar,
} from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { readTransactionConfirmations } from '@/lib/transaction-confirmations';

type HoldingOp = { portfolioId: string; code: string; shares: string; costPrice: string };
type BacktestResult = { artifactId?: string; backtestId?: unknown; [k: string]: unknown };
type MetricsData = {
  metrics?: { totalReturn?: unknown; sharpe?: unknown; maxDrawdown?: unknown };
  [k: string]: unknown;
};
type OptData = {
  optimization?: {
    expectedReturn?: unknown;
    expectedRisk?: unknown;
    sharpe?: unknown;
    weights?: unknown;
  };
  [k: string]: unknown;
};
type RiskData = {
  riskMetrics?: {
    var95?: unknown;
    var99?: unknown;
    cvar?: unknown;
    beta?: unknown;
    volatility?: unknown;
  };
  [k: string]: unknown;
};
type StressScenario = { name?: string; impact?: unknown; description?: string };
type StressData = { stressResult?: { scenarios?: StressScenario[] }; [k: string]: unknown };
type PortfolioDetailRecord = Record<string, unknown> & {
  strategyAllocations?: Array<Record<string, unknown>>;
};
type PendingPortfolioAction =
  | { type: 'create'; summary: string; payload: { name: string; initialCapital: string } }
  | { type: 'add'; summary: string; payload: HoldingOp }
  | { type: 'remove'; summary: string; portfolioId: string; code: string };
type WorkspaceTab = 'experiment' | 'deployment' | 'risk';

const WORKSPACE_TABS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: 'experiment', label: '试验' },
  { key: 'deployment', label: '落地' },
  { key: 'risk', label: '风控' },
];

function WorkbenchField({
  id,
  label,
  value,
  onChange,
  placeholder,
  className = '',
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <label htmlFor={id} className={`grid gap-1 text-xs text-text-secondary ${className}`}>
      <span>{label}</span>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full text-sm text-text-primary"
      />
    </label>
  );
}

export default function StrategyPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode();
  const [strategy, setStrategy] = useState('ma_cross');
  const [artifactId, setArtifactId] = useState('');
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>('experiment');
  const [formError, setFormError] = useState<string | null>(null);
  const [portfolioName, setPortfolioName] = useState('我的策略组合');
  const [holdingOp, setHoldingOp] = useState<HoldingOp>({
    portfolioId: '',
    code: '',
    shares: '100',
    costPrice: '1',
  });
  const [pendingAction, setPendingAction] = useState<PendingPortfolioAction | null>(null);
  const [backtestListPath, setBacktestListPath] = useState<string | null>(null);
  const [portfolioListPath, setPortfolioListPath] = useState<string | null>(null);
  const [portfolioDetailPath, setPortfolioDetailPath] = useState<string | null>(null);

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const metricsQ = useApiQuery<MetricsData>(
    artifactId ? `/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}` : null,
  );
  const backtestListQ = useApiQuery<unknown>(backtestListPath);
  const portfolioListQ = useApiQuery<unknown>(portfolioListPath);
  const portfolioDetailQ = useApiQuery<unknown>(portfolioDetailPath);

  const backtestApi = useApiMutation<BacktestResult>();
  const optimizeApi = useApiMutation<OptData>();
  const riskAnalysisApi = useApiMutation<RiskData>();
  const stressTestApi = useApiMutation<StressData>();
  const actionApi = useApiMutation<unknown>();

  const loading =
    backtestApi.isPending ||
    profileQ.isFetching ||
    metricsQ.isFetching ||
    backtestListQ.isFetching ||
    portfolioListQ.isFetching ||
    portfolioDetailQ.isFetching ||
    optimizeApi.isPending ||
    riskAnalysisApi.isPending ||
    stressTestApi.isPending ||
    actionApi.isPending;
  const error =
    formError ||
    backtestApi.error ||
    metricsQ.error ||
    backtestListQ.error ||
    portfolioListQ.error ||
    portfolioDetailQ.error ||
    optimizeApi.error ||
    riskAnalysisApi.error ||
    stressTestApi.error ||
    actionApi.error;
  const confirmPrefs = useMemo(() => readTransactionConfirmations(profileQ.data), [profileQ.data]);

  useEffect(() => {
    if (!trimmedCode) return;
    const id = window.setTimeout(() => {
      setHoldingOp((prev) => (prev.code ? prev : { ...prev, code: trimmedCode }));
    }, 0);
    return () => window.clearTimeout(id);
  }, [trimmedCode]);

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, { code: trimmedCode, strategy });
      setArtifactId(String(data?.artifactId ?? ''));
      setWorkspaceTab('experiment');
    } catch {
      /* captured */
    }
  }

  function loadBacktests() {
    const path = '/backtest/list?limit=10';
    if (path === backtestListPath) backtestListQ.refetch();
    else setBacktestListPath(path);
    setWorkspaceTab('experiment');
  }

  function loadMetrics(id = artifactId) {
    const nextId = id.trim();
    if (!nextId) {
      setFormError('请先提供回测制品 ID');
      return;
    }
    if (nextId !== artifactId) setArtifactId(nextId);
    else metricsQ.refetch();
    setWorkspaceTab('experiment');
  }

  async function executeCreatePortfolio(payload: { name: string; initialCapital: string }) {
    const data = await actionApi.triggerAsync('/portfolio/create', { method: 'POST' }, payload);
    const createdId =
      data && typeof data === 'object' && 'portfolioId' in data
        ? String((data as { portfolioId?: unknown }).portfolioId ?? '')
        : '';
    if (createdId) {
      setHoldingOp((prev) => ({ ...prev, portfolioId: createdId }));
      const detailPath = `/portfolio/get?portfolioId=${encodeURIComponent(createdId)}`;
      if (detailPath === portfolioDetailPath) portfolioDetailQ.refetch();
      else setPortfolioDetailPath(detailPath);
      setWorkspaceTab('deployment');
    }
    const listPath = '/portfolio/list';
    if (listPath === portfolioListPath) portfolioListQ.refetch();
    else setPortfolioListPath(listPath);
  }

  async function createPortfolio() {
    setFormError(null);
    if (!portfolioName.trim()) {
      setFormError('组合名称不能为空');
      return;
    }
    try {
      const payload = {
        name: portfolioName.trim(),
        initialCapital: '100000',
      };
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

  function loadPortfolios() {
    const path = '/portfolio/list';
    if (path === portfolioListPath) portfolioListQ.refetch();
    else setPortfolioListPath(path);
    setWorkspaceTab('deployment');
  }

  async function executeAddHolding(payload: HoldingOp) {
    await actionApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, payload);
    const path = '/portfolio/list';
    if (path === portfolioListPath) portfolioListQ.refetch();
    else setPortfolioListPath(path);
  }

  async function addHolding() {
    setFormError(null);
    if (!/^\d+$/.test(holdingOp.portfolioId) || !/^\d{6}$/.test(holdingOp.code)) {
      setFormError('持仓参数不合法');
      return;
    }
    try {
      if (confirmPrefs.portfolioRebalance) {
        setPendingAction({
          type: 'add',
          summary: `组合 ${holdingOp.portfolioId} · ${holdingOp.code} · ${holdingOp.shares} 股`,
          payload: holdingOp,
        });
        return;
      }
      await executeAddHolding(holdingOp);
      setWorkspaceTab('deployment');
    } catch {
      /* captured */
    }
  }

  async function executeRemoveHolding(portfolioId: string, code: string) {
    await actionApi.triggerAsync(
      `/portfolio/remove-holding?portfolioId=${encodeURIComponent(portfolioId)}&code=${code}`,
      { method: 'DELETE' },
    );
    const path = '/portfolio/list';
    if (path === portfolioListPath) portfolioListQ.refetch();
    else setPortfolioListPath(path);
  }

  async function removeHolding() {
    setFormError(null);
    if (!/^\d+$/.test(holdingOp.portfolioId) || !/^\d{6}$/.test(holdingOp.code)) {
      setFormError('持仓参数不合法');
      return;
    }
    try {
      if (confirmPrefs.portfolioRebalance) {
        setPendingAction({
          type: 'remove',
          summary: `组合 ${holdingOp.portfolioId} · 删除 ${holdingOp.code}`,
          portfolioId: holdingOp.portfolioId,
          code: holdingOp.code,
        });
        return;
      }
      await executeRemoveHolding(holdingOp.portfolioId, holdingOp.code);
      setWorkspaceTab('deployment');
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
    if (action.type === 'add') {
      await executeAddHolding(action.payload);
      return;
    }
    await executeRemoveHolding(action.portfolioId, action.code);
  }

  function loadPortfolioDetail() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    const path = `/portfolio/get?portfolioId=${encodeURIComponent(holdingOp.portfolioId)}`;
    if (path === portfolioDetailPath) portfolioDetailQ.refetch();
    else setPortfolioDetailPath(path);
    setWorkspaceTab('deployment');
  }

  function optimizePortfolio() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    optimizeApi.trigger('/portfolio/optimize', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
    setWorkspaceTab('risk');
  }

  function analyzeRisk() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    riskAnalysisApi.trigger('/portfolio/risk-analysis', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
    setWorkspaceTab('risk');
  }

  function runStressTest() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    stressTestApi.trigger('/portfolio/stress-test', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
    setWorkspaceTab('risk');
  }

  const metrics = metricsQ.data?.metrics;
  const optData = optimizeApi.data;
  const riskData = riskAnalysisApi.data;
  const stressData = stressTestApi.data;

  const detailObj = useMemo(() => {
    if (!portfolioDetailQ.data || typeof portfolioDetailQ.data !== 'object') return null;
    return portfolioDetailQ.data as PortfolioDetailRecord;
  }, [portfolioDetailQ.data]);
  const detailHoldings = useMemo(
    () => extractArray(portfolioDetailQ.data, 'holdings', 'positions', 'data') as Record<string, unknown>[],
    [portfolioDetailQ.data],
  );
  const detailStrategies = useMemo(
    () => extractArray(portfolioDetailQ.data, 'strategyAllocations') as Record<string, unknown>[],
    [portfolioDetailQ.data],
  );

  const backtestRows = useMemo(() => {
    const rows = extractArray(backtestListQ.data, 'results', 'items', 'data');
    return rows.map((item) => ({
      backtestId: String(item.id ?? item.backtest_id ?? '-'),
      code: String(item.code ?? '-'),
      strategy: String(item.strategy ?? '-'),
      startDate: String(item.start_date ?? '-'),
      endDate: String(item.end_date ?? '-'),
      totalReturn: item.total_return,
      maxDrawdown: item.max_drawdown,
      sharpe: item.sharpe_ratio,
      createdAt: String(item.created_at ?? '-'),
    }));
  }, [backtestListQ.data]);

  const portfolioRows = useMemo(
    () =>
      extractArray(portfolioListQ.data, 'portfolios', 'items', 'data').map((item) => ({
        id: item.id ?? '-',
        name: item.name ?? '-',
        description: item.description ?? '-',
        strategyAllocationCount: item.strategyAllocationCount ?? 0,
        strategyAllocationSummary: item.strategyAllocationSummary ?? '-',
        currentValue: item.currentValue,
        createdAt: item.createdAt ?? '-',
      })),
    [portfolioListQ.data],
  );

  const optWeights = useMemo(() => {
    const weights = optData?.optimization?.weights;
    if (Array.isArray(weights)) return weights as Record<string, unknown>[];
    if (weights && typeof weights === 'object') {
      return Object.entries(weights as Record<string, unknown>).map(([key, value]) => ({ code: key, weight: value }));
    }
    return [] as Record<string, unknown>[];
  }, [optData]);

  const stressScenarios = useMemo(() => {
    const scenarios = stressData?.stressResult?.scenarios;
    if (Array.isArray(scenarios)) return scenarios as Record<string, unknown>[];
    return extractArray(stressData, 'scenarios', 'data') as Record<string, unknown>[];
  }, [stressData]);

  const activeWorkspaceLabel = WORKSPACE_TABS.find((item) => item.key === workspaceTab)?.label ?? '试验';
  const currentPortfolioId = holdingOp.portfolioId || '未绑定';
  const nextStepLabel = artifactId
    ? currentPortfolioId !== '未绑定'
      ? '继续查看组合详情、优化或压力测试'
      : '继续创建组合，把试验结果落地'
    : '先跑出第一份回测制品';

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      code,
      strategy,
      artifactId,
      portfolioId: holdingOp.portfolioId,
      holdingCode: holdingOp.code,
      holdingShares: holdingOp.shares,
      holdingCost: holdingOp.costPrice,
      workspaceTab,
    }),
    [artifactId, code, holdingOp.code, holdingOp.costPrice, holdingOp.portfolioId, holdingOp.shares, strategy, workspaceTab],
  );
  const strategyPageActions = [
    {
      id: 'strategy.open-experiment',
      label: '回到试验区',
      description: '切回回测与制品试验流程',
      keywords: ['回测', '试验'],
      scope: 'page' as const,
      pageKey: 'strategy',
      run: () => {
        setWorkspaceTab('experiment');
        return { message: '已切到试验区' };
      },
    },
    {
      id: 'strategy.load-portfolios',
      label: '加载组合列表',
      description: '拉取组合列表并切到落地区',
      keywords: ['组合', '落地'],
      scope: 'page' as const,
      pageKey: 'strategy',
      run: () => {
        loadPortfolios();
        return { message: '已加载组合列表' };
      },
    },
    {
      id: 'strategy.open-risk',
      label: '切到风控区',
      description: '切到优化、风险分析和压力测试视图',
      keywords: ['风控', '优化', '压力测试'],
      scope: 'page' as const,
      pageKey: 'strategy',
      run: () => {
        setWorkspaceTab('risk');
        return { message: '已切到风控区' };
      },
    },
  ];
  usePageActions(strategyPageActions);

  const applyView = useCallback((snapshot: Record<string, unknown>) => {
    if (typeof snapshot.code === 'string') setCode(snapshot.code);
    if (typeof snapshot.strategy === 'string') setStrategy(snapshot.strategy);
    if (typeof snapshot.artifactId === 'string') setArtifactId(snapshot.artifactId);
    if (typeof snapshot.workspaceTab === 'string' && WORKSPACE_TABS.some((item) => item.key === snapshot.workspaceTab)) {
      setWorkspaceTab(snapshot.workspaceTab as WorkspaceTab);
    }
    setHoldingOp((prev) => ({
      portfolioId: typeof snapshot.portfolioId === 'string' ? snapshot.portfolioId : prev.portfolioId,
      code: typeof snapshot.holdingCode === 'string' ? snapshot.holdingCode : prev.code,
      shares:
        typeof snapshot.holdingShares === 'string' || typeof snapshot.holdingShares === 'number'
          ? String(snapshot.holdingShares)
          : prev.shares,
      costPrice:
        typeof snapshot.holdingCost === 'string' || typeof snapshot.holdingCost === 'number'
          ? String(snapshot.holdingCost)
          : prev.costPrice,
    }));
  }, [setCode]);

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';
  const strategySummary = `当前视图 ${activeWorkspaceLabel}，当前标的 ${trimmedCode || '-'}，策略 ${strategy}，回测制品 ${artifactId || '-'}，当前组合 ${currentPortfolioId}。`;
  const strategyResult = buildLocalResultContract({
    summary: strategySummary,
    availableViews: metrics || portfolioRows.length > 1 || stressScenarios.length > 0 ? ['compare', 'visual'] : [],
    pageActions: strategyPageActions,
    preferredActionIds: ['strategy.open-experiment', 'strategy.load-portfolios', 'strategy.open-risk'],
    recommendedLinks: [
      { id: 'strategy-link-portfolio', label: '去组合页', href: trimmedCode ? `/portfolio?from=strategy&code=${encodeURIComponent(trimmedCode)}` : '/portfolio?from=strategy' },
      { id: 'strategy-link-backtest', label: '去回测页', href: trimmedCode ? `/backtest?code=${encodeURIComponent(trimmedCode)}` : '/backtest' },
      { id: 'strategy-link-paper', label: '去模拟盘', href: trimmedCode ? `/paper-trading?from=strategy&code=${encodeURIComponent(trimmedCode)}` : '/paper-trading?from=strategy' },
      { id: 'strategy-link-assistant', label: '继续追问 Copilot', href: trimmedCode ? `/assistant?from=strategy&code=${encodeURIComponent(trimmedCode)}` : '/assistant?from=strategy' },
    ],
    evidence: [
      { label: '当前标的', value: trimmedCode || '-' },
      { label: '策略标识', value: strategy },
      { label: '当前视图', value: activeWorkspaceLabel },
      { label: '回测制品', value: artifactId || '-' },
      { label: '组合数量', value: String(portfolioRows.length) },
      { label: '压力场景', value: String(stressScenarios.length) },
    ],
    riskNotes: [
      ...(error ? [error] : []),
      ...(!artifactId ? ['当前还没有生成回测制品。'] : []),
      ...(!holdingOp.portfolioId ? ['当前还没有绑定组合 ID，后续落地与风险分析会受限。'] : []),
      ...(riskData?.riskMetrics?.var95 != null && Number(riskData.riskMetrics.var95) < -0.1 ? ['组合 VaR(95%) 较高，进入执行前建议先复核风险暴露。'] : []),
    ],
    platformMeta: {
      sourceTool: 'strategy-workspace',
      sourceChain: ['backtest', 'portfolio', 'risk-analysis', 'stress-test'],
      degraded: Boolean(error),
      fallbackReason: [error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('strategy', `复查策略工作台 ${strategy}`, '/strategy', 'strategy-workspace-review', {
      code: trimmedCode || null,
      strategy,
      artifactId,
      portfolioId: holdingOp.portfolioId || null,
      workspaceTab,
    }),
  });
  usePageContext({
    pageKey: 'strategy',
    title: '策略工作台',
    summary: strategySummary,
    objectType: 'strategy',
    objectId: strategy,
    resultType: 'strategy-workspace',
    tags: [
      strategy,
      trimmedCode || '未输入标的',
      activeWorkspaceLabel,
      artifactId ? '已生成回测制品' : '待生成回测制品',
    ],
    suggestions: [
      '总结当前策略工作台离真正落地还差哪一步',
      '如果要继续推进，先做回测、组合落地还是风险分析',
      '解释当前回测制品、组合和风控结果之间的衔接关系',
    ],
    recommendedActions: strategyResult.recommendedActions ?? [],
    recommendedLinks: strategyResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(strategyResult.evidence),
    riskNotes: strategyResult.riskNotes ?? [],
    freshness: strategyResult.freshness ?? null,
    raw: {
      code: trimmedCode || null,
      strategy,
      artifactId,
      portfolioId: holdingOp.portfolioId || null,
      workspaceTab,
      portfolioCount: portfolioRows.length,
      stressScenarioCount: stressScenarios.length,
    },
  });

  const experimentContent = (
    <SectionCard tabAttached>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">运行新的回测</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            先确认标的和策略标识，再运行回测并保留制品 ID 供后续指标刷新。
          </p>
          <form onSubmit={runBacktest} className="mt-4 grid gap-3 lg:grid-cols-[160px_220px_auto_auto] lg:items-end">
            <StockCodeInput
              id="strategy-backtest-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
            />
            <WorkbenchField
              id="strategy-backtest-name"
              label="策略标识"
              value={strategy}
              onChange={setStrategy}
              placeholder="例如 ma_cross"
            />
            <button type="submit" className={heroPrimaryButtonCls}>
              运行回测
            </button>
            <button type="button" onClick={loadBacktests} className={heroSecondaryButtonCls}>
              最近回测
            </button>
          </form>
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">回测结果定位</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            把最近一次回测生成的制品 ID 留在手边，后续刷新收益指标时不需要重新跑完整流程。
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,260px)_auto] md:items-end">
            <WorkbenchField
              id="strategy-artifact-id"
              label="制品 ID"
              value={artifactId}
              onChange={setArtifactId}
              placeholder="粘贴或保留最近一次回测的制品 ID"
            />
            <div className="flex gap-2">
              <button type="button" onClick={() => loadMetrics()} className={heroSecondaryButtonCls}>
                刷新指标
              </button>
            </div>
          </div>
        </div>
      </div>

      {metrics ? (
        <KpiGrid cols={3} className="mt-4">
          <KpiCard title="总收益" value={metrics.totalReturn != null ? fmtPct(Number(metrics.totalReturn)) : null} />
          <KpiCard title="Sharpe" value={metrics.sharpe != null ? fmtNum(Number(metrics.sharpe), 2) : null} />
          <KpiCard
            title="最大回撤"
            value={metrics.maxDrawdown != null ? fmtPct(Number(metrics.maxDrawdown)) : null}
          />
        </KpiGrid>
      ) : null}

      {backtestRows.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">最近回测</div>
          <DataTable
            rows={backtestRows}
            columns={[
              { key: 'backtestId', label: '回测ID' },
              { key: 'code', label: '代码' },
              { key: 'strategy', label: '策略' },
              { key: 'startDate', label: '开始日期' },
              { key: 'endDate', label: '结束日期' },
              { key: 'totalReturn', label: '总收益', align: 'right', render: (value) => fmtPct(Number(value ?? 0)) },
              { key: 'maxDrawdown', label: '最大回撤', align: 'right', render: (value) => fmtPct(Number(value ?? 0)) },
              { key: 'sharpe', label: 'Sharpe', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'createdAt', label: '创建时间' },
            ]}
            pageSize={6}
            searchable
            onExport={() => exportCSV(backtestRows, 'strategy-backtests')}
          />
        </div>
      ) : null}
    </SectionCard>
  );

  const deploymentContent = (
    <SectionCard tabAttached>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">创建组合</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            先建立组合容器，再继续做持仓落地和后续分析。
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,240px)_auto_auto] md:items-end">
            <WorkbenchField
              id="strategy-portfolio-name"
              label="组合名称"
              value={portfolioName}
              onChange={setPortfolioName}
              placeholder="例如 我的策略组合"
            />
            <button type="button" onClick={createPortfolio} className={heroPrimaryButtonCls}>
              创建组合
            </button>
            <button type="button" onClick={loadPortfolios} className={heroSecondaryButtonCls}>
              组合列表
            </button>
          </div>
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">持仓与详情操作</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            把组合 ID、标的、股数和成本价收在同一块里，便于做加仓、减仓和详情查看。
          </p>
          <div className="mt-4 grid gap-3 lg:grid-cols-[140px_140px_120px_120px_auto_auto_auto] lg:items-end">
            <WorkbenchField
              id="strategy-portfolio-id"
              label="组合 ID"
              value={holdingOp.portfolioId}
              onChange={(value) => setHoldingOp({ ...holdingOp, portfolioId: value })}
              placeholder="输入 portfolioId"
            />
            <WorkbenchField
              id="strategy-holding-code"
              label="股票代码"
              value={holdingOp.code}
              onChange={(value) => setHoldingOp({ ...holdingOp, code: value.slice(0, 6) })}
              placeholder="6 位股票代码"
            />
            <WorkbenchField
              id="strategy-holding-shares"
              label="持仓股数"
              value={holdingOp.shares}
              onChange={(value) => setHoldingOp({ ...holdingOp, shares: value })}
              placeholder="例如 100"
            />
            <WorkbenchField
              id="strategy-holding-cost"
              label="成本价"
              value={holdingOp.costPrice}
              onChange={(value) => setHoldingOp({ ...holdingOp, costPrice: value })}
              placeholder="例如 12.56"
            />
            <button type="button" onClick={addHolding} className={heroSecondaryButtonCls}>
              加仓
            </button>
            <button type="button" onClick={removeHolding} className={heroSecondaryButtonCls}>
              减仓
            </button>
            <button type="button" onClick={loadPortfolioDetail} className={heroSecondaryButtonCls}>
              查看详情
            </button>
          </div>
        </div>
      </div>

      {portfolioRows.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">组合列表</div>
          <DataTable
            rows={portfolioRows}
            columns={[
              { key: 'id', label: '组合ID' },
              { key: 'name', label: '组合名称' },
              { key: 'description', label: '描述' },
              { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
              { key: 'strategyAllocationSummary', label: '策略配置' },
              { key: 'currentValue', label: '当前资产', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'createdAt', label: '创建时间' },
            ]}
            pageSize={6}
            searchable
            onExport={() => exportCSV(portfolioRows, 'strategy-portfolios')}
            onRowClick={(row) => {
              const selectedId = String(row.id ?? '').trim();
              if (!selectedId || selectedId === '-') return;
              setHoldingOp((prev) => ({ ...prev, portfolioId: selectedId }));
              const detailPath = `/portfolio/get?portfolioId=${encodeURIComponent(selectedId)}`;
              if (detailPath === portfolioDetailPath) portfolioDetailQ.refetch();
              else setPortfolioDetailPath(detailPath);
            }}
          />
        </div>
      ) : null}

      {detailObj ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">组合详情</div>
          <KpiGrid cols={4} className="mb-4">
            <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
            <KpiCard title="总资产" value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null} />
            <KpiCard
              title="总收益"
              value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null}
              change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null}
            />
            <KpiCard title="持仓数" value={detailHoldings.length || null} />
          </KpiGrid>
          {detailStrategies.length > 0 ? (
            <DataTable
              rows={detailStrategies}
              columns={[
                {
                  key: 'strategyId',
                  label: '策略ID',
                  render: (_value, row) => String(row.strategyId ?? row.strategy_id ?? '-'),
                },
                { key: 'weight', label: '权重', align: 'right', render: (value) => fmtPct(Number(value ?? 0)) },
              ]}
              className="mb-4"
            />
          ) : null}
          {detailHoldings.length > 0 ? (
            <DataTable
              rows={detailHoldings}
              pageSize={10}
              onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')}
            />
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  );

  const riskContent = (
    <SectionCard tabAttached>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <div className="text-sm font-medium text-text-primary">风控动作</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            以下动作默认基于当前填写的组合 ID 执行，适合在持仓落地后继续做优化、风险和压力校验。
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={optimizePortfolio} className={heroPrimaryButtonCls}>
              优化配置
            </button>
            <button type="button" onClick={analyzeRisk} className={heroSecondaryButtonCls}>
              风险分析
            </button>
            <button type="button" onClick={runStressTest} className={heroSecondaryButtonCls}>
              压力测试
            </button>
          </div>
        </div>

        <div className="panel-soft rounded-[24px] p-4">
          <div className="text-sm font-medium text-text-primary">当前执行上下文</div>
          <div className="mt-3 space-y-3">
            <div className={noteCardCls}>组合 ID：{holdingOp.portfolioId || '未填写'}</div>
            <div className={noteCardCls}>优化结果：{optData?.optimization ? '已生成' : '未生成'}</div>
            <div className={noteCardCls}>压力场景：{stressScenarios.length} 条</div>
          </div>
        </div>
      </div>

      {optData?.optimization ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">优化结果</div>
          <KpiGrid cols={3} className="mb-4">
            <KpiCard
              title="预期收益"
              value={optData.optimization.expectedReturn != null ? fmtPct(Number(optData.optimization.expectedReturn)) : null}
            />
            <KpiCard
              title="预期风险"
              value={optData.optimization.expectedRisk != null ? fmtPct(Number(optData.optimization.expectedRisk)) : null}
            />
            <KpiCard
              title="夏普比率"
              value={optData.optimization.sharpe != null ? fmtNum(Number(optData.optimization.sharpe), 2) : null}
            />
          </KpiGrid>
          {optWeights.length > 0 ? (
            <DataTable rows={optWeights} onExport={() => exportCSV(optWeights, 'optimization-weights')} />
          ) : null}
        </div>
      ) : null}

      {riskData?.riskMetrics ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">风险指标</div>
          <KpiGrid cols={5}>
            <KpiCard title="VaR (95%)" value={riskData.riskMetrics.var95 != null ? fmtPct(Number(riskData.riskMetrics.var95)) : null} />
            <KpiCard title="VaR (99%)" value={riskData.riskMetrics.var99 != null ? fmtPct(Number(riskData.riskMetrics.var99)) : null} />
            <KpiCard title="CVaR" value={riskData.riskMetrics.cvar != null ? fmtPct(Number(riskData.riskMetrics.cvar)) : null} />
            <KpiCard title="Beta" value={riskData.riskMetrics.beta != null ? fmtNum(Number(riskData.riskMetrics.beta), 2) : null} />
            <KpiCard title="波动率" value={riskData.riskMetrics.volatility != null ? fmtPct(Number(riskData.riskMetrics.volatility)) : null} />
          </KpiGrid>
        </div>
      ) : null}

      {stressScenarios.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-text-primary">压力测试</div>
          <DataTable
            rows={stressScenarios}
            columns={[
              { key: 'name', label: '场景' },
              {
                key: 'impact',
                label: '影响',
                align: 'right',
                render: (value: unknown) => {
                  const amount = Number(value);
                  return <span style={{ color: amount < 0 ? '#ef4444' : '#10b981' }}>{fmtPct(amount)}</span>;
                },
              },
              { key: 'description', label: '描述' },
            ]}
            onExport={() => exportCSV(stressScenarios, 'stress-test')}
          />
        </div>
      ) : null}
    </SectionCard>
  );

  const primaryContent = (
    <>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">策略工作台</Badge>
              <Badge variant={artifactId ? 'success' : 'warning'}>
                {artifactId ? '已形成回测制品' : '等待生成回测制品'}
              </Badge>
              <Badge variant={holdingOp.portfolioId ? 'success' : 'neutral'}>
                {holdingOp.portfolioId ? `组合 ${holdingOp.portfolioId}` : '尚未绑定组合'}
              </Badge>
              <Badge variant="neutral">{activeWorkspaceLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              策略工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              先跑回测形成可追踪制品，再切到组合落地，最后进入优化和风控，按阶段推进策略研究。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => setWorkspaceTab('experiment')} className={heroPrimaryButtonCls}>
                回到试验区
              </button>
              <button type="button" onClick={loadPortfolios} className={heroSecondaryButtonCls}>
                加载组合列表
              </button>
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前视图 {activeWorkspaceLabel} ｜ 当前标的 {trimmedCode || '-'} ｜ 策略 {strategy}
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                回测制品 {artifactId || '-'} ｜ 当前组合 {currentPortfolioId} ｜ 持仓 {detailHoldings.length} 条
              </p>
            </div>
          </div>

          <details className={sidePanelCls} open>
            <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              当前上下文与下一步
            </summary>
            <div className="mt-4 space-y-3">
              <div className={noteCardCls}>当前标的：{trimmedCode || '未输入'} ｜ 策略：{strategy}</div>
              <div className={noteCardCls}>回测制品：{artifactId || '尚未生成'} ｜ 组合：{currentPortfolioId}</div>
              <div className={noteCardCls}>{nextStepLabel}</div>
            </div>
          </details>
        </div>
      </section>

      <ResponsiveResultWorkbench pageKey="strategy" title="策略结果工作台" result={strategyResult} />

      {loading ? <LoadingState text="正在运行策略任务..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">策略流程</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">当前主任务</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              按试验、落地和风控三个阶段切换，便于复查每一步的输入和输出。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            回测 {backtestRows.length} 条 ｜ 组合 {portfolioRows.length} 个 ｜ 压力场景 {stressScenarios.length} 条
          </div>
        </div>
        <div className="mt-4">
          <TabBar tabs={WORKSPACE_TABS} active={workspaceTab} onChange={(key) => setWorkspaceTab(key as WorkspaceTab)} />
        </div>
        {workspaceTab === 'experiment' ? experimentContent : null}
        {workspaceTab === 'deployment' ? deploymentContent : null}
        {workspaceTab === 'risk' ? riskContent : null}
      </div>
    </>
  );

  const summaryPanel = (
    <div className={sidePanelCls}>
      <div className="text-sm font-medium text-text-primary">摘要</div>
      <div className="mt-3 space-y-3 text-xs text-text-secondary">
        <div className={noteCardCls}>
          回测制品：<span className="font-medium text-text-primary">{artifactId || '尚未生成'}</span>
        </div>
        <div className={noteCardCls}>
          当前组合：<span className="font-medium text-text-primary">{currentPortfolioId}</span>
        </div>
        <div className={noteCardCls}>
          当前指标：
          <span className="font-medium text-text-primary">
            {metrics?.totalReturn != null ? ` 总收益 ${fmtPct(Number(metrics.totalReturn))}` : ' 等待回测'}
          </span>
        </div>
      </div>
    </div>
  );

  const nextStepsPanel = (
    <div className={sidePanelCls}>
      <div className="text-sm font-medium text-text-primary">下一步动作</div>
      <div className="mt-3 space-y-3">
        <div className={noteCardCls}>1. 先在试验区跑回测，确认收益和回撤是否可接受。</div>
        <div className={noteCardCls}>2. 再创建或选中组合，把持仓和策略配置落到组合里。</div>
        <div className={noteCardCls}>3. 最后执行优化、风险分析和压力测试，确认不是单场景有效。</div>
      </div>
    </div>
  );

  const mobileSummary = (
    <div className="panel-soft rounded-[24px] px-4 py-3 text-sm text-text-secondary">
      {activeWorkspaceLabel} ｜ 回测制品 {artifactId || '-'} ｜ 组合 {currentPortfolioId}
    </div>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar
        pageKey="strategy"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />
      <WorkspaceSplitLayout
        pageKey="strategy"
        primary={primaryContent}
        secondary={summaryPanel}
        secondaryPanels={[
          { key: 'summary', label: '摘要', content: summaryPanel },
          { key: 'next', label: '下一步', content: nextStepsPanel },
        ]}
        mobileSummary={mobileSummary}
        maxDefaultSections={0}
      />
      <ConfirmDialog
        open={pendingAction != null}
        title={
          pendingAction?.type === 'create'
            ? '确认创建组合'
            : pendingAction?.type === 'remove'
              ? '确认删除持仓'
              : '确认添加持仓'
        }
        confirmText={
          pendingAction?.type === 'create'
            ? '确认创建'
            : pendingAction?.type === 'remove'
              ? '确认删除'
              : '确认添加'
        }
        danger={pendingAction?.type === 'remove'}
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
