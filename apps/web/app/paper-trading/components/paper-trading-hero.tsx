import { AskAiButton } from '@/components/ask-ai-button';
import { Badge } from '@/components/ui';
import {
  paperTradingChipButtonCls,
  paperTradingNoteCardCls,
  paperTradingPrimaryButtonCls,
  paperTradingSidePanelCls,
} from '@/app/paper-trading/components/paper-trading-panel-styles';
import { fmtNum, fmtPct } from '@/lib/data-utils';

type PaperTradingHeroProps = {
  compactMobile?: boolean;
  showAccountBootstrap: boolean;
  matchOk: boolean;
  navOk: boolean;
  matchStatusLabel: string;
  navStatusLabel: string;
  trimmedCode: string;
  directionLabel: string;
  orderTypeLabel: string;
  estimatedAmount: number | null;
  previewUnitPrice: number | null;
  accountId: string;
  positionsCount: number;
  pendingCount: number;
  tradesCount: number;
  totalValue: number;
  todayPnl: number;
  returnPct: number;
  quantityValue: number;
  useComplianceCheck: boolean;
  urgentExecution: boolean;
  riskHints: string[];
  tradeNotice: string | null;
  error: string | null;
  linkedStrategyId?: string | null;
  linkedStrategyName?: string | null;
  linkedStrategyStatus?: string | null;
  personalStrategyMode?: boolean;
  onRefreshPrices: () => void;
  refreshPricesPending: boolean;
  onReconcileLedger: () => void;
  reconcilePending: boolean;
};

export default function PaperTradingHero({
  compactMobile = false,
  showAccountBootstrap,
  matchOk,
  navOk,
  matchStatusLabel,
  navStatusLabel,
  trimmedCode,
  directionLabel,
  orderTypeLabel,
  estimatedAmount,
  previewUnitPrice,
  accountId,
  positionsCount,
  pendingCount,
  tradesCount,
  totalValue,
  todayPnl,
  returnPct,
  quantityValue,
  useComplianceCheck,
  urgentExecution,
  riskHints,
  tradeNotice,
  error,
  linkedStrategyId,
  linkedStrategyName,
  linkedStrategyStatus,
  personalStrategyMode = false,
  onRefreshPrices,
  refreshPricesPending,
  onReconcileLedger,
  reconcilePending,
}: PaperTradingHeroProps) {
  if (compactMobile) {
    return (
      <>
        <section className="page-hero p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Paper Trading Workspace</Badge>
            <Badge variant={showAccountBootstrap ? 'warning' : 'success'}>
              {showAccountBootstrap ? '待建立交易轨迹' : '账户已就绪'}
            </Badge>
            <Badge variant={matchOk ? 'success' : 'warning'}>撮合 {matchStatusLabel}</Badge>
            <Badge variant={navOk ? 'success' : 'warning'}>净值 {navStatusLabel}</Badge>
          </div>
          <h1 className="mb-0 mt-3 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2rem]">
            模拟交易工作台
          </h1>
          <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">
            先确认账户和链路状态，再直接提交真实模拟委托。
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={onRefreshPrices} disabled={refreshPricesPending} className={paperTradingPrimaryButtonCls}>
              {refreshPricesPending ? '刷新中...' : '刷新价格'}
            </button>
            <button type="button" onClick={onReconcileLedger} disabled={reconcilePending} className={paperTradingChipButtonCls}>
              {reconcilePending ? '校准中...' : '校准账本'}
            </button>
          </div>
          <div className="mt-4">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">账户状态</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{accountId || '默认账户'}</div>
              <div className="mt-1 text-xs text-text-secondary">
                当前标的 {trimmedCode || '-'} ｜ {directionLabel} · {orderTypeLabel}
              </div>
              <div className="mt-2 text-xs text-text-secondary">
                持仓 / 挂单 / 成交 {positionsCount} / {pendingCount} / {tradesCount}
              </div>
              <div className="mt-2 text-xs text-text-secondary">
                资产 {fmtNum(totalValue)} ｜ 今日盈亏 {fmtNum(todayPnl)} ｜ 收益率 {fmtPct(Number(returnPct))}
              </div>
            </div>
          </div>
          <details className="mt-3 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开账户来源与下一步</summary>
            {linkedStrategyId || linkedStrategyName ? (
              <div className="mt-3 rounded-[20px] border border-white/45 bg-white/28 px-4 py-3 text-sm text-text-secondary">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前账户来源</div>
                <div className="mt-2 text-base font-semibold text-text-primary">
                  {linkedStrategyName || linkedStrategyId}
                </div>
                <div className="mt-1 text-xs leading-6 text-text-secondary">
                  {personalStrategyMode ? '这是你的个人模拟盘测试账户，不是工厂孵化账户。' : '当前账户已绑定策略上下文。'}
                  {linkedStrategyStatus ? ` 当前阶段：${linkedStrategyStatus}。` : ''}
                </div>
              </div>
            ) : null}
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className={paperTradingNoteCardCls}>
                预估金额：
                <span className="font-medium text-text-primary">
                  {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
                </span>
                <div className="mt-1">
                  {previewUnitPrice != null && previewUnitPrice > 0 ? `预览单价 ${fmtNum(previewUnitPrice, 2)}` : '待补充价格后生成'}
                </div>
              </div>
              <div className={paperTradingNoteCardCls}>
                执行路径：
                <span className="font-medium text-text-primary">
                  {urgentExecution ? '极速智能路由已开启' : '当前按普通模拟委托处理'}
                </span>
                <div className="mt-1">{useComplianceCheck ? '先做合规检查' : '标准提交流程'}</div>
              </div>
            </div>
            {(tradeNotice ? [tradeNotice, ...riskHints] : riskHints).slice(0, 3).length > 0 ? (
              <div className="mt-3 space-y-3">
                {(tradeNotice ? [tradeNotice, ...riskHints] : riskHints).slice(0, 3).map((hint) => (
                  <div key={hint} className={paperTradingNoteCardCls}>
                    {hint}
                  </div>
                ))}
              </div>
            ) : null}
            {error ? <div className="mt-3 text-xs font-medium text-danger">{error}</div> : null}
          </details>
        </section>
      </>
    );
  }

  return (
    <>
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Paper Trading Workspace</Badge>
              <Badge variant={showAccountBootstrap ? 'warning' : 'success'}>
                {showAccountBootstrap ? '待建立交易轨迹' : '已有账户轨迹'}
              </Badge>
              <Badge variant={matchOk ? 'success' : 'warning'}>撮合 {matchStatusLabel}</Badge>
              <Badge variant={navOk ? 'success' : 'warning'}>净值 {navStatusLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              模拟交易工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里把委托输入、账户状态和绩效观察收成一条连续交易链路。只有真实下单、真实撮合和真实账户变化才会驱动页面更新，不再提供示例委托来伪造完成态。
            </p>
            {linkedStrategyId || linkedStrategyName ? (
              <div className="mt-4 rounded-[24px] border border-white/45 bg-white/28 px-4 py-3 text-sm text-text-secondary shadow-[inset_0_1px_0_rgba(255,255,255,0.58)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前账户来源</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {personalStrategyMode ? <Badge variant="info">个人模拟盘测试</Badge> : null}
                  {personalStrategyMode ? <Badge variant="neutral">非孵化盘</Badge> : null}
                  {linkedStrategyId ? <Badge variant="neutral">来源策略</Badge> : null}
                </div>
                <div className="mt-2 text-base font-semibold text-text-primary">
                  {linkedStrategyName || linkedStrategyId}
                </div>
                <div className="mt-1 text-xs leading-6 text-text-secondary">
                  {personalStrategyMode ? '这是你的个人模拟盘测试账户，不是工厂孵化账户。' : '当前账户已绑定策略上下文。'}
                  {linkedStrategyStatus ? ` 当前阶段：${linkedStrategyStatus}。` : ''}
                </div>
              </div>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={onRefreshPrices} disabled={refreshPricesPending} className={paperTradingPrimaryButtonCls}>
                {refreshPricesPending ? '刷新中...' : '刷新价格'}
              </button>
              <button type="button" onClick={onReconcileLedger} disabled={reconcilePending} className={paperTradingChipButtonCls}>
                {reconcilePending ? '校准中...' : '校准账本'}
              </button>
            </div>

            {!compactMobile ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-4">
                <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    {directionLabel} · {orderTypeLabel}
                  </div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预估金额</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">
                    {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
                  </div>
                  <div className="mt-1 text-xs text-text-secondary">
                    {previewUnitPrice != null && previewUnitPrice > 0
                      ? `预览单价 ${fmtNum(previewUnitPrice, 2)}`
                      : '待补充价格后生成'}
                  </div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">账户状态</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{accountId || '默认账户'}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    持仓 / 挂单 / 成交 {positionsCount} / {pendingCount} / {tradesCount}
                  </div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">资产概览</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{fmtNum(totalValue)}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    今日盈亏 {fmtNum(todayPnl)} · 收益率 {fmtPct(Number(returnPct))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    {directionLabel} · {orderTypeLabel}
                  </div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">账户状态</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{accountId || '默认账户'}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    持仓 / 挂单 / 成交 {positionsCount} / {pendingCount} / {tradesCount}
                  </div>
                </div>
              </div>
            )}
          </div>

          {!compactMobile ? (
            <div className="grid gap-3">
              <div className={paperTradingSidePanelCls}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
                <div className="mt-3 text-base font-semibold text-text-primary">
                  {showAccountBootstrap ? '先完成第一笔模拟委托' : '继续处理账户状态与委托结果'}
                </div>
                <div className="mt-4 space-y-3">
                  <div className={paperTradingNoteCardCls}>
                    方向 / 数量：
                    <span className="font-medium text-text-primary">
                      {directionLabel} /{' '}
                      {Number.isFinite(quantityValue) && quantityValue > 0 ? `${quantityValue} 股` : '待填写'}
                    </span>
                  </div>
                  <div className={paperTradingNoteCardCls}>
                    风控流程：
                    <span className="font-medium text-text-primary">
                      {useComplianceCheck ? '先做合规检查' : '标准提交流程'}
                    </span>
                  </div>
                  <div className={paperTradingNoteCardCls}>
                    执行路径：
                    <span className="font-medium text-text-primary">
                      {urgentExecution ? '极速智能路由已开启' : '当前按普通模拟委托处理'}
                    </span>
                  </div>
                </div>
                <div className="mt-4">
                  <AskAiButton
                    stockCode={trimmedCode || undefined}
                    summary={`账户 ${accountId || 'default'}，持仓 ${positionsCount} 条，挂单 ${pendingCount} 条`}
                    prompt="请评估当前模拟盘状态，并给出下一步操作建议"
                  />
                </div>
              </div>

              <div className={paperTradingSidePanelCls}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步动作</div>
                <div className="mt-4 space-y-3">
                  {(tradeNotice ? [tradeNotice, ...riskHints] : riskHints).slice(0, 3).map((hint) => (
                    <div key={hint} className={paperTradingNoteCardCls}>
                      {hint}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      {error ? <div className="panel-soft mb-4 rounded-[20px] px-4 py-3 text-xs font-medium text-danger">{error}</div> : null}

      {tradeNotice ? (
        <div className="panel-soft mb-4 rounded-[24px] px-4 py-3 text-sm text-primary">{tradeNotice}</div>
      ) : null}
    </>
  );
}
