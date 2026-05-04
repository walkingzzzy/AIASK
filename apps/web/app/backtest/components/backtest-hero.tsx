import { Badge } from '@/components/ui';
import {
  backtestChipButtonCls,
  backtestNoteCardCls,
  backtestPrimaryButtonCls,
  backtestSecondaryButtonCls,
  backtestSidePanelCls,
} from '@/app/backtest/components/backtest-panel-styles';
import { fmtPct } from '@/lib/data-utils';

type BacktestHeroProps = {
  loading: boolean;
  runStatusLabel: string;
  runStatusVariant: 'warning' | 'success' | 'neutral';
  artifactId: string | null | undefined;
  from: string | null;
  onScrollToSection: (id: string) => void;
  onRunBacktest: () => void;
  trimmedCode: string;
  strategyLabel: string;
  startDate: string;
  dateRangeLabel: string;
  totalReturn: number | null;
  maxDrawdown: number | null;
  batchResultsCount: number;
  hasAnyResultBlock: boolean;
  configurationSummary: string;
};

export default function BacktestHero({
  loading,
  runStatusLabel,
  runStatusVariant,
  artifactId,
  from,
  onScrollToSection,
  onRunBacktest,
  trimmedCode,
  strategyLabel,
  startDate,
  dateRangeLabel,
  totalReturn,
  maxDrawdown,
  batchResultsCount,
  hasAnyResultBlock,
  configurationSummary,
}: BacktestHeroProps) {
  return (
    <section className="page-hero mb-4 p-5 sm:p-6">
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">回测工作台</Badge>
            <Badge variant={runStatusVariant}>{runStatusLabel}</Badge>
            <Badge variant={artifactId ? 'success' : 'neutral'}>
              {artifactId ? `回测制品 ${artifactId}` : '尚未生成回测制品'}
            </Badge>
            {from ? <Badge variant="neutral">来源 {from}</Badge> : null}
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            回测分析工作台
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
            这一页用于完成策略回测配置、结果阅读和跨标的比较。先配置参数并运行回测，再结合摘要、净值曲线、历史对比和批量回测判断策略是否值得继续推进。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={onRunBacktest} disabled={loading} className={backtestPrimaryButtonCls}>
              {loading ? '运行中...' : '运行回测'}
            </button>
            <button type="button" onClick={() => onScrollToSection('backtest-overview')} className={backtestSecondaryButtonCls}>
              查看结果总览
            </button>
            <button type="button" onClick={() => onScrollToSection('backtest-chart')} className={backtestChipButtonCls}>
              看净值曲线
            </button>
            <button type="button" onClick={() => onScrollToSection('backtest-history')} className={backtestChipButtonCls}>
              看历史对比
            </button>
            <button type="button" onClick={() => onScrollToSection('backtest-batch')} className={backtestChipButtonCls}>
              看批量回测
            </button>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '未选择标的'}</div>
              <div className="mt-1 text-xs text-text-secondary">{strategyLabel}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">回测区间</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{startDate.slice(5)}</div>
              <div className="mt-1 text-xs text-text-secondary">{dateRangeLabel}</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关键读数</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">
                {totalReturn != null ? fmtPct(totalReturn) : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {maxDrawdown != null ? `回撤 ${fmtPct(maxDrawdown)}` : '等待回测结果'}
              </div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">
                {batchResultsCount > 0 ? batchResultsCount : hasAnyResultBlock ? '对比' : '运行'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {batchResultsCount > 0
                  ? '批量结果已可比较'
                  : hasAnyResultBlock
                    ? '继续看历史与批量验证'
                    : '先完成首轮回测'}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className={backtestSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前配置</div>
            <div className="mt-4 space-y-3">
              <div className={backtestNoteCardCls}>
                策略：<span className="font-medium text-text-primary">{strategyLabel}</span>
              </div>
              <div className={backtestNoteCardCls}>
                日期：<span className="font-medium text-text-primary">{dateRangeLabel}</span>
              </div>
              <div className={backtestNoteCardCls}>
                成本：<span className="font-medium text-text-primary">{configurationSummary}</span>
              </div>
            </div>
          </div>

          <div className={backtestSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
            <div className="mt-4 space-y-3">
              <div className={backtestNoteCardCls}>1. 先确认标的、策略和日期区间，避免错误的样本设置污染整轮判断。</div>
              <div className={backtestNoteCardCls}>2. 再看总收益、回撤和胜率，先判断这次回测值不值得继续展开。</div>
              <div className={backtestNoteCardCls}>3. 最后再看历史对比和批量回测，确认结果是否具有可复制性，而不是一次性幸运样本。</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
