import { Crosshair, Map, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { FinancialManagerQueryResult } from "../../types";

export function TradePlanWorkspace({ endpoint, apiToken, controlToken }: { endpoint: string; apiToken: string; controlToken: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [code, setCode] = useState("600519");
  const [entryPrice, setEntryPrice] = useState("1800");
  const [capital, setCapital] = useState("1000000");
  const [style, setStyle] = useState("balanced");
  const [planResult, setPlanResult] = useState<FinancialManagerQueryResult | null>(null);
  const [stopResult, setStopResult] = useState<FinancialManagerQueryResult | null>(null);
  const [levelsResult, setLevelsResult] = useState<FinancialManagerQueryResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function runAll(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const [plan, stop, levels] = await Promise.all([
        api.financialManagerQuery({ capability_id: "trade-plan", action_id: "generate", params: { code: code.trim(), capital: Number(capital), style } }),
        api.financialManagerQuery({ capability_id: "trade-plan", action_id: "stop_levels", params: { code: code.trim(), entry_price: Number(entryPrice) } }),
        api.financialManagerQuery({ capability_id: "trade-plan", action_id: "key_levels", params: { code: code.trim() } }),
      ]);
      setPlanResult(plan);
      setStopResult(stop);
      setLevelsResult(levels);
      setMessage(plan.success ? "TRADE_PLAN_OK" : plan.error || "TRADE_PLAN_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  const planData = planResult?.data && typeof planResult.data === "object" ? (planResult.data as Record<string, unknown>) : {};
  const stopData = stopResult?.data && typeof stopResult.data === "object" ? (stopResult.data as Record<string, unknown>) : {};

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>交易计划</span>
          <h1>入场方案与风险管理</h1>
          <p>综合关键价位、ATR 止损止盈和场景化交易方案，一键生成完整交易计划。</p>
        </div>
        <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
      </header>
      <div className="capabilities-body">
        <div className="capability-stack">
          <form className="capability-section" onSubmit={runAll}>
            <div className="section-header">
              <div><span>参数</span><h3>生成交易计划</h3></div>
              <Map size={18} />
            </div>
            <div className="quant-form-grid">
              <label className="field-row"><span>股票代码</span><input value={code} onChange={(e) => setCode(e.target.value)} /></label>
              <label className="field-row"><span>入场价</span><input value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} /></label>
              <label className="field-row"><span>资金量</span><input value={capital} onChange={(e) => setCapital(e.target.value)} /></label>
              <label className="field-row"><span>风格</span>
                <select value={style} onChange={(e) => setStyle(e.target.value)}>
                  <option value="conservative">保守</option>
                  <option value="balanced">均衡</option>
                  <option value="aggressive">激进</option>
                </select>
              </label>
            </div>
            <button className="primary-button" disabled={busy || !code.trim()} type="submit"><Crosshair size={15} /> 生成完整计划</button>
          </form>

          {(planResult || stopResult || levelsResult) && (
            <div className="capability-grid two">
              <section className="capability-section">
                <div className="section-header"><div><span>止损止盈</span><h3>ATR + 结构止损</h3></div><ShieldCheck size={18} /></div>
                <div className="diagnostics-summary wide">
                  <MetricCard label="ATR 止损" value={String((stopData as Record<string,unknown>).atr_stop_loss || "-")} status="partial" />
                  <MetricCard label="结构止损" value={String((stopData as Record<string,unknown>).structural_stop || "-")} status="partial" />
                </div>
                <details className="raw-details"><summary>详细数据</summary><JsonPanel value={stopResult} /></details>
              </section>
              <section className="capability-section">
                <div className="section-header"><div><span>关键价位</span><h3>支撑与阻力</h3></div><RefreshCw size={18} /></div>
                <details className="raw-details" open><summary>详细数据</summary><JsonPanel value={levelsResult} /></details>
              </section>
            </div>
          )}

          {planResult && (
            <section className="capability-section">
              <div className="section-header"><div><span>完整计划</span><h3>{String(planData.direction || "待定")} — 置信度 {String(planData.confidence || "-")}</h3></div></div>
              <details className="raw-details" open><summary>交易计划原始数据</summary><JsonPanel value={planResult} /></details>
            </section>
          )}
        </div>
      </div>
    </section>
  );
}
