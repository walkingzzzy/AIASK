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
          {databaseConfigured && envelope.error_code ? "Database is configured, but strategy manager returned an error. " : ""}
          {detail || envelope.error || envelope.error_code || "Strategy factory is not ready in this runtime."}
        </div>
      )}
      <div className="kv-grid">
        <span>Success</span>
        <strong>{String(envelope?.success ?? false)}</strong>
        <span>Configured</span>
        <strong>{String(configured ?? envelope?.success ?? false)}</strong>
        <span>Database</span>
        <strong>{databaseConfigured === undefined ? "-" : databaseConfigured ? "configured" : "not configured"}</strong>
        <span>DB backend</span>
        <strong>{databaseBackend}</strong>
        <span>DB path</span>
        <strong>{databasePath || databaseConfigSources || "-"}</strong>
        <span>Error</span>
        <strong>{errorText}</strong>
      </div>
      <details className="raw-details">
        <summary>Raw {title}</summary>
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
        "Run Strategy Factory once from the desktop control panel."
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
          <span>Strategy Factory</span>
          <h2>Scheduler, runs, promotion reviews</h2>
          <p>Read-only status is always safe. Mutating actions continue through durable approval intents.</p>
        </div>
        <StatusBadge status={factoryStatus} />
      </div>

      {!controlToken.trim() && (
        <div className="notice warn">Control token is required before factory action intents can be created from the desktop.</div>
      )}

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>Approved operation</span>
            <h3>Factory run once</h3>
          </div>
          <StatusBadge status={intentEnvelope?.success ? "ready" : "not_loaded"} label={intentMessage} />
        </div>
        <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createRunIntent} type="button">
          <Play size={15} />
          Create run intent
        </button>
        {intentEnvelope && (
          <details className="raw-details" open>
            <summary>
              <GitPullRequest size={14} />
              Latest intent
            </summary>
            <JsonPanel value={intentEnvelope} />
          </details>
        )}
      </div>

      <div className="capability-grid three">
        <FactoryCard title="Factory Status" envelope={factory?.status || null} />
        <FactoryCard title="Recent Runs" envelope={factory?.runs || null} />
        <FactoryCard title="Review Snapshot" envelope={factory?.review_snapshot || null} />
      </div>
    </div>
  );
}
