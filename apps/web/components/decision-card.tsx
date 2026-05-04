'use client';

type CardData = {
  version?: string;
  scene?: string;
  action?: 'buy' | 'hold' | 'reduce' | 'sell' | 'watch' | string;
  confidence?: number;
  finalScore?: number | null;
  summary?: string;
  reasons?: string[];
  executionPlan?: string[] | { position?: string; buy_zone?: string; stop_loss?: string; take_profit?: string[] };
  execution_plan?: { position?: string; buy_zone?: string; stop_loss?: string; take_profit?: string[] };
  risks?: string[];
  gateFlags?: Array<{ name?: string; status?: string; severity?: string; blocking?: boolean; message?: string; source?: string }>;
  gate_flags?: Array<{ name?: string; status?: string; severity?: string; blocking?: boolean; message?: string; source?: string }>;
  vetoReason?: string | null;
  veto_reason?: string | null;
  rawAiAction?: string | null;
  raw_ai_action?: string | null;
  recommendedHorizon?: string | null;
  recommended_horizon?: string | null;
  updatedAt?: string | null;
  updated_at?: string | null;
  fallbackReason?: string[];
  fallback_reason?: string[];
  positionSignal?: {
    label?: string;
    suggestedPositionPct?: number | null;
    positionCapPct?: number | null;
    requestedStyle?: string;
    userRiskLevel?: string | null;
  } | null;
  position_signal?: {
    label?: string;
    suggested_position_pct?: number | null;
    position_cap_pct?: number | null;
    requested_style?: string;
    user_risk_level?: string | null;
  } | null;
  dataProvenance?: Array<string | { source?: string; dataset?: string; timestamp?: string }>;
  data_provenance?: Array<{ source?: string; dataset?: string; timestamp?: string }>;
  timeliness?: Record<string, string>;
  complianceNotice?: string;
  compliance_notice?: string;
};

const ACTION_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  buy: { bg: 'bg-success/15', text: 'text-success', label: '买入' },
  hold: { bg: 'bg-warning/15', text: 'text-warning', label: '持有' },
  reduce: { bg: 'bg-danger/15', text: 'text-danger', label: '减仓' },
  sell: { bg: 'bg-danger/15', text: 'text-danger', label: '卖出' },
  watch: { bg: 'bg-glass', text: 'text-text-secondary', label: '观望' },
};

function formatConfidence(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  const percent = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
  return `${Math.max(0, Math.min(100, percent)).toFixed(0)}%`;
}

export default function DecisionCard({ data }: { data: CardData }) {
  const a = ACTION_STYLE[data.action ?? ''] ?? ACTION_STYLE.watch;
  const pct = data.confidence != null ? formatConfidence(data.confidence) : '-';
  const finalScore = data.finalScore;
  const executionPlan = data.executionPlan ?? data.execution_plan;
  const executionPlanDetails = executionPlan && !Array.isArray(executionPlan) ? executionPlan : null;
  const provenance = data.dataProvenance ?? data.data_provenance;
  const complianceNotice = data.complianceNotice ?? data.compliance_notice;
  const gateFlags = data.gateFlags ?? data.gate_flags;
  const vetoReason = data.vetoReason ?? data.veto_reason;
  const rawAiAction = data.rawAiAction ?? data.raw_ai_action;
  const recommendedHorizon = data.recommendedHorizon ?? data.recommended_horizon;
  const updatedAt = data.updatedAt ?? data.updated_at;
  const fallbackReason = data.fallbackReason ?? data.fallback_reason;
  const positionSignal = data.positionSignal
    ?? (data.position_signal
      ? {
          label: data.position_signal.label,
          suggestedPositionPct: data.position_signal.suggested_position_pct,
          positionCapPct: data.position_signal.position_cap_pct,
          requestedStyle: data.position_signal.requested_style,
          userRiskLevel: data.position_signal.user_risk_level,
        }
      : null);
  const suggestedPositionPct = positionSignal?.suggestedPositionPct != null
    ? formatConfidence(positionSignal.suggestedPositionPct)
    : null;
  const positionCapPct = positionSignal?.positionCapPct != null
    ? formatConfidence(positionSignal.positionCapPct)
    : null;

  return (
    <div className="surface-card rounded-xl p-4 mt-3">
      <div className="flex gap-2.5 items-center mb-2.5">
        <span className={`${a.bg} ${a.text} px-3 py-1 rounded-md font-bold`}>{a.label}</span>
        <span className="text-text-muted">置信度 {pct}</span>
        {finalScore != null ? <span className="text-text-muted">综合分 {finalScore.toFixed(1)}</span> : null}
      </div>
      {data.summary ? <p className="my-2 font-medium">{data.summary}</p> : null}
      {rawAiAction || recommendedHorizon ? (
        <div className="my-2 flex flex-wrap gap-2 text-xs text-text-muted">
          {rawAiAction ? <span className="rounded-md bg-surface-alt px-2 py-1">原始 AI 判断: {rawAiAction}</span> : null}
          {recommendedHorizon ? <span className="rounded-md bg-surface-alt px-2 py-1">建议观察周期: {recommendedHorizon}</span> : null}
        </div>
      ) : null}
      {vetoReason ? (
        <div className="my-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          当前触发统一闸门：{vetoReason}
        </div>
      ) : null}
      {positionSignal ? (
        <div className="my-2 p-2.5 surface-muted rounded-lg">
          <b>仓位信号</b>
          <div className="mt-1 text-sm text-text-secondary">
            {positionSignal.label ?? '暂不出手'}
            {suggestedPositionPct ? `，建议仓位 ${suggestedPositionPct}` : ''}
            {positionCapPct ? `，上限 ${positionCapPct}` : ''}
          </div>
          {positionSignal.requestedStyle || positionSignal.userRiskLevel ? (
            <div className="mt-1 text-xs text-text-muted">
              风格 {positionSignal.requestedStyle ?? '-'} / 用户风险偏好 {positionSignal.userRiskLevel ?? '-'}
            </div>
          ) : null}
        </div>
      ) : null}
      {gateFlags?.length ? (
        <div className="my-2">
          <b>闸门状态：</b>
          <div className="mt-2 flex flex-wrap gap-2">
            {gateFlags.map((flag, index) => (
              <span
                key={`${flag.name ?? 'gate'}-${index}`}
                className={`rounded-md px-2 py-1 text-xs ${
                  flag.blocking
                    ? 'bg-danger/15 text-danger'
                    : flag.status === 'warn'
                      ? 'bg-warning/15 text-warning'
                      : 'bg-success/15 text-success'
                }`}
                title={flag.message ?? ''}
              >
                {(flag.name ?? 'gate').replace(/_/g, ' ')}: {flag.message ?? flag.status ?? 'ok'}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {data.reasons?.length ? (
        <div className="my-2">
          <b>理由：</b>
          <ul className="my-1 pl-5">{data.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ) : null}
      {Array.isArray(executionPlan) && executionPlan.length > 0 ? (
        <div className="my-2 p-2.5 surface-muted rounded-lg">
          <b>执行计划</b>
          <ul className="my-1 pl-5 text-sm text-text-secondary">{executionPlan.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      ) : executionPlanDetails ? (
        <div className="my-2 p-2.5 surface-muted rounded-lg">
          <b>执行计划</b>
          <div>仓位：{executionPlanDetails.position ?? '-'}</div>
          {executionPlanDetails.buy_zone ? <div>买入区间：{executionPlanDetails.buy_zone}</div> : null}
          {executionPlanDetails.stop_loss ? <div>止损：{executionPlanDetails.stop_loss}</div> : null}
          {executionPlanDetails.take_profit?.length ? <div>止盈：{executionPlanDetails.take_profit.join(' / ')}</div> : null}
        </div>
      ) : null}

      {data.risks?.length ? (
        <div className="my-2">
          <b className="text-danger">风险提示：</b>
          <ul className="my-1 pl-5 text-sm text-text-secondary">{data.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ) : null}

      {provenance?.length ? (
        <details className="my-2 text-xs text-text-muted">
          <summary className="cursor-pointer">数据溯源</summary>
          <div className="mt-1 surface-muted rounded-lg p-2 space-y-1">
            {provenance.map((item, i) => {
              if (typeof item === 'string') return <div key={i}>{item}</div>;
              return <div key={i}>{item.source} / {item.dataset} — {item.timestamp}</div>;
            })}
          </div>
        </details>
      ) : null}

      {fallbackReason?.length ? (
        <details className="my-2 text-xs text-text-muted">
          <summary className="cursor-pointer">降级记录</summary>
          <div className="mt-1 surface-muted rounded-lg p-2 space-y-1">
            {fallbackReason.map((item, index) => <div key={`${item}-${index}`}>{item}</div>)}
          </div>
        </details>
      ) : null}

      {updatedAt ? (
        <div className="mt-2 text-xs text-text-muted">数据更新时间：{updatedAt}</div>
      ) : null}

      {complianceNotice ? (
        <div className="mt-2 text-xs surface-muted rounded-lg p-2 text-text-muted">{complianceNotice}</div>
      ) : null}
    </div>
  );
}
