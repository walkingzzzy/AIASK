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
  const [providerStatus, setProviderStatus] = useState<unknown>(null);
  const [models, setModels] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, modelsPayload] = await Promise.all([
        api.settingsStatus(),
        api.aiModels()
      ]);
      setSettings(settingsPayload);
      setProviderStatus(settingsPayload.llm.providers);
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
  const providersRecord =
    providerStatus && typeof providerStatus === "object"
      ? (providerStatus as Record<string, unknown>)
      : settings?.llm.providers && typeof settings.llm.providers === "object"
        ? (settings.llm.providers as Record<string, unknown>)
        : {};
  const providers = Array.isArray(providersRecord.providers) ? providersRecord.providers as Array<Record<string, unknown>> : [];

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>模型</span>
          <h1>LLM 提供方配置</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : ai?.configured ? "ready" : "unconfigured"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{ai?.provider || "-"}</span>
              <h2>{ai?.model || "模型未加载"}</h2>
              <p>提供方状态来自 Agent API，项目根配置由服务端加载，密钥会脱敏展示。</p>
            </div>
            <BrainCircuit size={24} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="提供方" value={ai?.provider || "-"} status={ai?.configured ? "ready" : "unconfigured"} />
            <MetricCard label="API 密钥" value={ai?.api_key_configured ? "已配置" : "缺失 / Mock"} status={ai?.api_key_configured ? "ready" : "partial"} />
            <MetricCard label="基础 URL" value={ai?.base_url_configured ? "已配置" : "默认"} status="ready" />
            <MetricCard label="来源" value={ai?.config_source?.loaded ? String(ai.config_source.source || "project") : "进程环境"} status="ready" />
            <MetricCard label="池" value={compact(providersRecord.configured_count || 0)} status={(providersRecord.configured_count as number) ? "ready" : "partial"} />
          </div>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>提供方池</span>
                  <h3>已配置提供方</h3>
                </div>
                <StatusBadge status={providersRecord.status as string || "not_loaded"} />
              </div>
              <div className="mini-list">
                {providers.map((provider) => (
                  <article key={String(provider.name)}>
                    <strong>{String(provider.name)}</strong>
                    <span>{String(provider.type || provider.model || "provider")}</span>
                    <StatusBadge status={String(provider.status || "not_loaded")} label={provider.configured ? "已配置" : String(provider.status || "缺失")} />
                  </article>
                ))}
                {!providers.length && <p className="muted">尚未加载提供方池条目。</p>}
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>模型列表</span>
                  <h3>提供方响应</h3>
                </div>
                <StatusBadge status={models ? "ready" : "not_loaded"} />
              </div>
              <JsonPanel value={models || { status: "not_loaded" }} />
            </article>
          </section>

          <details className="raw-details">
            <summary>原始模型配置</summary>
            <JsonPanel value={{ settings, providerStatus, models }} />
          </details>
        </div>
      </div>
    </section>
  );
}
