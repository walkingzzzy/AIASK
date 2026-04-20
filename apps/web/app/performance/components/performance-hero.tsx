import { Badge } from '@/components/ui';
import {
  performanceNoteCardCls,
  performancePrimaryButtonCls,
  performanceSecondaryButtonCls,
  performanceSidePanelCls,
} from '@/app/performance/components/performance-panel-styles';

type PerformanceHeroProps = {
  isAccountMode: boolean;
  activeModeLabel: string;
  outperformance: boolean;
  sourceExecutionId: string;
  onRefresh: () => void;
  onOpenRisk: () => void;
  focusStockCode: string;
  onOpenStock: (() => void) | null;
  onOpenResearch: (() => void) | null;
  currentEntityLabel: string;
  windowLabel: string;
  windowHint: string;
  primaryMetricLabel: string;
  primaryMetricValue: string;
  primaryMetricHint: string;
  focusMetricHint: string;
  pageSummary: string;
  benchmarkLabel: string;
  portfolioNarrative: string;
};

export default function PerformanceHero({
  isAccountMode,
  activeModeLabel,
  outperformance,
  sourceExecutionId,
  onRefresh,
  onOpenRisk,
  focusStockCode,
  onOpenStock,
  onOpenResearch,
  currentEntityLabel,
  windowLabel,
  windowHint,
  primaryMetricLabel,
  primaryMetricValue,
  primaryMetricHint,
  focusMetricHint,
  pageSummary,
  benchmarkLabel,
  portfolioNarrative,
}: PerformanceHeroProps) {
  return (
    <section className="page-hero p-5 sm:p-6">
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
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
            <button type="button" onClick={onRefresh} className={performancePrimaryButtonCls}>
              刷新当前数据
            </button>
            <button type="button" onClick={onOpenRisk} className={performanceSecondaryButtonCls}>
              打开风险中心
            </button>
            {focusStockCode && onOpenStock ? (
              <button type="button" onClick={onOpenStock} className={performanceSecondaryButtonCls}>
                查看重点股票
              </button>
            ) : null}
            {focusStockCode && onOpenResearch ? (
              <button type="button" onClick={onOpenResearch} className={performanceSecondaryButtonCls}>
                查看研究页
              </button>
            ) : null}
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前视角</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{activeModeLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">{currentEntityLabel}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">观察窗口</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{windowLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">{windowHint}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                {primaryMetricLabel}
              </div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{primaryMetricValue}</div>
              <div className="mt-1 text-xs text-text-secondary">{primaryMetricHint}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">重点标的</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{focusStockCode || '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">{focusMetricHint}</div>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className={performanceSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
            <div className="mt-3 text-base font-semibold text-text-primary">
              {isAccountMode ? `${currentEntityLabel} 复盘` : `${currentEntityLabel} 组合归因`}
            </div>
            <div className="mt-4 space-y-3">
              <div className={performanceNoteCardCls}>
                核心摘要：<span className="font-medium text-text-primary">{pageSummary}</span>
              </div>
              {!isAccountMode ? (
                <div className={performanceNoteCardCls}>
                  基准口径：<span className="font-medium text-text-primary">{benchmarkLabel}</span>
                </div>
              ) : null}
              <div className={performanceNoteCardCls}>
                联动股票：<span className="font-medium text-text-primary">{focusStockCode || '暂无'}</span>
              </div>
            </div>
          </div>

          <div className={performanceSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步动作</div>
            <div className="mt-4 space-y-3">
              <div className={performanceNoteCardCls}>{portfolioNarrative}</div>
              <div className={performanceNoteCardCls}>
                {isAccountMode
                  ? '先核对回撤和胜率，再决定是否追到单只股票。'
                  : '先看超额收益来源，再判断是配置问题还是个股问题。'}
              </div>
              <div className={performanceNoteCardCls}>
                {focusStockCode
                  ? `当前可直接跳转 ${focusStockCode} 的研究页和详情页。`
                  : '如果没有聚焦股票，先在持仓或归因列表中选一只拖累股或贡献股。'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
