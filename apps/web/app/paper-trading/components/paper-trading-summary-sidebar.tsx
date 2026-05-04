import { SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';

type PaperTradingSummarySidebarProps = {
  accountId: string;
  trimmedCode: string;
  directionLabel: string;
  orderTypeLabel: string;
  estimatedAmount: number | null;
  positionsCount: number;
  pendingCount: number;
  tradesCount: number;
  matchStatusLabel: string;
  navStatusLabel: string;
  totalValue: number;
  perfDays: number;
  todayPnl: number;
  useComplianceCheck: boolean;
  urgentExecution: boolean;
};

export default function PaperTradingSummarySidebar({
  accountId,
  trimmedCode,
  directionLabel,
  orderTypeLabel,
  estimatedAmount,
  positionsCount,
  pendingCount,
  tradesCount,
  matchStatusLabel,
  navStatusLabel,
  totalValue,
  perfDays,
  todayPnl,
  useComplianceCheck,
  urgentExecution,
}: PaperTradingSummarySidebarProps) {
  return (
    <SectionCard className="p-4 sm:p-5">
      <div className="eyebrow">模拟盘摘要</div>
      <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">模拟盘工作区摘要</h3>
      <div className="mt-4 grid gap-3">
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">账户与委托</div>
          <div className="metric-value mt-3 text-[1.45rem]">{accountId || '默认账户'}</div>
          <div className="mt-2 text-xs text-text-secondary">
            {trimmedCode || '未填写标的'} · {directionLabel} / {orderTypeLabel}
          </div>
          <div className="mt-1 text-xs text-text-secondary">预估金额 {estimatedAmount != null ? fmtNum(estimatedAmount) : '待补价格'}</div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">账户轨迹</div>
          <div className="metric-value mt-3 text-[1.45rem]">
            {positionsCount} / {pendingCount} / {tradesCount}
          </div>
          <div className="mt-2 text-xs text-text-secondary">持仓 / 挂单 / 成交</div>
          <div className="mt-1 text-xs text-text-secondary">
            撮合 {matchStatusLabel} · 净值 {navStatusLabel}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">绩效与模式</div>
          <div className="metric-value mt-3 text-[1.45rem]">{fmtNum(totalValue)}</div>
          <div className="mt-2 text-xs text-text-secondary">
            绩效窗口 {perfDays} 天 · 今日盈亏 {fmtNum(todayPnl)}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            {useComplianceCheck ? '已开启合规检查' : '标准提交流程'} · {urgentExecution ? '极速路由已开启' : '普通委托路径'}
          </div>
        </div>
        <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
          保存视图后，可固定账户、下单参数和风控开关，在不同工作区之间快速复用。
        </div>
      </div>
    </SectionCard>
  );
}
