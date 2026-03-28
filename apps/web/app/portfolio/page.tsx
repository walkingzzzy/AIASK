'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, StockCodeInput } from '@/components/ui';
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

type OptData = { optimization?: { expectedReturn?: number; expectedRisk?: number; sharpe?: number; weights?: Record<string, number> | Array<{ code: string; weight: number }> } };
type RiskData = { riskMetrics?: { var95?: number; var99?: number; cvar?: number; beta?: number; volatility?: number; riskContribution?: Record<string, number> } };
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
  const { code: holdCode, setCode: setHoldCode, codeError: holdCodeError, validate: validateHold, trimmedCode: holdTrimmed } = useStockCode();
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

  const loading = listQ.isFetching || detailQ.isFetching || optimizeApi.isPending || riskApi.isPending || stressApi.isPending || createApi.isPending || addHoldingApi.isPending;
  const error = formError || listQ.error || detailQ.error || optimizeApi.error || riskApi.error || stressApi.error || createApi.error || addHoldingApi.error;

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
      const data = await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, {
        name: newName.trim(), description: newDesc.trim(), initialCapital: newCapital.trim() || '1000000',
      });
      const createdId = data && typeof data === 'object' && 'portfolioId' in data ? String((data as { portfolioId?: unknown }).portfolioId ?? '') : '';
      if (createdId) {
        setPortfolioId(createdId);
      }
      setNewName(''); setNewDesc('');
    } catch { /* captured */ }
  }
  async function handleAddHolding() {
    if (!portfolioId.trim()) return setFormError('请先输入 portfolioId');
    if (!validateHold()) return;
    try {
      await addHoldingApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, {
        portfolioId: portfolioId.trim(),
        code: holdTrimmed,
        shares: holdShares.trim() || '100',
        ...(holdCost.trim() ? { costPrice: holdCost.trim() } : {}),
      });
      setHoldCode(''); setHoldShares('100'); setHoldCost('');
    } catch { /* captured */ }
  }

  const detailObj = useMemo(() => {
    if (!detailQ.data || typeof detailQ.data !== 'object') return null;
    return detailQ.data as PortfolioDetailRecord;
  }, [detailQ.data]);
  const detailHoldings = useMemo(() => extractArray(detailQ.data, 'holdings', 'positions', 'data') as Record<string, unknown>[], [detailQ.data]);
  const detailStrategies = useMemo(() => extractArray(detailQ.data, 'strategyAllocations') as Record<string, unknown>[], [detailQ.data]);
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

  const pageActions = useMemo(() => [
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
  ], [analyzeRisk, detailQ, listQ, optimize, runStress]);

  usePageActions(pageActions);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      portfolioId,
      holdCode,
      holdShares,
      holdCost,
    }),
    [holdCode, holdCost, holdShares, portfolioId],
  );

  const applyView = useCallback((snapshot: Record<string, unknown>) => {
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
  }, [setHoldCode]);

  const primaryContent = (
    <>
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_360px]">
        <div className="rounded-[28px] border border-border bg-surface p-6 shadow-sm">
          <div className="eyebrow">Portfolio Workspace</div>
          <h1 className="mt-3">先确认组合状态，再决定加仓、优化还是做风险复盘。</h1>
          <p className="page-lead mt-3 mb-0">
            组合页首屏不再让创建、加仓、分析按钮同时抢注意力。先锁定当前组合，再按“持仓维护、配置优化、风险复盘”的顺序推进。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-full border border-border bg-surface-alt/72 px-3 py-1 text-xs text-text-secondary">
              当前组合 {portfolioDisplayName}
            </span>
            <span className="rounded-full border border-border bg-surface-alt/72 px-3 py-1 text-xs text-text-secondary">
              组合总数 {portfolioList.length}
            </span>
            <span className="rounded-full border border-border bg-surface-alt/72 px-3 py-1 text-xs text-text-secondary">
              持仓 {detailHoldings.length} 条
            </span>
          </div>
        </div>
        <SectionCard className="mt-0">
          <div className="eyebrow">当前聚焦</div>
          <h2 className="mt-2">{portfolioDisplayName}</h2>
          <div className="mt-4 space-y-3 text-sm text-text-secondary">
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">组合 ID</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{activePortfolioId || '未选择'}</div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">待加仓股票</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{holdTrimmed || '未填写'}</div>
            </div>
            <div className="rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3">
              <div className="metric-label">下一步</div>
              <div className="mt-2 text-sm font-medium text-text-primary">{portfolioNextStep}</div>
            </div>
          </div>
          <div className="mt-4">
            <AskAiButton
              stockCode={holdTrimmed || undefined}
              summary={`当前组合 ${portfolioDisplayName}，持仓 ${detailHoldings.length} 条`}
              prompt="请评估当前组合结构、风险和下一步优化方向"
            />
          </div>
        </SectionCard>
      </section>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="mt-0 p-3">
        <h2 className="mt-0 text-base font-semibold">操作台</h2>
        <p className="text-sm text-text-secondary mt-1 mb-3">优先从下方组合列表点选目标组合；创建成功后也会自动选中，随后再执行加仓、优化、风险分析和压力测试。</p>
        <div className="mb-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-[18px] border border-border bg-surface-alt/72 p-3">
            <div className="text-xs text-text-secondary">当前选中</div>
            <div className="mt-1 text-sm font-medium">{portfolioDisplayName}</div>
            <div className="mt-1 text-xs text-text-secondary">{activePortfolioId || '请从列表点选一条组合后继续'}</div>
          </div>
          <div className="rounded-[18px] border border-border bg-surface-alt/72 p-3">
            <div className="text-xs text-text-secondary">组合总数</div>
            <div className="mt-1 text-sm font-medium">{portfolioList.length}</div>
            <div className="mt-1 text-xs text-text-secondary">支持从列表直接切换查看详情</div>
          </div>
          <div className="rounded-[18px] border border-border bg-surface-alt/72 p-3">
            <div className="text-xs text-text-secondary">下一步建议</div>
            <div className="mt-1 text-sm font-medium">{portfolioNextStep}</div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap items-end">
          <label htmlFor="portfolio-selected-id" className="grid gap-1 text-xs text-text-secondary">
            <span>当前组合 ID</span>
            <input id="portfolio-selected-id" value={portfolioId} onChange={(e) => { setPortfolioId(e.target.value); setFormError(null); }} placeholder="优先从列表选择；必要时可手动输入" className="w-[220px] px-2 py-1 border border-border rounded text-sm" />
          </label>
          <button type="button" onClick={() => listQ.refetch()}>组合列表</button>
          <button type="button" onClick={() => { if (!activePortfolioId) { setFormError('请先选择组合'); return; } detailQ.refetch(); }}>查看详情</button>
          <button type="button" onClick={optimize}>优化配置</button>
          <button type="button" onClick={analyzeRisk}>风险分析</button>
          <button type="button" onClick={runStress}>压力测试</button>
        </div>
      </SectionCard>

      {/* Create Portfolio */}
      <SectionCard className="mt-0 p-4">
        <h3 className="mt-0">创建组合</h3>
        <div className="flex gap-2 flex-wrap items-end">
          <label htmlFor="portfolio-new-name" className="grid gap-1 text-xs text-text-secondary">
            <span>组合名称</span>
            <input id="portfolio-new-name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="输入组合名称" className="w-[160px] px-2 py-1 rounded text-sm" />
          </label>
          <label htmlFor="portfolio-new-desc" className="grid gap-1 text-xs text-text-secondary">
            <span>描述</span>
            <input id="portfolio-new-desc" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="可选" className="w-[200px] px-2 py-1 rounded text-sm" />
          </label>
          <label htmlFor="portfolio-new-capital" className="grid gap-1 text-xs text-text-secondary">
            <span>初始资金</span>
            <input id="portfolio-new-capital" value={newCapital} onChange={(e) => setNewCapital(e.target.value)} placeholder="1000000" type="number" className="w-[140px] px-2 py-1 rounded text-sm" />
          </label>
          <button type="button" onClick={handleCreate} disabled={createApi.isPending}>{createApi.isPending ? '创建中...' : '创建'}</button>
        </div>
        {createApi.data != null && <p className="text-success text-xs mt-2">创建成功，已自动选中新组合。</p>}
      </SectionCard>

      {/* Add Holding (only when portfolioId is set) */}
      {activePortfolioId && (
        <SectionCard className="mt-0 p-4">
          <h3 className="mt-0">添加持仓（组合 {activePortfolioId}）</h3>
          <div className="flex gap-2 flex-wrap items-end">
            <StockCodeInput id="portfolio-holding-code" label="股票代码" value={holdCode} onChange={setHoldCode} error={holdCodeError} placeholder="股票代码" />
            <label htmlFor="portfolio-holding-shares" className="grid gap-1 text-xs text-text-secondary">
              <span>股数</span>
              <input id="portfolio-holding-shares" value={holdShares} onChange={(e) => setHoldShares(e.target.value)} placeholder="100" type="number" className="w-[100px] px-2 py-1 rounded text-sm" />
            </label>
            <label htmlFor="portfolio-holding-cost" className="grid gap-1 text-xs text-text-secondary">
              <span>成本价</span>
              <input id="portfolio-holding-cost" value={holdCost} onChange={(e) => setHoldCost(e.target.value)} placeholder="可选" type="number" step="0.01" className="w-[140px] px-2 py-1 rounded text-sm" />
            </label>
            <button type="button" onClick={handleAddHolding} disabled={addHoldingApi.isPending}>{addHoldingApi.isPending ? '添加中...' : '添加'}</button>
          </div>
          {addHoldingApi.data != null && <p className="text-success text-xs mt-2">添加成功</p>}
        </SectionCard>
      )}

      {portfolioList.length > 0 && (
        <SectionCard className="mt-0 p-3">
          <h3 className="mt-0">组合列表</h3>
          <DataTable
            rows={portfolioList}
            columns={[
              { key: 'id', label: '组合ID' },
              { key: 'name', label: '组合名称' },
              { key: 'description', label: '描述' },
              { key: 'strategyAllocationCount', label: '策略数', align: 'right' },
              { key: 'strategyAllocationSummary', label: '策略配置' },
              { key: 'initialCapital', label: '初始资金', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
              { key: 'currentValue', label: '当前资产', align: 'right', render: (value) => fmtNum(Number(value ?? 0), 2) },
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
                    <div className={`text-xs ${isActive ? 'text-primary' : 'text-text-secondary'}`}>{isActive ? '已选中' : '点按切换'}</div>
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
        </SectionCard>
      )}

      {!activePortfolioId ? (
        <SectionCard className="mt-0 p-4">
          <EmptyState text="还没有选中组合。可以先从“组合列表”点选一条，或在上方创建新组合后继续。" hint="后续的详情、加仓、优化和压力测试都会围绕当前选中的组合展开。" />
        </SectionCard>
      ) : null}

      {detailObj && (
        <SectionCard className="mt-0 p-3">
          <h3 className="mt-0">组合详情</h3>
          <KpiGrid cols={4}>
            <KpiCard title="组合名称" value={detailObj.name != null ? String(detailObj.name) : null} />
            <KpiCard title="总资产" value={detailObj.totalAssets != null ? fmtNum(Number(detailObj.totalAssets), 2) : null} />
            <KpiCard title="总收益" value={detailObj.totalReturn != null ? fmtPct(Number(detailObj.totalReturn)) : null} change={detailObj.totalReturn != null ? Number(detailObj.totalReturn) : null} />
            <KpiCard title="持仓数" value={detailHoldings.length || null} />
          </KpiGrid>
          {detailStrategies.length > 0 && (
            <DataTable
              rows={detailStrategies}
              columns={[
                { key: 'strategyId', label: '策略ID', render: (_value, row) => String(row.strategyId ?? row.strategy_id ?? '-') },
                { key: 'weight', label: '权重', align: 'right', render: (value) => fmtPct(Number(value ?? 0) * 100) },
              ]}
              className="mt-3"
              mobileCardRender={(row) => (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-text-primary">策略 {String(row.strategyId ?? row.strategy_id ?? '-')}</div>
                  <div className="text-xs text-text-secondary">权重：{fmtPct(Number(row.weight ?? 0) * 100)}</div>
                </div>
              )}
            />
          )}
          {detailHoldings.length > 0 && <DataTable rows={detailHoldings} pageSize={10} onExport={() => exportCSV(detailHoldings, 'portfolio-holdings')} mobileCardRender={(row) => (
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-medium text-text-primary">{String(row.code ?? row.stockCode ?? '-')}</div>
                <div className="text-xs text-text-secondary">数量：{String(row.shares ?? row.quantity ?? '-')}</div>
              </div>
              <div className="text-xs text-text-secondary">成本价：{fmtNum(Number(row.costPrice ?? row.cost_price ?? 0), 2)}</div>
              <div className="text-xs text-text-secondary">市值：{fmtNum(Number(row.marketValue ?? row.market_value ?? 0), 2)}</div>
            </div>
          )} />}
        </SectionCard>
      )}

      {(weightSlices.length > 0 || riskBars.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {weightSlices.length > 0 && (
            <SectionCard className="p-3">
              <h3 className="mt-0">配置权重</h3>
              <PieChart data={weightSlices} donut height={300} />
            </SectionCard>
          )}
          {riskBars.length > 0 && (
            <SectionCard className="p-3">
              <h3 className="mt-0">风险贡献度</h3>
              <BarChart items={riskBars} colorByValue height={300} yAxisName="贡献 %" />
            </SectionCard>
          )}
        </div>
      )}

      {optimizeApi.data?.optimization && (
        <SectionCard className="mt-0 p-3">
          <KpiGrid cols={3}>
            <KpiCard title="预期收益" value={fmtPct(Number(optimizeApi.data.optimization.expectedReturn))} />
            <KpiCard title="预期风险" value={fmtPct(Number(optimizeApi.data.optimization.expectedRisk))} />
            <KpiCard title="夏普比率" value={fmtNum(Number(optimizeApi.data.optimization.sharpe), 2)} />
          </KpiGrid>
        </SectionCard>
      )}

      {riskApi.data?.riskMetrics && (
        <SectionCard className="mt-0 p-3">
          <h3 className="mt-0">风险指标</h3>
          <KpiGrid cols={5}>
            <KpiCard title="VaR (95%)" value={fmtPct(Number(riskApi.data.riskMetrics.var95))} />
            <KpiCard title="VaR (99%)" value={fmtPct(Number(riskApi.data.riskMetrics.var99))} />
            <KpiCard title="CVaR" value={fmtPct(Number(riskApi.data.riskMetrics.cvar))} />
            <KpiCard title="Beta" value={fmtNum(Number(riskApi.data.riskMetrics.beta), 2)} />
            <KpiCard title="波动率" value={fmtPct(Number(riskApi.data.riskMetrics.volatility))} />
          </KpiGrid>
        </SectionCard>
      )}

      {stressScenarios.length > 0 && (
        <SectionCard className="mt-0 p-3">
          <h3 className="mt-0">压力测试</h3>
          <DataTable rows={stressScenarios} onExport={() => exportCSV(stressScenarios, 'stress-test')} mobileCardRender={(row) => (
            <div className="space-y-2">
              <div className="text-sm font-medium text-text-primary">{String(row.name ?? '-')}</div>
              <div className="text-xs text-text-secondary">影响：{fmtPct(Number(row.impact ?? 0))}</div>
              <div className="text-xs text-text-secondary">{String(row.description ?? '无额外说明')}</div>
            </div>
          )} />
        </SectionCard>
      )}
    </>
  );

  const secondaryContent = (
    <SectionCard className="p-4">
      <div className="text-sm font-medium text-text-primary">组合工作区摘要</div>
      <div className="mt-3 grid gap-3 text-xs text-text-secondary">
        <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
          <div>当前组合：{selectedPortfolio ? String(selectedPortfolio.name ?? activePortfolioId) : activePortfolioId || '未选择'}</div>
          <div className="mt-1">组合数：{portfolioList.length}</div>
          <div className="mt-1">持仓数：{detailHoldings.length}</div>
          <div className="mt-1">策略数：{detailStrategies.length}</div>
        </div>
        <div className="rounded-xl border border-glass-border bg-surface p-3">
          <div>待加仓股票：{holdTrimmed || '未填写'}</div>
          <div className="mt-1">股数：{holdShares || '-'}</div>
          <div className="mt-1">成本价：{holdCost || '未填写'}</div>
          <div className="mt-1">优化结果：{optimizeApi.data?.optimization ? '已生成' : '未生成'}</div>
        </div>
        <div className="rounded-xl border border-dashed border-glass-border p-3">
          保存视图后，可以把当前组合、加仓参数和分析入口固定成一套组合复盘工作台。
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
