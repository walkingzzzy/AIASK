import { useMemo, useState } from "react";
import { GitPullRequest, Play } from "lucide-react";
import { formatApiError } from "../../api";
import type { CapabilityWorkbenchPayload, ToolEnvelope } from "../../types";
import { JsonPanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

function envelopeStatus(envelope: ToolEnvelope | null | undefined): string {
  if (!envelope) return "not_loaded";
  if (envelope.success) return "implemented";
  const data = envelope.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const errorCode = String(envelope.error_code || "");
  const configured = data.database_configured || data.configured;
  if (data.status === "partial" || (configured && (errorCode.includes("TIMEOUT") || errorCode.includes("RECOVERY") || errorCode.includes("UNAVAILABLE")))) {
    return "partial";
  }
  if (errorCode.includes("MISSING") || errorCode.includes("TIMEOUT") || errorCode.includes("UNAVAILABLE")) {
    return "unconfigured";
  }
  return "failed";
}

function FactoryCard({ title, envelope }: { title: string; envelope: ToolEnvelope | null | undefined }) {
  const data = envelope?.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const configured = data.configured;
  const detail = String(data.detail || "");
  const dependency = String(data.dependency || "");
  const databaseConfigured = data.database_configured;
  const databaseBackend = String(data.database_backend || "sqlite");
  const databasePath = String(data.database_path || "");
  const databaseConfigSources = Array.isArray(data.database_config_sources) ? data.database_config_sources.join(", ") : "";
  const errorText = envelope?.error || detail || envelope?.error_code || "-";
  return (
    <article className="capability-card">
      <div className="card-head">
        <div>
          <span>{envelope?.error_code || "strategy_factory"}</span>
          <h3>{title}</h3>
        </div>
        <StatusBadge status={envelopeStatus(envelope)} />
      </div>
      {envelope && !envelope.success && (
        <div className="notice warn">
          {dependency ? `${dependency}: ` : ""}
          {databaseConfigured && envelope.error_code ? "数据库已配置，但 strategy manager 返回错误。" : ""}
          {detail || envelope.error || envelope.error_code || "当前运行时的策略工厂尚未就绪。"}
        </div>
      )}
      <div className="kv-grid">
        <span>成功</span>
        <strong>{String(envelope?.success ?? false)}</strong>
        <span>已配置</span>
        <strong>{String(configured ?? envelope?.success ?? false)}</strong>
        <span>数据库</span>
        <strong>{databaseConfigured === undefined ? "-" : databaseConfigured ? "已配置" : "未配置"}</strong>
        <span>DB backend</span>
        <strong>{databaseBackend}</strong>
        <span>DB path</span>
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
  const factoryStatus = !envelopes.length ? "not_loaded" : successCount === envelopes.length ? "implemented" : successCount > 0 ? "partial" : "unconfigured";

  async function createRunIntent() {
    setBusy(true);
    try {
      const envelope = await api.factoryIntentCreate(
        "factory_run_once",
        { execution_mode: "desktop_approved_once", source: "desktop_strategy_factory" },
        "从桌面控制面板运行一次 Strategy Factory。"
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

      {!controlToken.trim() && (
        <div className="notice warn">需要控制令牌后，桌面端才能创建工厂操作意图。</div>
      )}

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>受控操作</span>
            <h3>工厂单次运行</h3>
          </div>
          <StatusBadge status={intentEnvelope?.success ? "ready" : "not_loaded"} label={intentMessage} />
        </div>
        <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createRunIntent} type="button">
          <Play size={15} />
          创建运行意图
        </button>
        {intentEnvelope && (
          <details className="raw-details" open>
            <summary>
              <GitPullRequest size={14} />
              最近意图
            </summary>
            <JsonPanel value={intentEnvelope} />
          </details>
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
