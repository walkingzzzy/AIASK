import { useEffect, useState } from "react";
import { useAiSmoke } from "../../hooks/useAiSmoke";
import type { CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, StatusBadge } from "../../components/shared";

export function AiTestingPanel({
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
  const { status, result, models, message, busy, refreshStatus, runSmoke, refreshModels } = useAiSmoke(endpoint, apiToken, controlToken);
  const [prompt, setPrompt] = useState("Reply with AIASK model smoke ok.");
  const [model, setModel] = useState("");
  const currentStatus = status || payload?.ai || null;
  const runtimeMode = currentStatus?.mock ? "mock" : "live";

  useEffect(() => {
    refreshStatus().catch(() => undefined);
  }, [refreshStatus]);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>AI Tests</span>
          <h2>{currentStatus?.model || "Model runtime"}</h2>
          <p>
            Provider {currentStatus?.provider || "-"} / {runtimeMode} / base URL{" "}
            {currentStatus?.base_url_configured ? "configured" : "default"}
          </p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={runtimeMode === "live" ? "live_backend" : "mock_fixture"} label={runtimeMode} />
          <StatusBadge status={currentStatus?.configured ? "implemented" : "unconfigured"} />
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>Runtime</span>
              <h3>Model configuration</h3>
            </div>
            <button className="small-button" disabled={busy} onClick={() => refreshStatus()} type="button">Refresh</button>
          </div>
          <div className="kv-grid">
            <span>Provider</span>
            <strong>{currentStatus?.provider || "-"}</strong>
            <span>Model</span>
            <strong>{currentStatus?.model || "-"}</strong>
            <span>Mock</span>
            <strong>{String(currentStatus?.mock ?? "-")}</strong>
            <span>Mode</span>
            <strong>{runtimeMode}</strong>
            <span>Base URL</span>
            <strong>{currentStatus?.base_url_configured ? "configured" : "default"}</strong>
            <span>API key</span>
            <strong>{currentStatus?.api_key_configured ? "configured" : "not configured"}</strong>
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>Smoke</span>
              <h3>Run AI Smoke</h3>
            </div>
            <StatusBadge status={result?.success ? "implemented" : result ? "failed" : "not_loaded"} />
          </div>
          <label className="field-row">
            <span>Prompt</span>
            <input value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </label>
          <label className="field-row">
            <span>Model override</span>
            <input value={model} onChange={(event) => setModel(event.target.value)} placeholder={currentStatus?.model || "optional"} />
          </label>
          <div className="button-row">
            <button disabled={busy} onClick={() => runSmoke(prompt, model || undefined)} type="button">Run AI Smoke</button>
            <button disabled={busy} onClick={() => refreshModels()} type="button">List Models</button>
          </div>
          <p className="status-line">{message || "ready"}</p>
        </div>
      </section>

      <section className="capability-grid two">
        <div className="capability-section">
          <h3>Smoke Result</h3>
          <div className="kv-grid">
            <span>Success</span>
            <strong>{String(result?.success ?? false)}</strong>
            <span>Configured</span>
            <strong>{String(result?.configured ?? false)}</strong>
            <span>Mode</span>
            <strong>{result ? (result.mock ? "mock" : "live") : "-"}</strong>
            <span>Latency</span>
            <strong>{result?.latency_ms === undefined ? "-" : `${result.latency_ms}ms`}</strong>
            <span>Preview</span>
            <strong>{result?.response_preview || result?.error || "-"}</strong>
          </div>
        </div>
        <div className="capability-section">
          <h3>Models</h3>
          <div className="mini-list">
            {models.slice(0, 20).map((item) => (
              <article key={String(item.id || JSON.stringify(item))}>
                <strong>{String(item.id || "-")}</strong>
                <span>{String(item.owned_by || item.object || "model")}</span>
              </article>
            ))}
            {!models.length && <p className="muted">Run List Models to inspect OpenAI-compatible model IDs.</p>}
          </div>
        </div>
      </section>

      <details className="raw-details">
        <summary>Raw AI diagnostics</summary>
        <JsonPanel value={{ status: currentStatus, result, models }} />
      </details>
    </div>
  );
}
