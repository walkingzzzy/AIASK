import { Database, GitPullRequest, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { DesktopDataStatus, DesktopDataSyncPlan, ToolEnvelope } from "../../types";

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function intentIdFromEnvelope(envelope: ToolEnvelope | null): string {
  const data = envelope?.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const intent = data.intent && typeof data.intent === "object" ? (data.intent as Record<string, unknown>) : {};
  return String(intent.intent_id || "");
}

export function DataSyncWorkspace({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [codes, setCodes] = useState("600519, 000001, 000858");
  const [maxStaleDays, setMaxStaleDays] = useState("5");
  const [taskType, setTaskType] = useState("kline");
  const [period, setPeriod] = useState("daily");
  const [dataStatus, setDataStatus] = useState<DesktopDataStatus | null>(null);
  const [plan, setPlan] = useState<DesktopDataSyncPlan | null>(null);
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.dataStatus({ codes: splitList(codes), max_stale_days: Number(maxStaleDays || 5) });
      setDataStatus(payload);
      setMessage("DATA_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function generatePlan(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    try {
      const payload = await api.dataSyncPlan({
        codes: splitList(codes),
        max_stale_days: Number(maxStaleDays || 5),
        task_type: taskType,
        period
      });
      setPlan(payload);
      setDataStatus(payload.data_status || null);
      setMessage("SYNC_PLAN_READY");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createIntent() {
    if (!plan?.intent_request || !controlToken.trim()) return;
    setBusy(true);
    try {
      const envelope = await api.factoryIntentCreate(
        plan.intent_request.action,
        plan.intent_request.params,
        plan.intent_request.rationale || "Create data sync approval from Desktop."
      );
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? "SYNC_INTENT_CREATED" : envelope.error || "SYNC_INTENT_FAILED");
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

  const database = dataStatus?.database || {};
  const freshnessRecord =
    dataStatus?.freshness && typeof dataStatus.freshness === "object" ? (dataStatus.freshness as Record<string, unknown>) : {};
  const intentId = intentIdFromEnvelope(intentEnvelope);

  return (
    <section className="quant-workspace">
      <header className="quant-header">
        <div>
          <span>Data & Sync</span>
          <h1>Database quality and sync approvals</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : dataStatus?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="quant-body two-column">
        <form className="quant-params-panel" onSubmit={generatePlan}>
          <div className="section-header">
            <div>
              <span>Sync scope</span>
              <h3>Plan builder</h3>
            </div>
            <Database size={18} />
          </div>
          <label className="field-row">
            <span>Codes</span>
            <textarea value={codes} onChange={(event) => setCodes(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>Max stale days</span>
              <input value={maxStaleDays} onChange={(event) => setMaxStaleDays(event.target.value)} />
            </label>
            <label className="field-row">
              <span>Task type</span>
              <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
                <option value="kline">kline</option>
                <option value="quote">quote</option>
                <option value="financial">financial</option>
                <option value="core_market">core_market</option>
                <option value="factor_context">factor_context</option>
              </select>
            </label>
            <label className="field-row">
              <span>Period</span>
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="monthly">monthly</option>
              </select>
            </label>
          </div>
          <button className="primary-button" disabled={busy || !splitList(codes).length} type="submit">
            <Play size={15} />
            Generate sync plan
          </button>
          {!controlToken.trim() && (
            <div className="notice warn compact-notice">
              <ShieldCheck size={14} />
              Control token is required before the sync plan can become an approval intent.
            </div>
          )}
        </form>

        <section className="quant-center-panel">
          <div className="diagnostics-summary wide">
            <MetricCard label="Gate" value={dataStatus?.status || "-"} status={dataStatus?.status} />
            <MetricCard label="Codes" value={dataStatus?.codes?.length || splitList(codes).length} status="ready" />
            <MetricCard label="Missing" value={dataStatus?.missing_count ?? "-"} status={(dataStatus?.missing_count || 0) > 0 ? "failed" : "ready"} />
            <MetricCard label="Stale" value={dataStatus?.stale_count ?? "-"} status={(dataStatus?.stale_count || 0) > 0 ? "partial" : "ready"} />
          </div>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>SQLite / AKShare</span>
                <h3>Database readiness</h3>
              </div>
              <StatusBadge status={database.writable === false ? "failed" : "ready"} />
            </div>
            <div className="kv-grid">
              <span>Backend</span>
              <strong>{compact(database.backend)}</strong>
              <span>Writable</span>
              <strong>{compact(database.writable)}</strong>
              <span>Path</span>
              <strong>{compact(database.path)}</strong>
              <span>Sources</span>
              <strong>{compact(database.sources)}</strong>
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Freshness</span>
                <h3>Quality gate evidence</h3>
              </div>
              <StatusBadge status={dataStatus?.quality_gate?.success ? "ready" : "partial"} />
            </div>
            <JsonPanel value={freshnessRecord || dataStatus?.quality_gate || { status: "not_loaded" }} />
          </section>
        </section>

        <section className="quant-report-panel">
          <div className="section-header">
            <div>
              <span>Approval</span>
              <h3>Sync intent</h3>
            </div>
            <GitPullRequest size={18} />
          </div>
          {plan ? (
            <>
              <div className="kv-grid">
                <span>Action</span>
                <strong>{plan.intent_request.action}</strong>
                <span>Task</span>
                <strong>{compact(plan.intent_request.params.task_type)}</strong>
                <span>Period</span>
                <strong>{compact(plan.intent_request.params.period)}</strong>
                <span>Codes</span>
                <strong>{Array.isArray(plan.intent_request.params.codes) ? plan.intent_request.params.codes.length : "-"}</strong>
              </div>
              <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createIntent} type="button">
                <GitPullRequest size={15} />
                Create approval intent
              </button>
              {intentId && (
                <div className="notice ok">
                  <strong>{intentId}</strong>
                  <span>Review and confirm this intent from the Agent intent inspector.</span>
                </div>
              )}
              <details className="raw-details" open>
                <summary>Sync plan</summary>
                <JsonPanel value={{ plan, intentEnvelope }} />
              </details>
            </>
          ) : (
            <div className="empty-mini">
              <GitPullRequest size={24} />
              <span>Generate a sync plan before creating an approval intent.</span>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
