import { Badge, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { MetaLine } from '@/components/status-state';
import {
  performanceChipButtonCls,
  performanceNoteCardCls,
  performanceSidePanelCls,
} from '@/app/performance/components/performance-panel-styles';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import type {
  PaperTradingPerformanceMetrics,
  PaperTradingPosition,
  PerformanceAttributionResponse,
  PerformanceBenchmarkComparisonResponse,
} from '@aiask/shared-types';

type PerformanceSecondarySidebarProps = {
  isAccountMode: boolean;
  activeModeLabel: string;
  portfolioNarrative: string;
  days: number;
  portfolioLookbackDays: number;
  selectedBenchmarkLabel: string;
  focusStockCode: string;
  onOpenRisk: () => void;
  onOpenStock: (() => void) | null;
  onOpenResearch: (() => void) | null;
  totalValue: number;
  totalReturnPct: number;
  accountMetrics: PaperTradingPerformanceMetrics;
  accountLeaderCode: string;
  topPositions: PaperTradingPosition[];
  portfolioName: string;
  portfolioHoldingsCount: number;
  portfolioTotalReturnPct: number;
  benchmark: string;
  benchmarkOptions: Array<{ code: string; label: string }>;
  onBenchmarkChange: (value: string) => void;
  benchmarkComparison: PerformanceBenchmarkComparisonResponse | null | undefined;
  attribution: PerformanceAttributionResponse | null | undefined;
  outperformance: boolean;
  portfolioMessage: string | null;
  topContributorCode: string;
  weakContributorCode: string;
  onOpenStockTarget: (code: string) => void;
  onOpenResearchTarget: (code: string) => void;
};

export default function PerformanceSecondarySidebar({
  isAccountMode,
  activeModeLabel,
  portfolioNarrative,
  days,
  portfolioLookbackDays,
  selectedBenchmarkLabel,
  focusStockCode,
  onOpenRisk,
  onOpenStock,
  onOpenResearch,
  totalValue,
  totalReturnPct,
  accountMetrics,
  accountLeaderCode,
  topPositions,
  portfolioName,
  portfolioHoldingsCount,
  portfolioTotalReturnPct,
  benchmark,
  benchmarkOptions,
  onBenchmarkChange,
  benchmarkComparison,
  attribution,
  outperformance,
  portfolioMessage,
  topContributorCode,
  weakContributorCode,
  onOpenStockTarget,
  onOpenResearchTarget,
}: PerformanceSecondarySidebarProps) {
  return (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
      <div className={performanceSidePanelCls}>
        <div className="text-sm font-medium text-text-primary">当前联动摘要</div>
        <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">{portfolioNarrative}</p>
        <div className="mt-4 space-y-3">
          <div className={performanceNoteCardCls}>
            模式：<span className="font-medium text-text-primary">{activeModeLabel}</span>
          </div>
          <div className={performanceNoteCardCls}>
            观察窗口：
            <span className="font-medium text-text-primary">{isAccountMode ? days : portfolioLookbackDays} 天</span>
          </div>
          <div className={performanceNoteCardCls}>
            基准：<span className="font-medium text-text-primary">{isAccountMode ? '账户净值视角' : selectedBenchmarkLabel}</span>
          </div>
          {focusStockCode ? (
            <div className={performanceNoteCardCls}>
              焦点股票：<span className="font-medium text-text-primary">{focusStockCode}</span>
            </div>
          ) : null}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={onOpenRisk} className={performanceChipButtonCls}>
            打开风险中心
          </button>
          {focusStockCode && onOpenStock ? (
            <button type="button" onClick={onOpenStock} className={performanceChipButtonCls}>
              打开股票详情
            </button>
          ) : null}
          {focusStockCode && onOpenResearch ? (
            <button type="button" onClick={onOpenResearch} className={performanceChipButtonCls}>
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
              <Badge variant={accountLeaderCode ? 'success' : 'neutral'}>{accountLeaderCode || '暂无核心持仓'}</Badge>
            </div>
            <div className="mt-3 space-y-3">
              {topPositions.slice(0, 5).map((item) => (
                <div key={`${item.stock_code}-${item.stock_name}`} className={performanceNoteCardCls}>
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-text-primary">{item.stock_name || item.stock_code}</div>
                      <div className="text-xs text-text-secondary">{item.stock_code || '-'}</div>
                    </div>
                    <div className="text-xs text-text-secondary">{fmtPct(Number(item.profit_rate ?? 0) * 100)}</div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenStockTarget(String(item.stock_code ?? ''))}
                      className={performanceChipButtonCls}
                    >
                      详情
                    </button>
                    <button
                      type="button"
                      onClick={() => onOpenResearchTarget(String(item.stock_code ?? ''))}
                      className={performanceChipButtonCls}
                    >
                      研究
                    </button>
                  </div>
                </div>
              ))}
              {topPositions.length === 0 ? <div className="text-xs text-text-secondary">当前账户暂无核心持仓。</div> : null}
            </div>
          </SectionCard>
        </>
      ) : (
        <>
          <KpiGrid cols={2}>
            <KpiCard title="当前组合" value={portfolioName} />
            <KpiCard title="持仓数量" value={portfolioHoldingsCount} />
            <KpiCard title="组合收益率" value={fmtPct(portfolioTotalReturnPct)} change={portfolioTotalReturnPct} />
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
              <Badge variant={outperformance ? 'success' : 'warning'}>{outperformance ? '跑赢基准' : '未跑赢基准'}</Badge>
            </div>
            {portfolioMessage ? <MetaLine>{portfolioMessage}</MetaLine> : null}
            <div className="mt-3 space-y-2 text-xs text-text-secondary">
              <div>
                基准代码：<span className="font-medium text-text-primary">{benchmarkComparison?.benchmark ?? benchmark}</span>
              </div>
              <div>
                年化超额收益：
                <span className="font-medium text-text-primary">
                  {fmtPct(Number(benchmarkComparison?.annualizedExcessReturnPct ?? 0))}
                </span>
              </div>
              <div>
                对齐交易日：
                <span className="font-medium text-text-primary">{String(benchmarkComparison?.alignedDays ?? '-')}</span>
              </div>
              <div>
                归因方法：<span className="font-medium text-text-primary">{attribution?.method ?? '-'}</span>
              </div>
              {topContributorCode ? (
                <div>
                  最大贡献股：<span className="font-medium text-text-primary">{topContributorCode}</span>
                </div>
              ) : null}
              {weakContributorCode ? (
                <div>
                  主要拖累股：<span className="font-medium text-text-primary">{weakContributorCode}</span>
                </div>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {benchmarkOptions.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => onBenchmarkChange(item.code)}
                  className={`action-chip cursor-pointer text-[11px] ${benchmark === item.code ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </SectionCard>
        </>
      )}
    </div>
  );
}
