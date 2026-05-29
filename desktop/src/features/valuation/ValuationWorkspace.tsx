import { BarChart3, RefreshCw, TrendingUp } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { FinancialManagerQueryResult } from "../../types";

function safeNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmt(v: unknown, decimals = 2): string {
  const n = safeNum(v);
  return n === null ? "-" : n.toFixed(decimals);
}

function pct(v: unknown): string {
  const n = safeNum(v);
  return n === null ? "-" : `${(n * 100).toFixed(1)}%`;
}

interface ConsensusRow {
  method: string;
  per_share: number | null;
  error?: string;
}

function extractConsensus(data: unknown): { rows: ConsensusRow[]; stats: Record<string, unknown> } {
  const d = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const estimates = Array.isArray(d.estimates) ? d.estimates : [];
  const rows: ConsensusRow[] = estimates.map((e: unknown) => {
    const item = e && typeof e === "object" ? (e as Record<string, unknown>) : {};
    return { method: String(item.method || ""), per_share: safeNum(item.per_share), error: item.error ? String(item.error) : undefined };
  });
  const stats = d.statistics && typeof d.statistics === "object" ? (d.statistics as Record<string, unknown>) : {};
  return { rows, stats };
}

export function ValuationWorkspace({ endpoint, apiToken, controlToken }: { endpoint: string; apiToken: string; controlToken: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [code, setCode] = useState("600519");
  const [result, setResult] = useState<FinancialManagerQueryResult | null>(null);
  const [consensusResult, setConsensusResult] = useState<FinancialManagerQueryResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function runConsensus(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await api.financialManagerQuery({ capability_id: "valuation", action_id: "consensus", params: { code: code.trim() } });
      setConsensusResult(payload);
      setMessage(payload.success ? "VALUATION_CONSENSUS_OK" : payload.error || "VALUATION_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function runSingle(actionId: string, extraParams: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      const payload = await api.financialManagerQuery({ capability_id: "valuation", action_id: actionId, params: { code: code.trim(), ...extraParams } });
      setResult(payload);
      setMessage(payload.success ? `VALUATION_${actionId.toUpperCase()}_OK` : payload.error || "VALUATION_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  const consensus = consensusResult?.data ? extractConsensus(consensusResult.data) : null;

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>估值分析</span>
          <h1>多路径估值与共识</h1>
          <p>DCF / DDM / 相对估值 / 情景 DCF / 历史估值 — 5 路径共识估值一键生成。</p>
        </div>
        <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <form className="capability-section" onSubmit={runConsensus}>
            <div className="section-header">
              <div><span>输入</span><h3>估值共识（一键跑 5 路径）</h3></div>
              <TrendingUp size={18} />
            </div>
            <div className="quant-form-grid">
              <label className="field-row">
                <span>股票代码</span>
                <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="600519" />
              </label>
            </div>
            <div className="button-row">
              <button className="primary-button" disabled={busy || !code.trim()} type="submit">
                <BarChart3 size={15} /> 运行估值共识
              </button>
              <button className="small-button" type="button" disabled={busy} onClick={() => runSingle("dcf")}>DCF</button>
              <button className="small-button" type="button" disabled={busy} onClick={() => runSingle("ddm")}>DDM</button>
              <button className="small-button" type="button" disabled={busy} onClick={() => runSingle("relative")}>相对</button>
              <button className="small-button" type="button" disabled={busy} onClick={() => runSingle("scenario_dcf", { industry: "消费" })}>情景</button>
              <button className="small-button" type="button" disabled={busy} onClick={() => runSingle("historical", { days: 90 })}>历史</button>
            </div>
          </form>

          {consensus && (
            <section className="capability-section">
              <div className="section-header">
                <div><span>共识结果</span><h3>5 路径估值汇总</h3></div>
                <StatusBadge status={consensusResult?.success ? "implemented" : "failed"} />
              </div>
              <div className="diagnostics-summary wide">
                <MetricCard label="中位数" value={fmt(consensus.stats.median)} status="ready" />
                <MetricCard label="均值" value={fmt(consensus.stats.mean)} status="ready" />
                <MetricCard label="最低" value={fmt(consensus.stats.min)} status="partial" />
                <MetricCard label="最高" value={fmt(consensus.stats.max)} status="partial" />
              </div>
              <div className="mini-list">
                {consensus.rows.map((row, i) => (
                  <article key={i} className={`capability-row ${row.error ? "bad" : "ok"}`}>
                    <div>
                      <strong>{row.method}</strong>
                      <span>{row.error || `每股 ${fmt(row.per_share)} 元`}</span>
                    </div>
                    <StatusBadge status={row.error ? "failed" : "implemented"} label={row.error ? "失败" : "成功"} />
                  </article>
                ))}
              </div>
              <details className="raw-details"><summary>原始数据</summary><JsonPanel value={consensusResult} /></details>
            </section>
          )}

          {result && (
            <section className="capability-section">
              <div className="section-header">
                <div><span>单路径结果</span><h3>{message}</h3></div>
                <RefreshCw size={18} />
              </div>
              <JsonPanel value={result} />
            </section>
          )}
        </div>
      </div>
    </section>
  );
}
