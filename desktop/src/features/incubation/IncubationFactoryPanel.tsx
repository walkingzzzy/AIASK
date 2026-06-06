import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  FlaskConical,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  XCircle
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { TradePredictionMatrix, TradePredictionMatrixRow, TradePredictionOutcomes, TradePredictionStatus } from "../../types";

interface IncubationRunnerStatus {
  run_time?: string;
  dry_run?: boolean;
  run_count?: number;
  error_count?: number;
  last_run_at?: string | null;
  last_result_status?: string | null;
  [key: string]: unknown;
}

interface IncubationReport {
  report_date?: string;
  generated_at?: string;
  summary?: {
    total_incubating?: number;
    total_with_signals?: number;
    auto_promoted?: number;
    stage_counts?: Record<string, number>;
  };
  hit_rate_dashboard?: {
    overall?: {
      total_signals?: number;
      hit_count?: number;
      hit_rate?: number;
      avg_skill_lcb?: number;
      avg_forward_sharpe?: number;
      strategy_count?: number;
    };
    by_family?: Record<string, Record<string, number>>;
    by_stage?: Record<string, Record<string, number>>;
    trend?: {
      available?: boolean;
      improvement?: number;
      direction?: "improving" | "declining" | "stable";
    };
  };
  feedback_actions?: {
    families_to_boost?: string[];
    families_to_cooldown?: string[];
    families_to_freeze?: string[];
  };
  [key: string]: unknown;
}

interface StageEvent {
  id: string;
  strategy_id?: string;
  strategy_name?: string;
  event_type: string;
  from_stage?: string;
  to_stage?: string;
  severity?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown, fallback = 0): number {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function percent(value: unknown): string {
  return `${Math.round(asNumber(value) * 100)}%`;
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function eventListFromData(data: unknown): StageEvent[] {
  const record = recordFromUnknown(data);
  const rawEvents = Array.isArray(record.events) ? record.events : [];
  return rawEvents.map((item, index) => {
    const event = recordFromUnknown(item);
    const payload = recordFromUnknown(event.payload);
    return {
      id: compact(event.id || event.event_id || `${event.event_type || "event"}:${index}`),
      strategy_id: compact(event.strategy_id || payload.strategy_id || event.aggregate_id),
      strategy_name: compact(payload.strategy_name || payload.name || event.strategy_id || event.aggregate_id),
      event_type: compact(event.event_type || "unknown"),
      from_stage: compact(payload.from_stage),
      to_stage: compact(payload.to_stage || payload.stage || event.status),
      severity: compact(event.severity || payload.severity || "info"),
      created_at: compact(event.created_at || event.timestamp || payload.created_at),
      payload
    };
  });
}

function latestReportFromEvents(events: StageEvent[]): IncubationReport | null {
  const reportEvent = events.find((event) => event.event_type === "incubation_factory.hit_rate_report_generated");
  const payload = recordFromUnknown(reportEvent?.payload);
  return payload.hit_rate_dashboard || payload.summary ? (payload as IncubationReport) : null;
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    warmup: "预热",
    observe: "观察",
    candidate: "候选",
    graduation_ready: "可毕业",
    promoted: "已晋级",
    paused: "已暂停",
    failed: "失败",
    retired: "已退役"
  };
  return labels[stage] || stage || "未知";
}

function stageTone(stage: string): string {
  if (["promoted", "graduation_ready"].includes(stage)) return "implemented";
  if (["failed", "retired"].includes(stage)) return "failed";
  if (["candidate", "observe", "warmup", "paused"].includes(stage)) return "partial";
  return "not_loaded";
}

function StageDistribution({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (!entries.length) {
    return (
      <div className="empty-mini">
        <FlaskConical size={22} />
        <span>暂无生命周期阶段统计。</span>
      </div>
    );
  }
  return (
    <div className="lifecycle-board">
      {entries.map(([stage, count]) => (
        <article className={`lifecycle-column ${stageTone(stage)}`} key={stage}>
          <span>{stageLabel(stage)}</span>
          <strong>{count}</strong>
          <small>占跟踪策略 {Math.round((count / Math.max(total, 1)) * 100)}%</small>
        </article>
      ))}
    </div>
  );
}

function FamilyHealth({ report }: { report: IncubationReport | null }) {
  const families = Object.entries(report?.hit_rate_dashboard?.by_family || {}).sort(
    ([, left], [, right]) => asNumber(right.avg_skill_lcb) - asNumber(left.avg_skill_lcb)
  );
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>因子与族群健康度</span>
          <h3>孵化器正在学习什么</h3>
        </div>
        <Activity size={18} />
      </div>
      <div className="mini-list">
        {families.slice(0, 8).map(([family, metrics]) => {
          const lcb = asNumber(metrics.avg_skill_lcb);
          const status = lcb > 0.02 ? "implemented" : lcb < -0.01 ? "failed" : "partial";
          return (
            <article className={`capability-row ${status === "implemented" ? "ok" : status === "failed" ? "bad" : "warn"}`} key={family}>
              <div>
                <span>命中率 {percent(metrics.hit_rate)} | n={compact(metrics.total_n)}</span>
                <strong>{family}</strong>
              </div>
              <StatusBadge status={status} label={`lcb ${lcb.toFixed(3)}`} />
              <small>前向 Sharpe {asNumber(metrics.avg_forward_sharpe).toFixed(2)} | 策略 {compact(metrics.strategy_count)}</small>
            </article>
          );
        })}
        {!families.length && <p className="muted">尚未生成族群级命中率报告。</p>}
      </div>
    </section>
  );
}

function StageTimeline({ events }: { events: StageEvent[] }) {
  const stageEvents = events.filter((event) => event.event_type.includes("incubation")).slice(0, 12);
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>最近生命周期事件</span>
          <h3>晋级、暂停与退役轨迹</h3>
        </div>
        <Clock size={18} />
      </div>
      <div className="mini-list">
        {stageEvents.map((event) => {
          const toStage = event.to_stage || "recorded";
          const Icon = ["promoted", "graduation_ready"].includes(toStage)
            ? CheckCircle2
            : ["failed", "retired"].includes(toStage)
              ? XCircle
              : ArrowUpRight;
          return (
            <article className={`capability-row ${stageTone(toStage) === "implemented" ? "ok" : stageTone(toStage) === "failed" ? "bad" : "warn"}`} key={event.id}>
              <div>
                <span>{formatTime(event.created_at)}</span>
                <strong>
                  <Icon size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
                  {event.strategy_name || event.strategy_id || event.event_type}
                </strong>
              </div>
              <StatusBadge status={stageTone(toStage)} label={stageLabel(toStage)} />
              <small>{event.from_stage && event.to_stage ? `${stageLabel(event.from_stage)} -> ${stageLabel(event.to_stage)}` : event.event_type}</small>
            </article>
          );
        })}
        {!stageEvents.length && <p className="muted">暂无孵化生命周期事件。</p>}
      </div>
    </section>
  );
}

function FeedbackActions({ report }: { report: IncubationReport | null }) {
  const actions = report?.feedback_actions || {};
  const boosts = actions.families_to_boost || [];
  const cooldown = actions.families_to_cooldown || [];
  const freeze = actions.families_to_freeze || [];
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>建议操作</span>
          <h3>工厂反馈</h3>
        </div>
        <ShieldCheck size={18} />
      </div>
      <div className="feedback-grid">
        <article>
          <TrendingUp size={16} />
          <strong>加强</strong>
          <span>{boosts.length ? boosts.join(", ") : "暂无加强建议"}</span>
        </article>
        <article>
          <TrendingDown size={16} />
          <strong>降温</strong>
          <span>{cooldown.length ? cooldown.join(", ") : "暂无降温建议"}</span>
        </article>
        <article>
          <XCircle size={16} />
          <strong>冻结</strong>
          <span>{freeze.length ? freeze.join(", ") : "暂无冻结建议"}</span>
        </article>
      </div>
    </section>
  );
}

function formatOptionalNumber(value: unknown, digits = 3): string {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue.toFixed(digits) : "-";
}

function countEntries(counts?: Record<string, number>): Array<[string, number]> {
  return Object.entries(counts || {}).sort(([, left], [, right]) => right - left);
}

function statusSummary(counts?: Record<string, number>): string {
  const entries = countEntries(counts);
  return entries.length ? entries.map(([key, value]) => `${key}:${value}`).join(" | ") : "-";
}

function predictionStatusTone(status?: string): string {
  if (!status) return "not_loaded";
  if (status === "ok" || status === "ready") return "implemented";
  if (status.includes("missing") || status.includes("partial") || status === "insufficient_samples") return "partial";
  if (status.includes("rejected") || status.includes("invalid")) return "failed";
  return status;
}

function matrixRowTone(row: TradePredictionMatrixRow): string {
  const quality = row.data_quality_status_counts || {};
  const scoreStatuses = row.score_status_counts || {};
  if (quality.invalid_ohlc || scoreStatuses.post_hoc_rejected) return "failed";
  if (quality.intraday_missing || quality.partial_gap || scoreStatuses.insufficient_samples || scoreStatuses.partial_intraday_missing) return "partial";
  return "implemented";
}

function TradePredictionObservability({
  status,
  outcomes,
  matrix
}: {
  status: TradePredictionStatus | null;
  outcomes: TradePredictionOutcomes | null;
  matrix: TradePredictionMatrix | null;
}) {
  const rows = matrix?.rows || [];
  const latestOutcomes = outcomes?.items || [];
  const insufficientCount = status?.score_status_counts?.insufficient_samples || 0;
  const dataGapCount =
    (status?.data_quality_status_counts?.intraday_missing || 0) +
    (status?.data_quality_status_counts?.partial_gap || 0) +
    (status?.data_quality_status_counts?.daily_bar_missing || 0) +
    (status?.data_quality_status_counts?.invalid_ohlc || 0);

  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Trade Prediction Observability</span>
          <h3>预测评分、样本和贡献矩阵</h3>
        </div>
        <StatusBadge status={status?.status || "not_loaded"} label={status?.status || "not_loaded"} />
      </div>

      <div className="diagnostics-summary wide">
        <MetricCard label="Predictions" value={status?.prediction_count ?? "-"} status={status?.status || "not_loaded"} />
        <MetricCard label="Pending" value={status?.pending_count ?? "-"} status={(status?.pending_count || 0) > 0 ? "partial" : "implemented"} />
        <MetricCard label="Evaluated" value={status?.evaluated_count ?? "-"} status={(status?.evaluated_count || 0) > 0 ? "implemented" : "not_loaded"} />
        <MetricCard label="Partial" value={status?.partial_count ?? "-"} status={(status?.partial_count || 0) > 0 ? "partial" : "implemented"} />
        <MetricCard label="Sample n" value={status?.sample_n ?? "-"} status={(status?.sample_n || 0) > 0 ? "implemented" : "partial"} />
        <MetricCard label="Avg score" value={formatOptionalNumber(status?.score_summary?.avg)} status="partial" />
      </div>

      {(insufficientCount > 0 || dataGapCount > 0) && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          样本不足 {insufficientCount}，数据缺口 {dataGapCount}。这些状态只用于诊断展示，不触发实盘交易动作。
        </div>
      )}

      <div className="capability-grid two">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Score Versions</span>
              <h3>版本、状态与数据质量</h3>
            </div>
            <Activity size={18} />
          </div>
          <div className="kv-grid">
            <span>score_version</span>
            <strong>{statusSummary(status?.score_version_counts)}</strong>
            <span>score_status</span>
            <strong>{statusSummary(status?.score_status_counts)}</strong>
            <span>data_quality</span>
            <strong>{statusSummary(status?.data_quality_status_counts)}</strong>
            <span>score_buckets</span>
            <strong>{statusSummary(status?.score_distribution)}</strong>
          </div>
        </article>

        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>{latestOutcomes.length} outcomes</span>
              <h3>最近预测结果</h3>
            </div>
            <Clock size={18} />
          </div>
          <div className="mini-list">
            {latestOutcomes.slice(0, 6).map((outcome, index) => {
              const outcomeJson = outcome.outcome_json || {};
              return (
                <article className="capability-row" key={outcome.outcome_id || outcome.prediction_id || index}>
                  <div>
                    <span>
                      {outcome.stock_code || "-"} | {outcome.actual_trading_date || "-"}
                    </span>
                    <strong>{outcome.strategy_id || outcome.prediction_id || "prediction"}</strong>
                  </div>
                  <StatusBadge status={predictionStatusTone(outcome.score_status)} label={outcome.score_status || "unknown"} />
                  <small>
                    {outcome.score_version || "-"} | score {formatOptionalNumber(outcome.trade_prediction_score)} | quality{" "}
                    {outcome.data_quality_status || "-"} | direction {compact(outcomeJson.direction_hit)} | target{" "}
                    {compact(outcomeJson.target_touch)}
                  </small>
                </article>
              );
            })}
            {!latestOutcomes.length && <p className="muted">暂无预测 outcome。</p>}
          </div>
        </article>
      </div>

      <section className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>{matrix?.row_count ?? rows.length} rows</span>
            <h3>family / regime / event / factor 矩阵</h3>
          </div>
          <StatusBadge status={rows.length ? "implemented" : "not_loaded"} label={matrix?.score_version || "all score versions"} />
        </div>
        <div className="mini-list">
          {rows.slice(0, 12).map((row) => (
            <article className={`capability-row ${matrixRowTone(row) === "implemented" ? "ok" : matrixRowTone(row) === "failed" ? "bad" : "warn"}`} key={`${row.dimension}:${row.value}`}>
              <div>
                <span>
                  {row.dimension} | n={row.sample_n ?? 0}
                </span>
                <strong>{row.value || "unknown"}</strong>
              </div>
              <StatusBadge status={matrixRowTone(row)} label={`LCB ${formatOptionalNumber(row.score_lcb_95)}`} />
              <small>
                score {formatOptionalNumber(row.score_avg)} | direction {percent(row.direction_hit_rate)} | target{" "}
                {percent(row.target_touch_rate)} | status {statusSummary(row.score_status_counts)}
              </small>
            </article>
          ))}
          {!rows.length && <p className="muted">暂无预测贡献矩阵。</p>}
        </div>
      </section>
    </section>
  );
}

export function IncubationFactoryPanel({ endpoint, apiToken, controlToken = "" }: { endpoint: string; apiToken: string; controlToken?: string }) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [status, setStatus] = useState<IncubationRunnerStatus | null>(null);
  const [report, setReport] = useState<IncubationReport | null>(null);
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [predictionStatus, setPredictionStatus] = useState<TradePredictionStatus | null>(null);
  const [predictionOutcomes, setPredictionOutcomes] = useState<TradePredictionOutcomes | null>(null);
  const [predictionMatrix, setPredictionMatrix] = useState<TradePredictionMatrix | null>(null);
  const [intentEnvelope, setIntentEnvelope] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusEnvelope, eventEnvelope, predictionStatusEnvelope, predictionOutcomesEnvelope, predictionMatrixEnvelope] = await Promise.all([
        client.incubationFactoryStatus(),
        client.strategyDomainEvents({ event_type: "incubation_factory.hit_rate_report_generated", limit: 5 }),
        client.tradePredictionStatus({ limit: 1000 }),
        client.tradePredictionOutcomes({ limit: 50 }),
        client.tradePredictionMatrix({ dimensions: ["family", "regime", "event", "factor"], limit: 1000 })
      ]);
      const runner = recordFromUnknown(statusEnvelope.data);
      setStatus(runner);
      setPredictionStatus(predictionStatusEnvelope.data);
      setPredictionOutcomes(predictionOutcomesEnvelope.data);
      setPredictionMatrix(predictionMatrixEnvelope.data);

      const reportFromStatus = recordFromUnknown(runner.report);
      const reportEvents = eventListFromData(eventEnvelope.data);
      const latestReport = reportFromStatus.hit_rate_dashboard ? (reportFromStatus as IncubationReport) : latestReportFromEvents(reportEvents);
      setReport(latestReport);

      const stageEnvelope = await client.strategyDomainEvents({ event_type: "incubation.stage_transitioned", limit: 40 });
      setEvents([...eventListFromData(stageEnvelope.data), ...reportEvents]);
      setMessage(statusEnvelope.success ? "INCUBATION_LOADED" : statusEnvelope.error || "INCUBATION_DEGRADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    fetchData().catch(() => undefined);
  }, [fetchData]);

  async function createIntent(action: "run_once" | "dry_run" | "maintenance") {
    setLoading(true);
    try {
      const envelope = await client.factoryIntentCreate(
        `incubation_factory.${action}`,
        { source: "desktop_incubation_factory" },
        `从 Desktop 创建 Incubation Factory ${action} 审批意图。`
      );
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? `INCUBATION_${action.toUpperCase()}_INTENT_CREATED` : envelope.error || "INCUBATION_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  const overall = report?.hit_rate_dashboard?.overall || {};
  const trend = report?.hit_rate_dashboard?.trend || {};
  const stageCounts = report?.summary?.stage_counts || {};
  const runnerStatus = status?.last_result_status || (status ? "idle" : "not_loaded");
  const runnerTone = runnerStatus === "completed" ? "implemented" : runnerStatus === "failed" ? "failed" : "partial";

  return (
    <div className="capability-stack">
      <section className="capability-banner">
        <div>
          <span>孵化中心</span>
          <h2>策略生命周期与命中率看板</h2>
          <p>
            这里把孵化工厂整理成操作视图：生命周期阶段、近期失败、命中率健康度和晋级证据会一起展示，方便在策略毕业前完成复核。
          </p>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : runnerTone} label={message} />
          <button className="small-button" disabled={loading} onClick={fetchData} type="button">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            刷新
          </button>
        </div>
      </section>

      <section className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>需审批操作</span>
            <h3>运行、试运行与维护意图</h3>
          </div>
          <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label={controlToken.trim() ? "控制令牌已就绪" : "需要控制令牌"} />
        </div>
        <div className="button-row">
          <button
            aria-label="创建运行意图"
            className="primary-button"
            disabled={loading || !controlToken.trim()}
            onClick={() => createIntent("run_once")}
            type="button"
          >
            创建运行意图
          </button>
          <button
            aria-label="创建试运行意图"
            className="small-button"
            disabled={loading || !controlToken.trim()}
            onClick={() => createIntent("dry_run")}
            type="button"
          >
            创建试运行意图
          </button>
          <button
            aria-label="创建维护意图"
            className="small-button"
            disabled={loading || !controlToken.trim()}
            onClick={() => createIntent("maintenance")}
            type="button"
          >
            创建维护意图
          </button>
        </div>
        {intentEnvelope ? <JsonPanel value={intentEnvelope} /> : null}
      </section>

      {message.startsWith("AIASK_") && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          {message}. Agent API 与策略存储可达后会自动加载孵化状态。
        </div>
      )}

      <div className="diagnostics-summary wide">
        <MetricCard label="运行器" value={runnerStatus} status={runnerTone} />
        <MetricCard label="运行次数" value={status?.run_count ?? "-"} status="implemented" />
        <MetricCard label="错误数" value={status?.error_count ?? "-"} status={(status?.error_count || 0) > 0 ? "failed" : "implemented"} />
        <MetricCard label="最近运行" value={formatTime(status?.last_run_at)} />
        <MetricCard label="命中率" value={overall.hit_rate === undefined ? "-" : percent(overall.hit_rate)} status={asNumber(overall.hit_rate) >= 0.5 ? "implemented" : "partial"} />
        <MetricCard label="Skill LCB" value={overall.avg_skill_lcb === undefined ? "-" : asNumber(overall.avg_skill_lcb).toFixed(4)} status={asNumber(overall.avg_skill_lcb) > 0 ? "implemented" : "partial"} />
        <MetricCard label="Forward Sharpe" value={overall.avg_forward_sharpe === undefined ? "-" : asNumber(overall.avg_forward_sharpe).toFixed(2)} />
        <MetricCard label="趋势" value={compact(trend.direction || "unknown")} status={trend.direction === "improving" ? "implemented" : trend.direction === "declining" ? "failed" : "partial"} />
      </div>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>策略生命周期看板</span>
            <h3>策略在孵化漏斗中的位置</h3>
          </div>
          <FlaskConical size={18} />
        </div>
        <StageDistribution counts={stageCounts} />
      </section>

      <div className="capability-grid two">
        <FamilyHealth report={report} />
        <FeedbackActions report={report} />
      </div>

      <StageTimeline events={events} />

      <TradePredictionObservability status={predictionStatus} outcomes={predictionOutcomes} matrix={predictionMatrix} />

      <details className="raw-details">
        <summary>原始孵化数据</summary>
        <JsonPanel value={{ status, report, events, predictionStatus, predictionOutcomes, predictionMatrix }} />
      </details>
    </div>
  );
}
