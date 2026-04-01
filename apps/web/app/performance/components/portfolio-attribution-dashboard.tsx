import { Badge, DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { BarChart, WaterfallChart } from '@/components/charts';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  performanceChipButtonCls,
  performanceNoteCardCls,
} from '@/app/performance/components/performance-panel-styles';
import type {
  PerformanceAttributionResponse,
  PerformanceBenchmarkComparisonResponse,
  PerformanceSectorPerformanceItem,
  PerformanceAttributionStockItem,
} from '@aiask/shared-types';

type PortfolioAttributionDashboardProps = {
  errorMessage: string | null;
  isLoading: boolean;
  attribution: PerformanceAttributionResponse | null | undefined;
  benchmarkComparison: PerformanceBenchmarkComparisonResponse | null | undefined;
  portfolioMessage: string | null;
  portfolioName: string;
  portfolioHoldingsCount: number;
  attributionByStock: PerformanceAttributionStockItem[];
  portfolioTotalReturnPct: number;
  portfolioTotalAssets: number;
  waterfallData: Array<{ name: string; value: number }>;
  sectorBarItems: Array<{ label: string; value: number }>;
  outperformance: boolean;
  selectedPortfolioId: number | null;
  portfolioLookbackDays: number;
  benchmark: string;
  onOpenStockTarget: (code: string) => void;
  onOpenResearchTarget: (code: string) => void;
};

export default function PortfolioAttributionDashboard({
  errorMessage,
  isLoading,
  attribution,
  benchmarkComparison,
  portfolioMessage,
  portfolioName,
  portfolioHoldingsCount,
  attributionByStock,
  portfolioTotalReturnPct,
  portfolioTotalAssets,
  waterfallData,
  sectorBarItems,
  outperformance,
  selectedPortfolioId,
  portfolioLookbackDays,
  benchmark,
  onOpenStockTarget,
  onOpenResearchTarget,
}: PortfolioAttributionDashboardProps) {
  return (
    <>
      {errorMessage ? <ErrorState text={errorMessage} /> : null}
      {isLoading && !attribution ? <LoadingState text="加载组合归因中..." /> : null}
      {portfolioMessage ? <MetaLine>{portfolioMessage}</MetaLine> : null}

      <KpiGrid cols={5} className="mb-4 mt-4">
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
            className={performanceChipButtonCls}
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
                    <button type="button" onClick={() => onOpenStockTarget(rowCode)} className={performanceChipButtonCls}>
                      详情
                    </button>
                    <button
                      type="button"
                      onClick={() => onOpenResearchTarget(rowCode)}
                      className={performanceChipButtonCls}
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
                    onClick={() => onOpenStockTarget(String(row.code ?? ''))}
                    className={performanceChipButtonCls}
                  >
                    打开详情
                  </button>
                  <button
                    type="button"
                    onClick={() => onOpenResearchTarget(String(row.code ?? ''))}
                    className={performanceChipButtonCls}
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
          <div className={performanceNoteCardCls}>
            <div className="text-xs text-text-secondary">基准代码</div>
            <div className="mt-1 text-sm font-medium text-text-primary">{benchmarkComparison?.benchmark ?? benchmark}</div>
          </div>
          <div className={performanceNoteCardCls}>
            <div className="text-xs text-text-secondary">年化超额收益</div>
            <div className="mt-1 text-sm font-medium text-text-primary">
              {fmtPct(Number(benchmarkComparison?.annualizedExcessReturnPct ?? 0))}
            </div>
          </div>
          <div className={performanceNoteCardCls}>
            <div className="text-xs text-text-secondary">对齐交易日</div>
            <div className="mt-1 text-sm font-medium text-text-primary">{String(benchmarkComparison?.alignedDays ?? '-')}</div>
          </div>
          <div className={performanceNoteCardCls}>
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
        {attribution?.attribution?.timing?.basis ? <MetaLine>择时贡献口径：{attribution.attribution.timing.basis}</MetaLine> : null}
      </SectionCard>
    </>
  );
}
