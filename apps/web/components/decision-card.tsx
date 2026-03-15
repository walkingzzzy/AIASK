'use client';

type CardData = {
  version?: string;
  scene?: string;
  action?: 'buy' | 'hold' | 'reduce' | 'sell' | 'watch' | string;
  confidence?: number;
  summary?: string;
  reasons?: string[];
  executionPlan?: string[] | { position?: string; buy_zone?: string; stop_loss?: string; take_profit?: string[] };
  execution_plan?: { position?: string; buy_zone?: string; stop_loss?: string; take_profit?: string[] };
  risks?: string[];
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

export default function DecisionCard({ data }: { data: CardData }) {
  const a = ACTION_STYLE[data.action ?? ''] ?? ACTION_STYLE.watch;
  const pct = data.confidence != null ? `${(data.confidence * 100).toFixed(0)}%` : '-';
  const executionPlan = data.executionPlan ?? data.execution_plan;
  const executionPlanDetails = executionPlan && !Array.isArray(executionPlan) ? executionPlan : null;
  const provenance = data.dataProvenance ?? data.data_provenance;
  const complianceNotice = data.complianceNotice ?? data.compliance_notice;

  return (
    <div className="glass rounded-xl p-4 mt-3">
      <div className="flex gap-2.5 items-center mb-2.5">
        <span className={`${a.bg} ${a.text} px-3 py-1 rounded-md font-bold`}>{a.label}</span>
        <span className="text-text-muted">置信度 {pct}</span>
      </div>
      {data.summary ? <p className="my-2 font-medium">{data.summary}</p> : null}
      {data.reasons?.length ? (
        <div className="my-2">
          <b>理由：</b>
          <ul className="my-1 pl-5">{data.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ) : null}
      {Array.isArray(executionPlan) && executionPlan.length > 0 ? (
        <div className="my-2 p-2.5 glass rounded-lg">
          <b>执行计划</b>
          <ul className="my-1 pl-5 text-sm text-text-secondary">{executionPlan.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      ) : executionPlanDetails ? (
        <div className="my-2 p-2.5 glass rounded-lg">
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
          <div className="mt-1 glass rounded-lg p-2 space-y-1">
            {provenance.map((item, i) => {
              if (typeof item === 'string') return <div key={i}>{item}</div>;
              return <div key={i}>{item.source} / {item.dataset} — {item.timestamp}</div>;
            })}
          </div>
        </details>
      ) : null}

      {complianceNotice ? (
        <div className="mt-2 text-xs glass rounded-lg p-2 text-text-muted">{complianceNotice}</div>
      ) : null}
    </div>
  );
}
