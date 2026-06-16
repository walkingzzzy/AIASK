import { Activity, BarChart3, Database, FileText, FlaskConical, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { GatedState, MetricCard, PriceDelta, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { QuantPresetPayload, QuantResearchReport, QuantResearchRun } from "../../types";

type QuantStage = NonNullable<QuantResearchReport["stages"]>[number];

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

function stageLabel(name?: string): string {
  const labels: Record<string, string> = {
    backtest_suite: "回测套件",
    data_gate: "数据闸门",
    definition: "研究定义",
    factor_validation: "因子验证",
    portfolio_risk: "组合风险",
    strategy_factory_review: "策略工厂评审"
  };
  return labels[name || ""] || (name || "unknown").replace(/_/g, " ");
}

function stageExplanation(stage: QuantStage): string {
  const explanations: Record<string, string> = {
    backtest_suite: "检验成本、滑点和调仓假设下的收益、回撤与样本外稳定性。",
    data_gate: "确认本地行情库、证券覆盖和新鲜度是否足够支撑完整研究。",
    definition: "固定股票池、因子、基准和风险约束，避免后续结果口径漂移。",
    factor_validation: "检查因子 IC、覆盖率、衰减和冗余，判断信号是否值得进入回测。",
    portfolio_risk: "评估集中度、VaR、压力场景和风险限制是否可接受。",
    strategy_factory_review: "以只读方式交给策略工厂复核晋级建议和生产化限制。"
  };
  return explanations[stage.name] || "Agent 返回了该阶段的结构化证据，可展开查看原始 payload。";
}

function stageBlockingReason(stage: QuantStage): string {
  const output = unknownRecord(stage.output);
  const reason = stage.error || output.blocking_reason || output.error_code || output.reason || output.status;
  return reason ? compact(reason) : "";
}

function stageNextAction(stage: QuantStage, report?: QuantResearchReport): string {
  const status = stage.status.toLowerCase();
  const reason = stageBlockingReason(stage);
  if (stage.name === "data_gate" && (status === "blocked" || reason.includes("LOCAL_DATABASE_REQUIRED"))) {
    return "配置可写 SQLite 数据库并完成行情同步，然后重新运行研究。";
  }
  if (stage.name === "data_gate" && status !== "completed" && status !== "passed") {
    return "先在 Data & Sync 页面复核缺失、过期证券，并生成同步审批。";
  }
  if (stage.name === "factor_validation" && (status === "blocked" || status === "failed")) {
    return "收窄因子集合，补充 IC/覆盖率证据，避免把弱信号推进回测。";
  }
  if (stage.name === "backtest_suite" && (status === "blocked" || status === "failed")) {
    return "检查样本窗口、成本滑点和基准设置，再比较样本内外稳定性。";
  }
  if (stage.name === "portfolio_risk" && (status === "blocked" || status === "failed")) {
    return "下调集中度或权重上限，重新评估 VaR 与压力测试。";
  }
  if (stage.name === "strategy_factory_review" && (status === "blocked" || status === "failed")) {
    return "保留研究产物为观察状态，等待策略工厂只读评审通过后再进入孵化。";
  }
  if (status === "completed" || status === "passed") {
    return report?.summary?.failed_stage
      ? "该阶段已通过，继续处理后续失败阶段。"
      : "证据已通过，可进入下一层复核，但仍不是交易指令。";
  }
  if (status === "running" || status === "in_progress") return "等待 Agent 完成该阶段并刷新报告。";
  return "展开原始证据，确认阻塞字段和后续操作。";
}

function stageStatusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["completed", "passed", "success", "ready"].includes(normalized)) return "ok";
  if (["blocked", "failed", "error", "missing"].includes(normalized)) return "bad";
  if (["partial", "running", "in_progress", "queued", "unconfigured"].includes(normalized)) return "warn";
  return "neutral";
}

function normalizeStages(run: QuantResearchRun | null): QuantStage[] {
  const reportStages = run?.report?.stages || [];
  const payloadStages = run?.payload?.stages || [];
  const stages = reportStages.length ? reportStages : payloadStages;
  return stages.filter((stage) => stage && stage.name);
}

function StageList({ run }: { run: QuantResearchRun | null }) {
  const stages = normalizeStages(run);
  return (
    <div className="quant-stage-list">
      {stages.map((stage) => (
        <article key={stage.name}>
          <div>
            <strong>{stageLabel(stage.name)}</strong>
            <span>{stage.error || compact(stage.output).slice(0, 140)}</span>
          </div>
          <StatusBadge status={stage.status} />
        </article>
      ))}
      {!stages.length && <p className="muted">运行研究工作流后会生成阶段证据。</p>}
    </div>
  );
}

function StageDecisionPanel({ run }: { run: QuantResearchRun | null }) {
  const stages = normalizeStages(run);
  const failedStage = run?.report?.summary?.failed_stage || "";
  const completedCount = stages.filter((stage) => ["completed", "passed", "success"].includes(stage.status.toLowerCase())).length;
  const blockedCount = stages.filter((stage) => ["blocked", "failed", "error"].includes(stage.status.toLowerCase())).length;
  return (
    <div className="capability-section quant-stage-decision">
      <div className="section-header">
        <div>
          <span>Agent 流水线决策</span>
          <h3>阶段结论与下一步</h3>
        </div>
        <Database size={18} />
      </div>
      {stages.length ? (
        <>
          <div className="quant-stage-summary">
            <MetricCard label="通过阶段" value={completedCount} status={completedCount ? "completed" : "not_loaded"} />
            <MetricCard label="阻塞阶段" value={blockedCount} status={blockedCount ? "blocked" : "completed"} />
            <MetricCard label="失败阶段" value={failedStage ? stageLabel(failedStage) : "-"} status={failedStage ? "blocked" : "completed"} />
          </div>
          <div className="quant-stage-decision-grid">
            {stages.map((stage) => {
              const blocker = stageBlockingReason(stage);
              return (
                <article className={`quant-stage-decision-card ${stageStatusClass(stage.status)}`} key={stage.name}>
                  <div className="quant-stage-card-head">
                    <div>
                      <span>{stage.name}</span>
                      <strong>{stageLabel(stage.name)}</strong>
                    </div>
                    <StatusBadge status={stage.status} />
                  </div>
                  <p>{stageExplanation(stage)}</p>
                  {blocker && (
                    <div className="quant-stage-blocker">
                      <span>阻塞原因</span>
                      <strong>{blocker}</strong>
                    </div>
                  )}
                  <div className="quant-stage-next">
                    <span>下一步</span>
                    <strong>{stageNextAction(stage, run?.report)}</strong>
                  </div>
                  <RawEvidencePanel title={`${stageLabel(stage.name)} 原始证据`} value={stage} />
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <p className="muted">运行研究或加载历史报告后，会在这里显示每个阶段的结论、阻塞原因和下一步。</p>
      )}
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

function firstNumeric(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (value === undefined || value === null || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
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
          <span>信任层</span>
          <h3>验证与过拟合风险</h3>
        </div>
        <ShieldCheck size={18} />
      </div>
      <div className="diagnostics-summary wide">
        {(() => {
          const oosReturn = firstNumeric(backtest, ["oos_return", "out_sample_return"]);
          if (oosReturn !== null) {
            return (
              <div className={`metric-card ${report ? "" : "neutral"}`}>
                <span>OOS</span>
                <strong>
                  <PriceDelta value={oosReturn} />
                </strong>
              </div>
            );
          }
          return (
            <MetricCard
              label="OOS"
              value={firstMetric(backtest, ["oos_return", "out_sample_return", "oos_sharpe"])}
              status={report ? "partial" : "not_loaded"}
            />
          );
        })()}
        <MetricCard label="Walk-forward" value={firstMetric(backtest, ["walk_forward_score", "walk_forward_sharpe", "avg_out_pf"])} status={report ? "partial" : "not_loaded"} />
        <MetricCard label="过拟合风险" value={overfitRisk} status={overfitRisk === "review" ? "failed" : overfitRisk === "monitor" ? "partial" : "not_loaded"} />
        <MetricCard label="工厂闸门" value={firstMetric(strategyFactory, ["status", "recommendation", "decision"])} status={strategyFactory.status ? String(strategyFactory.status) : "not_loaded"} />
      </div>
      <p className="muted">
        进入孵化前，晋级决策应同时参考 OOS 稳定性、参数敏感性、样本覆盖和策略工厂评审。
      </p>
    </div>
  );
}

function FactorHealthPanel({ selectedFactors, library }: { selectedFactors: string[]; library: string[] }) {
  const librarySet = new Set(library);
  const rows = selectedFactors.map((factor) => ({
    name: factor,
    status: librarySet.has(factor) ? "implemented" : "partial",
    detail: librarySet.has(factor) ? "已在因子库中登记" : "自定义因子，需要更强证据"
  }));
  return (
    <div className="capability-section">
      <div className="section-header">
        <div>
          <span>因子发现</span>
          <h3>健康度与证据覆盖</h3>
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
            <StatusBadge status={row.status} label={row.status === "implemented" ? "已知" : "观察"} />
            <small>下一步检查：IC 稳定性、衰减、冗余和经济解释。</small>
          </article>
        ))}
        {!rows.length && <p className="muted">添加因子后会显示健康覆盖。</p>}
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
          <span>{run?.research_id || "研究产物"}</span>
          <h3>报告</h3>
        </div>
        <StatusBadge status={report?.status || run?.status || "not_loaded"} />
      </div>
      {report ? (
        <>
          <div className="kv-grid">
            <span>基准</span>
            <strong>{report.summary?.benchmark || "-"}</strong>
            <span>股票池</span>
            <strong>{report.summary?.universe_size ?? report.universe?.length ?? "-"}</strong>
            <span>因子</span>
            <strong>{report.summary?.factor_count ?? "-"}</strong>
            <span>失败阶段</span>
            <strong>{report.summary?.failed_stage || "-"}</strong>
          </div>
          <div className="notice warn">
            <ShieldCheck size={14} />
            {report.disclaimer || "NOT_INVESTMENT_ADVICE"}
          </div>
          <RawEvidencePanel title="结构化报告" value={report} />
        </>
      ) : (
        <div className="empty-mini">
          <FileText size={24} />
          <span>尚未加载研究报告。</span>
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
  const [reportResearchId, setReportResearchId] = useState("");

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

  async function loadHistoricalReport() {
    const researchId = reportResearchId.trim();
    if (!researchId) return;
    setBusy(true);
    try {
      const [detail, report] = await Promise.all([
        client.quantResearchGet(researchId).catch(() => null),
        client.quantResearchReport(researchId)
      ]);
      const research = detail?.data?.research || detail?.research || null;
      setRun({
        ...research,
        research_id: report.research_id || researchId,
        status: report.status || research?.status || "loaded",
        payload: research?.payload || { stages: report.stages || [] },
        report
      });
      setMessage("RESEARCH_REPORT_LOADED");
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
          <span>量化研究</span>
          <h1>数据、因子、回测与组合风险</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={dataStatus} label={dataStatus} />
          <button className="small-button" disabled={busy} onClick={refreshPresets} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="quant-body">
        <form className="quant-params-panel" onSubmit={submit}>
          <div className="section-header">
            <div>
              <span>研究配置</span>
              <h3>实验卡片</h3>
            </div>
            <FlaskConical size={18} />
          </div>

          <label className="field-row">
            <span>股票池</span>
            <textarea value={universe} onChange={(event) => setUniverse(event.target.value)} />
          </label>
          <label className="field-row">
            <span>因子</span>
            <input value={factors} onChange={(event) => setFactors(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>基准</span>
              <input value={benchmark} onChange={(event) => setBenchmark(event.target.value)} />
            </label>
            <label className="field-row">
              <span>调仓频率</span>
              <select value={rebalanceFrequency} onChange={(event) => setRebalanceFrequency(event.target.value)}>
                <option value="weekly">每周</option>
                <option value="monthly">每月</option>
                <option value="quarterly">每季度</option>
              </select>
            </label>
            <label className="field-row">
              <span>开始日期</span>
              <input value={startDate} onChange={(event) => setStartDate(event.target.value)} placeholder="YYYY-MM-DD" />
            </label>
            <label className="field-row">
              <span>结束日期</span>
              <input value={endDate} onChange={(event) => setEndDate(event.target.value)} placeholder="YYYY-MM-DD" />
            </label>
            <label className="field-row">
              <span>成本 bps</span>
              <input value={costBps} onChange={(event) => setCostBps(event.target.value)} />
            </label>
            <label className="field-row">
              <span>滑点 bps</span>
              <input value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} />
            </label>
          </div>
          <button className="primary-button" disabled={busy || !splitList(universe).length || !splitList(factors).length} type="submit">
            <Play size={15} />
            运行研究
          </button>
          <div className="inline-form">
            <input
              value={reportResearchId}
              onChange={(event) => setReportResearchId(event.target.value)}
              placeholder="research_id"
            />
            <button disabled={busy || !reportResearchId.trim()} onClick={loadHistoricalReport} type="button">
              <FileText size={14} />
              加载报告
            </button>
          </div>
        </form>

        <section className="quant-center-panel">
          <div className="diagnostics-summary wide">
            <MetricCard label="数据" value={dataStatus} status={dataStatus} />
            <MetricCard label="股票池" value={splitList(universe).length} status="implemented" />
            <MetricCard label="因子" value={splitList(factors).length} status="implemented" />
            <MetricCard label="运行" value={run?.status || "not_loaded"} status={run?.status || "not_loaded"} />
          </div>

          {database && (!database.configured || database.writable === false) && (
            <GatedState
              reason={database.setup_hint || "请配置可写 SQLite 数据库路径，以启用完整量化研究。"}
              status="unconfigured"
              title="量化数据库未就绪"
            />
          )}

          <ResearchConfidencePanel run={run} />
          <FactorHealthPanel selectedFactors={splitList(factors)} library={presets?.factor_library || []} />
          <StageDecisionPanel run={run} />

          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>{message}</span>
                <h3>流水线阶段</h3>
              </div>
              <Activity size={18} />
            </div>
            <StageList run={run} />
          </div>

          <div className="capability-grid two">
            <div className="capability-card">
              <div className="card-head">
                <div>
                  <span>回测</span>
                  <h3>假设</h3>
                </div>
                <BarChart3 size={18} />
              </div>
              <RawEvidencePanel
                title="回测假设 JSON"
                value={run?.report?.backtest_assumptions || { cost_bps: costBps, slippage_bps: slippageBps, benchmark }}
              />
            </div>
            <div className="capability-card">
              <div className="card-head">
                <div>
                  <span>策略工厂</span>
                  <h3>只读评审</h3>
                </div>
                <StatusBadge status={run?.report?.strategy_factory ? "implemented" : "not_loaded"} />
              </div>
              <RawEvidencePanel title="策略工厂评审 JSON" value={run?.report?.strategy_factory || { status: "not_loaded" }} />
            </div>
          </div>
        </section>

        <ReportPanel run={run} />
      </div>
    </section>
  );
}
