import { LineChart } from '@/components/charts';
import { Badge, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  paperTradingChipButtonCls,
  paperTradingNoteCardCls,
} from '@/app/paper-trading/components/paper-trading-panel-styles';
import type {
  PaperTradingAccount,
  PaperTradingPerformanceMetrics,
  PaperTradingPerformancePoint,
} from '@aiask/shared-types';

type PaperTradingAnalyticsProps = {
  showAccountBootstrap: boolean;
  matchOk: boolean;
  navOk: boolean;
  matchStatusLabel: string;
  navStatusLabel: string;
  onRefreshPrices: () => void;
  refreshPricesPending: boolean;
  onReconcileLedger: () => void;
  reconcilePending: boolean;
  accounts: PaperTradingAccount[];
  accountId: string;
  onAccountChange: (value: string) => void;
  statusNotes: string[];
  totalValue: number;
  cash: number;
  marketValue: number;
  returnPct: number;
  todayPnl: number;
  perfDays: number;
  onPerfDaysChange: (value: number) => void;
  performanceData: PaperTradingPerformancePoint[];
  performanceMetrics: PaperTradingPerformanceMetrics;
  perfCategories: string[];
  perfReturns: number[];
};

export default function PaperTradingAnalytics({
  showAccountBootstrap,
  matchOk,
  navOk,
  matchStatusLabel,
  navStatusLabel,
  onRefreshPrices,
  refreshPricesPending,
  onReconcileLedger,
  reconcilePending,
  accounts,
  accountId,
  onAccountChange,
  statusNotes,
  totalValue,
  cash,
  marketValue,
  returnPct,
  todayPnl,
  perfDays,
  onPerfDaysChange,
  performanceData,
  performanceMetrics,
  perfCategories,
  perfReturns,
}: PaperTradingAnalyticsProps) {
  return (
    <>
      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.12fr)_minmax(320px,0.88fr)]">
          <div>
            <div className="eyebrow">System Status</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">撮合、净值与账户上下文</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              交易时段内会自动刷新价格，非交易时段建议手动刷新后再核对持仓与收益。先确保账户和状态正常，再进入绩效复盘更稳妥。
            </p>
            <div className="toolbar-strip mt-4">
              <Badge variant={matchOk ? 'success' : 'warning'}>撮合 {matchStatusLabel}</Badge>
              <Badge variant={navOk ? 'success' : 'warning'}>净值 {navStatusLabel}</Badge>
              <button
                type="button"
                onClick={onRefreshPrices}
                disabled={refreshPricesPending}
                className={paperTradingChipButtonCls}
              >
                {refreshPricesPending ? '刷新中...' : '刷新价格'}
              </button>
              <button
                type="button"
                onClick={onReconcileLedger}
                disabled={reconcilePending}
                className={paperTradingChipButtonCls}
              >
                {reconcilePending ? '校准中...' : '校准账本'}
              </button>
              {accounts.length > 1 ? (
                <label className="flex min-w-[156px] flex-col gap-2 text-xs text-text-secondary">
                  <span>交易账户</span>
                  <select
                    id="paper-account-select"
                    value={accountId}
                    onChange={(event) => onAccountChange(event.target.value)}
                    className="text-sm"
                  >
                    <option value="">默认账户</option>
                    {accounts.map((account, index) => (
                      <option key={account.account_id ?? index} value={account.account_id ?? ''}>
                        {account.account_id ?? `账户 ${index + 1}`}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="text-xs text-text-secondary">交易时段内每 15 秒自动刷新价格。</div>
              <div className="text-xs text-warning">非交易时段的市价单与盈亏估算可能使用延迟行情。</div>
            </div>
          </div>

          <div className="panel-soft rounded-[24px] p-4">
            <div className="text-sm font-medium text-text-primary">{showAccountBootstrap ? '首笔交易提示' : '状态说明'}</div>
            <div className="mt-3 space-y-3">
              {statusNotes.length > 0 ? (
                statusNotes.map((note) => (
                  <div key={note} className={paperTradingNoteCardCls}>
                    {note}
                  </div>
                ))
              ) : (
                <>
                  <div className={paperTradingNoteCardCls}>当前撮合与净值状态已可用，可以直接继续维护持仓与观察绩效。</div>
                  <div className={paperTradingNoteCardCls}>如遇价格偏差，优先手动刷新一次持仓价格，再核对当日盈亏与净值变化。</div>
                </>
              )}
            </div>
          </div>
        </div>
      </SectionCard>

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="可用资金" value={fmtNum(cash)} />
        <KpiCard title="持仓市值" value={fmtNum(marketValue)} />
        <KpiCard title="总收益率" value={fmtPct(Number(returnPct))} change={Number(returnPct)} />
        <KpiCard title="今日盈亏" value={fmtNum(todayPnl)} change={todayPnl} />
      </KpiGrid>

      {!showAccountBootstrap ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(300px,0.9fr)]">
            <div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">绩效分析</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    这里聚焦模拟盘收益质量，先看窗口收益、回撤和胜率，再决定是否继续追到具体委托和个股。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[7, 30, 90, 0].map((days) => (
                    <button
                      key={days}
                      type="button"
                      onClick={() => onPerfDaysChange(days)}
                      className={`action-chip cursor-pointer text-xs ${perfDays === days ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                    >
                      {days === 0 ? '全部' : `${days} 天`}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      exportCSV(
                        performanceData.map((item) => ({
                          日期: item.date ?? '',
                          净值: item.totalValue ?? 0,
                          日收益率: item.dailyReturn ?? 0,
                        })),
                        `paper-trading-performance-${perfDays || 'all'}.csv`,
                      )
                    }
                    className={paperTradingChipButtonCls}
                  >
                    导出 CSV
                  </button>
                </div>
              </div>
              <KpiGrid cols={5} className="mt-4">
                <KpiCard
                  title="区间收益率"
                  value={fmtPct(Number(performanceMetrics.totalReturn ?? 0) * 100)}
                  change={Number(performanceMetrics.totalReturn ?? 0) * 100}
                />
                <KpiCard title="夏普比率" value={fmtNum(Number(performanceMetrics.sharpe ?? 0))} />
                <KpiCard
                  title="最大回撤"
                  value={fmtPct(Number(performanceMetrics.maxDrawdown ?? 0) * 100)}
                  change={Number(performanceMetrics.maxDrawdown ?? 0) * 100}
                />
                <KpiCard
                  title="胜率"
                  value={fmtPct(Number(performanceMetrics.winRate ?? 0) * 100)}
                  change={Number(performanceMetrics.winRate ?? 0) * 100}
                />
                <KpiCard title="平均持仓天数" value={fmtNum(Number(performanceMetrics.avgHoldDays ?? 0))} />
              </KpiGrid>
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="text-sm font-medium text-text-primary">绩效阅读顺序</div>
              <div className="mt-3 space-y-3">
                <div className={paperTradingNoteCardCls}>先确认区间收益率是否覆盖了成本与风险暴露。</div>
                <div className={paperTradingNoteCardCls}>再看最大回撤与胜率，判断当前交易节奏是否稳定。</div>
                <div className={paperTradingNoteCardCls}>最后结合持仓和成交列表，定位收益来自哪里、拖累来自哪里。</div>
              </div>
            </div>
          </div>

          <div className="mt-4">
            {performanceData.length > 1 ? (
              <LineChart categories={perfCategories} series={[{ name: '日收益率(%)', data: perfReturns }]} />
            ) : (
              <div className="panel-soft rounded-[22px] px-4 py-3 text-sm text-text-secondary">暂无足够绩效数据</div>
            )}
          </div>
        </SectionCard>
      ) : null}
    </>
  );
}
