import { BrainCircuit, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { DesktopSettingsStatus } from "../../types";

export function ModelsWorkspace({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [models, setModels] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, modelsPayload] = await Promise.all([api.settingsStatus(), api.aiModels()]);
      setSettings(settingsPayload);
      setModels(modelsPayload);
      setMessage("MODEL_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const ai = settings?.llm.ai_status;
  const providersRecord = settings?.llm.providers && typeof settings.llm.providers === "object" ? (settings.llm.providers as Record<string, unknown>) : {};
  const providers = Array.isArray(providersRecord.providers) ? providersRecord.providers as Array<Record<string, unknown>> : [];

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Models</span>
          <h1>LLM provider configuration</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : ai?.configured ? "ready" : "unconfigured"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{ai?.provider || "-"}</span>
              <h2>{ai?.model || "Model not loaded"}</h2>
              <p>Provider state comes from the Agent API, with root project configuration loaded server-side and secrets redacted.</p>
            </div>
            <BrainCircuit size={24} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="Provider" value={ai?.provider || "-"} status={ai?.configured ? "ready" : "unconfigured"} />
            <MetricCard label="API key" value={ai?.api_key_configured ? "configured" : "missing/mock"} status={ai?.api_key_configured ? "ready" : "partial"} />
            <MetricCard label="Base URL" value={ai?.base_url_configured ? "configured" : "default"} status="ready" />
            <MetricCard label="Source" value={ai?.config_source?.loaded ? String(ai.config_source.source || "project") : "process"} status="ready" />
            <MetricCard label="Pool" value={compact(providersRecord.configured_count || 0)} status={(providersRecord.configured_count as number) ? "ready" : "partial"} />
          </div>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Provider pool</span>
                  <h3>Configured providers</h3>
                </div>
                <StatusBadge status={providersRecord.status as string || "not_loaded"} />
              </div>
              <div className="mini-list">
                {providers.map((provider) => (
                  <article key={String(provider.name)}>
                    <strong>{String(provider.name)}</strong>
                    <span>{String(provider.type || provider.model || "provider")}</span>
                    <StatusBadge status={String(provider.status || "not_loaded")} label={provider.configured ? "configured" : String(provider.status || "missing")} />
                  </article>
                ))}
                {!providers.length && <p className="muted">No provider pool entries loaded.</p>}
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Model list</span>
                  <h3>Provider response</h3>
                </div>
                <StatusBadge status={models ? "ready" : "not_loaded"} />
              </div>
              <JsonPanel value={models || { status: "not_loaded" }} />
            </article>
          </section>

          <details className="raw-details">
            <summary>Raw model configuration</summary>
            <JsonPanel value={{ settings, models }} />
          </details>
        </div>
      </div>
    </section>
  );
}
