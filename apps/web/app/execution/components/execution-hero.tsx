import { Badge } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import type { ExecutionInsight } from '@/lib/execution-normalizers';
import {
  executionChipButtonCls,
  executionNoteCardCls,
  executionPrimaryButtonCls,
  executionSecondaryButtonCls,
  executionSidePanelCls,
} from '@/app/execution/components/execution-panel-styles';

type ExecutionHeroProps = {
  urgency: 'normal' | 'high';
  liveGatewayReady: boolean;
  activeExecutionCode: string;
  currentArtifactId: string;
  trimmedCode: string;
  direction: 'buy' | 'sell';
  quantity: string;
  estimatedAmount: number | null;
  orderType: 'market' | 'limit' | 'stop';
  currentExecutionId: string;
  executionInsight: ExecutionInsight | null;
  workbenchWarningCount: number;
  pendingOrderCount: number;
  liveOrderCount: number;
  liveFillCount: number;
  summaryText: string;
  executionGuidance: string[];
  onOpenPerformanceReview: () => void;
  onOpenRiskReview: () => void;
  onOpenStockDetail: (code: string) => void;
  onOpenArtifactDetail: (artifactId: string) => void;
  onStatusQuery: () => void;
  onRefreshLiveGateway: () => void;
};

export default function ExecutionHero({
  urgency,
  liveGatewayReady,
  activeExecutionCode,
  currentArtifactId,
  trimmedCode,
  direction,
  quantity,
  estimatedAmount,
  orderType,
  currentExecutionId,
  executionInsight,
  workbenchWarningCount,
  pendingOrderCount,
  liveOrderCount,
  liveFillCount,
  summaryText,
  executionGuidance,
  onOpenPerformanceReview,
  onOpenRiskReview,
  onOpenStockDetail,
  onOpenArtifactDetail,
  onStatusQuery,
  onRefreshLiveGateway,
}: ExecutionHeroProps) {
  return (
    <section className="page-hero p-5 sm:p-6">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Execution Workspace</Badge>
            <Badge variant={urgency === 'high' ? 'warning' : 'neutral'}>
              {urgency === 'high' ? '高优先级 VWAP' : '标准 TWAP'}
            </Badge>
            <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
              {liveGatewayReady ? '真实网关已连接' : '仅工作台 / 模拟链路'}
            </Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            执行工作台
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
            这里负责把下单参数、执行回执、实时网关和复盘入口收进一个操作面。重点不是替代模拟交易页，而是把一次执行后的状态、告警与后续动作压缩到可连续处理的首屏里。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={onOpenPerformanceReview} className={executionPrimaryButtonCls}>
              去绩效中心复盘
            </button>
            <button type="button" onClick={onOpenRiskReview} className={executionSecondaryButtonCls}>
              去风险中心核查
            </button>
            {activeExecutionCode ? (
              <button
                type="button"
                onClick={() => onOpenStockDetail(activeExecutionCode)}
                className={executionSecondaryButtonCls}
              >
                打开个股详情
              </button>
            ) : null}
            {currentArtifactId ? (
              <button
                type="button"
                onClick={() => onOpenArtifactDetail(currentArtifactId)}
                className={executionSecondaryButtonCls}
              >
                查看 Artifact
              </button>
            ) : null}
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {direction === 'buy' ? '买入方向' : '卖出方向'} · {quantity || '-'} 股
              </div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预估成交额</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">
                {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {orderType === 'market'
                  ? '市价单以实时价格成交'
                  : orderType === 'limit'
                    ? '按限价约束成交'
                    : '按止损条件触发'}
              </div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">执行单号</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{currentExecutionId || '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {executionInsight?.status ? `状态 ${executionInsight.status}` : '提交后会自动回填执行状态'}
              </div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">软闸门</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">
                {executionInsight?.warningCount ?? workbenchWarningCount}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {executionInsight?.hasHighSeverity ? '存在高严重级告警' : '当前没有高严重级告警'}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className={executionSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前执行摘要</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{summaryText}</div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <div className={executionNoteCardCls}>
                挂单数量：<span className="font-medium text-text-primary">{pendingOrderCount}</span>
              </div>
              <div className={executionNoteCardCls}>
                最近 Artifact：<span className="font-medium text-text-primary">{currentArtifactId || '-'}</span>
              </div>
              <div className={executionNoteCardCls}>
                真实订单 / 成交：
                <span className="font-medium text-text-primary">
                  {liveOrderCount} / {liveFillCount}
                </span>
              </div>
            </div>
          </div>

          <div className={executionSidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">复盘建议</div>
            <div className="mt-4 space-y-3">
              {executionGuidance.slice(0, 3).map((item) => (
                <div key={item} className={executionNoteCardCls}>
                  {item}
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={onStatusQuery} className={executionChipButtonCls}>
                查询执行状态
              </button>
              <button type="button" onClick={onRefreshLiveGateway} className={executionChipButtonCls}>
                刷新网关
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
