'use client';

type CardData = {
  version?: string;
  scene?: string;
  action?: 'buy' | 'hold' | 'reduce' | 'watch' | string;
  confidence?: number;
  summary?: string;
  reasons?: string[];
  execution_plan?: { position?: string; buy_zone?: string; stop_loss?: string; take_profit?: string[] };
  risks?: string[];
  data_provenance?: Array<{ source?: string; dataset?: string; timestamp?: string }>;
  timeliness?: Record<string, string>;
  compliance_notice?: string;
};

const ACTION_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  buy: { bg: 'bg-green-100', text: 'text-green-800', label: '买入' },
  hold: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '持有' },
  reduce: { bg: 'bg-red-100', text: 'text-red-800', label: '减仓' },
  watch: { bg: 'bg-gray-100', text: 'text-gray-700', label: '观望' },
};

export default function DecisionCard({ data }: { data: CardData }) {
  const a = ACTION_STYLE[data.action ?? ''] ?? ACTION_STYLE.watch;
  const pct = data.confidence != null ? `${(data.confidence * 100).toFixed(0)}%` : '-';

  return (
    <div className="border border-gray-300 rounded-[10px] p-4 mt-3">
      <div className="flex gap-2.5 items-center mb-2.5">
        <span className={`${a.bg} ${a.text} px-3 py-1 rounded-md font-bold`}>{a.label}</span>
        <span className="text-gray-500">置信度 {pct}</span>
      </div>
      {data.summary ? <p className="my-2 font-medium">{data.summary}</p> : null}
      {data.reasons?.length ? (
        <div className="my-2">
          <b>理由：</b>
          <ul className="my-1 pl-5">{data.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ) : null}
      {data.execution_plan ? (
        <div className="my-2 p-2.5 bg-gray-50 rounded-md">
          <b>执行计划</b>
          <div>仓位：{data.execution_plan.position ?? '-'}</div>
          {data.execution_plan.buy_zone ? <div>买入区间：{data.execution_plan.buy_zone}</div> : null}
          {data.execution_plan.stop_loss ? <div>止损：{data.execution_plan.stop_loss}</div> : null}
          {data.execution_plan.take_profit?.length ? <div>止盈：{data.execution_plan.take_profit.join(' / ')}</div> : null}
        </div>
      ) : null}
      {data.risks?.length ? (
        <div className="my-2">
          <b>风险提示：</b>
          <ul className="my-1 pl-5 text-red-700">{data.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ) : null}
      {data.data_provenance?.length ? (
        <details className="my-2 text-[13px] text-gray-500">
          <summary>数据来源</summary>
          {data.data_provenance.map((d, i) => <div key={i}>{d.source} / {d.dataset} ({d.timestamp})</div>)}
        </details>
      ) : null}
      <div className="mt-2.5 p-2 bg-gray-100 rounded text-xs text-gray-500">
        {data.compliance_notice || '本分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。'}
      </div>
    </div>
  );
}
