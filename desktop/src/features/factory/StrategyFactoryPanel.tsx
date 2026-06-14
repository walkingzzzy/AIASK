import { useMemo, useState } from "react";
import { AlertTriangle, GitPullRequest, Play } from "lucide-react";
import { formatApiError } from "../../api";
import type { CapabilityWorkbenchPayload, ToolEnvelope } from "../../types";
import { JsonPanel, StatusBadge, compact, localizeBlockedReason, statusLabel } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function envelopeStatus(envelope: ToolEnvelope | null | undefined): string {
  if (!envelope) return "not_loaded";
  if (envelope.success) return "implemented";
  const data = asRecord(envelope.data);
  const errorCode = String(envelope.error_code || "");
  const error = String(envelope.error || "");
  if (errorCode.includes("CONTROL_TOKEN") || error.toLowerCase().includes("control token")) {
    return "gated";
  }
  const configured = data.database_configured || data.configured;
  if (data.status === "partial" || (configured && (errorCode.includes("TIMEOUT") || errorCode.includes("RECOVERY") || errorCode.includes("UNAVAILABLE")))) {
    return "partial";
  }
  if (errorCode.includes("MISSING") || errorCode.includes("TIMEOUT") || errorCode.includes("UNAVAILABLE")) {
    return "unconfigured";
  }
  return "failed";
}

function yesNo(value: unknown): string {
  if (value === true) return "是";
  if (value === false) return "否";
  return compact(value);
}

function databaseBackendLabel(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized === "sqlite") return "本地数据库";
  if (normalized === "postgres" || normalized === "postgresql") return "PostgreSQL 数据库";
  if (normalized === "mysql") return "MySQL 数据库";
  return value || "-";
}

function envelopeMessage(envelope: ToolEnvelope | null | undefined): string {
  if (!envelope) return "尚未加载策略工厂状态。";
  const errorCode = String(envelope.error_code || "");
  const error = String(envelope.error || "");
  if (errorCode.includes("CONTROL_TOKEN") || error.toLowerCase().includes("control token")) {
    return localizeBlockedReason("control token required") || "需要控制令牌后才能读取策略工厂详情。";
  }
  return String(asRecord(envelope.data).detail || envelope.error || envelope.error_code || "当前运行时的策略工厂尚未就绪。");
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberFromUnknown(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function percent(value: unknown): string {
  return `${Math.round(numberFromUnknown(value) * 100)}%`;
}

function blockerCodeLabel(code: string): string {
  const labels: Record<string, string> = {
    diagnostic_only_not_allowed_for_incubation: "Diagnostic-only runtime",
    default_profile_not_allowed_for_single_name_runtime: "Default runtime profile",
    "execution_readiness_tier:missing_executable_contract": "Missing executable contract",
    "execution_readiness_tier:observe_diagnostic_only": "Observe/diagnostic runtime",
    proxy_runtime_not_allowed_for_formal_incubation: "Proxy runtime evidence",
    runtime_family_semantic_mismatch: "Runtime family mismatch",
    strict_incubation_pass_required_for_formal_track: "Strict pass required"
  };
  return labels[code] || code.replace(/[_:]/g, " ");
}

function blockerSummaryFromStatus(data: Record<string, unknown>): Record<string, unknown> {
  const direct = asRecord(data.strict_incubation_blocker_summary);
  if (Object.keys(direct).length) return direct;
  const diagnostics = asRecord(data.recent_run_diagnostics);
  const qualityProgress = asRecord(diagnostics.quality_progress);
  const fallbackTop = asArray(diagnostics.blocker_reason_topn)
    .map((item) => {
      const record = asRecord(item);
      const reasonCode = String(record.reason_code || record.reason || "");
      return {
        reason_code: reasonCode,
        count: numberFromUnknown(record.count),
        label: blockerCodeLabel(reasonCode),
        next_action: "Inspect the latest strategy quality report and replay admission after the contract gap is repaired."
      };
    })
    .filter((item) => item.reason_code);
  return {
    status: fallbackTop.length ? "blocked" : "unknown",
    headline: fallbackTop.length ? "Recent runs expose recurring formal-admission blockers." : "",
    analyzed_run_count: diagnostics.analyzed_run_count,
    strict_ready_given_raw_b_rate: qualityProgress.recent_strict_ready_given_raw_b_rate_mean,
    raw_b_or_above_rate: qualityProgress.recent_raw_b_or_above_rate_mean,
    top_blockers: fallbackTop
  };
}

function StrictIncubationBlockers({ envelope }: { envelope: ToolEnvelope | null | undefined }) {
  const data = asRecord(envelope?.data);
  const summary = blockerSummaryFromStatus(data);
  const topBlockers = asArray(summary.top_blockers).map(asRecord).filter((item) => Object.keys(item).length);
  const samples = asArray(summary.sample_blocked_strategies).map(asRecord).filter((item) => Object.keys(item).length);
  const headline = String(summary.headline || "");
  const hasEvidence = headline || topBlockers.length || numberFromUnknown(summary.analyzed_run_count) > 0;

  if (!hasEvidence) return null;

  return (
    <section className="capability-section strict-blocker-panel" aria-label="strict incubation blocker summary">
      <div className="section-header">
        <div>
          <span>Formal admission</span>
          <h3>Strict-incubation blockers</h3>
        </div>
        <StatusBadge status={String(summary.status || "partial")} label={`${numberFromUnknown(summary.analyzed_run_count)} runs`} />
      </div>
      {headline && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          <strong>{headline}</strong>
          {summary.next_action ? <span>{String(summary.next_action)}</span> : null}
        </div>
      )}
      <div className="diagnostics-summary blocker-metrics">
        <div className="metric-card warn">
          <span>Raw B+ rate</span>
          <strong>{percent(summary.raw_b_or_above_rate)}</strong>
          <small>{numberFromUnknown(summary.raw_b_or_above_count)} candidates</small>
        </div>
        <div className="metric-card bad">
          <span>Strict ready of B+</span>
          <strong>{percent(summary.strict_ready_given_raw_b_rate)}</strong>
          <small>{numberFromUnknown(summary.strict_ready_given_raw_b_count)} admitted</small>
        </div>
        <div className="metric-card warn">
          <span>Observe lane</span>
          <strong>{numberFromUnknown(summary.observe_lane_count)}</strong>
          <small>{numberFromUnknown(summary.diagnostic_lane_count)} diagnostic</small>
        </div>
        <div className="metric-card bad">
          <span>Strict not ready</span>
          <strong>{numberFromUnknown(summary.strict_not_ready_count)}</strong>
          <small>{numberFromUnknown(summary.submitted_count)} submitted</small>
        </div>
      </div>
      {topBlockers.length > 0 && (
        <div className="blocker-list">
          {topBlockers.slice(0, 5).map((item) => {
            const reasonCode = String(item.reason_code || item.reason || "");
            return (
              <article className="blocker-row" key={reasonCode}>
                <div>
                  <strong>{String(item.label || blockerCodeLabel(reasonCode))}</strong>
                  <span>{reasonCode}</span>
                  {item.next_action ? <p>{String(item.next_action)}</p> : null}
                </div>
                <StatusBadge status="warn" label={`x${numberFromUnknown(item.count)}`} />
              </article>
            );
          })}
        </div>
      )}
      {samples.length > 0 && (
        <details className="raw-details">
          <summary>Blocked strategy samples</summary>
          <div className="mini-list blocker-samples">
            {samples.slice(0, 5).map((sample, index) => (
              <article key={String(sample.strategy_id || index)}>
                <strong>{compact(sample.strategy_id || `sample-${index + 1}`)}</strong>
                <span>{compact(sample.family || "-")} / {compact(sample.grade || "-")} / {compact(sample.submission_lane || "-")}</span>
                <p>{asArray(sample.blockers).map(String).slice(0, 4).join(", ")}</p>
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function FactoryCard({ title, envelope }: { title: string; envelope: ToolEnvelope | null | undefined }) {
  const data = asRecord(envelope?.data);
  const configured = data.configured;
  const dependency = String(data.dependency || "");
  const databaseConfigured = data.database_configured;
  const databaseBackend = String(data.database_backend || "sqlite");
  const databasePath = String(data.database_path || "");
  const databaseConfigSources = Array.isArray(data.database_config_sources) ? data.database_config_sources.join(", ") : "";
  const errorText = envelopeMessage(envelope);
  return (
    <article className="capability-card">
      <div className="card-head">
        <div>
          <span>{envelope?.error_code ? statusLabel(envelope.error_code) : "strategy_factory"}</span>
          <h3>{title}</h3>
        </div>
        <StatusBadge status={envelopeStatus(envelope)} label={statusLabel(envelopeStatus(envelope))} />
      </div>
      {envelope && !envelope.success && (
        <div className="notice warn">
          {dependency ? `${dependency}: ` : ""}
          {databaseConfigured && envelope.error_code ? "数据库已配置，但 strategy manager 返回错误。" : ""}
          {errorText}
        </div>
      )}
      {data.strict_incubation_blocker_summary ? (
        <div className="notice compact warn">
          Formal blockers: {String(asRecord(data.strict_incubation_blocker_summary).status || "reported")}
        </div>
      ) : null}
      <div className="kv-grid">
        <span>成功</span>
        <strong>{yesNo(envelope?.success ?? false)}</strong>
        <span>已配置</span>
        <strong>{yesNo(configured ?? envelope?.success ?? false)}</strong>
        <span>数据库</span>
        <strong>{databaseConfigured === undefined ? "-" : databaseConfigured ? "已配置" : "未配置"}</strong>
        <span>数据库后端</span>
        <strong>{databaseBackendLabel(databaseBackend)}</strong>
        <span>数据库路径</span>
        <strong>{databasePath || databaseConfigSources || "-"}</strong>
        <span>错误</span>
        <strong>{errorText}</strong>
      </div>
      <details className="raw-details">
        <summary>原始 {title}</summary>
        <JsonPanel value={envelope} />
      </details>
    </article>
  );
}

function intentFromEnvelope(envelope: ToolEnvelope | null): Record<string, unknown> {
  const data = asRecord(envelope?.data);
  return asRecord(data.intent || data.action_intent || data);
}

function sideEffectFromEnvelope(envelope: ToolEnvelope | null): Record<string, unknown> {
  const meta = asRecord(envelope?.meta);
  return asRecord(meta.side_effect);
}

export function StrategyFactoryPanel({
  payload,
  endpoint,
  apiToken,
  controlToken
}: {
  payload: CapabilityWorkbenchPayload | null;
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [intentMessage, setIntentMessage] = useState("NO_INTENT");
  const [busy, setBusy] = useState(false);
  const factory = payload?.strategy_factory;
  const envelopes = [factory?.status, factory?.runs, factory?.review_snapshot].filter(Boolean) as ToolEnvelope[];
  const successCount = envelopes.filter((item) => item.success).length;
  const hasControlToken = Boolean(controlToken.trim());
  const factoryStatus = !hasControlToken ? "gated" : !envelopes.length ? "not_loaded" : successCount === envelopes.length ? "implemented" : successCount > 0 ? "partial" : "unconfigured";

  async function createRunIntent() {
    setBusy(true);
    try {
      const envelope = await api.factoryIntentCreate(
        "factory_run_once",
        { execution_mode: "desktop_approved_once", source: "desktop_strategy_factory" },
        "从桌面控制面板运行一次策略工厂。"
      );
      setIntentEnvelope(envelope);
      setIntentMessage(envelope.success ? "STRATEGY_FACTORY_INTENT_CREATED" : envelope.error || "STRATEGY_FACTORY_INTENT_FAILED");
    } catch (error) {
      setIntentMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>策略工厂</span>
          <h2>调度器、运行和晋升评审</h2>
          <p>只读状态检查始终安全；会改变状态的操作仍然通过持久化审批意图执行。</p>
        </div>
        <StatusBadge status={factoryStatus} />
      </div>

      {!hasControlToken && (
        <div className="notice warn">需要控制令牌后，桌面端才能创建工厂操作意图。</div>
      )}

      <StrictIncubationBlockers envelope={factory?.status || null} />

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>受控操作</span>
            <h3>工厂单次运行</h3>
          </div>
          <StatusBadge status={intentEnvelope?.success ? "ready" : "not_loaded"} label={statusLabel(intentMessage)} technicalLabel={intentMessage} />
        </div>
        <button className="primary-button" disabled={busy || !hasControlToken} onClick={createRunIntent} type="button">
          <Play size={15} />
          创建运行意图
        </button>
        {intentEnvelope && (
          <>
            <div className="kv-grid" aria-label="strategy factory intent summary">
              <span>动作</span>
              <strong>{compact(intentFromEnvelope(intentEnvelope).action || intentFromEnvelope(intentEnvelope).target_action || "factory_run_once")}</strong>
              <span>意图 ID</span>
              <strong>{compact(intentFromEnvelope(intentEnvelope).intent_id || intentFromEnvelope(intentEnvelope).id)}</strong>
              <span>状态</span>
              <strong>{compact(intentFromEnvelope(intentEnvelope).status || (intentEnvelope.success ? "created" : intentEnvelope.error_code || intentEnvelope.error))}</strong>
              <span>目标工具</span>
              <strong>{compact(intentFromEnvelope(intentEnvelope).target_tool || "agent_action_intent_create")}</strong>
              <span>执行模式</span>
              <strong>{compact(asRecord(intentFromEnvelope(intentEnvelope).params).execution_mode || asRecord(intentFromEnvelope(intentEnvelope).params).source || "desktop_approved_once")}</strong>
              <span>副作用</span>
              <strong>{compact(sideEffectFromEnvelope(intentEnvelope).level || "durable_intent")}</strong>
            </div>
            <details className="raw-details" open>
              <summary>
                <GitPullRequest size={14} />
                最近意图
              </summary>
              <JsonPanel value={intentEnvelope} />
            </details>
          </>
        )}
      </div>

      <div className="capability-grid three">
        <FactoryCard title="工厂状态" envelope={factory?.status || null} />
        <FactoryCard title="最近运行" envelope={factory?.runs || null} />
        <FactoryCard title="评审快照" envelope={factory?.review_snapshot || null} />
      </div>
    </div>
  );
}
