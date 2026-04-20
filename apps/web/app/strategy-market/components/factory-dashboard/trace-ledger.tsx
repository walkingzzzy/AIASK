'use client';

import { Badge } from '@/components/ui';
import { formatTaskLabel } from '@/app/strategy-market/lib/factory-dashboard-helpers';
import type {
  FactoryGateFamilyOutcomeSummary,
  FactoryPredictionTraceLedgerEntry,
  FactoryPredictionTraceLedgerNode,
  FactoryPredictionTraceLedgerSummary,
  StrategyPredictionTraceGateDecisions,
} from '../../types';

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asTypedObject<T extends Record<string, unknown>>(value: unknown): Partial<T> {
  return isObjectRecord(value) ? (value as Partial<T>) : {};
}

function toDisplayTextList(value: unknown, limit = 4) {
  if (!Array.isArray(value)) return [] as string[];
  return value
    .map((item) => String(item ?? '').trim())
    .filter(Boolean)
    .slice(0, limit);
}

function toDisplayText(value: unknown) {
  if (value == null) return null;
  const text = String(value).trim();
  return text || null;
}

function toDisplayNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatArtifactObjectSummary(value: unknown, limit = 4) {
  if (!isObjectRecord(value)) return '-';
  const entries = Object.entries(value)
    .filter(([, raw]) => {
      if (raw == null || raw === '') return false;
      if (Array.isArray(raw)) return raw.length > 0;
      if (isObjectRecord(raw)) return Object.keys(raw).length > 0;
      return true;
    })
    .slice(0, limit)
    .map(([key, raw]) => `${key}:${Array.isArray(raw) ? raw.join(',') : String(raw)}`);
  return entries.length > 0 ? entries.join(' / ') : '-';
}

function traceBadgeVariant(status: unknown): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(status ?? '').trim().toLowerCase();
  if (!normalized) return 'neutral';
  if (['success', 'succeeded', 'completed', 'recorded', 'ready', 'proceed', 'healthy', 'passed'].includes(normalized)) {
    return 'success';
  }
  if (['failed', 'error', 'blocked', 'rejected', 'halted'].includes(normalized)) {
    return 'danger';
  }
  if (['partial', 'running', 'pending', 'degraded', 'warning'].includes(normalized)) {
    return 'warning';
  }
  return 'info';
}

export function toLedgerEntries(value: unknown): FactoryPredictionTraceLedgerEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is FactoryPredictionTraceLedgerEntry => isObjectRecord(item));
}

function asLedgerNode(value: unknown): Partial<FactoryPredictionTraceLedgerNode> {
  return asTypedObject<FactoryPredictionTraceLedgerNode>(value);
}

function asTraceGateDecisions(value: unknown): Partial<StrategyPredictionTraceGateDecisions> {
  return asTypedObject<StrategyPredictionTraceGateDecisions>(value);
}

function traceNodeHasFallback(node: Partial<FactoryPredictionTraceLedgerNode> | undefined) {
  return String(node?.source_mode ?? '').trim().toLowerCase() === 'summary_fallback';
}

function traceNodeSummary(node: Partial<FactoryPredictionTraceLedgerNode> | undefined) {
  const available = Boolean(node?.available);
  const count = toDisplayNumber(node?.count);
  const status = toDisplayText(node?.status);
  return [
    available ? 'Y' : 'N',
    count != null ? String(count) : '-',
    status ?? '-',
  ].join(' / ');
}

function traceNodeDetails(node: Partial<FactoryPredictionTraceLedgerNode> | undefined, preferredKeys: string[]) {
  const payload = node ?? {};
  return preferredKeys
    .map((key) => [key, payload[key as keyof FactoryPredictionTraceLedgerNode]] as const)
    .filter(([, value]) => {
      if (value == null || value === '') return false;
      if (Array.isArray(value)) return value.length > 0;
      if (isObjectRecord(value)) return Object.keys(value).length > 0;
      return true;
    });
}

export function FactoryPredictionTraceLedgerPanel({
  ledger,
  predictionTraceId,
}: {
  ledger: Partial<FactoryPredictionTraceLedgerSummary>;
  predictionTraceId?: string | null;
}) {
  const entries = toLedgerEntries(ledger.entries);
  if (entries.length === 0) return null;

  const renderNodeCell = (nodeLike: unknown, detailKeys: string[]) => {
    const node = asLedgerNode(nodeLike);
    const fallback = traceNodeHasFallback(node);
    const detailRows = traceNodeDetails(node, detailKeys);
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{traceNodeSummary(node)}</span>
          {fallback ? <Badge variant="warning">降级</Badge> : null}
        </div>
        {detailRows.length > 0 && (
          <details className="text-[11px] text-text-secondary">
            <summary className="cursor-pointer select-none">详情</summary>
            <div className="mt-1 space-y-1">
              {detailRows.map(([key, raw]) => (
                <div key={String(key)}>
                  {String(key)}: {Array.isArray(raw) ? raw.join(' / ') : isObjectRecord(raw) ? formatArtifactObjectSummary(raw) : String(raw)}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs font-medium text-text-primary">Prediction Trace Ledger</div>
        <div className="text-xs text-text-secondary">
          Trace 数：{entries.length}
          {predictionTraceId ? ` · 当前 ${predictionTraceId}` : ''}
        </div>
      </div>
      <div className="overflow-x-auto rounded border border-border bg-surface">
        <table className="min-w-full text-xs text-left text-text-secondary">
          <thead className="bg-surface-alt text-text-primary">
            <tr>
              <th className="px-3 py-2 font-medium">trace_id</th>
              <th className="px-3 py-2 font-medium">signal</th>
              <th className="px-3 py-2 font-medium">order</th>
              <th className="px-3 py-2 font-medium">fill</th>
              <th className="px-3 py-2 font-medium">round_trip</th>
              <th className="px-3 py-2 font-medium">pnl</th>
              <th className="px-3 py-2 font-medium">gate</th>
              <th className="px-3 py-2 font-medium">gaps</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, idx) => {
              const signalNode = asLedgerNode(entry.signal_event);
              const orderNode = asLedgerNode(entry.intended_order);
              const fillNode = asLedgerNode(entry.actual_fill);
              const roundTripNode = asLedgerNode(entry.position_round_trip);
              const pnlNode = asLedgerNode(entry.pnl_audit_summary);
              const gateDecisions = asTraceGateDecisions(entry.gate_decisions);
              const hasFallback = [signalNode, orderNode, fillNode, roundTripNode, pnlNode].some(traceNodeHasFallback);
              const familyOutcomeSummary = asTypedObject<FactoryGateFamilyOutcomeSummary>(entry.family_outcome_summary);
              const gapCodes = toDisplayTextList(entry.evidence_gap_codes, 8);
              return (
                <tr key={String(entry.prediction_trace_id ?? idx)} className="border-t border-border align-top">
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="font-medium text-text-primary break-all">
                        {String(entry.prediction_trace_id ?? '-')}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {hasFallback ? <Badge variant="warning">summary_fallback</Badge> : <Badge variant="success">entity_backed</Badge>}
                        {predictionTraceId && entry.prediction_trace_id === predictionTraceId ? <Badge variant="info">当前</Badge> : null}
                      </div>
                      <details className="text-[11px] text-text-secondary">
                        <summary className="cursor-pointer select-none">展开</summary>
                        <div className="mt-1 space-y-1">
                          <div>artifact_ids: {toDisplayTextList(entry.artifact_ids, 8).join(' / ') || '-'}</div>
                          <div>retrieval_context_ids: {toDisplayTextList(entry.retrieval_context_ids, 8).join(' / ') || '-'}</div>
                          <div>family_outcome: {formatArtifactObjectSummary(familyOutcomeSummary, 6)}</div>
                        </div>
                      </details>
                    </div>
                  </td>
                  <td className="px-3 py-2">{renderNodeCell(signalNode, ['latest_signal_snapshot_id', 'recent_signal_ids', 'signal_evidence_count', 'runtime_action_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(orderNode, ['paper_account_id', 'order_ids', 'order_status_counts'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(fillNode, ['trade_ids', 'linked_signal_count', 'linked_position_count', 'realized_trade_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(roundTripNode, ['position_ids', 'mapped_position_count', 'closed_position_count', 'round_trip_close_rate', 'incomplete_position_count'])}</td>
                  <td className="px-3 py-2">{renderNodeCell(pnlNode, ['nav_row_count', 'realized_pnl_total', 'trade_expectancy', 'pnl_conversion_efficiency', 'execution_conversion_efficiency'])}</td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap gap-1">
                        {toDisplayText(gateDecisions.execution_audit_gate_status) ? (
                          <Badge variant={traceBadgeVariant(gateDecisions.execution_audit_gate_status)}>
                            {formatTaskLabel(gateDecisions.execution_audit_gate_status)}
                          </Badge>
                        ) : null}
                        <Badge variant={gateDecisions.hard_gate_passed ? 'success' : 'neutral'}>
                          hard_gate {gateDecisions.hard_gate_passed ? 'pass' : 'hold'}
                        </Badge>
                        <Badge variant={gateDecisions.promotion_ready ? 'success' : 'warning'}>
                          promotion {gateDecisions.promotion_ready ? 'ready' : 'hold'}
                        </Badge>
                      </div>
                      {toDisplayTextList(gateDecisions.failure_reasons, 6).length > 0 ? (
                        <details className="text-[11px] text-text-secondary">
                          <summary className="cursor-pointer select-none">failure_reasons</summary>
                          <div className="mt-1 break-all">{toDisplayTextList(gateDecisions.failure_reasons, 6).join(' / ')}</div>
                        </details>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap gap-1">
                        {gapCodes.length > 0 ? gapCodes.map((code) => (
                          <Badge key={code} variant="warning">{code}</Badge>
                        )) : <span>-</span>}
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
