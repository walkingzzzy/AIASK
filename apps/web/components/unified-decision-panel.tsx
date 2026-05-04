'use client';

import DecisionCard from '@/components/decision-card';
import UnifiedDecisionDetails from '@/components/unified-decision-details';

type UnifiedDecisionPanelProps = {
  card: Record<string, unknown>;
  details?: unknown;
  detailsPending?: boolean;
  canLoadDetails?: boolean;
  onLoadDetails?: () => void;
  legacyComparison?: unknown;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

export default function UnifiedDecisionPanel({
  card,
  details,
  detailsPending = false,
  canLoadDetails = false,
  onLoadDetails,
  legacyComparison,
}: UnifiedDecisionPanelProps) {
  const legacy = asRecord(legacyComparison);
  const auditId = legacy.auditId;
  const auditLogged = Boolean(legacy.auditLogged);

  return (
    <div>
      <DecisionCard data={card} />
      <div className="mt-3 rounded-xl border border-glass-border bg-surface-alt/20 p-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm font-medium text-text-primary">统一决策详情</div>
            <div className="text-xs text-text-muted">按层查看 stock / quant / event / gate / fusion 证据。</div>
          </div>
          {canLoadDetails ? (
            <button
              type="button"
              onClick={onLoadDetails}
              disabled={detailsPending || !onLoadDetails}
              className="rounded-md border border-glass-border bg-surface px-3 py-2 text-sm text-text-primary transition hover:bg-surface-alt disabled:opacity-50"
            >
              {detailsPending ? '详情加载中...' : details ? '重新加载详情' : '加载决策详情'}
            </button>
          ) : null}
        </div>

        {legacyComparison ? (
          <div className="mt-3 rounded-lg border border-glass-border bg-surface px-3 py-3 text-xs text-text-secondary">
            <div>legacy diff 对齐状态：{String(legacy.actionAlignment ?? '-')}</div>
            <div>审计落库：{auditLogged ? `已记录 #${String(auditId ?? '-')}` : '未落库'}</div>
          </div>
        ) : null}

        {details ? (
          <UnifiedDecisionDetails details={details} legacyComparison={legacyComparison} />
        ) : (
          <div className="mt-3 space-y-3">
            <div className="rounded-lg bg-surface px-3 py-3 text-sm text-text-muted">
              详情层按需加载，避免默认请求时拉取全部原始上下文。
            </div>
            {legacyComparison ? (
              <div className="rounded-lg border border-glass-border bg-surface px-3 py-3 text-sm text-text-secondary">
                历史接口对比已准备好，加载详情后可查看统一决策与历史结果的差异明细。
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
