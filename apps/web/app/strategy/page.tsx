'use client';

import { FormEvent, useMemo, useState } from 'react';
import { Badge, DataTable, KpiCard, KpiGrid, PageContainer, SectionCard, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

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
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [strategy, setStrategy] = useState('ma_cross');
  const [artifactId, setArtifactId] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [portfolioName, setPortfolioName] = useState('我的策略组合');
  const [holdingOp, setHoldingOp] = useState<HoldingOp>({
    portfolioId: '',
    code: '600519',
    shares: '100',
    costPrice: '1',
  });
  const [backtestListPath, setBacktestListPath] = useState<string | null>(null);
  const [portfolioListPath, setPortfolioListPath] = useState<string | null>(null);
  const [portfolioDetailPath, setPortfolioDetailPath] = useState<string | null>(null);

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

  async function runBacktest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    try {
      const data = await backtestApi.triggerAsync('/backtest/run', { method: 'POST' }, { code: trimmedCode, strategy });
      setArtifactId(String(data?.artifactId ?? ''));
    } catch {
      /* captured */
    }
  }

  function loadBacktests() {
    const path = '/backtest/list?limit=10';
    if (path === backtestListPath) backtestListQ.refetch();
    else setBacktestListPath(path);
  }

  function loadMetrics(id = artifactId) {
    const nextId = id.trim();
    if (!nextId) {
      setFormError('请先提供 artifactId');
      return;
    }
    if (nextId !== artifactId) setArtifactId(nextId);
    else metricsQ.refetch();
  }

  async function createPortfolio() {
    setFormError(null);
    if (!portfolioName.trim()) {
      setFormError('组合名称不能为空');
      return;
    }
    try {
      const data = await actionApi.triggerAsync(
        '/portfolio/create',
        { method: 'POST' },
        {
          name: portfolioName.trim(),
          initialCapital: '100000',
        },
      );
      const createdId =
        data && typeof data === 'object' && 'portfolioId' in data
          ? String((data as { portfolioId?: unknown }).portfolioId ?? '')
          : '';
      if (createdId) {
        setHoldingOp((prev) => ({ ...prev, portfolioId: createdId }));
        const detailPath = `/portfolio/get?portfolioId=${encodeURIComponent(createdId)}`;
        if (detailPath === portfolioDetailPath) portfolioDetailQ.refetch();
        else setPortfolioDetailPath(detailPath);
      }
      const listPath = '/portfolio/list';
      if (listPath === portfolioListPath) portfolioListQ.refetch();
      else setPortfolioListPath(listPath);
    } catch {
      /* captured */
    }
  }

  function loadPortfolios() {
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
      await actionApi.triggerAsync('/portfolio/add-holding', { method: 'POST' }, holdingOp);
      const path = '/portfolio/list';
      if (path === portfolioListPath) portfolioListQ.refetch();
      else setPortfolioListPath(path);
    } catch {
      /* captured */
    }
  }

  async function removeHolding() {
    setFormError(null);
    if (!/^\d+$/.test(holdingOp.portfolioId) || !/^\d{6}$/.test(holdingOp.code)) {
      setFormError('持仓参数不合法');
      return;
    }
    try {
      await actionApi.triggerAsync(
        `/portfolio/remove-holding?portfolioId=${encodeURIComponent(holdingOp.portfolioId)}&code=${holdingOp.code}`,
        { method: 'DELETE' },
      );
      const path = '/portfolio/list';
      if (path === portfolioListPath) portfolioListQ.refetch();
      else setPortfolioListPath(path);
    } catch {
      /* captured */
    }
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
  }

  function optimizePortfolio() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    optimizeApi.trigger('/portfolio/optimize', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
  }

  function analyzeRisk() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    riskAnalysisApi.trigger('/portfolio/risk-analysis', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
  }

  function runStressTest() {
    setFormError(null);
    if (!holdingOp.portfolioId) {
      setFormError('请输入 portfolioId');
      return;
    }
    stressTestApi.trigger('/portfolio/stress-test', { method: 'POST' }, { portfolioId: holdingOp.portfolioId });
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

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Strategy Workspace</Badge>
              <Badge variant={artifactId ? 'success' : 'warning'}>
                {artifactId ? '已形成回测产物' : '等待生成 Artifact'}
              </Badge>
              <Badge variant={holdingOp.portfolioId ? 'success' : 'neutral'}>
                {holdingOp.portfolioId ? `组合 ${holdingOp.portfolioId}` : '尚未绑定组合'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              策略工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页负责把策略试验和组合落地收进一条连续链路。先在试验区跑回测、确认 Artifact
              与核心收益指标，再进入落地区创建组合、调仓，并继续做优化与风控分析。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={loadBacktests} className={heroPrimaryButtonCls}>
                查看最近回测
              </button>
              <button type="button" onClick={loadPortfolios} className={heroSecondaryButtonCls}>
                加载组合列表
              </button>
              <button type="button" onClick={optimizePortfolio} className={heroSecondaryButtonCls}>
                优化配置
              </button>
              <button type="button" onClick={analyzeRisk} className={heroSecondaryButtonCls}>
                风险分析
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">{strategy || '未设置策略标识'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Artifact</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{artifactId || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  Backtest {backtestApi.data?.backtestId != null ? String(backtestApi.data.backtestId) : '-'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前组合</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{holdingOp.portfolioId || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  持仓 {detailHoldings.length} 条 · 策略 {detailStrategies.length} 条
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolioRows.length}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {holdingOp.portfolioId ? '继续调仓、优化与压力测试' : '先创建组合或从列表选择组合'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前实验状态</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {artifactId ? `已生成 Artifact ${artifactId}` : '等待第一次回测结果'}
              </div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  收益摘要：
                  <span className="font-medium text-text-primary">
                    {metrics?.totalReturn != null ? fmtPct(Number(metrics.totalReturn)) : '尚未生成'}
                  </span>
                </div>
                <div className={noteCardCls}>
                  回撤：
                  <span className="font-medium text-text-primary">
                    {metrics?.maxDrawdown != null ? fmtPct(Number(metrics.maxDrawdown)) : '尚未生成'}
                  </span>
                </div>
                <div className={noteCardCls}>
                  组合上下文：
                  <span className="font-medium text-text-primary">{holdingOp.portfolioId || '未绑定'}</span>
                </div>
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>1. 先跑回测，确认 Artifact、收益率和回撤是否在可接受区间。</div>
                <div className={noteCardCls}>2. 再创建组合并把持仓逐步落地到组合里，不要一开始就直接做风控。</div>
                <div className={noteCardCls}>3. 最后做优化、风险分析和压力测试，确认策略不是只在单一场景下成立。</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="Artifact ID" value={artifactId || null} />
        <KpiCard
          title="Backtest ID"
          value={backtestApi.data?.backtestId != null ? String(backtestApi.data.backtestId) : null}
        />
        <KpiCard
          title="总收益"
          value={metrics?.totalReturn != null ? fmtPct(Number(metrics.totalReturn)) : null}
          change={metrics?.totalReturn != null ? Number(metrics.totalReturn) : null}
        />
        <KpiCard title="夏普比率" value={metrics?.sharpe != null ? fmtNum(Number(metrics.sharpe), 2) : null} />
        <KpiCard title="最大回撤" value={metrics?.maxDrawdown != null ? fmtPct(Number(metrics.maxDrawdown)) : null} />
      </KpiGrid>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Experiment Workspace</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">试验区 · 回测执行</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              试验区先确认标的和策略标识，再运行回测并保留 Artifact
              供后续指标刷新。只有实验结果足够清晰，落地动作才有意义。
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="text-sm font-medium text-text-primary">运行新的回测</div>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              先确认标的和策略标识，再运行回测并保留 Artifact 供后续指标刷新。
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
              <button type="button" onClick={loadBacktests} className={chipButtonCls}>
                最近回测
              </button>
            </form>
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="text-sm font-medium text-text-primary">回测结果定位</div>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              把最近一次回测生成的 Artifact 留在手边，后续刷新收益指标时不需要重新跑完整流程。
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,260px)_auto] md:items-end">
              <WorkbenchField
                id="strategy-artifact-id"
                label="Artifact ID"
                value={artifactId}
                onChange={setArtifactId}
                placeholder="粘贴或保留最近一次回测的 artifactId"
              />
              <div className="flex gap-2">
                <button type="button" onClick={() => loadMetrics()} className={chipButtonCls}>
                  刷新指标
                </button>
              </div>
            </div>
          </div>
        </div>

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
                {
                  key: 'maxDrawdown',
                  label: '最大回撤',
                  align: 'right',
                  render: (value) => fmtPct(Number(value ?? 0)),
                },
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

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Deployment Workspace</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">落地区 · 组合管理</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这里负责把试验结果真正放进组合。先建组合容器，再把选定策略和持仓逐步落地到组合里。
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
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
              <button type="button" onClick={loadPortfolios} className={chipButtonCls}>
                组合列表
              </button>
            </div>
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="text-sm font-medium text-text-primary">持仓与详情操作</div>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              把组合 ID、标的、股数和成本价收在同一块里，便于在同一上下文里做加仓、减仓和详情查看。
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
              <button type="button" onClick={addHolding} className={chipButtonCls}>
                加仓
              </button>
              <button type="button" onClick={removeHolding} className={chipButtonCls}>
                减仓
              </button>
              <button type="button" onClick={loadPortfolioDetail} className={chipButtonCls}>
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
                {
                  key: 'currentValue',
                  label: '当前资产',
                  align: 'right',
                  render: (value) => fmtNum(Number(value ?? 0), 2),
                },
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

      <SectionCard className="p-4 sm:p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="eyebrow">Risk Workspace</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">落地区 · 组合优化与风控</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
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
                value={
                  optData.optimization.expectedReturn != null
                    ? fmtPct(Number(optData.optimization.expectedReturn))
                    : null
                }
              />
              <KpiCard
                title="预期风险"
                value={
                  optData.optimization.expectedRisk != null ? fmtPct(Number(optData.optimization.expectedRisk)) : null
                }
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
              <KpiCard
                title="VaR (95%)"
                value={riskData.riskMetrics.var95 != null ? fmtPct(Number(riskData.riskMetrics.var95)) : null}
              />
              <KpiCard
                title="VaR (99%)"
                value={riskData.riskMetrics.var99 != null ? fmtPct(Number(riskData.riskMetrics.var99)) : null}
              />
              <KpiCard
                title="CVaR"
                value={riskData.riskMetrics.cvar != null ? fmtPct(Number(riskData.riskMetrics.cvar)) : null}
              />
              <KpiCard
                title="Beta"
                value={riskData.riskMetrics.beta != null ? fmtNum(Number(riskData.riskMetrics.beta), 2) : null}
              />
              <KpiCard
                title="波动率"
                value={riskData.riskMetrics.volatility != null ? fmtPct(Number(riskData.riskMetrics.volatility)) : null}
              />
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
    </PageContainer>
  );
}
