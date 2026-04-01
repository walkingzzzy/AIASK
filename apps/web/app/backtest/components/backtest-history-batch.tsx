import { Badge, DataTable, SectionCard, SkeletonTable } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import {
  backtestInputCls,
  backtestLabelCls,
  backtestPrimaryButtonCls,
} from '@/app/backtest/components/backtest-panel-styles';
import { exportCSV } from '@/lib/export';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import type { BacktestBatchResultItem } from '@aiask/shared-types';

type HistoryEntry = {
  code: string;
  strategy: string;
  totalReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  ts: number;
};

type BacktestHistoryBatchProps = {
  historyRows: HistoryEntry[];
  historyLoading: boolean;
  batchCodes: string;
  onBatchCodesChange: (value: string) => void;
  onRunBatch: () => void;
  batchPending: boolean;
  batchError: string | null;
  batchResults: BacktestBatchResultItem[];
};

export default function BacktestHistoryBatch({
  historyRows,
  historyLoading,
  batchCodes,
  onBatchCodesChange,
  onRunBatch,
  batchPending,
  batchError,
  batchResults,
}: BacktestHistoryBatchProps) {
  return (
    <>
      <div id="backtest-history">
        <SectionCard className="mt-4 min-h-[240px] p-4 sm:p-5">
          <h3 className="mt-0">回测历史对比 {historyRows.length > 0 ? `(${historyRows.length})` : ''}</h3>
          {historyLoading ? (
            <SkeletonTable rows={5} cols={7} />
          ) : historyRows.length > 0 ? (
            <DataTable
              rows={historyRows}
              columns={[
                { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                { key: 'strategy', label: '策略' },
                {
                  key: 'totalReturn',
                  label: '总收益',
                  align: 'right' as const,
                  render: (v: unknown) => (
                    <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span>
                  ),
                },
                {
                  key: 'sharpe',
                  label: '夏普',
                  align: 'right' as const,
                  render: (v: unknown) => fmtNum(v as number, 2),
                },
                {
                  key: 'maxDrawdown',
                  label: '最大回撤',
                  align: 'right' as const,
                  render: (v: unknown) => fmtPct(v as number),
                },
                { key: 'winRate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
                {
                  key: 'ts',
                  label: '时间',
                  render: (v: unknown) => {
                    const t = v as number;
                    return t > 0 ? new Date(t).toLocaleString('zh-CN') : '-';
                  },
                },
              ]}
              onExport={() => exportCSV(historyRows, 'backtest-history')}
              mobileCardRender={(row) => (
                <div className="space-y-2 text-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs text-text-secondary">标的 / 策略</div>
                      <div className="font-medium">
                        <StockLink code={String(row.code)} /> · {String(row.strategy ?? '-')}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-text-secondary">总收益</div>
                      <div
                        className={
                          Number(row.totalReturn ?? 0) >= 0 ? 'text-danger font-medium' : 'text-success font-medium'
                        }
                      >
                        {fmtPct(Number(row.totalReturn ?? 0))}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>夏普：{fmtNum(Number(row.sharpe ?? 0), 2)}</div>
                    <div>胜率：{fmtPct(Number(row.winRate ?? 0))}</div>
                    <div>回撤：{fmtPct(Number(row.maxDrawdown ?? 0))}</div>
                    <div>时间：{row.ts ? new Date(Number(row.ts)).toLocaleDateString('zh-CN') : '-'}</div>
                  </div>
                </div>
              )}
            />
          ) : (
            <EmptyState
              text="还没有可对比的历史回测。"
              hint="运行过的结果会自动进入这里，方便横向比较不同标的和策略。"
            />
          )}
        </SectionCard>
      </div>

      <div id="backtest-batch">
        <SectionCard className="mt-4 min-h-[220px] p-4 sm:p-5">
          <h3 className="mt-0">批量回测对比</h3>
          <div className="panel-soft mt-3 flex flex-wrap items-end gap-3 rounded-[24px] p-4">
            <div className="grid gap-1">
              <label htmlFor="backtest-batch-codes" className={backtestLabelCls}>
                股票代码（逗号分隔）
              </label>
              <input
                id="backtest-batch-codes"
                value={batchCodes}
                onChange={(e) => onBatchCodesChange(e.target.value)}
                placeholder="600519,000858,601318"
                className={`${backtestInputCls} w-[280px]`}
              />
            </div>
            <button type="button" onClick={onRunBatch} disabled={batchPending} className={backtestPrimaryButtonCls}>
              {batchPending ? '运行中...' : '批量回测'}
            </button>
          </div>
          {batchError ? <p className="text-danger text-sm mt-2">{batchError}</p> : null}
          {batchPending ? (
            <div className="mt-3">
              <SkeletonTable rows={4} cols={6} />
            </div>
          ) : batchResults.length > 0 ? (
            <DataTable
              rows={batchResults}
              columns={[
                { key: 'code', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                {
                  key: 'success',
                  label: '状态',
                  render: (v: unknown) => {
                    const success = v !== false;
                    return <Badge variant={success ? 'success' : 'danger'}>{success ? '成功' : '失败'}</Badge>;
                  },
                },
                {
                  key: 'total_return',
                  label: '总收益',
                  align: 'right' as const,
                  render: (v: unknown) =>
                    v == null ? '-' : <span className={Number(v) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(Number(v))}</span>,
                },
                {
                  key: 'sharpe_ratio',
                  label: '夏普',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtNum(Number(v), 2)),
                },
                {
                  key: 'max_drawdown',
                  label: '最大回撤',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtPct(Number(v))),
                },
                {
                  key: 'win_rate',
                  label: '胜率',
                  align: 'right' as const,
                  render: (v: unknown) => (v == null ? '-' : fmtPct(Number(v))),
                },
                { key: 'trades_count', label: '交易次数', align: 'right' as const },
                { key: 'reasonCode', label: '失败代码' },
                { key: 'reason', label: '失败原因' },
              ]}
              onExport={() => exportCSV(batchResults, 'batch-backtest')}
              mobileCardRender={(row) => {
                const success = row.success !== false;
                return (
                  <div className="space-y-2 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-xs text-text-secondary">股票代码</div>
                        <div className="font-medium">
                          <StockLink code={String(row.code)} />
                        </div>
                      </div>
                      <Badge variant={success ? 'success' : 'danger'}>{success ? '成功' : '失败'}</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        总收益：
                        {row.total_return == null ? (
                          '-'
                        ) : (
                          <span className={Number(row.total_return) >= 0 ? 'text-danger' : 'text-success'}>
                            {fmtPct(Number(row.total_return))}
                          </span>
                        )}
                      </div>
                      <div>夏普：{row.sharpe_ratio == null ? '-' : fmtNum(Number(row.sharpe_ratio), 2)}</div>
                      <div>最大回撤：{row.max_drawdown == null ? '-' : fmtPct(Number(row.max_drawdown))}</div>
                      <div>胜率：{row.win_rate == null ? '-' : fmtPct(Number(row.win_rate))}</div>
                      <div>交易次数：{fmtNum((row.trades_count ?? 0) as number, 0)}</div>
                      <div>失败代码：{String(row.reasonCode ?? '-')}</div>
                    </div>
                    {!success && row.reason ? <div className="text-xs text-text-secondary">失败原因：{String(row.reason)}</div> : null}
                  </div>
                );
              }}
            />
          ) : (
            <EmptyState
              text="输入多只股票代码后，这里会显示批量回测对比表。"
              hint="结果区已固定预留，批量运行完成后不会把页面其他模块整体挤开。"
            />
          )}
        </SectionCard>
      </div>
    </>
  );
}
