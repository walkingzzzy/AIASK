'use client';

import { SectionCard } from '@/components/ui';

type UnifiedDecisionDetailsProps = {
  details: unknown;
  legacyComparison?: unknown;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function asArray<T = Record<string, unknown>>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

function asNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function pct(value: unknown, digits = 1, unit: 'ratio' | 'percent' | 'auto' = 'ratio'): string {
  const numeric = asNumber(value);
  if (numeric == null) return '-';
  const normalized = unit === 'percent' ? numeric : unit === 'auto' ? (Math.abs(numeric) <= 1 ? numeric * 100 : numeric) : numeric * 100;
  return `${normalized.toFixed(digits)}%`;
}

function compactList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (item && typeof item === 'object') {
        const row = item as Record<string, unknown>;
        return asText(row.message ?? row.title ?? row.summary ?? row.label ?? row.category);
      }
      return '';
    })
    .filter(Boolean);
}

function SignalPill({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: 'neutral' | 'good' | 'warn' | 'danger' }) {
  const toneClass = tone === 'good'
    ? 'bg-success/15 text-success'
    : tone === 'warn'
      ? 'bg-warning/15 text-warning'
      : tone === 'danger'
        ? 'bg-danger/15 text-danger'
        : 'bg-surface-alt text-text-secondary';
  return (
    <div className={`rounded-xl px-3 py-2 text-xs ${toneClass}`}>
      <div className="font-medium">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

function RenderStringList({ items, empty = '暂无数据' }: { items: string[]; empty?: string }) {
  if (!items.length) return <div className="text-sm text-text-muted">{empty}</div>;
  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={`${item}-${index}`} className="rounded-lg bg-surface-alt/30 px-3 py-2 text-sm text-text-secondary">
          {item}
        </div>
      ))}
    </div>
  );
}

export default function UnifiedDecisionDetails({ details, legacyComparison }: UnifiedDecisionDetailsProps) {
  const root = asRecord(details);
  const stock = asRecord(root.stock_context);
  const quant = asRecord(root.quant_context);
  const event = asRecord(root.event_context);
  const gate = asRecord(root.gate_result ?? root.gate);
  const fusion = asRecord(root.fusion);
  const marketSnapshot = asRecord(stock.market_snapshot);
  const fundFlowSnapshot = asRecord(stock.fund_flow_snapshot);
  const probabilityTargets = asRecord(quant.probability_targets);
  const confidenceMeta = asRecord(quant.confidence_meta);
  const rawAi = asRecord(fusion.raw_ai_output);
  const legacy = asRecord(legacyComparison);
  const legacyResults = asArray<Record<string, unknown>>(legacy.legacyResults);

  return (
    <div className="mt-4 space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">融合结果层</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <SignalPill label="最终动作" value={asText(fusion.action) || '-'} tone={asText(fusion.veto_reason) ? 'danger' : 'good'} />
            <SignalPill label="综合分" value={String(asNumber(fusion.final_score) ?? '-')} tone="neutral" />
            <SignalPill label="原始 AI 动作" value={asText(rawAi.raw_action) || '-'} tone="neutral" />
            <SignalPill label="建议观察周期" value={asText(rawAi.recommended_horizon) || '-'} tone="warn" />
          </div>
          <div className="mt-3 text-sm text-text-secondary">{asText(rawAi.raw_summary) || asText(fusion.summary)}</div>
        </SectionCard>

        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">上下文得分层</div>
          <div className="grid gap-2 sm:grid-cols-3">
            <SignalPill label="Stock" value={String(asNumber(stock.score) ?? '-')} tone="good" />
            <SignalPill label="Quant" value={String(asNumber(quant.score) ?? '-')} tone="warn" />
            <SignalPill label="Event" value={String(asNumber(event.score) ?? '-')} tone={asText(event.event_direction) === 'bearish' ? 'danger' : 'neutral'} />
          </div>
          <div className="mt-3 text-xs text-text-muted">
            动态权重: stock {asNumber(asRecord(fusion.weights).stock_context) ?? '-'} / quant {asNumber(asRecord(fusion.weights).quant) ?? '-'} / event {asNumber(asRecord(fusion.weights).event) ?? '-'}
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">Stock 证据层</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <SignalPill label="现价" value={String(asNumber(stock.current_price) ?? '-')} tone="neutral" />
            <SignalPill label="流动性评分" value={String(asNumber(marketSnapshot.liquidity_score) ?? '-')} tone="warn" />
            <SignalPill label="主力净流入" value={String(asNumber(fundFlowSnapshot.main_net_inflow) ?? '-')} tone={asText(fundFlowSnapshot.flow_bias) === 'bullish' ? 'good' : 'danger'} />
            <SignalPill label="北向持股占比" value={pct(fundFlowSnapshot.north_hold_ratio, 1, 'auto')} tone="neutral" />
          </div>
          <div className="mt-3 space-y-3">
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">亮点</div>
              <RenderStringList items={compactList(stock.highlights)} />
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">风险</div>
              <RenderStringList items={compactList(stock.risks)} empty="暂无显著风险标签" />
            </div>
          </div>
        </SectionCard>

        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">Quant 证据层</div>
          <div className="grid gap-2 sm:grid-cols-3">
            {Object.entries(probabilityTargets).map(([key, value]) => {
              const row = asRecord(value);
              return (
                <SignalPill
                  key={key}
                  label={`${key} 上涨概率`}
                  value={pct(row.up_probability)}
                  tone={(asNumber(row.up_probability) ?? 0) >= 0.55 ? 'good' : (asNumber(row.up_probability) ?? 0) <= 0.45 ? 'danger' : 'neutral'}
                />
              );
            })}
          </div>
          <div className="mt-3 space-y-2 text-sm text-text-secondary">
            <div>样本量: {asNumber(confidenceMeta.sample_size) ?? '-'}</div>
            <div>稳定性: {asNumber(confidenceMeta.stability_ratio) ?? '-'}</div>
            <div>质量评级: {asText(confidenceMeta.quality) || '-'}</div>
          </div>
          <div className="mt-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">量化理由</div>
            <RenderStringList items={compactList(quant.reasons)} empty="暂无量化正向证据" />
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">Event 证据层</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <SignalPill label="事件方向" value={asText(event.event_direction) || '-'} tone={asText(event.event_direction) === 'bearish' ? 'danger' : 'good'} />
            <SignalPill label="事件强度" value={asText(event.event_intensity) || '-'} tone={asText(event.hard_veto_eligible) === 'true' ? 'danger' : 'warn'} />
            <SignalPill label="观察周期" value={asText(event.event_horizon) || '-'} tone="neutral" />
            <SignalPill label="是否可 veto" value={String(Boolean(event.hard_veto_eligible))} tone={Boolean(event.hard_veto_eligible) ? 'danger' : 'neutral'} />
          </div>
          <div className="mt-3 space-y-3">
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">事件风险候选</div>
              <RenderStringList items={compactList(event.veto_candidates)} empty="暂无强事件 veto 候选" />
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">候选动作</div>
              <RenderStringList items={compactList(event.candidate_actions)} empty="暂无候选动作" />
            </div>
          </div>
        </SectionCard>

        <SectionCard className="p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">规则闸门层</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <SignalPill label="是否阻断" value={String(Boolean(gate.blocked))} tone={Boolean(gate.blocked) ? 'danger' : 'good'} />
            <SignalPill label="仓位上限" value={pct(gate.position_cap_pct)} tone="warn" />
            <SignalPill label="用户风险等级" value={asText(gate.user_risk_level) || '-'} tone="neutral" />
            <SignalPill label="请求风格" value={asText(gate.requested_style) || '-'} tone="neutral" />
          </div>
          <div className="mt-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">闸门命中明细</div>
            <RenderStringList items={compactList(gate.flags)} empty="未触发额外闸门" />
          </div>
        </SectionCard>
      </div>

      {legacyResults.length ? (
        <SectionCard className="p-4">
          <div className="mb-2 text-sm font-semibold text-text-primary">历史接口差异对比</div>
          <div className="text-sm text-text-secondary">{asText(legacy.diffSummary) || '已启用历史接口对照。'}</div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <SignalPill label="对齐状态" value={asText(legacy.actionAlignment) || '-'} tone={asText(legacy.actionAlignment) === 'aligned' ? 'good' : asText(legacy.actionAlignment) === 'divergent' ? 'danger' : 'warn'} />
            <SignalPill label="审计编号" value={asText(legacy.auditId) || '-'} tone={Boolean(legacy.auditLogged) ? 'good' : 'warn'} />
            <SignalPill label="追踪编号" value={asText(legacy.traceId) || '-'} tone="neutral" />
          </div>
          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            {legacyResults.map((item, index) => (
              <div key={`${asText(item.source)}-${index}`} className="rounded-xl border border-glass-border bg-surface-alt/30 p-3">
                <div className="text-xs uppercase tracking-wider text-text-muted">{asText(item.source)}</div>
                <div className="mt-1 text-sm font-semibold text-text-primary">{asText(item.action) || '-'}</div>
                <div className="mt-1 text-xs text-text-muted">置信度 {pct(item.confidence, 0)}</div>
                <div className="mt-2 text-sm text-text-secondary">{asText(item.summary) || '暂无摘要'}</div>
              </div>
            ))}
          </div>
          {compactList(legacy.disagreements).length ? (
            <div className="mt-3">
              <div className="mb-2 text-xs font-medium uppercase tracking-wider text-text-muted">差异摘要</div>
              <RenderStringList items={compactList(legacy.disagreements)} />
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      <details className="rounded-xl border border-glass-border bg-surface-alt/20 p-4">
        <summary className="cursor-pointer text-sm font-medium text-text-primary">查看原始 JSON</summary>
        <pre className="mt-3 max-h-[420px] overflow-auto rounded-lg bg-surface p-3 text-xs text-text-secondary">
          {JSON.stringify(root, null, 2)}
        </pre>
      </details>
    </div>
  );
}
