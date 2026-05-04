'use client';

import { useMemo } from 'react';
import { ErrorState } from '@/components/status-state';
import { useApiQuery } from '@/hooks/use-api-query';
import { Badge, SectionCard } from '@/components/ui';

type UnifiedDecisionDiffLogListProps = {
  code?: string;
  enabled?: boolean;
  limit?: number;
};

type DiffLogRecord = {
  id: string;
  stockCode: string;
  investmentStyle: string;
  unifiedAction: string;
  actionAlignment: 'aligned' | 'mixed' | 'divergent' | string;
  legacyActions: Array<{ source: string; action: string }>;
  disagreements: string[];
  diffSummary: string;
  createdAt: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

function normalizeLog(value: unknown, index: number): DiffLogRecord {
  const row = asRecord(value);
  const legacyActions = Array.isArray(row.legacyActions)
    ? row.legacyActions.map((item) => {
        const entry = asRecord(item);
        return {
          source: asText(entry.source) || 'legacy',
          action: asText(entry.action) || 'unknown',
        };
      })
    : [];

  return {
    id: asText(row.id) || `diff-log-${index}`,
    stockCode: asText(row.stockCode) || '-',
    investmentStyle: asText(row.investmentStyle) || '-',
    unifiedAction: asText(row.unifiedAction) || '-',
    actionAlignment: asText(row.actionAlignment) || 'mixed',
    legacyActions,
    disagreements: Array.isArray(row.disagreements)
      ? row.disagreements.map((item) => asText(item)).filter(Boolean)
      : [],
    diffSummary: asText(row.diffSummary) || '暂无差异摘要',
    createdAt: asText(row.createdAt),
  };
}

function formatTimestamp(value: string): string {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function alignmentVariant(value: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (value === 'aligned') return 'success';
  if (value === 'divergent') return 'danger';
  if (value === 'mixed') return 'warning';
  return 'neutral';
}

export default function UnifiedDecisionDiffLogList({
  code,
  enabled = false,
  limit = 6,
}: UnifiedDecisionDiffLogListProps) {
  const trimmedCode = String(code ?? '').trim();
  const queryPath = enabled
    ? `/assistant/unified-decision/diff-logs?limit=${Math.max(1, Math.min(20, limit))}${trimmedCode ? `&code=${encodeURIComponent(trimmedCode)}` : ''}`
    : null;

  const logsQ = useApiQuery<unknown>(queryPath, {
    staleTime: 15000,
    parse: (raw) => raw,
  });

  const items = useMemo(() => {
    const payload = asRecord(logsQ.data);
    const rawItems = Array.isArray(payload.items)
      ? payload.items
      : Array.isArray(asRecord(payload.data).items)
        ? (asRecord(payload.data).items as unknown[])
        : [];
    return rawItems.map((item, index) => normalizeLog(item, index));
  }, [logsQ.data]);

  if (!enabled) {
    return (
      <SectionCard className="mt-4 p-4">
        <div className="text-sm font-semibold text-text-primary">历史接口差异记录</div>
        <div className="mt-2 text-sm text-text-muted">开启历史接口对照后，这里会显示当前用户最近的统一决策差异记录。</div>
      </SectionCard>
    );
  }

  if (logsQ.error) {
    return (
      <SectionCard className="mt-4 p-4">
        <ErrorState text={logsQ.error} hint="最近的历史接口差异记录暂时不可用，请稍后重试。" onRetry={() => void logsQ.refetch()} />
      </SectionCard>
    );
  }

  return (
    <SectionCard className="mt-4 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-text-primary">历史接口差异记录</div>
          <div className="mt-1 text-xs text-text-muted">
            {trimmedCode ? `当前标的 ${trimmedCode} 最近的统一决策灰度对比记录。` : '当前用户最近的统一决策灰度对比记录。'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void logsQ.refetch()}
          className="rounded-md border border-glass-border bg-surface px-3 py-2 text-sm text-text-primary transition hover:bg-surface-alt"
        >
          {logsQ.isFetching ? '刷新中...' : '刷新历史'}
        </button>
      </div>

      {!items.length ? (
        <div className="mt-4 rounded-lg bg-surface-alt/30 px-3 py-4 text-sm text-text-muted">
          {logsQ.isFetching ? '正在加载最近的 diff 记录...' : '当前筛选条件下暂无 legacy diff 历史。'}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {items.map((item) => (
            <div key={item.id} className="rounded-xl border border-glass-border bg-surface-alt/20 p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={alignmentVariant(item.actionAlignment)}>{item.actionAlignment}</Badge>
                  <Badge variant="neutral">{item.stockCode}</Badge>
                  <Badge variant="info">{item.investmentStyle}</Badge>
                </div>
                <div className="text-xs text-text-muted">{formatTimestamp(item.createdAt)}</div>
              </div>

              <div className="mt-3 text-sm text-text-primary">
                统一决策动作: <span className="font-medium">{item.unifiedAction}</span>
              </div>
              <div className="mt-2 text-sm text-text-secondary">{item.diffSummary}</div>

              {item.legacyActions.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.legacyActions.map((legacy) => (
                    <Badge key={`${item.id}-${legacy.source}`} variant="neutral">
                      {legacy.source}: {legacy.action}
                    </Badge>
                  ))}
                </div>
              ) : null}

              {item.disagreements.length ? (
                <div className="mt-3 space-y-2">
                  {item.disagreements.slice(0, 3).map((disagreement, index) => (
                    <div key={`${item.id}-diff-${index}`} className="rounded-lg bg-surface px-3 py-2 text-xs text-text-secondary">
                      {disagreement}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
