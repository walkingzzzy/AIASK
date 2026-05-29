import { ArrowUpDown, RefreshCw, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { FinancialManagerQueryResult } from "../../types";

type Tab = "north" | "sector" | "concept" | "stock";

export function FundFlowWorkspace({ endpoint, apiToken, controlToken }: { endpoint: string; apiToken: string; controlToken: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [tab, setTab] = useState<Tab>("north");
  const [code, setCode] = useState("600519");
  const [result, setResult] = useState<FinancialManagerQueryResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function load(selectedTab?: Tab) {
    const t = selectedTab || tab;
    setBusy(true);
    try {
      const params = t === "stock" ? { code: code.trim() } : {};
      const payload = await api.financialManagerQuery({ capability_id: "fund-flow", action_id: t, params });
      setResult(payload);
      setMessage(payload.success ? `FUND_FLOW_${t.toUpperCase()}_OK` : payload.error || "FUND_FLOW_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { if (endpoint && apiToken) load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [endpoint, apiToken]);

  function switchTab(t: Tab) { setTab(t); load(t); }

  const data = result?.data && typeof result.data === "object" ? (result.data as Record<string, unknown>) : {};
  const items = Array.isArray(data.data) ? data.data : Array.isArray(data.items) ? data.items : [];

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div><span>资金流向</span><h1>北向 / 行业 / 概念 / 个股资金流</h1></div>
        <div className="button-row">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={() => load()} type="button"><RefreshCw size={14} /> 刷新</button>
        </div>
      </header>
      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="diagnostics-summary wide">
            <button className={`small-button ${tab === "north" ? "active" : ""}`} onClick={() => switchTab("north")} type="button">北向资金</button>
            <button className={`small-button ${tab === "sector" ? "active" : ""}`} onClick={() => switchTab("sector")} type="button">行业</button>
            <button className={`small-button ${tab === "concept" ? "active" : ""}`} onClick={() => switchTab("concept")} type="button">概念</button>
            <button className={`small-button ${tab === "stock" ? "active" : ""}`} onClick={() => switchTab("stock")} type="button">个股</button>
          </div>

          {tab === "stock" && (
            <div className="quant-form-grid">
              <label className="field-row"><span>股票代码</span><input value={code} onChange={(e) => setCode(e.target.value)} /></label>
              <button className="small-button" disabled={busy} onClick={() => load("stock")} type="button"><ArrowUpDown size={14} /> 查询</button>
            </div>
          )}

          <section className="capability-section">
            <div className="section-header"><div><span>{items.length} 条数据</span><h3>{tab === "north" ? "北向资金净流入" : tab === "sector" ? "行业资金流 Top20" : tab === "concept" ? "概念资金流 Top20" : "个股主力资金流"}</h3></div><TrendingUp size={18} /></div>
            {items.length > 0 ? (
              <div className="mini-list">
                {items.slice(0, 30).map((item: unknown, i: number) => {
                  const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
                  const label = String(row.name || row.date || row.sector || `#${i + 1}`);
                  const value = String(row.net_inflow ?? row.net_amount ?? row.change_pct ?? row.value ?? "");
                  return (
                    <article key={i} className="capability-row">
                      <div><strong>{label}</strong><span>{value}</span></div>
                    </article>
                  );
                })}
              </div>
            ) : <p className="muted">暂无数据，请刷新或检查 Agent 连接。</p>}
            <details className="raw-details"><summary>原始数据</summary><JsonPanel value={result} /></details>
          </section>
        </div>
      </div>
    </section>
  );
}
