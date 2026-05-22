import { Activity, BarChart3, Database, FileText, FlaskConical, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { QuantPresetPayload, QuantResearchRun } from "../../types";

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function firstTemplate(presets: QuantPresetPayload | null) {
  return presets?.templates?.[0] || {
    universe: ["600519", "000001", "000858"],
    factors: ["momentum", "volatility", "value"],
    benchmark: "000300",
    rebalance_frequency: "monthly",
    cost_bps: 3,
    slippage_bps: 1,
    risk_limits: { max_weight: 0.35 }
  };
}

function StageList({ run }: { run: QuantResearchRun | null }) {
  const stages = run?.report?.stages || run?.payload?.stages || [];
  return (
    <div className="quant-stage-list">
      {stages.map((stage) => (
        <article key={stage.name}>
          <div>
            <strong>{stage.name.replace(/_/g, " ")}</strong>
            <span>{stage.error || compact(stage.output).slice(0, 140)}</span>
          </div>
          <StatusBadge status={stage.status} />
        </article>
      ))}
      {!stages.length && <p className="muted">Run a research workflow to populate stage evidence.</p>}
    </div>
  );
}

function unknownRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function firstMetric(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== "") return compact(value);
  }
  return "-";
}

function ResearchConfidencePanel({ run }: { run: QuantResearchRun | null }) {
  const report = run?.report;
  const backtest = unknownRecord(report?.backtest);
  const strategyFactory = unknownRecord(report?.strategy_factory);
  const limitations = report?.limitations || [];
  const failedStage = report?.summary?.failed_stage;
  const overfitRisk =
    limitations.some((item) => String(item).toLowerCase().includes("overfit")) || failedStage
      ? "review"
      : report
        ? "monitor"
        : "not_loaded";
  return (
    <div className="capability-section">
      <div className="section-header">
        <div>
          <span>Trust layer</span>
          <h3>Validation and overfit risk</h3>
        </div>
        <ShieldCheck size={18} />
      </div>
      <div className="diagnostics-summary wide">
        <MetricCard label="OOS" value={firstMetric(backtest, ["oos_return", "out_sample_return", "oos_sharpe"])} status={report ? "partial" : "not_loaded"} />
        <MetricCard label="Walk-forward" value={firstMetric(backtest, ["walk_forward_score", "walk_forward_sharpe", "avg_out_pf"])} status={report ? "partial" : "not_loaded"} />
        <MetricCard label="Overfit risk" value={overfitRisk} status={overfitRisk === "review" ? "failed" : overfitRisk === "monitor" ? "partial" : "not_loaded"} />
        <MetricCard label="Factory gate" value={firstMetric(strategyFactory, ["status", "recommendation", "decision"])} status={strategyFactory.status ? String(strategyFactory.status) : "not_loaded"} />
      </div>
      <p className="muted">
        Promotion decisions should consider OOS stability, parameter sensitivity, sample coverage, and strategy-factory review before incubation.
      </p>
    </div>
  );
}

function FactorHealthPanel({ selectedFactors, library }: { selectedFactors: string[]; library: string[] }) {
  const librarySet = new Set(library);
  const rows = selectedFactors.map((factor) => ({
    name: factor,
    status: librarySet.has(factor) ? "implemented" : "partial",
    detail: librarySet.has(factor) ? "Known factor library member" : "Custom factor, needs stronger evidence"
  }));
  return (
    <div className="capability-section">
      <div className="section-header">
        <div>
          <span>Factor discovery</span>
          <h3>Health and evidence coverage</h3>
        </div>
        <Activity size={18} />
      </div>
      <div className="mini-list">
        {rows.map((row) => (
          <article className={`capability-row ${row.status === "implemented" ? "ok" : "warn"}`} key={row.name}>
            <div>
              <span>{row.detail}</span>
              <strong>{row.name}</strong>
            </div>
            <StatusBadge status={row.status} label={row.status === "implemented" ? "known" : "observe"} />
            <small>Next checks: IC stability, decay, redundancy, and economic rationale.</small>
          </article>
        ))}
        {!rows.length && <p className="muted">Add factors to see health coverage.</p>}
      </div>
    </div>
  );
}

function ReportPanel({ run }: { run: QuantResearchRun | null }) {
  const report = run?.report;
  return (
    <section className="quant-report-panel">
      <div className="section-header">
        <div>
          <span>{run?.research_id || "research artifact"}</span>
          <h3>Report</h3>
        </div>
        <StatusBadge status={report?.status || run?.status || "not_loaded"} />
      </div>
      {report ? (
        <>
          <div className="kv-grid">
            <span>Benchmark</span>
            <strong>{report.summary?.benchmark || "-"}</strong>
            <span>Universe</span>
            <strong>{report.summary?.universe_size ?? report.universe?.length ?? "-"}</strong>
            <span>Factors</span>
            <strong>{report.summary?.factor_count ?? "-"}</strong>
            <span>Failed stage</span>
            <strong>{report.summary?.failed_stage || "-"}</strong>
          </div>
          <div className="notice warn">
            <ShieldCheck size={14} />
            {report.disclaimer || "NOT_INVESTMENT_ADVICE"}
          </div>
          <details className="raw-details" open>
            <summary>Structured report</summary>
            <JsonPanel value={report} />
          </details>
        </>
      ) : (
        <div className="empty-mini">
          <FileText size={24} />
          <span>No research report loaded.</span>
        </div>
      )}
    </section>
  );
}

export function QuantResearchWorkspace({
  endpoint,
  apiToken,
  userId
}: {
  endpoint: string;
  apiToken: string;
  userId?: string;
}) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken }), [apiToken, endpoint]);
  const [presets, setPresets] = useState<QuantPresetPayload | null>(null);
  const [run, setRun] = useState<QuantResearchRun | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);
  const template = firstTemplate(presets);
  const [universe, setUniverse] = useState(template.universe.join(", "));
  const [factors, setFactors] = useState(template.factors.join(", "));
  const [benchmark, setBenchmark] = useState(template.benchmark);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rebalanceFrequency, setRebalanceFrequency] = useState(template.rebalance_frequency);
  const [costBps, setCostBps] = useState(String(template.cost_bps));
  const [slippageBps, setSlippageBps] = useState(String(template.slippage_bps));

  async function refreshPresets() {
    setBusy(true);
    try {
      const payload = await client.quantPresets();
      const shouldHydrateForm = presets === null;
      setPresets(payload);
      const nextTemplate = firstTemplate(payload);
      if (shouldHydrateForm) {
        setUniverse(nextTemplate.universe.join(", "));
        setFactors(nextTemplate.factors.join(", "));
        setBenchmark(nextTemplate.benchmark);
        setRebalanceFrequency(nextTemplate.rebalance_frequency);
        setCostBps(String(nextTemplate.cost_bps));
        setSlippageBps(String(nextTemplate.slippage_bps));
      }
      setMessage("PRESETS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshPresets().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const envelope = await client.quantResearchRun({
        universe: splitList(universe),
        factors: splitList(factors),
        benchmark,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        rebalance_frequency: rebalanceFrequency,
        cost_bps: Number(costBps || 0),
        slippage_bps: Number(slippageBps || 0),
        include_strategy_review: true,
        user_id: userId || undefined
      });
      const research = envelope.data?.research || null;
      setRun(research);
      setMessage(envelope.success ? "RESEARCH_RUN_CREATED" : envelope.error || "RESEARCH_RUN_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  const dataStatus = presets?.data_status?.status || "not_loaded";
  const database = presets?.data_status?.database;

  return (
    <section className="quant-workspace">
      <header className="quant-header">
        <div>
          <span>Quant Research</span>
          <h1>Data, factors, backtests, portfolio risk</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={dataStatus} label={dataStatus} />
          <button className="small-button" disabled={busy} onClick={refreshPresets} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="quant-body">
        <form className="quant-params-panel" onSubmit={submit}>
          <div className="section-header">
            <div>
              <span>Research setup</span>
              <h3>Experiment card</h3>
            </div>
            <FlaskConical size={18} />
          </div>

          <label className="field-row">
            <span>Universe</span>
            <textarea value={universe} onChange={(event) => setUniverse(event.target.value)} />
          </label>
          <label className="field-row">
            <span>Factors</span>
            <input value={factors} onChange={(event) => setFactors(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>Benchmark</span>
              <input value={benchmark} onChange={(event) => setBenchmark(event.target.value)} />
            </label>
            <label className="field-row">
              <span>Rebalance</span>
              <select value={rebalanceFrequency} onChange={(event) => setRebalanceFrequency(event.target.value)}>
                <option value="weekly">weekly</option>
                <option value="monthly">monthly</option>
                <option value="quarterly">quarterly</option>
              </select>
            </label>
            <label className="field-row">
              <span>Start date</span>
              <input value={startDate} onChange={(event) => setStartDate(event.target.value)} placeholder="YYYY-MM-DD" />
            </label>
            <label className="field-row">
              <span>End date</span>
              <input value={endDate} onChange={(event) => setEndDate(event.target.value)} placeholder="YYYY-MM-DD" />
            </label>
            <label className="field-row">
              <span>Cost bps</span>
              <input value={costBps} onChange={(event) => setCostBps(event.target.value)} />
            </label>
            <label className="field-row">
              <span>Slippage bps</span>
              <input value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} />
            </label>
          </div>
          <button className="primary-button" disabled={busy || !splitList(universe).length || !splitList(factors).length} type="submit">
            <Play size={15} />
            Run research
          </button>
        </form>

        <section className="quant-center-panel">
          <div className="diagnostics-summary wide">
            <MetricCard label="Data" value={dataStatus} status={dataStatus} />
            <MetricCard label="Universe" value={splitList(universe).length} status="implemented" />
            <MetricCard label="Factors" value={splitList(factors).length} status="implemented" />
            <MetricCard label="Run" value={run?.status || "not_loaded"} status={run?.status || "not_loaded"} />
          </div>

          {database && (!database.configured || database.writable === false) && (
            <div className="notice warn">
              <Database size={15} />
              {database.setup_hint || "Configure a writable SQLite database path to enable full quant research."}
            </div>
          )}

          <ResearchConfidencePanel run={run} />
          <FactorHealthPanel selectedFactors={splitList(factors)} library={presets?.factor_library || []} />

          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>{message}</span>
                <h3>Pipeline stages</h3>
              </div>
              <Activity size={18} />
            </div>
            <StageList run={run} />
          </div>

          <div className="capability-grid two">
            <div className="capability-card">
              <div className="card-head">
                <div>
                  <span>Backtest</span>
                  <h3>Assumptions</h3>
                </div>
                <BarChart3 size={18} />
              </div>
              <JsonPanel value={run?.report?.backtest_assumptions || { cost_bps: costBps, slippage_bps: slippageBps, benchmark }} />
            </div>
            <div className="capability-card">
              <div className="card-head">
                <div>
                  <span>Strategy factory</span>
                  <h3>Read-only review</h3>
                </div>
                <StatusBadge status={run?.report?.strategy_factory ? "implemented" : "not_loaded"} />
              </div>
              <JsonPanel value={run?.report?.strategy_factory || { status: "not_loaded" }} />
            </div>
          </div>
        </section>

        <ReportPanel run={run} />
      </div>
    </section>
  );
}
