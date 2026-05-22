import { BarChart3, GitPullRequest, RefreshCw, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { FactorFactoryStatus, ToolEnvelope } from "../../types";

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function intentId(envelope: ToolEnvelope | null): string {
  const data = envelope?.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const intent = data.intent && typeof data.intent === "object" ? (data.intent as Record<string, unknown>) : {};
  return String(intent.intent_id || "");
}

export function FactorFactoryPanel({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [status, setStatus] = useState<FactorFactoryStatus | null>(null);
  const [codes, setCodes] = useState("600519, 000001, 000858");
  const [engines, setEngines] = useState("llm_primary, gp_classic, rule_seed");
  const [candidateCount, setCandidateCount] = useState("10");
  const [generations, setGenerations] = useState("2");
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.factorFactoryStatus(80);
      setStatus(payload);
      setMessage("FACTOR_FACTORY_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createRunIntent() {
    setBusy(true);
    try {
      const envelope = await api.factorFactoryRunIntent({
        codes: splitList(codes),
        engines: splitList(engines),
        candidate_count: Number(candidateCount || 10),
        evolution_generations: Number(generations || 2)
      });
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? "FACTOR_RUN_INTENT_CREATED" : envelope.error || "FACTOR_RUN_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createMaintenanceIntent() {
    setBusy(true);
    try {
      const envelope = await api.factorFactoryMaintenanceIntent({});
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? "FACTOR_MAINTENANCE_INTENT_CREATED" : envelope.error || "FACTOR_MAINTENANCE_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken]);

  const factory = status?.factory || {};
  const activeFactors = status?.active_factors || [];
  const poolHealth = status?.pool_health || {};
  const engineHealth = status?.engine_health || {};
  const createdIntent = intentId(intentEnvelope);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Factor Mining Factory</span>
          <h2>Factor pool, engine health, and approved mining cycles</h2>
          <p>Run and maintenance controls create durable approval intents. Confirmed execution stays inside the Agent facade.</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : status?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {!controlToken.trim() && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          Control token is required to create factor factory approval intents.
        </div>
      )}

      <div className="diagnostics-summary wide">
        <MetricCard label="Status" value={status?.status || "-"} status={status?.status} />
        <MetricCard label="Pool size" value={compact(factory.pool_size)} status="ready" />
        <MetricCard label="Runs" value={compact(factory.run_count)} status="ready" />
        <MetricCard label="Active factors" value={activeFactors.length} status={activeFactors.length ? "ready" : "not_loaded"} />
      </div>

      <section className="capability-grid two">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Approved action</span>
              <h3>Mining cycle intent</h3>
            </div>
            <GitPullRequest size={18} />
          </div>
          <label className="field-row">
            <span>Codes</span>
            <textarea value={codes} onChange={(event) => setCodes(event.target.value)} />
          </label>
          <label className="field-row">
            <span>Engines</span>
            <input value={engines} onChange={(event) => setEngines(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>Candidates</span>
              <input value={candidateCount} onChange={(event) => setCandidateCount(event.target.value)} />
            </label>
            <label className="field-row">
              <span>Generations</span>
              <input value={generations} onChange={(event) => setGenerations(event.target.value)} />
            </label>
          </div>
          <div className="button-row">
            <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createRunIntent} type="button">
              <BarChart3 size={15} />
              Create run intent
            </button>
            <button className="small-button" disabled={busy || !controlToken.trim()} onClick={createMaintenanceIntent} type="button">
              <Wrench size={14} />
              Maintenance intent
            </button>
          </div>
          {createdIntent && (
            <div className="notice ok">
              <strong>{createdIntent}</strong>
              <span>Confirm this intent from the Agent intent inspector to execute it.</span>
            </div>
          )}
        </article>

        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Health</span>
              <h3>Engine and pool status</h3>
            </div>
            <StatusBadge status={status?.status || "not_loaded"} />
          </div>
          <div className="kv-grid">
            <span>Initialized</span>
            <strong>{compact(factory.initialized)}</strong>
            <span>Loaded</span>
            <strong>{compact(factory.pool_loaded_from_db)}</strong>
            <span>Promoted</span>
            <strong>{compact(poolHealth.active_promoted_count)}</strong>
            <span>Quarantine</span>
            <strong>{compact(poolHealth.quarantine_count)}</strong>
          </div>
          <JsonPanel value={{ engineHealth, poolHealth }} />
        </article>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{activeFactors.length} factors</span>
            <h3>Active pool</h3>
          </div>
          <StatusBadge status={activeFactors.length ? "ready" : "not_loaded"} />
        </div>
        <div className="mini-list">
          {activeFactors.slice(0, 20).map((factor, index) => (
            <article key={String(factor.factor_id || factor.id || index)}>
              <strong>{String(factor.name || factor.factor_id || factor.id || `factor-${index + 1}`)}</strong>
              <span>{String(factor.family || factor.generation_engine || factor.status || "factor")}</span>
              <p>{compact(factor.validation_summary || factor.fitness || factor.quality_score)}</p>
            </article>
          ))}
          {!activeFactors.length && <p className="muted">No active factors are loaded in this snapshot.</p>}
        </div>
      </section>

      <details className="raw-details">
        <summary>Raw factor factory data</summary>
        <JsonPanel value={{ status, intentEnvelope }} />
      </details>
    </div>
  );
}
