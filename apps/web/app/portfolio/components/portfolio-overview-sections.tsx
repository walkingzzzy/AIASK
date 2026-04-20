import { AskAiButton } from '@/components/ask-ai-button';
import { SectionCard, StockCodeInput, Badge } from '@/components/ui';
import {
  chipButtonCls,
  heroPrimaryButtonCls,
  heroSecondaryButtonCls,
  noteCardCls,
  sidePanelCls,
} from './portfolio-panel-styles';

type PortfolioHeroSectionProps = {
  activePortfolioId: string;
  portfolioDisplayName: string;
  portfolioNextStep: string;
  portfolioCount: number;
  holdingCount: number;
  strategyCount: number;
  holdTrimmed: string;
  currentAssetsDisplay: string;
  stressScenarioCount: number;
  hasOptimization: boolean;
  hasRiskMetrics: boolean;
  latestPortfolioRefreshText: string;
  lastPrimaryRefreshAt: string | null;
  onRefreshList: () => void;
  onOptimize: () => void;
  onAnalyzeRisk: () => void;
  onRunStress: () => void;
};

export function PortfolioHeroSection({
  activePortfolioId,
  portfolioDisplayName,
  portfolioNextStep,
  portfolioCount,
  holdingCount,
  strategyCount,
  holdTrimmed,
  currentAssetsDisplay,
  stressScenarioCount,
  hasOptimization,
  hasRiskMetrics,
  latestPortfolioRefreshText,
  lastPrimaryRefreshAt,
  onRefreshList,
  onOptimize,
  onAnalyzeRisk,
  onRunStress,
}: PortfolioHeroSectionProps) {
  return (
    <section className="page-hero p-5 sm:p-6">
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Portfolio Workspace</Badge>
            <Badge variant={activePortfolioId ? 'success' : 'warning'}>
              {activePortfolioId ? '已锁定当前组合' : '等待选择组合'}
            </Badge>
            <Badge variant={hasOptimization ? 'success' : 'neutral'}>
              {hasOptimization ? '已有优化结果' : '尚未优化'}
            </Badge>
            <Badge variant={hasRiskMetrics ? 'warning' : 'neutral'}>
              {hasRiskMetrics ? '已有风险分析' : '尚未分析'}
            </Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            组合管理工作台
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
            组合页不再让创建、加仓、优化和风险分析同时争夺注意力，而是把它们收束成一套连续的工作流。先锁定目标组合，再顺着持仓维护、配置优化和风险复盘依次推进。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRefreshList}
              data-testid="page-primary-action"
              data-action-testid="portfolio-refresh-action"
              className={heroPrimaryButtonCls}
            >
              刷新组合列表
            </button>
            <button type="button" onClick={onOptimize} className={heroSecondaryButtonCls}>
              优化配置
            </button>
            <button type="button" onClick={onAnalyzeRisk} className={heroSecondaryButtonCls}>
              风险分析
            </button>
            <button type="button" onClick={onRunStress} className={heroSecondaryButtonCls}>
              压力测试
            </button>
          </div>
          <div
            data-testid="page-primary-status"
            className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前组合 {portfolioDisplayName}，持仓 {holdingCount} 条，策略 {strategyCount} 条
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
              优化结果 {hasOptimization ? '已生成' : '未生成'} ｜ 风险分析 {hasRiskMetrics ? '已生成' : '未生成'} ｜
              压力场景 {stressScenarioCount} 条
            </p>
            <p className="mt-2 mb-0 text-xs text-text-secondary">
              最近数据：{latestPortfolioRefreshText}
              {lastPrimaryRefreshAt ? ` ｜ 手动刷新：${lastPrimaryRefreshAt}` : ''}
            </p>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前组合</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolioDisplayName}</div>
              <div className="mt-1 text-xs text-text-secondary">{activePortfolioId || '请先从列表选择'}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">组合规模</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolioCount}</div>
              <div className="mt-1 text-xs text-text-secondary">已创建组合总数</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">持仓 / 策略</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">
                {holdingCount} / {strategyCount}
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
                当前资产：<span className="font-medium text-text-primary">{currentAssetsDisplay}</span>
              </div>
            </div>
            <div className="mt-4">
              <AskAiButton
                stockCode={holdTrimmed || undefined}
                summary={`当前组合 ${portfolioDisplayName}，持仓 ${holdingCount} 条`}
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
                {stressScenarioCount > 0
                  ? `已生成 ${stressScenarioCount} 个压力场景，可继续判断拖累来源。`
                  : '如果已经选好组合，下一步优先做风险分析或压力测试。'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

type PortfolioOperationWorkspaceSectionProps = {
  activePortfolioId: string;
  portfolioDisplayName: string;
  portfolioNextStep: string;
  portfolioCount: number;
  currentAssetsDisplay: string;
  portfolioId: string;
  onPortfolioIdChange: (value: string) => void;
  setFormError: (error: string | null) => void;
  onRefetchList: () => void;
  onRefetchDetail: () => void;
  onOptimize: () => void;
  onAnalyzeRisk: () => void;
  onRunStress: () => void;
  newName: string;
  onNewNameChange: (value: string) => void;
  newDesc: string;
  onNewDescChange: (value: string) => void;
  newCapital: string;
  onNewCapitalChange: (value: string) => void;
  onCreate: () => void;
  createPending: boolean;
  createSuccess: boolean;
  holdCode: string;
  onHoldCodeChange: (value: string) => void;
  holdCodeError: string | null;
  holdShares: string;
  onHoldSharesChange: (value: string) => void;
  holdCost: string;
  onHoldCostChange: (value: string) => void;
  onAddHolding: () => void;
  addHoldingPending: boolean;
  addHoldingSuccess: boolean;
};

export function PortfolioOperationWorkspaceSection({
  activePortfolioId,
  portfolioDisplayName,
  portfolioNextStep,
  portfolioCount,
  currentAssetsDisplay,
  portfolioId,
  onPortfolioIdChange,
  setFormError,
  onRefetchList,
  onRefetchDetail,
  onOptimize,
  onAnalyzeRisk,
  onRunStress,
  newName,
  onNewNameChange,
  newDesc,
  onNewDescChange,
  newCapital,
  onNewCapitalChange,
  onCreate,
  createPending,
  createSuccess,
  holdCode,
  onHoldCodeChange,
  holdCodeError,
  holdShares,
  onHoldSharesChange,
  holdCost,
  onHoldCostChange,
  onAddHolding,
  addHoldingPending,
  addHoldingSuccess,
}: PortfolioOperationWorkspaceSectionProps) {
  return (
    <SectionCard className="mt-0 p-4 sm:p-5">
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
        <div>
          <div className="eyebrow">Operation Workspace</div>
          <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">锁定组合后再展开动作</h2>
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
                  onPortfolioIdChange(event.target.value);
                  setFormError(null);
                }}
                placeholder="优先从列表选择；必要时可手动输入"
                className="text-sm"
              />
            </label>
            <button type="button" onClick={onRefetchList} className={chipButtonCls}>
              组合列表
            </button>
            <button
              type="button"
              onClick={() => {
                if (!activePortfolioId) {
                  setFormError('请先选择组合');
                  return;
                }
                onRefetchDetail();
              }}
              className={chipButtonCls}
            >
              查看详情
            </button>
            <button type="button" onClick={onOptimize} className={chipButtonCls}>
              优化配置
            </button>
            <button type="button" onClick={onAnalyzeRisk} className={chipButtonCls}>
              风险分析
            </button>
            <button type="button" onClick={onRunStress} className={chipButtonCls}>
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
              <span className="font-medium text-text-primary">{portfolioCount}</span>
            </div>
            <div className={noteCardCls}>
              当前建议：
              <span className="font-medium text-text-primary">{portfolioNextStep}</span>
            </div>
            <div className={noteCardCls}>
              当前资产：
              <span className="font-medium text-text-primary">{currentAssetsDisplay}</span>
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
                onChange={(event) => onNewNameChange(event.target.value)}
                placeholder="输入组合名称"
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary">
              <span>描述</span>
              <input
                id="portfolio-new-desc"
                value={newDesc}
                onChange={(event) => onNewDescChange(event.target.value)}
                placeholder="可选"
                className="text-sm"
              />
            </label>
            <label className="flex flex-col gap-2 text-xs text-text-secondary md:col-span-2">
              <span>初始资金</span>
              <input
                id="portfolio-new-capital"
                value={newCapital}
                onChange={(event) => onNewCapitalChange(event.target.value)}
                placeholder="1000000"
                type="number"
                className="text-sm"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={onCreate} disabled={createPending} className={heroPrimaryButtonCls}>
              {createPending ? '创建中...' : '创建组合'}
            </button>
          </div>
          {createSuccess ? (
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
                  onChange={onHoldCodeChange}
                  error={holdCodeError}
                  placeholder="股票代码"
                />
                <label className="flex flex-col gap-2 text-xs text-text-secondary">
                  <span>股数</span>
                  <input
                    id="portfolio-holding-shares"
                    value={holdShares}
                    onChange={(event) => onHoldSharesChange(event.target.value)}
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
                    onChange={(event) => onHoldCostChange(event.target.value)}
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
                  onClick={onAddHolding}
                  disabled={addHoldingPending}
                  className={heroPrimaryButtonCls}
                >
                  {addHoldingPending ? '添加中...' : '添加持仓'}
                </button>
              </div>
              {addHoldingSuccess ? (
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
  );
}

type PortfolioSidebarSummaryProps = {
  portfolioDisplayName: string;
  portfolioCount: number;
  holdingCount: number;
  strategyCount: number;
  holdTrimmed: string;
  holdShares: string;
  holdCost: string;
  hasOptimization: boolean;
  hasRiskMetrics: boolean;
  stressScenarioCount: number;
};

export function PortfolioSidebarSummary({
  portfolioDisplayName,
  portfolioCount,
  holdingCount,
  strategyCount,
  holdTrimmed,
  holdShares,
  holdCost,
  hasOptimization,
  hasRiskMetrics,
  stressScenarioCount,
}: PortfolioSidebarSummaryProps) {
  return (
    <SectionCard className="p-4 sm:p-5">
      <div className="eyebrow">Portfolio Summary</div>
      <h3 className="mb-0 mt-2 text-lg font-semibold text-text-primary">组合工作区摘要</h3>
      <div className="mt-4 grid gap-3">
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">组合概览</div>
          <div className="metric-value mt-3 text-[1.45rem]">{portfolioDisplayName}</div>
          <div className="mt-2 text-xs text-text-secondary">
            组合数 {portfolioCount} · 持仓 {holdingCount} · 策略 {strategyCount}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">待执行动作</div>
          <div className="metric-value mt-3 text-[1.45rem]">{holdTrimmed || '未设标的'}</div>
          <div className="mt-2 text-xs text-text-secondary">
            股数 {holdShares || '-'} · 成本价 {holdCost || '未填写'}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            优化结果 {hasOptimization ? '已生成' : '未生成'} · 风险结果 {hasRiskMetrics ? '已生成' : '未生成'}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">分析进度</div>
          <div className="metric-value mt-3 text-[1.45rem]">
            {hasOptimization ? '优化' : '-'} / {hasRiskMetrics ? '风险' : '-'}
          </div>
          <div className="mt-2 text-xs text-text-secondary">压力场景 {stressScenarioCount} 条</div>
        </div>
        <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
          保存视图后，可以把当前组合、加仓参数和分析入口固定成一套组合复盘工作台，在策略页和绩效页之间来回复用。
        </div>
      </div>
    </SectionCard>
  );
}
